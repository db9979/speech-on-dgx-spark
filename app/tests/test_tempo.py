"""Independent review of 11.10.2026, package 3 (Tempo und Stabilität, V01.0.405): shared TLS setup for every
connection, nothing slow on the panel's event loop, a speech service that restarts is waited for, an LLM that
stays silent ends the turn, and conversations written by two turns at once keep both."""
import asyncio
import json
import socket
import threading
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import admin  # noqa: E402
import chat  # noqa: E402
import common  # noqa: E402
import profiles  # noqa: E402
import update  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def ask(text="Hallo"):
    helpers.set_config(public=True)
    r = TestClient(panel.app).post("/api/chat", json={"messages": [{"role": "user", "content": text}]})
    assert r.status_code == 200, r.text
    return helpers.events(r)


class SharedTls(unittest.TestCase):
    def test_clients_share_one_tls_setup(self):
        """httpx builds a new TLS context (certifi, ~40 ms) for every client: one is kept per kind now."""
        import httpx
        a, b = httpx.AsyncClient(), httpx.Client()
        try:
            self.assertIs(a._transport._pool._ssl_context, b._transport._pool._ssl_context)
        finally:
            b.close()
            asyncio.run(a.aclose())
        c = httpx.Client(verify=False)   # anything other than the default keeps its own
        try:
            self.assertIsNot(c._transport._pool._ssl_context, b._transport._pool._ssl_context)
        finally:
            c.close()
        t0 = time.perf_counter()
        for _ in range(20):
            httpx.Client().close()
        self.assertLess((time.perf_counter() - t0) / 20, 0.02)


class OffTheLoop(unittest.TestCase):
    def test_status_calls_systemctl_in_a_worker_thread(self):
        main = threading.get_ident()
        seen = []

        def state(unit):
            seen.append(threading.get_ident())
            return "active"
        calls = []
        with mock.patch.object(admin, "unit_state", state), mock.patch.object(admin, "QWEN38_UNITS", ["qwen38-a"]), \
                mock.patch.object(admin, "unit_exists", lambda u: calls.append(u) or True), \
                mock.patch.object(admin, "lane_fraction", lambda u: 0.5), \
                mock.patch.dict(admin._lanes, {"t": None, "units": []}):
            c = TestClient(panel.app)
            c.post("/api/login", json={"password": "secret-admin"})
            for _ in range(2):
                r = c.get("/api/status")
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["qwen38"], [{"unit": "qwen38-a", "state": "active", "mem_fraction": 0.5}])
        self.assertTrue(seen)
        self.assertNotIn(main, seen)
        self.assertEqual(calls, ["qwen38-a"])   # which lanes exist: looked up once, not every 3 seconds

    def test_update_check_waits_for_git_in_a_worker_thread(self):
        loop_thread = []

        def run(cmd, **kw):
            loop_thread.append(threading.get_ident())
            return 1, "fatal: unreachable"

        async def go():
            here = threading.get_ident()
            with mock.patch.object(update, "run", run), \
                    mock.patch.object(update, "installed_version", lambda: {"remote": "https://github.com/x/y", "branch": "main"}):
                await update._remote_state(force=True)
            return here
        here = asyncio.run(go())
        self.assertEqual(len(loop_thread), 1)
        self.assertNotEqual(loop_thread[0], here)

    def test_password_check_runs_in_a_worker_thread(self):
        import account
        seen = []
        real = account.check_password

        def check(pw):
            seen.append(threading.get_ident())
            return real(pw)
        c = TestClient(panel.app)
        with mock.patch.object(account, "check_password", check):
            self.assertEqual(c.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], threading.main_thread().ident)

    def test_background_task_error_is_logged_and_task_kept(self):
        import core
        import io
        from contextlib import redirect_stdout

        async def boom():
            await asyncio.sleep(0)
            raise ValueError("kaputt")

        async def go():
            t = core.spawn(boom(), name="probe")
            self.assertIn(t, core._tasks)
            await asyncio.sleep(0.05)
            return t
        out = io.StringIO()
        with redirect_stdout(out):
            t = asyncio.run(go())
        self.assertNotIn(t, core._tasks)
        self.assertIn("background task probe ended: ValueError: kaputt", out.getvalue())


