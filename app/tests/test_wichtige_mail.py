"""Wichtige Mail erst nach dem Einordnen (proactive.sort, Dominik 2026-10-26 „1-4“): fixed rules before any card.

- A mail no longer in the inbox (a rule or „Mails aufräumen“ moved it) never becomes a card „Wichtige Mail“.
- While „Mails aufräumen“ has not looked at a new mail yet, it waits (at most SORT_WAIT), then the rules decide alone.
- An automatic sender, a list, bulk mail, a social network, a login code, a mail a mail rule would move and a sender on
  the profile's „Nicht wichtig“ list are never „wichtig“; the model is not even asked about them.
- The senders on the profile's own list (pro_mail_from) always count while the mail is in the inbox.
- The card's „Nicht wichtig“ puts its sender on the list (pro_mail_not); open cards are tidied once by the same rules.
- Logs carry fixed words and numbers only (never a sender or subject); Live: numbers only.

The fake mailbox (helpers.FakeMailbox); the model's answer is a stub (no wall clock, no network).
"""
import asyncio
import contextlib
import datetime
import io
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import mail  # noqa: E402
import mailregeln  # noqa: E402
import proactive  # noqa: E402
import profiles  # noqa: E402
import tidy  # noqa: E402
import vorgaenge  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FMB = helpers.FakeMailbox
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = datetime.datetime.now(datetime.timezone.utc)


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def raw(frm, subject, extra=""):
    return (f"From: {frm}\r\nTo: {helpers.MAIL_USER}\r\nSubject: {subject}\r\nMessage-ID: <{abs(hash(subject))}@x>\r\n"
            f"Date: Mon, 26 Oct 2026 07:00:00 +0100\r\n{extra}Content-Type: text/plain; charset=utf-8\r\n\r\nHallo\r\n").encode()


MAILS = {   # name: (from, subject, extra headers)
    "anna": ("Anna <anna@example.de>", "Treffen morgen?", ""),
    "xcode": ("Xcode Cloud <no_reply@email.apple.com>", "Spark -- Build 792 failed (main)", ""),
    "github": ("ottelo <notifications@github.com>", "Re: [ottelo9/tasmota-sml-script] Issue #74",
               "List-ID: <tasmota-sml-script.ottelo9.github.com>\r\n"),
    "linkedin": ("Stefanie Benc <messages-noreply@linkedin.com>", "Stefanie hat Ihnen geschrieben", ""),
    "code": ("Bank <kunde@bank.de>", "Ihr Bestätigungscode", ""),
    "werkstatt": ("Autohaus <anna@autohaus-kehl.de>", "Ihr Wagen ist fertig", ""),
    "chef": ("Chef <chef@firma.de>", "Bitte heute noch", ""),
}


