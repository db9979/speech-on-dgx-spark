"""KI-Dungeon-Master: Musik, Geräusche, Würfel (plan dungeon-master/plan.md „5f Bauplan“, Dominik 2026-10-23
„deutlich mehr Stücke, im Hintergrund vorrendern, wenn man weiß, welcher Akt kommt“ and „1a, 2a, 3a, 4a“).

A store of music for the whole Spark, one field per world and mood (STIMMUNGEN), made by the own music model
(musik.make over the heavy jobs' one place, schwer.run("musik"), the voice first, vorrang.quiet):
- variety: the admin's number of pieces per field (Standard ZIEL, 1a), each with its own seed and a way of playing
  from fixed tables (instruments, tempo, key of the world, SPIELART); the caption is built here from fixed words only,
  never from a player's action, a narration or a story (the model has no field for music);
- the mood is the panel's (mood): a fight, a merchant, the last act of the story, else a word list over the scene
  and the act; the model gets nothing new to fill;
- made ahead (2a): a round on the table asks for the moods of its act and of the next act (BEREIT pieces each), every
  new act adds NEU_JE_AKT new pieces for the act after it, the night fills every field up to the number (and the
  admin's „Musik jetzt vorbereiten“ at once); one piece at a time, only while no other heavy job waits;
- the theme (Dominik 2026-10-24 „mehr mit den Themen zu tun, gerne mit Trommeln und Bässen“): every world and mood
  has its own character and instruments (THEMA), drums and bass with measure, never hectic; the caption is a list of
  tags (genre, instruments, mood, production), tempo, key and time signature go as metadata and what a piece must not
  be as its negative prompt (meta, plan dungeon-musik-tuning V1a, Dominik 2026-10-30 „1-8“); a boss fight has its own
  mood (boss: a foe with the bestiary's boss mark still stands in the panel's fight, V8a), the fight's pieces until
  its field has some; a vault of the map has its own
  mood (gewoelbe), a rest at the campfire too (lager, D&D idea 4, Dominik 2026-10-25 „1-12“); a piece of an older style (STIL_V) plays until its field has new ones and then goes first;
- full: per field marked, then older, then the most played pieces go first, and the store stays within the megabytes;
- „👎 Nervt“ (Dominik 2026-10-24 „als schlecht oder nervig markieren, auch von Spielern, in der Nacht erneuert“): any
  seat of a running round (a profile or a guest) marks the piece playing; one mark is enough, the piece is never played
  again and its field asks for a new one, the night throws the marked pieces away; the admin's list takes a mark back
  until then (each seat marks a piece once, own rate limit dungeonnervt, no name is kept: only the number of marks).

Sounds (3a) and the d20 (4a) are made in the browser (dungeon-ton.js, WebAudio, no files); the panel only names them:
the ambient sound of the place (KLANG, a word list over place and mood), the turn a door was told, the turn of the
last victory (an act told or a level reached, played once as a short „Sieg“ piece).

Off by default: only with the admin's „Musik vorbereiten“ (STATE/dungeon-musik.json „an“) and an installed music
model; without them the table has its sounds and dice and no music. Every seat of the round may fetch a piece (a
profile by its login, a guest by its seat code, dungeon._guest); nothing of the store is personal. The journal gets
fixed words and numbers only („dungeon: musik | …“), Live only counts.

    STATE/dungeon-musik.json          {"an", "stuecke", "mb"}   the admin's settings
    STATE/dungeon-musik/index.json    {"stuecke": [{id, w, st, s, t, b, n, v, nervt?}]}   the store
    STATE/dungeon-musik/<id>.mp3      one piece

    GET    /api/profile/dungeon/{rid}/musik/{sid}   a piece for a seat of the round (MP3)
    POST   /api/dungeon/musik                        {code, s}: the same for a guest's seat
    POST   /api/profile/dungeon/{rid}/musik/{sid}/nervt   „👎 Nervt“ from a seat of the round
    POST   /api/dungeon/musik/nervt                  {code, s}: the same for a guest's seat
    GET    /api/admin/dungeon/musik                  settings, the fields with their counts, Live
    PUT    /api/admin/dungeon/musik                  {an, stuecke, mb}
    POST   /api/admin/dungeon/musik/jetzt            fill every field up to the number now
    DELETE /api/admin/dungeon/musik                  delete every piece
    POST   /api/admin/dungeon/musik/{sid}/zurueck    take the marks of a piece back
"""
import asyncio
import hashlib
import os
import random
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import dungeon_lied
import features
import guard
from common import STATE, DayCounter, read_json, write_json
from core import assistant, auth, json_body, own_profile

router = APIRouter()
SETTINGS = os.path.join(STATE, "dungeon-musik.json")
DIR = os.path.join(STATE, "dungeon-musik")
INDEX = os.path.join(DIR, "index.json")

STIMMUNGEN = ("erkunden", "taverne", "spannung", "kampf", "finale", "sieg", "gewoelbe", "lager", "boss")
NAMEN = {"erkunden": ("Erkunden", "Exploring"), "taverne": ("Taverne", "Tavern"), "spannung": ("Spannung", "Tension"),
         "kampf": ("Kampf", "Fight"), "finale": ("Finale", "Finale"), "sieg": ("Sieg", "Victory"),
         "gewoelbe": ("Gewölbe", "Vault"), "lager": ("Lagerfeuer", "Campfire"), "boss": ("Boss", "Boss")}
