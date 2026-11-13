"""Probleme melden (meldung.py, plan plaene/probleme-melden.md): a report goes out to GitHub only as the anonymized
text the person saw in the preview, only with the admin's and the profile's switch, never for guests, never with a
name, a mail address, an address of the home network or a secret in it. GitHub is faked here; no test depends on
the time of day."""
import asyncio
import json
import os
import time
import unittest

import httpx

from tests import helpers

helpers.start()
import panel  # noqa: E402
import meldung  # noqa: E402
import profiles  # noqa: E402
import vault  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HOME = ("192.168.178.20", 50000)
TOKEN = "github_pat_" + "A1b2" * 20
SENT = []        # what the fake GitHub got: (method, path, json)


def gh(request):
    body = json.loads(request.content or b"{}") if request.content else None
    SENT.append((request.method, request.url.path, body, request.headers.get("authorization")))
    path = request.url.path
    if request.method == "POST" and path.endswith("/issues"):
        return httpx.Response(201, json={"number": 7, "html_url": "https://github.com/db9979/spark-meldungen/issues/7"},
                              headers={"github-authentication-token-expiration": "2027-01-09 10:00:00 UTC"})
    if request.method == "GET" and path.endswith("/issues"):
        return httpx.Response(200, json=[{"number": 7, "state": "closed", "comments": 1}])
    if path.endswith("/issues/7/comments"):
        return httpx.Response(200, json=[{"user": {"login": "db9979"}, "created_at": "2026-10-11T08:00:00Z",
                                          "body": "Behoben in V01.0.380.\u0007"}])
    if path.endswith("/issues/7"):
        return httpx.Response(200, json={"number": 7, "state": "closed"})
    if request.method == "GET" and path.endswith("/spark-meldungen"):
        return httpx.Response(200, json={"private": True}, headers={"github-authentication-token-expiration": "2027-01-09 10:00:00 UTC"})
    return httpx.Response(404, json={})


async def fake_client():
    return httpx.AsyncClient(transport=httpx.MockTransport(gh))


def client():
    return TestClient(panel.app, client=HOME)


def admin():
    c = client()
    assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    return c


def profile(name, pin="1234"):
    a = admin()
    r = a.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = client()
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    uid = next(u["id"] for u in profiles._load()["users"] if u["name"] == name)
    return c, uid


def block(tc, uid, on=False):
    """The admin blocks (on=False) or allows again (on=True) "Probleme melden" for one profile (chat.deny)."""
    r = admin().put(f"/api/admin/features/melden/profiles/{uid}", json={"on": on})
    assert r.status_code == 200, r.text
    if not on:
        tc.addCleanup(block, tc, uid, True)


class Base(unittest.TestCase):
    def setUp(self):
        import guard
        guard.reset()
        self.real = meldung._client
        meldung._client = fake_client
        SENT.clear()
        helpers.set_config(report=True)
        meldung.token_drop()
        meldung._states.update(t=0, items={})
        for d in meldung._all():
            os.remove(meldung._path(d["id"]))

    def tearDown(self):
        import guard
        guard.reset()
        meldung._client = self.real
        helpers.set_config(report=False)
        meldung.token_drop()


