"""Unit tests for text handling and helpers that need no server."""
import datetime
import unittest

from tests import helpers  # noqa: F401  (sets up paths and a throw-away state directory)
import calendars  # noqa: E402
import homeassistant  # noqa: E402
import recall  # noqa: E402
import textnorm  # noqa: E402


class Text(unittest.TestCase):
    def test_lines_end_with_a_full_stop(self):
        out = textnorm.clean_text("Einkaufsliste\n- Milch\n- Brot")
        for line in out.splitlines():
            self.assertTrue(line.endswith("."), line)

    def test_emoji_and_markdown_removed(self):
        out = textnorm.clean_text("**Hallo** 😀 Welt")
        self.assertNotIn("*", out)
        self.assertNotIn("😀", out)

    def test_language_guess(self):
        self.assertEqual(textnorm.guess_language("Wie spät ist es heute?"), "German")
        self.assertEqual(textnorm.guess_language("What is the weather like and when does the train leave?"), "English")


class Secrets(unittest.TestCase):
    """Fixed rule: passwords, code words, one-time codes and keys are never spoken (textnorm.hide_secrets)."""
    HIDDEN = [
        ("Dein WLAN-Passwort ist Sonne123, soll ich es dir schicken?", "Sonne123"),
        ("Das Passwort für das Gäste-WLAN lautet: Sonne Mond Sterne.", "Mond"),
        ("Das Passwort ist Sonne.", "Sonne."),
        ("Dein Passwort lautet sonnenblume", "sonnenblume"),
        ("Dein Bestätigungscode lautet 482 913. Er gilt zehn Minuten.", "913"),
        ("Der Code ist 4711.", "4711"),
        ("Deine SIM-PIN 1234 läuft ab.", "1234"),
        ("Dein PIN-Code: 0815", "0815"),
        ("Die TAN ist 123456.", "123456"),
        ("Dein Codewort ist „Sonnenblume“, sag es leise.", "Sonnenblume"),
        ("Das Passwort ist S, o, n, n, e.", "n, n"),
        ("The password is hunter2.", "hunter2"),
        ("Your API key is sk-proj-abcdefghijklmnop.", "abcdefghijklmnop"),
        ("Der Schlüssel ghp_abcdefghijklmnopqrstuvwxyz1234 ist neu.", "ghp_"),
        ("Hier: aB3dE5gH7jK9mN1pQ2", "aB3dE5"),
        ("otpauth://totp/Spark?secret=JBSWY3DPEHPK3PXP", "JBSWY3DP"),
    ]
    KEPT = ["Das Passwort ist falsch.", "Dein Passwort ist im Tresor gespeichert.", "Was ist dein Passwort?",
            "Der Abstand ist 50 cm.", "Der Pinguin ist 3 Jahre alt.", "Die Tante ist 80.", "Hockey ist toll.",
            "Sendungsnummer 1Z999AA10123456784 ist unterwegs.", "Das Modell heißt Qwen3.8-27B.",
            "Die Postleitzahl ist 80331.", "Morgen um 14:30 ist es sonnig."]

    def test_secrets_are_not_spoken(self):
        for text, value in self.HIDDEN:
            out = textnorm.hide_secrets(text)
            self.assertNotIn(value, out, text)
            self.assertTrue("nur schriftlich sichtbar" in out or "shown in writing only" in out, out)

    def test_ordinary_sentences_stay(self):
        for text in self.KEPT:
            self.assertEqual(textnorm.hide_secrets(text), text)

    def test_hint_follows_the_language(self):
        self.assertIn("shown in writing only", textnorm.hide_secrets("The password is hunter2.", "English"))
        self.assertIn("nur schriftlich sichtbar", textnorm.hide_secrets("The password is hunter2.", "German"))

    def test_both_speech_services_always_hide(self):
        """Before the clean_text switch, so turning clean-up off never lets a password through."""
        import ast
        import os
        for name in ("tts_server.py", "tts_proxy.py"):   # read, not imported: the server needs soundfile/torch
            path = os.path.join(os.path.dirname(textnorm.__file__), name)
            with open(path, encoding="utf-8") as f:
                code = f.read()
            fn = next(n for n in ast.walk(ast.parse(code)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == "speech")
            src = ast.get_source_segment(code, fn)
            self.assertIn("hide_secrets", src, name)
            self.assertLess(src.index("hide_secrets"), src.index('cfg.get("clean_text"'), name)

    def test_long_text_is_fast(self):
        import time
        start = time.perf_counter()
        for t in ("Passwort " * 2200, "Code ist " + "x " * 9000, "a" * 20000, "S, " * 6000):
            textnorm.hide_secrets(t[:20000])
        self.assertLess(time.perf_counter() - start, 2.0)


class HA(unittest.TestCase):
    def test_entry_validation(self):
        with self.assertRaises(ValueError):
            homeassistant.entry({"url": "ftp://x", "token": "a" * 40})
        with self.assertRaises(ValueError):
            homeassistant.entry({"url": "http://ha.local:8123", "token": "short"})
        old = {"url": "http://ha.local:8123", "token": "k" * 40}
        e = homeassistant.entry({"url": "http://ha.local:8123/", "token": ""}, old)
        self.assertEqual((e["url"], e["token"]), ("http://ha.local:8123", "k" * 40))
        # a new address never gets the stored token (it would be sent there)
        with self.assertRaises(ValueError):
            homeassistant.entry({"url": "https://evil.example", "token": ""}, old)


class Recall(unittest.TestCase):
    def test_parse_facts(self):
        self.assertEqual(recall.parse_facts('```json\n{"facts": ["Ben hat einen Hund.", "x"]}\n```'), ["Ben hat einen Hund."])
        self.assertEqual(recall.parse_facts("kein json"), [])


class Calendar(unittest.TestCase):
    def test_recurring_events_expand(self):
        ics = ("BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:1\nSUMMARY:Sport\n"
               "DTSTART:20261005T180000Z\nDTEND:20261005T190000Z\nRRULE:FREQ=WEEKLY\nEND:VEVENT\nEND:VCALENDAR\n")
        zone = datetime.timezone.utc
        start = datetime.datetime(2026, 10, 1, tzinfo=zone)
        evs = calendars._expand([ics], start, start + datetime.timedelta(days=21), zone, "Test")
        self.assertEqual(len(evs), 3)
        self.assertTrue(all(e["title"] == "Sport" for e in evs))


if __name__ == "__main__":
    unittest.main()


class WebPush(unittest.TestCase):
    def test_encryption_round_trip_and_vapid(self):
        """Decrypts like a browser would (RFC 8291) and checks the VAPID signature."""
        import json
        import os
        import struct
        import push
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ua = ec.generate_private_key(ec.SECP256R1())
        ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        auth = os.urandom(16)
        sub = push.valid({"endpoint": "https://fcm.googleapis.com/fcm/send/abc",
                          "keys": {"p256dh": push.b64(ua_pub), "auth": push.b64(auth)}})
        body = push.encrypt(sub, b'{"title": "x"}')
        salt, (rs, idlen) = body[:16], struct.unpack("!IB", body[16:21])
        as_pub = body[21:21 + idlen]
        shared = ua.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
        ikm = push._hkdf(auth, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
        cek = push._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
        nonce = push._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
        plain = AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)
        self.assertEqual(plain, b'{"title": "x"}\x02')
        token = push.vapid(sub["endpoint"]).split("t=")[1].split(",")[0]
        head, claims, sig = token.split(".")
        self.assertEqual(json.loads(push.unb64(claims))["aud"], "https://fcm.googleapis.com")
        raw = push.unb64(sig)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.unb64(push.public_key()))
        pub.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))  # raises if wrong

    def test_only_push_services(self):
        import push
        good = {"p256dh": push.b64(b"\x04" + b"1" * 64), "auth": push.b64(b"a" * 16)}
        for url in ("https://127.0.0.1/x", "http://fcm.googleapis.com/x", "https://evil.example/fcm.googleapis.com"):
            with self.assertRaises(ValueError):
                push.valid({"endpoint": url, "keys": good})
        push.valid({"endpoint": "https://web.push.apple.com/abc", "keys": good})