ERSATZ = {"boss": "kampf"}  # a mood without a piece yet plays these (plan dungeon-musik-tuning V8a)
ZIEL = 12                  # Dominik 1a: pieces per world and mood
ZIEL_SPANNE = (4, 30)
MB = 2400                  # the store on the whole Spark (about 12 × 9 moods × 5 worlds of 4.5 min at about 1 MB a minute)
MB_JE_MINUTE = 1.0         # an MP3 of the music model (for the admin's hint how much the number needs)
MB_SPANNE = (100, 5000)
BEREIT = 2                 # pieces the moods of the current and the next act get first (2a; long pieces, two last a while)
NEU_JE_AKT = 2             # new pieces every act asks for (2a: no two campaigns sound alike)
LAENGE = (180, 240, 300, 360)     # seconds of a piece, a seed picks one (Dominik 2026-10-25 „mindestens verdreifachen“)
SIEG_S = 30                # a victory is short and plays once
NACHT = (1, 6)             # local hours the night fills the fields
TAKT = 10                  # seconds between two looks at the queue
PAUSE_S = 3600             # after FEHLER_MAX failures in a row the store rests this long
FEHLER_MAX = 3
LISTE = 30                 # pieces of one field a seat gets to choose from
ID = re.compile(r"m[0-9a-f]{10}")
GRUENDE = ("memory", "belegt", "missing", "engine", "dienst", "zeit", "pause")   # musik.make's reasons (journal)

# the sound of a world (the admin's own worlds take EIGEN) and of its moods: fixed English words for the music model.
# Dominik 2026-10-24 "mehr mit den Themen zu tun ... auch gerne mit Trommeln und Bässen" (after 2026-10-23 "nichts
# nervig und zu schnell"): every world and mood has its own instruments and character, drums and bass with measure,
# steady and never hectic (TEMPO at most 110 bpm, a fight included). Plan dungeon-musik-tuning V1a (Dominik 2026-10-30
# „1-8“): the caption is a list of tags as ACE-Step 1.5 was trained on (genre, instruments, mood, production), never a
# sentence and never a negation; tempo, key and time signature go as the song's metadata (meta), so the planner of
# the engine keeps the caption word for word, and what a piece must not be goes as its negative prompt (NEGATIV).
STIL_V = 5                 # the style of the pieces: an older one plays until its field has new ones, then goes first
STIL = {"fantasy": "medieval fantasy, celtic folk, cinematic", "horror": "dark ambient, gothic horror, cinematic",
        "scifi": "science fiction, synthwave, cinematic", "piraten": "pirate adventure, sea shanty folk, cinematic"}
