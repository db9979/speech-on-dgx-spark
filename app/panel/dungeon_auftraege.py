"""KI-Dungeon-Master: Aufträge von Personen (LlamaTale idea 2, plan plaene/dungeon-llamatale-ideen.md, Dominik
2026-10-27 „1-7“; idea only, own code).

A person of the scene gives a hero an errand, and only the panel decides it, by fixed rules, never the model:
- seen(dm, r, rd, hits, rng): before the narration the panel reads each seat's open action with fixed word lists and
  the person of the scene it names (dungeon_nsc.scene, dungeon_nsc.named):
    neu        a word of ARBEIT to a person (attitude ≥ 0, no errand of theirs open, fewer than OFFEN_MAX open): the
               panel rolls the kind (ARTEN: bringen a thing of the market, reden with another person, besiegen a foe of
               the world near the group's level), the target, the reward (LOHN times the group's level, EP) and two
               clues (SPUREN: where the person was seen, what the market sells, what is said of the foe)
    bringen    a word of GEBEN to the giver while the hero carries the thing: done, the thing goes
    reden      the target person in the scene and named in an action: done
    besiegen   a hit this turn fells a foe of that kind: done
    zurueck    a word of ZURUECK to the giver: the errand is given back, the giver one step cooler
  The narration gets them as data (facts „auftraege“ with the open errands and their clues, „auftrag_jetzt“ for this
  turn) and only tells how the giver asks (the reason from the person's wish) or thanks.
- apply(dm, rd, events): after the narration the errands change: the reward to the hero who did it (gold) and the
  experience to every hero at the table (ep_tisch), the giver one step warmer, the feed and the chronicle say so.
Only while the admin's switch „Aufträge von Personen“ (dungeonauftraege) is allowed for the round's host, on top of
„NSC-Gedächtnis und Chronik“. The errands are no secret: every seat sees them with their clues (view). Journal: fixed
words and numbers („dungeon: auftraege | …“), Live only counts.

    rd["auftraege"]  [{"id", "art", "geber": person key, "geber_name", "ziel": item id | person key | foe id,
                       "ziel_name": [de, en], "lohn": gold, "ep", "spuren": [[de, en], …], "grund": [de, en],
                       "status": "offen" | "erfuellt" | "zurueck", "zug", "held": hero (lower) it was given to}]
"""
import random
import re

import dungeon_nsc as nsc
import features
from common import DayCounter

KEY = "dungeonauftraege"
ARTEN = ("bringen", "reden", "besiegen")
OFFEN_MAX = 3              # open errands of a round at once
LISTE_MAX = 12             # errands a round keeps (the newest)
LOHN = {"bringen": (8, 16), "reden": (5, 12), "besiegen": (15, 30)}    # gold, times the group's level
EP = {"bringen": 30, "reden": 20, "besiegen": 50}                    # experience for every hero at the table
ARBEIT = re.compile(r"(?i)(?:(?:arbeit|auftrag|aufgabe|job)\s+für\s+(?:mich|uns)|(?:hast|habt|haben\s+sie)\s+(?:[\w'-]+\s+){0,3}(?:arbeit|auftrag|aufgabe)|"
                    r"brauchst\s+du\s+hilfe|kann\s+ich\s+(?:dir|euch|ihnen)\s+helfen|was\s+kann\s+ich\s+für|(?:any|some)\s+(?:work|errand|task|job)|"
                    r"(?:work|errand|task|job|quest)\s+for\s+(?:me|us)|need\s+help|can\s+i\s+help)")
GEBEN = re.compile(r"(?i)(?<!\w)(?:gib|gebe|gebt|übergeb|uebergeb|überreich|ueberreich|bring|liefer|reich|give|hand|deliver)")
ZURUECK = re.compile(r"(?i)(?:auftrag\w*\s+(?:[\w'-]+\s+){0,3}zurück(?!\w)|auftrag\w*\s+ab(?:geben|brechen)?(?!\w)|"
                     r"brech\w*\s+(?:[\w'-]+\s+){0,3}auftrag\w*\s+ab(?!\w)|verzicht\w*\s+auf\s+(?:den\s+|diesen\s+)?auftrag|"
                     r"(?:errand|task|quest)\s+back|abandon\s+(?:[\w'-]+\s+){0,3}(?:errand|task|quest)|drop\s+(?:[\w'-]+\s+){0,3}(?:errand|task|quest))")
