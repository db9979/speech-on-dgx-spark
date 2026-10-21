"""Zustand der NAS (plan plaene/synology-bauplan.md, S6; Dominik 2026-10-13 "S1 - S8 umsetzen").

The admin lets the Spark read how the NAS is doing over SNMPv3 (DSM → Systemsteuerung → Terminal & SNMP → SNMP:
SNMPv3 with a user, SHA and AES): volume use, RAID state, the disks' state and temperature, the system temperature,
fans, power, uptime, the DSM version and whether an update is ready (Synology MIB 1.3.6.1.4.1.6574), and USB or eSATA
disks plugged into the NAS (HOST-RESOURCES-MIB hrStorageTable, only mounts like /volumeUSB1/usbshare). Reading only:
the Spark never sets anything over SNMP and never uses the DSM web interface.

    STATE/naszustand.json  {"host", "port", "user", "auth" (sealed), "priv" (sealed), "last": {"t", "ok", "why"},
                            "values": {...}, "warn": {code: {"since", "w"}}, "seen": {code: n}, "reads"}

Rules (fixed, never decided by the model):
- SNMPv3 with authPriv only (SHA and AES-128), never v1 or v2c with a community: _user refuses anything else.
- The host must be in the home network (nas.home_name) and goes through netguard HOME (resolve) like every NAS
  connection, so the Notaus and the Wächter hold it; the user and both passwords sit sealed in the vault and are never
  shown again, logged or sent to the apps. Changing them needs an admin (panel password or a profile with the Admin role, stufen.py).
- Answers are data: only the OIDs asked for are taken (_parse), numbers outside sane ranges, rows beyond MAX_ROWS and
  texts that are no plain names are dropped and counted ("verworfen"). The tool nas_zustand answers with fixed
  words and these numbers only (chat.INSIDE); volume names are kept only when they look like "Volume 1", a USB disk is
  named by fixed words and its number ("USB-Platte 2"), never by the path.
- The Synology RAID table lists storage pools and volumes. A pool's free space is what is not yet given to a volume
  (Dominik 2026-10-21: "Storage Pool 1 … 0 GB frei" was read as full), so a pool is shown as "an Volumes vergeben" and
  never warned of as full; only volumes and USB disks are (art()).
- Read every READ_EVERY seconds (after a failure every RETRY), never while the Spark updates or the Notaus holds
  things off, in a quiet moment (vorrang.speaking).

Notes (Dienst-Wächter, dienstwacht.py): service "naszustand" ("Zustand der NAS") is gone when the NAS has not
answered for a few minutes, and back when it answers again. A volume over chat.nas_full_pct (90), a degraded or
crashed RAID (pool or volume), a disk with a warning, a USB disk over the same limit, a temperature over chat.nas_temp_max (60 °C) or a failed fan or power supply is
told to the admins once (after SEEN_N readings in a row) and again when it is fine (dienstwacht.warn).

Zustand → Dienste: card "Zustand der NAS" (naszustand.js); Live: target "Zustand der NAS" (live.py "naszustand",
numbers only); Logs → Diagnose, area "NAS" (lines "naszustand: ..."), fixed words and numbers, never an address.
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
import netguard
import vault
from common import STATE, write_json
import core
from core import admin_code, auth

router = APIRouter()
FILE = "naszustand.json"
PORT = 161
READ_EVERY, RETRY = 300, 60
FRESH = 15 * 60            # a reading older than this counts as "not answering" for the Dienst-Wächter
TIMEOUT, RETRIES, DEADLINE = 2, 1, 25
MAX_ROWS = 32              # disks and volumes a NAS has at most (more rows are dropped and counted)
SEEN_N = 2                 # a problem is told after this many readings in a row
FULL_PCT, TEMP_MAX = 90, 60
HOST = re.compile(r"[a-z0-9.\-]{1,253}|[0-9a-f:.]{2,45}")
USER = re.compile(r"[A-Za-z0-9._\-]{1,32}")
NICE = re.compile(r"[A-Za-z0-9 ._+\-]{1,40}")
VOL_NAME = re.compile(r"(Volume|Speicherpool|Storage Pool|Pool|SSD Cache|Cache|Group|Gruppe) ?\d{1,2}")
POOL_NAME = re.compile(r"(Speicherpool|Storage Pool|Pool|Group|Gruppe) ?\d{1,2}")
CACHE_NAME = re.compile(r"(SSD Cache|Cache) ?\d{1,2}")

# the Synology MIB (SYNOLOGY-SYSTEM-MIB, -DISK-MIB, -RAID-MIB) and sysUpTime
SYS = "1.3.6.1.4.1.6574.1"
SCALARS = {"up": "1.3.6.1.2.1.1.3.0", "sys": SYS + ".1.0", "temp": SYS + ".2.0", "power": SYS + ".3.0",
           "fan": SYS + ".4.1.0", "cpufan": SYS + ".4.2.0", "model": SYS + ".5.1.0", "dsm": SYS + ".5.3.0",
           "update": SYS + ".5.4.0"}
DISK = "1.3.6.1.4.1.6574.2.1.1"
DISK_COLS = {"5": "st", "6": "temp", "13": "health"}
RAID = "1.3.6.1.4.1.6574.3.1.1"
RAID_COLS = {"2": "name", "3": "st", "4": "free", "5": "total"}
# HOST-RESOURCES-MIB hrStorageTable: descr (mount path), allocation unit, size and used in units (Integer32)
HR = "1.3.6.1.2.1.25.2.3.1"
HR_COLS = {"3": "descr", "4": "unit", "5": "size", "6": "used"}
USB_PATH = re.compile(r"/volume(USB|SATA)(\d{1,2})/(?:usb|sata)share(?:\d{1,2}(?:-(\d{1,2}))?)?")
# diskStatus: 1 normal, 2 initialized, 3 not initialized, 4 system partition failed, 5 crashed
DISK_ST = {1: "ok", 2: "ok", 3: "neu", 4: "fehler", 5: "defekt"}
# diskHealthStatus (DSM 7): 1 normal, 2 warning, 3 critical, 4 failing
DISK_HEALTH = {1: "ok", 2: "warnung", 3: "kritisch", 4: "fällt aus"}
# raidStatus: 1 normal, 2 repairing … 11 degrade, 12 crashed, 13 data scrubbing …
RAID_ST = {1: "ok", 2: "repariert", 3: "migriert", 4: "erweitert", 5: "wird gelöscht", 6: "wird angelegt",
           7: "synchronisiert", 8: "prüft Parität", 9: "setzt zusammen", 10: "bricht ab", 11: "beschädigt",
           12: "ausgefallen", 13: "prüft Daten", 14: "ok", 15: "ok", 16: "ok", 17: "ok", 18: "ok", 19: "ok",
           20: "ok", 21: "ok"}
RAID_BAD = {"beschädigt", "ausgefallen"}
WORDS_EN = {"ok": "fine", "neu": "not set up", "fehler": "system partition failed", "defekt": "crashed",
            "warnung": "warning", "kritisch": "critical", "fällt aus": "failing", "repariert": "repairing",
            "migriert": "migrating", "erweitert": "expanding", "wird gelöscht": "deleting", "wird angelegt": "creating",
            "synchronisiert": "syncing", "prüft Parität": "parity check", "setzt zusammen": "assembling",
            "bricht ab": "cancelling", "beschädigt": "degraded", "ausgefallen": "crashed", "prüft Daten": "scrubbing"}
WHY = {"offline": ("antwortet nicht", "not answering"), "auth": ("Benutzer oder Passwort abgelehnt", "user or password refused"),
       "blocked": ("vom Wächter nicht erlaubt", "not allowed by the Wächter"), "notaus": ("Notaus", "emergency stop"),
       "bad": ("Antwort unbrauchbar", "answer unusable"), "unset": ("nicht eingerichtet", "not set up"),
       "other": ("Fehler", "error")}
_lock = threading.Lock()
_mem = {"running": False}


def art(name):
    """What a row of the RAID table is: "pool" (free = not yet given to a volume), "cache" or "vol"."""
    name = name or ""
    return "pool" if POOL_NAME.fullmatch(name) else "cache" if CACHE_NAME.fullmatch(name) else "vol"


class Problem(Exception):
    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind if kind in WHY else "other"


# ---------------------------------------------------------------- switches and settings
def admin_on(c=None):
    """Switched on and set up (features.READY): reading, notes, the tool."""
    return features.admin_on("naszustand", c)


def switched(c=None):
    """Only the admin's switches (and the ones it builds on): setting it up needs no stored NAS yet."""
    c = features.chat_cfg() if c is None else c
    return c.get("nas_status") is True and features.admin_on("nas", c)


