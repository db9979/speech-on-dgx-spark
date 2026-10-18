"""Zustand → Modelle (plan plaene/eigene-modelle.md, Stufe E1): the model catalog (app/modelle.py) to look at, for
admins only. Per kind (Sprachmodell, Bildverständnis, Spracherkennung, Sprachausgabe, Bilder malen, kleine Modelle)
which models the catalog knows, which one this configuration runs, its memory need (measured or estimated), licence,
and the memory budget: fixed models, models loaded on demand, what is left beside the system and the reserve, and
the fixed rule that follows from the numbers (all at once, one on-demand model at a time, too tight). Numbers from
`sudo speech-spark modelle messen` (STATE/modelle-messung.json) next to each measured model.

Stage E4 (admin switch Funktionen → Modelle wechseln, default off): "Wechseln" per model and "Zurückholen" per kind
for 7 days. With the same switch "Messen" per model (Dominik 2026-10-17): the wish for the root unit
speech-spark-messen-wunsch, which measures like `sudo speech-spark modelle messen <id>`; the language model pauses
meanwhile, a switch waits until the measurement is done and the other way round. The panel checks the fixed rules (modelle.wechsel_pruefen, with the running qwen38 lanes in the budget),
leaves a wish file and starts the root unit speech-spark-wechsel, which checks everything again and does the work
(download, check, switch, restart, round trip). Only names, numbers and fixed words; never an address, a key or a
text of an answer.

Stage E5 (admin switch Funktionen → Modelle wechseln → Eigene Modelle, default off): the admin adds a Hugging Face
model for the language model or image understanding. The panel reads only the metadata of one commit (netguard,
public internet), modelle.eigen_vorschlag applies the fixed rules (safetensors only, no code from the repository, an
architecture the engine knows, within the memory share), and the entry is kept with its commit pinned. It downloads
only when a switch picks it, through the same root unit.

Models on another computer (plan Raspberry-Pi split, B4c): the catalog, the memory, the measurement, the switches and
the own models are that computer's. The page then takes them from its Wärter (steuer.modelle), and Wechseln,
Zurückholen and the own models go there (tarswart.py), which checks the same fixed rules again with its own numbers
and starts its speech-spark-wechsel. The switch Funktionen → Modelle wechseln stays the panel's.
"""
import os
import subprocess
import sys
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import features  # noqa: E402
import netguard  # noqa: E402
import guard  # noqa: E402
import modelle  # noqa: E402
import steuer  # noqa: E402
from common import journal, load_config, read_json  # noqa: E402
from core import admin_code, auth  # noqa: E402

LIVE_EVERY = 30          # seconds the Live view reuses the budget (systemctl and /proc are not read on every look)
MESSWERTE = ("tok_s", "erste_s", "belegt_gib", "laden_s", "mtp_annahme", "erste_warm_s", "zwischenspeicher", "werkzeug", "bild_text", "bild_szene", "bild_ok", "ok",
             "par2_tok_s", "par2_summe", "par2_erste_s", "par4_tok_s", "par4_summe", "par4_erste_s", "lang_tokens",
             "lang_erste_s", "lang_tok_s", "platz_64k", "par2_fehler", "par4_fehler", "lang_fehler")
