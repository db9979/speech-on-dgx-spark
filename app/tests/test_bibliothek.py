"""Modell-Bibliothek and the Hugging Face token (Dominik 2026-11-16 „1-5“ alzeo idea 2, „auch die hugginface api
eingabe … nicht vergessen“, „ja“ for models that need an approval; model catalog stage B1c). The protection rules,
each with its test:

- the token has the shape of a Hugging Face token, lives only on the computer the models run on (0600), never in an
  answer, a log or the page, goes only to huggingface.co; a token Hugging Face refuses is not used again;
- with the models on another computer the metadata is asked there (Wärter hf_info), the token never travels back;
- the library lists every commit in the cache with who needs it; only a loose one (no entry names it) can go, never
  a link, never outside the cache; blobs another commit still uses stay;
- the panel takes from the model computer only the library's shape;
- the endpoints: login, admin code (a fresh one for the token), limit and size.
Nothing depends on the time of day."""
import io
import json
import os
import stat
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

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TOK = "hf_" + "A1b2C3d4" * 5
REV1, REV2 = "1" * 40, "2" * 40
QWEN = "qwen36-35b-a3b-nvfp4"


def ordner():
    return tempfile.mkdtemp(dir=helpers.TMP)


def snapshot(hf, repo, rev, dateien):
    """A cache folder like huggingface_hub writes it: blobs/<hash> and snapshots/<rev>/<name> -> ../../blobs/<hash>."""
    base = os.path.join(hf, "hub", "models--" + repo.replace("/", "--"))
    os.makedirs(os.path.join(base, "blobs"), exist_ok=True)
    snap = os.path.join(base, "snapshots", rev)
    os.makedirs(snap, exist_ok=True)
    for name, (blob, size) in dateien.items():
        p = os.path.join(base, "blobs", blob)
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(b"x" * size)
        os.symlink(os.path.join("..", "..", "blobs", blob), os.path.join(snap, name))
    return base


class Token(unittest.TestCase):
    def test_kept_only_in_its_shape_and_never_shown(self):
        p = os.path.join(ordner(), "hf-token.json")
        self.assertEqual((hftoken.token(p), hftoken.info(p)["gesetzt"]), ("", False))
        for bad in ("", "ghp_" + "a" * 36, "hf_kurz", TOK + " x", "hf_" + "ä" * 40):
            with self.assertRaises(ValueError):
                hftoken.speichern(bad, path=p)
        hftoken.speichern(TOK, now=1_800_000_000, path=p)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
        self.assertEqual(hftoken.token(p), TOK)
        self.assertEqual(hftoken.info(p), {"gesetzt": True, "seit": 1_800_000_000, "abgelehnt": False})
        self.assertNotIn(TOK, json.dumps(hftoken.info(p)))
        self.assertEqual(hftoken.kopf("https://huggingface.co/api/models/a/b", p), {"Authorization": "Bearer " + TOK})
        for anders in ("https://huggingface.co.evil/x", "http://huggingface.co/x", "https://example.org/huggingface.co/"):
            self.assertEqual(hftoken.kopf(anders, p), {}, anders)
        with redirect_stdout(io.StringIO()) as out:
            hftoken.abgelehnt(p)
        self.assertNotIn(TOK, out.getvalue())
        self.assertEqual((hftoken.token(p), hftoken.info(p)["abgelehnt"]), ("", True))   # refused: not used again
        self.assertTrue(hftoken.weg(p))
        self.assertFalse(hftoken.weg(p))

    def test_the_download_takes_it_and_never_a_token_file_of_the_library(self):
        import huggingface_hub
        hf = ordner()
        with mock.patch.object(hftoken, "token", return_value=""), \
                mock.patch.object(huggingface_hub, "snapshot_download", side_effect=OSError("x")) as dl:
            with self.assertRaises(OSError):
                modelle._laden("a/b", "", os.path.join(hf, "hub", "models--a--b"))
        self.assertIs(dl.call_args.kwargs["token"], False)
        with mock.patch.object(hftoken, "token", return_value=TOK), \
                mock.patch.object(huggingface_hub, "snapshot_download", side_effect=OSError("x")) as dl:
            with self.assertRaises(OSError):
                modelle._laden("a/b", "", os.path.join(hf, "hub", "models--a--b"))
        self.assertEqual(dl.call_args.kwargs["token"], TOK)

    def test_metadata_only_from_the_fixed_address(self):
        for repo, rev in (("../x", ""), ("a/b", "main"), ("a/b; x", ""), ("a/b", "1" * 39)):
            with self.assertRaises(ValueError):
                hftoken.metadaten(repo, rev)
        self.assertEqual(hftoken.API.format(repo="a/b", rev="main")[:23], "https://huggingface.co/")
        self.assertEqual(modelle.HF_API, hftoken.API)


