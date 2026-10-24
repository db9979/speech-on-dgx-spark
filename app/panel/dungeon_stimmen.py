"""KI-Dungeon-Master: voices made from descriptions (Dominik 2026-10-23 „erzähler stimmen und die der npc ... generiert
je nach stimmung und karakter, auch die des erzählers variieren von geschichte zu geschichte“, „1-4“).

With the speech output's VoiceDesign (Einstellungen → Sprachausgabe → „VoiceDesign zusätzlich bereitstellen“) every
voice of a round is a description in words instead of one fixed voice name:
- the narrator: the panel picks one of the fixed descriptions of the world (dungeon_stimmen.json „erzaehler“) when a
  round starts, not one of the owner's last rounds; a campaign keeps it from chapter to chapter; the host may roll a
  new one or pick one (pick)
- the mood of the scene (szene.stimmung, the model's words) colours it: fixed key words map it to a fixed addition
- every NPC its own voice: the model only names traits from fixed lists (age, gender, sound, nature) the first time a
  person speaks; the panel builds the description from fixed English words and keeps it for the round (and the
  campaign); a person without traits gets them from its name, always the same
Every description is the panel's own text, never the model's. Without VoiceDesign the round reads with the fixed
voices of the rules (stimmen) as before.

State in the round: rd["erzaehler"] "<welt>:<i>", rd["npc_stimmen"] {name lower: {alter, geschlecht, klang, wesen}}.
"""
import hashlib
import json
import os
import random
import re

QUELLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dungeon_stimmen.json")
NPC_MAX = 40               # NPC voices kept per round
ZULETZT = 3                # a new round's narrator is none of the owner's last this many
TEXT_MAX = 80              # a description (as for a hero's voice, dungeon.KLANG)
MERKMALE = ("alter", "geschlecht", "klang", "wesen")
_TEXT = re.compile(r"[A-Za-z0-9 ,.\-]{10,%d}" % TEXT_MAX)
_data = {}

AUFGABE = {
    "de": " Spricht ein NPC zum ersten Mal, gib in seiner stimme an, wie er klingt (alter, geschlecht, klang, wesen aus "
          "den Listen); bei bekannten NPCs lass stimme weg.",
    "en": " When an NPC speaks for the first time, say in its stimme how it sounds (alter, geschlecht, klang, wesen from "
          "the lists); leave stimme out for known NPCs."}


def data():
    if not _data:
        with open(QUELLE, encoding="utf-8") as f:
            _data.update(json.load(f))
    return _data


def schema():
    """The NPC's stimme in the narration's JSON: only the fixed lists."""
    n = data()["npc"]
    return {"type": "object", "additionalProperties": False,
            "properties": {k: {"type": "string", "enum": list(n[k])} for k in MERKMALE}}


def check(d, welten):
    """Mistakes in the voice texts (test): every world or „alle“, labels in both languages, descriptions the speech
    output takes (letters, digits, space, comma, dot, hyphen; at most TEXT_MAX, also with each mood)."""
    err = []
    e = d.get("erzaehler") or {}
    if not e.get("alle"):
        err.append("erzaehler.alle fehlt")
    for w, xs in e.items():
        if w != "alle" and w not in welten:
            err.append(f"erzaehler.{w}: keine Welt")
        for i, x in enumerate(xs):
            if not (isinstance(x, list) and len(x) == 3 and all(isinstance(s, str) and 3 <= len(s) <= 60 for s in x[:2])
                    and _TEXT.fullmatch(x[2])):
                err.append(f"erzaehler.{w}[{i}]")
    for k, (words, add) in (d.get("stimmung") or {}).items():
        if not words or not all(isinstance(s, str) and s == s.lower() for s in words) or not re.fullmatch(r"[a-z ,]{5,40}", add):
            err.append(f"stimmung.{k}")
    n = d.get("npc") or {}
    for k in MERKMALE:
        if not n.get(k) or not all(re.fullmatch(r"[a-z]{2,12}", a) and re.fullmatch(r"[a-z ]{3,30}", b) for a, b in n[k].items()):
            err.append(f"npc.{k}")
    return err


def _pool(welt):
    e = data()["erzaehler"]
    return [f"{welt}:{i}" for i in range(len(e.get(welt) or []))] + [f"alle:{i}" for i in range(len(e["alle"]))]


