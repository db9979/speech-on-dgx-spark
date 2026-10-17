"""Zustand → Modelle „Messen“ (Dominik 2026-10-17, modelle.messen_*, modellseite.admin_messen, tarswart.messen,
speech-spark modelle messen-wunsch-intern): only a model this installation starts itself, only behind the admin switch
Funktionen → Modelle wechseln (off by default) with the admin's fresh code; the panel leaves a checked wish and starts
only the fixed root unit speech-spark-messen-wunsch, which checks the ids again; a measurement and a switch never run
at once; Live shows only that a measurement runs. Nothing depends on the time of day."""
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
import tarswart  # noqa: E402
from tests import test_waerter  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000.0
UNIT = ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "speech-spark-messen-wunsch"]


class Regeln(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(tempfile.mkdtemp(), "wunsch.json")

    def test_only_an_own_engine_and_the_wish_counts_once(self):
        kat = modelle.katalog()
        extern = next(i for i, m in kat.items() if m["engine"] != "vllm")
        for bad, word in (("gibts-nicht", "unbekannt"), ("x; reboot", "unbekannt"), (extern, "engine"), (None, "unbekannt")):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.messen_anfragen(bad, lambda: True, path=self.p)
            self.assertEqual(str(e.exception), word)
            self.assertFalse(os.path.exists(self.p))
        with self.assertRaises(modelle.Fehler) as e:
            modelle.messen_anfragen("gemma-4-26b-a4b", lambda: True, laeuft=True, path=self.p)
        self.assertEqual(str(e.exception), "misst")
        with self.assertRaises(modelle.Fehler) as e:
            modelle.messen_anfragen("gemma-4-26b-a4b", lambda: False, path=self.p)
        self.assertEqual(str(e.exception), "start")
        self.assertEqual(modelle.messen_anfragen("kolibri-1-nvfp4", lambda: True, path=self.p)["id"], "kolibri-1-nvfp4")
        with open(self.p) as f:
            zeit = json.load(f)["zeit"]
        self.assertEqual(modelle.messen_wunsch_nehmen(self.p, now=zeit + 5), ["kolibri-1-nvfp4"])
        with self.assertRaises(modelle.Fehler):
            modelle.messen_wunsch_nehmen(self.p, now=zeit + 5)              # taken once: gone afterwards

    def test_an_old_or_changed_wish_counts_as_none(self):
        for daten in ({"ids": ["gemma-4-26b-a4b"], "zeit": T0 - 3600}, {"ids": [], "zeit": T0},
                      {"ids": ["gemma-4-26b-a4b"] * 5, "zeit": T0}, {"ids": ["qwen3-asr-1.7b"], "zeit": T0},
                      {"ids": "gemma-4-26b-a4b", "zeit": T0}):
            with open(self.p, "w") as f:
                json.dump(daten, f)
            with self.assertRaises(modelle.Fehler, msg=daten):
                modelle.messen_wunsch_nehmen(self.p, now=T0)


class Laeuft(unittest.TestCase):
    """Dominik 2026-10-17: after „Messen“ nothing showed. A oneshot unit is "activating" for as long as it works."""
    def test_a_working_oneshot_unit_counts(self):
        for text, ok in (("activating", True), ("inactive\nactivating", True), ("active", True), ("deactivating", True),
                         ("inactive\nfailed", False), ("", False), ("unknown", False)):
            self.assertIs(modelle.im_gang(text), ok, text)

    def test_progress_lines_are_fixed_words_and_numbers_only(self):
        text = "\n".join(["Das lädt fehlende Modelle", "modelle: lade gemma-4-26b-a4b (falls noch nicht da)",
                          "modelle: frei zum messen 102.8 GiB", "INFO vllm: loading weights",
                          "modelle: messung x frage 1 erste 0.22 s, 400 tokens, 23.4 tok/s", "modelle: " + "x" * 200,
                          "modelle: antwort <b>hallo</b>", "modelle: Grüße"] + [f"modelle: messung x schritt {i}" for i in range(8)])
        got = modelle.stand(text)
        self.assertEqual(len(got), modelle.STAND_MAX)
        self.assertEqual(got[-1], "modelle: messung x schritt 7")
        self.assertTrue(all(modelle.STAND.match(x) for x in got))
        self.assertEqual(modelle.stand(text.split("modelle: messung x schritt 0")[0])[-2:],
                         ["modelle: frei zum messen 102.8 GiB", "modelle: messung x frage 1 erste 0.22 s, 400 tokens, 23.4 tok/s"])

    def test_the_panel_sees_a_working_unit_and_shows_its_lines(self):
        an = subprocess.CompletedProcess([], 3, "inactive\nactivating\n", "")
        with mock.patch.object(modellseite.subprocess, "run", return_value=an) as run, \
                mock.patch.object(modellseite, "journal", return_value="x\nmodelle: messung gemma-4-26b-a4b start\n") as j:
            self.assertTrue(modellseite._misst())
            self.assertEqual(modellseite._stand(), ["modelle: messung gemma-4-26b-a4b start"])
        self.assertEqual(run.call_args[0][0][:2], ["systemctl", "is-active"])
        self.assertEqual(j.call_args[0][0], modelle.MESS_WUNSCH_UNIT)
        with mock.patch.object(modellseite.subprocess, "run", return_value=subprocess.CompletedProcess([], 3, "inactive\ninactive\n", "")):
            self.assertFalse(modellseite._misst())
            self.assertFalse(modellseite._laeuft())
            self.assertEqual(modellseite._stand(), [])

    def test_lines_from_the_model_computer_are_checked_again(self):
        d = {"gesamt_gib": 121.0, "lanes": [], "messung": {}, "wechsel": {}, "eigene": [], "laeuft": False, "misst": True,
             "stand": ["modelle: frei zum messen 90.1 GiB", "<script>", 7, "modelle: Grüße"]}
        with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "call", return_value=d):
            self.assertEqual(modellseite._quelle(common.load_config())[7], ["modelle: frei zum messen 90.1 GiB"])
            d["misst"] = False
            self.assertEqual(modellseite._quelle(common.load_config())[7], [])
            d["stand"] = "modelle: x"
            with self.assertRaises(Exception):
                modellseite._quelle(common.load_config())       # not a list: the answer counts as none

    def test_the_shell_counts_a_working_oneshot_unit(self):
        sh = open(os.path.join(helpers.APP, "speech-spark.sh")).read()
        self.assertNotIn("systemctl is-active -q", sh)
        body = sh[sh.index("im_gang() {"):]
        body = body[:body.index("\n}\n") + 3]
        d = tempfile.mkdtemp()
        for state, rc in (("activating", 0), ("inactive", 1)):
            with open(os.path.join(d, "systemctl"), "w") as f:
                f.write(f"#!/bin/sh\necho inactive\necho {state}\nexit 3\n")
            os.chmod(os.path.join(d, "systemctl"), 0o755)
            r = subprocess.run(["bash", "-c", "set -euo pipefail\n" + body + "im_gang a b"],
                               env=dict(os.environ, PATH=d + os.pathsep + os.environ["PATH"]))
            self.assertEqual(r.returncode, rc, state)


