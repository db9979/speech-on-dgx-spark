"""Room mode on another device of the profile (roomfar.py): "Raummodus im Wohnzimmer an" by fixed rules,
never the model or Home Assistant; only own connected speakers, only after "Ja", off by default; ending
always works. Speakers are sessions with a fake connection, no wall clock."""
import asyncio
import json
import unittest

from tests import helpers

helpers.start()
import esp32  # noqa: E402
import guard  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import roomfar  # noqa: E402
import roomlive  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class FakeWS:
    async def send_text(self, t):
        pass

    async def send_bytes(self, b):
        pass

    async def close(self, code=1000):
        pass


def speaker(uid, name, area=""):
    profiles.add_device(name, uid)
    did = next(x["id"] for x in profiles.own_devices(uid) if x["name"] == name)
    esp32._update(lambda d: d["clients"].update({"c-" + did: {"device": did, "room_area": area}}))
    return did


def connect(uid, did, name):
    s = esp32.Session(FakeWS(), "c-" + did, {"user": uid, "id": did, "name": name}, "")
    s.said = []

    async def say(text, tone=False):
        s.said.append(text)
    s.say, s.listen = say, (lambda mode: None)
    esp32._live[did] = s
    return s


def ctx(uid, src="web:v1", **kw):
    return dict({"who": profiles.by_id(uid), "own": True, "src": src, "client": None, "private": True}, **kw)


