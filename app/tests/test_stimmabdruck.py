"""The voiceprint (users/<id>/voice.json) is biometric: it lies sealed with the Spark's key like a password, an older
plain file is sealed the first time it is read, and a file sealed with another key opens as no voiceprint at all
(Dominik 2026-10-13: „1. ja“ to sealing it, plan technische-doku.md)."""
import json
import os
import unittest

from tests import helpers

helpers.start()
import numpy as np  # noqa: E402

import profiles  # noqa: E402
import speakers  # noqa: E402
import vault  # noqa: E402


def _uid(name):
    try:
        return profiles.add_user(name, "4711")
    except Exception:
        return next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


@unittest.skipUnless(vault.available(), "no cryptography here")
class Sealed(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        profiles.delete_user(_uid("Stimmprobe"))

    def setUp(self):
        self.uid = _uid("Stimmprobe")
        self.old = speakers.embed, speakers.decode
        vec = np.ones(256, np.float32) / 16.0
        speakers.embed = lambda x, **kw: vec
        speakers.decode = lambda data: np.zeros(16000, np.float32)

    def tearDown(self):
        speakers.embed, speakers.decode = self.old
        speakers.forget(self.uid)

    def raw(self):
        with open(speakers._file(self.uid)) as f:
            return json.load(f)

    def test_written_sealed(self):
        self.assertEqual(speakers.enroll(self.uid, b"x"), 1)
        d = self.raw()
        self.assertEqual(set(d), {"sealed"})
        self.assertTrue(d["sealed"].startswith(vault.PREFIX))
        self.assertNotIn("0.0625", json.dumps(d))          # no number of the voiceprint in the file
        self.assertEqual(oct(os.stat(speakers._file(self.uid)).st_mode & 0o777), "0o600")
        self.assertEqual(len(speakers.samples(self.uid)), 1)
        self.assertTrue(speakers.has_voice(self.uid))
        self.assertEqual(speakers.enroll(self.uid, b"x"), 2)   # read back through the cache and written again

    def test_old_plain_file_is_sealed_when_read(self):
        profiles._write(speakers._file(self.uid), {"samples": [[0.5] * 256], "updated": 1})
        speakers._cache.pop(self.uid, None)
        self.assertEqual(len(speakers.samples(self.uid)), 1)
        self.assertEqual(set(self.raw()), {"sealed"})
        self.assertEqual(speakers.samples(self.uid), [[0.5] * 256])

    def test_other_key_opens_as_nothing(self):
        speakers.enroll(self.uid, b"x")
        from cryptography.fernet import Fernet
        foreign = vault.PREFIX + Fernet(Fernet.generate_key()).encrypt(b'{"samples": [[1.0]]}').decode()
        profiles._write(speakers._file(self.uid), {"sealed": foreign})
        self.assertEqual(speakers.samples(self.uid), [])
        self.assertFalse(speakers.has_voice(self.uid))
        self.assertEqual(speakers.enroll(self.uid, b"x"), 1)   # recorded anew

    def test_forget_removes_it(self):
        speakers.enroll(self.uid, b"x")
        speakers.forget(self.uid)
        self.assertFalse(os.path.exists(speakers._file(self.uid)))
        self.assertEqual(speakers.samples(self.uid), [])


if __name__ == "__main__":
    unittest.main()
