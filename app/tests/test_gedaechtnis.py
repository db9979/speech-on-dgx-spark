"""Gedächtnis mit Beleg und Prüfung (gedaechtnis.py): every fact keeps where it came from, fixed rules (never a
model) mark what may be out of date, nothing is deleted, the model gets the facts in three blocks, shipped on
(features.DEFAULT_ON, plan nutzerwissen Frage 1)."""
import contextlib
import io
import time
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402
import gedaechtnis as g  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
DAY = 86400
NOW = time.mktime((2026, 10, 12, 12, 0, 0, 0, 0, -1))   # fixed: the rules never read the clock in a test


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def fact(fid, text, days_ago, src="said", confirmed_days=None, **kw):
    f = {"id": fid, "text": text, "created": int(NOW - days_ago * DAY), "src": src}
    if src == "auto":
        f["auto"] = True
    if confirmed_days is not None:
        f["confirmed"] = int(NOW - confirmed_days * DAY)
    f.update(kw)
    return f


def marks(*facts, months=6):
    return {k: (v["mark"], v["rule"]) for k, v in g.check(list(facts), NOW, months).items()}


class Rules(unittest.TestCase):
    def test_date_passed(self):
        m = marks(fact("a", "Hat am 03.10. Zahnarzttermin.", 14, "auto"),
                  fact("b", "Hat am 14.11. Geburtstag.", 30),                   # a birthday comes back every year
                  fact("c", "Wohnt seit 01.03.2020 in Bad Wildbad.", 300),     # a start never goes out of date
                  fact("d", "Hat am 20.10. ein Konzert.", 3, "auto"),           # still to come
                  fact("e", "Prüfung am 2025-06-30.", 500))
        self.assertEqual(m["a"], ("stale", "datum"))
        self.assertEqual(m["b"], ("ok", ""))
        self.assertEqual(m["c"], ("ok", ""))
        self.assertEqual(m["d"], ("learned", ""))
        self.assertEqual(m["e"], ("stale", "datum"))

    def test_date_in_january_said_in_december_is_next_year(self):
        f = fact("a", "Fliegt am 5.1. nach Rom.", 0, "auto")
        f["created"] = int(time.mktime((2026, 12, 20, 12, 0, 0, 0, 0, -1)))
        self.assertEqual(g.check([f], f["created"] + 5 * DAY)["a"]["mark"], "learned")      # 25.12.: still to come
        self.assertEqual(g.check([f], f["created"] + 20 * DAY)["a"]["mark"], "stale")       # 9.1.: past

    def test_confirmed_after_the_date_is_right(self):
        self.assertEqual(marks(fact("a", "Termin am 03.10. bleibt wichtig.", 14, confirmed_days=2))["a"], ("ok", ""))

    def test_time_words(self):
        m = marks(fact("a", "Ist zurzeit auf Jobsuche.", 120, "auto"), fact("b", "Ist zurzeit auf Jobsuche.", 30, "auto"),
                  fact("c", "Fährt nächste Woche nach Berlin.", 20), fact("d", "Fährt nächste Woche nach Berlin.", 5),
                  fact("e", "Ist zurzeit krank.", 200, confirmed_days=10))   # confirmed lately: counts from then
        self.assertEqual((m["a"], m["b"], m["c"], m["d"], m["e"]),
                         (("stale", "zeitwort"), ("learned", ""), ("stale", "zeitwort"), ("ok", ""), ("ok", "")))

    def test_learned_and_never_confirmed_gets_old(self):
        m = marks(fact("a", "Fährt Rad.", 200, "auto"), fact("b", "Fährt Rad.", 150, "auto"),
                  fact("c", "Mag Tee.", 400), fact("d", "Mag Kaffee.", 400, "auto", confirmed_days=300), months=6)
        self.assertEqual((m["a"], m["b"], m["c"], m["d"]), (("stale", "alt"), ("learned", ""), ("ok", ""), ("ok", "")))
        self.assertEqual(marks(fact("a", "Fährt Rad.", 200, "auto"), months=12)["a"], ("learned", ""))

    def test_contradiction_marks_the_older(self):
        res = g.check([fact("old", "Wohnt in Pforzheim.", 400, "auto"), fact("new", "Wohnt in Bad Wildbad, Garten mit Whirlpool.", 10),
                       fact("bro", "Sein Bruder wohnt in Berlin.", 5),               # someone else: no contradiction
                       fact("car1", "Fährt einen VW Golf.", 300, "auto"), fact("car2", "Fährt jetzt einen Skoda Enyaq.", 2),
                       fact("t1", "Bruder heißt Max.", 100), fact("t2", "Bruder heißt Tim.", 1)], NOW, 6)
        self.assertEqual((res["old"]["mark"], res["old"]["by"]), ("contra", "new"))
        self.assertEqual(res["new"]["mark"], "ok")
        self.assertEqual(res["bro"]["mark"], "ok")
        self.assertEqual((res["car1"]["mark"], res["car2"]["mark"]), ("contra", "ok"))
        self.assertEqual((res["t1"]["mark"], res["t2"]["mark"]), ("contra", "ok"))
        same = g.check([fact("s1", "Wohnt in Pforzheim und arbeitet viel.", 50), fact("s2", "Wohnt in Pforzheim seit Jahren.", 1)], NOW, 6)
        self.assertEqual((same["s1"]["mark"], same["s2"]["mark"]), ("ok", "ok"))   # the same place in other words

    def test_a_confirmed_older_fact_wins_again(self):
        res = g.check([fact("old", "Wohnt in Pforzheim.", 400, confirmed_days=1), fact("new", "Wohnt in Calw.", 10, "auto")], NOW, 6)
        self.assertEqual((res["old"]["mark"], res["new"]["mark"]), ("ok", "contra"))

    def test_old_facts_without_evidence(self):
        self.assertEqual(g.source({"text": "x", "auto": True}), "auto")
        self.assertEqual(g.source({"text": "x"}), "said")
        self.assertEqual(g.confirmed({"text": "x", "created": 5}), 5)
        self.assertEqual(g.confirmed({"text": "x", "created": 5, "auto": True}), 0)

    def test_rules_never_delete(self):
        facts = [fact("a", "Hat am 03.10. Zahnarzttermin.", 14, "auto"), fact("b", "Wohnt in Pforzheim.", 400, "auto"),
                 fact("c", "Wohnt in Calw.", 1)]
        before = [dict(x) for x in facts]
        self.assertEqual(len(g.check(facts, NOW, 6)), 3)
        self.assertEqual(facts, before)


