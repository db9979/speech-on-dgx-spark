"""GitHub workflows stay hardened (V01.0.389): actions pinned to a commit, write access only on the job that needs
it, signing keys only through the environment "release" (main only), no pull_request_target, checkouts keep no
token unless the job pushes with git. (.github is not part of an app/-only copy; then this is skipped.)"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WFS = os.path.join(ROOT, ".github", "workflows")
SIGNING = ("ANDROID_KEYSTORE", "ASC_KEY", "ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_TEAM_ID", "MAC_DEVID_P12")
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
