"""Zustand → Modelle „Lange Gespräche“ (Dominik 2026-10-17, modelle.PLATZ, modellseite.admin_platz, tarswart.platz,
speech-spark platz_setzen): the own language model's context store as fixed choices only (standard, 4 × 64K, 1 × 256K),
never longer than the model knows (kontext_max), never one that leaves the budget too tight, only behind the admin
switch Funktionen → Modelle wechseln (off by default) with the admin's fresh code; the panel leaves a checked wish
(art platz) for the fixed root unit speech-spark-wechsel, which checks it again and goes back when the model does not
answer. Nothing depends on the time of day."""
import copy
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
import common  # noqa: E402
import panel  # noqa: E402
import guard  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402
import steuer  # noqa: E402
import stufen  # noqa: E402
import tarswart  # noqa: E402
from tests import test_waerter  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000.0
QWEN = "qwen38-27b-nvfp4"
UNIT = ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", modelle.WECHSEL_UNIT]


def cfg(reserve=10, **llm):
    return {"chat": {"llm_url": "http://127.0.0.1:31006/v1"}, "memory": {"reserve_gib": reserve},
            "llm": dict({"enabled": True, "modell": QWEN, "sehen_modell": "gemma-4-26b-a4b"}, **llm),
            "image": {"enabled": False, "variant": "4b-q8"}}


def eigenes_llm(test, **llm):
    """The test configuration with the own language model (after the move), put back afterwards."""
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        alt = json.load(f)
    c = copy.deepcopy(alt)
    c["llm"] = dict(c.get("llm", {}), enabled=True, modell=QWEN, **llm)
    helpers.write_config(c)
    test.addCleanup(helpers.write_config, alt)


