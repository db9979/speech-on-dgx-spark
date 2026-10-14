"""Ich-Seiten aufräumen (ich-aufraeumen/plan.md): one look for every Ich page. Lists never scroll inside the page
(the first ten and "Weitere … zeigen"), long addresses and paths never push the page sideways, sections become tabs
with counts, a mail question is answered with one tap, reMarkable has a folder tree with a save bar, and facts in
Gedächtnis can be searched, changed and deleted several at once. Static and API checks run everywhere, the browser
checks where Playwright and Chromium exist; no test reads the clock."""
import asyncio
import json
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")
LONG = "newsletter_at_update_lieferando_de_wyxk2sh2kk_724a0235_sehr_lang_ohne_leerzeichen@privaterelay.appleid.com"


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


def profile(name, pin="4711"):
    admin = TestClient(panel.app)
    admin.post("/api/login", json={"password": "secret-admin"})
    r = admin.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


class Static(unittest.TestCase):
    def test_building_blocks_load_before_the_pages(self):
        scripts = re.findall(r'<script src="/static/js/([\w]+)\.js"', read("index.html"))
        self.assertIn("ichteile", scripts)
        for page in ("me", "tidy", "remarkable", "agent", "chats"):
            self.assertLess(scripts.index("ichteile"), scripts.index(page), page)

    def test_blocks_build_with_text_only(self):
        js = read("js", "ichteile.js")
        # texts from data go in with textContent; the only markup is the fixed symbol paths
        self.assertNotIn("fetch(", js)
        self.assertNotRegex(js, r"\.innerHTML\s*=(?!\s*'<svg)")
        for page in ("tidy.js", "remarkable.js", "me.js"):
            self.assertNotRegex(read("js", page), r"\bon(click|change|input)=\"", page)

    def test_no_scroll_box_inside_ich(self):
        css = read("app.css")
        self.assertIn("#profmodal .facts,#profmodal .tidy ul{max-height:none;overflow:visible}", css)
        self.assertIn("#profmodal .mebody{overflow-x:hidden", css.replace(";", ";").replace("\n", ""))

    def test_new_texts_have_english(self):
        js = read("js", "i18n.js")
        en = json.loads(re.search(r"const EN=(\{.*?\});\n", js, re.S).group(1))
        for de in ("Alles vergessen …", "Anmeldung", "Geräte", "Browser", "Verlauf",
                   "Geräte mit Schlüssel: Lautsprecher, Uhr, Handy-App.",
                   "Löscht alles, was sich der Assistent über dich gemerkt hat. Lässt sich nicht rückgängig machen."):
            self.assertIn(de, en)

    def test_notaus_stays_below_the_security_tabs(self):
        html = read("index.html")
        a = html.index('id="secbox"')
        self.assertLess(html.index('class="ic-tabend"', a), html.index('id="mynaon"', a))