class Panel(unittest.TestCase):
    def setUp(self):
        for k in [k for k in guard._rate if k[0] in ("modelle_messen", "modelle_wechsel", "modelle")]:
            guard._rate.pop(k, None)
        self.saved = modellseite._lanes, modellseite._laeuft, modellseite._misst
        modellseite._lanes = lambda: []
        modellseite._laeuft = lambda: False
        modellseite._misst = lambda: False
        self.addCleanup(lambda: os.path.exists(modelle.MESS_WUNSCH) and os.remove(modelle.MESS_WUNSCH))

    def tearDown(self):
        modellseite._lanes, modellseite._laeuft, modellseite._misst = self.saved
        helpers.set_config(modelle_wechseln=False)
        modellseite._live["t"] = None

    def test_off_by_default_and_admin_only(self):
        self.assertEqual(ADMIN.post("/api/admin/modelle/messen", json={"id": "gemma-4-26b-a4b"}).status_code, 409)
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.post("/api/admin/modelle/messen", json={"id": "gemma-4-26b-a4b"}).status_code, (401, 403))
        self.assertFalse(os.path.exists(modelle.MESS_WUNSCH))
        page = ADMIN.get("/api/admin/modelle").json()
        self.assertFalse(any(m["messbar"] for a in page["arten"] for m in a["modelle"]))

    def test_the_panel_leaves_a_checked_wish_and_starts_only_the_fixed_unit(self):
        helpers.set_config(modelle_wechseln=True)
        done = subprocess.CompletedProcess([], 0, b"", b"")
        out = io.StringIO()
        with mock.patch.object(modellseite.subprocess, "run", return_value=done) as run, \
                mock.patch.object(modelle, "gesamt_gib", return_value=128.0), redirect_stdout(out):
            self.assertEqual(ADMIN.post("/api/admin/modelle/messen", json={"id": "qwen3-asr-1.7b"}).status_code, 400)
            self.assertFalse(run.called)
            r = ADMIN.post("/api/admin/modelle/messen", json={"id": "qwen3-vl-30b-a3b-fp8"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(run.call_args[0][0], UNIT)
        self.assertEqual(modelle.messen_wunsch_nehmen(), ["qwen3-vl-30b-a3b-fp8"])
        self.assertIn("modelle: messen abgelehnt engine", out.getvalue())
        self.assertIn("modelle: messen angefragt", out.getvalue())
        self.assertIs(r.json()["wechsel"]["misst"], True)          # the page shows it at once, before the unit works
        rows = {m["id"]: m for a in r.json()["arten"] for m in a["modelle"]}
        self.assertTrue(rows["gemma-4-26b-a4b"]["messbar"])
        self.assertFalse(rows["qwen3-asr-1.7b"]["messbar"])

    def test_a_measurement_and_a_switch_never_run_at_once(self):
        helpers.set_config(modelle_wechseln=True)
        modellseite._misst = lambda: True
        with mock.patch.object(modellseite.subprocess, "run") as run, redirect_stdout(io.StringIO()):
            self.assertEqual(ADMIN.post("/api/admin/modelle/messen", json={"id": "gemma-4-26b-a4b"}).status_code, 409)
            target = "qwen3-asr-0.6b" if modelle.jetzt_id("asr", modelle.load_config()) != "qwen3-asr-0.6b" else "qwen3-asr-1.7b"
            self.assertEqual(ADMIN.post("/api/admin/modelle/wechseln", json={"art": "asr", "id": target}).status_code, 409)
            self.assertFalse(run.called)
            self.assertTrue(ADMIN.get("/api/admin/modelle").json()["wechsel"]["misst"])
        modellseite._misst, modellseite._laeuft = (lambda: False), (lambda: True)
        with mock.patch.object(modellseite.subprocess, "run") as run, redirect_stdout(io.StringIO()):
            self.assertEqual(ADMIN.post("/api/admin/modelle/messen", json={"id": "gemma-4-26b-a4b"}).status_code, 409)
            self.assertFalse(run.called)
        self.assertFalse(os.path.exists(modelle.MESS_WUNSCH))

    def test_live_shows_only_that_a_measurement_runs(self):
        modellseite._misst = lambda: True                 # also one from the command line, switch on or off
        modellseite._live["t"] = None
        v = modellseite.for_live(now=1e9)
        if v.get("on"):
            self.assertIs(v.get("messen"), True)
            self.assertEqual(set(v) - {"on", "frei", "regel", "eigen", "wechsel", "messen"}, set())


class Waerter(test_waerter.Base):
    """The models on another computer: the Wärter checks the same rule and starts its own fixed unit."""
    def test_measuring_there(self):
        out = io.StringIO()
        self.addCleanup(lambda: os.path.exists(modelle.MESS_WUNSCH) and os.remove(modelle.MESS_WUNSCH))
        with redirect_stdout(out):
            for args in (["x; reboot"], [], ["a", "b"]):
                self.assertEqual(self.post(test_waerter.body("messen", args)).status_code, 400, args)
            bad = self.post(test_waerter.body("messen", ["qwen3-asr-1.7b"])).json()
            self.assertEqual(bad, {"ok": False, "fehler": "engine"})
            self.assertFalse([c for c in self.run.calls if "sudo" in c])
            good = self.post(test_waerter.body("messen", ["gemma-4-26b-a4b"])).json()
        self.assertEqual(good["ok"], True, good)
        self.assertIn(UNIT, self.run.calls)
        self.assertEqual(modelle.messen_wunsch_nehmen(), ["gemma-4-26b-a4b"])
        self.assertIn("waerter: messen ok", out.getvalue())
        self.assertIn("waerter: messen abgelehnt engine", out.getvalue())
        d = self.post(test_waerter.body("modelle")).json()
        self.assertIs(d["misst"], False)
        self.assertEqual(d["stand"], [])

    def test_a_running_measurement_there_shows_its_lines(self):
        alt = self.run.__class__.__call__

        def run(fake, cmd, timeout=10, env=None):
            if cmd[:2] == ["systemctl", "is-active"] and modelle.MESS_UNIT in cmd:
                fake.calls.append(cmd)
                return 3, "activating\ninactive\n"
            return alt(fake, cmd, timeout, env)
        with mock.patch.object(test_waerter.FakeRun, "__call__", run), \
                mock.patch.object(tarswart, "journal", return_value="modelle: lade x\nAntwort: hallo\n") as j, \
                redirect_stdout(io.StringIO()):
            d = self.post(test_waerter.body("modelle")).json()
            self.assertEqual(self.post(test_waerter.body("wechseln", ["asr", "qwen3-asr-0.6b"])).json()["fehler"], "misst")
        self.assertIs(d["misst"], True)
        self.assertEqual(d["stand"], ["modelle: lade x"])
        self.assertEqual(j.call_args[0][0], modelle.MESS_UNIT)

    def test_the_panel_takes_the_flag_and_an_old_waerter_without_it(self):
        d = {"gesamt_gib": 121.0, "lanes": [], "messung": {}, "wechsel": {}, "eigene": [], "laeuft": False}
        for extra, ok in (({}, True), ({"misst": True}, True), ({"misst": "ja"}, False)):
            with mock.patch.object(steuer, "call", return_value=dict(d, **extra)):
                self.assertEqual(steuer.modelle(common.load_config()) is not None, ok, extra)


class Kommando(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(helpers.APP, "speech-spark.sh")) as f:
            cls.sh = f.read()
        p = os.path.join(os.path.dirname(helpers.APP), "install.sh")
        cls.inst = open(p).read() if os.path.exists(p) else None    # a copy with only app/ has no install.sh

    def body(self, name):
        s = self.sh[self.sh.index(name + "() {"):]
        return s[:s.index("\n}\n")]

    def test_root_takes_only_checked_ids_and_waits_for_the_others(self):
        b = self.body("cmd_messen_wunsch")
        self.assertIn("modelle.py messen-wunsch-nehmen", b)
        self.assertLess(b.index('=~ ^[a-z0-9][a-z0-9.-]{1,47}$'), b.index('cmd_messen_intern "${ids[@]}"'))
        self.assertLess(b.index('"$MESS_UNIT" "$WECHSEL_UNIT" speech-spark-update'), b.index('cmd_messen_intern'))
        self.assertIn('messen-wunsch-intern) [ "${INVOCATION_ID:-}" ] || die', self.sh)
        self.assertIn('echo "modelle: wechsel abgelehnt misst"', self.body("cmd_wunsch_intern"))
        self.assertIn('"$MESS_UNIT" "$MESS_WUNSCH_UNIT"', self.body("run_wechsel"))
        self.assertEqual(modelle.MESS_UNIT, "speech-spark-messen")
        self.assertIn(f"MESS_WUNSCH_UNIT={modelle.MESS_WUNSCH_UNIT}", self.sh)

    def test_the_panel_may_start_only_the_fixed_unit(self):
        if self.inst is None:
            self.skipTest("install.sh is not part of an app/-only copy")
        self.assertIn("/usr/bin/systemctl start --no-block speech-spark-messen-wunsch\\n'", self.inst)
        self.assertIn("ExecStart=/bin/bash $PREFIX/app/speech-spark.sh modelle messen-wunsch-intern", self.inst)


if __name__ == "__main__":
    unittest.main()
