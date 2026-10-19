"""Code-Prüfung D8: one name per thing. An Ich page carries the name of its function (or a word of it) unless
features.ME_NAME_OWN gives the reason, no Ich page wears the name of a function that is set up elsewhere, and the
computer and the phone call the main menu points the same."""
import os
import re
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
WORDS = lambda s: [w for w in re.findall(r"[a-zäöüß]+", s.lower()) if len(w) >= 5]


def page_of(f):
    """the Ich page a function is set up on: its own, else its parent's"""
    by = {x.key: x for x in features.FEATURES}
    while f and not f.me:
        f = by.get(f.parent)
    return f.me if f else ""


def read(*p):
    with open(os.path.join(PANEL, *p), encoding="utf-8") as fh:
        return fh.read()


class Namen(unittest.TestCase):
    def test_an_ich_page_carries_the_name_of_its_function(self):
        bad = []
        for k, de, en in features.ME_PAGES:
            mine = [f for f in features.FEATURES if f.me == k]
            if not mine or k in features.ME_NAME_OWN:
                continue
            for i, name in ((0, de), (1, en)):
                names = [(f.de, f.en)[i].lower() for f in mine]
                if name.lower() not in names and not any(w in n for w in WORDS(name) for n in names):
                    bad.append((k, name, names[:3]))
        self.assertEqual(bad, [], "name the page like its function, or give the reason in features.ME_NAME_OWN")
        for k, why in features.ME_NAME_OWN.items():
            self.assertIn(k, [p[0] for p in features.ME_PAGES])
            self.assertGreater(len(why), 20, k)

    def test_no_ich_page_wears_the_name_of_a_function_elsewhere(self):
        # was: Ich → "Dienste per MCP" was the Spark as MCP server, the function "Dienste per MCP" the services it uses
        clash = [(k, f.key) for k, de, en in features.ME_PAGES for f in features.FEATURES
                 if de == f.de and page_of(f) != k]
        self.assertEqual(clash, [])

    def test_computer_and_phone_use_the_same_words(self):
        html, app, base = read("static", "index.html"), read("static", "js", "appview.js"), read("static", "js", "base.js")
        chat = re.search(r'data-s="chat"><i class="ni" data-ni="chat"></i>([^<]+)<', html).group(1).strip()
        self.assertIn(f"['spark',t('{chat}',", app)
        self.assertIn("Spark verwalten", html)
        self.assertIn("<h1 class=\"aplt\">${esc(t('Spark verwalten',", app)
        # "Weiche" is no "Switch" in English (the word of every switch); Zustand's first page is no "Monitoring"
        self.assertIn("['route',t('Weiche','Routing')]", base)
        self.assertIn("['mon',t('Überblick','Summary')]", base)


if __name__ == "__main__":
    unittest.main()