class Anonymize(Base):
    def test_names_mails_addresses_and_secrets_are_replaced(self):
        c, uid = profile("RpWaltraud")
        k = meldung.known()
        k["secrets"].append("supergeheim-12345")
        k["hosts"].append("speech.example.de")
        a = meldung.Anon(k)
        line = ('2026-10-11 chat: turn for RpWaltraud from 192.168.178.20 and 8.8.8.8 mail an waltraud@example.org '
                'betreff "Arzttermin am Montag" https://speech.example.de/api?x=1 key=abc token supergeheim-12345 '
                'mac aa:bb:cc:dd:ee:ff tel +49 171 2345678 bei 52.5200,13.4050 nas.fritz.box fe80::1')
        out = a.text(line, log=True)
        for bad in ("RpWaltraud", "192.168.178.20", "8.8.8.8", "waltraud@", "Arzttermin", "speech.example.de",
                    "supergeheim", "aa:bb:cc", "171 2345678", "52.5200", "fritz.box", "fe80"):
            self.assertNotIn(bad, out, out)
        for mark in ("[PERSON-1]", "[IP-LAN]", "[IP]", "[MAIL]", "[INHALT]", "[URL]", "[MAC]", "[TELEFON]", "[ORT]", "[HOST]"):
            self.assertIn(mark, out, out)
        self.assertIn("2026-10-11", out)                          # dates and times stay readable
        self.assertEqual(a.text("RpWaltraud ruft"), "[PERSON-1] ruft")   # the same name keeps its number
        self.assertEqual(meldung.leaks(out, k), [])

    def test_times_versions_and_tool_names_stay(self):
        a = meldung.Anon(meldung.known())
        s = "07:03:02 anfrage: 1a2b3c | web | kalender | calendar_events ok | erster Ton 1.2 s | V01.0.371 | app.py"
        self.assertEqual(a.text(s, log=True), s)

    def test_markdown_cannot_break_out_or_ping_people(self):
        a = meldung.Anon(meldung.known())
        out = a.text("```\n@db9979 schau mal")
        self.assertNotIn("```", out)
        self.assertNotIn("@db9979", out)

    def test_leak_check_finds_what_slipped_through(self):
        _, uid = profile("RpGunnar")
        k = meldung.known()
        self.assertIn("Name", meldung.leaks("Hallo RpGunnar", k))
        self.assertIn("Mail-Adresse", meldung.leaks("an x@example.org", k))
        self.assertIn("Adresse", meldung.leaks("von 10.0.0.5", k))
        self.assertEqual(meldung.leaks("Hallo [PERSON-1] von [IP-LAN]", k), [])


class Switches(Base):
    def test_off_by_default_and_never_for_guests(self):
        with open(meldung.features.DEFAULTS) as f:
            self.assertIs(json.load(f)["chat"]["report"], False)
        self.assertNotIn("report_on", profiles.SETTINGS)    # no profile switch: the admin's release counts
        helpers.set_config(report=False)
        c, _ = profile("RpRudi")
        self.assertEqual(c.get("/api/report").status_code, 404)
        helpers.set_config(report=True)
        self.assertEqual(client().get("/api/report").status_code, 401)            # no login
        helpers.set_config(public=True)
        try:
            self.assertEqual(client().get("/api/report").status_code, 401)        # guests never
        finally:
            helpers.set_config(public=False)
        q, uq = profile("RpRita")
        self.assertEqual(q.get("/api/report").status_code, 200)                   # released: at once for every profile
        block(self, uq)
        r = q.get("/api/report")
        self.assertEqual(r.status_code, 403)                                       # the admin blocked this profile
        self.assertIn("Personen und Geräte → Gesperrte Funktionen", r.json()["detail"])
        self.assertNotIn("Ich →", r.json()["detail"])                              # no profile switch to point to
        said = asyncio.run(meldung.by_phrase(uq, "RpRita", "Problem melden: geht nicht", "telegram"))
        self.assertIn("geht für dich gerade nicht", said)
        self.assertIn("Personen und Geräte → Gesperrte Funktionen", said)
        self.assertNotIn("Ich →", said)
        self.assertEqual(q.get("/api/report").status_code, 403)
        block(self, uq, True)
        self.assertEqual(q.get("/api/report").status_code, 200)

    def test_profile_sees_only_its_own_and_no_diagnose_lines(self):
        c, uid = profile("RpPaula")
        real = meldung._journal
        meldung._journal = lambda minutes: [{"t": "07:00:00", "area": "chat", "level": "err", "msg": "chat: broke for RpPaula", "raw": ""}]
        try:
            d = c.post("/api/report/draft", json={"text": "Antwort kam nicht", "area": "antwort", "logs": True}).json()
        finally:
            meldung._journal = real
        self.assertEqual([x for x in d["lines"] if x["part"] == "lines"], [])    # Diagnose only for admins
        q, _ = profile("RpPetra")
        self.assertEqual(q.get("/api/report", params={"id": d["id"]}).status_code, 404)
        self.assertEqual([x["id"] for x in q.get("/api/report").json()["items"]], [])
        self.assertEqual([x["id"] for x in c.get("/api/report").json()["items"]], [d["id"]])
        everything = admin().get("/api/report").json()
        self.assertTrue(everything["staff"])
        self.assertIn(d["id"], [x["id"] for x in everything["items"]])
        self.assertEqual(next(x for x in everything["items"] if x["id"] == d["id"])["by"], "RpPaula")

    def test_admin_gets_anonymized_diagnose_lines(self):
        _, uid = profile("RpHorst")
        real = meldung._journal
        meldung._journal = lambda minutes: [{"t": "07:00:00", "area": "ha", "level": "err",
                                             "msg": "homeassistant: turn for RpHorst failed at 192.168.178.30", "raw": ""}]
        try:
            d = admin().post("/api/report/draft", json={"text": "Licht geht nicht", "area": "zuhause", "logs": True}).json()
        finally:
            meldung._journal = real
        lines = [x["line"] for x in d["lines"] if x["part"] == "lines"]
        self.assertEqual(len(lines), 1)
        self.assertNotIn("RpHorst", lines[0])
        self.assertNotIn("192.168", lines[0])
        with open(meldung._path(d["id"])) as f:
            stored = f.read()
        self.assertNotIn("RpHorst", stored)                                         # never kept unanonymized

    def test_inputs_checked(self):
        c, _ = profile("RpInes")
        self.assertEqual(c.post("/api/report/draft", json={"text": "x"}).status_code, 400)
        self.assertEqual(c.post("/api/report/draft", content=b"[1]", headers={"content-type": "application/json"}).status_code, 400)
        self.assertEqual(c.post("/api/report/draft", content=b"{" + b" " * 50000 + b"}",
                                headers={"content-type": "application/json"}).status_code, 413)
        d = c.post("/api/report/draft", json={"text": "Wort " * 1000, "area": "<script>", "minutes": 9999}).json()
        self.assertEqual((d["area"], d["minutes"]), ("sonstiges", 30))
        self.assertTrue(1900 < len(d["text"]) <= meldung.MAX_TEXT)
        self.assertEqual(c.post("/api/report/preview", json={"id": d["id"], "skip": ["1"]}).status_code, 400)
        self.assertEqual(c.post("/api/report/preview", json={"id": "../../etc"}).status_code, 404)


