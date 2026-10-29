"""Notizen je System im Fernzugang (Dominik 2026-10-29 08:57 „Empfehlung umsetzen“, Bilder ssh-vermittlung/notizen):
one note per paired system, written by the admin, for the admin.

- Where: the box „Notizen“ in the detail of a system (under „Angaben“) and the tab „Notizen“ beside „Assistent“ in the
  terminal's column, also in full screen. Light markup only (# heading, - list, **bold**, ``` code ```); every code
  block has „Ins Terminal“: the page opens the shell when it is closed and puts the command in the line, Enter stays
  with the person. The page saves while typing („✓ gespeichert“).
- Stored sealed (vault.seal) in STATE/fernnotizen.json, admins only, behind the page's unlock (fernzugang._frei); the
  own iPhone app of an admin may read and write it like the rest of its doors (fernzugang.is_admin_app), also only
  unlocked. At most MAX_BYTES per note. The last FASSUNGEN versions are kept: a new version starts when the last save is FASSUNG_S old
  (one typed run is one version), „Wiederherstellen“ puts an old one back and keeps the current one as a version.
- „Assistent darf lesen“ (per note, on by default): the note goes to the own language model as data inside the
  material block of the assistant beside the terminal (fernzugang._material, at most MODELL_ZEICHEN characters), never
  to anything else; off, the model never sees it.
- Fixed rules, never the model, look for something that belongs in the vault (warnungen: password lines, private keys,
  tokens of known services): the page shows „gehört in den Tresor“ with the line and „Entfernen“.
- Search on the left finds note text too (a short snippet around the hit, only for this admin's page).
- „Entfernen“ of a system offers to download the note first, then the note goes with the system (forget).
- Logs: „fernzugang: notiz | <word> | <number>“, Live: how many systems have a note; never a word of a note.

    GET    /api/admin/fernzugang/notiz/{gid}                       -> {text, lesen, t, fassungen: [{t, zeichen}], warnungen}
    PUT    /api/admin/fernzugang/notiz/{gid} {text, lesen}         -> {t, warnungen, fassungen}
    POST   /api/admin/fernzugang/notiz/{gid}/wiederherstellen {t}  -> the note as GET
    DELETE /api/admin/fernzugang/notiz/{gid}                       -> {ok}
    GET    /api/admin/fernzugang/notiz/{gid}/laden                 -> the note as a text file (Markdown)
    GET    /api/admin/fernzugang/notizen/suche?q=…                 -> {treffer: {gid: snippet}}
"""
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import features
import fernzugang
import guard
import vault
from common import STATE, read_json, write_json
from core import auth, json_body

router = APIRouter()

FILE = os.path.join(STATE, "fernnotizen.json")
MAX_BYTES = 64 * 1024       # one note at most (UTF-8)
MAX_BODY = 80 * 1024        # the JSON body of a save (the note, escaped)
FASSUNGEN = 10              # versions kept besides the current one
FASSUNG_S = 600             # a save after this long since the last one starts a new version
MODELL_ZEICHEN = 8000       # characters of the note the assistant gets at most
SUCHE = (2, 100)            # characters of a search
SCHNIPSEL = 40              # characters on each side of a hit
_lock = threading.Lock()

# what belongs in the vault, not in a note: fixed rules (Dominik: „gehört in den Tresor“), never the model
GEHEIM = (
    ("passwort", re.compile(r"(?i)\b(pass(wort|word|wd)?|pw|kennwort|pin)\b\s*[:=]\s*\S{3,}")),
    ("schluessel", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token", re.compile(r"\b(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|glpat-[A-Za-z0-9_\-]{20,}|xox[abprs]-[A-Za-z0-9\-]{10,}"
                         r"|sk-[A-Za-z0-9_\-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,})\b")),
    ("token", re.compile(r"(?i)\b(api[_-]?key|token|secret|geheimnis)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-+/=.]{12,}")),
)


def on(c=None):
    """Notes are a part of the Fernzugang with a switch of their own (off by default)."""
    c = c if c is not None else features.chat_cfg()
    return fernzugang.admin_on(c) and features.admin_on("fernnotizen", c)


def _read():
    d = read_json(FILE, {})
    if not isinstance(d, dict) or not isinstance(d.get("notizen"), dict):
        d = {"notizen": {}}
    return d


