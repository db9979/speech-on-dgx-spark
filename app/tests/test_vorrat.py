"""Vorrat je Profil, stage A (plan vorrat-je-profil, Dominik 2026-10-20 „alle Punkte umsetzen“):

- Each service has a fresh and a highest age (vorrat.DIENSTE): inside an answer of the assistant a reading younger than
  fresh is taken as it is (warm), an older one up to the highest age only when the server does not answer within
  vorrat.WAIT (alt, the tool says „As of hh:mm“), else the answer waits (kalt).
- „Schau nochmal nach“, „aktualisiere“ (the person's own words) always ask the server.
- Pages and background work keep their own rules and are not counted.
- Per answer each service is noted once (the worse wins); latency keeps it as fixed words, Prüfen shows it per service.
- Calendar (calendars._one), weather (weather.forecast) and parcels (parcels.scan) follow it.
- Stage B: one round (vorrat.round_) keeps calendars, weather, parcels and „Für dich“ of active profiles fresh, only
  what got older than its fresh age; a mail newer than the last „Für dich“ reading reads it anew; the daily briefing is
  written ahead BRIEF_AHEAD before its time and sent as it is on the minute.

Fixed ages are passed as times; fetches are fakes, no network and no wall clock decides a result.
"""
import asyncio
import datetime
import os
import shutil
import threading
import time
import unittest
import zoneinfo

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import calendars  # noqa: E402
import frisch  # noqa: E402
import latency  # noqa: E402
import parcels  # noqa: E402
import vault  # noqa: E402
import vorrat  # noqa: E402
import weather  # noqa: E402

ZONE = zoneinfo.ZoneInfo("Europe/Berlin")
DAY = datetime.datetime(2026, 3, 9, tzinfo=ZONE)
EVENT = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:vorrat-1\r\n"
         "DTSTART;TZID=Europe/Berlin:20260310T103000\r\nDTEND;TZID=Europe/Berlin:20260310T120000\r\n"
         "SUMMARY:Zahnarzt\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
NEW = EVENT.replace("Zahnarzt", "Friseur").replace("vorrat-1", "vorrat-2")


def in_turn(question="Was steht heute an?"):
    """A fresh answer context, as chat._chat and run_tool make it."""
    st = vorrat.begin(question, "Europe/Berlin")
    vorrat.use(st)
    return st


class Ages(unittest.TestCase):
    def setUp(self):
        self.tok = vorrat._turn.set(None)

    def tearDown(self):
        vorrat._turn.reset(self.tok)

    def test_fresh_old_and_cold(self):
        fresh, most = vorrat.DIENSTE["mail"]
        now = 1_000_000.0
        self.assertEqual(vorrat.state("mail", now - fresh + 1, now), "warm")
        self.assertEqual(vorrat.state("mail", now - fresh - 1, now), "alt")
        self.assertEqual(vorrat.state("mail", now - most - 1, now), "kalt")
        self.assertEqual(vorrat.state("mail", None, now), "kalt")

    def test_look_again_always_asks_the_server(self):
        for q in ("Schau nochmal nach, ob neue Mails da sind", "Aktualisiere das Wetter", "check again please",
                  "Kannst du den Kalender neu laden?"):
            in_turn(q)
            self.assertEqual(vorrat.state("mail", 999_999.0, 1_000_000.0), "kalt", q)
        for q in ("Habe ich neue Mails?", "Wie wird das Wetter morgen?"):
            in_turn(q)
            self.assertEqual(vorrat.state("mail", 999_999.0, 1_000_000.0), "warm", q)

    def test_every_service_has_two_ages(self):
        for d, (fresh, most) in vorrat.DIENSTE.items():
            self.assertLess(0, fresh, d)
            self.assertLess(fresh, most, d)