class Api(unittest.TestCase):
    def setUp(self):
        helpers.set_config(memory=True)
        self.p = profile("Aufraeum")
        self.uid = self.p.get("/api/whoami").json()["profile"]["id"]
        profiles.forget(self.uid)
        for x in ("Mag Tee.", "Wohnt in Bonn.", "Hat einen Pool.", "Mag Kaffee."):
            profiles.remember(self.uid, x, auto=True)
        self.ids = {f["text"]: f["id"] for f in profiles.memory(self.uid)}

    def test_change_a_fact(self):
        r = self.p.put(f"/api/profile/memory/{self.ids['Mag Tee.']}", json={"text": "  Mag   grünen Tee.  "})
        self.assertEqual(r.status_code, 200, r.text)
        f = next(x for x in profiles.memory(self.uid) if x["id"] == self.ids["Mag Tee."])
        self.assertEqual(f["text"], "Mag grünen Tee.")
        self.assertNotIn("auto", f)                       # now the person's own words
        # the same text as another fact: the twin goes, one stays
        self.p.put(f"/api/profile/memory/{self.ids['Mag Kaffee.']}", json={"text": "Mag grünen Tee."})
        self.assertEqual(sum(x["text"] == "Mag grünen Tee." for x in profiles.memory(self.uid)), 1)
        # long text is cut, empty or unknown is refused
        self.p.put(f"/api/profile/memory/{self.ids['Wohnt in Bonn.']}", json={"text": "x" * 3000}).raise_for_status()
        self.assertLessEqual(len(next(x for x in profiles.memory(self.uid) if x["id"] == self.ids["Wohnt in Bonn."])["text"]), profiles.MAX_FACT_LEN)
        self.assertEqual(self.p.put(f"/api/profile/memory/{self.ids['Hat einen Pool.']}", json={"text": "  "}).status_code, 404)
        self.assertEqual(self.p.put("/api/profile/memory/nix", json={"text": "Neu"}).status_code, 404)

    def test_forget_several(self):
        r = self.p.post("/api/profile/memory/forget", json={"ids": [self.ids["Mag Tee."], self.ids["Hat einen Pool."], "nix"]})
        self.assertEqual(r.json()["removed"], 2)
        self.assertEqual(sorted(x["text"] for x in profiles.memory(self.uid)), ["Mag Kaffee.", "Wohnt in Bonn."])
        for bad in ({}, {"ids": []}, {"ids": "abc"}, {"ids": [1, 2]}):
            self.assertEqual(self.p.post("/api/profile/memory/forget", json=bad).status_code, 400, bad)

    def test_bodies_are_small(self):
        fid = self.ids["Mag Tee."]
        self.assertEqual(self.p.put(f"/api/profile/memory/{fid}", content=b'{"text":"' + b"x" * 5000 + b'"}',
                                    headers={"Content-Type": "application/json"}).status_code, 413)
        self.assertEqual(self.p.post("/api/profile/memory/forget", json={"ids": ["a" * 30] * 2000}).status_code, 413)
        self.assertEqual(self.p.put(f"/api/profile/memory/{fid}", content=b"[1]", headers={"Content-Type": "application/json"}).status_code, 400)

    def test_only_the_own_profile_in_a_browser(self):
        other = profile("Aufraeum2")
        fid = self.ids["Mag Tee."]
        self.assertEqual(other.put(f"/api/profile/memory/{fid}", json={"text": "Gekapert"}).status_code, 404)
        other.post("/api/profile/memory/forget", json={"ids": [fid]})
        self.assertIn("Mag Tee.", [x["text"] for x in profiles.memory(self.uid)])
        anon = TestClient(panel.app)
        self.assertIn(anon.put(f"/api/profile/memory/{fid}", json={"text": "x"}).status_code, (401, 403))
        self.assertIn(anon.post("/api/profile/memory/forget", json={"ids": [fid]}).status_code, (401, 403))


CATS = {"werbung": "Werbung", "newsletter": "Newsletter", "rechnungen": "Rechnungen"}
TIDY = {"admin": True, "every": 15, "root": "01-Spark", "folders": CATS, "cats": CATS, "backlog": None,
        "accounts": [{"id": "m1", "name": "iCloud", "mode": "preview", "drafts": False, "since": 1, "last_run": 2,
                      "error": "", "stopped": "", "sent": 0}],
        "actions": {"werbung": "move", "newsletter": "move", "rechnungen": "ask"},
        "rules": [{"id": "r0", "match": LONG, "cat": "werbung"}], "protected": [LONG],
        "questions": [{"id": "q1", "aid": "m1", "sender": LONG, "name": "Lieferando", "uids": [1], "subjects": ["Gutschein " * 20],
                       "guess": "werbung", "why": "", "t": 1, "account": "iCloud"}],
        "preview": [{"id": f"p{i}", "aid": "m1", "sender": LONG, "name": "Xcode Cloud", "subject": f"Build {i} " + "x" * 120,
                     "folder": "01-Spark/Newsletter", "why": "automatischer Absender"} for i in range(14)],
        "log": [{"id": f"l{i}", "run": "r", "t": 1, "aid": "m1", "mid": "x", "sender": LONG, "name": "Shop", "subject": f"Sale {i}",
                 "cat": "werbung", "folder": "01-Spark/Werbung", "why": "", "undone": False, "account": "iCloud"} for i in range(3)]}


def item(i, path, kind, folder=False, picked=False):
    return {"id": i, "path": path, "kind": kind, "folder": folder, "pages": 1, "picked": picked, "read": False}


