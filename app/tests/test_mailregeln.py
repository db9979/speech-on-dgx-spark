"""Mail-Regeln (mailregeln.py, Mailclient Stufe B, Dominik 2026-10-19 „2a 3a“): rules made on the page E-Mail.

- A rule is fixed data: sender (address or domain), optional subject word, recipient, attachment; then a folder
  of that mailbox (never trash, junk, sent or drafts), read, flag, not in Für dich. Anything else is refused.
- Rules take only mail that came in after the first look; the first rule that fits decides, in the profile's order.
- Probelauf counts and changes nothing; „auch die vorhandenen“ (with the code) moves, „Rückgängig“ brings them back.
- Off (admin switch) and guests: nothing; the rules of another profile are never touched; logs never carry a
  sender, subject, folder or word of a rule.

The fake mailbox (helpers.FakeMailbox); no wall clock, no network.
"""
import asyncio
import contextlib
import io
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import mail  # noqa: E402
import mailregeln  # noqa: E402
import tidy  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FMB = helpers.FakeMailbox
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def fill():
    FMB.reset(inbox=[helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Werkstatt fertig", "Der Wagen ist fertig.", mid="<r-1@x>"),
                     helpers.box_mail("Heise <news@heise.de>", "Die Woche", "…", mid="<r-2@x>")])
    for name in ("Archive", "Auto", "Newsletter", "Deleted Messages", "Junk"):
        FMB.boxes[name] = []


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True)
        cls.c, cls.uid = profile("Regel Rita")
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False, mail_manage=False)
        mailregeln.forget(cls.uid)

    def setUp(self):
        fill()
        mail.IMAP = FMB
        mailregeln.forget(self.uid)
        for k in [k for k in guard._rate if k[0] == "postordnen"]:
            guard._rate.pop(k, None)

    def save(self, when, then, account=None, **more):
        return self.c.post("/api/profile/mail/rules", json=dict(account=self.acct if account is None else account,
                                                                 when=when, then=then, **more))

    def test_only_real_rules(self):
        for when, then, acct in (({}, {"folder": "Auto"}, None),                                  # no condition
                                 ({"from": "anna@autohaus-kehl.de"}, {}, None),                   # nothing to do
                                 ({"from": "kein absender"}, {"read": True}, None),
                                 ({"from": "@x.de"}, {"folder": "Deleted Messages"}, None),       # never the trash
                                 ({"from": "@x.de"}, {"folder": "Junk"}, None),
                                 ({"from": "@x.de"}, {"folder": "Sent Messages"}, None),
                                 ({"from": "@x.de"}, {"folder": "Gibt es nicht"}, None),
                                 ({"from": "@x.de"}, {"folder": "Auto"}, ""),                     # a folder needs its mailbox
                                 ({"from": "@x.de"}, {"read": True}, "m00000000")):               # not an own mailbox
            self.assertEqual(self.save(when, then, acct).status_code, 400, (when, then, acct))
        self.assertEqual(mailregeln.load(self.uid)["rules"], [])

    def test_new_mail_only_and_the_first_rule_decides(self):
        self.assertEqual(self.save({"from": "@autohaus-kehl.de"}, {"folder": "Auto", "read": True}).status_code, 200)
        self.assertEqual(self.save({"subject": "werkstatt"}, {"flag": True}).status_code, 200)
        self.assertEqual(self.save({"from": "news@heise.de"}, {"folder": "Newsletter"}).status_code, 200)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(mailregeln.run(self.uid)["taken"], 0)      # first look: what is there stays
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)
        FMB.put("INBOX", helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Werkstatt: Rechnung", "Anbei.", mid="<r-3@x>"))
        FMB.put("INBOX", helpers.box_mail("Heise <news@heise.de>", "Neu", "…", mid="<r-4@x>"))
        FMB.put("INBOX", helpers.box_mail("Bob <bob@example.de>", "Hallo", "…", mid="<r-5@x>"))
        with contextlib.redirect_stdout(out):
            r = mailregeln.run(self.uid)
        self.assertEqual(r, {"taken": 2, "errors": 0})
        self.assertEqual([m["raw"].count(b"r-3@x") for m in FMB.boxes["Auto"]], [1])     # first rule: moved, not flagged
        self.assertEqual(len(FMB.boxes["Newsletter"]), 1)
        self.assertEqual(len(FMB.boxes["INBOX"]), 3)                                      # Bob stays, the old ones too
        rules = self.c.get("/api/profile/mail/rules").json()["rules"]
        self.assertEqual([x["month"] for x in rules], [1, 0, 1])
        log = out.getvalue()
        self.assertIn("mail: rules run | 2 taken, 0 errors |", log)
        for word in ("anna", "heise", "Auto", "Newsletter", "Werkstatt"):
            self.assertNotIn(word, log)

    def test_order_changes_who_decides(self):
        a = self.save({"from": "@autohaus-kehl.de"}, {"folder": "Auto"}).json()["saved"]
        b = self.save({"subject": "Werkstatt"}, {"flag": True}).json()["saved"]
        r = self.c.post("/api/profile/mail/rules/order", json={"ids": [b, a]})
        self.assertEqual([x["id"] for x in r.json()["rules"]], [b, a])
        mailregeln.run(self.uid)
        FMB.put("INBOX", helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Werkstatt morgen", "…", mid="<r-6@x>"))
        mailregeln.run(self.uid)
        self.assertEqual(FMB.boxes["Auto"], [])
        self.assertIn("\\Flagged", FMB.boxes["INBOX"][-1]["flags"])

    def test_preview_changes_nothing_apply_and_undo(self):
        n = FMB.total()
        r = self.c.post("/api/profile/mail/rules/test", json={"account": self.acct, "when": {"from": "@autohaus-kehl.de"},
                                                              "then": {"folder": "Auto"}})
        self.assertEqual((r.status_code, r.json()["n"]), (200, 1), r.text)
        self.assertEqual((FMB.total(), FMB.boxes["Auto"]), (n, []))
        rid = self.save({"from": "@autohaus-kehl.de"}, {"folder": "Auto"}).json()["saved"]
        r = self.c.post(f"/api/profile/mail/rules/{rid}/apply")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["n"], d["folder"], len(FMB.boxes["Auto"])), (1, "Auto", 1))
        r = self.c.post("/api/profile/mail/acts/back", json={"account": self.acct, "folder": "Auto", "mids": d["moved"][0]["mids"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((len(FMB.boxes["INBOX"]), FMB.boxes["Auto"]), (2, []))
        self.assertEqual(self.c.post("/api/profile/mail/rules/abcdef12/apply").status_code, 404)

    def test_attachment_and_recipient(self):
        rid = self.save({"subject": "rechnung", "attach": True}, {"flag": True}).json()["saved"]
        self.assertTrue(rid)
        mailregeln.run(self.uid)
        FMB.put("INBOX", helpers.box_mail("Shop <shop@x.de>", "Rechnung 4711", "…", headers={"Content-Type": "multipart/mixed; boundary=x"}))
        FMB.put("INBOX", helpers.box_mail("Shop <shop@x.de>", "Rechnung 4712", "…"))
        mailregeln.run(self.uid)
        self.assertEqual(["\\Flagged" in m["flags"] for m in FMB.boxes["INBOX"][-2:]], [True, False])
        h = {"from": "a@b.de", "to": ["ich@x.de"], "subject": "", "attach": False}
        self.assertTrue(mailregeln.fits({"when": {"to": "ich@x.de"}}, h))
        self.assertFalse(mailregeln.fits({"when": {"to": "du@x.de"}}, h))
        self.assertFalse(mailregeln.fits({"when": {"from": "@b.de.evil"}}, h))
        self.assertTrue(mailregeln.fits({"when": {"from": "@b.de"}}, dict(h, **{"from": "x@mail.b.de"})))

    def test_quiet_keeps_mail_out_of_fuer_dich(self):
        self.save({"from": "@heise.de"}, {"quiet": True}, account="")
        self.assertTrue(mailregeln.quiet(self.uid, "Heise <news@heise.de>", "Die Woche"))
        self.assertFalse(mailregeln.quiet(self.uid, "Anna <anna@autohaus-kehl.de>", "Werkstatt"))

    def test_tab_shows_tidy_rules_too_and_delete(self):
        tidy._mut(self.uid, lambda d: tidy.add_rule(d, "@heise.de", "newsletter"))
        try:
            d = self.c.get("/api/profile/mail/rules").json()
            self.assertEqual([x["match"] for x in d["tidy"]], ["@heise.de"])
        finally:
            tidy._mut(self.uid, lambda d: d.update(rules=[]))
        rid = self.save({"from": "@x.de"}, {"read": True}).json()["saved"]
        self.assertEqual(self.c.delete(f"/api/profile/mail/rules/{rid}").status_code, 200)
        self.assertEqual(self.c.delete(f"/api/profile/mail/rules/{rid}").status_code, 404)

    def test_off_guests_and_others(self):
        rid = self.save({"from": "@x.de"}, {"read": True}).json()["saved"]
        other, _ = profile("Regel Rolf")
        self.assertEqual(other.delete(f"/api/profile/mail/rules/{rid}").status_code, 404)
        self.assertEqual(other.post(f"/api/profile/mail/rules/{rid}/apply").status_code, 404)
        self.assertEqual(len(mailregeln.load(self.uid)["rules"]), 1)
        guest = TestClient(panel.app)
        self.assertIn(guest.get("/api/profile/mail/rules").status_code, (401, 403))
        self.assertIn(guest.post("/api/profile/mail/rules", json={}).status_code, (401, 403))
        helpers.set_config(mail_manage=False)
        try:
            self.assertEqual(self.c.get("/api/profile/mail/rules").status_code, 403)
            self.assertEqual(self.save({"from": "@y.de"}, {"read": True}).status_code, 403)
            asyncio.run(mailregeln.due_once(now=10 ** 10))       # off: no look at any inbox
            self.assertFalse([c for c in FMB.calls if c[0] == "select"])
            self.assertEqual(self.c.delete(f"/api/profile/mail/rules/{rid}").status_code, 200)   # deleting always works
        finally:
            helpers.set_config(mail_manage=True)


if __name__ == "__main__":
    unittest.main()
