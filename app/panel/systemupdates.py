"""System-Updates (Zustand → System-Updates, Dominik 2026-11-04 „1a 2a 3a 4a“, pictures 06:42 „Ok“).

One card under Zustand → Überblick (Bereiche, next to Geräte-Updates) and its page with one column per computer: the
panel's computer (the Pi) and, when the models run apart, the model computer (tars). Admins only, no tool for the
model, never for guests; off until the admin switches Funktionen → System-Updates on.

1. Betriebssystem: every CHECK_EVERY (and „Jetzt prüfen“) each computer's root unit speech-spark-systemupdate asks
   its sources and simulates the run (../sysupdate.py: how many, how many for security, package name old → new).
   „Jetzt einspielen“ (fresh code) writes the wish einspielen; the panel starts it only after a pause of PAUSE_S
   without speech („Wartet, Sprache läuft“, „Nicht mehr warten“ takes the wish back). The run itself is fixed in
   sysupdate.py and speech-spark.sh (own sources only, never a removal, firmware and drivers held back, lowest
   priority); it shows „läuft · n von m“. A restart happens only on the admin's word: „Jetzt neu starten“ (fresh
   code) or „Heute Nacht“ (fresh code, in the night window, only while nobody talks).
2. OpenCode and Python packages: the pinned OpenCode (werkstatt.OPENCODE_VERSION, the one source) against the
   newest version on npm (metadata only, nothing downloaded), and OSV warnings for the locked Python packages
   (app/requirements-*.lock: names and versions only go out). „Von Claude prüfen lassen“ keeps a check request with a
   fixed text to hand to a Claude thread; nothing is ever installed from here: it comes with the next Spark update.
3. Firmware and drivers (the Pi's EEPROM, NVIDIA driver and DGX OS): shown only; by hand with the guide
   the guide „Firmware von Hand“ at the bottom of Zustand → System-Updates → Einzelheiten.
4. Zeitpunkt: per computer „Nachts einspielen (03–05 Uhr)“ (own switches, off): only the operating system, never
   firmware, never a restart without the admin; after the Spark's own night update (update.night_once), never while
   it runs, never while somebody talks.

    STATE/system-updates.json  {"checked", "wartet": {rolle: t}, "nacht": {rolle: day}, "neustart_nacht": {rolle: day},
                                "osv": {...}, "opencode": {...}, "pruefbitte": {...}}
    GET    /api/admin/sysup                 both computers, packages, OSV, OpenCode, the check request
    POST   /api/admin/sysup/pruefen         check now (both computers, OSV, OpenCode), at most every CHECK_GAP
    POST   /api/admin/sysup/einspielen      {"rechner"}: the fixed run (fresh code), after a pause in speech
    POST   /api/admin/sysup/nicht-warten    {"rechner"}: take back a waiting run and a restart planned for tonight
    POST   /api/admin/sysup/neustart        {"rechner", "wann": "jetzt"|"nacht"}: restart (fresh code), only when needed
    POST   /api/admin/sysup/nacht           {"rechner", "an"}: the switch „Nachts einspielen“ of one computer (code, like
                                            every switch that lets root act by itself: admin.SENSITIVE)
    POST   /api/admin/sysup/pruefbitte      the check request for a Claude thread (a fixed text, nothing installed)
    DELETE /api/admin/sysup/pruefbitte      removes it
"""
import asyncio
import os
import re
import sys
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import features  # noqa: E402
import guard  # noqa: E402
import notaus  # noqa: E402
import osv  # noqa: E402
import sysupdate  # noqa: E402
from common import STATE, load_config, model_local, read_json, run, write_json  # noqa: E402
from core import admin_code, admin_code_fresh, auth, json_body  # noqa: E402

router = APIRouter()
_lock = threading.Lock()
_busy = asyncio.Lock()