class Regeln(unittest.TestCase):
    def test_the_choices_are_fixed_and_never_longer_than_the_model_knows(self):
        m = modelle.eintrag(QWEN)
        self.assertEqual(set(modelle.PLATZ), set(modelle.PLATZ_NAMEN))
        self.assertIs(modelle.mit_platz(m, "standard"), m)
        self.assertIs(modelle.mit_platz(m, None), m)
        for p, kontext in (("4x64k", 65536), ("1x256k", 262144)):
            n = modelle.mit_platz(m, p)
            self.assertEqual(n["kontext"], kontext)
            self.assertGreater(n["anteil"], m["anteil"])
            self.assertLessEqual(n["anteil"], modelle.ANTEIL_MAX)
        for bad in ("8x64k", "1x256k; reboot", ""):
            with self.assertRaises(modelle.Fehler, msg=bad):
                modelle.mit_platz(m, bad)
        kurz = dict(m, kontext_max=m["kontext"])
        with self.assertRaises(modelle.Fehler) as e:
            modelle.mit_platz(kurz, "1x256k")
        self.assertEqual(str(e.exception), "kontext")
        sehen = next(x for x in modelle.katalog().values() if x["engine"] == "vllm" and x["art"] == "sehen")
        with self.assertRaises(modelle.Fehler):
            modelle.mit_platz(sehen, "4x64k")

    def test_the_catalog_says_how_long_a_model_may_go(self):
        for mid, m in modelle.katalog().items():
            if m["engine"] == "vllm":
                self.assertGreaterEqual(m.get("kontext_max", m["kontext"]), m["kontext"], mid)
                self.assertLessEqual(m.get("kontext_max", m["kontext"]), 262144, mid)
        self.assertEqual(modelle.eintrag(QWEN)["kontext_max"], 262144)
        roh = dict(modelle.eintrag(QWEN), kontext_max=100)
        with self.assertRaises(modelle.Fehler):
            modelle._pruefe_vllm(roh)

    def test_the_rules_before_anything_happens(self):
        for c, p, word in ((cfg(), "8x64k", "platz"), (cfg(enabled=False), "4x64k", "aus"),
                           (cfg(), "standard", "schon"), (cfg(platz="4x64k"), "4x64k", "schon")):
            with self.assertRaises(modelle.Fehler, msg=(c, p)) as e:
                modelle.platz_pruefen(p, c, 121.0)
            self.assertEqual(str(e.exception), word)
        with self.assertRaises(modelle.Fehler) as e:
            modelle.platz_pruefen("1x256k", cfg(reserve=72), 121.0)      # standard fits, 8.5 GiB more does not
        self.assertEqual(str(e.exception), "budget")
        self.assertEqual(modelle.platz_pruefen("1x256k", cfg(), 121.0)["kontext"], 262144)
        self.assertEqual(modelle.platz_pruefen("standard", cfg(platz="1x256k"), 121.0)["kontext"],
                         modelle.eintrag(QWEN)["kontext"])

    def test_the_budget_counts_the_bigger_store(self):
        def llm_gib(c):
            return next(x["gib"] for x in modelle.aktiv(c, 121.0) if x["id"] == QWEN)
        self.assertAlmostEqual(llm_gib(cfg(platz="4x64k")) - llm_gib(cfg()), 0.07 * 121.0, places=1)
        self.assertEqual(llm_gib(cfg(platz="gibts-nicht")), llm_gib(cfg()))   # an unknown choice counts as standard

    def test_the_engine_starts_with_it(self):
        def args(c):
            m, port = modelle.rolle("llm", c)
            a = modelle.vllm_args(m, port, modelle.fest_revision(m))
            return a[a.index("--max-model-len") + 1], a[a.index("--gpu-memory-utilization") + 1]
        std = args(cfg())
        self.assertEqual(std[0], str(modelle.eintrag(QWEN)["kontext"]))
        self.assertEqual(args(cfg(platz="4x64k"))[0], "65536")
        self.assertEqual(args(cfg(platz="1x256k"))[0], "262144")
        self.assertGreater(float(args(cfg(platz="1x256k"))[1]), float(std[1]))
        # the vision model stays as it is
        self.assertEqual(modelle.rolle("sehen", cfg(platz="1x256k"))[0], modelle.eintrag("gemma-4-26b-a4b"))

    def test_the_page_lists_the_choices_with_why_not(self):
        w = modelle.platz_wahl(cfg(), 121.0)
        self.assertEqual(w["jetzt"], "standard")
        self.assertEqual([x["id"] for x in w["wahl"]], list(modelle.PLATZ))
        nein = {x["id"]: x["nein"] for x in w["wahl"]}
        self.assertEqual(nein, {"standard": "schon", "4x64k": "", "1x256k": ""})
        self.assertEqual({x["id"]: x["nein"] for x in modelle.platz_wahl(cfg(reserve=72), 121.0)["wahl"]}["1x256k"],
                         "budget")

    def test_the_wish_is_checked_again_and_counts_once(self):
        p = os.path.join(tempfile.mkdtemp(), "wunsch.json")
        for bad in ("8x64k", "x; reboot", ""):
            with self.assertRaises(modelle.Fehler):
                modelle.wunsch_schreiben("platz", bad, path=p)
        self.assertFalse(os.path.exists(p))
        with self.assertRaises(modelle.Fehler):
            modelle.platz_anfragen("4x64k", cfg(), 121.0, (), lambda: True, laeuft=True)
        modelle.wunsch_schreiben("platz", "1x256k", path=p)
        with open(p) as f:
            zeit = json.load(f)["zeit"]
        self.assertEqual(modelle.wunsch_nehmen(p, now=zeit + 5), ("platz", "1x256k"))
        with self.assertRaises(modelle.Fehler):
            modelle.wunsch_nehmen(p, now=zeit + 5)
        for daten in ({"art": "platz", "was": "8x64k", "zeit": T0}, {"art": "platz", "was": "4x64k", "zeit": T0 - 3600}):
            with open(p, "w") as f:
                json.dump(daten, f)
            with self.assertRaises(modelle.Fehler, msg=daten):
                modelle.wunsch_nehmen(p, now=T0)

    def test_root_writes_only_a_known_choice(self):
        eigenes_llm(self)
        out = []
        self.assertEqual(modelle.cli(["platz-schalten", "x; reboot"], log=out.append), 2)
        self.assertEqual(modelle.cli(["platz-jetzt"], log=out.append), 0)
        self.assertEqual(out[-1], "standard")
        self.assertEqual(modelle.cli(["platz-schalten", "4x64k"], log=out.append), 0)
        self.assertIn("modelle: schalter platz 4x64k", out)
        self.assertEqual(modelle._roh()["llm"]["platz"], "4x64k")
        self.assertEqual(modelle.cli(["platz-pruefen", "4x64k"], log=out.append), 2)     # schon
        self.assertEqual(modelle.cli(["platz-jetzt"], log=out.append), 0)
        self.assertEqual(out[-1], "4x64k")

    def test_the_choice_comes_back_from_the_model_computer(self):
        defaults = common.load_config()
        self.assertEqual(common.model_choice_take({"llm": {}}, {"llm": {"platz": "1x256k"}}, defaults),
                         {"llm": {"platz": "1x256k"}})
        for bad in (1, "x y", "<b>"):
            with self.assertRaises(ValueError, msg=bad):
                common.model_choice_take({"llm": {}}, {"llm": {"platz": bad}}, defaults)


