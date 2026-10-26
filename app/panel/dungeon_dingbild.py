"""KI-Dungeon-Master: Bilder für Ausrüstung und Zauber (plan dungeon-master/plan.md „5i“, Dominik 2026-10-23 „2“ and
„die Bildgeneration, aber auch startbar per Knopf direkt“). Builds on the game (dungeon.py) and on „Bilder malen“
(bilder.py); the function dungeonbilder (features.py, admin switch chat.dungeon_bilder, off) and the admin's
„Bilder malen“ must be on, else every item keeps its sign (ZEICHEN) and nothing is painted.

Two kinds of pictures, both painted by the fixed rules of the panel (the model chooses nothing):
- the catalog: one picture per entry of dungeon_regeln.json (weapons, armour, jewellery, potions, spells, scrolls,
  the admin's own entries too) in the fixed style of each world (dungeon.style: welten[].bildstil) and in the
  picture book style for the youngest tone while a round of that tone is open. The prompt is built from the
  catalog's English name and a fixed phrase per kind (ART_EN), checked like a picture wish (bilder.refuse_text);
  its hash names the file, so a changed style or name paints anew and the old file goes with the sweep. Painted
  in the night window NACHT (local time) and when the admin presses „Bilder jetzt erstellen“, one at a time
  through the heavy jobs' queue (schwer.py via dungeon._paint: the voice first, Wartungspause „bild“), at most
  TAG_MAX a day, the run stops on Notaus, a missing model or check, a closed switch, and „Anhalten“.
- a find: a named item of a round (the model's name, dungeon.loot) of at least rarity RANG_FUND gets its own
  picture once it is known (unknown magic only after naming), from the style of the round, the catalog's English
  name and the model's name and sentence, checked by dungeon.picture_text (tone, „nie“, taboos, word list, people);
  it counts to the game's day limit (dungeon._bild_take, grenzen.bilder_tag) and needs „Bilder malen“ of the host.
  Found by the minute loop (due), so the game's turn is never held up.

The map (dungeon_karte.py) adds its kinds of places and rooms to the catalog (wanted, painted alike) and an own
picture of every visited place (ort-<hash>, dungeon_karte.queue_orte from due, shown only to seats of its round).
The Bestiarium (dungeon.gegner) is painted alike, with its own fixed phrase FOE_EN, in the style of the worlds a foe
belongs to, from its English name, description (info, when the word list lets it through), size (GROESSE_EN) and
what it is by the panel's fixed lists MENSCH and HUMANOID (Dominik 2026-10-24 „2“). „Alle Bilder malen“ (grund
"alle") is the admin's run without the day limit. The hero form's peoples, classes and class abilities (Dominik 2026-10-24 „bilder keine icons“) are
painted alike, once each in every world's style with their own fixed phrases HELD_EN (hero_prompt; Punkt 8a of
2026-10-24: the style of the world, never fixed fantasy); the form shows the one of the world chosen, a round the one
of its world, until one is there a colour placeholder, never the old sign. Tools (art "werkzeug") have their own
phrase in ART_EN, no longer the scroll's. On the admin's tab „Regeln“ (dungeon_regelseite.py) „Nochmal malen“ paints one entry again as a candidate
neu-<hash> next to the picture in use (repaint, the same checks and day limit); „Neues behalten“ or „Altes behalten“
settles it, a candidate nobody settles goes with the sweep after NEU_S.

Every picture: FLUX through bilder.paint (NSFW above the limit and a missing check give no picture), the AI marks of
the service kept (bilder.quick_png „kleiner“: SIZE/2), stored as STATE/dungeon-bild/ding-<hash>.png or
fund-<iid>.png next to the scene pictures. Seats see it through view() (add: "bild" and "zeichen" on every item, a
copy); a profile loads it by GET /api/profile/dungeon/ding/<name>, a guest's seat by POST /api/dungeon/ding with its
code. Journal lines „dungeon: dingbild | …“, fixed words and numbers only; Live: dungeon's line, numbers only.

    GET    /api/profile/dungeon/ding/{name}     a picture of an item (the game released for the profile); ?klein=1 small
    POST   /api/dungeon/ding                    {code, name, klein}: the same for a guest's seat
    GET    /api/admin/dungeon/dingbilder        how far the pictures are (status)
    POST   /api/admin/dungeon/dingbilder        „Bilder jetzt erstellen“: the run starts now, not only at night
    DELETE /api/admin/dungeon/dingbilder        „Anhalten“: the run stops after the picture on its way
"""
import asyncio
import datetime
import hashlib
import os
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import dungeon_gesicht
import dungeon_wappen
import dungeon_karte
import features
import guard
import profiles
from common import STATE, DayCounter, read_json, write_json
from core import assistant, auth, json_body, own_profile, spawn

router = APIRouter()
KEY = "dungeonbilder"
FILE = os.path.join(STATE, "dungeon-dingbilder.json")
SIZE = 512                # painted square, kept at half (bilder.quick_png „kleiner“)
NACHT = (1, 5)            # the night window, local hours [from, to)
TAG_MAX = 300             # catalog pictures asked for a day on the whole Spark
RANG_FUND = 2             # a find from „rar“ on (index in seltenheit) gets its own picture
FEHL_MAX = 2              # a catalog picture refused this often is not tried again (until its prompt changes)
FUNDE_MAX = 2000          # finds the state file remembers
STOP = ("missing", "ohne_pruefung", "dienst", "zeit", "wartung", "memory", "belegt")   # a run ends on these
ART_EN = {"waffe": "a weapon", "ruestung": "a piece of armour", "schmuck": "a piece of jewellery",
          "trank": "a potion in a glass bottle", "zauber": "a magic spell, glowing magical energy",
          "rolle": "a rolled parchment scroll", "werkzeug": "a tool or a piece of gear, the object itself",
          "schatz": "a precious gem or a small work of art"}
ZEICHEN = {"waffe": "⚔️", "ruestung": "🛡️", "schmuck": "💍", "trank": "🧪", "zauber": "✨", "rolle": "📜", "werkzeug": "🧰", "schatz": "💎"}
ITEM_EN = "game item art, one single object in sharp focus"   # in a place of its kind (ORT_EN), Dominik 2026-10-25
# the world's style (welten[].bildstil) says fantasy, horror or science fiction, so these phrases name none (Dominik
# 2026-10-24 „alles umsetzten“, Punkt 8a: a sci-fi people was painted as a fantasy adventurer)
FOE_EN = "creature art for a bestiary, the whole creature"   # the Bestiarium (gegner);
# no "plain dark background": the world's style asks for a detailed one (Dominik 2026-10-24 „2“: a foe from its name only
# came out wrong, a Cultist as a horned demon), so the prompt has the English description (info), the size and what it is:
GROESSE_EN = {"winzig": "tiny", "klein": "small", "mittel": "human-sized", "gross": "large", "riesig": "huge"}
# what a foe is, by a fixed list of the panel (never the model's choice): people, and creatures shaped like people
MENSCH = frozenset(("bandit", "banditenhauptmann", "schlaeger", "kultist", "kultfanatiker", "wache", "veteran", "ritter",
                    "berserker", "spion", "assassine", "magier_gegner", "priester", "gladiator", "erzmagier", "raumpirat",
                    "cyborg_soeldner", "mutant", "meuterer", "piratenkapitaen", "puppenspieler",
                    # the bestiary's new foes (V01.1.039)
                    "enterkommando", "psi_adept", "schmuggler", "seehexe", "marinekapitaen", "verfluchter_kapitaen",
                    "puppenmacher", "seuchenarzt", "hexenmeister", "wegelagerer", "sternenfreibeuter"))
