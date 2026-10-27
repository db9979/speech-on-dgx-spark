"""KI-Dungeon-Master: Wandernde Personen und kleine Gesten (LlamaTale ideas 6 and 7, plan
plaene/dungeon-llamatale-ideen.md, Dominik 2026-10-27 „1-7“; ideas only, own code).

Wandernde Personen (switch dungeonwandern): over a long rest (dungeon_rast) the panel lets the people of the map move
on (dungeon_karte.wandern: each person not with the group, WANDERN percent, one way towards the place
dungeon_nsc.ziel_ort names: the place its open goals name, else the fitting place of its occupation). The table hears
it as a rumour at the campfire (a line in the feed), the next narration gets the moves as data (gewandert) with the
task to tell only a meeting again, never a new move. Not between chapters: the next chapter rolls a new map.
Kleine Gesten (switch dungeongesten): dungeon_nsc.geste picks a person of the scene with a strong trait and its fixed
line; the music thread's waiting time (dungeon_warten) asks when one is due and writes it into the feed (art "geste"),
never in the car. Both only while the admin's switch is allowed for the round's host, on top of „NSC-Gedächtnis und
Chronik“. Journal: fixed words and numbers, Live only counts.

    rd["gewandert"]  [{"name", "von", "nach"}]   the moves of the last long rest, until the next told turn
"""
import random

import dungeon_nsc as nsc
import features
from common import DayCounter

KEY = "dungeonwandern"
_day = DayCounter(rasten=0, gewandert=0)

AUFGABE = {
    "de": (" gewandert nennt Personen, die während der Rast weitergezogen sind (das Panel hat es so gewürfelt): trefft "
           "ihr eine davon wieder, erzähl das Wiedersehen kurz; lass niemanden sonst wandern."),
    "en": (" gewandert names people who moved on during the rest (the panel rolled it so): if you meet one of them again, "
           "tell the meeting briefly; let nobody else move."),
}


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and nsc.on(rd) and bool(rd.get("karte"))


def rest(dm, r, rd, rng=None):
    """After a long rest: the people move on by the map's rule; a rumour per move in the feed. Returns the moves."""
    import dungeon_karte
    if not on(rd):
        return []
    moves = dungeon_karte.wandern(r, rd, rng or random, "lange_rast")
    rd["gewandert"] = moves
    for m in moves:
        dm._log(rd, "system", text=[f"Am Lagerfeuer hört ihr: {m['name']} ist von {m['von']} nach {m['nach']} gezogen.",
                                    f"At the campfire you hear: {m['name']} moved from {m['von']} to {m['nach']}."])
    _day.bump("rasten")
    _day.bump("gewandert", len(moves))
    print(f"dungeon: wandern | {len(moves)} personen", flush=True)
    return moves


def facts(rd):
    """For the narration after the rest: who moved where ({} without moves)."""
    return {"gewandert": [{"name": m["name"], "nach": m["nach"]} for m in rd["gewandert"]]} if on(rd) and rd.get("gewandert") else {}


def task(rd, lang):
    return AUFGABE[lang] if on(rd) and rd.get("gewandert") else ""


def told(rd):
    """A told turn after the rest: the moves were the narration's once."""
    rd.pop("gewandert", None)


def for_live():
    """Numbers only: long rests on the map, people moved, gestures today."""
    return dict(_day.counts(), **nsc._gesten.counts())
