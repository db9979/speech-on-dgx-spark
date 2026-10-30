"""Finden, Stufe C (fundquellen.py, plan such-index): appointments, contacts, conversations, lists, reminders,
pictures and songs in the search index, each behind its sub-switch (off by default) and the function it comes from;
appointments and contacts sealed like mail (nothing in plain text on the disk); conversations only through recall (no
word of them in fund.db, answers from mail stay out); a shared list only with the right to it; periods by fixed rules
(frisch.spanne with a fixed „now“, never the clock); „vom OP“: the newest past appointment gives a window that is a
bonus, never a limit, and without one a fixed sentence says so. Logs with fixed words, Live with numbers only."""
import asyncio
import contextlib
import datetime
import io
import json
import os
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import bilder  # noqa: E402
import calendars  # noqa: E402
import contacts  # noqa: E402
import features  # noqa: E402
import frisch  # noqa: E402
import fund  # noqa: E402
import intent  # noqa: E402
import kalenderspiegel  # noqa: E402
import musik  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import tasks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000.0          # 2027-01-15, a fixed moment, never the clock
UTC = datetime.timezone.utc
SUBS = ("fund_termine", "fund_kontakte", "fund_chats", "fund_listen", "fund_medien")
KEYS = ("fundtermine", "fundkontakte", "fundchats", "fundlisten", "fundmedien")
URL = "https://kalender.example.invalid/dav/privat/"


def run(coro):
    return asyncio.run(coro)


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def day(*a):
    return int(datetime.datetime(*a, tzinfo=UTC).timestamp())


def ics(uid, summary, start, place="", text=""):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//\r\nBEGIN:VEVENT\r\n"
            f"UID:{uid}\r\nDTSTAMP:20250101T000000Z\r\nDTSTART:{start}\r\nSUMMARY:{summary}\r\n"
            + (f"LOCATION:{place}\r\n" if place else "") + (f"DESCRIPTION:{text}\r\n" if text else "")
            + "END:VEVENT\r\nEND:VCALENDAR\r\n")


def profile(name, pin="2468"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    uid = next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)
    return c, uid


def section(name, **kw):
    """The picture or music model's section of the config (features.READY: installed), put back by the caller."""
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    old = dict(c.get(name) or {})
    c.setdefault(name, {}).update(kw)
    helpers.write_config(c)
    return old


def disk(uid):
    data = b""
    for ext in ("", "-wal", "-shm"):
        p = fund.db_path(uid) + ext
        if os.path.exists(p):
            with open(p, "rb") as f:
                data += f.read()
    return data


