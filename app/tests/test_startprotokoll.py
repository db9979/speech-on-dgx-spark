"""Rezept-Abgleich and Startprotokoll (Dominik 2026-11-16 „1-5“ on the alzeo ideas, model catalog stages B1b/B1d).
The protection rules, each with its test:

- the protocol keeps per kind only the last five starts, ids and numbers only, never a line of the engine;
- load time and context room come from the engine's journal by fixed patterns, from this start only, written once;
- the panel takes from the model computer only the protocol's shape, anything else counts as none;
- „Neu starten“ only when the language model runs with other settings than its entry gives now, never during a
  switch or a measurement; root checks that again and starts only the fixed unit;
- the endpoint is behind the admin switch, with login, admin code, limit and size.
Nothing depends on the time of day."""
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import llmstart  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402
import steuer  # noqa: E402
import stufen  # noqa: E402
from tests import test_waerter  # noqa: E402
from tests.test_lange_gespraeche import QWEN, UNIT, cfg, eigenes_llm  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000
SIG = "0123456789abcdef"


def datei(test):
    d = tempfile.mkdtemp(dir=helpers.TMP)
    return os.path.join(d, "llm-starts.json")


class Protokoll(unittest.TestCase):
    def test_the_last_five_per_kind_newest_first(self):
        p = datei(self)
        for n in range(7):
            llmstart.merken("llm", QWEN, SIG, 36, 32768 + n, "gb10", now=T0 + n, path=p)
        llmstart.merken("sehen", "qwen3-vl-8b-fp8", SIG, 24, 8192, "gb10", now=T0, path=p)
        b = llmstart.buch(p)
        self.assertEqual([e["kontext"] for e in b["llm"]], [32774, 32773, 32772, 32771, 32770])
        self.assertNotIn("sig", b["llm"][0])                    # the signature stays on the model computer
        self.assertEqual(len(b["sehen"]), 1)
        self.assertEqual(llmstart.letzter("llm", p)["sig"], SIG)
        for art, mid, sig in (("asr", QWEN, SIG), ("llm", "../x", SIG), ("llm", QWEN, "x; reboot")):
            with self.assertRaises(ValueError):
                llmstart.merken(art, mid, sig, 36, 4096, "gb10", now=T0, path=p)

    def test_load_time_and_room_from_this_start_only(self):
        p = datei(self)
        llmstart.merken("llm", QWEN, SIG, 36, 32768, "gb10", now=T0, path=p)
        alt = f"{T0 - 900}.5 tars vllm[1]: GPU KV cache size: 99 tokens\n{T0 - 800}.1 tars vllm[1]: Application startup complete.\n"
        self.assertFalse(llmstart.nachtragen("llm", alt, p))          # an earlier start: nothing
        laden = alt + f"{T0 + 300}.2 tars vllm[2]: GPU KV cache size: 1,234,567 tokens\n"
        self.assertFalse(llmstart.nachtragen("llm", laden, p))        # not ready yet: nothing written
        self.assertNotIn("kv_tokens", llmstart.letzter("llm", p))
        fertig = laden + f"{T0 + 412}.9 tars vllm[2]: INFO: Application startup complete.\n"
        self.assertTrue(llmstart.nachtragen("llm", lambda: fertig, p))
        e = llmstart.buch(p)["llm"][0]
        self.assertEqual((e["bereit_s"], e["kv_tokens"]), (412, 1234567))
        self.assertFalse(llmstart.nachtragen("llm", fertig, p))       # once

    def test_the_panel_takes_only_the_shape(self):
        gut = {"zeit": T0, "id": QWEN, "gpu_gib": 36.0, "kontext": 32768, "profil": "gb10", "bereit_s": 412}
        self.assertEqual(llmstart.buch_pruefen({"llm": [gut]}), {"llm": [gut]})
        for schlecht in ({"llm": [dict(gut, id="<b>")]}, {"llm": [dict(gut, text="x")]}, {"llm": [dict(gut, sig=SIG)]},
                         {"llm": [dict(gut, bereit_s="1")]}, {"llm": [dict(gut, profil="x y")]}, {"llm": "x"}, [gut], None):
            self.assertEqual(llmstart.buch_pruefen(schlecht), {}, schlecht)
        self.assertEqual(llmstart.buch_pruefen({"asr": [gut]}), {})


