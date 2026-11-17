"""Modellsätze (Dominik 2026-11-16 „1-6“ point 4, stage B2): the models running now kept under a checked name (at most
SATZ_MAX), brought back one switch after the other: a switch or measurement still running waits for the next minute,
a refused one is skipped, the set ends by itself. Only admins with a code (stufen.LIST). No time of day."""
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from fastapi import HTTPException

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import modelle  # noqa: E402
import modellseite  # noqa: E402
import stufen  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class Saetze(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.ps = [mock.patch.object(modelle, "SAETZE", os.path.join(d, "s.json")),
                   mock.patch.object(modelle, "SATZ_LAUF", os.path.join(d, "lauf.json"))]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()

    def test_names_size_and_replacing(self):
        modelle.satz_speichern("Alltag", {"llm": "qwen36", "asr": "qwen3-asr-1.7b"}, now=1)
        modelle.satz_speichern("Alltag", {"llm": "gemma4"}, now=2)                # the same name: replaced
        self.assertEqual([(s["name"], s["modelle"]) for s in modelle.saetze()], [("Alltag", {"llm": "gemma4"})])
        for name, inhalt, wort in (("", {"llm": "x"}, "name"), ("../x", {"llm": "x"}, "name"), ("a" * 41, {"llm": "x"}, "name"),
                                   ("Leer", {}, "leer")):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.satz_speichern(name, inhalt)
            self.assertEqual(str(e.exception), wort)
        for i in range(modelle.SATZ_MAX - 1):
            modelle.satz_speichern(f"S{i}", {"llm": "gemma4"})
        with self.assertRaises(modelle.Fehler) as e:
            modelle.satz_speichern("Zuviel", {"llm": "gemma4"})
        self.assertEqual(str(e.exception), "voll")
        modelle.satz_loeschen("S0")
        with self.assertRaises(modelle.Fehler):
            modelle.satz_loeschen("S0")

    def test_a_broken_file_entry_is_left_out(self):
        modelle.write_json(modelle.SAETZE, {"saetze": [{"name": "Gut", "modelle": {"llm": "gemma4"}},
                                                       {"name": "Böse", "modelle": {"chat": "x"}},
                                                       {"name": "../x", "modelle": {"llm": "gemma4"}}]})
        self.assertEqual([s["name"] for s in modelle.saetze()], ["Gut"])

    def test_only_what_differs_in_the_order_of_the_kinds(self):
        kat = modelle.katalog(eigene=[])
        cfg = {"llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4"}, "asr": {"enabled": True, "recognizer": "qwen",
               "model": kat["qwen3-asr-1.7b"]["repo"]}}
        modelle.satz_speichern("A", {"asr": "qwen3-asr-0.6b", "llm": "qwen36-35b-a3b-nvfp4", "tts": "gibt-es-nicht"})
        self.assertEqual(modelle.satz_offen("A", cfg, kat), [["asr", "qwen3-asr-0.6b"]])
        self.assertEqual(modelle.satz_jetzt(cfg, kat), {"llm": "qwen36-35b-a3b-nvfp4", "asr": "qwen3-asr-1.7b"})
        with self.assertRaises(modelle.Fehler):
            modelle.satz_offen("B", cfg, kat)

    def test_one_switch_after_the_other(self):
        modelle.write_json(modelle.SATZ_LAUF, {"name": "A", "offen": [["llm", "gemma4"], ["asr", "x"], ["tts", "y"]]})
        antworten = [HTTPException(409, modellseite.GRUND["laeuft"]), None, HTTPException(400, "nein"), None]

        def wunsch(request, art, was, mid="", seite_zeigen=True):
            self.assertIsNone(request)
            self.assertFalse(seite_zeigen)
            a = antworten.pop(0)
            if a:
                raise a
        with mock.patch.object(modellseite, "_wunsch", wunsch), mock.patch.object(modellseite, "_an", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(modellseite.satz_schritt(), "wartet")
            self.assertEqual(len(modelle.read_json(modelle.SATZ_LAUF, {})["offen"]), 3)
            self.assertEqual(modellseite.satz_schritt(), "angefragt")
            self.assertEqual(modellseite.satz_schritt(), "uebersprungen")
            self.assertEqual(modellseite.satz_schritt(), "angefragt")
            self.assertFalse(os.path.exists(modelle.SATZ_LAUF))
            self.assertEqual(modellseite.satz_schritt(), "")
        log = out.getvalue()
        for line in ("modelle: satz llm angefragt", "modelle: satz asr uebersprungen", "modelle: satz fertig"):
            self.assertIn(line, log)

    def test_switched_off_ends_the_set(self):
        modelle.write_json(modelle.SATZ_LAUF, {"name": "A", "offen": [["llm", "gemma4"]]})
        with mock.patch.object(modellseite, "_an", return_value=False), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(modellseite.satz_schritt(), "ende")
        self.assertIn("modelle: satz aus", out.getvalue())
        self.assertFalse(os.path.exists(modelle.SATZ_LAUF))


class Seite(unittest.TestCase):
    def test_only_admins_with_a_code_and_the_page_shows_them(self):
        for k in (("POST", "/api/admin/modelle/saetze"), ("DELETE", "/api/admin/modelle/saetze"),
                  ("POST", "/api/admin/modelle/saetze/anwenden")):
            self.assertEqual(stufen.LIST[k][0], stufen.CONFIRM, k)
        z = modellseite.saetze_zeigen({})
        self.assertEqual(set(z), {"saetze", "lauf", "max"})
        with open(os.path.join(HERE, "..", "panel", "static", "js", "modelle.js"), encoding="utf-8") as f:
            js = f.read()
        for x in ("mdSaetze(d,w)", "/api/admin/modelle/saetze/anwenden", "data-mdsw"):
            self.assertIn(x, js)


if __name__ == "__main__":
    unittest.main()
