"""KI-Dungeon-Master: NSC-Gedächtnis, Chronik und Ruf (Tabletop-Punkt 5 of 2026-10-25 with Stufe 5c of 2026-10-23,
Dominik „ich hätte gerne alle punkte umgesetzt“; idea from loreweaver and NarrativeEngine-P, MIT, own code).

Every person of the round's truth gets a card the panel rolls from the fixed tables (dungeon_tabellen: looks, manner,
occupation, wish, secret), relations to heroes and other people (owes, fears, likes, knows about) and an attitude
towards each hero from −3 to +3. The model only reports changes (story "nsc": a hero won someone over or angered them,
a new relation), the panel takes them by fixed rules: only a person of this scene, only by name in the narration, one
step per hero and turn. Only the people of the scene go to the model with their cards; the others only by name.
The chronicle keeps what mattered (people met, fights won, heroes fallen, levels, threads closed, acts, chapters) by
fixed rules from the round's log, the reputation of a hero is the mean attitude of the people who know them.
Both go on in the next chapter. NSC-Ziele (Tabletop-Punkt 6, idea from NarrativeEngine-P, MIT, own code): every person
also has six traits from −3 to +3 and a goal on three levels (today, soon, in life, from the wish table and the truth);
between turns the panel rolls each person's progress on its nearest open goal, a reached one goes into the chronicle
and, only as data, into the next narration. Only while „NSC-Gedächtnis und Chronik“ is allowed for the round's host (features
"dungeonnsc"). The fields:

    rd["nsc"]     {name.lower(): {"name", "karte": {feld: [de, en]}, "kanten": [{"art", "ziel"}], "haltung": {held: −3..3},
                   "gesehen": turn | None, "wesen": {zug: −3..3}, "ziele": [{"ebene", "t": [de, en], "stand", "voll"}],
                   "geschlecht": weiblich|maennlich|divers, "alter": kind|jung|mittel|alt}}

One gender and one age per person (Review 27.10. Paket 10, Z1, Z5, Z9): the panel writes both onto the card once (gender:
a title or role word, else the name; dungeon_stimmen.fix; age: the looks' words, else the name, never a child with an
adult's occupation; age), the model's statements are dropped. Occupation word, voice, portrait, facts and catalog read
only these fields. Then the panel rolls the fixed looks (MERKMALE: hair, eyes, beard, build) by the age and gender
(grey or white only when old, a beard only for a man from young on), which the narrator's look check compares.
    rd["ziel_neu"] [{"name", "ebene", "t": [de, en]}]   the goals reached after the last told turn (for the next narration)
    rd["chronik"] [{"n": turn, "k": chapter, "t": [de, en]}]
"""
import random
import re

import dungeon_tabellen as tabellen
from common import DayCounter

KARTE = ("aussehen", "art", "beruf", "wunsch", "geheimnis")      # tables nsc_<feld>
MERKMALE = ("haar", "augen", "bart", "statur")                  # fixed looks, tables nsc_<feld>, rolled after gender and age
FELDER = KARTE + MERKMALE                                       # every field of a card
OFFEN = ("aussehen", "art", "beruf") + MERKMALE                 # what the table sees once met; wish and secret: host and model
ALTER_WORT = {"kind": ("Kind", "child"), "jung": ("jung", "young"), "mittel": ("mittleren Alters", "middle-aged"), "alt": ("alt", "old")}
ALTER_AUSSEHEN = (("alt", ("recht alt", "greis", "betagt")), ("jung", ("sehr jung",)))   # words of the looks (German) that set the age
KIND_BERUF = ("cabin boy",)                                     # occupations (English column) a child may have; any other: never a child
ALT_FARBE = ("grau", "weiss")                                   # hair and beard colours only for the old
BART_AB = ("jung", "mittel", "alt")
KANTEN = {"schuldet": ("schuldet", "owes"), "fuerchtet": ("fürchtet", "fears"), "mag": ("mag", "likes"),
          "weiss": ("weiß von", "knows about")}
KANTEN_MAX = 4             # relations kept per person (the oldest goes)
AENDERUNGEN_MAX = 3        # changes one narration may report
HALTUNG = (-3, 3)
HALTUNG_WORT = {-3: ("verfeindet", "hostile"), -2: ("feindselig", "unfriendly"), -1: ("misstrauisch", "wary"),
                0: ("neutral", "neutral"), 1: ("freundlich", "friendly"), 2: ("herzlich", "warm"), 3: ("treu ergeben", "devoted")}
RUF = ((-1.5, ("berüchtigt", "notorious")), (-0.5, ("beargwöhnt", "distrusted")), (0.5, ("unbekannt", "unknown")),
       (1.5, ("geachtet", "respected")), (99, ("gefeiert", "celebrated")))
SZENE_ZUEGE = 2            # a person counts as in the scene when it spoke or was named in the last this many turns
CHRONIK_MAX = 40
CHRONIK_FAKTEN = 6         # the last lines of the chronicle the model gets
NAME_LEN = 40
# NSC-Ziele (Tabletop-Punkt 6): six traits, each from −3 (the second word) to +3 (the first)
WESEN = {"mut": (("mutig", "brave"), ("ängstlich", "fearful")), "ehrlich": (("ehrlich", "honest"), ("verschlagen", "sly")),
         "freundlich": (("freundlich", "kind"), ("schroff", "gruff")), "grosszuegig": (("großzügig", "generous"), ("geizig", "stingy")),
         "ruhig": (("besonnen", "calm"), ("hitzig", "hot-headed")), "treu": (("treu", "loyal"), ("wankelmütig", "fickle"))}
