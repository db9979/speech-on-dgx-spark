"""Anrufe: Sprache und Video zwischen zwei Profilen (Messenger Stufe D, plan plaene/messenger-d-v2.md, Dominik 2026-10-14
„1a 2b 3a 4a“: eigener Vermittler auf tars, Sprache und Video zusammen, Anrufe zu anderen Sparks später).

The call itself runs between the two devices (WebRTC in anrufe.js): sound and picture are encrypted end to end
(DTLS-SRTP), also when they go through the Vermittler. The Spark only brings the two together:
    start   the caller's device asks for a call in a chat of two (an ordinary or a private one, never with another
            Spark); every open Chats page of the other person rings, its devices get "📞 Name ruft an"
    answer  one device of the other person takes it; its other devices stop ringing
    signal  offer, answer and network candidates go through the Spark to the one device on the other side
    end     either side hangs up (or rejects); RING_SECS without an answer is a missed call
Every call leaves one line in its chat ("Anruf, 4:12" or "Verpasster Anruf"), never more.

Fixed rules (the panel decides, nothing from outside): both have Chats and Anrufe, the other takes messages from the
caller (Ich → Gespräch → Chats „Wer darf mir schreiben“), not in its quiet hours or "Nicht stören", one call per
person at a time, PER_HOUR calls per caller. What goes through the Spark is checked for form and size only and never
kept or logged (an SDP names network addresses).

Anrufe von unterwegs (chat.calls_turn): coturn on tars (unit speech-spark-turn, installed by install.sh), its settings
written here into STATE/turn.conf: one shared secret derived from the Spark's key, short-lived access per profile
(TURN REST: user "expiry:hash", HMAC-SHA1), UDP 3478 and RELAY_MIN..RELAY_MAX, and the relay never reaches an
address of the home network or tars itself (DENIED), only public ones. The address from outside (calls_turn_host)
is looked up through netguard.resolve(PUBLIC) for coturn's external-ip; when it changes, the unit restarts.
"""
import asyncio
import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections import deque

import features
import profiles
from common import DayCounter, STATE

