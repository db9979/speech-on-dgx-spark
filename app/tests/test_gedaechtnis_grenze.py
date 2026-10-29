"""Obergrenze des Gedächtnisses ohne stilles Wegwerfen (plan nutzerwissen, Stufe 1, Punkt 4): over profiles.MAX_FACTS
the oldest learned, never confirmed facts go first (profiles._cap); what the person said, corrected, changed, tidied or
confirmed never goes. When only such facts are left, the new fact is refused (profiles.FULL) with a fixed result for
the model, the way to tidy up and one journal line a day. The same cap in memtidy.apply. Times are passed, never read."""
import contextlib
import io
import json
import re
import unittest

from tests import helpers

helpers.start()
import gedaechtnis  # noqa: E402
import memtidy  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import taten  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_760_000_000          # a fixed start: facts get created T0 + i, never the clock


def profile(name, pin="2580"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def said(i, **kw):
    return dict({"id": f"s{i:03d}", "text": f"Gesagt Nummer {i}.", "created": T0 + i, "src": "said",
                 "confirmed": T0 + i}, **kw)


def learned(i, **kw):
    return dict({"id": f"a{i:03d}", "text": f"Gelernt Nummer {i}.", "created": T0 + i, "src": "auto", "auto": True}, **kw)


def put(uid, facts):
    with profiles._lock:
        profiles.write_own(uid, "memory.json", facts)


def journal(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **kw)
    return r, out.getvalue()


class Cap(unittest.TestCase):
    """The rule itself, on lists: who may go, in which order, and that nothing goes when not enough may."""

    def test_under_the_cap_nothing_goes(self):
        facts = [said(i) for i in range(profiles.MAX_FACTS)]
        self.assertEqual(profiles._cap(facts), (facts, 0))

    def test_the_oldest_learned_unconfirmed_go_first(self):
        facts = [said(i) for i in range(profiles.MAX_FACTS - 2)] + [learned(500), learned(300), learned(400)]
        kept, gone = profiles._cap(facts)
        self.assertEqual((len(kept), gone), (profiles.MAX_FACTS, 1))
        self.assertNotIn("a300", [x["id"] for x in kept])                     # the oldest learned one went
        self.assertLessEqual({"a400", "a500"}, {x["id"] for x in kept})
        self.assertEqual(sum(x["src"] == "said" for x in kept), profiles.MAX_FACTS - 2)   # no said fact went

    def test_protected_facts_never_go(self):
        protected = [said(1), said(2, src="fix"), said(3, src="hand"), said(4, src="tidy"),
                     learned(5, confirmed=T0 + 99),                             # learned, then „Stimmt noch“
                     said(6, src=None, confirmed=None)]                         # an old fact without src: said
        for f in protected:
            self.assertFalse(profiles._droppable(f), f["id"])
        self.assertTrue(profiles._droppable(learned(7)))
        self.assertTrue(profiles._droppable({"id": "x", "text": "Alt.", "created": T0, "auto": True}))  # older version
        facts = protected + [said(i) for i in range(10, 10 + profiles.MAX_FACTS)]
        kept, gone = profiles._cap(facts)
        self.assertEqual((kept, gone), (facts, 0))                              # over the cap, but nothing may go

    def test_not_enough_to_drop_means_nothing_goes(self):
        facts = [said(i) for i in range(profiles.MAX_FACTS)] + [learned(900), said(901)]
        kept, gone = profiles._cap(facts)                                       # two over, only one may go
        self.assertEqual((len(kept), gone), (len(facts), 0))

    def test_the_new_fact_itself_is_kept(self):
        new = learned(1)                                                        # the oldest by time, but just added
        facts = [said(i) for i in range(10, 10 + profiles.MAX_FACTS)] + [new]
        self.assertEqual(profiles._cap(facts, keep=new), (facts, 0))

    def test_earlier_versions_do_not_count(self):
        facts = [said(i, prev=[{"text": "früher", "until": T0, "why": "fix"}] * profiles.MAX_PREV)
                 for i in range(profiles.MAX_FACTS)]
        self.assertEqual(profiles._cap(facts), (facts, 0))
        self.assertTrue(profiles.memory_full(None, facts))


class Remember(unittest.TestCase):
    """profiles.remember with a full memory: room from old learned facts, else refused and nothing lost."""

    def setUp(self):
        profiles._full_said.clear()

    def test_201st_fact_takes_the_oldest_learned_place(self):
        c, uid = profile("Grenze Gerda")
        put(uid, [learned(1)] + [said(i) for i in range(2, profiles.MAX_FACTS)] + [learned(2000)])
        self.assertEqual(len(profiles.memory(uid)), profiles.MAX_FACTS)
        saved, log = journal(profiles.remember, uid, "Mag Pflaumenkuchen.", src="said")
        self.assertEqual(saved, "Mag Pflaumenkuchen.")
        ids = [x["id"] for x in profiles.memory(uid)]
        self.assertEqual(len(ids), profiles.MAX_FACTS)
        self.assertNotIn("a001", ids)                                           # the oldest learned one made room
        self.assertIn("a2000", ids)
        self.assertEqual(sum(i.startswith("s") for i in ids), profiles.MAX_FACTS - 2)   # every said fact stayed
        self.assertIn("gedaechtnis: platz frei", log)
        self.assertIn("entfernt=1 grund=alt-gelernt", log)
        self.assertNotIn("Pflaumenkuchen", log)                                # never the fact in the journal
        self.assertNotIn("Grenze Gerda", log)                                  # nor the name without consent

    def test_only_protected_facts_left_refuses_and_keeps_everything(self):
        c, uid = profile("Grenze Gustav")
        before = [said(i) for i in range(profiles.MAX_FACTS - 1)] + [learned(999, confirmed=T0 + 5)]
        put(uid, before)
        self.assertTrue(profiles.memory_full(uid))
        for src in ("said", "fix", "auto"):
            r, log = journal(profiles.remember, uid, f"Neu {src}.", src=src)
            self.assertIs(r, profiles.FULL)
            self.assertFalse(r)                                                 # falsy: no caller counts it as saved
            self.assertEqual(profiles.memory(uid), before)                      # nothing lost, nothing added
            if src == "said":
                self.assertRegex(log, r"^gedaechtnis: voll \S.* \| abgelehnt=said max=\d+ \| next log in 24 h\n$")
            else:
                self.assertEqual(log, "")                                       # once a day, not per refusal
        # a correction about a fixed key still becomes a new version: it takes no place
        helpers.keep_chat(self, "memory_check")
        helpers.set_config(memory=True, memory_check=True)
        put(uid, [said(i) for i in range(profiles.MAX_FACTS - 1)] + [said(999, text="Wohnt in Pforzheim.")])
        self.assertEqual(profiles.remember(uid, "Wohnt in Calw.", src="fix", version="fix"), "Wohnt in Calw.")
        self.assertEqual(len(profiles.memory(uid)), profiles.MAX_FACTS)

    def test_learning_by_itself_never_pushes_out_a_said_fact(self):
        c, uid = profile("Grenze Greta")
        before = [said(i) for i in range(profiles.MAX_FACTS)]
        put(uid, before)
        self.assertIs(profiles.remember(uid, "Gelernt neu.", auto=True), profiles.FULL)
        self.assertEqual(profiles.memory(uid), before)

    def test_the_log_line_starts_with_an_area_word(self):
        import logfilter
        c, uid = profile("Grenze Gisela")
        put(uid, [said(i) for i in range(profiles.MAX_FACTS)])
        _, log = journal(profiles.remember, uid, "Noch etwas.", src="said")
        self.assertTrue(any(re.match(rx, log) for _, rx in logfilter.AREAS), log)   # a filterable area (gedaechtnis:)


class Tool(unittest.TestCase):
    """memory_save in a conversation: the fixed „Not done“ result with the way to tidy up, no „saved“ event."""

    def test_full_text_is_a_failure_with_the_way(self):
        self.assertTrue(taten.FAILED.match(profiles.FULL_TEXT))
        self.assertIn("Ich → Gedächtnis", profiles.FULL_TEXT)
        self.assertIn(str(profiles.MAX_FACTS), profiles.FULL_TEXT)

    def test_memory_save_says_full(self):
        helpers.keep_chat(self, "memory")
        helpers.set_config(memory=True)
        c, uid = profile("Grenze Gunda")
        before = [said(i) for i in range(profiles.MAX_FACTS)]
        put(uid, before)
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": 'TOOL memory_save {"fact": "Mag Quitten."}'}]})
        self.assertEqual(r.status_code, 200, r.text)
        evs = helpers.events(r)
        self.assertFalse([e for e in evs if e.get("type") == "memory" and e.get("action") == "saved"])
        tool = next(m for m in helpers.LLM_CALLS[-1]["messages"] if m["role"] == "tool")
        self.assertTrue(tool["content"].startswith("Not done: the memory is full"), tool["content"])
        self.assertEqual(profiles.memory(uid), before)

    def test_guests_have_no_memory_to_fill(self):
        g = TestClient(panel.app)
        self.assertEqual(g.get("/api/profile/memory").status_code, 401)


class Tidy(unittest.TestCase):
    """memtidy.apply caps the same way: a tidy-up never cuts a said fact off at the end."""

    def tidy(self, uid, prop):
        profiles._write(memtidy._file(uid, "memory-tidy.json"), dict(prop, created=T0))
        return journal(memtidy.apply, uid)

    def test_over_the_cap_only_learned_go(self):
        c, uid = profile("Grenze Gregor")
        put(uid, [learned(1), learned(2)] + [said(i) for i in range(10, 11 + profiles.MAX_FACTS)])   # 203, from before
        (n, log) = self.tidy(uid, {"merge": [], "drop": [{"id": "s010", "why": "alt"}]})
        ids = [x["id"] for x in profiles.memory(uid)]
        self.assertEqual(len(ids), profiles.MAX_FACTS)
        self.assertFalse({"a001", "a002", "s010"} & set(ids))
        self.assertEqual(n, 3)
        self.assertIn("entfernt=2 grund=alt-gelernt", log)

    def test_only_said_facts_all_stay(self):
        c, uid = profile("Grenze Gesine")
        put(uid, [said(i) for i in range(profiles.MAX_FACTS + 2)])               # 202 said ones from before
        n, _ = self.tidy(uid, {"merge": [], "drop": [{"id": "s000", "why": "alt"}]})
        ids = [x["id"] for x in profiles.memory(uid)]
        self.assertEqual((n, len(ids)), (1, profiles.MAX_FACTS + 1))           # only the one she accepted went
        self.assertIn("s001", ids)                                               # the oldest said one stays


class Live(unittest.TestCase):
    """Live: profiles with a full memory as a number, never a fact."""

    def test_full_profiles_counted(self):
        import live
        helpers.keep_chat(self, "memory", "memory_check")
        helpers.set_config(memory=True, memory_check=True)
        c, uid = profile("Grenze Gerold")
        put(uid, [said(i, text=f"Geheimer Satz {i}.") for i in range(profiles.MAX_FACTS)])
        gedaechtnis._live[:] = [0.0, None]
        self.assertGreaterEqual(gedaechtnis.for_live()["full"], 1)
        gedaechtnis._live[:] = [0.0, None]
        snap = live.snapshot("admin")
        node = next(x for x in snap["targets"] if x["id"] == "ged")
        self.assertIn("voll", node["sub"])
        self.assertNotIn("Geheimer Satz", json.dumps(snap))


if __name__ == "__main__":
    unittest.main()
