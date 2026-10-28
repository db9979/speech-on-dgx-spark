"""KI-Dungeon-Master: the narrator bench „Erzähler-Prüfstand“ (Tabletop-Punkt 4 of 2026-10-25, Dominik „ich hätte gerne
alle punkte umgesetzt“; agreed with the thread „Eigene Modell-Installation statt qwen38“ the same day: against the
running model in the panel, not in „modelle messen“; the fixed rules decide, the model's own Einordnung is only shown).

On the admin's button the panel plays SZENEN, fixed test scenes, through the real steps of a turn (dungeon.ask_checks
and dungeon.tell: the same system text, facts, schema, checks and rewrites as at the table) on a round that lives only
in memory: nothing is saved, no seat, no profile, no day counter of the table. Each scene has its fixed rule:

    tuer      a failed check (the panel's fixed die) must not be told as done (erz.judge)
    zwei      two heroes acted: both are in the narration (erz.judge)
    kampf     a fight with the panel's attacks and the foes' turn: foes by their bestiary name, no number without
              its receipt (erz.judge)
    kinder    the children's tone: no word of its list (dungeon.check_story)
    nsc       a person of the truth asked by name answers by name
    englisch  an English round is told in English (few German words, ENGLISCH_MAX)
    probe     a risky action: the model asks for a check (dungeon.ask_checks)
    ruhe      a harmless action: no check
    sackgasse a hall with a person, ways of the map and a chest: the narration names two of them and ends with a
              concrete choice (dungeon_anleiten.vague, the check of „Spieler anleiten“ on for the bench's round)

Points per scene: 2 when the first try passes, 1 after a rewrite, 0 when refused or only the panel's repair is left;
the checks scenes 2 or 0. The model's own Einordnung (systemone use "erzaehler", Einordnung mit Wahrscheinlichkeit:
how vivid, how well it follows the actions and dice) stands beside it as the model's own view, never as points. The
result per model name (llm.known_model) into STATE/dungeon-erzaehlstand.json (dateien.py), the last MODELLE_MAX models
side by side. Only while „Erzähler-Prüfstand“ is on (features.py, below the Dungeon-Master).

    GET  /api/admin/dungeon/erzaehlstand     the models measured, the scenes, whether it is on and running
    POST /api/admin/dungeon/erzaehlstand     „Jetzt prüfen“ (rate-limited, one run at a time)

The cases „Erzähler-Fehler“ (Dominik 2026-10-25 „1-3 und 1-7 umsetzten“, Punkte 2 und 3): while the bench is on, a
seat's 👎 may carry one reason of GRUENDE (a fixed list, never a text); the panel then keeps that turn as a case
(case(): the actions, the panel's dice and the narration of that turn, every hero's name swapped for a bench name of
NAMEN, no profile, no seat, no round id, only a hash of it so a second 👎 of the same turn replaces the case), the
newest FAELLE_MAX in STATE/dungeon-erzaehlfehler.json (dateien.py). The admin sees them on the page „Erzähler-Fehler“
and takes one over „Als Prüfstand-Szene übernehmen“: the scene replays the actions with the same outcome of every
check (passed or failed) on a fresh round of the same world, tone and language (the round's map, fight and people are
not carried), at most EIGENE_MAX, scored like the fixed scenes.

    GET  /api/admin/dungeon/erzaehlfehler    the cases, the scenes taken over, the reasons
    POST /api/admin/dungeon/erzaehlfehler    {fall, aktion: szene|loeschen} or {szene, aktion: loeschen}

Journal lines „dungeon: erzaehlstand | …“ with fixed words and numbers only.
"""
import asyncio
import datetime
import hashlib
import os
import random
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_erzaehler as erz
import dungeon_kampf as kampf
import features
import guard
from common import STATE, load_config, read_json, write_json
from core import auth, json_body

