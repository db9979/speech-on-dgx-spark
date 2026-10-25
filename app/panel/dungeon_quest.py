"""KI-Dungeon-Master: Quest-Gegenstände (Punkt 15 of the review of 2026-10-24, Dominik „alles umsetzten“, 12:33 „echte
Quest-Gegenstände“).

A quest thing is a named thing the story needs (a key, a map, a seal): no weight, never for sale, passed from hero to
hero, its own sign (ZEICHEN). It comes three ways, always checked by fixed rules:

    the story planner   an act may name one (dungeon.check_plan, act field "ding"); it lies in the scene while the act
                        runs (act_thing), until a hero takes it
    the map             the map thread lays one at a place of the map or a vault (dungeon.quest_legen)
    the narration       the model reports at most one find per turn (story "quest_fund"); the panel takes it only when
                        the narration names it, its name passes the word lists, and the round has fewer than QUEST_MAX

A thing lying where the group stands goes to the hero whose action names it (pickups, before the narration, so the
model hears it as data: quest_genommen); a hero gives it on or puts it down (hero). Doors and ways of the map open only
when an action names the thing and the group carries it (the map thread asks dungeon.quest_haben and
dungeon.quest_genannt); a thing used up goes with a line in the feed (dungeon.quest_verbrauchen). A carrier who leaves
the table or dies drops it where the group stands. Players see what the group carries and what lies here once seen
(named by a narration, or taken); the host sees every thing with its place (quest_geheim, dungeon_sicht.NUR_GASTGEBER).
Only while „Quest-Gegenstände“ is allowed for the round's host (features "dungeonquest").

    rd["quest"]      {qid: {"q", "name": [de, en], "info", "wer": pid | None, "hid": the carrier's hero | None,
                     "ort": place id, "gesehen": bool, "von": "plan" | "karte" | "modell", "zug"}}   place id: "" = the
                     scene wherever the group is, else dungeon.where's place or a place id of the map thread
                     (dungeon_karte.quest_orte)
    rd["quest_weg"]  [qid]   used up: never laid again
The next chapter takes the carried things (with their hero: hid, back in the hand once the hero sits down again) and
the used ones; a thing left lying stays behind.
"""
import re

NAME_LEN = 40
INFO_LEN = 120
QUEST_MAX = 12             # quest things of a round at once
ORT_LEN = 40
ID = re.compile(r"q_[a-z0-9_]{1,24}")
ZEICHEN = "✦"
VON = ("plan", "karte", "modell")

SCHEMA = {"type": "array", "maxItems": 1, "items": {"type": "object", "additionalProperties": False, "required": ["wer", "name"],
          "properties": {"wer": {"type": "string", "maxLength": 40}, "name": {"type": "string", "maxLength": NAME_LEN + 10},
                         "info": {"type": "string", "maxLength": INFO_LEN + 40}}}}
AUFGABE = {
    "de": (" Besondere Dinge der Geschichte: quest_gruppe trägt die Gruppe, quest_hier liegt hier, quest_genommen hat ein "
           "Held gerade an sich genommen. Sie wiegen nichts und sind nicht zu verkaufen; erzähle sie nur so, wie die Daten "
           "sagen. Findet ein Held in deiner Erzählung einen neuen Gegenstand, den die Geschichte wirklich braucht (einen "
           "Schlüssel, eine Karte, ein Siegel), meldest du ihn in quest_fund: höchstens einen, mit seinem Namen, wer ihn "
           "findet und einem kurzen Satz; nenne ihn in der Erzählung beim Namen."),
    "en": (" Special things of the story: quest_gruppe the group carries, quest_hier lies here, quest_genommen a hero has "
           "just taken. They weigh nothing and cannot be sold; tell them only as the data says. When a hero finds a new "
           "thing in your narration that the story really needs (a key, a map, a seal), report it in quest_fund: at most "
           "one, with its name, who finds it and a short sentence; name it in the narration."),
}


def on(rd):
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonquest", rd["owner"])


def _all(rd):
    return rd.setdefault("quest", {})


def _li(rd):
    return 1 if rd.get("lang") == "en" else 0


def _name(rd, x):
    return x["name"][_li(rd)] or x["name"][0]


def _carrier(dm, rd, pid):
    """The seat's hero when it may carry: seated and not dead."""
    p = rd["plaetze"].get(pid) if pid else None
    return p["held"] if p and p.get("held") and not p["held"].get("tot") and not p.get("wartet") else None


def _who(dm, rd, x):
    """The seat that carries the thing: its seat, or (a thing from the last chapter) the seat of its hero; None."""
    if x.get("wer"):
        return x["wer"] if _carrier(dm, rd, x["wer"]) else None
    if x.get("hid"):
        return next((pid for pid, p in dm.seated(rd) if p["held"].get("hid") == x["hid"] and _carrier(dm, rd, pid)), None)
    return None


