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
- full: per field the most played pieces go first, and the whole store stays within the admin's megabytes.

Sounds (3a) and the d20 (4a) are made in the browser (dungeon-ton.js, WebAudio, no files); the panel only names them:
the ambient sound of the place (KLANG, a word list over place and mood), the turn a door was told, the turn of the
last victory (an act told or a level reached, played once as a short „Sieg“ piece).

Off by default: only with the admin's „Musik vorbereiten“ (STATE/dungeon-musik.json „an“) and an installed music
model; without them the table has its sounds and dice and no music. Every seat of the round may fetch a piece (a
profile by its login, a guest by its seat code, dungeon._guest); nothing of the store is personal. The journal gets
fixed words and numbers only („dungeon: musik | …“), Live only counts.

    STATE/dungeon-musik.json          {"an", "stuecke", "mb"}   the admin's settings
    STATE/dungeon-musik/index.json    {"stuecke": [{id, w, st, s, t, b, n}]}   the store
    STATE/dungeon-musik/<id>.mp3      one piece

    GET    /api/profile/dungeon/{rid}/musik/{sid}   a piece for a seat of the round (MP3)
    POST   /api/dungeon/musik                        {code, s}: the same for a guest's seat
    GET    /api/admin/dungeon/musik                  settings, the fields with their counts, Live
    PUT    /api/admin/dungeon/musik                  {an, stuecke, mb}
    POST   /api/admin/dungeon/musik/jetzt            fill every field up to the number now
    DELETE /api/admin/dungeon/musik                  delete every piece
