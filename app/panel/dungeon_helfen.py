"""KI-Dungeon-Master: Helfen und Gruppenprobe (D&D ideas round 2, idea 4, Dominik 2026-10-26 „1-9 umsetzten
reihenfolge überlasse ich dir.“; the rules „Working Together“ and „Group Checks“ of the SRD 5.1, CC BY 4.0).

Helfen: a seat whose action of the turn says it helps another hero by name („Ich helfe Mara über die Mauer“, fixed
words WORTE, the hero's name as a word) gives that hero's first check of the turn advantage (a disadvantage cancels
it). Never for oneself, never on an attack (attacks are not checks), only a hero that can act helps, one helper a hero.
Gruppenprobe: when GRUPPE_MIN or more seats roll the same value against the same difficulty in one turn, the group
passes if at least half of them pass; then every check of the group counts as passed (the receipt says "gruppe").
Both are fixed rules of the panel on its own rolls (dungeon.roll); the model only reads them in the facts.

Off by default: the admin's switch dungeonhelfen (features.py, chat.dungeon_helfen) for the round's host.
Journal: fixed words and numbers („dungeon: helfen | …“), Live only counts.
"""
import re

import features
from common import DayCounter

KEY = "dungeonhelfen"
WORTE = ("helfe", "helfen", "hilf", "unterstütze", "stütze", "help", "assist", "support")
GRUPPE_MIN = 2             # seats rolling the same value against the same difficulty make a group check
NAME_MIN = 3               # a part of a hero's name counts as its name from this many letters

_day = DayCounter(hilfe=0, gruppe_geschafft=0, gruppe_nicht=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def _words(text):
    return set(re.findall(r"[\wäöüß]+", str(text or "").lower()))


def helpers(dm, rd):
    """{pid of the helped: name of its helper}: the actions of the turn with a word of WORTE and another hero's name."""
    if not on(rd):
        return {}
    seats = [(pid, p["held"]) for pid, p in dm.seated(rd) if not dm.zustand(p["held"])]
    out = {}
    for pid, h in seats:
        words = _words((rd.get("offen", {}).get(pid) or {}).get("text"))
        if not words & set(WORTE):
            continue
        for oid, o in seats:
            names = {x for x in _words(o["name"]) if len(x) >= NAME_MIN}
            if oid != pid and oid not in out and names & words:
                out[oid] = h["name"]
                break
    return out


def group(out):
    """The group checks of a turn's rolls: GRUPPE_MIN or more seats on the same value and difficulty; at least half
    passed, every one of them passes ("gruppe": True on all of the group)."""
    groups = {}
    for i, x in enumerate(out):
        groups.setdefault((x["wert"], x["schwer"]), {}).setdefault(x["pid"], i)
    for seats in groups.values():
        if len(seats) < GRUPPE_MIN:
            continue
        ok = sum(1 for i in seats.values() if out[i]["ok"])
        win = 2 * ok >= len(seats)
        for i in seats.values():
            out[i] = dict(out[i], gruppe=True, **({"ok": True} if win else {}))
        _day.bump("gruppe_geschafft" if win else "gruppe_nicht")
        print(f"dungeon: helfen | gruppe | {ok} von {len(seats)} | {'geschafft' if win else 'nicht'}", flush=True)
    return out


def used():
    """A help was given (the count and the journal line)."""
    _day.bump("hilfe")
    print("dungeon: helfen | vorteil", flush=True)


def for_live():
    """Numbers only: helps given, group checks passed and failed today."""
    t = _day.counts()
    return {k: t[k] for k in ("hilfe", "gruppe_geschafft", "gruppe_nicht")}
