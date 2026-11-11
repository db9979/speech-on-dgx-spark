"""Eigene Stimmen gestalten (Dominik 2026-11-11, plan eigene-stimme/plan.md, picks 1b, 2a with 20 voices, 3a, 4, 5, A).

The voice a profile answers with may be one of 20 fixed voices or one it designs itself. Both are made once with
VoiceDesign as a short sample of a fixed sentence and then kept: the speech output's Base engine (tts.klon_enabled,
tts_proxy role "klon") clones the sample for every answer, so the voice sounds the same in every sentence and costs no
more time than a named one. VoiceDesign itself runs only while voices are made (tts.voicedesign_leerlauf_min).

What decides (fixed rules of the panel, never a model):
- The 20 voices are the panel's own text (stimmdesign.json "fertig": id, names de/en, gender, age, kind, English
  description). They are made once in the background after the admin's release (fertige_anstossen: vorrang
  "Stimmen gestalten", stage „hinten“, one at a time, never while somebody speaks), each with its fixed seed.
- An own voice comes only from fixed fields (stimmdesign.json "felder": gender, age, pitch, pace, up to two kinds),
  each a word of the panel's list; the person's own words („Eigene Worte“, at most WORTE_MAX characters, only letters,
  spaces, commas and dots) go after them as data, never as an instruction of their own (beschreibung).
- „Probe“: the sample of the fixed sentence through VoiceDesign with a fresh seed („Neu würfeln“), PROBEN_TAG per
  profile and day (never for a profile without daily limits, coadmin.unbegrenzt). The last probe stays in memory for
  PROBE_S seconds; „Übernehmen“ keeps exactly that one, never audio a device sends.
- At most MAX_EIGENE own voices per profile. Its name on the speech output is "eigen-" and 16 random hex digits
  (stimmablage.NAME): nobody finds another profile's voice by its name, and the profile's name never goes there. The
  copy on the panel (users/<id>/stimmen/) plays „▶“ and puts the sample back when the speech output lost it.
- A designed voice counts only while the function is allowed for the profile and the voice is a fixed one or its own
  (stimme_ok, profiles.VOICE_CHECK): else the speech output's standard voice speaks.

The samples go to the speech output's voices folder through stimmablage.py: directly when it runs on this computer,
else signed through the Wärter (steuer.call "stimme_ablegen", "stimme_weg", "stimmen"). Every result writes one line
"stimmdesign: …" with fixed words and numbers, never a description, a name or the person's words.
"""
import asyncio
import io
import json
import os
import re
import secrets
import time
import wave

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import coadmin
import features
import guard
import profiles
import stimmablage
from common import STATE
from core import VOICES_DIR, assistant, browser_profile, json_body, own_profile

router = APIRouter()
KEY = "stimmdesign"
QUELLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stimmdesign.json")
FERTIG_DIR = os.path.join(STATE, "stimmdesign")       # the 20 fixed voices' samples (the panel's copy)
EIGENE = "stimmen.json"                                # users/<id>/: the own voices (id, name, fields, words, time)
EIGENE_DIR = "stimmen"                                 # users/<id>/stimmen/<id>.wav: their samples
MAX_EIGENE = 3
PROBEN_TAG = 10
PROBE_S = 900              # seconds the last probe can still be kept
NAME_MAX = 30
WORTE_MAX = 120
WORTE = re.compile(r"[A-Za-zÄÖÜäöüß ,.]{0,%d}" % WORTE_MAX)
NAME = re.compile(r"[A-Za-zÄÖÜäöüß0-9 .\-]{1,%d}" % NAME_MAX)
TON_FRIST = 120            # seconds one sample may take (VoiceDesign may be loading)
TON_GRENZE = 4 * 1024 * 1024
LADEN_WARTEN = (20, 15)    # the 20 fixed voices: seconds to wait while VoiceDesign loads, and how often
_daten = {}
_proben = {}               # uid -> (time, wav, fields, words)
_lauf = {"task": None, "fertig": 0, "fehler": 0, "zustand": "", "t": 0.0}


def daten():
    """stimmdesign.json (read once)."""
    if not _daten:
        with open(QUELLE, encoding="utf-8") as f:
            _daten.update(json.load(f))
    return _daten