HUMANOID = frozenset(("goblin", "kobold", "ork_krieger", "hobgoblin", "grottenschrat", "gnoll", "dunkelelf", "duergar",
                      "echsenmensch", "sahuagin", "meerhexe", "waldhexe", "nachtvettel", "doppelgaenger", "vampirbrut",
                      "meermensch", "oni", "geisterpirat", "klabautermann", "schattenkind", "oger", "troll", "huegelriese",
                      "ettin", "azer", "dryade", "satyr", "zombie", "ghul", "grabschrecken", "grabunhold", "mumie",
                      "kampfsynth", "sicherheitsdroide", "tarnjaeger", "schrottkrieger", "admiral_des_nichts", "geistermatrose",
                      "die_bleiche_graefin", "lichkoenig", "frostriesin", "dunkelelf_klinge", "spiegelkoenigin", "schicksalsweber"))
WESEN_EN = {"mensch": "an ordinary human person", "humanoid": "a humanoid with two arms and two legs"}
HELD_EN = {"volk": "character art, a {} adventurer of this world, head and shoulders",   # Dominik 2026-10-24 „bilder keine icons“
           "klasse": "character art, a {} of this world, the whole figure, where such a person works in this world",
           "kraft": "game ability art, one glowing moment of power in the middle of action, no person in the centre: {}",
           # Dominik 2026-10-24 „1a 2 und 3“: backgrounds and worlds get pictures too, renewed on the rules page
           "hintergrund": "character art, a {} of this world in a fitting place, the whole figure"}
WELT_EN = "landscape art, a wide view of the world {}, no people"   # a world's title picture (its own style)
# the stage behind the story (Dominik 2026-10-24 „alle umsetzen“, idea 10): one wide picture per kind of place and room
# and style, shown until the scene has its own; neutral light and weather, the stage lays daytime and weather over it
BUEHNE_EN = "scene art, a wide view of {}"
# three of each (Dominik 2026-10-25 „alles nach empfehlung umsetzten“, plan „Bilder mit Flair“ 6a): the panel takes
# kampf while rd["kampf"] is set, nacht for rd["tageszeit"] abend or nacht, else tag; weather is a layer of the stage
LAGE_EN = {"tag": "atmospheric light and depth, mist in the distance, no people",
           "nacht": "at night, moonlight, warm lit windows and torches, deep shadows, no people",
           "kampf": "in the middle of a fight, sparks, smoke and dust, overturned things, hard dramatic light, "
                    "fighters only as distant silhouettes without faces"}
ABENDS = ("abend", "nacht")      # rd["tageszeit"] (dungeon.py: morgen, tag, abend, nacht) that shows the night picture
# Flair (Dominik 2026-10-25 „alles nach empfehlung umsetzten“, plan „Bilder mit Flair“): every picture takes light,
# angle and mood from fixed lists of the panel, one choice per entry and style (flair, never the model's), an item a
# place of its kind, a foe a pose and surroundings by its size, a hero a place and a pose; a fixed rarity shows.
LICHT_EN = ("morning light", "golden hour light", "moonlight", "candle glow", "storm light", "light falling through a window",
            "the glow of magic")
WINKEL_EN = ("close-up", "seen from a low angle", "seen from above", "three-quarter view", "seen through an archway")
STIMMUNG_EN = ("calm mood", "mysterious mood", "menacing mood", "festive mood", "forgotten and dusty mood")
SANFT = ("menacing mood", "storm light")          # never in the picture book (dungeon.BILD_KIND)
DUESTER = ("gothic", "horror", "grim", "dark")    # a world style with one of these words is never festive
ORT_EN = {"waffe": ("resting on an anvil in a smithy", "hanging on a weapon rack", "stuck in the ground of an old battlefield",
                    "lying on a war table with maps"),
          "ruestung": ("on an armour stand in an armoury", "lying on a soldier's bed in a barracks", "hanging in a tent of a camp"),
          "schmuck": ("on a velvet cushion", "spilling from a treasure chest", "on a dressing table"),
          "trank": ("on an alchemist's table between flasks", "on a dusty cellar shelf", "in a healer's open bag"),
          "zauber": ("rising from an open spell book on a lectern", "above a circle of old stones", "in a tower room full of books"),
          "rolle": ("on a writing desk beside a candle", "in a niche of a library", "lying on an old map"),
          "werkzeug": ("on a workbench", "in an open bag of gear", "on a table in a camp"),
          "schatz": ("on a pile of coins in a hoard", "in a display case", "in a hidden alcove")}
SELTEN_EN = {"gewoehnlich": "plain and a little worn", "selten": "well made", "rar": "finely crafted with silver details",
             "episch": "with glowing engravings", "legendaer": "with a radiant aura, glowing runes and drifting sparks"}
HALTUNG_EN = ("lurking in the shadows", "in the middle of an attack", "roaring", "stepping out of the darkness",
              "waiting for prey", "circling slowly")
HALTUNG_KIND = ("standing proudly", "peeking out curiously", "waiting patiently")   # the picture book: nothing scary
UMGEBUNG_EN = {"gross": ("in the open land of its world", "in a wide hall", "on a rocky slope"),   # large and huge
               "klein": ("in a narrow passage", "in a ruin", "in a thicket")}                    # the rest
HALTUNG_HELD = ("looking into the distance", "ready for action", "resting for a moment", "with a confident look")
# the settlement (Dominik 2026-10-25 „so umsetzten“, Siedlung mit Leben 2a/4a): one picture per service and style,
# no person in front, and a line of life per service and world from dungeon_siedlung.json (never the model's)
DIENST_EN = {"gasthaus": "the common room of an inn of this world with a fireplace and long tables",
             "schmied": "a smithy of this world, a glowing forge, an anvil and hanging tools",
             "lehre": "a study room of this world with books, a lectern and a practice yard outside",
             "geruecht": "a busy corner of a tavern or market of this world where rumours are told",
             "verbessern": "a workbench of this world where gear is improved, fine tools and parts",
             "heiler": "a calm healer's room of this world with drying herbs, clean bandages, a cot and small potion bottles",
             "gefaehrte": "a hiring corner by the door of an inn of this world, a notice board with offers, a travelling pack and a shield against the wall"}
SIEDLUNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dungeon_siedlung.json")
HELD_TEILE = {"voelker": "volk", "klassen": "klasse", "hintergruende": "hintergrund"}   # rules page part -> art
NEU = re.compile(r"neu-[0-9a-f]{16}")   # a picture painted again on the admin's „Nochmal malen“, next to the one in use
NEU_S = 86400             # a candidate nobody kept or dropped goes with the sweep after a day
NAME = re.compile(r"ding-[0-9a-f]{16}|fund-i[0-9a-f]{8}|ort-[0-9a-f]{16}|nsc-[0-9a-f]{16}")   # ort-: a place of the map (dungeon_karte), nsc-: a person's face (dungeon_gesicht)
_lauf = {"task": None, "grund": "", "start": 0.0, "gemalt": 0, "stop": False}
_funde = set()            # iids of finds being painted right now
_files = {"m": None, "set": frozenset()}
_gelesen = {"m": None, "d": None}
_sweep = [0.0]
_day = DayCounter(gemalt=0, verworfen=0, ausgefallen=0, funde=0)
clock = time.time        # the one clock of this module (the tests set it, nothing here reads the wall clock else)


def on():
    """The Spark allows it: the game's pictures switch (with the game) and the admin's „Bilder malen“."""
    import bilder
    return features.admin_on(KEY) and features.admin_on(bilder.KEY)


def _state():
    d = read_json(FILE, {})
    for k in ("tag", "fehl", "funde", "letzter", "zuletzt", "fest"):
        if not isinstance(d.get(k), dict):
            d[k] = {}
    return d


def _seen():
    """The state for the lookups of every view (read again only when the file changed)."""
    try:
        m = os.stat(FILE).st_mtime_ns
    except FileNotFoundError:
        m = None
    if m != _gelesen["m"] or _gelesen["d"] is None:
        _gelesen.update(m=m, d=_state())
    return _gelesen["d"]


def key_of(style, c, art=""):
    """An entry in a style, whatever its prompt says (the prompt's hash names the file, this key names the entry):
    art "volk"/"klasse"/"kraft" of the hero form, an item, or a foe (no "art")."""
    kind = art or ("ding" if "art" in c else "gegner")
    return "k" + hashlib.sha256(f"{style}|{kind}|{c.get('id')}".encode()).hexdigest()[:16]


def _pick(n, k, have):
    """The picture to show for an entry (Dominik 2026-10-24: pictures of the Bestiarium were gone after every
    restart, the sweep took them when a new version changed the prompt): the admin's own (fest) first, then the one
    of the current prompt, then the last one painted for the entry until the new one is there; n when none is."""
    d = _seen()
    for x in (d["fest"].get(k), n, d["zuletzt"].get(k)):
        if x and x in have:
            return x
    return n


def _save(d):
    if len(d.get("funde") or {}) > FUNDE_MAX:
        d["funde"] = dict(list(d["funde"].items())[-FUNDE_MAX:])
    write_json(FILE, d, mode=0o600, dir_mode=0o700)


def _date():
    return DayCounter.date(clock())


def _today(d):
    t = d["tag"]
    return t.get("n", 0) if t.get("day") == _date() else 0


def files():
    """The names of the item pictures there are (the folder read again only when it changed)."""
    try:
        m = os.stat(dungeon.BILD_DIR).st_mtime_ns
    except FileNotFoundError:
        return frozenset()
    if m != _files["m"]:
        names = os.listdir(dungeon.BILD_DIR)
        _files.update(m=m, set=frozenset(f[:-4] for f in names if f.endswith(".png") and NAME.fullmatch(f[:-4])))
    return _files["set"]


# ---------------------------------------------------------------- the catalog's pictures
def styles(r):
    """The styles to paint in: every world's (dungeon.style), the picture book only while a round of the youngest
    tone is open. Worlds of open rounds first."""
    jung = min(t["id"] for t in r["toene"])
    rs = [v for v in dungeon._read()["runden"].values() if v.get("status") != "ende"]
    used = [v.get("welt") for v in rs]
    welten = sorted(r["welten"], key=lambda w: (w["id"] not in used, r["welten"].index(w)))
    out = []
    for w in welten:
        s = dungeon.style(r, {"welt": w["id"], "ton": None})
        if s not in out:
            out.append(s)
    if any(v.get("ton") == jung for v in rs):
        out.append(dungeon.BILD_KIND)
    return out


def _wahl(seq, *keys):
    """One fixed choice from a list for an entry: the same every time (sha256 of the keys), never the model's."""
    return seq[int(hashlib.sha256("|".join(str(k) for k in keys).encode()).hexdigest()[:8], 16) % len(seq)]


def flair(style, c, teil, weit=False):
    """The light, angle and mood of an entry's picture in a style from the fixed lists (plan „Bilder mit Flair“ 1a):
    the picture book never menacing or stormy, a dark world style never festive; weit (places, worlds, the stage): no
    close-up."""
    low = style.lower()
    no = set(SANFT) if style == dungeon.BILD_KIND else set()
    no |= {"festive mood"} if any(w in low for w in DUESTER) else set()
    key = (style, teil, c.get("id"))
    licht = _wahl([x for x in LICHT_EN if x not in no], *key, "licht")
    winkel = _wahl([x for x in WINKEL_EN if not (weit and x == "close-up")], *key, "winkel")
    return f"{licht}, {winkel}, {_wahl([x for x in STIMMUNG_EN if x not in no], *key, 'stimmung')}"


def prompt(style, c):
    """The fixed prompt of a catalog entry in a style: the English name, the kind's phrase, a spell's sentence; a foe
    of the Bestiarium (no "art") its own fixed phrase."""
    if "art" not in c:
        import bilder
        wesen = WESEN_EN["mensch"] if c.get("id") in MENSCH else WESEN_EN["humanoid"] if c.get("id") in HUMANOID else ""
        info = (c.get("info") or ["", ""])[1]
        info = "" if bilder.refuse_text("", info) else info          # a description the word list refuses stays out
        size = GROESSE_EN.get(c.get("groesse", "mittel"), "") if wesen or c.get("groesse", "mittel") != "mittel" else "medium-sized"
        kid = style == dungeon.BILD_KIND
        pose = _wahl(HALTUNG_KIND if kid else HALTUNG_EN, style, "gegner", c.get("id"), "haltung")
        place = _wahl(UMGEBUNG_EN["gross" if c.get("groesse") in ("gross", "riesig") else "klein"], style, "gegner", c.get("id"), "ort")
        parts = [c["name"][1], wesen, size, info, pose, place, flair(style, c, "gegner")]
        return f"{style}, {FOE_EN}: " + ", ".join(x.strip().rstrip(".") for x in parts if x and x.strip()) + f", {dungeon.BILD_ENDE}"
    extra = f", {c['satz'][1]}" if c["art"] == "zauber" and c.get("satz") else ""
    selten = f", {SELTEN_EN[c['seltenheit']]}" if c.get("seltenheit") in SELTEN_EN else ""
    where = _wahl(ORT_EN[c["art"]], style, "ding", c.get("id"), "ort")
    return (f"{style}, {ITEM_EN}: {c['name'][1]}, {ART_EN[c['art']]}{extra}{selten}, {where} of this world, "
            f"the place softly blurred behind it, {flair(style, c, 'ding')}, {dungeon.BILD_ENDE}")


