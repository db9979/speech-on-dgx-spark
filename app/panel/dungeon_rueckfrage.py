"""KI-Dungeon-Master: Rückfrage bei unklaren Aktionen (Dominik 2026-10-26 „Wenn der Spieler keine klaren Ansagen
macht … könnte man da noch eine Rückfrage einbauen?“, Plan plaene/dungeon-rueckfrage.md, „wie empfehlung umsetzen“:
Stufe 1 und 3, Stufe 2 mit dem Modell erst später).

When a seat sends its action the panel checks the text by fixed rules (unclear): too short, gibberish, only a pronoun
as the target while more than one fits, or no doing at all (no word of the fixed verb lists, no name of the scene, no
quoted speech). Then the action is kept as written but marked (rd["offen"][pid]["frage"]): the seat sees „Was genau
tut Morpheus?“ with up to VORSCHLAEGE suggestions and „So lassen“. The suggestions come only from fixed patterns and the
scene's data (foes still up, the props of the fight, people here, the ways of the map, the hero's own attack spell),
never from the model's words. A marked action does not count as „everyone acted“ (dungeon.due), so the turn waits
for the seat until its time runs out; then the action counts as written. Tapping a suggestion puts its text into the
field; sending it replaces the action. „So lassen“ (so_lassen) takes the mark off. Never twice for the same text, never
blocking.

In the car (dungeon_auto): the question is said with the suggestions as „erstens …, zweitens …“, the CarPlay list
shows them as buttons; „die erste“ or a button sends that suggestion, „so lassen“ keeps the action.

Off by default: the admin's switch dungeonrueckfrage (features.py, chat.dungeon_rueckfrage) for the round's host;
guests at the table get it the same way (it is part of the game, not a tool).
Journal: „dungeon: rueckfrage | regel | kurz“ (salat, fuerwort, kein tun), „| vorschlag genommen“, „| so lassen“,
„| klar“; Live only counts.
"""
import re

import features
from common import DayCounter

KEY = "dungeonrueckfrage"
GRUENDE = ("kurz", "salat", "fuerwort", "kein_tun")
WOERTER_MIN = 2           # words of an action at least
BUCHSTABEN_MIN = 8        # letters of an action at least
VORSCHLAEGE = 3           # suggestions at most
VORSCHLAG_MAX = 80        # characters of one suggestion

FRAGE = ("Was genau tut {name}?", "What exactly does {name} do?")
WARUM = {"kurz": ("Die Aktion ist sehr kurz.", "The action is very short."),
         "salat": ("Die Aktion ist schwer zu lesen.", "The action is hard to read."),
         "fuerwort": ("Wen oder was meinst du genau?", "Whom or what do you mean exactly?"),
         "kein_tun": ("Es steht nicht da, was die Figur tut.", "It does not say what the character does.")}
MUSTER = {"angriff": ("Ich greife {x} an.", "I attack {x}."), "zauber": ("Ich wirke {z} auf {x}.", "I cast {z} at {x}."),
          "requisit": ("Ich nutze {x}.", "I use {x}."), "person": ("Ich spreche mit {x}.", "I talk to {x}."),
          "weg": ("Ich gehe {x}.", "I go {x}."), "umsehen": ("Ich sehe mich genau um.", "I look around carefully."),
          "abwarten": ("Ich halte mich bereit und beobachte die Gegner.", "I stay ready and watch the foes.")}

