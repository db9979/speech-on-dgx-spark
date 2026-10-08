"""Own ESP32 speakers (esp32.py): firmware from a fake GitHub release, the board's start check (OTA),
pairing by code and over USB, and a whole spoken question over the WebSocket like the XiaoZhi firmware."""
import ctypes
import hashlib
import json
import os
import unittest

import numpy as np

from tests import helpers

helpers.start()
import panel  # noqa: E402
import esp32  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
GH_PORT = helpers._port()
FILES = {}          # release asset name -> bytes
GOOD = {"ok": True}


def release(version, bad=False):
    """A release fw-<version> with one board variant: partition table, app and its manifest."""
    FILES.clear()
    parts = {0x8000: b"\xaa\x50" + b"T" * 30, 0x20000: b"APP" + version.encode() * 100}
    plist = []
    for addr, data in parts.items():
        fn = f"bread-compact-wifi__{'partition-table' if addr == 0x8000 else 'xiaozhi'}.bin"
        FILES[fn] = data
        plist.append({"address": addr, "file": fn, "size": len(data),
                      "sha256": hashlib.sha256(b"x" if bad else data).hexdigest()})
    app = plist[1]
    FILES["manifest.json"] = json.dumps({"version": version, "variants": {"bread-compact-wifi": {
        "label": "Steckbrett", "flash": "16MB", "parts": plist, "app": app}}}).encode()


def fake_github():
    app = FastAPI()

    @app.get("/repos/{owner}/{name}/releases")
    def rels(owner: str, name: str):
        ver = json.loads(FILES["manifest.json"])["version"]
        return [{"tag_name": "v-other", "assets": []},
                {"tag_name": f"fw-{ver}", "draft": False, "prerelease": False,
                 "assets": [{"name": n, "browser_download_url": f"http://127.0.0.1:{GH_PORT}/dl/{n}"} for n in FILES]}]

    @app.get("/dl/{name}")
    def dl(name: str):
        return Response(FILES[name], media_type="application/octet-stream")
    return app


helpers._serve(fake_github(), GH_PORT)
os.environ["SPEECH_SPARK_GITHUB_API"] = f"http://127.0.0.1:{GH_PORT}"


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def board_hello(client_id, fw="2.5.1.1", variant="bread-compact-wifi"):
    """What the firmware sends at start (Ota::CheckVersion)."""
    return {"headers": {"Client-Id": client_id, "Device-Id": "aa:bb:cc:dd:ee:ff", "Activation-Version": "1"},
            "json": {"version": 2, "language": "de-DE", "application": {"name": "xiaozhi", "version": fw},
                     "board": {"type": "bread-compact-wifi", "name": variant}}}


def ota(client_id, **kw):
    b = board_hello(client_id, **kw)
    return TestClient(panel.app).post("/api/esp32/ota/", headers=b["headers"], json=b["json"])


def opus16k_frames(pcm):
    """60 ms Opus frames at 16 kHz, as the board sends them."""
    lib = esp32.Opus.lib()
    err = ctypes.c_int()
    enc = lib.opus_encoder_create(16000, 1, 2048, ctypes.byref(err))
    out = []
    for i in range(0, len(pcm) - 1919, 1920):
        buf = (ctypes.c_int16 * 960).from_buffer_copy(pcm[i:i + 1920])
        o = ctypes.create_string_buffer(4000)
        n = lib.opus_encode(enc, buf, 960, o, 4000)
        out.append(o.raw[:n])
    lib.opus_encoder_destroy(enc)
    return out


def _has_opus():
    try:
        esp32.Opus.lib()
        return True
    except OSError:
        return False


