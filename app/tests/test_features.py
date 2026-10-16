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


def block(test, key, uid, on=False):
    """The admin blocks (on=False) or allows again (on=True) a function for one profile: Personen und Geräte → Gesperrte Funktionen."""
    r = ADMIN.put(f"/api/admin/features/{key}/profiles/{uid}", json={"on": on})
    test.assertEqual(r.status_code, 200, r.text)
    if not on:
        test.addCleanup(ADMIN.put, f"/api/admin/features/{key}/profiles/{uid}", json={"on": True})
    return r


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

    def test_preferences_exist_start_on_and_are_no_preset(self):
        """Freigabe vereinfachen (Dominik 2026-10-13): a profile switches nothing on. Only where the Spark does
        something unasked it keeps a preference: in profiles.SETTINGS, on unless the profile switched it off, and
        never set by the admin's presets."""
        prefs = [f for f in features.FEATURES if f.pref]
        self.assertTrue(prefs)
        for f in prefs:
            self.assertIn(f.pref, profiles.SETTINGS, f.key)
            self.assertIs(profiles.SETTINGS[f.pref][0], True, f.key)          # missing = on
            self.assertIn(f.pref, profiles.NO_PRESET, f.key)
        self.assertEqual(features.PREFS, {f.pref for f in prefs})
        for f in features.FEATURES:
            self.assertFalse(hasattr(f, "profile"), "no per-profile release switch any more")
            if f.parent:
                self.assertIn(f.parent, features.BY_KEY, f.key)

    def test_every_preference_can_be_set_in_ich(self):
        """Dominik 2026-10-13: "Bilder aus dem Kiwix" was on for the admin but missing in Ich → Dokumente. Every
        preference of a function has a toggle on the Ich pages; Ich → Dokumente names it in DOCSW (me.js),
        and /api/profile/wissen reports it."""
        import wissen
        js = os.path.join(PANEL, "static", "js")
        src = "".join(open(os.path.join(js, n), encoding="utf-8").read() for n in os.listdir(js)
                      if n.endswith(".js") and n not in ("i18n.js", "guides.js"))
        src += open(os.path.join(PANEL, "static", "index.html"), encoding="utf-8").read()
        me = open(os.path.join(js, "me.js"), encoding="utf-8").read()
        doc = set(re.findall(r"\['(\w+)',t\(", me[me.index("const DOCSW"):me.index("const DOCSRC")]))
        for f in features.FEATURES:
            if not f.pref:
                continue
            if f.me == "docbox":
                word = f.pref[4:]
                self.assertIn(word, doc, f"{f.key}: add '{word}' to DOCSW in me.js")
                self.assertEqual(wissen.DOC_FEATURE.get(word), f.key, f"{f.key}: add '{word}' to wissen.DOC_FEATURE")
            else:
                self.assertTrue(f'"{f.pref}"' in src or f"'{f.pref}'" in src, f"{f.key}: no toggle for {f.pref}")

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
        self.assertIsNone(features.reason("weather", uid))               # released by the admin: works at once
        block(self, "weather", uid)
        self.assertEqual(features.reason("weather", uid), "blocked")     # the admin blocked it for this profile
        self.assertFalse(features.allowed("weather", uid))
        block(self, "weather", uid, on=True)
        self.assertIsNone(features.reason("weather", uid))
        self.assertEqual(features.reason("weather", None), "guest")
        helpers.set_config(search=True)
        self.assertEqual(features.reason("search", None), "guest")      # guests get no function, not even the search

    def test_what_a_function_builds_on(self):
        _, uid = profile("FeaXaver")
        helpers.set_config(mail=False, parcels=True)
        self.assertFalse(features.allowed("parcels", uid))
        helpers.set_config(mail=True)
        self.assertTrue(features.allowed("parcels", uid))
        # learning from corrections needs the memory (the page said so, the check did not: V01.0.267)
        helpers.set_config(learn_fixes=True, memory=False)
        self.assertFalse(features.allowed("fixes", uid))
        self.assertFalse(features.allowed("fixes", uid, features.chat_cfg()))
        helpers.set_config(memory=True)
        self.assertTrue(features.allowed("fixes", uid, features.chat_cfg()))
        self.assertFalse(features.allowed("fixes", None, features.chat_cfg()))   # never for guests
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
        helpers.set_config(weather=True, transit=False, proactive=True, search=True)
        self.addCleanup(helpers.set_config, weather=False, proactive=False, search=False)
        block(self, "search", uid)
        d = c.get("/api/features").json()
        f = {x["key"]: x for x in d["features"]}
        self.assertIsNone(f["weather"]["why"])                          # released: works at once
        self.assertIs(f["weather"]["can"], True)
        self.assertIsNone(f["weather"]["mine"])                         # no preference of its own
        self.assertEqual(f["transit"]["why"], "spark")
        self.assertEqual(f["search"]["why"], "blocked")
        self.assertIs(f["proactive"]["mine"], True)                     # a preference: on unless switched off
        profiles.save_settings(uid, {"pro_on": False})
        f = {x["key"]: x for x in c.get("/api/features").json()["features"]}
        self.assertEqual(f["proactive"]["why"], "profile")
        self.assertIs(f["proactive"]["mine"], False)
        self.assertEqual(d["why"]["spark"][0], "Vom Admin ausgeschaltet")
        self.assertEqual(d["why"]["blocked"][0], "Vom Admin für dich gesperrt")
        self.assertEqual(len(d["groups"]), 8)

    def test_guests_see_no_functions(self):
        helpers.set_config(public=True, search=True, reminders=True)
        try:
            d = TestClient(panel.app).get("/api/features").json()
            self.assertEqual(d["features"], [])                          # only questions and answers
            self.assertTrue(d["groups"])
            self.assertFalse(any(f.key for f in features.FEATURES if features.allowed(f.key, None)))
            self.assertFalse(hasattr(features.FEATURES[0], "guests"))     # no function may open itself to guests
        finally:
            helpers.set_config(public=False, search=False, reminders=True)
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
            helpers.write_config(c)
            got = common.load_config()
            self.assertIs(got["chat"]["weather"], False)
            self.assertEqual(got["chat"]["defaults"]["length"], common.shipped()["chat"]["defaults"]["length"])
            self.assertEqual(got["chat"]["defaults"].get("hands"), c["chat"]["defaults"].get("hands", False))
        finally:
            helpers.write_config(json.loads(saved))

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
    """Phase 3 (V01.0.269): Personen und Geräte → Gesperrte Funktionen."""
    def test_matrix_and_switching_a_profile(self):
        _, uid = profile("FeaAnton")
        helpers.set_config(weather=True)
        self.addCleanup(helpers.set_config, weather=False)
        d = ADMIN.get("/api/admin/features").json()
        row = next(f for f in d["features"] if f["key"] == "weather")
        self.assertIs(row["cells"][uid], True)                          # released: every profile may use it
        # only what its readers use (Gesperrte Funktionen, Wer darf es, needs.js, the tiles, the iPhone app): no Spark column,
        # no filters since Dominik 2026-10-14 ("Verschlanken")
        self.assertEqual(set(row), {"key", "name", "switch", "spark", "blockable", "cells", "inherited", "chain"})
        self.assertEqual(set(d), {"features", "profiles", "states", "snames"})
        self.assertTrue(any(p["id"] == uid for p in d["profiles"]))
        self.assertIs(next(f for f in d["features"] if f["key"] == "memory")["cells"][uid], True)
        block(self, "weather", uid)
        self.assertNotIn("wx_on", profiles.settings(uid))               # stored with the admin, not the profile
        self.assertIn(uid, features.chat_cfg()["deny"]["weather"])
        row = next(f for f in ADMIN.get("/api/admin/features").json()["features"] if f["key"] == "weather")
        self.assertIs(row["cells"][uid], False)
        prot = ADMIN.get("/api/admin/protocol?limit=50").json()["events"]
        self.assertTrue(any(x.get("event") == "feature_profile" and "FeaAnton" in x.get("detail", "") for x in prot))

    def test_refuses_what_is_not_there(self):
        _, uid = profile("FeaBerta")
        for path, body, code in (("/api/admin/features/weather/profiles/u_000000000000", {"on": True}, 404),
                                 ("/api/admin/features/weather/profiles/nobody", {"on": True}, 404),
                                 (f"/api/admin/features/nothing/profiles/{uid}", {"on": True}, 404),
                                 (f"/api/admin/features/weather/profiles/{uid}", {"on": "yes"}, 400),
                                 (f"/api/admin/features/weather/profiles/{uid}", {}, 400),
                                 (f"/api/admin/features/weather/profiles/{uid}", "x" * 300, 413)):
            r = ADMIN.put(path, content=body) if isinstance(body, str) else ADMIN.put(path, json=body)
            self.assertEqual(r.status_code, code, path)
        self.assertNotIn(uid, json.dumps(features.chat_cfg().get("deny") or {}))

    def test_only_admins(self):
        c, uid = profile("FeaCarl")
        self.assertEqual(TestClient(panel.app).get("/api/admin/features").status_code, 401)
        self.assertIn(c.get("/api/admin/features").status_code, (401, 403))
        self.assertIn(c.put(f"/api/admin/features/weather/profiles/{uid}", json={"on": False}).status_code, (401, 403))
        self.assertNotIn(uid, json.dumps(features.chat_cfg().get("deny") or {}))

    def test_first_on_recorded(self):
        """tipps.py shows „neu freigegeben“ from the time a function was first on; it stays known once it was on."""
        helpers.set_config(transit=False)
        self.addCleanup(helpers.set_config, transit=False)
        if "transit" not in features._seen(features.chat_cfg()):
            helpers.set_config(transit=True)
            self.assertIn("transit", features._seen(features.chat_cfg()))
            helpers.set_config(transit=False)
            self.assertIn("transit", features._seen(features.chat_cfg()))     # stays known once it was on
        self.assertIn("features-seen.json", __import__("backup").STATE_FILES)