EIGEN = "cinematic adventure, orchestral"
# (world, mood) -> (the mood's tags, the ways of playing: one is picked per piece); EIGEN_THEMA for the admin's own worlds
THEMA = {
    "fantasy": {
        "erkunden": ("wonder, adventurous, pastoral, open", ("harp, flute, soft frame drum, warm bass",
                     "lute, strings, hand drum, round bass", "celtic whistle, bodhran drum, cello, bass")),
        "taverne": ("lively, cheerful, folk dance, rustic", ("lute, fiddle, frame drum, upright bass",
                    "hurdy-gurdy, bodhran drum, plucked bass", "recorder, tambourine, mandolin, bass")),
        "spannung": ("mysterious, dark, suspenseful, creeping", ("low strings, deep bass drone, soft timpani",
                     "cello, distant war drum, bass pulse", "dark choir pads, low frame drum, bass")),
        "kampf": ("heroic, driving, intense, battle", ("war drums, deep bass, low brass, strings",
                  "taiko, timpani, horns, driving bass", "frame drums, staccato cellos, deep bass")),
        "finale": ("epic, triumphant, grand, climactic", ("choir, war drums, timpani, deep bass",
                   "full orchestra, big drums, brass, deep bass")),
        "sieg": ("victorious, joyful, festive, warm", ("horns, strings, festive drums, bass", "lute, fiddle, drums, bass")),
        "gewoelbe": ("dark, cavernous, echoing, ancient", ("low drums with echo, deep bass drone, dulcimer",
                     "frame drum, cello, bass", "distant taiko, harp, dark bass")),
        "lager": ("calm, warm, peaceful, starry night", ("acoustic guitar, soft flute, gentle hand drum, warm bass",
                  "lute, harp, brushed frame drum, upright bass")),
        "boss": ("epic, menacing, powerful, dramatic", ("low choir, war drums, low brass, deep bass",
                 "taiko, timpani, horns, string ostinato, deep bass", "dark choir, frame drums, cellos, deep bass")),
    },
    "horror": {
        "erkunden": ("eerie, melancholic, misty, lonely", ("music box, low piano, soft drum, bass drone",
                     "cello, soft heartbeat drum, deep bass", "organ pads, bells, slow tom drums, sub bass")),
        "taverne": ("gloomy, uneasy, whispering, old", ("detuned piano, accordion, brushed drums, upright bass",
                    "creaking fiddle, frame drum, bass")),
        "spannung": ("suspenseful, haunted, ominous, creeping", ("heartbeat bass drum, low strings, drones",
                     "deep sub bass, ticking percussion, dissonant strings", "low taiko, glass harmonica, bass")),
        "kampf": ("dark, aggressive, intense, battle", ("pounding low drums, distorted bass, harsh strings",
                  "taiko, organ stabs, deep bass", "metal percussion, cellos, heavy bass")),
        "finale": ("apocalyptic, ritual, epic, dark", ("pipe organ, choir, huge drums, sub bass",
                   "dark orchestra, timpani, deep bass")),
        "sieg": ("relief, dawn, hopeful, tender", ("strings, soft bells, soft drums, warm bass", "piano, cello, soft drums, bass")),
        "gewoelbe": ("cavernous, dread, echoing, cold", ("low drums with long echo, deep drones, bass",
                     "dripping percussion, cello, sub bass")),
        "lager": ("quiet, fragile, uneasy calm, night", ("acoustic guitar, music box, soft drum, warm bass",
                  "cello, soft piano, gentle hand drum, bass")),
        "boss": ("menacing, sinister, dread, powerful", ("pipe organ, low choir, pounding drums, sub bass",
                 "taiko, dissonant strings, low brass, deep bass")),
    },
    "scifi": {
        "erkunden": ("floating, wonder, spacious, calm", ("warm synth pads, soft electronic drums, analog bass",
                     "arpeggiated synth, light percussion, deep bass", "glassy bells, soft electronic drums, synth bass")),
        "taverne": ("groovy, laid-back, neon lounge, cool", ("synth groove, electronic drums, funky bass",
                    "lounge keys, brushed drums, synth bass")),
        "spannung": ("dark, tense, mechanical, suspenseful", ("deep synth bass, low pulses, metallic percussion",
                     "drones, ticking electronic drums, sub bass")),
        "kampf": ("driving, intense, futuristic, battle", ("hybrid orchestra, electronic drums, heavy synth bass",
                  "taiko, synth bass, brass", "pounding electronic drums, strings, deep bass")),
        "finale": ("epic, massive, climactic, futuristic", ("hybrid orchestra, choir, huge drums, sub bass",
                   "synth arpeggios, big drums, deep bass")),
        "sieg": ("triumphant, bright, celebratory, warm", ("bright synths, drums, warm bass", "strings, pads, soft drums, bass")),
        "gewoelbe": ("alien, ancient, echoing, mysterious", ("low electronic drums with echo, deep drones, bass",
                     "metallic percussion, pads, sub bass")),
        "lager": ("calm, dreamy, peaceful, night sky", ("warm synth pads, soft electronic drums, round bass",
                  "soft keys, light percussion, warm synth bass")),
        "boss": ("menacing, massive, powerful, dark", ("hybrid orchestra, choir, electronic drums, heavy synth bass",
                 "taiko, brass, synth arpeggios, deep bass")),
    },
    "piraten": {
        "erkunden": ("adventurous, breezy, free, open sea", ("accordion, fiddle, hand drum, upright bass",
                     "guitar, tin whistle, frame drum, bass", "concertina, strings, soft drums, bass")),
        "taverne": ("rowdy, cheerful, stomping, jolly", ("accordion, fiddle, stomping drums, bass",
                    "concertina, banjo, barrel drum, upright bass")),
        "spannung": ("foggy, suspenseful, dark, creeping", ("low strings, deep bass, distant drum",
                     "creaking cello, ocean drum, bass drone")),
        "kampf": ("swashbuckling, driving, intense, battle", ("barrel drums, war drums, brass, deep bass",
                  "taiko, fiddle, horns, driving bass", "stomping drums, staccato strings, bass")),
        "finale": ("epic, stormy, heroic, climactic", ("full orchestra, huge drums, choir, deep bass",
                   "brass, timpani, fiddle, bass")),
        "sieg": ("joyful, festive, triumphant, cheering", ("accordion, fiddle, drums, bass", "horns, strings, festive drums, bass")),
        "gewoelbe": ("mysterious, cavernous, dripping, echoing", ("low drums with echo, ocean drum, deep bass",
                     "cello, steel drum, bass drone")),
        "lager": ("calm, warm, gentle waves, night", ("acoustic guitar, concertina, soft hand drum, upright bass",
                  "fiddle, guitar, gentle frame drum, bass")),
        "boss": ("menacing, stormy, powerful, dramatic", ("full orchestra, war drums, low choir, deep bass",
                 "brass, timpani, fiddle, driving bass")),
    },
}
EIGEN_THEMA = {
    "erkunden": ("adventurous, wide, open", ("strings, flute, hand drum, bass", "guitar, pads, soft drums, bass")),
    "taverne": ("lively, cheerful, folk dance", ("fiddle, guitar, frame drum, upright bass",)),
    "spannung": ("suspenseful, dark, creeping", ("low strings, deep bass, distant drums",)),
    "kampf": ("heroic, driving, battle", ("war drums, brass, strings, deep bass", "taiko, staccato cellos, bass")),
    "finale": ("epic, grand, climactic", ("full orchestra, choir, huge drums, deep bass",)),
    "sieg": ("victorious, festive, warm", ("horns, strings, festive drums, bass",)),
    "gewoelbe": ("dark, cavernous, echoing", ("low drums with echo, deep drones, bass",)),
    "lager": ("calm, warm, peaceful", ("acoustic guitar, flute, gentle hand drum, warm bass",)),
    "boss": ("epic, menacing, powerful", ("low choir, war drums, brass, deep bass",)),
}
# one tempo and time signature per mood and one key per world (minor, the tavern, the victory and the camp in its
# relative major, the boss in the minor key a fifth up): two pieces of a field share them, so the crossfade between
# them is smooth (Dominik 2026-10-25 „smoother Übergang … eventuell gleiche Chord-Progression“); tempo at most 110 bpm,
# a fight included. The key as acestep.cpp's planner names it („D minor“, „Eb major“: musik_server.KEYSCALE).
TEMPO = {"erkunden": 75, "taverne": 96, "spannung": 72, "kampf": 100, "finale": 92, "sieg": 96, "gewoelbe": 66,
         "lager": 70, "boss": 104}
TAKT = {"taverne": "6", "lager": "3"}      # else 4/4 (musik_server.TIMESIG)
TONART = {"fantasy": ("D minor", "F major", "A minor"), "horror": ("C minor", "Eb major", "G minor"),
          "scifi": ("A minor", "C major", "E minor"), "piraten": ("E minor", "G major", "B minor")}
TONART_EIGEN = ("D minor", "F major", "A minor")
DUR = ("taverne", "sieg", "lager")
PRODUKTION = ("instrumental, tabletop role-playing game background music, steady groove, soft fade-in, "
              "long gentle fade-out, seamless loop, warm balanced mix")
# what a piece must not be: the planner's negative prompt (lm_negative_prompt), never words in the caption
NEGATIV = "vocals, singing, spoken words, hectic, frantic, chaotic, abrupt changes, sudden stops"

# the panel's word lists over the scene, the act and the place (the model's words are data: they only pick one of these)
_W = lambda s: re.compile(r"(?i)\b(" + s + r")")   # noqa: E731 - a word at its start (German compounds end freely)
KAMPF = _W(r"kampf|kämpf|gefecht|schlacht|angriff|angreif|überfall|duell|battle|fight|combat|attack|ambush|duel")
TAVERNE = _W(r"tavern|taverne|gasthaus|gasthof|wirtshaus|schenke|markt|basar|dorf|stadt|hafen|fest|feier|inn\b|market|"
             r"bazaar|village|town|city|harbou?r|feast")
SPANNUNG = _W(r"gefahr|gefährlich|unheimlich|bedrohlich|düster|dunkel|finster|angst|furcht|spannung|angespannt|lauer|"
              r"schleich|verfolg|flucht|nebel|grusel|danger|eerie|ominous|grim|dark|fear|tense|lurk|sneak|chase|escape|fog|creep")
