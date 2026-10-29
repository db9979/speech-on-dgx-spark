"""Ordner im Fernzugang (Dominik 2026-10-29 09:18 „A“, Bild ssh-vermittlung/ordner): the paired systems in folders.

- One level of folders, each with a free name and a symbol (an emoji), in an order of their own; a system is in one
  folder or in „Ohne Ordner“. Folders only order the list: rights, unlock and every door stay per system.
- The page shows each folder collapsible with „● online / gesamt“; drag & drop orders folders and systems, „⋯ →
  Verschieben nach …“ (long press on the phone) moves one system. A click on a folder shows its overview: rename,
  symbol, delete (its systems go to „Ohne Ordner“), „Alle aktualisieren“. „Koppeln“ can name the folder the new
  system lands in (held with the one-time code's hash until the anchor pairs, at most CODE_S).
- Stored in STATE/fernordner.json (mode 0600): {ordner: [{id, name, symbol}], systeme: {gid: oid}, reihe: [gid …]}.
- Admins only, behind the page's unlock (fernzugang._frei), in the own iPhone app of an admin too.
- Logs: „fernzugang: ordner | <word> | <number>“; Live: how many folders; never a folder name.

    POST   /api/admin/fernzugang/ordner {name, symbol}               -> {id}
    PUT    /api/admin/fernzugang/ordner/{oid} {name?, symbol?}       -> {ok}
    DELETE /api/admin/fernzugang/ordner/{oid}                        -> {ok, systeme}  (they go to „Ohne Ordner“)
    PUT    /api/admin/fernzugang/ordnung {ordner: [oid …], systeme: [[gid, oid or ""] …]}   (drag & drop) -> {ok}
    POST   /api/admin/fernzugang/geraete/{gid}/ordner {ordner: oid or ""}                   („Verschieben nach“) -> {ok}
"""
import hashlib
import os
import re
import secrets
import threading
import time
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import fernzugang
import guard
from common import STATE, read_json, write_json
from core import auth, json_body

router = APIRouter()

FILE = os.path.join(STATE, "fernordner.json")
MAX_ORDNER = 30             # folders at most
NAME_MAX = 40               # characters of a folder's name
SYMBOL_MAX = 8              # characters of its symbol (one emoji, maybe with a joiner)
SYMBOL = "📁"               # the symbol of a new folder without one
MAX_BODY = 16 * 1024        # the JSON body of an order (ids only)
OID = re.compile(r"o_[0-9a-f]{8}")
_lock = threading.Lock()
_KOPPELN = {}               # sha256 of a pairing code -> (oid, time): the folder a new system lands in


def on(c=None):
    """Folders are a part of the Fernzugang with a switch of their own (off by default)."""
    c = c if c is not None else features.chat_cfg()
    return fernzugang.admin_on(c) and features.admin_on("fernordner", c)


def _read():
    d = read_json(FILE, {})
    if not isinstance(d, dict):
        d = {}
    ordner = [o for o in d.get("ordner", []) if isinstance(o, dict) and OID.fullmatch(str(o.get("id")))]
    ids = {o["id"] for o in ordner}
    systeme = d.get("systeme") if isinstance(d.get("systeme"), dict) else {}
    return {"ordner": ordner, "systeme": {g: o for g, o in systeme.items() if o in ids},
            "reihe": [g for g in d.get("reihe", []) if isinstance(g, str)]}


def _write(d):
    write_json(FILE, d, mode=0o600)


def _name(v):
    """A folder's name: printable text, no line break or markup sign, 1 to NAME_MAX characters (None otherwise)."""
    if not isinstance(v, str):
        return None
    v = unicodedata.normalize("NFC", v).strip()
    if not 1 <= len(v) <= NAME_MAX or any(unicodedata.category(ch)[0] == "C" or ch in "<>" for ch in v):
        return None
    return v


def _symbol(v):
    """A folder's symbol: an emoji or another sign that is no letter, digit or markup (SYMBOL when empty)."""
    if v in (None, ""):
        return SYMBOL
    if not isinstance(v, str) or len(v) > SYMBOL_MAX:
        return None
    if any(ord(ch) < 0x2000 or unicodedata.category(ch)[0] in "LNC" and ch != "‍" for ch in v):
        return None
    return v


