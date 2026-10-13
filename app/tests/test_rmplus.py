"""More with the reMarkable (rmplus.py, V01.0.344): Morgenblatt, @Spark on paper, tasks, meetings, the week,
web pages and mail attachments, the daily inbox and the guide that keeps itself up to date. Fake cloud from
test_remarkable; no test depends on the clock (fixed times are passed in)."""
import asyncio
import datetime
import io
import json
import time
import zipfile

from tests import helpers
from tests.test_remarkable import ADMIN, CLOUD, NB, NB2, P1, P2, Base, page_file, quiet_due, run, profile  # noqa: F401

import chat  # noqa: E402
import features  # noqa: E402
import mail  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import remarkable  # noqa: E402
import rmplus  # noqa: E402

PLUS_DUE = rmplus.due_once   # the tests call the real one; the panel's minute loop gets a quiet one (Plus)
from fastapi.testclient import TestClient  # noqa: E402

T = 1_760_000_000            # a fixed "now"
ZONE = datetime.timezone.utc


def books(name_part=""):
    """{title: (fileType, data)} of the EPUBs / PDFs in the fake cloud."""
    out = {}
    for e in remarkable.parse_index(CLOUD[0].files[CLOUD[0].root]):
        files = {f["id"]: CLOUD[0].files[f["hash"]] for f in remarkable.parse_index(CLOUD[0].files[e["hash"]])}
        meta = next((json.loads(v) for k, v in files.items() if k.endswith(".metadata")), {})
        data = next(((k.rsplit(".", 1)[1], v) for k, v in files.items() if k.endswith((".epub", ".pdf"))), None)
        if data and name_part in meta.get("visibleName", ""):
            out[meta["visibleName"]] = data
    return out


def epub_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return z.read("text.xhtml").decode()


class Plus(Base):
    def setUp(self):
        super().setUp()
        rmplus._last.clear()
        rmplus.due_once = quiet_due
        helpers.set_config(remarkable_send=True, remarkable_plus=True)

    def tearDown(self):
        rmplus.due_once = PLUS_DUE
        super().tearDown()
        helpers.set_config(remarkable_plus=False)

    def on(self, name, *parts):
        """A paired profile with these parts (all without a name): released by the admin they work at once."""
        c, uid = self.paired(name)
        self.only(c, uid, parts or rmplus.PARTS)
        return c, uid

    def only(self, c, uid, parts):
        """Only these parts for this profile: the others the admin blocked for it (chat.deny), or, where the Spark
        acts unasked (morning sheet, week, inbox), the profile switched its preference off."""
        deny = dict(features.chat_cfg().get("deny") or {})
        prefs = {}
        for k in rmplus.PARTS:
            f = features.BY_KEY[k]
            deny[k] = [u for u in deny.get(k, []) if u != uid]
            if f.pref:
                prefs[f.pref] = k in parts
            elif k not in parts:
                deny[k].append(uid)
        helpers.set_config(deny={k: v for k, v in deny.items() if v})
        r = c.put("/api/profile/settings", json=prefs)
        self.assertEqual(r.status_code, 200, r.text)

    def notebook(self, c, uid, pages, name="Küche", times=None, did=NB):
        CLOUD[0].doc(did, name, pages, times=times)
        c.put("/api/profile/remarkable/pick", json={"ids": [did], "all": False})
        run(remarkable.sync(uid))