class RoomFar(unittest.TestCase):
    def setUp(self):
        helpers.set_config(room=True, room_remote=True, esp32=True, public=False)
        roomlive.ACTIVE.clear()
        roomfar._PENDING.clear()
        guard._rate.clear()

    def tearDown(self):
        for s in list(esp32._live.values()):
            if s.room is not None and s.room.get("task"):
                s.room["task"].cancel()
        esp32._live.clear()
        roomfar._PENDING.clear()
        helpers.set_config(room=False, room_remote=False, esp32=False)

    def test_sentences(self):
        p = roomfar.parse
        self.assertEqual(p("Kannst du den Raummodus für den Lautsprecher im Wohnzimmer aktivieren?"),
                         ("start", "wohnzimmer", None))
        self.assertEqual(p("Raum-Modus in der Küche für 60 Minuten an"), ("start", "küche", 60))
        self.assertEqual(p("Starte den Raummodus im Bad für eine Stunde"), ("start", "bad", 60))
        self.assertEqual(p("Raummodus im Wohnzimmer aus"), ("end", "wohnzimmer", None))
        self.assertEqual(p("Raummodus überall beenden"), ("end", "überall", None))
        # without a place it is the device's own room mode, not this
        for own in ("Raummodus an", "Raummodus bitte an", "Raummodus für 30 Minuten an", "Raummodus aus", "Wie spät ist es?"):
            self.assertIsNone(p(own), own)
        self.assertIsNone(p("Raummodus " + "x" * 200 + " an"))

    def test_off_by_default_and_fixed_answer(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["room_remote"], False)
        self.assertIs(profiles.SETTINGS["room_remote"][0], False)
        a, uid = profile("Rf Aus")
        a.put("/api/profile/settings", json={"esp_on": True})
        speaker(uid, "Wohnzimmer")
        helpers.HA_CALLS.clear()
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "Kannst du den Raummodus für den "
                                                   "Lautsprecher im Wohnzimmer aktivieren?"}], "convo": "f1"})
        self.assertEqual(r.status_code, 200)
        call = helpers.LLM_CALLS[-1]
        said = json.dumps(call, ensure_ascii=False)
        self.assertIn("Ich → Raum-Modus", said)     # the profile switch is still off: says where
        self.assertFalse(call.get("tools"))           # no smart home, no other tools in this turn
        self.assertEqual(helpers.HA_CALLS, [])
        self.assertEqual(roomfar._PENDING, {})
        helpers.set_config(room_remote=False)
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "Raummodus im Wohnzimmer an"}], "convo": "f1"})
        self.assertIn("ausgeschaltet", json.dumps(helpers.LLM_CALLS[-1], ensure_ascii=False))
        self.assertFalse(helpers.LLM_CALLS[-1].get("tools"))
        self.assertFalse(a.get("/api/whoami").json().get("room_remote"))

    def test_start_after_yes_only(self):
        a, uid = profile("Rf Jana")
        a.put("/api/profile/settings", json={"esp_on": True, "room_remote": True})
        did = speaker(uid, "Lautsprecher 2", area="Wohnzimmer")

        async def run():
            s = connect(uid, did, "Lautsprecher 2")
            res = await roomfar.answer(ctx(uid, app=True), "Raummodus im Wohnzimmer für 60 Minuten an")
            self.assertIn("Soll Lautsprecher 2 60 Minuten zuhören?", res["system"])
            self.assertIsNone(s.room)
            # another conversation's "Ja" does not count
            self.assertIsNone(await roomfar.answer(ctx(uid, src="web:v2"), "Ja"))
            self.assertIsNone(s.room)
            res = await roomfar.answer(ctx(uid, app=True), "Ja")
            self.assertIn("hört jetzt 60 Minuten zu", res["system"])
            await asyncio.sleep(0.01)
            self.assertIsNotNone(s.room)
            self.assertIn("gestartet von der iPhone-App", s.said[-1])
            self.assertEqual(roomlive.mine(uid)[0]["name"], "Lautsprecher 2")
            # asked again: already listening, no second proposal
            res = await roomfar.answer(ctx(uid), "Raummodus im Wohnzimmer an")
            self.assertIn("hört schon zu", res["system"])
            self.assertEqual(roomfar._PENDING, {})
            # ending needs no "Ja"
            res = await roomfar.answer(ctx(uid), "Raummodus im Wohnzimmer aus")
            self.assertIn("beendet", res["system"])
            self.assertIsNone(s.room)
            self.assertEqual(roomlive.mine(uid), [])
            # a "Nein" starts nothing
            await roomfar.answer(ctx(uid), "Raummodus im Wohnzimmer an")
            res = await roomfar.answer(ctx(uid), "Nein")
            self.assertIn("NICHT", res["system"])
            self.assertIsNone(s.room)
        asyncio.run(run())
        self.assertIn("far", [x["why"] for x in roomlive.load_history(uid)])

    def test_only_own_connected_speakers(self):
        a, uid = profile("Rf Ben")
        b, other = profile("Rf Ida")
        for c in (a, b):
            c.put("/api/profile/settings", json={"esp_on": True, "room_remote": True})
        mine = speaker(uid, "Küche")
        theirs = speaker(other, "Wohnzimmer")

        async def run():
            connect(other, theirs, "Wohnzimmer")
            res = await roomfar.answer(ctx(uid), "Raummodus im Wohnzimmer an")
            self.assertIn("keinen Lautsprecher „wohnzimmer“", res["system"])
            self.assertIn("Küche", res["system"])
            res = await roomfar.answer(ctx(uid), "Raummodus in der Küche an")
            self.assertIn("nicht verbunden", res["system"])   # and it does not start later by itself
            self.assertEqual(roomfar._PENDING, {})
            self.assertFalse(esp32.by_device(mine)[1].get("room_next"))
            self.assertIsNone(esp32._live[theirs].room)
        asyncio.run(run())

    def test_who_may_start(self):
        a, uid = profile("Rf Kai")
        a.put("/api/profile/settings", json={"esp_on": True, "room_remote": True})
        did = speaker(uid, "Bad")

        async def run():
            s = connect(uid, did, "Bad")
            for c, word in ((ctx(uid, client="telegram"), "Telegram"), (ctx(uid, client="siri"), "Siri"),
                            (ctx(uid, own=False), "Profil selbst")):
                res = await roomfar.answer(c, "Raummodus im Bad an")
                self.assertIn(word, res["system"])
            self.assertEqual(roomfar._PENDING, {})
            self.assertIn("angemeldete", roomfar.why_not({"who": None, "own": True}))
            # the switch going off between question and "Ja" stops it
            await roomfar.answer(ctx(uid), "Raummodus im Bad an")
            a.put("/api/profile/settings", json={"room_remote": False})
            await roomfar.answer(ctx(uid), "Ja")
            self.assertIsNone(s.room)
        asyncio.run(run())

    def test_several_fit_ask_again(self):
        a, uid = profile("Rf Lea")
        a.put("/api/profile/settings", json={"esp_on": True, "room_remote": True})
        for n in ("Küche oben", "Küche unten"):
            speaker(uid, n)

        async def run():
            res = await roomfar.answer(ctx(uid), "Raummodus in der Küche an")
            self.assertIn("Mehrere Lautsprecher passen", res["system"])
            self.assertEqual(roomfar._PENDING, {})
        asyncio.run(run())

    def test_speaker_passes_other_place_on(self):
        a, uid = profile("Rf Max")
        did = speaker(uid, "Küche", area="Küche")
        s = esp32.Session(FakeWS(), "c-" + did, {"user": uid, "id": did, "name": "Küche"}, "")
        self.assertTrue(s._room_elsewhere("Starte den Raummodus im Wohnzimmer"))
        self.assertFalse(s._room_elsewhere("Starte den Raummodus in der Küche"))
        self.assertFalse(s._room_elsewhere("Starte den Raummodus"))


if __name__ == "__main__":
    unittest.main()