WORTE = {"bringen": ("Bring {geber} {ziel}.", "Bring {geber} {ziel}."),
         "reden": ("Sprich für {geber} mit {ziel}.", "Speak with {ziel} for {geber}."),
         "besiegen": ("Besiege für {geber} {ziel}.", "Defeat {ziel} for {geber}.")}
_day = DayCounter(neu=0, erfuellt=0, zurueck=0)

AUFGABE = {
    "de": (" auftrag_jetzt nennt, was das Panel in diesem Zug mit Aufträgen von Personen entschieden hat: ein neuer "
           "Auftrag (erzähl in einem Satz, warum die Person ihn gibt, ihr grund leitet dich), ein erfüllter (erzähl ihren "
           "Dank) oder ein zurückgegebener. auftraege sind die offenen mit ihren Spuren: lass eine Spur sichtbar werden, "
           "wenn die Helden ihr folgen. Aufträge vergibt und schließt nur das Panel."),
    "en": (" auftrag_jetzt names what the panel decided this turn about errands from people: a new errand (tell in one "
           "sentence why the person gives it, its grund guides you), one done (tell their thanks) or one given back. "
           "auftraege are the open ones with their clues: let a clue show when the heroes follow it. Only the panel "
           "gives and closes errands."),
}


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and nsc.on(rd)


def _li(rd):
    return 1 if rd.get("lang") == "en" else 0


def open_(rd):
    return [a for a in rd.get("auftraege") or [] if a["status"] == "offen"]


def _items(dm, r, rd):
    """The things an errand may ask for: potions and tools of the market (no rarity of their own) of the world."""
    return [c for c in r["gegenstaende"] if c["art"] in ("trank", "werkzeug") and "seltenheit" not in c and dm.in_world(c, rd.get("welt"))]


def _foes(dm, r, rd, lvl):
    import dungeon_bestiarium                    # a peaceful one is never an errand's foe (Review 27.10. Paket 11)
    return [g for g in r["gegner"] if dm.in_world(g, rd.get("welt")) and g.get("stufe", 0) <= lvl and not g.get("boss")
            and not dungeon_bestiarium.friedlich(g)]


def _level(dm, rd):
    return dm.group_level([p["held"] for _, p in dm.seated(rd)] or [{"stufe": 1}])


def roll(dm, r, rd, geber, held, rng=None):
    """A new errand of the person geber (key) for the hero held (lower) by the fixed tables; None when no kind fits."""
    rng = rng or random
    ns = rd["nsc"]
    lvl = _level(dm, rd)
    ziele = {"bringen": _items(dm, r, rd), "reden": [k for k in ns if k != geber], "besiegen": _foes(dm, r, rd, lvl)}
    arten = [a for a in ARTEN if ziele[a]]
    if not arten:
        return None
    art = rng.choice(arten)
    z = rng.choice(ziele[art])
    import dungeon_karte
    weg = {x["name"].lower(): x["ort"] for x in dungeon_karte.leute(rd)["anderswo"]}
    if art == "bringen":
        zid, zname = z["id"], list(z["name"])
        spuren = [["Händler auf einem Markt führen " + z["name"][0] + ".", "Merchants at a market sell " + z["name"][1] + "."],
                  [str(z.get("info", ["", ""])[0])[:160], str(z.get("info", ["", ""])[1])[:160]]]
    elif art == "reden":
        x = ns[z]
        zid, zname = z, [x["name"], x["name"]]
        ort = weg.get(z)
        beruf = (x.get("karte") or {}).get("beruf")
        spuren = [[f"{x['name']} wurde zuletzt in {ort} gesehen.", f"{x['name']} was last seen at {ort}."] if ort else
                  [f"Die Leute der Gegend kennen {x['name']}; fragt nach.", f"The people around know {x['name']}; ask about."]]
        if isinstance(beruf, list) and len(beruf) == 2:
            spuren.append([f"{x['name']}: {beruf[0]}.", f"{x['name']}: {beruf[1]}."])
    else:
        zid, zname = z["id"], list(z["name"])
        spuren = [list(z["sage"]) if isinstance(z.get("sage"), list) and len(z["sage"]) == 2 else [z["name"][0], z["name"][1]],
                  [str(z.get("info", ["", ""])[0])[:160], str(z.get("info", ["", ""])[1])[:160]]]
    lo, hi = LOHN[art]
    wunsch = (ns[geber].get("karte") or {}).get("wunsch")
    return {"id": "", "art": art, "geber": geber, "geber_name": ns[geber]["name"], "ziel": zid, "ziel_name": zname,
            "lohn": rng.randint(lo, hi) * lvl, "ep": EP[art], "spuren": [s for s in spuren if s[0] and s[1]][:2],
            "grund": list(wunsch) if isinstance(wunsch, list) and len(wunsch) == 2 else ["", ""],
            "status": "offen", "zug": rd.get("zug", 0), "held": held}


