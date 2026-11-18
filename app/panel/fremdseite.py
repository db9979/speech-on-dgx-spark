"""Zustand → Modelle, card „Fremde Modell-Dienste“ (plan katalogpaket-und-zwei-modellrechner.md E6, Dominik
2026-11-17 „c“): an admin adds a language model another program in the home network serves through the OpenAI
interface (Ollama, LM Studio, Alzeo), the panel checks it with fixed rules, and the admin uses it „Für alle“ or as
„Ersatz“ while the model computer is gone. Every STATUS_S seconds it looks at each service; when the model in use is
no longer listed and another checked one is (Alzeo switched its lane), it follows (fremdmodell.folgen). The rules and the stored services are in fremdmodell.py; llm.py asks it.

Fixed rules (Richtlinie Teil 2): the address is an IP in the home network (fremdmodell.basis), every connection goes
through netguard (HOME); the service's answers are data: the check looks only for fixed things (the model in the list,
a German answer with a fixed word, a call of the fixed tool), never does what the text says. The key never reaches a
page or a log; logs carry the service's id (f1..f3), fixed words and numbers only.
"""
import asyncio
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import core
import features
import fremdmodell
import guard
import health
import llm
import netguard
from common import load_config
from core import admin_code, auth

MAX_BODY = 2048
TIMEOUT = 60           # seconds for one answer of the check (a big model on a Mac may load first)
LISTE_MAX = 200        # model names shown from /v1/models
STATUS_S = 60          # seconds between two looks at the services while the switch is on (a lane switch shows within)
SATZ = ("Antworte mit genau einem kurzen deutschen Satz: Welche Farbe hat der Himmel an einem klaren Tag?")
SATZ_WORT = "blau"
_status = fremdmodell.STATUS   # the last look per service (fremdmodell.STATUS), never a key or a text
GRUND = {
    "adresse": ("Die Adresse muss so aussehen: http://192.168.178.20:11434/v1 (eine IP im Heimnetz mit Port).",
                "The address must look like this: http://192.168.178.20:11434/v1 (an IP in the home network with "
                "a port)."),
    "heimnetz": ("Nur Adressen im Heimnetz (192.168.x.x, 10.x.x.x, 172.16-31.x.x).",
                 "Only addresses in the home network (192.168.x.x, 10.x.x.x, 172.16-31.x.x)."),
    "port": ("Dieser Port gehört zu den Diensten des Sparks.", "This port belongs to the Spark's own services."),
    "name": ("Ein Name mit 1 bis 30 Zeichen, ohne < > \" ' `.", "A name of 1 to 30 characters, without < > \" ' `."),
    "key": ("Der Schlüssel hat Zeichen, die nicht gehen (nur sichtbare ASCII-Zeichen, höchstens 200).",
            "The key has characters that do not work (visible ASCII only, at most 200)."),
    "voll": (f"Höchstens {fremdmodell.MAX} fremde Dienste.", f"At most {fremdmodell.MAX} foreign services."),
    "doppelt": ("Diese Adresse ist schon eingetragen.", "This address is already there."),
    "unbekannt": ("Diesen Dienst gibt es nicht mehr.", "This service is gone."),
    "modell": ("Diesen Modellnamen nimmt der Spark nicht.", "The Spark does not take this model name."),
    "ungeprueft": ("Erst prüfen: nur ein geprüftes Modell kann genutzt werden.",
                   "Check it first: only a checked model can be used."),
    "aus": ("Funktionen → Fremde Modell-Dienste ist aus.", "Features → Foreign model services is off."),
    "netz": ("netguard lässt diese Adresse nicht zu.", "netguard does not allow this address."),
    "erreichbar": ("Der Dienst antwortet nicht.", "The service does not answer."),
    "schluessel": ("Der Dienst will einen anderen Schlüssel.", "The service wants another key."),
    "fehlt": ("Der Dienst nennt dieses Modell nicht (mehr).", "The service does not list this model (any more)."),
    "satz": ("Keine passende deutsche Antwort.", "No fitting German answer."),
    "werkzeug": ("Das Modell ruft kein Werkzeug auf.", "The model does not call a tool."),
    "antwort": ("Die Antwort des Dienstes ist nicht lesbar.", "The service's answer is not readable."),
}