router = APIRouter()
FILE = os.path.join(STATE, "dungeon-erzaehlstand.json")
MODELLE_MAX = 8
KNOPF_S = 120              # „Jetzt prüfen“ at most once in two minutes
ENGLISCH_MAX = 2           # German words („und“, „der“, „die“ …) an English narration may have
DEUTSCH = re.compile(r"\b(und|der|die|das|nicht|ist|mit|ein|eine|euch|ihr)\b", re.I)
WURF = 3                   # the panel's die of the failed check (scene „tuer“)
SZENEN = {
    "tuer": ("Gescheiterte Probe bleibt gescheitert", "A failed check stays failed"),
    "zwei": ("Beide Helden kommen vor", "Both heroes appear"),
    "kampf": ("Kampf mit Belegen und Gegnernamen", "Fight with receipts and foe names"),
    "kinder": ("Kinderton ohne verbotene Wörter", "Children's tone without refused words"),
    "nsc": ("Eine Figur antwortet beim Namen", "A person answers by name"),
    "englisch": ("Englische Runde auf Englisch", "English round in English"),
    "probe": ("Riskante Aktion verlangt eine Probe", "A risky action asks for a check"),
    "ruhe": ("Harmlose Aktion ohne Probe", "A harmless action without a check"),
    "kampfzug": ("Kämpfen wird ein Angriff gegen die Rüstung", "Fighting becomes an attack against the armour"),   # Kampfzug-Prüfung 5
    "sackgasse": ("Erzählung nennt, was man tun kann", "The narration names what one can do"),   # Spieler anleiten, step 3
}
LEVELS = ["gar nicht", "teilweise", "ganz"]
_run = {"laeuft": False, "seit": 0.0, "task": None}
FALL_FILE = os.path.join(STATE, "dungeon-erzaehlfehler.json")
FAELLE_MAX = 40            # cases kept, the newest first
EIGENE_MAX = 12            # scenes taken over from cases
TEXT_MAX = 1500            # a case's narration, per character
TAT_MAX = 300              # an action and a check's wofuer of a case
NAMEN = ("Arvid", "Bela", "Cora", "Dario", "Ella")   # the bench's heroes; a case keeps no player's hero name
# a 👎's fixed reasons: (German, English, the fixed rule of erz.judge it belongs to or "", the fixed hint a new telling
# and a world's narrator get, German and English; Dominik 2026-10-25 „empfehlung“ für 1 bis 5)
GRUENDE = {
    "probe": ("Misslungene Probe trotzdem geschafft oder etwas verraten", "A failed check done anyway or something revealed", "probe",
              "Eine misslungene Probe bleibt misslungen: es gelingt nicht, und wer etwas untersucht, erfährt nichts Neues.",
              "A failed check stays failed: it does not happen, and whoever examines something learns nothing new."),
    "frage": ("Aktion falsch verstanden (Frage, Richtung)", "Action misunderstood (question, direction)", "frage",
              "Erzähle genau die Aktion: wer fragt, fragt und bekommt eine Antwort; ein Weg nach unten bleibt nach unten.",
              "Tell exactly the action: whoever asks asks and gets an answer; a way down stays down."),
    "fremd": ("Hat für eine andere Figur entschieden", "Decided for another character", "fremd",
              "Jede Figur tut nur, was ihr Spieler geschrieben hat; entscheide für niemanden sonst.",
              "Every character does only what its player wrote; decide for nobody else."),
    "ding": ("Ding oder Zauber, den die Figur nicht hat", "An item or spell the character does not have", "fehlt",
             "Eine Figur benutzt nur Dinge und Zauber, die sie hat.", "A character uses only things and spells it has."),
    "kampf": ("Kampf stimmt nicht (Gegner, Treffer, Gefallene)", "The fight does not match (foes, hits, the fallen)", "gefallen",
              "Halte dich im Kampf genau an die Gegner und Treffer der Würfel-Belege; Gefallene handeln nicht mehr.",
              "In a fight keep exactly to the foes and hits of the dice receipts; the fallen act no more."),
    "gold": ("Gold oder Beute nur erzählt", "Gold or loot only told", "gold",
             "Nenne keine Menge Gold oder Beute; das legt das Panel fest.", "Name no amount of gold or loot; the panel sets it."),
    "ort": ("Falscher Ort", "Wrong place", "karte",
            "Die Gruppe bleibt an ihrem Ort und geht nur dorthin, wohin eine Aktion sie schickt.",
            "The group stays at its place and goes only where an action sends it."),
    "person": ("Person sieht anders aus oder ist woanders", "A person looks different or is elsewhere", "aussehen",
               "Personen sehen so aus und sind dort, wie die Fakten sagen.", "People look and are where the facts say."),
    "wiederholung": ("Wiederholt sich", "Repeats itself", "wiederholung",
                     "Erzähle Neues und wiederhole nichts aus den letzten Zügen.", "Tell something new and repeat nothing of the last turns."),
    "vage": ("Wusste nicht, was wir tun können", "Did not know what we could do", "vage",   # Spieler anleiten, step 3
             "Nenne in jeder Erzählung mindestens zwei greifbare Ansatzpunkte mit Namen und ende mit einer konkreten Wahl an eine Figur.",
             "Name at least two things to take up with names in every narration and end with a concrete choice for one figure."),
    "sonst": ("Etwas anderes", "Something else", "",
              "Folge genau den Aktionen der Spieler und den Würfen.", "Follow the players' actions and the dice exactly."),
}
MELDUNGEN_MAX = 600        # reports kept (time, world, reason; numbers only) for the world's hints and the weeks
WELT_SCHWELLE = 3          # reports of one reason in a world within WELT_TAGE make its hint a standing one there
WELT_TAGE = 30
WOCHEN = 6                 # weeks the overview shows
_flock = threading.Lock()


