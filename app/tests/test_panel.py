"""API tests against the panel with fake LLM, TTS and Home Assistant (see helpers.py).

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
import chat  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    """A fresh browser logged into a (new) profile."""
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def ask(client, text, **body):
    r = client.post("/api/chat", json=dict({"messages": [{"role": "user", "content": text}]}, **body))
    assert r.status_code == 200, r.text
    return helpers.events(r)


def answer(evs):
    return "".join(e.get("delta", "") for e in evs if e["type"] == "text")


class Access(unittest.TestCase):
    def setUp(self):
        helpers.set_config(public=True)

    def test_admin_pages_need_password(self):
        g = TestClient(panel.app)
        self.assertEqual(g.get("/api/config").status_code, 401)
        self.assertEqual(ADMIN.get("/api/config").status_code, 200)
        self.assertEqual(g.post("/api/login", json={"password": "wrong"}).status_code, 401)

    def test_public_chat_for_guests(self):
        evs = ask(TestClient(panel.app), "Hallo")
        self.assertEqual(answer(evs), "Hallo.")
        self.assertTrue(any(e["type"] == "audio" for e in evs))

    def test_not_public_locks_guests_out_but_lets_profiles_in(self):
        p = profile("Pia")
        helpers.set_config(public=False)
        g = TestClient(panel.app)
        self.assertEqual(g.post("/api/chat", json={"messages": [{"role": "user", "content": "x"}]}).status_code, 401)
        self.assertEqual(g.post("/api/profile/login", json={"name": "Pia", "pin": "1234"}).status_code, 200)
        self.assertEqual(answer(ask(g, "Hallo")), "Hallo.")
        self.assertEqual(answer(ask(p, "Hallo")), "Hallo.")
        self.assertEqual(p.get("/api/config").status_code, 401)  # a profile is no admin

    def test_wrong_pin(self):
        profile("Wanda", "4321")
        self.assertEqual(TestClient(panel.app).post("/api/profile/login", json={"name": "Wanda", "pin": "0000"}).status_code, 401)


class Page(unittest.TestCase):
    def test_page_and_its_files_load(self):
        import re
        g = TestClient(panel.app)
        html = g.get("/").text
        files = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
        self.assertTrue(any(f.endswith(".js") for f in files))
        for f in files:
            self.assertEqual(g.get(f).status_code, 200, f)
        self.assertEqual(g.get("/static/js/../index.html").status_code, 404)


class Isolation(unittest.TestCase):
    """What one profile stores is never visible to another profile or a guest."""

    def test_memory_documents_conversations(self):
        a, b, g = profile("Anna"), profile("Bert"), TestClient(panel.app)
        ask(a, 'TOOL memory_save {"fact": "Anna mag Rosen."}')
        self.assertIn("Anna mag Rosen.", [f["text"] for f in a.get("/api/profile/memory").json()["facts"]])
        self.assertNotIn("Anna mag Rosen.", json.dumps(b.get("/api/profile/memory").json()))
        self.assertEqual(g.get("/api/profile/memory").status_code, 401)
        r = a.post("/api/profile/docs", files={"file": ("geheim.txt", b"Der Tresorcode ist 4711. " * 5)})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(a.get("/api/profile/docs").json()), 1)
        self.assertEqual(b.get("/api/profile/docs").json(), [])
        self.assertEqual(g.post("/api/profile/docs", files={"file": ("x.txt", b"x")}).status_code, 401)
        self.assertIn("NO TOOL document_search", answer(ask(b, 'TOOL document_search {"query": "Tresorcode"}')))
        self.assertIn("4711", answer(ask(a, 'TOOL document_search {"query": "Tresorcode"}')))
        a.put("/api/profile/convos", json={"id": "c1", "title": "Garten", "updated": 1, "msgs": [
            {"role": "user", "content": "Wann Rosen schneiden?"}, {"role": "assistant", "content": "Im März."}]})
        self.assertEqual(b.get("/api/profile/convos").json(), [])
        self.assertIn("März", answer(ask(a, 'TOOL history_search {"query": "Rosen schneiden"}')))
        self.assertNotIn("März", answer(ask(b, 'TOOL history_search {"query": "Rosen"}')))

    def test_guest_has_no_profile_tools(self):
        helpers.LLM_CALLS.clear()
        ask(TestClient(panel.app), "Hallo")
        names = {t["function"]["name"] for t in helpers.LLM_CALLS[-1].get("tools", [])}
        for n in ("memory_save", "document_search", "history_search", "home_assistant", "calendar_events"):
            self.assertNotIn(n, names)

    def test_guest_cannot_choose_voice(self):
        self.assertEqual(TestClient(panel.app).get("/api/assistant/voices").status_code, 401)


class HomeAssistant(unittest.TestCase):
    def test_per_profile(self):
        a, b = profile("Hanna"), profile("Holger")
        url = f"http://127.0.0.1:{helpers.HA_PORT}"
        self.assertEqual(a.put("/api/profile/homeassistant", json={"url": url, "token": "x" * 40}).status_code, 400)
        r = a.put("/api/profile/homeassistant", json={"url": url, "token": helpers.HA_TOKEN})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(helpers.HA_TOKEN, r.text)
        self.assertNotIn(helpers.HA_TOKEN, a.get("/api/profile/homeassistant").text)
        evs = ask(a, 'TOOL home_assistant {"command": "Licht in der Küche an"}')
        self.assertTrue(any(e["type"] == "home_done" and e["ok"] for e in evs))
        self.assertEqual(helpers.HA_CALLS[-1]["text"], "Licht in der Küche an")
        self.assertIn("NO TOOL home_assistant", answer(ask(b, 'TOOL home_assistant {"command": "Licht an"}')))
        # states: every entity, zones and people, found by room, kind or name, not only what Assist knows
        self.assertIn("21.5 °C", answer(ask(a, 'TOOL home_assistant_states {"query": "Wie warm ist es im Wohnzimmer"}')))
        res = answer(ask(a, 'TOOL home_assistant_states {"query": "Fenster offen"}'))
        self.assertIn("Bad Fenster", res)
        self.assertNotIn("Licht", res)
        res = answer(ask(a, 'TOOL home_assistant_states {}'))
        self.assertIn("Büro", res)
        self.assertIn("Zuhause", res)
        self.assertIn("Wohnzimmer", res)
        self.assertIn("Anna", answer(ask(a, 'TOOL home_assistant_states {"domain": "zone"}')))
        self.assertIn("NO TOOL home_assistant_states", answer(ask(b, 'TOOL home_assistant_states {}')))


class Settings(unittest.TestCase):
    def test_profile_settings_validated(self):
        a = profile("Sven")
        a.put("/api/profile/settings", json={"speed": 1.2, "length": "nonsense", "learn": False})
        s = a.get("/api/profile/settings").json()["settings"]
        self.assertEqual(s["speed"], 1.2)
        self.assertEqual(s["length"], "normal")
        self.assertFalse(s["learn"])


class Learning(unittest.TestCase):
    def test_learns_from_quiet_conversation(self):
        a = profile("Lena")
        old = int((time.time() - 3600) * 1000)
        a.put("/api/profile/convos", json={"id": "q1", "title": "Tee", "updated": old, "msgs": [
            {"role": "user", "content": "Ich trinke gern Tee."}, {"role": "assistant", "content": "Schön."}]})
        uid = next(u["id"] for u in profiles.admin_list()["users"] if u["name"] == "Lena")
        chat._last_chat[0] = 0
        import asyncio
        asyncio.run(chat.learn_once())
        facts = profiles.memory(uid)
        self.assertTrue(any(f["text"] == "Test mag Tee." and f.get("auto") for f in facts))
        self.assertEqual(asyncio.run(chat.learn_once()), 0)  # read once only


if __name__ == "__main__":
    unittest.main()
