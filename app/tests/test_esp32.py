"""Own ESP32 speakers (esp32.py): firmware from a fake GitHub release, the board's start check (OTA),
pairing by code and over USB, and a whole spoken question over the WebSocket like the XiaoZhi firmware."""
import asyncio
import ctypes
import hashlib
import ipaddress
import json
import os
import time
import unittest
import unittest.mock

import numpy as np

from tests import helpers

helpers.start()
import panel  # noqa: E402
import esp32  # noqa: E402
import features  # noqa: E402
import netguard  # noqa: E402
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
_GH_BEFORE = None


def setUpModule():
    # set when this module's tests run, not at import: unittest imports every test module first, and
    # another module may change the variable in between (the real GitHub had newer firmware, CI red)
    global _GH_BEFORE
    _GH_BEFORE = os.environ.get("SPEECH_SPARK_GITHUB_API")
    os.environ["SPEECH_SPARK_GITHUB_API"] = f"http://127.0.0.1:{GH_PORT}"


def tearDownModule():
    if _GH_BEFORE is None:
        os.environ.pop("SPEECH_SPARK_GITHUB_API", None)
    else:
        os.environ["SPEECH_SPARK_GITHUB_API"] = _GH_BEFORE


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


def ota(client_id, base="https://testserver", client=("testclient", 50000), mac=None, **kw):
    """The board's start check; over https by default (firmware goes out over Wi-Fi only there, Paket 4 M8)."""
    b = board_hello(client_id, **kw)
    if mac is not None:
        b["headers"]["Device-Id"] = mac
    return TestClient(panel.app, base_url=base, client=client).post("/api/esp32/ota/", headers=b["headers"], json=b["json"])


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

    def test_signed_manifest_once_a_key_exists(self):
        """Paket 4 (M8): with a public key in signatur.KEYS a firmware release needs a valid manifest.json.sig;
        unsigned or signed by another key it is refused and the kept firmware stays. Without a key nothing changes."""
        import base64
        import signatur
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        old = signatur.KEYS
        signatur.KEYS = (pub,)
        try:
            release("2.5.1.5")
            r = ADMIN.post("/api/admin/esp32/fetch")
            self.assertEqual(r.status_code, 400)
            self.assertIn("nicht signiert", r.json()["detail"])
            FILES["manifest.json.sig"] = base64.b64encode(other.sign(FILES["manifest.json"]))
            self.assertIn("passt nicht", ADMIN.post("/api/admin/esp32/fetch").json()["detail"])
            FILES["manifest.json.sig"] = b"%%%" * 40
            self.assertIn("ungültig", ADMIN.post("/api/admin/esp32/fetch").json()["detail"])
            self.assertEqual(esp32.manifest()["version"], "2.5.1.2")
            FILES["manifest.json.sig"] = base64.b64encode(key.sign(FILES["manifest.json"]))
            self.assertEqual(ADMIN.post("/api/admin/esp32/fetch").status_code, 200)
            self.assertEqual(esp32.manifest()["version"], "2.5.1.5")
        finally:
            signatur.KEYS = old
            release("2.5.1.2")
            self.assertEqual(asyncio.run(esp32.fetch_firmware()), "2.5.1.2")

    def test_board_id_bound_to_its_board_and_address(self):
        """Paket 4 (N20): a known board id from another board (MAC) gets nothing and changes nothing; the key
        after the code goes only to the address that showed the code; a wrong challenge is refused."""
        cid = "21111111-2222-4333-8444-555555555555"
        act = ota(cid, fw="2.5.1.1").json()["activation"]
        h = {"Client-Id": cid}
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/esp32/ota/activate", headers=h, json={"challenge": "0" * 32}).status_code, 403)
        self.assertEqual(c.post("/api/esp32/ota/activate", headers=h, json={"challenge": 5}).status_code, 403)
        self.assertEqual(c.post("/api/esp32/ota/activate", headers=h, json={"challenge": act["challenge"]}).status_code, 202)
        a = profile("Esp Nora")
        self.assertEqual(a.post("/api/profile/esp32/pair", json={"code": act["code"], "name": "Flur"}).status_code, 200)
        self.assertEqual(c.post("/api/esp32/ota/activate", headers=h, json={"algorithm": "hmac-sha256",
                                                                            "challenge": act["challenge"]}).status_code, 200)
        # another address asks first: no key for it, and the key stays for the board
        far = ota(cid, fw="2.5.1.1", client=("10.9.9.9", 50000)).json()
        self.assertNotIn("token", far["websocket"])
        # another board with the same id: refused, the record keeps the first board's firmware
        self.assertEqual(ota(cid, fw="0.0.1", mac="11:22:33:44:55:66").status_code, 403)
        mine = ota(cid, fw="2.5.1.1").json()
        self.assertTrue(mine["websocket"]["token"].startswith("sd_"))
        self.assertNotIn("token", ota(cid, fw="2.5.1.2").json()["websocket"])
        self.assertEqual(ota(cid, fw="2.5.1.2", mac="AA:BB:CC:DD:EE:FF").status_code, 200)   # same MAC, other case
        did = a.get("/api/profile/esp32").json()["devices"][0]["id"]
        self.assertEqual(a.delete(f"/api/profile/esp32/{did}").status_code, 200)

    def test_firmware_over_wifi_only_with_https(self):
        """Paket 4 (M8): over http anyone in the network could hand the board another file, so the start check
        offers no update there unless the admin allows it (chat.esp32_ota_http); the night round skips such boards."""
        import geraeteupdate
        cid = "31111111-2222-4333-8444-555555555555"
        act = ota(cid, fw="2.5.1.1").json()["activation"]
        helpers.set_config(esp32_ota_http=False)   # on by default (speakers on http keep updating)
        a = profile("Esp Paul")
        self.assertEqual(a.post("/api/profile/esp32/pair", json={"code": act["code"], "name": "Bad"}).status_code, 200)
        plain = ota(cid, fw="2.5.1.1", base="http://192.168.1.5:31080").json()
        self.assertTrue(plain["websocket"]["token"].startswith("sd_"))
        self.assertEqual(plain["firmware"]["url"], "")
        s = next(x for x in a.get("/api/profile/esp32").json()["devices"] if x["name"] == "Bad")
        self.assertTrue(s["plain"])
        self.assertFalse(esp32.ota_allowed(True))
        self.assertTrue(esp32.ota_allowed(False))
        try:
            helpers.set_config(esp32_ota_http=True)
            self.assertTrue(esp32.ota_allowed(True))
            self.assertTrue(ota(cid, fw="2.5.1.1", base="http://192.168.1.5:31080").json()["firmware"]["url"]
                            .startswith("http://192.168.1.5:31080/api/esp32/fw/2.5.1.2/"))
        finally:
            helpers.set_config(esp32_ota_http=True)
        self.assertIn("esp32_ota_http", " ".join(f"{a}.{b}" for a, b in __import__("admin").SENSITIVE))
        self.assertIn("esp32.ota_allowed(s.get(\"plain\"))", open(geraeteupdate.__file__).read())
        self.assertNotEqual(ota(cid, fw="2.5.1.1").json()["firmware"]["url"], "")   # https: offered
        self.assertEqual(a.delete(f"/api/profile/esp32/{s['id']}").status_code, 200)

    def test_firmware_two_checks_at_once(self):
        """The daily check, Geräte-Updates and the admin's button at the same moment: one after the other, each in
        its own temporary folder, nothing half written left behind (Dominik 2026-10-11: "No such file … .part/…")."""
        release("2.5.1.4")

        async def both():
            return await asyncio.gather(esp32.fetch_firmware(), esp32.fetch_firmware())
        self.assertEqual(asyncio.run(both()), ["2.5.1.4", "2.5.1.4"])
        self.assertEqual(esp32.manifest()["version"], "2.5.1.4")
        self.assertEqual([x for x in os.listdir(esp32.FW_DIR) if ".part" in x], [])
        release("2.5.1.2")
        self.assertEqual(asyncio.run(esp32.fetch_firmware()), "2.5.1.2")

    def test_failed_check_shows_no_path_or_server_text(self):
        async def broken(c, url, size):
            raise OSError("[Errno 2] No such file or directory: '/var/lib/speech-spark/firmware/x.part/y.bin'")
        release("2.5.1.4")
        orig = esp32._download
        esp32._download = broken
        try:
            err = asyncio.run(esp32.check())
            r = ADMIN.post("/api/admin/esp32/fetch")
        finally:
            esp32._download = orig
            release("2.5.1.2")
        self.assertNotIn("/var/lib", err)
        self.assertIn("Einzelheiten im Log", err)
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("/var/lib", r.text)
        self.assertEqual(esp32.manifest()["version"], "2.5.1.2")
        self.assertEqual([x for x in os.listdir(esp32.FW_DIR) if ".part" in x], [])

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
        # the admin blocks the profile: no pairing; released: works at once
        self.addCleanup(helpers.set_config, deny={})
        helpers.set_config(deny={"esp32": [a.get("/api/whoami").json()["profile"]["id"]]})
        self.assertEqual(a.post("/api/profile/esp32/pair", json={"code": act["code"], "name": "Küche"}).status_code, 403)
        helpers.set_config(deny={})
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
    def test_open_connection_ends_when_switched_off_under_wer_darf_was(self):
        """Rights arrive at once (V01.0.388): an open speaker connection looks at the switches again and ends
        when the admin turns the profile's speakers off, not only at the next connect."""
        a = profile("Esp Rita")
        uid = next(u["id"] for u in esp32.profiles._load()["users"] if u["name"] == "Esp Rita")
        s = a.post("/api/profile/esp32/setup", json={"name": "Keller", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        dev = esp32.device_for_token(s["token"])
        self.assertTrue(esp32.still_allowed(dev))
        old = esp32.RECHECK
        esp32.RECHECK = 0
        try:
            with TestClient(panel.app).websocket_connect("/api/esp32/ws", headers={
                    "Authorization": "Bearer " + s["token"], "Protocol-Version": "1", "Client-Id": s["uuid"]}) as ws:
                ws.send_text(json.dumps({"type": "hello", "version": 1, "transport": "websocket",
                                         "audio_params": {"format": "opus", "sample_rate": 16000, "channels": 1, "frame_duration": 60}}))
                self.assertEqual(json.loads(ws.receive_text())["type"], "hello")
                r = ADMIN.put(f"/api/admin/features/esp32/profiles/{uid}", json={"on": False})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertFalse(esp32.still_allowed(dev))
                ws.send_text(json.dumps({"type": "ping"}))
                with self.assertRaises(WebSocketDisconnect):
                    while True:
                        ws.receive_text()
        finally:
            esp32.RECHECK = old
        # on again, but the device is gone: not allowed either
        ADMIN.put(f"/api/admin/features/esp32/profiles/{uid}", json={"on": True})
        self.assertTrue(esp32.still_allowed(dev))
        a.delete(f"/api/profile/esp32/{s['device']}")
        self.assertFalse(esp32.still_allowed(dev))

    @unittest.skipUnless(_has_opus(), "libopus missing")
    def test_setup_over_usb_and_talk(self):
        a = profile("Esp Carla")
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
        # blocked for the profile by the admin: the key no longer connects
        self.addCleanup(helpers.set_config, deny={})
        helpers.set_config(deny={"esp32": [a.get("/api/whoami").json()["profile"]["id"]]})
        with self.assertRaises(WebSocketDisconnect):
            with c.websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer " + s["token"]}) as ws:
                ws.receive_text()

    def test_diagnosis(self):
        a = profile("Esp Dora")
        s = a.post("/api/profile/esp32/setup", json={"name": "Flur", "variant": "bread-compact-wifi",
                                                     "base": "https://192.168.1.5:31443"}).json()
        did = s["device"]
        d = a.get(f"/api/profile/esp32/{did}/diag").json()
        self.assertEqual(d["base"], "https://192.168.1.5:31443")
        text = " ".join(c["text"] for c in d["checks"] if c["ok"] is False)
        self.assertIn("noch nie", text)
        self.assertIn("selbst signiertes", text)
        # only the own profile in its browser
        self.assertEqual(profile("Esp Emil").get(f"/api/profile/esp32/{did}/diag").status_code, 404)
        self.assertEqual(TestClient(panel.app).get(f"/api/profile/esp32/{did}/diag",
                                                   headers={"X-Speech-Device": s["token"]}).status_code, 403)
        # the start check and a refused connection show up with their reason
        ota(s["uuid"])
        c = TestClient(panel.app)
        with self.assertRaises(WebSocketDisconnect):
            with c.websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer sd_wrong", "Client-Id": s["uuid"]}) as ws:
                ws.receive_text()
        d = a.get(f"/api/profile/esp32/{did}/diag").json()
        ev = [e["text"] for e in d["events"]]
        self.assertTrue(ev[0].startswith("Verbindung abgelehnt: Schlüssel unbekannt"), ev)
        self.assertTrue(any(e.startswith("Start-Prüfung vom Board: Firmware 2.5.1.1") for e in ev), ev)
        self.assertTrue(any(x["ok"] and "gemeldet" in x["text"] for x in d["checks"]))
        # the probe WebSocket says only which Spark it is
        with c.websocket_connect("/api/esp32/ws", headers={"x-spark-probe": "1"}) as ws:
            self.assertEqual(json.loads(ws.receive_text()), {"type": "probe", "spark": esp32.PROBE})
        self.assertEqual(c.get("/api/esp32/ping").json(), {"spark": esp32.PROBE})
        # "Netz prüfen": at most NET_CHECKS in ten minutes per profile
        asked = []

        async def check(base, hier=""):
            asked.append(base)
            return [(False, "nicht erreichbar")]
        old, esp32.net_check = esp32.net_check, check
        try:
            for _ in range(esp32.NET_CHECKS):
                r = a.post(f"/api/profile/esp32/{did}/check", json={})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["results"], [{"ok": False, "text": "nicht erreichbar"}])
            self.assertEqual(a.post(f"/api/profile/esp32/{did}/check", json={}).status_code, 429)
        finally:
            esp32.net_check = old
        self.assertEqual(asked, ["https://192.168.1.5:31443"] * esp32.NET_CHECKS)   # only the speaker's own address
        self.assertIn("Netz geprüft: nicht erreichbar", [e["text"] for e in a.get(f"/api/profile/esp32/{did}/diag").json()["events"]])
        a.delete(f"/api/profile/esp32/{did}")
        self.assertNotIn(did, esp32._diag)

    def test_board_type_follows_the_board(self):
        """A board rewritten over USB with another variant gets that variant's updates; a board without
        display (reports its base build) keeps its own."""
        a = profile("Esp Greta")
        s = a.post("/api/profile/esp32/setup", json={"name": "Bad2", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        real = esp32.manifest()
        app = lambda f: {"label": f, "parts": [], "app": {"file": f + "__xiaozhi.bin"}}
        fake = {"version": "9.9.9.9", "variants": {"bread-compact-wifi": app("bread-compact-wifi"),
                                                   "bread-compact-wifi-nodisplay": app("bread-compact-wifi-nodisplay"),
                                                   "esp32-s3-audio-board": app("esp32-s3-audio-board")}}
        old, esp32.manifest = esp32.manifest, lambda: fake
        try:
            r = ota(s["uuid"], variant="esp32-s3-audio-board").json()
            self.assertTrue(r["firmware"]["url"].endswith("/esp32-s3-audio-board__xiaozhi.bin"), r)
            self.assertEqual(esp32.clients()[s["uuid"]]["variant"], "esp32-s3-audio-board")
            esp32._update(lambda d: d["clients"][s["uuid"]].update(variant="bread-compact-wifi-nodisplay"))
            r = ota(s["uuid"], variant="bread-compact-wifi").json()
            self.assertTrue(r["firmware"]["url"].endswith("/bread-compact-wifi-nodisplay__xiaozhi.bin"), r)
            r = ota(s["uuid"], variant="something-else").json()
            self.assertTrue(r["firmware"]["url"].endswith("/bread-compact-wifi-nodisplay__xiaozhi.bin"), r)
        finally:
            esp32.manifest = old
        self.assertEqual(esp32.manifest(), real)

    def test_volume_and_microphone(self):
        a = profile("Esp Hanna")
        s = a.post("/api/profile/esp32/setup", json={"name": "Garten", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        did = s["device"]
        for bad in ({"volume": 101}, {"volume": -1}, {"volume": "50"}, {"volume": True}, {"mic": "loud"}):
            self.assertEqual(a.put(f"/api/profile/esp32/{did}", json=bad).status_code, 400, bad)
        self.assertEqual(TestClient(panel.app).put(f"/api/profile/esp32/{did}", headers={"X-Speech-Device": s["token"]},
                                                   json={"volume": 10}).status_code, 403)
        r = a.put(f"/api/profile/esp32/{did}", json={"volume": 55, "mic": "high"})
        dev = next(x for x in r.json()["devices"] if x["id"] == did)
        self.assertEqual((dev["volume"], dev["mic"]), (55, "high"))
        # the board gets its volume at every connection; the microphone setting picks the speech level
        with TestClient(panel.app).websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer " + s["token"],
                                                                             "Client-Id": s["uuid"]}) as ws:
            ws.send_text(json.dumps({"type": "hello", "features": {"mcp": True}}))
            self.assertEqual(json.loads(ws.receive_text())["type"], "hello")
            m = json.loads(ws.receive_text())
            self.assertEqual(m["type"], "mcp")
            self.assertEqual(m["payload"]["params"], {"name": "self.audio_speaker.set_volume", "arguments": {"volume": 55}})
            self.assertEqual(esp32._live[did].new_ear().level, esp32.MIC_LEVELS["high"])
            a.put(f"/api/profile/esp32/{did}", json={"volume": 30})   # connected: at once
            self.assertEqual(json.loads(ws.receive_text())["payload"]["params"]["arguments"], {"volume": 30})

    def test_net_check(self):
        """The real way: HTTP and the WebSocket through a running server, like a board would."""
        port = helpers._port()
        only = FastAPI()   # the speaker routes alone: the whole panel would start its background jobs here
        only.include_router(esp32.router)
        helpers._serve(only, port)
        res = asyncio.run(esp32.net_check(f"http://127.0.0.1:{port}"))
        self.assertIn("localhost", res[0][1])   # a board never reaches 127.0.0.1: said, but still tried
        res = res[1:]
        self.assertTrue(res[0][0], res)
        try:
            import websockets  # noqa: F401
        except ImportError:
            try:
                import wsproto  # noqa: F401
            except ImportError:
                self.skipTest("no WebSocket library for uvicorn")
        self.assertEqual(len(res), 2, res)
        self.assertTrue(res[1][0], res)
        # another server at that address is not this Spark; a closed port and a wrong name say so
        other = asyncio.run(esp32.net_check(f"http://127.0.0.1:{helpers.LLM_PORT}"))
        self.assertFalse(other[-1][0])
        self.assertIn("127.0.0.1", other[-1][1])
        self.assertFalse(asyncio.run(esp32.net_check("http://spark.invalid"))[0][0])
        self.assertIn("Spark-Adresse", asyncio.run(esp32.net_check("http://spark.invalid"))[0][1])

    def test_its_own_address_is_not_called_a_mistake(self):
        """V01.0.644: after the move to the Pi, http://<Pi>:31080 (the address the speakers need) read as "zeigt auf
        seine eigenen Dienste oder ist nicht erlaubt"; the guard still refuses it, the text says why."""
        with unittest.mock.patch.object(netguard, "own_addresses", lambda: {ipaddress.ip_address("192.0.2.7")}):
            res = asyncio.run(esp32.net_check("http://192.0.2.7:31080"))
        self.assertFalse(res[-1][0])
        self.assertIn("Adresse dieses Rechners selbst", res[-1][1])
        self.assertIn("eigenen Dienste oder ist nicht erlaubt", esp32._blocked_text("http://192.0.2.8:31080"))

    def test_the_old_model_computer_address_is_named(self):
        """Dominik 2026-10-16: after the move the board still had http://<tars>:31080 and only read "prüft der Spark
        nicht"; the model computer's address now says so and names the panel's address, nothing is tried there."""
        import common
        with unittest.mock.patch.object(common, "model_host", lambda cfg=None: "192.0.2.71"), \
                unittest.mock.patch.object(common, "model_local", lambda cfg=None: False), \
                unittest.mock.patch.object(netguard, "model_addresses", lambda: {ipaddress.ip_address("192.0.2.71")}):
            res = asyncio.run(esp32.net_check("http://192.0.2.71:31080", "http://192.0.2.21:31080"))
            self.assertEqual(len(res), 1, res)
            self.assertFalse(res[0][0])
            self.assertIn("Modell-Rechners", res[0][1])
            self.assertIn("http://192.0.2.21:31080 eintragen", res[0][1])
            self.assertIn("<Pi-IP>", esp32._addr_hint("http://192.0.2.71:31080", "http://192.0.2.71:31080"))
            self.assertIsNone(esp32._addr_hint("http://192.0.2.21:31080", "http://192.0.2.21:31080"))
        self.assertIsNone(esp32._addr_hint("http://192.0.2.71:31080"))   # all on one Spark: no model computer

    @unittest.skipUnless(_has_opus(), "libopus missing")
    def test_speaker_test(self):
        a = profile("Esp Frieda")
        s = a.post("/api/profile/esp32/setup", json={"name": "Keller", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        did = s["device"]
        r = a.post(f"/api/profile/esp32/{did}/test", json={})
        self.assertEqual((r.status_code, r.json()["now"], r.json()["test"]), (200, False, True))

        async def tts(uid, text):
            yield np.zeros(2400, dtype="<i2").tobytes()

        async def heard(pcm):
            return "Eins zwei drei"
        old = esp32.tts_stream, esp32.transcribe
        esp32.tts_stream, esp32.transcribe = tts, heard
        try:
            with TestClient(panel.app).websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer " + s["token"],
                                                                                 "Client-Id": s["uuid"]}) as ws:
                ws.send_text(json.dumps({"type": "hello", "audio_params": {"format": "opus", "sample_rate": 16000}}))
                ws.receive_text()

                def until_stop():
                    texts = []
                    while True:
                        m = ws.receive()
                        if m.get("text") is None:
                            continue
                        e = json.loads(m["text"])
                        texts.append(e.get("text") or "")
                        if e["type"] == "tts" and e.get("state") == "stop":
                            return " ".join(texts)
                ws.send_text(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
                self.assertIn("Lautsprecher-Test", until_stop())
                t = np.arange(16000 * 1.2) / 16000
                voice = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2").tobytes()
                quiet = np.zeros(16000, dtype="<i2").tobytes()
                for fr in opus16k_frames(quiet[:9600] + voice + quiet):
                    ws.send_bytes(fr)
                self.assertIn("Das Mikrofon geht. Verstanden habe ich: Eins zwei drei", until_stop())
        finally:
            esp32.tts_stream, esp32.transcribe = old
        ev = [e["text"] for e in a.get(f"/api/profile/esp32/{did}/diag").json()["events"]]
        self.assertTrue(any(e.startswith("Mikrofon: ") and "Sprache gehört" in e for e in ev), ev)
        self.assertIn("Test: Mikrofon geht", ev)
        self.assertFalse(a.get(f"/api/profile/esp32/{did}/diag").json()["test"])   # only once

    @unittest.skipUnless(_has_opus(), "libopus missing")
    def test_stop_word_ends_without_an_answer(self):
        """"Stopp" (also "Jarvis, stopp" after the wake word interrupted it) ends: nothing goes to the language
        model, nothing is said, the board goes back to its wake word. A real question still gets its answer."""
        a = profile("Esp Stella")
        s = a.post("/api/profile/esp32/setup", json={"name": "Flur", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        for said in ("Stopp", "Jarvis, stopp!", "Danke, das reicht", "Hör auf"):
            self.assertTrue(esp32.STOP_WORDS.match(said), said)
        for said in ("Stopp die Musik", "Halt, wie spät ist es?", "Danke", "Wie spät ist es?"):
            self.assertFalse(esp32.STOP_WORDS.match(said), said)
        spoken = []

        async def tts(uid, text):
            spoken.append(text)
            yield np.zeros(2400, dtype="<i2").tobytes()

        async def heard(pcm):
            return "Stopp."
        old = esp32.tts_stream, esp32.transcribe
        esp32.tts_stream, esp32.transcribe = tts, heard
        try:
            with TestClient(panel.app).websocket_connect("/api/esp32/ws", headers={"Authorization": "Bearer " + s["token"],
                                                                                 "Client-Id": s["uuid"]}) as ws:
                ws.send_text(json.dumps({"type": "hello", "audio_params": {"format": "opus", "sample_rate": 16000}}))
                ws.receive_text()
                ws.send_text(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
                t = np.arange(16000 * 1.2) / 16000
                voice = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2").tobytes()
                quiet = np.zeros(16000, dtype="<i2").tobytes()
                for fr in opus16k_frames(quiet[:9600] + voice + quiet):
                    ws.send_bytes(fr)
                kinds = []
                with self.assertRaises(WebSocketDisconnect):
                    while True:
                        m = ws.receive()
                        if m.get("type") == "websocket.close":
                            raise WebSocketDisconnect(m.get("code", 1000))
                        if m.get("text") is not None:
                            kinds.append(json.loads(m["text"])["type"])
                self.assertNotIn("stt", kinds)
                self.assertNotIn("llm", kinds)
                self.assertNotIn("tts", kinds)
        finally:
            esp32.tts_stream, esp32.transcribe = old
        self.assertEqual(spoken, [])
        ev = [e["text"] for e in a.get(f"/api/profile/esp32/{s['device']}/diag").json()["events"]]
        self.assertTrue(any(e.startswith("Stopp gehört") for e in ev), ev)

    def test_stop_while_speaking_needs_both_switches(self):
        """"Stopp beim Vorlesen" (espstopp) is off: no word to the board, nothing heard while it speaks. Released by the
        admin the board is asked at every connection, and told "off" again once the admin blocks the profile."""
        a = profile("Esp Selma")
        s = a.post("/api/profile/esp32/setup", json={"name": "Diele", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        hdr = {"Authorization": "Bearer " + s["token"], "Client-Id": s["uuid"]}

        def stop_calls():
            calls = []
            with TestClient(panel.app).websocket_connect("/api/esp32/ws", headers=hdr) as ws:
                ws.send_text(json.dumps({"type": "hello", "audio_params": {"format": "opus", "sample_rate": 16000}}))
                ws.receive_text()
                ws.send_text(json.dumps({"type": "listen", "state": "detect", "text": "jarvis"}))
                time.sleep(0.3)   # the hello's MCP calls go out after its answer
                s_ = esp32._live.get(s["device"])
                calls.append(s_.stop_on if s_ else None)
            return calls
        sent = []
        real = esp32.Session.send_stop_word

        async def spy(self, on):
            sent.append(on)
            await real(self, on)
        esp32.Session.send_stop_word = spy
        try:
            self.assertFalse(features.admin_on("espstopp"))
            self.assertEqual((stop_calls(), sent), ([False], []))           # off: as before, nothing sent
            helpers.set_config(esp32_stop=True)                             # released: works at once
            self.assertTrue(a.get("/api/profile/esp32").json()["stop"]["enabled"])
            self.assertEqual((stop_calls(), sent), ([True], [True]))
            helpers.set_config(deny={"espstopp": [a.get("/api/whoami").json()["profile"]["id"]]})   # admin blocks
            self.assertEqual((stop_calls(), sent), ([False], [True, False]))   # told off once
            self.assertEqual((stop_calls(), sent), ([False], [True, False]))   # then nothing again
        finally:
            esp32.Session.send_stop_word = real
            helpers.set_config(esp32_stop=False, deny={})

    def test_stop_heard_while_speaking(self):
        """Only a stop phrase ends the answer: the board gets "tts stop" with spark_quiet (drops its queue) and the
        Spark listens again. The phrase in its own sentence is its echo; other words never stop it."""
        sent = []

        class WS:
            async def send_text(self, t):
                sent.append(json.loads(t))

            async def send_bytes(self, b):
                pass
        dev = {"id": "d_stop", "user": "u_stop", "name": "Test"}
        heard = {"text": ""}

        async def asr(pcm):
            return heard["text"]

        async def run(text, spoken=()):
            sent.clear()
            heard["text"] = text
            ses = esp32.Session(WS(), "t", dev, "c_stop")
            ses.stop_on = True
            for x in spoken:
                await ses.send({"type": "tts", "state": "sentence_start", "text": x})
            sent.clear()
            ses.answer = asyncio.ensure_future(asyncio.sleep(30))
            await ses.check_stop(b"\0" * 32000)
            stopped = ses.answer.cancelled()
            ses.answer.cancel()
            return stopped, ses.ear is not None, sent
        old = esp32.transcribe
        esp32.transcribe = asr
        try:
            stopped, listens, out = asyncio.run(run("Stopp!"))
            self.assertTrue(stopped and listens)
            self.assertEqual(out, [{"type": "tts", "state": "stop", "spark_quiet": True, "session_id": out[0]["session_id"]}])
            self.assertEqual(asyncio.run(run("Hör auf, bitte."))[:2], (True, True))
            self.assertEqual(asyncio.run(run("Wie spät ist es?"))[:2], (False, False))     # no stop phrase
            self.assertEqual(asyncio.run(run("Stopp die Musik"))[:2], (False, False))
            self.assertEqual(asyncio.run(run("Halt", ["Das ist halt so."]))[:2], (False, False))   # its own echo
            self.assertEqual(asyncio.run(run("Halt", ["Morgen wird es sonnig."]))[:2], (True, True))
            self.assertEqual(asyncio.run(run(""))[:2], (False, False))
        finally:
            esp32.transcribe = old

    def test_stop_ear_cuts_short_pieces(self):
        """Sound while it speaks: quiet before a word is kept to half a second, a piece is at most STOP_PIECE long."""
        ses = esp32.Session(None, "t", {"id": "d_ear", "user": "u", "name": "T"}, "c_ear")
        jobs = []

        async def fake(seg):
            jobs.append(len(seg))
        ses.check_stop = fake

        async def go():
            quiet = np.zeros(960, dtype="<i2").tobytes()
            loud = (np.sin(np.arange(960) / 3) * 8000).astype("<i2").tobytes()
            for _ in range(60):
                ses.hear_stop(quiet)
            self.assertLessEqual(len(ses.stop_ear.pcm), 32000 + 1920)
            for _ in range(10):
                ses.hear_stop(loud)
            for _ in range(15):
                ses.hear_stop(quiet)
            await asyncio.sleep(0)
            for _ in range(120):
                ses.hear_stop(loud)
            await asyncio.sleep(0)
        asyncio.run(go())
        self.assertEqual(len(jobs), 2, jobs)
        self.assertLess(jobs[0], 1.8 * 32000)
        self.assertLessEqual(jobs[1], (esp32.STOP_PIECE + 0.1) * 32000)

    def test_live_counts_speakers_listening_for_stop(self):
        import live

        class S:
            stop_on, answer = True, None
        a, b = S(), S()

        async def go():
            a.answer = asyncio.ensure_future(asyncio.sleep(5))
            b.stop_on = False
            b.answer = asyncio.ensure_future(asyncio.sleep(5))
            with unittest.mock.patch.object(esp32, "_live", {"x": a, "y": b}):
                n = {c["name"]: c["n"] for c in live._conns(time.time())}
            a.answer.cancel()
            b.answer.cancel()
            return n
        n = asyncio.run(go())
        self.assertEqual((n.get("Lautsprecher"), n.get("Lautsprecher hört auf „Stopp“")), (2, 1))

    @unittest.skipUnless(_has_opus(), "libopus missing")
    def test_room_mode_on_a_speaker(self):
        import room
        helpers.set_config(room=True)
        a = profile("Esp Rosa")
        s = a.post("/api/profile/esp32/setup", json={"name": "Wohnzimmer", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        did = s["device"]
        heard = []

        async def asr(pcm):
            return heard.pop(0) if heard else ""

        async def tts(uid, text):
            yield b"\0" * 4800      # 0.1 s
        old = esp32.transcribe, esp32.tts_stream, room.night
        esp32.transcribe, esp32.tts_stream = asr, tts
        room.night = lambda uid, local=None: False      # never the real clock
        t = np.arange(16000 * 1.0) / 16000
        voice = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2").tobytes()
        quiet = np.zeros(16000, dtype="<i2").tobytes()
        c = TestClient(panel.app)
        hdr = {"Authorization": "Bearer " + s["token"], "Protocol-Version": "1", "Client-Id": s["uuid"]}

        def said(ws):
            """Texts the board shows until the next tts stop."""
            out = []
            while True:
                m = ws.receive()
                if m.get("type") == "websocket.close":
                    raise WebSocketDisconnect(1000)
                if m.get("bytes") is not None:
                    continue
                e = json.loads(m["text"])
                if e["type"] == "tts" and e.get("state") == "sentence_start":
                    out.append(e["text"])
                if e["type"] == "tts" and e.get("state") == "stop":
                    return out

        def talk(ws, text, mode="auto"):
            heard.append(text)
            ws.send_text(json.dumps({"type": "listen", "state": "start", "mode": mode}))
            for fr in opus16k_frames(quiet[:9600] + voice + quiet):
                ws.send_bytes(fr)

        def hello(ws):
            ws.send_text(json.dumps({"type": "hello", "version": 1, "transport": "websocket"}))
            json.loads(ws.receive_text())
        try:
            # by voice: on, a question answered in the pause after the tone, off by voice
            with c.websocket_connect("/api/esp32/ws", headers=hdr) as ws:
                hello(ws)
                talk(ws, "Raummodus an")
                self.assertIn("Ich höre 30 Minuten zu", said(ws)[0])
                dev = a.get("/api/profile/esp32").json()["devices"][0]
                self.assertTrue(dev["room"] and dev["room_until"])
                # a speaker profile cannot be switched by a device key
                self.assertEqual(TestClient(panel.app).put(f"/api/profile/esp32/{did}", headers={"X-Speech-Device": s["token"]},
                                                           json={"room": False}).status_code, 403)
                talk(ws, "Wie viel sind 180 Grad in Fahrenheit?")
                self.assertIn("Fahrenheit", said(ws)[0])
                self.assertTrue(any(k[0] == a.get("/api/whoami").json()["profile"]["id"] for k in room.ROOMS))
                # one piece with several sentences, the question without "?": answered, looked up only once
                import proactive
                asked, llm = [], proactive._llm

                async def fake(system, user, max_tokens=300):
                    asked.append(user)
                    return "Die Zugspitze ist 2962 Meter hoch." if "Frage:" in user else "NICHTS"
                proactive._llm = fake
                try:
                    for r in room.ROOMS.values():
                        r["said"] = 0
                    talk(ws, "Wir waren gestern am See. Wie hoch ist die Zugspitze")
                    self.assertIn("2962", said(ws)[0])
                    self.assertEqual(sum(1 for x in asked if "Frage:" in x), 1)
                finally:
                    proactive._llm = llm
                talk(ws, "Raummodus aus")
                self.assertEqual(said(ws), ["Raum-Modus aus."])
                with self.assertRaises(WebSocketDisconnect):
                    said(ws)
            uid = a.get("/api/whoami").json()["profile"]["id"]
            self.assertFalse(any(k[0] == uid for k in room.ROOMS))      # what was heard is gone
            self.assertFalse(a.get("/api/profile/esp32").json()["devices"][0]["room"])
            # the switch while the speaker sleeps: starts at its next wake word, then off from the panel
            a.put(f"/api/profile/esp32/{did}", json={"room": True, "room_mins": 15, "room_level": "questions",
                                                     "room_area": "Wohnzimmer<b>"})
            dev = a.get("/api/profile/esp32").json()["devices"][0]
            self.assertEqual((dev["room_waits"], dev["room_mins"], dev["room_level"], dev["room_area"]),
                             (True, 15, "questions", "Wohnzimmerb"))
            with c.websocket_connect("/api/esp32/ws", headers=hdr) as ws:
                hello(ws)
                ws.send_text(json.dumps({"type": "listen", "state": "detect", "text": "Jarvis"}))
                ws.send_text(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
                self.assertIn("Ich höre 15 Minuten zu", said(ws)[0])
                self.assertFalse(a.get("/api/profile/esp32").json()["devices"][0]["room_waits"])
                a.put(f"/api/profile/esp32/{did}", json={"room": False})
                self.assertEqual(said(ws), ["Raum-Modus aus."])
            # at most ROOM_MAX speakers at once
            fake = type("S", (), {"room": {"rid": "x"}})()
            for i in range(esp32.ROOM_MAX):
                esp32._live[f"fake{i}"] = fake
            try:
                with c.websocket_connect("/api/esp32/ws", headers=hdr) as ws:
                    hello(ws)
                    talk(ws, "Raummodus an")
                    self.assertIn("zu viele", said(ws)[0])
            finally:
                for i in range(esp32.ROOM_MAX):
                    esp32._live.pop(f"fake{i}", None)
            # admin switch off: no room mode, also not by voice
            helpers.set_config(room=False)
            self.assertEqual(a.put(f"/api/profile/esp32/{did}", json={"room": True}).status_code, 403)
            with c.websocket_connect("/api/esp32/ws", headers=hdr) as ws:
                hello(ws)
                talk(ws, "Raummodus an")
                self.assertIn("ausgeschaltet", said(ws)[0])
        finally:
            esp32.transcribe, esp32.tts_stream, room.night = old
            helpers.set_config(room=False)
        # in the quiet hours a speaker in room mode stays silent (it has no text to show)
        room.night = lambda uid, local=None: True
        try:
            sess = esp32.Session(None, "", {"user": "u", "id": "d", "name": "x"}, "")
            sess.room_say("Hallo")
            self.assertIsNone(sess.answer)
        finally:
            room.night = old[2]

    @unittest.skipUnless(_has_opus(), "libopus missing")
    def test_teach_voice_through_the_speaker(self):
        import speakers
        helpers.set_config(speaker_id=True)
        a = profile("Esp Vera")
        s = a.post("/api/profile/esp32/setup", json={"name": "Flur", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        did, uid = s["device"], a.get("/api/whoami").json()["profile"]["id"]
        board = np.zeros(256, np.float32)
        board[0] = 1.0
        old = speakers.embed, esp32.tts_stream

        async def tts(uid, text):
            yield b"\0" * 4800
        speakers.embed, esp32.tts_stream = (lambda x, **kw: board), tts
        try:
            # never with the speaker's own key: a voiceprint decides whose "Ja" counts
            self.assertEqual(TestClient(panel.app).post(f"/api/profile/esp32/{did}/voice", headers={"X-Speech-Device": s["token"]},
                                                        json={}).status_code, 403)
            self.assertFalse(speakers.device_known(did))
            self.assertFalse(a.post(f"/api/profile/esp32/{did}/voice", json={}).json()["now"])   # asleep: at its next wake word
            self.assertTrue(a.get("/api/profile/esp32").json()["devices"][0]["voice_waits"])
            t = np.arange(16000 * 1.5) / 16000
            voice = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2").tobytes()
            quiet = np.zeros(16000 * 2, dtype="<i2").tobytes()
            with TestClient(panel.app).websocket_connect("/api/esp32/ws", headers={
                    "Authorization": "Bearer " + s["token"], "Protocol-Version": "1", "Client-Id": s["uuid"]}) as ws:
                ws.send_text(json.dumps({"type": "hello", "version": 1, "transport": "websocket"}))
                json.loads(ws.receive_text())
                ws.send_text(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
                texts = []

                def until_stop():
                    while True:
                        m = ws.receive()
                        if m.get("bytes") is not None:
                            continue
                        e = json.loads(m["text"])
                        if e["type"] == "tts" and e.get("state") == "sentence_start":
                            texts.append(e["text"])
                        if e["type"] == "tts" and e.get("state") == "stop":
                            return
                until_stop()
                self.assertIn("fünf Sätze", texts[-1])
                for _ in range(5):
                    for fr in opus16k_frames(quiet[:9600] + voice + quiet):
                        ws.send_bytes(fr)
                until_stop()
                self.assertIn("erkenne deine Stimme", texts[-1])
            self.assertEqual(len(speakers.device_samples(uid)[did]), 5)
            self.assertTrue(speakers.device_known(did) and speakers.has_voice(uid))
            self.assertEqual(a.get("/api/profile/esp32").json()["devices"][0]["voice_here"], 5)
            # its own voiceprint next to the browser one: a recording through the board matches the profile
            browser = np.zeros(256, np.float32)
            browser[1] = 1.0
            __import__("profiles")._write(speakers._file(uid), dict(speakers._read(uid), samples=[browser.tolist()]))
            self.assertEqual(len(speakers.voiceprints()[uid]), 2)
            dec = speakers.decode
            speakers.decode = lambda data: np.zeros(16000, np.float32)
            try:
                who, best = speakers.identify(b"x", 0.75)
            finally:
                speakers.decode = dec
            self.assertEqual((who, round(best, 3)), (uid, 1.0))
        finally:
            speakers.embed, esp32.tts_stream = old
            speakers.forget(uid)
            helpers.set_config(speaker_id=False)

    def test_known_voices_only_once_taught_here(self):
        import speakers
        sess = esp32.Session(None, "", {"user": "nobody", "id": "dev-x", "name": "x"}, "")
        sess.room = {"rid": "espdevx"}
        old = esp32.room_cfg, speakers.device_known
        esp32.room_cfg = lambda c: {"level": "hints", "area": "", "detect": False, "voices": "known", "probe": False, "mins": 30}
        try:
            speakers.device_known = lambda did: False
            self.assertEqual(sess._room_body()["voices"], "all")     # nobody taught a voice here: listens to all
            speakers.device_known = lambda did: True
            self.assertEqual(sess._room_body()["voices"], "known")
        finally:
            esp32.room_cfg, speakers.device_known = old

    def test_speaker_page_settings(self):
        """Ich → Lautsprecher, one speaker's page: what the room mode may offer (checked and passed on to room
        mode), the readable board name, and the speaker's key marked (and not moved) elsewhere."""
        a = profile("Esp Lotte")
        s = a.post("/api/profile/esp32/setup", json={"name": "Flur", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        did = s["device"]
        dev = next(x for x in a.get("/api/profile/esp32").json()["devices"] if x["id"] == did)
        self.assertEqual(dev["board"], "Steckbrett")
        self.assertTrue(all(dev["room_kinds"].values()))   # everything allowed until switched off
        for bad in ({"room_kinds": {"evil": True}}, {"room_kinds": {"shop": "no"}}, {"room_kinds": {"shop": 0}}):
            self.assertEqual(a.put(f"/api/profile/esp32/{did}", json=bad).status_code, 400, bad)
        self.assertEqual(TestClient(panel.app).put(f"/api/profile/esp32/{did}", headers={"X-Speech-Device": s["token"]},
                                                   json={"room_kinds": {"shop": False}}).status_code, 403)
        a.put(f"/api/profile/esp32/{did}", json={"room_kinds": {"shop": False}})
        dev = next(x for x in a.put(f"/api/profile/esp32/{did}", json={"room_kinds": {"cal": False}}).json()["devices"] if x["id"] == did)
        self.assertEqual({k for k, v in dev["room_kinds"].items() if not v}, {"shop", "cal"})
        sess = esp32.Session(None, "", {"user": dev["user"], "id": did, "name": "Flur"}, s["uuid"])
        sess.room = {"rid": "espflur"}
        import room
        self.assertFalse(room._kinds(sess._room_body())["shop"])
        self.assertTrue(room._kinds(sess._room_body())["q"])
        # the speaker's key: marked under Profile und Geräte and Ich → Sicherheit, and it stays with its profile
        self.assertTrue(next(x for x in ADMIN.get("/api/admin/profiles").json()["devices"] if x["id"] == did)["speaker"])
        self.assertTrue(next(x for x in a.get("/api/profile/security").json()["devices"] if x["id"] == did)["speaker"])
        other = profile("Esp Lotte Zwei")
        uid2 = next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == "Esp Lotte Zwei")
        self.assertEqual(ADMIN.put(f"/api/admin/devices/{did}", json={"user": uid2}).status_code, 400)
        del other

    def test_admin_address_check(self):
        """Funktionen → Eigene Lautsprecher → „Adresse prüfen“: admin only, checked like the board's way, limited."""
        self.assertIn(TestClient(panel.app).post("/api/admin/esp32/check", json={"base": "http://spark.invalid"}).status_code, (401, 403))
        self.assertEqual(ADMIN.post("/api/admin/esp32/check", json={"base": "http://x/../etc"}).status_code, 400)
        esp32._net_tries.pop("admin", None)
        r = ADMIN.post("/api/admin/esp32/check", json={"base": "http://spark.invalid"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["results"][0]["ok"])
        esp32._net_tries["admin"] = [time.time()] * esp32.NET_CHECKS
        self.assertEqual(ADMIN.post("/api/admin/esp32/check", json={"base": "http://spark.invalid"}).status_code, 429)
        esp32._net_tries.pop("admin", None)

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

    def test_sound_is_buffered(self):
        """The board gets ~0.6 s before it starts, never more than ~1 s ahead, and a refill after a stall."""
        sent = []

        async def send(fr):
            sent.append(time.monotonic())

        async def run():
            pace = esp32.Pacer(send)
            pace.FRAME, pace.LEAD, pace.PRIME, pace.REFILL = 0.01, 0.05, 0.04, 0.03
            await pace.push([b"a"] * 2)          # 20 ms ready: still waiting
            self.assertEqual(len(sent), 0)
            await pace.push([b"a"] * 3)          # 50 ms ready: starts
            self.assertEqual(len(sent), 5)
            await asyncio.sleep(0.08)            # TTS falls behind, the board runs dry
            await pace.push([b"a"])
            self.assertEqual((len(sent), pace.stalls), (5, 1))
            await pace.push([b"a"] * 30)         # refilled: goes on, but paced
            t = time.monotonic()
            await pace.finish()
            self.assertEqual(len(sent), 36)
            self.assertGreater(sent[-1] - sent[6], 0.15)
            self.assertGreaterEqual(time.monotonic() - t, 0.05)
            last = esp32.Pacer(send)
            await last.push([b"b"], final=True)  # a short last bit goes out at once
            self.assertEqual(len(sent), 37)
        asyncio.run(run())

    def test_end_of_question(self):
        ear = esp32.Ear()
        quiet = np.zeros(960, dtype="<i2").tobytes()
        loud = (np.sin(np.arange(960) / 3) * 6000).astype("<i2").tobytes()
        self.assertIsNone(ear.feed(quiet))
        for _ in range(8):
            self.assertIsNone(ear.feed(loud))
        res = [ear.feed(quiet) for _ in range(15)]
        self.assertIn("done", res)
        # a quiet board (about -40 dB) still counts as speech, and is brought up for the recognition
        ear = esp32.Ear()
        soft = (np.sin(np.arange(960) / 3) * 450).astype("<i2").tobytes()
        self.assertIsNone(ear.feed(quiet))
        for _ in range(8):
            ear.feed(soft)
        self.assertIn("done", [ear.feed(quiet) for _ in range(15)])
        up = np.frombuffer(esp32.louder(soft), dtype="<i2")
        self.assertGreater(int(np.max(np.abs(up))), 8000)
        self.assertEqual(esp32.louder(loud * 0 + quiet), quiet)
        self.assertTrue(esp32.geraeteupdate.newer("2.5.1.10", "2.5.1.9"))
        self.assertFalse(esp32.geraeteupdate.newer("2.5.1", "2.5.1.0"))
        self.assertFalse(esp32.geraeteupdate.newer("abc", "1.0"))


class SharedSpeaker(unittest.TestCase):
    """A speaker in a room is shared: personal things only for the voice clearly recognized as the
    profile's own in this very recording; anyone else gets what a guest gets (fixed rule, no switch)."""

    @classmethod
    def setUpClass(cls):
        helpers.set_config(esp32=True)
        release("2.5.1.2")
        r = ADMIN.post("/api/admin/esp32/fetch")
        assert r.status_code == 200, r.text

    def setUp(self):
        import mail
        mail.IMAP = helpers.FakeIMAP
        mail._cache.clear()
        helpers.set_config(esp32=True, mail=True, public=True)

    def tearDown(self):
        helpers.set_config(mail=False, speaker_id=False)

    def speaker(self, name):
        a = profile(name)
        r = a.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        self.assertEqual(r.status_code, 200, r.text)
        r = a.post("/api/profile/esp32/setup", json={"name": "Wohnzimmer", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"})
        self.assertEqual(r.status_code, 200, r.text)
        s = r.json()
        ota(s["uuid"])
        return a, s["token"], a.get("/api/whoami").json()["profile"]["id"]

    def turn(self, token, text, voice=None, history=(), why="test"):
        """One turn prepared like esp32.speak builds it (voice None: not set, like any outside request)."""
        import chat_turn
        from starlette.requests import Request
        data = json.dumps({"messages": list(history) + [{"role": "user", "content": text}], "client": "speaker"}).encode()
        scope = {"type": "http", "method": "POST", "path": "/api/chat", "query_string": b"",
                 "headers": [(b"x-speech-device", token.encode())], "client": ("speaker", 0),
                 "server": ("127.0.0.1", 0), "scheme": "http"}
        if voice is not None:
            scope.update(speech_voice=voice, speech_voice_why=why)

        async def receive():
            return {"type": "http.request", "body": data, "more_body": False}
        return asyncio.run(chat_turn.prepare(Request(scope, receive)))

    @staticmethod
    def names(t):
        return {x["function"]["name"] for x in t.tools}

    def test_other_voice_gets_no_mail(self):
        import chat
        a, token, uid = self.speaker("Esp Inhaber")
        _, _, other = self.speaker("Esp Gast")
        # the reported case: the speaker's key, a voice nobody recognized -> no mail, no memory, no profile
        for voice in ("", other, None):
            t = self.turn(token, "Was steht in meinen E-Mails?", voice)
            self.assertIsNone(t.who)
            self.assertFalse(t.mailbox or t.prof or t.ha or t.docs)
            self.assertFalse(self.names(t) & {"mail_list", "mail_search", "mail_read", "memory_save", "memory_forget",
                                               "reminder_set", "calendar_events", "calendar_add", "history_search", "document_search"})
            self.assertIn(chat.SHARED_STRANGER_HINT, t.messages[0]["content"])
        # the journal (Zustand → Logs, Lautsprecher) says that and why, never what was asked
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.turn(token, "Was steht in meinen E-Mails?", "")
        line = next(x for x in out.getvalue().splitlines() if "withheld" in x)
        self.assertTrue(line.startswith("esp32: personal data withheld at Wohnzimmer"), line)
        self.assertNotIn("E-Mails", line)
        # over HTTP with the speaker's key (nothing can say whose voice it was): never the mail tool
        r = TestClient(panel.app).post("/api/chat", headers={"X-Speech-Device": token},
                                       json={"messages": [{"role": "user", "content": "TOOL mail_list {}"}]})
        self.assertIn("NO TOOL mail_list", "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text"))
        # a request that only says it comes from a speaker: stricter, never more
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "TOOL mail_list {}"}], "client": "speaker"})
        self.assertIn("NO TOOL mail_list", "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text"))
        # what the owner heard before at this speaker is not sent along for another voice
        before = [{"role": "user", "content": "Lies meine Mails"},
                  {"role": "assistant", "content": "Anna schreibt: Grillen am Samstag um 18 Uhr."}]
        t = self.turn(token, "Und was noch?", "", before)
        self.assertNotIn("Grillen", json.dumps(t.messages))
        # the owner's own voice, recognized in this recording: the mail tools as before
        t = self.turn(token, "Was steht in meinen E-Mails?", uid)
        self.assertEqual(t.who["id"], uid)
        self.assertTrue(t.mailbox)
        self.assertIn("mail_list", self.names(t))
        self.assertNotIn(chat.SHARED_STRANGER_HINT, t.messages[0]["content"])
        # the profile's own login in a browser is not a shared device
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "TOOL mail_list {}"}]})
        self.assertNotIn("NO TOOL", "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text"))

    def test_voice_decides_at_the_speaker(self):
        import speakers
        a, token, uid = self.speaker("Esp Vera")
        dev = {"id": next(x["id"] for x in profiles_devices() if x["user"] == uid), "user": uid, "name": "Wohnzimmer"}
        s = esp32.Session.__new__(esp32.Session)
        s.dev = dev

        def found(v):
            async def run():
                vt = asyncio.get_running_loop().create_future()
                vt.set_result(v)
                return (await s.voice_result(vt))[:2]
            return asyncio.run(run())
        base = {"ok": False, "why": "", "score": 0.0, "other": -1.0, "need": 0.75, "seconds": 0.0, "here": 0}
        # speaker ID off or no voice taught: nobody counts as the owner
        self.assertEqual(asyncio.run(s.voice_result(s.voice_check(b"\0" * 32000)))[0], "")
        helpers.set_config(speaker_id=True)
        self.assertEqual(asyncio.run(s.voice_result(s.voice_check(b"\0" * 32000))),
                         ("", "the profile has not taught its voice", None))
        self.assertEqual(found(dict(base, ok=True, score=0.9, seconds=2.0))[0], uid)
        voice, why = found(dict(base, why="voice not recognized", score=0.68, other=0.4, seconds=1.4, here=5))
        self.assertEqual(voice, "")
        # the journal gets the numbers, so a too strict check can be seen
        self.assertEqual(why, "voice not recognized (match 0.68 of 0.75 needed, other profiles 0.40, 1.4 s speech, taught here 5)")

    def test_verify_owner_voice(self):
        """speakers.verify: the owner's voiceprints against this recording, ahead of every other profile."""
        import speakers
        _, _, uid = self.speaker("Esp Walter")
        _, _, other = self.speaker("Esp Xaver")
        me, them = np.zeros(256, np.float32), np.zeros(256, np.float32)
        me[0], them[1] = 1.0, 1.0
        old = speakers.voiceprints, speakers.decode, speakers.embed
        speakers.decode = lambda data: np.ones(16000 * 2, np.float32) * 0.1
        try:
            speakers.voiceprints = lambda: {uid: [me], other: [them]}
            for heard, ok, why in ((me, True, ""), (them, False, "voice not recognized (voice not taught at this speaker)"),
                                   ((me * 0.75 + them * 0.72) / np.linalg.norm(me * 0.75 + them * 0.72), False,
                                    "too close to another profile's voice")):
                speakers.embed = lambda x, heard=heard: heard
                v = speakers.verify(uid, b"x", 0.7)
                self.assertEqual((v["ok"], v["why"]), (ok, why))
                self.assertNotIn("[", speakers.numbers(v))   # numbers only, never a voiceprint
            speakers.embed = lambda x: None
            self.assertEqual(speakers.verify(uid, b"x")["why"], "too little speech to check the voice")
            speakers.voiceprints = lambda: {other: [them]}
            self.assertEqual(speakers.verify(uid, b"x")["why"], "the profile has not taught its voice")
        finally:
            speakers.voiceprints, speakers.decode, speakers.embed = old

    def test_too_short_is_said(self):
        import chat
        _, token, _ = self.speaker("Esp Yvonne")
        t = self.turn(token, "Mails?", "", why="too little speech to check the voice")
        self.assertIn(chat.SHARED_SHORT_HINT, t.messages[0]["content"])


class SpeakerCode(unittest.TestCase):
    """Code word at a speaker (spkcode.py, plan plaene/lautsprecher-codewort.md): sure voice as before,
    grey zone or an implausible moment asks for the code word, a foreign voice never; the code word
    reaches no model, history or journal; three wrong ones lock asking for half an hour."""
    CODE = "Blaue Giraffe Sieben"

    @classmethod
    def setUpClass(cls):
        helpers.set_config(esp32=True)
        release("2.5.1.2")
        assert ADMIN.post("/api/admin/esp32/fetch").status_code == 200

    def setUp(self):
        helpers.set_config(esp32=True, speaker_id=True, speaker_code=True)

    def tearDown(self):
        helpers.set_config(speaker_id=False, speaker_code=False, deny={})

    def owner(self, name):
        a = profile(name)
        s = a.post("/api/profile/esp32/setup", json={"name": "Wohnzimmer", "variant": "bread-compact-wifi",
                                                     "base": "https://speech.example.de"}).json()
        uid = a.get("/api/whoami").json()["profile"]["id"]
        return a, s, uid

    @staticmethod
    def v(score, other=0.3, seconds=3.0, need=0.75):
        ok = score >= need and score - other >= 0.05
        return {"ok": ok, "why": "" if ok else "voice not recognized", "score": score, "other": other, "need": need,
                "seconds": seconds, "here": 5}

    def session(self, uid, did):
        s = esp32.Session.__new__(esp32.Session)
        s.dev, s.mode, s.said, s.spoken = {"id": did, "user": uid, "name": "Wohnzimmer"}, "auto", [], []

        async def say(text, tone=False):
            s.said.append(text)

        async def speak(text, voice="", why=""):
            s.spoken.append((text, voice))

        async def send(m):
            pass
        s.say, s.speak, s.send, s.listen, s.note = say, speak, send, (lambda m: None), (lambda x: None)
        return s

    def test_levels_are_fixed_rules(self):
        import spkcode
        _, s, uid = self.owner("Code Anke")
        did, now = s["device"], 1000.0
        self.assertEqual(spkcode.level(self.v(0.80), uid, did, now=now)[0], "sure")
        self.assertEqual(spkcode.level(self.v(0.70), uid, did, now=now)[0], "grey")
        self.assertEqual(spkcode.level(self.v(0.60), uid, did, now=now)[0], "foreign")       # too far below
        self.assertEqual(spkcode.level(self.v(0.70, other=0.72), uid, did, now=now)[0], "foreign")   # another profile fits better
        self.assertEqual(spkcode.level(None, uid, did, now=now)[0], "foreign")
        # a sure match in an implausible moment: grey
        self.assertEqual(spkcode.level(self.v(0.80, other=0.77), uid, did, now=now), ("grey", "another profile close behind"))
        self.assertEqual(spkcode.level(self.v(0.80, seconds=1.0), uid, did, now=now), ("grey", "short question"))
        self.assertEqual(spkcode.level(self.v(0.80), uid, did, foreign_at=now - 30, now=now),
                         ("grey", "unknown voice in the room just now"))
        self.assertEqual(spkcode.level(self.v(0.80), uid, did, foreign_at=now - 300, now=now)[0], "sure")
        self.assertTrue(spkcode.personal("Was steht in meinen Mails?"))
        self.assertTrue(spkcode.personal("Habe ich heute Termine im Kalender?"))
        self.assertFalse(spkcode.personal("Wie wird das Wetter morgen?"))

    def test_code_word_flow(self):
        import contextlib
        import io
        import spkcode
        a, s, uid = self.owner("Code Bernd")
        did = s["device"]
        # set only from the own browser, never with the speaker's key; weak ones refused; never sent back
        k = TestClient(panel.app).put("/api/profile/speaker-code", headers={"X-Speech-Device": s["token"]}, json={"code": self.CODE})
        self.assertEqual(k.status_code, 403)
        self.assertEqual(a.put("/api/profile/speaker-code", json={"code": "Giraffe"}).status_code, 400)
        r = a.put("/api/profile/speaker-code", json={"code": self.CODE})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("Giraffe", r.text + a.get("/api/profile/esp32").text)
        self.assertTrue(a.get("/api/profile/esp32").json()["code"]["has_code"])
        with open(spkcode._file(uid)) as f:
            self.assertNotIn("giraffe", f.read().lower())      # sealed in the vault
        se = self.session(uid, did)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            # a foreign voice is never asked
            voice, why, asked = asyncio.run(se.code_gate("Was steht in meinen Mails?", "", "x", self.v(0.55)))
            self.assertEqual((voice, asked), ("", False))
            self.assertIsNone(spkcode.waiting(did))
            # the grey zone and something personal: asked, the question waits
            voice, why, asked = asyncio.run(se.code_gate("Was steht in meinen Mails?", "", "x", self.v(0.70)))
            self.assertTrue(asked)
            self.assertEqual(se.said[-1], "Sag bitte dein Codewort.")
            self.assertTrue(spkcode.waiting(did))
            # the grey zone and nothing personal: no code word, nothing personal either
            voice, _, asked = asyncio.run(se.code_gate("Wie wird das Wetter?", "", "x", self.v(0.70)))
            self.assertEqual((voice, asked), ("", False))
            # a sure voice in a short question: nothing personal asked, the owner's rights as without the code
            # word (never stricter than off); something personal: asked for the code word
            self.assertEqual(asyncio.run(se.code_gate("Wie wird das Wetter?", uid, "", self.v(0.85, seconds=1.2))),
                             (uid, "", False))
            spkcode.forget(did)
            voice, _, asked = asyncio.run(se.code_gate("Was steht in meinen Mails?", uid, "", self.v(0.85, seconds=1.2)))
            self.assertEqual((voice, asked), ("", True))
            spkcode.forget(did)
            voice, _, asked = asyncio.run(se.code_gate("Was steht in meinen Mails?", "", "x", self.v(0.70)))
            self.assertTrue(asked)
            # the right code word (as speech recognition writes it): the waiting question with the profile's data
            asyncio.run(se.code_answer("blaue giraffe 7"))
            self.assertEqual(se.spoken[-1], ("Was steht in meinen Mails?", uid))
            # follow-ups at this speaker stay open for a while, for a voice that is at least close
            self.assertEqual(asyncio.run(se.code_gate("Und die nächste Mail?", "", "x", self.v(0.70)))[0], uid)
            self.assertEqual(asyncio.run(se.code_gate("Und die nächste Mail?", "", "x", self.v(0.50)))[0], "")
            spkcode.forget(did)
            # wrong code words: told, nothing answered; after three asking stops and the owner is told
            for i in range(3):
                asyncio.run(se.code_gate("Was steht in meinen Mails?", "", "x", self.v(0.70)))
                asyncio.run(se.code_answer("rote Katze acht"))
            self.assertIn("halbe Stunde", se.said[-1])
            self.assertTrue(spkcode.locked(uid, did))
            voice, why, asked = asyncio.run(se.code_gate("Was steht in meinen Mails?", "", "x", self.v(0.70)))
            self.assertEqual((voice, asked), ("", False))
            self.assertIn("locked", why)
        log = out.getvalue()
        self.assertIn("code word asked at Wohnzimmer", log)
        self.assertIn("code word right", log)
        self.assertIn("code word wrong at Wohnzimmer (1 of 3)", log)
        self.assertIn("code word locked", log)
        for word in ("giraffe", "katze", "blaue"):
            self.assertNotIn(word, log.lower())

    def test_waits_only_here_and_briefly(self):
        import spkcode
        _, s, uid = self.owner("Code Carla")
        spkcode.set_code(uid, self.CODE)
        did = s["device"]
        spkcode.ask(uid, did, "Meine Termine?", "short question", now=1000.0)
        self.assertIsNone(spkcode.waiting("other-speaker", now=1001.0))
        self.assertIsNone(spkcode.waiting(did, now=1000.0 + spkcode.WAIT))
        self.assertEqual(spkcode.attempt(uid, did, self.CODE, now=1000.0 + spkcode.WAIT), ("none", None))
        spkcode.ask(uid, did, "Meine Termine?", "short question", now=2000.0)
        self.assertEqual(spkcode.attempt(uid, did, "Blaue Giraffe Sieben", now=2010.0), ("right", "Meine Termine?"))
        self.assertTrue(spkcode.is_open(uid, did, now=2010.0 + spkcode.OPEN - 1))
        self.assertFalse(spkcode.is_open(uid, did, now=2010.0 + spkcode.OPEN))
        spkcode.forget(did)

    def test_off_means_as_before(self):
        import spkcode
        a, s, uid = self.owner("Code Dirk")
        spkcode.set_code(uid, self.CODE)
        se = self.session(uid, s["device"])
        # admin switch off, or on but the admin blocked this profile
        for cfg in ({"speaker_code": False, "deny": {}}, {"speaker_code": True, "deny": {"spkcode": [uid]}}):
            helpers.set_config(**cfg)
            self.assertFalse(spkcode.on(uid))
            # grey zone: guest rights as before, never asked
            self.assertEqual(asyncio.run(se.code_gate("Meine Mails?", "", "x", self.v(0.70))), ("", "x", False))
            # sure: as before
            self.assertEqual(asyncio.run(se.code_gate("Meine Mails?", uid, "", self.v(0.80)))[0], uid)
        self.assertIsNone(spkcode.waiting(s["device"]))


def profiles_devices():
    import profiles
    return profiles._load()["devices"]


if __name__ == "__main__":
    unittest.main()
