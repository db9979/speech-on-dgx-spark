"""Follow-up without the wake word (chat.follow_up, per profile "follow"): off by default, only for
signed-in profiles, only fixed durations, and the browser only opens the microphone after a spoken
question, never for guests, typed questions or room mode.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
JS = os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js")


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def read(name):
    with open(os.path.join(JS, name), encoding="utf-8") as f:
        return f.read()


class FollowUp(unittest.TestCase):
    def tearDown(self):
        helpers.set_config(follow_up=False)

    def test_off_by_default_and_only_for_profiles(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["follow_up"], False)
        self.assertEqual(profiles.SETTINGS["follow"][0], "0")
        a = profile("Fia")
        self.assertFalse(a.get("/api/profile/settings").json()["allow"]["follow"])
        helpers.set_config(follow_up=True)
        self.assertTrue(a.get("/api/profile/settings").json()["allow"]["follow"])
        g = TestClient(panel.app).get("/api/profile/settings")   # a guest: no access, or never allowed
        self.assertFalse(g.status_code == 200 and g.json()["allow"]["follow"])
        helpers.set_config(public=True)
        try:
            self.assertFalse(TestClient(panel.app).get("/api/profile/settings").json()["allow"]["follow"])
        finally:
            helpers.set_config(public=False)

    def test_only_fixed_durations(self):
        a = profile("Fia")
        self.assertEqual(a.put("/api/profile/settings", json={"follow": "6"}).json()["settings"]["follow"], "6")
        for bad in ("3", "60", 6, True, "6; rm -rf", None):
            got = a.put("/api/profile/settings", json={"follow": bad}).json()["settings"]["follow"]
            self.assertEqual(got, "6", bad)
        self.assertEqual(a.put("/api/profile/settings", json={"follow": "0"}).json()["settings"]["follow"], "0")

    def test_admin_switch_must_be_bool(self):
        cfg = ADMIN.get("/api/config").json()
        new = json.loads(json.dumps(cfg))
        new["chat"]["follow_up"] = "ja"
        self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 400)

    def test_browser_opens_only_after_spoken_question(self):
        js = read("chat.js")
        fn = js[js.index("function followSecs()"):]
        fn = fn[:fn.index("\n", fn.index("return"))]
        for need in ("ALLOW.follow", "!guest", "room.on", "document.hidden", "[4,6,8,10].includes(s)"):
            self.assertIn(need, fn, need)
        self.assertIn("else if(spoken&&followSecs())startListening({follow:followSecs()})", js)
        self.assertRegex(js, r"async function ask\(text,asrS,spk\)\{const spoken=!!chat\.nextSpoken;chat\.nextSpoken=false;")
        # spoken: after speech recognition and after "Hey Spark, …"; typed questions reset it
        self.assertEqual(len(re.findall(r"chat\.nextSpoken=true;ask\(", js)), 2)
        self.assertIn("chat.nextSpoken=false;ask(x,null)", read("users.js"))
        # the follow-up ends after its own seconds of silence, not the 8 s of a tapped recording
        self.assertIn("now-t0>(o.follow?o.follow*1000:8000)", js)


if __name__ == "__main__":
    unittest.main()
