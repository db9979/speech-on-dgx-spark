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
        # direct actions for devices Assist does not know, never for locks
        res = answer(ask(a, 'TOOL home_assistant_action {"entity_id": "switch.keller", "service": "turn_on"}'))
        self.assertIn("Kellerpumpe", res)
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "switch.keller", "service": "switch.turn_on"})
        n = len(helpers.HA_CALLS)
        res = answer(ask(a, 'TOOL home_assistant_action {"entity_id": "lock.haustuer", "service": "unlock"}'))
        self.assertIn("failed", res)
        self.assertEqual(len(helpers.HA_CALLS), n)
        self.assertIn("NO TOOL home_assistant_action",
                      answer(ask(b, 'TOOL home_assistant_action {"entity_id": "switch.keller", "service": "turn_on"}')))

    def test_code_word(self):
        a = profile("Carla")
        url = f"http://127.0.0.1:{helpers.HA_PORT}"
        self.assertEqual(a.put("/api/profile/homeassistant", json={"url": url, "token": helpers.HA_TOKEN}).status_code, 200)
        self.assertEqual(a.put("/api/profile/homeassistant/code", json={"code": "abc"}).status_code, 400)
        r = a.put("/api/profile/homeassistant/code", json={"code": "Sonnen Blume"})
        self.assertTrue(r.json()["has_code"])
        self.assertNotIn("Sonnen", r.text + a.get("/api/profile/homeassistant").text)
        # a new connection keeps the code word
        a.put("/api/profile/homeassistant", json={"url": url, "token": ""})
        self.assertTrue(a.get("/api/profile/homeassistant").json()["has_code"])
        cmd = 'TOOL home_assistant_action {"entity_id": "switch.keller", "service": "turn_off"'
        n = len(helpers.HA_CALLS)
        self.assertIn("code word", answer(ask(a, cmd + '}')))
        self.assertIn("code word", answer(ask(a, 'TOOL home_assistant {"command": "Licht aus"}')))
        self.assertEqual(len(helpers.HA_CALLS), n)
        # reading needs no code word
        self.assertIn("Kellerpumpe", answer(ask(a, 'TOOL home_assistant_states {"query": "Kellerpumpe"}')))
        # spoken in the same message (speech recognition may join the words): done, and the model never sees it
        helpers.LLM_CALLS.clear()
        res = answer(ask(a, cmd + ', "x": "sonnenblume!"}'))
        self.assertIn("Kellerpumpe", res)
        self.assertEqual(helpers.HA_CALLS[-1]["service"], "switch.turn_off")
        self.assertNotIn("sonnenblume", json.dumps(helpers.LLM_CALLS).lower())
        self.assertIn("[Codewort]", json.dumps(helpers.LLM_CALLS))
        # nor the stored conversation
        a.put("/api/profile/convos", json={"id": "c1", "title": "x", "msgs": [
            {"role": "user", "content": "Licht aus, Codewort Sonnen Blume"}]})
        self.assertNotIn("Sonnen", json.dumps(a.get("/api/profile/convos").json()))
        # an older message with the code word does not authorize a new change
        n = len(helpers.HA_CALLS)
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "Sonnenblume"},
                                                   {"role": "assistant", "content": "Ok."},
                                                   {"role": "user", "content": cmd + "}"}]})
        self.assertIn("code word", answer(helpers.events(r)))
        self.assertEqual(len(helpers.HA_CALLS), n)
        self.assertFalse(a.put("/api/profile/homeassistant/code", json={"code": ""}).json()["has_code"])


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


class SpeakerId(unittest.TestCase):
    def tearDown(self):
        helpers.set_config(speaker_id=False)

    def test_other_voice_gets_no_history_and_token_works_once(self):
        import speakers
        helpers.set_config(speaker_id=True, public=True)
        x, y = profile("Xaver"), profile("Yvonne")
        y_id = y.get("/api/whoami").json()["profile"]["id"]
        tok = speakers.token(y_id)
        history = [{"role": "user", "content": "Mein Passwort ist geheim"}, {"role": "assistant", "content": "Ok."},
                   {"role": "user", "content": "Hallo"}]
        helpers.LLM_CALLS.clear()
        evs = helpers.events(x.post("/api/chat", json={"messages": history, "speaker": tok}))
        spk = [e for e in evs if e["type"] == "speaker"]
        self.assertEqual(spk[0]["name"], "Yvonne")
        self.assertTrue(spk[0]["foreign"])
        sent = json.dumps(helpers.LLM_CALLS[0]["messages"])
        self.assertNotIn("Passwort ist geheim", sent)       # Xaver's conversation stays with Xaver
        self.assertNotIn("home_assistant", json.dumps(helpers.LLM_CALLS[0].get("tools")))
        evs = helpers.events(x.post("/api/chat", json={"messages": history, "speaker": tok}))
        self.assertFalse([e for e in evs if e["type"] == "speaker"])  # a token picks a profile once only
        # the own voice at the own browser keeps the conversation
        evs = helpers.events(y.post("/api/chat", json={"messages": history, "speaker": speakers.token(y_id)}))
        self.assertFalse([e for e in evs if e["type"] == "speaker"][0]["foreign"])


