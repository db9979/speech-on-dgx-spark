"""Aufnahmen abschreiben (plan open-notebook, Stufe 3a): audio and video files become documents.

- Upload: POST /api/profile/docs/audio (the file types of AUDIO). The panel checks the content by its first bytes
  (magic: the content must be the kind its ending says), the size (chat.doc_audio_mb) before and while reading, and the
  length with ffprobe (chat.doc_audio_min) before it keeps anything. The file waits in users/<id>/docs/audio-wait/
  (0600, named by the document id, never by the uploaded name); the document is kind 'audio', source 'audio', state
  'hoeren' (documents.audio_new).
- Transcription: due_once is a link of wissen.KETTE (after the page pictures, before the Steckbrief), so it runs only in
  quiet minutes (wissen.quiet). One piece per step: ffmpeg cuts PIECE seconds (OVERLAP more at the front) as 16 kHz mono
  WAV, only from the local file (-protocol_whitelist file,pipe, fixed arguments, no shell, no name of the user in a
  command), and the Spark's own speech recognition writes it down through vorrang.run("Abschrift"): cancelled as soon
  as somebody speaks, the same piece again in the next pause. The request carries stufe.headers("hinten"): with the key
  the ASR service lets it wait behind every person and does not mark it as speech (common.SpeechMark, Fund 0.1), else
  it would stop itself and all other background work. The words at the edge that the overlap heard twice go by a fixed
  rule (trim_edge). Recordings longer than LONG_S only after wissen.long_ok (night window "Lange Dokumente nachts
  lesen"); at most chat.doc_audio_day_min minutes per profile and day (documents.count_today key "abschrift").
  While the Dienst-Wächter sees the speech recognition gone (dienstwacht.down("asr")) nothing is tried.
- Every piece is pieces of the document with its start second as page: wissen.where says "Aufnahme: Name, bei 12:30",
  the text view and hits show the time and play the kept sound track there. At the end: with "Originale aufbewahren"
  only the sound track stays (Opus KEEP_KBIT kbit/s in docs/files/<id>.ogg within the quota), else the file is
  deleted; then the document is 'ready' and goes on like any other (Steckbrief, Auswertungen, vectors, Mappen).
- The transcript is outside text (what is said in a recording is never an instruction): it is searched as data like
  any document (chat.READS_OUTSIDE), never learned into the memory.

    POST /api/profile/docs/audio                  {file}  a recording (multipart), only with the release
    POST /api/profile/wissen/{doc}/abschrift/stop "Abbrechen": keeps what is written, without text the document goes

Off until the admin allows it (Funktionen → Eigene Dokumente → Aufnahmen abschreiben), then for every profile the admin
did not block; guests never. Journal: „abschrift: …" (logfilter area wissen), fixed words and numbers only.
"""
import asyncio
import json
import os
import re
import secrets
import subprocess
import time

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

import documents
import features
import guard
import profiles
from common import DayCounter, fester_ordner, load_config, model_url
from core import assistant, browser_profile

router = APIRouter()
AUDIO = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac", ".webm", ".mp4", ".mov", ".mkv")
# the content an ending must have (magic): the family of the first bytes
FAMILY = {".mp3": "mp3", ".aac": "aac", ".m4a": "mp4", ".mp4": "mp4", ".mov": "mp4", ".wav": "wav", ".ogg": "ogg",
          ".opus": "ogg", ".flac": "flac", ".webm": "mkv", ".mkv": "mkv"}
PIECE = 30               # seconds per piece (the page of a piece is its start second)
OVERLAP = 1              # seconds heard twice at the front of a piece; trim_edge takes the doubled words out
EDGE_WORDS = 8           # words at the edge compared with the end of the piece before
LONG_S = 20 * 60         # longer recordings only after wissen.long_ok
KEEP_KBIT = 32           # the kept sound track (Opus, about 14 MB per hour)
WAIT_MOST = 5            # recordings per profile waiting for their transcription
TRIES = 3                # a piece the speech recognition refuses this often is left out
HOLD_S = 300             # after a failed request to the speech recognition: the next try after this long
ASR_TIMEOUT = 120
WAV_MOST = 2 * 1024**2   # one cut piece (31 s of 16 kHz mono 16 bit is about 1 MB)
# chat.doc_audio_mb, chat.doc_audio_min, chat.doc_audio_day_min: (default, lowest, highest); config.default.json holds
# the defaults, admin.validate the bounds
GRENZEN = {"doc_audio_mb": (300, 10, 1000), "doc_audio_min": (180, 5, 600), "doc_audio_day_min": (240, 10, 1440)}
ID = re.compile(r"[0-9a-f]{12}")
_day = DayCounter(angenommen=0, abgelehnt=0, stuecke=0, sekunden=0, fertig=0, abgebrochen=0, fehler=0, asr=0, grenze=0)
_hold = {"asr": 0.0}     # until when nothing is sent to the speech recognition (it failed, or the Dienst-Wächter)
_said = {}               # what was written to the journal once: ("grenze", uid) -> day, "asr" -> until
_tries = {}              # (uid, doc, start) -> failed tries of one piece (memory only)
_now = {}                # the recording being transcribed right now: {"uid", "doc"} (Ich → Dokumente shows it)


