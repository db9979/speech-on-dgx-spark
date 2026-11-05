"""YouTube als Quelle (plan open-notebook, Stufe 3b): the sound track of a YouTube video the person names becomes a
recording that the Spark transcribes like an uploaded one (abschrift.py, Stufe 3a).

- In: only an address the person gives herself, through Links als Dokument (doklink.py: the field „Link hinzufügen“
  under Ich → Dokumente, the endpoint POST /api/profile/docs/link, the tool link_als_dokument with an address that
  stands word for word in her own message), never one from a page, a mail, a search result or the model. doklink sends
  an address here when video_id finds a video in it and docyoutube is released for the profile; the address is then
  built anew from the video id alone (kanonisch), so nothing else of it reaches yt-dlp. No playlist, no live stream.
- yt-dlp (Unlicense) exactly in the version of app/requirements-ytdlp.lock (VERSION, the wheel's SHA-256), alone in its
  own environment (VENV, install.sh --youtube, pip --no-deps --require-hashes); without it nothing is tried and the
  link says so with the way (wort "ytdlp"). It is started without a shell, isolated (python -I, a fixed small
  environment without proxy variables, its own empty folder as home), only with the fixed options of FEST: no config
  files, no plugins, no cookies, no cache, no JavaScript runtime, no remote components, no ffmpeg (an empty folder as
  its place, --fixup never, the own downloader), only the YouTube extractor, only the sound track (FORMAT), with
  --max-filesize. Nothing it gets is chosen by the person or by outside text except the 11 signs of the video id.
- Its whole traffic goes through the netguard proxy (netproxy.py) of this one run: only CONNECT to port 443 of the
  hosts of the fixed list (erlaubt: HOSTS and the media servers GOOGLEVIDEO), every name through netguard.resolve
  (public addresses only, the Notaus), at most chat.doc_audio_mb + EXTRA_MB from the servers.
- First a look without download (-J): the video id must be the one asked for, no live stream or premiere, the length
  at most chat.doc_audio_min; then the download of the sound track (HOLEN_S at most). The file goes through
  abschrift.aufnehmen like an upload (the first bytes, size, ffprobe length, waiting queue, quota, the second login
  step) and is transcribed in quiet minutes with its time marks. Title and channel are only data: cut, without control
  or markup signs, as the name of the document (titel · kanal); herkunft "yt:<id>" keeps one video once.

Journal: „ytquelle: …“ (logfilter area wissen), fixed words and numbers only, never an address, a title or what
yt-dlp writes (its error text is only matched against fixed patterns, FEHLER).
"""
import asyncio
import glob
import json
import os
import re
import shutil
import secrets
import time
from urllib.parse import parse_qs, urlsplit

import documents
import features
import netproxy
import profiles
from common import DayCounter, PREFIX

VERSION = "2026.10.26"           # the same as app/requirements-ytdlp.lock (tests/test_ytquelle.py)
LIZENZ = "Unlicense"
VENV = os.path.join(PREFIX, "venv-ytdlp")
INSTALL = "sudo ./install.sh --youtube"
WEG = "Funktionen → YouTube-Links abschreiben"
# the addresses a video link may have (doklink: the field and the tool); everything else is an ordinary link
EINGANG = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"})
ID = re.compile(r"[A-Za-z0-9_-]{11}")
PFAD = re.compile(r"/(?:shorts|live|embed|v)/([A-Za-z0-9_-]{11})/?")
# the proxy's fixed list: YouTube's pages and API, its pictures, and the media servers (rrN---sn-….googlevideo.com)
HOSTS = frozenset({"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be", "consent.youtube.com",
                   "youtubei.googleapis.com", "i.ytimg.com"})
GOOGLEVIDEO = re.compile(r"[a-z0-9-]{1,63}\.googlevideo\.com")
FORMAT = "bestaudio[protocol^=http]"
ARTEN = (".m4a", ".webm", ".mp4", ".ogg", ".opus", ".mp3")   # what yt-dlp's sound track may be (all in abschrift.AUDIO)
FEST = ("--ignore-config", "--no-plugin-dirs", "--no-js-runtimes", "--no-remote-components", "--no-cookies",
        "--no-cookies-from-browser", "--no-cache-dir", "--no-playlist", "--use-extractors", "youtube", "--no-exec",
        "--fixup", "never", "--downloader", "native", "--socket-timeout", "20", "--retries", "2",
        "--fragment-retries", "2", "--quiet", "--no-warnings", "--no-progress", "--no-mtime", "--no-write-info-json",
        "--no-write-thumbnail", "--no-write-subs", "--no-write-auto-subs", "--no-write-comments",
        "--no-write-description", "-f", FORMAT)
