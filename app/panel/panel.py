"""Speech on DGX Spark: web panel for config and monitoring.

This file starts the app and serves the page; the API lives in modules next to it:
core (paths, logins), monitor (samples), account (login and the profile's own data),
chat (assistant, tools, learning, watch), admin (settings, services, voices), update."""
import asyncio
import gzip
import hashlib
import os
import re
import sys
import time

import psutil
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import TLS_DIR, BodyLimit, load_config, quiet_access_log  # noqa: E402
from core import spawn, ADMIN_IDLE, COOKIE, SERVICES, STATIC, admin_cookie_ok, app_version, renewed_admin_cookie  # noqa: E402
from core import main_loop  # noqa: E402
from monitor import history, service_health, system_stats  # noqa: E402
import steuer  # noqa: E402
from chat import LEARN_EVERY, learn_once  # noqa: E402
from update import update_lock  # noqa: E402
import account  # noqa: E402
import calendars  # noqa: E402
import mail  # noqa: E402
import vorwaermen  # noqa: E402
import vorrat  # noqa: E402
import halive  # noqa: E402
import coadmin  # noqa: E402
import guard  # noqa: E402
import homeassistant  # noqa: E402
import profiles  # noqa: E402
import admin  # noqa: E402
import chat  # noqa: E402
import memtidy  # noqa: E402
import quality  # noqa: E402
import update  # noqa: E402
import system  # noqa: E402
import backup  # noqa: E402
import documents  # noqa: E402,F401  (registers its routes)
import health  # noqa: E402
import push  # noqa: E402
import proactive  # noqa: E402
import rechnerblick  # noqa: E402
import room  # noqa: E402
import roomlive  # noqa: E402
import tidy  # noqa: E402
import mailidle  # noqa: E402
import mailcode  # noqa: E402,F401  (hooks itself on mailidle.on_new)
import mailregeln  # noqa: E402
import senden  # noqa: E402
import mailstil  # noqa: E402
import weather  # noqa: E402
import contacts  # noqa: E402
import parcels  # noqa: E402
import fuerdich  # noqa: E402
import vorgaenge  # noqa: E402
import gemerkt  # noqa: E402  (Gemerkt-Hinweis: Rückgängig under an answer, the card of what was learned by itself)
import meinedaten  # noqa: E402  (Alle meine Daten herunterladen: the ZIP after a fresh code, picked up once)
import siegel  # noqa: E402  (memory and conversations sealed at rest: the one-time sealing, „Wieder einlesen“)
import ichweiss  # noqa: E402
import extras  # noqa: E402
import telegram  # noqa: E402
import tasks  # noqa: E402
import wyoming  # noqa: E402
import telefon  # noqa: E402
import telefon_ich  # noqa: E402
import vorrang  # noqa: E402
import transit  # noqa: E402
import feeds  # noqa: E402
import esp32  # noqa: E402
import iphone  # noqa: E402
import pebblewatch  # noqa: E402
import terminal  # noqa: E402
import android  # noqa: E402
import appupdate  # noqa: E402
import appmerken  # noqa: E402
import pruefzugang  # noqa: E402
import apns  # noqa: E402
import logfilter  # noqa: E402
import agent  # noqa: E402
import auftragsplan  # noqa: E402
import images  # noqa: E402
import wissen  # noqa: E402
import docembed  # noqa: E402
import nachsortieren  # noqa: E402
import messages  # noqa: E402
import intent  # noqa: E402
import tracelog  # noqa: E402
import weiche  # noqa: E402
import technik  # noqa: E402
import lokal  # noqa: E402
import features  # noqa: E402
import remarkable  # noqa: E402
import rmpapier  # noqa: E402
import rmplus  # noqa: E402
import join  # noqa: E402
import onboard  # noqa: E402
import hintergrund  # noqa: E402
import stufe  # noqa: E402
import today  # noqa: E402
import offsite  # noqa: E402
import doclingdienst  # noqa: E402
import suchpruefung  # noqa: E402
import wissensbuch  # noqa: E402
import fund  # noqa: E402
import dungeon  # noqa: E402
import dungeon_dingbild  # noqa: E402
import dungeon_pruefstand  # noqa: E402
import dungeon_erzaehlstand  # noqa: E402
import dungeon_import  # noqa: E402
import dungeon_geschichten  # noqa: E402
import dungeon_regelseite  # noqa: E402
import dungeon_musik  # noqa: E402
import dungeon_echt  # noqa: E402
import dungeon_knapp  # noqa: E402
import dungeon_fluestern  # noqa: E402
import dungeon_wunsch  # noqa: E402
import dungeon_lied  # noqa: E402
import dungeon_rast  # noqa: E402
import dungeon_chronik  # noqa: E402
import dungeon_buch  # noqa: E402
import dungeon_karte  # noqa: E402
import dungeon_gesicht  # noqa: E402
import dungeon_wappen  # noqa: E402
import wissenskarte  # noqa: E402
import mcpserver  # noqa: E402
import meinmcp  # noqa: E402
import live  # noqa: E402
import hamelden  # noqa: E402
import notaus  # noqa: E402
import hilfe  # noqa: E402
import tipps  # noqa: E402
import saetze  # noqa: E402
import spickzettel  # noqa: E402
import schreib  # noqa: E402
import begleiter  # noqa: E402
import fernsicht  # noqa: E402
import systemone  # noqa: E402
import geraeteupdate  # noqa: E402
import dienstwacht  # noqa: E402
import offline  # noqa: E402
import wartung  # noqa: E402
import faelle  # noqa: E402
import berater  # noqa: E402
import speicher  # noqa: E402
import nas  # noqa: E402
import nasquelle  # noqa: E402
import auslassen  # noqa: E402
import nasablage  # noqa: E402
import naszustand  # noqa: E402
import gehaeuse  # noqa: E402
import schirm  # noqa: E402
import rundlauf  # noqa: E402
import wachposten  # noqa: E402
import nashilfe  # noqa: E402
import meldung  # noqa: E402
import ghtoken  # noqa: E402
import docmake  # noqa: E402
import bilder  # noqa: E402
import musik  # noqa: E402
import verlauf  # noqa: E402
import klaeren  # noqa: E402
import chats  # noqa: E402
import chatsec  # noqa: E402
import anrufe  # noqa: E402
import verbund  # noqa: E402
import verbrauch  # noqa: E402
import modellseite  # noqa: E402
import werkstattseite  # noqa: E402
import weiche_abstimmen  # noqa: E402
import weiche_unklar  # noqa: E402
import praxistest  # noqa: E402
import kalenderserver  # noqa: E402
import zustellung  # noqa: E402
import geteilt  # noqa: E402
import mailansicht  # noqa: E402
import mitschreiblink  # noqa: E402
import mitteilungen  # noqa: E402
import kontaktserver  # noqa: E402
import einladung  # noqa: E402
import fernzugang  # noqa: E402
import spontanhilfe  # noqa: E402
import ferndateien  # noqa: E402
import fernbild  # noqa: E402
import fernanker  # noqa: E402
import fernnotiz  # noqa: E402
import fernordner  # noqa: E402
import ferngross  # noqa: E402

