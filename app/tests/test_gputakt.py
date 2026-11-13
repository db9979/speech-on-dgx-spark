"""GPU-Taktgrenze (Dominik 2026-11-13, Einstellungen → Spark → Betrieb → GPU-Taktgrenze): a ceiling on the model computer's
GPU clock. The protection rules, each with its test:

- off by default ("aus"), only the fixed values of gputakt.STUFEN, the panel refuses any other;
- the panel never hands nvidia-smi an argument: it only starts the fixed root unit, and only when the setting changed;
  root reads the setting itself and knows only the fixed values (anything else sets no cap);
- the sudoers allow exactly that start, the unit has its limits and runs only where nvidia-smi is;
- the Wärter starts the unit after it took the panel's settings; the state reaches the pages through gpu_stats;
- every outcome writes one log line with fixed words.
Nothing depends on the time of day."""
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import common  # noqa: E402
import gputakt  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def cfg(v):
    return {"watch": {"gpu_takt": v}}


class Wahl(unittest.TestCase):
    def test_off_by_default_and_only_fixed_values(self):
        self.assertEqual(common.shipped()["watch"]["gpu_takt"], "aus")
        self.assertEqual(gputakt.STUFEN, ("aus", "2400", "2200", "2000"))
        for bad in ("2500", "0,2400", "2400; reboot", 2400, None, "", "-rgc"):
            self.assertEqual(gputakt.wahl(cfg(bad)), "aus", bad)
        self.assertEqual(gputakt.wahl({}), "aus")
        self.assertEqual(gputakt.wahl(cfg("2200")), "2200")

    def test_the_state_file_only_fixed_words(self):
        lies = lambda text: (lambda path: text)  # noqa: E731
        self.assertEqual(gputakt.stand(lies("2400 1763040000\n")), {"wort": "2400", "t": 1763040000})
        self.assertEqual(gputakt.stand(lies("fehler 5")), {"wort": "fehler", "t": 5})
        for bad in ("", "2500 5", "2400", "2400 x", "<b>2400</b> 5", "aus 5 6"):
            self.assertIsNone(gputakt.stand(lies(bad)), bad)

        def weg(path):
            raise FileNotFoundError(path)
        self.assertIsNone(gputakt.stand(weg))


class Anwenden(unittest.TestCase):
    def test_nothing_when_unchanged(self):
        with mock.patch.object(gputakt, "run") as run:
            self.assertTrue(gputakt.anwenden(cfg("2400"), cfg("2400")))
            self.assertTrue(gputakt.anwenden(cfg("aus"), {}))
        run.assert_not_called()

    def test_only_the_fixed_unit_start(self):
        out = io.StringIO()
        with mock.patch.object(gputakt.os.path, "exists", lambda p: True), \
                mock.patch.object(gputakt, "run", return_value=(0, "")) as run, redirect_stdout(out):
            self.assertTrue(gputakt.anwenden(cfg("aus"), cfg("2000"), "waerter"))
        run.assert_called_once_with(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "speech-spark-gpu-takt"], timeout=20)
        self.assertIn("gputakt: waerter 2000 gestartet", out.getvalue())
        out = io.StringIO()
        with mock.patch.object(gputakt.os.path, "exists", lambda p: True), \
                mock.patch.object(gputakt, "run", return_value=(1, "")), redirect_stdout(out):
            self.assertFalse(gputakt.anwenden(cfg("2000"), cfg("aus")))
        self.assertIn("gputakt: panel aus fehler", out.getvalue())

    def test_without_a_gpu_only_a_line(self):
        out = io.StringIO()
        with mock.patch.object(gputakt.os.path, "exists", lambda p: False), \
                mock.patch.object(gputakt, "run") as run, redirect_stdout(out):
            self.assertTrue(gputakt.anwenden(cfg("aus"), cfg("2400")))
        run.assert_not_called()
        self.assertIn("gputakt: panel 2400 ohne gpu", out.getvalue())


class Panel(unittest.TestCase):
    def test_the_setting_is_checked_and_saving_starts_the_unit(self):
        old = ADMIN.get("/api/config").json()
        self.addCleanup(lambda: ADMIN.put("/api/config", json=old))
        for bad in ("2500", "0,2400", 2400, "2400; reboot"):
            r = ADMIN.put("/api/config", json=dict(old, watch=dict(old["watch"], gpu_takt=bad)))
            self.assertEqual(r.status_code, 400, bad)
        with mock.patch.object(gputakt, "anwenden") as anw:
            r = ADMIN.put("/api/config", json=dict(old, watch=dict(old["watch"], gpu_takt="2200")))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(ADMIN.get("/api/config").json()["watch"]["gpu_takt"], "2200")
        anw.assert_called_once()
        self.assertEqual(gputakt.wahl(anw.call_args[0][1]), "2200")
        self.assertIn("watch", common.SYNC_SECTIONS, "the model computer gets the setting with the speech settings")

    def test_the_gpu_state_carries_the_cap(self):
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), \
                mock.patch.object(common, "run", side_effect=[(0, "NVIDIA GB10, 5, 60, 35.9, 2387, [N/A], [N/A]"), (0, "")]), \
                mock.patch.object(gputakt, "stand", return_value={"wort": "2400", "t": 1}):
            g = common.gpu_stats()
        self.assertEqual(g["grenze"], {"wort": "2400", "t": 1})
        self.assertEqual(g["clock"], 2387)


