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
    with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
        json.dump(c, f)


def set_proxies(p):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c["panel"]["trusted_proxies"] = p
    with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
        json.dump(c, f)


def reset():
    with live._lock:
        live._run.clear(), live._events.clear(), live._guard.clear(), live._door.clear(), live._rets.clear()
        live._count.clear(), live._codes.clear(), live._seen.clear()
        live._saved[0] = 0.0
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
        self.assertEqual(ADMIN.get("/api/admin/live").status_code, 404)
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
        for m in extras.SERVICES:
            with open(m.__file__, encoding="utf-8") as f:
                names |= set(re.findall(r'"name": "([a-z_]+)"', f.read()))
        names -= {"parameters"}
        self.assertEqual(sorted(n for n in names if n not in live.TOOLS), [],
                         "a new tool: add it to live.TOOLS (and a target to live.TARGETS if it goes somewhere new)")
        for n, tgt in live.TOOLS.items():
            self.assertIn(tgt, live.TARGETS, n)
            self.assertIn(tgt, live.RETURNS, n)
        for k, v in live.TARGETS.items():
            self.assertIn(v[2], ("spark", "lan", "net"), k)
        # Dominik 2026-10-10: the web search asks search engines outside, pages from hits come from outside
        self.assertEqual((live.TARGETS["web"][2], live.TARGETS[live.TOOLS["read_page"]][2]), ("net", "net"))
        import tracelog as tl
        self.assertEqual(set(live.CLIENT) - {"other"}, set(tl.CLIENTS) - {"other"},
                         "a new kind of device: add a word to live.CLIENT")

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