class Switches(Plus):
    def test_off_by_default_admin_releases_admin_blocks_never_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["remarkable_plus"], False)
        for old in ("rm_ask", "rm_todo", "rm_meet", "rm_web", "rm_guide"):
            self.assertNotIn(old, profiles.SETTINGS)                        # no release switch of its own any more
        prefs = {k: features.BY_KEY[k].pref for k in rmplus.PARTS if features.BY_KEY[k].pref}
        self.assertEqual(prefs, {"rmmorning": "rm_morning", "rmweek": "rm_week", "rminbox": "rm_inbox"})
        for p in prefs.values():
            self.assertIs(profiles.SETTINGS[p][0], True, p)                 # unasked, but on unless switched off
        c, uid = self.paired("Rpoff")
        self.assertTrue(all(rmplus.on(k, uid) for k in rmplus.PARTS))     # released: works at once
        for k in rmplus.PARTS:                                              # the admin blocks each for this profile
            self.block(k, uid)
            self.assertFalse(rmplus.on(k, uid), k)
            self.block(k, uid, on=True)
            self.assertTrue(rmplus.on(k, uid), k)
        self.block("rmsend", uid)                                           # or what they build on
        self.assertFalse(any(rmplus.on(k, uid) for k in rmplus.PARTS))
        self.block("rmsend", uid, on=True)
        c.put("/api/profile/settings", json={p: False for p in prefs.values()})
        self.assertEqual({k for k in rmplus.PARTS if not rmplus.on(k, uid)}, set(prefs))   # its preference off
        c.put("/api/profile/settings", json={p: True for p in prefs.values()})
        self.assertTrue(all(rmplus.on(k, uid) for k in rmplus.PARTS))
        helpers.set_config(remarkable_send=False)                  # builds on "Aufs reMarkable schicken"
        self.assertFalse(any(rmplus.on(k, uid) for k in rmplus.PARTS))
        helpers.set_config(remarkable_send=True, remarkable_plus=False)
        self.assertFalse(any(rmplus.on(k, uid) for k in rmplus.PARTS))
        self.assertIsNone(run(PLUS_DUE(idle=True, now=T)))
        self.assertEqual(c.post("/api/profile/remarkable/guide").status_code, 403)
        g = TestClient(panel.app)
        for path in ("/api/profile/remarkable/todo", "/api/profile/remarkable/guide"):
            self.assertIn(g.post(path, json={}).status_code, (401, 403), path)
        self.assertFalse(rmplus.on("rmguide", ""))

    def test_never_while_someone_talks(self):
        self.on("Rpbusy")
        self.assertIsNone(run(PLUS_DUE(idle=False, now=T)))