WESEN_STUFE = {1: ("etwas ", "somewhat "), 2: ("", ""), 3: ("sehr ", "very ")}
EBENEN = {"heute": (("Heute", "Today"), 2), "bald": (("Bald", "Soon"), 4), "leben": (("Im Leben", "In life"), 6)}   # steps to reach
ZIEL_WURF = 5              # a d6 at or above this moves a person's nearest open goal a step between turns
ZIEL_MUTIG = 4             # the same for a brave person (mut 2 or more)

SCHEMA = {"type": "array", "maxItems": AENDERUNGEN_MAX, "items": {"type": "object", "additionalProperties": False, "required": ["name"],
          "properties": {"name": {"type": "string", "maxLength": NAME_LEN}, "held": {"type": "string", "maxLength": NAME_LEN},
                         "haltung": {"type": "string", "enum": ["", "besser", "schlechter"]},
                         "kante": {"type": "string", "enum": ["", *KANTEN]}, "ziel": {"type": "string", "maxLength": NAME_LEN}}}}
AUFGABE = {
    "de": (f" In nsc meldest du höchstens {AENDERUNGEN_MAX} Änderungen bei Figuren dieser Szene (nsc_szene): haltung "
           "besser oder schlechter, wenn ein Held (held) die Figur für sich gewinnt oder verärgert; kante schuldet, fürchtet, "
           "mag oder weiss mit ziel (ein Held oder eine Figur), wenn eine neue Beziehung entsteht. Bleib bei Geschlecht, Aussehen, Art "
           "und Beruf einer Figur aus nsc_szene; Wunsch und Geheimnis treiben sie an, verrate das Geheimnis nicht ohne Grund. "
           "Wesen und Ziele einer Figur bestimmen, was sie tut."),
    "en": (f" In nsc report at most {AENDERUNGEN_MAX} changes for people of this scene (nsc_szene): haltung besser or "
           "schlechter when a hero (held) wins the person over or angers them; kante schuldet, fuerchtet, mag or weiss with "
           "ziel (a hero or a person) when a new relation begins. Keep to the gender, looks, manner and occupation of a person from "
           "nsc_szene; wish and secret drive them, do not give the secret away without a reason. Traits (wesen) and goals "
           "(ziele) decide what a person does."),
}
# Review 27.10. T20: the scene's rules only with people in the scene, the goal's only with a goal reached, the names always
ZIEL_AUFGABE = {"de": " nsc_ziel_erreicht nennt, wer gerade ein Ziel erreicht hat: lass es in der Welt spürbar werden.",
                "en": " nsc_ziel_erreicht names who just reached a goal: let the world feel it."}
NAMEN_AUFGABE = {"de": " Für eine neue Figur nimm einen Namen aus freie_namen.", "en": " For a new person take a name from freie_namen."}


# a name or role that is a title names the occupation (Dominik 2026-10-27 „schattenwächter händler? stimmt das?“): the
# German stems besides the occupation table's own words (nsc_beruf, its forms m and w), mapped to the table's English word
TITEL = {"waechter": "guard", "wächter": "guard", "hueter": "guard", "hüter": "guard", "haendler": "trader", "kaufmann": "trader",
         "magier": "mystic", "zauberer": "mystic", "seher": "mystic", "priester": "priest", "jaeger": "hunter", "jäger": "hunter",
         "ritter": "knight", "schmied": "smith", "dieb": "thief", "wirt": "innkeeper", "heiler": "healer", "spaeher": "scout",
         "späher": "scout", "gelehrt": "scholar", "kundschafter": "scout", "soeldner": "mercenary", "söldner": "mercenary"}


# Review 27.10. Paket 8 (Z3, G30): a name is a person only by fixed rules, never by the model: no hero, no companion, no
# foe of the fight (a person fighting stays one), no name of the bestiary (also with a number or a plural), no group of
# the truth, no bare role word and no word ending in one („Schattenwächter“)
ROLLENWORTE = ("wache", "wachen", "händler", "haendler", "händlerin", "wirt", "wirtin", "schmied", "schmiedin", "alchemist",
               "alchemistin", "krämer", "kraemer", "krämerin", "bauer", "bäuerin", "fremder", "fremde", "mann", "frau", "kind",
               "junge", "mädchen", "alte", "alter", "greis", "stimme", "gestalt", "diener", "dienerin", "bote", "botin", "soldat",
               "soldaten", "krieger", "kriegerin", "erzähler", "erzählerin", "bord-ki", "ki", "computer", "guard", "guards",
               "merchant", "trader", "innkeeper", "smith", "stranger", "man", "woman", "child", "boy", "girl", "voice", "figure",
               "servant", "messenger", "soldier", "warrior", "narrator", "ship ai", "ai")
ROLLEN_ENDE = ("wächter", "waechter", "wächterin", "hüter", "hueter", "hüterin", "wache", "krieger", "kriegerin", "soldat",
               "guard", "warden", "keeper", "soldier", "warrior")
ARTIKEL = ("der", "die", "das", "den", "dem", "ein", "eine", "einer", "the", "a", "an")
LEERWORTE = ("kein", "keine", "keiner", "keins", "niemand", "nichts", "unbekannt", "unbekannte", "unbekannter", "namenlos",
             "namenlose", "namenloser", "unbenannt", "anonym", "leer", "name", "none", "nobody", "no one", "nothing", "unknown",
             "nameless", "unnamed", "anonymous", "empty", "null", "n/a", "tbd")   # the model's word for „no name“ (Dominik 2026-10-28: a card „keine“)


