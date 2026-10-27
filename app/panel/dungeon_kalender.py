"""KI-Dungeon-Master: Kalender der Welt (D&D idea 6, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; the idea of fantasycalendar/Fantasy-Calendar, no licence, only as an idea; own code and own lists).

Every world has twelve months of DAUER days, one or two moons and festivals from the fixed lists below (the children's
table takes the lists of „alle“). The round's first day comes from its start time and title (start); time runs only by fixed rules
(weiter): a stage of a way half a day (way: the stages of dungeon_karte.etappen, a journey of dungeon_reise lost a day
more), a long rest or a night at the inn a whole day (dungeon_rast.rest, dungeon_gold.serve), with the panel's time of day
(dungeon_tageszeit) until the next morning and half a day after its turns. The table shows the date,
the moons, today's festival or the next one within BALD days and the market day of a settlement (every MARKT days); on
a festival a settlement's services cost FEST_AUFSCHLAG percent more (dungeon_gold.price). The narrator gets the date as
data (facts) and may not change it.

Off by default: the admin's switch dungeonkalender (features.py, chat.dungeon_kalender) for the round's host.
State in the round: rd["kalender"] {"start": the first day of the year count, "halbe": half days since}.
Journal: fixed words and numbers („dungeon: kalender | …“), Live only counts.
"""
import hashlib

import features
from common import DayCounter

KEY = "dungeonkalender"
DAUER = 30                 # days a month
JAHR = 12 * DAUER
BALD = 7                   # a festival this many days ahead is announced
MARKT = 7                  # every this many days is market day in a settlement
FEST_AUFSCHLAG = 20        # percent on a settlement's services on a festival
HALB_MAX = 40              # half days one step may add at most

MONATE = {
    "alle": (("Eismond", "Ice Moon"), ("Tauwind", "Thaw Wind"), ("Saatmond", "Seed Moon"), ("Blütenmond", "Blossom Moon"),
             ("Grünmond", "Green Moon"), ("Sonnmond", "Sun Moon"), ("Heumond", "Hay Moon"), ("Erntemond", "Harvest Moon"),
             ("Weinmond", "Wine Moon"), ("Nebelmond", "Mist Moon"), ("Laubfall", "Leaf Fall"), ("Dunkelmond", "Dark Moon")),
    "horror": (("Aschmond", "Ash Moon"), ("Krähenmond", "Crow Moon"), ("Grabmond", "Grave Moon"), ("Bleichmond", "Pale Moon"),
               ("Dornmond", "Thorn Moon"), ("Blutmond", "Blood Moon"), ("Welkmond", "Wither Moon"), ("Schattenmond", "Shadow Moon"),
               ("Seelenmond", "Soul Moon"), ("Nebelmond", "Mist Moon"), ("Totenmond", "Moon of the Dead"), ("Langnacht", "Long Night")),
    "scifi": (("Zyklus Alpha", "Cycle Alpha"), ("Zyklus Beta", "Cycle Beta"), ("Zyklus Gamma", "Cycle Gamma"), ("Zyklus Delta", "Cycle Delta"),
              ("Zyklus Epsilon", "Cycle Epsilon"), ("Zyklus Zeta", "Cycle Zeta"), ("Zyklus Eta", "Cycle Eta"), ("Zyklus Theta", "Cycle Theta"),
              ("Zyklus Iota", "Cycle Iota"), ("Zyklus Kappa", "Cycle Kappa"), ("Zyklus Lambda", "Cycle Lambda"), ("Zyklus My", "Cycle Mu")),
    "piraten": (("Sturmmond", "Storm Moon"), ("Ebbmond", "Ebb Moon"), ("Möwenmond", "Gull Moon"), ("Passatmond", "Trade Wind Moon"),
                ("Korallenmond", "Coral Moon"), ("Flautenmond", "Calm Moon"), ("Rummond", "Rum Moon"), ("Kaperzeit", "Privateer Time"),
                ("Gezeitenmond", "Tide Moon"), ("Nebelbank", "Fog Bank"), ("Wrackmond", "Wreck Moon"), ("Hafenmond", "Harbour Moon")),
}
MONDE = {                  # (name, days of a round of phases)
    "alle": ((("Silbermond", "Silver Moon"), 28),),
    "fantasy": ((("Silbermond", "Silver Moon"), 28), (("Roter Wanderer", "Red Wanderer"), 9)),
    "horror": ((("Bleicher Mond", "Pale Moon"), 28),),
    "scifi": ((("Kleiner Mond", "Lesser Moon"), 11), (("Großer Mond", "Greater Moon"), 30)),
}
PHASEN = (("Neumond", "new"), ("zunehmend", "waxing"), ("zunehmend", "waxing"), ("zunehmend", "waxing"), ("voll", "full"),
          ("abnehmend", "waning"), ("abnehmend", "waning"), ("abnehmend", "waning"))
