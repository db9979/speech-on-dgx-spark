"""Musik machen, stage M0: measuring (plan plaene/musik.md, Dominik 2026-10-16 „1a 2a 3a 4a 5a“). ACE-Step 1.5 runs
on the model computer (musik_server.py, music.port 31004, installed with `install.sh --musik 2b`); this stage only
lets the admin measure it before anything else is built: „Musik testen“ makes two fixed songs one after the other,
a short instrumental piece and a short song with German lyrics, and keeps the numbers (seconds, memory at the peak)
and both MP3s to listen to. There is no tool, no page for profiles and nothing a profile can start yet (stage M1).

The text of both songs is fixed here (TESTS), nothing comes from a person or a model. Only one measurement at a time
on the whole Spark; it waits for a Wartungspause "musik" to end. Journal lines start with "musik:", fixed words and
numbers only."""
import asyncio
import base64
import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import guard
import wartung
from common import STATE, load_config, model_url, write_json
from core import api_headers, auth

router = APIRouter()
JOB_SECONDS = 1000           # one song on the service, both steps (musik_server.JOB_S plus loading)
MAX_MP3 = 40 * 1024**2
# the two fixed songs (Stufe M0): what they are, the description, length, lyrics, language, a fixed seed
TESTS = (
    {"n": 1, "name": ("Instrumental, 30 s", "Instrumental, 30 s"), "caption": "calm piano piece with soft strings, warm",
     "seconds": 30, "lyrics": "", "language": "", "title": "Musik testen 1"},
    {"n": 2, "name": ("Lied mit deutschem Gesang, 60 s", "Song with German vocals, 60 s"),
     "caption": "cheerful german pop song, female vocals, acoustic guitar, upbeat",
     "seconds": 60, "language": "de", "title": "Musik testen 2",
     "lyrics": "[verse]\nDer Morgen kommt, die Sonne lacht,\nich hab an dich gedacht die ganze Nacht.\n"
               "[chorus]\nHeute ist ein guter Tag,\nweil ich alles mag, was ich mag."},
)
REASONS = ("missing", "memory", "engine", "zeit", "dienst", "pause")
_run = {"run": False, "done": 0, "t": 0}
_task = []


def cfg():
    return load_config("music")


def _state(name):
    return os.path.join(STATE, name)


def _test_file():
    return _state("musik-test.json")


def mp3_file(n):
    """The MP3 of fixed song n (1 or 2), written out in full so the register dateien.py finds both names."""
    return _state("musik-test-1.mp3") if int(n) == 1 else _state("musik-test-2.mp3")


