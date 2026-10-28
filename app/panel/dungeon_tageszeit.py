"""KI-Dungeon-Master: Tageszeit vom Panel (LlamaTale-Idee 1, Dominik 2026-10-27 „1-7“; the idea of LlamaTale's clock,
LGPL-3.0, only as an idea, own code).

The time of day (dungeon.TAGESZEITEN: morgen, tag, abend, nacht) comes from fixed rules, never from the model: the
half days of the world's calendar (dungeon_kalender, rd["kalender"]["halbe"]; an even half is the day, an odd one the
night) and ZUEGE told turns per section (morgen, then tag; abend, then nacht). After 2 × ZUEGE turns of one half the
calendar runs half a day on by itself (kalender.weiter „zeit“); a way, a journey, a long rest or the inn move it as
before, a long rest and the inn always until the next morning (kalender.weiter). The fixed effects:
  - at night a settlement's shops are shut (LADEN_ZU: smith with its rune services, lesson, improving gear, healer, and a
    merchant's goods);
    the inn, the rumour of the taproom and hiring a companion stay open (dungeon_gold.serve, dungeon.shop);
  - at night outside a vault and a settlement, a hero without darkvision (dungeon_alarm.DUNKELSICHT) and without a
    light in the group (a light of dungeon_alarm: the light spell, a lasting thing, a torch in a bag) rolls checks at a
    disadvantage, as in a dark vault (dungeon.roll; in a vault dungeon_alarm counts the torches);
  - at night the foes offered prefer those of the night table (bestiary "nacht": true, dungeon_kampf.offer), when
    at least ANGEBOT of them fit.
The narrator gets the time of day as data (facts szene.tageszeit) and, on the first turn after a change, tageszeit_neu
to tell the change in one or two sentences; the model's szene.tageszeit is ignored while this is on (one source).

Off by default: the admin's switch dungeontageszeit (features.py, chat.dungeon_tageszeit) for the round's host; off,
the narrator reports the time of day as before (only forward, dungeon.tageszeit_ok).
State in the round: rd["tageszeit"] (the section, also read by dungeon_dingbild and dungeon_gold), rd["uhr"]
{"halbe": the calendar's half days it counted from, "zuege": told turns in this half, "wechsel": the turn the change is
told on}. Journal: fixed words and numbers („dungeon: tageszeit | …“), Live only counts.
"""
import features
from common import DayCounter

KEY = "dungeontageszeit"
ZUEGE = 6                  # told turns per section: a half day is 2 × ZUEGE turns
LADEN_ZU = ("schmied", "lehre", "verbessern", "heiler", "sockel", "loesen", "verschmelzen")   # shut at night; "markt" a merchant's goods
NAMEN = {"morgen": (("Morgen", "Morning"), "🌅"), "tag": (("Tag", "Day"), "☀️"),
         "abend": (("Abend", "Evening"), "🌇"), "nacht": (("Nacht", "Night"), "🌙")}

