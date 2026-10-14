"""Ablage-Ordner (plan plaene/synology-bauplan.md, S4; Dominik 2026-10-13 "S1 - S8 umsetzen").

A profile chooses one of its places in the home network (nas.py) as its filing folder: the folder "spark_ablage"
there (on a Synology a shared folder of that name with "Lesen/Schreiben" for the Spark's user, see the guide
"Synology einrichten"). Choosing it is the consent; nothing is written anywhere else, ever.

    spark_ablage/Erstellt/            what the Spark puts there: documents it made (automatically, unless the
                                      profile switched that off) and, after a plain "Ja", an own file or note
    spark_ablage/Eingang/             files the person puts there come into Ich → Dokumente like an upload
    spark_ablage/Eingang/erledigt/    ... and are moved here afterwards
    spark_ablage/Eingang/abgelehnt/   ... or here, when the upload check refuses them (kind, size, content)

    USERS_DIR/<uid>/nasablage.json  {"nas", "added", "auto", "inbox", "made", "dropped", "fetched", "refused",
                                     "last", "fail", "seen"}

Rules (fixed, never decided by the model):
- Only a place in the home network (nas.zone "lan"), only through netguard HOME with the place's login and its
  accepted certificate or server key (nasquelle's readers).
- The Spark never overwrites (a name that is there gets " (2)"), never deletes and never writes outside
  spark_ablage. Eingang only moves files into its own sub folders.
- nas_ablegen only proposes ("NOT done yet"); the panel files after a plain "Ja" in the same conversation
  (answer, calendars.confirms). Allowed is only an own thing of the profile: a document the Spark made, an upload
  with its kept original, or a short note. The tool counts as a change: after outside text in the same answer it
  is locked (extras "changes", chat.LOCKED_OUTSIDE), Notaus holds it (notaus.stop "aktion").
- Eingang: every chat.nas_drop_every minutes (5 to 1440, default 15), only in quiet minutes, never during an update
  or the Notaus; at most ROUND_FILES files per round; the same checks as an upload (wissen.add: kind, size, room,
  the admin's block of Dokumente) plus the content must fit the name (nasquelle.fits).

Zustand → Live: target "Ablage-Ordner" (live.py "nasablage", numbers only), job "Ablage-Eingang" of "Von selbst",
the tool on its way. Logs → Diagnose, area "NAS" (lines "nasablage: ..."), only fixed words and numbers, never a
path or a file name.
"""
import asyncio
import datetime
import hashlib
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import netguard
import nasquelle
import profiles
from common import load_config
import core
from core import auth, browser_profile

router = APIRouter()

DROP = "spark_ablage"
MADE = "Erstellt"
INBOX = "Eingang"
DONE = INBOX + "/erledigt"
REFUSED = INBOX + "/abgelehnt"
FOLDERS = (MADE, INBOX, DONE, REFUSED)
EVERY = 15                       # minutes (chat.nas_drop_every, 5 to 1440)
ROUND_FILES = 20                 # files taken from Eingang per round
MAX_SEEN = 500
MAX_NOTE = 20_000
PENDING_SECONDS = 15 * 60
RETRY = (600, 1800, 3600)
NAME_BAD = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")
WHY = dict(nasquelle.WHY, lesen=("nur lesbar: der Spark darf dort nicht schreiben", "read only: the Spark may not write there"),
           missing=("Ordner „spark_ablage“ fehlt", "folder \"spark_ablage\" is missing"),
           net=("nur im Heimnetz", "only in the home network"))
KINDS = {"dokument": ("ein erstelltes Dokument", "a made document"), "datei": ("ein hochgeladenes Dokument", "an uploaded document"),
         "notiz": ("eine Notiz", "a note")}
_lock = threading.RLock()
_running = set()
_pending = {}                    # uid -> {"kind", "ref", "label", "text", "src", "t"}


# ---------------------------------------------------------------- switches
def admin_on(c=None):
    return features.admin_on("nasablage", c)


def allowed(uid, c=None):
    c = features.chat_cfg() if c is None else c
    return bool(uid) and features.allowed("nasablage", uid, c)


