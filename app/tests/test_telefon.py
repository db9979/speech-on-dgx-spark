"""Telefon (telefon.py, telefon_ton.py, telefon_ich.py, plan telefon-anruf.md T1 and T2): the sound codecs, the SIP parser
and digest, whole calls against a PBX made up here (REGISTER with 401 and digest, INVITE with G.722 and G.711, RTP, DTMF,
BYE), own numbers confirmed with a code, the Telefon-PIN with its lock, and Ich → Telefon. No telephone, no clock: every
wait is a few hundred milliseconds, times are passed in."""
import asyncio
import hashlib
import json
import math
import random
import re
import socket
import struct
import unittest
from unittest import mock

import numpy as np

from tests import helpers

helpers.start()
import esp32  # noqa: E402
import profiles  # noqa: E402
import telefon  # noqa: E402
import telefon_ich  # noqa: E402
import telefon_ton  # noqa: E402


def tone(seconds, rate=16000, freq=440.0, level=9000):
    t = np.arange(int(rate * seconds)) / rate
    return (np.sin(2 * np.pi * freq * t) * level).astype("<i2").tobytes()


def snr(a, b):
    x = np.frombuffer(a, dtype="<i2").astype(np.float64)
    y = np.frombuffer(b, dtype="<i2").astype(np.float64)
    n = min(len(x), len(y))
    best = -99.0
    for d in range(0, 64):   # the codec's own delay
        if n - d < 100:
            break
        e = x[:n - d] - y[d:n]
        best = max(best, 10 * math.log10(np.sum(x[:n - d] ** 2) / max(np.sum(e ** 2), 1e-9)))
    return best


