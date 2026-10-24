"""KI-Dungeon-Master: the wait between turns made pleasant (Stufe 5j, plan dungeon-master/plan.md „5j“,
Dominik 2026-10-23 „1-7 aber viel mehr fest sätze als viarianten das es nicht zu schnell zu eintönig wird“).

While the Dungeon Master narrates, the table shows where it is: the steps lesen → würfeln → erzählen (→ nachbessern)
with one fixed sentence each, the panel's dice as soon as they are rolled (before the narration), a few lore cards
of the world and one hint „Während du wartest“. Every text comes from dungeon_warten.json (shipped, all fine from
age 8), never from the model or a player; the panel picks them and keeps the last ones of a round so they do not come
back soon. Two things for the players among themselves: „X schreibt …“ (kept in memory only, a few seconds) and the
table talk, a short chat between the seats of a round that the model never sees (not in facts, not in any prompt).

State in the round (dungeon.py's rounds file):
    rd["warten"]         {"s": step, "satz": key, "karten": [keys], "tipp": key, "w": [dice], "wt": time}  only while rd["dm"]
                         a die has "geworfen" once its seat threw it (throw); the number is the panel's all along
    rd["warten_zuletzt"] {"satz": [...], "karte": [...], "tipp": [...]}  the keys shown last in this round
    rd["tisch"]          [{"n", "pid", "name", "text", "t"}]  the table talk, the last TISCH_MAX
"""
import json
import os
import random
import threading
import time

QUELLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dungeon_warten.json")
SCHRITTE = ("lesen", "wuerfeln", "erzaehlen", "nachbessern")
FOLGE = ("lesen", "wuerfeln", "erzaehlen")  # the steps the bar shows; nachbessern stands on erzaehlen's place
ZURUECK = {"satz": 10, "karte": 90, "tipp": 15}   # keys of a round not shown again so soon (a step's own list)
KARTEN_ZUG = 3             # lore cards per wait
SATZ_LEN = (12, 120)       # a progress sentence
KARTE_LEN = (20, 220)      # a lore card's text
TITEL_LEN = 40
TISCH_MAX = 40             # table talk lines kept per round
TISCH_LEN = 200
TIPPT_S = 6                # „X schreibt …“ while the last keystroke is this fresh
WURF_S = 12                # a seat throws its own die (tap or shake); after this the others see it anyway

_data = {}
_tippt = {}                # rid -> {pid: monotonic time of the last keystroke}; never written to disk
_tl = threading.Lock()


def data():
    if not _data:
        with open(QUELLE, encoding="utf-8") as f:
            _data.update(json.load(f))
    return _data


def check(d, welten, dm=None):
    """Mistakes in a set of waiting texts (test and admin view): every step and world, lengths, both languages."""
    err = []
    pair = lambda x, lo, hi: isinstance(x, list) and len(x) == 2 and all(isinstance(s, str) and lo <= len(s) <= hi for s in x)
    for s in SCHRITTE:
        st = (d.get("schritte") or {}).get(s)
        if not isinstance(st, dict) or not st.get("alle"):
            err.append(f"schritte.{s}: alle fehlt")
            continue
        for k, xs in st.items():
            if k != "alle" and k not in welten:
                err.append(f"schritte.{s}.{k}: keine Welt")
            for i, x in enumerate(xs):
                if not pair(x, *SATZ_LEN):
                    err.append(f"schritte.{s}.{k}[{i}]")
    ks = d.get("karten") or {}
    for w in list(welten) + ["alle"]:
        if not ks.get(w):
            err.append(f"karten.{w}: fehlt")
    for k, xs in ks.items():
        for i, x in enumerate(xs):
            if not (isinstance(x, list) and len(x) == 4 and pair(x[:2], 2, TITEL_LEN) and pair(x[2:], *KARTE_LEN)):
                err.append(f"karten.{k}[{i}]")
    for i, x in enumerate(d.get("tipps") or []):
        if not pair(x, *SATZ_LEN):
            err.append(f"tipps[{i}]")
    if not d.get("tipps"):
        err.append("tipps: fehlt")
    if dm:                                   # the youngest tone's word list holds for every fixed text
        kid = {"ton": min(t["id"] for t in dm.rules()["toene"])}
        for t in texts(d):
            if dm.bad_words(dm.rules(), kid, t.lower()):
                err.append("wortliste: " + t[:40])
    return err


def texts(d):
    for st in (d.get("schritte") or {}).values():
        for xs in st.values():
            for x in xs:
                yield from x
    for xs in (d.get("karten") or {}).values():
        for x in xs:
            yield from x
    for x in d.get("tipps") or []:
        yield from x


def _pool(group, welt):
    return [f"{welt}:{i}" for i in range(len(group.get(welt) or []))] + [f"alle:{i}" for i in range(len(group.get("alle") or []))]


def _pick(rd, kind, pool, rng, n=1, back=""):
    """n keys from the pool, none of the ones shown last in this round while others are left."""
    back = rd.setdefault("warten_zuletzt", {}).setdefault(kind + (":" + back if back else ""), [])
    out = []
    for _ in range(n):
        free = [k for k in pool if k not in back and k not in out]
        if free:
            k = rng.choice(free)
        else:                                # all shown lately: the one shown longest ago
            age = {x: i for i, x in enumerate(back)}
            k = min([x for x in pool if x not in out] or pool, key=lambda x: age.get(x, -1))
        out.append(k)
        back.append(k)
    del back[:-ZURUECK[kind]]
    return out


def _text(group, key):
    w, i = key.rsplit(":", 1)
    xs = group.get(w) or []
    return xs[int(i)] if int(i) < len(xs) else None


