"""Plan „Vereinheitlichen“ (V01.0.267): one description per function in features.py, one check for
"Spark on, profile on", and every module, page and the app asking it instead of building its own."""
import ast
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import features  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(HERE, "..", "panel")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class Registry(unittest.TestCase):
    def test_every_admin_switch_belongs_to_one_function(self):
        with open(features.DEFAULTS) as f:
            chat = json.load(f)["chat"]
        used = {k for f in features.FEATURES for k in f.admin}
        for k, v in chat.items():
            if isinstance(v, bool):
                self.assertTrue(k in used or k in features.SPARK_ONLY, f"chat.{k}: add it to features.py")
        for k in used:
            self.assertIsInstance(chat.get(k), bool, k)

    def test_profile_switches_exist_and_start_off(self):
        for f in features.FEATURES:
            if f.profile:
                self.assertIn(f.profile, profiles.SETTINGS, f.key)
                self.assertIs(profiles.SETTINGS[f.profile][0], False, f.key)   # every function off until the profile says so
            if f.parent:
                self.assertIn(f.parent, features.BY_KEY, f.key)

    def test_every_switch_guide_has_a_function(self):
        with open(os.path.join(PANEL, "static", "js", "guides.js")) as f:
            js = f.read()
        guides = dict(re.findall(r"\{id:'([a-z0-9_]+)',grp:'[a-z]+'(?:,sw:'chat\.([a-z0-9_]+)')?", js))
        keys = {f.guide for f in features.FEATURES}
        for gid, sw in guides.items():
            if sw and sw not in ("public",):
                self.assertIn(gid, keys, f"guide {gid} (chat.{sw}) has no function in features.py")
        for f in features.FEATURES:
            self.assertIn(f.guide, guides, f.key)

    def test_no_module_builds_its_own_check(self):
        """admin_on / profile_on / usable / allowed / enabled ask features.py; reading chat.* there is not allowed."""
        own = {("netguard.py", "allowed"), ("wyoming.py", "allowed"), ("mfa.py", "enabled"), ("coadmin.py", "on"),
               ("tracelog.py", "on"), ("lokal.py", "on"), ("roles.py", "on"), ("wissen.py", "due_on"), ("telegram.py", "push_on"),
               ("iphone.py", "area_on"), ("images.py", "allowed"), ("agent.py", "level")}
        for fn in sorted(os.listdir(PANEL)):
            if not fn.endswith(".py") or fn == "features.py":
                continue
            with open(os.path.join(PANEL, fn)) as f:
                tree = ast.parse(f.read())
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name in ("admin_on", "profile_on", "usable", "allowed", "enabled") \
                        and (fn, node.name) not in own:
                    src = ast.unparse(node)
                    self.assertIn("features.", src, f"{fn}:{node.name} must ask features.py")


class Check(unittest.TestCase):
    def tearDown(self):
        helpers.set_config(weather=False, mail=False, parcels=False, memory=True, learn_fixes=False, room=False,
                           room_remote=False, esp32=False, iphone=False, iphone_push=False, search=False)

    def test_spark_profile_and_guest(self):
        _, uid = profile("FeaWera")
        helpers.set_config(weather=False)
        self.assertEqual(features.reason("weather", uid), "spark")
        helpers.set_config(weather=True)
        self.assertEqual(features.reason("weather", uid), "profile")   # off until the profile says so
        profiles.save_settings(uid, {"wx_on": True})
        self.assertIsNone(features.reason("weather", uid))
        self.assertEqual(features.reason("weather", None), "guest")
        helpers.set_config(search=True)
        self.assertIsNone(features.reason("search", None))             # guests may search the web

    def test_what_a_function_builds_on(self):
        _, uid = profile("FeaXaver")
        profiles.save_settings(uid, {"par_on": True, "fix_learn": True, "room_remote": True, "app_push": True, "app_on": True})
        helpers.set_config(mail=False, parcels=True)
        self.assertFalse(features.allowed("parcels", uid))
        helpers.set_config(mail=True)
        self.assertTrue(features.allowed("parcels", uid))
        # learning from corrections needs the memory (the page said so, the check did not: V01.0.267)
        helpers.set_config(learn_fixes=True, memory=False)
        self.assertFalse(features.allowed("fixes", uid))
        import fixes
        self.assertFalse(fixes.on(features.chat_cfg(), profiles.settings(uid)))
        helpers.set_config(memory=True)
        self.assertTrue(fixes.on(features.chat_cfg(), profiles.settings(uid)))
        # room mode from afar needs own speakers; push needs the app
        helpers.set_config(room=True, room_remote=True, esp32=False)
        self.assertFalse(features.admin_on("roomfar"))
        helpers.set_config(iphone=False, iphone_push=True)
        import apns
        self.assertFalse(apns.admin_on())

    def test_panel_and_app_agree(self):
        """The same switch shows the same in the browser and in the app (they differed for 'routing')."""
        helpers.set_config(routing="yes")    # a value that is not true/false: off everywhere
        self.assertFalse(features.admin_on("routing"))
        helpers.set_config(routing=False)