RING_SECS = 45           # an unanswered call becomes a missed one
TALK_MAX = 4 * 3600      # a call that nobody ended ends by itself
PER_HOUR = 20            # calls a profile may start per hour
MAX_SIGNAL = 16 * 1024   # one offer, answer or candidate
CRED_SECS = 3600         # how long the Vermittler's access for a call works
TURN_PORT = 3478
RELAY_MIN, RELAY_MAX = 49160, 49200
TURN_UNIT = "speech-spark-turn"
TURN_BIN = "/usr/bin/turnserver"   # from the coturn package (install.sh); its unit only starts when it is there
CALL_ID = re.compile(r"[0-9a-f]{16}")
DEV = re.compile(r"[0-9a-f]{12}")
HOST = re.compile(r"(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
# the relay never reaches these: the home network, tars itself, special ranges (only public addresses remain)
DENIED = ("0.0.0.0-0.255.255.255", "10.0.0.0-10.255.255.255", "100.64.0.0-100.127.255.255", "127.0.0.0-127.255.255.255",
          "169.254.0.0-169.254.255.255", "172.16.0.0-172.31.255.255", "192.0.0.0-192.0.0.255", "192.0.2.0-192.0.2.255",
          "192.168.0.0-192.168.255.255", "198.18.0.0-198.19.255.255", "198.51.100.0-198.51.100.255",
          "203.0.113.0-203.0.113.255", "224.0.0.0-255.255.255.255", "::1", "::ffff:0:0-::ffff:ffff:ffff",
          "64:ff9b::-64:ff9b::ffff:ffff", "fc00::-fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff",
          "fe80::-febf:ffff:ffff:ffff:ffff:ffff:ffff:ffff")

_lock = threading.RLock()
_calls = {}              # call id -> {"a", "b", "cid", "video", "t", "state", "adev", "bdev", "talk"}
_started = {}            # uid -> deque of start times (PER_HOUR)
_count = DayCounter(calls=0, talked=0, missed=0, secs=0, voip=0)
_tkey = None             # the Vermittler's shared secret (cached; backup._forget_cached drops it)
_turn = {"conf": "", "ip": "", "on": False, "why": ""}


# ---------------------------------------------------------------- switches
def admin_on():
    return features.admin_on("anrufe")


def usable(uid):
    import chats
    return bool(chats.usable(uid) and features.allowed("anrufe", uid))


def cfg():
    return features.chat_cfg()


def turn_host(c=None):
    c = c or cfg()
    h = str(c.get("calls_turn_host") or "").strip().lower() or str(c.get("verbund_domain") or "").strip().lower()
    return h if HOST.fullmatch(h) else ""   # empty: the address other Sparks use


def turn_on(c=None):
    c = c or cfg()
    return bool(features.admin_on("anrufeturn", c) and turn_host(c))


features.READY["anrufeturn"] = lambda c: bool(turn_host(c))   # needs the address from outside


# ---------------------------------------------------------------- numbers for Live, words for the journal
def _log(what, **nums):
    """A journal line in the area of the chats: fixed words and numbers only (never a name, an address or an SDP)."""
    import chats
    chats._log("call " + what, **nums)


def _client(request):
    """"app" for the iPhone app's own key, else "web" (a browser login; the Android app's page is one)."""
    if request.headers.get(profiles.DEVICE_HEADER):
        return "app" if (profiles.device(request) or {}).get("scope") == "app" else "web"
    return "web"


def _kind(x, state):
    return ("Videoanruf" if x["video"] else "Anruf") + " · " + state


def _seen(x, client):
    """Live, Monitoring and the Steuerzentrale show a call under Geräte as one entry from ringing to the end
    (Dominik 2026-10-17): both kinds of device ("Browser ↔ iPhone-App"), sound or video, ringing or connected, and
    both people, each name only with its own consent (live._who); never the chat or a word of it."""
    import live
    x["aclient"] = client if client in ("web", "app") else "web"
    rec = live.begin(x["aclient"], "", uid=x["a"], why=_kind(x, "klingelt"))
    if rec is not None:
        rec.peer = x["b"]
        rec.label = live.CLIENT[x["aclient"]] + " ↔ …"
    return rec


def _talks(x, client):
    """The call was answered on a device of kind client: its entry says so."""
    import live
    rec = x.get("rec")
    if rec is not None:
        rec.intent = _kind(x, "verbunden")
        rec.label = live.CLIENT[x["aclient"]] + " ↔ " + live.CLIENT[client if client in ("web", "app") else "web"]


def _gone(x):
    import live
    live.end((x or {}).get("rec"))


def for_live():
    if not admin_on():
        return {"on": False}
    t = _count.today()
    with _lock:
        now = sum(1 for x in _calls.values() if x["state"] == "talk")
        ring = sum(1 for x in _calls.values() if x["state"] == "ring")
    return {"on": True, "talking": now, "ringing": ring, "today": t["calls"], "talked": t["talked"],
            "missed": t["missed"], "minutes": t["secs"] // 60, "iphone": t["voip"], "turn": turn_on(), "turn_ok": bool(_turn["on"]),
            "turn_why": _turn["why"]}


# ---------------------------------------------------------------- a call
def _other(uid, cid):
    """The other person of a chat of two on this Spark (an ordinary or a private chat)."""
    import chats
    c = chats._member(uid, cid)
    if c.get("kind") not in ("one", "priv"):
        raise ValueError("Anrufe gehen nur in einem Chat zu zweit.")
    other = next((u for u in c["members"] if u != uid), "")
    if not other or chats.RID.fullmatch(other) or not profiles.by_id(other):
        raise ValueError("Anrufe gehen nur in einem Chat zu zweit.")
    return other


def why_not(rcpt, caller):
    """Said to the caller: switched off, takes nothing from you, or busy; never why exactly."""
    import chats
    if not usable(caller):
        return "Anrufe sind für dich ausgeschaltet."
    if not usable(rcpt) or not chats.takes(rcpt, caller):
        return f"{chats.name_of(rcpt) or 'Diese Person'} nimmt gerade keine Anrufe von dir an."
    return ""


def _busy(uid):
    return any(x["state"] in ("ring", "talk") and uid in (x["a"], x["b"]) for x in _calls.values())


def _quiet(uid):
    """Quiet hours or "Nicht stören" (Begleiter): no ringing, the call is a missed one at once."""
    try:
        import room
        if room.night(uid):
            return True
    except Exception:
        pass
    try:
        import begleiter
        return begleiter.busy(uid)
    except Exception:
        return False


def _rate(uid, now):
    q = _started.setdefault(uid, deque())
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= PER_HOUR:
        return False
    q.append(now)
    return True


async def start(uid, cid, video, dev, now=None, client="web"):
    """A new call from uid's device dev in chat cid (client "web" or "app": the iPhone app); returns its id. Raises PermissionError/ValueError/OverflowError."""
    import chats
    now = time.time() if now is None else now
    if not usable(uid):
        raise PermissionError("Anrufe sind für dich ausgeschaltet.")
    other = _other(uid, cid)
    why = why_not(other, uid)
    if why:
        _log("refused", why="not taken")
        raise PermissionError(why)
    with _lock:
        if _busy(uid):
            _log("refused", why="own call")
            raise ValueError("Du telefonierst schon.")
        if not _rate(uid, now):
            _log("refused", why="limit")
            raise OverflowError(f"Höchstens {PER_HOUR} Anrufe pro Stunde.")
        call = secrets.token_hex(8)
        x = {"a": uid, "b": other, "cid": cid, "video": bool(video), "t": now, "state": "ring", "adev": dev, "bdev": "",
             "talk": 0.0}
        _calls[call] = x
        busy = any(y["state"] in ("ring", "talk") and other in (y["a"], y["b"]) for k, y in _calls.items() if k != call)
    x["rec"] = _seen(x, client)
    import rufen
    rufen.taken(uid, cid)   # a call the assistant kept for this chat (Anrufe per Assistent) is done
    _count.today()["calls"] += 1
    _live("📞 Anruf beginnt")
    if busy or _quiet(other):
        await end(other, call, "busy" if busy else "quiet", now=now)
        _log("not rung", why="busy" if busy else "quiet")
        return call, ("busy" if busy else "missed")
    chats._send_event(other, {"type": "call", "id": cid, "call": call, "from": uid, "name": chats.name_of(uid),
                              "video": bool(video)})
    _log("started", video=int(bool(video)))
    await _voip(other, call)
    if not chats.listening(other):
        await _push(other, uid, video)
    spawn(_ring_out(call, now))
    return call, "ring"


async def _push(other, caller, video):
    """"📞 Name ruft an" to every device of the other person (none during its quiet hours, see start)."""
    try:
        import chats
        import push
        if not push.reachable(other, private=True):
            _log("push skipped", why="no device")
            return
        n = await push.send(other, ("🎥 " if video else "📞 ") + (chats.name_of(caller) or "Jemand"),
                            "ruft an", tag="call", private=True, why="Anruf", to="every")
        _log("push", sent=int(n or 0))
    except Exception as e:
        _log("push failed", error=type(e).__name__)


async def _voip(other, call):
    """The iPhones of the other person ring like a phone call (CallKit), also locked or with the app closed: Apple
    carries only the call's random id; the app asks the Spark who calls (/api/anrufe/info)."""
    try:
        import apns
        n = await apns.send_voip(other, call)
        if n:
            _count.today()["voip"] += 1
            _log("voip", sent=n)
    except Exception as e:
        _log("voip failed", error=type(e).__name__)


def info(uid, call):
    """What the app needs for its call screen: the chat, who calls, sound or video and the state. Only for the two
    people of the call; an ended or unknown call is "end", so a late VoIP push still shows and closes at once."""
    import chats
    with _lock:
        x = _calls.get(call)
        if not x or uid not in (x["a"], x["b"]):
            return {"call": call, "state": "end"}
        other = x["b"] if uid == x["a"] else x["a"]
        out = {"call": call, "id": x["cid"], "video": x["video"], "state": x["state"], "mine": uid == x["a"]}
    out["name"] = chats.name_of(other) or ""
    return out


def spawn(coro):
    try:
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()


async def _ring_out(call, t0):
    await asyncio.sleep(RING_SECS)
    with _lock:
        x = _calls.get(call)
        missed = bool(x and x["state"] == "ring" and x["t"] == t0)
    if missed:
        await end(x["b"], call, "missed")


def _get(uid, call):
    x = _calls.get(call)
    if not x or uid not in (x["a"], x["b"]) or x["state"] == "end":
        raise LookupError("no such call")
    return x


def answer(uid, call, dev, now=None, client="web"):
    """The called person's device dev (client "web" or "app") takes the call."""
    import chats
    now = time.time() if now is None else now
    with _lock:
        x = _get(uid, call)
        if uid != x["b"] or x["state"] != "ring":
            raise LookupError("no such call")
        x.update(state="talk", bdev=dev, talk=now)
    _talks(x, client)
    chats._send_event(x["a"], {"type": "call_ok", "id": x["cid"], "call": call, "dev": dev})
    chats._send_event(x["b"], {"type": "call_taken", "id": x["cid"], "call": call, "dev": dev})
    _count.today()["talked"] += 1
    _live("📞 Anruf angenommen")
    _log("answered", secs=int(now - x["t"]))
    return x


def _check_signal(data):
    """An offer or answer ({"sdp": {"type", "sdp"}}) or one network candidate ({"ice": {...}}): form and size only."""
    if not isinstance(data, dict) or len(data) != 1:
        raise ValueError("bad signal")
    if "sdp" in data:
        s = data["sdp"]
        if not isinstance(s, dict) or set(s) != {"type", "sdp"} or s["type"] not in ("offer", "answer") \
                or not isinstance(s["sdp"], str) or not s["sdp"].startswith("v=0") or len(s["sdp"]) > MAX_SIGNAL:
            raise ValueError("bad signal")
        return {"sdp": {"type": s["type"], "sdp": s["sdp"]}}
    if "ice" in data:
        c = data["ice"]
        if not isinstance(c, dict) or set(c) - {"candidate", "sdpMid", "sdpMLineIndex", "usernameFragment"}:
            raise ValueError("bad signal")
        if not isinstance(c.get("candidate", ""), str) or len(c.get("candidate", "")) > 1024:
            raise ValueError("bad signal")
        if c.get("sdpMid") is not None and (not isinstance(c["sdpMid"], str) or len(c["sdpMid"]) > 32):
            raise ValueError("bad signal")
        if c.get("sdpMLineIndex") is not None and (not isinstance(c["sdpMLineIndex"], int) or not 0 <= c["sdpMLineIndex"] < 16):
            raise ValueError("bad signal")
        if c.get("usernameFragment") is not None and (not isinstance(c["usernameFragment"], str) or len(c["usernameFragment"]) > 256):
            raise ValueError("bad signal")
        return {"ice": dict(c)}
    raise ValueError("bad signal")


def signal(uid, call, dev, data):
    """Passes one signal of uid's device on to the device on the other side; only the two devices of a call talk."""
    import chats
    clean = _check_signal(data)
    with _lock:
        x = _get(uid, call)
        if x["state"] != "talk":
            raise LookupError("no such call")
        mine, theirs, to = (("adev", "bdev", x["b"]) if uid == x["a"] else ("bdev", "adev", x["a"]))
        if x[mine] != dev:
            raise PermissionError("Dieser Anruf läuft auf einem anderen Gerät.")
    chats._send_event(to, {"type": "call_sig", "id": x["cid"], "call": call, "to": x[theirs], "data": clean})


async def end(uid, call, why="hangup", now=None):
    """Ends the call (hang up, reject, missed, busy, quiet); one line in the chat, both sides hear it."""
    import chats
    now = time.time() if now is None else now
    with _lock:
        x = _calls.get(call)
        if not x or uid not in (x["a"], x["b"]) or x["state"] == "end":
            raise LookupError("no such call")
        talked = x["state"] == "talk"
        x["state"] = "end"
        _calls.pop(call, None)
    _gone(x)
    secs = int(now - x["talk"]) if talked else 0
    if talked:
        _count.today()["secs"] += secs
        what, extra = "call", {"secs": secs, "video": x["video"]}
        _log("ended", secs=secs)
    else:
        if why in ("missed", "busy", "quiet") or (why == "hangup" and uid == x["a"]):
            _count.today()["missed"] += 1
            what = "call_missed"
        else:
            what = "call_rejected"
        extra = {"video": x["video"]}
        _log("not answered", why={"hangup": "caller hung up", "reject": "rejected"}.get(why, why))
    for u in (x["a"], x["b"]):
        chats._send_event(u, {"type": "call_end", "id": x["cid"], "call": call, "why": why})

    def f(meta, d, idx):
        chats._sys(d, x["a"], now, what, [x["b"]], **extra)
        meta["updated"] = now
        return meta["members"]
    try:
        chats._tell(chats._mutate(x["cid"], f, now), {"type": "chat", "id": x["cid"]})
    except LookupError:
        pass
    _live("📞 Anruf beendet" if talked else "📞 Anruf nicht angenommen")
    return what


def tidy(now=None):
    """Calls to end now: all of them when the admin switched Anrufe off, else those nobody ended (a closed browser)
    after TALK_MAX, and ringing ones whose timer got lost (a restart) after RING_SECS."""
    now = time.time() if now is None else now
    off = not admin_on()
    with _lock:
        return [(k, x["a"]) for k, x in _calls.items() if off
                or x["state"] == "talk" and now - x["talk"] > TALK_MAX
                or x["state"] == "ring" and now - x["t"] > RING_SECS + 30]


def forget(uid):
    """A deleted profile: its calls end without a line."""
    with _lock:
        for k in [k for k, x in _calls.items() if uid in (x["a"], x["b"])]:
            _gone(_calls.pop(k, None))
        _started.pop(uid, None)


def _live(text):
    try:
        import live
        live.mark("Chats", text)
    except Exception:
        pass


# ---------------------------------------------------------------- the Vermittler (TURN)
def _secret():
    global _tkey
    if _tkey:
        return _tkey
    import vault
    vault._key()
    with open(vault.KEY_FILE, "rb") as f:
        base = f.read().strip()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    _tkey = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"speech-spark turn v1").derive(base).hex()
    return _tkey


