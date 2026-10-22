"""IT-Krisenspiel (plan krisenspiel/plan.md, Dominik 2026-10-22 „so umsetzen aber den Szenarien-Ausbau auf 5“, Paket 1):
a text adventure for one profile at a time. An IT emergency (ransomware, SAN outage, power cut, BGP hijacking, BSI
alert) runs as a crisis dashboard: time left, stress, the management's trust, team morale, damage and emergency
budget on top, the systems with their state, the chronicle with the moves and the inspector with every step.

The panel decides everything by fixed rules, never the language model:
- the scenarios are data (krisenspiel_szenarien.json): systems, moves with fixed effects, conditions, events that
  follow by chance (ticks), side issues and the goal; check_data() keeps them consistent;
- every chance comes from the game's seed (incident_seed): the same seed and the same moves give the same game, the
  variants of a scenario (where it started, whether the backup is clean …) are drawn from it at the start;
- time passes by the minutes of a move; the systems that are down cost damage per minute (schaden_min and FAKTOR),
  stress, morale and trust move by fixed formulas (drift), the difficulty (STUFEN) scales time, budget and damage;
- the end, the grade A to F (bewerten) and the achievements (ERFOLGE) are fixed code.
The language model only retells a move in two to four sentences (Funktion „Krisenspiel mit Erzähler“, own switch,
off): it gets the fixed texts of the move as facts, its answer is checked by fixed rules (one paragraph, no links,
markup or code, every number from the facts) and else dropped for the fixed text; it never changes a value. It runs
behind speech (vorrang) and waits at most ERZAEHL_S seconds, during a pause of the model (wartung) not at all.
Nothing a player types is ever run: there is no console in Paket 1 (Paket 2 simulates one, never on the Spark).

Off until the admin allows it (Funktionen → Meine Daten → IT-Krisenspiel, chat.krisenspiel); then for every profile
the admin did not block; guests never. One running game and the last VERLAUF_MAX results per profile in
users/<id>/krisenspiel.json. The journal gets fixed words and numbers only (spiel: …), Live only counts.

    GET    /api/profile/krisenspiel            scenarios, the running game, the inspector, achievements, history
    POST   /api/profile/krisenspiel/neu        {szenario, stufe, seed?, lang}: a new game (replaces the running one)
    POST   /api/profile/krisenspiel/zug        {aktion, zug, lang}: one move; zug must be the game's turn (no double tap)
    DELETE /api/profile/krisenspiel            give up the running game (counts as F)
    DELETE /api/profile/krisenspiel/daten      delete the game, the history and the achievements (also while blocked)
    GET    /api/admin/krisenspiel              Zustand → Live: running games, moves today, profiles (numbers only)
"""
import asyncio
import copy
import hashlib
import json
import os
import random
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from common import DayCounter, load_config, no_think, read_json, write_json
from core import assistant, auth, browser_profile, json_body, own_profile

router = APIRouter()

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "krisenspiel_szenarien.json")
STATI = ("Online", "Degraded", "Critical", "Offline", "Isolated")
# share of an asset's damage per minute in each state
FAKTOR = {"Online": 0.0, "Degraded": 0.3, "Critical": 1.0, "Offline": 1.0, "Isolated": 0.6}
# difficulty: minutes at the start, budget and damage factor, pressure (stress drift and the chance of side issues)
STUFEN = {"uebung": {"zeit": 180, "budget": 1.5, "schaden": 0.7, "druck": 0.7, "name": ("Übung", "Practice")},
          "normal": {"zeit": 120, "budget": 1.0, "schaden": 1.0, "druck": 1.0, "name": ("Normal", "Normal")},
          "ernstfall": {"zeit": 100, "budget": 0.75, "schaden": 1.3, "druck": 1.3, "name": ("Ernstfall", "Emergency")}}
START = {"stress": 20, "vertrauen": 70, "moral": 70}
METRIKEN = ("zeit", "stress", "vertrauen", "moral", "kosten", "budget")
MAX_ZUEGE = 80           # moves in one game at most
VERLAUF_MAX = 20         # results kept per profile
CHRONIK_MAX = 150        # chronicle entries kept in a game
TRACE_MAX = 30           # turns the inspector keeps
SEED_MAX = 999999
ERZAEHL_S = 8            # seconds the narrator may take, else the fixed text stays
ERZAEHL_MIN, ERZAEHL_MAX = 30, 700   # characters of a narration
BODY = 2000              # bytes of a request body
# grade by points (bewerten)
NOTEN = ((85, "A"), (72, "B"), (58, "C"), (45, "D"), (30, "E"), (0, "F"))
ENDEN = {"gewonnen": ("Krise gemeistert", "Crisis mastered"), "zeit": ("Die Zeit ist abgelaufen", "Time ran out"),
         "entlassen": ("Die Geschäftsleitung hat dir den Fall entzogen", "The management took the case away from you"),
         "team": ("Das Team kann nicht mehr", "The team cannot go on"),
         "sackgasse": ("Kein Zug mehr möglich", "No move left"), "aufgegeben": ("Aufgegeben", "Given up")}