def _give(rd, x, pid):
    x.update(wer=pid, hid=(rd["plaetze"][pid].get("held") or {}).get("hid") if pid else None)


def here(dm, rd):
    """The place ids where the group stands: the scene (""), the map's place and, when the map thread has it, the
    places of a vault (dungeon_karte.quest_orte)."""
    import dungeon_karte
    out = {""}
    w = dm.where(rd).get("ort")
    if w is not None:
        out.add(w)
    more = getattr(dungeon_karte, "quest_orte", None)
    if more:
        out |= {str(x) for x in more(rd) or ()}
    return out


def _spot(dm, rd):
    """Where a thing put down now lies: the vault's or map's place, else the scene."""
    import dungeon_karte
    more = getattr(dungeon_karte, "quest_orte", None)
    first = next(iter(more(rd) or ()), None) if more else None
    return str(first) if first is not None else dm.where(rd).get("ort") or ""


def named(rd, x, text):
    """Whether a text names the thing: one of its names (small letters), also without its article."""
    import dungeon_fraktionen as fraktionen
    low = " ".join(str(text or "").lower().split())
    return any(n and fraktionen.named(n, low) for n in {" ".join(m.lower().split()) for m in x["name"]})


def _clean_name(dm, ding):
    n = ding.get("name")
    pair = list(n) if isinstance(n, (list, tuple)) and len(n) == 2 else [n, n]
    pair = [dm.plain(p, NAME_LEN) for p in pair]
    pair[1] = pair[1] or pair[0]
    return pair if all(len(p) >= 2 for p in pair) else None


def legen(dm, r, rd, ort_id, ding, von="karte"):
    """A quest thing laid at a place (the map thread, the story planner): ding = {id: q_…, name: [de, en] or text,
    info?}. Returns its id; the same id again changes nothing (a vault filled anew). Raises ValueError("quest") for a
    bad id, name or place, ValueError("wortliste") for a refused word, OverflowError("quest voll"), and
    PermissionError("quest aus") while off."""
    if not on(rd):
        print("dungeon: quest | legen | aus", flush=True)
        raise PermissionError("quest aus")
    ding = ding if isinstance(ding, dict) else {}
    q, ort = ding.get("id"), "" if ort_id is None else ort_id
    name = _clean_name(dm, ding)
    if not isinstance(q, str) or not ID.fullmatch(q) or not isinstance(ort, str) or len(ort) > ORT_LEN or not name or von not in VON:
        print("dungeon: quest | legen | eingabe", flush=True)
        raise ValueError("quest")
    if q in _all(rd) or q in (rd.get("quest_weg") or []):
        print("dungeon: quest | legen | schon da", flush=True)
        return q
    info = dm.plain(ding.get("info"), INFO_LEN)
    if dm.bad_words(r, rd, " ".join(name + [info])):
        print("dungeon: quest | legen | wortliste", flush=True)
        raise ValueError("wortliste")
    if len(_all(rd)) >= QUEST_MAX:
        print("dungeon: quest | legen | voll", flush=True)
        raise OverflowError("quest voll")
    _all(rd)[q] = {"q": q, "name": name, "info": info, "wer": None, "hid": None, "ort": ort, "gesehen": False, "von": von, "zug": rd.get("zug", 0)}
    print(f"dungeon: quest | gelegt | {von}", flush=True)
    return q


def haben(dm, rd, qid):
    """Who carries the thing: the seat (pid) of a hero at the table, or None."""
    x = _all(rd).get(qid) if on(rd) else None
    return _who(dm, rd, x) if x else None


def genannt(rd, qid, text):
    """Whether a text (an action) names the thing (the map thread's doors)."""
    x = _all(rd).get(qid)
    return bool(x) and named(rd, x, text)


def verbrauchen(dm, rd, qid, pid):
    """The thing is used up (a door opened with it): gone, with a line in the feed. False when that hero does not
    carry it."""
    if haben(dm, rd, qid) != pid or not pid:
        print("dungeon: quest | verbrauchen | nicht", flush=True)
        return False
    x = _all(rd).pop(qid)
    rd["quest_weg"] = (rd.get("quest_weg") or []) + [qid]
    dm._log(rd, "quest", was="verbraucht", name=_name(rd, x), wer=rd["plaetze"][pid]["held"]["name"])
    dm._day.bump("quest_verbraucht")
    print("dungeon: quest | verbraucht", flush=True)
    return True


def _lying(dm, rd):
    at = here(dm, rd)
    return [x for x in _all(rd).values() if not x.get("wer") and not x.get("hid") and x["ort"] in at]


