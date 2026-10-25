"""KI-Dungeon-Master: legendäre Einzelstücke je Welt (Gegenstands-Punkt 4 of 2026-10-24, Dominik „Ja, alles umsetzen“).

dungeon_legenden.json holds 20 named pieces for each world: a wearable base of the catalog, an own name and sentence in
both languages and two effects of the list „effekte“. The catalog's own pieces of fixed rarity „legendär“ (SRD: the
Vorpal Sword and the like) count as legends too, by their catalog id. A find that comes out legendär (rarity) becomes
one of them by fixed rules, never by the model:
- only from a boss, a reward or a chest (ANLASS); a merchant never sells one (open_market draws at most episch);
- each once a campaign: the round keeps the ones found (rd["legenden"]), a chapter hands them to the next one, and none
  a seated hero already carries comes again;
- one for the receiver's class first; with none free the find is episch.
The world „eigene“ uses the pieces of SONST.
"""
import json
import os

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dungeon_legenden.json")
ANLASS = ("boss", "truhe", "belohnung")
SONST = "fantasy"
EFFEKTE = 2
_cache = None


def load():
    """The shipped pieces as they stand in the file (read once)."""
    global _cache
    if _cache is None:
        try:
            with open(FILE, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        _cache = [x for x in (d.get("legenden") if isinstance(d, dict) else None) or [] if isinstance(x, dict)]
    return _cache


def problems(dm, r, x):
    """What is wrong with one piece against the rules in force: [] for a playable one."""
    out = []
    items, eff = dm._by(r, "gegenstaende"), dm._by(r, "effekte")
    c = items.get(x.get("basis"))
    if not isinstance(x.get("id"), str) or not x["id"]:
        out.append("id")
    if x.get("welt") not in [w["id"] for w in r["welten"]]:
        out.append("welt")
    if not c or c["art"] not in dm.PLATZ_ART or not dm.in_world(c, x.get("welt")):
        out.append("basis")
    for k in ("name", "satz"):
        if not (isinstance(x.get(k), list) and len(x[k]) == 2 and all(isinstance(s, str) and 0 < len(s) <= (40 if k == "name" else dm.SATZ_MAX) for s in x[k])):
            out.append(k)
    fx = x.get("effekte")
    if not (isinstance(fx, list) and len(fx) == EFFEKTE and len(set(fx)) == EFFEKTE and all(f in eff for f in fx)):
        out.append("effekte")
    elif c and any(eff[f].get("nur") and c["art"] not in eff[f]["nur"] for f in fx):
        out.append("nur")
    elif sum(eff[f].get("wirkung") == "schaden" for f in fx) > 1:
        out.append("schaden")
    return out


def check(dm, r):
    """Every problem of the file (selftest: none): per piece, and an id twice or one that is also a catalog id."""
    out, seen = [], set()
    items = dm._by(r, "gegenstaende")
    for x in load():
        p = problems(dm, r, x)
        if x.get("id") in seen or x.get("id") in items:
            p.append("doppelt")
        seen.add(x.get("id"))
        out += [f"{x.get('id')}: {w}" for w in p]
    return out


def of_world(dm, r, welt):
    """The playable pieces of a world: (id, catalog id, piece or None for a catalog piece of fixed rarity)."""
    w = welt if any(x.get("welt") == welt for x in load()) else SONST
    top = r["seltenheit"][-1]["id"]
    out = [(x["id"], x["basis"], x) for x in load() if x.get("welt") == w and not problems(dm, r, x)]
    return out + [(c["id"], c["id"], None) for c in r["gegenstaende"] if c.get("seltenheit") == top
                  and c["art"] in dm.PLATZ_ART and dm.in_world(c, welt)]


def piece(lid):
    return next((x for x in load() if x.get("id") == lid), None)


def carried(dm, rd):
    """The legends the seated heroes carry and the ones on the ground."""
    its = list(rd.get("boden") or [])
    for _, p in dm.seated(rd):
        h = p["held"]
        its += list(h.get("tasche") or []) + [x for x in (h.get("an") or {}).values() if x]
    return {x["leg"] for x in its if isinstance(x, dict) and x.get("leg")}


def pick(dm, r, rd, h, welt, rng):
    """A free legend for the hero (its class first), or None."""
    taken = set((rd or {}).get("legenden") or []) | (carried(dm, rd) if rd else set())
    free = [x for x in of_world(dm, r, welt) if x[0] not in taken]
    items = dm._by(r, "gegenstaende")
    pool = [x for x in free if dm.fits(r, h, items[x[1]])] or free
    return rng.choice(pool) if pool else None


def make(dm, r, leg, rng):
    """The item of a legend: legendary, unknown until named, its two effects (a catalog piece keeps its own)."""
    lid, cid, x = leg
    top = r["seltenheit"][-1]
    it = dm.item(r, cid, top["id"], rng)
    it.update(s=top["id"], bonus=top["bonus"], leg=lid, u=True)
    if x:
        it["eff"], it["eff2"] = x["effekte"]
    if dm._c(r, it)["art"] == "schmuck" and not it.get("wert"):
        it["wert"] = dm._by(r, "effekte")[it["eff"]]["wert"] if it.get("eff") else rng.choice([w["id"] for w in r["werte"]])
    return it


def text(it, li):
    """(name, sentence) of a shipped legend in the language, or None."""
    x = piece(it.get("leg"))
    return (x["name"][li], x["satz"][li]) if x else None
