"""Speech on DGX Spark: web panel for config and monitoring.

This file starts the app and serves the page; the API lives in modules next to it:
core (paths, logins), monitor (samples), account (login and the profile's own data),
chat (assistant, tools, learning, watch), admin (settings, services, voices), update."""
import asyncio
import os
import sys
import time

import psutil
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import load_config, quiet_access_log  # noqa: E402
from core import SERVICES, STATIC  # noqa: E402
from monitor import gpu_stats, history, service_health, system_stats  # noqa: E402
from chat import LEARN_EVERY, learn_once  # noqa: E402
from update import update_lock  # noqa: E402
import account  # noqa: E402
import admin  # noqa: E402
import chat  # noqa: E402
import update  # noqa: E402

app = FastAPI(title="Speech on DGX Spark")
for _module in (account, admin, chat, update):
    app.include_router(_module.router)
app.middleware("http")(update_lock)


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
                history.append({"t": time.time(), "gpu": g.get("util"), "cpu": s["cpu"],
                                "avail": s["mem_avail_gib"], "temp": g.get("temp"), "power": g.get("power"),
                                "asr_req": (h["asr"] or {}).get("requests"),
                                "tts_req": (h["tts"] or {}).get("requests")})
            except Exception as e:
                print("sampler:", e, flush=True)
            await asyncio.sleep(3)
    asyncio.create_task(loop())


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
    if name not in PUBLIC_FILES:
        raise HTTPException(404, "not found")
    return FileResponse(os.path.join(STATIC, name), media_type=PUBLIC_FILES[name],
                        headers={"Cache-Control": "max-age=86400"})


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