FESTE = {                  # (month 1-12, day 1-DAUER, name, what the settlement does)
    "alle": ((3, 1, ("Saatfest", "Sowing Feast"), ("Auf dem Platz werden Körner gesegnet und Bänder geflochten.", "Grain is blessed in the square and ribbons are braided.")),
             (6, 15, ("Sonnwendfest", "Midsummer Feast"), ("Feuer brennen bis zum Morgen, alle tanzen.", "Fires burn till morning, everyone dances.")),
             (8, 20, ("Erntefest", "Harvest Feast"), ("Lange Tische, frisches Brot und Musik bis spät.", "Long tables, fresh bread and music till late.")),
             (12, 30, ("Laternennacht", "Lantern Night"), ("In jedem Fenster brennt eine Laterne gegen die Dunkelheit.", "A lantern burns in every window against the dark."))),
    "scifi": ((1, 1, ("Gründungstag", "Founding Day"), ("Die Station feiert ihre Gründung mit Lichtern auf jedem Deck.", "The station celebrates its founding with lights on every deck.")),
              (7, 10, ("Andocktag", "Docking Day"), ("Fremde Schiffe docken an, auf dem Markt gibt es Waren von weit her.", "Strange ships dock, the market has goods from far away."))),
    "piraten": ((4, 4, ("Tag der Freibeuter", "Freebooters' Day"), ("Im Hafen wehen bunte Flaggen, alle Krüge sind voll.", "Colourful flags fly in the harbour, every mug is full.")),
                (9, 13, ("Gezeitenfest", "Tide Feast"), ("Boote voller Blumen treiben aufs Meer hinaus.", "Boats full of flowers drift out to sea."))),
}

