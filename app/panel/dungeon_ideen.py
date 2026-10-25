"""KI-Dungeon-Master: the tables of the D&D ideas (Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; the content comes from the thread „DnDAppFiles für den Dungeon-Master“, own texts, the sources were
only ideas): critical hits and fumbles (idea 2), landscapes with night watches and question cards for a rest (4),
travel roles and travel events (9), scars (8), and a saying on every foe (12, the field „sage“ of the catalog's foes).

All of it stands in dungeon_srd.json under „ideen“ (and „sage“ at the foes); this module checks it by fixed rules
(check_rules, part of dungeon.check_rules, so a broken table never reaches a round). The panel rolls on these tables,
the model only gets the line as data, never picks it.
"""
import re

import dungeon_kampf as kampf

TEILE = ("krit", "patzer", "landschaften", "nachtwachen", "fragekarten", "reise_rollen", "reise_ereignisse", "narben",
         "narben_kinder", "narben_sprueche")
PATZER = ("nahkampf", "fernkampf", "zauber")
KRIT_W = 12                 # a d12 for a critical hit or a fumble
NARBEN_W = 20               # a d20 for a scar and a night watch
ZUEGE = (1, 3)              # a state from a critical hit lasts this many turns
WACHE = ("ruhig", "geraeusch", "besuch", "ueberfall")
REISE = ("ruhig", "ausgeruht", "hungrig", "verirrt", "ueberrascht")
FOLGE_REISE = ("ueberrascht", "hungrig", "verirrt")
TEXT_MAX = 200              # a line of a table, per language
SAGE_MAX = 200
_ID = re.compile(r"[a-z0-9_]{1,24}")


def _pair(x, n=TEXT_MAX):
    import dungeon                       # the one helper of the rules (loaded already: dungeon.check_rules calls here)
    return dungeon._pair(x, n)


def _int(x, lo, hi):
    import dungeon
    return dungeon._int(x, lo, hi)


def _rows_w(rows, zustaende):
    """A d12 table: one row per number 1 to KRIT_W, a state only of the catalog for 1 to 3 turns."""
    return (isinstance(rows, list) and sorted(x.get("w") for x in rows if isinstance(x, dict) and _int(x.get("w"), 1, KRIT_W)) == list(range(1, KRIT_W + 1))
            and all(_pair(x.get("t")) and ("zustand" not in x or x["zustand"] in zustaende and _int(x.get("zuege"), *ZUEGE))
                    and ("zuege" not in x or "zustand" in x) for x in rows))


def _cover(rows, n):
    """Rows with von and bis cover 1 to n without a gap or an overlap."""
    if not isinstance(rows, list) or not all(isinstance(x, dict) and _int(x.get("von"), 1, n) and _int(x.get("bis"), 1, n) and x["von"] <= x["bis"] for x in rows):
        return False
    seen = sorted(i for x in rows for i in range(x["von"], x["bis"] + 1))
    return seen == list(range(1, n + 1))


