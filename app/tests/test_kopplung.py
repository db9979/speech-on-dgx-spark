"""The shared helpers for pairing codes (kopplung.Codes) and today's numbers (common.DayCounter): single use, expiry,
kind, limits, form check; a new local day starts from fresh zeros. No clock: every call gets its own `now`."""
import time
import unittest

from tests import helpers

helpers.start()
import kopplung  # noqa: E402
from common import DayCounter  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def noon(day):
    return time.mktime((2026, 3, day, 12, 0, 0, 0, 0, -1))


class Codes(unittest.TestCase):
    def codes(self, **kw):
        return kopplung.Codes(kopplung.link_code, kopplung.link_form, kw.get("seconds", 600), kw.get("most", 4),
                              kw.get("per_profile", 2), kind=kw.get("kind", ""))

    def test_once_and_only_its_hash(self):
        c = self.codes()
        code = c.new("u1", now=1000.0)
        self.assertGreaterEqual(len(code), 24)
        self.assertNotIn(code, str(c.pending))                       # only the hash is kept
        self.assertEqual(c.take(code, now=1001.0), "u1")
        self.assertIsNone(c.take(code, now=1002.0))                  # used up

    def test_expiry_kind_and_form(self):
        c = self.codes(kind="schreib")
        code = c.new("u1", now=1000.0)
        self.assertIsNone(c.take(code, now=1000.0 + 601))            # expired
        code = c.new("u1", now=2000.0, what="begleiter")
        self.assertIsNone(c.take(code, now=2001.0))                  # another kind never fits
        self.assertEqual(c.take(code, now=2001.0, what="begleiter"), "u1")
        for bad in (None, 5, "", "../" * 10, "x" * 80):
            self.assertIsNone(c.take(bad, now=2001.0))

    def test_limits(self):
        c = self.codes()
        first = c.new("u1", now=1000.0)
        c.new("u1", now=1001.0)
        c.new("u1", now=1002.0)                                      # replaces the oldest of the profile
        self.assertIsNone(c.take(first, now=1003.0))
        c.new("u2", now=1004.0)
        c.new("u3", now=1005.0)
        with self.assertRaises(HTTPException) as e:                  # the whole Spark: at most `most`
            c.new("u4", now=1006.0)
        self.assertEqual(e.exception.status_code, 429)


class Day(unittest.TestCase):
    def test_new_day_fresh_zeros(self):
        d = DayCounter(n=0, kinds={})
        d.today(noon(1))["kinds"]["a"] = 1
        self.assertEqual(d.bump("n", now=noon(1)), 1)
        self.assertEqual(d.counts(noon(1)), {"n": 1, "kinds": {"a": 1}})
        self.assertEqual(d.counts(noon(2)), {"n": 0, "kinds": {}})   # read only: nothing reset yet
        self.assertEqual(d["n"], 1)
        self.assertEqual(d.bump("n", now=noon(2)), 1)                # a new day starts from the zeros
        self.assertEqual(d.today(noon(2))["kinds"], {})              # a fresh copy, never the old dict
        self.assertEqual(d["day"], DayCounter.date(noon(2)))

    def test_open_keys(self):
        d = DayCounter()
        d.bump("x", 5, now=noon(3))
        self.assertEqual(d.counts(noon(3)), {"x": 5})
        self.assertEqual(d.counts(noon(4)), {})


if __name__ == "__main__":
    unittest.main()
