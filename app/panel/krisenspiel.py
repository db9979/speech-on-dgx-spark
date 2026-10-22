"""IT-Krisenspiel (plan krisenspiel/plan.md, Dominik 2026-10-22 „so umsetzen aber den Szenarien-Ausbau auf 5“, Paket 1):
a text adventure for one profile at a time. An IT emergency (ransomware, SAN outage, power cut, BGP hijacking, BSI
alert; Paket 4: DDoS, data leak, insider, cloud outage, poisoned update, CEO fraud, deleted database) runs as a crisis dashboard: time left, stress, the management's trust, team morale, damage and emergency
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
Nothing a player types is ever run: the console (Paket 2, krisenkonsole.py with the Linux simulation krisenlinux.py)
cuts a line by fixed rules and answers from the game's own simulated world; a typed move is the same move as its
button, the mode „nur Konsole“ hides the buttons (+KONSOLE_BONUS points when won).

Off until the admin allows it (Funktionen → Meine Daten → IT-Krisenspiel, chat.krisenspiel); then for every profile
the admin did not block; guests never. One running game and the last VERLAUF_MAX results per profile in
users/<id>/krisenspiel.json. The journal gets fixed words and numbers only (spiel: …), Live only counts.

    GET    /api/profile/krisenspiel            scenarios, the running game, the inspector, achievements, history
    GET    /api/profile/krisenspiel/anleitung  the guide (krisenanleitung.py), the same for everyone
    POST   /api/profile/krisenspiel/neu        {szenario|zufall, stufe, modus?, uhr?, seed?, lang}: a new game (replaces the running one)
    POST   /api/profile/krisenspiel/zug        {aktion, zug, lang}: one move; zug must be the game's turn (no double tap)
    POST   /api/profile/krisenspiel/konsole    {zeile, zug, lang}: one line at the console (never run, krisenkonsole)
    POST   /api/profile/krisenspiel/datei      {aktion: speichern|schliessen, text?, zug}: the file open in nano or vi
    POST   /api/profile/krisenspiel/uhr        {aktion: tick|pause|weiter}: „Uhr läuft“, real time as game time
    DELETE /api/profile/krisenspiel            give up the running game (counts as F)
    DELETE /api/profile/krisenspiel/daten      delete the game, the history and the achievements (also while blocked)
    (playing together, krisenteam.py: /api/profile/krisenspiel/team and the seats' /api/krise/lage, /api/krise/zug)
    GET    /api/admin/krisenspiel              Zustand → Live: running games, moves today, profiles (numbers only)
"""
import asyncio
import copy
import datetime
import hashlib
import json
import os
import random
import re
import secrets
import sys
import threading
import time
import zoneinfo

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import krisenanleitung
import krisenkonsole
import krisenlinux
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
KONSOLE_BONUS = 5        # points for a game won in the mode „nur Konsole“
MODI = ("knoepfe", "konsole")
ZUFALL = "zufall"         # szenario of a new game: one of the scenarios by chance
# „Uhr läuft“ (Dominik 2026-10-22 „Variante 2“): real time passes as game time while the page is open
UHR_S = 10               # real seconds per game minute
UHR_LUECKE = 60          # real seconds counted at most between two requests (the open page asks every UHR_POLL)
UHR_POLL = 20            # seconds between the page's ticks while it is visible
UHR_BONUS = 5            # points for a game won with the clock running
UHR_PAUSE = ("uebung", "normal")   # levels with a pause button
UHR_LABEL = ("Die Uhr ist abgelaufen", "The clock ran out")
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
           ("bestnote", ("Bestnote", "Top grade"), ("Ein Spiel mit der Note A abgeschlossen.", "Finished a game with grade A.")),
           ("ohne_knopf", ("Ohne Knopf gelöst", "Solved without a button"), ("Gewonnen, jeder Zug an der Konsole getippt.", "Won with every move typed at the console.")),
           ("gegen_uhr", ("Gegen die Uhr", "Against the clock"), ("Mit laufender Uhr gewonnen, ohne Pause.", "Won with the clock running, without a pause.")),
           ("delegiert", ("Gut delegiert", "Well delegated"), ("Gewonnen und mindestens vier Aufgaben ans Team gegeben.", "Won and handed at least four tasks to the team.")),
           ("ciso", ("CISO", "CISO"), ("Den höchsten Rang der Laufbahn erreicht.", "Reached the highest rank of the career.")),
           ("herausforderung", ("Herausforderung angenommen", "Challenge accepted"),
            ("Eine Tages- oder Wochen-Herausforderung beim ersten Versuch gewonnen.", "Won a daily or weekly challenge at the first try.")),
           ("mutig", ("Mutig", "Bold"), ("Mit mindestens zwei Mutatoren gewonnen.", "Won with at least two mutators.")),
           ("durchgehalten", ("Durchgehalten", "Saw it through"),
            ("Eine Kampagne bis zum Ende des letzten Kapitels gespielt.", "Played a campaign to the end of its last chapter.")))
ERFOLG_IDS = tuple(e[0] for e in ERFOLGE)
# roles of a game played together (Paket 11, krisenteam.py): every move has one (data key "rolle", else technik);
# Leitung may take every move, the others only their own; a game alone is played as Leitung
ROLLEN = {"technik": ("Technik", "Engineering"), "kommunikation": ("Kommunikation", "Communication"),
          "leitung": ("Leitung", "Lead")}


def darf(rolle, a):
    """May this role take the move a (krisenteam)?"""
    return rolle == "leitung" or a.get("rolle", "technik") == rolle


# Team und Laufbahn (Paket 3): colleagues with two subjects each take a move over and work on it in game time while
# the player goes on (delegieren). A move of the role Leitung stays with the player. Fixed rules: ZUWEISEN_MIN minutes
# to hand it over, the move's minutes times FACH_FAKTOR (its subject) or FREMD_FAKTOR, tired colleagues (MUEDE_LANGSAM)
# times MUEDE_FAKTOR; when it is done its effects apply (without its minutes, the budget went at the start).
FAECHER = {"netz": ("Netz", "Network"), "windows": ("Windows", "Windows"), "storage": ("Storage", "Storage"),
           "forensik": ("Forensik", "Forensics"), "rz": ("Rechenzentrum", "Data centre"),
           "kommunikation": ("Kommunikation", "Communication")}
ZUWEISEN_MIN = 2
FACH_FAKTOR, FREMD_FAKTOR = 0.7, 1.5
MUEDE_LANGSAM, MUEDE_FAKTOR, MUEDE_MAX = 70, 1.3, 100
MUEDE_FACH, MUEDE_FREMD, MUEDE_RUHE = 15, 25, 4    # tiredness after a task (own subject, other), less per move idle
ZUWEISEN_LABEL = ("Aufgabe ans Team geben", "Hand a task to the team")
# Laufbahn: the rank from the profile's results; it sets the team's size and the emergency budget
# (id, name, games won, a game with grade A needed, colleagues, budget factor)
RAENGE = (("junior", ("Junior-Admin", "Junior admin"), 0, False, 3, 1.0),
          ("admin", ("Admin", "Admin"), 2, False, 4, 1.0),
          ("itleiter", ("IT-Leiter", "IT manager"), 5, False, 5, 1.1),
          ("ciso", ("CISO", "CISO"), 10, True, 6, 1.2))
RANG_IDS = tuple(r[0] for r in RAENGE)


def fach(a):
    """The subject of a move: kommunikation for that role, None for Leitung (not to hand over)."""
    r = a.get("rolle", "technik")
    return None if r == "leitung" else "kommunikation" if r == "kommunikation" else a.get("fach")


def rang_of(gewonnen, bestnote):
    """The highest rank these results reach (fixed thresholds in RAENGE)."""
    return [r for r in RAENGE if gewonnen >= r[2] and (bestnote or not r[3])][-1]


def laufbahn(d):
    """For the page: the rank now, the next one and what it takes (numbers from the profile's stats)."""
    won = d["stats"].get("gewonnen", 0)
    best = "bestnote" in d["erfolge"]
    r = rang_of(won, best)
    i = RANG_IDS.index(r[0])
    nxt = RAENGE[i + 1] if i + 1 < len(RAENGE) else None
    return {"rang": r[0], "name": list(r[1]), "gewonnen": won, "team": r[4], "budget": r[5],
            "naechster": {"rang": nxt[0], "name": list(nxt[1]), "gewonnen": nxt[2], "note_a": nxt[3], "team": nxt[4]} if nxt else None,
            "raenge": [{"rang": x[0], "name": list(x[1]), "gewonnen": x[2], "note_a": x[3], "team": x[4], "budget": x[5]} for x in RAENGE]}


def _kollegen(seed, n):
    pool = _DATA.get("kollegen", [])
    pick = sorted(_rng(seed, "kollegen").sample(range(len(pool)), min(n, len(pool))))
    return [{"id": pool[i]["id"], "name": pool[i]["name"], "faecher": list(pool[i]["faecher"]), "muede": 0, "auftrag": None,
             "erledigt": 0} for i in pick]