# no /docs, /redoc or /openapi.json: a map of every path for guests, and Swagger from a CDN
app = FastAPI(title="Speech on DGX Spark", docs_url=None, redoc_url=None, openapi_url=None)
for _module in (account, admin, chat, chats, chatsec, verbund, anrufe, update, system, proactive, room, roomlive, tidy, mailstil, fuerdich, ichweiss, weather, contacts, parcels, telegram, tasks, esp32, iphone, pebblewatch, terminal, android, appupdate, appmerken, pruefzugang, apns, transit, feeds, logfilter, agent, auftragsplan, images, messages, intent, wissen, tracelog, lokal, features, remarkable, rmplus, rmpapier, join, onboard, hintergrund, stufe, today, offsite, doclingdienst, suchpruefung, wissensbuch, fund, gemerkt, meinedaten, siegel, dungeon_dingbild, dungeon_musik, dungeon_echt, dungeon_lied, dungeon_knapp, dungeon_fluestern, dungeon_wunsch, dungeon_rast, dungeon_chronik, dungeon_buch, dungeon_regelseite, dungeon_pruefstand, dungeon_erzaehlstand, dungeon_import, dungeon_geschichten, dungeon, dungeon_karte, dungeon_gesicht, dungeon_wappen, wissenskarte, mcpserver, meinmcp, live, hamelden, notaus, hilfe, tipps, saetze, spickzettel, schreib, begleiter, fernsicht, systemone, geraeteupdate, meldung, ghtoken, docmake, weiche, weiche_abstimmen, weiche_unklar, dienstwacht, offline, wartung, faelle, berater, speicher, nashilfe, nas, nasquelle, auslassen, nasablage, naszustand, gehaeuse, schirm, verlauf, klaeren, technik, bilder, musik, verbrauch, modellseite, werkstattseite, praxistest, telefon, telefon_ich, kalenderserver, kontaktserver, einladung, zustellung, geteilt, vorgaenge, mailansicht, mitschreiblink, mitteilungen, fernzugang, spontanhilfe, ferndateien, fernbild, fernanker, fernnotiz, fernordner, ferngross):
    app.include_router(_module.router)
app.middleware("http")(update_lock)


def _may_upload(scope):
    """Big uploads only from someone who could be allowed (the real check comes after)."""
    req = Request(scope)
    if req.headers.get("authorization") or admin_cookie_ok(req) or profiles.current(req) or coadmin.session(req):
        return True
    if scope.get("path") == verbund.BLOB_PATH:   # another Spark's file: only from an allowed Spark with a known key
        return verbund.blob_gate(req.headers)
    return scope.get("path") == "/api/test/asr" and bool(load_config().get("chat", {}).get("public", False))