def hero_prompt(r, art, c, welt=""):
    """The fixed prompt of a people (art "volk"), a class ("klasse") or a class's ability ("kraft") of the hero form in
    the style of a world (welt, else the first; one picture each per world): the English name, an ability's sentence."""
    return _hero_text(dungeon.style(r, {"welt": welt or r["welten"][0]["id"], "ton": None}), art, c)


def _hero_text(style, art, c):
    import bilder
    what = f"{c['name'][1]}, {c['satz'][1]}" if art == "kraft" else c["name"][1]
    info = (c.get("info") or ["", ""])[1].strip().rstrip(".") if art == "hintergrund" else ""
    if info and not bilder.refuse_text("", info):                      # a description the word list refuses stays out
        what += f", {info}"
    pose = "" if art == "kraft" else f", {_wahl(HALTUNG_HELD, style, art, c.get('id'), 'haltung')}"
    return f"{style}, {HELD_EN[art].format(what)}{pose}, {flair(style, c, art, art != 'kraft')}, {dungeon.BILD_ENDE}"


def world_text(r, w):
    """A world's title picture in its own style: the English name and sentence, no people (Dominik 2026-10-24 „3“)."""
    s = dungeon.style(r, {"welt": w["id"], "ton": None})
    return f"{s}, {WELT_EN.format(w['name'][1] + ', ' + w['satz'][1])}, {flair(s, w, 'welt', True)}, {dungeon.BILD_ENDE}"


def world_pic(r, w, have=None):
    """The name of a world's title picture once it is painted (and the pictures are on), else ""."""
    have = (files() if on() else frozenset()) if have is None else have
    n = _pick(name_of(world_text(r, w)), key_of(dungeon.style(r, {"welt": w["id"], "ton": None}), w, "welt"), have)
    return n if n in have else ""


def stage_text(style, e, room=False, lage="tag"):
    """The fixed prompt of a kind of place (ortsarten) or room (raeume) as the stage's backdrop in one of its three
    situations (LAGE_EN): the English name, a room's sentence too, never the model's words; the day picture with a
    light and mood of the lists."""
    what = f"{e['name'][1]}, {e['satz'][1]}" if room and e.get("satz") else e["name"][1]
    more = f", {flair(style, e, 'raum' if room else 'ortsart', True)}" if lage == "tag" else ""
    return f"{style}, {BUEHNE_EN.format(what)}, {LAGE_EN[lage]}{more}, {dungeon.BILD_ENDE}"


def stage_key(style, e, room, lage):
    return key_of(style, e, f"buehne-{'raum' if room else 'ort'}-{lage}")


def _is_stage(p):
    return BUEHNE_EN.split("{}")[0] in p


def stages(r, style):
    """[(name, prompt, key)] of the stage pictures in one style: the kinds of places of its worlds, the rooms (a room
    without worlds is in every vault), each by day, by night and in a fight."""
    ws = dungeon_karte._worlds(r, style)
    return [(name_of(p), p, stage_key(style, e, room, lage)) for k, room in (("ortsarten", False), ("raeume", True))
            for e in r.get(k) or [] if not e.get("welten") or set(e["welten"]) & ws
            for lage in LAGE_EN for p in [stage_text(style, e, room, lage)]]


def lage(rd):
    """The stage's situation by fixed rules: kampf while a fight runs, nacht in the evening and at night (an unknown
    daytime counts as day)."""
    return "kampf" if rd.get("kampf") else "nacht" if rd.get("tageszeit", "tag") in ABENDS else "tag"


def stage_pic(r, rd, have=None):
    """The stage's stand-in picture of a round (dungeon.js shows it only while the scene has no picture of its own):
    the kind of the place it is at, in a vault the kind of its room, in the round's style and situation (lage). The
    name once painted (or the last one painted for it, _pick) and the pictures on, else ""."""
    k = rd.get("karte")
    if not k:
        return ""
    have = (files() if on() else frozenset()) if have is None else have
    v = dungeon_karte.vault(rd)
    if v:
        try:
            here = v["raeume"][v["hier"]]
        except (KeyError, IndexError, TypeError):
            return ""
        rs = r.get("raeume") or []      # an entry the admin deleted: the first room of the same kind (boss, falle …)
        e = next((x for x in rs if x["id"] == here.get("t")), None) or next((x for x in rs if x.get("art") == here.get("art")), None)
        room = True
    else:
        try:
            art = k["orte"][k["hier"]]["art"]
        except (KeyError, IndexError, TypeError):
            return ""
        e, room = next((x for x in r.get("ortsarten") or [] if x["id"] == art), None), False
    if not e:
        return ""
    s, lg = dungeon.style(r, rd), lage(rd)
    n = _pick(name_of(stage_text(s, e, room, lg)), stage_key(s, e, room, lg), have)
    return n if n in have else ""


def service_text(style, d):
    """The fixed prompt of a settlement's service (DIENST_EN) in a style, with light, angle and mood of the lists."""
    return f"{style}, scene art, {DIENST_EN[d]}, no people in the foreground, {flair(style, {'id': d}, 'dienst', True)}, {dungeon.BILD_ENDE}"


REQUISITEN_MAX = 3         # props of a fight a scene picture names (dungeon_umgebung: 2 to 3 per place)


def props(r, rd):
    """D&D-Idee 3 of round 2 (Umgebung nutzen): the props of the fight still there (dungeon_umgebung.here, rows of
    ideen.requisiten) in the scene picture, by their English catalog name, never the model's text; a name the picture
    rules refuse is left out. "" without a fight, without props or while „Umgebung nutzen“ is off."""
    import dungeon_umgebung
    s = dungeon.style(r, rd)
    names = [str(x["name"][1]).strip().lower() for x in dungeon_umgebung.here(r, rd)[:REQUISITEN_MAX]
             if isinstance(x.get("name"), list) and len(x["name"]) == 2 and _ok_text(f"{s}, {x['name'][1]}", r)]
    return f", {', '.join(names)} clearly visible in the scene" if names else ""


def service_key(style, d):
    return key_of(style, {"id": d}, "dienst")


def services(style):
    """[(name, prompt, key)] of the settlement's service pictures in one style."""
    return [(name_of(p), p, service_key(style, d)) for d in DIENST_EN for p in [service_text(style, d)]]