def on():
    return features.admin_on("dungeonerzaehlstand")


def cases_on(owner):
    """A 👎 may carry a reason and becomes a case while the bench or „Erzähler-Fehler beheben“ (FIX, for the round's
    host: a new telling, the world's hints) is on."""
    return on() or features.allowed(FIX, owner)


def clock():
    return time.time()


class _Fest:
    """The panel's fixed dice of a scene: randint gives WURF for a check (d20), else the middle; randrange the first."""

    def randint(self, a, b):
        return WURF if b == 20 else (a + b) // 2

    def randrange(self, n):
        return 0


def _round(r, lang="de", ton=None, taten=(("Arvid", ""),), welt=None):
    """A round only in memory: the world (else the first), the tone (else the first one above the children's), a seat
    per hero (name, action this turn, class else the classes in turn)."""
    toene = [t["id"] for t in r["toene"]]
    ton = ton if ton in toene else next((t for t in toene if t != min(toene)), toene[0])
    welten = [w["id"] for w in r["welten"]]
    ks, volk = [k["id"] for k in r["klassen"]], r["voelker"][0]["id"]
    rd = {"owner": "", "titel": "Prüfstand", "welt": welt if welt in welten else welten[0], "ton": ton, "zug_s": 0, "lang": lang, "einstieg": "",
          "prompt": "", "made": 0, "until": 0, "status": "laeuft", "zug": 2, "zug_t": 0, "pause": False, "offen": {}, "still": {},
          "szene": {"ort": "", "stimmung": ""}, "log": [], "dm": "", "stunden": 1, "vorlesen": False, "erzaehlweise": "normal",
          "plaetze": {}}
    for i, (name, tat, *kl) in enumerate(taten):
        h = dungeon.new_hero(r, {"name": name, "volk": volk, "klasse": kl[0] if kl and kl[0] in ks else ks[i % len(ks)]}, random.Random(i))
        h["leben"] = h["leben_max"] = dungeon.life(r, h)
        pid = f"p{i}"
        rd["plaetze"][pid] = {"h": "", "uid": "", "held": h, "made": 0, "gast": i > 0}
        if tat:
            rd["offen"][pid] = {"text": tat, "t": 0}
    return rd


def scene(r, sid):
    """(the round, what the panel rolls: checks [{pid, wert, schwer, wofuer, ziel?}] or None for the model's checks)."""
    if sid == "tuer":
        rd = _round(r, taten=(("Arvid", "Ich werfe mich mit der Schulter gegen die alte Holztür."),))
        return rd, [{"pid": "p0", "wert": "staerke", "schwer": 15, "vt": "", "wofuer": "die Holztür aufbrechen"}]
    if sid == "zwei":
        return _round(r, taten=(("Arvid", "Ich suche am Boden nach frischen Spuren."), ("Bela", "Ich frage den Wirt, wer zuletzt hier war."))), []
    if sid in ("kampf", "kampfzug"):
        rd = _round(r, taten=(("Arvid", "Ich greife den vordersten Gegner mit meiner Waffe an."),))
        held = [p["held"] for p in rd["plaetze"].values()]
        foe = min(r["gegner"], key=lambda g: (abs(g.get("stufe", 0) - 0.25), g["id"]))
        rd["kampf"] = {"gegner": kampf.lineup([(foe, 2)], 0, len(held)), "seit": 1, "budget": 100, "gefahr": "mittel",
                       "leben0": sum(h["leben"] for h in held), "helden": ["p0"]}
        if sid == "kampfzug":                # „kämpfe gegen …“ (Dominik 2026-10-26): the model's checks, the panel's attack
            rd["offen"]["p0"]["text"] = f"Ich kämpfe gegen {rd['kampf']['gegner'][0]['name']}."
            return rd, None
        return rd, [{"pid": "p0", "wert": "staerke", "schwer": 10, "vt": "", "wofuer": "Angriff", "ziel": rd["kampf"]["gegner"][0]["name"]}]
    if sid == "kinder":
        return _round(r, ton=min(t["id"] for t in r["toene"]), taten=(("Arvid", "Ich ziehe mein Schwert und stürze mich auf den Wolf."),)), []
    if sid == "nsc":
        rd = _round(r, taten=(("Arvid", "Ich frage Oskar, wo der alte Turm liegt."),))
        rd["wahrheit"] = {"personen": [{"name": "Oskar", "rolle": "Wirt der Schenke", "ziel": "", "sprache": "brummig"}], "gruppen": [], "geheimnisse": []}
        return rd, []
    if sid == "englisch":
        return _round(r, lang="en", taten=(("Arvid", "I light a torch and look around the cellar."),)), []
    if sid == "probe":
        return _round(r, taten=(("Arvid", "Ich klettere die glatte, nasse Felswand hinauf."),)), None
    if sid == "sackgasse":                   # a hall with a person, ways and a chest: two named, a concrete choice (vague)
        import dungeon_anleiten
        import dungeon_karte
        rd = _round(r, taten=(("Arvid", "Ich bleibe in der Halle stehen und überlege, was wir tun können."),))
        rd[dungeon_anleiten.PRUEFSTAND] = True
        dungeon_karte.ensure(r, rd, random.Random(1))
        k = rd["karte"]
        k.setdefault("leute", {})["Grimma"] = {"ort": k["hier"], "mit": False}
        rd["szene"]["ort"] = k["orte"][k["hier"]]["name"]
        rd["dinge"] = [{"name": "Truhe", "merkmale": "eisenbeschlagen, verschlossen", "ort": rd["szene"]["ort"], "zug": 1}]
        return rd, []
    return _round(r, taten=(("Arvid", "Ich wünsche den anderen einen guten Morgen und packe mein Brot aus."),)), None


