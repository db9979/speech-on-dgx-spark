"""KI-Dungeon-Master: Personen-Katalog (Dominik 2026-10-26 „1-5“ with „das ganze muss natürlich im balancing
berücksichtigt werden“ and „auch in das begegnungs / monster album buch der spieler mit aufnehemen“; own code).

The people the tables met become a stock the stories and the roads use again:
1. Every person of a round with a card (dungeon_nsc) that the table met goes into the catalog when the round ends
   (collect): its card, traits, role and goal, voice, portrait and its attitude towards each hero by the hero's name.
   The admin sees, changes, deletes and adds people under Regeln → „Personen (NSC)“ (view, change; the same list and
   detail as the other parts of the rules, dungeon_regelseite). Wish and secret only there and for the round's host.
3. On the road: per act (without a story: per chapter) the panel offers the narrator up to ANGEBOT known people of the
   round's world (offer, by a die seeded with the round, chapter and act), only as data. When the narration brings one
   of them by its exact name, the person comes with its stored card (adopt, from dungeon_nsc.sync): the same looks,
   traits, voice and face, and the attitudes it keeps towards the heroes at the table (it knows them again). Any other
   new name is a new person as before; a name the catalog already has in that world is never taken over twice.
2. In the story planner (the admin's, a host's own stories): the form lists the catalog's people of the story's world
   (name and occupation, never wish or secret) to tick, up to PLAN_MAX; the model's draft gets them only as data and a
   person whose exact name the draft uses comes ticked (pick). A round with that story brings them into the chapter's
   truth with their stored role and goal (into_truth) and always offers them first (offer), so the narration meets them
   with their fixed card.
5. Off by default: the admin's switch dungeonpersonen (features.py, chat.dungeon_personen), on top of „NSC-Gedächtnis
   und Chronik“, for the round's host.

    STATE/dungeon-personen.json  {id: {"id", "name", "welt", "karte": {feld: [de, en]}, "wesen", "rolle", "ziel",
                                  "stimme", "gesicht"?, "haltung": {held lower: −3..3}, "treffen", "made", "t", "stand"}}

Journal: fixed words and numbers („dungeon: personen | …“), Live only counts.
"""
import os
import random
import re
import threading
import time

import dungeon_album as album
import dungeon_bestiarium as best
import dungeon_nsc as nsc
import dungeon_stimmen as stimmen
import features
from common import STATE, DayCounter, read_json, write_json

KEY = "dungeonpersonen"
FILE = os.path.join(STATE, "dungeon-personen.json")
MAX = 300                  # people in the catalog (the oldest from a round go first)
ANGEBOT = 3                # known people offered to the narrator per act
PLAN_MAX = 3               # people of the catalog a story brings (Personen-Katalog 2)
NAME_LEN = 40
FELD_LEN = 120             # a card's field per language
TEIL_LEN = 80              # role and goal
_ID = re.compile(r"^[a-z0-9_]{1,40}$")
_lock = threading.Lock()
_day = DayCounter(neu=0, wieder=0, erkannt=0, gekaempft=0, geaendert=0, geloescht=0, geschichte=0, stimme=0)
FELD = {"aussehen": ("Aussehen", "Looks"), "art": ("Art", "Manner"), "beruf": ("Beruf", "Occupation"),
        "wunsch": ("Wunsch", "Wish"), "geheimnis": ("Geheimnis", "Secret"), "haar": ("Haar", "Hair"), "augen": ("Augen", "Eyes"),
        "bart": ("Bart", "Beard"), "statur": ("Statur", "Build")}


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and nsc.on(rd)


def admin_on():
    return features.admin_on(KEY)


def load():
    d = read_json(FILE, {})
    return {k: v for k, v in d.items() if _ID.match(str(k)) and isinstance(v, dict) and v.get("name")} if isinstance(d, dict) else {}


def _save(d):
    write_json(FILE, d, 2, 0o600, False, 0o700)


