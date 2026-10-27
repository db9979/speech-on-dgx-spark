"""KI-Dungeon-Master: Spieler anleiten (Plan dungeon-anleitung/plan.md, Dominik 2026-10-27 „1-5“; question of
Dominik: „wie bekommen wir bessere Texte vom Dungeon Master, um mehr den Spieler anzuleiten, was man tun kann“).

Step 1 (ideas 3, 7 and 10 of the plan): the narration takes a fixed form and ends with something to grab.
  - The narrator's task (task): first what the deeds caused, then what is to be seen now, and every narration names
    at least two things the group can take up (a person to speak to, a thing to examine, a way out), by names of the
    facts or of its own narration; it ends with a concrete choice for one figure, never a hollow „What do you do?“.
  - Per world one model narration that ends with such points (welten[].anleiten in the rules, one pair [de, en],
    checked like the style examples, dungeon_erzaehler.style_text adds it).
  - A quiet seat (dungeon.STILL turns without an action) gets a question the panel builds from the scene's data
    (still_question: people here, ways of the map, foes in a fight), never the model's words: „Bela, sprichst du mit
    Grimma, oder gehst du nach Norden?“. With fewer than two points the old line stays.

Step 2 (ideas 1, 2, 8 and 9): „Das kannst du hier“ under every narration.
  - Per seat up to KNOEPFE[stufe] buttons built only from data (buttons): the narrator's ways of this turn that passed
    the fixed rules (check_ways), the scene's points of dungeon_rueckfrage.points (one source with the Rückfrage: foes,
    a prop, people here, ways of the map, a look round), a healing spell or potion when someone is badly hurt, a thing
    of the scene (dungeon_erzaehler._near) and an open thread. Tapping puts the text into the field (as the prologue's
    ways); an action that is one of them counts as taken (taken).
  - The narrator may give 2 to 3 ways in wege every turn; the panel takes at most MODELL_WEGE that are short, have a
    doing word (dungeon_rueckfrage.TUN_WORTE), name something the scene or the narration knows, have no refused word
    and no word only a later act, the turning point or a secret of the truth knows (check_ways).
  - The level per round (STUFEN, the host chooses it beside the way of telling, choose): einsteiger shows four buttons
    with the value that likely counts (WURF, a fixed table, never the difficulty) and the car reads them after the
    narration; normal three buttons; erfahren none, only the form of step 1.
  - In the car „Was kann ich tun?“ says the buttons, the CarPlay list shows them (car, answer).

Off by default: the admin's switch dungeonanleiten (features.py, chat.dungeon_anleiten) for the round's host; a guest at
the table gets it like everyone, it is part of the game and no tool.
Journal: fixed words and numbers („dungeon: anleitung | …“), Live only counts.
"""
import re

import features
from common import DayCounter

KEY = "dungeonanleiten"
WAHL = {                   # the second person's choices of the quiet seat's question
    "person": ("sprichst du mit {x}", "do you talk to {x}"),
    "weg": ("gehst du {x}", "do you go {x}"),
    "angriff": ("greifst du {x} an", "do you attack {x}"),
    "umsehen": ("siehst du dich hier genauer um", "do you look around here more closely"),
    "zauber": ("wirkst du {z} auf {x}", "do you cast {z} at {x}"),
    "requisit": ("nutzt du {x}", "do you use {x}"),
}

STUFEN = {"einsteiger": ("Einsteiger", "Beginner"), "normal": ("Normal", "Normal"), "erfahren": ("Erfahren", "Experienced")}
STUFE = "normal"
KNOEPFE = {"einsteiger": 4, "normal": 3, "erfahren": 0}
MODELL_WEGE = 2            # the narrator's ways taken per turn at most
WEG_MAX = 80
WORT_MIN = 5               # letters of a word that names something (check_ways)
MUSTER = {"ding": ("Ich untersuche {x}.", "I examine {x}."), "heilen": ("Ich wirke {z} auf {x}.", "I cast {z} on {x}."),
          "trank": ("Ich trinke {x}.", "I drink {x}."), "faden": ("Ich gehe dem nach: {x}", "I follow this up: {x}")}