class Sending(Base):
    def draft(self, c):
        d = c.post("/api/report/draft", json={"text": "Der Lautsprecher schweigt", "area": "geraete"}).json()
        return d, d["preview"]

    def test_only_the_previewed_text_goes_out(self):
        meldung.token_save(TOKEN)
        c, uid = profile("RpSven")
        d, p = self.draft(c)
        self.assertEqual(p["leaks"], [])
        r = c.post("/api/report/send", json={"id": d["id"], "sig": "0" * 32})
        self.assertEqual(r.status_code, 409)                                      # not what was shown
        self.assertEqual([x for x in SENT if x[0] == "POST"], [])
        r = c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["status"], r.json()["issue"]["number"]), ("gesendet", 7))
        method, path, body, auth = [x for x in SENT if x[0] == "POST"][0]
        self.assertEqual(path, "/repos/db9979/spark-meldungen/issues")
        self.assertEqual((body["title"], body["body"]), (p["title"], p["body"]))
        self.assertEqual(auth, "Bearer " + TOKEN)
        self.assertNotIn("RpSven", json.dumps(body))
        self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"]}).status_code, 409)   # once

    def test_bug_wish_with_the_page_and_its_errors(self):
        """Käfer-Symbol (Dominik 2026-11-13): „Verbesserung“ gets its own label and title, the page's name and its own
        browser errors come along anonymized (a quoted text and a mail address go), only EXTRA_LABELS may be added."""
        meldung.token_save(TOKEN)
        c, uid = profile("RpKai")
        d = c.post("/api/report/draft", json={"text": "Der Kalender könnte die Woche zeigen", "area": "post",
                                              "kind": "verbesserung", "page": "Kalender → Termine",
                                              "pageerr": "14:00:01 js: Cannot read 'Termin mit Rpkai' of null\n"
                                                         "14:00:02 api: 404 /api/profile/cal/x kai@example.org\n" * 15}).json()
        self.assertEqual(d["kind"], "verbesserung")
        page = [x["line"] for x in d["lines"] if x["part"] == "page"]
        self.assertEqual(page[0], "Seite: Kalender → Termine")
        self.assertEqual(len(page), 1 + meldung.MAX_PAGEERR)                      # the last 20 errors only
        self.assertNotIn("kai@example.org", json.dumps(page))
        self.assertNotIn("Termin mit Rpkai", json.dumps(page))
        p = d["preview"]
        self.assertTrue(p["title"].startswith("[Verbesserung · Mail, Kalender, Kontakte]"), p["title"])
        self.assertIn("**Art:** Verbesserung", p["body"])
        self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"]}).status_code, 200)
        body = [x for x in SENT if x[0] == "POST"][-1][2]
        self.assertEqual(body["labels"], ["von-spark", "bereich:post", "verbesserung"])
        e = c.post("/api/report/draft", json={"text": "Absturz", "kind": "<b>", "page": 7}).json()
        self.assertEqual(e["kind"], "fehler")
        self.assertFalse([x for x in e["lines"] if x["part"] == "page"])
        self.assertEqual(meldung.labels({"area": "update", "labels": ["schwachstelle", "admin", "von-spark"]}),
                         ["von-spark", "bereich:update", "schwachstelle"])

    def test_bug_goes_out_at_once_with_direct(self):
        """With „Antwort-Meldungen direkt an GitHub“ a report from the Käfer goes out at once; without a page (the
        old window) it stays a draft for the preview."""
        meldung.token_save(TOKEN)
        helpers.set_config(report_direct=True)
        try:
            c, _ = profile("RpLea")
            d = c.post("/api/report/draft", json={"text": "Knopf reagiert nicht", "page": "Listen"}).json()
            self.assertEqual(d["status"], "gesendet")
            self.assertIn("Nummer 7", d["said"])
            d = c.post("/api/report/draft", json={"text": "Knopf reagiert nicht"}).json()
            self.assertEqual(d["status"], "entwurf")
        finally:
            helpers.set_config(report_direct=False)

    def test_dropped_lines_need_a_new_preview(self):
        meldung.token_save(TOKEN)
        c, _ = profile("RpLars")
        d, p = self.draft(c)
        self.assertTrue(d["lines"])
        q = c.post("/api/report/preview", json={"id": d["id"], "skip": [1]}).json()
        self.assertNotEqual(q["sig"], p["sig"])
        self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"], "skip": [1]}).status_code, 409)
        r = c.post("/api/report/send", json={"id": d["id"], "sig": q["sig"], "skip": [1]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(d["lines"][0]["line"], [x for x in SENT if x[0] == "POST"][0][2]["body"].split("\n"))

    def test_leak_blocks_sending(self):
        meldung.token_save(TOKEN)
        c, uid = profile("RpMelda")
        d, p = self.draft(c)
        # something the rules did not catch (here: written into the stored draft behind their back)
        with open(meldung._path(d["id"])) as f:
            raw = json.load(f)
        raw["parts"]["text"] += " RpMelda"
        with open(meldung._path(d["id"]), "w") as f:
            json.dump(raw, f)
        q = c.post("/api/report/preview", json={"id": d["id"]}).json()
        self.assertIn("Name", q["leaks"])
        self.assertEqual(q["sig"], "")
        r = c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual([x for x in SENT if x[0] == "POST"], [])

    def test_without_token_the_browser_link(self):
        c, _ = profile("RpBea")
        d, p = self.draft(c)
        self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"]}).status_code, 409)
        r = c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"], "browser": True}).json()
        self.assertTrue(r["url"].startswith("https://github.com/db9979/spark-meldungen/issues/new?title="))
        self.assertLess(len(r["url"]), 7500)
        self.assertEqual(SENT, [])
        r = c.post("/api/report/send", json={"id": d["id"], "local": True}).json()
        self.assertEqual(r["status"], "lokal")

    def test_daily_and_minute_limits(self):
        meldung.token_save(TOKEN)
        c, _ = profile("RpOlaf")
        d1, p1 = self.draft(c)
        self.assertEqual(c.post("/api/report/send", json={"id": d1["id"], "sig": p1["sig"]}).status_code, 200)
        d2, p2 = self.draft(c)
        self.assertEqual(c.post("/api/report/send", json={"id": d2["id"], "sig": p2["sig"]}).status_code, 429)   # a minute
        for d in meldung._all():                    # move the first one back in time instead of waiting
            if d.get("issue"):
                d["issue"]["t"] -= 120
                meldung._write(d)
        self.assertEqual(c.post("/api/report/send", json={"id": d2["id"], "sig": p2["sig"]}).status_code, 200)
        now = time.time()
        self.assertEqual(meldung._sent_count(meldung._all(now), d1["uid"] if "uid" in d1 else None, now)[1] >= 2, True)

    def test_answers_from_github_are_text_only(self):
        meldung.token_save(TOKEN)
        c, _ = profile("RpUdo")
        d, p = self.draft(c)
        c.post("/api/report/send", json={"id": d["id"], "sig": p["sig"]})
        items = c.get("/api/report").json()["items"]
        self.assertEqual(items[0]["gh"], {"state": "erledigt", "comments": 1})
        t = c.post("/api/report/thread", json={"id": d["id"]}).json()
        self.assertEqual(t["state"], "erledigt")
        self.assertEqual(t["answers"][0]["by"], "db9979")
        self.assertNotIn("\u0007", t["answers"][0]["text"])


class AdminNote(Base):
    def test_admins_hear_of_new_reports_in_fixed_words_and_can_turn_it_off(self):
        """Dominik 2026-10-11: the assistant tells the admin profiles of a new report; admin switch and own
        switch turn it off; the reporter is not told, the text never goes into the note."""
        import notaus
        import proactive
        meldung.token_save(TOKEN)
        _, boss = profile("RpChefin")
        c, uid = profile("RpSven")
        real = notaus.admin_uids
        notaus.admin_uids = lambda: [boss, uid]
        notes = lambda u: [x for x in proactive.state(u).get("queue", []) if x["kind"] == "meldung"]
        try:
            before = len(notes(boss))
            d = c.post("/api/report/draft", json={"text": "Ab Werk still", "area": "geraete"}).json()
            self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "local": True}).status_code, 200)
            self.assertEqual(len(notes(boss)), before)                            # the admin switch is off by default
            self.assertIs(c.get("/api/report").json()["notify"], False)
            helpers.set_config(report_notify=True)
            d = c.post("/api/report/draft", json={"text": "Der Lautsprecher schweigt", "area": "geraete"}).json()
            self.assertEqual(len(notes(boss)), before)                            # a draft is not a report yet
            r = c.post("/api/report/send", json={"id": d["id"], "sig": d["preview"]["sig"]})
            self.assertEqual(r.status_code, 200, r.text)
            got = notes(boss)
            self.assertEqual(len(got), before + 1)
            self.assertIn("RpSven", got[-1]["text"])
            self.assertIn("Nummer 7", got[-1]["text"])
            self.assertNotIn("schweigt", got[-1]["text"])
            self.assertEqual(notes(uid), [])                                      # not the reporter
            self.assertIs(c.get("/api/report").json()["notify"], True)                # its own switch shows
            # the admin profile turns it off for itself
            profiles.save_settings(boss, {"report_notify": False})
            d = c.post("/api/report/draft", json={"text": "Wieder still", "area": "geraete"}).json()
            self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "local": True}).status_code, 200)
            self.assertEqual(len(notes(boss)), before + 1)
            # on again for itself, but the admin switch off
            profiles.save_settings(boss, {"report_notify": True})
            helpers.set_config(report_notify=False)
            d = c.post("/api/report/draft", json={"text": "Noch einmal still", "area": "geraete"}).json()
            self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "local": True}).status_code, 200)
            self.assertEqual(len(notes(boss)), before + 1)
            helpers.set_config(report_notify=True)
            d = c.post("/api/report/draft", json={"text": "Und nochmal", "area": "geraete"}).json()
            self.assertEqual(c.post("/api/report/send", json={"id": d["id"], "local": True}).status_code, 200)
            self.assertEqual(len(notes(boss)), before + 2)
            self.assertIn("nur auf dem Spark", notes(boss)[-1]["text"])
        finally:
            notaus.admin_uids = real
            helpers.set_config(report_notify=False)


