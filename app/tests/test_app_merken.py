"""Apps merken sich den letzten Stand (appmerken.py, Merken.swift, merken.js; Dominik 2026-10-17): the iPhone and the
Android app keep the last state of a few pages for their profile on the phone and show it at once next time.

The Spark only says whether the app on this device may keep (hello "keep", /api/profile/settings "app_keep"): an app,
a profile, the function released for it; never a plain browser, never a guest. A slow page reaches the log with a fixed
page word and the milliseconds, nothing else. The apps keep nothing of a private or vanishing chat, never the key,
delete everything on unpairing, signing out, another profile and the switch off, and store only in the app's own
protected place. Static checks of the app sources skip in the app/-only copy the Spark tests. No wall clock dependence.
"""
import contextlib
import io
import os
import re
import unittest

from tests import helpers

helpers.start()
import appmerken  # noqa: E402
import guard  # noqa: E402
import iphone  # noqa: E402
import logfilter  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import pair, profile, uid_of  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
JS = os.path.join(APP, "panel", "static", "js")
IOS = os.path.join(ROOT, "ios", "Spark")
MAIN = os.path.join(ROOT, "android", "app", "src", "main", "java", "io", "github", "db9979", "spark", "MainActivity.kt")
ANDROID_UA = "Mozilla/5.0 (Linux; Android 15) SparkAndroid/1.4.1"


def read(path):
    if not os.path.exists(path):
        raise unittest.SkipTest(f"{os.path.relpath(path, ROOT)} is not in this copy (the Spark tests only app/)")
    with open(path, encoding="utf-8") as f:
        return f.read()


def said(fn):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn()
    return r, out.getvalue()


class Spark(unittest.TestCase):
    def setUp(self):
        helpers.set_config(iphone=True, app_cache=True, deny={})
        iphone._pending.clear()
        for k in [k for k in guard._rate if k[0] in ("pair", "applangsam")]:
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(iphone=False, app_cache=True, deny={})

    def key(self, name):
        r = pair(profile(name))
        self.assertEqual(r.status_code, 200, r.text)
        return {"X-Speech-Device": r.json()["token"]}

    def test_the_iphone_app_may_keep_while_released(self):
        h = self.key("Merk Mia")
        app = TestClient(panel.app)
        self.assertIs(app.get("/api/iphone/hello", headers=h).json()["keep"], True)
        helpers.set_config(deny={"appmerken": [uid_of("Merk Mia")]})   # the admin blocks the profile: delete
        self.assertIs(app.get("/api/iphone/hello", headers=h).json()["keep"], False)
        helpers.set_config(deny={}, app_cache=False)                     # the switch off: delete
        self.assertIs(app.get("/api/iphone/hello", headers=h).json()["keep"], False)

    def test_only_the_android_app_never_a_browser_or_a_guest(self):
        c = profile("Merk Max")
        self.assertIs(c.get("/api/profile/settings").json()["app_keep"], False)   # a plain browser
        self.assertIs(c.get("/api/profile/settings", headers={"User-Agent": ANDROID_UA}).json()["app_keep"], True)
        guest = TestClient(panel.app)
        self.assertIs(appmerken.keep(None, None), False)
        r = guest.get("/api/profile/settings", headers={"User-Agent": ANDROID_UA})
        if r.status_code == 200:
            self.assertIs(r.json()["app_keep"], False)

    def test_a_slow_page_is_one_line_of_fixed_words(self):
        h = self.key("Merk Moni")
        app = TestClient(panel.app)
        r, out = said(lambda: app.post("/api/app/langsam", headers=h, json={"seite": "chats", "ms": 2400}))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertRegex(out, r"^app: langsam chats 2400 ms iphone \S+")
        self.assertNotIn("Merk Moni", out)                        # the profile only by profiles.log_name
        for bad in ({"seite": "<b>x</b>", "ms": 2400}, {"seite": "chats", "ms": 10}, {"seite": "chats", "ms": "2400"},
                    {"seite": "chats", "ms": True}, {"seite": "chats", "ms": 10 ** 9}):
            r, out = said(lambda: app.post("/api/app/langsam", headers=h, json=bad))
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("app: langsam abgelehnt falsch iphone", out)
            self.assertNotIn("<b>", out)

    def test_not_from_a_browser_and_not_too_often(self):
        c = profile("Merk Mats")
        r, out = said(lambda: c.post("/api/app/langsam", json={"seite": "chats", "ms": 2400}))
        self.assertEqual(r.status_code, 403)
        self.assertIn("app: langsam abgelehnt kein-app", out)
        self.assertEqual(TestClient(panel.app).post("/api/app/langsam", json={"seite": "chats", "ms": 2400}).status_code, 401)
        r = c.post("/api/app/langsam", headers={"User-Agent": ANDROID_UA}, content=b"x" * (appmerken.BODY + 1))
        self.assertEqual(r.status_code, 413)
        for k in [k for k in guard._rate if k[0] == "applangsam"]:   # the refused call above counted too
            guard._rate.pop(k, None)
        codes = [c.post("/api/app/langsam", headers={"User-Agent": ANDROID_UA}, json={"seite": "seite", "ms": 3000}).status_code
                 for _ in range(guard.RATE["applangsam"][1] + 1)]
        self.assertEqual(codes[:-1], [200] * guard.RATE["applangsam"][1])
        self.assertEqual(codes[-1], 429)

    def test_the_log_area(self):
        rx = dict(logfilter.AREAS)["apps"]
        self.assertRegex("app: langsam chats 2400 ms iphone Profil 1a2b", rx)