def ice(uid, now=None):
    """The servers a device of uid uses for one call: none in the home network alone; with the Vermittler its
    address and an access that works CRED_SECS (TURN REST: user "expiry:hash of the profile", HMAC-SHA1)."""
    now = time.time() if now is None else now
    if not turn_on():
        return []
    host = turn_host()
    user = f"{int(now) + CRED_SECS}:{hashlib.sha256(('turn|' + uid).encode()).hexdigest()[:12]}"
    cred = base64.b64encode(hmac.new(_secret().encode(), user.encode(), hashlib.sha1).digest()).decode()
    return [{"urls": [f"stun:{host}:{TURN_PORT}"]},
            {"urls": [f"turn:{host}:{TURN_PORT}?transport=udp", f"turn:{host}:{TURN_PORT}?transport=tcp"],
             "username": user, "credential": cred}]


def turn_conf(host, ip, state):
    """coturn's settings: only short-lived access, no admin console, no TLS (the media are encrypted anyway), the
    relay only to public addresses, quotas per person and in total, no log of addresses."""
    lines = [f"listening-port={TURN_PORT}", f"min-port={RELAY_MIN}", f"max-port={RELAY_MAX}", "fingerprint",
             "use-auth-secret", f"static-auth-secret={_secret()}", f"realm={host}", f"external-ip={ip}",
             "no-tls", "no-dtls", "no-cli", "no-multicast-peers", "no-tcp-relay", "user-quota=4", "total-quota=40",
             "max-bps=4000000", "stale-nonce=600", "log-file=/dev/null", "simple-log", "no-stdout-log",
             f"pidfile={os.path.join(state, 'turn.pid')}"]
    lines += [f"denied-peer-ip={r}" for r in DENIED]
    # the Spark's own addresses too (its public IPv6 address and the address from outside are not in DENIED)
    lines += [f"denied-peer-ip={a}" for a in sorted({str(a) for a in _own()} | {ip}) if a]
    return "\n".join(lines) + "\n"


