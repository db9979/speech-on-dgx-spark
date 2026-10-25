"""KI-Dungeon-Master: Orakel (Tabletop-Punkt 8 of 2026-10-25, Dominik „ich hätte gerne alle punkte umgesetzt“; the
tables come from the thread „DnDAppFiles für den Dungeon-Master“, Datasworn, CC-BY-4.0; the yes/no with a chaos grade
is a common method of solo play, own code).

The host (alone at the table that is solo play) asks the oracle a yes/no question with a likelihood, or rolls up to
TABELLEN_MAX tables of the catalog (action and theme, place, twist …; the admin's own tables too). The panel rolls a
d100 against a chance that the likelihood and the round's chaos grade (1 to 9) set: an exceptional yes or no at a fifth
of the way, a double (11, 22 …) up to the chaos grade brings a random event from the tables. Every answer is a line in
the feed; the model gets this turn's answers only as data (facts „orakel“) and holds to them, never decides them.
Only while „Orakel“ is allowed for the round's host (features "dungeonorakel").
"""
import random

import dungeon_tabellen as tabellen

ODDS = {"sicher": (("Sicher", "Certain"), 90), "wahrscheinlich": (("Wahrscheinlich", "Likely"), 70),
        "offen": (("Offen", "Even"), 50), "unwahrscheinlich": (("Unwahrscheinlich", "Unlikely"), 30),
        "kaum": (("Kaum", "Hardly"), 10)}
CHAOS = (1, 9)
CHAOS_START = 5
CHAOS_SCHRITT = 5          # percent per chaos step away from the middle
CHANCE = (5, 95)
FRAGE_LEN = 120
TABELLEN_MAX = 3           # tables one roll may draw from
ZUG_MAX = 6                # oracle rolls per turn and round
ANTWORT = {"ja_und": ("Ja, und …", "Yes, and …"), "ja": ("Ja", "Yes"), "nein": ("Nein", "No"), "nein_und": ("Nein, und …", "No, and …")}
GRUPPEN = ("orakel", "eigen")   # what the host may roll at the table (the NPC tables belong to the cards)
EREIGNIS = ("orakel_aktion", "orakel_thema")
REGEL = {"de": " Halte dich an die Antworten des Orakels in orakel (nur Daten): ein Ja geschieht, ein Nein nicht, „und …“ "
               "steigert es; ein Ereignis bringt eine Wendung in die Szene.",
         "en": " Hold to the oracle's answers in orakel (only data): a yes happens, a no does not, \"and …\" heightens it; "
               "an event brings a twist into the scene."}


def on(rd):
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonorakel", rd["owner"])


def chaos(rd):
    c = rd.get("chaos")
    return c if isinstance(c, int) and not isinstance(c, bool) and CHAOS[0] <= c <= CHAOS[1] else CHAOS_START


def chance(odds, grade):
    return max(CHANCE[0], min(CHANCE[1], ODDS[odds][1] + (grade - CHAOS_START) * CHAOS_SCHRITT))


