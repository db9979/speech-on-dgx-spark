"""Zustand → Modelle (plan plaene/eigene-modelle.md, Stufe E1): the model catalog (app/modelle.py) to look at, for
admins only. Per kind (Sprachmodell, Bildverständnis, Spracherkennung, Sprachausgabe, Bilder malen, kleine Modelle)
which models the catalog knows, which one this configuration runs, its memory need (measured or estimated), licence,
and the memory budget: fixed models, models loaded on demand, what is left beside the system and the reserve, and
the fixed rule that follows from the numbers (all at once, one on-demand model at a time, too tight). Numbers from
`sudo speech-spark modelle messen` (STATE/modelle-messung.json) next to each measured model.

Stage E4 (admin switch Funktionen → Modelle wechseln, default off): "Wechseln" per model and "Zurückholen" per kind
for 7 days. The panel checks the fixed rules (modelle.wechsel_pruefen, with the running qwen38 lanes in the budget),
leaves a wish file and starts the root unit speech-spark-wechsel, which checks everything again and does the work
(download, check, switch, restart, round trip). Only names, numbers and fixed words; never an address, a key or a
text of an answer.

Stage E5 (admin switch Funktionen → Modelle wechseln → Eigene Modelle, default off): the admin adds a Hugging Face
model for the language model or image understanding. The panel reads only the metadata of one commit (netguard,
public internet), modelle.eigen_vorschlag applies the fixed rules (safetensors only, no code from the repository, an
architecture the engine knows, within the memory share), and the entry is kept with its commit pinned. It downloads
only when a switch picks it, through the same root unit.
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
from common import load_config, read_json  # noqa: E402
from core import admin_code, auth  # noqa: E402

LIVE_EVERY = 30          # seconds the Live view reuses the budget (systemctl and /proc are not read on every look)
MESSWERTE = ("tok_s", "erste_s", "belegt_gib", "laden_s", "mtp_annahme", "werkzeug", "bild_text", "bild_szene", "bild_ok", "ok")
_live = {"t": None, "v": None}
UNIT = "speech-spark-wechsel"
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
         # stage E5: an own model
         "repo": "Name wie besitzer/modell.", "antwort": "Hugging Face kennt dieses Modell nicht.",
         "zugang": "Das Modell ist privat oder braucht eine Freigabe; nur offene Modelle gehen.",
         "format": "Keine Gewichte als safetensors (Pickle-Dateien nimmt der Spark nie).",
         "code": "Das Modell braucht eigenen Code aus dem Repository; das läuft hier nie.",
         "architektur": "Diese Bauart kennt die Engine nicht.", "eigen": "ungültig", "voll": "Schon 20 eigene Modelle.",
         "aktiv": "Das Modell läuft gerade.", "netz": "Hugging Face ist gerade nicht erreichbar."}
EIGEN_BODY = 512


def _eigen_an(cfg=None):
    """Funktionen → Modelle wechseln → Eigene Modelle (stage E5)."""
    return features.admin_on("modelleeigen", None if cfg is None else cfg.get("chat", {}))


def _an(cfg=None):
    """Funktionen → Modelle wechseln (cfg: the whole configuration, None reads it)."""
    return features.admin_on("modellwechsel", None if cfg is None else cfg.get("chat", {}))


def _laeuft():
    try:
        return subprocess.run(["systemctl", "is-active", "-q", UNIT], timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _waehlbar(art, mid, cfg, total_gib, lanes, kat, messung):
    try:
        modelle.wechsel_pruefen(art, mid, cfg, total_gib, lanes, kat, messung)
        return ""
    except modelle.Fehler as e:
        return str(e)


def _lanes():
    import admin
    return [f for _, f in admin._qwen38_lanes()]


def seite(cfg=None, total_gib=None, lanes=None, messung=None, lang="de"):
    """What the page shows: {arten: [{art, name, modelle: [...]}], budget, messung_zeit}."""
    cfg = load_config() if cfg is None else cfg
    total_gib = modelle.gesamt_gib() if total_gib is None else total_gib
    lanes = _lanes() if lanes is None else lanes
    messung = read_json(modelle.MESSUNG, {}) if messung is None else messung
    i = 1 if lang == "en" else 0
    kat = modelle.katalog()
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
                         "eigen": bool(m.get("eigen")),
                         "gemessen": m["gemessen"], "betrieb": m["betrieb"], "lizenz": m["lizenz"], "gewerblich": m["gewerblich"],
                         "aktiv": mid in laufend, "gib": laufend.get(mid), "fest": bool(m["revision"]) or m["engine"] == "extern",
                         "messung": {k: r[k] for k in MESSWERTE if k in r}})
        arten.append({"art": art, "name": namen[i], "modelle": rows})
    wechsel = {"an": an, "laeuft": _laeuft() if an else False, "alte": modelle.alte(cfg, kat=kat) if an else {},
               "tage": modelle.ALT_TAGE, "eigene": _eigen_an(cfg)}
    return {"arten": arten, "budget": {k: v for k, v in b.items() if k != "teile"}, "messung_zeit": messung.get("zeit"),
            "wechsel": wechsel}


def for_live(now=None):
    """For the Live view's language model box: the memory left for models and the budget's rule (numbers, fixed word),
    after the move (llm.enabled) the catalog name of the own model."""
    now = time.monotonic() if now is None else now
    if _live["t"] is None or now - _live["t"] > LIVE_EVERY:
        try:
            cfg = load_config()
            b = modelle.budget(cfg, modelle.gesamt_gib(), _lanes())
            _live["v"] = {"on": True, "frei": b["frei"], "regel": b["regel"]}
            if cfg.get("llm", {}).get("enabled"):   # after the move: the own model's catalog name instead of qwen38
                _live["v"]["eigen"] = modelle.rolle("llm", cfg)[0]["name"]["de"]
            if _an(cfg) and _laeuft():              # stage E4: a switch runs (only that it runs, never which model)
                _live["v"]["wechsel"] = True
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


def _wunsch(request, art, was, mid):
    """Checks the rules for switching art to mid, leaves the wish and starts the root unit."""
    if not _an():
        print("modelle: wechsel abgelehnt aus", flush=True)
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    if _laeuft():
        print("modelle: wechsel abgelehnt laeuft", flush=True)
        raise HTTPException(409, "Ein Modellwechsel läuft schon.")
    try:
        modelle.wechsel_pruefen(art, mid, load_config(), modelle.gesamt_gib(), _lanes())
        modelle.wunsch_schreiben(art, was)
    except modelle.Fehler as e:
        print(f"modelle: wechsel abgelehnt {e}", flush=True)
        raise HTTPException(400, GRUND.get(str(e), "ungültig"))
    try:
        r = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", UNIT], capture_output=True, timeout=20)
        ok = r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if not ok:
        print("modelle: wechsel start fehler", flush=True)
        raise HTTPException(503, "Der Wechsel ließ sich nicht starten. Auf dem Spark: sudo speech-spark update, dann noch einmal.")
    print(f"modelle: wechsel {art} angefragt", flush=True)
    guard.log("modelle_wechsel", detail=f"{modelle.ARTEN[art][0]}: {modelle.eintrag(mid)['name']['de']}")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de")


@router.post("/api/admin/modelle/wechseln", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_wechseln(request: Request):
    """Wechseln: one model of the catalog for its kind (stage E4)."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    art, mid = str(body.get("art", ""))[:16], str(body.get("id", ""))[:48]
    return _wunsch(request, art, mid, mid)