class Presets(unittest.TestCase):
    """Phase 4 (V01.0.270), since Freigabe vereinfachen (Dominik 2026-10-13): no presets for new profiles any more,
    what the admin releases holds for every profile, old and new; never a preset that fakes a function."""
    def test_new_profiles_get_what_the_admin_released(self):
        self.assertIn(ADMIN.put("/api/admin/features/weather/new", json={"on": True}).status_code, (404, 405))
        self.assertFalse(hasattr(features, "new_profile"))
        helpers.set_config(weather=True)
        self.addCleanup(helpers.set_config, weather=False)
        _, uid = profile("FeaDora")
        self.assertTrue(features.allowed("weather", uid))               # no switch of its own needed
        self.assertEqual(profiles.settings(uid), {})                    # nothing written for it
        self.assertNotIn("new", next(f for f in ADMIN.get("/api/admin/features").json()["features"]
                                     if f["key"] == "weather"))

    def test_config_check(self):
        cfg = ADMIN.get("/api/config").json()
        self.assertNotIn("new_profile_on", cfg["chat"])
        for bad in (["weather"], ["nothing"], "weather"):             # the removed key is refused, whatever it holds
            c = json.loads(json.dumps(cfg))
            c["chat"]["new_profile_on"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=c).status_code, 400, bad)
        for bad in ({"weather": ["nobody"]}, {"weather": "u_000000000000"}, ["weather"]):
            c = json.loads(json.dumps(cfg))
            c["chat"]["deny"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=c).status_code, 400, bad)

    def test_a_removed_function_in_the_list_never_blocks_saving(self):
        """V01.0.491: "messages" (removed in .488) or one without an own switch any more stayed in new_profile_on,
        and every admin switch failed with "new_profile_on: functions with an own switch, each once". With
        "Freigabe vereinfachen" new_profile_on is gone altogether: an old entry is dropped, saving works."""
        helpers.set_config(new_profile_on=["messages", "rmaufgaben", "weather"])
        try:
            self.assertNotIn("new_profile_on", ADMIN.get("/api/config").json()["chat"])
            r = ADMIN.put("/api/admin/switches", json={"key": "weather", "on": False})
            self.assertEqual(r.status_code, 200, r.text)
            cfg = ADMIN.get("/api/config").json()
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 200)
            with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
                self.assertNotIn("new_profile_on", json.load(f)["chat"])
        finally:
            with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
                left = json.load(f)
            left["chat"].pop("new_profile_on", None)
            helpers.write_config(left)

    def test_a_gone_setting_in_the_presets_never_blocks_saving(self):
        """V01.0.494: a preset whose setting no longer exists (or no longer takes that value) stayed in chat.defaults,
        and every admin switch failed with "chat defaults: invalid value"."""
        helpers.set_config(defaults={"msg_gone_since_488": True, "length": "short", "echo": "kaputt"},
                           messages_voice=True, berater_off=["gone_melder"])
        with open(helpers.APP + "/config.default.json") as f:
            want = dict(json.load(f)["chat"]["defaults"], length="short")     # the shipped presets fill the rest
        try:
            self.assertEqual(ADMIN.get("/api/config").json()["chat"]["defaults"], want)
            r = ADMIN.put("/api/admin/switches", json={"key": "weather", "on": False})
            self.assertEqual(r.status_code, 200, r.text)
            with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
                stored = json.load(f)["chat"]
            self.assertEqual(stored["defaults"], want)
            self.assertNotIn("messages_voice", stored)                   # a switch removed in V01.0.488
            self.assertEqual(stored["berater_off"], [])
            cfg = ADMIN.get("/api/config").json()
            cfg["chat"]["defaults"] = {"nothing": 1}
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)
            cfg["chat"]["defaults"] = {"length": "short"}
            cfg["chat"]["gone_since_long"] = True
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)    # what the admin sends: still strict
        finally:
            helpers.set_config(defaults={}, berater_off=[])

    def test_presets_never_switch_a_function_on(self):
        _, uid = profile("FeaFrida")
        chat = {"defaults": {"route": True, "wx_on": True, "pro_on": False, "length": "short", "echo": False}}
        eff = profiles.effective(uid, chat)
        self.assertNotIn("route", eff)               # removed release switches: no preset either
        self.assertNotIn("wx_on", eff)
        self.assertIs(eff["pro_on"], True)           # a preference stays the profile's own, never a preset
        self.assertEqual(eff["length"], "short")
        self.assertIs(eff["echo"], False)            # no function switch of its own: a preset is fine


