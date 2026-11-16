"""„Nur laden“ and „Nur herunterladen“ (Dominik 2026-11-16 „es sollten geprüfte angezeigt werden sowie auch alles
mögliche gedownloaded werden“, „1-6“ with the token and „ja“ for approved models; alzeo idea 3; model catalog stage
B1c). The protection rules, each with its test:

- any public model, one that needs an approval only with the admin's token, never a private one;
- only the file kinds of ERLAUBT_LADEN (safetensors, GGUF, ONNX, text), never Python code or pickle, and at least
  one weight file; only when 20 GB stay free on the disk, checked again before the download;
- a downloaded model is only on the disk (nothing runs it), once per commit, at most 40;
- the download goes as the wish „laden <id>“ to the fixed root unit, never during a switch or a measurement;
- endpoints behind their switches, with login, admin code, limit and size; the model computer decides there.
Nothing depends on the time of day."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import hftoken  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402
import steuer  # noqa: E402
import stufen  # noqa: E402
from tests import test_waerter  # noqa: E402
from tests.test_lange_gespraeche import UNIT  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SHA = "e" * 40
GIB = 2**30


def info(**over):
    d = {"sha": SHA, "private": False, "gated": False, "disabled": False, "cardData": {"license": "apache-2.0"},
         "config": {"architectures": ["WhisperForConditionalGeneration"]},
         "siblings": [{"rfilename": "model.safetensors", "lfs": {"size": 3 * GIB}},
                      {"rfilename": "flux-q8.gguf", "lfs": {"size": 2 * GIB}},
                      {"rfilename": "config.json", "size": 900}, {"rfilename": "README.md", "size": 10},
                      {"rfilename": "pytorch_model.bin", "lfs": {"size": 50 * GIB}},
                      {"rfilename": "modeling_x.py", "size": 4000}]}
    d.update(over)
    return d


def liste():
    return os.path.join(tempfile.mkdtemp(dir=helpers.TMP), "geladen.json")


class Regeln(unittest.TestCase):
    def test_only_allowed_kinds_count_and_the_disk_must_keep_room(self):
        e = modelle.laden_vorschlag(info(), "beispiel/Whisper-X", 500.0)
        self.assertEqual(e["gib"], 5.0)                                  # pickle and code are never fetched
        self.assertTrue(modelle.ID.match(e["id"]))
        self.assertEqual((e["revision"], e["lizenz"], e["gewerblich"], e["code"]), (SHA, "apache-2.0", True, False))
        self.assertTrue(modelle.laden_vorschlag(info(config={"auto_map": {"x": "y"}}), "a/b", 500.0)["code"])
        for i, repo, frei, word in ((info(private=True), "a/b", 500.0, "zugang"), (info(gated="auto"), "a/b", 500.0, "zugang"),
                                    (info(siblings=[{"rfilename": "x.bin", "lfs": {"size": 1}}, {"rfilename": "c.json"}]), "a/b", 500.0, "format"),
                                    (info(), "a/b", 24.0, "platte"), (info(), "../x", 500.0, "repo"), (info(sha="main"), "a/b", 500.0, "antwort")):
            with self.assertRaises(modelle.Fehler, msg=word) as c:
                modelle.laden_vorschlag(i, repo, frei)
            self.assertEqual(str(c.exception), word)
        self.assertEqual(modelle.laden_vorschlag(info(gated="manual"), "a/b", 500.0, mit_token=True)["revision"], SHA)
        with self.assertRaises(modelle.Fehler):
            modelle.laden_vorschlag(info(private=True), "a/b", 500.0, mit_token=True)     # private: never

    def test_approved_models_also_as_own_models_only_with_the_token(self):
        with self.assertRaises(modelle.Fehler) as c:
            modelle._zugang({"gated": "auto"}, False)
        self.assertEqual(str(c.exception), "zugang")
        modelle._zugang({"gated": "auto"}, True)

    def test_kept_once_and_fetched_with_the_wider_kinds_only(self):
        p = liste()
        e = modelle.laden_vorschlag(info(), "beispiel/Whisper-X", 500.0)
        with mock.patch.object(modelle, "GELADEN", p):
            modelle.laden_merken(e, path=p)
            with self.assertRaises(modelle.Fehler):
                modelle.laden_merken(e, path=p)
            self.assertEqual(modelle.laden_ziel(e["id"], path=p)["repo"], "beispiel/Whisper-X")
            with self.assertRaises(modelle.Fehler):
                modelle.laden_ziel("hf-gibts-nicht", path=p)
            kat = modelle.katalog()
            qwen = kat["qwen36-35b-a3b-nvfp4"]
            with self.assertRaises(modelle.Fehler):                       # a commit of the catalog: already there
                modelle.laden_merken(dict(e, repo=qwen["repo"], revision=qwen["revision"]), path=p)
            with mock.patch.object(modelle, "_laden") as lade, mock.patch.object(modelle, "platte_frei_gib", return_value=500.0):
                modelle.laden_lauf(e["id"], log=lambda s: None)
            self.assertEqual(lade.call_args[0][3], modelle.ERLAUBT_LADEN)
            with mock.patch.object(modelle, "_laden") as lade, mock.patch.object(modelle, "platte_frei_gib", return_value=10.0):
                with self.assertRaises(modelle.Fehler):
                    modelle.laden_lauf(e["id"], log=lambda s: None)       # the disk filled meanwhile
            self.assertFalse(lade.called)
            with mock.patch.object(modelle, "vorbereiten") as vor:
                modelle.laden_lauf("qwen36-35b-a3b-nvfp4", log=lambda s: None)
            self.assertEqual(vor.call_args[0][0]["id"], "qwen36-35b-a3b-nvfp4")
        self.assertIn("*.gguf", modelle.ERLAUBT_LADEN)
        self.assertFalse([x for x in modelle.ERLAUBT_LADEN if modelle.VERBOTEN.search(x.replace("*", "x"))])

    def test_a_gguf_download_is_checked_like_the_others(self):
        from tests.test_bibliothek import snapshot
        hf = tempfile.mkdtemp(dir=helpers.TMP)
        import hashlib
        data = b"G" * 100
        h = hashlib.sha256(data).hexdigest()
        base = snapshot(hf, "a/b", SHA, {"m.gguf": (h, 0)})
        with open(os.path.join(base, "blobs", h), "wb") as f:
            f.write(data)
        with self.assertRaises(modelle.Fehler):
            modelle.pruefen(base, SHA)                                     # the catalog's rule: safetensors
        self.assertEqual(modelle.pruefen(base, SHA, gewichte=modelle.GEWICHTE_LADEN)[0], 1)
        os.symlink(os.path.join("..", "..", "blobs", h), os.path.join(base, "snapshots", SHA, "x.py"))
        with self.assertRaises(modelle.Fehler) as c:
            modelle.pruefen(base, SHA, gewichte=modelle.GEWICHTE_LADEN)
        self.assertEqual(str(c.exception), "dateiart")

    def test_the_wish_and_root(self):
        p = liste()
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))
        with mock.patch.object(modelle, "GELADEN", p):
            with self.assertRaises(modelle.Fehler) as c:
                modelle.herunterladen_anfragen("a/b", "", info(), lambda: True, laeuft=True, frei_gib=500.0)
            self.assertEqual(str(c.exception), "laeuft")
            with self.assertRaises(modelle.Fehler) as c:
                modelle.herunterladen_anfragen("a/b", "f" * 40, info(), lambda: True, frei_gib=500.0)
            self.assertEqual(str(c.exception), "antwort")
            e = modelle.herunterladen_anfragen("a/b", SHA, info(), lambda: True, frei_gib=500.0)
        self.assertEqual(modelle.wunsch_nehmen(), ("laden", e["id"]))
        sh = open(os.path.join(os.path.dirname(modelle.__file__), "speech-spark.sh")).read()
        self.assertIn('if [ "$art" = laden ]; then laden_setzen "$was"; return; fi', sh)
        self.assertIn('as_panel_user ../modelle.py laden "$1"', sh)


class Seite(unittest.TestCase):
    def setUp(self):
        guard._rate.clear()
        self.saved = modellseite._laeuft, modellseite._misst
        modellseite._laeuft = lambda: False
        modellseite._misst = lambda: False
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))

    def tearDown(self):
        modellseite._laeuft, modellseite._misst = self.saved
        helpers.set_config(modelle_wechseln=False, modelle_eigene=False)

    def test_listed_behind_the_switches_and_admin_only(self):
        for k in (("POST", "/api/admin/modelle/laden"), ("POST", "/api/admin/modelle/herunterladen")):
            self.assertIn(k, stufen.LIST)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(ADMIN.post("/api/admin/modelle/laden", json={"id": "qwen3-vl-8b-fp8"}).status_code, 409)
            self.assertEqual(ADMIN.post("/api/admin/modelle/herunterladen", json={"repo": "a/b"}).status_code, 409)
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.post("/api/admin/modelle/herunterladen", json={"repo": "a/b"}).status_code, (401, 403))
        self.assertIn(anon.post("/api/admin/modelle/laden", json={"id": "x"}).status_code, (401, 403))
        self.assertEqual(ADMIN.post("/api/admin/modelle/laden", content=b"{" + b" " * 4000 + b"}").status_code, 413)
        self.assertFalse(os.path.exists(modelle.WUNSCH))

    def test_on_another_computer_it_decides(self):
        helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
        for antwort, code in (({"ok": True, "id": "hf-b-eeeeeeee"}, 200), ({"ok": False, "fehler": "platte"}, 400),
                              ({"ok": False, "fehler": "<b>"}, 503), (None, 503)):
            guard._rate.clear()
            with mock.patch.object(steuer, "remote", return_value=True), \
                    mock.patch.object(steuer, "call", return_value=antwort) as call, \
                    mock.patch.object(modellseite, "seite", return_value={}), redirect_stdout(io.StringIO()):
                self.assertEqual(ADMIN.post("/api/admin/modelle/herunterladen", json={"repo": "a/b", "revision": SHA}).status_code, code, antwort)
            self.assertEqual(call.call_args[0][:2], ("herunterladen", ("a/b", SHA)))
        with mock.patch.object(steuer, "remote", return_value=True), \
                mock.patch.object(steuer, "call") as call, redirect_stdout(io.StringIO()):
            self.assertEqual(ADMIN.post("/api/admin/modelle/herunterladen", json={"repo": "../x"}).status_code, 400)
            self.assertEqual(ADMIN.post("/api/admin/modelle/laden", json={"id": "<b>"}).status_code, 404)
        self.assertFalse(call.called)

    def test_here_the_same_rules_and_the_fixed_unit(self):
        import subprocess
        helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
        p = liste()
        done = subprocess.CompletedProcess([], 0, b"", b"")
        with mock.patch.object(steuer, "remote", return_value=False), mock.patch.object(modelle, "GELADEN", p), \
                mock.patch.object(hftoken, "metadaten", return_value=info()), \
                mock.patch.object(modelle, "platte_frei_gib", return_value=500.0), \
                mock.patch.object(modellseite.subprocess, "run", return_value=done) as run, \
                mock.patch.object(modellseite, "seite", return_value={}), redirect_stdout(io.StringIO()) as out:
            r = ADMIN.post("/api/admin/modelle/herunterladen", json={"repo": "beispiel/Whisper-X"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn(modelle.WECHSEL_UNIT, run.call_args[0][0])
            self.assertEqual(ADMIN.post("/api/admin/modelle/herunterladen", json={"repo": "beispiel/Whisper-X"}).status_code, 409)
        self.assertEqual(modelle.wunsch_nehmen()[0], "laden")
        self.assertIn("modelle: herunterladen angefragt", out.getvalue())
        self.assertIn("modelle: herunterladen abgelehnt schon", out.getvalue())


class Waerter(test_waerter.Base):
    def test_there_with_its_token_and_its_unit(self):
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))
        p = liste()
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(modelle, "GELADEN", p), \
                mock.patch.object(hftoken, "metadaten", return_value=info()), \
                mock.patch.object(modelle, "platte_frei_gib", return_value=500.0):
            self.assertEqual(self.post(test_waerter.body("laden", ["<b>"])).status_code, 400)
            self.assertEqual(self.post(test_waerter.body("laden", ["gibts-nicht"])).json(), {"ok": False, "fehler": "unbekannt"})
            d = self.post(test_waerter.body("herunterladen", ["beispiel/Whisper-X"])).json()
        self.assertIs(d["ok"], True)
        self.assertIn(UNIT, self.run.calls)
        self.assertEqual(modelle.wunsch_nehmen(), ("laden", d["id"]))
        self.assertIn("waerter: herunterladen ok", out.getvalue())
        self.assertIn("waerter: laden abgelehnt unbekannt", out.getvalue())


if __name__ == "__main__":
    unittest.main()
