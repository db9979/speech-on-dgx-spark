"""KI-Dungeon-Master: Gedanken lesen (LlamaTale idea 5, plan plaene/dungeon-llamatale-ideen.md, Dominik 2026-10-27
„1-7“; idea only, own code).

A hero who reads a person's mind hears its thoughts by fixed rules of the panel, never by the model:
- checks(dm, r, rd, proben): before the narration a seat whose action casts the spell „Gedanken lesen“ this turn (the
  action's kraft, dungeon.check_powers) or that still has its blessing or that of the „Trank des Gedankenlesens“
  (segen with q in QUELLEN) and asks for thoughts with a word of LESEN, and that names a person of the scene
  (dungeon_nsc.scene, dungeon_nsc.named), rolls the panel's Intelligenz check in place of the model's checks for it;
  how hard comes from the person's attitude towards the hero (SG: hostile 15, neutral 13, fond 11), the blessing's
  bonus helps.
- apply(dm, rd, wuerfe): after the narration a passed check gives only that seat a fixed line (the person's wish,
  secret and attitude towards the hero, from its card), a failed one „… verschließt die Gedanken vor dir.“; kept in
  rd["gedanken"][pid] (at most LISTE_MAX). The host sees only who read whose thoughts, never what (view).
The narration gets the check as a receipt and the task to tell only that the hero listens, never what the person
thinks: the model writes no line for it, so the secret cannot reach the table through the narration. The car never
reads the line aloud (others may listen there); the seat's own screen shows it. Only while the admin's switch
„Gedanken lesen“ (dungeongedanken) is allowed for the round's host, on top of „NSC-Gedächtnis und Chronik“.
Journal: fixed words and numbers („dungeon: gedanken | …“), Live only counts.
"""
import re

import dungeon_nsc as nsc
import features
from common import DayCounter

KEY = "dungeongedanken"
QUELLEN = ("gedanken_lesen", "gedankentrank")      # the spell and the potion whose blessing reads minds (catalog ids)
ZAUBER = "gedanken_lesen"
LESEN = re.compile(r"(?i)(?<!\w)(?:gedanken|denkt|denken|durchschau|ergründ|ergruend|horch|lausch|read|mind|thought|think)")
SG = (15, 13, 11)          # the check against a hostile (< 0), a neutral (0..1) and a fond (≥ 2) person
LISTE_MAX = 8              # lines a seat keeps
_day = DayCounter(versuche=0, gelesen=0, verschlossen=0)

AUFGABE = {
    "de": (" Eine Probe „Gedanken lesen“ ist dabei: erzähl nur, dass der Held lauscht und ob es gelingt, nie, was die "
           "Person denkt, wünscht oder verbirgt; das hört der Held allein vom Panel."),
    "en": (" A check „read the thoughts“ is part of it: tell only that the hero listens and whether it works, never what "
           "the person thinks, wishes or hides; the hero alone hears that from the panel."),
}


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and nsc.on(rd)


def reads(h, a):
    """Whether the seat's action reads a mind: the spell cast this turn, or its blessing (or the potion's) still on
    and a word of LESEN."""
    if a.get("kraft") == ZAUBER:
        return True
    return any(x.get("q") in QUELLEN for x in h.get("segen") or []) and bool(LESEN.search(str(a.get("text") or "")))


def hard(x, held):
    """How hard the check is against this person: by its attitude towards the hero."""
    v = (x.get("haltung") or {}).get(held, 0)
    return SG[0] if v < 0 else SG[2] if v >= 2 else SG[1]


