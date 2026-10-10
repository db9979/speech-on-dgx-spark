"""Telegram bot: profiles talk to the assistant by text or voice message from anywhere, without the
web page and without an open port (the panel asks Telegram for new messages itself, long polling).

Off until the admin switches it on (chat.telegram) and enters the token of a bot made with
@BotFather. Each profile links its own Telegram account in "Ich" → Telegram with a one-time code
(/start CODE); chats nobody linked get one fixed sentence and nothing else. Groups are ignored.

What a profile allows over Telegram (all off until it switches them on, see profiles.SETTINGS):
    tg_voice    answers also as a voice message in the Spark voice
    tg_private  calendar, e-mail, contacts, parcels and documents (messages pass Telegram's servers)
    tg_ha       switching Home Assistant, only with the profile's code word
    tg_push     reminders, the daily briefing and proactive notes also as Telegram messages

    STATE/telegram.json             {"token": sealed, "bot": "name", "offset": n}
    USERS_DIR/<uid>/telegram.json   {"chat": id, "name": "@user", "since": t}
"""
import asyncio
import datetime
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time

import httpx

import profiles
import vault
import features
from common import load_config

API = "https://api.telegram.org"
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
CODE_SECONDS = 600
FOLLOW_UP = 30 * 60          # earlier messages of the day's Telegram conversation count this long
MAX_VOICE = 5 * 1024 * 1024
STRANGER = "Dieser Spark-Assistent ist privat. Wer ein Profil hat, verbindet Telegram im Panel unter Profil → Telegram."
HELP = ("Schreib mir oder schick eine Sprachnachricht. /neu beginnt ein neues Gespräch, /stimme schaltet die "
        "Antwort als Sprachnachricht an oder aus, /merken als Antwort auf ein Foto legt es in deine Dokumente, "
        "/trennen löst die Verbindung.")
_lock = threading.Lock()
_codes = {}                  # code -> (uid, expiry)
_strangers = {}              # chat id -> last time it got STRANGER
_tries = {}                  # chat id -> [times of wrong codes] (guessing a code is pointless after a few)
MAX_TRIES = 5                # wrong codes per chat and hour
FORWARDED = ("Weitergeleitete Nachrichten nehme ich nicht als Auftrag, sie stammen von jemand anderem. "
             "Schreib mir selbst, was ich tun soll.")
_history = {}                # uid -> (time, messages)


def _file():
    return os.path.join(STATE, "telegram.json")


