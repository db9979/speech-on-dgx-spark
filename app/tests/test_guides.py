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
        # sign-in, the log and the overview are no services
        self.assertEqual(pages - have - {"loginbox", "logbox", "overbox"}, set(), "Seiten ohne Anleitung")

    def test_guides_complete_and_grouped(self):
        groups, gs = guides()
        self.assertEqual(len(groups), 7)
        ids = [g["id"] for g in gs]
        self.assertEqual(len(ids), len(set(ids)))
        for g in gs:
            self.assertIn(g.get("grp"), groups, g["id"])
            self.assertEqual(g["sections"] & {"what", "need", "setup", "say", "out", "off", "fix"},
                             {"what", "need", "setup", "say", "out", "off", "fix"}, g["id"])


if __name__ == "__main__":
    unittest.main()


class MenuPlaces(unittest.TestCase):
    """Cloned voices are a settings page (Einstellungen → Stimmen); the main menu entry is "Profile"."""

    def test_voices_under_settings(self):
        html = read("index.html")
        self.assertNotIn('<section id="voices"', html)
        cfg = html[html.index('<section id="cfg">'):html.index('</section>', html.index('<section id="cfg">'))]
        self.assertIn('data-p="voices"', cfg)
        self.assertIn('id="pane-voices"', cfg)
        self.assertIn('id="vlist"', cfg)
        self.assertIn('<i class="ni" data-ni="prof"></i>Profile und Geräte</button>', html)
        self.assertNotIn("'voices'", read("js", "base.js"))

    def test_voice_list_has_no_inline_handlers(self):
        js = read("js", "admin.js")
        clone = js[js.index("async function loadClone"):js.index("$('vlist').onclick")]
        self.assertNotIn("onclick=", clone)
        self.assertIn("data-vprobe=", clone)

    def test_old_menu_paths_are_gone(self):
        for f in ("index.html", "js/guides.js", "js/extras.js", "js/wizard.js", "js/i18n.js", "js/me.js"):
            text = read(*f.split("/"))
            for old in ("Nutzer →", "Users →", "Reiter „Stimmen“", "Profil-Knopf → Stimme →"):
                self.assertNotIn(old, text, f)


class SettingsOrder(unittest.TestCase):
    """V01.0.123: every setting sits below its switch on Funktionen, one name per page, short rows,
    unsaved changes are shown and asked about."""

    def feat(self):
        html = read("index.html")
        return html, html[html.index('id="pane-feat"'):html.index('id="pane-ai"')]

    def test_feature_settings_below_their_switch(self):
        html, feat = self.feat()
        for el, sw in (("chat.search_url", "chat.search"), ("chat.weather_url", "chat.weather"),
                       ("chat.speaker_strictness", "chat.speaker_id")):
            self.assertIn(f'id="{el}"', feat, el)
            block = feat[:feat.index(f'id="{el}"')]
            self.assertEqual(block.rindex('data-show="'), block.rindex(f'data-show="{sw}"'), el)
        self.assertIn('id="chat.tool_thinking"', feat)
        self.assertNotIn('pane-know', html)
        self.assertNotIn('data-p="know"', html)

    def test_one_name_per_page(self):
        html = read("index.html")
        nav = html[html.index('id="cfgnav"'):html.index('</div>', html.index('id="cfgnav"'))]
        names = re.findall(r'data-p="\w+"[^>]*>([^<]+)<', nav)
        self.assertEqual(len(names), len(set(names)))
        for old in (">Assistent<", ">Gespräch<", ">System<", ">Websuche<"):
            self.assertNotIn(old, nav)
        for f in ("index.html", "js/guides.js", "js/extras.js", "js/me.js", "js/i18n.js", "js/chat.js"):
            text = read(*f.split("/"))
            for old in ("Profil-Knopf", "profile button", "Profile button", "Einstellungen → Websuche", "Einstellungen → Assistent"):
                self.assertNotIn(old, text, f)

    def test_feature_rows_are_short_and_translated(self):
        _, feat = self.feat()
        en = read("js", "i18n.js")
        for text in re.findall(r'<div class="lbl"><b>[^<]+</b><span>([^<]+)</span>', feat):
            self.assertLessEqual(len(text), 140, text)
            self.assertIn(json_str(text), en, text)

    def test_unsaved_changes_are_asked(self):
        js = read("js", "admin.js")
        self.assertIn("beforeunload", js)
        self.assertIn("Ungespeicherte Änderungen", js)
        self.assertIn("leaveOk()", js)


