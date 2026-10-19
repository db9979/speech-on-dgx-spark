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
        with mock.patch.object(admin, "unit_state", state), mock.patch.object(common, "QWEN38_UNITS", ["qwen38-a"]), \
                mock.patch.object(common, "unit_exists", lambda u: calls.append(u) or True), \
                mock.patch.object(common, "lane_fraction", lambda u: 0.5), \
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


class Rounds(unittest.TestCase):
    def test_shipped_rounds_stay_strong(self):
        """The self-tests run with fewer rounds (helpers.py); what ships is OWASP's 600 000 (V01.0.825)."""
        import os
        import re
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
        for name, const in (("core.py", "ROUNDS"), ("profiles.py", "PIN_ROUNDS")):
            with open(os.path.join(here, name)) as f:
                m = re.search(rf"^{const} = ([0-9_]+)", f.read(), re.M)
            self.assertIsNotNone(m, name)
            self.assertGreaterEqual(int(m.group(1).replace("_", "")), 600_000, name)
        with open(os.path.join(here, "profiles.py")) as f:
            self.assertIn("rounds = salt or secrets.token_hex(16), rounds or PIN_ROUNDS", f.read())


class RoundsRenewed(unittest.TestCase):
    """V01.0.825 (code check 19.10. C8): hashes from before keep working and get today's rounds at the next sign-in;
    a profile's other browsers stay signed in, a new PIN still ends them."""

    def test_admin_password_from_before(self):
        import hashlib
        import os
        import secrets
        import tempfile
        from unittest import mock
        import core
        with tempfile.TemporaryDirectory() as d, mock.patch.object(core, "PASSWORD_FILE", os.path.join(d, "pw")), \
                mock.patch.object(core, "OLD_ROUNDS", 500):
            salt = secrets.token_bytes(16)
            with open(core.PASSWORD_FILE, "w") as f:
                f.write(f"{salt.hex()} {hashlib.pbkdf2_hmac('sha256', b'alt-und-gut', salt, 500).hex()}\n")
            self.assertFalse(core.check_password("falsch"))
            self.assertEqual(len(open(core.PASSWORD_FILE).read().split()), 2, "a wrong password renews nothing")
            self.assertTrue(core.check_password("alt-und-gut"))
            self.assertEqual(open(core.PASSWORD_FILE).read().split()[2], str(core.ROUNDS))
            self.assertTrue(core.check_password("alt-und-gut"))

    def test_pin_from_before(self):
        import hashlib
        from unittest import mock
        import profiles
        uid = profiles.add_user("Rundenrolf", "4711")
        with mock.patch.object(profiles, "OLD_PIN_ROUNDS", 500):
            with profiles._lock:
                d = profiles._load()
                u = next(x for x in d["users"] if x["id"] == uid)
                salt = "ab" * 16
                u["pin"] = salt + "$" + hashlib.pbkdf2_hmac("sha256", b"4711", bytes.fromhex(salt), 500).hex()
                profiles._write(profiles._path("profiles.json"), d)
                old = profiles._cookie_value(u)
            self.assertIsNone(profiles.login("Rundenrolf", "0000"))
            self.assertIsNotNone(profiles.login("Rundenrolf", "4711"))
            d = profiles._load()
            u = next(x for x in d["users"] if x["id"] == uid)
            self.assertEqual(profiles._pin_rounds(u["pin"]), profiles.PIN_ROUNDS)
            self.assertIsNotNone(profiles._cookie_user(d, old)[0], "the other browser stays signed in")
            self.assertIsNotNone(profiles.login("Rundenrolf", "4711"))
            profiles.set_pin(uid, "8888")
            self.assertIsNone(profiles._cookie_user(profiles._load(), old)[0], "a new PIN ends the old logins")


