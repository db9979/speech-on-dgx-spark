"""Kontakte wie Apple Kontakte, Stufe 3b (Apple-Stil „6a“, Dominik 2026-10-21 „Weiter“): the Spark as a CardDAV
server for the iPhone's Kontakte app.

- Off by default: without the admin switch /carddav and /.well-known/carddav do not exist (404).
- The door is the Kalender-Server's: HTTP Basic with the profile's id and its app password; wrong guesses lock like a
  PIN, a web page of another site is refused, Mein Notaus closes it, a profile the admin blocked gets 403.
- Only the profile's own address book „Auf dem Spark“: another profile's path is 404.
- CardDAV as a contacts app speaks it: discovery, PROPFIND, REPORT addressbook-query and addressbook-multiget, GET,
  PUT, DELETE with etags; a card from the app shows on the page Kontakte at once, a change on the page keeps the
  app's object name. Without „Kontakte ändern“ it is read only (403 on PUT and DELETE).
- The panel's own CardDAV client (contacts.fetch_account) finds and reads it like any server.
"""
import asyncio
import base64
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import contacts  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import httpx  # noqa: E402
import kontaktserver  # noqa: E402
import notaus  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
CARD = ("BEGIN:VCARD\r\nVERSION:3.0\r\nPRODID:-//Apple Inc.//iOS 26//EN\r\nN:Kasten;Karla;;;\r\nFN:Karla Kasten\r\n"
        "TEL;type=CELL:+49 170 5550101\r\nEMAIL;type=INTERNET:karla@example.org\r\nUID:app-1\r\nEND:VCARD\r\n")
