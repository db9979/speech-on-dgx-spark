"""Vorrat: a profile's sealed supply on the disk, the one way to keep what a service read for a profile so it answers
at once after a restart and when its source does not answer (first the Mail-Vorrat, mailvorrat.py; plan
vorrat-je-profil, Paket B, for the other services).

    USERS_DIR/<user id>/<name>   {"v": 1, "data": base64("G1" + nonce + AES-GCM(json))}

- In the profile's own folder (dateien.py registers each name): it goes with the profile, a copy of my data finds it.
- Sealed with AES-GCM (Sicherheits-Checkliste: new parts take an AEAD), its key derived from the Spark's secret key
  (vault.KEY_FILE, HKDF "speech-spark vorrat v1"), the profile and the name as associated data, so a file copied
  into another profile does not open. Without cryptography nothing is written, the memory alone; never plain text.
- Written at most every write_every seconds per profile (the SD card of the Pi); flush() writes the rest.
- sweep() deletes a file nobody wrote for idle_days: a service writes only while its profile uses it.

The ages and the answer from memory (second part of this file):
Vorrat je Profil (plan vorrat-je-profil, Dominik 2026-10-20 „alle Punkte umsetzen“), stage A: the assistant answers
from what the services already keep in memory instead of asking the server again for every question.

Every service with a memory of its own (mail, calendar, weather, parcels) has two ages here (DIENSTE):
  - fresh: a stored reading younger than this is taken as it is (warm),
  - most:  a stored reading younger than this is taken when the server does not answer within WAIT seconds; the
           service asks anew behind it, and the tool's text says „Stand hh:mm“ (alt). Older or nothing: the
           answer waits for the server as before (kalt).
„Schau nochmal nach“, „aktualisiere“ and the like (NEU, the person's own words) always ask the server anew.

Per answer the services note what they did (note); chat.wait_measure keeps it with the answer for Zustand → Prüfen
(latency.py, per service: from the store, old, waited), and Live shows today's share from the store. Only fixed
words and numbers, never what was read. The readings stay in the memory of their own modules; weather (the
profile's own place) and parcels also keep their last reading sealed as a Vorrat (weather.SUPPLY, parcels.SUPPLY),
written and swept by the round (_disk), so the first question after a restart finds them.
"""
import asyncio
import base64
import concurrent.futures
import contextvars
import hashlib
import hmac
import json
import os
import re
import threading
import time

from common import write_json
import profiles
import vault


_vkey = None      # the AES-GCM key (backup._forget_cached drops it after a restore)
_mkeys = (None, {})   # (the _vkey they belong to, {uid: HMAC key of the Blind-Index}): a restore makes them anew


def _secret():
    """The Spark's secret key (vault.KEY_FILE), made when there is none yet; None without cryptography."""
    if not vault.available():
        return None
    vault._key()
    try:
        with open(vault.KEY_FILE, "rb") as f:
            return f.read().strip()
    except OSError:
        return None


def _derive(base, info):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(base)


def _key():
    global _vkey
    if _vkey:
        return _vkey
    base = _secret()
    if not base:
        return None
    _vkey = _derive(base, b"speech-spark vorrat v1")
    return _vkey


def marke(uid, wort):
    """Blind-Index of Finden (fund.py, plan such-index): a word stem or a normed tag as a mark, base32 of
    HMAC-SHA256 with a key of its own per profile (HKDF from the Spark's secret key, info "speech-spark fund marken v1"
    plus the profile id), cut to 10 characters (50 bits). The same word gives another mark in another profile; None
    without a key (then Finden writes nothing that needs one)."""
    global _mkeys
    v = _key()
    if not v or not uid:
        return None
    if _mkeys[0] is not v:
        _mkeys = (v, {})
    k = _mkeys[1].get(uid)
    if k is None:
        base = _secret()
        if not base:
            return None
        if len(_mkeys[1]) > 500:
            _mkeys[1].clear()
        k = _mkeys[1][uid] = _derive(base, b"speech-spark fund marken v1:" + str(uid).encode())
    return base64.b32encode(hmac.new(k, str(wort).encode(), hashlib.sha256).digest()).decode()[:10].lower()