class Speakers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(esp32=True)
        release("2.5.1.2")
        r = ADMIN.post("/api/admin/esp32/fetch")
        assert r.status_code == 200, r.text

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(esp32=False)

    def test_firmware_checked_and_kept(self):
        self.assertEqual(esp32.manifest()["version"], "2.5.1.2")
        # a newer release with a wrong checksum is refused and the old one stays
        release("2.5.1.3", bad=True)
        r = ADMIN.post("/api/admin/esp32/fetch")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Prüfsumme", r.json()["detail"])
        self.assertEqual(esp32.manifest()["version"], "2.5.1.2")
        release("2.5.1.2")
        f = TestClient(panel.app).get("/api/esp32/fw/2.5.1.2/bread-compact-wifi__xiaozhi.bin")
        self.assertEqual(f.content, FILES["bread-compact-wifi__xiaozhi.bin"])
        self.assertEqual(TestClient(panel.app).get("/api/esp32/fw/2.5.1.2/manifest.json").status_code, 404)
        self.assertEqual(TestClient(panel.app).get("/api/esp32/fw/2.5.1.2/..%2Fcurrent.json").status_code, 404)

    def test_pair_by_code(self):
        cid = "11111111-2222-4333-8444-555555555555"
        r = ota(cid, fw="2.5.1.1")
        self.assertEqual(r.status_code, 200)
        act = r.json()["activation"]
        self.assertRegex(act["code"], r"^\d{6}$")
        self.assertNotIn("websocket", r.json())
        h = {"Client-Id": cid}
        self.assertEqual(TestClient(panel.app).post("/api/esp32/ota/activate", headers=h, json={}).status_code, 202)
        a = profile("Esp Anna")
        # off for the profile until it switches it on
        self.assertEqual(a.post("/api/profile/esp32/pair", json={"code": act["code"], "name": "Küche"}).status_code, 403)
        a.put("/api/profile/settings", json={"esp_on": True})
        self.assertEqual(a.post("/api/profile/esp32/pair", json={"code": "000000" if act["code"] != "000000" else "111111",
                                                                 "name": "Küche"}).status_code, 400)
        r = a.post("/api/profile/esp32/pair", json={"code": act["code"], "name": "Küche"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(TestClient(panel.app).post("/api/esp32/ota/activate", headers=h, json={}).status_code, 200)
        # next check: the server, the key once, and the newer firmware
        first = ota(cid, fw="2.5.1.1").json()
        self.assertTrue(first["websocket"]["url"].endswith("/api/esp32/ws"))
        self.assertTrue(first["websocket"]["token"].startswith("sd_"))
        self.assertEqual(first["firmware"]["version"], "2.5.1.2")
        self.assertTrue(first["firmware"]["url"].endswith("/api/esp32/fw/2.5.1.2/bread-compact-wifi__xiaozhi.bin"))
        again = ota(cid, fw="2.5.1.2").json()
        self.assertNotIn("token", again["websocket"])
        self.assertEqual(again["firmware"]["url"], "")
        lst = a.get("/api/profile/esp32").json()["devices"]
        self.assertEqual([(d["name"], d["fw"]) for d in lst], [("Küche", "2.5.1.2")])
        # auto updates off: an older board is not updated until "Aktualisieren"
        did = lst[0]["id"]
        a.put(f"/api/profile/esp32/{did}", json={"auto": False})
        self.assertEqual(ota(cid, fw="2.5.1.1").json()["firmware"]["url"], "")
        a.post(f"/api/profile/esp32/{did}/update")
        self.assertNotEqual(ota(cid, fw="2.5.1.1").json()["firmware"]["url"], "")
        self.assertEqual(ota(cid, fw="2.5.1.1").json()["firmware"]["url"], "")   # only once
        # another profile cannot touch it; removing it ends the key
        b = profile("Esp Bert")
        self.assertEqual(b.delete(f"/api/profile/esp32/{did}").status_code, 404)
        self.assertEqual(a.delete(f"/api/profile/esp32/{did}").status_code, 200)
        self.assertIn("activation", ota(cid).json())

    @unittest.skipUnless(_has_opus(), "libopus missing")
    def test_setup_over_usb_and_talk(self):
        a = profile("Esp Carla")
        a.put("/api/profile/settings", json={"esp_on": True})
        r = a.post("/api/profile/esp32/setup", json={"name": "Bad", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"})
        self.assertEqual(r.status_code, 200, r.text)
        s = r.json()
        self.assertEqual(s["ota_url"], "https://speech.example.de/api/esp32/ota/")
        self.assertEqual(s["ws_url"], "wss://speech.example.de/api/esp32/ws")
        self.assertEqual([p["address"] for p in s["parts"]], [0x8000, 0x20000])
        self.assertNotIn("password", json.dumps(s))
        # a device key (this speaker's or a Siri key) never sets up further speakers
        k = TestClient(panel.app).post("/api/profile/esp32/setup", headers={"X-Speech-Device": s["token"]},
                                       json={"name": "Y", "variant": "bread-compact-wifi", "base": "https://a.de"})
        self.assertEqual(k.status_code, 403)
        self.assertEqual(a.post("/api/profile/esp32/setup", json={"name": "X", "variant": "nope", "base": "https://a.de"}).status_code, 400)
        self.assertEqual(a.post("/api/profile/esp32/setup", json={"name": "X", "variant": "bread-compact-wifi",
                                                                  "base": "https://a.de/pfad"}).status_code, 400)
        # the board knows its client id from the settings block: no code, no key in the answer
        first = ota(s["uuid"]).json()
        self.assertNotIn("activation", first)
        self.assertNotIn("token", first["websocket"])

        c = TestClient(panel.app)
        with self.assertRaises(WebSocketDisconnect):
            with c.websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer sd_wrong"}) as ws:
                ws.receive_text()
        said = []

        async def heard(pcm):
            said.append(len(pcm))
            return "Wie spät ist es?"
        old = esp32.transcribe
        esp32.transcribe = heard
        try:
            with c.websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer " + s["token"],
                                                               "Protocol-Version": "1", "Client-Id": s["uuid"]}) as ws:
                ws.send_text(json.dumps({"type": "hello", "version": 1, "transport": "websocket",
                                         "audio_params": {"format": "opus", "sample_rate": 16000, "channels": 1, "frame_duration": 60}}))
                hello = json.loads(ws.receive_text())
                self.assertEqual((hello["type"], hello["audio_params"]["sample_rate"]), ("hello", 24000))
                ws.send_text(json.dumps({"session_id": hello["session_id"], "type": "listen", "state": "start", "mode": "auto"}))
                t = np.arange(16000 * 1.2) / 16000
                voice = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2").tobytes()
                quiet = np.zeros(16000, dtype="<i2").tobytes()
                for fr in opus16k_frames(quiet[:9600] + voice + quiet):
                    ws.send_bytes(fr)
                kinds, audio = [], 0
                while True:
                    m = ws.receive()
                    if m.get("bytes") is not None:
                        audio += 1
                        continue
                    e = json.loads(m["text"])
                    kinds.append((e["type"], e.get("state"), e.get("text")))
                    if e["type"] == "tts" and e.get("state") == "stop":
                        break
                self.assertEqual(kinds[0], ("stt", None, "Wie spät ist es?"))
                self.assertIn(("tts", "start", None), kinds)
                self.assertTrue(any(k[:2] == ("tts", "sentence_start") and k[2] for k in kinds), kinds)
                self.assertGreater(audio, 0)
                self.assertTrue(said and said[0] >= 16000)
        finally:
            esp32.transcribe = old
        convo = [x for x in a.get("/api/profile/convos").json() if str(x.get("id", "")).startswith("esp-")]
        self.assertTrue(convo and convo[0]["title"].startswith("Bad "), convo)
        # switched off for the profile: the key no longer connects
        a.put("/api/profile/settings", json={"esp_on": False})
        with self.assertRaises(WebSocketDisconnect):
            with c.websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer " + s["token"]}) as ws:
                ws.receive_text()

    def test_off_means_off(self):
        helpers.set_config(esp32=False)
        try:
            self.assertEqual(ota("22222222-2222-4333-8444-555555555555").status_code, 403)
            self.assertEqual(TestClient(panel.app).get("/api/esp32/fw/2.5.1.2/bread-compact-wifi__xiaozhi.bin").status_code, 403)
        finally:
            helpers.set_config(esp32=True)

    def test_limits(self):
        c = TestClient(panel.app)
        b = board_hello("33333333-2222-4333-8444-555555555555")
        # a code is never handed out on GET, bodies are small, one address holds only a few codes
        self.assertEqual(c.get("/api/esp32/ota/", headers=b["headers"]).status_code, 405)
        self.assertEqual(c.post("/api/esp32/ota/", headers=b["headers"], content=b"{" + b" " * 20000 + b"}").status_code, 413)
        esp32._pending.clear()
        for i in range(esp32.PENDING_PER_IP):
            self.assertEqual(ota(f"4444444{i}-2222-4333-8444-555555555555").status_code, 200)
        self.assertEqual(ota("55555555-2222-4333-8444-555555555555").status_code, 429)
        esp32._pending.clear()
        # firmware only from GitHub's download addresses
        self.assertTrue(esp32._allowed_download("https://github.com/db9979/speech-on-dgx-spark/releases/download/fw-2.5.1.1/a.bin"))
        for bad in ("http://github.com/a/b/releases/download/x/a.bin", "https://evil.example/a/b/releases/download/x/a.bin",
                    "https://github.com.evil.de/a/b/releases/download/x/a.bin", "http://127.0.0.1:80/x"):
            self.assertFalse(esp32._allowed_download(bad), bad)

    def test_end_of_question(self):
        ear = esp32.Ear()
        quiet = np.zeros(960, dtype="<i2").tobytes()
        loud = (np.sin(np.arange(960) / 3) * 6000).astype("<i2").tobytes()
        self.assertIsNone(ear.feed(quiet))
        for _ in range(8):
            self.assertIsNone(ear.feed(loud))
        res = [ear.feed(quiet) for _ in range(15)]
        self.assertIn("done", res)
        self.assertTrue(esp32.newer("2.5.1.10", "2.5.1.9"))
        self.assertFalse(esp32.newer("2.5.1", "2.5.1.0"))
        self.assertFalse(esp32.newer("abc", "1.0"))


if __name__ == "__main__":
    unittest.main()