def start(rd, rng=None):
    """A new wait (the turn closed or the prologue starts): its first step, the lore cards and the hint."""
    rng = rng or random.Random()
    d, welt = data(), rd.get("welt", "")
    rd["warten"] = {"s": "lesen", "w": [],
                    "satz": _pick(rd, "satz", _pool(d["schritte"]["lesen"], welt), rng, back="lesen")[0],
                    "karten": _pick(rd, "karte", _pool(d["karten"], welt), rng, KARTEN_ZUG),
                    "tipp": _pick(rd, "tipp", [f"alle:{i}" for i in range(len(d["tipps"]))], rng)[0]}


def step(rd, s, wuerfe=None, rng=None):
    """The next step of the wait; with wuerfe the panel's dice, shown before the narration comes."""
    if s not in SCHRITTE or not rd.get("dm"):
        return
    if "warten" not in rd:
        start(rd, rng)
    w = rd["warten"]
    w["s"] = s
    w["satz"] = _pick(rd, "satz", _pool(data()["schritte"][s], rd.get("welt", "")), rng or random.Random(), back=s)[0]
    if wuerfe is not None:
        w["wt"] = time.time()
        w["w"] = [{"pid": x.get("pid", ""), "name": x["name"], "wert": x["wert"], "w": x["w"], "bonus": x.get("bonus", 0), "gesamt": x["gesamt"], "schwer": x["schwer"],
                   "ok": bool(x["ok"]), "vt": x.get("vt", ""), "ws": list(x.get("ws") or [])[:2], "belastet": bool(x.get("belastet")),
                   "werkzeug": x.get("werkzeug", "")} for x in wuerfe]


def throw(rd, pid):
    """The seat throws its own die (Dominik 2026-10-23 „1 und 2“): from now on the others see the number. The number
    itself was rolled by the panel before (dungeon.roll); the tap only shows it. Returns whether there was one."""
    hit = False
    for x in (rd.get("warten") or {}).get("w") or []:
        if x.get("pid") == pid and not x.get("geworfen"):
            x["geworfen"] = hit = True
    return hit


def _die(x, pid, now, wt):
    """One die as a seat sees it: its own always (the page rolls it on the tap), another's once thrown or WURF_S old."""
    ich = x.get("pid") == pid
    offen = ich or x.get("geworfen") or now - (wt or 0) > WURF_S
    out = {"name": x["name"], "wert": x["wert"], "schwer": x["schwer"], "ich": ich, "geworfen": bool(x.get("geworfen")) or not ich and offen,
           "werkzeug": x.get("werkzeug", "")}
    if offen:
        out.update(w=x["w"], bonus=x.get("bonus", x["gesamt"] - x["w"]), gesamt=x["gesamt"], ok=bool(x["ok"]),
                   vt=x.get("vt", ""), ws=x.get("ws") or [], belastet=bool(x.get("belastet")))
    return out


def end(rd):
    rd.pop("warten", None)


def typing(rid, pid):
    """A keystroke in the action field of a seat: „X schreibt …“ for the others for a few seconds."""
    now = time.monotonic()
    with _tl:
        seats = _tippt.setdefault(rid, {})
        seats[pid] = now
        for r_id in [k for k, v in _tippt.items() if all(now - t > TIPPT_S for t in v.values())]:
            _tippt.pop(r_id, None)               # old rounds drop out, the dict stays small


def typing_now(rid, pid):
    now = time.monotonic()
    with _tl:
        return {p for p, t in (_tippt.get(rid) or {}).items() if p != pid and now - t <= TIPPT_S}


def talk(dm, rd, pid, text, now):
    """One line of table talk from a seat; only the players see it, the model never does."""
    if rd["status"] != "laeuft":
        raise LookupError("runde")
    t = dm._clean(text, TISCH_LEN)
    if not t:
        raise ValueError("leer")
    h = rd["plaetze"][pid].get("held")
    if not h:
        raise LookupError("held")
    log = rd.setdefault("tisch", [])
    log.append({"n": (log[-1]["n"] + 1) if log else 1, "pid": pid, "name": h["name"], "text": t, "t": now})
    del log[:-TISCH_MAX]


def view(rd, rid, pid, lang):
    """What the table shows of the wait, the table talk and who is typing."""
    li = 1 if lang == "en" else 0
    d, welt = data(), rd.get("welt", "")
    names = {p: (x.get("held") or {}).get("name", "") for p, x in rd["plaetze"].items()}
    out = {"tisch": [{"n": x["n"], "name": x["name"], "text": x["text"], "ich": x["pid"] == pid, "t": x["t"]} for x in rd.get("tisch") or []],
           "tippt": sorted(names[p] for p in typing_now(rid, pid) if names.get(p) and p not in rd.get("offen", {})),
           "warten": None}
    w = rd.get("warten")
    if rd.get("dm") and w:
        satz = _text(d["schritte"].get(w["s"]) or {}, w["satz"]) if w.get("satz") else None
        karten = [x for x in (_text(d["karten"], k) for k in w.get("karten") or []) if x]
        tipp = _text({"alle": d["tipps"]}, w["tipp"]) if w.get("tipp") else None
        out["warten"] = {"s": w["s"], "wt": w.get("wt") or 0, "folge": list(FOLGE), "satz": satz[li] if satz else "",
                         "karten": [{"titel": x[li], "text": x[2 + li]} for x in karten], "tipp": tipp[li] if tipp else "",
                         "w": [_die(x, pid, time.time(), w.get("wt")) for x in w.get("w") or []], "welt": welt}
    return out
