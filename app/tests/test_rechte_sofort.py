"""Rights arrive at once (V01.0.388): what the admin sets under Funktionen → Wer darf was reaches the profile
on every way without reloading by hand: the pages see a new fingerprint (features.stamp in /api/whoami and
/api/features) and reload, the iPhone app asks again on coming to the front and every minute, a device key
whose function is off answers "not now" (503) and keeps its pairing, and new profiles by invitation may use what
the admin released at once (Freigabe vereinfachen, Dominik 2026-10-13). Speakers, the Begleiter and MCP have their own tests (test_esp32,
test_begleiter, test_mcpserver)."""
import os
import re
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402
import guard  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
JS = os.path.join(HERE, "..", "panel", "static", "js")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


class Stamp(unittest.TestCase):
    def setUp(self):
        for k in [k for k in guard._rate if k[0] == "features"]:
            guard._rate.pop(k, None)

    def test_admin_switches_change_the_profiles_fingerprint(self):
        helpers.set_config(weather=True)
        try:
            c, uid = profile("RsAnna")
            first = c.get("/api/whoami").json()["rights"]
            self.assertRegex(first, r"^[0-9a-f]{16}$")
            self.assertEqual(c.get("/api/features").json()["stamp"], first)    # one fingerprint for page and app
            self.assertEqual(c.get("/api/whoami").json()["rights"], first)     # stable while nothing changes
            # the admin blocks the function for this profile under Wer darf was
            self.assertEqual(ADMIN.put(f"/api/admin/features/weather/profiles/{uid}", json={"on": False}).status_code, 200)
            second = c.get("/api/whoami").json()["rights"]
            self.assertNotEqual(second, first)
            # and allows it again
            self.assertEqual(ADMIN.put(f"/api/admin/features/weather/profiles/{uid}", json={"on": True}).status_code, 200)
            self.assertEqual(c.get("/api/whoami").json()["rights"], first)
            # the profile switches a preference off
            helpers.set_config(proactive=True)
            third = c.get("/api/whoami").json()["rights"]
            profiles.save_settings(uid, {"pro_on": False})
            self.assertNotEqual(c.get("/api/whoami").json()["rights"], third)
            second = c.get("/api/whoami").json()["rights"]
            # the admin turns the function off for the whole Spark
            helpers.set_config(weather=False)
            self.assertNotEqual(c.get("/api/whoami").json()["rights"], second)
        finally:
            ADMIN.put(f"/api/admin/features/weather/profiles/{uid}", json={"on": True})
            helpers.set_config(weather=False, proactive=False)

    def test_one_profile_does_not_change_the_other(self):
        helpers.set_config(weather=True)
        try:
            a, _ = profile("RsBert")
            _, uid_b = profile("RsCora")
            before = a.get("/api/whoami").json()["rights"]
            ADMIN.put(f"/api/admin/features/weather/profiles/{uid_b}", json={"on": False})
            self.assertEqual(a.get("/api/whoami").json()["rights"], before)
        finally:
            ADMIN.put(f"/api/admin/features/weather/profiles/{uid_b}", json={"on": True})
            helpers.set_config(weather=False)

    def test_fingerprint_shows_no_content(self):
        st = features.stamp(None)
        self.assertRegex(st, r"^[0-9a-f]{16}$")
        self.assertEqual(st, features.stamp(None))


class Pages(unittest.TestCase):
    def test_open_pages_look_every_minute_and_on_coming_back(self):
        base = read(JS, "base.js")
        self.assertIn("k==='rights'", base)                                  # the fingerprint counts as a flag
        self.assertIn("setInterval(verCheck,60e3)", base)
        self.assertRegex(base, r"async function verCheck\(\)\{[^\n]*\n[^\n]*\n[^\n]*flagsAway\(w\)")
        # never mid-conversation or while typing: the same calm rules as a new version
        self.assertRegex(base, r"function flagsAway\(w\)\{[^\n]*\n(?:[^\n]*\n)?[^\n]*sparkBusy\(\)&&now-verWatch\.edit>600e3")
        self.assertIn("'away'", read(JS, "start.js"))

    def test_iphone_app_asks_again_in_front(self):
        if not os.path.isdir(os.path.join(ROOT, "ios")):
            self.skipTest("ios/ is not in an app/-only copy")
        sw = read(ROOT, "ios", "Spark", "Assistant.swift")
        self.assertIn("private func rightsCheck() async", sw)
        scene = sw[sw.index("func scene("):sw.index("func settingsChanged(")]
        self.assertIn("rightsCheck()", scene)
        tick = sw[sw.index("private func tick()"):sw.index("// ---------------------------------------------------------------- resting state")]
        self.assertIn("rightsCheck()", tick)
        check = sw[sw.index("private func rightsCheck() async"):sw.index("private var ticks")]
        self.assertIn("base()", check)                                         # the wake word follows at once
        self.assertIn("struct Allowed: Equatable", read(ROOT, "ios", "Shared", "SparkAPI.swift"))


class DeviceKeys(unittest.TestCase):
    def test_switched_off_function_answers_not_now_unknown_key_pair_again(self):
        import core
        from starlette.requests import Request
        from fastapi import HTTPException

        def req(closed):
            r = Request({"type": "http", "method": "GET", "path": "/api/x", "headers": [], "query_string": b""})
            if closed:
                r.scope["speech_gate_closed"] = closed
            return r
        helpers.set_config(public=False)
        for closed, code, start in (("off", 503, "Für dieses Gerät"), ("notaus", 503, "Mein Notaus"), (None, 401, "")):
            with self.assertRaises(HTTPException) as e:
                core.assistant(req(closed), None)
            self.assertEqual(e.exception.status_code, code)
            self.assertTrue(str(e.exception.detail).startswith(start))
        src = read(HERE, "..", "panel", "profiles.py")
        body = src[src.index("    token = request.headers.get(DEVICE_HEADER"):src.index("        _note_device(dev[\"id\"], request)")]
        self.assertEqual(len(re.findall(r"_GATE\[0\]\(dev\[\"user\"\]\):\n\s+return _gate_closed\(request\)", body)), 7)   # V01.0.646: +1 terminal (tui)


class NewProfiles(unittest.TestCase):
    def test_invited_profiles_get_what_is_released_at_once(self):
        import join
        helpers.set_config(weather=True, mfa=False)
        try:
            self.assertEqual(ADMIN.put("/api/admin/join", json={"mode": "invite", "mfa": "off"}).status_code, 200)
            r = ADMIN.post("/api/admin/join/invites", json={"name": "", "days": 7, "base": "https://spark.example"})
            self.assertEqual(r.status_code, 200, r.text)
            code = r.json()["link"].split("#join=", 1)[1]
            uid, _ = join.create_profile(code, "Rs Neu", "123456")
            self.assertTrue(features.allowed("weather", uid))      # nothing to switch on for the new profile
            self.assertNotIn("wx_on", profiles.settings(uid))
        finally:
            ADMIN.put("/api/admin/join", json={"mode": "off"})
            helpers.set_config(weather=False)


if __name__ == "__main__":
    unittest.main()