class Admin(Base):
    def test_token_only_fine_grained_sealed_and_never_shown(self):
        a = admin()
        self.assertEqual(a.put("/api/admin/report/token", json={"token": "ghp_" + "x" * 36}).status_code, 400)
        r = a.put("/api/admin/report/token", json={"token": TOKEN})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["until"], "2027-01-09")
        self.assertNotIn(TOKEN, json.dumps(r.json()))
        self.assertNotIn(TOKEN, json.dumps(a.get("/api/admin/report").json()))
        with open(meldung.TOKEN_FILE) as f:
            raw = f.read()
        self.assertNotIn(TOKEN, raw)
        self.assertTrue(json.loads(raw)["token"].startswith(vault.PREFIX))
        self.assertEqual(oct(os.stat(meldung.TOKEN_FILE).st_mode & 0o777), "0o600")

    def test_token_not_from_profiles_or_apps(self):
        c, uid = profile("RpTina")
        self.assertIn(c.put("/api/admin/report/token", json={"token": TOKEN}).status_code, (401, 403))
        self.assertIn(client().get("/api/admin/report").status_code, (401, 403))
        self.assertFalse(meldung._token())

    def test_repo_checked_and_sensitive(self):
        a = admin()
        cfg = a.get("/api/config").json()
        cfg["chat"]["report_repo"] = "x/../../y z"
        self.assertEqual(a.put("/api/config", json=cfg).status_code, 400)
        self.assertIn(("chat", "report_repo"), __import__("admin").SENSITIVE)
        self.assertIn(("chat", "report"), __import__("admin").SENSITIVE)


