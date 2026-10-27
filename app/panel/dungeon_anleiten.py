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

Step 3 (ideas 4 and 12): measured and checked.
  - The fixed check „vage“ (vague, in dungeon_erzaehler.judge): the narration names fewer than two of the scene's points
    (people here, the targets of the ways, things, foes, props, the people it lets speak; as many as there are, when
    the scene has fewer) or ends with a hollow question of HOHL („Was tut ihr?“). Then one rewrite with the hint and
    up to three names to take up; the second try stays as it is (dungeon_erzaehler.repair).
  - A 👎 may carry the reason „Wusste nicht, was wir tun können“ (dungeon_erzaehlstand.GRUENDE "vage", shown only
    while this is on) and the bench has the scene „Sackgasse“ (a hall with a person, ways and a chest: the narration
    must name two of them and end with a concrete choice; the bench's round turns the check on with PRUEFSTAND).

Step 4 (ideas 6 and 11): the stall hint in three stages and a way out after a failed check.
  - Progress by fixed rules (progress): a new place, a thread opened or closed, a new thing, an act done, a fight
    begun or ended. Without it for WINK[stufe] told turns (Einsteiger 1, Normal 2, Erfahren never) the next narration
    gets stage 1 in the facts (wink 1: let something tangible appear clearly that leads on), one turn later stage 2 (an
    event of the rules' fixed table „stillstand“, at the children's table only mild ones, rolled by the panel), one
    more and the panel adds a line „Tipp: …“ from the scene's data (tip); then it starts again.
  - A failed check to find something out (dungeon_erzaehler._forscht) stays failed, but the seat's buttons of the next
    turn start with another way to the same goal: ask a person here, else another way of the map (ausweg).

Step 5 (idea 5, the three-clue rule): every act of a story may carry up to SPUREN_MAX clues (spuren) that lead to its
turning point: the 50 stories of dungeon_geschichten.json, the planner's draft, the adventure import and the form
(dungeon.check_plan). The panel keeps book of the clues shown (rd["spuren"] {akt, gezeigt}): the facts of the plan
name the next one (clue_facts: spur, at the stall hint's stage 1 deutlich), a narration that names enough of its words
counts it as shown (seen, and a clue shown is progress for the stall hint). A clue not yet shown is a secret for the
narrator's ways (check_ways). The host sees the clues with ✓ in „Nur für dich → Geschichte“.

Off by default: the admin's switch dungeonanleiten (features.py, chat.dungeon_anleiten) for the round's host; a guest at
the table gets it like everyone, it is part of the game and no tool. Step 4's progress counter with the stall hint and
step 5's clues are the core of the story (Review 27.10. E12, Dominik „ok“): their own switch dungeonfortschritt
(chat.dungeon_fortschritt) is on from the start (features.DEFAULT_ON, kern), at the level normal while this is off.
Journal: fixed words and numbers („dungeon: anleitung | …“), Live only counts.
"""
import random
import re

import features
from common import DayCounter

KEY = "dungeonanleiten"
KERN = "dungeonfortschritt"   # progress counter, stall hint and clues (steps 4 and 5), on from the start
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
WEGE = 3                   # ways of the map among the buttons (a crossing of three all, Dominik 2026-10-27 „Bibliothek fehlt“)
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
SPUREN_MAX = 3            # clues of an act at most
SPUR_LEN = 100             # characters of a clue
SPUR_TREFFER = 0.5         # part of a clue's words a narration names for the clue to count as shown
SPUREN_PLAN = ("zwei bis drei Spuren, die zum Wendepunkt führen (je ein greifbarer Hinweis wie Wachs am Turm oder ein "
               f"redseliger Lehrling, höchstens {SPUR_LEN} Zeichen), ",
               "two to three clues that lead to the turning point (each a tangible hint such as wax on the tower or a "
               f"talkative apprentice, at most {SPUR_LEN} characters), ")
WINK = {"einsteiger": 1, "normal": 2, "erfahren": 0}   # told turns without progress before the stall hint's stage 1
EREIGNIS_MAX = 160
TIPP = {"person": ("mit {x} sprechen", "talk to {x}"), "weg": ("{x} gehen", "go {x}"), "ding": ("{x} untersuchen", "examine {x}"),
        "angriff": ("{x} angreifen", "attack {x}"), "umsehen": ("euch hier genauer umsehen", "look around here more closely")}
AUSWEG = {"person": ("Ich frage {x} danach.", "I ask {x} about it."), "weg": ("Ich suche {x} weiter.", "I search on {x}.")}

KERN_ZAEHLER = ("wink1", "wink2", "wink3", "spur")   # the day's counts of kern (Live: Fortschritt der Geschichte)
_day = DayCounter(frage=0, frage_alt=0, zeile=0, genommen=0, weg=0, weg_verworfen=0, vage=0, wink1=0, wink2=0, wink3=0, ausweg=0,
                  spur=0)


PRUEFSTAND = "_anleiten"   # set only by the Erzähler-Prüfstand on its round in memory: the checks of this file count
# hollow questions at the end of a narration (the fixed check „vage“), lower case, without the question mark
HOHL = re.compile(r"(?i)(?:^|\W)(?:und |also |nun |so )?(?:was (?:tut|macht|tust|machst) (?:ihr|du)(?: nun| jetzt| als nächstes| als naechstes)?|"
                  r"was nun|was jetzt|wie geht es weiter|was wollt ihr tun|was willst du tun|"
                  r"what (?:do|will) you do(?: now| next)?|what now|what next|what is your next move|what's next)\W*$")


def on(rd):
    return bool(rd.get(PRUEFSTAND)) or bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def kern(rd):
    """Whether the story's progress counter, stall hint and clues count (steps 4 and 5, switch KERN)."""
    return bool(rd.get(PRUEFSTAND)) or bool(rd.get("owner")) and features.allowed(KERN, rd["owner"])


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


SPUR_TASK = {
    "de": (" Steht spur im Plan, lass diese Spur in dieser Erzählung in eigenen Worten sichtbar werden, bei deutlich "
           "unübersehbar; verrate nichts darüber hinaus."),
    "en": (" When the plan holds spur, let this clue become visible in this narration in your own words, with deutlich "
           "impossible to miss; reveal nothing beyond it."),
}


def task(rd, lang):
    """The narrator's form (step 1), the clues (step 5) and, unless the level is erfahren, the ways of the turn
    (step 2) and the stall hint (step 4); the clues and the stall hint follow kern, the rest on, "" while both are off."""
    k, o = kern(rd), on(rd)
    return ((TASK[lang] if o else "") + (SPUR_TASK[lang] if k and rd.get("plan") else "")
            + (WEGE_TASK[lang] if o and KNOEPFE[stufe(rd)] else "") + (WINK_TASK[lang] if k and WINK[stufe(rd)] else ""))


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
        gezeigt = shown(rd)
        for j, sp in enumerate(akte[i].get("spuren") or []):   # a clue not shown yet
            if j not in gezeigt:
                out |= _words(sp)
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
    a = rd.get("anleitausweg") or {}
    if a.get("zug") == rd.get("zug") and pid in (a.get("pids") or []):   # a failed check: another way to the same goal
        pts = _way_out(dm, r, rd, pid) + pts
    care = _care(dm, r, rd, h, li)
    scene = rf.points(dm, r, rd, pid, wege=WEGE)
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
        t = x["x"] if x["art"] in ("modell", "ausweg") else (MUSTER[x["art"]][li] if x["art"] in MUSTER else rf.MUSTER[x["art"]][li]).format(x=x["x"], z=x.get("z", ""))
        t = t[:WEG_MAX]
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append({"text": t, "wert": werte.get(_wurf(x["art"], t), "")})
    return out[:n]


def _way_out(dm, r, rd, pid):
    """After a failed check to find something out: ask a person here, else go on searching along another way."""
    import dungeon_karte
    li = _li(rd)
    le = dungeon_karte.leute(rd)["hier"][:1]
    if le:
        return [{"art": "ausweg", "x": AUSWEG["person"][li].format(x=le[0])}]
    w = [x for x in dungeon_karte.wege(rd, ("de", "en")[li]) if x["richtung"]][:1]
    if w:
        d = w[0]["richtung"]
        return [{"art": "ausweg", "x": AUSWEG["weg"][li].format(x=d if li or d in ("hinaus", "hinein") else "nach " + d)}]
    return []


def told(dm, r, rd):
    """After a narration (dungeon.apply, the next turn open): one line with the seats that get buttons."""
    if not on(rd) or not KNOEPFE[stufe(rd)]:
        return
    n = sum(1 for pid, _ in dm.seated(rd) if buttons(dm, r, rd, pid))
    if n:
        _day.bump("zeile")
        print(f"dungeon: anleitung | zeile | {n}", flush=True)
    a = rd.get("anleitausweg") or {}
    k = sum(1 for pid in a.get("pids") or [] if a.get("zug") == rd.get("zug") and _way_out(dm, r, rd, pid)) if WINK[stufe(rd)] else 0
    if k:
        _day.bump("ausweg", k)
        print(f"dungeon: anleitung | ausweg | {k}", flush=True)


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


def scene_names(dm, rd, story=None):
    """The names of the scene's points a narration may take up: people here, things near and of this narration, foes
    still up, props of the fight, the people the narration lets speak, the targets of the ways (in this order)."""
    import dungeon_erzaehler as erz
    import dungeon_karte
    import dungeon_kampf
    import dungeon_umgebung
    li = _li(rd)
    out = list(dungeon_karte.leute(rd)["hier"]) + [x["name"] for x in erz._near(rd)] + [x["name"] for x in (story or {}).get("dinge") or []]
    if rd.get("kampf"):
        out += [re.sub(r"\s+\d+$", "", str(g.get("name", ""))) for g in dungeon_kampf.up(rd)]
        out += [row["name"][li] for row in dungeon_umgebung.here(dm.rules(), rd)]
    out += [str(n.get("name", "")) for n in (story or {}).get("npc") or []] + [w["ziel"] for w in dungeon_karte.wege(rd, ("de", "en")[li])]
    heroes = {p["held"]["name"].lower() for _, p in dm.seated(rd)}
    return [n for n in dict.fromkeys(x.strip() for x in out) if len(n) >= 3 and n.lower() not in heroes]


def _named(n, low):
    w = n.lower()
    return bool(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low)) or (len(w) >= 5 and " " in w and w.split()[-1] in low.split())


def vague(dm, rd, story):
    """The fixed check „vage“ (dungeon_erzaehler.judge): [] when the narration names enough of the scene's points
    (two, or as many as the scene has), at least one of them from the panel's data (a person here, a thing near, a
    foe, a prop, a way by its target or direction; the narration's own things and speakers alone are no way on,
    Dominik 2026-10-27 „eine Präsenz“) and ends without a hollow question; else up to three names to take up (or
    ["…"] when the scene has none). Only while on."""
    if not on(rd):
        return []
    text = str(story.get("text") or "")
    low = text.lower()
    names = scene_names(dm, rd, story)
    found = [n for n in names if _named(n, low)]
    last = [x for x in re.split(r"(?<=[.!?…])\s+", text.strip()) if x][-1:] or [""]
    hohl = last[0].rstrip().endswith("?") and bool(HOHL.search(last[0].rstrip().rstrip("?!.… ")))
    panel = scene_names(dm, rd)                  # the panel's own points: the narration's own things alone are no way on
    eigen = not panel or any(_named(n, low) for n in panel) or any(_named(d, low) for d in _richtungen(rd))
    if len(found) >= min(2, len(names)) and not hohl and eigen:
        return []
    _day.bump("vage")
    print(f"dungeon: anleitung | vage | {'hohl' if hohl else 'zu wenig' if len(found) < min(2, len(names)) else 'kein ansatz'}", flush=True)
    return ([n for n in panel if n not in found] + [n for n in names if n not in found and n not in panel])[:3] or found[:3] or ["…"]


def _richtungen(rd):
    """The directions of the ways from here („nach Nordosten“ names that way too)."""
    import dungeon_karte
    return [w["richtung"] for w in dungeon_karte.wege(rd, ("de", "en")[_li(rd)]) if w.get("richtung") and w["richtung"] not in ("hinaus", "hinein", "outside", "inside")]


def check_rules(r, need):
    """The fixed table of stall events (rules „stillstand“): ids once, a pair [German, English] of 20 to EREIGNIS_MAX
    characters, mild a bool, at least three mild ones for the children's table."""
    t = r.get("stillstand")
    need(isinstance(t, list) and t, "stillstand: eine Liste fester Ereignisse")
    ids = [x.get("id") for x in t or [] if isinstance(x, dict)]
    need(len(ids) == len(t or []) and len(set(ids)) == len(ids) and all(isinstance(i, str) and i for i in ids), "stillstand: jede id einmal")
    for x in t or []:
        p = x.get("text") if isinstance(x, dict) else None
        need(isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) and 20 <= len(s) <= EREIGNIS_MAX for s in p),
             f"stillstand[{x.get('id') if isinstance(x, dict) else ''}].text: ein Paar [Deutsch, Englisch] mit 20 bis {EREIGNIS_MAX} Zeichen")
        need(isinstance(x, dict) and isinstance(x.get("mild"), bool), "stillstand: mild ist true oder false")
    need(sum(1 for x in t or [] if isinstance(x, dict) and x.get("mild") is True) >= 3, "stillstand: mindestens drei milde Ereignisse")