_live = {"t": None, "v": None}
MAX_BODY = 256
# why a switch is refused (modelle.Fehler words): a sentence for the page
GRUND = {"art": "Diese Art lässt sich nicht wechseln.", "unbekannt": "Das Modell steht nicht im Katalog.",
         "engine": "Dieses Modell startet der Spark nicht selbst.",
         "revision": "Das Modell ist noch nicht gemessen. Auf dem Spark: sudo speech-spark modelle messen",
         "aus": "Erst auf das eigene Sprachmodell umziehen: sudo speech-spark modelle llm uebernehmen",
         "wahl": "Dieses Modell kommt nur zusammen mit einem anderen.", "schon": "Dieses Modell läuft schon.",
         "budget": "Zu knapp: mit diesem Modell bleibt weniger als die Reserve frei.",
         "keins": "Es gibt kein voriges Modell zum Zurückholen.", "frist": "Das vorige Modell ist älter als 7 Tage.",
         "wunsch": "ungültig", "ungeprueft": "Erst messen: sudo speech-spark modelle messen <id>",
         "docker": "Modelle in Docker werden vorerst nur gemessen; Wechseln kommt im nächsten Schritt.",
         # stage E5: an own model
         "repo": "Name wie besitzer/modell.", "antwort": "Hugging Face kennt dieses Modell nicht.",
         "zugang": "Das Modell ist privat oder braucht eine Freigabe; nur offene Modelle gehen.",
         "format": "Keine Gewichte als safetensors (Pickle-Dateien nimmt der Spark nie).",
         "code": "Das Modell braucht eigenen Code aus dem Repository; das läuft hier nie.",
         "architektur": "Diese Bauart kennt die Engine nicht.", "eigen": "ungültig", "voll": "Schon 20 eigene Modelle.",
         "aktiv": "Das Modell läuft gerade.", "netz": "Hugging Face ist gerade nicht erreichbar.",
         # plan Raspberry-Pi split: the model computer's answers
         "laeuft": "Ein Modellwechsel läuft schon.", "misst": "Eine Messung läuft gerade.",
         "start": "Der Wechsel ließ sich nicht starten. Auf dem Spark: sudo speech-spark update, dann noch einmal.",
         "start_messen": "Die Messung ließ sich nicht starten. Auf dem Spark: sudo speech-spark update, dann noch einmal.",
         "rechner": "Der Modell-Rechner antwortet gerade nicht.",
         # „Lange Gespräche“
         "platz": "Diese Auswahl gibt es nicht.", "suche": "Suchwort mit Buchstaben, Zahlen, Leerzeichen, Punkt, Strich.", "kontext": "Dieses Modell kann so lange Gespräche nicht.", "dateien": "Die Dateien ließen sich nicht ganz löschen."}
STATUS = {"laeuft": 409, "misst": 409, "start": 503, "start_messen": 503, "rechner": 503}
EIGEN_BODY = 512


def _eigen_an(cfg=None):
    """Funktionen → Modelle wechseln → Eigene Modelle (stage E5)."""
    return features.admin_on("modelleeigen", None if cfg is None else cfg.get("chat", {}))


def _an(cfg=None):
    """Funktionen → Modelle wechseln (cfg: the whole configuration, None reads it)."""
    return features.admin_on("modellwechsel", None if cfg is None else cfg.get("chat", {}))


