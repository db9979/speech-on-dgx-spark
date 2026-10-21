"""Kontakte wie Apple Kontakte (Apple-Stil „6a“, Dominik 2026-10-21 „Weiter“): the page Kontakte and its changes.

- kontaktkarte.py on fixed vCards: the page's fields checked, written into a card while every other line stays
  (photo, UID, groups), a card with more fields than the page shows is refused, a new card.
- GET /api/profile/contacts/page: books (each address book of an account, the Spark's own one when changing is on),
  every card with whether it may change; „Mit …“ and the .vcf to pass on.
- „Kontakte ändern“ (chat.contacts_edit) off: nothing changes (403). On: a change goes back into its own address book
  with If-Match, a card changed there meanwhile gives 409 and stays as it is; a new card into the book chosen or the
  Spark's own one; delete with If-Match. Another profile never reaches a card; guests never.
- The page at 1280 and 390 px: A–Z, the card, „Bearbeiten“ with + fields, „Fertig“ saves.

Fake CardDAV server with ETags; no wall clock.
"""
import asyncio
import base64
import hashlib
import os
import re
import unittest
from xml.sax.saxutils import escape

from tests import helpers

helpers.start()
import panel  # noqa: E402
import contacts  # noqa: E402
import guard  # noqa: E402
import kontaktkarte  # noqa: E402
import profiles  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PORT = helpers._port()
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
CARDS = {}
AUTH = "Basic " + base64.b64encode(b"kai@example.org:pw-k").decode()


def tag(text):
    return '"' + hashlib.sha1(text.encode()).hexdigest()[:12] + '"'


def vcard(given, family, extra=""):
    return (f"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:{given.lower()}-uid\r\nFN:{given} {family}\r\nN:{family};{given};;;\r\n"
            f"{extra}END:VCARD\r\n")


def fake():
    app = FastAPI()
    ms = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'

    def resp(href, prop):
        return f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{prop}</d:prop></d:propstat></d:response>"

    @app.api_route("/kdav/{rest:path}", methods=["PROPFIND", "REPORT", "GET", "PUT", "DELETE"])
    async def dav(rest: str, req: Request):
        if req.headers.get("authorization") != AUTH:
            return Response(status_code=401)
        path, body = "/kdav/" + rest, (await req.body()).decode()
        if req.method == "PROPFIND":
            x = resp("/kdav/", "<d:resourcetype><d:collection/></d:resourcetype>") + \
                resp("/kdav/privat/", "<d:resourcetype><d:collection/><a:addressbook/></d:resourcetype><d:displayname>Privat</d:displayname>")
            return Response(ms + x + "</d:multistatus>", status_code=207, media_type="application/xml")
        if req.method == "REPORT":
            return Response(ms + "".join(resp(h, f"<d:getetag>{tag(v)}</d:getetag><a:address-data>{escape(v)}</a:address-data>")
                                         for h, v in CARDS.items()) + "</d:multistatus>", status_code=207, media_type="application/xml")
        if req.method == "GET":
            if path not in CARDS:
                return Response(status_code=404)
            return Response(CARDS[path], media_type="text/vcard", headers={"ETag": tag(CARDS[path])})
        if req.method == "PUT":
            if req.headers.get("if-none-match") == "*":
                if path in CARDS:
                    return Response(status_code=412)
            elif path not in CARDS or req.headers.get("if-match") != tag(CARDS[path]):
                return Response(status_code=412)
            CARDS[path] = body
            return Response(status_code=201)
        if path not in CARDS:
            return Response(status_code=404)
        if req.headers.get("if-match") != tag(CARDS[path]):
            return Response(status_code=412)
        CARDS.pop(path)
        return Response(status_code=204)
    return app


helpers._serve(fake(), PORT)


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


