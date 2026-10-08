"""Security scanner: runs with every update's self-test and fails when new code brings back a pattern
the reviews removed. Reads only files inside app/ (the self-test runs on a copy of app/).

- no shell=True, eval, exec, os.system, pickle or yaml.load in the Python code
- every panel route has a login check, or is on OPEN with the reason why it needs none
- an uploaded file is never read without a size (UploadFile.read() needs a limit)
- values in inline handlers of the page (onclick="...${x}...") are escaped for JavaScript (escq)
- every tool the assistant can call is sorted: reads outside text, reads Home Assistant, changes
  something, mail, or only reads the person's own data
"""
import glob
import os
import re
import unittest

from tests import helpers  # noqa: F401  (paths of a test install before chat is imported)

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(APP, "panel")


def sources(*dirs):
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.py"))):
            with open(p, encoding="utf-8") as f:
                yield os.path.relpath(p, APP), f.read()


def code_lines(text):
    """Lines without comments and docstring-like plain text (good enough for these patterns)."""
    for n, line in enumerate(text.splitlines(), 1):
        yield n, line.split("#", 1)[0]


# routes that need no login, and why
OPEN = {
    "/api/whoami": "says who is logged in (nothing private without a login)",
    "/api/login": "the admin's way in (lockout in guard.py)",
    "/api/logout": "ends a login",
    "/api/profile/login": "a profile's way in (lockout in guard.py)",
    "/api/profile/logout": "ends a login",
    "/api/siri/ask": "checks the profile itself (device key or login), 401 otherwise",
    "/api/tasks/inbox": "checks the profile itself (device key), 401 otherwise",
    "/api/esp32/ota/": "the speaker's first contact; only while the admin switched it on, codes are one-time",
    "/api/esp32/ota/activate": "the speaker's first contact; only with a pending one-time code",
    "/api/esp32/fw/{version}/{name}": "public firmware files",
    "/": "the page itself",
    "/static/{name}": "page files",
    "/static/js/{name}": "page files",
    "/manifest.webmanifest": "page files",
    "/apple-touch-icon.png": "page files",
    "/favicon.ico": "page files",
    "/pebble/speech-spark.pbw": "the watch app",
    "/sw.js": "the page's service worker",
}
LOGIN = re.compile(r"Depends\((auth|assistant|own_profile|browser_profile|secret_profile|_on)\)")
ROUTE = re.compile(r'@(?:router|app)\.(?:get|post|put|delete|patch|api_route)\("([^"]*)"[^\n]*\n((?:@[^\n]*\n)*)'
                   r'(?:async )?def \w+\((.*?)\):\n', re.S)


class Scanner(unittest.TestCase):
    def test_no_dangerous_calls(self):
        bad = re.compile(r"shell\s*=\s*True|\beval\(|\bexec\(|os\.system\(|os\.popen\(|pickle\.loads?\(|"
                         r"yaml\.load\(|__import__\(")
        found = [f"{p}:{n}" for p, text in sources(APP, PANEL) for n, line in code_lines(text) if bad.search(line)]
        self.assertEqual(found, [])

    def test_every_route_has_a_login(self):
        found = []
        for p, text in sources(PANEL):
            for m in ROUTE.finditer(text):
                path, more, sig = m.group(1), m.group(2), m.group(3)
                head = text[m.start():m.end()]
                if LOGIN.search(head) or path in OPEN:
                    continue
                found.append(f"{p}: {path}")
        self.assertEqual(found, [], "routes without a login check (add one, or add them to OPEN with a reason)")

    def test_uploads_read_with_a_limit(self):
        found = []
        for p, text in sources(APP, PANEL):
            names = set(re.findall(r"(\w+): UploadFile", text))
            for n, line in code_lines(text):
                for name in names:
                    if re.search(rf"\b{name}\.read\(\)", line):
                        found.append(f"{p}:{n}")
        self.assertEqual(found, [])

    def test_inline_handlers_escaped(self):
        found = []
        for p in sorted(glob.glob(os.path.join(PANEL, "static", "js", "*.js"))):
            with open(p, encoding="utf-8") as f:
                text = f.read()
            for attr in re.findall(r'\son[a-z]+="[^"]*\$\{[^"]*"', text):
                found += [f"{os.path.basename(p)}: {v}" for v in re.findall(r"\$\{([^}]*)\}", attr)
                          if not v.startswith("escq(")]
        self.assertEqual(found, [])

    def test_every_tool_is_sorted(self):
        with open(os.path.join(PANEL, "chat.py"), encoding="utf-8") as f:
            text = f.read()
        import chat
        known = chat.READS_OUTSIDE | chat.HA_READS | chat.LOCKED_OUTSIDE | chat.INSIDE
        tools = set(re.findall(r'"name": "([a-z_]+)"', text))
        self.assertEqual({t for t in tools if t not in known and not t.startswith("mail_")}, set(),
                         "a new tool in chat.py: put it into READS_OUTSIDE, HA_READS, LOCKED_OUTSIDE or INSIDE")
        import extras
        for m in extras.SERVICES:
            with open(m.__file__, encoding="utf-8") as f:
                src = f.read()
            names = set(re.findall(r'"name": "([a-z_]+)"', src))
            sets = set()
            for body in re.findall(r'\{("[a-z_]+"(?:,\s*"[a-z_]+")*)\}', src):
                sets |= set(re.findall(r'"([a-z_]+)"', body))
            missing = names - sets - set(getattr(m, "INSIDE", set()))
            self.assertEqual(missing, set(), f"{m.__name__}: say in offer() whether the tool reads outside text, "
                                             "mail or changes something, or put it into INSIDE")


if __name__ == "__main__":
    unittest.main()
