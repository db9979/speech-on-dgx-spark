"""Every service that can be switched on has a guide (static/js/guides.js) and sits in exactly one group."""
import os
import re
import unittest

STATIC = os.path.join(os.path.dirname(__file__), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


def guides():
    js = read("js", "guides.js")
    groups = re.findall(r"\['(\w+)','[^']+','[^']+'\]", js[js.index("const GGROUPS"):js.index("const GSECT")])
    body = js[js.index("const GUIDES=["):js.index("// ---------------------------------------------------------------- rendering")]
    out = []
    for chunk in re.split(r"\n\{(?=id:)", body)[1:]:
        g = dict(re.findall(r"\b(id|grp|sw|me):'([^']+)'", chunk.split("\n", 1)[0]))
        g["sections"] = set(re.findall(r"^ (\w+):", chunk, re.M))
        out.append(g)
    return groups, out


class Guides(unittest.TestCase):
    def test_every_switch_has_a_guide(self):
        html = read("index.html")
        feat = html[html.index('id="pane-feat"'):html.index('id="pane-ai"')]
        switches = set(re.findall(r'type="checkbox" id="(chat\.\w+)"', feat))
        self.assertTrue(switches)
        _, gs = guides()
        have = {g.get("sw") for g in gs}
        self.assertEqual(switches - have, set(), "Schalter ohne Anleitung")
        for g in gs:
            if g.get("sw"):
                self.assertIn(f'id="{g["sw"]}"', html, g["id"])

    def test_settings_of_a_switch_sit_below_it(self):
        # guidesFeat moves every block with data-show="<switch>" under that switch; a block for a
        # switch without a guide would stay loose at the top of the page
        html = read("index.html")
        feat = html[html.index('id="pane-feat"'):html.index('id="pane-ai"')]
        _, gs = guides()
        have = {g.get("sw") for g in gs}
        for sw in set(re.findall(r'data-show="([\w.]+)"', feat)):
            self.assertIn(sw, have, f"Einstellungen für {sw} hätten keinen Platz unter einem Schalter")

    def test_every_profile_page_has_a_guide(self):
        me = read("js", "me.js")
        pages = set(re.findall(r"\['(\w+box)',t\(", me[me.index("function meTabs"):]))
        _, gs = guides()
        have = {g.get("me") for g in gs}
        # sign-in and the log are no services
        self.assertEqual(pages - have - {"loginbox", "logbox"}, set(), "Seiten ohne Anleitung")

    def test_guides_complete_and_grouped(self):
        groups, gs = guides()
        self.assertEqual(len(groups), 6)
        ids = [g["id"] for g in gs]
        self.assertEqual(len(ids), len(set(ids)))
        for g in gs:
            self.assertIn(g.get("grp"), groups, g["id"])
            self.assertEqual(g["sections"] & {"what", "need", "setup", "say", "out", "off", "fix"},
                             {"what", "need", "setup", "say", "out", "off", "fix"}, g["id"])


if __name__ == "__main__":
    unittest.main()