ANNA = vcard("Anna", "Alt", "TEL;TYPE=CELL:+49 170 1234567\r\nEMAIL;TYPE=INTERNET:anna@example.org\r\n"
                            "PHOTO;ENCODING=b;TYPE=JPEG:QUJD\r\nitem1.URL:https://anna.example.org\r\nitem1.X-ABLabel:_$!<HomePage>!$_\r\n"
                            "X-SOCIALPROFILE;type=mastodon:https://social.example/@anna\r\n")


class Card(unittest.TestCase):
    def test_fields_are_checked(self):
        f = kontaktkarte.fields({"given": "Anna", "phones": [["Handy", "+49 170 1"], ["Fax", "0711 5"]], "emails": ["A@Example.org", "a@example.org"],
                                 "addrs": [{"kind": "Privat", "street": "Hauptstr. 1", "zip": "89073", "city": "Ulm"}], "bday": "--03-15"})
        self.assertEqual((f["phones"], f["emails"], f["addrs"][0]["city"]), ([["Handy", "+49 170 1"], ["Telefon", "0711 5"]], ["a@example.org"], "Ulm"))
        for bad in ({}, {"given": "A", "phones": ["0711<script>"]}, {"given": "A", "emails": ["anna"]}, {"given": "A", "urls": ["javascript:x"]},
                    {"given": "A", "bday": "1985-02-30"}, {"given": "A", "phones": [str(i) * 3 for i in range(10)]}):
            with self.assertRaises(ValueError, msg=bad):
                kontaktkarte.fields(bad)

    def test_patch_keeps_the_rest(self):
        f = kontaktkarte.fields({"given": "Anna", "family": "Neu", "phones": [["Arbeit", "0731 1"]], "note": "Zeile 1\nZeile 2, mit; Zeichen"})
        out = kontaktkarte.patch(ANNA, f)
        flat = out.replace("\r\n ", "")
        for keep in ("UID:anna-uid", "PHOTO;ENCODING=b;TYPE=JPEG:QUJD", "X-SOCIALPROFILE;type=mastodon:https://social.example/@anna"):
            self.assertIn(keep, flat)
        for gone in ("+49 170", "anna@example.org", "item1.", "FN:Anna Alt"):
            self.assertNotIn(gone, flat)
        c = contacts.parse_vcard(out)
        self.assertEqual((c["name"], c["phones"], c["note"]), ("Anna Neu", [["Arbeit", "0731 1"]], "Zeile 1\nZeile 2, mit; Zeichen"))
        self.assertTrue(all(len(x.encode()) <= 75 for x in out.split("\r\n")))
        many = vcard("Viel", "Tel", "".join(f"TEL:0711 {i}\r\n" for i in range(kontaktkarte.PHONES_MAX + 1)))
        with self.assertRaises(ValueError):
            kontaktkarte.patch(many, f)
        uid_text, text = kontaktkarte.new(kontaktkarte.fields({"org": "Bäckerei Brot", "bday": "1990-01-02"}))
        c = contacts.parse_vcard(text)
        self.assertEqual((c["name"], c["bday"], c["uid"]), ("Bäckerei Brot", "1990-01-02", uid_text))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(contacts=True, contacts_edit=False)
        cls.c, cls.uid = profile("Kontakte Kai")

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(contacts=False, contacts_edit=False)

    def setUp(self):
        guard.reset()
        CARDS.clear()
        CARDS["/kdav/privat/anna.vcf"] = ANNA
        CARDS["/kdav/privat/bert.vcf"] = vcard("Bert", "Brot", "TEL;TYPE=HOME:0731 98765\r\n")
        for a in contacts.accounts(self.uid):
            contacts.remove(self.uid, a["id"])
        contacts._save(self.uid, spark=[])
        r = self.c.post("/api/profile/contacts", json={"url": f"http://127.0.0.1:{PORT}/kdav/", "user": "kai@example.org", "password": "pw-k"})
        self.assertEqual(r.status_code, 200, r.text)
        helpers.set_config(contacts_edit=True)

    def page(self, c=None):
        r = (c or self.c).get("/api/profile/contacts/page")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def card(self, d, name):
        return next(x for x in d["cards"] if x["name"] == name)

    def test_page_and_switch(self):
        helpers.set_config(contacts_edit=False)
        d = self.page()
        self.assertEqual([b["name"] for b in d["books"]], ["Privat"])   # no Spark book while changing is off
        a = self.card(d, "Anna Alt")
        self.assertEqual((a["given"], a["family"], a["phones"], a["urls"], a["edit"]),
                         ("Anna", "Alt", [["Handy", "+49 170 1234567"]], ["https://anna.example.org"], False))
        self.assertNotIn("href", a)
        self.assertEqual(self.c.put(f"/api/profile/contacts/card/{a['id']}", json={"given": "X"}).status_code, 403)
        self.assertEqual(self.c.post("/api/profile/contacts/card", json={"given": "X"}).status_code, 403)
        helpers.set_config(contacts_edit=True)
        d = self.page()
        self.assertEqual([b["id"] for b in d["books"]][-1], contacts.SPARK)
        self.assertTrue(self.card(d, "Anna Alt")["edit"])
        r = self.c.get(f"/api/profile/contacts/vcf/{a['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("TEL;TYPE=CELL:+49 170 1234567", r.text)
        self.assertNotIn("PHOTO", r.text)
        self.assertEqual(self.c.get(f"/api/profile/contacts/with/{a['id']}").json(), {"event": None, "mail": None})

    def test_change_goes_back_with_its_etag(self):
        a = self.card(self.page(), "Anna Alt")
        body = dict(a, family="Alt-Neu", phones=[["Handy", "+49 170 1234567"], ["Arbeit", "0731 1"]], note="kommt gern")
        r = self.c.put(f"/api/profile/contacts/card/{a['id']}", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["name"], len(r.json()["phones"])), ("Anna Alt-Neu", 2))
        stored = CARDS["/kdav/privat/anna.vcf"]
        self.assertIn("N:Alt-Neu;Anna;;;", stored)
        self.assertIn("PHOTO;ENCODING=b;TYPE=JPEG:QUJD", stored)
        self.assertEqual(self.card(self.page(), "Anna Alt-Neu")["note"], "kommt gern")
        # changed on the iPhone meanwhile: the page's old ETag is refused, nothing is overwritten
        CARDS["/kdav/privat/anna.vcf"] = stored.replace("kommt gern", "kommt nicht")
        r = self.c.put(f"/api/profile/contacts/card/{a['id']}", json=dict(body, note="mein Text", etag=r.json()["etag"]))
        self.assertEqual(r.status_code, 409)
        self.assertIn("kommt nicht", CARDS["/kdav/privat/anna.vcf"])
        self.assertGreaterEqual(contacts.page_today(), 1)

    def test_new_delete_and_the_spark_book(self):
        r = self.c.post("/api/profile/contacts/card", json={"given": "Carla", "family": "Chor", "emails": ["carla@example.org"],
                                                           "book": self.page()["books"][0]["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sum("Carla" in v for v in CARDS.values()), 1)
        r = self.c.delete(f"/api/profile/contacts/card/{r.json()['id']}", params={"etag": r.json()["etag"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(any("Carla" in v for v in CARDS.values()))
        r = self.c.post("/api/profile/contacts/card", json={"org": "Bäckerei Brot", "phones": [["Arbeit", "0731 5"]], "book": "spark"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["book"], "spark")
        self.assertFalse(any("Bäckerei" in v for v in CARDS.values()))     # only on the Spark
        raw = open(profiles._path(self.uid, "contacts.json")).read()
        self.assertNotIn("Bäckerei", raw)                                    # sealed
        self.assertIn("Bäckerei Brot", contacts.line(contacts.search(self.uid, "Bäckerei")[0]))   # the assistant finds it
        sid = r.json()["id"]
        r = self.c.put(f"/api/profile/contacts/card/{sid}", json={"org": "Bäckerei Brot", "phones": [["Arbeit", "0731 6"]]})
        self.assertEqual(r.json()["phones"], [["Arbeit", "0731 6"]])
        self.assertEqual(self.c.delete(f"/api/profile/contacts/card/{sid}").status_code, 200)
        self.assertFalse(any(x["name"] == "Bäckerei Brot" for x in self.page()["cards"]))

    def test_refused(self):
        a = self.card(self.page(), "Anna Alt")
        self.assertEqual(self.c.put(f"/api/profile/contacts/card/{a['id']}", json={"given": "", "family": ""}).status_code, 400)
        self.assertEqual(self.c.put("/api/profile/contacts/card/cfremd0000000", json={"given": "X"}).status_code, 409)
        self.assertEqual(self.c.post("/api/profile/contacts/card", json={"given": "X", "book": "bnichtda00"}).status_code, 409)
        other, _ = profile("Kontakte Olga")
        self.assertEqual(other.put(f"/api/profile/contacts/card/{a['id']}", json={"given": "X"}).status_code, 409)
        self.assertEqual(other.delete(f"/api/profile/contacts/card/{a['id']}").status_code, 409)
        self.assertEqual(TestClient(panel.app).get("/api/profile/contacts/page").status_code, 401)
        helpers.set_config(deny={"contacts": [self.uid]})
        try:
            self.assertEqual(self.c.put(f"/api/profile/contacts/card/{a['id']}", json={"given": "X"}).status_code, 403)
        finally:
            helpers.set_config(deny={})
        self.assertEqual(CARDS["/kdav/privat/anna.vcf"], ANNA)


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(contacts=True, contacts_edit=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(contacts=False, contacts_edit=False)

    def test_list_card_and_edit(self):
        from tests.test_ui_browser import Browser, async_playwright
        CARDS.clear()
        CARDS["/kdav/privat/anna.vcf"] = ANNA
        CARDS["/kdav/privat/bert.vcf"] = vcard("Bert", "Brot", "TEL;TYPE=HOME:0731 98765\r\n")
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for w in (1280, 390):
                    br, pg, errors = await b.page(p, w, 900)
                    try:
                        uid = await pg.evaluate("PROFILE.id")
                        if not contacts.accounts(uid):
                            r = await contacts.add(uid, contacts.entry({"url": f"http://127.0.0.1:{PORT}/kdav/", "user": "kai@example.org", "password": "pw-k"}))
                            self.assertEqual(r["count"], 2)
                        await pg.evaluate("CON_ON=true;icTabSet('kontakte','show');goSec('kontakte')")
                        await b.until(pg, "!!KON.data&&document.querySelectorAll('#konview [data-c]').length===2")
                        self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#konview .konlet [data-l]')].map(x=>x.dataset.l).join('')"), "AB")
                        await pg.evaluate("[...document.querySelectorAll('#konview [data-c]')].find(e=>e.textContent.includes('Anna')).click()")
                        await b.until(pg, "!!document.querySelector('#konview .koncard [data-k=edit]')")
                        self.assertIn("+49 170 1234567", await pg.text_content("#konview .koncard"))
                        await pg.click("#konview .koncard [data-k=edit]")
                        await pg.click("#konview .konform [data-add=phones]")
                        await pg.fill("#konview .konform [data-f=phones] .konrow:last-child input", "0731 42")
                        await pg.click("#konview .konform [data-k=save]")
                        await b.until(pg, "!KON.busy&&!KON.form&&KON.data.cards.some(x=>x.phones.some(p=>p[1]==='0731 42'))")
                        self.assertIn("0731 42", CARDS["/kdav/privat/anna.vcf"])
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the page scrolls sideways")
                        CARDS["/kdav/privat/anna.vcf"] = ANNA
                        await contacts.refresh(uid)   # the next width starts from the card as it was
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