class Abgleich(unittest.TestCase):
    def test_other_settings_than_the_entry_gives_now(self):
        p = datei(self)
        c = cfg()
        self.assertFalse(modelle.abweichung("llm", c, path=p))          # never started here: nothing to say
        llmstart.merken("llm", QWEN, modelle.signatur("llm", c), 36, 32768, "gb10", now=T0, path=p)
        self.assertFalse(modelle.abweichung("llm", c, path=p))
        self.assertTrue(modelle.abweichung("llm", cfg(platz="4x64k"), path=p))
        kat = modelle.katalog()
        kat[QWEN] = dict(kat[QWEN], gpu_gib=kat[QWEN]["gpu_gib"] + 2)    # an update changed the entry
        self.assertTrue(modelle.abweichung("llm", c, kat=kat, path=p))
        self.assertFalse(modelle.abweichung("llm", cfg(enabled=True, modell="gibts-nicht"), path=p))

    def test_the_restart_is_asked_only_when_it_differs(self):
        p = datei(self)
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))
        llmstart.merken("llm", QWEN, modelle.signatur("llm", cfg()), 36, 32768, "gb10", now=T0, path=p)
        for c, laeuft, word in ((cfg(platz="4x64k"), True, "laeuft"), (cfg(), False, "schon")):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.neustart_anfragen(c, lambda: True, laeuft, path=p)
            self.assertEqual(str(e.exception), word)
        self.assertFalse(os.path.exists(modelle.WUNSCH))
        with self.assertRaises(modelle.Fehler) as e:
            modelle.neustart_anfragen(cfg(platz="4x64k"), lambda: False, path=p)
        self.assertEqual(str(e.exception), "start")
        modelle.neustart_anfragen(cfg(platz="4x64k"), lambda: True, path=p)
        self.assertEqual(modelle.wunsch_nehmen(), ("neustart", "llm"))
        for was in ("sehen", "x; reboot"):
            with self.assertRaises(modelle.Fehler):
                modelle.wunsch_schreiben("neustart", was)

    def test_root_checks_again_and_only_the_fixed_unit_restarts(self):
        sh = open(os.path.join(os.path.dirname(modelle.__file__), "speech-spark.sh")).read()
        teil = sh[sh.index("neustart_setzen() {"):sh.index("cmd_wunsch_intern() {")]
        self.assertIn("modelle.py neustart-pruefen", teil)
        self.assertIn("systemctl start speech-spark-llm.service", teil)
        self.assertIn('if [ "$art" = neustart ]; then neustart_setzen; return; fi', sh)
        out = []
        with mock.patch.object(modelle, "abweichung", return_value=False), mock.patch.object(modelle, "load_config", return_value={}):
            self.assertNotEqual(modelle.cli(["neustart-pruefen"], log=out.append), 0)
        with mock.patch.object(modelle, "abweichung", return_value=True), mock.patch.object(modelle, "load_config", return_value={}):
            self.assertEqual(modelle.cli(["neustart-pruefen"], log=out.append), 0)

    def test_engine_sh_start_writes_the_protocol_and_never_stops_on_it(self):
        with mock.patch.object(modelle, "start_args", return_value=["m", "--port", "1"]), \
                mock.patch.object(modelle, "load_config", return_value=cfg()), \
                mock.patch.object(llmstart, "merken") as merken:
            out = []
            self.assertEqual(modelle.cli(["start-args", "llm"], log=out.append), 0)
        self.assertEqual(out, ["m", "--port", "1"])                       # stdout: only the arguments
        self.assertEqual(merken.call_args[0][:3], ("llm", QWEN, modelle.signatur("llm", cfg())))
        with mock.patch.object(modelle, "start_args", return_value=["m"]), \
                mock.patch.object(modelle, "load_config", return_value=cfg()), \
                mock.patch.object(llmstart, "merken", side_effect=OSError), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(modelle.cli(["start-args", "llm"], log=[].append), 0)


