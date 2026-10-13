"""Geräte-Updates (plan plaene/firmware-verteilen.md): an overview of what the Spark keeps for the devices,
a note when a new version is there, the speakers updated at night and a note when XiaoZhi has a new version.

What the devices get comes only from the modules that already fetch and check it, each from GitHub's own
download addresses with size and SHA-256 from its release's manifest: speaker firmware (esp32.py, fw-…),
Android app (android.py, android-v…), Spark-Begleiter (begleiter.py, its own update note stays there) and the
Pebble watch app (comes with the Spark's own tested update). This module only asks them more often (CHECK_EVERY),
reads what they keep and tells people. Release notes or any other text from GitHub are never shown or used:
only version numbers that match VERSION.

- Overview: Zustand (admin, all devices), Mein Zustand (own devices, hintergrund.py), Live (kinds, counts, state).
- Note per new version (kind "devup" in push.py): once per version and profile, only to profiles with such a
  device (unless the admin blocked them), plus the admin's note profile (coadmin.notify_uid). The first version a
  Spark sees is only remembered, so switching this on does not send old news.
- Speakers at night (admin chat.dev_updates_night, profile devup_night, per speaker "Updates von selbst"): in the
  window from chat.dev_updates_night_at for NIGHT_LEN the Spark restarts one connected, idle speaker; it fetches
  the firmware at its start (XiaoZhi asks only then). Only when it comes back with the new version within
  BACK_WAIT do the others follow, one at a time, the first of them REST_GAP later. A speaker that does not come
  back stops the round for this version: owner and admin get a note, the rest waits until the admin says
  "Weiter verteilen" in Zustand. Nothing restarts during a Notaus, the profile's own Notaus, a Spark update,
  a conversation, room mode or a test at that speaker.
- XiaoZhi (admin chat.dev_updates_upstream): the newest release of github.com/78/xiaozhi-esp32 compared with
  the version our firmware builds on; one note to the admin per new version. Nothing is built by itself.

Off until the admin switches chat.dev_updates on (Funktionen → Geräte-Updates); then for every profile the
admin did not block; guests never. The language model has no tool for any of this.

    STATE/geraete-updates.json  {"seen": {kind: version}, "due": {kind: {"v", "uids", "admin"}}, "checked": t,
                                 "night": {...}, "upstream": {"version", "told", "checked", "error"}}
    GET  /api/admin/devup                 overview of all devices, night round, XiaoZhi
    POST /api/admin/devup/check           look for new versions now (all kinds), at most every CHECK_GAP
    POST /api/admin/devup/night/resume    the stopped night round may go on
"""
import asyncio
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import notaus
import profiles
from common import load_config
from core import auth

router = APIRouter()
_lock = threading.Lock()
_busy = asyncio.Lock()     # one check at a time

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
CHECK_EVERY = 6 * 3600     # the modules on their own look once a day
CHECK_GAP = 60             # "Jetzt suchen" at most this often
LOOP = 60
NIGHT_LEN = 60 * 60        # the window's length after chat.dev_updates_night_at
BACK_WAIT = 10 * 60        # a restarted speaker must be back with the new version within this
REST_GAP = 30 * 60         # after the first speaker came back: this long until the others
QUIET = 10 * 60            # a speaker used this lately is left for now
UPSTREAM = "78/xiaozhi-esp32"
VERSION = re.compile(r"\d{1,4}(\.\d{1,4}){0,3}")
TAG = re.compile(r"v?(\d{1,4}(?:\.\d{1,4}){1,3})")
HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
MAX_UIDS = 500
LIVE_CACHE = 10

# the kinds: name (de, en), Ich page
KINDS = {"esp": (("Lautsprecher-Firmware", "Speaker firmware"), "espbox"),
         "android": (("Android-App", "Android app"), "andbox"),
         "pebble": (("Pebble-Uhr-App", "Pebble watch app"), "pebbox"),
         "desk_windows": (("Spark-Begleiter Windows", "Spark companion Windows"), "deskbox"),
         "desk_mac": (("Spark-Begleiter Mac", "Spark companion Mac"), "deskbox")}
SHORT = {"esp": "Lautsprecher", "android": "Android", "pebble": "Pebble", "desk_windows": "Begleiter Win", "desk_mac": "Begleiter Mac"}
NOTE_KINDS = ("esp", "android", "pebble")   # the Begleiter tells about its updates itself (begleiter.py)


