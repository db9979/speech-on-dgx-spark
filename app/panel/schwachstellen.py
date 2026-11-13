"""Schwachstellen (Zustand → Schwachstellen, Dominik 2026-11-13 „1“, Bild schwachstellen/entwurf.png): known holes in
what the Spark runs, against the OSV database, with what to do. Admins only, no tool for the model, never for guests;
off until the admin switches Funktionen → Schwachstellen on.

What is checked (every CHECK_EVERY and on „Jetzt prüfen“, at most every CHECK_GAP):
- pi: the panel's Python packages (app/requirements-*.lock), the versions the Spark installs;
- tars: what the model computer really has installed in its venvs (Wärter command `pakete`, app/installiert.py),
  else the engines pinned in install.sh (vLLM, vllm-omni);
- the panel computer's other venvs (those without a lock file, e.g. the Notbetrieb's);
- docker: the model engines' Docker images (modelle.DOCKER): OSV has no entry for an image, so one older than
  DOCKER_TAGE days is named (a newer digest should be looked for);
- docker contents: the Python packages inside the engines' images (read once per digest on the model computer);
- apps: what the apps and companions bring along, from the repository (osv.apps: iPhone Swift packages, Android
  build plugins, NuGet, npm, the panel's vendored JavaScript);
- os: the security updates System-Updates counts for each computer (only when that function is on).
Only package names and versions go out (one batch question), then one question per id for its weight and fix
(app/osv.py, the one place, the same as GitHub's nightly „Pakete prüfen“); only ids, numbers and versions come back,
OSV's texts are never read. Without internet the page shows the last result with its age.

Each finding gets one fixed action (AKTIONEN), never a text from outside:
- anheben: a panel package with a fix: „Lücke schließen“ on GitHub raises it (Weg 1), it comes with the next update;
- neu: an engine (vLLM, yt-dlp) with a fix: a person or a Claude thread pins the new version (GitHub's tests do not
  start the engines);
- abbild: a package inside an engine's Docker image with a fix: a newer image (digest) brings it;
- kein_fix: OSV names no fixed version yet: watch;
- alt: a Docker image older than DOCKER_TAGE days;
- os: security updates of the operating system: Zustand → System-Updates.

    STATE/schwachstellen.json  {"t", "t_fehler", "fehler", "funde": [...], "n": {ort: count}, "seit": {key: t}}
    GET    /api/admin/schwach           the page: the findings, counts per place, the last check
    POST   /api/admin/schwach/pruefen   check now (at most every CHECK_GAP)
"""
import asyncio
import datetime
import glob
import os
import sys
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import features  # noqa: E402
import guard  # noqa: E402
import installiert  # noqa: E402
import modelle  # noqa: E402
import netguard  # noqa: E402
import notaus  # noqa: E402
import osv  # noqa: E402
import steuer  # noqa: E402
import systemupdates  # noqa: E402
import schwachstellen_stand as stand  # noqa: E402
from schwachstellen_stand import _file, _live_cache, _read, live_sub  # noqa: E402,F401
from common import model_local, write_json  # noqa: E402
from core import auth, json_body  # noqa: E402

router = APIRouter()
_lock = threading.Lock()
_busy = asyncio.Lock()

CHECK_EVERY = 6 * 3600
CHECK_GAP = 60             # „Jetzt prüfen“ at most this often
LOOP = 60
MAX_BODY = 256
MAX_RECORDS = 80           # records asked per check (one per id), the rest counts as unknown
DOCKER_TAGE = osv.DOCKER_TAGE
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
ORTE = ("pi", "tars", "docker", "apps", "os")
ORT_NAME = {"pi": ("Pi · Python", "Pi · Python"), "tars": ("tars · Python", "tars · Python"),
            "docker": ("Docker-Abbilder", "Docker images"), "apps": ("Apps und Begleiter", "Apps and companion"),
            "os": ("Betriebssystem", "Operating system")}
AKTIONEN = ("anheben", "neu", "abbild", "alt", "os", "kein_fix")
WARUM = {"aus": "Schwachstellen sind aus (Funktionen → Schwachstellen).",
         "eben": "Eben erst geprüft, bitte gleich noch einmal."}