CHECK_EVERY = 6 * 3600
CHECK_GAP = 60             # „Jetzt prüfen“ at most this often
PAUSE_S = 120              # a run starts only after this long without speech (update.BUSY_S)
LOOP = 30
NIGHT = (3, 5)             # the same window as the Spark's own night update (update.NIGHT)
MAX_BODY = 256
LIVE_CACHE = 10
OSV_URL, OSV_MAX = osv.OSV_URL, osv.OSV_MAX     # app/osv.py, the one place for OSV
NPM_URL = "https://registry.npmjs.org/opencode-linux-{arch}/latest"
NPM_MAX = 262144
LOCKS = ("requirements-panel.lock",)
LOCK_LINE, OSV_ID = osv.PIN, osv.OSV_ID
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLLEN = sysupdate.ROLLEN
NAMEN = {"panel": ("Panel", "Panel"), "modelle": ("Modelle", "Models")}
FALLBACK = {"panel": ("Panel-Rechner", "Panel computer"), "modelle": ("Modell-Rechner", "Model computer")}
WARUM = {"aus": "System-Updates sind aus (Funktionen → System-Updates).",
         "rechner": "Diesen Rechner gibt es hier nicht.",
         "laeuft": "Auf diesem Rechner läuft schon ein Update.",
         "spark": "Das Spark-Update läuft gerade; danach noch einmal.",
         "nichts": "Es gibt nichts einzuspielen.",
         "nicht_noetig": "Ein Neustart ist gerade nicht nötig.",
         "start": "Ließ sich nicht starten. Auf dem Rechner: sudo speech-spark update, dann noch einmal.",
         "weg": "Der Modell-Rechner antwortet gerade nicht.",
         "notaus": "Der Notaus hält das gerade an."}


def admin_on(c=None):
    return features.admin_on("systemupdates", c)


def nacht_an(rolle, c=None):
    return features.admin_on("systemnachtpanel" if rolle == "panel" else "systemnachtmodelle", c)


def _file():
    return os.path.join(STATE, "system-updates.json")


def _read():
    d = read_json(_file(), {})
    for k in ("wartet", "nacht", "neustart_nacht", "osv", "opencode"):
        if not isinstance(d.get(k), dict):
            d[k] = {}
    return d


def _change(fn):
    with _lock:
        d = _read()
        out = fn(d)
        write_json(_file(), d, mode=0o600)
        return out


def rollen(cfg=None):
    cfg = load_config() if cfg is None else cfg
    return ["panel"] if model_local(cfg) else ["panel", "modelle"]


def talking_ago(now=None):
    """Seconds since somebody last talked with the Spark (vorrang.py), None when never."""
    import vorrang
    now = time.time() if now is None else now
    last = vorrang.last_speech()
    return int(now - last) if last else None


def quiet(now=None):
    ago = talking_ago(now)
    return ago is None or ago >= PAUSE_S


# ---------------------------------------------------------------- the computers
def _unit_hier():
    return run(["systemctl", "is-active", sysupdate.UNIT])[1].strip() in ("active", "activating", "deactivating", "reloading")


STAND_CACHE = 15          # seconds the model computer's state is reused (notes on top and Live ask often)
_stand = {}


def stand(rolle, frisch=False, now=None):
    """One computer's state (checked: names and versions in a fixed character set); None when it does not answer."""
    if rolle == "panel":
        return dict(sysupdate.lesen(), unit=_unit_hier())
    now = time.time() if now is None else now
    t, d = _stand.get(rolle, (0.0, None))
    if frisch or not 0 <= now - t < STAND_CACHE:
        import steuer
        r = steuer.call("systemupdate")
        d = sysupdate.fremd(r) if isinstance(r, dict) else None
        _stand[rolle] = (now, d)
    return d


def laeuft():
    """True while this computer's root unit runs (the Spark's night update waits for it)."""
    if not admin_on():
        return False
    s = stand("panel")
    return bool(s["unit"] or s["lauf"]["laeuft"])


def _starten_hier():
    import subprocess
    try:
        return subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", sysupdate.UNIT], timeout=20,
                              capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def tun(rolle, was):
    """The wish for one computer's root unit: here written and started, there through the Wärter's fixed command."""
    if rolle == "panel":
        sysupdate.wunsch(was, "panel")
        ok = _starten_hier()
    else:
        import steuer
        r = steuer.call("systemupdate_tun", [was])
        ok = isinstance(r, dict) and r.get("ok") is True
    print(f"systemupdate: {was} {rolle} {'gestartet' if ok else 'fehler'}", flush=True)
    return ok