def _text(r, x):
    """Every text of a person in both languages (for the word checks)."""
    return " ".join([x.get("name", ""), x.get("rolle", ""), x.get("ziel", "")] + [t for v in (x.get("karte") or {}).values() for t in v])


# ---------------------------------------------------------------- in a round
def _pool(dm, r, rd):
    """The catalog's people of the round's world whose words fit its tone, in a fixed order."""
    return [x for _, x in sorted(load().items()) if x.get("welt") == rd.get("welt") and not dm.bad_words(r, rd, _text(r, x))]


def offer(dm, r, rd):
    """The people the round's story brings (Personen-Katalog 2) first, then up to ANGEBOT people of the world for this
    act, by a die seeded with the round, its chapter and act."""
    if not on(rd):
        return []
    xs = _pool(dm, r, rd)
    mine = [x for i in (rd.get("plan") or {}).get("personen") or [] for x in xs if x["id"] == i]
    rest = [x for x in xs if x not in mine]
    rng = random.Random(f"{rd.get('made', 0)}:{rd.get('kapitel', 0)}:{rd.get('akt', 0)}")
    return mine + rng.sample(rest, min(max(0, ANGEBOT - len(mine)), len(rest)))


def for_plan(welt=None):
    """The catalog's people for the planner's form: id, name, world, occupation [de, en]; never wish or secret."""
    return [{"id": x["id"], "name": x["name"], "welt": x.get("welt"), "beruf": list((x.get("karte") or {}).get("beruf") or ["", ""])[:2]}
            for _, x in sorted(load().items(), key=lambda kv: kv[1]["name"].lower()) if welt is None or x.get("welt") == welt]


def plan_ids(ids, welt):
    """A story's people by fixed rules: ids of the catalog in the story's world, each once, at most PLAN_MAX."""
    if not isinstance(ids, list) or not ids:
        return []
    have = load()
    ok = [i for i in dict.fromkeys(x for x in ids if isinstance(x, str) and _ID.match(x)) if (have.get(i) or {}).get("welt") == welt]
    return ok[:PLAN_MAX]


def pick(pool, g):
    """The draft's people: those of the pool whose exact name the model's story uses (at most PLAN_MAX)."""
    text = " ".join([g.get("titel", ""), g.get("idee", ""), g.get("ziel", ""), g.get("gegner", "")]
                    + [" ".join((a["titel"], a["inhalt"], a["wende"])) for a in g.get("akte") or []])
    return [p["id"] for p in pool if re.search(r"(?<!\w)" + re.escape(p["name"]) + r"(?!\w)", text)][:PLAN_MAX]


def into_truth(r, rd, wahr):
    """At a chapter's start: the people the round's story brings go into the truth with their stored role and goal
    (first, never twice, at most the truth's limit); a truth the model did not make gets them alone."""
    import dungeon_erzaehler as erz
    ids = (rd.get("plan") or {}).get("personen") or []
    if not ids or not on(rd) or rd.get("wahrheit"):
        return wahr
    d = load()
    xs = [d[i] for i in ids if i in d and d[i].get("welt") == rd.get("welt")]
    if not xs:
        return wahr
    w = wahr or {"personen": [], "gruppen": [], "geheimnisse": []}
    have = {p["name"].lower() for p in w["personen"]}
    neu = [{"name": x["name"][:erz.NAME_LEN], "rolle": x.get("rolle", "")[:erz.TEIL_LEN], "ziel": x.get("ziel", "")[:erz.TEIL_LEN], "sprache": ""}
           for x in xs if x["name"][:erz.NAME_LEN].lower() not in have]
    w["personen"] = (neu + w["personen"])[:erz.PERSONEN_MAX]
    _day.bump("geschichte", len(neu))
    print(f"dungeon: personen | geschichte | {len(neu)} in der wahrheit", flush=True)
    return w