KLAENGE = (("regen", _W(r"regen|sturm|gewitter|donner|rain|storm|thunder")),
           ("feuer", _W(r"feuer|kamin|lagerfeuer|fackel|schmiede|lava|glut|fire|hearth|campfire|torch|forge|ember")),
           ("wasser", _W(r"fluss|see\b|meer|ozean|küste|strand|schiff|kanal|quelle|höhle|brunnen|river|lake|sea\b|ocean|coast|"
                         r"beach|ship|sewer|spring|cave|well\b")),
           ("wind", _W(r"wind|klippe|gipfel|berg|wüste|eis|schnee|turm|ebene|cliff|peak|mountain|desert|ice|snow|tower|plain")))
TUER = _W(r"tür|tor\b|pforte|falltür|door|gate|hatch")
KLANG_WELT = {"piraten": "wasser", "horror": "wind"}   # the place says nothing: the world's own

_lock = threading.Lock()
_cache = {"mtime": None, "d": None}
_want = {}                 # (welt, st) -> {"upto": n, "extra": n}   the queue, in the order asked
_akte = {}                 # rid -> the act seen last (a new act asks for new pieces)
_plays = {}                # id -> plays since the index was written last
_state = {"run": None, "fehler": 0, "ruhe": 0.0, "nacht": ""}
_day = DayCounter(gemacht=0, weg=0, geholt=0, entfernt=0, nervt=0)
_gemerkt = {}              # id -> hashes of the seats that marked it (in memory: a seat marks a piece once)
NERVT_MAX = 99             # marks kept per piece


# ---------------------------------------------------------------- settings
def settings():
    s = read_json(SETTINGS, {})
    s = s if isinstance(s, dict) else {}
    return {"an": s.get("an") is True, "stuecke": _int(s.get("stuecke"), *ZIEL_SPANNE, ZIEL), "mb": _int(s.get("mb"), *MB_SPANNE, MB)}


def _int(x, lo, hi, default):
    return x if isinstance(x, int) and not isinstance(x, bool) and lo <= x <= hi else default


def installed():
    import musik
    return bool(musik.cfg().get("enabled"))


def on(s=None):
    """Music only with the game, the admin's „Musik vorbereiten“ and the music model installed."""
    return features.admin_on("dungeon") and (s or settings())["an"] and installed()


# ---------------------------------------------------------------- the store
def _read():
    try:
        m = os.path.getmtime(INDEX)
    except OSError:
        return {"stuecke": []}
    if _cache["mtime"] != m:
        d = read_json(INDEX, {})
        d = d if isinstance(d, dict) else {}
        d["stuecke"] = [x for x in d.get("stuecke") or [] if isinstance(x, dict) and ID.fullmatch(str(x.get("id")))]
        _cache.update(mtime=m, d=d)
    return _cache["d"]


def _write(d):
    for x in d["stuecke"]:
        x["n"] = x.get("n", 0) + _plays.pop(x["id"], 0)
    os.makedirs(DIR, mode=0o700, exist_ok=True)
    write_json(INDEX, d, None, 0o600, False, 0o700)
    _cache.update(mtime=None, d=None)


def file_of(sid):
    return os.path.join(DIR, sid + ".mp3")


def _rm(sid):
    try:
        os.remove(file_of(sid))
    except FileNotFoundError:
        pass


def spielbar(x):
    """A piece the table plays: not marked „Nervt“ (a marked one waits for the night or the admin's „Zurücknehmen“)."""
    return not x.get("nervt")


def neu(x):
    """A piece of the current style (STIL_V); an older one plays until its field has new ones and goes first."""
    return x.get("v") == STIL_V


def count(d, welt, st):
    """The playable pieces of the current style of a field (a marked or older one does not count: its field asks for a
    new piece)."""
    return sum(1 for x in d["stuecke"] if x["w"] == welt and x["st"] == st and spielbar(x) and neu(x))


def prune(d, ziel, mb, keep=""):
    """Inside the lock: each field at most ziel pieces and the store within mb; the most played go first (then the
    oldest), never keep (the piece just made). Returns the ids taken out."""
    plays = lambda x: (spielbar(x), neu(x), -(x.get("n", 0) + _plays.get(x["id"], 0)), x.get("t", 0))   # noqa: E731 - marked, older first
    out = []
    fields = {}
    for x in d["stuecke"]:
        fields.setdefault((x["w"], x["st"]), []).append(x)
    for xs in fields.values():
        for x in sorted((x for x in xs if x["id"] != keep), key=plays)[:max(0, len(xs) - ziel)]:
            out.append(x["id"])
    left = [x for x in d["stuecke"] if x["id"] not in out]
    while sum(x.get("b", 0) for x in left) > mb * 1024 * 1024:
        sizes = {}
        for x in left:
            if x["id"] != keep:
                sizes.setdefault((x["w"], x["st"]), []).append(x)
        if not sizes:
            break
        x = sorted(max(sizes.values(), key=len), key=plays)[0]
        out.append(x["id"])
        left.remove(x)
    d["stuecke"] = left
    for sid in out:
        _rm(sid)
        _plays.pop(sid, None)
    return out


def caption(welt, st, rng):
    """The words for the music model: only fixed words of this module (never a text of the game), as tags: genre,
    instruments, mood, production."""
    art, wie = THEMA.get(welt, EIGEN_THEMA)[st]
    return ", ".join((STIL.get(welt, EIGEN), rng.choice(wie), art, PRODUKTION))


def meta(welt, st):
    """The piece's metadata for the engine (musik_server.metadata): tempo, key and time signature of the field and
    the negative prompt; with all of them the engine's planner keeps the caption as it is."""
    tonart = TONART.get(welt, TONART_EIGEN)
    return {"bpm": TEMPO[st], "keyscale": tonart[1 if st in DUR else 2 if st == "boss" else 0],
            "timesignature": TAKT.get(st, "4"), "negative": NEGATIV}