@router.post("/api/admin/modelle/zurueck", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_zurueck(request: Request):
    """Zurückholen: the model before the last switch of this kind, within 7 days."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    art = str(body.get("art", ""))[:16]
    try:
        mid = modelle.zurueck_ziel(art) if art in modelle.TAUSCH else ""
    except modelle.Fehler as e:
        print(f"modelle: zurueck abgelehnt {e}", flush=True)
        raise HTTPException(400, GRUND.get(str(e), "ungültig"))
    if not mid:
        print("modelle: zurueck abgelehnt art", flush=True)
        raise HTTPException(400, GRUND["art"])
    return _wunsch(request, art, "zurueck", mid)


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


@router.post("/api/admin/modelle/eigen/pruefen", dependencies=[Depends(auth)])
async def eigen_pruefen(request: Request):
    """Prüfen: what the Spark would add for this Hugging Face name (nothing is kept or downloaded)."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    body = await core.json_body(request, EIGEN_BODY)
    art, repo = str(body.get("art", ""))[:16], str(body.get("repo", "")).strip()[:200]
    try:
        m = modelle.eigen_vorschlag(await _hf_info(repo), art, repo, modelle.gesamt_gib())
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
    try:
        if not modelle.REV.match(rev):
            raise modelle.Fehler("repo")
        m = modelle.eigen_vorschlag(await _hf_info(repo, rev), art, repo, modelle.gesamt_gib())
        if m["revision"] != rev:
            raise modelle.Fehler("antwort")
        modelle.eigen_speichern(m)
    except modelle.Fehler as e:
        print(f"modelle: eigenes abgelehnt {e}", flush=True)
        raise HTTPException(503 if str(e) == "netz" else 400, GRUND.get(str(e), "ungültig"))
    print(f"modelle: eigenes hinzugefuegt {m['art']}", flush=True)
    guard.log("modelle_eigen", detail=f"hinzugefügt: {m['name']['de']}")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de")


@router.delete("/api/admin/modelle/eigen/{mid}", dependencies=[Depends(auth), Depends(admin_code)])
def eigen_weg(request: Request, mid: str):
    """Löschen: an own model off the list and its files off the disk; never one that runs or can still come back."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    try:
        if not modelle.ID.match(mid):
            raise modelle.Fehler("unbekannt")
        weg = modelle.ordner_weg(modelle.eigen_loeschen(mid, load_config()))
    except modelle.Fehler as e:
        print(f"modelle: eigenes loeschen abgelehnt {e}", flush=True)
        raise HTTPException(404 if str(e) == "unbekannt" else 409, GRUND.get(str(e), "ungültig"))
    except OSError:
        print("modelle: eigenes loeschen dateien fehler", flush=True)
        raise HTTPException(500, "Die Dateien ließen sich nicht ganz löschen. Auf dem Spark: sudo speech-spark modelle liste")
    print(f"modelle: eigenes geloescht {'mit dateien' if weg else 'ohne dateien'}", flush=True)
    guard.log("modelle_eigen", detail=f"gelöscht: {mid}")
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de")
