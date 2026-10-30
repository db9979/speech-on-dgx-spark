"""KI-Dungeon-Master: Heldenlied des Barden (D&D-Ideen Runde 2, Punkt 8, Dominik 2026-10-26 „1-9 umsetzten“; the
probe in German: „1 deutsch“).

When a chapter ends (the log's „kapitel_ende“ with its number, the main thread's), the own music model sings a short
song of 60 to 90 seconds about the heroes of the round: the lyrics come only from fixed verses of this module (one
chorus per world) with the heroes' names and deeds after a word list, never a text of the model or a player:
- a name only if it is a plain name (NAME: letters, space, apostrophe, hyphen, at most 24) and passes the music's own
  word list (musik.refuse_text), else „ein Held“;
- a deed per hero from the log of this chapter (TATEN: the hero's own hits, spells, loot, levels; else „ging mutig
  voran“), one fixed line each;
- German singing, a bard's sound per world (STIL_LIED), on the heavy jobs' place after the voice (dungeon_musik.render),
  before the store's pieces; one try per chapter.
The table plays the new song once (music on), the bar lists the round's songs to play again, the host deletes one;
nobody else hears them: a song is fetched like a piece only by a seat of its own round (dungeon_musik.stueck).

Off by default: the admin's switch dungeonheldenlied (features.py, chat.dungeon_heldenlied) for the round's host,
and only with „Musik vorbereiten“ and the music model (dungeon_musik.on). The journal gets fixed words and numbers
(„dungeon: lied | …“), Live only counts.

    STATE/dungeon-lieder/index.json   {"lieder": [{id, rid, kapitel, welt, s, t, b}]}
    STATE/dungeon-lieder/<id>.mp3     one song (personal: the names of a round's heroes)

    POST /api/profile/dungeon/{rid}/lied/{sid}/weg   the host deletes a song of the round
"""
import asyncio
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, Request

import features
import guard
from common import STATE, DayCounter, read_json, write_json
from core import assistant, own_profile

router = APIRouter()
KEY = "dungeonheldenlied"
DIR = os.path.join(STATE, "dungeon-lieder")
INDEX = os.path.join(DIR, "index.json")
ID = re.compile(r"l[0-9a-f]{10}")
SPRACHE = "de"             # Dominik 2026-10-26 „1 deutsch“ after listening to the probe
SEKUNDEN = (60, 90)        # 60 s and 6 s more per hero, at most 90
JE_RUNDE = 20              # songs kept per round (the oldest go)
HELDEN = 5
NAME = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{0,23}")
ORDNUNG = ("ersten", "zweiten", "dritten", "vierten", "fünften", "sechsten", "siebten", "achten", "neunten", "zehnten",
           "elften", "zwölften")

# the bard's sound per world: fixed English words for the music model as tags (genre, voice and instruments, mood,
# production; plan dungeon-musik-tuning V1a, Dominik 2026-10-30 „1-8“); tempo (TEMPO_LIED), the world's minor key
# (dungeon_musik.TONART, one source) and 4/4 go as the song's metadata, what it must not be as its negative prompt
STIL_LIED = {"fantasy": "medieval bard song, folk ballad, solo voice, lute, flute, soft frame drum, warm bass",
             "horror": "dark gothic ballad, solo voice, cello, harp, slow drum, deep bass",
             "scifi": "space ballad, solo voice, acoustic guitar, warm synth pads, soft drums, bass",
             "piraten": "sea shanty, solo voice, accordion, fiddle, stomping drums, upright bass"}
STIL_EIGEN = "storytelling ballad, solo voice, guitar, strings, soft drums, warm bass"
TEMPO_LIED = {"fantasy": 84, "horror": 70, "scifi": 80, "piraten": 96}
TEMPO_EIGEN = 82
ENDE_LIED = "verse and chorus, clear expressive German singing, storytelling, warm, soft ending"
NEGATIV_LIED = "mumbling, shouting, off-key singing, spoken words, hectic, harsh noise"