# what a character does: the fixed verbs (beside the fight's own lists in dungeon_kampf)
TUN_WORTE = re.compile(
    r"(?i)(?<!\w)(?:geh|lauf|renn|spring|kletter|schleich|versteck|flieh|folg|komm|tret|wart|bleib|setz|leg|steh|"
    r"sprech|sprich|sag|frag|ruf|antwort|rede|red|erzähl|erzaehl|bitt|biet|droh|überred|ueberred|lüg|lueg|"
    r"nehm|nimm|heb|greif|pack|gib|geb|reich|zeig|steck|zieh|trink|ess|iss|öffn|oeffn|schließ|schliess|"
    r"such|untersuch|prüf|pruef|schau|seh|sieh|beobacht|lausch|hör|hoer|riech|tast|lies|les|"
    r"wirk|zauber|heil|hilf|helf|schütz|schuetz|bet|sing|spiel|bau|repar|brech|knack|schneid|wirf|werf|"
    r"go|walk|run|jump|climb|sneak|hide|flee|follow|come|step|wait|stay|sit|stand|"
    r"say|ask|call|answer|talk|speak|tell|beg|offer|threaten|persuade|lie|"
    r"take|grab|pick|give|hand|show|put|pull|drink|eat|open|close|shut|"
    r"search|examine|inspect|check|look|watch|listen|smell|feel|read|"
    r"cast|heal|help|protect|pray|sing|play|build|repair|break|cut|throw|use|nutz|benutz|verwend)\w*")
# a pronoun as the last thing the action names („nimm es“, „greif ihn an“, „take it“), never an article before a noun
FUERWORT = re.compile(r"(?i)(?<!\w)(?:es|ihn|ihm|das|dies|it|him|her|them|that|this)\s*(?:an|auf|mit|um|weg|hoch|ab|up|on|down|out)?\W*$")
_ANF = re.compile(r"[„“\"»«]")
_VOKAL = re.compile(r"(?i)[aeiouäöüyáéíóú]")

