"""Entwickeln auf dem Pi (plan plaene/opencode-pi.md, Dominik 2026-11-03, Paket 1): the panel's side of app/entwickeln.py,
for admins only, default off (admin switch chat.entwickeln).

OpenCode runs in the terminal of the panel computer as the user spark-dev in its own clone; its changes are commits
on the branch „lokal“ there (Weg B, no GitHub). The panel never reads that clone and never runs any of it: root
(update.sh with app/entwickeln.py) takes the commits, checks them, runs the quick test in a sandbox and installs
them like an update. Here only:

    for_live / live_sub   Zustand → Live, box „Entwickeln“: lokale Änderungen N, waiting in the clone, the last result
    alerts                a hint on top of the admin pages while an update or an install kept the running version
                          because of the local changes (conflict, red quick test), with the way to the update log
    GET  /api/admin/entwickeln             the copy root wrote (counts, short commits, fixed words, red test names)
    POST /api/admin/entwickeln/einspielen  „Lokal einspielen“: a new version of the Spark, so the code every time
    POST /api/admin/entwickeln/zurueck     back to what ran before the last local install (same version only)
    POST /api/admin/entwickeln/verwerfen   the installed version without the local commits (they stay in the clone)

The three POSTs only write the wish STATE/update-lokal (one fixed word) and start the update unit through
update.begin (backup first, the lock, the progress bar); update.sh checks the wish and every rule again as root.

Weg A (package 2, switch Funktionen → Entwickeln auf dem Pi → An GitHub geben, chat.entwickeln_github, off):
    POST /api/admin/entwickeln/github  {"thema"}: a fresh code; the topic in the fixed charset (entwickeln.thema_pruefen)
                          is the wish STATE/github-wunsch, then root's oneshot speech-spark-github pushes spark-dev's
                          branch as opencode/<thema> with root's deploy key (never main, never forced; offline it
                          waits and the timer tries again). The panel never sees the key.
    GET  /api/admin/entwickeln/github  the branches handed over, GitHub's "Tests" for each (the public API through
                          update.green_runs, no key; at most every TESTS_S per branch), the fixed hint for Dominik.
The page part (Zustand → Werkstatt → Entwickeln) comes with package 3; the command line works already:
sudo speech-spark lokal einspielen|zurueck|verwerfen|status.
Logs: "entwickeln: …" with fixed words only.
"""
import asyncio
import os
import sys
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import entwickeln  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
from core import admin_code, admin_code_fresh, auth  # noqa: E402

MAX_BODY = 256           # the POSTs carry nothing
MAX_BODY_GH = 512        # {"thema": …}: the topic is cut to 200 characters and its fixed charset anyway
TESTS_S = 300            # GitHub's tests of one branch asked at most this often (60 questions an hour for everything)
TESTS_ZWEIGE = 3         # only the newest branches are asked about
HINWEIS_S = 3 * 86400    # a refused update or install stays on top of the admin pages this long (or until the next ok)
ART_TEXT = {"einspielen": ("Lokal einspielen", "Install local changes"), "zurueck": ("Lokal zurück", "Local back"),
            "verwerfen": ("Lokal verwerfen", "Drop local changes"), "aufsetzen": ("Update mit lokalen Änderungen", "Update with local changes")}


def _an(cfg=None):
    """Funktionen → Entwickeln auf dem Pi (cfg: the whole configuration, None reads it)."""
    return features.admin_on("entwickeln", None if cfg is None else cfg.get("chat", {}))


def _github_an(cfg=None):
    """Funktionen → Entwickeln auf dem Pi → An GitHub geben (needs Entwickeln auf dem Pi, features.parent)."""
    return features.admin_on("entwickelngithub", None if cfg is None else cfg.get("chat", {}))


def github_daten(path=None):
    """What root last wrote about Weg A (entwickeln.github_anzeige_lesen: checked again here)."""
    return entwickeln.github_anzeige_lesen(path)


def daten(path=None):
    """What root last wrote (entwickeln.anzeige_lesen: checked again here)."""
    return entwickeln.anzeige_lesen(path)


def for_live(path=None, gh_path=None):
    """Zustand → Live, box „Entwickeln“: counts and fixed words only, never a commit text, a path or a test output."""
    if not _an():
        return {"on": False}
    d = daten(path)
    out = {"on": True, "anzahl": d.get("anzahl", 0), "offen": d.get("offen"),
           "letzter": (d.get("letzter") or {}).get("ergebnis"), "art": (d.get("letzter") or {}).get("art")}
    if _github_an():
        g = github_daten(gh_path)
        out.update(github=(g.get("letzter") or {}).get("zustand"), gegeben=len(g["zweige"]))
    return out


