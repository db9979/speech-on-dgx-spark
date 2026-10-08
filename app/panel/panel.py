"""Speech on DGX Spark: web panel for config and monitoring.

This file starts the app and serves the page; the API lives in modules next to it:
core (paths, logins), monitor (samples), account (login and the profile's own data),
chat (assistant, tools, learning, watch), admin (settings, services, voices), update."""
import asyncio
import os
import re
import sys
import time

import psutil
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import load_config, quiet_access_log  # noqa: E402
from core import ADMIN_IDLE, COOKIE, SERVICES, STATIC, admin_cookie_ok, renewed_admin_cookie  # noqa: E402
from monitor import gpu_stats, history, service_health, system_stats  # noqa: E402
from chat import LEARN_EVERY, learn_once  # noqa: E402
from update import update_lock  # noqa: E402
import account  # noqa: E402
import calendars  # noqa: E402
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
import health  # noqa: E402
import push  # noqa: E402
import proactive  # noqa: E402
import room  # noqa: E402
import tidy  # noqa: E402
import weather  # noqa: E402
import contacts  # noqa: E402
import parcels  # noqa: E402
import extras  # noqa: E402
import telegram  # noqa: E402
import tasks  # noqa: E402
import wyoming  # noqa: E402
import esp32  # noqa: E402

app = FastAPI(title="Speech on DGX Spark")
for _module in (account, admin, chat, update, system, proactive, room, tidy, weather, contacts, parcels, telegram, tasks, esp32):
    app.include_router(_module.router)
app.middleware("http")(update_lock)


@app.middleware("http")
async def sessions(request: Request, call_next):
    """Refuses changes from foreign pages, writes the change log and renews logins in use."""
    if not guard.same_origin(request, (COOKIE, profiles.COOKIE)):
        guard.log("foreign_page_refused", ip=guard.client_ip(request), path=request.url.path,
                  origin=request.headers.get("origin", ""))
        return guard.foreign_page()
    response = await call_next(request)
    path = request.url.path
    if guard.logged(path, request.method):
        prof = profiles.current(request)
        basic = request.headers.get("authorization", "").startswith("Basic ") and response.status_code < 400
        who = "admin" if admin_cookie_ok(request) or basic else (prof or {}).get("name", "guest")
        guard.log("change", ip=guard.client_ip(request), who=who, uid=(prof or {}).get("id"),
                  method=request.method, path=path, status=response.status_code)
    if path.startswith("/api/") and response.status_code < 400:
        admin_value, user_value = renewed_admin_cookie(request), profiles.renewed_cookie(request)
        if admin_value:
            response.set_cookie(COOKIE, admin_value, max_age=ADMIN_IDLE, httponly=True, samesite="strict")
        if user_value:
            response.set_cookie(profiles.COOKIE, user_value, max_age=profiles.SESSION_DAYS * 86400,
                                httponly=True, samesite="lax")
    if guard.https(request):  # on https (also behind a proxy) logins never travel over plain http
        raw = response.headers.getlist("set-cookie") if hasattr(response.headers, "getlist") else []
        if raw and any("secure" not in c.lower() for c in raw):
            del response.headers["set-cookie"]
            for c in raw:
                response.headers.append("set-cookie", c if "secure" in c.lower() else c + "; Secure")
    return response


@app.on_event("startup")
async def sampler():
    async def loop():
        psutil.cpu_percent()
        while True:
            try:
                cfg = load_config()
                g = gpu_stats() or {}
                s = system_stats()
                h = {n: await service_health(n, cfg) for n in SERVICES}
                health.check_memory(s["mem_avail_gib"], cfg)
                history.append({"t": time.time(), "gpu": g.get("util"), "cpu": s["cpu"],
                                "avail": s["mem_avail_gib"], "temp": g.get("temp"), "power": g.get("power"),
                                "asr_req": (h["asr"] or {}).get("requests"),
                                "tts_req": (h["tts"] or {}).get("requests")})
            except Exception as e:
                print("sampler:", e, flush=True)
            await asyncio.sleep(3)
    asyncio.create_task(loop())


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
                if backup.due():
                    item = await asyncio.to_thread(backup.create, "daily")
                    print("backup:", item["name"], flush=True)
            except Exception as e:
                guard.log("backup_failed", detail=f"{type(e).__name__}: {e}"[:200])
            await asyncio.sleep(3600)

    async def after_update():
        if health.after_update_due(update.update_progress()):
            await health.ready(load_config())
            res = await health.livecheck("after update")
            print("live check after update:", "ok" if res and res["ok"] else res, flush=True)
            if res and res["ok"]:
                await quality.run("after update")
    async def reminders():
        # due reminders on their own: a slow briefing or proactive check never holds them up
        while True:
            await asyncio.sleep(15)
            try:
                await push.due_reminders()
            except Exception as e:
                print("push reminders:", type(e).__name__, e, flush=True)

    async def every_minute():
        # each minute once, even when the work of the one before took longer than a minute
        last = None
        while True:
            minute = int(time.time()) // 60
            if minute != last:
                last = minute
                room.sweep()
                try:
                    await chat.due_briefings()
                except Exception as e:
                    print("briefing:", type(e).__name__, e, flush=True)
                try:
                    await proactive.due_once()
                except Exception as e:
                    print("proactive:", type(e).__name__, e, flush=True)
                try:
                    await extras.due_once()
                except Exception as e:
                    print("extras:", type(e).__name__, e, flush=True)
            await asyncio.sleep(5)
    asyncio.create_task(reminders())
    asyncio.create_task(telegram.loop())
    asyncio.create_task(wyoming.loop())
    asyncio.create_task(esp32.fetch_loop())
    asyncio.create_task(every_minute())
    asyncio.create_task(watchdog())
    asyncio.create_task(backups())
    asyncio.create_task(after_update())