class StatusCheap(unittest.TestCase):
    """Code check 19.10. B4/B5: the latency file is read again only when it changed, summary() is kept a few seconds
    while no answer came, and the screens that ask every second take the hints from a short cache."""

    def test_latency_reads_the_file_only_when_it_changed(self):
        import builtins
        from unittest import mock
        import latency
        latency.add(1.5, "web")
        latency._load()
        real, opened = builtins.open, []

        def counting(path, *a, **kw):
            if str(path).endswith("latency.json"):
                opened.append(path)
            return real(path, *a, **kw)
        with mock.patch("builtins.open", counting):
            for _ in range(5):
                latency._load()
                latency.summary()
        self.assertEqual(opened, [], "unchanged file: no read")
        n = latency.summary()["day"]["n"]
        latency.add(2.5, "web")
        self.assertEqual(latency.summary()["day"]["n"], n + 1, "a new answer shows at once")

    def test_hints_for_screens_are_cached(self):
        from unittest import mock
        import health
        calls = []
        with mock.patch.object(health, "alerts", lambda: calls.append(1) or [{"kind": "x"}]), \
                mock.patch.dict(health._alerts_kept, t=0.0, a=[]):
            for i in range(5):
                self.assertEqual(health.alerts_cached(now=1000 + i), [{"kind": "x"}])
            self.assertEqual(len(calls), 1)
            health.alerts_cached(now=1000 + health.ALERTS_S + 1)
            self.assertEqual(len(calls), 2)

    def test_write_json_writes_the_same(self):
        import json
        import os
        import tempfile
        from common import write_json
        data = {"ä": [1, 2.5, None, True], "b": {"c": "x" * 1000}}
        with tempfile.TemporaryDirectory() as d:
            for kw in ({}, {"indent": 1}, {"ensure_ascii": False}):
                p = os.path.join(d, "x.json")
                write_json(p, data, **kw)
                self.assertEqual(open(p, encoding="utf-8").read(), json.dumps(data, **kw))


class JsonStore(unittest.TestCase):
    def test_write_json_is_atomic_and_keeps_the_mode(self):
        import os
        import stat
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.json")
        common.write_json(p, {"a": 1})
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)   # new: owner only
        os.chmod(p, 0o640)
        common.write_json(p, {"a": 2}, indent=2)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o640)   # kept
        with open(p) as f:
            self.assertEqual(json.load(f), {"a": 2})
        os.symlink(os.path.join(d, "elsewhere"), p + ".tmp")   # the old fixed name: never written through
        common.write_json(p, {"a": 3})
        self.assertFalse(os.path.exists(os.path.join(d, "elsewhere")))
        self.assertEqual(sorted(os.listdir(d)), ["x.json", "x.json.tmp"])
        with self.assertRaises(TypeError):
            common.write_json(p, {"a": object()})
        with open(p) as f:
            self.assertEqual(json.load(f), {"a": 3})   # a failed write leaves the old file and no leftovers
        self.assertEqual(sorted(os.listdir(d)), ["x.json", "x.json.tmp"])


