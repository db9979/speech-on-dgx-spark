"""Where room mode listens (roomlive.py): the list of pages and speakers, who sees it, who may end or extend
it, the room key for Home Assistant, the note when a speaker starts by voice, the history without text.
The clock is the test's own; speakers are sessions with a fake connection."""
import asyncio
import json
import unittest

from tests import helpers

helpers.start()
import esp32  # noqa: E402
import guard  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
import room  # noqa: E402
import roomlive  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = [1_900_000_000.0]


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def keyed(token):
    return TestClient(panel.app, headers={"X-Speech-Device": token})


class FakeWS:
    def __init__(self):
        self.sent, self.closed = [], False

    async def send_text(self, t):
        self.sent.append(json.loads(t))

    async def send_bytes(self, b):
        pass

    async def close(self, code=1000):
        self.closed = True


class RoomLive(unittest.TestCase):
    def setUp(self):
        helpers.set_config(room=True, room_ha=False, iphone=False, public=False)   # no guest access: keys alone count
        roomlive.clock = lambda: NOW[0]
        roomlive.ACTIVE.clear()
        roomlive._ENDED.clear()
        roomlive._TOLD.clear()
        guard._rate.clear()

    def tearDown(self):
        roomlive.clock = __import__("time").time
        helpers.set_config(room=False, room_ha=False, iphone=False)

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            chat = json.load(f)["chat"]
        self.assertIs(chat["room_ha"], False)
        for k in ("room_tell", "app_room"):
            self.assertIs(profiles.SETTINGS[k][0], False)
        helpers.set_config(room=False)
        a, _ = profile("Rl Aus")
        self.assertEqual(a.post("/api/room/start", json={"room": "aaaaaaaa"}).status_code, 403)
        self.assertEqual(a.get("/api/room/active").json()["rooms"], [])

    def test_page_listed_seen_and_gone(self):
        a, uid = profile("Rl Anna")
        b, _ = profile("Rl Bert")
        r = a.post("/api/room/start", json={"room": "page0001", "mins": 30, "name": "Küchen-Tablet<script>", "voices": "tv", "probe": True})
        self.assertEqual(r.status_code, 200, r.text)
        key = r.json()["key"]
        rooms = a.get("/api/room/active").json()["rooms"]
        self.assertEqual([x["name"] for x in rooms], ["Küchen-Tabletscript"])   # no markup characters
        self.assertEqual(rooms[0]["until"], int((NOW[0] + 1800) * 1000))
        self.assertNotIn("rid", rooms[0])
        # another profile sees nothing and cannot end it
        self.assertEqual(b.get("/api/room/active").json()["rooms"], [])
        self.assertEqual(b.post("/api/room/end", json={"key": key}).status_code, 404)
        self.assertEqual(b.post("/api/room/extend", json={"key": key, "mins": 30}).status_code, 404)
        # a sign of life keeps it; without one for ALIVE seconds it is gone (and in the history as such)
        NOW[0] += 120
        self.assertEqual(a.post("/api/room/alive", json={"room": "page0001"}).json()["key"], key)
        NOW[0] += roomlive.ALIVE + 1
        self.assertEqual(a.get("/api/room/active").json()["rooms"], [])
        hist = a.get("/api/room/history").json()["items"]
        self.assertEqual(hist[0]["why"], "lost")
        # after a restart the page adds itself again with the time it has left
        r = a.post("/api/room/alive", json={"room": "page0001", "left": 600, "name": "Tablet"}).json()
        self.assertEqual(r["until"], int((NOW[0] + 600) * 1000))
        # stopped at the page: gone, history without anything heard
        room.ROOMS[(uid, "page0001")] = dict(room._room(uid, "page0001"), lines=[(NOW[0], "geheim gesagt")])
        a.post("/api/room/stop", json={"room": "page0001"})
        self.assertEqual(a.get("/api/room/active").json()["rooms"], [])
        with open(roomlive._hist_file(uid)) as f:
            self.assertNotIn("geheim", f.read())

    def test_end_from_elsewhere_reaches_the_page(self):
        a, uid = profile("Rl Clara")
        key = a.post("/api/room/start", json={"room": "page0002"}).json()["key"]
        self.assertEqual(a.post("/api/room/end", json={"key": key}).json()["ended"], 1)
        self.assertTrue(a.post("/api/room/heard", json={"room": "page0002", "text": "Hallo"}).json()["end"])
        key = a.post("/api/room/start", json={"room": "page0003"}).json()["key"]
        a.post("/api/room/end", json={"all": True})
        self.assertTrue(a.post("/api/room/alive", json={"room": "page0003"}).json()["end"])
        self.assertEqual(a.get("/api/room/history").json()["items"][0]["why"], "panel")

    def test_extend_capped_and_only_in_the_browser(self):
        a, uid = profile("Rl Dora")
        key = a.post("/api/room/start", json={"room": "page0004", "mins": 240}).json()["key"]
        self.assertEqual(a.post("/api/room/extend", json={"key": key, "mins": 45}).status_code, 400)
        until = a.post("/api/room/extend", json={"key": key, "mins": 60}).json()["rooms"][0]["until"]
        self.assertEqual(until, int((NOW[0] + roomlive.LONGEST) * 1000))   # never more than 4 hours from now
        token = profiles.add_device("Skript", uid)
        self.assertEqual(keyed(token).post("/api/room/extend", json={"key": key, "mins": 15}).status_code, 403)

    def test_limits(self):
        a, _ = profile("Rl Emil")
        for i in range(roomlive.PER_PROFILE):
            self.assertEqual(a.post("/api/room/start", json={"room": f"lim{i:05d}"}).status_code, 200)
        self.assertEqual(a.post("/api/room/start", json={"room": "lim99999"}).status_code, 429)
        self.assertEqual(a.post("/api/room/start", json={"room": "../x"}).status_code, 400)
        self.assertEqual(a.post("/api/room/start", content=b"{" + b" " * 5000 + b"}").status_code, 413)
        self.assertEqual(a.post("/api/room/end", json={"key": "x;rm"}).status_code, 400)

    def test_iphone_app_sees_and_ends_only_with_its_switch(self):
        helpers.set_config(iphone=True)
        a, uid = profile("Rl Frida")
        a.put("/api/profile/settings", json={"app_on": True})
        key = a.post("/api/room/start", json={"room": "page0005", "name": "Bad"}).json()["key"]
        app = keyed(profiles.add_device("iPhone", uid, scope="app"))
        self.assertEqual(app.get("/api/room/active").status_code, 403)
        a.put("/api/profile/settings", json={"app_room": True})
        self.assertEqual(app.get("/api/iphone/hello").json()["rooms"], True)
        self.assertEqual([x["name"] for x in app.get("/api/room/active").json()["rooms"]], ["Bad"])
        # never starting or extending
        self.assertEqual(app.post("/api/room/start", json={"room": "page0006"}).status_code, 401)
        self.assertEqual(app.post("/api/room/extend", json={"key": key, "mins": 15}).status_code, 401)
        self.assertEqual(app.post("/api/room/end", json={"key": key}).status_code, 200)
        self.assertEqual(a.get("/api/room/history").json()["items"][0]["why"], "iphone")

    def test_home_assistant_room_key(self):
        a, uid = profile("Rl Gero")
        self.assertEqual(a.post("/api/profile/room/ha").status_code, 403)   # the admin did not allow it
        helpers.set_config(room_ha=True)
        token = a.post("/api/profile/room/ha").json()["token"]
        self.assertEqual(keyed(token).post("/api/profile/room/ha").status_code, 401)   # the key cannot make keys
        ha = keyed(token)
        a.post("/api/room/start", json={"room": "page0007", "name": "Wohnzimmer"})
        d = ha.get("/api/room/active").json()
        self.assertEqual((d["count"], d["first"]), (1, "Wohnzimmer"))
        # only these two paths: no chat, no profile data
        self.assertEqual(ha.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]}).status_code, 401)
        self.assertEqual(ha.get("/api/profile/settings").status_code, 401)
        self.assertEqual(ha.post("/api/room/end", json={"all": True}).json()["ended"], 1)
        self.assertEqual(a.get("/api/room/history").json()["items"][0]["why"], "ha")
        # a new key replaces the old one; switched off by the admin, the key reads nothing
        token2 = a.post("/api/profile/room/ha").json()["token"]
        self.assertEqual(keyed(token).get("/api/room/active").status_code, 401)
        helpers.set_config(room_ha=False)
        self.assertEqual(keyed(token2).get("/api/room/active").status_code, 401)

    def test_admin_sees_all_and_ends_all(self):
        a, _ = profile("Rl Hanna")
        b, _ = profile("Rl Ines")
        a.post("/api/room/start", json={"room": "page0008", "name": "Küche"})
        b.post("/api/room/start", json={"room": "page0009", "name": "Büro"})
        self.assertEqual(TestClient(panel.app).get("/api/admin/rooms").status_code, 401)
        self.assertEqual(a.get("/api/admin/rooms").status_code, 401)
        rooms = ADMIN.get("/api/admin/rooms").json()["rooms"]
        self.assertEqual({(x["profile"], x["name"]) for x in rooms}, {("Rl Hanna", "Küche"), ("Rl Ines", "Büro")})
        lst = ADMIN.get("/api/admin/profiles", params={"show": "room"}).json()["users"]
        self.assertEqual({u["name"] for u in lst}, {"Rl Hanna", "Rl Ines"})
        self.assertEqual(ADMIN.post("/api/admin/rooms/end", json={"all": True}).json()["ended"], 2)
        self.assertEqual(ADMIN.get("/api/admin/rooms").json()["rooms"], [])
        self.assertTrue(a.post("/api/room/alive", json={"room": "page0008"}).json()["end"])

    def test_speaker_listed_note_extend_end(self):
        helpers.set_config(esp32=True)
        NOW[0] = __import__("time").time()   # the speaker counts its minutes on the real clock
        a, uid = profile("Rl Jana")
        profiles.add_device("Küche", uid)
        did = next(x["id"] for x in profiles.own_devices(uid) if x["name"] == "Küche")
        sent = []

        async def fake_send(u, title, body, tag="", private=True):
            sent.append((u, body, tag))
            return 1
        old = push.send
        push.send = fake_send
        try:
            async def run():
                s = esp32.Session(FakeWS(), "", {"user": uid, "id": did, "name": "Küche"}, "")

                async def quiet(text, tone=False):
                    pass
                s.say, s.listen = quiet, (lambda mode: None)   # no sound, no Opus here
                await s.room_start(source="voice")
                await asyncio.sleep(0)
                self.assertEqual(sent, [])   # the note is off by default
                await s.room_end("test", code="voice")
                a.put("/api/profile/settings", json={"room_tell": True, "pro_quiet": False})
                room.night = lambda u, local=None: False
                await s.room_start(source="voice")
                await asyncio.sleep(0.05)
                self.assertEqual(len(sent), 1)
                self.assertEqual(sent[0][2], "room")
                self.assertIn("Küche", sent[0][1])
                rooms = roomlive.mine(uid)
                self.assertEqual((rooms[0]["kind"], rooms[0]["device"]), ("speaker", did))
                roomlive.extend(rooms[0]["key"], 30, uid)
                self.assertEqual(s.room["until"], roomlive.ACTIVE[(uid, s.room["rid"])]["until"])
                self.assertIn(did, roomlive.devices_listening())
                self.assertTrue(await roomlive.end(rooms[0]["key"], "admin"))
                self.assertIsNone(s.room)
                self.assertEqual(roomlive.mine(uid), [])
                # started again by voice within the hour: no second note
                await s.room_start(source="voice")
                await asyncio.sleep(0.05)
                self.assertEqual(len(sent), 1)
                await s.room_end("test")
            asyncio.run(run())
        finally:
            push.send = old
            room.night = _night
            helpers.set_config(esp32=False)
        whys = [x["why"] for x in roomlive.load_history(uid)]
        self.assertIn("admin", whys)

    def test_speaker_board_stop_answers_once(self):
        """In room mode a "listen stop" from the board is no second question: the piece goes to room mode only."""
        helpers.set_config(esp32=True)
        NOW[0] = __import__("time").time()
        a, uid = profile("Rl Ole")
        profiles.add_device("Flur", uid)
        did = next(x["id"] for x in profiles.own_devices(uid) if x["name"] == "Flur")

        async def run():
            s = esp32.Session(FakeWS(), "", {"user": uid, "id": did, "name": "Flur"}, "")
            pieces, answers = [], []

            async def quiet(text, tone=False):
                pass

            async def heard(pcm):
                pieces.append(len(pcm))

            async def answer(pcm):
                answers.append(pcm)
            s.say, s.room_heard, s.run_answer = quiet, heard, answer
            await s.room_start(source="voice")
            s.listen("auto")
            s.ear.pcm += b"\x01\x00" * 20000
            s.ear.heard = True
            await s.on_text({"type": "listen", "state": "stop"})
            s.start_answer(b"\x00\x00" * 16000)   # whatever else hands over a sentence: room mode only
            await asyncio.sleep(0.05)
            self.assertEqual(answers, [])
            self.assertEqual(len(pieces), 2)
            self.assertIsNotNone(s.ear)            # room mode keeps listening
            await s.room_end("test")
        asyncio.run(run())
        helpers.set_config(esp32=False)

    def test_history_kept_short(self):
        a, uid = profile("Rl Kai")
        for i in range(roomlive.HIST_MAX + 5):
            a.post("/api/room/start", json={"room": f"his{i:05d}"})
            a.post("/api/room/stop", json={"room": f"his{i:05d}", "why": "time"})
        self.assertEqual(len(a.get("/api/room/history").json()["items"]), roomlive.HIST_MAX)
        NOW[0] += roomlive.HIST_DAYS * 86400 + 1
        self.assertEqual(a.get("/api/room/history").json()["items"], [])


_night = room.night

if __name__ == "__main__":
    unittest.main()