def _state():
    try:
        with open(_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(**kw):
    with _lock:
        d = dict(_state(), **kw)
        os.makedirs(STATE, exist_ok=True)
        tmp = _file() + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(d, f)
        os.replace(tmp, _file())


def token():
    return vault.open_(_state().get("token", ""))


def admin_on():
    return features.admin_on("telegram")


def base():
    return (load_config().get("chat", {}).get("telegram_api") or API).rstrip("/") + "/bot" + token()


def safe(e, n=160):
    """An error for the log without the bot token (httpx puts the full URL, /bot<token>/..., into its messages)."""
    text = str(e)
    try:
        tok = token()
    except Exception:
        tok = ""
    if tok:
        text = text.replace(tok, "***")
    return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***", text)[:n]


async def call(c, method, **params):
    """One Bot API call; ValueError with Telegram's description when it refuses."""
    r = await c.post(f"{base()}/{method}", json=params)
    try:
        d = r.json()
    except ValueError:
        raise ValueError(f"Telegram answered {r.status_code}")
    if not d.get("ok"):
        raise ValueError(str(d.get("description") or f"Telegram answered {r.status_code}")[:200])
    return d.get("result")


# ---------------------------------------------------------------- links (one Telegram chat per profile)
def _link_file(uid):
    return profiles._path(uid, "telegram.json")


def link(uid):
    try:
        with open(_link_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("chat"), int) else None
    except (OSError, ValueError):
        return None


def owner(chat_id):
    return next((u for u in profiles.user_ids() if (link(u) or {}).get("chat") == chat_id), None)


def new_code(uid):
    now = time.time()
    for k in [k for k, v in _codes.items() if v[1] < now or v[0] == uid]:
        _codes.pop(k, None)
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    _codes[code] = (uid, now + CODE_SECONDS)
    return code


def take_code(code):
    hit = _codes.pop(str(code).strip().upper(), None)
    return hit[0] if hit and hit[1] > time.time() else None


def unlink(uid):
    try:
        os.remove(_link_file(uid))
    except OSError:
        pass
    _history.pop(uid, None)


def push_on(uid, private=False):
    """Notes go to Telegram: tg_push, and for private ones (appointments, mails, the briefing) also tg_private."""
    s = profiles.settings(uid)
    return bool(admin_on() and token() and link(uid) and s.get("tg_push") and (not private or s.get("tg_private")))


# ---------------------------------------------------------------- talking to the assistant
async def ask(uid, text, pictures=None):
    """Runs the assistant for the profile like a device would and returns its answer."""
    import chat
    from starlette.requests import Request
    now = time.time()
    last = _history.get(uid)
    history = last[1][-8:] if last and now - last[0] < FOLLOW_UP else []
    s = profiles.settings(uid)
    body = {"messages": history + [{"role": "user", "content": text}], "client": "telegram", "speak": False,
            "tz": s.get("tz", "")}
    if pictures:
        body["images"] = pictures
    data = json.dumps(body).encode()
    # the profile is set by the panel itself (an HTTP request can never put this key into its scope)
    scope = {"type": "http", "method": "POST", "path": "/api/chat", "headers": [], "query_string": b"",
             "client": ("telegram", 0), "server": ("127.0.0.1", 0), "scheme": "http", "speech_profile": uid}

    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}
    response = await chat.chat(Request(scope, receive))
    answer, error, from_mail, from_outside = "", "", False, False
    async for chunk in response.body_iterator:
        for line in (chunk.decode() if isinstance(chunk, bytes) else chunk).split("\n"):
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            if ev.get("type") == "text":
                answer += ev.get("delta", "")
            elif ev.get("type") in ("truncated", "retract"):
                answer = answer[:max(0, len(answer) - int(ev.get("drop") or 0))]
            elif ev.get("type") == "mail":
                from_mail = True
            elif ev.get("type") == "outside":
                from_outside = True
            elif ev.get("type") == "error" and not error:
                error = "Der Spark konnte gerade nicht antworten."
    answer = answer.strip() or error or "Dazu habe ich keine Antwort."
    import homeassistant
    ha = homeassistant.get(uid)
    if ha and homeassistant.needs_code(ha):
        text = homeassistant.redact(ha, text)   # the code word is never kept
    msgs = history + [{"role": "user", "content": ("(Foto) " if pictures else "") + text},
                      dict({"role": "assistant", "content": answer}, **({"mail": True} if from_mail else
                                                                       {"outside": True} if from_outside else {}))]
    _history[uid] = (now, msgs)
    local = datetime.datetime.now(chat.user_zone(s.get("tz", "")))
    day = local.strftime("%Y%m%d")
    try:
        old = next((c for c in profiles.convos(uid) if c.get("id") == "tg-" + day), None)
        profiles.save_convo(uid, {"id": "tg-" + day, "title": "Telegram " + local.strftime("%d.%m."),
                                  "updated": int(now * 1000), "msgs": (old["msgs"] if old else []) + msgs[-2:]})
    except Exception as e:
        print("telegram: convo", type(e).__name__, flush=True)
    return answer


def _ffmpeg(args, data):
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in"), os.path.join(d, "out")
        with open(src, "wb") as f:
            f.write(data)
        # -t: a tiny compressed file must not unpack to hours of audio (voice messages are short)
        p = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src, "-t", "600"] + args + [dst],
                           capture_output=True, timeout=60)
        if p.returncode != 0:
            raise ValueError("ffmpeg: " + p.stderr.decode(errors="replace")[-200:])
        with open(dst, "rb") as f:
            return f.read()


async def transcribe(audio):
    """Text of a voice message (OGG/Opus) through the Spark's speech recognition."""
    from core import api_headers
    cfg = load_config()
    wav = await asyncio.to_thread(_ffmpeg, ["-ac", "1", "-ar", "16000", "-f", "wav"], audio)
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['asr']['port']}/v1/audio/transcriptions",
                         files={"file": ("voice.wav", wav)}, data={"language": "auto", "response_format": "json"},
                         headers=api_headers())
    r.raise_for_status()
    return str(r.json().get("text", "")).strip()


