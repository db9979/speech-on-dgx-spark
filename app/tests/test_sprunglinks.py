"""Sprung-Links (Dominik 12.10.2026: „bei solchen Meldungen immer direkt Link anbieten“): every hint that names a
place in the panel ("unter Einstellungen → Spark → Betrieb → Logs „Live-Seite“") is a link to that place
(static/js/way.js). The rule stays: this test collects every such way from the panel's texts (scripts, page,
server messages) and checks in a real browser that each step of it is found on the page, so a new hint links
itself and a hint whose place was renamed or moved turns this test red instead of leaving a dead way."""
import ast
import asyncio
import glob
import json
import os
import re
import unittest
from unittest import mock

from tests import helpers
from tests.test_ui_browser import PAGE_READY, async_playwright, browser_ok, chromium

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(APP, "panel")
DE_ROOTS = ("Personen und Geräte", "Einstellungen", "Funktionen", "Zustand", "Ich")
EN_ROOTS = ("People and devices", "Settings", "Features", "Status", "Me")
HINT = re.compile(r"(?<![\w-])(?<!Mein )(?<!My )(?<!→ )(" + "|".join(DE_ROOTS + EN_ROOTS) + r")\s*→")
# a way that starts like ours but means another program (the iPhone's or Open WebUI's settings, …): text that
# names it right before the way. Everything else that starts with one of the names above must be found.
NAMES = (r"iPhone|iOS|iPad|Android|Windows|Mac|macOS|Outlook|Word|Excel|Open WebUI|WebUI|Pebble|Home Assistant|"
         r"Telegram|Kiwix|SearXNG|reMarkable-App|Chrome|Safari|Firefox|App Store|TestFlight|Xcode|Apple|Google|Gmail|"
         r"GitHub|Action-Button|Systemeinstellungen|System Settings|Begleiter|Companion|Wear OS|Siri|Kurzbefehle|Shortcuts|E-Mail-Einstellungen")
OTHER = re.compile(r"(" + NAMES + r")[\w\s()\-:,]{0,20}$")
# Ways whose place is not on the panel page on purpose (said elsewhere or only once a person is chosen)
KNOWN = {}


def _sources():
    """(file, text) of everything the panel or the assistant can show: the scripts, the page and the server's
    Python files, without code comments."""
    out = []
    for p in sorted(glob.glob(os.path.join(PANEL, "static", "js", "*.js"))):
        if os.path.basename(p) == "way.js":
            continue
        out.append((p, re.sub(r"(?m)(^|\s)//.*$", r"\1", open(p, encoding="utf-8").read())))
    out.append((os.path.join(PANEL, "static", "index.html"), open(os.path.join(PANEL, "static", "index.html"), encoding="utf-8").read()))
    for p in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
        out.append((p, "\n".join(_py_strings(open(p, encoding="utf-8").read()))))
    return out + _app_sources()


# the apps, the Begleiter and the Pebble app link their ways too (…/#weg=, Dominik 12.10.2026 „überall“); not in a
# copy with only app/
ROOT = os.path.dirname(APP)
APP_GLOBS = ("ios/**/*.swift", "android/**/*.kt", "tools/begleiter/mac/**/*.swift", "tools/begleiter/windows/**/*.cs",
             "pebble/src/pkjs/*.js")


def _app_sources():
    out = []
    for g in APP_GLOBS:
        for p in sorted(glob.glob(os.path.join(ROOT, g), recursive=True)):
            text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), open(p, encoding="utf-8").read(), flags=re.S)
            out.append((p, re.sub(r"(?m)(^|\s)//.*$", r"\1", text)))
    return out


# in an app "Einstellungen → …" is the device's own settings; the panel's only with "Panel" right before it
DEVICE = re.compile(r"(?<!Panel unter )(?<!Panel: )(?<!panel under )(?<!panel: )(?<![\w-])(Einstellungen|Settings)\s*→")