def admin_on(c=None):
    return features.admin_on("schwachstellen", c)






def _change(fn):
    with _lock:
        d = _read()
        out = fn(d)
        write_json(_file(), d, mode=0o600)
        return out


# ---------------------------------------------------------------- what is checked
def locks(app=APP):
    """[(lock file name, {name: version})] of app/requirements-*.lock."""
    out = []
    for path in sorted(glob.glob(os.path.join(app, "requirements-*.lock"))):
        pins = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = osv.PIN.match(line)
                if m:
                    pins[m.group(1).lower()] = m.group(2)
        out.append((os.path.basename(path), pins))
    return out


def motoren(root=ROOT):
    """{name: version} of the engines pinned in install.sh ({} in a copy without it)."""
    try:
        with open(os.path.join(root, "install.sh"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return {}
    return osv.motoren(text)


def abbilder():
    """[(image name, day pinned)] of modelle.DOCKER."""
    out = []
    for x in modelle.DOCKER.values():
        try:
            out.append((str(x["image"]).split("@")[0], datetime.date.fromisoformat(x["seit"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


LOCK_VENVS = ("panel", "ytdlp")   # venvs built from a lock file: the lock is what they have


def tars_installiert():
    """What the model computer has installed ({"venvs", "abbilder"}), None when it does not answer. On one computer
    for both it is read here."""
    try:
        if model_local():
            return installiert.lesen([x.get("image") for x in modelle.DOCKER.values() if isinstance(x, dict)])
        return installiert.fremd(steuer.call("pakete", timeout=60))
    except Exception:   # noqa: BLE001  (not answering: the engines pinned in install.sh stand in)
        return None


def _venv_pakete(out, ort, venvs):
    for vname, pk in sorted(venvs.items()):
        if vname in LOCK_VENVS:
            continue
        for n, v in pk.items():
            k = f"{ort}:{n}"
            if k in out and out[k][2] != v:
                k = f"{ort}:{n}@{v}"
            out.setdefault(k, (ort, n, v, "neu", "PyPI", vname))


def pakete(app=APP, root=ROOT, tars=None, hier=None):
    """{key: (ort, name, version, wie, ecosystem, wo)}: wie is "anheben" for the panel's own lock (Weg 1 raises it),
    "abbild" for a package inside a Docker image, "neu" for the rest; wo names the venv, image or app part."""
    out = {}
    for lock, pins in locks(app):
        wie = "anheben" if lock == "requirements-panel.lock" else "neu"
        for n, v in pins.items():
            out.setdefault(f"pi:{n}", ("pi", n, v, wie, "PyPI", lock))
    lokal = model_local()
    _venv_pakete(out, "tars" if lokal else "pi", installiert.venvs() if hier is None else hier)
    if tars and tars.get("venvs") and not lokal:
        _venv_pakete(out, "tars", tars["venvs"])
    if not any(v[0] == "tars" for v in out.values()):
        for n, v in motoren(root).items():
            out[f"tars:{n}"] = ("tars", n.split(" ")[0], v, "neu", "PyPI", "install.sh")
    for image, pk in sorted(((tars or {}).get("abbilder") or {}).items()):
        for n, v in (pk or {}).items():
            out[f"docker:{image}:{n}"] = ("docker", n, v, "abbild", "PyPI", image)
    for teil, n, v, oeko in osv.apps(root):
        out.setdefault(f"apps:{n}", ("apps", n, v, "neu", oeko, teil))
    return out


def aktion(wie, w):
    if not w.get("behoben"):
        return "kein_fix"
    return wie


# ---------------------------------------------------------------- the check
async def _client():
    return netguard.client(netguard.PUBLIC, max_bytes=osv.OSV_MAX, timeout=30, follow_redirects=False)


async def frage(pak, c):
    """OSV's batch answer for {key: (ort, name, version, wie)}: {key: {"v", "ids", "alle"}}."""
    named = list({f"{v[1]} {k}": v[2] for k, v in pak.items()}.items())   # OSV is asked the first word, the name
    oeko = {f"{v[1]} {k}": v[4] for k, v in pak.items()}
    out = {}
    for i in range(0, len(named), osv.BATCH):        # OSV takes at most BATCH questions at once
        teil = dict(named[i:i + osv.BATCH])
        r = await c.post(osv.OSV_URL, json=osv.anfrage(teil, oeko))
        r.raise_for_status()
        out.update({k.split(" ", 1)[1]: w for k, w in osv.antwort(teil, r.json()).items()})
    return out


async def genauer(warn, pak, c):
    """Weight, fix and holes without a fix (app/osv.zusammen); a record that does not come counts as unknown."""
    left = MAX_RECORDS
    for k, w in warn.items():
        records = []
        for vid in w["alle"]:
            rec = None
            if left > 0:
                left -= 1
                try:
                    r = await c.get(osv.VULN_URL + vid)
                    r.raise_for_status()
                    rec = r.json()
                except Exception:   # noqa: BLE001  (that hole counts as unknown, without fix)
                    rec = None
            records.append(rec if isinstance(rec, dict) else None)
        w.update(osv.zusammen({"name": pak[k][1], "v": w["v"]}, records, pak[k][4]))
    return warn


def os_funde():
    """Security updates System-Updates counts per computer (only when it is on): [(rolle, count)]."""
    try:
        if not systemupdates.admin_on():
            return []
        out = []
        for r in systemupdates.rollen():
            s = systemupdates.stand(r)
            if s and s.get("sicherheit"):
                out.append((r, int(s["sicherheit"])))
        return out
    except Exception:
        return []


async def pruefen(c=None, heute=None, now=None):
    """One check of everything; returns "" or the error's type name (then the last result stays)."""
    now = time.time() if now is None else now
    heute = heute or datetime.date.fromtimestamp(now)
    if notaus.blocks("internet"):
        print("schwachstellen: pruefen abgelehnt notaus", flush=True)
        return "notaus"
    tars = await asyncio.to_thread(tars_installiert)
    pak = await asyncio.to_thread(pakete, APP, ROOT, tars)
    err, warn = "", {}
    try:
        if c is None:
            async with await _client() as cl:
                warn = await frage(pak, cl)
                await genauer(warn, pak, cl)
        else:
            warn = await frage(pak, c)
            await genauer(warn, pak, c)
    except Exception as e:   # noqa: BLE001  (no answer: the last result stays, with its age)
        err = type(e).__name__
    if err:
        print(f"schwachstellen: pruefen fehler {err} {len(pak)} pakete", flush=True)
        _change(lambda d: d.update(fehler=True, t_fehler=int(now)))
        return err
    funde = []
    for k, w in sorted(warn.items()):
        ort, name, v, wie, _oeko, wo = pak[k]
        funde.append({"key": k, "ort": ort, "n": name, "v": v, "ids": w["ids"], "stufe": w["stufe"], "wo": wo,
                      "score": w["score"], "behoben": w["behoben"], "ohne_fix": w["ohne_fix"], "aktion": aktion(wie, w)})
    for name, day in abbilder():
        tage = (heute - day).days
        if tage > DOCKER_TAGE:
            funde.append({"key": f"docker:{name}", "ort": "docker", "n": name, "v": day.isoformat(), "ids": [],
                          "stufe": "unbekannt", "score": None, "behoben": None, "ohne_fix": 0, "aktion": "alt", "tage": tage})
    for rolle, anzahl in os_funde():
        funde.append({"key": f"os:{rolle}", "ort": "os", "n": rolle, "v": "", "ids": [], "stufe": "unbekannt",
                      "score": None, "behoben": None, "ohne_fix": 0, "aktion": "os", "anzahl": anzahl})
    n = {o: sum(1 for v in pak.values() if v[0] == o) for o in ("pi", "tars", "docker", "apps")}
    n["abbilder"] = len(abbilder())
    n["ungelesen"] = sum(1 for x in ((tars or {}).get("abbilder") or {}).values() if x is None)
    n["tars_da"] = tars is not None

    def fn(d):
        alt = d.get("seit") or {}
        d.update(t=int(now), fehler=False, funde=funde, n=n, seit={f["key"]: int(alt.get(f["key"]) or now) for f in funde})
    _change(fn)
    zahl = {s: sum(1 for f in funde if f["stufe"] == s) for s in osv.STUFEN}
    print(f"schwachstellen: pruefen ok {len(funde)} funde {zahl['kritisch']} kritisch {zahl['hoch']} hoch "
          f"{len(pak)} pakete", flush=True)
    return ""


async def tick(now=None):
    now = time.time() if now is None else now
    if not admin_on():
        return ""
    if notaus.blocks("auto"):
        print("schwachstellen: pruefen abgelehnt notaus", flush=True)
        return "notaus"
    d = _read()
    if 0 <= now - max(float(d.get("t") or 0), float(d.get("t_fehler") or 0)) < CHECK_EVERY:
        return ""
    async with _busy:
        await pruefen(now=now)
    return "geprueft"


async def loop():
    while True:
        await asyncio.sleep(LOOP)
        try:
            await tick()
        except Exception as e:
            print("schwachstellen: loop", type(e).__name__, flush=True)


# ---------------------------------------------------------------- the page, Live, the notes on top
def _rang(f):
    return (AKTIONEN.index(f["aktion"]), osv.STUFEN.index(f["stufe"]), f["n"])


def overview(now=None):
    now = time.time() if now is None else now
    if not admin_on():
        return {"on": False}
    d = _read()
    funde = sorted(d["funde"], key=_rang)
    for f in funde:
        f["neu"] = 0 <= now - float(d["seit"].get(f["key"]) or 0) < 86400
    zahl = {s: sum(1 for f in funde if f["stufe"] == s) for s in osv.STUFEN}
    orte = {o: sum(1 for f in funde if f["ort"] == o) for o in ORTE}
    return {"on": True, "t": int(d.get("t") or 0), "fehler": d.get("fehler") is True, "t_fehler": int(d.get("t_fehler") or 0),
            "next": int(max(d.get("t") or 0, d.get("t_fehler") or 0) + CHECK_EVERY), "funde": funde, "zahl": zahl,
            "orte": orte, "n": d["n"], "internet": not notaus.blocks("internet"), "docker_tage": DOCKER_TAGE,
            "system_updates": bool(_sysup_on())}


def _sysup_on():
    try:
        return systemupdates.admin_on()
    except Exception:
        return False


def ampel(zahl, funde):
    if zahl.get("kritisch"):
        return "bad"
    if zahl.get("hoch") or any(f["aktion"] in ("anheben", "neu", "os") for f in funde):
        return "warn"
    return "ok"









def for_live(now=None):
    """Live: counts per weight, fixed words only (never a package name)."""
    return stand.zahlen(admin_on(), now)


def alerts():
    """The note on top of the admin pages: a critical or high hole (fixed sentences, counts only)."""
    return stand.hinweise(admin_on())


# ---------------------------------------------------------------- routes
async def _body(request, key="sysup_tun"):
    guard.limit(request, key, admin=True)
    body = await json_body(request, MAX_BODY, lenient=True)
    if not admin_on():
        print("schwachstellen: abgelehnt aus", flush=True)
        raise HTTPException(409, WARUM["aus"])
    return body


@router.get("/api/admin/schwach", dependencies=[Depends(auth)])
async def admin_get(request: Request):
    guard.limit(request, "sysup", admin=True)
    return await asyncio.to_thread(overview)


@router.post("/api/admin/schwach/pruefen", dependencies=[Depends(auth)])
async def admin_pruefen(request: Request):
    await _body(request)
    d = _read()
    if _busy.locked() or 0 <= time.time() - max(float(d.get("t") or 0), float(d.get("t_fehler") or 0)) < CHECK_GAP:
        print("schwachstellen: pruefen abgelehnt eben", flush=True)
        raise HTTPException(429, WARUM["eben"], headers={"Retry-After": str(CHECK_GAP)})
    async with _busy:
        err = await pruefen()
    if err == "notaus":
        raise HTTPException(409, "Der Notaus sperrt gerade das Internet.")
    return await asyncio.to_thread(overview)
