"""Home Assistant live (Vorrat je Profil, stage C, Dominik 2026-10-20 „alle Punkte umsetzen“): for profiles that used the
panel lately, one WebSocket connection to their own Home Assistant keeps a copy of every state in memory, updated by
Home Assistant itself (subscribe_events state_changed). „Ist das Fenster offen?“, the states tool, history and switching
look up devices in that copy instead of reading GET /api/states (often several hundred KB) for every question.

- No switch of its own: it follows the release of Home Assistant (features.allowed("ha")), never for guests, never while
  Mein Notaus (kind auto) holds the profile. Only profiles active in the last ACTIVE_SECONDS (vorrat.active), newest
  first, at most MAX_OPEN connections on the whole Spark.
- Only reading: the connection asks get_states once and then only listens; it never calls a service. Switching keeps
  its own way (Assist, services, the read-back of the one entity over HTTP).
- The address goes through netguard (HOME rules, the checked IP is the one connected to), TLS like the profile set it,
  the token only to that address. One thread per connection waits on its socket, so it costs no time on the panel's
  loop; a lost connection is tried again after BACKOFF seconds, doubling up to BACKOFF_MAX. A connection that stayed
  up STABLE seconds after its copy was complete counts as good: lost then, it is tried again after SOON seconds and
  the doubling starts anew (2026-11-04: once five losses had come together, every later one waited BACKOFF_MAX,
  because only a session that ended on purpose reset the wait). A WebSocket ping every PING seconds (an answer within
  PING_WAIT) and TCP keepalive keep proxies and routers (a Synology reverse proxy, NAT) from dropping a quiet line;
  the journal names the close code as a number (1006: closed without a close frame) and how long it was up.
- What Home Assistant sends is data, as before: states are kept as they come (at most MAX_ENTITIES, MAX_MESSAGE bytes
  per message) and wrapped for the model by the tools like the HTTP answer.
- Logs: fixed words and numbers, the profile only as profiles.log_name; Live (node Home Assistant): connections open,
  state changes today. Nothing is written to disk.
"""
import json
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

import features
import netguard
import notaus
import profiles
from common import DayCounter

MAX_OPEN = 4                # connections on the whole Spark
ACTIVE_SECONDS = 24 * 3600  # profiles active in this time get one (vorrat.active)
MAX_ENTITIES = 5000
MAX_MESSAGE = 8 * 1024 * 1024
WAIT = 5                    # seconds one recv waits before it looks at the stop flag again
BACKOFF, BACKOFF_MAX = 60, 900
STABLE = 300                # seconds up (after the copy was complete) that make a connection a good one
SOON = 10                   # seconds before a good connection that was lost is tried again
PING, PING_WAIT = 20, 30    # WebSocket keepalive: a ping every PING seconds, lost without a pong within PING_WAIT
EVERY = 60                  # seconds between two looks of the supervisor (loop)

_open = {}                  # uid -> _Live
_lock = threading.Lock()
_count = DayCounter(aenderungen=0, verbindungen=0)


def states(item):
    """The copy of every state for this Home Assistant connection (a list of state dicts), or None when there is no live
    connection with a complete copy for exactly this address and token (then the caller asks over HTTP)."""
    uid = item.get("_uid")
    with _lock:
        w = _open.get(uid)
    if not w or not w.synced or w.url != item.get("url") or w.token != item.get("token"):
        return None
    with w.lock:
        return list(w.states.values())


def wanted(now=None):
    """[uid] that should have a connection now: newest first, at most MAX_OPEN."""
    import homeassistant
    import vorrat
    out = []
    for uid in vorrat.active(now):
        if len(out) >= MAX_OPEN:
            break
        if features.allowed("ha", uid) and not notaus.blocks("auto", uid) and homeassistant.get(uid):
            out.append(uid)
    return out


def look(now=None):
    """The supervisor: opens what is wanted and closes what is not any more. Returns (open, started, stopped)."""
    import homeassistant
    want = set(wanted(now))
    started = stopped = 0
    with _lock:
        for uid, w in list(_open.items()):
            item = homeassistant.get(uid) if uid in want else None
            if not item or not w.alive() or w.url != item["url"] or w.token != item["token"]:
                w.stop()
                _open.pop(uid, None)
                stopped += 1
        for uid in want:
            if uid not in _open:
                _open[uid] = _Live(uid, homeassistant.get(uid))
                _open[uid].start()
                started += 1
        n = len(_open)
    if started or stopped:
        print(f"homeassistant: live looked | {n} open, {started} started, {stopped} stopped", flush=True)
    return n, started, stopped


def stop_all():
    with _lock:
        for w in _open.values():
            w.stop()
        _open.clear()


async def loop():
    """Started with the panel; every EVERY seconds one look (in a thread: reading the settings is file work)."""
    import asyncio
    while True:
        await asyncio.sleep(EVERY)
        try:
            await asyncio.to_thread(look)
        except Exception as e:
            print(f"homeassistant: live look failed ({type(e).__name__})", flush=True)


def for_live():
    """Zustand → Live, node Home Assistant: live connections and state changes today (numbers, never who or which)."""
    with _lock:
        n = sum(1 for w in _open.values() if w.synced)
    c = _count.counts()
    return {"open": n, "changes": c["aenderungen"]}


def backoff(wait, up):
    """(seconds to wait now, the wait after that) once a connection is lost that was up `up` seconds after its copy
    was complete (0: it never was): a good one is tried again soon and the doubling starts anew."""
    if up >= STABLE:
        return SOON, BACKOFF
    return wait, min(BACKOFF_MAX, wait * 2)