_zeilen = {}


def lines():
    """{welt|"alle": {service: [[de, en], …]}} from dungeon_siedlung.json (read once)."""
    if "z" not in _zeilen:
        _zeilen["z"] = read_json(SIEDLUNG, {}).get("zeilen") or {}
    return _zeilen["z"]


def line(rd, d):
    """A line of life for a service in the round's world and language: another one at every turn and place, the
    same within one (sha256 of turn, place and service), never the model's; "" for a service without lines."""
    z = lines()
    pool = (z.get(rd.get("welt")) or {}).get(d) or (z.get("alle") or {}).get(d) or []
    if not pool:
        return ""
    k = rd.get("karte") or {}
    return _wahl(pool, rd.get("zug", 0), k.get("hier"), d)[1 if rd.get("lang") == "en" else 0]


def settle_view(r, rd, sv, have):
    """dungeon_gold.view's settlement for the own seat: "kopf" the place's stage picture (by day or at night), and
    per service "bild" (its picture in the round's style once painted) and "zeile" (a line of life)."""
    s = dungeon.style(r, rd)
    sv = dict(sv, kopf=stage_pic(r, rd, have))
    out = []
    for x in sv.get("dienste") or []:
        d = x.get("id")
        n = _pick(name_of(service_text(s, d)), service_key(s, d), have) if d in DIENST_EN else ""
        out.append(dict(x, bild=n if n in have else "", zeile=line(rd, d)))
    sv["dienste"] = out
    return sv


def heroes(r):
    """[(art, entry)] of every people, class, class ability and background there is a picture for."""
    return [("volk", v) for v in r["voelker"]] + [("klasse", k) for k in r["klassen"]] + \
        [("kraft", f) for k in r["klassen"] for f in k["faehigkeiten"]] + \
        [("hintergrund", h) for h in r.get("hintergruende") or []]


def hero_pic(r, art, c, have=None, welt=""):
    """The picture name of a people, class or ability in a world's style (welt, else the first) once it is painted (and
    the pictures are on), else ""."""
    have = (files() if on() else frozenset()) if have is None else have
    s = dungeon.style(r, {"welt": welt or r["welten"][0]["id"], "ton": None})
    n = _pick(name_of(_hero_text(s, art, c)), key_of(s, c, art), have)
    return n if n in have else ""


def hero_pics(r, art, c, have=None):
    """{world id: picture name} of a people, class or ability, the worlds it is painted for (the hero form shows the
    one of the world chosen, dungeon.js dmHB)."""
    have = (files() if on() else frozenset()) if have is None else have
    out = {}
    for w in r["welten"]:
        n = hero_pic(r, art, c, have, w["id"])
        if n:
            out[w["id"]] = n
    return out


def name_of(p):
    return "ding-" + hashlib.sha256(p.encode()).hexdigest()[:16]


def wanted(r):
    """[(name, prompt)] of every catalog picture there should be, in painting order (style by style): the items,
    then the map's kinds of places and rooms (dungeon_karte.bilder), then the foes of that world (dungeon.gegner), then
    the peoples, classes and abilities of the hero form in that world's style (hero_prompt; not in the picture book)."""
    return [(n, p) for n, p, _ in _want(r)]


def _want(r):
    """wanted with the entry's key (key_of; None for the map's kinds, dungeon_karte names them itself)."""
    out, seen = [], set()
    for s in styles(r):
        welten = {w["id"] for w in r["welten"] if dungeon.style(r, {"welt": w["id"], "ton": None}) == s} or {w["id"] for w in r["welten"]}
        foes = [c for c in r.get("gegner") or [] if "alle" in c.get("welten", ["alle"]) or welten & set(c.get("welten") or [])]
        for n, p, k in [(name_of(prompt(s, c)), prompt(s, c), key_of(s, c)) for c in r["gegenstaende"]] + \
                dungeon_karte.bilder(r, s) + stages(r, s) + services(s) + \
                [(name_of(prompt(s, c)), prompt(s, c), key_of(s, c)) for c in foes] + \
                ([(name_of(_hero_text(s, a, c)), _hero_text(s, a, c), key_of(s, c, a)) for a, c in heroes(r)] +
                 [(name_of(world_text(r, w)), world_text(r, w), key_of(s, w, "welt")) for w in r["welten"] if w["id"] in welten]
                 if s != dungeon.BILD_KIND else []):
            if n not in seen:
                seen.add(n)
                out.append((n, p, k))
    return out


def _ok_text(p, r=None):
    """A catalog prompt passes the picture rules (the admin's entries are data too, a foe's description as well): the
    word list of „Bilder malen“, the game's list „nie“, in the picture book style the youngest tone's words."""
    import bilder
    if r is not None:
        low = " " + p.lower() + " "
        if any(w.lower() in low for w in r["nie"]) or \
                p.startswith(dungeon.BILD_KIND) and dungeon.bad_words(r, {"ton": min(t["id"] for t in r["toene"])}, p):
            return False
    return not bilder.refuse_text("", p)


def _stand(d, have, n, k):
    """An entry's state, the one rule for missing and status: "da" (the current prompt's picture is there), "fest"
    (a picture the admin kept by hand stands for it, a later prompt does not paint it over), "abgelehnt" (refused too
    often) or "offen" (a run paints it)."""
    if n in have:
        return "da"
    if k and d["fest"].get(k) in have:
        return "fest"
    return "abgelehnt" if d["fehl"].get(n, 0) >= FEHL_MAX else "offen"


def missing(r, d=None):
    """What a run still paints (_stand "offen")."""
    d = _state() if d is None else d
    have = files()
    return [(n, p) for n, p, k in _want(r) if _stand(d, have, n, k) == "offen"]


def _night(now):
    h = datetime.datetime.fromtimestamp(now).hour
    return NACHT[0] <= h < NACHT[1]


def start(grund):
    """Starts a run (grund "nacht", "knopf", or "alle": the admin's „Alle Bilder malen“ without the day limit, Dominik
    2026-10-24 „alle bilder generieren lassen knopf ohne sich ans limit zu halten“; space and the queue hold) unless
    one runs; returns False when it cannot (off or running)."""
    if not on() or (_lauf["task"] and not _lauf["task"].done()):
        return False
    _lauf.update(grund=grund, start=clock(), gemalt=0, stop=False)
    _lauf["task"] = spawn(_run(grund), name="dungeon-dingbild")
    print(f"dungeon: dingbild | lauf start | {grund}", flush=True)
    return True


def stop():
    if _lauf["task"] and not _lauf["task"].done():
        _lauf["stop"] = True
        print("dungeon: dingbild | lauf anhalten", flush=True)
        return True
    return False