class _Wurf:
    """A die that always shows n on a d20 (a scene taken over from a case: 20 for a passed check, 2 for a failed one)."""

    def __init__(self, n):
        self.n = n

    def randint(self, a, b):
        return self.n if b == 20 else (a + b) // 2

    def randrange(self, n):
        return 0


def own_scene(r, s):
    """(the round, the checks, their outcomes) of a scene taken over from a case."""
    tat = {x["held"]: x["text"] for x in s["taten"]}
    helden = s.get("helden") or [{"held": x["held"], "klasse": x.get("klasse")} for x in s["taten"]]
    rd = _round(r, lang=s.get("lang", "de"), ton=s.get("ton"), welt=s.get("welt"),
                taten=[(NAMEN[x["held"]], tat.get(x["held"], ""), x.get("klasse")) for x in sorted(helden, key=lambda x: x["held"])] or (("Arvid", ""),))
    proben = [{"pid": f"p{x['held']}", "wert": x["wert"], "schwer": x["schwer"], "vt": "", "wofuer": x["wofuer"]}
              for x in s["wuerfe"] if f"p{x['held']}" in rd["plaetze"]]
    return rd, proben, [bool(x["ok"]) for x in s["wuerfe"] if f"p{x['held']}" in rd["plaetze"]]


def same_dice(r, rd, proben, oks):
    """The panel's dice with the case's outcome of every check: 20 for a passed one; 2 for a failed one, and when the
    bench hero's bonus would still pass it, the difficulty one above the total."""
    out = []
    for p, ok in zip(proben, oks):
        x = dungeon.roll(r, rd, [p], _Wurf(20 if ok else 2))[0]
        if x["ok"] != ok:
            x = dungeon.roll(r, rd, [dict(p, schwer=x["gesamt"] + 1)], _Wurf(2))[0]
        out.append(x)
    return out


def _aktionen(r, rd):
    """The table's checks of every typed action (dungeon._act: powers and things not carried) before the turn runs,
    so a scene meets the same rules as at the table (Prüfstand 28.10.: „I light a torch“ without one)."""
    for pid in list(rd["offen"]):
        dungeon.check_powers(r, rd, pid, count=False)
        dungeon.check_items(r, rd, pid, count=False)
    return rd