class Api(unittest.TestCase):
    def test_profile_sees_why(self):
        c, uid = profile("FeaYvonne")
        helpers.set_config(weather=True, transit=False)
        d = c.get("/api/features").json()
        f = {x["key"]: x for x in d["features"]}
        self.assertEqual(f["weather"]["why"], "profile")
        self.assertEqual(f["transit"]["why"], "spark")
        self.assertIs(f["weather"]["mine"], False)
        self.assertEqual(d["why"]["spark"][0], "Vom Admin ausgeschaltet")
        self.assertEqual(len(d["groups"]), 7)
        helpers.set_config(weather=False)

    def test_guests_see_only_guest_functions(self):
        helpers.set_config(public=True)
        try:
            d = TestClient(panel.app).get("/api/features").json()
            self.assertTrue(d["features"])
            self.assertTrue(all(x["guests"] for x in d["features"]))
            self.assertTrue(all(x["mine"] is None for x in d["features"]))
        finally:
            helpers.set_config(public=False)
        self.assertEqual(TestClient(panel.app).get("/api/features").status_code, 401)

    def test_whoami_flags_come_from_here(self):
        helpers.set_config(mail=False, parcels=True)
        self.assertFalse(TestClient(panel.app).get("/api/whoami").json()["parcels"])
        helpers.set_config(mail=True)
        self.assertTrue(TestClient(panel.app).get("/api/whoami").json()["parcels"])
        helpers.set_config(mail=False, parcels=False)


class Values(unittest.TestCase):
    """Phase 2 (V01.0.268): defaults in one place, one mix of presets and own values."""
    def test_missing_keys_get_the_shipped_default(self):
        import common
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            saved = f.read()
        try:
            c = json.loads(saved)
            c["chat"].pop("weather", None)
            c["chat"].setdefault("defaults", {}).pop("length", None)
            with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
                json.dump(c, f)
            got = common.load_config()
            self.assertIs(got["chat"]["weather"], False)
            self.assertEqual(got["chat"]["defaults"]["length"], common.shipped()["chat"]["defaults"]["length"])
            self.assertEqual(got["chat"]["defaults"].get("hands"), c["chat"]["defaults"].get("hands", False))
        finally:
            with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
                f.write(saved)

    def test_effective_mixes_presets_and_own(self):
        _, uid = profile("FeaZora")
        chat = {"defaults": {"length": "short", "style": "nie übernehmen"}}
        self.assertEqual(profiles.effective(uid, chat)["length"], "short")
        self.assertEqual(profiles.effective(uid, chat)["style"], "")          # the tone is the profile's own
        profiles.save_settings(uid, {"length": "long"})
        self.assertEqual(profiles.effective(uid, chat)["length"], "long")
        self.assertEqual(profiles.effective(None, chat)["length"], "short")   # guests: the presets

    def test_no_second_place_for_defaults(self):
        """No module merges the shipped defaults or the presets by hand, and no code default disagrees."""
        import common
        chat = common.shipped()["chat"]
        for fn in sorted(os.listdir(PANEL)):
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(PANEL, fn)) as f:
                src = f.read()
            self.assertNotRegex(src, r'dict\(json\.load\([^)]*\)\)?\["chat"\], \*\*', fn)
            if fn != "profiles.py":
                self.assertNotIn("dict(profiles.defaults(", src, fn)
            for k, d in re.findall(r'\.get\("chat", \{\}\)\.get\("([a-z_0-9]+)", ([^()]+?)\)', src):
                if k in chat and isinstance(chat[k], (bool, int, float, str)):
                    try:
                        val = ast.literal_eval(d)
                    except ValueError:
                        continue
                    self.assertEqual(val, chat[k], f"{fn}: chat.{k} default {d} differs from config.default.json")