def facts(dm, r, rd, li):
    """The offered people not yet in the story, only as data: name, role, looks, occupation."""
    have = {k for k in rd.get("nsc") or {}} | {p["name"].lower() for p in (rd.get("wahrheit") or {}).get("personen") or []}
    xs = [x for x in offer(dm, r, rd) if x["name"].lower() not in have]
    if not xs:
        return {}
    k = lambda x, f: (x.get("karte") or {}).get(f, ["", ""])[li]   # noqa: E731
    return {"bekannte_personen": [{"name": x["name"], "rolle": x.get("rolle", ""), "aussehen": k(x, "aussehen"), "beruf": k(x, "beruf")}
                                  for x in xs]}


AUFGABE = {
    "de": (" Tritt eine neue Person auf, darf es eine aus bekannte_personen sein, mit genau diesem Namen und so, wie sie "
           "dort beschrieben ist; sie kann die Helden von früher kennen."),
    "en": (" When a new person appears, it may be one of bekannte_personen, with exactly that name and as described there; "
           "it may know the heroes from before."),
}


KAMPF_AUFGABE = {
    "de": (" Ein Eintrag in angebot mit person ist diese Person der Szene mit festen Werten; wähle sie nur, wenn sie "
           "wirklich gegen die Gruppe kämpft."),
    "en": (" An entry of angebot with person is that person of the scene with fixed values; choose it only when it really "
           "fights against the group."),
}


def task(dm, r, rd, lang):
    return (AUFGABE[lang] if facts(dm, r, rd, 0) else "") + (KAMPF_AUFGABE[lang] if on(rd) and nsc.scene(rd) and not rd.get("kampf") else "")


def adopt(r, rd, name):
    """From dungeon_nsc.sync: a new person of the round named like one offered this act comes with its stored card,
    traits, voice, face and the attitudes towards the heroes at the table; None for anyone else."""
    import dungeon as dm
    k = str(name or "").strip().lower()
    x = next((x for x in offer(dm, r, rd) if x["name"].lower() == k), None)
    if not x:
        return None
    heroes = {p["held"]["name"].lower() for p in rd["plaetze"].values() if p.get("held")}
    haltung = {h: v for h, v in (x.get("haltung") or {}).items() if h in heroes and isinstance(v, int)}
    card = {"name": x["name"], "karte": {f: list(v) for f, v in (x.get("karte") or {}).items()}, "kanten": [], "haltung": haltung,
            "gesehen": None, "wesen": dict(x.get("wesen") or {}) or nsc.traits(), "ziele": nsc.goals(r, rd, x.get("ziel", "")), "katalog": x["id"],
            **_fixed(x)}                                 # its one gender and age (Review 27.10. Paket 10)
    g = x.get("gesicht")
    if isinstance(g, dict) and g.get("n"):
        card["gesicht"] = {"n": g["n"], "st": "ok"}
    elif not dm.kids(r, rd):                    # its catalog face (dungeon_dingbild.person_pic), never at the children's table
        import dungeon_dingbild
        n = dungeon_dingbild.person_pic(r, x)
        if n:
            card["gesicht"] = {"n": n, "st": "ok"}
    if isinstance(x.get("stimme"), dict):
        rd.setdefault("npc_stimmen", {})[k[:40]] = dict(x["stimme"])
    for p in (rd.get("wahrheit") or {}).get("personen") or []:
        if p["name"].lower() == k:
            p["rolle"] = p.get("rolle") or x.get("rolle", "")
            p["ziel"] = p.get("ziel") or x.get("ziel", "")
    _day.bump("wieder")
    print(f"dungeon: personen | wieder | {len(haltung)} helden", flush=True)
    if haltung:
        _day.bump("erkannt")
        names = {p["held"]["name"].lower(): p["held"]["name"] for p in rd["plaetze"].values() if p.get("held")}
        wer = ", ".join(names[h] for h in sorted(haltung))
        nsc.note(rd, f"{x['name']} erkennt {wer} wieder.", f"{x['name']} recognises {wer}.")
    return card