@app.on_event("startup")
async def mail_tidy():
    """Tidying inboxes (see tidy.py): each minute the mailboxes whose interval is due; the language
    model only sorts while nobody is talking to the assistant."""
    async def loop():
        while True:
            await asyncio.sleep(60)
            try:
                await tidy.due_once(idle=time.time() - chat._last_chat[0] > 60)
            except Exception as e:
                print("mail tidy:", type(e).__name__, e, flush=True)
    asyncio.create_task(loop())


@app.on_event("startup")
def seal_secrets():
    """Calendar passwords and Home Assistant tokens from older versions get encrypted once."""
    for uid in profiles.user_ids():
        try:
            calendars.seal_stored(uid)
            homeassistant.seal_stored(uid)
        except Exception as e:
            print("sealing secrets:", type(e).__name__, e, flush=True)


@app.on_event("startup")
async def learner():
    async def loop():
        while True:
            await asyncio.sleep(LEARN_EVERY)
            try:
                n = await learn_once()
                if n:
                    print(f"learned {n} fact(s) from conversations", flush=True)
            except Exception as e:
                print("learning:", type(e).__name__, e, flush=True)
            try:
                if time.time() - chat._last_chat[0] > 60:   # never while someone is talking
                    uid = await memtidy.due_once()
                    if uid:
                        print("memory tidy: checked a profile", flush=True)
            except Exception as e:
                print("memory tidy:", type(e).__name__, e, flush=True)
    asyncio.create_task(loop())


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-cache"})


# App files (installable assistant). Public like the start page: they hold no data.
PUBLIC_FILES = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png",
                "apple-touch-icon.png": "image/png", "favicon-32.png": "image/png",
                "manifest.webmanifest": "application/manifest+json"}


@app.get("/static/{name}")
def static_file(name: str):
    if name == "app.css":  # the page's style and scripts: revalidated, so an update shows at once
        return FileResponse(os.path.join(STATIC, name), media_type="text/css", headers={"Cache-Control": "no-cache"})
    if name not in PUBLIC_FILES:
        raise HTTPException(404, "not found")
    return FileResponse(os.path.join(STATIC, name), media_type=PUBLIC_FILES[name],
                        headers={"Cache-Control": "max-age=86400"})


@app.get("/static/js/{name}")
def script_file(name: str):
    if not re.fullmatch(r"[a-z0-9\-]+\.js", name) or not os.path.isfile(os.path.join(STATIC, "js", name)):
        raise HTTPException(404, "not found")
    return FileResponse(os.path.join(STATIC, "js", name), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return static_file("manifest.webmanifest")


@app.get("/apple-touch-icon.png")
def apple_icon():
    return static_file("apple-touch-icon.png")


@app.get("/favicon.ico")
def favicon():
    return static_file("favicon-32.png")


@app.get("/pebble/speech-spark.pbw")
def pebble_app():
    """The Pebble watch app, to open on the phone with the Pebble app (public: it holds no data)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pebble", "speech-spark.pbw")
    if not os.path.exists(path):
        raise HTTPException(404, "not built")
    return FileResponse(path, media_type="application/octet-stream", filename="speech-spark.pbw")


@app.get("/sw.js")
def service_worker():  # served from / so it may control the whole panel
    return FileResponse(os.path.join(STATIC, "sw.js"), media_type="text/javascript", headers={"Cache-Control": "no-cache"})


TLS_DIR = os.environ.get("SPEECH_SPARK_TLS", "/etc/speech-spark/tls")


class Server(uvicorn.Server):
    """Two servers (http and https) share one process; signals are handled once for both."""
    def capture_signals(self):
        import contextlib
        return contextlib.nullcontext()


async def serve():
    import signal
    quiet_access_log()
    pcfg = load_config("panel")
    servers = [Server(uvicorn.Config(app, host=pcfg["host"], port=pcfg["port"]))]
    cert, key = os.path.join(TLS_DIR, "cert.pem"), os.path.join(TLS_DIR, "key.pem")
    # Browsers only allow the microphone on https (or localhost); the voice chat needs it.
    if pcfg.get("https_port") and os.path.exists(cert) and os.path.exists(key):
        servers.append(Server(uvicorn.Config(app, host=pcfg["host"], port=pcfg["https_port"],
                                             ssl_certfile=cert, ssl_keyfile=key)))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [setattr(x, "should_exit", True) for x in servers])
    await asyncio.gather(*(x.serve() for x in servers))


if __name__ == "__main__":
    asyncio.run(serve())
