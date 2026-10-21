"""Tagesaktuell (Dominik 2026-10-21: „sämtliche Informationen immer aktuell überprüfen … falls es Bedenken gibt, soll er
das mitteilen“): fixed rules of the panel hold every source against today (frisch.py).

- A stand always says its day („gestern 18:00“), never only the time.
- The web search: the person's words decide the period (SearXNG time_range, news category), every hit carries its date,
  older hits are dropped for such a question; without a current hit the result and the answer say so.
- Weather: „heute“ comes from the clock, never from the first day of a forecast read before midnight; „Jetzt“ only from
  a young reading.
- The rule „Stand nennen“ (Antwort-Prüfung) and the morning briefing as a push add one fixed sentence when a part was
  not current and the text did not say so.

Times are given as fixed moments or relative to time.time(); no result depends on the wall clock.
"""
import asyncio
import datetime
import inspect
import time
import unittest
import zoneinfo

from tests import helpers  # noqa: F401  (sets up paths and a throw-away state directory)
import chat  # noqa: E402
import chat_modell  # noqa: E402
import frisch  # noqa: E402
import vorrat  # noqa: E402
import weather  # noqa: E402
import mail  # noqa: E402
from tests.test_mailvorrat import A1, UID, Base, head  # noqa: E402  (fake mailboxes, no IMAP)

ZONE = zoneinfo.ZoneInfo("Europe/Berlin")
NOON = datetime.datetime(2026, 10, 21, 12, 0, tzinfo=ZONE).timestamp()   # a Wednesday


def at(day, hh, mm=0):
    return datetime.datetime(2026, 10, day, hh, mm, tzinfo=ZONE).timestamp()


class Stand(unittest.TestCase):
    def test_always_with_its_day(self):
        self.assertEqual(frisch.stand(at(21, 6, 40), NOON, ZONE), "heute 06:40")
        self.assertEqual(frisch.stand(at(20, 18), NOON, ZONE), "gestern 18:00")
        self.assertEqual(frisch.stand(at(18, 18), NOON, ZONE), "Sonntag 18.10., 18:00")
        self.assertEqual(frisch.stand(at(1, 9), NOON, ZONE), "01.10.2026, 09:00")
        self.assertTrue(frisch.is_today(at(21, 0, 1), NOON, ZONE))
        self.assertFalse(frisch.is_today(at(20, 23, 59), NOON, ZONE))

    def test_vorrat_stand_names_the_day(self):
        st = vorrat.begin("", "Europe/Berlin")
        when = time.time() - 3 * 86400
        st["when"]["calendar"] = when
        vorrat.use(st)
        try:
            text = vorrat.stand("calendar")
        finally:
            vorrat._turn.set(None)
        self.assertIn(frisch.stand(when, zone=ZONE), text)
        self.assertNotIn("heute", text)


class Period(unittest.TestCase):
    def test_own_words_decide(self):
        self.assertEqual(frisch.zeitraum("Was gibt es heute Neues zu Bayern?"), "day")
        self.assertEqual(frisch.zeitraum("Die neuesten Nachrichten bitte"), "day")
        self.assertEqual(frisch.zeitraum("Was war gestern in Berlin los?"), "week")
        self.assertEqual(frisch.zeitraum("Wie hoch ist der Eiffelturm?"), "")
        self.assertTrue(frisch.news("Nachrichten aus Ulm"))
        self.assertFalse(frisch.news("Wie hoch ist der Eiffelturm?"))

    def test_the_panel_time_note_is_not_the_persons_word(self):
        # the time line the model gets („Aktuelles Datum …“) must never make every search a search of today
        self.assertIn("aktuell", chat.now_line("Europe/Berlin").lower())
        src = inspect.getsource(__import__("chat_tools"))
        self.assertIn('frisch.zeitraum(own, query)', src)
        self.assertIn('own = getattr(t, "ask_text", "")', src)


class _Resp:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


class _Client:
    def __init__(self, results, empty_with_period=False):
        self.results, self.empty, self.params = results, empty_with_period, []

    async def get(self, url, params=None, **kw):
        self.params.append(dict(params or {}))
        if self.empty and "time_range" in (params or {}):
            return _Resp({"results": []})
        return _Resp({"results": [dict(x) for x in self.results]})


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