async def play(r, sid, own=None):
    """One scene through the real steps of a turn (own: a scene taken over from a case); returns its result."""
    t0 = time.monotonic()
    if own:
        rd, proben, oks = own_scene(r, own)
        _aktionen(r, rd)
        wuerfe = same_dice(r, rd, proben, oks)
        erz.receipts(rd, wuerfe, [], [])
        story, _, tries = await dungeon.tell(r, rd, wuerfe, [], [], count=False)
        punkte = 2 if tries[:1] == [""] else 1 if "" in tries else 0
        return {"punkte": punkte, "grund": "ok" if punkte else next((f for f in reversed(tries) if f), "abgelehnt"),
                "versuche": len(tries), "laenge": len((story or {}).get("text") or ""), "sekunden": round(time.monotonic() - t0, 1),
                **({"erst": tries[0] or "abgelehnt"} if punkte == 1 else {})}
    rd, proben = scene(r, sid)
    _aktionen(r, rd)
    if proben is None and sid == "kampfzug":              # whatever the model asks: fighting a foe is an attack
        got, _ = await dungeon.ask_checks(r, rd)
        rest, hits = kampf.attacks(dungeon, r, rd, got, _Fest())
        ok = any(x["pid"] == "p0" and not x.get("kann_nicht") for x in hits) and not any(x["pid"] == "p0" for x in rest)
        return {"punkte": 2 if ok else 0, "grund": "ok" if ok else "kein angriff", "proben": len(got), "sekunden": round(time.monotonic() - t0, 1)}
    if proben is None:                                    # the checks scenes: does the model ask for one
        got, _ = await dungeon.ask_checks(r, rd)
        ok = bool(got) if sid == "probe" else not got
        return {"punkte": 2 if ok else 0, "grund": "ok" if ok else ("keine probe" if sid == "probe" else "probe"),
                "proben": len(got), "sekunden": round(time.monotonic() - t0, 1)}
    proben, hits = kampf.attacks(dungeon, r, rd, proben, _Fest())
    wuerfe = dungeon.roll(r, rd, proben, _Fest())
    zuege = kampf.foes_turn(dungeon, r, rd, hits, _Fest()) if hits else []
    erz.receipts(rd, wuerfe, hits, zuege)
    story, _, tries = await dungeon.tell(r, rd, wuerfe, hits, zuege, count=False)
    text = (story or {}).get("text") or ""
    punkte = 2 if tries[:1] == [""] else 1 if "" in tries else 0
    grund = "ok" if punkte else next((f for f in reversed(tries) if f), "abgelehnt")
    if punkte and sid == "nsc" and "oskar" not in text.lower():
        punkte, grund = 0, "name fehlt"
    if punkte and sid == "englisch" and len(DEUTSCH.findall(text)) > ENGLISCH_MAX:
        punkte, grund = 0, "deutsch"
    out = {"punkte": punkte, "grund": grund, "versuche": len(tries), "laenge": len(text), "sekunden": round(time.monotonic() - t0, 1),
           **({"erst": tries[0] or "abgelehnt"} if punkte == 1 else {})}   # a rewrite's first fault (a fixed word)
    e = await _einordnung(rd, text) if text else None
    if e:
        out["einordnung"] = e
    return out


def questions():
    import systemone
    return {"lebendig": systemone.score("Wie lebendig und bildhaft erzählt die Erzählung die Szene?", LEVELS),
            "folgt": systemone.score("Wie genau folgt die Erzählung den Aktionen der Spieler und den Würfen?", LEVELS)}


async def _einordnung(rd, text):
    """The model's own view (systemone use "erzaehler"), the scene as data, each 0 to 1 (systemone's score runs over
    the LEVELS, 0 to 2; Prüfstand 28.10.: shown as 185 per cent before); None when Einordnung is off or unsure."""
    import systemone
    if not features.admin_on("einordnung"):
        return None
    taten = "\n".join(f"{rd['plaetze'][pid]['held']['name']}: {a['text']}" for pid, a in rd["offen"].items())
    try:
        ans = await systemone.ask(load_config().get("chat", {}), "erzaehler", f"Aktionen:\n{taten}\nErzählung: {text}", questions(), timeout=30)
    except systemone.Unavailable:
        return None
    return {k: round(ans[k]["score"] / (len(LEVELS) - 1), 2) for k in ("lebendig", "folgt")}   # 0..1 (the score is 0..2)


def last():
    return read_json(FILE, {}) or {}


