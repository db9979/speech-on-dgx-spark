"""Geräte-Bild: a picture of each computer on its card (Zustand → Überblick → Rechner; Dominik 2026-11-11: „cool,
wenn man ein entsprechendes Bild zum System sehen könnte“, his choice „2 Zeichnung plus eigenes Foto“).

- art(geraet): which of the panel's own drawings fits the device name the computer reports (static/geraete/*.svg:
  the Dell Pro Max with GB10 / DGX Spark, a Raspberry Pi, else a neutral computer). The name is outside text: it is
  only matched against fixed patterns, never shown through this module and never part of a path.
- The admin's own photo per computer ("modell", "panel") replaces the drawing. The page makes it small before it
  sends it; the panel decodes it with Pillow, takes only JPEG, PNG or WebP, makes it at most MAX_PX wide or high and
  stores it again as JPEG without any of the file's extra data (place, camera, time). Nothing is loaded from the
  internet, no manufacturer's photo is part of the Spark.

No switch of its own: it is part of the admin's page Zustand and only shows something there.

    GET    /api/admin/rechner/bild/{k}    the admin's photo (404 without one)
    POST   /api/admin/rechner/bild/{k}    {"bild": "data:image/jpeg;base64,…"} stores it
    DELETE /api/admin/rechner/bild/{k}    the drawing again

State: geraetebild.json in common.STATE (dateien.py). Log: "rechner: bild …" with fixed words and numbers only.
"""
import base64
import io
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import common
import guard
from core import auth, json_body

router = APIRouter()
RECHNER = ("modell", "panel")
PLATZ = "rechner"                                   # the neutral drawing for hardware no pattern knows
ARTEN = (("gb10", re.compile(r"\bGB10\b|DGX Spark|Dell Pro Max", re.I)),
         ("pi", re.compile(r"Raspberry Pi", re.I)))
ZEICHNUNGEN = ("gb10", "pi", PLATZ)                 # static/geraete/<name>.svg, own drawings
MAX_BODY = 2 * 1048576                              # bytes of the request (the page sends well below 1 MB)
MAX_BILD = 1 * 1048576                              # bytes of the picture itself
MAX_PIXEL = 40_000_000                              # width times height before it is decoded
MAX_PX = 640
FORMATE = ("JPEG", "PNG", "WEBP")
DATA = re.compile(r"data:image/(?:jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)")
_lock = threading.Lock()


def _file():
    return os.path.join(common.STATE, "geraetebild.json")


def art(geraet):
    """The drawing for a device name, by fixed patterns only."""
    name = str(geraet or "")[:200]
    return next((a for a, muster in ARTEN if muster.search(name)), PLATZ)


def zeichnung(name):
    """The path of GET /static/geraete/<name> (panel.py): only the drawings of ZEICHNUNGEN."""
    if not name.endswith(".svg") or name[:-4] not in ZEICHNUNGEN:
        raise HTTPException(404, "not found")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "geraete", name)


def _lesen():
    d = common.read_json(_file(), {})
    return d if isinstance(d, dict) else {}


def eigen(k):
    """(JPEG bytes, time) of the admin's photo for this computer, or (None, 0)."""
    x = _lesen().get(k) if k in RECHNER else None
    try:
        return (base64.b64decode(x["jpg"], validate=True), int(x["t"])) if isinstance(x, dict) else (None, 0)
    except (KeyError, ValueError, TypeError):
        return None, 0


def fuer_karte(k, geraet):
    """For the computer's card: {"art": the drawing, "eigen": the time of the admin's photo or 0}."""
    return {"art": art(geraet), "eigen": eigen(k)[1]}


def jpeg(data):
    """The picture as a small JPEG without the file's extra data. ValueError("format") for anything that is not a
    JPEG, PNG or WebP picture, ValueError("gross") above MAX_PIXEL."""
    import warnings
    from PIL import Image
    try:
        # Pillow's own pixel limit is one number for the whole process and other modules set it (images, bilder,
        # documents): above it Pillow warns or raises before the size can be asked. Both mean „gross“ here, whatever
        # that number is (main red 2026-11-11: with a lower limit the answer was „format“).
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                im = Image.open(io.BytesIO(data), formats=FORMATE)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValueError("gross")
        if im.width * im.height > MAX_PIXEL or min(im.size) < 1:
            raise ValueError("gross")
        im.load()
        im = im.convert("RGB")
        im.thumbnail((MAX_PX, MAX_PX))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82, optimize=True)     # a new file: no EXIF, no place, no comment
        return out.getvalue()
    except ValueError:
        raise
    except Exception:   # noqa: BLE001  (whatever Pillow says about a broken file)
        raise ValueError("format")


def setzen(k, data):
    """Stores the admin's photo for this computer; returns its size in bytes."""
    if k not in RECHNER:
        raise ValueError("rechner")
    jpg = jpeg(data)
    with _lock:
        d = _lesen()
        d[k] = {"t": int(time.time()), "jpg": base64.b64encode(jpg).decode()}
        common.write_json(_file(), {x: d[x] for x in RECHNER if x in d}, mode=0o600)
    return len(jpg)


def weg(k):
    with _lock:
        d = _lesen()
        war = d.pop(k, None) is not None
        if war:
            common.write_json(_file(), {x: d[x] for x in RECHNER if x in d}, mode=0o600)
    return war


def _rechner(k):
    if k not in RECHNER:
        raise HTTPException(404, "not found")
    return k


@router.get("/api/admin/rechner/bild/{k}", dependencies=[Depends(auth)])
async def bild_get(k: str, request: Request):
    guard.limit(request, "rechnerbild", admin=True)
    jpg, _ = eigen(_rechner(k))
    if not jpg:
        raise HTTPException(404, "not found")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400",
                                                           "X-Content-Type-Options": "nosniff"})


@router.post("/api/admin/rechner/bild/{k}", dependencies=[Depends(auth)])
async def bild_post(k: str, request: Request):
    guard.limit(request, "rechnerbild_tun", admin=True)
    k = _rechner(k)
    body = await json_body(request, MAX_BODY)
    m = DATA.fullmatch(str(body.get("bild") or ""))
    try:
        if not m:
            raise ValueError("format")
        data = base64.b64decode(m.group(1), validate=False)
        if len(data) > MAX_BILD:
            raise ValueError("gross")
        import asyncio
        n = await asyncio.to_thread(setzen, k, data)
    except ValueError as e:
        why = "gross" if str(e) == "gross" else "format"
        print(f"rechner: bild abgelehnt {why} {k}", flush=True)
        raise HTTPException(400, "Das Bild ist zu groß." if why == "gross" else "Nur ein Foto als JPEG, PNG oder WebP.")
    print(f"rechner: bild gespeichert {k} | {n // 1024} kB", flush=True)
    return {"ok": True, "eigen": eigen(k)[1]}


@router.delete("/api/admin/rechner/bild/{k}", dependencies=[Depends(auth)])
async def bild_delete(k: str, request: Request):
    guard.limit(request, "rechnerbild_tun", admin=True)
    war = weg(_rechner(k))
    print(f"rechner: bild {'geloescht' if war else 'keins'} {k}", flush=True)
    return {"ok": True, "war": war}
