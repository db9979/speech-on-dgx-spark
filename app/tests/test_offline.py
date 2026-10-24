"""Ohne Internet (offline.py, Dominik 2026-10-23: „sind wir komplett offline fähig“).

Wächter against downloads at run time: every model loader reads only its own disk (modelle.ohne_netz before
from_pretrained, HF_HUB_OFFLINE in the engines and the Notbetrieb), a download call sits only where its reason is
listed here (DOWNLOADS), no packages or images are fetched while the Spark runs (only install.sh and the measurement
`modelle messen` pull), and the pages load nothing from outside. Then the check itself: the SNTP question and its
answer, the time server's address (only a private IPv4 address, the same check as install.sh), the clock rows, the
model computer's clock through its Wärter and its refusal because of the time (a hint on top of the admin pages),
the names from outside, the endpoint (admin only, one journal line with counts, never a name).
No test depends on the wall clock or the network: times and answers are passed in or faked.
"""
import ast
import asyncio
import glob
import hashlib
import io
import os
import re
import secrets
import socket
import struct
import tempfile
import sys
import threading
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import common  # noqa: E402
import dienstwacht  # noqa: E402
import modelle  # noqa: E402
import offline  # noqa: E402
import panel  # noqa: E402
import parakeet  # noqa: E402
import steuer  # noqa: E402
import tarswart  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(APP, "panel")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})

# (file, function) -> why a download may happen there while the Spark runs; any other place is red
DOWNLOADS = {
    ("modelle.py", "_laden"): "checks the cache first (modelle.pruefen) and fetches only a missing or changed file of the "
                              "pinned commit; afterwards the speech servers call ohne_netz()",
    ("parakeet.py", "download"): "takes the files from the disk first (local_files_only), fetches only when one is missing",
    ("bildmodell.py", "fetch"): "only from install.sh (python3 bildmodell.py download), for Bilder and Musik",
    ("embed_worker.py", "hole"): "a pinned commit: huggingface_hub answers a file of a commit from the cache without asking",
}


def sources():
    """The Python files that run on the Spark (no tests, no terminal program for other computers)."""
    out = sorted(glob.glob(os.path.join(APP, "*.py")) + glob.glob(os.path.join(PANEL, "*.py")))
    return [f for f in out if os.path.basename(f) != "selftest.py"]


