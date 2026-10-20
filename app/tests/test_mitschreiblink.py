"""Mitschreib-Link (mitschreiblink.py, Listen Stufe 4): a link for people without a profile to put entries on one list.

- Off by default: without the admin switch (chat.tasks_link) the visitor's routes are 404 and the owner cannot make
  a link; switched off later, every link stops at once.
- Only the hash of the code is kept, the code only comes back once (with its QR code); links() never shows it.
- A visitor puts entries on (source „Mitschreib-Link“, its typed name), nothing else; with „sehen“ it reads the open
  entries (texts only), without it nothing. Ticking off or deleting have no route at all.
- Expiry, „Widerrufen“, a deleted list and a list in a calendar account end or refuse the link; wrong codes lock like
  a PIN; another site's Origin is refused; Mein Notaus of the owner holds every entry off.
- The assistant reads a list with link entries as outside text; journal lines with fixed words only, never the code,
  the name or the entry; Live counts.

No wall clock in the checks: expiry is tested with a given now.
"""
import contextlib
import io
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import mitschreiblink  # noqa: E402
import notaus  # noqa: E402
import tasks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
BASE = "https://spark.example"


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def code_of(link):
    return link.split("#liste=", 1)[1]


class Link(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Mitlink Mia")

    def setUp(self):
        helpers.keep_chat(self, "tasks", "tasks_link")
        helpers.set_config(tasks=True, tasks_link=True)
        guard.reset()
        d = tasks._load(self.uid)
        d["items"], d["targets"] = [], {}
        tasks._save(self.uid, d)
        if os.path.exists(mitschreiblink.FILE):
            os.remove(mitschreiblink.FILE)
        self.v = TestClient(panel.app)   # a visitor: no login at all

    def make(self, lid="einkauf", days=30, see=False):
        r = self.c.post(f"/api/profile/listen/{lid}/links", json={"days": days, "see": see, "base": BASE})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_off_by_default(self):
        self.assertNotIn("listlink", tasks.features.DEFAULT_ON)
        made = self.make()
        helpers.set_config(tasks_link=False)
        self.assertEqual(self.v.post("/api/liste/check", json={"code": code_of(made["link"])}).status_code, 404)
        self.assertEqual(self.c.post("/api/profile/listen/einkauf/links", json={"days": 7, "base": BASE}).status_code, 403)
        helpers.set_config(tasks_link=True)
        self.assertEqual(self.v.post("/api/liste/check", json={"code": code_of(made["link"])}).status_code, 200)

    def test_only_the_hash_and_the_code_once(self):
        made = self.make(days=7)
        code = code_of(made["link"])
        self.assertTrue(made["link"].startswith(BASE + "/#liste="))
        self.assertIn("<svg", made["qr"])
        with open(mitschreiblink.FILE) as f:
            self.assertNotIn(code, f.read())
        listed = self.c.get("/api/profile/listen/einkauf/links").json()["links"]
        self.assertEqual([sorted(x) for x in listed], [["id", "made", "see", "until"]])
        self.assertNotIn(code, str(listed))
        self.assertEqual(self.c.post("/api/profile/listen/einkauf/links", json={"days": 2, "base": BASE}).status_code, 400)
        self.assertEqual(self.c.post("/api/profile/listen/einkauf/links", json={"days": 7}).status_code, 400)

    def test_visitor_puts_on_and_sees_only_with_see(self):
        code = code_of(self.make()["link"])
        r = self.v.post("/api/liste/check", json={"code": code})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["name"], r.json()["see"]), ("Einkauf", False))
        self.assertNotIn("items", r.json())
        r = self.v.post("/api/liste/add", json={"code": code, "text": "2 Milch, Brot", "name": "Oma <b>Erna</b>"})
        self.assertEqual((r.status_code, r.json()["added"]), (200, 2))
        self.assertNotIn("items", r.json())
        rows = self.c.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"]
        self.assertEqual(sorted((x["text"], x["src"], x["by_name"]) for x in rows),
                         [("Brot", "link", "Oma bErna/b"), ("Milch", "link", "Oma bErna/b")])
        seeing = code_of(self.make(see=True)["link"])
        self.assertEqual(sorted(self.v.post("/api/liste/check", json={"code": seeing}).json()["items"]), ["Brot", "Milch 2×"])
        # nothing but putting on: no route ticks off or deletes, the owner's own routes need a login
        mid = rows[0]["id"]
        self.assertEqual(self.v.post("/api/profile/tasks/einkauf/done", json={"ids": [mid]}).status_code, 401)
        self.assertEqual(self.v.delete(f"/api/profile/tasks/einkauf/{mid}").status_code, 401)
        self.assertEqual(self.v.post("/api/liste/add", json={"code": code, "text": " , "}).status_code, 400)

    def test_ends_with_revoke_expiry_and_the_list(self):
        made = self.make()
        code = code_of(made["link"])
        self.assertEqual(self.c.delete(f"/api/profile/listen/einkauf/links/{made['id']}").json()["links"], [])
        self.assertEqual(self.v.post("/api/liste/check", json={"code": code}).status_code, 400)
        # expiry, with a given now
        kid, code = mitschreiblink.make(self.uid, "einkauf", 7, False, now=1_000_000)
        self.assertIsNone(mitschreiblink.find(code, now=1_000_000 + 7 * 86400))
        self.assertIsNotNone(mitschreiblink.find(code, now=1_000_000 + 7 * 86400 - 1))
        # an own list: deleting it takes its links along
        lid = self.c.post("/api/profile/listen", json={"name": "Grillfest"}).json()["made"]
        code = code_of(self.make(lid)["link"])
        self.assertEqual(self.v.post("/api/liste/check", json={"code": code}).json()["name"], "Grillfest")
        self.c.delete(f"/api/profile/listen/{lid}")
        self.assertEqual(self.v.post("/api/liste/check", json={"code": code}).status_code, 400)
        # a list in a calendar account gets no link
        d = tasks._load(self.uid)
        d["targets"]["aufgaben"] = {"acc": "x", "url": "https://dav.example/t/", "name": "Nextcloud"}
        tasks._save(self.uid, d)
        self.assertEqual(self.c.post("/api/profile/listen/aufgaben/links", json={"days": 7, "base": BASE}).status_code, 404)

    def test_the_door(self):
        code = code_of(self.make()["link"])
        r = self.v.post("/api/liste/check", json={"code": code}, headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        codes = [self.v.post("/api/liste/check", json={"code": "x" * 24}).status_code for _ in range(7)]
        self.assertEqual(codes[-1], 429)   # locked like a PIN
        guard.reset()
        real = notaus.own
        notaus.own = lambda uid: uid == self.uid
        try:
            self.assertEqual(self.v.post("/api/liste/add", json={"code": code, "text": "Käse"}).status_code, 503)
        finally:
            notaus.own = real
        self.assertEqual(self.c.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"], [])

    def test_outside_text_journal_and_live(self):
        code = code_of(self.make()["link"])
        before = mitschreiblink.for_live()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.v.post("/api/liste/add", json={"code": code, "text": "Geheimtorte", "name": "Besuch Bea"})
            self.v.post("/api/liste/check", json={"code": "y" * 24})
        log = out.getvalue()
        for secret in (code, "Geheimtorte", "Besuch Bea"):
            self.assertNotIn(secret, log)
        self.assertIn("tasks: add einkauf | 1 entries |", log)
        self.assertIn("tasks: link refused | bad code", log)
        live = mitschreiblink.for_live()
        self.assertEqual((live["added"], live["refused"], live["links"]), (before["added"] + 1, before["refused"] + 1, 1))
        offer = tasks.offer({"who": {"id": self.uid}, "own": True})
        self.assertIn("tasks_show", offer["outside"])


if __name__ == "__main__":
    unittest.main()
