"""Ich → Mein Zustand (hintergrund.py), V01.0.281.

Off without the admin's and the profile's switch, never for guests; each profile sees only its own jobs
and services; the answer carries fixed words, numbers and the person's own names, never mail subjects,
document text or a server's error text; a service's state comes from its last real request (the fake
mail and CalDAV servers), the page asks nobody itself; the history keeps HIST entries for HIST_DAYS days.
No test depends on the wall clock: times are passed in.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import io
import json
import time
import unittest

from fastapi.testclient import TestClient
from PIL import Image

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import documents  # noqa: E402
import hintergrund  # noqa: E402
import mail  # noqa: E402
import netguard  # noqa: E402
import profiles  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def run(coro):
    import asyncio
    return asyncio.run(coro)


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 30, 30)).save(out, "JPEG")
    return out.getvalue()


class MyStatus(unittest.TestCase):
    def setUp(self):
        helpers.set_config(my_status=True, mail=True, calendar=True, documents=True, doc_pictures=True)
        mail.IMAP = helpers.FakeIMAP

    def tearDown(self):
        helpers.set_config(my_status=False, doc_pictures=False)

    def on(self, name):
        c = profile(name)
        uid = uid_of(name)
        profiles.save_settings(uid, {"my_status": True})
        return c, uid

    def test_off_by_default_and_never_for_guests(self):
        helpers.set_config(my_status=False)
        self.assertIs(profiles.SETTINGS["my_status"][0], False)
        c = profile("Hbert")
        self.assertEqual(c.get("/api/profile/hintergrund").status_code, 403)          # admin switch off
        helpers.set_config(my_status=True)
        self.assertEqual(c.get("/api/profile/hintergrund").status_code, 403)          # own switch still off
        self.assertEqual(TestClient(panel.app).get("/api/profile/hintergrund").status_code, 401)   # guests
        self.assertEqual(TestClient(panel.app).get("/api/admin/hintergrund").status_code, 401)
        self.assertIn(c.get("/api/admin/hintergrund").status_code, (401, 403))
        profiles.save_settings(uid_of("Hbert"), {"my_status": True})
        d = c.get("/api/profile/hintergrund").json()
        self.assertEqual(d["sum"]["need"], 0)
        self.assertTrue(all(r["state"] in hintergrund.STATES for r in d["rows"]))

    def test_mailbox_state_from_the_last_real_request_without_contents(self):
        c, uid = self.on("Hmara")
        mail.add(uid, mail.entry({"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW, "name": "Privat"}))
        aid = mail.get(uid)["accounts"][0]["id"]
        row = lambda: next(r for r in c.get("/api/profile/hintergrund").json()["rows"] if r["key"] == "mail:" + aid)
        n = len(helpers.IMAP_CALLS)
        self.assertEqual((row()["state"], row()["why"]), ("idle", "ungeprueft"))
        self.assertEqual(len(helpers.IMAP_CALLS), n)                               # the page asks nobody itself
        mail.find(uid, "", days=30)
        self.assertEqual(row()["state"], "ok")
        raw = c.get("/api/profile/hintergrund").text
        for secret in ("Grillen", "Telekom", "anna.alt", "Ignoriere"):              # nothing of the mails
            self.assertNotIn(secret, raw)
        # a refused password: fixed reason, the dot at "Ich" comes
        d = mail.get(uid)
        d["accounts"][0]["password"] = "wrong"
        mail._store(uid, d)
        mail._drop(uid)
        self.assertTrue(mail.find(uid, "", days=30)[1])                            # the account failed
        r = row()
        self.assertEqual((r["state"], r["why"]), ("bad", "anmeldung"))
        self.assertEqual(r["why_text"], list(hintergrund.WHY["anmeldung"]))
        brief = c.get("/api/profile/hintergrund?brief=1").json()
        self.assertEqual(set(brief), {"sum"})
        self.assertGreaterEqual(brief["sum"]["need"], 1)
        self.assertNotIn("AUTHENTICATIONFAILED", c.get("/api/profile/hintergrund").text)
        # another profile sees none of it
        o, _ = self.on("Hotto")
        self.assertNotIn(aid, o.get("/api/profile/hintergrund").text)
        self.assertNotIn("Privat", o.get("/api/profile/hintergrund").text)

    def test_calendar_state_through_netguard(self):
        c, uid = self.on("Hcarla")
        calendars.add(uid, calendars.entry({"name": "Familie", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/"}))
        calendars.add(uid, calendars.entry({"name": "Weg", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/nirgends/"}))
        cals = calendars.get(uid)["calendars"]
        import datetime
        start = datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc)
        for cal in cals:
            try:
                run(calendars._fetch(cal, start, start + datetime.timedelta(days=1)))
            except Exception:
                pass
        rows = {r["label"]: r for r in c.get("/api/profile/hintergrund").json()["rows"] if r["key"].startswith("cal:")}
        self.assertEqual(rows["Familie"]["state"], "ok")
        self.assertEqual((rows["Weg"]["state"], rows["Weg"]["why"]), ("bad", "adresse"))

    def test_netguard_gives_one_verdict_per_client(self):
        got = []
        async def go():
            async with netguard.client(netguard.USER, origin=f"http://127.0.0.1:{helpers.CAL_PORT}/",
                                       seen=lambda ok, why: got.append((ok, why))) as cl:
                await cl.get(f"http://127.0.0.1:{helpers.CAL_PORT}/dav/x")       # 404 while looking around
                await cl.request("PROPFIND", f"http://127.0.0.1:{helpers.CAL_PORT}/dav/privat/")   # answers
        run(go())
        self.assertEqual(got, [(True, "")])
        got.clear()
        async def down():
            async with netguard.client(netguard.USER, origin="http://127.0.0.1:9/", seen=lambda ok, why: got.append((ok, why))) as cl:
                try:
                    await cl.get("http://127.0.0.1:9/")
                except Exception:
                    pass
        run(down())
        self.assertEqual(got, [(False, "nicht_erreichbar")])

    def test_documents_show_names_and_numbers_never_text(self):
        c, uid = self.on("Hdora")
        profiles.save_settings(uid, {"doc_pictures": True})
        documents.add(uid, "Mietvertrag.txt", b"GEHEIMWORT steht im Vertrag", text="GEHEIMWORT steht im Vertrag")
        documents.add(uid, "Rechnung.jpg", jpeg(), pictures=True)
        d = c.get("/api/profile/hintergrund").json()
        docs = next(r for r in d["rows"] if r["key"] == "docs")
        self.assertIn(docs["state"], ("wait", "run"))
        self.assertIn("1 Seiten warten", docs["detail"][0])
        self.assertNotIn("GEHEIMWORT", json.dumps(d))
        import wissen
        doc = next(x for x in documents.list_docs(uid) if x["name"] == "Rechnung.jpg")
        wissen._now.update(uid=uid, doc=doc["id"], page=1)
        try:
            docs = next(r for r in c.get("/api/profile/hintergrund").json()["rows"] if r["key"] == "docs")
            self.assertEqual((docs["state"], docs["label"], docs["total"]), ("run", "Rechnung.jpg", 1))
        finally:
            wissen._now.clear()
        # another profile does not see that this one reads
        o, _ = self.on("Hemil")
        wissen._now.update(uid=uid, doc=doc["id"], page=1)
        try:
            self.assertNotIn("Rechnung.jpg", o.get("/api/profile/hintergrund").text)
        finally:
            wissen._now.clear()

    def test_reasons_are_fixed_words(self):
        for text, why in (("the mail server rejects the user name or password", "anmeldung"),
                          ("Der Speicher für Dokumente ist voll (Ich → Dokumente).", "voll"),
                          ("mail server not reachable (TimeoutError)", "nicht_erreichbar"),
                          ("no calendar found at this address", "adresse"),
                          ("KeyError", "fehler"), ("", "")):
            self.assertEqual(hintergrund.reason_of(text), why, text)
        hintergrund.seen("mail", "a1", False, "<script>")       # an unknown word is never passed on
        self.assertEqual(hintergrund.service("mail", "a1")["why"], "fehler")
        hintergrund.seen("nope", "a1", True)
        self.assertEqual(hintergrund.service("nope", "a1"), {})

    def test_history_keeps_seven_days_and_a_limit(self):
        _, uid = self.on("Hfrida")
        t0 = 1_800_000_000
        for i in range(hintergrund.HIST + 10):
            hintergrund.note(uid, "tidy", True, 2, now=t0 + i * 60)
        h = hintergrund._hist(uid)["tidy"]
        self.assertEqual(len(h), hintergrund.HIST)
        hintergrund.note(uid, "tidy", False, now=t0 + 8 * 86400)
        self.assertEqual(len(hintergrund._hist(uid)["tidy"]), 1)          # older than 7 days gone
        for i in range(5):
            hintergrund.note(uid, "docs", True, 1, now=t0 + i, per_day=True)
        self.assertEqual(hintergrund._hist(uid)["docs"][-1]["n"], 5)        # one line per day
        hintergrund.note(uid, "unknown", True, now=t0)
        self.assertNotIn("unknown", hintergrund._hist(uid))
        # nothing is written for a profile that does not use the page
        _, other = self.on("Hgreta")
        profiles.save_settings(other, {"my_status": False})
        hintergrund.note(other, "tidy", True, now=t0)
        self.assertEqual(hintergrund._hist(other), {})

    def test_admin_sees_counts_only(self):
        c, uid = self.on("Hhans")
        mail.add(uid, mail.entry({"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW, "name": "Geheimpostfach"}))
        d = ADMIN.get("/api/admin/hintergrund").json()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["profiles"], 1)
        self.assertNotIn("Geheimpostfach", json.dumps(d))
        self.assertNotIn("Hhans", json.dumps(d))
        helpers.set_config(my_status=False)
        self.assertEqual(ADMIN.get("/api/admin/hintergrund").json(), {"on": False})

    def test_the_iphone_app_may_read_it(self):
        self.assertIn("/api/profile/hintergrund", profiles.APP_PATHS)


if __name__ == "__main__":
    unittest.main()