def _fixed(x):
    """A catalog person's one gender and age: its own fields, else those of the voice the admin chose."""
    st = x.get("stimme") if isinstance(x.get("stimme"), dict) else {}
    g = x.get("geschlecht") or {v: k for k, v in stimmen.KARTE.items()}.get(st.get("geschlecht"))
    a = x.get("alter") or st.get("alter")
    return {**({"geschlecht": g} if g in stimmen.KARTE else {}), **({"alter": a} if a in nsc.ALTER_WORT else {})}


def collect(dm, r, rd, now=None):
    """At the round's end: every person the table met into the catalog. One taken from the catalog updates its own
    entry (attitudes, meetings, face); a new one is added unless its world has that name already."""
    if not on(rd):
        return 0
    now = int(time.time() if now is None else now)
    welt = rd.get("welt")
    stimmen = rd.get("npc_stimmen") or {}
    rollen = {p["name"].lower(): p for p in (rd.get("wahrheit") or {}).get("personen") or []}
    n = 0
    with _lock:
        d = load()
        names = {(v.get("welt"), v["name"].lower()) for v in d.values()}
        for k, x in (rd.get("nsc") or {}).items():
            if x.get("gesehen") is None or nsc.no_person(r, dict(rd, kampf=None), x.get("name"), "katalog"):
                continue                         # Review 27.10. Paket 8: never a foe, hero or role word in the catalog
            g = x.get("gesicht") if isinstance(x.get("gesicht"), dict) and (x.get("gesicht") or {}).get("st") == "ok" else None
            p = d.get(x.get("katalog") or "")
            if p and p.get("welt") == welt:
                album.met(dm, rd, p["id"])      # the hero's album page „Personen“: one more meeting
                p["haltung"] = dict(p.get("haltung") or {}, **{h: v for h, v in (x.get("haltung") or {}).items() if isinstance(v, int)})
                p["treffen"] = p.get("treffen", 0) + 1
                p["t"] = now
                if g:
                    p["gesicht"] = {"n": g["n"]}
                continue
            if (welt, k) in names or len(x.get("name", "")) < 2 or dm.word_hit(r["nie"], x["name"]):
                continue
            pid = "p" + os.urandom(4).hex()
            t = rollen.get(k) or {}
            d[pid] = {"id": pid, "name": x["name"][:NAME_LEN], "welt": welt, "karte": {f: list(v) for f, v in (x.get("karte") or {}).items()},
                      "wesen": dict(x.get("wesen") or {}), "rolle": t.get("rolle", "")[:TEIL_LEN], "ziel": t.get("ziel", "")[:TEIL_LEN],
                      **{f: x[f] for f in ("geschlecht", "alter") if x.get(f)},   # the card's, the catalog picture reads the same
                      "stimme": _voice(rd, x, stimmen.get(k[:40])), "haltung": {h: v for h, v in (x.get("haltung") or {}).items() if isinstance(v, int)},
                      "treffen": 1, "made": now, "t": now, "stand": "runde", **({"gesicht": {"n": g["n"]}} if g else {})}
            names.add((welt, k))
            album.met(dm, rd, pid)
            n += 1
        while len(d) > MAX:                     # the oldest from a round go first, the admin's own stay
            old = min(d.values(), key=lambda v: (v.get("stand") == "eigen", v.get("t", 0)))
            d.pop(old["id"])
        _save(d)
    if n:
        _day.bump("neu", n)
    print(f"dungeon: personen | gesammelt | {n} neu", flush=True)
    return n


def _voice(rd, x, kept):
    """The voice the catalog keeps: the traits heard, with the card's gender and age (one source with the portrait); {}
    when it never spoke and the card has neither."""
    t = dict(kept or {})
    if t or x.get("geschlecht") or x.get("alter"):
        t = dict(stimmen._of(rd, x["name"]), **{k: v for k, v in t.items() if k not in stimmen.PANEL})
    return t


