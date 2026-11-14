"""Spark-Clients im Panel (plan spark-entkoppeln E1, Dominik 2026-11-14 „2a“): Einstellungen → Spark → Betrieb →
Spark-Clients. The admin lets other programs (another assistant, Open WebUI, Home Assistant, own scripts) use the
model computer's services with a key of their own: rights per service, a priority class, limits, only from the home
network. The rules live in ../mandanten.py on the computer that runs the services; this module only hands the
admin's wishes there: on the all-in-one install straight, on a split install through the Wärter (steuer.call).

Admins only, never guests, no tool for the model; off until the admin switches Funktionen → Spark-Clients on
(features "sparkclients", chat.spark_clients). Switching the function off closes the door for the clients again
(admin._save → zu()). A new key is shown once (fresh code) and never kept here.

    GET  /api/admin/spark-clients           switch, networks, clients (never a hash or key)
    POST /api/admin/spark-clients/schalten  {"an", "netze"}: open or close the services for the clients (code)
    POST /api/admin/spark-clients/neu       {"name", "rechte", "klasse", "minute", "parallel", "tokens_tag"} (fresh code)
    POST /api/admin/spark-clients/aendern   {"id", "felder"} (code)
    POST /api/admin/spark-clients/weg       {"id"} (code)
Journal lines: "sparkclient: panel …" with fixed words and counts, never a name or key.
"""
import asyncio
import os
import sys

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import features  # noqa: E402
import guard  # noqa: E402
import mandanten  # noqa: E402
import steuer  # noqa: E402
from core import admin_code, admin_code_fresh, auth, json_body  # noqa: E402

router = APIRouter()
MAX_BODY = 4096
WARUM = {"aus": "Spark-Clients sind aus (Funktionen → Spark-Clients).",
         "weg": "Der Modell-Rechner antwortet nicht. Später noch einmal.",
         "name": "Name: 1 bis 40 Zeichen, Buchstaben, Ziffern, Leerzeichen, . _ ( ) -.",
         "recht": "Mindestens ein Recht wählen.", "klasse": "Unbekannte Vorrangklasse.",
         "wert": "Ein Wert liegt außerhalb der Grenzen.", "voll": "Es gibt schon die größte Zahl an Clients.",
         "unbekannt": "Diesen Client gibt es nicht mehr.",
         "netz": "Nur Netze im Heimnetz, z. B. 192.168.178.0/24."}


def admin_on(c=None):
    return features.admin_on("sparkclients", c)


def _tun(cmd, args=(), daten=None):
    """One step on the computer that runs the services: here straight, else through the Wärter. The answer, or
    HTTPException with a fixed sentence of WARUM."""
    try:
        if not steuer.remote():
            if cmd == "clients":
                return mandanten.uebersicht()
            if cmd == "client_neu":
                c, key = mandanten.neu(daten.get("name"), daten.get("rechte"), daten.get("klasse"),
                                       **{k: daten[k] for k in mandanten.GRENZEN if k in daten})
                return {"client": c, "key": key}
            if cmd == "client_aendern":
                return {"client": mandanten.aendern(str(daten.get("id") or ""), daten.get("felder"))}
            if cmd == "client_weg":
                return {"ok": mandanten.weg(args[0])}
            return mandanten.schalten(daten.get("an"), daten.get("netze"))
        d = steuer.call(cmd, args, daten=daten, timeout=15)
    except mandanten.Fehler as e:
        d = {"fehler": str(e)}
    if not isinstance(d, dict):
        print(f"sparkclient: panel {cmd} modell-rechner weg", flush=True)
        raise HTTPException(503, WARUM["weg"])
    if d.get("fehler"):
        print(f"sparkclient: panel {cmd} abgelehnt {d['fehler'] if d['fehler'] in WARUM else 'wert'}", flush=True)
        raise HTTPException(400, WARUM.get(str(d["fehler"]), WARUM["wert"]))
    print(f"sparkclient: panel {cmd} ok", flush=True)
    return d


async def _body(request, code=None):
    guard.limit(request, "sparkclients", admin=True)
    body = await json_body(request, MAX_BODY)
    if not admin_on():
        print("sparkclient: panel abgelehnt aus", flush=True)
        raise HTTPException(409, WARUM["aus"])
    return body


@router.get("/api/admin/spark-clients", dependencies=[Depends(auth)])
async def admin_get(request: Request):
    guard.limit(request, "sparkclients", admin=True)
    if not admin_on():
        raise HTTPException(409, WARUM["aus"])
    return await asyncio.to_thread(_tun, "clients")


@router.post("/api/admin/spark-clients/schalten", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_schalten(request: Request):
    b = await _body(request)
    d = await asyncio.to_thread(_tun, "clients_schalten", (), {"an": b.get("an"), "netze": b.get("netze")})
    guard.log("spark_clients", detail=f"{'an' if d.get('an') else 'aus'}, {len(d.get('netze') or [])} Netze")
    return d


@router.post("/api/admin/spark-clients/neu", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_neu(request: Request):
    b = await _body(request)
    daten = {k: b[k] for k in ("name", "rechte", "klasse", *mandanten.GRENZEN) if k in b}
    d = await asyncio.to_thread(_tun, "client_neu", (), daten)
    guard.log("spark_client", detail="neu")
    return d


@router.post("/api/admin/spark-clients/aendern", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_aendern(request: Request):
    b = await _body(request)
    d = await asyncio.to_thread(_tun, "client_aendern", (), {"id": b.get("id"), "felder": b.get("felder")})
    guard.log("spark_client", detail="geändert")
    return d


@router.post("/api/admin/spark-clients/weg", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_weg(request: Request):
    b = await _body(request)
    cid = str(b.get("id") or "")
    if not mandanten.ID_RE.fullmatch(cid):
        raise HTTPException(400, WARUM["unbekannt"])
    d = await asyncio.to_thread(_tun, "client_weg", (cid,))
    guard.log("spark_client", detail="gelöscht")
    return d