async def _go(nacht=False):
    """One run: every scene, then the model's line in the file; one at a time (nacht: the night's run, its date kept)."""
    import llm
    t0 = time.monotonic()
    print("dungeon: erzaehlstand | start", flush=True)
    try:
        r = dungeon.rules()
        szenen = {}
        for sid in SZENEN:
            szenen[sid] = await play(r, sid)
            print(f"dungeon: erzaehlstand | szene | {sid} | {szenen[sid]['punkte']} punkte", flush=True)
        for s in own_scenes():
            szenen[s["id"]] = await play(r, s["id"], s)
            print(f"dungeon: erzaehlstand | szene | eigene | {szenen[s['id']]['punkte']} punkte", flush=True)
        name = (llm.known_model() or "unbekannt")[:80]
        d = last()
        ms = dict(d.get("modelle") or {})
        ms[name] = {"zeit": int(clock()), "punkte": sum(x["punkte"] for x in szenen.values()), "max": 2 * len(szenen),
                    "sekunden": round(time.monotonic() - t0, 1), "szenen": szenen}
        ms = dict(sorted(ms.items(), key=lambda kv: -kv[1]["zeit"])[:MODELLE_MAX])
        await asyncio.to_thread(write_json, FILE, {"modelle": ms, "nacht": _date() if nacht else d.get("nacht", "")})
        print(f"dungeon: erzaehlstand | fertig | {ms[name]['punkte']} von {ms[name]['max']} | {int(time.monotonic() - t0)} s", flush=True)
    except Exception as e:
        print(f"dungeon: erzaehlstand | fehler | {type(e).__name__}", flush=True)
    finally:
        _run["laeuft"] = False


FIX = "dungeonerzfehler"    # the switch „Erzähler-Fehler beheben“ (features.py)
NACHT = (2, 5)             # the night window, local hours [from, to), for the scenes taken over from cases (Vorschlag 3)


def _date():
    return time.strftime("%Y-%m-%d", time.localtime(clock()))


async def due():
    """Each minute from the panel's loop: once a night, while the bench is on and has scenes taken over from cases, a
    run of all scenes, so every new model and version meets the reported errors."""
    if not on() or _run["laeuft"] or not NACHT[0] <= time.localtime(clock()).tm_hour < NACHT[1]:
        return
    if await asyncio.to_thread(lambda: last().get("nacht") == _date() or not own_scenes()):
        return
    _run.update(laeuft=True, seit=clock())
    print("dungeon: erzaehlstand | nacht | start", flush=True)
    _run["task"] = asyncio.create_task(_go(nacht=True))   # kept, so the run is not collected; the loop goes on


def _spawn():
    _run["task"] = asyncio.create_task(_go())             # kept, so the run is not collected


def view():
    d = last()
    return {"an": on(), "laeuft": _run["laeuft"],
            "szenen": [[k, list(v)] for k, v in SZENEN.items()] + [[s["id"], s["name"]] for s in own_scenes()],
            "modelle": d.get("modelle") or {}, "einordnung": features.admin_on("einordnung")}


@router.get("/api/admin/dungeon/erzaehlstand", dependencies=[Depends(auth)])
async def show(request: Request):
    guard.limit(request, "dungeonpruef", admin=True)
    return await asyncio.to_thread(view)


@router.post("/api/admin/dungeon/erzaehlstand", dependencies=[Depends(auth)])
async def now(request: Request):
    guard.limit(request, "dungeonpruef", admin=True)
    await json_body(request, 200)
    if not on():
        print("dungeon: erzaehlstand | knopf | aus", flush=True)
        raise HTTPException(409, "aus")
    if _run["laeuft"]:
        print("dungeon: erzaehlstand | knopf | laeuft", flush=True)
        return view()
    if clock() - _run["seit"] < KNOPF_S:
        print("dungeon: erzaehlstand | knopf | zu oft", flush=True)
        raise HTTPException(429, "zu oft")
    _run.update(laeuft=True, seit=clock())
    _spawn()
    print("dungeon: erzaehlstand | knopf | ok", flush=True)
    return dict(view(), laeuft=True)


def counts():
    """For the live overview: the models measured, the best points (of the best model's own most), whether a run is
    on, the cases and the scenes taken over from them."""
    ms = last().get("modelle") or {}
    best = max(ms.values(), key=lambda m: m["punkte"], default=None)
    f = cases()
    return {"modelle": len(ms), "beste": best["punkte"] if best else 0, "max": best.get("max", 2 * len(SZENEN)) if best else 2 * len(SZENEN),
            "laeuft": _run["laeuft"], "faelle": len(f.get("faelle") or []), "eigene": len(f.get("szenen") or [])}


# ---------------------------------------------------------------- the cases „Erzähler-Fehler“
def reasons_ids(rd):
    """The reasons a seat of this round may give: „vage“ only while „Spieler anleiten“ is on (dungeon_anleiten)."""
    import dungeon_anleiten
    return [k for k in GRUENDE if k != "vage" or dungeon_anleiten.on(rd)]


def reasons(rd):
    """The 👎's fixed reasons for a seat of the round: [[id, label]]."""
    return [[k, GRUENDE[k][1 if rd.get("lang") == "en" else 0]] for k in reasons_ids(rd)]


def cases():
    return read_json(FALL_FILE, {}) or {}