class Prompt(unittest.TestCase):
    def test_three_blocks(self):
        prof = {"id": "x-prompt", "name": "Ina"}
        text = g.hint_lines(prof, [fact("a", "Bruder heißt Tim.", 10), fact("b", "Mag Tee.", 10, "auto"),
                                   fact("c", "Fährt einen VW Golf.", 500, "auto")], NOW)
        sure, rest = text.split("Aus Gesprächen gelernt", 1)
        learned, stale = rest.split("Vielleicht veraltet", 1)
        self.assertIn("Bruder heißt Tim.", sure)
        self.assertIn("Mag Tee.", learned)
        self.assertIn("Fährt einen VW Golf.", stale)
        self.assertIn("NIE als Tatsache", stale)


class Panel(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "memory_check", "deny")

    def test_on_by_default_and_never_for_guests(self):
        import json
        import os
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["memory_check"], True)   # shipped on: fixed rules, nothing leaves the house
        self.assertIn("chat.memory_check", features.DEFAULT_ON)
        c, uid = profile("Gedi")
        helpers.set_config(memory_check=False)                        # the admin can still switch it off
        self.assertFalse(c.get("/api/profile/settings").json()["allow"]["mem_check"])
        d = c.get("/api/profile/memory").json()
        self.assertFalse(d["check"])
        helpers.set_config(memory_check=True)
        self.assertTrue(features.allowed("gedpruefen", uid))                  # released by the admin: on for the profile at once
        self.assertTrue(c.get("/api/profile/settings").json()["allow"]["mem_check"])
        helpers.set_config(deny={"gedpruefen": [uid]})                # the admin blocks this one profile
        self.assertFalse(features.allowed("gedpruefen", uid))
        self.assertFalse(c.get("/api/profile/memory").json()["check"])
        self.assertFalse(c.get("/api/profile/settings").json()["allow"]["mem_check"])
        helpers.set_config(deny={"memory": [uid]})                    # ... or the Gedächtnis it builds on
        self.assertFalse(features.allowed("gedpruefen", uid))
        self.assertEqual(TestClient(panel.app).get("/api/profile/memory").status_code, 401)
        self.assertEqual(TestClient(panel.app).post("/api/profile/memory/x/confirm", json={}).status_code, 401)
        self.assertFalse(features.allowed("gedpruefen", None))

    def test_evidence_kept_even_while_off(self):
        c, uid = profile("Gedb")
        profiles.remember(uid, "Mag Tee.", src="said", convo="abc-1")
        profiles.remember(uid, "Fährt Rad.", auto=True, convo="../evil")
        f = {x["text"]: x for x in profiles.memory(uid)}
        self.assertEqual((f["Mag Tee."]["src"], f["Mag Tee."]["convo"]), ("said", "abc-1"))
        self.assertTrue(f["Mag Tee."]["confirmed"])
        self.assertEqual(f["Fährt Rad."]["src"], "auto")
        self.assertNotIn("convo", f["Fährt Rad."])                   # never a strange conversation id
        self.assertNotIn("confirmed", f["Fährt Rad."])
        profiles.change_fact(uid, f["Fährt Rad."]["id"], "Fährt gern Rad.")
        x = next(y for y in profiles.memory(uid) if y["text"] == "Fährt gern Rad.")
        self.assertEqual(x["src"], "hand")
        self.assertTrue(x["confirmed"])

    def test_marks_and_confirm(self):
        c, uid = profile("Gedc")
        helpers.set_config(memory=True, memory_check=True)
        with profiles._lock:
            profiles.write_own(uid, "memory.json", [
                {"id": "f1", "text": "Fährt einen VW Golf.", "created": int(time.time()) - 400 * DAY, "auto": True},
                {"id": "f2", "text": "Bruder heißt Tim.", "created": int(time.time()) - 5 * DAY}])
        d = c.get("/api/profile/memory").json()
        self.assertTrue(d["check"])
        self.assertEqual(d["months"], 6)
        f = {x["id"]: x for x in d["facts"]}
        self.assertEqual((f["f1"]["mark"], f["f1"]["rule"], f["f1"]["src"]), ("stale", "alt", "auto"))
        self.assertEqual(f["f2"]["mark"], "ok")
        r = c.post("/api/profile/memory/f1/confirm", json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(next(x for x in r.json()["facts"] if x["id"] == "f1")["mark"], "ok")
        self.assertEqual(c.post("/api/profile/memory/nope/confirm", json={}).status_code, 404)
        self.assertEqual(c.post("/api/profile/memory/f1/confirm", content=b"x" * 5000,
                                headers={"Content-Type": "application/json"}).status_code, 413)
        # the Live page: numbers only, never a fact
        g._live[:] = [0.0, None]
        snap = live.snapshot("admin")
        node = next(x for x in snap["targets"] if x["id"] == "ged")
        self.assertIn("Einträge", node["sub"])
        self.assertNotIn("VW Golf", str(snap))
        self.assertNotIn("Bruder heißt Tim", str(snap))   # never a fact ("Tim" alone is in "Timer" of the Weiche)
        # the switch off: the old single list for the model, no marks for Ich
        helpers.set_config(memory_check=False)
        d = c.get("/api/profile/memory").json()
        self.assertFalse(d["check"])
        self.assertNotIn("mark", d["facts"][0])
        self.assertEqual(c.post("/api/profile/memory/f1/confirm", json={}).status_code, 403)

    def test_model_gets_blocks_only_with_the_switches(self):
        c, uid = profile("Gedd")
        helpers.set_config(memory=True, memory_check=True)
        with profiles._lock:
            profiles.write_own(uid, "memory.json", [
                {"id": "f1", "text": "Fährt einen VW Golf.", "created": int(time.time()) - 400 * DAY, "auto": True}])

        def system():
            helpers.LLM_CALLS.clear()
            r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}], "client": "web", "convo": "g1"})
            self.assertEqual(r.status_code, 200, r.text)
            helpers.events(r)
            return next(x for x in helpers.LLM_CALLS if x.get("stream"))["messages"][0]["content"]
        self.assertIn("Vielleicht veraltet", system())
        helpers.set_config(deny={"gedpruefen": [uid]})               # the admin blocks it for this profile
        s = system()
        self.assertNotIn("Vielleicht veraltet", s)
        self.assertIn("Fährt einen VW Golf.", s)