def seal(data, ad):
    """bytes -> text: "G1" + nonce + AES-GCM, base64; None without a key."""
    k = _key()
    if not k:
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return base64.b64encode(b"G1" + nonce + AESGCM(k).encrypt(nonce, data, ad.encode())).decode()


def unseal(text, ad):
    """The bytes, or None (other key, other profile, changed file)."""
    k = _key()
    try:
        raw = base64.b64decode(text or "", validate=True)
        if not k or raw[:2] != b"G1":
            return None
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
        try:
            return AESGCM(k).decrypt(raw[2:14], raw[14:], ad.encode())
        except InvalidTag:
            return None
    except ValueError:
        return None


class Vorrat:
    def __init__(self, name, idle_days, write_every=300, empty=dict):
        self.name, self.idle_days, self.write_every, self.empty = name, idle_days, write_every, empty
        self.mem = {}          # uid -> data
        self.dirty = {}        # uid -> True when changed since the last write
        self.written = {}      # uid -> when the file was written last
        self.lock = threading.RLock()

    def file(self, uid):
        return profiles._path(uid, self.name)

    def load(self, uid):
        """The profile's data (memory, else its sealed file, else empty()); never raises."""
        d = self.mem.get(uid)
        if d is not None:
            return d
        d = self.empty()
        try:
            with open(self.file(uid), encoding="utf-8") as f:
                got = json.loads(unseal(json.load(f).get("data", ""), f"{uid}/{self.name}") or b"null")
            if isinstance(got, dict):
                d.update(got)
        except (OSError, ValueError, AttributeError):
            pass
        self.mem[uid] = d
        return d

    def changed(self, uid, now=None, force=False):
        """The data of uid changed: written now when the last write is write_every seconds old (or force), else later."""
        now = time.time() if now is None else now
        if not force and now - self.written.get(uid, 0) < self.write_every:
            self.dirty[uid] = True
            return
        with self.lock:
            d = self.mem.get(uid)
            self.dirty.pop(uid, None)
            if d is None or not os.path.isdir(os.path.dirname(self.file(uid))):
                return
            sealed = seal(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode(), f"{uid}/{self.name}")
            if not sealed:   # no key: never in plain text
                return
            write_json(self.file(uid), {"v": 1, "data": sealed}, mode=0o600, dir_mode=0o700)
            self.written[uid] = now

    def flush(self, now=None):
        """Writes every changed profile. Returns how many."""
        n = 0
        for uid in list(self.dirty):
            self.changed(uid, now, force=True)
            n += 1
        return n

    def forget(self, uid):
        with self.lock:
            for d in (self.mem, self.dirty, self.written):
                d.pop(uid, None)
            try:
                os.remove(self.file(uid))
            except OSError:
                pass

    def sweep(self, now=None):
        """Files nobody wrote for idle_days go. Returns how many."""
        now = time.time() if now is None else now
        try:
            names = os.listdir(profiles.USERS_DIR)
        except OSError:
            return 0
        n = 0
        for uid in names:
            if not re.fullmatch(r"[\w-]{1,40}", uid) or uid in self.dirty:
                continue
            try:
                old = now - os.stat(self.file(uid)).st_mtime > self.idle_days * 86400
            except OSError:
                continue
            if old:
                self.forget(uid)
                n += 1
        return n

    def clear(self):
        """Memory only (tests)."""
        for d in (self.mem, self.dirty, self.written):
            d.clear()


# Vorrat je Profil: ages per service, the answer's notes and the one background round
MIN, HOUR, DAY = 60, 3600, 86400
# service -> (fresh, most) in seconds; the only place these ages are set
DIENSTE = {"mail": (10 * MIN, DAY), "calendar": (10 * MIN, DAY), "weather": (30 * MIN, 6 * HOUR),
           "parcels": (15 * MIN, 6 * HOUR)}
WAIT = 2.0              # seconds an answer waits for the server when an older reading is at hand
STATES = ("warm", "alt", "kalt")
RANK = {"warm": 0, "kalt": 1, "alt": 2}   # what an answer says about a service when it read it more than once
# the person asks to look again: always the server, never the store (own words only, never the model's)
NEU = re.compile(r"(?i)\b(noch ?mal|erneut|aktualisier\w*|neu (?:laden|abrufen|holen|nachsehen|nachschauen)|"
                 r"check again|look again|refresh\w*|reload)\b")

