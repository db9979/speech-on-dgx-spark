"""pip hash lock for the panel's environment (V01.0.286): every package pinned with its hashes, install.sh builds a new
environment from it with --no-deps --require-hashes, the GitHub test installs the same file, and the list of wanted
packages is requirements-panel.in. packaging stays >= 24 although rmscene asks for < 24
(V01.0.278: an older packaging broke wheel). (install.sh and the workflow are skipped in an app/-only copy.)"""
import os
import re
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)


def wanted():
    with open(os.path.join(APP, "requirements-panel.in")) as f:
        return [x.strip() for x in f if x.strip() and not x.startswith("#") and "# lock only" not in x]


class Lock(unittest.TestCase):
    def test_every_package_pinned_with_hashes(self):
        with open(os.path.join(APP, "requirements-panel.lock")) as f:
            text = f.read()
        blocks = re.split(r"\n(?=[A-Za-z0-9])", text.split("\n", 1)[1] if text.startswith("#") else text)
        pins = {}
        for b in blocks:
            if not b.strip() or b.lstrip().startswith("#"):
                continue
            m = re.match(r"([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;\\]+)", b)
            self.assertIsNotNone(m, b[:80])
            self.assertIn("--hash=sha256:", b, m.group(1))
            pins[m.group(1).lower().replace("_", "-")] = m.group(3)
        for w in wanted():
            name = re.split(r"[\[=<>]", w)[0].lower().replace("_", "-")
            self.assertIn(name, pins, w)
            if "==" in w:
                self.assertEqual(pins[name], w.split("==")[1], w)
        self.assertGreater(len(pins), 40)
        self.assertGreaterEqual(int(pins["packaging"].split(".")[0]), 24)

    def test_install_and_ci_use_it(self):
        sh = os.path.join(ROOT, "install.sh")
        if not os.path.exists(sh):
            self.skipTest("install.sh is not in an app/-only copy")
        with open(sh) as f:
            text = f.read()
        self.assertIn('install -q --no-deps --require-hashes -r "$PANEL_LOCK"', text)
        # one way only (Ausdünnen 8): no package list of its own beside the lock, no extra lock files
        self.assertNotIn("make_venv panel", text)
        self.assertNotIn("legacy-r2", text)
        self.assertEqual(sorted(f for f in os.listdir(APP) if f.startswith("requirements-") and f.endswith(".lock")),
                         ["requirements-panel.lock", "requirements-ytdlp.lock"])
        with open(os.path.join(ROOT, ".github", "workflows", "tests.yml")) as f:
            self.assertIn("--no-deps --require-hashes -r app/requirements-panel.lock", f.read())


class Mindestversionen(unittest.TestCase):
    """app/mindestversionen.txt (spark-meldungen #5-#10, V01.1.448): security floors for the environments on tars that
    have no lock file, handed to pip and uv as constraints; its checksum is part of each .pkgs mark."""

    def test_file_only_floors(self):
        with open(os.path.join(APP, "mindestversionen.txt")) as f:
            lines = [x.strip() for x in f if x.strip() and not x.startswith("#")]
        self.assertTrue(lines)
        for x in lines:
            self.assertRegex(x, r"^[a-z0-9][a-z0-9._\-]*>=[0-9][0-9.]*$", x)
        self.assertEqual(len({x.split(">=")[0] for x in lines}), len(lines))

    def test_install_uses_them(self):
        sh = os.path.join(ROOT, "install.sh")
        if not os.path.exists(sh):
            self.skipTest("install.sh is not in an app/-only copy")
        with open(sh) as f:
            text = f.read()
        self.assertIn('FLOORS="$INSTALL_FROM/app/mindestversionen.txt"', text)
        self.assertIn('sig="pkgs-r2 $* $FLOORS_SUM"', text)
        self.assertEqual(text.count('-c "$FLOORS"'), 4)   # torch, torch extras, plain pip, uv for venv-engine
        self.assertEqual(text.count("engine $VLLM_VERSION $VLLM_OMNI_VERSION $FLOORS_SUM"), 2)
        self.assertNotIn("pkgs-r1", text)

    def test_pip_in_panel_lock(self):
        with open(os.path.join(APP, "requirements-panel.lock")) as f:
            m = re.search(r"^pip==([0-9.]+) \\$", f.read(), re.M)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(tuple(int(x) for x in m.group(1).split(".")[:2]), (26, 3))