# achievements: id, name and what it takes (de, en); the rule is fixed code in erfolge_neu()
ERFOLGE = (("feuertaufe", ("Feuertaufe", "Baptism of fire"), ("Das erste Spiel zu Ende gespielt.", "Finished the first game.")),
           ("gemeistert", ("Krise gemeistert", "Crisis mastered"), ("Ein Spiel gewonnen.", "Won a game.")),
           ("ohne_verlust", ("Zero Data Loss", "Zero data loss"), ("Gewonnen, ohne Daten zu verlieren.", "Won without losing data.")),
           ("schnell", ("Schnell eingedämmt", "Contained fast"), ("Gewonnen mit mindestens der Hälfte der Zeit übrig.", "Won with at least half of the time left.")),
           ("ransom30", ("Ransomware unter 30 Minuten", "Ransomware under 30 minutes"), ("Die Ransomware in höchstens 30 Spielminuten eingedämmt.", "Contained the ransomware within 30 game minutes.")),
           ("sparfuchs", ("Sparfuchs", "Penny pincher"), ("Gewonnen und höchstens ein Fünftel des Notfall-Budgets ausgegeben.", "Won and spent at most a fifth of the emergency budget.")),
           ("teamgeist", ("Teamgeist", "Team spirit"), ("Gewonnen mit einer Team-Moral von mindestens 70 %.", "Won with team morale of at least 70 %.")),
           ("vertrauen", ("Volles Vertrauen", "Full trust"), ("Gewonnen mit mindestens 80 % Vertrauen der Geschäftsleitung.", "Won with at least 80 % of the management's trust.")),
           ("kuehl", ("Kühler Kopf", "Cool head"), ("Gewonnen, ohne dass der Stress je 70 % erreicht hat.", "Won without stress ever reaching 70 %.")),
           ("ernstfall", ("Ernstfall bestanden", "Emergency passed"), ("Auf der Stufe Ernstfall gewonnen.", "Won on the level Emergency.")),
           ("allrounder", ("Allrounder", "All-rounder"), ("Jedes Szenario mindestens einmal gewonnen.", "Won every scenario at least once.")),
           ("bestnote", ("Bestnote", "Top grade"), ("Ein Spiel mit der Note A abgeschlossen.", "Finished a game with grade A.")))
ERFOLG_IDS = tuple(e[0] for e in ERFOLGE)

_day = DayCounter(zuege=0, spiele=0, erzaehlt=0, verworfen=0)   # Zustand → Live, numbers only
_locks = {}
_locks_lock = threading.Lock()


# ---------------------------------------------------------------- the scenarios
def _load_data():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    return d


_DATA = _load_data()
SZENARIEN = {s["id"]: s for s in _DATA["szenarien"]}


def _pair(x):
    return isinstance(x, list) and len(x) == 2 and all(isinstance(v, str) and v.strip() for v in x)


COND_KEYS = {"flags", "ohne", "irgendein", "var", "status", "zug_ab", "min_ab", "alt", "vertrauen_unter", "stress_ueber", "moral_unter"}
EFF_KEYS = {"zeit", "stress", "vertrauen", "moral", "kosten", "budget", "setzt", "details", "flags", "weg", "text", "je", "wenn"}
ACT_KEYS = EFF_KEYS | {"id", "label", "einmal", "max"}
TICK_KEYS = EFF_KEYS | {"id", "chance", "einmal"}


def check_data(d=None):
    """Every problem of the scenario data as a sentence; [] when it is sound (test_krisenspiel)."""
    d = _DATA if d is None else d
    bad = []
    ids = set()

    def cond(c, sz, where):
        if c is None:
            return
        if not isinstance(c, dict) or set(c) - COND_KEYS:
            bad.append(f"{where}: unknown condition {sorted(set(c) - COND_KEYS) if isinstance(c, dict) else c}")
            return
        for k, v in (c.get("var") or {}).items():
            vals = v if isinstance(v, list) else [v]
            known = [x[0] for x in sz.get("varianten", {}).get(k, [])] if sz else []
            if sz and any(x not in known for x in vals):
                bad.append(f"{where}: variant {k}={v}")
        for a, sts in (c.get("status") or {}).items():
            if sz and a not in {x["id"] for x in sz["assets"]} or any(s not in STATI for s in sts):
                bad.append(f"{where}: status {a}")

    def eff(e, sz, where, keys):
        if set(e) - keys:
            bad.append(f"{where}: unknown keys {sorted(set(e) - keys)}")
        cond(e.get("wenn"), sz, where)
        if "text" in e and not _pair(e["text"]):
            bad.append(f"{where}: text")
        for k in ("zeit", "stress", "vertrauen", "moral", "kosten", "budget"):
            if k in e and (not isinstance(e[k], int) or isinstance(e[k], bool)):
                bad.append(f"{where}: {k}")
        assets = {x["id"] for x in sz["assets"]} if sz else set()
        for a, s in (e.get("setzt") or {}).items():
            if sz and a not in assets or s not in STATI:
                bad.append(f"{where}: setzt {a}={s}")
        for a, t in (e.get("details") or {}).items():
            if sz and a not in assets or not _pair(t):
                bad.append(f"{where}: details {a}")
        for j in e.get("je") or []:
            eff(j, sz, where + " je", EFF_KEYS)

    for a in d.get("allgemein", []):
        eff(a, None, "allgemein " + a.get("id", "?"), ACT_KEYS)
        if not _pair(a.get("label")):
            bad.append(f"allgemein {a.get('id')}: label")
    for t in d.get("neben_allgemein", []) + d.get("ticks_allgemein", []):
        eff(t, None, "allgemein " + t.get("id", "?"), TICK_KEYS)
    for sz in d.get("szenarien", []):
        sid = sz.get("id", "?")
        if sid in ids:
            bad.append(f"{sid}: twice")
        ids.add(sid)
        for k in ("titel", "kurz", "start_text"):
            if not _pair(sz.get(k)):
                bad.append(f"{sid}: {k}")
        if not isinstance(sz.get("kosten_ref"), int) or not isinstance(sz.get("budget"), int):
            bad.append(f"{sid}: kosten_ref/budget")
        aids = [x["id"] for x in sz.get("assets", [])]
        if len(aids) != len(set(aids)) or not aids:
            bad.append(f"{sid}: assets")
        for x in sz.get("assets", []):
            if not _pair(x.get("typ")) or not _pair(x.get("details")) or not isinstance(x.get("schaden_min"), int):
                bad.append(f"{sid}: asset {x.get('id')}")
        for k, vals in sz.get("varianten", {}).items():
            if not vals or any(not _pair(v[1]) for v in vals):
                bad.append(f"{sid}: variant {k}")
            for marker in re.findall(r"\{(\w+)\}", " ".join(sz["start_text"])):
                if marker not in sz["varianten"]:
                    bad.append(f"{sid}: placeholder {marker}")
        for e in sz.get("start", []):
            eff(e, sz, f"{sid} start", EFF_KEYS)
        acts = [a.get("id") for a in sz.get("aktionen", [])] + [a.get("id") for a in d.get("allgemein", [])]
        if len(acts) != len(set(acts)):
            bad.append(f"{sid}: action ids twice")
        for a in sz.get("aktionen", []):
            eff(a, sz, f"{sid} {a.get('id')}", ACT_KEYS)
            if not _pair(a.get("label")):
                bad.append(f"{sid} {a.get('id')}: label")
        for t in sz.get("ticks", []) + sz.get("neben", []):
            eff(t, sz, f"{sid} {t.get('id')}", TICK_KEYS)
            if not isinstance(t.get("chance"), int) or not 0 < t["chance"] <= 100:
                bad.append(f"{sid} {t.get('id')}: chance")
        for g in sz.get("ziel", []):
            cond(g, sz, f"{sid} ziel")
        if not sz.get("ziel"):
            bad.append(f"{sid}: no goal")
    return bad


