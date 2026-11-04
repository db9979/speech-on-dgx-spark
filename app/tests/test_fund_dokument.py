"""Finden, Stufe B: „Zu Dokumenten übernehmen“ at an attachment hit (fundmail.zu_dokumenten, wissen.aufnehmen). The
button only by the fixed rule (a kind of documents.TYPES, at most fundmail.ANHANG_MAX, both releases); the endpoint
takes only an attachment entry of the own index, fetches the bytes itself from the own mailbox (PEEK), keeps the
origin as a fixed key (never a text of the mail) and takes the same attachment in once (doppelt, without asking the
mailbox again); another profile's entry, a guest and a switched-off function are refused; Live and the journal with
fixed words and numbers. The fake mailbox and the fixed moment of test_fund_mail (never the clock)."""
import contextlib
import io
import json
import re
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import documents  # noqa: E402
import features  # noqa: E402
import fund  # noqa: E402
import guard  # noqa: E402
import fundmail  # noqa: E402
import panel  # noqa: E402
import wissen  # noqa: E402
from tests.test_fund_mail import FMB, NOW, SENDER, SUBJECT, Base, quiet, raw  # noqa: E402
from tests.test_mailclient_c import profile  # noqa: E402

URL = "/api/profile/fund/eintrag/{}/dokument"


