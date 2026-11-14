"""Natürliches Gespräch (gespraech.py, plan gespraechshinweise/plan.md, Dominik 2026-11-14): the tone of spoken small
talk and one fixed hint at the end of a spoken answer without a tool.

The panel decides, never the model: the kind comes from fixed words of the person's own sentences, the sentence is
fixed and holds only numbers and times the panel read itself (never a title or other outside text), nothing is fetched
from the network for it. Off by default, a preference per profile, never for guests, another voice, after outside text,
with a tool, under the Notaus, parcels never in the car. A „Ja“ becomes a fixed question that reaches its group; „Nein“
rests the kind. No test depends on the wall clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import datetime
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat_modell  # noqa: E402
import features  # noqa: E402
import gespraech  # noqa: E402
import intent  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000
ZONE = datetime.timezone.utc
NOW = datetime.datetime.fromtimestamp(T0, ZONE)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    return next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class Turn:
    """What gespraech reads of a turn (chat_turn.Turn)."""

    def __init__(self, uid, text, org="speaker", body=None, carry=None, own=True, before=()):
        self.who = {"id": uid} if uid else None
        self.own_browser = own
        self.hilfe_origin = org
        self.body = dict({"tz": "UTC"}, **(body or {}))
        self.messages = [{"role": "user", "content": t} for t in before] + [{"role": "user", "content": text}]
        self.carry = carry
        self.mcp = None
        self.src0 = "speaker:c1:abc"
        self.route = intent.classify(text)


def hint(turn, calls=(), now=T0, en=False):
    return asyncio.run(chat_modell.gespraechshinweis(turn, list(calls), en, now=now))


def ton(turn, en=False):
    """chat_turn's rule for the tone note (the stage _prompt asks the same)."""
    import saetze
    uid = turn.who and turn.who["id"]
    return gespraech.ton(bool(uid) and turn.own_browser and gespraech.talk(turn.route) and not turn.carry
                         and gespraech.spoken(turn.body, saetze.channel(turn)) and features.allowed(gespraech.KEY, uid), en)


def shopping(n):
    return mock.patch("tasks.card", return_value={"open": n, "shopping": n, "first": ["Geheime Zutat"], "lists": 2})


def events(*starts, title="Geheimes Treffen bei Firma X"):
    evs = [{"start": NOW + datetime.timedelta(minutes=m), "allday": False, "title": title} for m in starts]

    async def ev(uid, start, end, zone, shared=False, stale=False):
        return evs, []
    return mock.patch.multiple("calendars", get=mock.Mock(return_value={"calendars": [{"name": "x"}]}),
                               events=ev)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uid = profile("Plaudertasche")

    def setUp(self):
        helpers.set_config(gespraech=True, tasks=True, calendar=True, weather=True, parcels=True, mail=True)
        profiles.save_settings(self.uid, {"talk_hints": True})
        gespraech._st.clear()

    def tearDown(self):
        helpers.set_config(gespraech=False)
        gespraech._st.clear()


class Defaults(unittest.TestCase):
    def test_off_by_default_and_a_preference_that_is_on(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["gespraech"], False)
        self.assertIs(profiles.SETTINGS["talk_hints"][0], True)   # something the Spark does unasked: on unless off
        f = next(x for x in features.FEATURES if x.key == gespraech.KEY)
        self.assertEqual((f.admin, f.pref), (("gespraech",), "talk_hints"))

    def test_every_fixed_question_reaches_its_group(self):
        want = {"termine": "kalender", "wetter": "wetter", "pakete": "paket", "einkauf": "liste"}
        self.assertEqual(set(gespraech.FRAGE), set(gespraech.THEMEN))
        for kind, (de, en) in gespraech.FRAGE.items():
            for q in (de, en):
                self.assertIn(want[kind], intent.classify(q).names, q)