def every():
    v = load_config().get("chat", {}).get("nas_drop_every", EVERY)
    return (v if isinstance(v, int) and not isinstance(v, bool) and 5 <= v <= 1440 else EVERY) * 60


# ---------------------------------------------------------------- the profile's setting
def _file(uid):
    return profiles._path(uid, "nasablage.json")


def get(uid):
    """The profile's filing folder or None: {"nas", "added", "auto", "inbox", counters, "last", "fail", "seen"}."""
    with _lock:
        try:
            with open(_file(uid)) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
    if not isinstance(d, dict) or not nasquelle.ID.fullmatch(str(d.get("nas", ""))):
        return None
    seen = d.get("seen") if isinstance(d.get("seen"), dict) else {}
    return {"nas": d["nas"], "added": int(d.get("added") or 0), "auto": d.get("auto") is not False,
            "inbox": d.get("inbox") is not False, **{k: int(d.get(k) or 0) for k in ("made", "dropped", "fetched", "refused")},
            "last": d.get("last") if isinstance(d.get("last"), dict) else None,
            "fail": d.get("fail") if isinstance(d.get("fail"), dict) else None,
            "seen": {k: str(v)[:12] for k, v in list(seen.items())[-MAX_SEEN:] if isinstance(k, str) and len(k) == 16}}


def _save(uid, d):
    with _lock:
        if d is None:
            try:
                os.remove(_file(uid))
            except OSError:
                pass
            return
        profiles._write(_file(uid), d)


def _bump(uid, **kw):
    with _lock:
        d = get(uid)
        if not d:
            return
        for k, v in kw.items():
            d[k] = d.get(k, 0) + v if isinstance(v, int) else v
        _save(uid, d)


def uses(uid):
    """For nas.uses: {connection id: 1}."""
    d = get(uid)
    return {d["nas"]: 1} if d else {}


def _log_name(uid):
    return profiles.log_name(profiles.by_id(uid))


def _live(name, *a, **kw):
    try:
        import live
        getattr(live, name)(*a, **kw)
    except Exception as e:   # noqa: BLE001 - the overview never stops the work
        print("nasablage: live", type(e).__name__, flush=True)


