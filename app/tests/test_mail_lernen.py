"""Sortieren aus Korrekturen lernen (mailregeln.py, Dominik 2026-10-30 „nach Empfehlung umsetzen“, plan mail-lernen 3a + 4a + 5a).

- Off (admin switch chat.mail_learn, ab Werk aus): nothing is recorded, no folder is made, no rule changes.
- A mail the Spark sorted and the person moved elsewhere is a correction: on the page at once, in the inbox at the next
  look, below the KI folder in the night look; into „Falsch sortiert“ = wrong without a goal.
- Fixed thresholds, never the model: one correction makes the sender an exception of the rule (fits skips it), three in
  30 days pause the rule with a card; a correction with a goal counts three times and brings the card „Regel-Vorschlag“
  with „Regel ändern“ / „Nur Ausnahme“ / „Nicht mehr fragen“; „Falsch sortiert“ brings „Wohin gehört diese Mail?“.
- The night counts a mail the Spark moved where the person put it since; logs carry fixed words and numbers only.

The fake mailbox (helpers.FakeMailbox); no wall clock, no network.
"""
import contextlib
import io
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import mail  # noqa: E402
import mailregeln  # noqa: E402
import postfach  # noqa: E402
import tidy  # noqa: E402
import vorgaenge  # noqa: E402
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
    FMB.reset(inbox=[helpers.box_mail("Alt <alt@x.de>", "Alt", "…", mid="<alt-1@x>")])
    for name in ("Archive", "Auto", "Newsletter", "KI/Strom", "KI/Rechnungen", "KI/Werbung", "Deleted Messages", "Junk"):
        FMB.boxes[name] = []


def cards(uid):
    return {x["key"]: x for x in vorgaenge._load(uid)["items"] if x["art"] == "regel"}


