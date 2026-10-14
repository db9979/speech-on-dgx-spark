"""Ich → Speicher aufgeräumt (Dominik 2026-10-13 „wie empfohlen umsetzen“, Variante 1): the page shows places (a NAS or
cloud connected once, a folder on the Spark) and below each place what it is for ("Wofür"), today "Kopie meiner
Daten". Funktionen has one heading "Speicher und NAS" with the copy below it, and no profile switch any more. Static
checks run everywhere, the browser check where Playwright and Chromium exist; no test reads the clock."""
import asyncio
import json
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()
import features  # noqa: E402
import profiles  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


PLACE = {"id": "a1b2c3", "name": "Synology Keller mit einem sehr langen Namen", "kind": "webdav",
         "url": "https://nas-im-keller-mit-langem-namen.fritz.box:5006", "user": "spark-kopie-benutzer",
         "has_password": True, "zone": "lan", "added": 1, "checked": {"t": 1, "ok": True}, "uses": {"speicher": 1},
         "cert": ""}
SFTP = {"id": "d4e5f6", "name": "Server", "kind": "sftp", "url": "sftp://server.example.org", "user": "spark",
        "has_password": True, "zone": "internet", "added": 1, "checked": None, "uses": {}, "hostkey": "SHA256:abc"}
NAS = {"admin": True, "on": True, "why": None, "max": 4, "items": [PLACE, SFTP]}
COPY = {"id": "t1", "name": "Kopie", "kind": "webdav", "zone": "lan", "areas": ["gedaechtnis", "dokumente"], "added": 1,
        "last": {"t": 1, "ok": True}, "fail": None, "free": None, "files": 12, "bytes": 123456, "trash": 0, "running": "",
        "offload": False, "away": 0, "hist": [], "url": PLACE["url"] + "/spark/", "user": PLACE["user"],
        "has_password": True, "nas": PLACE["id"], "path": "/spark/ein/sehr/langer/ordnername/ohne/ende/bis/hier"}
STORE = {"admin": True, "on": True, "why": None, "lan": True, "folder": False, "offload": True, "offload_days": 30,
         "root": "", "max": 2, "key": True, "areas": [{"id": "gedaechtnis", "name": ["Gedächtnis", "Memory"]},
                                                      {"id": "dokumente", "name": ["Dokumente", "Documents"]}],
         "targets": [COPY]}
GROUPS = [{"id": "dokumente", "name": ["Dokumente", "Documents"], "ends": [".pdf", ".docx"], "on": True},
          {"id": "bilder", "name": ["Bilder und Scans", "Pictures and scans"], "ends": [".jpg"], "on": False}]
FOLDER = {"id": "f1f2f3", "nas": PLACE["id"], "path": "/volume1/Ablage/Vertraege/ein/sehr/langer/ordnername/ohne/ende",
          "groups": ["dokumente"], "skip": ["Alt"], "added": 1, "docs": 1234, "seen": 1300, "left": 66,
          "out": {"art": 3, "versteckt": 2}, "last": {"t": 1, "ok": True}, "fail": None, "running": False}
NQ = {"admin": True, "on": True, "why": None, "max": 8, "pictures": False, "docs": 1234, "max_docs": 5000, "groups": GROUPS,
      "out_words": {"art": ["Art wird nie gelesen", "kind is never read"], "versteckt": ["System- oder versteckte Datei", "hidden"]},
      "why_words": {"offline": ["nicht erreichbar", "not reachable"]}, "sources": [FOLDER]}


