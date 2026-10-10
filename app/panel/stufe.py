"""Priority for people (plan plaene/vorrang-personen.md, V01.0.282): a profile the admin gives "Vorrang" gets
its answer first when several people talk to the Spark at once.

- The stage per profile ("vorrang", normal, "hinten") is given only by the admin (Personen und Geräte → profile
  → Rechte), at most MAX_HIGH profiles with Vorrang, stored in STATE/personen-vorrang.json. Off until the admin
  switches chat.person_priority on (features.py "vorrang"); then everybody without a stage is normal as before.
- Who asks comes from the sign-in (browser, app or device key, linked Telegram), never from what a request
  or the model says. Guests and everything without a profile are always normal. At a shared speaker the
  stage counts only when the speaker recognition heard the profile's own voice (the turn of chat_turn.py
  is then the profile's own, else it is a guest turn).
- The panel sends the stage to the ASR/TTS services with the key of common.stage_key(); they let waiting
  requests go by stage (common.PrioGate), never stop one that runs.
- Language model (qwen38, not ours): while an answer with Vorrang has no first sentence yet, new rounds of
  other people wait at most chat.person_priority_wait seconds before they go out (wait_turn()). Background
  work gives way to all speech anyway (vorrang.py).
- A device of a profile with Vorrang may say "recording starts" (POST /api/vorrang/spricht): background work
  stops at once and the language model gate closes for a short while, before the recording is even sent.
"""
import asyncio
import json
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from common import STAGE_HEADER, STAGE_HIGH, STAGE_KEY_HEADER, STAGE_LOW, stage_key
from core import assistant, auth

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
LEVELS = {"vorrang": STAGE_HIGH, "hinten": STAGE_LOW}
NAMES = {"vorrang": ("Vorrang", "Priority"), "": ("Normal", "Normal"), "hinten": ("Hinten", "Last")}
MAX_HIGH = 3            # more would make Vorrang mean nothing
WAIT_RANGE = (0, 5)     # chat.person_priority_wait: how long others wait at most (seconds)
HINT_S = 15             # "recording starts" closes the gate this long at most (or until the turn begins)
FIRST_MAX = 30          # a Vorrang answer holds others only this long, even without a first sentence
_lock = threading.Lock()
router = APIRouter()


def _file():
    return os.path.join(STATE, "personen-vorrang.json")


def levels():
    """{uid: "vorrang"|"hinten"} as the admin set it (profiles that are gone are left out)."""
    try:
        with open(_file()) as f:
            d = json.load(f)
        d = d.get("levels") if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    ids = profiles.user_ids()
    return {k: v for k, v in (d or {}).items() if isinstance(k, str) and k in ids and v in LEVELS}


def _save(lv):
    with _lock:
        os.makedirs(STATE, exist_ok=True)
        tmp = _file() + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump({"levels": lv}, f)
        os.replace(tmp, _file())


def on(c=None):
    return features.admin_on("vorrang", c)


features.GRANTED["vorrang"] = lambda uid: levels().get(uid) == "vorrang"   # Ich shows "Vorrang: bei dir aus" otherwise


def level(uid, c=None):
    """"vorrang", "" (normal) or "hinten" for this profile; always "" while the admin switch is off or for guests."""
    if not uid or not on(c):
        return ""
    return levels().get(uid, "")


def turn_level(turn):
    """The stage of a chat turn: only the profile's own turn (own browser or its own voice), never a stranger's."""
    who = getattr(turn, "who", None)
    if not who or not getattr(turn, "own_browser", False):
        return ""
    return level(who["id"], getattr(turn, "ccfg", None))


def headers(lv):
    """What goes with a request to the ASR/TTS services (nothing for normal)."""
    if lv not in LEVELS:
        return {}
    key = stage_key(create=True)
    return {STAGE_HEADER: str(LEVELS[lv]), STAGE_KEY_HEADER: key} if key else {}


def asr_level(request):
    """For a recording sent to the speech recognition: the signed-in profile, but not at a shared speaker
    (whose voice it is shows only after the recognition)."""
    me = profiles.current(request)
    if not me:
        return ""
    dev = profiles.device(request)
    if dev and not dev["scope"]:
        import esp32
        if esp32.by_device(dev["id"])[0] is not None:
            return ""
    return level(me["id"])