# Request bodies: small by default; uploads only where they belong and only up to their limit.
app.add_middleware(BodyLimit, default=2 * 1024**2, gate=_may_upload, limits=[
    ("/api/backups-upload", backup.MAX_UPLOAD + 1024**2), ("/api/clone-voices-import", 200 * 1024**2),
    ("/api/clone-voices", 60 * 1024**2), ("/api/test/asr", 51 * 1024**2), ("/api/desk/dictate", begleiter.MAX_AUDIO), ("/api/desk/hear", begleiter.MAX_HEAR), ("/api/desk/file", begleiter.MAX_UPLOAD + 64 * 1024), ("/api/desk/screen", begleiter.MAX_SHOT + 64 * 1024), ("/api/desk/meeting/chunk", begleiter.MEET_CHUNK), ("/api/desk/view/frame", fernsicht.MAX_FRAME + 4096), ("/api/profile/desk/send", begleiter.INBOX_FILE + 64 * 1024), ("/api/logverbose", 4096), ("/api/profile/voice", 11 * 1024**2),
    ("/api/profile/docs", lambda: wissen.pdf_bytes() + 1024**2), ("/api/chat/image", images.MAX_BYTES + 64 * 1024), ("/api/musik/hochladen", musik.MAX_UPLOAD + 64 * 1024),
    ("/api/chats/media", max(chats.MAX_FILE, chatsec.MAX_BLOB) + chatsec.MAX_BOX + 64 * 1024), ("/api/chats", 128 * 1024), ("/api/verbund/blob", lambda: chats.MAX_FILE + 1024), ("/api/verbund", verbund.MAX_BODY + 1024), ("/api/anrufe", anrufe.MAX_SIGNAL + 4096), ("/api/admin/fernzugang/dateien", lambda: ferndateien.max_bytes() + 64 * 1024), ("/api/admin/fernzugang/gross", ferngross.TEIL + 64 * 1024), ("/api/hilfe", spontanhilfe.MAX_BODY), ("/api/admin/spontanhilfe", spontanhilfe.MAX_BODY), ("/api/admin/verbund", 16 * 1024), ("/api/chat", 4 * 1024**2), ("/api/login", 64 * 1024),
    ("/api/profile/login", 64 * 1024), ("/mcp", mcpserver.MAX_BODY), ("/oauth/", mcpserver.MAX_JSON)],
    gated=("/api/backups-upload", "/api/clone-voices", "/api/test/asr", "/api/desk/dictate", "/api/desk/hear", "/api/desk/file", "/api/desk/screen", "/api/desk/meeting/chunk", "/api/profile/desk/send", "/api/profile/voice", "/api/profile/docs",
           "/api/chat/image", "/api/musik/hochladen", "/api/admin/fernzugang/dateien", "/api/admin/fernzugang/gross", "/api/chats/media", "/api/verbund/blob", "/mcp"))


# Browser protection on every answer (V01.0.262): no other page may show the panel in a frame (clickjacking),
# no guessing of file types, no address leaks to other sites, microphone and camera only for the panel itself,
# and on https the browser keeps using https. A page that sets its own policy (wissen.py "Ansehen") keeps it.
SECURITY_HEADERS = {
    "X-Frame-Options": "SAMEORIGIN",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "microphone=(self), camera=(self), geolocation=(), payment=(), usb=(), serial=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
    # strict since V01.0.286 (plan „Bedienung gesamt“ D1 Stufe 2): scripts only as files from the panel, no inline
    # script, no inline handler, no eval; styles may stay inline (style attributes run no code, older Safari in the
    # iPhone app needs them). Pictures and sound also from data:/blob: (recordings, QR codes, the face).
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; "
                               "worker-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
                               "object-src 'none'; form-action 'self'",
}


def protect(request, response):
    for k, v in SECURITY_HEADERS.items():
        if k.lower() not in response.headers:
            response.headers[k] = v
    if guard.https(request):
        response.headers.setdefault("Strict-Transport-Security", "max-age=15552000")


