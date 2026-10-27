"""KI-Dungeon-Master: runes and sockets (plan dungeon-runen/plan.md, Dominik 2026-10-27 „1a 2b 3a 4a 5a 6a 7a 8a 10a
11a“): the catalog's 13 runes and 7 runewords in dungeon_srd.json (thread „DnDAppFiles für den Dungeon-Master“; the rune
names are historical runes, public domain) and their check by fixed rules.

r["runen"] = [{"id", "rang": 1..13 without a gap, "name": [de, en], "sinn": [de, en], "preis", "waffe": W|null,
"ruestung": W|null, "schild": W|null}]: what the rune does in a weapon, in a worn piece (body, head, hands, feet) or in a
shield; null = not there. r["runenwoerter"] = [{"id", "name": [de, en], "runen": [rune ids in this order], "ort":
ORTE_RW, "sockel": len(runen), "ab": level, "zusatz": W}]. A W is an object of WIRKUNG keys only. The panel decides
everything (which rune falls, sockets, effect, cap, price); the model only tells the fixed line. The world's word for a
rune (Rune, Chip, Perle, Siegel) and the sockets per base item are code rules, not catalog fields.
"""
import re

import dungeon_kampf as kampf

ORTE = ("waffe", "ruestung", "schild")                     # where a rune sits
ORTE_RW = ("waffe", "koerper", "nebenhand", "kopf")         # where a runeword sits
WIRKUNG = {"treffer": (1, 2), "schaden": (1, 2), "leben": (1, 8), "rabatt": (1, 20), "gold": (1, 10), "heiltrank": (1, 4),
           "rk": (1, 1), "schutz": (1, 1), "bonus": (1, 1), "effekt": None, "werte": None, "widerstand": None}   # int keys: (lo, hi)
RAENGE = 13
RUNENWORT_MAX = 6           # runes in one runeword
AB_MAX = 20
PREIS_MAX = 4000            # at most „episch“
_ID = re.compile(r"[a-z0-9_]{2,24}")
NAME_MAX = 40


def _pair(x, n=NAME_MAX):
    import dungeon                       # the one helper of the rules (loaded already: dungeon.check_rules calls here)
    return dungeon._pair(x, n)


def _int(x, lo, hi):
    import dungeon
    return dungeon._int(x, lo, hi)


def _art(ort):
    """The art of the base item a rune or runeword sits in (an effect's „nur“ names arts)."""
    return "waffe" if ort == "waffe" else "ruestung"


def wirkung_ok(r, w, ort):
    """A W by fixed rules: only WIRKUNG keys, numbers in their range, "werte" with "bonus", an effect of the rules that
    may sit at this place, a damage type of the list."""
    if not isinstance(w, dict) or not w or not set(w) <= set(WIRKUNG):
        return False
    if any(rng and not _int(w[k], *rng) for k, rng in WIRKUNG.items() if k in w):
        return False
    werte = {x["id"] for x in r.get("werte") or [] if isinstance(x, dict)}
    if ("werte" in w) != ("bonus" in w) or "werte" in w and not (isinstance(w["werte"], list) and w["werte"] and set(w["werte"]) <= werte):
        return False
    if "widerstand" in w and w["widerstand"] not in kampf.SCHADEN_ARTEN:
        return False
    if "effekt" in w:
        e = next((x for x in r.get("effekte") or [] if isinstance(x, dict) and x.get("id") == w["effekt"]), None)
        if e is None or e.get("nur") and _art(ort) not in e["nur"]:
            return False
    return not ("treffer" in w or "schaden" in w) or ort == "waffe"


def check_rules(r):
    """The runes and runewords by fixed rules: German sentences of what is wrong (dungeon.check_rules adds them). Both
    lists are optional; what stands there must be whole."""
    err = []

    def need(ok, text):
        if not ok:
            err.append(text)
    rs = r.get("runen")
    if rs is None and r.get("runenwoerter") is None:
        return err
    by = {}
    need(isinstance(rs, list) and all(isinstance(x, dict) for x in rs), "runen: eine Liste von Runen")
    for x in rs if isinstance(rs, list) else []:
        if not isinstance(x, dict):
            continue
        need(isinstance(x.get("id"), str) and _ID.fullmatch(x["id"]) and x["id"] not in by, f"runen {x.get('id')}: eigene id aus a-z, 0-9 und _")
        by[x.get("id")] = x
        need(_int(x.get("rang"), 1, RAENGE) and _pair(x.get("name")) and _pair(x.get("sinn")) and _int(x.get("preis"), 1, PREIS_MAX),
             f"runen {x.get('id')}: rang 1 bis {RAENGE}, name und sinn als [deutsch, englisch], preis 1 bis {PREIS_MAX}")
        need(all(o in x for o in ORTE) and any(x[o] is not None for o in ORTE)
             and all(x[o] is None or wirkung_ok(r, x[o], o) for o in ORTE),
             f"runen {x.get('id')}: waffe, ruestung und schild je eine Wirkung oder null (Treffer und Schaden nur in der Waffe, "
             "Effekte nur, wo ihr „nur“ passt)")
    if isinstance(rs, list) and rs:
        need(sorted(x.get("rang") for x in rs if isinstance(x, dict) and _int(x.get("rang"), 1, RAENGE)) == list(range(1, len(rs) + 1)),
             "runen: jeder Rang von 1 an genau einmal, ohne Lücke")
    ws = r.get("runenwoerter") or []
    need(isinstance(ws, list) and all(isinstance(x, dict) for x in ws), "runenwoerter: eine Liste von Runenwörtern")
    seen, folgen = set(), set()
    for x in ws if isinstance(ws, list) else []:
        if not isinstance(x, dict):
            continue
        need(isinstance(x.get("id"), str) and _ID.fullmatch(x["id"]) and x["id"] not in seen, f"runenwoerter {x.get('id')}: eigene id")
        seen.add(x.get("id"))
        ru, ort = x.get("runen"), x.get("ort")
        stelle = "waffe" if ort == "waffe" else "schild" if ort == "nebenhand" else "ruestung"
        ok = isinstance(ru, list) and 2 <= len(ru) <= RUNENWORT_MAX and all(isinstance(i, str) and i in by for i in ru)
        need(ok and ort in ORTE_RW and all(by[i].get(stelle) is not None for i in ru) and x.get("sockel") == len(ru)
             and tuple(ru) not in folgen,
             f"runenwoerter {x.get('id')}: runen (2 bis {RUNENWORT_MAX} vorhandene, jede an diesem Ort möglich, keine Folge doppelt), "
             f"ort aus {', '.join(ORTE_RW)}, sockel = Zahl der Runen")
        if ok:
            folgen.add(tuple(ru))
        need(_pair(x.get("name")) and _int(x.get("ab"), 1, AB_MAX) and ort in ORTE_RW and wirkung_ok(r, x.get("zusatz"), _art(ort)),
             f"runenwoerter {x.get('id')}: name als [deutsch, englisch], ab Stufe 1 bis {AB_MAX}, zusatz eine Wirkung")
    return err
