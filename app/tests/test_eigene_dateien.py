"""Eigene Bild- und Musikmodelle (Dominik 2026-11-16 „alle 1-6“ points 2 and 4, 2026-11-17 „mache das projekt bis zu
ende durch“): an own GGUF file stands in place of the main model of a checked basis variant (modelle.DATEI_ART), size
and SHA-256 from its LFS pointer, never under a catalog file's name; before the switch the model computer fetches it
(checked like every file) and its header must name the same family as the basis's file (bildmodell.gguf_arch); after
the switch a fixed picture or ten seconds of fixed music must come (modelle.datei_probe), else root goes back. Nothing
depends on the time of day."""
import base64
import io
import json
import os
import struct
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import bildmodell  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402
import musikmodell  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SHA = "c" * 40
HASH = "d" * 64
HERE = os.path.dirname(os.path.abspath(__file__))


def info(path="flux-2-klein-4b-fein-Q6_K.gguf", size=3 * 10**9, sha=HASH, **over):
    i = {"id": "beispiel/flux-fein", "sha": SHA, "private": False, "gated": False, "disabled": False,
         "cardData": {"license": "apache-2.0"},
         "siblings": [{"rfilename": "README.md", "size": 100},
                      {"rfilename": path, "size": 134, "lfs": {"sha256": sha, "size": size}}]}
    i.update(over)
    return i


def gguf(arch, extra_before=True):
    """A small GGUF header: version 3, no tensors, a few keys, general.architecture among them."""
    def s(t):
        b = t.encode()
        return struct.pack("<Q", len(b)) + b
    kvs = []
    if extra_before:
        kvs.append(s("general.count") + struct.pack("<I", 4) + struct.pack("<I", 7))
        kvs.append(s("general.tags") + struct.pack("<I", 9) + struct.pack("<IQ", 8, 2) + s("a") + s("bc"))
        kvs.append(s("general.zahlen") + struct.pack("<I", 9) + struct.pack("<IQ", 6, 3) + b"\0" * 12)
    kvs.append(s("general.architecture") + struct.pack("<I", 8) + s(arch))
    return b"GGUF" + struct.pack("<IQQ", 3, 0, len(kvs)) + b"".join(kvs)


class Kopf(unittest.TestCase):
    def test_the_family_comes_from_the_header_with_limits(self):
        d = tempfile.mkdtemp()

        def datei(name, data):
            p = os.path.join(d, name)
            with open(p, "wb") as f:
                f.write(data)
            return p
        self.assertEqual(bildmodell.gguf_arch(datei("a.gguf", gguf("flux"))), "flux")
        self.assertEqual(bildmodell.gguf_arch(datei("b.gguf", gguf("acestep", extra_before=False))), "acestep")
        self.assertEqual(bildmodell.gguf_arch(datei("c.gguf", b"PK\x03\x04" + b"\0" * 40)), "")
        self.assertEqual(bildmodell.gguf_arch(datei("d.gguf", b"GGUF" + struct.pack("<IQQ", 3, 0, 10**9))), "")
        self.assertEqual(bildmodell.gguf_arch(datei("e.gguf", b"GGUF" + struct.pack("<IQQ", 3, 0, 1)
                                                    + struct.pack("<Q", 1 << 40))), "")
        self.assertEqual(bildmodell.gguf_arch(datei("f.gguf", gguf("flux")[:30])), "")
        self.assertEqual(bildmodell.gguf_arch(os.path.join(d, "fehlt.gguf")), "")