@app.middleware("http")
async def sessions(request: Request, call_next):
    """Refuses changes from foreign pages, writes the change log and renews logins in use."""
    if not guard.same_origin(request, (COOKIE, profiles.COOKIE, live.COOKIE)):
        guard.log("foreign_page_refused", ip=guard.client_ip(request), path=request.url.path,
                  origin=request.headers.get("origin", ""))
        r = guard.foreign_page()
        protect(request, r)
        return r
    if request.method in ("POST", "PUT") and request.url.path.startswith("/api/") and verbrauch.on():
        # Verbrauchszähler: what this request asks the models (also jobs it starts) counts for its profile
        me = profiles.current(request)
        verbrauch.WHO.set(me["id"] if me else verbrauch.SPARK)
    response = await call_next(request)
    path = request.url.path
    if guard.logged(path, request.method):
        prof = profiles.current(request)
        basic = request.headers.get("authorization", "").startswith("Basic ") and response.status_code < 400
        elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
        main = bool(request.scope.get("speech_main_admin")) or ((admin_cookie_ok(request) or basic) and not elev)
        who = "admin" if main else elev["name"] if elev else (prof or {}).get("name", "guest")
        # by: an admin action, by the main admin or an admin profile (Logs → Admin-Protokoll)
        by = "main" if request.scope.get("speech_main_admin") else elev["id"] if elev else None
        guard.log("change", ip=guard.client_ip(request), who=who, uid=(prof or {}).get("id"), by=by,
                  method=request.method, path=path, status=response.status_code)
    protect(request, response)
    if path.startswith("/api/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"   # switches and states: never from a browser or proxy cache
    if path.startswith("/api/") and response.status_code < 400:
        admin_value, user_value = renewed_admin_cookie(request), profiles.renewed_cookie(request)
        if admin_value:
            response.set_cookie(COOKIE, admin_value, max_age=ADMIN_IDLE, httponly=True, samesite="strict")
        if user_value:
            response.set_cookie(profiles.COOKIE, user_value, max_age=profiles.session_secs(),
                                httponly=True, samesite="lax")
    if guard.https(request):  # on https (also behind a proxy) logins never travel over plain http
        raw = response.headers.getlist("set-cookie") if hasattr(response.headers, "getlist") else []
        if raw and any("secure" not in c.lower() for c in raw):
            del response.headers["set-cookie"]
            for c in raw:
                response.headers.append("set-cookie", c if "secure" in c.lower() else c + "; Secure")
    return response


@app.middleware("http")
async def emergency(request: Request, call_next):
    """Notaus (notaus.py): from stage 1 nothing from outside but the page and the Notaus itself, in stage 3 at home
    only logins, reading Zustand and the logs, and lifting it. Decided before any route reads the request."""
    held = notaus.mine_gate(request) or notaus.gate(request)
    if held:
        status, detail = held
        r = JSONResponse({"detail": detail, "notaus": notaus.level()}, status_code=status,
                         headers={"Retry-After": "60", "Cache-Control": "no-store"})
        protect(request, r)
        return r
    return await call_next(request)


# Seiten sichtbar laden (plan seiten-laden.md): a read of the page that took long is one line in Zustand → Logs →
# Diagnose ("seite: slow GET /api/profile/calendar 4.2 s"), so it shows which page waits on what. Only the route's
# pattern and the time, never the query, ids or names; one line per route a minute at most (Zustand polls every 3 s).
SLOW_READ = 1.5
SLOW_EVERY = 60
# reads that wait on purpose: the Android app's lasting connection (android.py) and the Begleiter's held request
# (begleiter.ACT_WAIT, 25 s; Dominik 2026-10-19 saw it as "slow GET /api/desk/wait 25.3 s")
WAITS = ("/api/android/wait", "/api/desk/wait")
_slow_said = {}


def slow_read(method, route, took, now):
    """The Diagnose line for a slow read, or None (fast, not a read, or said in the last minute)."""
    if method != "GET" or took < SLOW_READ or not route.startswith("/api/") or route in WAITS:
        return None
    if now - _slow_said.get(route, -SLOW_EVERY) < SLOW_EVERY:
        return None
    if len(_slow_said) > 500:
        _slow_said.clear()
    _slow_said[route] = now
    return f"seite: slow GET {route} {took:.1f} s"


@app.middleware("http")
async def slow_reads(request: Request, call_next):
    t0 = time.monotonic()
    response = await call_next(request)
    now = time.monotonic()
    route = getattr(request.scope.get("route"), "path", None) or ("/api/?" if request.url.path.startswith("/api/") else "")
    line = slow_read(request.method, route, now - t0, now)
    if line:
        print(line, flush=True)
    return response


@app.exception_handler(notaus.NotausAktiv)
async def held_off(request: Request, exc: notaus.NotausAktiv):
    """An action the Notaus held off deep down (the last line of defence): said plainly, never a 500."""
    return JSONResponse({"detail": str(exc), "notaus": notaus.level()}, status_code=503)


@app.on_event("startup")
async def sampler():
    live.mark("Spark", "Panel gestartet · " + (re.sub(r"[^A-Za-z0-9.\-]", "", app_version())[:32] or "?"))

    async def loop():
        psutil.cpu_percent()
        while True:
            try:
                cfg = load_config()
                # nvidia-smi and psutil block for a moment: off the event loop; both health checks at once
                g, s = await asyncio.to_thread(lambda: (steuer.gpu() or {}, system_stats()))
                await asyncio.to_thread(rechnerblick.probe)     # both computers' cards when the models run apart
                h = dict(zip(SERVICES, await asyncio.gather(*(service_health(n, cfg) for n in SERVICES))))
                health.check_memory(s["mem_avail_gib"], cfg)
                live.services(h, cfg)
                history.append({"t": time.time(), "gpu": g.get("util"), "cpu": s["cpu"],
                                "avail": s["mem_avail_gib"], "temp": g.get("temp"), "power": g.get("power"),
                                "asr_req": (h["asr"] or {}).get("requests"),
                                "tts_req": (h["tts"] or {}).get("requests")})
            except Exception as e:
                print("sampler:", e, flush=True)
            await asyncio.sleep(3)
    spawn(loop())


@app.on_event("startup")
async def stability():
    """Watchdog, daily backup and the live check after an update."""
    async def watchdog():
        while True:
            await asyncio.sleep(health.WATCH_EVERY)
            try:
                await health.watch_once(update.update_running)
            except Exception as e:
                print("watchdog:", type(e).__name__, e, flush=True)

    async def backups():
        while True:
            try:
                if backup.due():   # packing is CPU and disk work: in a pause, with low priority
                    item = await vorrang.in_thread("Sicherung", backup.create, "daily")
                    print("backup:", item["name"], flush=True)
                if offsite.due():  # the encrypted copy to the NAS (off unless switched on), with the change log
                    await offsite.run("daily")
                if guard.chain_due():   # the change log's chain, once a day and after a start
                    await vorrang.in_thread("Protokoll prüfen", guard.chain_daily)
            except Exception as e:
                guard.log("backup_failed", detail=f"{type(e).__name__}: {e}"[:200])
            await asyncio.sleep(3600)

    async def after_update():
        if health.after_update_due(update.update_progress()):
            while wartung.state()["on"]:     # a Wartungspause (wartung.py): the check comes after it
                await asyncio.sleep(wartung.EVERY)
            await health.ready(load_config())
            res = await health.livecheck("after update")
            print("livecheck: after update:", "ok" if res and res["ok"] else res, flush=True)
            if res and res["ok"]:
                await quality.run("after update")
    async def reminders():
        # due reminders on their own: a slow briefing or proactive check never holds them up
        while True:
            await asyncio.sleep(15)
            try:
                if notaus.blocks("gespraech"):   # Notaus stage 3: not even reminders ring
                    continue
                await push.due_reminders()
            except Exception as e:
                print("reminders: push failed:", type(e).__name__, e, flush=True)

    async def every_minute():
        # each minute once, even when the work of the one before took longer than a minute
        last = None
        while True:
            minute = int(time.time()) // 60
            if minute != last:
                last = minute
                # an error here must not end the loop (briefings, Von selbst, jobs and the night update with it)
                try:
                    room.sweep()
                except Exception as e:
                    print("room: sweep failed:", type(e).__name__, flush=True)
                try:
                    held = notaus.blocks("auto")   # Notaus stage 2: nothing happens by itself (notaus.py)
                except Exception as e:
                    print("notaus:", type(e).__name__, flush=True)
                    held = True
                if held:
                    await asyncio.sleep(5)
                    continue
                try:
                    await chat.due_briefings()
                except Exception as e:
                    print("briefing:", type(e).__name__, e, flush=True)
                try:
                    await proactive.due_once()
                except Exception as e:
                    print("proactive:", type(e).__name__, e, flush=True)
                try:   # Meldung ans genutzte Gerät: a note nobody saw comes once to the phone app (zustellung.py)
                    await zustellung.follow()
                except Exception as e:
                    print("push: nachfassen", type(e).__name__, flush=True)
                try:   # Offen: „Später“ is over → the card comes back (vorgaenge.py)
                    await vorgaenge.due()
                except Exception as e:
                    print("vorgang: due", type(e).__name__, flush=True)
                try:
                    await extras.due_once()
                except Exception as e:
                    print("extras:", type(e).__name__, e, flush=True)
                try:   # Dungeon-Master: a turn whose time is over closes, „Du bist dran“ and the game date (dungeon.py)
                    await dungeon.due_once()
                except Exception as e:
                    print("dungeon: melden", type(e).__name__, flush=True)
                try:   # Dungeon-Master: pictures of named finds, the catalog's run at night (dungeon_dingbild.py)
                    await dungeon_dingbild.due()
                except Exception as e:
                    print("dungeon: dingbild | due", type(e).__name__, flush=True)
                try:   # Dungeon-Master: the balance bench once a night (dungeon_pruefstand.py)
                    await dungeon_pruefstand.due()
                except Exception as e:
                    print("dungeon: pruefstand | due", type(e).__name__, flush=True)
                try:   # Dungeon-Master: the narrator bench once a night with the scenes from reported errors (dungeon_erzaehlstand.py)
                    await dungeon_erzaehlstand.due()
                except Exception as e:
                    print("dungeon: erzaehlstand | due", type(e).__name__, flush=True)
                try:
                    await agent.due_once()
                except Exception as e:
                    print("agent:", type(e).__name__, flush=True)
                try:
                    await appupdate.due_once()
                except Exception as e:
                    print("iphone: update notice failed:", type(e).__name__, flush=True)
                try:
                    await update.night_once()      # "Heute Nacht einspielen" (update.py), off by default
                except Exception as e:
                    print("update: overnight failed:", type(e).__name__, flush=True)
            await asyncio.sleep(5)
    spawn(reminders())
    spawn(telegram.loop())
    spawn(wyoming.loop())
    spawn(telefon.loop())
    spawn(esp32.fetch_loop())
    spawn(android.fetch_loop())
    spawn(begleiter.fetch_loop())
    spawn(geraeteupdate.loop())
    spawn(dienstwacht.loop())
    spawn(rundlauf.loop())
    spawn(wachposten.loop())
    spawn(modellseite.melde_loop())
    spawn(wartung.loop())
    spawn(berater.loop())
    spawn(speicher.loop())
    nasquelle.clean_tmp()
    spawn(nasquelle.loop())
    spawn(nasablage.loop())
    spawn(naszustand.loop())
    spawn(gehaeuse.loop())
    spawn(werkstattseite.loop())
    spawn(dungeon_musik.loop())   # KI-Dungeon-Master: music made ahead, one piece after everybody else
    spawn(schirm.loop())
    spawn(every_minute())
    spawn(watchdog())
    spawn(backups())
    spawn(after_update())


@app.on_event("startup")
async def nas_move():
    """S1 (nas.py): Eigener Speicher and the backup to the NAS keep their login in one NAS connection."""
    await asyncio.to_thread(nas.migrate_all)


@app.on_event("startup")
async def mail_tidy():
    """Tidying inboxes (see tidy.py): each minute the mailboxes whose interval is due; the language
    model only sorts while nobody is talking to the assistant."""
    async def loop():
        while True:
            await asyncio.sleep(60)
            if notaus.blocks("auto"):
                continue
            try:
                await tidy.due_once(idle=not vorrang.speaking())
            except Exception as e:
                print("mail tidy:", type(e).__name__, e, flush=True)
    spawn(loop())


@app.on_event("startup")
async def mail_rules():
    """Mail-Regeln (mailregeln.py): each minute the profiles whose rules are due look at their new inbox mail."""
    async def loop():
        while True:
            await asyncio.sleep(60)
            if notaus.blocks("auto"):
                continue
            try:
                await mailregeln.due_once()
            except Exception as e:
                print("mail: rules loop failed |", type(e).__name__, flush=True)
            try:
                await senden.later_due_once()   # Später senden: what is due goes out (each mail once)
            except Exception as e:
                print("mail: send later loop failed |", type(e).__name__, flush=True)
    spawn(loop())


@app.on_event("startup")
async def doc_reader():
    """Documents (wissen.py): pictures and scans read by the language model, meaning vectors; one step
    at a time and only while nobody is talking to the assistant."""
    async def loop():
        while True:
            await asyncio.sleep(20)
            try:
                if not notaus.blocks("gespraech"):
                    while await wissen.due_once(idle=wissen.quiet()) in ("page", "vectors", "kopf"):
                        await asyncio.sleep(1)
            except Exception as e:
                print("documents:", type(e).__name__, e, flush=True)
            docembed.idle_stop()     # also during Notaus, after an error or a "Steckbrief": idle time ends it
            nachsortieren.idle_stop()
    spawn(loop())


@app.on_event("startup")
async def remarkable_sync():
    """reMarkable notebooks (remarkable.py): each minute one profile whose comparison is due, never
    while someone is talking (vorrang.py)."""
    async def loop():
        while True:
            await asyncio.sleep(60)
            if notaus.blocks("internet"):   # the reMarkable cloud is on the internet
                continue
            try:
                await remarkable.due_once(idle=not vorrang.speaking())
                await rmplus.due_once(idle=not vorrang.speaking())    # Morgenblatt, @Spark, guide ... (rmplus.py)
                await dungeon_buch.due_once(idle=not vorrang.speaking())   # the hero books after a round (dungeon_buch.py)
            except Exception as e:
                print("remarkable:", type(e).__name__, flush=True)
    spawn(loop())


@app.on_event("startup")
async def seal_profile_data():
    """Memory and conversations of older versions get sealed once, after a backup „vor-siegel“ (siegel.py)."""
    spawn(siegel.migrate_later())


@app.on_event("startup")
def seal_secrets():
    """Calendar passwords and Home Assistant tokens from older versions get encrypted once."""
    for uid in profiles.user_ids():
        try:
            calendars.seal_stored(uid)
            homeassistant.seal_stored(uid)
        except Exception as e:
            print("vault: sealing secrets failed:", type(e).__name__, e, flush=True)


@app.on_event("startup")
async def anrufe_loop():
    """Anrufe (anrufe.py): the Vermittler as the switches say, every minute; calls nobody ended."""
    spawn(anrufe.loop())


@app.on_event("startup")
async def mail_fresh():
    """E-Mail (mail.keep_fresh): the inbox of whoever read it lately is fetched anew in the background."""
    spawn(mail.keep_fresh_loop())
    spawn(mailidle.loop())


@app.on_event("startup")
async def calendar_fresh():
    """Vorrat je Profil (vorrat.loop): calendars, weather, parcels and „Für dich“ of whoever used them lately are read
    anew in the background, so the assistant answers from memory."""
    spawn(vorrat.loop())
    spawn(halive.loop())   # Home Assistant live: a copy of the states for active profiles (halive.py)
    main_loop[0] = asyncio.get_running_loop()   # core.later: page changes behind the page


@app.on_event("startup")
async def warm_start():
    """Vorwärmen (vorwaermen.py): a profile that signs in or opens the panel or its app is read ahead from here."""
    vorwaermen.start(asyncio.get_running_loop())


@app.on_event("startup")
async def verbund_queue():
    """Chats mit anderen Sparks (verbund.py): what waits for another Spark goes out every 30 seconds, new ones at once."""
    spawn(verbund.loop())


@app.on_event("startup")
def messages_into_chats():
    """Once after V01.0.488: the old mailboxes of "Nachrichten" into the chats (messages.migrate_all)."""
    try:
        messages.migrate_all()
    except Exception as e:
        print("messages: moving into chats failed:", type(e).__name__, flush=True)


@app.on_event("startup")
async def learner():
    async def loop():
        while True:
            await asyncio.sleep(LEARN_EVERY)
            if notaus.blocks("auto"):   # Notaus stage 2: nothing is learned or tidied in the memory
                continue
            try:
                n = await learn_once()
                if n:
                    print(f"gedaechtnis: learned {n} fact(s) from conversations", flush=True)
            except Exception as e:
                print("learning:", type(e).__name__, e, flush=True)
            try:
                if not vorrang.speaking():   # never while someone is talking (vorrang.py)
                    uid = await memtidy.due_once()
                    if uid:
                        print("memtidy: checked a profile", flush=True)
            except Exception as e:
                print("memtidy:", type(e).__name__, e, flush=True)
            try:
                if not vorrang.speaking():   # Gedächtnis-Themen (gedaechtnis.py): only for showing Ich → Gedächtnis
                    import gedaechtnis
                    await gedaechtnis.topics_once()
            except Exception as e:
                print("gedaechtnis: themen", type(e).__name__, flush=True)
    spawn(loop())


_PAGE = {}
_TAG = {}   # path -> (mtime, size, fingerprint)


def file_tag(path):
    """The fingerprint of a style or script: the first 12 hex digits of its SHA-256. It is the ?v= on the page's
    links, so after an update only files that really changed are loaded again (V01.0.750); before, every update
    (several a day) loaded all 2.2 MB once more."""
    st = os.stat(path)
    hit = _TAG.get(path)
    if not hit or hit[:2] != (st.st_mtime, st.st_size):
        with open(path, "rb") as f:
            hit = _TAG[path] = (st.st_mtime, st.st_size, hashlib.sha256(f.read()).hexdigest()[:12])
    return hit[2]


def page_html():
    """index.html with the fingerprint of each file on every style and script link (/static/js/chat.js?v=3fa9c0d1e2b4,
    file_tag) and the version in <meta name="spark-version">: after an update the browser loads the changed files at
    once (no Strg+F5, also behind a caching proxy), and an open page sees that a newer version is there (base.js)."""
    path = os.path.join(STATIC, "index.html")
    ver = re.sub(r"[^A-Za-z0-9.\-]", "", app_version())[:32] or "0"
    key = (ver, os.path.getmtime(path))
    if _PAGE.get("key") != key:
        with open(path, encoding="utf-8") as f:
            html = f.read()
        html = re.sub(r'((?:href|src)="/static/((?:js/)?[a-z0-9\-]+\.(?:css|js)))"',
                      lambda m: f'{m.group(1)}?v={file_tag(os.path.join(STATIC, m.group(2)))}"', html)
        html = html.replace("<head>", f'<head>\n<meta name="spark-version" content="{ver}">', 1)
        _PAGE.update(key=key, html=html, gz=gzip.compress(html.encode("utf-8"), 6, mtime=0))
    return _PAGE["html"]


@app.get("/")
def index(request: Request):
    # never stored: the page names the current files, those are only revalidated (no-cache). Gzipped when the browser
    # takes it (212 KB → about 40 KB); the page is the same for everybody and holds no secret (no BREACH target).
    html = page_html()
    head = {"Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0", "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", "").lower():
        return Response(_PAGE["gz"], media_type="text/html; charset=utf-8", headers={**head, "Content-Encoding": "gzip"})
    return HTMLResponse(html, headers=head)


# App files (installable assistant). Public like the start page: they hold no data.
PUBLIC_FILES = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png",
                "apple-touch-icon.png": "image/png", "favicon-32.png": "image/png",
                "manifest.webmanifest": "application/manifest+json"}