def admin_on():
    return features.admin_on("geraeteupdate")


def allowed(uid):
    return features.allowed("geraeteupdate", uid)


def night_on():
    return features.admin_on("geraetenacht")


def upstream_on():
    return features.admin_on("xiaozhihinweis")


def vt(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


def newer(new, old):
    a, b = vt(new), vt(old)
    return bool(a) and bool(b) and a > b


def _clean(v):
    v = str(v or "")
    return v if VERSION.fullmatch(v) else ""


# ---------------------------------------------------------------- state
def _file():
    return os.path.join(STATE, "geraete-updates.json")


def _read():
    try:
        with open(_file()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    for k in ("seen", "due", "night", "upstream"):
        if not isinstance(d.get(k), dict):
            d[k] = {}
    return d


def _write(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = _file() + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f)
    os.replace(tmp, _file())


def _change(fn):
    with _lock:
        d = _read()
        out = fn(d)
        _write(d)
        return out


# ---------------------------------------------------------------- what the Spark keeps and who has what
def kept():
    """{kind: version} the Spark keeps now ("" for none), only for the kinds whose function is on."""
    out = {}
    if features.admin_on("esp32"):
        import esp32
        out["esp"] = _clean((esp32.manifest() or {}).get("version"))
    if features.admin_on("android"):
        import android
        out["android"] = _clean((android.meta() or {}).get("version"))
    if features.admin_on("pebble"):
        import pebblewatch
        out["pebble"] = _clean(pebblewatch.app_version())
    if features.admin_on("begleiter"):
        import begleiter
        for p in ("windows", "mac"):
            out["desk_" + p] = _clean((begleiter.kept(p) or {}).get("version"))
    return out


def _checks():
    """{kind: (last check, error)} as the modules keep it."""
    out = {}
    try:
        import esp32
        out["esp"] = esp32.checked()
    except Exception:
        pass
    try:
        import android
        out["android"] = (float(android._state.get("checked") or 0), str(android._state.get("error") or ""))
    except Exception:
        pass
    try:
        import begleiter
        for p in ("windows", "mac"):
            out["desk_" + p] = (float(begleiter._upd["checked"].get(p) or 0), str(begleiter._upd["error"].get(p) or ""))
    except Exception:
        pass
    return out


def speakers(uid=None):
    """[{"id", "name", "user", "fw", "auto", "online", "newer"}] (esp32._list), only while speakers are on."""
    if not features.admin_on("esp32"):
        return []
    import esp32
    return esp32._list(uid)


def _desks(uid):
    if not features.admin_on("begleiter"):
        return []
    import begleiter
    out = []
    for x in begleiter.devices(uid):
        info = begleiter._info.get(x["id"]) or {}
        arch = info.get("arch", "")
        plat = begleiter.ARCHS.get(arch, ("", ""))[0]
        if not plat:
            plat = "mac" if str(x.get("name", "")).startswith("Begleiter Mac") else "windows"
        out.append({"id": x["id"], "name": x.get("name", ""), "user": uid, "kind": "desk_" + plat,
                    "have": _clean(info.get("version")),
                    "newer": bool(arch and begleiter.newer(arch, info.get("version", "")))})
    return out


def _watches(uid):
    if not features.admin_on("pebble"):
        return []
    import pebblewatch
    return [{"id": x["id"], "name": x.get("name", ""), "user": uid} for x in pebblewatch.watches(uid)]


def has_android(uid):
    return features.allowed("android", uid)


def devices(uid):
    """The devices of one profile per kind, with what is known of their version (fixed words, numbers, names)."""
    out = {k: [] for k in KINDS}
    for s in speakers(uid):
        out["esp"].append({"id": s["id"], "name": s["name"], "have": _clean(s.get("fw")), "newer": bool(s.get("newer")),
                           "auto": bool(s.get("auto", True)), "online": bool(s.get("online"))})
    for x in _desks(uid):
        out[x["kind"]].append({"id": x["id"], "name": x["name"], "have": x["have"], "newer": x["newer"]})
    for x in _watches(uid):
        out["pebble"].append({"id": x["id"], "name": x["name"], "have": "", "newer": None})
    return out


def overview(uid=None, now=None):
    """Per kind: what the Spark keeps, the last check and its outcome, the devices (all profiles for the admin)."""
    now = now or time.time()
    k, ch, st = kept(), _checks(), _read()
    uids = [uid] if uid else profiles.user_ids()
    names = {u["id"]: u["name"] for u in profiles.names()}
    devs = {x: [] for x in KINDS}
    android_users = 0
    for u in uids:
        for kind, rows in devices(u).items():
            for r in rows:
                devs[kind].append(dict(r, owner=names.get(u, "") if not uid else ""))
        if "android" in k and has_android(u):
            android_users += 1
    kinds = []
    for kind, (name, go) in KINDS.items():
        if kind not in k:
            continue
        rows = sorted(devs[kind], key=lambda r: r["name"].lower())
        last, err = ch.get(kind, (0, ""))
        kinds.append({"kind": kind, "name": list(name), "go": go, "version": k[kind], "checked": int(last) or None,
                      "error": bool(err), "devices": rows, "current": sum(1 for r in rows if r["newer"] is False),
                      "waiting": sum(1 for r in rows if r["newer"]),
                      "profiles": android_users if kind == "android" else None})
    n = st["night"]
    out = {"on": admin_on(), "kinds": kinds, "checked": int(st.get("checked") or 0) or None,
           "night": {"on": night_on(), "at": night_at(), "version": n.get("version", ""), "ok": len(n.get("ok") or []),
                     "pending": len(n.get("pending") or {}), "stopped": bool(n.get("stopped")),
                     "failed": n.get("failed_name", "") if not uid else ""}}
    if not uid:
        u = st["upstream"]
        out["upstream"] = {"on": upstream_on(), "version": u.get("version", ""), "base": base_version(),
                           "checked": int(u.get("checked") or 0) or None, "error": bool(u.get("error"))}
    return out


# ---------------------------------------------------------------- looking for new versions
async def check_all(c=None, now=None):
    """Asks every module that fetches something for devices (only the ones that are on), and XiaoZhi."""
    import live
    if notaus.blocks("internet"):
        return {"ok": False, "why": "notaus"}
    async with _busy:
        t0 = time.time()
        bad = []    # which part failed, in fixed words (the request's line on Logs → Anfragen names them)
        if features.admin_on("esp32"):
            import esp32
            if await esp32.check():
                bad.append("esp32")
        if features.admin_on("android"):
            import android
            err, none = await android._check()   # (error, only "no release yet"): that one is no failure here
            if err and not none:
                bad.append("android")
        if features.admin_on("begleiter"):
            import begleiter
            for p in begleiter.platforms():
                await begleiter.check(p)    # "noch keine Version" is no failure here
        if upstream_on() and await check_upstream(c):
            bad.append("xiaozhi")
        ok = not bad
        _change(lambda d: d.update(checked=now or time.time()))
        if bad:
            print("geraeteupdate: check failed for", ", ".join(bad), flush=True)
        live.job("Geräte-Updates", "Geräte-Updates", t0, ok, code="_".join(bad)[:30])
        return {"ok": ok}


def base_version():
    """The XiaoZhi version our speaker firmware builds on: its version without our build number."""
    import esp32
    v = _clean((esp32.manifest() or {}).get("version"))
    parts = v.split(".")
    return ".".join(parts[:-1]) if len(parts) >= 2 else ""


async def check_upstream(c=None):
    """The newest XiaoZhi release (version number only). Returns the error or ""."""
    import ghtoken
    import netguard
    api = os.environ.get("SPEECH_SPARK_GITHUB_API", "https://api.github.com")
    err, ver = "", ""
    try:
        if c is not None:
            r = await ghtoken.get(c, f"{api}/repos/{UPSTREAM}/releases/latest")
        else:
            async with netguard.client(netguard.PUBLIC, max_bytes=256 * 1024, timeout=20, follow_redirects=False) as cl:
                r = await ghtoken.get(cl, f"{api}/repos/{UPSTREAM}/releases/latest", headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        m = TAG.fullmatch(str((r.json() or {}).get("tag_name", "")))
        if not m:
            raise ValueError("unknown version")
        ver = m.group(1)
    except Exception as e:
        err = type(e).__name__
        print("geraeteupdate: XiaoZhi check failed:", err, flush=True)

    def keep(d):
        d["upstream"].update(checked=time.time(), error=err)
        if ver:
            d["upstream"]["version"] = ver
    _change(keep)
    return err


# ---------------------------------------------------------------- notes
def _recipients(kind):
    """Profiles with such a device (or, for the Android app, its own switch on)."""
    if kind == "esp":
        return sorted({s["user"] for s in speakers()})
    if kind == "android":
        return [u for u in profiles.user_ids() if has_android(u)]
    if kind == "pebble":
        return [u for u in profiles.user_ids() if _watches(u)]
    return []


def _text(kind, v, uid):
    if kind == "esp":
        mine = [s for s in speakers(uid) if newer(v, s.get("fw", ""))]
        night = night_on() and features.allowed("geraetenacht", uid)
        when = ("heute Nacht" if night else "beim nächsten Neustart") if any(s.get("auto", True) for s in mine) else \
            "sobald du unter Ich → Lautsprecher „Jetzt aktualisieren“ tippst"
        n = len(mine)
        who = f"{n} deiner Lautsprecher bekommt sie {when}." if n == 1 else f"{n} deiner Lautsprecher bekommen sie {when}." \
            if n else "Deine Lautsprecher haben sie schon."
        return "🔊 Neue Lautsprecher-Firmware " + v, "Geprüft und bereit. " + who
    if kind == "android":
        return "📱 Android-App " + v, "Geprüft und bereit. Die App zeigt den Hinweis zum Installieren, den Link gibt es auch unter Ich → Android-App."
    return "⌚ Pebble-Uhr-App " + v, "Liegt bereit. Installieren über die Pebble-App am Handy, den Link zeigt Ich → Pebble-Uhr."


async def notes(now=None):
    """Finds new versions (against the one seen before) and sends the notes that are due. A note the profile's own
    Notaus holds back waits for the next round. Returns how many were sent."""
    import live
    k, st = kept(), _read()
    found = {}
    for kind in NOTE_KINDS:
        v, seen = k.get(kind), st["seen"].get(kind)
        if v and (not seen or newer(v, seen)):
            found[kind] = (v, bool(seen))
    if found:
        admin = _admin_uid()
        due = {kind: {"v": v, "uids": _recipients(kind)[:MAX_UIDS], "admin": admin}
               for kind, (v, old) in found.items() if old}   # the first version a Spark sees is only remembered

        def remember(d):
            for kind, (v, _) in found.items():
                d["seen"][kind] = v
            d.setdefault("due", {}).update(due)
        _change(remember)
        for kind in due:
            live.event("Geräte-Updates", f"{KINDS[kind][0][0]} {due[kind]['v']} geprüft und bereit")
    sent = 0
    for kind, e in dict(_read().get("due") or {}).items():
        if kind not in NOTE_KINDS or not isinstance(e, dict) or not VERSION.fullmatch(str(e.get("v", ""))):
            continue
        v, left, admin = e["v"], [], e.get("admin") or ""
        for uid in e.get("uids") or []:
            if not allowed(uid):
                continue
            if notaus.blocks("auto", uid):
                left.append(uid)
                continue
            title, body = _text(kind, v, uid)
            sent += await _send(uid, title, body)
        if admin and admin not in (e.get("uids") or []):
            if notaus.blocks("auto", admin):
                left.append(admin)
            else:
                title, body = _text(kind, v, admin)
                if kind == "esp":
                    n = sum(1 for s in speakers() if newer(v, s.get("fw", "")))
                    body = f"Geprüft und bereit. {n} Lautsprecher im Haus haben noch eine ältere."
                sent += await _send(admin, title, body)
        admin_left = admin if admin in left and admin not in (e.get("uids") or []) else ""

        def done(d, kind=kind, v=v, left=left, admin_left=admin_left):
            cur = (d.get("due") or {}).get(kind)
            if not cur or cur.get("v") != v:      # a newer version came meanwhile
                return
            if left:
                cur.update(uids=[u for u in left if u != admin_left], admin=admin_left)
            else:
                d["due"].pop(kind, None)
        _change(done)
    return sent


async def _send(uid, title, body):
    import push
    try:
        await push.send(uid, title, body, tag="devup", private=False)
        return 1
    except Exception as e:
        print("geraeteupdate: note", type(e).__name__, flush=True)
        return 0


def _admin_uid():
    try:
        import coadmin
        return coadmin.notify_uid()
    except Exception:
        return ""


async def upstream_note():
    """One note to the admin per new XiaoZhi version newer than our base."""
    if not upstream_on():
        return 0
    st = _read()["upstream"]
    v, base = st.get("version", ""), base_version()
    if not v or not base or not newer(v, base) or st.get("told") == v:
        return 0
    uid = _admin_uid()
    if not uid or notaus.blocks("auto", uid):
        return 0
    import live
    import push
    try:
        await push.send(uid, "🛠 XiaoZhi " + v + " ist erschienen",
                        f"Die Lautsprecher-Firmware baut auf XiaoZhi {base}. Eine neue Firmware entsteht erst auf dein Wort "
                        "(firmware/xiaozhi.json, Commit anheben) und will dann getestet werden.", tag="devup", private=False)
    except Exception as e:
        print("geraeteupdate: XiaoZhi note", type(e).__name__, flush=True)
    _change(lambda d: d["upstream"].update(told=v))
    live.event("Geräte-Updates", f"XiaoZhi {v} erschienen (wir: {base})")
    return 1


# ---------------------------------------------------------------- speakers at night
def night_at():
    at = str(load_config().get("chat", {}).get("dev_updates_night_at") or "05:15")
    return at if HHMM.fullmatch(at) else "05:15"


def in_window(now):
    """True while now is within NIGHT_LEN after the Spark's local time chat.dev_updates_night_at."""
    hh, mm = map(int, night_at().split(":"))
    t = time.localtime(now)
    start = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hh, mm, 0, 0, 0, -1))
    if start > now:      # the window may have begun yesterday
        start = time.mktime((t.tm_year, t.tm_mon, t.tm_mday - 1, hh, mm, 0, 0, 0, -1))
    return 0 <= now - start < NIGHT_LEN


def _idle(did, now):
    """The speaker is connected and nobody uses it: no answer running, no room mode, test or voice training,
    and not used lately."""
    import esp32
    s = esp32._live.get(did)
    if s is None:
        return False
    if s.room is not None or s.enrolling is not None or s.testing or s.room_next:
        return False
    if s.answer is not None and not s.answer.done():
        return False
    last = (esp32._history.get(did) or (0,))[0]
    return now - float(last or 0) > QUIET


def _spark_updating():
    try:
        import update
        return bool(update.update_running())
    except Exception:
        return False


async def night_step(now=None):
    """One step of the night round. Returns what it did: "", "restart", "back", "stopped"."""
    now = now or time.time()
    if not (admin_on() and night_on()) or not features.admin_on("esp32"):
        return ""
    import esp32
    import live
    m = esp32.manifest()
    v = _clean((m or {}).get("version"))
    if not v:
        return ""
    st = _read()["night"]
    if st.get("version") != v:      # a new version: a new round
        st = {"version": v, "ok": [], "pending": {}, "stopped": False}
        _change(lambda d: d.update(night=st))
    fw = {s["id"]: s for s in speakers()}
    # who came back, who did not
    pending = dict(st.get("pending") or {})
    for did, t in pending.items():
        s = fw.get(did)
        if s and s.get("fw") == v:
            def back(d, did=did):
                d["night"]["pending"].pop(did, None)
                d["night"].setdefault("ok", []).append(did)
                d["night"]["ok_t"] = now
            _change(back)
            live.event("Geräte-Updates", f"Lautsprecher wieder da mit {v}")
            live.bg("Lautsprecher-Update", None)
            return "back"
        if not s or now - float(t) > BACK_WAIT:
            name = s["name"] if s else "?"
            owner = s["user"] if s else ""

            def stop(d, did=did, name=name):
                d["night"]["pending"].pop(did, None)
                d["night"].update(stopped=True, failed=did, failed_name=name, stopped_t=now)
            _change(stop)
            await _tell_stopped(name, owner, v)
            return "stopped"
    if pending or st.get("stopped"):
        return ""
    if not in_window(now) or notaus.level() >= 1 or await asyncio.to_thread(_spark_updating):
        return ""
    proven = bool(st.get("ok")) or any(s.get("fw") == v for s in fw.values())
    if st.get("ok") and now - float(st.get("ok_t") or 0) < REST_GAP and len(st["ok"]) == 1:
        return ""
    for s in sorted(fw.values(), key=lambda x: (x["name"].lower(), x["id"])):
        uid = s["user"]
        if not (s.get("auto", True) and newer(v, s.get("fw", "")) and esp32.ota_allowed(s.get("plain"))
                and features.allowed("geraetenacht", uid)
                and features.allowed("esp32", uid) and not notaus.own(uid) and _idle(s["id"], now)):
            continue
        if not await _restart(s["id"]):
            continue
        _change(lambda d, did=s["id"]: d["night"].setdefault("pending", {}).update({did: now}))
        live.bg("Lautsprecher-Update", "run", now)
        live.event("Geräte-Updates", ("erster " if not proven else "") + f"Lautsprecher startet neu für {v}")
        return "restart"
    return ""


async def _restart(did):
    import esp32
    cid, _ = esp32.by_device(did)
    s = esp32._live.get(did)
    if not cid or s is None:
        return False
    esp32._update(lambda d: d["clients"][cid].update(update=True))
    try:
        await s.send({"type": "system", "command": "reboot"})
        return True
    except Exception as e:
        print("geraeteupdate: restart", type(e).__name__, flush=True)
        return False


async def _tell_stopped(name, owner, v):
    import live
    import push
    live.bg("Lautsprecher-Update", None)
    live.event("Geräte-Updates", f"Lautsprecher nicht mit {v} zurück, Verteilung angehalten")
    title = "🔊 Lautsprecher-Update angehalten"
    body = (f"„{name}“ kam nach dem Neustart nicht mit der Firmware {v} zurück. Die übrigen Lautsprecher warten. "
            "Prüfen unter Ich → Lautsprecher; über USB neu einrichten geht immer.")
    for uid in dict.fromkeys(x for x in (owner, _admin_uid()) if x):
        try:
            await push.send(uid, title, body, tag="devup", private=False)
        except Exception as e:
            print("geraeteupdate: stop note", type(e).__name__, flush=True)


def hint():
    """For Live (live.hints): the stopped round or a failed check, fixed words only."""
    if not admin_on():
        return None
    if night_on() and _read()["night"].get("stopped"):
        return {"at": "geraete", "level": "bad", "word": "Lautsprecher-Update angehalten"}
    k, ch = kept(), _checks()
    if any(ch.get(kind, (0, ""))[1] for kind in ("esp", "android") if kind in k):
        return {"at": "geraete", "level": "warn", "word": "Update-Prüfung fehlgeschlagen"}
    return None


_live_cache = [0.0, None]


def for_live(now=None):
    """Live: kinds with the version kept and how many devices are current or waiting. Counts only (kept LIVE_CACHE s:
    the monitor asks every few seconds)."""
    now = now or time.time()
    if not admin_on():
        return None
    if 0 <= now - _live_cache[0] < LIVE_CACHE:
        return _live_cache[1]
    try:
        o = overview()
    except Exception:
        return None
    parts = []
    for k in o["kinds"]:
        n = len(k["devices"])
        parts.append({"kind": k["kind"], "name": k["name"][0], "short": SHORT[k["kind"]], "version": k["version"], "n": n,
                      "current": k["current"], "waiting": k["waiting"], "counted": k["kind"] not in ("android", "pebble")})
    out = {"kinds": parts, "night": {"on": o["night"]["on"], "pending": o["night"]["pending"], "stopped": o["night"]["stopped"]}}
    _live_cache[:] = [now, out]
    return out


# ---------------------------------------------------------------- loop
async def loop():
    while True:
        await asyncio.sleep(LOOP)
        try:
            await tick()
        except Exception as e:
            print("geraeteupdate: loop", type(e).__name__, flush=True)


async def tick(now=None):
    now = now or time.time()
    if not admin_on():
        return
    if not notaus.blocks("internet") and now - float(_read().get("checked") or 0) > CHECK_EVERY:
        await check_all(now=now)
    await notes(now)
    await upstream_note()
    await night_step(now)


# ---------------------------------------------------------------- routes
@router.get("/api/admin/devup", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "devup", admin=True)
    return overview()


@router.post("/api/admin/devup/check", dependencies=[Depends(auth)])
async def admin_check(request: Request):
    guard.limit(request, "devup", admin=True)
    if not admin_on():
        raise HTTPException(403, "Geräte-Updates sind aus (Funktionen)")
    if _busy.locked() or time.time() - float(_read().get("checked") or 0) < CHECK_GAP:
        raise HTTPException(429, "eben erst gesucht, bitte gleich noch einmal", headers={"Retry-After": str(CHECK_GAP)})
    r = await check_all()
    await notes()
    await upstream_note()
    return dict(r, **overview())


@router.post("/api/admin/devup/night/resume", dependencies=[Depends(auth)])
def admin_resume(request: Request):
    guard.limit(request, "devup", admin=True)
    if not admin_on():
        raise HTTPException(403, "Geräte-Updates sind aus (Funktionen)")

    def fn(d):
        d["night"].update(stopped=False, failed="", failed_name="")
    _change(fn)
    guard.log("devup_resume")
    return overview()
