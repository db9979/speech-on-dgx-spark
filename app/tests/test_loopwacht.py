"""Hänge-Wächter (Dominik 2026-10-18 "1a 2a 3a 5a"): the panel's loop beats, a stall gets a log line with the place
and systemd restarts a panel that stands still; heavy work never runs on the loop (a list of the places other
threads still move, which only shrinks); the panel and the Notbetrieb-ASR keep the speech services' priority and
leave only the last core; the Raspberry Pi's hardware watchdog restarts a frozen Pi."""
import ast
import io
import os
import re
import socket
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests import helpers

helpers.start()
import loopwacht  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(APP, "panel")

# Calls that block the loop however small the data: a program, a pause, walking or deleting a folder tree, a download
# without asyncio, reading a document (PDF, Office, pictures).
ALWAYS = {("subprocess", "run"), ("subprocess", "check_output"), ("subprocess", "call"), ("subprocess", "check_call"),
          ("time", "sleep"), ("os", "walk"), ("shutil", "rmtree"), ("shutil", "copytree"), ("shutil", "make_archive"),
          ("request", "urlopen"), ("urllib", "urlopen"), ("documents", "add"), ("documents", "reread"),
          ("documents", "extract"), ("documents", "extract_pages"), ("documents", "notebook_put"),
          ("documents", "picture_jpeg")}
# Writes per document: fine once, on the loop they add up with every document in a loop (Ordner auslassen with
# thousands of documents, 2026-10-18).
PER_DOC = {("documents", "delete"), ("nasquelle", "_put_state"), ("documents", "set_use"), ("documents", "set_shared"),
           ("documents", "set_tags"), ("documents", "set_place"), ("documents", "set_card")}
# Places another thread still moves off the loop (Dominik's push queue; the coordinator handed them on 2026-10-18).
# The list only shrinks: an entry that is no longer found is red, so it goes in the same commit.
LATER = {
    ("nasquelle", "sync_once"): "Ordner von Suche ausschließen: the state of a Wissensordner written per file",
    ("remarkable", "_sync"): "Ordner von Suche ausschließen: notebooks deleted one by one on the loop",
    ("remarkable", "unpair"): "Ordner von Suche ausschließen: forget() deletes every notebook on the loop",
}


def _modules():
    out = {}
    for d in (APP, PANEL):
        for f in sorted(os.listdir(d)):
            if f.endswith(".py"):
                out.setdefault(f[:-3], os.path.join(d, f))
    return out


class _Graph:
    """The panel's code as a call graph (by module and function name): which sync function reaches heavy work."""
    def __init__(self):
        self.funcs, self.coros, self.mods = {}, {}, _modules()
        for m, p in self.mods.items():
            with open(p, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for n in tree.body:
                if isinstance(n, ast.FunctionDef):
                    self.funcs[(m, n.name)] = n
                    for k in ast.walk(n):   # coroutines inside a function (the startup loops) are checked too
                        if isinstance(k, ast.AsyncFunctionDef) and os.path.dirname(p) == PANEL:
                            self.coros.setdefault((m, k.name), k)
                elif isinstance(n, ast.AsyncFunctionDef) and os.path.dirname(p) == PANEL:
                    self.coros[(m, n.name)] = n
                    for k in ast.walk(n):
                        if isinstance(k, ast.AsyncFunctionDef) and k is not n:
                            self.coros.setdefault((m, k.name), k)
        self.memo = {}

    @staticmethod
    def calls(fn, mod):
        """[(target, in a loop)] of the calls made right here: not in nested functions or lambdas (they run
        elsewhere, e.g. asyncio.to_thread(lambda: ...)), not under await (a coroutine is checked by itself)."""
        out = []

        def walk(node, loop):
            for c in ast.iter_child_nodes(node):
                if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.Await)):
                    continue
                inl = loop or isinstance(c, (ast.For, ast.While, ast.comprehension))
                if isinstance(c, ast.Call):
                    f = c.func
                    if isinstance(f, ast.Name):
                        out.append(((mod, f.id), inl))
                    elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                        out.append(((f.value.id, f.attr), inl))
                    elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) and isinstance(f.value.value, ast.Name):
                        out.append(((f.value.attr, f.attr), inl))
                walk(c, inl)
        walk(fn, False)
        return out

    def why(self, target, inl, stack=()):
        """"" or the way to the heavy call ("x.f > y.g > subprocess.run")."""
        if target in ALWAYS:
            return f"{target[0]}.{target[1]}"
        if inl and target in PER_DOC:
            return f"loop:{target[0]}.{target[1]}"
        if target in PER_DOC or target not in self.funcs or target in stack or len(stack) > 12:
            return ""
        if target not in self.memo:
            self.memo[target] = ""
            for t, i in self.calls(self.funcs[target], target[0]):
                w = self.why(t, i, stack + (target,))
                if w:
                    self.memo[target] = w
                    break
        return f"{target[0]}.{target[1]} > {self.memo[target]}" if self.memo[target] else ""

    def found(self):
        hits = {}
        for key, fn in self.coros.items():
            for t, inl in self.calls(fn, key[0]):
                w = self.why(t, inl)
                if w:
                    hits[key] = w
                    break
        return hits


class OffTheLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hits = _Graph().found()

    def test_no_heavy_work_on_the_loop(self):
        new = {f"{m}.{f}: {w}" for (m, f), w in self.hits.items() if (m, f) not in LATER}
        self.assertFalse(new, "heavy work on the panel's event loop: move it into asyncio.to_thread or vorrang.in_thread "
                              "(docs/de/richtlinien.md, Teil 2.2)")

    def test_the_later_list_only_shrinks(self):
        gone = sorted(f"{m}.{f}" for m, f in LATER if (m, f) not in self.hits)
        self.assertFalse(gone, "no longer found: take it out of LATER in the same commit")
        for k, why in LATER.items():
            self.assertRegex(why, r"^[^:]+: .{10,}", k)

    def test_the_rule_finds_what_hung_the_pi(self):
        """Ordner auslassen with thousands of documents (2026-10-18): one write per document in a loop on the loop."""
        src = ("import documents\n"
               "def apply(uid, ids):\n    for d in ids:\n        documents.delete(uid, d)\n"
               "def one(uid, d):\n    documents.delete(uid, d)\n"
               "async def add(uid, ids):\n    apply(uid, ids)\n"
               "async def single(uid, d):\n    one(uid, d)\n")
        g, coros = self._graph(src)
        self.assertEqual([g.why(t, i) for t, i in g.calls(coros["add"], "x")], ["x.apply > loop:documents.delete"])
        self.assertFalse(any(g.why(t, i) for t, i in g.calls(coros["single"], "x")))   # one document is fine

    @staticmethod
    def _graph(src):
        tree = ast.parse(src)
        g = _Graph.__new__(_Graph)
        g.funcs = {("x", n.name): n for n in tree.body if isinstance(n, ast.FunctionDef)}
        g.memo = {}
        return g, {n.name: n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}

    def test_a_thread_takes_it_off_the_loop(self):
        src = ("import asyncio, subprocess\n"
               "def slow():\n    subprocess.run(['true'])\n"
               "async def bad():\n    slow()\n"
               "async def good():\n    await asyncio.to_thread(slow)\n    await asyncio.to_thread(lambda: slow())\n")
        g, coros = self._graph(src)
        bad = [g.why(t, i) for t, i in g.calls(coros["bad"], "x")]
        good = [g.why(t, i) for t, i in g.calls(coros["good"], "x")]
        self.assertIn("x.slow > subprocess.run", bad)
        self.assertFalse(any(good))