class Channels(Base):
    def test_the_fixed_sentence(self):
        P = meldung.phrase
        self.assertEqual(P("Spark, Problem melden: die Uhr zeigt nichts"), "die Uhr zeigt nichts")
        self.assertEqual(P("Hey Spark melde ein Problem, der Timer klingelt nicht"), "der Timer klingelt nicht")
        self.assertEqual(P("spark fehler melden: x y z"), "x y z")
        for no in ("Wie melde ich ein Problem?", "Problem melden: x y z", "Spark, Problem melden", "", None):
            self.assertIsNone(P(no), no)
        self.assertEqual(meldung.phrase_channel("watch"), "pebble")
        self.assertEqual(meldung.phrase_channel("speaker"), "esp32")

    def test_by_sentence_only_a_draft(self):
        meldung.token_save(TOKEN)
        c, uid = profile("RpVera")
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "Spark, Problem melden: Wecker blieb stumm"}]})
        list(helpers.events(r))
        mine = [d for d in meldung._all() if d.get("uid") == uid]
        self.assertEqual([(d["status"], d["parts"]["text"]) for d in mine], [("entwurf", "Wecker blieb stumm")])
        self.assertEqual([x for x in SENT if x[0] == "POST"], [])              # nothing goes out by voice
        q, uid2 = profile("RpWilli")
        r = q.post("/api/chat", json={"messages": [{"role": "user", "content": "Spark, Problem melden: fremde Stimme"}],
                                      "client": "speaker"})
        list(helpers.events(r))
        self.assertEqual([d for d in meldung._all() if d.get("uid") == uid2], [])   # a voice the speaker did not know

    def test_app_key_reaches_only_the_report_paths(self):
        helpers.set_config(iphone=True)
        try:
            p, uid = profile("RpUte")
            p.put("/api/profile/settings", json={"app_on": True})
            a = client()
            a.headers[profiles.DEVICE_HEADER] = profiles.add_device("RpUte App", uid, scope="app")
            d = a.post("/api/report/draft", json={"text": "App hängt", "applog": "engine start\nUte 10.1.2.3"}).json()
            self.assertEqual(d["channel"], "app")
            log = [x["line"] for x in d["lines"] if x["part"] == "applog"]
            self.assertEqual(log[0], "engine start")
            self.assertNotIn("RpUte", log[1])
            self.assertNotIn("10.1.2.3", log[1])
            self.assertIn(a.put("/api/admin/report/token", json={"token": TOKEN}).status_code, (401, 403))
            w = client()
            w.headers[profiles.DEVICE_HEADER] = profiles.add_device("RpUte Uhr", uid, scope="watch")
            self.assertIn(w.post("/api/report/draft", json={"text": "von der Uhr"}).status_code, (401, 403))
        finally:
            helpers.set_config(iphone=False)


