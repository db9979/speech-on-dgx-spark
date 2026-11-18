"""Zustand → Modelle (plan plaene/eigene-modelle.md, Stufe E1): the model catalog (app/modelle.py) to look at, for
admins only. Per kind (Sprachmodell, Bildverständnis, Spracherkennung, Sprachausgabe, Bilder malen, kleine Modelle)
which models the catalog knows, which one this configuration runs, its memory need (measured or estimated), licence,
and the memory budget: fixed models, models loaded on demand, what is left beside the system and the reserve, and
the fixed rule that follows from the numbers (all at once, one on-demand model at a time, too tight). Numbers from
`sudo speech-spark modelle messen` (STATE/modelle-messung.json) next to each measured model.

Stage E4 (admin switch Funktionen → Modelle wechseln, default off): "Wechseln" per model and "Zurückholen" per kind
for 7 days. With the same switch "Messen" per model (Dominik 2026-10-17): the wish for the root unit
speech-spark-messen-wunsch, which measures like `sudo speech-spark modelle messen <id>`; the language model pauses
meanwhile, a switch waits until the measurement is done and the other way round. The panel checks the fixed rules (modelle.wechsel_pruefen, with the budget),
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
import asyncio
import os
import subprocess
import sys
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import admin  # noqa: E402
import core  # noqa: E402
import features  # noqa: E402
import netguard  # noqa: E402
import guard  # noqa: E402
import hardware  # noqa: E402
import health  # noqa: E402
import hftoken  # noqa: E402
import konsole  # noqa: E402
import llmstart  # noqa: E402
import modelle  # noqa: E402
import modelleneu  # noqa: E402
import probetag  # noqa: E402
import quality  # noqa: E402
import steuer  # noqa: E402
from common import journal, load_config, read_json, spark_allein, write_json  # noqa: E402
from core import admin_code, admin_code_fresh, auth  # noqa: E402

LIVE_EVERY = 30          # seconds the Live view reuses the budget (systemctl and /proc are not read on every look)
MESSWERTE = ("tok_s", "erste_s", "belegt_gib", "laden_s", "mtp_annahme", "erste_warm_s", "zwischenspeicher", "werkzeug", "bild_text", "bild_szene", "bild_ok", "ok",
             "par2_tok_s", "par2_summe", "par2_erste_s", "par4_tok_s", "par4_summe", "par4_erste_s", "lang_tokens",
             "lang_erste_s", "lang_tok_s", "platz_64k", "par2_fehler", "par4_fehler", "lang_fehler", "ablage", "frei_geladen_gib",
             "frei_tiefst_gib")
_live = {"t": None, "v": None}
LAGE_S = 10              # seconds the banner and the chat reuse what the language model does (lage)
_lage = {"t": None, "v": None}
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
         "docker": "Dieses Modell läuft nur in Docker, und das nur als Sprachmodell nach einer Messung hier.",
         # stage E5: an own model
         "repo": "Name wie besitzer/modell.", "antwort": "Hugging Face kennt dieses Modell nicht.",
         "zugang": "Das Modell ist privat oder braucht eine Freigabe; nur offene Modelle gehen.",
         "format": "Keine Gewichte als safetensors (Pickle-Dateien nimmt der Spark nie).",
         "code": "Das Modell braucht eigenen Code aus dem Repository; das läuft hier nie.",
         "architektur": "Diese Bauart kennt die Engine nicht.",
         "familie": "Nicht dieselbe Bauart wie die geprüften Modelle dieses Programms.",
         "basis": "Diese Grundvariante gibt es nicht, oder sie ist noch nicht installiert.", "eigen": "ungültig", "voll": "Schon 20 eigene Modelle.",
         "aktiv": "Das Modell läuft gerade.", "netz": "Hugging Face ist gerade nicht erreichbar.",
         # plan Raspberry-Pi split: the model computer's answers
         "laeuft": "Ein Modellwechsel läuft schon.", "misst": "Eine Messung läuft gerade.",
         "start": "Der Wechsel ließ sich nicht starten. Auf dem Spark: sudo speech-spark update, dann noch einmal.",
         "start_messen": "Die Messung ließ sich nicht starten. Auf dem Spark: sudo speech-spark update, dann noch einmal.",
         "rechner": "Der Modell-Rechner antwortet gerade nicht.",
         # „Lange Gespräche“
         "platz": "Diese Auswahl gibt es nicht.", "suche": "Suchwort mit Buchstaben, Zahlen, Leerzeichen, Punkt, Strich.", "kontext": "Dieses Modell kann so lange Gespräche nicht.", "dateien": "Die Dateien ließen sich nicht ganz löschen."}
STATUS = {"laeuft": 409, "misst": 409, "start": 503, "start_messen": 503, "rechner": 503}
# Modell-Bibliothek (stage B1c): the answers to „Löschen“
BIBLIOTHEK_GRUND = {"repo": "ungültig", "fehlt": "Dieser Stand liegt nicht mehr auf der Platte.",
                    "gebraucht": "Dieser Stand gehört zu einem Modell im Katalog; er bleibt.",
                    "dateien": "Die Dateien ließen sich nicht ganz löschen.", "rechner": "Der Modell-Rechner antwortet gerade nicht."}
# the words the model computer may answer a restart with (Rezept-Abgleich); "schon": it runs as its entry says
NEUSTART_GRUND = ("laeuft", "misst", "schon", "start")
EIGEN_BODY = 512
# the Rezept-Editor's own answers (stage B1); every field of modelle.REZEPT_FELDER answers with its name
REZEPT_GRUND = {"schon": "Am Rezept hat sich nichts geändert.", "felder": "Unbekanntes Feld im Rezept.",
                "entwurf": "Das Entwurfsmodell braucht einen Namen wie anbieter/name, einen festen Stand (40 Zeichen) und MTP über 0.",
                "budget": "So passt das Modell nicht in den Speicher dieses Rechners.",
                "aktiv": "Das Modell läuft gerade. Erst zu einem anderen wechseln, dann das Rezept ändern."}
REZEPT_WOERTER = set(GRUND) | set(REZEPT_GRUND) | set(modelle.REZEPT_FELDER)


def _eigen_an(cfg=None):
    """Funktionen → Modelle wechseln → Eigene Modelle (stage E5); in the Spark-Konsole (konsole.py) always: that page is
    the Spark's own, its admin decides there."""
    return konsole.aktiv() or features.admin_on("modelleeigen", None if cfg is None else cfg.get("chat", {}))


def _an(cfg=None):
    """Funktionen → Modelle wechseln (cfg: the whole configuration, None reads it); always in the Spark-Konsole."""
    return konsole.aktiv() or features.admin_on("modellwechsel", None if cfg is None else cfg.get("chat", {}))


def _probetag_an(cfg=None):
    """Funktionen → Modelle wechseln → „Probetag nach dem Wechsel“ (cfg: the whole configuration, None reads it)."""
    return features.admin_on("modelleprobetag", None if cfg is None else cfg.get("chat", {}))


