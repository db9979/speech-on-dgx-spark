"""One scroll bar where the eye is (Dominik 2026-10-19: „so viele Leisten an der Seite nicht komfortabel und
verwirrend“, „auf manchen Seiten gibt es auch Balken, der gar nichts macht … gesehen bei Musik“; plan bildlauf/plan.md
1 2a 3 4).

Before: Ich had three bars (its menu, its page and the window bar, which only scrolled the page hidden under Ich), and
E-Mail three inside each other (page, reading pane, mail text); small lists kept a height of their own.

- An open window (Ich, sign-in, search …) is the only thing that scrolls: the page under it stands still.
- Ich scrolls as a whole: its menu and its page grow with their content.
- A list with details as a frame (.ld-frame, E-Mail): beside the menu the page fills the window and stands still, the
  list and the details each scroll on their own, side by side.
- No bar inside a scrolling bar, no bar with nothing to scroll; boxes that keep a bar of their own are FENSTER below,
  each with its reason (a log or code window, the conversation, a popup, a sticky side column).

The browser part runs with the real scroll bars (Playwright hides them by default) on a computer and a phone screen,
over every page of the menu, every Einstellungen tab, every Ich page and an open long mail."""
import asyncio
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import PAGE_READY, async_playwright, browser_ok, chromium

helpers.start()
import profiles  # noqa: E402
from tests import test_post_seite as post  # noqa: E402  (its fake mailbox; a module, so its tests do not run twice)

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")

# the boxes that may scroll on their own, inside a page that scrolls too; anything else with overflow auto/scroll
# in the style sheets is a box inside the page and shows its content in full or „Weitere … zeigen“
FENSTER = {
    "pre": "code and machine output keep their lines",
    ".modal": "a window over the page: the one bar while it is open",
    ".ullog": "update progress, follows the newest line",
    ".mdstand": "model install progress, follows the newest line",
    ".fabtext": "the floating face's bubble",
    ".fabpop": "the floating face's bubble",
    "#chatlog": "the conversation: only it scrolls on the assistant page",
    "body.inchat .stage": "the assistant page on a phone",
    ".sheetcard": "a sheet over the page (phone)",
    ".finds": "search results in their window",
    ".wizbody": "the first-start window",
    ".sres": "search suggestions under the field",
    "body.adm header": "the side menu beside the page",
    ".lout": "the log window, follows the newest line",
    ".rlist": "the request list beside one request (Zustand → Logs), refreshed every 10 s",
    ".fpal .fres": "the command search (Strg K)",
    "body.hilfeon .fabpop": "the floating face's bubble",
    ".tipsetup": "a tip in the face's bubble",
    ".rpcard": "the window „Problem melden“",
    "pre.rpbody": "the report in that window",
    ".ld-detail": "the sticky detail column beside a list: scrolls only when taller than the window",
    ".ld-frame>.ld-split>.ld-list,.ld-frame>.ld-split>.ld-detail,.ld-frame>.ld-split>.postfold": "list, details and the mail folders of a frame, side by side",
    ".post .postfold": "the mail folders (narrow screens: a panel over the list)",
    ".post .postcmpb": "the window „Neue E-Mail“: its text scrolls inside the window",
    ".fdin": "the sticky detail column of Funktionen",
    ".pcard.split .pside": "the sticky side column of a person",
    ".choice .chrows": "a choice card inside the conversation",
    ".cx-list": "Chats: the list of chats beside the messages",
    ".fzview:fullscreen .fzside": "Fernzugang in full screen: the drawer with suggestions and assistant beside the terminal",
    ".cx-log": "Chats: the messages",
    ".cx-pane": "Chats: the side pane",
    ".dkvpic": "the companion's screen picture",
    ".wkpatch": "a code change (Werkstatt)",
    ".kal .kaldet.sheet": "an appointment as a sheet (phone)",
    ".kal .kalside.sheet": "the calendars as a sheet (phone)",
    ".calpeople": "the people list in the window „Kalender teilen“",
    "body.appview.inchat #chatlog": "the conversation in the app view",
    ".apsbody": "a sheet of the app view",
    "body.kiosk": "the Live page as a kiosk screen",
    "#tkbox.tk-full #tkview": "Technik full screen",
    "#tkbox.tk-full .tk-pic": "Technik full screen",
    ".dm-feed": "Dungeon-Master: the story of a round, like a conversation; the newest line stays in view",
    ".dm-voll .dm-group,.dm-voll .dm-side": "Dungeon-Master full screen: the group and the side beside the story",
    ".dm.dm-voll:not(.dm-tisch)": "Dungeon-Master overview in full screen: over the page, its one bar while it is open",
    ".dm.dm-tisch.dm-voll": "Dungeon-Master full screen on a narrow screen: the table is the one bar",
    ".dmk.gross": "Dungeon-Master map opened large: a window over the page, its one bar while it is open",
    ".dm-fen-body": "Dungeon-Master hero sheet, merchant or item opened as a window over the table: its one bar while it is open",
    ".dm-rlist": "Dungeon-Master tab Regeln on a wide screen: the catalogue list beside its detail (like .ld-list); narrow screens show it in full",
    ".dm-rtafel": "Dungeon-Master tab Regeln: the rows of one table (up to 300) in the detail beside the list; the detail stays in view",
    ".dm-tisch .dm-handeln": "Dungeon-Master table on a phone: the field to act stays above the bottom bar; only a long text in it scrolls (at most 45 % of the screen)",
}
CSS = ("app.css", "appview.css", "live.css", "technik.css", "weiche.css")