class Regeln(unittest.TestCase):
    def test_a_good_file_becomes_an_entry_on_its_basis(self):
        m = modelle.datei_vorschlag(info(), "bild", "beispiel/flux-fein", "flux-2-klein-4b-fein-Q6_K.gguf", "4b-q8", 121)
        self.assertEqual((m["engine"], m["variante"], m["basis"], m["revision"]), ("sdcpp", m["id"], "4b-q8", SHA))
        self.assertEqual(m["datei"], {"path": "flux-2-klein-4b-fein-Q6_K.gguf", "sha256": HASH, "size": 3 * 10**9})
        b = bildmodell.VARIANTS["4b-q8"]
        self.assertEqual(m["need_gib"], max(1, round(b["need_gib"] + (3 * 10**9 - b["model"].size) / 2**30)))
        mus = modelle.datei_vorschlag(info("ace-fein.gguf"), "musik", "beispiel/ace", "ace-fein.gguf", "xl", 121)
        self.assertEqual((mus["engine"], mus["basis"]), ("acestepcpp", "xl"))

    def test_fixed_words_for_what_does_not_fit(self):
        katalogname = bildmodell.VARIANTS["4b-q8"]["model"].name
        for args, wort in ((("bild", "x/y", "fehlt.gguf", "4b-q8"), "format"),
                           (("bild", "x/y", "m.bin", "4b-q8"), "format"),
                           (("bild", "x/y", "../m.gguf", "4b-q8"), "format"),
                           (("bild", "x/y", "flux-2-klein-4b-fein-Q6_K.gguf", "4b-q4"), "basis"),
                           (("musik", "x/y", "flux-2-klein-4b-fein-Q6_K.gguf", "4b-q8"), "basis"),
                           (("asr", "x/y", "flux-2-klein-4b-fein-Q6_K.gguf", "4b-q8"), "art"),
                           (("bild", "x/../y", "flux-2-klein-4b-fein-Q6_K.gguf", "4b-q8"), "repo")):
            with self.assertRaises(modelle.Fehler, msg=args) as e:
                modelle.datei_vorschlag(info(), args[0], args[1], args[2], args[3], 121)
            self.assertEqual(str(e.exception), wort, args)
        for i, wort in ((info(path="../m.gguf"), "format"), (info(sha="nein"), "format"), (info(size=0), "format"),
                        (info(path=katalogname), "format"), (info(size=300 * 10**9), "budget"),
                        (info(private=True), "zugang"), (info(gated="auto"), "zugang")):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.datei_vorschlag(i, "bild", "x/y", i["siblings"][1]["rfilename"], "4b-q8", 121)
            self.assertEqual(str(e.exception), wort)
        self.assertEqual(modelle.datei_vorschlag(info(gated="auto"), "bild", "x/y", "flux-2-klein-4b-fein-Q6_K.gguf",
                                                 "4b-q8", 121, mit_token=True)["revision"], SHA)

    def test_own_file_entries_keep_their_rules(self):
        m = modelle.datei_vorschlag(info(), "bild", "beispiel/flux-fein", "flux-2-klein-4b-fein-Q6_K.gguf", "4b-q8", 121)
        for bad in (dict(m, engine="acestepcpp"), dict(m, variante="4b-q8"), dict(m, basis="xl"), dict(m, wahl="x"),
                    dict(m, datei=dict(m["datei"], path="/etc/x.gguf")), dict(m, datei=dict(m["datei"], extra=1)),
                    dict(m, revision=""), dict(m, empfohlen=["gb10"]), dict(m, eigen=False)):
            with self.assertRaises(modelle.Fehler):
                modelle.eigen_ok(bad)