class Take(unittest.TestCase):
    def setUp(self):
        self.tok = vorrat._turn.set(None)
        self.wait = vorrat.WAIT
        vorrat.WAIT = 0.05

    def tearDown(self):
        vorrat.WAIT = self.wait
        vorrat._turn.reset(self.tok)

    def run_take(self, hit, delay, fail=False):
        calls = []

        async def fetch():
            calls.append(1)
            await asyncio.sleep(delay)
            if fail:
                raise OSError("down")
            return "neu"

        async def go():
            st = in_turn()
            v = await vorrat.take("weather", hit, ("weather", "t", delay, fail), fetch)
            await asyncio.sleep(delay + 0.05)   # a fetch behind finishes
            return v, st
        v, st = asyncio.run(go())
        return v, st, calls

    def test_warm_never_fetches(self):
        v, st, calls = self.run_take((time.time() - 5, "alt"), 0.0)
        self.assertEqual((v, calls, st["seen"]), ("alt", [], {"weather": "warm"}))
        self.assertEqual(vorrat.stand("weather"), "")

    def test_old_reading_when_the_server_is_slow_with_its_time(self):
        when = time.time() - vorrat.DIENSTE["weather"][0] - 60
        v, st, calls = self.run_take((when, "alt"), 0.3)
        self.assertEqual(v, "alt")
        self.assertEqual(st["seen"], {"weather": "alt"})
        self.assertEqual(len(calls), 1)   # asked anew behind it
        vorrat.use(st)
        at = datetime.datetime.fromtimestamp(when, ZONE)
        self.assertIn(f"As of {frisch.stand(when, zone=ZONE)}: ", vorrat.stand("weather"))   # with its day (Tagesaktuell)
        self.assertIn(f"{at:%H:%M}", vorrat.stand("weather"))

    def test_old_reading_when_the_server_fails(self):
        when = time.time() - vorrat.DIENSTE["weather"][0] - 60
        v, st, _ = self.run_take((when, "alt"), 0.0, fail=True)
        self.assertEqual((v, st["seen"]), ("alt", {"weather": "alt"}))

    def test_new_reading_when_the_server_answers_in_time(self):
        v, st, _ = self.run_take((time.time() - vorrat.DIENSTE["weather"][0] - 60, "alt"), 0.0)
        self.assertEqual((v, st["seen"]), ("neu", {"weather": "kalt"}))
        self.assertEqual(vorrat.stand("weather"), "")

    def test_nothing_stored_waits(self):
        v, st, _ = self.run_take(None, 0.1)
        self.assertEqual((v, st["seen"]), ("neu", {"weather": "kalt"}))

    def test_sync_variant(self):
        gate = threading.Event()

        def slow():
            gate.wait(2)
            return "neu"
        st = in_turn()
        when = time.time() - vorrat.DIENSTE["parcels"][0] - 60
        self.assertEqual(vorrat.take_sync("parcels", (when, "alt"), ("parcels", "sync-test"), slow), "alt")
        self.assertEqual(st["seen"], {"parcels": "alt"})
        gate.set()
        self.assertEqual(vorrat.take_sync("parcels", None, ("parcels", "sync-test-2"), lambda: "neu"), "neu")

    def test_pages_are_not_counted(self):
        vorrat._turn.set(None)
        before = vorrat.for_live()
        vorrat.note("mail", "warm")
        self.assertEqual(vorrat.for_live(), before)


class Notes(unittest.TestCase):
    def setUp(self):
        self.tok = vorrat._turn.set(None)

    def tearDown(self):
        vorrat._turn.reset(self.tok)

    def test_once_per_service_and_the_worse_wins(self):
        day = time.strftime("%Y-%m-%d")
        vorrat._today.update(day=day, counts={})
        st = in_turn()
        vorrat.note("calendar", "warm")
        vorrat.note("calendar", "kalt")
        vorrat.note("calendar", "alt", 100.0)
        vorrat.note("calendar", "warm")
        vorrat.note("calendar", "alt", 50.0)
        self.assertEqual(st["seen"], {"calendar": "alt"})
        self.assertEqual(st["when"], {"calendar": 50.0})
        live = vorrat.for_live()["calendar"]
        self.assertEqual((live["n"], live["alt"], live["warm"], live["kalt"]), (1, 1, 0, 0))
        self.assertEqual(vorrat.seen(st), "calendar:alt")
        self.assertIn("1 Fragen, 100 % aus dem Vorrat", vorrat.live_sub("calendar"))


