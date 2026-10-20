"""Neue Mails sofort (Vorwärmen Stufe C, Dominik 2026-10-19 „6a“, 2026-10-20 „alles so umsetzen“): IMAP IDLE for the
inboxes of profiles that read their mail lately, so new mail is on the page E-Mail within seconds and the profile's
Mail-Regeln take it at once instead of at the next five-minute look.

- Off until the admin switches chat.mail_idle on (Funktionen → E-Mail lesen → „Neue Mails sofort“); then for every
  profile that may read mail (features.allowed, the admin can block single profiles), never for guests.
- Only for profiles that read their mail in the last ACTIVE_SECONDS (mail._used), newest first, and at most MAX_OPEN
  connections on the whole Spark; a server without IDLE is left to mail.keep_fresh (asked again after a day).
- Only reading: the inbox is opened with EXAMINE, the IDLE connection itself never changes a message. On EXISTS or
  EXPUNGE (a new mail, or one moved in another program) the profile's rules run (mailregeln.run, with „Mails
  ordnen“), the page's listing is fetched anew with the newest messages ahead (mail.warm) and LISTENERS hear it
  (Für dich); at most every QUIET seconds per profile, and only while nobody speaks (vorrang.hold).
- One thread per connection that waits in select() on its socket, so it holds no lock and costs no time on the
  panel's loop; IDLE is renewed every RENEW seconds (servers end it after 29 minutes), a lost connection is tried
  again after BACKOFF seconds, doubling up to BACKOFF_MAX. Mein Notaus (kind auto) and the switch close it.
- What a server sends is data: only the words EXISTS, EXPUNGE, BYE and the tagged answer are looked at.
- Logs: fixed words and numbers, the profile only as profiles.log_name; Live: connections open, new mails today.
"""
import imaplib
import select
import threading
import time

import features
import mail
import notaus
import profiles
import vorrang
from common import DayCounter

MAX_OPEN = 4                # IDLE connections on the whole Spark (the Pi keeps few sockets and threads)
ACTIVE_SECONDS = 2 * 3600   # profiles that read their mail in this time get one
RENEW = 24 * 60             # seconds until IDLE is ended and started again
WAIT = 30                   # seconds one select() waits before it looks at the stop flag again
QUIET = 20                  # seconds between two refreshes of one profile
BACKOFF, BACKOFF_MAX = 60, 900
NO_IDLE_AGAIN = 24 * 3600   # a server without IDLE is asked again after this
EVERY = 60                  # seconds between two looks of the supervisor (loop)
LINE_MAX = 64 * 1024        # a line a server sends while idling; longer is a broken connection
LISTENERS = []              # fn(uid) called after new mail came (Für dich); errors there never stop the connection

_open = {}                  # (uid, account id) -> _Watch
_no_idle = {}               # account id -> when its server said it has no IDLE
_lock = threading.Lock()
_count = DayCounter(neu=0, verbindungen=0)


def on_new(fn):
    """Für dich and others: fn(uid) after new mail came into one of the profile's inboxes."""
    if fn not in LISTENERS:
        LISTENERS.append(fn)


def wanted(now=None):
    """[(uid, account)] that should have a connection now: newest readers first, at most MAX_OPEN."""
    now = time.time() if now is None else now
    if not features.chat_cfg().get("mail_idle"):
        return []
    out = []
    for uid, seen in sorted(mail._used.items(), key=lambda x: -x[1]):
        if now - seen > ACTIVE_SECONDS or not features.allowed("mailidle", uid) or notaus.blocks("auto", uid):
            continue
        for a in mail.get(uid)["accounts"]:
            if len(out) >= MAX_OPEN:
                return out
            if now - _no_idle.get(a["id"], 0) >= NO_IDLE_AGAIN:
                out.append((uid, a))
    return out


def look(now=None):
    """The supervisor: opens what is wanted and closes what is not any more. Returns (open, started, stopped)."""
    want = {(uid, a["id"]): (uid, a) for uid, a in wanted(now)}
    started = stopped = 0
    with _lock:
        for key, w in list(_open.items()):
            if key not in want or not w.alive() or w.acct != want[key][1]:
                w.stop()
                _open.pop(key, None)
                stopped += 1
        for key, (uid, a) in want.items():
            if key not in _open:
                _open[key] = _Watch(uid, a)
                _open[key].start()
                started += 1
        n = len(_open)
    if started or stopped:
        print(f"mail: idle looked | {n} open, {started} started, {stopped} stopped", flush=True)
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
            print(f"mail: idle look failed ({type(e).__name__})", flush=True)


def for_live():
    """Zustand → Live, node E-Mail: connections open and new mails today (numbers, never who or which)."""
    with _lock:
        n = sum(1 for w in _open.values() if w.idling)
    return {"on": bool(features.chat_cfg().get("mail_idle")), "open": n, "new": _count.counts()["neu"]}


