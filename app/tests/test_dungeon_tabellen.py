"""KI-Dungeon-Master: the tables of the table page against the panel's tables (Dominik 2026-10-28 „es kommen zu viele
fehler aktuell … mache mir vorschläge“, Vorschlag 4, „ok“). The page names a check's level, a rarity, a kind of damage
or a settlement's service by its own small tables (dungeon*.js); each one must know every value the panel sends, and
every reason the panel refuses with has its sentence on the page (or one of the general ones). The Alte-Bibliothek
round showed why: the card said „mittel“, the dice bar „leicht“. Nothing here depends on the clock or on the model.
"""
import contextlib
import glob
import io
import os
import re
import unittest

from tests import helpers  # noqa: F401,E402  (sets the paths like every test module)
with contextlib.redirect_stdout(io.StringIO()):
    import dungeon  # noqa: E402
    import dungeon_balance  # noqa: E402
    import dungeon_gold  # noqa: E402
    import dungeon_ideen  # noqa: E402
    import dungeon_karte  # noqa: E402
    import dungeon_regelseite  # noqa: E402

PANEL = os.path.dirname(dungeon.__file__)
JS = os.path.join(PANEL, "static", "js")
# reasons the page answers with its general sentences (errSay: a status of its own) and never with one of its own
ALLGEMEIN = {"zu oft": "429, errSay", "not from another site": "403, CSRF of every page",
             "eigene": "400, the rules form sends its own list of faults (check_rules)",
             "teil": "404, a part of the rules page that does not exist: only a wrong address",
             "id": "400, an id the rules page never sends: only a wrong address",
             "wert": "dungeon_wappen.Nein: the coat of arms form shows its own field"}


def _src(name):
    with open(os.path.join(JS, name), encoding="utf-8") as f:
        return f.read()


def js_keys(name, const):
    """The keys of one object table „const NAME={…}“ of a page script, read without running it."""
    s = _src(name)
    m = re.search(r"\b(?:const|let)\s+" + const + r"\s*=\s*\{", s)
    if not m:
        raise AssertionError(f"{name}: {const} is gone")
    i, depth, keys, quote, start = m.end(), 1, [], "", True
    while depth:
        c = s[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = ""
        elif c in "'\"`":
            if depth == 1 and start:
                j = s.index(c, i + 1)
                if s[j + 1:j + 2] == ":":
                    keys.append(s[i + 1:j])
                    i, start = j + 1, False
                    continue
            quote = c
        elif c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif depth == 1 and c == ",":
            start = True
        elif depth == 1 and start and (c.isalpha() or c == "_"):
            k = re.match(r"[A-Za-z_]\w*", s[i:]).group(0)
            if s[i + len(k):i + len(k) + 1] == ":":
                keys.append(k)
            i, start = i + len(k), False
            continue
        i += 1
    return set(keys)


class Tabellen(unittest.TestCase):
    def test_every_page_table_knows_every_value_of_the_panel(self):
        r = dungeon.rules()
        dienste = {d for _, _, ds in dungeon_gold.HAEUSER for d in ds}
        kinds = {"heilen", "sonst", *(k for k, _ in dungeon._KANN_ART)}
        with open(os.path.join(PANEL, "dungeon.py"), encoding="utf-8") as f:
            ep = set(re.findall(r'\bmark\("(\w+)"\)', f.read()))
        for f in glob.glob(os.path.join(PANEL, "dungeon_*.py")):
            with open(f, encoding="utf-8") as fh:
                ep |= set(re.findall(r'_log\(rd, "ep",.*grund=\["(\w+)"\]', fh.read()))
        same = (("dungeon.js", "DMSG", set(dungeon.PROBE_SG)),                     # the level of a check (the Bibliothek fault)
                ("dungeon.js", "DMSEL", {x["id"] for x in r["seltenheit"]}),
                ("dungeon.js", "DMZ", kinds), ("dungeon.js", "DMKK", kinds),        # the kind of a power (power_kind)
                ("dungeon.js", "DMEIG", set(dungeon.kampf.EIGENSCHAFTEN)),
                ("dungeon.js", "DMWIRKT", {"resistenz", "immun", "schwaeche"}),     # kampf.resisted
                ("dungeon.js", "DMWACHE", set(dungeon_ideen.WACHE)),
                ("dungeon.js", "DMGFAUS", {"am_boden", "geflohen"}),                # dungeon_gefaehrte: c["aus"]
                ("dungeon.js", "DMEPGRUND", ep),
                ("dungeon.js", "DMRMARKE", set(dungeon_balance.MARKEN)),
                ("dungeonfenster.js", "DMZEIT", set(dungeon.TAGESZEITEN)),
                ("dungeonfenster.js", "DMHAUS", {h for h, _, _ in dungeon_gold.HAEUSER}),
                ("dungeonfenster.js", "DMVERB", dienste))
        for name, const, want in same:
            self.assertEqual(sorted(js_keys(name, const)), sorted(want), f"{name} {const}")
        self.assertLessEqual(js_keys("dungeon.js", "DMART"), set(dungeon.kampf.SCHADEN_ARTEN))
        self.assertLessEqual(set(dungeon.kampf.SCHADEN_ARTEN), js_keys("dungeon.js", "DMART"))
        self.assertLessEqual(js_keys("dungeonfenster.js", "DMSLEER"), dienste)
        self.assertLessEqual(js_keys("dungeonkarte.js", "DMK_ART"), set(dungeon_karte.RAUM_ARTEN))
        self.assertEqual(set(dungeon_regelseite.RAUM_ART), set(dungeon_karte.RAUM_ARTEN))

    def test_every_reason_the_panel_refuses_with_has_its_sentence(self):
        """A refusal („fluestern oft“, „kein vorschlag“) the page shows only by its sentence: in DMGRUND or another
        page script of the game, else in ALLGEMEIN with why; and no sentence of DMGRUND for a reason gone."""
        seiten = "".join(_src(os.path.basename(f)) for f in glob.glob(os.path.join(JS, "dungeon*.js")))
        py = ""
        for f in sorted(glob.glob(os.path.join(PANEL, "dungeon*.py"))):
            with open(f, encoding="utf-8") as fh:
                py += fh.read()
        code = r'"([a-zäöü_][a-zäöü_ -]*)"'                      # a reason word; a whole sentence shows as it is
        raised = set(re.findall(r'raise (?:_http\()?(?!RuntimeError)\w+\((?:\d+, )?' + code + r'\)', py))
        raised |= set(re.findall(r'Error: \(\d+, ' + code + r'\)', py))      # dungeon._NEIN
        lose = sorted(x for x in raised - set(ALLGEMEIN) if f"'{x}'" not in seiten and f'"{x}"' not in seiten
                      and not re.search(r"[{,]\s*" + re.escape(x) + r"\s*:", seiten))
        self.assertEqual(lose, [], "reasons of the panel without a sentence on the page")
        alt = sorted(k for k in js_keys("dungeon.js", "DMGRUND") if f'"{k}"' not in py)
        self.assertEqual(alt, [], "DMGRUND sentences of reasons the panel no longer gives")
        self.assertLessEqual(set(ALLGEMEIN), raised | {"not from another site"})


if __name__ == "__main__":
    unittest.main()