def dauer(st, a, k):
    """Game minutes a colleague needs for the move a (fixed rule)."""
    f = FACH_FAKTOR if fach(a) in k["faecher"] else FREMD_FAKTOR
    if k["muede"] >= MUEDE_LANGSAM:
        f *= MUEDE_FAKTOR
    return max(1, -(-round(a.get("zeit", 1) * f * 10) // 10))

_day = DayCounter(zuege=0, spiele=0, erzaehlt=0, verworfen=0, konsole=0, delegiert=0, heraus=0, kampagnen=0)   # Zustand → Live, numbers only
_locks = {}
_locks_lock = threading.Lock()


# ---------------------------------------------------------------- the scenarios
def _load_data():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    return d


_DATA = _load_data()
SZENARIEN = {s["id"]: s for s in _DATA["szenarien"]}
KAMPAGNEN = {k["id"]: k for k in _DATA.get("kampagnen", [])}


def _pair(x):
    return isinstance(x, list) and len(x) == 2 and all(isinstance(v, str) and v.strip() for v in x)


COND_KEYS = {"flags", "ohne", "irgendein", "var", "status", "zug_ab", "min_ab", "alt", "vertrauen_unter", "stress_ueber", "moral_unter"}
EFF_KEYS = {"zeit", "stress", "vertrauen", "moral", "kosten", "budget", "setzt", "details", "flags", "weg", "text", "je", "wenn",
            "erholung"}
ACT_KEYS = EFF_KEYS | {"id", "label", "einmal", "max", "rolle", "fach"}
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
        if a.get("rolle", "technik") not in ROLLEN:
            bad.append(f"allgemein {a.get('id')}: rolle")
    for i, x in enumerate(d.get("lehren_allgemein", [])):
        _check_lehre(x, None, f"lehre allgemein {i}", bad, cond)
    ks = d.get("kollegen", [])
    if len(ks) < max(r[4] for r in RAENGE) or len({k.get("id") for k in ks}) != len(ks):
        bad.append("kollegen: too few or ids twice")
    for k in ks:
        if not k.get("name") or not k.get("faecher") or any(f not in FAECHER for f in k["faecher"]):
            bad.append(f"kollegen {k.get('id')}")
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
            if a.get("rolle", "technik") not in ROLLEN:
                bad.append(f"{sid} {a.get('id')}: rolle")
            if a.get("rolle", "technik") == "technik" and a.get("fach") not in FAECHER or a.get("fach") == "kommunikation" \
                    or "fach" in a and a.get("rolle", "technik") != "technik":
                bad.append(f"{sid} {a.get('id')}: fach")
        for t in sz.get("ticks", []) + sz.get("neben", []):
            eff(t, sz, f"{sid} {t.get('id')}", TICK_KEYS)
            if not isinstance(t.get("chance"), int) or not 0 < t["chance"] <= 100:
                bad.append(f"{sid} {t.get('id')}: chance")
        for g in sz.get("ziel", []):
            cond(g, sz, f"{sid} ziel")
        lids = [x.get("id") for x in sz.get("lehren", []) + d.get("lehren_allgemein", [])]
        if len(lids) != len(set(lids)):
            bad.append(f"{sid}: lehren ids twice")
        for x in sz.get("lehren", []):
            _check_lehre(x, sz, f"{sid} lehre {x.get('id')}", bad, cond, set(acts))
        if not sz.get("ziel"):
            bad.append(f"{sid}: no goal")
        # the console of the scenario (Paket 2): wrong moves are effects, output lines have conditions
        for i, e in enumerate(krisenkonsole._DATA["szenarien"].get(sid, {}).get("befehle", [])):
            if e.get("falsch"):
                eff(e["falsch"], sz, f"{sid} konsole {i}", EFF_KEYS)
            for x in e.get("ausgabe", []):
                if isinstance(x, list):
                    cond(x[1], sz, f"{sid} konsole {i}")
        for f in krisenkonsole._DATA["szenarien"].get(sid, {}).get("dateien", []):
            for x in f["zeilen"]:
                if isinstance(x, list):
                    cond(x[1], sz, f"{sid} datei {f['pfad']}")
    known = {x["id"] for x in d["szenarien"]}
    for k in d.get("kampagnen", []):
        where = f"kampagne {k.get('id')}"
        if set(k) != {"id", "titel", "kurz", "kapitel"} or not _pair(k.get("titel")) or not _pair(k.get("kurz")):
            bad.append(f"{where}: keys id, titel, kurz, kapitel")
            continue
        if not KAMPAGNE_KAPITEL[0] <= len(k["kapitel"]) <= KAMPAGNE_KAPITEL[1]:
            bad.append(f"{where}: {KAMPAGNE_KAPITEL[0]} to {KAMPAGNE_KAPITEL[1]} chapters")
        days = [c.get("tag") for c in k["kapitel"]]
        if any(not isinstance(x, int) or x < 1 for x in days) or days != sorted(set(days)):
            bad.append(f"{where}: tag rises from 1")
        for c in k["kapitel"]:
            if set(c) != {"szenario", "tag", "text"} or c.get("szenario") not in known or not _pair(c.get("text")):
                bad.append(f"{where}: chapter {c}")
    if len({k.get("id") for k in d.get("kampagnen", [])}) != len(d.get("kampagnen", [])):
        bad.append("kampagnen: ids twice")
    if d is _DATA:
        bad += krisenkonsole.check_data(SZENARIEN, d.get("allgemein", []))
    return bad


LEHR_KEYS = {"genutzt", "fehlt", "vor", "ohne_vor", "ende"}


def _check_lehre(x, sz, where, bad, cond, acts=None):
    w = x.get("wenn") or {}
    if not _pair(x.get("text")) or not isinstance(x.get("bezug"), str) or not x["bezug"].strip() or not isinstance(w, dict) \
            or not isinstance(x.get("gut", False), bool) or not x.get("id"):
        bad.append(f"{where}: text, bezug, gut, id")
        return
    if any(e not in ENDEN for e in w.get("ende", [])):
        bad.append(f"{where}: ende")
    for k in ("vor", "ohne_vor"):
        if k in w and len(w[k]) != 2:
            bad.append(f"{where}: {k} takes two moves")
    known = acts if acts is not None else {a["id"] for a in _DATA.get("allgemein", [])}
    for k in ("genutzt", "fehlt", "vor", "ohne_vor"):
        if any(a not in known for a in w.get(k, [])):
            bad.append(f"{where}: {k} names an unknown move")
    cond({k: v for k, v in w.items() if k not in LEHR_KEYS}, sz, where)


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
    if e.get("erholung"):
        for k in st.get("kollegen") or ():
            k["muede"] = max(0, k["muede"] - e["erholung"])
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


def uhr_ticken(st, now):
    """„Uhr läuft“: the real seconds since the last request become game minutes (UHR_S each, at most UHR_LUECKE
    seconds per request, so a closed page hardly loses time); they wait in uhr.offen and the next move takes them
    along (its inspector shows „davon_uhr“). When they use up the time left, the clock is a move of its own and the
    game ends by time. Returns the facts of that move or None. now comes from the caller, the rule is fixed."""
    u = st.get("uhr")
    if not u or st.get("ende"):
        return None
    gap = max(0.0, min(now - u["t"], UHR_LUECKE))
    u["t"] = now
    if u["pause"]:
        return None
    sec = u["rest"] + gap
    n = int(sec // UHR_S)
    u["rest"], u["offen"] = round(sec - n * UHR_S, 3), u["offen"] + n
    if u["offen"] >= st["m"]["zeit"]:
        return move(st, None, a={"id": "uhr", "label": list(UHR_LABEL)}, via="uhr")
    return None


def uhr_pause(st, on, now):
    """Pause or go on (only on UHR_PAUSE levels); the seconds up to now still count. False if not allowed."""
    u = st.get("uhr")
    if not u or st.get("ende") or st["stufe"] not in UHR_PAUSE or u["pause"] == on:
        return False
    uhr_ticken(st, now)
    u["pause"] = on
    u["pausen"] += 1 if on else 0
    return True


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
        out.append({"id": a["id"], "label": a["label"], "kosten": cost, "frei": free, "rolle": a.get("rolle", "technik"),
                    "fach": fach(a),
                    "warum": [] if free else ["Das Notfall-Budget reicht nicht.", "The emergency budget is not enough."]})
    return out


def new_game(szenario, stufe, seed=None, lang="de", now=None, modus="knoepfe", uhr=False, rang="junior", lernen=False,
             mutatoren=(), heraus=None, erbe=(), kampagne=None):
    """A fresh game: variants drawn from the seed, the start effects applied. modus „konsole“: moves only by typing;
    uhr: the clock runs in real time (uhr_ticken); rang (Laufbahn): the team's size and the budget factor, the
    colleagues drawn from the seed; lernen (Paket 5): the page shows a hint before every move, no achievements;
    mutatoren (Paket 6): extra rules for more points; heraus: the key of a challenge this game is; erbe and
    kampagne (Paket 9): what the chapter before left behind, the campaign and chapter this game is."""
    if szenario not in SZENARIEN or stufe not in STUFEN or modus not in MODI or rang not in RANG_IDS \
            or any(x not in MUT_IDS for x in mutatoren) or len(set(mutatoren)) != len(mutatoren) \
            or any(x not in ERBE_IDS for x in erbe) or len(set(erbe)) != len(erbe):
        raise ValueError("szenario, stufe, modus, rang, mutatoren")
    r = RAENGE[RANG_IDS.index(rang)]
    sz = SZENARIEN[szenario]
    s = STUFEN[stufe]
    seed = secrets.randbelow(SEED_MAX + 1) if seed is None else int(seed)
    now = time.time() if now is None else now
    var = {k: vals[_rng(seed, "var", k).randrange(len(vals))][0] for k, vals in sorted(sz.get("varianten", {}).items())}
    budget = round(sz["budget"] * s["budget"] * r[5])
    st = {"v": 1, "id": secrets.token_hex(8), "szenario": szenario, "stufe": stufe, "seed": seed, "var": var,
          "lang": "en" if lang == "en" else "de", "start": int(now), "zug": 0, "max_stress": START["stress"],
          "m": {"zeit": s["zeit"], "zeit_start": s["zeit"], "stress": START["stress"], "vertrauen": START["vertrauen"],
                "moral": START["moral"], "kosten": 0, "budget": budget, "budget_start": budget},
          "assets": {x["id"]: {"status": "Online", "details": list(x["details"])} for x in sz["assets"]},
          "flags": {}, "flag_min": {}, "uses": {}, "done": [], "chronik": [], "trace": [], "ende": None,
          "modus": modus, "knoepfe": 0, "konsole": krisenkonsole.fresh(szenario),
          "uhr": {"t": now, "rest": 0.0, "offen": 0, "pause": False, "pausen": 0} if uhr else None,
          "rang": rang, "kollegen": _kollegen(seed, r[4]), "delegiert": 0, "lernen": bool(lernen), "folge": [],
          "kurve": [], "mutatoren": sorted(mutatoren), "heraus": heraus, "erbe": [x for x in ERBE_IDS if x in erbe],
          "kampagne": kampagne}
    _mutieren(st)
    _erben(st)
    rec = _rec()
    for e in sz.get("start", []):
        if holds(e.get("wenn"), st):
            _apply(st, e, rec)
    _clamp(st)
    st["chronik"].append({"zug": 0, "min": 0, "art": "start", "text": _text(sz["start_text"], st)})
    st["trace"].append({"zug": 0, "steps": [
        _step("eingabe", ("Neues Spiel", "New game"), {"szenario": szenario, "stufe": stufe, "seed": seed, "modus": modus,
                                                     "uhr": bool(uhr), "rang": rang, "lernen": bool(lernen),
                                                     "mutatoren": sorted(mutatoren), "herausforderung": heraus,
                                                     "erbe": st["erbe"], "kampagne": kampagne,
                                                     "kollegen": [k["id"] for k in st["kollegen"]]}),
        _step("zufall", ("Varianten aus dem Seed", "Variants from the seed"), {"varianten": var}),
        _step("regel", ("Startlage", "Starting situation"), {"systeme": rec["assets"], "werte": rec["delta"]})]})
    return st


# Herausforderungen (Paket 6): every profile of this Spark gets the same game on one day (one mutator) or in one week
# (two), drawn from the date in Europe/Berlin; the board lists each profile's first try, by name only when the
# profile wants it (BOARD_ZEIGEN), else anonymous, or not at all. Mutators are extra rules; a game won with them earns
# their points. Fixed rules, never the model.
MUTATOREN = (("sparkurs", ("Sparkurs", "Austerity"), ("Halbes Notfall-Budget.", "Half the emergency budget."), 5),
             ("eile", ("Eile", "Hurry"), ("Ein Fünftel weniger Zeit.", "A fifth less time."), 5),
             ("presse", ("Presse im Nacken", "Press on your heels"), ("Das Vertrauen startet 20 Punkte tiefer.",
                                                                      "Trust starts 20 points lower."), 4),
             ("muede", ("Nach der Nachtschicht", "After the night shift"), ("Das Team startet zu 40 % müde, die Moral 15 Punkte tiefer.",
                                                                           "The team starts 40 % tired, morale 15 points lower."), 4))
MUT_IDS = tuple(x[0] for x in MUTATOREN)
MUT_BONUS = {x[0]: x[3] for x in MUTATOREN}
HERAUS = {"tag": (1, ("Tages-Herausforderung", "Daily challenge")), "woche": (2, ("Wochen-Herausforderung", "Weekly challenge"))}
HERAUS_RANG = "admin"            # the same team and budget for everyone, whatever the career
HERAUS_ZONE = zoneinfo.ZoneInfo("Europe/Berlin")
BOARD_ZEIGEN = ("anonym", "name", "aus")
BOARD_MAX = 20
BOARD_CACHE = 20


def _mutieren(st):
    m = st["m"]
    for x in st.get("mutatoren") or ():
        if x == "sparkurs":
            m["budget"] = m["budget_start"] = m["budget"] // 2
        elif x == "eile":
            m["zeit"] = m["zeit_start"] = m["zeit"] * 4 // 5
        elif x == "presse":
            m["vertrauen"] -= 20
        elif x == "muede":
            m["moral"] -= 15
            for k in st["kollegen"]:
                k["muede"] = 40


def herausforderung(art, now=None):
    """The challenge of the day or week: its key, scenario, seed and mutators, the same on every computer."""
    t = datetime.datetime.fromtimestamp(time.time() if now is None else now, HERAUS_ZONE)
    key = f"tag:{t:%Y-%m-%d}" if art == "tag" else "woche:%d-W%02d" % t.isocalendar()[:2]
    r = random.Random("krisenspiel:" + key)
    sid = sorted(SZENARIEN)[r.randrange(len(SZENARIEN))]
    return {"art": art, "key": key, "name": list(HERAUS[art][1]), "szenario": sid, "stufe": "normal",
            "seed": r.randrange(SEED_MAX + 1), "mutatoren": sorted(r.sample(MUT_IDS, HERAUS[art][0]))}


# Kampagnen (Paket 9): chains of chapters over several game days (data: kampagnen); what a finished chapter leaves
# behind (ERBE) is fixed code from its end and values, never the model; it changes the start of the next chapter.
# A campaign can wait between chapters as long as it likes; a chapter replaced by another game counts as given up.
KAMPAGNE_KAPITEL = (2, 5)
KAMPAGNEN_MAX = 10       # finished campaigns kept per profile
ERBE = (("audit", ("Audit", "Audit"), ("Ein Audit prüft den letzten Fall: ein Fünftel weniger Notfall-Budget.",
                                       "An audit checks the last case: a fifth less emergency budget."),
         ("Kapitel nicht gewonnen oder Note D bis F.", "Chapter not won or grade D to F.")),
        ("versicherung", ("Versicherung zahlt", "Insurance pays"), ("Die Cyber-Versicherung erstattet: ein Fünftel mehr Notfall-Budget.",
                                                                  "The cyber insurance pays: a fifth more emergency budget."),
         ("Gewonnen ohne Datenverlust.", "Won without data loss.")),
        ("erschoepft", ("Erschöpftes Team", "Exhausted team"), ("Die Moral startet 15 Punkte tiefer, das Team ist zu 30 % müde.",
                                                               "Morale starts 15 points lower, the team is 30 % tired."),
         ("Moral am Ende unter 40 %.", "Morale below 40 % at the end.")),
        ("ruf", ("Ruf beschädigt", "Reputation damaged"), ("Das Vertrauen startet 15 Punkte tiefer.", "Trust starts 15 points lower."),
         ("Vertrauen am Ende unter 40 %.", "Trust below 40 % at the end.")),
        ("eingespielt", ("Eingespielt", "Well-rehearsed"), ("Der Stress startet 10 Punkte tiefer, die Moral 5 Punkte höher.",
                                                          "Stress starts 10 points lower, morale 5 points higher."),
         ("Gewonnen mit Note A oder B.", "Won with grade A or B.")))
ERBE_IDS = tuple(x[0] for x in ERBE)


def erbe_aus(st):
    """What a finished chapter leaves to the next one, by fixed rules in the order of ERBE."""
    e, m = st["ende"], st["m"]
    won = e["art"] == "gewonnen"
    rules = {"audit": not won or e["note"] in ("D", "E", "F"), "versicherung": won and "datenverlust" not in st["flags"],
             "erschoepft": m["moral"] < 40, "ruf": m["vertrauen"] < 40, "eingespielt": won and e["note"] in ("A", "B")}
    return [k for k in ERBE_IDS if rules[k]]


def _erben(st):
    m = st["m"]
    for x in st.get("erbe") or ():
        if x == "audit":
            m["budget"] = m["budget_start"] = m["budget"] * 4 // 5
        elif x == "versicherung":
            m["budget"] = m["budget_start"] = m["budget"] * 6 // 5
        elif x == "erschoepft":
            m["moral"] -= 15
            for k in st["kollegen"]:
                k["muede"] = max(k.get("muede", 0), 30)
        elif x == "ruf":
            m["vertrauen"] -= 15
        elif x == "eingespielt":
            m["stress"] -= 10
            m["moral"] += 5


def kampagne_start(d, kid, stufe, seed=None, now=None):
    """A new campaign for the profile (replaces a running one); its chapters' seeds come from its own seed."""
    if kid not in KAMPAGNEN or stufe not in STUFEN:
        raise ValueError("kampagne, stufe")
    seed = secrets.randbelow(SEED_MAX + 1) if seed is None else int(seed)
    d["kampagne"] = {"id": kid, "lauf": secrets.token_hex(6), "stufe": stufe, "seed": seed, "kapitel": 0, "erbe": [],
                     "ergebnisse": [], "t": int(time.time() if now is None else now)}
    return d["kampagne"]


def kapitel_spiel(d, lang="de", modus="knoepfe", uhr=False, now=None):
    """The game of the campaign's next chapter, with what the chapter before left behind."""
    k = d["kampagne"]
    kd = KAMPAGNEN[k["id"]]
    c = kd["kapitel"][k["kapitel"]]
    seed = _rng(k["seed"], "kapitel", k["kapitel"]).randrange(SEED_MAX + 1)
    return new_game(c["szenario"], k["stufe"], seed, lang, now=now, modus=modus, uhr=uhr, rang=laufbahn(d)["rang"],
                    erbe=k["erbe"], kampagne={"id": k["id"], "lauf": k["lauf"], "kapitel": k["kapitel"], "n": len(kd["kapitel"])})


def _kapitel_fertig(d, st, now):
    """A finished chapter into its campaign: the result, the heritage for the next one, at the end the total."""
    k, c = d.get("kampagne"), st.get("kampagne")
    if not k or not c or c.get("lauf") != k["lauf"] or c.get("kapitel") != k["kapitel"]:
        return
    erbe = erbe_aus(st)
    k["ergebnisse"].append({"szenario": st["szenario"], "ende": st["ende"]["art"], "note": st["ende"]["note"],
                            "punkte": st["ende"]["punkte"], "erbe": erbe})
    k["kapitel"] += 1
    k["erbe"] = erbe
    n = len(KAMPAGNEN[k["id"]]["kapitel"])
    if k["kapitel"] < n:
        print(f"spiel: kampagne | kapitel {k['kapitel']} von {n} | {len(erbe)} folgen", flush=True)
        return
    p = round(sum(x["punkte"] for x in k["ergebnisse"]) / n)
    note = next(x for floor, x in NOTEN if p >= floor)
    d["kampagnen"] = ([{"id": k["id"], "stufe": k["stufe"], "seed": k["seed"], "punkte": p, "note": note, "t": int(now),
                        "ergebnisse": k["ergebnisse"]}] + d.get("kampagnen", []))[:KAMPAGNEN_MAX]
    d["kampagne"] = None
    print(f"spiel: kampagne | ende | note {d['kampagnen'][0]['note']}", flush=True)


def _step(art, titel, daten, ms=0.0):
    return {"art": art, "titel": list(titel), "daten": daten, "ms": round(ms, 1)}


def move(st, aktion, now=None, a=None, via="knopf", rolle=None, wer=None, an=None):
    """One move by the panel's fixed rules. Returns the facts of the move (fixed texts) for the narrator.
    Raises ValueError when the move is not offered right now. a: a move of the console that is no action of the
    scenario (a wrong command, reading for LESEN_MAX minutes) with its own fixed effects; via: knopf or konsole.
    rolle and wer: a player of a game together (krisenteam) takes only the moves of its role; wer stands in the
    chronicle ({"rolle", "name"}). an: a colleague's id (Paket 3): the move is handed over and done in game time."""
    if st.get("ende"):
        raise ValueError("over")
    t0 = time.perf_counter()
    sz = SZENARIEN[st["szenario"]]
    s = STUFEN[st["stufe"]]
    if a is None:
        offer = {x["id"]: x for x in available(st)}
        if aktion not in offer or not offer[aktion]["frei"]:
            raise ValueError("not offered")
        a = next(x for x in _all_actions(sz) if x["id"] == aktion)
        if rolle and not darf(rolle, a):
            raise ValueError("not this role")
    task = None
    if an is not None:
        k = next((x for x in st.get("kollegen") or () if x["id"] == an), None)
        if aktion is None or not k or k["auftrag"] or k["muede"] >= MUEDE_MAX or not fach(a):
            raise ValueError("not to hand over")
        n = dauer(st, a, k)
        task = (a, k, n)
        a = {"id": "zuweisen", "label": list(ZUWEISEN_LABEL), "zeit": ZUWEISEN_MIN, "budget": a.get("budget", 0),
             "text": [f"{k['name']} übernimmt: {a['label'][0]} (fertig in etwa {n} Minuten).",
                      f"{k['name']} takes over: {a['label'][1]} (done in about {n} minutes)."]}
    aktion = a["id"]
    pre_assets = {k: v["status"] for k, v in st["assets"].items()}
    m = st["m"]
    st["zug"] += 1
    st["uses"][aktion] = st["uses"].get(aktion, 0) + 1
    if via == "knopf":
        st["knoepfe"] = st.get("knoepfe", 0) + 1
    k = st.setdefault("konsole", krisenkonsole.fresh(st["szenario"]))
    reading, k["min"] = k.get("min", 0), 0
    clock = 0
    if st.get("uhr"):
        clock, st["uhr"]["offen"] = st["uhr"]["offen"], 0
    steps = [_step("eingabe", ("Zug", "Move"), dict({"zug": st["zug"], "aktion": aktion, "label": a["label"], "weg": via},
                                                    **({"rolle": rolle} if rolle else {})))]
    if aktion in {x["id"] for x in _all_actions(SZENARIEN[st["szenario"]])}:
        st.setdefault("folge", []).append(aktion)
    if task:
        ta, tk, n = task
        st.setdefault("folge", []).append(ta["id"])
        st["uses"][ta["id"]] = st["uses"].get(ta["id"], 0) + 1
        tk["auftrag"] = {"aktion": ta["id"], "label": list(ta["label"]), "start": minutes_gone(st), "fertig": minutes_gone(st) + n}
        st["delegiert"] = st.get("delegiert", 0) + 1
        steps[0]["daten"].update(an=tk["id"], aufgabe=ta["id"], dauer=n, fach=fach(ta), passt=fach(ta) in tk["faecher"],
                                 muede=tk["muede"])
    rec = _rec()
    _effect(st, a, rec)
    rec["minuten"] += reading + clock
    minutes = rec["minuten"]
    steps.append(_step("regel", ("Folgen des Zugs (feste Regel)", "Effects of the move (fixed rule)"),
                       {"minuten": minutes, "davon_lesen": reading, "davon_uhr": clock, "werte": rec["delta"], "systeme": rec["assets"], "flags": rec["flags"],
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
    _team_tick(st, rec, texts, steps)
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
        st["chronik"].append(dict({"zug": st["zug"], "min": gone, "art": x["art"], "text": x["text"]},
                                  **({"wer": wer} if wer and x["art"] == "zug" else {})))
    end = _end(st)
    if end:
        finish(st, end)
        st["chronik"].append({"zug": st["zug"], "min": gone, "art": "ende", "text": list(ENDEN[end])})
        steps.append(_step("ende", ("Spielende", "Game over"), {"ende": end, "note": st["ende"]["note"], "punkte": st["ende"]["punkte"]}))
    else:
        steps.append(_step("antwort", ("Angebotene Züge", "Moves offered"), {"anzahl": len(available(st))}))
    steps[1]["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    st["chronik"] = st["chronik"][-CHRONIK_MAX:]
    st.setdefault("kurve", []).append([st["zug"], gone, m["kosten"]])     # the ghost of a later game (Paket 5)
    st["trace"].append({"zug": st["zug"], "steps": steps})
    st["trace"] = st["trace"][-TRACE_MAX:]
    return {"label": a["label"], "texte": texts, "systeme": rec["assets"], "minute": gone}


def _team_tick(st, rec, texts, steps):
    """The colleagues after the minutes of a move: a task whose minute has come applies its move's effects (without
    its minutes and budget), tiredness goes up by the subject, idle colleagues rest a little."""
    gone = minutes_gone(st)
    sz = SZENARIEN[st["szenario"]]
    for k in st.get("kollegen") or ():
        t = k["auftrag"]
        if not t:
            k["muede"] = max(0, k["muede"] - MUEDE_RUHE)
            continue
        if t["fertig"] > gone:
            continue
        a = next((x for x in _all_actions(sz) if x["id"] == t["aktion"]), None)
        k["auftrag"] = None
        if not a:
            continue
        r2 = _rec()
        _effect(st, {x: v for x, v in a.items() if x not in ("zeit", "budget")}, r2)
        rec["assets"] += r2["assets"]
        own = fach(a) in k["faecher"]
        k["muede"] = min(MUEDE_MAX, k["muede"] + (MUEDE_FACH if own else MUEDE_FREMD))
        k["erledigt"] = k.get("erledigt", 0) + 1
        texts.append({"art": "team", "text": [f"{k['name']} ist fertig: {a['label'][0]}. " + " ".join(x[0] for x in r2["texte"]),
                                              f"{k['name']} is done: {a['label'][1]}. " + " ".join(x[1] for x in r2["texte"])]})
        steps.append(_step("team", ("Aufgabe des Teams fertig (feste Regel)", "Team task done (fixed rule)"),
                           {"kollege": k["id"], "aktion": a["id"], "minute": gone, "werte": r2["delta"], "systeme": r2["assets"],
                            "flags": r2["flags"], "muede": k["muede"]}))


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
        + 15 * max(0.0, 1 - m["kosten"] / ref) + 10 * m["vertrauen"] / 100 + 5 * m["moral"] / 100 - (10 if loss else 0) \
        + (KONSOLE_BONUS if won and st.get("modus") == "konsole" else 0) + (UHR_BONUS if won and st.get("uhr") else 0) \
        + (_mut_bonus(st) if won else 0)
    p = max(0, min(100, round(p)))
    note = next(n for floor, n in NOTEN if p >= floor) if end != "aufgegeben" else "F"
    eur = lambda v: f"{v:,}".replace(",", ".")
    eur_en = lambda v: f"{v:,}"
    why = [list(ENDEN[end]),
           [f"{minutes_gone(st)} Minuten gespielt, {m['zeit']} Minuten Reserve.", f"{minutes_gone(st)} minutes played, {m['zeit']} minutes to spare."],
           [f"Schaden {eur(m['kosten'])} € (Richtwert {eur(round(ref))} €).", f"Damage {eur_en(m['kosten'])} € (benchmark {eur_en(round(ref))} €)."],
           [f"Vertrauen {m['vertrauen']} %, Moral {m['moral']} %.", f"Trust {m['vertrauen']} %, morale {m['moral']} %."],
           ["Datenverlust: ja." if loss else "Kein Datenverlust.", "Data loss: yes." if loss else "No data loss."]]
    if won and st.get("modus") == "konsole":
        why.append([f"Nur Konsole: +{KONSOLE_BONUS} Punkte.", f"Console only: +{KONSOLE_BONUS} points."])
    if won and st.get("uhr"):
        why.append([f"Uhr lief: +{UHR_BONUS} Punkte.", f"Clock running: +{UHR_BONUS} points."])
    if won and _mut_bonus(st):
        why.append([f"Mutatoren: +{_mut_bonus(st)} Punkte.", f"Mutators: +{_mut_bonus(st)} points."])
    return p, note, why


def _mut_bonus(st):
    return sum(MUT_BONUS.get(x, 0) for x in st.get("mutatoren") or ())


def finish(st, end):
    p, note, why = bewerten(st, end)
    st["ende"] = {"art": end, "punkte": p, "note": note, "gruende": why, "minuten": minutes_gone(st)}
    st["ende"]["lehren"] = nachbesprechung(st)


def _lehre_gilt(w, st):
    f = st.get("folge") or []
    first = {}
    for i, a in enumerate(f):
        first.setdefault(a, i)
    if any(a not in first for a in w.get("genutzt", ())) or any(a in first for a in w.get("fehlt", ())):
        return False
    if "vor" in w and not (w["vor"][0] in first and w["vor"][1] in first and first[w["vor"][0]] < first[w["vor"][1]]):
        return False
    if "ohne_vor" in w and not (w["ohne_vor"][1] in first and first.get(w["ohne_vor"][0], 10 ** 6) > first[w["ohne_vor"][1]]):
        return False
    if "ende" in w and (st.get("ende") or {}).get("art") not in w["ende"]:
        return False
    return holds({k: v for k, v in w.items() if k not in LEHR_KEYS}, st)


def nachbesprechung(st):
    """The debrief (Paket 5): the fixed lessons of the scenario and the general ones whose condition holds for the
    moves taken (st["folge"]) and the end; what went well first. Never the model."""
    sz = SZENARIEN[st["szenario"]]
    out = [{"id": x["id"], "text": list(x["text"]), "bezug": x["bezug"], "gut": bool(x.get("gut"))}
           for x in list(sz.get("lehren", [])) + list(_DATA.get("lehren_allgemein", [])) if _lehre_gilt(x.get("wenn") or {}, st)]
    return sorted(out, key=lambda x: not x["gut"])


def tipp(st):
    """Lernmodus: the offered move that brings the game closest to its goal one move ahead (fixed rule: goal parts,
    then flags, then less damage), or None. Tried on a copy, the game itself does not change."""
    if st.get("ende"):
        return None
    sz = SZENARIEN[st["szenario"]]
    best = None
    for a in available(st):
        if not a["frei"]:
            continue
        s2 = copy.deepcopy(st)
        s2["trace"], s2["chronik"] = [], []
        move(s2, a["id"])
        won = (s2.get("ende") or {}).get("art") == "gewonnen"
        lost = bool(s2.get("ende")) and not won
        goal = sum(int(holds(g, s2)) for g in sz["ziel"])
        score = (won, not lost, goal, len(s2["flags"]) - len(st["flags"]), -s2["m"]["kosten"])
        if best is None or score > best[0]:
            best = (score, a)
    if not best:
        return None
    a = best[1]
    return {"aktion": a["id"], "label": a["label"],
            "warum": ["Dieser Zug bringt dich dem Ziel am nächsten (das Panel rechnet einen Zug voraus).",
                      "This move brings you closest to the goal (the panel calculates one move ahead)."]}


def erfolge_neu(st, prof_data):
    """The achievements this finished game earns that the profile does not have yet (fixed rules)."""
    have = prof_data.get("erfolge", {})
    e = st["ende"]
    if e["art"] == "aufgegeben" or st.get("lernen"):   # given up (Dominik 2026-10-22) or with hints: no achievement
        return []
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
             "allrounder": all(won_by.get(k) for k in SZENARIEN), "bestnote": e["note"] == "A",
             "ohne_knopf": won and st.get("knoepfe", 0) == 0,
             "gegen_uhr": won and bool(st.get("uhr")) and st["uhr"]["pausen"] == 0,
             "delegiert": won and st.get("delegiert", 0) >= 4,
             "ciso": rang_of(prof_data.get("stats", {}).get("gewonnen", 0) + won,
                             "bestnote" in have or e["note"] == "A")[0] == RANG_IDS[-1],
             "herausforderung": won and bool(st.get("heraus")) and st["heraus"] not in prof_data.get("heraus", {}),
             "mutig": won and len(st.get("mutatoren") or ()) >= 2,
             "durchgehalten": bool(st.get("kampagne")) and st["kampagne"]["kapitel"] == st["kampagne"]["n"] - 1}
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
            "stats": d.get("stats") if isinstance(d.get("stats"), dict) else {},
            "heraus": {k: v for k, v in (d.get("heraus") or {}).items() if isinstance(v, dict)},
            "bestenliste": d.get("bestenliste") if d.get("bestenliste") in BOARD_ZEIGEN else BOARD_ZEIGEN[0],
            "kampagne": d["kampagne"] if isinstance(d.get("kampagne"), dict) and d["kampagne"].get("id") in KAMPAGNEN else None,
            "kampagnen": [x for x in d.get("kampagnen") or [] if isinstance(x, dict) and x.get("id") in KAMPAGNEN][:KAMPAGNEN_MAX]}


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
    learn = bool(st.get("lernen"))                 # with hints: counted as played, never for the career or the best
    won = st["ende"]["art"] == "gewonnen" and not learn
    if won:
        stats["gewonnen"] = stats.get("gewonnen", 0) + 1
        stats.setdefault("gewonnen_je", {})[st["szenario"]] = stats.get("gewonnen_je", {}).get(st["szenario"], 0) + 1
    if not learn:
        best = stats.setdefault("beste", {})
        best[st["szenario"]] = max(best.get(st["szenario"], 0), st["ende"]["punkte"])
    je = stats.setdefault("je", {}).setdefault(st["szenario"], {"gespielt": 0, "gewonnen": 0, "summe": 0, "minuten": 0})
    je["gespielt"] += 1
    je["gewonnen"] += int(won)
    je["summe"] += st["ende"]["punkte"]
    je["minuten"] += st["ende"]["minuten"]
    noten = stats.setdefault("noten", {})
    noten[st["ende"]["note"]] = noten.get(st["ende"]["note"], 0) + 1
    st["ende"]["erfolge"] = new
    key = st.get("heraus")
    if key and not learn and key not in d.setdefault("heraus", {}):      # the first try of a challenge counts
        d["heraus"][key] = {"punkte": st["ende"]["punkte"], "note": st["ende"]["note"], "minuten": st["ende"]["minuten"],
                            "ende": st["ende"]["art"], "t": int(now)}
        for k in sorted(d["heraus"], key=lambda k: d["heraus"][k]["t"])[:-VERLAUF_MAX]:
            del d["heraus"][k]
        _board["d"] = None
    d["verlauf"] = ([{"id": st["id"], "szenario": st["szenario"], "stufe": st["stufe"], "seed": st["seed"],
                      "ende": st["ende"]["art"], "note": st["ende"]["note"], "punkte": st["ende"]["punkte"],
                      "zuege": st["zug"], "minuten": st["ende"]["minuten"], "t": int(now), "erfolge": new, "lernen": learn,
                      "heraus": key, "mutatoren": st.get("mutatoren") or [], "kampagne": (st.get("kampagne") or {}).get("id"),
                      "kurve": [] if learn else st.get("kurve", [])[:MAX_ZUEGE]}]
                    + d["verlauf"])[:VERLAUF_MAX]
    print(f"spiel: ende | {st['ende']['art']} | note {st['ende']['note']} | {st['zug']} zuege | {len(new)} erfolge", flush=True)
    _kapitel_fertig(d, st, now)


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


# ---------------------------------------------------------------- the console (Paket 2)
FALSCH_LABEL = ("Falscher Befehl an der Konsole", "Wrong command at the console")
LESEN_LABEL = ("Analyse an der Konsole", "Analysis at the console")


def konsole_zeile(st, zeile, lang="de"):
    """One typed line (krisenkonsole.run cuts and answers it, nothing runs): a move like its button, a wrong move
    with its own fixed effects, a move of the simulation (a service stopped or started, a reboot: krisenlinux) or
    reading that costs a minute (LESEN_MAX minutes are a move of their own).
    Returns (facts of a move or None, the console's result)."""
    k = st.setdefault("konsole", krisenkonsole.fresh(st["szenario"]))
    host = k["host"]
    names = {a["id"]: a["name"] for a in SZENARIEN[st["szenario"]]["assets"]}
    res = krisenkonsole.run(st, zeile, {a["id"]: a for a in available(st)}, holds, lang, names)
    if res["art"] == "leer":
        return None, res
    typed = zeile.strip()[:krisenkonsole.MAX_ZEILE]
    lines = [] if res["clear"] else [{"k": "in", "s": typed, "h": host}] + [{"k": x, "s": t} for x, t in res["out"]]
    if res["clear"]:
        k["zeilen"] = []
    if res["art"] != "abgelehnt":
        k["verlauf"] = (k["verlauf"] + [typed])[-krisenkonsole.VERLAUF:]
    facts = None
    if res["zug"]:
        facts = move(st, res["zug"], via="konsole", an=res.get("an"))
    elif res["falsch"]:
        facts = move(st, None, a=dict(res["falsch"], id="konsole_falsch", label=list(FALSCH_LABEL)), via="konsole")
    elif res["wirkung"]:
        facts = move(st, None, a=dict(res["wirkung"]), via="konsole")      # a stopped service, a reboot (krisenlinux)
    elif res["art"] == "lesen":
        k["min"] += 1
        if k["min"] >= krisenkonsole.LESEN_MAX:
            facts = move(st, None, a={"id": "konsole_lesen", "label": list(LESEN_LABEL)}, via="konsole")
    if facts:
        li = 1 if lang == "en" else 0
        lines += [{"k": "zug", "s": "# " + x["text"][li]} for x in facts["texte"]]
        lines.append({"k": "zug", "s": "# " + ("Minute " if li == 0 else "minute ") + str(minutes_gone(st))})
        if st.get("ende"):
            lines.append({"k": "zug", "s": "# " + ENDEN[st["ende"]["art"]][li]})
    k["zeilen"] = (k["zeilen"] + lines)[-krisenkonsole.PUFFER:]
    return facts, res


# ---------------------------------------------------------------- views
def view(d, uid=None):
    st = d["spiel"]
    out = {"on": True, "erzaehler": bool(uid and features.allowed("krisenerzaehler", uid)),
           "team": bool(uid and features.allowed("krisenteam", uid)), "rollen": {k: list(v) for k, v in ROLLEN.items()},
           "szenarien": [{"id": s["id"], "titel": s["titel"], "kurz": s["kurz"], "systeme": len(s["assets"])}
                         for s in _DATA["szenarien"]],
           "stufen": [{"id": k, "name": list(v["name"]), "zeit": v["zeit"]} for k, v in STUFEN.items()],
           "erfolge": [{"id": k, "name": list(n), "text": list(t), "t": d["erfolge"].get(k, 0)} for k, n, t in ERFOLGE],
           "verlauf": [dict({k: v for k, v in x.items() if k != "kurve"}, titel=SZENARIEN[x["szenario"]]["titel"])
                       for x in d["verlauf"] if x.get("szenario") in SZENARIEN],
           "laufbahn": laufbahn(d), "faecher": {k: list(v) for k, v in FAECHER.items()},
           "mutatoren": [{"id": k, "name": list(n), "text": list(t), "bonus": b} for k, n, t, b in MUTATOREN],
           "herausforderungen": heraus_view(d, uid), "bestenliste": d.get("bestenliste", BOARD_ZEIGEN[0]),
           "kampagnen": [{"id": k["id"], "titel": k["titel"], "kurz": k["kurz"],
                          "kapitel": [{"szenario": c["szenario"], "titel": SZENARIEN[c["szenario"]]["titel"], "tag": c["tag"]}
                                      for c in k["kapitel"]]} for k in _DATA.get("kampagnen", [])],
           "erbe": [{"id": k, "name": list(n), "text": list(t), "wann": list(w)} for k, n, t, w in ERBE],
           "kampagne": kampagne_view(d.get("kampagne")),
           "kampagnen_verlauf": [dict(x, titel=KAMPAGNEN[x["id"]]["titel"]) for x in d.get("kampagnen") or []],
           "stats": {"gespielt": d["stats"].get("gespielt", 0), "gewonnen": d["stats"].get("gewonnen", 0),
                     "beste": d["stats"].get("beste", {}), "je": d["stats"].get("je", {}), "noten": d["stats"].get("noten", {})},
           "spiel": None}
    if st:
        sz = SZENARIEN[st["szenario"]]
        k = st.get("konsole") or krisenkonsole.fresh(st["szenario"])
        out["spiel"] = {"id": st["id"], "szenario": st["szenario"], "titel": sz["titel"], "stufe": st["stufe"],
                        "seed": st["seed"], "zug": st["zug"], "m": st["m"], "min": minutes_gone(st),
                        "assets": [{"id": x["id"], "name": x["name"], "typ": x["typ"], "status": st["assets"][x["id"]]["status"],
                                    "details": st["assets"][x["id"]]["details"]} for x in sz["assets"]],
                        "chronik": st["chronik"], "trace": st["trace"], "ende": st["ende"],
                        "modus": st.get("modus", "knoepfe"), "uhr": _uhr_view(st),
                        "aktionen": [] if st["ende"] or st.get("modus") == "konsole" else available(st),
                        "rang": st.get("rang", "junior"), "delegiert": st.get("delegiert", 0),
                        "mutatoren": st.get("mutatoren") or [], "heraus": st.get("heraus"),
                        "erbe": st.get("erbe") or [], "kampagne": st.get("kampagne"),
                        "lernen": bool(st.get("lernen")), "tipp": tipp(st) if st.get("lernen") and not st["ende"] else None,
                        "geist": geist(d, st),
                        "kollegen": [dict(x, rest=max(0, x["auftrag"]["fertig"] - minutes_gone(st)) if x["auftrag"] else 0)
                                     for x in st.get("kollegen") or ()],
                        "konsole": dict(krisenkonsole.hilfe_daten(st["szenario"]), host=k["host"], zeilen=k["zeilen"],
                                        verlauf=k["verlauf"], lesen=k["min"], lesen_max=krisenkonsole.LESEN_MAX,
                                        **krisenkonsole.tab_daten(st, holds, st.get("lang", "de")))}
    return out


def kampagne_view(k):
    """The running campaign: its chapters with results so far, the next chapter's text and what it inherits."""
    if not k:
        return None
    kd = KAMPAGNEN[k["id"]]
    nxt = kd["kapitel"][k["kapitel"]] if k["kapitel"] < len(kd["kapitel"]) else None
    return {"id": k["id"], "titel": kd["titel"], "stufe": k["stufe"], "seed": k["seed"], "kapitel": k["kapitel"],
            "n": len(kd["kapitel"]), "erbe": k["erbe"], "ergebnisse": k["ergebnisse"], "lauf": k["lauf"],
            "naechstes": {"szenario": nxt["szenario"], "titel": SZENARIEN[nxt["szenario"]]["titel"], "tag": nxt["tag"],
                          "text": nxt["text"]} if nxt else None}


def geist(d, st):
    """The ghost (Paket 5): the profile's best finished run of the same scenario and level (not with hints), and
    where it stood after as many moves: minute and damage. None without one."""
    runs = [v for v in d["verlauf"] if v.get("szenario") == st["szenario"] and v.get("stufe") == st["stufe"]
            and v.get("kurve") and not v.get("lernen") and v.get("id") != st["id"]]
    if not runs:
        return None
    b = max(runs, key=lambda v: (v["punkte"], -v["minuten"]))
    k = b["kurve"]
    bei = k[min(st["zug"], len(k)) - 1] if st["zug"] else None
    return {"note": b["note"], "punkte": b["punkte"], "zuege": b["zuege"], "minuten": b["minuten"], "seed": b["seed"],
            "bei": {"zug": bei[0], "min": bei[1], "kosten": bei[2]} if bei else None}


def _uhr_view(st):
    """The clock for the page: minutes waiting for the next move, seconds since the last request (the page counts
    on from there) and the rule's numbers, so the time on top runs down between two requests."""
    u = st.get("uhr")
    if not u:
        return None
    return {"offen": u["offen"], "rest": u["rest"], "seit": round(max(0.0, min(time.time() - u["t"], UHR_LUECKE)), 1),
            "pause": u["pause"], "pausen": u["pausen"], "pause_ok": st["stufe"] in UHR_PAUSE, "s": UHR_S,
            "poll": UHR_POLL, "luecke": UHR_LUECKE}


# ---------------------------------------------------------------- endpoints
_board = {"at": 0.0, "d": None}


def board(key, uid):
    """The board of a challenge: every allowed profile's first try, best first; a name only where that profile chose
    „name“, profiles that chose „aus“ only for themselves. Read from the profiles' own files (cached BOARD_CACHE s)."""
    if _board["d"] is None or time.time() - _board["at"] >= BOARD_CACHE:
        idx = {}
        for u in profiles.user_ids():
            if os.path.exists(_file(u)) and features.allowed("krisenspiel", u):
                d = load(u)
                if d["heraus"]:
                    idx[u] = (d["bestenliste"], d["heraus"])
        _board.update(at=time.time(), d=idx)
    rows = []
    for u, (zeigen, her) in _board["d"].items():
        r = her.get(key)
        if not r or zeigen == "aus" and u != uid:
            continue
        p = profiles.by_id(u) or {}
        rows.append({"ich": u == uid, "name": p.get("name") if zeigen == "name" or u == uid else None,
                     "punkte": r["punkte"], "note": r["note"], "minuten": r["minuten"], "ende": r["ende"]})
    rows.sort(key=lambda x: (-x["punkte"], x["minuten"]))
    return rows[:BOARD_MAX]


def heraus_view(d, uid, now=None):
    out = []
    for art in HERAUS:
        h = herausforderung(art, now)
        out.append(dict(h, titel=SZENARIEN[h["szenario"]]["titel"], ich=d.get("heraus", {}).get(h["key"]), liste=board(h["key"], uid)))
    return out


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


_anleitung = []


@router.get("/api/profile/krisenspiel/anleitung", dependencies=[Depends(assistant)])
def anleitung(request: Request, prof=Depends(own_profile)):
    """The guide (tab „Anleitung“): fixed texts, every number, command, scenario and achievement from the code."""
    _need(prof["id"])
    guard.limit(request, "spiel", prof["id"])
    if not _anleitung:
        _anleitung.append(krisenanleitung.build(sys.modules[__name__]))
    return {"abschnitte": _anleitung[0]}


@router.post("/api/profile/krisenspiel/neu", dependencies=[Depends(assistant)])
async def neu(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, BODY)
    sid, stufe, seed, modus = b.get("szenario"), b.get("stufe", "normal"), b.get("seed"), b.get("modus", "knoepfe")
    uhr, lernen, muts, her = b.get("uhr", False), b.get("lernen", False), b.get("mutatoren", []), b.get("herausforderung")
    kamp = b.get("kampagne")
    if kamp is not None:
        if kamp != "weiter" and kamp not in KAMPAGNEN or her is not None or lernen or muts or sid is not None \
                or modus not in MODI or not isinstance(uhr, bool) or stufe not in STUFEN or seed is not None and (
                not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= SEED_MAX):
            print("spiel: neu abgelehnt | eingabe", flush=True)
            raise HTTPException(400, "kampagne")
        return await _kapitel_neu(request, prof, b, kamp, stufe, seed, modus, uhr)
    if her is not None:
        if her not in HERAUS:
            print("spiel: neu abgelehnt | eingabe", flush=True)
            raise HTTPException(400, "herausforderung")
        h = herausforderung(her)
        sid, stufe, seed, muts, lernen = h["szenario"], h["stufe"], h["seed"], h["mutatoren"], False
    if not isinstance(muts, list) or any(x not in MUT_IDS for x in muts) or len(set(muts)) != len(muts):
        print("spiel: neu abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "mutatoren")
    if sid == ZUFALL and (seed is None or isinstance(seed, int) and not isinstance(seed, bool)):
        n = len(SZENARIEN)                      # Dominik 2026-10-22: „Überraschung, was passiert“; with a seed repeatable
        sid = sorted(SZENARIEN)[secrets.randbelow(n) if seed is None else random.Random(f"zufall:{seed}").randrange(n)]
    if sid not in SZENARIEN or stufe not in STUFEN or modus not in MODI or not isinstance(uhr, bool) \
            or not isinstance(lernen, bool) or seed is not None and (
            not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= SEED_MAX):
        print("spiel: neu abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "szenario, stufe, seed, modus, uhr, lernen")

    def go():
        with _lock(uid):
            d = load(uid)
            _ersetzen(d)
            d["spiel"] = new_game(sid, stufe, seed, _lang(b), modus=modus, uhr=uhr, lernen=lernen, mutatoren=muts,
                                  rang=HERAUS_RANG if her else laufbahn(d)["rang"], heraus=h["key"] if her else None)
            save(uid, d)
            return d
    d = await asyncio.to_thread(go)
    _day.bump("spiele")
    if her:
        _day.bump("heraus")
    print(f"spiel: neu | {sid} | {stufe} | {modus}{' | uhr' if uhr else ''}{' | lernen' if lernen else ''}"
          f"{' | ' + her if her else ''}{f' | {len(muts)} mutatoren' if muts else ''} | {profiles.log_name(prof)}", flush=True)
    return view(d, uid)


def _ersetzen(d):
    """Before a new game: a running one is replaced; a running chapter of the campaign counts as given up."""
    st = d["spiel"]
    if not st or st.get("ende"):
        return
    print("spiel: altes spiel ersetzt | nicht beendet", flush=True)
    k, c = d.get("kampagne"), st.get("kampagne")
    if k and c and c.get("lauf") == k["lauf"] and c.get("kapitel") == k["kapitel"]:
        finish(st, "aufgegeben")
        _book(d, time.time())


async def _kapitel_neu(request, prof, b, kamp, stufe, seed, modus, uhr):
    """POST …/neu with kampagne: an id starts that campaign at chapter 1, „weiter“ the next chapter of the running one;
    an open chapter game is simply shown again (played on later, the game is saved)."""
    uid = prof["id"]

    def go():
        with _lock(uid):
            d = load(uid)
            if kamp == "weiter":
                k = d["kampagne"]
                if not k:
                    return d, "keine"
                st = d["spiel"]
                c = (st or {}).get("kampagne") or {}
                if st and not st.get("ende") and c.get("lauf") == k["lauf"] and c.get("kapitel") == k["kapitel"]:
                    return d, "offen"
            else:
                if d["kampagne"]:
                    print("spiel: kampagne | ersetzt", flush=True)
                kampagne_start(d, kamp, stufe, seed)
            _ersetzen(d)
            if not d["kampagne"]:              # the replaced game was the last chapter of the running campaign
                return d, "keine"
            d["spiel"] = kapitel_spiel(d, _lang(b), modus, uhr)
            save(uid, d)
            return d, "neu"
    d, how = await asyncio.to_thread(go)
    if how == "keine":
        print("spiel: kampagne abgelehnt | keine kampagne", flush=True)
        raise HTTPException(404, "no campaign")
    if how == "offen":
        print("spiel: kampagne | weiter | offen", flush=True)
        return view(d, uid)
    k = d["kampagne"]
    _day.bump("spiele")
    if k["kapitel"] == 0:
        _day.bump("kampagnen")
    print(f"spiel: kampagne | {'start' if k['kapitel'] == 0 else 'weiter'} | {k['id']} | kapitel {k['kapitel'] + 1} | "
          f"{k['stufe']} | {modus}{' | uhr' if uhr else ''} | {profiles.log_name(prof)}", flush=True)
    return view(d, uid)


@router.delete("/api/profile/krisenspiel/kampagne", dependencies=[Depends(assistant)])
def kampagne_beenden(request: Request, prof=Depends(browser_profile)):
    """Ends the running campaign without a result; a running chapter game stays as a free game."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    with _lock(uid):
        d = load(uid)
        if not d["kampagne"]:
            print("spiel: kampagne abgelehnt | keine kampagne", flush=True)
            raise HTTPException(404, "no campaign")
        d["kampagne"] = None
        save(uid, d)
    print("spiel: kampagne | beendet", flush=True)
    return view(d, uid)


async def _narrated(uid, d, facts, lang):
    """After a move: the narrator's words for its chronicle line (own switch), checked, kept only for the same turn."""
    st = d["spiel"]
    if not features.allowed("krisenerzaehler", uid) or not facts or not facts["texte"]:
        return d
    text, why, ms = await narrate(st, facts, lang)
    _day.bump("erzaehlt" if text else "verworfen")
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
                         {"ok": bool(text), "zeichen": len(text), "verworfen": why, "werte_uebernommen": 0}, ms)
            s2["trace"][-1]["steps"].insert(-1, step)
            save(uid, d2)
            return d2
    return await asyncio.to_thread(keep)


@router.post("/api/profile/krisenspiel/zug", dependencies=[Depends(assistant)])
async def zug(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, BODY)
    aktion, turn, lang, an = b.get("aktion"), b.get("zug"), _lang(b), b.get("an")
    if not isinstance(aktion, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", aktion) or not isinstance(turn, int) \
            or an is not None and (not isinstance(an, str) or not re.fullmatch(r"[a-z0-9_]{1,20}", an)):
        print("spiel: zug abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "aktion, zug, an")

    def go():
        with _lock(uid):
            d = load(uid)
            st = d["spiel"]
            if not st or st.get("ende"):
                return None, None, 404
            if st["zug"] != turn:
                return None, None, 409
            if st.get("modus") == "konsole":
                return None, None, 423
            facts = uhr_ticken(st, time.time())
            if st.get("ende"):                  # the clock ran out before this move
                _book(d, time.time())
                save(uid, d)
                print("spiel: uhr | abgelaufen", flush=True)
                return d, facts, 200
            try:
                facts = move(st, aktion, an=an)
            except ValueError:
                return None, None, 422
            if st.get("ende"):
                _book(d, time.time())
            save(uid, d)
            return d, facts, 200
    t0 = time.perf_counter()
    d, facts, code = await asyncio.to_thread(go)
    if code != 200:
        why = {404: "kein spiel", 409: "alter zug", 422: "nicht angeboten", 423: "nur konsole"}[code]
        print(f"spiel: zug abgelehnt | {why}", flush=True)
        raise HTTPException(422 if code == 423 else code, why)
    _day.bump("zuege")
    if an:
        _day.bump("delegiert")
    print(f"spiel: zug | {'delegiert' if an else 'ok'} | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)
    return view(await _narrated(uid, d, facts, lang), uid)


@router.post("/api/profile/krisenspiel/konsole", dependencies=[Depends(assistant)])
async def konsole(request: Request, prof=Depends(browser_profile)):
    """One line at the simulated console: never run, cut by fixed rules (krisenkonsole)."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, BODY)
    zeile, turn, lang = b.get("zeile"), b.get("zug"), _lang(b)
    if not isinstance(zeile, str) or len(zeile) > 2 * krisenkonsole.MAX_ZEILE or not isinstance(turn, int) \
            or isinstance(turn, bool):
        print("spiel: konsole abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "zeile, zug")

    def go():
        with _lock(uid):
            d = load(uid)
            st = d["spiel"]
            if not st or st.get("ende"):
                return None, None, "", 404
            if st["zug"] != turn:
                return None, None, "", 409
            facts = uhr_ticken(st, time.time())
            if st.get("ende"):                  # the clock ran out before this line
                _book(d, time.time())
                save(uid, d)
                print("spiel: uhr | abgelaufen", flush=True)
                return d, facts, "uhr", 200
            facts, res = konsole_zeile(st, zeile, lang)
            if st.get("ende"):
                _book(d, time.time())
            save(uid, d)
            return d, facts, res["art"], 200
    t0 = time.perf_counter()
    d, facts, art, code = await asyncio.to_thread(go)
    if code != 200:
        why = {404: "kein spiel", 409: "alter zug"}[code]
        print(f"spiel: konsole abgelehnt | {why}", flush=True)
        raise HTTPException(code, why)
    _day.bump("konsole")
    if facts:
        _day.bump("zuege")
    print(f"spiel: konsole | {art} | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)
    return view(await _narrated(uid, d, facts, lang), uid)


@router.post("/api/profile/krisenspiel/datei", dependencies=[Depends(assistant)])
async def datei(request: Request, prof=Depends(browser_profile)):
    """nano, vi and vim at the console (Dominik 2026-10-22): {aktion: speichern | schliessen, text?, zug}. The text goes
    into the game's simulated file system like > does (krisenlinux.save), never onto the Spark's disk; no move, no
    minute."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, krisenlinux.EDIT_BYTES + 1000)
    aktion, text, turn, lang = b.get("aktion"), b.get("text", ""), b.get("zug"), _lang(b)
    if aktion not in ("speichern", "schliessen") or not isinstance(text, str) or len(text) > krisenlinux.EDIT_BYTES \
            or not isinstance(turn, int) or isinstance(turn, bool):
        print("spiel: datei abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "aktion, text, zug")

    def go():
        with _lock(uid):
            d = load(uid)
            st = d["spiel"]
            if not st or st.get("ende"):
                return None, "kein spiel"
            if st["zug"] != turn:
                return None, "alter zug"
            c = krisenkonsole.ctx(st, holds, lang)
            if not krisenlinux.editor_view(c):
                return None, "kein editor"
            k = st["konsole"]
            e = k["editor"]
            if aktion == "speichern":
                err = krisenlinux.save(c, text)
                n = len([x for x in text.split("\n")]) - (1 if text.endswith("\n") else 0)
                msg = ("err", "[ " + err + " ]") if err else \
                    ("out", f'"{e["pfad"]}" {n}L written' if e["art"] != "nano" else f"[ Wrote {n} lines ]")
                k["zeilen"] = (k["zeilen"] + [{"k": msg[0], "s": msg[1]}])[-krisenkonsole.PUFFER:]
                why = "fehler" if err else "gespeichert"
            else:
                k.pop("editor", None)
                why = "zu"
            save(uid, d)
            return d, why
    d, why = await asyncio.to_thread(go)
    if not d:
        print(f"spiel: datei abgelehnt | {why}", flush=True)
        raise HTTPException(404 if why in ("kein spiel", "kein editor") else 409, why)
    print(f"spiel: datei | {why}", flush=True)
    return view(d, uid)


@router.post("/api/profile/krisenspiel/uhr", dependencies=[Depends(assistant)])
async def uhr(request: Request, prof=Depends(browser_profile)):
    """„Uhr läuft“: the open page ticks every UHR_POLL seconds while it is visible (tick), pause and weiter on the
    levels UHR_PAUSE. Only the fixed rule of uhr_ticken turns real seconds into game minutes."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, BODY)
    aktion, lang = b.get("aktion"), _lang(b)
    if aktion not in ("tick", "pause", "weiter"):
        print("spiel: uhr abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "aktion")

    def go():
        with _lock(uid):
            d = load(uid)
            st = d["spiel"]
            if not st or st.get("ende") or not st.get("uhr"):
                return None, None, 404
            now = time.time()
            if aktion == "tick":
                facts = uhr_ticken(st, now)
            elif not uhr_pause(st, aktion == "pause", now):
                return None, None, 422
            else:
                facts = None
            if st.get("ende"):
                _book(d, now)
            save(uid, d)
            return d, facts, 200
    d, facts, code = await asyncio.to_thread(go)
    if code != 200:
        why = {404: "keine uhr", 422: "keine pause"}[code]
        print(f"spiel: uhr abgelehnt | {why}", flush=True)
        raise HTTPException(code, why)
    if d["spiel"].get("ende"):
        print("spiel: uhr | abgelaufen", flush=True)
    elif aktion != "tick":
        print(f"spiel: uhr | {aktion}", flush=True)
    return view(await _narrated(uid, d, facts, lang), uid)


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


@router.post("/api/profile/krisenspiel/bestenliste", dependencies=[Depends(assistant)])
async def bestenliste(request: Request, prof=Depends(browser_profile)):
    """How the profile stands on the boards of the challenges: anonym (default), name or aus."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    b = await json_body(request, BODY)
    z = b.get("zeigen")
    if z not in BOARD_ZEIGEN:
        print("spiel: bestenliste abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "zeigen")

    def go():
        with _lock(uid):
            d = load(uid)
            d["bestenliste"] = z
            save(uid, d)
            return d
    d = await asyncio.to_thread(go)
    _board["d"] = None
    print(f"spiel: bestenliste | {z}", flush=True)
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
        running = profs = clocks = camps = 0
        only = sum(1 for uid in profiles.user_ids() if profiles.nur_spiel(uid))   # Spielprofile „Nur Krisenspiel“ (nurspiel.py)
        for uid in profiles.user_ids():
            if not os.path.exists(_file(uid)):
                continue
            profs += 1
            d = load(uid)
            st = d["spiel"]
            camps += bool(d["kampagne"])
            running += bool(st and not st.get("ende"))
            clocks += bool(st and not st.get("ende") and st.get("uhr"))
        _live.update(at=time.time(), d={"laufend": running, "profile": profs, "uhr": clocks, "kampagnen_laufend": camps, "nur_spiel": only})
    t = _day.today()
    return dict(_live["d"], on=True, zuege=t["zuege"], spiele=t["spiele"], erzaehlt=t["erzaehlt"], verworfen=t["verworfen"],
                konsole=t["konsole"], delegiert=t["delegiert"], heraus=t["heraus"], kampagnen=t["kampagnen"])


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
    _board["d"] = None
    print("spiel: daten geloescht | eigene daten", flush=True)


features.OWN["krisenspiel"] = (_own_count, _own_clear)
