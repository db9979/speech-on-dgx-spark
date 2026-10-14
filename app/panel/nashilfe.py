"""Synology-Komfort (plan synology-bauplan.md S3, below "Speicher und NAS"): find a NAS in the home network and show
what the Spark's user may do on a connected place.

Finding: only mDNS announcements in the home network (zeroconf asks the usual "who offers SMB, WebDAV, SFTP?" once
and listens for 4 seconds); no address range is ever scanned. What comes back is outside data: names and models are
cut to plain text, only private IPv4 addresses are kept, nothing is stored. Without a find the profile types the
address as before.

Rights: the folders on the top level of a place are listed (WebDAV PROPFIND, SFTP list) and each is tried for
reading. Writing is tried only in "spark_ablage" (the filing folder of stage S4): a probe file is written and
deleted at once; nowhere else is anything ever written, not even to check. When the user sees system folders like
"homes" (all homes) or "NetBackup", the page warns that this looks like an admin account and recommends a user of
its own; nothing is blocked. SMB cannot list shares without extra protocols: the page says so.
"""
import asyncio
import ipaddress
import re
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import guard
import nas
import nasquelle
import profiles

router = APIRouter()
_on = nas._on                              # the NAS switch and the profile's own browser login

FIND_SECS = 4
MAX_FOUND = 20
MAX_FOLDERS = 40
RIGHTS_SECS = 60
DROP = "spark_ablage"                      # the only folder the Spark ever writes to (S4); here only a probe
# folders only an admin (or a user with too many rights) sees on a Synology
ADMIN_SIGNS = {"homes", "netbackup"}
TYPES = {"_smb._tcp.local.": "smb", "_webdav._tcp.local.": "webdav", "_webdavs._tcp.local.": "webdavs",
         "_sftp-ssh._tcp.local.": "sftp", "_http._tcp.local.": "http"}
_TEXT = re.compile(r"[^\w .,:()+\-]", re.UNICODE)


def _log_name(uid):
    return profiles.log_name(profiles.by_id(uid))


def _clean(v, most=64):
    v = v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v or "")
    return _TEXT.sub("", v).strip()[:most]


def _private(a):
    try:
        ip = ipaddress.ip_address(a)
    except ValueError:
        return False
    return ip.version == 4 and ip.is_private and not ip.is_loopback and not ip.is_link_local