def _write(d):
    write_json(FILE, d, mode=0o600)


def _open(sealed):
    try:
        return vault.open_(sealed) if isinstance(sealed, str) and sealed else ""
    except (ValueError, TypeError):
        return ""


def _seal(text):
    s = vault.seal(text)
    if not str(s).startswith(vault.PREFIX):       # never a note in plain text on the disk
        fernzugang.log("notiz", "tresor fehlt", 0)
        raise HTTPException(503, "Der Tresor ist nicht bereit.")
    return s


def has(gid):
    x = _read()["notizen"].get(gid)
    return bool(isinstance(x, dict) and x.get("text"))


def anzahl():
    return sum(1 for x in _read()["notizen"].values() if isinstance(x, dict) and x.get("text"))


def warnungen(text):
    """[{zeile, art}] for every line that looks like a secret (the first rule that fits)."""
    out = []
    for i, line in enumerate(str(text or "").splitlines(), 1):
        for art, rx in GEHEIM:
            if rx.search(line):
                out.append({"zeile": i, "art": art})
                break
    return out[:20]


def fuer_modell(gid, c=None):
    """The note for the assistant, only when notes are on and „Assistent darf lesen“ is set ("" otherwise)."""
    if not on(c):
        return ""
    x = _read()["notizen"].get(gid)
    if not isinstance(x, dict) or not x.get("lesen", True):
        return ""
    return _open(x.get("text"))[:MODELL_ZEICHEN]


def forget(gid):
    """The system is removed: its note goes with it."""
    with _lock:
        d = _read()
        if d["notizen"].pop(gid, None) is not None:
            _write(d)
            fernzugang.log("notiz", "mit system geloescht", 1)


def _view(x):
    text = _open(x.get("text"))
    return {"text": text, "lesen": bool(x.get("lesen", True)), "t": x.get("t"),
            "fassungen": [{"t": f.get("t"), "zeichen": len(_open(f.get("text")))} for f in x.get("fassungen", [])],
            "warnungen": warnungen(text)}


def _gate(request, gid):
    """Notes on, an admin in the browser (the page unlocked) or in the own app, no Notaus, a paired system."""
    if not on():
        fernzugang.log("notiz", "aus", 0)
        raise HTTPException(404, "Notizen sind aus (Funktionen → Fernzugang zu Servern → Notizen im Fernzugang)")
    fernzugang._admin_here(request)
    if fernzugang._notaus(count=True):
        fernzugang.log("notiz", "notaus", 0)
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")
    fernzugang._frei(request)
    guard.limit(request, "fernzugang_notiz", admin=True)
    if gid is not None and (not fernzugang.GID.fullmatch(str(gid)) or gid not in fernzugang._read()["geraete"]):
        fernzugang.log("notiz", "unbekannt", 0)
        raise HTTPException(404, "no such system")


# ---------------------------------------------------------------- doors
@router.get("/api/admin/fernzugang/notiz/{gid}", dependencies=[Depends(auth)])
def get_note(gid: str, request: Request):
    _gate(request, gid)
    x = _read()["notizen"].get(gid)
    fernzugang.log("notiz", "gelesen", 1 if x else 0)
    return _view(x) if isinstance(x, dict) else {"text": "", "lesen": True, "t": None, "fassungen": [], "warnungen": []}


@router.put("/api/admin/fernzugang/notiz/{gid}", dependencies=[Depends(auth)])
async def put_note(gid: str, request: Request):
    _gate(request, gid)
    body = await json_body(request, MAX_BODY)
    text, lesen = body.get("text"), body.get("lesen", True)
    if not isinstance(text, str) or not isinstance(lesen, bool):
        fernzugang.log("notiz", "ungueltig", 0)
        raise HTTPException(400, "text: a string, lesen: true or false")
    text = text.replace("\r\n", "\n").replace("\x00", "")
    if len(text.encode("utf-8")) > MAX_BYTES:
        fernzugang.log("notiz", "zu gross", 0)
        raise HTTPException(413, f"Eine Notiz hat höchstens {MAX_BYTES // 1024} KB.")
    now = int(time.time())
    with _lock:
        d = _read()
        x = d["notizen"].get(gid) if isinstance(d["notizen"].get(gid), dict) else {}
        alt = _open(x.get("text"))
        fassungen = list(x.get("fassungen", []))
        if alt and alt != text and now - int(x.get("t") or 0) >= FASSUNG_S:   # a new typed run: the old one stays a version
            fassungen.insert(0, {"t": int(x.get("t") or now), "text": x.get("text")})
        if not text.strip() and not fassungen:
            d["notizen"].pop(gid, None)
        else:
            d["notizen"][gid] = {"text": _seal(text) if text else "", "lesen": lesen, "t": now, "fassungen": fassungen[:FASSUNGEN]}
        _write(d)
        out = _view(d["notizen"][gid]) if gid in d["notizen"] else {"t": None, "fassungen": [], "warnungen": []}
    fernzugang.log("notiz", "gespeichert" if text.strip() else "leer", 1)
    if out["warnungen"]:
        fernzugang.log("notiz", "tresor hinweis", len(out["warnungen"]))
    return {"t": out["t"], "fassungen": out["fassungen"], "warnungen": out["warnungen"]}