class Versions(unittest.TestCase):
    """Fassungen: a correction about the same thing replaces the wording and keeps the old one (at most 5), the
    person can bring an earlier one back; with the switch off a correction is a new fact as before."""
    def setUp(self):
        helpers.keep_chat(self, "memory_check", "deny")

    def test_correction_becomes_a_version(self):
        c, uid = profile("Gedv")
        helpers.set_config(memory_check=False)
        profiles.remember(uid, "Wohnt in Pforzheim.", src="said")
        profiles.remember(uid, "Wohnt in Karlsruhe.", src="fix", version="fix")       # switch off: a second fact
        self.assertEqual(len(profiles.memory(uid)), 2)
        with profiles._lock:
            profiles.write_own(uid, "memory.json", [])
        helpers.set_config(memory=True, memory_check=True)
        profiles.remember(uid, "Wohnt in Pforzheim.", src="said")
        profiles.remember(uid, "Mag Tee.", src="said")
        for town in ("Karlsruhe", "Ulm", "Bonn", "Kiel", "Jena", "Gera"):
            profiles.remember(uid, f"Wohnt in {town}.", src="fix", version="fix")
        facts = profiles.memory(uid)
        self.assertEqual(len(facts), 2)                                   # still one fact about where he lives
        f = next(x for x in facts if x["text"].startswith("Wohnt"))
        self.assertEqual(f["text"], "Wohnt in Gera.")
        self.assertEqual(len(f["prev"]), profiles.MAX_PREV)               # at most 5 earlier versions
        self.assertEqual((f["prev"][0]["text"], f["prev"][0]["why"]), ("Wohnt in Jena.", "fix"))
        self.assertNotIn("Wohnt in Pforzheim.", [p["text"] for p in f["prev"]])
        # bring one back: it is the wording again, the wording so far is kept
        r = c.post(f"/api/profile/memory/{f['id']}/restore", json={"i": 2})
        self.assertEqual(r.status_code, 200, r.text)
        f = next(x for x in r.json()["facts"] if x["id"] == f["id"])
        self.assertEqual(f["text"], "Wohnt in Bonn.")
        self.assertEqual((f["prev"][0]["text"], f["prev"][0]["why"]), ("Wohnt in Gera.", "zurueck"))
        self.assertEqual(f["src"], "hand")
        for bad in ({"i": 9}, {"i": "1"}, {"i": True}, {}):
            self.assertEqual(c.post(f"/api/profile/memory/{f['id']}/restore", json=bad).status_code, 400)
        self.assertEqual(c.post("/api/profile/memory/nope/restore", json={"i": 0}).status_code, 404)
        self.assertEqual(TestClient(panel.app).post(f"/api/profile/memory/{f['id']}/restore", json={"i": 0}).status_code, 401)
        # another profile never reaches this fact
        c2, _ = profile("Gedw")
        self.assertEqual(c2.post(f"/api/profile/memory/{f['id']}/restore", json={"i": 0}).status_code, 404)
        self.assertEqual(next(x for x in profiles.memory(uid) if x["id"] == f["id"])["text"], "Wohnt in Bonn.")
        # blocked by the admin for this profile: no bringing back
        helpers.set_config(deny={"gedpruefen": [uid]})
        self.assertEqual(c.post(f"/api/profile/memory/{f['id']}/restore", json={"i": 0}).status_code, 403)
        helpers.set_config(deny={})
        # changing by hand keeps the old wording too
        profiles.change_fact(uid, f["id"], "Wohnt in Bonn-Ost.")
        f = next(x for x in profiles.memory(uid) if x["id"] == f["id"])
        self.assertEqual((f["prev"][0]["text"], f["prev"][0]["why"]), ("Wohnt in Bonn.", "hand"))
        helpers.set_config(memory_check=False)
        self.assertEqual(c.post(f"/api/profile/memory/{f['id']}/restore", json={"i": 0}).status_code, 403)

    def test_without_a_key_a_correction_stays_a_new_fact(self):
        c, uid = profile("Gedx")
        helpers.set_config(memory=True, memory_check=True)
        profiles.remember(uid, "Mag Tee.", src="said")
        profiles.remember(uid, "Mag Kaffee.", src="fix", version="fix")
        self.assertEqual(len(profiles.memory(uid)), 2)