EXTRA_MB = 30                    # bytes from the servers beyond the sound track (pages, the player's data)
INFO_S = 90                      # seconds for the look without download
HOLEN_S = 1800                   # seconds for the download
INFO_MOST = 16 * 1024**2         # bytes of the look's JSON
ERR_MOST = 64 * 1024             # bytes of yt-dlp's error text kept to match FEHLER
# the fixed words of this way (doklink keeps them in dl_link.fehler): ytdlp (not installed or another version), video
# (gone, private, age or region), live, laenge, format (no sound track to fetch), host (yt-dlp wanted a host outside
# the list), schritt (the second login step is due); netproxy's and netguard's words besides (notaus, privat, groesse,
# zeit, netz, doppelt, warteschlange, speicher)
WORTE = ("ytdlp", "video", "live", "laenge", "format", "host", "schritt")
FEHLER = ((re.compile(r"(?i)\bmax-filesize\b|\blarger than\b"), "groesse"),
          (re.compile(r"(?i)\brequested format is not available\b|\bno (video|audio) formats\b"), "format"),
          (re.compile(r"(?i)\blive event\b|\bis live\b|\bpremieres? in\b"), "live"),
          (re.compile(r"(?i)\bvideo (is )?unavailable\b|\bprivate video\b|\bhas been removed\b|\bcopyright\b|"
                      r"\bnot available in your country\b|\bsign in to confirm\b|\bmembers[- ]only\b|"
                      r"\bage[- ]restricted\b|\binappropriate\b"), "video"))
# abschrift.aufnehmen's refusal -> the word of this way
VON_ABSCHRIFT = {"zweiter schritt": "schritt", "typ": "format", "keine tonspur": "format", "speicher": "speicher",
                 "warteschlange": "warteschlange", "groesse": "groesse", "laenge": "laenge"}
_day = DayCounter(geholt=0, abgelehnt=0, fehlt=0, host=0, kb=0, s=0)
_jetzt = {}                      # the run of now: {"uid"} (Live: "holt")


def _who(uid):
    return profiles.log_name(profiles.by_id(uid) or {"id": uid})


# ---------------------------------------------------------------- the address
def video_id(url):
    """The 11 signs of the video in a YouTube address (watch?v=, youtu.be/, shorts/, live/, embed/), else None."""
    try:
        u = urlsplit(str(url or "").strip())
        host, port = (u.hostname or "").rstrip("."), u.port
    except ValueError:
        return None
    if u.scheme.lower() not in ("http", "https") or host not in EINGANG or "@" in u.netloc or port not in (None, 80, 443):
        return None
    if host == "youtu.be":
        m = re.fullmatch(r"/([A-Za-z0-9_-]{11})/?", u.path)
        return m.group(1) if m else None
    if u.path.rstrip("/") == "/watch":
        v = parse_qs(u.query).get("v") or []
        return v[0] if len(v) == 1 and ID.fullmatch(v[0]) else None
    m = PFAD.fullmatch(u.path)
    return m.group(1) if m else None


def kanonisch(vid):
    """The one address yt-dlp gets: built from the video id alone."""
    if not ID.fullmatch(vid or ""):
        raise ValueError("video id")
    return f"https://www.youtube.com/watch?v={vid}"


def herkunft(vid):
    return "yt:" + vid


def erlaubt(host):
    """The proxy's fixed list (netproxy.Proxy): exact names, and one label before .googlevideo.com."""
    return host in HOSTS or bool(GOOGLEVIDEO.fullmatch(host))


# ---------------------------------------------------------------- yt-dlp
def _site():
    got = glob.glob(os.path.join(VENV, "lib", "python3*", "site-packages", "yt_dlp", "version.py"))
    return got[0] if got else ""