DEEP = "01 Projekte/01 Kleiberit/Ein sehr langer Ordnername ohne Ende " + "x" * 80
RM = {"connected": True, "since": 1, "last": 2, "count": 6, "busy": False, "error": "", "pictures": True, "all": False,
      "send": False, "sent_today": 0, "connect_url": "https://my.remarkable.com/pair",
      "library": [item("a", "01 Projekte", "folder", True), item("b", "01 Projekte/01 Kleiberit", "folder", True),
                  item("c", DEEP, "folder", True), item("d", DEEP + "/Besprechung.pdf", "pdf"),
                  item("e", "01 Projekte/01 Kleiberit/Notizen", "notebook", picked=True), item("f", "10 Notizen", "folder", True)]}


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(memory=True)
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Ichseite", "4711")
        except Exception:
            pass

    async def page(self, p, w, h):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Ichseite", "pin": "4711"})).status, 200)
        uid = (await (await pg.request.get(base + "/api/whoami")).json())["profile"]["id"]
        profiles.forget(uid)
        for i in range(24):
            profiles.remember(uid, f"Eintrag {i:02d} " + ("mit https://wiki.example.org/" + "a" * 120 if i == 3 else "über etwas."), auto=i % 2 == 0)
        self.answers = []

        async def fx(route, data):
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

        async def answer(route):
            self.answers.append(json.loads(route.request.post_data or "{}"))
            await fx(route, {"report": {"moved": 0}, **TIDY})
        await pg.route("**/api/profile/tidy", lambda r: fx(r, TIDY))
        await pg.route("**/api/profile/tidy/answer", answer)
        await pg.route("**/api/profile/remarkable", lambda r: fx(r, RM))
        await pg.goto(base + "/")
        await pg.wait_for_timeout(600)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        await pg.evaluate("MAIL_ON=true;TIDY_ON=true;RM_ON=true;S.rm_on=true")
        return br, pg, errors, uid

    async def show(self, pg, tab, js):
        await pg.evaluate(f"openMe('{tab}')")
        await pg.evaluate(js)
        await pg.wait_for_timeout(300)

    async def check_layout(self, pg, what):
        over = await pg.evaluate("(()=>{const b=document.querySelector('#profmodal .mebody');return b.scrollWidth-b.clientWidth})()")
        self.assertLessEqual(over, 0, what)
        boxes = await pg.evaluate("""[...document.querySelectorAll('#profmodal .ptab:not([hidden]) *')].filter(x=>{const c=getComputedStyle(x);
            return /auto|scroll/.test(c.overflowY)&&x.scrollHeight>x.clientHeight+2&&x.tagName!=='TEXTAREA'&&x.tagName!=='SELECT'}).map(x=>x.id||x.className)""")
        self.assertEqual(boxes, [], what)

    def test_pages_fit_and_never_scroll_inside(self):
        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 900), (390, 844), (320, 640)):
                    br, pg, errors, uid = await self.page(p, w, h)
                    try:
                        if w == 320:
                            # wider letters than the container's fonts, like on some systems (GitHub runner, V01.0.424)
                            await pg.add_style_tag(content="#profmodal{letter-spacing:.12em}")
                        await self.show(pg, "factbox", "showFacts()")
                        await pg.wait_for_selector("#factlist [data-fact]")
                        await self.check_layout(pg, f"{w} Gedächtnis")
                        await self.show(pg, "mailbox", "showMailTidy()")
                        await pg.wait_for_selector("#mailtidy .ic-q")
                        await self.check_layout(pg, f"{w} E-Mail Fragen")
                        await pg.evaluate("document.querySelector('#mailtidy .ic-tabs button[data-k=p]').click()")
                        await self.check_layout(pg, f"{w} E-Mail Vorschau")
                        await self.show(pg, "rmbox", "showRm()")
                        await pg.wait_for_selector("#rmbox [data-rmid]")
                        await self.check_layout(pg, f"{w} reMarkable")
                        await self.show(pg, "secbox", "0")
                        await self.check_layout(pg, f"{w} Sicherheit")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())

    def test_mail_tabs_and_one_tap_answer(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors, uid = await self.page(p, 1280, 900)
                try:
                    await self.show(pg, "mailbox", "showMailTidy()")
                    await pg.wait_for_selector("#mailtidy .ic-q")
                    tabs = await pg.evaluate("[...document.querySelectorAll('#mailtidy .ic-tabs button')].map(b=>[b.dataset.k,b.classList.contains('on'),(b.querySelector('i')||{}).className||''])")
                    self.assertEqual(tabs[0], ["q", True, "hot"])     # the tab that needs you opens first, its count orange
                    self.assertEqual([x[0] for x in tabs], ["q", "p", "log", "r", "f"])
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#mailtidy details').length"), 0)
                    # the guess is marked; one tap answers, "Immer so" is ticked
                    self.assertIn("guess", await pg.evaluate("document.querySelector('#mailtidy .ic-q .ic-chip.guess').className"))
                    await pg.evaluate("[...document.querySelectorAll('#mailtidy .ic-q .ic-chip')].find(b=>b.textContent.includes('Newsletter')).click()")
                    await pg.wait_for_timeout(300)
                    self.assertEqual(self.answers, [{"id": "q1", "cat": "newsletter", "always": True}])
                    # preview: grouped by folder, the first five, the rest behind a button
                    await pg.evaluate("document.querySelector('#mailtidy .ic-tabs button[data-k=p]').click()")
                    rows = await pg.evaluate("document.querySelectorAll('#mailtidy .ic-panel:not([hidden]) .ic-row').length")
                    self.assertLess(rows, 14)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_mail_modes_say_what_they_do(self):
        """Aus / Vorschau / Sicher / Voll: a visible line under the card says what the chosen mode does (not only a
        tooltip, phones have none); pointing at another mode shows its line; fits 320 px."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors, uid = await self.page(p, 320, 700)
                try:
                    await self.show(pg, "mailbox", "showMailTidy()")
                    await pg.wait_for_selector("#mailtidy .ic-modesay")
                    say = "document.querySelector('#mailtidy [data-modesay=m1]')"
                    self.assertTrue(await pg.evaluate(say + ".getBoundingClientRect().height>0"))
                    self.assertIn("schlägt nur vor", await pg.evaluate(say + ".textContent"))      # the mock is in preview
                    lines = {}
                    for k in ("off", "safe", "auto"):
                        await pg.evaluate(f"document.querySelector('#mailtidy .ic-seg button[data-v={k}]').focus()")
                        lines[k] = await pg.evaluate(say + ".textContent")
                    self.assertIn("nicht", lines["off"])
                    self.assertIn("Eindeutiges", lines["safe"])
                    self.assertIn("85 %", lines["auto"])
                    self.assertEqual(len(set(lines.values())), 3)
                    await pg.evaluate("document.activeElement.blur()")
                    self.assertIn("schlägt nur vor", await pg.evaluate(say + ".textContent"))
                    self.assertEqual(await pg.evaluate("document.querySelector('#mailtidy .ic-seg button[data-v=auto]').title"), "Voll automatisch")
                    await self.check_layout(pg, "modes 320")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_mail_mode_change_asks_for_the_code(self):
        """Changing a mode is a setting (stufen.py: code when the profile has the second step). The answer 428 opens
        the code window and sends again; with a bare fetch the switch seemed stuck (Dominik 2026-10-14)."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors, uid = await self.page(p, 390, 844)
                try:
                    sent = []

                    async def put(route):
                        if route.request.method != "PUT":
                            await route.fulfill(status=200, content_type="application/json", body=json.dumps(TIDY))
                            return
                        sent.append([json.loads(route.request.post_data or "{}"), route.request.headers.get("x-speech-code")])
                        if not route.request.headers.get("x-speech-code"):
                            await route.fulfill(status=428, content_type="application/json", body=json.dumps({"detail": "code required"}))
                            return
                        acc = dict(TIDY["accounts"][0], mode="safe")
                        await route.fulfill(status=200, content_type="application/json", body=json.dumps(dict(TIDY, accounts=[acc])))
                    await pg.route("**/api/profile/tidy", put)
                    await pg.evaluate("window.confirmAsk=async()=>({code:'123456'})")
                    await self.show(pg, "mailbox", "showMailTidy()")
                    await pg.wait_for_selector("#mailtidy .ic-seg")
                    await pg.evaluate("document.querySelector('#mailtidy .ic-seg button[data-v=safe]').click()")
                    await pg.wait_for_function("document.querySelector('#mailtidy .ic-seg button.on').dataset.v==='safe'")
                    self.assertEqual(sent, [[{"accounts": {"m1": {"mode": "safe"}}}, None], [{"accounts": {"m1": {"mode": "safe"}}}, "123456"]])
                    self.assertIn("Eindeutiges", await pg.evaluate("document.querySelector('#mailtidy [data-modesay=m1]').textContent"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_mail_new_folder_from_a_question(self):
        """'＋ Neuer Ordner' in a question: a name field, a wrong name is refused here already, a right one is sent
        with the answer (the panel makes the folder); fits on a phone."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors, uid = await self.page(p, 390, 844)
                try:
                    await self.show(pg, "mailbox", "showMailTidy()")
                    await pg.wait_for_selector("#mailtidy .ic-q")
                    await pg.evaluate("document.querySelector('#mailtidy .ic-q .ic-chip[data-cat=new]').click()")
                    await pg.wait_for_selector("#mailtidy .ic-newf input")
                    self.assertTrue(await pg.evaluate("[...document.querySelectorAll('#mailtidy .ic-q .ic-chips button')].every(b=>b.disabled)"))
                    await pg.fill("#mailtidy .ic-newf input", "Spark/../INBOX")
                    await pg.evaluate("document.querySelector('#mailtidy .ic-newf .b.p').click()")
                    await pg.wait_for_timeout(200)
                    self.assertEqual(self.answers, [])
                    self.assertIn("Ordnername", await pg.evaluate("document.getElementById('tidymsg').textContent"))
                    await pg.fill("#mailtidy .ic-newf input", "Lieferdienste")
                    await self.check_layout(pg, "new folder 390")
                    await pg.press("#mailtidy .ic-newf input", "Enter")
                    await pg.wait_for_timeout(300)
                    self.assertEqual(self.answers, [{"id": "q1", "new": "Lieferdienste", "always": True}])
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_remarkable_tree_and_save_bar(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors, uid = await self.page(p, 1280, 900)
                try:
                    puts = []
                    await pg.route("**/api/profile/remarkable/pick", lambda r: (puts.append(json.loads(r.request.post_data)), r.fulfill(status=200, content_type="application/json", body="{}"))[1])
                    await self.show(pg, "rmbox", "showRm()")
                    await pg.wait_for_selector("#rmbox .ic-tree")
                    self.assertFalse(await pg.is_visible("#rmbox .ic-save"))
                    # a folder holding a chosen notebook is half ticked
                    self.assertTrue(await pg.evaluate("!!document.querySelector('#rmbox .ic-tree [data-dir=\"01 Projekte\"] .ic-cb.half,#rmbox .ic-tree [data-dir=\"01 Projekte\"].half')"))
                    for d in ("01 Projekte", "01 Projekte/01 Kleiberit"):
                        await pg.evaluate(f"[...document.querySelectorAll('#rmbox .ic-tree [data-dir]')].find(x=>x.dataset.dir==='{d}').click()")
                        await pg.wait_for_timeout(200)
                    self.assertIn("Kleiberit", await pg.text_content("#rmbox .ic-crumb"))
                    # tick the long folder in the list: the save bar comes, saving sends both
                    await pg.evaluate("document.querySelector('#rmbox .ic-row [data-rmid=\"c\"]').click()")
                    await pg.wait_for_selector("#rmbox .ic-save", state="visible")
                    await pg.evaluate("$('rmsave').click()")
                    await pg.wait_for_timeout(400)
                    self.assertEqual(len(puts), 1)
                    self.assertEqual(sorted(puts[0]["ids"]), ["c", "e"])
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_facts_search_change_and_select(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors, uid = await self.page(p, 1280, 900)
                try:
                    await self.show(pg, "factbox", "showFacts()")
                    await pg.wait_for_selector("#factlist [data-fact]")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#factlist [data-fact]').length"), 15)
                    await pg.fill("#factfind", "Eintrag 07")
                    await pg.wait_for_timeout(200)
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#factlist [data-fact]').length"), 1)
                    # change in place
                    await pg.evaluate("document.querySelector('#factlist [data-fact] .ic-ib[aria-label=\"Ändern\"]').click()")
                    await pg.wait_for_selector("#factlist textarea.factedit")
                    await pg.fill("#factlist textarea.factedit", "Eintrag 07 neu formuliert.")
                    await pg.evaluate("[...document.querySelectorAll('#factlist button')].find(b=>/Speichern/.test(b.textContent)).click()")
                    await pg.wait_for_timeout(400)
                    self.assertIn("Eintrag 07 neu formuliert.", [x["text"] for x in profiles.memory(uid)])
                    # select several and delete them
                    await pg.fill("#factfind", "")
                    await pg.evaluate("$('factpick').click()")
                    await pg.evaluate("[...document.querySelectorAll('#factlist [data-fact]')].slice(0,3).forEach(r=>r.querySelector('.ic-cb').click())")
                    await pg.wait_for_selector("#factbox .ic-save", state="visible")
                    pg.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
                    await pg.evaluate("[...document.querySelectorAll('#factbox .ic-save button')].find(b=>/Löschen/.test(b.textContent)).click()")
                    await pg.wait_for_timeout(500)
                    self.assertEqual(len(profiles.memory(uid)), 21)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