def _py_strings(src):
    """The strings of a Python file that can reach a person (not docstrings): f-strings with {} in their gaps."""
    tree, docs, out = ast.parse(src), set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            docs.add(id(n.value))
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values))
            docs.update(id(v) for v in n.values)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            out.append(n.value)
    return out


def hints():
    """{way text: [where]} for every way in the sources, cut where its string ends."""
    found = {}
    for path, text in _sources():
        for m in HINT.finditer(text):
            if OTHER.search(text[max(0, m.start() - 60):m.start()]):
                continue
            if not path.startswith(PANEL) and DEVICE.match(text, m.start()):
                continue
            s = text[m.start():m.start() + 220]
            cut = r"\n|\{" if path.endswith(".py") else r"(?<!\\)['`\"]|\\n|\n|<|\$\{|\\\(|\{"
            s = re.split(cut, s)[0].replace("\\'", "'")
            line = text.count("\n", 0, m.start()) + 1
            found.setdefault(s, []).append(f"{os.path.relpath(path, APP)}:{line}")
    return found


def alert_ways():
    """{go: [file]} of every note for the top of the admin pages (dicts with kind, level and text, health.alerts):
    each must say with "go" where to look or act; [file] of those without."""
    ways, missing = {}, []
    for p in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
        for n in ast.walk(ast.parse(open(p, encoding="utf-8").read())):
            if not isinstance(n, ast.Dict):
                continue
            keys = {k.value: v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant)}
            if not {"kind", "level", "text"} <= set(keys):
                continue
            go = keys.get("go")
            both = [go.body, go.orelse] if isinstance(go, ast.IfExp) else [go]   # one way or the other
            if all(isinstance(g, ast.Constant) for g in both):
                for g in both:
                    ways.setdefault(g.value, []).append(f"{os.path.basename(p)}:{n.lineno}")
            else:
                missing.append(f"{os.path.basename(p)}:{n.lineno}")
    return ways, missing


class Static(unittest.TestCase):
    def test_finds_the_ways(self):
        h = hints()
        self.assertGreater(len(h), 40)
        self.assertTrue(any(s.startswith("Einstellungen → Spark → Betrieb → Logs „Live-Seite“") for s in h), h.keys())

    def test_ways_start_with_a_menu_name(self):
        """„unter Sprachausgabe → …“ cannot be found (and was an old name): a way after „unter“/„under“ starts with
        Einstellungen, Funktionen, Zustand, Personen und Geräte or Ich, or it names another program."""
        rx = re.compile(r"\b(?:[Uu]nter|[Uu]nder) ([A-ZÄÖÜ][^\s→'\"`<.:]*(?: [^\s→'\"`<.:]+){0,3}?) →")
        bad = []
        for path, text in _sources():
            for m in rx.finditer(text):
                if m.group(1) in DE_ROOTS + EN_ROOTS or re.search(NAMES, m.group(1)):
                    continue
                bad.append(f"{os.path.relpath(path, APP)}: {m.group(0)}")
        self.assertEqual(bad, [])

    def test_every_alert_names_its_place(self):
        """Dominik 12.10.2026 („Antworten sind langsamer geworden …“ without a way): every note on top of the admin
        pages carries a fixed way to the place it is about; the button under it jumps there."""
        ways, missing = alert_ways()
        self.assertEqual(missing, [])
        self.assertGreaterEqual(len(ways), 6)
        self.assertIn("Zustand → Logs → Anfragen", ways)
        js = open(os.path.join(PANEL, "static", "js", "admin.js"), encoding="utf-8").read()
        self.assertIn("b.onclick=()=>wayGo(x.go)", js)

    def test_way_js_is_loaded_and_only_moves(self):
        html = open(os.path.join(PANEL, "static", "index.html"), encoding="utf-8").read()
        self.assertIn('<script src="/static/js/way.js"></script>', html)
        js = open(os.path.join(PANEL, "static", "js", "way.js"), encoding="utf-8").read()
        # a link only opens a place: no request, no saving, no HTML from the text
        for bad in ("api(", "fetch(", "innerHTML", "localStorage", "eval(", "PUT", "POST"):
            self.assertNotIn(bad, js, bad)


