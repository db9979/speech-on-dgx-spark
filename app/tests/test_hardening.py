"""Security hardening from the second review (V01.0.105 on): every guard here has its own test.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import datetime
import io
import json
import os
import struct
import time
import unittest
import zipfile

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def repo_file(*parts):
    """A file next to app/ (install.sh, update.sh); the self-test during an update only has app/ itself."""
    path = os.path.join(ROOT, *parts)
    if not os.path.exists(path):
        raise unittest.SkipTest(f"{parts[-1]} is not part of this copy")
    return open(path).read()


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def device_key(client, name="Tablet"):
    uid = client.get("/api/whoami").json()["profile"]["id"]
    return ADMIN.post("/api/admin/devices", json={"name": name, "user": uid}).json()["token"]


def wav(rate, seconds_of_frames):
    """A 16-bit mono WAV whose header claims `rate`."""
    frames = b"\x00\x01" * seconds_of_frames
    hdr = b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return hdr + b"data" + struct.pack("<I", len(frames)) + frames


class Stage1(unittest.TestCase):
    def setUp(self):
        import guard
        guard.reset()

    tearDown = setUp

    def test_only_qwen_speech_models(self):
        cfg = ADMIN.get("/api/config").json()
        for sec, key in (("tts", "model"), ("asr", "model"), ("tts", "voicedesign_model")):
            bad = json.loads(json.dumps(cfg))
            bad[sec][key] = "evil/remote-code-model"
            self.assertEqual(ADMIN.put("/api/config", json=bad).status_code, 400, (sec, key))
        engine = open(os.path.join(ROOT, "app", "engine.sh")).read()
        self.assertIn("^Qwen/Qwen3-(ASR|TTS|ForcedAligner)-", engine)

    def test_sensitive_settings_need_the_code(self):
        import admin
        import mfa
        cfg = ADMIN.get("/api/config").json()
        real = mfa.enabled
        mfa.enabled = lambda who: who == mfa.ADMIN
        try:
            for sec, key in (("chat", "llm_url"), ("chat", "telegram_api"), ("chat", "search_url")):
                new = json.loads(json.dumps(cfg))
                new[sec][key] = "https://elsewhere.example/v1"
                self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 428, key)
            same = json.loads(json.dumps(cfg))
            same["chat"]["max_tokens"] = cfg["chat"]["max_tokens"]  # nothing sensitive changed
            self.assertEqual(ADMIN.put("/api/config", json=same).status_code, 200)
        finally:
            mfa.enabled = real
        self.assertIn(("chat", "llm_key"), admin.SENSITIVE)

    def test_llm_test_keeps_the_stored_key_home(self):
        import system
        sent = {}

        class Fake:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None):
                sent["auth"] = (headers or {}).get("Authorization")
                raise system.httpx.ConnectError("no")
        real = system.httpx.AsyncClient
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            key_before = json.load(f)["chat"].get("llm_key", "")
        helpers.set_config(llm_key="stored-secret-key")
        system.httpx.AsyncClient = Fake
        try:
            ADMIN.post("/api/setup/llm-test", json={"url": "https://evil.example/v1"})
        finally:
            system.httpx.AsyncClient = real
            helpers.set_config(llm_key=key_before)
        self.assertIsNone(sent.get("auth"))

    def test_backup_has_no_login_keys_and_needs_a_ticket(self):
        import backup
        profile("Backupa")
        profiles._secret()
        b = ADMIN.post("/api/backups").json()
        import tarfile
        with tarfile.open(backup.path_of(b["name"])) as t:
            names = t.getnames()
        self.assertNotIn("users/secret", names)
        self.assertFalse(any("admin-session" in n for n in names))
        self.assertEqual(ADMIN.get(f"/api/backups/{b['name']}").status_code, 403)
        url = ADMIN.post(f"/api/backups/{b['name']}/ticket").json()["url"]
        self.assertEqual(ADMIN.get(url).status_code, 200)

    def test_device_key_changes_no_connections(self):
        p = profile("Geraeta")
        key = device_key(p)
        dev = TestClient(panel.app)
        h = {profiles.DEVICE_HEADER: key}
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            chat = json.load(f)["chat"]
        before = {k: chat.get(k) for k in ("homeassistant", "calendar", "mail")}
        helpers.set_config(homeassistant=True, calendar=True, mail=True)
        try:
            for method, path, body in (
                    ("put", "/api/profile/homeassistant", {"url": "https://evil.example", "token": ""}),
                    ("put", "/api/profile/homeassistant/code", {"code": ""}),
                    ("post", "/api/profile/push", {"subscription": {}}),
                    ("post", "/api/profile/calendar", {"url": "https://evil.example/cal"}),
                    ("post", "/api/profile/mail", {"kind": "other"}),
                    ("post", "/api/profile/logout-all", {}),
                    ("delete", "/api/profile/memory", None),
                    ("put", "/api/profile/settings", {"speed": 1.0})):
                r = dev.request(method.upper(), path, json=body, headers=h)
                self.assertEqual(r.status_code, 403, (path, r.text))
            # talking to the assistant still works
            self.assertEqual(dev.get("/api/whoami", headers=h).json()["profile"]["name"], "Geraeta")
        finally:
            helpers.set_config(**before)

    def test_fast_recurrence_does_not_stall(self):
        import calendars
        z = datetime.timezone.utc
        txt = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
               "BEGIN:VEVENT\r\nUID:a\r\nDTSTART:20000101T000000Z\r\nRRULE:FREQ=SECONDLY\r\nSUMMARY:bomb\r\nEND:VEVENT\r\n"
               "BEGIN:VEVENT\r\nUID:b\r\nDTSTART:20000101T000000Z\r\nRRULE:FREQ=HOURLY\r\nSUMMARY:hourly\r\nEND:VEVENT\r\n"
               "BEGIN:VEVENT\r\nUID:c\r\nDTSTART:20260101T090000Z\r\nDTEND:20260101T100000Z\r\nRRULE:FREQ=DAILY\r\n"
               "SUMMARY:ok\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        s = datetime.datetime(2026, 10, 8, tzinfo=z)
        t = time.time()
        r = calendars._expand([txt], s, s + datetime.timedelta(hours=12), z)
        self.assertLess(time.time() - t, 2)
        self.assertEqual([x["title"] for x in r], ["ok"])

    def test_wav_with_made_up_rate(self):
        import speakers
        with self.assertRaises(ValueError):
            speakers.decode(wav(1, 1000))
        x = speakers.decode(wav(48000, 48000 * 200))
        self.assertLessEqual(len(x), speakers.SR * speakers.MAX_SECONDS + 1)

    def test_docx_bomb(self):
        import documents
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", b"<w:p>" + b" " * (documents.MAX_UNPACKED + 10) + b"</w:p>")
        self.assertLess(len(buf.getvalue()), documents.MAX_FILE)
        with self.assertRaises(ValueError):
            documents.extract("bomb.docx", buf.getvalue())

    def test_bodies_refused_before_reading(self):
        guest = TestClient(panel.app)
        # no login: a big upload is refused before a byte of it is read
        r = guest.post("/api/backups-upload", content=b"x" * 1000,
                       headers={"content-type": "application/octet-stream", "content-length": "1000"})
        self.assertEqual(r.status_code, 401)
        # too large for its path, whoever sends it
        r = ADMIN.post("/api/login", content=b"{" + b" " * (70 * 1024) + b"}", headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 413)
        r = ADMIN.put("/api/config", content=b"{" + b" " * (3 * 1024**2) + b"}", headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_message_id_cannot_carry_commands(self):
        import tidy
        self.assertEqual(tidy.clean_mid("<abc@example.com>"), "<abc@example.com>")
        for bad in ("<a\r\nX UID STORE 1:* +FLAGS (\\Deleted)>", '<a"b@x>', "a@b", "<@>", "<a\\b@x>", "<" + "a" * 300 + ">"):
            self.assertEqual(tidy.clean_mid(bad), "", bad)

    def test_rollback_only_to_the_kept_previous_version(self):
        sh = repo_file("update.sh")
        self.assertIn('if [ "$new" != "$prev" ] || ! git merge-base --is-ancestor "$SECURITY_FLOOR" "$new"', sh)
        self.assertIn('[ ! -L "$STATE/update-target" ]', sh)

    def test_units_have_memory_limits(self):
        sh = repo_file("install.sh")
        self.assertIn("MemoryMax=4G", sh)
        self.assertIn("PrivateTmp=yes", sh)


if __name__ == "__main__":
    unittest.main()
