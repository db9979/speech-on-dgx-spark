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

    def test_unknown_to_assist(self):
        a = profile("Theo")
        url = f"http://127.0.0.1:{helpers.HA_PORT}"
        a.put("/api/profile/homeassistant", json={"url": url, "token": helpers.HA_TOKEN})
        # Assist does not know the TV: found by kind and room among all states and switched directly,
        # not the speaker in the same room nor the TV in another room
        evs = ask(a, 'TOOL home_assistant {"command": "Schalte den Fernseher im Wohnzimmer aus"}')
        self.assertTrue(any(e["type"] == "home_done" and e["ok"] for e in evs), evs)
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.samsung", "service": "media_player.turn_off"})
        # unclear which device: nothing switched, the candidates go back to the model
        n = len(helpers.HA_CALLS)
        res = answer(ask(a, 'TOOL home_assistant {"command": "Schalte den Fernseher aus"}'))
        self.assertIn("media_player.sz_tv", res)
        self.assertEqual(len(helpers.HA_CALLS), n + 1)  # only the Assist attempt

    def test_panel_runs_plain_commands(self):
        a = profile("Rita")
        a.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        import homeassistant
        homeassistant._VERIFY_WAIT = 0.05
        # no tool call by the model needed: the panel switches and the model only gets the checked result
        res = answer(ask(a, "Schalte den T V im Wohnzimmer aus"))
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.samsung", "service": "media_player.turn_off"})
        self.assertIn("done", res)
        # several entities of one device (media_player, remote, art mode switch): the media player
        ask(a, "Schalte Samsung The Frame aus")
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.the_frame", "service": "media_player.turn_off"})
        # the model may name the device instead of its id
        res = answer(ask(a, 'TOOL home_assistant_action {"entity_id": "Samsung The Frame", "service": "media_player.turn_on"}'))
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.the_frame", "service": "media_player.turn_on"})
        # field names as the model on tars wrote them
        ask(a, 'TOOL home_assistant_action {"command": "turn_off", "entity_id": "media_player.the_frame"}')
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.the_frame", "service": "media_player.turn_off"})
        ask(a, 'TOOL home_assistant_action {"action": "einschalten", "entity": "Samsung The Frame"}')
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.the_frame", "service": "media_player.turn_on"})
        n = len(helpers.HA_CALLS)
        ask(a, "Ist das Licht an?")  # a question switches nothing
        ask(a, "Ich habe das Licht an gelassen")  # nor a statement
        ask(a, "Auf Wiedersehen")  # no device named
        self.assertEqual(len(helpers.HA_CALLS), n)
        # with a code word the command waits and runs when the next message brings the word
        a.put("/api/profile/homeassistant/code", json={"code": "Apollo dreizehn"})
        ask(a, "Kannst du bitte die Kellerpumpe einschalten?")
        self.assertEqual(len(helpers.HA_CALLS), n)
        ask(a, "Apollo 13")
        self.assertEqual(helpers.HA_CALLS[-1]["text"], "Kannst du bitte die Kellerpumpe einschalten?")
        n = len(helpers.HA_CALLS)
        ask(a, "Apollo 13")  # the waiting command ran once, not again
        self.assertEqual(len(helpers.HA_CALLS), n)
        a.put("/api/profile/homeassistant/code", json={"code": ""})

    def test_from_ha_mcp(self):
        a = profile("Moritz")
        a.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        import homeassistant
        homeassistant._VERIFY_WAIT = 0.05
        # history: numbers as lowest/highest, other states as changes
        res = answer(ask(a, 'TOOL home_assistant_history {"query": "Temperatur Wohnzimmer", "hours": 24}'))
        self.assertIn("lowest 19.5 °C", res)
        self.assertIn("highest 23 °C", res)
        # a misheard name still finds the device
        ask(a, "Schalte die Kelerpumpe aus")
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "switch.keller", "service": "switch.turn_off"})
        # all lights at once, each checked
        for x in helpers.HA_STATES:
            if x["entity_id"].startswith("light."):
                x["state"] = "on"
        res = answer(ask(a, "Schalte alle Lichter aus"))
        self.assertIn("Flurlampe", res)
        self.assertIn("Licht Küche", res)
        self.assertTrue(all(x["state"] == "off" for x in helpers.HA_STATES if x["entity_id"].startswith("light.")))
        # a room nobody knows never widens "all" to the whole home
        for x in helpers.HA_STATES:
            if x["entity_id"].startswith("light."):
                x["state"] = "on"
        ask(a, "Schalte alle Lichter im Dachboden aus")
        self.assertTrue(all(x["state"] == "on" for x in helpers.HA_STATES if x["entity_id"].startswith("light.")))
        # shopping list: show, add, tick off, each read back
        self.assertIn("Brot", answer(ask(a, 'TOOL home_assistant_todo {"action": "show"}')))
        res = answer(ask(a, 'TOOL home_assistant_todo {"action": "add", "item": "Milch"}'))
        self.assertIn("'Milch' added to Einkaufsliste", res)
        res = answer(ask(a, 'TOOL home_assistant_todo {"action": "done", "item": "brot"}'))
        self.assertIn("'Brot' ticked off", res)
        self.assertEqual(helpers.TODO, {"Brot": "completed", "Milch": "needs_action"})
        # with a code word, changing a list needs it too; reading does not
        a.put("/api/profile/homeassistant/code", json={"code": "Apollo dreizehn"})
        self.assertIn("code word", answer(ask(a, 'TOOL home_assistant_todo {"action": "add", "item": "Eier"}')))
        self.assertNotIn("Eier", helpers.TODO)
        self.assertIn("Milch", answer(ask(a, 'TOOL home_assistant_todo {"action": "show"}')))
        a.put("/api/profile/homeassistant/code", json={"code": ""})
        for x in helpers.HA_STATES:
            if x["entity_id"].startswith("light."):
                x["state"] = "on"

    def test_state_read_back(self):
        a = profile("Vera")
        a.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        import homeassistant
        homeassistant._VERIFY_WAIT = 0.05
        # Home Assistant accepts the call but the device stays on: reported as not done, never as done
        evs = ask(a, 'TOOL home_assistant_action {"entity_id": "switch.kaputt", "service": "turn_off"}')
        self.assertFalse(any(e["type"] == "home_done" and e["ok"] for e in evs))
        res = answer(evs)
        self.assertIn("still 'on'", res)
        self.assertIn("NOT done", res)

    def test_words_before_tool_call(self):
        a = profile("Paula")
        a.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        evs = ask(a, 'PRE TOOL home_assistant_states {"query": "Kellerpumpe"}')
        shown = ""
        for e in evs:
            shown = shown + e.get("delta", "") if e["type"] == "text" else \
                shown[:len(shown) - e["drop"]] if e["type"] == "retract" else shown
        self.assertTrue(shown.startswith("Ergebnis:"), shown)
        res = answer(ask(a, "XML Erzähl was"))
        self.assertNotIn("<", res)
        self.assertIn("Hallo.", res)  # one more round answers instead of stopping mid-way

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
        self.assertIn("code word", answer(ask(a, 'TOOL home_assistant {"command": "Licht dimmen"}')))
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
        # numbers count as words: "Apollo 13" is "Apollo dreizehn"
        a.put("/api/profile/homeassistant/code", json={"code": "Apollo dreizehn"})
        self.assertNotIn("code word", answer(ask(a, cmd + ', "x": "Apollo 13"}')))
        # speech recognition spellings: joined digits, a letter misheard; a different word does not pass
        self.assertNotIn("code word", answer(ask(a, cmd + ', "x": "Apollo13"}')))
        self.assertNotIn("code word", answer(ask(a, cmd + ', "x": "Apolo dreizehen"}')))
        self.assertIn("code word", answer(ask(a, cmd + ', "x": "Apollo vierzehn zwölf"}')))
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