def anzahl():
    return len(_read()["ordner"])


def view(gids):
    """What the page gets: the folders in their order and, for the systems that exist, their folder and order."""
    d = _read()
    gids = list(gids)
    known = set(gids)
    reihe = [g for g in d["reihe"] if g in known]
    reihe += [g for g in gids if g not in set(reihe)]
    return {"ordner": [{"id": o["id"], "name": o.get("name", ""), "symbol": o.get("symbol") or SYMBOL} for o in d["ordner"]],
            "systeme": {g: o for g, o in d["systeme"].items() if g in known}, "reihe": reihe}


def forget(gid):
    """The system is removed: it leaves its folder."""
    with _lock:
        d = _read()
        if gid in d["systeme"] or gid in d["reihe"]:
            d["systeme"].pop(gid, None)
            d["reihe"] = [g for g in d["reihe"] if g != gid]
            _write(d)


def _hash(code):
    return hashlib.sha256(str(code).encode()).hexdigest()


def vormerken(code, oid):
    """„Koppeln“ with a folder: held with the code's hash until the anchor pairs (at most CODE_S)."""
    now = time.time()
    with _lock:
        for k, (_, t) in list(_KOPPELN.items()):
            if now - t > fernzugang.CODE_S:
                _KOPPELN.pop(k, None)
        if oid and any(o["id"] == oid for o in _read()["ordner"]):
            _KOPPELN[_hash(code)] = (oid, now)
            return True
    return False


def nach_koppeln(code, gid):
    """The anchor paired with that code: the new system goes into the folder named at „Koppeln“ (if it still exists)."""
    with _lock:
        x = _KOPPELN.pop(_hash(code), None)
        if not x or time.time() - x[1] > fernzugang.CODE_S:
            return
        d = _read()
        if any(o["id"] == x[0] for o in d["ordner"]):
            d["systeme"][gid] = x[0]
            _write(d)
            fernzugang.log("ordner", "koppeln", 1)


def _gate(request):
    """Folders on, an admin in the browser (the page unlocked) or in the own app, no Notaus."""
    if not on():
        fernzugang.log("ordner", "aus", 0)
        raise HTTPException(404, "Ordner sind aus (Funktionen → Fernzugang zu Servern → Ordner im Fernzugang)")
    fernzugang._admin_here(request)
    if fernzugang._notaus(count=True):
        fernzugang.log("ordner", "notaus", 0)
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")
    fernzugang._frei(request)
    guard.limit(request, "fernzugang_ordner", admin=True)


def _oid(oid, d):
    if not OID.fullmatch(str(oid)) or not any(o["id"] == oid for o in d["ordner"]):
        fernzugang.log("ordner", "unbekannt", 0)
        raise HTTPException(404, "no such folder")


def _invalid(what):
    fernzugang.log("ordner", "ungueltig", 0)
    raise HTTPException(400, what)


# ---------------------------------------------------------------- doors
@router.post("/api/admin/fernzugang/ordner", dependencies=[Depends(auth)])
async def new_folder(request: Request):
    _gate(request)
    body = await json_body(request, MAX_BODY)
    name, symbol = _name(body.get("name")), _symbol(body.get("symbol"))
    if name is None or symbol is None:
        _invalid(f"name: 1 to {NAME_MAX} characters, symbol: one emoji")
    with _lock:
        d = _read()
        if len(d["ordner"]) >= MAX_ORDNER:
            fernzugang.log("ordner", "voll", 0)
            raise HTTPException(409, f"Höchstens {MAX_ORDNER} Ordner.")
        oid = "o_" + secrets.token_hex(4)
        d["ordner"].append({"id": oid, "name": name, "symbol": symbol})
        _write(d)
    fernzugang.log("ordner", "neu", 1)
    fernzugang._live("Fernzugang: Ordner angelegt")
    return {"id": oid}