def close_code(e):
    """The WebSocket close code of a lost connection as a number: the one Home Assistant (or a proxy) sent, 1006 when
    the line ended without a close frame, 0 for any other error (a refused address, a time-out on connecting)."""
    if not hasattr(e, "rcvd"):
        return 0
    code = getattr(e.rcvd, "code", None)
    return int(code) if isinstance(code, int) else 1006


def apply(store, msg):
    """One message of Home Assistant into the copy: the answer to get_states (id 1) fills it, a state_changed event
    changes one entity. Returns "synced", "changed" or "". Anything else is left alone."""
    if not isinstance(msg, dict):
        return ""
    if msg.get("type") == "result" and msg.get("id") == 1 and msg.get("success") and isinstance(msg.get("result"), list):
        store.clear()
        for s in msg["result"][:MAX_ENTITIES]:
            if isinstance(s, dict) and isinstance(s.get("entity_id"), str):
                store[s["entity_id"]] = s
        return "synced"
    if msg.get("type") != "event":
        return ""
    data = (msg.get("event") or {}).get("data") or {}
    eid = data.get("entity_id")
    if not isinstance(eid, str):
        return ""
    new = data.get("new_state")
    if new is None:
        store.pop(eid, None)
    elif isinstance(new, dict) and (eid in store or len(store) < MAX_ENTITIES):
        store[eid] = new
    else:
        return ""
    return "changed"


def keepalive(sock):
    """TCP keepalive on the socket (where the system offers it): a router or NAT between the Spark and Home Assistant
    keeps a quiet line; a dead one is noticed after about two minutes. Never raises."""
    opts = ((socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),) + tuple(
        (socket.IPPROTO_TCP, getattr(socket, n), v) for n, v in (("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 20), ("TCP_KEEPCNT", 3))
        if hasattr(socket, n))
    for level, opt, value in opts:
        try:
            sock.setsockopt(level, opt, value)
        except OSError:
            pass


class _Live(threading.Thread):
    """One WebSocket connection to one Home Assistant; ends when stop() is called."""

    def __init__(self, uid, item):
        super().__init__(name="ha-live", daemon=True)
        self.uid, self.url, self.token, self.verify = uid, item["url"], item["token"], item.get("verify", True)
        self.states, self.lock = {}, threading.Lock()
        self.synced = False
        self._halt = threading.Event()
        self.ws = None
        self.since = 0.0            # clock() when the copy became complete, 0 while it is not
        self.clock = time.monotonic

    def alive(self):
        return self.is_alive() and not self._halt.is_set()

    def stop(self):
        self._halt.set()
        self.synced = False
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass

    def up(self):
        """Whole seconds since the copy became complete, 0 when it never did on this connection."""
        return int(self.clock() - self.since) if self.since else 0

    def run(self):
        name = profiles.log_name(profiles.by_id(self.uid))
        wait = BACKOFF
        while not self._halt.is_set():
            self.since = 0.0
            try:
                self._session(name)
                now, wait = BACKOFF, BACKOFF   # ended on purpose (token refused, Notaus): the next try waits BACKOFF
            except Exception as e:
                if self._halt.is_set():
                    break
                up = self.up()
                now, wait = backoff(wait, up)
                code = close_code(e)
                print(f"homeassistant: live lost ({type(e).__name__})" + (f" | code {code}" if code else "")
                      + f" | up {up} s | retry in {now} s | {name}", flush=True)
            self.synced = False
            if self._halt.wait(now):
                break

    def _connect(self):
        from websockets.sync.client import connect
        u = urlsplit(self.url)
        tls = u.scheme == "https"
        port = u.port or (443 if tls else 80)
        ip = netguard.resolve(u.hostname, port, netguard.HOME)   # the checked address is the one connected to
        sock = socket.create_connection((ip, port), 10)
        keepalive(sock)
        ctx = None
        if tls:
            ctx = ssl.create_default_context()
            if not self.verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
        path = (u.path or "").rstrip("/") + "/api/websocket"
        return connect(f"{'wss' if tls else 'ws'}://{u.netloc.rsplit('@', 1)[-1]}{path}", sock=sock, ssl=ctx,
                       server_hostname=u.hostname if tls else None, max_size=MAX_MESSAGE, open_timeout=10,
                       ping_interval=PING, ping_timeout=PING_WAIT, close_timeout=5,
                       proxy=None, user_agent_header=None, compression=None)

    def _session(self, name):
        with self._connect() as ws:
            self.ws = ws
            self._listen(ws, name)

    def _listen(self, ws, name):
        try:
            hello = json.loads(ws.recv(timeout=10))
            if hello.get("type") != "auth_required":
                raise ValueError("no auth request")
            ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            if json.loads(ws.recv(timeout=10)).get("type") != "auth_ok":
                print(f"homeassistant: live refused (token) | {name}", flush=True)
                self._halt.wait(BACKOFF_MAX)
                return
            ws.send(json.dumps({"id": 1, "type": "get_states"}))
            ws.send(json.dumps({"id": 2, "type": "subscribe_events", "event_type": "state_changed"}))
            _count.bump("verbindungen")
            while not self._halt.is_set():
                try:
                    raw = ws.recv(timeout=WAIT)
                except TimeoutError:
                    continue
                if notaus.blocks("auto", self.uid):
                    print(f"homeassistant: live stopped, notaus | {name}", flush=True)
                    self._halt.set()
                    break
                with self.lock:
                    got = apply(self.states, json.loads(raw))
                if got == "synced":
                    self.synced = True
                    self.since = self.since or self.clock()
                    print(f"homeassistant: live connected | {len(self.states)} entities | {name}", flush=True)
                elif got == "changed":
                    _count.bump("aenderungen")
        finally:
            self.synced = False
