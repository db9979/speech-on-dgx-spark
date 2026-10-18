"""Änderungsprotokoll mit Prüfkette (guard.py, offsite.py; plan plaene/sicheres-ki-system, Dominik 2026-10-18 "1-3").

Every line carries the SHA-256 of the line before it, also across rotated files; a line changed, taken out or put
in breaks the chain and verify() names the place; lines from before the chain stay readable; rotation keeps at most
AUDIT_FILES files and drops old ones by age; the pages never see the chain value; the daily check writes one journal
line and an alert on the admin pages when the chain breaks; the sealed copy on the NAS round-trips and the
comparison finds a line missing on the Spark; „Protokoll prüfen“ is for the main admin only.
No test depends on the wall clock: times are passed in or taken relative to now.
"""
import io
import json
import os
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import health  # noqa: E402
import offsite  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


class Chain(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(helpers.TMP, "protokoll-" + str(time.monotonic_ns()))
        os.makedirs(self.dir)
        self.audit = os.path.join(self.dir, "audit.log")
        for p in (mock.patch.object(guard, "AUDIT", self.audit),
                  mock.patch.object(guard, "AUDIT_LOCK", self.audit + ".lock"),
                  mock.patch.object(guard, "_chain", {"t": 0, "bad": None})):
            p.start()
            self.addCleanup(p.stop)

    def lines(self, path=None):
        with open(path or self.audit, "rb") as f:
            return [x for x in f.read().split(b"\n") if x]

    def write(self, lines, path=None):
        with open(path or self.audit, "wb") as f:
            f.write(b"".join(x + b"\n" for x in lines))

    def test_every_line_points_at_the_one_before(self):
        for i in range(5):
            guard.log("config_switch", detail=f"n{i}")
        got = self.lines()
        self.assertEqual(json.loads(got[0])["p"], guard.GENESIS)
        for a, b in zip(got, got[1:]):
            self.assertEqual(json.loads(b)["p"], guard.line_hash(a))
        r = guard.verify()
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["lines"], r["old"], r["files"]), (5, 0, 1))
        self.assertEqual(r["head"], guard.line_hash(got[-1])[:16])

    def test_a_changed_line_breaks_the_chain_there(self):
        for i in range(5):
            guard.log("config_switch", detail=f"n{i}")
        got = self.lines()
        got[2] = got[2].replace(b"n2", b"xx")
        self.write(got)
        r = guard.verify()
        self.assertFalse(r["ok"])
        self.assertEqual(r["broken"]["line"], 4, "the line after the changed one no longer fits")
        self.assertEqual(r["broken"]["file"], "audit.log")

    def test_a_line_taken_out_or_put_in_breaks_the_chain(self):
        for i in range(5):
            guard.log("config_switch", detail=f"n{i}")
        got = self.lines()
        self.write(got[:1] + got[2:])
        self.assertEqual(guard.verify()["broken"]["line"], 2)
        self.write(got[:3] + [json.dumps({"t": 1, "event": "admin_login"}).encode()] + got[3:])
        self.assertEqual(guard.verify()["broken"]["line"], 4, "a line without chain after the chain began")
        self.write(got[:3] + [b"not json"] + got[3:])
        self.assertFalse(guard.verify()["ok"])

    def test_a_lock_file_that_cannot_be_opened_keeps_no_entry_out(self):
        with mock.patch.object(guard, "AUDIT_LOCK", os.path.join(self.dir, "fehlt", "audit.log.lock")):
            guard.log("config_switch")
        self.assertEqual(len(self.lines()), 1)

    def test_lines_from_before_the_chain_stay_readable(self):
        self.write([json.dumps({"t": 100, "event": "admin_login"}).encode(),
                    json.dumps({"t": 101, "event": "backup"}).encode()])
        guard.log("config_switch")
        r = guard.verify()
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["lines"], r["old"]), (3, 2))
        self.assertEqual([e["event"] for e in guard.read()], ["config_switch", "backup", "admin_login"])

    def test_the_pages_never_see_the_chain_value(self):
        guard.log("config_switch")
        self.assertNotIn("p", guard.read()[0])
        guard.log("config_switch", p="0" * 64)   # a caller cannot set it either
        self.assertTrue(guard.verify()["ok"])

    def test_the_chain_goes_on_across_rotated_files_and_old_ones_go(self):
        with mock.patch.object(guard, "AUDIT_MAX", 300), mock.patch.object(guard, "AUDIT_FILES", 3):
            for i in range(40):
                guard.log("config_switch", detail=f"eintrag {i:03d} " + "x" * 40)
            files = guard.audit_files()
            self.assertEqual(len(files), 4, files)   # audit.log and three rotated
            self.assertEqual(os.path.basename(files[-1]), "audit.log")
            r = guard.verify()
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["files"], 4)
            self.assertEqual(guard.read(limit=1)[0]["detail"][:12], "eintrag 039 ")
            # a line changed in a rotated file breaks it there
            mid = files[1]
            got = self.lines(mid)
            got[0] = got[0].replace(b"eintrag", b"Eintrag")
            self.write(got, mid)
            self.assertEqual(guard.verify()["broken"]["file"], os.path.basename(mid))

    def test_rotated_files_older_than_a_year_go(self):
        guard.log("config_switch")
        old = self.audit + ".1"
        self.write([json.dumps({"t": 1, "event": "backup"}).encode()], old)
        past = time.time() - (guard.AUDIT_DAYS + 2) * 86400
        os.utime(old, (past, past))
        guard._rotate(time.time())
        self.assertFalse(os.path.exists(self.audit + ".2"), "older than AUDIT_DAYS: gone")
        self.assertTrue(os.path.exists(self.audit + ".1"))

    def test_the_daily_check_alerts_once_and_clears(self):
        for i in range(3):
            guard.log("config_switch", detail=f"n{i}")
        now = 1_000_000
        self.assertTrue(guard.chain_due(now))
        self.assertTrue(guard.chain_daily(now)["ok"])
        self.assertFalse(guard.chain_due(now + 60))
        self.assertEqual(guard.alerts(), [])
        got = self.lines()
        got[0] = got[0].replace(b"n0", b"zz")
        self.write(got)
        guard.chain_daily(now + 86400)
        a = guard.alerts()
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["go"], "Zustand → Logs → Änderungen")
        self.assertIn(a[0], health.alerts())
        guard.chain_daily(now + 2 * 86400)   # the same break: no second entry
        events = [json.loads(x)["event"] for x in self.lines()]
        self.assertEqual(events.count("audit_chain_broken"), 1)
        self.write(got[:1])                  # whole again (one line left): the alert goes
        guard.chain_daily(now + 3 * 86400)
        self.assertEqual(guard.alerts(), [])


