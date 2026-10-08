"""Room mode overhears voices from the TV (room.py, chat.room_voices): only known voices count, by choice only
while Home Assistant reports a TV on; "Spark, ..." and "Raummodus aus" count from any voice; the trial only
counts. Speaker identification and Home Assistant are mocks."""
import json
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import room  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
Q = "Wie viel sind 180 Grad in Fahrenheit?"     # a cue by fixed rules, no model needed


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class RoomVoices(unittest.TestCase):
    def setUp(self):
        helpers.set_config(room=True, room_voices=True, speaker_id=True, homeassistant=True)
        room._TV.clear()

    def tearDown(self):
        helpers.set_config(room=False, room_voices=False, speaker_id=False)

    def heard(self, a, rid, text, **body):
        r = a.post("/api/room/heard", json=dict({"room": rid, "text": text}, **body))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_only_known_voices(self):
        a, uid = profile("Vera")
        b = {"voices": "known", "probe": False}
        # a voice nobody taught (the TV): the question is not taken and not kept
        self.assertFalse(self.heard(a, "vv1234", Q, **b)["wait"])
        self.assertFalse(any(Q in x[1] for x in room.ROOMS[(uid, "vv1234")]["lines"]))
        self.assertEqual(a.post("/api/room/pause", json=dict(b, room="vv1234", quiet=3)).json().get("say"), None)
        # a known voice of exactly this sentence counts
        room.set_voice(uid, "vv1234", "", Q, known=True)
        self.assertTrue(self.heard(a, "vv1234", Q, **b)["wait"])
        # a known voice heard on another recording does not lend itself to this sentence
        room.ROOMS[(uid, "vv1234")]["pending"] = None
        room.set_voice(uid, "vv1234", "", "Ja das stimmt", known=True)
        self.assertFalse(self.heard(a, "vv1234", Q, **b)["wait"])
        # a "Nein" from the TV does not drop an open proposal
        room.ROOMS[(uid, "vv1234")]["offer"] = {"kind": "timer", "t": room.time.time()}
        self.assertNotIn("say", self.heard(a, "vv1234", "Nein", **b))
        self.assertTrue(room.ROOMS[(uid, "vv1234")]["offer"])
        room.ROOMS[(uid, "vv1234")]["offer"] = None
        # addressed to Spark, or ending room mode: any voice
        self.assertTrue(self.heard(a, "vv1234", "Spark, " + Q, **b)["wait"])
        self.assertTrue(self.heard(a, "vv1234", "Raummodus aus", **b).get("end"))

    def test_switch_off_means_as_before(self):
        a, uid = profile("Valentin")
        helpers.set_config(room_voices=False)
        self.assertTrue(self.heard(a, "vo1234", Q, voices="known", probe=False)["wait"])
        self.assertFalse(room.needs_voice(uid, "vo1234"))
        helpers.set_config(room_voices=True)
        self.assertTrue(self.heard(a, "vo1235", Q, voices="nonsense", probe=False)["wait"])   # unknown value = all

    def test_only_while_the_tv_is_on(self):
        a, uid = profile("Viktor")
        a.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        b = {"voices": "tv", "probe": False}
        self.assertTrue(self.heard(a, "vt1234", Q, area="Küche", **b)["wait"])          # no TV in the kitchen
        self.assertFalse(self.heard(a, "vt1235", Q, area="Wohnzimmer", **b)["wait"])    # TV on in the living room
        room.set_voice(uid, "vt1235", "", Q, known=True)
        self.assertTrue(self.heard(a, "vt1235", Q, area="Wohnzimmer", **b)["wait"])     # but a known voice counts
        # no answer from Home Assistant: listens to everybody, as without the setting
        room._TV[(uid, "buero")] = (room.time.time(), None)
        self.assertTrue(self.heard(a, "vt1236", Q, area="Büro", **b)["wait"])

    def test_trial_counts_only(self):
        a, uid = profile("Vroni")
        b = {"voices": "known", "probe": True}
        self.assertTrue(self.heard(a, "vp1234", Q, **b)["wait"])         # nothing ignored in the trial
        room.set_voice(uid, "vp1234", "", "Das ist ein Satz von mir", known=True)
        self.heard(a, "vp1234", "Das ist ein Satz von mir", **b)
        out = a.post("/api/room/stop", json={"room": "vp1234"}).json()["summary"]
        self.assertIn("Probelauf: Von 2 Sätzen hätte ich 1 als fremde Stimme überhört.", [x["text"] for x in out])
        log = json.dumps(a.get("/api/profile/toollog").json(), ensure_ascii=False)
        self.assertIn("fremde Stimme", log)
        self.assertNotIn("180 Grad", log)                                # never what was heard

    def test_voice_checked_only_when_needed(self):
        a, uid = profile("Viola")
        self.assertTrue(room.needs_voice(uid, "vn1234"))                 # first sentence: setting not known yet
        self.heard(a, "vn1234", "Hallo zusammen", voices="all")
        self.assertFalse(room.needs_voice(uid, "vn1234"))
        self.heard(a, "vn1234", "Hallo zusammen", voices="tv")
        self.assertTrue(room.needs_voice(uid, "vn1234"))
        helpers.set_config(speaker_id=False)
        self.assertFalse(room.needs_voice(uid, "vn1234"))
        # a known voice never creates a room for an odd room id
        room.set_voice(uid, "../x", "", "Hallo", known=True)
        self.assertNotIn((uid, "../x"), room.ROOMS)

    def test_speaker_settings_checked(self):
        import esp32
        self.assertEqual(esp32.room_cfg({"room_voices": "rm -rf"})["voices"], "all")
        self.assertTrue(esp32.room_cfg({})["probe"])
        c = esp32.room_cfg({"room_voices": "tv", "room_probe": False})
        self.assertEqual((c["voices"], c["probe"]), ("tv", False))


if __name__ == "__main__":
    unittest.main()
