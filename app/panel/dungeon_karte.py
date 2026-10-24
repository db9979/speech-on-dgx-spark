"""Die Karte des KI-Dungeon-Masters (plan dungeon-master/karte-plan.md, Dominik 2026-10-23 „karte 2“): a net of
places per chapter and random vaults as a grid of rooms, rolled and kept by the panel, never by the model.

- At the start of a round or chapter the panel rolls ORTE places on a plane in one of the FORMEN of land (scattered,
  a river valley, around a lake, two realms with one crossing, a coast), a minimum distance apart, joins them by a
  spanning tree plus a few short ways that cross no other (at most GRAD ways per place), puts the start in the west
  and the goal farthest away and gives every act of the story a place on the way there. Names come first from the
  story's places, then from the world's kinds of places (ortsarten in the rules, the admin adds his own): a name of
  the list or, for a kind with teile, a stem of the world (silben) joined with one of its endings.
- Going a way for the first time, the panel rolls an encounter on the way (begegnungen, UNTERWEGS percent): quiet,
  weather or a hint for the narration, a foe (the fight's offer, dungeon_kampf), a find from the catalog, a merchant.
- The model gets only the place it stands at, the ways from there with their direction and the direction of the next
  act's place (facts); it names in szene.ort_id one of those ways when the group goes on. Any other id leaves the
  group where it is (journal „dungeon: karte | verworfen“). The place's name is the panel's, whatever the model wrote.
- Fog: a place is visited, known (a neighbour of a visited one) or unknown; the players' view carries only visited
  and known places, an unknown one only as a stub with „?“ (view), and the model never hears of it.
- A vault (below a kind with gewoelbe, or rolled by the host's „Gewölbe würfeln“; the group goes in only when the
  narration names the way "ein", never just by arriving or by the button) is a grid of RAEUME rooms (RASTER) grown from the
  entrance at the west edge in one of the GEWOELBE forms (branching, a long corridor with side rooms, a maze with
  loops, a cross around a hall, a winding cave), the master of the vault in the farthest room, a treasure next to it,
  a trap, a riddle, a guardian, a spring and an altar when there is room, the rest by weight from the room table of
  the world. Entering a trap room the panel rolls a save, d20 + value for every hero against the
  trap's difficulty (raised by the group's level): failed the whole damage, made half (armour does not count); a riddle door keeps its ways shut until an
  action holds one of the fixed answers (umlauts and case do not count), after VERSUCHE turns the hint is shown; a
  guardian or the master keeps its ways shut until the fight is won: entering, the panel picks the room's foes from the
  Bestiarium of the world by the group's level (_room_foes) and offers only them (rd["raum_gegner"]); the fight's
  victory (rd["sieg"], dungeon_kampf) opens the room; a treasure room gives
  the catalog's loot „truhe“ once, a spring heals every hero (QUELLE), an altar blesses one value (ALTAR). The answer never reaches the model, only whether it was found.

Pictures instead of signs (Dominik 2026-10-23 „sollten wir auch bilder generieren und keine emojies verwenden“, option
2), with „Bilder für Ausrüstung und Zauber“ (dungeon_dingbild.py: its switch, „Bilder malen“, the night, the button,
the day's limit, the sweep): one picture per kind of place and kind of room in the style of every world it belongs to
(bilder: fixed prompts from the English names, named ding-<hash> like the catalog's items), and an own picture of
every visited place of a running round whose host has „Bilder malen“ (queue_orte: the kind, the place's name and the
round's style, checked by dungeon.picture_text, counted to the game's day limit, named ort-<hash>). Until a picture is
there the place keeps its sign. A seat gets the picture's name in view ("b"); an ort- picture is served only to a
profile or a guest's seat of a round whose map names it (may_see).

The round keeps it all in rd["karte"] (dungeon-runden.json, nothing new on disk). Journal: fixed words and numbers.

    POST /api/profile/dungeon/{rid}/karte   host: {was: neu|gewoelbe} roll the map again (before the first step)
                                            or a vault's entrance at the current place
"""
import asyncio
import hashlib
import json
import math
import os
import random
import re
import time
import unicodedata

from fastapi import APIRouter, Depends, Request

import guard
from core import assistant, browser_profile, json_body

router = APIRouter()
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dungeon_karte.json")

LISTS = ("ortsarten", "silben", "raeume", "fallen", "raetsel", "begegnungen")
RAUM_ARTEN = ("eingang", "gang", "kammer", "falle", "raetsel", "schatz", "waechter", "boss", "quelle", "altar")
BEGEGNUNG_ARTEN = ("nichts", "wetter", "hinweis", "fund", "gegner", "haendler")
FORMEN = ("verstreut", "tal", "see", "zwei_reiche", "kueste")
GEWOELBE = ("verzweigt", "gang", "labyrinth", "kreuz", "hoehle")
ORTE = (8, 15)            # places of one chapter (more with more acts)
FLAECHE = (1000, 600)     # the plane the places lie on (the view's SVG uses it as viewBox)
RAND = 60                 # no place nearer to the edge
ABSTAND = 150             # places at least this far apart
GRAD = 4                  # ways of one place at most
QUER = 260                # an extra way at most this long
RAUME = (5, 12)           # rooms of a vault
RASTER = ((6, 9), (4, 6))   # the grid a vault lies on: columns, rows
UNTERWEGS = 40            # percent: an encounter on a way gone for the first time
QUELLE = (2, 6)           # life a spring gives every hero
ALTAR = (1, 3)            # an altar's blessing: bonus 1 for 3 turns
VERSUCHE = 3              # turns at a riddle before the hint is shown
NAME_MAX = 40
SATZ_MAX = 160
FRAGE_MAX = 240
STUB = 0.42               # how far a way into the unknown is drawn
BLICK = 560               # the seat's view of the plane is at least this wide (view: box)
ORT_EN = "map vignette art, one single place seen from a high angle, a small round scene, plain light background"
RAUM_EN = "dungeon art, one room of an underground vault seen from a high angle, no people"
_ID = re.compile(r"(?:o|r)[0-9]{1,2}|aus|ein")
_WORD = re.compile(r"[a-z0-9_]{1,24}")
RICHTUNG = (("Osten", "east"), ("Südosten", "south-east"), ("Süden", "south"), ("Südwesten", "south-west"),
            ("Westen", "west"), ("Nordwesten", "north-west"), ("Norden", "north"), ("Nordosten", "north-east"))
AUFGABE = {
    "de": "Die Karte führt das Panel (karte in den Fakten). Zieht die Gruppe weiter, setze szene.ort_id auf die id eines "
          "Wegs aus karte.wege und erzähle den Weg dorthin; andere Orte gibt es nicht, erfinde keine. Bleibt sie, lass "
          "ort_id leer. Nenne Orte und Räume nur mit ihren Namen aus der Karte. Steht in karte eine Falle, ein Rätsel "
          "oder Gegner, erzähle, was das Panel entschieden hat (Gegner kommen nur aus dem Angebot); die Lösung eines Rätsels kennst du nicht, verrate "
          "keine.",
    "en": "The panel keeps the map (karte in the facts). When the group moves on, set szene.ort_id to the id of a way "
          "from karte.wege and narrate the way there; there are no other places, invent none. When it stays, leave "
          "ort_id empty. Name places and rooms only by their names from the map. When karte holds a trap, a riddle or "
          "foes, narrate what the panel decided (foes come only from the offer); you do not know a riddle's answer, give none away."}


# ---------------------------------------------------------------- the tables (shipped; the admin's own on top)
def tables():
    """The shipped tables, merged into the game's rules (dungeon._base_rules)."""
    with open(DATA) as f:
        return json.load(f)


def _pair(x, n):
    return isinstance(x, list) and len(x) == 2 and all(isinstance(s, str) and 0 < len(s.strip()) <= n for s in x)