class Measure(unittest.TestCase):
    def test_only_fixed_words_are_kept(self):
        ok, bad = latency.MEASURE["s"], latency.MEASURE["s"]
        self.assertTrue(ok("calendar:alt+mail:warm"))
        self.assertFalse(bad("mail:Termin beim Zahnarzt"))
        self.assertFalse(bad("mail:warm+x"))
        self.assertTrue(latency.MEASURE["w"](1.5))
        self.assertFalse(latency.MEASURE["w"]("1.5"))

    def test_per_service(self):
        now = 2_000_000
        items = [{"t": now - 10, "a": 3.0, "s": "mail:warm", "w": 0.1},
                 {"t": now - 20, "a": 5.0, "s": "mail:kalt+weather:alt", "w": 2.5},
                 {"t": now - 30, "a": 4.0, "s": "mail:alt", "w": 2.0},
                 {"t": now - 9 * 86400, "a": 9.0, "s": "mail:kalt", "w": 9.0}]   # older than the 7 days
        rows = {r["service"]: r for r in latency.by_service(items, now)}
        self.assertEqual((rows["mail"]["n"], rows["mail"]["warm"], rows["mail"]["alt"], rows["mail"]["kalt"]), (3, 1, 1, 1))
        self.assertEqual(rows["mail"]["share"], 67)
        self.assertEqual(rows["mail"]["wait"], 2.0)
        self.assertEqual(rows["weather"]["share"], 100)


class Calendar(unittest.TestCase):
    """calendars._one inside an answer follows vorrat; outside it (page, check) nothing changes."""

    def setUp(self):
        self.tok = vorrat._turn.set(None)
        self.saved = (calendars._fetch, vorrat.WAIT)
        calendars._cache.clear()
        calendars._inflight.clear()
        self.cal = {"id": "t1", "name": "Privat", "url": "http://x/", "user": "k"}
        self.key = ("u1", "t1", "2026-03-01")
        self.calls = []
        vorrat.WAIT = 0.05

    def tearDown(self):
        calendars._fetch, vorrat.WAIT = self.saved
        calendars._cache.clear()
        calendars._inflight.clear()
        vorrat._turn.reset(self.tok)

    def fake(self, delay):
        async def fetch(d, a, b):
            self.calls.append(a.date().isoformat())
            await asyncio.sleep(delay)
            return [NEW], 1
        calendars._fetch = fetch

    def ask(self, question="Was steht morgen an?", settle=0.0):
        async def go():
            st = in_turn(question)
            evs = await calendars._one("u1", self.cal, DAY, DAY + datetime.timedelta(days=2), ZONE)
            await asyncio.sleep(settle)
            return evs, st
        evs, st = asyncio.run(go())
        return [x["title"] for x in evs], st

    def test_fresh_enough_block_without_asking(self):
        self.fake(0.0)
        calendars._cache[self.key] = (time.time() - calendars.CACHE_SECONDS - 30, [EVENT])   # older than the page's 2 min
        titles, st = self.ask()
        self.assertEqual((titles, self.calls, st["seen"]), (["Zahnarzt"], [], {"calendar": "warm"}))

    def test_older_block_when_the_server_is_slow(self):
        self.fake(0.3)
        calendars._cache[self.key] = (time.time() - vorrat.DIENSTE["calendar"][0] - 60, [EVENT])
        titles, st = self.ask(settle=0.4)
        self.assertEqual(titles, ["Zahnarzt"])
        self.assertEqual(st["seen"], {"calendar": "alt"})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(calendars._cache[self.key][1], [NEW])   # fetched anew behind it

    def test_look_again_waits_for_the_server(self):
        self.fake(0.1)
        calendars._cache[self.key] = (time.time() - 30, [EVENT])
        titles, st = self.ask("Schau nochmal in meinen Kalender")
        self.assertEqual((titles, st["seen"]), (["Friseur"], {"calendar": "kalt"}))