def check_daten(d):
    """Mistakes in stimmdesign.json (test): 20 fixed voices with unique ids, both names, gender, age and kind of the
    lists, descriptions only of letters, spaces, commas and dots; every field with labels in both languages and a
    fixed English word; the sentence in both languages."""
    err = []
    xs = d.get("fertig") or []
    if len(xs) != 20 or len({x[0] for x in xs}) != len(xs):
        err.append("fertig")
    for x in xs:
        if not (isinstance(x, list) and len(x) == 7 and stimmablage.NAME.fullmatch("sd-" + str(x[0]))
                and all(isinstance(t, str) and 3 <= len(t) <= 40 for t in x[1:3]) and x[3] in ("w", "m", "n")
                and isinstance(x[4], int) and 15 <= x[4] <= 90 and x[5] in ("ruhig", "lebhaft", "erzaehler")
                and re.fullmatch(r"[A-Za-z ,.]{20,200}", x[6])):
            err.append(f"fertig.{x[0] if isinstance(x, list) and x else '?'}")
    for k in ("geschlecht", "alter", "tonlage", "tempo", "art"):
        for y in (d.get("felder") or {}).get(k) or [None]:
            if not (isinstance(y, list) and len(y) == 4 and re.fullmatch(r"[a-z]{1,12}", str(y[0]))
                    and all(isinstance(t, str) and t for t in y[1:3]) and re.fullmatch(r"[a-z ,]{3,40}", str(y[3]))):
                err.append(f"felder.{k}")
    for lang in ("de", "en"):
        if not stimmablage.WORTE.fullmatch(str((d.get("satz") or {}).get(lang, ""))):
            err.append(f"satz.{lang}")
    return err


def fertige():
    """[(name, de, en, gender, age, kind, description)] of the 20 fixed voices; name = "sd-<id>"."""
    return [("sd-" + x[0], *x[1:]) for x in daten()["fertig"]]


def beschreibung(felder, worte=""):
    """The English description VoiceDesign gets for the fields (each a word of the panel's list) and the person's own
    words (only as data, behind the fixed part). ValueError("felder"/"worte") for anything else."""
    f = daten()["felder"]
    felder = felder if isinstance(felder, dict) else {}

    def wort(k):
        hit = next((y[3] for y in f[k] if y[0] == felder.get(k)), None)
        if hit is None:
            raise ValueError("felder")
        return hit
    arten = felder.get("art") if isinstance(felder.get("art"), list) else []
    if not 1 <= len(arten) <= 2 or len(set(arten)) != len(arten):
        raise ValueError("felder")
    art = " and ".join(next((y[3] for y in f["art"] if y[0] == a), "") for a in arten)
    if not all(any(y[0] == a for y in f["art"]) for a in arten):
        raise ValueError("felder")
    worte = str(worte or "").strip()
    if not WORTE.fullmatch(worte):
        raise ValueError("worte")
    out = f"A {art} {wort('geschlecht')} voice, {wort('alter')}, {wort('tonlage')}, {wort('tempo')}"
    return out + (f". In the person's own words: {worte}" if worte else "") + "."


def satz(sprache="de"):
    return daten()["satz"]["en" if sprache == "en" else "de"]


# ---------------------------------------------------------------- the own voices of a profile
def eigene(uid):
    d = profiles.read_own(uid, EIGENE, {})
    xs = d.get("stimmen") if isinstance(d, dict) else None
    return [x for x in (xs or []) if isinstance(x, dict) and stimmablage.NAME.fullmatch(str(x.get("id", "")))
            and str(x["id"]).startswith("eigen-")][:MAX_EIGENE]


def _speichern(uid, xs, proben=None):
    d = profiles.read_own(uid, EIGENE, {})
    d = d if isinstance(d, dict) else {}
    d["stimmen"] = xs
    if proben is not None:
        d["proben"] = proben
    profiles.write_own(uid, EIGENE, d)


def proben_heute(uid, add=0):
    day = time.strftime("%Y-%m-%d")
    d = profiles.read_own(uid, EIGENE, {})
    p = d.get("proben") if isinstance(d, dict) else None
    n = p.get("n", 0) if isinstance(p, dict) and p.get("tag") == day else 0
    if add:
        n += add
        _speichern(uid, eigene(uid), {"tag": day, "n": n})
    return n


def _wav_pfad(uid, vid):
    return profiles._path(uid, EIGENE_DIR, vid + ".wav")


