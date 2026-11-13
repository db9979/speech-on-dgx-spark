"""Steckbrief pro Funktion (steckbrief.py, Kritische Prüfung 2026-11-12 point 4): one place per function, the lists read it.

- every Steckbrief is complete and reaches every list it feeds (features, werkzeuge, Live, logs, Werkzeug-Abdeckung,
  Spickzettel, technik, Begleiter);
- no old table names a part of it again (rule 12: one source);
- a new function comes with a Steckbrief: OHNE_ALT, the functions without one, only shrinks (V01.1.397: all but
  „Rechnen“; V01.1.401: the group „Tempo und Genauigkeit“; V01.1.405: every function without a tool of its own;
  V01.1.406: the last 65, the functions with tools; it is empty now and stays so).

Reads only app/, so it runs in the app/-only copy too. No wall clock dependence.
"""
import ast
import os
import re
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402
import live  # noqa: E402
import logfilter  # noqa: E402
import spickzettel  # noqa: E402
import steckbrief  # noqa: E402
import technik  # noqa: E402
import werkzeug_abdeckung  # noqa: E402
import werkzeuge  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
OHNE_ALT = ()   # V01.1.406: every function has its Steckbrief; stays empty


def source(name):
    with open(os.path.join(PANEL, name), encoding="utf-8") as f:
        return f.read()