# the fixed verses (German; only the names and the chapter's number are filled in)
KEHRREIM = {
    "fantasy": ("Singt vom Mut, singt vom Licht,", "singt, bis der Morgen bricht!", "Wer am Feuer sitzt und lauscht,", "vergisst die Helden nicht."),
    "horror": ("Singt leis, wenn Nebel steigt,", "wenn jede Glocke schweigt.", "Sie gingen durch die finstre Nacht", "und haben nicht geweicht."),
    "scifi": ("Singt vom Licht der fernen Sterne,", "von der Fahrt durch kalten Raum.", "Wer die Dunkelheit bezwungen,", "lebt in jedem Sternentraum."),
    "piraten": ("Hoch die Segel, hoch das Lied,", "wenn der Sturm vorüberzieht!", "Trinkt auf Mut und trinkt auf Glück,", "die Helden kehren heim zurück!"),
}
KEHRREIM_EIGEN = ("Singt vom Mut, singt vom Weg,", "singt von Freund und Treu.", "Wer am Feuer sitzt und lauscht,", "hört die Geschichte neu.")
SCHLUSS = {"fantasy": "und weiter ruft das alte Land.", "horror": "und hinter ihnen fiel das Tor.",
           "scifi": "und vor dem Bug ein neuer Stern.", "piraten": "und vor dem Wind ein neues Ziel."}
SCHLUSS_EIGEN = "und vor uns liegt der nächste Weg."
TATEN = {"krit": "{name} traf, wie keiner je zuvor,", "kampf": "{name} schlug manchen Feind zurück,",
         "zauber": "{name} wob Zauber, hell und klar,", "stufe": "{name} wuchs an Kraft und Mut,",
         "beute": "{name} fand Gold und alten Glanz,", "": "{name} ging mutig stets voran,"}
REIHE = ("krit", "kampf", "zauber", "stufe", "beute")   # the first deed a hero has in this order is sung

_lock = threading.Lock()
_cache = {"mtime": None, "d": None}
_want = {}                 # (rid, kapitel) -> {"welt", "lyrics", "s"}   in the order asked
_tried = set()             # (rid, kapitel) tried once (made or not): never again
_state = {"run": None}
_day = DayCounter(gemacht=0, weg=0, geloescht=0)


def on(rd):
    """The host's admin switch and the round's music (dungeon_musik.on: „Musik vorbereiten“ and the model)."""
    import dungeon_musik
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"]) and dungeon_musik.on()


# ---------------------------------------------------------------- the lyrics (fixed verses, names and deeds only)
def name(x):
    """A hero's name for the song: a plain name the music's word list lets through, else „ein Held“."""
    import musik
    x = re.sub(r"\s+", " ", str(x or "")).strip()
    return x if NAME.fullmatch(x) and not musik.refuse_text("", x) else "ein Held"


def taten(rd, seit):
    """{hero's name: the first deed of REIHE it did since the log's turn seit} (its own hits, spells, loot, level)."""
    got = {}
    for e in rd.get("log") or []:
        if e.get("n", 0) <= seit:
            continue
        a, n = e.get("art"), e.get("name")
        k = ("krit" if e.get("krit") else "kampf") if a == "angriff" and e.get("treffer") and not e.get("von_gegner") else \
            a if a in ("zauber", "stufe", "beute") else ""
        if k and n:
            got.setdefault(n, set()).add(k)
    return {n: next(k for k in REIHE if k in ks) for n, ks in got.items()}


