"""Security scanner: runs with every update's self-test and fails when new code brings back a pattern
the reviews removed. Reads only files inside app/ (the self-test runs on a copy of app/).

- no shell=True, eval, exec, os.system, pickle or yaml.load in the Python code
- every panel route has a login check, or is on OPEN with the reason why it needs none
- an uploaded file is never read without a size (UploadFile.read() needs a limit)
- strict CSP (V01.0.286): no inline handler (onclick="..."), no inline <script>, no javascript: link, no eval or
  new Function in the page's scripts; buttons name their function with data-on (base.js ON)
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
    "/live": "the monitor page: static, 404 while off, home network only (live.py)",
    "/api/live/pair": "a screen enters its one-time code (home network, lockout and rate limit in live.py)",
    "/api/live/state": "checks the monitor's own cookie itself, 401 otherwise, home network only (live.py)",
    "/api/schirm/zustand": "the HDMI screen on the same computer: loopback only without a forwarded sender, its own key, 404 while off (schirm.py)",
    "/api/login": "the admin's way in (lockout in guard.py)",
    "/api/logout": "ends a login",
    "/api/profile/login": "a profile's way in (lockout in guard.py)",
    "/api/profile/logout": "ends a login",
    "/api/siri/ask": "checks the profile itself (device key or login), 401 otherwise",
    "/api/tasks/inbox": "checks the profile itself (device key), 401 otherwise",
    "/api/esp32/ota/": "the speaker's first contact; only while the admin switched it on, codes are one-time",
    "/api/esp32/ota/activate": "the speaker's first contact; only with a pending one-time code",
    "/api/esp32/fw/{version}/{name}": "public firmware files",
    "/api/iphone/pair": "the iPhone app's first contact; only with a one-time code from the profile's own login",
    "/api/confirm/end": "ends only the confirmation window of the logins this request carries",
    "/api/pebble/pair": "the Pebble phone app's first contact; only with a one-time code from the profile's own login",
    "/api/write/pair": "a writing help program's first contact; only with a one-time code from the profile's own login",
    "/api/desk/pair": "the Spark-Begleiter's first contact; only with a one-time code from the profile's own login",
    "/api/tui/pair": "the terminal client's first contact; only with a one-time code from the profile's own login",
    "/office/{name}": "the Office add-in's task pane files: static, no data, 404 while the admin has it off",
    "/api/esp32/ping": "\"Netz prüfen\": a random marker of this Spark, nothing else; only while the admin switched speakers on",
    "/": "the page itself",
    "/.well-known/caldav": "only a redirect to /caldav/ for calendar apps, 404 while the admin has the calendar server off (kalenderserver.py)",
    "/.well-known/carddav": "only a redirect to /carddav/ for contacts apps, 404 while the admin has the contacts server off (kontaktserver.py)",
    "/carddav": "contacts apps log in like calendar apps (kalenderserver.login: app password, lockout, rate limit, own path only), 404 while off",
    "/caldav": "calendar apps log in with HTTP Basic and the profile's app password (kalenderserver.login: lockout, rate limit, own path only), 404 while off",
    "/static/{name}": "page files",
    "/static/js/{name}": "page files",
    "/manifest.webmanifest": "page files",
    "/apple-touch-icon.png": "page files",
    "/favicon.ico": "page files",
    "/pebble/speech-spark.pbw": "the watch app",
    "/pebble/spark-zifferblatt.pbw": "the Spark watchface (Paket 2), a public app file like the watch app",
    "/tui/spark-tui.py": "the terminal client program; no data, its SHA-256 is shown under Ich → Terminal",
    "/android/spark.apk": "the Android app file; only with a download link (one-time token, 30 minutes) from a profile's own login",
    "/sw.js": "the page's service worker",
    "/api/join/check": "an invited person's first contact; 404 unless the admin allows invitations, one-time codes, lockout",
    "/api/join": "an invited person's first contact; 404 unless the admin allows invitations, one-time codes, lockout",
    "/api/iphone/join": "the iPhone app with an invitation; 404 unless the admin allows invitations, one-time codes, lockout",
    "/api/handoff/claim": "a phone scanned the computer's code; 404 unless the admin allows it, two minutes, once, lockout",
    "/api/handoff/finish": "the phone signs in only after its number was picked on the computer; 404 unless allowed",
    "/api/mymcp/back": "an own MCP service's sign-in comes back: changes nothing, only hands state and code to the signed-in page; 404 while off",
    "/mcp": "the MCP endpoint checks the connection's own token itself (mcpserver.check_conn), 404 while switched off",
    "/oauth/register": "OAuth programs say who they are; opens nothing, the person decides in the panel; 404 unless allowed",
    "/oauth/authorize": "checks the program and hands over to the signed-in panel page; 404 unless allowed",
    "/oauth/token": "trades a one-time code (PKCE) or refresh token for a token; 404 unless allowed",
    "/.well-known/oauth-authorization-server": "public OAuth addresses, no data; 404 unless allowed",
    "/.well-known/oauth-protected-resource": "public OAuth addresses, no data; 404 unless allowed",
    "/.well-known/oauth-protected-resource/mcp": "public OAuth addresses, no data; 404 unless allowed",
    "/.well-known/apple-app-site-association": "Apple asks which app may use this host's passkeys: only the app's public ID; 404 unless the iPhone app is on",
    "/api/notaus": "the kill switch: strangers see only the stage; triggering checks the caller itself (notaus._caller), only up, rate limit",
    "/api/admin/notaus/off": "lifting checks the admin itself (notaus._lift_how): browser at home, fresh code or password, rate limit",
    "/api/notaus/mine": "Mein Notaus: checks the profile itself (notaus._caller), only on, rate limit",
    "/api/notaus/mine/off": "Mein Notaus off: the profile's browser login only, PIN with lockout and its fresh code, rate limit",
    "/api/notaus/ha": "Home Assistant raises the Notaus with its own key (notaus.key_find, hash, compare_digest), home network only, lockout, rate limit",
    "/api/admin/notaus/mine/off": "an admin lifts a profile's own Notaus: notaus._lift_how (browser at home), fresh code or password",
    "/api/liste/check": "Mitschreib-Link: a visitor without a profile; 404 unless the admin allows it, random code (only its hash kept), expiry, revoke, Origin check, rate limit, lockout like a PIN (mitschreiblink._door)",
    "/api/liste/add": "Mitschreib-Link: only puts entries on the one list of the link; 404 unless allowed, same door as /api/liste/check, Mein Notaus of the owner holds it",
    "/api/make/dl": "a made document for whoever holds its download link (random token, only its hash kept, 10 minutes, 5 uses, one file of one profile); 404 once off, rate limit",
    "/api/changelog": "Was ist neu: is_admin, else browser_profile (no guests, no device keys), rate limit; read only",
}
LOGIN = re.compile(r"Depends\((auth|main_auth|own_profile|browser_profile|secret_profile|secret_profile_fresh)\)")
# assistant is open while chat.public is on, a module's _on mostly only checks a switch (code check 19.10. C6): a route
# with only these binds the caller itself, by a parameter (prof=Depends(_on)) or a known call in its body, or stands
# in WEAK_OK with a reason
WEAK = re.compile(r"Depends\((assistant|_on)\)")
BOUND_PARAM = re.compile(r"\b\w+\s*=\s*Depends\([\w.]+\)")
BOUND_CALL = re.compile(r"\b(profiles\.current|own_profile|browser_profile|_program|writer|_prof|_watch_prof|_watch_job|"
                        r"caller)\(")
WEAK_OK = {
    "/api/stufen": "the fixed list of when the Spark asks for a code (stufen.overview), no profile data, rate limit",
}
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
                if path in OPEN:
                    continue
                if LOGIN.search(head):
                    continue
                if WEAK.search(head):
                    nxt = re.search(r"\n(@|def |async def |class )", text[m.end():])
                    body = text[m.end():m.end() + (nxt.start() if nxt else len(text))]
                    if BOUND_PARAM.search(sig) or BOUND_CALL.search(body) or path in WEAK_OK:
                        continue
                    found.append(f"{p}: {path} (only assistant/_on, binds no profile)")
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

    def test_no_inline_script_for_the_strict_csp(self):
        found = []
        files = sorted(glob.glob(os.path.join(PANEL, "static", "js", "*.js"))) + [os.path.join(PANEL, "static", "index.html")]
        for p in files:
            if p.endswith("esptool.js"):   # Espressif's bundle, unchanged (checked once: no eval, no Function)
                continue
            with open(p, encoding="utf-8") as f:
                text = f.read()
            name = os.path.basename(p)
            found += [f"{name}: {m}" for m in re.findall(r"<[a-z][^<>]*\son[a-z]+\s*=", text)]
            found += [f"{name}: javascript:" for _ in re.findall(r"(?i)javascript:", text)]
            found += [f"{name}: eval" for _ in re.findall(r"\beval\(|\bnew Function\(|setTimeout\(\s*['\"`]", text)]
            if name == "index.html":
                found += [f"{name}: inline <script>" for _ in re.findall(r"<script(?![^>]*\ssrc=)[^>]*>", text)]
        self.assertEqual(found, [])

    def test_csp_is_strict(self):
        import panel
        csp = panel.SECURITY_HEADERS["Content-Security-Policy"]
        self.assertIn("script-src 'self';", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertEqual(csp.count("unsafe-inline"), 1)        # only for styles
        self.assertIn("style-src 'self' 'unsafe-inline'", csp)

    def test_every_tool_is_sorted(self):
        text = ""
        for name in ("chat.py", "chat_modell.py", "chat_ton.py"):   # model side and speech output have their own files
            with open(os.path.join(PANEL, name), encoding="utf-8") as f:
                text += f.read()
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
            # only sets given as "outside"/"mail"/"changes" (or INSIDE, READS..., LOCKED...): a name that is merely
            # in some other set literal (fillers, word lists) is not sorted (review 11.10.2026)
            sets = set()
            for m2 in re.finditer(r'(?i)(outside|mail|changes|inside|reads|locked)\w*"?\s*(?::|\|=|=|\|)\s*'
                                  r'(?:\w+\s*\|\s*)?\{("[a-z_]+"(?:,\s*"[a-z_]+")*)\}', src):
                sets |= set(re.findall(r'"([a-z_]+)"', m2.group(2)))
            missing = names - sets - set(getattr(m, "INSIDE", set()))
            self.assertEqual(missing, set(), f"{m.__name__}: say in offer() whether the tool reads outside text, "
                                             "mail or changes something, or put it into INSIDE")


if __name__ == "__main__":
    unittest.main()