async def speak(uid, text):
    """The answer in the profile's voice as OGG/Opus for sendVoice."""
    from core import api_headers
    cfg = load_config()
    voice = profiles.settings(uid).get("voice") or ""
    body = {"input": text[:1500], "response_format": "wav"}
    if voice:
        body["voice"] = voice
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech", json=body, headers=api_headers())
    r.raise_for_status()
    return await asyncio.to_thread(_ffmpeg, ["-c:a", "libopus", "-b:a", "32k", "-f", "ogg"], r.content)


async def send_voice(c, chat_id, ogg):
    r = await c.post(f"{base()}/sendVoice", data={"chat_id": str(chat_id)}, files={"voice": ("antwort.ogg", ogg, "audio/ogg")})
    if not r.json().get("ok"):
        raise ValueError(str(r.json().get("description"))[:200])


# ---------------------------------------------------------------- the update loop
async def handle(c, upd):
    """One update from Telegram."""
    m = upd.get("message") or {}
    chat_ = m.get("chat") or {}
    if chat_.get("type") != "private" or not isinstance(chat_.get("id"), int):
        return    # groups and channels: never
    cid = chat_["id"]
    text = str(m.get("text") or "").strip()
    uid = owner(cid)
    if text.startswith("/start"):
        code = text[6:].strip()
        now = time.time()
        tries = [t for t in _tries.get(cid, []) if now - t < 3600]
        if len(tries) >= MAX_TRIES:
            return    # someone guessing codes: no answer, no check
        new = take_code(code) if code else None
        if code and not new:
            _tries[cid] = tries + [now]
        if new:
            for u in profiles.user_ids():          # one profile per Telegram chat
                if u != new and (link(u) or {}).get("chat") == cid:
                    unlink(u)
            frm = m.get("from") or {}
            profiles._write(_link_file(new), {"chat": cid, "since": int(time.time()),
                                              "name": ("@" + frm["username"]) if frm.get("username") else str(frm.get("first_name", ""))[:40]})
            who = profiles.by_id(new)
            await call(c, "sendMessage", chat_id=cid, text=f"Verbunden mit dem Profil {who['name'] if who else ''}. " + HELP)
            print("telegram: linked a profile", flush=True)
            return
        if not uid:
            await call(c, "sendMessage", chat_id=cid, text="Der Code passt nicht oder ist abgelaufen. Hol dir im Panel unter Profil → Telegram einen neuen.")
            return
    if not uid:
        if len(_strangers) > 1000:
            _strangers.clear()
        if time.time() - _strangers.get(cid, 0) > 24 * 3600:
            _strangers[cid] = time.time()
            await call(c, "sendMessage", chat_id=cid, text=STRANGER)
        return
    s = profiles.settings(uid)
    if text in ("/start", "/hilfe", "/help"):
        await call(c, "sendMessage", chat_id=cid, text=HELP)
        return
    if text in ("/neu", "/new"):
        _history.pop(uid, None)
        await call(c, "sendMessage", chat_id=cid, text="Gut, wir fangen neu an.")
        return
    if text in ("/stimme", "/voice"):
        profiles.save_settings(uid, dict(s, tg_voice=not s.get("tg_voice")))
        await call(c, "sendMessage", chat_id=cid, text="Antworten kommen jetzt auch als Sprachnachricht." if not s.get("tg_voice")
                   else "Antworten kommen jetzt nur als Text.")
        return
    if text in ("/trennen", "/stop"):
        unlink(uid)
        await call(c, "sendMessage", chat_id=cid, text="Getrennt. Neu verbinden geht im Panel unter Profil → Telegram.")
        return
    if any(k in m for k in ("forward_origin", "forward_from", "forward_from_chat", "forward_sender_name", "forward_date")):
        await call(c, "sendMessage", chat_id=cid, text=FORWARDED)   # someone else's words never act for the profile
        return
    # a photo (or a reply to one, for a follow-up question): the model looks at it (images.py), only
    # with the profile's tg_images; the caption is the question
    if text.lower() in KEEP or str(m.get("caption") or "").strip().lower() in KEEP:
        await photo_keep(c, uid, cid, m.get("photo") or (m.get("reply_to_message") or {}).get("photo"))
        return
    photo = m.get("photo") or (((m.get("reply_to_message") or {}).get("photo")) if text else None)
    if photo and isinstance(photo, list):
        await photo_question(c, uid, cid, m, photo, text or str(m.get("caption") or "").strip())
        return
    voice = m.get("voice") or m.get("audio")
    if voice and not text:
        if int(voice.get("file_size") or 0) > MAX_VOICE:
            await call(c, "sendMessage", chat_id=cid, text="Die Sprachnachricht ist zu lang.")
            return
        await call(c, "sendChatAction", chat_id=cid, action="typing")
        f = await call(c, "getFile", file_id=voice["file_id"])
        root = (load_config().get("chat", {}).get("telegram_api") or API).rstrip("/")
        r = await c.get(f"{root}/file/bot{token()}/{f['file_path']}")
        r.raise_for_status()
        try:
            text = await transcribe(r.content)
        except Exception as e:
            print("telegram: voice", type(e).__name__, safe(e, 120), flush=True)
            await call(c, "sendMessage", chat_id=cid, text="Ich konnte die Sprachnachricht nicht verstehen.")
            return
        if not text:
            await call(c, "sendMessage", chat_id=cid, text="In der Sprachnachricht habe ich nichts gehört.")
            return
    if not text:
        return
    await call(c, "sendChatAction", chat_id=cid, action="typing")
    answer = await ask(uid, text[:2000])
    await call(c, "sendMessage", chat_id=cid, text=answer[:4000])
    await forget_code(c, uid, cid, m, text)
    if s.get("tg_voice"):
        try:
            await send_voice(c, cid, await speak(uid, answer))
        except Exception as e:
            print("telegram: voice answer", type(e).__name__, safe(e, 120), flush=True)