class Hint(Base):
    def test_a_topic_word_gives_one_fixed_sentence_and_a_yes_becomes_the_question(self):
        with shopping(4):
            s = hint(Turn(self.uid, "Ich muss nachher noch kochen, mal sehen was ich mache."))
        self.assertEqual(s, "Auf deiner Einkaufsliste stehen übrigens 4 Sachen. Soll ich sie dir vorlesen?")
        self.assertNotIn("Geheime", s)
        self.assertEqual(gespraech.answer(self.uid, "speaker:c1:abc", "Ja, gern", now=T0 + 60),
                         ("Was steht auf meiner Einkaufsliste?", "einkauf"))
        self.assertIsNone(gespraech.answer(self.uid, "speaker:c1:abc", "Ja", now=T0 + 70))   # only once

    def test_calendar_hint_has_numbers_and_times_never_a_title(self):
        with events(30, 150):
            s = hint(Turn(self.uid, "Puh, heute ist echt viel los."))
        self.assertIn("2 Termine", s)
        self.assertIn(f"{(NOW + datetime.timedelta(minutes=30)):%H:%M}", s)
        self.assertNotIn("Geheim", s)
        self.assertNotIn("Firma", s)

    def test_without_a_topic_only_an_appointment_soon_and_only_after_every_answers(self):
        with events(45):
            st = gespraech._state(self.uid)
            st["n"] = 0
            self.assertEqual(hint(Turn(self.uid, "Erzähl mir was Lustiges.")), "")
            self.assertEqual(hint(Turn(self.uid, "Erzähl mir was Lustiges.")), "")
            s = hint(Turn(self.uid, "Erzähl mir was Lustiges."))
        self.assertTrue(s.startswith("Kurz zur Erinnerung: um"), s)
        gespraech._st.clear()
        with events(120):
            self.assertEqual(hint(Turn(self.uid, "Erzähl mir was Lustiges.")), "")

    def test_weather_only_from_a_fresh_reading_never_from_the_network(self):
        import weather
        place = {"lat": 48.1, "lon": 11.6, "name": "Zuhause"}
        hours = [(NOW + datetime.timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(12)]
        d = {"utc_offset_seconds": 0, "hourly": {"time": hours, "precipitation_probability": [0, 0, 0, 80] + [0] * 8}}

        async def never(*a, **k):
            raise AssertionError("no network for a hint")
        with mock.patch.object(weather, "usable", return_value=True), mock.patch.object(weather, "get", return_value=place), \
                mock.patch.object(weather, "forecast", never), \
                mock.patch.dict(weather._cache, {(48.1, 11.6): (T0 - 600, d)}):
            s = hint(Turn(self.uid, "Ich will nachher noch joggen gehen."))
            self.assertIn(f"ab etwa {(NOW + datetime.timedelta(hours=3)).hour} Uhr", s)
            gespraech._st.clear()
            with mock.patch.dict(weather._cache, {(48.1, 11.6): (T0 - gespraech.WEATHER_FRESH - 1, d)}), \
                    mock.patch.object(weather.SUPPLY, "load", return_value={}):
                self.assertEqual(hint(Turn(self.uid, "Ich will nachher noch joggen gehen.")), "")

    def test_parcels_never_in_the_car(self):
        import parcels
        hit = (T0, ([{"status": "today", "day": NOW.date().isoformat(), "shop": "Geheimshop"}], []))
        with mock.patch.object(parcels, "usable", return_value=True), mock.patch.dict(parcels._cache, {self.uid: hit}):
            self.assertEqual(hint(Turn(self.uid, "Ich habe was bestellt.", org="iphone", body={"car": True})), "")
            s = hint(Turn(self.uid, "Ich habe was bestellt."))
        self.assertEqual(s, "Übrigens soll heute noch ein Paket kommen. Soll ich dir sagen, welches?")


class Never(Base):
    def test_not_for_guests_another_voice_outside_text_or_a_tool(self):
        with shopping(3):
            t = "Ich muss nachher noch kochen."
            self.assertEqual(hint(Turn(None, t)), "")
            self.assertEqual(hint(Turn(self.uid, t, own=False)), "")
            self.assertEqual(hint(Turn(self.uid, t, carry="outside")), "")
            self.assertEqual(hint(Turn(self.uid, t), calls=[{"name": "tasks_show"}]), "")
            self.assertEqual(hint(Turn(self.uid, "Wie wird das Wetter morgen beim Kochen?")), "")   # a group: no talk

    def test_only_spoken(self):
        with shopping(3):
            t = "Ich muss nachher noch kochen."
            self.assertEqual(hint(Turn(self.uid, t, org="panel")), "")              # typed in the panel
            self.assertEqual(hint(Turn(self.uid, t, body={"speak": False})), "")    # text only
            self.assertTrue(hint(Turn(self.uid, t, org="panel", body={"spoken": True})))

    def test_admin_profile_and_notaus_switch_it_off(self):
        with shopping(3):
            t = "Ich muss nachher noch kochen."
            profiles.save_settings(self.uid, {"talk_hints": False})
            self.assertEqual(hint(Turn(self.uid, t)), "")
            self.assertEqual(ton(Turn(self.uid, t)), "")
            profiles.save_settings(self.uid, {"talk_hints": True})
            helpers.set_config(gespraech=False)
            self.assertEqual(hint(Turn(self.uid, t)), "")
            helpers.set_config(gespraech=True)
            with mock.patch.object(notaus, "refuse", return_value=True):
                self.assertEqual(hint(Turn(self.uid, t)), "")


class Sparing(Base):
    def test_one_per_every_answers_and_each_kind_once_per_gap(self):
        with shopping(2), events(200):
            t = "Ich muss nachher noch kochen."
            self.assertTrue(hint(Turn(self.uid, t), now=T0))
            self.assertEqual(hint(Turn(self.uid, "Heute ist viel los."), now=T0 + 10), "")
            self.assertEqual(hint(Turn(self.uid, "Heute ist viel los."), now=T0 + 20), "")
            self.assertTrue(hint(Turn(self.uid, "Heute ist viel los."), now=T0 + 30).startswith("Übrigens steht"))
            for i in range(3):   # the shopping list again only after KIND_GAP
                self.assertEqual(hint(Turn(self.uid, t), now=T0 + 40 + i), "")
            self.assertTrue(hint(Turn(self.uid, t), now=T0 + gespraech.KIND_GAP + 60))

    def test_no_rests_the_kind_and_a_yes_counts_only_in_its_conversation_and_time(self):
        with shopping(2):
            t = "Ich muss nachher noch kochen."
            self.assertTrue(hint(Turn(self.uid, t), now=T0))
            self.assertIsNone(gespraech.answer(self.uid, "speaker:c1:abc", "Nein, danke", now=T0 + 5))
            gespraech._state(self.uid)["n"] = gespraech.EVERY
            self.assertEqual(hint(Turn(self.uid, t), now=T0 + gespraech.KIND_GAP + 1), "")   # rests NO_PAUSE
            self.assertTrue(hint(Turn(self.uid, t), now=T0 + gespraech.NO_PAUSE + 10))
            self.assertIsNone(gespraech.answer(self.uid, "telefon:c9:def", "Ja", now=T0 + gespraech.NO_PAUSE + 20))
            gespraech._st.clear()
            self.assertTrue(hint(Turn(self.uid, t), now=T0))
            self.assertIsNone(gespraech.answer(self.uid, "speaker:c1:abc", "Ja", now=T0 + gespraech.OFFER_SECONDS + 1))


class Tone(Base):
    def test_only_small_talk_spoken(self):
        self.assertEqual(ton(Turn(self.uid, "Wie geht es dir heute?")), gespraech.TON)
        self.assertEqual(ton(Turn(self.uid, "How are you today?"), en=True), gespraech.TON_EN)
        self.assertEqual(ton(Turn(self.uid, "Wie wird das Wetter morgen?")), "")
        self.assertEqual(ton(Turn(self.uid, "Wie geht es dir heute?", org="panel")), "")
        self.assertEqual(ton(Turn(None, "Wie geht es dir heute?")), "")


class Anschluss(Base):
    def test_after_the_weather_the_calendar_is_offered_once(self):
        t = Turn(self.uid, "Wie wird das Wetter morgen?")
        s = hint(t, calls=[{"name": "weather"}])
        self.assertEqual(s, gespraech.ANGEBOT["termine"][0])
        self.assertEqual(gespraech.answer(self.uid, "speaker:c1:abc", "Ja", now=T0 + 30),
                         ("Was steht heute noch in meinem Kalender?", "termine"))
        for i in range(gespraech.EVERY):   # the same kind not again before KIND_GAP
            self.assertEqual(hint(t, calls=[{"name": "weather"}], now=T0 + 60 + i), "")

    def test_never_what_the_answer_read_itself_or_unknown_tools(self):
        t = Turn(self.uid, "Wie wird das Wetter und was steht im Kalender?")
        self.assertEqual(hint(t, calls=[{"name": "weather"}, {"name": "calendar_events"}]), "")
        gespraech._st.clear()
        self.assertEqual(hint(t, calls=[{"name": "mail_list"}]), "")
        gespraech._st.clear()
        helpers.set_config(calendar=False)
        self.assertEqual(hint(t, calls=[{"name": "weather"}]), "")


class Ueberblick(Base):
    def over(self, text, **kw):
        return asyncio.run(chat_modell.gespraech_ueberblick(Turn(self.uid, text, **kw), text, now=T0))

    def test_fixed_overview_and_a_word_picks_the_kind(self):
        with events(30, 90), shopping(2):
            s = self.over("Was gibt's Neues?")
        self.assertIn("Heute stehen noch 2 Termine an", s)
        self.assertIn("Auf der Einkaufsliste stehen 2 Sachen.", s)
        self.assertTrue(s.endswith("Worüber soll ich mehr erzählen?"))
        self.assertNotIn("Geheim", s)
        self.assertEqual(gespraech.answer(self.uid, "speaker:c1:abc", "Die Einkaufsliste bitte", now=T0 + 20),
                         ("Was steht auf meiner Einkaufsliste?", "einkauf"))

    def test_only_whole_questions_spoken_and_released(self):
        with shopping(2):
            self.assertIsNone(self.over("Was gibt es Neues in der Welt?"))
            self.assertIsNone(self.over("Was gibt's Neues?", org="panel"))
            helpers.set_config(gespraech=False)
            self.assertIsNone(self.over("Was gibt's Neues?"))

    def test_nothing_to_say(self):
        with shopping(0), mock.patch.object(features, "allowed", lambda k, u, *a: k in (gespraech.KEY, "tasks")):
            self.assertEqual(self.over("Was gibt's Neues?"), "Gerade liegt bei dir nichts Neues an.")
        self.assertIsNone(gespraech.answer(self.uid, "speaker:c1:abc", "Ja", now=T0 + 5))


class Begruessung(Base):
    def test_a_greeting_gets_the_one_most_important_point_once(self):
        with events(45, 200):
            s = hint(Turn(self.uid, "Hallo Spark!"))   # „Guten Morgen“ is the morning briefing (Weiche kalender)
            self.assertTrue(s.startswith("Übrigens stehen heute noch 2 Termine an"), s)
            self.assertNotIn("Geheim", s)
            gespraech._state(self.uid)["kinds"].clear()
            self.assertFalse(hint(Turn(self.uid, "Servus"), now=T0 + 60).startswith("Übrigens stehen"))

    def test_nothing_to_say_and_not_for_more_than_a_greeting(self):
        with events(), shopping(3):
            self.assertEqual(hint(Turn(self.uid, "Guten Abend")), "")   # no appointment left, no rain, no parcel
        self.assertEqual(gespraech.gruss(self.uid, "Guten Morgen, wie wird das Wetter?", {"termine"}, T0 + 10 ** 6), [])
        self.assertEqual(gespraech.gruss(self.uid, "Hallo", {"termine", "einkauf"}, T0 + 10 ** 6), ["termine"])


if __name__ == "__main__":
    unittest.main()
