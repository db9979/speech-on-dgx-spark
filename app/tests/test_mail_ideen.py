"""Ideen aus pl_mail (Dominik 2026-11-13 „1-7“, plan pl-mail/plan.md), stage S1, without the model:
- 5 Suche erweitern: an:/to:, vor:/before:, nach:/after:/seit: as fixed words (mail._words, mail.day_of), checked on
  the header (fits) and asked of the server (BEFORE, SINCE, TO); ordner:/in: is the page's (it opens the folder), never
  a word the server searches for; a date that is none is no word.
- 4 Warum liegt die Mail hier: mailregeln.placed from the lists that are there anyway (rule or tidying, undone);
  fuerdich.echtheit only from the top Authentication-Results header of the own server.
- 7 Postfach-Zustand: mail.zustand names a mailbox only after ZUSTAND_AFTER without an answer, with a fixed reason.
Fixed days and times, no wall clock, no network."""
import datetime
import email
import email.policy
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import mail  # noqa: E402
import fuerdich  # noqa: E402
import mailregeln  # noqa: E402
import tidy  # noqa: E402

TODAY = datetime.date(2026, 11, 13)
UTC = datetime.timezone.utc


def head(**k):
    h = {"from": "Anna <anna@example.de>", "to": "ich@example.de", "subject": "Umzug", "attach": False,
         "flagged": False, "unread": False, "date": datetime.datetime(2026, 11, 10, 12, 0, tzinfo=UTC)}
    h.update(k)
    return h


class Suche(unittest.TestCase):
    def test_date_words(self):
        for text, want in (("heute", "2026-11-13"), ("gestern", "2026-11-12"), ("today", "2026-11-13"),
                           ("1.11.", "2026-11-01"), ("24.12.", "2025-12-24"), ("13.11.2026", "2026-11-13"),
                           ("3.4.25", "2025-04-03"), ("2026-10-01", "2026-10-01"), ("32.1.", ""), ("morgen", ""), ("abc", "")):
            with self.subTest(text=text):
                self.assertEqual(mail.day_of(text, TODAY), want)

    def test_words(self):
        w = mail._words("an:paula vor:13.11. nach:1.11. ordner:Rechnungen in:Archiv seit:gestern Umzug", TODAY)
        self.assertEqual(w, ["to:paula", "before:2026-11-13", "after:2026-11-01", "after:2026-11-12", "umzug"])
        self.assertEqual(mail._words("vor:nirgends", TODAY), [])   # no date: no word, never the text „nirgends“

    def test_fits_on_the_header(self):
        h = head()
        self.assertTrue(mail.fits(["to:ich@"], h))
        self.assertFalse(mail.fits(["to:paula"], h))
        self.assertTrue(mail.fits(["before:2026-11-11"], h))
        self.assertFalse(mail.fits(["before:2026-11-10"], h))   # vor: the day itself is not before
        self.assertTrue(mail.fits(["after:2026-11-10"], h))      # nach: from that day on
        self.assertFalse(mail.fits(["after:2026-11-11"], h))
        self.assertFalse(mail.fits(["after:2026-11-01"], head(date=None)))

    def test_server_keys(self):
        crit, lit, after = mail._criteria(["to:paula", "before:2026-11-13", "after:2026-11-01"], False)
        self.assertEqual(crit, ["TO", '"paula"', "BEFORE", "13-Nov-2026", "SINCE", "01-Nov-2026"])
        self.assertIsNone(lit)
        self.assertEqual(after, ["before:2026-11-13", "after:2026-11-01"])


def msg(ar):
    raw = (f"Authentication-Results: {ar}\r\n" if ar else "") + "From: Bank <info@bank.example>\r\nSubject: x\r\n\r\nHallo\r\n"
    return email.message_from_string(raw, policy=email.policy.default)