def _an(cfg=None):
    """Funktionen → Fremde Modell-Dienste (cfg: the whole configuration, None reads it)."""
    return features.admin_on("fremdmodelle", (load_config() if cfg is None else cfg).get("chat", {}))


def _fehler(wort, lang="de"):
    raise HTTPException(400, GRUND.get(wort, GRUND["antwort"])[1 if lang == "en" else 0])


def _client(x, timeout):
    """A client to exactly this service: netguard HOME, the key only in the header."""
    ip, port = fremdmodell.ziel_ip(x)
    if netguard.allowed(ip, port, netguard.HOME) is not None:
        raise fremdmodell.Fehler("netz")
    hdrs = {"Authorization": f"Bearer {x['key']}"} if x.get("key") else {}
    return netguard.client(netguard.HOME, headers=hdrs, timeout=httpx.Timeout(timeout, connect=5),
                           follow_redirects=False)


def _darf(url):
    """The Spark's own services are never a foreign service (netguard.own_service, the one rule), and netguard must
    allow the address in the home network."""
    ip, port = fremdmodell.ziel_ip({"url": url})
    if netguard.own_service(ip, port):
        raise fremdmodell.Fehler("port")
    if netguard.allowed(ip, port, netguard.HOME) is not None:
        raise fremdmodell.Fehler("netz")


def _wort(e):
    """A fixed word for what went wrong on the way to the service."""
    if isinstance(e, fremdmodell.Fehler):
        return str(e)
    if isinstance(e, httpx.HTTPStatusError):
        return "schluessel" if e.response.status_code in (401, 403) else "antwort"
    if isinstance(e, netguard.Blocked):
        return "netz"
    if isinstance(e, httpx.HTTPError):
        return "erreichbar"
    return "antwort"


async def modelle_holen(x, timeout=15):
    """The model names the service lists itself (/v1/models), sorted, at most LISTE_MAX."""
    async with _client(x, timeout) as c:
        r = await c.get(x["url"] + "/models")
        r.raise_for_status()
        data = r.json().get("data")
    if not isinstance(data, list):
        raise ValueError("data")
    names = sorted({str(m.get("id")) for m in data if isinstance(m, dict) and fremdmodell.MODELL.match(str(m.get("id")))})
    return names[:LISTE_MAX]