class Security(unittest.TestCase):
    def setUp(self):
        import guard
        guard.reset()

    tearDown = setUp

    def test_lockout_after_wrong_pins(self):
        profile("Lotte", "5678")
        g = TestClient(panel.app)
        codes = [g.post("/api/profile/login", json={"name": "Lotte", "pin": "0000"}).status_code for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)  # even the right PIN waits now
        self.assertEqual(g.post("/api/profile/login", json={"name": "Lotte", "pin": "5678"}).status_code, 429)
        self.assertEqual(g.post("/api/login", json={"password": "secret-admin"}).status_code, 429)

    def test_foreign_page_cannot_change_anything(self):
        p = profile("Fritz")
        evil = {"origin": "http://other.example:8080"}
        self.assertEqual(p.delete("/api/profile/memory", headers=evil).status_code, 403)
        self.assertEqual(ADMIN.put("/api/config", json={}, headers=evil).status_code, 403)
        self.assertEqual(p.delete("/api/profile/memory", headers={"origin": "http://testserver"}).status_code, 200)
        self.assertEqual(p.delete("/api/profile/memory", headers={"sec-fetch-site": "same-site"}).status_code, 403)
        # scripts without cookies (device key, HTTP Basic) are not affected
        self.assertEqual(TestClient(panel.app).post("/api/chat", headers=evil, json={
            "messages": [{"role": "user", "content": "Hallo"}]}).status_code, 200)

    def test_behind_reverse_proxy(self):
        """Like a proxy in the LAN: other Host, X-Forwarded-*; the page itself still works."""
        p = profile("Paul")
        proxied = {"origin": "https://speech.example.org", "host": "tars:31080", "sec-fetch-site": "same-origin"}
        self.assertEqual(p.delete("/api/profile/memory", headers=proxied).status_code, 200)
        g = TestClient(panel.app, client=("192.168.1.5", 50000))
        for i in range(5):  # another internet address behind the same proxy is not locked out
            g.post("/api/login", json={"password": "x"}, headers={"x-forwarded-for": "203.0.113.9"})
        self.assertEqual(g.post("/api/login", json={"password": "x"}, headers={"x-forwarded-for": "203.0.113.9"}).status_code, 429)
        r = g.post("/api/login", json={"password": "secret-admin"},
                   headers={"x-forwarded-for": "198.51.100.7", "x-forwarded-proto": "https"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("secure", r.headers["set-cookie"].lower())

    def test_logins_expire_and_log_out_everywhere(self):
        a = profile("Ella")
        b = TestClient(panel.app)
        b.post("/api/profile/login", json={"name": "Ella", "pin": "1234"})
        self.assertEqual(a.post("/api/profile/logout-all").status_code, 200)
        self.assertIsNone(b.get("/api/whoami").json()["profile"])
        self.assertEqual(a.get("/api/whoami").json()["profile"]["name"], "Ella")
        u = next(x for x in profiles._load()["users"] if x["name"] == "Ella")
        old = TestClient(panel.app)
        old.cookies.set(profiles.COOKIE, profiles._cookie_value(u, time.time() - 91 * 86400))
        self.assertIsNone(old.get("/api/whoami").json()["profile"])

    def test_secrets_encrypted_on_disk(self):
        import homeassistant
        import vault
        p = profile("Sina")
        r = p.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}",
                                                     "token": helpers.HA_TOKEN})
        self.assertEqual(r.status_code, 200, r.text)
        uid = p.get("/api/whoami").json()["profile"]["id"]
        raw = open(profiles._path(uid, "homeassistant.json")).read()
        self.assertNotIn(helpers.HA_TOKEN, raw)
        self.assertIn(vault.PREFIX, raw)
        self.assertEqual(homeassistant.get(uid)["token"], helpers.HA_TOKEN)
        self.assertNotIn(helpers.HA_TOKEN, p.get("/api/profile/homeassistant").text)

    def test_change_log_and_devices(self):
        p = profile("Theo")
        uid = p.get("/api/whoami").json()["profile"]["id"]
        token = ADMIN.post("/api/admin/devices", json={"name": "Küche", "user": uid}).json()["token"]
        TestClient(panel.app).get("/api/whoami", headers={profiles.DEVICE_HEADER: token})
        dev = p.get("/api/profile/security").json()["devices"]
        self.assertEqual(dev[0]["name"], "Küche")
        self.assertTrue(dev[0]["last"])
        other = profile("Uwe")
        self.assertEqual(other.delete(f"/api/profile/devices/{dev[0]['id']}").status_code, 404)
        self.assertEqual(p.delete(f"/api/profile/devices/{dev[0]['id']}").json()["devices"], [])
        log = ADMIN.get("/api/audit").json()["events"]
        self.assertTrue(any(e.get("path") == "/api/admin/devices" and e.get("who") == "admin" for e in log))
        self.assertTrue(any(e["event"] == "profile_login" and e.get("name") == "Theo" for e in log))
        self.assertEqual(p.get("/api/audit").status_code, 401)