PHOTO_ASK = "Was ist auf dem Bild?"
KEEP = ("/merken", "/save")


async def photo_bytes(c, photo):
    """The biggest size of a Telegram photo, read with a byte limit (ValueError if none fits)."""
    import images
    sizes = [p for p in photo if isinstance(p, dict) and isinstance(p.get("file_id"), str)
             and 0 < int(p.get("file_size") or 0) <= images.MAX_BYTES] if isinstance(photo, list) else []
    if not sizes:
        raise ValueError("no photo of a usable size")
    best = max(sizes, key=lambda p: int(p.get("width") or 0) * int(p.get("height") or 0))
    f = await call(c, "getFile", file_id=best["file_id"])
    if int(f.get("file_size") or 0) > images.MAX_BYTES or not re.fullmatch(r"[\w/.\-]{1,200}", str(f.get("file_path"))):
        raise ValueError("unexpected file")
    root = (load_config().get("chat", {}).get("telegram_api") or API).rstrip("/")
    data = bytearray()
    async with c.stream("GET", f"{root}/file/bot{token()}/{f['file_path']}") as r:
        r.raise_for_status()
        async for chunk in r.aiter_bytes():
            data += chunk
            if len(data) > images.MAX_BYTES:
                raise ValueError("too big")
    return bytes(data)


async def photo_keep(c, uid, cid, photo):
    """/merken on a photo (as its caption or as an answer to it): the photo goes into the profile's
    documents, where the language model reads it later (wissen.py). Needs the same switches as photos
    over Telegram plus "Bilder und Scans lesen"."""
    import asyncio
    import datetime
    import images
    import wissen
    if not photo:
        await call(c, "sendMessage", chat_id=cid, text="Antworte mit /merken auf ein Foto, dann lege ich es in deine Dokumente.")
        return
    if not images.allowed(uid, "tg") or not wissen.on(uid, "pictures"):
        await call(c, "sendMessage", chat_id=cid, text="Fotos lege ich nur ab, wenn du es im Panel erlaubst: Ich → Telegram → "
                   "Fotos über Telegram und Ich → Dokumente → Bilder und Scans lesen lassen.")
        return
    try:
        data = await photo_bytes(c, photo)
        await asyncio.to_thread(wissen.add, uid, f"Telegram-Foto {datetime.datetime.now():%Y-%m-%d %H-%M}.jpg", data,
                                None, "telegram")
    except Exception as e:
        print("telegram: photo not kept", type(e).__name__, safe(e, 120), flush=True)
        await call(c, "sendMessage", chat_id=cid, text="Dieses Foto konnte ich nicht ablegen.")
        return
    await call(c, "sendMessage", chat_id=cid, text="Abgelegt unter Meine Dokumente. Ich lese es in einer ruhigen Minute, "
               "danach kannst du danach fragen.")