def ist_person(r, rd, name):
    """"" when name may be a person of the round, else why not: "leer" (a word for no name, LEERWORTE, or no letter),
    "held", "gefaehrte", "gegner", "bestiarium", "gruppe" or "rolle" (dungeon_erzaehler.check_truth and learn_people, dungeon.open_market, dungeon_personen.collect)."""
    n = re.sub(r"\s+\d+$", "", str(name or "").strip()).lower()
    if len(n) < 2:
        return "rolle"
    if n in LEERWORTE or not re.search(r"[^\W\d_]", n):
        return "leer"
    if n in {str(p["held"]["name"]).lower() for p in (rd.get("plaetze") or {}).values() if p.get("held")}:
        return "held"
    if n in {str(c.get("name") or "").lower() for c in rd.get("gefaehrten") or []}:
        return "gefaehrte"
    if n in {re.sub(r"\s+\d+$", "", str(g.get("name") or "")).lower() for g in (rd.get("kampf") or {}).get("gegner") or [] if not g.get("person")}:
        return "gegner"
    for g in r.get("gegner") or []:
        for b in g.get("name") or []:
            b = str(b).lower()
            if n == b or n in (b + "e", b + "en", b + "n", b + "s", b + "es"):
                return "bestiarium"
    if n in {str(g.get("name") or "").lower() for g in (rd.get("wahrheit") or {}).get("gruppen") or []}:
        return "gruppe"
    ws = [w for w in n.split() if w not in ARTIKEL] or n.split()   # „der Fremde“ is a role like „Fremder“
    if n in ROLLENWORTE or all(w in ROLLENWORTE for w in ws) or len(ws) == 1 and ws[0].endswith(ROLLEN_ENDE):
        return "rolle"
    return ""


_personen = DayCounter(keine_person=0, haendler_karte=0, beruf_rolle=0, stimme_verworfen=0)   # names refused as people, merchants
# given a card, occupations set by a role, the model's age or gender dropped (Live)


def zaehle(k):
    """One more of the day's count k (dungeon_stimmen.learn: stimme_verworfen)."""
    _personen.bump(k)


def no_person(r, rd, name, wo):
    """ist_person with its log line: True when name is refused (the line names where and why, never the name)."""
    why = ist_person(r, rd, name)
    if why:
        print(f"dungeon: wahrheit | person | abgelehnt | {why} | {wo}", flush=True)
        _personen.bump("keine_person")
    return bool(why)


def _beruf_rows(r, rd):
    t = tabellen.table(r, "nsc_beruf") or {}
    w = rd.get("welt")
    return [z for z in t.get("zeilen") or [] if not z.get("welten") or w in z["welten"]]


def _sex_of_word(word, form, row):
    """The gender a word of a name or role gives: the table's feminine or masculine form, a German „-in“ ending."""
    if row.get("w") and form == row["w"].lower() or word.endswith(form + "in") or form.endswith("in") and not row.get("m"):
        return "weiblich"
    return "maennlich" if row.get("m") and form == row["m"].lower() or form in TITEL else ""


def beruf_of(r, rd, text):
    """The occupation a name or role names (([de, en], gender) or (None, "")): a word that is or ends in a form of the
    occupation table (nsc_beruf: t, m, w) or a stem of TITEL („Schattenwächter“ → guard, masculine)."""
    rows = _beruf_rows(r, rd)
    by_en = {z["t"][1]: z for z in rows}
    for word in re.findall(r"\w+", str(text or "").lower()):
        for z in rows:
            for f in {str(x).lower() for x in (z.get("m"), z.get("w"), z["t"][0]) if x}:
                if len(f) >= 4 and (word == f or word.endswith(f) or word.endswith(f + "in")):
                    return list(z["t"]), _sex_of_word(word, f, z)
        for f, en in TITEL.items():
            if en in by_en and (word.endswith(f) or word.endswith(f + "in")):
                z = by_en[en]
                return list(z["t"]), "weiblich" if word.endswith(f + "in") else "maennlich"
    return None, ""


def beruf_wort(r, rd, b, sex):
    """The occupation's German word in the person's gender: the table's form m or w when it has them, else as rolled."""
    z = next((z for z in _beruf_rows(r, rd) if z["t"][1] == b[1]), None) or {}
    return (z.get("w") if sex == "weiblich" else z.get("m") if sex == "maennlich" else None) or b[0]


def gender(r, rd, x, rng=None):
    """The person's one gender (dungeon_stimmen.fix) and age (age), written once on the card, its occupation word made
    to fit, and its fixed looks (looks)."""
    import dungeon_stimmen
    sex = dungeon_stimmen.fix(rd, x)
    b = (x.get("karte") or {}).get("beruf")
    if isinstance(b, list) and len(b) == 2:
        x["karte"]["beruf"] = [beruf_wort(r, rd, b, sex), b[1]]
    age(rd, x)
    looks(r, rd, x, rng)
    return sex