def stimme_ok(uid, voice):
    """Whether this profile may speak with this voice: anything but a designed one, or a designed one while the
    function is allowed and it is one of the 20 or its own (profiles.VOICE_CHECK)."""
    v = str(voice or "")
    if not v.startswith(("sd-", "eigen-")):
        return True
    if not uid or not features.allowed(KEY, uid):
        return False
    if v.startswith("sd-"):
        return any(x[0] == v for x in fertige())
    return any(x["id"] == v for x in eigene(uid))


profiles.VOICE_CHECK.append(stimme_ok)


# ---------------------------------------------------------------- the speech output's voices folder
def _hier():
    import steuer
    return not steuer.remote()


def _ablegen(name, wav, worte):
    """The sample to the speech output (this computer or its Wärter); True when it is there."""
    if _hier():
        try:
            return stimmablage.ablegen(VOICES_DIR, name, wav, worte)
        except (ValueError, OSError):
            return False
    import base64
    import steuer
    r = steuer.call("stimme_ablegen", daten={"name": name, "wav": base64.b64encode(wav).decode(), "worte": worte},
                    timeout=30)
    return bool(r and r.get("ok"))


def _weg(name):
    if _hier():
        try:
            return stimmablage.weg(VOICES_DIR, name) or True
        except (ValueError, OSError):
            return False
    import steuer
    r = steuer.call("stimme_weg", (name,))
    return bool(r and r.get("ok"))


def _namen_dort():
    """The designed voices the speech output has, None when it does not answer."""
    if _hier():
        return stimmablage.namen(VOICES_DIR)
    import steuer
    r = steuer.call("stimmen")
    return r.get("namen") if isinstance(r, dict) and isinstance(r.get("namen"), list) else None


RESTE_MOST = 10            # leftover own voices taken off the speech output per look at most
_nimmt = {}                # uid -> the id being taken over right now (one „Übernehmen“ per profile at a time)


def reste_weg(dort):
    """Own voices the speech output still has but no profile owns (its deletion did not reach the model computer,
    or the profile is gone): taken off there, at most RESTE_MOST per look; never one being taken over right now.
    A voice sample is a person's data and must not stay behind. Returns how many went."""
    if not dort:
        return 0
    meine = {x["id"] for uid in profiles.user_ids() for x in eigene(uid)} | set(_nimmt.values())
    n = 0
    for name in sorted(x for x in dort if isinstance(x, str) and x.startswith("eigen-") and x not in meine)[:RESTE_MOST]:
        ok = stimmablage.NAME.fullmatch(name) and _weg(name)
        n += bool(ok)
        print(f"stimmdesign: rest geloescht {'ok' if ok else 'fehler'}", flush=True)
    return n


# ---------------------------------------------------------------- making a sample
def _wav(raw):
    """A WAV of what the speech output sent (PCM or WAV), checked like the speech output checks it."""
    import hoerstueck
    pcm, rate = hoerstueck.pcm_of(raw)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    out = buf.getvalue()
    stimmablage.pruefe_wav(out)
    return out


async def _design_an():
    import admin
    v = await admin.tts_voices()
    return v.get("voicedesign") is True, v.get("klon")


async def _ton(text, klang, seed, stufe=""):
    import tonteile
    raw = await tonteile.sprich(text, klang=klang, stufe=stufe, frist=TON_FRIST, grenze=TON_GRENZE, sprache="German",
                                seed=seed)
    return _wav(raw)


def fertig_da():
    """Names of the fixed voices whose sample the panel keeps."""
    try:
        return {"sd-" + f[:-4] for f in os.listdir(FERTIG_DIR) if f.endswith(".wav")}
    except OSError:
        return set()


