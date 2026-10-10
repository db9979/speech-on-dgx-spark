"""Home Assistant tells the Spark (hamelden.py, plan „Home Assistant meldet an Spark“): rule options (when,
pause, only when), the live WebSocket connection, house notes on speakers, events with a key of their own,
rules by voice and a camera picture in words. Everything off by default, the panel decides by fixed rules.
Home Assistant, its WebSocket API and the language model are fakes (tests/helpers.py); no wall clock."""
import asyncio
import datetime
import time
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402
import hamelden  # noqa: E402
import messages  # noqa: E402
import netguard  # noqa: E402
import panel  # noqa: E402
import proactive  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ALL_ON = dict(proactive=True, ha_live=True, ha_loud=True, ha_events=True, ha_voice_rules=True, ha_camera=True,
              messages=True, messages_announce=True)
ALL_OFF = {k: False for k in ALL_ON}
EXTRA = [
    {"entity_id": "binary_sensor.flur_bewegung", "state": "off",
     "attributes": {"friendly_name": "Flur Bewegung", "device_class": "motion"}},
    {"entity_id": "binary_sensor.garten_bewegung", "state": "off",
     "attributes": {"friendly_name": "Garten Bewegung", "device_class": "motion"}},
    {"entity_id": "light.garten", "state": "off", "attributes": {"friendly_name": "Garten Licht"}},
    {"entity_id": "event.haustuer_klingel", "state": "2026-10-10T10:00:00+00:00",
     "attributes": {"friendly_name": "Haustür Klingel", "device_class": "doorbell"}},
    {"entity_id": "camera.haustuer", "state": "idle", "attributes": {"friendly_name": "Kamera Haustür"}},
    {"entity_id": "person.hanne", "state": "home", "attributes": {"friendly_name": "Hanne"}},
    {"entity_id": "sun.sun", "state": "above_horizon", "attributes": {"friendly_name": "Sonne"}},
]


def profile(name, pin="1234", **settings):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    uid = c.get("/api/whoami").json()["profile"]["id"]
    s = dict({"pro_on": True, "pro_quiet": "", "tz": "Europe/Berlin", "pro_max": 30}, **settings)
    assert c.put("/api/profile/settings", json=s).status_code == 200
    c.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
    return c, uid


def _uid(client):
    return client.get("/api/whoami").json()["profile"]["id"]


def notes(client):
    return [x["text"] for x in client.get("/api/proactive").json()["items"]]


def state(eid):
    return next(s for s in helpers.HA_STATES if s["entity_id"] == eid)


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(**ALL_ON)
        helpers.HA_STATES.extend(dict(x, attributes=dict(x["attributes"])) for x in EXTRA)
        hamelden._PENDING.clear()
        hamelden._loud.clear()
        hamelden._cam.clear()
        hamelden._ev_said.clear()

    def tearDown(self):
        ids = {x["entity_id"] for x in EXTRA}
        helpers.HA_STATES[:] = [s for s in helpers.HA_STATES if s["entity_id"] not in ids]
        hamelden.stop_all()
        helpers.set_config(**ALL_OFF)