def _end_why(grund):
    """Why the run should end before the next picture ("" = go on)."""
    import notaus
    import schwer
    if _lauf["stop"]:
        return "angehalten"
    if not on():
        return "aus"
    if notaus.blocks("auto"):
        return "notaus"
    if grund == "nacht" and not _night(clock()):
        return "morgen"
    if grund != "alle" and _today(_state()) >= TAG_MAX:
        return "tag"
    if schwer.full():
        return "voll"
    return ""


async def paint_one(n, p):
    """One picture through the game's painter (dungeon._paint), kept at half size with its AI marks; a stage picture
    (BUEHNE_EN) in the scene's 16:9 (dungeon.BILD_W × BILD_H). Returns "ok" or the reason it did not come
    (dungeon.BILD_GRUENDE)."""
    import bilder
    w, h = (dungeon.BILD_W, dungeon.BILD_H) if _is_stage(p) else (SIZE, SIZE)
    try:
        png = await dungeon._paint(secrets.token_hex(6), p, w, h)
        png, _, _ = await asyncio.to_thread(bilder.quick_png, png, "kleiner")
        await asyncio.to_thread(dungeon._bild_save, n, png)
        return "ok"
    except ValueError as e:
        return dungeon._bild_why(e)
    except Exception:   # noqa: BLE001 - every picture ends with a journal line
        return "dienst"