def pickups(dm, rd):
    """[(qid, pid)]: the things lying where the group stands that an action of this turn names, each to the first
    hero (in seat order) who names it. Fixed rule, nothing from the model."""
    if not on(rd) or not _all(rd):
        return []
    out, taken = [], set()
    for pid, _p in dm.seated(rd):
        a = (rd.get("offen") or {}).get(pid) or {}
        if not a.get("text") or not _carrier(dm, rd, pid):
            continue
        for x in _lying(dm, rd):
            if x["q"] not in taken and named(rd, x, a["text"]):
                out.append((x["q"], pid))
                taken.add(x["q"])
    return out


def _drop_lost(dm, rd):
    """A carrier who left the table or died: the thing lies where the group stands now. A thing of the last chapter
    goes back into its hero's hand once the hero sits down."""
    for x in _all(rd).values():
        if x.get("wer") and not _carrier(dm, rd, x["wer"]):
            _give(rd, x, None)
            x.update(ort=_spot(dm, rd), gesehen=True)
            print("dungeon: quest | liegt | traeger weg", flush=True)
        elif not x.get("wer") and x.get("hid") and _who(dm, rd, x):
            _give(rd, x, _who(dm, rd, x))
            print("dungeon: quest | zurueck", flush=True)


def act_thing(dm, r, rd):
    """The running act's thing of the story planner lies in the scene (once; never again once used up)."""
    if not on(rd):
        return
    akte = (rd.get("plan") or {}).get("akte") or []
    n = rd.get("akt", 0)
    ding = akte[n].get("ding") if n < len(akte) and isinstance(akte[n], dict) else ""
    if not ding:
        return
    try:
        legen(dm, r, rd, "", {"id": f"q_akt{n + 1}", "name": ding}, "plan")
    except (ValueError, OverflowError) as e:
        print(f"dungeon: quest | akt | {str(e).split()[-1]}", flush=True)


def check(dm, r, rd, obj, text):
    """The narration's find by fixed rules: at most one, a name of 2 to NAME_LEN characters that the narration names,
    no word of the lists, not a thing the round has already, room in QUEST_MAX. [{"wer": pid | None, "name", "info"}]."""
    if not on(rd) or not isinstance(obj, list) or not obj or not isinstance(obj[0], dict):
        return []
    x = obj[0]
    name, info = dm.plain(x.get("name"), NAME_LEN), dm.plain(x.get("info"), INFO_LEN)
    probe = {"name": [name, name]}
    if len(name) < 2 or not named(rd, probe, text) or len(_all(rd)) >= QUEST_MAX:
        print("dungeon: quest | fund | verworfen", flush=True)
        return []
    if dm.bad_words(r, rd, name + " " + info) or any(name.lower() in (n.lower() for n in y["name"]) for y in _all(rd).values()):
        print("dungeon: quest | fund | verworfen", flush=True)
        return []
    wer = next((pid for pid, p in dm.seated(rd) if p["held"]["name"].lower() == str(x.get("wer") or "").strip().lower()), None)
    return [{"wer": wer if _carrier(dm, rd, wer) else None, "name": name, "info": info}]


def learn(dm, r, rd, story, take):
    """After a told turn: the things the actions took (pickups, checked again), carriers gone, the narration's find
    (to its finder, else here), the things lying here that the narration named are seen, the act's thing."""
    if not on(rd):
        return
    for q, pid in take:
        x = _all(rd).get(q)
        if x and x in _lying(dm, rd) and _carrier(dm, rd, pid):
            _give(rd, x, pid)
            x["gesehen"] = True
            dm._log(rd, "quest", was="genommen", name=_name(rd, x), wer=rd["plaetze"][pid]["held"]["name"])
            dm._day.bump("quest_genommen")
            print("dungeon: quest | genommen", flush=True)
        else:
            print("dungeon: quest | genommen | verworfen", flush=True)
    _drop_lost(dm, rd)
    for f in (story or {}).get("quest_fund") or []:       # checked in dungeon.check_story (check)
        if len(_all(rd)) >= QUEST_MAX:
            print("dungeon: quest | fund | voll", flush=True)
            continue
        q = f"q_f{rd.get('zug', 0)}"
        while q in _all(rd) or q in (rd.get("quest_weg") or []):
            q += "x"
        wer = f["wer"] if _carrier(dm, rd, f["wer"]) else None
        _all(rd)[q] = {"q": q, "name": [f["name"], f["name"]], "info": f["info"], "wer": None, "hid": None,
                       "ort": "" if wer else _spot(dm, rd), "gesehen": True, "von": "modell", "zug": rd.get("zug", 0)}
        _give(rd, _all(rd)[q], wer)
        dm._log(rd, "quest", was="gefunden", name=f["name"], wer=rd["plaetze"][wer]["held"]["name"] if wer else "")
        dm._day.bump("quest_gefunden")
        print(f"dungeon: quest | fund | {'held' if wer else 'boden'}", flush=True)
    text = str((story or {}).get("text") or "")
    for x in _lying(dm, rd):
        if not x["gesehen"] and text and named(rd, x, text):
            x["gesehen"] = True
            print("dungeon: quest | gesehen", flush=True)
    act_thing(dm, r, rd)