class WeatherAndParcels(unittest.TestCase):
    def setUp(self):
        self.tok = vorrat._turn.set(None)

    def tearDown(self):
        vorrat._turn.reset(self.tok)
        weather._cache.clear()
        parcels._cache.clear()

    def test_weather_from_the_store(self):
        key = (50.0, 8.0)
        weather._cache[key] = (time.time() - 60, {"daily": {"time": []}})

        async def go():
            in_turn()
            return await weather.forecast(50.0, 8.0, 7)
        self.assertEqual(asyncio.run(go()), {"daily": {"time": []}})   # no network needed

    def test_parcels_from_the_store(self):
        import mail
        saved = mail.get
        mail.get = lambda uid: {"accounts": [{"id": "m1"}]}
        self.addCleanup(setattr, mail, "get", saved)
        parcels._cache["u1"] = (time.time() - 60, ([], []))
        st = in_turn()
        self.assertEqual(parcels.scan("u1"), ([], []))
        self.assertEqual(st["seen"], {"parcels": "warm"})


@unittest.skipUnless(vault.available(), "needs cryptography for the sealed file")
class Supply(unittest.TestCase):
    """3b: weather (own place only) and parcels keep their last reading sealed in the profile's folder; after a
    restart the first question is answered from it, with „Stand“ when older; it goes with the place, the last mailbox
    and after idle_days."""
    UID = "u_00000000c3d4"

    def setUp(self):
        import mail
        import profiles
        self.saved = (mail.get, parcels._scan_account, weather.urls)
        os.makedirs(profiles._path(self.UID), exist_ok=True)
        self.addCleanup(shutil.rmtree, profiles._path(self.UID), True)
        self.accts = [{"id": "m1", "name": "Privat"}]
        mail.get = lambda uid: {"accounts": list(self.accts)}
        self.item = {"carrier": "DHL", "shop": "Geheimladen", "item": "Teekanne", "track": "JJD0001", "status": "transit",
                     "day": "", "sent": "2026-10-19", "at": 1000.0}
        parcels._scan_account = lambda a, days: [dict(self.item)]
        self.tok = vorrat._turn.set(None)
        self.clear()

    def tearDown(self):
        import mail
        mail.get, parcels._scan_account, weather.urls = self.saved
        vorrat._turn.reset(self.tok)
        self.clear()

    def clear(self):
        for v in (weather.SUPPLY, parcels.SUPPLY):
            v.clear()
        weather._cache.clear()
        parcels._cache.clear()

    def raw(self, v):
        with open(v.file(self.UID), encoding="utf-8") as f:
            return f.read()

    def test_parcels_sealed_and_back_after_a_restart(self):
        self.assertEqual(parcels.scan(self.UID)[0][0]["shop"], "Geheimladen")
        parcels.SUPPLY.flush()
        text = self.raw(parcels.SUPPLY)
        self.assertNotIn("Geheimladen", text)
        self.assertNotIn("JJD0001", text)
        self.clear()   # a restart: memory empty
        parcels._scan_account = lambda a, days: (_ for _ in ()).throw(OSError("timed out"))
        st = in_turn()
        found, errors = parcels.scan(self.UID)
        self.assertEqual((found[0]["shop"], errors, st["seen"]), ("Geheimladen", [], {"parcels": "warm"}))

    def test_parcels_go_with_the_last_mailbox(self):
        parcels.scan(self.UID)
        parcels.SUPPLY.flush()
        self.assertTrue(os.path.exists(parcels.SUPPLY.file(self.UID)))
        self.accts = []
        self.assertEqual(parcels.scan(self.UID), ([], []))
        self.assertFalse(os.path.exists(parcels.SUPPLY.file(self.UID)))

    def test_a_failed_mailbox_is_not_kept(self):
        parcels._scan_account = lambda a, days: (_ for _ in ()).throw(OSError("timed out"))
        parcels.scan(self.UID)
        parcels.SUPPLY.flush()
        self.assertFalse(os.path.exists(parcels.SUPPLY.file(self.UID)))

    def fake_weather(self, data):
        import httpx

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return data

        class C:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None):
                return R()
        saved = httpx.AsyncClient
        httpx.AsyncClient = C
        self.addCleanup(setattr, httpx, "AsyncClient", saved)
        weather.urls = lambda: ("http://x", "http://y")

    def test_weather_of_the_own_place_only(self):
        self.fake_weather({"daily": {"time": ["2026-10-20"]}, "ort": "Heimatort"})
        asyncio.run(weather.forecast(50.0, 8.0, 7))   # a place asked for once: memory only
        weather.SUPPLY.flush()
        self.assertFalse(os.path.exists(weather.SUPPLY.file(self.UID)))
        asyncio.run(weather.forecast(50.1, 8.1, 7, self.UID))
        weather.SUPPLY.flush()
        self.assertNotIn("Heimatort", self.raw(weather.SUPPLY))
        self.clear()
        weather.urls = lambda: (_ for _ in ()).throw(AssertionError("asked the service"))
        got = asyncio.run(weather.forecast(50.1, 8.1, 7, self.UID))
        self.assertEqual(got["ort"], "Heimatort")
        self.clear()   # another place than the kept one: not taken
        with self.assertRaises(AssertionError):
            asyncio.run(weather.forecast(50.2, 8.2, 7, self.UID))

    def test_weather_goes_with_the_place(self):
        self.fake_weather({"daily": {"time": []}})
        asyncio.run(weather.forecast(50.1, 8.1, 7, self.UID))
        weather.SUPPLY.flush()
        weather.forget(self.UID)
        self.assertFalse(os.path.exists(weather.SUPPLY.file(self.UID)))

    def test_the_round_writes_and_sweeps(self):
        parcels.scan(self.UID)
        now = time.time()
        vorrat._round.pop("swept", None)
        vorrat._disk(now)
        self.assertTrue(os.path.exists(parcels.SUPPLY.file(self.UID)))
        vorrat._disk(now + 15 * 86400)   # the day after: nobody read it for idle_days
        self.assertFalse(os.path.exists(parcels.SUPPLY.file(self.UID)))


