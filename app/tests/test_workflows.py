"""GitHub workflows stay hardened (V01.0.389): actions pinned to a commit, write access only on the job that needs
it, signing keys only through the environment "release" (main only), no pull_request_target, checkouts keep no
token unless the job pushes with git. (.github is not part of an app/-only copy; then this is skipped.)"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WFS = os.path.join(ROOT, ".github", "workflows")
SIGNING = ("ANDROID_KEYSTORE", "ASC_KEY", "ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_TEAM_ID", "MAC_DEVID_P12",
           "UPDATE_SIGNING_KEY")
MOVER = "schluessel-umziehen.yml"       # reads the repository copies once to move them into the environment
GIT_PUSH = {"screenshots.yml"}           # pushes with the checkout's own credentials


def workflows():
    files = sorted(glob.glob(os.path.join(WFS, "*.yml")))
    if not files:
        raise unittest.SkipTest(".github is not part of this copy")
    return [(os.path.basename(f), open(f, encoding="utf-8").read()) for f in files]


def jobs(text):
    """{job name: its lines} from the jobs: block (two-space indented keys)."""
    body = text.split("\njobs:\n", 1)[1]
    out, name = {}, None
    for line in body.split("\n"):
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            name = m.group(1)
            out[name] = []
        elif name:
            out[name].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


class Workflows(unittest.TestCase):
    def test_actions_pinned_to_commit(self):
        for name, text in workflows():
            for ref in re.findall(r"^\s*-?\s*uses:\s*(\S+)", text, re.M):
                if ref.startswith("./"):
                    continue
                self.assertRegex(ref, r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$", f"{name}: {ref} not pinned to a commit")

    def test_write_only_on_jobs(self):
        for name, text in workflows():
            top = text.split("\njobs:\n", 1)[0]
            self.assertNotRegex(top, r"\n\s+[a-z-]+:\s*write", f"{name}: write access for the whole workflow")

    def test_no_pull_request_target(self):
        for name, text in workflows():
            self.assertNotIn("pull_request_target", text, name)

    def test_signing_keys_only_from_environment(self):
        for name, text in workflows():
            if name == MOVER:
                continue
            for job, body in jobs(text).items():
                if any(re.search(rf"secrets\.{s}\b", body) for s in SIGNING):
                    self.assertRegex(body, re.compile(r"^    environment:\s*release\b", re.M), f"{name}/{job}: signing keys outside 'release'")

    def test_mover_main_only_and_quiet(self):
        text = dict(workflows()).get(MOVER)
        if text is None:
            return
        self.assertIn("workflow_dispatch", text)
        self.assertNotIn("\n  push:", text)
        self.assertIn("if: github.ref == 'refs/heads/main'", text)
        self.assertNotRegex(text, r"echo[^\n]*\$\{!n\}", "a key value would reach the log")
        self.assertIn("gh secret delete MIGRATE_TOKEN", text)

    def test_checkout_keeps_no_token(self):
        for name, text in workflows():
            if name in GIT_PUSH:
                continue
            for m in re.finditer(r"uses: actions/checkout@\S+[^\n]*\n((?:[ ]+[^ \n-][^\n]*\n)*)", text):
                self.assertIn("persist-credentials: false", m.group(1), f"{name}: checkout keeps the token")

    def test_releases_only_from_the_environment(self):
        """Paket 4 (M9): a job that publishes a release (firmware rolls out to every speaker at night) runs in
        the environment "release" (main only)."""
        for name, text in workflows():
            for job, body in jobs(text).items():
                if re.search(r"gh release (create|upload)", body):
                    self.assertRegex(body, re.compile(r"^    environment:\s*release\b", re.M), f"{name}/{job}")

    def test_tools_and_images_pinned(self):
        """Paket 4 (M9): build tools with a fixed version, the ESP-IDF container by digest, no token in a URL."""
        wfs = dict(workflows())
        for image in re.findall(r"^\s*image:\s*(\S+)", "\n".join(wfs.values()), re.M):
            self.assertRegex(image, r"@sha256:[0-9a-f]{64}$", image)
        self.assertRegex(wfs["pebble.yml"], r"uv tool install pebble-tool==\d+\.\d+\.\d+\n")
        self.assertRegex(wfs["tests.yml"], r"pip install -q playwright==\d+\.\d+\.\d+\n")
        for name, text in wfs.items():
            self.assertNotRegex(text, r"https://[^\s\"']*\$\{\{\s*(github\.token|secrets\.)", f"{name}: token in a URL")
            self.assertNotRegex(text, r"x-access-token:\$", f"{name}: token in a URL")

    def test_update_signing_stays_optional(self):
        """Paket 4 (M8): manifests are signed only when UPDATE_SIGNING_KEY exists, and the .sig goes out with them."""
        wfs = dict(workflows())
        for name, manifest in (("firmware.yml", "release/manifest.json"), ("begleiter-windows.yml", "dist/begleiter.json"),
                               ("begleiter-mac.yml", "dist/begleiter.json")):
            text = wfs[name]
            self.assertIn("HAS_UPDKEY: ${{ secrets.UPDATE_SIGNING_KEY != '' }}", text, name)
            step = text[text.index("OPTIONAL sign"):]
            step = step[:step.index("\n      - ")]
            self.assertIn("if: env.HAS_UPDKEY == 'true'", step, name)
            self.assertIn("sign-manifest.sh", step, name)
            self.assertIn(manifest, step, name)


class SignManifest(unittest.TestCase):
    """tools/sign-manifest.sh writes what app/panel/signatur.py accepts (needs OpenSSL 3 here)."""

    def test_signature_round_trip(self):
        import shutil
        import subprocess
        import sys
        import tempfile
        script = os.path.join(ROOT, "tools", "sign-manifest.sh")
        if not os.path.exists(script):
            self.skipTest("tools is not part of this copy")
        if not shutil.which("openssl") or "OpenSSL 3" not in subprocess.run(["openssl", "version"], capture_output=True, text=True).stdout:
            self.skipTest("no OpenSSL 3")
        sys.path.insert(0, os.path.join(ROOT, "app", "panel"))
        import signatur
        with tempfile.TemporaryDirectory() as d:
            key = os.path.join(d, "k.pem")
            subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", key], check=True, capture_output=True)
            man = os.path.join(d, "manifest.json")
            with open(man, "wb") as f:
                f.write(b'{"version": "2.5.1.3"}')
            env = dict(os.environ, UPDATE_SIGNING_KEY=open(key).read())
            out = subprocess.run(["bash", script, man], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertNotIn("PRIVATE", out.stdout + out.stderr)
            pub = re.search(r"public key \(signatur.KEYS\): (\S+)", out.stdout).group(1)
            sig = open(man + ".sig", "rb").read()
            old = signatur.KEYS
            signatur.KEYS = (pub,)
            try:
                signatur.verify(b'{"version": "2.5.1.3"}', sig)
                with self.assertRaises(signatur.SignatureError):
                    signatur.verify(b'{"version": "9.9.9.9"}', sig)
            finally:
                signatur.KEYS = old
            # without the key the script refuses instead of publishing unsigned files as signed
            env.pop("UPDATE_SIGNING_KEY")
            self.assertNotEqual(subprocess.run(["bash", script, man], env=env, capture_output=True).returncode, 0)