class NasCopy(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(helpers.TMP, "protokoll-nas-" + str(time.monotonic_ns()))
        os.makedirs(self.dir)
        self.audit = os.path.join(self.dir, "audit.log")
        for p in (mock.patch.object(guard, "AUDIT", self.audit),
                  mock.patch.object(guard, "AUDIT_LOCK", self.audit + ".lock")):
            p.start()
            self.addCleanup(p.stop)
        with mock.patch.object(guard, "AUDIT_MAX", 400):
            for i in range(12):
                guard.log("config_switch", detail=f"n{i:02d} " + "y" * 60)

    def sealed_copy(self):
        enc = io.BytesIO()
        offsite.encrypt(offsite._LogReader(guard.audit_files()), enc, "ein langes Sicherungspasswort")
        out = io.BytesIO()
        offsite.decrypt(io.BytesIO(enc.getvalue()), out, "ein langes Sicherungspasswort", most=offsite.LOG_MOST)
        return out.getvalue()

    def test_the_sealed_copy_holds_every_kept_file_in_order(self):
        self.assertGreater(len(guard.audit_files()), 1)
        raw = self.sealed_copy()
        want = b""
        for p in guard.audit_files():
            with open(p, "rb") as f:
                want += f.read()
        self.assertEqual(raw, want)
        r = offsite.compare_lines(raw.split(b"\n"), guard.audit_files())
        self.assertEqual((r["lines"], r["missing"]), (12, 0))

    def test_a_line_gone_on_the_spark_shows_against_the_copy(self):
        copy = self.sealed_copy().split(b"\n")
        newest = self.audit
        with open(newest, "rb") as f:
            got = [x for x in f.read().split(b"\n") if x]
        with open(newest, "wb") as f:
            f.write(b"".join(x + b"\n" for x in got[:-1]))
        self.assertEqual(offsite.compare_lines(copy, guard.audit_files())["missing"], 1)

    def test_lines_the_spark_dropped_by_age_do_not_count(self):
        copy = self.sealed_copy().split(b"\n")
        oldest = guard.audit_files()[0]
        with open(oldest, "rb") as f:
            n = len([x for x in f.read().split(b"\n") if x])
        own = guard.audit_files()[1:]
        r = offsite.compare_lines(copy, own)
        self.assertEqual(r["missing"], 0)
        self.assertEqual(r["lines"], 12 - n)

    def test_the_check_reads_the_newest_copy_from_the_nas(self):
        import asyncio
        import httpx
        key = "ein langes Sicherungspasswort"
        enc = io.BytesIO()
        offsite.encrypt(offsite._LogReader(guard.audit_files()), enc, key)
        asked = []

        def handler(request):
            asked.append(request.url.path)
            return httpx.Response(200, content=enc.getvalue())
        real = offsite.netguard.client
        offsite.netguard.client = lambda level, origin=None, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        offsite._write({"url": "https://nas.example.de/dav/", "key": offsite.vault.seal(key),
                        "sent_log": [offsite.LOG_PREFIX + "a.log.enc", offsite.LOG_PREFIX + "b.log.enc"]})
        try:
            r = asyncio.run(offsite.compare_audit())
        finally:
            offsite.netguard.client = real
            offsite._write({})
        self.assertEqual(asked, ["/dav/" + offsite.LOG_PREFIX + "b.log.enc"])
        self.assertEqual((r["lines"], r["missing"], r["name"]), (12, 0, offsite.LOG_PREFIX + "b.log.enc"))

    def test_the_copy_name_follows_the_backup(self):
        src = open(offsite.__file__).read()
        self.assertIn('LOG_PREFIX + stamp.removeprefix("speech-spark-")', src)
        self.assertTrue(offsite.LOG_PREFIX.startswith("speech-spark-protokoll-"))


class Endpoint(unittest.TestCase):
    def test_only_the_main_admin_checks(self):
        self.assertEqual(TestClient(panel.app).get("/api/audit/check").status_code, 401)
        r = ADMIN.get("/api/audit/check")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertIn("ok", d["chain"])
        self.assertIsNone(d["nas"])

    def test_without_a_nas_copy_the_answer_says_so(self):
        with mock.patch.object(offsite, "_read", return_value={}):
            d = ADMIN.get("/api/audit/check?nas=1").json()
        self.assertIsNone(d["nas"])
        self.assertEqual(d["nas_error"], "")


if __name__ == "__main__":
    unittest.main()