class Round(unittest.TestCase):
    """vorrat.round_: only active profiles, only what is older than its fresh age, nothing for a blocked service."""

    def setUp(self):
        import fuerdich
        import mail
        import vorwaermen
        self.saved = (weather.usable, weather.get, weather.forecast, parcels.usable, parcels.scan, fuerdich.usable,
                      fuerdich._reading, calendars.keep_fresh, dict(vorwaermen._last), dict(mail._cache), fuerdich._last)
        self.calls = []
        vorwaermen._last.clear()
        vorwaermen._last["u1"] = time.time() - 60
        weather.usable = lambda uid: True
        weather.get = lambda uid: {"lat": 50.0, "lon": 8.0, "name": "Ort"}

        async def fc(lat, lon, days=7, uid=None):
            self.calls.append("weather")
            return {}
        weather.forecast = fc
        parcels.usable = lambda uid: True
        parcels.scan = lambda uid, days=14: self.calls.append("parcels") or ([], [])
        fuerdich.usable = lambda uid: True

        def reading(uid, fresh=False):
            self.calls.append("fuerdich")
            f = asyncio.get_running_loop().create_future()
            f.set_result(([], []))
            return f
        fuerdich._reading = reading
        self.fd = {}
        fuerdich._last = lambda uid: self.fd.get(uid)

        async def kf(now=None):
            self.calls.append("calendar")
            return 0, 0
        calendars.keep_fresh = kf
        import profiles
        self.by_id = profiles.by_id
        profiles.by_id = lambda uid: {"id": uid, "name": "T"} if uid == "u1" else None

    def tearDown(self):
        import fuerdich
        import mail
        import profiles
        import vorwaermen
        (weather.usable, weather.get, weather.forecast, parcels.usable, parcels.scan, fuerdich.usable,
         fuerdich._reading, calendars.keep_fresh, last, mc, fc) = self.saved
        vorwaermen._last.clear()
        vorwaermen._last.update(last)
        mail._cache.clear()
        mail._cache.update(mc)
        fuerdich._last = fc
        profiles.by_id = self.by_id
        weather._cache.clear()
        parcels._cache.clear()
        vorrat._round["calendar"] = 0.0

    def test_refreshes_what_is_old_and_leaves_what_is_fresh(self):
        import fuerdich
        import mail
        now = time.time()
        weather._cache[(50.0, 8.0)] = (now - vorrat.DIENSTE["weather"][0] - 5, {})   # older than fresh
        parcels._cache["u1"] = (now - 30, ([], []))                                   # fresh
        self.fd["u1"] = (now - 600, ([], []))
        newer = datetime.datetime.fromtimestamp(now - 60, datetime.timezone.utc)      # a mail after the last reading
        mail._cache[("u1", "", 14, False, 50)] = (now - 30, ([("a", 1, {"date": newer})], [], False))
        vorrat._round["calendar"] = 0.0
        n = asyncio.run(vorrat.round_(now))
        self.assertEqual(sorted(self.calls), ["calendar", "fuerdich", "weather"])
        self.assertEqual(n, 2)
        # a second round right after: the calendars wait for their own age, the rest is fresh or read already
        self.calls.clear()
        weather._cache[(50.0, 8.0)] = (now, {})
        self.fd["u1"] = (now, ([], []))
        self.assertEqual(asyncio.run(vorrat.round_(now + 1)), 0)
        self.assertEqual(self.calls, [])

    def test_inactive_and_unknown_profiles_are_left_alone(self):
        import vorwaermen
        vorwaermen._last.clear()
        vorwaermen._last["u1"] = time.time() - vorrat.ACTIVE_SECONDS - 60
        vorwaermen._last["gone"] = time.time()
        vorrat._round["calendar"] = time.time()
        self.assertEqual(asyncio.run(vorrat.round_()), 0)
        self.assertEqual(self.calls, [])

    def test_a_blocked_service_is_never_read(self):
        weather.usable = lambda uid: False
        parcels.usable = lambda uid: False
        import fuerdich
        fuerdich.usable = lambda uid: False
        vorrat._round["calendar"] = time.time()
        self.assertEqual(asyncio.run(vorrat.round_()), 0)
        self.assertEqual(self.calls, [])


