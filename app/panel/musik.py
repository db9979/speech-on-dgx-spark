"""Musik machen (plan plaene/musik.md, Dominik 2026-10-16 „1a 2a 3a 4a 5a“, M1 „3a“): songs from a wish, made on
the model computer by ACE-Step 1.5 (musik_server.py, music.port 31004, installed with `install.sh --musik 2b|xl`).

Ways in: the tool musik_machen in the conversation (the language model writes the English description from the
person's words and, for a song with singing, the lyrics) and Ich → Musik (the person's own sentence goes as it is).
The panel decides everything else with fixed rules: instrumental and DEFAULT_S seconds unless the person asks for
singing or a length, at most music.max_s seconds, one song at a time on the whole Spark, at most WAITING waiting,
one open job per profile, music.day_limit songs per profile in 24 hours, music.store_mb per profile. The admin
picks the model (music.model: one of the installed variants, Dominik 2026-10-16 „das größere Modell auch testen
und auswählen“); „Musik testen“ measures every installed one with two fixed songs.

Protection (fixed rules, no switch): a word list before making (the wish, the description and the lyrics, de and
en), no passwords or account numbers, no songs „im Stil von“ a named artist, and every song marked as made by an
AI (musik_server: its own ID3 tag). Text from outside (mail, web, documents) never starts a
song: musik_machen is a changing tool, locked after outside text (chat.LOCKED_OUTSIDE via the extras' "changes"),
and from Notaus stage 2 on. Guests never get the tool or the page; a blocked profile only sees „Daten löschen“.

Speech first (vorrang): a job waits until the spoken answer is over, the song itself runs while nobody speaks.
Storage users/<id>/musik/<song>.mp3 and index.json (speicher.AREAS "musik"). Journal lines start with "musik:",
fixed words and numbers only: never a wish, a description, lyrics or a name (profiles.log_name)."""
import asyncio
import base64
import json
import os
import re
import secrets
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

import features
import guard
import notaus
import profiles
import wartung
from common import DayCounter, STATE, load_config, model_url, write_json
from core import api_headers, assistant, auth, browser_profile, json_body, own_profile

router = APIRouter()
KEY = "musik"
VARIANTS = {"2b": ("2B turbo + 1,7B", "2B turbo + 1.7B"), "2b-klein": ("2B turbo + 0,6B", "2B turbo + 0.6B"),
            "xl": ("XL turbo + 1,7B", "XL turbo + 1.7B")}   # musikmodell.VARIANTS (the panel has no model files)
MAX_WISH = 300
MAX_CAPTION = 600            # musik_server.MAX_CAPTION
MAX_LYRICS = 3000
MAX_SONGS = 200             # songs per profile, whatever the space
MIN_S, DEFAULT_S = 10, 120   # Dominik 3a: instrumental, 2 minutes unless asked
WAITING = 10                # open jobs on the whole Spark
JOB_SECONDS = 20 * 60       # waiting for a pause, loading the model and making the song
BACK = 7                    # messages back an answer from outside text stays data for a song wish (chat_turn)
FOLLOW_SECONDS = 10 * 60    # after a wish, „ja, mit Gesang“ is understood without the words
MAX_MP3 = 40 * 1024**2
DAY_S = 24 * 3600
ID = re.compile(r"[0-9a-f]{12}")
CTRL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f<>\ud800-\udfff]")
LANGS = ("de", "en", "fr", "es", "it", "nl", "pt", "pl", "sv", "da", "no", "fi", "tr", "ru", "uk", "ja", "zh", "ko")

# a wish for a song in the person's own words (the Weiche's group "musik" and offer below): a verb of making and a
# song, or composing; „Spiel Musik“, „Mach Musik an“ (Home Assistant, the speakers) has no making word and stays there
_SONG = (r"(lied\w*|song\w*|musik[\s-]?stück\w*|musik[\s-]?stueck\w*|stück musik|beat\w*|\w+tracks?|melodie\w*|jingle\w*|klingelton\w*|weckton\w*|"
         r"hymne\w*|ballade\w*|rap\w*|schlaflied\w*|gute-nacht-lied\w*|geburtstagslied\w*|instrumental\w*|"
         r"hintergrundmusik|filmmusik|tune|track|melody|lullaby|anthem)")
WORDS = re.compile(
    r"(?i)\b(komponier\w*|compose\w*|vertone\w*)\b"
    r"|\b(mach\w*|erstell\w*|erzeug\w*|generier\w*|schreib\w*|dicht\w*|produzier\w*|sing\w*|create|make|generate|write|produce)\b"
    r".{0,60}\b" + _SONG + r"\b"
    # the song first, the verb at the end („Kannst du mir ein Lied über Katzen machen?“)
    r"|\b(ein|eine|einen)\s+(?:[\w-]+[\s-]+){0,3}" + _SONG + r"\b.{0,120}\b(machen|erstellen|erzeugen|generieren|schreiben|"
    r"komponieren|dichten|produzieren|singen)\b"
    r"|\bmusik\b.{0,30}\b(machen|erzeugen|komponieren|generieren|erstellen|produzieren)\b(?!\s+an)"
    r"|\b(mach\w*|erzeug\w*|generier\w*|make|generate)\s+(?:mir\s+|uns\s+|bitte\s+)*(?:etwas\s+|ein\s+bisschen\s+)?(?:eigene\s+)?musik\b(?!\s+an\b|\s+aus\b|\s+lauter|\s+leiser)")
