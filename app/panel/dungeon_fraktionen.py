"""KI-Dungeon-Master: Fraktionen mit Uhren (Tabletop-Punkt 7 of 2026-10-25, Dominik „ich hätte gerne alle punkte
umgesetzt“; clocks with fields are a common method of tabletop play, own code).

Every group of the chapter's truth (dungeon_erzaehler: wahrheit.gruppen, name and what it wants) becomes a faction with
a clock of 4, 6 or 8 fields; the host adds own factions (up to FRAKTIONEN_MAX in all), changes what they want and the
fields, turns a clock by hand or takes a faction away. Between told turns the panel rolls each running clock with a d6
(UHR_WURF or more: one field). The narration reports when the heroes help or hinder a faction (story "fraktionen"),
the panel turns that clock one field by fixed rules: only a known faction named in the narration, once per faction and
turn. A full clock changes the world: a line in the feed (and in the chronicle while it runs), the model gets it once as
data (fraktion_voll) with the fixed rule to tell it, and the faction holds the group's place on the map then
(occupied: the hook for the map thread). The table sees a faction's clock once the narration has named it, never what
it wants (host and model only). Only while „Fraktionen mit Uhren“ is allowed for the round's host (features
"dungeonfraktionen"). The fields:

    rd["fraktionen"]   {name.lower(): {"name", "will", "felder": 4|6|8, "stand": 0..felder, "bekannt": bool,
                        "voll": turn | None, "ort": the map's place as text (dungeon.where) | None, "eigen": bool}}
    rd["fraktion_neu"] [name.lower()]   the clocks filled after the last told turn (for the next narration)
Both go on in the next chapter.
"""
import random

FELDER = (4, 6, 8)
FELDER_EIGEN = 6           # an own faction of the host without a choice
FRAKTIONEN_MAX = 6
UHR_WURF = 5               # a d6 at or above this turns a running clock one field between told turns
AENDERUNGEN_MAX = 2        # factions one narration may report
NAME_LEN = 30
WILL_LEN = 80
WIRKUNG = {"hilft": 1, "stoert": -1}
ARTIKEL = ("der ", "die ", "das ", "den ", "dem ", "des ", "the ")   # „Die Rabengilde“ is named as „der Rabengilde“ too

SCHEMA = {"type": "array", "maxItems": AENDERUNGEN_MAX, "items": {"type": "object", "additionalProperties": False,
          "required": ["name", "wirkung"], "properties": {"name": {"type": "string", "maxLength": NAME_LEN + 10},
                                                          "wirkung": {"type": "string", "enum": list(WIRKUNG)}}}}
AUFGABE = {
    "de": (f" Die Gruppen in fraktionen verfolgen, was sie wollen, auch ohne die Helden; ihre Uhr zeigt, wie weit sie "
           f"sind. In fraktionen meldest du höchstens {AENDERUNGEN_MAX} Gruppen, die diese Erzählung beim Namen nennt und "
           "deren Ziel eine Handlung der Helden spürbar näher bringt (hilft) oder behindert (stoert). fraktion_voll nennt, "
           "wer sein Ziel gerade erreicht hat: erzähle, wie sich die Welt dadurch ändert."),
    "en": (f" The groups in fraktionen pursue what they want, also without the heroes; their clock shows how far they "
           f"are. In fraktionen report at most {AENDERUNGEN_MAX} groups this narration names whose goal an action of the "
           "heroes clearly brings closer (hilft) or hinders (stoert). fraktion_voll names who has just reached its goal: "
           "tell how the world changes by it."),
}


def on(rd):
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonfraktionen", rd["owner"])


def _all(rd):
    return rd.setdefault("fraktionen", {})


def named(k, low):
    """Whether a narration (in small letters) names the faction k: by its name, or without its article."""
    return k in low or next((k[len(a):] for a in ARTIKEL if k.startswith(a)), "\0") in low


def sync(rd, rng=None):
    """Every group of the truth becomes a faction with a clock the panel rolls (4, 6 or 8 fields), up to
    FRAKTIONEN_MAX; returns how many are new."""
    rng = rng or random
    fr, n = _all(rd), 0
    for g in (rd.get("wahrheit") or {}).get("gruppen") or []:
        k = g["name"].lower()
        if k in fr or len(fr) >= FRAKTIONEN_MAX:
            continue
        fr[k] = {"name": g["name"], "will": g.get("will") or "", "felder": rng.choice(FELDER), "stand": 0,
                 "bekannt": False, "voll": None, "ort": None, "eigen": False}
        n += 1
    return n


