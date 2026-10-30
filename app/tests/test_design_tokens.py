"""Design-Tokens: Farben, Schrift und Abstände nur aus den Tokens (Redesign Stufe 1, Plan redesign/plan.md, Dominik
2026-10-29 „wie Empfehlung“: Richtung A Systemstil).

`app/panel/static/tokens.css` is the one source for the panel's colours, shadows, radii and page frame. It is loaded
before app.css on every page that loads app.css, it holds only custom properties (and color-scheme), and no other
style sheet defines one of its names again. The rest reads var(--…).

What was there before stands in an Altlastenliste per check (Ratchet from test_aufraeumen, docs/de/richtlinien.md
Teil 17): a style sheet may never get more fixed hex colours or font sizes outside the scale than its entry, and when
it gets fewer, the entry shrinks with it. A new style sheet starts at zero.

Klar 3 (Redesign Stufe 3): every symbol comes from js/icons.js; emoji used as symbols and SVG paths drawn in place are
counted per file against their own Altlastenliste the same way."""
import os
import re
import unittest

from tests.test_aufraeumen import Ratchet

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")
TOKENS = "tokens.css"
# pages of the panel that bring their own look and do not load app.css, with the reason
OWN_LOOK = {
    "spontanhilfe.css": "Hilfe am Bildschirm (/hilfe): public page for a person who is no profile, own small palette, "
                        "loads neither app.css nor tokens.css",
}
# the type scale of „Klar 2“ (plan, Design-System A): 26/22/17/14/12.5/11.5 px and 12 px mono; on the phone 16 px
# fields (no zoom in iOS Safari) and the 32 px large title
SCALE = {"11.5px", "12px", "12.5px", "14px", "16px", "17px", "22px", "26px", "32px"}
SAME = {"inherit", "1em", "100%"}   # no size of its own


def read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def sheets():
    return sorted(n for n in os.listdir(STATIC) if n.endswith(".css"))