class Sheet(Plus):
    def test_pdf_is_valid_with_umlauts_and_ruled_pages(self):
        pdf = rmplus.sheet("Morgenblatt Sa 11.10.", "## Termine\n09:00 Zahnarzt – „Müller“ (Praxis)\n\n" + "Wort " * 900)
        self.assertTrue(pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF"))
        xref = int(pdf.rsplit(b"startxref", 1)[1].split()[0])
        self.assertTrue(pdf[xref:].startswith(b"xref"))
        offs = [int(x.split()[0]) for x in pdf[xref:].split(b"\n")[3:] if x.endswith(b" n ")]
        for i, o in enumerate(offs, 1):
            self.assertTrue(pdf[o:].startswith(b"%d 0 obj" % i), i)
        self.assertIn("Müller".encode("cp1252"), pdf)
        self.assertIn(b"\\(Praxis\\)", pdf)                                  # brackets escaped
        self.assertGreaterEqual(pdf.count(b"/Type /Page "), 3)               # long text, then an extra ruled page
        self.assertNotIn(b"/FontFile", pdf)                                  # nothing embedded

    def test_questions_and_tasks_on_paper(self):
        self.assertEqual(rmplus.asks("Einkauf\n@Spark Wie lange hält Sauerteig?\n\nMilch"), ["Wie lange hält Sauerteig?"])
        self.assertEqual(rmplus.asks("@ spark: Wann ist Ostern 2027? @Spark Was kostet ein Brenner?"),
                         ["Wann ist Ostern 2027?", "Was kostet ein Brenner?"])
        self.assertEqual(rmplus.asks("Mail an spark@example.com"), [])
        # read handwriting: the reader's picture line and unreadable parts are not part of the question
        self.assertEqual(rmplus.asks("@Spark Wie [unleserlich] lange hält Sauerteig? Danke\nBild: Handschrift auf Linien."),
                         ["Wie lange hält Sauerteig?"])
        self.assertEqual(rmplus.asks("@Spark [unleserlich]\nBild: eine Skizze"), [])
        self.assertEqual(rmplus.todos("☐ Steuer abgeben\n[ ] Reifen wechseln\nTODO: Oma anrufen\nAufgabe: Rasen\nNotiz ohne"),
                         ["Steuer abgeben", "Reifen wechseln", "Oma anrufen", "Rasen"])


class FromPaper(Plus):
    def test_spark_question_is_answered_once_as_a_new_document(self):
        c, uid = self.on("Rpask")
        self.notebook(c, uid, [(P1, page_file("Backen\n@Spark Wie lange hält Sauerteig im Kühlschrank?"))],
                      times={P1: (T - 600) * 1000})
        helpers.LLM_CALLS.clear()
        self.assertEqual(run(rmplus.from_pages(uid, T)), "ask")
        call = next(x for x in helpers.LLM_CALLS if x["messages"][0]["content"] == rmplus.ASK_SYSTEM)
        self.assertIn("<<<", call["messages"][1]["content"])                # the page goes in as data
        self.assertIn("Die Frage der Person: Wie lange hält Sauerteig im Kühlschrank?", call["messages"][1]["content"])
        self.assertIn("eigenen Wissen", call["messages"][0]["content"])     # not only from the notes
        self.assertNotIn("tools", call)
        got = books("Antwort:")
        self.assertEqual(list(got), ["Antwort: Wie lange hält Sauerteig im Kühlschrank"])
        self.assertIn("Sauerteig", epub_text(got["Antwort: Wie lange hält Sauerteig im Kühlschrank"][1]))
        self.assertIsNone(run(rmplus.from_pages(uid, T + 60)))              # asked once
        self.assertEqual(len(books("Antwort:")), 1)
        self.assertIsNone(run(rmplus.from_pages(uid, T + 5 * 86400)))      # old pages are not looked at

    def test_shown_on_the_live_page(self):
        """Zustand → Live: the job and its end as an event, fixed words only (never the question)."""
        import live
        with open(helpers.os.environ["SPEECH_SPARK_CONFIG"]) as f:
            cfg = json.load(f)
        cfg.setdefault("logs", {})["live"] = True
        helpers.write_config(cfg)
        try:
            c, uid = self.on("Rplive", "rmask")
            self.notebook(c, uid, [(P1, page_file("@Spark Wie lange hält Sauerteig im Kühlschrank?"))],
                          times={P1: (T - 60) * 1000})
            self.assertEqual(run(PLUS_DUE(idle=True, now=T, uids=[uid])), "pages")
            ev = [e for e in live.snapshot()["events"] if "reMarkable" in e["area"] + e["text"]]
            self.assertTrue(any("@Spark-Antwort fertig" in e["text"] for e in ev), ev)
            self.assertFalse(any("Sauerteig" in e["text"] for e in live.snapshot()["events"]))
            self.assertEqual([b for b in live.snapshot()["bg"] if b["job"].startswith("reMarkable")], [])
        finally:
            cfg["logs"]["live"] = False
            helpers.write_config(cfg)

    def test_tasks_become_reminders_only_on_click(self):
        c, uid = self.on("Rptodo")
        self.notebook(c, uid, [(P1, page_file("☐ Steuer abgeben\nTODO Reifen wechseln"))], times={P1: (T - 60) * 1000})
        run(rmplus.from_pages(uid, T))
        todos = c.get("/api/profile/remarkable").json()["plus"]["todos"]
        self.assertEqual(sorted(x["text"] for x in todos), ["Reifen wechseln", "Steuer abgeben"])
        self.assertEqual(profiles.reminders(uid), [])                       # nothing by itself
        run(rmplus.from_pages(uid, T + 60))
        self.assertEqual(len(c.get("/api/profile/remarkable").json()["plus"]["todos"]), 2)   # not twice
        steuer = next(x for x in todos if x["text"] == "Steuer abgeben")
        self.assertEqual(c.post("/api/profile/remarkable/todo", json={"id": steuer["id"], "do": "remind", "due": 5}).status_code, 400)
        due = int((time.time() + 86400) * 1000)
        r = c.post("/api/profile/remarkable/todo", json={"id": steuer["id"], "do": "remind", "due": due})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([x["text"] for x in profiles.reminders(uid)], ["Steuer abgeben"])
        other = next(x for x in todos if x["text"] != "Steuer abgeben")
        c.post("/api/profile/remarkable/todo", json={"id": other["id"], "do": "drop"})
        self.assertEqual(c.get("/api/profile/remarkable").json()["plus"]["todos"], [])
        self.assertEqual(len(profiles.reminders(uid)), 1)
        self.assertEqual(c.post("/api/profile/remarkable/todo", json={"id": other["id"], "do": "drop"}).status_code, 404)

    def test_meeting_summarized_after_quiet_time_once(self):
        c, uid = self.on("Rpmeet", "rmmeet")
        self.notebook(c, uid, [(P1, page_file("Besprechung Heizung\nBrenner tauschen, Müller fragt Angebot an"))],
                      name="Besprechung Heizung", times={P1: (T - 600) * 1000})
        self.assertIsNone(run(rmplus.from_pages(uid, T)))                  # still being written
        helpers.LLM_CALLS.clear()
        self.assertEqual(run(rmplus.from_pages(uid, T + rmplus.QUIET)), "meet")
        self.assertTrue(any(x["messages"][0]["content"] == rmplus.MEET_SYSTEM for x in helpers.LLM_CALLS))
        self.assertEqual(list(books("Zusammenfassung")), ["Zusammenfassung Besprechung Heizung"])
        self.assertIsNone(run(rmplus.from_pages(uid, T + rmplus.QUIET + 60)))   # the same notes: not again

    def test_other_notebooks_are_no_meeting(self):
        c, uid = self.on("Rpnomeet", "rmmeet")
        self.notebook(c, uid, [(P1, page_file("Einkaufsliste\nMilch"))], name="Einkauf", times={P1: (T - 7200) * 1000})
        self.assertIsNone(run(rmplus.from_pages(uid, T)))


class Sheets(Plus):
    def test_morning_sheet_once_a_day_from_its_time(self):
        c, uid = self.on("Rpmorning", "rmmorning")
        c.put("/api/profile/settings", json={"rm_morning_at": "07:15"})
        day = lambda h, m: datetime.datetime(2026, 10, 10, h, m, tzinfo=ZONE)   # noqa: E731
        p = rmplus.plus(uid)
        self.assertFalse(rmplus.morning_due(uid, day(7, 0), p))
        self.assertTrue(rmplus.morning_due(uid, day(7, 20), p))
        self.assertFalse(rmplus.morning_due(uid, day(9, 30), p))             # two hours' window
        r = run(rmplus.morning(uid, day(7, 20)))
        self.assertEqual(r["title"], "Morgenblatt Sa 10.10.")
        kind, data = books("Morgenblatt")["Morgenblatt Sa 10.10."]
        self.assertEqual((kind, data[:5]), ("pdf", b"%PDF-"))
        self.assertFalse(rmplus.morning_due(uid, day(7, 30), rmplus.plus(uid)))
        c.put("/api/profile/settings", json={"rm_morning_at": "25:00"})          # not a time: not taken
        self.assertEqual(profiles.settings(uid)["rm_morning_at"], "07:15")

    def test_week_on_friday_evening_once(self):
        c, uid = self.on("Rpweek", "rmweek")
        fri = datetime.datetime(2025, 10, 10, 17, 30, tzinfo=ZONE)          # T is on that Thursday
        p = rmplus.plus(uid)
        self.assertFalse(rmplus.week_due(fri.replace(hour=16), p))
        self.assertFalse(rmplus.week_due(fri - datetime.timedelta(days=1), p))
        self.assertTrue(rmplus.week_due(fri, p))
        self.notebook(c, uid, [(P1, page_file("Urlaub planen"))], times={P1: (T - 3600) * 1000})
        r = run(rmplus.week(uid, fri))
        self.assertEqual(r["title"], "Wochenrückblick KW 41")
        self.assertEqual(books("Wochen")["Wochenrückblick KW 41"][0], "pdf")
        self.assertFalse(rmplus.week_due(fri, rmplus.plus(uid)))


class Guide(Plus):
    def test_every_remarkable_function_is_in_the_guide(self):
        def family(f):
            while f.parent:
                if f.parent == "remarkable":
                    return True
                f = features.BY_KEY[f.parent]
            return False
        rm = {f.key for f in features.FEATURES if f.key == "remarkable" or family(f)}
        self.assertEqual(rm - {k for k, _, _ in rmplus.GUIDE}, set())
        self.assertEqual({k for k, _, _ in rmplus.GUIDE} - rm, set())

    def test_only_remarkable_and_the_service_marked_on_or_off(self):
        c, uid = self.on("Rpguidetext", "rmguide", "rmask")
        text = rmplus.guide_text(uid)
        self.assertIn("## @Spark: Fragen auf Papier (an)", text)
        self.assertIn("## Morgenblatt (aus)", text)
        self.assertIn("## So arbeitet der Dienst", text)
        self.assertNotIn("Neueste zuerst", text)                             # the Spark does not offer it now
        helpers.set_config(remarkable_fresh=True)
        self.assertIn("## Neueste zuerst (an)", rmplus.guide_text(uid))      # released: on at once
        self.block("rmfresh", uid)
        self.assertIn("## Neueste zuerst (aus)", rmplus.guide_text(uid))     # blocked for this profile
        for word in ("Home Assistant", "Kalender verbinden", "Telegram einrichten"):
            self.assertNotIn(word, text)

    def test_guide_is_renewed_in_place_when_its_text_changes(self):
        c, uid = self.on("Rpguide", "rmguide")
        self.assertEqual(run(PLUS_DUE(idle=True, now=T, uids=[uid])), "guide")
        first = remarkable.load(uid)["own"]["guide"]
        self.assertIn("Spark-Anleitung", books("Spark-Anleitung"))
        # the person writes into it on the tablet: an extra page file in that document
        e = next(x for x in remarkable.parse_index(CLOUD[0].files[CLOUD[0].root]) if x["id"] == first)
        idx = remarkable.parse_index(CLOUD[0].files[e["hash"]])
        mark = CLOUD[0].put(b"handwriting")
        rows = sorted([(f["hash"], f["id"], f["size"]) for f in idx] + [(mark, first + "/p1.rm", 11)], key=lambda r: r[1])
        body = "3\n" + "".join(f"{h}:0:{i}:0:{s}\n" for h, i, s in rows)
        import hashlib
        dh = hashlib.sha256(b"".join(bytes.fromhex(h) for h, _, _ in rows)).hexdigest()
        CLOUD[0].files[dh] = body.encode()
        CLOUD[0].entries[first] = (dh, len(rows), sum(s for _, _, s in rows))
        CLOUD[0].commit()
        n = len(CLOUD[0].entries)
        self.assertIsNone(run(rmplus.guide(uid)))                            # same text: nothing written
        self.only(c, uid, ("rmguide", "rmask"))                            # a change of what it may changes the text
        r = run(rmplus.guide(uid))
        self.assertTrue(r["renewed"])
        self.assertEqual(remarkable.load(uid)["own"]["guide"], first)
        self.assertEqual(len(CLOUD[0].entries), n)                          # no second guide
        e = next(x for x in remarkable.parse_index(CLOUD[0].files[CLOUD[0].root]) if x["id"] == first)
        ids = {f["id"] for f in remarkable.parse_index(CLOUD[0].files[e["hash"]])}
        self.assertIn(first + "/p1.rm", ids)                                 # the person's marks stay
        self.assertIn("@Spark: Fragen auf Papier (an)", epub_text(books("Spark-Anleitung")["Spark-Anleitung"][1]))
        # deleted on the tablet: a new one, never a write to something that is not there
        CLOUD[0].drop(first)
        self.only(c, uid, ("rmguide", "rmask", "rmtodo"))
        r = run(rmplus.guide(uid))
        self.assertFalse(r["renewed"])
        self.assertNotEqual(remarkable.load(uid)["own"]["guide"], first)

    def test_only_own_documents_are_renewed(self):
        c, uid = self.on("Rpown", "rmguide")
        CLOUD[0].doc(NB2, "Mein Buch", [(P1, page_file("Eigenes"))])
        d = remarkable.load(uid)
        d["own"] = {"guide": NB2.replace("0", "1", 1)}                     # an id the Spark never made: not there
        remarkable.save(uid, d)
        r = run(rmplus.guide(uid, force=True))
        self.assertFalse(r["renewed"])
        self.assertIn("Mein Buch", [m["visibleName"] for m in CLOUD[0].listed().values()])
        with self.assertRaises(remarkable.CloudError):
            run(remarkable._add_to_root(uid, [], {"0" * 8 + NB[8:]: {"hash": "0" * 64, "id": "x", "subfiles": 0, "size": 0}}))

    def test_button_puts_it_there_now(self):
        c, uid = self.on("Rpguidebtn", "rmguide")
        r = c.post("/api/profile/remarkable/guide")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["where"], "Spark")


