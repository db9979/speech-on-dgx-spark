"""Suche und Gesicht leichter finden (plaene/suche-gesicht.md, Dominik 2026-10-13 "1 b").

Suche: the search button in the menu also for profiles, the magnifier at the top of the app view, the search box fits
a phone (it was 640 px wide and stuck out) and has a cross to close it.
Gesicht: every profile may pick its own face under Ich → Gespräch → Anzeige (and in the iPhone app), on all its
devices; "" or nothing is the Spark's face (chat.face, the admin's pick under Einstellungen → Vorgaben). Guests and
shared devices get the Spark's. Only the fixed names from FACES; the admin's presets never copy a face into a profile.
Static checks run everywhere, the browser checks where Playwright and Chromium exist; no test reads the clock.
"""
import asyncio
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
from core import FACES  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_ui_browser import async_playwright, browser_ok, chromium  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
STATIC = os.path.join(APP, "panel", "static")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


class OwnFace(unittest.TestCase):
    def tearDown(self):
        helpers.set_config(face="robot")

    def test_profile_picks_its_own_face(self):
        c = profile("Gesichtwahl")
        self.assertEqual(c.get("/api/whoami").json()["face"], "robot")
        c.put("/api/profile/settings", json={"face": "comic"})
        who = c.get("/api/whoami").json()
        self.assertEqual(who["face"], "comic")
        self.assertEqual(who["face_spark"], "robot")
        # the Spark's face changes: the own pick stays, the Spark's is reported beside it
        helpers.set_config(face="comic_woman")
        who = c.get("/api/whoami").json()
        self.assertEqual((who["face"], who["face_spark"]), ("comic", "comic_woman"))
        # back to the default: the Spark's face again
        c.put("/api/profile/settings", json={"face": ""})
        self.assertEqual(c.get("/api/whoami").json()["face"], "comic_woman")

    def test_only_known_faces_are_kept(self):
        c = profile("Gesichtfalsch")
        c.put("/api/profile/settings", json={"face": "comic"})
        for bad in ("Comic", "../comic", "<svg>", 1, None, True, ["comic"]):
            c.put("/api/profile/settings", json={"face": bad})
            self.assertEqual(c.get("/api/whoami").json()["face"], "comic", bad)
        for v in ("robot", "comic", "comic_woman", ""):
            self.assertTrue(profiles.SETTINGS["face"][1](v), v)
        self.assertFalse(profiles.SETTINGS["face"][1]("<svg>"))
        self.assertEqual(set(FACES), {"robot", "comic", "comic_woman"})
        self.assertIs(profiles.FACES, FACES)

    def test_guests_get_the_sparks_face(self):
        helpers.set_config(face="comic")
        who = TestClient(panel.app).get("/api/whoami").json()
        self.assertEqual((who["face"], who["face_spark"]), ("comic", "comic"))
        self.assertEqual(profiles.face_of(None, {"face": "comic_woman"}), "comic_woman")
        self.assertEqual(profiles.face_of(None, {"face": "<b>"}), "robot")

    def test_presets_never_copy_a_face(self):
        # the admin's own pick is chat.face; chat.defaults with a face does not reach a profile
        self.assertIn("face", profiles.NO_PRESET)
        self.assertEqual(profiles.defaults({"face": "comic"})["face"], "")

    def test_every_device_asks_for_the_profiles_face(self):
        # the apps, the companions and the watch get the profile's face from one place (profiles.face_of);
        # only the admin's own settings and whoami's "face_spark" read chat.face themselves
        for mod in ("iphone.py", "pebblewatch.py", "begleiter.py", "chat.py"):
            src = read(APP, "panel", mod)
            self.assertNotRegex(src, r'get\("face"\)', mod)
            self.assertIn("profiles.face_of(", src, mod)
        self.assertIn('"face": profiles.face_of(prof["id"] if prof else None, cfg.get("chat", {})),', read(APP, "panel", "account.py"))
        import iphone
        self.assertIn("face", iphone.APP_FIELDS)

    def test_iphone_app_offers_the_choice(self):
        ios = os.path.join(APP, "..", "ios", "Spark")
        if not os.path.isdir(ios):
            self.skipTest("ios is not part of this copy")
        v = read(ios, "Views.swift")
        self.assertIn('Picker("Gesicht", selection: $face)', v)
        for kind in ("", *FACES):
            self.assertIn(f'.tag("{kind}")', v)
        self.assertIn('saveProfileSettings(["face": v])', v)
        strings = read(ios, "Localizable.xcstrings")
        for s in ("Gesicht", "Vorgabe des Spark", "Comic (Frau)"):
            self.assertIn(f'"{s}"', strings)