# ---------------------------------------------------------------- writing into spark_ablage (never elsewhere)
class _Place:
    """spark_ablage at a place: nasquelle's reader (listing, fetching) plus making folders, adding a file under a
    name that is not there yet and moving inside Eingang. Nothing here can delete or overwrite."""

    def __init__(self, c):
        self.c = c
        self.rd = nasquelle.reader(c, "/" + DROP)

    async def list(self, rel):
        return await self.rd.list(rel)

    async def get(self, rel, dst, most):
        await self.rd.get(rel, dst, most)

    async def close(self):
        await self.rd.close()

    # WebDAV
    async def _dav(self, method, rel, folder=False, timeout=nasquelle.TIMEOUT, **kw):
        rd = self.rd
        url = rd.base + ("/" + quote(rel) if rel else "") + ("/" if folder else "")
        try:
            async with rd._client(timeout, 64 * 1024) as cl:
                return await cl.request(method, url, auth=rd.auth, **kw)
        except (netguard.Blocked, httpx.HTTPError, OSError, netguard.TooLarge, ValueError) as e:
            raise rd._err(e)

    async def make(self):
        """spark_ablage itself (where the place lets the Spark make it) and its four sub folders."""
        if self.c["kind"] == "webdav":
            r = await self._dav("MKCOL", "", folder=True)
            if r.status_code not in (201, 405, 301, 302, 409, 403):
                raise self.rd._code(r.status_code)
            for p in FOLDERS:
                r = await self._dav("MKCOL", p, folder=True)
                if r.status_code not in (201, 405, 301, 302):
                    raise _err("missing" if r.status_code == 409 else "lesen" if r.status_code == 403 else self.rd._code(r.status_code).kind)
            return
        rd = self.rd

        def mk():
            import speicher
            if not rd._isdir(rd._at("")):
                try:
                    rd._mkdir(rd._at(""))
                except Exception:   # noqa: BLE001 - a share or a folder the user may not make: say it is missing
                    raise speicher.StoreError("other", "missing")
            for p in FOLDERS:
                at = rd._at(p)
                if not rd._isdir(at):
                    rd._mkdir(at)
        await self._run(mk)

    async def _run(self, fn, *a, timeout=nasquelle.TIMEOUT):
        import speicher
        try:
            return await self.rd._run(fn, *a, timeout=timeout)
        except speicher.StoreError as e:
            raise _err(e.kind if e.kind in nasquelle.WHY else "missing" if str(e) == "missing" else "other")

    async def names(self, rel):
        return {n for n, _, _, _ in await self.list(rel)}

    async def add(self, rel_dir, name, data):
        """Writes data as a new file in rel_dir; the name gets " (2)" ... when it is there. Returns the name."""
        for _ in range(3):
            final = free_name(name, await self.names(rel_dir))
            rel = rel_dir + "/" + final
            if self.c["kind"] == "webdav":
                r = await self._dav("PUT", rel, timeout=60 + len(data) // (256 * 1024), content=data,
                                    headers={"If-None-Match": "*", "Content-Type": "application/octet-stream"})
                if r.status_code in (200, 201, 204):
                    return final
                if r.status_code == 412:      # came in between: another name
                    continue
                if r.status_code == 403:
                    raise _err("lesen")
                raise self.rd._code(r.status_code)
            rd = self.rd

            def put():
                with rd._open(rd._at(rel), "xb") as f:    # "x": never over an existing file
                    f.write(data)
            try:
                await self._run(put, timeout=60 + len(data) // (256 * 1024))
                return final
            except nasquelle.SourceError as e:
                if e.kind != "other":
                    raise
        raise nasquelle.SourceError("other")

    async def move(self, rel, rel_dir):
        """Moves one file of Eingang into one of its sub folders, never over an existing file."""
        name = rel.split("/")[-1]
        final = free_name(name, await self.names(rel_dir))
        dst = rel_dir + "/" + final
        if self.c["kind"] == "webdav":
            r = await self._dav("MOVE", rel, headers={"Destination": self.rd.base + "/" + quote(dst), "Overwrite": "F"})
            if r.status_code not in (201, 204):
                raise _err("lesen" if r.status_code in (403, 412) else self.rd._code(r.status_code).kind)
            return final
        rd = self.rd

        def mv():
            a, b = rd._at(rel), rd._at(dst)
            if self.c["kind"] == "sftp":
                rd.conn[1].rename(a, b)          # SFTP's rename never replaces
            else:
                import smbclient
                smbclient.rename(a, b, **rd._kw())   # nor does SMB's
        await self._run(mv)
        return final


def _err(kind):
    """nasquelle's error with this module's own kinds too ("lesen", "net": WHY here)."""
    e = nasquelle.SourceError("other", kind)
    e.kind = kind if kind in WHY else "other"
    return e


def free_name(name, have):
    """name, or "name (2).ext", "name (3).ext" ... that is not in have (case does not count)."""
    low = {n.lower() for n in have}
    if name.lower() not in low:
        return name
    base, ext = os.path.splitext(name)
    for i in range(2, 1000):
        n = f"{base} ({i}){ext}"
        if n.lower() not in low:
            return n
    return f"{base} ({secrets.token_hex(3)}){ext}"


def clean_name(name, ext=""):
    n = NAME_BAD.sub("", str(name or "")).strip().strip(".")[:120] or "Spark"
    return n if not ext or n.lower().endswith(ext) else n + ext


def _conn(uid, d=None):
    import nas
    d = d or get(uid)
    c = nas.find(uid, d["nas"]) if d else None
    if not c:
        raise nasquelle.SourceError("gone")
    if nas.zone(c) != "lan":
        raise _err("net")
    return c


# ---------------------------------------------------------------- filing (after "Ja", or a made document)
async def put(uid, name, data, kind, why="ja"):
    """Puts one file into spark_ablage/Erstellt; returns the name it got. SourceError / NotausAktiv."""
    import notaus
    notaus.stop("aktion", uid)
    t0 = time.time()
    pl = _Place(_conn(uid))
    try:
        final = await pl.add(MADE, name, data)
    except nasquelle.SourceError as e:
        print(f"nasablage: ablegen fehlgeschlagen | art={e.kind} | {_log_name(uid)}", flush=True)
        _bump(uid, fail={"kind": e.kind, "since": int(time.time()), "n": 1})
        _live("job", "Ablage-Ordner", "Ablegen", t0, ok=False, uid=uid)
        raise
    finally:
        await pl.close()
    _bump(uid, **({"made": 1} if why == "auto" else {"dropped": 1}), fail=None)
    print(f"nasablage: abgelegt | {kind} | {why} | {_log_name(uid)}", flush=True)
    import tagebuch
    tagebuch.note(uid, "ablegen", final)
    _live("job", "Ablage-Ordner", "Ablegen", t0, ok=True, uid=uid)
    return final


async def after_made(uid, d):
    """docmake: a finished document goes into Erstellt too, when the profile set up a filing folder and did not
    switch "Erstellte Dokumente automatisch ablegen" off. Returns a sentence for the note, or ""."""
    a = get(uid)
    if not a or not a["auto"] or not allowed(uid):
        return ""
    import docmake
    try:
        data, name, _ = await asyncio.to_thread(docmake.build, uid, d, d["format"])
        await put(uid, clean_name(name), data, "dokument", "auto")
        return " Liegt auch im Ablage-Ordner der NAS (Erstellt)."
    except (nasquelle.SourceError, ValueError) as e:
        if not isinstance(e, nasquelle.SourceError):
            print(f"nasablage: ablegen fehlgeschlagen | art=bauen | {_log_name(uid)}", flush=True)
        return " Ablage auf der NAS ging nicht."


# ---------------------------------------------------------------- Eingang
def _seen_key(rel, size, mtime):
    return hashlib.sha256(f"{rel}\0{size}\0{mtime}".encode()).hexdigest()[:16]


def due(uid, d, now=None):
    now = now or time.time()
    if uid in _running or not d["inbox"] or not features.allowed("documents", uid):
        return False
    last = int((d["last"] or {}).get("t") or 0)
    if d["fail"]:
        return now - last > RETRY[min(len(RETRY), int(d["fail"].get("n") or 1)) - 1]
    return now - last > every()


async def inbox_once(uid, why="auto", now=None):
    """Takes new files from Eingang into Ich → Dokumente. {"ok", "fetched", "refused", "left"} or {"ok": False, "kind"}."""
    d = get(uid)
    if not d or uid in _running:
        return {"ok": False, "kind": "other"}
    if not features.allowed("documents", uid):      # where it would go is off: nothing is taken, nothing failed
        print(f"nasablage: eingang übersprungen | dokumente aus | {_log_name(uid)}", flush=True)
        return {"ok": False, "kind": "docs"}
    _running.add(uid)
    now = now or time.time()
    t0 = time.time()
    _live("bg", "Ablage-Eingang", "läuft")
    pl = None
    got = refused = 0
    try:
        import documents
        import wissen
        pl = _Place(_conn(uid, d))
        files = [(n, s, m) for n, isdir, s, m in await pl.list(INBOX)
                 if not isdir and not nasquelle.SKIP_FILES.match(n)]
        seen = d["seen"]
        for name, size, mtime in files[:ROUND_FILES]:
            rel = INBOX + "/" + name
            key = _seen_key(rel, size, mtime)
            if key in seen:                        # taken before, the move did not happen then: only move
                await pl.move(rel, DONE if seen[key] != "x" else REFUSED)
                continue
            ext = os.path.splitext(name.lower())[1]
            most = wissen.pdf_bytes() if ext == ".pdf" else documents.MAX_OTHER
            doc = ""
            if ext in documents.TYPES and 0 < size <= most:
                tmp = nasquelle._tmp()
                try:
                    await pl.get(rel, tmp, most)
                    with open(tmp, "rb") as f:
                        data = f.read(most + 1)
                finally:
                    nasquelle._rm(tmp)
                if nasquelle.fits(name, data[:4096]):
                    try:
                        doc = (await asyncio.to_thread(wissen.add, uid, name, data, None, "eingang"))["id"]
                    except (ValueError, HTTPException):
                        doc = ""
            seen[key] = doc or "x"
            _bump(uid, seen=dict(list(seen.items())[-MAX_SEEN:]))
            await pl.move(rel, DONE if doc else REFUSED)
            got, refused = got + bool(doc), refused + (not doc)
        left = max(0, len(files) - ROUND_FILES)
        _bump(uid, fetched=got, refused=refused, fail=None,
              last={"t": int(now), "ok": True, "n": got, "x": refused, "why": why})
        print(f"nasablage: eingang | {got} geholt | {refused} abgelehnt | {left} übrig | {_log_name(uid)}", flush=True)
        _live("job", "Ablage-Ordner", "Ablage-Eingang", t0, ok=True, uid=uid)
        return {"ok": True, "fetched": got, "refused": refused, "left": left}
    except nasquelle.SourceError as e:
        f = (get(uid) or {}).get("fail") or {}
        _bump(uid, fetched=got, refused=refused, fail={"kind": e.kind, "since": int(f.get("since") or now), "n": int(f.get("n") or 0) + 1},
              last={"t": int(now), "ok": False, "kind": e.kind, "why": why})
        print(f"nasablage: fehler | art={e.kind} | {_log_name(uid)}", flush=True)
        _live("job", "Ablage-Ordner", "Ablage-Eingang", t0, ok=False, uid=uid)
        return {"ok": False, "kind": e.kind}
    finally:
        _running.discard(uid)
        _live("bg", "Ablage-Eingang", None)
        if pl is not None:
            await pl.close()


async def round_once(now=None):
    now = now or time.time()
    c = features.chat_cfg()
    if not admin_on(c) or nasquelle._paused(now):
        return []
    import vorrang
    if vorrang.speaking():
        return []
    done = []
    for uid in profiles.user_ids():
        d = get(uid) if allowed(uid, c) else None
        if d and due(uid, d, now):
            await inbox_once(uid, "auto", now)
            done.append(uid)
    return done


async def loop():
    while True:
        await asyncio.sleep(60)
        try:
            await round_once()
        except Exception as e:   # noqa: BLE001 - the next minute tries again
            print("nasablage: loop", type(e).__name__, flush=True)


# ---------------------------------------------------------------- the tool nas_ablegen (proposal, then "Ja")
WORDS = re.compile(r"(?i)\b(nas|synology|diskstation|ablage-?ordner|spark_ablage)\b")
TOOL = {"type": "function", "function": {
    "name": "nas_ablegen",
    "description": "Proposes to put one of the user's own things into the filing folder on the user's NAS "
                   "(spark_ablage/Erstellt): a document the Spark made (was=dokument), an uploaded document "
                   "(was=datei) or a short note in the user's words (was=notiz with text). Nothing is written "
                   "before the user says yes. Only when the user asks for exactly that.",
    "parameters": {"type": "object", "properties": {
        "was": {"type": "string", "enum": list(KINDS)},
        "name": {"type": "string", "description": "words of the document's title; empty = the newest"},
        "text": {"type": "string", "description": "only for was=notiz: the note"}},
        "required": ["was"]}}}
HINT = ("Will der Nutzer etwas auf seine NAS legen, schlag es mit nas_ablegen vor; abgelegt wird erst nach seinem Ja. "
        "Sag nie, dass es schon liegt.")


def pending(uid):
    p = _pending.get(uid)
    return p if p and time.time() - p["t"] < PENDING_SECONDS else None


def drop_pending(uid):
    _pending.pop(uid, None)


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp":
        return None
    uid = who["id"]
    if not WORDS.search(str(ctx.get("text") or "")) or not allowed(uid) or not get(uid):
        return None
    return {"tools": [TOOL], "hint": HINT, "changes": {"nas_ablegen"}, "keep": {"nas_ablegen"},
            "filler": {"nas_ablegen": ("Ich schaue nach.", "Let me check.")}}


def _upload(uid, words):
    import documents
    w = str(words or "").lower().strip()
    for r in documents.list_docs(uid):
        if r.get("source") in ("nas", "eingang", "spark") or not r.get("file"):
            continue
        if not w or w in str(r.get("name", "")).lower():
            return r
    return None


async def tool(name, args, ctx):
    uid = (ctx.get("who") or {}).get("id")
    if name != "nas_ablegen" or not allowed(uid) or not get(uid):
        return "Der Ablage-Ordner ist für dieses Profil nicht eingerichtet (Ich → Speicher)."
    args = args if isinstance(args, dict) else {}
    kind = args.get("was") if args.get("was") in KINDS else "dokument"
    import nas
    place = (nas.find(uid, get(uid)["nas"]) or {}).get("name", "NAS")
    if kind == "dokument":
        import docmake
        d = docmake.find(uid, args.get("name"))
        if not d:
            return "Not proposed: no document the Spark made fits. Ask the user which one."
        p = {"kind": kind, "ref": d["id"], "label": d["title"][:80]}
    elif kind == "datei":
        r = _upload(uid, args.get("name"))
        if not r:
            return ("Not proposed: no uploaded document with a kept original fits (only with \"Originale aufbewahren\" "
                    "under Ich → Dokumente). Say so.")
        p = {"kind": kind, "ref": r["id"], "label": str(r["name"])[:80]}
    else:
        text = str(args.get("text") or "").strip()[:MAX_NOTE]
        if not text:
            return "Not proposed: the note is empty. Ask the user what to write."
        p = {"kind": kind, "ref": "", "label": "Notiz", "text": text}
    _pending[uid] = dict(p, src=ctx.get("src") or "", t=time.time())
    print(f"nasablage: vorgeschlagen | {kind} | {_log_name(uid)}", flush=True)
    return (f"NOT done yet. Ask the user exactly: „Soll ich {KINDS[kind][0]} („{p['label']}“) in den Ablage-Ordner auf "
            f"„{place}“ legen?“ It is filed only if the user says yes in the next message.")


async def _carry_out(uid, p):
    if p["kind"] == "dokument":
        import docmake
        d = docmake.load(uid, p["ref"])
        if not d:
            raise ValueError("das Dokument gibt es nicht mehr")
        data, name, _ = await asyncio.to_thread(docmake.build, uid, d, d["format"])
    elif p["kind"] == "datei":
        import documents
        got = documents.original(uid, p["ref"])
        if not got:
            raise ValueError("das Original gibt es nicht mehr")
        with open(got[0], "rb") as f:
            data = f.read()
        name = got[1]
    else:
        data = p["text"].encode("utf-8")
        name = f"Notiz {datetime.datetime.now():%Y-%m-%d %H-%M}.txt"
    return await put(uid, clean_name(name), data, p["kind"])


async def answer(ctx, latest):
    who = ctx.get("who")
    if not who or not ctx.get("own"):
        return None
    uid = who["id"]
    p = pending(uid)
    if not p or p.get("src", "") != (ctx.get("src") or ""):
        return None
    drop_pending(uid)
    import calendars
    import notaus
    what = f"{KINDS[p['kind']][0]} („{p['label']}“)"
    if not calendars.confirms(latest):
        print(f"nasablage: nicht abgelegt | kein ja | {_log_name(uid)}", flush=True)
        return {"call": {"name": "nas_ablegen (abgelehnt)", "args": p["label"], "result": "nicht abgelegt"},
                "system": f"NAS: {what} wurde NICHT abgelegt, weil der Nutzer nicht zugestimmt hat."}
    if not allowed(uid) or not get(uid):
        note = "NICHT abgelegt: der Ablage-Ordner ist nicht mehr frei."
        print(f"nasablage: ablegen abgelehnt | aus | {_log_name(uid)}", flush=True)
    else:
        try:
            final = await _carry_out(uid, p)
            note = f"Abgelegt: {what} liegt jetzt als „{final}“ im Ablage-Ordner unter Erstellt (von der NAS bestätigt)."
        except nasquelle.SourceError as e:
            note = f"NICHT abgelegt: die NAS meldet „{WHY.get(e.kind, WHY['other'])[0]}“."
        except notaus.NotausAktiv as e:
            note = f"NICHT abgelegt: {e}."
            print(f"nasablage: ablegen abgelehnt | notaus | {_log_name(uid)}", flush=True)
        except (ValueError, OSError) as e:
            note = f"NICHT abgelegt: {e}."
            print(f"nasablage: ablegen fehlgeschlagen | art=quelle | {_log_name(uid)}", flush=True)
    return {"call": {"name": "nas_ablegen (bestätigt)", "args": p["label"], "result": note},
            "system": "NAS: " + note + " Sag dem Nutzer genau das in einem Satz."}


async def briefing(uid, zone=None):
    return ""


# ---------------------------------------------------------------- for other modules
def for_live():
    """Live: profiles with a filing folder, files put there, taken from Eingang, failing (numbers only)."""
    if not admin_on():
        return {"on": False}
    profs = made = fetched = bad = 0
    for uid in profiles.user_ids():
        d = get(uid)
        if not d:
            continue
        profs += 1
        made += d["made"] + d["dropped"]
        fetched += d["fetched"]
        bad += bool(d["fail"])
    return {"on": True, "profiles": profs, "made": made, "fetched": fetched, "bad": bad}


def probes():
    """For the Dienst-Wächter: the places with a filing folder of a profile that may use it (no login)."""
    out = {}
    if not admin_on():
        return out
    import nas
    for uid in profiles.user_ids():
        d = get(uid) if allowed(uid) else None
        c = nas.find(uid, d["nas"]) if d else None
        if not c:
            continue
        u = urlsplit(c["url"])
        k = hashlib.sha256(f"{u.scheme}://{u.netloc}".encode()).hexdigest()[:8]
        if c["kind"] == "webdav":
            p = {"url": f"{u.scheme}://{u.netloc}/", "level": netguard.HOME, "verify": True, "pin": c.get("cert") or ""}
        else:
            p = {"tcp": True, "host": (u.hostname or "").lower(), "port": u.port or (22 if c["kind"] == "sftp" else 445),
                 "level": netguard.HOME, "ssh": c["kind"] == "sftp"}
        out.setdefault(k, dict(p, uids=[]))["uids"].append(uid)
    return out


def overview():
    """Zustand (admin): per profile numbers and state, never a path or a name."""
    names = {p["id"]: p["name"] for p in profiles.names()}
    rows = []
    for uid in profiles.user_ids():
        d = get(uid)
        if d:
            rows.append({"profile": names.get(uid, "?"), "made": d["made"] + d["dropped"], "fetched": d["fetched"],
                         "refused": d["refused"], "fail": (d["fail"] or {}).get("kind", ""), "last": (d["last"] or {}).get("t", 0)})
    return {"on": admin_on(), "rows": rows}


# ---------------------------------------------------------------- views and routes
def public(uid, d):
    return {"nas": d["nas"], "added": d["added"], "auto": d["auto"], "inbox": d["inbox"], "made": d["made"],
            "dropped": d["dropped"], "fetched": d["fetched"], "refused": d["refused"], "last": d["last"],
            "fail": d["fail"], "running": uid in _running}


def _view(uid):
    d = get(uid)
    return {"admin": admin_on(), "on": allowed(uid), "why": features.reason("nasablage", uid),
            "docs": features.allowed("documents", uid), "made_ok": features.allowed("erstellen", uid),
            "every": every() // 60, "folder": DROP, "why_words": {k: list(v) for k, v in WHY.items()},
            "drop": public(uid, d) if d else None}


def _on(prof=Depends(browser_profile)):
    """Only the profile's own browser login, never a device key."""
    if not admin_on():
        raise HTTPException(403, "Der Ablage-Ordner ist ausgeschaltet.")
    if not allowed(prof["id"]):
        raise HTTPException(403, "Der Ablage-Ordner ist für dieses Profil nicht frei.")
    return prof


def _say(kind):
    return {"lesen": "Der Spark darf in „spark_ablage“ nicht schreiben: dort „Lesen/Schreiben“ für seinen Benutzer geben.",
            "missing": "Einen Ordner „spark_ablage“ gibt es dort nicht, und der Spark darf ihn nicht anlegen: auf der NAS "
                       "einen freigegebenen Ordner „spark_ablage“ anlegen (Anleitung „Synology einrichten“).",
            "net": "Ablegen geht nur an einem Ort im Heimnetz.",
            "docs": "Den Eingang abholen braucht „Eigene Dokumente“ (Funktionen)."}.get(kind) or nasquelle._say(kind)


@router.get("/api/profile/nasablage")
def get_mine(request: Request, prof=Depends(browser_profile)):
    """Also when switched off or blocked: the own setting stays visible and can be removed."""
    guard.limit(request, "storage", prof["id"])
    return _view(prof["id"])


@router.post("/api/profile/nasablage")
async def setup(request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    uid = prof["id"]
    body = await core.json_body(request, 8192, lenient=True)
    nid = str(body.get("nas") or "")
    c = nasquelle._place(uid, nid)
    import nas
    if nas.zone(c) != "lan":
        print(f"nasablage: einrichten abgelehnt | internet | {_log_name(uid)}", flush=True)
        raise HTTPException(400, _say("net"))
    import nashilfe
    pl = _Place(c)
    try:
        await pl.make()
        right = await nashilfe._write_probe(c)
        if right != "schreiben":
            raise _err("lesen" if right == "lesen" else "missing")
    except nasquelle.SourceError as e:
        print(f"nasablage: einrichten fehlgeschlagen | art={e.kind} | {_log_name(uid)}", flush=True)
        raise HTTPException(409 if e.kind in ("lesen", "missing") else 502, _say(e.kind))
    finally:
        await pl.close()
    old = get(uid)
    keep = {k: old[k] for k in ("auto", "inbox")} if old else {"auto": True, "inbox": True}
    _save(uid, {"nas": nid, "added": int(time.time()), **keep, "made": 0, "dropped": 0, "fetched": 0, "refused": 0,
                "last": None, "fail": None, "seen": {}})
    print(f"nasablage: eingerichtet | art={c['kind']} | {_log_name(uid)}", flush=True)
    _live("event", "NAS", "Ablage-Ordner eingerichtet")
    return _view(uid)


@router.put("/api/profile/nasablage")
async def change(request: Request, prof=Depends(_on)):
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    body = await core.json_body(request, 1024, lenient=True)
    d = get(uid)
    if not d:
        raise HTTPException(404, "kein Ablage-Ordner eingerichtet")
    for k in ("auto", "inbox"):
        if k in body:
            if not isinstance(body[k], bool):
                raise HTTPException(400, f"{k}: true or false")
            d[k] = body[k]
    _save(uid, d)
    print(f"nasablage: geändert | auto={'ja' if d['auto'] else 'nein'} | eingang={'ja' if d['inbox'] else 'nein'} | {_log_name(uid)}", flush=True)
    return _view(uid)


@router.post("/api/profile/nasablage/now")
async def now_route(request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    uid = prof["id"]
    if not get(uid):
        raise HTTPException(404, "kein Ablage-Ordner eingerichtet")
    r = await inbox_once(uid, "hand")
    if not r["ok"]:
        raise HTTPException(409 if r["kind"] == "docs" else 502, _say(r["kind"]))
    return r


@router.delete("/api/profile/nasablage")
def remove(request: Request, prof=Depends(browser_profile)):
    """Also when blocked (own data). At the place everything stays as it is."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    had = get(uid) is not None
    _save(uid, None)
    drop_pending(uid)
    print(f"nasablage: entfernt | {'ja' if had else 'nichts da'} | {_log_name(uid)}", flush=True)
    return _view(uid)


@router.get("/api/admin/nasablage", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "storage", "admin")
    return overview()


import nas  # noqa: E402

nas.USES["ablage"] = uses
