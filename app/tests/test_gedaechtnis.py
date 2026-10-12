"""Gedächtnis mit Beleg und Prüfung (gedaechtnis.py): every fact keeps where it came from, fixed rules (never a
model) mark what may be out of date, nothing is deleted, the model gets the facts in three blocks, off by default."""
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
    def tearDown(self):
        helpers.set_config(memory_check=False)

    def test_off_by_default_and_never_for_guests(self):
        self.assertFalse(features.admin_on("gedpruefen"))
        c, uid = profile("Gedi")
        self.assertFalse(c.get("/api/profile/settings").json()["allow"]["mem_check"])
        d = c.get("/api/profile/memory").json()
        self.assertFalse(d["check"])
        helpers.set_config(memory_check=True)
        self.assertFalse(g.on(uid))                                   # the profile has not switched it on
        self.assertTrue(c.get("/api/profile/settings").json()["allow"]["mem_check"])
        self.assertEqual(TestClient(panel.app).get("/api/profile/memory").status_code, 401)
        self.assertEqual(TestClient(panel.app).post("/api/profile/memory/x/confirm", json={}).status_code, 401)
        self.assertFalse(g.on(None))

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
        self.assertEqual(c.put("/api/profile/settings", json={"mem_check": True}).status_code, 200)
        with profiles._lock:
            profiles._write(profiles._path(uid, "memory.json"), [
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
        self.assertNotIn("Golf", str(snap))
        self.assertNotIn("Tim", str(snap))
        # the switch off: the old single list for the model, no marks for Ich
        helpers.set_config(memory_check=False)
        d = c.get("/api/profile/memory").json()
        self.assertFalse(d["check"])
        self.assertNotIn("mark", d["facts"][0])
        self.assertEqual(c.post("/api/profile/memory/f1/confirm", json={}).status_code, 403)

    def test_model_gets_blocks_only_with_the_switches(self):
        c, uid = profile("Gedd")
        helpers.set_config(memory=True, memory_check=True)
        c.put("/api/profile/settings", json={"mem_check": True})
        with profiles._lock:
            profiles._write(profiles._path(uid, "memory.json"), [
                {"id": "f1", "text": "Fährt einen VW Golf.", "created": int(time.time()) - 400 * DAY, "auto": True}])

        def system():
            helpers.LLM_CALLS.clear()
            r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}], "client": "web", "convo": "g1"})
            self.assertEqual(r.status_code, 200, r.text)
            helpers.events(r)
            return next(x for x in helpers.LLM_CALLS if x.get("stream"))["messages"][0]["content"]
        self.assertIn("Vielleicht veraltet", system())
        c.put("/api/profile/settings", json={"mem_check": False})
        s = system()
        self.assertNotIn("Vielleicht veraltet", s)
        self.assertIn("Fährt einen VW Golf.", s)


class Versions(unittest.TestCase):
    """Fassungen: a correction about the same thing replaces the wording and keeps the old one (at most 5), the
    person can bring an earlier one back; with the switch off a correction is a new fact as before."""
    def tearDown(self):
        helpers.set_config(memory_check=False)

    def test_correction_becomes_a_version(self):
        c, uid = profile("Gedv")
        profiles.remember(uid, "Wohnt in Pforzheim.", src="said")
        profiles.remember(uid, "Wohnt in Karlsruhe.", src="fix", version="fix")       # switch off: a second fact
        self.assertEqual(len(profiles.memory(uid)), 2)
        with profiles._lock:
            profiles._write(profiles._path(uid, "memory.json"), [])
        helpers.set_config(memory=True, memory_check=True)
        c.put("/api/profile/settings", json={"mem_check": True})
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
        self.assertEqual(c2.post(f"/api/profile/memory/{f['id']}/restore", json={"i": 0}).status_code, 403)
        # changing by hand keeps the old wording too
        profiles.change_fact(uid, f["id"], "Wohnt in Bonn-Ost.")
        f = next(x for x in profiles.memory(uid) if x["id"] == f["id"])
        self.assertEqual((f["prev"][0]["text"], f["prev"][0]["why"]), ("Wohnt in Bonn.", "hand"))
        helpers.set_config(memory_check=False)
        self.assertEqual(c.post(f"/api/profile/memory/{f['id']}/restore", json={"i": 0}).status_code, 403)

    def test_without_a_key_a_correction_stays_a_new_fact(self):
        c, uid = profile("Gedx")
        helpers.set_config(memory=True, memory_check=True)
        c.put("/api/profile/settings", json={"mem_check": True})
        profiles.remember(uid, "Mag Tee.", src="said")
        profiles.remember(uid, "Mag Kaffee.", src="fix", version="fix")
        self.assertEqual(len(profiles.memory(uid)), 2)