def last_test():
    try:
        import json
        with open(_test_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


async def call(path, body=None, timeout=JOB_SECONDS):
    """One request to musik_server on the model computer (common.model_url, the panel's API key); (status, JSON)."""
    url = model_url("musik", path)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as c:
        if body is None:
            r = await c.get(url, headers=api_headers())
        else:
            r = await c.post(url, json=body, headers=api_headers())
    try:
        d = r.json()
    except ValueError:
        d = {}
    return r.status_code, d if isinstance(d, dict) else {}


async def health():
    """The service's state and numbers, {"status": "off_install"} when not installed, {"status": "down"} when it
    does not answer."""
    if not cfg().get("enabled"):
        return {"status": "off_install"}
    try:
        code, d = await call("/health", timeout=5)
    except httpx.HTTPError:
        return {"status": "down"}
    return d if code == 200 else {"status": "down"}


async def make(test):
    """One fixed song: (MP3 bytes, the service's numbers), or ValueError(why) with a word of REASONS."""
    body = {k: test[k] for k in ("caption", "seconds", "lyrics", "language", "title")}
    body["seed"] = 42
    try:
        code, d = await call("/v1/musik", body)
    except httpx.HTTPError:
        raise ValueError("dienst")
    if code in (502, 503) and d.get("detail") in ("memory", "missing", "engine"):
        raise ValueError(d["detail"])     # 502 "engine": the engine runs but did not make the song
    if code == 504:
        raise ValueError("zeit")
    if code != 200 or not isinstance(d.get("mp3"), str) or len(d["mp3"]) > MAX_MP3 * 4 // 3 + 4:
        raise ValueError("dienst")
    try:
        mp3 = base64.b64decode(d["mp3"], validate=True)
    except ValueError:
        raise ValueError("dienst")
    if not mp3.startswith(b"ID3") or len(mp3) > MAX_MP3:
        raise ValueError("dienst")
    return mp3, d


async def _measure():
    t0 = time.time()
    res = {"t": round(t0), "ok": False, "tests": []}
    try:
        for test in TESTS:
            row = {"n": test["n"], "ok": False, "why": ""}
            if wartung.paused("musik"):
                row["why"] = "pause"
            elif not cfg().get("enabled"):
                row["why"] = "missing"
            else:
                try:
                    mp3, d = await make(test)
                    with open(mp3_file(test["n"]), "wb") as f:
                        f.write(mp3)
                    row.update(ok=True, **{k: d.get(k) for k in ("seconds", "lm_s", "synth_s", "peak_gib", "length_s")})
                    row["kb"] = len(mp3) // 1024
                except ValueError as e:
                    row["why"] = str(e) if str(e) in REASONS else "dienst"
                except OSError:
                    row["why"] = "dienst"
            print(f"musik: test {row['n']}", "ok" if row["ok"] else "nicht ok " + row["why"],
                  f"{row.get('seconds') or 0} s", flush=True)
            res["tests"].append(row)
            _run["done"] += 1
        res["ok"] = all(r["ok"] for r in res["tests"])
        res["total_s"] = round(time.time() - t0, 1)
        res["health"] = await health()
        try:
            write_json(_test_file(), res)
        except OSError:
            print("musik: test nicht gespeichert", flush=True)
    finally:
        _run["run"] = False


def for_live():
    """Live-Übersicht: installed, measuring now, and how many of the last measurement's songs came out (numbers)."""
    last = last_test() or {}
    rows = last.get("tests") or []
    return {"on": bool(cfg().get("enabled")), "run": _run["run"], "ok": sum(1 for r in rows if r.get("ok")),
            "total": len(rows)}


def view():
    return {"run": _run["run"], "done": _run["done"], "total": len(TESTS), "last": last_test(),
            "tests": [{"n": t["n"], "name": {"de": t["name"][0], "en": t["name"][1]}} for t in TESTS]}


@router.get("/api/admin/musik-test", dependencies=[Depends(auth)])
async def musik_test_get():
    return dict(view(), health=await health())


@router.post("/api/admin/musik-test", dependencies=[Depends(auth)])
async def musik_test_run(request: Request):
    """Starts the measurement (only one at a time) and returns its state; the page asks GET for the rest."""
    guard.limit(request, "musiktest", None, True)
    if not _run["run"]:
        _run.update(run=True, done=0, t=time.time())
        print("musik: test gestartet", flush=True)
        _task[:] = [asyncio.create_task(_measure())]
    else:
        print("musik: test laeuft schon", flush=True)
    return dict(view(), health=await health())


@router.get("/api/admin/musik-test/{n}.mp3", dependencies=[Depends(auth)])
def musik_test_mp3(n: int, request: Request):
    guard.limit(request, "musikdatei", None, True)
    if n not in [t["n"] for t in TESTS] or not os.path.isfile(mp3_file(n)):
        raise HTTPException(404, "Noch kein Probestück")
    with open(mp3_file(n), "rb") as f:
        data = f.read(MAX_MP3 + 1)
    if len(data) > MAX_MP3:
        raise HTTPException(404, "Noch kein Probestück")
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "no-store",
                                                             "Content-Disposition": f'inline; filename="musik-test-{n}.mp3"'})