# ---------------------------------------------------------------- fixed rules
def _rng(seed, *parts):
    """The game's chance for one roll: the same seed and the same parts give the same number on every computer."""
    h = hashlib.sha256("|".join(str(p) for p in (seed,) + parts).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _text(pair, st):
    """A [de, en] text with the variant names put in ({herd} → „auf dem Fileserver FS01“)."""
    sz = SZENARIEN[st["szenario"]]
    out = []
    for i in (0, 1):
        t = pair[i]
        for k, vals in sz.get("varianten", {}).items():
            name = next((v[1][i] for v in vals if v[0] == st["var"].get(k)), "")
            t = t.replace("{" + k + "}", name)
        out.append(t)
    return out


def holds(c, st):
    """A condition of the scenario data against the game's state (all parts must hold)."""
    if not c:
        return True
    fl = st["flags"]
    if any(f not in fl for f in c.get("flags", ())):
        return False
    if any(f in fl for f in c.get("ohne", ())):
        return False
    if c.get("irgendein") and not any(f in fl for f in c["irgendein"]):
        return False
    for k, v in (c.get("var") or {}).items():
        if st["var"].get(k) not in (v if isinstance(v, list) else [v]):
            return False
    for a, sts in (c.get("status") or {}).items():
        if st["assets"].get(a, {}).get("status") not in sts:
            return False
    if st["zug"] < c.get("zug_ab", 0) or minutes_gone(st) < c.get("min_ab", 0):
        return False
    for f, n in (c.get("alt") or {}).items():
        if f not in fl or st["zug"] - fl[f] < n:
            return False
    m = st["m"]
    if "vertrauen_unter" in c and not m["vertrauen"] < c["vertrauen_unter"]:
        return False
    if "stress_ueber" in c and not m["stress"] > c["stress_ueber"]:
        return False
    if "moral_unter" in c and not m["moral"] < c["moral_unter"]:
        return False
    return True


def _clamp(st):
    m = st["m"]
    for k in ("stress", "vertrauen", "moral"):
        m[k] = max(0, min(100, int(m[k])))
    m["zeit"] = max(0, int(m["zeit"]))
    m["budget"] = max(0, int(m["budget"]))
    m["kosten"] = max(0, int(m["kosten"]))
    st["max_stress"] = max(st.get("max_stress", 0), m["stress"])


def _apply(st, e, rec):
    """One effect without its je parts; rec collects what changed (for the inspector and the narrator)."""
    s = STUFEN[st["stufe"]]
    m = st["m"]
    for k in ("stress", "vertrauen", "moral"):
        if e.get(k):
            m[k] += e[k]
            rec["delta"][k] = rec["delta"].get(k, 0) + e[k]
    if e.get("zeit"):
        rec["minuten"] += e["zeit"]
    if e.get("kosten"):
        v = round(e["kosten"] * s["schaden"])
        m["kosten"] += v
        rec["delta"]["kosten"] = rec["delta"].get("kosten", 0) + v
    if e.get("budget"):
        m["budget"] -= e["budget"]
        rec["delta"]["budget"] = rec["delta"].get("budget", 0) - e["budget"]
    for a, status in (e.get("setzt") or {}).items():
        old = st["assets"][a]["status"]
        if old != status:
            st["assets"][a]["status"] = status
            rec["assets"].append([a, old, status])
    for a, t in (e.get("details") or {}).items():
        st["assets"][a]["details"] = list(t)
    for f in e.get("flags") or ():
        if f not in st["flags"]:
            st["flags"][f] = st["zug"]
            st["flag_min"][f] = minutes_gone(st) + rec["minuten"]
            rec["flags"].append(f)
    for f in e.get("weg") or ():
        if st["flags"].pop(f, None) is not None:
            rec["weg"].append(f)
    if e.get("text"):
        rec["texte"].append(_text(e["text"], st))


def _effect(st, e, rec):
    """An effect and its je parts; the je conditions are read against the state before the effect."""
    before = copy.deepcopy(st)
    _apply(st, e, rec)
    for j in e.get("je") or ():
        if holds(j.get("wenn"), before):
            rec["je"] += 1
            _apply(st, j, rec)


def _rec():
    return {"delta": {}, "minuten": 0, "assets": [], "flags": [], "weg": [], "texte": [], "je": 0}


def minutes_gone(st):
    return st["m"]["zeit_start"] - st["m"]["zeit"]


def _all_actions(sz):
    return list(sz["aktionen"]) + list(_DATA.get("allgemein", []))


def available(st):
    """The moves the panel offers now, in the scenario's order: condition holds, not used up; a move the budget does
    not cover stays visible but cannot be taken."""
    sz = SZENARIEN[st["szenario"]]
    out = []
    for a in _all_actions(sz):
        used = st["uses"].get(a["id"], 0)
        if a.get("einmal") and used >= 1 or a.get("max") and used >= a["max"]:
            continue
        if not holds(a.get("wenn"), st):
            continue
        cost = {k: a[k] for k in ("zeit", "budget", "stress", "vertrauen", "moral") if a.get(k)}
        free = not a.get("budget") or st["m"]["budget"] >= a["budget"]
        out.append({"id": a["id"], "label": a["label"], "kosten": cost, "frei": free,
                    "warum": [] if free else ["Das Notfall-Budget reicht nicht.", "The emergency budget is not enough."]})
    return out


def new_game(szenario, stufe, seed=None, lang="de", now=None):
    """A fresh game: variants drawn from the seed, the start effects applied."""
    if szenario not in SZENARIEN or stufe not in STUFEN:
        raise ValueError("szenario, stufe")
    sz = SZENARIEN[szenario]
    s = STUFEN[stufe]
    seed = secrets.randbelow(SEED_MAX + 1) if seed is None else int(seed)
    now = time.time() if now is None else now
    var = {k: vals[_rng(seed, "var", k).randrange(len(vals))][0] for k, vals in sorted(sz.get("varianten", {}).items())}
    budget = round(sz["budget"] * s["budget"])
    st = {"v": 1, "id": secrets.token_hex(8), "szenario": szenario, "stufe": stufe, "seed": seed, "var": var,
          "lang": "en" if lang == "en" else "de", "start": int(now), "zug": 0, "max_stress": START["stress"],
          "m": {"zeit": s["zeit"], "zeit_start": s["zeit"], "stress": START["stress"], "vertrauen": START["vertrauen"],
                "moral": START["moral"], "kosten": 0, "budget": budget, "budget_start": budget},
          "assets": {x["id"]: {"status": "Online", "details": list(x["details"])} for x in sz["assets"]},
          "flags": {}, "flag_min": {}, "uses": {}, "done": [], "chronik": [], "trace": [], "ende": None}
    rec = _rec()
    for e in sz.get("start", []):
        if holds(e.get("wenn"), st):
            _apply(st, e, rec)
    _clamp(st)
    st["chronik"].append({"zug": 0, "min": 0, "art": "start", "text": _text(sz["start_text"], st)})
    st["trace"].append({"zug": 0, "steps": [
        _step("eingabe", ("Neues Spiel", "New game"), {"szenario": szenario, "stufe": stufe, "seed": seed}),
        _step("zufall", ("Varianten aus dem Seed", "Variants from the seed"), {"varianten": var}),
        _step("regel", ("Startlage", "Starting situation"), {"systeme": rec["assets"], "werte": rec["delta"]})]})
    return st


def _step(art, titel, daten, ms=0.0):
    return {"art": art, "titel": list(titel), "daten": daten, "ms": round(ms, 1)}


def move(st, aktion, now=None):
    """One move by the panel's fixed rules. Returns the facts of the move (fixed texts) for the narrator.
    Raises ValueError when the move is not offered right now."""
    if st.get("ende"):
        raise ValueError("over")
    t0 = time.perf_counter()
    sz = SZENARIEN[st["szenario"]]
    s = STUFEN[st["stufe"]]
    offer = {a["id"]: a for a in available(st)}
    if aktion not in offer or not offer[aktion]["frei"]:
        raise ValueError("not offered")
    a = next(x for x in _all_actions(sz) if x["id"] == aktion)
    pre_assets = {k: v["status"] for k, v in st["assets"].items()}
    m = st["m"]
    st["zug"] += 1
    st["uses"][aktion] = st["uses"].get(aktion, 0) + 1
    steps = [_step("eingabe", ("Zug", "Move"), {"zug": st["zug"], "aktion": aktion, "label": a["label"]})]
    rec = _rec()
    _effect(st, a, rec)
    minutes = rec["minuten"]
    steps.append(_step("regel", ("Folgen des Zugs (feste Regel)", "Effects of the move (fixed rule)"),
                       {"minuten": minutes, "werte": rec["delta"], "systeme": rec["assets"], "flags": rec["flags"],
                        "weg": rec["weg"], "bedingte_folgen": rec["je"]}))
    # time passes: the systems that were down during the move cost per minute
    per_min = sum(x["schaden_min"] * FAKTOR[pre_assets[x["id"]]] for x in sz["assets"])
    damage = round(per_min * minutes * s["schaden"])
    m["zeit"] -= minutes
    m["kosten"] += damage
    # drift by fixed formulas
    bad = sum(1 for v in st["assets"].values() if v["status"] in ("Critical", "Offline"))
    d_stress = round(bad * 1.5 * s["druck"]) if bad else -3
    d_moral = -3 if m["stress"] + d_stress >= 75 else 0
    d_trust = -2 if m["kosten"] >= sz["kosten_ref"] * s["schaden"] else 0
    m["stress"] += d_stress
    m["moral"] += d_moral
    m["vertrauen"] += d_trust
    steps.append(_step("regel", ("Laufende Kosten und Druck (feste Formeln)", "Running damage and pressure (fixed formulas)"),
                       {"schaden_pro_minute": round(per_min * s["schaden"]), "schaden": damage, "ausfaelle": bad,
                        "stress": d_stress, "moral": d_moral, "vertrauen": d_trust}))
    texts = [{"art": "zug", "text": [" ".join(x[0] for x in rec["texte"]), " ".join(x[1] for x in rec["texte"])]}] \
        if rec["texte"] else []
    rolls = []
    # events that follow (ticks): in order, each once unless the data says otherwise
    for t in list(_DATA.get("ticks_allgemein", [])) + list(sz.get("ticks", [])):
        once = t.get("einmal", True)
        if once and t["id"] in st["done"] or not holds(t.get("wenn"), st):
            continue
        roll = _rng(st["seed"], st["zug"], "tick", t["id"]).randrange(100)
        hit = roll < t["chance"]
        rolls.append({"id": t["id"], "wurf": roll, "chance": t["chance"], "trifft": hit})
        if hit:
            if once:
                st["done"].append(t["id"])
            r2 = _rec()
            _effect(st, t, r2)
            rec["assets"] += r2["assets"]
            if r2["texte"]:
                texts.append({"art": "folge", "text": r2["texte"][0]})
    # at most one side issue per move; pressure makes them likelier
    for n in list(_DATA.get("neben_allgemein", [])) + list(sz.get("neben", [])):
        if n["id"] in st["done"] or not holds(n.get("wenn"), st):
            continue
        roll = _rng(st["seed"], st["zug"], "neben", n["id"]).randrange(100)
        chance = min(100, round(n["chance"] * s["druck"]))
        hit = roll < chance
        rolls.append({"id": n["id"], "wurf": roll, "chance": chance, "trifft": hit})
        if hit:
            st["done"].append(n["id"])
            r2 = _rec()
            _effect(st, n, r2)
            rec["assets"] += r2["assets"]
            if r2["texte"]:
                texts.append({"art": "neben", "text": r2["texte"][0]})
            break
    if rolls:
        steps.append(_step("zufall", ("Würfe aus dem Seed", "Rolls from the seed"), {"seed": st["seed"], "wuerfe": rolls[:16]}))
    _clamp(st)
    gone = minutes_gone(st)
    for x in texts:
        st["chronik"].append({"zug": st["zug"], "min": gone, "art": x["art"], "text": x["text"]})
    end = _end(st)
    if end:
        finish(st, end)
        st["chronik"].append({"zug": st["zug"], "min": gone, "art": "ende", "text": list(ENDEN[end])})
        steps.append(_step("ende", ("Spielende", "Game over"), {"ende": end, "note": st["ende"]["note"], "punkte": st["ende"]["punkte"]}))
    else:
        steps.append(_step("antwort", ("Angebotene Züge", "Moves offered"), {"anzahl": len(available(st))}))
    steps[1]["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    st["chronik"] = st["chronik"][-CHRONIK_MAX:]
    st["trace"].append({"zug": st["zug"], "steps": steps})
    st["trace"] = st["trace"][-TRACE_MAX:]
    return {"label": a["label"], "texte": texts, "systeme": rec["assets"], "minute": gone}


def _end(st):
    sz = SZENARIEN[st["szenario"]]
    m = st["m"]
    if all(holds(g, st) for g in sz["ziel"]):
        return "gewonnen"
    if m["vertrauen"] <= 0:
        return "entlassen"
    if m["moral"] <= 0:
        return "team"
    if m["zeit"] <= 0 or st["zug"] >= MAX_ZUEGE:
        return "zeit"
    if not any(a["frei"] for a in available(st)):
        return "sackgasse"
    return ""


def bewerten(st, end):
    """Points 0 to 100 and the grade A to F by a fixed formula, with its reasons as sentences."""
    sz = SZENARIEN[st["szenario"]]
    s = STUFEN[st["stufe"]]
    m = st["m"]
    won = end == "gewonnen"
    ref = sz["kosten_ref"] * s["schaden"]
    loss = "datenverlust" in st["flags"]
    p = (50 if won else 0) + (20 * m["zeit"] / m["zeit_start"] if won else 0) \
        + 15 * max(0.0, 1 - m["kosten"] / ref) + 10 * m["vertrauen"] / 100 + 5 * m["moral"] / 100 - (10 if loss else 0)
    p = max(0, min(100, round(p)))
    note = next(n for floor, n in NOTEN if p >= floor) if end != "aufgegeben" else "F"
    eur = lambda v: f"{v:,}".replace(",", ".")
    eur_en = lambda v: f"{v:,}"
    why = [list(ENDEN[end]),
           [f"{minutes_gone(st)} Minuten gespielt, {m['zeit']} Minuten Reserve.", f"{minutes_gone(st)} minutes played, {m['zeit']} minutes to spare."],
           [f"Schaden {eur(m['kosten'])} € (Richtwert {eur(round(ref))} €).", f"Damage {eur_en(m['kosten'])} € (benchmark {eur_en(round(ref))} €)."],
           [f"Vertrauen {m['vertrauen']} %, Moral {m['moral']} %.", f"Trust {m['vertrauen']} %, morale {m['moral']} %."],
           ["Datenverlust: ja." if loss else "Kein Datenverlust.", "Data loss: yes." if loss else "No data loss."]]
    return p, note, why


def finish(st, end):
    p, note, why = bewerten(st, end)
    st["ende"] = {"art": end, "punkte": p, "note": note, "gruende": why, "minuten": minutes_gone(st)}


def erfolge_neu(st, prof_data):
    """The achievements this finished game earns that the profile does not have yet (fixed rules)."""
    have = prof_data.get("erfolge", {})
    e = st["ende"]
    m = st["m"]
    won = e["art"] == "gewonnen"
    won_by = dict(prof_data.get("stats", {}).get("gewonnen_je", {}))
    if won:
        won_by[st["szenario"]] = won_by.get(st["szenario"], 0) + 1
    rules = {"feuertaufe": True, "gemeistert": won,
             "ohne_verlust": won and "datenverlust" not in st["flags"],
             "schnell": won and m["zeit"] * 2 >= m["zeit_start"],
             "ransom30": st["szenario"] == "ransomware" and st["flag_min"].get("eingedaemmt", 10 ** 6) <= 30,
             "sparfuchs": won and (m["budget_start"] - m["budget"]) * 5 <= m["budget_start"],
             "teamgeist": won and m["moral"] >= 70, "vertrauen": won and m["vertrauen"] >= 80,
             "kuehl": won and st.get("max_stress", 100) < 70, "ernstfall": won and st["stufe"] == "ernstfall",
             "allrounder": all(won_by.get(k) for k in SZENARIEN), "bestnote": e["note"] == "A"}
    return [k for k in ERFOLG_IDS if rules[k] and k not in have]


# ---------------------------------------------------------------- the profile's file
def _file(uid):
    return profiles._path(uid, "krisenspiel.json")


def _lock(uid):
    with _locks_lock:
        return _locks.setdefault(uid, threading.Lock())


def load(uid):
    d = read_json(_file(uid), {})
    st = d.get("spiel") if isinstance(d.get("spiel"), dict) and d["spiel"].get("szenario") in SZENARIEN \
        and d["spiel"].get("stufe") in STUFEN else None
    return {"spiel": st, "verlauf": [x for x in d.get("verlauf") or [] if isinstance(x, dict)][:VERLAUF_MAX],
            "erfolge": {k: int(v) for k, v in (d.get("erfolge") or {}).items() if k in ERFOLG_IDS and isinstance(v, (int, float))},
            "stats": d.get("stats") if isinstance(d.get("stats"), dict) else {}}


def save(uid, d):
    write_json(_file(uid), d, mode=0o600, ensure_ascii=False, dir_mode=0o700)


def _book(d, now):
    """A finished game into the history, the stats and the achievements."""
    st = d["spiel"]
    new = erfolge_neu(st, d)
    for k in new:
        d["erfolge"][k] = int(now)
    stats = d["stats"]
    stats["gespielt"] = stats.get("gespielt", 0) + 1
    if st["ende"]["art"] == "gewonnen":
        stats["gewonnen"] = stats.get("gewonnen", 0) + 1
        stats.setdefault("gewonnen_je", {})[st["szenario"]] = stats.get("gewonnen_je", {}).get(st["szenario"], 0) + 1
    best = stats.setdefault("beste", {})
    best[st["szenario"]] = max(best.get(st["szenario"], 0), st["ende"]["punkte"])
    st["ende"]["erfolge"] = new
    d["verlauf"] = ([{"id": st["id"], "szenario": st["szenario"], "stufe": st["stufe"], "seed": st["seed"],
                      "ende": st["ende"]["art"], "note": st["ende"]["note"], "punkte": st["ende"]["punkte"],
                      "zuege": st["zug"], "minuten": st["ende"]["minuten"], "t": int(now), "erfolge": new}]
                    + d["verlauf"])[:VERLAUF_MAX]
    print(f"spiel: ende | {st['ende']['art']} | note {st['ende']['note']} | {st['zug']} zuege | {len(new)} erfolge", flush=True)


# ---------------------------------------------------------------- the narrator (language model, only words)
PROMPT = {"de": ("Du erzählst ein IT-Krisenspiel. Du bekommst die Fakten eines Spielzugs. Schreibe zwei bis vier kurze "
                 "Sätze auf Deutsch im Präsens, lebendig wie eine Szene im Rechenzentrum. Nutze nur die Fakten: keine "
                 "neuen Systeme, keine Zahlen, die nicht in den Fakten stehen, keine Befehle und keine Ratschläge, was "
                 "als Nächstes zu tun ist. Kein Markdown, keine Aufzählung."),
          "en": ("You narrate an IT crisis game. You get the facts of one move. Write two to four short sentences in "
                 "English in the present tense, vivid like a scene in the data centre. Use only the facts: no new "
                 "systems, no numbers that are not in the facts, no commands and no advice on what to do next. No "
                 "markdown, no list.")}
_NO = re.compile(r"(?i)https?://|www\.|[<>`{}\[\]|]|^\s*[-*#]|\n\s*[-*#]")


def facts_text(st, facts, lang):
    li = 1 if lang == "en" else 0
    sz = SZENARIEN[st["szenario"]]
    names = {x["id"]: x["name"] for x in sz["assets"]}
    word = {"Online": ("läuft", "running"), "Degraded": ("gestört", "degraded"), "Critical": ("kritisch", "critical"),
            "Offline": ("aus", "off"), "Isolated": ("isoliert", "isolated")}
    lines = [("Szenario: " if li == 0 else "Scenario: ") + sz["titel"][li],
             ("Zug: " if li == 0 else "Move: ") + facts["label"][li]]
    lines += [x["text"][li] for x in facts["texte"]]
    lines += [f"{names[a]}: {word[o][li]} → {word[n][li]}" for a, o, n in facts["systeme"]]
    return "\n".join(lines)


def check_story(text, facts):
    """The narration by fixed rules: plain text, one paragraph, the length, no links or markup, every number from the
    facts. Returns (text, "") or ("", reason)."""
    t = re.sub(r"\s+", " ", no_think(text or "")).strip().strip('"„“')
    if not ERZAEHL_MIN <= len(t) <= ERZAEHL_MAX:
        return "", "laenge"
    if _NO.search(text or "") or "```" in (text or ""):
        return "", "format"
    if len(re.findall(r"[.!?](\s|$)", t)) > 6:
        return "", "saetze"
    known = set(re.findall(r"\d+", facts))
    if any(n not in known for n in re.findall(r"\d+", t)):
        return "", "zahl"
    return t, ""


async def ask_model(system, user):
    """The narrator's words for one move (tests replace this)."""
    import llm
    return await llm.complete(system, user, "Krisenspiel", 220, temperature=0.7, timeout=ERZAEHL_S + 5,
                              ccfg=load_config("chat"), stream=False)


async def narrate(st, facts, lang):
    """(text, reason, ms): the checked narration, or "" with a fixed reason; never raises."""
    import wartung
    if wartung.paused("llm"):
        return "", "pause", 0.0
    f = facts_text(st, facts, lang)
    t0 = time.perf_counter()
    try:
        raw = await asyncio.wait_for(ask_model(PROMPT["en" if lang == "en" else "de"], f), ERZAEHL_S)
    except asyncio.TimeoutError:
        return "", "zeit", (time.perf_counter() - t0) * 1000
    except Exception:
        return "", "fehler", (time.perf_counter() - t0) * 1000
    text, why = check_story(raw, f)
    return text, why, (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------- views
def view(d, uid=None):
    st = d["spiel"]
    out = {"on": True, "erzaehler": bool(uid and features.allowed("krisenerzaehler", uid)),
           "szenarien": [{"id": s["id"], "titel": s["titel"], "kurz": s["kurz"], "systeme": len(s["assets"])}
                         for s in _DATA["szenarien"]],
           "stufen": [{"id": k, "name": list(v["name"]), "zeit": v["zeit"]} for k, v in STUFEN.items()],
           "erfolge": [{"id": k, "name": list(n), "text": list(t), "t": d["erfolge"].get(k, 0)} for k, n, t in ERFOLGE],
           "verlauf": [dict(x, titel=SZENARIEN[x["szenario"]]["titel"]) for x in d["verlauf"] if x.get("szenario") in SZENARIEN],
           "stats": {"gespielt": d["stats"].get("gespielt", 0), "gewonnen": d["stats"].get("gewonnen", 0),
                     "beste": d["stats"].get("beste", {})},
           "spiel": None}
    if st:
        sz = SZENARIEN[st["szenario"]]
        out["spiel"] = {"id": st["id"], "szenario": st["szenario"], "titel": sz["titel"], "stufe": st["stufe"],
                        "seed": st["seed"], "zug": st["zug"], "m": st["m"], "min": minutes_gone(st),
                        "assets": [{"id": x["id"], "name": x["name"], "typ": x["typ"], "status": st["assets"][x["id"]]["status"],
                                    "details": st["assets"][x["id"]]["details"]} for x in sz["assets"]],
                        "chronik": st["chronik"], "trace": st["trace"], "ende": st["ende"],
                        "aktionen": [] if st["ende"] else available(st)}
    return out


# ---------------------------------------------------------------- endpoints
def admin_on():
    return features.admin_on("krisenspiel")


def _need(uid):
    if not features.allowed("krisenspiel", uid):
        print("spiel: abgelehnt | nicht freigegeben", flush=True)
        raise HTTPException(403, features.missing_text("krisenspiel", uid))


def _lang(b):
    return "en" if b.get("lang") == "en" else "de"


@router.get("/api/profile/krisenspiel", dependencies=[Depends(assistant)])
def show(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    return view(load(uid), uid)


@router.post("/api/profile/krisenspiel/neu", dependencies=[Depends(assistant)])
async def neu(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, BODY)
    sid, stufe, seed = b.get("szenario"), b.get("stufe", "normal"), b.get("seed")
    if sid not in SZENARIEN or stufe not in STUFEN or seed is not None and (
            not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= SEED_MAX):
        print("spiel: neu abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "szenario, stufe, seed")

    def go():
        with _lock(uid):
            d = load(uid)
            if d["spiel"] and not d["spiel"].get("ende"):
                print("spiel: altes spiel ersetzt | nicht beendet", flush=True)
            d["spiel"] = new_game(sid, stufe, seed, _lang(b))
            save(uid, d)
            return d
    d = await asyncio.to_thread(go)
    _day.bump("spiele")
    print(f"spiel: neu | {sid} | {stufe} | {profiles.log_name(prof)}", flush=True)
    return view(d, uid)


@router.post("/api/profile/krisenspiel/zug", dependencies=[Depends(assistant)])
async def zug(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, BODY)
    aktion, turn, lang = b.get("aktion"), b.get("zug"), _lang(b)
    if not isinstance(aktion, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", aktion) or not isinstance(turn, int):
        print("spiel: zug abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "aktion, zug")

    def go():
        with _lock(uid):
            d = load(uid)
            st = d["spiel"]
            if not st or st.get("ende"):
                return None, None, 404
            if st["zug"] != turn:
                return None, None, 409
            try:
                facts = move(st, aktion)
            except ValueError:
                return None, None, 422
            if st.get("ende"):
                _book(d, time.time())
            save(uid, d)
            return d, facts, 200
    t0 = time.perf_counter()
    d, facts, code = await asyncio.to_thread(go)
    if code != 200:
        why = {404: "kein spiel", 409: "alter zug", 422: "nicht angeboten"}[code]
        print(f"spiel: zug abgelehnt | {why}", flush=True)
        raise HTTPException(code, why)
    _day.bump("zuege")
    print(f"spiel: zug | ok | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)
    st = d["spiel"]
    if features.allowed("krisenerzaehler", uid) and facts["texte"]:
        text, why, ms = await narrate(st, facts, lang)
        if text:
            _day.bump("erzaehlt")
        else:
            _day.bump("verworfen")
        print(f"spiel: erzaehler | {'ok' if text else why} | {round(ms)} ms", flush=True)

        def keep():
            with _lock(uid):
                d2 = load(uid)
                s2 = d2["spiel"]
                if not s2 or s2["id"] != st["id"] or s2["zug"] != st["zug"]:
                    return d2
                if text:
                    for c in reversed(s2["chronik"]):
                        if c["zug"] == s2["zug"] and c["art"] == "zug":
                            c["erzaehlt"], c["lang"] = text, lang
                            break
                step = _step("modell", ("Erzähler (Sprachmodell)", "Narrator (language model)"),
                             {"ok": bool(text), "zeichen": len(text), "verworfen": why,
                              "werte_uebernommen": 0}, ms)
                s2["trace"][-1]["steps"].insert(-1, step)
                save(uid, d2)
                return d2
        d = await asyncio.to_thread(keep)
    return view(d, uid)


@router.delete("/api/profile/krisenspiel", dependencies=[Depends(assistant)])
def aufgeben(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    with _lock(uid):
        d = load(uid)
        st = d["spiel"]
        if not st or st.get("ende"):
            print("spiel: aufgeben abgelehnt | kein spiel", flush=True)
            raise HTTPException(404, "no game")
        finish(st, "aufgegeben")
        st["chronik"].append({"zug": st["zug"], "min": minutes_gone(st), "art": "ende", "text": list(ENDEN["aufgegeben"])})
        _book(d, time.time())
        save(uid, d)
    return view(d, uid)


@router.delete("/api/profile/krisenspiel/daten", dependencies=[Depends(assistant)])
def daten_loeschen(request: Request, prof=Depends(browser_profile)):
    """The own game data: allowed also while the admin blocked the game for this profile (Richtlinie Teil 3)."""
    guard.limit(request, "spiel", prof["id"])
    _own_clear(prof["id"])
    return {"ok": True}


@router.get("/api/admin/krisenspiel", dependencies=[Depends(auth)])
def admin_state():
    """Zustand → Live: sums over all profiles, never a scenario of a person, a move or a name."""
    return for_live()


# ---------------------------------------------------------------- Live and own data
_live = {"at": 0.0, "d": None}
LIVE_CACHE = 20


def for_live():
    """Running games and profiles with a game file, moves and narrations today (numbers only)."""
    if not admin_on():
        return {"on": False}
    if _live["d"] is None or time.time() - _live["at"] >= LIVE_CACHE:
        running = profs = 0
        for uid in profiles.user_ids():
            if not os.path.exists(_file(uid)):
                continue
            profs += 1
            st = load(uid)["spiel"]
            running += bool(st and not st.get("ende"))
        _live.update(at=time.time(), d={"laufend": running, "profile": profs})
    t = _day.today()
    return dict(_live["d"], on=True, zuege=t["zuege"], spiele=t["spiele"], erzaehlt=t["erzaehlt"], verworfen=t["verworfen"])


def _own_count(uid):
    d = load(uid)
    return len(d["verlauf"]) + (1 if d["spiel"] else 0)


def _own_clear(uid):
    with _lock(uid):
        try:
            os.remove(_file(uid))
        except FileNotFoundError:
            pass
    _live["d"] = None
    print("spiel: daten geloescht | eigene daten", flush=True)


features.OWN["krisenspiel"] = (_own_count, _own_clear)