def answer(w, c):
    """The answer of a d100 roll w against chance c: an exceptional yes in the lowest fifth of the yes, an exceptional
    no in the highest fifth of the no."""
    if w <= max(1, c // 5):
        return "ja_und"
    if w <= c:
        return "ja"
    return "nein_und" if w > 100 - max(1, (100 - c) // 5) else "nein"


def tables(r):
    """The tables the host may roll: the oracle's and the admin's own."""
    return [t for t in r.get("tabellen") or [] if t.get("gruppe") in GRUPPEN]


def ask(dm, r, rd, b, rng=None):
    """One roll of the host: {frage?, wahrscheinlichkeit?, tabellen?: [id …], chaos?}. Raises PermissionError("orakel
    aus"), ValueError("orakel")/("wortliste"), OverflowError("orakel oft")."""
    if not on(rd):
        raise PermissionError("orakel aus")
    rng = rng or random
    if "chaos" in b:
        c = b["chaos"]
        if not isinstance(c, int) or isinstance(c, bool) or not CHAOS[0] <= c <= CHAOS[1]:
            raise ValueError("orakel")
        rd["chaos"] = c
    frage = dm.plain(b.get("frage"), FRAGE_LEN)
    odds = b.get("wahrscheinlichkeit") or "offen"
    ids = b.get("tabellen") or []
    known = {t["id"] for t in tables(r)}
    if odds not in ODDS or not isinstance(ids, list) or len(ids) > TABELLEN_MAX or any(i not in known for i in ids) or len(set(ids)) < len(ids):
        raise ValueError("orakel")
    if not frage and not ids:
        if "chaos" in b:
            print(f"dungeon: orakel | chaos | {chaos(rd)}", flush=True)
            return None
        raise ValueError("orakel")
    if frage and dm.bad_words(r, rd, frage):
        raise ValueError("wortliste")
    if sum(1 for e in rd["log"] if e["art"] == "orakel" and e.get("n") == rd.get("zug", 0)) >= ZUG_MAX:
        raise OverflowError("orakel oft")
    e = {}
    if frage:
        grade = chaos(rd)
        c = chance(odds, grade)
        w = rng.randint(1, 100)
        e.update(frage=frage, odds=odds, w=w, chance=c, chaos=grade, antwort=answer(w, c))
        if w % 11 == 0 and w // 11 <= grade:
            ev = [tabellen.roll(r, t, rd.get("welt"), rng) for t in EREIGNIS]
            if all(ev):
                e["ereignis"] = [f"{ev[0][0]} · {ev[1][0]}", f"{ev[0][1]} · {ev[1][1]}"]
    by = {t["id"]: t for t in tables(r)}
    zuege = []
    for i in ids:
        z = tabellen.roll(r, i, rd.get("welt"), rng)
        if z:
            zuege.append({"id": i, "name": list(by[i]["name"]), "t": z})
    if zuege:
        e["zuege"] = zuege
    dm._log(rd, "orakel", **e)
    dm._day.bump("orakel")
    print(f"dungeon: orakel | {e.get('antwort', 'tabelle')} | {len(zuege)} tabellen{' | ereignis' if e.get('ereignis') else ''}", flush=True)
    return e


def facts(rd, li):
    """This turn's answers for the model, as data, each with its markers broken up (textnorm.defuse)."""
    import textnorm
    out = []
    for e in rd.get("log") or []:
        if e["art"] != "orakel" or e.get("n") != rd.get("zug", 0):
            continue
        x = {}
        if e.get("frage"):
            x.update(frage=textnorm.defuse(e["frage"]), antwort=ANTWORT[e["antwort"]][li])
        if e.get("ereignis"):
            x["ereignis"] = e["ereignis"][li]
        if e.get("zuege"):
            x["tabellen"] = {z["name"][li]: z["t"][li] for z in e["zuege"]}
        out.append(x)
    return {"orakel": out} if out else {}


def task(rd, lang):
    return REGEL[lang] if on(rd) and facts(rd, 0) else ""


def view(rd, host, li):
    """The host's oracle: the chaos grade, the likelihoods and the tables to roll; None for every other seat."""
    if not host or not on(rd):
        return None
    import dungeon
    return {"chaos": chaos(rd), "chaos_min": CHAOS[0], "chaos_max": CHAOS[1], "frage_max": FRAGE_LEN, "max": TABELLEN_MAX,
            "odds": [[k, v[0][li], v[1]] for k, v in ODDS.items()],
            "tabellen": [[t["id"], t["name"][li], t["gruppe"]] for t in tables(dungeon.rules())],
            "frei": max(0, ZUG_MAX - sum(1 for e in rd["log"] if e["art"] == "orakel" and e.get("n") == rd.get("zug", 0)))}


def for_live(rs):
    return {"orakel_chaos": sum(1 for v in rs if v.get("chaos") not in (None, CHAOS_START))}