def _path():
    return os.path.join(STATE, "naszustand.json")      # = FILE


def _read():
    try:
        with open(_path()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def _write(d):
    write_json(_path(), d, mode=0o600)


def _update(**kw):
    with _lock:
        d = _read()
        d.update(kw)
        _write(d)
        return d


def set_up(c=None):
    """features.READY: host, user and both passwords are stored."""
    d = _read()
    return bool(d.get("host") and d.get("user") and d.get("auth") and d.get("priv"))


def _num(c, key, lo, hi, default):
    v = c.get(key, default)
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else default


def limits(c=None):
    c = features.chat_cfg() if c is None else c
    return _num(c, "nas_full_pct", 50, 99, FULL_PCT), _num(c, "nas_temp_max", 40, 90, TEMP_MAX)


def check_host(raw):
    """A host name or address in the home network, nothing else (no scheme, no port, no path)."""
    import nas
    host = str(raw or "").strip().lower().strip("[]")
    if not host or len(host) > 253 or not HOST.fullmatch(host) or ".." in host:
        raise ValueError("Bitte nur den Namen oder die IP-Adresse der NAS, ohne http:// und ohne Port.")
    if not nas.home_name(host):
        raise ValueError("Nur eine NAS im Heimnetz (zum Beispiel ds.fritz.box oder 192.168.178.20).")
    return host


# ---------------------------------------------------------------- reading (SNMPv3 authPriv only)
def _user(d):
    """The SNMPv3 user: always authPriv with SHA and AES-128. Nothing else is ever built (no v1, no v2c)."""
    from pysnmp.hlapi.v3arch.asyncio import UsmUserData, usmAesCfb128Protocol, usmHMACSHAAuthProtocol
    auth_pw = vault.open_(d.get("auth") or "") if d.get("auth") else ""
    priv_pw = vault.open_(d.get("priv") or "") if d.get("priv") else ""
    if not USER.fullmatch(str(d.get("user") or "")) or len(auth_pw or "") < 8 or len(priv_pw or "") < 8:
        raise Problem("unset")
    return UsmUserData(d["user"], auth_pw, priv_pw, authProtocol=usmHMACSHAAuthProtocol,
                       privProtocol=usmAesCfb128Protocol)


def _kind(err):
    """pysnmp's error indication -> a fixed word (never its text)."""
    name = type(err).__name__
    if name == "RequestTimedOut":
        return "offline"
    if name in ("UnknownUserName", "WrongDigest", "DecryptionError", "UnsupportedSecurityLevel", "AuthenticationError",
                "AuthenticationFailure", "UnknownSecurityName"):
        return "auth"
    return "other"


def _plain(v):
    """A pysnmp value -> int or str (never an object); None for "no such object"."""
    name = type(v).__name__
    if name in ("NoSuchObject", "NoSuchInstance", "EndOfMibView", "Null"):
        return None
    if name in ("OctetString", "DisplayString"):
        try:
            return bytes(v).decode("utf-8", "replace")[:200]
        except Exception:   # noqa: BLE001 - an odd value is dropped
            return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


async def _query(ip, port, d):
    """{oid: value} for SCALARS, the DISK and RAID tables and the hrStorageTable columns. Raises Problem."""
    from pysnmp.hlapi.v3arch.asyncio import (ContextData, ObjectIdentity, ObjectType, SnmpEngine, UdpTransportTarget,
                                             bulk_walk_cmd, get_cmd)
    user = _user(d)
    eng = SnmpEngine()
    out = {}
    try:
        target = await UdpTransportTarget.create((ip, port), timeout=TIMEOUT, retries=RETRIES)
        err, status, _, binds = await get_cmd(eng, user, target, ContextData(),
                                              *(ObjectType(ObjectIdentity(o)) for o in SCALARS.values()))
        if err:
            raise Problem(_kind(err))
        if status:
            raise Problem("bad")
        for oid, v in binds:
            out[str(oid)] = _plain(v)
        for base in (DISK, RAID) + tuple(f"{HR}.{c}" for c in HR_COLS):
            n = 0
            async for err, status, _, binds in bulk_walk_cmd(eng, user, target, ContextData(), 0, 25,
                                                             ObjectType(ObjectIdentity(base)), lexicographicMode=False):
                if err:
                    raise Problem(_kind(err))
                if status:
                    break        # an older DSM without this table
                for oid, v in binds:
                    out[str(oid)] = _plain(v)
                    n += 1
                if n > MAX_ROWS * 20:
                    break
    finally:
        try:
            eng.close_dispatcher()
        except Exception:   # noqa: BLE001
            pass
    return out


def _int(v, lo, hi):
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else None


def _u32(v):
    """hrStorageSize/Used are Integer32: a big disk wraps to a negative number (net-snmp), read it as unsigned."""
    v = _int(v, -2 ** 31, 2 ** 31 - 1)
    return None if v is None else v + 2 ** 32 if v < 0 else v


def _usb(rows):
    """USB and eSATA disks from the hrStorageTable rows: only mounts like /volumeUSB2/usbshare, named by number."""
    out, dropped = [], 0
    for i, r in sorted(rows.items()):
        m = USB_PATH.fullmatch(r.get("descr").strip()) if isinstance(r.get("descr"), str) else None
        if not m:
            continue          # memory, / and the volumes: not asked for, not counted
        if len(out) >= MAX_ROWS:
            dropped += 1
            continue
        unit, size, used = _int(r.get("unit"), 1, 2 ** 24), _u32(r.get("size")), _u32(r.get("used"))
        if size == 2 ** 31 - 1 or used == 2 ** 31 - 1 or (size is not None and used is not None and used > size):
            size = used = None      # capped by the agent or odd: no numbers rather than wrong ones
            dropped += 1
        n = int(m.group(2))
        part = int(m.group(3)) if m.group(3) else 0
        name = ("USB-Platte" if m.group(1) == "USB" else "eSATA-Platte") + f" {n}" + (f" Teil {part}" if part else "")
        en = ("USB disk" if m.group(1) == "USB" else "eSATA disk") + f" {n}" + (f" part {part}" if part else "")
        total = size * unit if unit and size else None
        free = (size - used) * unit if total and used is not None else None
        out.append({"n": n, "name": name, "en": en, "pct": round(100 * used / size) if free is not None else None,
                    "free_gb": free // 2 ** 30 if free is not None else None,
                    "total_gb": total // 2 ** 30 if total else None})
    return out, dropped


def _parse(raw):
    """Only the asked-for OIDs, sane numbers and plain names: {"up_s", "sys", "temp", "power", "fans", "model",
    "dsm", "update", "disks": [...], "vols": [...] (each with "kind" pool, cache or vol), "usb": [...], "dropped"}."""
    raw = raw if isinstance(raw, dict) else {}
    dropped = 0
    out = {}
    s = {k: raw.get(o) for k, o in SCALARS.items()}
    up = _int(s["up"], 0, 2 ** 32)
    out["up_s"] = up // 100 if up is not None else None
    t = _int(s["temp"], -20, 150)
    out["temp"] = t
    dropped += s["temp"] is not None and t is None
    out["sys"] = {1: "ok", 2: "fehler"}.get(_int(s["sys"], 1, 2))
    out["power"] = {1: "ok", 2: "fehler"}.get(_int(s["power"], 1, 2))
    fans = [x for x in (_int(s["fan"], 1, 2), _int(s["cpufan"], 1, 2)) if x]
    out["fans"] = ("fehler" if 2 in fans else "ok") if fans else None
    out["update"] = {1: True, 2: False}.get(_int(s["update"], 1, 5))
    for k in ("model", "dsm"):
        v = s[k].strip() if isinstance(s[k], str) else ""
        out[k] = v if NICE.fullmatch(v) else ""
        dropped += bool(v) and not out[k]
    rows = {}
    for base, cols, kind, top in ((DISK, DISK_COLS, "disk", 1000), (RAID, RAID_COLS, "raid", 1000), (HR, HR_COLS, "hr", 65535)):
        for oid, v in raw.items():
            if not oid.startswith(base + "."):
                continue
            rest = oid[len(base) + 1:].split(".")
            if len(rest) != 2 or rest[0] not in cols or not rest[1].isdigit() or int(rest[1]) > top:
                dropped += 1
                continue
            rows.setdefault((kind, int(rest[1])), {})[cols[rest[0]]] = v
    disks, vols = [], []
    usb, n = _usb({i: r for (kind, i), r in rows.items() if kind == "hr"})
    dropped += n
    for (kind, i), r in sorted(rows.items()):
        if kind == "hr":
            continue
        if kind == "disk":
            if len(disks) >= MAX_ROWS:
                dropped += 1
                continue
            st = DISK_ST.get(_int(r.get("st"), 1, 5))
            temp = _int(r.get("temp"), -20, 150)
            dropped += r.get("temp") is not None and temp is None
            disks.append({"n": len(disks) + 1, "st": st, "temp": temp,
                          "health": DISK_HEALTH.get(_int(r.get("health"), 1, 4))})
        else:
            if len(vols) >= MAX_ROWS:
                dropped += 1
                continue
            free, total = _int(r.get("free"), 0, 2 ** 60), _int(r.get("total"), 1, 2 ** 60)
            if free is not None and total is not None and free > total:
                free = total = None
                dropped += 1
            name = r.get("name").strip() if isinstance(r.get("name"), str) else ""
            name = name if VOL_NAME.fullmatch(name) else ""
            vols.append({"n": len(vols) + 1, "name": name, "kind": art(name),
                         "st": RAID_ST.get(_int(r.get("st"), 1, 21)),
                         "pct": round(100 * (total - free) / total) if free is not None and total else None,
                         "free_gb": free // 2 ** 30 if free is not None and total else None,
                         "total_gb": total // 2 ** 30 if total else None})
    out["disks"], out["vols"], out["usb"], out["dropped"] = disks, vols, usb, dropped
    if out["up_s"] is None and not disks and not vols and out["temp"] is None:
        raise Problem("bad")
    return out


async def read(d=None):
    """Asks the NAS now (through netguard HOME). The values, or raises Problem."""
    d = _read() if d is None else d
    if not d.get("host"):
        raise Problem("unset")
    try:
        ip = await asyncio.to_thread(netguard.resolve, d["host"], int(d.get("port") or PORT), netguard.HOME)
    except netguard.Blocked as e:
        raise Problem("notaus" if "Notaus" in str(e) else "blocked")
    except Exception:   # noqa: BLE001 - a name that is not found
        raise Problem("offline")
    try:
        raw = await asyncio.wait_for(_query(ip, int(d.get("port") or PORT), d), DEADLINE)
    except asyncio.TimeoutError:
        raise Problem("offline")
    except Problem:
        raise
    except Exception as e:   # noqa: BLE001 - a broken answer is "bad", never its text
        print("naszustand: lesen fehler", type(e).__name__, flush=True)
        raise Problem("other")
    return _parse(raw)


# ---------------------------------------------------------------- what is wrong (fixed words and numbers)
def problems(v, c=None):
    """[(code, German words, English words)] for the admins' note and the page."""
    if not v:
        return []
    full, hot = limits(c)
    out = []
    for x in v.get("vols") or []:
        de, en = (x["name"], x["name"]) if x.get("name") else (f"Speicherbereich {x['n']}", f"Storage area {x['n']}")
        if x.get("st") in RAID_BAD:
            out.append((f"raid{x['n']}", f"{de} {x['st']}", f"{en} {WORDS_EN[x['st']]}"))
        # a pool's "used" is what it gave to volumes, a cache is always full: only a volume can run out of room
        if art(x.get("name")) == "vol" and isinstance(x.get("pct"), int) and x["pct"] >= full:
            out.append((f"voll{x['n']}", f"{de} zu {x['pct']} % belegt", f"{en} {x['pct']} % full"))
    for i, x in enumerate(v.get("usb") or [], 1):
        if isinstance(x.get("pct"), int) and x["pct"] >= full:
            out.append((f"usbvoll{i}", f"{x['name']} zu {x['pct']} % belegt", f"{x.get('en') or x['name']} {x['pct']} % full"))
    for x in v.get("disks") or []:
        bad = x.get("st") if x.get("st") in ("fehler", "defekt") else x.get("health") if x.get("health") not in (None, "ok") else ""
        if bad:
            out.append((f"platte{x['n']}", f"Festplatte {x['n']}: {bad}", f"Disk {x['n']}: {WORDS_EN[bad]}"))
        if isinstance(x.get("temp"), int) and x["temp"] >= hot:
            out.append((f"plattewarm{x['n']}", f"Festplatte {x['n']} {x['temp']} °C", f"Disk {x['n']} {x['temp']} °C"))
    if isinstance(v.get("temp"), int) and v["temp"] >= hot:
        out.append(("warm", f"System {v['temp']} °C", f"System {v['temp']} °C"))
    for k, de, en in (("sys", "System meldet einen Fehler", "System reports an error"),
                      ("fans", "Lüfter ausgefallen", "Fan failed"), ("power", "Netzteil meldet einen Fehler", "Power supply reports an error")):
        if v.get(k) == "fehler":
            out.append((k, de, en))
    return out


def _tell(d, v, now):
    """A problem seen SEEN_N times in a row goes to the admins once; when it is gone, that it is fine again."""
    import dienstwacht
    now_codes = {code: de for code, de, _ in problems(v)}
    seen = {k: int(n) + 1 for k, n in (d.get("seen") or {}).items() if k in now_codes}
    seen.update({k: 1 for k in now_codes if k not in seen})
    warn = dict(d.get("warn") or {})
    told = fine = 0
    for code, de in now_codes.items():
        if code not in warn and seen[code] >= SEEN_N:
            warn[code] = {"since": int(now), "w": de}
            dienstwacht.warn("naszustand", de, True, now)
            told += 1
    for code in [k for k in warn if k not in now_codes]:
        dienstwacht.warn("naszustand", warn.pop(code)["w"], False, now)
        fine += 1
    if told or fine:
        print(f"naszustand: hinweis | {told} neu | {fine} wieder gut | {len(warn)} offen", flush=True)
    return warn, seen


async def read_once(why="auto", now=None):
    """One reading, stored with its outcome. {"ok": True, "values"} or {"ok": False, "why"}."""
    now = time.time() if now is None else now
    d = _read()
    if not set_up():
        return {"ok": False, "why": "unset"}
    _mem["running"] = True
    try:
        v = await read(d)
    except Problem as e:
        _update(last={"t": int(now), "ok": False, "why": e.kind})
        print(f"naszustand: lesen fehlgeschlagen | {e.kind} | {why}", flush=True)
        return {"ok": False, "why": e.kind}
    finally:
        _mem["running"] = False
    v["t"] = int(now)
    with _lock:
        d = _read()
        warn, seen = _tell(d, v, now)
        was_ok = (d.get("last") or {}).get("ok")
        d.update(last={"t": int(now), "ok": True}, values=v, warn=warn, seen=seen, reads=int(d.get("reads") or 0) + 1)
        _write(d)
    if why != "auto" or not was_ok or v["dropped"]:     # every good reading counts; a line when it means something
        print(f"naszustand: gelesen | {len(v['vols'])} bereiche | {len(v['usb'])} usb | {len(v['disks'])} platten | {len(warn)} hinweise"
              f" | {v['dropped']} verworfen | {why}", flush=True)
    return {"ok": True, "values": v}


def due(now=None):
    now = time.time() if now is None else now
    last = _read().get("last") or {}
    return now - int(last.get("t") or 0) >= (READ_EVERY if last.get("ok") else RETRY)


def _paused(now):
    import nasquelle
    import notaus
    return nasquelle._paused(now) or notaus.blocks("auto")


async def round_once(now=None):
    now = time.time() if now is None else now
    if not admin_on() or not set_up() or _paused(now) or not due(now) or _mem["running"]:
        return None
    import vorrang
    if vorrang.speaking():
        return None
    return await read_once("auto", now)


async def loop():
    while True:
        await asyncio.sleep(30)
        try:
            await round_once()
        except Exception as e:   # noqa: BLE001 - the next round tries again
            print("naszustand: loop", type(e).__name__, flush=True)


def reachable(now=None):
    """For the Dienst-Wächter: the newest reading answered and is fresh (no extra question to the NAS)."""
    now = time.time() if now is None else now
    last = _read().get("last") or {}
    return bool(last.get("ok")) and now - int(last.get("t") or 0) < FRESH


def probes():
    """For the Dienst-Wächter: one part while the switch is on and the NAS is set up."""
    if not admin_on() or not set_up():
        return {}
    return {"snmp": {"snmp": True, "host": _read().get("host", "")}}


# ---------------------------------------------------------------- what pages, Live and the assistant see
def public(d=None, c=None):
    d = _read() if d is None else d
    full, hot = limits(c)
    v = d.get("values") or None
    if v:      # the kind from the name also for a reading stored before it was kept (art(): one source for the page)
        v = dict(v, vols=[dict(x, kind=art(x.get("name"))) for x in v.get("vols") or []])
    return {"on": switched(c), "set": set_up(), "host": d.get("host", ""), "port": int(d.get("port") or PORT),
            "user": d.get("user", ""), "has_auth": bool(d.get("auth")), "has_priv": bool(d.get("priv")),
            "last": d.get("last"), "values": v, "running": _mem["running"],
            "problems": [{"de": de, "en": en} for _, de, en in problems(v, c)], "full_pct": full, "temp_max": hot,
            "words": WORDS_EN, "why_words": WHY}


def for_live():
    """Live: whether it answers, volumes, pools, USB disks, disks and open problems (numbers only)."""
    if not admin_on() or not set_up():
        return {"on": False}
    d = _read()
    v = d.get("values") or {}
    kinds = [art(x.get("name")) for x in v.get("vols") or []]
    return {"on": True, "ok": reachable(), "vols": kinds.count("vol"), "pools": kinds.count("pool"),
            "usb": len(v.get("usb") or []), "disks": len(v.get("disks") or []), "warn": len(d.get("warn") or {})}


def alerts():
    """The banner on admin pages: the problems the admins were told of and that still hold."""
    if not admin_on():
        return []
    return [{"kind": "naszustand", "level": "warn", "go": "Zustand → Dienste",
             "text": f"Zustand der NAS: {x['w']}."} for x in (_read().get("warn") or {}).values()][:5]


def _dur(s):
    if not isinstance(s, int):
        return "unbekannt"
    days, hours = s // 86400, s % 86400 // 3600
    return f"{days} Tagen und {hours} Stunden" if days else f"{hours} Stunden"


def text(part="alles"):
    """The tool's answer: fixed words and numbers (volume names only like "Volume 1")."""
    d = _read()
    last = d.get("last") or {}
    v = d.get("values")
    if not v:
        return ("Die NAS hat noch keine Werte geliefert" + (f" ({WHY[last['why']][0]})" if last.get("why") in WHY else "")
                + ". Einrichten unter Funktionen → Speicher und NAS → Zustand der NAS.")
    out = []
    if not last.get("ok"):
        out.append(f"Die NAS antwortet gerade nicht ({WHY.get(last.get('why'), WHY['other'])[0]}); das sind die Werte von "
                   + time.strftime("%d.%m. %H:%M", time.localtime(v.get("t") or 0)) + ".")
    if part in ("alles", "platz"):
        for x in v.get("vols") or []:
            name = x["name"] or f"Speicherbereich {x['n']}"
            line = f"{name}: {x['st'] or 'Zustand unbekannt'}"
            kind = art(x.get("name"))
            if kind == "pool" and isinstance(x.get("pct"), int):
                line += (f", ganz an Volumes vergeben ({x['total_gb']} GB)" if x["free_gb"] == 0 else
                         f", {x['total_gb'] - x['free_gb']} von {x['total_gb']} GB an Volumes vergeben, {x['free_gb']} GB noch nicht vergeben")
            elif kind == "vol" and isinstance(x.get("pct"), int):
                line += f", {x['pct']} % belegt, {x['free_gb']} GB frei von {x['total_gb']} GB"
            out.append(line + ".")
        if not v.get("vols"):
            out.append("Speicherbereiche: keine gemeldet.")
        for x in v.get("usb") or []:
            out.append(f"{x['name']}: " + (f"{x['pct']} % belegt, {x['free_gb']} GB frei von {x['total_gb']} GB."
                                           if isinstance(x.get("pct"), int) else "Größe nicht lesbar."))
    if part in ("alles", "platten"):
        for x in v.get("disks") or []:
            st = x["health"] if x.get("health") not in (None, "ok") else x.get("st") or "unbekannt"
            out.append(f"Festplatte {x['n']}: {st}" + (f", {x['temp']} °C" if isinstance(x.get("temp"), int) else "") + ".")
    if part in ("alles", "system"):
        out.append("System: " + ", ".join(y for y in (
            f"{v['temp']} °C" if isinstance(v.get("temp"), int) else "",
            "Lüfter in Ordnung" if v.get("fans") == "ok" else "Lüfter ausgefallen" if v.get("fans") == "fehler" else "",
            "Netzteil meldet einen Fehler" if v.get("power") == "fehler" else "",
            f"läuft seit {_dur(v.get('up_s'))}" if v.get("up_s") is not None else "",
            (f"{v['dsm']}" if v.get("dsm") else "")
            + (", Update verfügbar" if v.get("update") is True else ", kein Update" if v.get("update") is False else "")) if y) + ".")
    probs = problems(v)
    out.append("Probleme: " + "; ".join(de for _, de, _ in probs) + "." if probs else "Keine Probleme gemeldet.")
    return " ".join(out)


# ---------------------------------------------------------------- the tool nas_zustand (reading, admins only)
WORDS = re.compile(r"(?i)\b(nas|synology|diskstation|festplatte\w*|raid|volume\w*|speicherplatz|"
                   r"platz auf der nas|wie voll|disk\w*)\b")
PARTS = ("alles", "platz", "platten", "system")
TOOL = {"type": "function", "function": {
    "name": "nas_zustand",
    "description": "How the user's NAS is doing, read by the panel over SNMP: volumes (state, % used, GB free), storage "
                   "pools (how much is given to volumes, not free space), USB disks on the NAS (% used, GB free), "
                   "disks (state, temperature), system temperature, fans, uptime, DSM version and update. Only for "
                   "the admin. Answer only from this result, never guess that all is well.",
    "parameters": {"type": "object", "properties": {
        "teil": {"type": "string", "enum": list(PARTS), "description": "which part (default alles)"}}}}}
HINT = ("Fragt der Admin, wie voll die NAS ist, ob es den Festplatten gut geht oder wie es der NAS geht, ruf "
        "nas_zustand und antworte nur aus dessen Ergebnis.")
# reads only numbers and fixed words the panel took from the own NAS (chat.INSIDE)
INSIDE = {"nas_zustand"}


def allowed(uid, c=None):
    """Only an admin profile, only with the admin switch and a NAS set up."""
    import zustand_wz
    return bool(uid) and features.allowed("naszustand", uid, c) and zustand_wz.is_admin(uid) and set_up()


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp" or not allowed(who["id"]):
        return None
    if not WORDS.search(str(ctx.get("text") or "")):
        return None
    return {"tools": [TOOL], "hint": HINT, "keep": {"nas_zustand"},
            "filler": {"nas_zustand": ("Ich schaue bei der NAS nach.", "Let me check the NAS.")}}


async def tool(name, args, ctx):
    who = ctx.get("who") or {}
    if name != "nas_zustand" or not allowed(who.get("id")):
        print("naszustand: werkzeug abgelehnt | nicht erlaubt", flush=True)
        return "Den Zustand der NAS sieht nur ein Admin, wenn er unter Funktionen → Speicher und NAS eingerichtet ist."
    args = args if isinstance(args, dict) else {}
    part = args.get("teil") if args.get("teil") in PARTS else "alles"
    d = _read()
    if time.time() - int((d.get("last") or {}).get("t") or 0) > 60 and not _mem["running"]:
        await read_once("frage")
    print(f"naszustand: werkzeug | {part}", flush=True)
    return text(part)


# ---------------------------------------------------------------- routes (admin)
@router.get("/api/admin/naszustand", dependencies=[Depends(auth)])
def get_state(request: Request):
    guard.limit(request, "naszustand", admin=True)
    return public()


# where the Spark's SNMP user goes: an admin, at the level in stufen.py
@router.put("/api/admin/naszustand", dependencies=[Depends(auth), Depends(admin_code)])
async def put_state(request: Request):
    """{"host", "user", "auth", "priv"}: empty passwords keep the stored ones (a new host needs them again)."""
    guard.limit(request, "naszustand", admin=True)
    if not switched():
        raise HTTPException(403, "Zustand der NAS ist aus (Funktionen → Speicher und NAS).")
    b = await core.json_body(request, 2048)
    d = _read()
    try:
        host = check_host(b.get("host", d.get("host", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))
    user = str(b.get("user", d.get("user", "")) or "").strip()
    if not USER.fullmatch(user):
        raise HTTPException(400, "Benutzer: bis 32 Buchstaben, Ziffern, . _ -")
    new = dict(d, host=host, user=user, port=PORT)
    if host != d.get("host") or user != d.get("user"):
        new.update(auth="", priv="", values=None, warn={}, seen={}, last=None)   # never old passwords to a new place
    for k, label in (("auth", "Passwort für die Anmeldung (SHA)"), ("priv", "Passwort für die Verschlüsselung (AES)")):
        pw = b.get(k)
        if isinstance(pw, str) and pw:
            if not 8 <= len(pw) <= 64 or re.search(r"[\x00-\x1f\x7f]", pw):
                raise HTTPException(400, f"{label}: 8 bis 64 Zeichen.")
            new[k] = vault.seal(pw)
    if not (new.get("auth") and new.get("priv")):
        raise HTTPException(400, "Bitte beide Passwörter eingeben (Anmeldung und Verschlüsselung).")
    with _lock:
        _write(new)
    guard.log("naszustand_settings", detail="SNMPv3 authPriv")
    print("naszustand: eingerichtet | snmpv3 authpriv", flush=True)
    res = await read_once("einrichten")
    return dict(public(), checked=res.get("ok", False), why=res.get("why", ""))


@router.post("/api/admin/naszustand/now", dependencies=[Depends(auth)])
async def read_now(request: Request):
    guard.limit(request, "naszustandnow", admin=True)
    if not switched():
        raise HTTPException(403, "Zustand der NAS ist aus (Funktionen → Speicher und NAS).")
    if not set_up():
        raise HTTPException(409, "Erst die NAS einrichten.")
    if _mem["running"]:
        raise HTTPException(409, "Die NAS wird gerade gelesen.")
    res = await read_once("von hand")
    return dict(public(), checked=res.get("ok", False), why=res.get("why", ""))


@router.delete("/api/admin/naszustand", dependencies=[Depends(auth)])
def forget(request: Request):
    """Forgets host, user and passwords; the switch stays as it is."""
    guard.limit(request, "naszustand", admin=True)
    with _lock:
        _write({})
    guard.log("naszustand_settings", detail="vergessen")
    print("naszustand: vergessen", flush=True)
    return public()