def portraits():
    """The portraits the catalog names (dungeon_gesicht.keep keeps them from the sweep)."""
    return {(x.get("gesicht") or {}).get("n") for x in load().values()} - {None, ""}


# ---------------------------------------------------------------- a person who fights (Personen-Katalog 4)
KAEMPFER = 2               # people of the scene the panel offers as foes at most
VORLAGE = (                # words of the occupation (the card's English text) → templates of the bestiary, strongest first
    (("knight",), ("gladiator", "ritter", "veteran", "wache")),
    (("mercenary", "bounty hunter", "gunner", "adventurer", "leader"), ("gladiator", "veteran", "banditenhauptmann", "schlaeger", "wache")),
    (("guard", "watch", "lawkeeper"), ("wache",)),
    (("scout", "hunter", "forester", "explorer", "guide"), ("spaeher", "wache")),
    (("thief", "smuggler", "outcast", "vagrant", "scavenger"), ("banditenhauptmann", "bandit")),
    (("investigator", "agent", "spy", "courier"), ("assassine", "spion", "bandit")),
    (("priest", "mystic", "pilgrim", "healer", "witch"), ("akolyth", "kultist", "wache")),   # no „priester“: its power are spells
    (("diplomat", "noble"), ("adliger", "wache")))
SONST = ("wache",)         # any other occupation, but not one of NICHT_KAEMPFER (Review 27.10. Paket 8, Z8: never as a guard)
NICHT_KAEMPFER = ("artisan", "bard", "bell ringer", "butler", "cabin boy", "cartographer", "clockmaker", "farmer", "fisher", "forager",
                  "herder", "historian", "innkeeper", "lamplighter", "performer", "researcher", "scholar", "cook", "shipwright",
                  "technician", "trader", "traveller", "engineer", "pilot", "navigator", "ai", "child")
# a person counts in the fight's budget and gives experience by its template's fight experience (ep_kampf, Review 27.10.
# Paket 11.6, else its experience) times this weight (people come with their guards), measured
# with the balance bench (dungeon_pruefstand, people only): a group wins 70 to 90 per cent at „mittel“ on average, every
# level and group size within SPANNE (few templates, so single cells swing more than with the whole bestiary)
GEWICHT = {"adliger": 0.87, "akolyth": 1.04, "assassine": 0.75, "bandit": 1.68, "banditenhauptmann": 0.89, "gladiator": 0.85,
           "kultist": 1.12, "ritter": 0.94, "schlaeger": 1.15, "spaeher": 1.29, "spion": 1.21, "veteran": 0.93, "wache": 1.63}
SPANNE = (50, 98)
HALB = 0.5                 # a person's template nearest to this share of the budget (Review 27.10. B14)
FREUND = 2                 # a person at least this friendly to a hero at the table never comes as a foe
AUS = {"besiegt": ("{} wurde im Kampf besiegt.", "{} was beaten in the fight."), "geflohen": ("{} ist aus dem Kampf geflohen.", "{} fled the fight.")}


def templates():
    """Every template a person may fight with."""
    return sorted({i for _, ids in VORLAGE for i in ids} | set(SONST))


def weighted(g):
    """A template as a person fights with it: its fight experience (dungeon_bestiarium.ep_kampf) times GEWICHT, for the
    budget and the reward alike; its experience in the bestiary stays."""
    return dict(g, ep_kampf=max(1, round(best.ep_kampf(g) * GEWICHT.get(g["id"], 1.0))))


def _row(x):
    """The templates of a person's occupation (VORLAGE, else SONST); None for one of NICHT_KAEMPFER."""
    beruf = ((x.get("karte") or {}).get("beruf") or ["", ""])[1].lower()
    row = next((ids for words, ids in VORLAGE if any(w in beruf for w in words)), SONST)
    if row is SONST and any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", beruf) for w in NICHT_KAEMPFER):
        return None                              # a farmer, a bard, a ship's AI never fights as a guard
    return row