class Search(unittest.TestCase):
    def setUp(self):
        chat._search_cache.clear()
        self.st = vorrat.begin("", "Europe/Berlin")
        vorrat.use(self.st)

    def tearDown(self):
        vorrat._turn.set(None)

    def search(self, c, query, period="", news=False, topic=False):
        return asyncio.run(chat.web_search(c, {"search_url": "http://searx", "search_pages": 0}, query, period, news, topic))

    def test_period_dates_and_old_hits_dropped(self):
        new, old = time.time() - 3600, time.time() - 5 * 86400
        c = _Client([{"title": "Neu", "url": "https://a.example/1", "content": "x", "publishedDate": iso(new)},
                     {"title": "Alt", "url": "https://a.example/2", "content": "y", "publishedDate": iso(old)},
                     {"title": "Ohne", "url": "https://a.example/3", "content": "z"}])
        text, sources = self.search(c, "Bayern", "day", True)
        self.assertEqual(c.params[0].get("time_range"), "day")
        self.assertIn("news", c.params[0].get("categories", ""))
        self.assertIn("Datum: " + frisch.stand(new), text)
        self.assertIn("Datum: unbekannt", text)
        self.assertNotIn("Alt", text)
        self.assertEqual([s["title"] for s in sources], ["Neu", "Ohne"])
        self.assertNotIn("frisch", self.st)     # a current hit: nothing to add

    def test_nothing_current_is_said(self):
        old = time.time() - 5 * 86400
        c = _Client([{"title": "Alt", "url": "https://a.example/2", "content": "y", "publishedDate": iso(old)}],
                    empty_with_period=True)
        text, _ = self.search(c, "Bayern", "day")
        self.assertEqual(len(c.params), 2)                    # once more without the period, the dates decide
        self.assertNotIn("time_range", c.params[1])
        self.assertIn("Kein Treffer von heute", text)
        self.assertIn(frisch.stand(old), text)
        note = frisch.nachsatz(self.st, "Bayern hat gewonnen.")
        self.assertIn("Aktuelles von heute habe ich im Netz nicht gefunden", note)
        self.assertEqual(frisch.nachsatz(self.st, "Von heute habe ich nichts, nichts aktuelles dazu."), "")

    def test_a_quiet_briefing_topic_adds_no_sentence(self):
        c = _Client([], empty_with_period=True)
        text, _ = self.search(c, "Bayern", "day", True, topic=True)
        self.assertIn("Kein Treffer", text)
        self.assertNotIn("frisch", self.st)

    def test_without_period_as_before(self):
        c = _Client([{"title": "Turm", "url": "https://a.example/t", "content": "330 m"}])
        text, _ = self.search(c, "Eiffelturm Höhe")
        self.assertNotIn("time_range", c.params[0])
        self.assertIn("Turm", text)


def forecast(days, current):
    n = len(days)
    return {"utc_offset_seconds": 7200, "current": {"time": current, "temperature_2m": 3.0, "weather_code": 0},
            "daily": {"time": days, "weather_code": [61] + [0] * (n - 1), "temperature_2m_max": [9.0] + [15.0] * (n - 1),
                      "temperature_2m_min": [1.0] + [5.0] * (n - 1), "precipitation_probability_max": [90] + [0] * (n - 1),
                      "precipitation_sum": [5.0] + [0.0] * (n - 1), "wind_gusts_10m_max": [70] + [10] * (n - 1)},
            "hourly": {"time": [], "precipitation_probability": [], "temperature_2m": []}}


class Weather(unittest.TestCase):
    MORNING = at(21, 7)

    def report(self, d):
        async def fake(*a, **kw):
            return d
        real = weather.forecast
        weather.forecast = fake
        try:
            return asyncio.run(weather.report(48.4, 10.0, "Ulm", None, 1, None, now=self.MORNING))
        finally:
            weather.forecast = real

    def test_today_from_the_clock_not_from_a_forecast_of_yesterday(self):
        # read at 23:00 yesterday: its first day is yesterday, its „current“ is of last night
        out = self.report(forecast(["2026-10-%02d" % d for d in range(20, 27)], "2026-10-20T23:00"))
        self.assertIn("Heute in Ulm: klar, 5 bis 15 Grad", out)       # the second day of that forecast
        self.assertNotIn("Regen", out)
        self.assertNotIn("Jetzt", out)

    def test_a_forecast_without_today_says_so(self):
        out = self.report(forecast(["2026-10-19", "2026-10-20"], "2026-10-20T23:00"))
        self.assertEqual(out, "Für Ulm habe ich gerade keine Vorhersage für heute.")

    def test_now_from_a_young_reading(self):
        out = self.report(forecast(["2026-10-%02d" % d for d in range(21, 28)], "2026-10-21T06:45"))
        self.assertIn("Jetzt in Ulm: 3 Grad", out)

    def test_tomorrow_by_the_clock(self):
        d = forecast(["2026-10-%02d" % d for d in range(20, 27)], "2026-10-20T23:00")
        d["daily"]["precipitation_probability_max"] = [0, 0, 95, 0, 0, 0, 0]   # the 22nd is tomorrow on the 21st
        real_f, real_g, real_u = weather.forecast, weather.get, weather.usable

        async def fake(*a, **kw):
            return d
        weather.forecast, weather.get = fake, lambda uid: {"lat": 48.4, "lon": 10.0, "name": "Ulm"}
        try:
            text, why = asyncio.run(weather.notable_tomorrow("x", now=self.MORNING))
        finally:
            weather.forecast, weather.get, weather.usable = real_f, real_g, real_u
        self.assertEqual(why, ["rain"])
        self.assertTrue(text.startswith("Morgen in Ulm"))


