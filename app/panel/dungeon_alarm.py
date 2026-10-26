"""KI-Dungeon-Master: Alarm und Fackeln im Gewölbe (D&D ideas round 2, idea 6, Dominik 2026-10-26 „1-9 umsetzten
reihenfolge überlasse ich dir.“; the alarm clock and the torch count of the tabletop dungeon crawl, only as an idea,
own code).

The map's vault (dungeon_karte) counts by fixed rules of the panel, the model only tells:
  Alarm 0 to STUFEN per vault. Noise raises it (laerm, through dungeon_karte.laerm): a fight, a door, the price „Lärm“
  of a near miss, a failed sneak (the main thread's events) and a trap sprung (the map's own), each from GRUENDE.
  At STREIFE a patrol comes once: the next plain room the group enters holds guardian foes (dungeon_karte._enter_room).
  At STUFEN the master is ready: his room gets one more foe at his side. A vault filled again (dungeon_karte.refill)
  is calm again.
  Light: entering a vault the panel lights a torch of the group by itself, a lasting light first (a hero with the
  spell LICHT_ZAUBER, a thing of the catalog with "licht": -1, the Ewige Fackel, never burns out), else the first
  thing with "licht" > 0 in a hero's bag (holzfackel, leuchtstab: 4 rooms), which is used up. Every room the group
  walks into burns one; at 0 the next one is lit, without one the vault is dark: checks of a hero without darkvision
  (DUNKELSICHT, by people) at a disadvantage (dunkel, dungeon.roll).
The view carries karte.alarm (0 to 6) and karte.fackel (rooms left, -1 lasting, 0 dark), both null outside a vault;
the facts tell the model the alarm and whether it is dark.

Off by default: the admin's switch dungeonalarm (features.py, chat.dungeon_alarm) for the round's host.
State: in the vault v["alarm"], v["streife"] (0 none yet, 1 coming, 2 came), v["licht"], v["licht_von"] [de, en].
Journal: fixed words and numbers („dungeon: alarm | …“), Live only counts.
"""
import features
from common import DayCounter

KEY = "dungeonalarm"
STUFEN = 6
STREIFE = 3
GRUENDE = ("kampf", "tuer", "preis", "schleichen_patzer", "falle")
LAERM_MAX = 3                     # one event raises the alarm by at most this much
PLAIN = ("gang", "kammer")         # the kinds of room a patrol walks through
LICHT_ZAUBER = "lichtzauber"
DUNKELSICHT = ("zwerg", "elf", "ork", "gnom", "halbelf", "tiefling")   # the peoples that see in the dark (SRD 5.1)