class Errors(unittest.TestCase):
    def _set(self, sec, **kw):
        with open(helpers.os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        old = dict(c[sec])
        c[sec].update(kw)
        with open(helpers.os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
            json.dump(c, f)
        return old

    def test_tts_down_still_gives_the_text(self):
        old = self._set("tts", port=helpers._port())
        try:
            evs = ask(TestClient(panel.app), "Hallo")
        finally:
            self._set("tts", **old)
        self.assertEqual(answer(evs), "Hallo.")
        self.assertEqual([e["code"] for e in evs if e["type"] == "error"], ["tts_down"])

    def test_llm_down_is_named(self):
        old = self._set("chat", llm_url=f"http://127.0.0.1:{helpers._port()}/v1", llm_model="x")
        try:
            evs = ask(TestClient(panel.app), "Hallo")
        finally:
            self._set("chat", **old)
        self.assertEqual([e["code"] for e in evs if e["type"] == "error"], ["llm_down"])


class Push(unittest.TestCase):
    def test_due_reminders_go_to_own_devices_only(self):
        import asyncio
        import push
        a, b = profile("Hanna"), profile("Ida")
        a_id = a.get("/api/whoami").json()["profile"]["id"]
        b_id = b.get("/api/whoami").json()["profile"]["id"]
        sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/x",
               "keys": {"p256dh": push.b64(b"\x04" + b"1" * 64), "auth": push.b64(b"a" * 16)}}
        self.assertEqual(a.post("/api/profile/push", json={"subscription": dict(sub, endpoint="https://evil.example/x")}).status_code, 400)
        push.add(a_id, sub)
        self.assertEqual(len(a.get("/api/profile/push").json()["devices"]), 1)
        self.assertEqual(b.get("/api/profile/push").json()["devices"], [])
        profiles.add_reminder(a_id, "Tee", time.time() * 1000 - 1000)
        profiles.add_reminder(b_id, "Kaffee", time.time() * 1000 - 1000)
        got = []

        async def fake(uid, title, body, tag=""):
            got.append((uid, title))
            return 1
        real, push.send = push.send, fake
        try:
            asyncio.run(push.due_reminders())
        finally:
            push.send = real
        self.assertEqual(got, [(a_id, "⏰ Tee")])
        self.assertEqual(profiles.reminders(a_id), [])
        self.assertEqual(len(profiles.reminders(b_id)), 1)  # no push device: the page rings it


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


class ToolLog(unittest.TestCase):
    def test_own_log_only_and_short_lived(self):
        a, b, g = profile("Lou"), profile("Kim"), TestClient(panel.app)
        answer(ask(a, "TOOL reminder_list {}"))
        answer(ask(a, "Wie geht es dir?"))
        items = a.get("/api/profile/toollog").json()["items"]
        self.assertEqual(items[1]["calls"][0]["name"], "reminder_list")
        self.assertIn("No pending reminders", items[1]["calls"][0]["result"])
        self.assertEqual(items[0]["calls"], [])
        self.assertTrue(items[0]["answer"])
        self.assertEqual(b.get("/api/profile/toollog").json()["items"], [])
        self.assertEqual(g.get("/api/profile/toollog").status_code, 401)
        uid = a.get("/api/whoami").json()["profile"]["id"]
        old = profiles.tool_log(uid)
        old[0]["t"] -= 8 * 86400 * 1000
        profiles._write(profiles._path(uid, "toollog.json"), old)
        self.assertEqual(len(a.get("/api/profile/toollog").json()["items"]), 1)
        a.delete("/api/profile/toollog")
        self.assertEqual(a.get("/api/profile/toollog").json()["items"], [])


class Quick(unittest.TestCase):
    def test_smalltalk_without_tools_and_filler_for_slow_tools(self):
        a = profile("Eli")
        helpers.LLM_CALLS.clear()
        answer(ask(a, "Danke!"))
        self.assertNotIn("tools", helpers.LLM_CALLS[-1])
        evs = ask(a, "TOOL history_search {}")
        kinds = [e["type"] for e in evs]
        # the filler is spoken (audio only) before the answer text arrives
        self.assertLess(kinds.index("tts_request"), kinds.index("text"))
        self.assertEqual(evs[kinds.index("tts_request")]["chars"], len("Ich schaue in unseren früheren Gesprächen nach."))


class Briefing(unittest.TestCase):
    def test_once_a_day_after_the_time_only_with_push(self):
        import asyncio
        import datetime
        import push
        a = profile("Uwe")
        uid = a.get("/api/whoami").json()["profile"]["id"]
        self.assertEqual(a.put("/api/profile/settings", json={"briefing_at": "07:30", "tz": "Europe/Berlin"}).json()
                         ["settings"]["briefing_at"], "07:30")
        self.assertEqual(a.put("/api/profile/settings", json={"briefing_at": "25:00"}).json()["settings"]["briefing_at"],
                         "07:30")
        sent = []

        async def fake_send(u, title, body, tag=""):
            sent.append((u, title, body))
            return 1
        old_send, old_subs = push.send, push.subs
        push.send, push.subs = fake_send, lambda u: [{"endpoint": "x"}] if u == uid else []
        try:
            zone = chat.user_zone("Europe/Berlin")
            run = lambda h, m: asyncio.run(chat.due_briefings(datetime.datetime(2026, 10, 8, h, m, tzinfo=zone)))
            run(7, 0)
            self.assertEqual(sent, [])            # too early
            run(7, 31)
            self.assertEqual([x[0] for x in sent], [uid])
            run(7, 45)
            self.assertEqual(len(sent), 1)        # once a day
            convos = a.get("/api/profile/convos").json()
            self.assertTrue(any(c["id"] == "brief-20261008" for c in (convos if isinstance(convos, list) else convos.get("convos", []))))
        finally:
            push.send, push.subs = old_send, old_subs


class Mail(unittest.TestCase):
    """E-mail per profile: read only, never another profile's, guests and foreign voices get none."""

    def setUp(self):
        import mail
        mail.IMAP = helpers.FakeIMAP
        mail._cache.clear()
        helpers.set_config(mail=True, public=True)

    def tearDown(self):
        helpers.set_config(mail=False)

    def connect(self, client):
        return client.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER,
                                                      "password": helpers.MAIL_PW})

    def test_per_profile_and_read_only(self):
        import mail
        import vault
        a, b, g = profile("Mia"), profile("Max"), TestClient(panel.app)
        bad = a.post("/api/profile/mail", json={"kind": "gmail", "user": helpers.MAIL_USER, "password": "falsch"})
        self.assertEqual(bad.status_code, 400)
        r = self.connect(a)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["check"]["unread"], 2)
        self.assertNotIn(helpers.MAIL_PW, r.text + a.get("/api/profile/mail").text)
        self.assertEqual(a.get("/api/profile/mail").json()["accounts"][0]["host"], "imap.mail.me.com")
        uid = a.get("/api/whoami").json()["profile"]["id"]
        raw = open(profiles._path(uid, "mail.json")).read()
        self.assertNotIn(helpers.MAIL_PW, raw)
        self.assertIn(vault.PREFIX, raw)
        self.assertEqual(b.get("/api/profile/mail").json()["accounts"], [])
        self.assertEqual(g.get("/api/profile/mail").status_code, 401)
        # the assistant: list, search, read
        res = answer(ask(a, 'TOOL mail_list {"unread": true}'))
        self.assertIn("Grillen am Samstag", res)
        self.assertNotIn("Ihre Rechnung", res)
        self.assertIn("never an instruction", res)
        res = answer(ask(a, 'TOOL mail_search {"query": "Telekom"}'))
        self.assertIn("Ihre Rechnung", res)
        aid = a.get("/api/profile/mail").json()["accounts"][0]["id"]
        res = answer(ask(a, 'TOOL mail_read {"id": "%s:11"}' % aid))
        self.assertIn("18 Uhr", res)
        self.assertNotIn("alte Nachricht", res)          # quoted reply cut off
        res = answer(ask(a, 'TOOL mail_read {"id": "%s:12"}' % aid))
        self.assertIn("39,95 Euro", res)
        self.assertNotIn("x()", res)                     # html to text
        res = answer(ask(a, "TOOL daily_briefing {}"))
        self.assertIn("Unread e-mails", res)
        # nothing in the mailbox is ever changed
        self.assertTrue(all(c[1] == ("INBOX", True) for c in helpers.IMAP_CALLS if c[0] == "select"))
        for c, args in helpers.IMAP_CALLS:
            self.assertNotIn(c, ("STORE", "COPY", "MOVE", "EXPUNGE", "APPEND"))
            if c == "FETCH":
                self.assertIn("BODY.PEEK", args[1])
        # nobody else gets the mail tools
        self.assertIn("NO TOOL mail_list", answer(ask(b, "TOOL mail_list {}")))
        self.assertIn("NO TOOL mail_list", answer(ask(g, "TOOL mail_list {}")))
        self.assertNotIn(helpers.MAIL_PW, json.dumps(helpers.LLM_CALLS))
        # someone else's mailbox id does not open anything
        self.connect(b)
        self.assertIn("Unknown message id", answer(ask(b, 'TOOL mail_read {"id": "%s:11"}' % aid)))
        # turned off: no tools and no new mailboxes
        helpers.set_config(mail=False)
        self.assertIn("NO TOOL mail_list", answer(ask(a, "TOOL mail_list {}")))
        self.assertEqual(self.connect(a).status_code, 403)
        mail._cache.clear()

    def test_no_made_up_mail(self):
        a, g = profile("Pia"), TestClient(panel.app)
        helpers.LLM_CALLS.clear()
        answer(ask(g, "Habe ich neue Mails?"))
        sysmsg = helpers.LLM_CALLS[-1]["messages"][0]["content"]
        self.assertIn("keinen Zugriff auf", sysmsg)
        self.assertIn("E-Mails", sysmsg)
        self.assertNotIn("tool_choice", helpers.LLM_CALLS[-1])
        self.connect(a)
        answer(ask(a, "Habe ich neue Mails?"))
        self.assertEqual(helpers.LLM_CALLS[-1]["tool_choice"], "required")
        self.assertNotIn("E-Mails (nicht", helpers.LLM_CALLS[-1]["messages"][0]["content"])
        answer(ask(a, "Wie spät ist es?"))
        self.assertNotIn("tool_choice", helpers.LLM_CALLS[-1])

    def test_reading_mail_turns_off_switching_and_search(self):
        p = profile("Ole")
        self.connect(p)
        p.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        helpers.set_config(mail=True, search=True, search_url="http://127.0.0.1:9")
        helpers.LLM_CALLS.clear()
        ask(p, "TOOL mail_list {}")
        first, after = [{t["function"]["name"] for t in c.get("tools", [])} for c in helpers.LLM_CALLS[:2]]
        self.assertTrue({"home_assistant", "home_assistant_action", "web_search"} <= first)
        self.assertFalse({"home_assistant", "home_assistant_action", "web_search"} & after)
        self.assertIn("home_assistant_states", after)    # reading the home stays possible
        helpers.set_config(search=False, search_url="")

    def test_foreign_voice_gets_no_mail(self):
        import speakers
        helpers.set_config(mail=True, speaker_id=True)
        x, y = profile("Xenia"), profile("Yann")
        self.connect(y)
        tok = speakers.token(y.get("/api/whoami").json()["profile"]["id"])
        helpers.LLM_CALLS.clear()
        helpers.events(x.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}], "speaker": tok}))
        self.assertNotIn("mail_list", json.dumps(helpers.LLM_CALLS[0].get("tools")))
        helpers.set_config(speaker_id=False)

    def test_learner_skips_answers_from_mail(self):
        import recall
        p = profile("Malte")
        p.put("/api/profile/convos", json={"id": "m1", "title": "Mails", "updated": 1, "msgs": [
            {"role": "user", "content": "Was schreibt Anna?"},
            {"role": "assistant", "content": "Anna lädt dich zum Grillen ein.", "mail": True}]})
        prof = p.get("/api/whoami").json()["profile"]
        convo = profiles.convos(prof["id"])[0]
        self.assertTrue(convo["msgs"][1]["mail"])
        text = recall.learn_messages(prof, convo)[1]["content"]
        self.assertNotIn("Grillen", text)


if __name__ == "__main__":
    unittest.main()
