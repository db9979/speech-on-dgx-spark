"""Admin pages: status, configuration, services, logs, tests, cloned voices, benchmark, profiles and devices."""
import asyncio
import json
import os
import re
import io
import sys
import threading
import time
import zipfile

import httpx
import psutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backup  # noqa: E402
import undo  # noqa: E402
import echo  # noqa: E402
import stille  # noqa: E402
import fremdstimme  # noqa: E402
import satzende  # noqa: E402
import guard  # noqa: E402
import llm  # noqa: E402
import kiwix  # noqa: E402
import health  # noqa: E402
import coadmin  # noqa: E402
import features  # noqa: E402
import mfa  # noqa: E402
import speakers  # noqa: E402
import wyoming  # noqa: E402
import telefon  # noqa: E402
import profiles  # noqa: E402
from common import (CONFIG_PATH, MODEL_CHOICE, MODEL_ID, estimate_gib, load_config, model_local, model_url, qwen38_lanes,  # noqa: E402
                    write_json)
import modelle  # noqa: E402
from core import (  # noqa: E402
    json_body,
    spawn,
    ASR_ENGINE_KEYS,
    ADMIN_IDLE,
    COOKIE,
    DEFAULTS,
    FACES,
    DESIGN_KEYS,
    ENGINE_KEYS,
    LANGS,
    LOG_UNITS,
    SERVICES,
    UNITS,
    VOICES_DIR,
    _session_token,
    admin_cookie_ok,
    acting_profile,
    admin_code,
    admin_code_fresh,
    api_headers,
    assistant,
    auth,
    main_auth,
    check_password,
    password_set,
    store_password)
from monitor import history, service_health, system_stats  # noqa: E402
import rechnerblick  # noqa: E402
import rundlauf  # noqa: E402
import steuer  # noqa: E402
from steuer import unit_state  # noqa: E402
from chat import web_search  # noqa: E402

router = APIRouter()


@router.get("/api/audit", dependencies=[Depends(auth)])
def audit(limit: int = 300):
    """The change log: logins, failed logins, lockouts and every change, newest first."""
    names = {u: (profiles.by_id(u) or {}).get("name") for u in profiles.user_ids()}
    return {"events": guard.read(max(1, min(limit, 2000))), "names": names}


@router.get("/api/audit/check", dependencies=[Depends(main_auth)])
async def audit_check(request: Request, nas: int = 0):
    """„Protokoll prüfen“: the change log's chain (guard.verify) and, with nas=1, the newest sealed copy on the NAS
    against it (offsite.compare_audit). Numbers and file names only."""
    guard.limit(request, "offsite", admin=True)
    res = await asyncio.to_thread(guard.verify)
    out = {"chain": res, "nas": None, "nas_error": ""}
    if nas:
        import offsite
        import zertpin
        try:
            out["nas"] = await offsite.compare_audit()
        except Exception as e:   # noqa: BLE001 - shown as a fixed word, the chain result stands on its own
            out["nas_error"] = "zertifikat" if zertpin.problem(e) else type(e).__name__
        print(f"audit: check | chain {'ok' if res['ok'] else 'broken'} | nas "
              f"{'none' if out['nas'] is None else out['nas']['missing']} missing", flush=True)
    else:
        print(f"audit: check | chain {'ok' if res['ok'] else 'broken'}", flush=True)
    return out


@router.get("/api/admin/wyoming/suggest", dependencies=[Depends(auth)])
async def wyoming_suggest():
    """Addresses to allow for Wyoming: from the Home Assistant URLs of the profiles and from refused knocks."""
    return await asyncio.to_thread(wyoming.suggest)


def _profile_extra(uid):
    import roomlive
    import onboard
    return {"mfa": mfa.enabled(uid), "room": roomlive.count(uid),
            "role": coadmin.role(uid), "setup": onboard.summary(uid)}


@router.get("/api/admin/profiles", dependencies=[Depends(auth)])
def admin_profiles(q: str = "", show: str = "", sort: str = "name", page: int = 0, per: int = 0):
    """One page of the profiles (search, filter, sort; per 0: all of them, for the setup wizard)."""
    d = profiles.admin_list(q[:40], show, sort, page, per or None, extra=_profile_extra)
    import esp32
    import roomlive
    spk, listening = esp32.speaker_ids(), roomlive.devices_listening()
    for x in d["devices"]:
        x["speaker"] = x["id"] in spk   # managed under Ich → Lautsprecher of its profile
        x["room"] = x["id"] in listening   # in room mode right now (roomlive.py)
    for u in d["users"]:
        u.setdefault("room", roomlive.count(u["id"]))
    d["guests"] = features.guests()   # the row "Gäste" above the profiles
    return d


@router.post("/api/admin/profiles", dependencies=[Depends(auth)])
async def admin_add_profile(request: Request):
    body = await request.json()
    name, pin = body.get("name", ""), body.get("pin", "")
    if not profiles.valid_name(name):
        raise HTTPException(400, "name: 1 to 40 characters")
    if not profiles.valid_pin(pin):
        raise HTTPException(400, "PIN: 4 to 64 characters without spaces")
    try:
        uid = profiles.add_user(name, pin)
    except ValueError as e:
        raise HTTPException(409, str(e))
    import onboard
    onboard.save_state(uid, fresh=True)   # "Los geht's" opens at the first sign-in, as after an invitation (code check D6)
    return {"id": uid}


def _no_admin_profile(request, *uids):
    """An admin profile (coadmin.py) changes another admin profile's PIN, second step, devices or deletes it only
    with the role Admin, never its own here (that is Ich → Sicherheit) and never the main one's (Haupt-Admin):
    so nobody locks the main admin out. A Verwalter never changes an admin profile."""
    me = acting_profile(request)
    main = coadmin.main_uid()
    if me and any(u and coadmin.role(u) and (me["role"] != "admin" or u == me["id"] or u == main) for u in uids):
        raise HTTPException(403, "Dieses Admin-Profil ändert nur der Haupt-Admin oder das Panel-Passwort.")


def _device_owner(did):
    return next((x.get("user") for x in profiles._load()["devices"] if x["id"] == did), None)