class Varianten(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.eigene = os.path.join(self.d, "modelle-eigene.json")
        self.bild = modelle.datei_vorschlag(info(), "bild", "beispiel/flux-fein", "flux-2-klein-4b-fein-Q6_K.gguf", "4b-q8", 121)
        self.musik = modelle.datei_vorschlag(info("ace-fein.gguf"), "musik", "beispiel/ace", "ace-fein.gguf", "2b", 121)
        with open(self.eigene, "w") as f:
            json.dump({"modelle": [self.bild, self.musik, {"id": "kaputt", "art": "bild"}]}, f)
        p = mock.patch.object(modelle, "EIGENE", self.eigene)
        p.start()
        self.addCleanup(p.stop)

    def test_own_variants_take_the_basis_except_the_main_file(self):
        v = bildmodell.alle()[self.bild["id"]]
        self.assertEqual(v["model"].name, "flux-2-klein-4b-fein-Q6_K.gguf")
        self.assertEqual((v["model"].sha256, v["model"].repo), (HASH, "beispiel/flux-fein"))
        self.assertEqual(v["llm"], bildmodell.VARIANTS["4b-q8"]["llm"])
        self.assertEqual(bildmodell.files(self.bild["id"])[1:], bildmodell.files("4b-q8")[1:])
        self.assertEqual(bildmodell.variant("unbekannt"), bildmodell.DEFAULT)
        mv = musikmodell.alle()[self.musik["id"]]
        self.assertEqual((mv["dit"].name, mv["lm"]), ("ace-fein.gguf", musikmodell.VARIANTS["2b"]["lm"]))
        self.assertNotIn("kaputt", bildmodell.alle())
        self.assertEqual(set(modelle.katalog()) & {self.bild["id"], self.musik["id"]}, {self.bild["id"], self.musik["id"]})

    def test_switch_way_configuration_and_current(self):
        kat = modelle.katalog()
        self.assertEqual(modelle.wechsel_weg("bild", self.bild), f"datei beispiel/flux-fein {SHA}")
        self.assertEqual(modelle.wechsel_weg("musik", kat["ace-step-15-xl"]), "wahl xl")
        cfg = modelle.mit_wechsel({"image": {"enabled": True}, "music": {"enabled": True}}, "bild", self.bild)
        cfg = modelle.mit_wechsel(cfg, "musik", self.musik)
        self.assertEqual((cfg["image"]["variant"], cfg["music"]["variant"]), (self.bild["id"], self.musik["id"]))
        self.assertEqual(modelle.jetzt_id("musik", cfg, kat), self.musik["id"])
        self.assertEqual(modelle.jetzt_id("bild", cfg, kat), self.bild["id"])
        self.assertIn("musik", modelle.TAUSCH)

    def test_before_the_switch_header_and_basis_decide(self):
        ordner = tempfile.mkdtemp()
        basis = bildmodell.VARIANTS["4b-q8"]["model"]
        with mock.patch.object(bildmodell, "FOLDER", ordner), mock.patch.object(bildmodell, "fetch", return_value=True) as fetch:
            with self.assertRaises(modelle.Fehler) as e:
                modelle.datei_laden(self.bild["id"], log=lambda *a: None)
            self.assertEqual(str(e.exception), "basis")
            fetch.assert_not_called()
            with open(os.path.join(ordner, basis.name), "wb") as f:
                f.write(gguf("flux"))
            with mock.patch.object(bildmodell, "file_size", side_effect=lambda p: basis.size if p.endswith(basis.name) else 0):
                with open(os.path.join(ordner, "flux-2-klein-4b-fein-Q6_K.gguf"), "wb") as f:
                    f.write(gguf("llama"))
                with self.assertRaises(modelle.Fehler) as e:
                    modelle.datei_laden(self.bild["id"], log=lambda *a: None)
                self.assertEqual(str(e.exception), "familie")
                with open(os.path.join(ordner, "flux-2-klein-4b-fein-Q6_K.gguf"), "wb") as f:
                    f.write(gguf("flux"))
                said = []
                modelle.datei_laden(self.bild["id"], log=said.append)
                self.assertEqual(said, ["modelle: datei bild ok"])
                fetch.return_value = False
                with self.assertRaises(modelle.Fehler) as e:
                    modelle.datei_laden(self.bild["id"], log=lambda *a: None)
                self.assertEqual(str(e.exception), "nicht_geladen")
        with self.assertRaises(modelle.Fehler):
            modelle.datei_laden("qwen3-asr-1.7b", log=lambda *a: None)


class Probe(unittest.TestCase):
    def png(self, bunt):
        from PIL import Image
        im = Image.new("RGB", (64, 64), (120, 120, 120))
        if bunt:
            for x in range(64):
                for y in range(0, 64, 2):
                    im.putpixel((x, y), (250, 10, 10))
        b = io.BytesIO()
        im.save(b, "PNG")
        return base64.b64encode(b.getvalue()).decode()

    def test_a_picture_or_music_must_come(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("no Pillow in this venv")
        cfg = {"api": {"key": "k"}, "image": {"port": 1}, "music": {"port": 2}}
        self.assertEqual(modelle.datei_probe("bild", cfg, post=lambda *a: {"png": self.png(True)}), (True, "ok"))
        self.assertEqual(modelle.datei_probe("bild", cfg, post=lambda *a: {"png": self.png(False)}), (False, "leer"))
        mp3 = base64.b64encode(b"\xff" * modelle.DATEI_PROBE_MIN_MP3).decode()
        self.assertEqual(modelle.datei_probe("musik", cfg, post=lambda *a: {"mp3": mp3}), (True, "ok"))
        self.assertEqual(modelle.datei_probe("musik", cfg, post=lambda *a: {"mp3": "AAAA"}), (False, "leer"))

        def kaputt(*a):
            raise OSError("weg")
        self.assertEqual(modelle.datei_probe("bild", cfg, post=kaputt), (False, "antwort"))
        with open(os.path.join(HERE, "..", "speech-spark.sh"), encoding="utf-8") as f:
            sh = f.read()
        teil = sh[sh.index('if [ "$kind" = sprache ] || [ "$kind" = datei ]'):sh.index('elif [ "$kind" = wahl ]')]
        for step in ('datei-laden "$mid"', "probe=dateiprobe", 'dienst_neu "$art"', 'wechsel-schalten "$art" "$alt"'):
            self.assertIn(step, teil)


class Seite(unittest.TestCase):
    def test_check_and_add_a_file_with_its_basis(self):
        helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
        d = tempfile.mkdtemp()
        with mock.patch.object(modelle, "EIGENE", os.path.join(d, "e.json")), \
                mock.patch.object(modellseite, "_hf_info", mock.AsyncMock(return_value=info())), \
                mock.patch.object(modelle, "gesamt_gib", return_value=121.0):
            body = {"art": "bild", "repo": "beispiel/flux-fein", "datei": "flux-2-klein-4b-fein-Q6_K.gguf", "basis": "4b-q8"}
            r = ADMIN.post("/api/admin/modelle/eigen/pruefen", json=body)
            self.assertEqual(r.status_code, 200, r.text)
            v = r.json()["vorschlag"]
            self.assertEqual((v["datei"], v["basis"], v["revision"]), (body["datei"], "4b-q8", SHA))
            r = ADMIN.post("/api/admin/modelle/eigen/pruefen", json=dict(body, basis="xl"))
            self.assertEqual(r.status_code, 400)
            r = ADMIN.post("/api/admin/modelle/eigen", json=dict(body, revision=SHA))
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual([m["art"] for m in modelle.eigene(os.path.join(d, "e.json"))], ["bild"])
            basen = r.json()["wechsel"]["basen"]
            self.assertEqual([b[0] for b in basen["bild"]], list(modelle.DATEI_ART["bild"][1]))
            self.assertEqual([b[0] for b in basen["musik"]], list(modelle.DATEI_ART["musik"][1]))
        with open(os.path.join(HERE, "..", "panel", "static", "js", "modelle.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("mdDatei", js)
        self.assertIn("(w.basen||{})[a.art]", js)


if __name__ == "__main__":
    unittest.main()
