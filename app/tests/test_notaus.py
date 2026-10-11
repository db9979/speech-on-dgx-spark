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
    for f in (notaus.FILE, notaus.MINE_FILE):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
    notaus._cache.update(key=None, state=None)
    notaus._mine_cache.update(key=None, d=None)


class Base(unittest.TestCase):
    def setUp(self):
        off()
        set_panel(trusted_proxies=[])

    def tearDown(self):
        off()
        set_panel(trusted_proxies=[])


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
        p, _ = profile("NxNora")
        self.assertEqual(p.post("/api/admin/notaus/off", json={"to": 0}).status_code, 403)
        # HTTP Basic (scripts) never lifts it
        basic = client()
        self.assertEqual(basic.post("/api/admin/notaus/off", json={"to": 0, "password": "secret-admin"},
                                    auth=("admin", "secret-admin")).status_code, 403)
        self.assertEqual(notaus.level(), 2)

    def test_only_admins_see_and_trigger_it(self):
        p, uid = profile("NxPaula")
        self.assertEqual(p.get("/api/whoami").json()["notaus_may"], False)
        self.assertEqual(p.post("/api/notaus", json={"level": 2}).status_code, 403)
        self.assertEqual(client().post("/api/notaus", json={"level": 2}).status_code, 401)   # guests never
        set_panel(notaus_profiles=True)                                                     # the old switch counts no more
        self.assertEqual(p.post("/api/notaus", json={"level": 1}).status_code, 403)
        notaus.trigger(1, "Anna", "u_x", "panel", "geheim")
        self.assertEqual(set(p.get("/api/notaus").json()), {"level", "outside", "mine"})    # not who, why or how
        a = admin()
        self.assertEqual(a.post("/api/notaus", json={"level": "3"}).status_code, 400)
        # from outside an admin can still go up (the phone on the way), never down
        out = client(OUTSIDE)
        out.cookies = a.cookies
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
        a, _ = profile("NxHanna")
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