@router.put("/api/admin/profiles/{uid}", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_set_pin(uid: str, request: Request):
    _no_admin_profile(request, uid)
    pin = (await request.json()).get("pin", "")
    if not profiles.valid_pin(pin):
        raise HTTPException(400, "PIN: 4 to 64 characters without spaces")
    if not profiles.set_pin(uid, pin):
        raise HTTPException(404, "no such profile")
    return {"ok": True}


@router.delete("/api/admin/profiles/{uid}/mfa", dependencies=[Depends(auth), Depends(admin_code_fresh)])
def admin_reset_mfa(uid: str, request: Request):
    """For a profile that lost its phone and its recovery codes: the second step is off again."""
    _no_admin_profile(request, uid)
    if uid not in profiles.user_ids():
        raise HTTPException(404, "no such profile")
    mfa.disable(uid)
    guard.log("profile_mfa_reset", ip=guard.client_ip(request), uid=uid)
    return {"ok": True}


@router.get("/api/admin/profiles/{uid}", dependencies=[Depends(auth)])
def admin_profile(uid: str, request: Request):
    """One profile in detail (Personen und Geräte, plan "Vereinheitlichen" Phase 5): access (PIN, second step,
    role, browsers), devices, how many functions are on, and its rights (agent, Spark update, upload space).
    A Verwalter sees no rights block: those pages are not his."""
    u = next((x for x in profiles.names() if x["id"] == uid), None)
    if not u:
        raise HTTPException(404, "no such profile")
    last = profiles.seen()
    import esp32
    spk = esp32.speaker_ids()
    import roomlive
    listening = roomlive.devices_listening()
    devs = [dict(x, speaker=x["id"] in spk, room=x["id"] in listening) for x in profiles.own_devices(uid)]
    on, of = features.count(uid)
    me = acting_profile(request)
    out = dict(u, **_profile_extra(uid), last=profiles.last_use(uid, last), devices=devs,
               facts=len(profiles.memory(uid)), sessions=profiles.sessions(uid), trusted=mfa.list_trusted(uid),
               features={"on": on, "of": of}, main=not me or me["role"] == "admin", owner=not me)
    if not me or coadmin.role(me["id"]) != "manager":
        out["rights"] = _rights(uid)
    return out


def _rights(uid):
    import agent
    import appupdate
    import wissen
    import documents
    import stufe
    lv = agent.admin_state().get("levels", {}).get(uid, "")
    docs = features.chat_cfg().get("documents", True) is not False
    return {"agent": {"spark": agent.admin_on(), "level": lv}, "vorrang": stufe.rights(uid),
            "update": dict(appupdate.rights(uid), spark=appupdate.admin_on()),
            "quota": {"spark": docs, "mb": wissen.quota_bytes(uid) // 1024**2, "own": uid in wissen._quotas(),
                      "default_mb": wissen.quota_bytes("") // 1024**2,
                      "used": documents.usage_total(uid) if os.path.exists(documents.db_path(uid)) else 0}}


@router.delete("/api/admin/profiles/{uid}/sessions/{sid}", dependencies=[Depends(auth)])
def admin_end_session(uid: str, sid: str, request: Request):
    """Ends one signed-in browser of a profile (protective, so no code; a profile with a role only by the main admin)."""
    _no_admin_profile(request, uid)
    if not re.fullmatch(r"[0-9a-f]{16}", sid) or not profiles.end_session(uid, sid):
        raise HTTPException(404, "no such login")
    guard.log("profile_session_end", ip=guard.client_ip(request), uid=uid, by="admin")
    return {"ok": True}


@router.delete("/api/admin/profiles/{uid}/trusted/{tid}", dependencies=[Depends(auth)])
def admin_untrust(uid: str, tid: str, request: Request):
    """This trusted browser of a profile has to enter a code again (protective, so no code)."""
    _no_admin_profile(request, uid)
    if not re.fullmatch(r"[0-9a-f]{16}", tid) or uid not in profiles.user_ids() or not mfa.remove_trusted(uid, tid):
        raise HTTPException(404, "no such browser")
    guard.log("trusted_browser_removed", ip=guard.client_ip(request), uid=uid, by="admin")
    return {"ok": True}


@router.put("/api/admin/profiles/{uid}/call", dependencies=[Depends(auth)])
async def admin_set_call(uid: str, request: Request):
    """The Rufname others use in messages ("Thomas M."): unique among every name and Rufname."""
    _no_admin_profile(request, uid)
    call = str((await json_body(request, 1024)).get("call") or "")
    try:
        return {"call": profiles.set_call(uid, call)}
    except LookupError:
        raise HTTPException(404, "no such profile")
    except ValueError as e:
        raise HTTPException(409 if "used" in str(e) else 400, str(e))


@router.delete("/api/admin/profiles/{uid}", dependencies=[Depends(auth), Depends(admin_code)])
def admin_delete_profile(uid: str, request: Request):
    """Deleting cannot be undone (memory, conversations, devices): a fresh code, like a new PIN."""
    _no_admin_profile(request, uid)
    profiles.delete_user(uid)
    coadmin.forget(uid)
    import join
    join.forget(uid)
    import pruefzugang
    pruefzugang.forget(uid)   # its review accesses for Apple
    import tipps
    tipps.forget(uid)   # its hints and counts (tipps.json)
    import chats
    chats.forget(uid)   # out of every chat, its messages gone (their place stays for the others)
    import chatsec
    chatsec.forget(uid)   # its device keys for private chats
    import verbund
    verbund.forget(uid)   # its contacts on other Sparks, its address, what still waited to go out from it
    import anrufe
    anrufe.forget(uid)    # its calls end
    import rufen
    rufen.forget(uid)     # a call the assistant still kept for it (Anrufe per Assistent)
    telefon.forget(uid)   # its handsets are no longer assigned
    import sparkkalender
    sparkkalender.drop_profile(uid)   # its Spark calendars went with the profile folder
    return {"ok": True}


@router.post("/api/admin/devices", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_add_device(request: Request):
    body = await request.json()
    _no_admin_profile(request, str(body.get("user", "")))
    if not profiles.valid_name(body.get("name", "")):
        raise HTTPException(400, "name: 1 to 40 characters")
    try:
        return {"token": profiles.add_device(body["name"], str(body.get("user", "")))}
    except ValueError as e:
        raise HTTPException(400, str(e))


# Device keys a profile paired itself (scope): the admin cannot move them to another profile, only delete them.
FIXED_KINDS = {
    "app": "Ein iPhone gehört zum Profil, das es gekoppelt hat. Dort entfernen und neu koppeln.",
    "watch": "Eine Pebble-Uhr gehört zum Profil, das sie gekoppelt hat. Dort entfernen und neu koppeln.",
    "room": "Der Home-Assistant-Schlüssel gehört zum Profil, das ihn erzeugt hat. Dort einen neuen erzeugen.",
    "tui": "Ein Terminal gehört zum Profil, das es gekoppelt hat. Dort unter Ich → Terminal entfernen und neu koppeln.",
}


@router.put("/api/admin/devices/{did}", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_set_device(did: str, request: Request):
    body = await request.json()
    _no_admin_profile(request, _device_owner(did), str(body.get("user", "")))
    import esp32
    if did in esp32.speaker_ids():
        # a speaker stays with the profile that set it up (its board, voice print and room settings are kept there)
        raise HTTPException(400, "Ein Lautsprecher gehört zum Profil, das ihn eingerichtet hat. Dort entfernen und neu einrichten.")
    kind = next((x.get("kind") for x in profiles.admin_list()["devices"] if x["id"] == did), "")
    if kind in FIXED_KINDS:
        # iPhone app, Pebble watch, terminal and Home Assistant room key were paired by the profile itself: they stay there
        raise HTTPException(400, FIXED_KINDS[kind])
    if not profiles.set_device_user(did, str(body.get("user", ""))):
        raise HTTPException(404, "no such device or profile")
    return {"ok": True}


@router.delete("/api/admin/devices/{did}", dependencies=[Depends(auth)])
def admin_delete_device(did: str, request: Request):
    _no_admin_profile(request, _device_owner(did))
    profiles.delete_device(did)
    return {"ok": True}


@router.post("/api/password", dependencies=[Depends(main_auth), Depends(admin_code_fresh)])
async def change_password(request: Request):
    body = await request.json()
    new = str(body.get("new", ""))
    if len(new) < 10:
        raise HTTPException(400, "the new password needs at least 10 characters")
    guard.check(request, guard.ADMIN)
    if password_set() and not await asyncio.to_thread(check_password, str(body.get("old", ""))):
        guard.failed(request, guard.ADMIN, what="admin_password")
        await asyncio.sleep(1)
        raise HTTPException(401, "current password is wrong")
    await asyncio.to_thread(store_password, new)
    r = Response('{"ok": true}', media_type="application/json")
    r.set_cookie(COOKIE, _session_token(), max_age=ADMIN_IDLE, httponly=True, samesite="strict")
    guard.log("admin_password_changed", ip=guard.client_ip(request))
    return r


@router.get("/api/status", dependencies=[Depends(auth)])
async def status():
    """Zustand. The health checks run together, everything that calls systemctl, nvidia-smi or reads /proc
    in a worker thread (V01.0.405: these calls held the event loop, every 3 seconds per open Zustand tab)."""
    cfg = load_config()
    healths = await asyncio.gather(*(service_health(name, cfg) for name in SERVICES))
    return await asyncio.to_thread(_status, cfg, dict(zip(SERVICES, healths)))


# Which qwen38 lanes exist (and their pool share) changes only when qwen38 is reinstalled: looked up once in 5 minutes
LANES_EVERY = 300
_lanes = {"t": None, "units": []}


def _qwen38_lanes():
    now = time.monotonic()
    if _lanes["t"] is None or now - _lanes["t"] > LANES_EVERY:
        # models on another computer: its lanes count only in its own budget (Zustand → Modelle, through the Wärter)
        _lanes["units"] = qwen38_lanes() if model_local() else []
        _lanes["t"] = now
    return _lanes["units"]


def _status(cfg, healths):
    services = {}
    for name, unit in SERVICES.items():
        services[name] = {"unit": unit, "state": unit_state(unit), "enabled": cfg[name]["enabled"],
                          "port": cfg[name]["port"], "estimate_gib": estimate_gib(cfg[name]["model"]),
                          "health": healths.get(name)}
    sysd = system_stats()
    # the engines' shares are of the memory of the computer they run on: with the models on tars the Pi's 8 GB read as
    # "geschätzt ~2.2 GiB" while the TTS engine reserved ~11.8 (2026-10-16); None (no estimate) while tars does not answer
    total_gib = sysd["mem_total_gib"] if sysd.get("mem_von") == "modell-rechner" else psutil.virtual_memory().total / 2**30

    def share(frac):
        return round(frac * total_gib + 1.5, 1) if total_gib else None
    a = cfg["asr"]
    if a.get("recognizer") == "parakeet":
        services["asr"]["estimate_gib"] = modelle.eintrag("parakeet-primeline")["need_gib"]  # CPU model, no engine
    elif a.get("backend") == "vllm":
        gib = share(a["engine_mem"])
        services["asr"]["backend"] = "vllm"
        services["asr"]["estimate_gib"] = gib
        services["asr"]["engines"] = [
            {"name": "asr-engine", "kind": "vLLM", "unit": UNITS["asr-engine"], "state": unit_state(UNITS["asr-engine"]),
             "model": a["model"], "port": a["engine_port"], "estimate_gib": gib}]
    t = cfg["tts"]
    if t.get("backend") == "vllm-omni":
        per_engine = share(t["engine_mem_talker"] + t["engine_mem_code2wav"])
        services["tts"]["backend"] = "vllm-omni"
        services["tts"]["estimate_gib"] = per_engine and round(per_engine * (2 if t.get("voicedesign_enabled") else 1), 1)
        services["tts"]["engines"] = [
            {"name": "tts-engine", "kind": "vllm-omni", "unit": UNITS["tts-engine"], "state": unit_state(UNITS["tts-engine"]),
             "model": t["model"], "port": t["engine_port"], "estimate_gib": per_engine}]
        if t.get("voicedesign_enabled") or unit_state(UNITS["tts-design"]) != "inactive":
            services["tts"]["engines"].append(
                {"name": "tts-design", "kind": "vllm-omni", "unit": UNITS["tts-design"], "state": unit_state(UNITS["tts-design"]),
                 "model": t["voicedesign_model"], "port": t["voicedesign_port"], "estimate_gib": per_engine})
    qwen38 = [{"unit": u, "state": unit_state(u), "mem_fraction": frac} for u, frac in _qwen38_lanes()]
    return {"time": time.time(), "system": sysd, "gpu": steuer.gpu(),
            "services": services, "qwen38": qwen38, "history": list(history),
            "alerts": health.alerts(), "watchdog": health.events[-10:], "glance": glance(cfg),
            "rechner": rechnerblick.fuer_status(),   # both computers when the models run apart (Zustand → Überblick → Rechner)
            "rundlauf": rundlauf.fuer_status()}      # the last round trip through the models (Zustand → Überblick → Rundlauf)


def glance(cfg):
    """Zustand in plain words (plan „Bedienung gesamt“ C3, V01.0.286): version, last backup, the last live check
    (does the language model answer?) and the "Heute" tiles; "slower" is latency's fixed rule (clearly slower than the
    week), which colours the first-sound tile; "hours" are the answers per hour for the bars. Only times and counts, never
    what was said."""
    import aktiv
    import latency
    import vorrang
    from core import app_version
    live = health.last_live() or {}
    llm = next((x for x in live.get("steps") or [] if x.get("name") == "llm"), None)
    last = backup.listing()
    lat = latency.summary()
    day = lat["day"] or {}
    out = {"version": app_version(), "backup": last[0]["created"] if last else None,
           "check": {"time": live.get("t"), "llm": None if llm is None else bool(llm.get("ok")),
                     "seconds": llm.get("seconds") if llm else None},
           "answers": day.get("n", 0), "first_sound": day.get("median"), "slower": lat["warn"] is not None,
           "hours": lat["hours"],
           "background": vorrang.today(), "aktiv": aktiv.zahlen()}
    if features.admin_on("esp32", cfg.get("chat", {})):
        import esp32
        out["speakers"] = {"known": len(esp32.clients()), "online": len(esp32._live)}
    return out


@router.get("/api/admin/prompt", dependencies=[Depends(auth)])
def prompt_preview():
    """The prompt as the model gets it (parts in order) and the shipped system prompt for "Standard"."""
    import chat
    with open(DEFAULTS) as f:
        default = json.load(f)["chat"]
    ccfg = dict(default, **load_config().get("chat", {}))
    return {"parts": chat.prompt_parts(ccfg), "default": default["system_prompt"]}


# The models the configured LLM server offers, for the choice under Einstellungen -> Sprachmodell. The request
# goes only to the stored address (never one from the request: no way to make the panel call elsewhere), with
# the stored key, no redirects, 5 seconds and 256 KB at most; at most 50 names of up to 200 plain characters.
# Not through netguard: that refuses this machine's ports 30000-31099, where qwen38 lives. Kept 60 seconds.
LLM_MODELS_TTL, LLM_MODELS_MAX, LLM_MODELS_BYTES = 60, 50, 256 * 1024
_llm_list = {}                    # url -> (time, models)
_MODEL_ID = re.compile(r"^[\w.:/@+-]{1,200}$")


async def _fetch_llm_models(url, key):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as c:
        async with c.stream("GET", url + "/models", headers=headers) as r:
            if r.status_code in (401, 403):
                raise ValueError("Der Server lehnt den Schlüssel ab.")
            if r.status_code != 200:
                raise ValueError(f"Der Server antwortet mit HTTP {r.status_code}.")
            body = b""
            async for part in r.aiter_bytes():
                body += part
                if len(body) > LLM_MODELS_BYTES:
                    raise ValueError("Die Antwort des Servers ist zu groß.")
    data = json.loads(body).get("data")
    if not isinstance(data, list):
        raise ValueError("Der Server meldet keine Modellliste.")
    out = []
    for m in data:
        mid = m.get("id") if isinstance(m, dict) else None
        if isinstance(mid, str) and _MODEL_ID.match(mid) and mid not in out:
            out.append(mid)
        if len(out) >= LLM_MODELS_MAX:
            break
    return out


@router.get("/api/admin/llm-models", dependencies=[Depends(auth)])
async def llm_models(request: Request, fresh: bool = False):
    """{models, current, error}: the names /v1/models of the configured address lists (empty with error
    when it cannot be read; the page then keeps the free text field)."""
    guard.limit(request, "llmmodels", admin=True)
    ccfg = load_config().get("chat", {})
    url = str(ccfg.get("llm_url") or "").rstrip("/")
    current = str(ccfg.get("llm_model") or "")
    if not url.startswith(("http://", "https://")):
        return {"models": [], "current": current, "error": "Keine gültige Adresse eingestellt."}
    hit = _llm_list.get(url)
    if hit and not fresh and time.monotonic() - hit[0] < LLM_MODELS_TTL:
        return {"models": hit[1], "current": current, "error": ""}
    try:
        models = await _fetch_llm_models(url, llm.key(ccfg))
    except httpx.HTTPError as e:
        return {"models": [], "current": current, "error": f"Server nicht erreichbar ({type(e).__name__})."}
    except (ValueError, AttributeError) as e:   # also an answer that is no JSON object
        msg = str(e) if type(e) is ValueError else "Der Server meldet keine Modellliste."
        return {"models": [], "current": current, "error": msg}
    _llm_list.clear()             # only the configured address is kept
    _llm_list[url] = (time.monotonic(), models)
    return {"models": models, "current": current, "error": ""}


@router.get("/api/config", dependencies=[Depends(auth)])
def get_config():
    with open(DEFAULTS) as f:
        cfg = json.load(f)
    known = {sec: set(vals) for sec, vals in cfg.items() if isinstance(vals, dict)}
    for sec, vals in load_config().items():  # fill keys added by newer versions
        cfg.setdefault(sec, {}).update(vals)
    return _tidy(cfg, known)


def _tidy(cfg, known):
    """What older versions left in the stored config and this one no longer knows must not block every save
    (V01.0.492/493): validate() stays strict for what the admin sends, the stored leftovers are dropped here."""
    for sec, keys in known.items():
        if isinstance(cfg.get(sec), dict):
            cfg[sec] = {k: v for k, v in cfg[sec].items() if k in keys}
    ch = cfg.get("chat", {})
    # gone with "Freigabe vereinfachen" (Dominik 2026-10-13): what a new profile got switched on; every profile now
    # gets what the admin releases
    ch.pop("new_profile_on", None)
    if "chat" in cfg:   # a removed function or a deleted profile in Gesperrte Funktionen never blocks saving
        ch["deny"] = features.clean_deny(ch.get("deny"))
    if isinstance(ch.get("defaults"), dict):        # a preset whose setting is gone or takes other values now
        ch["defaults"] = profiles.clean_settings(ch["defaults"])
    if isinstance(ch.get("berater_off"), list):     # a Melder of the Einstellungs-Assistent that is gone
        import berater
        ch["berater_off"] = list(dict.fromkeys(x for x in ch["berater_off"] if isinstance(x, str) and x in berater.MELDER))
    return cfg


def _is_ip(x):
    import ipaddress
    try:
        ipaddress.ip_address(x)
        return True
    except ValueError:
        return False




def validate(new):
    old = load_config()
    with open(DEFAULTS) as f:
        defaults = json.load(f)
    for sec in defaults:
        if sec not in new or not isinstance(new[sec], dict):
            raise HTTPException(400, f"section '{sec}' missing")
        for k in new[sec]:
            if k not in defaults[sec]:
                raise HTTPException(400, f"unknown key {sec}.{k}")
            # every switch: its type comes from config.default.json, the one list (Richtlinie Teil 17)
            if isinstance(defaults[sec][k], bool) and not isinstance(new[sec][k], bool):
                raise HTTPException(400, f"{k} must be true or false")
    if not re.fullmatch(r"[A-Za-z0-9_\-]*", new["api"]["key"]):
        raise HTTPException(400, "API key: letters, digits, _ and - only")
    if not new["api"]["key"] and not all(new[s].get("host") in ("127.0.0.1", "::1", "localhost") for s in ("asr", "tts")):
        raise HTTPException(400, "API key: required while speech recognition or output listen in the network "
                                 "(host not 127.0.0.1); press Erzeugen")
    # the model computer and the TLS-Tor (plan Raspberry-Pi split, B1/B2): set only by install.sh and the pairing,
    # never from the panel, so a stolen login can not send speech to another computer; once the models run on
    # another computer the key is a must (the connection is https with the pinned certificate, common.model_url)
    for sec, keys in (("models", ("host", "cert")), ("api", ("tls_listen", "tls_from"))):
        for k in keys:
            if k in old.get(sec, {}):
                new[sec][k] = old[sec][k]
            else:
                new[sec].pop(k, None)
    if not new["api"]["key"] and not model_local(new):
        raise HTTPException(400, "API key: required while the models run on another computer; press Erzeugen")
    # which model runs is then the model computer's (B4c, common.MODEL_CHOICE): the panel only shows it
    if not model_local(new):
        for sec, keys in MODEL_CHOICE.items():
            for k in keys:
                if k in old.get(sec, {}):
                    new[sec][k] = old[sec][k]
    ch = new["chat"]
    if ch.get("search_url") and not re.fullmatch(r"https?://\S+", ch["search_url"]):
        raise HTTPException(400, "SearXNG address must start with http:// or https://")
    for k in ("weather_url", "geocode_url", "telegram_api", "transit_url", "wiki_url"):
        if ch.get(k) and not re.fullmatch(r"https?://\S+", ch[k]):
            raise HTTPException(400, f"{k}: the address must start with http:// or https://")
    import verbund
    if ch.get("verbund_mode", "pair") not in verbund.MODES:
        raise HTTPException(400, "verbund_mode: pair or open")
    vd = ch.get("verbund_domain", "")
    if not isinstance(vd, str) or vd.strip() and not verbund.DOMAIN.fullmatch(vd.strip().lower()):
        raise HTTPException(400, "verbund_domain: the Spark's name from outside, e.g. spark.example.de (no https://, no path)")
    if isinstance(vd, str):
        ch["verbund_domain"] = vd.strip().lower()
    import anrufe
    th = ch.get("calls_turn_host", "")
    if not isinstance(th, str) or th.strip() and not anrufe.HOST.fullmatch(th.strip().lower()):
        raise HTTPException(400, "calls_turn_host: the Spark's name from outside, e.g. spark.example.de (no https://, no port)")
    if isinstance(th, str):
        ch["calls_turn_host"] = th.strip().lower()
    if ch.get("kiwix_url") and not kiwix.URL.fullmatch(str(ch["kiwix_url"]).strip().rstrip("/")):
        raise HTTPException(400, "kiwix_url: http(s)://name or http(s)://name:port, optionally a path, nothing else")
    if ch.get("kiwix_link_url") and not kiwix.URL.fullmatch(str(ch["kiwix_link_url"]).strip().rstrip("/")):
        raise HTTPException(400, "kiwix_link_url: http(s)://name or http(s)://name:port, optionally a path, nothing else")
    import meldung
    if not isinstance(ch.get("report_repo", meldung.DEFAULT_REPO), str) or not meldung.REPO.fullmatch(ch.get("report_repo", meldung.DEFAULT_REPO)):
        raise HTTPException(400, "report_repo: owner/name of a GitHub repository")
    books = ch.get("kiwix_books", [])
    if not isinstance(books, list) or len(books) > kiwix.MAX_BOOKS \
            or not all(isinstance(b, str) and kiwix.BOOK.fullmatch(b) for b in books):
        raise HTTPException(400, f"kiwix_books: at most {kiwix.MAX_BOOKS} book names (letters, digits, . _ -)")
    for k, lo, hi, d in (("berater_calls", 1, 100, 20), ("berater_check_h", 6, 72, 24), ("memory_stale_months", 1, 60, 6),
                         ("nas_max_docs", 100, 20000, 5000), ("nas_sources_every", 15, 1440, 30), ("nas_drop_every", 5, 1440, 15),
                         ("nas_full_pct", 50, 99, 90), ("nas_temp_max", 40, 90, 60)):
        v = ch.get(k, d)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise HTTPException(400, f"{k}: {lo} bis {hi}")
    import gehaeuse
    why = gehaeuse.check(ch)
    if why:
        raise HTTPException(400, why)
    import werkstattseite
    why = werkstattseite.check(ch)
    if why:
        raise HTTPException(400, why)
    import schirm
    why = schirm.check(ch)
    if why:
        raise HTTPException(400, why)
    import rundlauf
    why = rundlauf.check(ch)
    if why:
        raise HTTPException(400, why)
    import berater
    off = ch.get("berater_off", [])
    if not isinstance(off, list) or len(off) > len(berater.MELDER) or any(x not in berater.MELDER for x in off):
        raise HTTPException(400, "berater_off: Melder des Einstellungs-Assistenten")
    # Eigener Speicher, "Ordner auf dem Spark" (speicher.py): below /mnt, /media or /srv, no "..", no "//"
    sroot = ch.get("storage_root", "")
    if not isinstance(sroot, str) or sroot and not (len(sroot) <= 200 and sroot.startswith(("/mnt/", "/media/", "/srv/"))
                                                    and re.fullmatch(r"/[A-Za-z0-9._\-/]+", sroot)
                                                    and not re.search(r"(^|/)\.\.?(/|$)|//", sroot)):
        raise HTTPException(400, "storage_root: a folder below /mnt, /media or /srv")
    if ch.get("esp32_url") and not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?/?", ch["esp32_url"]):
        raise HTTPException(400, "esp32_url: http(s)://name or http(s)://name:port, without a path")
    if ch.get("telegram_panel_url") and not re.fullmatch(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?/?", ch["telegram_panel_url"]):
        raise HTTPException(400, "telegram_panel_url: https://name or https://name:port, without a path")
    if not re.fullmatch(r"[\w.\-]+/[\w.\-]+", ch.get("esp32_repo") or "x/x"):
        raise HTTPException(400, "esp32_repo: owner/name")
    # Gesperrte Funktionen: the functions the admin blocked for single profiles (features.blocked); only the admin writes it
    deny = ch.get("deny", {})
    if not (isinstance(deny, dict) and len(deny) <= len(features.FEATURES)
            and all(k in features.BY_KEY and k not in features.NO_BLOCK and isinstance(v, list) and 0 < len(v) <= features.MAX_DENY and len(set(v)) == len(v)
                    and all(isinstance(u, str) and re.fullmatch(r"u_[0-9a-f]{12}", u) for u in v) for k, v in deny.items())):
        raise HTTPException(400, "deny: function → list of profile ids")
    if not isinstance(ch.get("defaults"), dict) or profiles.clean_settings(ch["defaults"]) != ch["defaults"]:
        raise HTTPException(400, "chat defaults: invalid value")
    if ch.get("speaker_strictness") not in speakers.STRICTNESS:
        raise HTTPException(400, "speaker_strictness: low, normal or high")
    if ch.get("grund_internet", "offen") not in ("offen", "ja", "nein"):
        raise HTTPException(400, "grund_internet: offen, ja or nein")
    if not (isinstance(ch.get("search_results"), int) and 1 <= ch["search_results"] <= 10
            and isinstance(ch.get("search_pages"), int) and 0 <= ch["search_pages"] <= 5):
        raise HTTPException(400, "search: 1..10 results, 0..5 pages to read")
    a = new["asr"]
    if not isinstance(a.get("context", ""), str) or len(a.get("context", "")) > 2000:
        raise HTTPException(400, "ASR context: text up to 2000 characters")
    if a.get("recognizer", "qwen") not in ("qwen", "parakeet"):
        raise HTTPException(400, "recognizer must be qwen or parakeet")
    if a.get("backend") != old["asr"].get("backend"):
        raise HTTPException(400, "the ASR backend is chosen at install time: sudo ./install.sh --asr-backend ...")
    if not isinstance(a["engine_mem"], (int, float)) or not 0.01 <= a["engine_mem"] <= 0.5:
        raise HTTPException(400, "asr engine_mem must be a share of the memory pool between 0.01 and 0.5")
    if a.get("backend") == "vllm" and "1.7B" in a["model"] and a["engine_mem"] < 0.055:
        raise HTTPException(400, "Qwen3-ASR-1.7B needs an engine share of at least 0.055 (0.6B: 0.035)")
    if not isinstance(a["engine_max_seqs"], int) or not 1 <= a["engine_max_seqs"] <= 256:
        raise HTTPException(400, "asr engine_max_seqs must be 1..256")
    t = new["tts"]
    if t.get("backend") != old["tts"].get("backend"):
        raise HTTPException(400, "the TTS backend is chosen at install time: sudo ./install.sh --tts-backend ...")
    for k in ("engine_mem_talker", "engine_mem_code2wav"):
        if not isinstance(t[k], (int, float)) or not 0.01 <= t[k] <= 0.5:
            raise HTTPException(400, f"{k} must be a share of the memory pool between 0.01 and 0.5")
    if not isinstance(t["engine_max_model_len"], int) or not 512 <= t["engine_max_model_len"] <= 65536:
        raise HTTPException(400, "engine_max_model_len must be 512..65536")
    if not isinstance(t.get("temperature"), (int, float)) or not 0.05 <= t["temperature"] <= 2:
        raise HTTPException(400, "temperature must be 0.05..2")
    if not isinstance(t.get("top_p"), (int, float)) or not 0.05 <= t["top_p"] <= 1:
        raise HTTPException(400, "top_p must be 0.05..1")
    if not isinstance(t.get("initial_chunk_frames"), int) or not 0 <= t["initial_chunk_frames"] <= 25:
        raise HTTPException(400, "Speech output start (first audio block): a whole number of frames from 0 to 25")
    if t.get("engine_decode_batch") not in (1, 2, 4) or isinstance(t.get("engine_decode_batch"), bool):
        raise HTTPException(400, "Several voices at once (decoder): 1, 2 or 4")
    if not isinstance(t.get("engine_prefix_cache"), bool):
        raise HTTPException(400, "engine_prefix_cache must be true or false")
    if t.get("ref_max_s") not in (0, 8, 10, 15) or isinstance(t.get("ref_max_s"), bool):
        raise HTTPException(400, "Shorten the voice reference: 0 (off), 8, 10 or 15 seconds")
    if t.get("numbers") not in ("off", "words", "blocks", "digits"):
        raise HTTPException(400, "numbers must be off, words, blocks or digits")
    if not isinstance(t.get("seed"), int) or t["seed"] < -1:
        raise HTTPException(400, "seed must be a whole number, -1 = random")
    if not isinstance(t["engine_max_seqs"], int) or not 1 <= t["engine_max_seqs"] <= 64:
        raise HTTPException(400, "engine_max_seqs must be 1..64")
    if not MODEL_ID.fullmatch(str(t["voicedesign_model"])):
        raise HTTPException(400, "VoiceDesign: only Qwen's own speech models (Qwen/Qwen3-TTS-...)")
    ports = [new["asr"]["port"], t["port"], new["panel"]["port"]]
    if a.get("backend") == "vllm":
        ports.append(a["engine_port"])
    if t.get("backend") == "vllm-omni":
        ports += [t["engine_port"], t["voicedesign_port"]]
    sd = new["panel"].get("session_days", 30)
    if not isinstance(sd, int) or isinstance(sd, bool) or not 7 <= sd <= 90:
        raise HTTPException(400, "session_days must be 7..90")
    td = new["panel"].get("trust_days", 60)
    if not isinstance(td, int) or isinstance(td, bool) or not 7 <= td <= 90:
        raise HTTPException(400, "trust_days must be 7..90")
    tp = new["panel"].get("trusted_proxies", [])
    if not isinstance(tp, list) or len(tp) > 10 or not all(isinstance(x, str) and _is_ip(x) for x in tp):
        raise HTTPException(400, "trusted_proxies: a list of up to 10 IP addresses")
    if not isinstance(new["panel"].get("https_port"), int):
        raise HTTPException(400, "https_port must be a number, 0 = off")
    if new["panel"]["https_port"]:
        ports.append(new["panel"]["https_port"])
    for p in ports:
        if not isinstance(p, int) or not 1024 <= p <= 65535:
            raise HTTPException(400, f"invalid port {p}")
        if 30000 <= p <= 30099:
            raise HTTPException(400, f"port {p} is in the 30000-30099 range used by dgx-spark-qwen38")
    if len(set(ports)) != len(ports):
        raise HTTPException(400, "ports must differ")
    # Bilder malen (bild_server.py): whether it is installed, which model and its ports are chosen by install.sh
    # (sudo ./install.sh --bild ...); the panel only sets the limits, read live by the service
    im, oim = new["image"], old.get("image", {})
    for k in ("enabled", "variant", "port", "engine_port"):
        if k in oim:
            im[k] = oim[k]
        else:
            im.pop(k, None)
    for k, lo, hi in (("idle_min", 1, 120), ("day_limit", 1, 500), ("store_mb", 50, 20000), ("max_side", 512, 1408)):
        v = im.get(k)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise HTTPException(400, f"image {k}: {lo} bis {hi}")
    if im["max_side"] % 64:
        raise HTTPException(400, "image max_side: a multiple of 64")
    # Musik machen (musik_server.py): whether it is installed, its variant and ports come from install.sh
    # (sudo ./install.sh --musik ...); the panel picks the model per song among the installed ones and sets the limits
    mu, omu = new["music"], old.get("music", {})
    for k in ("enabled", "variant", "port", "engine_port", "idle_min"):
        if k in omu:
            mu[k] = omu[k]
        else:
            mu.pop(k, None)
    import musik
    if mu.get("model", "") not in ("",) + tuple(musik.VARIANTS):
        raise HTTPException(400, "music model: " + ", ".join(musik.VARIANTS) + " or empty")
    for k, lo, hi in (("day_limit", 1, 100), ("store_mb", 50, 20000), ("max_s", 30, 600)):
        v = mu.get(k)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise HTTPException(400, f"music {k}: {lo} bis {hi}")
    w = new["watch"]
    if not isinstance(w.get("warn_gib"), (int, float)) or not 2 <= w["warn_gib"] <= 64:
        raise HTTPException(400, "watch warn_gib must be 2..64")
    import offline   # Zeitserver im Heimnetz: empty, or one private IPv4 address (install.sh checks it the same way)
    if not isinstance(w.get("zeitserver", ""), str) or (w.get("zeitserver", "").strip() and not offline.zeitserver(w["zeitserver"])):
        raise HTTPException(400, "Zeitserver im Heimnetz: eine IP-Adresse im Heimnetz wie 192.168.178.1, oder leer.")
    w["zeitserver"] = offline.zeitserver(w.get("zeitserver", ""))
    lg = new["logs"]
    if not isinstance(lg["max_mb"], int) or not 50 <= lg["max_mb"] <= 20000:
        raise HTTPException(400, "logs max_mb must be 50..20000")
    if not isinstance(lg["keep_days"], int) or not 1 <= lg["keep_days"] <= 365:
        raise HTTPException(400, "logs keep_days must be 1..365")
    if isinstance(lg.get("live_screens", 3), bool) or not isinstance(lg.get("live_screens", 3), int) or not 1 <= lg.get("live_screens", 3) <= 5:
        raise HTTPException(400, "logs live_screens must be 1..5")
    ch = new["chat"]
    if not re.fullmatch(r"https?://[^\s]+", str(ch["llm_url"])):
        raise HTTPException(400, "chat llm_url must start with http:// or https://")
    if not isinstance(ch.get("wyoming_port", 31003), int) or not 1024 <= ch.get("wyoming_port", 31003) <= 65535:
        raise HTTPException(400, "Wyoming port must be 1024..65535")
    try:
        nets = wyoming.allowed(ch.get("wyoming_allow", ""))
    except ValueError as e:
        raise HTTPException(400, f"Wyoming: „{e}“ ist keine Adresse. Erlaubt sind Adressen wie 192.168.1.20 oder Netze wie 192.168.1.0/24.")
    if ch.get("wyoming") and not nets:
        raise HTTPException(400, "Wyoming braucht mindestens eine erlaubte Adresse: die deines Home Assistant, z. B. 192.168.1.20.")
    if ch.get("wyoming_port", 31003) in (new.get("asr", {}).get("port"), new.get("tts", {}).get("port"),
                                         new.get("panel", {}).get("port"), new.get("panel", {}).get("https_port")):
        raise HTTPException(400, "Wyoming port is already used by another service")
    if not isinstance(ch.get("wyoming_voice", ""), str) or len(ch.get("wyoming_voice", "")) > 64:
        raise HTTPException(400, "Wyoming voice: invalid")
    # Den Spark anrufen (telefon.py): sound "hd" (G.722 first) or "schmal" (G.711 only), 1 or 2 calls at once
    if ch.get("telefon_ton", "hd") not in ("hd", "schmal"):
        raise HTTPException(400, "telefon_ton must be hd or schmal")
    if isinstance(ch.get("telefon_max", 1), bool) or ch.get("telefon_max", 1) not in range(1, telefon.MAX_CALLS + 1):
        raise HTTPException(400, f"telefon_max must be 1..{telefon.MAX_CALLS}")
    if not isinstance(ch["max_tokens"], int) or not 16 <= ch["max_tokens"] <= 32768:
        raise HTTPException(400, "chat max_tokens must be 16..32768")
    if not isinstance(ch.get("temperature", 0.3), (int, float)) or not 0 <= ch.get("temperature", 0.3) <= 1.5:
        raise HTTPException(400, "chat temperature must be 0..1.5")
    if not isinstance(ch.get("tool_temperature", 0.1), (int, float)) or isinstance(ch.get("tool_temperature", 0.1), bool) \
            or not 0 <= ch.get("tool_temperature", 0.1) <= 1.5:
        raise HTTPException(400, "chat tool_temperature must be 0..1.5")
    import chat  # chat imports much of the panel; only needed here
    num = lambda k, d: ch.get(k, d) if isinstance(ch.get(k, d), (int, float)) and not isinstance(ch.get(k, d), bool) else None  # noqa: E731
    if not isinstance(ch.get("history_chars", 24000), int) or num("history_chars", 24000) is None \
            or not chat.HISTORY_RANGE[0] <= ch.get("history_chars", 24000) <= chat.HISTORY_RANGE[1]:
        raise HTTPException(400, "Verlaufslänge: %d bis %d Zeichen" % chat.HISTORY_RANGE)
    if not isinstance(ch.get("max_searches", 2), int) or num("max_searches", 2) is None \
            or not chat.SEARCH_RANGE[0] <= ch.get("max_searches", 2) <= chat.SEARCH_RANGE[1]:
        raise HTTPException(400, "Websuchen pro Antwort: %d bis %d" % chat.SEARCH_RANGE)
    if not isinstance(ch.get("llm_timeout", 600), int) or num("llm_timeout", 600) is None \
            or not chat.TIMEOUT_RANGE[0] <= ch.get("llm_timeout", 600) <= chat.TIMEOUT_RANGE[1]:
        raise HTTPException(400, "Zeitlimit: %d bis %d Sekunden" % chat.TIMEOUT_RANGE)
    tp, pp = num("top_p", 0), num("presence_penalty", 0)
    if tp is None or not (tp == 0 or 0.05 <= tp <= 1):
        raise HTTPException(400, "top_p: 0 (Standard des Servers) oder 0.05 bis 1")
    if pp is None or not 0 <= pp <= 2:
        raise HTTPException(400, "presence_penalty: 0 (Standard des Servers) bis 2")
    tk = ch.get("top_k", 0)
    if not isinstance(tk, int) or isinstance(tk, bool) or not 0 <= tk <= 100:
        raise HTTPException(400, "top_k: 0 (Standard des Servers) bis 100")
    try:
        chat.parse_tool_words(ch.get("tool_words", ""))
    except ValueError as e:
        raise HTTPException(400, f"Eigene Stichwörter: {e}")
    try:
        chat.parse_tool_hints(ch.get("tool_hints", ""))
    except ValueError as e:
        raise HTTPException(400, f"Werkzeug-Hinweise: {e}")
    import intent   # (needs chat fully loaded)
    try:
        intent.parse_route_words(ch.get("route_words", ""))
    except ValueError as e:
        raise HTTPException(400, f"Eigene Wörter der Werkzeugwahl: {e}")
    import weiche   # Funktionen → Weiche: „Nicht bei“, zusätzliche Werkzeuge, Gruppen ohne Eingrenzen, Testsätze
    try:
        weiche.check(ch)
    except ValueError as e:
        raise HTTPException(400, f"Weiche: {e}")
    if ch.get("face", "robot") not in FACES:
        raise HTTPException(400, "face: " + " or ".join(FACES))
    if ch.get("self_echo_mode", "pause") not in ("text", "pause"):
        raise HTTPException(400, "self_echo_mode: text or pause")
    for k in ("doc_night_from", "doc_night_to", "dev_updates_night_at"):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(ch.get(k, "01:00"))):
            raise HTTPException(400, f"{k}: HH:MM")
    pw = ch.get("person_priority_wait", 2)
    if isinstance(pw, bool) or not isinstance(pw, (int, float)) or not 0 <= pw <= 5:
        raise HTTPException(400, "person_priority_wait: 0 to 5 seconds")
    ms = ch.get("local_first_ms", 400)
    if not isinstance(ms, int) or isinstance(ms, bool) or not 200 <= ms <= 1500:
        raise HTTPException(400, "local_first_ms: 200 to 1500")
    ms = ch.get("local_first_kiwix_ms", 900)
    if not isinstance(ms, int) or isinstance(ms, bool) or not 200 <= ms <= 2000:
        raise HTTPException(400, "local_first_kiwix_ms: 200 to 2000")
    m = ch.get("doc_max_mb", 100)
    if not isinstance(m, int) or isinstance(m, bool) or not 20 <= m <= 300:
        raise HTTPException(400, "doc_max_mb: 20 to 300")
    d = ch.get("search_check_day", 20)
    if not isinstance(d, int) or isinstance(d, bool) or not 5 <= d <= 100:
        raise HTTPException(400, "search_check_day: 5 to 100")
    d = ch.get("knowledge_book_day", 40)
    if not isinstance(d, int) or isinstance(d, bool) or not 5 <= d <= 200:
        raise HTTPException(400, "knowledge_book_day: 5 to 200")
    d = ch.get("knowledge_book_sample", 50)
    if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 100:
        raise HTTPException(400, "knowledge_book_sample: 0 to 100")
    d = ch.get("knowledge_map_day", 200)
    if not isinstance(d, int) or isinstance(d, bool) or not 5 <= d <= 500:
        raise HTTPException(400, "knowledge_map_day: 5 to 500")
    r = ch.get("rerank_ms", 800)
    if not isinstance(r, int) or isinstance(r, bool) or not 300 <= r <= 2000:
        raise HTTPException(400, "rerank_ms: 300 to 2000")
    if ch.get("rerank_model", "klein") not in ("klein", "gross"):
        raise HTTPException(400, "rerank_model: klein or gross")
    import verbrauch
    for z, (_de, _en, key, top) in verbrauch.ZEITRAEUME.items():   # Kontingent: 0 = no limit in this period
        uq = ch.get(key, verbrauch.QUOTA_DEFAULT_K[z])
        if not isinstance(uq, int) or isinstance(uq, bool) or not 0 <= uq <= top:
            raise HTTPException(400, f"{key}: 0 to {top}")
    uw = ch.get("usage_quota_warn", verbrauch.WARN_DEFAULT)
    if not isinstance(uw, int) or isinstance(uw, bool) or not 0 <= uw <= 99:
        raise HTTPException(400, "usage_quota_warn: 0 to 99")
    q = ch.get("doc_quota_mb", 500)
    if not isinstance(q, int) or isinstance(q, bool) or not 50 <= q <= 5000:
        raise HTTPException(400, "doc_quota_mb: 50 to 5000")
    import systemone
    if ch.get("systemone_min", systemone.ROUTE_MIN) not in systemone.ROUTE_STEPS \
            or isinstance(ch.get("systemone_min"), bool):
        raise HTTPException(400, "systemone_min: " + ", ".join(str(x) for x in systemone.ROUTE_STEPS))
    if ch.get("route_model", "off") not in ("off", "on", "lean", "systemone"):
        raise HTTPException(400, "route_model: off, on, lean or systemone")
    for sec in ("asr", "tts"):
        if not MODEL_ID.fullmatch(str(new[sec]["model"])):
            raise HTTPException(400, f"{sec}: only Qwen's own speech models (Qwen/Qwen3-ASR-... or Qwen/Qwen3-TTS-...)")
    if not MODEL_ID.fullmatch(str(new["asr"].get("aligner_model", "Qwen/Qwen3-ForcedAligner-0.6B"))):
        raise HTTPException(400, "aligner: only Qwen's own models")
        if new[sec]["dtype"] not in ("bfloat16", "float16", "float32"):
            raise HTTPException(400, "dtype must be bfloat16, float16 or float32")
    return old


SENSITIVE = [("api", "key"), ("chat", "llm_url"), ("chat", "llm_key"), ("chat", "telegram_api"),
             ("chat", "search_url"), ("chat", "kiwix_url"), ("chat", "kiwix_link_url"), ("chat", "public"), ("chat", "esp32_url"), ("chat", "telegram_panel_url"), ("chat", "esp32_ota_http"), ("chat", "esp32_repo"),
             ("chat", "mfa"), ("chat", "mcp_server"), ("chat", "mcp_server_extern"), ("chat", "mcp_server_act"),
             ("chat", "mcp_own"), ("chat", "mcp_own_oauth"), ("chat", "report"), ("chat", "report_repo"),
             ("chat", "chats_verbund"), ("chat", "verbund_media"), ("chat", "verbund_groups"), ("chat", "verbund_mode"), ("chat", "verbund_domain"),
             ("chat", "calls_turn"), ("chat", "calls_turn_host"),
             ("panel", "trusted_proxies"), ("panel", "allow_lan"), ("panel", "notaus_auto"), ("panel", "update_night"), ("panel", "session_days"), ("panel", "trust_days"), ("asr", "model"), ("asr", "aligner_model"),
             ("tts", "model"), ("tts", "voicedesign_model")]


@router.put("/api/config", dependencies=[Depends(auth)])
async def put_config(request: Request):
    new = await request.json()
    old = validate(new)
    # the Weiche's rules have their own page (Funktionen → Weiche, weiche.py): the settings form carries a copy
    # from when it was loaded, which must not put back older rules
    import weiche
    for k in weiche.KEYS:
        if k in old.get("chat", {}):
            new["chat"][k] = old["chat"][k]
        else:
            new["chat"].pop(k, None)
    touched = [f"{sec}.{k}" for sec, k in SENSITIVE if new.get(sec, {}).get(k) != old.get(sec, {}).get(k)]
    if touched:
        # these send keys or conversations to another address, change who may log in, or which code
        # runs: a stolen login alone must not be enough (second step, when it is on)
        await admin_code(request)
        guard.log("config_sensitive", detail=", ".join(touched))
    if new.get("chat", {}).get("llm_key") != old.get("chat", {}).get("llm_key"):
        new["chat"].pop("llm_key_from", None)  # typed by hand: updates keep it as is
    # systemctl restarts take up to a minute: in a worker thread, the panel keeps answering meanwhile
    return await asyncio.to_thread(_save, new, old, _by(request))


def _by(request):
    me = acting_profile(request)
    return me["id"] if me else "main"


_save_lock = threading.Lock()


def _save(new, old, by):
    """Writes a checked config, keeps what may be undone (undo.py) and starts or stops the services it touches.
    Runs in worker threads (saving and undoing): one at a time."""
    with _save_lock:
        return _save_locked(new, old, by)


def _save_locked(new, old, by):
    write_json(CONFIG_PATH, new, indent=2)
    undo.record(old, new, by, SENSITIVE)
    # models on another computer (Spark teilen): it takes the speech settings before its units restart below
    handed = steuer.einstellen(new) if steuer.remote(new) else True
    # the API key is read per request, so changing it needs no restart
    mem_changed = new["memory"] != old.get("memory")
    actions = {}  # unit name -> start | stop | restart
    for n in SERVICES:
        if new[n] != old[n] or mem_changed:
            actions[n] = "restart" if new[n]["enabled"] else "stop"
    a, oa = new["asr"], old["asr"]
    if a.get("backend") == "vllm":
        if not a["enabled"] or (a.get("recognizer") == "parakeet" and oa.get("recognizer") != "parakeet"):
            actions["asr-engine"] = "stop"  # Parakeet runs inside the ASR service, the engine frees its memory
        elif a.get("recognizer") == "parakeet":
            pass
        elif oa.get("recognizer") == "parakeet":
            actions["asr-engine"] = "restart"
        elif any(a.get(k) != oa.get(k) for k in ASR_ENGINE_KEYS) or mem_changed or not oa["enabled"]:
            actions["asr-engine"] = "restart"
    t, ot = new["tts"], old["tts"]
    if t.get("backend") == "vllm-omni":
        changed = lambda keys: any(t.get(k) != ot.get(k) for k in keys)  # noqa: E731
        if not t["enabled"]:
            actions["tts-engine"] = actions["tts-design"] = "stop"
        else:
            if changed(ENGINE_KEYS) or mem_changed or not ot["enabled"]:
                actions["tts-engine"] = "restart"
            if not t["voicedesign_enabled"]:
                if ot.get("voicedesign_enabled"):
                    actions["tts-design"] = "stop"
            elif changed(DESIGN_KEYS) or mem_changed or not ot["enabled"]:
                actions["tts-design"] = "restart"
    errors = []
    for n, action in actions.items():
        code, out = steuer.systemctl(action, UNITS[n])
        if code != 0:
            errors.append(f"{UNITS[n]}: {out}")
    if not handed:
        errors.append("Modell-Rechner: Einstellungen nicht übertragen, sie folgen, sobald er antwortet")
    return {"saved": True, "restarted": [n for n, a in actions.items() if a == "restart"],
            "stopped": [n for n, a in actions.items() if a == "stop"], "errors": errors,
            "panel_restart_needed": new["panel"] != old["panel"]}


# Funktionen from the iPhone app ("Spark verwalten", V01.0.250): only the on/off switches of
# chat.*, never the sensitive ones (SENSITIVE: those want the admin's code in the browser) nor the ones that
# would shut the app itself out. The admin signs in there with password and code, like the browser.
APP_SWITCH_SKIP = {"public", "mfa", "iphone", "iphone_panel"}


def app_switches():
    with open(DEFAULTS) as f:
        d = json.load(f)["chat"]
    sens = {k for sec, k in SENSITIVE if sec == "chat"}
    return [k for k, v in d.items() if isinstance(v, bool) and k not in APP_SWITCH_SKIP and k not in sens]


@router.get("/api/admin/switches", dependencies=[Depends(auth)])
def admin_switches():
    cfg = get_config()["chat"]
    keys = app_switches()
    names, groups = features.switch_names(set(keys))
    return {"switches": {k: bool(cfg.get(k)) for k in keys}, "names": names, "groups": groups,
            "grund": features.grund_state(cfg)}


@router.put("/api/admin/switches", dependencies=[Depends(auth)])
async def admin_switch(request: Request):
    body = await json_body(request, 512)
    key, on = body.get("key"), body.get("on")
    if key not in app_switches() or not isinstance(on, bool):
        raise HTTPException(400, "not a switch the app may change")
    with _save_lock:   # one config write at a time (_save)
        new = get_config()
        new["chat"][key] = on
        old = validate(new)
        write_json(CONFIG_PATH, new, indent=2)
    undo.record(old, new, _by(request), SENSITIVE)
    guard.log("config_switch", detail=f"chat.{key}={'on' if on else 'off'}")
    return {"key": key, "on": on}


# Grundausstattung (features.GRUNDAUSSTATTUNG, Dominik 2026-10-17): the card on Funktionen and in the iPhone app.
# "basis" switches the whole list on (back off only through Rückgängig in the Admin-Protokoll, like every saved
# change); "internet" answers „Darf der Spark ins Internet?“: yes switches features.GRUND_INTERNET on (the web search
# only with a stored SearXNG address), no only keeps the answer. Only the admin, like every switch (coadmin.MANAGER).
@router.get("/api/admin/grundausstattung", dependencies=[Depends(auth)])
def grund_get(request: Request):
    guard.limit(request, "features", admin=True)
    return features.grund_state(get_config()["chat"])


@router.post("/api/admin/grundausstattung", dependencies=[Depends(auth)])
async def grund_take(request: Request):
    guard.limit(request, "features", admin=True)
    body = await json_body(request, 256)
    teil, on = body.get("teil"), body.get("on")
    if teil not in ("basis", "internet") or not isinstance(on, bool) or (teil == "basis" and not on):
        raise HTTPException(400, "teil: basis (on: true) or internet (on: true or false)")
    with _save_lock:   # one config write at a time (_save)
        new = get_config()
        ch = new["chat"]
        if teil == "basis":
            keys = list(features.GRUNDAUSSTATTUNG)
        else:
            ch["grund_internet"] = "ja" if on else "nein"
            url = str(ch.get("search_url") or "").strip()
            keys = [k for k in features.GRUND_INTERNET if on and (k != "chat.search" or url)]
        turned = [k for k in keys if ch.get(k.split(".", 1)[1]) is not True]
        for k in turned:
            ch[k.split(".", 1)[1]] = True
        old = validate(new)
        write_json(CONFIG_PATH, new, indent=2)
    undo.record(old, new, _by(request), SENSITIVE)
    guard.log("config_switch", detail=f"Grundausstattung {teil}: {'ja' if on else 'nein'}, {len(turned)} eingeschaltet")
    return dict(features.grund_state(new["chat"]), turned=turned)


# Rückgängig (undo.py, plan „Bedienung gesamt“ C5): the last 50 saved changes with their old values. The main admin
# sees all, a Verwalter his own; undoing goes through validate() and _save() like saving.
def _undo_view(x, names):
    by = x.get("by")
    return {"id": x["id"], "t": x["t"], "by": "main" if by == "main" else names.get(by, ""), "mine": by,
            "changes": x["changes"], "undone": bool(x.get("undone"))}


@router.get("/api/admin/undo", dependencies=[Depends(auth)])
def undo_list(request: Request):
    me = acting_profile(request)
    names = {u["id"]: u["name"] for u in profiles.names()}
    mine = me["id"] if me and me["role"] != "admin" else None
    return {"items": [_undo_view(x, names) for x in undo.listing(mine)]}


@router.post("/api/admin/undo/{uid}", dependencies=[Depends(auth)])
def undo_one(uid: str, request: Request):
    guard.limit(request, "undo", admin=True)
    item = undo.get(uid) if undo.ID.fullmatch(uid) else None
    me = acting_profile(request)
    if not item or (me and me["role"] != "admin" and item.get("by") != me["id"]):
        raise HTTPException(404, "no such change")
    if item.get("undone"):
        raise HTTPException(409, "already undone")
    new, done, kept = undo.revert(item, get_config(), SENSITIVE)
    if not done:
        raise HTTPException(409, "every value was changed again since")
    old = validate(new)   # the same checks as saving
    res = _save(new, old, _by(request))
    undo.mark_undone(uid, _by(request))
    guard.log("config_undo", detail=", ".join(done)[:300])
    return dict(res, undone=done, kept=kept)


@router.post("/api/service/{name}/{action}", dependencies=[Depends(auth)])
def service_action(name: str, action: str):
    if name not in UNITS or action not in ("start", "stop", "restart"):
        raise HTTPException(400, "bad service or action")
    code, out = steuer.systemctl(action, UNITS[name])
    if code != 0:
        raise HTTPException(500, out or f"systemctl {action} failed")
    return {"ok": True}


@router.get("/api/logs/{name}", dependencies=[Depends(auth)])
def logs(name: str, lines: int = 200):
    if name not in LOG_UNITS:
        raise HTTPException(400, "bad service")
    return Response(steuer.logs(name, LOG_UNITS[name], min(lines, 2000)), media_type="text/plain")


@router.get("/api/languages", dependencies=[Depends(auth)])
def languages():
    return LANGS


MAX_AUDIO = 50 * 1024**2  # far more than any spoken question (5 minutes of 16 kHz WAV are ~10 MB)


async def read_audio(file):
    data = bytearray()   # appending to bytes copies everything each time
    while chunk := await file.read(1 << 20):
        data += chunk
        if len(data) > MAX_AUDIO:
            raise HTTPException(413, "recording too large")
    return bytes(data)


@router.post("/api/test/asr", dependencies=[Depends(assistant)])
async def test_asr(request: Request, file: UploadFile = File(...), language: str = Form("auto"), wake: str = Form(""),
                   room: str = Form(""), opened: str = Form(""), hold: str = Form(""), asked: str = Form(""),
                   turn: str = Form(""), turns: str = Form("", max_length=400)):
    """Load limits (per caller per minute, guests only a few at once), then the transcription. hold: the page paused
    the answer for this barge-in and asks whether it plays on (zwischenruf.py; asked: the answer ended on a question).
    turn: a pause snapshot Satzende am Tonfall measures, turns: what became of earlier ones (satzende.py)."""
    me = profiles.current(request)
    admin = not me and admin_cookie_ok(request)
    guard.limit(request, "asr", me and me["id"], admin)
    slot = None if me or admin else guard.Slot("asr")
    try:
        if me and turns:
            satzende.report(me["id"], turns)
        heard = {"start": (lambda data: satzende.start(me["id"], data, load_config())) if me and turn == "1" else None}
        res = await _test_asr(request, file, language, wake, room, opened, heard)
        key = heard.get("key")
        got = answer_dict(res) if me and (hold == "1" or key) else None
        if got is None:
            return res
        if hold == "1" and fremdstimme.opened(opened) == "barge":
            import zwischenruf
            got = zwischenruf.attach(got, me["id"], asked == "1", echo.device_of(request).split(":")[0])
        if key:
            await satzende.settle(key)
            got = dict(got, turn=key)
        return got
    finally:
        if slot:
            slot.release()


@router.get("/api/admin/satzende", dependencies=[Depends(auth)])
def admin_satzende():
    """Satzende am Tonfall: the measurement's numbers for Funktionen → Gespräch (satzende.summary), never words."""
    return satzende.summary()


def answer_dict(res):
    """The recognition's answer as a dict (a 200 JSON answer unpacked), None for an error or anything else."""
    if isinstance(res, dict):
        return res
    if getattr(res, "status_code", 0) != 200:
        return None
    try:
        got = json.loads(bytes(res.body))
    except (ValueError, TypeError, AttributeError):
        return None
    return got if isinstance(got, dict) else None


def wav_seconds(data):
    """Length of a plain 16-bit PCM WAV recording in seconds, None for anything else."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    rate = int.from_bytes(data[28:32], "little")
    return (len(data) - 44) / rate if rate > 0 else None


def _quiet(task):
    """A side task whose answer may never be asked for (the recognition failed, the voice was not needed): its
    error (e.g. "cannot read this audio") is taken here instead of ending up as "Task exception was never
    retrieved" in the log."""
    task.add_done_callback(lambda t: t.cancelled() or t.exception())
    return task


async def _test_asr(request, file, language, wake, room, opened="", heard=None):
    cfg = load_config()
    data = await read_audio(file)
    if heard is not None and heard.get("start"):
        heard["key"] = heard["start"](data)   # a pause snapshot: Smart Turn hears it beside the recognition (satzende.py)
    ended = time.time()   # the recording ended about now (for "speaking pause", echo.py)
    # voices are only told apart for a signed-in profile or device: a guest page gets no token that
    # could open someone's data, and a token only works where it was issued
    me = profiles.current(request)
    form = {"language": language, "response_format": "verbose_json"}
    if wake and not me and not admin_cookie_ok(request):
        raise HTTPException(403, "the wake word is for profiles only")
    # Namen fürs Hören (hoerwoerter.py): the names this profile may use, the wake phrase and the admin's own context
    import hoerwoerter
    ctx = hoerwoerter.prompt(cfg, me and me["id"], extra=f"{wake[:40]}." if wake else "")
    if ctx and (wake or hoerwoerter.on(cfg)):
        form["prompt"] = ctx
    # speaker identification runs on the CPU while the GPU transcribes
    spk = None
    th = speakers.STRICTNESS.get(cfg.get("chat", {}).get("speaker_strictness"), 0.75)
    if cfg.get("chat", {}).get("speaker_id", False) and not wake and me:
        spk = _quiet(asyncio.create_task(asyncio.to_thread(speakers.identify, data, th)))
    # room mode: whose voice this is, while a proposal waits for a yes (only the profile may say yes) and when
    # the room listens only to known voices (TV)
    import room as room_mode
    rv = None
    if room and me:
        room_mode.set_voice(me["id"], room, None)
        if room_mode.needs_voice(me["id"], room):
            rv = _quiet(asyncio.create_task(asyncio.to_thread(speakers.identify, data, th)))
    # a microphone the page opened by itself (barge-in, follow-up window, hands-free) takes only a known voice,
    # never the TV (fremdstimme.py; only with a taught voice), checked on the CPU while the GPU transcribes
    how = fremdstimme.opened(opened)
    fv = None
    if me and not wake and not room and fremdstimme.applies(cfg, me["id"], how):
        fv = _quiet(asyncio.create_task(asyncio.to_thread(fremdstimme.check, me["id"], data, th)))
    # silence never becomes words (stille.py): how much of the recording is voice, measured while the GPU listens
    quiet = _quiet(asyncio.create_task(asyncio.to_thread(stille.measure, data)))
    try:
        async with httpx.AsyncClient(timeout=600) as c:
            import stufe   # priority for people: the profile's own recording goes first (not at shared speakers)
            r = await c.post(model_url("asr", "/v1/audio/transcriptions", cfg),
                             files={"file": (file.filename or "audio.wav", data)},
                             data=form, headers=dict(api_headers(), **stufe.headers(stufe.asr_level(request))))
    except (httpx.ConnectError, httpx.ConnectTimeout):
        for task in (spk, rv, quiet, fv):
            if task is not None:
                task.cancel()
        raise HTTPException(503, "asr_down: the speech recognition service does not answer")
    import verbrauch   # Verbrauchszähler: seconds heard, for the profile (or guests)
    verbrauch.heard("Frage hören", r, verbrauch.who_of(me))
    # a click, the chime or the room after an answer comes back as "Ja" or "Okay": no question (fixed rule)
    if r.status_code == 200:
        try:
            got = r.json()
        except ValueError:
            got = {}
        got = got if isinstance(got, dict) else {}
        why = stille.check(str(got.get("text") or ""), await quiet)
        if why:
            for task in (spk, rv, fv):
                if task is not None:
                    task.cancel()
            stille.note(why, echo.device_of(request).split(":")[0])
            return {"text": "", "ignored": why}
    else:
        quiet.cancel()
    # the Spark's own voice from another device (or leaking through this one) is no question: the
    # recording counts as silence (echo.py; profiles only)
    if me and r.status_code == 200:
        try:
            got = r.json()
        except ValueError:
            got = {}
        got = got if isinstance(got, dict) else {}
        secs = got.get("duration") if isinstance(got.get("duration"), (int, float)) else wav_seconds(data)
        dev = echo.device_of(request)
        why = echo.check(me["id"], dev, str(got.get("text") or ""), secs, now=ended)
        if why:
            for task in (spk, rv):
                if task is not None:
                    task.cancel()
            echo.note(why, dev.split(":")[0])
            return {"text": "", "ignored": why}
    if fv is not None and r.status_code == 200:
        try:
            why, v = await fv
        except Exception:   # unreadable audio: no numbers, the question counts as before
            why, v = None, {}
        fremdstimme.note(why, how, v, echo.device_of(request).split(":")[0])
        if why:
            if spk is not None:
                spk.cancel()
            return {"text": "", "ignored": why}
    elif fv is not None:
        fv.cancel()
    if rv is not None:
        # the voice belongs to exactly this recording: kept together with its words, so a "Ja" heard in
        # another recording (TV, another person) never borrows the owner's voice
        try:
            said = str(r.json().get("text") or "") if r.status_code == 200 else ""
        except ValueError:
            said = ""
        try:
            who, best = await rv
            room_mode.set_voice(me["id"], room, who or "", said, known=best >= th)
        except Exception:
            room_mode.set_voice(me["id"], room, "", said)
    if r.status_code != 200 and not me and not admin_cookie_ok(request):
        # guests get the code only: the service's text can name temporary files or internal addresses
        detail = {413: "audio_too_large", 415: "audio_unsupported", 503: "asr_busy"}.get(r.status_code, "asr_failed")
        return JSONResponse({"detail": detail}, status_code=r.status_code if r.status_code in (413, 415, 503) else 502)
    if spk is None or r.status_code != 200:
        return Response(r.content, status_code=r.status_code, media_type="application/json")
    out = r.json()
    try:
        uid, score = await spk
    except Exception:  # unreadable audio etc.: just no speaker
        uid, score = None, 0.0
    who = uid and profiles.by_id(uid)
    import live
    live.mark("Sprechererkennung", "Stimme erkannt" if who else "Stimme nicht erkannt")   # never whose
    if who:
        out["speaker"] = {"name": who["name"], "token": speakers.token(uid, me["id"]), "score": round(score, 3)}
    return out


@router.post("/api/test/tts", dependencies=[Depends(auth)])
async def test_tts(request: Request):
    cfg = load_config()
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(model_url("tts", "/v1/audio/speech", cfg), json=await request.json(),
                         headers=api_headers())
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"),
                    headers={k: v for k, v in r.headers.items() if k.lower() == "x-processing-seconds"})


@router.post("/api/test/tts-stream", dependencies=[Depends(auth)])
async def test_tts_stream(request: Request):
    """Passes the SSE stream through so the test page hears audio as it is generated."""
    cfg = load_config()
    body = await request.json()
    body.update(stream=True, response_format="pcm")
    c = httpx.AsyncClient(timeout=600)
    up = await c.send(c.build_request("POST", model_url("tts", "/v1/audio/speech", cfg),
                                      json=body, headers=api_headers()), stream=True)
    if up.status_code != 200:
        content = await up.aread()
        await up.aclose(); await c.aclose()
        return Response(content, status_code=up.status_code, media_type="application/json")

    async def relay():
        try:
            async for chunk in up.aiter_raw():
                yield chunk
        finally:
            await up.aclose(); await c.aclose()
    return StreamingResponse(relay(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/api/search-test", dependencies=[Depends(auth)])
async def search_test(q: str = "DGX Spark", url: str = ""):
    """Tests the address in the form (url), so it works before saving; else the saved one."""
    cfg = load_config()
    ccfg = cfg.get("chat", {})   # with the shipped defaults (common.load_config)
    if url:
        if not re.fullmatch(r"https?://\S+", url):
            raise HTTPException(400, "SearXNG address must start with http:// or https://")
        ccfg["search_url"] = url
    if not ccfg.get("search_url"):
        raise HTTPException(400, "no SearXNG address configured")
    async with httpx.AsyncClient() as c:
        t = time.time()
        try:
            text, sources = await web_search(c, dict(ccfg, search_pages=0), q)
        except Exception as e:
            raise HTTPException(502, f"SearXNG: {e}")
    return {"results": len(sources), "first": sources[:3], "seconds": round(time.time() - t, 2)}


# The TTS names its voices only while its engine answers: while it loads, restarts or is busy for a moment
# the list is empty, and a profile could only pick "Standard". The last list it gave stands in meanwhile
# (same model only); a Base model's voices are the cloned recordings, which the panel can list itself.
_last_voices = {}   # model -> the TTS's last non-empty answer


def _voice_names(v):
    return [x for x in (v.get("voices") or []) if isinstance(x, str) and 0 < len(x) <= 64][:200]


@router.get("/api/tts/voices", dependencies=[Depends(auth)])
async def tts_voices():
    cfg = load_config()
    model = str(cfg.get("tts", {}).get("model", ""))
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            # with the key: the front end's size gate turns away keyless /v1/ calls even from here (401)
            v = (await c.get(model_url("tts", "/v1/voices", cfg), headers=api_headers())).json()
        if not isinstance(v, dict):
            raise ValueError("not a JSON object")
    except Exception:
        v = {"model_kind": None, "voices": [], "languages": []}
    if _voice_names(v):
        _last_voices.clear()
        _last_voices[model] = dict(v, voices=_voice_names(v))
        return v
    if model in _last_voices:
        return dict(_last_voices[model], stale=True)
    if model.lower().endswith("-base"):
        return dict(v, model_kind="base", voices=clone_voices(), stale=True)
    return v


@router.get("/api/clone-voices", dependencies=[Depends(auth)])
def clone_voices():
    os.makedirs(VOICES_DIR, exist_ok=True)
    return sorted(f[:-4] for f in os.listdir(VOICES_DIR) if f.endswith(".wav"))


@router.post("/api/clone-voices", dependencies=[Depends(auth)])
async def add_clone_voice(name: str = Form(...), text: str = Form(""), file: UploadFile = File(...)):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name):
        raise HTTPException(400, "name: letters, digits, _ and - only")
    os.makedirs(VOICES_DIR, exist_ok=True)
    data = await file.read(60 * 1024**2 + 1)   # the size limit in front of the panel says the same
    if len(data) > 60 * 1024**2:
        raise HTTPException(413, "the recording is larger than 60 MB")
    if not data.startswith(b"RIFF"):  # mp3, m4a, webm, ...: the engine expects WAV
        p = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-loglevel", "error", "-protocol_whitelist", "file,pipe", "-i", "pipe:0", "-t", "120", "-ac", "1", "-ar", "24000",
            "-f", "wav", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        data, err = await p.communicate(data)
        if p.returncode or not data:
            raise HTTPException(400, f"could not read the audio file: {err.decode(errors='replace')[:200]}")
    with open(os.path.join(VOICES_DIR, name + ".wav"), "wb") as f:
        f.write(data)
    txt = os.path.join(VOICES_DIR, name + ".txt")
    if text.strip():
        with open(txt, "w") as f:
            f.write(text.strip())
    elif os.path.exists(txt):
        os.remove(txt)
    return {"ok": True}


@router.get("/api/clone-voices/{name}.wav", dependencies=[Depends(auth)])
def clone_voice_audio(name: str):
    path = os.path.join(VOICES_DIR, name + ".wav")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name) or not os.path.exists(path):
        raise HTTPException(404, "no such voice")
    return FileResponse(path, media_type="audio/wav")


@router.delete("/api/clone-voices/{name}", dependencies=[Depends(auth)])
def delete_clone_voice(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name):
        raise HTTPException(400, "bad name")
    for p in [os.path.join(VOICES_DIR, name + ext) for ext in (".wav", ".txt")] + \
            [os.path.join(VOICES_DIR, "kurz", name + ext) for ext in (".wav", ".txt", ".json")]:   # kurzref.py
        if os.path.exists(p):
            os.remove(p)
    return {"ok": True}


# A voice archive is a ZIP with <name>.wav, an optional <name>.txt (transcript of the reference)
# and voices.json describing the contents, so voices can move between Sparks or be backed up.
VOICE_NAME = re.compile(r"[A-Za-z0-9_\-]{1,40}")


@router.get("/api/clone-voices-export", dependencies=[Depends(auth)])
def export_clone_voices(names: str = ""):
    have = clone_voices()
    want = [n for n in names.split(",") if n] or have
    missing = [n for n in want if n not in have]
    if missing or not want:
        raise HTTPException(404, f"no such voice: {', '.join(missing)}" if missing else "no voices to export")
    buf, meta = io.BytesIO(), []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in want:
            z.write(os.path.join(VOICES_DIR, n + ".wav"), n + ".wav")
            entry = {"name": n, "audio": n + ".wav"}
            txt = os.path.join(VOICES_DIR, n + ".txt")
            if os.path.exists(txt):
                z.write(txt, n + ".txt")
                with open(txt) as f:
                    entry["transcript"] = f.read()
            meta.append(entry)
        z.writestr("voices.json", json.dumps({"format": "speech-spark-voices", "version": 1,
                                              "exported": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                              "voices": meta}, ensure_ascii=False, indent=2))
    fname = f"stimme-{want[0]}.zip" if len(want) == 1 else f"stimmen-{time.strftime('%Y-%m-%d')}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/api/clone-voices-import", dependencies=[Depends(auth)])
async def import_clone_voices(file: UploadFile = File(...), conflict: str = Form("rename")):
    """conflict: rename (keep both, the new one gets -2, -3, ...), overwrite or skip."""
    if conflict not in ("rename", "overwrite", "skip"):
        raise HTTPException(400, "conflict must be rename, overwrite or skip")
    try:
        raw = await file.read(200 * 1024**2 + 1)
        if len(raw) > 200 * 1024**2:
            raise HTTPException(413, "the file is larger than 200 MB")
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "not a ZIP file (export voices in the panel to get one)")
    # only flat <name>.wav / <name>.txt entries count; sizes are checked before anything is unpacked
    files = {}
    for info in z.infolist():
        base = info.filename.rsplit("/", 1)[-1]
        stem, _, ext = base.rpartition(".")
        if ext.lower() in ("wav", "txt") and VOICE_NAME.fullmatch(stem):
            limit = 50 << 20 if ext.lower() == "wav" else 64 << 10
            if info.file_size > limit:
                raise HTTPException(400, f"{base} is too large")
            files.setdefault(stem, {})[ext.lower()] = info
    if not files or len(files) > 200:
        raise HTTPException(400, "the ZIP holds no voices (expected <name>.wav files)" if not files else "too many voices")
    os.makedirs(VOICES_DIR, exist_ok=True)
    have, done = set(clone_voices()), []
    for name, parts in sorted(files.items()):
        if "wav" not in parts:
            continue
        audio = z.read(parts["wav"])
        if not audio.startswith(b"RIFF"):
            done.append({"name": name, "result": "skipped", "reason": "not a WAV file"})
            continue
        target = name
        if name in have:
            if conflict == "skip":
                done.append({"name": name, "result": "skipped", "reason": "exists"})
                continue
            if conflict == "rename":
                i = 2
                while f"{name[:36]}-{i}" in have:
                    i += 1
                target = f"{name[:36]}-{i}"
        with open(os.path.join(VOICES_DIR, target + ".wav"), "wb") as f:
            f.write(audio)
        txt = os.path.join(VOICES_DIR, target + ".txt")
        text = z.read(parts["txt"]).decode("utf-8", errors="replace").strip() if "txt" in parts else ""
        if text:
            with open(txt, "w") as f:
                f.write(text)
        elif os.path.exists(txt):
            os.remove(txt)
        have.add(target)
        done.append({"name": name, "result": "imported", "as": target})
    return {"voices": done}


