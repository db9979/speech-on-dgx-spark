"""pip hash lock for the panel's environment (V01.0.286): every package pinned with its hashes, install.sh builds a new
environment from it with --no-deps --require-hashes, the GitHub test installs the same file, and the list of wanted
packages is the same in install.sh and requirements-panel.in. packaging stays >= 24 although rmscene asks for < 24
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
        line = re.search(r"make_venv panel (.*?)(?:\s+#|$)", text, re.M).group(1)
        listed = [x.strip('"') for x in re.findall(r'"[^"]+"|\S+', line)]
        listed += re.findall(r'install -q --no-deps "((?:rmscene|fido2)==[^"]+)"', text)   # alone: rmscene's packaging<24 pin, fido2's cryptography cap
        self.assertEqual(sorted(listed), sorted(wanted()))
        with open(os.path.join(ROOT, ".github", "workflows", "tests.yml")) as f:
            self.assertIn("--no-deps --require-hashes -r app/requirements-panel.lock", f.read())