class IPhoneApp(unittest.TestCase):
    def test_kept_only_in_the_protected_place_and_deleted_on_unpairing(self):
        m = read(os.path.join(IOS, "Merken.swift"))
        self.assertIn("FileProtectionType.complete", m)
        self.assertIn(".completeFileProtection", m)
        self.assertIn("isExcludedFromBackup = true", m)
        self.assertIn(".applicationSupportDirectory", m)
        self.assertNotIn("UserDefaults.standard.set(data", m)   # the pages never into the defaults
        self.assertIn("SHA256.hash", m)                          # the folder names the pairing, never the key itself
        self.assertNotRegex(m, r"appendingPathComponent\(\s*key")
        allow = m[m.index("static func allow("):]
        self.assertIn("if !keep { forget() }", allow[:allow.index("\n    }\n")])
        conv = read(os.path.join(IOS, "Conversation.swift"))
        unpair = conv[conv.index("func unpair()"):]
        self.assertIn("Merken.forget()", unpair[:unpair.index("\n    }\n")])
        self.assertIn("Merken.saw(r)", conv)
        self.assertIn("Merken.saw(allowed)", read(os.path.join(IOS, "Assistant.swift")))

    def test_the_kept_rights_never_start_anything(self):
        m = read(os.path.join(IOS, "Merken.swift"))
        kept = m[m.index("static func allowed() -> Allowed?"):]
        kept = kept[:kept.index("\n    }\n")]
        for k in ("listen", "act", "proactive", "push", "calls", "ios"):
            self.assertIn(f"a.{k} = false", kept)

    def test_private_and_vanishing_chats_are_never_kept(self):
        c = read(os.path.join(IOS, "ChatsView.swift"))
        items = c[c.index("func chatItems("):]
        items = items[:items.index("\n    }\n")]
        self.assertIn("if p.priv || p.vanish != 0 { Merken.drop(name) } else { Merken.keep(name, data) }", items)
        self.assertIn("before.isEmpty", items)

    def test_meine_sachen_keeps_only_numbers(self):
        t = read(os.path.join(IOS, "ThingsView.swift"))
        kept = re.findall(r'Merken\.keepObject\("sachen", \[(.*?)\]\)', t, re.S)
        self.assertEqual(len(kept), 1)
        for part in re.findall(r'"[a-z]+": (\S+?)[,\]]?\s', kept[0] + " "):
            self.assertTrue(part.endswith(".count"), part)   # how many, never a name, a wish or a fact

    def test_same_numbers_and_page_words_as_the_spark(self):
        m = read(os.path.join(IOS, "Merken.swift"))
        self.assertIn(f"static let slowMs = {appmerken.SLOW_MS}", m)
        words = set()
        for name in os.listdir(IOS):
            if name.endswith(".swift"):
                words |= set(re.findall(r'Merken\.timed\("([a-z]+)"', read(os.path.join(IOS, name))))
        self.assertTrue(words)
        self.assertLessEqual(words, set(appmerken.PAGES))


class AndroidApp(unittest.TestCase):
    def test_the_page_keeps_only_inside_the_app_and_deletes_on_signing_out(self):
        m = read(os.path.join(JS, "merken.js"))
        self.assertRegex(m, r"function merkOn\(\)\{if\(typeof IN_ANDROID==='undefined'\|\|!IN_ANDROID\|\|!PROFILE\)return false")
        self.assertIn(f"MERK_SLOW={appmerken.SLOW_MS}", m)
        me = read(os.path.join(JS, "me.js"))
        self.assertIn("offlineWipe(true);merkWipe(true)", me)                  # Abmelden
        self.assertIn("if(!PROFILE){offlineWipe(true);merkWipe(true)}", me)     # signed out from elsewhere
        self.assertIn("merkAllow(d.app_keep)", me)                              # the switch off: merkWipe(false)
        words = set()
        for name in ("merken.js", "me.js", "chat.js", "chats.js"):
            words |= set(re.findall(r"merkTime\('([a-z]+)'", read(os.path.join(JS, name))))
        self.assertLessEqual(words, set(appmerken.PAGES))
        # the settings kept are the lists and values the page already gets, never the profile itself
        self.assertIn("merkPut('einstellungen',{settings:d.settings,defaults:d.defaults,choices:d.choices,ranges:d.ranges,allow:d.allow})", me)

    def test_the_first_load_is_never_blank(self):
        k = read(MAIN)
        self.assertIn("if (!loadedOnce) firstLoad()", k)
        first = k[k.index("private fun firstLoad()"):]
        first = first[:first.index("\n    }\n")]
        self.assertIn("Verbinde mit dem Spark", first)
        self.assertIn("8000", first)
        self.assertIn('waitRetry.text = "Noch einmal"', k)


if __name__ == "__main__":
    unittest.main()