def _clues(rd):
    """The current act's clues and the indices shown of it (a new act starts with none shown)."""
    p = rd.get("plan") or {}
    i = rd.get("akt", 0)
    akte = p.get("akte") or []
    sp = list(akte[i].get("spuren") or []) if i < len(akte) else []
    b = rd.get("spuren") if isinstance(rd.get("spuren"), dict) else {}
    return sp, (b.get("gezeigt") or []) if b.get("akt") == i else []


def shown(rd):
    """The indices of the current act's clues shown so far."""
    return list(_clues(rd)[1])


def clue_facts(rd):
    """For the plan's facts: the next clue to show, „deutlich“ at the stall hint's stage 1; {} while off or none left."""
    if not kern(rd):
        return {}
    sp, seen = _clues(rd)
    nxt = next((t for j, t in enumerate(sp) if j not in seen), None)
    if not nxt:
        return {}
    w = rd.get("anleitwink") or {}
    return {"spur": nxt, **({"deutlich": True} if w.get("zug") == rd.get("zug") and w.get("stufe") == 1 else {})}


def _stem(w):
    return w[:max(5, len(w) - 2)]


def named(text, of, need):
    """Whether text names need stems of the content words of of (all of them when it has fewer); False when of has
    none (dungeon.step_act: the turning point, dungeon.goal_told: the goal)."""
    stems = {_stem(w) for w in _words(text)}
    ws = {_stem(w) for w in _words(of)}
    return bool(ws) and sum(1 for w in ws if w in stems) >= min(need, len(ws))