# ---------------------------------------------------------------- OpenCode and the Python packages
def gepinnt():
    """{name: version} of the locked Python packages (the one place they are pinned)."""
    out = {}
    for name in LOCKS:
        try:
            with open(os.path.join(APP, name)) as f:
                for line in f:
                    m = LOCK_LINE.match(line)
                    if m:
                        out[m.group(1).lower()] = m.group(2)
        except OSError:
            continue
    return dict(sorted(out.items()))


def opencode_version():
    import werkstatt
    return werkstatt.OPENCODE_VERSION


def opencode_hier():
    """Whether the OpenCode program is really on this computer: Entwickeln auf dem Pi (install.sh --entwickeln,
    entwickeln.OPENCODE) or the Werkstatt (install.sh --werkstatt, werkstatt.OPENCODE; on one computer both can be
    here). The real file, never a switch."""
    import entwickeln
    import werkstatt
    return any(os.path.isfile(p) and os.access(p, os.X_OK) for p in (entwickeln.OPENCODE, werkstatt.OPENCODE))


def opencode_da(rolle, s=None):
    """Whether OpenCode is installed on the panel's computer (here) or the model computer (its Wärter's state s,
    sysupdate.fremd: the Werkstatt's program there); the version is the one pin for both."""
    if rolle == "panel":
        return opencode_hier()
    return isinstance(s, dict) and s.get("opencode") is True


async def check_osv(c=None):
    """OSV warnings for the locked packages: only names and versions go out, only ids come back."""
    import netguard
    pak = gepinnt()
    body = osv.anfrage(pak)
    err, warn = "", {}
    try:
        if c is not None:
            r = await c.post(OSV_URL, json=body)
        else:
            async with netguard.client(netguard.PUBLIC, max_bytes=OSV_MAX, timeout=30, follow_redirects=False) as cl:
                r = await cl.post(OSV_URL, json=body)
        r.raise_for_status()
        warn = {n: {"v": w["v"], "ids": w["ids"][:sysupdate.MAX_IDS]} for n, w in osv.antwort(pak, r.json()).items()}
    except Exception as e:
        err = type(e).__name__
    print(f"systemupdate: osv {'fehler ' + err if err else 'ok'} {len(warn)} warnungen {len(pak)} pakete", flush=True)
    _change(lambda d: d.update(osv={"t": int(time.time()), "fehler": bool(err), "n": len(pak), "warn": warn}) if not err
            else d["osv"].update(t_fehler=int(time.time()), fehler=True))
    return err


async def check_opencode(c=None, arch=None):
    """The newest OpenCode on npm (the version only, nothing downloaded)."""
    import netguard
    arch = arch or ("arm64" if os.uname().machine in ("aarch64", "arm64") else "x64")
    url = NPM_URL.format(arch=arch)
    err, neu = "", ""
    try:
        if c is not None:
            r = await c.get(url)
        else:
            async with netguard.client(netguard.PUBLIC, max_bytes=NPM_MAX, timeout=20, follow_redirects=False) as cl:
                r = await cl.get(url, headers={"Accept": "application/json"})
        r.raise_for_status()
        v = str((r.json() or {}).get("version") or "")
        if not re.fullmatch(r"\d{1,4}\.\d{1,4}\.\d{1,4}", v):
            raise ValueError("version")
        neu = v
    except Exception as e:
        err = type(e).__name__
    print(f"systemupdate: opencode {'fehler ' + err if err else 'ok'}", flush=True)
    _change(lambda d: d.update(opencode={"t": int(time.time()), "neu": neu, "fehler": False}) if not err
            else d["opencode"].update(t_fehler=int(time.time()), fehler=True))
    return err