class Learn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True, mail_learn=True, vorgaenge=True)
        cls.c, cls.uid = profile("Lern Lena")
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False, mail_manage=False, mail_learn=False, vorgaenge=False)
        mailregeln.forget(cls.uid)
        tidy.forget(cls.uid)
        vorgaenge.forget(cls.uid)

    def setUp(self):
        fill()
        mail.IMAP = FMB
        helpers.set_config(mail_learn=True)
        mailregeln.forget(self.uid)
        vorgaenge.forget(self.uid)
        tidy._mut(self.uid, lambda d: d.update(root="KI", rules=[], log=[], questions=[]))

    def rule(self, sender, folder):
        r = self.c.post("/api/profile/mail/rules", json={"account": self.acct, "when": {"from": sender}, "then": {"folder": folder}})
        self.assertEqual(r.status_code, 200, r.text)
        mailregeln.run(self.uid)                                          # first look: what is there stays
        return r.json()["saved"]

    def arrive(self, frm, mid):
        FMB.put("INBOX", helpers.box_mail(frm, "Post", "…", mid=mid))

    def uid_in(self, folder, mid):
        return next(m["uid"] for m in FMB.boxes[folder] if mid.encode() in m["raw"])

    def rule_of(self, rid):
        return next(r for r in mailregeln.load(self.uid)["rules"] if r["id"] == rid)

    def test_off_nothing_is_learnt(self):
        helpers.set_config(mail_learn=False)
        rid = self.rule("@autohaus-kehl.de", "Auto")
        self.arrive("Anna <anna@autohaus-kehl.de>", "<o-1@x>")
        self.assertEqual(mailregeln.run(self.uid)["taken"], 1)
        postfach.act(self.uid, f"{self.acct}:{self.uid_in('Auto', '<o-1@x>')}", "move", "Newsletter", src="Auto")
        FMB.put("INBOX", FMB.boxes["Newsletter"].pop()["raw"])            # and back into the inbox
        mailregeln.run(self.uid)
        d = mailregeln.load(self.uid)
        self.assertEqual((d["fixes"], self.rule_of(rid).get("except")), ([], None))
        self.assertNotIn("KI/Falsch sortiert", FMB.boxes)
        self.assertEqual(cards(self.uid), {})

    def test_page_correction_makes_an_exception_and_the_card(self):
        rid = self.rule("@autohaus-kehl.de", "Auto")
        self.assertIn("KI/Falsch sortiert", FMB.boxes)                     # made once the function is on
        self.arrive("Anna <anna@autohaus-kehl.de>", "<k-1@x>")
        mailregeln.run(self.uid)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = postfach.act(self.uid, f"{self.acct}:{self.uid_in('Auto', '<k-1@x>')}", "move", "Newsletter", src="Auto")
        self.assertIsNone(r["hint"])                                         # the card asks, not the page's hint
        fx = mailregeln.load(self.uid)["fixes"]
        self.assertEqual([(f["how"], f["von"], f["nach"], f["from"], f["rid"], f["by"]) for f in fx],
                         [("folder", "Auto", "Newsletter", "anna@autohaus-kehl.de", rid, "rule")])
        self.assertEqual(self.rule_of(rid)["except"], ["anna@autohaus-kehl.de"])
        log = out.getvalue()
        self.assertIn("mail: rule correction | folder | 1 |", log)
        self.assertIn("mail: rule exception | 1 |", log)
        for word in ("anna", "autohaus", "Newsletter", "Auto "):
            self.assertNotIn(word, log)
        (card,) = cards(self.uid).values()
        self.assertIn("anna@autohaus-kehl.de", card["titel"])
        self.assertIn("War in „Auto“", card["zeile"])
        self.assertEqual([k["k"] for k in vorgaenge.public(self.uid, card)["acts"]], ["rg_aendern", "rg_ausnahme", "rg_nie", "spaeter"])
        # the exception: Anna's next mail stays, another address of the domain is still taken; the mail itself never again
        self.arrive("Anna <anna@autohaus-kehl.de>", "<k-2@x>")
        self.arrive("Bob <bob@autohaus-kehl.de>", "<k-3@x>")
        self.assertEqual(mailregeln.run(self.uid)["taken"], 1)
        self.assertEqual([m["raw"].count(b"k-3@x") for m in FMB.boxes["Auto"]], [1])
        # „Regel ändern“: the rule's folder becomes Newsletter and Anna is no exception any more; the card is done
        res = vorgaenge.act(self.uid, card["id"], "rg_aendern")
        self.assertIn("Newsletter", res["text"])
        r = self.rule_of(rid)
        self.assertEqual((r["then"]["folder"], r["except"], r["on"]), ("Newsletter", [], True))
        self.assertEqual(cards(self.uid)[card["key"]]["zustand"], "erledigt")
        # a second move of the same mail is no second correction
        postfach.act(self.uid, f"{self.acct}:{self.uid_in('Newsletter', '<k-1@x>')}", "move", "Auto", src="Newsletter")
        self.assertEqual(len(mailregeln.load(self.uid)["fixes"]), 1)

    def test_archiving_is_no_correction(self):
        self.rule("@autohaus-kehl.de", "Auto")
        self.arrive("Anna <anna@autohaus-kehl.de>", "<a-1@x>")
        mailregeln.run(self.uid)
        postfach.act(self.uid, f"{self.acct}:{self.uid_in('Auto', '<a-1@x>')}", "archive", src="Auto")
        self.assertEqual(mailregeln.load(self.uid)["fixes"], [])

    def test_three_corrections_pause_the_rule_with_a_card(self):
        rid = self.rule("@autohaus-kehl.de", "Auto")
        for i, who in enumerate(("anna", "bob", "carl")):
            self.arrive(f"{who} <{who}@autohaus-kehl.de>", f"<p-{i}@x>")
        self.assertEqual(mailregeln.run(self.uid)["taken"], 3)
        refs = [f"{self.acct}:{m['uid']}" for m in FMB.boxes["Auto"]]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            postfach.act_many(self.uid, refs, "move", "Newsletter", src="Auto")
        r = self.rule_of(rid)
        self.assertEqual((r["on"], bool(r["paused"]), len(r["except"])), (False, True, 3))
        self.assertIn(f"mail: rule paused | {mailregeln.FIX_PAUSE} |", out.getvalue())
        self.assertEqual(mailregeln.for_live()["paused"], 1)
        pause = next(x for x in cards(self.uid).values() if x["titel"].startswith("Regel pausiert"))
        acts = vorgaenge.public(self.uid, pause)["acts"]
        self.assertEqual([(k["k"], k["de"]) for k in acts][:2], [("oeffnen", "Regel ansehen …"), ("rg_an", "Wieder einschalten")])
        self.assertEqual(pause["daten"], {"weg": "E-Mail → Regeln"})
        # paused: nothing is taken any more (also not Dora, who is no exception)
        self.arrive("Dora <dora@autohaus-kehl.de>", "<p-9@x>")
        self.assertEqual(mailregeln.run(self.uid)["taken"], 0)
        self.assertEqual(vorgaenge.act(self.uid, pause["id"], "rg_an")["text"], "Die Regel ist wieder an.")
        r = self.rule_of(rid)
        self.assertEqual((r["on"], "paused" in r), (True, False))

    def test_wrong_folder_asks_where_it_belongs(self):
        rid = self.rule("@stadtwerke.de", "KI/Strom")
        mailregeln.learn(self.uid, self.acct, ["rechnung@stadtwerke.de"], "KI/Rechnungen")   # moved there once on the page
        self.arrive("Stadtwerke <rechnung@stadtwerke.de>", "<w-1@x>")
        mailregeln.run(self.uid)
        FMB.put("KI/Falsch sortiert", FMB.boxes["KI/Strom"].pop()["raw"])   # in Apple Mail into „Falsch sortiert“
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mailregeln.suggest(self.uid)
        self.assertIn("mail: rule correction | wrong | 1 |", out.getvalue())
        (f,) = mailregeln.load(self.uid)["fixes"]
        self.assertEqual((f["how"], f["von"], f["nach"], f["rid"]), ("wrong", "KI/Strom", "", rid))
        (card,) = [x for x in cards(self.uid).values() if x["titel"] == "Wohin gehört diese Mail?"]
        acts = [(k["k"], k["de"]) for k in vorgaenge.public(self.uid, card)["acts"]]
        self.assertEqual(acts, [("rg_w1", "Nach „KI/Rechnungen“"), ("rg_eingang", "Posteingang"), ("oeffnen", "Anderer Ordner …"),
                                ("rg_nur", "Nur diese Mail"), ("rg_ausnahme", "Absender als Ausnahme"), ("rg_nie", "Nicht mehr fragen"),
                                ("spaeter", "Später")])
        self.assertEqual(self.c.get("/api/profile/mail/rules").json()["suggest"], [])     # not a suggestion of the page
        res = vorgaenge.act(self.uid, card["id"], "rg_w1")
        self.assertEqual(res["text"], "Abgelegt in „KI/Rechnungen“.")
        self.assertEqual((FMB.boxes["KI/Falsch sortiert"], [m["raw"].count(b"w-1@x") for m in FMB.boxes["KI/Rechnungen"]]), ([], [1]))
        (f,) = mailregeln.load(self.uid)["fixes"]
        self.assertEqual(f["nach"], "KI/Rechnungen")
        fix = [x for x in cards(self.uid).values() if x["titel"].startswith("Regel-Vorschlag")]
        self.assertEqual([k["k"] for k in vorgaenge.public(self.uid, fix[0])["acts"]], ["rg_aendern", "rg_ausnahme", "rg_nie", "spaeter"])
        # „Nur diese Mail“ on another one takes the sender's exception back
        self.assertEqual(self.rule_of(rid)["except"], ["rechnung@stadtwerke.de"])
        self.assertTrue(mailregeln._set_except(self.uid, rid, "rechnung@stadtwerke.de", True))

    def test_only_this_mail_and_never(self):
        rid = self.rule("@stadtwerke.de", "KI/Strom")
        for i in range(2):
            self.arrive("Stadtwerke <rechnung@stadtwerke.de>", f"<n-{i}@x>")
        mailregeln.run(self.uid)
        for _ in range(2):
            FMB.put("KI/Falsch sortiert", FMB.boxes["KI/Strom"].pop()["raw"])
        mailregeln.suggest(self.uid)
        wohin = [x for x in cards(self.uid).values() if x["titel"] == "Wohin gehört diese Mail?"]
        self.assertEqual(len(wohin), 2)
        self.assertEqual(vorgaenge.act(self.uid, wohin[0]["id"], "rg_nur")["text"], "Gut, nur diese Mail; für den Absender ändert sich nichts.")
        self.assertEqual(self.rule_of(rid)["except"], [])
        self.assertEqual(vorgaenge.act(self.uid, wohin[1]["id"], "rg_nie")["text"], "Gut, dazu frage ich nicht mehr.")
        self.assertIn(f"{self.acct}|rechnung@stadtwerke.de|", mailregeln.load(self.uid)["never"])
        self.assertEqual({x["zustand"] for x in cards(self.uid).values()}, {"erledigt", "weg"})

    def test_night_counts_where_the_person_put_it(self):
        """The night look: a mail „Mails aufräumen“ moved into KI/Werbung that now lies in KI/Rechnungen counts there
        (FIX_WEIGHT times) and is a correction; without the function it never counts (the filter of before)."""
        for i in range(2):
            FMB.put("KI/Rechnungen", helpers.box_mail("Shop <promo@shop.de>", f"Rechnung {i}", "…", mid=f"<pr-{i}@x>"))
        tidy._mut(self.uid, lambda d: d.update(log=[{"id": f"l{i}", "run": "r", "t": 10 ** 10, "aid": self.acct,
                                                     "mid": f"<pr-{i}@x>", "folder": "KI/Werbung", "sender": "promo@shop.de"}
                                                    for i in range(2)]))
        helpers.set_config(mail_learn=False)
        self.assertEqual(mailregeln.suggest(self.uid), [])
        helpers.set_config(mail_learn=True)
        mailregeln.forget(self.uid)
        mailregeln.suggest(self.uid)
        fx = mailregeln.load(self.uid)["fixes"]
        self.assertEqual(sorted((f["by"], f["von"], f["nach"]) for f in fx), [("tidy", "KI/Werbung", "KI/Rechnungen")] * 2)
        sug = mailregeln.load(self.uid)["suggest"]
        self.assertEqual([(x.get("kind"), x["from"], x["folder"]) for x in sug], [("fix", "promo@shop.de", "KI/Rechnungen")])
        (card,) = cards(self.uid).values()
        self.assertEqual([k["k"] for k in vorgaenge.public(self.uid, card)["acts"]], ["rg_regel", "rg_nie", "spaeter"])
        self.assertIn("promo@shop.de", mailregeln.fixed_senders(self.uid, self.acct))

    def test_exceptions_in_fits_and_thresholds_in_one_place(self):
        h = {"from": "anna@x.de", "to": [], "subject": "", "attach": False}
        self.assertFalse(mailregeln.fits({"when": {"from": "@x.de"}, "except": ["anna@x.de"]}, h))
        self.assertTrue(mailregeln.fits({"when": {"from": "@x.de"}, "except": ["bob@x.de"]}, h))
        self.assertEqual((mailregeln.FIX_EXCEPT, mailregeln.FIX_PAUSE, mailregeln.FIX_DAYS, mailregeln.FIX_WEIGHT), (1, 3, 30, 3))
        self.assertGreaterEqual(mailregeln.FIX_WEIGHT, mailregeln.LEARN_AFTER)    # one correction is enough for the card
        with self.assertRaises(ValueError):                                       # no tidy folder of the same name
            tidy.check_new_name(tidy.state(self.uid), "Falsch sortiert")

    def test_guests_and_other_profiles(self):
        rid = self.rule("@autohaus-kehl.de", "Auto")
        self.arrive("Anna <anna@autohaus-kehl.de>", "<g-1@x>")
        mailregeln.run(self.uid)
        postfach.act(self.uid, f"{self.acct}:{self.uid_in('Auto', '<g-1@x>')}", "move", "Newsletter", src="Auto")
        (card,) = cards(self.uid).values()
        other, ouid = profile("Lern Lutz")
        r = other.post("/api/profile/vorgaenge/act", json={"id": card["id"], "act": "rg_aendern"})
        self.assertEqual(r.status_code, 404, r.text)                            # another profile's card is not there
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/vorgaenge/act", json={"id": card["id"], "act": "rg_aendern"}).status_code, (401, 403))
        self.assertEqual(self.rule_of(rid)["then"]["folder"], "Auto")
        helpers.set_config(mail_learn=False)                                     # off: the card has no buttons of its own
        self.assertEqual(mailregeln._card_acts(self.uid, card), set())
        self.assertFalse(mailregeln.features.allowed("maillearn", self.uid))


if __name__ == "__main__":
    unittest.main()
