"""Zustand → Live and the wall monitor /live (V01.0.312, live.py): off by default, admin only, only fixed words,
tool names and numbers (never question, answer, tool arguments or results), names only with the profile's own
consent (and on the monitor only when the admin also allows it), every tool and service is on the picture, the
monitor pairs once with a one-time code from the home network only, wrong codes lock like a wrong login,
deleting a monitor cuts it off at once, at most logs.live_screens screens. No wall clock dependence.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import re
import unittest
import unittest.mock

from tests import helpers

helpers.start()
import guard  # noqa: E402
import live  # noqa: E402
import netguard  # noqa: E402
import panel  # noqa: E402
import tracelog  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_tracelog import ADMIN, SECRET, ask, profile  # noqa: E402

HOME = ("192.168.1.40", 50000)      # a screen in the home network
NET = ("89.204.1.2", 50000)         # a sender from the internet


def set_logs(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c.setdefault("logs", {}).update(kw)
    helpers.write_config(c)


def set_proxies(p):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c["panel"]["trusted_proxies"] = p
    helpers.write_config(c)


def reset():
    with live._lock:
        live._run.clear(), live._events.clear(), live._guard.clear(), live._door.clear(), live._rets.clear()
        live._count.clear(), live._codes.clear(), live._seen.clear(), live._past.clear(), live._hits.clear()
        live._saved[0] = 0.0
        live._unset[0] = 0.0
    try:
        os.remove(live._file())
    except OSError:
        pass
    guard.reset()
    guard._rate.clear()


def new_code(name="Flur"):
    r = ADMIN.post("/api/admin/live/monitors", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def paired(client=HOME, name="Flur"):
    c = TestClient(panel.app, client=client)
    r = c.post("/api/live/pair", json={"code": new_code(name)})
    assert r.status_code == 200, r.text
    return c


class Live(unittest.TestCase):
    def setUp(self):
        reset()
        set_logs(live=True, live_monitor=True, live_names=False, live_screens=3, trace=False)

    def tearDown(self):
        set_logs(live=False, live_monitor=False, live_names=False, live_screens=3)
        set_proxies([])
        reset()
        tracelog.clear()

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            logs = json.load(f)["logs"]
        self.assertEqual((logs["live"], logs["live_monitor"], logs["live_names"]), (False, False, False))
        set_logs(live=False, live_monitor=False)
        r = ADMIN.get("/api/admin/live")   # off: a quiet answer, no 404 in the console of every admin page (B8)
        self.assertEqual((r.status_code, r.json()), (200, {"on": False}))
        self.assertEqual(TestClient(panel.app, client=HOME).get("/live").status_code, 404)
        self.assertEqual(TestClient(panel.app, client=HOME).get("/api/live/state").status_code, 404)
        # live off: the monitor switch alone opens nothing
        set_logs(live=False, live_monitor=True)
        self.assertEqual(TestClient(panel.app, client=HOME).get("/live").status_code, 404)
        self.assertIsNone(tracelog.start(0, "web"))

    def test_admin_only(self):
        self.assertEqual(TestClient(panel.app).get("/api/admin/live").status_code, 401)
        self.assertIn(profile("Lgast").get("/api/admin/live").status_code, (401, 403))
        self.assertEqual(TestClient(panel.app).post("/api/admin/live/monitors", json={}).status_code, 401)
        import coadmin
        self.assertFalse(any("GET" in m and p.fullmatch("/api/admin/live") for m, p in coadmin.MANAGER))   # not a Verwalter

    def test_request_shows_without_any_text(self):
        a = profile("Lweg")
        ask(a, 'TOOL memory_save {"fact": "Lweg mag ' + SECRET + '."}')
        d = ADMIN.get("/api/admin/live").json()
        self.assertEqual(len(d["reqs"]), 1)
        r = d["reqs"][0]
        self.assertTrue(r["done"])
        self.assertEqual(r["who"], "Profil")                     # no consent: no name
        self.assertIn("memory_save", [s["n"] for s in r["steps"]])
        self.assertEqual(d["rets"][0]["tool"], "memory_save")
        self.assertEqual(d["rets"][0]["to"], "mem")
        self.assertNotIn(SECRET, json.dumps(d))
        self.assertNotIn("Lweg", json.dumps(d))
        # Logs → Anfragen is off: nothing was written
        self.assertEqual(ADMIN.get("/api/admin/traces?minutes=60").json()["items"], [])

    def test_last_action_stays_until_a_new_one_comes(self):
        """Dominik 2026-10-10: the last action stays on the picture; it fades only once something new came."""
        rec = tracelog.start(1000.0, "web")
        self.assertFalse(rec.persist)
        rec.step("in", "Eingang", 1000.0, 1000.1)
        tracelog.finish(rec, now=1001.0)
        r = live.snapshot(now=5000.0)["reqs"]
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["last"])
        self.assertIsNone(r[0]["left"])
        self.assertEqual(r[0]["ago"], 3999)
        new = tracelog.start(5001.0, "speaker")
        r = {x["id"]: x for x in live.snapshot(now=5005.0)["reqs"]}
        self.assertFalse(r[rec.id]["last"])
        self.assertEqual(r[rec.id]["left"], 6)
        self.assertFalse(r[new.id]["done"])
        self.assertEqual([x["id"] for x in live.snapshot(now=5012.0)["reqs"]], [new.id])
        tracelog.finish(new, now=5013.0)
        self.assertTrue(live.snapshot(now=9000.0)["reqs"][0]["last"])

    def test_names_only_with_consent_and_on_the_monitor_only_when_allowed(self):
        a = profile("Lname")
        self.assertEqual(a.put("/api/profile/settings", json={"trace_name": True}).status_code, 200)
        ask(a, "Hallo")
        self.assertEqual(ADMIN.get("/api/admin/live").json()["reqs"][0]["who"], "Lname")
        m = paired()
        self.assertEqual(m.get("/api/live/state").json()["reqs"][0]["who"], "Person")
        set_logs(live_names=True)
        self.assertEqual(m.get("/api/live/state").json()["reqs"][0]["who"], "Lname")
        a.put("/api/profile/settings", json={"trace_name": False})
        self.assertEqual(m.get("/api/live/state").json()["reqs"][0]["who"], "Person")

    def test_every_tool_is_on_the_picture(self):
        """Dominik 2026-10-10: keep the monitor current. A new tool in chat.py or an extras service must get a
        target in live.TOOLS, else it would not show where the request goes."""
        import chat
        import extras
        with open(chat.__file__, encoding="utf-8") as f:
            names = set(re.findall(r'"name": "([a-z_]+)"', f.read()))
        import rmplus      # tools another module offers through a service (remarkable.offer)
        for m in list(extras.SERVICES) + [rmplus]:
            with open(m.__file__, encoding="utf-8") as f:
                names |= set(re.findall(r'"name": "([a-z_]+)"', f.read()))
        names -= {"parameters"}
        # function tools defined anywhere in the panel (rmplus.py, …), except the live check's own test tool
        import glob
        for path in glob.glob(os.path.join(os.path.dirname(live.__file__), "*.py")):
            with open(path, encoding="utf-8") as f:
                names |= set(re.findall(r'"function":\s*\{\s*"name":\s*"([a-z_]+)"', f.read()))
        names -= {"get_time"}
        # tool steps the panel writes itself (a running job: .now("tool", …), its steps, live.job(why, tool, …)):
        # each needs a target too, else a new job would stand nowhere in the picture (Dominik 2026-10-12)
        own = set()
        for path in glob.glob(os.path.join(os.path.dirname(live.__file__), "*.py")):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            own |= set(re.findall(r'\.(?:now|step)\("tool",\s*"([^"]+)"', text))
            own |= set(re.findall(r'live\.job\(\s*[^,]+,\s*"([^"]+)"', text))
        self.assertTrue({"document_write", "document_build", "NAS-Sicherung"} <= own, own)
        import docmake
        own |= set(docmake.SEND_LIVE.values())       # delivering a document goes to its real target
        self.assertEqual(sorted(n for n in own if n.removesuffix(" (Panel)") not in live.TOOLS), [],
                         "a job's own tool step: add it to live.TOOLS with a target")
        self.assertEqual(sorted(n for n in names if n not in live.TOOLS), [],
                         "a new tool: add it to live.TOOLS (and a target to live.TARGETS if it goes somewhere new)")
        import mcpserver   # tools programs call over MCP show as their own requests
        self.assertEqual(sorted(n for n in mcpserver.TOOLS if n not in live.TOOLS and n not in mcpserver.SHOW
                                and n != "ask_spark"), [], "a new MCP tool: add it to live.TOOLS or mcpserver.SHOW")
        self.assertEqual(sorted(v[1] for v in mcpserver.SHOW.values() if v[0] == "tool" and v[1] not in live.TOOLS), [])
        for n, tgt in live.TOOLS.items():
            self.assertIn(tgt, live.TARGETS, n)
            self.assertIn(tgt, live.RETURNS, n)
        for k, v in live.TARGETS.items():
            self.assertIn(v[2], ("spark", "lan", "net"), k)
        # Dominik 2026-10-10: the web search asks search engines outside, pages from hits come from outside
        self.assertEqual((live.TARGETS["web"][2], live.TARGETS[live.TOOLS["read_page"]][2]), ("net", "net"))
        # every kind of the admin log reaches "Ereignisse" or is shown in its own way (Dominik 2026-10-12)
        kinds = set()
        for path in glob.glob(os.path.join(os.path.dirname(live.__file__), "*.py")):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            kinds |= set(re.findall(r'guard\.log\(\s*"([a-z_]+)"', text))
            kinds |= {p + w for p, ws in re.findall(r'guard\.log\(\s*"([a-z_]+_)"\s*\+\s*\(([^,]+)', text)
                      for w in re.findall(r'"([a-z]+)"', ws)}
        kinds |= {"hilfe_applied", "hilfe_undone"}       # "hilfe_" + card["state"]
        self.assertTrue({"handoff_ok", "handoff_wrong", "admin_login"} <= kinds, kinds)
        self.assertEqual(sorted(k for k in kinds if k not in guard.LIVE_WORDS and k not in guard.LIVE_SKIP and not k.endswith("_")), [],
                         "a new kind in the admin log: add it to guard.LIVE_WORDS (or LIVE_SKIP with the reason)")
        import tracelog as tl
        self.assertEqual(set(live.CLIENT) - {"other"}, set(tl.CLIENTS) - {"other"},
                         "a new kind of device: add a word to live.CLIENT")

    def test_rewind_counters_and_node_numbers(self):
        """Live-Log interaktiv (Dominik 2026-10-11): finished requests of the last 15 minutes for Zurückspulen
        (admin only, never on the monitor), numbers per node for its sheet, the Selbst-Notaus counters."""
        import notaus
        rec = live.begin("auto", "", t=1000, auto=True, why="Update-Prüfung")
        rec.step("in", "Von selbst", 1000)
        rec.step("tool", "GitHub", 1000, 1001.5, ok=False)
        live.ended(rec, now=1002)
        P = live.past_reqs(now=1100)
        self.assertEqual([(x["id"], x["te"], x["steps"][-1]["to"]) for x in P], [(rec.id, 1002, "github")])
        self.assertEqual(live.past_reqs(now=1002 + live.REWIND + 1), [])
        self.assertEqual(ADMIN.get("/api/admin/live?past=1").json()["rewind"], live.REWIND)
        self.assertNotIn("past", live.snapshot("monitor"))
        st = live.node_stats(now=1100)
        self.assertEqual((st["github"]["n"], st["github"]["bad"], st["github"]["ms"], st["github"]["last"]), (1, 1, 1500, [False]))
        self.assertEqual(live.node_stats(now=1001.5 + 3601), {})
        with notaus._auto_lock:
            before = {k: list(v) for k, v in notaus._auto_seen.items()}
        try:
            for i in range(3):
                notaus.watch("login", now=5000 + i)
            rows = {r["k"]: (r["n"], r["of"], r["min"]) for r in notaus.auto_for_live(now=5010)["rows"]}
            self.assertEqual(rows["login"], (3, 20, 10))
            self.assertEqual(notaus.auto_for_live(now=5010 + 601)["rows"][0]["n"], 0)
            self.assertIn("auto", live.snapshot()["notaus"])
        finally:
            with notaus._auto_lock:
                notaus._auto_seen.update(before)

    def test_services_state(self):
        """Hören, Sprechen and the language model carry a dot: running, loading, not answering, off; a change and a
        watchdog restart are events (point 10 of the list, Dominik 2026-10-10)."""
        reset()
        set_logs(live=True)
        try:
            live._svc.clear()
            cfg = {"asr": {"enabled": True}, "tts": {"enabled": True}}
            live.services({"asr": {"status": "ok", "queue": {"waiting": 2, "running": 1}}, "tts": {"status": "loading"}}, cfg, now=1000)
            self.assertEqual(live.snapshot(now=1001)["svc"]["asr"], {"st": "ok", "word": "läuft", "ago": 1, "wait": 2, "run": 1})
            live.services({"asr": None, "tts": {"status": "loading"}}, cfg, now=1003)
            live.llm_seen(False, "llm_down", now=1004)
            d = live.snapshot(now=1010)
            self.assertEqual({k: v["st"] for k, v in d["svc"].items()}, {"asr": "down", "tts": "load", "qwen": "down"})
            self.assertEqual(d["svc"]["asr"]["word"], "antwortet nicht")
            live.services({"asr": None, "tts": None}, {"asr": {"enabled": True}, "tts": {"enabled": False}}, now=1011)
            self.assertEqual(live.snapshot(now=1012)["svc"]["tts"]["st"], "off")
            live.restarted("ASR", "antwortet seit 300 s nicht", True)
            texts = [e["text"] for e in live.snapshot(now=1013)["events"] if e["area"] == "Dienste"]
            self.assertIn("Hören: antwortet nicht", texts)
            self.assertIn("Sprachmodell: antwortet nicht", texts)
            self.assertTrue(any(t.startswith("ASR neu gestartet") for t in texts))
            # Vorrang für Personen (stufe.py): a star at the request
            import stufe
            from types import SimpleNamespace
            rec = live.begin("web", "", t=1012)
            turn = SimpleNamespace(who={"id": "u1"}, own_browser=True, ccfg={}, tr=rec)
            real = stufe.level
            stufe.level = lambda uid, c=None: "vorrang"
            try:
                stufe.first(stufe.begin(turn))
            finally:
                stufe.level = real
            self.assertTrue(next(r for r in live.snapshot(now=1013)["reqs"] if r["id"] == rec.id)["prio"])
            # an hour without news: no dot (nothing known)
            self.assertEqual(live.snapshot(now=1011 + 3601)["svc"], {})
        finally:
            live._svc.clear()
            set_logs(live=False)

    def test_background_work(self):
        """Point 8 of the list: background work (vorrang.py) shows under "Läuft gerade", waiting while somebody
        speaks; its end is an event. Only the job's fixed name, never what it works on."""
        import asyncio
        import vorrang
        reset()
        set_logs(live=True)
        real = vorrang.speaking
        try:
            talk = [True]
            vorrang.speaking = lambda now=None: talk[0]
            seen = []

            async def nap(s):
                seen.append([(b["job"], b["st"]) for b in live.snapshot()["bg"]])
                talk[0] = False

            async def work():
                seen.append([(b["job"], b["st"]) for b in live.snapshot()["bg"]])
                return 7
            self.assertEqual(asyncio.run(vorrang.run("Dokument lesen", work, sleep=nap)), 7)
            self.assertEqual(seen, [[("Dokument lesen", "wait")], [("Dokument lesen", "run")]])
            self.assertEqual(live.snapshot()["bg"], [])
            self.assertTrue(any(e["area"] == "Hintergrund" and e["text"].startswith("Dokument lesen fertig")
                                for e in live.snapshot()["events"]))
            self.assertEqual(asyncio.run(vorrang.in_thread("Sicherung", lambda: 3)), 3)
            self.assertEqual(live.snapshot()["bg"], [])
        finally:
            vorrang.speaking = real
            set_logs(live=False)

    def test_warnings_at_their_place(self):
        """Dominik 2026-10-10: a warning like "Antworten sind langsamer geworden" shows at its connection on the
        live page, in fixed words with numbers, and once under Ereignisse; never the quality test's question."""
        from unittest import mock
        import latency
        import quality
        reset()
        set_logs(live=True)
        live._hint_cache[:] = [0.0, []]
        live._hint_seen.clear()
        slow = {"day": {"n": 12, "median": 5.03, "p90": 7}, "week": {"n": 80, "median": 3.23, "p90": 4}, "warn": "x"}
        try:
            with mock.patch.object(latency, "summary", lambda now=None: slow), \
                    mock.patch.object(quality, "last", lambda: {"t": 1000, "cases": [{"q": "Geheime Testfrage", "new": True}]}):
                d = live.snapshot(now=1000)
                live.snapshot(now=1010)
            hs = {h["word"]: h for h in d["hints"]}
            self.assertEqual({k: hs["erster Ton 5,03 s statt 3,23 s"][k] for k in ("at", "level", "go")},
                             {"at": "tts", "level": "warn", "go": "test"})
            self.assertEqual({k: hs["Qualitätstest: 1 neu kaputt"][k] for k in ("at", "level", "go")},
                             {"at": "llm", "level": "warn", "go": "test"})
            # a click on ⚠ explains it in one fixed sentence and leads to a page (never the server's error text)
            for h in d["hints"]:
                self.assertIn(h["why"], [w for _, w, _ in live.EXPLAIN])
            self.assertNotIn("Geheime", json.dumps(d))
            ev = [e["text"] for e in live.snapshot(now=1020)["events"] if e["area"] == "Hinweis"]
            self.assertEqual(sorted(ev), sorted(["erster Ton 5,03 s statt 3,23 s", "Qualitätstest: 1 neu kaputt"]))
        finally:
            live._hint_cache[:] = [0.0, []]
            set_logs(live=False)

    def test_everything_else_that_happens(self):
        """Gesamtprüfung 2026-10-11 (Dominik: everything that can be shown): audit events in fixed words, the update
        check and the NAS backup as ways of "Von selbst", the Spark-Begleiter and room mode as open channels.
        Never a name, address or detail."""
        import guard
        import update
        reset()
        set_logs(live=True)
        try:
            guard.log("profile_login", who="Geheimname", ip="192.168.1.77")
            guard.log("invite_used", detail="Einladung für Oma")
            guard.log("change", path="/api/x")                     # the generic one stays out
            update._remote_cache.update(time=0, data=None)
            real = update._remote_state

            async def fake(force=False):
                return {"checked": __import__("time").time(), "latest": "a" * 40, "behind": 3, "version": "V9.9.9",
                        "head_state": "running", "error": None}
            update._remote_state = fake
            try:
                import asyncio
                asyncio.run(update.remote_state(force=True))
            finally:
                update._remote_state = real
            live.job("Sicherung nach außen", "NAS-Sicherung", __import__("time").time() - 2)
            d = live.snapshot()
            texts = [(e["area"], e["text"]) for e in d["events"]]
            self.assertIn(("Eingang", "Anmeldung eines Profils"), texts)
            self.assertIn(("Eingang", "Einladung benutzt"), texts)
            self.assertIn(("Update", "Prüfung: neuere getestete Version V9.9.9 (3 Änderungen) · neuester Stand: Tests laufen"), texts)
            self.assertFalse(any("api/x" in t for _, t in texts))
            ways = sorted((r["intent"], r["steps"][-1]["to"]) for r in d["reqs"] if r["auto"])
            self.assertEqual(ways, [("Sicherung nach außen", "nas"), ("Update-Prüfung", "github")])
            self.assertEqual({t["zone"] for t in d["targets"] if t["id"] == "github"}, {"net"})
            # what the Spark starts itself is labelled "Spark", never "Gast" (live page and Logs → Anfragen)
            self.assertEqual({r["who"] for r in d["reqs"] if r["auto"]}, {"Spark"})
            import tracelog
            mine = [tracelog.shown(r.data()) for r in live._run.values() if getattr(r, "auto", False)]
            self.assertEqual({x["name"] for x in mine}, {"Spark"})
            self.assertEqual(tracelog.shown({"kind": "guest"})["name"], "Gast")
            for secret in ("Geheimname", "192.168.1.77", "Oma"):
                self.assertNotIn(secret, json.dumps(d))
            # the Spark-Begleiter asking for notes, room mode listening: open channels
            import begleiter
            import roomlive
            with unittest.mock.patch.object(roomlive, "everybody", lambda: [{}, {}]), \
                    unittest.mock.patch.object(begleiter, "_seen", {"dX": __import__("time").time(), "old": 0}):
                names = {c["name"]: c["n"] for c in live.snapshot()["conns"]}
            self.assertEqual((names.get("Spark-Begleiter (PC/Mac)"), names.get("Raum-Modus hört zu")), (1, 2))
            # every audit word is a fixed word
            for k, (area, word) in guard.LIVE_WORDS.items():
                self.assertRegex(word, r"^[\wÄÖÜäöüß ().,-]+$", k)
        finally:
            set_logs(live=False)

    def test_waechter_decisions_with_reasons(self):
        with self.assertRaises(Exception):
            netguard.resolve("127.0.0.1", 31002, "public")
        d = ADMIN.get("/api/admin/live").json()["guard"]
        self.assertEqual(d["bad"], 1)
        x = d["items"][0]
        self.assertFalse(x["ok"])
        self.assertEqual(x["to"], "127.0.0.1:31002")             # the blocked address is the reason, so it shows
        self.assertTrue(x["why"])
        live.outgoing("search.example.org", 443, "public", "93.184.216.34", None)
        x = ADMIN.get("/api/admin/live").json()["guard"]["items"][0]
        self.assertTrue(x["ok"])
        self.assertEqual(x["to"], "Webseite")                    # allowed pages from search results: no address
        set_logs(live=False)
        live.outgoing("a.example", 443, "public", "93.184.216.34", None)
        self.assertEqual(len(live._guard), 2)                    # off: nothing is kept

    def test_short_ip(self):
        self.assertEqual(live.short_ip("89.204.135.7"), "89.204.x.x")
        self.assertEqual(live.short_ip("2a02:810:abcd::1"), "2a02:0810::x")
        self.assertEqual(live.short_ip("kein"), "?")

    def test_monitor_pairs_once_with_a_code(self):
        c = TestClient(panel.app, client=HOME)
        self.assertEqual(c.get("/api/live/state").status_code, 401)
        page = c.get("/live")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("<script>", page.text)
        self.assertIn("/static/js/live.js?v=", page.text)
        code = new_code()
        self.assertRegex(code, r"^\d{6}$")
        r = c.post("/api/live/pair", json={"code": code})
        self.assertEqual(r.status_code, 200)
        cookie = r.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        d = c.get("/api/live/state")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.json()["monitor"], "Flur")
        self.assertEqual(d.json()["view"], "monitor")
        # the code works once
        self.assertEqual(TestClient(panel.app, client=("192.168.1.41", 1)).post("/api/live/pair", json={"code": code}).status_code, 401)
        # stored as a hash only
        with open(live._file()) as f:
            text = f.read()
        self.assertNotIn(c.cookies.get(live.COOKIE), text)
        self.assertEqual(oct(os.stat(live._file()).st_mode & 0o777), "0o600")
        # the monitor's cookie opens nothing else
        self.assertEqual(c.get("/api/admin/live").status_code, 401)
        self.assertEqual(c.get("/api/status").status_code, 401)

    def test_code_expires(self):
        code = new_code()
        with live._lock:
            for k, (u, n) in list(live._codes.items()):
                live._codes[k] = (u - live.CODE_S - 1, n)
        self.assertEqual(TestClient(panel.app, client=HOME).post("/api/live/pair", json={"code": code}).status_code, 401)

    def test_wrong_codes_lock_and_show_in_eingang(self):
        new_code()
        g = TestClient(panel.app, client=("192.168.1.66", 1))
        codes = []
        for i in range(8):
            r = g.post("/api/live/pair", json={"code": f"{i:06d}x"})
            codes.append(r.status_code)
        self.assertIn(429, codes)
        self.assertEqual(codes[0], 401)
        door = ADMIN.get("/api/admin/live").json()["door"]
        self.assertGreaterEqual(door["out"], 1)
        self.assertEqual(door["items"][-1]["from"], "192.168.x.x")
        self.assertIn("Monitor-Code", door["items"][-1]["why"])

    def test_internet_is_turned_away(self):
        n = TestClient(panel.app, client=NET)
        self.assertEqual(n.get("/live").status_code, 403)
        self.assertEqual(n.post("/api/live/pair", json={"code": new_code()}).status_code, 403)
        self.assertEqual(n.get("/api/live/state").status_code, 403)
        door = ADMIN.get("/api/admin/live").json()["door"]["items"]
        self.assertEqual(door[0]["from"], "89.204.x.x")
        # behind the listed reverse proxy, its X-Forwarded-For counts
        set_proxies(["192.168.1.5"])
        p = TestClient(panel.app, client=("192.168.1.5", 1))
        self.assertEqual(p.get("/live", headers={"x-forwarded-for": "89.204.1.2"}).status_code, 403)
        self.assertEqual(p.get("/live", headers={"x-forwarded-for": "192.168.1.70"}).status_code, 200)
        # from an unlisted device an invented X-Forwarded-For is ignored (it is a home screen)
        set_proxies([])
        self.assertEqual(TestClient(panel.app, client=("192.168.1.66", 1)).get(
            "/live", headers={"x-forwarded-for": "89.204.1.2"}).status_code, 200)

    def test_deleting_cuts_off_at_once(self):
        m = paired()
        self.assertEqual(m.get("/api/live/state").status_code, 200)
        items = ADMIN.get("/api/admin/live/monitors").json()["items"]
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["watching"])
        self.assertEqual(ADMIN.delete("/api/admin/live/monitors/" + items[0]["id"]).status_code, 200)
        self.assertEqual(m.get("/api/live/state").status_code, 401)
        self.assertEqual(ADMIN.delete("/api/admin/live/monitors/../x").status_code, 404)
        self.assertEqual(ADMIN.delete("/api/admin/live/monitors/m_zz").status_code, 400)

    def test_switching_the_monitor_off_stops_it(self):
        m = paired()
        set_logs(live_monitor=False)
        self.assertEqual(m.get("/api/live/state").status_code, 404)
        self.assertEqual(ADMIN.post("/api/admin/live/monitors", json={"name": "x"}).status_code, 409)

    def test_screens_cap(self):
        set_logs(live_screens=1)
        a, b = paired(name="Eins"), paired(("192.168.1.41", 1), name="Zwei")
        self.assertEqual(a.get("/api/live/state").status_code, 200)
        self.assertEqual(b.get("/api/live/state").status_code, 429)
        self.assertEqual(a.get("/api/live/state").status_code, 200)   # the one already showing goes on

    def test_old_monitor_must_pair_again(self):
        m = paired()
        token = m.cookies.get(live.COOKIE)

        class R:
            cookies = {live.COOKIE: token}
        import time
        self.assertIsNotNone(live.monitor_of(R()))
        live._seen.clear()
        self.assertIsNone(live.monitor_of(R(), now=time.time() + live.KEEP_DAYS * 86400 + 10))

    def test_monitor_name_checked(self):
        self.assertEqual(ADMIN.post("/api/admin/live/monitors", json={"name": "<b>x</b>"}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/live/monitors", json={"name": "x" * 31}).status_code, 400)

    def test_settings_validated(self):
        cfg = ADMIN.get("/api/config").json()
        for bad in ({"live": "ja"}, {"live_screens": 9}, {"live_screens": True}):
            c = json.loads(json.dumps(cfg))
            c.setdefault("logs", {}).update(bad)
            self.assertEqual(ADMIN.put("/api/config", json=c).status_code, 400, bad)


if __name__ == "__main__":
    unittest.main()


class SetUp(unittest.TestCase):
    """Dominik 2026-10-12: targets that are not set up are not on the picture at all (not even in "+ N ruhig")."""

    def setUp(self):
        reset()
        set_logs(live=True)
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            self.was = json.load(f)
        self.addCleanup(helpers.write_config, self.was)
        self.addCleanup(reset)

    def chat(self, **kw):
        c = json.loads(json.dumps(self.was))
        c.setdefault("chat", {}).update(kw)
        helpers.write_config(c)
        live._unset[0] = 0.0

    def ids(self):
        return {x["id"] for x in live.snapshot("admin", now=1000.0)["targets"]}

    def test_only_what_is_set_up(self):
        import profiles
        from unittest import mock
        # one profile of its own: others in the run may have a calendar.json, and alone there may be none
        uid = "u_livesetup01"
        p = mock.patch.object(profiles, "user_ids", return_value=[uid])
        p.start()
        self.addCleanup(p.stop)
        self.chat(search=False, calendar=True, mail=False, remarkable=False, homeassistant=False)
        ids = self.ids()
        self.assertIn("qwen", ids)
        for t in ("web", "mail", "rm", "push", "ha"):
            self.assertNotIn(t, ids, t)
        self.assertNotIn("cal", ids)          # switched on, but no profile has a calendar
        f = profiles._path(uid, "calendar.json")
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w") as fh:
            fh.write("{}")
        self.addCleanup(os.remove, f)
        self.chat(search=True, search_url="", calendar=True)
        ids = self.ids()
        self.assertIn("cal", ids)
        self.assertNotIn("web", ids)          # switched on, but no SearXNG address
        self.chat(search=True, search_url="http://127.0.0.1:9/", calendar=True)
        self.assertIn("web", self.ids())

    def test_used_shows_anyway_and_checks_are_cached(self):
        self.chat(search=False)
        self.assertNotIn("web", self.ids())
        r = live.begin("speaker", "Küche", t=999.0)
        r.now("tool", "web_search", 999.5)
        self.assertIn("web", {x["id"] for x in live.snapshot("admin", now=1000.0)["targets"]})
        live.end(r, True)
        # within 30 s the answer is the one remembered (no file reads every second)
        live._unset[:] = [5000.0, frozenset({"qwen"})]
        self.assertEqual(live.unset(5010.0), frozenset({"qwen"}))


class Proxy(unittest.TestCase):
    """Dominik 2026-10-12: a device over the reverse proxy (speech.…) shows under "Über das Internet", also when
    the proxy is not entered under panel.trusted_proxies; for decisions (the monitor) that header still does not count."""

    def req(self, peer, fwd=""):
        from starlette.requests import Request
        h = [(b"x-forwarded-for", fwd.encode())] if fwd else []
        return Request({"type": "http", "method": "GET", "path": "/", "headers": h, "client": (peer, 1), "query_string": b""})

    def test_shown_outside_but_not_trusted(self):
        set_proxies([])
        self.addCleanup(set_proxies, [])
        r = self.req("192.168.178.20", "89.204.1.2")
        self.assertTrue(live.shown_outside(r))
        self.assertFalse(live.from_internet(r))          # the decision keeps to the listed proxies
        self.assertEqual(live.short_ip(live.sender(r)), "89.204.x.x")
        self.assertFalse(live.shown_outside(self.req("192.168.178.20", "192.168.178.31")))
        self.assertFalse(live.shown_outside(self.req("192.168.178.20")))
        self.assertTrue(live.shown_outside(self.req("89.204.1.2")))
        reset()
        set_logs(live=True)
        rec = live.begin("desk", "PC", t=1000.0, request=r)
        self.assertTrue(rec.net)
        self.assertEqual(live.snapshot("admin", now=1001.0)["door"]["items"][0]["from"], "89.204.x.x")
        set_logs(live=False)
        reset()
