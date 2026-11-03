"""Fernzugang, Dateien als anderer Benutzer (plan ssh-vermittlung/dateien-als-benutzer.md, Dominik 2026-11-03 „1“):
„Dateien“ of a paired server as root or another named user instead of `spark`, or (Windows) in folders given free.

Two consents, both needed (the panel's key alone never becomes root on a server):
- on the server, by a person as root: `sudo spark-anker dateien als root,anna [--schreiben]` (Linux, macOS) writes the
  drop-in /etc/sudoers.d/spark-anker (only the one sftp-server with exactly `-R`, with `--schreiben` also without
  arguments; checked with visudo -cf before it counts), or as Administrator `spark-anker dateien ordner "C:\\…"
  [--schreiben]` (Windows: icacls for spark on exactly these folders, never a system folder or a whole drive), and
  reports it here (POST /api/fernzugang/anker/dateien); `dateien aus` and „Entfernen“ take it away again;
- here, per system, the admin's switch „Dateien als anderer Benutzer“ (with a fresh code or passkey), under the admin
  switch chat.fernals (Funktionen → Fernzugang zu Servern → Dateien als anderer Benutzer, off).

Then „Dateien“ may pick a user from the server's own list: the panel opens an exec channel `sudo -n -u <user>
<sftp-server> -R` (never asks for a password; a missing rule fails at once), read only. Writing needs its own step:
the server said `--schreiben`, and every writing session asks a fresh code or passkey; `-R` makes the server refuse
any write by itself either way. Names and paths come only from the anchor's report, checked here (USER, SFTP, ORDNER),
never typed in the browser. Logs: „fernzugang: dateien_als | root|anderer|ordner | n“, fixed words, never a user name
or a path; Live counts file sessions as another user only.

    anchor (Bearer key):
    POST   /api/fernzugang/anker/dateien {art: sudo|ordner, benutzer[], schreiben, sftp | ordner[]}
    DELETE /api/fernzugang/anker/dateien
    admin in the browser or the app (core.auth):
    POST   /api/admin/fernzugang/geraete/{gid}/als        switch on for this system (fresh code or passkey)
    (opening: POST /api/admin/fernzugang/dateien {als} read only, …/dateien/schreiben {als} with a fresh code, ferndateien)
    DELETE /api/admin/fernzugang/geraete/{gid}/als        switch off
"""
import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import fernzugang
import guard
from core import admin_code_fresh, auth, json_body

router = APIRouter()

USER = re.compile(r"[a-z_][a-z0-9_.\-]{0,31}")
NOT_USERS = ("spark", "spark-anker", "_sparkanker")     # spark is what „Dateien“ is anyway
SFTP = re.compile(r"/(?:[A-Za-z0-9_.\-]+/){1,6}sftp-server")
ORDNER = re.compile(r"[A-Za-z]:/(?:[^\x00-\x1f<>:\"|?*/\\]{1,255}/){0,30}[^\x00-\x1f<>:\"|?*/\\]{1,255}")
MAX_USERS = 8
MAX_ORDNER = 8
ARTEN = ("sudo", "ordner")


def on(c=None):
    return features.admin_on("fernals", c) and fernzugang.admin_on(c)


def clean(body):
    """The anchor's report as stored here, or None when anything in it is not what the anchor writes."""
    art = body.get("art")
    if art not in ARTEN or not isinstance(body.get("schreiben", False), bool):
        return None
    out = {"art": art, "schreiben": bool(body.get("schreiben"))}
    if art == "sudo":
        users, sftp = body.get("benutzer"), body.get("sftp")
        if not isinstance(users, list) or not 1 <= len(users) <= MAX_USERS or len(set(users)) != len(users):
            return None
        if not all(isinstance(u, str) and USER.fullmatch(u) and u not in NOT_USERS for u in users):
            return None
        if not isinstance(sftp, str) or not SFTP.fullmatch(sftp) or "/../" in sftp or "/./" in sftp:
            return None
        out.update(benutzer=users, sftp=sftp)
    else:
        dirs = body.get("ordner")
        if not isinstance(dirs, list) or not 1 <= len(dirs) <= MAX_ORDNER or len(set(dirs)) != len(dirs):
            return None
        if not all(isinstance(p, str) and ORDNER.fullmatch(p) and ".." not in p.split("/") for p in dirs):
            return None
        out["ordner"] = dirs
    return out


def row(x):
    """What the list of systems shows (only when the switch is on): the server's report and this system's switch."""
    a = x.get("als")
    if not isinstance(a, dict):
        return {"als": None, "als_frei": False}
    return {"als": {k: a[k] for k in ("art", "benutzer", "schreiben", "ordner") if k in a}, "als_frei": bool(x.get("als_frei"))}


def word(user):
    """The fixed word a log line gets for a user: never the name."""
    return "root" if user == "root" else "anderer"


