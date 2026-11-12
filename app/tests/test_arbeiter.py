"""Zweiter Prozess für schwere Arbeit (arbeiter.py, Kritische Prüfung 2026-11-12 point 6): a document is built by
docrender in a process of its own, only JSON goes in, only the file's bytes come out, docrender's refusals stay
ValueError. No wall clock dependence.
"""
import contextlib
import io
import unittest

from tests import helpers

helpers.start()
import arbeiter  # noqa: E402
import docrender  # noqa: E402

C = {"title": "Probe", "sections": [{"heading": "Eins", "text": "Ein kurzer Absatz."}]}


class Arbeiter(unittest.TestCase):
    def test_a_document_comes_from_its_own_process(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            md = arbeiter.dokument(C, "md", "spark-hell")
            docx = arbeiter.dokument(C, "docx", "spark-hell")
        self.assertEqual(md, docrender.render(C, "md", "spark-hell"))
        self.assertTrue(docx.startswith(b"PK"))   # a Word file is a zip
        self.assertIn("arbeiter: dokument fertig md", out.getvalue())
        self.assertNotIn("Ein kurzer Absatz", out.getvalue())

    def test_a_refusal_stays_a_value_error(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError) as e:
            arbeiter.dokument(C, "exe", "spark-hell")
        self.assertIn("format", str(e.exception))

    def test_pictures_go_as_paths_only(self):
        def res(s):
            return ["/tmp/a.png"] if s.get("pictures") == ["p1"] else []
        res.wiki = lambda s: "/tmp/w.png"
        res.cover = lambda c: None
        b = arbeiter._bilder({"sections": [{"pictures": ["p1", "p2"], "wikipic": {"id": "w1"}}]}, res)
        self.assertEqual(b, {"pics": {"p1": "/tmp/a.png"}, "wiki": {"w1": "/tmp/w.png"}, "cover": None})
        again = arbeiter._resolver(b)
        self.assertEqual(again({"pictures": ["p1", "p2"]}), ["/tmp/a.png"])
        self.assertEqual(again.wiki({"wikipic": {"id": "w1"}}), "/tmp/w.png")


if __name__ == "__main__":
    unittest.main()