class RuleOptions(Base):
    def test_when_pause_and_only(self):
        a, uid = profile("Hedda")
        r = a.post("/api/proactive/rules", json={"conds": [{"entity": "Flur Bewegung", "op": "changes", "when": "on"}],
                                                 "pause": 10, "text": "Bewegung im Flur."})
        self.assertEqual(r.status_code, 200, r.text)
        rule = r.json()["rules"][0]
        self.assertEqual(rule["conds"][0]["when"], "on")
        self.assertEqual(rule["pause"], 10)
        self.assertIn("höchstens alle 10 Minuten", r.json()["rules"][0]["line"])
        p = proactive.prefs(uid)
        flur = dict(state("binary_sensor.flur_bewegung"))

        def run(st):
            asyncio.run(proactive.check_ha(uid, p, by_id={flur["entity_id"]: dict(flur, state=st)}))
        run("off")            # first look: only remembered
        run("on")             # off → on: said
        run("off")            # on → off: "bei an" only, nothing
        run("on")             # again, but within its 10 minute pause
        self.assertEqual(notes(a), ["Bewegung im Flur."])
        # the pause is over (the rule's memory says when it last spoke): it speaks again
        proactive._mut(uid, lambda st: st["rules"][rule["id"]].update(said=time.time() - 601))
        run("off")
        run("on")
        self.assertEqual(notes(a), ["Bewegung im Flur.", "Bewegung im Flur."])

    def test_only_when(self):
        local = datetime.datetime(2026, 10, 10, 14, 0)
        home = {"person.anna": {"entity_id": "person.anna", "state": "home"},
                "person.ben": {"entity_id": "person.ben", "state": "not_home"}}
        away = {"person.anna": {"entity_id": "person.anna", "state": "not_home"},
                "person.ben": {"entity_id": "person.ben", "state": "not_home"}}
        self.assertTrue(proactive.only_ok({}, home, local))
        self.assertFalse(proactive.only_ok({"only": "empty"}, home, local))
        self.assertTrue(proactive.only_ok({"only": "empty"}, away, local))
        self.assertFalse(proactive.only_ok({"only": "empty"}, {}, local))          # no persons: never "empty"
        self.assertFalse(proactive.only_ok({"only": "away", "me": "person.anna"}, home, local))
        self.assertTrue(proactive.only_ok({"only": "away", "me": "person.ben"}, home, local))
        self.assertFalse(proactive.only_ok({"only": "away", "me": "person.zoe"}, home, local))   # unknown: no
        sun_down = {"sun.sun": {"entity_id": "sun.sun", "state": "below_horizon"}}
        self.assertTrue(proactive.only_ok({"only": "night"}, sun_down, local))     # the sun decides, not the clock
        self.assertFalse(proactive.only_ok({"only": "day"}, sun_down, local))
        self.assertTrue(proactive.only_ok({"only": "night"}, {}, datetime.datetime(2026, 10, 10, 23, 0)))
        self.assertFalse(proactive.only_ok({"only": "night"}, {}, local))

    def test_away_needs_the_person_and_fires_only_then(self):
        a, uid = profile("Hanne")        # the profile's name is the person's name in Home Assistant
        r = a.post("/api/proactive/rules", json={"conds": [{"entity": "Bad Fenster", "op": "is", "value": "offen"}],
                                                 "only": "away"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["rules"][0]["me"], "person.hanne")
        b, _ = profile("Niemand")
        r = b.post("/api/proactive/rules", json={"conds": [{"entity": "Bad Fenster", "op": "is", "value": "offen"}],
                                                 "only": "away"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Person", r.json()["detail"])
        b.put("/api/profile/settings", json={"pro_ha_me": "../etc"})          # not a person: not taken
        self.assertEqual(profiles.settings(_uid(b)).get("pro_ha_me", ""), "")
        self.assertEqual(b.put("/api/profile/settings", json={"pro_ha_me": "person.anna"}).status_code, 200)
        r = b.post("/api/proactive/rules", json={"conds": [{"entity": "Bad Fenster", "op": "is", "value": "offen"}],
                                                 "only": "away"})
        self.assertEqual(r.status_code, 200, r.text)
        # Hanne and Anna are at home: the open window is true, but not said
        win = state("binary_sensor.bad_fenster")
        old = win["state"]
        try:
            win["state"] = "off"
            asyncio.run(proactive.due_once())
            win["state"] = "on"
            asyncio.run(proactive.due_once())
            self.assertEqual(notes(a), [])
        finally:
            win["state"] = old
        self.assertEqual(a.post("/api/proactive/rules", json={"conds": [{"entity": "Bad Fenster", "op": "is", "value": "x"}],
                                                              "only": "sometimes"}).status_code, 400)


class Live(Base):
    def wait(self, check, steps=150):
        async def go():
            for _ in range(steps):
                if check():
                    return True
                await asyncio.sleep(0.02)
            return False
        return go()

    def test_live_connection_sees_short_motion(self):
        a, uid = profile("Lino", pro_ha_live=True)
        r = a.post("/api/proactive/rules", json={"conds": [{"entity": "Flur Bewegung", "op": "is", "value": "an"}],
                                                 "text": "Bewegung im Flur."})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(hamelden.live_wanted(uid))
        eid = "binary_sensor.flur_bewegung"

        async def go():
            helpers.HA_WS["subs"].clear()
            await hamelden.ensure()
            self.assertTrue(await self.wait(lambda: hamelden.cache(uid) is not None))
            self.assertEqual(helpers.HA_WS["subs"][-1]["type"], "subscribe_entities")
            self.assertEqual(helpers.HA_WS["subs"][-1]["entity_ids"], [eid])       # only the rule's devices
            self.assertTrue(await self.wait(lambda: proactive.state(uid).get("rules")))   # first look: armed
            # a motion of a few seconds between two minute checks: on, then off again
            helpers.HA_WS["push"].put({"c": {eid: {"+": {"s": "on", "lc": 1}}}})
            helpers.HA_WS["push"].put({"c": {eid: {"+": {"s": "off", "lc": 2}}}})
            # a device the rules do not name is ignored
            helpers.HA_WS["push"].put({"a": {"light.flur": {"s": "off", "a": {}}}})
            self.assertTrue(await self.wait(lambda: notes(a)))
            self.assertEqual(hamelden.status(uid)["live"], True)
            self.assertNotIn("light.flur", hamelden.cache(uid))
            # Zustand → Live shows the connection and what happened, in fixed words (no device names)
            import live
            self.assertIn({"name": "Home Assistant live", "proto": "WebSocket · Heimnetz", "dir": "aus", "n": 1},
                          live._conns(time.time()))
            texts = [x for _, area, x in live._events if area == "Home Assistant"]
            self.assertIn("Live-Verbindung steht · 1 Gerät(e)", texts)
            self.assertIn("Regel gemeldet", texts)
            self.assertFalse(any("Flur" in x for x in texts))
            hamelden.stop(uid)
        asyncio.run(go())
        self.assertEqual(notes(a), ["Bewegung im Flur."])

    def test_live_off_without_switches_and_refused_token(self):
        a, uid = profile("Lorna")
        a.post("/api/proactive/rules", json={"conds": [{"entity": "Flur Bewegung", "op": "is", "value": "an"}]})
        self.assertFalse(hamelden.live_wanted(uid))                     # the profile has not switched it on
        a.put("/api/profile/settings", json={"pro_ha_live": True})
        self.assertTrue(hamelden.live_wanted(uid))
        helpers.set_config(ha_live=False)
        self.assertFalse(hamelden.live_wanted(uid))                     # the admin has not
        helpers.set_config(ha_live=True)
        item = dict(profiles_ha(uid), token="x" * 40)
        s = hamelden.Stream(uid, "fp")

        async def go():
            with self.assertRaises(PermissionError):
                await hamelden._session(s, item, ["binary_sensor.flur_bewegung"])
        asyncio.run(go())

    def test_only_checked_addresses(self):
        s = hamelden.Stream("u_000000000000", "fp")
        for url in ("http://169.254.169.254", "http://127.0.0.1:31002"):
            async def go(url=url):
                with self.assertRaises(netguard.Blocked):
                    await hamelden._session(s, {"url": url, "token": "t" * 40}, ["sun.sun"])
            asyncio.run(go())
        self.assertEqual(hamelden.ws_target("https://ha.local:8123/x/")[0], "wss://ha.local:8123/x/api/websocket")
        self.assertEqual(hamelden.ws_target("http://ha.local")[:3], ("ws://ha.local/api/websocket", "ha.local", 80))

    def test_apply(self):
        st = {}
        eids = ["sensor.a", "sensor.b"]
        self.assertTrue(hamelden.apply(st, {"a": {"sensor.a": {"s": "1", "a": {"unit_of_measurement": "W", "x": 1}},
                                                  "sensor.z": {"s": "9", "a": {}}}}, eids))
        self.assertNotIn("sensor.z", st)
        hamelden.apply(st, {"c": {"sensor.a": {"+": {"s": "2", "a": {"y": 2}}, "-": {"a": ["x"]}}}}, eids)
        self.assertEqual(st["sensor.a"], {"entity_id": "sensor.a", "state": "2", "attributes": {"unit_of_measurement": "W", "y": 2}})
        self.assertTrue(hamelden.apply(st, {"r": ["sensor.a"]}, eids))
        self.assertEqual(st, {})
        self.assertFalse(hamelden.apply(st, {"c": {"sensor.b": {"+": {"s": "1"}}}}, eids))   # unknown before: nothing


def profiles_ha(uid):
    import homeassistant
    return homeassistant.get(uid)


class Loud(Base):
    def test_only_own_sentence_without_names_or_persons(self):
        a, uid = profile("Lars", pro_ha_loud=True)
        profile("Mirella")
        old = hamelden.speakers
        hamelden.speakers = lambda u: [{"id": "d_flur", "name": "Flur"}]
        try:
            body = {"conds": [{"entity": "Flur Bewegung", "op": "is", "value": "an"}], "loud": True, "speakers": ["d_flur"]}
            r = a.post("/api/proactive/rules", json=body)
            self.assertIn("eigenen Satz", r.json()["detail"])
            r = a.post("/api/proactive/rules", json=dict(body, text="Mirella ist im Flur."))
            self.assertIn("Name", r.json()["detail"])
            r = a.post("/api/proactive/rules", json={"conds": [{"entity": "person.anna", "op": "is", "value": "zu Hause"}],
                                                     "loud": True, "speakers": ["d_flur"], "text": "Jemand ist da."})
            self.assertIn("Person", r.json()["detail"])
            r = a.post("/api/proactive/rules", json=dict(body, text="Bewegung im Flur.", speakers=["d_anders"]))
            self.assertIn("Lautsprecher", r.json()["detail"])
            r = a.post("/api/proactive/rules", json=dict(body, text="Bewegung im Flur."))
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["rules"][0]["speakers"], ["d_flur"])
            a.put("/api/profile/settings", json={"pro_ha_loud": False})
            r = a.post("/api/proactive/rules", json=dict(body, text="Bewegung im Flur."))
            self.assertIn("aus", r.json()["detail"])
        finally:
            hamelden.speakers = old

    def test_said_on_speakers_as_it_is(self):
        a, uid = profile("Luzi", pro_ha_loud=True)
        said = []

        async def announce(sender, dids, text, now=None, house=False):
            said.append((sender, dids, text, house))
            return ["Flur"], ""
        old = hamelden.speakers, messages.announce
        hamelden.speakers = lambda u: [{"id": "d_flur", "name": "Flur"}]
        messages.announce = announce
        try:
            rule = {"conds": [{"entity": "binary_sensor.flur_bewegung", "name": "Flur Bewegung", "op": "is", "value": "an"}],
                    "text": "Bewegung im Flur.", "loud": True,
                    "speakers": ["d_flur", "d_fremd"]}
            asyncio.run(hamelden.said(uid, rule, "Bewegung im Flur.", "Flur Bewegung ist jetzt an", {}))
            self.assertEqual(said, [(uid, ["d_flur"], "Bewegung im Flur.", True)])
            self.assertEqual(notes(a), ["Bewegung im Flur."])           # and on the profile's own devices
            # quiet hours or a pause: nothing aloud either
            old_b = proactive.blocked
            proactive.blocked = lambda *x, **k: "quiet hours"
            try:
                asyncio.run(hamelden.said(uid, rule, "Bewegung im Flur.", "", {}))
            finally:
                proactive.blocked = old_b
            self.assertEqual(len(said), 1)
            # the daily limit of personal notes does not hold the house back
            self.assertTrue(hamelden._loud_may(uid, "daily limit reached"))
            # never more than LOUD_PER_HOUR an hour
            for _ in range(hamelden.LOUD_PER_HOUR + 3):
                asyncio.run(hamelden.loud(uid, rule))
            self.assertEqual(len(said), hamelden.LOUD_PER_HOUR)
        finally:
            hamelden.speakers, messages.announce = old

    def test_house_announcement_has_no_sender_prefix(self):
        import esp32
        _, uid = profile("Mats")
        got = []

        class S:
            answer = None

            async def say(self, text, tone=False):
                got.append(text)
        old = messages.speakers_for
        messages.speakers_for = lambda u: [{"id": "d_x", "name": "Küche", "owner": uid}]
        esp32._live["d_x"] = S()

        async def go():
            await messages.announce(uid, ["d_x"], "Es hat geklingelt.", house=True)
            await asyncio.sleep(0.05)
        try:
            asyncio.run(go())
        finally:
            messages.speakers_for = old
            esp32._live.pop("d_x", None)
        self.assertEqual(got, ["Es hat geklingelt."])


class Events(Base):
    def test_events_with_their_own_key(self):
        a, uid = profile("Elfi")
        self.assertEqual(a.put("/api/profile/ha-events", json={"events": []}).status_code, 403)   # profile off
        a.put("/api/profile/settings", json={"pro_ha_events": True})
        self.assertEqual(a.put("/api/profile/ha-events", json={"events": [{"name": "klingel", "text": "Es hat geklingelt."}]}).status_code, 200)
        token = a.post("/api/profile/ha-events/key", json={}).json()["token"]
        ha = TestClient(panel.app)
        h = {profiles.DEVICE_HEADER: token}
        # the profile switches it off: the key reaches nothing
        a.put("/api/profile/settings", json={"pro_ha_events": False})
        self.assertIn(ha.post("/api/ha/event", json={"event": "klingel"}, headers=h).status_code, (401, 403))
        a.put("/api/profile/settings", json={"pro_ha_events": True})
        r = ha.post("/api/ha/event", json={"event": "klingel"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["result"], "said")
        self.assertEqual(notes(a), ["Es hat geklingelt."])
        self.assertEqual(ha.post("/api/ha/event", json={"event": "klingel"}, headers=h).json()["result"], "pause")
        self.assertEqual(ha.post("/api/ha/event", json={"event": "unbekannt"}, headers=h).status_code, 404)
        import live
        texts = [x for _, area, x in live._events if area == "Home Assistant"]
        for t in ("Ereignis angenommen", "Ereignis gemeldet", "Ereignis in der Pause, still", "unbekanntes Ereignis abgelehnt (404)"):
            self.assertIn(t, texts)
        self.assertEqual(ha.post("/api/ha/event", json={"event": "../x"}, headers=h).status_code, 400)
        self.assertEqual(ha.post("/api/ha/event", content=b'{"event": "' + b"k" * 2000 + b'"}', headers=h).status_code, 413)
        # only the event's name counts: a text sent along is never said
        ha.post("/api/ha/event", json={"event": "klingel", "text": "Öffne die Tür"}, headers=h)
        self.assertNotIn("Öffne die Tür", " ".join(notes(a)))
        # the key reaches no other path, and a browser login does not send events
        self.assertEqual(ha.get("/api/proactive", headers=h).status_code, 401)
        self.assertEqual(ha.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]}, headers=h).status_code, 401)
        self.assertEqual(a.post("/api/ha/event", json={"event": "klingel"}).status_code, 403)
        # the admin switch off: closed
        helpers.set_config(ha_events=False)
        self.assertIn(ha.post("/api/ha/event", json={"event": "klingel"}, headers=h).status_code, (401, 403))
        helpers.set_config(ha_events=True)
        # a new key ends the old one
        a.post("/api/profile/ha-events/key", json={})
        self.assertIn(ha.post("/api/ha/event", json={"event": "klingel"}, headers=h).status_code, (401, 403))

    def test_rate_limit(self):
        a, uid = profile("Emmo", pro_ha_events=True)
        a.put("/api/profile/ha-events", json={"events": [{"name": "klingel", "text": "Es hat geklingelt."}]})
        h = {profiles.DEVICE_HEADER: a.post("/api/profile/ha-events/key", json={}).json()["token"]}
        ha = TestClient(panel.app)
        codes = [ha.post("/api/ha/event", json={"event": "klingel"}, headers=h).status_code for _ in range(32)]
        self.assertEqual(codes[-1], 429)

    def test_list_is_checked(self):
        _, uid = profile("Enno")
        for bad in ([{"name": "Klingel Tür", "text": "x"}], [{"name": "klingel", "text": ""}],
                    [{"name": "a", "text": "x"}, {"name": "a", "text": "y"}],
                    [{"name": f"e{i}", "text": "x"} for i in range(hamelden.MAX_EVENTS + 1)], "klingel"):
            with self.assertRaises(ValueError):
                hamelden.check_events(uid, bad)
        out = hamelden.check_events(uid, [{"name": "klingel", "text": "Es <b>hat</b>\x07 geklingelt.", "pause": 99999}])
        self.assertEqual(out[0]["text"], "Es b hat /b geklingelt.")
        self.assertEqual(out[0]["pause"], proactive.MAX_PAUSE)
        helpers.set_config(ha_events=False)
        a, _ = profile("Enno", pro_ha_events=True)
        self.assertEqual(a.put("/api/profile/ha-events", json={"events": []}).status_code, 403)