class BriefingAhead(unittest.TestCase):
    def test_written_ahead_and_sent_on_the_minute(self):
        import chat
        import push
        from fastapi.testclient import TestClient
        name = "Vorrat-Briefing"
        admin = TestClient(panel.app)
        admin.post("/api/login", json={"password": "secret-admin"})
        admin.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code, 200)
        uid = c.get("/api/whoami").json()["profile"]["id"]
        c.put("/api/profile/settings", json={"briefing_at": "07:30", "tz": "Europe/Berlin"})
        written, sent = [], []

        async def brief(u, tz="", markdown=False):
            written.append(u)
            return "Guten Morgen."

        async def send(u, title, body, tag="", private=True, why=""):
            sent.append(u)
            return 1
        old = chat.morning_briefing, push.send, push.subs
        chat.morning_briefing, push.send = brief, send
        push.subs = lambda u: [{"endpoint": "x"}] if u == uid else []
        zone = chat.user_zone("Europe/Berlin")
        try:
            asyncio.run(chat.due_briefings(datetime.datetime(2026, 10, 14, 7, 22, tzinfo=zone)))   # 8 min ahead
            self.assertEqual((written, sent), ([uid], []))
            asyncio.run(chat.due_briefings(datetime.datetime(2026, 10, 14, 7, 25, tzinfo=zone)))   # once a day
            self.assertEqual(written, [uid])
            asyncio.run(chat.due_briefings(datetime.datetime(2026, 10, 14, 7, 30, tzinfo=zone)))   # on the minute
            self.assertEqual((written, sent), ([uid], [uid]))                                       # not written again
        finally:
            chat.morning_briefing, push.send, push.subs = old
            chat._brief_ready.pop(uid, None)


if __name__ == "__main__":
    unittest.main()