def _chat():
    return load_config().get("chat", {})


def admin_on():
    return features.admin_on("docaudio")


def grenze(key, c=None):
    c = _chat() if c is None else c
    d, lo, hi = GRENZEN[key]
    v = c.get(key, d)
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else d


def max_bytes():
    return grenze("doc_audio_mb") * 1024**2


def _who(uid):
    return profiles.log_name(profiles.by_id(uid) or {"id": uid})


# ---------------------------------------------------------------- checking a file
def family(head):
    """What the first bytes say a file is ("wav", "ogg", "flac", "mkv", "mp4", "aac", "mp3"), else None."""
    head = bytes(head[:16])
    if len(head) < 4:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "mkv"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[0] == 0xFF and head[1] & 0xF6 == 0xF0:      # ADTS: sync, layer 00
        return "aac"
    if head[:3] == b"ID3" or head[0] == 0xFF and head[1] & 0xE0 == 0xE0 and head[1] & 0x06:   # MPEG audio, layer set
        return "mp3"
    return None


def fits(name, head):
    """The ending is a recording and the content is what the ending says (an ID3 tag may lead an AAC file too)."""
    ext = os.path.splitext(str(name or "").lower())[1]
    want, got = FAMILY.get(ext), family(head)
    return bool(want) and (got == want or want == "aac" and got == "mp3" and bytes(head[:3]) == b"ID3")


def _cmd(args, timeout, out_most=WAV_MOST):
    """A fixed ffmpeg/ffprobe call without a shell in a fixed folder; (exit code, stdout bytes up to out_most)."""
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, cwd=fester_ordner(), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return 1, b""
    return p.returncode, p.stdout[:out_most + 1]


def laenge(path):
    """Seconds of the sound in a local file (ffprobe), None without a sound track or when it cannot be read."""
    code, out = _cmd(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams", "a",
                      "-show_entries", "stream=codec_type:format=duration", "-of", "json", "file:" + path], 60, 64 * 1024)
    if code != 0:
        return None
    try:
        d = json.loads(out.decode("utf-8", "replace"))
        if not any(s.get("codec_type") == "audio" for s in d.get("streams") or []):
            return None
        secs = float((d.get("format") or {}).get("duration"))
    except (ValueError, TypeError, AttributeError):
        return None
    return secs if 0 < secs < 10**6 else None


def schneiden(path, start, secs):
    """secs seconds of sound from start on as 16 kHz mono WAV (bytes), b"" when ffmpeg failed."""
    code, out = _cmd(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe",
                      "-ss", f"{max(0.0, float(start)):.3f}", "-t", f"{max(0.5, float(secs)):.3f}", "-i", "file:" + path,
                      "-vn", "-sn", "-dn", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"], 120)
    return out if code == 0 and 44 < len(out) <= WAV_MOST else b""


def tonspur(path, dst, secs):
    """The kept sound track: Opus KEEP_KBIT kbit/s mono in an Ogg file; True when it was written."""
    code, _ = _cmd(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe", "-y",
                    "-i", "file:" + path, "-t", str(int(secs) + 5), "-vn", "-sn", "-dn", "-ac", "1", "-c:a", "libopus",
                    "-b:a", f"{KEEP_KBIT}k", "-f", "ogg", "file:" + dst], 1800, 0)
    return code == 0 and os.path.isfile(dst) and os.path.getsize(dst) > 0


# ---------------------------------------------------------------- the words at the edge
def _w(word):
    return re.sub(r"[^\w]", "", word.lower())


def trim_edge(before, text):
    """The new piece without the words the overlap heard twice: the longest run of words (at most EDGE_WORDS) that ends
    the piece before and begins this one is taken out of this one (fixed rule, compared without case and signs)."""
    old, new = str(before or "").split(), str(text or "").split()
    for k in range(min(EDGE_WORDS, len(old), len(new)), 0, -1):
        a, b = [_w(x) for x in old[-k:]], [_w(x) for x in new[:k]]
        if a == b and any(a):
            return " ".join(new[k:])
    return " ".join(new)