class Codecs(unittest.TestCase):
    def test_g711_roundtrip(self):
        pcm = tone(0.2, 8000)
        for enc, dec in ((telefon_ton.alaw_encode, telefon_ton.alaw_decode), (telefon_ton.ulaw_encode, telefon_ton.ulaw_decode)):
            data = enc(pcm)
            self.assertEqual(len(data), len(pcm) // 2)
            self.assertGreater(snr(pcm, dec(data)), 30)

    def test_g711_known_values(self):
        # ITU-T G.711 tables: silence and full scale
        self.assertEqual(telefon_ton.alaw_encode(b"\x00\x00"), b"\xd5")
        self.assertEqual(telefon_ton.ulaw_encode(b"\x00\x00"), b"\xff")
        self.assertEqual(telefon_ton.alaw_encode(struct.pack("<h", 32767)), b"\xaa")
        self.assertEqual(telefon_ton.ulaw_encode(struct.pack("<h", 32767)), b"\x80")

    def test_g722_roundtrip_and_size(self):
        pcm = tone(0.4, 16000, 700) + tone(0.4, 16000, 2500, 6000)
        enc, dec = telefon_ton.G722Encoder(), telefon_ton.G722Decoder()
        data = b"".join(enc.encode(pcm[i:i + 640]) for i in range(0, len(pcm), 640))
        self.assertEqual(len(data), len(pcm) // 4)          # 64 kbit/s: one byte per two samples
        out = b"".join(dec.decode(data[i:i + 160]) for i in range(0, len(data), 160))
        self.assertEqual(len(out), len(pcm))
        self.assertGreater(snr(pcm[3200:], out[3200:]), 15)

    def test_resampler_keeps_tone_across_pieces(self):
        pcm = tone(0.5, 24000, 500)
        one = telefon_ton.Resampler(24000, 8000).feed(pcm)
        r = telefon_ton.Resampler(24000, 8000)
        pieces = b"".join(r.feed(pcm[i:i + 960]) for i in range(0, len(pcm), 960))
        self.assertAlmostEqual(len(one) / 2, 4000, delta=40)
        self.assertGreater(snr(one[400:len(pieces)], pieces[400:]), 40)

    def test_codec_frames(self):
        for pt in (9, 8, 0):
            c = telefon_ton.Codec(pt)
            frame = c.encode(b"\0\0" * c.samples_per_frame())
            self.assertEqual(len(frame), 160)
            self.assertEqual(len(c.decode(frame)) // 2 >= 300, True)


class Parser(unittest.TestCase):
    INV = ("INVITE sip:spark@192.168.178.20:31060 SIP/2.0\r\nVia: SIP/2.0/UDP 192.168.178.1:5060;branch=z9hG4bKx\r\n"
           "From: \"Küche\" <sip:**611@fritz.box>;tag=a1\r\nTo: <sip:spark@fritz.box>\r\nCall-ID: c1@fritz\r\n"
           "CSeq: 7 INVITE\r\nContact: <sip:**611@192.168.178.1:5060>\r\nContent-Type: application/sdp\r\n")

    def msg(self, body="v=0\r\n"):
        return (self.INV + f"Content-Length: {len(body)}\r\n\r\n" + body).encode()

    def test_reads_an_invite(self):
        m = telefon.parse(self.msg())
        self.assertEqual((m.method, m.cseq()), ("INVITE", (7, "INVITE")))
        self.assertEqual(telefon.number_of(m), "**611")
        self.assertEqual(telefon.uri_of(m.get("contact")), "sip:**611@192.168.178.1:5060")

    def test_refuses_large_and_broken(self):
        self.assertIsNone(telefon.parse(self.msg("x" * telefon.MAX_MSG)))
        self.assertIsNone(telefon.parse(b"\xff\xfe" + self.msg()))
        self.assertIsNone(telefon.parse(b"HELLO\r\n\r\n"))
        self.assertIsNone(telefon.parse(self.msg().replace(b"Call-ID: c1@fritz\r\n", b"")))
        self.assertIsNone(telefon.parse(self.INV.encode() + b"Content-Length: 999\r\n\r\nv=0"))
        self.assertIsNone(telefon.parse(self.INV.encode() + b"X: 1\r\n" * 70 + b"\r\n"))

    def test_fuzz_never_raises(self):
        rnd = random.Random(4733)
        base = self.msg(telefon.sdp_offer("192.168.178.1", 7078, [9, 8, 0], 1))
        for _ in range(3000):
            b = bytearray(base)
            for _ in range(rnd.randint(1, 12)):
                k = rnd.randrange(len(b))
                op = rnd.random()
                if op < 0.4:
                    b[k] = rnd.randrange(256)
                elif op < 0.7:
                    del b[k:k + rnd.randint(1, 30)]
                else:
                    b[k:k] = bytes(rnd.randrange(256) for _ in range(rnd.randint(1, 20)))
            m = telefon.parse(bytes(b))
            if m is not None:
                telefon.number_of(m)
                telefon.sdp_parse(m.body)
                m.cseq()

    def test_digest_rfc2617_example(self):
        chal = 'Digest realm="testrealm@host.com", qop="auth,auth-int", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", ' \
               'opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        out = telefon.digest(chal, "GET", "/dir/index.html", "Mufasa", "Circle Of Life", 1, "0a4f113b")
        self.assertIn('response="6629fae49393a05397450978507c4ef1"', out)
        self.assertIn('opaque="5ccc069c403ebaf9f0171e9517f40e41"', out)
        sha = telefon.digest('Digest realm="r", nonce="n", algorithm=SHA-256', "REGISTER", "sip:x", "u", "p")
        ha1, ha2 = hashlib.sha256(b"u:r:p").hexdigest(), hashlib.sha256(b"REGISTER:sip:x").hexdigest()
        self.assertIn(hashlib.sha256(f"{ha1}:n:{ha2}".encode()).hexdigest(), sha)
        with self.assertRaises(ValueError):
            telefon.digest('Digest realm="r", nonce="n", algorithm=MD5-sess-unknown', "REGISTER", "sip:x", "u", "p")

    def test_sdp_and_codec_choice(self):
        sdp = telefon.sdp_parse(telefon.sdp_offer("192.168.178.1", 7078, [8, 0, 9], 5))
        self.assertEqual((sdp["ip"], sdp["port"], sdp["dtmf"]), ("192.168.178.1", 7078, 101))
        self.assertEqual(telefon.choose(sdp, "hd"), 9)
        self.assertEqual(telefon.choose(sdp, "schmal"), 8)
        self.assertIsNone(telefon.choose(telefon.sdp_parse("m=audio 4000 RTP/AVP 18\r\n"), "hd"))

    def test_internal_numbers_by_preset_and_home_network_only(self):
        self.assertTrue(telefon.internal("**611", "fritzbox"))
        self.assertFalse(telefon.internal("01701234567", "fritzbox"))
        self.assertFalse(telefon.internal("", "fritzbox"))
        self.assertTrue(telefon.lan_ip("192.168.178.1"))
        for ip in ("8.8.8.8", "127.0.0.1", "169.254.1.1", "0.0.0.0", "nonsense"):
            self.assertFalse(telefon.lan_ip(ip), ip)

    def test_every_preset_complete_in_both_languages(self):
        ids = set()
        for a in telefon.presets():
            self.assertNotIn(a["id"], ids)
            ids.add(a["id"])
            re.compile(a["intern"])
            self.assertTrue(a["name"] and a["steps"])
            for de, en in a["steps"] + [a["hint"]]:
                self.assertTrue(de.strip() and en.strip(), a["id"])
        self.assertIn("andere", ids)
        self.assertIn("fritzbox", ids)


# ---------------------------------------------------------------- a made-up PBX
class Pbx(asyncio.DatagramProtocol):
    def __init__(self, pw="geheim-1234"):
        self.pw, self.got, self.q, self.nonce = pw, [], asyncio.Queue(), "n0nce"

    def connection_made(self, t):
        self.t = t

    def datagram_received(self, data, addr):
        m = telefon.parse(data)
        self.got.append(m)
        if m and m.method == "REGISTER":
            auth = m.get("authorization")
            if not auth:
                self.reply(m, addr, f'401 Unauthorized\r\nWWW-Authenticate: Digest realm="fritz.box", nonce="{self.nonce}", qop="auth"')
                return
            p = dict((k, a or b) for k, a, b in re.findall(r'(\w+)=(?:"([^"]*)"|([^\s,]+))', auth))
            h = lambda s: hashlib.md5(s.encode()).hexdigest()  # noqa: E731
            want = h(f"{h(p['username'] + ':fritz.box:' + self.pw)}:{self.nonce}:{p['nc']}:{p['cnonce']}:auth:{h('REGISTER:' + p['uri'])}")
            if p["response"] == want:
                self.reply(m, addr, "200 OK\r\nContact: " + m.get("contact") + ";expires=300")
            else:
                self.reply(m, addr, "403 Forbidden")
            return
        self.q.put_nowait((m, addr))

    def reply(self, m, addr, status):
        self.t.sendto((
            f"SIP/2.0 {status}\r\nVia: {m.get('via')}\r\nFrom: {m.get('from')}\r\nTo: {m.get('to')};tag=pbx\r\n"
            f"Call-ID: {m.get('call-id')}\r\nCSeq: {m.get('cseq')}\r\nContent-Length: 0\r\n\r\n").encode(), addr)


class Phone(asyncio.DatagramProtocol):
    """The handset's sound (RTP) at the PBX."""

    def __init__(self):
        self.packets = []

    def connection_made(self, t):
        self.t = t

    def datagram_received(self, data, addr):
        self.packets.append((data, addr))


def invite(spark, number, rtp_port, cid, pts="9 8 0 101", cseq=1):
    sdp = (f"v=0\r\no=fb 1 1 IN IP4 127.0.0.1\r\ns=-\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio {rtp_port} RTP/AVP {pts}\r\n"
           "a=rtpmap:9 G722/8000\r\na=rtpmap:8 PCMA/8000\r\na=rtpmap:101 telephone-event/8000\r\n")
    return (f"INVITE sip:spark@127.0.0.1:{spark} SIP/2.0\r\nVia: SIP/2.0/UDP 127.0.0.1;branch=z9hG4bK{cid}\r\n"
            f"From: <sip:{number}@fritz.box>;tag=f{cid}\r\nTo: <sip:spark@fritz.box>\r\nCall-ID: {cid}\r\nCSeq: {cseq} INVITE\r\n"
            f"Contact: <sip:{number}@127.0.0.1>\r\nContent-Type: application/sdp\r\nContent-Length: {len(sdp)}\r\n\r\n{sdp}").encode()


def ack_or_bye(meth, cid, spark, cseq):
    return (f"{meth} sip:spark@127.0.0.1:{spark} SIP/2.0\r\nVia: SIP/2.0/UDP 127.0.0.1;branch=z9hG4bKa{cseq}\r\n"
            f"From: <sip:x@fritz.box>;tag=f{cid}\r\nTo: <sip:spark@fritz.box>;tag=t\r\nCall-ID: {cid}\r\n"
            f"CSeq: {cseq} {meth}\r\nContent-Length: 0\r\n\r\n").encode()


def rtp(seq, pt, payload, ts=None, marker=0):
    return struct.pack("!BBHII", 0x80, (marker << 7) | pt, seq, ts if ts is not None else seq * 160, 77) + payload


class Calls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uid = profiles.add_user("Tele Toni", "4711")
        cls.blocked = profiles.add_user("Tele Berta", "4712")

    def setUp(self):
        helpers.set_config(telefon=True, telefon_gaeste=False, telefon_max=1, speaker_id=False,
                           deny={"telefon": [self.blocked]})
        self.patches = [mock.patch.object(telefon, "SIP_PORT", 0), mock.patch.object(telefon, "RTP_PORTS", (0,)),
                        mock.patch.object(telefon, "RING", 0.05), mock.patch.object(telefon, "lan_ip", lambda ip: ip.startswith("127.")),
                        mock.patch.object(telefon, "QUIET_ASK", 1.5), mock.patch.object(telefon, "QUIET_END", 0.8)]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        self.addCleanup(lambda: helpers.set_config(telefon=False, deny={}))
        self.heard = []

        async def transcribe(pcm):
            self.heard.append(len(pcm))
            return self.say_next.pop(0) if self.say_next else ""
        self.say_next = []
        self.patches.append(mock.patch.object(esp32, "transcribe", transcribe))
        self.patches[-1].start()

    def run_with_pbx(self, body, pw="geheim-1234"):
        async def go():
            loop = asyncio.get_running_loop()
            pbx = Pbx()
            tp, _ = await loop.create_datagram_endpoint(lambda: pbx, local_addr=("127.0.0.1", 0))
            port = tp.get_extra_info("sockname")[1]
            z = {"anlage": "fritzbox", "host": "127.0.0.1", "port": port, "user": "spark620", "pw": pw}
            with mock.patch.object(telefon, "zugang", lambda: dict(z)), mock.patch.object(
                    telefon, "nummern", lambda: {"**611": {"uid": self.uid, "name": "Küche"}, "**612": {"uid": "", "name": "Flur"},
                                                 "**613": {"uid": self.blocked, "name": ""}}), \
                    mock.patch.object(telefon, "seen", lambda n: None):
                a = await telefon._start(z)
                try:
                    return await body(a, pbx, port)
                finally:
                    a.close()
                    tp.close()
        return asyncio.run(go())

    def test_register_with_digest(self):
        async def body(a, pbx, port):
            return a.reg, [m.method for m in pbx.got]
        reg, methods = self.run_with_pbx(body)
        self.assertTrue(reg["ok"])
        self.assertEqual(methods, ["REGISTER", "REGISTER"])

    def test_wrong_password_says_so(self):
        async def body(a, pbx, port):
            return a.reg
        reg = self.run_with_pbx(body, pw="falsch")
        self.assertEqual((reg["ok"], reg["why"]), (False, "zugang"))
        self.assertIn("Kennwort", telefon.SAY["zugang"][0])

    def test_messages_from_other_addresses_are_dropped(self):
        async def body(a, pbx, port):
            before = telefon._today.counts()["fremd"]
            a.datagram_received(invite(a.port, "**611", 4000, "x1"), ("127.0.0.2", 5060))
            a.datagram_received(b"garbage", (a.pbx[0], port))
            return telefon._today.counts()["fremd"] - before, a.calls
        n, calls = self.run_with_pbx(body)
        self.assertEqual(n, 1)
        self.assertEqual(calls, {})

    async def _answer(self, pbx, cid):
        """Waits for the Spark's final answer to the INVITE (skips 100 and 180)."""
        while True:
            m, addr = await asyncio.wait_for(pbx.q.get(), 5)
            if m and m.code >= 200 and m.get("call-id") == cid:
                return m

    def test_outside_number_and_busy_are_refused(self):
        async def body(a, pbx, port):
            to = ("127.0.0.1", a.port)
            pbx.t.sendto(invite(a.port, "01701234567", 4000, "out1"), to)
            out = (await self._answer(pbx, "out1")).code
            pbx.t.sendto(invite(a.port, "**613", 4000, "blk1"), to)
            blk = (await self._answer(pbx, "blk1")).code
            return out, blk
        with _quiet() as log:
            out, blk = self.run_with_pbx(body)
        self.assertEqual((out, blk), (603, 403))
        self.assertIn("telefon: anruf extern abgelehnt", log.text)
        self.assertNotIn("0170", log.text)          # an external number never in the log

    def test_a_call_greets_answers_and_hangs_up(self):
        self.say_next = ["Wie spät ist es?"]

        async def body(a, pbx, port):
            loop = asyncio.get_running_loop()
            ph = Phone()
            pt_, _ = await loop.create_datagram_endpoint(lambda: ph, local_addr=("127.0.0.1", 0))
            rport = pt_.get_extra_info("sockname")[1]
            to = ("127.0.0.1", a.port)
            pbx.t.sendto(invite(a.port, "**611", rport, "call1"), to)
            ok = await self._answer(pbx, "call1")
            sdp = telefon.sdp_parse(ok.body)
            pbx.t.sendto(ack_or_bye("ACK", "call1", a.port, 1), to)
            # the greeting comes as G.722 packets
            for _ in range(100):
                if len(ph.packets) > 20:
                    break
                await asyncio.sleep(0.05)
            spark_rtp = ("127.0.0.1", sdp["port"])
            # a question: 1 s of a loud tone, then quiet, as G.722 every 20 ms
            enc = telefon_ton.G722Encoder()
            speech = b"\0\0" * 8000 + tone(1.0, 16000, 300, 12000) + b"\0\0" * 16000   # quiet first: the Ear learns the line
            for i in range(0, len(speech), 640):
                pt_.sendto(rtp(i // 640, 9, enc.encode(speech[i:i + 640])), spark_rtp)
                await asyncio.sleep(0.004)
            for _ in range(200):
                if self.heard and a.calls.get("call1") and a.calls["call1"].questions:
                    break
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.3)
            # "#" as RFC 4733 (end bit) while it speaks or listens, then hang up
            pt_.sendto(rtp(900, 101, bytes([11, 0x80, 0, 160])), spark_rtp)
            call = a.calls.get("call1")
            pbx.t.sendto(ack_or_bye("BYE", "call1", a.port, 2), to)
            bye_ok = None
            while bye_ok is None:
                m, _ = await asyncio.wait_for(pbx.q.get(), 5)
                if m and m.code and m.cseq()[1] == "BYE":
                    bye_ok = m.code
            for _ in range(60):
                if "call1" not in a.calls:
                    break
                await asyncio.sleep(0.05)
            pt_.close()
            return ok, sdp, len(ph.packets), call, bye_ok, "call1" in a.calls
        with _quiet() as log:
            ok, sdp, n, call, bye_ok, still = self.run_with_pbx(body)
        self.assertEqual(ok.code, 200)
        self.assertEqual(sdp["pts"], [9, 101])
        self.assertGreater(n, 20)
        self.assertEqual(call.questions, 1)
        self.assertEqual(call.uid, self.uid)
        self.assertEqual(bye_ok, 200)
        self.assertFalse(still)
        self.assertIn("telefon: anruf intern **611 als Profil ", log.text)
        self.assertIn("telefon: aufgelegt nach", log.text)
        self.assertNotIn("Wie spät", log.text)       # never what was said
        convo = [c for c in profiles.convos(self.uid) if str(c.get("id", "")).startswith("tel-")]
        self.assertTrue(convo)
        msgs = convo[0].get("msgs", [])
        # the speaker ID is off: the turn counts as not the owner's voice (outside, like at a speaker)
        self.assertTrue(msgs and msgs[0].get("outside"))

    def test_silence_asks_then_hangs_up(self):
        async def body(a, pbx, port):
            loop = asyncio.get_running_loop()
            ph = Phone()
            pt_, _ = await loop.create_datagram_endpoint(lambda: ph, local_addr=("127.0.0.1", 0))
            rport = pt_.get_extra_info("sockname")[1]
            to = ("127.0.0.1", a.port)
            pbx.t.sendto(invite(a.port, "**612", rport, "call2", pts="8 101"), to)
            ok = await self._answer(pbx, "call2")
            pbx.t.sendto(ack_or_bye("ACK", "call2", a.port, 1), to)
            bye = None
            while bye is None:
                m, addr = await asyncio.wait_for(pbx.q.get(), 15)
                if m and m.method == "BYE":
                    bye = m
                    pbx.t.sendto(telefon.response(m, 200, "OK"), addr)
            for _ in range(60):
                if "call2" not in a.calls:
                    break
                await asyncio.sleep(0.05)
            pt_.close()
            return ok, bye
        with _quiet() as log:
            ok, bye = self.run_with_pbx(body)
        self.assertEqual(telefon.sdp_parse(ok.body)["pts"], [8, 101])
        self.assertEqual(bye.get("call-id"), "call2")
        self.assertIn("gemeinsames telefon", log.text)
        self.assertIn("aufgelegt nach", log.text)
        self.assertTrue(any("Noch etwas" in t for t in helpers.TTS_TEXT))

    def test_unassigned_handset_hears_a_sentence_and_the_call_ends(self):
        async def body(a, pbx, port):
            loop = asyncio.get_running_loop()
            ph = Phone()
            pt_, _ = await loop.create_datagram_endpoint(lambda: ph, local_addr=("127.0.0.1", 0))
            to = ("127.0.0.1", a.port)
            pbx.t.sendto(invite(a.port, "**619", pt_.get_extra_info("sockname")[1], "call3"), to)
            await self._answer(pbx, "call3")
            pbx.t.sendto(ack_or_bye("ACK", "call3", a.port, 1), to)
            while True:
                m, addr = await asyncio.wait_for(pbx.q.get(), 10)
                if m and m.method == "BYE":
                    pbx.t.sendto(telefon.response(m, 200, "OK"), addr)
                    break
            pt_.close()
            return True
        with _quiet() as log:
            self.run_with_pbx(body)
        self.assertIn("nicht zugeordnet", log.text)
        self.assertTrue(any("noch keinem Profil zugeordnet" in t for t in helpers.TTS_TEXT))

    def test_busy_when_one_call_runs(self):
        async def body(a, pbx, port):
            ph = Phone()
            loop = asyncio.get_running_loop()
            pt_, _ = await loop.create_datagram_endpoint(lambda: ph, local_addr=("127.0.0.1", 0))
            to = ("127.0.0.1", a.port)
            pbx.t.sendto(invite(a.port, "**611", pt_.get_extra_info("sockname")[1], "b1"), to)
            await self._answer(pbx, "b1")
            pbx.t.sendto(ack_or_bye("ACK", "b1", a.port, 1), to)
            pbx.t.sendto(invite(a.port, "**612", 4000, "b2"), to)
            second = (await self._answer(pbx, "b2")).code
            pbx.t.sendto(ack_or_bye("BYE", "b1", a.port, 2), to)
            await asyncio.sleep(0.2)
            pt_.close()
            return second
        with _quiet() as log:
            self.assertEqual(self.run_with_pbx(body), 486)
        self.assertIn("telefon: besetzt", log.text)


    # ------------------------------------------------------------ T2: code and PIN typed on the phone
    async def _open(self, a, pbx, number, cid):
        loop = asyncio.get_running_loop()
        ph = Phone()
        pt_, _ = await loop.create_datagram_endpoint(lambda: ph, local_addr=("127.0.0.1", 0))
        to = ("127.0.0.1", a.port)
        pbx.t.sendto(invite(a.port, number, pt_.get_extra_info("sockname")[1], cid), to)
        ok = await self._answer(pbx, cid)
        if ok.code != 200:
            pt_.close()
            return ok.code, None, None, to
        pbx.t.sendto(ack_or_bye("ACK", cid, a.port, 1), to)
        return 200, pt_, ("127.0.0.1", telefon.sdp_parse(ok.body)["port"]), to

    @staticmethod
    async def _keys(pt_, spark_rtp, keys, base=1000):
        for i, k in enumerate(keys):
            pt_.sendto(rtp(base + i, 101, bytes(["0123456789*#".index(k), 0x80, 0, 160]), ts=(base + i) * 1600), spark_rtp)
            await asyncio.sleep(0.02)

    async def _until(self, check, wait=8.0):
        for _ in range(int(wait / 0.05)):
            if check():
                return True
            await asyncio.sleep(0.05)
        return False

    def setUp_t2(self):
        telefon_ich._fails.clear()
        telefon_ich._locked.clear()
        telefon_ich.clear(self.uid)

    def test_an_own_number_is_confirmed_with_the_code_typed_on_a_call(self):
        self.setUp_t2()
        code = telefon_ich.add_number(self.uid, "0170 1234567", "Handy")
        self.assertEqual(telefon_ich.pending_for("+491701234567"), self.uid)

        async def body(a, pbx, port):
            # a wrong code first, then the right one
            st, pt_, sr, to = await self._open(a, pbx, "01701234567", "c1")
            wrong = "".join(str((int(c) + 1) % 10) for c in code)
            await asyncio.sleep(0.3)
            await self._keys(pt_, sr, wrong, 100)
            await asyncio.sleep(0.4)
            await self._keys(pt_, sr, code, 200)
            bye = await self._until(lambda: "c1" not in a.calls)
            pt_.close()
            # an external number without a waiting code is refused as before
            refused, *_ = await self._open(a, pbx, "01709999999", "c2")
            return st, bye, refused
        with _quiet() as log:
            st, bye, refused = self.run_with_pbx(body)
        self.assertEqual((st, bye, refused), (200, True, 603))
        nums = telefon_ich.view(self.uid)["nummern"]
        self.assertTrue(nums[0]["ok"])
        self.assertEqual(telefon_ich.owner_of("01701234567"), self.uid)
        self.assertIn("telefon: bestaetigungscode falsch", log.text)
        self.assertIn("telefon: nummer bestaetigt fuer Profil ", log.text)
        self.assertNotIn("0170", log.text)            # an external number never in the log
        self.assertNotIn(code, log.text)
        self.assertEqual([c["art"] for c in telefon_ich.calls(self.uid)], ["bestaetigung"])

    def test_the_pin_stands_for_the_voice_and_locks_after_three_wrong(self):
        self.setUp_t2()
        telefon_ich.set_pin(self.uid, "2580")
        self.say_next = ["Was steht heute im Kalender?"]
        sent = []

        async def fake_push(uid, title, body, **k):
            sent.append(uid)

        async def body(a, pbx, port):
            st, pt_, sr, to = await self._open(a, pbx, "**611", "p1")
            await asyncio.sleep(0.3)
            await self._keys(pt_, sr, "2580#", 300)
            call = a.calls.get("p1")
            unlocked = await self._until(lambda: call.pin_uid == self.uid)
            vr = await call.voice_result(None)
            pbx.t.sendto(ack_or_bye("BYE", "p1", a.port, 2), to)
            await self._until(lambda: "p1" not in a.calls)
            pt_.close()
            st2, pt2, sr2, to2 = await self._open(a, pbx, "**611", "p2")
            await asyncio.sleep(0.3)
            for i, k in enumerate(("1111#", "2222#", "3333#", "2580#")):
                await self._keys(pt2, sr2, k, 400 + 10 * i)
                await asyncio.sleep(0.5)
            call2 = a.calls.get("p2")
            await asyncio.sleep(0.5)
            locked = call2.pin_uid
            pbx.t.sendto(ack_or_bye("BYE", "p2", a.port, 2), to2)
            await self._until(lambda: "p2" not in a.calls)
            pt2.close()
            return unlocked, vr, locked
        with _quiet() as log, mock.patch("push.send", fake_push):
            unlocked, vr, locked = self.run_with_pbx(body)
        self.assertTrue(unlocked)
        self.assertEqual(vr, (self.uid, self.uid, ""))        # the PIN stands for the voice
        self.assertEqual(locked, "")                           # the right PIN after three wrong: still locked
        self.assertIn("telefon: pin richtig fuer Profil ", log.text)
        self.assertIn("telefon: pin gesperrt", log.text)
        self.assertEqual(sent, [self.uid])
        self.assertNotIn("2580", log.text)
        self.assertTrue(telefon_ich.locked("**611"))
        self.assertEqual({c["art"] for c in telefon_ich.calls(self.uid)}, {"intern"})


    def test_settings_follow_the_switches(self):
        helpers.set_config(telefon=False, telefon_gaeste=True, telefon_aussen=True)
        self.assertEqual({k: v for k, v in telefon.settings().items() if k in ("on", "gaeste", "aussen")},
                         {"on": False, "gaeste": False, "aussen": False})       # nothing without the main switch
        helpers.set_config(telefon=True, telefon_gaeste=True, telefon_aussen=False, telefon_max=5, telefon_ton="schmal")
        st = telefon.settings()
        self.assertEqual((st["on"], st["gaeste"], st["aussen"], st["max"], st["ton"]), (True, True, False, telefon.MAX_CALLS, "schmal"))
        helpers.set_config(telefon_ton="hd")

    # ------------------------------------------------------------ T3: calls from outside
    def test_calls_from_outside_known_number_guest_and_refused(self):
        self.setUp_t2()
        code = telefon_ich.add_number(self.uid, "0170 1234567")
        self.assertEqual(telefon_ich.try_code("01701234567", code)[0], "ok")
        helpers.set_config(telefon=True, telefon_gaeste=False, telefon_aussen=True, telefon_max=1, speaker_id=False,
                           deny={"telefon": [self.blocked]})
        self.addCleanup(lambda: helpers.set_config(telefon=False, telefon_aussen=False, telefon_gaeste=False, deny={}))
        helpers.TTS_TEXT.clear()

        async def hang(a, pbx, cid, pt_, to):
            pbx.t.sendto(ack_or_bye("BYE", cid, a.port, 2), to)
            await self._until(lambda: cid not in a.calls)
            pt_.close()

        async def body(a, pbx, port):
            out = {}
            st, pt_, sr, to = await self._open(a, pbx, "+491701234567", "o1")      # the confirmed number, international
            call = a.calls.get("o1")
            out["known"] = (st, call.mode, call.uid, call.shared)
            await asyncio.sleep(0.4)
            await hang(a, pbx, "o1", pt_, to)
            out["unknown_off"], *_ = await self._open(a, pbx, "01709999999", "o2")
            out["hidden_off"], *_ = await self._open(a, pbx, "anonymous", "o3")
            helpers.set_config(telefon=True, telefon_gaeste=True, telefon_aussen=True, telefon_max=1, speaker_id=False)
            st, pt_, sr, to = await self._open(a, pbx, "01709999999", "o4")
            call = a.calls.get("o4")
            out["guest"] = (st, call.mode, call.uid)
            await hang(a, pbx, "o4", pt_, to)
            with mock.patch.object(telefon, "GUESTS", 0):
                out["guest_full"], *_ = await self._open(a, pbx, "01708888888", "o5")
            helpers.set_config(telefon=True, telefon_gaeste=True, telefon_aussen=False, telefon_max=1, speaker_id=False)
            out["switch_off"], *_ = await self._open(a, pbx, "01701234567", "o6")
            return out
        with _quiet() as log:
            out = self.run_with_pbx(body)
        self.assertEqual(out["known"], (200, "extern", self.uid, False))
        self.assertEqual((out["unknown_off"], out["hidden_off"]), (603, 603))
        self.assertEqual(out["guest"], (200, "extern", ""))
        self.assertEqual((out["guest_full"], out["switch_off"]), (603, 603))
        self.assertIn("telefon: anruf extern bekannt als Profil ", log.text)
        self.assertIn("telefon: anruf extern unbekannt abgelehnt", log.text)
        self.assertIn("telefon: anruf extern unbekannt als gast", log.text)
        for nr in ("0170", "+49", "anonymous"):
            self.assertNotIn(nr, log.text)                        # an external number never in the log
        self.assertFalse(any("Tele Toni" in t for t in helpers.TTS_TEXT))   # a forged number learns no name
        self.assertIn("extern", {c["art"] for c in telefon_ich.calls(self.uid)})


class OwnNumbersAndPin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = profiles.add_user("Tele Anna", "4721")
        cls.b = profiles.add_user("Tele Bodo", "4722")

    def setUp(self):
        for u in (self.a, self.b):
            telefon_ich.clear(u)
        telefon_ich._fails.clear()
        telefon_ich._locked.clear()

    def test_numbers_in_one_form(self):
        self.assertEqual(telefon_ich.canon("0049 170 123-4567"), "+491701234567")
        self.assertEqual(telefon_ich.canon("0170/1234567"), "01701234567")
        self.assertEqual(telefon_ich.canon("12"), "")
        self.assertTrue(telefon_ich.same("01701234567", "+491701234567"))
        self.assertTrue(telefon_ich.same("+491701234567", "00491701234567"))
        self.assertFalse(telefon_ich.same("01701234567", "+491701234568"))
        self.assertFalse(telefon_ich.same("01701234567", "+4912341701234567"))   # more than a country code in front

    def test_a_number_belongs_to_one_profile_and_the_code_wears_out(self):
        code = telefon_ich.add_number(self.a, "01701234567", now=1000)
        telefon_ich.add_number(self.b, "+491701234567", now=1000)       # both may wait …
        with self.assertRaises(ValueError):
            telefon_ich.add_number(self.a, "**611")                      # internal ones: the admin
        self.assertEqual(telefon_ich.try_code("01701234567", "0000" if code != "0000" else "1111", now=1001)[0], "wrong")
        self.assertEqual(telefon_ich.try_code("01701234567", code, now=1002), ("ok", self.a))
        self.assertEqual(telefon_ich.numbers(self.b), [])                # … only the first right code wins
        with self.assertRaises(ValueError):
            telefon_ich.add_number(self.b, "01701234567")
        # a code counts CODE_SECONDS and CODE_TRIES times
        c2 = telefon_ich.add_number(self.a, "030 1234567", now=2000)
        self.assertEqual(telefon_ich.try_code("0301234567", c2, now=2000 + telefon_ich.CODE_SECONDS + 1)[0], "none")
        telefon_ich.add_number(self.a, "030 1234567", now=3000)
        res = [telefon_ich.try_code("0301234567", "99999", now=3001)[0] for _ in range(telefon_ich.CODE_TRIES)]
        self.assertEqual(res[-1], "void")
        self.assertEqual(telefon_ich.try_code("0301234567", c2, now=3002)[0], "none")
        with open(telefon_ich._file(self.a)) as f:
            raw = f.read()
        self.assertNotIn("1701234567", raw)                              # numbers and codes sealed
        for _ in range(3):
            telefon_ich.add_number(self.a, f"0171{random.randint(1000000, 9999999)}")
        with self.assertRaises(ValueError):
            telefon_ich.add_number(self.a, "0172 7654321")                # at most MAX_NUMBERS

    def test_pin_rules_lock_and_shared_phones(self):
        for bad in ("123", "123456789", "1111", "1234", "4321", "12a4"):
            with self.assertRaises(ValueError, msg=bad):
                telefon_ich.set_pin(self.a, bad)
        self.assertTrue(telefon_ich.set_pin(self.a, "2580"))
        telefon_ich.set_pin(self.b, "7391")
        with open(telefon_ich._file(self.a)) as f:
            self.assertNotIn("2580", f.read())
        both = [self.a, self.b]
        self.assertEqual(telefon_ich.pin_attempt("**612", both, "7391", now=10), ("ok", self.b))   # a shared phone
        self.assertEqual(telefon_ich.pin_attempt("**611", [self.a], "7391", now=10), ("wrong", ""))  # not this handset's
        self.assertEqual(telefon_ich.pin_attempt("**611", [self.a], "0000", now=11), ("wrong", ""))
        self.assertEqual(telefon_ich.pin_attempt("**611", [self.a], "0001", now=12), ("locked", "neu"))
        self.assertEqual(telefon_ich.pin_attempt("**611", [self.a], "2580", now=13), ("locked", ""))
        self.assertEqual(telefon_ich.pin_attempt("**611", [self.a], "2580", now=13 + telefon_ich.LOCK), ("ok", self.a))
        self.assertEqual(telefon_ich.pin_attempt("**612", [], "2580"), ("none", ""))
        self.assertFalse(any("611" in k for k in telefon_ich._fails))    # counters hold no number
        telefon_ich.set_pin(self.a, "")
        self.assertFalse(telefon_ich.has_pin(self.a))

    def test_calls_kept_and_deleted_and_own_data(self):
        for i in range(telefon_ich.KEEP_CALLS + 3):
            telefon_ich.keep_call(self.a, 100 + i, 30, 2, "intern")
        rows = telefon_ich.calls(self.a)
        self.assertEqual(len(rows), telefon_ich.KEEP_CALLS)
        self.assertEqual(set(rows[0]), {"id", "t", "s", "fragen", "art"})    # no number, no words
        telefon_ich.drop_calls(self.a, rows[0]["id"])
        self.assertEqual(len(telefon_ich.calls(self.a)), telefon_ich.KEEP_CALLS - 1)
        count, clear = __import__("features").OWN["telefon"]
        self.assertEqual(count(self.a), telefon_ich.KEEP_CALLS - 1)
        clear(self.a)
        self.assertEqual(count(self.a), 0)


class _quiet:
    """Collects what the module prints (the journal lines)."""

    def __enter__(self):
        import contextlib
        import io
        self.buf = io.StringIO()
        self.cm = contextlib.redirect_stdout(self.buf)
        self.cm.__enter__()
        return self

    def __exit__(self, *a):
        self.cm.__exit__(*a)
        self.text = self.buf.getvalue()


class Endpoints(unittest.TestCase):
    def test_admin_only_and_numbers_checked(self):
        from fastapi.testclient import TestClient
        import panel
        c = TestClient(panel.app)
        self.assertEqual(c.get("/api/admin/telefon").status_code, 401)
        h = {"Authorization": "Basic " + __import__("base64").b64encode(b"admin:secret-admin").decode()}
        r = c.get("/api/admin/telefon", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(a["id"] == "fritzbox" for a in r.json()["anlagen"]))
        self.assertFalse(r.json()["zugang"]["pw"])
        with mock.patch.object(telefon, "zugang", lambda: {"anlage": "fritzbox"}):
            bad = c.put("/api/admin/telefon/nummern", headers=dict(h, **{"Content-Type": "application/json"}),
                        content=json.dumps({"nr": "01701234567", "uid": ""}))
        self.assertEqual(bad.status_code, 400)

    def test_ich_telefon_own_browser_only(self):
        from fastapi.testclient import TestClient
        import panel
        admin = TestClient(panel.app)
        admin.headers["Authorization"] = "Basic " + __import__("base64").b64encode(b"admin:secret-admin").decode()
        self.assertIn(admin.post("/api/admin/profiles", json={"name": "Tele Emma", "pin": "4731"}).status_code, (200, 409))
        c = TestClient(panel.app)
        self.assertEqual(c.get("/api/profile/telefon").status_code, 401)
        self.assertEqual(c.post("/api/profile/login", json={"name": "Tele Emma", "pin": "4731"}).status_code, 200)
        helpers.set_config(telefon=False)
        self.assertEqual(c.post("/api/profile/telefon/nummern", json={"nr": "01701112222"}).status_code, 403)   # off
        helpers.set_config(telefon=True)
        self.addCleanup(lambda: helpers.set_config(telefon=False))
        r = c.post("/api/profile/telefon/nummern", json={"nr": "0170 1112222", "name": "Handy"})
        self.assertEqual(r.status_code, 200, r.text)
        row = r.json()["nummern"][0]
        self.assertFalse(row["ok"])
        self.assertRegex(row["code"], r"^\d{4}$")
        self.assertEqual(c.post("/api/profile/telefon/nummern", json={"nr": "abc"}).status_code, 400)
        self.assertEqual(c.put("/api/profile/telefon/pin", json={"pin": "1111"}).status_code, 400)
        r = c.put("/api/profile/telefon/pin", json={"pin": "8462"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["pin"])
        self.assertNotIn("8462", r.text + c.get("/api/profile/telefon").text)    # never sent back
        self.assertFalse(c.delete("/api/profile/telefon/pin").json()["pin"])
        self.assertEqual(c.delete("/api/profile/telefon/nummern/" + row["id"]).json()["nummern"], [])
        self.assertEqual(c.delete("/api/profile/telefon/nummern/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