_GZ = {}   # path -> (mtime, size, gzipped bytes)


def _asset(request: Request, path, media):
    """A style or script of the page. Gzipped when the browser takes it (a third of the size; kept in memory per
    file version). With ?v= of its own fingerprint (file_tag, the start page) the browser keeps it a year without
    asking: changed content gets another ?v=. With ?v= of the running version (live.html, scripts loading scripts)
    a day (an update changes ?v=; not longer, in case a file was fetched mid-update). Else revalidated (no-cache)."""
    ver = re.sub(r"[^A-Za-z0-9.\-]", "", app_version())[:32] or "0"
    v = request.query_params.get("v")
    cache = ("public, max-age=31536000, immutable" if v == file_tag(path) else
             "public, max-age=86400" if v == ver else "no-cache")
    if "gzip" not in request.headers.get("accept-encoding", "").lower():
        return FileResponse(path, media_type=media, headers={"Cache-Control": cache, "Vary": "Accept-Encoding"})
    st = os.stat(path)
    hit = _GZ.get(path)
    if not hit or hit[:2] != (st.st_mtime, st.st_size):
        with open(path, "rb") as f:
            hit = _GZ[path] = (st.st_mtime, st.st_size, gzip.compress(f.read(), 6, mtime=0))
    return Response(hit[2], media_type=media, headers={"Cache-Control": cache, "Content-Encoding": "gzip",
                                                       "Vary": "Accept-Encoding"})


