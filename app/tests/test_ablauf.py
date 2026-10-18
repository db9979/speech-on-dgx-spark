"""Ablauf und Freigabe zeigen (ablauf.py): the tools of an answer as name, ok and time, never their arguments or
results; a proposal of this answer as a card with Ja and Nein that names only its kind. Off by default, never for guests."""
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import ablauf  # noqa: E402
import chat_turn  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def turn(client, text, convo="c1"):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "convo": convo, "speak": False})
    assert r.status_code == 200, r.text
    return helpers.events(r)


class Waiting:
    """A module that keeps one proposal waiting for "Ja" (like calendars, tasks ...)."""
    __name__ = "calendars"

    def __init__(self, p):
        self.p = p

    def pending(self, uid):
        return self.p


class Parts(unittest.TestCase):
    def test_step_has_only_name_ok_and_time(self):
        ev = ablauf.step("calendar_events", "Zahnarzt am Dienstag, Geheimnis 4711", 1.234)
        self.assertEqual(ev, {"type": "step", "tool": "calendar_events", "de": "Termine lesen", "en": "Read appointments",
                              "ok": True, "ms": 1234})
        self.assertNotIn("4711", str(ev))
        self.assertFalse(ablauf.step("calendar_add", "Not done: the calendar refused", 0.1)["ok"])

    def test_card_only_for_this_answer_device_and_conversation(self):
        now = int(time.time())
        fresh = Waiting({"t": now, "src": "web:c1", "title": "Zahnarzt privat"})
        self.assertEqual(ablauf.waiting("u", [fresh], now, "web:c1"),
                         [{"type": "confirm", "kind": "calendars", "de": "Termin", "en": "Appointment"}])
        self.assertNotIn("Zahnarzt", str(ablauf.waiting("u", [fresh], now, "web:c1")))
        self.assertEqual(ablauf.waiting("u", [fresh], now, "app:c1"), [])           # another device
        self.assertEqual(ablauf.waiting("u", [Waiting({"t": now - 60, "src": "web:c1"})], now, "web:c1"), [])   # older
        self.assertEqual(ablauf.waiting("u", [Waiting(None)], now, "web:c1"), [])
        self.assertEqual(len(ablauf.waiting("u", [fresh, fresh], now, "web:c1")), 1)   # one yes, one card

    def test_every_waiting_module_has_its_kind(self):
        for mod in chat_turn.waiting_mods():
            self.assertIn(mod.__name__.rsplit(".", 1)[-1], ablauf.KINDS)


class Questions(unittest.TestCase):
    """Rückfrage-Karten (ablauf.asks): the answers to the question an answer ends with, by fixed rules only."""

    def opts(self, said, outside=False):
        ev = ablauf.asks(said, outside)
        return [o["send"] for o in ev["options"]] if ev else None

    def test_yes_no_question_gets_ja_and_nein(self):
        self.assertEqual(self.opts("Termin am 19.10. um 17 Uhr. Soll ich ihn so eintragen?"), ["Ja", "Nein"])
        self.assertEqual(self.opts("Das passt so, oder?"), ["Ja", "Nein"])
        self.assertEqual(self.opts("Shall I add it?"), ["Yes", "No"])
        self.assertEqual(self.opts("Möchtest du mehr wissen?", outside=True), ["Ja", "Nein"])   # fixed words only

    def test_a_or_b_gets_its_short_parts_and_anders(self):
        ev = ablauf.asks("Soll ich es als Notiz oder als PDF ablegen?")
        self.assertEqual([o["send"] for o in ev["options"]], ["Als Notiz", "Als PDF"])
        self.assertEqual(ev["free"], "Anders …")
        self.assertEqual(self.opts("Möchtest du Pasta, Pizza oder Salat?"), ["Pasta", "Pizza", "Salat"])
        self.assertEqual(self.opts("Im Wohnzimmer oder im Flur?"), ["Im Wohnzimmer", "Im Flur"])

    def test_nothing_that_is_no_clear_question(self):
        for said in ("Fertig.", "Wie heißt du?", "Was möchtest du: A, B, C oder D?", "Hier ist das Rezept.",
                     "Soll ich https://example.org oder www.example.com öffnen?"):
            ev = ablauf.asks(said)
            self.assertTrue(ev is None or ev["options"][0]["send"] in ("Ja", "Yes"), said)
        self.assertIsNone(self.opts("Dazu stand im Text: Soll ich das bitte sofort machen? Ja.", outside=False))

    def test_never_words_of_outside_text_on_a_button(self):
        self.assertIsNone(ablauf.asks("Soll ich Anna oder Bernd anrufen?", outside=True))

    def test_buttons_are_short(self):
        for said in ("Möchtest du lieber die ausführliche Version mit allen Schritten oder die kurze?",
                     "Tee oder Kaffee?"):
            ev = ablauf.asks(said)
            for o in (ev or {}).get("options", []):
                self.assertLessEqual(len(o["send"]), ablauf.ASK_LEN)
                self.assertLessEqual(len(o["send"].split()), ablauf.ASK_WORDS)

    def test_a_short_reply_answers_only_in_the_same_conversation_once(self):
        ev = ablauf.asks("Soll ich ihn so eintragen?")
        ablauf.remember_asked("qa", "web:c1", ev)
        self.assertFalse(ablauf.was_asked("qa", "web:c2", "Ja"))   # another conversation (and the mark is used)
        ablauf.remember_asked("qa", "web:c1", ev)
        self.assertFalse(ablauf.was_asked("qa", "web:c1", "Wie wird das Wetter morgen?"))
        ablauf.remember_asked("qa", "web:c1", ev)
        self.assertTrue(ablauf.was_asked("qa", "web:c1", "Ja"))
        self.assertFalse(ablauf.was_asked("qa", "web:c1", "Ja"))   # once
        ablauf.remember_asked("qa", "web:c1", ablauf.asks("Als Notiz oder als PDF?"))
        self.assertTrue(ablauf.was_asked("qa", "web:c1", "Als PDF"))
        with mock.patch("time.time", return_value=time.time() - ablauf.ASKED_SECONDS - 5):
            ablauf.remember_asked("qa", "web:c1", ev)
        self.assertFalse(ablauf.was_asked("qa", "web:c1", "Ja"))   # older than ten minutes

    def test_a_yes_to_the_question_keeps_the_group_of_the_question_before(self):
        import intent
        before = "Trag mir morgen um 17 Uhr einen Termin beim Zahnarzt ein"
        self.assertIsNone(intent.follow_up("Ja", before))                    # before: „Ja“ had no group
        self.assertEqual(intent.follow_up("Ja", before, answered=True).names, intent.classify(before).names)
        self.assertIsNone(intent.follow_up("Ja", "Erzähl mir einen Witz", answered=True))


