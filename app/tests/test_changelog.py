"""Was ist neu (GET /api/changelog, update.py): the changelog of the installed version as plain lines, for the admin
and profiles in their own browser login only (no guests, no device keys), rate limited, size limited, a link instead
of the file is not followed; install.sh copies CHANGELOG.md next to the installed app. No wall clock dependence.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import os
import tempfile
import unittest

from tests import helpers

helpers.start()
import guard  # noqa: E402
import panel  # noqa: E402
import update  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_tracelog import ADMIN, profile  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE = """# Changelog

Every version in one line, newest first.

- **V01.0.12** · 2026-10-11 · Neu: **fett** wird schlicht <script>x</script>
- **V01.0.11** · 2026-10-10 · Zweite Zeile
- 2026-10-05 · Alte Zeile ohne Version
- keine gültige Zeile
"""


class Parse(unittest.TestCase):
    def test_lines(self):
        e = update.parse_changelog(SAMPLE)
        self.assertEqual([x["version"] for x in e], ["V01.0.12", "V01.0.11", None])
        self.assertEqual(e[0]["date"], "2026-10-11")
        self.assertEqual(e[0]["text"], "Neu: fett wird schlicht <script>x</script>")   # text; the page escapes it
        self.assertEqual(e[2]["text"], "Alte Zeile ohne Version")

    def test_limits(self):
        long = "- **V01.0.1** · 2026-10-01 · " + "a" * 9000
        self.assertLessEqual(len(update.parse_changelog(long)[0]["text"]), update.CHANGELOG_MAX_TEXT)
        many = "\n".join(f"- 2026-10-01 · Zeile {i}" for i in range(update.CHANGELOG_MAX_ENTRIES + 50))
        self.assertEqual(len(update.parse_changelog(many)), update.CHANGELOG_MAX_ENTRIES)
        self.assertEqual(update.parse_changelog(None), [])

    def test_real_changelog_parses(self):
        path = os.path.join(ROOT, "CHANGELOG.md")
        if not os.path.exists(path):     # the self-test on the Spark runs on a copy of app/ only
            self.skipTest("no repository around app/")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        e = update.parse_changelog(text)
        self.assertGreater(len(e), 100)
        self.assertTrue(e[0]["version"], "CHANGELOG.md: the newest line carries a version")

    def test_install_copies_it(self):
        path = os.path.join(ROOT, "install.sh")
        if not os.path.exists(path):
            self.skipTest("no repository around app/")
        with open(path) as f:
            self.assertIn('cp -- "$INSTALL_FROM/CHANGELOG.md" "$PREFIX/app.new/CHANGELOG.md"', f.read())


class Files(unittest.TestCase):
    def setUp(self):
        self.real = update.CHANGELOG_FILES
        self.dir = tempfile.mkdtemp()
        update._cl_cache.update(key=None, entries=[])

    def tearDown(self):
        update.CHANGELOG_FILES = self.real
        update._cl_cache.update(key=None, entries=[])

    def test_first_file_wins_and_missing_is_empty(self):
        a, b = os.path.join(self.dir, "a.md"), os.path.join(self.dir, "b.md")
        with open(b, "w") as f:
            f.write(SAMPLE)
        update.CHANGELOG_FILES = (a, b)
        self.assertEqual(len(update.changelog()), 3)
        update.CHANGELOG_FILES = (a,)
        self.assertEqual(update.changelog(), [])

    def test_link_not_followed(self):
        real, link = os.path.join(self.dir, "secret.md"), os.path.join(self.dir, "CHANGELOG.md")
        with open(real, "w") as f:
            f.write(SAMPLE)
        os.symlink(real, link)
        update.CHANGELOG_FILES = (link,)
        self.assertEqual(update.changelog(), [])

    def test_size_capped(self):
        p = os.path.join(self.dir, "big.md")
        line = "- 2026-10-01 · " + "x" * 500 + "\n"
        with open(p, "w") as f:
            f.write(line * (update.CHANGELOG_MAX_BYTES // len(line) + 100))
        update.CHANGELOG_FILES = (p,)
        self.assertLessEqual(len(update.changelog()), update.CHANGELOG_MAX_BYTES // len(line) + 1)


class Api(unittest.TestCase):
    def setUp(self):
        self.real = update.CHANGELOG_FILES
        d = tempfile.mkdtemp()
        p = os.path.join(d, "CHANGELOG.md")
        with open(p, "w") as f:
            f.write(SAMPLE)
        update.CHANGELOG_FILES = (p,)
        update._cl_cache.update(key=None, entries=[])
        with guard._rate_lock:
            guard._rate.clear()

    def tearDown(self):
        update.CHANGELOG_FILES = self.real
        update._cl_cache.update(key=None, entries=[])
        with guard._rate_lock:
            guard._rate.clear()

    def test_admin_and_profile(self):
        r = ADMIN.get("/api/changelog")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["entries"][0]["version"], "V01.0.12")
        self.assertTrue(r.json()["version"])
        self.assertIn("no-store", r.headers.get("cache-control", ""))
        self.assertEqual(profile("Clara").get("/api/changelog").status_code, 200)

    def test_guest_refused(self):
        self.assertIn(TestClient(panel.app).get("/api/changelog").status_code, (401, 403))

    def test_rate_limited(self):
        c = profile("Clara")
        codes = [c.get("/api/changelog").status_code for _ in range(guard.RATE["changelog"][1] + 1)]
        self.assertEqual(codes[-1], 429)
        self.assertEqual(set(codes[:-1]), {200})


class Page(unittest.TestCase):
    def test_wired_without_inline_code(self):
        st = os.path.join(os.path.dirname(update.__file__), "static")
        with open(os.path.join(st, "index.html")) as f:
            html = f.read()
        with open(os.path.join(st, "js", "changelog.js")) as f:
            js = f.read()
        self.assertIn('/static/js/changelog.js', html)
        self.assertIn('data-on="clOpen"', html)                 # bottom line and Einstellungen → Update
        self.assertEqual(html.count('data-on="clOpen"'), 2)
        self.assertNotIn("onclick=", html.split('id="clmodal"')[1].split("</div></div>")[0])
        self.assertIn("esc(e.text)", js)                         # file text never as HTML
        self.assertNotIn("api('/api/changelog'", js)             # a guest gets a hint, not the admin login


if __name__ == "__main__":
    unittest.main()