class Panel(unittest.TestCase):
    def setUp(self):
        for k in [k for k in guard._rate if k[0] in ("modelle_wechsel", "modelle")]:
            guard._rate.pop(k, None)
        self.saved = modellseite._lanes, modellseite._laeuft, modellseite._misst
        modellseite._lanes = lambda: []
        modellseite._laeuft = lambda: False
        modellseite._misst = lambda: False
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))

    def tearDown(self):
        modellseite._lanes, modellseite._laeuft, modellseite._misst = self.saved
        helpers.set_config(modelle_wechseln=False)
        modellseite._live["t"] = None

    def test_listed_with_its_level(self):
        self.assertIn(("POST", "/api/admin/modelle/platz"), stufen.LIST)

    def test_off_by_default_and_admin_only(self):
        eigenes_llm(self)
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ADMIN.post("/api/admin/modelle/platz", json={"platz": "4x64k"}).status_code, 409)
        self.assertIn("modelle: platz abgelehnt aus", out.getvalue())
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.post("/api/admin/modelle/platz", json={"platz": "4x64k"}).status_code, (401, 403))
        self.assertFalse(os.path.exists(modelle.WUNSCH))
        self.assertIsNone(ADMIN.get("/api/admin/modelle").json()["wechsel"]["platz"])

    def test_the_panel_leaves_a_checked_wish_and_starts_only_the_fixed_unit(self):
        eigenes_llm(self)
        helpers.set_config(modelle_wechseln=True)
        done = subprocess.CompletedProcess([], 0, b"", b"")
        out = io.StringIO()
        with mock.patch.object(modellseite.subprocess, "run", return_value=done) as run, \
                mock.patch.object(steuer, "remote", return_value=False), \
                mock.patch.object(modelle, "gesamt_gib", return_value=121.0), redirect_stdout(out):
            page = ADMIN.get("/api/admin/modelle").json()["wechsel"]["platz"]
            self.assertEqual(page["jetzt"], "standard")
            self.assertTrue(all(isinstance(x["name"], str) for x in page["wahl"]))
            for bad in ("8x64k", "standard"):
                self.assertEqual(ADMIN.post("/api/admin/modelle/platz", json={"platz": bad}).status_code, 400, bad)
            self.assertFalse(run.called)
            r = ADMIN.post("/api/admin/modelle/platz", json={"platz": "1x256k"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn(modelle.WECHSEL_UNIT, run.call_args[0][0])
        self.assertEqual(modelle.wunsch_nehmen(), ("platz", "1x256k"))
        self.assertIn("modelle: platz abgelehnt platz", out.getvalue())
        self.assertIn("modelle: platz angefragt", out.getvalue())
        self.assertIs(r.json()["wechsel"]["laeuft"], True)        # the page shows it at once, before the unit works

    def test_never_during_a_measurement_or_a_switch(self):
        eigenes_llm(self)
        helpers.set_config(modelle_wechseln=True)
        for misst, laeuft in ((True, False), (False, True)):
            modellseite._misst, modellseite._laeuft = (lambda: misst), (lambda: laeuft)
            with mock.patch.object(modellseite.subprocess, "run") as run, \
                    mock.patch.object(steuer, "remote", return_value=False), \
                    mock.patch.object(modelle, "gesamt_gib", return_value=121.0), redirect_stdout(io.StringIO()):
                self.assertEqual(ADMIN.post("/api/admin/modelle/platz", json={"platz": "4x64k"}).status_code, 409)
                self.assertFalse(run.called)
        self.assertFalse(os.path.exists(modelle.WUNSCH))

    def test_with_the_models_on_another_computer_the_waerter_decides(self):
        helpers.set_config(modelle_wechseln=True)
        for antwort, code in (({"ok": True}, 200), ({"ok": False, "fehler": "budget"}, 400),
                              ({"ok": False, "fehler": "<b>"}, 400), (None, 503)):
            guard._rate.clear()
            with mock.patch.object(steuer, "remote", return_value=True), \
                    mock.patch.object(steuer, "call", return_value=antwort) as call, \
                    mock.patch.object(modellseite, "seite", return_value={}), redirect_stdout(io.StringIO()):
                self.assertEqual(ADMIN.post("/api/admin/modelle/platz", json={"platz": "4x64k"}).status_code, code, antwort)
            self.assertEqual(call.call_args[0][:2], ("platz", ("4x64k",)))
        self.assertFalse(os.path.exists(modelle.WUNSCH))


class Waerter(test_waerter.Base):
    def test_there_the_same_rule_and_its_own_fixed_unit(self):
        eigenes_llm(self)
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(modelle, "gesamt_gib", return_value=121.0):
            for args in (["x; reboot"], [], ["a", "b"]):
                self.assertEqual(self.post(test_waerter.body("platz", args)).status_code, 400, args)
            self.assertEqual(self.post(test_waerter.body("platz", ["standard"])).json(), {"ok": False, "fehler": "schon"})
            self.assertFalse([c for c in self.run.calls if "sudo" in c])
            good = self.post(test_waerter.body("platz", ["4x64k"])).json()
        self.assertEqual(good, {"ok": True})
        self.assertIn(UNIT, self.run.calls)
        self.assertEqual(modelle.wunsch_nehmen(), ("platz", "4x64k"))
        self.assertIn("waerter: platz ok", out.getvalue())
        self.assertIn("waerter: platz abgelehnt schon", out.getvalue())


class Kommando(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(helpers.APP, "speech-spark.sh")) as f:
            cls.sh = f.read()

    def body(self, name):
        s = self.sh[self.sh.index(name + "() {"):]
        return s[:s.index("\n}\n")]

    def test_root_checks_again_and_goes_back_when_the_model_does_not_answer(self):
        b = self.body("platz_setzen")
        self.assertLess(b.index("modelle.py platz-pruefen"), b.index("modelle.py platz-schalten \"$neu\""))
        self.assertLess(b.index("modelle.py platz-jetzt"), b.index("modelle.py platz-schalten \"$neu\""))
        self.assertLess(b.index("systemctl stop speech-spark-llm"), b.index("systemctl start speech-spark-llm"))
        self.assertLess(b.index("modelle.py rundlauf"), b.index("platz-schalten \"$alt\""))
        for word in ("startet", "ok", "fehler, zurueck", "abgelehnt"):
            self.assertIn(f"modelle: platz {'$neu ' if word in ('startet', 'ok', 'fehler, zurueck') else ''}{word}", b)
        w = self.body("cmd_wunsch_intern")
        self.assertLess(w.index('=~ ^[a-z0-9][a-z0-9.-]{1,47}$'), w.index('platz_setzen "$was"'))
        self.assertLess(w.index('"$MESS_UNIT" "$MESS_WUNSCH_UNIT"'), w.index('platz_setzen "$was"'))


if __name__ == "__main__":
    unittest.main()