class History(unittest.TestCase):
    def test_trim_keeps_newest_and_starts_with_user(self):
        import chat
        msgs = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i) * 1000} for i in range(40)]
        out = chat.trim_history(msgs, 5500)
        self.assertEqual(out[-1], msgs[-1])
        self.assertEqual(out[0]["role"], "user")
        self.assertLessEqual(sum(len(m["content"]) for m in out), 5500)
        self.assertEqual([m["role"] for m in chat.trim_history([{"role": "user", "content": "x" * 99999}], 10)], ["user"])


class AsrFrontEnd(unittest.TestCase):
    def test_parakeet_gets_the_whole_recording(self):
        """With Parakeet the upload goes to the CPU model once (it used to be read twice, the second
        read was empty)."""
        import asr_proxy
        from fastapi.testclient import TestClient
        seen = []

        class Fake:
            status, error = "ready", None

            def transcribe_file(self, path):
                with open(path, "rb") as f:
                    seen.append(f.read())
                return "hallo welt", 1.0
        asr_proxy.local, old = Fake(), asr_proxy.local
        try:
            r = TestClient(asr_proxy.app).post("/v1/audio/transcriptions", files={"file": ("a.wav", b"RIFF" + b"x" * 100)},
                                               headers={"Authorization": "Bearer " + (asr_proxy.load_config().get("api", {}).get("key") or "")})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(seen, [b"RIFF" + b"x" * 100])
            self.assertIn("hallo welt", r.text)
        finally:
            asr_proxy.local = old


class WithoutPanel(unittest.TestCase):
    """Install mode "api": the command line speech-spark and the watchdog of its own."""

    def info(self, mode, **hosts):
        import json
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as etc:
            with open(os.path.join(helpers.APP, "config.default.json")) as f:
                cfg = json.load(f)
            cfg["api"]["key"] = "sk-test123"
            for name, host in hosts.items():
                cfg[name]["host"] = host
            with open(os.path.join(etc, "config.json"), "w") as f:
                json.dump(cfg, f)
            with open(os.path.join(etc, "mode"), "w") as f:
                f.write(mode + "\n")
            env = dict(os.environ, SPEECH_SPARK_ETC=etc, SPEECH_SPARK_PREFIX=helpers.TMP)
            p = subprocess.run(["bash", os.path.join(helpers.APP, "speech-spark.sh"), "info"], env=env,
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)
            return p.stdout

    def test_info_names_endpoints_and_key(self):
        out = self.info("api")
        self.assertIn("only the models with their APIs", out)
        self.assertIn(":31001/v1/audio/transcriptions", out)
        self.assertIn(":31002/v1/audio/speech", out)
        self.assertIn("Authorization: Bearer sk-test123", out)
        self.assertIn("from the network", out)

    def test_info_local_only(self):
        out = self.info("full", asr="127.0.0.1", tts="127.0.0.1")
        self.assertIn("http://127.0.0.1:31001/v1", out)
        self.assertIn("only on this machine", out)
        self.assertIn("with the web panel", out)

    def test_watchdog_uses_the_panel_rules(self):
        import api_watchdog
        self.assertTrue(callable(api_watchdog.health.watch_once))
        self.assertTrue(callable(api_watchdog.update.update_running))