# „spiel“, „abspielen“, „lauter“: playing music somewhere, never making it
PLAY = re.compile(r"(?i)\b(spiel\w*|abspiel\w*|play\w*|lauter|leiser|pausier\w*|stopp?\w*|nächste\w*|weiter)\b")
# a change of the last song in the follow window: „nochmal“, „länger“, and a style or genre („geht das in Reggae
# style“, Dominik 2026-10-16: without these words the tool was not offered and the model promised a song anyway)
AGAIN = re.compile(r"(?i)\b(nochmal|noch einmal|noch ein|nochmals|anders|andere[nrs]?|aber|statt|lieber|länger|"
                   r"kürzer|schneller|langsamer|ruhiger|fröhlicher|mit gesang|ohne gesang|again|another|instead|longer|shorter|"
                   r"geht das|kannst du das|stil\w*|style|version|variante|fassung|remix|genre|reggae|rock|jazz|pop|techno|"
                   r"klassik\w*|classical|schlager|hip.?hop|metal|blues|country|funk|disco|soul|punk|folk|akustisch\w*|acoustic)\b")
# a song named in the last answer or the person's words (also „Musik“): in the follow window the model gets NO_PROMISE
SONG = re.compile(r"(?i)\b" + _SONG + r"\b")
ABOUT = re.compile(r"(?i)\b(" + _SONG[1:-1] + r"|musik|music)\b")
NO_PROMISE = ("In dieser Runde ist musik_machen nicht angeboten, es entsteht also kein Lied: sag nie, dass ein Lied "
              "entsteht oder neu gemacht wird. Für eine andere Fassung soll die Person es sagen, z. B. „Mach das Lied "
              "nochmal im Reggae-Stil“.")
YES = re.compile(r"(?i)^\W*(ja|jo|jep|jawohl|ok|okay|passt|genau|gern|gerne|mach|los|klar|super|yes|yep|yeah|sure|fine)\b")
YES_MAX = 120
# fixed word list: nothing sexual, no violence, no hate (de and en), the same words for the wish, the description
# and the lyrics
BAD = re.compile(
    r"(?i)\b(porn\w*|sex\w*|erotik\w*|erotisch\w*|erotic\w*|nackt\w*|naked|nude\w*|nsfw|kinderporn\w*|missbrauch\w*|"
    r"vergewaltig\w*|rape|massaker|massacre|blutbad|folter\w*|tortur\w*|töte[nt]?|umbring\w*|kill\w*|murder\w*|"
    r"hakenkreuz\w*|swastika|nazi\w*|hitler|kkk|sieg heil|white power|rassenhass|volksverhetz\w*)\b")
# no copies of a named artist („im Stil von …“, „klingt wie …“): the style comes from words, never from a name
ARTIST = re.compile(r"(?i)\b(im stile? von|in der art von|klingt wie|wie von|so wie|in the style of|sounds? like|like a song by)\s+\S")
SECRET = re.compile(r"(?i)\b(passwort\w*|kennwort\w*|password\w*|pin|tan|iban|kontonummer|api.?key|token)\b\s*[:=]?\s*\S*\d")

TOOL = {"type": "function", "function": {
    "name": "musik_machen",
    "description": "Makes a song on the Spark (ACE-Step 1.5) from the user's wish. Write beschreibung_en yourself: "
                   "one English description of the music (genre, mood, instruments, tempo, voice if sung), at most 60 "
                   "words, no artist names. Only when the user wants singing: gesang true, sprache and liedtext (short "
                   "verses with [verse] and [chorus] lines, in the asked language). Without a length leave sekunden "
                   "out. The song is made in the background; do not describe it as if you could hear it.",
    "parameters": {"type": "object", "required": ["beschreibung_en"], "properties": {
        "beschreibung_en": {"type": "string", "description": "the music described in English"},
        "wunsch": {"type": "string", "description": "the user's wish in their own words, short"},
        "sekunden": {"type": "integer", "description": "length in seconds, only if the user named one"},
        "gesang": {"type": "boolean", "description": "true only when the user wants singing"},
        "sprache": {"type": "string", "enum": list(LANGS), "description": "language of the lyrics"},
        "liedtext": {"type": "string", "description": "the lyrics with [verse]/[chorus] lines, only with gesang"}}}}}
HINT = ("musik_machen macht ein Lied oder Musikstück auf dem Spark. Rufe es nur auf, wenn die Person selbst Musik, "
        "ein Lied oder eine Melodie haben möchte; schreib beschreibung_en auf Englisch, ohne Künstlernamen. Ohne "
        "Wunsch nach Gesang ist es instrumental. Danach ein kurzer Satz, dass das Lied entsteht und gleich erscheint "
        "(im Chat und unter Ich → Musik). „Spiel Musik“ heißt abspielen, nicht machen.")