class Steckbrief(unittest.TestCase):
    def test_every_steckbrief_reaches_its_lists(self):
        for key, s in steckbrief.STECKBRIEFE.items():
            f = features.BY_KEY[key]
            self.assertEqual((f.de, f.en, f.group, f.admin, f.pref, f.parent, f.me, f.guide),
                             (s.de, s.en, s.gruppe, s.schalter, s.pref, s.parent, s.me, s.anleitung), key)
            self.assertIn(s.gruppe, {g[0] for g in features.GROUPS}, key)
            if s.parent:
                self.assertIn(s.parent, features.BY_KEY, key)
            # a tool or the reason why there is none, never both
            has_tools = bool(s.werkzeuge or s.auch)
            self.assertNotEqual(has_tools, bool(s.ohne_werkzeug), key)
            for tool, names in s.werkzeuge.items():
                self.assertEqual(werkzeuge.NAMES[tool], names, key)
                self.assertEqual(live.TOOLS[tool], s.knoten.get(tool) or s.live[0], key)
            for tool in s.auch:   # a tool of another function: that one has it
                self.assertIn(tool, werkzeuge.NAMES, key)
                self.assertNotIn(tool, s.werkzeuge, key)
            self.assertEqual(sorted(set(s.knoten) - set(s.werkzeuge)), [], key)
            if has_tools:
                self.assertEqual(werkzeug_abdeckung.TOOLS[key], tuple(s.werkzeuge) + s.auch, key)
            else:
                self.assertNotIn(key, werkzeug_abdeckung.TOOLS, key)
                art, why = s.ohne_werkzeug
                self.assertEqual({"regel": werkzeug_abdeckung.RULES, "ohne": werkzeug_abdeckung.WITHOUT}[art][key], why, key)
            if s.live:
                self.assertEqual(live.TARGETS[s.live[0]], s.live[1:5], key)
                self.assertEqual(live.RETURNS[s.live[0]], s.live[5], key)
            if s.log:
                area = dict(logfilter.AREAS)[s.log[0]]
                self.assertRegex(s.log[1] + ": x", area, key)
            for tool, mod in s.eigenes_wort.items():
                self.assertIn(tool, s.werkzeuge, key)
                self.assertEqual(werkzeug_abdeckung.BY_WORD[tool], mod, key)
            for entry in s.kurz:
                self.assertIn(entry[0], set(s.werkzeuge) | set(s.auch), key)
                self.assertIn(entry, spickzettel.KURZ, key)
            for tool, pair in s.saetze.items():
                self.assertIn(tool, set(s.werkzeuge) | set(s.auch), key)
                self.assertEqual(werkzeug_abdeckung.SENTENCES[tool], pair, key)
            if s.begleiter_teile:
                self.assertEqual(features.DESK[key], s.begleiter_teile, key)
                self.assertFalse(s.begleiter, f"{key}: Begleiter parts or the reason why there are none, never both")
            if s.modul:
                self.assertTrue(any(os.path.isfile(os.path.join(d, s.modul[0] + ".py")) for d in (PANEL, os.path.dirname(PANEL))),
                                key)
                self.assertEqual(technik.MODULE[s.modul[0]], s.modul[1:], key)
            if s.begleiter:
                self.assertIn(key, features.DESK_SKIP, key)
                if s.begleiter in ("talk", "voice", "spark", "link", "device", "panel"):
                    self.assertTrue(features.DESK_SKIP[key].startswith(("works", "for speaking", "a setting", "stays",
                                                                        "another")), key)
                else:
                    self.assertEqual(features.DESK_SKIP[key], s.begleiter, key)
            self.assertEqual(key in features.SPARK_ONLY, s.nur_spark, key)

    def test_no_old_table_names_it_again(self):
        """One source: what a Steckbrief holds stands nowhere else as a literal: not as a key or element of the table
        it feeds, not as the first word of an F(...) or of an example sentence."""
        tables = {"features.py": ("FEATURES", "DESK_SKIP", "DESK", "SPARK_ONLY"), "werkzeuge.py": ("NAMES",),
                  "live.py": ("TOOLS", "TARGETS", "RETURNS"), "werkzeug_abdeckung.py": ("TOOLS", "RULES", "WITHOUT", "BY_WORD",
                                                                                         "SENTENCES"),
                  "technik.py": ("MODULE",), "spickzettel.py": ("KURZ",)}
        found = {}
        for name, names in tables.items():
            tree = ast.parse(source(name))
            for node in tree.body:
                targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    targets = [node.target.id]
                if not set(targets) & set(names) or node.value is None:
                    continue
                for n in ast.walk(node.value):
                    lits = []
                    if isinstance(n, ast.Dict):
                        lits = [k for k in n.keys if k is not None]
                    elif isinstance(n, ast.Set):
                        lits = n.elts
                    elif isinstance(n, ast.Tuple) and targets[0] == "KURZ":
                        lits = n.elts[:1]   # (tool, example de, example en)
                    elif isinstance(n, ast.Call) and n.args and not (isinstance(n.func, ast.Attribute)
                                                                     and getattr(n.func.value, "id", "") == "steckbrief"):
                        first = n.args[0]   # F("key", …) or dict.fromkeys(("a", "b"), …)
                        lits = first.elts if isinstance(first, ast.Tuple) else [first]
                    for k in lits:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            found.setdefault(k.value, set()).add(f"{name} {targets[0]}")
        feature_tables = {"features.py FEATURES", "features.py DESK_SKIP", "features.py DESK", "features.py SPARK_ONLY",
                          "werkzeug_abdeckung.py TOOLS", "werkzeug_abdeckung.py RULES", "werkzeug_abdeckung.py WITHOUT"}
        tool_tables = {"werkzeuge.py NAMES", "live.py TOOLS", "werkzeug_abdeckung.py BY_WORD", "werkzeug_abdeckung.py SENTENCES",
                       "spickzettel.py KURZ"}
        for key, s in steckbrief.STECKBRIEFE.items():
            # each name only against the tables that hold that kind of name (a feature's key may also be the name of
            # a Live node of its own, which stays in live.py until the Steckbrief carries it)
            words = [(key, feature_tables)] + [(t, tool_tables) for t in s.werkzeuge] \
                + ([(s.live[0], {"live.py TARGETS", "live.py RETURNS"})] if s.live else []) \
                + ([(s.modul[0], {"technik.py MODULE"})] if s.modul else [])
            for w, where in words:
                self.assertEqual(sorted(found.get(w, set()) & where), [], f"{w} stands there again: it lives in steckbrief.py")
            if s.log:
                self.assertNotRegex(source("logfilter.py"), r"[|(]%s[|)]" % re.escape(s.log[1]), "logfilter names it again")

    def test_a_new_function_comes_with_a_steckbrief(self):
        ohne = set(features.BY_KEY) - set(steckbrief.STECKBRIEFE)
        self.assertEqual(sorted(ohne - set(OHNE_ALT)), [], "a new function needs its Steckbrief in steckbrief.py")
        self.assertEqual(sorted(set(OHNE_ALT) - ohne), [], "these functions have a Steckbrief now (or are gone): take "
                                                          "them out of OHNE_ALT, the list only shrinks")


if __name__ == "__main__":
    unittest.main()