class PageFiles(unittest.TestCase):
    def test_scripts_and_styles_go_gzipped(self):
        import gzip
        from core import app_version
        c = TestClient(panel.app)
        for path in ("/static/js/base.js", "/static/app.css"):
            raw = c.get(path + "?v=" + app_version(), headers={"Accept-Encoding": "identity"})
            z = c.get(path + "?v=" + app_version(), headers={"Accept-Encoding": "gzip"})
            self.assertEqual(z.headers.get("content-encoding"), "gzip", path)
            self.assertEqual(z.content, raw.content)   # the client unpacks it: same file
            self.assertLess(len(gzip.compress(raw.content)), len(raw.content) * 0.6)
            self.assertIn("Accept-Encoding", z.headers.get("vary", ""))
        # the start page too (V01.0.750: 212 KB went out unpacked), and it stays never stored
        raw = c.get("/", headers={"Accept-Encoding": "identity"})
        z = c.get("/", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(z.headers.get("content-encoding"), "gzip")
        self.assertIsNone(raw.headers.get("content-encoding"))
        self.assertEqual(z.text, raw.text)
        self.assertEqual(z.headers["cache-control"], "no-store")
        self.assertIn("Accept-Encoding", z.headers.get("vary", ""))
        self.assertEqual(c.get("/static/js/nope.js").status_code, 404)
        self.assertEqual(c.get("/static/js/..%2Fpanel.py").status_code, 404)


class QuickStart(unittest.TestCase):
    """Webanwendung (V01.0.750, Dominik 2026-10-17): an admin's page start on a slow phone took 11.5 s. The jump links
    asked getComputedStyle for every hint (the page was recalculated each time), the Zustand cards asked the panel 13
    times while the assistant was open, and some 70 guides were written at every start."""

    @staticmethod
    def js(name):
        import os
        with open(os.path.join(os.path.dirname(panel.__file__), "static", "js", name), encoding="utf-8") as f:
            return f.read()

    def test_zustand_cards_ask_only_while_zustand_is_seen(self):
        import re
        start = self.js("start.js")
        cards = re.search(r"zPoll\(\[(.*?)\]\);", start).group(1)
        names = re.findall(r"'(z[A-Z]\w*)'", cards)
        self.assertGreaterEqual(len(names), 10)
        for n in names:
            self.assertNotRegex(start, r"\b" + n + r"\(\)", n + " is called at the start again: zCards only")
            self.assertNotIn("setInterval(" + n, start)
        admin_js = self.js("admin.js")
        body = admin_js[admin_js.index("function zPoll("):]
        self.assertIn("if(zSeen())f()", body[:300])    # the timer asks only while Zustand is seen
        self.assertIn("zPollNow()", admin_js[:admin_js.index("async function refresh(")])   # at once when it opens
        # one global namespace for every panel script: a second "function zPoll" would replace this one silently
        # (V01.0.750 was red: its first name zCards was already the Heute tiles in admin.js)
        import os
        d = os.path.dirname(os.path.join(os.path.dirname(panel.__file__), "static", "js", "x"))
        for fn in ("zPoll", "zPollNow", "zSeen", "wayFrame"):
            n = sum(len(re.findall(r"(?:function |const )" + fn + r"\b", self.js(f))) for f in os.listdir(d) if f.endswith(".js"))
            self.assertEqual(n, 1, fn)

    def test_jump_links_look_at_the_menu_once_per_frame(self):
        way = self.js("way.js")
        root = way[way.index("function wayRootOk("):way.index("// the open parts of a page")]
        self.assertIn("wayFrame()", root)
        self.assertEqual(way.count("wayVis("), 1, "wayVis (getComputedStyle) only in wayRootOk, kept per frame")
        self.assertIn("const l=k.low;", way)   # names lowered once per frame, not per hint

    def test_guides_are_written_when_they_are_opened(self):
        g = self.js("guides.js")
        init = g[g.index("function guidesInit("):]
        self.assertIn("if(sec.classList.contains('on'))guidesAll()", init)   # the list only with its page open
        self.assertNotIn(";guidesAll();", init)
        sw = g[g.index("function guidesSwitches("):g.index("function guidesMe(")]
        build = sw[:sw.index("btn.onclick")]
        self.assertNotIn("guideHTML", build, "the inline guide is written at the first tap, not at the start")


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


class SpeechRefusal(unittest.TestCase):
    """V01.0.462: a piece with nothing to say ("---", an emoji, a link alone) made the speech service answer HTTP 400
    and the whole rest of the answer stayed text only (Logs → Anfragen: "Fehler: tts_http_400")."""

    def test_nothing_to_say_is_not_sent(self):
        import textnorm
        for x in ("---", "***", "😊", "👍 ", "https://example.org/a.pdf", "Haha!", "| --- | --- |", "```", ""):
            self.assertFalse(textnorm.speakable(x), x)
        for x in ("Hallo.", "😊 Gern!", "**Quelle:** Archiv", "[Link](https://example.org)", "1.", "Oh!"):
            self.assertTrue(textnorm.speakable(x), x)
        helpers.TTS_TEXT[:] = []
        evs = ask("SAY | | 😊")
        self.assertEqual(helpers.TTS_TEXT, [])   # nothing sent, so nothing refused
        self.assertFalse([e for e in evs if e["type"] == "error"])

    def test_a_refused_piece_does_not_silence_the_rest(self):
        helpers.TTS_FAIL[:] = [(400, "nothing left to speak after removing emojis and markup")]
        try:
            evs = ask("SAY | | Hallo. Schön, dass du da bist, das freut mich wirklich sehr.")
        finally:
            helpers.TTS_FAIL[:] = []
        self.assertTrue(any(e["type"] == "audio" for e in evs))
        self.assertFalse([e for e in evs if e["type"] == "error"])

    def test_refusals_get_a_fixed_word(self):
        self.assertEqual(chat.tts_refusal(400, '{"detail":"nothing left to speak after removing emojis and markup"}'), "empty")
        self.assertEqual(chat.tts_refusal(400, "unknown voice 'x', available: []"), "voice")
        self.assertEqual(chat.tts_refusal(400, "the Base model needs a cloned voice: record one"), "voice")
        self.assertEqual(chat.tts_refusal(400, "input: at most 20000 characters per request"), "long")
        self.assertEqual(chat.tts_refusal(400, "body must be JSON"), "other")
        self.assertEqual(chat.tts_refusal(500, "nothing left to speak"), "other")
        helpers.TTS_FAIL[:] = [(400, "unknown voice 'weg', available: ['ryan']")]
        try:
            evs = ask()
        finally:
            helpers.TTS_FAIL[:] = []
        self.assertEqual([e["code"] for e in evs if e["type"] == "error"], ["tts_error"])
        self.assertEqual("".join(e.get("delta", "") for e in evs if e["type"] == "text"), "Hallo.")

    def test_error_codes_are_explained_in_the_page(self):
        """Logs → Anfragen shows a sentence for each error code (de and en), the code stays small beside it.
        The sentences have one source (klartext.CODES); the page reads them from the traces answer."""
        import os
        import klartext
        with open(os.path.join(os.path.dirname(chat.__file__), "static", "js", "logs.js"), encoding="utf-8") as f:
            js = f.read()
        for code in ("tts_http", "tts_voice", "tts_long", "tts_error", "tts_down", "llm_down", "llm_slow", "llm_auth",
                     "llm_model", "llm_error", "docmake", "error"):
            de, en = klartext.code_text(code)
            self.assertTrue(de and en and de != en, code)
        self.assertIn(".codes", js)
        self.assertIn("'lcode'", js)


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


class DocsCheap(unittest.TestCase):
    """Code check 19.10. B1-B3: the document list, the database and the meaning vectors cost little per question."""
    def setUp(self):
        import documents
        self.d = documents
        self.uid = profiles.add_user(f"Dokumente {self._testMethodName[5:30]}", "1234")
        self.a = documents.add(self.uid, "Rechnung Mai.txt", b"x", text="Die Rechnung vom Mai beträgt 120 Euro.")["id"]
        documents.add(self.uid, "Notiz.txt", b"x", text="Der Hund heißt Bello.")

    def test_list_is_remembered_until_something_changes(self):
        with mock.patch.object(self.d, "_list_docs", wraps=self.d._list_docs) as build:
            first = self.d.list_docs(self.uid)
            self.d.list_docs(self.uid)
            self.assertEqual(build.call_count, 1)
            first[0]["name"] = "verändert"                     # each caller gets its own dicts
            self.assertNotEqual(self.d.list_docs(self.uid)[0]["name"], "verändert")
            self.d.count_today(self.uid, "2026-10-19", add=1)   # a counter only: the list stays
            self.d.list_docs(self.uid)
            self.assertEqual(build.call_count, 1)
            self.d.set_use(self.uid, self.a, False)
            self.assertFalse(next(x for x in self.d.list_docs(self.uid) if x["id"] == self.a)["use"])
            self.assertEqual(build.call_count, 2)
            self.assertEqual([x["id"] for x in self.d.list_docs(self.uid, used_only=True)].count(self.a), 0)

    def test_a_replaced_file_is_read_again(self):
        import os
        import shutil
        self.d.list_docs(self.uid)
        path = self.d.db_path(self.uid)
        shutil.copyfile(path, path + ".neu")
        os.replace(path + ".neu", path)                       # what a restore does
        with mock.patch.object(self.d, "_list_docs", wraps=self.d._list_docs) as build:
            self.d.list_docs(self.uid)
        self.assertEqual(build.call_count, 1)

    def test_counts_match_the_pieces(self):
        row = next(x for x in self.d.list_docs(self.uid) if x["id"] == self.a)
        with self.d._Db(self.uid) as con:
            n = con.execute("SELECT COUNT(*), COUNT(vec) FROM chunks WHERE doc=?", (self.a,)).fetchone()
        self.assertEqual((row["chunks"], row["vecs"]), tuple(n))
        self.assertEqual(self.d.count_docs(self.uid), 2)

    def test_schema_is_checked_once(self):
        self.d._open(self.uid).close()
        con = self.d._open(self.uid)
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], self.d._schema_version())
        finally:
            con.close()
        with mock.patch.object(self.d, "_import_json") as imp:
            self.d._open(self.uid).close()
        imp.assert_not_called()

    def test_one_profile_does_not_wait_for_another(self):
        other = profiles.add_user("Dokumente nebenan", "1234")
        self.d.add(other, "x.txt", b"x", text="Etwas anderes.")
        held, done = threading.Event(), threading.Event()

        def hold():
            with self.d._Db(self.uid):
                held.set()
                done.wait(5)
        th = threading.Thread(target=hold)
        th.start()
        try:
            held.wait(5)
            t0 = time.time()
            self.assertEqual(self.d.count_docs(other), 1)
            self.assertLess(time.time() - t0, 1)
        finally:
            done.set()
            th.join()

    def test_vectors_stay_float32_and_counters_keep_them(self):
        import numpy as np
        with self.d._Db(self.uid) as con:
            ids = [r[0] for r in con.execute("SELECT id FROM chunks")]
        self.d.set_vectors(self.uid, [(i, np.ones(4, dtype=np.float16).tobytes()) for i in ids])
        got, mat = self.d._vectors(self.uid, now=1000)
        self.assertEqual(mat.dtype, np.float32)
        self.d.count_today(self.uid, "2026-10-19", add=1)
        self.assertIs(self.d._vectors(self.uid, now=1001)[1], mat)
        self.d.set_use(self.uid, self.a, False)
        self.assertIsNot(self.d._vectors(self.uid, now=1002)[1], mat)

    def test_catch_up_builds_at_most_every_few_seconds(self):
        import numpy as np
        self.d.add(self.uid, "Dritte.txt", b"x", text="Noch ohne Vektor.")     # one stays missing: the catch-up runs
        with self.d._Db(self.uid) as con:
            ids = [r[0] for r in con.execute("SELECT id FROM chunks ORDER BY id")]
        self.d.set_vectors(self.uid, [(ids[0], np.ones(4, dtype=np.float16).tobytes())])
        first = self.d._vectors(self.uid, now=2000)[1]
        self.d.set_vectors(self.uid, [(ids[1], np.ones(4, dtype=np.float16).tobytes())])
        self.assertIs(self.d._vectors(self.uid, now=2000 + self.d.VEC_CATCHUP_S - 1)[1], first)
        self.assertEqual(len(self.d._vectors(self.uid, now=2000 + self.d.VEC_CATCHUP_S)[0]), 2)

    def test_the_question_reads_the_lists_beside_the_loop(self):
        import inspect
        import chat_turn
        src = inspect.getsource(chat_turn.prepare)
        self.assertNotIn("documents.list_docs(", src)
        self.assertNotIn("wissen.shared_list(", src)
        self.assertNotIn("chat.docs_hint(", src)