# the value that likely counts for a kind of button (einsteiger), and for a way of the narrator by its doing word
WURF = {"person": "charisma", "ding": "intelligenz", "umsehen": "weisheit", "requisit": "geschick"}
WURF_WORTE = (("charisma", r"sprech|sprich|frag|überred|ueberred|bitt|verhandel|talk|ask|persuade|bargain|beg"),
              ("geschick", r"schleich|kletter|versteck|knack|spring|sneak|climb|hide|pick|jump"),
              ("intelligenz", r"untersuch|such|prüf|pruef|lies|les|entziffer|examine|search|inspect|read|study"),
              ("weisheit", r"lausch|beobacht|späh|spaeh|spür|spuer|listen|watch|track|spot"),
              ("staerke", r"brech|heb|stemm|drück|drueck|zieh|break|lift|force|push|pull"))
SO_LASSEN = ("so lassen", "keep it")

_day = DayCounter(frage=0, frage_alt=0, zeile=0, genommen=0, weg=0, weg_verworfen=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


TASK = {
    "de": (" Form jeder Erzählung: erst, was die Taten bewirken, dann, was jetzt zu sehen ist. Nenne in jeder Erzählung "
           "mindestens zwei greifbare Ansatzpunkte mit Namen (eine Person, die man ansprechen kann, ein Ding, das man "
           "untersuchen kann, einen Ausgang oder Weg), nur aus den Fakten oder deiner eigenen Erzählung. Ende mit einer "
           "konkreten Wahl an eine Figur, etwa „Folgt ihr den Spuren zum Lagerhaus, oder fragt ihr Grimma?“, nie mit "
           "einer leeren Frage wie „Was tut ihr?“."),
    "en": (" Form of every narration: first what the deeds cause, then what is to be seen now. Name in every narration at "
           "least two things to take up, with names (a person to speak to, a thing to examine, an exit or way), only "
           "from the facts or your own narration. End with a concrete choice for one figure, such as \"Do you follow "
           "the tracks to the warehouse, or do you ask Grimma?\", never with an empty question like \"What do you do?\"."),
}


WEGE_TASK = {
    "de": (" Schlage in wege zwei bis drei kurze nächste Schritte aus der Geschichte vor (je ein Tun und etwas, das in deiner "
           "Erzählung oder den Fakten vorkommt, höchstens 80 Zeichen, etwa „Dem Lehrling zur Gießerei folgen“); verrate darin "
           "nichts, was die Gruppe noch nicht weiß."),
    "en": (" Suggest in wege two to three short next steps from the story (each a doing and something that appears in your "
           "narration or the facts, at most 80 characters, such as \"Follow the apprentice to the foundry\"); reveal nothing "
           "in them the group does not know yet."),
}


def task(rd, lang):
    """The narrator's form (step 1) and, unless the level is erfahren, the ways of the turn (step 2); "" while off."""
    if not on(rd):
        return ""
    return TASK[lang] + (WEGE_TASK[lang] if KNOEPFE[stufe(rd)] else "")


def example(r, rd, li):
    """The world's model narration with points to take up, [] while off or without one."""
    if not on(rd):
        return []
    w = next((x for x in r.get("welten") or [] if x.get("id") == rd.get("welt")), None) or {}
    p = w.get("anleiten")
    return [p[li]] if isinstance(p, list) and len(p) == 2 else []


def _points(dm, r, rd, pid):
    """The quiet seat's choices from the scene's data (dungeon_rueckfrage.points, the one source): in a fight the foes
    standing and the hero's attack spell, else people here and ways of the map, a look round as the second when there
    is only one."""
    import dungeon_rueckfrage as rf
    li = _li(rd)
    pts = [p for p in rf.points(dm, r, rd, pid, wege=2) if p["art"] in WAHL]
    out = [WAHL[p["art"]][li].format(x=p["x"], z=p.get("z", "")) for p in pts if p["art"] != "umsehen"]
    return out + [WAHL["umsehen"][li]] if len(out) == 1 and not rd.get("kampf") else out


def still_question(dm, r, rd, pid):
    """The panel's question to a quiet seat: two choices of the scene for this hero, None while off or with fewer
    than two (then the old line stays)."""
    if not on(rd):
        return None
    p = list(dict.fromkeys(_points(dm, r, rd, pid)))[:2]
    if len(p) < 2:
        _day.bump("frage_alt")
        print("dungeon: anleitung | frage | zu wenig", flush=True)
        return None
    _day.bump("frage")
    print("dungeon: anleitung | frage | 2", flush=True)
    return f"{rd['plaetze'][pid]['held']['name']}, {p[0]}, {('oder', 'or')[_li(rd)]} {p[1]}?"


def stufe(rd):
    s = rd.get("anleitstufe")
    return s if s in STUFEN else STUFE


def choose(rd, s):
    """The host's level for the round (dungeon.erzaehler {anleitung}); ValueError while off or for another word."""
    if not on(rd) or s not in STUFEN:
        raise ValueError()
    rd["anleitstufe"] = s


def _li(rd):
    return 1 if rd.get("lang") == "en" else 0


def _words(t):
    return set(re.findall(r"[^\W\d_]{%d,}" % WORT_MIN, str(t or "").lower()))


def _secret(rd):
    """Words only a later act, the current act's turning point or a secret of the truth knows."""
    p = rd.get("plan") or {}
    akte, i = p.get("akte") or [], rd.get("akt", 0)
    out = set()
    for a in akte[i + 1:]:
        out |= _words(" ".join(str(a.get(k, "")) for k in ("titel", "inhalt", "wende")))
    if i < len(akte):
        out |= _words(akte[i].get("wende", ""))
    for g in (rd.get("wahrheit") or {}).get("geheimnisse") or []:
        out |= _words(g)
    return out


def check_ways(dm, r, rd, obj, text):
    """The narrator's wege of a turn by fixed rules (dungeon.check_story): at most MODELL_WEGE, each short, with a doing
    word, naming something the scene or the narration knows, without a refused word and without a word only a later
    act, the turning point or a secret knows. [] while off or at the level erfahren."""
    import dungeon_rueckfrage as rf
    if not on(rd) or not KNOEPFE[stufe(rd)] or not isinstance(obj, list):
        return []
    known = _words(text) | {w for n in rf._names(dm, r, rd, "") for w in _words(n)}
    hidden = _secret(rd) - known
    out, seen, drop = [], set(), {"regel": 0, "geheim": 0}
    for w in obj[:MODELL_WEGE * 3]:
        t = dm.plain(w, WEG_MAX)
        own = _words(t)
        if own & hidden:                         # names what only a later act, the turning point or a secret knows
            drop["geheim"] += 1
            continue
        if len(out) >= MODELL_WEGE or len(t) < 5 or t.lower() in seen or not rf.TUN_WORTE.search(t.lower()) \
                or not own & known or dm.bad_words(r, rd, t):
            drop["regel"] += 1
            continue
        seen.add(t.lower())
        out.append(t)
    for k, n in drop.items():
        if n:
            _day.bump("weg_verworfen", n)
            print(f"dungeon: anleitung | weg verworfen | {k} {n}", flush=True)
    if out:
        _day.bump("weg", len(out))
        print(f"dungeon: anleitung | weg | {len(out)}", flush=True)
    return out


def keep_ways(rd, wege):
    """The checked ways for the turn the narration opens (dungeon.apply, before the turn is counted on)."""
    if on(rd):
        rd["anleitwege"] = {"zug": rd.get("zug", 0) + 1, "wege": list(wege or [])}


def _hurt(dm, rd):
    """The seated hero worst hurt below half its life (not down or dead), or None."""
    hs = [p["held"] for _, p in dm.seated(rd) if not dm.zustand(p["held"]) and p["held"]["leben"] * 2 < p["held"]["leben_max"]]
    return min(hs, key=lambda h: h["leben"] / max(1, h["leben_max"])) if hs else None


def _care(dm, r, rd, h, li):
    """A healing spell the hero can cast now on the worst hurt, else a healing potion of its bag when it is hurt itself."""
    wer = _hurt(dm, rd)
    if not wer:
        return []
    cat = dm._by(r, "gegenstaende")
    z = next((x for x in dm.powers(r, h, rd.get("lang", "de"))["zauber"] if (cat.get(x["id"]) or {}).get("heilung")
              and (x["rest"] is None or x["rest"] > 0)), None)
    if z:
        return [{"art": "heilen", "x": wer["name"], "z": z["name"]}]
    if wer is h:
        tr = next((x for x in h.get("tasche") or [] if (cat.get(x.get("id")) or {}).get("art") == "trank"
                   and (cat.get(x.get("id")) or {}).get("heilung")), None)
        if tr:
            return [{"art": "trank", "x": dm.item_view(r, tr, rd.get("lang", "de"))["name"]}]
    return []


def _wurf(art, text):
    if art in WURF:
        return WURF[art]
    if art == "modell":
        low = text.lower()
        return next((w for w, rx in WURF_WORTE if re.search(r"(?<!\w)(?:" + rx + r")", low)), "")
    return ""


def buttons(dm, r, rd, pid):
    """„Das kannst du hier“ for this seat: [{text, wert}] from data only, [] while off, at the level erfahren, for a
    seat that has acted, is down or waits, and while the narrator tells."""
    import dungeon_erzaehler as erz
    import dungeon_rueckfrage as rf
    p = (rd.get("plaetze") or {}).get(pid) or {}
    h = p.get("held")
    n = KNOEPFE[stufe(rd)] if on(rd) else 0
    if not n or not h or rd.get("status") != "laeuft" or rd.get("dm") or pid in (rd.get("offen") or {}) or p.get("wartet") \
            or dm.zustand(h):
        return []
    li = _li(rd)
    w = rd.get("anleitwege") or {}
    pts = [{"art": "modell", "x": t} for t in (w.get("wege") or [] if w.get("zug") == rd.get("zug") else [])]
    care = _care(dm, r, rd, h, li)
    scene = rf.points(dm, r, rd, pid, wege=2)
    if rd.get("kampf"):
        pts += scene[:1] + care + scene[1:]
    else:
        heroes = {q["held"]["name"].lower() for _, q in dm.seated(rd)}
        dinge = [{"art": "ding", "x": x["name"]} for x in erz._near(rd) if x["name"].lower() not in heroes][-1:]
        faden = [{"art": "faden", "x": f} for f in (rd.get("faeden") or [])[:1]]
        rest = [x for x in scene if x["art"] != "umsehen"]
        pts += care + rest[:2] + dinge + rest[2:] + faden + [x for x in scene if x["art"] == "umsehen"]
    werte = {x["id"]: x["name"][li] for x in r["werte"]} if stufe(rd) == "einsteiger" else {}
    out, seen = [], set()
    for x in pts:
        t = x["x"] if x["art"] == "modell" else (MUSTER[x["art"]][li] if x["art"] in MUSTER else rf.MUSTER[x["art"]][li]).format(x=x["x"], z=x.get("z", ""))
        t = t[:WEG_MAX]
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append({"text": t, "wert": werte.get(_wurf(x["art"], t), "")})
    return out[:n]


def told(dm, r, rd):
    """After a narration (dungeon.apply, the next turn open): one line with the seats that get buttons."""
    if not on(rd) or not KNOEPFE[stufe(rd)]:
        return
    n = sum(1 for pid, _ in dm.seated(rd) if buttons(dm, r, rd, pid))
    if n:
        _day.bump("zeile")
        print(f"dungeon: anleitung | zeile | {n}", flush=True)


def taken(dm, r, rd, pid, text, offered):
    """An action that is one of the seat's buttons (dungeon.act, offered before it was written) counts as taken."""
    if offered and str(text or "").strip().lower() in {b["text"].lower() for b in offered}:
        _day.bump("genommen")
        print("dungeon: anleitung | knopf genommen", flush=True)


def view(dm, r, rd, pid, host):
    """The table's part: the seat's buttons, and for the host the level with its choice; None while off."""
    if not on(rd):
        return None
    li = _li(rd)
    return {"knoepfe": buttons(dm, r, rd, pid), "stufe": stufe(rd),
            "wahl": [[k, v[li]] for k, v in STUFEN.items()] if host else None}


def car(dm, r, rd, pid, li):
    """„Was kann ich tun?“ in the car: the sentence and the buttons for the CarPlay list, None without buttons."""
    b = [x["text"] for x in buttons(dm, r, rd, pid)]
    if not b:
        return None
    nth = (("Erstens", "zweitens", "drittens", "viertens"), ("First", "second", "third", "fourth"))[li]
    s = ("Du kannst hier: ", "You can here: ")[li] + " ".join(f"{nth[i]}: {x}" for i, x in enumerate(b[:3]))
    return {"sagen": s, "vorschlaege": b[:3], "titel": ("Das kannst du hier", "What you can do here")[li]}


def answer(dm, r, rd, pid, text):
    """The car's pick from the list: a button by its number or its text, "" for anything else."""
    import dungeon_rueckfrage as rf
    b = [x["text"] for x in buttons(dm, r, rd, pid)][:3]
    t = str(text or "").strip()
    m = rf.NTH.match(t)
    i = rf._NTH[m.group(1).lower()] if m else None
    if i is not None:
        return b[i] if i < len(b) else ""
    return next((x for x in b if x.lower() == t.lower()), "")


def for_live():
    """Numbers only: questions to quiet seats built from the scene and those that kept the old line, lines of buttons
    shown, buttons taken, the narrator's ways taken and refused."""
    return _day.counts()