def _neu_an(cfg=None):
    """Funktionen → Modelle wechseln → „Neu verfügbar“ (cfg: the whole configuration, None reads it)."""
    return features.admin_on("modelleneu", None if cfg is None else cfg.get("chat", {}))


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
    """(total_gib, messung, laeuft, kat, alte switches, misst, stand, start, profil, buch) of the computer the models run on;
    HTTPException 503 when that is another one and it does not answer. laeuft, misst and stand are None here (asked
    when needed); start is what the language model does while it switches or starts (llmstart); profil its hardware
    (hardware.py; a model computer before stage A sends none: the reference, a DGX Spark); buch the Startprotokoll and
    whether the language model runs with other settings than its entry (stage B1b/B1d; none from an older one)."""
    if steuer.remote(cfg):
        d = steuer.modelle(cfg)
        if d is None:
            raise HTTPException(503, GRUND["rechner"])
        stand = modelle.stand("\n".join(x for x in d.get("stand", []) if isinstance(x, str))) if d.get("misst") else []
        # the own re-ranking models are this computer's (they run here, nachsortieren.py), the others the model computer's
        eigene = [x for x in d["eigene"] if isinstance(x, dict) and x.get("art") != "klein"] + modelle.eigene_eintraege("klein")
        return (d["gesamt_gib"], d["messung"], d["laeuft"], modelle.katalog(eigene=eigene), d["wechsel"],
                d.get("misst", False), stand, d.get("start"), hardware.gueltig(d.get("profil")) or hardware.profil(),
                {"starts": llmstart.buch_pruefen(d.get("starts")), "abweichung": d.get("abweichung") is True,
                 "hf_token": _hf_token_pruefen(d.get("hf_token")), "bibliothek": _bibliothek_pruefen(d.get("bibliothek"))})
    messung = read_json(modelle.MESSUNG, {})
    return (modelle.gesamt_gib(), messung, None, modelle.katalog(), None, None, None,
            llmstart.hier(cfg, messung), hardware.profil(),
            {"starts": _starts_hier(), "abweichung": modelle.abweichung("llm", cfg), "hf_token": hftoken.info(),
             "bibliothek": modelle.bibliothek(cfg)})


def _bibliothek_pruefen(x):
    """The model computer's library in the shape modelle.bibliothek gives; a row of another shape is left out."""
    def gut(e):
        return (isinstance(e, dict) and set(e) == {"repo", "revision", "gib", "ids", "laeuft", "lose", "geladen"}
                and isinstance(e["geladen"], bool)
                and modelle.REPO.match(str(e["repo"])) is not None and ".." not in e["repo"]
                and modelle.REV.match(str(e["revision"])) is not None
                and isinstance(e["gib"], (int, float)) and not isinstance(e["gib"], bool) and 0 <= e["gib"] < 10**5
                and isinstance(e["ids"], list) and len(e["ids"]) <= 50 and all(isinstance(i, str) and modelle.ID.match(i) for i in e["ids"])
                and isinstance(e["laeuft"], bool) and e["lose"] is (not e["ids"]))
    return [dict(e) for e in x[:modelle.BIBLIOTHEK_MAX] if gut(e)] if isinstance(x, list) else []


def _starts_hier():
    """The Startprotokoll on this computer, the newest start's load time taken from its engine's journal once."""
    from common import journal
    for art in llmstart.BUCH_ARTEN:
        e = llmstart.letzter(art)
        if e and "bereit_s" not in e:
            llmstart.nachtragen(art, lambda u=f"speech-spark-{art}": journal(u, 600, "short-unix"))
    return llmstart.buch()


def _fehler(e, was="wechsel"):
    """The HTTP answer for a refused switch or measurement (a fixed word from here or from the model computer)."""
    word = str(e)
    print(f"modelle: {was} abgelehnt {word}", flush=True)
    raise HTTPException(STATUS.get(word, 400), GRUND.get(word, "ungültig"))


def _waehlbar(art, mid, cfg, total_gib, kat, messung, profil=None):
    try:
        modelle.wechsel_pruefen(art, mid, cfg, total_gib, kat, messung, profil)
        return ""
    except modelle.Fehler as e:
        return str(e)


def _klein_nein(mid, cfg, kat):
    try:
        modelle.klein_pruefen(mid, cfg, kat)
        return ""
    except modelle.Fehler as e:
        return str(e)