def _note(rd, de, en):
    import dungeon_nsc as nsc
    if nsc.on(rd):                     # the chronicle runs with „NSC-Gedächtnis und Chronik“
        nsc.note(rd, de, en)


def turn(dm, rd, k, schritt):
    """One clock a step (+1 forwards, -1 back), within 0 and its fields. A clock that becomes full: a line in the
    feed and the chronicle, the group's place on the map, the next narration hears it (fraktion_neu); one turned back
    from full runs again. Returns the new state or None when nothing moved."""
    x = _all(rd)[k]
    neu = max(0, min(x["felder"], x["stand"] + schritt))
    if neu == x["stand"]:
        return None
    x["stand"] = neu
    if neu >= x["felder"] and x["voll"] is None:
        x.update(voll=rd.get("zug", 0), bekannt=True, ort=dm.where(rd).get("ort"))
        rd["fraktion_neu"] = (rd.get("fraktion_neu") or []) + [k]
        dm._log(rd, "fraktion", name=x["name"], was="voll", stand=neu, felder=x["felder"])
        _note(rd, f"Ziel erreicht: {x['name']}.", f"Goal reached: {x['name']}.")   # one form for every name (2026-10-28)
        dm._day.bump("fraktion_voll")
    elif neu < x["felder"] and x["voll"] is not None:
        x.update(voll=None, ort=None)
    return neu


def progress(dm, rd, rng=None):
    """Between told turns every running clock rolls a d6; UHR_WURF or more turns it a field. Returns (moved, full)."""
    rng = rng or random
    weiter = voll = nichts = 0
    for k, x in _all(rd).items():
        if x["voll"] is not None:
            continue
        if rng.randint(1, 6) < UHR_WURF:
            nichts += 1
            continue
        weiter += 1
        turn(dm, rd, k, 1)
        voll += x["voll"] is not None
    if weiter:
        dm._day.bump("fraktion_weiter", weiter)
    print(f"dungeon: fraktion | uhren | {weiter} weiter | {voll} voll | {nichts} nichts", flush=True)
    return weiter, voll


def check(rd, obj, text):
    """The narration's faction changes by fixed rules: a known faction named in the narration, once each."""
    if not on(rd) or not isinstance(obj, list):
        return []
    fr, low, out = _all(rd), text.lower(), []
    for x in obj[:AENDERUNGEN_MAX]:
        if not isinstance(x, dict):
            continue
        k = str(x.get("name") or "").strip().lower()
        if k in fr and named(k, low) and x.get("wirkung") in WIRKUNG and k not in {c["name"] for c in out}:
            out.append({"name": k, "schritt": WIRKUNG[x["wirkung"]]})
    return out


def learn(dm, rd, story, rng=None):
    """After a told turn: factions for new groups of the truth, the clocks the narration named become known, the
    narration's changes, then the panel's roll for every running clock."""
    if not on(rd):
        return
    rd["fraktion_neu"] = []                # told now: the next narration hears only what fills from here on
    neu = sync(rd, rng)
    if neu:
        print(f"dungeon: fraktion | neu | {neu}", flush=True)
    low = str((story or {}).get("text") or "").lower()
    for k, x in _all(rd).items():
        if not x["bekannt"] and named(k, low):
            x["bekannt"] = True
            print("dungeon: fraktion | bekannt", flush=True)
    for c in (story or {}).get("fraktionen") or []:     # checked in dungeon.check_story (check)
        x = _all(rd).get(c["name"])
        if not x:
            print("dungeon: fraktion | verworfen | weg", flush=True)
        elif c["schritt"] > 0 and x["voll"] is not None:
            print("dungeon: fraktion | verworfen | voll", flush=True)
        elif turn(dm, rd, c["name"], c["schritt"]) is None:
            print("dungeon: fraktion | verworfen | grenze", flush=True)
        else:
            if x["voll"] is None:
                dm._log(rd, "fraktion", name=x["name"], was="hilft" if c["schritt"] > 0 else "stoert", stand=x["stand"], felder=x["felder"])
            dm._day.bump("fraktion_helden")
            print(f"dungeon: fraktion | helden | {'hilft' if c['schritt'] > 0 else 'stoert'}", flush=True)
    if story:
        progress(dm, rd, rng)