def lyrics(rd, kapitel, seit):
    """The song's text: verse, chorus, verse, chorus; only fixed lines with names and the chapter's number."""
    welt = rd.get("welt", "")
    helden = [(p.get("held") or {}).get("name", "") for p in (rd.get("plaetze") or {}).values() if p.get("held")][:HELDEN]
    tat = taten(rd, seit)
    zeilen = [TATEN[tat.get(h, "")].format(name=name(h)) for h in helden] or [TATEN[""].format(name="ein Held")]
    ordnung = ORDNUNG[kapitel - 1] if 1 <= kapitel <= len(ORDNUNG) else "neuen"
    kehr = "\n".join(KEHRREIM.get(welt, KEHRREIM_EIGEN))
    erst, dann = zeilen[:3], zeilen[3:]
    vers1 = [f"Hört, was im {ordnung} Kapitel geschah:"] + erst
    vers2 = dann + ["So zog die Schar von Ort zu Ort,", SCHLUSS.get(welt, SCHLUSS_EIGEN)]
    return f"[verse]\n" + "\n".join(vers1) + f"\n[chorus]\n{kehr}\n[verse]\n" + "\n".join(vers2) + f"\n[chorus]\n{kehr}", len(helden)


def caption(welt):
    return ", ".join((STIL_LIED.get(welt, STIL_EIGEN), ENDE_LIED))


def meta(welt):
    """The song's metadata (musik_server.metadata): with all of them the engine's planner keeps the caption."""
    import dungeon_musik
    return {"bpm": TEMPO_LIED.get(welt, TEMPO_EIGEN), "keyscale": dungeon_musik.TONART.get(welt, dungeon_musik.TONART_EIGEN)[0],
            "timesignature": "4", "negative": NEGATIV_LIED}


# ---------------------------------------------------------------- the store
def _read():
    try:
        m = os.path.getmtime(INDEX)
    except OSError:
        return {"lieder": []}
    if _cache["mtime"] != m:
        d = read_json(INDEX, {})
        d = d if isinstance(d, dict) else {}
        d["lieder"] = [x for x in d.get("lieder") or [] if isinstance(x, dict) and ID.fullmatch(str(x.get("id")))]
        _cache.update(mtime=m, d=d)
    return _cache["d"]


def _write(d):
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


def of_round(rid):
    """The round's songs, newest first (the index keeps them in the order made): [{id, kapitel, s}]."""
    return [{"id": x["id"], "kapitel": x["kapitel"], "s": x.get("s", 0)} for x in reversed(_read()["lieder"]) if x.get("rid") == rid]


def piece(rid, sid):
    """The MP3 of a song of this round (the seat is checked by the caller)."""
    if not isinstance(sid, str) or not ID.fullmatch(sid) or not any(x["id"] == sid and x.get("rid") == rid for x in _read()["lieder"]):
        raise LookupError("stueck")
    with open(file_of(sid), "rb") as f:
        return f.read()


def remove(rid, sid):
    with _lock:
        d = _read()
        if not any(x["id"] == sid and x.get("rid") == rid for x in d["lieder"]):
            raise LookupError("stueck")
        d = {"lieder": [x for x in d["lieder"] if x["id"] != sid]}
        _write(d)
        _rm(sid)
    _day.bump("geloescht")


def tidy(rids):
    """The night: songs of rounds that are gone go too. Returns how many."""
    with _lock:
        d = _read()
        gone = [x["id"] for x in d["lieder"] if x.get("rid") not in rids]
        if gone:
            _write({"lieder": [x for x in d["lieder"] if x["id"] not in gone]})
            for sid in gone:
                _rm(sid)
    return len(gone)


# ---------------------------------------------------------------- what a round asks for (dungeon_musik.for_view)
def ask_round(rid, rd):
    """A chapter that ended and has no song yet asks for one (once). Returns the table's fields."""
    if not on(rd):
        return {}
    ends = [e for e in rd.get("log") or [] if e.get("art") == "kapitel_ende" and isinstance(e.get("kapitel"), int)
            and not isinstance(e.get("kapitel"), bool) and e["kapitel"] > 0]
    have = {x["kapitel"] for x in _read()["lieder"] if x.get("rid") == rid}
    if ends:
        e = ends[-1]
        k = (rid, e["kapitel"])
        with _lock:
            if e["kapitel"] not in have and k not in _tried and k not in _want:
                seit = max([x.get("n", 0) for x in ends[:-1]] or [0])
                text, n = lyrics(rd, e["kapitel"], seit)
                _want[k] = {"welt": rd.get("welt", ""), "lyrics": text, "s": min(SEKUNDEN[1], SEKUNDEN[0] + 6 * n)}
    lieder = of_round(rid)
    return {"lieder": lieder, "lied": lieder[0]["id"] if lieder else ""}


