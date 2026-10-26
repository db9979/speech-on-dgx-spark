"""KI-Dungeon-Master: Gegner-Ansagen und Haltung (D&D ideas round 2, idea 2, Dominik 2026-10-26 „1-9 umsetzten
reihenfolge überlasse ich dir.“; the telegraphed attacks of many tabletop and video games, only as an idea, own code).

Ansage: at the end of every fought turn each foe still up says what it does next (announce): one of ARTEN at a
standing hero, by the panel's dice. In the foes' next turn its first blow goes at that hero and works by the fixed rule
of its kind (blow): „zielt“ +ZIELT to hit, „holt_aus“ −HOLT to hit but the damage dice twice on a hit, „lauert“ with
advantage. A hero that fell meanwhile frees the foe again. The table shows the announcements as a log card, the
narrator gets them as data to foreshadow.
Haltung: a hero's action may say how it stands (stance, fixed words, also by voice and in the car): „Abwehr“ +ABWEHR
to its armour class against the foes this turn, but its own attack at a disadvantage; „Ausweichen“ its saves against
the foes' states this turn with advantage; anything else attacks as before.

Off by default: the admin's switch dungeonhaltung (features.py, chat.dungeon_haltung) for the round's host.
State in the fight: rd["kampf"]["ansage"] {foe's k: {"art", "pid"}}, made new every turn.
Journal: fixed words and numbers („dungeon: ansage | …“, „dungeon: haltung | …“), Live only counts.
"""
import random
import re

import features
from common import DayCounter

KEY = "dungeonhaltung"
ARTEN = ("zielt", "holt_aus", "lauert")
ZIELT = 2
HOLT = 2
ABWEHR = 2
TEXT = {"zielt": ("{g} zielt auf {h}.", "{g} takes aim at {h}."),
        "holt_aus": ("{g} holt gegen {h} weit aus.", "{g} winds up a heavy blow at {h}."),
        "lauert": ("{g} lauert auf eine Lücke bei {h}.", "{g} waits for an opening on {h}.")}
HALTUNG = {"abwehr": re.compile(r"(?i)(?<!\w)(abwehr|wehre?\w*\b.{0,30}\bab\b|verteidig|deckung|block|parier|schild hoch|defend|parry|guard)"),
           "ausweichen": re.compile(r"(?i)(?<!\w)(ausweich|weiche?\b.{0,30}\baus\b|duck|dodge|evade)")}

_day = DayCounter(ansagen=0, abwehr=0, ausweichen=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def stance(rd, pid):
    """The hero's stance this turn from its action's words: "abwehr", "ausweichen" or "" (attacks as before)."""
    if not on(rd):
        return ""
    t = str(((rd.get("offen") or {}).get(pid) or {}).get("text", ""))
    return next((k for k, x in HALTUNG.items() if x.search(t)), "")


def blow(rd, g, standing):
    """The foe's announced first blow: (pid, hero, art) at a hero still standing, else None."""
    a = ((rd.get("kampf") or {}).get("ansage") or {}).get(str(g["k"])) if on(rd) else None
    if not a or a.get("art") not in ARTEN:
        return None
    return next(((q, hh, a["art"]) for q, hh in standing if q == a.get("pid")), None)


def announce(dm, r, rd, rng=None):
    """After a fought turn: every foe still up announces its next blow at a standing hero; a log card for the table."""
    import dungeon_kampf
    rng = rng or random
    k = rd.get("kampf")
    if not k:
        return
    k.pop("ansage", None)
    standing = [(pid, p["held"]) for pid, p in dm.seated(rd) if not dm.zustand(p["held"])]
    if not on(rd) or not standing:
        return
    li = 1 if rd.get("lang") == "en" else 0
    k["ansage"], cards = {}, []
    for g in dungeon_kampf.up(rd):
        pid, h = standing[rng.randrange(len(standing))]
        art = ARTEN[rng.randrange(len(ARTEN))]
        k["ansage"][str(g["k"])] = {"art": art, "pid": pid}
        cards.append({"k": g["k"], "gegner": g["name"], "art": art, "pid": pid, "name": h["name"],
                      "t": TEXT[art][li].format(g=g["name"], h=h["name"])})
    if cards:
        dm._log(rd, "ansage", ansagen=cards)
        _day.bump("ansagen", len(cards))
        print(f"dungeon: ansage | {len(cards)} gegner", flush=True)


def count(rd, zuege):
    """The stances that worked in the foes' turn, for the journal and Live."""
    n = {"abwehr": 0, "ausweichen": 0}
    for x in zuege:
        if x.get("haltung") in n:
            n[x["haltung"]] += 1
    for s, m in n.items():
        if m:
            _day.bump(s, m)
            print(f"dungeon: haltung | {s} | {m}", flush=True)


def facts(rd, li):
    """The announcements of the next turn, only as data for the narrator."""
    a = (rd.get("kampf") or {}).get("ansage") if on(rd) else None
    if not a:
        return {}
    by = {str(g["k"]): g["name"] for g in rd["kampf"]["gegner"]}
    names = {pid: (p.get("held") or {}).get("name", "") for pid, p in rd["plaetze"].items()}
    return {"ansagen": [TEXT[x["art"]][li].format(g=by.get(k, ""), h=names.get(x["pid"], "")) for k, x in a.items() if k in by]}


AUFGABE = {
    "de": (" Stehen in den Fakten ansagen, erzähle am Ende kurz, was die Gegner als Nächstes vorhaben, genau so; die "
           "Spieler können mit „Abwehr“ oder „Ausweichen“ in ihrer Aktion darauf antworten, das Panel rechnet es."),
    "en": (" When the facts hold ansagen, tell briefly at the end what the foes mean to do next, exactly so; the players "
           "may answer with \"Defend\" or \"Dodge\" in their action, the panel does the numbers."),
}


def task(rd, lang):
    return AUFGABE[lang] if on(rd) and rd.get("kampf") else ""


def for_live():
    """Numbers only: announcements and stances that worked today."""
    t = _day.counts()
    return {k: t[k] for k in ("ansagen", "abwehr", "ausweichen")}