@app.get("/static/{name}")
def static_file(name: str, request: Request):
    if name in ("tokens.css", "app.css", "appview.css", "live.css", "weiche.css", "technik.css", "spontanhilfe.css"):  # the page's style and scripts: revalidated, so an update shows at once
        return _asset(request, os.path.join(STATIC, name), "text/css")
    if name not in PUBLIC_FILES:
        raise HTTPException(404, "not found")
    return FileResponse(os.path.join(STATIC, name), media_type=PUBLIC_FILES[name],
                        headers={"Cache-Control": "max-age=86400"})


@app.get("/static/js/{name}")
def script_file(name: str, request: Request):
    if not re.fullmatch(r"[a-z0-9\-]+\.js", name) or not os.path.isfile(os.path.join(STATIC, "js", name)):
        raise HTTPException(404, "not found")
    return _asset(request, os.path.join(STATIC, "js", name), "text/javascript")


@app.get("/static/xterm/{name}")
def xterm_file(name: str, request: Request):
    """xterm.js for Fernzugang → Systeme (MIT, pinned in fernzugang.XTERM, served only from here: script-src 'self')."""
    path, media = fernzugang.xterm_file(name)
    return _asset(request, path, media)


@app.get("/static/guac/{name}")
def guac_file(name: str, request: Request):
    """guacamole-common-js for Fernzugang → Bildschirm (Apache-2.0, pinned in fernbild.GUAC, served only from here)."""
    path, media = fernbild.guac_file(name)
    return _asset(request, path, media)