class Voice(Base):
    def test_parse(self):
        cases = {
            "Sag mir Bescheid, wenn jemand an der Haustür ist": ("changes", "motion"),
            "Melde dich, wenn Bewegung im Garten erkannt wird": ("changes", "motion"),
            "Gib mir Bescheid, sobald Anna heimkommt": ("is", "person"),
            "Sag mir Bescheid, wenn das Bad Fenster offen ist": ("is", None),
            "Melde dich, wenn der Whirlpool über 38 Grad hat": ("above", None),
            "Sag Bescheid, wenn es an der Haustür klingelt": ("changes", "ring"),
        }
        for text, (op, kind) in cases.items():
            got = hamelden.parse(text)
            self.assertIsNotNone(got, text)
            self.assertEqual((got[1]["op"], got[1].get("kind")), (op, kind), text)
        self.assertEqual(hamelden.parse("Melde dich, wenn der Whirlpool über 38 Grad hat")[1]["value"], "38")
        for text in ("Wie ist das Wetter?", "Sag mir Bescheid", "Erinnere mich morgen an den Müll", "x" * 300):
            self.assertIsNone(hamelden.parse(text), text)

    def ctx(self, uid, src="web:c1"):
        return {"who": {"id": uid}, "own": True, "src": src}

    def test_proposal_then_yes(self):
        a, uid = profile("Verena", pro_ha_voice=True)
        res = asyncio.run(hamelden.answer(self.ctx(uid), "Gib mir Bescheid, wenn Bewegung im Garten erkannt wird"))
        self.assertIn("Noch NICHT angelegt", res["system"])
        self.assertIn("Garten Bewegung", res["system"])                 # the sensor, not the garden lamp
        self.assertEqual(a.get("/api/proactive/status").json()["rules"], [])
        hamelden.drop_pending(uid)                                      # the end of the proposing turn
        self.assertIsNone(asyncio.run(hamelden.answer(self.ctx(uid, "web:other"), "Ja")))   # another conversation
        res = asyncio.run(hamelden.answer(self.ctx(uid), "Ja"))
        self.assertIn("Regel angelegt", res["system"])
        rules = a.get("/api/proactive/status").json()["rules"]
        self.assertEqual([(r["conds"][0]["entity"], r["conds"][0].get("when"), r.get("pause"), r.get("src")) for r in rules],
                         [("binary_sensor.garten_bewegung", "on", 10, "voice")])
        # a no: nothing
        asyncio.run(hamelden.answer(self.ctx(uid), "Melde dich, wenn Anna heimkommt"))
        hamelden.drop_pending(uid)
        res = asyncio.run(hamelden.answer(self.ctx(uid), "Nein"))
        self.assertIn("NICHT angelegt", res["system"])
        self.assertEqual(len(a.get("/api/proactive/status").json()["rules"]), 1)

    def test_person_and_doorbell(self):
        _, uid = profile("Vito", pro_ha_voice=True)
        res = asyncio.run(hamelden.answer(self.ctx(uid), "Melde dich, wenn Anna heimkommt"))
        self.assertIn("Anna ist zu Hause", res["system"])
        hamelden._PENDING.clear()
        res = asyncio.run(hamelden.answer(self.ctx(uid), "Sag Bescheid, wenn es an der Haustür klingelt"))
        self.assertIn("Haustür Klingel ändert sich", res["system"])

    def test_off_and_not_for_others(self):
        _, uid = profile("Vivi")
        self.assertIsNone(asyncio.run(hamelden.answer(self.ctx(uid), "Melde dich, wenn Anna heimkommt")))   # profile off
        self.assertIsNone(asyncio.run(hamelden.answer({"who": {"id": uid}, "own": False, "src": "x"},
                                                      "Melde dich, wenn Anna heimkommt")))
        self.assertIsNone(asyncio.run(hamelden.answer({"who": None, "own": False}, "Melde dich, wenn Anna heimkommt")))
        _, uid2 = profile("Volker", pro_ha_voice=True)
        helpers.set_config(ha_voice_rules=False)
        self.assertIsNone(asyncio.run(hamelden.answer(self.ctx(uid2), "Melde dich, wenn Anna heimkommt")))
        helpers.set_config(ha_voice_rules=True)
        res = asyncio.run(hamelden.answer(self.ctx(uid2), "Melde dich, wenn der Zeppelin landet"))
        self.assertIn("kein passendes Gerät", res["system"])
        self.assertEqual(hamelden.pending(uid2), None)