def seite(cfg=None, total_gib=None, messung=None, lang="de", gestartet=False, wechselt=False):
    """What the page shows: {arten: [{art, name, modelle: [...]}], budget, messung_zeit}."""
    cfg = load_config() if cfg is None else cfg
    q_gib, q_messung, laeuft, kat, wechsel, misst, stand, start, profil, buch = _quelle(cfg)
    total_gib = q_gib if total_gib is None else total_gib
    messung = q_messung if messung is None else messung
    i = 1 if lang == "en" else 0
    an = _an(cfg)
    b = modelle.budget(cfg, total_gib, kat, profil)
    laufend = {x["id"]: x for x in b["teile"]}
    gemessen = messung.get("modelle") or {}
    platte = {(e["repo"], e["revision"]) for e in buch["bibliothek"]}
    arten = []
    # Hilfsmodell, Einbetten and Nachsortieren to choose: only in the Spark-Konsole of a Spark alone (Dominik
    # 2026-11-18); the pooling kinds are not shown anywhere else
    allein = konsole.aktiv() and spark_allein(cfg)
    for art, namen in modelle.ARTEN.items():
        if art in modelle.POOL_ARTEN and not allein:
            continue
        rows = []
        emp = modelle.empfohlen(art, kat, profil)      # the checked recommendation for this kind of computer
        for mid, m in kat.items():
            if m["art"] != art:
                continue
            r = gemessen.get(mid) or {}
            nein = (_waehlbar(art, mid, cfg, total_gib, kat, messung, profil)
                    if an and art in modelle.TAUSCH and (allein or art not in modelle.ALLEIN_ARTEN)
                    else _klein_nein(mid, cfg, kat) if an and art == "klein" else "art")
            rows.append({"id": mid, "name": m["name"]["en" if i else "de"], "engine": m["engine"], "need_gib": m["need_gib"],
                         "waehlbar": not nein, "nein": "" if nein in ("art", "schon", "wahl") else nein,
                         "eigen": bool(m.get("eigen")), "empfohlen": mid == emp,
                         "messbar": an and m["engine"] == "vllm" and art not in modelle.POOL_ARTEN,
                         # how the configuration runs it (VoiceDesign on demand), else the catalog's way
                         "gemessen": m["gemessen"], "betrieb": (laufend.get(mid) or {}).get("betrieb") or m["betrieb"], "lizenz": m["lizenz"], "gewerblich": m["gewerblich"],
                         "aktiv": mid in laufend, "gib": (laufend.get(mid) or {}).get("gib"), "fest": bool(m["revision"]),
                         "messung": {k: r[k] for k in MESSWERTE if k in r},
                         # numbers from another kind of computer (a measurement before stage A was on the Spark)
                         "gemessen_auf": _anderswo(r, profil, i),
                         # Rezept-Editor (stage B1): the own entry's engine settings for the form
                         **({"rezept": modelle.rezept(m)} if m.get("eigen") and m["engine"] == "vllm" else {}),
                         # „Nur laden“ (stage B1c): a pinned model of the cache that is not on the disk yet
                         "laden": bool(an and m["engine"] in modelle.ENTFERNBAR and m["revision"]
                                       and (m["repo"], m["revision"]) not in platte)})
        arten.append({"art": art, "name": namen[i], "modelle": rows, "empfohlen": emp,
                      # „Entladen“ (Spark-Konsole): Einbetten / Nachsortieren off again while one is loaded
                      **({"entladbar": an and bool(modelle.jetzt_id(art, cfg, kat))} if art in modelle.POOL_ARTEN else {})})
    laeuft = ((_laeuft() if laeuft is None else laeuft) or wechselt) if an else False
    misst = bool(_misst() if misst is None else misst)
    stand = (_stand() if stand is None else stand) if misst else []
    # just asked for: the unit starts in a moment (--no-block), the page shows it at once
    platz = modelle.platz_wahl(cfg, total_gib, kat, profil) if an and cfg.get("llm", {}).get("enabled") else None
    for p in (platz or {}).get("wahl", []):
        p["name"] = p["name"][i]
    probe = modelle.probe_stand(kat, messung, laufend, misst or gestartet) if an else None
    if probe:
        probe["name"] = kat[probe["id"]]["name"]["en" if i else "de"]
        probe["jetzt_name"] = kat[probe["jetzt_id"]]["name"]["en" if i else "de"] if probe["jetzt_id"] else ""
        probe["waehlbar"] = next((m["waehlbar"] for a in arten for m in a["modelle"] if m["id"] == probe["id"]), False)
    wechsel = {"an": an, "laeuft": laeuft, "misst": misst or gestartet, "stand": stand, "platz": platz, "probe": probe,
               "start": _start_zeigen(start, kat, i),
               "alte": modelle.alte(cfg, kat=kat, daten=wechsel) if an else {},
               "tage": modelle.ALT_TAGE, "eigene": _eigen_an(cfg), "allein": allein,
               # the basis variants an own picture or music file can stand on (modelle.DATEI_ART), with their names
               "basen": dict({a: [[b, modelle.basis_variante(a, b)["name"]] for b in x[1]] for a, x in modelle.DATEI_ART.items()},
                             klein=[]),     # an own re-ranking model: one .onnx file, no basis
               # Rezept-Abgleich (stage B1b): the running language model started with other settings than its entry
               "abweichung": bool(an and buch["abweichung"] and not laeuft and cfg.get("llm", {}).get("enabled"))}
    # the bar's parts (Dominik 2026-10-18: one colored piece per model, the tiles below in the same color)
    teile = [{"id": x["id"], "name": kat[x["id"]]["name"]["en" if i else "de"], "art": x["art"], "gib": x["gib"],
              "betrieb": x["betrieb"]} for x in b["teile"]]
    return {"arten": arten, "budget": dict(b, teile=teile), "messung_zeit": messung.get("zeit"),
            "wechsel": wechsel, "geraet": hardware.text(profil, "en" if i else "de"), "starts": _starts_zeigen(buch, kat, i),
            "hf_token": buch["hf_token"], "bibliothek": _bibliothek_zeigen(buch["bibliothek"], kat, i),
            "probetag": probetag.zeigen(_probetag_an(), kat, "en" if i else "de"),
            "neu": modelleneu.zeigen(_neu_an(), "en" if i else "de"), **saetze_zeigen(kat, "en" if i else "de")}


def _bibliothek_zeigen(rows, kat, i):
    """The library for the page: each commit with the names of the entries that need it."""
    return [dict(e, namen=[(kat.get(x) or {}).get("name", {}).get("en" if i else "de", x) for x in e["ids"]]) for e in rows]


def _starts_zeigen(buch, kat, i):
    """Startprotokoll (stage B1d) for the page: per kind its name and the last starts with the model's name."""
    out = []
    for art, liste in buch["starts"].items():
        rows = [dict(e, name=(kat.get(e["id"]) or {}).get("name", {}).get("en" if i else "de", e["id"]),
                     geraet=hardware.PROFILE.get(e.get("profil"), {}).get("en" if i else "de", "")) for e in liste]
        out.append({"art": art, "name": modelle.ARTEN[art][i], "starts": rows})
    return out


def _anderswo(r, profil, i):
    """The name of the computer a measurement r was made on when that is another kind than this one, else ""."""
    wo = r.get("profil", "gb10") if r else ""
    if not wo or profil["id"] == "ohne_gpu" or wo == profil["id"] or wo not in hardware.PROFILE:
        return ""
    return hardware.PROFILE[wo]["en" if i else "de"]


def _start_zeigen(x, kat, i):
    """llmstart's row for the page (Dominik „1a“): with the names of the steps, the kind of start and the model."""
    if not x:
        return None
    m = kat.get(x["ziel"])
    return dict(x, **llmstart.zeigen(x, m["name"]["en" if i else "de"] if m else "", i))


def lage(now=None):
    """What every admin page's banner and the chat need (Dominik „2a 3a“): {start, misst}, asked at most every LAGE_S
    seconds (the model computer is not asked on every look); never blocks on its own failure."""
    now = time.monotonic() if now is None else now
    if _lage["t"] is None or now - _lage["t"] > LAGE_S:
        try:
            cfg = load_config()
            q = _quelle(cfg)
            _lage["v"] = {"start": q[7], "misst": bool(_misst() if q[5] is None else q[5])}
        except Exception:
            _lage["v"] = {"start": None, "misst": False}
        _lage["t"] = now
    return _lage["v"]


MELDE_S = 20             # seconds between two looks for a switch that ended (the notice for the admins)


async def melde_loop():
    """Dominik „5a“: when a switch of the language model ends, every admin gets one note on the iPhone, Android or the
    browser. What had already ended before the panel started is not told again."""
    vorher = (await asyncio.to_thread(lage))["start"]
    while True:
        await asyncio.sleep(MELDE_S)
        try:
            vorher = await melde_tick(vorher)
        except Exception as e:   # noqa: BLE001 - the loop goes on
            print("modelle: meldung fehler", type(e).__name__, flush=True)


async def melde_tick(vorher):
    """One look: tells the admins about a switch that ended since vorher; returns what it saw."""
    import notaus
    import push
    jetzt = (await asyncio.to_thread(lage))["start"]
    x = llmstart.fertig(vorher, jetzt)
    if not x:
        return jetzt
    cfg = load_config()
    if not _an(cfg):
        print("modelle: meldung aus", flush=True)
        return jetzt
    kat = (await asyncio.to_thread(_quelle, cfg))[3]
    title, body = llmstart.meldung(x, (kat.get(x["ziel"]) or {}).get("name", {}).get("de", ""))
    reached = 0
    for uid in notaus.admin_uids():
        if not push.reachable(uid, False):
            continue
        try:
            reached += 1 if await push.send(uid, title, body, tag="modell", private=False) else 0
        except Exception as e:   # noqa: BLE001 - one admin's device must not stop the others
            print("modelle: meldung push", type(e).__name__, flush=True)
    if reached:
        print(f"modelle: meldung gesendet | {x['ergebnis'] or 'ok'} | {reached} Admin(s)", flush=True)
    else:
        print("modelle: meldung keine Admins mit Gerät", flush=True)
    return jetzt


