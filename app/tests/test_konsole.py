"""Spark-Konsole (plan spark-entkoppeln E4, Dominik 2026-11-14 „Beides“): the panel's code as the model computer's own
page. The protection rules, each with its test:

- off by default (konsole.an); only root switches it on, and only with networks of the home network (private, not
  wider than /8), never without one;
- the console process answers only this machine and konsole.netze, and only the paths of konsole.WEGE: everything
  else (the assistant, profiles, tools) is 404 before a route reads the request; the panel without the console mode
  is unchanged;
- "/" is the console's own page, the rest needs the panel's login (401) and its codes;
- of the panel's background work only the sampler starts; the door's firewall lets the console's port in only from
  konsole.netze;
- every switch writes a journal line with fixed words and numbers.
Nothing depends on the time of day."""
import io
import re
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import common  # noqa: E402
import core  # noqa: E402
import konsole  # noqa: E402
import teilen  # noqa: E402


def setze(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c["konsole"] = dict(c.get("konsole") or {}, **kw)
    helpers.write_config(c)


class Base(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        self.before_k, self.before_api = c.get("konsole"), c.get("api")
        self.addCleanup(self.back)

    def back(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["konsole"], c["api"] = self.before_k, self.before_api
        helpers.write_config(c)


class Schalter(Base):
    def test_off_by_default_and_only_home_networks(self):
        with open(os.path.join(os.path.dirname(konsole.__file__), "config.default.json")) as f:
            d = json.load(f)
        self.assertEqual(d["konsole"], {"an": False, "port": konsole.PORT, "netze": []})
        self.assertFalse(konsole.an())
        self.assertTrue(konsole.erlaubt("127.0.0.1"))
        self.assertFalse(konsole.erlaubt("192.168.178.30"))
        for bad in (["8.8.8.0/24"], ["0.0.0.0/0"], ["10.0.0.0/7"], ["127.0.0.0/8"], ["kein netz"], []):
            with self.assertRaises(konsole.Fehler, msg=bad):
                konsole.schalten(True, bad)
        with redirect_stdout(io.StringIO()) as out:
            z = konsole.schalten(True, ["192.168.178.7/24"])
        self.assertEqual(z, {"an": True, "netze": ["192.168.178.0/24"], "port": konsole.PORT})
        self.assertIn("konsole: root an netze 1", out.getvalue())
        self.assertTrue(konsole.erlaubt("192.168.178.30"))
        self.assertTrue(konsole.erlaubt("::ffff:192.168.178.30"))
        self.assertFalse(konsole.erlaubt("192.168.10.5"))
        self.assertFalse(konsole.erlaubt("testclient"))
        with redirect_stdout(io.StringIO()) as out:
            konsole.schalten(False, [])
        self.assertFalse(konsole.erlaubt("192.168.178.30"))
        self.assertIn("konsole: root aus netze 0", out.getvalue())

    def test_port_only_below_31100(self):
        setze(port=8080)
        self.assertEqual(konsole.port(), 8080)
        setze(port=40000)
        self.assertEqual(konsole.port(), konsole.PORT)
        setze(port=True)
        self.assertEqual(konsole.port(), konsole.PORT)

    def test_only_its_own_paths(self):
        for ok in ("/", "/static/konsole.css", "/static/js/konsole.js", "/api/login", "/api/status", "/api/logs/llm",
                   "/api/update", "/api/update/progress", "/api/admin/spark-clients/neu", "/api/admin/modelle",
                   "/api/admin/modellgenau", "/api/konsole/koppeln"):
            self.assertTrue(konsole.weg_ok(ok), ok)
        for bad in ("/api/chat", "/api/profile/login", "/api/updatexyz", "/api/admin/config", "/mcp",
                    "/api/statusx", "/v1/chat/completions", "/api/admin/spark-clientsx", "/api/admin/modellex",
                    "/api/konsolex", "/api/admin/modellgenaux"):
            self.assertFalse(konsole.weg_ok(bad), bad)


class Seite(Base):
    def test_the_console_process_answers_only_its_paths_and_networks(self):
        c = TestClient(panel.app)
        with mock.patch.object(panel, "KONSOLE", True), mock.patch.object(panel.konsole, "erlaubt", lambda h, cfg=None: True):
            r = c.get("/")
            self.assertEqual(r.status_code, 200)
            self.assertIn("Spark-Konsole", r.text)
            self.assertIn("/static/js/konsole.js?v=", r.text)
            self.assertEqual(c.get("/api/chat/history").status_code, 404)
            self.assertEqual(c.post("/api/chat", json={"text": "hallo"}).status_code, 404)
            self.assertEqual(c.get("/api/status").status_code, 401)
            self.assertEqual(c.get("/static/konsole.css").status_code, 200)
            self.assertIn("default-src 'self'", c.get("/api/chat/history").headers.get("content-security-policy", ""))
        with mock.patch.object(panel, "KONSOLE", True):
            self.assertEqual(c.get("/").status_code, 404)   # the test client is no address of the home network
        panel._PAGE.clear()
        r = c.get("/")
        self.assertNotIn("konsole.js", r.text)   # the panel itself is unchanged
        self.assertNotEqual(c.get("/api/whoami").status_code, 404)

    def test_clients_page_is_open_in_the_console(self):
        import sparkclients
        with mock.patch.object(sparkclients.features, "admin_on", lambda k, c=None: False):
            self.assertFalse(sparkclients.admin_on())
            with mock.patch.dict(os.environ, {konsole.ENV: "1"}):
                self.assertTrue(sparkclients.admin_on())

    def test_only_the_sampler_starts(self):
        names = {getattr(f, "__name__", "") for f in panel.app.router.on_startup}
        for n in panel.KONSOLE_START:
            self.assertIn(n, names)
        self.assertGreater(len(names), len(panel.KONSOLE_START))

    def test_page_names_only_files_that_exist(self):
        static = os.path.join(os.path.dirname(panel.__file__), "static")
        with open(os.path.join(static, "konsole.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("<script>", html)          # strict CSP: scripts only as files
        self.assertNotIn("onclick=", html)
        for f in ("konsole.css", "js/konsole.js", "favicon-32.png"):
            self.assertIn("/static/" + f, html)
            self.assertTrue(os.path.exists(os.path.join(static, f)), f)
        with open(os.path.join(static, "js", "konsole.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("const esc=", js)
        for path in ("/api/status", "/api/admin/spark-clients", "/api/update", "/api/logs/", "/api/login", "/api/whoami",
                     "/api/admin/modelle", "/api/konsole/koppeln"):
            self.assertIn(path, js)
            self.assertTrue(konsole.weg_ok(path.rstrip("/") + ("/x" if path.endswith("/") else "")), path)
        for name in re.search(r"const LOGS=\[([^\]]*)\]", js).group(1).replace("'", "").split(","):
            self.assertIn(name, core.LOG_UNITS)


    def test_models_switch_measure_and_own_models_are_open_in_the_console(self):
        import modellseite
        with mock.patch.object(modellseite.features, "admin_on", lambda k, c=None: False):
            self.assertFalse(modellseite._an())
            self.assertFalse(modellseite._eigen_an())
            with mock.patch.dict(os.environ, {konsole.ENV: "1"}):
                self.assertTrue(modellseite._an())
                self.assertTrue(modellseite._eigen_an())

    def test_model_in_detail_is_a_tab_of_the_console(self):
        """Dominik 2026-11-16 „1+2“: the console shows the same page as Zustand → Modell-Rechner genau (one source:
        modellgenau.js, modellgenau.css, zeichnen.js in both pages) and a line about the chat model in its overview."""
        static = os.path.join(os.path.dirname(panel.__file__), "static")
        def read(*p):
            with open(os.path.join(static, *p), encoding="utf-8") as f:
                return f.read()
        html, index, js = read("konsole.html"), read("index.html"), read("js", "konsole.js")
        for page, first in ((html, "/static/js/konsole.js"), (index, "/static/js/base.js")):
            self.assertIn("/static/modellgenau.css", page)
            self.assertLess(page.index("/static/js/zeichnen.js"), page.index(first))
            self.assertLess(page.index(first), page.index("/static/js/modellgenau.js"))
        for i in ('id="zmgdet"', 'id="zmgmeta"', 'id="zmgbody"'):
            self.assertIn(i, html)
        self.assertIn('data-tab="modellgenau"', js)       # since 2026-11-18 a detail of Überblick, no area of its own
        self.assertIn("'modellgenau'", re.search(r"const TABS=\[([^\]]*)\]", js).group(1))
        self.assertIn("modellgenau:mgOpen", js)
        self.assertIn("mgClose()", js)
        self.assertIn("const L=", js)                       # modellgenau.js reads the language as L
        self.assertIn("function setHtml(", read("js", "zeichnen.js"))
        self.assertIn("function spark(", read("js", "zeichnen.js"))
        self.assertNotIn("function setHtml(", read("js", "base.js"))
        self.assertTrue(konsole.weg_ok("/api/admin/modellgenau"))
        # the overview's line: numbers from /api/status, a jump link to the tab
        self.assertIn("genau(d.genau)", js)
        self.assertIn('href="#modellgenau" data-tab="modellgenau"', js)
        import admin
        with mock.patch.object(admin.modellgenau, "fuer_live", lambda nur_llm=False: {"laufen": 2, "warten": 1, "tok_s": 48.0, "kv": 12.0}):
            d = admin._status(common.load_config(), {n: None for n in admin.SERVICES})
        self.assertEqual(d["genau"], {"laufen": 2, "warten": 1, "tok_s": 48.0, "kv": 12.0})
        c = TestClient(panel.app)
        with mock.patch.object(panel, "KONSOLE", True), mock.patch.object(panel.konsole, "erlaubt", lambda h, cfg=None: True):
            self.assertEqual(c.get("/api/admin/modellgenau").status_code, 401)   # open in the console, behind its login
            self.assertEqual(c.get("/static/modellgenau.css").status_code, 200)
            self.assertEqual(c.get("/static/js/zeichnen.js").status_code, 200)
            self.assertEqual(c.get("/static/js/modellgenau.js").status_code, 200)

    def test_overview_shows_only_hints_about_the_spark_itself(self):
        static = os.path.join(os.path.dirname(panel.__file__), "static")
        with open(os.path.join(static, "js", "konsole.js"), encoding="utf-8") as f:
            js = f.read()
        kinds = re.search(r"const HINWEISE=\[([^\]]*)\]", js).group(1).replace("'", "").split(",")
        src = ""
        for name in ("health.py", "systemupdates.py"):
            with open(os.path.join(os.path.dirname(panel.__file__), name), encoding="utf-8") as f:
                src += f.read()
        known = set(re.findall(r'"kind": *"([a-z_]+)"', src))
        for k in kinds:
            self.assertIn(k, known)
        for k in ("latency", "livecheck", "quality"):   # the assistant's own hints stay on the Pi
            self.assertNotIn(k, kinds)
        self.assertIn("HINWEISE.includes(a.kind)", js)


STATIC = os.path.join(os.path.dirname(os.path.abspath(panel.__file__)), "static")


def lies(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Ordnung(unittest.TestCase):
    """Dominik 2026-11-18 „1-6“ (Tafeln konsole-neu/1-4): four areas instead of seven tabs, Modelle and Verbindungen as
    list and detail, the address says where you are (back button), light and dark follow the system, line symbols only
    from icons.js."""

    def test_four_areas_and_the_address(self):
        html, js = lies("konsole.html"), lies("js", "konsole.js")
        nav = re.search(r'<nav class="knav" id="ktabs">(.*?)</nav>', html, re.S).group(1)
        self.assertEqual(re.findall(r'data-tab="([a-z]+)"', nav), ["ueberblick", "modelle", "verbindungen", "wartung"])
        self.assertNotIn("data-theme", html)                   # follows the system, never always dark
        self.assertLess(html.index("/static/js/icons.js"), html.index("/static/js/konsole.js"))
        self.assertIn("addEventListener('hashchange'", js)     # back button and links move between the areas
        self.assertNotIn("replaceState", js)
        for weg in ("#modelle/", "#verbindungen/c/", "#verbindungen/neu", "#verbindungen/assistent", "#wartung/log/", "#modellgenau"):
            self.assertIn(weg, js)
        # Clients and Assistent koppeln are one area, Updates and Logs another; each part is still there
        for teil in ("function koppelDetail", "function clientDetail", "function neuDetail", "function netzDetail",
                     "async function updates", "async function logs"):
            self.assertIn(teil, js)

    def test_lists_and_details_keep_what_the_user_types(self):
        js = lies("js", "konsole.js")
        for name in ("async function verbindungen", "function modDraw"):
            body = js[js.index(name):]
            body = body[:body.index("\nasync function") if "\nasync function" in body else len(body)]
            self.assertIn("felderNeu(el,", body, name)      # a redraw keeps fields, focus and scroll (zeichnen.js)
        self.assertIn('class="kld', js)
        css = lies("konsole.css")
        self.assertIn(".kld:not(.open) .kdet,.kld.open .klist{display:none}", css)   # a phone: list or detail
        self.assertNotRegex(css, r":hover\{[^}]*(transform|translate|scale)")          # nothing jumps


@unittest.skipUnless(__import__("tests.test_ui_browser", fromlist=["browser_ok"]).browser_ok(), "no Playwright/Chromium here")
class Bild(unittest.TestCase):
    """Every area and detail at 1280 and 390 px under the strict CSP: no error, no sideways scrolling, the area marked,
    on a phone list or detail; the back button goes back."""
    ANTWORT = {
        "/api/whoami": {"admin": True, "version": "V01.1.999"},
        "/api/status": {"gpu": {"util": 38, "temp": 61, "power": 74}, "system": {"mem_total_gib": 120, "mem_avail_gib": 31, "cpu": 12},
                        "services": {"llm": {"port": 31016, "state": "active"}, "asr": {"port": 31001, "state": "active"},
                                     "musik": {"port": 31004, "state": "failed"}},
                        "alerts": [{"kind": "memory", "text": "Speicher zu 74 % belegt."}], "genau": {"laufen": 2, "warten": 0, "tok_s": 61.8, "kv": 23}},
        "/api/admin/modelle": {"geraet": "GB10", "budget": {"gesamt": 120, "teile": [{"name": "Sprachmodell", "gib": 62}]}, "wechsel": {"alte": {"llm": 1}},
                               "arten": [{"art": "llm", "name": "Sprachmodell", "modelle": [
                                   {"id": "a", "name": "Modell A", "engine": "vllm", "aktiv": True, "gib": 62, "messbar": True, "empfohlen": False},
                                   {"id": "b", "name": "Modell B", "engine": "vllm", "waehlbar": True, "need_gib": 58, "empfohlen": True},
                                   {"id": "c", "name": "Eigenes C", "engine": "vllm", "waehlbar": True, "need_gib": 20, "eigen": True}]}]},
        "/api/admin/spark-clients": {"an": True, "netze": ["192.168.178.0/24"], "max": 20, "klassen": ["sprache", "dialog", "hintergrund"],
                                     "rechte": ["llm", "asr"], "vorgabe": {"klasse": "dialog", "rechte": ["llm"], "minute": 60, "parallel": 2, "tokens_tag": 0},
                                     "host": "tars", "clients": [{"id": "x1", "name": "Open WebUI", "rechte": ["llm"], "klasse": "dialog",
                                                                  "minute": 60, "parallel": 2, "tokens_tag": 0}]},
        "/api/konsole/koppeln": {"stand": "gekoppelt"},
        "/api/update": {"installed": {"version": "V01.1.999"}, "remote": {"version": "V01.1.999"}},
        "/api/update/progress": {"log": []},
    }

    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def test_every_area(self):
        import asyncio
        from urllib.parse import urlparse
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        html = lies("konsole.html")
        antwort = self.ANTWORT

        async def api(route, request=None):
            weg = urlparse(route.request.url).path
            if weg.startswith("/api/logs/"):
                return await route.fulfill(status=200, content_type="text/plain", body="llm: fertig 61\n")
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(antwort.get(weg, {})))

        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 900), (390, 844)):
                    br, pg, errors = await b.page(p, w, h, csp=True)
                    base = f"http://127.0.0.1:{self.port}"
                    csp = (await pg.request.get(base + "/")).headers.get("content-security-policy", "")
                    await pg.route("**/konsole-probe", lambda route, request=None: route.fulfill(
                        status=200, content_type="text/html", body=html, headers={"Content-Security-Policy": csp}))
                    await pg.route("**/api/**", api)
                    await pg.goto(base + "/konsole-probe")
                    await b.until(pg, "!!document.querySelector('#kohero .kt')")
                    self.assertIn("Musik", await pg.inner_text("#kohero"))       # what does not run, in one sentence
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#ktabs .ic').length"), 4)
                    for weg, area, sel in (("modelle/llm", "modelle", "#tab-modelle .kdet h1"), ("verbindungen/c/x1", "verbindungen", "[data-recht-c]"),
                                           ("verbindungen/neu", "verbindungen", "#kcname"), ("verbindungen/assistent", "verbindungen", "[data-a='code']"),
                                           ("wartung/log/llm", "wartung", "#klog"), ("modelle/eigen", "modelle", "#kmrepo"), ("modellgenau", "ueberblick", "#zmgdet:not([hidden])")):
                        await pg.evaluate(f"location.hash='{weg}'")
                        await b.until(pg, f"!!document.querySelector(\"{sel}\")")
                        self.assertEqual(await pg.evaluate("document.querySelector('#ktabs a.on').dataset.tab"), area, weg)
                        self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth"), 0, (w, weg))
                        if w < 761 and area in ("modelle", "verbindungen"):   # a phone shows the detail alone
                            self.assertTrue(await pg.evaluate(f"!!document.querySelector('#tab-{area} .kld.open')"), weg)
                        if os.environ.get("KONSOLE_SHOT"):
                            await pg.screenshot(path=os.path.join(os.environ["KONSOLE_SHOT"], f"{w}-{weg.replace('/', '_')}.png"), full_page=True)
                    await pg.go_back()
                    await b.until(pg, "!document.getElementById('tab-modelle').hidden")   # back: Modelle → eigenes Modell
                    if w < 761:
                        await pg.evaluate("location.hash='modelle'")
                        # the list alone: drawn anew without the detail once the answer is there
                        await b.until(pg, "!!document.querySelector('#tab-modelle .kld:not(.open) .klist')")
                        self.assertTrue(await pg.evaluate("getComputedStyle(document.getElementById('kside')).position==='fixed'"))
                    self.assertEqual(errors, [], w)
                    await br.close()
        asyncio.run(go())


class Koppeln(Base):
    """Assistent koppeln (E4b): root's unit shows the code; the console reads it only while it lives."""
    def test_code_only_while_it_lives_and_only_checked_shapes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "koppelcode.json")
            self.assertEqual(konsole.koppeln_stand(1000, p), {})
            f = ":".join(["AB"] * 32)
            teilen.konsole_schreiben({"code": "ABC-DEF", "bis": 1600, "fingerabdruck": f}, p)
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)
            self.assertEqual(konsole.koppeln_stand(1000, p), {"code": "ABC-DEF", "bis": 1600, "rest": 600, "fingerabdruck": f})
            self.assertEqual(konsole.koppeln_stand(1600, p), {})
            teilen.konsole_schreiben({"code": "<b>x</b>", "bis": 1600}, p)
            self.assertEqual(konsole.koppeln_stand(1000, p), {})
            teilen.konsole_schreiben({"stand": "gekoppelt", "t": 1000}, p)
            self.assertEqual(konsole.koppeln_stand(1100, p), {"stand": "gekoppelt", "t": 1000})
            self.assertEqual(konsole.koppeln_stand(1000 + konsole.KOPPEL_ZEIGEN, p), {})
            teilen.konsole_schreiben({"stand": "irgendwas", "t": 1000}, p)
            self.assertEqual(konsole.koppeln_stand(1100, p), {})

    def test_only_in_the_console_and_only_with_login(self):
        c = TestClient(panel.app)
        self.assertEqual(c.get("/api/konsole/koppeln").status_code, 404)   # the panel itself has no such page
        with mock.patch.object(panel, "KONSOLE", True), mock.patch.object(panel.konsole, "erlaubt", lambda h, cfg=None: True):
            self.assertEqual(c.get("/api/konsole/koppeln").status_code, 401)
            self.assertEqual(c.post("/api/konsole/koppeln", json={}).status_code, 401)

    def test_start_is_the_fixed_unit_and_logs(self):
        seen = []
        with mock.patch.object(konsole.subprocess, "run", lambda a, **k: seen.append(a) or mock.Mock(returncode=0)), \
                redirect_stdout(io.StringIO()) as out:
            self.assertTrue(konsole.koppeln_starten())
        self.assertEqual(seen, [["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", konsole.KOPPEL_UNIT]])
        self.assertIn("konsole: koppeln gestartet", out.getvalue())
        with mock.patch.object(konsole.subprocess, "run", side_effect=OSError), redirect_stdout(io.StringIO()) as out:
            self.assertFalse(konsole.koppeln_starten())
        self.assertIn("konsole: koppeln fehler", out.getvalue())


class SparkKoppeln(Base):
    """Einstellungen → Spark → Spark koppeln (E4c): the panel writes a checked wish of 5 minutes; root takes it once."""
    def setUp(self):
        super().setUp()
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        for k, v in (("WUNSCH", "w.json"), ("KOPPEL_STAND", "s.json")):
            p = mock.patch.object(teilen, k, os.path.join(self.d.name, v))
            p.start()
            self.addCleanup(p.stop)

    def test_the_wish_is_checked_taken_once_and_lives_five_minutes(self):
        for host, code in (("192.168.178.171", "abc def"), ("tars.lan", "ABC-DEF")):
            self.assertEqual(teilen.wunsch_schreiben(host, code, now=1000), host)
            self.assertEqual(teilen.stand_lesen(1000)["stand"], "laeuft")
            self.assertEqual(teilen.wunsch_nehmen(1001), (host, "ABCDEF"))
            self.assertIsNone(teilen.wunsch_nehmen(1002))            # once
        teilen.wunsch_schreiben("tars", "ABCDEF", now=1000)
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(teilen.wunsch_nehmen(1000 + teilen.WUNSCH_SECS))
        for host, code in (("tars; rm -rf /", "ABCDEF"), ("", "ABCDEF"), ("tars", "ABCDE0"), ("tars", "ABC")):
            with self.assertRaises(teilen.Fehler):
                teilen.wunsch_schreiben(host, code)
        teilen.stand_setzen("unsinn", 1000)
        self.assertEqual(teilen.stand_lesen(1000)["stand"], "laeuft")
        self.assertEqual(teilen.stand_lesen(1000 + 3601)["stand"], "fehler")   # a pairing never runs this long

    def test_endpoint_needs_login_and_root_takes_only_the_checked_wish(self):
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/admin/spark/koppeln", json={"host": "tars", "code": "ABCDEF"}).status_code, 401)
        with mock.patch.object(panel, "KONSOLE", True), mock.patch.object(panel.konsole, "erlaubt", lambda h, cfg=None: True):
            self.assertEqual(c.get("/api/admin/spark/koppeln").status_code, 404)   # not a path of the console
        with open(os.path.join(os.path.dirname(konsole.__file__), "speech-spark.sh"), encoding="utf-8") as f:
            cli = f.read()
        fn = cli[cli.index("teilen_koppeln_wunsch() {"):]
        fn = fn[:fn.index("\n}\n")]
        self.assertIn("as_panel_user ../teilen.py wunsch-nehmen", fn)
        self.assertIn('"${code:-}" =~ ^[A-HJ-NP-Z2-9]{6}$', fn)
        self.assertIn('SPEECH_SPARK_CODE="$code" teilen_koppeln "$host"', fn)
        self.assertIn('[ "${INVOCATION_ID:-}" ] || die "only inside its own unit"; teilen_koppeln_wunsch', cli)
        self.assertEqual(set(teilen.CODE_ABC), set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789"))
        try:
            sh = helpers.repo_file("install.sh")
        except unittest.SkipTest:
            return
        self.assertIn("ExecStart=/bin/bash $PREFIX/app/speech-spark.sh teilen koppeln-wunsch-intern", sh)
        self.assertIn("/usr/bin/systemctl start --no-block speech-spark-koppeln'", sh)


class Firewall(Base):
    def test_door_rules_let_the_console_in_only_from_its_networks(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["api"] = dict(c.get("api") or {}, tls_listen="192.168.178.171", tls_from=["192.168.178.20"])
        helpers.write_config(c)
        self.assertNotIn(str(konsole.PORT), teilen.regeln(common.load_config()))
        setze(an=True, netze=["192.168.178.0/24"])
        r = teilen.regeln(common.load_config())
        self.assertIn(f"ip saddr {{ 192.168.178.0/24 }} tcp dport {konsole.PORT} accept", r)
        self.assertIn(f"tcp dport {konsole.PORT} drop", r)
        self.assertLess(r.index(f"tcp dport {konsole.PORT} accept"), r.index(f"tcp dport {konsole.PORT} drop"))

    def test_unit_and_command(self):
        try:
            sh = helpers.repo_file("install.sh")
        except unittest.SkipTest:
            sh = ""   # the copy with only app/
        if sh:
            self.assertIn("Environment=SPEECH_SPARK_KONSOLE=1", sh)
            self.assertIn("systemctl disable --now speech-spark-konsole.service", sh)
            self.assertIn("ExecStart=/bin/bash $PREFIX/app/speech-spark.sh teilen code --konsole", sh)
            self.assertIn(f"/usr/bin/systemctl start --no-block {konsole.KOPPEL_UNIT}'", sh)
        with open(os.path.join(os.path.dirname(konsole.__file__), "speech-spark.sh"), encoding="utf-8") as f:
            cli = f.read()
        self.assertIn('konsole) shift; need_root konsole "$@"; cmd_konsole "$@" ;;', cli)
        self.assertIn('--konsole) k=1 ;;', cli)
        self.assertIn("""[ "$(mode)" = full ] || [ "$(cfg '.konsole.an // false')" = true ] || die "no web panel""", cli)
        self.assertIn('TEILEN_KONSOLE="${TEILEN_KONSOLE:-0}"', cli)


if __name__ == "__main__":
    unittest.main()