class Outside(unittest.TestCase):
    """Outside the panel a way opens <panel>/#weg=<way> (wege.py): Telegram, push notes, the apps."""

    def test_find_takes_the_first_way_up_to_the_end_of_the_clause(self):
        import wege
        self.assertEqual(wege.find("Ansehen und bestätigen unter Ich → Gedächtnis."), "Ich → Gedächtnis")
        self.assertEqual(wege.find("Erlauben: Ich → Telegram → Fotos über Telegram und mehr"), "Ich → Telegram → Fotos über Telegram und mehr")
        self.assertEqual(wege.find("Probleme melden ist aus (Admin: Funktionen → „Probleme melden“)"), "Funktionen → „Probleme melden“")
        for none in ("Mein Notaus ist an.", "In Open WebUI → Einstellungen → Verbindungen", "", None, "Ich bin da → gleich"):
            self.assertEqual(wege.find(none), "", none)
        self.assertLessEqual(len(wege.find("Ich → " + "x" * 500)), wege.MAX)

    def test_link_only_with_a_plain_address(self):
        import wege
        self.assertEqual(wege.link("https://spark.example.de/", "Ich → Sicherheit"),
                         "https://spark.example.de/#weg=Ich%20%E2%86%92%20Sicherheit")
        for bad in ("javascript:alert(1)", "https://a@b.de", "https://b.de/x", "https://b.de/#x", "", None, "ftp://b.de"):
            self.assertEqual(wege.link(bad, "Ich → Sicherheit"), "", bad)
        self.assertEqual(wege.link("https://b.de", ""), "")

    def test_telegram_button_only_with_the_panel_address(self):
        import telegram
        with mock.patch.object(telegram, "load_config", return_value={"chat": {}}):
            self.assertIsNone(telegram.way_button("Neu verbinden unter Ich → Telegram."))
        with mock.patch.object(telegram, "load_config", return_value={"chat": {"telegram_panel_url": "https://s.example.de"}}):
            self.assertIsNone(telegram.way_button("Hallo, wie geht's?"))
            b = telegram.way_button("Neu verbinden unter Ich → Telegram.")
            self.assertEqual(b, {"inline_keyboard": [[{"text": "Im Panel öffnen",
                                                       "url": "https://s.example.de/#weg=Ich%20%E2%86%92%20Telegram"}]]})
            self.assertEqual(telegram.way_button("Reconnect under Me → Telegram.")["inline_keyboard"][0][0]["text"], "Open in the panel")

    def test_telegram_sends_without_the_button_when_refused(self):
        """A button Telegram refuses (an address it does not take) never costs the message itself."""
        import telegram
        sent = []

        class R:
            def __init__(self, ok):
                self.ok, self.status_code = ok, 200 if ok else 400

            def json(self):
                return {"ok": True, "result": {}} if self.ok else {"ok": False, "description": "Bad Request: wrong HTTP URL"}

        class C:
            async def post(self, url, json):
                sent.append(json)
                return R("reply_markup" not in json)

        with mock.patch.object(telegram, "load_config", return_value={"chat": {"telegram_panel_url": "https://s.example.de"}}), \
                mock.patch.object(telegram, "token", return_value="1:x"):
            asyncio.run(telegram.call(C(), "sendMessage", chat_id=1, text="Unter Ich → Telegram."))
        self.assertEqual(len(sent), 2)
        self.assertIn("reply_markup", sent[0])
        self.assertNotIn("reply_markup", sent[1])

    def test_push_note_carries_the_way_and_the_page_opens_it(self):
        src = open(os.path.join(PANEL, "push.py"), encoding="utf-8").read()
        self.assertIn('"weg": wege.find(body)', src)
        sw = open(os.path.join(PANEL, "static", "sw.js"), encoding="utf-8").read()
        self.assertIn("'/#weg=' + encodeURIComponent(weg)", sw)
        self.assertIn("postMessage({weg})", sw)
        way = open(os.path.join(PANEL, "static", "js", "way.js"), encoding="utf-8").read()
        self.assertIn("addEventListener('hashchange'", way)
        self.assertIn("navigator.serviceWorker.addEventListener('message'", way)

    def test_apps_use_the_same_rule(self):
        """The Android app finds ways with the same roots as wege.py (the iPhone app and the Begleiter: see below)."""
        import wege
        kt = os.path.join(ROOT, "android", "app", "src", "main", "java", "io", "github", "db9979", "spark", "Wege.kt")
        if not os.path.exists(kt):
            self.skipTest("only app/ here")
        src = open(kt, encoding="utf-8").read()
        roots = re.search(r'ROOTS = "([^"]+)"', src).group(1).split("|")
        self.assertEqual(sorted(roots), sorted(wege.ROOTS))
        self.assertIn("[^\\\\n.;:()!?]{1,160}", src)
        poll = open(os.path.join(os.path.dirname(kt), "NotePoll.kt"), encoding="utf-8").read()
        self.assertIn("Wege.link(base, body)", poll)
        # the iPhone app, the Mac and the Windows Begleiter: the same roots and the same end of a way
        for path, rx in (("ios/Spark/PanelAPI.swift", r'wayRoots = "([^"]+)"'), ("tools/begleiter/mac/Sources/Wege.swift", r'roots = "([^"]+)"'),
                         ("tools/begleiter/windows/Wege.cs", r'Roots = "([^"]+)"')):
            src = open(os.path.join(ROOT, path), encoding="utf-8").read()
            self.assertEqual(sorted(re.search(rx, src).group(1).split("|")), sorted(wege.ROOTS), path)
            self.assertIn("{1,160}", src, path)
            self.assertIn("#weg=", src, path)

    def test_app_texts_with_a_way_are_links(self):
        """A text the iPhone app or the Mac Begleiter shows with a way goes through the link helper (SparkAPI.way,
        Wege.text), never as plain Text; the widget only opens the app (no links in widgets)."""
        if not os.path.isdir(os.path.join(ROOT, "ios")):
            self.skipTest("only app/ here")
        plain = re.compile(r'Text\((?:verbatim: )?"([^"]*)"\)')
        bad = []
        for g in ("ios/Spark/*.swift", "tools/begleiter/mac/Sources/*.swift"):
            for p in sorted(glob.glob(os.path.join(ROOT, g))):
                for n, line in enumerate(open(p, encoding="utf-8"), 1):
                    for m in plain.finditer(line):
                        t = m.group(1)
                        if HINT.search(t) and not DEVICE.match(t, HINT.search(t).start()) and not OTHER.search(t[:HINT.search(t).start()][-60:]):
                            bad.append(f"{os.path.relpath(p, ROOT)}:{n}")
        self.assertEqual(bad, [])
        ios = "".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(ROOT, "ios/Spark/*.swift")))
        self.assertGreaterEqual(ios.count("SparkAPI.way("), 20)
        win = open(os.path.join(ROOT, "tools/begleiter/windows/UiControls.cs"), encoding="utf-8").read()
        self.assertIn("Wege.OpenFrom(Text)", win)
        tray = open(os.path.join(ROOT, "tools/begleiter/windows/TrayContext.cs"), encoding="utf-8").read()
        self.assertIn("_balloonAction = Wege.Hash(text)", tray)