def _own():
    import netguard
    return netguard.own_addresses()


def _state_dir():
    return STATE


def _systemctl(action):
    from core import run
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", action, TURN_UNIT], timeout=60)
    return code == 0


def _installed():
    return os.path.exists(TURN_BIN)


def _active():
    from core import run
    return run(["systemctl", "is-active", TURN_UNIT])[1].split("\n")[0].strip() == "active"


def outside_ip(host):
    """The public IPv4 address coturn names as its own (external-ip) and "", or "" and the reason in fixed words.
    Only IPv4: an extra IPv6 record of the name (often a home-only fd… address) must not stop the relay. Nothing
    connects to this address, so one public address among them is enough; the relay's peers stay limited by DENIED."""
    import socket
    import netguard
    try:
        found = sorted({i[4][0] for i in socket.getaddrinfo(host, TURN_PORT, socket.AF_INET, socket.SOCK_DGRAM)})
    except (OSError, UnicodeError):
        return "", "not found"
    whys = [netguard.allowed(a, TURN_PORT, netguard.PUBLIC) for a in found]
    for a, w in zip(found, whys):
        if not w:
            return a, ""
    if not found:
        return "", "not found"
    return "", "notaus" if any(str(w).startswith("Notaus") for w in whys) else "home address"


def _conf_ip(path):
    """external-ip of the settings written before (after a panel restart), only a public IPv4 address."""
    import ipaddress
    try:
        with open(path) as f:
            m = re.search(r"^external-ip=([0-9.]{7,15})$", f.read(), re.M)
        return m.group(1) if m and ipaddress.ip_address(m.group(1)).is_global else ""
    except (OSError, ValueError):
        return ""


