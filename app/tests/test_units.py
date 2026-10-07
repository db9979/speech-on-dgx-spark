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


class HA(unittest.TestCase):
    def test_entry_validation(self):
        with self.assertRaises(ValueError):
            homeassistant.entry({"url": "ftp://x", "token": "a" * 40})
        with self.assertRaises(ValueError):
            homeassistant.entry({"url": "http://ha.local:8123", "token": "short"})
        e = homeassistant.entry({"url": "http://ha.local:8123/", "token": ""}, {"token": "k" * 40})
        self.assertEqual((e["url"], e["token"]), ("http://ha.local:8123", "k" * 40))


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
