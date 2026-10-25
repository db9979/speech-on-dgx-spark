"""Anrufe (anrufe.py, plan plaene/messenger-d-v2.md): off until the admin switches them on, only in a chat of two on
this Spark, the rules of who may ring whom, one device per side, signals checked for form only, one line per call in
the chat, short-lived access to the Vermittler that never reaches the home network, and Live and journal with
numbers only."""
import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import anrufe  # noqa: E402
import chats  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
DEV_A, DEV_B, DEV_B2 = "a1" * 6, "b2" * 6, "c3" * 6
SDP = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\n"


def profile(name, pin="2468"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(client):
    return client.get("/api/whoami").json()["profile"]["id"]


def open_with(a, b):
    r = a.post("/api/chats/open", json={"to": uid_of(b)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


class Events:
    """What the Spark tells each profile's open Chats pages (chats._send_event), kept per profile."""
    def __init__(self, case):
        self.got = {}
        p = mock.patch.object(chats, "_send_event", side_effect=lambda uid, ev: self.got.setdefault(uid, []).append(ev))
        p.start()
        case.addCleanup(p.stop)

    def of(self, uid, kind):
        return [e for e in self.got.get(uid, []) if e.get("type") == kind]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(chats=True, chats_calls=True)
        anrufe._calls.clear()
        anrufe._started.clear()
        self.ev = Events(self)
        q = mock.patch.object(anrufe, "_quiet", return_value=False)   # no quiet hours: the tests never hang on the clock
        q.start()
        self.addCleanup(q.stop)
        p = mock.patch.object(anrufe, "_push", new=mock.AsyncMock())
        self.push = p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        helpers.set_config(chats=False, chats_calls=False, calls_turn=False, calls_turn_host="", chats_groups=False)
        anrufe._calls.clear()
        anrufe._started.clear()

    def call(self, a, cid, video=False, dev=DEV_A):
        return a.post("/api/anrufe/start", json={"id": cid, "video": video, "dev": dev})

    def lines(self, client, cid):
        return [x for x in client.get("/api/chats/items", params={"id": cid}).json()["items"] if x["kind"] == "sys"]


class Off(Base):
    def test_off_until_the_admin_switch_and_never_for_guests_or_device_keys(self):
        import features
        self.assertEqual(features.BY_KEY["anrufe"].parent, "chats")
        self.assertEqual(features.BY_KEY["anrufeturn"].parent, "anrufe")
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            c = json.load(f)["chat"]
        self.assertIs(c["chats_calls"], False)
        self.assertIs(c["calls_turn"], False)
        a, b = profile("Analma"), profile("Anbert")
        cid = open_with(a, b)
        helpers.set_config(chats_calls=False)
        self.assertEqual(self.call(a, cid).status_code, 403)
        self.assertEqual(a.get("/api/anrufe/ice").status_code, 403)
        self.assertFalse(a.get("/api/chats").json().get("calls"))
        helpers.set_config(chats_calls=True)
        self.assertTrue(a.get("/api/chats").json().get("calls"))
        g = TestClient(panel.app)
        self.assertIn(g.post("/api/anrufe/start", json={"id": cid, "dev": DEV_A}).status_code, (401, 403))
        # a device key that is not the iPhone app (a speaker, a watch, a terminal) never calls
        token = profiles.add_device("Antestbox", uid_of(a))
        did = next(x["id"] for x in profiles._load()["devices"] if x["name"] == "Antestbox")
        self.addCleanup(profiles.delete_device, did)
        k = TestClient(panel.app)
        self.assertIn(k.get("/api/anrufe/ice", headers={profiles.DEVICE_HEADER: token}).status_code, (401, 403))
        # the iPhone app's key only while the admin has the iPhone app on (profiles.APP_GATE)
        token = profiles.add_device("Antestapp", uid_of(a), scope="app")
        did = next(x["id"] for x in profiles._load()["devices"] if x["name"] == "Antestapp")
        self.addCleanup(profiles.delete_device, did)
        helpers.set_config(iphone=False)
        self.assertIn(k.get("/api/anrufe/ice", headers={profiles.DEVICE_HEADER: token}).status_code, (401, 403, 503))

    def test_the_admin_blocks_one_profile_and_switching_off_ends_running_calls(self):
        a, b = profile("Ancarl"), profile("Andora")
        cid = open_with(a, b)
        r = ADMIN.put(f"/api/admin/features/anrufe/profiles/{uid_of(b)}", json={"on": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.addCleanup(ADMIN.put, f"/api/admin/features/anrufe/profiles/{uid_of(b)}", json={"on": True})
        r = self.call(a, cid)
        self.assertEqual(r.status_code, 403)
        self.assertIn("nimmt gerade keine Anrufe", r.text)
        ADMIN.put(f"/api/admin/features/anrufe/profiles/{uid_of(b)}", json={"on": True})
        self.assertEqual(self.call(a, cid).json()["state"], "ring")
        self.assertEqual(anrufe.tidy(), [])
        helpers.set_config(chats_calls=False)
        self.assertEqual(len(anrufe.tidy()), 1)


class Ringing(Base):
    def test_ring_answer_on_one_device_signal_and_hang_up_leaves_one_line(self):
        a, b = profile("Anemil"), profile("Anfrida")
        ua, ub = uid_of(a), uid_of(b)
        cid = open_with(a, b)
        r = self.call(a, cid, video=True)
        self.assertEqual(r.status_code, 200, r.text)
        call = r.json()["call"]
        self.assertEqual(r.json()["state"], "ring")
        ring = self.ev.of(ub, "call")[0]
        self.assertEqual((ring["call"], ring["id"], ring["video"], ring["name"]), (call, cid, True, "Anemil"))
        self.push.assert_awaited_once()                     # nobody had the page open: the phone hears of it
        # only the called person answers, and only once
        self.assertEqual(a.post("/api/anrufe/answer", json={"call": call, "dev": DEV_A}).status_code, 404)
        self.assertEqual(b.post("/api/anrufe/answer", json={"call": call, "dev": DEV_B}).status_code, 200)
        self.assertEqual(b.post("/api/anrufe/answer", json={"call": call, "dev": DEV_B2}).status_code, 404)
        self.assertEqual(self.ev.of(ua, "call_ok")[0]["dev"], DEV_B)
        self.assertEqual(self.ev.of(ub, "call_taken")[0]["dev"], DEV_B)   # the other devices stop ringing
        # signals go to the one device on the other side, only from the two devices of the call
        offer = {"sdp": {"type": "offer", "sdp": SDP}}
        self.assertEqual(a.post("/api/anrufe/signal", json={"call": call, "dev": DEV_A, "data": offer}).status_code, 200)
        sig = self.ev.of(ub, "call_sig")[0]
        self.assertEqual((sig["to"], sig["data"]), (DEV_B, offer))
        self.assertEqual(b.post("/api/anrufe/signal", json={"call": call, "dev": DEV_B2, "data": offer}).status_code, 403)
        ice = {"ice": {"candidate": "candidate:1 1 udp 1 192.0.2.1 5000 typ host", "sdpMid": "0", "sdpMLineIndex": 0}}
        self.assertEqual(b.post("/api/anrufe/signal", json={"call": call, "dev": DEV_B, "data": ice}).status_code, 200)
        self.assertEqual(self.ev.of(ua, "call_sig")[0]["to"], DEV_A)
        c = profile("Angustav")
        self.assertEqual(c.post("/api/anrufe/signal", json={"call": call, "dev": DEV_A, "data": offer}).status_code, 404)
        self.assertEqual(c.post("/api/anrufe/end", json={"call": call, "dev": DEV_A}).status_code, 404)
        self.assertEqual(b.post("/api/anrufe/end", json={"call": call, "dev": DEV_B}).json()["line"], "call")
        self.assertEqual(len(self.ev.of(ua, "call_end")), 1)
        line = self.lines(a, cid)[-1]
        self.assertEqual((line["sys"], line["video"]), ("call", True))
        self.assertIsInstance(line["secs"], int)
        self.assertEqual(b.post("/api/anrufe/end", json={"call": call, "dev": DEV_B}).status_code, 404)

    def test_rejected_missed_and_caller_hung_up(self):
        a, b = profile("Anhanna"), profile("Anigor")
        cid = open_with(a, b)
        call = self.call(a, cid).json()["call"]
        self.assertEqual(b.post("/api/anrufe/end", json={"call": call, "dev": DEV_B, "why": "reject"}).json()["line"], "call_rejected")
        call = self.call(a, cid).json()["call"]
        self.assertEqual(a.post("/api/anrufe/end", json={"call": call, "dev": DEV_A}).json()["line"], "call_missed")
        call = self.call(a, cid).json()["call"]
        self.assertEqual(asyncio.run(anrufe.end(uid_of(b), call, "missed")), "call_missed")
        self.assertEqual([x["sys"] for x in self.lines(b, cid)][-3:], ["call_rejected", "call_missed", "call_missed"])

    def test_busy_quiet_hours_and_one_call_at_a_time(self):
        a, b, c = profile("Anjana"), profile("Ankurt"), profile("Anlena")
        ab, cb = open_with(a, b), open_with(c, b)
        self.assertEqual(self.call(a, ab).json()["state"], "ring")
        self.assertEqual(self.call(a, ab).status_code, 400)          # the caller is on a call already
        self.assertEqual(self.call(c, cb).json()["state"], "busy")    # b is: busy, a missed line, no ringing
        self.assertEqual(len(self.ev.of(uid_of(b), "call")), 1)
        anrufe._calls.clear()
        with mock.patch.object(anrufe, "_quiet", return_value=True):
            self.assertEqual(self.call(c, cb).json()["state"], "missed")
        self.assertEqual(len(self.ev.of(uid_of(b), "call")), 1)

    def test_only_in_a_chat_of_two_and_only_who_takes_messages_from_the_caller(self):
        a, b, c = profile("Anmarc"), profile("Annora"), profile("Anotto")
        helpers.set_config(chats_groups=True)
        g = a.post("/api/chats/group", json={"name": "Drei", "members": [uid_of(b), uid_of(c)]}).json()["id"]
        r = self.call(a, g)
        self.assertEqual(r.status_code, 400)
        self.assertIn("zu zweit", r.text)
        cid = open_with(a, b)
        b.put("/api/profile/settings", json={"msg_from": "chosen"})
        self.addCleanup(b.put, "/api/profile/settings", json={"msg_from": "all"})
        self.assertEqual(self.call(a, cid).status_code, 403)
        self.assertEqual(self.ev.of(uid_of(b), "call"), [])
        self.assertEqual(self.call(a, "c" + "0" * 12).status_code, 404)   # no such chat

    def test_at_most_per_hour(self):
        a, b = profile("Anpia"), profile("Anquirin")
        cid = open_with(a, b)
        for _ in range(anrufe.PER_HOUR):
            call = self.call(a, cid).json()["call"]
            a.post("/api/anrufe/end", json={"call": call, "dev": DEV_A})
        self.assertEqual(self.call(a, cid).status_code, 429)

    def test_signals_checked_for_form_and_size(self):
        bad = [None, {}, {"sdp": {"type": "offer", "sdp": "x"}}, {"sdp": {"type": "pranswer", "sdp": SDP}},
               {"sdp": {"type": "offer", "sdp": SDP, "x": 1}}, {"sdp": {"type": "offer", "sdp": "v=0" + "a" * anrufe.MAX_SIGNAL}},
               {"ice": {"candidate": "c", "evil": 1}}, {"ice": {"candidate": "c" * 2000}}, {"ice": {"sdpMLineIndex": 99}},
               {"sdp": {"type": "offer", "sdp": SDP}, "ice": {}}, {"cmd": "x"}]
        for d in bad:
            with self.assertRaises(ValueError, msg=repr(d)[:80]):
                anrufe._check_signal(d)
        self.assertEqual(anrufe._check_signal({"ice": {"candidate": ""}}), {"ice": {"candidate": ""}})
        a = profile("Anrosa")
        self.assertEqual(a.post("/api/anrufe/start", json={"id": "x", "dev": "nicht-hex"}).status_code, 400)
        self.assertEqual(a.post("/api/anrufe/signal", json={"call": "zz", "dev": DEV_A, "data": {}}).status_code, 400)


class Vermittler(Base):
    def test_short_lived_access_and_the_relay_never_reaches_home(self):
        import hashlib
        import hmac
        import base64
        a = profile("Ansven")
        self.assertEqual(a.get("/api/anrufe/ice").json()["servers"], [])   # at home only: no Vermittler
        helpers.set_config(calls_turn=True, calls_turn_host="")
        self.assertEqual(anrufe.ice(uid_of(a)), [])                       # no address from outside: nothing
        helpers.set_config(calls_turn_host="Spark.Example.de")
        s = anrufe.ice(uid_of(a), now=1000)
        turn = s[1]
        self.assertEqual(turn["urls"][0], "turn:spark.example.de:3478?transport=udp")
        exp, who = turn["username"].split(":")
        self.assertEqual(int(exp), 1000 + anrufe.CRED_SECS)
        self.assertNotIn(uid_of(a), turn["username"])
        want = base64.b64encode(hmac.new(anrufe._secret().encode(), turn["username"].encode(), hashlib.sha1).digest()).decode()
        self.assertEqual(turn["credential"], want)
        import ipaddress
        with mock.patch.object(anrufe, "_own", return_value={ipaddress.ip_address("2001:db8::5")}):
            conf = anrufe.turn_conf("spark.example.de", "198.51.100.7", "/tmp/x")
        self.assertIn("denied-peer-ip=2001:db8::5\n", conf)               # the Spark's own public addresses
        self.assertIn("denied-peer-ip=198.51.100.7\n", conf)
        for need in ("use-auth-secret", "no-cli", "no-tls", "no-multicast-peers", "no-tcp-relay", "no-stdout-log",
                     "denied-peer-ip=192.168.0.0-192.168.255.255", "denied-peer-ip=10.0.0.0-10.255.255.255",
                     "denied-peer-ip=127.0.0.0-127.255.255.255", "denied-peer-ip=172.16.0.0-172.31.255.255",
                     "denied-peer-ip=fc00::-fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", "min-port=49160", "max-port=49200"):
            self.assertIn(need + "\n", conf)
        self.assertNotIn("lt-cred-mech", conf)
        self.assertNotIn("user=", conf)

    def test_the_unit_follows_the_switch(self):
        with mock.patch.object(anrufe, "_systemctl", return_value=True) as sc, \
                mock.patch.object(anrufe, "_installed", return_value=True), \
                mock.patch.object(anrufe, "_state_dir", return_value=tempfile.mkdtemp()), \
                mock.patch.object(anrufe, "outside_ip", return_value=("203.0.113.9", "")):
            self.assertEqual(anrufe.apply_turn(), "off")
            sc.assert_not_called()
            helpers.set_config(calls_turn=True, calls_turn_host="spark.example.de")
            self.assertEqual(anrufe.apply_turn(), "on")
            sc.assert_called_with("restart")
            path = os.path.join(anrufe._state_dir(), "turn.conf")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            sc.reset_mock()
            with mock.patch.object(anrufe, "_active", return_value=True):
                self.assertEqual(anrufe.apply_turn(), "on")
            sc.assert_not_called()                                         # nothing changed: no restart
            helpers.set_config(calls_turn=False)
            self.assertEqual(anrufe.apply_turn(), "off")
            sc.assert_called_with("stop")
            self.assertFalse(os.path.exists(path))

    def test_outside_address_only_public_ipv4(self):
        def gai(addrs):
            return lambda *a, **k: [(2, 2, 17, "", (x, 3478)) for x in addrs]
        with mock.patch("socket.getaddrinfo", gai(["192.168.178.20", "93.184.216.34"])):
            self.assertEqual(anrufe.outside_ip("spark.example.de"), ("93.184.216.34", ""))
        with mock.patch("socket.getaddrinfo", gai(["192.168.178.20"])):
            self.assertEqual(anrufe.outside_ip("spark.example.de"), ("", "home address"))
        with mock.patch("socket.getaddrinfo", side_effect=OSError("no")):
            self.assertEqual(anrufe.outside_ip("spark.example.de"), ("", "not found"))
        with mock.patch("socket.getaddrinfo") as g:   # IPv4 only: a home-only IPv6 record never stops the relay
            g.return_value = []
            anrufe.outside_ip("spark.example.de")
            self.assertEqual(g.call_args[0][2], __import__("socket").AF_INET)

    def test_refused_logs_once_per_reason_and_a_running_relay_keeps_its_address(self):
        state = tempfile.mkdtemp()
        with mock.patch.object(anrufe, "_systemctl", return_value=True), \
                mock.patch.object(anrufe, "_installed", return_value=True), \
                mock.patch.object(anrufe, "_state_dir", return_value=state), \
                mock.patch.object(anrufe, "_active", return_value=False), \
                mock.patch.object(anrufe, "outside_ip", return_value=("", "home address")):
            helpers.set_config(calls_turn=True, calls_turn_host="spark.example.de")
            anrufe._turn.update(conf="", ip="", on=False, why="")
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    for _ in range(3):   # every minute: one line, not three
                        self.assertEqual(anrufe.apply_turn(), "noip")
            finally:
                helpers.set_config(calls_turn=False)
            self.assertEqual(out.getvalue().count("chats: call relay refused | why home address"), 1)
            self.assertEqual(anrufe._turn["why"], "Adresse von außen zeigt ins Heimnetz")
            self.assertFalse(anrufe.relay_ok())
        with open(os.path.join(state, "turn.conf"), "w") as f:   # written before the panel restarted
            f.write("listening-port=3478\nexternal-ip=93.184.216.34\n")
        with mock.patch.object(anrufe, "_systemctl", return_value=True) as sc, \
                mock.patch.object(anrufe, "_installed", return_value=True), \
                mock.patch.object(anrufe, "_state_dir", return_value=state), \
                mock.patch.object(anrufe, "_active", return_value=True), \
                mock.patch.object(anrufe, "outside_ip", return_value=("", "not found")):
            helpers.set_config(calls_turn=True, calls_turn_host="spark.example.de")
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    self.assertEqual(anrufe.apply_turn(), "on")
                    self.assertTrue(anrufe.relay_ok())
                    self.assertEqual(anrufe._turn["ip"], "93.184.216.34")
            finally:
                helpers.set_config(calls_turn=False)
                with contextlib.redirect_stdout(io.StringIO()):
                    anrufe.apply_turn()
            self.assertIn("chats: call relay kept | why not found", out.getvalue())
            sc.assert_any_call("stop")                       # switched off at the end: the unit stops

    def test_without_coturn_nothing_starts_and_the_reason_shows(self):
        with mock.patch.object(anrufe, "_systemctl", return_value=True) as sc, \
                mock.patch.object(anrufe, "_installed", return_value=False), \
                mock.patch.object(anrufe, "_state_dir", return_value=tempfile.mkdtemp()):
            helpers.set_config(calls_turn=True, calls_turn_host="spark.example.de")
            try:
                self.assertEqual(anrufe.apply_turn(), "missing")
            finally:
                helpers.set_config(calls_turn=False)
            sc.assert_not_called()
            self.assertEqual(anrufe._turn["why"], "coturn fehlt")
            self.assertFalse(anrufe.relay_ok())
            anrufe.apply_turn()
        ins = helpers.repo_file("install.sh")
        self.assertIn("ConditionPathExists=/usr/bin/turnserver", ins)   # no restart loop without the program
        self.assertIn("RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK", ins)   # coturn reads its addresses

    def test_installed_as_its_own_unit_and_the_distribution_service_never_runs(self):
        ins = helpers.repo_file("install.sh")
        self.assertIn("systemctl mask --now coturn.service", ins)   # stopped too when it already ran
        self.assertIn("speech-spark-turn.service", ins)
        self.assertRegex(ins, r"for u in [^;\n]*\bturn\b[^;\n]*; do")              # sudoers: start/stop/restart only
        self.assertNotIn("enable speech-spark-turn", ins)


class Visible(Base):
    def test_live_and_journal_numbers_only(self):
        a, b = profile("Antilda"), profile("Anulf")
        cid = open_with(a, b)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            call = self.call(a, cid).json()["call"]
            b.post("/api/anrufe/answer", json={"call": call, "dev": DEV_B})
            a.post("/api/anrufe/signal", json={"call": call, "dev": DEV_A, "data": {"sdp": {"type": "offer", "sdp": SDP}}})
            a.post("/api/anrufe/end", json={"call": call, "dev": DEV_A})
        log = out.getvalue()
        for w in ("chats: call started", "chats: call answered", "chats: call ended"):
            self.assertIn(w, log)
        for never in ("Antilda", "Anulf", uid_of(a), cid, call, "127.0.0.1", "v=0"):
            self.assertNotIn(never, log)
        lv = anrufe.for_live()
        self.assertTrue(lv["on"])
        self.assertGreaterEqual(lv["today"], 1)
        self.assertNotIn("Antilda", json.dumps(lv))

    def test_running_calls_show_as_connections_in_live_monitoring_and_the_steuerzentrale(self):
        import live
        import time
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        before = dict(c.get("logs") or {})
        c.setdefault("logs", {})["live"] = True
        helpers.write_config(c)

        def back():
            with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
                c = json.load(f)
            c["logs"] = before
            helpers.write_config(c)
        self.addCleanup(back)
        a, b = profile("Anwalda"), profile("Anrolf")
        cid = open_with(a, b)
        with contextlib.redirect_stdout(io.StringIO()):
            call = self.call(a, cid).json()["call"]
            rec = anrufe._calls[call]["rec"]     # under Geräte like a request, from ringing to the end
            self.assertIsNotNone(rec)
            self.assertEqual((rec.intent, rec.done), ("Anruf · klingelt", False))
            self.assertIn(rec, live._run.values())
            row = live._req(rec, "monitor", time.time())
            self.assertEqual((row["dev"], row["who"]), ("Browser ↔ …", "Person ↔ Person"))   # no names without consent
            n = {c["name"]: c["n"] for c in live._conns(time.time())}
            self.assertEqual((n.get("Anruf klingelt"), n.get("Anruf im Chat")), (1, None))
            b.post("/api/anrufe/answer", json={"call": call, "dev": DEV_B})
            self.assertEqual(rec.intent, "Anruf · verbunden")
            self.assertEqual(live._req(rec, "admin", time.time())["dev"], "Browser ↔ Browser")
            for u in (a, b):     # with both people's consent both names show, still never the chat
                profiles.save_settings(uid_of(u), {"trace_name": True})
            row = live._req(rec, "admin", time.time())
            self.assertEqual(row["who"], "Anwalda ↔ Anrolf", row)
            self.assertNotIn(cid, json.dumps(row))
            rows = [c for c in live._conns(time.time()) if c["name"].startswith("Anruf")]
            self.assertEqual([(c["name"], c["n"]) for c in rows], [("Anruf im Chat", 1)])
            self.assertNotIn("Anwalda", json.dumps(rows))
            a.post("/api/anrufe/end", json={"call": call, "dev": DEV_A})
        self.assertTrue(rec.done)
        self.assertFalse([c for c in live._conns(time.time()) if c["name"].startswith("Anruf")])


if __name__ == "__main__":
    unittest.main()


class IPhone(Base):
    """The iPhone app (V01.0.652): its own key calls and answers like a browser, its iPhones ring over VoIP push with
    nothing but the call's id, and it asks the Spark who calls (info, only for the two people of the call)."""
    def setUp(self):
        super().setUp()
        helpers.set_config(iphone=True)
        self.voip = mock.patch("apns.send_voip", new=mock.AsyncMock(return_value=1)).start()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self):
        helpers.set_config(iphone=False)
        super().tearDown()

    def app(self, client, name):
        token = profiles.add_device(name, uid_of(client), scope="app")
        did = next(x["id"] for x in profiles._load()["devices"] if x["name"] == name)
        self.addCleanup(profiles.delete_device, did)
        k = TestClient(panel.app)
        k.headers[profiles.DEVICE_HEADER] = token
        return k

    def test_the_app_calls_answers_and_learns_who_calls(self):
        a, b = profile("Anifa"), profile("Anibo")
        cid = open_with(a, b)
        pa, pb = self.app(a, "Anifa iPhone"), self.app(b, "Anibo iPhone")
        self.assertEqual(pa.get("/api/anrufe/ice").status_code, 200)
        r = pa.post("/api/anrufe/start", json={"id": cid, "video": True, "dev": DEV_A})
        self.assertEqual(r.status_code, 200, r.text)
        call = r.json()["call"]
        # the other person's iPhones ring over VoIP with the call's id only
        self.voip.assert_awaited_once_with(uid_of(b), call)
        info = pb.get("/api/anrufe/info", params={"call": call}).json()
        self.assertEqual((info["id"], info["video"], info["state"], info["mine"], info["name"]), (cid, True, "ring", False, "Anifa"))
        self.assertEqual(pa.get("/api/anrufe/info", params={"call": call}).json()["mine"], True)
        # a third person learns nothing about the call
        c = self.app(profile("Anicus"), "Anicus iPhone")
        self.assertEqual(c.get("/api/anrufe/info", params={"call": call}).json(), {"call": call, "state": "end"})
        self.assertEqual(pb.get("/api/anrufe/info", params={"call": "x"}).status_code, 400)
        self.assertEqual(pb.post("/api/anrufe/answer", json={"call": call, "dev": DEV_B}).status_code, 200)
        self.assertEqual(pb.post("/api/anrufe/signal", json={"call": call, "dev": DEV_B,
                                                            "data": {"sdp": {"type": "answer", "sdp": SDP}}}).status_code, 200)
        self.assertEqual(pb.post("/api/anrufe/end", json={"call": call, "dev": DEV_B}).status_code, 200)
        # a late VoIP push still finds out the call is over
        self.assertEqual(pb.get("/api/anrufe/info", params={"call": call}).json()["state"], "end")

    def test_the_app_key_reaches_nothing_else_of_a_call_without_the_iphone_app(self):
        a, b = profile("Anigo"), profile("Anihu")
        cid = open_with(a, b)
        pa = self.app(a, "Anigo iPhone")
        helpers.set_config(iphone=False)
        self.assertIn(pa.post("/api/anrufe/start", json={"id": cid, "dev": DEV_A}).status_code, (401, 403, 503))
        self.voip.assert_not_awaited()

