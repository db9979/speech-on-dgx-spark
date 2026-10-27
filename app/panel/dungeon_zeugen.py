"""KI-Dungeon-Master: Zeugen-Regel (LlamaTale idea 3, plan plaene/dungeon-llamatale-ideen.md, Dominik 2026-10-27 „1-7“;
idea only, own code).

What a hero does in front of people changes how they stand towards the hero, by fixed rules and never by the model:
- seen(dm, r, rd, wuerfe): before the narration the panel reads each seat's open action with fixed word lists (an attack
  by dungeon_kampf.intent, TATEN for theft, a gift, help) and the person of the scene it names (dungeon_nsc.scene); a
  theft whose Geschick check passed this turn stays unseen; an attack on a foe of the running fight is no deed. Every
  other person of the scene is a witness. The steps come from the fixed table FOLGE (target, witnesses). The narration
  gets the deeds and the new attitudes as data (facts „zeugen“) and only tells the reaction.
- apply(dm, rd, deeds): after the narration the attitudes change (one entry per person and hero, within −3..+3), the
  feed and the chronicle say so; the model's own nsc changes for these pairs are dropped this turn (drop).
Only while the admin's switch „Zeugen-Regel“ (dungeonzeugen) is allowed for the round's host, on top of „NSC-Gedächtnis
und Chronik“. Journal: fixed words and numbers („dungeon: zeugen | …“), Live only counts.
"""
import re

import dungeon_nsc as nsc
import features
from common import DayCounter

KEY = "dungeonzeugen"
TATEN = {                  # deeds besides an attack (dungeon_kampf.intent), by fixed word lists
    "diebstahl": re.compile(r"(?i)(?<!\w)(?:stiehl|stehl|stahl|klau|entwend|stibitz|mops|bestehl|steal|stole|pickpocket|pilfer|swipe|snatch)"),
    "geschenk": re.compile(r"(?i)(?<!\w)(?:schenk|beschenk|überreich|ueberreich|spendier|gift|present|(?:gebe?|gib|gab)\s+(?:[\w'-]+\s+){0,4}"
                           r"(?:ihm|ihr|ihnen|dir)(?!\w)|give\s+(?:him|her|them)(?!\w)|hand\s+(?:him|her|them)(?!\w))"),
    "hilfe": re.compile(r"(?i)(?<!\w)(?:helf|hilf|half|heil|rette|verbind|stütz|stuetz|beschütz|beschuetz|help|heal|rescue|bandage|aid|protect)"),
}
FOLGE = {"angriff": (-2, -1), "diebstahl": (-2, -1), "geschenk": (1, 0), "hilfe": (1, 0)}   # steps for (target, witnesses)
TAT_WORT = {"angriff": ("greift {ziel} an", "attacks {ziel}"), "diebstahl": ("bestiehlt {ziel}", "steals from {ziel}"),
            "geschenk": ("beschenkt {ziel}", "gives {ziel} a gift"), "hilfe": ("hilft {ziel}", "helps {ziel}")}
_day = DayCounter(taten=0, zeugen=0, unbemerkt=0)

AUFGABE = {
    "de": (" zeugen nennt, was ein Held vor Zeugen getan hat und wie die Leute der Szene jetzt zu ihm stehen (das Panel "
           "hat es so festgelegt): erzähl ihre Reaktion kurz und passend, melde für diese Leute und diesen Helden kein nsc."),
    "en": (" zeugen names what a hero did in front of witnesses and how the people of the scene now stand towards them (the "
           "panel set it so): tell their reaction briefly and fittingly, report no nsc for these people and this hero."),
}


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and nsc.on(rd)


def deed(text):
    """The deed of an action by the fixed word lists: angriff, diebstahl, geschenk, hilfe or ""."""
    import dungeon_kampf
    if dungeon_kampf.intent(text) in ("angriff", "bezug"):
        return "angriff"
    t = dungeon_kampf.NICHT_ANGRIFF.sub(" ", str(text or ""))
    return next((k for k, w in TATEN.items() if w.search(t)), "")