def _vt(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


def pruefbitte_text(d=None):
    """The fixed text for a Claude thread: what to re-pin, from names, versions and ids only."""
    d = _read() if d is None else d
    import core
    pb = d.get("pruefbitte") if isinstance(d.get("pruefbitte"), dict) else {}
    zeilen = [f"Prüfbitte System-Updates (Speech on DGX Spark {core.app_version()}, {time.strftime('%Y-%m-%d', time.localtime(pb.get('t') or time.time()))}).",
              "Bitte in einem Claude-Thread prüfen und neu pinnen; der Spark spielt nichts davon selbst ein, es kommt mit dem nächsten Spark-Update.",
              "Ablauf: Version und Prüfsumme neu pinnen, Selbsttests, CHANGELOG, Push über die Warteschlange (Richtlinie Teil 10)."]
    for n, w in sorted((pb.get("python") or {}).items()):
        zeilen.append(f"- Python {n} {w['v']} (app/requirements-*.lock): {', '.join(w['ids'])}")
    oc = pb.get("opencode") or {}
    if oc:
        zeilen.append(f"- OpenCode {oc['alt']} → {oc['neu']} (app/werkstatt.py OPENCODE_VERSION und OPENCODE_SHA512)")
    return "\n".join(zeilen)


def _pruefbitte_punkte(d):
    warn = (d.get("osv") or {}).get("warn") or {}
    oc = (d.get("opencode") or {}).get("neu") or ""
    alt = opencode_version()
    out = {"python": {n: {"v": w["v"], "ids": list(w["ids"])} for n, w in warn.items()}}
    if oc and _vt(oc) > _vt(alt):
        out["opencode"] = {"alt": alt, "neu": oc}
    return out


# ---------------------------------------------------------------- what the page shows
def _rechner(rolle, d, c, lang):
    i = 1 if lang == "en" else 0
    s = stand(rolle)
    host = (s or {}).get("host") or ""
    name = f"{host} ({NAMEN[rolle][i]})" if host else FALLBACK[rolle][i]
    out = {"rolle": rolle, "name": name, "da": s is not None, "nacht": nacht_an(rolle, c),
           "wartet": int(d["wartet"].get(rolle) or 0), "neustart_nacht": d["neustart_nacht"].get(rolle) == _tag(),
           "opencode": opencode_da(rolle, s)}
    if s:
        out.update({k: v for k, v in s.items() if k != "opencode"})
    return out


def _tag(now=None):
    return time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))


def overview(lang="de", now=None):
    now = time.time() if now is None else now
    cfg = load_config()
    c = cfg.get("chat", {})
    if not admin_on(c):
        return {"on": False}
    d = _read()
    osv = d["osv"]
    oc = d["opencode"]
    pak = gepinnt()
    alt = opencode_version()
    return {"on": True, "checked": int(d.get("checked") or 0), "next": int((d.get("checked") or now) + CHECK_EVERY),
            "rechner": [_rechner(r, d, c, lang) for r in rollen(cfg)],
            "osv": {"t": int(osv.get("t") or 0), "fehler": osv.get("fehler") is True, "n": len(pak),
                    "warn": [{"n": n, "v": w["v"], "ids": w["ids"]} for n, w in sorted((osv.get("warn") or {}).items())]},
            "opencode": {"alt": alt, "neu": oc.get("neu") or "", "t": int(oc.get("t") or 0), "fehler": oc.get("fehler") is True,
                         "neuer": bool(oc.get("neu")) and _vt(oc.get("neu")) > _vt(alt)},
            "internet": not notaus.blocks("internet"),
            "pruefbitte": {"t": int(d["pruefbitte"]["t"]), "text": pruefbitte_text(d)} if isinstance(d.get("pruefbitte"), dict) else None,
            "talking": not quiet(now), "pause_s": PAUSE_S, "spark": _spark_nebenan()}


def _spark_nebenan():
    """Nebenan: the Spark's own version and the device updates waiting (counts only, their own pages)."""
    import core
    out = {"version": core.app_version(), "geraete": None}
    try:
        import geraeteupdate
        if geraeteupdate.admin_on():
            o = geraeteupdate.overview()
            out["geraete"] = sum(int(k.get("waiting") or 0) for k in o.get("kinds") or [])
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- checks, waiting runs, the night
async def pruefen_alle(now=None):
    now = time.time() if now is None else now
    _change(lambda d: d.update(checked=int(now)))
    cfg = load_config()
    for r in rollen(cfg):
        await asyncio.to_thread(tun, r, "pruefen")
    if notaus.blocks("internet"):
        print("systemupdate: internet abgelehnt notaus", flush=True)
        return
    await check_osv()
    await check_opencode()