@app.get("/fernzugang/anker")
def fernzugang_anker(request: Request):
    """The spark-anker program for `curl … | sudo python3 - einrichten` (public: no secret in it; 404 while
    Funktionen → Fernzugang zu Servern is off)."""
    return fernzugang.download(request)


@app.get("/koppeln")
def fernzugang_link_page(request: Request):
    """Fernzugang: the page a pairing's „Einmal-Link“ opens on the new system (public, its own strict CSP, no data in
    it, the key behind „#“; 404 while Funktionen → Fernzugang zu Servern is off)."""
    return fernzugang.link_page(request)


@app.get("/hilfe")
def spontanhilfe_page(request: Request):
    """Spontanhilfe: the person's page (public, its own strict CSP, screen sharing only here; 404 while
    Funktionen → Fernzugang zu Servern → Spontanhilfe is off)."""
    return spontanhilfe.page(request)


@app.get("/manifest.webmanifest")
def manifest(request: Request):
    return static_file("manifest.webmanifest", request)


@app.get("/apple-touch-icon.png")
def apple_icon(request: Request):
    return static_file("apple-touch-icon.png", request)


@app.get("/favicon.ico")
def favicon(request: Request):
    return static_file("favicon-32.png", request)


@app.get("/android/spark.apk")
def android_app(request: Request, t: str = ""):
    """The Android app, only with a download link of a profile (android.py)."""
    return android.apk_response(request, t)