class SpeechRestart(unittest.TestCase):
    def test_tts_restart_is_waited_for(self):
        """During an update the speech service is gone for ~8 s: a 503 is tried again, the answer still speaks."""
        helpers.TTS_FAIL[:] = [503, 502]
        try:
            with mock.patch.object(chat, "TTS_WAITS", (0.01, 0.01, 0.01, 0.01)):
                evs = ask()
        finally:
            helpers.TTS_FAIL[:] = []
        self.assertTrue(any(e["type"] == "audio" for e in evs))
        self.assertFalse([e for e in evs if e["type"] == "error"])

    def test_tts_that_stays_down_ends_as_text(self):
        helpers.TTS_FAIL[:] = [503] * 6
        try:
            with mock.patch.object(chat, "TTS_WAITS", (0.01, 0.01)):
                evs = ask()
        finally:
            helpers.TTS_FAIL[:] = []
        self.assertEqual("".join(e.get("delta", "") for e in evs if e["type"] == "text"), "Hallo.")
        self.assertEqual([e["code"] for e in evs if e["type"] == "error"], ["tts_down"])


class SilentModel(unittest.TestCase):
    def test_llm_that_stays_silent_ends_the_turn(self):
        """An LLM that accepts the request but writes nothing: "llm_slow" after FIRST_WAIT, not 600 s of silence."""
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(8)
        stop = threading.Event()

        def one(conn):
            req = b""
            while b"\r\n\r\n" not in req:
                req += conn.recv(65536)
            head, body = req.split(b"\r\n\r\n", 1)
            size = int(next((h.split(b":")[1] for h in head.split(b"\r\n") if h.lower().startswith(b"content-length")), b"0"))
            while len(body) < size:
                body += conn.recv(65536)
            if b'"stream": true' not in body and b'"stream":true' not in body:   # side calls (models, intent) answer at once
                out = json.dumps({"data": [{"id": "fake"}], "choices": [{"message": {"content": "{}"}}]}).encode()
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
                             + f"Content-Length: {len(out)}\r\n\r\n".encode() + out)
            else:   # the answer: accepted, then nothing
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n")
                stop.wait(10)
            conn.close()

        def serve():
            while not stop.is_set():
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                threading.Thread(target=one, args=(conn,), daemon=True).start()
        threading.Thread(target=serve, daemon=True).start()
        path = helpers.os.environ["SPEECH_SPARK_CONFIG"]
        with open(path) as f:
            c = json.load(f)
        old = dict(c["chat"])
        c["chat"].update(llm_url=f"http://127.0.0.1:{srv.getsockname()[1]}/v1")
        with open(path, "w") as f:
            json.dump(c, f)
        try:
            with mock.patch.object(chat, "FIRST_WAIT", 0.5):
                t0 = time.time()
                evs = ask()
                took = time.time() - t0
        finally:
            stop.set()
            srv.close()
            with open(path) as f:
                c = json.load(f)
            c["chat"] = old
            with open(path, "w") as f:
                json.dump(c, f)
        self.assertIn("llm_slow", [e.get("code") for e in evs if e["type"] == "error"])
        self.assertLess(took, 4.5)

    def test_first_within_passes_every_line(self):
        async def lines():
            for x in ("a", "b", "c"):
                yield x

        async def go():
            return [x async for x in chat.first_within(lines(), 1)]
        self.assertEqual(asyncio.run(go()), ["a", "b", "c"])


class ConvoAppend(unittest.TestCase):
    def test_two_turns_at_once_keep_both(self):
        uid = profiles.add_user("Parallel", "1234")
        n = 12

        def turn(i):
            profiles.append_convo(uid, "tg-20261011", "Telegram 11.10.",
                                  [{"role": "user", "content": f"Frage {i}"}, {"role": "assistant", "content": f"Antwort {i}"}])
        threads = [threading.Thread(target=turn, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        c = next(x for x in profiles.convos(uid) if x["id"] == "tg-20261011")
        self.assertEqual(sorted(m["content"] for m in c["msgs"] if m["role"] == "user"),
                         sorted(f"Frage {i}" for i in range(n)))
        self.assertEqual(c["title"], "Telegram 11.10.")

    def test_append_keeps_marks_and_limits(self):
        uid = profiles.add_user("Marken", "1234")
        profiles.append_convo(uid, "esp-x-1", "Box", [{"role": "user", "content": "x", "outside": True},
                                                      {"role": "assistant", "content": "y", "mail": True}])
        for i in range(40):
            profiles.append_convo(uid, "esp-x-1", "Box", [{"role": "user", "content": str(i)}, {"role": "assistant", "content": "ok"}])
        c = next(x for x in profiles.convos(uid) if x["id"] == "esp-x-1")
        self.assertEqual(len(c["msgs"]), profiles.MAX_MSGS)
        self.assertIsNone(profiles.append_convo(uid, "../bad", "x", []))


if __name__ == "__main__":
    unittest.main()