@router.put("/api/admin/fernzugang/ordner/{oid}", dependencies=[Depends(auth)])
async def change_folder(oid: str, request: Request):
    _gate(request)
    body = await json_body(request, MAX_BODY)
    with _lock:
        d = _read()
        _oid(oid, d)
        o = next(o for o in d["ordner"] if o["id"] == oid)
        if "name" in body:
            name = _name(body.get("name"))
            if name is None:
                _invalid(f"name: 1 to {NAME_MAX} characters")
            o["name"] = name
        if "symbol" in body:
            symbol = _symbol(body.get("symbol"))
            if symbol is None:
                _invalid("symbol: one emoji")
            o["symbol"] = symbol
        _write(d)
    fernzugang.log("ordner", "geaendert", 1)
    return {"ok": True}


@router.delete("/api/admin/fernzugang/ordner/{oid}", dependencies=[Depends(auth)])
def delete_folder(oid: str, request: Request):
    _gate(request)
    with _lock:
        d = _read()
        _oid(oid, d)
        d["ordner"] = [o for o in d["ordner"] if o["id"] != oid]
        frei = [g for g, o in d["systeme"].items() if o == oid]
        for g in frei:
            d["systeme"].pop(g, None)
        _write(d)
    fernzugang.log("ordner", "geloescht", 1)
    if frei:
        fernzugang.log("ordner", "ohne ordner", len(frei))
    fernzugang._live("Fernzugang: Ordner gelöscht")
    return {"ok": True, "systeme": len(frei)}


@router.put("/api/admin/fernzugang/ordnung", dependencies=[Depends(auth)])
async def put_order(request: Request):
    """Drag & drop: the whole order at once, folders and systems (with each system's folder)."""
    _gate(request)
    body = await json_body(request, MAX_BODY)
    ordner, systeme = body.get("ordner"), body.get("systeme")
    if not isinstance(ordner, list) or not isinstance(systeme, list) or len(systeme) > fernzugang.MAX_ANKER * 2:
        _invalid("ordner: a list of ids, systeme: a list of [id, folder]")
    known = fernzugang._read()["geraete"]
    with _lock:
        d = _read()
        ids = [o["id"] for o in d["ordner"]]
        if sorted(ordner) != sorted(ids):
            _invalid("ordner: every folder once")
        pairs = []
        for p in systeme:
            if (not isinstance(p, list) or len(p) != 2 or p[0] not in known or not isinstance(p[1], str)
                    or (p[1] and p[1] not in ids)):
                _invalid("systeme: [id, folder] of paired systems")
            pairs.append((p[0], p[1]))
        if len({g for g, _ in pairs}) != len(pairs):
            _invalid("systeme: every system once")
        d["ordner"] = sorted(d["ordner"], key=lambda o: ordner.index(o["id"]))
        for g, o in pairs:
            if o:
                d["systeme"][g] = o
            else:
                d["systeme"].pop(g, None)
        seen = [g for g, _ in pairs]
        d["reihe"] = seen + [g for g in d["reihe"] if g not in set(seen) and g in known]
        _write(d)
    fernzugang.log("ordner", "reihenfolge", len(pairs))
    return {"ok": True}


@router.post("/api/admin/fernzugang/geraete/{gid}/ordner", dependencies=[Depends(auth)])
async def move_system(gid: str, request: Request):
    """„Verschieben nach …“: one system into a folder ("" = „Ohne Ordner“), at that folder's end."""
    _gate(request)
    if not fernzugang.GID.fullmatch(str(gid)) or gid not in fernzugang._read()["geraete"]:
        fernzugang.log("ordner", "unbekannt", 0)
        raise HTTPException(404, "no such system")
    body = await json_body(request, MAX_BODY)
    oid = body.get("ordner")
    if not isinstance(oid, str):
        _invalid("ordner: a folder id or \"\"")
    with _lock:
        d = _read()
        if oid:
            _oid(oid, d)
            d["systeme"][gid] = oid
        else:
            d["systeme"].pop(gid, None)
        d["reihe"] = [g for g in d["reihe"] if g != gid] + [gid]
        _write(d)
    fernzugang.log("ordner", "verschoben", 1)
    return {"ok": True}
