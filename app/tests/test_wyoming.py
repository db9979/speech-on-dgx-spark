"""Wyoming for Home Assistant (wyoming.py): describe, speech to text and text to speech over the real
protocol, and only for listed addresses."""
import asyncio
import json
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import wyoming  # noqa: E402
from fastapi import FastAPI, File, Form, UploadFile  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ASR_PORT = helpers._port()
HEARD = []


def fake_asr():
    app = FastAPI()

    @app.post("/v1/audio/transcriptions")
    async def tr(file: UploadFile = File(...), language: str = Form("auto")):
        data = await file.read()
        HEARD.append((data[:4], len(data), language))
        return {"text": "Mach das Licht an"}
    return app


helpers._serve(fake_asr(), ASR_PORT)


async def talk(port, events):
    """Sends events, reads what comes back until the server closes or goes quiet."""
    r, w = await asyncio.open_connection("127.0.0.1", port)
    got = []
    try:
        for kind, data, payload in events:
            await wyoming.write_event(w, kind, data, payload)
        while True:
            ev = await asyncio.wait_for(wyoming.read_event(r), timeout=3)
            if ev is None:
                break
            got.append(ev)
            if ev[0] in ("info", "transcript", "audio-stop", "error"):
                break
    except (asyncio.TimeoutError, ConnectionError):
        pass
    w.close()
    return got


def run(events, allow="127.0.0.1"):
    helpers.set_config(wyoming=True, wyoming_allow=allow)
    real = wyoming.settings

    def settings():
        return dict(real(), asr_port=ASR_PORT)

    async def go():
        wyoming.settings = settings
        srv = await asyncio.start_server(wyoming.handle, "127.0.0.1", 0)
        try:
            return await talk(srv.sockets[0].getsockname()[1], events)
        finally:
            srv.close()
            wyoming.settings = real
    try:
        return asyncio.run(go())
    finally:
        helpers.set_config(wyoming=False, wyoming_allow="")


class Wyoming(unittest.TestCase):
    def test_describe_listen_speak(self):
        info = run([("describe", {}, b"")])
        self.assertEqual(info[0][0], "info")
        self.assertEqual(info[0][1]["asr"][0]["name"], "spark")
        self.assertTrue(info[0][1]["tts"][0]["voices"])
        pcm = b"\0\1" * 16000
        got = run([("transcribe", {"language": "de"}, b""), ("audio-start", {"rate": 16000, "width": 2, "channels": 1}, b""),
                   ("audio-chunk", {"rate": 16000, "width": 2, "channels": 1}, pcm[:20000]),
                   ("audio-chunk", {"rate": 16000, "width": 2, "channels": 1}, pcm[20000:]), ("audio-stop", {}, b"")])
        self.assertEqual(got[-1][:2], ("transcript", {"text": "Mach das Licht an"}))
        self.assertEqual(HEARD[-1], (b"RIFF", 44 + len(pcm), "de"))
        got = run([("synthesize", {"text": "Das Licht ist an.", "voice": {"name": "ryan"}}, b"")])
        kinds = [e[0] for e in got]
        self.assertEqual((kinds[0], kinds[-1]), ("audio-start", "audio-stop"))
        self.assertEqual(got[0][1], {"rate": 24000, "width": 2, "channels": 1})
        self.assertEqual(b"".join(e[2] for e in got if e[0] == "audio-chunk"), b"\1\0" * 2400)

    def test_only_listed_addresses(self):
        self.assertEqual(run([("describe", {}, b"")], allow="192.168.1.20"), [])
        self.assertEqual(run([("describe", {}, b"")], allow="127.0.0.0/8")[0][0], "info")
        self.assertTrue(wyoming.permitted("::ffff:192.168.1.5", wyoming.allowed("192.168.1.0/24")))
        self.assertFalse(wyoming.permitted("192.168.2.5", wyoming.allowed("192.168.1.0/24")))

    def test_settings_checked_and_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["wyoming"], False)
        admin = TestClient(panel.app)
        admin.post("/api/login", json={"password": "secret-admin"})
        cfg = admin.get("/api/config").json()
        for bad in ({"wyoming": True, "wyoming_allow": ""}, {"wyoming_allow": "kein-host"}, {"wyoming_port": cfg["tts"]["port"]}):
            c = json.loads(json.dumps(cfg))
            c["chat"].update(bad)
            self.assertEqual(admin.put("/api/config", json=c).status_code, 400, bad)

    def test_suggests_the_home_assistant_address(self):
        from unittest import mock
        import homeassistant
        import profiles
        urls = {"a": "http://192.168.1.20:8123", "b": "https://ha.example.org", "c": "http://8.8.8.8:8123",
                "d": "http://192.168.1.20:8123/"}
        wyoming._knocked.clear()
        with mock.patch.object(profiles, "user_ids", lambda: list(urls)), \
                mock.patch.object(homeassistant, "_raw", lambda uid: {"url": urls[uid], "token": "t"}):
            with mock.patch.object(wyoming.socket, "getaddrinfo",
                                   lambda h, *a, **k: [(0, 0, 0, "", (h, 0))] if h[0].isdigit() else []):
                d = wyoming.suggest()
            self.assertEqual(d, {"ha": [{"ip": "192.168.1.20", "host": "192.168.1.20"}], "knocked": []})
            # a refused knock while switched on is offered too, once
            run([("describe", {}, b"")], allow="10.0.0.1")
            run([("describe", {}, b"")], allow="10.0.0.1")
            self.assertEqual(wyoming._knocked, wyoming.collections.deque(["127.0.0.1"], maxlen=5))
            admin = TestClient(panel.app)
            self.assertEqual(admin.get("/api/admin/wyoming/suggest").status_code, 401)
            admin.post("/api/login", json={"password": "secret-admin"})
            # a name in the home network is resolved; the admin sees which name it came from
            with mock.patch.object(wyoming.socket, "getaddrinfo", lambda h, *a, **k: [(0, 0, 0, "", (
                    "192.168.1.30" if h == "ha.example.org" else h, 0))]):
                d = admin.get("/api/admin/wyoming/suggest").json()
            self.assertEqual(d["ha"], [{"ip": "192.168.1.20", "host": "192.168.1.20"},
                                       {"ip": "192.168.1.30", "host": "ha.example.org"}])
            self.assertEqual(d["knocked"], ["127.0.0.1"])


if __name__ == "__main__":
    unittest.main()