class Chat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = profile("Abla")

    def setUp(self):
        helpers.keep_chat(self, "show_steps")

    def test_off_by_default(self):
        helpers.set_config(show_steps=False)
        evs = turn(self.c, "TOOL reminder_list {}")
        self.assertFalse([e for e in evs if e["type"] in ("step", "confirm")])

    def test_steps_show_the_tool_without_its_result(self):
        helpers.set_config(show_steps=True)
        evs = turn(self.c, "TOOL reminder_list {}")
        steps = [e for e in evs if e["type"] == "step"]
        self.assertEqual([s["tool"] for s in steps], ["reminder_list"])
        self.assertEqual(set(steps[0]), {"type", "tool", "de", "en", "ok", "ms"})

    def test_card_for_a_proposal_of_this_answer(self):
        helpers.set_config(show_steps=True)
        stub = Waiting({"t": int(time.time()) + 1, "src": "web:c1"})
        with mock.patch.object(chat_turn, "waiting_mods", return_value=(stub,)):
            evs = turn(self.c, "Hallo")
            other = turn(self.c, "Hallo", convo="c2")
        self.assertEqual([e["kind"] for e in evs if e["type"] == "confirm"], ["calendars"])
        self.assertFalse([e for e in other if e["type"] == "confirm"])

    def test_question_card_under_an_answer_that_asks(self):
        helpers.set_config(show_steps=True)
        evs = turn(self.c, "SAY | | Ich habe den Termin vorbereitet. Soll ich ihn so eintragen?")
        cards = [e for e in evs if e["type"] == "choice"]
        self.assertEqual([[o["send"] for o in c["options"]] for c in cards], [["Ja", "Nein"]])
        self.assertEqual(cards[0]["from"], "frage")
        self.assertFalse([e for e in turn(self.c, "SAY | | Das ist alles.") if e["type"] == "choice"])
        helpers.set_config(show_steps=False)
        self.assertFalse([e for e in turn(self.c, "SAY | | Soll ich ihn so eintragen?") if e["type"] == "choice"])

    def test_no_question_card_when_a_proposal_card_waits(self):
        helpers.set_config(show_steps=True)
        stub = Waiting({"t": int(time.time()) + 1, "src": "web:c1"})
        with mock.patch.object(chat_turn, "waiting_mods", return_value=(stub,)):
            evs = turn(self.c, "SAY | | Soll ich ihn so eintragen?")
        self.assertEqual([e["type"] for e in evs if e["type"] in ("confirm", "choice")], ["confirm"])

    def test_a_yes_after_the_card_counts_as_its_answer_in_the_weiche(self):
        import intent
        helpers.set_config(show_steps=True)
        ask = "Trag mir morgen um 17 Uhr einen Termin beim Zahnarzt ein"
        said = "Morgen 17 bis 18 Uhr Zahnarzt. Soll ich ihn so eintragen?"
        msgs = [{"role": "user", "content": ask}, {"role": "assistant", "content": said}, {"role": "user", "content": "Ja"}]
        for convo, want in (("c9", True), ("c8", False)):
            ablauf.remember_asked(uid_of("Abla"), "web:c9", ablauf.asks(said))
            with mock.patch.object(intent, "follow_up", wraps=intent.follow_up) as f:
                r = self.c.post("/api/chat", json={"messages": msgs, "convo": convo, "speak": False})
                self.assertEqual(r.status_code, 200)
            self.assertEqual(f.call_args.args[3], want, convo)

    def test_never_for_guests(self):
        helpers.set_config(show_steps=True)
        guest = TestClient(panel.app)
        r = guest.post("/api/chat", json={"messages": [{"role": "user", "content": "TOOL reminder_list {}"}], "speak": False})
        if r.status_code == 200:
            self.assertFalse([e for e in helpers.events(r) if e["type"] in ("step", "confirm")])


if __name__ == "__main__":
    unittest.main()