class ConvoOffLoop(unittest.TestCase):
    """Code check 19.10. B6: the whole conversation file is read and written beside the event loop, without indenting."""
    def test_turns_are_saved_in_a_thread(self):
        import inspect
        import account
        import esp32
        import telefon
        src = inspect.getsource(account.profile_save_convo)
        self.assertNotIn("= profiles.append_convo(", src)
        self.assertNotIn("= profiles.save_convo(", src)
        self.assertIn("await beside(remember,", inspect.getsource(esp32))
        self.assertIn("await beside(self.remember,", inspect.getsource(telefon))
        self.assertIn("await beside(profiles.save_convo,", src)

    def test_a_cancelled_caller_still_saves(self):
        """A speaker that disconnects right after the answer cancels the answer task: with every thread busy,
        asyncio.to_thread dropped the waiting save and the turn was lost (test_esp32 red under load)."""
        import concurrent.futures
        import threading
        import common
        ran, gate = [], threading.Event()

        async def go():
            loop = asyncio.get_running_loop()
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            loop.set_default_executor(pool)
            busy = loop.run_in_executor(None, gate.wait)      # the only thread is taken
            task = asyncio.ensure_future(common.beside(ran.append, "saved"))
            await asyncio.sleep(0)
            task.cancel()                                     # the caller goes away while the save still waits
            with self.assertRaises(asyncio.CancelledError):
                await task
            gate.set()
            await busy
            pool.shutdown(wait=True)

        asyncio.run(go())
        self.assertEqual(ran, ["saved"])

    def test_the_file_is_not_indented(self):
        uid = profiles.add_user("Ohne Einrückung", "1234")
        profiles.append_convo(uid, "c1", "Test", [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}])
        with open(profiles._path(uid, "convos.json")) as f:
            self.assertNotIn("\n", f.read().strip())


if __name__ == "__main__":
    unittest.main()