def calls_in_functions(path, names):
    """[(function, line, called name)] of the calls to one of names."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
                if name in names:
                    out.append((fn, n.lineno, name))
    return out


class Downloads(unittest.TestCase):
    def test_every_loader_reads_only_its_disk(self):
        """from_pretrained only after modelle.ohne_netz() in the same function (no question to the Hub that hangs)."""
        bad, seen = [], 0
        for path in sources():
            for fn, line, _ in calls_in_functions(path, {"from_pretrained"}):
                seen += 1
                before = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                          and n.func.attr == "ohne_netz" and n.lineno < line]
                if not before:
                    bad.append(f"{os.path.basename(path)}:{line}")
        self.assertGreaterEqual(seen, 2, "asr_server and tts_server load with from_pretrained")
        self.assertEqual(bad, [], "from_pretrained without modelle.ohne_netz() before it")

    def test_downloads_only_where_listed(self):
        found = {}
        for path in sources():
            for fn, line, _ in calls_in_functions(path, {"snapshot_download", "hf_hub_download"}):
                found.setdefault((os.path.basename(path), fn.name), line)
        self.assertEqual(sorted(set(found) - set(DOWNLOADS)), [], "a new download at run time: take it from the disk, "
                                                                  "or list it with its reason in DOWNLOADS")
        self.assertEqual(sorted(set(DOWNLOADS) - set(found)), [], "a listed download is gone: take its line away")
        for why in DOWNLOADS.values():
            self.assertGreater(len(why), 20)

    def test_engines_and_the_notbetrieb_load_offline(self):
        engine = open(os.path.join(APP, "engine.sh"), encoding="utf-8").read()
        self.assertGreaterEqual(len(re.findall(r"export HF_HUB_OFFLINE=1", engine)), 2, "the own LLM and the speech engines")
        self.assertIn('"HF_HUB_OFFLINE": "1"', open(os.path.join(APP, "modelle.py"), encoding="utf-8").read(), "the Docker recipe")
        install = helpers.repo_file("install.sh")
        self.assertRegex(install, r"Environment=HF_HOME=\$VAR/hf HF_HUB_OFFLINE=1 SPEECH_SPARK_NOTASR=1")

    def test_no_packages_or_images_while_running(self):
        """pip, npm and docker pull only in install.sh; on the running Spark only the measurement pulls its image."""
        rx = re.compile(r"\bpip3?\s+install\b|[\"']pip3?[\"']\s*,\s*[\"']install|\bnpm\s+(install|ci)\b|\bnpx\s|docker\s+pull|[\"']pull[\"']")
        hits = []
        for path in sources() + sorted(glob.glob(os.path.join(APP, "*.sh"))):
            for i, line in enumerate(open(path, encoding="utf-8"), 1):
                if rx.search(line) and not line.lstrip().startswith("#"):
                    hits.append((os.path.basename(path), line.strip()))
        self.assertEqual([h for h in hits if not (h[0] == "speech-spark.sh" and "messung" in h[1])], [],
                         "fetching packages or images while the Spark runs")
        self.assertEqual(len(hits), 1, "the one pull of `modelle messen`")

    def test_pages_load_nothing_from_outside(self):
        static = os.path.join(PANEL, "static")
        rx = re.compile(r"<(script|link|img|iframe|audio|video|source)\b[^>]*\b(src|href)=[\"'](https?:)?//|url\(\s*[\"']?(https?:)?//"
                        r"|@import\s+[\"']?(url\()?[\"']?https?:|\bimport\s*\(\s*[\"']https?:|from\s+[\"']https?:")
        bad = []
        for path in glob.glob(os.path.join(static, "**", "*.*"), recursive=True):
            if path.endswith((".html", ".css", ".js")):
                for i, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
                    if rx.search(line):
                        bad.append(f"{os.path.relpath(path, static)}:{i}")
        self.assertEqual(bad, [], "a page that loads from outside breaks without the internet")

    def test_the_rule_finds_what_it_should(self):
        rx = re.compile(r"url\(\s*[\"']?(https?:)?//")
        self.assertTrue(rx.search("src:url('https://fonts.example/x.woff2')"))
        self.assertFalse(rx.search("background:url(/static/x.png)"))

    def test_ohne_netz_sets_the_switches(self):
        hub = types.SimpleNamespace(HF_HUB_OFFLINE=False)
        tf = types.SimpleNamespace(_is_offline_mode=False)
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.dict(sys.modules, {"huggingface_hub.constants": hub, "transformers.utils.hub": tf}):
            for k in modelle.OHNE_NETZ:
                os.environ.pop(k, None)
            modelle.ohne_netz()
            self.assertEqual({k: os.environ.get(k) for k in modelle.OHNE_NETZ}, modelle.OHNE_NETZ)
        self.assertIs(hub.HF_HUB_OFFLINE, True)
        self.assertIs(tf._is_offline_mode, True)
        self.assertEqual(modelle.OHNE_NETZ["HF_HUB_OFFLINE"], "1")

    def test_parakeet_takes_the_disk_first(self):
        folder = os.path.join(helpers.TMP, "parakeet-offline")
        os.makedirs(folder, exist_ok=True)
        calls = []

        def snap(repo, revision, allow_patterns, local_files_only=False):
            calls.append(local_files_only)
            return folder
        fake = types.SimpleNamespace(snapshot_download=snap)
        with mock.patch.dict(sys.modules, {"huggingface_hub": fake}):
            self.assertEqual(parakeet.download(), folder)
            self.assertEqual(calls, [True, False], "a file missing: fetched")
            for f in parakeet.FILES:
                open(os.path.join(folder, f), "w").close()
            calls.clear()
            self.assertEqual(parakeet.download(), folder)
            self.assertEqual(calls, [True], "all there: no question to the Hub")


def packet(server_t, li=0, mode=4, stratum=2):
    secs = int(server_t) + offline.NTP_1970
    frac = int((server_t - int(server_t)) * 2 ** 32)
    return bytes([(li << 6) | (4 << 3) | mode, stratum]) + 38 * b"\0" + struct.pack("!II", secs, frac)


class Zeiger(unittest.TestCase):
    """refs/main of every pinned model on its checked commit (tars 2026-10-23: vllm-omni asked for the VoiceDesign
    model without a revision, found no refs/main offline and speech-spark-tts-design restarted every 30 s)."""
    REV = "a" * 40

    def cache(self, hub):
        d = os.path.join(hub, "models--A--B")
        snap = os.path.join(d, "snapshots", self.REV)
        os.makedirs(snap)
        os.makedirs(os.path.join(d, "blobs"))
        for name, data in (("config.json", b"{}"), ("model.safetensors", b"x" * 64)):
            blob = (hashlib.sha256(data).hexdigest() if name.endswith(".safetensors")
                    else hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest())
            with open(os.path.join(d, "blobs", blob), "wb") as f:
                f.write(data)
            os.symlink(os.path.join("..", "..", "blobs", blob), os.path.join(snap, name))
        return d

    def test_a_checked_cache_gets_its_pointer_without_a_download(self):
        import huggingface_hub
        with tempfile.TemporaryDirectory() as hub:
            d = self.cache(hub)
            with self.assertRaises(Exception):          # the failure on tars: no refs/main, offline
                huggingface_hub.snapshot_download("A/B", cache_dir=hub, local_files_only=True)
            with mock.patch.object(huggingface_hub, "snapshot_download", side_effect=AssertionError("download")):
                self.assertEqual(modelle._laden("A/B", self.REV, d), self.REV)
            with open(os.path.join(d, "refs", "main")) as f:
                self.assertEqual(f.read(), self.REV)
            # a loader without a revision now finds exactly the checked snapshot, offline
            path = huggingface_hub.snapshot_download("A/B", cache_dir=hub, local_files_only=True)
            self.assertEqual(os.path.realpath(path), os.path.realpath(os.path.join(d, "snapshots", self.REV)))

    def test_the_pointer_is_written_once_and_only_to_a_checked_commit(self):
        with tempfile.TemporaryDirectory() as hub:
            d = self.cache(hub)
            self.assertTrue(modelle.zeiger(d, self.REV))
            self.assertFalse(modelle.zeiger(d, self.REV))          # unchanged: nothing written
            os.unlink(os.path.join(d, "refs", "main"))
            os.symlink(os.path.join(hub, "anderswo"), os.path.join(d, "refs", "main"))
            self.assertTrue(modelle.zeiger(d, self.REV))            # a link is replaced by a plain file
            self.assertFalse(os.path.islink(os.path.join(d, "refs", "main")))
            for bad in ("b" * 40, "../../etc", "", None):          # no snapshot or no commit
                with self.assertRaises(modelle.Fehler):
                    modelle.zeiger(d, bad)
            self.assertEqual(os.listdir(os.path.join(d, "refs")), ["main"])


class Uhr(unittest.TestCase):
    def test_sntp_answer(self):
        t0, t1 = 1_800_000_000.0, 1_800_000_000.2
        self.assertEqual(offline.sntp_answer(packet(t0 + 5.1), t0, t1), (5.0, 200))
        self.assertEqual(offline.sntp_answer(packet(t0 - 3.0), t0, t1)[0], -3.1)
        self.assertIsNone(offline.sntp_answer(packet(t0, li=3), t0, t1), "the server has no time itself")
        self.assertIsNone(offline.sntp_answer(packet(t0, stratum=0), t0, t1), "kiss of death")
        self.assertIsNone(offline.sntp_answer(packet(t0, mode=3), t0, t1), "no server answer")
        self.assertIsNone(offline.sntp_answer(b"\x24" * 20, t0, t1))

    def test_one_question_to_a_server_here(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        got = []

        def answer():
            data, addr = srv.recvfrom(512)
            got.append(data)
            srv.sendto(packet(time.time() + 4.0), addr)
        th = threading.Thread(target=answer, daemon=True)
        th.start()
        try:
            with mock.patch.object(offline, "NTP_PORT", port):
                ab, ms = offline.sntp("127.0.0.1", wait=5)
        finally:
            th.join(5)
            srv.close()
        self.assertAlmostEqual(ab, 4.0, delta=0.5)
        self.assertGreaterEqual(ms, 0)
        self.assertEqual(len(got[0]), 48)
        self.assertEqual(got[0][0], 0x1b, "client mode, version 3, nothing else sent")
        self.assertEqual(set(got[0][1:]), {0})

    def test_no_answer_is_none(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        try:
            with mock.patch.object(offline, "NTP_PORT", srv.getsockname()[1]):
                self.assertIsNone(offline.sntp("127.0.0.1", wait=0.2))
        finally:
            srv.close()

    def test_only_a_private_ipv4_address(self):
        for ok in ("192.168.10.1", "192.168.178.1", "10.0.0.2", "172.16.4.1"):
            self.assertEqual(offline.zeitserver(ok), ok)
            self.assertEqual(offline.zeitserver(f" {ok} "), ok)
        for bad in ("", "8.8.8.8", "127.0.0.1", "169.254.1.1", "0.0.0.0", "224.0.0.1", "fritz.box", "192.168.1.1; reboot",
                    "192.168.1.1 8.8.8.8", "999.1.1.1", None, 5, "::1"):
            self.assertEqual(offline.zeitserver(bad), "", bad)

    def test_the_setting_is_checked_like_in_install_sh(self):
        cfg = ADMIN.get("/api/config").json()
        self.addCleanup(lambda: ADMIN.put("/api/config", json=dict(cfg, watch=dict(cfg["watch"], zeitserver=""))))
        for bad in ("8.8.8.8", "fritz.box", "192.168.1.1; reboot"):
            r = ADMIN.put("/api/config", json=dict(cfg, watch=dict(cfg["watch"], zeitserver=bad)))
            self.assertEqual(r.status_code, 400, bad)
        r = ADMIN.put("/api/config", json=dict(cfg, watch=dict(cfg["watch"], zeitserver=" 192.168.10.1 ")))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(ADMIN.get("/api/config").json()["watch"]["zeitserver"], "192.168.10.1")
        install = helpers.repo_file("install.sh")
        self.assertIn("ZS=$(cfg '.watch.zeitserver // \"\"')", install)
        self.assertIn("a.is_private and not (a.is_loopback or a.is_link_local or a.is_unspecified or a.is_multicast)", install)
        self.assertIn("watch", common.SYNC_SECTIONS, "the model computer gets the address with the speech settings")

    def test_the_clock_rows(self):
        cfg = {"watch": {"zeitserver": "192.168.10.1"}, "models": {"host": "192.168.178.171"}}
        with mock.patch.object(offline, "model_local", lambda c: False):
            rows = {r["id"]: r for r in offline.uhr_rows(cfg, hier={"ntp": True}, server=(0.4, 3), modell={"ab": 0.3, "ntp": True})}
            self.assertEqual([rows[k]["level"] for k in ("uhr", "zeitserver", "modelluhr")], ["ok", "ok", "ok"])
            self.assertIn("192.168.10.1", rows["zeitserver"]["de"])
            for ab, level in ((15.0, "warn"), (45.0, "bad"), (-90.0, "bad"), (1.2, "ok")):
                r = offline.uhr_rows(cfg, hier={"ntp": True}, server=(0.0, 1), modell={"ab": ab, "ntp": False})[-1]
                self.assertEqual(r["level"], level, ab)
                self.assertIn("vor" if ab >= 0 else "nach", r["de"])
            self.assertEqual(offline.uhr_rows(cfg, hier={"ntp": True}, server=None, modell={"abgelehnt": True})[1]["level"], "bad")
            self.assertEqual(offline.uhr_rows(cfg, hier={"ntp": True}, server=None, modell={"abgelehnt": True})[-1]["level"], "bad")
            self.assertEqual(offline.uhr_rows(cfg, hier={"ntp": False}, server=(0, 1), modell=None)[0]["level"], "warn")
        none = offline.uhr_rows({"watch": {}}, hier={"ntp": None}, server=None, modell=None)
        self.assertEqual([r["id"] for r in none][:1], ["zeitserver"], "no reading of this clock: no row for it")
        self.assertEqual(none[0]["way"], "zeit")
        for r in offline.uhr_rows(cfg, hier={"ntp": True}, server=(0.0, 1)):
            self.assertTrue(r["de"] and r["en"])

    def test_common_uhr(self):
        u = common.uhr()
        self.assertEqual(set(u), {"t", "ntp"})
        self.assertIn(u["ntp"], (True, False, None))
        self.assertIsInstance(u["t"], float)


class Modellrechner(unittest.TestCase):
    """The model computer's clock through its Wärter, and its refusal because of the time."""
    def setUp(self):
        key = secrets.token_bytes(32)
        path = os.path.join(helpers.TMP, "waerter-offline.key")
        with open(path, "w") as f:
            f.write(key.hex())
        p = mock.patch.object(common, "WAERTER_KEY", path)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(tarswart, "run", lambda cmd, timeout=10, env=None: (1, ""))
        p.start()
        self.addCleanup(p.stop)
        tarswart._seen.clear()
        tarswart._times.clear()
        steuer._client = TestClient(tarswart.app)
        self.addCleanup(setattr, steuer, "_client", None)
        self.addCleanup(steuer._status.pop, "zeit", None)

    def test_its_clock_against_this_one(self):
        with mock.patch.object(tarswart, "uhr", lambda: {"t": time.time() + 7.0, "ntp": False}):
            d = steuer.uhr_vergleich()
        self.assertAlmostEqual(d["ab"], 7.0, delta=1.0)
        self.assertIs(d["ntp"], False)

    def test_refused_because_of_the_time(self):
        with redirect_stdout(io.StringIO()), mock.patch.object(tarswart, "WINDOW", -1):   # every time counts as far off
            d = steuer.uhr_vergleich()
        self.assertEqual(d, {"abgelehnt": True}, "the Wärter saw a time far off and refused")
        t = steuer._status["zeit"]
        self.assertTrue(steuer.uhr_abgelehnt(now=t + 10))
        self.assertFalse(steuer.uhr_abgelehnt(now=t + steuer.ZEIT_S + 1))
        a = offline.alerts(now=t + 10)
        self.assertEqual([x["kind"] for x in a], ["uhr"])
        self.assertEqual(a[0]["go"], "Einstellungen → Spark → Betrieb → Zeitserver im Heimnetz")
        self.assertEqual(offline.alerts(now=t + steuer.ZEIT_S + 1), [])

    def test_an_older_model_computer_without_a_clock(self):
        real = tarswart.status
        with mock.patch.object(tarswart, "status", lambda: {k: v for k, v in real().items() if k != "uhr"}):
            self.assertIsNone(steuer.uhr_vergleich())