class Watcher(unittest.TestCase):
    def setUp(self):
        self.old = dict(loopwacht._st)
        self.old_stalls = list(loopwacht._stalls)
        loopwacht._stalls.clear()
        loopwacht._st.update(last=None, tid=None, since=None, where="", warned=False, started=None)

    def tearDown(self):
        loopwacht._st.clear()
        loopwacht._st.update(self.old)
        loopwacht._stalls.clear()
        loopwacht._stalls.extend(self.old_stalls)

    def _tick(self, now, frames=None):
        out = io.StringIO()
        sent = []
        with redirect_stdout(out), mock.patch.object(loopwacht, "_notify", lambda m: sent.append(m) or True):
            r = loopwacht.tick(now, frames)
        return r, out.getvalue(), sent

    def test_start_up_pings_only_for_a_while(self):
        r, _, sent = self._tick(1000.0)
        self.assertEqual((r, sent), ("start", ["WATCHDOG=1"]))
        _, _, sent = self._tick(1000.0 + loopwacht.START_MAX_S + 1)
        self.assertEqual(sent, [])

    def test_a_stall_is_logged_with_its_place_and_systemd_is_left_to_restart(self):
        loopwacht._st.update(last=100.0, tid=7)
        r, out, sent = self._tick(101.0)
        self.assertEqual((r, out, sent), ("ok", "", ["WATCHDOG=1"]))

        def deep():
            return sys._getframe()
        frames = {7: deep()}
        r, out, sent = self._tick(100.0 + loopwacht.STALL_S, frames)
        self.assertEqual((r, sent), ("stalled", []))       # no ping: systemd's WatchdogSec runs out
        # outermost and innermost own frame: the running test (the endpoint in the panel) and where it stands
        self.assertRegex(out, r"^loopwacht: stalled \| test_loopwacht\.test_a_stall\w* > test_loopwacht\.deep \| 5 s\n$")
        _, out, sent = self._tick(110.0, frames)
        self.assertEqual((out, sent), ("", []))             # one line per stall, not one per second
        _, out, _ = self._tick(100.0 + loopwacht.WARN_S, frames)
        self.assertIn(f"restart after {loopwacht.RESTART_S} s", out)
        _, out, _ = self._tick(100.0 + loopwacht.WARN_S + 1, frames)
        self.assertEqual(out, "")
        loopwacht._st["last"] = 112.0                       # the loop beats again
        r, out, sent = self._tick(112.5)
        self.assertEqual((r, sent), ("ok", ["WATCHDOG=1"]))
        self.assertRegex(out, r"^loopwacht: free again \| test_loopwacht\.test_a_stall\w* > test_loopwacht\.deep \| 12 s\n"
                              r"ereignis: Spark \| Panel hing 12 s\n$")   # Live shows it under Ereignisse
        v = loopwacht.view()
        self.assertEqual((v["n"], v["max_s"], v["letzt_s"], v["jetzt_s"]), (1, 12, 12, 0))

    def test_the_place_names_only_code(self):
        """Outermost and innermost frame of the panel's own code; nothing of a request's content."""
        def inner(text):
            return sys._getframe()

        def outer():
            return inner("geheime Frage an den Spark")
        f = outer()
        w = loopwacht.where(1, {1: f})
        self.assertTrue(w.endswith("test_loopwacht.inner"), w)
        self.assertNotIn("geheim", w)
        self.assertRegex(w, r"^[A-Za-z0-9_.<> ]+$")
        self.assertEqual(loopwacht.where(2, {}), "")

    def test_hint_on_the_admin_pages_for_an_hour(self):
        loopwacht._stalls.append((10_000.0, 30, "x.y"))
        a = loopwacht.alerts(now=10_000.0 + 120)
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["kind"], a[0]["level"], a[0]["go"]), ("loopwacht", "warn", "Zustand → Logs → Diagnose"))
        self.assertIn("vor 2 min 30 s lang still", a[0]["text"])
        self.assertNotIn("x.y", a[0]["text"])
        self.assertEqual(loopwacht.alerts(now=10_000.0 + loopwacht.HINT_S + 1), [])

    def test_notify_reaches_systemd_and_is_quiet_without_it(self):
        d = tempfile.mkdtemp(prefix="lw-")
        path = os.path.join(d, "notify")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.bind(path)
        try:
            with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": path}):
                self.assertTrue(loopwacht._notify("WATCHDOG=1"))
            self.assertEqual(s.recv(64), b"WATCHDOG=1")
            with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": ""}):
                self.assertFalse(loopwacht._notify("WATCHDOG=1"))
        finally:
            s.close()

    def test_the_beat_runs_on_the_loop(self):
        import asyncio

        async def go():
            t = asyncio.ensure_future(loopwacht.beat())
            await asyncio.sleep(0.05)
            t.cancel()
            return threading.get_ident()
        tid = asyncio.run(go())
        self.assertEqual(loopwacht._st["tid"], tid)
        self.assertIsNotNone(loopwacht._st["last"])

    def test_panel_starts_it(self):
        with open(os.path.join(PANEL, "panel.py"), encoding="utf-8") as f:
            src = f.read()
        serve = src[src.index("async def serve"):]
        self.assertIn("loopwacht.start()", serve)


