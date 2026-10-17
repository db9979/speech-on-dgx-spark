"""Aktiv in den letzten 10 Minuten (aktiv.py, Dominik 2026-10-17 "1b 2a 3a"): who counts, for how long, never a name."""
import time
import unittest

from tests import helpers

helpers.start()
import aktiv  # noqa: E402
import tracelog  # noqa: E402

T0 = time.mktime((2026, 10, 17, 9, 0, 0, 0, 0, -1))


class Aktiv(unittest.TestCase):
    def setUp(self):
        aktiv._seen.clear()
        self.addCleanup(aktiv._seen.clear)

    def test_profiles_and_guests_for_ten_minutes(self):
        aktiv.sah(T0, "u1", "profile", "web")
        aktiv.sah(T0 + 5, "u1", "profile", "speaker")          # the same profile on a second device: still one
        aktiv.sah(T0, None, "admin", "web")
        aktiv.sah(T0, None, "guest", "speaker", ort="192.168.178.50")
        aktiv.sah(T0, None, "guest", "speaker", ort="192.168.178.51")
        aktiv.sah(T0, None, "guest", "ha", device="Assist (Wyoming)")
        aktiv.sah(T0, None, "guest", "ha", device="Assist (Wyoming)")
        self.assertEqual(aktiv.zahlen(T0 + 60), {"gesamt": 5, "profile": 2, "gaeste": 3})
        self.assertEqual(aktiv.zahlen(T0 + aktiv.FENSTER_S + 4)["profile"], 1, "u1 came again 5 s later")
        self.assertEqual(aktiv.zahlen(T0 + aktiv.FENSTER_S + 6), {"gesamt": 0, "profile": 0, "gaeste": 0})

    def test_the_spark_itself_never_counts(self):
        aktiv.sah(T0, "u1", "spark", "auto")
        aktiv.sah(T0, "u1", "profile", "auto")
        self.assertEqual(aktiv.zahlen(T0)["gesamt"], 0)

    def test_no_name_and_no_address_is_kept(self):
        aktiv.sah(T0, None, "guest", "web", ort="203.0.113.7")
        aktiv.sah(T0, None, "guest", "speaker", device="Küche")
        text = " ".join(aktiv._seen)
        self.assertNotIn("203.0.113", text)
        self.assertNotIn("Küche", text)

    def test_memory_is_bounded(self):
        for i in range(aktiv.MAX + 50):
            aktiv.sah(T0 + i / 1000, None, "guest", "web", ort=f"10.1.{i // 256}.{i % 256}")
        self.assertEqual(len(aktiv._seen), aktiv.MAX)

    def test_counts_while_logs_and_live_are_off(self):
        import common
        old = common.load_config()
        self.addCleanup(helpers.write_config, old)
        cfg = dict(old, logs=dict(old.get("logs", {}), trace=False, live=False))
        helpers.write_config(cfg)
        tracelog.start(T0, "app", "u7", "profile", "")
        self.assertEqual(aktiv.zahlen(T0)["profile"], 1)


if __name__ == "__main__":
    unittest.main()