def check_rules(r):
    """The idea tables and the foes' sayings by fixed rules: German sentences of what is wrong (empty: fine). Both are
    optional; what stands there must be whole."""
    err = []

    def need(ok, text):
        if not ok:
            err.append(text)
    for g in r.get("gegner") or []:
        if isinstance(g, dict) and "sage" in g:
            need(_pair(g["sage"], SAGE_MAX), f"gegner {g.get('id')}: sage als [deutsch, englisch], je höchstens {SAGE_MAX} Zeichen")
    i = r.get("ideen")
    if i is None:
        return err
    if not isinstance(i, dict):
        return err + ["ideen: ein Objekt"]
    need(set(i) <= set(TEILE), f"ideen: nur {', '.join(TEILE)}")
    zust = {x.get("id") for x in r.get("zustaende") or [] if isinstance(x, dict)}
    werte = {x.get("id") for x in r.get("werte") or [] if isinstance(x, dict)}
    welten = {x.get("id") for x in r.get("welten") or [] if isinstance(x, dict)}
    ortsarten = {x.get("id") for x in r.get("ortsarten") or [] if isinstance(x, dict)}
    if "krit" in i:
        k = i["krit"]
        need(isinstance(k, dict) and set(k) <= set(kampf.SCHADEN_ARTEN), f"ideen.krit: je Schadensart aus {', '.join(kampf.SCHADEN_ARTEN)}")
        for a, rows in (k.items() if isinstance(k, dict) else ()):
            need(_rows_w(rows, zust), f"ideen.krit {a}: W{KRIT_W} mit je einer Zeile 1 bis {KRIT_W}, t als [deutsch, englisch], zustand aus zustaende mit zuege 1 bis 3")
    if "patzer" in i:
        p = i["patzer"]
        need(isinstance(p, dict) and set(p) <= set(PATZER), f"ideen.patzer: nur {', '.join(PATZER)}")
        for a, rows in (p.items() if isinstance(p, dict) else ()):
            need(_rows_w(rows, zust), f"ideen.patzer {a}: W{KRIT_W} mit je einer Zeile 1 bis {KRIT_W}, zustand aus zustaende mit zuege 1 bis 3")
    land = i.get("landschaften")
    lids = set()
    if land is not None:
        ok = isinstance(land, list) and all(isinstance(x, dict) and isinstance(x.get("id"), str) and _ID.fullmatch(x["id"]) and _pair(x.get("name"), 40)
                                             and isinstance(x.get("ortsarten"), list) for x in land)
        need(ok, "ideen.landschaften: Liste mit id, name [deutsch, englisch] und ortsarten")
        if ok:
            lids = {x["id"] for x in land}
            arten = [a for x in land for a in x["ortsarten"]]
            need(len(lids) == len(land) and "weg" in lids, "ideen.landschaften: eigene ids, darunter weg als Rückfall")
            need(len(arten) == len(set(arten)) and (not ortsarten or set(arten) <= ortsarten), "ideen.landschaften: jede Ortsart der Karte höchstens einmal")
    for teil, check, text in (("nachtwachen", lambda rows: _cover(rows, NARBEN_W) and all(x.get("art") in WACHE and _pair(x.get("t")) for x in rows),
                               f"W{NARBEN_W} lückenlos mit von, bis, art aus {', '.join(WACHE)} und t"),
                              ("reise_ereignisse", lambda rows: isinstance(rows, list) and rows and all(isinstance(x, dict) and x.get("ergebnis") in REISE and _pair(x.get("t")) for x in rows),
                               f"Zeilen mit ergebnis aus {', '.join(REISE)} und t")):
        if teil in i:
            v = i[teil]
            need(isinstance(v, dict) and set(v) <= lids, f"ideen.{teil}: je Landschaft aus ideen.landschaften")
            for a, rows in (v.items() if isinstance(v, dict) else ()):
                need(check(rows), f"ideen.{teil} {a}: {text}")
    if "fragekarten" in i:
        f = i["fragekarten"]
        need(isinstance(f, dict) and "alle" in f and set(f) <= welten | {"alle"}
             and all(isinstance(v, list) and v and all(_pair(x) for x in v) for v in f.values()),
             "ideen.fragekarten: alle und je Welt eine Liste von [deutsch, englisch]")
    if "reise_rollen" in i:
        rr = i["reise_rollen"]
        need(isinstance(rr, list) and rr and all(isinstance(x, dict) and isinstance(x.get("id"), str) and _ID.fullmatch(x["id"]) and x.get("wert") in werte
                                                 and isinstance(x.get("name"), dict) and "alle" in x["name"] and set(x["name"]) <= welten | {"alle"}
                                                 and all(_pair(n, 40) for n in x["name"].values()) and _pair(x.get("gelingt")) and _pair(x.get("misslingt"))
                                                 and x.get("folge_misslingt") in FOLGE_REISE for x in rr),
             f"ideen.reise_rollen: id, wert aus den Werten, name je Welt mit alle, gelingt, misslingt, folge_misslingt aus {', '.join(FOLGE_REISE)}")
    if "narben" in i:
        n = i["narben"]
        need(_cover(n, NARBEN_W) and all(_pair(x.get("t")) and ("folge" not in x or isinstance(x["folge"], dict) and x["folge"].get("wert") in werte and x["folge"].get("minus") == 1)
                                         for x in n), f"ideen.narben: W{NARBEN_W} lückenlos mit von, bis, t und folge {{wert, minus: 1}}")
    if "narben_kinder" in i:
        need(isinstance(i["narben_kinder"], list) and i["narben_kinder"] and all(_pair(x) for x in i["narben_kinder"]), "ideen.narben_kinder: Liste von [deutsch, englisch]")
    if "narben_sprueche" in i:
        need(isinstance(i["narben_sprueche"], list) and i["narben_sprueche"] and all(_pair(x) and ("{narbe}" in x[0]) == ("{narbe}" in x[1]) for x in i["narben_sprueche"]),
             "ideen.narben_sprueche: Liste von [deutsch, englisch], {narbe} in beiden Sprachen oder in keiner")
    return err
