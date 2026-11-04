"""Änderungsprotokoll mit Prüfkette (guard.py, offsite.py; plan plaene/sicheres-ki-system, Dominik 2026-10-18 "1-3").

Every line carries the SHA-256 of the line before it, also across rotated files; a line changed, taken out or put
in breaks the chain and verify() names the place; lines from before the chain stay readable; rotation keeps at most
AUDIT_FILES files and drops old ones by age; the pages never see the chain value; the daily check writes one journal
line and an alert on the admin pages when the chain breaks; the sealed copy on the NAS round-trips and the
comparison finds a line missing on the Spark; a break names its kind (unreadable, without chain, wrong predecessor)
and the time before it, a line torn by a power cut stays a line of its own and a lone surrogate keeps no entry out; the page shows the kind in those words, the time before an unreadable
line, the number of breaks and whether the chain is whole after it; „Protokoll prüfen“ is for every admin, also an admin profile
(test_coadmin), never without a login.
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


class AuditDir(unittest.TestCase):
    """A change log of its own in a fresh folder (no tests here)."""

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


class Chain(AuditDir):
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

    def test_a_changed_line_and_a_torn_line_say_their_kind(self):
        for i in range(5):
            guard.log("config_switch", detail=f"n{i}")
        got = self.lines()
        before = json.loads(got[1])["t"]
        self.write(got[:2] + [got[2][:20]] + got[3:])   # torn, also unreadable: no time of its own
        r = guard.verify()
        self.assertEqual((r["broken"]["line"], r["broken"]["kind"], r["broken"]["t"]), (3, "unlesbar", 0))
        self.assertEqual(r["broken"]["before"], before, "the time of the last readable entry before it")
        self.assertEqual(r["breaks"], 2, "the line after it points at the whole line")
        self.assertFalse(r["broken"]["after_ok"])
        self.write(got[:2] + [got[2].replace(b"n2", b"xx")] + got[3:])
        r = guard.verify()
        self.assertEqual((r["broken"]["line"], r["broken"]["kind"], r["breaks"]), (4, "vorgaenger", 1))
        self.assertTrue(r["broken"]["after_ok"])
        self.write(got[:2] + [json.dumps({"t": 5, "event": "backup"}).encode()] + got[2:])
        self.assertEqual(guard.verify()["broken"]["kind"], "ohne_kette")
        self.assertEqual(set(guard.BREAK_WORDS), {"unlesbar", "ohne_kette", "vorgaenger"})

    def test_a_line_torn_by_a_power_cut_stays_its_own_line(self):
        """A write cut off (power cut, full disk) leaves a line without its end: the next entry must not be glued
        onto it (that entry was lost and the break hid it); the torn line itself still breaks the chain."""
        for i in range(3):
            guard.log("config_switch", detail=f"n{i}")
        with open(self.audit, "ab") as f:
            f.write(b'{"t": 17, "event": "config_sw')          # cut off mid-line
        guard.log("config_switch", detail="danach")
        guard.log("config_switch", detail="weiter")
        got = self.lines()
        self.assertEqual(len(got), 6)
        self.assertEqual(json.loads(got[4])["detail"], "danach", "the entry after the torn line stands on its own")
        r = guard.verify()
        self.assertFalse(r["ok"], "a torn line is never taken as whole")
        self.assertEqual((r["broken"]["line"], r["broken"]["kind"], r["breaks"]), (4, "unlesbar", 1))
        self.assertTrue(r["broken"]["after_ok"], "the chain fits again from the next entry on")
        guard.chain_daily(1_000_000)
        self.assertIn("unlesbare Zeile", guard.alerts()[0]["text"])
        self.assertIn("danach ist sie wieder heil", guard.alerts()[0]["text"])

    def test_a_lone_surrogate_from_outside_keeps_no_entry_out(self):
        name = json.loads('"\\udcff Gast"')      # what a JSON body can hold
        guard.log("profile_login_failed", name=name)
        got = self.lines()
        self.assertEqual(len(got), 1)
        self.assertEqual(json.loads(got[0])["name"], name)
        self.assertTrue(guard.verify()["ok"])

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


class Ack(AuditDir):
    """„Bruch als geprüft bestätigen“ (Dominik 2026-11-04, a real power cut: „Kette bricht in audit.log.1, Zeile 1907 …
    unlesbare Zeile … Danach ist die Kette wieder heil“): a confirmation is a new entry, the chain stays as it is, the
    break shows as confirmed with its kind and reason, only exactly that break (same line, same bytes, same line
    before; also after rotation), a changed or new break is open again, the daily check stays silent for it."""

    def torn(self, after=2):
        for i in range(3):
            guard.log("config_switch", detail=f"n{i}")
        with open(self.audit, "ab") as f:
            f.write(b'{"t": 17, "event": "config_sw')          # a power cut mid-line
        for i in range(after):
            guard.log("config_switch", detail=f"danach {i}")
        return guard.verify()["broken"]

    def test_a_confirmation_is_a_new_entry_and_the_chain_stays(self):
        b = self.torn()
        self.assertEqual((b["file"], b["line"], b["kind"]), ("audit.log", 4, "unlesbar"))
        self.assertEqual(b["sha"], guard.line_hash(b'{"t": 17, "event": "config_sw'))
        before = self.lines()
        self.assertEqual(guard.ack_break(b["file"], b["line"], b["sha"], "stromausfall", by="main"), (True, "unlesbar"))
        got = self.lines()
        self.assertEqual(got[:len(before)], before, "nothing of the chain is changed or healed")
        e = json.loads(got[-1])
        self.assertEqual((e["event"], e["file"], e["line"], e["sha"], e["kind"], e["reason"], e["by"]),
                         ("chain_break_ack", "audit.log", 4, b["sha"], "unlesbar", "stromausfall", "main"))
        self.assertEqual(e["prev"], guard.line_hash(before[2]), "bound to the line before it too")
        self.assertEqual(e["p"], guard.line_hash(got[-2]), "the confirmation is a link of the chain itself")
        r = guard.verify()
        self.assertFalse(r["ok"], "a confirmed break is still a break")
        self.assertIsNone(r["broken"])
        self.assertEqual((r["breaks"], r["open"]), (1, 0))
        a = r["acked"][0]
        self.assertEqual((a["line"], a["kind"], a["ack"]["reason"]), (4, "unlesbar", "stromausfall"))
        self.assertEqual(a["ack"]["t"], e["t"])
        self.assertIn("chain_break_ack", guard.LIVE_WORDS)
        import wachposten
        self.assertEqual(wachposten.rule_for({"event": "chain_break_ack"}), "schutz", "the other admins hear of it")

    def test_every_kind_can_be_confirmed_and_keeps_its_kind(self):
        for i in range(5):
            guard.log("config_switch", detail=f"n{i}")
        got = self.lines()
        self.write(got[:2] + [got[2].replace(b"n2", b"xx")] + got[3:])
        b = guard.verify()["broken"]
        self.assertEqual(b["kind"], "vorgaenger")
        self.assertTrue(guard.ack_break(b["file"], b["line"], b["sha"], "unbekannt")[0])
        a = guard.verify()["acked"][0]
        self.assertEqual((a["kind"], a["ack"]["reason"]), ("vorgaenger", "unbekannt"))

    def test_only_the_break_the_check_reports_now(self):
        self.assertEqual(guard.ack_break("audit.log", 1, "0" * 64, "stromausfall"), (False, "kein_bruch"))
        b = self.torn()
        n = len(self.lines())
        self.assertEqual(guard.ack_break(b["file"], b["line"], b["sha"], "weil ich will"), (False, "grund"))
        self.assertEqual(guard.ack_break(b["file"], b["line"], "f" * 64, "stromausfall"), (False, "anders"))
        self.assertEqual(guard.ack_break(b["file"], b["line"] + 1, b["sha"], "stromausfall"), (False, "anders"))
        self.assertEqual(guard.ack_break("audit.log.1", b["line"], b["sha"], "stromausfall"), (False, "anders"))
        self.assertEqual(len(self.lines()), n, "a refused confirmation writes nothing")
        self.assertEqual(set(guard.ACK_REASONS), {"stromausfall", "karte_voll", "unbekannt"})
        for de, en in guard.ACK_REASONS.values():
            self.assertTrue(de and en)

    def test_a_changed_or_a_new_break_is_open_again(self):
        b = self.torn()
        guard.ack_break(b["file"], b["line"], b["sha"], "karte_voll")
        self.assertIsNone(guard.verify()["broken"])
        guard.log("config_switch", detail="noch eine")
        got = self.lines()
        self.write(got[:-1] + [b"kaputt"])                    # a new break after the confirmation
        r = guard.verify()
        self.assertEqual((r["broken"]["line"], r["open"], len(r["acked"])), (len(got), 1, 1))
        self.write(got)
        self.assertIsNone(guard.verify()["broken"])
        got[3] = b'{"t": 17, "event": "config_XX'               # the same line, other bytes: open again
        self.write(got)
        r = guard.verify()
        self.assertEqual((r["broken"]["line"], r["broken"]["kind"]), (4, "unlesbar"))
        self.assertEqual(r["acked"], [])

    def test_the_same_bytes_elsewhere_are_not_confirmed(self):
        b = self.torn()
        guard.ack_break(b["file"], b["line"], b["sha"], "stromausfall")
        got = self.lines()
        # the same torn bytes again at another place: another line before it, so not the confirmed break
        self.write(got + [b'{"t": 17, "event": "config_sw'])
        r = guard.verify()
        self.assertEqual(r["broken"]["line"], len(got) + 1)
        self.assertEqual(r["broken"]["sha"], b["sha"])

    def test_a_confirmation_off_the_chain_or_before_the_break_counts_not(self):
        b = self.torn()
        got = self.lines()
        fake = json.dumps({"t": 20, "event": "chain_break_ack", "file": b["file"], "line": b["line"], "sha": b["sha"],
                           "prev": b["prev"], "kind": b["kind"], "reason": "stromausfall"}).encode()
        self.write(got + [fake])                              # without chain value: put in from outside
        self.assertEqual(guard.verify()["broken"]["line"], 4)
        self.write(got[:1] + [json.dumps({**json.loads(fake), "p": guard.line_hash(got[0])}).encode()] + got[1:])
        r = guard.verify()
        self.assertEqual(r["broken"]["line"], 3, "put in before the break: the line after it no longer fits")
        self.assertEqual((r["acked"], r["open"]), ([], 2), "and it confirms nothing")

    def test_the_confirmation_follows_the_line_through_rotation(self):
        with mock.patch.object(guard, "AUDIT_MAX", 900), mock.patch.object(guard, "AUDIT_FILES", 5):
            b = self.torn(after=1)
            self.assertTrue(guard.ack_break(b["file"], b["line"], b["sha"], "stromausfall")[0])
            for i in range(12):
                guard.log("config_switch", detail=f"weiter {i:03d} " + "z" * 40)
            self.assertGreater(len(guard.audit_files()), 2)
            self.assertLess(len(guard.audit_files()), 5, "the file with the break is still kept")
            r = guard.verify()
            self.assertIsNone(r["broken"], r)
            self.assertNotEqual(r["acked"][0]["file"], "audit.log", "the line moved on with its file")
            self.assertEqual((r["acked"][0]["line"], r["acked"][0]["sha"]), (4, b["sha"]))

    def test_the_daily_check_is_silent_for_a_confirmed_break_and_alerts_for_a_new_one(self):
        b = self.torn()
        now = 1_000_000
        guard.chain_daily(now)
        self.assertEqual(len(guard.alerts()), 1)
        guard.ack_break(b["file"], b["line"], b["sha"], "stromausfall")
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            r = guard.chain_daily(now + 60)
        self.assertEqual(guard.alerts(), [])
        self.assertIn("audit: chain confirmed |", out.getvalue())
        self.assertEqual(r["open"], 0)
        guard.chain_daily(now + 86400)
        events = [json.loads(x)["event"] for x in self.lines() if x.startswith(b'{"t": ') and x.endswith(b"}")]
        self.assertEqual(events.count("audit_chain_broken"), 1, "no new entry for the confirmed break")
        with open(self.audit, "ab") as f:
            f.write(b"\x00\x00\x00\n")                       # a new break
        guard.chain_daily(now + 2 * 86400)
        self.assertEqual(len(guard.alerts()), 1)
        events = [json.loads(x)["event"] for x in self.lines() if x.startswith(b'{"t": ') and x.endswith(b"}")]
        self.assertEqual(events.count("audit_chain_broken"), 2)


class AckEndpoint(AuditDir):
    """POST /api/audit/ack: only an admin (Verwalter and admin profiles' code: test_coadmin), a reason of the list,
    exactly the break the check reports, size limit, CSRF and rate limit."""

    def setUp(self):
        super().setUp()
        with guard._rate_lock:
            guard._rate.clear()
        self.b = Ack.torn(self)

    def body(self, **kw):
        return {"file": self.b["file"], "line": self.b["line"], "sha": self.b["sha"], "reason": "stromausfall", **kw}

    def test_an_admin_confirms_and_sees_it_confirmed(self):
        d = ADMIN.get("/api/audit/check").json()
        self.assertEqual(d["chain"]["broken"]["sha"], self.b["sha"])
        self.assertEqual(d["reasons"], [[k, de, en] for k, (de, en) in guard.ACK_REASONS.items()])
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            r = ADMIN.post("/api/audit/ack", json=self.body())
        self.assertEqual(r.status_code, 200, r.text)
        c = r.json()["chain"]
        self.assertIsNone(c["broken"])
        self.assertEqual(c["acked"][0]["ack"]["say"], list(guard.ACK_REASONS["stromausfall"]))
        self.assertEqual(c["acked"][0]["say"], list(guard.BREAK_WORDS["unlesbar"]))
        self.assertIn("audit: ack ok | unlesbar | stromausfall | main", out.getvalue())
        self.assertIsNone(ADMIN.get("/api/audit/check").json()["chain"]["broken"])

    def test_refused_without_login_out_of_the_list_or_for_another_break(self):
        self.assertEqual(TestClient(panel.app).post("/api/audit/ack", json=self.body()).status_code, 401)
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertEqual(ADMIN.post("/api/audit/ack", json=self.body(reason="sonstwas")).status_code, 400)
            self.assertEqual(ADMIN.post("/api/audit/ack", json=self.body(sha="a" * 64)).status_code, 409)
            self.assertEqual(ADMIN.post("/api/audit/ack", json=self.body(line="4")).status_code, 400)
            self.assertEqual(ADMIN.post("/api/audit/ack", json=self.body(sha="<b>")).status_code, 400)
        said = out.getvalue()
        for word in ("audit: ack refused | grund", "audit: ack refused | anders", "audit: ack refused | form"):
            self.assertIn(word, said)
        self.assertIsNotNone(guard.verify()["broken"], "nothing was confirmed")

    def test_size_limit_csrf_and_rate_limit(self):
        big = json.dumps(self.body(pad="x" * 2000))
        self.assertEqual(ADMIN.post("/api/audit/ack", content=big,
                                    headers={"Content-Type": "application/json"}).status_code, 413)
        self.assertEqual(ADMIN.post("/api/audit/ack", json=self.body(),
                                    headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertIsNotNone(guard.verify()["broken"])
        codes = [ADMIN.post("/api/audit/ack", json=self.body(sha="b" * 64)).status_code for _ in range(12)]
        self.assertEqual(codes[-1], 429)
        self.assertIn(("POST", "/api/audit/ack"), __import__("stufen").LIST)

    def test_the_page_offers_the_button_with_the_reasons_of_the_server(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js", "logs.js"), encoding="utf-8") as f:
            js = f.read()
        body = js[js.index("function chainAck("):js.index("// „Protokoll prüfen“ : the chain")]
        for need in ("d.reasons", "/api/audit/ack", "b.sha", "codeLock(go,'protect')", "Bruch als geprüft bestätigen"):
            self.assertIn(need, body)
        self.assertIn("b.ack.t", js[js.index("function chainAcked("):])
        for word in ("Stromausfall", "Karte voll"):
            self.assertNotIn(word, js, "the reasons come from guard.ACK_REASONS only")


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
    def test_only_an_admin_checks(self):
        self.assertEqual(TestClient(panel.app).get("/api/audit/check").status_code, 401)
        r = ADMIN.get("/api/audit/check")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertIn("ok", d["chain"])
        self.assertIsNone(d["nas"])

    def test_a_break_comes_with_its_kind_in_fixed_words(self):
        broken = {"ok": False, "lines": 3, "old": 0, "files": 1, "first": 1, "last": 3, "head": "", "breaks": 1,
                  "broken": {"file": "audit.log", "line": 2, "t": 0, "kind": "unlesbar", "before": 1, "after_ok": True}}
        with mock.patch.object(guard, "verify", return_value=broken):
            d = ADMIN.get("/api/audit/check").json()
        self.assertEqual(d["chain"]["broken"]["say"], list(guard.BREAK_WORDS["unlesbar"]))

    def test_the_page_says_the_kind_and_the_time_before_a_break(self):
        js = open(os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js", "logs.js"),
                  encoding="utf-8").read()
        body = js[js.index("function chainBreak("):js.index("function chainSay(")]
        for need in ("b.say", "say[0]", "say[1]", "b.before", "c.breaks", "b.after_ok"):
            self.assertIn(need, body)
        self.assertIn("chainBreak(c,day)", js[js.index("function chainSay("):])
        self.assertNotIn("danach wurde etwas verändert", js)

    def test_without_a_nas_copy_the_answer_says_so(self):
        with mock.patch.object(offsite, "_read", return_value={}):
            d = ADMIN.get("/api/audit/check?nas=1").json()
        self.assertIsNone(d["nas"])
        self.assertEqual(d["nas_error"], "")


if __name__ == "__main__":
    unittest.main()
