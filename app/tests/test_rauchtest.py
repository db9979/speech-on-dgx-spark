"""Smoke test of an update (install.sh runs only this file when the version passed GitHub's whole test run):
every module loads with the packages of this Spark, the panel starts and answers, and app/restart-map knows
every file the ASR and TTS front ends run from (an update restarts them only when one of those changed).
Short on purpose: the whole self-test already ran on GitHub for exactly this commit."""
import ast
import glob
import importlib
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

APP = helpers.APP
# the scripts each front end starts (both kinds: the proxy in front of an engine, the transformers server)
ENTRY = {"asr": ("asr_proxy.py", "asr_server.py"), "tts": ("tts_proxy.py", "tts_server.py"), "bild": ("bild_server.py",),
         "llmtor": ("llm_tor.py",), "tlstor": ("tlstor.py",), "waerter": ("tarswart.py",)}
SAFE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")


def restart_map(path=os.path.join(APP, "restart-map")):
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                name, _, files = line.partition(":")
                out[name.strip()] = files.split()
    return out


def local_imports(path):
    """Modules of app/ a file imports, also inside functions (lazy imports load from disk later)."""
    tree = ast.parse(open(path).read(), path)
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            names.add(n.module.split(".")[0])
    return {m + ".py" for m in names if os.path.isfile(os.path.join(APP, m + ".py"))}


def needs(entry):
    """The entry script and every app/ module it reaches, transitively."""
    seen, todo = set(), [entry]
    while todo:
        f = todo.pop()
        if f not in seen:
            seen.add(f)
            todo += local_imports(os.path.join(APP, f))
    return seen


class Smoke(unittest.TestCase):
    def test_every_module_loads(self):
        for path in sorted(glob.glob(os.path.join(APP, "panel", "*.py"))):
            with self.subTest(module=os.path.basename(path)):
                importlib.import_module(os.path.basename(path)[:-3])
        for name in ("common", "textnorm", "tempo", "parakeet", "asr_proxy", "tts_proxy", "llm_tor", "einordnung", "modelle"):
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_panel_starts_and_answers(self):
        c = TestClient(panel.app)
        self.assertEqual(c.get("/").status_code, 200)
        self.assertEqual(c.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        self.assertEqual(c.get("/api/whoami").status_code, 200)
        self.assertEqual(c.get("/api/config").status_code, 200)


class RestartMap(unittest.TestCase):
    """install.sh restarts the ASR / TTS front end in an update only when a file listed here changed."""

    def test_map_knows_every_file_the_front_ends_run_from(self):
        m = restart_map()
        for svc, entries in ENTRY.items():
            self.assertIn(svc, m)
            for e in entries:
                missing = needs(e) - set(m[svc])
                self.assertFalse(missing, f"app/restart-map, line {svc}: also needs {sorted(missing)}")
            self.assertIn("config.default.json", m[svc])   # common.shipped() reads it

    def test_listed_files_exist_and_stay_inside_app(self):
        for svc, files in restart_map().items():
            self.assertIn(svc, ENTRY, "install.sh only knows asr, tts, bild, llmtor, tlstor and waerter")
            for f in files:
                self.assertTrue(SAFE.fullmatch(f) and ".." not in f, f)
                self.assertTrue(os.path.isfile(os.path.join(APP, f)), f"app/restart-map: {f} does not exist")

    def test_a_new_import_is_noticed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.py")
            with open(p, "w") as f:
                f.write("import os\nfrom common import load_config\ndef late():\n    import textnorm\n")
            self.assertEqual(local_imports(p), {"common.py", "textnorm.py"})


if __name__ == "__main__":
    unittest.main()
