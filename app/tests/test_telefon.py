"""Telefon (telefon.py, telefon_ton.py, plan telefon-anruf.md T1): the sound codecs, the SIP parser and digest, and whole
calls against a PBX made up here (REGISTER with 401 and digest, INVITE with G.722 and G.711, RTP, DTMF, BYE). No telephone,
no clock: every wait is a few hundred milliseconds."""
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


if __name__ == "__main__":
    unittest.main()