def choose(g, user, write):
    """„Dateien“ as `user` (``""``: as spark): (command for the exec channel or "", writing allowed) or HTTPException.
    Only when the switch is on, this system's switch is on, the server reported this user, and writing only when the
    server allowed it (the fresh code is the caller's)."""
    if not user or user == "spark":
        if write:
            raise HTTPException(400, "Schreiben als spark braucht keinen eigenen Schritt.")
        return "", False
    a = g.get("als") if isinstance(g.get("als"), dict) else None
    if not on():
        fernzugang.log("dateien_als", "aus", 0)
        raise HTTPException(404, "Dateien als anderer Benutzer ist aus (Funktionen → Fernzugang zu Servern → Dateien als anderer Benutzer).")
    if not a or a.get("art") != "sudo" or user not in (a.get("benutzer") or ()):
        fernzugang.log("dateien_als", "nicht gemeldet", 0)
        raise HTTPException(403, "Auf dem Server nicht freigegeben (dort: sudo spark-anker dateien als …).")
    if not g.get("als_frei"):
        fernzugang.log("dateien_als", "schalter", 0)
        raise HTTPException(403, "Für dieses System nicht eingeschaltet (im Fernzugang beim System, Kasten „Dateien als anderer Benutzer“).")
    if write and not a.get("schreiben"):
        fernzugang.log("dateien_als", "nur lesen", 0)
        raise HTTPException(403, "Der Server erlaubt nur Lesen (dort: sudo spark-anker dateien als … --schreiben).")
    if not USER.fullmatch(user) or not SFTP.fullmatch(str(a.get("sftp") or "")):
        raise HTTPException(400, "bad user")
    return f"sudo -n -u {user} {a['sftp']}" + ("" if write else " -R"), bool(write)


# ---------------------------------------------------------------- the anchor
def _anchor(request):
    if not fernzugang.admin_on():
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_koppeln")
    gid, _x = fernzugang.by_key(fernzugang._bearer(request))
    if not gid:
        guard.failed(request, "fernzugang-anker", what="fernzugang_anker")
        fernzugang.log("dateien_als", "schluessel", 0)
        raise HTTPException(403, "unknown key")
    return gid


@router.post("/api/fernzugang/anker/dateien")
async def anchor_report(request: Request):
    """`dateien als …` / `dateien ordner …` on the server: what it set up. A new report switches this system's own
    switch off again (the admin looks at what changed and switches it on with a fresh code)."""
    gid = _anchor(request)
    body = await json_body(request, fernzugang.MAX_BODY)
    a = clean(body)
    if a is None:
        fernzugang.log("dateien_als", "meldung falsch", 0)
        raise HTTPException(400, "bad report")
    await asyncio.to_thread(fernzugang._update, gid, als=a, als_frei=False)
    fernzugang.log("dateien_als", "gemeldet " + a["art"], len(a.get("benutzer") or a.get("ordner") or ()))
    fernzugang._live("Fern-Dateien als anderer Benutzer gemeldet")
    return {}


@router.delete("/api/fernzugang/anker/dateien")
async def anchor_off(request: Request):
    gid = _anchor(request)
    await asyncio.to_thread(fernzugang._update, gid, als=None, als_frei=False)
    fernzugang.log("dateien_als", "abgebaut", 1)
    fernzugang._live("Fern-Dateien als anderer Benutzer abgebaut")
    return {}


# ---------------------------------------------------------------- the admin's switch per system
def _admin(request, gid):
    if not on():
        raise HTTPException(404, "Dateien als anderer Benutzer ist aus (Funktionen → Fernzugang zu Servern → Dateien als anderer Benutzer).")
    fernzugang._admin_here(request)
    fernzugang._frei(request)
    fernzugang._second_step(request)
    if fernzugang._notaus(count=True):
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")
    guard.limit(request, "fernzugang", admin=True)
    if not fernzugang.GID.fullmatch(gid):
        raise HTTPException(400, "no such system")


def _set(gid, value):
    with fernzugang._lock:
        d = fernzugang._read()
        x = d["geraete"].get(gid)
        if not x or x.get("stand") == "abbau":
            return None
        if value and not isinstance(x.get("als"), dict):
            return False
        x["als_frei"] = value
        fernzugang._write(d)
        return True


@router.post("/api/admin/fernzugang/geraete/{gid}/als", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_on_for(gid: str, request: Request):
    _admin(request, gid)
    ok = await asyncio.to_thread(_set, gid, True)
    if ok is None:
        fernzugang.log("dateien_als", "unbekannt", 0)
        raise HTTPException(404, "no such system")
    if ok is False:
        fernzugang.log("dateien_als", "nicht gemeldet", 0)
        raise HTTPException(409, "Der Server hat noch nichts freigegeben (dort: sudo spark-anker dateien als …).")
    fernzugang.log("dateien_als", "an", 1)
    guard.log("fernzugang_als", detail="Fern-Dateien als anderer Benutzer an")
    fernzugang._live("Fern-Dateien als anderer Benutzer an")
    return {"als_frei": True}


@router.delete("/api/admin/fernzugang/geraete/{gid}/als", dependencies=[Depends(auth)])
async def admin_off_for(gid: str, request: Request):
    _admin(request, gid)
    ok = await asyncio.to_thread(_set, gid, False)
    if ok is None:
        fernzugang.log("dateien_als", "unbekannt", 0)
        raise HTTPException(404, "no such system")
    fernzugang.log("dateien_als", "aus", 1)
    fernzugang._live("Fern-Dateien als anderer Benutzer aus")
    return {"als_frei": False}
