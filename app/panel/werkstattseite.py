"""Zustand → Werkstatt (plan plaene/opencode-werkstatt.md, Dominik 2026-10-17 „0-4“ and „3 und 1 ohne OpenCode“; its
own page since Dominik 2026-10-21 „1“, before a box under Funktionen): the panel's side of app/werkstatt.py, for admins
only, default off (switch Funktionen → Werkstatt, chat.werkstatt).

Five kinds of orders, all run on the model computer in the sandbox of werkstatt.py (user spark-werkstatt, own copy
of the code, no data folder, no internet, no push):

    tests      the whole self-test like GitHub "Tests", without any model (also every night, see below)
    nachtest   only the red tests of a kept test run again, without any model (the names come from that result here,
               never from the page)
    messen     the code measurement: the running language model repairs 10 known bugs with OpenCode, counted green
    diagnose   OpenCode reads the code for the admin's problem and answers in words (it may not change anything)
    reparatur  OpenCode changes its copy; the result is a patch with the tests of the changed files

The page shows what runs (progress lines with fixed words and numbers), the results, the measurement per language
model and last night's test run. A patch is only shown (as text) and can be thrown away; nothing is installed or
pushed from here, the admin hands it to a Claude thread.

The panel decides with fixed rules (werkstatt.pruefen, again on the model computer and again by root); OpenCode never
decides anything. Diagnose, Reparatur and Code-Messung ask for the code (stufen.LIST): they let a model run code.

Night rule (fixed, in the panel, its own switch „Jede Nacht testen“, chat.werkstatt_nacht): in the hour chat.werkstatt_stunde (default 3) the test run
starts once; within NACHT_FENSTER_H hours after it, a code measurement when the language model running now has
none yet (werkstatt.messen_faellig: after a model switch). Nothing starts while an order runs.

With the models on another computer (plan Raspberry-Pi split) everything goes through its Wärter (tarswart.py
werkstatt, werkstatt_auftrag, werkstatt_eins, werkstatt_weg), which checks the same rules with its own state.
"""
import asyncio
import datetime
import os
import subprocess
import sys
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import steuer  # noqa: E402
import werkstatt  # noqa: E402
from common import journal, load_config  # noqa: E402
from core import admin_code, auth  # noqa: E402

MAX_BODY = 4096          # an order: the kind and at most werkstatt.TEXT_MAX characters
NACHT_FENSTER_H = 5      # hours after chat.werkstatt_stunde in which the night's orders may start
NACHT_PRUEF_S = 60       # the night rule looks once a minute
LIVE_EVERY = 20          # seconds the Live view reuses what it asked
_live = {"t": None, "v": None}
_nacht = {}              # kind -> the night (date) it was started for (in memory; the results say the rest)
# why an order is refused (werkstatt.Fehler words and the model computer's answers): a sentence for the page
GRUND = {"art": "Diese Art von Auftrag gibt es nicht.", "laeuft": "Ein Auftrag läuft schon.",
         "opencode": "OpenCode fehlt. Auf dem Modell-Rechner einmal: sudo ./install.sh --werkstatt",
         "llm": "Erst auf das eigene Sprachmodell umziehen: sudo speech-spark modelle llm uebernehmen",
         "text": f"Bitte das Problem in {werkstatt.TEXT_MIN} bis {werkstatt.TEXT_MAX} Zeichen beschreiben.",
         "start": "Der Auftrag ließ sich nicht starten. Auf dem Modell-Rechner: sudo ./install.sh --werkstatt",
         "wunsch": "ungültig", "rechner": "Der Modell-Rechner antwortet gerade nicht.",
         "aus": "Die Werkstatt ist aus (Funktionen → Werkstatt).",
         "namen": "Dieses Ergebnis hat keine roten Tests zum Wiederholen.", "keins": "Kein solcher Auftrag."}
STATUS = {"laeuft": 409, "aus": 409, "start": 503, "rechner": 503, "opencode": 409, "llm": 409, "namen": 409, "keins": 404}


def _an(cfg=None):
    """Funktionen → Werkstatt (cfg: the whole configuration, None reads it)."""
    return features.admin_on("werkstatt", None if cfg is None else cfg.get("chat", {}))


def _nacht_an(c=None):
    """Funktionen → Werkstatt → Jede Nacht testen (c: the chat section)."""
    return features.admin_on("werkstattnacht", c)


def check(ch):
    """Why the Werkstatt's own settings are not valid, "" when they are (admin.validate)."""
    v = ch.get("werkstatt_stunde", 3)
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 23:
        return "werkstatt_stunde: 0 bis 23"
    return ""


