"""KI-Dungeon-Master: Helden kommentieren selbst (Dominik 2026-10-26 „ebenso fehlt ein bisschen das die helden mehr
eigende komentare abgeben“, gewählt „2a“).

The narration may give every hero who acted this turn one short line of its own in „helden_sagen“ ({name, sagt}): a
reaction or a feeling about its own action, never a new decision. The panel takes it by fixed rules (check): only a
hero whose seat acted this turn (not one answered out of the game), one line a hero, plain text of at most SAGT_MAX
characters, no word the round refuses, no number, no first-person deed (TUN: „ich gehe“, „wir nehmen“ …) and no
deciding word of dungeon_erzaehler.ENTSCHEIDET. The line stands as a speech bubble of the hero under the narration and,
read aloud, speaks in the hero's own voice (speak). Players' own quotes in their actions stay first (hero_lines).

Off by default: the admin's switch dungeonkommentar (features.py, chat.dungeon_kommentar) for the round's host.
Journal: fixed words and numbers („dungeon: kommentar | …“), Live only counts.
"""
import re

import features
from common import DayCounter

KEY = "dungeonkommentar"
SAGT_MAX = 120
TUN = re.compile(r"\b(ich|wir|i|we)\s+(gehe|gehen|greife|greifen|nehme|nehmen|öffne|öffnen|renne|rennen|ziehe|ziehen|springe|"
                 r"springen|laufe|laufen|entscheide|entscheiden|kaufe|kaufen|verkaufe|verkaufen|töte|töten|go|take|attack|open|"
                 r"grab|run|jump|buy|sell|decide|kill)\b", re.I)
ZAHL = re.compile(r"\d")

SCHEMA = {"type": "array", "maxItems": 5, "items": {"type": "object", "additionalProperties": False, "required": ["name", "sagt"],
          "properties": {"name": {"type": "string", "maxLength": 60}, "sagt": {"type": "string", "maxLength": SAGT_MAX + 40}}}}
AUFGABE = {
    "de": (" Gib in helden_sagen jedem Helden, der in diesem Zug gehandelt hat, eine kurze wörtliche Zeile (höchstens "
           "120 Zeichen): wie er seine eigene Tat oder ihren Ausgang kommentiert, ein Gefühl, ein Spruch, ein Fluch. Nie "
           "eine neue Entscheidung, nie eine Zahl; was er tut, schreibt nur sein Spieler."),
    "en": (" In helden_sagen give every hero who acted this turn one short line in its own words (at most 120 characters): "
           "how it comments on its own deed or its outcome, a feeling, a quip, a curse. Never a new decision, never a "
           "number; what it does only its player writes."),
}

_day = DayCounter(gesagt=0, verworfen=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def task(rd, lang):
    return AUFGABE[lang] if on(rd) else ""


def check(dm, r, rd, rows, ooc=()):
    """The narration's hero lines by fixed rules: [{pid, name, sagt}] in the order given; [] while off."""
    if not on(rd) or not isinstance(rows, list):
        return []
    import dungeon_erzaehler as erz
    acted = {p["held"]["name"].strip().lower(): pid for pid, p in rd["plaetze"].items()
             if p.get("held") and pid in (rd.get("offen") or {}) and pid not in ooc and not dm.zustand(p["held"])}
    out, bad = [], 0
    for x in rows:
        pid = acted.get(str(x.get("name", "")).strip().lower()) if isinstance(x, dict) else None
        sagt = dm.plain(x.get("sagt"), SAGT_MAX).strip(" „“\"»«") if isinstance(x, dict) else ""
        low = sagt.lower()
        if not pid or len(sagt) < 3 or pid in (y["pid"] for y in out) or ZAHL.search(sagt) or TUN.search(low) \
                or any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low) for w in erz.ENTSCHEIDET) or dm.bad_words(r, rd, sagt):
            bad += 1
            continue
        out.append({"pid": pid, "name": rd["plaetze"][pid]["held"]["name"], "sagt": sagt})
    if out:
        _day.bump("gesagt", len(out))
    if bad:
        _day.bump("verworfen", bad)
    if out or bad:
        print(f"dungeon: kommentar | {len(out)} gesagt | {bad} verworfen", flush=True)
    return out


def speak(dm, r, rd, lines):
    """The hero lines read aloud, each in its hero's voice (the NPC voice for a hero without one)."""
    v = dm.voices(r)
    out = []
    for x in lines or []:
        h = (rd["plaetze"].get(x.get("pid")) or {}).get("held") or {}
        out.append((h.get("stimme", "") or v["npc"], x["sagt"], h.get("klang", "") if dm._stimmen["design"] else ""))
    return out


def for_live():
    """Numbers only: hero lines taken and refused today."""
    t = _day.counts()
    return {k: t[k] for k in ("gesagt", "verworfen")}
