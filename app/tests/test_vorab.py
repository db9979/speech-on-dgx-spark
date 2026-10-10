"""Vorab holen bei Rückfrage (vorab.py), V01.0.307.

When an answer asks back, the panel warms the caches of calendar, mail, weather and parcels by fixed rules
while the question is spoken. Only reading jobs, only tools the turn offered, the groups from the person's own
words (from the question back only when nothing outside was read), never guests, off without both switches.
A longer calendar period in the cache serves a shorter one. No test depends on the wall clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import contextlib
import datetime
import io
import unittest
import zoneinfo

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import chat  # noqa: E402
import intent  # noqa: E402
import logfilter  # noqa: E402
import profiles  # noqa: E402
import vorab  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class Turn:
    def __init__(self, uid, text="", offered=("calendar_events", "mail_list", "weather", "parcels"), **kw):
        self.who = {"id": uid, "name": "x"} if uid else None
        self.own_browser, self.private_ok, self.carry = True, True, None
        self.route = intent.classify(text)
        self.offered_all = set(offered)
        self.ccfg = None
        self.body = {"tz": "Europe/Berlin"}
        self.__dict__.update(kw)


class Fake:
    """Replaces the fetches of the four modules; records what was fetched."""

    def __init__(self):
        self.got = []

    def __enter__(self):
        import mail
        import parcels
        import weather
        self.saved = (calendars.events, mail.find, weather.get, weather.forecast, parcels.scan)

        async def events(uid, start, end, zone):
            self.got.append(("kalender", uid, (end - start).days))
            return [], []

        async def forecast(lat, lon, days=7):
            self.got.append(("wetter", lat))
            return {}
        calendars.events = events
        mail.find = lambda uid, q, days, unread, limit: self.got.append(("mail", uid, q, days, unread))
        weather.get = lambda uid: {"lat": 48.1, "lon": 11.6, "name": "Daheim"}
        weather.forecast = forecast
        parcels.scan = lambda uid: self.got.append(("paket", uid))
        return self

    def __exit__(self, *a):
        import mail
        import parcels
        import weather
        calendars.events, mail.find, weather.get, weather.forecast, parcels.scan = self.saved
        vorab._running.clear()
        vorab._ready.clear()


def run_after(turn, said, st=None, calls=()):
    async def go():
        todo = vorab.after(turn, said, st or {"mail": False, "outside": False}, list(calls))
        task = vorab._running.get(turn.who["id"]) if turn.who else None
        if task:
            await task
        return todo
    with contextlib.redirect_stdout(io.StringIO()) as out:
        todo = asyncio.run(go())
    return todo, out.getvalue()


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.uid = profile("VorabVera")
        _, cls.other = profile("VorabOtto")

    def setUp(self):
        helpers.set_config(routing=True, prefetch=True)
        profiles.save_settings(self.uid, {"route": True, "prefetch": True})

    def tearDown(self):
        helpers.set_config(prefetch=False)

    def test_asks_back(self):
        self.assertTrue(vorab.asks_back("Gern. Für welchen Tag?"))
        self.assertTrue(vorab.asks_back("Meinst du heute oder morgen?“"))
        self.assertFalse(vorab.asks_back("Morgen hast du zwei Termine."))
        self.assertFalse(vorab.asks_back("Was meinst du? Ich habe es so verstanden: morgen."))
        self.assertFalse(vorab.asks_back(""))

    def test_fetches_by_the_persons_words(self):
        with Fake() as f:
            todo, out = run_after(Turn(self.uid, "Habe ich einen Termin?"), "Für welchen Tag?")
        self.assertEqual(todo, ["kalender"])
        self.assertEqual(f.got, [("kalender", self.uid, 8)])
        self.assertIn("vorab: geholt Kalender", out)
        self.assertNotIn("Termin", out)     # the journal line never holds the question

    def test_mail_weather_parcels(self):
        with Fake() as f:
            run_after(Turn(self.uid, "Wie wird das Wetter?"), "Wo genau?")
            run_after(Turn(self.uid, "Hab ich neue Mails?"), "Von wem?")
            run_after(Turn(self.uid, "Wo ist mein Paket?"), "Welches meinst du?")
        self.assertIn(("wetter", 48.1), f.got)
        self.assertIn(("mail", self.uid, "", 7, False), f.got)
        self.assertIn(("paket", self.uid), f.got)

    def test_question_back_only_without_outside_text(self):
        turn = Turn(self.uid, "Was ist los?")      # no rule: unklar
        with Fake() as f:
            self.assertEqual(run_after(turn, "Meinst du deinen Kalender?")[0], ["kalender"])
            self.assertIsNone(run_after(turn, "Meinst du deinen Kalender?", {"mail": False, "outside": True})[0])
            self.assertIsNone(run_after(turn, "Meinst du deinen Kalender?", {"mail": True, "outside": False})[0])
            self.assertIsNone(run_after(Turn(self.uid, "Was ist los?", carry="outside"), "Meinst du deinen Kalender?")[0])
        self.assertEqual(len(f.got), 1)

    def test_no_question_no_fetch(self):
        with Fake() as f:
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?"), "Morgen um neun den Zahnarzt.")[0])
        self.assertEqual(f.got, [])

    def test_only_what_the_turn_offered(self):
        with Fake() as f:
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?", offered=("mail_list",)), "Wann?")[0])
            # the tool already ran in this answer: nothing to fetch ahead
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?"), "Wann?",
                                        calls=[{"name": "calendar_events"}])[0])
            self.assertIsNone(run_after(Turn(self.uid, "Hab ich neue Mails?"), "Soll ich vorlesen?",
                                        calls=[{"name": "mail_list (Panel)"}])[0])
        self.assertEqual(f.got, [])

    def test_only_reading_jobs(self):
        changing = chat.LOCKED_OUTSIDE | chat.LOCKED_MAIL
        for group, (tool, _) in vorab.JOBS.items():
            self.assertNotIn(tool, changing, group)
            self.assertIn(tool, intent.GROUPS[group][0], group)
        self.assertLessEqual(vorab.MAX_JOBS, 3)

    def test_switches_and_guests(self):
        with Fake() as f:
            helpers.set_config(prefetch=False)
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?"), "Wann?")[0])
            helpers.set_config(prefetch=True)
            self.assertIsNone(run_after(Turn(self.other, "Habe ich einen Termin?"), "Wann?")[0])   # profile switch off
            self.assertIsNone(run_after(Turn(None, "Habe ich einen Termin?"), "Wann?")[0])          # guest
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?", own_browser=False), "Wann?")[0])
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?", private_ok=False), "Wann?")[0])
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?", mcp={"tools": []}), "Wann?")[0])
            helpers.set_config(routing=False)      # builds on Gezielte Werkzeugwahl
            self.assertIsNone(run_after(Turn(self.uid, "Habe ich einen Termin?"), "Wann?")[0])
        self.assertEqual(f.got, [])

    def test_used_once_per_profile_and_only_while_fresh(self):
        vorab._ready[self.uid] = {"kalender": 1000.0, "wetter": 1000.0}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(vorab.used(self.other, "calendar_events", now=1010.0))
            self.assertTrue(vorab.used(self.uid, "calendar_events", now=1010.0))
            self.assertFalse(vorab.used(self.uid, "calendar_events", now=1011.0))   # counted once
            self.assertFalse(vorab.used(self.uid, "weather", now=1000.0 + vorab.KEEP_SECONDS + 1))
        self.assertIn("vorab: genutzt Kalender", out.getvalue())
        vorab._ready.clear()

    def test_one_at_a_time_and_never_breaks_the_answer(self):
        async def go():
            with Fake():
                async def slow(uid, start, end, zone):
                    await asyncio.sleep(0.05)
                calendars.events = slow
                first = vorab.after(Turn(self.uid, "Habe ich einen Termin?"), "Wann?", {}, [])
                second = vorab.after(Turn(self.uid, "Habe ich einen Termin?"), "Wann?", {}, [])
                await vorab._running[self.uid]
                return first, second
        with contextlib.redirect_stdout(io.StringIO()):
            first, second = asyncio.run(go())
            self.assertEqual(first, ["kalender"])
            self.assertIsNone(second)
            self.assertIsNone(vorab.after(object(), "Wann?", {}, []))   # a broken turn: nothing, no error

    def test_failed_fetch_is_logged_by_kind_only(self):
        with Fake():
            async def broken(uid, start, end, zone):
                raise ValueError("geheim.example.org antwortet nicht")
            calendars.events = broken
            todo, out = run_after(Turn(self.uid, "Habe ich einen Termin?"), "Wann?")
        self.assertIn("fehlgeschlagen Kalender (ValueError)", out)
        self.assertNotIn("geheim", out)
        self.assertEqual(vorab._ready.get(self.uid), None)

    def test_log_area(self):
        self.assertEqual(logfilter.parse("vorab: geholt Kalender | 0.2 s")["area"], "chat")


class CalendarCover(unittest.TestCase):
    def test_longer_period_serves_a_shorter_one(self):
        zone = zoneinfo.ZoneInfo("Europe/Berlin")
        start = datetime.datetime(2026, 10, 10, tzinfo=zone)
        cal = {"id": "c1", "name": "Privat"}
        calls = []
        saved = calendars._fetch

        async def fetch(d, a, b):
            calls.append((a, b))
            return ["BEGIN:VCALENDAR\nEND:VCALENDAR"], 1
        calendars._fetch = fetch
        calendars._cache.clear()
        try:
            asyncio.run(calendars._one("u1", cal, start, start + datetime.timedelta(days=8), zone))
            asyncio.run(calendars._one("u1", cal, start + datetime.timedelta(days=1), start + datetime.timedelta(days=2), zone))
            self.assertEqual(len(calls), 1)    # tomorrow came from the eight days fetched ahead
            asyncio.run(calendars._one("u2", cal, start + datetime.timedelta(days=1), start + datetime.timedelta(days=2), zone))
            asyncio.run(calendars._one("u1", cal, start + datetime.timedelta(days=7), start + datetime.timedelta(days=10), zone))
            self.assertEqual(len(calls), 3)    # another profile, and a period beyond the fetched one: fetched anew
        finally:
            calendars._fetch = saved
            calendars._cache.clear()


class EndToEnd(unittest.TestCase):
    def test_the_answer_hands_over_what_it_said(self):
        c, uid = profile("VorabEmil")
        helpers.set_config(routing=True, prefetch=True)
        profiles.save_settings(uid, {"route": True, "prefetch": True})
        seen = []
        saved = vorab.after
        vorab.after = lambda turn, said, st, calls, tr=None: seen.append((turn.who["id"], said, st["outside"]))
        try:
            r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "SAY | x | Für welchen Tag?"}]})
            self.assertEqual(r.status_code, 200, r.text)
            helpers.events(r)
        finally:
            vorab.after = saved
            helpers.set_config(prefetch=False)
        self.assertEqual(seen, [(uid, "Für welchen Tag?", False)])


class RouteModelBeside(unittest.TestCase):
    """chat.route_model "on": the pick starts early and is waited for only as long as allowed."""

    def test_pick_in_time(self):
        async def quick():
            return "wetter"

        async def never():
            await asyncio.Event().wait()

        async def go():
            t = asyncio.create_task(quick())
            first = await intent.pick_in_time(t, 1)
            slow = asyncio.create_task(never())
            second = await intent.pick_in_time(slow, 0)
            await asyncio.sleep(0)
            return first, second, slow.cancelled()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            first, second, stopped = asyncio.run(go())
        self.assertEqual((first, second, stopped), ("wetter", None, True))
        self.assertIn("nicht rechtzeitig", out.getvalue())

    def test_turn_still_uses_the_pick(self):
        c, uid = profile("VorabRita")
        helpers.set_config(routing=True, route_model="on")
        profiles.save_settings(uid, {"route": True})
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "ROUTE gedaechtnis quux"}]})
                self.assertEqual(r.status_code, 200, r.text)
                helpers.events(r)
        finally:
            helpers.set_config(route_model="off")
        self.assertIn("Modell-Zuordnung fertig", out.getvalue())
        self.assertIn("weiche: Absicht gedaechtnis", out.getvalue())


if __name__ == "__main__":
    unittest.main()