class Ask(unittest.TestCase):
    """Nachfrage im Gespräch: the panel asks after the answer about a maybe outdated fact that fits the question,
    by fixed rules; once per conversation, three times a day, a yes confirms, „vergiss das“ forgets."""
    def setUp(self):
        helpers.keep_chat(self, "memory_check", "memory_ask", "deny")

    def setup_profile(self, name):
        c, uid = profile(name)
        helpers.set_config(memory=True, memory_check=True, memory_ask=True)
        with profiles._lock:
            profiles.write_own(uid, "memory.json", [
                {"id": "g1", "text": "Fährt einen VW Golf.", "created": int(time.time()) - 400 * DAY, "auto": True},
                {"id": "g2", "text": "Mag Tee.", "created": int(time.time()) - 5 * DAY}])
            profiles.drop_own(uid, "memory-ask.json")
        return c, uid

    def say(self, c, text, convo):
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "client": "web", "convo": convo})
        self.assertEqual(r.status_code, 200, r.text)
        return "".join(e.get("delta", "") for e in helpers.events(r) if e.get("type") == "text")

    def test_asks_once_and_yes_confirms(self):
        c, uid = self.setup_profile("Geda")
        said = self.say(c, "Wie alt ist mein Golf eigentlich?", "a1")
        self.assertIn("Stimmt das noch: „Fährt einen VW Golf“?", said)
        self.assertEqual(g.pending(uid)["fact"], "g1")
        said = self.say(c, "Ja", "a1")
        self.assertIsNone(g.pending(uid))
        f = next(x for x in profiles.memory(uid) if x["id"] == "g1")
        self.assertTrue(f.get("confirmed"))
        self.assertNotIn("Stimmt das noch", self.say(c, "Und mein Golf?", "a1"))   # once per conversation

    def test_forget_and_limits(self):
        c, uid = self.setup_profile("Gedf")
        self.assertIn("Stimmt das noch", self.say(c, "Mein Golf?", "f1"))
        self.say(c, "Vergiss das", "f1")
        self.assertNotIn("g1", [x["id"] for x in profiles.memory(uid)])
        # a fact asked about once is not asked again within 30 days, a fact that fits no question never
        with profiles._lock:
            facts = profiles.memory(uid) + [{"id": "g3", "text": "Fährt einen Golf GTI.", "created": int(time.time()) - 400 * DAY,
                                             "auto": True}]
            profiles.write_own(uid, "memory.json", facts)
        self.assertNotIn("Stimmt das noch", self.say(c, "Wie spät ist es?", "f2"))
        self.assertIn("Stimmt das noch", self.say(c, "Mein Golf GTI?", "f3"))
        self.say(c, "Nein", "f3")                                   # bare no: nothing changes
        self.assertIn("g3", [x["id"] for x in profiles.memory(uid)])
        # three a day at most
        d = g._ask_read(uid)
        d["asked"], d["days"] = {}, {time.strftime("%Y-%m-%d"): g.ASK_DAY}
        profiles.write_own(uid, "memory-ask.json", d)
        self.assertNotIn("Stimmt das noch", self.say(c, "Mein Golf GTI?", "f4"))

    def test_a_correction_becomes_a_version(self):
        c, uid = self.setup_profile("Gedk")
        helpers.set_config(learn_fixes=True)
        try:
            self.assertIn("Stimmt das noch", self.say(c, "Mein Golf?", "k1"))
            said = self.say(c, "Nein, ich fahre jetzt einen Skoda. FACT Fährt einen Skoda Octavia.", "k1")
            self.assertIn("Soll ich mir merken: Fährt einen Skoda Octavia?", said)
            self.say(c, "Ja", "k1")
            f = next(x for x in profiles.memory(uid) if x["id"] == "g1")
            self.assertEqual(f["text"], "Fährt einen Skoda Octavia.")
            self.assertEqual((f["prev"][0]["text"], f["prev"][0]["why"]), ("Fährt einen VW Golf.", "fix"))
        finally:
            helpers.set_config(learn_fixes=False)

    def test_never_without_the_switches_or_as_guest(self):
        c, uid = self.setup_profile("Gedg")
        helpers.set_config(deny={"gedfragen": [uid]})               # the admin blocks it for this profile
        self.assertNotIn("Stimmt das noch", self.say(c, "Mein Golf?", "n1"))
        self.assertFalse(g.ask_on(uid))
        helpers.set_config(deny={})
        helpers.set_config(memory_check=False)
        self.assertNotIn("Stimmt das noch", self.say(c, "Mein Golf?", "n2"))
        self.assertFalse(g.ask_on(None))
        self.assertFalse(features.admin_on("gedfragen", {"memory": True, "memory_check": False, "memory_ask": True}))