def host(dm, r, rd, b):
    """The host's change: {name, will?, felder?, schritt?: 1|-1, weg?: true}. A new name adds an own faction. Raises
    PermissionError("fraktionen aus"), ValueError("fraktion")/("wortliste"), OverflowError("fraktionen voll")."""
    if not on(rd):
        raise PermissionError("fraktionen aus")
    name = dm.plain(b.get("name"), NAME_LEN)
    will = dm.plain(b.get("will"), WILL_LEN) if "will" in b else None
    felder, schritt = b.get("felder"), b.get("schritt")
    if len(name) < 2 or felder is not None and felder not in FELDER or schritt is not None and schritt not in (1, -1) \
            or "weg" in b and b["weg"] is not True:
        raise ValueError("fraktion")
    if dm.bad_words(r, rd, name + " " + (will or "")):
        raise ValueError("wortliste")
    fr, k = _all(rd), name.lower()
    if b.get("weg"):
        if k not in fr:
            raise ValueError("fraktion")
        del fr[k]
        rd["fraktion_neu"] = [x for x in rd.get("fraktion_neu") or [] if x != k]
        return "weg"
    if k not in fr:
        if len(fr) >= FRAKTIONEN_MAX:
            raise OverflowError("fraktionen voll")
        fr[k] = {"name": name, "will": will or "", "felder": felder or FELDER_EIGEN, "stand": 0, "bekannt": False,
                 "voll": None, "ort": None, "eigen": True}
        return "neu"
    x = fr[k]
    if will is not None:
        x["will"] = will
    if felder is not None and felder != x["felder"]:
        x["felder"] = felder
        x["stand"] = min(x["stand"], felder)
        if x["stand"] < felder and x["voll"] is not None:
            x.update(voll=None, ort=None)
    if schritt is not None and turn(dm, rd, k, schritt) is None:
        return "grenze"
    return "dreh" if schritt is not None else "geaendert"


def facts(rd):
    """For the model, as data: every faction with what it wants and its clock; the clocks filled since the last
    narration once. {} when off or none."""
    if not on(rd) or not _all(rd):
        return {}
    import textnorm
    fr = _all(rd)
    out = {"fraktionen": [{"name": x["name"], **({"will": textnorm.defuse(x["will"])} if x["will"] else {}),
                           "uhr": f"{x['stand']}/{x['felder']}", **({"am_ziel": True} if x["voll"] is not None else {})}
                          for x in fr.values()]}
    voll = [fr[k] for k in rd.get("fraktion_neu") or [] if k in fr]
    if voll:
        out["fraktion_voll"] = [{"name": x["name"], **({"will": textnorm.defuse(x["will"])} if x["will"] else {})} for x in voll]
    return out


def task(rd, lang):
    return AUFGABE[lang] if on(rd) and _all(rd) else ""


def view(rd, host):
    """The clocks the table knows (name, fields, state, full), for every seat; the host's view also has every faction
    with what it wants (fraktionen_geheim, dungeon_sicht.NUR_GASTGEBER). None when off."""
    if not on(rd):
        return None, None
    fr = _all(rd)
    out = {"uhren": [{"name": x["name"], "felder": x["felder"], "stand": x["stand"], "voll": x["voll"] is not None}
                     for x in fr.values() if x["bekannt"]]}
    geheim = {"max": FRAKTIONEN_MAX, "felder": list(FELDER), "name_max": NAME_LEN, "will_max": WILL_LEN,
              "alle": [{"name": x["name"], "will": x["will"], "felder": x["felder"], "stand": x["stand"], "bekannt": x["bekannt"],
                        "voll": x["voll"] is not None, "eigen": x["eigen"]} for x in fr.values()]} if host else None
    return out, geheim


def occupied(rd):
    """The hook for the map thread: {place (the index on the map as text, dungeon.where): faction name} of the full
    clocks that hold a place."""
    return {x["ort"]: x["name"] for x in (rd.get("fraktionen") or {}).values() if x.get("voll") is not None and x.get("ort") is not None}


def for_live(rs):
    return {"fraktionen": sum(len(v.get("fraktionen") or {}) for v in rs),
            "fraktionen_voll": sum(1 for v in rs for x in (v.get("fraktionen") or {}).values() if x.get("voll") is not None)}


def keep(rd):
    """What the next chapter takes over (with dungeon_nsc.keep)."""
    return {"fraktionen": rd["fraktionen"]} if rd.get("fraktionen") else {}


def carry(kampagne):
    return {"fraktionen": kampagne["fraktionen"]} if isinstance(kampagne.get("fraktionen"), dict) else {}