async def tick(now=None):
    now = time.time() if now is None else now
    if not admin_on():
        return ""
    d = _read()
    if notaus.blocks("auto"):
        return "notaus"
    if not 0 <= now - float(d.get("checked") or 0) < CHECK_EVERY:
        await pruefen_alle(now)
        return "geprueft"
    if not quiet(now):
        return "sprache"
    import update
    if await asyncio.to_thread(update.update_running):
        return "spark"
    for r in rollen():
        if d["wartet"].get(r):
            _change(lambda x, r=r: x["wartet"].pop(r, None))
            if await asyncio.to_thread(tun, r, "einspielen"):
                guard.log("sysup_einspielen", detail=f"{r} nach der Sprechpause")
                return "gestartet"
    return await nacht(now)


async def nacht(now=None):
    """The night window: the operating system on the computers whose switch is on (once a night, after the Spark's own
    night update), then a restart the admin asked for tonight. Never firmware, never a restart without that word."""
    now = time.time() if now is None else now
    t = time.localtime(now)
    if not NIGHT[0] <= t.tm_hour < NIGHT[1]:
        return ""
    import update
    if update.night_on() and update._night_day() != _tag(now):   # the Spark's own night update goes first
        return "spark_zuerst"
    d = _read()
    day = _tag(now)
    for r in rollen():
        s = await asyncio.to_thread(stand, r, True)
        if not s or s["unit"] or s["lauf"]["laeuft"]:
            continue
        if nacht_an(r) and d["nacht"].get(r) != day and s["anzahl"]:
            _change(lambda x, r=r: x["nacht"].update({r: day}))
            if await asyncio.to_thread(tun, r, "einspielen"):
                guard.log("sysup_einspielen", detail=f"{r} in der Nacht")
                return "nacht"
        if d["neustart_nacht"].get(r) == day and s["neustart"] and d["nacht"].get(r) in (None, day):
            _change(lambda x, r=r: x["neustart_nacht"].pop(r, None))   # before: the panel's computer goes away with it
            guard.log("sysup_neustart", detail=f"{r} in der Nacht")
            if await asyncio.to_thread(tun, r, "neustart"):
                return "neustart"
    return ""


async def loop():
    while True:
        await asyncio.sleep(LOOP)
        try:
            await tick()
        except Exception as e:
            print("systemupdate: loop", type(e).__name__, flush=True)


# ---------------------------------------------------------------- Live, the notes on top
_live_cache = [0.0, None]


def for_live(now=None):
    """Live: per computer counts and fixed words only (never a package name)."""
    now = time.time() if now is None else now
    if not admin_on():
        return {"on": False}
    if 0 <= now - _live_cache[0] < LIVE_CACHE and _live_cache[1]:
        return _live_cache[1]
    d = _read()
    out = {"on": True, "rechner": [], "warnungen": len((d["osv"].get("warn") or {})),
           "pruefbitte": isinstance(d.get("pruefbitte"), dict)}
    for r in rollen():
        s = stand(r)
        if s is None:
            out["rechner"].append({"rolle": r, "da": False})
            continue
        out["rechner"].append({"rolle": r, "da": True, "anzahl": s["anzahl"], "sicherheit": s["sicherheit"],
                               "laeuft": bool(s["unit"] or s["lauf"]["laeuft"]), "n": s["lauf"]["n"], "m": s["lauf"]["m"],
                               "wartet": bool(d["wartet"].get(r)), "neustart": s["neustart"]})
    _live_cache[:] = [now, out]
    return out


def live_sub(v):
    teile = []
    for x in v.get("rechner") or []:
        wer = NAMEN[x["rolle"]][0]
        if not x.get("da"):
            teile.append(f"{wer}: antwortet nicht")
            continue
        t = f"{wer}: {x['anzahl']} Updates" + (f", {x['sicherheit']} Sicherheit" if x["sicherheit"] else "")
        if x["laeuft"]:
            t += f", läuft {x['n']} von {x['m']}"
        elif x["wartet"]:
            t += ", wartet auf Sprechpause"
        if x["neustart"]:
            t += ", Neustart nötig"
        teile.append(t)
    if v.get("warnungen"):
        teile.append(f"Python: {v['warnungen']} Warnungen")
    if v.get("pruefbitte"):
        teile.append("Prüfbitte offen")
    return " · ".join(teile)[:120]