_day = DayCounter(halbe_tage=0, feste=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def _welt(r, rd, table):
    import dungeon
    w = rd.get("welt", "")
    return table["alle"] if dungeon.kids(r, rd) or w not in table else table[w]


def ensure(rd):
    """The round's calendar: the first day fixed from the round's start time and title."""
    k = rd.get("kalender")
    if not isinstance(k, dict):
        start = int.from_bytes(hashlib.sha256(f"{rd.get('made', 0)}|{rd.get('titel', '')}".encode()).digest()[:4], "big") % JAHR
        k = rd["kalender"] = {"start": start, "halbe": 0}
    return k


def tag(rd):
    """The day count since the year 1 began (pure on the calendar)."""
    k = ensure(rd)
    return k["start"] + k["halbe"] // 2


def _feste(r, rd):
    import dungeon
    w = rd.get("welt", "")
    return FESTE["alle"] if dungeon.kids(r, rd) or w not in FESTE else FESTE[w]


def _fest_an(r, rd, d):
    m, t = d % JAHR // DAUER + 1, d % DAUER + 1
    return next((f for f in _feste(r, rd) if (f[0], f[1]) == (m, t)), None)


def heute(r, rd):
    """Today: {"tag", "monat", "jahr", "monde", "fest", "bald", "markt"} with the names as [de, en]."""
    import dungeon_gold
    d = tag(rd)
    monde = [{"name": list(n), "phase": list(PHASEN[d % p * len(PHASEN) // p])} for n, p in _welt(r, rd, MONDE)]
    fest = _fest_an(r, rd, d)
    bald = next(({"name": list(f[2]), "in": i} for i in range(1, BALD + 1) for f in [_fest_an(r, rd, d + i)] if f), None)
    return {"tag": d % DAUER + 1, "monat": list(_welt(r, rd, MONATE)[d % JAHR // DAUER]), "jahr": d // JAHR + 1, "monde": monde,
            "fest": {"name": list(fest[2]), "satz": list(fest[3])} if fest else None, "bald": bald,
            "markt": bool(dungeon_gold.here(rd)) and d % MARKT == 0}


def text(r, rd, li):
    """The date as one line: „3. Tag des Erntemonds · Silbermond voll“."""
    h = heute(r, rd)
    datum = f"{h['tag']}. Tag im {h['monat'][0]}" if not li else f"Day {h['tag']} of {h['monat'][1]}"
    return " · ".join([datum] + [f"{m['name'][li]} {m['phase'][li]}" for m in h["monde"]])


MORGEN = ("rast", "gasthaus")   # with the time of day of the panel (dungeon_tageszeit) these end at the next morning


def weiter(r, rd, halbe, warum):
    """Time runs by a fixed rule: halbe half days for warum (weg, reise, rast, gasthaus, zeit: the turns of a half day
    of dungeon_tageszeit); a festival reached counts. Runs while the calendar or the time of day is on."""
    import dungeon_tageszeit as tageszeit
    if not (on(rd) or tageszeit.on(rd)) or not isinstance(halbe, int) or halbe <= 0:
        return
    k = ensure(rd)
    if warum in MORGEN and tageszeit.on(rd):
        halbe = 2 - k["halbe"] % 2               # sleep until the next morning: the next even half
    before = tag(rd)
    k["halbe"] = min(10 ** 7, k["halbe"] + min(halbe, HALB_MAX))
    feste = sum(1 for d in range(before + 1, tag(rd) + 1) if _fest_an(r, rd, d))
    _day.bump("halbe_tage", min(halbe, HALB_MAX))
    if feste:
        _day.bump("feste", feste)
    print(f"dungeon: kalender | {min(halbe, HALB_MAX)} halbe tage | {warum}" + (" | fest" if feste else ""), flush=True)
    if warum in MORGEN and tageszeit.on(rd):
        tageszeit.sync(rd)                       # between turns: the morning is told on the next turn


def way(r, rd, von, reise):
    """A way on the map: half a day a stage, a journey that went astray a day more; nothing inside a vault."""
    import dungeon_karte
    import dungeon_tageszeit as tageszeit
    k = rd.get("karte") or {}
    if not (on(rd) or tageszeit.on(rd)) or dungeon_karte.vault(rd) or not isinstance(von, int) or not 0 <= von < len(k.get("orte") or []) or von == k.get("hier"):
        return
    e = reise["etappen"] if reise else dungeon_karte.etappen(k, von, k["hier"])
    weiter(r, rd, e + (2 if reise and reise["ergebnis"] == "verirrt" else 0), "reise" if reise else "weg")


def aufschlag(r, rd):
    """Percent on a settlement's services today: FEST_AUFSCHLAG on a festival, else 0."""
    import dungeon_gold
    return FEST_AUFSCHLAG if on(rd) and dungeon_gold.here(rd) and heute(r, rd)["fest"] else 0


def facts(r, rd):
    """The date for the narrator, only as data."""
    if not on(rd):
        return {}
    li = 1 if rd.get("lang") == "en" else 0
    h = heute(r, rd)
    return {"kalender": {"datum": text(r, rd, li), "fest": h["fest"]["name"][li] if h["fest"] else "",
                         "fest_heute": h["fest"]["satz"][li] if h["fest"] else "", "markttag": h["markt"],
                         "fest_bald": f"{h['bald']['name'][li]} in {h['bald']['in']} " + ("Tagen" if not li else "days") if h["bald"] else ""}}


AUFGABE = {
    "de": (" Steht in den Fakten kalender, ist das Datum fest: nenne es, wenn es passt, ändere es nie und lass keine Zeit "
           "springen; ein Fest heute oder bald und ein Markttag dürfen die Szene färben."),
    "en": (" When the facts hold kalender, the date is fixed: name it when it fits, never change it and never let time jump; "
           "a festival today or soon and a market day may colour the scene."),
}


def task(rd, lang):
    return AUFGABE[lang] if on(rd) else ""


def view(r, rd):
    """What the table shows on top: the date line, today's festival, the next one, the market day; None while off."""
    if not on(rd):
        return None
    li = 1 if rd.get("lang") == "en" else 0
    h = heute(r, rd)
    return {"text": text(r, rd, li), "fest": h["fest"]["name"][li] if h["fest"] else "", "satz": h["fest"]["satz"][li] if h["fest"] else "",
            "bald": h["bald"]["name"][li] if h["bald"] else "", "in": h["bald"]["in"] if h["bald"] else 0, "markt": h["markt"],
            "aufschlag": aufschlag(r, rd)}


def for_live():
    """Numbers only: half days passed and festivals reached today."""
    t = _day.counts()
    return {k: t[k] for k in ("halbe_tage", "feste")}
