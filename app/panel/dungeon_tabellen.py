"""KI-Dungeon-Master: the fixed tables of the catalog (Tabletop-Punkte 5 and 8 of 2026-10-25, Dominik „ich hätte gerne
alle punkte umgesetzt“; the data comes from the thread „DnDAppFiles für den Dungeon-Master“, dungeon_srd.json).

r["tabellen"] = [{"id", "gruppe": "nsc"|"orakel", "name": [de, en], "zeilen": [{"t": [de, en], "welten"?: [...]}]}]: a row
without "welten" counts in every world. r["namensilben"] = {volk or "welt:<id>": {"anfang", "mitte", "ende"}}: a name is a
start, at most one middle and an end (the Syllabore method, own syllables). The panel rolls, never the model; what it
rolls goes to the model only as data. The oracle and many NPC rows are translated from Datasworn (CC-BY-4.0, the
attribution stands in dungeon_srd.json "lizenz" and in the docs).
"""
import random

NAMEN_VORSCHLAG = 3        # fresh names the model may take for a new person
NAME_LEN = 30


def table(r, tid):
    return next((t for t in r.get("tabellen") or [] if t.get("id") == tid), None)


def rows(r, tid, welt):
    """The rows of a table that count in this world, as [de, en]."""
    t = table(r, tid)
    return [z["t"] for z in (t or {}).get("zeilen") or [] if not z.get("welten") or welt in z["welten"]]


def roll(r, tid, welt, rng=None):
    """One row of the table for this world, [de, en]; None when there is none."""
    xs = rows(r, tid, welt)
    return list((rng or random).choice(xs)) if xs else None


def _syllables(r, welt, volk, rng):
    s = r.get("namensilben") or {}
    if f"welt:{welt}" in s:
        return s[f"welt:{welt}"]
    if volk in s:
        return s[volk]
    keys = sorted(k for k in s if not k.startswith("welt:"))
    return s[rng.choice(keys)] if keys else None


def name(r, welt, volk=None, rng=None):
    """A name from the syllables of the world (sci-fi, pirates) or of a people; "" without syllables."""
    rng = rng or random
    s = _syllables(r, welt, volk, rng)
    if not s or not s.get("anfang") or not s.get("ende"):
        return ""
    mitte = rng.choice(s["mitte"]) if s.get("mitte") and rng.random() < 0.4 else ""
    n = (rng.choice(s["anfang"]) + mitte + rng.choice(s["ende"]))[:NAME_LEN]
    return n[:1].upper() + n[1:]


def fresh_names(r, rd, rng=None, n=NAMEN_VORSCHLAG):
    """Up to n names nobody of the round bears yet (heroes, the people of the truth), for the model as data."""
    rng = rng or random
    taken = {p["held"]["name"].lower() for p in rd["plaetze"].values() if p.get("held")}
    taken |= {p["name"].lower() for p in (rd.get("wahrheit") or {}).get("personen") or []}
    out = []
    for _ in range(n * 4):
        x = name(r, rd.get("welt"), None, rng)
        if x and x.lower() not in taken:
            taken.add(x.lower())
            out.append(x)
        if len(out) >= n:
            break
    return out