# ---------------------------------------------------------------- upload
COPY = 1024**2          # bytes copied at a time from the received upload into the waiting file


def aufnehmen(uid, name, src):
    """Checks and keeps one recording (in a worker thread). src: the received file (bytes or a file object, read at most
    max_bytes() + 1 bytes, in parts, never all into memory). Returns the new document; ValueError with a fixed sentence."""
    import io
    src = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src
    head = src.read(16)
    import wissen
    import join
    who = _who(uid)

    def nein(why, de):
        _day.today()["abgelehnt"] += 1
        print(f"abschrift: abgelehnt | {why} | {who}", flush=True)
        e = ValueError(de)
        e.wort = why             # the fixed word for a caller (ytquelle.VON_ABSCHRIFT)
        raise e
    if join.mfa_due(uid):
        nein("zweiter schritt", "Erst den zweiten Anmeldeschritt einrichten (Ich → Sicherheit), dann Aufnahmen ablegen.")
    if not fits(name, head):
        nein("typ", "Das ist keine Ton- oder Videodatei der erlaubten Arten, oder der Inhalt passt nicht zur Endung.")
    if documents.usage_total(uid) >= wissen.quota_bytes(uid):
        nein("speicher", f"Der Platz für Dokumente ist voll ({wissen.quota_bytes(uid) // 1024**2} MB).")
    if documents.audio_waiting(uid)[0] >= WAIT_MOST:
        nein("warteschlange", f"Schon {WAIT_MOST} Aufnahmen warten auf ihre Abschrift; erst danach weitere.")
    doc_id = secrets.token_hex(6)
    ext = os.path.splitext(name.lower())[1]
    folder = documents.audio_dir(uid)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    path = os.path.join(folder, doc_id + ext)
    size, most = len(head), max_bytes()
    try:
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(head)
            while size <= most:
                part = src.read(min(COPY, most + 1 - size))
                if not part:
                    break
                f.write(part)
                size += len(part)
        if size > most:
            nein("groesse", f"Die Aufnahme ist größer als {grenze('doc_audio_mb')} MB.")
        secs = laenge(path)
        if secs is None:
            nein("keine tonspur", "In der Datei ist keine lesbare Tonspur.")
        if secs > grenze("doc_audio_min") * 60:
            nein("laenge", f"Die Aufnahme ist länger als {grenze('doc_audio_min')} Minuten.")
        documents.audio_new(uid, doc_id, name, size, int(secs + 0.999))
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    _day.today()["angenommen"] += 1
    print(f"abschrift: angenommen | {round(secs / 60)} min | {who}", flush=True)
    return {"id": doc_id, "name": documents.file_name(name, "Aufnahme"), "state": "hoeren", "kind": "audio",
            "secs": int(secs + 0.999)}


# ---------------------------------------------------------------- the quiet chain
async def hoeren(wav, uid=None):
    """The speech recognition's text of one piece (tests replace this). Stage "hinten" with the panel's key."""
    import httpx
    import stufe
    import verbrauch
    from core import api_headers
    cfg = load_config()
    async with httpx.AsyncClient(timeout=httpx.Timeout(ASR_TIMEOUT, connect=5)) as c:
        r = await c.post(model_url("asr", "/v1/audio/transcriptions", cfg), files={"file": ("teil.wav", wav)},
                         data={"language": "auto", "response_format": "json"},
                         headers=dict(api_headers(), **stufe.headers("hinten")))
    verbrauch.heard("Abschrift", r, uid)
    r.raise_for_status()
    return str(r.json().get("text", "")).strip()[:20000]


def _file(uid, doc):
    got = documents._wait_files(uid, doc, documents.audio_dir(uid))
    return got[0] if got else None


def _fertig(uid, doc, path, secs):
    """The end of a transcription (worker thread): the sound track kept or the file gone, the document ready."""
    import wissen
    stored, note = "", ""
    if path and wissen.on(uid, "originals"):
        dst = os.path.join(documents._files(uid), doc + ".ogg")
        os.makedirs(documents._files(uid), mode=0o700, exist_ok=True)
        tmp = dst + ".tmp"
        if tonspur(path, tmp, secs) and documents.usage(uid) + os.path.getsize(tmp) <= wissen.keep_bytes(uid):
            os.chmod(tmp, 0o600)
            os.replace(tmp, dst)
            stored = doc + ".ogg"
        else:
            note = "Tonspur nicht aufbewahrt: Speicher voll oder nicht lesbar"
        try:
            os.remove(tmp)
        except OSError:
            pass
    documents.audio_done(uid, doc, stored, note)
    documents._drop_wait(uid, doc)
    return bool(stored)


