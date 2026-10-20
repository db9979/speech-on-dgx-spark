"""Spickzettel zum Ausdrucken (spickzettel.py, plan plaene/spickzettel.md, Dominik 2026-10-20 „1a 2a 3b“): Ich → Was ich
kann opens a printable page of what the profile can say, in German or English, built from the code on each request.

It stays true: every tool of saetze.AREAS has a card, every sentence and key word on it reaches its group in the
Weiche, every mix-up lands where the sheet says, the marked word is the one the Weiche matched. Only what the profile
can use, never for guests or with „Das kannst du auch sagen“ off, nothing of the profile's data, a strict page policy.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import intent  # noqa: E402
import saetze  # noqa: E402
import spickzettel as sz  # noqa: E402
import werkzeug_abdeckung as wa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ON = dict(spark_help=True, feature_tips=True, feature_sentences=True)


def all_cards():
    for aid, rows in sz.KARTEN.items():
        for groups, tools, title, words, more in rows:
            yield aid, groups, tools, title, words, more


def hits(groups, text):
    """The Weiche puts `text` into one of `groups` (its rule, or the group's own words)."""
    for g in groups:
        pattern = intent.GROUPS[g][1] or (intent.HOME_WORDS if g == "smarthome" else None)
        if pattern is not None and pattern.search(text):
            return True
    return bool(set(groups) & set(intent.classify(text).names))


class Cards(unittest.TestCase):
    def test_every_tool_of_the_areas_has_one_card_in_its_area(self):
        on_card = [t for _a, _g, tools, *_ in all_cards() for t in tools]
        self.assertEqual(len(on_card), len(set(on_card)), "a tool on two cards")
        listed = {t for _a, _d, _e, ts in saetze.AREAS for t in ts}
        self.assertEqual(sorted(listed - set(on_card)), [], "a tool of saetze.AREAS has no card on the Spickzettel")
        self.assertEqual(sorted(set(on_card) - listed), [])
        for aid, _g, tools, *_ in all_cards():
            for t in tools:
                self.assertEqual(saetze.AREA_OF[t], aid, t)
        self.assertEqual(sorted(sz.KARTEN), sorted(a for a, *_ in saetze.AREAS))
        self.assertEqual(sorted(sz.AREA_COLOR), sorted(sz.KARTEN))

    def test_every_sentence_reaches_its_tool(self):
        for _a, groups, tools, _t, _w, more in all_cards():
            self.assertTrue(set(groups) <= set(intent.GROUPS), groups)
            for t in tools:
                de, en = saetze.text_of(t)
                self.assertIn(t, intent.classify(de).tools() | ({t} if t in wa.BY_WORD else set()), de)
            for t, de, en in more:
                self.assertIn(t, tools)
                self.assertTrue(de and en and de != en, de)
                self.assertIn(t, intent.classify(de).tools(), f"{de!r} -> {intent.classify(de).label()}")

    def test_every_key_word_hits_its_group(self):
        def tries(w, en):
            w = w.replace("…", "morgen")
            return (w, f"{w} Anna", f"Make me a {w}" if en else f"Erstell mir eine {w}",
                    f"Mach mir {w}" if not en else f"Look at {w}")
        for _a, groups, _t, title, (de, en), _m in all_cards():
            for lang, words in ((0, de), (1, en)):
                parts = [w.strip() for w in words.split(",")]
                self.assertTrue(all(parts), title)
                for w in parts:
                    self.assertTrue(any(hits(groups, x) for x in tries(w, lang)), f"{title[0]}: „{w}“ trifft {groups} nicht")

    def test_short_commands_need_their_own_word(self):
        import intent_alltag
        for tool, de, en in sz.KURZ:
            self.assertIn(tool, wa.BY_WORD, tool)
            self.assertTrue(intent_alltag.byword(tool, de), de)
            self.assertTrue(en, tool)

    def test_mix_ups_land_where_the_sheet_says(self):
        for de, en, group, what, need in sz.VERWECHSELT:
            names = intent.classify(de).names
            if group:
                self.assertIn(group, names, de)
                self.assertIn(need, intent.GROUPS[group][0], de)
            else:
                self.assertEqual([n for n in names if n != "plaudern"], [], de)
            self.assertTrue(what[0] and what[1], de)

    def test_marks_the_word_the_weiche_matched(self):
        self.assertEqual(sz._marked("Wie wird das Wetter morgen?", {}), "Wie wird das <mark>Wetter</mark> morgen?")
        self.assertEqual(sz._marked("Erzähl einen Witz", {}), "Erzähl einen Witz")
        # the admin's own words (Funktionen → Weiche) count too
        self.assertIn("<mark>", sz._marked("Wie läuft es beim Kegelklub?", {"route_words": "websuche: kegelklub"}))


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = ADMIN.post("/api/admin/profiles", json={"name": "Spicktest", "pin": "1234"})
        assert r.status_code in (200, 409), r.text
        cls.p = TestClient(panel.app)
        assert cls.p.post("/api/profile/login", json={"name": "Spicktest", "pin": "1234"}).status_code == 200

    def setUp(self):
        helpers.keep_chat(self, *ON)
        helpers.set_config(**ON)
        sz._CACHE.clear()

    def test_whole_sheet_in_both_languages(self):
        with mock.patch.object(saetze, "usable", return_value=True):
            de = sz.build("x", "de", {}, now=1_800_000_000)
            en = sz.build("x", "en", {}, now=1_800_000_000)
        for _a, _g, _t, title, _w, _m in all_cards():
            self.assertIn(sz._esc(title[0]), de)
            self.assertIn(sz._esc(title[1]), en)
        self.assertIn('lang="de"', de)
        self.assertIn('lang="en"', en)
        self.assertIn("@page", de)
        self.assertNotIn("<script", de + en)

    def test_only_what_the_profile_can_use(self):
        with mock.patch.object(saetze, "usable", side_effect=lambda uid, t, c=None, org="panel": t == "weather"):
            text = sz.build("x", "de", {}, now=1_800_000_000)
        self.assertIn("Wetter", text)
        self.assertNotIn("Licht", text)
        self.assertNotIn("Ruf Mama an", text)
        with mock.patch.object(saetze, "usable", return_value=False):
            self.assertIn("nichts freigegeben", sz.build("x", "de", {}, now=1_800_000_000))

    def test_admin_words_are_escaped(self):
        with mock.patch.object(saetze, "usable", return_value=True):
            text = sz.build("x", "de", {}, admin_words={"wetter": ["<b>x</b>"]}, now=1_800_000_000)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", text)

    def test_endpoint_profile_only_with_strict_policy(self):
        r = self.p.get("/api/profile/spickzettel?sprache=en")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.headers["content-type"].startswith("text/html"))
        self.assertIn("default-src 'none'", r.headers["content-security-policy"])
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertIn('lang="en"', r.text)
        r = self.p.get("/api/profile/spickzettel?datei=1")
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertEqual(TestClient(panel.app).get("/api/profile/spickzettel").status_code, 401)

    def test_off_with_the_sentences(self):
        helpers.set_config(feature_sentences=False)
        self.assertEqual(self.p.get("/api/profile/spickzettel").status_code, 403)


if __name__ == "__main__":
    unittest.main()