def age(rd, x):
    """The person's one age (x["alter"], kind, jung, mittel, alt), written once: a word of its looks („ist schon recht
    alt“, ALTER_AUSSEHEN), else the one its name gives (dungeon_stimmen._traits, never the model's); a person with an
    adult's occupation (any but KIND_BERUF) is never a child. Returns it."""
    import dungeon_stimmen
    if x.get("alter") in ALTER_WORT:
        return x["alter"]
    k = x.get("karte") or {}
    low = str((k.get("aussehen") or [""])[0]).lower()
    a = next((a for a, ws in ALTER_AUSSEHEN if any(w in low for w in ws)), "") or dungeon_stimmen._traits(x["name"])["alter"]
    if a == "kind" and str((k.get("beruf") or ["", ""])[1]).lower() not in KIND_BERUF:
        a = "jung"
    x["alter"] = a
    return a


def looks(r, rd, x, rng=None):
    """The fixed looks rolled once onto the card (MERKMALE, tables nsc_haar, nsc_augen, nsc_bart, nsc_statur): grey or
    white hair and beard (ALT_FARBE) only when old, a beard only for a man from young on (BART_AB)."""
    k = x.setdefault("karte", {})
    if any(f in k for f in MERKMALE):
        return
    t = lambda f: [z for z in (tabellen.table(r, "nsc_" + f) or {}).get("zeilen") or []   # noqa: E731
                   if (not z.get("welten") or rd.get("welt") in z["welten"]) and (x.get("alter") == "alt" or z.get("farbe") not in ALT_FARBE)]
    for f in MERKMALE:
        if f == "bart" and not (x.get("geschlecht") == "maennlich" and x.get("alter") in BART_AB):
            continue
        zs = t(f)
        if zs:
            k[f] = list((rng or random).choice(zs)["t"])


def on(rd):
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonnsc", rd["owner"])


def card(r, rd, rng=None):
    """A new person's card, rolled by the panel from the tables of the round's world."""
    out = {}
    for k in KARTE:
        x = tabellen.roll(r, "nsc_" + k, rd.get("welt"), rng)
        if x:
            out[k] = x
    return out


def traits(rng=None):
    """Six traits, each 2W4−5 (−3..+3, the middle most often)."""
    rng = rng or random
    return {k: rng.randint(1, 4) + rng.randint(1, 4) - 5 for k in WESEN}


def goals(r, rd, ziel="", rng=None):
    """A goal on each level from the wish table of the round's world; „soon“ is the truth's goal of the person when it has one."""
    out, seen = [], set()
    for e, (_, voll) in EBENEN.items():
        t = [ziel, ziel] if e == "bald" and ziel else None
        for _ in range(6):
            t = t or tabellen.roll(r, "nsc_wunsch", rd.get("welt"), rng)
            if not t or t[0] not in seen:
                break
            t = None
        if t:
            seen.add(t[0])
            out.append({"ebene": e, "t": t, "stand": 0, "voll": voll})
    return out


def trait_words(x, li):
    """The traits that show (1 or more either way) as words: „sehr mutig“, „etwas geizig“."""
    out = []
    for k, v in (x.get("wesen") or {}).items():
        if v and k in WESEN:
            out.append(WESEN_STUFE[min(3, abs(v))][li] + WESEN[k][0 if v > 0 else 1][li])
    return out


def progress(dm, r, rd, rng=None):
    """Between told turns every person moves its nearest open goal by a d6; a goal reached goes into the chronicle
    (without what it was, that stays with host and model) and into rd["ziel_neu"]; a reached goal of today is
    followed by a new one. Returns (moved, reached)."""
    rng = rng or random
    weiter = erreicht = nichts = 0
    rd["ziel_neu"] = []
    for x in (rd.get("nsc") or {}).values():
        z = next((g for g in x.get("ziele") or [] if g["stand"] < g["voll"]), None)
        if not z:
            continue
        if rng.randint(1, 6) < (ZIEL_MUTIG if (x.get("wesen") or {}).get("mut", 0) >= 2 else ZIEL_WURF):
            nichts += 1
            continue
        z["stand"] += 1
        weiter += 1
        if z["stand"] >= z["voll"]:
            erreicht += 1
            rd["ziel_neu"].append({"name": x["name"], "ebene": z["ebene"], "t": list(z["t"])})
            note(rd, f"{x['name']} hat ein Ziel erreicht.", f"{x['name']} has reached a goal.")
            if z["ebene"] == "heute":
                t = tabellen.roll(r, "nsc_wunsch", rd.get("welt"), rng)
                if t and t[0] not in {g["t"][0] for g in x["ziele"]}:
                    x["ziele"] = [g for g in x["ziele"] if g is not z] + [{"ebene": "heute", "t": t, "stand": 0, "voll": EBENEN["heute"][1]}]
    if weiter:
        dm._day.bump("nsc_ziel_weiter", weiter)
    if erreicht:
        dm._day.bump("nsc_ziel_erreicht", erreicht)
    print(f"dungeon: nsc | ziele | {weiter} weiter | {erreicht} erreicht | {nichts} nichts", flush=True)
    return weiter, erreicht


def note(rd, de, en):
    """A line in the chronicle (fixed words of the panel and names the round checked)."""
    rd["chronik"] = ((rd.get("chronik") or []) + [{"n": rd.get("zug", 0), "k": rd.get("kapitel", 1), "t": [de, en]}])[-CHRONIK_MAX:]