class AnswerReports(Base):
    """„Mach ein Issue draus“ and „Melden“ under an answer (Dominik 2026-11-13): a report bound to exactly that
    answer; question and answer stay on the Spark and go to GitHub only ticked or with „Direkt an GitHub senden“."""

    def ask(self, c, text, client="web"):
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "client": client})
        return list(helpers.events(r))

    def aid(self, evs):
        ids = [e["id"] for e in evs if e["type"] == "melden"]
        return ids[0] if ids else None

    def tearDown(self):
        helpers.set_config(report_direct=False)
        super().tearDown()

    def test_the_sentence(self):
        A = meldung.answer_phrase
        self.assertEqual(A("Mach ein Issue draus"), (True, ""))
        self.assertEqual(A("Spark, mach daraus ein Issue: die Uhrzeit stimmt nicht"), (True, "die Uhrzeit stimmt nicht"))
        self.assertEqual(A("Das war falsch, mach einen Fehlerbericht draus."), (True, ""))
        self.assertEqual(A("Melde das als Fehler"), (True, ""))
        self.assertEqual(A("make an issue of it: wrong date"), (True, "wrong date"))
        for no in ("Wie mache ich ein Issue?", "Melde das Problem mit dem Wecker", "Mach ein Foto", "", None):
            self.assertIsNone(A(no), no)

    def test_off_no_button_and_never_for_guests(self):
        helpers.set_config(report=False)
        c, uid = profile("RpAnOff")
        self.assertIsNone(self.aid(self.ask(c, "Wie spät ist es?")))
        helpers.set_config(report=True)
        self.assertIsNone(self.aid(self.ask(client(), "Wie spät ist es?")))          # a guest
        block(self, uid)
        self.assertIsNone(self.aid(self.ask(c, "Wie spät ist es?")))                  # blocked for this profile

    def test_sentence_asks_what_was_wrong_and_takes_the_next_message(self):
        meldung.token_save(TOKEN)
        c, uid = profile("RpAnna")
        self.assertTrue(self.aid(self.ask(c, "Wie heißt die Hauptstadt von Australien?")))
        evs = self.ask(c, "Mach ein Issue draus")
        self.assertIsNone(self.aid(evs))                       # the report's own answer gets no button
        mine = [d for d in meldung._all() if d.get("uid") == uid]
        self.assertEqual(len(mine), 1)
        d = mine[0]
        self.assertTrue(d["answer"])
        self.assertEqual(d["status"], "entwurf")
        self.assertEqual(d["raw"]["q"], "Wie heißt die Hauptstadt von Australien?")
        self.assertTrue(d["raw"]["a"])
        self.assertIn("Frage:", d["parts"]["qa"])
        self.assertTrue(d["parts"]["way"])
        self.assertTrue(meldung.waits(uid))
        self.ask(c, "Die Hauptstadt ist Canberra, nicht Sydney")
        self.assertFalse(meldung.waits(uid))
        d = meldung._read(d["id"])
        self.assertEqual(d["parts"]["text"], "Die Hauptstadt ist Canberra, nicht Sydney")
        self.assertEqual([x for x in SENT if x[0] == "POST"], [])                     # without the switch: nothing out
        # the preview leaves question and answer out until ticked
        p = c.get("/api/report?id=" + d["id"]).json()
        self.assertNotIn("Australien", p["preview"]["body"])
        self.assertEqual(p["raw"]["q"], "Wie heißt die Hauptstadt von Australien?")
        q = c.post("/api/report/preview", json={"id": d["id"], "skip": []}).json()
        self.assertIn("Australien", q["body"])
        # an old client without "skip" sends without them
        r = c.post("/api/report/send", json={"id": d["id"], "sig": p["preview"]["sig"]})
        self.assertEqual(r.status_code, 200, r.text)
        body = [x for x in SENT if x[0] == "POST"][0][2]
        self.assertNotIn("Australien", body["body"])
        self.assertIn("falsche-antwort", body["labels"])

    def test_no_answer_no_report(self):
        c, uid = profile("RpAnLeer")
        self.ask(c, "Mach ein Issue draus")
        self.assertEqual([d for d in meldung._all() if d.get("uid") == uid], [])

    def test_button_only_for_own_answers(self):
        c, uid = profile("RpBruno")
        aid = self.aid(self.ask(c, "Wie spät ist es?"))
        o, _ = profile("RpOtto")
        self.assertEqual(o.post("/api/report/answer", json={"id": aid, "text": "x"}).status_code, 404)
        self.assertEqual(c.post("/api/report/answer", json={"id": "nope", "text": "x"}).status_code, 400)
        r = c.post("/api/report/answer", json={"id": aid, "text": "Uhrzeit falsch"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["status"], d["area"], d["answer"]), ("entwurf", "antwort", True))
        self.assertEqual(sorted(d["skip"]), sorted(x["n"] for x in d["lines"] if x["part"] == "qa"))
        self.assertNotIn("RpBruno", json.dumps(d["preview"]))

    def test_tool_results_go_along_unticked(self):
        """Issue 1 (2026-11-13): whether the tool or the model was wrong shows only with what the tool gave back."""
        c, uid = profile("RpTilo")
        aid = meldung.keep_answer(None, {"id": uid}, "welches Paket kommt heute?", "Es kommt heute keins.",
                                  [{"name": "parcels", "args": "", "result": "Pakete laut deinen Mails:\nDHL-Paket: kommt heute."}])
        self.assertTrue(aid)
        d = c.post("/api/report/answer", json={"id": aid, "text": "Antwort widerspricht der Meldung"}).json()
        res = [x for x in d["lines"] if x["part"] == "results"]
        self.assertEqual(len(res), 1)
        self.assertIn("DHL-Paket: kommt heute.", res[0]["line"])
        self.assertIn(res[0]["n"], d["skip"])
        self.assertNotIn("kommt heute.", d["preview"]["body"])
        self.assertIn("DHL-Paket: kommt heute.", d["raw"]["res"][0])
        q = c.post("/api/report/preview", json={"id": d["id"], "skip": []}).json()
        self.assertIn("Ergebnisse der Werkzeuge", q["body"])

    def test_source_is_the_note_of_this_device(self):
        """The source part is the Quellenangabe record of the same turn (keyed by the device, profiles.quelle), not a
        guess from the client name."""
        import quellenangabe
        uid = "rp-src"
        quellenangabe.merke(uid, "dev-a", [{"tool": "parcels", "de": "Pakete", "en": "Parcels", "art": "eigen", "n": 1,
                                             "mehr": []}], "")
        aid = meldung.keep_answer(None, {"id": uid}, "kommt ein Paket?", "Nein.", [{"name": "parcels", "args": ""}],
                                  None, "web", None, "dev-a")
        self.assertEqual(meldung._answers[aid]["src"], ["Pakete (eigen, 1)"])
        aid = meldung.keep_answer(None, {"id": uid}, "kommt ein Paket?", "Nein.", [{"name": "parcels", "args": ""}],
                                  None, "web", None, "dev-b")
        self.assertEqual(meldung._answers[aid]["src"], ["Werkzeug: parcels"])

    def test_direct_sends_anonymized_with_question_and_answer(self):
        meldung.token_save(TOKEN)
        helpers.set_config(report_direct=True)
        c, uid = profile("RpDora")
        aid = self.aid(self.ask(c, "Schreib RpDora eine Mail an dora@example.org"))
        d = c.post("/api/report/answer", json={"id": aid, "text": "Falsche Adresse"}).json()
        self.assertEqual(d["status"], "gesendet", d)
        body = [x for x in SENT if x[0] == "POST"][0][2]["body"]
        self.assertIn("Frage", body)
        self.assertNotIn("dora@example.org", body)
        self.assertNotIn("RpDora", body)
        # the leak check still holds it back: something slipped into the stored answer
        aid = self.aid(self.ask(c, "Wie spät ist es?"))
        real = meldung.leaks
        meldung.leaks = lambda text, k=None: ["Name"]
        self.addCleanup(setattr, meldung, "leaks", real)
        for x in meldung._all():          # the minute between two sends
            if x.get("issue"):
                x["issue"]["t"] -= 120
                meldung._write(x)
        d = c.post("/api/report/answer", json={"id": aid, "text": "noch einmal"}).json()
        self.assertEqual(d["status"], "entwurf")
        self.assertEqual(len([x for x in SENT if x[0] == "POST"]), 1)


class Live(Base):
    def test_counts_only(self):
        c, _ = profile("RpLena")
        c.post("/api/report/draft", json={"text": "Geheimes Thema Arzt"})
        x = meldung.for_live()
        self.assertEqual((x["on"], x["drafts"], x["token"]), (True, 1, False))
        import live
        snap = json.dumps(live.snapshot())
        self.assertNotIn("Arzt", snap)
        self.assertIn("GitHub (Meldungen)", snap)


if __name__ == "__main__":
    unittest.main()