_turn = contextvars.ContextVar("vorrat_turn", default=None)
_lock = threading.Lock()
_today = {"day": "", "counts": {}}    # service -> {state: n} of today (Live; RAM only)
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="vorrat")
_inflight = {}          # key -> Future of a fetch that runs (one per key, however many ask)
_tasks = {}             # key -> asyncio.Task of a fetch that runs


def begin(question="", tz=None):
    """A new answer: what its services take from the store is noted in the returned dict (kept on the turn)."""
    return {"neu": bool(NEU.search(str(question or "")[:400])), "tz": tz, "seen": {}, "when": {}}


def use(turn_state):
    """The answer's tool calls run in this context (chat.run_tool): their notes go into turn_state."""
    if isinstance(turn_state, dict):
        _turn.set(turn_state)


def state(dienst, when, now=None):
    """warm, alt or kalt for a stored reading of `when` (None: nothing stored)."""
    if when is None:
        return "kalt"
    cur = _turn.get()
    if cur and cur["neu"]:
        return "kalt"
    fresh, most = DIENSTE[dienst]
    age = (time.time() if now is None else now) - when
    return "warm" if 0 <= age < fresh else "alt" if 0 <= age < most else "kalt"


def in_turn():
    """True inside an answer of the assistant (use()); pages and background work keep their own rules."""
    return _turn.get() is not None


def note(dienst, kind, when=None):
    """The service answered from the store (warm), with an older reading (alt, `when` it was read) or after waiting
    for the server (kalt). Counted only inside an answer of the assistant (use()), once per service and answer: a
    second note (another calendar) only makes it worse (warm < kalt < alt) and keeps the oldest reading."""
    if dienst not in DIENSTE or kind not in STATES:
        return
    cur = _turn.get()
    if cur is None:       # a page or the background: only answers of the assistant are counted
        return
    was = cur["seen"].get(dienst)
    if was and RANK[kind] <= RANK[was]:
        kind = was
    else:
        cur["seen"][dienst] = kind
    if kind == "alt" and when:
        cur["when"][dienst] = min(when, cur["when"].get(dienst) or when)
    if was == kind:
        return
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _today["day"] != day:
            _today.update(day=day, counts={})
        c = _today["counts"].setdefault(dienst, dict.fromkeys(STATES, 0))
        if was and c[was] > 0:
            c[was] -= 1
        c[kind] += 1
    if kind == "alt":     # the answer goes on with an older reading: worth a line (fixed words, no profile, no content)
        print(f"vorrat: older reading | {dienst} | {int(time.time() - (cur['when'].get(dienst) or time.time())) // 60} min",
              flush=True)


def stand(dienst):
    """For the tool's text: „As of heute 14:05 …“ when this answer took an older reading of the service, else ""; the day
    always comes with the time (frisch.stand: a reading of last evening never sounds like this morning's)."""
    cur = _turn.get()
    when = cur and cur["when"].get(dienst)
    if not when:
        return ""
    import frisch
    try:
        import chat
        zone = chat.user_zone(cur.get("tz"))
    except Exception:
        zone = None
    at = frisch.stand(when, zone=zone)
    return f"\n(As of {at}: the service is slow right now, this is its last reading. Say that, e.g. „Stand {at} Uhr“.)"


def current():
    """The notes of the answer that runs in this context (begin/use), or None outside an answer (frisch.py adds its own)."""
    return _turn.get()


def seen(turn_state):
    """For latency (MEASURE "s"): "mail:warm+weather:alt", sorted, fixed words only."""
    got = (turn_state or {}).get("seen") or {}
    return "+".join(f"{d}:{k}" for d, k in sorted(got.items()) if d in DIENSTE and k in STATES)[:80]