def merchant(r, rd, name, paar, rng=None):
    """Review 27.10. Paket 8 (Z4): a merchant with a name of its own becomes a person of the round with a card (its
    occupation the market's kind, paar [de, en], its one gender from the name's form), so portrait, voice and the
    catalog know it; only while the person memory is on and the name is a person (ist_person). Returns the gender."""
    k = str(name or "").lower()
    if not on(rd) or not k or ist_person(r, rd, name):
        return ""
    ns = rd.setdefault("nsc", {})
    if k in ns:
        return (ns[k].get("karte") or {}).get("geschlecht") or ns[k].get("geschlecht") or ""
    import dungeon_stimmen
    x = {"name": name, "karte": card(r, rd, rng), "kanten": [], "haltung": {}, "gesehen": None, "wesen": traits(rng),
         "ziele": goals(r, rd, "", rng)}
    _, sex = beruf_of(r, rd, f"{name} {paar[0]}")
    x["karte"]["beruf"] = list(paar)             # the panel's kind, never a drawn occupation
    dungeon_stimmen.fix(rd, x, sex)
    gender(r, rd, x, rng)
    ns[k] = x
    _personen.bump("haendler_karte")
    print("dungeon: markt | person | neu", flush=True)
    return sex


def sync(r, rd, rng=None):
    """Every person of the truth gets a card (a card or person named with a word for no name leaves); returns how many
    are new."""
    w = rd.get("wahrheit") or {}
    ns = rd.setdefault("nsc", {})
    weg = [k for k in ns if ist_person(r, rd, ns[k].get("name")) == "leer"]
    if weg or any(ist_person(r, rd, p.get("name")) == "leer" for p in w.get("personen") or []):
        for k in weg:                             # a card made before the rule (Dominik 2026-10-28: „keine“) leaves
            x = ns.pop(k)
            for n in {k, x.get("name")}:
                ((rd.get("karte") or {}).get("leute") or {}).pop(n, None)
        w["personen"] = [p for p in w["personen"] if ist_person(r, rd, p.get("name")) != "leer"]
        print(f"dungeon: nsc | leer | {len(weg)} weg", flush=True)
    n = 0
    for p in w.get("personen") or []:
        k = p["name"].lower()
        if k not in ns:
            import dungeon_personen                # a known person of the catalog comes with its own card (Personen-Katalog 3)
            import dungeon_stimmen
            x = dungeon_personen.adopt(r, rd, p["name"])
            if not x:
                x = {"name": p["name"], "karte": card(r, rd, rng), "kanten": [], "haltung": {}, "gesehen": None}
                b, sex = beruf_of(r, rd, f"{p['name']} {p.get('rolle') or ''}")   # a title or role names the occupation
                if b:
                    x["karte"]["beruf"] = b
                dungeon_stimmen.fix(rd, x, sex)          # one gender from now on, never the model's
            ns[k] = x
            n += 1
        else:                                     # Z10: a role naming another occupation sets it (never a catalog card)
            b, _ = beruf_of(r, rd, p.get("rolle") or "")
            c = ns[k].setdefault("karte", {})
            if b and not ns[k].get("katalog") and (c.get("beruf") or ["", ""])[1] != b[1]:
                c["beruf"] = b
                _personen.bump("beruf_rolle")
                print("dungeon: nsc | beruf | nach rolle", flush=True)
        if "wesen" not in ns[k]:                  # traits and goals (Tabletop-Punkt 6), also for cards made before
            ns[k].update(wesen=traits(rng), ziele=goals(r, rd, p.get("ziel") or "", rng))
    for x in ns.values():                         # also cards made before: the gender their portrait was painted in
        gender(r, rd, x, rng)
    return n


def scene(rd):
    """The people of the scene: at the group's place on the map, along with it, or speaking or named in the last
    SZENE_ZUEGE turns."""
    ns = rd.get("nsc") or {}
    if not ns:
        return []
    zug = rd.get("zug", 0)
    near = set()
    k = rd.get("karte")
    if k:
        le = k.get("leute") or {}
        near |= {n.lower() for n, p in le.items() if p.get("ort") == k.get("hier") or p.get("mit")}
    for e in rd.get("log") or []:
        if e.get("art") == "dm" and e.get("n", 0) > zug - SZENE_ZUEGE:
            near |= {str(x.get("name", "")).lower() for x in e.get("npc") or []}
            low = str(e.get("text", "")).lower()
            near |= {n for n in ns if n in low}
    return [n for n in ns if n in near]


# LlamaTale idea 6 (dungeon_wandern): the kinds of places a person of this occupation (the card's beruf, English) heads for
BERUF_ORT = {"trader": ("stadt", "dorf", "basar", "hafen"), "innkeeper": ("taverne",), "miner": ("berg", "hoehle", "mine"),
             "priest": ("kirche", "stadt"), "pilgrim": ("kirche", "krypta", "ruine"), "hunter": ("wald", "sumpf", "dschungel"),
             "forester": ("wald",), "forager": ("wald", "sumpf"), "herb witch": ("sumpf", "wald"), "herder": ("dorf", "muehle"),
             "farmer": ("dorf", "muehle"), "guard": ("festung", "stadt", "turm"), "knight": ("festung", "stadt"),
             "mercenary": ("lager", "festung"), "scholar": ("turm", "ruine", "labor"), "researcher": ("labor", "ruine", "turm"),
             "mystic": ("turm", "krypta"), "smuggler": ("hafen", "hoehle", "lagune"), "smith": ("stadt", "dorf"),
             "artisan": ("stadt", "dorf"), "healer": ("dorf", "stadt", "kirche"), "ghost hunter": ("friedhof", "gruft", "herrenhaus"),
             "pilot": ("hangar", "station"), "navigator": ("hangar", "station", "hafen"), "engineer": ("station", "hangar"),
             "scavenger": ("wrack", "schiffswrack", "krater")}