# Zahlen mit Ziel (Dominik 14.10.2026: „sollte klickbar sein und direkt hinbringen sonst sucht man sich den Wolf“):
# cards under Zustand → Monitoring whose rows need no way of their own (they carry their own buttons, or there are none)
ROWS_OWN = {"zneed": "jede Zeile hat ihren Knopf zum Ort",
            "zroom": "jede Zeile hat Beenden, die Karte zeigt nur wo und bis wann",
            "znotaus": "zeigt den Notaus selbst, seine Knöpfe stehen auf der Karte",
            "znmine": "jede Zeile hat Aufheben",
            "zhead": "Überschrift ohne Zeilen; ein Weg in ihrem Satz wird von selbst ein Sprung-Link"}


def count_ways():
    """{(de, en)}: the ways that counts and rows open (way.js WAY_CARDS, data-way, wayA)."""
    pair = re.compile(r"""(?:\[|t\()'([^']*→[^']*)','([^']*→[^']*)'""")
    out = set()
    for f in glob.glob(os.path.join(PANEL, "static", "js", "*.js")):
        src = open(f, encoding="utf-8").read()
        block = re.search(r"const WAY_CARDS=\{(.*?)\};", src, re.S)
        if block:
            out |= set(pair.findall(block.group(1)))
        for line in src.splitlines():
            if "data-way=" in line or "wayA(" in line:
                out |= set(pair.findall(line))
    return out


