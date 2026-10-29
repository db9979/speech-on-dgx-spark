"""KI-Dungeon-Master: Protokoll-Prüfer (Dominik 2026-10-28 „es kommen zu viele fehler aktuell … mache mir vorschläge“,
Vorschlag 5, „ok“).

Two halves, both by fixed rules, never the model:

  rest        after every told turn the panel runs all fixed checks of the narration (dungeon_erzaehler.faults) once
              more over the narration it keeps, the repaired one too (repair_all). What is still found counts as a
              fault the table saw: the journal names its kinds („dungeon: protokoll | rest | gegner knapp“), Live counts
              the turns checked and those with a fault left. The round's names are checked too (runde): a word for no
              name („keine“) as a foe, a person card or a person of the truth, a person card that is also a foe.
  Prüffall    a round as the page shows it, copied and pasted (Dominik's „passt das alles?“), read back into its turns
              (read): the actions, the lines before and after the turn's header, the narration. text_faults finds by
              fixed rules what such a copy shows wrong (STUFE, PLATZHALTER, ZAUBER_TRIFFT, HAENDLER, PANEL_SATZ,
              FRAGE_GEHEN, ZAUBER_PROBE). A copy kept in tests/dungeon_protokolle/ with the findings it must give
              (its header) is a test case: test_dungeon_protokoll reads every one; tools/protokoll.py prints the
              findings of a new copy and keeps it as a case.

No switch of its own: a measurement inside the Dungeon Master and a test, no new behaviour at the table.
Journal: fixed words and numbers („dungeon: protokoll | …“), Live only counts.
"""
import re

from common import DayCounter

ARTEN = ("stufe", "platzhalter", "zauber_trifft", "haendler", "panel_satz", "frage_gehen", "zauber_probe")
RUNDE = ("platzhalter", "person_gegner")   # the round's names (runde)
LANG = 120                                 # a line of a pasted copy this long is narration

_day = DayCounter(geprueft=0, rest=0, platzhalter=0, person_gegner=0)
_ZUG = re.compile(r"^(?:ZUG|TURN) (\d+)")
_SG = re.compile(r"gegen Schwierigkeit (\d+) · ([^\n·]+?)\s*$|against difficulty (\d+) · ([^\n·]+?)\s*$", re.I)
_ZIEL = re.compile(r"(?:Ziel|Target) (\d+) \(([^)]+)\)")
_PFEIL = re.compile(r"^(.+?) → (.+?) ·")
_WIRKT = re.compile(r"^✦ (.+?) (?:wirkt|casts) (.+?): \S")
_MARKT = re.compile(r"^⚖ (.+?) (?:bietet hier Waren an|offers goods here)")
_WUERFELT = re.compile(r"^(.+?) (?:WÜRFELT|ROLLS) ")
_GEHEN = ("Keine Probe: Gehen braucht keine", "No check: going needs none")


def rest(dm, rd, story, wuerfe=(), hits=(), zuege=(), count=True):
    """The fault words the fixed checks still find in the narration kept (story), [] when none; journal and count
    (count=False: the Erzähler-Prüfstand's Rundlauf, neither)."""
    fs = [w for w, _ in dm.erz.faults(dm, rd, story, wuerfe, hits, zuege, False) if w not in dm.erz.NUR_HINWEIS]
    if not count:
        return fs
    _day.bump("geprueft")
    if fs:
        _day.bump("rest")
        print(f"dungeon: protokoll | rest | {' '.join(dict.fromkeys(fs))}", flush=True)
    else:
        print("dungeon: protokoll | ok", flush=True)
    return fs


def runde(dm, rd, count=True):
    """The round's names after a told turn: [(kind, count)] of RUNDE that are wrong; journal and count (count=False:
    the Rundlauf, neither)."""
    import dungeon_nsc as nsc
    leer = set(nsc.LEERWORTE)
    feinde = {re.sub(r" \d+$", "", str(g.get("name", ""))).lower() for g in (rd.get("kampf") or {}).get("gegner") or []}
    karten = {str(x.get("name", "")).lower() for x in (rd.get("nsc") or {}).values()}
    wahr = {str(p.get("name", "")).lower() for p in (rd.get("wahrheit") or {}).get("personen") or []}
    out = [(k, n) for k, n in (("platzhalter", len((feinde | karten | wahr) & leer)), ("person_gegner", len(karten & feinde))) if n]
    for k, n in out if count else ():
        _day.bump(k, n)
        print(f"dungeon: protokoll | {k} | {n}", flush=True)
    return out