async def take(dienst, hit, key, fetch):
    """The value for an assistant's question: hit = (when, value) or None; fetch() a coroutine reading anew. One
    fetch per key runs at a time; an older reading is taken after WAIT seconds, the fetch goes on behind it."""
    kind = state(dienst, hit[0] if hit else None)
    if kind == "warm":
        note(dienst, "warm")
        return hit[1]
    task = _tasks.get(key)
    if task is None or task.done():
        task = _tasks[key] = asyncio.ensure_future(fetch())
        task.add_done_callback(lambda t: (_tasks.pop(key, None) if _tasks.get(key) is t else None,
                                          t.cancelled() or t.exception()))
    if kind == "alt":
        done, _ = await asyncio.wait({task}, timeout=WAIT)
        if task in done and not task.cancelled() and task.exception() is None:
            note(dienst, "kalt")
            return task.result()
        note(dienst, "alt", hit[0])
        return hit[1]
    value = await asyncio.shield(task)
    note(dienst, "kalt")
    return value


def take_sync(dienst, hit, key, fetch):
    """take() for code in a worker thread: fetch() runs in the store's own small pool."""
    kind = state(dienst, hit[0] if hit else None)
    if kind == "warm":
        note(dienst, "warm")
        return hit[1]
    with _lock:
        fut = _inflight.get(key)
        if fut is None or fut.done():
            fut = _inflight[key] = _pool.submit(contextvars.copy_context().run, fetch)
            fut.add_done_callback(lambda f: _inflight.pop(key, None) if _inflight.get(key) is f else None)
    if kind == "alt":
        try:
            value = fut.result(WAIT)
        except Exception:     # still running or failed: the older reading, „Stand hh:mm“
            note(dienst, "alt", hit[0])
            return hit[1]
        note(dienst, "kalt")
        return value
    value = fut.result()
    note(dienst, "kalt")
    return value


def for_live():
    """Today per service: how many answers came from the store, old or after waiting (numbers only)."""
    day = time.strftime("%Y-%m-%d")
    with _lock:
        counts = {d: dict(c) for d, c in _today["counts"].items()} if _today["day"] == day else {}
    out = {}
    for d, c in counts.items():
        n = sum(c.values())
        out[d] = dict(c, n=n, share=round(100 * (c["warm"] + c["alt"]) / n) if n else 0)
    return out