def da():
    """yt-dlp is installed in its own environment, in exactly VERSION."""
    py, ver = os.path.join(VENV, "bin", "python"), _site()
    if not (os.path.isfile(py) and os.access(py, os.X_OK) and ver):
        return False
    try:
        with open(ver, encoding="utf-8") as f:
            return f"__version__ = '{VERSION}'" in f.read(4096)
    except OSError:
        return False


def befehl(vid, ordner, proxy, mb, info):
    """The fixed call (a list, no shell): FEST, the proxy, the size limit, the look (-J) or the download into ordner."""
    args = [os.path.join(VENV, "bin", "python"), "-I", "-m", "yt_dlp", *FEST, "--proxy", proxy,
            "--max-filesize", f"{int(mb)}M", "--ffmpeg-location", os.path.join(ordner, "leer")]
    args += ["-J", "--skip-download"] if info else ["-o", os.path.join(ordner, "ton.%(ext)s")]
    return args + ["--", kanonisch(vid)]


def umgebung(ordner):
    """The whole environment yt-dlp gets: no proxy variables, no config, its own folder as home."""
    return {"PATH": "/usr/bin:/bin", "HOME": ordner, "TMPDIR": ordner, "LANG": "C.UTF-8", "XDG_CONFIG_HOME": ordner,
            "XDG_CACHE_HOME": ordner}


async def _lauf(args, sekunden, out_most, ordner):
    """Runs yt-dlp; (exit code or None after the time limit, stdout up to out_most + 1, stderr up to ERR_MOST)."""
    p = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.PIPE, cwd=ordner, env=umgebung(ordner))

    async def lies(stream, most):
        buf = bytearray()
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                return bytes(buf)
            if len(buf) <= most:
                buf += chunk[:most + 1 - len(buf)]
    try:
        out, err, code = await asyncio.wait_for(asyncio.gather(lies(p.stdout, out_most), lies(p.stderr, ERR_MOST), p.wait()),
                                                sekunden)
    except asyncio.TimeoutError:
        try:
            p.kill()
        except ProcessLookupError:
            pass
        await p.wait()
        return None, b"", b""
    return code, out, err


def wort(code, err, proxy):
    """The fixed word of a failed run: the proxy's refusals first, then FEHLER on yt-dlp's text, else netz."""
    if code is None:
        return "zeit"
    for w in ("notaus", "privat", "host", "groesse", "netz"):
        if proxy.abgelehnt.get(w):
            return w
    text = err.decode("utf-8", "replace")
    return next((w for rx, w in FEHLER if rx.search(text)), "netz")


def name_of(titel, kanal, ext):
    """The document's name from title and channel (data only: one line, no control or markup signs, cut)."""
    def rein(s, most):
        s = re.sub(r"<<<|>>>|[\x00-\x1f\x7f<>\"\\/|*?:`{}\[\]]", " ", str(s or ""))
        return re.sub(r"\s+", " ", s).strip()[:most].strip()
    t, k = rein(titel, 80) or "YouTube-Video", rein(kanal, 40)
    return (f"{t} · {k}" if k else t) + ext


def pruefe_info(info, vid, mb, most_min):
    """"" when the look fits (the video asked for, no live stream, the length, the known size), else a fixed word."""
    if not isinstance(info, dict) or info.get("id") != vid or info.get("_type", "video") != "video":
        return "video"
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        return "live"
    secs = info.get("duration")
    if not isinstance(secs, (int, float)) or isinstance(secs, bool) or secs <= 0:
        return "video"
    if secs > most_min * 60:
        return "laenge"
    size = info.get("filesize") or info.get("filesize_approx") or 0
    if isinstance(size, (int, float)) and size > mb * 1024**2:
        return "groesse"
    return ""


def _aufnehmen(uid, name, path, herk):
    import abschrift
    with open(path, "rb") as f:
        doc = abschrift.aufnehmen(uid, name, f)
    documents.set_place(uid, doc["id"], herk, "")
    return doc


def _ordner(uid):
    """A fresh folder of this run inside the waiting folder of recordings (0700); leftovers of an aborted run go."""
    base = documents.audio_dir(uid)
    os.makedirs(base, mode=0o700, exist_ok=True)
    for old in glob.glob(os.path.join(base, "yt-*")):
        shutil.rmtree(old, ignore_errors=True)
    path = os.path.join(base, "yt-" + secrets.token_hex(6))
    os.makedirs(os.path.join(path, "leer"), mode=0o700)
    return path