def seen(dm, r, rd, hits=(), rng=None):
    """Before the narration: the panel's events of the turn [{was: neu|erfuellt|zurueck, …}]; [] while off."""
    if not on(rd):
        return []
    ns = rd.get("nsc") or {}
    here = nsc.scene(rd)
    offen = open_(rd)
    out, busy = [], {a["geber"] for a in offen}
    n_offen = len(offen)
    for pid, a in (rd.get("offen") or {}).items():
        h = (rd["plaetze"].get(pid) or {}).get("held")
        if not h or not isinstance(a, dict) or dm.zustand(h):
            continue
        t = str(a.get("text") or "")
        low = t.lower()
        named = [k for k in here if nsc.named(ns[k], low)]
        for x in offen:
            if any(e.get("id") == x["id"] for e in out):
                continue
            if x["geber"] in named and ZURUECK.search(t):
                out.append({"was": "zurueck", "id": x["id"], "pid": pid})
            elif x["art"] == "bringen" and x["geber"] in named and GEBEN.search(t):
                it = next((i for i in h.get("tasche") or [] if i.get("id") == x["ziel"]), None)
                if it:
                    out.append({"was": "erfuellt", "id": x["id"], "pid": pid, "i": it["i"]})
            elif x["art"] == "reden" and x["ziel"] in named:
                out.append({"was": "erfuellt", "id": x["id"], "pid": pid})
        if ARBEIT.search(t) and not ZURUECK.search(t):
            k = next((k for k in named if k not in busy and (ns[k].get("haltung") or {}).get(h["name"].lower(), 0) >= 0), None)
            if k and n_offen < OFFEN_MAX:
                neu = roll(dm, r, rd, k, h["name"].lower(), rng)
                if neu:
                    out.append({"was": "neu", "pid": pid, "auftrag": neu})
                    busy.add(k)
                    n_offen += 1
            elif named:
                print("dungeon: auftraege | kein neuer", flush=True)
    foes = {str(g.get("name", "")): g.get("id") for g in (rd.get("kampf") or {}).get("gegner") or []}
    for x in hits or ():
        if not x.get("faellt"):
            continue
        fid = foes.get(str(x.get("gegner", "")))
        a = next((a for a in offen if a["art"] == "besiegen" and a["ziel"] == fid and not any(e.get("id") == a["id"] for e in out)), None)
        if a:
            out.append({"was": "erfuellt", "id": a["id"], "pid": x["pid"]})
    return out


def _text(a, li):
    return WORTE[a["art"]][li].format(geber=a["geber_name"], ziel=a["ziel_name"][li])


def facts(rd, events):
    """For the narration: the open errands with their clues and this turn's events ({} while off or without any)."""
    if not on(rd):
        return {}
    li, byid = _li(rd), {a["id"]: a for a in rd.get("auftraege") or []}
    out = {}
    offen = [{"auftrag": _text(a, li), "lohn": a["lohn"], "spuren": [s[li] for s in a["spuren"]]} for a in open_(rd)]
    if offen:
        out["auftraege"] = offen
    jetzt = []
    for e in events or []:
        a = e.get("auftrag") or byid.get(e.get("id"))
        if a:
            jetzt.append({"was": e["was"], "auftrag": _text(a, li), "von": a["geber_name"], "lohn": a["lohn"],
                          **({"grund": a["grund"][li]} if e["was"] == "neu" and a["grund"][li] else {})})
    if jetzt:
        out["auftrag_jetzt"] = jetzt
    return out


def task(rd, lang):
    """The narrator's task, only while errands are open or this turn has events (rd["_auftraege"] on run_turn's copy)."""
    return AUFGABE[lang] if on(rd) and (rd.get("_auftraege") or open_(rd)) else ""