class Bibliothek(unittest.TestCase):
    def setUp(self):
        self.hf = ordner()
        self.kat = modelle.katalog()
        self.repo = self.kat[QWEN]["repo"]
        self.fest = self.kat[QWEN]["revision"]
        self.base = snapshot(self.hf, self.repo, self.fest, {"model.safetensors": ("a" * 64, 3000), "config.json": ("c" * 40, 10)})
        snapshot(self.hf, self.repo, REV1, {"model.safetensors": ("b" * 64, 2000), "config.json": ("c" * 40, 10)})
        snapshot(self.hf, "fremd/Alt", REV2, {"model.safetensors": ("d" * 64, 500)})
        self.cfg = {"llm": {"enabled": True, "modell": QWEN}}

    def test_every_commit_with_who_needs_it(self):
        b = modelle.bibliothek(self.cfg, self.kat, self.hf)
        rows = {(x["repo"], x["revision"]): x for x in b}
        self.assertEqual(set(rows), {(self.repo, self.fest), (self.repo, REV1), ("fremd/Alt", REV2)})
        fest = rows[(self.repo, self.fest)]
        self.assertIn(QWEN, fest["ids"])
        self.assertTrue(fest["laeuft"])
        self.assertFalse(fest["lose"])
        self.assertTrue(rows[(self.repo, REV1)]["lose"])
        self.assertTrue(rows[("fremd/Alt", REV2)]["lose"])
        os.symlink(self.hf, os.path.join(self.hf, "hub", "models--link--Weg"))     # a link is never listed
        self.assertEqual(len(modelle.bibliothek(self.cfg, self.kat, self.hf)), 3)

    def test_only_a_loose_commit_goes_and_shared_blobs_stay(self):
        with self.assertRaises(modelle.Fehler) as e:
            modelle.lose_weg(self.repo, self.fest, self.cfg, self.kat, self.hf)
        self.assertEqual(str(e.exception), "gebraucht")
        for repo, rev in (("../x", REV1), (self.repo, "main"), ("a/b", REV1)):
            with self.assertRaises(modelle.Fehler):
                modelle.lose_weg(repo, rev, self.cfg, self.kat, self.hf)
        frei = modelle.lose_weg(self.repo, REV1, self.cfg, self.kat, self.hf)
        self.assertEqual(frei, 2000)                                         # config.json's blob is shared: stays
        self.assertFalse(os.path.exists(os.path.join(self.base, "snapshots", REV1)))
        self.assertTrue(os.path.exists(os.path.join(self.base, "blobs", "c" * 40)))
        self.assertFalse(os.path.exists(os.path.join(self.base, "blobs", "b" * 64)))
        self.assertEqual(modelle.pruefen(self.base, self.fest, hashes=False)[0], 2)   # the pinned one is whole
        # the last commit of a model: its whole folder
        self.assertEqual(modelle.lose_weg("fremd/Alt", REV2, self.cfg, self.kat, self.hf), 500)
        self.assertFalse(os.path.exists(os.path.join(self.hf, "hub", "models--fremd--Alt")))

    def test_the_panel_takes_only_the_shape(self):
        gut = {"repo": "a/b", "revision": REV1, "gib": 1.5, "ids": [], "laeuft": False, "lose": True}
        self.assertEqual(modellseite._bibliothek_pruefen([gut]), [gut])
        for bad in (dict(gut, repo="../x"), dict(gut, revision="main"), dict(gut, ids=["<b>"]), dict(gut, lose=False),
                    dict(gut, pfad="/etc"), dict(gut, gib="1")):
            self.assertEqual(modellseite._bibliothek_pruefen([bad]), [], bad)
        self.assertEqual(modellseite._bibliothek_pruefen("x"), [])