class Waerter(unittest.TestCase):
    def test_taking_the_settings_starts_the_unit(self):
        import tarswart
        with mock.patch.object(tarswart, "write_json"), mock.patch.object(gputakt, "anwenden") as anw, \
                redirect_stdout(io.StringIO()):
            tarswart.einstellen({"watch": {"gpu_takt": "2000"}})
        anw.assert_called_once()
        self.assertEqual(anw.call_args[0][2], "waerter")


class Root(unittest.TestCase):
    """The root part of speech-spark.sh (gputakt_setzen) with a stand-in nvidia-smi that writes down its arguments."""
    def setUp(self):
        path = os.path.join(APP, "speech-spark.sh")
        if not os.path.exists(path):
            self.skipTest("speech-spark.sh missing")
        with open(path) as f:
            sh = f.read()
        self.src = sh[sh.index("GPU_TAKT_STAND="):sh.index("cmd_gputakt() {")]
        self.dir = tempfile.mkdtemp(dir=helpers.TMP)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.args = os.path.join(self.dir, "args")
        self.smi = os.path.join(self.dir, "nvidia-smi")
        with open(self.smi, "w") as f:
            f.write(f'#!/bin/bash\necho "$*" >> {self.args}\nexit ${{SMI_EXIT:-0}}\n')
        os.chmod(self.smi, os.stat(self.smi).st_mode | stat.S_IXUSR)
        self.stand = os.path.join(self.dir, "run", "stand")
        self.cfg = os.path.join(self.dir, "config.json")

    def setzen(self, wert, exit_code=0):
        with open(self.cfg, "w") as f:
            json.dump({"watch": {"gpu_takt": wert}}, f)
        if os.path.exists(self.args):
            os.remove(self.args)
        env = dict(os.environ, SPEECH_SPARK_GPU_TAKT=self.stand, SPEECH_SPARK_NVSMI=self.smi, SMI_EXIT=str(exit_code))
        stubs = f"cfg() {{ python3 -c 'import json,sys; v=json.load(open(sys.argv[1]))[\"watch\"][\"gpu_takt\"]; print(v)' {self.cfg}; }}\n"
        r = subprocess.run(["bash", "-c", "set -euo pipefail\n" + self.src + stubs + "gputakt_setzen"],
                           env=env, capture_output=True, text=True, timeout=30)
        args = open(self.args).read().split("\n")[0] if os.path.exists(self.args) else None
        return r, args, open(self.stand).read().split()[0] if os.path.exists(self.stand) else None

    def test_only_the_two_fixed_commands(self):
        r, args, st = self.setzen("2400")
        self.assertEqual((r.returncode, args, st), (0, "-lgc 0,2400", "2400"), r.stderr)
        self.assertIn("gputakt: gesetzt 2400", r.stdout)
        r, args, st = self.setzen("aus")
        self.assertEqual((r.returncode, args, st), (0, "-rgc", "aus"), r.stderr)
        for bad in ("2500", "0,2400 -pm 1", "2400; touch x", "$(id)"):
            r, args, st = self.setzen(bad)
            self.assertEqual((args, st), ("-rgc", "aus"), bad)
            self.assertIn("gputakt: abgelehnt wert", r.stdout)
        r, args, st = self.setzen("2000", exit_code=3)
        self.assertEqual((r.returncode, st), (1, "fehler"))
        self.assertIn("gputakt: fehler 2000", r.stdout)


class Install(unittest.TestCase):
    def test_sudoers_and_unit(self):
        src = helpers.repo_file("install.sh")
        if not src:
            self.skipTest("install.sh missing (copy with app/ only)")
        self.assertIn("printf ', /usr/bin/systemctl start --no-block speech-spark-gpu-takt'", src)
        unit = src[src.index("cat >/etc/systemd/system/speech-spark-gpu-takt.service"):]
        unit = unit[:unit.index("\nUNIT\n")]
        for line in ("ConditionPathExists=/usr/bin/nvidia-smi", "MemoryMax=", "PrivateTmp=yes", "Type=oneshot",
                     "ExecStart=/bin/bash $PREFIX/app/speech-spark.sh gputakt intern", "WantedBy=multi-user.target",
                     "RuntimeDirectoryPreserve=yes"):
            self.assertIn(line, unit)
        self.assertIn("systemctl enable speech-spark-gpu-takt.service", src)


if __name__ == "__main__":
    unittest.main()