class Static(unittest.TestCase):
    def test_own_face_row_only_on_the_own_page(self):
        me = read(STATIC, "js", "me.js")
        self.assertIn("k:'face',type:'face',prof:1,me:1", me)
        self.assertIn("&&(!f.me||!admin));", me)
        self.assertIn("if(window.faceTiles)faceTiles(el);", me)
        self.assertIn("if(window.faceApply)faceApply();", me)

    def test_tiles_draw_only_the_fixed_faces(self):
        js = read(STATIC, "js", "face.js")
        fn = js[js.index("window.faceTiles="):js.index("mountAll();\nconst F=")]
        # the picture comes from the fixed drawings by a checked name, the label only as text
        self.assertIn("pic.innerHTML=faceStill(faceOk(k)?k:'robot')", fn)
        self.assertEqual(fn.count("innerHTML"), 1)
        self.assertIn("l.textContent=", fn)
        self.assertIn("const faceOk=k=>k==='robot'||k==='comic'||k==='comic_woman';", js)
        self.assertIn("setFaceSpark(who.face_spark||who.face);setFaceKind(who.face);", read(STATIC, "js", "start.js"))

    def test_admin_face_sits_on_top_of_vorgaben(self):
        html = read(STATIC, "index.html")
        pane = html[html.index('id="pane-talk"'):]
        pane = pane[:pane.index('<div class="card pane"')]
        self.assertLess(pane.index('<h3 class="sec">Gesicht</h3>'), pane.index('id="facerow"'))
        self.assertLess(pane.index('id="faceliferow"'), pane.index('id="chatdefaults"'))

    def test_search_for_profiles_and_on_phones(self):
        css, appv, find = read(STATIC, "app.css"), read(STATIC, "js", "appview.js"), read(STATIC, "js", "find.js")
        self.assertNotIn("body.prof #findbtn", css)
        self.assertIn("grid-template-columns:minmax(0,1fr)", css[css.index(".fpal{"):css.index(".fpal[hidden]")])
        self.assertIn('data-ap="find"', appv)
        self.assertIn("else if(a==='find')palOpen()});", appv)
        self.assertIn("x.onclick=palClose;", find)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        helpers.set_config(face="robot")
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Gesicht", "4711")
        except Exception:
            pass
        cls.uid = next(u for u in profiles.user_ids() if (profiles.by_id(u) or {}).get("name") == "Gesicht")

    async def page(self, p, w, h, admin=False):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        if admin:
            self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
        self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Gesicht", "pin": "4711"})).status, 200)
        await pg.goto(base + "/")
        # signed in: lzIdle() is true as soon as no box loads, which can be before /api/whoami has answered
        await pg.wait_for_function("document.body.classList.contains('adm')", timeout=20000)
        await pg.wait_for_function("!!window.lzIdle&&lzIdle()", timeout=20000)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        return br, pg, errors

    def test_phone_search_and_own_face(self):
        """320 and 390 px as a profile: the magnifier at the top opens the search, the box stays inside the screen
        and closes with the cross; under Ich → Gespräch the face tiles change the face at once and it is saved."""
        async def go():
            async with async_playwright() as p:
                for w in (320, 390):
                    br, pg, errors = await self.page(p, w, 760)
                    try:
                        await pg.click("#aptrail [data-ap=find]")
                        box = await pg.evaluate("(()=>{const b=document.querySelector('#fpal .fbox').getBoundingClientRect();return [b.left,b.right]})()")
                        self.assertGreaterEqual(box[0], 0, w)
                        self.assertLessEqual(box[1], w, w)
                        await pg.fill("#palq", "Gesicht")
                        await pg.wait_for_timeout(300)
                        self.assertGreater(await pg.evaluate("document.querySelectorAll('#palres .fit').length"), 0, w)
                        await pg.click("#palx")
                        self.assertTrue(await pg.evaluate("document.getElementById('fpal').hidden"), w)
                        await pg.evaluate("openMe('setbox')")
                        # the group "Anzeige" is folded (Code-Prüfung D9): open it as a person would
                        await pg.wait_for_selector("#setform details.megrp .facetiles", state="attached", timeout=10000)
                        await pg.evaluate("document.querySelector('#setform .facetiles').closest('details.megrp').querySelector(':scope>summary').click()")
                        await pg.wait_for_selector(".facetiles .facetile", timeout=10000)
                        tiles = await pg.evaluate("[...document.querySelectorAll('#setform .facetile')].map(b=>b.dataset.v)")
                        self.assertEqual(tiles, ["", *FACES], w)
                        await pg.evaluate("window.__noreload=1")
                        await pg.click("#setform .facetile[data-v=comic]")
                        await pg.wait_for_timeout(700)
                        self.assertEqual(await pg.evaluate("document.body.dataset.face"), "comic", w)
                        # the own pick shows at once: the page does not load itself again (whoFlags reads face_spark)
                        await pg.evaluate("whoCheck()")
                        await pg.wait_for_timeout(400)
                        self.assertEqual(await pg.evaluate("window.__noreload"), 1, w)
                        self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth"), w, w)   # no overflow
                        await pg.click("#setform .facetile[data-v='']")
                        await pg.wait_for_timeout(700)
                        self.assertEqual(await pg.evaluate("document.body.dataset.face"), "robot", w)
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
            # the last tap (the default) was saved for the profile
            self.assertEqual(profiles.settings(self.uid).get("face", ""), "")
        asyncio.run(go())

    def test_desktop_search_for_profiles_and_admin_tiles(self):
        """1280 px: a profile sees the search in the menu; the admin picks the Spark's face with tiles on top of
        Vorgaben, the select underneath follows the tap."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                try:
                    self.assertTrue(await pg.evaluate("document.getElementById('findbtn').offsetParent!==null"))
                finally:
                    await br.close()
                br, pg, errors = await self.page(p, 1280, 900, admin=True)
                try:
                    await pg.evaluate("goSec('cfg')")
                    await pg.wait_for_function("!!window.lzIdle&&lzIdle()", timeout=20000)
                    await pg.evaluate("document.querySelector('#cfgnav button[data-p=talk]').click()")
                    await pg.wait_for_selector("#pane-talk .facetile", timeout=10000)
                    tiles = await pg.evaluate("[...document.querySelectorAll('#pane-talk #facerow .facetile')].map(b=>b.dataset.v)")
                    self.assertEqual(tiles, list(FACES))
                    self.assertEqual(await pg.evaluate("document.querySelector('#facerow .facetile.on').dataset.v"), "robot")
                    await pg.click("#facerow .facetile[data-v=comic_woman]")
                    self.assertEqual(await pg.evaluate("document.getElementById('chat.face').value"), "comic_woman")
                    self.assertTrue(await pg.evaluate("$('pane-talk').classList.contains('dirty')"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
