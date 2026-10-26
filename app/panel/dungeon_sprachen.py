"""KI-Dungeon-Master: Sprachen der Völker (D&D idea 7, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; the idea of brisvag/gibberify, GPL-3, only as an idea, own code; the sounds are the name syllables
of the catalog, „namensilben“ of dungeon_srd.json).

The narration may let one person of the scene say one short greeting or cry in the tongue of a people („fremd“:
{name, volk, sagt}, sagt is what it means). The panel takes it by fixed rules (check): only a tongue of SPRACHEN whose
people has syllables in the catalog, at most SAGT_MAX characters and WOERTER words, no word the round refuses, and never
when the meaning already stands in the narration's quotes (then everyone has heard it). The sounds come from the
meaning by a fixed rule (laut): every word picks syllables of the people by its hash, so the same sentence always
sounds the same. Who understands it is fixed too (versteht): a hero of that people (a half-elf understands Elvish), a
bard or a wizard every tongue. Everyone sees and hears the sounds; the meaning goes through the view only to the seats
that understand it and to the host (view, GEHEIM „fremd_bedeutung“ in dungeon_sicht.py), never to the car or the model.

Off by default: the admin's switch dungeonsprachen (features.py, chat.dungeon_sprachen) for the round's host.
State in the round: rd["fremd"] [{"k": the narration's number, "sagt", "wer": [pid, …]}], the last FREMD_MAX.
Journal: fixed words and numbers („dungeon: sprache | …“), Live only counts.
"""
import hashlib
import re

import features
from common import DayCounter

KEY = "dungeonsprachen"
SAGT_MAX = 60              # a greeting or a cry, never a speech
WOERTER = 8
FREMD_MAX = 20
SPRACHEN = {               # the people's id: the tongue's name
    "elf": ("Elfisch", "Elvish"), "zwerg": ("Zwergisch", "Dwarvish"), "halbling": ("Halblingisch", "Halfling"),
    "ork": ("Orkisch", "Orcish"), "gnom": ("Gnomisch", "Gnomish"), "drachenbluetig": ("Drakonisch", "Draconic"),
    "tiefling": ("Infernalisch", "Infernal"),
}
VERWANDT = {"halbelf": ("elf",)}            # a people that understands another's tongue too
ALLE_KLASSEN = ("barde", "magier")           # who understands every tongue
WORT = re.compile(r"\w+")

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["name", "volk", "sagt"], "properties": {
    "name": {"type": "string", "maxLength": 40}, "volk": {"type": "string", "enum": list(SPRACHEN)},
    "sagt": {"type": "string", "maxLength": SAGT_MAX + 40}}}
AUFGABE = {
    "de": (" Grüßt oder ruft eine Person der Szene kurz in der Sprache ihres Volkes, gib es in fremd an (name, volk, "
           "sagt: was es bedeutet, höchstens 60 Zeichen), nur bei kurzen Begrüßungen und Ausrufen, höchstens einmal im Zug. "
           "In der erzaehlung steht dann nur, dass sie in ihrer Sprache spricht, nie die Bedeutung; das Panel macht die "
           "fremden Laute und zeigt die Übersetzung nur, wer die Sprache kann."),
    "en": (" When a person of the scene briefly greets or cries out in the tongue of its people, give it in fremd (name, "
           "volk, sagt: what it means, at most 60 characters), only for short greetings and cries, at most once a turn. The "
           "erzaehlung then only says that it speaks in its tongue, never the meaning; the panel makes the foreign sounds "
           "and shows the translation only to who knows the tongue."),
}

_day = DayCounter(gesagt=0, verstanden=0, verworfen=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def task(rd, lang):
    return AUFGABE[lang] if on(rd) else ""


def tongues(r):
    """The tongues of this catalog: a people of SPRACHEN with its name syllables (pure)."""
    s = r.get("namensilben") or {}
    return [v for v in SPRACHEN if all((s.get(v) or {}).get(t) for t in ("anfang", "mitte", "ende"))]


def laut(r, volk, sagt):
    """The sounds of the meaning sagt in the people's tongue: every word a start, for a long word a middle, and an end
    of the people's syllables, chosen by the word's hash; the sentence's last mark stays (pure, the same sentence gives
    the same sounds)."""
    s = r["namensilben"][volk]
    out = []
    for w in WORT.findall(sagt.lower()):
        h = hashlib.sha256(f"{volk}|{w}".encode()).digest()
        a, m, e = s["anfang"][h[0] % len(s["anfang"])], s["mitte"][h[1] % len(s["mitte"])], s["ende"][h[2] % len(s["ende"])]
        out.append(a.lower() if len(w) <= 2 else (a + (m if len(w) > 5 else "") + e).lower())
    if not out:
        return ""
    t = " ".join(out)
    end = sagt.rstrip()[-1:]
    return t[:1].upper() + t[1:] + (end if end in ".!?" else ".")


def versteht(h, volk):
    """Whether the hero h understands the people's tongue: its own people's, a related one, a bard's or a wizard's."""
    return h.get("volk") == volk or volk in VERWANDT.get(h.get("volk"), ()) or h.get("klasse") in ALLE_KLASSEN


def check(dm, r, rd, x, text):
    """The narration's foreign line by fixed rules: {"name", "volk", "sprache", "laut", "sagt", "wer"} or None."""
    if not on(rd) or not isinstance(x, dict):
        return None
    import dungeon_vorlesen as vortrag
    name, volk = dm.plain(x.get("name"), 40), x.get("volk")
    sagt = dm.plain(x.get("sagt"), SAGT_MAX).strip(" „“\"»«")
    grund = ("sprache" if volk not in tongues(r) else "name" if not name else
             "laenge" if len(sagt) < 2 or len(WORT.findall(sagt)) > WOERTER else
             "wort" if dm.bad_words(r, rd, sagt) else "im text" if vortrag.in_text(sagt, text) else "")
    if grund:
        _day.bump("verworfen")
        print(f"dungeon: sprache | verworfen | {grund}", flush=True)
        return None
    li = 1 if rd.get("lang") == "en" else 0
    wer = [pid for pid, p in dm.seated(rd) if versteht(p["held"], volk)]
    _day.bump("gesagt")
    _day.bump("verstanden", len(wer))
    print(f"dungeon: sprache | {volk} | {len(wer)} verstehen", flush=True)
    return {"name": name, "volk": volk, "sprache": SPRACHEN[volk][li], "laut": laut(r, volk, sagt), "sagt": sagt, "wer": wer}


def keep(rd, f):
    """After the narration's log entry: its sounds stay in the log for everyone, the meaning only in rd["fremd"]."""
    if not f:
        return None
    rd["fremd"] = ((rd.get("fremd") or []) + [{"k": rd.get("dmk", 0), "sagt": f["sagt"], "wer": f["wer"]}])[-FREMD_MAX:]
    return {k: f[k] for k in ("name", "volk", "sprache", "laut")}


def view(rd, pid, host):
    """{narration number: meaning} for what this seat understands; the host as game master all of it."""
    return {str(x["k"]): x["sagt"] for x in rd.get("fremd") or [] if host or pid in x["wer"]}


def speak(dm, r, rd, e):
    """The foreign sounds read aloud in the speaker's NPC voice, after the narration."""
    f = (e or {}).get("fremd")
    if not f:
        return []
    fest, klang = dm._npc_voice(r, rd, f["name"], dm._stimmen["design"])
    return [(fest, f["laut"], klang)]


def for_live():
    """Numbers only: foreign lines said, seats that understood, lines refused today."""
    t = _day.counts()
    return {k: t[k] for k in ("gesagt", "verstanden", "verworfen")}
