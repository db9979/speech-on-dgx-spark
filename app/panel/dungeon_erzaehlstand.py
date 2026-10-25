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

Points per scene: 2 when the first try passes, 1 after a rewrite, 0 when refused or only the panel's repair is left;
the checks scenes 2 or 0. The model's own Einordnung (systemone use "erzaehler", Einordnung mit Wahrscheinlichkeit:
how vivid, how well it follows the actions and dice) stands beside it as the model's own view, never as points. The
result per model name (llm.known_model) into STATE/dungeon-erzaehlstand.json (dateien.py), the last MODELLE_MAX models
side by side. Only while „Erzähler-Prüfstand“ is on (features.py, below the Dungeon-Master).

    GET  /api/admin/dungeon/erzaehlstand     the models measured, the scenes, whether it is on and running
    POST /api/admin/dungeon/erzaehlstand     „Jetzt prüfen“ (rate-limited, one run at a time)

Journal lines „dungeon: erzaehlstand | …“ with fixed words and numbers only.
"""
import asyncio
import os
import random
import re
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
}
LEVELS = ["gar nicht", "teilweise", "ganz"]
_run = {"laeuft": False, "seit": 0.0, "task": None}


def on():
    return features.admin_on("dungeonerzaehlstand")


def clock():
    return time.time()


class _Fest:
    """The panel's fixed dice of a scene: randint gives WURF for a check (d20), else the middle; randrange the first."""

    def randint(self, a, b):
        return WURF if b == 20 else (a + b) // 2

    def randrange(self, n):
        return 0


def _round(r, lang="de", ton=None, taten=(("Arvid", ""),)):
    """A round only in memory: the first world, the tone (else the first one above the children's), a seat per hero
    with its action this turn."""
    toene = [t["id"] for t in r["toene"]]
    ton = ton if ton in toene else next((t for t in toene if t != min(toene)), toene[0])
    ks, volk = [k["id"] for k in r["klassen"]], r["voelker"][0]["id"]
    rd = {"owner": "", "titel": "Prüfstand", "welt": r["welten"][0]["id"], "ton": ton, "zug_s": 0, "lang": lang, "einstieg": "",
          "prompt": "", "made": 0, "until": 0, "status": "laeuft", "zug": 2, "zug_t": 0, "pause": False, "offen": {}, "still": {},
          "szene": {"ort": "", "stimmung": ""}, "log": [], "dm": "", "stunden": 1, "vorlesen": False, "erzaehlweise": "normal",
          "plaetze": {}}
    for i, (name, tat) in enumerate(taten):
        h = dungeon.new_hero(r, {"name": name, "volk": volk, "klasse": ks[i % len(ks)]}, random.Random(i))
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
    if sid == "kampf":
        rd = _round(r, taten=(("Arvid", "Ich greife den vordersten Gegner mit meiner Waffe an."),))
        held = [p["held"] for p in rd["plaetze"].values()]
        foe = min(r["gegner"], key=lambda g: (abs(g.get("stufe", 0) - 0.25), g["id"]))
        rd["kampf"] = {"gegner": kampf.lineup([(foe, 2)], 0, len(held)), "seit": 1, "budget": 100, "gefahr": "mittel",
                       "leben0": sum(h["leben"] for h in held), "helden": ["p0"]}
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
    return _round(r, taten=(("Arvid", "Ich wünsche den anderen einen guten Morgen und packe mein Brot aus."),)), None


async def play(r, sid):
    """One scene through the real steps of a turn; returns its result."""
    rd, proben = scene(r, sid)
    t0 = time.monotonic()
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
    out = {"punkte": punkte, "grund": grund, "versuche": len(tries), "laenge": len(text), "sekunden": round(time.monotonic() - t0, 1)}
    e = await _einordnung(rd, text) if text else None
    if e:
        out["einordnung"] = e
    return out


def questions():
    import systemone
    return {"lebendig": systemone.score("Wie lebendig und bildhaft erzählt die Erzählung die Szene?", LEVELS),
            "folgt": systemone.score("Wie genau folgt die Erzählung den Aktionen der Spieler und den Würfen?", LEVELS)}


async def _einordnung(rd, text):
    """The model's own view (systemone use "erzaehler"), the scene as data; None when Einordnung is off or unsure."""
    import systemone
    if not features.admin_on("einordnung"):
        return None
    taten = "\n".join(f"{rd['plaetze'][pid]['held']['name']}: {a['text']}" for pid, a in rd["offen"].items())
    try:
        ans = await systemone.ask(load_config().get("chat", {}), "erzaehler", f"Aktionen:\n{taten}\nErzählung: {text}", questions(), timeout=30)
    except systemone.Unavailable:
        return None
    return {k: round(ans[k]["score"], 2) for k in ("lebendig", "folgt")}


def last():
    return read_json(FILE, {}) or {}


async def _go():
    """One run: every scene, then the model's line in the file; one at a time."""
    import llm
    t0 = time.monotonic()
    print("dungeon: erzaehlstand | start", flush=True)
    try:
        r = dungeon.rules()
        szenen = {}
        for sid in SZENEN:
            szenen[sid] = await play(r, sid)
            print(f"dungeon: erzaehlstand | szene | {sid} | {szenen[sid]['punkte']} punkte", flush=True)
        name = (llm.known_model() or "unbekannt")[:80]
        d = last()
        ms = dict(d.get("modelle") or {})
        ms[name] = {"zeit": int(clock()), "punkte": sum(x["punkte"] for x in szenen.values()), "max": 2 * len(SZENEN),
                    "sekunden": round(time.monotonic() - t0, 1), "szenen": szenen}
        ms = dict(sorted(ms.items(), key=lambda kv: -kv[1]["zeit"])[:MODELLE_MAX])
        await asyncio.to_thread(write_json, FILE, {"modelle": ms})
        print(f"dungeon: erzaehlstand | fertig | {ms[name]['punkte']} von {ms[name]['max']} | {int(time.monotonic() - t0)} s", flush=True)
    except Exception as e:
        print(f"dungeon: erzaehlstand | fehler | {type(e).__name__}", flush=True)
    finally:
        _run["laeuft"] = False


def _spawn():
    _run["task"] = asyncio.create_task(_go())             # kept, so the run is not collected


def view():
    d = last()
    return {"an": on(), "laeuft": _run["laeuft"], "szenen": [[k, list(v)] for k, v in SZENEN.items()],
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
    """For the live overview: the models measured, the best points, whether a run is on."""
    ms = last().get("modelle") or {}
    return {"modelle": len(ms), "beste": max((m["punkte"] for m in ms.values()), default=0), "max": 2 * len(SZENEN),
            "laeuft": _run["laeuft"]}