async def stueck(uid, doc, secs, heard, now):
    """One piece of one recording. Returns "stueck", "fertig", "abgebrochen", "asr" or "fehler"."""
    import live
    import vorrang
    who = _who(uid)
    path = await asyncio.to_thread(_file, uid, doc)
    if not path:
        await asyncio.to_thread(documents.audio_done, uid, doc, "", "Aufnahme fehlt")
        _day.today()["fehler"] += 1
        print(f"abschrift: fehler | datei fehlt | {who}", flush=True)
        return "fehler"
    start = int(heard)
    if start >= secs:
        kept = await asyncio.to_thread(_fertig, uid, doc, path, secs)
        _day.today()["fertig"] += 1
        print(f"abschrift: fertig | {round(secs / 60)} min | tonspur {'ja' if kept else 'nein'} | {who}", flush=True)
        return "fertig"
    front = OVERLAP if start else 0
    took = min(PIECE, secs - start)
    t0 = time.time()
    wav = await asyncio.to_thread(schneiden, path, start - front, took + front)
    key = (uid, doc, start)
    text = ""
    if wav:
        _now.update(uid=uid, doc=doc)
        try:
            text = await vorrang.run("Abschrift", lambda: hoeren(wav, uid), retries=0)
        except vorrang.Busy:
            _day.today()["abgebrochen"] += 1
            print(f"abschrift: abgebrochen | sprache | bei {start} s | {who}", flush=True)
            return "abgebrochen"
        except Exception as e:   # noqa: BLE001  the speech recognition is gone or refused this piece
            import httpx
            gone = isinstance(e, (httpx.TransportError, OSError)) or getattr(getattr(e, "response", None), "status_code", 0) >= 500
            if gone:             # a missing service never costs a piece: it waits and the same piece comes again
                _hold["asr"] = now + HOLD_S
                _day.today()["asr"] += 1
                print(f"abschrift: asr fehlt | {type(e).__name__} | naechster versuch in {HOLD_S} s", flush=True)
                live.bg_done("Abschrift", False, time.time() - t0, "Spracherkennung fehlt")
                return "asr"
            _tries[key] = _tries.get(key, 0) + 1
            if _tries[key] < TRIES:
                _day.today()["fehler"] += 1
                print(f"abschrift: fehler | {type(e).__name__} | versuch {_tries[key]} | {who}", flush=True)
                return "fehler"
            print(f"abschrift: stueck uebersprungen | bei {start} s | {TRIES} versuche | {who}", flush=True)
        finally:
            _now.clear()
    else:
        print(f"abschrift: stueck uebersprungen | ffmpeg | bei {start} s | {who}", flush=True)
    _tries.pop(key, None)
    if text and start:
        before = await asyncio.to_thread(documents.audio_last, uid, doc)
        text = trim_edge(before, text)
    if not await asyncio.to_thread(documents.audio_piece, uid, doc, start, text, start + took):
        print(f"abschrift: weg | geloescht oder abgebrochen | {who}", flush=True)
        return "fehler"
    documents.count_today(uid, _today(now), add=int(took), key="abschrift")
    d = _day.today()
    d["stuecke"] += 1
    d["sekunden"] += int(took)
    print(f"abschrift: stueck | {int(took)} s {len(text)} zeichen | {who}", flush=True)
    if start + took >= secs:
        kept = await asyncio.to_thread(_fertig, uid, doc, path, secs)
        d["fertig"] += 1
        print(f"abschrift: fertig | {round(secs / 60)} min {int(-(-secs // PIECE))} stuecke | tonspur "
              f"{'ja' if kept else 'nein'} | {who}", flush=True)
        live.bg_done("Abschrift", True, time.time() - t0)
        return "fertig"
    return "stueck"


def _today(now):
    import wissen
    return wissen.today(now)