def relay_ok():
    """For the Dienst-Wächter: the Vermittler runs with the settings written here."""
    return bool(_turn["on"]) and _active()


def apply_turn():
    """Brings the unit to what the switches say: settings written and running, or stopped. Returns the state word."""
    path = os.path.join(_state_dir(), "turn.conf")
    if not turn_on():
        _turn.update(on=False, why="")
        if _turn["conf"] or os.path.exists(path):
            _systemctl("stop")
            try:
                os.remove(path)
            except OSError:
                pass
            _turn.update(conf="", ip="")
            _log("relay stopped")
        return "off"
    if not _installed():     # coturn missing (an update could not install it): say so, never start a unit in vain
        if _turn["why"] != "coturn fehlt":
            _log("relay refused", why="not installed")
        _turn.update(on=False, why="coturn fehlt")
        return "missing"
    host = turn_host()
    ip, why = outside_ip(host)
    if not ip:
        old = _turn["ip"] or _conf_ip(path)
        if old and _active():   # the name fails for a moment (or shows an odd address): the running relay keeps its last one
            if _turn["why"] != "alte Adresse":
                _log("relay kept", why=why)
            _turn.update(on=True, ip=old, why="alte Adresse")
            return "on"
        text = {"home address": "Adresse von außen zeigt ins Heimnetz",
                "notaus": "Notaus: kein Internet"}.get(why, "Adresse von außen nicht gefunden")
        if _turn["why"] != text:   # once per reason, not every minute
            _log("relay refused", why=why)
        _turn.update(on=False, why=text)
        return "noip"
    conf = turn_conf(host, ip, _state_dir())
    if conf != _turn["conf"] or not _active():
        old = None
        try:
            with open(path) as f:
                old = f.read()
        except OSError:
            pass
        if old != conf:
            fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(conf)
            os.replace(path + ".tmp", path)
        ok = _systemctl("restart")
        _turn.update(conf=conf if ok else "", ip=ip, on=ok, why="" if ok else "Vermittler startet nicht")
        _log("relay started" if ok else "relay failed", changed=int(old != conf))
        return "on" if ok else "failed"
    if _turn["why"]:
        _log("relay back")
    _turn.update(on=True, why="")
    return "on"