@router.post("/api/admin/fernzugang/notiz/{gid}/wiederherstellen", dependencies=[Depends(auth)])
async def restore_note(gid: str, request: Request):
    _gate(request, gid)
    body = await json_body(request, 256)
    want = body.get("t")
    now = int(time.time())
    with _lock:
        d = _read()
        x = d["notizen"].get(gid)
        fassungen = list(x.get("fassungen", [])) if isinstance(x, dict) else []
        hit = next((f for f in fassungen if isinstance(want, int) and f.get("t") == want), None)
        if hit is None:
            fernzugang.log("notiz", "fassung fehlt", 0)
            raise HTTPException(404, "no such version")
        fassungen.remove(hit)
        if x.get("text"):
            fassungen.insert(0, {"t": int(x.get("t") or now), "text": x["text"]})
        d["notizen"][gid] = {"text": hit["text"], "lesen": bool(x.get("lesen", True)), "t": now, "fassungen": fassungen[:FASSUNGEN]}
        _write(d)
        out = _view(d["notizen"][gid])
    fernzugang.log("notiz", "wiederhergestellt", 1)
    return out


@router.delete("/api/admin/fernzugang/notiz/{gid}", dependencies=[Depends(auth)])
def delete_note(gid: str, request: Request):
    _gate(request, gid)
    with _lock:
        d = _read()
        gone = d["notizen"].pop(gid, None) is not None
        if gone:
            _write(d)
    fernzugang.log("notiz", "geloescht", 1 if gone else 0)
    return {"ok": True}


@router.get("/api/admin/fernzugang/notiz/{gid}/laden", dependencies=[Depends(auth)])
def download_note(gid: str, request: Request):
    """The note as a file before „Entfernen“ (or any time): Markdown, named after the system (letters and digits)."""
    _gate(request, gid)
    x = _read()["notizen"].get(gid)
    text = _open(x.get("text")) if isinstance(x, dict) else ""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(fernzugang._read()["geraete"][gid].get("name") or "system")).strip("-.")[:40] or "system"
    fernzugang.log("notiz", "heruntergeladen", 1 if text else 0)
    return Response(text, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="notiz-{name}.md"', "Cache-Control": "no-store"})


@router.get("/api/admin/fernzugang/notizen/suche", dependencies=[Depends(auth)])
def search_notes(request: Request, q: str = ""):
    """„Systeme suchen“ also finds note text: per system a short snippet around the first hit."""
    _gate(request, None)
    q = " ".join(str(q).split())
    if not SUCHE[0] <= len(q) <= SUCHE[1]:
        fernzugang.log("notiz", "suche ungueltig", 0)
        raise HTTPException(400, f"q: {SUCHE[0]} to {SUCHE[1]} characters")
    out, low = {}, q.lower()
    for gid, x in _read()["notizen"].items():
        text = _open(x.get("text")) if isinstance(x, dict) else ""
        i = text.lower().find(low)
        if i < 0:
            continue
        a, b = max(0, i - SCHNIPSEL), min(len(text), i + len(q) + SCHNIPSEL)
        out[gid] = {"vor": ("…" if a else "") + " ".join(text[a:i].split()), "treffer": text[i:i + len(q)],
                    "nach": " ".join(text[i + len(q):b].split()) + ("…" if b < len(text) else "")}
    fernzugang.log("notiz", "suche", len(out))
    return {"treffer": out}