# ---------------------------------------------------------------- measuring
bench_state = {"running": False, "log": []}


@router.get("/api/bench", dependencies=[Depends(auth)])
def bench_status():
    import bench
    out = {"running": bench_state["running"], "log": bench_state["log"][-40:], "result": None, "report": None,
           "rating": None}
    try:
        with open(bench.RESULT) as f:
            out["result"] = json.load(f)
        out["report"] = bench.report(out["result"])
        out["rating"] = bench.rate(out["result"], out["result"].get("previous"))
    except Exception:
        pass
    return out


@router.post("/api/bench", dependencies=[Depends(auth)])
async def bench_start():
    import bench
    if bench_state["running"]:
        raise HTTPException(409, "a measurement is already running")
    bench_state.update(running=True, log=["starting"])

    async def go():
        try:
            await bench.Bench(log=bench_state["log"].append).run()
        except Exception as e:
            bench_state["log"].append(f"failed: {type(e).__name__}: {e}")
        finally:
            bench_state["running"] = False
    spawn(go())
    return {"started": True}


# ---------------------------------------------------------------- Sicherheit auf einen Blick (V01.0.262)
# Fixed checks with a traffic light; the page writes the sentences. Only states and numbers, no secrets.
@router.get("/api/admin/security-glance", dependencies=[Depends(auth)])
def security_glance(request: Request):
    cfg = load_config()
    chat, panel_cfg = cfg.get("chat", {}), cfg.get("panel", {})
    items = []

    def add(key, lvl, **extra):
        items.append(dict(key=key, lvl=lvl, **extra))

    add("admin_mfa", "ok" if mfa.enabled(mfa.ADMIN) else "bad")
    last = backup.listing()
    age = int((time.time() - last[0]["created"]) / 86400) if last else None
    add("backup", "bad" if age is None or age > 3 else "warn", days=age, count=len(last))
    short = profiles.short_pins()
    add("short_pins", "warn" if short else "ok", names=short[:10], count=len(short))
    no_mfa = [r["name"] for r in coadmin.listing()["users"] if not r["mfa"]]
    if no_mfa:
        add("role_mfa", "warn", names=no_mfa[:10])
    add("https", "ok" if guard.https(request) else "warn")
    add("public", "warn" if chat.get("public") else "ok")
    add("allow_lan", "warn" if panel_cfg.get("allow_lan") else "ok")
    add("session_days", "ok" if panel_cfg.get("session_days", 30) <= 30 else "warn", days=panel_cfg.get("session_days", 30))
    import wachposten
    wp = wachposten.for_status()
    add("wachposten", "ok" if wp["on"] else "warn", week=wp["week"])
    add("audit_chain", "bad" if guard.alerts() else "ok")
    for k in ("headers", "updates", "vault", "outside"):   # fixed protections of the panel itself
        add(k, "ok")
    order = {"bad": 0, "warn": 1, "ok": 2}
    items.sort(key=lambda x: order[x["lvl"]])
    return {"items": items}
