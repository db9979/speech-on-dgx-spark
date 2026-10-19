"""Wachposten (wachposten.py; plan plaene/sicheres-ki-system, Dominik 2026-10-18 "1-3").

Off by default and nothing counted while off; the rules are fixed (lockout, new way in, protection changed, change
log changed, quality worse) and take only the change log's fixed words, never a name, an address or a detail; one
note per round to every admin with a device, at most MAX_DAY a day for lockouts and the quality test (the rest the
next day), a new way in or changed protection always at once and never dropped; a note that reached nobody
waits; the quality run is told once; never for a profile without the admin role.
No test depends on the wall clock: times are passed in.
"""
import asyncio
import os
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import features  # noqa: E402
import guard  # noqa: E402
import wachposten  # noqa: E402

NOW = 1_800_000_000   # a fixed moment; days are counted from here


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "wachposten")
        self.file = os.path.join(helpers.TMP, f"wachposten-{time.monotonic_ns()}.json")
        self.audit = os.path.join(helpers.TMP, f"audit-wp-{time.monotonic_ns()}.log")
        for p in (mock.patch.object(wachposten, "FILE", self.file),
                  mock.patch.object(guard, "AUDIT", self.audit),
                  mock.patch.object(guard, "AUDIT_LOCK", self.audit + ".lock")):
            p.start()
            self.addCleanup(p.stop)
        self.sent = []

        async def send(uid, title, body, tag="", private=True, why="", to=""):
            self.sent.append((uid, title, body, tag, private))
            return 1
        for p in (mock.patch("push.send", send), mock.patch("push.reachable", lambda uid, private: True),
                  mock.patch("notaus.admin_uids", lambda: ["admin1", "admin2"]),
                  mock.patch("health.quality_alert", lambda: [])):
            p.start()
            self.addCleanup(p.stop)

    def switch(self, on):
        helpers.set_config(wachposten=on)


class Rules(Base):
    def test_off_by_default_and_nothing_counted_while_off(self):
        self.assertIs(features.DEFAULT_ON.get("wachposten", False), False)
        self.switch(False)
        guard.log("admin_mfa_off")
        self.assertEqual(wachposten._read()["queue"], [])
        self.assertEqual(asyncio.run(wachposten.tick(NOW)), 0)
        self.assertEqual(self.sent, [])

    def test_the_rules_are_fixed(self):
        self.assertEqual(wachposten.rule_for({"event": "profile_login_failed", "locked": 60}), "sperre")
        self.assertIsNone(wachposten.rule_for({"event": "profile_login_failed"}), "a wrong PIN alone is no report")
        self.assertEqual(wachposten.rule_for({"event": "trusted_browser"}), "zugang")
        self.assertEqual(wachposten.rule_for({"event": "mcp_connect"}), "zugang")
        self.assertEqual(wachposten.rule_for({"event": "admin_mfa_off"}), "schutz")
        self.assertEqual(wachposten.rule_for({"event": "restore"}), "schutz")
        self.assertEqual(wachposten.rule_for({"event": "audit_chain_broken"}), "protokoll")
        self.assertIsNone(wachposten.rule_for({"event": "config_switch"}))
        self.assertIsNone(wachposten.rule_for({"event": "change", "path": "/api/admin/notaus"}))
        for evs in wachposten.EVENTS.values():
            for e in evs:
                self.assertIn(e, guard.LIVE_WORDS, f"{e}: its fixed words come from guard.LIVE_WORDS")

    def test_only_fixed_words_never_a_name_address_or_detail(self):
        self.switch(True)
        guard.log("profile_login_failed", ip="203.0.113.7", name="Wilma", locked=120)
        guard.log("trusted_browser", ip="198.51.100.9", detail="Wilmas iPhone")
        guard.log("config_sensitive", detail="panel.allow_lan an")
        q = wachposten._read()["queue"]
        self.assertEqual([x["r"] for x in q], ["sperre", "zugang", "schutz"])
        asyncio.run(wachposten.tick(NOW))
        self.assertEqual(len(self.sent), 2, "one note per admin")
        for uid, title, body, tag, private in self.sent:
            self.assertEqual((tag, private), ("wache", False))
            for secret in ("203.0.113", "198.51.100", "Wilma", "allow_lan"):
                self.assertNotIn(secret, title + body)
            self.assertIn("Zustand → Logs → Änderungen", body)
            self.assertIn("Sperre nach falschen Anmeldungen", title)
        self.assertEqual(wachposten._read()["queue"], [], "told: the queue is empty")


