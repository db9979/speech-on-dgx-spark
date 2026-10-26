"""KI-Dungeon-Master: Umgebung nutzen (D&D ideas round 2, idea 3, Dominik 2026-10-26 „1-9 umsetzten reihenfolge
überlasse ich dir.“; the props of the tabletop's theatre of the mind, only as an idea, own code).

Where a fight goes on, the room or place holds 2 to 3 props (dungeon_karte.requisiten, the map thread's: ideen.requisiten
with a fixed wirkung). The panel keeps them in the fight (prepare, rd["kampf"]["requisiten"]) and shows them as chips
at the table. A hero's action that names one (named: its name or the last word of it, also by voice and in the car)
is that hero's action this turn (checks): one check of the panel, d20 + the value of its kind (WERTE) against SCHWER
(the children's table SCHWER_KINDER), with the seat's own die at the real table. On a success the prop works by the
fixed rule of its kind (roll), in this turn already, and is gone from there (used):
  schaden_gruppe  every foe up takes 1d6 (SCHADEN_W), its resistances count, as a hit with the prop
  umwerfen        one foe (the one the action names, else the one with the most life) lies on the ground (liegend)
  deckung         +DECKUNG to the hero's armour class against the foes this turn
  vorteil         the group's attacks this turn with advantage
  fluchtweg       the foes cannot reach the hero this turn
A failed check leaves the prop where it is. The model only tells; it gets the props as data (facts) and the check as a
receipt like any other.

Off by default: the admin's switch dungeonumgebung (features.py, chat.dungeon_umgebung) for the round's host.
State: rd["kampf"]["requisiten"] [ids]; only on run_turn's copy rd["kampf"]["_umgebung"] {wirkung: [pids]}.
Journal: fixed words and numbers („dungeon: umgebung | …“), Live only counts.
"""
import random
import re

import features
from common import DayCounter

KEY = "dungeonumgebung"
SCHWER = 12
SCHWER_KINDER = 10
SCHADEN_W = 6
DECKUNG = 2
WERTE = {"schaden_gruppe": "geschick", "umwerfen": "staerke", "deckung": "geschick", "vorteil": "weisheit", "fluchtweg": "geschick"}
WIRKT = {"schaden_gruppe": ("trifft alle Gegner", "hits every foe"), "umwerfen": ("wirft einen Gegner um", "knocks a foe down"),
         "deckung": ("+2 Rüstung diesen Zug", "+2 armour this turn"), "vorteil": ("Angriffe der Gruppe mit Vorteil", "the group's attacks with advantage"),
         "fluchtweg": ("außer Reichweite der Gegner", "out of the foes' reach")}
LIEGEND = "liegend"

