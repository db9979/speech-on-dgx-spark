"""Verlauf auf allen Geräten (plan plaene/verlauf-sync.md): what keeps a profile's conversations alike everywhere.

Always (no switch, it only repairs what was there): devices send only their new messages (PUT /api/profile/convos
with "add", account.py), an open page asks for changes with ?since=, a conversation deleted elsewhere closes, and
what stood under an answer (sources, documents, a created document) is kept with it ("att", profiles._clean_convo).

Three functions, each off until the admin and the profile switch them on, never for guests:

    verlaufsync    Sofort-Abgleich: GET /api/profile/convos/stream, one event stream per open page. "convo" when a
                   conversation of the profile changed or went (only its id), "busy"/"idle" while an answer runs on
                   another device (only the kind of device, never the question). The page then asks ?since=.
    eingespraech   Ein Gespräch für alle Kanäle: Telegram, Siri, Begleiter, the watch and the own voice at a speaker
                   write into today's main conversation (marked with their channel, "via") instead of their own
                   conversation per day. A voice at a speaker that is not clearly the owner's stays in the speaker's.
    offlinelesen   Offline lesen: a browser the profile trusts (its second sign-in step remembers it, mfa.trusted)
                   keeps a copy of the conversations and the questions asked without the Spark. Every other browser
                   keeps nothing and deletes what it had (/api/profile/settings says "offline_here").
"""
import asyncio
import json
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import features
import guard
import profiles
from core import assistant, own_profile

router = APIRouter()
_lock = threading.Lock()

MAX_STREAMS = 8          # open pages per profile with the stream
STREAM_SECONDS = 30 * 60  # a stream ends after this; the page opens a new one
BEAT = 25                # a comment line keeps proxies from closing a quiet stream
QUEUE = 50               # events waiting per stream (more: the oldest are dropped, the page asks ?since= anyway)
BUSY_MAX = 10 * 60       # an answer that never said "done" stops counting as running

# conversations of the channels themselves (Telegram "tg-", speaker "esp-", ...) and of the Spark's own work:
# never "today's main conversation"
OWN_PREFIXES = ("tg-", "siri-", "desk-", "watch-", "esp-", "brief-", "agent-", "meet-")
VIA = {"telegram": "Telegram", "siri": "Siri", "desk": "Begleiter", "watch": "Uhr", "speaker": "Lautsprecher"}
# who answers right now, by kind of device (fixed words, shown as "Handy antwortet gerade …")
KINDS = {"web": "Browser", "phone": "Handy", "app": "iPhone-App", "car": "CarPlay", "speaker": "Lautsprecher",
         "watch": "Uhr", "siri": "Siri", "telegram": "Telegram", "desk": "Begleiter"}

_subs = {}   # uid -> {stream id: (loop, queue)}
_busy = {}   # uid -> {token: {"kind", "convo", "tab", "since"}}


def live_on(uid):
    return bool(uid) and features.allowed("verlaufsync", uid)


def streams():
    """Open streams (for the live view: only the number)."""
    with _lock:
        return sum(len(x) for x in _subs.values())


def _send(uid, ev):
    with _lock:
        subs = list(_subs.get(uid, {}).values())
    for loop, q in subs:
        def put(q=q):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(ev)
        try:
            loop.call_soon_threadsafe(put)
        except RuntimeError:   # the stream's loop is gone
            pass


def changed(uid, cid, gone=False):
    """profiles calls this after a conversation was stored or deleted (from any thread)."""
    if uid in _subs:
        _send(uid, {"type": "convo", "id": str(cid)[:40], "gone": bool(gone)})


profiles.CONVO_HOOKS.append(changed)


# ---------------------------------------------------------------- an answer running elsewhere
def kind_of(request, body):
    body = body if isinstance(body, dict) else {}
    c = body.get("client")
    if c in ("speaker", "watch", "siri", "telegram", "desk"):
        return c
    if profiles.key_scope(request) == "app":
        return "car" if body.get("car") is True else "app"
    return "phone" if body.get("view") == "app" else "web"