class Sort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True, mail_tidy=True, proactive=True, vorgaenge=True,
                           systemone=True, systemone_mail=True)
        FMB.reset()
        cls.c, cls.uid = profile("Wichtig Wanda")
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False, mail_manage=False, mail_tidy=False, proactive=False, vorgaenge=False,
                           systemone=False, systemone_mail=False)
        mailregeln.forget(cls.uid)
        tidy._mut(cls.uid, lambda d: tidy.acct_state(d, cls.acct).update(mode="off"))

    def setUp(self):
        FMB.reset()
        FMB.boxes["Archive"] = []
        self.uids = {k: FMB.put("INBOX", raw(*v)) for k, v in MAILS.items()}
        mailregeln.forget(self.uid)
        tidy._mut(self.uid, lambda d: tidy.acct_state(d, self.acct).update(mode="off", last_uid=0))
        profiles.save_settings(self.uid, {"pro_on": True, "pro_mail": True, "pro_mail_smart": True,
                                          "pro_mail_from": "", "pro_mail_not": ""})
        proactive._mut(self.uid, lambda st: st.clear())
        vorgaenge.forget(self.uid)
        r = self.c.post("/api/profile/mail/rules", json={"account": self.acct, "when": {"from": "@autohaus-kehl.de"},
                                                          "then": {"folder": "Archive"}})
        assert r.status_code == 200, r.text
        self.asked, self.said = [], []

    def heads(self, names, date=NOW):
        return [(self.acct, self.uids.get(n, 999), {"from": MAILS[n][0] if n in MAILS else "Weg <weg@x.de>",
                                                    "subject": MAILS[n][1] if n in MAILS else "weg", "date": date,
                                                    "unread": True}) for n in names]

    def check(self, heads):
        """check_mail as the minute loop runs it, past its first look; returns its log."""
        async def important(h):
            self.asked.append(h["subject"])
            return 0.95

        async def deliver(u, kind, text, why="", data="", **kw):
            self.said.append(text)
        out = io.StringIO()
        with mock.patch.object(mail, "find", lambda *a, **k: (heads, [], False)), \
                mock.patch.object(proactive, "important", important), mock.patch.object(proactive, "deliver", deliver), \
                contextlib.redirect_stdout(out):
            proactive._mut(self.uid, lambda st: st.update(mail_checked=0, mail_since=NOW.timestamp() - 3600,
                                                          mail_smart_since=NOW.timestamp() - 3600))
            asyncio.run(proactive.check_mail(self.uid, proactive.prefs(self.uid)))
        return out.getvalue()

    def test_fixed_rules_before_the_model(self):
        verdict = proactive.sort(self.uid, self.heads(list(MAILS) + ["weg"]))
        u = self.uids
        ref = lambda n: f"{self.acct}:{u.get(n, 999)}"   # noqa: E731
        self.assertEqual(verdict[ref("anna")], "")
        self.assertEqual(verdict[ref("chef")], "")
        for n in ("xcode", "github", "linkedin", "code"):
            self.assertEqual(verdict[ref(n)], "auto", n)
        self.assertEqual(verdict[ref("werkstatt")], "rule")
        self.assertEqual(verdict[ref("weg")], "gone")
        log = self.check(self.heads(list(MAILS) + ["weg"]))
        self.assertEqual(sorted(self.said), ["Neue Mail von Anna: Treffen morgen?.", "Neue Mail von Chef: Bitte heute noch."])
        self.assertEqual(sorted(self.asked), ["Bitte heute noch", "Treffen morgen?"])     # the model saw only these
        self.assertIn("proactive: mail sorted | 8 new, 5 not important, 2 asked", log)
        for secret in ("anna", "Anna", "apple", "github", "Treffen", "Build"):
            self.assertNotIn(secret, log)
        self.assertGreaterEqual(proactive.mail_today()["out"], 5)
        self.assertGreaterEqual(proactive.mail_today()["cards"], 2)
        self.said.clear()
        self.check(self.heads(list(MAILS)))                                               # each mail once
        self.assertEqual(self.said, [])

    def test_own_list_counts_while_in_the_inbox(self):
        profiles.save_settings(self.uid, {"pro_mail_from": "apple.com", "pro_mail_smart": False})
        self.check(self.heads(["xcode", "anna", "weg"]))
        self.assertEqual(self.said, ["Neue Mail von Xcode Cloud: Spark -- Build 792 failed (main)."])
        self.assertEqual(self.asked, [])

    def test_waits_for_the_tidying(self):
        tidy._mut(self.uid, lambda d: tidy.acct_state(d, self.acct).update(mode="safe", last_uid=self.uids["anna"] - 1))
        self.assertEqual(proactive.sort(self.uid, self.heads(["anna"]))[f"{self.acct}:{self.uids['anna']}"], "wait")
        self.check(self.heads(["anna"]))
        self.assertEqual((self.said, self.asked), ([], []))
        # „Mails aufräumen“ looked at it and left it in the inbox: now it is asked about
        tidy._mut(self.uid, lambda d: tidy.acct_state(d, self.acct).update(last_uid=self.uids["anna"]))
        self.check(self.heads(["anna"]))
        self.assertEqual(self.said, ["Neue Mail von Anna: Treffen morgen?."])
        # a mail older than SORT_WAIT waits no longer, the fixed rules decide alone
        tidy._mut(self.uid, lambda d: tidy.acct_state(d, self.acct).update(last_uid=1))
        old = NOW - datetime.timedelta(seconds=proactive.SORT_WAIT + 60)
        self.assertEqual(proactive.sort(self.uid, self.heads(["chef"], old))[f"{self.acct}:{self.uids['chef']}"], "")

    def test_not_important_button_and_list(self):
        self.check(self.heads(["anna"]))
        x = next(y for y in vorgaenge._load(self.uid)["items"] if y["art"] == "mail")
        self.assertIn("ausblenden", vorgaenge._allowed_acts(self.uid, x))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            vorgaenge.act(self.uid, x["id"], "ausblenden")
        self.assertIn("proactive: mail sender not important | added", out.getvalue())
        self.assertNotIn("anna", out.getvalue())
        self.assertEqual(proactive.not_important(self.uid), ["anna@example.de"])
        self.assertEqual(vorgaenge._load(self.uid)["items"][0]["zustand"], "weg")
        FMB.put("INBOX", raw("Anna <anna@example.de>", "Noch was"))
        self.uids["anna2"] = FMB.uidnext["INBOX"] - 1
        MAILS["anna2"] = ("Anna <anna@example.de>", "Noch was", "")
        try:
            self.asked.clear()
            self.check(self.heads(["anna2"]))
            self.assertEqual((self.said[1:], self.asked), ([], []))    # the model is not asked about her any more
        finally:
            MAILS.pop("anna2")
        # the list is the profile's setting: shown and changed on the page, one line, at most NOT_MAX characters
        for bad in ("a" * (proactive.NOT_MAX + 1), "x@y.de\nz"):
            self.c.put("/api/profile/settings", json={"pro_mail_not": bad})
            self.assertEqual(proactive.not_important(self.uid), ["anna@example.de"])
        self.assertEqual(self.c.put("/api/profile/settings", json={"pro_mail_not": ""}).status_code, 200)
        self.assertEqual(proactive.not_important(self.uid), [])

    def test_open_cards_tidied_once(self):
        for n in ("xcode", "anna"):
            ref = f"{self.acct}:{self.uids[n]}"
            vorgaenge.put(self.uid, "mail", f"mail:{ref}", f"Wichtige Mail von {n}", "x", daten={"ref": ref, "folder": "INBOX"})
        log = self.check([])
        self.assertIn("proactive: mail cards tidied | 1", log)
        state = {x["key"]: x["zustand"] for x in vorgaenge._load(self.uid)["items"]}
        self.assertEqual(state[f"mail:{self.acct}:{self.uids['xcode']}"], "weg")
        self.assertNotIn(state[f"mail:{self.acct}:{self.uids['anna']}"], ("weg", "erledigt"))
        vorgaenge.reopen(self.uid, f"mail:{self.acct}:{self.uids['xcode']}")
        self.assertNotIn("cards tidied", self.check([]))                 # once only


if __name__ == "__main__":
    unittest.main()