async def _fertige_machen():
    """The background run: every fixed voice without a sample, one after the other, and every kept one the speech
    output lost goes back. Waits while VoiceDesign loads; stops at the first other failure."""
    import vorrang
    _lauf.update(fertig=0, fehler=0, zustand="laeuft", t=time.time())
    os.makedirs(FERTIG_DIR, mode=0o700, exist_ok=True)
    dort = await asyncio.to_thread(_namen_dort)
    for i, (name, _, _, _, _, _, klang) in enumerate(fertige()):
        pfad = os.path.join(FERTIG_DIR, name[3:] + ".wav")
        if name in fertig_da():
            if dort is not None and name not in dort:
                with open(pfad, "rb") as f:
                    ok = await asyncio.to_thread(_ablegen, name, f.read(), satz())
                print(f"stimmdesign: fertige zurueckgelegt {'ok' if ok else 'fehler'}", flush=True)
            continue
        for _ in range(LADEN_WARTEN[1]):
            try:
                wav = await vorrang.run("Stimmen gestalten", lambda: _ton(satz(), klang, 1000 + i, "hinten"), retries=1)
                break
            except RuntimeError as e:
                if "loading" not in str(e):
                    raise
                _lauf["zustand"] = "laedt"
                await asyncio.sleep(LADEN_WARTEN[0])
        else:
            raise RuntimeError("tts loading")
        _lauf["zustand"] = "laeuft"
        with open(pfad + ".neu", "wb") as f:
            f.write(wav)
        os.replace(pfad + ".neu", pfad)
        ok = await asyncio.to_thread(_ablegen, name, wav, satz())
        _lauf["fertig" if ok else "fehler"] += 1
        print(f"stimmdesign: fertige stimme {'ok' if ok else 'fehler ablage'}", flush=True)


async def _fertige_lauf():
    try:
        await _fertige_machen()
        _lauf["zustand"] = "fertig"
        print(f"stimmdesign: fertige lauf ok | {_lauf['fertig']} neu | {_lauf['fehler']} fehler", flush=True)
    except Exception as e:   # noqa: BLE001  (busy, gone or loading too long: said with a fixed word, tried again later)
        _lauf["zustand"] = "fehler"
        print(f"stimmdesign: fertige lauf fehler | {type(e).__name__}", flush=True)
    finally:
        _lauf["t"] = time.time()


LAUF_NEU_S = 900           # a failed run is tried again at the earliest after this many seconds


def fertige_anstossen(design):
    """Starts the background run when samples are missing, VoiceDesign is there and no run is on (or failed lately)."""
    t = _lauf["task"]
    if not design or (t is not None and not t.done()) or len(fertig_da()) >= len(fertige()) \
            or (_lauf["zustand"] == "fehler" and time.time() - _lauf["t"] < LAUF_NEU_S):
        return False
    import core
    _lauf["task"] = core.spawn(_fertige_lauf(), name="stimmdesign")
    print("stimmdesign: fertige lauf start", flush=True)
    return True


def waehlbar(uid):
    """[(id, name)] of the designed voices this profile can choose now (the fixed ones with a sample, its own ones);
    [] while the function is not allowed. For the voice list of the apps (account.assistant_voices)."""
    if not uid or not features.allowed(KEY, uid):
        return []
    da = fertig_da()
    return ([(n, de) for n, de, *_ in fertige() if n in da]
            + [(x["id"], str(x.get("name", "")) or "Eigene Stimme") for x in eigene(uid)])


def for_live():
    """For the Live page: how many fixed voices are ready and whether the run works (numbers and words only)."""
    return {"on": features.admin_on(KEY), "fertig": len(fertig_da()), "von": len(daten()["fertig"]),
            "zustand": _lauf["zustand"] or "ruht", "proben": len(_proben)}


# ---------------------------------------------------------------- routes
def _prof(prof):
    if not features.allowed(KEY, prof["id"]):
        raise HTTPException(403, features.missing_text(KEY, prof["id"]) or "Eigene Stimmen gestalten ist aus.")
    return prof


@router.get("/api/stimmdesign", dependencies=[Depends(assistant)])
async def uebersicht(request: Request, prof=Depends(own_profile)):
    """Everything Ich → Gespräch → Stimme shows: the 20 fixed voices (ready or not), the own ones, the fields, the
    chosen voice, the probes of today and whether VoiceDesign and the engine of the own voices run."""
    uid = _prof(prof)["id"]
    guard.limit(request, "stimmdesign", uid)
    design, klon = await _design_an()
    fertige_anstossen(design)
    da = fertig_da()
    f = daten()["felder"]
    xs = eigene(uid)
    dort = await asyncio.to_thread(_namen_dort)
    await asyncio.to_thread(reste_weg, dort)
    for x in xs:    # the speech output lost an own voice (new install): its copy goes back
        if dort is not None and x["id"] not in dort and os.path.exists(_wav_pfad(uid, x["id"])):
            with open(_wav_pfad(uid, x["id"]), "rb") as fh:
                ok = await asyncio.to_thread(_ablegen, x["id"], fh.read(), satz())
            print(f"stimmdesign: eigene zurueckgelegt {'ok' if ok else 'fehler'} fuer {profiles.log_name(prof)}", flush=True)
    return {"fertig": [{"id": n, "de": de, "en": en, "g": g, "alter": a, "art": k, "da": n in da}
                       for n, de, en, g, a, k, _ in fertige()],
            "eigene": [{"id": x["id"], "name": x.get("name", ""), "felder": x.get("felder", {}), "worte": x.get("worte", ""),
                        "t": x.get("t", 0)} for x in xs],
            "felder": {k: [[y[0], y[1], y[2]] for y in v] for k, v in f.items()},
            "wahl": profiles.voice_for(uid), "max": MAX_EIGENE,
            "proben": proben_heute(uid), "proben_max": PROBEN_TAG, "frei": coadmin.unbegrenzt(uid, request),
            "design": design, "klon": klon, "lauf": for_live()}