class Seite(unittest.TestCase):
    def setUp(self):
        guard._rate.clear()

    def test_listed_and_admin_only(self):
        for k in (("PUT", "/api/admin/modelle/hftoken"), ("DELETE", "/api/admin/modelle/hftoken"),
                  ("DELETE", "/api/admin/modelle/bibliothek")):
            self.assertIn(k, stufen.LIST)
        self.assertEqual(stufen.LIST[("PUT", "/api/admin/modelle/hftoken")][0], stufen.PROTECT)
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.put("/api/admin/modelle/hftoken", json={"token": TOK}).status_code, (401, 403))
        self.assertIn(anon.request("DELETE", "/api/admin/modelle/bibliothek", json={"repo": "a/b", "revision": REV1}).status_code, (401, 403))
        self.assertEqual(ADMIN.put("/api/admin/modelle/hftoken", content=b"{" + b" " * 2000 + b"}").status_code, 413)

    def test_the_token_on_this_computer_and_never_in_the_page(self):
        self.addCleanup(hftoken.weg)
        with mock.patch.object(steuer, "remote", return_value=False), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ADMIN.put("/api/admin/modelle/hftoken", json={"token": "nein"}).status_code, 400)
            r = ADMIN.put("/api/admin/modelle/hftoken", json={"token": TOK})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIs(r.json()["gesetzt"], True)
            page = ADMIN.get("/api/admin/modelle")
            self.assertEqual(page.status_code, 200, page.text)
            self.assertIs(page.json()["hf_token"]["gesetzt"], True)
            self.assertNotIn(TOK, page.text)
            self.assertEqual(ADMIN.delete("/api/admin/modelle/hftoken").json()["gesetzt"], False)
        self.assertNotIn(TOK, out.getvalue())
        self.assertIn("modelle: hf-token gesetzt", out.getvalue())
        self.assertIn("modelle: hf-token abgelehnt form", out.getvalue())

    def test_on_another_computer_the_token_goes_there_once(self):
        with mock.patch.object(steuer, "remote", return_value=True), \
                mock.patch.object(steuer, "call", return_value={"ok": True}) as call, \
                mock.patch.object(steuer, "modelle", return_value={"hf_token": {"gesetzt": True, "seit": 5, "abgelehnt": False, "token": TOK}}), \
                redirect_stdout(io.StringIO()):
            r = ADMIN.put("/api/admin/modelle/hftoken", json={"token": TOK})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(call.call_args[0][0], "hf_token")
        self.assertEqual(call.call_args[0][4], {"token": TOK})
        self.assertEqual(r.json(), {"gesetzt": True, "seit": 5, "abgelehnt": False})      # nothing else comes back
        self.assertFalse(os.path.exists(hftoken.DATEI))

    def test_metadata_there_when_the_models_run_there(self):
        import asyncio
        with mock.patch.object(steuer, "remote", return_value=True), \
                mock.patch.object(steuer, "call", return_value={"ok": True, "info": {"sha": REV1}}) as call:
            self.assertEqual(asyncio.run(modellseite._hf_info("a/b", REV1)), {"sha": REV1})
        self.assertEqual(call.call_args[0][:2], ("hf_info", ("a/b", REV1)))
        for antwort, word in (({"ok": False, "fehler": "zugang"}, "zugang"), ({"ok": False, "fehler": "<b>"}, "antwort"),
                              (None, "rechner")):
            with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "call", return_value=antwort):
                with self.assertRaises(modelle.Fehler) as e:
                    asyncio.run(modellseite._hf_info("a/b"))
            self.assertEqual(str(e.exception), word)

    def test_only_a_loose_commit_is_deleted_through_the_page(self):
        with mock.patch.object(steuer, "remote", return_value=True), \
                mock.patch.object(steuer, "call", return_value={"ok": False, "fehler": "gebraucht"}), \
                redirect_stdout(io.StringIO()) as out:
            r = ADMIN.request("DELETE", "/api/admin/modelle/bibliothek", json={"repo": "a/b", "revision": REV1})
        self.assertEqual(r.status_code, 409)
        self.assertIn("modelle: bibliothek abgelehnt gebraucht", out.getvalue())
        with mock.patch.object(steuer, "remote", return_value=True), \
                mock.patch.object(steuer, "call", return_value={"ok": True, "gib": 1.0}) as call, \
                mock.patch.object(modellseite, "seite", return_value={}), redirect_stdout(io.StringIO()):
            self.assertEqual(ADMIN.request("DELETE", "/api/admin/modelle/bibliothek",
                                           json={"repo": "a/b", "revision": "main"}).status_code, 400)
            self.assertFalse(call.called)
            self.assertEqual(ADMIN.request("DELETE", "/api/admin/modelle/bibliothek",
                                           json={"repo": "a/b", "revision": REV1}).status_code, 200)
        self.assertEqual(call.call_args[0][:2], ("lose_weg", ("a/b", REV1)))


class Waerter(test_waerter.Base):
    def test_token_info_and_library_there(self):
        self.addCleanup(hftoken.weg)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.post(test_waerter.body("hf_token", daten={"token": "x"})).json(), {"ok": False, "fehler": "token"})
            self.assertEqual(self.post(test_waerter.body("hf_token", daten={"token": TOK})).json(), {"ok": True})
            d = self.post(test_waerter.body("modelle")).json()
            self.assertEqual(self.post(test_waerter.body("hf_info", ["../x"])).json(), {"ok": False, "fehler": "repo"})
            self.assertEqual(self.post(test_waerter.body("lose_weg", ["a/b"])).status_code, 400)
            self.assertEqual(self.post(test_waerter.body("lose_weg", ["a/b", REV1])).json()["ok"], False)
            self.assertEqual(self.post(test_waerter.body("hf_token_weg")).json(), {"ok": True})
        self.assertIs(d["hf_token"]["gesetzt"], True)
        self.assertNotIn(TOK, json.dumps(d))
        self.assertIsInstance(d["bibliothek"], list)
        self.assertNotIn(TOK, out.getvalue())
        self.assertIn("waerter: hf_token gesetzt", out.getvalue())
        self.assertIn("waerter: lose_weg abgelehnt", out.getvalue())


if __name__ == "__main__":
    unittest.main()