class Release(unittest.TestCase):
    """Freigabe vereinfachen (Dominik 2026-10-13): the admin releases a function for every profile at once and
    only blocks single profiles; profiles keep a preference only where the Spark does something unasked."""
    def tearDown(self):
        helpers.set_config(weather=False, mail=False, parcels=False, proactive=False)

    def test_release_works_for_every_profile_at_once(self):
        _, a = profile("RelAda")
        _, b = profile("RelBen")
        sa, sb = profiles.settings(a), profiles.settings(b)
        helpers.set_config(weather=False)
        self.assertFalse(features.allowed("weather", a))
        self.assertFalse(features.allowed("weather", b))
        helpers.set_config(weather=True)
        self.assertTrue(features.allowed("weather", a))
        self.assertTrue(features.allowed("weather", b))
        self.assertEqual((profiles.settings(a), profiles.settings(b)), (sa, sb))   # nothing touched at the profiles

    def test_admin_blocks_one_profile_and_the_chain(self):
        c, uid = profile("RelCleo")
        _, other = profile("RelDirk")
        helpers.set_config(mail=True, parcels=True)
        self.assertTrue(features.allowed("parcels", uid))
        block(self, "mail", uid)
        self.assertEqual(features.reason("mail", uid), "blocked")
        self.assertEqual(features.reason("parcels", uid), "blocked")    # builds on mail: blocked through the chain
        self.assertTrue(features.allowed("parcels", other))             # only this profile
        row = next(f for f in ADMIN.get("/api/admin/features").json()["features"] if f["key"] == "parcels")
        self.assertIs(row["cells"][uid], True)                          # not blocked itself ...
        self.assertIs(row["inherited"][uid], True)                      # ... but through mail
        # the profile cannot lift it: not through the admin route, not through its settings, not through the config
        self.assertIn(c.put(f"/api/admin/features/mail/profiles/{uid}", json={"on": True}).status_code, (401, 403))
        c.put("/api/profile/settings", json={"deny": {}, "mail": True})
        self.assertIn(c.put("/api/config", json={"chat": {"deny": {}}}).status_code, (401, 403))
        self.assertEqual(features.reason("parcels", uid), "blocked")
        self.assertNotIn("deny", profiles.settings(uid))
        block(self, "mail", uid, on=True)
        self.assertIsNone(features.reason("mail", uid))
        self.assertIsNone(features.reason("parcels", uid))
        self.assertNotIn("mail", features.chat_cfg().get("deny") or {})

    def test_blocking_a_second_function_keeps_the_first(self):
        _, uid = profile("RelEmil")
        helpers.set_config(weather=True, mail=True)
        block(self, "weather", uid)
        block(self, "mail", uid)
        self.assertEqual((features.reason("weather", uid), features.reason("mail", uid)), ("blocked", "blocked"))
        block(self, "mail", uid, on=True)                              # lifting one leaves the other
        self.assertEqual((features.reason("weather", uid), features.reason("mail", uid)), ("blocked", None))

    def test_preference_off_turns_only_that_off(self):
        _, uid = profile("RelEmma")
        _, other = profile("RelFred")
        helpers.set_config(proactive=True, weather=True)
        self.assertNotIn("pro_on", profiles.settings(uid))
        self.assertTrue(features.allowed("proactive", uid))             # missing = on
        profiles.save_settings(uid, {"pro_on": False})
        self.assertEqual(features.reason("proactive", uid), "profile")
        self.assertTrue(features.allowed("weather", uid))               # nothing else goes off
        self.assertTrue(features.allowed("proactive", other))           # and nobody else's
        self.assertIn("Du hast es ausgeschaltet", features.missing_text("proactive", uid))
        profiles.save_settings(uid, {"pro_on": True})
        self.assertTrue(features.allowed("proactive", uid))

    def test_old_deny_entries_never_block_saving(self):
        """chat.deny cleaned on reading (features.clean_deny): a removed function, a deleted or unknown profile,
        doubles and empty lists go; the valid block stays and still works."""
        _, uid = profile("RelHanno")
        _, gone_uid = profile("RelIrma")
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{gone_uid}").status_code, 200)
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            saved = f.read()
        self.addCleanup(helpers.write_config, json.loads(saved))
        c = json.loads(saved)
        c["chat"]["deny"] = {"wx_gone": [uid], "weather": [uid, uid, gone_uid, "u_000000000000"], "mail": [],
                             "search": [gone_uid]}
        helpers.write_config(c)
        cfg = ADMIN.get("/api/config").json()
        self.assertEqual(cfg["chat"]["deny"], {"weather": [uid]})
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 200)
        self.assertTrue(features.blocked("weather", uid))
        self.assertFalse(features.blocked("search", uid))
        self.assertEqual(features.clean_deny(features.chat_cfg().get("deny")), {"weather": [uid]})
        self.assertEqual(features.clean_deny(["weather"]), {})

    def test_removed_keys_are_not_stored(self):
        c, uid = profile("RelGina")
        # the release switches that were removed with Freigabe vereinfachen and the App-Gleichstand: one list
        gone = sorted(profiles.GONE)
        self.assertIn("app_mine", gone)
        import iphone
        self.assertLessEqual(iphone.GONE, profiles.GONE, "iphone.GONE only from profiles.GONE")
        r = c.put("/api/profile/settings", json=dict({k: True for k in gone}, pro_on=False))
        self.assertEqual(r.status_code, 200)
        stored = profiles.settings(uid)
        for k in gone:
            self.assertNotIn(k, profiles.SETTINGS, k)
            self.assertNotIn(k, stored, k)
            self.assertNotIn(k, r.json()["settings"], k)
        self.assertIs(stored["pro_on"], False)                          # a known preference is still kept