# LlamaTale idea 7 (switch dungeongesten): a small gesture of a person of the scene by a strong trait (±2 or more)
GESTEN = {("freundlich", 1): ("{n} nickt euch freundlich zu.", "{n} nods at you kindly."),
          ("freundlich", -1): ("{n} mustert euch mit verschränkten Armen.", "{n} eyes you with folded arms."),
          ("ruhig", 1): ("{n} sitzt still da und beobachtet die Gruppe.", "{n} sits still and watches the group."),
          ("ruhig", -1): ("{n} trommelt ungeduldig mit den Fingern.", "{n} drums impatient fingers."),
          ("mut", 1): ("{n} steht breitbeinig da und wartet.", "{n} stands firm and waits."),
          ("mut", -1): ("{n} wirft einen nervösen Blick zur Tür.", "{n} glances nervously at the door."),
          ("grosszuegig", 1): ("{n} schiebt euch wortlos einen Becher Wasser hin.", "{n} silently pushes a cup of water towards you."),
          ("grosszuegig", -1): ("{n} zählt leise ein paar Münzen nach.", "{n} quietly counts a few coins again."),
          ("ehrlich", 1): ("{n} schaut euch offen in die Augen.", "{n} looks you openly in the eye."),
          ("ehrlich", -1): ("{n} tuschelt kurz mit jemandem in der Ecke.", "{n} whispers briefly with someone in the corner."),
          ("treu", 1): ("{n} bleibt dicht bei der Gruppe.", "{n} stays close to the group."),
          ("treu", -1): ("{n} sieht sich nach anderer Gesellschaft um.", "{n} looks around for other company.")}


def ziel_ort(rd, name):
    """The map's place a person heads for (dungeon_karte.wandern, LlamaTale idea 6), by fixed rules: a place of the map
    its open goals name, else the nearest fitting place of its occupation (BERUF_ORT: the person's own place when it
    fits, else the first in the map's order); None without a map, card or fitting place."""
    k = rd.get("karte")
    x = (rd.get("nsc") or {}).get(str(name or "").lower())
    if not k or not x or not isinstance(k.get("orte"), list):
        return None
    orte = k["orte"]
    texte = " ".join(str(t).lower() for z in x.get("ziele") or [] if isinstance(z, dict) and z.get("stand", 0) < z.get("voll", 1)
                     for t in z.get("t") or [])
    for i, o in enumerate(orte):
        n = str(o.get("name", "")).lower()
        if len(n) >= 3 and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", texte):
            return i
    b = (x.get("karte") or {}).get("beruf")
    arten = BERUF_ORT.get(str(b[1]).lower()) if isinstance(b, list) and len(b) == 2 else None
    if not arten:
        return None
    hier = ((k.get("leute") or {}).get(x["name"]) or {}).get("ort")
    if isinstance(hier, int) and 0 <= hier < len(orte) and orte[hier].get("art") in arten:
        return hier
    return next((i for i, o in enumerate(orte) if o.get("art") in arten), None)


def geste(rd, rng=None):
    """A small gesture for the idle time (LlamaTale idea 7, the music thread's dungeon_warten asks when one is due): a
    person of the scene with a strong trait and its fixed line (GESTEN), {nsc, art, text: [de, en]}; None while the
    switch dungeongesten is off or nobody fits. No state changes, no model."""
    import features
    if not on(rd) or not features.allowed("dungeongesten", rd["owner"]):
        return None
    rng = rng or random
    ns = rd.get("nsc") or {}
    wahl = [(k, w, 1 if v > 0 else -1) for k in scene(rd) for w, v in sorted((ns[k].get("wesen") or {}).items())
            if isinstance(v, int) and abs(v) >= 2 and (w, 1 if v > 0 else -1) in GESTEN]
    if not wahl:
        return None
    k, w, sg = rng.choice(wahl)
    name = ns[k]["name"]
    _gesten.bump("gesten")
    print("dungeon: nsc | geste", flush=True)
    return {"nsc": name, "art": f"{w}{'+' if sg > 0 else '-'}", "text": [t.format(n=name) for t in GESTEN[(w, sg)]]}


_gesten = DayCounter(gesten=0)       # gestures given today (Live, through dungeon_wandern.for_live)


def named(x, low):
    """Whether a lower-case action names a person: its whole name, or its last word of three letters or more, also with
    the genitive s („Oskars“, „Oskar's“)."""
    name = x["name"].lower()
    last = name.split()[-1] if name.split() else ""
    return any(re.search(r"(?<!\w)" + re.escape(n) + r"(?:s|['’]s)?(?!\w)", low) for n in {name, last} if len(n) >= 3)


def word(v, li):
    return HALTUNG_WORT[max(HALTUNG[0], min(HALTUNG[1], v))][li]


def ruf(rd, li):
    """A hero's reputation: the mean attitude of the people who know them, as a word; None when nobody knows them."""
    out = {}
    for _, p in _heroes(rd):
        name = p["held"]["name"]
        vs = [x["haltung"][name.lower()] for x in (rd.get("nsc") or {}).values() if name.lower() in x.get("haltung", {})]
        if vs:
            m = sum(vs) / len(vs)
            out[name] = next(w[li] for lim, w in RUF if m <= lim)
    return out


def _heroes(rd):
    return [(pid, p) for pid, p in rd["plaetze"].items() if p.get("held")]