async def _browse(secs=FIND_SECS):
    """Raw finds: [{"type", "name", "addrs", "port", "props"}]. Only mDNS in the home network."""
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    zc = AsyncZeroconf()
    seen = []

    def on(zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Added and len(seen) < 200:
            seen.append((service_type, name))
    browser = AsyncServiceBrowser(zc.zeroconf, list(TYPES), handlers=[on])
    try:
        await asyncio.sleep(secs)
        out = []
        for t, name in seen[:200]:
            info = AsyncServiceInfo(t, name)
            if await info.async_request(zc.zeroconf, 1500):
                out.append({"type": t, "name": name[: -len(t) - 1] if name.endswith("." + t) else name,
                            "addrs": info.parsed_addresses(), "port": info.port or 0, "props": dict(info.properties or {})})
        return out
    finally:
        await browser.async_cancel()
        await zc.async_close()


def merge(raw):
    """One entry per device (by address): name, model, Synology or not, the ports it offers. Outside data."""
    found = {}
    for r in raw:
        kind = TYPES.get(r.get("type"))
        addrs = [a for a in r.get("addrs") or [] if _private(a)]
        if not kind or not addrs:
            continue
        props = {_clean(k, 20).lower(): _clean(v, 40) for k, v in (r.get("props") or {}).items()}
        a = addrs[0]
        d = found.setdefault(a, {"addr": a, "name": "", "model": "", "synology": False, "offers": {}})
        d["name"] = d["name"] or _clean(r.get("name"))
        d["synology"] = d["synology"] or props.get("vendor", "").lower() == "synology"
        d["model"] = d["model"] or props.get("model", "")
        port = int(r.get("port") or 0)
        if 0 < port < 65536:
            d["offers"].setdefault(kind, port)
    items = sorted(found.values(), key=lambda d: (not d["synology"], d["name"].lower(), d["addr"]))[:MAX_FOUND]
    for d in items:
        d["suggest"] = suggest(d)
    return items


def suggest(d):
    """The address to fill in: WebDAV over HTTPS first (Synology package: 5006), then SFTP, then SMB."""
    o = d["offers"]
    if "webdavs" in o:
        return {"kind": "webdav", "url": f"https://{d['addr']}:{o['webdavs']}"}
    if d["synology"]:
        return {"kind": "webdav", "url": f"https://{d['addr']}:5006"}
    if "sftp" in o:
        return {"kind": "sftp", "url": f"sftp://{d['addr']}" + ("" if o["sftp"] == 22 else f":{o['sftp']}")}
    if "smb" in o:
        return {"kind": "smb", "url": f"smb://{d['addr']}"}
    if "webdav" in o:
        return {"kind": "webdav", "url": f"http://{d['addr']}:{o['webdav']}"}
    return None


async def find():
    import notaus
    if notaus.level() >= 1:
        print("nas: suche abgelehnt | notaus", flush=True)
        raise HTTPException(503, "Notaus ist an: der Spark sucht nichts im Netz.")
    try:
        raw = await asyncio.wait_for(_browse(), FIND_SECS + 15)
    except (OSError, asyncio.TimeoutError, ImportError) as e:
        print(f"nas: suche fehler | {type(e).__name__}", flush=True)
        return []
    return merge(raw)


# ---------------------------------------------------------------- rights
async def _write_probe(c):
    """Writes and deletes one probe file in spark_ablage: "schreiben", "lesen" (no write), "fehlt" (no folder)."""
    name = f".spark-probe-{secrets.token_hex(4)}"
    if c["kind"] == "webdav":
        rd = nasquelle._Dav(c, "/" + DROP)
        url = rd.base + "/" + name
        try:
            async with rd._client(nasquelle.TIMEOUT, 64 * 1024) as cl:
                r = await cl.request("PUT", url, auth=rd.auth, content=b"spark", headers={"Content-Type": "text/plain"})
                if r.status_code in (200, 201, 204):
                    await cl.request("DELETE", url, auth=rd.auth)
                    return "schreiben"
                return "fehlt" if r.status_code in (404, 409) else "lesen"
        except (httpx.HTTPError, OSError) as e:
            raise rd._err(e)
    rd = nasquelle._remote(c, "/" + DROP)
    try:
        def put():
            p = rd._at(name)
            with rd._open(p, "wb") as f:
                f.write(b"spark")
            rd._remove(p)
        try:
            await rd._run(put)
            return "schreiben"
        except Exception as e:   # noqa: BLE001 - the drivers raise their own kinds; anything but auth is "fehlt"
            return "lesen" if getattr(e, "kind", "") == "auth" else "fehlt"
    finally:
        await rd.close()


async def rights(c):
    """{"supported", "folders": [{"name", "right"}], "admin_like", "drop", "complete"}."""
    if c["kind"] == "smb":
        return {"supported": False, "folders": [], "admin_like": False, "drop": "", "complete": True}
    rd = nasquelle.reader(c, "")
    t_end = time.monotonic() + RIGHTS_SECS
    try:
        top = await rd.list("")
        names = sorted((n for n, d, _, _ in top if d and not nasquelle.SKIP_DIRS.match(n)), key=str.lower)
        folders, complete = [], len(names) <= MAX_FOLDERS
        for n in names[:MAX_FOLDERS]:
            if time.monotonic() > t_end:
                complete = False
                break
            try:
                await rd.list(n)
                right = "lesen"
            except nasquelle.SourceError as e:
                if e.kind in ("offline", "cert", "blocked", "notaus"):
                    raise
                right = "nein"
            folders.append({"name": n, "right": right})
    finally:
        await rd.close()
    drop = ""
    if any(f["name"] == DROP for f in folders):
        drop = await _write_probe(c)
        for f in folders:
            if f["name"] == DROP and drop == "schreiben":
                f["right"] = "schreiben"
    admin_like = any(n.lower() in ADMIN_SIGNS for n in names)
    return {"supported": True, "folders": folders, "admin_like": admin_like, "drop": drop or "fehlt", "complete": complete}


# ---------------------------------------------------------------- routes
@router.get("/api/profile/nas/find")
async def find_route(request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    items = await find()
    print(f"nas: gesucht | {len(items)} gefunden | {sum(1 for x in items if x['synology'])} synology | {_log_name(prof['id'])}", flush=True)
    return {"items": items, "secs": FIND_SECS}


@router.post("/api/profile/nas/{nid}/rights")
async def rights_route(nid: str, request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    uid = prof["id"]
    c = nas.find(uid, nid)
    if not c:
        raise HTTPException(404, "no such connection")
    try:
        got = await rights(c)
    except nasquelle.SourceError as e:
        print(f"nas: rechte fehler | art={e.kind} | {_log_name(uid)}", flush=True)
        raise HTTPException(502, nasquelle._say(e.kind))
    print(f"nas: rechte | art={c['kind']} | {len(got['folders'])} ordner | ablage={got['drop']} | "
          f"admin={'ja' if got['admin_like'] else 'nein'} | {_log_name(uid)}", flush=True)
    return got
