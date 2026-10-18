"""App-Gleichstand (docs/de/richtlinien.md Teil 1 Zeile 18, Dominik 2026-10-14: „dass Erweiterungen … Einzug in die
App erhalten, zum Einstellen, angucken und so weiter, dass das der User nicht nur alles am Browser machen kann“).

- features.ME_PAGES is the one list of the Ich pages: me.js meAll and guides.js ME_NAME carry the same ids and
  names, every function's Ich page is in it.
- Pages of their own in the menu (features.OWN_PAGES: Kalender) hold everything of their kind and are no longer
  pages of Ich (Dominik 2026-10-18); kalender.js OWN_PAGES carries the same, the apps list them first.
- Every Ich page reaches the apps: Android shows the panel itself (WebView, appview.js takes the panel's own list),
  the iPhone app lists /api/features "pages" and keeps no list of its own; only features.APP_SKIP leaves a page
  out, with a reason. Every preference (pref=) can be set from the app through its page.
- The pages a profile gets follow the admin release; guests get none.
- The app's admin pages and the iPhone app's texts: every place exists in the panel, every German text has its
  English one (an Altlastenliste per file that only shrinks, like test_aufraeumen).

Files outside app/ skip in the app/-only copy the Spark tests. No wall clock dependence.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import glob
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402
import profiles  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
JS = os.path.join(APP, "panel", "static", "js")
IOS = os.path.join(ROOT, "ios")
ANDROID = os.path.join(ROOT, "android")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def need(path):
    if not os.path.exists(path):
        raise unittest.SkipTest(f"{os.path.relpath(path, ROOT)} is not in this copy (the Spark tests only app/)")
    return path


def js_str(x):
    return x.replace("\\'", "'")


# every page an app can list: the pages of their own in the menu (Kalender …) and the Ich pages
ALL_PAGES = tuple((k, de, en) for k, _, de, en in features.OWN_PAGES) + features.ME_PAGES


class OneList(unittest.TestCase):
    def test_pages_are_unique_and_every_function_has_its_page(self):
        ids = [k for k, _, _ in ALL_PAGES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted({f.me for f in features.FEATURES if f.me} - set(ids)), [])
        self.assertEqual(sorted(set(features.APP_SKIP) - set(ids)), [])
        for k, why in features.APP_SKIP.items():
            self.assertGreater(len(why), 10, k)

    def test_me_js_lists_the_same_pages(self):
        src = read(JS, "me.js")
        block = src[src.index("function meAll(){"):src.index("function meTabs")]
        got = [(m.group(1), js_str(m.group(2) or m.group(4)), js_str(m.group(3) or m.group(4))) for m in re.finditer(
            r"\['(\w+)',(?:t\('((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\)|'([^']*)')", block)]
        self.assertEqual(got, list(features.ME_PAGES), "me.js meAll: the same pages and names as features.ME_PAGES")

    def test_own_pages_are_the_same_in_the_panel(self):
        # Dominik 2026-10-18: everything of a kind in one place, out of Ich; the panel's list is the same as features'
        src = read(JS, "kalender.js")
        block = src[src.index("const OWN_PAGES={"):]
        block = block[:block.index("};")]
        got = [(m.group(1), m.group(2), js_str(m.group(3)), js_str(m.group(4))) for m in re.finditer(
            r"(\w+):\['(\w+)',t\('((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\)", block)]
        self.assertEqual(got, list(features.OWN_PAGES))
        html = read(APP, "panel", "static", "index.html")
        names = read(JS, "guides.js")
        names = names[names.index("const ME_NAME={"):]
        names = names[:names.index("};")]
        for key, sec, de, _ in features.OWN_PAGES:
            self.assertRegex(html, f'<section id="{sec}">', key)
            self.assertRegex(html, f'<button data-s="{sec}" hidden><i class="ni" data-ni="{sec}"></i>{de}</button>', key)
            self.assertNotIn(f"{key}:", names, f"{key}: no longer a page of Ich")
            self.assertRegex(html, f'id="{key}"', key)

    def test_guides_name_the_pages_the_same(self):
        src = read(JS, "guides.js")
        block = src[src.index("const ME_NAME={"):]
        block = block[:block.index("};")]
        names = {k: (de, en) for k, de, en in features.ME_PAGES}
        for m in re.finditer(r"(\w+):\['((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\]", block):
            self.assertEqual((js_str(m.group(2)), js_str(m.group(3))), names.get(m.group(1)), m.group(1))


class InTheApps(unittest.TestCase):
    def test_android_shows_the_panel_with_its_own_list(self):
        main = read(need(ANDROID), "app", "src", "main", "java", "io", "github", "db9979", "spark", "MainActivity.kt")
        self.assertIn("WebView", main)
        view = read(JS, "appview.js")
        self.assertIn("meTabs", view)                     # the app view takes the panel's Ich list
        self.assertNotIn("meAll=", view.replace(" ", ""))

    def test_iphone_keeps_no_list_of_pages(self):
        need(IOS)
        bridge = read(IOS, "Spark", "PanelViews.swift")
        self.assertNotRegex(bridge, r'"me=[a-z]+box"', "the iPhone app takes the Ich pages from /api/features (pages)")
        # a single link to one page elsewhere (a hint, a button) must lead to a page the app may open
        ids = {k for k, _, _ in ALL_PAGES} - set(features.APP_SKIP)
        for path in glob.glob(os.path.join(IOS, "**", "*.swift"), recursive=True):
            for m in re.finditer(r'"me=([a-z]+)"', read(path)):
                self.assertIn(m.group(1), ids, os.path.relpath(path, ROOT))
        self.assertIn('d["pages"]', bridge)
        self.assertIn("SFSafariViewController", bridge)   # opens inside the app, not in Safari

    def test_the_apps_admin_places_exist_in_the_panel(self):
        bridge = read(need(IOS), "Spark", "PanelViews.swift")
        html = read(APP, "panel", "static", "index.html")
        places = re.findall(r'"(go|cfg)=([a-z]+)"', bridge)
        self.assertGreater(len(places), 5)
        for kind, name in places:
            want = f'<section[^>]*id="{name}"' if kind == "go" else f'id="pane-{name}"'
            self.assertRegex(html, want, f"{kind}={name}")

    def test_every_preference_reaches_the_app(self):
        for f in features.FEATURES:
            if f.pref:
                self.assertTrue(f.me, f"{f.key}: a preference needs its Ich page")
                if f.me != "andbox":                         # the Android app's own page, set in the Android app
                    self.assertNotIn(f.me, features.APP_SKIP, f"{f.key}: its page must reach the app")


class PagesFollowTheRelease(unittest.TestCase):
    def test_pages_for_a_profile(self):
        uid = profiles.add_user("Gleich Gabi", "5813")
        try:
            helpers.set_config(weather=False)
            ids = [p["id"] for p in features.app_pages(uid)]
            for k in ("factbox", "logbox", "secbox", "setbox"):
                self.assertIn(k, ids, k)
            for k in features.APP_SKIP:
                self.assertNotIn(k, ids, k)
            self.assertNotIn("wxbox", ids)                  # its function off
            self.assertEqual(ids, [k for k, _, _ in ALL_PAGES if k in ids])   # the panel's order
            helpers.set_config(weather=True)
            self.assertIn("wxbox", [p["id"] for p in features.app_pages(uid)])
            helpers.set_config(deny={"weather": [uid]})
            self.assertNotIn("wxbox", [p["id"] for p in features.app_pages(uid)])
            names = {k: [de, en] for k, de, en in ALL_PAGES}
            for p in features.app_pages(uid):
                self.assertEqual(p["name"], names[p["id"]])
            self.assertEqual(features.app_pages(None), [])  # guests: only questions and answers
        finally:
            helpers.set_config(weather=False, deny={})
            profiles.delete_user(uid)

    def test_the_list_comes_with_api_features(self):
        from tests.test_iphone import profile
        c = profile("Gleich Gero")
        pages = c.get("/api/features").json()["pages"]
        self.assertIn({"id": "factbox", "name": ["Gedächtnis", "Memory"]}, pages)


class AppTexts(unittest.TestCase):
    """Every German text of the iPhone app has its English one in Localizable.xcstrings."""
    # texts without English on 2026-10-14; this list only gets shorter
    ALT = {"AreaViews.swift": 1, "ReportView.swift": 12, "Views.swift": 4}
    RX = re.compile(r'(?:Text|LocalizedStringKey|navigationTitle|Section|Label|Button|Toggle|NavigationLink|'
                    r'String\(localized:)\s*\(\s*"((?:[^"\\]|\\.)*)"')

    def test_no_new_text_without_english(self):
        strings = json.loads(read(need(IOS), "Spark", "Localizable.xcstrings"))["strings"]
        now = {}
        for path in sorted(glob.glob(os.path.join(IOS, "Spark", "*.swift"))):
            n = 0
            for m in self.RX.finditer(read(path)):
                k = m.group(1)
                if "\\(" in k or not re.search(r"[A-Za-zÄÖÜäöüß]", k):
                    continue
                e = strings.get(k) or {}
                if not (e.get("localizations", {}).get("en") or e.get("shouldTranslate") is False):
                    n += 1
            if n:
                now[os.path.basename(path)] = n
        more = {f: n for f, n in now.items() if n > self.ALT.get(f, 0)}
        self.assertEqual(more, {}, "a new app text without English in Localizable.xcstrings")
        less = {f: n for f, n in self.ALT.items() if now.get(f, 0) < n}
        self.assertEqual(less, {}, "translated, thank you: lower these entries in AppTexts.ALT")


if __name__ == "__main__":
    unittest.main()
