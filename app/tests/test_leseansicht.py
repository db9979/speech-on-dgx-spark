"""Leseansicht (Dominik 2026-11-17, „Dokumente suchen und lesen“: „die Suche und danach das Dokument öffnen ist schlecht
umgesetzt, das Lesen im schmalen Band rechts unübersichtlich“): ein Dokument liest sich in einer eigenen Ansicht über
die ganze Fläche (lesen.js), öffnet an der Fundstelle, markiert die Wörter der Suche und zählt „1 von N“.

Server: documents.text_of gibt die Stücke ohne ihre Überlappung, mit Nummer (n) und Überschriften (part), dazu das
Inhaltsverzeichnis (heads) und mit um= den Teil um ein Stück weit hinten in einem langen Dokument; die Suche nennt je
Treffer sein Stück (n). Browser: Treffer anklicken → Leseansicht an der Stelle, Fremdtext bleibt Text."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel"))

from tests import helpers  # noqa: E402
from tests import test_ui_browser as T  # noqa: E402  (a module: its tests do not run twice)

TITEL = ["Mietsache", "Mietzeit", "Miete", "Nebenkosten", "Kaution", "Nutzung", "Reparaturen", "Schönheitsreparaturen",
         "Kündigung", "Haustiere", "Untermiete", "Bauliche Änderungen"]


def vertrag(boese=""):
    """A lease with a heading per paragraph; the word Kündigung only in § 9 (twice) and § 12."""
    out = []
    for i, t in enumerate(TITEL, 1):
        body = f"Absatz {i}: Der Mieter behandelt die Wohnung pfleglich und lüftet regelmäßig. " * 5
        if i == 9:
            body += "Die Kündigungsfrist beträgt drei Monate. Eine Kündigung bedarf der Schriftform." + boese
        if i == 12:
            body += "Nach einer Kündigung wird alles zurückgebaut."
        out.append(f"§ {i} {t}\n{body}")
    return "\n\n".join(out)


def ensure_user(name, pin):
    import profiles
    try:
        profiles.add_user(name, pin)
    except Exception:
        pass   # already there from an earlier test
    return next(u for u in profiles._load()["users"] if u["name"] == name)["id"]


class Text(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        helpers.set_config(documents=True)
        cls.uid = ensure_user("Lesetext", "4712")

    def doc(self, text):
        import documents
        d = documents.add(self.uid, "Vertrag.txt", text.encode(), text=text, source="upload")
        self.addCleanup(documents.delete, self.uid, d["id"])
        return d["id"]

    def test_pieces_without_their_overlap(self):
        """The pieces overlap by about OVERLAP characters (the search finds a sentence on a border); read one after
        another, nothing comes twice and nothing is lost."""
        import documents
        text = vertrag()
        got = documents.text_of(self.uid, self.doc(text))
        self.assertGreater(len(got["parts"]), 3)
        joined = " ".join(" ".join(p["text"].split()) for p in got["parts"])
        self.assertEqual(joined.count("Absatz 5:"), 5)                 # each sentence once, not again in the next piece
        self.assertLessEqual(len(joined), len(" ".join(text.split())) + 50)
        for i in range(1, len(TITEL) + 1):
            self.assertIn(f"Absatz {i}:", joined)
        self.assertEqual([p["n"] for p in got["parts"]], sorted(p["n"] for p in got["parts"]))

    def test_contents_and_place(self):
        """heads: each heading once with the piece it starts in; um= on a long document starts a few pieces before
        that piece (a hit far in the back), a document that fits whole opens whole."""
        import documents
        did = self.doc(vertrag())
        got = documents.text_of(self.uid, did)
        names = [h["t"] for h in got["heads"]]
        self.assertIn("§ 9 Kündigung", names)
        self.assertEqual(len(names), len(set(names)))
        last = got["parts"][-1]["n"]
        self.assertEqual(documents.text_of(self.uid, did, um=last)["start"], 0)
        small = documents.text_of(self.uid, did, most=100, um=last)
        self.assertEqual(small["start"], len(got["parts"]) - 1 - documents.UM_DAVOR)
        self.assertEqual(small["parts"][0]["n"], got["parts"][small["start"]]["n"])

    def test_search_names_the_piece(self):
        """A hit carries its piece, so the Leseansicht opens there (Suche, Assistent)."""
        import documents
        did = self.doc(vertrag())
        hits = [h for h in documents.search(self.uid, "Kündigung", k=5) if h["id"] == did]
        self.assertTrue(hits)
        pieces = {p["n"]: p["text"] for p in documents.text_of(self.uid, did)["parts"]}
        self.assertTrue(all(isinstance(h["n"], int) and "Kündigung" in pieces[h["n"]] for h in hits))

    def test_endpoint_takes_um(self):
        import documents
        did = self.doc(vertrag())
        import panel
        from fastapi.testclient import TestClient
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/profile/login", json={"name": "Lesetext", "pin": "4712"}).status_code, 200)
        r = c.get(f"/api/profile/wissen/{did}/text?um=3")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("heads", r.json())
        self.assertEqual(c.get(f"/api/profile/wissen/{did}/text?um=x").status_code, 422)
        self.assertTrue(documents.has_doc(self.uid, did))


@unittest.skipUnless(T.browser_ok(), "no Playwright/Chromium here")
class Lesen(T.Browser):
    def test_lese_hit_opens_at_the_place(self):
        """Ich → Dokumente, Suche „Kündigung“ + Enter, Treffer anklicken: die Leseansicht deckt Ich ab, öffnet an der
        Stelle (die aktuelle Markierung steht im Stück des Treffers), zählt „1 von N“, ⌄ geht weiter, das
        Inhaltsverzeichnis zeigt § 9 mit Treffer; Text aus dem Dokument bleibt Text (kein <img> aus dem Dokument);
        Esc schließt und gibt den Platz zurück. Am Rechner und am Handy, mit strenger CSP, ohne seitliches Rollen."""
        import documents
        me = ensure_user("Lesetest", "4713")
        text = vertrag(boese=' <img src=x id="boese"> <b>fett</b>')
        d = documents.add(me, "Mietvertrag.txt", text.encode(), text=text, source="upload")
        self.addCleanup(documents.delete, me, d["id"])

        async def go():
            async with T.async_playwright() as p:
                for name, w, h in T.VIEWS:
                    br, pg, errors = await self.page(p, w, h, csp=True, who=("Lesetest", "4713"))
                    await pg.evaluate("openMe('docbox')")
                    await pg.wait_for_selector("#doclist .ld-row", timeout=20000)
                    await pg.fill("#docfind", "Kündigung")
                    await pg.press("#docfind", "Enter")
                    await pg.wait_for_selector("#dochits .dhit", timeout=20000)
                    n = await pg.get_attribute("#dochits .dhit >> nth=0", "data-n")
                    self.assertTrue(n and n.isdigit(), name)
                    await pg.click("#dochits .dhit >> nth=0")
                    await pg.wait_for_selector("#lesemodal #lscol mark.cur", timeout=20000)
                    self.assertTrue(await pg.is_visible("#lesemodal"), name)
                    self.assertIn("Kündigung", await pg.inner_text("#lsbackt"))
                    cur = await pg.evaluate("document.querySelector('#lscol mark.cur').closest('.lsteil').dataset.n")
                    self.assertEqual(cur, n, name)
                    count = await pg.inner_text("#lsn")
                    self.assertRegex(count, r"^\d+ von \d+$", name)
                    total = int(count.split()[-1])
                    self.assertGreaterEqual(total, 3, name)
                    await pg.click("#lsnext")
                    self.assertNotEqual(await pg.inner_text("#lsn"), count, name)
                    if name == "pc":
                        self.assertTrue(await pg.is_visible("#lstoc .lstocx.treffer"), name)
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#boese,#lscol img,#lscol b').length"), 0)
                    self.assertIn('<img src=x id="boese">', await pg.inner_text("#lscol"))
                    over = await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth")
                    self.assertLessEqual(over, 1, f"{name}: {over}px zu breit")
                    await pg.fill("#lsq", "Schriftform")
                    await self.until(pg, "document.getElementById('lsn').textContent==='1 von 1'")
                    await pg.click("#lsback")
                    self.assertFalse(await pg.is_visible("#lesemodal"), name)
                    self.assertEqual(errors, [], name)
        self.run_async(go())


def load_tests(loader, tests, pattern):
    """Only this module's own tests (Lesen borrows the page helpers of test_ui_browser.Browser, not its tests)."""
    suite = unittest.TestSuite(loader.loadTestsFromTestCase(Text))
    suite.addTests(Lesen(m) for m in dir(Lesen) if m.startswith("test_lese"))
    return suite