def _im_gang(*units):
    """The states of the units, one line each (`systemctl is-active`); "" when systemctl does not answer."""
    try:
        return subprocess.run(["systemctl", "is-active", *units], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _laeuft():
    return modelle.im_gang(_im_gang(modelle.WECHSEL_UNIT))


def _misst():
    """A measurement runs here (the command line's unit or the one for „Messen“)."""
    return modelle.im_gang(_im_gang(modelle.MESS_UNIT, modelle.MESS_WUNSCH_UNIT))


def _stand():
    """While a measurement runs here: its last progress lines (modelle.stand), from the unit that works."""
    units = (modelle.MESS_UNIT, modelle.MESS_WUNSCH_UNIT)
    unit = next((u for u, z in zip(units, _im_gang(*units).splitlines()) if modelle.im_gang(z)), "")
    return modelle.stand(journal(unit, 60)) if unit else []


def _starten(unit=modelle.WECHSEL_UNIT):
    try:
        r = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", unit], capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _quelle(cfg):
    """(total_gib, lanes, messung, laeuft, kat, alte switches, misst, stand) of the computer the models run on;
    HTTPException 503 when that is another one and it does not answer. laeuft, misst and stand are None here (asked
    when needed)."""
    if steuer.remote(cfg):
        d = steuer.modelle(cfg)
        if d is None:
            raise HTTPException(503, GRUND["rechner"])
        stand = modelle.stand("\n".join(x for x in d.get("stand", []) if isinstance(x, str))) if d.get("misst") else []
        return (d["gesamt_gib"], d["lanes"], d["messung"], d["laeuft"], modelle.katalog(eigene=d["eigene"]), d["wechsel"],
                d.get("misst", False), stand)
    return modelle.gesamt_gib(), _lanes(), read_json(modelle.MESSUNG, {}), None, modelle.katalog(), None, None, None


def _fehler(e, was="wechsel"):
    """The HTTP answer for a refused switch or measurement (a fixed word from here or from the model computer)."""
    word = str(e)
    print(f"modelle: {was} abgelehnt {word}", flush=True)
    raise HTTPException(STATUS.get(word, 400), GRUND.get(word, "ungültig"))


def _waehlbar(art, mid, cfg, total_gib, lanes, kat, messung):
    try:
        modelle.wechsel_pruefen(art, mid, cfg, total_gib, lanes, kat, messung)
        return ""
    except modelle.Fehler as e:
        return str(e)


def _lanes():
    import admin
    return [f for _, f in admin._qwen38_lanes()]


def seite(cfg=None, total_gib=None, lanes=None, messung=None, lang="de", gestartet=False, wechselt=False):
    """What the page shows: {arten: [{art, name, modelle: [...]}], budget, messung_zeit}."""
    cfg = load_config() if cfg is None else cfg
    q_gib, q_lanes, q_messung, laeuft, kat, wechsel, misst, stand = _quelle(cfg)
    total_gib = q_gib if total_gib is None else total_gib
    lanes = q_lanes if lanes is None else lanes
    messung = q_messung if messung is None else messung
    i = 1 if lang == "en" else 0
    an = _an(cfg)
    b = modelle.budget(cfg, total_gib, lanes, kat)
    laufend = {x["id"]: x["gib"] for x in b["teile"]}
    gemessen = messung.get("modelle") or {}
    arten = []
    for art, namen in modelle.ARTEN.items():
        rows = []
        for mid, m in kat.items():
            if m["art"] != art:
                continue
            r = gemessen.get(mid) or {}
            nein = _waehlbar(art, mid, cfg, total_gib, lanes, kat, messung) if an and art in modelle.TAUSCH else "art"
            rows.append({"id": mid, "name": m["name"]["en" if i else "de"], "engine": m["engine"], "need_gib": m["need_gib"],
                         "waehlbar": not nein, "nein": "" if nein in ("art", "schon", "wahl") else nein,
                         "eigen": bool(m.get("eigen")), "messbar": an and m["engine"] == "vllm",
                         "gemessen": m["gemessen"], "betrieb": m["betrieb"], "lizenz": m["lizenz"], "gewerblich": m["gewerblich"],
                         "aktiv": mid in laufend, "gib": laufend.get(mid), "fest": bool(m["revision"]) or m["engine"] == "extern",
                         "messung": {k: r[k] for k in MESSWERTE if k in r}})
        arten.append({"art": art, "name": namen[i], "modelle": rows})
    laeuft = ((_laeuft() if laeuft is None else laeuft) or wechselt) if an else False
    misst = bool(_misst() if misst is None else misst)
    stand = (_stand() if stand is None else stand) if misst else []
    # just asked for: the unit starts in a moment (--no-block), the page shows it at once
    platz = modelle.platz_wahl(cfg, total_gib, lanes, kat) if an and cfg.get("llm", {}).get("enabled") else None
    for p in (platz or {}).get("wahl", []):
        p["name"] = p["name"][i]
    probe = modelle.probe_stand(kat, messung, laufend, misst or gestartet) if an else None
    if probe:
        probe["name"] = kat[probe["id"]]["name"]["en" if i else "de"]
        probe["jetzt_name"] = kat[probe["jetzt_id"]]["name"]["en" if i else "de"] if probe["jetzt_id"] else ""
        probe["waehlbar"] = next((m["waehlbar"] for a in arten for m in a["modelle"] if m["id"] == probe["id"]), False)
    wechsel = {"an": an, "laeuft": laeuft, "misst": misst or gestartet, "stand": stand, "platz": platz, "probe": probe,
               "alte": modelle.alte(cfg, kat=kat, daten=wechsel) if an else {},
               "tage": modelle.ALT_TAGE, "eigene": _eigen_an(cfg)}
    # the bar's parts (Dominik 2026-10-18: one colored piece per model, the tiles below in the same color)
    teile = [{"id": x["id"], "name": kat[x["id"]]["name"]["en" if i else "de"], "art": x["art"], "gib": x["gib"],
              "betrieb": x["betrieb"]} for x in b["teile"]]
    return {"arten": arten, "budget": dict(b, teile=teile), "messung_zeit": messung.get("zeit"),
            "wechsel": wechsel}


def for_live(now=None):
    """For the Live view's language model box: the memory left for models and the budget's rule (numbers, fixed word),
    after the move (llm.enabled) the catalog name of the own model."""
    now = time.monotonic() if now is None else now
    if _live["t"] is None or now - _live["t"] > LIVE_EVERY:
        try:
            cfg = load_config()
            total_gib, lanes, _, laeuft, kat, _, misst, _ = _quelle(cfg)
            b = modelle.budget(cfg, total_gib, lanes, kat)
            _live["v"] = {"on": True, "frei": b["frei"], "regel": b["regel"]}
            if cfg.get("llm", {}).get("enabled"):   # after the move: the own model's catalog name instead of qwen38
                _live["v"]["eigen"] = modelle.rolle("llm", cfg, kat)[0]["name"]["de"]
            if _an(cfg) and (_laeuft() if laeuft is None else laeuft):   # stage E4: a switch runs (never which model)
                _live["v"]["wechsel"] = True
            if _misst() if misst is None else misst:   # a measurement runs (from the panel or the command line)
                _live["v"]["messen"] = True
        except Exception:
            _live["v"] = {"on": False}
        _live["t"] = now
    return _live["v"]


router = APIRouter()


@router.get("/api/admin/modelle", dependencies=[Depends(auth)])
def admin_modelle(request: Request, lang: str = "de"):
    """Zustand → Modelle: catalog, active models, memory budget and the last measurement (names and numbers only)."""
    guard.limit(request, "modelle", None, True)
    return seite(lang="en" if lang == "en" else "de")


@router.post("/api/admin/modelle/messen", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_messen(request: Request):
    """„Messen“: one model measured like `speech-spark modelle messen`, here or on the model computer (Dominik
    2026-10-17). The language model pauses meanwhile; the root unit speech-spark-messen-wunsch does the work."""
    guard.limit(request, "modelle_messen", None, True)
    body = await core.json_body(request, MAX_BODY)
    mid = str(body.get("id", ""))[:48]
    probe = body.get("probe") is True        # „Ausprobieren“: afterwards the page asks whether to switch
    if not _an():
        print("modelle: messen abgelehnt aus", flush=True)
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    cfg = load_config()
    if steuer.remote(cfg):
        d = steuer.call("messen", (mid,), cfg=cfg, timeout=30)
        if not isinstance(d, dict):
            _fehler("rechner", "messen")
        if d.get("ok") is not True:
            word = d.get("fehler") if d.get("fehler") in GRUND else "wunsch"
            _fehler("start_messen" if word == "start" else word, "messen")
        name = str(d.get("name") or "")[:48]
    else:
        try:
            name = modelle.messen_anfragen(mid, lambda: _starten(modelle.MESS_WUNSCH_UNIT), _misst() or _laeuft())["name"]["de"]
        except modelle.Fehler as e:
            if str(e) == "start":
                print("modelle: messen start fehler", flush=True)
                raise HTTPException(503, GRUND["start_messen"])
            _fehler(e, "messen")
    print("modelle: messen angefragt", flush=True)
    if probe:
        kat = _quelle(cfg)[4]                 # with the model computer's own models
        if mid in kat and kat[mid]["art"] in modelle.TAUSCH:
            modelle.probe_merken(mid, kat[mid]["art"])
            print("modelle: ausprobieren angefragt", flush=True)
        else:
            print("modelle: ausprobieren abgelehnt art", flush=True)
    guard.log("modelle_messen", detail=name)
    _live["t"] = None
    return seite(cfg, lang="en" if request.query_params.get("lang") == "en" else "de", gestartet=True)


def _wunsch(request, art, was, mid=""):
    """Checks the rules for switching art to was (an id or "zurueck"), leaves the wish and starts the root unit: here,
    or through the Wärter on the model computer."""
    if not _an():
        print("modelle: wechsel abgelehnt aus", flush=True)
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    cfg = load_config()
    if steuer.remote(cfg):
        d = steuer.call("wechseln", (art, was), cfg=cfg, timeout=30)
        if not isinstance(d, dict):
            _fehler("rechner")
        if d.get("ok") is not True:
            _fehler(d.get("fehler") if d.get("fehler") in GRUND else "wunsch")
        name = str(d.get("name") or "")[:48]
    else:
        if _misst():
            _fehler("misst")
        try:
            name = modelle.wechsel_anfragen(art, was, cfg, modelle.gesamt_gib(), _lanes(), _starten, _laeuft())["name"]["de"]
        except modelle.Fehler as e:
            if str(e) == "start":
                print("modelle: wechsel start fehler", flush=True)
                raise HTTPException(503, GRUND["start"])
            _fehler(e)
    print(f"modelle: wechsel {art} angefragt", flush=True)
    if (read_json(modelle.PROBE, {}) or {}).get("art") == art and modelle.probe_weg():
        print("modelle: ausprobieren erledigt", flush=True)
    guard.log("modelle_wechsel", detail=f"{modelle.ARTEN[art][0]}: {name}")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de", wechselt=True)


@router.post("/api/admin/modelle/platz", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_platz(request: Request):
    """„Lange Gespräche“ (Dominik 2026-10-17): the own language model's context store as one of modelle.PLATZ; root
    (speech-spark-wechsel) restarts it with the new memory share and context, here or on the model computer."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    was = str(body.get("platz", ""))[:16]
    if not _an():
        print("modelle: platz abgelehnt aus", flush=True)
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    cfg = load_config()
    if steuer.remote(cfg):
        d = steuer.call("platz", (was,), cfg=cfg, timeout=30)
        if not isinstance(d, dict):
            _fehler("rechner", "platz")
        if d.get("ok") is not True:
            _fehler(d.get("fehler") if d.get("fehler") in GRUND else "wunsch", "platz")
    else:
        if _misst():
            _fehler("misst", "platz")
        try:
            modelle.platz_anfragen(was, cfg, modelle.gesamt_gib(), _lanes(), _starten, _laeuft())
        except modelle.Fehler as e:
            if str(e) == "start":
                print("modelle: platz start fehler", flush=True)
                raise HTTPException(503, GRUND["start"])
            _fehler(e, "platz")
    print("modelle: platz angefragt", flush=True)
    guard.log("modelle_wechsel", detail=f"Lange Gespräche: {modelle.PLATZ_NAMEN[was][0]}")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de", wechselt=True)


@router.post("/api/admin/modelle/wechseln", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_wechseln(request: Request):
    """Wechseln: one model of the catalog for its kind (stage E4)."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    art, mid = str(body.get("art", ""))[:16], str(body.get("id", ""))[:48]
    return _wunsch(request, art, mid)


@router.post("/api/admin/modelle/zurueck", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_zurueck(request: Request):
    """Zurückholen: the model before the last switch of this kind, within 7 days."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    art = str(body.get("art", ""))[:16]
    if art not in modelle.TAUSCH:
        print("modelle: zurueck abgelehnt art", flush=True)
        raise HTTPException(400, GRUND["art"])
    return _wunsch(request, art, "zurueck")


@router.delete("/api/admin/modelle/probe", dependencies=[Depends(auth)])
def admin_probe_weg(request: Request):
    """„Verwerfen“ after „Ausprobieren“: the question whether to switch goes away, nothing else changes."""
    guard.limit(request, "modelle", None, True)
    if modelle.probe_weg():
        print("modelle: ausprobieren verworfen", flush=True)
    else:
        print("modelle: ausprobieren verworfen keins", flush=True)
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de")


# ---------------------------------------------------------------- stage E5: own models
async def _hf_info(repo, rev=""):
    """The metadata of one commit (or the newest) from Hugging Face, through netguard (public internet only)."""
    if not modelle.REPO.match(repo) or ".." in repo or not (rev == "" or modelle.REV.match(rev)):
        raise modelle.Fehler("repo")
    import httpx
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=modelle.HF_INFO_MAX, timeout=20, follow_redirects=False) as c:
            r = await c.get(modelle.HF_API.format(repo=repo, rev=rev or "main"))
    except (httpx.HTTPError, OSError, ValueError):
        raise modelle.Fehler("netz")
    if r.status_code in (401, 403):
        raise modelle.Fehler("zugang")
    if r.status_code != 200:
        raise modelle.Fehler("antwort")
    try:
        return r.json()
    except ValueError:
        raise modelle.Fehler("antwort")


def _eigen_tor(request):
    if not _eigen_an():
        print("modelle: eigenes abgelehnt aus", flush=True)
        raise HTTPException(409, "Eigene Modelle sind aus (Funktionen → Modelle wechseln → Eigene Modelle).")


def _zeige(m):
    return {k: m[k] for k in ("id", "art", "name", "repo", "revision", "lizenz", "gewerblich", "platte_gb", "need_gib",
                              "kann_sehen", "werkzeuge")}


@router.post("/api/admin/modelle/eigen/suche", dependencies=[Depends(auth)])
async def eigen_suche(request: Request):
    """„Suchen“ (Dominik 2026-10-17 „3a“): Hugging Face's public search through netguard; the hits get the quick rules
    of modelle.such_treffer, nothing is kept, downloaded or added."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    body = await core.json_body(request, EIGEN_BODY)
    art = str(body.get("art", ""))[:16]
    import httpx
    try:
        url = modelle.such_url(str(body.get("q", ""))[:80])
        try:
            async with netguard.client(netguard.PUBLIC, max_bytes=modelle.SUCHE_ANTWORT_MAX, timeout=20,
                                       follow_redirects=False) as c:
                r = await c.get(url)
        except (httpx.HTTPError, OSError, ValueError):
            raise modelle.Fehler("netz")
        if r.status_code != 200:
            raise modelle.Fehler("antwort")
        try:
            items = r.json()
        except ValueError:
            raise modelle.Fehler("antwort")
        q = _quelle(load_config())
        treffer = modelle.such_treffer(items, art, q[0], q[4])
    except modelle.Fehler as e:
        print(f"modelle: suche abgelehnt {e}", flush=True)
        raise HTTPException(503 if str(e) == "netz" else 400, GRUND.get(str(e), "ungültig"))
    print(f"modelle: suche {len(treffer)} treffer", flush=True)
    return {"treffer": treffer}


@router.post("/api/admin/modelle/eigen/pruefen", dependencies=[Depends(auth)])
async def eigen_pruefen(request: Request):
    """Prüfen: what the Spark would add for this Hugging Face name (nothing is kept or downloaded)."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    body = await core.json_body(request, EIGEN_BODY)
    art, repo = str(body.get("art", ""))[:16], str(body.get("repo", "")).strip()[:200]
    total_gib = _quelle(load_config())[0]
    try:
        m = modelle.eigen_vorschlag(await _hf_info(repo), art, repo, total_gib)
    except modelle.Fehler as e:
        print(f"modelle: eigenes abgelehnt {e}", flush=True)
        raise HTTPException(503 if str(e) == "netz" else 400, GRUND.get(str(e), "ungültig"))
    print("modelle: eigenes geprueft", flush=True)
    return {"vorschlag": _zeige(m)}


@router.post("/api/admin/modelle/eigen", dependencies=[Depends(auth), Depends(admin_code)])
async def eigen_dazu(request: Request):
    """Hinzufügen: the checked commit becomes an own catalog entry (downloaded only when a switch picks it)."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    body = await core.json_body(request, EIGEN_BODY)
    art, repo, rev = str(body.get("art", ""))[:16], str(body.get("repo", "")).strip()[:200], str(body.get("revision", ""))[:40]
    cfg = load_config()
    total_gib = _quelle(cfg)[0]
    try:
        if not modelle.REV.match(rev):
            raise modelle.Fehler("repo")
        m = modelle.eigen_vorschlag(await _hf_info(repo, rev), art, repo, total_gib)
        if m["revision"] != rev:
            raise modelle.Fehler("antwort")
        if steuer.remote(cfg):              # the model computer keeps the list and checks the entry again
            d = steuer.call("eigen_dazu", cfg=cfg, daten=m, timeout=15)
            if not isinstance(d, dict) or d.get("ok") is not True:
                raise modelle.Fehler(d.get("fehler") if isinstance(d, dict) and d.get("fehler") in GRUND else "rechner")
        else:
            modelle.eigen_speichern(m)
    except modelle.Fehler as e:
        print(f"modelle: eigenes abgelehnt {e}", flush=True)
        raise HTTPException(503 if str(e) in ("netz", "rechner") else 400, GRUND.get(str(e), "ungültig"))
    print(f"modelle: eigenes hinzugefuegt {m['art']}", flush=True)
    guard.log("modelle_eigen", detail=f"hinzugefügt: {m['name']['de']}")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de")


@router.delete("/api/admin/modelle/eigen/{mid}", dependencies=[Depends(auth), Depends(admin_code)])
def eigen_weg(request: Request, mid: str):
    """Löschen: an own model off the list and its files off the disk; never one that runs or can still come back."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    cfg = load_config()
    try:
        if not modelle.ID.match(mid):
            raise modelle.Fehler("unbekannt")
        if steuer.remote(cfg):              # the list and the files are the model computer's
            d = steuer.call("eigen_weg", (mid,), cfg=cfg, timeout=60)
            if isinstance(d, dict) and d.get("fehler") == "dateien":
                raise OSError("dateien")
            if not isinstance(d, dict) or d.get("ok") is not True:
                raise modelle.Fehler(d.get("fehler") if isinstance(d, dict) and d.get("fehler") in GRUND else "rechner")
            weg = d.get("dateien") is True
        else:
            weg = modelle.ordner_weg(modelle.eigen_loeschen(mid, cfg))
    except modelle.Fehler as e:
        print(f"modelle: eigenes loeschen abgelehnt {e}", flush=True)
        raise HTTPException({"unbekannt": 404, "rechner": 503}.get(str(e), 409), GRUND.get(str(e), "ungültig"))
    except OSError:
        print("modelle: eigenes loeschen dateien fehler", flush=True)
        raise HTTPException(500, "Die Dateien ließen sich nicht ganz löschen. Auf dem Spark: sudo speech-spark modelle liste")
    print(f"modelle: eigenes geloescht {'mit dateien' if weg else 'ohne dateien'}", flush=True)
    guard.log("modelle_eigen", detail=f"gelöscht: {mid}")
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de")