_day = DayCounter(proben=0, geschafft=0, daneben=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def _rows(r):
    return {x["id"]: x for x in (r.get("ideen") or {}).get("requisiten") or [] if x.get("wirkung") in WERTE}


def here(r, rd):
    """The props of the fight still there, as rows of ideen.requisiten."""
    k = rd.get("kampf") if on(rd) else None
    rows = _rows(r)
    return [rows[x] for x in (k or {}).get("requisiten") or [] if x in rows]


def prepare(r, rd, rng=None):
    """In dungeon.apply: the props where the fight goes on, rolled once there and kept by the map."""
    import dungeon_karte
    k = rd.get("kampf")
    if k is None:
        return
    if not on(rd):
        k.pop("requisiten", None)
        return
    k["requisiten"] = dungeon_karte.requisiten(r, rd, rng)


def named(row, text):
    """Whether an action names this prop: its whole name in one of the languages, or the last word of it (≥4 letters,
    a German plural or case ending allowed)."""
    import dungeon_kampf
    low = str(text or "").lower()
    for n in row["name"]:
        n = n.lower()
        if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", low):
            return True
        last = n.split()[-1]
        if len(last) >= 4 and any(set(dungeon_kampf._stems(w)) & set(dungeon_kampf._stems(last)) for w in re.findall(r"\w+", low)):
            return True
    return False


def checks(dm, r, rd, proben):
    """Before the dice (run_turn, on its copy): a hero whose action names a prop of the fight makes that its action this
    turn, one check of the panel instead of the checks the model asked for it; each prop once a turn."""
    import dungeon_kampf
    rows = here(r, rd)
    if not rows:
        return proben
    sg = SCHWER_KINDER if dm.kids(r, rd) else SCHWER
    li = 1 if rd.get("lang") == "en" else 0
    taken, out = set(), []
    for pid, p in dm.seated(rd):
        h = p["held"]
        if dm.zustand(h) or dungeon_kampf.blocked(r, h):
            continue
        t = ((rd.get("offen") or {}).get(pid) or {}).get("text", "")
        row = next((x for x in rows if x["id"] not in taken and named(x, t)), None)
        if row:
            taken.add(row["id"])
            out.append({"pid": pid, "wert": WERTE[row["wirkung"]], "schwer": sg, "umgebung": row["id"],
                        "wofuer": f"{row['name'][li]} ({WIRKT[row['wirkung']][li]})"})
    if out:
        mine = {x["pid"] for x in out}
        print(f"dungeon: umgebung | probe | {len(out)}", flush=True)
        return [p for p in proben if p.get("pid") not in mine] + out
    return proben


def roll(dm, r, rd, proben, rng=None, hand=None):
    """The props' checks out of proben, rolled by the panel (the seat's own die first, dungeon_echt.Hand); a success
    works at once on this copy of the round: damage as hits, a foe on the ground, cover, advantage, out of reach.
    Returns (the other checks, the props' rolls as log entries like dungeon.roll's, the props' hits)."""
    import dungeon_kampf as kampf
    rng = rng or random
    mine = [p for p in proben if p.get("umgebung")]
    if not mine or not rd.get("kampf"):
        return [p for p in proben if not p.get("umgebung")], [], []
    rows, li = _rows(r), 1 if rd.get("lang") == "en" else 0
    has_liegend = any(z["id"] == LIEGEND for z in r.get("zustaende") or [])
    wuerfe, hits = [], []
    eff = rd["kampf"].setdefault("_umgebung", {})
    _day.bump("proben", len(mine))
    for p in mine:
        row = rows[p["umgebung"]]
        h = rd["plaetze"][p["pid"]]["held"]
        vt = kampf._state_vt(r, h, "", "probe")
        ws = [hand.d20(p["pid"], rng) if hand else rng.randint(1, 20) for _ in range(2 if vt else 1)]
        w = max(ws) if vt == "vorteil" else min(ws)
        w, gl = kampf.lucky(dm, r, h, w, rng)
        bonus = dm.total(r, h, p["wert"])
        ok = w == 20 or (w != 1 and w + bonus >= p["schwer"])
        x = {"pid": p["pid"], "name": h["name"], "wert": p["wert"], "w": w, "bonus": bonus, "gesamt": w + bonus, "schwer": p["schwer"],
             "ok": ok, "vt": vt, "ws": ws, "wofuer": p["wofuer"], "umgebung": row["id"], "wirkung": row["wirkung"],
             **({"glueck": True} if gl else {}), **({"echt": True} if hand and hand.used(p["pid"]) else {})}
        wuerfe.append(x)
        if not ok:
            continue
        if row["wirkung"] == "schaden_gruppe":
            for g in kampf.up(rd):
                if g["leben"] <= 0:
                    continue
                n, wirkt = kampf.against(g, "wucht", rng.randint(1, SCHADEN_W))
                g["leben"] -= n
                hits.append({"pid": p["pid"], "name": h["name"], "ziel": g["k"], "gegner": g["name"], "mit": row["name"][li], "wert": p["wert"],
                             "w": w, "ws": ws, "vt": vt, "bonus": bonus, "gesamt": w + bonus, "rk": p["schwer"], "treffer": True, "krit": False,
                             "schaden": n, "faellt": g["leben"] <= 0, "art": "wucht", "wirkt": wirkt, "eig": [], "umgebung": row["id"]})
        elif row["wirkung"] == "umwerfen":
            t = ((rd.get("offen") or {}).get(p["pid"]) or {}).get("text", "")
            gs = [g for g in kampf.up(rd) if g["leben"] > 0]
            g = kampf._named(rd, t, text=True) or (max(gs, key=lambda g: g["leben"]) if gs else None)
            if g and has_liegend:
                x["ziel"] = g["k"]
                kampf.st(rd, g, {"id": LIEGEND, "zuege": 1})   # this turn already: the heroes' attacks and its own blows
        else:
            eff.setdefault(row["wirkung"], []).append(p["pid"])
    return [p for p in proben if not p.get("umgebung")], wuerfe, hits


def edge(rd):
    """The group's attacks this turn with advantage (a prop of kind vorteil worked)."""
    return bool(((rd.get("kampf") or {}).get("_umgebung") or {}).get("vorteil"))


def cover(rd, pid):
    """The armour class the hero's cover gives against the foes this turn."""
    return DECKUNG if pid in ((rd.get("kampf") or {}).get("_umgebung") or {}).get("deckung", ()) else 0


def away(rd, pid):
    """The hero out of the foes' reach this turn (a way out)."""
    return pid in ((rd.get("kampf") or {}).get("_umgebung") or {}).get("fluchtweg", ())


def used(dm, r, rd, w):
    """In dungeon.apply, for a prop's roll: a success takes the prop away from there and puts a foe on the ground for
    its turn; a line for every result."""
    import dungeon_karte
    import dungeon_kampf as kampf
    if not w["ok"]:
        _day.bump("daneben")
        print(f"dungeon: umgebung | {w['wirkung']} | daneben", flush=True)
        return
    dungeon_karte.requisit_benutzt(rd, w["umgebung"])
    k = rd.get("kampf")
    if k:
        k["requisiten"] = [x for x in k.get("requisiten") or [] if x != w["umgebung"]]
        g = next((g for g in kampf.up(rd) if g["k"] == w.get("ziel")), None)
        if g:
            kampf.st(rd, g, {"id": LIEGEND, "zuege": 1})
    _day.bump("geschafft")
    print(f"dungeon: umgebung | {w['wirkung']} | ok", flush=True)


def facts(r, rd, li):
    """The props of the fight, only as data for the narrator to describe."""
    rows = here(r, rd)
    return {"umgebung": [f"{x['name'][li]} ({WIRKT[x['wirkung']][li]})" for x in rows]} if rows else {}


AUFGABE = {
    "de": (" Stehen in den Fakten umgebung, beschreibe diese Dinge im Kampf mit; die Spieler können sie in ihrer Aktion "
           "nutzen, ob es gelingt und was es bewirkt, würfelt und rechnet das Panel, erzähle es nach dem Beleg."),
    "en": (" When the facts hold umgebung, show these things in the fight; the players may use them in their action, the "
           "panel rolls and works out whether it succeeds and what it does, tell it by the receipt."),
}


def task(rd, lang):
    return AUFGABE[lang] if on(rd) and (rd.get("kampf") or {}).get("requisiten") else ""


def view(r, rd):
    """The chips of the fight's props for the table: id, name, sign and what it does."""
    li = 1 if rd.get("lang") == "en" else 0
    return [{"id": x["id"], "name": x["name"][li], "zeichen": x.get("zeichen", ""), "wirkt": WIRKT[x["wirkung"]][li]} for x in here(r, rd)]


def for_live():
    """Numbers only: props tried, worked and missed today."""
    t = _day.counts()
    return {k: t[k] for k in ("proben", "geschafft", "daneben")}
