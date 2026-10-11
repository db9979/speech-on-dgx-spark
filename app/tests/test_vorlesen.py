"""Antworten vorlesen (profile setting speak, on by default): switched off, the answer comes as text only on every
own screen: no TTS request, no ready-made sentence (ack.py). A speaker without a screen and CarPlay keep speaking.
The request can always ask for text only itself, never for sound against the switch. No model, no clock."""
import base64
import unittest
from types import SimpleNamespace

from tests import helpers

helpers.start()
import panel  # noqa: E402
import ack  # noqa: E402
import chat_turn  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
CLIP = b"\x07\x00" * 1200


def profile(name, **settings):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    if settings:
        assert c.put("/api/profile/settings", json=settings).status_code == 200
    return c


def ask(client, text="Erzähl mir etwas über Bäume.", **extra):
    r = client.post("/api/chat", json=dict({"messages": [{"role": "user", "content": text}]}, **extra))
    assert r.status_code == 200, r.text
    return helpers.events(r)


def sound(evs):
    return [base64.b64decode(e["audio"]) for e in evs if e["type"] == "audio"]


def text(evs):
    return "".join(e.get("delta", "") for e in evs if e["type"] == "text")


class Setting(unittest.TestCase):
    def test_on_by_default_and_only_true_or_false(self):
        default, ok = profiles.SETTINGS["speak"]
        self.assertIs(default, True)
        self.assertTrue(ok(False) and ok(True))
        self.assertFalse(ok("off") or ok(0) or ok(None))

    def test_rule(self):
        req = SimpleNamespace(scope={})
        off, on = {"speak": False}, {"speak": True}
        import unittest.mock as m
        with m.patch.object(profiles, "device", return_value=None):
            self.assertTrue(chat_turn.quiet(req, {}, off, False))
            self.assertFalse(chat_turn.quiet(req, {}, on, False))
            self.assertFalse(chat_turn.quiet(req, {}, off, True))                       # CarPlay keeps speaking
            self.assertFalse(chat_turn.quiet(req, {"client": "speaker"}, off, False))   # a speaker without a screen
            self.assertFalse(chat_turn.quiet(SimpleNamespace(scope={"speech_voice": "x"}), {}, off, False))

    def test_the_app_may_change_it(self):
        import iphone
        self.assertIn("speak", iphone.APP_FIELDS)


class InTheAnswer(unittest.TestCase):
    def setUp(self):
        helpers.LLM_CALLS.clear()

    def test_on_speaks(self):
        evs = ask(profile("Vorl1"))
        self.assertTrue(sound(evs))
        self.assertTrue(text(evs))

    def test_off_text_only(self):
        evs = ask(profile("Vorl2", speak=False))
        self.assertFalse(sound(evs))
        self.assertTrue(text(evs))
        self.assertFalse(any(e["type"] == "tts_request" for e in evs))   # no TTS request at all

    def test_off_also_no_ready_made_sentence(self):
        helpers.set_config(routing=True, instant_ack=True)
        try:
            for t in ack.all_texts(False):
                ack.save(ack.key({}, t, "German"), CLIP)
            evs = ask(profile("Vorl3", route=True, instant_ack=True, speak=False), "Welche Termine habe ich morgen?")
            self.assertFalse(sound(evs))
        finally:
            helpers.set_config(routing=False, instant_ack=False)

    def test_request_asks_text_only_never_sound(self):
        self.assertFalse(sound(ask(profile("Vorl4"), speak=False)))               # this device only
        self.assertFalse(sound(ask(profile("Vorl5", speak=False), speak=True)))   # the profile's switch wins

    def test_the_begleiter_hears_of_it(self):   # the paired program: test_begleiter.test_aloud_follows_the_profile
        import begleiter
        p = profile("Vorl6")
        uid = next(x["id"] for x in profiles._load()["users"] if x["name"] == "Vorl6")
        self.assertTrue(begleiter.aloud(uid))
        p.put("/api/profile/settings", json={"speak": False})
        self.assertFalse(begleiter.aloud(uid))

if __name__ == "__main__":
    unittest.main()