class Echtheit(unittest.TestCase):
    def test_states(self):
        s = "Bank <info@bank.example>"
        self.assertEqual(fuerdich.echtheit(msg("mx.own; dmarc=pass header.from=bank.example"), s), "ok")
        self.assertEqual(fuerdich.echtheit(msg("mx.own; dkim=pass header.d=bank.example"), s), "ok")
        self.assertEqual(fuerdich.echtheit(msg("mx.own; dmarc=fail header.from=bank.example"), s), "falsch")
        self.assertEqual(fuerdich.echtheit(msg("mx.own; spf=fail smtp.mailfrom=bank.example"), s), "falsch")
        self.assertEqual(fuerdich.echtheit(msg("mx.own; spf=fail smtp.mailfrom=other.example"), s), "")
        self.assertEqual(fuerdich.echtheit(msg(""), s), "")
        # only the top header counts: a pass lower down (anyone can write it) confirms nothing
        two = email.message_from_string("Authentication-Results: mx.own; dmarc=fail\r\nAuthentication-Results: x; dmarc=pass\r\n"
                                        "From: info@bank.example\r\n\r\nx\r\n", policy=email.policy.default)
        self.assertEqual(fuerdich.echtheit(two, "info@bank.example"), "falsch")


class Warum(unittest.TestCase):
    def test_placed_by_rule_and_tidy(self):
        d = {"rules": [{"id": "r1", "when": {"from": "@shop.example", "subject": "", "to": "", "attach": False}, "then": {"folder": "Shop"}}],
             "moved": []}
        moved = {"<a@x>": {"mid": "<a@x>", "aid": "m1", "folder": "Shop", "rid": "r1", "t": 5, "by": "rule"},
                 "<b@x>": {"mid": "<b@x>", "aid": "m1", "folder": "Spark/Newsletter", "cat": "newsletter", "why": "List-Id",
                           "t": 6, "by": "tidy", "undone": True},
                 "<c@x>": {"mid": "<c@x>", "aid": "m1", "folder": "Alt", "rid": "weg", "t": 7, "by": "rule"}}
        with mock.patch.object(mailregeln, "load", return_value=d), mock.patch.object(mailregeln, "spark_moved", return_value=moved):
            r = mailregeln.placed("u", "m1:17", "<a@x>")
            self.assertEqual((r["by"], r["folder"], r["rule"]["from"], r["rule"]["gone"]), ("rule", "Shop", "@shop.example", False))
            t = mailregeln.placed("u", "m1:18", "<b@x>")
            self.assertEqual((t["by"], t["cat"], t["why"], t["undone"]), ("tidy", "newsletter", "List-Id", True))
            self.assertTrue(mailregeln.placed("u", "m1:19", "<c@x>")["rule"]["gone"])
            self.assertIsNone(mailregeln.placed("u", "m1:20", "<z@x>"))
            self.assertIsNone(mailregeln.placed("u", "m1:20", ""))
        # the one sentence for every device, fixed words with the values
        self.assertEqual(r["satz"][0], "Hierher gelegt von deiner Regel (Absender endet auf @example.de) → „Shop“".replace("example.de", "shop.example"))
        self.assertEqual(t["satz"][0], "Hierher gelegt vom Aufräumen: Newsletter (List-Id) → „Spark/Newsletter“. Du hast sie danach zurückgeholt.")


class Zustand(unittest.TestCase):
    def test_only_after_a_while_with_a_fixed_reason(self):
        accts = {"accounts": [{"id": "m1", "name": "GMX"}, {"id": "m2", "name": "Privat"}, {"id": "m3", "name": "Neu"}]}
        now = 1_800_000_000
        svc = {"m1": {"try": now, "ok": now - 3600, "why": "anmeldung"},
               "m2": {"try": now, "ok": now - 60, "why": "nicht_erreichbar"},   # a blink: not named yet
               "m3": {"try": now, "ok": 0, "why": "fehler"}}
        with mock.patch.object(mail, "get", return_value=accts):
            z = mail.zustand("u", lambda kind, key: svc.get(key, {}), now)
        self.assertEqual([(x["name"], x["why"], x["ok"]) for x in z], [("GMX", "anmeldung", now - 3600), ("Neu", "fehler", 0)])
        self.assertIn("E-Mail → Einstellungen", z[0]["satz"][0])   # the way, a jump link on every device


if __name__ == "__main__":
    unittest.main()