class Mine(Base):
    """Mein Notaus (3b): one profile stops its own part; reading goes on, everything else of it waits."""

    def test_on_closes_the_profiles_ways_in_but_this_browser(self):
        p, uid = profile("NxMira")
        other = client()
        self.assertEqual(other.post("/api/profile/login", json={"name": "NxMira", "pin": "1234"}).status_code, 200)
        key = profiles.add_device("Mira Lautsprecher", uid)
        dev = client()
        dev.headers[profiles.DEVICE_HEADER] = key
        self.assertEqual(dev.get("/api/whoami").status_code, 200)
        r = p.post("/api/notaus/mine", json={})
        self.assertEqual((r.status_code, r.json()["mine"]["on"], r.json()["level"]), (200, True, 0))
        self.assertEqual(p.post("/api/notaus/mine", json={}).status_code, 409)
        self.assertTrue(notaus.own(uid))
        self.assertEqual(p.get("/api/whoami").json()["profile"]["id"], uid)      # this browser stays
        self.assertFalse((other.get("/api/whoami").json().get("profile") or {}).get("id"))   # the other login ended
        self.assertEqual(dev.get("/api/whoami").status_code, 503)                # the device key is closed
        self.assertEqual(dev.get("/api/notaus").status_code, 200)              # the status stays readable
        req = request("192.168.178.20")
        req.scope["speech_mcp"] = {"uid": uid}
        self.assertIsNone(profiles.current(req))                                 # MCP
        req = request("192.168.178.20")
        req.scope["speech_profile"] = uid
        self.assertIsNone(profiles.current(req))                                 # Telegram
        # the whole Spark goes on: no stage, the internet stays open, other profiles act
        self.assertEqual(notaus.level(), 0)
        self.assertFalse(notaus.blocks("internet", uid))
        with self.assertRaises(notaus.NotausAktiv):
            notaus.stop("aktion", uid)
        notaus.stop("aktion", "u_jemand")
        notaus.acting(uid)
        try:
            with self.assertRaises(notaus.NotausAktiv):
                notaus.stop("aktion")                                            # the acting profile, without a uid
        finally:
            notaus.acting("")
        # Zustand → Live: how many, never who
        lv = notaus.for_live()["mine"]
        self.assertEqual(lv["n"], 1)
        self.assertNotIn("NxMira", json.dumps(notaus.for_live(), ensure_ascii=False))
        # the admin sees which profile, and may lift it
        a = admin()
        self.assertEqual([x["name"] for x in a.get("/api/notaus").json()["mine_list"]], ["NxMira"])

    def test_lifting_by_the_profile_with_its_pin_or_by_an_admin(self):
        p, uid = profile("NxNele", pin="4321")
        self.assertEqual(p.post("/api/notaus/mine/off", json={"pin": "4321"}).status_code, 409)   # not on
        p.post("/api/notaus/mine", json={})
        key = profiles.add_device("Nele App", uid, scope="app")
        app = client()
        app.headers[profiles.DEVICE_HEADER] = key
        self.assertIn(app.post("/api/notaus/mine/off", json={"pin": "4321"}).status_code, (403, 503))   # never from the app
        self.assertEqual(p.post("/api/notaus/mine/off", json={"pin": "0000"}).status_code, 401)
        self.assertEqual(p.post("/api/notaus/mine/off", json={"pin": 4321}).status_code, 401)
        self.assertTrue(notaus.own(uid))
        r = p.post("/api/notaus/mine/off", json={"pin": "4321"})
        self.assertEqual((r.status_code, r.json()["mine"]["on"]), (200, False))
        self.assertFalse(notaus.own(uid))
        # an admin, in the browser at home, with the password (no second step here)
        p.post("/api/notaus/mine", json={})
        self.assertEqual(p.post("/api/admin/notaus/mine/off", json={"uid": uid}).status_code, 403)   # not an admin
        a = admin()
        self.assertEqual(a.post("/api/admin/notaus/mine/off", json={"uid": uid, "password": "falsch"}).status_code, 401)
        self.assertEqual(a.post("/api/admin/notaus/mine/off", json={"uid": uid, "password": "secret-admin"}).status_code, 200)
        self.assertFalse(notaus.own(uid))

    def test_a_damaged_file_holds_everyone_and_only_an_admin_clears_it(self):
        p, uid = profile("NxOda", pin="5555")
        os.makedirs(os.path.dirname(notaus.MINE_FILE), exist_ok=True)
        with open(notaus.MINE_FILE, "w") as f:
            f.write("{kaputt")
        self.assertTrue(notaus.own(uid) and notaus.own("u_jemand"))
        self.assertEqual(p.post("/api/notaus/mine/off", json={"pin": "5555"}).status_code, 409)
        a = admin()
        self.assertEqual(a.post("/api/admin/notaus/mine/off", json={"uid": "", "password": "secret-admin"}).status_code, 200)
        self.assertFalse(notaus.own(uid))

    def test_the_model_reads_but_does_not_act(self):
        a, uid = profile("NxInes")
        url = f"http://127.0.0.1:{helpers.HA_PORT}"
        self.assertEqual(a.put("/api/profile/homeassistant", json={"url": url, "token": helpers.HA_TOKEN}).status_code, 200)
        try:
            def said(cmd):
                r = a.post("/api/chat", json={"messages": [{"role": "user", "content": cmd}]})
                return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
            a.post("/api/notaus/mine", json={})
            self.assertIn("NO TOOL home_assistant", said('TOOL home_assistant {"command": "Licht in der Küche an"}'))
            self.assertNotIn("NO TOOL home_assistant_states", said('TOOL home_assistant_states {}'))   # reading stays
            b, _ = profile("NxJule")                                                                     # others act
            self.assertEqual(b.get("/api/notaus").json()["mine"]["on"], False)
        finally:
            off()
            a.delete("/api/profile/homeassistant")