# ---------------------------------------------------------------- the mood (panel rules)
def act_mood(plan, i):
    """The mood of act i of a story: the last act is the finale, else the act's words, else exploring at the start
    and tension after."""
    if not plan or i >= len(plan.get("akte") or []):
        return ""
    if i == len(plan["akte"]) - 1:
        return "finale"
    a = plan["akte"][i]
    text = " ".join(str(a.get(k) or "") for k in ("titel", "inhalt", "wende"))
    if KAMPF.search(text):
        return "kampf"
    if TAVERNE.search(text):
        return "taverne"
    return "spannung" if i or SPANNUNG.search(text) else "erkunden"


def _im_gewoelbe(rd):
    """The group stands in a vault of the map (dungeon_karte.vault, 5d)."""
    if not rd.get("karte"):
        return False
    try:
        import dungeon_karte
        return bool(dungeon_karte.vault(rd))
    except Exception:   # noqa: BLE001 - the mood never fails for the map
        return False


def boss(rd):
    """A boss fight (plan dungeon-musik-tuning V8a): the panel's fight (dungeon_kampf, rd["kampf"]) has a foe still
    standing whose bestiary entry carries the boss mark; never the model's words."""
    k = rd.get("kampf")
    return isinstance(k, dict) and any(isinstance(g, dict) and g.get("boss") is True and not g.get("aus")
                                       for g in k.get("gegner") or [])


def mood(rd):
    """The round's mood now: a boss fight > a fight (5b's kampf or the scene's words) > a rest at the campfire > in a
    vault > a merchant or a settlement > the finale > tension in the scene's words > the act's mood > exploring."""
    sz = rd.get("szene") or {}
    text = f"{sz.get('ort') or ''} {sz.get('stimmung') or ''}"
    if boss(rd):
        return "boss"
    if rd.get("kampf") or KAMPF.search(text):
        return "kampf"
    if rd.get("rast"):                         # resting at the campfire (D&D idea 4, the main thread sets rd["rast"])
        return "lager"
    if _im_gewoelbe(rd):
        return "gewoelbe"
    if rd.get("markt") or TAVERNE.search(text):
        return "taverne"
    m = act_mood(rd.get("plan"), rd.get("akt", 0))
    if m == "finale":
        return m
    if SPANNUNG.search(text):
        return "spannung"
    return m if m in ("spannung", "erkunden") else "erkunden"


def klang(rd):
    """The ambient sound of the place: a word list over place and mood, else the world's own, else none."""
    if rd.get("rast"):                         # the campfire crackles while the group rests
        return "feuer"
    sz = rd.get("szene") or {}
    text = f"{sz.get('ort') or ''} {sz.get('stimmung') or ''}"
    for k, words in KLAENGE:
        if words.search(text):
            return k
    return KLANG_WELT.get(rd.get("welt"), "")


def _last(rd, arts, test=None):
    for e in reversed(rd.get("log") or []):
        if e.get("art") in arts and (test is None or test(e)):
            return e.get("n", 0)
    return -1


# ---------------------------------------------------------------- what a round asks for (dungeon.view)
def want(welt, st, upto=0, extra=0):
    if st not in STIMMUNGEN or not welt:
        return
    with _lock:
        w = _want.setdefault((welt, st), {"upto": 0, "extra": 0})
        w["upto"] = max(w["upto"], upto)
        w["extra"] = min(w["extra"] + extra, ZIEL_SPANNE[1])


def ask_round(rid, rd, s=None):
    """The current mood, the moods of this act and the next one (BEREIT each, the fight, the boss and the victory too) and, on
    a new act, NEU_JE_AKT new pieces for the act after it."""
    s = s or settings()
    welt, plan, i = rd.get("welt"), rd.get("plan"), rd.get("akt", 0)
    now_m = mood(rd)
    nxt = act_mood(plan, i + 1)
    for m in (now_m, act_mood(plan, i), nxt, "kampf", "boss", "sieg", "gewoelbe" if rd.get("karte") else "", "lager" if rd.get("rast") else ""):
        if m:
            want(welt, m, min(BEREIT, s["stuecke"]))
    seen = _akte.get(rid)
    _akte[rid] = i
    if seen is not None and i > seen and nxt:
        want(welt, nxt, extra=NEU_JE_AKT)
    return now_m


def for_view(rid, rd, lang="de"):
    """The table's field „musik“ (dungeon.view): the mood and its pieces (only with music on), the victory pieces,
    the turn of the last victory and door, the ambient sound. Never raises: the table works without."""
    li = 1 if lang == "en" else 0
    out = {"an": False, "klang": "", "sieg_zug": -1, "tuer_zug": -1}
    try:
        out.update(klang=klang(rd), sieg_zug=_last(rd, ("akt", "stufe")),
                   tuer_zug=_last(rd, ("dm",), lambda e: bool(TUER.search(str(e.get("text") or "")))))
        s = settings()
        if not on(s) or rd.get("status") != "laeuft":
            return out
        st = ask_round(rid, rd, s)
        d = _read()
        def pick(m):   # the current style once its field has one, until then the older pieces
            xs = [x for x in sorted(d["stuecke"], key=lambda x: -x.get("t", 0)) if x["w"] == rd.get("welt") and x["st"] == m and spielbar(x)]
            return [x["id"] for x in ([x for x in xs if neu(x)] or xs)][:LISTE]
        xs = pick(st)
        if not xs and st in ERSATZ:   # a boss without its own pieces yet: the fight's (the table plays on as a fight)
            st = ERSATZ[st]
            xs = pick(st)
        out.update(an=True, st=st, name=NAMEN[st][li], stuecke=xs, sieg=pick("sieg"), ziel=s["stuecke"])
        out.update(dungeon_lied.ask_round(rid, rd))   # the bard's song of each chapter (lieder, lied: the newest)
    except Exception as e:   # noqa: BLE001 - the table never fails for its music
        print("dungeon: musik | ansicht fehler", type(e).__name__, flush=True)
    return out


# ---------------------------------------------------------------- making a piece (one at a time, after everybody else)
def night(now):
    h = time.localtime(now).tm_hour
    return NACHT[0] <= h < NACHT[1]