def _ton_antwort(wav):
    return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.get("/api/stimmdesign/hoeren/{name}", dependencies=[Depends(assistant)])
def hoeren(name: str, request: Request, prof=Depends(own_profile)):
    """„▶“: the kept sample of a fixed voice or of one of the profile's own voices."""
    uid = _prof(prof)["id"]
    guard.limit(request, "stimmdesign", uid)
    if name.startswith("sd-") and stimmablage.NAME.fullmatch(name) and name in fertig_da():
        pfad = os.path.join(FERTIG_DIR, name[3:] + ".wav")
    elif any(x["id"] == name for x in eigene(uid)):
        pfad = _wav_pfad(uid, name)
    else:
        raise HTTPException(404, "keine solche Stimme")
    try:
        with open(pfad, "rb") as f:
            return _ton_antwort(f.read())
    except OSError:
        raise HTTPException(404, "keine solche Stimme")


@router.post("/api/stimmdesign/probe", dependencies=[Depends(assistant)])
async def probe(request: Request, prof=Depends(browser_profile)):
    """„▶ Probe“ / „Neu würfeln“: the fixed sentence in a voice from the fields and the own words, with a fresh seed."""
    uid = _prof(prof)["id"]
    guard.limit(request, "stimmprobe", uid)
    body = await json_body(request, 4 * 1024)
    try:
        klang = beschreibung(body.get("felder"), body.get("worte", ""))
    except ValueError as e:
        print(f"stimmdesign: probe abgelehnt {e} fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, "Bitte die Felder aus der Liste wählen; eigene Worte nur mit Buchstaben, Komma und Punkt.")
    frei = coadmin.unbegrenzt(uid, request)
    if not frei and proben_heute(uid) >= PROBEN_TAG:
        print(f"stimmdesign: probe abgelehnt tageslimit fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(429, f"Heute schon {PROBEN_TAG} Proben. Morgen geht es weiter.")
    design, _ = await _design_an()
    if not design:
        print(f"stimmdesign: probe abgelehnt voicedesign fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(409, "VoiceDesign ist aus: Einstellungen → Sprachausgabe → „VoiceDesign zusätzlich bereitstellen“.")
    try:
        wav = await _ton(satz(), klang, secrets.randbelow(2 ** 31))
    except RuntimeError as e:
        if "loading" in str(e):
            print(f"stimmdesign: probe wartet laedt fuer {profiles.log_name(prof)}", flush=True)
            raise HTTPException(503, "VoiceDesign wird geladen …", headers={"Retry-After": "15"})
        print(f"stimmdesign: probe fehler {type(e).__name__} fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(503, "Die Sprachausgabe ist gerade belegt oder fehlt; gleich noch einmal.")
    except ValueError:   # too short or too long for a sample (stimmablage.MIN_S … MAX_S)
        print(f"stimmdesign: probe fehler laenge fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(503, "Die Probe ist misslungen; bitte noch einmal würfeln.")
    except Exception as e:   # noqa: BLE001  (gone: said in words, never the error's text)
        print(f"stimmdesign: probe fehler {type(e).__name__} fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(503, "Die Sprachausgabe ist gerade belegt oder fehlt; gleich noch einmal.")
    proben_heute(uid, 1)
    _proben[uid] = (time.time(), wav, body.get("felder"), str(body.get("worte", "")).strip())
    for k in [k for k, v in _proben.items() if time.time() - v[0] > PROBE_S]:
        _proben.pop(k, None)
    print(f"stimmdesign: probe ok fuer {profiles.log_name(prof)}", flush=True)
    return _ton_antwort(wav)


@router.post("/api/stimmdesign/eigene", dependencies=[Depends(assistant)])
async def uebernehmen(request: Request, prof=Depends(browser_profile)):
    """„Übernehmen“: the profile's last probe (never audio sent along) becomes an own voice and its voice."""
    uid = _prof(prof)["id"]
    guard.limit(request, "stimmdesign", uid)
    body = await json_body(request, 1024)
    name = str(body.get("name", "")).strip()
    if not NAME.fullmatch(name):
        print(f"stimmdesign: uebernehmen abgelehnt name fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, f"Ein Name mit höchstens {NAME_MAX} Zeichen, nur Buchstaben, Ziffern, Punkt und Strich.")
    p = _proben.get(uid)
    if not p or time.time() - p[0] > PROBE_S:
        print(f"stimmdesign: uebernehmen abgelehnt keine probe fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(409, "Erst eine Probe anhören, dann übernehmen.")
    xs = eigene(uid)
    if len(xs) >= MAX_EIGENE:
        print(f"stimmdesign: uebernehmen abgelehnt voll fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(409, f"Schon {MAX_EIGENE} eigene Stimmen. Lösche zuerst eine.")
    if uid in _nimmt:      # a second „Übernehmen“ while the first still stores: both read the same list (a fourth voice)
        print(f"stimmdesign: uebernehmen abgelehnt laeuft fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(409, "Die Stimme wird gerade übernommen.")
    vid = "eigen-" + secrets.token_hex(8)
    _nimmt[uid] = vid
    try:
        pfad = _wav_pfad(uid, vid)
        os.makedirs(os.path.dirname(pfad), mode=0o700, exist_ok=True)
        with open(pfad + ".neu", "wb") as f:
            f.write(p[1])
        os.replace(pfad + ".neu", pfad)
        if not await asyncio.to_thread(_ablegen, vid, p[1], satz()):
            os.remove(pfad)
            print(f"stimmdesign: uebernehmen fehler ablage fuer {profiles.log_name(prof)}", flush=True)
            raise HTTPException(503, "Die Sprachausgabe hat die Stimme nicht angenommen; gleich noch einmal.")
        xs = eigene(uid)
        xs.append({"id": vid, "name": name, "felder": p[2], "worte": p[3], "t": int(time.time())})
        _speichern(uid, xs)
    finally:
        _nimmt.pop(uid, None)
    _proben.pop(uid, None)
    profiles.save_settings(uid, {"voice": vid})
    print(f"stimmdesign: uebernommen fuer {profiles.log_name(prof)}", flush=True)
    return {"id": vid, "eigene": len(xs)}


def _loeschen(uid, vid):
    xs = eigene(uid)
    if not any(x["id"] == vid for x in xs):
        return False
    if not _weg(vid):      # the model computer did not answer: the sample goes with the next look (reste_weg)
        print("stimmdesign: loeschen ablage fehler", flush=True)
    try:
        os.remove(_wav_pfad(uid, vid))
    except OSError:
        pass
    _speichern(uid, [x for x in xs if x["id"] != vid])
    if profiles.settings(uid).get("voice") == vid:
        profiles.save_settings(uid, {"voice": ""})
    return True


@router.delete("/api/stimmdesign/eigene/{vid}", dependencies=[Depends(assistant)])
def loeschen(vid: str, request: Request, prof=Depends(browser_profile)):
    """Deletes one own voice (also while the function is locked: own data can always go)."""
    guard.limit(request, "stimmdesign", prof["id"])
    if not _loeschen(prof["id"], vid):
        print(f"stimmdesign: nicht geloescht unbekannt fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "keine solche Stimme")
    print(f"stimmdesign: geloescht 1 fuer {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


# ---------------------------------------------------------------- Ich → Daten löschen
def _own_count(uid):
    return len(eigene(uid))


def alle_weg(uid):
    """Every own voice of the profile, on the speech output too (features.OWN "stimmdesign")."""
    n = 0
    for x in eigene(uid):
        n += _loeschen(uid, x["id"])
    profiles.drop_own(uid, EIGENE)
    print(f"stimmdesign: geloescht {n} | daten loeschen", flush=True)


features.OWN[KEY] = (_own_count, alle_weg)