def _im_gang():
    try:
        return subprocess.run(["systemctl", "is-active", werkstatt.UNIT, werkstatt.LAUF_UNIT], capture_output=True,
                              text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _starten():
    try:
        r = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", werkstatt.UNIT],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sauber(d):
    """What the model computer (or this one) says, as data: known keys, results checked again, progress lines only
    with fixed words and numbers. None stays None (it does not answer)."""
    if not isinstance(d, dict):
        return None
    auftraege = []
    for a in (d.get("auftraege") if isinstance(d.get("auftraege"), list) else [])[:werkstatt.AUFTRAEGE_MAX]:
        try:
            r = werkstatt.pruefe_ergebnis(dict(a, patch="", text="") if isinstance(a, dict) else a)
        except werkstatt.Fehler:
            continue
        auftraege.append(werkstatt.kurz(r) | {"hat_patch": a.get("hat_patch") is True, "hat_text": a.get("hat_text") is True})
    stand = [z for z in (d.get("stand") if isinstance(d.get("stand"), list) else []) if isinstance(z, str) and werkstatt.STAND.match(z)]
    messungen = {}
    for mid, m in (d.get("messungen") if isinstance(d.get("messungen"), dict) else {}).items():
        if isinstance(mid, str) and werkstatt.MODELL.match(mid) and isinstance(m, dict):
            messungen[mid] = {k: werkstatt._zahl(m.get(k), 10 ** 11) for k in ("zeit", "gruen", "von", "dauer_s")}
    n = d.get("nacht") if isinstance(d.get("nacht"), dict) else {}
    t = n.get("tests") if isinstance(n.get("tests"), dict) else {}
    nacht = {"zeit": werkstatt._zahl(n.get("zeit"), 10 ** 11), "dauer_s": werkstatt._zahl(n.get("dauer_s"), 10 ** 6),
             "grund": n.get("grund") if n.get("grund") in werkstatt.GRUENDE else "",
             "tests": {k: werkstatt._zahl(t.get(k)) for k in ("gruen", "rot", "wackelig")}} if n else {}
    modell = d.get("modell") if isinstance(d.get("modell"), str) and werkstatt.MODELL.match(d.get("modell") or "") else ""
    art = next((z.split()[1] for z in stand[::-1] if len(z.split()) > 1 and z.split()[1] in werkstatt.ARTEN), "")
    return {"installiert": d.get("installiert") is True, "laeuft": d.get("laeuft") is True, "stand": stand,
            "art": art if d.get("laeuft") is True else "", "modell": modell, "auftraege": auftraege,
            "messungen": messungen, "nacht": nacht, "aufgaben": len(werkstatt.AUFGABEN), "version": werkstatt.OPENCODE_VERSION}


def holen(cfg=None):
    """The Werkstatt's state where the models are (checked), None when that computer does not answer."""
    cfg = load_config() if cfg is None else cfg
    if steuer.remote(cfg):
        return sauber(steuer.call("werkstatt", cfg=cfg, timeout=15))
    laeuft = werkstatt.im_gang(_im_gang())
    return sauber(werkstatt.daten(laeuft, werkstatt.stand(journal(werkstatt.UNIT, 60)) if laeuft else [], cfg=cfg))


def _eins(aid, cfg=None):
    """One kept order (checked), from here or the model computer; raises werkstatt.Fehler("keins"/"rechner")."""
    cfg = load_config() if cfg is None else cfg
    if not werkstatt.ID.match(str(aid)):
        raise werkstatt.Fehler("keins")
    if steuer.remote(cfg):
        d = steuer.call("werkstatt_eins", (aid,), cfg=cfg, timeout=15)
        if not isinstance(d, dict):
            raise werkstatt.Fehler("rechner")
        a = d.get("auftrag")
    else:
        a = werkstatt.eins(aid)
    try:
        return werkstatt.pruefe_ergebnis(a)
    except werkstatt.Fehler:
        raise werkstatt.Fehler("keins")


def nachtest_namen(r):
    """„Nur die roten noch mal“: the red tests of a kept result, whole names only, together at most werkstatt.TEXT_MAX
    characters (the Wärter takes no more). "selftest" (the run broke before any test) cannot run alone."""
    out = []
    for n in werkstatt.namen(" ".join((r.get("tests") or {}).get("rot_namen") or [])):
        if n != "selftest" and len(" ".join(out + [n])) <= werkstatt.TEXT_MAX:
            out.append(n)
    return out


def _fehler(word):
    word = word if word in GRUND else "wunsch"
    raise HTTPException(STATUS.get(word, 400), GRUND[word])


def auftrag_geben(art, text, cfg=None):
    """One order: the rules here (or on the model computer), the wish, the unit. Returns the kind; raises
    werkstatt.Fehler with the word."""
    cfg = load_config() if cfg is None else cfg
    if not _an(cfg):
        raise werkstatt.Fehler("aus")
    if steuer.remote(cfg):
        d = steuer.call("werkstatt_auftrag", cfg=cfg, timeout=30, daten={"art": str(art)[:12], "text": str(text)[:werkstatt.TEXT_MAX + 100]})
        if not isinstance(d, dict):
            raise werkstatt.Fehler("rechner")
        if d.get("ok") is not True:
            raise werkstatt.Fehler(d.get("fehler") if d.get("fehler") in GRUND else "wunsch")
        return art
    return werkstatt.anfragen(art, text, _starten, werkstatt.im_gang(_im_gang()), cfg)


# ---------------------------------------------------------------- the night rule (fixed, no model decides)
def nacht_art(d, jetzt, stunde, gestartet=None):
    """Which order the night wants now: "tests", "messen" or "". d: holen(); jetzt: the local time (aware or not);
    stunde: chat.werkstatt_stunde; gestartet: kind -> night already started for."""
    gestartet = {} if gestartet is None else gestartet
    if not d or d.get("laeuft") or not isinstance(stunde, int) or isinstance(stunde, bool) or not 0 <= stunde <= 23:
        return ""
    ab = jetzt.replace(hour=stunde, minute=0, second=0, microsecond=0)
    if jetzt < ab:
        ab -= datetime.timedelta(days=1)
    if jetzt >= ab + datetime.timedelta(hours=NACHT_FENSTER_H):
        return ""
    nacht = ab.date().isoformat()
    zeit = (d.get("nacht") or {}).get("zeit") or 0
    getestet = gestartet.get("tests") == nacht or (zeit and zeit >= ab.timestamp())
    if not getestet:
        return "tests" if jetzt < ab + datetime.timedelta(hours=1) else ""
    if werkstatt.messen_faellig(d) and gestartet.get("messen") != nacht:
        return "messen"
    return ""


def _nacht_einmal(now=None):
    cfg = load_config()
    c = cfg.get("chat", {})
    if not _nacht_an(c):
        return
    import chat
    jetzt = chat.local_now() if now is None else now
    d = holen(cfg)
    art = nacht_art(d, jetzt, c.get("werkstatt_stunde", 3), _nacht)
    if not art:
        return
    ab = jetzt.replace(hour=c.get("werkstatt_stunde", 3), minute=0, second=0, microsecond=0)
    _nacht[art] = (ab if jetzt >= ab else ab - datetime.timedelta(days=1)).date().isoformat()
    try:
        auftrag_geben(art, "", cfg)
        print(f"werkstatt: nacht {art} gestartet", flush=True)
    except werkstatt.Fehler as e:
        print(f"werkstatt: nacht {art} abgelehnt {e}", flush=True)
    _live["t"] = None


async def loop():
    while True:
        try:
            await asyncio.to_thread(_nacht_einmal)
        except Exception as e:
            print("werkstatt: nacht fehler", type(e).__name__, flush=True)
        await asyncio.sleep(NACHT_PRUEF_S)


def for_live(now=None):
    """Zustand → Live, box „Werkstatt“: what runs and the last numbers (kinds, counts), never a text or a patch."""
    now = time.time() if now is None else now
    if not _an():
        return {"on": False}
    if _live["t"] is None or now - _live["t"] > LIVE_EVERY:
        try:
            d = holen()
        except Exception:
            d = None
        _live["v"] = {"on": True, "da": d is not None}
        if d:
            m = d["messungen"].get(d["modell"]) if d["modell"] else None
            _live["v"].update(installiert=d["installiert"], laeuft=d["laeuft"], art=d["art"],
                              nacht=d["nacht"].get("tests") or {}, messung=m and f"{m['gruen']}/{m['von']}")
        _live["t"] = now
    return _live["v"]


def live_sub(v):
    """The Live box's line from for_live() (fixed words and numbers)."""
    if not v.get("da"):
        return "Modell-Rechner antwortet nicht"
    teile = [f"{werkstatt.ARTEN[v['art']][0]} läuft" if v.get("laeuft") and v.get("art") in werkstatt.ARTEN
             else ("Auftrag läuft" if v.get("laeuft") else "bereit")]
    if v.get("nacht"):
        teile.append(f"Nacht {v['nacht'].get('gruen', 0)} grün, {v['nacht'].get('rot', 0)} rot")
    if v.get("messung"):
        teile.append(f"Code-Messung {v['messung']}")
    if not v.get("installiert"):
        teile.append("ohne OpenCode")
    return " · ".join(teile)


# ---------------------------------------------------------------- the page (admins only)
router = APIRouter()


def _seite(cfg=None):
    cfg = load_config() if cfg is None else cfg
    d = holen(cfg)
    if d is None:
        raise HTTPException(503, GRUND["rechner"])
    c = cfg.get("chat", {})
    return d | {"an": _an(cfg), "nacht_an": _nacht_an(c),
                "stunde": c.get("werkstatt_stunde", 3), "arten": {k: {"de": v[0], "en": v[1], "llm": v[2], "text": v[3]}
                                                                   for k, v in werkstatt.ARTEN.items()}}


@router.get("/api/admin/werkstatt", dependencies=[Depends(auth)])
async def admin_werkstatt(request: Request):
    """Zustand → Werkstatt: what runs, the results without patches, the measurements, last night."""
    guard.limit(request, "werkstatt", None, True)
    return await asyncio.to_thread(_seite)


@router.post("/api/admin/werkstatt/tests", dependencies=[Depends(auth)])
async def admin_tests(request: Request):
    """„Alles testen“: the self-test in the sandbox, without a model (no code from a model runs: no code asked).
    With {"von": <id>} „Nur die roten noch mal“: the red tests of that kept result again; the names come from the
    result, never from the page."""
    guard.limit(request, "werkstatt_auftrag", None, True)
    body = await core.json_body(request, MAX_BODY, lenient=True)
    von = body.get("von") if isinstance(body, dict) else None
    if von is None:
        return await _geben(request, "tests", "")
    try:
        liste = nachtest_namen(await asyncio.to_thread(_eins, von))
    except werkstatt.Fehler as e:
        print(f"werkstatt: auftrag nachtest abgelehnt {e}", flush=True)
        _fehler(str(e))
    if not liste:
        print("werkstatt: auftrag nachtest abgelehnt namen", flush=True)
        _fehler("namen")
    return await _geben(request, "nachtest", " ".join(liste))


@router.post("/api/admin/werkstatt/auftrag", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_auftrag(request: Request):
    """Diagnose, Reparatur or Code-Messung: a model works in the sandbox with OpenCode, so the code is asked."""
    guard.limit(request, "werkstatt_auftrag", None, True)
    body = await core.json_body(request, MAX_BODY)
    art = body.get("art")
    if art not in werkstatt.ARTEN or art == "tests":
        _fehler("art")
    text = body.get("text", "")
    return await _geben(request, art, text if isinstance(text, str) else "")


async def _geben(request, art, text):
    try:
        await asyncio.to_thread(auftrag_geben, art, text)
    except werkstatt.Fehler as e:
        print(f"werkstatt: auftrag {art} abgelehnt {e}", flush=True)
        _fehler(str(e))
    print(f"werkstatt: auftrag {art} gestartet", flush=True)
    guard.log("werkstatt_auftrag", detail=werkstatt.ARTEN[art][0])
    _live["t"] = None
    return await asyncio.to_thread(_seite)


@router.get("/api/admin/werkstatt/{aid}", dependencies=[Depends(auth)])
def admin_eins(request: Request, aid: str):
    """One result with its answer and patch (both only text for the page)."""
    guard.limit(request, "werkstatt", None, True)
    try:
        r = _eins(aid)
    except werkstatt.Fehler as e:
        print(f"werkstatt: eins {e}", flush=True)
        _fehler(str(e))
    print("werkstatt: eins ok", flush=True)
    return r


@router.delete("/api/admin/werkstatt/{aid}", dependencies=[Depends(auth)])
def admin_weg(request: Request, aid: str):
    """„Verwerfen“: one result with its patch is deleted."""
    guard.limit(request, "werkstatt_auftrag", None, True)
    if not werkstatt.ID.match(aid):
        raise HTTPException(404, "Kein solcher Auftrag.")
    cfg = load_config()
    if steuer.remote(cfg):
        d = steuer.call("werkstatt_weg", (aid,), cfg=cfg, timeout=15)
        if not isinstance(d, dict):
            _fehler("rechner")
        ok = d.get("ok") is True
    else:
        ok = werkstatt.weg(aid)
    print(f"werkstatt: weg {'ok' if ok else 'keins'}", flush=True)
    if not ok:
        raise HTTPException(404, "Kein solcher Auftrag.")
    guard.log("werkstatt_weg")
    _live["t"] = None
    return _seite(cfg)