class Seite(unittest.TestCase):
    def setUp(self):
        for k in [k for k in guard._rate if k[0] in ("modelle_wechsel", "modelle")]:
            guard._rate.pop(k, None)
        self.saved = modellseite._laeuft, modellseite._misst
        modellseite._laeuft = lambda: False
        modellseite._misst = lambda: False
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))

    def tearDown(self):
        modellseite._laeuft, modellseite._misst = self.saved
        helpers.set_config(modelle_wechseln=False)
        modellseite._live["t"] = None

    def test_listed_behind_the_switch_and_admin_only(self):
        self.assertIn(("POST", "/api/admin/modelle/neustart"), stufen.LIST)
        eigenes_llm(self)
        helpers.set_config(modelle_wechseln=False)   # the state this test is about, whatever ran before it
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ADMIN.post("/api/admin/modelle/neustart", json={}).status_code, 409)
        self.assertIn("modelle: neustart abgelehnt aus", out.getvalue())
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.post("/api/admin/modelle/neustart", json={}).status_code, (401, 403))
        self.assertEqual(ADMIN.post("/api/admin/modelle/neustart", content=b"{" + b" " * 9000 + b"}").status_code, 413)
        self.assertFalse(os.path.exists(modelle.WUNSCH))

    def test_the_page_shows_it_and_restarts_only_when_it_differs(self):
        eigenes_llm(self)
        helpers.set_config(modelle_wechseln=True)
        done = subprocess.CompletedProcess([], 0, b"", b"")
        out = io.StringIO()
        with mock.patch.object(modellseite.subprocess, "run", return_value=done) as run, \
                mock.patch.object(steuer, "remote", return_value=False), \
                mock.patch.object(modelle, "gesamt_gib", return_value=121.0), redirect_stdout(out):
            with mock.patch.object(modelle, "abweichung", return_value=False):
                self.assertIs(ADMIN.get("/api/admin/modelle").json()["wechsel"]["abweichung"], False)
                r = ADMIN.post("/api/admin/modelle/neustart", json={})
                self.assertEqual((r.status_code, r.json()["detail"]), (409, "Das Sprachmodell läuft schon so, wie es im Katalog steht."))
                self.assertFalse(run.called)
            with mock.patch.object(modelle, "abweichung", return_value=True):
                self.assertIs(ADMIN.get("/api/admin/modelle").json()["wechsel"]["abweichung"], True)
                r = ADMIN.post("/api/admin/modelle/neustart", json={})
                self.assertEqual(r.status_code, 200, r.text)
            self.assertIn(modelle.WECHSEL_UNIT, run.call_args[0][0])
        self.assertEqual(modelle.wunsch_nehmen(), ("neustart", "llm"))
        self.assertIn("modelle: neustart abgelehnt schon", out.getvalue())
        self.assertIn("modelle: neustart angefragt", out.getvalue())

    def test_with_the_models_on_another_computer_the_waerter_decides(self):
        helpers.set_config(modelle_wechseln=True)
        for antwort, code in (({"ok": True}, 200), ({"ok": False, "fehler": "schon"}, 409),
                              ({"ok": False, "fehler": "<b>"}, 400), (None, 503)):
            guard._rate.clear()
            with mock.patch.object(steuer, "remote", return_value=True), \
                    mock.patch.object(steuer, "call", return_value=antwort) as call, \
                    mock.patch.object(modellseite, "seite", return_value={}), redirect_stdout(io.StringIO()):
                self.assertEqual(ADMIN.post("/api/admin/modelle/neustart", json={}).status_code, code, antwort)
            self.assertEqual(call.call_args[0][:2], ("neustart", ()))

    def test_the_protocol_on_the_page_with_names(self):
        buch = {"starts": {"llm": [{"zeit": T0, "id": QWEN, "gpu_gib": 36.0, "kontext": 32768, "profil": "gb300",
                                    "bereit_s": 412, "kv_tokens": 1234567}]}, "abweichung": False}
        z = modellseite._starts_zeigen(buch, modelle.katalog(), 0)
        self.assertEqual((z[0]["art"], z[0]["name"]), ("llm", "Sprachmodell"))
        self.assertEqual((z[0]["starts"][0]["name"], z[0]["starts"][0]["geraet"]),
                         (modelle.eintrag(QWEN)["name"]["de"], "DGX Station (GB300)"))
        with mock.patch.object(steuer, "remote", return_value=True), \
                mock.patch.object(steuer, "modelle", return_value={"gesamt_gib": 120.0, "messung": {}, "laeuft": False,
                                                                  "eigene": [], "wechsel": {}, "starts": {"llm": "<b>"},
                                                                  "abweichung": "ja"}):
            q = modellseite._quelle({})
        self.assertEqual((q[9]["starts"], q[9]["abweichung"]), ({}, False))


class Waerter(test_waerter.Base):
    def test_there_the_same_rule_and_its_own_fixed_unit(self):
        eigenes_llm(self)
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.post(test_waerter.body("neustart", ["x"])).status_code, 400)
            with mock.patch.object(modelle, "abweichung", return_value=False):
                self.assertEqual(self.post(test_waerter.body("neustart")).json(), {"ok": False, "fehler": "schon"})
            self.assertFalse([c for c in self.run.calls if "sudo" in c])
            with mock.patch.object(modelle, "abweichung", return_value=True):
                self.assertEqual(self.post(test_waerter.body("neustart")).json(), {"ok": True})
            d = self.post(test_waerter.body("modelle")).json()
        self.assertIn(UNIT, self.run.calls)
        self.assertEqual(modelle.wunsch_nehmen(), ("neustart", "llm"))
        self.assertIn("waerter: neustart ok", out.getvalue())
        self.assertIn("waerter: neustart abgelehnt schon", out.getvalue())
        self.assertIsInstance(d["starts"], dict)
        self.assertIsInstance(d["abweichung"], bool)


if __name__ == "__main__":
    unittest.main()