class Base(unittest.TestCase):
    NAME = "Fundquelle Ida"

    def setUp(self):
        helpers.keep_chat(self, "fund", *SUBS, "documents", "knowledge_book", "contacts", "calendar", "history", "tasks",
                          "tasks_share", "reminders", "bilder", "musik")
        helpers.set_config(fund=True, documents=False, knowledge_book=False, contacts=True, calendar=True, history=True,
                           tasks=True, reminders=True, bilder=True, musik=True, tasks_share=False,
                           **{k: True for k in SUBS})
        fund._live.update(at=0.0, d=None)
        fund._last.clear()
        self.c, self.uid = profile(self.NAME)
        self.clean(self.uid)

    def clean(self, uid):
        for c in calendars.get(uid)["calendars"]:
            calendars.remove(uid, c["id"])
        contacts._save(uid, cards=[])
        with profiles._lock:
            profiles._write(profiles._path(uid, "reminders.json"), [])
            profiles._write(profiles._path(uid, "tasks.json"), {})
        profiles.write_own(uid, "convos.json", [])
        bilder._save_index(uid, [])
        musik._save_index(uid, [])
        with quiet():
            fund.leeren(uid, hand=True)

    def calendar(self, uid, objects):
        calendars.add(uid, calendars.entry({"url": URL, "name": "Privat"}))
        cid = calendars.get(uid)["calendars"][-1]["id"]
        kalenderspiegel._mem[cid] = {URL: {"token": "", "at": NOW, "done": True,
                                           "items": {f"/dav/privat/{h}.ics": [f'"{tag}"', text, 0.0, kalenderspiegel.FOREVER]
                                                     for h, tag, text in objects}}}
        self.addCleanup(lambda: [calendars.remove(uid, c["id"]) for c in calendars.get(uid)["calendars"]])
        return cid

    def index(self, uid=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = fund.runde(uid or self.uid, NOW)
        self.log = buf.getvalue()
        return got

    def find(self, words, uid=None, **kw):
        return fund.suche(uid or self.uid, words, now=NOW, **kw)


class Off(Base):
    def test_sub_switches_off_by_default_and_each_alone(self):
        shipped = json.loads(helpers.repo_file("app", "config.default.json"))["chat"]
        for k in SUBS:
            self.assertIs(shipped[k], False, k)
        for k in KEYS:
            self.assertNotIn(k, features.DEFAULT_ON)
            self.assertEqual(features.BY_KEY[k].parent, "fund", k)
        profiles.add_reminder(self.uid, "Quokkafutter kaufen", NOW * 1000)
        helpers.set_config(fund_listen=False)
        self.assertNotIn("erinnerung", {q.name for q in fund.quellen_fuer(self.uid)})
        self.index()
        self.assertEqual(self.find("Quokkafutter"), [])
        helpers.set_config(fund_listen=True)
        self.index()
        self.assertEqual([h["quelle"] for h in self.find("Quokkafutter")], ["erinnerung"])
        # the function a source comes from off: the source goes, its rows with the next round
        helpers.set_config(reminders=False)
        self.assertEqual(self.index()["erinnerung"], (0, 1))
        self.assertEqual(self.find("Quokkafutter"), [])
        # Finden itself off: nothing at all
        helpers.set_config(reminders=True, fund=False)
        self.assertEqual(fund.quellen_fuer(self.uid), [])

    def test_never_for_guests(self):
        for k in KEYS:
            self.assertEqual(features.reason(k, None), "guest", k)


class Spanne(unittest.TestCase):
    """frisch.spanne: fixed rules with a fixed „now“ (Wednesday 2026-10-07 15:00 UTC), never the clock."""
    NOW = datetime.datetime(2026, 10, 7, 15, 0, tzinfo=UTC).timestamp()

    def test_periods(self):
        cases = {"heute": (day(2026, 10, 7), None), "gestern": (day(2026, 10, 6), day(2026, 10, 7)),
                 "vorgestern": (day(2026, 10, 5), day(2026, 10, 6)), "diese Woche": (day(2026, 10, 5), None),
                 "Telegram-Gespräch von letzter Woche": (day(2026, 9, 28), day(2026, 10, 5)),
                 "last week": (day(2026, 9, 28), day(2026, 10, 5)), "letzten Monat": (day(2026, 9, 1), day(2026, 10, 1)),
                 "diesen Monat": (day(2026, 10, 1), None), "letztes Jahr": (day(2025, 1, 1), day(2026, 1, 1)),
                 "dieses Jahr": (day(2026, 1, 1), None), "Rechnung von 2023": (day(2023, 1, 1), day(2024, 1, 1)),
                 "Rechnung von 2023.": (day(2023, 1, 1), day(2024, 1, 1)),
                 "im März": (day(2026, 3, 1), day(2026, 4, 1)), "im November": (day(2025, 11, 1), day(2025, 12, 1)),
                 "im Oktober": (day(2026, 10, 1), day(2026, 11, 1)), "März 2024": (day(2024, 3, 1), day(2024, 4, 1)),
                 "Mail vom Dezember 2025": (day(2025, 12, 1), day(2026, 1, 1)),
                 "vor 3 Tagen": (day(2026, 10, 4), day(2026, 10, 5)), "vor zwei Wochen": (day(2026, 9, 21), day(2026, 9, 28)),
                 "vor einem Monat": (day(2026, 9, 1), day(2026, 10, 1)), "vor drei Monaten": (day(2026, 7, 1), day(2026, 8, 1)),
                 "vor einem Jahr": (day(2025, 1, 1), day(2026, 1, 1)), "2 weeks ago": (day(2026, 9, 21), day(2026, 9, 28))}
        for text, want in cases.items():
            got = frisch.spanne(text, self.NOW, UTC)
            self.assertIsNotNone(got, text)
            self.assertEqual(got[:2], want, text)
            a, b = got[2]
            self.assertTrue(text[a:b].strip(), text)

    def test_no_period(self):
        for text in ("Rechnungen von 2022 und 2023", "Rechnung Nummer RE-2024-88812", "am 12.03.2024", "Such die Rechnung",
                     "vor dem OP", "Kundennummer 40211", "", "Mai", "vor Ort"):
            self.assertIsNone(frisch.spanne(text, self.NOW, UTC), text)

    def test_the_tool_filter_takes_it(self):
        flt, dropped = fund.filter_eigen({"von": "2026-09-28"}, "Finde das Telegram-Gespräch von letzter Woche", self.NOW, UTC)
        self.assertEqual((flt["von"], flt["bis"]), ("2026-09-28", "2026-10-04"))
        self.assertEqual(dropped, 0)
        flt, _ = fund.filter_eigen({}, "Such die Rechnung von heute", self.NOW, UTC)
        self.assertEqual(flt, {"von": "2026-10-07"})


class Termine(Base):
    OBJECTS = (("op", "e1", ics("op-1", "OP Knie", "20250310T090000Z", "Klinik Nordstadt", "Nüchtern kommen Quittungsheft")),
               ("zahn", "e2", ics("z-1", "Zahnreinigung", "20261120T080000Z", "Praxis Wombat")))

    def test_sealed_incremental_and_gone_with_the_calendar(self):
        cid = self.calendar(self.uid, self.OBJECTS)
        self.assertEqual(self.index()["termin"], (2, 0))
        self.assertEqual(self.index(), {})                     # nothing changed: nothing to do
        hits = self.find("Nordstadt")
        self.assertEqual([h["titel"] for h in hits], ["OP Knie"])
        self.assertEqual(hits[0]["wann"], day(2025, 3, 10, 9))
        self.assertEqual(hits[0]["weg"]["art"], "termin")
        self.assertEqual(hits[0]["felder"]["ort"], "Klinik Nordstadt")
        self.assertEqual([h["titel"] for h in self.find("Quittung")], ["OP Knie"])   # four letters find the longer word
        data = disk(self.uid)
        for word in ("OP Knie", "Nordstadt", "Zahnreinigung", "Wombat", "Quittungsheft", "Klinik"):
            self.assertNotIn(word.encode(), data, word)
            self.assertNotIn(word.lower().encode(), data.lower(), word)
        # a changed object (another etag) is read again, a deleted one leaves
        items = kalenderspiegel._mem[cid][URL]["items"]
        items["/dav/privat/op.ics"] = ['"e3"', ics("op-1", "OP Knie links", "20250310T090000Z", "Klinik Nordstadt"), 0.0, 0.0]
        del items["/dav/privat/zahn.ics"]
        self.assertEqual(self.index()["termin"], (1, 1))
        self.assertEqual([h["titel"] for h in self.find("links")], ["OP Knie links"])
        self.assertEqual(self.find("Wombat"), [])
        # the calendar removed: its appointments are never a hit again, at once
        calendars.remove(self.uid, cid)
        self.assertEqual(self.find("Nordstadt"), [])
        self.assertEqual(self.index()["termin"], (0, 1))

    def test_vom_op_window_is_a_bonus_and_a_fixed_sentence_without(self):
        self.calendar(self.uid, self.OBJECTS[:1])
        # two reminders with the same words: one long before the OP, one in its window (14 days before to 60 after)
        profiles.add_reminder(self.uid, "Thomann Rechnung zahlen", day(2025, 1, 1) * 1000)
        profiles.add_reminder(self.uid, "Thomann Rechnung zahlen", day(2025, 4, 1) * 1000)
        self.index()
        plain = self.find("Thomann Rechnung")
        self.assertEqual([h["wann"] for h in plain], [day(2025, 1, 1), day(2025, 4, 1)])
        info = {}
        got = self.find("Thomann Rechnung", bezug="OP", info=info)
        self.assertEqual([h["wann"] for h in got], [day(2025, 4, 1), day(2025, 1, 1)])   # a bonus, nothing dropped
        self.assertEqual(info, {"bezug": "OP", "termin": day(2025, 3, 10, 9)})
        # the tool: the event only from the own words; its word is no search word; a fixed sentence and fixed log words
        who = {"id": self.uid, "name": self.NAME}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = run(fund.tool("fund_suche", {"worte": "Thomann Rechnung vom OP"},
                                {"who": who, "private": True, "text": "Such mir die Rechnung von Thomann vom OP"}))
        self.assertTrue(out.startswith("Bezug: der Termin „OP“ am "), out)
        self.assertLess(out.index("01.04.2025"), out.index("01.01.2025"))
        self.assertIn("fund: bezug | termin gefunden", buf.getvalue())
        self.assertNotIn("Thomann", buf.getvalue())
        with contextlib.redirect_stdout(buf):
            out = run(fund.tool("fund_suche", {"worte": "Thomann Rechnung"},
                                {"who": who, "private": True, "text": "Such die Rechnung von Thomann vom Zahnarzt"}))
        self.assertTrue(out.startswith("Einen Termin „Zahnarzt“ habe ich im Kalender nicht gefunden.\n"), out)
        self.assertIn("Thomann Rechnung zahlen", out)          # searched without a window
        self.assertIn("fund: bezug | kein termin", buf.getvalue())
        self.assertNotIn("Zahnarzt", buf.getvalue())
        # a weak word without an appointment says nothing; the event never from the model's words alone
        out = run(fund.tool("fund_suche", {"worte": "Thomann vom OP"}, {"who": who, "private": True, "text": "Such Thomann beim Hafen"}))
        self.assertFalse(out.startswith(("Bezug", "Einen Termin")), out)
        # a future appointment is no event of the past; one in another profile is never seen
        self.assertIsNone(fund.bezug_aus("Rechnung vom letzten Jahr"))
        self.assertIsNone(fund.bezug_aus("Rechnung vom Montag"))
        self.assertEqual(fund.bezug_aus("Such die Rechnung vom OP")[:2], ("OP", True))
        self.assertEqual(fund.bezug_aus("Fotos von der Hochzeit")[:2], ("Hochzeit", False))
        info = {}
        self.find("Rechnung", bezug="Zahnreinigung", info=info)
        self.assertIsNone(info.get("termin"))
        c2, other = profile("Fundquelle Ole")
        self.clean(other)
        info = {}
        self.find("Rechnung", uid=other, bezug="OP", info=info)
        self.assertIsNone(info.get("termin"))

    def test_the_page_shows_period_and_event(self):
        self.calendar(self.uid, self.OBJECTS[:1])
        profiles.add_reminder(self.uid, "Thomann Rechnung zahlen", day(2025, 4, 1) * 1000)
        self.index()
        r = self.c.post("/api/profile/fund/suche", json={"worte": "Thomann vom OP"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["deutung"]["bezug"], "OP")
        self.assertEqual(d["deutung"]["termin"], day(2025, 3, 10, 9))
        self.assertEqual([h["quelle"] for h in d["treffer"]], ["erinnerung"])   # „OP“ is no search word: the appointment stays out
        d = self.c.post("/api/profile/fund/suche", json={"worte": "Thomann 2025"}).json()
        self.assertEqual(d["deutung"], {"von": "2025-01-01", "bis": "2025-12-31"})
        self.assertEqual(len(d["treffer"]), 1)
        d = self.c.post("/api/profile/fund/suche", json={"worte": "Thomann 2024"}).json()
        self.assertEqual(d["treffer"], [])


class Kontakte(Base):
    def test_name_company_place_sealed_never_numbers(self):
        contacts._save(self.uid, cards=[{"id": "k1", "name": "Klara Kakadu", "org": "Quokka Versand", "nick": "",
                                         "title": "Einkauf", "phones": [["Handy", "+49 170 5550199"]],
                                         "emails": ["zwergpinguin@example.invalid"], "addrs": [{"kind": "Arbeit", "street": "Hafenweg 9",
                                                                                        "zip": "20457", "city": "Hamburg"}]}])
        self.assertEqual(self.index()["kontakt"], (1, 0))
        hits = self.find("Kakadu")
        self.assertEqual([(h["quelle"], h["titel"]) for h in hits], [("kontakt", "Klara Kakadu")])
        self.assertEqual(hits[0]["felder"], {"firma": "Quokka Versand", "ort": "Hamburg"})
        self.assertEqual({(t["typ"], t["wert"]) for t in hits[0]["tags"]},
                         {("person", "Klara Kakadu"), ("firma", "Quokka Versand"), ("ort", "Hamburg")})
        self.assertEqual(len(self.find("", firma="Quokka Versand")), 1)
        for nothing in ("5550199", "Hafenweg", "zwergpinguin", "20457"):
            self.assertEqual(self.find(nothing), [], nothing)
        data = disk(self.uid)
        for word in ("Kakadu", "Quokka", "Hamburg", "5550199", "Hafenweg"):
            self.assertNotIn(word.encode(), data, word)
            self.assertNotIn(word.lower().encode(), data.lower(), word)
        contacts._save(self.uid, cards=[])
        self.assertEqual(self.index()["kontakt"], (0, 1))


class Chats(Base):
    def test_only_through_recall_never_a_word_in_the_index(self):
        profiles.save_convo(self.uid, {"id": "c1", "title": "Gespräch über Zebrafinken", "updated": int(NOW * 1000), "msgs": [
            {"role": "user", "content": "Was fressen Zebrafinken im Winter?", "via": "telegram"},
            {"role": "assistant", "content": "Hirse und Keimfutter."}]})
        profiles.save_convo(self.uid, {"id": "c2", "title": "Mail", "updated": int(NOW * 1000) - 1000, "msgs": [
            {"role": "user", "content": "Was schreibt Anna?"},
            {"role": "assistant", "content": "Anna schreibt über den Pfauenhof.", "mail": True}]})
        self.assertEqual(self.index()["chat"], (2, 0))
        hits = self.find("Keimfutter")
        self.assertEqual([h["ext"] for h in hits], ["c1"])
        self.assertEqual(hits[0]["titel"], "Gespräch über Zebrafinken")       # read from the conversation when shown
        self.assertEqual(hits[0]["felder"]["kanal"], "Telegram")
        self.assertEqual(hits[0]["weg"], {"art": "chat", "id": "c1"})
        self.assertEqual(self.find("Pfauenhof"), [])                           # an answer from mail stays in the mailbox
        self.assertEqual([h["ext"] for h in self.find("Telegram")], ["c1"])    # the channel is a field
        data = disk(self.uid)
        for word in ("Zebrafink", "Keimfutter", "Hirse", "Pfauenhof", "Anna"):
            self.assertNotIn(word.encode(), data, word)
            self.assertNotIn(word.lower().encode(), data.lower(), word)
        got = fund.eintrag(self.uid, hits[0]["id"])
        self.assertEqual(got["titel"], "Gespräch über Zebrafinken")


class Listen(Base):
    def test_own_lists_reminders_and_shared_only_with_the_right(self):
        run(tasks.add(self.uid, "einkauf", ["Bohrmaschine leihen"]))
        profiles.add_reminder(self.uid, "Reifenwechsel anmelden", day(2026, 11, 2) * 1000)
        _, owner = profile("Fundquelle Paul")
        self.clean(owner)
        lid = tasks.make_list(owner, "Baumarkt Wombat", "🔨")
        run(tasks.add(owner, lid, ["Spachtelmasse"]))
        got = self.index()
        self.assertEqual((got["liste"][0], got["erinnerung"]), (2, (1, 0)))   # Einkauf and Aufgaben, no other's list
        self.assertEqual([h["quelle"] for h in self.find("Bohrmaschine")], ["liste"])
        self.assertEqual([h["wann"] for h in self.find("Reifenwechsel")], [day(2026, 11, 2)])
        self.assertEqual(self.find("Spachtelmasse"), [])                     # not shared: never
        helpers.set_config(tasks_share=True)
        with quiet():
            tasks.set_share(owner, lid, self.uid, "see")
        self.index()
        hits = self.find("Spachtelmasse")
        self.assertEqual([h["ext"] for h in hits], [f"{owner}.{lid}"])
        self.assertIn("Baumarkt Wombat", hits[0]["titel"])
        # sharing off for the Spark or taken back: gone with the next round
        helpers.set_config(tasks_share=False)
        self.index()
        self.assertEqual(self.find("Spachtelmasse"), [])
        helpers.set_config(tasks_share=True)
        self.index()
        self.assertEqual(len(self.find("Spachtelmasse")), 1)
        with quiet():
            tasks.set_share(owner, lid, self.uid, "")
        self.index()
        self.assertEqual(self.find("Spachtelmasse"), [])


class Medien(Base):
    def test_pictures_and_songs_by_their_words(self):
        for name in ("image", "music"):   # the models installed (features.READY)
            old = section(name, enabled=True)
            self.addCleanup(lambda n=name, o=old: section(n, **dict(o, enabled=o.get("enabled", False))))
        bilder._save_index(self.uid, [{"id": "a" * 12, "t": NOW, "wish": "Leuchtturm im Sturm", "prompt": "lighthouse"},
                                      {"id": "b" * 12, "t": NOW - 5, "wish": "", "prompt": "", "art": "foto", "src": "foto"}])
        musik._save_index(self.uid, [{"id": "c" * 12, "t": NOW, "wish": "Lied über unsere Katze", "caption": "ruhig",
                                      "lyrics": "Mimi schläft am Ofen"}])
        got = self.index()
        self.assertEqual((got["bild"], got["musik"]), ((2, 0), (1, 0)))
        self.assertEqual([h["weg"] for h in self.find("Leuchtturm")], [{"art": "bild", "id": "a" * 12}])
        self.assertEqual([h["quelle"] for h in self.find("Ofen")], ["musik"])
        self.assertEqual([h["ext"] for h in self.find("", kategorie="Foto")], ["b" * 12])
        helpers.set_config(musik=False)
        self.assertEqual(self.index()["musik"], (0, 1))


class Weiche(unittest.TestCase):
    def test_finden_for_the_new_sources_calendar_stays(self):
        for text in ("Finde das Telegram-Gespräch von letzter Woche", "Such den Termin vom OP", "Such meine Baumarkt-Liste",
                     "Such mir die Rechnung von Thomann vom OP"):
            self.assertIn("finden", intent.classify(text).names, text)
        for text in ("Zeig mir meine Termine morgen", "Was habe ich morgen für Termine?", "Setz Milch auf die Einkaufsliste",
                     "Wann ist mein OP-Termin"):
            self.assertNotIn("finden", intent.classify(text).names, text)


class LogsAndLive(Base):
    def test_fixed_words_and_numbers_only(self):
        self.calendar(self.uid, Termine.OBJECTS)
        contacts._save(self.uid, cards=[{"id": "k1", "name": "Klara Kakadu", "org": "Quokka Versand"}])
        profiles.add_reminder(self.uid, "Reifenwechsel anmelden", NOW * 1000)
        self.index()
        log = self.log
        for word in ("Knie", "Nordstadt", "Kakadu", "Quokka", "Reifenwechsel", "Privat"):
            self.assertNotIn(word, log, word)
        for line in log.splitlines():
            if line.strip():
                self.assertRegex(line, r"^(fund|vorrang|hintergrund):", line)
        fund._live.update(at=0.0, d=None)
        d = fund.for_live()
        self.assertGreaterEqual(d["quellen"].get("termin", 0), 2)
        self.assertGreaterEqual(d["quellen"].get("kontakt", 0), 1)
        self.assertIsInstance(d["bezug"], int)
        text = json.dumps(d)
        for word in ("Knie", "Kakadu", "Reifenwechsel"):
            self.assertNotIn(word, text)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    """The page Finden with Stufe C in a real browser (strict CSP, 1280 and 390 px): „Thomann vom OP“ shows the line
    with the appointment's day, the reminder in its window; an appointment hit opens the calendar on its day."""
    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def setUp(self):
        helpers.keep_chat(self, "fund", "fund_termine", "fund_listen", "documents", "knowledge_book", "calendar", "reminders")
        helpers.set_config(fund=True, fund_termine=True, fund_listen=True, documents=False, knowledge_book=False,
                           calendar=True, reminders=True)

    def test_event_line_and_an_appointment_opens_the_calendar(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for w in (1280, 390):
                    br, pg, errors = await b.page(p, w, 900, csp=True)
                    try:
                        await b.until(pg, "window.FUND_ON===true")
                        uid = await pg.evaluate("PROFILE.id")
                        Base.clean(None, uid)
                        Base.calendar(self, uid, Termine.OBJECTS[:1])
                        profiles.add_reminder(uid, "Thomann Rechnung zahlen", day(2025, 4, 1) * 1000)
                        with quiet():
                            fund.runde(uid, NOW)
                        await pg.evaluate("goSec('finden')")
                        await b.until(pg, "!!document.querySelector('#fundview .fundq')&&!!FUND.stand")
                        await pg.fill("#fundview .fundq", "Thomann vom OP")
                        await pg.press("#fundview .fundq", "Enter")
                        await b.until(pg, "document.querySelectorAll('#fundview [data-fundsel]').length===1")
                        line = await pg.text_content("#fundview .funddeut")
                        self.assertIn("„OP“", line)
                        self.assertIn("2025", line)
                        await pg.fill("#fundview .fundq", "Nordstadt")
                        await pg.press("#fundview .fundq", "Enter")
                        await b.until(pg, "document.querySelectorAll('#fundview [data-fundsel]').length===1&&!document.querySelector('#fundview .funddeut')")
                        self.assertIn("OP Knie", await pg.text_content("#fundview .ld-list"))
                        await pg.click("#fundview [data-fundsel]")
                        await b.until(pg, "!!document.querySelector('#fundview .funddet:not([hidden]) [data-fundgo]')")
                        await pg.click("#fundview [data-fundgo]")
                        await b.until(pg, "typeof KAL!=='undefined'&&!!KAL.day&&KAL.day.getFullYear()===2025&&KAL.day.getMonth()===2")
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the page scrolls sideways")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