def scrolling_rules():
    for name in CSS:
        with open(os.path.join(STATIC, name), encoding="utf-8") as f:
            css = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            if re.search(r"overflow(-y)?\s*:\s*(auto|scroll)", m.group(2)):
                yield name, m.group(1).strip()


class Static(unittest.TestCase):
    def test_every_box_with_a_bar_of_its_own_has_a_reason(self):
        for name, sel in scrolling_rules():
            self.assertIn(sel, FENSTER, f"{name}: {sel} scrolls inside the page; show it in full or give it a reason here")

    def test_no_reason_without_its_box(self):
        have = {sel for _, sel in scrolling_rules()}
        self.assertEqual(sorted(set(FENSTER) - have), [])

    def test_ich_and_windows_have_the_one_bar(self):
        css = open(os.path.join(STATIC, "app.css"), encoding="utf-8").read()
        self.assertIn('html:has(.modal[style*="grid"]){overflow:hidden;scrollbar-gutter:auto}', css)
        self.assertEqual(css.count("scrollbar-gutter:stable"), 1)   # the page's own, nothing inside it
        # the Ich window's card, its menu and its page never get a height or a bar of their own
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
            if any(re.search(r"\.(mecard|mewrap|menav|mebody)$", x.strip()) for x in sel.split(",")):
                self.assertNotRegex(body, r"(?<![-\w])height:\d|max-height:\d|overflow(-y)?:(auto|scroll)", sel.strip())

    def test_scroll_places_follow_the_window(self):
        for name in ("base.js", "start.js", "me.js", "remarkable.js"):
            js = open(os.path.join(STATIC, "js", name), encoding="utf-8").read()
            self.assertNotRegex(js, r"mebody'\)\.scrollTop|closest\('\.mebody'\)|\.mebody'\);if\(mb\)", name)

    def test_mail_is_a_frame(self):
        self.assertIn("w.className='ld-box ld-frame post'", open(os.path.join(STATIC, "js", "post.js"), encoding="utf-8").read())