_lock = threading.Lock()
_make = []                  # [(loop, asyncio.Lock)] of the running loop: one song at a time
_jobs = {}                  # jid -> job
_tasks = set()
_recent = {}                # uid -> time of the last wish (also a refused one), song start and end (FOLLOW_SECONDS)
_count = DayCounter(done=0, failed=0, refused=0)
BACKGROUND = True           # tests run _work themselves


# ---------------------------------------------------------------- switches and limits
def cfg():
    return load_config("music")


def admin_on():
    return features.admin_on(KEY)


def limits(c=None):
    c = cfg() if c is None else c
    return {"day": int(c["day_limit"]), "store_mb": int(c["store_mb"]), "max_s": int(c["max_s"]),
            "default_s": min(DEFAULT_S, int(c["max_s"])), "wish": MAX_WISH, "lyrics": MAX_LYRICS, "songs": MAX_SONGS}


def model(c=None):
    """The variant the admin picked (music.model), "" = the one install.sh set on the model computer."""
    v = (cfg() if c is None else c).get("model") or ""
    return v if v in VARIANTS else ""


def off_hint(uid, lang="de"):
    t = features.missing_text(KEY, uid, lang)
    if lang == "en":
        return "Making music is not available. " + (t or "Ask the admin (Features → Making music).")
    return ("Musik machen geht gerade nicht. " + (t or "Frag den Admin (Funktionen → Musik machen).")
            + " Sag das so in einem Satz und beschreibe kein Lied.")


def clean(v, most, lines=False):
    s = CTRL.sub(" ", str(v or ""))
    if lines:
        return "\n".join(re.sub(r"[ \t]+", " ", x).strip() for x in s.replace("\r", "").split("\n")).strip()[:most]
    return re.sub(r"\s+", " ", s).strip()[:most]


def refuse_text(uid, *texts):
    """The reason in fixed words when a fixed rule refuses, else "". Names are fine in a song (Dominik 2026-10-16:
    „das sind einfach nur die Namen dazu“; a birthday song names its people): unlike a picture, a song shows no
    one's face."""
    joined = " ".join(str(t or "") for t in texts)
    if BAD.search(joined):
        return "wortliste"
    if ARTIST.search(joined):
        return "kuenstler"
    if SECRET.search(joined):
        return "geheim"
    return ""


REFUSED = {"wortliste": ("Das mache ich nicht: der Wunsch fällt unter die festen Regeln (nichts Sexuelles, keine "
                         "Gewalt, kein Hass).", "I won't make that: the wish falls under the fixed rules (nothing "
                         "sexual, no violence, no hate)."),
           "kuenstler": ("Den Stil eines bestimmten Künstlers ahme ich nicht nach; beschreib lieber Stil, Stimmung und "
                         "Instrumente.", "I don't copy a named artist; describe the style, mood and instruments instead."),
           "geheim": ("Passwörter, PINs und Kontonummern kommen in kein Lied.",
                      "Passwords, PINs and account numbers go into no song."),
           "memory": ("Gerade ist zu wenig Speicher frei; das Musikmodell startet erst, wenn mehr frei ist.",
                      "Too little memory is free right now; the music model starts once more is free."),
           "missing": ("Das Musikmodell ist nicht installiert (Admin: sudo ./install.sh --musik 2b).",
                       "The music model is not installed (admin: sudo ./install.sh --musik 2b)."),
           "engine": ("Die Musik-Engine hat das Lied abgebrochen.", "The music engine stopped the song."),
           "dienst": ("Der Musik-Dienst antwortet gerade nicht.", "The music service does not answer right now."),
           "zeit": ("Das Lied dauerte zu lange.", "The song took too long."),
           "notaus": ("Der Notaus hält das gerade an.", "The Notaus holds this off right now."),
           "pause": ("Musik machen wird gerade gewartet; bitte etwas später noch einmal.",
                     "Making music is being maintained right now; please try again a little later.")}


# ---------------------------------------------------------------- storage (users/<id>/musik/)
def _dir(uid):
    if not re.fullmatch(r"[\w\-]{1,64}", str(uid or "")):
        raise ValueError("bad profile")
    return profiles._path(uid, "musik")


def _index_file(uid):
    return os.path.join(_dir(uid), "index.json")


def all_songs(uid):
    """The profile's songs, newest first."""
    try:
        p = _index_file(uid)
        if os.path.islink(p):
            return []
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        items = [x for x in d.get("items") or [] if isinstance(x, dict) and ID.fullmatch(str(x.get("id") or ""))]
    except (OSError, ValueError):
        return []
    return sorted(items, key=lambda x: -float(x.get("t") or 0))


def _save_index(uid, items):
    profiles._write(_index_file(uid), {"items": items[:MAX_SONGS]})


def song_path(uid, sid):
    if not ID.fullmatch(str(sid or "")):
        return None
    p = os.path.join(_dir(uid), sid + ".mp3")
    return p if os.path.isfile(p) and not os.path.islink(p) else None


def used_bytes(uid):
    return sum(int(x.get("bytes") or 0) for x in all_songs(uid))