class Background(unittest.TestCase):
    """The search's embedding worker is a child of the panel and shares its CPU limit: half of the cores at most,
    the catch-up only in time nobody else wants (htop 2026-10-18: four threads at ~60 % during 46000 passages)."""

    def test_embed_worker_computes_behind_speech(self):
        import embed_worker
        import subprocess
        self.assertLessEqual(embed_worker.THREADS, max(1, (os.cpu_count() or 2) // 2))
        src = open(embed_worker.__file__, encoding="utf-8").read()
        self.assertNotRegex(src, r"intra_op_num_threads = \d")
        self.assertEqual(src.count("intra_op_num_threads = THREADS"), 2)
        self.assertIn("hinten(True)", src)
        self.assertIn("hinten(False)", src)
        code = ("import os, sys; sys.path.insert(0, sys.argv[1]); import embed_worker; n = os.nice(0); "
                "embed_worker.hinten(True); print(os.nice(0) - n, getattr(os, 'SCHED_IDLE', -1) == os.sched_getscheduler(0))")
        out = subprocess.run([sys.executable, "-c", code, os.path.dirname(embed_worker.__file__)],
                             capture_output=True, text=True, timeout=60).stdout.split()
        self.assertGreater(int(out[0]), 0)
        if hasattr(os, "SCHED_IDLE"):
            self.assertEqual(out[1], "True")


class Limits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sh = helpers.repo_file("install.sh")

    def unit(self, name):
        m = re.search(r"cat >/etc/systemd/system/" + re.escape(name) + r" <<EOF\n(.*?)\nEOF\n", self.sh, re.S)
        self.assertIsNotNone(m, name)
        return m.group(1)

    def test_panel_unit_has_the_watchdog_and_limits(self):
        u = self.unit("speech-spark-panel.service")
        self.assertIn(f"WatchdogSec={loopwacht.RESTART_S}\n", u)
        for line in ("NotifyAccess=main", "Restart=always", "MemoryHigh=3G", "MemoryMax=4G", "CPUQuota=$PANEL_CPU",
                     "CPUWeight=1000", "IOWeight=1000"):
            self.assertIn(line + "\n", u)
        self.assertIn("PANEL_CPU=$(( $(nproc) > 1 ? ($(nproc) - 1) * 100 : 100 ))%", self.sh)
        self.assertLess(loopwacht.STALL_S, loopwacht.WARN_S)
        self.assertLess(loopwacht.WARN_S, loopwacht.RESTART_S)

    def test_speech_comes_first(self):
        """Dominik 2026-10-18: "der Sprachassistent muss immer Vorrang haben": the panel and Parakeet get the share of
        the speech services, never less; only the last core stays for the system."""
        u = self.unit("speech-spark-notasr.service")
        for line in ("Nice=-5", "CPUWeight=1000", "IOWeight=1000", "CPUQuota=$PANEL_CPU", "MemoryMax=2G"):
            self.assertIn(line + "\n", u)

    def test_hardware_watchdog_only_on_a_raspberry_pi(self):
        i = self.sh.index("WD_CONF=/etc/systemd/system.conf.d/speech-spark-watchdog.conf")
        part = self.sh[i:i + 1400]
        self.assertIn("[ -c /dev/watchdog ] && tr -d '\\0' </proc/device-tree/model 2>/dev/null | grep -q '^Raspberry Pi'", part)
        self.assertIn("RuntimeWatchdogSec=15\n", part)
        self.assertIn('rm -f "$WD_CONF"', part)      # off again on another computer
        un = helpers.repo_file("uninstall.sh")
        self.assertIn("rm -f /etc/systemd/system.conf.d/speech-spark-watchdog.conf", un)


if __name__ == "__main__":
    unittest.main()