class Camera(Base):
    def test_described_only_when_on(self):
        a, uid = profile("Kaja")
        body = {"conds": [{"entity": "Flur Bewegung", "op": "is", "value": "an"}], "camera": "Kamera Haustür"}
        self.assertIn("aus", a.post("/api/proactive/rules", json=body).json()["detail"])
        a.put("/api/profile/settings", json={"pro_ha_cam": True})
        self.assertEqual(a.post("/api/proactive/rules", json=dict(body, camera="Zeppelin")).status_code, 400)
        r = a.post("/api/proactive/rules", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        rule = r.json()["rules"][0]
        self.assertEqual(rule["camera"], "camera.haustuer")
        import homeassistant
        asyncio.run(hamelden.said(uid, rule, "Bewegung im Flur.", "", homeassistant.get(uid)))
        # the fake model "reads" the test picture; the description is outside text, kept short and clean
        self.assertEqual(notes(a), ["Bewegung im Flur. Kamera: Die Zahl ist 42."])
        self.assertEqual(hamelden.clean_desc("<script>\x00 " + "Wort " * 40), "script " + " ".join(["Wort"] * 19))
        self.assertEqual(asyncio.run(hamelden.describe_camera(uid, homeassistant.get(uid), "camera.../x")), "")

    def test_switches_are_functions(self):
        for key in ("halive", "haloud", "haevent", "havoice", "hacam"):
            f = features.BY_KEY[key]
            self.assertEqual(f.parent, "proactive")
            self.assertFalse(f.guests)
            self.assertTrue(f.profile.startswith("pro_ha_"))
            self.assertIs(profiles.SETTINGS[f.profile][0], False)


if __name__ == "__main__":
    unittest.main()