_day = DayCounter(gefragt=0, kurz=0, salat=0, fuerwort=0, kein_tun=0, genommen=0, so_lassen=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def _names(dm, r, rd, pid):
    """Every name the scene knows for this seat: foes still up, the fight's props, people (here and elsewhere), places,
    the hero's things and powers (both languages where the catalog has them), the other heroes."""
    import dungeon_karte
    import dungeon_kampf
    import dungeon_umgebung
    out = set()
    for g in dungeon_kampf.up(rd) if rd.get("kampf") else []:
        out.add(re.sub(r"\s+\d+$", "", str(g.get("name", ""))))
    for row in dungeon_umgebung.here(r, rd):
        out |= set(row["name"])
    out |= {str(x.get("name", "")) for x in (rd.get("nsc") or {}).values()}
    le = dungeon_karte.leute(rd)
    out |= set(le["hier"]) | {x["name"] for x in le["anderswo"]} | set(le["mit"])
    out |= {w["ziel"] for w in dungeon_karte.wege(rd, rd.get("lang", "de"))}
    out |= {str(p["held"]["name"]) for _, p in dm.seated(rd) if p.get("held")}
    h = ((rd.get("plaetze") or {}).get(pid) or {}).get("held") or {}
    cat = dm._by(r, "gegenstaende")
    for it in [*(h.get("tasche") or []), *dm.worn(h)] if h else []:
        out |= set((cat.get(it.get("id")) or {}).get("name") or [])
    if h:
        k = dm.powers(r, h, rd.get("lang", "de"))
        out |= {str(x.get("name", "")) for x in k["faehigkeiten"] + k["zauber"]}
    return {n.lower() for n in out if len(n) >= 3}


def _named(names, low):
    return any(re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", low) or (len(n) >= 5 and n.split()[-1] in low.split())
               for n in names)


def unclear(dm, r, rd, pid, text):
    """The reason (GRUENDE) an action is unclear by the fixed rules, "" when it is clear."""
    import dungeon_kampf
    t = str(text or "").strip()
    low = t.lower()
    words = re.findall(r"[^\W\d_]+", low)
    if len(words) < WOERTER_MIN or sum(len(w) for w in words) < BUCHSTABEN_MIN:
        return "kurz"
    if re.search(r"(.)\1{3}", low) or sum(1 for w in words if len(w) > 3 and not _VOKAL.search(w)) * 2 >= len(words):
        return "salat"
    if _ANF.search(t):                           # the character says something: that is its doing
        return ""
    names = _names(dm, r, rd, pid)
    named = _named(names, low)
    doing = bool(TUN_WORTE.search(low) or dungeon_kampf.ANGRIFF_WORTE.search(low) or dungeon_kampf.BEZUG_WORTE.search(low)
                 or dungeon_kampf.MAGIE_WORTE.search(low) or dungeon_kampf.FRIEDEN_WORTE.search(low))
    if doing and not named and FUERWORT.search(low) and len(words) <= 6 and _choices(r, rd) > 1:
        return "fuerwort"                        # „nimm es“, „greif ihn an“ while more than one fits
    if not doing and not named:
        return "kein_tun"
    return ""


def _choices(r, rd):
    """How many things a pronoun may mean here: foes up in a fight, else props, people here and ways."""
    import dungeon_karte
    import dungeon_kampf
    import dungeon_umgebung
    if rd.get("kampf"):
        return len(dungeon_kampf.up(rd)) + len(dungeon_umgebung.here(r, rd))
    return len(dungeon_karte.leute(rd)["hier"]) + len(dungeon_karte.wege(rd, rd.get("lang", "de")))


def points(dm, r, rd, pid, wege=1):
    """The scene's points for this seat from its data only, never the model's words (one source for the suggestions
    here and dungeon_anleiten): [{art, x, z?}] with art a key of MUSTER; in a fight the foes still up (the weakest
    first, the hero's own attack spell on the first), one prop of the fight and waiting, else people here, up to wege
    ways of the map (only what a seat may see) and a look round."""
    import dungeon_karte
    import dungeon_kampf
    import dungeon_umgebung
    li = 1 if rd.get("lang") == "en" else 0
    h = ((rd.get("plaetze") or {}).get(pid) or {}).get("held") or {}
    out = []
    if rd.get("kampf"):
        foes = sorted(dungeon_kampf.up(rd), key=lambda g: (g.get("leben", 0), g.get("k", 0)))
        out += [{"art": "angriff", "x": g["name"]} for g in foes[:2]]
        z = _attack_spell(dm, r, h, li) if h else ""
        if z and foes:
            out.insert(1, {"art": "zauber", "x": foes[0]["name"], "z": z})
        out += [{"art": "requisit", "x": row["name"][li]} for row in dungeon_umgebung.here(r, rd)[:1]]
        out.append({"art": "abwarten", "x": ""})
    else:
        out += [{"art": "person", "x": n} for n in dungeon_karte.leute(rd)["hier"][:2]]
        for w in dungeon_karte.wege(rd, ("de", "en")[li])[:wege]:
            d = w["richtung"]
            out.append({"art": "weg", "x": (d if li or d in ("hinaus", "hinein") else "nach " + d) if d else w["ziel"]})
        out.append({"art": "umsehen", "x": ""})
    return out


def say(p, li):
    """A point as the seat's own action (MUSTER)."""
    return MUSTER[p["art"]][li].format(x=p["x"], z=p.get("z", ""))[:VORSCHLAG_MAX]


def suggestions(dm, r, rd, pid):
    """Up to VORSCHLAEGE suggestions for the seat from fixed patterns and the scene's data, never the model's words."""
    li = 1 if rd.get("lang") == "en" else 0
    return list(dict.fromkeys(say(p, li) for p in points(dm, r, rd, pid)))[:VORSCHLAEGE]


def _attack_spell(dm, r, h, li):
    """The name of the hero's own attack spell of grade 0 with a damage kind, "" for none."""
    cat = dm._by(r, "gegenstaende")
    z = (dm._by(r, "klassen").get(h.get("klasse")) or {}).get("zauber") or {}
    c = next((cat[x] for x in z.get("0") or [] if x in cat and cat[x].get("schaden_art")), None)
    return c["name"][li].split(": ", 1)[-1] if c else ""


def check(dm, r, rd, pid, so_lassen=False):
    """After dungeon.act, inside the lock: marks the seat's new action when it is unclear (with the question and the
    suggestions), never the same text twice; so_lassen takes a mark off and keeps the action as written."""
    a = (rd.get("offen") or {}).get(pid)
    if not a or not on(rd):
        return
    alt = (rd.get("rueckfrage") or {}).get(pid) or {}
    alt = alt if alt.get("zug") == rd.get("zug") else {}
    if so_lassen:                                # „So lassen“ or a suggestion tapped in the car: as it is, never asked again
        a.pop("frage", None)
        if alt.get("text") == a["text"]:
            _day.bump("so_lassen")
            print("dungeon: rueckfrage | so lassen", flush=True)
        elif a["text"] in (alt.get("vorschlaege") or []):
            _day.bump("genommen")
            print("dungeon: rueckfrage | vorschlag genommen", flush=True)
        a["klar"] = a["text"]
        return
    if a.get("klar") == a["text"] or alt.get("text") == a["text"]:
        return                                  # asked once for this text already, or kept as it is
    if alt.get("vorschlaege") and a["text"] in alt["vorschlaege"]:
        _day.bump("genommen")
        print("dungeon: rueckfrage | vorschlag genommen", flush=True)
    why = unclear(dm, r, rd, pid, a["text"])
    if not why:
        print("dungeon: rueckfrage | klar", flush=True)
        return
    h = rd["plaetze"][pid]["held"]
    li = 1 if rd.get("lang") == "en" else 0
    a["frage"] = {"grund": why, "frage": FRAGE[li].format(name=h["name"]), "warum": WARUM[why][li],
                  "vorschlaege": suggestions(dm, r, rd, pid)}
    rd.setdefault("rueckfrage", {})[pid] = {"text": a["text"], "vorschlaege": a["frage"]["vorschlaege"], "zug": rd["zug"]}
    _day.bump("gefragt")
    _day.bump(why)
    print(f"dungeon: rueckfrage | regel | {why.replace('_', ' ')}", flush=True)


def waiting(rd, pid):
    """Whether the seat's action still waits for its answer to the question (dungeon.due waits for it)."""
    return bool(((rd.get("offen") or {}).get(pid) or {}).get("frage"))


def view(rd, pid):
    """The seat's own question for the table: {frage, warum, vorschlaege} or None."""
    f = ((rd.get("offen") or {}).get(pid) or {}).get("frage")
    return {k: f[k] for k in ("frage", "warum", "vorschlaege")} if f else None


def car(rd, pid, li):
    """The question as one sentence for the car: the suggestions as „erstens …“, then „so lassen“."""
    f = view(rd, pid)
    if not f:
        return ""
    nth = (("Erstens", "zweitens", "drittens"), ("First", "second", "third"))[li]
    rest = " ".join(f"{nth[i]}: {x}" for i, x in enumerate(f["vorschlaege"]))
    tail = ("Oder sag „so lassen“.", "Or say \"keep it\".")[li]
    return " ".join(x for x in (f["frage"], f["warum"], rest, tail) if x)


SO_LASSEN = re.compile(r"(?i)^\W*(?:so lassen|lass es so|passt so|so ist gut|bleibt so|keep it|leave it|as it is)\W*$")
NTH = re.compile(r"(?i)^\W*(?:die |den |der |the )?(erste|ersten|eins|zweite|zweiten|zwei|dritte|dritten|drei|first|second|third|1|2|3)"
                 r"\.?(?: vorschlag| suggestion| one)?\W*$")
_NTH = {"erste": 0, "ersten": 0, "eins": 0, "first": 0, "1": 0, "zweite": 1, "zweiten": 1, "zwei": 1, "second": 1, "2": 1,
        "dritte": 2, "dritten": 2, "drei": 2, "third": 2, "3": 2}


def answer(rd, pid, text):
    """The car's answer to the seat's open question: the suggestion named by its number, the action as written for
    „so lassen“, "" for anything else (a new action, checked again). Only what this file offered, never a text of
    the app."""
    q = (rd.get("rueckfrage") or {}).get(pid) or {}
    if q.get("zug") != rd.get("zug") or not waiting(rd, pid):
        return ""
    if SO_LASSEN.match(str(text or "")):
        return q["text"]
    m = NTH.match(str(text or ""))
    i = _NTH[m.group(1).lower()] if m else None
    return q["vorschlaege"][i] if i is not None and i < len(q["vorschlaege"]) else ""


def for_live():
    """Numbers only: questions asked today by reason, suggestions taken, actions kept as written."""
    return _day.counts()