def apply(dm, rd, events):
    """After the narration: the errands by the events of the turn, the rewards, the giver's attitude, feed and chronicle."""
    ns = rd.get("nsc") or {}
    li = rd.setdefault("auftraege", [])
    for e in events or []:
        p = rd["plaetze"].get(e.get("pid")) or {}
        h = p.get("held")
        if e.get("was") == "neu":
            a = e.get("auftrag")
            if not h or not isinstance(a, dict) or a.get("geber") not in ns or len(open_(rd)) >= OFFEN_MAX \
                    or any(x["geber"] == a["geber"] for x in open_(rd)):
                print("dungeon: auftraege | verworfen | neu", flush=True)
                continue
            a["id"] = f"a{max([int(x['id'][1:]) for x in li if re.fullmatch(r'a[0-9]+', x['id'])] or [0]) + 1}"
            li.append(a)
            dm._log(rd, "system", text=[f"Neuer Auftrag von {a['geber_name']}: {_text(a, 0)} Lohn {a['lohn']} Gold.",
                                        f"New errand from {a['geber_name']}: {_text(a, 1)} Reward {a['lohn']} gold."])
            _day.bump("neu")
            print(f"dungeon: auftraege | neu | {a['art']}", flush=True)
            continue
        a = next((x for x in open_(rd) if x["id"] == e.get("id")), None)
        if not a or not h:
            print("dungeon: auftraege | verworfen | weg", flush=True)
            continue
        x = ns.get(a["geber"])
        if e["was"] == "zurueck":
            a["status"] = "zurueck"
            if x:
                x.setdefault("haltung", {})[h["name"].lower()] = max(nsc.HALTUNG[0], x["haltung"].get(h["name"].lower(), 0) - 1)
            dm._log(rd, "system", text=[f"{h['name']} gibt den Auftrag von {a['geber_name']} zurück.", f"{h['name']} gives {a['geber_name']}'s errand back."])
            _day.bump("zurueck")
            print("dungeon: auftraege | zurueck", flush=True)
            continue
        if a["art"] == "bringen":
            it = next((i for i in h.get("tasche") or [] if i.get("i") == e.get("i") and i.get("id") == a["ziel"]), None)
            if not it:
                print("dungeon: auftraege | verworfen | ding", flush=True)
                continue
            dm.use_one(h, it)
        a["status"] = "erfuellt"
        h["gold"] = h.get("gold", 0) + a["lohn"]
        for q, s in dm.seated(rd):
            if not s["held"].get("tot"):
                s["held"]["ep_tisch"] = min(10 ** 7, s["held"].get("ep_tisch", 0) + a["ep"])
                dm._log(rd, "ep", pid=q, name=s["held"]["name"], zahl=a["ep"], tisch=s["held"]["ep_tisch"], grund=["auftrag"])
        if x:
            x.setdefault("haltung", {})[h["name"].lower()] = min(nsc.HALTUNG[1], x["haltung"].get(h["name"].lower(), 0) + 1)
        dm._log(rd, "system", text=[f"Auftrag erfüllt: {_text(a, 0)} {h['name']} bekommt {a['lohn']} Gold.",
                                    f"Errand done: {_text(a, 1)} {h['name']} gets {a['lohn']} gold."])
        nsc.note(rd, f"{h['name']} erfüllt den Auftrag von {a['geber_name']}.", f"{h['name']} does {a['geber_name']}'s errand.")
        _day.bump("erfuellt")
        print(f"dungeon: auftraege | erfuellt | {a['art']}", flush=True)
    if len(li) > LISTE_MAX:                    # the open ones stay, of the others the newest
        alt = [x for x in li if x["status"] != "offen"][len(li) - LISTE_MAX:]
        rd["auftraege"] = [x for x in li if x["status"] == "offen" or x in alt]


def view(rd):
    """Every seat's view: the open errands with their clues and the last ones done or given back (None while off)."""
    if not on(rd):
        return None
    li = _li(rd)
    return [{"id": a["id"], "text": _text(a, li), "von": a["geber_name"], "lohn": a["lohn"], "status": a["status"],
             "spuren": [s[li] for s in a["spuren"]]} for a in rd.get("auftraege") or []][-6:]


def for_live():
    """Numbers only: errands given, done, given back today."""
    return _day.counts()
