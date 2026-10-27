"""Every document the Spark puts on the reMarkable reads its text with one reader (rmpapier.blocks) and is well formed
(Dominik 2026-10-21 „alle Dokumente auf dem reMarkable gut formatiert“, „1a 2a 3a 4a 5a“): no Markdown marks left, a
numbered list stays a list, a table a table, nothing past the right margin, documents in the device's own format.
A new kind of document (rmpapier.ARTEN) without a sample here makes this test red."""
import io
import os
import re
import unittest
import zipfile

from tests import helpers

helpers.start()
import docmake  # noqa: E402
import docrender  # noqa: E402
import remarkable  # noqa: E402
import rmaufgaben  # noqa: E402
import rmpapier  # noqa: E402

# every part a model or a briefing writes: headings, bold parts, lines, lists, numbers, a table, a link, a quote, an emoji
SAMPLE = """Hier ist das Rezept für **Kirschkuchen** vom Blech 🍒:

## Zutaten
- 250 g Butter
- 200 g *Zucker*

**Zubereitung**
1. Ofen auf 180 °C vorheizen.
2. Butter und Zucker schaumig rühren.
3. Teig aufs Blech, 40 Minuten backen.

| Schritt | Zeit |
|---|---|
| Rühren | 10 min |
| Backen | 40 min |

> Tipp: mit Puderzucker bestäuben.

Mehr: [Chefkoch](https://www.chefkoch.de/kirschkuchen)
Guten Appetit!
Donaudampfschifffahrtsgesellschaftskapitänsmütze"""
MARKS = re.compile(r"\*\*|##|\|\s*-{2,}|\]\(|`|(?<!\w)\*\w|\w\*(?!\w)")
TODO = [{"id": "a1b2c3d4", "text": "Müll rausbringen", "at": "08:00"}]
ITS = [{"key": "todo:00000000000000a1", "src": "todo", "id": "00000000000000a1", "text": "Steuer abschicken", "sub": ""}]


def designed(label):
    return lambda m: rmpapier.build_text(m, label, "Titel " + label, SAMPLE)[0]


# kind -> how its document is made: per model as a designed sheet, and the way it goes without „Gestaltete Blätter“
KINDS = {
    "aufgaben": (lambda m: rmaufgaben.build(m, ITS, 2, [], "21.10.2026")[0], None),
    "morgen": (lambda m: rmpapier.build_morning(m, "Guten Morgen", "Dienstag", SAMPLE, TODO)[0], "plain"),
    "woche": (designed("Wochenrückblick"), "plain"),
    "besprechung": (designed("Besprechung"), "epub"),
    "antwort": (designed("Antwort"), "epub"),
    "eingang": (designed("Eingang"), "epub"),
    "web": (None, "epub"),                       # web pages stay EPUB (Dominik 3a)
    "archiv": (None, None),                      # only a folder: the documents of the other kinds go there
    "dungeon": (None, None),                     # only a folder: the hero books and their notes have their own layout,
                                                 # checked on every model in test_dungeon_buch (nothing outside the page)
    "anleitung": (designed("Anleitung"), "epub"),
    "kalibrierung": (lambda m: rmpapier.build_calibration(m)[0], None),
}


def pdf_text(pdf):
    from pypdf import PdfReader
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]


def past_margin(pdf, m):
    """Dark pixels right of the text area (between the margin and the corner marks), page by page."""
    import pypdfium2 as pdfium
    W, H = m["mm"]
    margin = 7.0 if W < 120 else 11.0
    out = []
    for i, page in enumerate(pdfium.PdfDocument(pdf)):
        img = page.render(scale=4).to_pil().convert("L")
        px = img.width / W
        x0, x1 = int((W - margin + 0.9) * px), int((W - 4.2) * px)
        y0, y1 = int(14 * px), int((H - 12) * px)
        if x1 > x0 and min(img.crop((x0, y0, x1, y1)).getdata()) < 120:
            out.append(i + 1)
    return out