def _shown(rd):
    """The attitudes are kept by the hero's name in small letters; shown with the name as the hero bears it."""
    return {p["held"]["name"].lower(): p["held"]["name"] for _, p in _heroes(rd)}


def check(dm, r, rd, obj, text):
    """The narration's nsc changes by fixed rules: a known person named in the narration (so in its scene), a hero of
    the table named there too, one attitude step per hero and turn, a relation only to a hero or a known person."""
    if not on(rd) or not isinstance(obj, list):
        return []
    ns = {k: x["name"] for k, x in (rd.get("nsc") or {}).items()}
    ns.update({p["name"].lower(): p["name"] for p in (rd.get("wahrheit") or {}).get("personen") or []})   # a card comes in learn
    low = text.lower()
    heroes = {p["held"]["name"].lower(): p["held"]["name"] for _, p in _heroes(rd)}
    out, pairs = [], set()
    for x in obj[:AENDERUNGEN_MAX]:
        if not isinstance(x, dict):
            continue
        k = str(x.get("name") or "").strip().lower()
        if k not in ns or k not in low:              # named in this narration: in its scene
            continue
        held = str(x.get("held") or "").strip().lower()
        if x.get("haltung") in ("besser", "schlechter") and held in heroes and held in low and (k, held) not in pairs:
            pairs.add((k, held))
            out.append({"name": k, "held": held, "schritt": 1 if x["haltung"] == "besser" else -1})
        ziel = str(x.get("ziel") or "").strip().lower()
        if x.get("kante") in KANTEN and ziel != k and (ziel in heroes or ziel in ns) and ziel in low:
            out.append({"name": k, "kante": x["kante"], "ziel": heroes.get(ziel) or ns[ziel]})
    return out


def apply(dm, rd, changes):
    """The checked changes into the round: an attitude a step (the feed says it), a relation (only host and model)."""
    ns = rd.get("nsc") or {}
    heroes = {p["held"]["name"].lower(): (pid, p["held"]["name"]) for pid, p in _heroes(rd)}
    for c in changes:
        x = ns.get(c["name"])
        if not x or "schritt" in c and c["held"] not in heroes:
            print("dungeon: nsc | verworfen | weg", flush=True)
            continue
        if "schritt" in c:
            was = x["haltung"].get(c["held"], 0)
            neu = max(HALTUNG[0], min(HALTUNG[1], was + c["schritt"]))
            if neu == was:
                print("dungeon: nsc | haltung | grenze", flush=True)
                continue
            x["haltung"][c["held"]] = neu
            pid, name = heroes[c["held"]]
            dm._log(rd, "nsc", pid=pid, name=name, nsc=x["name"], haltung=neu,
                    text=[f"{x['name']} ist {name} gegenüber jetzt {word(neu, 0)}.", f"{x['name']} is now {word(neu, 1)} towards {name}."])
            dm._day.bump("nsc_haltung")
            print(f"dungeon: nsc | haltung | {'besser' if neu > was else 'schlechter'}", flush=True)
            if abs(neu) == HALTUNG[1]:
                note(rd, f"{x['name']} ist {name} {word(neu, 0)}.", f"{x['name']} is {word(neu, 1)} towards {name}.")
        else:
            kante = {"art": c["kante"], "ziel": c["ziel"]}
            if kante in x["kanten"]:
                print("dungeon: nsc | kante | schon", flush=True)
                continue
            x["kanten"] = (x["kanten"] + [kante])[-KANTEN_MAX:]
            dm._day.bump("nsc_kanten")
            print(f"dungeon: nsc | kante | {c['kante']}", flush=True)


def chronicle(rd, turn, closed=()):
    """The chronicle lines of this turn by fixed rules from the round's log; returns how many were written."""
    n0 = len(rd.get("chronik") or [])
    ns = rd.get("nsc") or {}
    for k in scene(rd):
        x = ns[k]
        if x.get("gesehen") is None:
            x["gesehen"] = turn
            b = x["karte"].get("beruf") or ["", ""]
            note(rd, f"Begegnung: {x['name']}" + (f" ({b[0]})" if b[0] else ""), f"Met: {x['name']}" + (f" ({b[1]})" if b[1] else ""))
    for e in rd.get("log") or []:
        if e.get("n") != turn or e.get("chronik"):
            continue
        a = e.get("art")
        if a == "kampf" and e.get("was") == "sieg" and e.get("besiegt"):
            note(rd, "Ein mächtiger Gegner ist besiegt." if e.get("boss") else f"Sieg im Kampf über {e['besiegt']} Gegner.",
                 "A mighty foe is defeated." if e.get("boss") else f"Won a fight against {e['besiegt']} foes.")
        elif a == "zustand" and e.get("was") == "tot":
            note(rd, f"{e['name']} ist gefallen.", f"{e['name']} has fallen.")
        elif a == "stufe":
            note(rd, f"{e['name']} erreicht Stufe {e['stufe']}.", f"{e['name']} reaches level {e['stufe']}.")
        elif a == "akt" and e.get("text"):
            note(rd, *e["text"])
        else:
            continue
        e["chronik"] = True
    for f in closed:
        note(rd, f"Erledigt: {f}", f"Done: {f}")
    return len(rd.get("chronik") or []) - n0


