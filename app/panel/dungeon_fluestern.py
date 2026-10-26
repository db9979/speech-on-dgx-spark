"""KI-Dungeon-Master: Flüstern mit einer Figur (D&D ideas round 2, idea 5, Dominik 2026-10-26 „1-9 umsetzten
reihenfolge überlasse ich dir.“; the secret word with the innkeeper of the tabletop, only as an idea, own code).

Once a turn a seat may whisper to a person of the scene (figures: the people of the NSC memory in the scene and those
who spoke in the last turns): a line of at most TEXT_MAX characters, typed or spoken, never from the car. The model
answers as that person (at most ANTWORT_MAX characters, the person's card, its attitude towards the hero, the place, the
last narration; the whisper only as game text between <<< and >>>), the panel checks the answer by fixed rules (plain
text, no word the round refuses) and keeps it only for that seat (rd["fluester"][pid]); the host sees only that a seat
whispered with whom, never what. The answer is never read aloud at the table; the seat's own device may speak it.
By fixed rules of the panel, never the model's:
  attitude   the answer may make the person a step warmer or cooler (dungeon_nsc.apply: one step per hero and turn)
  gift       a person at least GESCHENK_HALTUNG („herzlich“) towards the hero may give up to GESCHENK gold, once a round
  betrayal   a d20 at or below VERRAT − the attitude: the person tells on; the table sees „X erzählt weiter …“ and the
             next narration gets the whisper as game text (betrayed_lines)

Off by default: the admin's switch dungeonfluestern (features.py, chat.dungeon_fluestern) for the round's host.
Journal: fixed words and numbers („dungeon: fluestern | …“), Live only counts.

    POST /api/profile/dungeon/{rid}/fluestern   {an, text}: the own seat whispers
    POST /api/dungeon/fluestern                 {code, an, text}: a guest's seat whispers
"""
import asyncio
import json
import random

from fastapi import APIRouter, Depends, Request

import features
import guard
import textnorm
from common import DayCounter
from core import assistant, browser_profile, json_body

router = APIRouter()
KEY = "dungeonfluestern"
TEXT_MAX = 200
ANTWORT_MAX = 400
LISTE_MAX = 12             # whispers a seat keeps
VERRAT = 3                 # a d20 at or below this minus the attitude: the person tells on
GESCHENK = 10              # gold a fond person may give, once a round
GESCHENK_HALTUNG = 2
SZENE_ZUEGE = 2
BODY = 2048
TOKENS = 400

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["antwort"],
          "properties": {"antwort": {"type": "string", "maxLength": ANTWORT_MAX + 100},
                         "haltung": {"type": "string", "enum": ["", "besser", "schlechter"]},
                         "gold": {"type": "integer", "minimum": 0, "maximum": GESCHENK}}}
AUFGABE = {
    "de": ("Ein Held flüstert einer Figur etwas zu, die anderen hören es nicht. Antworte in antwort als diese Figur, in "
           "ihrer Art, mit ihrem Wissen, wörtlich und höchstens {n} Zeichen, ohne Zahlen von Werten. Die Figur entscheidet "
           "nichts für den Helden. Ihr Wunsch und ihr Geheimnis treiben sie an; das Geheimnis verrät sie nur mit gutem "
           "Grund. haltung besser oder schlechter, wenn das Flüstern sie für den Helden gewinnt oder verärgert. gold nur, "
           "wenn sie dem Helden etwas schenkt (höchstens {g}); ob es ankommt, entscheidet das Panel."),
    "en": ("A hero whispers something to a person, the others do not hear it. Answer in antwort as that person, in its "
           "manner, with its knowledge, in its own words and at most {n} characters, without numbers of values. The "
           "person decides nothing for the hero. Its wish and secret drive it; it gives the secret away only for a good "
           "reason. haltung besser or schlechter when the whisper wins it over or angers it. gold only when it gives the "
           "hero something (at most {g}); the panel decides whether it arrives."),
}