def declarations(css):
    """(property, value) of every declaration, comments and url(…) taken out (an SVG reference #id is no colour)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"url\([^)]*\)", "url()", css)
    for body in re.findall(r"\{([^{}]*)\}", css):
        for decl in body.split(";"):
            if ":" in decl:
                prop, val = decl.split(":", 1)
                yield prop.strip().lower(), val.strip()


HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")


def hex_colours(css):
    return sum(len(HEX.findall(v)) for _, v in declarations(css))


def off_scale(css):
    n = 0
    for prop, val in declarations(css):
        val = val.replace("!important", "").strip()
        if prop == "font-size":
            size = val
        elif prop == "font":
            m = re.search(r"(?<![\w.])(\d*\.?\d+(?:px|em|rem|%))", val)
            if not m:
                continue   # font:inherit, font:var(--…)
            size = m.group(1)
        else:
            continue
        if size in SCALE or size in SAME or size.startswith(("var(", "calc(var(")):
            continue
        n += 1
    return n


def token_names():
    return set(re.findall(r"(?:^|[{;\s])(--[\w-]+)\s*:", read(TOKENS)))


class Tokens(unittest.TestCase):
    def test_tokens_hold_only_custom_properties(self):
        css = re.sub(r"/\*.*?\*/", "", read(TOKENS), flags=re.S)
        for sel in re.findall(r"([^{}]+)\{[^{}]*\}", css):
            sel = re.sub(r"^.*\)\s*\{", "", sel.strip()).strip()   # inside @media (…){
            self.assertRegex(sel, r"^:root(\[data-theme=(light|dark)\]|:not\(\[data-theme=light\]\))?$", sel)
        for prop, val in declarations(read(TOKENS)):
            self.assertTrue(prop.startswith("--") or prop == "color-scheme", f"{TOKENS}: {prop} is no token")
        self.assertGreater(len(token_names()), 20)

    def test_no_other_sheet_defines_a_token_again(self):
        names = token_names()
        for name in sheets():
            if name == TOKENS or name in OWN_LOOK:
                continue
            again = sorted({p for p, _ in declarations(read(name))} & names)
            self.assertEqual(again, [], f"{name} defines tokens again; they live only in {TOKENS}")

    def test_every_page_with_app_css_loads_the_tokens_first(self):
        pages = [n for n in os.listdir(STATIC) if n.endswith(".html")]
        with_app = 0
        for page in pages:
            links = re.findall(r'<link rel="stylesheet" href="/static/([a-z0-9\-]+\.css)', read(page))
            if "app.css" in links:
                with_app += 1
                self.assertIn(TOKENS, links, page)
                self.assertLess(links.index(TOKENS), links.index("app.css"), page)
            for own in OWN_LOOK:
                if own in links:
                    self.assertNotIn("app.css", links, page)
        self.assertGreaterEqual(with_app, 2)   # index.html and live.html

    def test_the_own_look_list_names_real_sheets(self):
        for name in OWN_LOOK:
            self.assertIn(name, sheets())

    def test_the_tokens_are_served(self):
        src = open(os.path.join(STATIC, "..", "panel.py"), encoding="utf-8").read()
        allowed = re.search(r'def static_file\(.*?\n    if name in \(([^)]*)\)', src, re.S)
        self.assertIsNotNone(allowed)
        for name in sheets():
            self.assertIn(f'"{name}"', allowed.group(1), name)

    def test_the_counters_see_what_they_should(self):
        self.assertEqual(hex_colours(".a{color:#fff;background:#0b1020cc;border:1px solid #abcd}"), 3)
        self.assertEqual(hex_colours(".a{--x:#fff}#fabface .b{fill:url(#dmkf-stein)}"), 1)
        self.assertEqual(off_scale(".a{font-size:13px}.b{font:600 12px var(--font)}.c{font:inherit}.d{font-size:.9em}"), 2)
        self.assertEqual(off_scale(".a{font-size:var(--t)}.b{font:700 26px/1.15 x}.c{font-size:inherit!important}"), 0)


class Klar2(unittest.TestCase):
    """Redesign Stufe 2 (Navigation und Seitenkopf): system font and the type scale as tokens, a calm side menu, a page
    head, nothing that jumps, and no floating face: the face lives only in the assistant."""
    def test_font_and_type_scale_are_tokens(self):
        names = token_names()
        for name in ("--font", "--font-display", "--mono", "--serif", "--t-large", "--t-title", "--t-head", "--t-body",
                     "--t-sub", "--t-cap", "--t-mono", "--side", "--side-w", "--sel", "--fill", "--faint", "--dur"):
            self.assertIn(name, names)
        css = read("app.css")
        self.assertIn("body{margin:0;min-height:100vh;color:var(--fg);font:var(--t-body);", css)
        self.assertNotRegex(css, r"body\{[^}]*gradient")          # a calm ground, no gradient behind the pages
        # no font is loaded from anywhere: the system's own (Google Fonts or a CDN would leave the house)
        for name in sheets():
            self.assertNotIn("@import", read(name), name)
            self.assertNotIn("@font-face", read(name), name)

    def test_nothing_jumps_on_hover(self):
        """Bewegung only as opacity and colour: no translateY or scale when the pointer is over something."""
        for name in sheets():
            css = re.sub(r"/\*.*?\*/", "", read(name), flags=re.S)
            for sel, body in re.findall(r"([^{}]*:hover[^{}]*)\{([^{}]*)\}", css):
                self.assertNotRegex(body, r"translateY|scale\(", f"{name}: {sel.strip()[-60:]}")

    def test_side_menu_and_page_head(self):
        css, html = read("app.css"), read("index.html")
        self.assertIn("body.adm{padding-left:var(--side-w)}", css)
        self.assertIn("background:var(--side)", css)
        self.assertIn("body.adm nav button.on{background:var(--sel)", css)
        self.assertIn('<div class="phead" id="phead" hidden><h2 class="pt" id="pheadt"></h2><div class="pintro" id="pheadi"></div></div>', html)
        base = read(os.path.join("js", "base.js"))
        self.assertIn("function pageHead(g,s,many)", base)
        self.assertIn("$('pheadt').textContent=it[1]", base)   # text, never HTML
        # the coloured tiles of the second column are gone: one line colour, the open page in the accent
        self.assertNotRegex(css, r"\.cic\.c-\w+\{background")

    def test_no_floating_face(self):
        """Dominik 2026-10-29 („wie Empfehlung“): the face only in the assistant. The button „Frag Spark“ (#fabface)
        is a line sign in the top row, never a mounted face, never fixed at the bottom of the window."""
        html, css = read("index.html"), read("app.css")
        fab = html[html.index('<div class="fabface" id="fabface"'):]
        fab = fab[:fab.index("</div>")]
        self.assertIn('stroke="currentColor"', fab)
        self.assertNotIn("face fabface", html)
        self.assertIn("function mountAll(){faces.length=0;FD.vis=null;FD.mode=null;mountFace($('face'),'A')}",
                      read(os.path.join("js", "face.js")))
        rule = re.search(r"\n#fab\{([^}]*)\}", css).group(1)
        self.assertIn("top:", rule)
        self.assertNotIn("bottom:", rule)
        self.assertNotRegex(re.search(r"\n\.fabface\{([^}]*)\}", css).group(1), r"shadow|transform")


# Picture characters (Redesign Stufe 3, Klar 3): every pictograph and the symbols systems draw as colour emoji. Typographic
# marks in the text colour (✓ ✕ ★ ▶ ● ↩ ↻ ♪ ☐ ⛶ …) are text, no emoji.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA\u2600\u2614\u2615\u2622\u2623\u2639"
                   "\u263A\u2648-\u2653\u267B\u267F\u2692-\u2697\u2699\u269B\u26A0\u26A1\u26AA\u26AB\u26B0\u26B1\u26BD"
                   "\u26BE\u26C4\u26C5\u26CE\u26D4\u26EA\u26F2-\u26F5\u26FA\u26FD\u2705\u2709\u270A\u270B\u2728\u274C"
                   "\u274E\u2753-\u2755\u2757\u2764\u2795-\u2797\u27B0\u27BF\u2B1B\u2B1C\u2B50\u2B55]|.\uFE0F")
# a symbol drawn in place: an SVG on the 24 grid with its own paths (icons.js draws them all)
OWN_SYMBOL = re.compile(r'viewBox="0 0 24 24"[^>]*>\s*<(?:path|circle|rect|polyline|line)')
ICON_USE = re.compile(r"\b(?:ic|icNode|icSvg|icBtn|zIco|postIc|postIb|konIc)\('([a-z_]+)'|data-(?:ic|ni)=\"([a-z_]+)\"")


def ui_files():
    """The pages, style sheets and scripts of the panel (esptool.js is the flasher's bundled library)."""
    js = sorted(os.path.join("js", n) for n in os.listdir(os.path.join(STATIC, "js")) if n.endswith(".js") and n != "esptool.js")
    return sorted(n for n in os.listdir(STATIC) if n.endswith((".html", ".css"))) + js


def icon_names():
    src = read(os.path.join("js", "icons.js"))
    return set(re.findall(r"^  ([a-z_]+):'", src, re.M)) | set(re.findall(r"\b([a-z_]+):'[a-z_]+'", src[src.index("Object.entries({"):]))


class Klar3(unittest.TestCase):
    """Redesign Stufe 3 (Dominik 2026-10-29 „wie Empfehlung“): line symbols instead of emoji, from one source."""

    def test_icons_have_one_source(self):
        """icons.js holds every symbol (ICONS, ic, icNode); every page that draws symbols loads it before its scripts,
        no other script keeps a table of its own (the old ones: base.js NI, appview.js IC, ichteile.js SVG, post.js
        POST_IC, admin.js ZICO, kontakte.js KON_IC, fernzugang.js FZ_SVG, users.js PDEV paths, seite.js paths)."""
        src = read(os.path.join("js", "icons.js"))
        self.assertIn("const ICONS={", src)
        self.assertIn("const ic=(n,c)=>", src)
        self.assertIn("function icNode(n,c)", src)
        self.assertNotIn("innerHTML=ic(n", src.replace("w.innerHTML=ic(n,c)", ""))   # only its own wrapper
        for page, first in (("index.html", "/static/js/base.js"), ("live.html", "/static/js/live.js")):
            html = read(page)
            self.assertIn("/static/js/icons.js", html, page)
            self.assertLess(html.index("/static/js/icons.js"), html.index(first), page)
        for name in ui_files():
            if name.endswith(".js") and name != os.path.join("js", "icons.js"):
                body = read(name)
                self.assertNotRegex(body, r"\b(?:const|let|var)\s+(?:ICONS|NI|ZICO|KON_IC|POST_IC|FZ_SVG|SVG)\s*=\s*\{", name)
        # a name the table does not know would draw an empty symbol
        known = icon_names()
        unknown = {f"{n}: {a or b}" for n in ui_files() for a, b in ICON_USE.findall(read(n)) if (a or b) not in known}
        self.assertEqual(unknown, set(), "a symbol name that is not in icons.js")

    def test_symbols_follow_the_text_colour(self):
        """A symbol is drawn with the text colour and the stroke width of the tokens; places only set its size."""
        css = read("app.css")
        rule = re.search(r":where\(\.ic\)\{([^}]*)\}", css).group(1)
        for part in ("fill:none", "stroke:currentColor", "stroke-width:var(--ic-stroke)"):
            self.assertIn(part, rule)
        self.assertIn("--ic-stroke:", read(TOKENS))
        self.assertNotIn("innerHTML=", read(os.path.join("js", "icons.js")).split("function icNode")[0])

    def test_no_close_glyph_buttons(self):
        """A button that only says ✕ draws the symbol „x“ (the game Dungeon keeps its own look for now)."""
        left = {n: read(n).count(">✕</button>") for n in ui_files() if not os.path.basename(n).startswith("dungeon")}
        self.assertEqual({n: c for n, c in left.items() if c}, {})


class Emoji(Ratchet, unittest.TestCase):
    """Emoji as symbols in the user interface (Klar 3): only what people write (chat text, reactions, folder and list
    symbols) and the game stay; the rest of the old list shrinks (setting names with thumbs in index.html, guides.js
    texts, the Dungeon). i18n.js follows the German texts."""
    WHAT = "an emoji as a symbol in the user interface; take a line symbol of icons.js (ic('name'))"
    ALT = {"app.css": 1, "index.html": 9, "js/dungeon-ton.js": 9, "js/dungeon.js": 256, "js/dungeonbuch.js": 1,
           "js/dungeonfenster.js": 44, "js/dungeonkarte.js": 23, "js/dungeonwarten.js": 11, "js/fernzugang.js": 2,
           "js/guides.js": 242, "js/i18n.js": 18}

    def hits(self):
        return {n.replace(os.sep, "/"): c for n in ui_files() if (c := len(EMOJI.findall(read(n))))}


class OwnSymbols(Ratchet, unittest.TestCase):
    WHAT = "a symbol with its own SVG paths; add it to icons.js and draw it with ic('name') or <i data-ic=\"name\">"
    ALT = {"index.html": 45}

    def hits(self):
        return {n.replace(os.sep, "/"): c for n in ui_files() if n != os.path.join("js", "icons.js")
                and (c := len(OWN_SYMBOL.findall(read(n))))}


class HexColours(Ratchet, unittest.TestCase):
    WHAT = "a fixed hex colour outside tokens.css; take a token (var(--…)) or add one to tokens.css"
    ALT = {"app.css": 424, "appview.css": 24, "live.css": 18, "spontanhilfe.css": 19, "technik.css": 10, "weiche.css": 2}

    def hits(self):
        return {n: c for n in sheets() if n != TOKENS and (c := hex_colours(read(n)))}


class FontSizes(Ratchet, unittest.TestCase):
    WHAT = "a font size outside the scale (SCALE); take a size of the scale"
    ALT = {"app.css": 394, "appview.css": 17, "live.css": 21, "spontanhilfe.css": 5, "technik.css": 30, "weiche.css": 14}

    def hits(self):
        return {n: c for n in sheets() if n != TOKENS and (c := off_scale(read(n)))}


if __name__ == "__main__":
    unittest.main()