async def holen(uid, url):
    """One YouTube link of the profile: ("ok", document) or (fixed word, None). Only called by doklink.eins for an
    address the person gave, with docyoutube released for her."""
    import abschrift
    import notaus
    who = _who(uid)

    def nein(w):
        d = _day.today()
        d["abgelehnt"] += 1
        if w == "ytdlp":
            d["fehlt"] += 1
        if w == "host":
            d["host"] += 1
        print(f"ytquelle: abgelehnt | {w} | {who}", flush=True)
        return w, None
    vid = video_id(url)
    if not vid:
        return nein("video")
    if not da():
        return nein("ytdlp")
    if notaus.refuse("internet"):
        return nein("notaus")
    herk = herkunft(vid)
    if await asyncio.to_thread(documents.by_origin, uid, "audio", herk):
        return nein("doppelt")
    if (await asyncio.to_thread(documents.audio_waiting, uid))[0] >= abschrift.WAIT_MOST:
        return nein("warteschlange")
    mb, most_min = abschrift.grenze("doc_audio_mb"), abschrift.grenze("doc_audio_min")
    ordner = await asyncio.to_thread(_ordner, uid)
    t0 = time.time()
    _jetzt["uid"] = uid
    try:
        async with netproxy.Proxy(erlaubt, (mb + EXTRA_MB) * 1024**2) as p:
            code, out, err = await _lauf(befehl(vid, ordner, p.url, mb, True), INFO_S, INFO_MOST, ordner)
            if code != 0 or len(out) > INFO_MOST:
                return nein(wort(code, err, p) if code != 0 else "video")
            try:
                info = json.loads(out.decode("utf-8", "replace"))
            except ValueError:
                return nein("video")
            w = pruefe_info(info, vid, mb, most_min)
            if w:
                return nein(w)
            code, _, err = await _lauf(befehl(vid, ordner, p.url, mb, False), HOLEN_S, 0, ordner)
            files = sorted(f for f in os.listdir(ordner) if f.startswith("ton.") and os.path.splitext(f)[1] in ARTEN
                           and os.path.isfile(os.path.join(ordner, f)) and not os.path.islink(os.path.join(ordner, f)))
            if code != 0 or not files:
                # --max-filesize ends a download that turns out larger without a file and without an error
                return nein(wort(code, err, p) if code != 0 else "groesse")
            kb = p.unten // 1024
        path = os.path.join(ordner, files[0])
        name = name_of(info.get("title"), info.get("channel") or info.get("uploader"), os.path.splitext(files[0])[1])
        try:
            doc = await asyncio.to_thread(_aufnehmen, uid, name, path, herk)
        except ValueError as e:
            return nein(VON_ABSCHRIFT.get(getattr(e, "wort", ""), "speicher"))
    finally:
        _jetzt.clear()
        await asyncio.to_thread(shutil.rmtree, ordner, True)
    d = _day.today()
    d["geholt"] += 1
    d["kb"] += kb
    d["s"] += int(time.time() - t0)
    print(f"ytquelle: geholt | {round(doc.get('secs', 0) / 60)} min {kb} kb | {who}", flush=True)
    return "ok", doc


# ---------------------------------------------------------------- what pages and Live see
def info(uid):
    """For Ich → Dokumente (doklink.info "yt"): released, installed, the limits."""
    if not features.allowed("docyoutube", uid):
        return {"on": False}
    import abschrift
    return {"on": True, "da": da(), "min": abschrift.grenze("doc_audio_min"), "mb": abschrift.grenze("doc_audio_mb")}


def for_live(now=None):
    """{"on", "da", "geholt", "abgelehnt", "fehlt", "host", "kb", "s", "laeuft"}: today's numbers, never an address."""
    if not features.admin_on("docyoutube"):
        return {"on": False}
    d = _day.today(now)
    return {"on": True, "da": da(), **{k: d[k] for k in ("geholt", "abgelehnt", "fehlt", "host", "kb", "s")},
            "laeuft": bool(_jetzt)}
