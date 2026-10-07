"""Test setup: a throw-away state directory, fake LLM / TTS / Home Assistant servers in threads,
and the panel app imported against them. Nothing touches the real installation."""
import asyncio
import atexit
import base64
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="speech-spark-test-")
atexit.register(lambda: shutil.rmtree(TMP, ignore_errors=True))


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


LLM_PORT, TTS_PORT, HA_PORT = _port(), _port(), _port()
HA_TOKEN = "t" * 40

cfg = json.load(open(os.path.join(APP, "config.default.json")))
cfg["chat"].update(llm_url=f"http://127.0.0.1:{LLM_PORT}/v1", llm_key="", homeassistant=True, search=False)
cfg["tts"]["port"] = TTS_PORT
with open(os.path.join(TMP, "config.json"), "w") as f:
    json.dump(cfg, f)
for d in ("state", "users", "voices", "tls"):
    os.makedirs(os.path.join(TMP, d), exist_ok=True)
os.environ.update(SPEECH_SPARK_CONFIG=os.path.join(TMP, "config.json"), SPEECH_SPARK_STATE=os.path.join(TMP, "state"),
                  SPEECH_SPARK_USERS=os.path.join(TMP, "users"), SPEECH_SPARK_VOICES=os.path.join(TMP, "voices"),
                  SPEECH_SPARK_TLS=os.path.join(TMP, "tls"), SPEECH_SPARK_PREFIX=TMP, PANEL_PASSWORD="secret-admin")
for p in (APP, os.path.join(APP, "panel")):
    if p not in sys.path:
        sys.path.insert(0, p)

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import PlainTextResponse, StreamingResponse  # noqa: E402

LLM_CALLS = []   # every request body the fake LLM got
HA_CALLS = []


def _sse(obj):
    return "data: " + json.dumps(obj) + "\n\n"


def fake_llm():
    """Answers "Hallo." to everything; "TOOL name {json}" as the last user message calls that tool,
    and after a tool result it echoes the result. Non-streaming requests get a facts JSON."""
    app = FastAPI()

    @app.get("/v1/models")
    def models():
        return {"data": [{"id": "fake"}]}

    @app.post("/v1/chat/completions")
    async def cc(req: Request):
        b = await req.json()
        LLM_CALLS.append(b)
        last = b["messages"][-1]
        if not b.get("stream"):
            return {"choices": [{"message": {"content": '{"facts": ["Test mag Tee."]}'}}]}

        async def gen():
            names = [t["function"]["name"] for t in b.get("tools") or []]
            c = last.get("content") or ""
            if last["role"] == "user" and c.startswith("TOOL "):
                name, _, args = c[5:].partition(" ")
                if name in names:
                    yield _sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                                "function": {"name": name, "arguments": args or "{}"}}]}, "finish_reason": None}]})
                    yield _sse({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]})
                    yield "data: [DONE]\n\n"
                    return
                c = "NO TOOL " + name
            text = ("Ergebnis: " + c[:800]) if last["role"] == "tool" else ("Hallo." if not c.startswith("NO TOOL") else c)
            for i in range(0, len(text), 10):
                yield _sse({"choices": [{"delta": {"content": text[i:i + 10]}, "finish_reason": None}]})
            yield _sse({"choices": [{"delta": {}, "finish_reason": "stop"}]})
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")
    return app


def fake_tts():
    app = FastAPI()

    @app.post("/v1/audio/speech")
    async def speech(req: Request):
        await req.json()

        async def gen():
            pcm = base64.b64encode(b"\0\0" * 2400).decode()
            yield _sse({"type": "speech.audio.delta", "audio": pcm})
            yield _sse({"type": "speech.audio.done"})
        return StreamingResponse(gen(), media_type="text/event-stream")
    return app


HA_STATES = [
    {"entity_id": "sensor.wz_temp", "state": "21.5", "attributes": {"friendly_name": "Temperatur",
     "unit_of_measurement": "°C", "device_class": "temperature"}},
    {"entity_id": "light.kueche", "state": "on", "attributes": {"friendly_name": "Licht Küche", "brightness": 255}},
    {"entity_id": "binary_sensor.bad_fenster", "state": "on", "attributes": {"friendly_name": "Bad Fenster",
     "device_class": "window"}},
    {"entity_id": "zone.home", "state": "1", "attributes": {"friendly_name": "Zuhause", "radius": 100,
     "persons": ["person.anna"]}},
    {"entity_id": "zone.buero", "state": "0", "attributes": {"friendly_name": "Büro", "radius": 150, "persons": []}},
    {"entity_id": "switch.keller", "state": "off", "attributes": {"friendly_name": "Kellerpumpe"}},
    {"entity_id": "lock.haustuer", "state": "locked", "attributes": {"friendly_name": "Haustür"}},
    {"entity_id": "person.anna", "state": "home", "attributes": {"friendly_name": "Anna"}},
]


def fake_ha():
    app = FastAPI()

    def auth(r):
        if r.headers.get("authorization") != "Bearer " + HA_TOKEN:
            raise HTTPException(401)

    @app.get("/api/")
    def root(request: Request):
        auth(request)
        return {"message": "API running."}

    @app.get("/api/states")
    def states(request: Request):
        auth(request)
        return HA_STATES

    @app.get("/api/states/{eid}")
    def one(eid: str, request: Request):
        auth(request)
        for x in HA_STATES:
            if x["entity_id"] == eid:
                return x
        raise HTTPException(404)

    @app.post("/api/services/{domain}/{service}")
    async def service(domain: str, service: str, request: Request):
        auth(request)
        b = await request.json()
        HA_CALLS.append(dict(b, service=f"{domain}.{service}"))
        for x in HA_STATES:
            if x["entity_id"] == b.get("entity_id") and service in ("turn_on", "turn_off"):
                x["state"] = service[5:]
                return [x]
        return []

    @app.post("/api/template")
    async def template(request: Request):
        auth(request)
        return PlainTextResponse("sensor.wz_temp|Wohnzimmer\nlight.kueche|Küche\n")

    @app.post("/api/conversation/process")
    async def proc(request: Request):
        auth(request)
        b = await request.json()
        HA_CALLS.append(b)
        return {"response": {"response_type": "action_done", "speech": {"plain": {"speech": "Erledigt"}},
                             "data": {"success": [{"name": "Licht Küche"}], "failed": []}}}
    return app


def _serve(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    server.install_signal_handlers = lambda: None
    threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True).start()
    for _ in range(100):
        if server.started:
            return
        time.sleep(0.05)
    raise RuntimeError(f"fake server on {port} did not start")


_started = False


def start():
    global _started
    if not _started:
        _serve(fake_llm(), LLM_PORT)
        _serve(fake_tts(), TTS_PORT)
        _serve(fake_ha(), HA_PORT)
        _started = True


def set_config(**chat):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c["chat"].update(chat)
    with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
        json.dump(c, f)


def events(response):
    """The JSON events of a /api/chat stream."""
    return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]