class Check(unittest.TestCase):
    def setUp(self):
        async def probe(sid, key, p, cfg):
            return dienstwacht.Probe(sid != "tts")
        for target, name, value in ((dienstwacht, "probe", probe), (offline, "_where", lambda h: "net"),
                                    (offline, "sntp", lambda host, wait=1.5: (0.2, 4)),
                                    (steuer, "uhr_vergleich", lambda cfg=None: {"ab": 0.5, "ntp": True})):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_admin_only(self):
        self.assertIn(TestClient(panel.app).post("/api/admin/offline/check").status_code, (401, 403))

    def test_rows_counts_and_one_journal_line(self):
        out = io.StringIO()
        with redirect_stdout(out):
            r = ADMIN.post("/api/admin/offline/check", headers={"host": "spark.example.org"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        ids = [x["id"] for x in d["rows"]]
        self.assertIn("zeitserver", ids)
        self.assertIn("pause", ids)
        name = next(x for x in d["rows"] if x["id"] == "name")
        self.assertEqual(name["level"], "warn")
        self.assertIn("spark.example.org", name["de"])
        self.assertEqual(sum(d["count"].values()), sum(x["level"] != "info" for x in d["rows"]))
        for x in d["rows"]:
            self.assertIn(x["level"], ("ok", "warn", "bad", "info"))
            self.assertIn(x["way"], ("", "zeit", "modelle", "dienste"))
        lines = [ln for ln in out.getvalue().splitlines() if ln.startswith("offline:")]
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^offline: pruefung \| \d+ ok \d+ warnung \d+ fehler \| \d+ ms$")
        self.assertNotIn("example", out.getvalue(), "no name in the journal")

    def test_names(self):
        req = types.SimpleNamespace(headers={"host": "Spark.Example.org:31443", "x-forwarded-host": "a.b.de, x"})
        cfg = {"chat": {"verbund_domain": "own.example.net"}}
        self.assertEqual(offline._names(req, cfg), ["own.example.net", "a.b.de", "spark.example.org"])
        req = types.SimpleNamespace(headers={"host": "192.168.178.20:31080"})
        self.assertEqual(offline._names(req, {"chat": {}}), [], "an address is no name")
        req = types.SimpleNamespace(headers={"host": "spark.local"})
        self.assertEqual(offline._names(req, {"chat": {}}), [])

    def test_a_name_in_the_home_network(self):
        with mock.patch.object(offline, "_where", lambda h: "lan"):
            rows = asyncio.run(offline._addresses(types.SimpleNamespace(headers={"host": "spark.example.org"}), {"chat": {}}))
        self.assertEqual([r["level"] for r in rows], ["ok"])


if __name__ == "__main__":
    unittest.main()