def today_count(uid, now=None):
    now = time.time() if now is None else now
    return sum(1 for x in all_songs(uid) if now - float(x.get("t") or 0) < DAY_S)


def keep(uid, mp3, meta):
    """Stores one song and its line in the index; returns the line."""
    sid = secrets.token_hex(6)
    os.makedirs(_dir(uid), mode=0o700, exist_ok=True)
    p = os.path.join(_dir(uid), sid + ".mp3")
    with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(mp3)
    row = dict(meta, id=sid, bytes=len(mp3), t=round(time.time(), 1))
    with _lock:
        _save_index(uid, [row] + all_songs(uid))
    return row


def delete(uid, sid):
    with _lock:
        items = all_songs(uid)
        rest = [x for x in items if x["id"] != sid]
        if len(rest) == len(items):
            return False
        _save_index(uid, rest)
    p = song_path(uid, sid)
    if p:
        os.unlink(p)
    return True


def clear(uid):
    """Every song of the profile (Ich → Musik „Alle löschen“, Daten löschen of the Freigabe)."""
    with _lock:
        n = len(all_songs(uid))
        try:
            d = _dir(uid)
            for name in os.listdir(d):
                if re.fullmatch(r"[0-9a-f]{12}\.mp3|index\.json", name):
                    os.unlink(os.path.join(d, name))
        except OSError:
            pass
    return n


features.OWN[KEY] = (lambda uid: len(all_songs(uid)), clear)


def public(x):
    return {"id": x["id"], "t": x.get("t"), "wish": x.get("wish", ""), "caption": x.get("caption", ""),
            "lyrics": x.get("lyrics", ""), "sung": bool(x.get("sung")), "language": x.get("language", ""),
            "length_s": x.get("length_s"), "seconds": x.get("seconds"), "model": x.get("model", ""),
            "bytes": x.get("bytes", 0), "src": x.get("src", ""), "job": x.get("job", "")}


# ---------------------------------------------------------------- jobs
def stats():
    _count.today()
    with _lock:
        run = sum(1 for j in _jobs.values() if j["state"] == "run")
        wait = sum(1 for j in _jobs.values() if j["state"] == "wait")
    return {"run": run, "wait": wait, "done": _count["done"], "failed": _count["failed"], "refused": _count["refused"]}


def busy(now=None):
    """Live „Im Hintergrund“: (state, seconds) of every song waiting or being made, oldest first (no wish)."""
    now = time.time() if now is None else now
    with _lock:
        return [("run" if j["state"] == "run" else "wait", int(now - j["t0"])) for j in sorted(_jobs.values(), key=lambda j: j["t0"])
                if j["state"] in ("wait", "run")]


def _live(text_):
    try:
        import live
        live.event("Musik", text_)
    except Exception:
        pass


def job_public(j):
    return {"id": j["id"], "state": j["state"], "error": j.get("error", ""), "error_en": j.get("error_en", ""),
            "song": public(j["song"]) if j.get("song") else None, "caption": j["caption"], "t0": int(j["t0"]),
            "length_s": j["seconds"], "sung": j["sung"]}


def jobs_of(uid):
    with _lock:
        return [job_public(j) for j in sorted(_jobs.values(), key=lambda j: j["t0"]) if j["uid"] == uid
                and (j["state"] in ("wait", "run") or time.time() - j.get("end", 0) < 600)]


def _sweep(now):
    with _lock:
        for k in [k for k, j in _jobs.items() if j["state"] not in ("wait", "run") and now - j.get("end", 0) > 3600]:
            _jobs.pop(k, None)


def _say(why, prof):
    print(f"musik: nicht gestartet {why} fuer {profiles.log_name(prof)}", flush=True)