def seen(rd, text):
    """After a narration: the clues it names (SPUR_TREFFER of their words, by stem) count as shown; returns how many
    are new."""
    if not kern(rd):
        return 0
    sp, old = _clues(rd)
    low = str(text or "").lower()
    stems = {_stem(w) for w in _words(low)}
    new = []
    for j, t in enumerate(sp):
        ws = {_stem(w) for w in _words(t)}
        if j not in old and ws and sum(1 for w in ws if w in stems) >= max(1, round(len(ws) * SPUR_TREFFER)):
            new.append(j)
    if new:
        rd["spuren"] = {"akt": rd.get("akt", 0), "gezeigt": sorted(set(old) | set(new))}
        _day.bump("spur", len(new))
        print(f"dungeon: anleitung | spur | {len(rd['spuren']['gezeigt'])}/{len(sp)}", flush=True)
    return len(new)


def _stand(rd):
    """What counts as progress, as one comparable value: the place, the threads, the things, the act, a fight."""
    k = rd.get("karte") or {}
    return [k.get("hier"), k.get("drin"), (rd.get("szene") or {}).get("ort", ""), list(rd.get("faeden") or []),
            len(rd.get("dinge") or []), rd.get("akt", 0), bool(rd.get("kampf"))]


def _tip(dm, r, rd):
    """The panel's line „Tipp: …“ from the scene's data (the first seat's points), "" with fewer than one."""
    import dungeon_erzaehler as erz
    import dungeon_rueckfrage as rf
    li = _li(rd)
    seats = [pid for pid, _ in dm.seated(rd)]
    pts = [p for p in (rf.points(dm, r, rd, seats[0], wege=1) if seats else []) if p["art"] in TIPP and p["art"] != "umsehen"]
    dinge = [{"art": "ding", "x": x["name"]} for x in erz._near(rd)][-1:]
    pts = (pts[:1] + dinge + pts[1:])[:2] or [{"art": "umsehen", "x": ""}]
    t = (" oder ", " or ")[li].join(TIPP[p["art"]][li].format(x=p["x"]) for p in pts)
    return (" Tipp: Ihr könnt {t}.", " Tip: You can {t}.")[li].format(t=t)


