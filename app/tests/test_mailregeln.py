"""Mail-Regeln (mailregeln.py, Mailclient Stufe B, Dominik 2026-10-19 „2a 3a“): rules made on the page E-Mail.

- A rule is fixed data: sender (address or domain), optional subject word, recipient, attachment; then a folder
  of that mailbox (never trash, junk, sent or drafts), read, flag, not in Für dich. Anything else is refused.
- Rules take only mail that came in after the first look; the first rule that fits decides, in the profile's order.
- Probelauf counts and changes nothing; „auch die vorhandenen“ (with the code) moves, „Rückgängig“ brings them back.
- No ping-pong (plan mail-lernen 1a + 2a): a mail a rule moved and the person put back stays in the inbox.
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

    def test_no_ping_pong_a_mail_put_back_stays(self):
        """Plan mail-lernen 1a + 2a (Dominik 2026-10-30): what a rule moved is remembered by its Message-ID; when the person
        puts it back into the inbox (new UID, same Message-ID), no rule takes it again, and „auch die vorhandenen“ neither."""
        rid = self.save({"from": "@autohaus-kehl.de"}, {"folder": "Auto"}).json()["saved"]
        mailregeln.run(self.uid)                                                            # first look
        FMB.put("INBOX", helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Termin", "…", mid="<pp-1@x>"))
        self.assertEqual(mailregeln.run(self.uid)["taken"], 1)
        moved = mailregeln.load(self.uid)["moved"]
        self.assertEqual([(x["mid"], x["aid"], x["folder"], x["rid"]) for x in moved], [("<pp-1@x>", self.acct, "Auto", rid)])
        self.assertEqual(set(moved[0]), {"mid", "aid", "folder", "rid", "t"})               # no sender, no subject
        back0 = mailregeln.for_live()["back"]
        FMB.put("INBOX", FMB.boxes["Auto"].pop()["raw"])                                     # the person puts it back
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for _ in range(2):
                self.assertEqual(mailregeln.run(self.uid)["taken"], 0)
            FMB.put("INBOX", FMB.boxes["INBOX"].pop()["raw"])                                # and once more: still stays
            self.assertEqual(mailregeln.run(self.uid)["taken"], 0)
        self.assertEqual((FMB.boxes["Auto"], FMB.boxes["INBOX"][-1]["raw"].count(b"pp-1@x")), ([], 1))
        self.assertIn("mail: rule skip | user_moved | 1 |", out.getvalue())
        self.assertNotIn("autohaus", out.getvalue())
        self.assertEqual(mailregeln.for_live()["back"], back0 + 1)                          # counted once
        r = self.c.post(f"/api/profile/mail/rules/{rid}/apply")                              # the old ones: not this one
        self.assertEqual((r.status_code, FMB.boxes["Auto"][-1]["raw"].count(b"r-1@x")), (200, 1), r.text)
        self.assertEqual(r.json()["n"], 1)
        self.assertEqual(len(mailregeln.load(self.uid)["moved"]), 2)                         # apply remembers too
        # one list of both sorters: a mail „Postfach aufräumen“ moved counts, „Zurück“ wins
        st = {"log": [{"id": "a", "aid": self.acct, "mid": "<t-1@x>", "folder": "KI/Werbung"},
                      {"id": "b", "aid": self.acct, "mid": "<t-2@x>", "folder": "KI/Werbung", "undone": True},
                      {"id": "c", "aid": "other", "mid": "<t-3@x>", "folder": "KI/Werbung"}]}
        m = mailregeln.spark_moved(self.uid, self.acct, st=st)
        self.assertEqual({k: v["by"] for k, v in m.items()}, {"<pp-1@x>": "rule", "<r-1@x>": "rule", "<t-1@x>": "tidy", "<t-2@x>": "tidy"})
        self.assertTrue(mailregeln.user_moved(m, "<t-1@x>", "INBOX"))
        self.assertFalse(mailregeln.user_moved(m, "<t-1@x>", "KI/Werbung"))                 # still where the Spark put it
        self.assertTrue(mailregeln.user_moved(m, "<t-2@x>", "KI/Werbung"))
        self.assertIsNone(mailregeln.user_moved(m, "<r-2@x>", "INBOX"))
        self.assertIsNone(mailregeln.user_moved(m, "", "INBOX"))

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



class Suggest(unittest.TestCase):
    """Regel-Vorschläge aus dem Ablegen (Dominik 2026-10-21 „ok“ and 09:55 „nur die Ordner unterhalb deines KI Ordners“):
    the night looks only below the KI folder and only when one changed; what „Mails aufräumen“ moved never counts; a
    sender needs SUGGEST_MIN mails and SUGGEST_SHARE of them in one folder; a domain only with a clear picture, never
    freemail; at most SUGGEST_DAY a night; a rule only after a click, which (or „Nicht mehr fragen“) takes it off."""

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True)
        cls.c, cls.uid = profile("Ablage Alma")
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False, mail_manage=False)
        mailregeln.forget(cls.uid)
        tidy.forget(cls.uid)

    def setUp(self):
        fill()
        mail.IMAP = FMB
        mailregeln.forget(self.uid)
        tidy._mut(self.uid, lambda d: d.update(root="KI", rules=[], log=[]))

    def put(self, folder, frm, n, tag):
        for i in range(n):
            FMB.put(folder, helpers.box_mail(frm, f"Post {i}", "…", mid=f"<{tag}-{i}@x>"))

    def test_only_below_the_ki_folder_and_fixed_rules(self):
        self.put("KI/Strom", "Stadtwerke <rechnung@stadtwerke.de>", 6, "sw")
        FMB.put("INBOX", helpers.box_mail("Stadtwerke <rechnung@stadtwerke.de>", "Neu", "…"))
        self.put("Auto", "Kehl <werkstatt@kehl.de>", 6, "auto")                    # not below the KI folder
        self.put("KI/A", "Mix <mix@verein.de>", 3, "ma")                           # spread over two folders
        self.put("KI/B", "Mix <mix@verein.de>", 3, "mb")
        self.put("KI/Werbung", "Shop <promo@shop.de>", 6, "pr")                    # moved by „Mails aufräumen“
        tidy._mut(self.uid, lambda d: d.update(log=[{"id": f"l{i}", "run": "r", "t": 10 ** 10, "aid": self.acct,
                                                     "mid": f"<pr-{i}@x>", "folder": "KI/Werbung"} for i in range(6)]))
        self.put("KI/Bestellungen", "A <a@amazon.de>", 3, "a1")                    # one domain, two addresses
        self.put("KI/Bestellungen", "B <b@amazon.de>", 3, "a2")
        self.put("KI/Freunde", "X <x@gmail.com>", 3, "g1")                          # freemail: never as a domain
        self.put("KI/Freunde", "Y <y@gmail.com>", 3, "g2")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = mailregeln.suggest(self.uid)
        self.assertEqual(sorted((x["from"], x["folder"], x["n"], x["inbox"]) for x in got),
                         [("@amazon.de", "KI/Bestellungen", 6, 0), ("rechnung@stadtwerke.de", "KI/Strom", 6, 1)])
        self.assertIn("mail: rule suggestions | 2 |", out.getvalue())
        self.assertNotIn("stadtwerke", out.getvalue())                               # never a sender in the log
        # nothing changed below the KI folder: no folder is read again
        FMB.calls.clear()
        self.assertEqual(mailregeln.suggest(self.uid), [])
        self.assertFalse([c for c in FMB.calls if c[0] == "select"])
        # the page shows them; a rule (from the click) or „Nicht mehr fragen“ takes one off
        d = self.c.get("/api/profile/mail/rules").json()
        self.assertEqual(len(d["suggest"]), 2)
        r = self.c.post("/api/profile/mail/rules", json={"account": self.acct, "when": {"from": "rechnung@stadtwerke.de"},
                                                        "then": {"folder": "KI/Strom"}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([x["from"] for x in r.json()["suggest"]], ["@amazon.de"])
        r = self.c.post("/api/profile/mail/rules/never", json={"account": self.acct, "from": "@amazon.de", "folder": "KI/Bestellungen"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get("/api/profile/mail/rules").json()["suggest"], [])
        # a new mail there: looked at again, but never asked again and the rule's sender is left out
        self.put("KI/Bestellungen", "A <a@amazon.de>", 1, "a3")
        self.assertEqual(mailregeln.suggest(self.uid), [])

    def test_cards_in_the_assistant_with_the_page_buttons(self):
        """Each suggestion is a card „Regel-Vorschlag“ (vorgaenge.QUELLEN): „Regel anlegen und ablegen“ only while some
        of its mails lie in the inbox; a button runs the page's own rule; taking one on the page closes its card."""
        import vorgaenge
        helpers.set_config(vorgaenge=True)
        self.addCleanup(helpers.set_config, vorgaenge=False)
        self.put("KI/Strom", "Stadtwerke <rechnung@stadtwerke.de>", 6, "sw")
        FMB.put("INBOX", helpers.box_mail("Stadtwerke <rechnung@stadtwerke.de>", "Neu", "…"))
        self.put("KI/Verein", "Verein <info@verein.de>", 5, "vn")
        self.put("KI/Shop", "Shop <post@shop.de>", 5, "sh")
        got = {x["from"]: x for x in mailregeln.suggest(self.uid)}
        cards = {x["key"]: x for x in vorgaenge._load(self.uid)["items"] if x["art"] == "regel"}
        self.assertEqual(set(cards), {f"regel:{x['id']}" for x in got.values()})
        sw, vn, sh = (cards[f"regel:{got[a]['id']}"] for a in ("rechnung@stadtwerke.de", "info@verein.de", "post@shop.de"))
        self.assertIn("rechnung@stadtwerke.de", sw["titel"])
        self.assertEqual([k["k"] for k in vorgaenge.public(self.uid, sw)["acts"]], ["rg_ablegen", "rg_regel", "rg_nie", "spaeter"])
        self.assertEqual([k["k"] for k in vorgaenge.public(self.uid, vn)["acts"]], ["rg_regel", "rg_nie", "spaeter"])
        with self.assertRaises(vorgaenge.HTTPException):
            vorgaenge.act(self.uid, vn["id"], "rg_ablegen")                         # none of its mails in the inbox
        out = vorgaenge.act(self.uid, sw["id"], "rg_ablegen")
        self.assertIn("1 Mails aus dem Posteingang", out["text"])
        self.assertEqual([(r["when"]["from"], r["then"]["folder"]) for r in mailregeln.load(self.uid)["rules"]],
                         [("rechnung@stadtwerke.de", "KI/Strom")])
        self.assertEqual(len(FMB.boxes["KI/Strom"]), 7)
        self.assertEqual(vorgaenge.act(self.uid, vn["id"], "rg_nie")["text"], "Gut, dazu frage ich nicht mehr.")
        self.c.post("/api/profile/mail/rules", json={"account": self.acct, "when": {"from": "post@shop.de"}, "then": {"folder": "KI/Shop"}})
        state = {x["key"]: x["zustand"] for x in vorgaenge._load(self.uid)["items"] if x["art"] == "regel"}
        self.assertEqual(state, {sw["key"]: "erledigt", vn["key"]: "weg", sh["key"]: "erledigt"})
        self.assertEqual(mailregeln.load(self.uid)["suggest"], [])
        helpers.set_config(mail_manage=False)                                      # without Mails ordnen: no button
        try:
            self.assertEqual(mailregeln._card_acts(self.uid, sw), set())
        finally:
            helpers.set_config(mail_manage=True)

    def test_at_most_three_a_night_and_only_at_night(self):
        for i in range(5):
            self.put(f"KI/F{i}", f"S <s{i}@firma{i}.de>", 5 + i, f"f{i}")
        import datetime
        day = datetime.datetime(2026, 10, 21, 14, 0).timestamp()
        night = datetime.datetime(2026, 10, 22, 3, 0).timestamp()
        others = {u: "2026-10-22" for u in mailregeln.profiles.user_ids() if u != self.uid}   # one profile a minute
        mailregeln._sug_day.update(others)
        mailregeln._sug_day.pop(self.uid, None)
        asyncio.run(mailregeln.due_once(now=day))
        self.assertEqual(mailregeln.load(self.uid)["suggest"], [])
        asyncio.run(mailregeln.due_once(now=night))
        got = mailregeln.load(self.uid)["suggest"]
        self.assertEqual([x["n"] for x in got], [9, 8, 7])                          # the strongest first
        helpers.set_config(mail_manage=False)                                         # off: no look
        try:
            mailregeln.forget(self.uid)
            mailregeln._sug_day.pop(self.uid, None)
            asyncio.run(mailregeln.due_once(now=night))
            self.assertEqual(mailregeln.load(self.uid)["suggest"], [])
        finally:
            helpers.set_config(mail_manage=True)