# every box that scrolls or shows a bar: where its bar is and which scrolling box holds it
SCAN = """(()=>{const out=[],modal=[...document.querySelectorAll('.modal')].find(m=>m.style.display==='grid');
const name=e=>{if(e===document.documentElement)return'html';let s=e.tagName.toLowerCase();if(e.id)s+='#'+e.id;
  const c=[...e.classList].slice(0,3);if(c.length)s+='.'+c.join('.');return s};
const shown=e=>{const r=e.getBoundingClientRect();if(r.width<2||r.height<2)return false;
  for(let x=e;x&&x!==document.documentElement;x=x.parentElement){const cs=getComputedStyle(x);if(cs.display==='none'||cs.visibility==='hidden')return false}return true};
const scrolls=e=>{const cs=getComputedStyle(e);return e===document.documentElement?cs.overflowY!=='hidden'&&e.scrollHeight>e.clientHeight+1
  :/auto|scroll/.test(cs.overflowY)&&e.scrollHeight>e.clientHeight+1};
for(const e of document.querySelectorAll('body *')){if(modal&&!modal.contains(e)&&e!==modal)continue;
  const cs=getComputedStyle(e);if(!/auto|scroll/.test(cs.overflowY)||!shown(e)||/^(TEXTAREA|SELECT)$/.test(e.tagName))continue;
  const bar=Math.round(e.offsetWidth-e.clientWidth-parseFloat(cs.borderLeftWidth)-parseFloat(cs.borderRightWidth));
  const over=e.scrollHeight-e.clientHeight;let up=e.parentElement;while(up&&up!==document.documentElement&&!scrolls(up))up=up.parentElement;
  out.push({el:name(e),over,bar,scroll:over>1,inside:up?(up===document.documentElement?(scrolls(up)?'html':''):name(up)):''})}
return {boxes:out,page:modal?(getComputedStyle(document.documentElement).overflowY==='hidden'||!scrolls(document.documentElement)):true}})()"""
ALLOWED_INSIDE = re.compile(r"^(pre|div\.lout|div\.rlist|div\.ullog|div\.mdstand|div\.wkpatch|div#chatlog|div\.cx-|div\.ld-detail|div\.fdin|div\.pside|div\.pcard|div#fabtext|div#fabpop)")


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(post.Fake):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        helpers.set_config(memory=True, documents=True, calendar=True, weather=True, mail=True)
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Bildlauf", "4713")
        except Exception:
            pass
        # a full inbox and long mails: the reading pane and the list both have more than a window
        cls.raw = dict(post.RAW)
        for i in range(10, 50):
            post.RAW[i] = (f"From: Absender {i} <a{i}@example.de>\r\nTo: ich@example.de\r\nSubject: Betreff {i}\r\n"
                           f"Date: Mon, {1 + i % 27:02d} Mar 2026 10:00:00 +0100\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
                           + "Eine Zeile einer langen Mail.\r\n\r\n" * 60)

    @classmethod
    def tearDownClass(cls):
        post.RAW.clear()
        post.RAW.update(cls.raw)
        super().tearDownClass()

    async def until(self, pg, expr, seconds=20):
        for _ in range(int(seconds * 10)):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass   # the page is just loading again
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    async def page(self, p, w, h):
        exe = chromium()
        # Playwright starts Chromium with --hide-scrollbars: without it the bars are there like on a Mac or Windows
        br = await p.chromium.launch(ignore_default_args=["--hide-scrollbars"], **({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True,
                                   is_mobile=w < 500, has_touch=w < 500)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.route("**/api/setup", lambda route: route.fulfill(json={"done": True})
                       if route.request.method == "GET" else route.continue_())
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
        self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Bildlauf", "pin": "4713"})).status, 200)
        await pg.goto(base + "/")
        await self.until(pg, PAGE_READY + "&&typeof PROFILE!=='undefined'&&!!PROFILE&&ADMIN===true")
        post.OWNERS[await pg.evaluate("PROFILE.id")] = [post.ACCT]
        await pg.evaluate("MAIL_ON=true;postStart({profile:PROFILE,mail:true})")
        return br, pg, errors

    async def check(self, pg, where):
        await self.until(pg, "!!window.lzIdle&&lzIdle()")
        await pg.wait_for_timeout(150)   # one frame for the layout after the last box
        d = await pg.evaluate(SCAN)
        self.assertTrue(d["page"], f"{where}: the page under the open window scrolls (a bar that moves nothing visible)")
        for b in d["boxes"]:
            self.assertFalse(b["bar"] > 0 and not b["scroll"], f"{where}: {b['el']} shows a bar with nothing to scroll")
            if b["scroll"] and b["inside"]:
                self.assertRegex(b["el"], ALLOWED_INSIDE, f"{where}: {b['el']} scrolls inside {b['inside']}")
        return d["boxes"]

    def test_every_page_one_bar(self):
        async def go():
            async with async_playwright() as p:
                for vname, w, h in (("pc", 1280, 900), ("handy", 390, 844)):
                    br, pg, errors = await self.page(p, w, h)
                    try:
                        for s in ("chat", "mon", "live", "test", "werk", "logs", "verb", "usage", "models", "tech", "feat", "prof",
                                  "route", "int", "apps", "cal"):
                            await pg.evaluate(f"goSec('{s}')")
                            await self.check(pg, f"{vname}/{s}")
                        await pg.evaluate("goSec('cfg')")
                        for pid in await pg.evaluate("[...document.querySelectorAll('#cfgnav button[data-p]')].map(b=>b.dataset.p)"):
                            await pg.evaluate(f"document.querySelector('#cfgnav button[data-p={pid}]').click()")
                            await self.check(pg, f"{vname}/cfg-{pid}")
                        # a long mail open: on a computer list and reading pane side by side, the page stands still
                        await pg.evaluate("icTabSet('post','show');goSec('post')")
                        await self.until(pg, "document.querySelectorAll('#postview .ld-row').length>20")
                        await pg.evaluate("document.querySelector('#postview .ld-row').click()")
                        await self.until(pg, "!!document.querySelector('#postview .posttext')&&$('postview').querySelector('.posttext').textContent.length>500")
                        boxes = await self.check(pg, f"{vname}/post")
                        if w > 760:
                            self.assertEqual(sorted(b["el"].split(".")[1] for b in boxes if b["scroll"]), ["ld-detail", "ld-list"], boxes)
                            self.assertLessEqual(await pg.evaluate("document.documentElement.scrollHeight-innerHeight"), 1, "pc/post: the page scrolls")
                        else:
                            self.assertEqual([b for b in boxes if b["scroll"]], [], f"{vname}/post: {boxes}")   # only the page
                        # every Ich page: the window is the one bar, the page under it stands still
                        for mid in await pg.evaluate("meAll().map(x=>x[0])"):
                            await pg.evaluate(f"openMe('{mid}')")
                            await self.until(pg, "document.getElementById('profmodal').style.display==='grid'")
                            boxes = await self.check(pg, f"{vname}/me-{mid}")
                            # the page takes the width beside the menu or the whole phone, nothing sticks out
                            wide = await pg.evaluate("(()=>{const b=document.querySelector('#profmodal .mebody');return [b.clientWidth,b.scrollWidth-b.clientWidth]})()")
                            self.assertGreater(wide[0], 300, f"{vname}/me-{mid}: Ich page {wide[0]} px wide")
                            self.assertLessEqual(wide[1], 0, f"{vname}/me-{mid}: sideways")
                            self.assertEqual([b["el"] for b in boxes if b["scroll"] and not b["el"].startswith("div#profmodal")
                                              and not re.match(ALLOWED_INSIDE, b["el"])], [], f"{vname}/me-{mid}")
                        await pg.evaluate("closeProf()")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