def news(uid):
    """New mail (or a mail gone) in one of the profile's inboxes: its rules, its listing, the listeners."""
    name = profiles.log_name(profiles.by_id(uid))
    vorrang.hold("mailidle")
    if features.allowed("mailmanage", uid) and not notaus.blocks("auto", uid):
        import mailregeln
        try:
            mailregeln.run(uid)
        except notaus.NotausAktiv:
            print(f"mail: idle rules not run, notaus | {name}", flush=True)
    mail.changed(uid, "", "back")   # the cached listings are fetched anew
    n = mail.warm(uid)
    for fn in list(LISTENERS):
        try:
            fn(uid)
        except Exception as e:
            print(f"mail: idle listener failed ({type(e).__name__}) | {name}", flush=True)
    print(f"mail: idle news | {n} messages ahead | {name}", flush=True)


class _Watch(threading.Thread):
    """One IDLE connection to one inbox; ends when stop() is called, the switch goes off or Notaus stops it."""

    def __init__(self, uid, acct):
        super().__init__(name="mail-idle", daemon=True)
        self.uid, self.acct = uid, acct
        self.halt = threading.Event()
        self.idling = False
        self.last = 0.0
        self.waiting = False      # a change came within QUIET of the last refresh: handled once QUIET is over
        self.tag = 0

    def alive(self):
        return self.is_alive() and not self.halt.is_set()

    def stop(self):
        self.halt.set()

    def run(self):
        name = profiles.log_name(profiles.by_id(self.uid))
        wait = BACKOFF
        while not self.halt.is_set():
            try:
                why = self._session()
            except (ValueError, OSError, imaplib.IMAP4.error, EOFError) as e:
                why = f"lost ({type(e).__name__})"
            self.idling = False
            if why == "stopped":
                print(f"mail: idle stopped | {name}", flush=True)
                return
            if why == "no idle":
                _no_idle[self.acct["id"]] = time.time()
                print(f"mail: idle not offered, kept fresh every 5 min | {name}", flush=True)
                self.halt.set()
                return
            print(f"mail: idle {why}, again in {wait} s | {name}", flush=True)
            if self.halt.wait(wait):
                print(f"mail: idle stopped | {name}", flush=True)
                return
            wait = min(wait * 2, BACKOFF_MAX)

    def _session(self):
        with mail._Session(self.acct) as s:
            typ, data = s.c.capability()
            caps = b" ".join(x for x in data if isinstance(x, bytes)).upper().split() if typ == "OK" else []
            if b"IDLE" not in caps:
                return "no idle"
            lines = _Lines(s.c.sock)
            _count.bump("verbindungen")
            print(f"mail: idle open | {profiles.log_name(profiles.by_id(self.uid))}", flush=True)
            while not self.halt.is_set():
                why = self._idle(lines)
                if why != "renew":
                    return why
            return "stopped"

    def _idle(self, lines):
        """One IDLE until RENEW, a stop, or a change; a change is handled while the server keeps the IDLE open."""
        self.tag += 1
        tag = b"SPK%d" % self.tag
        lines.send(tag + b" IDLE")
        first = lines.next(WAIT)
        while first is not None and first.startswith(b"* "):    # news the server had queued before its „+“
            if first.upper().split()[2:3] in ([b"EXISTS"], [b"EXPUNGE"]):
                self.waiting = True
            first = lines.next(WAIT)
        if first is None or not first.startswith(b"+"):
            raise ValueError("idle refused")
        self.idling = True
        until = time.monotonic() + RENEW
        while not self.halt.is_set() and time.monotonic() < until:
            left = until - time.monotonic()
            if self.waiting:
                left = min(left, self.last + QUIET - time.monotonic())
            line = lines.next(min(WAIT, max(0.05, left)))
            words = line.upper().split() if line is not None else []
            if words[:1] == [b"*"] and b"BYE" in words[1:2]:
                raise EOFError("bye")
            if words[:1] == [b"*"] and len(words) >= 3 and words[2] in (b"EXISTS", b"EXPUNGE"):
                if words[2] == b"EXISTS":
                    _count.bump("neu")
                self.waiting = True
            if self.waiting and time.monotonic() - self.last >= QUIET:
                self.waiting, self.last = False, time.monotonic()
                news(self.uid)
        lines.send(b"DONE")
        while True:                       # the rest of the IDLE, up to its tagged answer
            line = lines.next(WAIT)
            if line is None:
                raise ValueError("no answer to done")
            if line.startswith(tag + b" "):
                break
        self.idling = False
        return "stopped" if self.halt.is_set() else "renew"


class _Lines:
    """Lines from the server's socket, waiting in select() (TLS: what the TLS layer holds back counts too)."""

    def __init__(self, sock):
        self.sock, self.buf = sock, b""

    def send(self, line):
        self.sock.sendall(line + b"\r\n")

    def next(self, seconds):
        end = time.monotonic() + seconds
        while b"\n" not in self.buf:
            pending = getattr(self.sock, "pending", lambda: 0)()
            if not pending:
                left = end - time.monotonic()
                if left <= 0 or not select.select([self.sock], [], [], left)[0]:
                    return None
            chunk = self.sock.recv(4096)
            if not chunk:
                raise EOFError("closed")
            self.buf += chunk
            if len(self.buf) > LINE_MAX:
                raise ValueError("line too long")
        line, self.buf = self.buf.split(b"\n", 1)
        return line.rstrip(b"\r")
