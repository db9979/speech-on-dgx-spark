"""Rückfrage statt Raten, Korrektur und Merken (klaeren.py, plan „Rückfrage, Korrektur und Merken“).

The Fernseher case of 2026-10-12 and what follows from it: the panel asks which device when several fit or none,
takes the answer by fixed rules (button, number, name), carries out the choice with the code word of the command
it answers, offers to remember it, and "Nein, den anderen" takes a choice back. Never the model, never guests,
never from another conversation or after the time is up.
"""
import json
import os
import unittest

from tests import helpers
from tests.test_panel import ADMIN, answer, ask, profile

import klaeren  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import homeassistant  # noqa: E402
import profiles  # noqa: E402

CODE = "Apollo dreizehn"


def choices(evs):
    return [e for e in evs if e["type"] == "choice"]


def state(eid):
    return next(x for x in helpers.HA_STATES if x["entity_id"] == eid)


class Klaeren(unittest.TestCase):
    def setUp(self):
        homeassistant._VERIFY_WAIT = 0.05
        helpers.set_config(klaeren=True, klaeren_merken=True)
        self.box = {"entity_id": "media_player.wz_appletv", "state": "off", "attributes": {"friendly_name": "Apple TV Wohnzimmer"}}
        helpers.HA_STATES.append(self.box)
        self.saved = {x["entity_id"]: x["state"] for x in helpers.HA_STATES}

    def tearDown(self):
        helpers.HA_STATES.remove(self.box)
        for x in helpers.HA_STATES:
            x["state"] = self.saved.get(x["entity_id"], x["state"])
        helpers.set_config(klaeren=False, klaeren_merken=False, deny={})
        klaeren._waiting.clear()
        klaeren._last.clear()

    def person(self, name):
        a = profile(name)
        a.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        a.put("/api/profile/homeassistant/code", json={"code": CODE})
        return a, a.get("/api/whoami").json()["profile"]["id"]

    def test_off_by_default_and_never_for_guests(self):
        helpers.set_config(klaeren=False, klaeren_merken=False)
        a, uid = self.person("Kla Aus")
        self.assertFalse(a.get("/api/profile/settings").json()["allow"]["klaeren"])
        evs = ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        self.assertEqual(choices(evs), [])
        self.assertNotIn(uid, klaeren._waiting)
        self.assertEqual(a.get("/api/profile/zuordnungen").status_code, 403)
        helpers.set_config(klaeren=True)
        b, uid_b = self.person("Kla Profil aus")
        helpers.set_config(deny={"klaeren": [uid_b]})   # the admin allows it, but blocks it for this one profile
        self.assertFalse(b.get("/api/profile/settings").json()["allow"]["klaeren"])
        self.assertEqual(choices(ask(b, f"Schalte den Fernseher aus Codewort {CODE}")), [])
        self.assertNotIn(uid_b, klaeren._waiting)
        self.assertEqual(b.get("/api/profile/zuordnungen").status_code, 403)
        helpers.set_config(deny={})                      # released: it asks back at once
        self.assertTrue(b.get("/api/profile/settings").json()["allow"]["klaeren"])
        guest = TestClient(panel.app)   # no profile: no mappings
        self.assertIn(guest.get("/api/profile/zuordnungen").status_code, (401, 403))

    def test_asks_then_switches_the_choice_and_remembers(self):
        a, uid = self.person("Kla Eins")
        n = len(helpers.HA_CALLS)
        evs = ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        ch = choices(evs)
        self.assertEqual(len(ch), 1, evs)
        labels = [o["label"] for o in ch[0]["options"]]
        self.assertIn("Samsung The Frame", labels)
        self.assertLessEqual(len(labels), klaeren.MAX_BUTTONS)
        self.assertEqual(len(helpers.HA_CALLS), n + 1)   # only the Assist attempt: nothing switched
        res = answer(evs)
        self.assertIn("Welches meinst du?", res)
        self.assertIn("Call no tool", res)
        # the answer: a name, without the code word again
        evs = ask(a, "den Samsung The Frame")
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.the_frame", "service": "media_player.turn_off"})
        self.assertEqual(state("media_player.the_frame")["state"], "off")
        rem = choices(evs)
        self.assertEqual(rem and rem[0].get("kind"), "remember", evs)
        self.assertIn("Soll ich mir merken", answer(evs))
        ask(a, "Ja")
        maps = a.get("/api/profile/zuordnungen").json()["items"]
        self.assertEqual([(m["words"], m["id"]) for m in maps], [("fernseher", "media_player.the_frame")])
        # from now on the same words switch that device straight away, without asking Assist
        state("media_player.the_frame")["state"] = "on"
        n = len(helpers.HA_CALLS)
        evs = ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        self.assertEqual(choices(evs), [])
        self.assertEqual(helpers.HA_CALLS[n:], [{"entity_id": "media_player.the_frame", "service": "media_player.turn_off"}])
        # the code word never reaches the stored mapping
        with open(profiles._path(uid, "zuordnungen.json")) as f:
            self.assertNotIn("apollo", f.read().lower())
        # a mapping needs the code word all the same: without it the command waits as before
        n = len(helpers.HA_CALLS)
        ask(a, "Schalte den Fernseher an")
        self.assertEqual(len(helpers.HA_CALLS), n)

    def test_switches_go_into_the_diary_without_the_code_word(self):
        """Spark-Tagebuch (tagebuch.py): a choice, a correction and a remembered mapping each note the device and
        the action under "geraet", never the sentence with the code word; nothing while the diary is off."""
        import tagebuch
        a, uid = self.person("Kla Tagebuch")
        ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        ask(a, "den Samsung The Frame")
        self.assertEqual(tagebuch.recent(uid), [])   # diary off: nothing noted
        helpers.set_config(tagebuch=True)
        try:
            profiles.save_settings(uid, {"tagebuch_on": True})
            state("media_player.the_frame")["state"] = "on"
            ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
            ask(a, "den Samsung The Frame")
            rows = tagebuch.recent(uid, art="geraet")
            self.assertEqual([r["title"] for r in rows], ["Samsung The Frame ausgeschaltet"])
            with open(profiles._path(uid, "tagebuch.json")) as f:
                self.assertNotIn("apollo", f.read().lower())
        finally:
            helpers.set_config(tagebuch=False)

    def test_number_answer_and_no(self):
        a, uid = self.person("Kla Zwei")
        evs = ask(a, f"Schalte den Fernseher an Codewort {CODE}")
        opts = choices(evs)[0]["options"]
        evs = ask(a, "die zweite")
        self.assertEqual(helpers.HA_CALLS[-1]["service"], "media_player.turn_on")
        chosen = helpers.HA_CALLS[-1]["entity_id"]
        self.assertEqual(state(chosen)["attributes"]["friendly_name"], opts[1]["label"])
        ask(a, "Nein")
        self.assertEqual(a.get("/api/profile/zuordnungen").json()["items"], [])

    def test_choice_only_here_and_now(self):
        a, uid = self.person("Kla Drei")
        ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        n = len(helpers.HA_CALLS)
        ask(a, "den Samsung The Frame", convo="anderes")   # another conversation: no answer to this question
        self.assertFalse(any(c.get("entity_id") == "media_player.the_frame" for c in helpers.HA_CALLS[n:]))
        ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        klaeren._waiting[uid]["t"] -= klaeren.ASK_SECONDS + 1   # too late
        n = len(helpers.HA_CALLS)
        ask(a, "den Samsung The Frame")
        self.assertFalse(any(c.get("entity_id") == "media_player.the_frame" for c in helpers.HA_CALLS[n:]))
        # another profile cannot answer the first one's question
        ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        b, _ = self.person("Kla Vier")
        n = len(helpers.HA_CALLS)
        ask(b, "den Samsung The Frame")
        self.assertFalse(any(c.get("entity_id") == "media_player.the_frame" for c in helpers.HA_CALLS[n:]))

    def test_none_of_these_gives_the_list_and_a_pick_from_it(self):
        a, uid = self.person("Kla Liste")
        ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        evs = ask(a, "Keins davon")
        ch = choices(evs)
        self.assertTrue(ch and ch[0]["list"], evs)
        labels = [o["label"] for o in ch[0]["options"]]
        self.assertIn("Kellerpumpe", labels)
        self.assertNotIn("Haustür", labels)   # locks are never offered
        state("switch.keller")["state"] = "on"
        ask(a, "Kellerpumpe")
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "switch.keller", "service": "switch.turn_off"})

    def test_only_some_words_fit_then_the_whole_list(self):
        a, uid = self.person("Kla Glotze")
        n = len(helpers.HA_CALLS)
        evs = ask(a, f"Mach die Glotze im Dachboden an Codewort {CODE}")   # TVs, but no attic
        ch = choices(evs)
        self.assertTrue(ch and not ch[0]["list"], evs)
        self.assertIn("Das finde ich so nicht genau. Meinst du", answer(evs))
        self.assertIn("Samsung", [o["label"] for o in ch[0]["options"]])
        self.assertFalse([c for c in helpers.HA_CALLS[n:] if "service" in c])   # nothing switched
        evs = ask(a, "Keins davon")
        ch = choices(evs)
        self.assertTrue(ch and ch[0]["list"], evs)
        self.assertIn("Such dir das Richtige aus der Liste aus", answer(evs))

    def test_no_the_other_one_takes_it_back(self):
        a, uid = self.person("Kla Korrektur")
        state("media_player.samsung")["state"] = "off"
        # the TV wins over the box without device class (V01.0.458), both stay candidates
        ask(a, f"Schalte den Fernseher im Wohnzimmer ein Codewort {CODE}")
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.samsung", "service": "media_player.turn_on"})
        self.assertEqual(state("media_player.samsung")["state"], "on")
        evs = ask(a, "Nein, ich meinte das Apple TV")
        self.assertIn({"entity_id": "media_player.samsung", "service": "media_player.turn_off"}, helpers.HA_CALLS[-2:])
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "media_player.wz_appletv", "service": "media_player.turn_on"})
        self.assertEqual(state("media_player.samsung")["state"], "off")
        self.assertEqual(state("media_player.wz_appletv")["state"], "on")
        self.assertIn("Soll ich mir merken", answer(evs))

    def test_endpoints(self):
        a, uid = self.person("Kla Hand")
        ziele = a.get("/api/profile/zuordnungen/ziele?area=ha").json()["items"]
        self.assertIn("media_player.samsung", [z["id"] for z in ziele])
        self.assertNotIn("lock.haustuer", [z["id"] for z in ziele])
        r = a.post("/api/profile/zuordnungen", json={"area": "ha", "words": "Glotze im Keller", "id": "switch.keller"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["words"], "glotze keller")
        self.assertEqual(a.post("/api/profile/zuordnungen", json={"area": "ha", "words": "Tür", "id": "lock.haustuer"}).status_code, 400)
        self.assertEqual(a.post("/api/profile/zuordnungen", json={"area": "ha", "words": "x" * 200, "id": "switch.keller"}).status_code, 400)
        self.assertEqual(a.post("/api/profile/zuordnungen", content=b"{" + b" " * 5000 + b"}").status_code, 413)
        mid = r.json()["mid"]
        self.assertEqual(a.put(f"/api/profile/zuordnungen/{mid}", json={"words": "Keller Glotze bitte"}).json()["words"], "glotze keller")
        # a device key may read, never change
        key = profiles.add_device("Kla Uhr", uid)
        dev = TestClient(panel.app, headers={profiles.DEVICE_HEADER: key})
        self.assertEqual(dev.delete(f"/api/profile/zuordnungen/{mid}").status_code, 403)
        state("switch.keller")["state"] = "off"
        ask(a, f"Mach die Glotze im Keller an Codewort {CODE}")
        self.assertEqual(helpers.HA_CALLS[-1], {"entity_id": "switch.keller", "service": "switch.turn_on"})
        self.assertEqual(a.delete(f"/api/profile/zuordnungen/{mid}").status_code, 200)
        self.assertEqual(a.get("/api/profile/zuordnungen").json()["items"], [])

    def test_live_and_journal_have_numbers_only(self):
        import live
        a, uid = self.person("Kla Live")
        ask(a, f"Schalte den Fernseher aus Codewort {CODE}")
        t = next(x for x in live.snapshot()["targets"] if x["id"] == "klaeren")
        self.assertNotIn("Frame", t["sub"])
        self.assertIn("1 Fragen offen", t["sub"])

    def test_which_list_is_asked_and_remembered(self):
        """Stufe C: "die Einkaufliste" fits two lists and names neither exactly: the panel asks instead of taking the
        first; the choice shows that list (the code word of the request goes with a change), a yes remembers it."""
        extra = {"entity_id": "todo.baumarkt", "state": "0", "attributes": {"friendly_name": "Einkauf Baumarkt"}}
        helpers.HA_STATES.append(extra)
        try:
            a, uid = self.person("Kla Liste2")
            evs = ask(a, 'TOOL home_assistant_todo {"action": "show", "list": "Einkauf"}')
            ch = choices(evs)
            self.assertEqual(sorted(o["label"] for o in ch[0]["options"]), ["Einkauf Baumarkt", "Einkaufsliste"])
            self.assertIn("Da passen mehrere", answer(evs))
            n = len(helpers.HA_CALLS)
            evs = ask(a, "Baumarkt")
            self.assertIn({"entity_id": "todo.baumarkt", "service": "todo.get_items"}, helpers.HA_CALLS[n:])
            self.assertIn("Soll ich mir merken", answer(evs))
            ask(a, "Ja")
            self.assertEqual([(m["area"], m["id"]) for m in klaeren.load(uid)], [("liste", "todo.baumarkt")])
            n = len(helpers.HA_CALLS)
            evs = ask(a, 'TOOL home_assistant_todo {"action": "show", "list": "Einkauf"}')
            self.assertEqual(choices(evs), [])
            self.assertIn({"entity_id": "todo.baumarkt", "service": "todo.get_items"}, helpers.HA_CALLS[n:])
            # a change: the code word of the request goes with the choice, never without one
            klaeren._save(uid, [])
            n = len(helpers.HA_CALLS)
            ask(a, 'TOOL home_assistant_todo {"action": "add", "list": "Einkauf", "item": "Schrauben"}')
            self.assertEqual(choices(ask(a, "Baumarkt")), [])
            self.assertFalse([c for c in helpers.HA_CALLS[n:] if c.get("service") == "todo.add_item"])
            ask(a, f'TOOL home_assistant_todo {{"action": "add", "list": "Einkauf", "item": "Schrauben", "x": "Codewort {CODE}"}}')
            ask(a, "Baumarkt")
            self.assertIn({"entity_id": "todo.baumarkt", "item": "Schrauben", "service": "todo.add_item"}, helpers.HA_CALLS[n:])
            helpers.TODO.pop("Schrauben", None)
        finally:
            helpers.HA_STATES.remove(extra)

    def test_telegram_keyboard_from_a_choice(self):
        import telegram
        kb = telegram.keyboard({"options": [{"label": "Samsung", "room": "Wohnzimmer"}, {"label": "TV", "room": ""},
                                            {"label": "Ja, merken", "send": "Ja", "room": "x"}], "none": "Keins davon"})
        self.assertEqual([r[0]["text"] for r in kb["keyboard"]], ["Samsung Wohnzimmer", "TV", "Ja", "Keins davon"])
        self.assertTrue(kb["one_time_keyboard"])
        self.assertIsNone(telegram.keyboard({"options": [], "none": ""}))

    def test_same_conversation_only(self):
        self.assertFalse(klaeren._same("web:", "web:abc"))
        self.assertTrue(klaeren._same("web:abc", "web:abc"))
        self.assertFalse(klaeren._same("web:abc", "web:xyz"))
        self.assertFalse(klaeren._same("web:", "telegram:"))
        self.assertFalse(klaeren._same("ios:abc", "web:abc"))

    def test_words_and_pick(self):
        self.assertEqual(klaeren.words("Schalte den Fernseher im Wohnzimmer ein [Codewort]"), "fernseher wohnzimmer")
        self.assertEqual(klaeren.words("Fernseher im Wohnzimmer an, Codewort ist [Codewort]"), "fernseher wohnzimmer")
        c = [{"id": "a", "name": "Samsung", "room": "Wohnzimmer"}, {"id": "b", "name": "Apple TV Wohnzimmer", "room": ""}]
        self.assertEqual(klaeren.pick("den Samsung", c)["id"], "a")
        self.assertEqual(klaeren.pick("zwei", c)["id"], "b")
        self.assertEqual(klaeren.pick("die erste", c)["id"], "a")
        self.assertIsNone(klaeren.pick("Wohnzimmer", c))   # fits both: no choice
        self.assertIsNone(klaeren.pick("Toaster", c))


if __name__ == "__main__":
    unittest.main()