class Stability(unittest.TestCase):
    def test_backup_and_restore(self):
        import io
        import tarfile
        p = profile("Bruno")
        p.post("/api/chat", json={"messages": [{"role": "user", "content": 'TOOL memory_save {"fact": "Bruno mag Kuchen."}'}]})
        facts = lambda: [f["text"] for f in p.get("/api/profile/memory").json()["facts"]]  # noqa: E731
        self.assertIn("Bruno mag Kuchen.", facts())
        b = ADMIN.post("/api/backups").json()
        self.assertEqual(TestClient(panel.app).post("/api/backups").status_code, 401)
        p.delete("/api/profile/memory")
        self.assertEqual(facts(), [])
        r = ADMIN.post(f"/api/backups/{b['name']}/restore")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("users", r.json()["restored"])
        self.assertIn("Bruno mag Kuchen.", facts())
        names = [x["name"] for x in ADMIN.get("/api/backups").json()["backups"]]
        self.assertTrue(any("before-restore" in n for n in names))
        self.assertEqual(ADMIN.get(f"/api/backups/{b['name']}").status_code, 200)
        self.assertEqual(ADMIN.get("/api/backups/..%2Fconfig.json").status_code, 404)
        # a file with anything outside the known places is refused
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name in ("backup.json", "../../etc/evil"):
                info = tarfile.TarInfo(name)
                info.size = 2
                tar.addfile(info, io.BytesIO(b"{}"))
        r = ADMIN.post("/api/backups-upload", files={"file": ("x.tar.gz", buf.getvalue())})
        self.assertEqual(r.status_code, 400)

    def test_watchdog_judges(self):
        import health
        u = "unit-x"
        health._seen.clear()
        self.assertIsNone(health.judge(u, None, 1000, 60))            # just started: grace time
        self.assertIsNone(health.judge(u, None, 1000, 600))
        self.assertIn("antwortet", health.judge(u, None, 1000 + health.HUNG_AFTER, 600))
        health._seen.clear()
        busy = {"status": "ready", "busy": True, "requests": 7}
        self.assertIsNone(health.judge(u, busy, 2000, 600, front=False))
        self.assertIsNone(health.judge(u, busy, 2100, 600, front=False))
        self.assertIn("arbeitet", health.judge(u, busy, 2100 + health.HUNG_AFTER, 600, front=False))
        health._seen.clear()
        health.judge(u, busy, 3000, 600, front=False)
        self.assertIsNone(health.judge(u, dict(busy, requests=8), 3000 + health.HUNG_AFTER, 600, front=False))

    def test_memory_warning(self):
        import health
        health.memory_state.update(low=False)
        health.check_memory(20.0)
        self.assertFalse(health.alerts() and health.alerts()[0]["kind"] == "memory")
        health.check_memory(7.5)
        self.assertEqual(health.alerts()[0]["kind"], "memory")
        self.assertIn("alerts", ADMIN.get("/api/status").json())
        health.check_memory(20.0)
        self.assertFalse(health.memory_state["low"])

    def test_rollback_needs_known_version(self):
        self.assertEqual(ADMIN.post("/api/update/rollback").status_code, 404)
        self.assertEqual(TestClient(panel.app).post("/api/update/rollback").status_code, 401)


if __name__ == "__main__":
    unittest.main()