def hero(dm, rd, pid, b, was):
    """The hero's own move: questgeben {q, an}, questablegen {q}, questaufheben {q}. Raises ValueError("quest")."""
    if not on(rd):
        print(f"dungeon: quest | {was} | aus", flush=True)
        raise PermissionError("quest aus")
    x = _all(rd).get(b.get("q"))
    me = rd["plaetze"][pid]["held"]["name"]
    if not x:
        raise ValueError("quest")
    if was == "questgeben":
        an = b.get("an")
        if haben(dm, rd, x["q"]) != pid or an == pid or not _carrier(dm, rd, an):
            raise ValueError("quest")
        _give(rd, x, an)
        dm._log(rd, "quest", was="gegeben", name=_name(rd, x), wer=me, an=rd["plaetze"][an]["held"]["name"])
        dm._day.bump("quest_gegeben")
    elif was == "questablegen":
        if haben(dm, rd, x["q"]) != pid:
            raise ValueError("quest")
        _give(rd, x, None)
        x.update(ort=_spot(dm, rd), gesehen=True)
        dm._log(rd, "quest", was="abgelegt", name=_name(rd, x), wer=me)
    else:
        if x not in _lying(dm, rd) or not x["gesehen"]:
            raise ValueError("quest")
        _give(rd, x, pid)
        dm._log(rd, "quest", was="genommen", name=_name(rd, x), wer=me)
        dm._day.bump("quest_genommen")
    return was


def facts(dm, rd):
    """For the model, as data: what the group carries (and who), what lies here, what an action takes this turn.
    {} when off or none."""
    if not on(rd) or not _all(rd):
        return {}
    import textnorm
    take = dict(pickups(dm, rd))
    names = {pid: p["held"]["name"] for pid, p in dm.seated(rd)}
    d = lambda x: {"name": textnorm.defuse(_name(rd, x)), **({"info": textnorm.defuse(x["info"])} if x["info"] else {})}
    out = {}
    gruppe = [dict(d(x), wer=names[_who(dm, rd, x)]) for x in _all(rd).values() if _who(dm, rd, x)]
    hier = [d(x) for x in _lying(dm, rd) if x["q"] not in take]
    neu = [dict(d(_all(rd)[q]), wer=names[pid]) for q, pid in take.items()]
    if gruppe:
        out["quest_gruppe"] = gruppe
    if hier:
        out["quest_hier"] = hier
    if neu:
        out["quest_genommen"] = neu
    return out


def task(rd, lang):
    return AUFGABE[lang] if on(rd) else ""


def view(dm, rd, pid, host):
    """For a seat: the own things, what the others carry (with who), what lies here once seen; the host also every
    thing with its place (quest_geheim). (None, None) when off."""
    if not on(rd):
        return None, None
    names = {k: p["held"]["name"] for k, p in dm.seated(rd)}
    v = lambda x: {"q": x["q"], "name": _name(rd, x), "info": x["info"]}
    alle = list(_all(rd).values())
    out = {"zeichen": ZEICHEN, "meine": [v(x) for x in alle if pid and _who(dm, rd, x) == pid],
           "gruppe": [dict(v(x), wer=names[_who(dm, rd, x)]) for x in alle if _who(dm, rd, x) not in (None, pid)],
           "hier": [v(x) for x in _lying(dm, rd) if x["gesehen"]],
           "an": [{"pid": k, "name": n} for k, n in names.items() if k != pid and _carrier(dm, rd, k)]}
    geheim = {"alle": [dict(v(x), wer=names.get(_who(dm, rd, x), ""), ort="" if x.get("wer") or x.get("hid") else x["ort"],
                            gesehen=x["gesehen"], von=x["von"]) for x in alle], "max": QUEST_MAX} if host else None
    return out, geheim


def for_live(rs):
    return {"quest_dinge": sum(len(v.get("quest") or {}) for v in rs),
            "quest_getragen": sum(1 for v in rs for x in (v.get("quest") or {}).values() if x.get("wer"))}


def keep(rd):
    """What the next chapter takes over: the carried things (with their hero, no seat) and the used ones."""
    out = {}
    mit = {q: dict(x, wer=None, ort="") for q, x in (rd.get("quest") or {}).items() if x.get("hid")}
    if mit:
        out["quest"] = mit
    if rd.get("quest_weg"):
        out["quest_weg"] = list(rd["quest_weg"])
    return out


def carry(kampagne):
    return {k: kampagne[k] for k in ("quest", "quest_weg") if isinstance(kampagne.get(k), (dict, list))}