async def pruefen(x, modell):
    """The panel's own check (fixed rules): the model in the list, a German sentence with the fixed word, a call of
    the fixed tool. Returns (word or "", numbers {"ms", "tok_s"}); never the service's text."""
    zahlen = {}
    try:
        if modell not in await modelle_holen(x):
            return "fehlt", zahlen
        async with _client(x, TIMEOUT) as c:
            t0 = time.monotonic()
            r = await c.post(llm.url(llm.eigen({"llm_url": x["url"]})), json={
                "model": modell, "max_tokens": 200, "temperature": 0, "stream": False,
                "messages": [{"role": "user", "content": SATZ}]})
            r.raise_for_status()
            s = time.monotonic() - t0
            d = r.json()
            text = str(((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            n = int(((d.get("usage") or {}).get("completion_tokens")) or 0)
            zahlen = {"ms": int(s * 1000), "tok_s": round(n / s, 1) if n and s > 0 else None}
            if SATZ_WORT not in text.lower():
                return "satz", zahlen
            r = await c.post(llm.url(llm.eigen({"llm_url": x["url"]})), json={
                "model": modell, "max_tokens": 300, "temperature": 0.1, "stream": False, "tools": [health.CHECK_TOOL],
                "tool_choice": "auto",
                "messages": [{"role": "user", "content": "Wie spät ist es? Nutze dafür das Werkzeug."}]})
            r.raise_for_status()
            if not health.tool_called(r.json())[0]:
                return "werkzeug", zahlen
    except (httpx.HTTPError, netguard.Blocked, fremdmodell.Fehler, ValueError, KeyError, TypeError,
            AttributeError, IndexError) as e:
        return _wort(e), zahlen
    return "", zahlen


async def status_tick():
    """One look at every service while the switch is on: answers /v1/models, how fast. Logs only a change."""
    if not _an():
        _status.clear()
        return
    for x in fremdmodell.stand()["dienste"]:
        t0 = time.monotonic()
        try:
            names = await modelle_holen(x, 10)
            wort = "" if not x.get("modell") or x["modell"] in names else "fehlt"
            if wort and fremdmodell.folgen(x["id"], names):   # another checked model runs now (Alzeo's lanes)
                wort = ""
                print(f"modelle: fremd {x['id']} folgt lane {len(fremdmodell.lanes(x))} geprueft", flush=True)
        except Exception as e:   # noqa: BLE001 - a broken service is a status, not a crash
            wort = _wort(e)
        alt = _status.get(x["id"]) or {}
        _status[x["id"]] = dict(alt, ok=not wort, wort=wort, ms=int((time.monotonic() - t0) * 1000), t=int(time.time()))
        if alt.get("ok", None) is not (not wort):
            print(f"modelle: fremd {x['id']} {'erreichbar' if not wort else 'weg ' + wort}", flush=True)
    for fid in set(_status) - {x["id"] for x in fremdmodell.stand()["dienste"]}:
        _status.pop(fid, None)


async def status_loop():
    while True:
        await asyncio.sleep(STATUS_S)
        try:
            await status_tick()
        except Exception as e:   # noqa: BLE001 - the loop goes on
            print("modelle: fremd status fehler", type(e).__name__, flush=True)


router = APIRouter()


def _seite():
    d = fremdmodell.stand()
    return {"an": bool(_an()), "max": fremdmodell.MAX, "wahl": d["wahl"], "ersatz": d["ersatz"],
            "dienste": fremdmodell.zeigen(d, _status)}


@router.get("/api/admin/modelle/fremd", dependencies=[Depends(auth)])
def fremd_liste(request: Request):
    """The card: the services (never a key), which one is used how, status and numbers."""
    guard.limit(request, "modelle", None, True)
    return _seite()


@router.put("/api/admin/modelle/fremd", dependencies=[Depends(auth), Depends(admin_code)])
async def fremd_speichern(request: Request, lang: str = "de"):
    """A new service (id "") or a changed one: name, address, key (absent keeps it, "" deletes it)."""
    guard.limit(request, "modelle_fremd", None, True)
    body = await core.json_body(request, MAX_BODY)
    if not _an():
        print("modelle: fremd speichern aus", flush=True)
        _fehler("aus", lang)
    try:
        url = fremdmodell.basis(body.get("url"))
        _darf(url)
        fid = fremdmodell.speichern(str(body.get("id") or ""), body.get("name"), url,
                                    body["key"] if isinstance(body.get("key"), str) else None)
    except fremdmodell.Fehler as e:
        print(f"modelle: fremd speichern abgelehnt {e}", flush=True)
        _fehler(str(e), lang)
    _status.pop(fid, None)
    print(f"modelle: fremd {fid} gespeichert", flush=True)
    guard.log("modelle_fremd", detail=f"{fid} gespeichert")
    return _seite() | {"id": fid}


@router.post("/api/admin/modelle/fremd/modelle", dependencies=[Depends(auth)])
async def fremd_modelle(request: Request, lang: str = "de"):
    """The model names the service lists itself, to pick one for the check."""
    guard.limit(request, "modelle_fremd", None, True)
    body = await core.json_body(request, MAX_BODY)
    x = fremdmodell.finde(fremdmodell.stand(), str(body.get("id") or ""))
    if x is None:
        _fehler("unbekannt", lang)
    try:
        names = await modelle_holen(x)
    except Exception as e:   # noqa: BLE001 - every way it fails is one fixed word
        print(f"modelle: fremd {x['id']} liste {_wort(e)}", flush=True)
        _fehler(_wort(e), lang)
    print(f"modelle: fremd {x['id']} liste {len(names)}", flush=True)
    return {"modelle": names}


@router.post("/api/admin/modelle/fremd/pruefen", dependencies=[Depends(auth), Depends(admin_code)])
async def fremd_pruefen(request: Request, lang: str = "de"):
    """The check on exactly this address and model; passed: the model is usable (fremdmodell.geprueft)."""
    guard.limit(request, "modelle_fremd", None, True)
    body = await core.json_body(request, MAX_BODY)
    if not _an():
        print("modelle: fremd pruefen aus", flush=True)
        _fehler("aus", lang)
    x = fremdmodell.finde(fremdmodell.stand(), str(body.get("id") or ""))
    modell = str(body.get("modell") or "")
    if x is None:
        _fehler("unbekannt", lang)
    if not fremdmodell.MODELL.match(modell):
        _fehler("modell", lang)
    wort, zahlen = await pruefen(x, modell)
    _status[x["id"]] = {"ok": not wort, "wort": wort, "t": int(time.time()), **zahlen}
    if wort:
        print(f"modelle: fremd {x['id']} pruefung {wort}", flush=True)
        _fehler(wort, lang)
    try:
        fremdmodell.geprueft(x["id"], modell)
    except fremdmodell.Fehler as e:
        print(f"modelle: fremd {x['id']} pruefung {e}", flush=True)
        _fehler(str(e), lang)
    print(f"modelle: fremd {x['id']} geprueft {zahlen.get('ms', 0)} ms {zahlen.get('tok_s') or 0} tok/s", flush=True)
    guard.log("modelle_fremd", detail=f"{x['id']} geprüft")
    return _seite()


@router.post("/api/admin/modelle/fremd/wahl", dependencies=[Depends(auth), Depends(admin_code)])
async def fremd_wahl(request: Request, lang: str = "de"):
    """„Für alle“ (wahl) and „Ersatz“ (ersatz): an id of a checked service or "" for the own model."""
    guard.limit(request, "modelle_fremd", None, True)
    body = await core.json_body(request, MAX_BODY)
    if not _an():
        print("modelle: fremd wahl aus", flush=True)
        _fehler("aus", lang)
    try:
        fremdmodell.nutzung(str(body.get("wahl") or ""), str(body.get("ersatz") or ""))
    except fremdmodell.Fehler as e:
        print(f"modelle: fremd wahl {e}", flush=True)
        _fehler(str(e), lang)
    d = fremdmodell.stand()
    print(f"modelle: fremd wahl {d['wahl'] or 'eigen'} ersatz {d['ersatz'] or 'keiner'}", flush=True)
    guard.log("modelle_fremd", detail=f"Für alle {d['wahl'] or 'eigen'}, Ersatz {d['ersatz'] or 'keiner'}")
    return _seite()


@router.delete("/api/admin/modelle/fremd/{fid}", dependencies=[Depends(auth), Depends(admin_code)])
def fremd_loeschen(fid: str, request: Request, lang: str = "de"):
    """A service and its key are gone; „Für alle“ or „Ersatz“ on it fall back to the own model."""
    guard.limit(request, "modelle_fremd", None, True)
    try:
        fremdmodell.loeschen(fid)
    except fremdmodell.Fehler as e:
        print("modelle: fremd loeschen unbekannt", flush=True)
        _fehler(str(e), lang)
    _status.pop(fid, None)
    print(f"modelle: fremd {fid} geloescht", flush=True)
    guard.log("modelle_fremd", detail=f"{fid} gelöscht")
    return _seite()