def json_str(s):
    import json
    return json.dumps(s, ensure_ascii=False)


class DesignKlar(unittest.TestCase):
    """V01.0.145 design „Klar“: the main menu is Assistent and Ich for oneself, then "Spark verwalten" with
    Zustand, Einstellungen, Profile und Geräte, Einbinden; phones get a bar with the same first entries;
    no help text sends anyone to the old name "Übersicht"."""

    def test_menu_order(self):
        html = read("index.html")
        nav = html[html.index("<nav>"):html.index("</nav>")]
        self.assertEqual(re.findall(r'data-s="(\w+)"', nav), ["chat", "mon", "cfg", "prof", "int"])
        self.assertLess(nav.index('id="navme"'), nav.index("Spark verwalten"))
        self.assertLess(nav.index("Spark verwalten"), nav.index('data-s="mon"'))
        self.assertEqual(re.findall(r'data-m="(\w+)"', html), ["chat", "me", "mon", "more"])

    def test_no_old_page_name(self):
        for f in ("guides.js", "admin.js", "wizard.js"):
            self.assertNotIn("Übersicht →", read("js", f), f)
        self.assertNotIn("Overview →", read("js", "guides.js"))


class MenuStructure(unittest.TestCase):
    """V01.0.125: settings menu in three blocks, all checks under Übersicht → Prüfen, Einbinden only guides and
    apps, the Ich window starts with an overview and keeps the groups of the Funktionen page."""

    def test_settings_menu_blocks(self):
        html = read("index.html")
        nav = html[html.index('id="cfgnav"'):html.index('</div>\n    <div>', html.index('id="cfgnav"'))]
        self.assertEqual(re.findall(r'class="cgrp">([^<]+)<', nav), ["Was er kann", "Wie er denkt und spricht", "Spark selbst"])
        self.assertEqual(re.findall(r'data-p="(\w+)"', nav), ["feat", "ai", "talk", "tts", "voices", "asr", "sec", "sysc"])

    def test_checks_in_one_place(self):
        html = read("index.html")
        sec = lambda s: html[html.index(f'<section id="{s}">'):html.index("</section>", html.index(f'<section id="{s}">'))]
        for el in ("livesteps", "qlist", "benchout", "asrfile", "ttstext"):
            self.assertIn(f'id="{el}"', sec("test"), el)
        for el in ("baklist", "updlog", "sysver"):
            self.assertIn(f'id="{el}"', sec("sys"), el)
        self.assertIn('id="guidelist"', sec("int"))
        self.assertNotIn('id="int-ep"', sec("int"))
        self.assertIn('id="int-ep"', sec("apps"))
        base = read("js", "base.js")
        self.assertIn("['test',t('Prüfen'", base)
        self.assertIn("['apps',t('Apps und Schnittstellen'", base)

    def test_me_pages_follow_the_groups(self):
        me = read("js", "me.js")
        pages = re.findall(r"\['(\w+box)',t\(", me[me.index("function meTabs"):me.index("// pages in the same groups")])
        self.assertEqual(pages[0], "overbox")
        groups, gs = guides()
        grp = {g["me"]: g["grp"] for g in gs if g.get("me") and g["id"] != "hands"}
        seen = [grp[p] for p in pages if p in grp]
        order = [g for i, g in enumerate(seen) if i == 0 or seen[i - 1] != g]
        self.assertEqual(len(order), len(set(order)), f"Gruppen im Ich-Fenster zerrissen: {order}")
        self.assertEqual(order, [g for g in groups if g in order], "andere Reihenfolge als auf Funktionen")
        self.assertIn('id="notebox"', read("index.html"))
        self.assertIn("showOver()", me)