def length(v, lim):
    """The song's length in seconds: the asked one within MIN_S and music.max_s, else the default (Dominik 3a)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        return lim["default_s"]
    return int(max(MIN_S, min(lim["max_s"], int(v))))


def start(prof, caption, wish, seconds=None, sung=False, language="", lyrics="", src="chat", client="web"):
    """Checks everything with fixed rules and starts a job; raises ValueError((de, en)) with the reason."""
    uid = prof["id"]
    if not features.allowed(KEY, uid):
        _say("aus", prof)
        raise ValueError(("Musik machen ist für dich nicht freigegeben.", "Making music is not released for you."))
    try:
        notaus.stop("auftrag", uid)
    except notaus.NotausAktiv:
        _say("notaus", prof)
        raise ValueError(REFUSED["notaus"])
    if wartung.paused("musik"):   # Wartungspause (wartung.py): the music model is being updated, nothing starts
        _say("wartung", prof)
        raise ValueError(REFUSED["pause"])
    caption, wish = clean(caption, MAX_CAPTION), clean(wish, MAX_WISH)
    lyrics = clean(lyrics, MAX_LYRICS, lines=True) if sung else ""
    language = language if language in LANGS else "de"
    if not caption:
        _say("leer", prof)
        raise ValueError(("Was für Musik soll ich machen?", "What kind of music shall I make?"))
    why = refuse_text(uid, caption, wish, lyrics)
    if why:
        _count.bump("refused")
        _say(why, prof)
        raise ValueError(REFUSED[why])
    lim = limits()
    secs = length(seconds, lim)
    _sweep(time.time())
    with _lock:
        if any(j["uid"] == uid and j["state"] in ("wait", "run") for j in _jobs.values()):
            _say("laeuft", prof)
            raise ValueError(("Ich mache schon ein Lied für dich; erst wenn es fertig ist.",
                              "I am already making a song for you; once it is done."))
        if sum(1 for j in _jobs.values() if j["state"] in ("wait", "run")) >= WAITING:
            _say("warteschlange", prof)
            raise ValueError(("Gerade warten schon viele Lieder; bitte etwas später noch einmal.",
                              "Many songs are waiting already; please try again a little later."))
    if today_count(uid) >= lim["day"]:
        _say("tageslimit", prof)
        raise ValueError((f"Heute sind schon {lim['day']} Lieder entstanden; morgen wieder.",
                          f"{lim['day']} songs were made today already; tomorrow again."))
    if used_bytes(uid) >= lim["store_mb"] * 1024 * 1024 or len(all_songs(uid)) >= MAX_SONGS:
        _say("voll", prof)
        raise ValueError(("Deine Lieder brauchen schon den ganzen Platz; bitte erst alte löschen (Ich → Musik).",
                          "Your songs use all their space; please delete old ones first (Me → Music)."))
    jid = secrets.token_hex(6)
    j = {"id": jid, "uid": uid, "state": "wait", "caption": caption, "wish": wish, "seconds": secs, "sung": bool(sung),
         "language": language if sung else "", "lyrics": lyrics, "t0": time.time(), "src": src, "client": client,
         "log": profiles.log_name(prof), "model": model()}
    with _lock:
        _jobs[jid] = j
    _recent[uid] = time.time()
    kind = "gesang" if sung else "instrumental"
    _live(f"Lied {secs} s {kind} angenommen")
    print(f"musik: auftrag {secs} s {kind} {src} fuer {j['log']}", flush=True)
    if BACKGROUND:
        try:
            t = asyncio.get_running_loop().create_task(_go(j))
            _tasks.add(t)
            t.add_done_callback(_tasks.discard)
        except RuntimeError:
            _fail(j, "dienst")
    return job_public(j)


def _fail(j, why):
    de, en = REFUSED.get(why, REFUSED["dienst"])
    j.update(state="error", error=de, error_en=en, end=time.time())
    _count.bump("failed")
    _live(f"Lied nicht gemacht: {why}")
    print(f"musik: nicht gemacht {why} fuer {j['log']}", flush=True)


async def _go(j):
    try:
        await asyncio.wait_for(_work(j), JOB_SECONDS)
    except asyncio.TimeoutError:
        _fail(j, "zeit")
    except Exception as e:   # noqa: BLE001 - every job ends with a state and a journal line
        print("musik: fehler", type(e).__name__, flush=True)
        _fail(j, "dienst")


def _make_lock():
    loop = asyncio.get_running_loop()
    if not _make or _make[0][0] is not loop:
        _make[:] = [(loop, asyncio.Lock())]
    return _make[0][1]


async def call(path, body=None, timeout=JOB_SECONDS):
    """One request to musik_server on the model computer (common.model_url, the panel's API key); (status, JSON)."""
    url = model_url("musik", path)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as c:
        if body is None:
            r = await c.get(url, headers=api_headers())
        else:
            r = await c.post(url, json=body, headers=api_headers())
    try:
        d = r.json()
    except ValueError:
        d = {}
    return r.status_code, d if isinstance(d, dict) else {}


async def make(body):
    """One song: (MP3 bytes, the service's numbers), or ValueError(why) with a key of REFUSED."""
    try:
        code, d = await call("/v1/musik", body)
    except httpx.HTTPError:
        raise ValueError("dienst")
    if code in (502, 503) and d.get("detail") in ("memory", "missing", "engine"):
        raise ValueError(d["detail"])     # 502 "engine": the engine runs but did not make the song
    if code == 504:
        raise ValueError("zeit")
    if code != 200 or not isinstance(d.get("mp3"), str) or len(d["mp3"]) > MAX_MP3 * 4 // 3 + 4:
        raise ValueError("dienst")
    try:
        mp3 = base64.b64decode(d["mp3"], validate=True)
    except ValueError:
        raise ValueError("dienst")
    if not mp3.startswith(b"ID3") or len(mp3) > MAX_MP3:
        raise ValueError("dienst")
    return mp3, d


def _body(j):
    b = {"caption": j["caption"], "seconds": j["seconds"], "lyrics": j["lyrics"], "language": j["language"],
         "title": (j["wish"] or j["caption"])[:120], "seed": -1}
    if j.get("model"):
        b["variant"] = j["model"]
    return b


async def _work(j):
    import vorrang
    await vorrang.quiet("Musik machen")
    async with _make_lock():
        await vorrang.quiet("Musik machen")
        if wartung.paused("musik"):
            _fail(j, "pause")
            return
        j["state"] = "run"
        try:
            mp3, d = await make(_body(j))
        except ValueError as e:
            _fail(j, str(e) if str(e) in REFUSED else "dienst")
            return
    row = keep(j["uid"], mp3, {"wish": j["wish"], "caption": j["caption"], "lyrics": j["lyrics"], "sung": j["sung"],
                               "language": j["language"], "length_s": j["seconds"], "seconds": d.get("seconds"),
                               "model": str(d.get("variant") or j.get("model") or "")[:10], "src": j["src"],
                               "job": j["id"]})
    j.update(state="done", song=row, end=time.time())
    _recent[j["uid"]] = time.time()   # „geht das auch als Reggae?“ after listening is still a follow-up
    _count.bump("done")
    import verbrauch   # Verbrauchszähler: one song and its time (does nothing while the counter is off)
    verbrauch.add("musik", "Musik machen", who=j["uid"], amount=1, ms=int((d.get("seconds") or 0) * 1000))
    kind = "gesang" if j["sung"] else "instrumental"
    _live(f"Lied {j['seconds']} s {kind} gemacht")
    print(f"musik: gemacht {j['seconds']} s {kind} {d.get('seconds')} s fuer {j['log']}", flush=True)
    try:
        import tagebuch
        tagebuch.note(j["uid"], "musik", "Lied: " + (j["wish"] or j["caption"])[:70], ref=row["id"])
    except Exception:
        pass
    if j["client"] != "web":
        try:
            import push
            await push.send(j["uid"], "Lied fertig", "Dein Lied liegt unter Ich → Musik.", tag="musik", why="Musik")
        except Exception as e:   # noqa: BLE001 - the song is there anyway
            print("musik: hinweis nicht gesendet", type(e).__name__, flush=True)


# ---------------------------------------------------------------- the assistant
def wants(text):
    """The person's own message asks to make music (the wish words, never „spiel …“): chat_turn keeps the last
    answer from outside text as data for it, so chords or a style named there can go into the description."""
    words = str(text or "")[:2000]
    return bool(WORDS.search(words)) and not (PLAY.search(words) and not re.search(r"(?i)komponier|compose", words))


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp":
        return None
    uid = who["id"]
    words = str(ctx.get("text") or "")
    asked = wants(words)
    before = str(ctx.get("before") or "")
    # the window counts from the last wish, the start and the end of a song; the last answer about a song counts too
    recent = time.time() - _recent.get(uid, 0) < FOLLOW_SECONDS or bool(SONG.search(before))
    again = recent and not PLAY.search(words) and (bool(AGAIN.search(words)) or len(words) <= YES_MAX and bool(YES.search(words)))
    if not asked and not again:
        # about a song, but no wish: no tool, and the model must not promise one (eine Zusage ohne Werkzeug)
        if recent and ABOUT.search(words) and features.allowed(KEY, uid):
            return {"tools": [], "hint": NO_PROMISE}
        return None
    if asked:
        _recent[uid] = time.time()   # the wish itself: the assistant may ask back, the answer still makes the song
    if not features.allowed(KEY, uid):
        return {"tools": [], "hint": off_hint(uid)} if asked else None
    # own: the person's own words ask for the song, so an answer from outside text before (a web search about a
    # synthesizer, chords) does not lock it; that answer stays data for the description (Dominik 2026-10-16)
    return {"tools": [TOOL], "hint": HINT, "changes": {"musik_machen"}, "keep": {"musik_machen"}, "own": {"musik_machen"},
            "filler": {"musik_machen": ("Ich mache das Lied.", "Making the song.")}}


async def tool(name, args, ctx):
    who = ctx.get("who") or {}
    if name != "musik_machen" or not who.get("id"):
        return "Not done: unknown tool."
    args = args if isinstance(args, dict) else {}
    client = ctx.get("client") or "web"
    sung = args.get("gesang") is True
    try:
        j = start(who, args.get("beschreibung_en"), args.get("wunsch"), args.get("sekunden"), sung,
                  str(args.get("sprache") or ""), str(args.get("liedtext") or ""), "chat", client)
    except ValueError as e:
        de = e.args[0][0] if e.args and isinstance(e.args[0], tuple) else "Das ging nicht."
        return f"Not done: {de} Sag das so in einem Satz und beschreibe kein Lied."
    if client in ("", "web") and ctx.get("out") is not None:   # the panel's chat shows it (the apps: Ich → Musik and a push)
        await ctx["out"].put({"type": "musik", "job": j["id"], "caption": j["caption"]})
        where = "Es erscheint gleich hier im Chat und unter Ich → Musik."
    else:
        where = "Es liegt gleich unter Ich → Musik; der Spark sagt Bescheid."
    kind = "with singing" if sung else "instrumental"
    return (f"Started: a {j['length_s']} s song, {kind}, is being made on the Spark. Tell the user in one short "
            f"sentence that you are making it. {where} Do not describe how it sounds.")


# ---------------------------------------------------------------- routes
def _prof(request, prof):
    if not features.allowed(KEY, prof["id"]):
        raise HTTPException(403, "Musik machen ist aus (Funktionen → Musik machen)")
    return prof


@router.get("/api/musik", dependencies=[Depends(assistant)])
def musik_list(request: Request, prof=Depends(own_profile)):
    uid = _prof(request, prof)["id"]
    guard.limit(request, "musik", uid)
    return {"songs": [public(x) for x in all_songs(uid)], "jobs": jobs_of(uid), "limits": limits(),
            "used": used_bytes(uid), "today": today_count(uid), "langs": list(LANGS)}


@router.post("/api/musik", dependencies=[Depends(assistant)])
async def musik_make(request: Request, prof=Depends(browser_profile)):
    """Ich → Musik: the person's own description, the length and, for singing, the language and the lyrics."""
    uid = _prof(request, prof)["id"]
    guard.limit(request, "musikmachen", uid)
    body = await json_body(request, 16 * 1024, lenient=True)
    wish = clean(body.get("wunsch"), MAX_WISH)
    sung = body.get("gesang") is True
    try:
        return start(prof, wish, wish, body.get("sekunden"), sung, str(body.get("sprache") or ""),
                     str(body.get("liedtext") or ""), "seite", "web")
    except ValueError as e:
        raise HTTPException(409, e.args[0][0] if e.args and isinstance(e.args[0], tuple) else "geht nicht")


@router.get("/api/musik/job/{jid}", dependencies=[Depends(assistant)])
def musik_job(jid: str, request: Request, prof=Depends(own_profile)):
    uid = _prof(request, prof)["id"]
    guard.limit(request, "musikjob", uid)
    j = _jobs.get(jid)
    if j and j["uid"] == uid:
        return job_public(j)
    # a finished job the panel already forgot (an hour later, after a restart): the kept song names its job, so an
    # answer in the chat finds its song again on every device
    s = next((x for x in all_songs(uid) if ID.fullmatch(jid) and x.get("job") == jid), None)
    if not s:
        raise HTTPException(404, "kein solcher Auftrag")
    return {"id": jid, "state": "done", "error": "", "error_en": "", "song": public(s), "caption": s.get("caption", ""),
            "t0": int(s.get("t") or 0), "length_s": s.get("length_s"), "sung": bool(s.get("sung"))}


@router.get("/api/musik/{sid}/datei", dependencies=[Depends(assistant)])
def musik_file(sid: str, request: Request, dl: int = 0, prof=Depends(own_profile)):
    uid = _prof(request, prof)["id"]
    guard.limit(request, "musikdatei", uid)
    p = song_path(uid, sid)
    if not p:
        raise HTTPException(404, "kein solches Lied")
    with open(p, "rb") as f:
        data = f.read(MAX_MP3 + 1)
    if len(data) > MAX_MP3 or not data.startswith(b"ID3"):
        raise HTTPException(404, "kein solches Lied")
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "default-src 'none'", "Referrer-Policy": "no-referrer"}
    if dl:
        headers["Content-Disposition"] = f'attachment; filename="spark-lied-{sid}.mp3"'
    return Response(data, media_type="audio/mpeg", headers=headers)