async def _run(grund):
    why, tried = "fertig", set()          # a picture that did not come waits for the next run
    try:
        while True:
            why = await asyncio.to_thread(_end_why, grund) or "fertig"
            if why != "fertig":
                break
            r = dungeon.rules()
            todo = [x for x in await asyncio.to_thread(missing, r) if x[0] not in tried]
            keys = {x[0]: x[2] for x in await asyncio.to_thread(_want, r)} if todo else {}
            if not todo:
                break
            n, p = todo[0]
            tried.add(n)
            t0 = time.perf_counter()
            res = await paint_one(n, p) if _ok_text(p, r) else "wortliste"

            def note():
                d = _state()
                if res != "wortliste":            # every picture asked for counts, so a refusing check cannot run on
                    d["tag"] = {"day": _date(), "n": _today(d) + 1}
                if res != "ok":
                    d["fehl"][n] = d["fehl"].get(n, 0) + (FEHL_MAX if res == "wortliste" else 1)
                elif keys.get(n):
                    d["zuletzt"][keys[n]] = n           # shown until a later prompt's picture is there
                _save(d)
            await asyncio.to_thread(note)
            if res == "ok":
                _lauf["gemalt"] += 1
            _day.bump("gemalt" if res == "ok" else "verworfen" if res in ("pruefung", "ohne_pruefung", "wortliste") else "ausgefallen")
            print(f"dungeon: dingbild | {res} | katalog | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)
            if res in STOP:
                why = res
                break
    finally:
        def last():
            d = _state()
            d["letzter"] = {"grund": grund, "start": _lauf["start"], "ende": clock(), "gemalt": _lauf["gemalt"], "warum": why}
            if grund == "nacht":
                d["nacht"] = _date()
            _save(d)
        await asyncio.to_thread(last)
        print(f"dungeon: dingbild | lauf ende | {why} | {_lauf['gemalt']} gemalt", flush=True)


# ---------------------------------------------------------------- a named find's own picture
def _finds(r, rd):
    """The named items of the round's heroes and its ground that are known and rare enough."""
    rank = [x["id"] for x in r["seltenheit"]]
    items = list(rd.get("boden") or [])
    for p in rd["plaetze"].values():
        h = p.get("held") or {}
        items += [x for x in (h.get("an") or {}).values() if x] + list(h.get("tasche") or [])
    return [it for it in items if it.get("eigen") and not it.get("u") and it.get("s") in rank and rank.index(it["s"]) >= RANG_FUND
            and it.get("id") in dungeon._by(r, "gegenstaende")]


def find_prompt(r, rd, it):
    c = dungeon._by(r, "gegenstaende")[it["id"]]
    return f"{ART_EN[c['art']]}, {c['name'][1]}, a unique treasure named {it['eigen']}" + (f", {it['satz']}" if it.get("satz") else "")


def queue_finds():
    """Inside dungeon._lock: every named find without a picture, of rounds whose host has „Bilder malen“, within the
    game's day limit (dungeon._bild_take). Returns [(name, prompt)] to paint."""
    import schwer
    r = dungeon.rules()
    out = []
    with dungeon._lock:
        d = dungeon._read()
        st = _state()
        have, taken, changed = files(), False, False
        for rid, rd in d["runden"].items():
            if rd.get("status") != "laeuft" or not dungeon.pictures_on(rd["owner"]):
                continue
            for it in _finds(r, rd):
                n = "fund-" + it["i"]
                f = st["funde"].get(it["i"]) or {}
                if n in have or it["i"] in _funde or f.get("st") in ("ok", "weg") or f.get("st") == "tag" and f.get("day") == _date():
                    continue
                text, why = dungeon.picture_text(r, rd, find_prompt(r, rd, it))
                if not why and dungeon._bild_tag_voll(r, d, rd):
                    why = "tag"
                if not why and schwer.full():
                    continue
                if why:
                    st["funde"][it["i"]] = {"st": "tag" if why == "tag" else "weg", "day": _date()}
                    changed = True
                    print(f"dungeon: dingbild | abgelehnt | fund | {why}", flush=True)
                    continue
                dungeon._bild_take(d)
                taken = True
                _funde.add(it["i"])
                out.append((n, f"{dungeon.style(r, rd)}, {text}, {dungeon.BILD_ENDE}"))
        if taken:
            dungeon._write(d)
        if changed:
            _save(st)
    return out


async def paint_find(n, p):
    t0 = time.perf_counter()
    iid = n[5:]
    try:
        res = await paint_one(n, p)
    finally:
        _funde.discard(iid)

    def note():
        d = _state()
        d["funde"][iid] = {"st": "ok" if res == "ok" else "weg" if res in ("pruefung", "ohne_pruefung") else "fehler", "day": _date()}
        _save(d)
    await asyncio.to_thread(note)
    _day.bump("funde" if res == "ok" else "verworfen" if res in ("pruefung", "ohne_pruefung") else "ausgefallen")
    print(f"dungeon: dingbild | {res} | fund | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)


# ---------------------------------------------------------------- the minute loop (panel.py every_minute)
async def due():
    """Each minute: the people's faces (dungeon_gesicht: „Bilder malen“ without this switch), the sweep of the arms
    (dungeon_wappen), the finds, the night's run once a night, the sweep at most hourly."""
    now = clock()
    for rid, k, n, p in await asyncio.to_thread(dungeon_gesicht.queue):
        spawn(dungeon_gesicht.paint(rid, k, n, p), name="dungeon-gesicht")
    await asyncio.to_thread(dungeon_gesicht.sweep, now)
    await asyncio.to_thread(dungeon_wappen.sweep, now)     # the host's choices of arms of rounds that are gone
    if not on():
        return
    for n, p in await asyncio.to_thread(queue_finds):
        spawn(paint_find(n, p), name="dungeon-dingbild")
    for rid, i, n, p in await asyncio.to_thread(dungeon_karte.queue_orte):
        spawn(dungeon_karte.paint_ort(rid, i, n, p), name="dungeon-dingbild")
    if _night(now) and await asyncio.to_thread(lambda: _state().get("nacht") != _date()):
        if await asyncio.to_thread(lambda: bool(missing(dungeon.rules()))):
            start("nacht")
    await asyncio.to_thread(sweep, now)


def sweep(now=None, force=False):
    """At most every hour: catalog pictures no style or entry asks for any more, finds no round, hero, Figur-Code or
    campaign keeps."""
    now = clock() if now is None else now
    if not force and now - _sweep[0] < 3600:
        return 0
    _sweep[0] = now
    r = dungeon.rules()
    if not _complete(r):                     # the rules fell back (no SRD): never take pictures of the missing entries
        print("dungeon: dingbild | aufraeumen ausgelassen | regeln unvollstaendig", flush=True)
        return 0
    want = _want(r)
    st = _state()
    ks = {k for _, _, k in want if k}
    keep = {n for n, _, _ in want} | {st[t][k] for t in ("zuletzt", "fest") for k in ks if st[t].get(k)}
    if any(set(st[t]) - ks for t in ("zuletzt", "fest")):
        for t in ("zuletzt", "fest"):
            st[t] = {k: v for k, v in st[t].items() if k in ks}
        _save(st)
    iids = set()

    def held(h):
        for x in list((h or {}).get("an", {}).values()) + list((h or {}).get("tasche") or []):
            if isinstance(x, dict):
                iids.add(x.get("i"))
    d = dungeon._read()
    orte = dungeon_karte.keep(d)
    for v in d["runden"].values():
        for p in v["plaetze"].values():
            held(p.get("held"))
        iids.update(x.get("i") for x in v.get("boden") or [])
    for f in dungeon._read_fig()["figuren"].values():
        held(f.get("held"))
    for uid in profiles.user_ids():
        for h in dungeon.heroes(uid):
            held(h)
        for c in dungeon.campaigns(uid).values():
            for h in c.get("gaeste") or []:
                held(h)
    gone = 0
    for n in candidates():
        try:
            if now - os.path.getmtime(dungeon.bild_file(n)) > NEU_S:
                dungeon._bild_rm(n)
                gone += 1
        except OSError:
            pass
    for n in files():
        if n.startswith("ding-") and n not in keep or n.startswith("fund-") and n[5:] not in iids or n.startswith("ort-") and n not in orte:
            dungeon._bild_rm(n)
            gone += 1
    if gone:
        print(f"dungeon: dingbild | aufgeraeumt | {gone} bilder", flush=True)
    return gone


# ---------------------------------------------------------------- what a seat sees (dungeon.view)
def add(r, rd, out):
    """dungeon.view's last step: every item of the view (bags, slots, ground, merchant, offers, log) gets "zeichen"
    (the sign of its kind) and "bild" (the name of its picture, "" while there is none): a find's own once known,
    else the catalog's in the round's style. Items are copied, nothing of the round changes."""
    have = files() if on() else frozenset()
    style = dungeon.style(r, rd)
    cat = dungeon._by(r, "gegenstaende")

    def item(x):
        c = cat.get(x["id"])
        bild = ""
        if c and have:
            f = "fund-" + str(x.get("i"))
            bild = f if not x.get("u") and f in have else _pick(name_of(prompt(style, c)), key_of(style, c), have)
            bild = bild if bild in have else ""
        return dict(x, zeichen=ZEICHEN.get(x.get("art"), dungeon.ZEICHEN), bild=bild)

    def walk(v):
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            w = {k: walk(x) for k, x in v.items()}
            return item(w) if {"i", "id", "art", "selten"} <= w.keys() else w
        return v
    for k in list(out):
        out[k] = walk(out[k])
    out["buehne"] = {"ersatz": stage_pic(r, rd, have)}   # the stage's stand-in until the scene has its own picture
    if isinstance(out.get("siedlung"), dict):              # the settlement's head and service pictures, lines of life
        out["siedlung"] = settle_view(r, rd, out["siedlung"], have)
    return dungeon_wappen.add(rd, dungeon_gesicht.add(rd, out))   # the faces of the people met (Tabletop-Punkt 15), the arms (D&D-Idee 10)


# ---------------------------------------------------------------- „Nochmal malen“ (the admin's rules page)
def candidates():
    try:
        return [f[:-4] for f in os.listdir(dungeon.BILD_DIR) if f.endswith(".png") and NEU.fullmatch(f[:-4])]
    except FileNotFoundError:
        return []


def _complete(r):
    """The rules in force hold every shipped item and foe but those the admin hid (dungeon.rules falls back to the
    rules without the SRD data when they do not pass; a sweep then would take hundreds of pictures)."""
    base = dungeon._base_rules()
    own = dungeon.own_rules()
    own = own if isinstance(own, dict) else {}
    for teil in ("gegner", "gegenstaende"):
        hidden = {str(e.get("id")) for e in own.get(teil) or [] if isinstance(e, dict) and e.get("aus") is True}
        if {str(x["id"]) for x in base.get(teil) or []} - hidden - {str(x["id"]) for x in r.get(teil) or []}:
            return False
    return True


def picture_of(r, c, welt=""):
    """The name of a catalog entry's picture in the style of its world (the first it belongs to, else the first
    world), and whether it is there: the admin's own, else the current prompt's, else the last one painted (_pick)."""
    s = dungeon.style(r, {"welt": welt or _welt(r, c), "ton": None})
    have = files()
    n = _pick(name_of(prompt(s, c)), key_of(s, c), have)
    return n, n in have


def _current(r, c, teil="", welt=""):
    """(name of the current prompt's picture, prompt, key) of an entry of the rules page: an item or foe in its
    world's style, a people, class or background in the style of welt (else the first world), a world in its own."""
    if teil in HELD_TEILE:
        s = dungeon.style(r, {"welt": welt or r["welten"][0]["id"], "ton": None})
        p = _hero_text(s, HELD_TEILE[teil], c)
        return name_of(p), p, key_of(s, c, HELD_TEILE[teil])
    if teil == "welten":
        p = world_text(r, c)
        return name_of(p), p, key_of(dungeon.style(r, {"welt": c["id"], "ton": None}), c, "welt")
    s = dungeon.style(r, {"welt": _welt(r, c), "ton": None})
    return name_of(prompt(s, c)), prompt(s, c), key_of(s, c)


def entry_pic(r, teil, c, welt=""):
    """The picture of an entry of the rules page as shown (_pick), and whether it is there."""
    n, _, k = _current(r, c, teil, welt)
    have = files()
    n = _pick(n, k, have)
    return n, n in have


def _welt(r, c):
    ws = [w for w in c.get("welten") or [] if w != "alle"]
    return ws[0] if ws else r["welten"][0]["id"]


async def repaint(r, c, frei=False, teil="", welt=""):
    """Paints a catalog entry's picture once more as a candidate neu-<hash> next to the one in use (the same checks
    and day limit as every catalog picture; frei: the admin's own button, no day limit, Dominik 2026-10-24 „im
    Dungeon-Master kann ich keine neuen Bilder erstellen“, it still counts). Returns ("ok", name) or (reason, "")."""
    if not on():
        return "aus", ""
    d = _state()
    if _today(d) >= TAG_MAX and not frei:
        return "tag", ""
    n, p, _ = _current(r, c, teil, welt)
    if not _ok_text(p, r):
        return "pruefung", ""
    neu = "neu-" + n[5:]
    why = await paint_one(neu, p)

    def note():
        d = _state()
        d["tag"] = {"day": _date(), "n": _today(d) + 1}
        _save(d)
    await asyncio.to_thread(note)
    print(f"dungeon: dingbild | nochmal | {why}", flush=True)
    return (why, neu if why == "ok" else "")


def settle(r, c, keep_new, teil="", welt=""):
    """„Neues behalten“ puts the candidate in place of the picture and keeps it as the admin's own (fest: a later
    prompt does not paint it over, the sweep keeps it), „Altes behalten“ drops it."""
    n, _, k = _current(r, c, teil, welt)
    neu = "neu-" + n[5:]
    if not os.path.exists(dungeon.bild_file(neu)):
        raise LookupError("bild")
    if keep_new:
        os.replace(dungeon.bild_file(neu), dungeon.bild_file(n))
        d = _state()
        d["fest"][k] = d["zuletzt"][k] = n
        _save(d)
    else:
        dungeon._bild_rm(neu)
    print(f"dungeon: dingbild | nochmal | {'neu behalten' if keep_new else 'alt behalten'}", flush=True)


# ---------------------------------------------------------------- Live and the admin's page
def status(r=None):
    r = r or dungeon.rules()
    d = _state()
    have = files()
    st = [_stand(d, have, n, k) for n, _, k in _want(r)]
    # an entry the admin kept by hand counts as done: „Alle Bilder malen · N“ names only what a run paints (Dominik
    # 2026-10-26: 3984/3990 and „· 6“, but every run ended at once with 0 painted)
    return {"an": features.admin_on(KEY), "bilder": on(), "fertig": sum(1 for x in st if x in ("da", "fest")), "von": len(st),
            "offen": st.count("offen"), "abgelehnt": st.count("abgelehnt"),
            "funde": sum(1 for n in have if n.startswith("fund-")), "heute": _today(d), "tag_max": TAG_MAX,
            "nacht": [f"{NACHT[0]:02d}:00", f"{NACHT[1]:02d}:00"], "stile": len(styles(r)),
            "laeuft": bool(_lauf["task"] and not _lauf["task"].done()), "grund": _lauf["grund"], "gemalt": _lauf["gemalt"],
            "letzter": d["letzter"]}


def for_live():
    """Numbers only: pictures there are, missing, painted today, refused, failed, whether a run is on."""
    if not features.admin_on(KEY):
        return {"on": False}
    t = _day.counts()
    have = files()
    return {"on": True, "da": sum(1 for n in have if n.startswith("ding-")), "funde_da": sum(1 for n in have if n.startswith("fund-")),
            "gemalt": t["gemalt"], "funde": t["funde"], "verworfen": t["verworfen"], "ausgefallen": t["ausgefallen"],
            "laeuft": bool(_lauf["task"] and not _lauf["task"].done()), "malt_funde": len(_funde)}


# ---------------------------------------------------------------- endpoints
def _png(name, klein=False):
    """klein: the small copy for the bag, the seats and the map (dungeon.small_png; Dominik 2026-10-25: 23 pictures of
    80 to 140 kB made the table slow over the proxy)."""
    if not NAME.fullmatch(str(name or "")):
        raise LookupError("bild")
    return dungeon.small_png(name) if klein else dungeon._png(name)


def _may_see(name, uid=None, rid=None):
    """A place's picture and a person's face only for a seat of their round; an item's for every seat."""
    return dungeon_karte.may_see(name, uid=uid, rid=rid) and dungeon_gesicht.may_see(name, uid=uid, rid=rid)


@router.get("/api/profile/dungeon/ding/{name}", dependencies=[Depends(assistant)])
async def ding(name: str, request: Request, prof=Depends(own_profile), klein: int = 0):
    """A picture of an item, for a profile the game is released for; ?klein=1 the small copy."""
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeonding", uid)
    try:
        if not await asyncio.to_thread(_may_see, name, uid=uid):
            raise LookupError("bild")
        return dungeon._png_out(await asyncio.to_thread(_png, name, bool(klein)))
    except LookupError as e:
        raise dungeon._http(e)


@router.post("/api/dungeon/ding")
async def gast_ding(request: Request):
    """{"code", "name", "klein"}: a picture of an item for a guest's seat (klein: the small copy)."""
    b, rid, _ = await dungeon._guest(request)
    guard.limit(request, "dungeonding")
    try:
        if not await asyncio.to_thread(_may_see, b.get("name"), rid=rid):
            raise LookupError("bild")
        return dungeon._png_out(await asyncio.to_thread(_png, b.get("name"), b.get("klein") is True))
    except LookupError as e:
        raise dungeon._http(e)


@router.get("/api/admin/dungeon/dingbilder", dependencies=[Depends(auth)])
async def admin_status():
    """How far the pictures are (the admin's page asks again every few seconds while a run is on)."""
    return await asyncio.to_thread(status)


@router.post("/api/admin/dungeon/dingbilder", dependencies=[Depends(auth)])
async def admin_start(request: Request):
    """„Bilder jetzt erstellen“: the run starts now (the same rules as at night, without the window); {"alle": true}
    „Alle Bilder malen“: without the day limit too (only the admin reaches this, coadmin.unbegrenzt's rule)."""
    guard.limit(request, "dungeonding", admin=True)
    b = await json_body(request, 200, lenient=True)
    if not on():
        print("dungeon: dingbild | abgelehnt | aus", flush=True)
        raise HTTPException(409, "aus")
    if not start("alle" if b.get("alle") is True else "knopf"):
        print("dungeon: dingbild | abgelehnt | laeuft", flush=True)
    return await asyncio.to_thread(status)


@router.delete("/api/admin/dungeon/dingbilder", dependencies=[Depends(auth)])
async def admin_stop():
    """„Anhalten“: the run ends after the picture on its way."""
    if not stop():
        print("dungeon: dingbild | anhalten | kein lauf", flush=True)
    return await asyncio.to_thread(status)
