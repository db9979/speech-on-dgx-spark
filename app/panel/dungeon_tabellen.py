"""KI-Dungeon-Master: the fixed tables of the catalog (Tabletop-Punkte 5 and 8 of 2026-10-25, Dominik „ich hätte gerne
alle punkte umgesetzt“; the data comes from the thread „DnDAppFiles für den Dungeon-Master“, dungeon_srd.json).

r["tabellen"] = [{"id", "gruppe": "nsc"|"orakel", "name": [de, en], "zeilen": [{"t": [de, en], "welten"?: [...]}]}]: a row
without "welten" counts in every world. A row of a FORMEN table (occupations) also names "m" and "w", the male and the
female German form; „Aussehen“ holds only looks (no word of AUSSEHEN_NICHT). A row of a FARBE table (hair, eyes, beard,
review 2026-10-27 Z9) may name "farbe", the fixed colour word the narrator's look check compares (dungeon_erzaehler). r["namensilben"] = {volk or "welt:<id>": {"anfang", "mitte", "ende"}}: a name is a
start, at most one middle and an end (the Syllabore method, own syllables). The panel rolls, never the model; what it
rolls goes to the model only as data. The oracle and many NPC rows are translated from Datasworn (CC-BY-4.0, the
attribution stands in dungeon_srd.json "lizenz" and in the docs).
"""
import random
import re

NAMEN_VORSCHLAG = 3        # fresh names the model may take for a new person
NAME_LEN = 30
GRUPPEN = ("nsc", "orakel", "eigen")   # "eigen": the admin's own tables (Regeln → Tabellen), rolled at the oracle
ZEILEN = (2, 300)
ZEILE_LEN = 160
TITEL_LEN = 40
_ID = re.compile(r"^[a-z0-9_]{2,40}$")
FORMEN = ("nsc_beruf",)   # tables whose rows name the male and the female German form ("m", "w"), to fit the person's gender
FORM_LEN = 40
FARBE = ("nsc_haar", "nsc_augen", "nsc_bart")   # fixed looks the panel rolls onto a card; nsc_statur has no colour
_FARBE = re.compile(r"^[a-z]{2,12}$")
AUSSEHEN = "nsc_aussehen"
AUSSEHEN_NICHT = ("wirkt", "spricht", "flüstert", "akzent", "begleitung", "energie", "gefasst", "nervös", "schrullig", "großspurig",
                  "unheimlich", "unheimliches", "blick", "art", "zerstreut", "einnehmende")   # manner, not looks: such rows go to „Art“