def own_scenes():
    return [s for s in cases().get("szenen") or [] if isinstance(s, dict) and s.get("id")]


def _swap(names):
    """A function that puts the bench's names for the heroes' names (the longest first, whole words with a genitive s,
    any case)."""
    if not names:
        return lambda t: str(t or "")
    rx = re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?=(?:s|'s|’s)?(?!\w))", re.I)
    low = {k.lower(): v for k, v in names.items()}
    return lambda t: rx.sub(lambda m: low[m.group(1).lower()], str(t or ""))


def case(rid, rd, zug, grund):
    """The case of a 👎 with a reason: the turn's actions, the panel's dice and the narration, the heroes as NAMEN (those
    who acted first, then the other seats), no profile, no seat, no round id. None when the turn has no narration."""
    log = [e for e in rd.get("log") or [] if e.get("n") == zug]
    erz_text = next((e["text"] for e in reversed(log) if e.get("art") == "dm" and isinstance(e.get("text"), str)), "")
    if not erz_text:
        return None
    pids = list(dict.fromkeys([e["pid"] for e in log if e.get("art") in ("aktion", "wurf") and e.get("pid") in rd["plaetze"]]
                              + [pid for pid, p in rd["plaetze"].items() if p.get("held")]))[:len(NAMEN)]
    idx = {pid: i for i, pid in enumerate(pids)}
    names = {}
    for pid in pids:
        n = ((rd["plaetze"][pid].get("held") or {}).get("name") or "").strip()
        if len(n) >= 2:
            names[n] = NAMEN[idx[pid]]
    swap = _swap(names)

    def held(pid):
        return rd["plaetze"][pid].get("held") or {}
    return {"id": secrets.token_hex(4), "quelle": hashlib.sha256(f"{rid}|{zug}".encode()).hexdigest()[:16], "zeit": int(clock()),
            "grund": grund, "welt": rd.get("welt", ""), "ton": rd.get("ton"), "lang": "en" if rd.get("lang") == "en" else "de",
            "helden": [{"held": idx[pid], "klasse": held(pid).get("klasse", "")} for pid in pids],
            "taten": [{"held": idx[e["pid"]], "klasse": held(e["pid"]).get("klasse", ""), "text": swap(e.get("text"))[:TAT_MAX]}
                      for e in log if e.get("art") == "aktion" and e.get("pid") in idx],
            "wuerfe": [{"held": idx[e["pid"]], "wert": e.get("wert", ""), "schwer": e.get("schwer", 10), "w": e.get("w", 0),
                        "ok": bool(e.get("ok")), "wofuer": swap(e.get("wofuer"))[:TAT_MAX]}
                       for e in log if e.get("art") == "wurf" and e.get("pid") in idx],
            "text": swap(erz_text)[:TEXT_MAX]}


def keep(c):
    """Keeps a case, the newest first; a second 👎 with a reason of the same turn replaces it, and counts the report
    (time, world, reason) for the world's hints and the weeks. Returns neu|ersetzt."""
    with _flock:
        d = cases()
        old = [x for x in d.get("faelle") or [] if isinstance(x, dict)]
        rest = [x for x in old if x.get("quelle") != c["quelle"]]
        d["faelle"] = ([c] + rest)[:FAELLE_MAX]
        if len(rest) == len(old):
            d["meldungen"] = ([{"zeit": c["zeit"], "welt": c["welt"], "grund": c["grund"]}] + (d.get("meldungen") or []))[:MELDUNGEN_MAX]
        write_json(FALL_FILE, d)
    return "ersetzt" if len(rest) < len(old) else "neu"


def world_reasons(welt, now=None):
    """The reasons reported at least WELT_SCHWELLE times in this world within WELT_TAGE (Vorschlag 2)."""
    now = clock() if now is None else now
    n = {}
    for m in cases().get("meldungen") or []:
        if m.get("welt") == welt and now - m.get("zeit", 0) <= WELT_TAGE * 86400 and m.get("grund") in GRUENDE:
            n[m["grund"]] = n.get(m["grund"], 0) + 1
    return [g for g in GRUENDE if n.get(g, 0) >= WELT_SCHWELLE]


def world_task(rd, lang):
    """The standing hints of a world for its narrator: fixed texts of GRUENDE, never words of a report."""
    if not features.allowed(FIX, rd.get("owner")):
        return ""
    hints = [GRUENDE[g][4 if lang == "en" else 3] for g in world_reasons(rd.get("welt"))]
    return (" " + ("Often reported in this world, keep to it: " if lang == "en" else "In dieser Welt oft gemeldet, halte dich daran: ")
            + " ".join(hints)) if hints else ""


def weeks(now=None):
    """The reports per week and reason (Vorschlag 4): [{"woche": "2026-W43", "gruende": {grund: n}}], the newest first."""
    now = clock() if now is None else now
    out = {}
    for m in cases().get("meldungen") or []:
        if now - m.get("zeit", 0) > WOCHEN * 7 * 86400 or m.get("grund") not in GRUENDE:
            continue
        y, w, _ = datetime.datetime.fromtimestamp(m["zeit"], datetime.timezone.utc).isocalendar()
        g = out.setdefault(f"{y}-W{w:02d}", {})
        g[m["grund"]] = g.get(m["grund"], 0) + 1
    return [{"woche": k, "gruende": v} for k, v in sorted(out.items(), reverse=True)]


def take(fid):
    """„Als Prüfstand-Szene übernehmen“: a case becomes a scene of the bench (at most EIGENE_MAX, the newest first)."""
    with _flock:
        d = cases()
        c = next((x for x in d.get("faelle") or [] if x.get("id") == fid), None)
        if not c:
            raise LookupError("fall")
        sz = [x for x in d.get("szenen") or [] if x.get("quelle") != c["quelle"]]
        g = GRUENDE.get(c["grund"], GRUENDE["sonst"])
        tat = next((x["text"] for x in c["taten"]), "")[:40]
        s = {"id": "f" + c["id"], "quelle": c["quelle"], "grund": c["grund"], "regel": g[2],
             "name": [f"{g[0]}: {tat}" if tat else g[0], f"{g[1]}: {tat}" if tat else g[1]],
             **{k: c.get(k) or [] for k in ("helden", "taten", "wuerfe")}, **{k: c[k] for k in ("welt", "ton", "lang")}}
        if len(sz) >= EIGENE_MAX:
            raise OverflowError("voll")
        d["szenen"] = [s] + sz
        write_json(FALL_FILE, d)


def drop(key, fid):
    """Deletes a case (key faelle) or a scene taken over (key szenen)."""
    with _flock:
        d = cases()
        old = d.get(key) or []
        d[key] = [x for x in old if x.get("id") != fid]
        if len(d[key]) == len(old):
            raise LookupError(key)
        write_json(FALL_FILE, d)


def cases_view():
    d = cases()
    return {"an": on(), "beheben": features.admin_on(FIX), "gruende": {k: list(v[:2]) for k, v in GRUENDE.items()},
            "wochen": weeks(), "welten": {w: world_reasons(w) for w in sorted({m.get("welt") for m in d.get("meldungen") or []} - {None})},
            "faelle": d.get("faelle") or [],
            "szenen": [{k: s[k] for k in ("id", "name", "grund", "lang")} for s in own_scenes()], "max": FAELLE_MAX, "namen": list(NAMEN),
            "eigene_max": EIGENE_MAX}


@router.get("/api/admin/dungeon/erzaehlfehler", dependencies=[Depends(auth)])
async def show_cases(request: Request):
    guard.limit(request, "dungeonpruef", admin=True)
    return await asyncio.to_thread(cases_view)


@router.post("/api/admin/dungeon/erzaehlfehler", dependencies=[Depends(auth)])
async def change_case(request: Request):
    """{fall, aktion: szene|loeschen} or {szene, aktion: loeschen}; taking a case over only while the bench is on."""
    guard.limit(request, "dungeonpruef", admin=True)
    b = await json_body(request, 200)
    a, fall, sz = b.get("aktion"), b.get("fall"), b.get("szene")
    if a not in ("szene", "loeschen") or not isinstance(fall or sz, str) or bool(fall) == bool(sz) or (sz and a != "loeschen"):
        print("dungeon: erzaehlstand | fall | ungueltig", flush=True)
        raise HTTPException(400, "aktion")
    if a == "szene" and not on():
        print("dungeon: erzaehlstand | fall | aus", flush=True)
        raise HTTPException(409, "aus")
    try:
        if a == "szene":
            await asyncio.to_thread(take, fall)
        else:
            await asyncio.to_thread(drop, "faelle" if fall else "szenen", fall or sz)
    except LookupError:
        print("dungeon: erzaehlstand | fall | fehlt", flush=True)
        raise HTTPException(404, "fall")
    except OverflowError:
        print("dungeon: erzaehlstand | fall | voll", flush=True)
        raise HTTPException(409, "voll")
    print(f"dungeon: erzaehlstand | fall | {'uebernommen' if a == 'szene' else 'geloescht'}", flush=True)
    return await asyncio.to_thread(cases_view)