def pending():
    return bool(_want) and not _state["run"]


async def make_next():
    """The first song asked for: made once, kept; the round keeps at most JE_RUNDE. Returns "ok" or why not."""
    import dungeon_musik
    with _lock:
        if not _want:
            return "nichts"
        k = next(iter(_want))
        job = _want.pop(k)
        _tried.add(k)
    rid, kapitel = k
    body = {"caption": caption(job["welt"]), "seconds": job["s"], "lyrics": job["lyrics"], "language": SPRACHE,
            "seed": secrets.randbelow(2 ** 31), "title": "Heldenlied", **meta(job["welt"])}
    import musik
    if musik.model():
        body["variant"] = musik.model()
    jid = secrets.token_hex(6)
    _state["run"] = jid
    t0 = time.perf_counter()
    why = "ok"
    try:
        mp3 = await dungeon_musik.render(body, jid)
        sid = "l" + secrets.token_hex(5)

        def keep():
            with _lock:
                os.makedirs(DIR, mode=0o700, exist_ok=True)
                with open(file_of(sid) + ".neu", "wb") as f:
                    f.write(mp3)
                os.chmod(file_of(sid) + ".neu", 0o600)
                os.replace(file_of(sid) + ".neu", file_of(sid))
                d = _read()
                xs = list(d["lieder"]) + [{"id": sid, "rid": rid, "kapitel": kapitel, "welt": job["welt"], "s": job["s"],
                                           "t": int(time.time()), "b": len(mp3)}]
                mine = [x for x in xs if x.get("rid") == rid]        # in the order made, the oldest first
                old = [x["id"] for x in mine[:max(0, len(mine) - JE_RUNDE)]]
                _write({"lieder": [x for x in xs if x["id"] not in old]})
                for o in old:
                    _rm(o)
        await asyncio.to_thread(keep)
        _day.bump("gemacht")
    except asyncio.TimeoutError:
        why = "zeit"
    except ValueError as e:
        why = str(e) if str(e) in dungeon_musik.GRUENDE else "dienst"
    except Exception:   # noqa: BLE001 - every song ends with a journal line
        why = "dienst"
    finally:
        _state["run"] = None
    if why != "ok":
        _day.bump("weg")
    print(f"dungeon: lied | {why} | kapitel {kapitel} | {job['s']} s | {round((time.perf_counter() - t0) * 1000)} ms", flush=True)
    return why


def for_live():
    """Numbers only: songs kept, made/failed/deleted today, waiting."""
    t = _day.counts()
    return {"lieder": len(_read()["lieder"]), "gemacht": t["gemacht"], "weg": t["weg"], "geloescht": t["geloescht"],
            "wartet": len(_want), "macht": bool(_state["run"])}


# ---------------------------------------------------------------- routes
@router.post("/api/profile/dungeon/{rid}/lied/{sid}/weg", dependencies=[Depends(assistant)])
async def weg(rid: str, sid: str, request: Request, prof=Depends(own_profile)):
    """The host deletes a song of the round."""
    import dungeon
    uid = prof["id"]
    dungeon._need(uid)
    guard.limit(request, "dungeonmusik", uid)

    def go():
        rd = dungeon._round(dungeon._read(), rid)
        if rd.get("owner") != uid:
            raise PermissionError("gastgeber")
        remove(rid, sid)
    try:
        await asyncio.to_thread(go)
    except dungeon.KNOWN as e:
        print(f"dungeon: lied | loeschen abgelehnt | {type(e).__name__}", flush=True)
        raise dungeon._http(e)
    print("dungeon: lied | geloescht", flush=True)
    return {"lieder": of_round(rid)}