def progress(dm, r, rd, story, wuerfe, rng):
    """After a told turn (dungeon.apply, before the turn is counted on): the stall counter by fixed rules, the stage
    for the next narration (rd["anleitwink"]), the way out after a failed check (rd["anleitausweg"]); returns the
    panel's tip line of stage 3, else "". Nothing while kern is off or at the level erfahren."""
    neu = seen(rd, story.get("text"))              # a clue shown: progress
    if not kern(rd) or not WINK[stufe(rd)]:
        rd.pop("anleitwink", None)
        return ""
    import dungeon_erzaehler as erz
    nxt = rd.get("zug", 0) + 1
    out = [x["pid"] for x in wuerfe or () if erz._forscht(x) and x.get("pid")]
    rd["anleitausweg"] = {"zug": nxt, "pids": out}
    s = rd.setdefault("stillstand", {"zuege": 0})
    now = _stand(rd)
    moved = s.get("stand") is None or s.get("stand") != now or neu > 0 \
        or bool(story.get("akt_fertig") or story.get("begegnung") or story.get("kampf_ende"))
    s.update(stand=now, zuege=0 if moved else s.get("zuege", 0) + 1)
    n = s["zuege"] - WINK[stufe(rd)] + 1           # the stage of the stall hint, 1 to 3
    rd.pop("anleitwink", None)
    if n < 1:
        return ""
    st = min(n, 3)
    _day.bump(f"wink{st}")
    print(f"dungeon: anleitung | wink | {st}", flush=True)
    if st == 3:
        s["zuege"] = 0                           # the tip is said: the stages start again
        return _tip(dm, r, rd)
    w = {"zug": nxt, "stufe": st}
    if st == 2:
        pool = [x for x in r.get("stillstand") or [] if x.get("mild") or not dm.kids(r, rd)]
        if pool:
            w["ereignis"] = (rng or random).choice(pool)["text"][_li(rd)]
    rd["anleitwink"] = w
    return ""


WINK_TASK = {
    "de": (" Steht wink in den Fakten, kommt die Geschichte nicht voran: bei stufe 1 lass in dieser Erzählung etwas "
           "Greifbares deutlich auftauchen, das weiterführt (eine Spur, eine Person, ein Ausgang), ohne spätere Akte zu "
           "verraten; steht ereignis darin, erzähle genau dieses Ereignis als Teil der Szene."),
    "en": (" When the facts hold wink, the story does not move on: at stufe 1 let something tangible appear clearly in "
           "this narration that leads on (a trace, a person, an exit), without revealing later acts; when it holds "
           "ereignis, tell exactly this event as part of the scene."),
}


def facts(rd):
    """The stall hint of this turn as data: {"wink": {stufe, ereignis?}}, {} without one."""
    w = rd.get("anleitwink") or {}
    if not kern(rd) or w.get("zug") != rd.get("zug"):
        return {}
    return {"wink": {k: w[k] for k in ("stufe", "ereignis") if k in w}}


def for_live():
    """Numbers only: questions to quiet seats built from the scene and those that kept the old line, lines of buttons
    shown, buttons taken, the narrator's ways taken and refused, narrations sent back as vague."""
    return _day.counts()