async def due_once(now=None):
    """KETTE (wissen.due_once, after the page pictures): one piece of one recording of one profile, only in quiet
    minutes, at most chat.doc_audio_day_min minutes per profile and day, long recordings only after wissen.long_ok."""
    if not admin_on():
        return None
    import wissen
    if not wissen.quiet():
        return None
    now = time.time() if now is None else now
    if now < _hold["asr"]:
        return None
    import dienstwacht
    if dienstwacht.down("asr"):
        if _said.get("asr", 0) < now:
            _said["asr"] = now + HOLD_S
            _day.today()["asr"] += 1
            print(f"abschrift: asr fehlt | dienstwaechter | naechster versuch in {HOLD_S} s", flush=True)
        _hold["asr"] = now + HOLD_S
        return None
    day, most = _today(now), grenze("doc_audio_day_min") * 60
    lang = wissen.long_ok(now)
    for uid in profiles.user_ids():
        if not features.allowed("docaudio", uid) or not os.path.exists(documents.db_path(uid)):
            continue
        nxt = await asyncio.to_thread(documents.audio_next, uid, None if lang else LONG_S)
        if not nxt:
            continue
        if documents.count_today(uid, day, key="abschrift") >= most:
            if _said.get(("grenze", uid)) != day:
                _said[("grenze", uid)] = day
                _day.today()["grenze"] += 1
                print(f"abschrift: grenze | {most // 60} min | {_who(uid)}", flush=True)
            continue
        doc, secs, heard = nxt
        await stueck(uid, doc, int(secs), int(heard), now)
        return "abschrift"
    return None


# ---------------------------------------------------------------- what pages and Live see
def info(uid):
    """For Ich → Dokumente (wissen.info "audio"): released, the limits, today's minutes, what is transcribed now."""
    if not features.allowed("docaudio", uid):
        return {"on": False}
    import dienstwacht
    import wissen
    now = time.time()
    return {"on": True, "types": list(AUDIO), "mb": grenze("doc_audio_mb"), "min": grenze("doc_audio_min"),
            "day_min": grenze("doc_audio_day_min"), "long_min": LONG_S // 60, "long_ok": wissen.long_ok(now),
            "today_min": documents.count_today(uid, _today(now), key="abschrift") // 60 if os.path.exists(documents.db_path(uid)) else 0,
            "now": _now.get("doc") if _now.get("uid") == uid else None,
            "asr": not (dienstwacht.down("asr") or now < _hold["asr"])}


def for_live(now=None):
    """{"on", "warten", "minuten", "stuecke", "heute_min", "fertig", "abgebrochen", "fehler", "asr", "grenze",
    "angenommen", "abgelehnt"}: recordings waiting and minutes left over all profiles, today's counts (numbers only)."""
    if not admin_on():
        return {"on": False}
    n = left = 0
    for uid in profiles.user_ids():
        try:
            a, b = documents.audio_waiting(uid)
        except Exception:   # noqa: BLE001  (a broken database counts as none, never a word of it)
            continue
        n, left = n + a, left + b
    d = _day.today(now)
    return {"on": True, "warten": n, "minuten": -(-left // 60), "stuecke": d["stuecke"], "heute_min": d["sekunden"] // 60,
            "fertig": d["fertig"], "abgebrochen": d["abgebrochen"], "fehler": d["fehler"], "asr": d["asr"],
            "grenze": d["grenze"], "angenommen": d["angenommen"], "abgelehnt": d["abgelehnt"], "laeuft": bool(_now)}


# ---------------------------------------------------------------- endpoints
def _need(uid):
    if not _chat().get("documents", True):
        raise HTTPException(403, "documents are turned off (Einstellungen -> Funktionen)")
    if not features.allowed("docaudio", uid):
        raise HTTPException(403, features.missing_text("docaudio", uid))


@router.post("/api/profile/docs/audio", dependencies=[Depends(assistant)])
async def upload(request: Request, file: UploadFile = File(...), prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "docaudio", uid)
    if features.blocked("documents", uid):
        raise HTTPException(403, "documents are blocked for this profile (Personen und Geräte → Gesperrte Funktionen)")
    try:   # the received file is copied in parts with its limit (aufnehmen), never read into memory at once
        return await asyncio.to_thread(aufnehmen, uid, file.filename or "", file.file)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/profile/wissen/{doc}/abschrift/stop", dependencies=[Depends(assistant)])
async def stop(doc: str, request: Request, prof=Depends(browser_profile)):
    """"Abbrechen" (also while the switch is off: what was uploaded can always be stopped)."""
    uid = prof["id"]
    guard.limit(request, "docaudio", uid)
    if not ID.fullmatch(doc or ""):
        raise HTTPException(404, "no such recording")
    got = await asyncio.to_thread(documents.audio_stop, uid, doc)
    if not got:
        print(f"abschrift: stopp | keine | {_who(uid)}", flush=True)
        raise HTTPException(404, "no such recording being transcribed")
    if got == "deleted":
        documents.on_gone(uid, [doc], "geloescht")
    print(f"abschrift: stopp | {'geloescht' if got == 'deleted' else 'behalten'} | {_who(uid)}", flush=True)
    return {"ok": True, "removed": got == "deleted"}