async def photo_question(c, uid, cid, m, photo, text):
    import images
    if not images.allowed(uid, "tg"):
        if m.get("photo"):
            await call(c, "sendMessage", chat_id=cid, text="Fotos schaue ich mir nur an, wenn du es im Panel erlaubst: "
                       "Ich → Gespräch → Bilder an den Assistenten und Ich → Telegram → Fotos über Telegram.")
        return
    await call(c, "sendChatAction", chat_id=cid, action="typing")
    try:
        pic = await images.put(uid, "tg", await photo_bytes(c, photo))
    except Exception as e:
        print("telegram: photo", type(e).__name__, safe(e, 120), flush=True)
        await call(c, "sendMessage", chat_id=cid, text="Mit diesem Foto kann ich nichts anfangen.")
        return
    try:
        answer = await ask(uid, (text or PHOTO_ASK)[:2000], [pic["id"]])
    except Exception as e:
        print("telegram: photo answer", type(e).__name__, safe(e, 120), flush=True)
        answer = "Der Spark konnte gerade nicht antworten."
    finally:
        images.drop(pic["id"], uid, "tg")     # a follow-up answers the photo again (reply to it)
    await call(c, "sendMessage", chat_id=cid, text=answer[:4000])
    if profiles.settings(uid).get("tg_voice"):
        try:
            await send_voice(c, cid, await speak(uid, answer))
        except Exception as e:
            print("telegram: voice answer", type(e).__name__, safe(e, 120), flush=True)


async def forget_code(c, uid, cid, m, text):
    """The Home Assistant code word must not stay readable in the chat: the bot deletes the person's
    message with it, or asks them to when Telegram refuses."""
    import homeassistant
    ha = homeassistant.get(uid)
    if not (ha and homeassistant.code_given(ha, text)) or not m.get("message_id"):
        return
    try:
        await call(c, "deleteMessage", chat_id=cid, message_id=m["message_id"])
    except Exception as e:
        print("telegram: delete code message", type(e).__name__, safe(e, 120), flush=True)
        await call(c, "sendMessage", chat_id=cid,
                   text="Deine Nachricht enthält das Codewort. Bitte lösche sie hier im Chat.")


async def poll_once(c, wait=25):
    """Fetches and handles waiting updates; returns how many came."""
    offset = int(_state().get("offset") or 0)
    ups = await call(c, "getUpdates", offset=offset, timeout=wait, allowed_updates=["message"])
    for u in ups or []:
        _save_state(offset=int(u["update_id"]) + 1)   # first: a message that breaks the handler is not retried forever
        try:
            await handle(c, u)
        except Exception as e:
            print("telegram: message", type(e).__name__, safe(e, 160), flush=True)
    return len(ups or [])


# Telegram hands new messages to one getUpdates at a time; a second one ("Conflict: terminated by other
# getUpdates request") means another poller uses the same token: a second loop in this process (guarded by
# _poller) or another program. Then wait longer and longer instead of every 15 s, log rarely and show a
# fixed hint (alert()); one conflict right after a restart is normal (the old process's long poll still runs).
CONFLICT_WAIT = (5, 30, 60, 120, 300, 600)
_poller = {"on": False}
conflict = {"count": 0, "since": 0.0}


def is_conflict(e):
    return isinstance(e, ValueError) and str(e).lower().startswith("conflict")


def conflict_wait(n):
    """Seconds to wait after the n-th conflict in a row (n >= 1)."""
    return CONFLICT_WAIT[min(max(n, 1), len(CONFLICT_WAIT)) - 1]


def on_conflict(now):
    """Counts one conflict; returns the wait. Logs the 2nd and then every 20th, never the token."""
    conflict["count"] += 1
    n = conflict["count"]
    if n == 1:
        conflict["since"] = now
    wait = conflict_wait(n)
    if n == 2 or n % 20 == 0:
        print(f"telegram: conflict: another program polls with the same bot token ({n} times), "
              f"retry in {wait} s; use the token in one place only (Funktionen → Telegram)", flush=True)
    return wait