def check_rules(r):
    """The tables and the name syllables by fixed rules: German sentences of what is wrong (dungeon.check_rules adds
    them). The admin's own tables pass the same rules."""
    err = []
    welten = {w.get("id") for w in r.get("welten") or [] if isinstance(w, dict)}
    pair = lambda x, n: isinstance(x, list) and len(x) == 2 and all(isinstance(t, str) and 0 < len(t.strip()) <= n for t in x)  # noqa: E731
    for t in r.get("tabellen") or []:
        tid = t.get("id") if isinstance(t, dict) else None
        if not isinstance(tid, str) or not _ID.match(tid):
            err.append(f"tabellen: id {tid!r} nur aus a-z, 0-9 und _ (2 bis 40 Zeichen)")
            continue
        if t.get("gruppe") not in GRUPPEN:
            err.append(f"tabellen {tid}: gruppe nur {', '.join(GRUPPEN)}")
        if not pair(t.get("name"), TITEL_LEN):
            err.append(f"tabellen {tid}: name als [deutsch, englisch], je bis {TITEL_LEN} Zeichen")
        z = t.get("zeilen")
        if not isinstance(z, list) or not ZEILEN[0] <= len(z) <= ZEILEN[1]:
            err.append(f"tabellen {tid}: {ZEILEN[0]} bis {ZEILEN[1]} zeilen")
            continue
        form = tid in FORMEN
        keys = {"t", "welten", *(("m", "w") if form else ()), *(("farbe",) if tid in FARBE else ())}
        for x in z:
            if not isinstance(x, dict) or not pair(x.get("t"), ZEILE_LEN) or not set(x) <= keys \
                    or "welten" in x and not (isinstance(x["welten"], list) and x["welten"] and set(x["welten"]) <= welten):
                err.append(f"tabellen {tid}: jede Zeile {{\"t\": [deutsch, englisch]}} bis {ZEILE_LEN} Zeichen, welten nur bekannte Welten")
                break
            if "farbe" in x and not (isinstance(x["farbe"], str) and _FARBE.match(x["farbe"])):
                err.append(f"tabellen {tid}: farbe ein festes Farbwort aus a-z")
                break
            if form and not all(isinstance(x.get(k), str) and 0 < len(x[k].strip()) <= FORM_LEN for k in ("m", "w")):
                err.append(f"tabellen {tid}: jede Zeile mit \"m\" und \"w\", der männlichen und der weiblichen Form (bis {FORM_LEN} Zeichen)")
                break
            if tid == AUSSEHEN and set(re.findall(r"[a-zäöüß]+", x["t"][0].lower())) & set(AUSSEHEN_NICHT):
                err.append(f"tabellen {tid}: nur Äußeres; „{x['t'][0][:40]}“ beschreibt Art oder Verhalten und gehört nach nsc_art")
                break
    s = r.get("namensilben")
    if s is not None and not (isinstance(s, dict) and all(
            isinstance(v, dict) and all(isinstance(v.get(k), list) and all(isinstance(y, str) and 0 < len(y) <= 12 for y in v[k])
                                        for k in ("anfang", "mitte", "ende")) and v["anfang"] and v["ende"] for v in s.values())):
        err.append("namensilben: je Volk oder welt:<id> anfang, mitte und ende als Listen kurzer Silben")
    return err


def table(r, tid):
    return next((t for t in r.get("tabellen") or [] if t.get("id") == tid), None)


def rows(r, tid, welt):
    """The rows of a table that count in this world, as [de, en]."""
    t = table(r, tid)
    return [z["t"] for z in (t or {}).get("zeilen") or [] if not z.get("welten") or welt in z["welten"]]


def roll(r, tid, welt, rng=None):
    """One row of the table for this world, [de, en]; None when there is none."""
    xs = rows(r, tid, welt)
    return list((rng or random).choice(xs)) if xs else None


def _syllables(r, welt, volk, rng):
    s = r.get("namensilben") or {}
    if f"welt:{welt}" in s:
        return s[f"welt:{welt}"]
    if volk in s:
        return s[volk]
    keys = sorted(k for k in s if not k.startswith("welt:"))
    return s[rng.choice(keys)] if keys else None


def name(r, welt, volk=None, rng=None):
    """A name from the syllables of the world (sci-fi, pirates) or of a people; "" without syllables."""
    rng = rng or random
    s = _syllables(r, welt, volk, rng)
    if not s or not s.get("anfang") or not s.get("ende"):
        return ""
    mitte = rng.choice(s["mitte"]) if s.get("mitte") and rng.random() < 0.4 else ""
    n = (rng.choice(s["anfang"]) + mitte + rng.choice(s["ende"]))[:NAME_LEN]
    return n[:1].upper() + n[1:]


def fresh_names(r, rd, rng=None, n=NAMEN_VORSCHLAG):
    """Up to n names nobody of the round bears yet (heroes, the people of the truth), for the model as data."""
    rng = rng or random
    taken = {p["held"]["name"].lower() for p in rd["plaetze"].values() if p.get("held")}
    taken |= {p["name"].lower() for p in (rd.get("wahrheit") or {}).get("personen") or []}
    out = []
    for _ in range(n * 4):
        x = name(r, rd.get("welt"), None, rng)
        if x and x.lower() not in taken:
            taken.add(x.lower())
            out.append(x)
        if len(out) >= n:
            break
    return out