class Channels(Base):
    """Paket 1: Telegram, a fixed sentence, Home Assistant. Only switching on; the big one only for admin profiles."""

    def setUp(self):
        super().setUp()
        import coadmin
        import guard
        self.real = (coadmin.on, coadmin.role)
        self.admins = set()
        coadmin.on = lambda: True
        coadmin.role = lambda uid: "coadmin" if uid in self.admins else None
        guard.reset()
        try:
            os.remove(notaus.KEYS_FILE)
        except FileNotFoundError:
            pass

    def tearDown(self):
        import coadmin
        import guard
        coadmin.on, coadmin.role = self.real
        guard.reset()
        try:
            os.remove(notaus.KEYS_FILE)
        except FileNotFoundError:
            pass
        super().tearDown()

    def test_the_fixed_sentence_and_nothing_else(self):
        P = notaus.phrase
        self.assertEqual(P("Spark, Mein Notaus"), ("mine",))
        self.assertEqual(P("spark mein not-aus!"), ("mine",))
        self.assertEqual(P("Hey Spark, Notaus."), ("big", 2))
        self.assertEqual(P("Spark Not aus Stufe drei"), ("big", 3))
        self.assertEqual(P("Spark, Notaus Stufe 1"), ("big", 1))
        for no in ("Was ist der Notaus?", "Spark, wie geht der Notaus", "Notaus", "Spark, Notaus Stufe vier",
                   "Bitte sag: Spark, Notaus", "Spark Notaus aufheben", "", None, "Spark, Mein Notaus " * 20):
            self.assertIsNone(P(no), no)
        self.assertEqual(notaus.phrase_channel("speaker"), "esp32")
        self.assertEqual(notaus.phrase_channel("<script>"), "sprache")

    def test_by_sentence_in_the_chat(self):
        p, uid = profile("NxSaga")
        r = p.post("/api/chat", json={"messages": [{"role": "user", "content": "Spark, Notaus"}]})
        self.assertEqual(r.status_code, 200)
        list(helpers.events(r))
        self.assertEqual(notaus.level(), 0)                     # not an admin: the big one stays off
        self.admins.add(uid)
        r = p.post("/api/chat", json={"messages": [{"role": "user", "content": "Spark, Notaus Stufe eins"}]})
        list(helpers.events(r))
        self.assertEqual((notaus.level(), notaus.state()["channel"]), (1, "sprache"))
        off()
        q, uid2 = profile("NxSven")
        r = q.post("/api/chat", json={"messages": [{"role": "user", "content": "Spark, Mein Notaus"}], "client": "speaker"})
        list(helpers.events(r))
        self.assertFalse(notaus.own(uid2))                       # a voice the speaker did not recognise: a guest, nothing
        r = q.post("/api/chat", json={"messages": [{"role": "user", "content": "Spark, Mein Notaus"}]})
        list(helpers.events(r))
        self.assertTrue(notaus.own(uid2))
        self.assertEqual(notaus.mine()[uid2]["channel"], "sprache")
        self.assertEqual(notaus.level(), 0)

    def test_by_telegram(self):
        import telegram
        _, uid = profile("NxTill")
        sent = []

        async def call(c, method, **kw):
            sent.append(kw.get("text", ""))
        real = (telegram.call, telegram.owner)
        telegram.call = call
        telegram.owner = lambda cid: uid if cid == 77 else None
        try:
            def say(text, **extra):
                m = {"chat": {"type": "private", "id": 77}, "text": text, **extra}
                asyncio.run(telegram.handle(None, {"message": m}))
                return sent[-1] if sent else ""
            self.assertIn("nur Admins", say("/notaus 3"))
            self.assertEqual(notaus.level(), 0)
            self.admins.add(uid)
            self.assertIn("Stufe", say("/notaus 9"))                      # wrong stage: nothing
            self.assertEqual(notaus.level(), 0)
            n = len(sent)
            say("/notaus", forward_origin={"type": "user"})                 # forwarded: someone else's words
            self.assertEqual(notaus.level(), 0)
            self.assertIn("Stufe 2", say("/notaus"))
            self.assertEqual((notaus.level(), notaus.state()["channel"]), (2, "telegram"))
            self.assertGreater(len(sent), n)
            off()
            self.assertIn("Mein Notaus ist an", say("/meinnotaus"))
            self.assertTrue(notaus.own(uid))
            self.assertIn("Browser", say("Hallo"))                          # Telegram is closed for it now
        finally:
            telegram.call, telegram.owner = real

    def test_android_tile(self):
        # the tile sends the page's login without Origin, named by the app's user agent; it gets a fresh login back
        p, uid = profile("NxAnja")
        ua = {"user-agent": "SparkAndroid/1.1.0"}
        s = p.get("/api/notaus", headers=ua).json()
        self.assertEqual((s["level"], s["mine"]["on"], s.get("may")), (0, False, None))
        self.assertEqual(p.post("/api/notaus", json={"level": 2}, headers=ua).status_code, 403)
        r = p.post("/api/notaus/mine", content="{}", headers={**ua, "content-type": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(profiles.COOKIE, r.headers.get("set-cookie", ""))
        self.assertEqual(notaus.mine()[uid]["channel"], "android")
        a = admin()
        r = a.post("/api/notaus", json={"level": 2}, headers=ua)
        self.assertEqual((r.status_code, notaus.state()["channel"]), (200, "android"))

    def test_home_assistant_key_only_raises(self):
        a = admin()
        self.assertEqual(client().post("/api/admin/notaus/keys", json={"name": "HA"}).status_code, 401)
        self.assertEqual(a.post("/api/admin/notaus/keys", json={"name": "<b>"}).status_code, 400)
        token = a.post("/api/admin/notaus/keys", json={"name": "HA Wohnzimmer"}).json()["token"]
        self.assertTrue(token.startswith("na_"))
        self.assertNotIn(token, open(notaus.KEYS_FILE).read())                    # only the hash
        self.assertEqual([k["name"] for k in a.get("/api/admin/notaus/keys").json()["keys"]], ["HA Wohnzimmer"])
        self.assertEqual(client().get("/api/admin/notaus/keys").status_code, 401)
        h = {"Authorization": "Bearer " + token}
        self.assertEqual(client(OUTSIDE).post("/api/notaus/ha", json={}, headers=h).status_code, 403)
        self.assertEqual(client().post("/api/notaus/ha", json={}, headers={"Authorization": "Bearer na_falsch"}).status_code, 401)
        self.assertEqual(client().post("/api/notaus/ha", json={"level": "3"}, headers=h).status_code, 400)
        self.assertEqual(notaus.level(), 0)
        r = client().post("/api/notaus/ha", json={}, headers=h)
        self.assertEqual((r.status_code, r.json()["level"], notaus.state()["channel"]), (200, 2, "ha"))
        # it never lifts and is no login: it opens nothing else
        ha = client()
        ha.headers.update(h)
        self.assertNotEqual(ha.post("/api/notaus/lift", json={"level": 0}).status_code, 200)
        self.assertNotEqual(ha.get("/api/admin/notaus/keys").status_code, 200)
        self.assertEqual(notaus.level(), 2)
        kid = notaus._keys()[0]["id"]
        self.assertEqual(a.delete("/api/admin/notaus/keys/" + kid).status_code, 200)
        self.assertEqual(a.delete("/api/admin/notaus/keys/../x").status_code, 404)
        self.assertIsNone(notaus.key_find(token))
        for i in range(notaus.MAX_KEYS):
            notaus.key_new(f"k{i}")
        with self.assertRaises(ValueError):
            notaus.key_new("zu viel")
        with self.assertRaises(ValueError):
            os.remove(notaus.KEYS_FILE)
            notaus.key_new("<b>")


if __name__ == "__main__":
    unittest.main()