class Hint(unittest.TestCase):
    def test_older_reading_not_said_gets_the_fixed_sentence(self):
        st = {"when": {"weather": at(20, 23, 10)}}
        note = frisch.nachsatz(st, "Heute wird es sonnig.", now=NOON, zone=ZONE)
        self.assertEqual(note, "Nicht ganz aktuell: Wetter: Stand gestern 23:10 Uhr.")
        self.assertEqual(frisch.nachsatz(st, "Stand gestern 23:10 Uhr: sonnig.", now=NOON, zone=ZONE), "")
        # the time alone is not enough for a reading of yesterday: it would sound like this morning's
        self.assertTrue(frisch.nachsatz(st, "Stand 23:10 Uhr: sonnig.", now=NOON, zone=ZONE))
        self.assertTrue(frisch.nachsatz(st, "x", en=True, now=NOON, zone=ZONE).startswith("Not quite current: weather: as of"))
        self.assertEqual(frisch.nachsatz({"when": {}}, "x"), "")
        self.assertEqual(frisch.nachsatz(None, "x"), "")

    def test_wired_into_the_answer_check_and_the_briefing_push(self):
        src = inspect.getsource(chat_modell)
        self.assertIn("frisch.nachsatz(", src)
        self.assertIn("if check_on else", src)   # under the switch Antwort-Prüfung
        self.assertNotIn("await morning_briefing(", inspect.getsource(chat.due_briefings))

    def test_briefing_push_says_an_older_reading(self):
        when = time.time() - 30 * 3600

        async def fake(uid, tz="", markdown=False):
            vorrat.note("weather", "alt", when)
            return "Guten Morgen."
        real = chat.morning_briefing
        chat.morning_briefing = fake
        try:
            text = asyncio.run(chat.briefing_checked("x", "Europe/Berlin"))
        finally:
            chat.morning_briefing = real
        self.assertTrue(text.startswith("Guten Morgen.\n\nNicht ganz aktuell: Wetter: Stand "), text)
        self.assertIn(frisch.stand(when, zone=ZONE), text)

        async def fresh(uid, tz="", markdown=False):
            return "Guten Morgen."
        chat.morning_briefing = fresh
        try:
            self.assertEqual(asyncio.run(chat.briefing_checked("x", "Europe/Berlin")), "Guten Morgen.")
        finally:
            chat.morning_briefing = real


class Mail(Base):
    """Mails: the briefing names each with its day, an older listing says its day and notes it for the answer, the
    Mail-Vorrat is no answer when it is days old."""
    def test_briefing_names_the_day(self):
        got = mail.briefing(UID)
        self.assertIn(f"{frisch.stand(head(1)['date'].timestamp())} from Anna: Rechnung 1", got)
        self.assertNotIn("Rechnung 2", got)            # read already: not in the briefing

    def test_older_listing_says_its_day_and_is_noted(self):
        st = vorrat.begin("", "Europe/Berlin")
        vorrat.use(st)
        try:
            when = time.time() - 26 * 3600
            text = mail._as_of(when)
        finally:
            vorrat._turn.set(None)
        self.assertIn(f"Listing as of {frisch.stand(when)};", text)
        self.assertEqual(st["when"].get("mail"), when)
        self.assertIn("E-Mails: Stand", frisch.nachsatz(st, "Du hast zwei Mails."))

    def test_a_supply_of_days_ago_is_no_answer(self):
        # mail._find goes back in Base.tearDown; a cleanup runs after it and would put this test's fake back for
        # every later test (test_tidy, test_telegram_tasks found no mail, Angriffs-Selbsttest 2026-10-21)
        saved = (mail.ASK_WAIT, mail._supply)
        self.addCleanup(lambda: (setattr(mail, "ASK_WAIT", saved[0]), setattr(mail, "_supply", saved[1])))
        mail.ASK_WAIT = 0.1
        mail._supply = lambda *a: (([(A1["id"], 9, head(9))], [], False), time.time() - 2 * 86400)
        fast = mail._find

        def slow(*a):
            time.sleep(0.4)
            return fast(*a)
        mail._find = slow
        out = mail.listing(UID, "", 7, False, 8)
        self.assertNotIn("Rechnung 9", out)            # waited for the mailbox instead
        self.assertIn("Rechnung 1", out)
        self.assertNotIn("as of", out)


class Live(unittest.TestCase):
    def test_numbers_only(self):
        c = frisch.for_live()
        self.assertEqual(set(c), {"searches", "old", "dropped", "hints"})
        self.assertTrue(all(isinstance(v, int) for v in c.values()))


if __name__ == "__main__":
    unittest.main()