def echt_name(cfg, kat, i=0):
    """The catalog name of the language model that really runs: what the LLM-Tor last said its engine serves
    (llm.known_model, its "modell" field), else the one the configuration names (i: 0 German, 1 English)."""
    import llm
    m = kat.get(llm.known_model()) or modelle.rolle("llm", cfg, kat)[0]
    return m["name"][("de", "en")[i]]


def for_live(now=None):
    """For the Live view's language model box: the memory left for models and the budget's rule (numbers, fixed word),
    after the move (llm.enabled) the catalog name of the own model."""
    now = time.monotonic() if now is None else now
    if _live["t"] is None or now - _live["t"] > LIVE_EVERY:
        try:
            cfg = load_config()
            total_gib, _, laeuft, kat, _, misst, _, start, profil, _ = _quelle(cfg)
            b = modelle.budget(cfg, total_gib, kat, profil)
            _live["v"] = {"on": True, "frei": b["frei"], "regel": b["regel"]}
            if cfg.get("llm", {}).get("enabled"):   # after the move: the catalog name of the model that really runs
                _live["v"]["eigen"] = echt_name(cfg, kat)
            if _an(cfg) and (_laeuft() if laeuft is None else laeuft):   # stage E4: a switch runs (never which model)
                _live["v"]["wechsel"] = True
            if _misst() if misst is None else misst:   # a measurement runs (from the panel or the command line)
                _live["v"]["messen"] = True
            if start and not start["ende"]:          # the language model switches or starts: step n of 6 (no name)
                _live["v"]["start"] = {"n": start["n"], "von": len(llmstart.SCHRITTE), "vorgang": start["vorgang"]}
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


@router.get("/api/admin/modelle/lage", dependencies=[Depends(auth)])
def admin_lage(request: Request, lang: str = "de"):
    """The banner on every admin page (Dominik „2a“): only while the language model switches or starts, or a
    measurement runs; step and minutes, never a line from the engine."""
    guard.limit(request, "modelle", None, True)
    i = 1 if lang == "en" else 0
    d = lage()
    x = d["start"]
    if x:
        x = {k: x[k] for k in ("vorgang", "n", "dauer_s", "ende", "ergebnis", "grund")} | {
            "titel": llmstart.VORGAENGE[x["vorgang"]][i], "von": len(llmstart.SCHRITTE),
            "schritt_name": llmstart.SCHRITTE[x["n"] - 1][1 + i], "rest_min": llmstart.rest_min(x)}
    return {"start": x, "misst": d["misst"]}