def fill_all(s=None, welten=None):
    """Every field of every world up to the admin's number (the night and „Musik jetzt vorbereiten“)."""
    s = s or settings()
    if welten is None:
        import dungeon
        welten = [w["id"] for w in dungeon.rules()["welten"]]
    for w in welten:
        for st in STIMMUNGEN:
            want(w, st, s["stuecke"])
    return len(welten) * len(STIMMUNGEN)


def next_job(s):
    """The first field asked for that still needs a piece: (welt, st) or None; fields that have enough leave the
    queue."""
    d = _read()
    with _lock:
        for k in list(_want):
            w = _want[k]
            if w["extra"] > 0 or count(d, *k) < min(w["upto"], s["stuecke"]):
                return k
            _want.pop(k)
    return None


async def render(body, jid):
    """One piece from the music model on the heavy jobs' place, the voice first (vorrang.quiet, wartung „musik“):
    the MP3, or ValueError(why) / asyncio.TimeoutError. Also the bard's songs (dungeon_lied.py)."""
    import musik
    import schwer
    import vorrang
    import wartung
    await vorrang.quiet("Musik machen")

    async def once():
        await vorrang.quiet("Musik machen")
        if wartung.paused("musik"):
            raise ValueError("pause")
        return await musik.make(body)
    mp3, _d = await asyncio.wait_for(schwer.run("musik", jid, time.time(), once), musik.JOB_SECONDS + schwer.WAIT_S)
    return mp3