def live_sub(v):
    teile = [f"lokale Änderungen: {v.get('anzahl', 0)}"]
    if v.get("offen"):
        teile.append(f"{v['offen']} im Klon noch nicht eingespielt")
    if v.get("letzter") and v["letzter"] != "ok" and v.get("art") in ART_TEXT:
        teile.append(f"zuletzt {ART_TEXT[v['art']][0]} abgelehnt: {v['letzter']}")
    if v.get("gegeben"):
        teile.append(f"an GitHub gegeben: {v['gegeben']}")
    if v.get("github") and v["github"] != "gegeben":
        teile.append(f"an GitHub zuletzt: {v['github']}")
    return " · ".join(teile)


def alerts(now=None, path=None, gh_path=None):
    """While the last update or install was refused because of the local changes (the running version stayed);
    with An GitHub geben the hint after a branch went to GitHub, or why it did not go (waiting says nothing)."""
    if not _an():
        return []
    out = []
    lz = daten(path).get("letzter") or {}
    now = time.time() if now is None else now
    if lz.get("ergebnis") not in (None, "ok", "leer") and now - lz.get("t", 0) <= HINWEIS_S:
        text = entwickeln.GRUENDE.get(lz["ergebnis"], entwickeln.GRUENDE["fehler"])[0]
        out.append({"kind": "entwickeln", "level": "warn", "go": "Einstellungen → Update",
                    "text": f"{ART_TEXT[lz['art']][0]}: {text}" + (f" (rot: {', '.join(lz['rot'][:5])})" if lz.get("rot") else "")
                    + ". Weiter mit sudo speech-spark lokal status."})
    if _github_an():
        g = github_daten(gh_path)
        gl = g.get("letzter") or {}
        if gl.get("zustand") and gl["zustand"] != "wartet" and now - gl.get("t", 0) <= HINWEIS_S:
            if gl["zustand"] == "gegeben" and g["zweige"]:
                out.append({"kind": "entwickeln_github", "level": "info", "go": "Funktionen → Entwickeln auf dem Pi",
                            "text": entwickeln.hinweis(g["zweige"][0]["zweig"], _repo())[0]})
            elif gl["zustand"] != "gegeben":
                out.append({"kind": "entwickeln_github", "level": "warn", "go": "Funktionen → Entwickeln auf dem Pi",
                            "text": "An GitHub geben: " + entwickeln.GH_GRUENDE[gl["zustand"]][0]
                            + ". Weiter mit sudo speech-spark lokal zweige."})
    return out


def _repo():
    """"owner/repo" of the installed version's GitHub remote, "" for a clone from elsewhere."""
    import update
    return update.github_repo(update.installed_version().get("remote")) or ""


router = APIRouter()


@router.get("/api/admin/entwickeln", dependencies=[Depends(auth)])
async def admin_entwickeln(request: Request):
    """The state of the local changes for an admin (counts, short commits, fixed words, red test names)."""
    guard.limit(request, "entwickeln", None, True)
    import update
    return {"an": _an(), **await asyncio.to_thread(daten), "update": await asyncio.to_thread(update.update_running)}


async def _wunsch(request, art):
    guard.limit(request, "entwickeln_einspielen", None, True)
    await core.json_body(request, MAX_BODY, lenient=True)
    if not _an():
        print(f"entwickeln: {art} abgelehnt aus", flush=True)
        raise HTTPException(409, entwickeln.GRUENDE["aus"][0])
    import update
    if await asyncio.to_thread(update.update_running):
        print(f"entwickeln: {art} abgelehnt laeuft", flush=True)
        raise HTTPException(409, "Ein Update läuft schon.")
    with open(entwickeln.WUNSCH, "w") as f:
        f.write(art)
    try:
        out = await asyncio.to_thread(update.begin, "before-update", "")
    except HTTPException:
        try:
            os.remove(entwickeln.WUNSCH)
        except OSError:
            pass
        print(f"entwickeln: {art} abgelehnt start", flush=True)
        raise
    print(f"entwickeln: {art} gestartet", flush=True)
    guard.log("entwickeln_lokal", detail=ART_TEXT[art][0])
    return out


