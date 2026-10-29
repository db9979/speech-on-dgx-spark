"""Design-Tokens: Farben, Schrift und Abstände nur aus den Tokens (Redesign Stufe 1, Plan redesign/plan.md, Dominik
2026-10-29 „wie Empfehlung“: Richtung A Systemstil).

`app/panel/static/tokens.css` is the one source for the panel's colours, shadows, radii and page frame. It is loaded
before app.css on every page that loads app.css, it holds only custom properties (and color-scheme), and no other
style sheet defines one of its names again. The rest reads var(--…).

What was there before stands in an Altlastenliste per check (Ratchet from test_aufraeumen, docs/de/richtlinien.md
Teil 17): a style sheet may never get more fixed hex colours or font sizes outside the scale than its entry, and when
it gets fewer, the entry shrinks with it. A new style sheet starts at zero."""
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


class HexColours(Ratchet, unittest.TestCase):
    WHAT = "a fixed hex colour outside tokens.css; take a token (var(--…)) or add one to tokens.css"
    ALT = {"app.css": 431, "appview.css": 24, "live.css": 18, "spontanhilfe.css": 19, "technik.css": 10, "weiche.css": 2}

    def hits(self):
        return {n: c for n in sheets() if n != TOKENS and (c := hex_colours(read(n)))}


class FontSizes(Ratchet, unittest.TestCase):
    WHAT = "a font size outside the scale (SCALE); take a size of the scale"
    ALT = {"app.css": 406, "appview.css": 17, "live.css": 21, "spontanhilfe.css": 5, "technik.css": 30, "weiche.css": 14}

    def hits(self):
        return {n: c for n in sheets() if n != TOKENS and (c := off_scale(read(n)))}


if __name__ == "__main__":
    unittest.main()