_day = DayCounter(wechsel=0, dunkel=0, zu=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def stand(rd):
    """The section by the rules: the calendar's half and the turns told in it."""
    import dungeon
    import dungeon_kalender
    halb = dungeon_kalender.ensure(rd)["halbe"] % 2
    u = rd.get("uhr") or {}
    return dungeon.TAGESZEITEN[halb * 2 + (1 if u.get("zuege", 0) >= ZUEGE else 0)]


def sync(rd, wann=None):
    """The time of day after the calendar moved or a turn was counted: a new half begins with no turns told; a change
    is logged and told to the narrator on turn wann (the current turn by default)."""
    import dungeon_kalender
    k = dungeon_kalender.ensure(rd)
    u = rd.get("uhr")
    if not isinstance(u, dict) or not isinstance(u.get("zuege"), int) or not isinstance(u.get("halbe"), int):
        u = rd["uhr"] = {"halbe": k["halbe"], "zuege": 0}
    if u["halbe"] != k["halbe"]:
        u.update(halbe=k["halbe"], zuege=0)
    neu = stand(rd)
    if neu != rd.get("tageszeit"):
        rd["tageszeit"] = neu
        u["wechsel"] = rd.get("zug", 0) if wann is None else wann
        _day.bump("wechsel")
        print(f"dungeon: tageszeit | {neu} | panel", flush=True)


def zug(r, rd):
    """A told turn (dungeon.apply): one turn more in this half; after 2 × ZUEGE the calendar runs half a day on. The
    change is told on the next turn."""
    import dungeon_kalender
    sync(rd, rd.get("zug", 0) + 1)               # a way of this turn moved the calendar: a new half
    u = rd["uhr"]
    u["zuege"] += 1
    if u["zuege"] >= 2 * ZUEGE:
        dungeon_kalender.weiter(r, rd, 1, "zeit")   # the new half starts with no turns
    sync(rd, rd.get("zug", 0) + 1)


def nachts(rd):
    return on(rd) and rd.get("tageszeit") == "nacht"


def zu(rd, was):
    """Whether this offer of a settlement is shut now: at night LADEN_ZU and a merchant's goods ("markt")."""
    if nachts(rd) and (was in LADEN_ZU or was == "markt"):
        _day.bump("zu")
        print(f"dungeon: tageszeit | zu | {was}", flush=True)
        return True
    return False


def dunkel(r, rd, h):
    """Whether this hero's check is in the dark of the night (dungeon.roll, counted): outside a vault and a settlement,
    without darkvision and without a light in the group."""
    import dungeon_alarm
    import dungeon_gold
    import dungeon_karte
    if not nachts(rd) or dungeon_karte.vault(rd) or dungeon_gold.here(rd) or h.get("volk") in dungeon_alarm.DUNKELSICHT:
        return False
    lasting, burn, _ = dungeon_alarm._lights(r, rd)
    if lasting or burn:
        return False
    _day.bump("dunkel")
    print("dungeon: tageszeit | dunkel", flush=True)
    return True


def night_foes(rd, fit, angebot):
    """dungeon_kampf.offer: at night the foes of the night table when enough of them fit, else all that fit (pure)."""
    if not nachts(rd):
        return fit
    n = [g for g in fit if g.get("nacht") is True]
    return n if len(n) >= angebot else fit


TASK = {
    "de": " Die Tageszeit setzt das Panel (szene.tageszeit in den Fakten), lass szene.tageszeit leer und ändere sie nie.",
    "en": " The panel sets the time of day (szene.tageszeit in the facts), leave szene.tageszeit empty and never change it.",
}
NEU_TASK = {"de": " Steht tageszeit_neu in den Fakten, erzähle den Übergang in ein oder zwei Sätzen.",   # only with it (T20)
            "en": " When the facts hold tageszeit_neu, tell the change in one or two sentences."}
MELDEN = {
    "de": " Ändert sich die Tageszeit, melde sie in szene.tageszeit (morgen, tag, abend, nacht).",
    "en": " When the time of day changes, report it in szene.tageszeit (morgen, tag, abend, nacht).",
}


def task(rd, lang):
    """The narrator's sentence on the time of day: the panel's while on, else the model reports it."""
    return TASK[lang] + (NEU_TASK[lang] if facts(rd) else "") if on(rd) else MELDEN[lang]


def facts(rd):
    """tageszeit_neu on the first turn after a change, only as data."""
    if not on(rd) or (rd.get("uhr") or {}).get("wechsel") != rd.get("zug", 0):
        return {}
    li = 1 if rd.get("lang") == "en" else 0
    return {"tageszeit_neu": NAMEN[rd.get("tageszeit", "tag")][0][li]}


def view(rd):
    """What the table shows on top: the section, its sign and the turns until the next; None while off."""
    if not on(rd):
        return None
    li = 1 if rd.get("lang") == "en" else 0
    u = rd.get("uhr")
    z = rd.get("tageszeit", "tag") if isinstance(u, dict) else stand(rd)   # before the first narration: by the rules
    u = u if isinstance(u, dict) else {}
    return {"zeit": z, "name": NAMEN[z][0][li], "zeichen": NAMEN[z][1], "zuege": max(1, ZUEGE - u.get("zuege", 0) % ZUEGE),
            "dunkel": z == "nacht"}


def for_live():
    """Numbers only: changes of the time of day, checks in the dark of the night and shut shops today."""
    t = _day.counts()
    return {k: t[k] for k in ("wechsel", "dunkel", "zu")}