def begin(uid, kind, convo="", tab=""):
    """An answer for uid started; returns its token for end (None when nobody listens)."""
    if not uid or uid not in _subs:
        return None
    tok = secrets.token_hex(6)
    item = {"kind": kind if kind in KINDS else "web", "convo": str(convo or "")[:40], "tab": str(tab or "")[:24],
            "since": time.time()}
    with _lock:
        _busy.setdefault(uid, {})[tok] = item
    _send(uid, dict({"type": "busy", "name": KINDS[item["kind"]]}, **{k: item[k] for k in ("kind", "convo", "tab")}))
    return tok


def end(uid, tok):
    if not tok:
        return
    with _lock:
        item = _busy.get(uid, {}).pop(tok, None)
        if uid in _busy and not _busy[uid]:
            _busy.pop(uid)
    if item:
        _send(uid, {"type": "idle", "kind": item["kind"], "convo": item["convo"], "tab": item["tab"]})


def running(uid):
    now = time.time()
    with _lock:
        items = [x for x in _busy.get(uid, {}).values() if now - x["since"] < BUSY_MAX]
    return [{"type": "busy", "name": KINDS[x["kind"]], "kind": x["kind"], "convo": x["convo"], "tab": x["tab"]} for x in items]


@router.get("/api/profile/convos/stream", dependencies=[Depends(assistant)])
async def stream(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    if not live_on(uid):
        raise HTTPException(403, "Sofort-Abgleich ist aus (Ich → Gespräch → Verlauf)")
    guard.limit(request, "convostream", uid)
    loop, q, sid = asyncio.get_running_loop(), asyncio.Queue(maxsize=QUEUE), secrets.token_hex(6)
    with _lock:
        mine = _subs.setdefault(uid, {})
        if len(mine) >= MAX_STREAMS:   # the oldest page gives way (it asks ?since= every 30 s anyway)
            mine.pop(next(iter(mine)))
        mine[sid] = (loop, q)

    async def events():
        end_at = time.monotonic() + STREAM_SECONDS
        try:
            yield "retry: 5000\n\n"
            for ev in running(uid):
                yield f"data: {json.dumps(ev)}\n\n"
            while time.monotonic() < end_at and live_on(uid):
                try:
                    ev = await asyncio.wait_for(q.get(), BEAT)
                except asyncio.TimeoutError:
                    yield ": .\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            with _lock:
                (_subs.get(uid) or {}).pop(sid, None)
                if uid in _subs and not _subs[uid]:
                    _subs.pop(uid)
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- one conversation for all channels
def target(uid, own_cid, own_title, local, via, owner=True):
    """Where a channel keeps its turn: (conversation id, title, extra marks of its messages). With "Ein Gespräch für
    alle Kanäle" today's main conversation of the profile (the newest of today that is no channel's own), else the
    channel's own as before. A voice that was not clearly the owner's never goes into the main conversation."""
    if not owner or via not in VIA or not features.allowed("eingespraech", uid):
        return own_cid, own_title, {}
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    main = next((c for c in profiles.convos(uid) if c.get("updated", 0) >= midnight
                 and not str(c.get("id", "")).startswith(OWN_PREFIXES)), None)
    if main:
        return main["id"], main.get("title") or "Heute", {"via": via}
    return "tag-" + local.strftime("%Y%m%d"), "Heute " + local.strftime("%d.%m."), {"via": via}


def keep(uid, own_cid, own_title, local, via, msgs, owner=True):
    """Stores a channel's turn (the last question and answer) where target says, every message marked."""
    cid, title, mark = target(uid, own_cid, own_title, local, via, owner)
    return profiles.append_convo(uid, cid, title, [dict(m, **mark) for m in msgs])


# ---------------------------------------------------------------- offline reading
def offline_here(prof, request):
    """This browser may keep the profile's conversations for reading without the Spark: the function is on and the
    profile trusts this browser (second sign-in step, "diesem Browser vertrauen"). Device keys never."""
    if not prof or request.headers.get(profiles.DEVICE_HEADER) or request.scope.get("speech_profile"):
        return False
    if not features.allowed("offlinelesen", prof["id"]):
        return False
    import mfa
    return mfa.trusted(prof["id"], request)