def template(dm, r, rd, x, b):
    """The bestiary entry a person fights with: by its occupation's row (nearest); None when none fits or the occupation is
    one of NICHT_KAEMPFER. The model never gives values."""
    row = _row(x)
    return nearest(dm, r, rd.get("welt", ""), row, b) if row else None


def nearest(dm, r, welt, row, b):
    """Of a row the template that plays in the world, fits the encounter's budget b (it counts in it like any foe) and
    is nearest to HALB of it (Review 27.10. B14, never simply the strongest); weighted. Also the balance bench's."""
    import dungeon_kampf as kampf
    by = dm._by(r, "gegner")
    fit = [weighted(by[i]) for i in dict.fromkeys(tuple(row) + SONST) if i in by and kampf.plays_in(r, by[i], welt)
           and best.ep_kampf(weighted(by[i])) <= b * kampf.SCHWER]
    return min(fit, key=lambda g: (abs(best.ep_kampf(g) - HALB * b), -best.ep_kampf(g)), default=None)


def escort(dm, r, rd, g):
    """A fighting person's guards (Review 27.10. B14, guards); None for a person without a row."""
    x = (rd.get("nsc") or {}).get(g.get("person") or "")
    row = _row(x) if x else None
    return guards(dm, r, rd.get("welt", ""), row) if row else None


def guards(dm, r, welt, row):
    """The weakest template of a row that plays in the world, as plain foes (dungeon_kampf.fill counts them up to the
    band); weighted. Also the balance bench's."""
    import dungeon_kampf as kampf
    by = dm._by(r, "gegner")
    fit = [weighted(by[i]) for i in dict.fromkeys(tuple(row) + SONST) if i in by and kampf.plays_in(r, by[i], welt)]
    return min(fit, key=lambda w: (best.ep_kampf(w), w["id"]), default=None)


def fighters(dm, r, rd, held, b):
    """For dungeon_kampf.offer: up to KAEMPFER people of the scene as foes with their template's values and their own
    name (offer id „p:<name>“); never in a fight, never one beaten or fled before, never a friend of a hero here."""
    if not on(rd) or rd.get("kampf"):
        return []
    heroes = {h["name"].lower() for h in held}
    out = []
    for k in nsc.scene(rd):
        x = rd["nsc"][k]
        if x.get("kampf") or x.get("alter") == "kind" \
                or any(isinstance(v, int) and v >= FREUND for h, v in (x.get("haltung") or {}).items() if h in heroes):
            continue                             # a child never fights (Review 27.10. Z5)
        g = template(dm, r, rd, x, b)
        if g:
            out.append(dict(g, name=[x["name"], x["name"]], person=k, oid=("p:" + k)[:40]))
    return out[:KAEMPFER]


def after_fight(dm, rd, k):
    """From dungeon_kampf.end: a person beaten or fled is marked (no second fight in the round) and goes into the chronicle."""
    for g in k.get("gegner") or []:
        x = (rd.get("nsc") or {}).get(g.get("person") or "")
        if x is not None and g.get("aus") in AUS:
            x["kampf"] = g["aus"]
            nsc.note(rd, AUS[g["aus"]][0].format(x["name"]), AUS[g["aus"]][1].format(x["name"]))
            _day.bump("gekaempft")
            print(f"dungeon: personen | kampf | {g['aus']}", flush=True)


# ---------------------------------------------------------------- the admin's part of the rules
def _clean(dm, x, n):
    return dm.plain(x, n) if isinstance(x, str) else ""