class Inbox(Plus):
    def test_dictated_notes_gather_in_one_document_a_day(self):
        c, uid = self.on("Rpinbox", "rminbox")
        ctx = {"who": {"id": uid}, "own": True, "text": "Notier auf dem reMarkable: Milch"}
        out = run(remarkable.tool("remarkable_note", {"title": "Milch", "text": "Milch kaufen"}, ctx))
        self.assertIn("Eingang", out)
        run(remarkable.tool("remarkable_note", {"title": "Brot", "text": "Brot backen"}, ctx))
        got = books("Eingang")
        self.assertEqual(len(got), 1)
        text = epub_text(list(got.values())[0][1])
        self.assertIn("Milch kaufen", text)
        self.assertIn("Brot backen", text)
        c.put("/api/profile/settings", json={"rm_inbox": False})            # preference off: one document each again
        run(remarkable.tool("remarkable_note", {"title": "Käse", "text": "Käse"}, ctx))
        self.assertIn("Käse", books("Käse"))


class WebAndMail(Plus):
    def test_tools_only_on_own_words_with_address_or_attachment(self):
        c, uid = self.on("Rpweb", "rmweb")
        self.assertEqual(rmplus.tools_for(uid, "Leg die Seite aufs reMarkable"), [])
        self.assertEqual([t["function"]["name"] for t in rmplus.tools_for(uid, "Leg https://example.org/a aufs reMarkable")],
                         ["remarkable_page"])
        self.block("rmweb", uid)
        self.assertEqual(rmplus.tools_for(uid, "Leg https://example.org/a aufs reMarkable"), [])
        self.assertTrue(remarkable.answer_wanted("Leg https://example.org/a aufs reMarkable", uid))   # off: the answer goes
        self.block("rmweb", uid, on=True)
        self.assertFalse(remarkable.answer_wanted("Leg https://example.org/a aufs reMarkable", uid))  # on: the page itself
        o = remarkable.offer({"who": {"id": uid}, "own": True, "text": "Leg https://example.org/a aufs reMarkable"})
        self.assertEqual([t["function"]["name"] for t in o["tools"]], ["remarkable_note", "remarkable_sent", "remarkable_page"])

    def test_page_as_ebook(self):
        c, uid = self.on("Rppage", "rmweb")
        real = chat.page_text

        async def page(cl, url, limit=3000):
            return "Sauerteig braucht Zeit. Er hält eine Woche im Kühlschrank. " * 20 if "lang" in url else "kurz"
        chat.page_text = page
        try:
            ctx = {"who": {"id": uid}, "own": True}
            self.assertIn("ließ sich nicht lesen", run(remarkable.tool("remarkable_page", {"url": "https://example.org/kurz"}, ctx)))
            self.assertIn("Adresse", run(remarkable.tool("remarkable_page", {"url": "file:///etc/passwd"}, ctx)))
            out = run(remarkable.tool("remarkable_page", {"url": "https://example.org/lang", "title": "Sauerteig"}, ctx))
        finally:
            chat.page_text = real
        self.assertIn("Liegt jetzt", out)
        self.assertIn("Quelle: https://example.org/lang", epub_text(books("Sauerteig")["Sauerteig"][1]))

    def test_mail_attachment_pdf(self):
        c, uid = self.on("Rpattach", "rmweb")
        real_get, real_att = mail.get, mail.attachment
        mail.get = lambda u: {"accounts": [{"id": "m1"}]}
        pdf = rmplus.sheet("Rechnung", "Betrag 12 €", ruled=False)
        mail.attachment = lambda u, q, days, most: ("Rechnung 10-2026.pdf", pdf, "pdf") if "bank" in q.lower() else None
        try:
            ctx = {"who": {"id": uid}, "own": True}
            self.assertIn("keinen PDF", run(remarkable.tool("remarkable_attachment", {"query": "Versicherung"}, ctx)))
            out = run(remarkable.tool("remarkable_attachment", {"query": "Bank"}, ctx))
        finally:
            mail.get, mail.attachment = real_get, real_att
        self.assertIn("Rechnung 10-2026.pdf", out)
        self.assertEqual(books("Rechnung")["Rechnung 10-2026"], ("pdf", pdf))

    def test_attachment_needs_a_whole_pdf(self):
        import email.message
        msg = email.message.EmailMessage()
        msg.set_content("Anbei")
        msg.add_attachment(b"%PDF-1.4 abgeschnitten", maintype="application", subtype="pdf", filename="a.pdf")
        msg.add_attachment(b"%PDF-1.4 ganz\n%%EOF\n", maintype="application", subtype="pdf", filename="b.pdf")

        class Sess:
            def __init__(self, a):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def body(self, u, most=0):
                return msg
        real = (mail.find, mail.get, mail._Session)
        mail.find = lambda *a: ([("m1", 7, {})], [], False)
        mail.get = lambda u: {"accounts": [{"id": "m1"}]}
        mail._Session = Sess
        try:
            self.assertEqual(mail.attachment("x", "Bank")[0], "b.pdf")     # the cut-off one is skipped
            self.assertIsNone(mail.attachment("x", "Bank", most=5))
        finally:
            mail.find, mail.get, mail._Session = real




