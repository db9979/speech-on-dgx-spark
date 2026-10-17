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

    def test_never_for_guests(self):
        helpers.set_config(show_steps=True)
        guest = TestClient(panel.app)
        r = guest.post("/api/chat", json={"messages": [{"role": "user", "content": "TOOL reminder_list {}"}], "speak": False})
        if r.status_code == 200:
            self.assertFalse([e for e in helpers.events(r) if e["type"] in ("step", "confirm")])


if __name__ == "__main__":
    unittest.main()