def learn(dm, r, rd, story, turn, rng=None):
    """After a told turn: cards for new people, the narration's changes, the chronicle's lines."""
    if not on(rd):
        return
    neu = sync(r, rd, rng)
    if neu:
        print(f"dungeon: nsc | karte | {neu}", flush=True)
    apply(dm, rd, (story or {}).get("nsc") or [])         # checked in dungeon.check_story (check)
    if story:
        progress(dm, r, rd, rng)                            # the people's goals move on (Tabletop-Punkt 6)
    zeilen = chronicle(rd, turn, (story.get("faeden") or {}).get("erledigt") or [] if story else [])
    if zeilen:
        dm._day.bump("chronik", zeilen)
        print(f"dungeon: chronik | {zeilen} zeilen", flush=True)


def facts(r, rd, li, rng=None):
    """For the model, as data: the people of the scene with their cards, relations and attitudes; the others only
    by name; the last lines of the chronicle, the heroes' reputation and fresh names. {} when off."""
    if not on(rd):
        return {}
    ns = rd.get("nsc") or {}
    w = {p["name"].lower(): p for p in (rd.get("wahrheit") or {}).get("personen") or []}
    here, hn = scene(rd), _shown(rd)
    szene = []
    for k in here:
        x, p = ns[k], w.get(k) or {}
        szene.append({"name": x["name"], "geschlecht": _sex_word(rd, x["name"], li),
                      **({"alter": ALTER_WORT[x["alter"]][li]} if x.get("alter") in ALTER_WORT else {}),
                      **{f: p[f] for f in ("rolle", "ziel", "sprache") if p.get(f)},
                      **{f: v[li] for f, v in x["karte"].items()},
                      **({"kanten": [f"{KANTEN[c['art']][li]} {c['ziel']}" for c in x["kanten"]]} if x["kanten"] else {}),
                      **({"haltung": {hn.get(h, h): word(v, li) for h, v in x["haltung"].items()}} if x["haltung"] else {}),
                      **({"wesen": trait_words(x, li)} if trait_words(x, li) else {}),
                      **({"ziele": [{"ebene": EBENEN[g["ebene"]][0][li], "ziel": g["t"][li], "stand": f"{g['stand']}/{g['voll']}"}
                                    for g in x.get("ziele") or [] if g["stand"] < g["voll"]]} if x.get("ziele") else {})})
    out = {"nsc_szene": szene, "nsc_fern": [x["name"] for k, x in ns.items() if k not in here],
           "freie_namen": tabellen.fresh_names(r, rd, rng)}
    if rd.get("ziel_neu"):
        out["nsc_ziel_erreicht"] = [{"name": z["name"], "ziel": z["t"][li]} for z in rd["ziel_neu"]]
    if rd.get("chronik"):
        out["chronik"] = [c["t"][li] for c in rd["chronik"][-CHRONIK_FAKTEN:]]
    if ruf(rd, li):
        out["ruf"] = ruf(rd, li)
    return out


def _sex_word(rd, name, li):
    """The person's gender as a word of the language, for the pronouns of the narration."""
    import dungeon_stimmen
    return dungeon_stimmen.WORTE["geschlecht"][dungeon_stimmen._of(rd, name)["geschlecht"]][li]


def task(rd, lang):
    if not on(rd):
        return ""
    return (AUFGABE[lang] if scene(rd) else "") + (ZIEL_AUFGABE[lang] if rd.get("ziel_neu") else "") + NAMEN_AUFGABE[lang]


def view(rd, host, li):
    """The people the table met (looks, manner, occupation, attitude to each hero), the chronicle and the reputation;
    the host also wish, secret and relations of each (nsc_geheim, dungeon_sicht.NUR_GASTGEBER). None when off."""
    if not on(rd):
        return None, None
    ns, hn = rd.get("nsc") or {}, _shown(rd)
    leute = [{"name": x["name"], **{f: x["karte"][f][li] for f in OFFEN if f in x["karte"]},
              "haltung": [[hn.get(h, h), word(v, li), v] for h, v in sorted(x["haltung"].items())]}
             for x in ns.values() if x.get("gesehen") is not None]
    out = {"leute": leute, "chronik": [{"n": c["n"], "k": c["k"], "t": c["t"][li]} for c in rd.get("chronik") or []],
           "ruf": [[h, w] for h, w in ruf(rd, li).items()]}
    geheim = {x["name"]: {**{f: x["karte"][f][li] for f in KARTE if f not in OFFEN and f in x["karte"]},
                          "kanten": [f"{KANTEN[c['art']][li]} {c['ziel']}" for c in x["kanten"]], "gesehen": x.get("gesehen") is not None,
                          "wesen": trait_words(x, li),
                          "ziele": [[EBENEN[g["ebene"]][0][li], g["t"][li], g["stand"], g["voll"]] for g in x.get("ziele") or []]}
              for x in ns.values()} if host else None
    return out, geheim


def for_live(rs):
    t = _personen.today()
    return {"nsc_karten": sum(len(v.get("nsc") or {}) for v in rs), "chronik_zeilen": sum(len(v.get("chronik") or []) for v in rs),
            "keine_person": t["keine_person"], "haendler_karte": t["haendler_karte"], "beruf_rolle": t["beruf_rolle"],
            "stimme_verworfen": t["stimme_verworfen"]}


def keep(rd):
    """What the next chapter takes over (dungeon_erzaehler.keep_chapter)."""
    return {k: rd[k] for k in ("nsc", "chronik") if rd.get(k)}


def carry(kampagne):
    out = {}
    if isinstance(kampagne.get("nsc"), dict):
        out["nsc"] = kampagne["nsc"]
    if isinstance(kampagne.get("chronik"), list):
        out["chronik"] = kampagne["chronik"][-CHRONIK_MAX:]
    return out
