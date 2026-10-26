"""KI-Dungeon-Master: Narben und bleibende Wunden (D&D idea 8, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du
alles umsetzten kannst.“; wounds as in giffyglyph/darker-dungeons, CC BY-NC-ND, only the idea; own code, the tables'
texts come from the thread „DnDAppFiles für den Dungeon-Master“, dungeon_srd.json „ideen“).

A hero that stands up again after lying down (stood_up, Gnade) or takes a foe's critical hit gets a wound: the panel
rolls a d20 on the table ideen.narben; mostly only a scar (its look), on a few rows a mild consequence, −1 on one value
(folge, in dungeon.total) until a healer of a settlement takes it away for gold (dungeon_gold, „heiler“); the scar stays
as a memory. At the children's table only a plaster (ideen.narben_kinder), never a consequence. The admin's second
switch „nur Narben“ (chat.dungeon_narben_nur) keeps every wound to its look. At most one wound a hero and turn, at most
NARBEN_MAX a hero; the scars are kept with the hero (h["narben"], fix) and shown in its sheet; in a settlement people
ask about one (ideen.narben_sprueche, saying). Only the panel rolls; the model only reads the scars in its facts.

Off by default: the admin's switch dungeonnarben (features.py, chat.dungeon_narben) for the round's host.
Journal: fixed words and numbers („dungeon: narbe | …“), Live only counts.
"""
import random

import features
from common import DayCounter

KEY = "dungeonnarben"
NUR = "dungeonnarbennur"   # the admin's „nur Narben“ (chat.dungeon_narben_nur): the look only, never a consequence
NARBEN_MAX = 8             # wounds a hero keeps
HEILER = 8                 # the healer's gold per level of the group (dungeon_gold.PREIS)
TEXT_MAX = 200
FAKTEN = 3                 # scars per hero in the model's facts

_day = DayCounter(narben=0, folgen=0, pflaster=0, geheilt=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def only_look(rd):
    return features.allowed(NUR, rd["owner"])


def wound(dm, r, rd, pid, h, warum, rng=None):
    """A wound by the table (warum: auf, gnade, krit): the entry put on the hero and logged, or None (off, no table,
    already one this turn, NARBEN_MAX reached, a hero fallen)."""
    if not on(rd) or not h or h.get("tot"):
        return None
    zug = rd.get("zug", 0)
    seen = rd.setdefault("narbe_zug", {})
    n = h.get("narben") or []
    if seen.get(pid) == zug or len(n) >= NARBEN_MAX:
        return None
    rng = rng or random
    i = r.get("ideen") or {}
    if dm.kids(r, rd):
        rows = i.get("narben_kinder") or []
        if not rows:
            return None
        e = {"t": list(rows[rng.randrange(len(rows))]), "pflaster": True}
    else:
        import dungeon_ideen                 # the table's die (dungeon_ideen imports dungeon_kampf, which calls in here)
        rows = i.get("narben") or []
        w = rng.randint(1, dungeon_ideen.NARBEN_W)
        row = next((x for x in rows if x["von"] <= w <= x["bis"]), None)
        if not row:
            return None
        e = {"t": list(row["t"]), "w": w, **({"folge": dict(row["folge"])} if row.get("folge") and not only_look(rd) else {})}
    seen[pid] = zug
    h["narben"] = n + [e]
    li = 1 if rd.get("lang") == "en" else 0
    folge = _folge(r, e, li)
    dm._log(rd, "narbe", pid=pid, name=h["name"], t=e["t"], folge=folge, pflaster=bool(e.get("pflaster")))
    was = "pflaster" if e.get("pflaster") else "folge" if folge else "narbe"
    _day.bump("narben")
    if was != "narbe":
        _day.bump("pflaster" if was == "pflaster" else "folgen")
    print(f"dungeon: narbe | {was} | {warum}", flush=True)
    return e


def _folge(r, e, li):
    f = e.get("folge")
    if not f:
        return ""
    w = next((x for x in r["werte"] if x["id"] == f["wert"]), None)
    return f"−{f['minus']} {w['name'][li]}" if w else ""


def minus(h, wert):
    """What the hero's wounds take from a value (dungeon.total)."""
    return sum(x["folge"]["minus"] for x in h.get("narben") or [] if x.get("folge") and x["folge"]["wert"] == wert)


def to_heal(h):
    """The wounds with a consequence a healer can take."""
    return sum(1 for x in h.get("narben") or [] if x.get("folge"))


def heal(h):
    """The healer takes every consequence; the scars stay. Returns how many."""
    n = to_heal(h)
    for x in h.get("narben") or []:
        x.pop("folge", None)
    if n:
        _day.bump("geheilt")
    return n


def fix(r, h):
    """A hero read from a file: its wounds only as the table writes them, at most NARBEN_MAX."""
    werte = {w["id"] for w in r["werte"]}
    ok_t = lambda t: isinstance(t, list) and len(t) == 2 and all(isinstance(s, str) and 0 < len(s) <= TEXT_MAX for s in t)
    out = []
    for x in h.get("narben") or [] if isinstance(h.get("narben"), list) else []:
        if not isinstance(x, dict) or not ok_t(x.get("t")):
            continue
        e = {"t": list(x["t"])}
        if x.get("pflaster") is True:
            e["pflaster"] = True
        f = x.get("folge")
        if isinstance(f, dict) and f.get("wert") in werte and f.get("minus") == 1 and not e.get("pflaster"):
            e["folge"] = {"wert": f["wert"], "minus": 1}
        out.append(e)
    h["narben"] = out[:NARBEN_MAX]


def view(r, h, lang):
    """The hero's wounds for its sheet: [{t, folge, pflaster}], the newest first."""
    li = 1 if lang == "en" else 0
    return [{"t": x["t"][li], "folge": _folge(r, x, li), "pflaster": bool(x.get("pflaster"))} for x in reversed(h.get("narben") or [])]


def facts(rd, seated):
    """The scars of the heroes at the table for the model (it may tell them, never makes one)."""
    if not on(rd):
        return {}
    li = 1 if rd.get("lang") == "en" else 0
    out = {p["held"]["name"]: [x["t"][li] for x in (p["held"].get("narben") or [])[-FAKTEN:]] for _, p in seated if p["held"].get("narben")}
    return {"narben": out} if out else {}


def saying(r, rd, seated):
    """In a settlement: one fixed line of ideen.narben_sprueche about a hero's scar (never a plaster), hero and line
    picked by the turn: {name, text}, or None."""
    rows = (r.get("ideen") or {}).get("narben_sprueche") or []
    mit = [(pid, p["held"]) for pid, p in seated if any(not x.get("pflaster") for x in p["held"].get("narben") or [])]
    if not on(rd) or not rows or not mit:
        return None
    li = 1 if rd.get("lang") == "en" else 0
    z = rd.get("zug", 0)
    _, h = mit[z % len(mit)]
    narbe = [x for x in h["narben"] if not x.get("pflaster")][-1]["t"][li]
    s = rows[z % len(rows)][li]
    return {"name": h["name"], "text": s.replace("{narbe}", narbe[:1].lower() + narbe[1:])}


def for_live():
    """Numbers only: wounds, consequences, plasters and healings today."""
    t = _day.counts()
    return {k: t[k] for k in ("narben", "folgen", "pflaster", "geheilt")}