def conflict_over():
    if conflict["count"] >= 2:
        print(f"telegram: conflict over after {conflict['count']} times, polling again", flush=True)
    conflict.update(count=0, since=0.0)


def alert():
    """For Zustand (health.alerts): the hint while another program keeps taking the bot's messages."""
    if conflict["count"] < 2 or not admin_on():
        return []
    return [{"kind": "telegram", "level": "warn",
             "text": "Telegram: Ein anderes Programm fragt mit demselben Bot-Token nach Nachrichten, deshalb "
                     "kommen Nachrichten nicht sicher an. Den Token nur an einer Stelle nutzen oder bei @BotFather "
                     "einen neuen holen (/revoke) und unter Funktionen → Telegram eintragen."}]


async def loop():
    if _poller["on"]:   # one poller per process, however often startup runs
        print("telegram: a poller runs already, not starting a second one", flush=True)
        return
    _poller["on"] = True
    while True:
        if not admin_on() or not token():
            conflict_over()
            await asyncio.sleep(10)
            continue
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10)) as c:
                while admin_on() and token():
                    await poll_once(c)
                    if conflict["count"]:
                        conflict_over()
        except Exception as e:
            if is_conflict(e):
                await asyncio.sleep(on_conflict(time.time()))
                continue
            print("telegram:", type(e).__name__, safe(e, 160), flush=True)
            await asyncio.sleep(15)


async def notify(uid, text, private=True):
    """A reminder, briefing or proactive note as a Telegram message (when the profile wants that)."""
    if not push_on(uid, private):
        return 0
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await call(c, "sendMessage", chat_id=link(uid)["chat"], text=text[:4000])
        return 1
    except (httpx.HTTPError, ValueError) as e:
        print("telegram: notify", type(e).__name__, safe(e, 120), flush=True)
        return 0


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from account import browser_profile, secret_profile  # noqa: E402
from core import admin_code, assistant, auth, own_profile  # noqa: E402

router = APIRouter()


@router.get("/api/admin/telegram", dependencies=[Depends(auth)])
def admin_get():
    st = _state()
    return {"bot": st.get("bot", ""), "has_token": bool(st.get("token")),
            "linked": sum(1 for u in profiles.user_ids() if link(u)), "conflict": conflict["count"] >= 2}


@router.put("/api/admin/telegram", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_set(request: Request):
    body = await request.json()
    tok = str((body or {}).get("token", "")).strip()
    if not re.fullmatch(r"\d{5,15}:[\w\-]{30,60}", tok):
        raise HTTPException(400, "Das sieht nicht wie ein Bot-Token aus (Zahl:Buchstaben, von @BotFather).")
    old = _state().get("token", "")
    _save_state(token=vault.seal(tok))
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            me = await call(c, "getMe")
    except (httpx.HTTPError, ValueError) as e:
        _save_state(token=old)
        raise HTTPException(400, f"Telegram lehnt den Token ab: {safe(e, 200)}")
    _save_state(bot=str(me.get("username") or ""), offset=0)
    return admin_get()


@router.delete("/api/admin/telegram", dependencies=[Depends(auth), Depends(admin_code)])
def admin_delete():
    _save_state(token="", bot="", offset=0)
    return admin_get()


def _on():
    if not admin_on() or not token():
        raise HTTPException(403, "Telegram is turned off")


@router.get("/api/profile/telegram", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(own_profile)):
    lk = link(prof["id"])
    return {"enabled": bool(admin_on() and token()), "bot": _state().get("bot", ""),
            "linked": {"name": lk.get("name", ""), "since": lk.get("since")} if lk else None}


@router.post("/api/profile/telegram/link", dependencies=[Depends(assistant), Depends(_on)])
async def profile_link(request: Request, prof=Depends(secret_profile)):
    # a new way into the profile: only from its own browser login (never a shared device with a key),
    # with the second login step when the profile has it; from its iPhone app always with a fresh code
    code = new_code(prof["id"])
    bot = _state().get("bot", "")
    return {"code": code, "bot": bot, "url": f"https://t.me/{bot}?start={code}" if bot else "", "minutes": CODE_SECONDS // 60}


@router.delete("/api/profile/telegram", dependencies=[Depends(assistant)])
def profile_unlink(prof=Depends(browser_profile)):
    unlink(prof["id"])
    return profile_get(prof)