def _entry(key):
    w, _, i = str(key or "").rpartition(":")
    xs = data()["erzaehler"].get(w) or []
    return xs[int(i)] if i.isdigit() and int(i) < len(xs) else None


def pick(rd, others=(), rng=None):
    """The narrator of a new round: one of its world's (or „alle“), none of the owner's last ZULETZT rounds."""
    pool = _pool(rd.get("welt", ""))
    free = [k for k in pool if k not in list(others)[-ZULETZT:]] or pool
    rd["erzaehler"] = (rng or random).choice(free)
    return rd["erzaehler"]


def choose(rd, key, rng=None):
    """The host's choice: a key of the world's list, or "" for a new one (not the current)."""
    pool = _pool(rd.get("welt", ""))
    if key:
        if key not in pool:
            raise ValueError("stimme")
        rd["erzaehler"] = key
    else:
        rd["erzaehler"] = (rng or random).choice([k for k in pool if k != rd.get("erzaehler")] or pool)
    return rd["erzaehler"]


def mood(stimmung):
    """The fixed addition for the scene's mood (the model's words, only matched against fixed key words)."""
    low = str(stimmung or "").lower()
    for _, (words, add) in data()["stimmung"].items():
        if any(w in low for w in words):
            return add
    return ""


def narrator(rd):
    """The narrator's description for the turn: its voice and the scene's mood."""
    x = _entry(rd.get("erzaehler")) or _entry(_pool(rd.get("welt", ""))[0])
    m = mood((rd.get("szene") or {}).get("stimmung"))
    return x[2] + (", " + m if m else "")


def _traits(name):
    """Traits from the name alone, always the same for it."""
    n = data()["npc"]
    h = hashlib.sha256(name.lower().encode()).digest()
    return {k: list(n[k])[h[i] % len(n[k])] for i, k in enumerate(MERKMALE)}


def learn(rd, npcs):
    """The traits the model gave for NPCs that speak for the first time (only values of the fixed lists)."""
    n, keep = data()["npc"], rd.setdefault("npc_stimmen", {})
    for x in npcs or []:
        name = str(x.get("name") or "").strip().lower()[:40]
        if not name or name in keep or len(keep) >= NPC_MAX:
            continue
        s = x.get("stimme") if isinstance(x.get("stimme"), dict) else {}
        base = _traits(name)
        keep[name] = {k: s[k] if s.get(k) in n[k] else base[k] for k in MERKMALE}


def npc(rd, name):
    """One NPC's description: its traits as fixed English words."""
    n = data()["npc"]
    t = (rd.get("npc_stimmen") or {}).get(str(name or "").strip().lower()[:40]) or _traits(str(name or "?"))
    who = {"weiblich": "a girl", "maennlich": "a boy"}.get(t["geschlecht"], "a child") if t["alter"] == "kind" \
        else f"{n['alter'][t['alter']]} {n['geschlecht'][t['geschlecht']]}"
    return f"{who[0].upper()}{who[1:]}, {n['klang'][t['klang']]}, {n['wesen'][t['wesen']]}"


def weiblich(rd, name):
    """Whether an NPC is a woman or a girl by its kept traits (or those of its name): the fixed female NPC voice."""
    t = (rd.get("npc_stimmen") or {}).get(str(name or "").strip().lower()[:40]) or _traits(str(name or "?"))
    return t.get("geschlecht") == "weiblich"


def keep(rd):
    """What a campaign carries to its next chapter."""
    return {k: rd[k] for k in ("erzaehler", "npc_stimmen") if rd.get(k)}


def view(rd, lang, host):
    """The narrator's label for the table; the host also gets the list to choose from."""
    li = 1 if lang == "en" else 0
    x = _entry(rd.get("erzaehler"))
    out = {"erzaehler": x[li] if x else ""}
    if host:
        out["erzaehler_k"] = rd.get("erzaehler", "")
        out["erzaehler_liste"] = [{"k": k, "name": _entry(k)[li]} for k in _pool(rd.get("welt", ""))]
    return out


def probe_text(key):
    """The description of a narrator key for a sample (dungeon.probe), without mood."""
    x = _entry(key)
    return x[2] if x else ""