class Stats(unittest.TestCase):
    """Mail-Statistik (Dominik 2026-10-21 „6“): who writes most in 30 days and the mails a week, counted by the panel
    from the listing the Mail-Vorrat keeps; a sender with a rule says so; logs carry numbers only; with Mails ordnen."""

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True)
        cls.c, cls.uid = profile("Statistik Stella")
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False, mail_manage=False)
        mailregeln.forget(cls.uid)

    def test_counts_weeks_rules_and_logs(self):
        import datetime
        from unittest import mock
        now = 1_800_000_000.0
        day = lambda d: datetime.datetime.fromtimestamp(now - d * 86400 - 60, datetime.timezone.utc)
        found = [(self.acct, i, {"from": "Heise <news@heise.de>", "unread": i < 2, "date": day(i)}) for i in range(5)]
        found += [(self.acct, 10 + i, {"from": "anna@autohaus-kehl.de", "unread": False, "date": day(8 + i)}) for i in range(2)]
        found += [(self.acct, 20, {"from": "Shop <promo@shop.de>", "unread": True, "date": day(25)})]
        mailregeln.forget(self.uid)
        self.assertEqual(self.c.post("/api/profile/mail/rules", json={"account": self.acct, "when": {"from": "anna@autohaus-kehl.de"},
                                                                     "then": {"folder": "Auto"}}).status_code, 200)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(mail, "lookup", return_value=((found, [], 0), None)):
            s = mailregeln.stats(self.uid, now)
            r = self.c.get("/api/profile/mail/stats")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((s["total"], s["unread"], s["weeks"]), (8, 3, [5, 2, 0, 1]))
        self.assertEqual([(x["addr"], x["name"], x["n"], x["unread"], x["rule"]) for x in s["senders"]],
                         [("news@heise.de", "Heise", 5, 2, False), ("anna@autohaus-kehl.de", "", 2, 0, True),
                          ("promo@shop.de", "Shop", 1, 1, False)])
        self.assertIn("mail: stats shown | 8 mails, 3 senders", out.getvalue())
        for secret in ("heise", "anna", "shop"):
            self.assertNotIn(secret, out.getvalue())
        with mock.patch.object(mail, "lookup", side_effect=TimeoutError):
            self.assertEqual(self.c.get("/api/profile/mail/stats").json(), {"loading": True})
        self.assertIn(TestClient(panel.app).get("/api/profile/mail/stats").status_code, (401, 403))
        helpers.set_config(mail_manage=False)
        try:
            self.assertEqual(self.c.get("/api/profile/mail/stats").status_code, 403)
        finally:
            helpers.set_config(mail_manage=True)


if __name__ == "__main__":
    unittest.main()