"""
import asyncio
import os
import random
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import features
import guard
from common import STATE, DayCounter, read_json, write_json
from core import assistant, auth, json_body, own_profile

router = APIRouter()
SETTINGS = os.path.join(STATE, "dungeon-musik.json")
DIR = os.path.join(STATE, "dungeon-musik")
INDEX = os.path.join(DIR, "index.json")

STIMMUNGEN = ("erkunden", "taverne", "spannung", "kampf", "finale", "sieg")
NAMEN = {"erkunden": ("Erkunden", "Exploring"), "taverne": ("Taverne", "Tavern"), "spannung": ("Spannung", "Tension"),
         "kampf": ("Kampf", "Fight"), "finale": ("Finale", "Finale"), "sieg": ("Sieg", "Victory")}
ZIEL = 12                  # Dominik 1a: pieces per world and mood
ZIEL_SPANNE = (4, 30)
MB = 600                   # the store on the whole Spark (12 × 6 moods × 5 worlds of about 1.4 MB)
MB_SPANNE = (100, 5000)
BEREIT = 4                 # pieces the moods of the current and the next act get first (2a)
NEU_JE_AKT = 2             # new pieces every act asks for (2a: no two campaigns sound alike)
LAENGE = (60, 75, 90, 105, 120)   # seconds of a piece (a seed picks one)
SIEG_S = 30                # a victory is short and plays once
NACHT = (1, 6)             # local hours the night fills the fields
TAKT = 10                  # seconds between two looks at the queue
PAUSE_S = 3600             # after FEHLER_MAX failures in a row the store rests this long
FEHLER_MAX = 3
LISTE = 30                 # pieces of one field a seat gets to choose from
ID = re.compile(r"m[0-9a-f]{10}")
GRUENDE = ("memory", "belegt", "missing", "engine", "dienst", "zeit", "pause")   # musik.make's reasons (journal)

# the sound of a world (the admin's own worlds take EIGEN) and of a mood: fixed English words for the music model.
# Dominik 2026-10-23 "nichts nervig und zu schnell ... schön ambient music und ruhig": calm ambient in every mood,
# soft pads and drones instead of drums, a fight only as a low steady pulse, 60 to 80 bpm
STIL_V = 2                 # the style of the pieces: a piece of an older style is thrown away and made again
STIL = {"fantasy": "calm ambient medieval fantasy soundscape", "horror": "quiet dark ambient soundscape, eerie but soft",
        "scifi": "calm ambient space soundscape", "piraten": "calm ambient seafaring soundscape"}
EIGEN = "calm cinematic ambient soundscape"
ART = {"erkunden": "peaceful, wonder, gentle and airy", "taverne": "warm cozy tavern ambience, soft and relaxed",
       "spannung": "mysterious, subdued, slowly evolving tension",
       "kampf": "restrained tension, low steady pulse, serious but soft, not aggressive",
       "finale": "solemn and grand, slowly swelling pads, calm intensity", "sieg": "short gentle warm resolution, soft and hopeful"}
INSTRUMENTE = {
    "fantasy": ("soft harp and warm pads", "gentle lute and strings", "low flute and drones", "soft choir pads and cello",
                "dulcimer and ambient strings", "felt piano and harp"),
    "horror": ("low drones and soft strings", "distant music box and pads", "soft organ drones", "glass harmonica and choir pads",
               "cello and dark pads"),
    "scifi": ("warm analog pads and drones", "glassy bells and deep drones", "soft synth pads and slow textures",
              "ambient strings and synth pads"),
    "piraten": ("soft accordion and pads", "gentle guitar and warm pads", "low strings and soft whistle", "cello and warm pads"),
}
INSTRUMENTE_EIGEN = ("soft strings and pads", "felt piano and strings", "harp and choir pads", "ambient guitar and pads")
_LANGSAM = ("very slow tempo, 60 bpm", "slow tempo, 66 bpm", "slow tempo, 72 bpm")
TEMPO = {"erkunden": _LANGSAM, "spannung": _LANGSAM, "finale": _LANGSAM, "sieg": _LANGSAM,
         "taverne": ("slow tempo, 72 bpm", "relaxed tempo, 80 bpm"), "kampf": ("slow steady tempo, 76 bpm", "steady tempo, 80 bpm")}
TONART = ("in D minor", "in A minor", "in E minor", "in C major", "in G major", "in F major", "in B flat major", "in C minor")
ENDE = ("instrumental ambient background music for a tabletop role-playing game, quiet and soft dynamics, "
        "no drums, no percussion, no sudden changes, no vocals, loops well")

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
_state = {"run": None, "fehler": 0, "ruhe": 0.0, "nacht": "", "stil": False}
_day = DayCounter(gemacht=0, weg=0, geholt=0, entfernt=0)


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
        d["stuecke"] = [x for x in d.get("stuecke") or [] if isinstance(x, dict) and ID.fullmatch(str(x.get("id")))
                        and x.get("v") == STIL_V]   # an older style is never played (alt_weg throws it away)
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


def count(d, welt, st):
    return sum(1 for x in d["stuecke"] if x["w"] == welt and x["st"] == st)


def prune(d, ziel, mb, keep=""):
    """Inside the lock: each field at most ziel pieces and the store within mb; the most played go first (then the
    oldest), never keep (the piece just made). Returns the ids taken out."""
    plays = lambda x: (-(x.get("n", 0) + _plays.get(x["id"], 0)), x.get("t", 0))   # noqa: E731
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
    """The words for the music model: only fixed words of this module (never a text of the game)."""
    inst = INSTRUMENTE.get(welt, INSTRUMENTE_EIGEN)
    return ", ".join((STIL.get(welt, EIGEN), ART[st], rng.choice(inst), rng.choice(TEMPO[st]), rng.choice(TONART), ENDE))


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


def mood(rd):
    """The round's mood now: a fight (5b's kampf or the scene's words) > a merchant or a settlement > the finale >
    tension in the scene's words > the act's mood > exploring."""
    sz = rd.get("szene") or {}
    text = f"{sz.get('ort') or ''} {sz.get('stimmung') or ''}"
    if rd.get("kampf") or KAMPF.search(text):
        return "kampf"
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
    """The current mood, the moods of this act and the next one (BEREIT each, the fight and the victory too) and, on
    a new act, NEU_JE_AKT new pieces for the act after it."""
    s = s or settings()
    welt, plan, i = rd.get("welt"), rd.get("plan"), rd.get("akt", 0)
    now_m = mood(rd)
    nxt = act_mood(plan, i + 1)
    for m in (now_m, act_mood(plan, i), nxt, "kampf", "sieg"):
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
        pick = lambda m: [x["id"] for x in sorted(d["stuecke"], key=lambda x: -x.get("t", 0))   # noqa: E731
                          if x["w"] == rd.get("welt") and x["st"] == m][:LISTE]
        out.update(an=True, st=st, name=NAMEN[st][li], stuecke=pick(st), sieg=pick("sieg"), ziel=s["stuecke"])
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


async def make(welt, st, rng=None):
    """One piece of this field on the heavy jobs' place, the voice first; kept and the store pruned. Returns "ok" or
    why not (GRUENDE). Never raises."""
    import musik
    import schwer
    import vorrang
    import wartung
    rng = rng or random.Random(secrets.randbits(32))
    secs = SIEG_S if st == "sieg" else rng.choice(LAENGE)
    body = {"caption": caption(welt, st, rng), "seconds": secs, "lyrics": "", "language": "", "seed": rng.randrange(2 ** 31),
            "title": f"Dungeon {st}"}
    if musik.model():
        body["variant"] = musik.model()
    jid = secrets.token_hex(6)
    _state["run"] = jid
    t0 = time.perf_counter()
    why = "ok"
    try:
        await vorrang.quiet("Musik machen")

        async def once():
            await vorrang.quiet("Musik machen")
            if wartung.paused("musik"):
                raise ValueError("pause")
            return await musik.make(body)
        mp3, _d = await asyncio.wait_for(schwer.run("musik", jid, time.time(), once), musik.JOB_SECONDS + schwer.WAIT_S)
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


def alt_weg():
    """Throws away the pieces of an older style (STIL_V) with their files, so the fields are made again. Returns how
    many."""
    with _lock:
        raw = read_json(INDEX, {})
        alle = raw.get("stuecke") if isinstance(raw, dict) and isinstance(raw.get("stuecke"), list) else []
        alt = [x for x in alle if not isinstance(x, dict) or x.get("v") != STIL_V]
        if not alt:
            return 0
        for x in alt:
            if isinstance(x, dict) and ID.fullmatch(str(x.get("id"))):
                _rm(x["id"])
        _write({"stuecke": [x for x in alle if x not in alt]})
    _day.bump("entfernt", len(alt))
    print(f"dungeon: musik | neuer stil | {len(alt)} stuecke weg", flush=True)
    return len(alt)


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
    if not _state.get("stil"):
        _state["stil"] = True
        await asyncio.to_thread(alt_weg)
    day = DayCounter.date()
    if night(now) and _state["nacht"] != day and not notaus.blocks("auto"):
        _state["nacht"] = day
        print(f"dungeon: musik | nacht | {fill_all(s)} felder", flush=True)
    if _state["run"] or now < _state["ruhe"]:
        return "ruht"
    job = next_job(s)
    if not job:
        return "nichts"
    if schwer.offen():
        return "wartet"
    return await make(*job)


async def loop():
    while True:
        try:
            await step()
        except Exception as e:   # noqa: BLE001 - the loop goes on
            print("dungeon: musik | fehler", type(e).__name__, flush=True)
        await asyncio.sleep(TAKT)


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


def piece(sid):
    """The MP3 of a piece of the store (any seat of a running round may hear any piece: nothing of it is personal)."""
    if not isinstance(sid, str) or not ID.fullmatch(sid) or not any(x["id"] == sid for x in _read()["stuecke"]):
        raise LookupError("stueck")
    with open(file_of(sid), "rb") as f:
        mp3 = f.read()
    _plays[sid] = _plays.get(sid, 0) + 1
    _day.bump("geholt")
    return mp3


def for_live():
    """Numbers only: pieces, full fields, making or waiting, made/failed/fetched/pruned today."""
    s = settings()
    d = _read()
    t = _day.counts()
    fields = {(x["w"], x["st"]) for x in d["stuecke"]}
    return {"an": on(s), "stuecke": len(d["stuecke"]), "mb": round(sum(x.get("b", 0) for x in d["stuecke"]) / 1024 / 1024),
            "voll": sum(1 for k in fields if count(d, *k) >= s["stuecke"]), "macht": bool(_state["run"]),
            "wartet": len(_want), "gemacht": t["gemacht"], "weg": t["weg"], "geholt": t["geholt"], "entfernt": t["entfernt"]}


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
            return piece(sid)
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
            return piece(b.get("s"))
        return _mp3(await asyncio.to_thread(go))
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


@router.delete("/api/admin/dungeon/musik", dependencies=[Depends(auth)])
async def admin_clear(request: Request):
    guard.limit(request, "dungeonmusik", admin=True)
    await asyncio.to_thread(clear)
    return admin_view("en" if request.query_params.get("lang") == "en" else "de")
