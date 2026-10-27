"""KI-Dungeon-Master: Überreden zum Mitkommen (LlamaTale idea 4, plan plaene/dungeon-llamatale-ideen.md, Dominik
2026-10-27 „1-7“; idea only, own code).

Without this switch a word of MIT in an action takes a person of the map along at once (dungeon_karte._people). With
it the panel decides by fixed rules, never the model:
- checks(dm, r, rd, proben): before the narration each person a seat asks along (dungeon_karte.fragen, the map
  thread's) gets the panel's answer: not at the group's place or no card: no; an attitude towards the hero below
  MIN (+1): no, without a check; „treu ergeben“ (TREU, +3): yes, without a check; else the panel's Charisma check in
  place of the model's checks for that seat, SG by the attitude (SG: friendly 13, warm 11).
- tell (dungeon.py): the decisions and the check's result are the narration's facts (mitkommen) with the task that
  the person only answers in a short sentence that fits; whether it comes is the panel's.
- apply(dm, rd, events): after the narration (after dungeon_karte.step asked, p["fragt"]) dungeon_karte.mitnehmen
  takes the person along or leaves it; a line in the feed and the chronicle.
A person along is no hired companion (dungeon_gefaehrte): it travels with the group and speaks, but never fights by
the panel's dice. Only while the admin's switch „Überreden zum Mitkommen“ (dungeonmitkommen) is allowed for the round's
host, on top of „NSC-Gedächtnis und Chronik“. Journal: fixed words and numbers („dungeon: mitkommen | …“), Live only
counts.

    rd["_mitkommen"]  [{"name", "pid", "ja", "grund"}]   only on run_turn's copy; the story carries it into keep
"""
import dungeon_nsc as nsc
import features
from common import DayCounter

KEY = "dungeonmitkommen"
MIN = 1                    # the attitude a person needs towards the hero to be asked along at all
TREU = 3                   # „treu ergeben“: comes along without a check
SG = {1: 13, 2: 11}        # the Charisma check by the attitude
_day = DayCounter(gefragt=0, ja=0, nein=0)

AUFGABE = {
    "de": (" mitkommen nennt Personen, die ein Held zum Mitkommen gefragt hat, und ob sie mitkommen (ja) oder bleiben "
           "(nein); das hat das Panel entschieden. Lass die Person nur mit einem kurzen Satz so antworten, entscheide es "
           "nie anders."),
    "en": (" mitkommen names people a hero asked to come along and whether they come (ja) or stay (nein); the panel "
           "decided it. Let the person only answer in a short sentence that fits; never decide it otherwise."),
}


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and nsc.on(rd) and bool(rd.get("karte"))


def checks(dm, r, rd, proben):
    """Before the narration: the panel's answer for each person a seat asks along, a Charisma check in place of the
    model's checks for that seat where the attitude leaves it open; the fixed answers in rd["_mitkommen"]."""
    rd["_mitkommen"] = []
    if not on(rd):
        return proben
    import dungeon_karte
    k, ns, li = rd["karte"], rd.get("nsc") or {}, 1 if rd.get("lang") == "en" else 0
    for name, pid in dungeon_karte.fragen(rd):
        h = (rd["plaetze"].get(pid) or {}).get("held")
        if not h:
            continue
        _day.bump("gefragt")
        p, x = (k.get("leute") or {}).get(name) or {}, ns.get(name.lower())
        v = ((x or {}).get("haltung") or {}).get(h["name"].lower(), 0)
        if not x or p.get("ort") != k["hier"]:
            grund = "weg"
        elif v < MIN:
            grund = "abgelehnt"
        elif v >= TREU:
            grund = "treu"
        else:
            proben = [q for q in proben if q["pid"] != pid] + [
                {"pid": pid, "wert": "charisma", "schwer": SG[min(v, max(SG))], "vt": "", "mitkommen": name,
                 "wofuer": (f"{name} zum Mitkommen überreden", f"persuade {name} to come along")[li]}]
            print("dungeon: mitkommen | probe", flush=True)
            continue
        rd["_mitkommen"].append({"name": name, "pid": pid, "ja": grund == "treu", "grund": grund})
        print(f"dungeon: mitkommen | {grund}", flush=True)
    return proben


def seen(rd, wuerfe):
    """In tell: the fixed answers and the checks' results, one event per person asked (also the story's)."""
    out = list(rd.get("_mitkommen") or []) if on(rd) else []
    out += [{"name": w["mitkommen"], "pid": w["pid"], "ja": bool(w["ok"]), "grund": "probe"} for w in wuerfe or () if w.get("mitkommen") and on(rd)]
    rd["_mitkommen"] = out
    return out


def facts(rd):
    """For the narration: who asked whom along and the panel's answer ({} without)."""
    if not on(rd) or not rd.get("_mitkommen"):
        return {}
    names = {pid: (p.get("held") or {}).get("name", "") for pid, p in rd["plaetze"].items()}
    return {"mitkommen": [{"wer": names.get(e["pid"], ""), "person": e["name"], "antwort": "ja" if e["ja"] else "nein"} for e in rd["_mitkommen"]]}


def task(rd, lang):
    return AUFGABE[lang] if on(rd) and rd.get("_mitkommen") else ""


def apply(dm, rd, events):
    """After the narration: the map takes each person along or leaves it (dungeon_karte.mitnehmen); a line in the
    feed and the chronicle."""
    import dungeon_karte
    for e in events or []:
        if not dungeon_karte.mitnehmen(rd, e["name"], e["ja"]):
            continue
        _day.bump("ja" if e["ja"] else "nein")
        n = e["name"]
        de, en = (f"{n} kommt mit euch.", f"{n} comes along with you.") if e["ja"] else (f"{n} bleibt hier.", f"{n} stays here.")
        dm._log(rd, "system", text=[de, en])
        if e["ja"]:
            nsc.note(rd, f"{n} schließt sich der Gruppe an.", f"{n} joins the group.")
        print(f"dungeon: mitkommen | {'ja' if e['ja'] else 'nein'}", flush=True)


def for_live():
    """Numbers only: people asked along today, come along, stayed."""
    return _day.counts()