def checks(dm, r, rd, proben):
    """Before the narration: the panel's Intelligenz check for each seat that reads a person's mind, in place of the
    model's checks for that seat; the check names the person (gedanken: its key)."""
    if not on(rd):
        return proben
    here = nsc.scene(rd)
    if not here:
        return proben
    ns, li = rd["nsc"], 1 if rd.get("lang") == "en" else 0
    for pid, a in (rd.get("offen") or {}).items():
        h = (rd["plaetze"].get(pid) or {}).get("held")
        if not h or dm.zustand(h) or not isinstance(a, dict) or not reads(h, a):
            continue
        low = str(a.get("text") or "").lower()
        k = next((k for k in here if nsc.named(ns[k], low)), None)
        if not k:
            print("dungeon: gedanken | kein ziel", flush=True)
            continue
        _day.bump("versuche")
        print("dungeon: gedanken | probe", flush=True)
        proben = [p for p in proben if p["pid"] != pid] + [
            {"pid": pid, "wert": "intelligenz", "schwer": hard(ns[k], h["name"].lower()), "vt": "", "gedanken": k,
             "wofuer": (f"Gedanken lesen: {ns[k]['name']}", f"read the thoughts of {ns[k]['name']}")[li]}]
    return proben


def task(rd, lang):
    """The narrator's task, only for a turn with such a check (rd["_gedanken"] on run_turn's copy)."""
    return AUFGABE[lang] if on(rd) and rd.get("_gedanken") else ""


def _t(v, li):
    return str(v[li] if isinstance(v, list) and len(v) > li else v or "")[:160]


def line(x, held):
    """The fixed line of a passed check (de, en): the person's wish, secret and attitude towards the hero."""
    k = x.get("karte") or {}
    v = (x.get("haltung") or {}).get(held, 0)
    out = []
    for li, (denkt, wunsch, geheim, dir_) in enumerate((("denkt", "Wunsch", "Verbirgt", "Dir gegenüber"),
                                                         ("thinks", "Wish", "Hides", "Towards you"))):
        t = [f"{x['name']} {denkt}:"]
        if _t(k.get("wunsch"), li):
            t.append(f"{wunsch}: {_t(k['wunsch'], li)}.")
        if _t(k.get("geheimnis"), li):
            t.append(f"{geheim}: {_t(k['geheimnis'], li)}.")
        t.append(f"{dir_}: {nsc.word(v, li)}.")
        out.append(" ".join(t))
    return out


def apply(dm, rd, wuerfe):
    """After the narration: each mind-reading check gives its seat the fixed line (or that the person shut it out)."""
    ns = rd.get("nsc") or {}
    for w in wuerfe or []:
        k = w.get("gedanken")
        if not k:
            continue
        x, h = ns.get(k), (rd["plaetze"].get(w["pid"]) or {}).get("held")
        if not x or not h:
            print("dungeon: gedanken | verworfen | weg", flush=True)
            continue
        if w["ok"]:
            zeile = line(x, h["name"].lower())
            _day.bump("gelesen")
        else:
            zeile = [f"{x['name']} verschließt die Gedanken vor dir.", f"{x['name']} shuts their thoughts away from you."]
            _day.bump("verschlossen")
        mine = rd.setdefault("gedanken", {}).setdefault(w["pid"], [])
        mine.append({"zug": rd.get("zug", 0), "nsc": x["name"], "ok": bool(w["ok"]), "zeile": zeile})
        del mine[:-LISTE_MAX]
        print(f"dungeon: gedanken | {'gelesen' if w['ok'] else 'verschlossen'}", flush=True)


def view(rd, pid, host):
    """The own seat's lines in the round's language; the host also who read whose thoughts (never what)."""
    if not on(rd):
        return None
    li = 1 if rd.get("lang") == "en" else 0
    alle = rd.get("gedanken") or {}
    out = {"meine": [{"zug": x["zug"], "nsc": x["nsc"], "ok": x["ok"], "zeile": x["zeile"][li]} for x in alle.get(pid) or []][-3:]}
    if host:
        names = {q: (p.get("held") or {}).get("name", "") for q, p in rd["plaetze"].items()}
        out["andere"] = [{"wer": names.get(q, ""), "nsc": x["nsc"], "zug": x["zug"]} for q, xs in alle.items() if q != pid for x in xs][-LISTE_MAX:]
    return out


def for_live():
    """Numbers only: mind-reading checks today, thoughts read, thoughts shut away."""
    return _day.counts()