def alerts():
    """The note on top of the admin pages: security updates waiting, a restart needed (fixed sentences)."""
    if not admin_on():
        return []
    out = []
    for r in rollen():
        s = stand(r)
        if not s:
            continue
        name = FALLBACK[r][0]
        if s["sicherheit"]:
            out.append({"kind": "systemupdate", "level": "warn", "go": "Zustand → System-Updates",
                        "text": f"{s['sicherheit']} Sicherheitsupdates für den {name} unter Zustand → System-Updates."})
        if s["neustart"] and not s["lauf"]["laeuft"]:
            out.append({"kind": "systemupdate_neustart", "level": "info", "go": "Zustand → System-Updates",
                        "text": f"Der {name} braucht einen Neustart, erst danach gelten die Updates (Zustand → System-Updates)."})
    return out


# ---------------------------------------------------------------- routes
async def _body(request, key="sysup_tun"):
    guard.limit(request, key, admin=True)
    body = await json_body(request, MAX_BODY, lenient=True)
    if not admin_on():
        print("systemupdate: abgelehnt aus", flush=True)
        raise HTTPException(409, WARUM["aus"])
    return body


def _rolle(body):
    r = body.get("rechner")
    if r not in rollen():
        print("systemupdate: abgelehnt rechner", flush=True)
        raise HTTPException(400, WARUM["rechner"])
    return r


def _lang(request):
    return "en" if request.query_params.get("lang") == "en" else "de"


@router.get("/api/admin/sysup", dependencies=[Depends(auth)])
async def admin_get(request: Request):
    guard.limit(request, "sysup", admin=True)
    return await asyncio.to_thread(overview, _lang(request))


@router.post("/api/admin/sysup/pruefen", dependencies=[Depends(auth)])
async def admin_pruefen(request: Request):
    await _body(request, "sysup")
    if _busy.locked() or 0 <= time.time() - float(_read().get("checked") or 0) < CHECK_GAP:
        print("systemupdate: pruefen abgelehnt eben", flush=True)
        raise HTTPException(429, "Eben erst geprüft, bitte gleich noch einmal.", headers={"Retry-After": str(CHECK_GAP)})
    async with _busy:
        await pruefen_alle()
    return await asyncio.to_thread(overview, _lang(request))