async def loop():
    """Every minute: the Vermittler as the switches say (and a new address from outside), calls nobody ended."""
    while True:
        try:
            await asyncio.to_thread(apply_turn)
            for call, uid in tidy():
                await end(uid, call, "hangup")
        except Exception as e:
            _log("loop failed", error=type(e).__name__)
        await asyncio.sleep(60)


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from core import assistant, json_body, own_profile  # noqa: E402

router = APIRouter()


def _on(request: Request, prof=Depends(own_profile)):
    """The profile's own browser login (the Android app's page is one) or the iPhone app's own key (WebRTC and CallKit
    in the app, V01.0.652): camera and microphone live there. No other device key (speakers, watches, terminals)."""
    import guard
    if request.headers.get(profiles.DEVICE_HEADER) and (profiles.device(request) or {}).get("scope") != "app":
        _log("refused", why="device key")
        raise HTTPException(403, "only in the profile's own browser login or the iPhone app")
    if not admin_on():
        _log("refused", why="off")
        raise HTTPException(403, "Anrufe sind auf dem Spark aus.")
    if not usable(prof["id"]):
        _log("refused", why="not for the profile")
        raise HTTPException(403, ("Anrufe gehen für dich gerade nicht. " + features.missing_text("anrufe", prof["id"])).strip())
    guard.limit(request, "anrufe", prof["id"])
    return prof