@router.post("/api/admin/entwickeln/einspielen", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_einspielen(request: Request):
    """„Lokal einspielen“: spark-dev's branch, checked and quick-tested by root, installed like an update."""
    return await _wunsch(request, "einspielen")


@router.post("/api/admin/entwickeln/zurueck", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_zurueck(request: Request):
    """Back to what ran before the last local install."""
    return await _wunsch(request, "zurueck")


@router.post("/api/admin/entwickeln/verwerfen", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_verwerfen(request: Request):
    """The installed version without the local commits (they stay in spark-dev's clone)."""
    return await _wunsch(request, "verwerfen")


_tests = {}   # branch -> (time, head, state): GitHub's "Tests" asked at most every TESTS_S


async def _tests_von(repo, zweig, kopf, now=None):
    import update
    now = time.time() if now is None else now
    c = _tests.get(zweig)
    if c and c[1] == kopf and now - c[0] < TESTS_S:
        return c[2]
    try:
        stand = entwickeln.tests_zustand(await update.green_runs(repo, zweig), zweig, kopf)
    except Exception as e:   # GitHub's limit, no internet, a broken answer: "unbekannt", asked again later
        print(f"entwickeln: github tests unbekannt {type(e).__name__}", flush=True)
        stand = "unbekannt"
    _tests[zweig] = (now, kopf, stand)
    return stand


@router.get("/api/admin/entwickeln/github", dependencies=[Depends(auth)])
async def admin_github_stand(request: Request):
    """Weg A for an admin: the branches handed to GitHub with their tests and links, the last state (fixed word),
    whether one waits for the internet, and the fixed hint for Dominik."""
    guard.limit(request, "entwickeln", None, True)
    g = await asyncio.to_thread(github_daten)
    repo = await asyncio.to_thread(_repo)
    zweige = []
    for i, z in enumerate(g["zweige"]):
        tests = await _tests_von(repo, z["zweig"], z["kopf"]) if repo and i < TESTS_ZWEIGE else "unbekannt"
        zweige.append({"zweig": z["zweig"], "kopf": z["kopf"][:7], "anzahl": z["anzahl"], "t": z["t"], "tests": tests,
                       "link": f"https://github.com/{repo}/tree/{z['zweig']}" if repo else ""})
    lz = g.get("letzter")
    return {"an": _github_an(), "zweige": zweige, "wartet": os.path.exists(entwickeln.GH_WUNSCH),
            "letzter": dict(lz, text=entwickeln.GH_GRUENDE[lz["zustand"]]) if lz else None,
            "hinweis": entwickeln.hinweis(zweige[0]["zweig"], repo) if zweige else None}


@router.post("/api/admin/entwickeln/github", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_github(request: Request):
    """„An GitHub geben“: the topic as the wish, then root's oneshot; the branch reaches GitHub only as
    opencode/<thema>, and only root's deploy key pushes it. A fresh code every time: it leaves the house."""
    guard.limit(request, "entwickeln_github", None, True)
    body = await core.json_body(request, MAX_BODY_GH, lenient=True)
    if not _github_an():
        print("entwickeln: github abgelehnt aus", flush=True)
        raise HTTPException(409, entwickeln.GH_GRUENDE["aus"][0])
    thema = entwickeln.thema_pruefen(body.get("thema") or entwickeln.ZWEIG)
    if not thema:
        print("entwickeln: github abgelehnt thema", flush=True)
        raise HTTPException(400, entwickeln.GH_GRUENDE["thema"][0])
    with open(entwickeln.GH_WUNSCH, "w") as f:
        f.write(thema)
    from core import run
    code, _out = await asyncio.to_thread(run, ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", entwickeln.GH_UNIT], timeout=20)
    if code != 0:
        try:
            os.remove(entwickeln.GH_WUNSCH)
        except OSError:
            pass
        print("entwickeln: github abgelehnt start", flush=True)
        raise HTTPException(500, "An GitHub geben konnte nicht starten (sudo ./install.sh --entwickeln einmal neu)")
    zweig = entwickeln.GH_PREFIX + thema
    print("entwickeln: github gestartet", flush=True)
    guard.log("entwickeln_github", detail=zweig)
    return {"gestartet": True, "zweig": zweig, "hinweis": entwickeln.hinweis(zweig, await asyncio.to_thread(_repo))}
