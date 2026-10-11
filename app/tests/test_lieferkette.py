"""Unabhängige Prüfung, Paket 4 (updates and supply chain): signed manifests, the speech APIs without a key,
ffmpeg only on local input, the ASR gate before the upload is read, Telegram downloads with a limit and a checked
path, and the iPhone app never switching Spark quietly. (The shell scripts: test_hardening; workflows:
test_workflows; firmware and Begleiter fetches: test_esp32, test_begleiter.)"""
import asyncio
import base64
import inspect
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401  (sets up the panel's import path)

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def _key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    return k, base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()


class Signature(unittest.TestCase):
    """M8: signatur.verify is off without a key and fails closed with one."""

    def test_off_without_a_key_and_strict_with_one(self):
        import signatur
        self.assertEqual(signatur.KEYS, ())          # nothing is required until Dominik made a key
        signatur.verify(b"anything", None)
        key, pub = _key()
        other, _ = _key()
        data = b'{"version": "1.0.400"}'
        old = signatur.KEYS
        signatur.KEYS = (pub,)
        try:
            self.assertTrue(signatur.required())
            signatur.verify(data, base64.b64encode(key.sign(data)) + b"\n")
            for sig in (None, b"", b"not base64 !", base64.b64encode(b"x" * 63), base64.b64encode(other.sign(data)),
                        base64.b64encode(key.sign(data + b" ")), b"A" * 5000):
                with self.assertRaises(signatur.SignatureError, msg=sig):
                    signatur.verify(data, sig)
            with self.assertRaises(signatur.SignatureError):
                signatur.verify(data + b" ", base64.b64encode(key.sign(data)))
            signatur.KEYS = ("dG9vIHNob3J0",)
            with self.assertRaises(signatur.SignatureError):
                signatur.verify(data, base64.b64encode(key.sign(data)))
        finally:
            signatur.KEYS = old


class ApiKey(unittest.TestCase):
    """N16: an empty api.key leaves the speech APIs open only to this machine, not to the network."""

    def _app(self):
        from common import api_key_dependency
        from fastapi import Depends, FastAPI
        app = FastAPI()

        @app.get("/v1/x", dependencies=[Depends(api_key_dependency())])
        def x():
            return {"ok": True}
        return app

    def test_empty_key_only_for_this_machine(self):
        from common import api_key_ok
        from fastapi.testclient import TestClient
        app = self._app()
        self._set_key("")
        try:
            self.assertEqual(TestClient(app, client=("127.0.0.1", 5000)).get("/v1/x").status_code, 200)
            self.assertEqual(TestClient(app, client=("::1", 5000)).get("/v1/x").status_code, 200)
            self.assertEqual(TestClient(app, client=("192.168.1.20", 5000)).get("/v1/x").status_code, 401)
            self.assertTrue(api_key_ok({"client": ("127.0.0.1", 1), "headers": []}))
            self.assertFalse(api_key_ok({"client": ("10.0.0.2", 1), "headers": []}))
            self.assertFalse(api_key_ok({"headers": []}))
            self._set_key("sk-test")
            far = TestClient(app, client=("192.168.1.20", 5000))
            self.assertEqual(far.get("/v1/x").status_code, 401)
            self.assertEqual(far.get("/v1/x", headers={"Authorization": "Bearer sk-test"}).status_code, 200)
            self.assertEqual(TestClient(app, client=("127.0.0.1", 5000)).get("/v1/x").status_code, 401)
            self.assertTrue(api_key_ok({"client": ("10.0.0.2", 1), "headers": [(b"authorization", b"Bearer sk-test")]}))
        finally:
            self._set_key(self._before)

    def _set_key(self, key):
        import json
        path = os.environ["SPEECH_SPARK_CONFIG"]
        with open(path) as f:
            c = json.load(f)
        if not hasattr(self, "_before"):
            self._before = c["api"].get("key", "")
        c["api"]["key"] = key
        with open(path, "w") as f:
            json.dump(c, f)

    def test_install_gives_old_network_configs_a_key(self):
        path = os.path.join(ROOT, "install.sh")
        if not os.path.exists(path):
            self.skipTest("install.sh is not part of this copy")
        sh = read(path)
        self.assertIn("""if [ -z "$(cfgq -r '.api.key // ""')" ]""", sh)
        self.assertIn("""jqi --arg k "sk-$(head -c 24 /dev/urandom""", sh)


class Ffmpeg(unittest.TestCase):
    """N18: every ffmpeg/ffprobe call reads only local files or pipes (a playlist cannot fetch a URL)."""

    def test_protocol_whitelist_everywhere(self):
        calls = 0
        for folder in (APP, os.path.join(APP, "panel")):
            for name in sorted(os.listdir(folder)):
                if not name.endswith(".py"):
                    continue
                src = read(folder, name)
                for m in re.finditer(r'"(ffmpeg|ffprobe)",\s*"-', src):
                    calls += 1
                    rest = src[m.end():m.end() + 400]
                    i = rest.find('"-i"') if m.group(1) == "ffmpeg" else len(rest)
                    self.assertIn('"-protocol_whitelist", "file,pipe"', rest[:i], f"{name}: {m.group(0)}")
        self.assertGreaterEqual(calls, 7)


class AsrLimits(unittest.TestCase):
    """N17: the ASR proxy waits at its gate before it reads an upload of up to 200 MB into memory; parakeet decodes
    one recording at a time with few threads and a time limit."""

    def test_gate_before_reading(self):
        src = read(APP, "asr_proxy.py")
        body = src[src.index("async def transcriptions("):src.index("async def local_transcription(")]
        self.assertLess(body.index("await gate.enter("), body.index("await read_upload(upload)"))
        self.assertIn("gate.leave(ticket)\n        raise HTTPException(415, bad)", body)

    def test_parakeet_one_at_a_time(self):
        import parakeet
        src = inspect.getsource(parakeet.Recognizer.transcribe_file)
        self.assertLess(src.index("with self.lock:"), src.index("read_audio(path)"))
        reader = inspect.getsource(parakeet.read_audio)
        self.assertIn('"-threads", str(FFMPEG_THREADS)', reader)
        self.assertIn("timeout=FFMPEG_SECONDS", reader)
        self.assertLessEqual(parakeet.FFMPEG_THREADS, 4)


class TelegramFiles(unittest.TestCase):
    """N21: voice messages are downloaded like photos: streamed, cut off at the limit, file_path checked."""

    class Stream:
        def __init__(self, chunks):
            self.chunks = chunks

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        async def aiter_bytes(self):
            for c in self.chunks:
                yield c

    class Client:
        def __init__(self, chunks):
            self.chunks, self.urls = chunks, []

        def stream(self, method, url):
            self.urls.append(url)
            return TelegramFiles.Stream(self.chunks)

    def _run(self, result, chunks, limit=100):
        import telegram
        real = telegram.call

        async def call(c, method, **params):
            assert method == "getFile"
            return result
        telegram.call = call
        c = self.Client(chunks)
        try:
            return asyncio.run(telegram.file_bytes(c, "file-1", limit)), c.urls
        finally:
            telegram.call = real

    def test_limit_and_path(self):
        import telegram
        data, urls = self._run({"file_path": "voice/file_3.oga", "file_size": 10}, [b"a" * 30, b"b" * 30])
        self.assertEqual(data, b"a" * 30 + b"b" * 30)
        self.assertTrue(urls[0].endswith("/voice/file_3.oga"))
        with self.assertRaisesRegex(ValueError, "too big"):          # more than the limit, whatever the size said
            self._run({"file_path": "voice/file_3.oga", "file_size": 10}, [b"x" * 60, b"y" * 60])
        for bad in ("../../x", "voice/../../bot", "/etc/passwd", "voice//x", "voice/x?y=1", "a" * 300, ""):
            with self.assertRaises(ValueError, msg=bad):
                self._run({"file_path": bad, "file_size": 1}, [b"x"])
        with self.assertRaises(ValueError):
            self._run({"file_path": "voice/a.oga", "file_size": 101}, [b"x"])
        with self.assertRaises(ValueError):
            self._run(["not", "a", "dict"], [b"x"])
        src = inspect.getsource(telegram)
        self.assertIn("audio = await file_bytes(c, voice.get(\"file_id\"), MAX_VOICE)", src)
        self.assertNotIn("r = await c.get(f\"{root}/file/bot", src)


class IphonePairLink(unittest.TestCase):
    """N19: a pairing link never re-points an app that is paired with another Spark without asking."""

    def test_switch_needs_its_own_question(self):
        conv = os.path.join(ROOT, "ios", "Spark", "Conversation.swift")
        if not os.path.exists(conv):
            self.skipTest("ios is not part of this copy")
        c = read(conv)
        v = read(ROOT, "ios", "Spark", "Views.swift")
        opened = c[c.index("func open(_ url: URL)"):c.index("static func link(_ url: URL)")]
        self.assertIn("if paired, let now = Store.baseURL, !Self.sameSpark(now, link.base) {", opened)
        self.assertIn("link.replacing = Self.label(now)", opened)
        self.assertIn('Text("Zu einem anderen Spark wechseln?")', v)
        self.assertIn('.destructive(Text("Wechseln"))', v)
        pair = c[c.index("func pair(_ link: Link) async"):c.index("func join(")]
        self.assertLess(pair.index("Outbox.clear()"), pair.index("Store.baseURL = link.base"))
        strings = read(ROOT, "ios", "Spark", "Localizable.xcstrings")
        self.assertIn('"Zu einem anderen Spark wechseln?"', strings)


if __name__ == "__main__":
    unittest.main()