async def make(welt, st, rng=None):
    """One piece of this field on the heavy jobs' place, the voice first; kept and the store pruned. Returns "ok" or
    why not (GRUENDE). Never raises."""
    import musik
    rng = rng or random.Random(secrets.randbits(32))
    secs = SIEG_S if st == "sieg" else rng.choice(LAENGE)
    body = {"caption": caption(welt, st, rng), "seconds": secs, "lyrics": "", "language": "", "seed": rng.randrange(2 ** 31),
            "title": f"Dungeon {st}", **meta(welt, st)}
    if musik.model():
        body["variant"] = musik.model()
    jid = secrets.token_hex(6)
    _state["run"] = jid
    t0 = time.perf_counter()
    why = "ok"
    try:
        mp3 = await render(body, jid)
        sid = "m" + secrets.token_hex(5)

        def keep():
            s = settings()
            with _lock:
                os.makedirs(DIR, mode=0o700, exist_ok=True)
                with open(file_of(sid) + ".neu", "wb") as f:
                    f.write(mp3)
                os.chmod(file_of(sid) + ".neu", 0o600)
                os.replace(file_of(sid) + ".neu", file_of(sid))
                d = _read()
                d = {"stuecke": list(d["stuecke"]) + [{"id": sid, "w": welt, "st": st, "s": secs, "t": int(time.time()),
                                                       "b": len(mp3), "n": 0, "v": STIL_V}]}
                gone = prune(d, s["stuecke"], s["mb"], keep=sid)   # a new act's pieces push out the most played
                _write(d)
                w = _want.get((welt, st))
                if w and w["extra"] > 0:
                    w["extra"] -= 1
                return len(gone)
        gone = await asyncio.to_thread(keep)
        if gone:
            _day.bump("entfernt", gone)
        _day.bump("gemacht")
        _state["fehler"] = 0
    except asyncio.TimeoutError:
        why = "zeit"
    except ValueError as e:
        why = str(e) if str(e) in GRUENDE else "dienst"
    except Exception:   # noqa: BLE001 - every piece ends with a journal line
        why = "dienst"
    finally:
        _state["run"] = None
    if why != "ok":
        _day.bump("weg")
        _state["fehler"] += 1
        if _state["fehler"] >= FEHLER_MAX:
            _state.update(ruhe=time.time() + PAUSE_S, fehler=0)
            print(f"dungeon: musik | ruhe | {FEHLER_MAX} fehler | {PAUSE_S // 60} min", flush=True)
    print(f"dungeon: musik | {why} | {st} | {secs} s | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)
    return why


async def step(now=None):
    """One look: the night fills the fields, then one piece when no other heavy job waits. Returns what it did."""
    import notaus
    import schwer
    now = time.time() if now is None else now
    s = settings()
    if not on(s):
        with _lock:
            _want.clear()
        return "aus"
    day = DayCounter.date()
    if night(now) and _state["nacht"] != day and not notaus.blocks("auto"):
        _state["nacht"] = day
        await asyncio.to_thread(markierte_weg)
        print(f"dungeon: musik | nacht | {fill_all(s)} felder | {await asyncio.to_thread(_lieder_weg)} lieder weg", flush=True)
    if _state["run"] or dungeon_lied._state["run"] or now < _state["ruhe"]:
        return "ruht"
    if dungeon_lied.pending():   # a chapter's song goes before the store's pieces (dungeon_lied.py)
        return "wartet" if schwer.offen() else await dungeon_lied.make_next()
    job = next_job(s)
    if not job:
        return "nichts"
    if schwer.offen():
        return "wartet"
    return await make(*job)


def _lieder_weg():
    """The night: the songs of rounds that are gone (dungeon_lied.tidy)."""
    import dungeon
    return dungeon_lied.tidy(set(dungeon._read()["runden"]))


async def loop():
    while True:
        try:
            await step()
        except Exception as e:   # noqa: BLE001 - the loop goes on
            print("dungeon: musik | fehler", type(e).__name__, flush=True)
        await asyncio.sleep(TAKT)


def nervt(sid, seat):
    """„👎 Nervt“ from a seat (rid:pid or rid:uid, only its hash is kept in memory): the piece is never played again,
    its field asks for a new one. Returns the piece's world and mood, or raises LookupError."""
    if not isinstance(sid, str) or not ID.fullmatch(sid):
        print("dungeon: musik | nervt abgelehnt | unbekannt", flush=True)
        raise LookupError("stueck")
    h = hashlib.sha256(seat.encode()).hexdigest()[:16]
    with _lock:
        d = _read()
        x = next((x for x in d["stuecke"] if x["id"] == sid), None)
        if not x:
            print("dungeon: musik | nervt abgelehnt | unbekannt", flush=True)
            raise LookupError("stueck")
        seen = _gemerkt.setdefault(sid, set())
        if h in seen:
            print(f"dungeon: musik | nervt schon | {x['st']}", flush=True)
            return x["w"], x["st"], False
        seen.add(h)
        d = {"stuecke": [dict(y, nervt=min(NERVT_MAX, y.get("nervt", 0) + 1)) if y["id"] == sid else y for y in d["stuecke"]]}
        _write(d)
    _day.bump("nervt")
    print(f"dungeon: musik | nervt | {x['st']}", flush=True)
    return x["w"], x["st"], True


def zurueck(sid):
    """The admin takes the marks of a piece back: it plays again. Returns whether it was marked."""
    if not isinstance(sid, str) or not ID.fullmatch(sid):
        raise LookupError("stueck")
    with _lock:
        d = _read()
        x = next((x for x in d["stuecke"] if x["id"] == sid), None)
        if not x:
            raise LookupError("stueck")
        if spielbar(x):
            print("dungeon: musik | zurueck | nicht markiert", flush=True)
            return False
        _write({"stuecke": [{k: v for k, v in y.items() if k != "nervt"} if y["id"] == sid else y for y in d["stuecke"]]})
        _gemerkt.pop(sid, None)
    print(f"dungeon: musik | zurueck | {x['st']}", flush=True)
    return True


def markierte_weg():
    """The night: every marked piece out with its file (their fields are made again). Returns how many."""
    with _lock:
        d = _read()
        weg = [x["id"] for x in d["stuecke"] if not spielbar(x)]
        if not weg:
            return 0
        for sid in weg:
            _rm(sid)
            _gemerkt.pop(sid, None)
            _plays.pop(sid, None)
        _write({"stuecke": [x for x in d["stuecke"] if spielbar(x)]})
    _day.bump("entfernt", len(weg))
    print(f"dungeon: musik | nervt weg | {len(weg)} stuecke", flush=True)
    return len(weg)


def clear():
    """Every piece out (the admin's „Vorrat löschen“). Returns how many."""
    with _lock:
        d = _read()
        for x in d["stuecke"]:
            _rm(x["id"])
        n = len(d["stuecke"])
        _write({"stuecke": []})
        _want.clear()
    print(f"dungeon: musik | geloescht | {n}", flush=True)
    return n


def piece(sid, probe=False):
    """The MP3 of a piece of the store (any seat of a running round may hear any piece: nothing of it is personal).
    probe: the admin listens before deciding on a mark (Dominik 2026-10-25), a marked piece too, not counted as played."""
    if not isinstance(sid, str) or not ID.fullmatch(sid) or not any(x["id"] == sid and (probe or spielbar(x)) for x in _read()["stuecke"]):
        raise LookupError("stueck")
    with open(file_of(sid), "rb") as f:
        mp3 = f.read()
    if not probe:
        _plays[sid] = _plays.get(sid, 0) + 1
        _day.bump("geholt")
    return mp3


def for_live():
    """Numbers only: pieces, full fields, making or waiting, made/failed/fetched/pruned today."""
    s = settings()
    d = _read()
    t = _day.counts()
    fields = {(x["w"], x["st"]) for x in d["stuecke"]}
    return {"an": on(s), "stuecke": sum(1 for x in d["stuecke"] if spielbar(x)), "alt": sum(1 for x in d["stuecke"] if not neu(x)), "mb": round(sum(x.get("b", 0) for x in d["stuecke"]) / 1024 / 1024),
            "voll": sum(1 for k in fields if count(d, *k) >= s["stuecke"]), "macht": bool(_state["run"]),
            "wartet": len(_want), "gemacht": t["gemacht"], "weg": t["weg"], "geholt": t["geholt"], "entfernt": t["entfernt"],
            "markiert": sum(1 for x in d["stuecke"] if not spielbar(x)), "nervt": t["nervt"]}


# ---------------------------------------------------------------- routes
def _mp3(b):
    return Response(b, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


def _seat_ok(rid, pid):
    import dungeon
    rd = dungeon._round(dungeon._read(), rid)
    if pid not in rd["plaetze"] or rd["status"] != "laeuft":
        raise LookupError("runde")


@router.get("/api/profile/dungeon/{rid}/musik/{sid}", dependencies=[Depends(assistant)])
async def stueck(rid: str, sid: str, request: Request, prof=Depends(own_profile)):
    """A piece of the store for a seat of a running round."""
    import dungeon
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeonmusik", uid)
    try:
        def go():
            _seat_ok(rid, dungeon._seat_uid(rid, uid))
            return dungeon_lied.piece(rid, sid) if dungeon_lied.ID.fullmatch(sid) else piece(sid)   # a song only of its round
        return _mp3(await asyncio.to_thread(go))
    except dungeon.KNOWN as e:
        raise dungeon._http(e)


@router.post("/api/dungeon/musik")
async def gast_stueck(request: Request):
    """{"code", "s"}: a piece of the store for a guest's seat (the seat link's door, dungeon._guest)."""
    import dungeon
    b, rid, pid = await dungeon._guest(request)
    guard.limit(request, "dungeonmusik")
    try:
        def go():
            _seat_ok(rid, pid)
            sid = b.get("s")
            return dungeon_lied.piece(rid, sid) if isinstance(sid, str) and dungeon_lied.ID.fullmatch(sid) else piece(sid)
        return _mp3(await asyncio.to_thread(go))
    except dungeon.KNOWN as e:
        raise dungeon._http(e)


@router.post("/api/profile/dungeon/{rid}/musik/{sid}/nervt", dependencies=[Depends(assistant)])
async def stueck_nervt(rid: str, sid: str, request: Request, prof=Depends(own_profile)):
    """„👎 Nervt“ from a profile's seat of a running round."""
    import dungeon
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeonnervt", uid)
    try:
        def go():
            pid = dungeon._seat_uid(rid, uid)
            _seat_ok(rid, pid)
            return nervt(sid, f"{rid}:{pid}")
        _w, _st, neu = await asyncio.to_thread(go)
        return {"ok": True, "neu": neu}
    except dungeon.KNOWN as e:
        raise dungeon._http(e)


@router.post("/api/dungeon/musik/nervt")
async def gast_nervt(request: Request):
    """{"code", "s"}: „👎 Nervt“ from a guest's seat (the seat link's door, dungeon._guest)."""
    import dungeon
    b, rid, pid = await dungeon._guest(request)
    guard.limit(request, "dungeonnervt")
    try:
        def go():
            _seat_ok(rid, pid)
            return nervt(b.get("s"), f"{rid}:{pid}")
        _w, _st, neu = await asyncio.to_thread(go)
        return {"ok": True, "neu": neu}
    except dungeon.KNOWN as e:
        raise dungeon._http(e)


def _short(d, s, welt, st):
    """The field is asked for and still short of pieces (the admin's table shows ⏳)."""
    w = _want.get((welt, st))
    return bool(w) and (w["extra"] > 0 or count(d, welt, st) < min(w["upto"], s["stuecke"]))


def admin_view(lang="de"):
    import dungeon
    li = 1 if lang == "en" else 0
    s = settings()
    d = _read()
    r = dungeon.rules()
    return {"einstellung": s, "installiert": installed(), "spanne": {"stuecke": ZIEL_SPANNE, "mb": MB_SPANNE},
            "stimmungen": [{"id": m, "name": NAMEN[m][li]} for m in STIMMUNGEN],
            "felder": [{"welt": w["id"], "name": w["name"][li], "zeichen": w.get("zeichen", ""),
                        "n": {m: count(d, w["id"], m) for m in STIMMUNGEN},
                        "wartet": [m for m in STIMMUNGEN if _short(d, s, w["id"], m)]} for w in r["welten"]],
            "markiert": [{"id": x["id"], "welt": next((w["name"][li] for w in r["welten"] if w["id"] == x["w"]), x["w"]),
                          "st": NAMEN.get(x["st"], ("", ""))[li], "nervt": x["nervt"], "s": x.get("s", 0)}
                         for x in sorted(d["stuecke"], key=lambda x: -x.get("t", 0)) if not spielbar(x)],
            "mb_noetig": round(len(r["welten"]) * len(STIMMUNGEN) * s["stuecke"] * sum(LAENGE) / len(LAENGE) / 60 * MB_JE_MINUTE),
            "live": for_live()}


@router.get("/api/admin/dungeon/musik", dependencies=[Depends(auth)])
def admin_show(request: Request):
    return admin_view("en" if request.query_params.get("lang") == "en" else "de")


@router.put("/api/admin/dungeon/musik", dependencies=[Depends(auth)])
async def admin_save(request: Request):
    """{an, stuecke, mb}: refused unless every value is within its range."""
    guard.limit(request, "dungeonmusik", admin=True)
    b = await json_body(request, 1024)
    an, n, mb = b.get("an"), b.get("stuecke"), b.get("mb")
    if not isinstance(an, bool) or _int(n, *ZIEL_SPANNE, None) is None or _int(mb, *MB_SPANNE, None) is None:
        print("dungeon: musik | einstellung abgelehnt", flush=True)
        raise HTTPException(400, f"an: true/false, stuecke: {ZIEL_SPANNE[0]}-{ZIEL_SPANNE[1]}, mb: {MB_SPANNE[0]}-{MB_SPANNE[1]}")
    await asyncio.to_thread(write_json, SETTINGS, {"an": an, "stuecke": n, "mb": mb}, 2, 0o600, False, 0o700)

    def shrink():
        with _lock:
            d = _read()
            gone = prune(d, n, mb)
            if gone:
                _write(d)
            return len(gone)
    gone = await asyncio.to_thread(shrink)
    if not an:
        with _lock:
            _want.clear()
    print(f"dungeon: musik | einstellung | {'an' if an else 'aus'} | {n} stuecke | {mb} mb | {gone} entfernt", flush=True)
    return admin_view("en" if b.get("lang") == "en" else "de")


@router.post("/api/admin/dungeon/musik/jetzt", dependencies=[Depends(auth)])
async def admin_jetzt(request: Request):
    """„Musik jetzt vorbereiten“: every field up to the number, one piece after the other, the voice first."""
    guard.limit(request, "dungeonmusik", admin=True)
    if not on():
        print("dungeon: musik | jetzt abgelehnt | aus", flush=True)
        raise HTTPException(409, "aus")
    n = await asyncio.to_thread(fill_all)
    print(f"dungeon: musik | jetzt | {n} felder", flush=True)
    return admin_view("en" if request.query_params.get("lang") == "en" else "de")


@router.get("/api/admin/dungeon/musik/{sid}", dependencies=[Depends(auth)])
async def admin_hoeren(sid: str, request: Request):
    """The admin listens to a piece (the marked list: does it really go, or does it stay?)."""
    guard.limit(request, "dungeonmusik", admin=True)
    try:
        mp3 = await asyncio.to_thread(piece, sid, True)
    except (LookupError, OSError):
        print("dungeon: musik | anhoeren abgelehnt | unbekannt", flush=True)
        raise HTTPException(404, "stueck")
    print("dungeon: musik | anhoeren | admin", flush=True)
    return _mp3(mp3)


@router.post("/api/admin/dungeon/musik/{sid}/zurueck", dependencies=[Depends(auth)])
async def admin_zurueck(sid: str, request: Request):
    """Takes the marks of a piece back: it plays again (until the night it waits in the admin's list)."""
    guard.limit(request, "dungeonmusik", admin=True)
    try:
        await asyncio.to_thread(zurueck, sid)
    except LookupError:
        print("dungeon: musik | zurueck abgelehnt | unbekannt", flush=True)
        raise HTTPException(404, "stueck")
    return admin_view("en" if request.query_params.get("lang") == "en" else "de")


@router.delete("/api/admin/dungeon/musik", dependencies=[Depends(auth)])
async def admin_clear(request: Request):
    guard.limit(request, "dungeonmusik", admin=True)
    await asyncio.to_thread(clear)
    return admin_view("en" if request.query_params.get("lang") == "en" else "de")