class Matrix(unittest.TestCase):
    """Phase 3 (V01.0.269): Funktionen → Wer darf was."""
    def test_matrix_and_switching_a_profile(self):
        _, uid = profile("FeaAnton")
        helpers.set_config(weather=True)
        d = ADMIN.get("/api/admin/features").json()
        row = next(f for f in d["features"] if f["key"] == "weather")
        self.assertIs(row["cells"][uid], False)
        self.assertTrue(row["switchable"])
        self.assertTrue(row["seen"])                                    # on now, so no longer "new"
        self.assertTrue(any(p["id"] == uid for p in d["profiles"]))
        self.assertIsNone(next(f for f in d["features"] if f["key"] == "memory")["cells"])   # no own switch
        r = ADMIN.put(f"/api/admin/features/weather/profiles/{uid}", json={"on": True})
        self.assertEqual(r.status_code, 200)
        self.assertIs(profiles.settings(uid)["wx_on"], True)
        prot = ADMIN.get("/api/admin/protocol?limit=50").json()["events"]
        self.assertTrue(any(x.get("event") == "feature_profile" and "FeaAnton" in x.get("detail", "") for x in prot))
        helpers.set_config(weather=False)

    def test_refuses_what_is_not_there(self):
        _, uid = profile("FeaBerta")
        for path, body, code in ((f"/api/admin/features/memory/profiles/{uid}", {"on": True}, 404),      # no own switch
                                 ("/api/admin/features/weather/profiles/u_000000000000", {"on": True}, 404),
                                 (f"/api/admin/features/nothing/profiles/{uid}", {"on": True}, 404),
                                 (f"/api/admin/features/weather/profiles/{uid}", {"on": "yes"}, 400),
                                 (f"/api/admin/features/weather/profiles/{uid}", "x" * 300, 413)):
            r = ADMIN.put(path, content=body) if isinstance(body, str) else ADMIN.put(path, json=body)
            self.assertEqual(r.status_code, code, path)

    def test_only_admins(self):
        c, uid = profile("FeaCarl")
        self.assertEqual(TestClient(panel.app).get("/api/admin/features").status_code, 401)
        self.assertIn(c.get("/api/admin/features").status_code, (401, 403))
        self.assertIn(c.put(f"/api/admin/features/weather/profiles/{uid}", json={"on": True}).status_code, (401, 403))
        self.assertNotEqual(profiles.settings(uid).get("wx_on"), True)

    def test_new_until_first_on(self):
        helpers.set_config(transit=False)
        rows = {f["key"]: f for f in ADMIN.get("/api/admin/features").json()["features"]}
        if not rows["transit"]["seen"]:
            helpers.set_config(transit=True)
            rows = {f["key"]: f for f in ADMIN.get("/api/admin/features").json()["features"]}
            self.assertTrue(rows["transit"]["seen"])
            helpers.set_config(transit=False)
            rows = {f["key"]: f for f in ADMIN.get("/api/admin/features").json()["features"]}
            self.assertTrue(rows["transit"]["seen"])                  # stays known once it was on
        self.assertIn("features-seen.json", __import__("backup").STATE_FILES)


class Presets(unittest.TestCase):
    """Phase 4 (V01.0.270): presets for new profiles, never a preset that fakes a function switch."""
    def test_new_profiles_get_what_the_admin_chose(self):
        self.assertEqual(ADMIN.put("/api/admin/features/weather/new", json={"on": True}).status_code, 200)
        try:
            _, uid = profile("FeaDora")
            self.assertIs(profiles.settings(uid).get("wx_on"), True)
            row = next(f for f in ADMIN.get("/api/admin/features").json()["features"] if f["key"] == "weather")
            self.assertIs(row["new"], True)
        finally:
            ADMIN.put("/api/admin/features/weather/new", json={"on": False})
        _, uid = profile("FeaEmil")
        self.assertIsNone(profiles.settings(uid).get("wx_on"))
        self.assertEqual(ADMIN.put("/api/admin/features/memory/new", json={"on": True}).status_code, 404)   # no own switch
        self.assertEqual(TestClient(panel.app).put("/api/admin/features/weather/new", json={"on": True}).status_code, 401)

    def test_config_check(self):
        cfg = ADMIN.get("/api/config").json()
        for bad in (["nothing"], ["memory"], ["weather", "weather"], "weather"):
            cfg["chat"]["new_profile_on"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400, bad)

    def test_presets_never_switch_a_function_on(self):
        _, uid = profile("FeaFrida")
        chat = {"defaults": {"route": True, "wx_on": True, "length": "short", "echo": False}}
        eff = profiles.effective(uid, chat)
        self.assertIs(eff["route"], False)          # the Wer-darf-was switch, not a preset
        self.assertIs(eff["wx_on"], False)
        self.assertEqual(eff["length"], "short")
        self.assertIs(eff["echo"], False)           # no function switch of its own: a preset is fine


if __name__ == "__main__":
    unittest.main()
