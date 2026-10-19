"""Vorwärmen (Dominik 2026-10-19 „1a 2b 3a 4a 5a 6a 7a 9“, stage A): when a profile signs in, or the panel or its app
opens (GET /api/whoami with a profile), its calendars (this and the next month), its mail listing with the newest
messages, „Für dich“ and its address book are read into the caches of their own modules in the background, so the
pages, Heute and the assistant answer at once. From then on calendars.keep_fresh and mail.keep_fresh keep them fresh
(every 5 minutes, for profiles active in the last day).

- Only what the profile may use now (features.allowed), never for guests; only reading, nothing is changed.
- A profile at most every WARM_AGAIN seconds; at most AT_ONCE profiles at the same time; each step waits while
  somebody speaks (vorrang.quiet: voice always first).
- Nothing new on the disk: the caches live in memory (the address book's own cache stays encrypted in its file).
- Live (Zustand → Live, nodes Kalender and E-Mail): how many profiles are warm and how long ago, never who or what.
"""
import asyncio
import threading
import time

import features
import profiles
import vorrang

WARM_AGAIN = 600     # seconds: a profile is warmed at most this often (every page load asks /api/whoami)
AT_ONCE = 2          # profiles warmed at the same time
WARM_SECONDS = 24 * 3600   # Live counts the profiles warmed in this time

_last = {}           # uid -> when it was warmed last
_lock = threading.Lock()
_loop = [None]       # the panel's event loop (start()), so a request thread can hand the work over
_sem = [None]


def start(loop):
    """Called once at the panel's start with its running loop."""
    _loop[0] = loop
    _sem[0] = asyncio.Semaphore(AT_ONCE)


def ask(uid, now=None):
    """A profile signed in or opened the panel or its app: warm it in the background unless done lately.
    Thread-safe and never waits; returns True when it was started."""
    now = time.time() if now is None else now
    loop = _loop[0]
    if not uid or loop is None or loop.is_closed() or not profiles.by_id(uid):
        return False
    with _lock:
        if now - _last.get(uid, 0) < WARM_AGAIN:
            return False
        _last[uid] = now
    try:
        asyncio.run_coroutine_threadsafe(warm(uid), loop)
    except RuntimeError:     # the loop just stopped (the panel shuts down): nothing to warm for
        return False
    return True


async def warm(uid):
    """Reads the profile's calendars, mail, Für dich and address book into their caches; one log line."""
    sem = _sem[0] or asyncio.Semaphore(AT_ONCE)
    parts, failed = 0, 0
    async with sem:
        for name, step in _steps(uid):
            await vorrang.quiet("Vorwärmen")
            try:
                await step()
                parts += 1
            except Exception:
                failed += 1
    who = profiles.log_name(profiles.by_id(uid))
    if failed:
        print(f"vorwaermen: done | {parts} parts, {failed} failed | {who}", flush=True)
    else:
        print(f"vorwaermen: done | {parts} parts | {who}", flush=True)
    return parts, failed


def _steps(uid):
    """[(name, coroutine function)] of what this profile may use now."""
    out = []
    if features.allowed("calendar", uid):
        import calendars
        if calendars.reading(uid)["calendars"]:
            out.append(("calendar", lambda: calendars.warm(uid)))
    if features.allowed("mail", uid):
        import mail
        if mail.get(uid)["accounts"]:
            out.append(("mail", lambda: asyncio.to_thread(mail.warm, uid)))
            if features.allowed("fuerdich", uid):
                import fuerdich
                out.append(("fuerdich", lambda: asyncio.shield(fuerdich._reading(uid))))
    import contacts
    if contacts.usable(uid):
        out.append(("contacts", lambda: asyncio.to_thread(contacts.cards, uid)))
    return out


def for_live(now=None):
    """Live: how many profiles were warmed in the last day and how many minutes ago the last one (numbers only)."""
    now = time.time() if now is None else now
    with _lock:
        recent = [t for t in _last.values() if now - t < WARM_SECONDS]
    return {"profiles": len(recent), "ago": int((now - max(recent)) // 60) if recent else None}