@router.post("/api/admin/modelle/messen", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_messen(request: Request):
    """„Messen“: one model measured like `speech-spark modelle messen`, here or on the model computer (Dominik
    2026-10-17). The language model pauses meanwhile; the root unit speech-spark-messen-wunsch does the work."""
    guard.limit(request, "modelle_messen", None, True)
    body = await core.json_body(request, MAX_BODY)
    return await asyncio.to_thread(_messen, request, body)   # systemctl and the model computer, off the loop


def _messen(request, body):
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
        kat = _quelle(cfg)[3]                 # with the model computer's own models
        if mid in kat and kat[mid]["art"] in modelle.TAUSCH:
            modelle.probe_merken(mid, kat[mid]["art"])
            print("modelle: ausprobieren angefragt", flush=True)
        else:
            print("modelle: ausprobieren abgelehnt art", flush=True)
    guard.log("modelle_messen", detail=name)
    _live["t"] = None
    return seite(cfg, lang="en" if request.query_params.get("lang") == "en" else "de", gestartet=True)


def wunsch_ohne_seite(art, was):
    """The same wish without a page to answer (Probetag: back to the model before)."""
    _wunsch(None, art, was, seite_zeigen=False)


def _wunsch(request, art, was, mid="", seite_zeigen=True):
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
            name = modelle.wechsel_anfragen(art, was, cfg, modelle.gesamt_gib(), _starten, _laeuft())["name"]["de"]
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
    if not seite_zeigen:
        return None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de", wechselt=True)


@router.post("/api/admin/modelle/platz", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_platz(request: Request):
    """„Lange Gespräche“ (Dominik 2026-10-17): the own language model's context store as one of modelle.PLATZ; root
    (speech-spark-wechsel) restarts it with the new memory share and context, here or on the model computer."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    return await asyncio.to_thread(_platz, request, str(body.get("platz", ""))[:16])   # off the loop (systemctl)


def _platz(request, was):
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
            modelle.platz_anfragen(was, cfg, modelle.gesamt_gib(), _starten, _laeuft())
        except modelle.Fehler as e:
            if str(e) == "start":
                print("modelle: platz start fehler", flush=True)
                raise HTTPException(503, GRUND["start"])
            _fehler(e, "platz")
    print("modelle: platz angefragt", flush=True)
    guard.log("modelle_wechsel", detail=f"Lange Gespräche: {modelle.PLATZ_NAMEN[was][0]}")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de", wechselt=True)


@router.post("/api/admin/modelle/neustart", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_neustart(request: Request):
    """Rezept-Abgleich (stage B1b, alzeo idea 1): „Neu starten“ when the language model runs with other settings than
    its catalog entry gives now; root (speech-spark-wechsel) checks that again and restarts it, here or there."""
    guard.limit(request, "modelle_wechsel", None, True)
    await core.json_body(request, MAX_BODY)
    return await asyncio.to_thread(_neustart, request)   # off the loop (systemctl)


def _neustart(request):
    if not _an():
        print("modelle: neustart abgelehnt aus", flush=True)
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    cfg = load_config()
    if steuer.remote(cfg):
        d = steuer.call("neustart", (), cfg=cfg, timeout=30)
        if not isinstance(d, dict):
            _fehler("rechner", "neustart")
        if d.get("ok") is not True:
            _neustart_fehler(d.get("fehler") if d.get("fehler") in NEUSTART_GRUND else "wunsch")
    else:
        if _misst():
            _fehler("misst", "neustart")
        try:
            modelle.neustart_anfragen(cfg, _starten, _laeuft())
        except modelle.Fehler as e:
            if str(e) == "start":
                print("modelle: neustart start fehler", flush=True)
                raise HTTPException(503, GRUND["start"])
            _neustart_fehler(str(e))
    print("modelle: neustart angefragt", flush=True)
    guard.log("modelle_wechsel", detail="Neustart mit den Einstellungen aus dem Katalog")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de", wechselt=True)


def _neustart_fehler(word):
    if word == "schon":
        print("modelle: neustart abgelehnt schon", flush=True)
        raise HTTPException(409, "Das Sprachmodell läuft schon so, wie es im Katalog steht.")
    _fehler(word, "neustart")


@router.post("/api/admin/modelle/wechseln", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_wechseln(request: Request):
    """Wechseln: one model of the catalog for its kind (stage E4)."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    art, mid = str(body.get("art", ""))[:16], str(body.get("id", ""))[:48]
    if art == "klein":       # the re-ranking model: a setting of this computer, no root and no model computer
        return await asyncio.to_thread(_klein_wechsel, request, mid)
    return await asyncio.to_thread(_wunsch, request, art, mid)


def _klein_wechsel(request, mid):
    """Wechseln for the re-ranking model: chat.rerank_model to its size or own id, saved like the settings page; an own
    one passes modelle.KLEIN_PROBE at its first start, else the small checked one works (nachsortieren.py)."""
    if not _an():
        print("modelle: wechsel abgelehnt aus", flush=True)
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    cfg = load_config()
    try:
        m = modelle.klein_pruefen(mid, cfg)
    except modelle.Fehler as e:
        _fehler(e)
    admin.chat_setzen(request, "rerank_model", m["variante"], f"Nachsortieren: {m['name']['de']}")
    print("modelle: wechsel klein angefragt", flush=True)
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de")   # systemctl and the model computer, off the loop


@router.post("/api/admin/modelle/entladen", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_entladen(request: Request):
    """„Entladen“ in the Spark-Konsole: Einbetten or Nachsortieren off again (root's speech-spark-wechsel)."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    return await asyncio.to_thread(_entladen, request, str(body.get("art", ""))[:16])


def _entladen(request, art):
    cfg = load_config()
    if not konsole.aktiv() or steuer.remote(cfg):
        print("modelle: entladen abgelehnt art", flush=True)
        raise HTTPException(400, GRUND["art"])
    if _misst():
        _fehler("misst", "entladen")
    try:
        name = modelle.aus_anfragen(art, cfg, _starten, _laeuft())["name"]["de"]
    except modelle.Fehler as e:
        if str(e) == "start":
            print("modelle: entladen start fehler", flush=True)
            raise HTTPException(503, GRUND["start"])
        _fehler(e, "entladen")
    print(f"modelle: entladen {art} angefragt", flush=True)
    guard.log("modelle_wechsel", detail=f"{modelle.ARTEN[art][0]} entladen: {name}")
    _live["t"] = None
    return seite(lang="en" if request.query_params.get("lang") == "en" else "de", wechselt=True)


@router.post("/api/admin/modelle/zurueck", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_zurueck(request: Request):
    """Zurückholen: the model before the last switch of this kind, within 7 days."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    art = str(body.get("art", ""))[:16]
    if art not in modelle.TAUSCH:
        print("modelle: zurueck abgelehnt art", flush=True)
        raise HTTPException(400, GRUND["art"])
    return await asyncio.to_thread(_wunsch, request, art, "zurueck")


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
async def _vorschlag(body, art, repo, rev, total_gib, mit_token):
    """The own entry the fixed rules make of one commit: a picture or music file (DATEI_ART: the named .gguf file on a
    basis variant), a speech model (its program's family) or a language or picture-understanding model; a helper,
    embedding or re-ranking model only in the Spark-Konsole of a Spark alone."""
    if art in modelle.ALLEIN_ARTEN and not (konsole.aktiv() and spark_allein(load_config())):
        raise modelle.Fehler("art")
    if art == "klein":            # an own re-ranking model: the named .onnx file (runs on this computer's CPU)
        return modelle.klein_vorschlag(await _hf_info(repo, rev), repo, str(body.get("datei", ""))[:200], await _familien(art))
    if art in modelle.DATEI_ART:
        return modelle.datei_vorschlag(await _hf_info(repo, rev), art, repo, str(body.get("datei", ""))[:200],
                                       str(body.get("basis", ""))[:16], total_gib, mit_token)
    return modelle.eigen_vorschlag(await _hf_info(repo, rev), art, repo, total_gib, mit_token, await _familien(art))


async def _familien(art, kat=None):
    """The families (modelle.familie) of the checked models of a speech kind's program (or the checked re-rankers), from their pinned commits'
    metadata; () for the other kinds. An own speech model must be one of them (modelle.SPRACH)."""
    refs = modelle.SPRACH[art][1] if art in modelle.SPRACH else modelle.KLEIN_ROLLE["nachsortieren"] if art == "klein" else ()
    if not refs:
        return ()
    kat = await asyncio.to_thread(modelle.katalog) if kat is None else kat
    out = []
    for ref in refs:
        m = kat.get(ref)
        if m and m["revision"]:
            f = modelle.familie((await _hf_info(m["repo"], m["revision"])).get("config"))
            if f and f not in out:
                out.append(f)
    return tuple(out)


async def _hf_info(repo, rev=""):
    """The metadata of one commit (or the newest) from Hugging Face: with the models on another computer that one asks
    with its token (Wärter hf_info, the token never leaves it), here through netguard (public internet only) with the
    token of this computer when one is set."""
    if not modelle.REPO.match(repo) or ".." in repo or not (rev == "" or modelle.REV.match(rev)):
        raise modelle.Fehler("repo")
    cfg = load_config()
    if steuer.remote(cfg):
        d = await asyncio.to_thread(steuer.call, "hf_info", (repo, rev) if rev else (repo,), cfg, 30)
        if not isinstance(d, dict):
            raise modelle.Fehler("rechner")
        if d.get("ok") is not True or not isinstance(d.get("info"), dict):
            raise modelle.Fehler(d.get("fehler") if d.get("fehler") in ("repo", "zugang", "antwort", "netz") else "antwort")
        return d["info"]
    import httpx
    url = modelle.HF_API.format(repo=repo, rev=rev or "main")
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=modelle.HF_INFO_MAX, timeout=20, follow_redirects=False,
                                   headers=hftoken.kopf(url)) as c:
            r = await c.get(url)
    except (httpx.HTTPError, OSError, ValueError):
        raise modelle.Fehler("netz")
    if r.status_code == 401 and hftoken.token():
        hftoken.abgelehnt()
    if r.status_code in (401, 403):
        raise modelle.Fehler("zugang")
    if r.status_code != 200:
        raise modelle.Fehler("antwort")
    try:
        return r.json()
    except ValueError:
        raise modelle.Fehler("antwort")


# ---------------------------------------------------------------- the admin's Hugging Face token (stage B1c)
HFTOKEN_BODY = 512


def _hf_token_info(cfg=None):
    """{gesetzt, seit, abgelehnt} of the computer the models run on; never the token."""
    cfg = load_config() if cfg is None else cfg
    if steuer.remote(cfg):
        return _hf_token_pruefen((steuer.modelle(cfg) or {}).get("hf_token"))
    return hftoken.info()


def _hf_token_pruefen(d):
    """What the model computer said about its token, in the shape hftoken.info gives; anything else: none set."""
    ok = isinstance(d, dict) and d.get("gesetzt") is True
    seit = d.get("seit") if ok and isinstance(d.get("seit"), int) and not isinstance(d.get("seit"), bool) else None
    return {"gesetzt": ok, "seit": seit, "abgelehnt": ok and d.get("abgelehnt") is True}


@router.put("/api/admin/modelle/hftoken", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def hf_token_setzen(request: Request):
    """Zustand → Modelle → „Mehr“ „Hugging-Face-Token“ (Dominik 2026-11-16): kept only on the computer the models run
    on, with a fresh admin code; the answer says only whether one is set."""
    guard.limit(request, "modelle_eigen", None, True)
    t = str((await core.json_body(request, HFTOKEN_BODY)).get("token") or "").strip()
    if not hftoken.TOKEN.fullmatch(t):
        print("modelle: hf-token abgelehnt form", flush=True)
        raise HTTPException(400, "Das ist kein Hugging-Face-Token (er beginnt mit hf_).")
    cfg = load_config()
    if steuer.remote(cfg):
        d = await asyncio.to_thread(steuer.call, "hf_token", (), cfg, 15, {"token": t})
        if not isinstance(d, dict) or d.get("ok") is not True:
            print("modelle: hf-token abgelehnt rechner", flush=True)
            raise HTTPException(503, GRUND["rechner"])
    else:
        hftoken.speichern(t)
    print("modelle: hf-token gesetzt", flush=True)
    guard.log("modelle_eigen", detail="Hugging-Face-Token gesetzt")
    _live["t"] = None
    return await asyncio.to_thread(_hf_token_info, cfg)


@router.delete("/api/admin/modelle/hftoken", dependencies=[Depends(auth), Depends(admin_code)])
def hf_token_loeschen(request: Request):
    guard.limit(request, "modelle_eigen", None, True)
    cfg = load_config()
    if steuer.remote(cfg):
        d = steuer.call("hf_token_weg", (), cfg, 15)
        if not isinstance(d, dict) or d.get("ok") is not True:
            print("modelle: hf-token weg rechner", flush=True)
            raise HTTPException(503, GRUND["rechner"])
    else:
        hftoken.weg()
    print("modelle: hf-token geloescht", flush=True)
    guard.log("modelle_eigen", detail="Hugging-Face-Token gelöscht")
    _live["t"] = None
    return _hf_token_info(cfg)


# „Nur laden“ / „Nur herunterladen“ (stage B1c): the answers the model computer may give
LADEN_GRUND = {"laeuft": GRUND["laeuft"], "misst": GRUND["misst"], "start": GRUND["start"], "rechner": GRUND["rechner"],
               "unbekannt": GRUND["unbekannt"], "repo": GRUND["repo"], "antwort": GRUND["antwort"], "netz": GRUND["netz"],
               "zugang": "Das Modell ist privat, oder es braucht eine Freigabe: dann den Hugging-Face-Token eintragen und "
                         "den Bedingungen auf Hugging Face zustimmen.",
               "format": "Keine Gewichte in einer erlaubten Form (safetensors, GGUF, ONNX); Pickle und Python-Code nimmt der Spark nie.",
               "platte": "Zu wenig Platz auf der Platte (mindestens 20 GB bleiben frei).",
               "schon": "Dieser Stand liegt schon auf der Platte oder steht im Katalog.", "voll": "Schon 40 heruntergeladene Modelle."}


def _laden_fehler(word, was):
    word = word if word in LADEN_GRUND else "rechner"
    print(f"modelle: {was} abgelehnt {word}", flush=True)
    raise HTTPException({"laeuft": 409, "misst": 409, "schon": 409, "start": 503, "rechner": 503, "netz": 503,
                         "unbekannt": 404}.get(word, 400), LADEN_GRUND[word])


@router.post("/api/admin/modelle/laden", dependencies=[Depends(auth), Depends(admin_code)])
async def laden(request: Request):
    """„Nur laden“ (alzeo idea 3): a catalog or own model fetched and checked while the current one keeps running."""
    guard.limit(request, "modelle_wechsel", None, True)
    mid = str((await core.json_body(request, MAX_BODY)).get("id", ""))[:48]
    if not _an():
        print("modelle: laden abgelehnt aus", flush=True)
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    if not modelle.ID.match(mid):
        _laden_fehler("unbekannt", "laden")
    cfg = load_config()
    if steuer.remote(cfg):
        d = await asyncio.to_thread(steuer.call, "laden", (mid,), cfg, 30)
        if not isinstance(d, dict) or d.get("ok") is not True:
            _laden_fehler(d.get("fehler") if isinstance(d, dict) else "rechner", "laden")
    else:
        if await asyncio.to_thread(_misst):
            _laden_fehler("misst", "laden")
        try:
            await asyncio.to_thread(modelle.laden_anfragen, mid, _starten, await asyncio.to_thread(_laeuft))
        except modelle.Fehler as e:
            _laden_fehler(str(e), "laden")
    print("modelle: laden angefragt", flush=True)
    guard.log("modelle_wechsel", detail="Nur laden: " + mid)
    _live["t"] = None
    return await asyncio.to_thread(seite, None, None, None, "en" if request.query_params.get("lang") == "en" else "de", False, True)


@router.post("/api/admin/modelle/herunterladen", dependencies=[Depends(auth), Depends(admin_code)])
async def herunterladen(request: Request):
    """„Nur herunterladen“ (Dominik 2026-11-16 „alles mögliche gedownloaded“): any public model, or one with an approval
    and the token, on a pinned commit, only the allowed file kinds, when it fits the disk; nothing runs it."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    body = await core.json_body(request, EIGEN_BODY)
    repo, rev = str(body.get("repo", "")).strip()[:200], str(body.get("revision", "")).strip()[:40]
    if not modelle.REPO.match(repo) or ".." in repo or not (rev == "" or modelle.REV.match(rev)):
        _laden_fehler("repo", "herunterladen")
    cfg = load_config()
    if steuer.remote(cfg):
        d = await asyncio.to_thread(steuer.call, "herunterladen", (repo, rev) if rev else (repo,), cfg, 40)
        if not isinstance(d, dict) or d.get("ok") is not True:
            _laden_fehler(d.get("fehler") if isinstance(d, dict) else "rechner", "herunterladen")
    else:
        if await asyncio.to_thread(_misst):
            _laden_fehler("misst", "herunterladen")
        try:
            try:
                info = await asyncio.to_thread(hftoken.metadaten, repo, rev)
            except ValueError as e:
                raise modelle.Fehler(str(e))
            laeuft = await asyncio.to_thread(_laeuft)
            await asyncio.to_thread(modelle.herunterladen_anfragen, repo, rev, info, _starten, laeuft,
                                    bool(hftoken.token()))
        except modelle.Fehler as e:
            _laden_fehler(str(e), "herunterladen")
    print("modelle: herunterladen angefragt", flush=True)
    guard.log("modelle_eigen", detail="Nur herunterladen: " + repo)
    _live["t"] = None
    return await asyncio.to_thread(seite, None, None, None, "en" if request.query_params.get("lang") == "en" else "de", False, True)


@router.delete("/api/admin/modelle/bibliothek", dependencies=[Depends(auth), Depends(admin_code)])
async def bibliothek_weg(request: Request):
    """Modell-Bibliothek „Löschen“ (stage B1c): one commit no catalog or own entry names, after the admin confirmed;
    the computer the models run on checks that again."""
    guard.limit(request, "modelle_eigen", None, True)
    body = await core.json_body(request, MAX_BODY)
    repo, rev = str(body.get("repo", "")).strip()[:200], str(body.get("revision", ""))[:40]
    cfg = load_config()
    try:
        if not modelle.REPO.match(repo) or ".." in repo or not modelle.REV.match(rev):
            raise modelle.Fehler("repo")
        if steuer.remote(cfg):
            d = await asyncio.to_thread(steuer.call, "lose_weg", (repo, rev), cfg, 120)
            if not isinstance(d, dict):
                raise modelle.Fehler("rechner")
            if d.get("ok") is not True:
                raise modelle.Fehler(d.get("fehler") if d.get("fehler") in BIBLIOTHEK_GRUND else "rechner")
        else:
            await asyncio.to_thread(modelle.lose_weg, repo, rev, cfg)
    except modelle.Fehler as e:
        word = str(e) if str(e) in BIBLIOTHEK_GRUND else "repo"
        print(f"modelle: bibliothek abgelehnt {word}", flush=True)
        raise HTTPException({"gebraucht": 409, "fehlt": 404, "rechner": 503}.get(word, 400), BIBLIOTHEK_GRUND[word])
    except OSError:
        print("modelle: bibliothek dateien fehler", flush=True)
        raise HTTPException(500, GRUND["dateien"])
    print("modelle: bibliothek geloescht", flush=True)
    guard.log("modelle_eigen", detail="Modell-Bibliothek: ein loser Stand gelöscht")
    _live["t"] = None
    return await asyncio.to_thread(seite, lang="en" if request.query_params.get("lang") == "en" else "de")


def _eigen_tor(request):
    if not _eigen_an():
        print("modelle: eigenes abgelehnt aus", flush=True)
        raise HTTPException(409, "Eigene Modelle sind aus (Funktionen → Modelle wechseln → Eigene Modelle).")


def _zeige(m):
    """What „Prüfen“ shows; a speech model or an own file has no picture understanding and no tools."""
    return dict({k: m[k] for k in ("id", "art", "name", "repo", "revision", "lizenz", "gewerblich", "platte_gb", "need_gib")},
                kann_sehen=bool(m.get("kann_sehen")), werkzeuge=bool(m.get("werkzeuge")),
                **({"datei": m["datei"]["path"], "basis": m["basis"]} if m.get("datei") else {}))


def _raum(cfg, art, q):
    """The room for a model of art beside the others that run: the budget's free memory plus what art's own models
    take now (the new one would replace them)."""
    if art not in modelle.ARTEN:
        return None
    b = modelle.budget(cfg, q[0], q[3], q[8])
    return round(b["frei"] + sum(x["gib"] for x in b["teile"] if x["art"] == art), 1)


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
        cfg = load_config()
        q = await asyncio.to_thread(_quelle, cfg)
        tok = q[9]["hf_token"]
        treffer = modelle.such_treffer(items, art, q[0], q[3], q[8], _raum(cfg, art, q), tok["gesetzt"] and not tok["abgelehnt"],
                                       await _familien(art, q[3]))
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
    total_gib = (await asyncio.to_thread(_quelle, load_config()))[0]
    try:
        m = await _vorschlag(body, art, repo, "", total_gib, (await asyncio.to_thread(_hf_token_info))["gesetzt"])
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
    total_gib = (await asyncio.to_thread(_quelle, cfg))[0]
    try:
        if not modelle.REV.match(rev):
            raise modelle.Fehler("repo")
        m = await _vorschlag(body, art, repo, rev, total_gib, (await asyncio.to_thread(_hf_token_info, cfg))["gesetzt"])
        if m["revision"] != rev:
            raise modelle.Fehler("antwort")
        if steuer.remote(cfg) and art != "klein":   # the model computer keeps the list and checks the entry again
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
    return await asyncio.to_thread(seite, lang="en" if request.query_params.get("lang") == "en" else "de")


@router.put("/api/admin/modelle/eigen/{mid}/rezept", dependencies=[Depends(auth), Depends(admin_code)])
async def eigen_rezept(request: Request, mid: str):
    """Rezept-Editor (Dominik 2026-11-16 „1-6“, stage B1): an own model's engine settings from fixed ranges and words;
    the model computer checks every field again (modelle.eigen_aendern) and drops the old measurement."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    felder = await core.json_body(request, EIGEN_BODY)
    cfg = load_config()
    try:
        if not modelle.ID.match(mid) or not isinstance(felder, dict):
            raise modelle.Fehler("unbekannt" if not modelle.ID.match(mid) else "felder")
        if steuer.remote(cfg):
            d = steuer.call("eigen_rezept", (mid,), cfg=cfg, daten=felder, timeout=15)
            if not isinstance(d, dict) or d.get("ok") is not True:
                raise modelle.Fehler(d.get("fehler") if isinstance(d, dict) and d.get("fehler") in REZEPT_WOERTER else "rechner")
        else:
            await asyncio.to_thread(modelle.eigen_aendern, mid, felder, modelle.gesamt_gib(), cfg)
    except modelle.Fehler as e:
        word = str(e) if str(e) in REZEPT_WOERTER else "eigen"
        print(f"modelle: rezept abgelehnt {word}", flush=True)
        status = {"unbekannt": 404, "rechner": 503, "aktiv": 409, "schon": 409}.get(word, 400)
        raise HTTPException(status, REZEPT_GRUND.get(word) or GRUND.get(word)
                            or ("Wert außerhalb des erlaubten Bereichs: " + word))
    print("modelle: rezept gespeichert", flush=True)
    guard.log("modelle_eigen", detail=f"Rezept geändert: {mid}")
    _live["t"] = None
    return await asyncio.to_thread(seite, lang="en" if request.query_params.get("lang") == "en" else "de")


@router.get("/api/admin/modelle/eigen/{mid}/katalogzeile", dependencies=[Depends(auth)])
async def eigen_katalogzeile(request: Request, mid: str):
    """„In den Katalog übernehmen“ (stage B1): the own entry as a ready line for modelle.json, nothing is changed."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    q = await asyncio.to_thread(_quelle, load_config())
    m = q[3].get(mid) if modelle.ID.match(mid) else None
    try:
        if m is None:
            raise modelle.Fehler("unbekannt")
        zeile = modelle.katalog_zeile(m, q[1] or {})
    except modelle.Fehler as e:
        print(f"modelle: katalogzeile abgelehnt {e}", flush=True)
        raise HTTPException(404 if str(e) == "unbekannt" else 400, GRUND.get(str(e), "ungültig"))
    print("modelle: katalogzeile gezeigt", flush=True)
    return {"zeile": zeile}


@router.delete("/api/admin/modelle/eigen/{mid}", dependencies=[Depends(auth), Depends(admin_code)])
def eigen_weg(request: Request, mid: str):
    """Löschen: an own model off the list and its files off the disk; never one that runs or can still come back."""
    guard.limit(request, "modelle_eigen", None, True)
    _eigen_tor(request)
    cfg = load_config()
    try:
        if not modelle.ID.match(mid):
            raise modelle.Fehler("unbekannt")
        hier = any(x.get("id") == mid for x in modelle.eigene_eintraege("klein"))    # a re-ranking model is this computer's
        if steuer.remote(cfg) and not hier:   # the list and the files are the model computer's
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


# ---------------------------------------------------------------- Modellsätze (stage B2)
SATZ_GRUND = {"name": "Name: 1 bis 40 Buchstaben, Ziffern, Leerzeichen, Punkt, Komma, Strich.",
              "leer": "Gerade läuft kein Modell, das ein Satz behalten könnte.",
              "voll": f"Höchstens {modelle.SATZ_MAX} Sätze; erst einen löschen.",
              "unbekannt": "Diesen Satz gibt es nicht.", "laeuft": "Ein anderer Satz wird gerade eingestellt.",
              "nichts": "Alle Modelle dieses Satzes laufen schon."}


def _satz_fehler(e, was):
    word = str(e) if str(e) in SATZ_GRUND else "unbekannt"
    print(f"modelle: satz {was} abgelehnt {word}", flush=True)
    raise HTTPException(404 if word == "unbekannt" else 409 if word in ("laeuft", "nichts", "voll") else 400, SATZ_GRUND[word])


def saetze_zeigen(kat, lang="de"):
    """The kept sets with the names of their models, and the set being brought back (what is still open)."""
    i = "en" if lang == "en" else "de"
    lauf = read_json(modelle.SATZ_LAUF, {}) or {}

    def name(x):
        return ((kat.get(x) or {}).get("name") or {}).get(i, x)
    return {"saetze": [{"name": s["name"], "modelle": [[a, name(m)] for a, m in s["modelle"].items()]}
                       for s in modelle.saetze()],
            "lauf": {"name": lauf.get("name", ""), "offen": len(lauf.get("offen") or [])} if lauf.get("name") else None,
            "max": modelle.SATZ_MAX}


@router.post("/api/admin/modelle/saetze", dependencies=[Depends(auth), Depends(admin_code)])
async def satz_dazu(request: Request):
    """„Als Satz behalten“: the models running now under a name."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    if not _an():
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    cfg = load_config()
    try:
        kat = (await asyncio.to_thread(_quelle, cfg))[3]
        await asyncio.to_thread(modelle.satz_speichern, body.get("name"), modelle.satz_jetzt(cfg, kat))
    except modelle.Fehler as e:
        _satz_fehler(e, "speichern")
    print("modelle: satz gespeichert", flush=True)
    guard.log("modelle_wechsel", detail="Modellsatz gespeichert")
    return await asyncio.to_thread(seite, lang="en" if request.query_params.get("lang") == "en" else "de")


@router.delete("/api/admin/modelle/saetze", dependencies=[Depends(auth), Depends(admin_code)])
async def satz_weg(request: Request):
    guard.limit(request, "modelle_wechsel", None, True)
    name = str(request.query_params.get("name", ""))[:40]
    try:
        await asyncio.to_thread(modelle.satz_loeschen, name)
    except modelle.Fehler as e:
        _satz_fehler(e, "loeschen")
    print("modelle: satz geloescht", flush=True)
    guard.log("modelle_wechsel", detail="Modellsatz gelöscht")
    return await asyncio.to_thread(seite, lang="en" if request.query_params.get("lang") == "en" else "de")


@router.post("/api/admin/modelle/saetze/anwenden", dependencies=[Depends(auth), Depends(admin_code)])
async def satz_anwenden(request: Request):
    """„Einstellen“: the switches the set needs, one after the other (satz_schritt, once a minute)."""
    guard.limit(request, "modelle_wechsel", None, True)
    body = await core.json_body(request, MAX_BODY)
    if not _an():
        raise HTTPException(409, "Modelle wechseln ist aus (Funktionen → Modelle wechseln).")
    name = str(body.get("name", ""))[:40]
    cfg = load_config()
    try:
        if (read_json(modelle.SATZ_LAUF, {}) or {}).get("name"):
            raise modelle.Fehler("laeuft")
        kat = (await asyncio.to_thread(_quelle, cfg))[3]
        offen = await asyncio.to_thread(modelle.satz_offen, name, cfg, kat)
        if not offen:
            raise modelle.Fehler("nichts")
    except modelle.Fehler as e:
        _satz_fehler(e, "anwenden")
    write_json(modelle.SATZ_LAUF, {"name": name, "offen": offen, "zeit": int(time.time())}, indent=1)
    print(f"modelle: satz anwenden {len(offen)}", flush=True)
    guard.log("modelle_wechsel", detail=f"Modellsatz einstellen: {len(offen)} Wechsel")
    await asyncio.to_thread(satz_schritt)
    return await asyncio.to_thread(seite, lang="en" if request.query_params.get("lang") == "en" else "de")


_probetag_task = None
_neu_task = None


def probetag_schritt(now=None):
    """Once a minute (panel.every_minute): Probetag nach dem Wechsel (probetag.py) with this page's parts: the switch,
    the fixed quality test, the wait for the model and „Zurückholen“ as the way back. Returns probetag.schritt's word."""
    global _probetag_task
    cfg = load_config()
    laeuft = bool(_probetag_task and not _probetag_task.done()) or quality.running()
    wort = probetag.schritt(cfg, time.time() if now is None else now, _probetag_an(cfg), laeuft)
    if wort == "start":
        d = probetag.stand()
        _probetag_task = asyncio.get_running_loop().create_task(probetag.lauf(
            d["gesehen"], d.get("alt", ""), _probetag_an, lambda: health.ready(load_config(), minutes=5),
            lambda: quality.run("probetag"), quality.history, lambda: wunsch_ohne_seite("llm", "zurueck")))
    return wort


async def _neu_holen(herausgeber):
    """Neu verfügbar: one publisher's public list through netguard (public internet, no token), None on an error."""
    import httpx
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=modelle.SUCHE_ANTWORT_MAX, timeout=20,
                                   follow_redirects=False) as c:
            r = await c.get(modelle.neu_url(herausgeber))
    except (httpx.HTTPError, OSError, ValueError):
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def neu_schritt(now=None):
    """Once a minute (panel.every_minute): Neu verfügbar (modelleneu.py), the daily look in its own task when due."""
    global _neu_task
    if (_neu_task and not _neu_task.done()) or not modelleneu.faellig(_neu_an(), now):
        return ""
    _neu_task = asyncio.get_running_loop().create_task(modelleneu.lauf(_neu_holen, _quelle, _familien))
    return "start"


def satz_schritt():
    """Once a minute (panel.every_minute) while a set is being brought back: asks for its next switch. A switch or
    measurement still running waits for the next minute; a refused one is left out with its word in the log."""
    lauf = read_json(modelle.SATZ_LAUF, {}) or {}
    offen = lauf.get("offen") or []
    if not lauf.get("name"):
        return ""
    if not offen or not _an():
        _satz_ende("fertig" if not offen else "aus")
        return "ende"
    art, mid = offen[0]
    try:
        _wunsch(None, art, mid, seite_zeigen=False)
        wort = "angefragt"
    except HTTPException as e:
        if e.status_code == 409 and e.detail in (GRUND.get("laeuft"), GRUND.get("misst")):
            return "wartet"
        wort = "uebersprungen"
    rest = offen[1:]
    if rest:
        write_json(modelle.SATZ_LAUF, dict(lauf, offen=rest), indent=1)
    else:
        _satz_ende("fertig")
    print(f"modelle: satz {art} {wort}", flush=True)
    return wort


def _satz_ende(wort):
    try:
        os.remove(modelle.SATZ_LAUF)
    except FileNotFoundError:
        pass
    print(f"modelle: satz {wort}", flush=True)