@router.delete("/api/musik/{sid}", dependencies=[Depends(assistant)])
def musik_delete(sid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    guard.limit(request, "musik", uid)
    if not ID.fullmatch(sid) or not delete(uid, sid):
        print(f"musik: nicht geloescht unbekannt fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "kein solches Lied")
    print(f"musik: geloescht 1 fuer {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


@router.delete("/api/musik", dependencies=[Depends(assistant)])
def musik_clear(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "musik", prof["id"])
    n = clear(prof["id"])
    print(f"musik: geloescht {n} fuer {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "deleted": n}


# ---------------------------------------------------------------- admin: Musik testen (stage M0, measuring)
# the two fixed songs: what they are, the description, length, lyrics, language; nothing from a person or a model
TESTS = (
    {"n": 1, "name": ("Instrumental, 30 s", "Instrumental, 30 s"), "caption": "calm piano piece with soft strings, warm",
     "seconds": 30, "lyrics": "", "language": "", "title": "Musik testen 1"},
    {"n": 2, "name": ("Lied mit deutschem Gesang, 60 s", "Song with German vocals, 60 s"),
     "caption": "cheerful german pop song, female vocals, acoustic guitar, upbeat",
     "seconds": 60, "language": "de", "title": "Musik testen 2",
     "lyrics": "[verse]\nDer Morgen kommt, die Sonne lacht,\nich hab an dich gedacht die ganze Nacht.\n"
               "[chorus]\nHeute ist ein guter Tag,\nweil ich alles mag, was ich mag."},
)
REASONS = ("missing", "memory", "engine", "zeit", "dienst", "pause")
_run = {"run": False, "done": 0, "total": 0, "t": 0}
_task = []


def _state(name):
    return os.path.join(STATE, name)


def _test_file():
    return _state("musik-test.json")


def mp3_file(v, n):
    """The MP3 of fixed song n (1 or 2) of variant v, written out in full so the register dateien.py finds each name."""
    first = int(n) == 1
    if v == "xl":
        return _state("musik-test-xl-1.mp3") if first else _state("musik-test-xl-2.mp3")
    if v == "2b-klein":
        return _state("musik-test-2b-klein-1.mp3") if first else _state("musik-test-2b-klein-2.mp3")
    return _state("musik-test-2b-1.mp3") if first else _state("musik-test-2b-2.mp3")


def last_test():
    try:
        with open(_test_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("runs"), list) else None
    except (OSError, ValueError):
        return None


async def health():
    """The service's state and numbers, {"status": "off_install"} when not installed, {"status": "down"} when it
    does not answer."""
    if not cfg().get("enabled"):
        return {"status": "off_install"}
    try:
        code, d = await call("/health", timeout=5)
    except httpx.HTTPError:
        return {"status": "down"}
    return d if code == 200 else {"status": "down"}


async def _measure(variants):
    t0 = time.time()
    res = {"t": round(t0), "ok": False, "runs": []}
    try:
        for v in variants:
            run = {"variant": v, "tests": []}
            try:   # the engine ends first, so the first song of each model counts its loading too
                await call("/v1/musik/stop", {}, timeout=30)
            except httpx.HTTPError:
                pass
            for test in TESTS:
                row = {"n": test["n"], "ok": False, "why": ""}
                if wartung.paused("musik"):
                    row["why"] = "pause"
                elif not cfg().get("enabled"):
                    row["why"] = "missing"
                else:
                    body = {k: test[k] for k in ("caption", "seconds", "lyrics", "language", "title")}
                    body.update(seed=42, variant=v)
                    try:
                        async with _make_lock():
                            mp3, d = await make(body)
                        with open(mp3_file(v, test["n"]), "wb") as f:
                            f.write(mp3)
                        row.update(ok=True, **{k: d.get(k) for k in ("seconds", "lm_s", "synth_s", "peak_gib", "length_s")})
                        row["kb"] = len(mp3) // 1024
                    except ValueError as e:
                        row["why"] = str(e) if str(e) in REASONS else "dienst"
                    except OSError:
                        row["why"] = "dienst"
                print(f"musik: test {v} {row['n']}", "ok" if row["ok"] else "nicht ok " + row["why"],
                      f"{row.get('seconds') or 0} s", flush=True)
                run["tests"].append(row)
                _run["done"] += 1
            res["runs"].append(run)
        res["ok"] = bool(res["runs"]) and all(r["ok"] for run in res["runs"] for r in run["tests"])
        res["total_s"] = round(time.time() - t0, 1)
        res["health"] = await health()
        try:
            write_json(_test_file(), res)
        except OSError:
            print("musik: test nicht gespeichert", flush=True)
    finally:
        _run["run"] = False


def for_live():
    """Live-Übersicht: switched on, songs running and waiting, made, failed and refused today, and how many songs
    of the last measurement came out (numbers only)."""
    last = last_test() or {}
    rows = [r for run in last.get("runs") or [] for r in run.get("tests") or []]
    try:
        on = admin_on()
    except Exception:
        on = False
    return dict(stats(), on=on, installed=bool(cfg().get("enabled")), test_run=_run["run"],
                test_ok=sum(1 for r in rows if r.get("ok")), test_total=len(rows))


def view():
    return {"run": _run["run"], "done": _run["done"], "total": _run["total"], "last": last_test(), "model": model(),
            "variants": [[k, de, en] for k, (de, en) in VARIANTS.items()],
            "tests": [{"n": t["n"], "name": {"de": t["name"][0], "en": t["name"][1]}} for t in TESTS]}


@router.get("/api/admin/musik-test", dependencies=[Depends(auth)])
async def musik_test_get():
    return dict(view(), health=await health())


@router.post("/api/admin/musik-test", dependencies=[Depends(auth)])
async def musik_test_run(request: Request):
    """Starts the measurement of every installed model (only one at a time); the page asks GET for the rest."""
    guard.limit(request, "musiktest", None, True)
    h = await health()
    variants = [v for v in (h.get("installed") or []) if v in VARIANTS] or [h.get("variant") or "2b"]
    if not _run["run"]:
        _run.update(run=True, done=0, total=len(variants) * len(TESTS), t=time.time())
        print(f"musik: test gestartet {len(variants)} modelle", flush=True)
        _task[:] = [asyncio.create_task(_measure([v for v in variants if v in VARIANTS]))]
    else:
        print("musik: test laeuft schon", flush=True)
    return dict(view(), health=h)


@router.get("/api/admin/musik-test/{v}/{n}.mp3", dependencies=[Depends(auth)])
def musik_test_mp3(v: str, n: int, request: Request):
    guard.limit(request, "musikdatei", None, True)
    if v not in VARIANTS or n not in [t["n"] for t in TESTS] or not os.path.isfile(mp3_file(v, n)):
        raise HTTPException(404, "Noch kein Probestück")
    with open(mp3_file(v, n), "rb") as f:
        data = f.read(MAX_MP3 + 1)
    if len(data) > MAX_MP3:
        raise HTTPException(404, "Noch kein Probestück")
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "no-store",
                                                             "Content-Disposition": f'inline; filename="musik-test-{v}-{n}.mp3"'})