@router.post("/api/admin/sysup/einspielen", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_einspielen(request: Request):
    r = _rolle(await _body(request))
    if notaus.blocks("auto"):
        print("systemupdate: einspielen abgelehnt notaus", flush=True)
        raise HTTPException(409, WARUM["notaus"])
    s = await asyncio.to_thread(stand, r, True)
    if s is None:
        print("systemupdate: einspielen abgelehnt weg", flush=True)
        raise HTTPException(503, WARUM["weg"])
    if s["unit"] or s["lauf"]["laeuft"]:
        print("systemupdate: einspielen abgelehnt laeuft", flush=True)
        raise HTTPException(409, WARUM["laeuft"])
    if not s["anzahl"]:
        print("systemupdate: einspielen abgelehnt nichts", flush=True)
        raise HTTPException(409, WARUM["nichts"])
    import update
    if await asyncio.to_thread(update.update_running):
        print("systemupdate: einspielen abgelehnt spark", flush=True)
        raise HTTPException(409, WARUM["spark"])
    if not quiet():
        _change(lambda d: d["wartet"].update({r: int(time.time())}))
        print(f"systemupdate: einspielen {r} wartet sprache", flush=True)
        guard.log("sysup_einspielen", detail=f"{r} wartet auf eine Sprechpause")
        return dict(await asyncio.to_thread(overview, _lang(request)), wartet=True)
    if not await asyncio.to_thread(tun, r, "einspielen"):
        raise HTTPException(503, WARUM["start"])
    guard.log("sysup_einspielen", detail=r)
    return await asyncio.to_thread(overview, _lang(request))


@router.post("/api/admin/sysup/nicht-warten", dependencies=[Depends(auth)])
async def admin_nicht_warten(request: Request):
    r = _rolle(await _body(request))

    def fn(d):
        war = bool(d["wartet"].pop(r, None)) | bool(d["neustart_nacht"].pop(r, None))
        return war
    war = _change(fn)
    print(f"systemupdate: nicht warten {r} {'ok' if war else 'keins'}", flush=True)
    return await asyncio.to_thread(overview, _lang(request))


@router.post("/api/admin/sysup/neustart", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_neustart(request: Request):
    body = await _body(request)
    r = _rolle(body)
    wann = body.get("wann")
    if wann not in ("jetzt", "nacht"):
        print("systemupdate: neustart abgelehnt wann", flush=True)
        raise HTTPException(400, "wann: jetzt oder nacht")
    s = await asyncio.to_thread(stand, r, True)
    if s is None:
        print("systemupdate: neustart abgelehnt weg", flush=True)
        raise HTTPException(503, WARUM["weg"])
    if not s["neustart"]:
        print("systemupdate: neustart abgelehnt nicht noetig", flush=True)
        raise HTTPException(409, WARUM["nicht_noetig"])
    if s["unit"] or s["lauf"]["laeuft"]:
        print("systemupdate: neustart abgelehnt laeuft", flush=True)
        raise HTTPException(409, WARUM["laeuft"])
    if wann == "nacht":
        now = time.time()
        day = _tag(now if time.localtime(now).tm_hour < NIGHT[0] else now + 86400)
        _change(lambda d: d["neustart_nacht"].update({r: day}))
        print(f"systemupdate: neustart {r} heute nacht", flush=True)
        guard.log("sysup_neustart", detail=f"{r} heute Nacht")
        return await asyncio.to_thread(overview, _lang(request))
    guard.log("sysup_neustart", detail=f"{r} jetzt")
    if not await asyncio.to_thread(tun, r, "neustart"):
        raise HTTPException(503, WARUM["start"])
    return {"neustart": True, "rechner": r}


NACHT_KEY = {"panel": "system_updates_night_panel", "modelle": "system_updates_night_models"}


@router.post("/api/admin/sysup/nacht", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_nacht(request: Request):
    body = await _body(request)
    r = _rolle(body)
    an = body.get("an")
    if not isinstance(an, bool):
        print("systemupdate: nacht abgelehnt wert", flush=True)
        raise HTTPException(400, "an: true oder false")
    import admin
    by = admin._by(request)

    def save():
        with admin._save_lock:
            new = admin.get_config()
            new["chat"][NACHT_KEY[r]] = an
            old = admin.validate(new)
            admin._save_locked(new, old, by)
    await asyncio.to_thread(save)
    guard.log("config_switch", detail=f"chat.{NACHT_KEY[r]}={'on' if an else 'off'}")
    print(f"systemupdate: nacht {r} {'an' if an else 'aus'}", flush=True)
    return await asyncio.to_thread(overview, _lang(request))


@router.post("/api/admin/sysup/pruefbitte", dependencies=[Depends(auth)])
async def admin_pruefbitte(request: Request):
    await _body(request)

    def fn(d):
        punkte = _pruefbitte_punkte(d)
        if not punkte["python"] and not punkte.get("opencode"):
            return False
        d["pruefbitte"] = dict(punkte, t=int(time.time()))
        return True
    if not _change(fn):
        print("systemupdate: pruefbitte abgelehnt nichts", flush=True)
        raise HTTPException(409, "Es gibt nichts zu prüfen.")
    print("systemupdate: pruefbitte angelegt", flush=True)
    guard.log("sysup_pruefbitte", detail="angelegt")
    import live
    live.mark("System-Updates", "Prüfbitte für einen Claude-Thread angelegt")
    return await asyncio.to_thread(overview, _lang(request))


@router.delete("/api/admin/sysup/pruefbitte", dependencies=[Depends(auth)])
async def admin_pruefbitte_weg(request: Request):
    await _body(request)
    war = _change(lambda d: d.pop("pruefbitte", None) is not None)
    print(f"systemupdate: pruefbitte {'geloescht' if war else 'keine'}", flush=True)
    if war:
        guard.log("sysup_pruefbitte", detail="gelöscht")
    return await asyncio.to_thread(overview, _lang(request))