class Static(unittest.TestCase):
    def test_one_heading_with_the_copy_below_it(self):
        self.assertEqual(features.BY_KEY["nas"].de, "Speicher und NAS")
        self.assertEqual(features.BY_KEY["speicher"].de, "Kopie meiner Daten")
        self.assertEqual(features.BY_KEY["speicher"].parent, "nas")
        for k in ("nas", "speicher"):
            self.assertEqual(features.BY_KEY[k].pref, "")         # Freigabe rule: the admin's release counts for all
            self.assertFalse(features.allowed(k, None))           # never guests
        html = read("index.html")
        a = html.index('data-sw="chat.nas_on"') if 'data-sw="chat.nas_on"' in html else html.index("chat.nas_on")
        self.assertLess(a, html.index("chat.storage_own"))
        self.assertNotIn("Eigener Speicher für mich", read("js", "speicher.js") + read("js", "nas.js") + html)

    def test_old_names_are_gone_from_the_page_and_the_guides(self):
        src = read("index.html") + read("js", "nas.js") + read("js", "speicher.js") + read("js", "guides.js")
        for old in ("Eigener Speicher", "NAS verbinden", "Meine NAS", "Speicher einbinden"):
            self.assertNotIn(old, src, old)

    def test_new_texts_have_english(self):
        en = json.loads(re.search(r"const EN=(\{.*?\});\n", read("js", "i18n.js"), re.S).group(1))
        for de in ("Speicher und NAS", "Kopie meiner Daten", "Ordner für Kopien", "Wissensordner", "Abgleich alle (Minuten)"):
            self.assertIn(de, en)

    def test_server_text_is_text(self):
        for name in ("nas.js", "speicher.js", "nasquelle.js"):
            js = read("js", name)
            self.assertNotRegex(js, r"\bon(click|change|input)=\"", name)
            self.assertNotRegex(js, r"\$\{x\.(name|url|user|path)\}", name)   # always through esc()


@unittest.skipUnless(browser_ok(), "Playwright/Chromium fehlt")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(nas_on=True, storage_own=True, storage_lan=True)
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Speicherseite", "4711")
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(nas_on=False, storage_own=False, storage_lan=False)

    async def page(self, p, w, h):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Speicherseite", "pin": "4711"})).status, 200)

        async def fx(route, data):
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
        await pg.route("**/api/profile/nas", lambda r: fx(r, NAS))
        await pg.route("**/api/profile/speicher", lambda r: fx(r, STORE))
        await pg.route("**/api/profile/nasquelle", lambda r: fx(r, NQ))
        await pg.goto(base + "/")
        await pg.wait_for_timeout(600)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        await pg.evaluate("NAS_ON=true;STORE_ON=true")
        return br, pg, errors

    def test_places_with_their_uses_fit(self):
        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 900), (390, 844), (320, 640)):
                    br, pg, errors = await self.page(p, w, h)
                    try:
                        await pg.evaluate("openMe('storebox')")
                        await pg.evaluate("showNas()")
                        await pg.wait_for_selector("#nasbox .place")
                        n = await pg.evaluate("document.querySelectorAll('#nasbox .place').length")
                        self.assertEqual(n, 2, w)
                        text = await pg.evaluate("document.getElementById('nasbox').textContent")
                        for s in ("Wofür", "Kopie meiner Daten", "Verbindung prüfen", "Ort hinzufügen"):
                            self.assertIn(s, text, (w, s))
                        self.assertNotIn("Eigener Speicher", text)
                        # the copy sits at its place, the other place offers to switch it on
                        first = await pg.evaluate("document.querySelectorAll('#nasbox .place')[0].innerText")
                        self.assertIn("12 Dateien", first)
                        self.assertIn("Wissensordner", first)              # the folder sits at its place too
                        self.assertIn("1234 Dokumente", first)
                        self.assertIn("Weiterer Wissensordner", first)
                        second = await pg.evaluate("document.querySelectorAll('#nasbox .place')[1].innerText")
                        self.assertIn("Wissensordner", second)             # the other place offers one
                        await pg.evaluate("document.querySelector('[data-nqon=\"d4e5f6\"]').click()")
                        self.assertFalse(await pg.evaluate("document.querySelector('[data-nqform=\"d4e5f6\"]').hidden"))
                        over = await pg.evaluate("(()=>{const b=document.querySelector('#profmodal .mebody');return b.scrollWidth-b.clientWidth})()")
                        self.assertLessEqual(over, 0, w)
                        self.assertEqual(errors, [], w)
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