class Delivery(Base):
    def setUp(self):
        super().setUp()
        self.switch(True)

    def test_many_entries_come_in_one_note(self):
        for _ in range(9):
            guard.log("passkey_added")
        asyncio.run(wachposten.tick(NOW))
        self.assertEqual(len(self.sent), 2)
        self.assertIn(f"und {9 - wachposten.SHOW} weitere", self.sent[0][2])

    def test_at_most_max_day_notes_then_the_next_day(self):
        for i in range(wachposten.MAX_DAY + 2):
            guard.log("profile_login_failed", locked=60)
            asyncio.run(wachposten.tick(NOW + i))
        per_admin = [x for x in self.sent if x[0] == "admin1"]
        self.assertEqual(len(per_admin), wachposten.MAX_DAY)
        self.assertEqual(len(wachposten._read()["queue"]), 2, "the rest waits")
        asyncio.run(wachposten.tick(NOW + 86400 + 60))
        self.assertEqual(len([x for x in self.sent if x[0] == "admin1"]), wachposten.MAX_DAY + 1)
        self.assertEqual(wachposten._read()["queue"], [])

    def test_lockouts_never_silence_a_new_way_in(self):
        """Code check 19.10. C1: lockouts from the internet use up the day; a new passkey still goes out at once,
        and a flood of lockouts never pushes it out of the queue."""
        for i in range(wachposten.MAX_DAY):
            guard.log("profile_login_failed", locked=60)
            asyncio.run(wachposten.tick(NOW + i))
        guard.log("profile_login_failed", locked=60)
        self.sent.clear()
        asyncio.run(wachposten.tick(NOW + 100))
        self.assertEqual(self.sent, [], "the day is used up for lockouts")
        guard.log("passkey_added")
        for _ in range(wachposten.MAX_QUEUE + 20):
            guard.log("profile_login_failed", locked=60)
        self.assertIn("zugang", [x["r"] for x in wachposten._read()["queue"]])
        asyncio.run(wachposten.tick(NOW + 200))
        self.assertEqual(len(self.sent), 2, "one note per admin despite the cap")
        self.assertIn(wachposten.RULES["zugang"][0], self.sent[0][1])
        self.assertEqual(wachposten._read()["queue"], [])

    def test_a_note_that_reached_nobody_waits(self):
        guard.log("admin_main")
        with mock.patch("push.reachable", lambda uid, private: False):
            self.assertEqual(asyncio.run(wachposten.tick(NOW)), 0)
        self.assertEqual(len(wachposten._read()["queue"]), 1)
        self.assertEqual(asyncio.run(wachposten.tick(NOW + 60)), 2)
        self.assertEqual(wachposten._read()["queue"], [])

    def test_the_quality_run_is_told_once(self):
        run = {"t": NOW - 100, "cases": [{"q": "a", "new": True}, {"q": "b", "new": True}, {"q": "c"}]}
        with mock.patch("health.quality_alert", lambda: [{"kind": "quality"}]), mock.patch("quality.last", lambda: run):
            asyncio.run(wachposten.tick(NOW))
            asyncio.run(wachposten.tick(NOW + 60))
        self.assertEqual(len([x for x in self.sent if x[0] == "admin1"]), 1)
        self.assertIn("2 Frage(n) neu kaputt", self.sent[0][2])
        self.assertIn("Qualitätstest schlechter", self.sent[0][1])

    def test_the_change_log_never_fails_because_of_it(self):
        with mock.patch.object(wachposten, "_read", side_effect=OSError):
            guard.log("admin_mfa_off")     # no exception
        self.assertEqual(guard.read(limit=1)[0]["event"], "admin_mfa_off")

    def test_status_counts_only(self):
        guard.log("admin_mfa_off")
        st = wachposten.for_status(NOW)
        self.assertEqual(st, {"on": True, "waiting": 1, "week": 0})


if __name__ == "__main__":
    unittest.main()