class Reader(unittest.TestCase):
    def test_blocks_keep_lists_numbers_tables_and_lines(self):
        kinds = [k for k, _ in rmpapier.blocks(SAMPLE)]
        self.assertEqual(kinds, ["p", "h", "ul", "h", "ol", "table", "quote", "p"])
        b = dict((k, d) for k, d in rmpapier.blocks(SAMPLE))
        self.assertEqual(b["ol"], [("1", "Ofen auf 180 °C vorheizen."), ("2", "Butter und Zucker schaumig rühren."),
                                   ("3", "Teig aufs Blech, 40 Minuten backen.")])
        self.assertEqual(b["table"], [["Schritt", "Zeit"], ["Rühren", "10 min"], ["Backen", "40 min"]])
        self.assertEqual(b["ul"], ["250 g Butter", "200 g Zucker"])
        self.assertEqual(rmpapier.blocks(SAMPLE)[-1][1][0], "Mehr: Chefkoch (https://www.chefkoch.de/kirschkuchen)")
        self.assertEqual(len(rmpapier.blocks(SAMPLE)[-1][1]), 3)       # a single line break stays one

    def test_a_rule_is_no_list_and_a_wide_table_becomes_lines(self):
        self.assertEqual(rmpapier.blocks("a\n\n---\n\nb")[1], ("hr", None))
        wide = "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |"
        text = "".join(pdf_text(rmpapier.build_text(rmpapier.model("move"), "Antwort", "T", wide)[0]))
        self.assertIn("A: 1", text)
        self.assertNotIn("|", text)

    def test_no_gap_where_an_emoji_was(self):
        self.assertEqual(rmpapier.clean("vom Blech 🍒:"), "vom Blech:")


class EveryKind(unittest.TestCase):
    def test_every_kind_has_a_sample(self):
        self.assertEqual(set(KINDS) - {"kalibrierung", "anleitung"}, set(rmpapier.ARTEN))

    def test_designed_sheets_are_clean_on_every_model(self):
        for kind, (make, _) in KINDS.items():
            if not make:
                continue
            for key in rmpapier.MODELS:
                m = rmpapier.model(key)
                pdf = make(m)
                text = "\n".join(pdf_text(pdf))
                self.assertIsNone(MARKS.search(text), f"{kind} {key}: {MARKS.search(text)}")
                self.assertEqual(past_margin(pdf, m), [], f"{kind} {key}")
                if make.__name__ == "<lambda>" and "Ofen" in text:
                    self.assertRegex(text, r"(?m)^1\.\s*Ofen", f"{kind} {key}")      # numbers stay on their own lines
                    self.assertRegex(text, r"(?m)^2\.\s*Butter", f"{kind} {key}")

    def test_plain_sheets_and_epubs_are_clean(self):
        for kind, (_, plain) in KINDS.items():
            if plain == "plain":
                text = "\n".join(pdf_text(rmpapier.plain_pdf("nobody", kind, "Titel", SAMPLE)))
                self.assertIsNone(MARKS.search(text), kind)
                self.assertIn("Zubereitung", text)
            elif plain == "epub":
                x = zipfile.ZipFile(io.BytesIO(remarkable.epub("Titel", SAMPLE))).read("text.xhtml").decode()
                self.assertIsNone(MARKS.search(re.sub(r"<[^>]+>", " ", x)), kind)
                for tag in ("<h2>Zutaten</h2>", "<ol>", "<table>", "<blockquote>", "<br/>"):
                    self.assertIn(tag, x, kind)

    def test_documents_go_in_the_device_format(self):
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from test_docmake import SAMPLE as DOC
        c = docmake.check_content(DOC)
        for key in rmpapier.MODELS:
            m = rmpapier.model(key)
            pdf = docrender.render(c, "pdf", "spark-hell", page=m["mm"])
            import pypdfium2 as pdfium
            w, h = pdfium.PdfDocument(pdf)[0].get_size()
            self.assertAlmostEqual(w / 72 * 25.4, m["mm"][0], delta=0.5)
            self.assertAlmostEqual(h / 72 * 25.4, m["mm"][1], delta=0.5)


if __name__ == "__main__":
    unittest.main()