_day = DayCounter(laerm=0, streifen=0, bereit=0, fackeln=0, dunkel=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def _vault(rd):
    import dungeon_karte
    return dungeon_karte.vault(rd) if on(rd) else None


def laerm(rd, n, grund):
    """Noise in the vault where the group is: the alarm up by n (1 to LAERM_MAX) for a grund of GRUENDE; at STREIFE a
    patrol is on its way, at STUFEN the master is ready (told at the table). Returns the alarm, None outside a vault
    or switched off."""
    import dungeon_karte
    v = _vault(rd)
    if v is None:
        return None
    if grund not in GRUENDE or not isinstance(n, int) or isinstance(n, bool) or n < 1:
        print("dungeon: alarm | verworfen", flush=True)
        return v.get("alarm", 0)
    vor = v.get("alarm", 0)
    v["alarm"] = min(STUFEN, vor + min(n, LAERM_MAX))
    _day.bump("laerm")
    print(f"dungeon: alarm | {grund} | {v['alarm']}", flush=True)
    if vor < STREIFE <= v["alarm"] and not v.get("streife"):
        v["streife"] = 1
        dungeon_karte._say(rd, "Irgendwo im Gewölbe schlägt eine Glocke. Eine Streife ist unterwegs.",
                           "Somewhere in the vault a bell tolls. A patrol is on its way.")
    if vor < STUFEN <= v["alarm"]:
        dungeon_karte._say(rd, "Das ganze Gewölbe ist wach. Sein Herr erwartet euch.", "The whole vault is awake. Its master awaits you.")
    return v["alarm"]


def streife(rd, room):
    """Whether the patrol stands in this room the group walks into: once, after STREIFE, in a plain room (PLAIN: no
    guardian, master, trap, riddle or treasure of its own); dungeon_karte puts guardian foes there."""
    v = _vault(rd)
    if not v or v.get("streife") != 1 or room["art"] not in PLAIN or room.get("streife"):
        return False
    v["streife"] = 2
    _day.bump("streifen")
    print("dungeon: alarm | streife", flush=True)
    return True


def bereit(rd, room):
    """Whether the master's room gets one more foe now: the alarm at STUFEN, once per room."""
    v = _vault(rd)
    if not v or v.get("alarm", 0) < STUFEN or room["art"] != "boss" or room.get("fertig") or room.get("bereit"):
        return False
    room["bereit"] = True
    _day.bump("bereit")
    print("dungeon: alarm | herr bereit", flush=True)
    return True


def _lights(r, rd):
    """The light the group carries: (lasting, [(pid, item, rooms, name)]) by a fixed order, the spell and lasting
    things first, then the bag's torches."""
    import dungeon
    cat = {c["id"]: c for c in r.get("gegenstaende") or []}
    li = 1 if rd.get("lang") == "en" else 0
    lasting, burn = None, []
    for pid, p in dungeon.seated(rd):
        h = p["held"]
        if h.get("tot"):
            continue
        if LICHT_ZAUBER in (h.get("faehigkeiten") or []):
            lasting = lasting or ["Lichtzauber", "Light spell"]
        for it in h.get("tasche") or []:
            c = cat.get(it.get("id")) or {}
            n = c.get("licht")
            if it.get("id") == LICHT_ZAUBER:
                lasting = lasting or ["Lichtzauber", "Light spell"]
            elif n == -1:
                lasting = lasting or list(c["name"])
            elif isinstance(n, int) and not isinstance(n, bool) and n > 0:
                burn.append((pid, it, n, list(c["name"])))
    return lasting, burn, li


def anzuenden(r, rd):
    """A new light when none burns (entering the vault, a torch burnt down): a lasting one, else a torch of the bag
    used up; else the vault is dark (told once)."""
    import dungeon_karte
    v = _vault(rd)
    if v is None or v.get("licht", 0) != 0:
        return
    lasting, burn, li = _lights(r, rd)
    if lasting:
        v["licht"], v["licht_von"] = -1, lasting
    elif burn:
        pid, it, n, name = burn[0]
        rd["plaetze"][pid]["held"]["tasche"].remove(it)
        v["licht"], v["licht_von"] = n, name
        _day.bump("fackeln")
        dungeon_karte._say(rd, f"{rd['plaetze'][pid]['held']['name']} entzündet: {name[0]}.", f"{rd['plaetze'][pid]['held']['name']} lights: {name[1]}.")
    elif "licht_von" in v and v["licht_von"] is None:
        return                                   # dark already: told before
    else:
        v["licht_von"] = None
        _day.bump("dunkel")
        dungeon_karte._say(rd, "Kein Licht mehr. Wer nicht im Dunkeln sieht, würfelt mit Nachteil.",
                           "No light left. Whoever cannot see in the dark rolls at a disadvantage.")
    print(f"dungeon: alarm | licht | {v['licht']}", flush=True)


def schritt(r, rd):
    """A room walked into: a burning torch is one room shorter; burnt down, the next one is lit."""
    v = _vault(rd)
    if v is None:
        return
    if v.get("licht", 0) > 0:
        v["licht"] -= 1
    anzuenden(r, rd)


def dunkel(r, rd, h):
    """Whether this hero rolls in the dark: in a vault without light and not of a people with darkvision (pure)."""
    v = _vault(rd)
    return bool(v) and v.get("licht", 0) == 0 and h.get("volk") not in DUNKELSICHT


def ruhe(v):
    """A vault filled again (dungeon_karte.refill) is calm again; its light is the group's and stays."""
    v["alarm"], v["streife"] = 0, 0


def view(rd):
    """The fields of the map's view: alarm and fackel in a vault (the music thread's bell and flicker), else None."""
    v = _vault(rd)
    if v is None:
        return {"alarm": None, "fackel": None}
    return {"alarm": v.get("alarm", 0), "fackel": v.get("licht", 0), "licht_von": (v.get("licht_von") or ["", ""])[1 if rd.get("lang") == "en" else 0]}


def facts(rd):
    """What the model may know: the alarm and the light, for the narration (data, never an order)."""
    v = _vault(rd)
    if v is None:
        return {}
    li = 1 if rd.get("lang") == "en" else 0
    out = {"alarm": f"{v.get('alarm', 0)}/{STUFEN}", "licht": ("dunkel", "dark")[li] if v.get("licht", 0) == 0 else ("hell", "lit")[li]}
    if v.get("streife") == 1:
        out["streife"] = ("unterwegs", "on its way")[li]
    if v.get("alarm", 0) >= STUFEN:
        out["herr"] = ("bereit", "ready")[li]
    return out


def for_live():
    """Numbers only: noise, patrols, masters ready, torches lit and darkness today."""
    t = _day.counts()
    return {k: t[k] for k in ("laerm", "streifen", "bereit", "fackeln", "dunkel")}