if __name__ == "__main__":
    unittest.main()


class Detail(unittest.TestCase):
    """Phase 5: Personen und Geräte has one profile detail with access, functions and rights."""
    def test_detail_has_functions_and_rights(self):
        c, uid = profile("DetaEva")
        d = ADMIN.get(f"/api/admin/profiles/{uid}").json()
        self.assertEqual(set(d["features"]), {"on", "of"})
        self.assertEqual(d["features"]["on"], d["features"]["of"])   # a new profile may use all that is released
        self.assertTrue(d["main"])
        self.assertEqual(set(d["rights"]), {"agent", "update", "quota", "vorrang"})
        self.assertEqual(d["rights"]["agent"]["level"], "")
        self.assertIsInstance(d["sessions"], list)
        self.assertEqual(len(d["sessions"]), 1)              # the login above
        lst = ADMIN.get("/api/admin/profiles").json()
        self.assertEqual(set(lst["guests"]), {"public"})
        self.assertIn("role", next(u for u in lst["users"] if u["id"] == uid))

    def test_function_count_follows_the_switches(self):
        c, uid = profile("DetaFin")
        helpers.set_config(weather=True)
        self.addCleanup(helpers.set_config, weather=False)
        on, of = features.count(uid)
        self.assertGreaterEqual(of, 1)
        block(self, "weather", uid)
        self.assertEqual(features.count(uid), (on - 1, of))
        helpers.set_config(weather=False)
        self.assertEqual(features.count(uid), (on - 1, of - 1))   # what the Spark switched off does not count
        block(self, "weather", uid, on=True)
        self.assertEqual(features.count(uid), (on - 1, of - 1))

    def test_agent_level_per_profile(self):
        c, uid = profile("DetaGus")
        for bad in ("root", 1, None):
            self.assertEqual(ADMIN.put(f"/api/admin/agent/levels/{uid}", json={"level": bad}).status_code, 400)
        self.assertEqual(ADMIN.put("/api/admin/agent/levels/u_000000000000", json={"level": "read"}).status_code, 404)
        self.assertEqual(c.put(f"/api/admin/agent/levels/{uid}", json={"level": "act"}).status_code, 401)   # no admin
        self.assertEqual(ADMIN.put(f"/api/admin/agent/levels/{uid}", json={"level": "read"}).json(), {"level": "read"})
        self.assertEqual(ADMIN.get(f"/api/admin/profiles/{uid}").json()["rights"]["agent"]["level"], "read")
        import guard
        self.assertTrue(any(x.get("event") == "agent_level" and x.get("uid") == uid for x in guard.read(50)))
        ADMIN.put(f"/api/admin/agent/levels/{uid}", json={"level": ""})
        self.assertEqual(ADMIN.get(f"/api/admin/profiles/{uid}").json()["rights"]["agent"]["level"], "")

    def test_admin_ends_a_browser(self):
        c, uid = profile("DetaHil")
        sid = ADMIN.get(f"/api/admin/profiles/{uid}").json()["sessions"][0]["id"]
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{uid}/sessions/{sid}").status_code, 200)
        self.assertIsNone(c.get("/api/whoami").json()["profile"])


class AppNames(unittest.TestCase):
    """Phase 6: the app's Funktionen page takes names and groups from the Spark, it keeps no list of its own."""
    def test_every_app_switch_has_a_name(self):
        d = ADMIN.get("/api/admin/switches").json()
        self.assertEqual(set(d["names"]), set(d["switches"]))
        grouped = [k for g in d["groups"] for k in g["switches"]]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertTrue(set(grouped) <= set(d["switches"]))
        for v in d["names"].values():
            self.assertEqual(len(v), 2)

    def test_swift_keeps_no_list(self):
        with open(os.path.join(HERE, "..", "..", "ios", "Spark", "AdminViews.swift")) if os.path.exists(
                os.path.join(HERE, "..", "..", "ios")) else open(os.devnull) as f:
            swift = f.read()
        self.assertNotIn('("memory", LocalizedStringKey(', swift)