class Counts(unittest.TestCase):
    def test_the_count_ways_are_collected(self):
        ways = count_ways()
        self.assertIn(("Zustand → Logs → Anfragen", "Status → Logs → Requests"), ways)
        self.assertIn(("Ich → Mein Zustand", "Me → My status"), ways)
        self.assertGreaterEqual(len(ways), 8)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        import panel
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Wegtest", "4711")
        except Exception:
            pass

    async def until(self, pg, expr, seconds=20):
        for _ in range(int(seconds * 10)):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    async def page(self, p, locale="de-DE", width=1280, profile=True):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": width, "height": 900}, locale=locale, bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        r = await pg.request.post(base + "/api/login", data={"password": "secret-admin"})
        self.assertEqual(r.status, 200)
        if profile:
            r = await pg.request.post(base + "/api/profile/login", data={"name": "Wegtest", "pin": "4711"})
            self.assertEqual(r.status, 200)
        await pg.goto(base + "/")
        await self.until(pg, PAGE_READY + "&&ADMIN===true" + ("&&!!PROFILE" if profile else ""))
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        if profile:   # Ich draws its rows when it opens
            await pg.evaluate("openMe('setbox')")
            await pg.wait_for_timeout(1500)
            await pg.evaluate("closeProf()")
        return br, pg, errors

    def test_every_way_is_found(self):
        """Each step of every way names a page, a part or a row the panel has (German and English texts)."""
        found = hints()

        async def go():
            bad = []
            async with async_playwright() as p:
                for locale, roots in (("de-DE", DE_ROOTS), ("en-US", EN_ROOTS)):
                    br, pg, errors = await self.page(p, locale)
                    for s in ("mon", "logs", "test", "prof", "apps", "who", "int", "cfg"):   # pages draw their parts on opening
                        await pg.evaluate(f"goSec('{s}')")
                        await pg.wait_for_timeout(400)
                    ways = [s for s in found if s.startswith(roots) and not (locale == "de-DE" and s.startswith(EN_ROOTS))]
                    res = await pg.evaluate("ws=>ws.map(w=>{const r=wayParse(w,0,true);return r?[r.steps,r.want,r.quoted]:null})", ways)
                    for w, r in zip(ways, res):
                        if w in KNOWN:
                            continue
                        first = HINT.sub("", w, count=1).lstrip().lstrip('„“"')
                        if not r and not re.match(r"[A-ZÄÖÜ0-9]", first):
                            continue   # „Ich → einschalten“: what to do, no place
                        if not r:   # the first step names no page or part the viewer has
                            bad.append(f"{w!r} ({', '.join(found[w][:3])}): {r}")
                    self.assertEqual(errors, [])
                    await br.close()
            return bad

        bad = asyncio.run(go())
        self.assertEqual(bad, [], "Wege ohne Ziel:\n" + "\n".join(bad))

    def test_alert_ways_lead_somewhere(self):
        """Every way of a note on top finds each of its steps, and the note's button opens it (slow answers:
        Zustand → Logs → Anfragen)."""
        ways, _ = alert_ways()

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, profile=False)
                for s in ("mon", "logs", "test"):
                    await pg.evaluate(f"goSec('{s}')")
                    await pg.wait_for_timeout(400)
                # the recording of requests on: its tab exists (without it the way goes to the switch for it)
                await pg.evaluate("TRACE_ON=true;$('logreqtab').hidden=false")
                res = await pg.evaluate("ws=>ws.map(w=>{const r=wayParse(w,0);return r?[r.steps,r.want,r.end===w.length]:null})", list(ways))
                bad = [f"{w} ({ways[w][0]}): {r}" for w, r in zip(ways, res) if not r or r[0] < r[1] or not r[2]]
                self.assertEqual(bad, [])
                await pg.evaluate("goSec('chat')")
                await pg.evaluate("TRACE_ON=true;showAlerts([{kind:'latency',level:'warn',text:'Antworten sind langsamer geworden.',go:'Zustand → Logs → Anfragen'}])")
                await pg.evaluate("goSec('mon')")
                await pg.click("#alerts .gonote button")
                await self.until(pg, "LG.tab==='req'&&getComputedStyle($('logs')).display!=='none'")
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())

    def test_live_hint_links_to_its_switch(self):
        """Dominik's example: the Live page is off, its hint opens Einstellungen → Betrieb and marks „Live-Seite“."""
        # the page is off for this test, whatever an earlier test in the run left on (test_live switches it on)
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        was = c.setdefault("logs", {}).get("live", False)
        c["logs"]["live"] = False
        helpers.write_config(c)
        self.addCleanup(self._live_back, was)

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, profile=False)
                await pg.evaluate("goSec('live')")
                await self.until(pg, "!!document.querySelector('#live a.wayl')")
                text = await pg.evaluate("document.querySelector('#live a.wayl').textContent")
                self.assertEqual(text, "Einstellungen → Spark → Betrieb → Logs „Live-Seite“")
                await pg.click("#live a.wayl")
                await self.until(pg, "document.querySelector('#pane-sysc').classList.contains('on')")
                await self.until(pg, "!!document.querySelector('#pane-sysc .sflash')")
                flashed = await pg.evaluate("document.querySelector('#pane-sysc .sflash').textContent")
                self.assertIn("Live-Seite", flashed)
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())

    @staticmethod
    def _live_back(was):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c.setdefault("logs", {})["live"] = was
        helpers.write_config(c)

    def test_ich_hint_links_for_a_profile_only(self):
        """A way into Ich is a link for a signed-in profile and opens that page; admin ways are not links for a
        profile without admin rights, and nothing is a link inside a text field."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                await pg.evaluate("""(()=>{const d=document.createElement('div');d.id='waytest';
                  d.innerHTML='<p>Steht unter Ich → Sicherheit.</p><textarea>Ich → Sicherheit</textarea>';document.querySelector('main').appendChild(d)})()""")
                await self.until(pg, "!!document.querySelector('#waytest p a.wayl')")
                self.assertEqual(await pg.evaluate("document.querySelector('#waytest p a.wayl').textContent"), "Ich → Sicherheit")
                self.assertEqual(await pg.evaluate("document.querySelector('#waytest textarea').value"), "Ich → Sicherheit")
                await pg.click("#waytest p a.wayl")
                await self.until(pg, "$('profmodal').style.display==='grid'&&document.querySelector('#ptabs button.on').dataset.t==='secbox'")
                # without admin rights the admin pages are no way to go
                await pg.evaluate("closeProf();ADMIN=false")
                await pg.evaluate("""(()=>{const p=document.createElement('p');p.id='wayadm';p.textContent='Unter Einstellungen → Sicherheit.';document.querySelector('main').appendChild(p)})()""")
                await pg.wait_for_timeout(300)
                self.assertEqual(await pg.evaluate("document.querySelectorAll('#wayadm a').length"), 0)
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())

    def test_every_count_ways_whole(self):
        """Each way a count or row opens finds every one of its steps, in German and in English."""
        ways = sorted(count_ways())

        async def go():
            bad = []
            async with async_playwright() as p:
                for locale, k in (("de-DE", 0), ("en-US", 1)):
                    br, pg, errors = await self.page(p, locale)
                    for s in ("mon", "logs", "prof", "live", "cfg"):
                        await pg.evaluate(f"goSec('{s}')")
                        await pg.wait_for_timeout(300)
                    await pg.evaluate("TRACE_ON=true;$('logreqtab').hidden=false")
                    res = await pg.evaluate("ws=>ws.map(w=>{const r=wayParse(w,0,true);return r?[r.steps,r.want,r.end===w.length]:null})",
                                            [w[k] for w in ways])
                    bad += [f"{w[k]}: {r}" for w, r in zip(ways, res) if not r or r[0] < r[1] or not r[2]]
                    self.assertEqual(errors, [])
                    await br.close()
            return bad

        bad = asyncio.run(go())
        self.assertEqual(bad, [], "Zahlen mit Weg ohne Ziel:\n" + "\n".join(bad))

    def test_every_status_card_row_leads_somewhere(self):
        """A row in any card under Zustand → Monitoring opens its place (a new card without a way turns this red),
        the counts of „Mein Zustand aller Profile“ and „Heute“ are links, and a click on one jumps there."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                await pg.evaluate("goSec('mon')")
                await pg.wait_for_timeout(400)
                # a plain row in every card: it takes the card's way
                cards = await pg.evaluate("""[...document.querySelectorAll('#mon .card[id]')].filter(c=>c.id!=='ztech'&&!c.closest('#ztech')).map(c=>{
                  const r=document.createElement('div');r.className='zrow';r.dataset.probe='1';r.innerHTML='<span class="pill">1</span><span>x</span>';
                  c.appendChild(r);const w=wayRowWay(r),x=w&&wayParse(w,0,true);r.remove();return [c.id,w,!!x&&x.steps>=x.want]})""")
                bad = [f"{i}: {w!r}" for i, w, ok in cards if i not in ROWS_OWN and not ok]
                self.assertEqual(bad, [], "Karten unter Zustand ohne Ziel für ihre Zeilen")
                self.assertIn("zbg", [c[0] for c in cards])
                # Dominik's screenshot: „Mein Zustand aller Profile“ and the „Heute“ line
                await pg.route("**/api/admin/hintergrund", lambda r: r.fulfill(json={
                    "on": True, "profiles": 2, "need": 0, "jobs": {"run": 1, "wait": 2, "ok": 6}, "services": {"wait": 3, "ok": 15}}))
                await pg.evaluate("MYST_ON=true;zBg()")   # the own page Mein Zustand is on for this profile
                await self.until(pg, "document.querySelectorAll('#zbglist .zrow.wayrow[role=link]').length===3")
                await pg.evaluate("zCards({glance:{answers:10,first_sound:4.7,speakers:{online:0,known:2},background:{held:3}},services:{},system:{},check:{}})")
                parts = await pg.evaluate("[...$('ztoday').childNodes].filter(n=>n.nodeName!=='B'&&n.textContent.trim()!=='·').map(n=>n.nodeName+':'+(n.dataset?n.dataset.way:n.textContent))")
                # the speakers: the own page Lautsprecher, or its switch while that page is off (here)
                self.assertEqual(parts, ["A:Zustand → Logs → Anfragen", "A:Funktionen → Eigene Lautsprecher (ESP32)", "A:Zustand → Logs"])
                await pg.click("#zbglist .zrow.wayrow >> nth=0")
                await self.until(pg, "getComputedStyle($('prof')).display!=='none'")
                await pg.evaluate("goSec('mon')")
                await pg.focus("#zbglist .zrow.wayrow >> nth=0")
                await pg.keyboard.press("Enter")
                await self.until(pg, "getComputedStyle($('prof')).display!=='none'")
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())

if __name__ == "__main__":
    unittest.main()
