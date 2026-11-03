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
HINWEIS_S = 3 * 86400    # a refused update or install stays on top of the admin pages this long (or until the next ok)
ART_TEXT = {"einspielen": ("Lokal einspielen", "Install local changes"), "zurueck": ("Lokal zurück", "Local back"),
            "verwerfen": ("Lokal verwerfen", "Drop local changes"), "aufsetzen": ("Update mit lokalen Änderungen", "Update with local changes")}


def _an(cfg=None):
    """Funktionen → Entwickeln auf dem Pi (cfg: the whole configuration, None reads it)."""
    return features.admin_on("entwickeln", None if cfg is None else cfg.get("chat", {}))


def daten(path=None):
    """What root last wrote (entwickeln.anzeige_lesen: checked again here)."""
    return entwickeln.anzeige_lesen(path)


def for_live(path=None):
    """Zustand → Live, box „Entwickeln“: counts and fixed words only, never a commit text, a path or a test output."""
    if not _an():
        return {"on": False}
    d = daten(path)
    return {"on": True, "anzahl": d.get("anzahl", 0), "offen": d.get("offen"),
            "letzter": (d.get("letzter") or {}).get("ergebnis"), "art": (d.get("letzter") or {}).get("art")}


def live_sub(v):
    teile = [f"lokale Änderungen: {v.get('anzahl', 0)}"]
    if v.get("offen"):
        teile.append(f"{v['offen']} im Klon noch nicht eingespielt")
    if v.get("letzter") and v["letzter"] != "ok" and v.get("art") in ART_TEXT:
        teile.append(f"zuletzt {ART_TEXT[v['art']][0]} abgelehnt: {v['letzter']}")
    return " · ".join(teile)


def alerts(now=None, path=None):
    """While the last update or install was refused because of the local changes (the running version stayed)."""
    if not _an():
        return []
    lz = daten(path).get("letzter") or {}
    now = time.time() if now is None else now
    if lz.get("ergebnis") in (None, "ok", "leer") or now - lz.get("t", 0) > HINWEIS_S:
        return []
    text = entwickeln.GRUENDE.get(lz["ergebnis"], entwickeln.GRUENDE["fehler"])[0]
    return [{"kind": "entwickeln", "level": "warn", "go": "Einstellungen → Update",
             "text": f"{ART_TEXT[lz['art']][0]}: {text}" + (f" (rot: {', '.join(lz['rot'][:5])})" if lz.get("rot") else "")
             + ". Weiter mit sudo speech-spark lokal status."}]


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