def rounds_live(now=None):
    """Live (box Vorrat je Profil): rounds and services read anew today, minutes since the last round."""
    now = time.time() if now is None else now
    with _lock:
        st = dict(_stats) if _stats["day"] == time.strftime("%Y-%m-%d") else {"rounds": 0, "refreshed": 0, "last": _stats["last"]}
    return {"rounds": st["rounds"], "refreshed": st["refreshed"],
            "ago": int((now - st["last"]) // 60) if st.get("last") else None}


def live_sub(dienst, live=None):
    """The words Live adds to a service's box: „heute 12 Fragen, 83 % aus dem Vorrat“ ("" without questions)."""
    c = (for_live() if live is None else live).get(dienst)
    if not c or not c["n"]:
        return ""
    return f" · heute {c['n']} Fragen, {c['share']} % aus dem Vorrat" + (f", {c['alt']} mit Stand" if c["alt"] else "")


# ---------------------------------------------------------------- stage B: one round keeps the store fresh
# One loop instead of one per service (calendars.keep_fresh_loop is gone): every EVERY seconds it looks at the profiles
# active in the last ACTIVE_SECONDS and refreshes what got older than its fresh age, so the next question finds it warm.
# Only what the profile may use now, never guests, each step waits while somebody speaks (vorrang.quiet), at most
# AT_ONCE profiles at the same time. Mail keeps its own round (mail.keep_fresh_loop, with the encrypted mail store).
EVERY = 60
ACTIVE_SECONDS = DAY
AT_ONCE = 2
_round = {"calendar": 0.0}     # when a service's own round ran last
_stats = {"day": "", "rounds": 0, "refreshed": 0, "last": None}   # Live: numbers only


def active(now=None):
    """Profiles that used the panel, its app or a service in the last ACTIVE_SECONDS (from the services' own notes)."""
    import calendars
    import mail
    import vorwaermen
    now = time.time() if now is None else now
    seen = {}
    for src in (vorwaermen._last, calendars._used, mail._used):
        for uid, t in list(src.items()):
            seen[uid] = max(seen.get(uid, 0), t)
    return [uid for uid, t in sorted(seen.items(), key=lambda kv: -kv[1]) if now - t < ACTIVE_SECONDS]


def _older(hit, dienst, now):
    return not hit or now - hit[0] >= DIENSTE[dienst][0]


async def _profile(uid, now):
    """The services of one profile that got older than their fresh age; returns how many were read anew."""
    import vorrang
    import weather
    import parcels
    import fuerdich
    n = 0
    if weather.usable(uid):
        w = weather.get(uid)
        if _older(weather._cache.get((round(w["lat"], 3), round(w["lon"], 3))), "weather", now):
            await vorrang.quiet("Vorrat")
            await weather.forecast(w["lat"], w["lon"], 7, uid)
            n += 1
    if parcels.usable(uid) and _older(parcels._cache.get(uid), "parcels", now):
        await vorrang.quiet("Vorrat")
        await asyncio.to_thread(parcels.scan, uid)   # an older reading stays until the new one is there
        n += 1
    if fuerdich.usable(uid) and _newer_mail(uid):
        await vorrang.quiet("Vorrat")
        await asyncio.shield(fuerdich._reading(uid))
        n += 1
    return n


def _newer_mail(uid):
    """A mail came after the last reading of „Für dich“ (and that reading is at least a minute old): read it anew, so
    the assistant and the tab know of it before anyone asks. Only the dates of the mail listing are looked at."""
    import fuerdich
    import mail
    hit = fuerdich._last(uid)
    if not hit or time.time() - hit[0] < MIN:
        return False
    newest = 0.0
    for (u, w, _d, _un, _lim), (_t, (found, _e, _m)) in list(mail._cache.items()):
        if u == uid and not w and found:
            newest = max(newest, found[0][2]["date"].timestamp())
    return newest > hit[0]


async def round_(now=None):
    """One round: the calendars every calendars.CACHE_SECONDS (calendars.keep_fresh), then weather, parcels and „Für
    dich“ of each active profile. Returns the number of services read anew."""
    import calendars
    import profiles
    now = time.time() if now is None else now
    n = 0
    if now - _round["calendar"] >= calendars.CACHE_SECONDS:
        _round["calendar"] = now
        people, cals = await calendars.keep_fresh(now)
        if people:
            print(f"calendar: kept fresh | {cals} calendars of {people} profiles", flush=True)
    sem = asyncio.Semaphore(AT_ONCE)

    async def one(uid):
        async with sem:
            try:
                return await _profile(uid, now)
            except Exception as e:
                print(f"vorrat: refresh failed ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)
                return 0
    got = await asyncio.gather(*(one(u) for u in active(now) if profiles.by_id(u)))
    n = sum(got)
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _stats["day"] != day:
            _stats.update(day=day, rounds=0, refreshed=0)
        _stats["rounds"] += 1
        _stats["refreshed"] += n
        _stats["last"] = now
    if n:
        print(f"vorrat: kept fresh | {n} services of {len(got)} profiles", flush=True)
    await asyncio.to_thread(_disk, now)
    return n


def supply_live():
    """Live (nodes weather and parcels): profiles whose last reading is kept sealed (in memory now); numbers only."""
    import weather
    import parcels
    return {"weather": sum(1 for d in weather.SUPPLY.mem.values() if d.get("t")),
            "parcels": sum(1 for d in parcels.SUPPLY.mem.values() if d.get("t"))}


def _disk(now):
    """The sealed supplies of weather and parcels (3b): what changed is written, once a day what nobody read for
    their idle_days goes."""
    import weather
    import parcels
    kept = (weather.SUPPLY, parcels.SUPPLY)
    written = sum(v.flush(now) for v in kept)
    swept = 0
    if now - _round.get("swept", 0) >= DAY:
        _round["swept"] = now
        swept = sum(v.sweep(now) for v in kept)
    if written or swept:
        print(f"vorrat: supply written | {written} written, {swept} deleted", flush=True)


async def loop():
    """Started with the panel; one round every EVERY seconds."""
    while True:
        await asyncio.sleep(EVERY)
        try:
            await round_()
        except Exception as e:
            print(f"vorrat: round failed ({type(e).__name__})", flush=True)