def check_rules(r):
    """The map's tables by fixed rules: German sentences of what is wrong (dungeon.check_rules adds them)."""
    err = []

    def need(ok, text):
        if not ok:
            err.append(text)
    welten = {w.get("id") for w in r.get("welten") or [] if isinstance(w, dict)}
    werte = {w.get("id") for w in r.get("werte") or [] if isinstance(w, dict)}
    oa = [x for x in r.get("ortsarten") or [] if isinstance(x, dict)]
    for x in oa:
        n = x.get("namen")
        need(isinstance(n, list) and len(n) == 2 and all(isinstance(v, list) and 1 <= len(v) <= 20 and all(
            isinstance(s, str) and 2 <= len(s) <= NAME_MAX for s in v) for v in n),
             f"ortsarten {x.get('id')}: namen als [[deutsch …], [englisch …]], je 1 bis 20 Namen mit höchstens {NAME_MAX} Zeichen")
        need(isinstance(x.get("welten"), list) and x["welten"] and set(x["welten"]) <= welten, f"ortsarten {x.get('id')}: welten aus den Welten")
        need(all(isinstance(x.get(k, False), bool) for k in ("gewoelbe", "start")), f"ortsarten {x.get('id')}: gewoelbe und start true oder false")
    for w in welten:
        mine = [x for x in oa if w in (x.get("welten") or [])]
        need(len(mine) >= 4 and any(x.get("gewoelbe") for x in mine), f"ortsarten: die Welt {w} braucht mindestens 4 Ortsarten, eine davon mit gewoelbe")
        t = x.get("teile")
        need(t is None or isinstance(t, list) and len(t) == 2 and all(isinstance(v, list) and 1 <= len(v) <= 20 and all(
            isinstance(s, str) and 2 <= len(s) <= 20 for s in v) for v in t), f"ortsarten {x.get('id')}: teile als [[deutsch …], [englisch …]], Endungen mit 2 bis 20 Zeichen")
    for x in r.get("silben") or []:
        v = x.get("vor")
        need(x.get("id") in welten and isinstance(v, list) and len(v) == 2 and all(isinstance(a, list) and 1 <= len(a) <= 40 and all(
            isinstance(s, str) and 2 <= len(s) <= 20 for s in a) for a in v), f"silben {x.get('id')}: id einer Welt und vor als [[deutsch …], [englisch …]]")
    for k in ("raeume", "fallen", "begegnungen"):
        for x in r.get(k) or []:
            need(not isinstance(x, dict) or x.get("welten") is None or isinstance(x["welten"], list) and set(x["welten"]) <= welten,
                 f"{k} {x.get('id') if isinstance(x, dict) else '?'}: welten aus den Welten oder weglassen (alle)")
            need(not isinstance(x, dict) or isinstance(x.get("gewicht", 1), int) and not isinstance(x.get("gewicht", 1), bool)
                 and 1 <= x.get("gewicht", 1) <= 10, f"{k} {x.get('id') if isinstance(x, dict) else '?'}: gewicht 1 bis 10")
    ra = [x for x in r.get("raeume") or [] if isinstance(x, dict)]
    for x in ra:
        need(x.get("art") in RAUM_ARTEN and _pair(x.get("satz"), SATZ_MAX), f"raeume {x.get('id')}: art eine von {', '.join(RAUM_ARTEN)} und satz [deutsch, englisch]")
    for w in welten:
        mine = {x.get("art") for x in ra if w in (x.get("welten") or welten)}
        need(mine >= {"eingang", "kammer", "schatz", "boss"}, f"raeume: die Welt {w} braucht mindestens je einen eingang, kammer, schatz und boss")
    for x in r.get("begegnungen") or []:
        need(x.get("art") in BEGEGNUNG_ARTEN and _pair(x.get("satz"), SATZ_MAX),
             f"begegnungen {x.get('id')}: art eine von {', '.join(BEGEGNUNG_ARTEN)} und satz [deutsch, englisch]")
    for x in r.get("fallen") or []:
        lo, hi = (x.get("schaden") + [0, 0])[:2] if isinstance(x.get("schaden"), list) else (0, 0)
        need(_pair(x.get("satz"), SATZ_MAX) and x.get("wert") in werte and isinstance(x.get("schwer"), int) and 5 <= x["schwer"] <= 20
             and isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi <= 6,
             f"fallen {x.get('id')}: satz, wert, schwer 5 bis 20 und schaden [von, bis] von 1 bis 6")
    for x in r.get("raetsel") or []:
        lo = x.get("loesung")
        need(_pair(x.get("frage"), FRAGE_MAX) and _pair(x.get("hinweis"), SATZ_MAX) and isinstance(lo, list) and len(lo) == 2
             and all(isinstance(v, list) and 1 <= len(v) <= 6 and all(isinstance(s, str) and 2 <= len(s) <= 30 for s in v) for v in lo),
             f"raetsel {x.get('id')}: frage, hinweis und loesung als [[deutsch …], [englisch …]], je 1 bis 6 Wörter")
    return err


def _li(rd):
    return 1 if rd.get("lang") == "en" else 0


def _kinds(r, welt):
    return [x for x in r["ortsarten"] if welt in x["welten"]]


def _of_world(r, k, welt):
    """The entries of a table for a world: those naming it, and those naming none (every world)."""
    return [x for x in r.get(k) or [] if welt in (x.get("welten") or [welt])]


def _weighted(rng, xs):
    return rng.choices(xs, weights=[x.get("gewicht", 1) for x in xs])[0]


