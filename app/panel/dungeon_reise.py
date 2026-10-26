"""KI-Dungeon-Master: Reise-Etappen (D&D idea 9, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; own code, the tables „reise_rollen“ and „reise_ereignisse“ come from the thread „DnDAppFiles für
den Dungeon-Master“, the stages of a way from the map thread, dungeon_karte.etappen).

When the map moves the group along a way of REISE_MIN or more stages (not inside a vault), the panel makes a journey of
it by fixed rules: every seat with a hero up takes one role of ideen.reise_rollen (scout, hunter, watch … in the
world's words; the roles go round by the turn, so everyone gets each in time) and rolls one d20 check on the role's
value against SCHWER plus the stages. One event of ideen.reise_ereignisse of the landscape follows the outcome: the
first failed role's consequence (ueberrascht, hungrig, verirrt), else „ausgeruht“ on a natural 20, else „ruhig“.
The consequence works by a fixed rule: ueberrascht, every hero's checks of the next turn at a disadvantage; hungrig,
1 life each (never below 1); verirrt, a day more on the road; ausgeruht, 2 life each. The next narration tells the
journey from its facts (reise); the table shows it as a card in the log. rd["reise_tage"] counts the days on the road
(the world's calendar, D&D idea 6).

Off by default: the admin's switch dungeonreise (features.py, chat.dungeon_reise) for the round's host.
Journal: fixed words and numbers („dungeon: reise | …“), Live only counts.
"""
import random

import features
from common import DayCounter

KEY = "dungeonreise"
REISE_MIN = 2              # stages from which a way is a journey
SCHWER = 10                # the roles' difficulty, plus the way's stages
HUNGER = 1                 # life a hungry hero loses (never below 1)
RUHE = 2                   # life a rested hero gets back
FOLGEN = ("ueberrascht", "hungrig", "verirrt")

_day = DayCounter(reisen=0, gelungen=0, misslungen=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def _name(x, welt):
    n = x.get("name") or {}
    return list(n.get(welt) or n.get("alle") or ["", ""])


def journey(dm, r, rd, von, rng=None):
    """The way from the place von to where the map put the group: the roles' checks, the event, its consequence;
    the journey as rd["reise"] for the next narration, or None (off, short way, a vault, no table)."""
    import dungeon_karte
    import dungeon_rast
    rng = rng or random
    k = rd.get("karte") or {}
    i = r.get("ideen") or {}
    rollen = i.get("reise_rollen") or []
    if not on(rd) or not rollen or not isinstance(von, int) or dungeon_karte.vault(rd) or von == k.get("hier") \
            or not 0 <= von < len(k.get("orte") or []):
        return None
    e = dungeon_karte.etappen(k, von, k["hier"])
    if e < REISE_MIN:
        return None
    seats = [(pid, p["held"]) for pid, p in dm.seated(rd) if not dm.zustand(p["held"])]
    if not seats:
        return None
    li = 1 if rd.get("lang") == "en" else 0
    zug, schwer, welt = rd.get("zug", 0), SCHWER + e, rd.get("welt", "")
    out = []
    for n, (pid, h) in enumerate(seats):
        x = rollen[(zug + n) % len(rollen)]
        w = rng.randint(1, 20)
        bonus = dm.total(r, h, x["wert"])
        ok = w == 20 or (w != 1 and w + bonus >= schwer)
        out.append({"pid": pid, "name": h["name"], "rolle": _name(x, welt), "wert": x["wert"], "w": w, "bonus": bonus,
                    "gesamt": w + bonus, "schwer": schwer, "ok": ok, "t": list(x["gelingt"] if ok else x["misslingt"]),
                    **({} if ok else {"folge": x["folge_misslingt"]})})
    fail = [x["folge"] for x in out if not x["ok"]]
    ergebnis = fail[0] if fail else "ausgeruht" if any(x["w"] == 20 for x in out) else "ruhig"
    la = dungeon_rast.land(r, rd)
    table = i.get("reise_ereignisse") or {}
    rows = table.get(la["id"] if la else "") or table.get("weg") or []
    fit = [x for x in rows if x["ergebnis"] == ergebnis] or rows
    ev = fit[rng.randrange(len(fit))] if fit else None
    for _, h in seats:
        if ergebnis == "hungrig":
            h["leben"] = max(1, h["leben"] - HUNGER) if h["leben"] > 1 else h["leben"]
        elif ergebnis == "ausgeruht":
            dm.heal(h, RUHE)
        elif ergebnis == "ueberrascht":
            h["nachteil_zug"] = zug + 1               # dungeon.roll: the next turn's checks at a disadvantage
    rd["reise_tage"] = min(10 ** 6, rd.get("reise_tage", 0) + e + (1 if ergebnis == "verirrt" else 0))
    rd["reise"] = {"zug": zug + 1, "etappen": e, "land": la["name"] if la else ["", ""], "rollen": out, "ergebnis": ergebnis,
                   "t": list(ev["t"]) if ev else ["", ""]}
    dm._log(rd, "reise", etappen=e, land=(la["name"] if la else ["", ""])[li], ergebnis=ergebnis, t=(ev["t"] if ev else ["", ""])[li],
            rollen=[{k_: (v[li] if k_ in ("rolle", "t") else v) for k_, v in x.items()} for x in out])
    ok = sum(1 for x in out if x["ok"])
    _day.bump("reisen")
    _day.bump("gelungen", ok)
    _day.bump("misslungen", len(out) - ok)
    print(f"dungeon: reise | {e} etappen | {ok} von {len(out)} | {ergebnis}", flush=True)
    return rd["reise"]


def facts(rd):
    """The journey of the last way for the narration right after it: stages, landscape, roles with outcome, event."""
    x = rd.get("reise")
    if not x or x.get("zug") != rd.get("zug") or not on(rd):
        return {}
    li = 1 if rd.get("lang") == "en" else 0
    return {"reise": {"etappen": x["etappen"], "landschaft": x["land"][li], "ergebnis": x["ergebnis"], "ereignis": x["t"][li],
                      "rollen": [{"held": y["name"], "rolle": y["rolle"][li], "gelungen": y["ok"], "was": y["t"][li]} for y in x["rollen"]]}}


AUFGABE = {
    "de": (" Steht in den Fakten reise, erzählst du zuerst kurz die Reise: wie lange sie dauerte, die Landschaft, was "
           "jeder Held in seiner Rolle tat und wie es ausging, dann das ereignis. Die Folgen hat das Panel schon "
           "vergeben; nenne keine Zahlen."),
    "en": (" When the facts hold reise, first tell the journey briefly: how long it took, the landscape, what every hero did "
           "in its role and how it went, then the ereignis. The panel has already given the consequences; name no numbers."),
}


def task(rd, lang):
    return AUFGABE[lang] if on(rd) else ""


def for_live():
    """Numbers only: journeys and the roles' checks passed and failed today."""
    t = _day.counts()
    return {k: t[k] for k in ("reisen", "gelungen", "misslungen")}
