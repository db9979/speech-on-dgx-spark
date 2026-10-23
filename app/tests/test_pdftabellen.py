"""Tables in PDFs read row by row (pdftabellen.py, Dominik 2026-10-23: "welche Sanjeevini-Karte bei Durchfall"
was answered with a wrong card): a row stays one line with its cells, a long table is cut only between rows with
its head in every piece, a page without a drawn table stays as pypdf read it, "Erst lokal" shows the rows with
the question's words instead of the first 500 characters, and PDFs from before are read again in a quiet moment.
The PDFs are made here with fpdf2 (in the panel's lock), so the test runs in a copy with only app/."""
import asyncio
import contextlib
import io
import os
import sqlite3
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import lokal  # noqa: E402
import panel  # noqa: E402
import pdftabellen  # noqa: E402
import profiles  # noqa: E402
import wissen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from fpdf import FPDF  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000.0
ROW = ("Durchfall", "SR 18 Darmflora, SS 25 Durchfall akut",
       "Fluessigkeit ersetzen, bei Kindern frueh zum Arzt gehen, wenn es laenger als zwei Tage dauert")
LINE = "| " + " | ".join(ROW) + " |"


def uid_of(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def fresh(name):
    uid = uid_of(name)
    for d in documents.list_docs(uid):
        documents.delete(uid, d["id"])
    return uid


def table_pdf(n=30, lines=True, align="BOTTOM", size=10):
    """A card table like the one in Dominik's PDF: the complaint at the bottom of its row (the cards wrap above it)."""
    rows = [("Beschwerde", "Sanjeevini Karten", "Hinweis")]
    rows += [(f"Beschwerde {i}", f"SS {i} Karte, NM {i + 40} Nerven", "Hinweis " + "lang " * (i % 3 * 6)) for i in range(n)]
    rows[min(n, 13)] = ROW
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=size)
    pdf.cell(text="Heilkarten Uebersicht")
    pdf.ln(10)
    with pdf.table(text_align="LEFT", v_align=align, borders_layout="ALL" if lines else "NONE",
                   col_widths=(30, 40, 60)) as t:
        for r in rows:
            row = t.row()
            for c in r:
                row.cell(c)
    return bytes(pdf.output())


def prose_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=11)
    pdf.multi_cell(0, 6, text=" ".join(f"Satz {i} ueber die Pflege der Karten im Alltag." for i in range(60)))
    return bytes(pdf.output())


def all_text(data):
    pages, _ = documents.extract_pages("karten.pdf", data)
    return "\n\n".join(t for _, t in pages)


class Reading(unittest.TestCase):
    def test_a_row_stays_one_line(self):
        text = all_text(table_pdf())
        self.assertIn(LINE, text)
        self.assertIn("| Beschwerde | Sanjeevini Karten | Hinweis |", text)
        self.assertIn("Heilkarten Uebersicht", text)       # the text above the table stays

    def test_without_it_the_row_falls_apart(self):
        # what pypdf alone gives (before 2026-10-23): the cells one under the other, the row lost
        with mock.patch.object(pdftabellen, "read", return_value={}):
            text = all_text(table_pdf())
        self.assertNotIn(LINE, text)
        self.assertIn("Durchfall", text)

    def test_top_aligned_and_wrapped_cells_too(self):
        self.assertIn(LINE, all_text(table_pdf(align="TOP")))

    def test_no_drawn_table_stays_as_pypdf_read_it(self):
        data = table_pdf(lines=False)
        with mock.patch.object(pdftabellen, "read", return_value={}):
            plain = all_text(data)
        self.assertEqual(all_text(data), plain)

    def test_prose_stays_as_pypdf_read_it(self):
        data = prose_pdf()
        self.assertEqual(pdftabellen.read(data, {0}), {})
        self.assertFalse(documents.has_tables(data))
        self.assertTrue(documents.has_tables(table_pdf()))

    def test_a_broken_pdf_is_no_table(self):
        self.assertEqual(pdftabellen.read(b"%PDF-1.4 kaputt", {0}), {})

    def test_a_cell_never_breaks_the_row(self):
        self.assertEqual(pdftabellen._cell(" a |\n b\r\n c "), "a / b c")


class Pieces(unittest.TestCase):
    def test_a_long_table_is_cut_between_rows_with_its_head(self):
        pages, _ = documents.extract_pages("karten.pdf", table_pdf(80, size=5))
        self.assertGreater(len(pages[0][1]), documents.TABLE)      # one page, one table longer than TABLE
        table = [p for p, _ in documents.pieces(pages[0][1]) if p.startswith("|")]
        self.assertGreater(len(table), 2)
        for p in table:
            self.assertTrue(p.startswith("| Beschwerde | Sanjeevini Karten | Hinweis |"), p[:80])
            self.assertTrue(all(x.startswith("|") and x.endswith("|") for x in p.split("\n")), p)
            self.assertLessEqual(len(p), documents.CHUNK + 200)
        self.assertEqual(sum(LINE in p for p in table), 1)

    def test_a_short_table_stays_one_piece(self):
        t = "| a | b |\n| 1 | 2 |"
        self.assertEqual(documents.pieces("Vorher.\n\n" + t + "\n\nNachher."), [("Vorher.", ""), (t, ""), ("Nachher.", "")])

    def test_markdown_head_with_its_line(self):
        t = "| Karte | Wofuer |\n|---|---|\n" + "\n".join(f"| SS {i} | Beschwerde {i} mit etwas Text |" for i in range(200))
        got = documents._rows(t)
        self.assertGreater(len(got), 2)
        self.assertTrue(all(p.startswith("| Karte | Wofuer |\n|---|---|\n| SS ") for p in got))

    def test_the_search_finds_the_row(self):
        uid = fresh("Tabelle Suche")
        documents.add(uid, "Sanjeevini.pdf", table_pdf(80))
        hits = documents.search(uid, "welche Sanjeevini Karte kann ich bei Durchfall nehmen", 3)
        self.assertTrue(hits)
        self.assertIn(LINE, hits[0]["text"])