FIND = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            cls.config = dict(json.load(f)["chat"])   # put back at the end: the next module gets the config it had
        helpers.set_config(calendar=True, calendar_server=True, contacts=True, contacts_edit=True, contacts_server=True)
        cls.c, cls.uid = profile("Karla Kasten")
        cls.o, cls.oid = profile("Karla Olsen")
        r = cls.c.post("/api/profile/calserver")
        assert r.status_code == 200, r.text
        cls.pw = r.json()["password"]
        cls.dav = TestClient(panel.app)
        cls.dav.headers.update(basic(cls.uid, cls.pw))
        cls.book = f"/carddav/{cls.uid}/spark/"

    @classmethod
    def tearDownClass(cls):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["chat"] = cls.config
        helpers.write_config(c)
        guard.reset()

    def setUp(self):
        guard.reset()
        contacts._save(self.uid, spark=[])

    def test_discovery_like_a_contacts_app(self):
        r = self.dav.request("PROPFIND", "/.well-known/carddav", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (301, "/carddav/"))
        r = self.dav.request("PROPFIND", "/carddav/", content=FIND, headers={"Depth": "0"})
        self.assertEqual(r.status_code, 207)
        self.assertIn(f"<d:href>/carddav/{self.uid}/</d:href></d:current-user-principal>", r.text)
        r = self.dav.request("PROPFIND", f"/carddav/{self.uid}/", headers={"Depth": "1"})
        self.assertIn("addressbook-home-set", r.text)
        self.assertIn(f"<d:href>{self.book}</d:href>", r.text)
        self.assertIn("<card:addressbook/>", r.text)
        self.assertIn("<d:write/>", r.text)

    def test_put_report_get_delete_and_the_page(self):
        href = self.book + "app-1.vcf"
        r = self.dav.put(href, content=CARD, headers={"If-None-Match": "*", "Content-Type": "text/vcard"})
        self.assertEqual(r.status_code, 201, r.text)
        tag = r.headers["etag"]
        page = self.c.get("/api/profile/contacts/page").json()
        karla = next(x for x in page["cards"] if x["name"] == "Karla Kasten")   # on the page at once
        self.assertEqual((karla["book"], karla["edit"], karla["phones"]), ("spark", True, [["Handy", "+49 170 5550101"]]))
        r = self.dav.request("PROPFIND", self.book, headers={"Depth": "1"})
        self.assertIn(f"<d:href>{href}</d:href>", r.text)
        q = (b'<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><d:getetag/>'
             b'<card:address-data/></d:prop></card:addressbook-query>')
        self.assertIn("Karla Kasten", self.dav.request("REPORT", self.book, content=q, headers={"Depth": "1"}).text)
        m = (b'<card:addressbook-multiget xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><d:getetag/>'
             b'<card:address-data/></d:prop><d:href>' + href.encode() + b'</d:href><d:href>' + self.book.encode()
             + b'nix.vcf</d:href></card:addressbook-multiget>')
        r = self.dav.request("REPORT", self.book, content=m, headers={"Depth": "1"})
        self.assertIn("karla@example.org", r.text)
        self.assertIn("404 Not Found", r.text)
        self.assertEqual(self.dav.get(href).text, CARD)
        # a change on the page keeps the app's object name: the app sees the same card changed
        r = self.c.put(f"/api/profile/contacts/card/{karla['id']}", json={"given": "Karla", "family": "Kasten-Neu",
                                                                         "phones": [["Arbeit", "0731 1"]]})
        self.assertEqual(r.status_code, 200, r.text)
        got = self.dav.get(href)
        self.assertIn("Kasten-Neu", got.text)
        self.assertIn("UID:app-1", got.text)
        self.assertNotEqual(got.headers["etag"], tag)
        self.assertEqual(self.dav.request("DELETE", href, headers={"If-Match": tag}).status_code, 412)
        self.assertEqual(self.dav.request("DELETE", href, headers={"If-Match": got.headers["etag"]}).status_code, 204)
        self.assertNotIn("Karla Kasten-Neu", [x["name"] for x in self.c.get("/api/profile/contacts/page").json()["cards"]])

    def test_only_the_own_address_book_and_only_cards(self):
        for path in (f"/carddav/{self.oid}/", f"/carddav/{self.oid}/spark/", f"/carddav/{self.uid}/icloud/",
                     f"/carddav/{self.uid}/spark/../x.vcf", f"/carddav/{self.uid}/spark/a/b.vcf"):
            self.assertEqual(self.dav.request("PROPFIND", path, headers={"Depth": "1"}).status_code, 404, path)
        self.assertEqual(self.dav.put(self.book + "x.vcf", content=b"<html>").status_code, 415)
        self.assertEqual(self.dav.put(self.book + "y.vcf", content=(CARD + CARD).encode()).status_code, 415)
        self.assertEqual(self.dav.put(self.book + "z.vcf", content=b"BEGIN:VCARD\r\nVERSION:3.0\r\nEND:VCARD\r\n").status_code, 415)
        self.assertEqual(self.dav.put(self.book + "big.vcf", content=CARD.replace("UID:", "NOTE:" + "x" * 300000 + "\r\nUID:")).status_code, 415)
        self.assertEqual(self.dav.request("MKCOL", f"/carddav/{self.uid}/neu/").status_code, 404)
        self.assertEqual(self.dav.request("PROPPATCH", self.book).status_code, 403)

    def test_read_only_without_kontakte_aendern(self):
        self.assertEqual(self.dav.put(self.book + "app-1.vcf", content=CARD).status_code, 201)
        helpers.set_config(contacts_edit=False)
        try:
            self.assertEqual(self.dav.put(self.book + "app-2.vcf", content=CARD).status_code, 403)
            self.assertEqual(self.dav.request("DELETE", self.book + "app-1.vcf").status_code, 403)
            self.assertIn("Karla Kasten", self.dav.get(self.book + "app-1.vcf").text)
            self.assertNotIn("<d:write/>", self.dav.request("PROPFIND", self.book).text)
        finally:
            helpers.set_config(contacts_edit=True)

    def test_the_door(self):
        anon = TestClient(panel.app)
        self.assertEqual(anon.request("PROPFIND", "/carddav/").status_code, 401)
        self.assertEqual(anon.request("PROPFIND", "/carddav/", headers=basic(self.oid, self.pw)).status_code, 401)
        self.assertEqual(self.dav.request("PROPFIND", "/carddav/", headers={"Origin": "https://evil.example"}).status_code, 403)
        codes = [anon.request("PROPFIND", "/carddav/", headers=basic(self.uid, "falsch-falsch")).status_code for _ in range(7)]
        self.assertEqual(codes[-1], 429)   # locked like a PIN
        guard.reset()
        real = notaus.own
        notaus.own = lambda uid: uid == self.uid
        try:
            self.assertEqual(self.dav.request("PROPFIND", "/carddav/").status_code, 503)
        finally:
            notaus.own = real
        real_stop = notaus.stop

        def stop(what, uid):
            raise notaus.NotausAktiv()
        notaus.stop = stop
        try:
            self.assertEqual(self.dav.put(self.book + "app-3.vcf", content=CARD).status_code, 423)
        finally:
            notaus.stop = real_stop
        real_allowed = features.allowed
        features.allowed = lambda key, uid=None: key != "kontaktserver" and real_allowed(key, uid)
        try:
            self.assertEqual(self.dav.request("PROPFIND", "/carddav/").status_code, 403)
        finally:
            features.allowed = real_allowed

    def test_off_means_not_there(self):
        helpers.set_config(contacts_server=False)
        try:
            self.assertEqual(self.dav.request("PROPFIND", "/carddav/").status_code, 404)
            self.assertEqual(self.dav.request("PROPFIND", "/.well-known/carddav", follow_redirects=False).status_code, 404)
        finally:
            helpers.set_config(contacts_server=True)

    def test_the_panels_own_carddav_client_reads_it(self):
        self.assertEqual(self.dav.put(self.book + "app-1.vcf", content=CARD).status_code, 201)
        real = contacts._client

        def client(acct, seen=True):
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=panel.app), base_url="http://testserver",
                                     auth=(acct["user"], acct["password"]))
        contacts._client = client
        try:
            got = asyncio.run(contacts.fetch_account({"id": "a1", "url": "http://testserver/carddav/", "user": self.uid,
                                                      "password": self.pw}))
        finally:
            contacts._client = real
        self.assertIn("Karla Kasten", [x["name"] for x in got])

    def test_live_numbers_only(self):
        self.dav.request("PROPFIND", "/carddav/")
        d = kontaktserver.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["requests"], 1)
        self.assertEqual(set(d), {"on", "requests", "saved", "refused"})


if __name__ == "__main__":
    unittest.main()