class Dok(Base):
    NAME = "Fundanhang Ida"

    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "doc_originals", "doc_semantic", "doc_brief", "doc_auswertung", "deny")
        helpers.set_config(documents=True, doc_originals=False, doc_semantic=False, doc_brief=False, doc_auswertung=False)
        FMB.put("INBOX", raw("Programmpaket Wombat", files=[("setup.exe", b"MZ" + b"0" * 200, "application/octet-stream")]))
        for d in documents.list_docs(self.uid):
            documents.delete(self.uid, d["id"])
        for k in [k for k in guard._rate if k[0] == "funddok"]:   # each test starts with a fresh minute
            guard._rate.pop(k, None)
        self.round()

    def anhang(self, words="Ohrensessel"):
        """The PDF attachment as its own hit (quelle anhang)."""
        hits = self.find(words, quelle="anhang")
        self.assertEqual(len(hits), 1)
        return hits[0]

    def post(self, iid, c=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = (c or self.c).post(URL.format(iid))
        self.out = buf.getvalue()
        return r


class Knopf(Dok):
    def test_only_by_the_fixed_rule(self):
        h = self.anhang()
        self.assertIs(h["dokument"], True)
        mail_hit = self.find("Ohrensessel")[0]
        self.assertEqual([a["dokument"] for a in mail_hit["anhaenge"]], [True])
        e = fund.eintrag(self.uid, mail_hit["id"])
        kinds = {a["titel"]: a["dokument"] for a in e["anhaenge"]}
        self.assertEqual(kinds, {"Beleg-Quokka.pdf": True, "foto.jpg": True})      # a picture: OCR in the documents
        self.assertIs(fund.eintrag(self.uid, h["id"])["dokument"], True)
        exe = self.find("Programmpaket")[0]
        self.assertEqual([a["dokument"] for a in fund.eintrag(self.uid, exe["id"])["anhaenge"]], [False])
        # the rule itself: a kind of the documents and at most ANHANG_MAX (≤ 10 MB, Stufe B)
        self.assertTrue(fundmail.ANHANG_MAX <= 10 * 1024 * 1024)
        self.assertTrue(fundmail.dok_passt("a.PDF", 1))
        self.assertFalse(fundmail.dok_passt("a.exe", 1))
        self.assertFalse(fundmail.dok_passt("ohne", 1))
        self.assertFalse(fundmail.dok_passt("a.pdf", fundmail.ANHANG_MAX // 1024 + 1))
        self.assertFalse(fundmail.dok_passt("a.pdf", "5"))

    def test_without_documents_no_button_and_refused(self):
        helpers.set_config(documents=False)
        h = self.anhang()
        self.assertIs(h["dokument"], False)
        r = self.post(h["id"])
        self.assertEqual(r.status_code, 403)
        self.assertIn("fund: dokument abgelehnt | aus", self.out)
        helpers.set_config(documents=True, deny={"documents": [self.uid]})
        self.assertIs(self.anhang()["dokument"], False)
        r = self.post(h["id"])
        self.assertEqual(r.status_code, 403)
        self.assertIn("Gesperrte Funktionen", r.json()["detail"])
        self.assertEqual(documents.list_docs(self.uid), [])

    def test_mail_switch_off_refused(self):
        h = self.anhang()
        helpers.set_config(fund_mail=False)
        self.assertEqual(self.post(h["id"]).status_code, 403)
        self.assertEqual(documents.list_docs(self.uid), [])


class Uebernehmen(Dok):
    def test_taken_once_with_a_fixed_origin(self):
        h = self.anhang()
        FMB.calls = []
        r = self.post(h["id"])
        self.assertEqual(r.status_code, 200, r.text)
        got = r.json()
        self.assertEqual((got["ok"], got["doppelt"], got["name"]), (True, False, "Beleg-Quokka.pdf"))
        self.assertIn("fund: dokument | uebernommen | ", self.out)
        # fetched from the own mailbox only reading: EXAMINE and PEEK, the mail stays unread
        self.assertTrue([a for c, a in FMB.calls if c == "FETCH"])
        self.assertTrue(all("PEEK" in a[1] for c, a in FMB.calls if c == "FETCH"))
        self.assertFalse([c for c, _ in FMB.calls if c in ("STORE", "MOVE", "EXPUNGE", "COPY", "APPEND")])
        self.assertTrue(all(not m["seen"] for m in FMB.boxes["INBOX"]))
        docs = [d for d in documents.list_docs(self.uid) if d["id"] == got["id"]]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["source"], "mail")
        # the origin is the entry's fixed key, never a word of the mail
        origin = "mail:" + h["ext"]
        self.assertTrue(wissen.HERKUNFT.fullmatch(origin))
        self.assertRegex(origin, r"^mail:m[0-9a-f]{8}:[a-z2-7]{8}:\d+:\d+$")
        self.assertEqual(documents.by_origin(self.uid, "mail", origin), got["id"])
        for word in ("Quokka", "quokka", "Zebrafink", "Beleg", "rechnung@"):
            self.assertNotIn(word, origin)
        # the second click: in the documents already, the mailbox is not asked again
        FMB.calls = []
        r = self.post(h["id"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["doppelt"], r.json()["id"]), (True, got["id"]))
        self.assertIn("fund: dokument | doppelt | ", self.out)
        self.assertEqual([c for c, _ in FMB.calls if c == "FETCH"], [])
        self.assertEqual(len([d for d in documents.list_docs(self.uid) if d["source"] == "mail"]), 1)
        # the same attachment from its mail's list is the same entry: still once
        mail_hit = self.find("Ohrensessel")[0]
        self.assertEqual(self.post(mail_hit["anhaenge"][0]["id"]).json()["doppelt"], True)
        # Live: numbers only
        fund._live.update(at=0.0, d=None)
        live = fund.for_live()
        self.assertGreaterEqual(live["dok"], 1)
        self.assertGreaterEqual(live["dok_doppelt"], 2)
        for word in (SUBJECT, SENDER, "Beleg", "Quokka", self.NAME):
            self.assertNotIn(word, json.dumps(live, ensure_ascii=False))
            self.assertNotIn(word, self.out)

    def test_the_kind_and_the_size_are_checked_again(self):
        exe = fund.eintrag(self.uid, self.find("Programmpaket")[0]["id"])["anhaenge"][0]
        r = self.post(exe["id"])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"], fundmail.DOK_SAETZE["art"])
        self.assertIn("fund: dokument abgelehnt | art", self.out)
        h = self.anhang()
        with mock.patch.object(fundmail, "ANHANG_MAX", 512):   # below the PDF's one KB in the index
            self.assertIs(self.anhang()["dokument"], False)
            r = self.post(h["id"])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"], fundmail.DOK_SAETZE["groesse"])
        # bigger in the mailbox than in the index: refused after the fetch too
        with mock.patch.object(fundmail.mail, "file_of", lambda *a: ("Beleg-Quokka.pdf", b"0" * (fundmail.ANHANG_MAX + 1))):
            r = self.post(h["id"])
        self.assertEqual(r.status_code, 400)
        # another file at this place of the mail: never taken under the indexed name
        with mock.patch.object(fundmail.mail, "file_of", lambda *a: ("anderes.pdf", b"%PDF-1.4")):
            r = self.post(h["id"])
        self.assertEqual(r.status_code, 404)
        self.assertEqual(documents.list_docs(self.uid), [])

    def test_gone_from_the_mailbox(self):
        h = self.anhang()
        uid_mail = int(h["ext"].split(":")[2])
        FMB.boxes["INBOX"] = [m for m in FMB.boxes["INBOX"] if m["uid"] != uid_mail]
        r = self.post(h["id"])
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"], fundmail.DOK_SAETZE["weg"])
        self.assertIn("fund: dokument abgelehnt | weg", self.out)

    def test_a_mail_is_no_attachment(self):
        mail_hit = self.find("Ohrensessel")[0]
        self.assertNotIn("dokument", mail_hit)
        r = self.post(mail_hit["id"])
        self.assertEqual(r.status_code, 404)
        self.assertIn("fund: dokument abgelehnt | kein", self.out)
        self.assertEqual(self.post("abc").status_code, 404)


class Fremd(Dok):
    def test_another_profile_and_a_guest_are_refused(self):
        h = self.anhang()
        other, ouid = profile("Fundanhang Ole")
        self.assertNotEqual(ouid, self.uid)
        r = self.post(h["id"], other)
        self.assertIn(r.status_code, (403, 404))
        self.assertEqual(documents.list_docs(self.uid), [])
        self.assertFalse([d for d in documents.list_docs(ouid) if d["source"] == "mail"])
        guest = TestClient(panel.app)
        self.assertIn(guest.post(URL.format(h["id"])).status_code, (401, 403))
        self.assertFalse(fundmail.dok_frei(None))
        self.assertEqual(features.reason("fundmail", None), "guest")
        # a body is never needed: a big one is refused before it is read
        r = self.c.post(URL.format(h["id"]), content=b"{" + b" " * 4096 + b"}", headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(documents.list_docs(self.uid), [])

    def test_route_rules(self):
        import iphone
        self.assertTrue(any(re.fullmatch(p, "/api/profile/fund/eintrag/12/dokument") and "POST" in m
                            for m, p in iphone.profiles.APP_AREAS["fund"]))
        self.assertEqual(self.c.get(URL.format(12)).status_code, 405)            # a change only by POST
        # the rate limit: at most guard.RATE["funddok"] a minute per profile
        most = guard.RATE["funddok"][1]
        with mock.patch.object(fundmail, "zu_dokumenten", mock.Mock(side_effect=fundmail.DokNein("kein"))):
            codes = [self.post(999999).status_code for _ in range(most + 1)]
        self.assertEqual(codes[:most], [404] * most)
        self.assertEqual(codes[-1], 429)


if __name__ == "__main__":
    import unittest
    unittest.main()