def check(dm, r, e, have):
    """A person the admin wrote, by fixed rules: (the clean entry, German sentences of what is wrong)."""
    err = []
    e = e if isinstance(e, dict) else {}
    name = _clean(dm, e.get("name"), NAME_LEN)
    welten = [w["id"] for w in r["welten"]]
    welt = e.get("welt") if e.get("welt") in welten else None
    if len(name) < 2:
        err.append(f"name: 2 bis {NAME_LEN} Zeichen")
    if not welt:
        err.append("welt: eine der Welten (" + ", ".join(welten) + ")")
    karte = {}
    for f, v in (e.get("karte") if isinstance(e.get("karte"), dict) else {}).items():
        v = [v, v] if isinstance(v, str) else v
        if f not in nsc.FELDER or not isinstance(v, list) or len(v) != 2:
            err.append(f"karte.{f}: eines von {', '.join(nsc.FELDER)} mit [Deutsch, Englisch]")
            continue
        v = [_clean(dm, t, FELD_LEN) for t in v]
        if all(v):
            karte[f] = v
    wesen = {}
    for k, v in (e.get("wesen") if isinstance(e.get("wesen"), dict) else {}).items():
        if k not in nsc.WESEN or not isinstance(v, int) or isinstance(v, bool) or not nsc.HALTUNG[0] <= v <= nsc.HALTUNG[1]:
            err.append(f"wesen.{k}: eines von {', '.join(nsc.WESEN)} mit einer Zahl von −3 bis 3")
            continue
        wesen[k] = v
    out = {"name": name, "welt": welt, "karte": karte, "wesen": wesen, "rolle": _clean(dm, e.get("rolle"), TEIL_LEN),
           "ziel": _clean(dm, e.get("ziel"), TEIL_LEN)}
    if "stimme" in e:                      # left out: the person keeps its voice
        try:
            out["stimme"] = stimmen.clean(e["stimme"])
        except ValueError:
            err.append("stimme: {} (nach dem Namen) oder je eines von " + ", ".join(f"{k} ({'/'.join(stimmen.data()['npc'][k])})" for k in stimmen.MERKMALE))
    if dm.word_hit(r["nie"], _text(r, out)):
        err.append("Ein Wort steht in „nie“")
    if welt and any(v.get("welt") == welt and v["name"].lower() == name.lower() for v in have):
        err.append("name: diese Welt hat schon eine Person mit diesem Namen")
    return (None, err) if err else (out, [])


def change(was, i, eintrag=None, now=None):
    """The admin sets („setzen“, a new id makes a new person), gives one a voice („stimme“, eintrag {"stimme"}: only
    that, the person stays as it came) or deletes („zurueck“, „aus“) one person."""
    import dungeon as dm
    r = dm.rules()
    with _lock:
        d = load()
        if was == "setzen":
            if not _ID.match(str(i)) or not isinstance(eintrag, dict) or str(eintrag.get("id")) != str(i):
                print("dungeon: personen | abgelehnt | id", flush=True)
                raise ValueError(["id: Kleinbuchstaben, Ziffern und _ (höchstens 40)"])
            e, err = check(dm, r, eintrag, [v for k, v in d.items() if k != i])
            if err:
                print(f"dungeon: personen | abgelehnt | {len(err)} fehler", flush=True)
                raise ValueError(err)
            if i not in d and len(d) >= MAX:
                print("dungeon: personen | abgelehnt | voll", flush=True)
                raise ValueError([f"höchstens {MAX} Personen"])
            now = int(time.time() if now is None else now)
            d[i] = dict(d.get(i) or {"id": i, "stimme": {}, "haltung": {}, "treffen": 0, "made": now}, **e, t=now, stand="eigen")
            _day.bump("geaendert")
        elif was == "stimme":
            if i not in d:
                print("dungeon: personen | abgelehnt | fehlt", flush=True)
                raise LookupError("eintrag")
            try:
                d[i]["stimme"] = stimmen.clean((eintrag or {}).get("stimme") if isinstance(eintrag, dict) else None)
                if d[i]["stimme"]:                   # the chosen voice sets its one gender and age (Review 27.10. Paket 10)
                    for f in ("geschlecht", "alter"):
                        d[i].pop(f, None)
                    d[i].update(_fixed(d[i]))
            except ValueError:
                print("dungeon: personen | abgelehnt | stimme", flush=True)
                raise ValueError(["stimme"])
            _day.bump("stimme")
        elif was in ("zurueck", "aus"):
            if i not in d:
                print("dungeon: personen | abgelehnt | fehlt", flush=True)
                raise LookupError("eintrag")
            d.pop(i)
            _day.bump("geloescht")
        else:
            print("dungeon: personen | abgelehnt | was", flush=True)
            raise ValueError(["was"])
        _save(d)
    print(f"dungeon: personen | {was}", flush=True)