class Ask(unittest.TestCase):
    """Nachfrage im Gespräch: the panel asks after the answer about a maybe outdated fact that fits the question,
    by fixed rules; once per conversation, three times a day, a yes confirms, „vergiss das“ forgets."""
    def tearDown(self):
        helpers.set_config(memory_check=False, memory_ask=False)

    def setup_profile(self, name):
        c, uid = profile(name)
        helpers.set_config(memory=True, memory_check=True, memory_ask=True)
        self.assertEqual(c.put("/api/profile/settings", json={"mem_check": True, "mem_ask": True}).status_code, 200)
        with profiles._lock:
            profiles._write(profiles._path(uid, "memory.json"), [
                {"id": "g1", "text": "Fährt einen VW Golf.", "created": int(time.time()) - 400 * DAY, "auto": True},
                {"id": "g2", "text": "Mag Tee.", "created": int(time.time()) - 5 * DAY}])
            try:
                import os
                os.remove(profiles._path(uid, "memory-ask.json"))
            except OSError:
                pass
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
            profiles._write(profiles._path(uid, "memory.json"), facts)
        self.assertNotIn("Stimmt das noch", self.say(c, "Wie spät ist es?", "f2"))
        self.assertIn("Stimmt das noch", self.say(c, "Mein Golf GTI?", "f3"))
        self.say(c, "Nein", "f3")                                   # bare no: nothing changes
        self.assertIn("g3", [x["id"] for x in profiles.memory(uid)])
        # three a day at most
        d = g._ask_read(uid)
        d["asked"], d["days"] = {}, {time.strftime("%Y-%m-%d"): g.ASK_DAY}
        profiles._write(g._ask_file(uid), d)
        self.assertNotIn("Stimmt das noch", self.say(c, "Mein Golf GTI?", "f4"))

    def test_a_correction_becomes_a_version(self):
        c, uid = self.setup_profile("Gedk")
        helpers.set_config(learn_fixes=True)
        c.put("/api/profile/settings", json={"fix_learn": True})
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
        c.put("/api/profile/settings", json={"mem_ask": False})
        self.assertNotIn("Stimmt das noch", self.say(c, "Mein Golf?", "n1"))
        c.put("/api/profile/settings", json={"mem_ask": True})
        helpers.set_config(memory_check=False)
        self.assertNotIn("Stimmt das noch", self.say(c, "Mein Golf?", "n2"))
        self.assertFalse(g.ask_on(None))
        self.assertFalse(features.admin_on("gedfragen", {"memory": True, "memory_check": False, "memory_ask": True}))


class Topics(unittest.TestCase):
    """Themen: only from the fixed list, anything else is "sonstiges", the person's own pick stays."""
    def tearDown(self):
        helpers.set_config(memory_check=False, memory_topics=False)

    def test_only_fixed_topics(self):
        got = g.parse_topics('<think>x</think> {"a": "arbeit", "b": "Hacker", "c": 3, "z": "person"}', ["a", "b", "c", "d"])
        self.assertEqual(got, {"a": "arbeit", "b": "sonstiges", "c": "sonstiges", "d": "sonstiges"})
        self.assertEqual(g.parse_topics("kein JSON", ["a"]), {"a": "sonstiges"})

    def test_model_never_overwrites_the_persons_pick(self):
        import asyncio
        c, uid = profile("Gedt")
        helpers.set_config(memory=True, memory_check=True, memory_topics=True)
        self.assertEqual(c.put("/api/profile/settings", json={"mem_check": True, "mem_topics": True}).status_code, 200)
        with profiles._lock:
            profiles._write(profiles._path(uid, "memory.json"), [
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
        c.put("/api/profile/settings", json={"mem_topics": False})
        self.assertIsNone(c.get("/api/profile/memory").json()["topics"])
        self.assertEqual(c.post("/api/profile/memory/t1/topic", json={"topic": "arbeit"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