@app.get("/pebble/speech-spark.pbw")
def pebble_app():
    """The Pebble watch app, to open on the phone with the Pebble app (public: it holds no data)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pebble", "speech-spark.pbw")
    if not os.path.exists(path):
        raise HTTPException(404, "not built")
    return FileResponse(path, media_type="application/octet-stream", filename="speech-spark.pbw")


@app.get("/pebble/spark-zifferblatt.pbw")
def pebble_face():
    """The Spark-Zifferblatt, a watchface of its own (public: it holds no data; it only works with a paired key)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pebble", "spark-zifferblatt.pbw")
    if not os.path.exists(path):
        raise HTTPException(404, "not built")
    return FileResponse(path, media_type="application/octet-stream", filename="spark-zifferblatt.pbw")


@app.get("/tui/spark-tui.py")
def terminal_program():
    """The terminal client (terminal.py), to fetch with curl on the terminal (public: it holds no data; Ich → Terminal
    shows its SHA-256 to compare)."""
    if not os.path.exists(terminal.PROGRAM):
        raise HTTPException(404, "missing")
    return FileResponse(terminal.PROGRAM, media_type="text/x-python", filename="spark-tui.py")


@app.get("/sw.js")
def service_worker():  # served from / so it may control the whole panel
    return FileResponse(os.path.join(STATIC, "sw.js"), media_type="text/javascript", headers={"Cache-Control": "no-cache"})




class Server(uvicorn.Server):
    """Two servers (http and https) share one process; signals are handled once for both."""
    def capture_signals(self):
        import contextlib
        return contextlib.nullcontext()


def tls_context(config, default):
    """uvicorn's TLS context with TLS 1.2 as the floor (V01.0.825, code check 19.10. C8: security checklist "only
    TLS 1.2 or newer"; Python's default floor depends on the system's OpenSSL settings).

    No TLS 1.3 session tickets (V01.1.243): with them, about one https connection in a hundred to the stock asyncio
    loop of Python 3.11 hung after the handshake (the request never reached the app, the browser waited; a
    terminal of the Fernzugang never opened). uvicorn, TLS and one WebSocket alone, 800 handshakes: 9 hung with
    tickets, none without. The panel never resumes a session, so nothing is lost; without tickets there is also no
    ticket key in memory that could open recorded connections later."""
    import ssl
    ctx = default()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.num_tickets = 0
    return ctx


def https_config(pcfg, cert, key):
    return uvicorn.Config(app, host=pcfg["host"], port=pcfg["https_port"], ssl_certfile=cert, ssl_keyfile=key,
                          ssl_context_factory=tls_context, lifespan="off")


async def serve():
    import signal
    quiet_access_log()
    pcfg = load_config("panel")
    servers = [Server(uvicorn.Config(app, host=pcfg["host"], port=pcfg["port"]))]
    cert, key = os.path.join(TLS_DIR, "cert.pem"), os.path.join(TLS_DIR, "key.pem")
    # Browsers only allow the microphone on https (or localhost); the voice chat needs it.
    if pcfg.get("https_port") and os.path.exists(cert) and os.path.exists(key):
        # lifespan off: the startup handlers (Telegram poller, reminders, watchdog, backups …) run once, with
        # the http server; before V01.0.214 they ran twice, and two Telegram pollers knocked each other out
        servers.append(Server(https_config(pcfg, cert, key)))
    import loopwacht   # the Hänge-Wächter: systemd restarts a panel whose loop stands still (WatchdogSec=)
    loopwacht.start()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [setattr(x, "should_exit", True) for x in servers])
    await asyncio.gather(*(x.serve() for x in servers))


if __name__ == "__main__":
    asyncio.run(serve())
