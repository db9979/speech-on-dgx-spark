"""Neu verfügbar (modelleneu.py, Dominik 2026-11-16 „1-6“ point 6, stage D2): off by default; once a day the newest
models of fixed publishers only, through the quick rules of the search, at most NEU_TAGE old, never one of the catalog;
only a hint, nothing downloaded. No network: the answers are given. Time from fixed numbers, never the clock."""
import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import modelle  # noqa: E402
import modelleneu  # noqa: E402
import modellseite  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = 1_800_000_000.0           # 2027-01-15


def item(repo, tage, arch="Qwen3ForCausalLM", tag="text-generation"):
    import datetime
    c = datetime.datetime.fromtimestamp(NOW - tage * 86400, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return {"id": repo, "createdAt": c, "downloads": 3, "tags": ["safetensors"], "pipeline_tag": tag,
            "config": {"architectures": [arch]}, "safetensors": {"parameters": {"BF16": 4_000_000_000}},
            "cardData": {"license": "apache-2.0"}}


class Regeln(unittest.TestCase):
    def test_off_by_default_and_only_fixed_publishers(self):
        with open(os.path.join(HERE, "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["modelle_neu"], False)
        self.assertIn("author=Qwen&", modelle.neu_url("Qwen"))
        for bad in ("evil", "Qwen&x=1", "../x", ""):
            with self.assertRaises(modelle.Fehler):
                modelle.neu_url(bad)

    def test_new_fitting_and_not_in_the_catalog(self):
        kat = modelle.katalog(eigene=[])
        schon = next(m["repo"] for m in kat.values() if m["art"] == "llm" and m["repo"])
        items = [item("Qwen/neu-4b", 3), item("Qwen/alt-4b", modelle.NEU_TAGE + 1), item(schon, 1),
                 item("Qwen/stimme", 2, tag="text-to-speech"), item("Qwen/kaputt", 1) | {"createdAt": "gestern"},
                 item("Qwen/fremd", 1, arch="UnknownForCausalLM")]
        got = modelle.neu_auswahl(items, "llm", 121.0, kat, now=NOW)
        self.assertEqual([(x["repo"], x["art"], x["tage"]) for x in got], [("Qwen/neu-4b", "llm", 3)])

    def test_once_a_day_only_when_on(self):
        p = mock.patch.object(modelleneu, "NEU", os.path.join(tempfile.mkdtemp(), "neu.json"))
        p.start()
        self.addCleanup(p.stop)
        with mock.patch.object(modelleneu, "an", return_value=False):
            self.assertFalse(modelleneu.faellig(now=NOW))
        with mock.patch.object(modelleneu, "an", return_value=True):
            self.assertTrue(modelleneu.faellig(now=NOW))
            modelleneu.write_json(modelleneu.NEU, {"zeit": NOW - 3600})
            self.assertFalse(modelleneu.faellig(now=NOW))
            self.assertTrue(modelleneu.faellig(now=NOW - 3600 + modelleneu.ALLE_S))

    def test_the_daily_look_keeps_hints_only(self):
        p = mock.patch.object(modelleneu, "NEU", os.path.join(tempfile.mkdtemp(), "neu.json"))
        p.start()
        self.addCleanup(p.stop)
        gefragt = []

        async def holen(h):
            gefragt.append(h)
            return None if h == "google" else [item(f"{h}/neu-4b", 2)] if h == "Qwen" else []

        async def fam(art, kat=None):
            return ()
        with mock.patch.object(modellseite, "_familien", fam), mock.patch.object(modelleneu, "an", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            got = asyncio.run(modelleneu.lauf(now=NOW, holen=holen))
            z = modelleneu.zeigen()
        self.assertEqual(gefragt, list(modelle.NEU_HERAUSGEBER))
        self.assertEqual([x["repo"] for x in got], ["Qwen/neu-4b"])
        self.assertEqual((z["fehler"], z["treffer"][0]["art_name"]), (1, modelle.ARTEN["llm"][0]))
        self.assertIn("modelle: neu 1 treffer 1 fehler", out.getvalue())
        with open(os.path.join(HERE, "..", "panel", "static", "js", "modelle.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("mdNeu(d.neu,w)", js)


if __name__ == "__main__":
    unittest.main()