class Excerpt(unittest.TestCase):
    Q = "welche Sanjeevini Karte kann ich bei Durchfall nehmen"

    def test_a_table_gives_its_head_and_the_fitting_rows(self):
        table = next(p for p in documents.pieces(all_text(table_pdf(80))) if LINE in p[0])[0]
        self.assertGreater(len(table), lokal.MAX_HIT_CHARS)
        got = lokal.excerpt(table, lokal.terms(self.Q))
        self.assertEqual(got, "| Beschwerde | Sanjeevini Karten | Hinweis |\n" + LINE)

    def test_text_gives_the_part_with_the_words(self):
        text = "Einleitung ohne Inhalt. " * 60 + "Bei Durchfall hilft die Sanjeevini Karte SS 25. " + "Weiteres. " * 80
        got = lokal.excerpt(text, lokal.terms(self.Q))
        self.assertIn("Durchfall hilft die Sanjeevini Karte SS 25", got)
        self.assertLessEqual(len(got), lokal.MAX_HIT_CHARS + 4)
        self.assertTrue(got.startswith("… ") and got.endswith(" …"), got)

    def test_without_the_words_the_start_as_before(self):
        text = "Ganz anderes Thema. " * 60
        self.assertEqual(lokal.excerpt(text, lokal.terms(self.Q)), lokal._cut(text))
        self.assertEqual(lokal.excerpt("kurz", ["durchfall"]), "kurz")


class Again(unittest.TestCase):
    def test_a_pdf_from_before_is_read_again_in_a_quiet_moment(self):
        uid = fresh("Tabelle Alt")
        doc = documents.add(uid, "Sanjeevini.pdf", table_pdf(), keep=10 * 1024 ** 2)["id"]
        other = documents.add(uid, "Notiz.txt", b"x", text="Der Hund heisst Bello.")["id"]
        con = sqlite3.connect(documents.db_path(uid))          # as read before 2026-10-23: the cells one per line
        with mock.patch.object(pdftabellen, "read", return_value={}):
            plain = all_text(table_pdf())
        con.execute("DELETE FROM chunks WHERE doc=?", (doc,))
        con.execute("INSERT INTO chunks (doc, n, page, text) VALUES (?,?,?,?)", (doc, 0, 1, plain))
        con.execute("UPDATE docs SET tablev=0")
        con.commit()
        con.close()
        self.assertEqual(documents.tables_left(uid), 1)        # the note is no PDF: only marked
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(profiles, "user_ids", return_value=[uid]):
            got = [asyncio.run(wissen.due_once(idle=True, now=NOW)) for _ in range(3)]
        self.assertIn("tabellen", got)
        self.assertIn("wissen: tabellen geprüft | neu gelesen", out.getvalue())
        self.assertNotIn("Durchfall", out.getvalue())
        self.assertEqual(documents.tables_left(uid), 0)
        self.assertIn(LINE, "\n".join(p["text"] for p in documents.text_of(uid, doc)["parts"]))
        self.assertTrue(documents.has_doc(uid, other))

    def test_without_an_original_it_is_only_marked(self):
        uid = fresh("Tabelle Ohne")
        doc = documents.add(uid, "Sanjeevini.pdf", table_pdf())["id"]
        con = sqlite3.connect(documents.db_path(uid))
        con.execute("UPDATE docs SET tablev=0")
        con.commit()
        con.close()
        self.assertEqual(documents.tables_left(uid), 0)        # nothing to read it from
        self.assertEqual(documents.due_tables(uid), "")
        self.assertTrue(documents.has_doc(uid, doc))

    def test_a_pdf_without_a_table_keeps_its_pieces(self):
        uid = fresh("Tabelle Keine")
        doc = documents.add(uid, "Text.pdf", prose_pdf(), keep=10 * 1024 ** 2)["id"]
        con = sqlite3.connect(documents.db_path(uid))
        con.execute("UPDATE docs SET tablev=0")
        con.commit()
        before = [r[0] for r in con.execute("SELECT id FROM chunks WHERE doc=?", (doc,))]
        con.close()
        self.assertEqual(documents.due_tables(uid), "gleich")
        con = sqlite3.connect(documents.db_path(uid))
        self.assertEqual([r[0] for r in con.execute("SELECT id FROM chunks WHERE doc=?", (doc,))], before)
        con.close()
        self.assertEqual(documents.tables_left(uid), 0)


if __name__ == "__main__":
    unittest.main()