class Topics(unittest.TestCase):
    """Themen: only from the fixed list, anything else is "sonstiges", the person's own pick stays."""
    def setUp(self):
        helpers.keep_chat(self, "memory_check", "memory_topics", "deny")

    def test_only_fixed_topics(self):
        got = g.parse_topics('<think>x</think> {"a": "arbeit", "b": "Hacker", "c": 3, "z": "person"}', ["a", "b", "c", "d"])
        self.assertEqual(got, {"a": "arbeit", "b": "sonstiges", "c": "sonstiges", "d": "sonstiges"})
        self.assertEqual(g.parse_topics("kein JSON", ["a"]), {"a": "sonstiges"})

    def test_model_never_overwrites_the_persons_pick(self):
        import asyncio
        c, uid = profile("Gedt")
        helpers.set_config(memory=True, memory_check=True, memory_topics=True)
        with profiles._lock:
            profiles.write_own(uid, "memory.json", [
                {"id": "t1", "text": "Arbeitet bei Bosch.", "created": int(time.time())},
                {"id": "t2", "text": "Mag Tee.", "created": int(time.time())}])
        r = c.post("/api/profile/memory/t1/topic", json={"topic": "arbeit"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.post("/api/profile/memory/t1/topic", json={"topic": "hacker"}).status_code, 400)
        self.assertEqual(c.post("/api/profile/memory/nope/topic", json={"topic": "arbeit"}).status_code, 404)
        self.assertEqual(TestClient(panel.app).post("/api/profile/memory/t1/topic", json={"topic": "arbeit"}).status_code, 401)
        g._topic_tried.pop(uid, None)
        n = asyncio.run(g.assign_topics(uid))                      # the fake model answers no topic: "sonstiges"
        f = {x["id"]: x for x in profiles.memory(uid)}
        self.assertEqual(n, 1)
        self.assertEqual((f["t1"]["topic"], f["t1"]["topic_by"]), ("arbeit", "hand"))
        self.assertEqual((f["t2"]["topic"], f["t2"]["topic_by"]), ("sonstiges", "model"))
        self.assertEqual(g.set_topics(uid, {"t1": "person"}), 0)  # the model again: the person's pick stays
        self.assertEqual(asyncio.run(g.assign_topics(uid)), 0)    # nothing without a topic, no call within the hour
        d = c.get("/api/profile/memory").json()
        self.assertIn("arbeit", d["topics"])
        helpers.set_config(deny={"gedthemen": [uid]})               # the admin blocks it for this profile
        self.assertIsNone(c.get("/api/profile/memory").json()["topics"])
        self.assertEqual(c.post("/api/profile/memory/t1/topic", json={"topic": "arbeit"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- Feste Plätze (plan nutzerwissen, Stufe 2)
# sentences and the place they fill (None: no place); wrong grabs are the risk of fixed patterns (plan, Risiko 4)
BENCH = (("Wohnt in Pforzheim.", ("wohnort:", "pforzheim")), ("Ina wohnt jetzt in Bad Wildbad.", ("wohnort:", "bad wildbad")),
         ("Sein Bruder wohnt in Berlin.", ("wohnort:bruder", "berlin")), ("Lives in London.", ("wohnort:", "london")),
         ("Wohnt in der Nähe von Ulm.", None), ("Anna wohnt in Ulm.", None),          # no value / someone else by name
         ("Arbeitet bei Bosch.", ("arbeit:", "bosch")), ("Arbeitet als Lehrerin.", ("beruf:", "lehrerin")),
         ("Ist verheiratet mit Eva.", ("partner:", "eva")), ("Hat zwei Kinder.", ("kinder:", "zwei")),
         ("Hat am 14.11. Geburtstag.", ("geburtstag:", "14 11")), ("Ist Vegetarier.", ("ernaehrung:", "vegetarier")),
         ("Hat einen Hund.", ("haustierhund:", "einen")), ("Hat zwei Hunde.", ("haustierhund:", "zwei")),
         ("Hat eine Katze.", ("haustierkatze:", "eine")),                           # a dog and a cat: two places
         ("Fährt jetzt einen Skoda Enyaq.", ("auto:", "skoda enyaq")), ("Bruder heißt Tim.", ("name:bruder", "tim")),
         ("Seine Lieblingsfarbe ist Blau.", ("lieblingsfarbe:", "blau")), ("Mag Tee.", None),
         ("Ist allergisch gegen Nüsse.", None))                                     # allergies add up: no place


def places_of(uid):
    return {p["place"]: p for p in g.places(uid)}


class Places(unittest.TestCase):
    """Feste Plätze: fixed patterns of the panel say which place a fact fills; per place the newest value said or
    corrected wins, the old one is an earlier version (at most 5, grund platz); a learned value never replaces a
    confirmed one, it waits as an offer with a card „Übernehmen / Verwerfen“; the model gets only the newest value."""

    def setUp(self):
        helpers.keep_chat(self, "memory", "memory_check", "reminders", "vorgaenge", "deny")
        helpers.set_config(memory=True, memory_check=True)

    def test_bench(self):
        for text, want in BENCH:
            self.assertEqual(g.slot_of(text, "Ina"), want, text)
        self.assertEqual([k for k, _, _ in g.SLOTS if k in g.ME], list(g.ME))     # every own place is a slot
        self.assertFalse(hasattr(g, "KEYS") or hasattr(g, "key_of"))             # one source: the old list is gone
        self.assertEqual(g.slot_label("wohnort:bruder"), "Wohnort · Bruder")
        self.assertEqual(g.slot_label("lieblingsfarbe:", en=True), "Favourite farbe")
        self.assertEqual(g.slot_base("lieblingsirgendwas:"), "lieblings")      # a log line never takes the rest

    def test_newest_said_value_wins_and_keeps_five(self):
        c, uid = profile("Platz Paula")
        profiles.remember(uid, "Wohnt in Pforzheim.", src="said")
        profiles.remember(uid, "Mag Tee.", src="said")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for town in ("Karlsruhe", "Ulm", "Bonn", "Kiel", "Jena", "Gera"):
                self.assertEqual(profiles.remember(uid, f"Wohnt in {town}.", src="said"), f"Wohnt in {town}.")
        facts = profiles.memory(uid)
        self.assertEqual(len(facts), 2)                                            # one fact holds the place
        f = next(x for x in facts if x["text"].startswith("Wohnt"))
        self.assertEqual(f["text"], "Wohnt in Gera.")
        self.assertEqual(len(f["prev"]), profiles.MAX_PREV)
        self.assertEqual((f["prev"][0]["text"], f["prev"][0]["why"]), ("Wohnt in Jena.", "platz"))
        self.assertIn("gedaechtnis: fassung", out.getvalue())
        self.assertIn("grund=platz", out.getvalue())
        self.assertNotIn("Gera", out.getvalue())                                   # never the fact in the journal
        # someone else's place is a place of its own
        profiles.remember(uid, "Sein Bruder wohnt in Berlin.", src="said")
        self.assertEqual(len(profiles.memory(uid)), 3)
        # the model gets only the value that holds the place, never an earlier version
        hint = g.hint_lines({"id": uid, "name": "Platz Paula"})
        self.assertIn("Wohnt in Gera.", hint)
        self.assertNotIn("Jena", hint)
        # Feste Themen: the own places stand there even while empty, the held one with its versions
        p = places_of(uid)
        self.assertEqual(list(p)[:len(g.ME)], [k + ":" for k in g.ME])
        self.assertEqual((p["wohnort:"]["id"], p["wohnort:"]["prev"]), (f["id"], profiles.MAX_PREV))
        self.assertNotIn("id", p["beruf:"])
        self.assertIn("wohnort:bruder", p)
        # switch off: a second fact beside it as before
        helpers.set_config(memory_check=False)
        profiles.remember(uid, "Wohnt in Gotha.", src="said")
        self.assertEqual(len(profiles.memory(uid)), 4)

    def test_older_contradicting_facts_never_reach_the_model(self):
        prof = {"id": "x-places", "name": "Ina"}
        text = g.hint_lines(prof, [fact("old", "Wohnt in Pforzheim.", 400, "auto"), fact("new", "Wohnt in Calw.", 10)], NOW)
        self.assertIn("Wohnt in Calw.", text)
        self.assertNotIn("Pforzheim", text)

    def test_learned_value_never_replaces_a_confirmed_one(self):
        helpers.set_config(reminders=True, vorgaenge=True)
        import vorgaenge
        c, uid = profile("Platz Pia")
        profiles.remember(uid, "Wohnt in Pforzheim.", src="said")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertIsNone(profiles.remember(uid, "Wohnt in Bad Wildbad.", auto=True, convo="c1"))
        facts = profiles.memory(uid)
        self.assertEqual([x["text"] for x in facts], ["Wohnt in Pforzheim."])     # the said value stays
        self.assertEqual(facts[0]["offer"]["text"], "Wohnt in Bad Wildbad.")
        self.assertRegex(out.getvalue(), r"gedaechtnis: angebot \S.* \| platz=wohnort\n")
        self.assertNotIn("Wildbad", out.getvalue())
        self.assertNotIn("Wildbad", g.hint_lines({"id": uid, "name": "Platz Pia"}))   # an offer never goes to the model
        self.assertEqual(places_of(uid)["wohnort:"]["offer"], "Wohnt in Bad Wildbad.")
        # the card under Offen with Übernehmen / Verwerfen
        card = next(x for x in vorgaenge.view(uid)["items"] if x["art"] == g.CARD)
        self.assertEqual({a["k"] for a in card["acts"]} >= {"gp_nehmen", "gp_weg"}, True)
        self.assertIn(["Neu gelernt", "Wohnt in Bad Wildbad."], card["felder"])
        # the same learned value again: no second card, nothing changes
        self.assertIsNone(profiles.remember(uid, "Wohnt in Bad Wildbad.", auto=True))
        self.assertEqual(len([x for x in vorgaenge.view(uid)["items"] if x["art"] == g.CARD]), 1)
        # Übernehmen on the card: the learned value holds the place, the said one is an earlier version
        r = c.post("/api/profile/vorgaenge/act", json={"id": card["id"], "act": "gp_nehmen", "rev": card["rev"]})
        self.assertEqual(r.status_code, 200, r.text)
        f = profiles.memory(uid)[0]
        self.assertEqual((f["text"], f["src"], f["prev"][0]["why"]), ("Wohnt in Bad Wildbad.", "hand", "gelernt"))
        self.assertNotIn("offer", f)
        self.assertEqual(next(x for x in vorgaenge.view(uid)["items"] if x["art"] == g.CARD)["zustand"], "erledigt")
        # Verwerfen in Ich → Gedächtnis: the value goes and never asks again
        profiles.remember(uid, "Wohnt in Calw.", auto=True)
        self.assertEqual(c.post(f"/api/profile/memory/{f['id']}/offer", json={"do": "drop"}).status_code, 200)
        self.assertNotIn("offer", profiles.memory(uid)[0])
        self.assertIsNone(profiles.remember(uid, "Wohnt in Calw.", auto=True))
        self.assertNotIn("offer", profiles.memory(uid)[0])
        self.assertEqual(c.post(f"/api/profile/memory/{f['id']}/offer", json={"do": "drop"}).status_code, 404)
        # a learned value over a learned one: the newest wins (nothing the person said is touched)
        profiles.remember(uid, "Fährt einen VW Golf.", auto=True)
        profiles.remember(uid, "Fährt einen Skoda Enyaq.", auto=True)
        car = [x for x in profiles.memory(uid) if x["text"].startswith("Fährt")]
        self.assertEqual([x["text"] for x in car], ["Fährt einen Skoda Enyaq."])
        # something said closes a waiting offer and its card
        profiles.remember(uid, "Wohnt in Ulm.", auto=True)
        profiles.remember(uid, "Wohnt in Tübingen.", src="said")
        f = profiles.memory(uid)[0]
        self.assertEqual((f["text"], "offer" in f), ("Wohnt in Tübingen.", False))

    def test_offer_endpoint_checks(self):
        c, uid = profile("Platz Pit")
        profiles.remember(uid, "Arbeitet bei Bosch.", src="said")
        profiles.remember(uid, "Arbeitet bei Siemens.", auto=True)
        fid = profiles.memory(uid)[0]["id"]
        for bad in ({"do": "x"}, {}, {"do": 1}):
            self.assertEqual(c.post(f"/api/profile/memory/{fid}/offer", json=bad).status_code, 400)
        self.assertEqual(TestClient(panel.app).post(f"/api/profile/memory/{fid}/offer", json={"do": "take"}).status_code, 401)
        c2, _ = profile("Platz Pat")
        self.assertEqual(c2.post(f"/api/profile/memory/{fid}/offer", json={"do": "take"}).status_code, 404)
        helpers.set_config(deny={"gedpruefen": [uid]})
        self.assertEqual(c.post(f"/api/profile/memory/{fid}/offer", json={"do": "take"}).status_code, 403)
        helpers.set_config(deny={})
        self.assertEqual(c.post(f"/api/profile/memory/{fid}/offer", content="x" * 4000,
                                headers={"Content-Type": "application/json"}).status_code, 413)
        r = c.post(f"/api/profile/memory/{fid}/offer", json={"do": "take"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(profiles.memory(uid)[0]["text"], "Arbeitet bei Siemens.")
        d = c.get("/api/profile/memory").json()
        self.assertEqual((d["max"], d["warn"], d["full"]), (profiles.MAX_FACTS, profiles.WARN_FACTS, False))
        self.assertEqual(next(p for p in d["places"] if p["place"] == "arbeit:")["text"], "Arbeitet bei Siemens.")


class FullCard(unittest.TestCase):
    """Stufe-1-Rest: „Gedächtnis voll – aufräumen“ as a card under Offen while only protected facts are left; it goes
    by itself when there is room again."""

    def setUp(self):
        helpers.keep_chat(self, "memory", "reminders", "vorgaenge")
        helpers.set_config(memory=True, reminders=True, vorgaenge=True)

    def test_card_comes_and_goes(self):
        import vorgaenge
        c, uid = profile("Voll Vera")
        facts = [{"id": f"{i:08x}", "text": f"Gesagt {i}.", "created": 1_760_000_000 + i, "src": "said",
                  "confirmed": 1_760_000_000 + i} for i in range(profiles.MAX_FACTS)]
        with profiles._lock:
            profiles.write_own(uid, "memory.json", facts)
        profiles._full_said.pop(uid, None)
        self.assertIs(profiles.remember(uid, "Noch etwas.", src="said"), profiles.FULL)
        card = next(x for x in vorgaenge.view(uid)["items"] if x["art"] == g.FULL_CARD)
        self.assertEqual((card["zustand"], card["daten"]["weg"]), ("offen", "Ich → Gedächtnis"))
        self.assertEqual([a["k"] for a in card["acts"]][0], "oeffnen")
        self.assertTrue(c.get("/api/profile/memory").json()["full"])
        profiles.forget(uid, fact_id=facts[0]["id"])
        card = next(x for x in vorgaenge.view(uid)["items"] if x["art"] == g.FULL_CARD)
        self.assertEqual(card["zustand"], "erledigt")