# ---------------------------------------------------------------- the language model gate (step B)
_active = {}     # token -> (uid, since): answers with Vorrang that have no first sentence yet
_hints = {}      # uid -> until: a device of this profile said "recording starts"
_count = {"held": 0, "held_ms_max": 0}


def _wait_s(c=None):
    c = features.chat_cfg() if c is None else c
    v = c.get("person_priority_wait", 2)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and WAIT_RANGE[0] <= v <= WAIT_RANGE[1] else 2


def begin(turn):
    """A Vorrang answer starts: returns its token (None for any other answer)."""
    if turn_level(turn) != "vorrang":
        return None
    tok = object()
    _active[tok] = (turn.who["id"], time.monotonic())
    _hints.pop(turn.who["id"], None)
    return tok


def first(tok):
    """Its first sentence is there (or it ended): the others may go on."""
    if tok is not None:
        _active.pop(tok, None)


def hint(uid, now=None):
    now = time.monotonic() if now is None else now
    _hints[uid] = now + HINT_S


def holding(now=None):
    """Somebody with Vorrang is about to get or getting the first sentence of an answer."""
    now = time.monotonic() if now is None else now
    for k, (_, since) in list(_active.items()):
        if now - since > FIRST_MAX:
            _active.pop(k, None)
    for u, until in list(_hints.items()):
        if until < now:
            _hints.pop(u, None)
    return bool(_active or _hints)


async def wait_turn(lv, c=None, sleep=asyncio.sleep, clock=time.monotonic):
    """Before another person's request to the language model goes out: wait while a Vorrang answer has no
    first sentence yet, at most chat.person_priority_wait seconds. Returns the seconds waited."""
    if lv == "vorrang" or not on(c) or not holding():
        return 0.0
    most, t0 = _wait_s(c), clock()
    while holding() and clock() - t0 < most:
        await sleep(0.05)
    waited = clock() - t0
    if waited > 0:
        _count["held"] += 1
        _count["held_ms_max"] = max(_count["held_ms_max"], int(waited * 1000))
        print(f"vorrang: Antwort wartete {waited:.1f} s auf eine Antwort mit Vorrang", flush=True)
    return waited


def today():
    return dict(_count, active=len(_active) + len(_hints))


# ---------------------------------------------------------------- endpoints
async def _small(request):
    raw = await request.body()
    if len(raw) > 256:
        raise HTTPException(413, "too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid JSON")
    return body


def rights(uid):
    """For the profile detail (admin.py _rights)."""
    lv = levels()
    return {"spark": on(), "level": lv.get(uid, ""), "high": sum(1 for v in lv.values() if v == "vorrang"), "max": MAX_HIGH}


@router.put("/api/admin/vorrang/{uid}", dependencies=[Depends(auth)])
async def admin_level(uid: str, request: Request):
    """{"level": "" | "vorrang" | "hinten"} for one profile (Personen und Geräte → profile → Rechte)."""
    guard.limit(request, "features", admin=True)
    body = await _small(request)
    lv = body.get("level")
    if uid not in profiles.user_ids():
        raise HTTPException(404, "no such profile")
    if lv not in ("",) + tuple(LEVELS):
        raise HTTPException(400, "level: empty, vorrang or hinten")
    cur = levels()
    if lv == "vorrang" and cur.get(uid) != "vorrang" and sum(1 for v in cur.values() if v == "vorrang") >= MAX_HIGH:
        raise HTTPException(400, f"Höchstens {MAX_HIGH} Profile mit Vorrang.")
    if lv:
        cur[uid] = lv
    else:
        cur.pop(uid, None)
    _save(cur)
    elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
    guard.log("person_priority", ip=guard.client_ip(request), uid=uid, by="main" if not elev else elev["id"],
              detail=NAMES[lv][0])
    print(f"vorrang: Stufe eines Profils geändert ({NAMES[lv][0]})", flush=True)
    return {"level": lv}


@router.post("/api/vorrang/spricht", dependencies=[Depends(assistant)])
async def speaking_now(request: Request):
    """A device of a profile with Vorrang: "a recording starts now" (wake word heard, button pressed). Stops
    background work and closes the language model gate briefly. Answers the same for everybody, so nobody
    learns whether a profile has Vorrang."""
    me = profiles.current(request)
    if not me:
        raise HTTPException(401, "sign in first")
    guard.limit(request, "vorrang", me["id"])
    if asr_level(request) == "vorrang":
        import vorrang
        vorrang.mark()
        hint(me["id"])
    return {"ok": True}
