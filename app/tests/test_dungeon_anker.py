"""KI-Dungeon-Master: the anchor table (Dominik 2026-10-28 „es kommen zu viele fehler aktuell … mache mir vorschläge“,
Vorschlag 3, „ok“): every field of every JSON answer the model gives the game stands in tests/dungeon_anker.py with
its kind and the fixed check that holds it. A new field without an anchor, an anchor of a field that is gone or a
check that no longer exists turns this test red. Nothing here depends on the clock or on the model.
"""
import contextlib
import glob
import importlib
import io
import os
import unittest

from tests import helpers  # noqa: F401,E402  (sets the paths like every test module)
with contextlib.redirect_stdout(io.StringIO()):
    import dungeon  # noqa: E402
    import dungeon_stimmen  # noqa: E402
from tests.dungeon_anker import ANKER, ARTEN  # noqa: E402

PANEL = os.path.dirname(dungeon.__file__)


def paths(s, pre=""):
    """The field paths of a JSON schema: „a.b“ through objects, „a[].b“ through lists of objects."""
    if s.get("type") == "object" and "properties" in s:
        for k, v in s["properties"].items():
            yield from paths(v, f"{pre}.{k}" if pre else k)
    elif s.get("type") == "array" and isinstance(s.get("items"), dict) and s["items"].get("type") in ("object", "array"):
        yield from paths(s["items"], pre + "[]")
    else:
        yield pre


def leaf(s, path):
    """The schema of one path."""
    for part in path.split("."):
        while s.get("type") == "array":
            s = s["items"]
        s = s["properties"][part.removesuffix("[]")]
    while s.get("type") == "array" and isinstance(s.get("items"), dict):
        s = s["items"]
    return s


def schemas():
    """Every schema the game sends the model: each SCHEMA… of a dungeon module (defined there) and schema_proben,
    without the ones that are part of another (their fields count where they stand)."""
    with contextlib.redirect_stdout(io.StringIO()):
        out = {}
        for f in sorted(glob.glob(os.path.join(PANEL, "dungeon*.py"))):
            m = importlib.import_module(os.path.basename(f)[:-3])
            with open(f, encoding="utf-8") as fh:
                src = fh.read()
            for a in dir(m):
                v = getattr(m, a)
                if a.startswith("SCHEMA") and isinstance(v, dict) and f"\n{a} =" in src:
                    out[f"{m.__name__}.{a}"] = v
        out["dungeon.schema_proben"] = dungeon.schema_proben(dungeon.rules())
    inner = {id(x) for s in out.values() for x in _parts(s) if x is not s}
    return {k: v for k, v in out.items() if id(v) not in inner}


def _parts(s):
    yield s
    for v in (s.get("properties") or {}).values():
        yield from _parts(v)
    if isinstance(s.get("items"), dict):
        yield from _parts(s["items"])


class Anker(unittest.TestCase):
    def test_every_field_of_the_model_has_its_anchor(self):
        got = schemas()
        self.assertEqual(sorted(got), sorted(ANKER), "a schema without its table in tests/dungeon_anker.py, or one gone")
        for k, s in got.items():
            have = set(paths(s))
            self.assertEqual(sorted(have - set(ANKER[k])), [], f"{k}: fields without an anchor")
            self.assertEqual(sorted(set(ANKER[k]) - have), [], f"{k}: anchors of fields that are gone")

    def test_every_anchor_names_its_kind_and_a_check_that_exists(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for k, felder in ANKER.items():
                for path, (art, where) in felder.items():
                    self.assertIn(art, ARTEN, f"{k} {path}")
                    mod, fn = where.rsplit(".", 1)
                    self.assertTrue(callable(getattr(importlib.import_module(mod), fn, None)), f"{k} {path}: {where} is gone")

    def test_a_field_of_a_fixed_list_has_its_list_in_the_schema(self):
        got = schemas()
        for k, felder in ANKER.items():
            for path, (art, _) in felder.items():
                if art == "liste":
                    s = leaf(got[k], path)
                    self.assertTrue("enum" in s or s.get("type") == "boolean", f"{k} {path}: kind liste without an enum")

    def test_a_field_the_narration_must_name_is_dropped_when_it_does_not(self):
        """The anchors of kind erzaehlt that the anchor table closed (2026-10-28): a thing the story never shows stays
        out (the writing: test_dungeon Schrift, the merchant: test_dungeon Bibliothek)."""
        self.assertEqual(ANKER["dungeon.SCHEMA_ERZAEHLEN"]["dinge[].name"][0], "erzaehlt")
        self.assertEqual(ANKER["dungeon.SCHEMA_ERZAEHLEN"]["schriftstueck.titel"][0], "erzaehlt")
        r = dungeon.rules()
        rd = {"plaetze": {}, "lang": "de", "dinge": [], "szene": {"ort": "Keller"}, "ton": r["toene"][0]["id"]}
        with contextlib.redirect_stdout(io.StringIO()) as log:
            ding = [{"name": "Rostige Laterne", "merkmale": "verbeult"}]
            self.assertEqual(dungeon.erz.check_things(dungeon, r, rd, ding, "Im Keller ist es still."), [])
            self.assertEqual(dungeon.erz.check_things(dungeon, r, rd, ding, "Eine rostige Laterne hängt am Haken."), ding)
        self.assertIn("dungeon: dinge | nicht erzaehlt", log.getvalue())


if __name__ == "__main__":
    unittest.main()