_day = DayCounter(gefluestert=0, verraten=0, geschenkt=0, stumm=0, abgelehnt=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def figures(rd):
    """{name in small letters: name}: the people of the scene a seat may whisper to."""
    import dungeon_nsc
    out = {k: rd["nsc"][k]["name"] for k in dungeon_nsc.scene(rd)} if dungeon_nsc.on(rd) else {}
    zug = rd.get("zug", 0)
    for e in rd.get("log") or []:
        if e.get("art") == "dm" and e.get("n", 0) > zug - SZENE_ZUEGE:
            for x in e.get("npc") or []:
                n = str(x.get("name", "")).strip()[:40] if isinstance(x, dict) else ""
                if len(n) >= 2:
                    out.setdefault(n.lower(), n)
    return out


def _mine(rd, pid):
    return (rd.get("fluester") or {}).get(pid) or []


def free(rd, pid):
    """Whether the seat may still whisper this turn."""
    return not any(x["zug"] == rd.get("zug") for x in _mine(rd, pid))


def prepare(dm, r, rd, pid, uid, an, text):
    """Before the model: the fixed rules of a whisper; returns what the model gets and what keep needs."""
    import dungeon_auto
    if not on(rd):
        raise LookupError("fluestern aus")
    if rd.get("status") != "laeuft":
        raise TimeoutError("zug")
    h = (rd["plaetze"].get(pid) or {}).get("held")
    if not h:
        raise LookupError("platz")
    if dm.zustand(h):
        raise ValueError("boden")
    if dungeon_auto.im_auto(uid):
        raise ValueError("fluestern auto")
    if not free(rd, pid):
        raise FileExistsError("fluestern oft")
    figs = figures(rd)
    k = str(an or "").strip().lower()
    if k not in figs:
        raise LookupError("figur")
    t = dm.plain(text, TEXT_MAX)
    if len(t) < 2:
        raise ValueError("eingabe")
    if dm.bad_words(r, rd, t):
        raise ValueError("wortliste")
    return {"pid": pid, "k": k, "an": figs[k], "text": t, "zug": rd["zug"], "held": h["name"]}


def ask_parts(dm, r, rd, ctx):
    """The model's rules and data for the answer: the person's card, its attitude, the place, the last narration; the
    whisper only between <<< and >>>."""
    import dungeon_nsc
    lang = "en" if rd.get("lang") == "en" else "de"
    li = 1 if lang == "en" else 0
    system = dm.PANEL_REGELN[lang].format(ton=dm._ton(r, rd)["regel"][li]) + "\n\n" + AUFGABE[lang].format(n=ANTWORT_MAX, g=GESCHENK)
    x = (rd.get("nsc") or {}).get(ctx["k"]) if dungeon_nsc.on(rd) else None
    figur = {"name": ctx["an"]}
    if x:
        figur.update({f: v[li] for f, v in (x.get("karte") or {}).items() if isinstance(v, list) and len(v) == 2})
        figur["wesen"] = dungeon_nsc.trait_words(x, li)
        figur["haltung"] = dungeon_nsc.word(x.get("haltung", {}).get(ctx["held"].lower(), 0), li)
    last = next((e.get("text", "") for e in reversed(rd.get("log") or []) if e.get("art") == "dm"), "")
    head = json.dumps({"figur": figur, "held": ctx["held"], "szene": rd.get("szene") or {}, "zuletzt": str(last)[:600]}, ensure_ascii=False)
    return system, f"{head}\n<<<\n{textnorm.defuse(ctx['held'] + ': ' + ctx['text'])}\n>>>"


def check(dm, r, rd, obj):
    """The model's answer by fixed rules: {antwort, haltung, gold} or None."""
    if not isinstance(obj, dict):
        return None
    a = dm.plain(obj.get("antwort"), ANTWORT_MAX)
    if len(a) < 3 or dm.bad_words(r, rd, a):
        return None
    g = obj.get("gold")
    return {"antwort": a, "haltung": obj.get("haltung") if obj.get("haltung") in ("besser", "schlechter") else "",
            "gold": g if isinstance(g, int) and not isinstance(g, bool) and 0 < g <= GESCHENK else 0}


def keep(dm, r, rd, ctx, ans, rng=None):
    """Under the lock: the answer for the seat, the attitude, a gift, the betrayal by the panel's d20."""
    import dungeon_nsc
    rng = rng or random
    pid = ctx["pid"]
    if rd.get("zug") != ctx["zug"]:
        raise TimeoutError("zug")
    if not free(rd, pid):
        raise FileExistsError("fluestern oft")
    h = (rd["plaetze"].get(pid) or {}).get("held")
    if not h:
        raise LookupError("platz")
    x = (rd.get("nsc") or {}).get(ctx["k"]) if dungeon_nsc.on(rd) else None
    held = h["name"].lower()
    if x and ans["haltung"]:
        dungeon_nsc.apply(dm, rd, [{"name": ctx["k"], "held": held, "schritt": 1 if ans["haltung"] == "besser" else -1}])
    haltung = (x.get("haltung") or {}).get(held, 0) if x else 0
    gold = 0
    schon = rd.setdefault("fluester_gold", [])
    if ans["gold"] and haltung >= GESCHENK_HALTUNG and ctx["k"] not in schon:
        gold = ans["gold"]
        h["gold"] = h.get("gold", 0) + gold
        schon.append(ctx["k"])
        _day.bump("geschenkt")
        print("dungeon: fluestern | geschenk", flush=True)
    w = rng.randint(1, 20)
    verraten = w <= VERRAT - haltung
    e = {"zug": ctx["zug"], "an": ctx["an"], "text": ctx["text"], "antwort": ans["antwort"], "gold": gold, "verraten": verraten}
    rd.setdefault("fluester", {})[pid] = (_mine(rd, pid) + [e])[-LISTE_MAX:]
    if verraten:
        z = rd["zug"] + (1 if rd.get("dm") else 0)     # while the turn is being told: the next narration tells on
        rd["verrat"] = [v for v in rd.get("verrat") or [] if v["zug"] >= rd["zug"]] + [{"zug": z, "an": ctx["an"], "wer": h["name"], "text": ctx["text"]}]
        dm._log(rd, "verrat", pid=pid, name=h["name"], an=ctx["an"])
        _day.bump("verraten")
        print("dungeon: fluestern | verraten", flush=True)
    _day.bump("gefluestert")
    print(f"dungeon: fluestern | gefluestert | w{w}", flush=True)
    return e


def betrayed_lines(rd):
    """The whispers a person told on this turn, as game text for the narration (dungeon.facts puts them between <<< and
    >>>); nothing else of a whisper ever reaches the narration."""
    return [f"{v['an']} ({v['wer']}): {v['text']}" for v in rd.get("verrat") or [] if v.get("zug") == rd.get("zug")]


TASK = {"de": " Steht im Spieltext eine Zeile „Figur (Held): …“, hat diese Figur verraten, was der Held ihr zugeflüstert hat; "
              "lass sie es in dieser Szene weitererzählen.",
        "en": " When the game text holds a line \"person (hero): …\", that person has told on what the hero whispered to it; "
              "let it pass it on in this scene."}


def task(rd, lang):
    return TASK[lang] if on(rd) and betrayed_lines(rd) else ""


def view(rd, pid, host):
    """The seat's own whispers with the answers, whom it may whisper to now; the host only that and with whom other
    seats whispered (never what)."""
    if not on(rd):
        return None
    out = {"frei": bool(pid in rd["plaetze"] and free(rd, pid)), "figuren": sorted(figures(rd).values()) if pid else [],
           "meine": [{k: x[k] for k in ("zug", "an", "text", "antwort", "gold", "verraten")} for x in _mine(rd, pid)][-LISTE_MAX:]}
    if host:
        names = {q: (p.get("held") or {}).get("name", "") for q, p in rd["plaetze"].items()}
        out["andere"] = [{"wer": names.get(q, ""), "an": x["an"], "zug": x["zug"]} for q, xs in (rd.get("fluester") or {}).items()
                         if q != pid for x in xs][-LISTE_MAX:]
    return out


def for_live():
    """Numbers only: whispers, betrayals, gifts, answers refused, refused requests today."""
    t = _day.counts()
    return {k: t[k] for k in ("gefluestert", "verraten", "geschenkt", "stumm", "abgelehnt")}


# ---------------------------------------------------------------- routes
async def _whisper(rid, seat, uid, b):
    import dungeon as dm
    try:
        def first():
            pid = seat()
            rd = dm._round(dm._read(), rid)
            r = dm.rules()
            ctx = prepare(dm, r, rd, pid, uid, b.get("an"), b.get("text"))
            return r, ctx, ask_parts(dm, r, rd, ctx)
        r, ctx, (system, user) = await asyncio.to_thread(first)
        obj = await dm._ask_json(system, user, SCHEMA, "fluestern", TOKENS)

        def second():
            with dm._lock:
                d = dm._read()
                rd = dm._round(d, rid)
                ans = check(dm, r, rd, obj)
                if not ans:
                    _day.bump("stumm")
                    print("dungeon: fluestern | stumm", flush=True)
                    raise LookupError("stumm figur")
                keep(dm, r, rd, ctx, ans)
                dm._write(d)
            return dm.view(rid, ctx["pid"])
        return await asyncio.to_thread(second)
    except dm.KNOWN as e:
        _day.bump("abgelehnt")
        print(f"dungeon: fluestern | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/fluestern", dependencies=[Depends(assistant)])
async def fluestern(rid: str, request: Request, prof=Depends(browser_profile)):
    """{an, text}: the own seat whispers to a person of the scene."""
    import dungeon as dm
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonfluester", uid)
    b = await json_body(request, BODY)
    return await _whisper(rid, lambda: dm._seat_uid(rid, uid), uid, b)


@router.post("/api/dungeon/fluestern")
async def gast_fluestern(request: Request):
    """{"code", "an", "text"}: a guest's seat whispers."""
    import dungeon as dm
    b, rid, pid = await dm._guest(request, BODY)
    guard.limit(request, "dungeonfluester")
    return await _whisper(rid, lambda: pid, None, b)
