"""Notaus (notaus.py, plan plaene/notaus.md): three stages, triggering only goes up, lifting only by the admin in a
browser at home with a fresh code (or the password without a second step), never from an app key, from outside,
by the model or by text. Each stage really holds its things off: requests from outside, connections to the
internet, actions and their last line of defence, jobs, conversation. No test depends on the time of day."""
import asyncio
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import agent  # noqa: E402
import chat  # noqa: E402
import homeassistant  # noqa: E402
import messages  # noqa: E402
import netguard  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

HOME = ("192.168.178.20", 50000)
OUTSIDE = ("93.184.216.34", 50000)


def client(where=HOME):
    return TestClient(panel.app, client=where)


def admin(where=HOME):
    c = client(where)
    assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    return c


def profile(name, pin="1234"):
    a = admin()
    r = a.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = client()
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


def request(peer, headers=None, path="/api/chat", method="POST"):
    return Request({"type": "http", "method": method, "path": path, "query_string": b"",
                    "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()], "client": (peer, 1)})


def set_panel(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c["panel"].update(kw)
    with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
        json.dump(c, f)


def off():
    try:
        os.remove(notaus.FILE)
    except FileNotFoundError:
        pass
    notaus._cache.update(key=None, state=None)


class Base(unittest.TestCase):
    def setUp(self):
        off()
        set_panel(notaus_profiles=False, trusted_proxies=[])

    def tearDown(self):
        off()
        set_panel(notaus_profiles=False, trusted_proxies=[])


class State(Base):
    def test_only_up_and_survives_rereading(self):
        old, s = notaus.trigger(2, "Anna", "u_1", "panel", "  komisch\n Mail ", now=1000)
        self.assertEqual((old, s["level"], s["since"], s["reason"]), (0, 2, 1000, "komisch Mail"))
        old, s = notaus.trigger(1, "Bert", "", "panel", now=1100)      # never down this way
        self.assertEqual((old, s["level"], s["by"]), (2, 2, "Anna"))
        notaus._cache.update(key=None, state=None)                       # like a restart: read from the file
        self.assertEqual(notaus.level(), 2)
        old, s = notaus.trigger(3, "Bert", "", "app", now=1200)
        self.assertEqual((old, s["level"], s["since"], s["channel"]), (2, 3, 1000, "app"))
        with self.assertRaises(ValueError):
            notaus.lift(3, "Admin")
        notaus.lift(1, "Admin", now=1300)
        self.assertEqual(notaus.level(), 1)
        notaus.lift(0, "Admin", now=1400)
        self.assertEqual(notaus.level(), 0)
        self.assertEqual(len(notaus.state()["history"]), 4)

    def test_a_damaged_file_never_switches_it_off(self):
        os.makedirs(notaus.STATE, exist_ok=True)
        for raw in ("{", '{"level": "0"}', '{"level": 7}', "[]"):
            with open(notaus.FILE, "w") as f:
                f.write(raw)
            notaus._cache.update(key=None, state=None)
            self.assertEqual(notaus.level(), 3, raw)

    def test_reason_and_channel_are_checked(self):
        with self.assertRaises(ValueError):
            notaus.trigger(2, "x", "", "model")
        with self.assertRaises(ValueError):
            notaus.trigger(4, "x", "", "panel")
        _, s = notaus.trigger(1, "x", "", "panel", "a" * 500 + "\x00\x1b")
        self.assertEqual(len(s["reason"]), notaus.MAX_REASON)


class Where(Base):
    def test_home_and_outside(self):
        self.assertTrue(notaus.at_home(request("192.168.178.20")))
        self.assertTrue(notaus.at_home(request("127.0.0.1")))
        self.assertFalse(notaus.at_home(request("93.184.216.34")))
        # a reverse proxy on this host: the browser behind it decides
        self.assertTrue(notaus.at_home(request("127.0.0.1", {"x-forwarded-for": "192.168.178.30"})))
        self.assertFalse(notaus.at_home(request("127.0.0.1", {"x-forwarded-for": "93.184.216.34"})))
        # forwarding headers from a device nobody listed: outside (they could claim anything)
        self.assertFalse(notaus.at_home(request("192.168.178.40", {"x-forwarded-for": "192.168.178.30"})))
        self.assertFalse(notaus.at_home(request("192.168.178.40", {"x-real-ip": "192.168.178.30"})))
        # a listed proxy without a home address behind it counts as outside, also without headers
        set_panel(trusted_proxies=["192.168.178.40"])
        self.assertFalse(notaus.at_home(request("192.168.178.40")))
        self.assertFalse(notaus.at_home(request("192.168.178.40", {"x-forwarded-for": "8.8.8.8"})))
        self.assertTrue(notaus.at_home(request("192.168.178.40", {"x-forwarded-for": "192.168.178.30"})))

    def test_gate_by_stage(self):
        self.assertIsNone(notaus.gate(request("93.184.216.34")))
        notaus.trigger(1, "x", "", "panel")
        self.assertEqual(notaus.gate(request("93.184.216.34"))[0], 503)
        self.assertEqual(notaus.gate(request("93.184.216.34", path="/mcp"))[0], 503)
        self.assertIsNone(notaus.gate(request("93.184.216.34", path="/api/notaus")))
        self.assertIsNone(notaus.gate(request("93.184.216.34", path="/static/js/base.js", method="GET")))
        self.assertIsNone(notaus.gate(request("192.168.178.20")))        # at home stage 1 changes nothing
        notaus.trigger(3, "x", "", "panel")
        self.assertEqual(notaus.gate(request("192.168.178.20"))[0], 503)
        self.assertEqual(notaus.gate(request("192.168.178.20", path="/api/test/asr"))[0], 503)
        self.assertIsNone(notaus.gate(request("192.168.178.20", path="/api/login")))
        self.assertIsNone(notaus.gate(request("192.168.178.20", path="/api/admin/notaus/off")))
        self.assertIsNone(notaus.gate(request("192.168.178.20", path="/api/audit", method="GET")))
        self.assertEqual(notaus.gate(request("192.168.178.20", path="/api/audit", method="POST"))[0], 503)
        self.assertGreaterEqual(notaus.counts()["gespraech"], 2)

    def test_the_live_view_shows_the_stage_without_content(self):
        import live
        self.assertEqual(live.snapshot()["notaus"]["level"], 0)
        notaus.trigger(3, "Merle", "u_1", "panel", reason="geheimer Grund")
        snap = live.snapshot()
        n = snap["notaus"]
        self.assertEqual((n["level"], n["channel"]), (3, "panel"))
        self.assertEqual({k["k"] for k in n["kinds"]}, set(notaus.STAGE))
        text = json.dumps(snap, ensure_ascii=False)
        self.assertNotIn("geheimer Grund", text)                       # never the reason
        self.assertNotIn("Merle", text)                                # nor who
        self.assertTrue(any(e["area"] == "Notaus" for e in snap["events"]))
        for path in ("/live", "/api/live/state", "/api/admin/live"):   # the monitor keeps watching in stage 3
            self.assertIsNone(notaus.gate(request("192.168.178.20", path=path, method="GET")))
        self.assertEqual(notaus.gate(request("192.168.178.20", path="/api/live/pair"))[0], 503)


class Api(Base):
    def test_admin_triggers_and_lifts_at_home_with_password(self):
        a = admin()
        self.assertEqual(a.get("/api/whoami").json()["notaus_may"], True)
        r = a.post("/api/notaus", json={"level": 2, "reason": "Test"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["level"], r.json()["by"], r.json()["lift"]), (2, "Admin", "password"))
        self.assertEqual(a.post("/api/notaus", json={"level": 1}).status_code, 409)   # only up
        self.assertEqual(a.post("/api/admin/notaus/off", json={"to": 0, "password": "wrong"}).status_code, 401)
        self.assertEqual(notaus.level(), 2)
        r = a.post("/api/admin/notaus/off", json={"to": 0, "password": "secret-admin"})
        self.assertEqual((r.status_code, r.json()["level"]), (200, 0), r.text)

    def test_lifting_never_from_outside_an_app_or_a_profile(self):
        notaus.trigger(2, "x", "", "panel")
        out = admin(HOME)
        out = client(OUTSIDE)
        out.cookies = admin().cookies
        self.assertEqual(out.post("/api/admin/notaus/off", json={"to": 0, "password": "secret-admin"}).status_code, 503)
        self.assertEqual(out.get("/api/notaus").json()["outside"], True)
        p, _ = profile("Nora")
        self.assertEqual(p.post("/api/admin/notaus/off", json={"to": 0}).status_code, 403)
        # HTTP Basic (scripts) never lifts it
        basic = client()
        self.assertEqual(basic.post("/api/admin/notaus/off", json={"to": 0, "password": "secret-admin"},
                                    auth=("admin", "secret-admin")).status_code, 403)
        self.assertEqual(notaus.level(), 2)

    def test_profiles_only_when_the_admin_allows_it(self):
        p, uid = profile("Paula")
        self.assertEqual(p.get("/api/whoami").json()["notaus_may"], False)
        self.assertEqual(p.post("/api/notaus", json={"level": 2}).status_code, 403)
        self.assertEqual(client().post("/api/notaus", json={"level": 2}).status_code, 401)   # guests never
        set_panel(notaus_profiles=True)
        self.assertEqual(p.get("/api/whoami").json()["notaus_may"], True)
        r = p.post("/api/notaus", json={"level": 1})
        self.assertEqual((r.status_code, r.json()["level"], r.json()["lift"]), (200, 1, ""))
        self.assertEqual(p.post("/api/notaus", json={"level": "3"}).status_code, 400)
        # from outside it can still go up (the phone on the way), never down
        out = client(OUTSIDE)
        out.cookies = p.cookies
        self.assertEqual(out.post("/api/notaus", json={"level": 2}).json()["level"], 2)
        self.assertEqual(out.post("/api/admin/notaus/off", json={"to": 0}).status_code, 503)

    def test_strangers_see_only_the_stage(self):
        notaus.trigger(1, "Anna", "u_x", "panel", "geheim")
        d = client(OUTSIDE).get("/api/notaus").json()
        self.assertEqual(set(d), {"level", "outside"})

    def test_outside_gets_nothing_else_at_stage_one(self):
        a = admin(OUTSIDE)
        self.assertEqual(a.get("/api/status").status_code, 200)
        notaus.trigger(1, "x", "", "panel")
        self.assertEqual(a.get("/api/status").status_code, 503)
        self.assertEqual(a.get("/").status_code, 200)
        self.assertEqual(admin(HOME).get("/api/status").status_code, 200)


class Holds(Base):
    def test_no_internet_from_stage_one(self):
        self.assertIsNone(netguard.allowed("93.184.216.34", 443, netguard.PUBLIC))
        notaus.trigger(1, "x", "", "panel")
        self.assertIn("Notaus", netguard.allowed("93.184.216.34", 443, netguard.PUBLIC))
        self.assertIn("Notaus", netguard.allowed("93.184.216.34", 443, netguard.HOME))
        self.assertIsNone(netguard.allowed("192.168.178.5", 8123, netguard.HOME))   # Home Assistant at home goes on
        self.assertTrue({"web_search", "weather", "wikipedia"} <= notaus.locked_tools(1))
        self.assertNotIn("home_assistant", notaus.locked_tools(1))

    def test_actions_are_held_from_stage_two(self):
        notaus.trigger(2, "x", "", "panel")
        tools = notaus.locked_tools(2, {"message_send", "tasks_add"})
        self.assertTrue(chat.LOCKED_OUTSIDE <= tools)
        self.assertTrue({"message_send", "tasks_add", "mail_draft", "home_assistant_action"} <= tools)
        self.assertNotIn("document_search", tools)                          # reading what it knows goes on
        item = {"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN}
        before = len(helpers.HA_CALLS)
        with self.assertRaises(notaus.NotausAktiv):
            asyncio.run(homeassistant.command(item, "Licht an"))
        with self.assertRaises(notaus.NotausAktiv):
            asyncio.run(homeassistant.action(item, "light.kueche", "turn_on"))
        with self.assertRaises(notaus.NotausAktiv):
            asyncio.run(homeassistant.todo(item, "Einkauf", "add", "Milch"))
        self.assertEqual(len(helpers.HA_CALLS), before)
        names, why = asyncio.run(messages.send("u_x", ["u_y"], "Hallo"))
        self.assertEqual(names, [])
        self.assertIn("Notaus", why)
        job, why = agent.enqueue("u_x", "Such mir etwas")
        self.assertIsNone(job)
        self.assertIn("Notaus", why)
        self.assertGreaterEqual(notaus.counts()["aktion"], 4)

    def test_home_assistant_rules_are_held_from_stage_two(self):
        import hamelden
        import proactive
        got = []

        async def deliver(*a, **k):
            got.append("note")

        async def announce(*a, **k):
            got.append("loud")
            return [], ""
        old = proactive.deliver, messages.announce
        proactive.deliver, messages.announce = deliver, announce
        try:
            rule = {"conds": [], "text": "Es hat geklingelt.", "loud": True, "speakers": ["d_flur"]}
            notaus.trigger(2, "x", "", "panel")
            asyncio.run(hamelden.said("u_1", rule, "Es hat geklingelt.", "", {}))
            self.assertEqual(got, [])
            self.assertGreaterEqual(notaus.counts()["auto"], 1)
            hamelden._streams["u_1"] = hamelden.Stream("u_1", "fp")
            asyncio.run(hamelden.ensure())                      # no live connection to Home Assistant either
            self.assertEqual(hamelden._streams, {})
        finally:
            proactive.deliver, messages.announce = old
            hamelden._streams.clear()

    def test_the_model_is_not_offered_the_smart_home(self):
        a, _ = profile("Hanna")
        url = f"http://127.0.0.1:{helpers.HA_PORT}"
        self.assertEqual(a.put("/api/profile/homeassistant", json={"url": url, "token": helpers.HA_TOKEN}).status_code, 200)
        try:
            cmd = 'TOOL home_assistant {"command": "Licht in der Küche an"}'

            def said():
                r = a.post("/api/chat", json={"messages": [{"role": "user", "content": cmd}]})
                return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
            self.assertNotIn("NO TOOL home_assistant", said())
            notaus.trigger(2, "x", "", "panel")
            self.assertIn("NO TOOL home_assistant", said())
            notaus.trigger(3, "x", "", "panel")
            r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]})
            self.assertEqual(r.status_code, 503)
        finally:
            off()
            a.delete("/api/profile/homeassistant")


if __name__ == "__main__":
    unittest.main()