def seen(dm, r, rd, wuerfe=()):
    """Before the narration: [{pid, held (lower), tat, ziel (person key), schritte: {person key: step}}] for every seat
    whose action does a deed to a person of the scene; [] while off."""
    if not on(rd):
        return []
    ns = rd.get("nsc") or {}
    here = nsc.scene(rd)
    if not here:
        return []
    foes = {str(g.get("name", "")).lower() for g in (rd.get("kampf") or {}).get("gegner") or []}
    flink = {w["pid"] for w in wuerfe or () if w.get("ok") and w.get("wert") == "geschick"}
    out = []
    for pid, a in (rd.get("offen") or {}).items():
        h = (rd["plaetze"].get(pid) or {}).get("held")
        if not h or not isinstance(a, dict):
            continue
        tat = deed(a.get("text"))
        low = str(a.get("text") or "").lower()
        ziel = next((k for k in here if nsc.named(ns[k], low)), None)
        if not tat or not ziel:
            continue
        if tat == "angriff" and ns[ziel]["name"].lower() in foes:      # a foe of the running fight: no deed
            continue
        if tat == "diebstahl" and pid in flink:                         # a theft whose Geschick check passed: unseen
            _day.bump("unbemerkt")
            print("dungeon: zeugen | diebstahl | unbemerkt", flush=True)
            continue
        z, w = FOLGE[tat]
        schritte = {k: (z if k == ziel else w) for k in here}
        out.append({"pid": pid, "held": h["name"].lower(), "tat": tat, "ziel": ziel, "schritte": {k: v for k, v in schritte.items() if v}})
    return out


def facts(rd, deeds):
    """For the narration: each deed with the hero, the target and the attitudes the panel sets ({} without one)."""
    if not deeds:
        return {}
    ns, li, out = rd.get("nsc") or {}, 1 if rd.get("lang") == "en" else 0, []
    hn = {p["held"]["name"].lower(): p["held"]["name"] for p in rd["plaetze"].values() if p.get("held")}
    for d in deeds:
        neu = {ns[k]["name"]: nsc.word((ns[k].get("haltung") or {}).get(d["held"], 0) + s, li) for k, s in d["schritte"].items() if k in ns}
        out.append({"held": hn.get(d["held"], d["held"]), "tat": TAT_WORT[d["tat"]][li].format(ziel=ns[d["ziel"]]["name"]), "haltung": neu})
    return {"zeugen": out}


def task(rd, lang):
    """The narrator's task, only for a turn with deeds (rd["_zeugen"] on run_turn's copy)."""
    return AUFGABE[lang] if on(rd) and rd.get("_zeugen") else ""


def apply(dm, rd, deeds):
    """After the narration: the attitudes by the deeds (each person and hero once a turn); returns the (person, hero)
    pairs changed, so the model's own changes for them are dropped."""
    ns = rd.get("nsc") or {}
    heroes = {p["held"]["name"].lower(): (pid, p["held"]["name"]) for pid, p in rd["plaetze"].items() if p.get("held")}
    pairs = set()
    for d in deeds or []:
        if d.get("held") not in heroes or d.get("tat") not in FOLGE:
            print("dungeon: zeugen | verworfen | weg", flush=True)
            continue
        pid, name = heroes[d["held"]]
        n = 0
        for k, s in (d.get("schritte") or {}).items():
            x = ns.get(k)
            if not x or (k, d["held"]) in pairs or not isinstance(s, int):
                continue
            pairs.add((k, d["held"]))
            x.setdefault("haltung", {})
            was = x["haltung"].get(d["held"], 0)
            neu = max(nsc.HALTUNG[0], min(nsc.HALTUNG[1], was + s))
            if neu == was:
                continue
            x["haltung"][d["held"]] = neu
            n += k != d["ziel"]
            dm._log(rd, "nsc", pid=pid, name=name, nsc=x["name"], haltung=neu,
                    text=[f"{x['name']} ist {name} gegenüber jetzt {nsc.word(neu, 0)}.", f"{x['name']} is now {nsc.word(neu, 1)} towards {name}."])
        z = (ns.get(d["ziel"]) or {}).get("name", "")
        if d["tat"] in ("angriff", "diebstahl") and z:
            de, en = TAT_WORT[d["tat"]]
            nsc.note(rd, f"{name} {de.format(ziel=z)}, vor Zeugen.", f"{name} {en.format(ziel=z)}, in front of witnesses.")
        _day.bump("taten")
        _day.bump("zeugen", n)
        print(f"dungeon: zeugen | {d['tat']} | {n} zeugen", flush=True)
    return pairs


def drop(changes, pairs):
    """The model's nsc changes without the attitude steps the deeds set this turn (one step per person and hero)."""
    return [c for c in changes or [] if "schritt" not in c or (c.get("name"), c.get("held")) not in pairs]


def for_live():
    """Numbers only: deeds seen today, witnesses whose attitude changed, thefts unseen."""
    return _day.counts()
