"""Präsentationen professionell (Dominik 2026-10-12, plan plaene/praesentationen-professionell.md, "alle punkte
umsetzen 1-6"): slide types with the variety rules, little text per slide, charts only with real numbers, symbols
from the repository, pictures from the own Kiwix (own switch, off), numbers only with a source. All fixed rules on
the model's JSON (folien.py); the model, the Kiwix and the clock are faked."""
import asyncio
import io
import os
import random
import re
import tempfile
import unittest
import zipfile

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import docmake  # noqa: E402
import docrender  # noqa: E402
import features  # noqa: E402
import folien  # noqa: E402
import kiwix  # noqa: E402
import profiles  # noqa: E402
import symbole  # noqa: E402
from tests.test_docmake import profile  # noqa: E402

docmake.BACKGROUND = False


class Types(unittest.TestCase):
    def test_variety_rules_hold_for_any_outline(self):
        """Never the same type twice in a row, at most a third lists (one is always allowed)."""
        rnd = random.Random(7)
        for _ in range(400):
            n = rnd.randint(1, 14)
            want = [rnd.choice(list(folien.LAYOUTS)) for _ in range(n)]
            got = folien.vary(want)
            self.assertEqual(len(got), n)
            for a, b in zip(got, got[1:]):
                self.assertNotEqual(a, b, (want, got))
            self.assertLessEqual(got.count("liste"), max(1, n // 3), (want, got))

    def test_outline_gets_types_only_for_slides(self):
        secs = [{"heading": h, "note": ""} for h in ("Lage und Landschaft", "Geschichte des Grabens", "Zahlen und Fakten",
                                                      "Chancen und Risiken im Vergleich", "Klima", "Fazit")]
        folien.plan_layouts(secs, "praesentation")
        lays = [s["layout"] for s in secs]
        self.assertEqual(lays[1], "ablauf")
        self.assertEqual(lays[3], "vergleich")
        self.assertEqual(lays[-1], "fazit")
        self.assertTrue(all(x in folien.LAYOUTS for x in lays))
        rep = [{"heading": "Fazit", "note": "", "layout": "fazit"}]
        self.assertNotIn("layout", folien.plan_layouts(rep, "bericht")[0])
        # the model's own choice stays when it is a known type
        mine = [{"heading": "Irgendwas", "layout": "zahlen"}, {"heading": "Noch was", "layout": "erfunden"}]
        folien.plan_layouts(mine, "praesentation")
        self.assertEqual(mine[0]["layout"], "zahlen")
        self.assertIn(mine[1]["layout"], folien.LAYOUTS)
        plan = docmake.check_plan({"kind": "bericht", "format": "pptx", "title": "T", "sections": ["A", "B"]})
        self.assertTrue(all(s.get("layout") for s in plan["sections"]))       # a report as slides gets types too

    def test_written_slide_settles_on_what_it_holds(self):
        s = folien.settle({"heading": "x", "bullets": ["a", "b", "c"]}, "diagramm")      # no chart → points
        self.assertEqual(s["layout"], "liste")
        s = folien.settle({"heading": "x", "stats": [{"value": "300 km", "label": "lang"}]}, "symbole")
        self.assertEqual(s["layout"], "zahlen")
        s = folien.settle({"heading": "x", "bullets": ["Berge", "Wasser", "Wein"]}, "symbole")
        self.assertEqual(s["layout"], "symbole")
        self.assertEqual([p["title"] for p in s["points"]], ["Berge", "Wasser", "Wein"])
        self.assertNotIn("bullets", s)
        s = folien.settle({"heading": "x", "paras": ["Nur ein Satz."]}, "")
        self.assertEqual((s["layout"], s["quote"]), ("kernaussage", "Nur ein Satz."))
        # three lists in a row become something else, the text stays
        secs = [folien.settle({"heading": str(i), "bullets": ["eins", "zwei", "drei"]}, "liste") for i in range(3)]
        out = folien.vary_written(secs)
        self.assertNotEqual(out[0]["layout"], out[1]["layout"])
        self.assertNotEqual(out[1]["layout"], out[2]["layout"])
        for s in out:
            self.assertEqual(len(s.get("bullets") or s.get("points")), 3)


class LessText(unittest.TestCase):
    def test_at_most_four_points_with_eight_words(self):
        s = {"heading": "x", "bullets": ["Der Rhein fließt durch den Graben und bringt seit Jahrtausenden Kies, Sand und Ton mit",
                                         "zwei", "drei", "vier", "fünf", "sechs"]}
        self.assertTrue(folien.too_long(s))
        folien.tighten(s)
        self.assertEqual(len(s["bullets"]), 4)
        self.assertTrue(all(len(b.split()) <= folien.MAX_WORDS + 1 for b in s["bullets"]))     # "…" counts as one
        self.assertIn("fünf", s["notes"])
        self.assertIn("Kies, Sand und Ton", s["notes"])        # nothing is lost: the long text is in the notes
        self.assertEqual(folien.shorten("Kurz und klar", 8), "Kurz und klar")
        self.assertEqual(folien.shorten("Der Rhein fließt seit langem, und zwar sehr gemächlich durch das Tal hinab", 8),
                         "Der Rhein fließt seit langem")
        self.assertEqual(folien.too_long({"heading": "x", "bullets": ["eins", "zwei"]}), [])


class Numbers(unittest.TestCase):
    MATERIAL = ("Der Oberrheingraben ist etwa 300 Kilometer lang und 30 bis 40 Kilometer breit. Er entstand vor rund "
                "45 Millionen Jahren. 133.000 Menschen; Niederschlag 5,5 mm.")

    def test_numbers_without_a_source_go(self):
        have = folien.known(self.MATERIAL)
        sec = {"heading": "Ein Graben von 300 km", "bullets": ["Breite 5–10 km", "Länge 300 km", "3 Gründe", "Im 19. Jahrhundert begradigt"],
               "stats": [{"value": "133000", "label": "Menschen"}, {"value": "1.200", "label": "Brücken"}],
               "steps": [{"label": "45 Mio.", "text": "Beginn"}, {"label": "1817", "text": "Tulla"}]}
        gone = folien.unbacked(sec, have)
        self.assertIn("1.200", gone)
        self.assertIn("1817", gone)
        self.assertNotIn("300", gone)
        self.assertNotIn("19", gone)          # "19. Jahrhundert" needs no source
        n = folien.drop_unbacked(sec, have, "Ein Graben")
        self.assertGreaterEqual(n, 3)
        self.assertEqual(sec["bullets"], ["Länge 300 km", "3 Gründe", "Im 19. Jahrhundert begradigt"])
        self.assertEqual([s["label"] for s in sec["stats"]], ["Menschen"])
        self.assertEqual([s["label"] for s in sec["steps"]], ["45 Mio."])
        self.assertEqual(sec["heading"], "Ein Graben von 300 km")
        self.assertIn("55", have)       # 5,5 → backs "5,5" and "5.5"

    def test_rheingraben_width_would_have_gone(self):
        """Dominik's slides said "Breite 5–10 km"; the article says 30 to 40 km."""
        have = folien.known(self.MATERIAL)
        sec = {"heading": "Lage", "bullets": ["Breite: 5–10 km", "Lage zwischen Schwarzwald und Vogesen"]}
        folien.drop_unbacked(sec, have)
        self.assertEqual(sec["bullets"], ["Lage zwischen Schwarzwald und Vogesen"])

    def test_charts_only_with_real_numbers(self):
        have = folien.known(self.MATERIAL, "Regen: Juni 95, Juli 85, Mai 80")
        origins = [("deine Angaben", folien.known("Regen: Juni 95, Juli 85, Mai 80")), ("Wikipedia „X“ (Kiwix)", folien.known(self.MATERIAL))]
        ok = {"heading": "x", "chart": {"type": "bar", "labels": ["Mai", "Jun", "Jul"], "series": [{"label": "mm", "values": [80, 95, 85]}]}}
        self.assertEqual(folien.check_chart(ok, have, origins), "ok")
        self.assertEqual(ok["chart"]["source"], "deine Angaben")
        self.assertEqual(ok["chart"]["highlight"], "Jun")           # the biggest when the model named none
        pie = {"heading": "x", "chart": {"type": "pie", "labels": ["A", "B"], "series": [{"label": "", "values": [1, 99]}]}}
        self.assertEqual(folien.check_chart(pie, have, origins), "weg")      # two values, 99 without a source
        self.assertNotIn("chart", pie)
        same = {"heading": "x", "chart": {"type": "bar", "labels": ["a", "b", "c"], "series": [{"label": "", "values": [1, 1, 1]}]}}
        self.assertEqual(folien.check_chart(same, have, origins), "weg")
        made_up = {"heading": "x", "chart": {"type": "bar", "labels": ["Länge", "Breite", "Tiefe"],
                                             "series": [{"label": "km", "values": [300, 40, 777]}]}}
        self.assertEqual(folien.check_chart(made_up, have, origins), "zahlen")   # the real ones as big numbers
        self.assertEqual([s["value"] for s in made_up["stats"]], ["300", "40"])


class Symbols(unittest.TestCase):
    def test_fixed_set_in_the_repository(self):
        self.assertGreaterEqual(len(symbole.ROWS), 150)
        self.assertTrue(os.path.isfile(os.path.join(symbole.HERE, "LICENSE-lucide.txt")))
        for k, r in symbole.ROWS.items():
            self.assertTrue(os.path.isfile(os.path.join(symbole.HERE, r["icon"] + ".png")), k)
        self.assertEqual(symbole.pick("berg"), "berg")
        self.assertEqual(symbole.pick("mountain"), "berg")
        self.assertEqual(symbole.pick("", "Die Vulkane am Kaiserstuhl"), "vulkan")
        self.assertEqual(symbole.pick("gibtsnicht", "xyz"), symbole.FALLBACK)
        png = symbole.color("berg", "5B5BF0")
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(symbole.color("berg", "nicht-hex"), b"")
        self.assertEqual(symbole.color("../../etc/passwd", "5B5BF0"), b"")
        # the model's word is checked: an unknown one never reaches a file name
        s = docmake.check_section({"heading": "x", "points": [{"icon": "../../x", "title": "Wasser im Graben", "text": "t"}]})
        self.assertIn(s["points"][0]["icon"], symbole.ROWS)


DECK = {"kind": "praesentation", "title": "Der Oberrheingraben", "subtitle": "Test", "lang": "de", "sections": [
    {"layout": "kapitel", "heading": "Wie er entstand", "paras": ["Vor langer Zeit"]},
    {"layout": "symbole", "heading": "Vier Kräfte", "points": [{"icon": "berg", "title": "Gebirge", "text": "heben sich"},
                                                               {"icon": "wasser", "title": "Rhein", "text": "füllt"},
                                                               {"icon": "vulkan", "title": "Vulkan", "text": "Kaiserstuhl"}]},
    {"layout": "zahlen", "heading": "Groß", "stats": [{"value": "300 km", "label": "lang"}, {"value": "40 km", "label": "breit"}]},
    {"layout": "ablauf", "heading": "Ablauf", "steps": [{"label": "früh", "text": "Dehnung"}, {"label": "später", "text": "Meer"},
                                                        {"label": "heute", "text": "sinkt"}]},
    {"layout": "kernaussage", "heading": "Darum", "quote": "Ein Riss mitten in Europa."},
    {"layout": "vergleich", "heading": "Abwägen", "compare": {"left": {"title": "Chancen", "points": ["Wärme"]},
                                                              "right": {"title": "Risiken", "points": ["Beben"]}}},
    {"layout": "bildtext", "heading": "Kaiserstuhl", "paras": ["Ein Vulkan."], "wikipic": {"id": "aaaaaaaaaaaa_bbbbbbbbbb", "credit": "Bild: Wikipedia"}},
    {"layout": "diagramm", "heading": "Regen", "paras": ["Im Sommer am meisten."], "chart": {
        "type": "bar", "labels": ["Mai", "Jun", "Jul"], "series": [{"label": "mm", "values": [80, 95, 85]}], "highlight": "Jun", "source": "Kiwix"}},
    {"layout": "fazit", "heading": "Fazit", "bullets": ["Er sinkt", "Er wärmt"], "notes": "Danke."}],
    "cover": {"id": "aaaaaaaaaaaa_bbbbbbbbbb", "credit": "Bild: Wikipedia"}}


def _pic(path):
    from PIL import Image
    Image.new("RGB", (800, 500), (30, 90, 140)).save(path)
    return path


class Render(unittest.TestCase):
    def test_every_type_in_every_format(self):
        c = docmake.check_content(DECK)
        self.assertEqual([s["layout"] for s in c["sections"]], [s["layout"] for s in DECK["sections"]])
        self.assertEqual(c["cover"]["id"], "aaaaaaaaaaaa_bbbbbbbbbb")
        pic = _pic(os.path.join(tempfile.mkdtemp(), "folien-test.jpg"))

        def res(s):
            return []
        res.wiki = lambda s: pic if s.get("wikipic") else None
        res.cover = lambda c_: pic
        for st in docrender.STYLES:
            data = docrender.render(c, "pptx", st, res)
            z = zipfile.ZipFile(io.BytesIO(data))
            slides = [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
            self.assertEqual(len(slides), 1 + 1 + len(c["sections"]))        # title, overview, one per part
            xml = "".join(z.read(n).decode() for n in slides)
            self.assertEqual(re.findall(r'\s(?:x|y|cx|cy)="-?\d+\.\d*"', xml), [])
            for word in ("Gebirge", "Dehnung", "Chancen", "Ein Riss mitten in Europa.", "Er wärmt", "Quelle: Kiwix"):
                self.assertIn(word, xml, (st, word))
            self.assertGreaterEqual(len([n for n in z.namelist() if n.startswith("ppt/media/")]), 3)   # symbols, picture
        for fmt in ("docx", "pdf", "md", "txt"):
            data = docrender.render(c, fmt, "spark-hell", res)
            self.assertTrue(data)
        md = docrender.render(c, "md").decode()
        for word in ("Gebirge: heben sich", "früh: Dehnung", "Chancen: Wärme", "Risiken: Beben"):
            self.assertIn(word, md)
        z = zipfile.ZipFile(io.BytesIO(docrender.render(c, "docx", "spark-hell", res)))
        body = z.read("word/document.xml").decode()
        for word in ("Gebirge", "Dehnung", "Chancen", "Bild: Wikipedia"):
            self.assertIn(word, body)
        # an own template: the types become bullets, nothing is lost
        from pptx import Presentation
        b = io.BytesIO()
        Presentation().save(b)
        z = zipfile.ZipFile(io.BytesIO(docrender.render(c, "pptx", "spark-hell", res, io.BytesIO(b.getvalue()))))
        xml = "".join(z.read(n).decode() for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n))
        self.assertIn("Gebirge: heben sich", xml)

    def test_preview_line_for_typed_slides(self):
        c = docmake.check_content(dict(DECK, sections=DECK["sections"][1:2]))
        self.assertIn("Gebirge: heben sich", docmake.peek(c)["lines"])


def fake_model(answers):
    calls = []

    async def model(msgs, schema, tokens):
        calls.append(msgs)
        return answers[min(len(calls), len(answers)) - 1]
    return model, calls


class Writing(unittest.TestCase):
    def setUp(self):
        self.model = docmake._model

    def tearDown(self):
        docmake._model = self.model

    def plan(self, layout="liste"):
        return {"kind": "praesentation", "format": "pptx", "title": "Oberrheingraben", "lang": "de", "length": "mittel",
                "wish": "Präsentation über den Oberrheingraben", "facts": "", "sections": [{"heading": "Lage", "note": "", "layout": layout}]}

    def test_one_more_try_then_the_rules(self):
        import json
        bad = json.dumps({"heading": "Lage", "layout": "liste", "bullets": [
            "Der Graben ist fünf bis zehn Kilometer breit und liegt zwischen zwei Gebirgen im Westen und Osten",
            "Breite 5–10 km", "a", "b", "c", "d"]})
        docmake._model, calls = fake_model([bad, bad])
        have = folien.known(Numbers.MATERIAL)
        tally = {}
        sec = asyncio.run(docmake.write_part(self.plan(), 0, Numbers.MATERIAL, have=have, origins=[], tally=tally))
        self.assertEqual(len(calls), 2)                       # asked once more, with what was wrong
        again = calls[1][-1]["content"]
        self.assertIn("lass sie weg: 10", again)            # "5" is in the material (5,5 mm), "10" is not
        self.assertIn("Stichpunkte", again)
        self.assertEqual(tally.get("retries"), 1)
        self.assertGreaterEqual(tally.get("dropped"), 1)
        self.assertNotIn("Breite 5–10 km", sec.get("bullets") or [])
        self.assertLessEqual(len(sec.get("bullets") or sec.get("points")), 4)
        self.assertIn(sec["layout"], folien.LAYOUTS)

    def test_good_answer_needs_no_second_try(self):
        import json
        good = json.dumps({"heading": "Ein Graben von 300 Kilometern", "layout": "zahlen",
                           "stats": [{"value": "300 km", "label": "lang"}, {"value": "30–40 km", "label": "breit"}],
                           "notes": "Von Basel bis Frankfurt."})
        docmake._model, calls = fake_model([good])
        sec = asyncio.run(docmake.write_part(self.plan("zahlen"), 0, Numbers.MATERIAL,
                                             have=folien.known(Numbers.MATERIAL), origins=[], tally={}))
        self.assertEqual(len(calls), 1)
        self.assertEqual(sec["layout"], "zahlen")
        self.assertEqual(len(sec["stats"]), 2)
        # the writer is told the type and the symbols it may use
        self.assertIn("FOLIENTYP: zahlen", calls[0][-1]["content"])
        self.assertIn("SYMBOLE: ", calls[0][-1]["content"])

    def test_spreadsheet_numbers_are_the_persons_own(self):
        plan = self.plan()
        plan["kind"] = "tabelle"
        _, _, have = asyncio.run(docmake.material("nobody", plan, "", None))
        self.assertIsNone(have)


class KiwixPictures(unittest.TestCase):
    PAGE = ('<html><body><table class="infobox"><img src="../I/Flag_of_Germany.svg.png.webp" width="300" height="200">'
            '<img src="../I/tiny.jpg.webp" width="40" height="30"><img src="https://evil.example/x.jpg" width="600">'
            '<img src="../../other/I/x.jpg" width="600"><img src="../I/Kaiserstuhl.jpg.webp" width="320" height="240">'
            '</table></body></html>')

    def setUp(self):
        import json
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            chat = json.load(f)["chat"]
        self.kept = {k: chat.get(k) for k in ("documents", "doc_make", "doc_make_wikipics")}   # other tests expect them
        self.get, self.base = kiwix._get, kiwix.base
        self.asked = []

        async def get(path, params=None, most=kiwix.SMALL_BYTES, under=None, raw=False):
            self.asked.append((path, raw, most))
            if not raw:
                return self.PAGE, "/content/wikipedia_de/A/Kaiserstuhl"
            return b"picture-bytes", path
        kiwix._get = get
        kiwix.base = lambda: "http://kiwix.lan:8080"

    def tearDown(self):
        kiwix._get, kiwix.base = self.get, self.base
        helpers.set_config(**self.kept)

    def test_first_real_photo_of_the_article_only_inside_the_book(self):
        data = asyncio.run(kiwix.picture("wikipedia_de", "A/Kaiserstuhl"))
        self.assertEqual(data, b"picture-bytes")
        pics = [p for p, raw, _ in self.asked if raw]
        self.assertEqual(pics, ["/content/wikipedia_de/I/Kaiserstuhl.jpg.webp"])
        self.assertTrue(all(most <= kiwix.PICTURE_BYTES for _, raw, most in self.asked if raw))
        self.assertIsNone(asyncio.run(kiwix.picture("../etc", "A/x")))
        self.assertIsNone(asyncio.run(kiwix.picture("wikipedia_de", "../../x")))

    def test_pictures_are_checked_and_saved_anew(self):
        from PIL import Image
        _, uid = profile("FolienBild")
        b = io.BytesIO()
        Image.new("RGB", (3000, 2000), (10, 20, 30)).save(b, "PNG")
        pid = docmake.keep_picture(uid, "abcdefabcdef", b.getvalue())
        self.assertRegex(pid, docmake.WIKIPIC.pattern)
        path = docmake._pic_path(uid, pid)
        with Image.open(path) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), docmake.PICTURE_SIDE)
        self.assertEqual(docmake.keep_picture(uid, "abcdefabcdef", b"<svg onload=alert(1)>"), "")
        self.assertEqual(docmake.keep_picture(uid, "abcdefabcdef", b"\x89PNG broken"), "")
        self.assertIsNone(docmake._pic_path(uid, "../../profiles"))
        docmake.drop_pictures(uid, "abcdefabcdef")
        self.assertIsNone(docmake._pic_path(uid, pid))

    def test_switch_is_off_by_default_and_needs_both(self):
        self.assertIn("erstellenbilder", features.BY_KEY)
        self.assertEqual(features.BY_KEY["erstellenbilder"].parent, "erstellen")
        _, uid = profile("FolienSchalter")
        helpers.set_config(documents=True, doc_make=True, doc_make_wikipics=False)
        self.assertFalse(docmake.pictures_on(uid))
        helpers.set_config(doc_make_wikipics=True)
        self.assertFalse(docmake.pictures_on(uid))             # the profile's own switch is still off
        profiles.save_settings(uid, {"doc_make_wikipics": True})
        self.assertTrue(docmake.pictures_on(uid))
        # with both on but no Kiwix for the profile nothing is fetched; a "Bild und Text" slide becomes another type
        plan = {"kind": "praesentation", "format": "pptx", "title": "T", "lang": "de",
                "sections": [{"heading": "A", "layout": "symbole"}, {"heading": "B", "layout": "bildtext"}]}
        asyncio.run(docmake.wiki_pictures(uid, "abcdefabcdef", plan))
        self.assertNotIn("cover", plan)
        self.assertNotEqual(plan["sections"][1]["layout"], "bildtext")
        self.assertNotEqual(plan["sections"][0]["layout"], plan["sections"][1]["layout"])
        helpers.set_config(doc_make_wikipics=False)

    def test_pictures_come_with_kiwix_and_switches(self):
        from PIL import Image
        _, uid = profile("FolienKiwix")
        helpers.set_config(documents=True, doc_make=True, doc_make_wikipics=True)
        profiles.save_settings(uid, {"doc_make_wikipics": True})
        b = io.BytesIO()
        Image.new("RGB", (900, 600), (200, 100, 50)).save(b, "JPEG")
        usable, pic = kiwix.usable, kiwix.picture_of

        async def picture_of(q):
            return b.getvalue(), "Kaiserstuhl"
        kiwix.usable, kiwix.picture_of = (lambda u: True), picture_of
        try:
            plan = {"kind": "praesentation", "format": "pptx", "title": "Kaiserstuhl", "lang": "de",
                    "sections": [{"heading": "A", "layout": "symbole"}, {"heading": "B", "layout": "bildtext"}]}
            tally = {}
            asyncio.run(docmake.wiki_pictures(uid, "abcdefabcdef", plan, None, tally))
        finally:
            kiwix.usable, kiwix.picture_of = usable, pic
            helpers.set_config(doc_make_wikipics=False)
        self.assertIn("Kaiserstuhl", plan["cover"]["credit"])
        self.assertEqual(plan["sections"][1]["layout"], "bildtext")
        self.assertTrue(docmake._pic_path(uid, plan["sections"][1]["wikipic"]["id"]))
        self.assertEqual(tally["pictures"], 2)
        docmake.drop_pictures(uid, "abcdefabcdef")

    def test_facts_from_the_kiwix_back_the_numbers(self):
        _, uid = profile("FolienFakten")
        usable, facts = kiwix.usable, kiwix.facts

        async def fake_facts(q, most=4500):
            return "Oberrheingraben", Numbers.MATERIAL
        kiwix.usable, kiwix.facts = (lambda u: True), fake_facts
        try:
            plan = {"kind": "praesentation", "title": "Oberrheingraben", "lang": "de", "wish": "", "facts": "",
                    "sections": [{"heading": "Lage", "note": ""}]}
            text, origins, have = asyncio.run(docmake.material(uid, plan, "", None))
        finally:
            kiwix.usable, kiwix.facts = usable, facts
        self.assertIn("Wikipedia (Kiwix), Artikel „Oberrheingraben“", text)
        self.assertIn("300", have)
        self.assertIn("Wikipedia „Oberrheingraben“ (Kiwix)", [o[0] for o in origins])
        self.assertIn("Zahlen geprüft mit Kiwix", docmake.check_line({"numbers": True, "kiwix": True, "dropped": 2}))


if __name__ == "__main__":
    unittest.main()