def _ids(body, call=True):
    dev = str(body.get("dev") or "")
    if not DEV.fullmatch(dev):
        raise HTTPException(400, "device id is required")
    if not call:
        return dev
    c = str(body.get("call") or "")
    if not CALL_ID.fullmatch(c):
        raise HTTPException(400, "call id is required")
    return c, dev


def _err(e):
    import chats
    return chats._err(e)


@router.get("/api/anrufe/ice", dependencies=[Depends(assistant)])
def api_ice(request: Request, prof=Depends(_on)):
    return {"servers": ice(prof["id"]), "ring": RING_SECS}


@router.get("/api/anrufe/info", dependencies=[Depends(assistant)])
def api_info(request: Request, call: str = "", prof=Depends(_on)):
    if not CALL_ID.fullmatch(call or ""):
        raise HTTPException(400, "call id is required")
    out = info(prof["id"], call)
    if out["state"] == "end":
        _log("info", state="end")
    return out


@router.post("/api/anrufe/start", dependencies=[Depends(assistant)])
async def api_start(request: Request, prof=Depends(_on)):
    import chats
    body = await json_body(request, 1024)
    dev = _ids(body, call=False)
    try:
        call, state = await start(prof["id"], chats._cid(body.get("id")), body.get("video") is True, dev,
                                  client=_client(request))
    except (PermissionError, ValueError, OverflowError, LookupError) as e:
        if isinstance(e, LookupError):
            _log("refused", why="no chat")
        raise _err(e)
    return {"call": call, "state": state, "servers": ice(prof["id"])}


@router.delete("/api/anrufe/bereit", dependencies=[Depends(assistant)])
def api_ready_off(request: Request, prof=Depends(_on)):
    """„Nein“ on the bar of a call the assistant kept for the person (rufen.py): it goes away on every device."""
    import rufen
    return {"ok": rufen.decline(prof["id"])}


@router.post("/api/anrufe/answer", dependencies=[Depends(assistant)])
async def api_answer(request: Request, prof=Depends(_on)):
    call, dev = _ids(await json_body(request, 1024))
    try:
        x = answer(prof["id"], call, dev, client=_client(request))
    except LookupError as e:
        _log("answer refused", why="no call")
        raise _err(e)
    return {"call": call, "video": x["video"], "servers": ice(prof["id"])}


@router.post("/api/anrufe/signal", dependencies=[Depends(assistant)])
async def api_signal(request: Request, prof=Depends(_on)):
    body = await json_body(request, MAX_SIGNAL + 2048)
    call, dev = _ids(body)
    try:
        signal(prof["id"], call, dev, body.get("data"))
    except (LookupError, PermissionError, ValueError) as e:
        _log("signal refused", why=type(e).__name__)
        raise _err(e)
    return {"ok": True}


@router.post("/api/anrufe/end", dependencies=[Depends(assistant)])
async def api_end(request: Request, prof=Depends(_on)):
    body = await json_body(request, 1024)
    call, _ = _ids(body)
    why = body.get("why") if body.get("why") in ("hangup", "reject") else "hangup"
    try:
        what = await end(prof["id"], call, why)
    except LookupError as e:
        _log("end refused", why="no call")
        raise _err(e)
    return {"ok": True, "line": what}