class SheetOnRequest(Plus):
    """Dominik 2026-10-13: „Leg mir das Morgenblatt erneut auf den reMarkable“ found no tool. remarkable_sheet makes
    the named sheet now, offered only when the person's own words name it and its switch is on."""
    ASK = "Leg mir das Morgenblatt erneut auf den reMarkable"

    def test_offered_only_for_a_named_sheet_with_its_switch(self):
        c, uid = self.on("Rpsheet", "rmmorning", "rmguide")
        o = remarkable.offer({"who": {"id": uid}, "own": True, "text": self.ASK})
        sheet = [t for t in o["tools"] if t["function"]["name"] == "remarkable_sheet"]
        self.assertEqual(sheet[0]["function"]["parameters"]["properties"]["what"]["enum"], ["morgen"])
        self.assertIn("remarkable_sheet", o["changes"])
        self.assertFalse(remarkable.answer_wanted(self.ASK, uid))       # never the model's answer as a document
        self.assertEqual(rmplus.tools_for(uid, "Leg die Anleitung aufs reMarkable")[0]["function"]["parameters"]
                         ["properties"]["what"]["enum"], ["anleitung"])
        self.assertEqual(rmplus.tools_for(uid, "Was ist ein reMarkable?"), [])
        self.assertEqual(rmplus.sheets_for(uid, "Put the guide on my reMarkable"), ["anleitung"])
        c.put("/api/profile/settings", json={"rm_morning": False})
        self.assertEqual(rmplus.tools_for(uid, self.ASK), [])
        self.assertFalse(remarkable.answer_wanted("Schick das Morgenblatt nochmal aufs reMarkable", uid))  # off: no text
        self.assertEqual(run(rmplus.sheet_now(uid, "morgen")), "Das ist aus oder gibt es nicht.")
        self.assertEqual(run(rmplus.sheet_now(uid, "rm -rf")), "Das ist aus oder gibt es nicht.")

    def test_morning_sheet_now(self):
        c, uid = self.on("Rpsheetnow", "rmmorning")
        old = chat.morning_briefing

        async def brief(uid, tz="", markdown=False):
            return "Heute sonnig."
        chat.morning_briefing = brief
        try:
            said = run(remarkable.tool("remarkable_sheet", {"what": "morgen"}, {"who": {"id": uid}}))
        finally:
            chat.morning_briefing = old
        self.assertTrue(said.startswith("Das Morgenblatt liegt jetzt auf deinem reMarkable"), said)
        self.assertTrue(books("Morgenblatt"))