def for_live():
    t = _day.counts()
    return {"protokoll_geprueft": t["geprueft"], "protokoll_rest": t["rest"], "protokoll_namen": t["platzhalter"] + t["person_gegner"]}


def read(text):
    """A round as the page shows it, pasted, read back into its turns: [{"zug": n or None, "aktionen": [(name, text)],
    "vorher": [lines before the header], "erzaehlung": text, "danach": [lines after it]}]. The lines before the first
    header belong to a turn without a number (the end of an earlier one)."""
    lines = [x.strip() for x in str(text or "").replace("&#39;", "'").replace("&quot;", '"').split("\n") if not x.startswith("# ")]
    turns, cur, pend, pre = [], {"zug": None, "aktionen": [], "vorher": [], "erzaehlung": "", "danach": []}, [], []
    i = 0
    while i < len(lines):
        x = lines[i]
        if i + 2 < len(lines) and lines[i + 2] == "⊘" and x and lines[i + 1]:
            pend.append((x, lines[i + 1]))
            i += 3
            continue
        m = _ZUG.match(x)
        if m:
            turns.append(cur)
            cur = {"zug": int(m.group(1)), "aktionen": pend, "vorher": pre, "erzaehlung": "", "danach": []}
            pend, pre = [], []
        elif x in ("👎", ""):
            pass
        elif len(x) >= LANG and not pend:
            cur["erzaehlung"] = (cur["erzaehlung"] + " " + x).strip()
        elif pend:
            pre.append(x)
        else:
            cur["danach"].append(x)
        i += 1
    turns.append(cur)
    return [t for t in turns if t["zug"] is not None or t["erzaehlung"] or t["danach"]]


def text_faults(dm, turns, lang="de"):
    """What a pasted round shows wrong, by fixed rules: [(kind, turn number)] in the order found, each once a turn."""
    import dungeon_nsc as nsc
    leer, li = set(nsc.LEERWORTE), 1 if lang == "en" else 0
    zauber = [n.split(": ", 1)[-1].lower() for c in dm.rules()["gegenstaende"] if c["art"] == "zauber" for n in c["name"]]
    out = []

    def add(k, z):
        if (k, z) not in out:
            out.append((k, z))
    for t in turns:
        z, alle = t["zug"], t["vorher"] + t["danach"]
        sg = {int(a or c): (b or d).strip().lower() for x in t["vorher"] for a, b, c, d in _SG.findall(x)}
        for x in t["vorher"]:
            for n, w in _ZIEL.findall(x):
                if int(n) in sg and w.strip().lower() != sg[int(n)]:
                    add("stufe", z)            # the card and the dice bar name two levels for one number
        daneben = set()
        for j, x in enumerate(alle):
            m = _PFEIL.match(x)
            if m and ({m.group(1).lower(), m.group(2).split(" · ")[0].lower()} & leer):
                add("platzhalter", z)          # „keine → Gandalf“: a word for no name as a foe
            if m and any(y in ("daneben", "miss") for y in alle[j + 1:j + 7]):
                daneben.add(m.group(1).lower())
            if x.lower() in leer or re.search(r"· (?:von|by) (\w+)$", x) and re.search(r"· (?:von|by) (\w+)$", x).group(1).lower() in leer:
                add("platzhalter", z)
            w = _WIRKT.match(x)
            if w and w.group(1).lower() in daneben:
                add("zauber_trifft", z)        # a missed spell whose line still tells its effect
            mk = _MARKT.match(x)
            low = t["erzaehlung"].lower()
            if mk and mk.group(1).lower() not in low and not any(k in low for k in dm.MARKT_WORT):
                add("haendler", z)             # a merchant the narration never shows
        if any(dm.panel_says({"lang": lang}, s) for s in dm.erz._saetze(t["erzaehlung"])):
            add("panel_satz", z)
        if any(_GEHEN[li] in x for x in alle) and any(dm.erz.asks(a) for _, a in t["aktionen"]):
            add("frage_gehen", z)              # a question told as „going needs no check“
        for name, a in t["aktionen"]:
            if dm._named(a, zauber) and any((_WUERFELT.match(x) or [None, ""])[1].lower() == name.lower() for x in t["vorher"]) \
                    and not any(x.startswith(("Das kann", "That is beyond")) for x in alle):
                add("zauber_probe", z)         # a spell named, a check rolled instead of „cannot do that yet“
    return out


def header(text):
    """The findings a kept case must give, from its header line „# befunde: kind turn, kind turn …“."""
    m = re.search(r"^# befunde:(.*)$", text, re.M)
    return [(k, int(n) if n != "-" else None) for k, n in re.findall(r"(\w+) (\d+|-)", m.group(1))] if m else None