# ---------------------------------------------------------------- the net of places
def _cross(a, b, c, d):
    """Whether the ways a-b and c-d cross (a shared end does not count)."""
    if len({a, b, c, d}) < 4:
        return False

    def o(p, q, s):
        return (q[0] - p[0]) * (s[1] - p[1]) - (q[1] - p[1]) * (s[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _hops(n, wege, von):
    nb = {i: [] for i in range(n)}
    for a, b in wege:
        nb[a].append(b)
        nb[b].append(a)
    dist, back, q = {von: 0}, {}, [von]
    for x in q:
        for y in sorted(nb[x]):
            if y not in dist:
                dist[y], back[y] = dist[x] + 1, x
                q.append(y)
    return dist, back, nb


def _path(back, von, nach):
    out = [nach]
    while out[-1] != von:
        out.append(back[out[-1]])
    return out[::-1]


def _land(form, rng):
    """The shape of the land: a function that draws one point and the decoration the view paints (river, lake,
    border, sea)."""
    w, h = FLAECHE
    if form == "tal":
        amp, f, ph = rng.randint(60, 150), rng.uniform(0.7, 1.6), rng.uniform(0, 2 * math.pi)

        def mid(x):
            return h / 2 + amp * math.sin(2 * math.pi * f * x / w + ph)
        def pt():                                # on either bank, never in the river
            x = rng.randint(RAND, w - RAND)
            return x, round(mid(x) + rng.choice((-1, 1)) * rng.randint(55, 170))
        return pt, {"fluss": [[x, round(mid(x))] for x in range(0, w + 1, 50)]}
    if form == "see":
        cx, cy, rx, ry = w / 2 + rng.randint(-60, 60), h / 2 + rng.randint(-30, 30), w * 0.37, h * 0.36

        def pt():
            a, k = rng.uniform(0, 2 * math.pi), rng.uniform(0.82, 1.18)
            return round(cx + rx * k * math.cos(a)), round(cy + ry * k * math.sin(a))
        return pt, {"see": [round(cx), round(cy), round(rx * 0.5), round(ry * 0.5)]}
    if form == "zwei_reiche":
        mx = w / 2 + rng.randint(-50, 50)
        deko = {"grenze": [[round(mx + rng.randint(-25, 25)), y] for y in range(0, h + 1, 60)]}
        return (lambda: (rng.randint(RAND, round(mx - 85)) if rng.random() < 0.5 else rng.randint(round(mx + 85), w - RAND),
                         rng.randint(RAND, h - RAND))), deko
    if form == "kueste":
        y0, y1 = rng.randint(round(h * 0.7), h - 40), rng.randint(round(h * 0.55), round(h * 0.8))
        ph = rng.uniform(0, 2 * math.pi)

        def coast(x):
            return y0 + (y1 - y0) * x / w + 28 * math.sin(ph + x / 70)

        def pt():
            x = rng.randint(RAND, w - RAND)
            return x, rng.randint(RAND, max(RAND + 1, round(coast(x) - 45)))
        return pt, {"kueste": [[x, round(coast(x))] for x in range(0, w + 1, 40)]}
    return (lambda: (rng.randint(RAND, w - RAND), rng.randint(RAND, h - RAND))), {}


def roll_net(n, rng, form="verstreut"):
    """n points on the plane in the shape of the land, with ways between them: (points, ways, decoration). Every
    place is reached, no two ways cross. Where the land is narrow the minimum distance shrinks a little."""
    pt, deko = _land(form, rng)
    w, h = FLAECHE
    pts, gap = [], ABSTAND
    while len(pts) < n and gap > ABSTAND * 0.55:
        for _ in range(3000):
            if len(pts) >= n:
                break
            p = pt()
            if RAND <= p[0] <= w - RAND and RAND <= p[1] <= h - RAND and all(math.dist(p, q) >= gap for q in pts):
                pts.append(p)
        gap *= 0.88
    n = len(pts)
    wege, inside = set(), {0}
    while len(inside) < n:                       # the spanning tree (Prim): the shortest way out of the reached part
        a, b = min(((i, j) for i in inside for j in range(n) if j not in inside), key=lambda e: math.dist(pts[e[0]], pts[e[1]]))
        wege.add((min(a, b), max(a, b)))
        inside.add(b)
    extra = 0
    for i, j in sorted(((i, j) for i in range(n) for j in range(i + 1, n) if (i, j) not in wege),
                       key=lambda e: math.dist(pts[e[0]], pts[e[1]])):
        if extra >= max(2, n // 4) or math.dist(pts[i], pts[j]) > QUER:
            continue
        if sum(i in e for e in wege) >= GRAD or sum(j in e for e in wege) >= GRAD:
            continue
        if any(_cross(pts[i], pts[j], pts[a], pts[b]) for a, b in wege):
            continue
        if rng.random() < 0.6:
            wege.add((i, j))
            extra += 1
    return pts, sorted(wege), deko


def _name(r, rd, k, used, rng):
    """A name for a place of kind k: from the kind's list, or a stem of the world joined with one of the kind's
    endings (Krähen + wald, Crow + Wood); never one the map has already."""
    li = _li(rd)
    vor = next((x["vor"][li] for x in r.get("silben") or [] if x["id"] == rd.get("welt")), [])
    for _ in range(30):
        if k.get("teile") and vor and rng.random() < 0.55:
            a, b = rng.choice(vor), rng.choice(k["teile"][li])
            name = f"{a} {b[:1].upper()}{b[1:]}" if li else f"{a}{b}"
        else:
            name = rng.choice(k["namen"][li])
        if name not in used:
            return name
    return next(f"{k['name'][li]} {i}" for i in range(2, 99) if f"{k['name'][li]} {i}" not in used)


def make(r, rd, rng=None, start="", form=""):
    """A new map into the round: the land's shape (rolled unless given), the net of places, the start (named start,
    e.g. where the last chapter ended), the goal and the act's places."""
    rng = rng or random.Random()
    plan = rd.get("plan") or {}
    akte = len(plan.get("akte") or []) or 3
    n = max(ORTE[0], min(ORTE[1], 6 + 2 * akte + rng.randint(0, 2)))
    form = form if form in FORMEN else rng.choice(FORMEN)
    pts, wege, deko = roll_net(n, rng, form)
    n = len(pts)
    first = min(range(n), key=lambda i: (pts[i][0], pts[i][1]))
    dist, back, _ = _hops(n, wege, first)
    ziel = max(range(n), key=lambda i: (dist[i], pts[i][0]))
    weg = _path(back, first, ziel)
    stellen = [weg[min(len(weg) - 1, round((k + 1) * (len(weg) - 1) / akte))] for k in range(akte)]
    kinds = _kinds(r, rd.get("welt")) or r["ortsarten"]
    gw = [x for x in kinds if x.get("gewoelbe")] or kinds
    st = [x for x in kinds if x.get("start")] or kinds
    arten = {first: rng.choice(st), ziel: rng.choice(gw)}
    count = {}
    for i in [first, ziel] + [i for i in range(n) if i not in (first, ziel)]:
        if i not in arten:                       # every kind about as often: one used already is rarer
            arten[i] = rng.choices(kinds, weights=[1 / (1 + 3 * count.get(x["id"], 0)) for x in kinds])[0]
        count[arten[i]["id"]] = count.get(arten[i]["id"], 0) + 1
    used, orte = set(), []
    story = [str(x)[:NAME_MAX] for x in plan.get("orte") or [] if str(x).strip()]
    named = {first: start[:NAME_MAX] if start else (story.pop(0) if story else "")}   # the story's first place is the start
    for i, s in zip([i for i in stellen if i != first], story):
        named[i] = s
    for i in range(n):
        k = arten[i]
        name = named.get(i) or _name(r, rd, k, used, rng)
        used.add(name)
        orte.append({"name": name, "art": k["id"], "x": pts[i][0], "y": pts[i][1]})
    rd["karte"] = {"form": form, "deko": deko, "orte": orte, "wege": [list(e) for e in wege], "hier": first, "besucht": [first],
                   "gegangen": [], "ziel": ziel, "akte": stellen, "schritte": 0, "gw": {}, "drin": None}
    print(f"dungeon: karte | neu | {form} | {n} orte | {len(wege)} wege", flush=True)
    return rd["karte"]


def _nb(k):
    out = {i: [] for i in range(len(k["orte"]))}
    for a, b in k["wege"]:
        out[a].append(b)
        out[b].append(a)
    return out


def _dir(a, b, li):
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360     # y grows downwards: 90 is south
    return RICHTUNG[round(ang / 45) % 8][li]


def _kind(r, k_id):
    return next((x for x in r["ortsarten"] if x["id"] == k_id), None)


def names(rd):
    """The places the group went through, in order (the campaign keeps them for the chapter)."""
    k = rd.get("karte")
    return [k["orte"][i]["name"] for i in k["besucht"]] if k else []


# ---------------------------------------------------------------- vaults
def _grow(form, n, gw, gh, rng):
    """Cells and corridors of a vault in one of the GEWOELBE forms, grown from the entrance at the west edge."""
    mid = rng.randrange(gh) if form not in ("gang", "kreuz") else gh // 2
    zellen, gaenge = [(0, mid)], set()

    def add(a, b):
        if b not in zellen and 0 <= b[0] < gw and 0 <= b[1] < gh and len(zellen) < n:
            gaenge.add((zellen.index(a), len(zellen)))
            zellen.append(b)
            return True
        return False

    def line(a, dx, dy, k):
        for _ in range(k):
            b = (a[0] + dx, a[1] + dy)
            if not add(a, b):
                return a
            a = b
        return a
    if form == "gang":                           # a long corridor east, rooms off it to the north and the south
        end = line(zellen[0], 1, 0, min(gw - 1, max(3, n // 2)))
        spine = list(zellen[:zellen.index(end) + 1])
        rng.shuffle(spine)
        for a in spine:
            add(a, (a[0], a[1] + rng.choice((-1, 1))))
    elif form == "kreuz":                        # a corridor to a hall in the middle, arms to every side from there
        hub = line(zellen[0], 1, 0, max(1, gw // 2 - 1))
        for dx, dy in rng.sample(((1, 0), (0, 1), (0, -1)), 3):
            line(hub, dx, dy, max(1, (n - len(zellen)) // 2))
    tries = 0
    while len(zellen) < n and tries < 2000:      # every form: grow on from a room until there are n
        tries += 1
        a = rng.choice(zellen[-3:] if form == "hoehle" and rng.random() < 0.7 else zellen)
        dirs = ((1, 0), (1, 0), (0, 1), (0, -1), (-1, 0)) if form == "verzweigt" else ((1, 0), (0, 1), (0, -1), (-1, 0))
        dx, dy = rng.choice(dirs)
        add(a, (a[0] + dx, a[1] + dy))
    loops = {"labyrinth": 3, "verzweigt": 1, "hoehle": 1}.get(form, 0)
    for i, a in sorted(enumerate(zellen), key=lambda _: rng.random()):
        if loops <= 0:
            break
        j = next((j for j, b in enumerate(zellen) if abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 and (min(i, j), max(i, j)) not in gaenge), None)
        if j is not None:
            gaenge.add((min(i, j), max(i, j)))
            loops -= 1
    return zellen, gaenge


def roll_vault(r, rd, name, rng, form=""):
    """A vault on the grid in one of the GEWOELBE forms: the master in the farthest room, a treasure next to it; a
    trap, a riddle, a guardian, a spring and an altar while there are rooms enough; the rest by weight from the
    room table of the world."""
    welt = rd.get("welt")
    form = form if form in GEWOELBE else rng.choice(GEWOELBE)
    gw, gh = rng.randint(*RASTER[0]), rng.randint(*RASTER[1])
    n = min(rng.randint(*RAUME), gw * gh * 2 // 3)
    zellen, gaenge = _grow(form, n, gw, gh, rng)
    n = len(zellen)
    dist, back, nb = _hops(n, gaenge, 0)
    boss = max(range(n), key=lambda i: (dist[i], i))
    arten = {0: "eingang", boss: "boss"}
    schatz = next((j for j in sorted(nb[boss], key=lambda j: -dist[j]) if j not in arten), None)
    if schatz is not None:
        arten[schatz] = "schatz"
    tab = _of_world(r, "raeume", welt) or r["raeume"]
    have = {x["art"] for x in tab}
    rest = [i for i in range(n) if i not in arten]
    rng.shuffle(rest)
    want = [a for a in ["falle", "raetsel", "waechter"] + rng.sample(["quelle", "altar", "falle", "waechter", "schatz"], 3)
            if a in have and (a != "falle" or _of_world(r, "fallen", welt)) and (a != "raetsel" or r.get("raetsel"))]
    rng.shuffle(want)
    for i, a in zip(rest, want[:(len(rest) + 1) // 2]):     # about half the rooms are special, the others plain
        arten[i] = a
    filler = [x for x in tab if x["art"] in ("gang", "kammer")]
    fallen = _of_world(r, "fallen", welt) or r["fallen"]
    raeume, used, qused = [], set(), set()
    for i, (x, y) in enumerate(zellen):
        a = arten.get(i)
        pool = [t for t in tab if t["art"] == a] if a else filler
        e = _weighted(rng, [t for t in pool if t["id"] not in used] or pool)
        used.add(e["id"])
        room = {"x": x, "y": y, "art": e["art"], "t": e["id"], "fertig": e["art"] in ("eingang", "gang", "kammer")}
        if e["art"] == "falle":
            room["falle"] = _weighted(rng, fallen)["id"]
        if e["art"] == "raetsel":
            room["raetsel"], room["versuche"] = rng.choice([q for q in r["raetsel"] if q["id"] not in qused] or r["raetsel"])["id"], 0
            qused.add(room["raetsel"])
        raeume.append(room)
    print(f"dungeon: gewoelbe | neu | {form} | {n} raeume", flush=True)
    return {"name": name, "form": form, "raeume": raeume, "gaenge": [list(e) for e in sorted(gaenge)], "hier": 0, "besucht": [0], "gegangen": []}


def _vnb(v):
    out = {i: [] for i in range(len(v["raeume"]))}
    for a, b in v["gaenge"]:
        out[a].append(b)
        out[b].append(a)
    return out


def _shut(v, i):
    """Whether the ways on from room i are shut: an unsolved riddle, an unbeaten guardian; only the way back is open."""
    return not v["raeume"][i]["fertig"] and v["raeume"][i]["art"] in ("raetsel", "waechter", "boss")


def _ways_in(v):
    """The rooms the group may go to from where it stands (and whether it may leave the vault)."""
    i = v["hier"]
    nb = sorted(_vnb(v)[i])
    if _shut(v, i):
        nb = [j for j in nb if j in v["besucht"]]
    return nb


def _table(r, k, tid):
    return next((x for x in r[k] if x["id"] == tid), None)


def _words(s):
    s = str(s or "").lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return re.findall(r"[a-z]+", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode())


def _norm(s):
    return set(_words(s))


def solved(r, rd):
    """Whether one of this turn's actions holds an answer of the riddle where the group stands (pure)."""
    v = vault(rd)
    if not v:
        return False
    room = v["raeume"][v["hier"]]
    q = _table(r, "raetsel", room.get("raetsel")) if room["art"] == "raetsel" and not room["fertig"] else None
    if not q:
        return False
    want = {w for ws in q["loesung"] for w in _norm(" ".join(ws))}
    return any(want & _norm(a.get("text")) for a in (rd.get("offen") or {}).values())


def _names(name, words):
    """Whether every longer word of a place's name stands in words (also bent: „alten“ for „Alte“)."""
    need = [w for w in _words(name) if len(w) >= 4]
    return bool(need) and all(any(x.startswith(w) for x in words) for w in need)


def named_way(rd, text):
    """The way the turn named when the model left szene.ort_id empty (Dominik 2026-10-24 „in die alte Bibliothek
    bewegt, die Position ist nicht aktuell“): exactly one neighbouring place is named in the narration and asked for
    in an action of this turn (by its name or its direction). The panel's fixed rule, never the model alone; -1 for
    none (pure)."""
    k = rd.get("karte")
    if not k or vault(rd):
        return -1
    told, li, o, here = _words(text), _li(rd), k["orte"], k["hier"]
    said = [_words(a.get("text")) for a in (rd.get("offen") or {}).values() if isinstance(a, dict)]

    def asked(j):       # its name, or its direction („nach Nordosten“), in an action
        d = " " + " ".join(_words(_dir((o[here]["x"], o[here]["y"]), (o[j]["x"], o[j]["y"]), li))) + " "
        return any(_names(o[j]["name"], w) or d in " " + " ".join(w) + " " for w in said)
    hits = [j for j in sorted(_nb(k)[here]) if _names(o[j]["name"], told) and asked(j)]
    return hits[0] if len(hits) == 1 else -1


def vault(rd):
    k = rd.get("karte")
    return k["gw"].get(str(k["drin"])) if k and k.get("drin") is not None else None


# ---------------------------------------------------------------- what the model gets
def facts(r, rd):
    """The map as the model may know it: where the group stands, the ways from there, the direction of the next act's
    place; in a vault the room, its trap, riddle (question, never the answer) or foe. {} without a map."""
    k = rd.get("karte")
    if not k:
        return {}
    li = _li(rd)
    o = k["orte"]
    v = vault(rd)
    if v:
        room = v["raeume"][v["hier"]]
        t = _table(r, "raeume", room["t"]) or {"name": [room["art"]] * 2, "satz": [""] * 2}
        nb = _vnb(v)
        wege = [{"id": f"r{j + 1}", "richtung": _dir((v["raeume"][v["hier"]]["x"], v["raeume"][v["hier"]]["y"]),
                                                      (v["raeume"][j]["x"], v["raeume"][j]["y"]), li),
                 "raum": (_table(r, "raeume", v["raeume"][j]["t"]) or t)["name"][li] if j in v["besucht"] else ("unbekannt", "unknown")[li]}
                for j in _ways_in(v)]
        if v["hier"] == 0:
            wege.append({"id": "aus", "richtung": ("hinaus", "outside")[li], "raum": o[k["drin"]]["name"]})
        out = {"gewoelbe": v["name"], "raum": {"id": f"r{v['hier'] + 1}", "name": t["name"][li], "satz": t["satz"][li]},
               "wege": wege, "noch_zu": len(nb[v["hier"]]) - len(_ways_in(v)) if _shut(v, v["hier"]) else 0}
        if room["art"] == "falle":
            f = _table(r, "fallen", room.get("falle"))
            if f:
                out["falle"] = {"name": f["name"][li], "satz": f["satz"][li], "getroffen": room.get("getroffen", []), "bemerkt": room.get("bemerkt", [])}
        if room["art"] == "raetsel":
            q = _table(r, "raetsel", room.get("raetsel"))
            if q:
                out["raetsel"] = {"frage": q["frage"][li], "stand": "geloest" if room["fertig"] or solved(r, rd) else "offen"}
                if not room["fertig"] and room.get("versuche", 0) >= VERSUCHE:
                    out["raetsel"]["hinweis"] = q["hinweis"][li]
        if room["art"] in ("waechter", "boss") and not room["fertig"]:
            out["gegner"] = ("die Gegner dieses Raums stehen im Angebot", "the foes of this room are in the offer")[li]
        if room["art"] == "schatz":
            out["truhe"] = "offen" if room["fertig"] else "zu"
        if room["art"] in ("quelle", "altar"):
            out[room["art"]] = ("vom Panel gewirkt", "worked by the panel")[li]
        return dict(out, **_on_way(r, rd))
    here = k["hier"]
    p = (o[here]["x"], o[here]["y"])
    kd = _kind(r, o[here]["art"])
    out = {"ort": {"id": f"o{here + 1}", "name": o[here]["name"], "art": kd["name"][li] if kd else o[here]["art"]},
           "wege": [{"id": f"o{j + 1}", "name": o[j]["name"], "richtung": _dir(p, (o[j]["x"], o[j]["y"]), li),
                     "besucht": j in k["besucht"]} for j in sorted(_nb(k)[here])]}
    akt = min(rd.get("akt", 0), len(k["akte"]) - 1)
    goal = k["akte"][akt] if k["akte"] else k["ziel"]
    if goal == here:
        out["aktziel"] = ("hier", "here")[li]
    else:
        _, back, _ = _hops(len(o), k["wege"], here)
        nxt = _path(back, here, goal)[1]
        out["aktziel"] = _dir(p, (o[nxt]["x"], o[nxt]["y"]), li)
    if has_vault(r, k, here):
        out["wege"].append({"id": "ein", "name": ("ins Gewölbe", "into the vault")[li], "richtung": ("hinein", "inside")[li],
                            "besucht": str(here) in k["gw"]})
    return dict(out, **_on_way(r, rd))


def _on_way(r, rd):
    """The encounter of the last way, for the narration right after it."""
    u = rd["karte"].get("unterwegs")
    b = _table(r, "begegnungen", (u or {}).get("t"))
    if not b or u["zug"] != rd.get("zug"):
        return {}
    return {"unterwegs": {"art": b["art"], "satz": b["satz"][_li(rd)]}}


def task(rd):
    """The sentence for the system text of a narration (only with a map)."""
    return (" " + AUFGABE["en" if rd.get("lang") == "en" else "de"]) if rd.get("karte") else ""


def ort_id(obj):
    """The id the model named in szene.ort_id, or "" (the shape only; step checks it against the ways)."""
    s = obj.get("szene") if isinstance(obj, dict) else None
    x = str(s.get("ort_id") or "").strip().lower() if isinstance(s, dict) else ""
    return x if _ID.fullmatch(x) else ""


SCHEMA = {"type": "string", "maxLength": 8}   # szene.ort_id in dungeon.SCHEMA_ERZAEHLEN


# ---------------------------------------------------------------- the group moves (the panel decides)
def _say(rd, de, en):
    import dungeon
    dungeon._log(rd, "system", text=[de, en])


def _trap(r, rd, room, rng):
    """The panel rolls for every hero entering a trap room: a save, d20 + value against the difficulty; failed the
    whole damage, made half of it (as in D&D: armour does not help against a trap)."""
    import dungeon
    f = _table(r, "fallen", room.get("falle"))
    if not f:
        room["fertig"] = True
        return
    held = dungeon.seated(rd)
    stufe = dungeon.group_level([p["held"] for _, p in held])
    schwer = max(dungeon.SCHWER[0], min(dungeon.SCHWER[1], f["schwer"] + (stufe - 1) // 2))
    room["getroffen"], room["bemerkt"] = [], []
    _say(rd, f"Falle: {f['name'][0]}!", f"Trap: {f['name'][1]}!")
    for pid, p in held:
        h = p["held"]
        w, bonus = rng.randint(1, 20), dungeon.total(r, h, f["wert"])
        ok = w == 20 or (w != 1 and w + bonus >= schwer)
        dungeon._log(rd, "wurf", pid=pid, name=h["name"], wert=f["wert"], w=w, bonus=bonus, gesamt=w + bonus, schwer=schwer, ok=ok, vt="", ws=[w])
        n = rng.randint(*f["schaden"]) // (2 if ok else 1)
        if not n:
            room["bemerkt"].append(h["name"])
            continue
        h["leben"] = max(0, h["leben"] - n)
        room["getroffen"].append(h["name"])
        dungeon._log(rd, "folge", pid=pid, name=h["name"], was="schaden", zahl=n, leben=h["leben"])
    room["fertig"] = True
    print(f"dungeon: falle | {len(room['getroffen'])} getroffen | {len(room['bemerkt'])} bemerkt", flush=True)


def _treasure(r, rd, room, rng):
    import dungeon
    held = [p["held"] for _, p in dungeon.seated(rd)]
    if held:
        dungeon.give_loot(r, rd, held, "truhe", dungeon.group_level(held), rng)
    room["fertig"] = True


def _spring(r, rd, room, rng):
    """A spring heals every hero by QUELLE (the panel rolls once for the group)."""
    import dungeon
    n = rng.randint(*QUELLE)
    for pid, p in dungeon.seated(rd):
        h = p["held"]
        h["leben"] = min(h["leben_max"], h["leben"] + n)
        dungeon._log(rd, "folge", pid=pid, name=h["name"], was="heilung", zahl=n, leben=h["leben"])
    room["fertig"] = True
    print(f"dungeon: quelle | {n} leben", flush=True)


def _altar(r, rd, room, rng):
    """An altar blesses one value of every hero for some turns (ALTAR: bonus, turns)."""
    import dungeon
    wert = rng.choice([w["id"] for w in r["werte"]])
    t = _table(r, "raeume", room["t"]) or {"name": ["Altar", "Altar"]}
    for _, p in dungeon.seated(rd):
        dungeon.bless(p["held"], {"wert": wert, "bonus": ALTAR[0], "zuege": ALTAR[1]}, t["name"][_li(rd)])
    w = next(x for x in r["werte"] if x["id"] == wert)
    _say(rd, f"{t['name'][0]}: +{ALTAR[0]} auf {w['name'][0]} für {ALTAR[1]} Züge.", f"{t['name'][1]}: +{ALTAR[0]} to {w['name'][1]} for {ALTAR[1]} turns.")
    room["fertig"] = True
    print(f"dungeon: altar | {wert}", flush=True)


ON_ENTER = {"falle": _trap, "schatz": _treasure, "quelle": _spring, "altar": _altar}


def _enter_room(r, rd, v, j, rng):
    a = v["hier"]
    v["hier"] = j
    e = [min(a, j), max(a, j)]
    if e not in v["gegangen"]:
        v["gegangen"].append(e)
    rd.pop("raum_gegner", None)                  # the foes of the room left behind are no more on offer
    room = v["raeume"][j]
    if j not in v["besucht"]:
        v["besucht"].append(j)
        if room["art"] in ON_ENTER and not room["fertig"]:
            ON_ENTER[room["art"]](r, rd, room, rng)
    if room["art"] in ("waechter", "boss") and not room["fertig"]:
        room.setdefault("gegner", _room_foes(r, rd, room["art"] == "boss", rng))
        if room["gegner"]:
            rd["raum_gegner"] = {"raum": _room_id(rd, j), "ids": room["gegner"]}


def won(rd):
    """The fight's victory (rd["sieg"], dungeon_kampf.end) opens the guardian's or the master's room the group stands
    in; dungeon.apply calls it right after the fight, step before its move. Any other tag is dropped."""
    sieg, v = rd.pop("sieg", None), vault(rd)
    if not sieg or not v:
        return
    room = v["raeume"][v["hier"]]
    if room["art"] not in ("waechter", "boss") or room["fertig"] or sieg != _room_id(rd, v["hier"]):
        print("dungeon: gewoelbe | sieg verworfen", flush=True)
        return
    room["fertig"] = True
    rd.pop("raum_gegner", None)
    print(f"dungeon: gewoelbe | sieg | {room['art']}", flush=True)
    if room["art"] == "boss":
        _say(rd, f"Das Gewölbe {v['name']} ist bezwungen.", f"The vault {v['name']} is conquered.")
        print("dungeon: gewoelbe | bezwungen", flush=True)


def _room_id(rd, j):
    """The id of a vault's room for the fight (dungeon_kampf: rd["raum_gegner"], rd["sieg"])."""
    return f"gw{rd['karte']['drin']}-r{j + 1}"


def _room_foes(r, rd, boss, rng):
    """The foes of a guardian's or the master's room from the Bestiarium of the world, by the group's level L: a
    guardian is one foe (two from 3 heroes on) of the challenge nearest L/2, the master one of the challenge nearest
    L+1 with up to two of the nearest L/4 at his side (from 2 heroes on); never more than 5."""
    import dungeon
    held = dungeon.seated(rd)
    lv = dungeon.group_level([p["held"] for _, p in held])
    tab = [x for x in r.get("gegner") or [] if "alle" in x.get("welten", ["alle"]) or rd.get("welt") in x.get("welten", [])]

    def near(t, n, but=()):
        c = [x for x in tab if x["id"] not in but]
        if not c:
            return []
        d = min(abs(x["stufe"] - t) for x in c)
        c = [x["id"] for x in c if abs(x["stufe"] - t) == d]
        rng.shuffle(c)
        return c[:n]
    if not boss:
        return near(max(0.125, lv / 2), 2 if len(held) >= 3 else 1)
    herr = near(lv + 1, 1)
    return (herr + near(max(0.125, lv / 4), 2 if len(held) >= 2 else 0, herr))[:5]


def on_the_way(r, rd, rng):
    """A way gone for the first time: UNTERWEGS percent an encounter from the world's table, its effect by the panel
    (a find from the catalog, a merchant; a foe comes through the fight's offer); the next narration hears of it."""
    import dungeon
    k = rd["karte"]
    tab = _of_world(r, "begegnungen", rd.get("welt"))
    if not tab or rng.randint(1, 100) > UNTERWEGS:
        return
    b = _weighted(rng, tab)
    k["unterwegs"] = {"t": b["id"], "zug": rd.get("zug", 0) + 1}
    _say(rd, "Unterwegs: " + b["satz"][0], "On the way: " + b["satz"][1])
    held = [p["held"] for _, p in dungeon.seated(rd)]
    if b["art"] == "fund" and held:
        dungeon.give_loot(r, rd, held, "belohnung", dungeon.group_level(held), rng)
    print(f"dungeon: unterwegs | {b['art']}", flush=True)


def has_vault(r, k, i):
    """A place leads into a vault: by its kind, or the host rolled one there."""
    return bool((_kind(r, k["orte"][i]["art"]) or {}).get("gewoelbe") or str(i) in k["gw"])


def roll_entrance(r, rd, rng):
    """The host's „Gewölbe würfeln“: a vault below the place the group stands at; the group goes in only when its
    action says so (ort_id "ein", Dominik 2026-10-24 „warum landet man direkt im gewölbe“)."""
    k = rd["karte"]
    key = str(k["hier"])
    if key not in k["gw"]:
        k["gw"][key] = roll_vault(r, rd, k["orte"][k["hier"]]["name"], rng)
        _say(rd, f"Ein Eingang tut sich auf: {k['gw'][key]['name']}.", f"An entrance opens: {k['gw'][key]['name']}.")
    return k["gw"][key]


def enter_vault(r, rd, rng):
    """The group goes into the vault of the place it stands at (rolled the first time)."""
    k = rd["karte"]
    key = str(k["hier"])
    if key not in k["gw"]:
        k["gw"][key] = roll_vault(r, rd, k["orte"][k["hier"]]["name"], rng)
    k["drin"] = k["hier"]
    v = k["gw"][key]
    v["hier"] = 0
    _say(rd, f"Ihr betretet das Gewölbe: {v['name']}.", f"You enter the vault: {v['name']}.")
    return v


def place_name(r, rd):
    """The scene's place: the map's name, in a vault with the room's."""
    k, v = rd["karte"], vault(rd)
    ort = k["orte"][k["hier"]]["name"]
    t = _table(r, "raeume", v["raeume"][v["hier"]]["t"]) if v else None
    return (f"{ort} · {t['name'][_li(rd)]}" if t else ort)[:60]


def ensure(r, rd, rng=None):
    """A round from before the map gets one, starting where its scene stands."""
    if not rd.get("karte"):
        make(r, rd, rng, start=(rd.get("szene") or {}).get("ort", ""))
    return rd["karte"]


def step(r, rd, story, ep, rng=None):
    """The checked narration's move on the map (dungeon.apply, dungeon.prolog): riddles, beaten foes, the ep for a
    solved riddle (into ep), traps, treasures and encounters are the panel's; when the place changed, the merchant
    and what lies on the ground stay behind. The scene's place is always the map's name. Returns whether the place
    changed."""
    import dungeon
    rng = rng or random
    k = ensure(r, rd, rng)
    k.pop("unterwegs", None)                     # told in the narration after it, then it is behind the group
    want = story.get("ort_id") or ""
    if not want and named_way(rd, story.get("text")) >= 0:
        want = f"o{named_way(rd, story.get('text')) + 1}"
        print("dungeon: karte | name statt id", flush=True)
    before = (k["hier"], k.get("drin"), (vault(rd) or {}).get("hier"))
    won(rd)
    v = vault(rd)
    if v:
        room = v["raeume"][v["hier"]]
        if room["art"] == "raetsel" and not room["fertig"] and rd.get("offen"):
            if solved(r, rd):
                room["fertig"] = True
                for pid in ep:
                    ep[pid] += r["ep"]["ziel"] // 2
                _say(rd, "Rätsel gelöst! Der Weg ist frei.", "Riddle solved! The way is open.")
                print("dungeon: raetsel | geloest", flush=True)
            else:
                room["versuche"] = room.get("versuche", 0) + 1
                print(f"dungeon: raetsel | offen | {room['versuche']} versuche", flush=True)
        if want == "aus" and v["hier"] == 0:
            k["drin"] = None
            rd.pop("raum_gegner", None)
            _say(rd, f"Ihr verlasst das Gewölbe {v['name']}.", f"You leave the vault {v['name']}.")
        elif want.startswith("r") and int(want[1:]) - 1 in _ways_in(v):
            _enter_room(r, rd, v, int(want[1:]) - 1, rng)
        elif want:
            print("dungeon: karte | verworfen | weg", flush=True)
    elif want.startswith("o") and int(want[1:]) - 1 in _nb(k)[k["hier"]]:
        a, j = k["hier"], int(want[1:]) - 1
        k["hier"], k["schritte"] = j, k["schritte"] + 1
        e = [min(a, j), max(a, j)]
        if e not in k["gegangen"]:
            k["gegangen"].append(e)
            on_the_way(r, rd, rng)
        if j not in k["besucht"]:
            k["besucht"].append(j)
    elif want == "ein" and has_vault(r, k, k["hier"]):
        enter_vault(r, rd, rng)
    elif want:
        print("dungeon: karte | verworfen | weg", flush=True)
    story["szene"] = {"ort": place_name(r, rd), "stimmung": (story.get("szene") or rd.get("szene") or {}).get("stimmung", "")}
    changed = (k["hier"], k.get("drin"), (vault(rd) or {}).get("hier")) != before
    if changed:
        dungeon.close_market(rd)
        rd["boden"] = []
        b = _table(r, "begegnungen", (k.get("unterwegs") or {}).get("t"))
        if b and b["art"] == "haendler" and k["unterwegs"]["zug"] == rd.get("zug", 0) + 1:
            dungeon.open_market(r, rd, rng=rng)
    return changed


# ---------------------------------------------------------------- what the players see
def view(r, rd, host=False):
    """The map for a seat: visited and known places only, ways into the unknown as stubs; the vault where the group
    is; the ways one may take from here (the players tap one into their action)."""
    k = rd.get("karte")
    if not k:
        return None
    li = _li(rd)
    o, nb = k["orte"], _nb(k)
    known = set(k["besucht"]) | {j for i in k["besucht"] for j in nb[i]}
    gegangen = {tuple(e) for e in k["gegangen"]}

    def place(i):
        kd = _kind(r, o[i]["art"]) or {}
        return {"id": f"o{i + 1}", "n": o[i]["name"], "z": kd.get("zeichen", "◆"), "x": o[i]["x"], "y": o[i]["y"],
                "s": 2 if i in k["besucht"] else 1, "gw": has_vault(r, k, i), "a": o[i]["art"]}
    wege = []
    for a, b in k["wege"]:
        if a in known and b in known:
            wege.append([o[a]["x"], o[a]["y"], o[b]["x"], o[b]["y"], 2 if (a, b) in gegangen else 1])
        elif a in known or b in known:
            s, u = (a, b) if a in known else (b, a)
            wege.append([o[s]["x"], o[s]["y"], round(o[s]["x"] + (o[u]["x"] - o[s]["x"]) * STUB),
                         round(o[s]["y"] + (o[u]["y"] - o[s]["y"]) * STUB), 0])
    xs = [o[i]["x"] for i in known] + [w[2] for w in wege]
    ys = [o[i]["y"] for i in known] + [w[3] for w in wege]
    out = {"box": _box(xs, ys), "w": FLAECHE[0], "h": FLAECHE[1], "form": k.get("form", "verstreut"), "deko": k.get("deko") or {}, "orte": [place(i) for i in sorted(known)], "wege": wege, "hier": f"o{k['hier'] + 1}",
           "welt": rd.get("welt"), "gesehen": len(k["besucht"]), "neu": host and k["schritte"] == 0 and k.get("drin") is None and not k["gw"]}
    v = vault(rd)
    here = (o[k["hier"]]["x"], o[k["hier"]]["y"])
    if v:
        vnb = _vnb(v)
        seen = set(v["besucht"]) | {j for i in v["besucht"] for j in vnb[i]}
        x0, y0 = min(v["raeume"][i]["x"] for i in seen), min(v["raeume"][i]["y"] for i in seen)
        rooms = []
        for i in sorted(seen):
            rm = v["raeume"][i]
            t = _table(r, "raeume", rm["t"]) or {}
            b = i in v["besucht"]
            rooms.append({"id": f"r{i + 1}", "x": rm["x"] - x0, "y": rm["y"] - y0, "s": 2 if b else 1, "a": rm["art"],
                          "z": t.get("zeichen", "") if b else "", "n": (t.get("name") or ["", ""])[li] if b else "", "f": rm["fertig"]})
        boss = next(rm for rm in v["raeume"] if rm["art"] == "boss")
        out["gewoelbe"] = {"name": v["name"], "raeume": rooms, "hier": f"r{v['hier'] + 1}", "zahl": len(v["raeume"]),
                           "gaenge": [[f"r{a + 1}", f"r{b + 1}", 2 if [a, b] in v["gegangen"] else 1] for a, b in v["gaenge"]
                                      if a in seen and b in seen and (a in v["besucht"] or b in v["besucht"])],
                           "geschafft": boss["fertig"]}
        cur = v["raeume"][v["hier"]]
        out["von_hier"] = [{"id": f"r{j + 1}", "n": (_table(r, "raeume", v["raeume"][j]["t"]) or {"name": ["", ""]})["name"][li]
                            if j in v["besucht"] else ("unbekannter Raum", "unknown room")[li],
                            "r": _dir((cur["x"], cur["y"]), (v["raeume"][j]["x"], v["raeume"][j]["y"]), li), "b": j in v["besucht"]}
                           for j in _ways_in(v)]
        if v["hier"] == 0:
            out["von_hier"].append({"id": "aus", "n": ("hinaus", "outside")[li], "r": "", "b": True})
        if _shut(v, v["hier"]):
            out["zu"] = {"raetsel": ("Die Tür bleibt zu, bis das Rätsel gelöst ist.", "The door stays shut until the riddle is solved."),
                         "waechter": ("Der Wächter versperrt den Weg.", "The guardian blocks the way."),
                         "boss": ("Der Herr des Gewölbes versperrt den Weg.", "The master of the vault blocks the way.")}[cur["art"]][li]
        if cur["art"] == "raetsel":
            q = _table(r, "raetsel", cur.get("raetsel"))
            if q:
                out["raetsel"] = {"frage": q["frage"][li], "fertig": cur["fertig"], "versuche": cur.get("versuche", 0), "max": VERSUCHE,
                                  "hinweis": q["hinweis"][li] if not cur["fertig"] and cur.get("versuche", 0) >= VERSUCHE else ""}
    else:
        out["von_hier"] = [{"id": f"o{j + 1}", "n": o[j]["name"], "r": _dir(here, (o[j]["x"], o[j]["y"]), li), "b": j in k["besucht"]}
                           for j in sorted(nb[k["hier"]])]
        if has_vault(r, k, k["hier"]):
            out["von_hier"].append({"id": "ein", "n": ("ins Gewölbe", "into the vault")[li], "r": "", "b": str(k["hier"]) in k["gw"]})
        out["gw_knopf"] = host and not has_vault(r, k, k["hier"])
    return _pictures(r, rd, out)


def _box(xs, ys):
    """The part of the plane the seat sees: what it knows with a margin for the names, at least BLICK wide and
    not flatter than the plane; so the map grows as the fog lifts."""
    x0, x1, y0, y1 = min(xs) - 130, max(xs) + 130, min(ys) - 90, max(ys) + 90
    w, h = max(x1 - x0, BLICK), max(y1 - y0, BLICK * 0.5)
    w = max(w, h * 1.2)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [round(cx - w / 2), round(cy - h / 2), round(w), round(h)]


# ---------------------------------------------------------------- pictures instead of signs (dungeon_dingbild)
_malt = set()             # ort- pictures being painted right now


def _worlds(r, style):
    """The worlds painted in this style (the picture book: every world)."""
    import dungeon
    ws = {w["id"] for w in r["welten"]}
    return ws if style == dungeon.BILD_KIND else {w for w in ws if dungeon.style(r, {"welt": w, "ton": None}) == style}


def kind_prompt(style, e, room=False):
    """The fixed prompt of a kind of place or room: the English name (a room's sentence too), never the model's."""
    import dungeon
    extra = f", {e['satz'][1]}" if room and e.get("satz") else ""
    return f"{style}, {RAUM_EN if room else ORT_EN}: {e['name'][1]}{extra}, {dungeon.BILD_ENDE}"


def bilder(r, style):
    """[(name, prompt)] of the map's catalog pictures in one style (dungeon_dingbild.wanted adds them after the items)."""
    import dungeon_dingbild as db
    ws = _worlds(r, style)
    out = []
    for k, room in (("ortsarten", False), ("raeume", True)):
        for e in r.get(k) or []:
            if not e.get("welten") or set(e["welten"]) & ws:
                p = kind_prompt(style, e, room)
                out.append((db.name_of(p), p))
    return out


def _ort_text(r, k, i):
    o = k["orte"][i]
    kd = _kind(r, o["art"]) or {"name": ["", "a place"]}
    return f"{ORT_EN}: {kd['name'][1]}, a place named {o['name']}"


def queue_orte():
    """Inside dungeon._lock: every visited place of a running round without its own picture, of a host with „Bilder
    malen“, within the game's day limit. Returns [(rid, i, name, prompt)] to paint (dungeon_dingbild.due)."""
    import dungeon
    import dungeon_dingbild as db
    import schwer
    r = dungeon.rules()
    out, today = [], db._date()
    with dungeon._lock:
        d = dungeon._read()
        changed = False
        for rid, rd in d["runden"].items():
            k = rd.get("karte")
            if not k or rd.get("status") != "laeuft" or not dungeon.pictures_on(rd["owner"]):
                continue
            bl = k.setdefault("bild", {})
            for i in k["besucht"]:
                f = bl.get(str(i)) or {}
                if f.get("st") in ("ok", "weg") or f.get("n") in _malt or f.get("st") in ("tag", "fehler", "malt") and f.get("day") == today:
                    continue
                text, why = dungeon.picture_text(r, rd, _ort_text(r, k, i))
                if not why and dungeon._bild_tag_voll(r, d, rd):
                    why = "tag"
                if not why and schwer.full():
                    continue
                changed = True
                if why:
                    bl[str(i)] = {"st": "tag" if why == "tag" else "weg", "day": today}
                    print(f"dungeon: karte | ortsbild abgelehnt | {why}", flush=True)
                    continue
                prompt = f"{dungeon.style(r, rd)}, {text}, {dungeon.BILD_ENDE}"
                n = "ort-" + hashlib.sha256(f"{rid}|{prompt}".encode()).hexdigest()[:16]
                dungeon._bild_take(d)
                bl[str(i)] = {"n": n, "st": "malt", "day": today}
                _malt.add(n)
                out.append((rid, i, n, prompt))
        if changed:
            dungeon._write(d)
    return out


async def paint_ort(rid, i, n, p):
    """One place's own picture through the game's painter; the round notes how it went."""
    import dungeon
    import dungeon_dingbild as db
    t0 = time.perf_counter()
    try:
        res = await db.paint_one(n, p)
    finally:
        _malt.discard(n)

    def note():
        with dungeon._lock:
            d = dungeon._read()
            k = (d["runden"].get(rid) or {}).get("karte")
            if k:
                k.setdefault("bild", {})[str(i)] = {"n": n, "st": "ok" if res == "ok" else "weg" if res in ("pruefung", "ohne_pruefung") else "fehler",
                                                    "day": db._date()}
                dungeon._write(d)
    await asyncio.to_thread(note)
    print(f"dungeon: karte | ortsbild | {res} | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)


def keep(d):
    """The ort- pictures some round's map still names (dungeon_dingbild.sweep keeps them)."""
    return {f.get("n") for v in d["runden"].values() for f in ((v.get("karte") or {}).get("bild") or {}).values() if f.get("n")}


def may_see(name, uid=None, rid=None):
    """An ort- picture only for the round whose map names it: a guest's seat of that round (rid), or a profile that
    hosts or sits in it (uid). Any other name pattern is not this module's (True: dungeon_dingbild decides)."""
    import dungeon
    if not str(name).startswith("ort-"):
        return True
    for r_id, v in dungeon._read()["runden"].items():
        if rid is not None and r_id != rid:
            continue
        if uid is not None and v.get("owner") != uid and not any(p.get("uid") == uid for p in v["plaetze"].values()):
            continue
        if any(f.get("n") == name for f in ((v.get("karte") or {}).get("bild") or {}).values()):
            return True
    return False


def _pictures(r, rd, out):
    """view's last step: "b" on every place and room, the name of its picture ("" while there is none): a place's
    own once painted, else its kind's in the round's style."""
    import dungeon
    import dungeon_dingbild as db
    have = db.files() if db.on() else frozenset()
    k = rd["karte"]
    style = dungeon.style(r, rd)
    bl = k.get("bild") or {}
    for p in out["orte"]:
        i = int(p["id"][1:]) - 1
        own = (bl.get(str(i)) or {}).get("n", "")
        kd = _kind(r, k["orte"][i]["art"])
        kind = db.name_of(kind_prompt(style, kd)) if kd else ""
        p["b"] = own if own in have else kind if kind in have else ""
    v = vault(rd)
    if out.get("gewoelbe") and v:
        for p in out["gewoelbe"]["raeume"]:
            t = _table(r, "raeume", v["raeume"][int(p["id"][1:]) - 1]["t"]) if p["s"] == 2 else None
            n = db.name_of(kind_prompt(style, t, True)) if t else ""
            p["b"] = n if n in have else ""
    return out


def for_live(rounds):
    """Only counts: rounds with a map, rounds inside a vault, own pictures of places."""
    ks = [v.get("karte") for v in rounds if v.get("karte")]
    return {"karten": len(ks), "gewoelbe_drin": sum(1 for k in ks if k.get("drin") is not None),
            "ortsbilder": sum(1 for k in ks for f in (k.get("bild") or {}).values() if f.get("st") == "ok")}


# ---------------------------------------------------------------- the host's buttons
@router.post("/api/profile/dungeon/{rid}/karte", dependencies=[Depends(assistant)])
async def karte(rid: str, request: Request, prof=Depends(browser_profile)):
    """{was: neu} rolls the map again while the group has not moved; {was: gewoelbe} rolls a vault below the place
    the group stands at (a place with a vault already: refused); the group goes in by its action."""
    import dungeon
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dungeon.BODY)
    was = b.get("was")

    def go():
        r = dungeon.rules()
        with dungeon._lock:
            d = dungeon._read()
            rd = dungeon._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende" or rd.get("dm"):
                raise LookupError("gastgeber")
            k = rd.get("karte")
            if was == "neu" and (not k or k["schritte"] == 0 and k.get("drin") is None and not k["gw"]):
                make(r, rd, start=k["orte"][k["hier"]]["name"] if k and rd.get("kid") else "")
                dungeon.close_market(rd)
            elif was == "gewoelbe" and k and k.get("drin") is None and not has_vault(r, k, k["hier"]):
                roll_entrance(r, rd, random.Random())
            else:
                raise ValueError("eingabe")
            rd["szene"] = dict(rd["szene"], ort=place_name(r, rd))
            dungeon._write(d)
        print(f"dungeon: karte | {was}", flush=True)
        return dungeon.view(rid, dungeon._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dungeon.KNOWN as e:
        raise dungeon._http(e)