def _sex_name(g, li):
    import dungeon as dm
    return dm.GESCHLECHT[g][0][li] if g in dm.GESCHLECHT else ""


def view(lang="de"):
    """{"teil", "zeilen", "eintraege"} for the rules page: every person with its card (wish and secret too: the admin),
    traits, role, goal, whom it knows and how often it was met."""
    import dungeon as dm
    li = 1 if lang == "en" else 0
    r = dm.rules()
    welten = {w["id"]: w["name"][li] for w in r["welten"]}
    rows, entries = [], {}
    import dungeon_dingbild                      # each person's face (Dominik 2026-10-27 „portrait fehlt bei den npc“)
    have, neu = dungeon_dingbild.files(), set(dungeon_dingbild.candidates())
    for i, x in sorted(load().items(), key=lambda kv: kv[1]["name"].lower()):
        k = x.get("karte") or {}
        werte = [[FELD[f][li], k[f][li]] for f in nsc.FELDER if f in k]
        werte += [[n, w] for n, w in ((("Geschlecht", "Gender")[li], _sex_name(x.get("geschlecht"), li)),
                                      (("Alter", "Age")[li], nsc.ALTER_WORT.get(x.get("alter"), ("", ""))[li])) if w]
        wesen = nsc.trait_words(x, li)
        if wesen:
            werte.append([("Wesen", "Traits")[li], ", ".join(wesen)])
        werte += [[n, x[f]] for f, n in (("rolle", ("Rolle", "Role")[li]), ("ziel", ("Ziel", "Goal")[li])) if x.get(f)]
        werte.append([("Stimme", "Voice")[li], stimmen.words(stimmen.of_name(x["name"], x.get("stimme")), li)
                      + ("" if x.get("stimme") else (" (nach dem Namen)", " (by the name)")[li])])
        if x.get("haltung"):
            werte.append([("Kennt", "Knows")[li], ", ".join(f"{h.title()}: {nsc.word(v, li)}" for h, v in sorted(x["haltung"].items()))])
        rows.append({"id": i, "name": x["name"], "zeichen": "👤", "art": "", "stand": x.get("stand", "runde"), "welten": [x.get("welt")],
                     "zeile": " · ".join(t for t in ((k.get("beruf") or ["", ""])[li], welten.get(x.get("welt"), ""),
                                                     (f"{x.get('treffen', 0)}× getroffen", f"met {x.get('treffen', 0)}×")[li]) if t),
                     "werte": werte})
        dungeon_dingbild.person_row(r, x, rows[-1], have, neu)
        entries[i] = {"id": i, "name": x["name"], "welt": x.get("welt"), "rolle": x.get("rolle", ""), "ziel": x.get("ziel", ""),
                      "karte": k, "wesen": x.get("wesen") or {}, "stimme": dict(x.get("stimme") or {}),
                      "stimme_jetzt": stimmen.of_name(x["name"], x.get("stimme"))}
    return {"teil": "personen", "zeilen": rows, "eintraege": entries, "bilder_an": dungeon_dingbild.person_on(), "neu": True, "stimmwahl": stimmen.choices(li),
            "weltfilter": [{"id": w, "name": n} for w, n in welten.items()]}


def for_live():
    """Numbers only: people in the catalog; new, met again, recognised, fought, changed, deleted, brought by a story,
    voices set today."""
    t = _day.counts()
    return dict({k: t[k] for k in ("neu", "wieder", "erkannt", "gekaempft", "geaendert", "geloescht", "geschichte", "stimme")}, personen=len(load()))
