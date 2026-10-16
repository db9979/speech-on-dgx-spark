"""The engines start one after the other and only when they must (tars 2026-10-16: a run of `install.sh --musik 2b`
restarted every engine, the own language model last; it loaded while the TTS engine sized its memory, and the TTS
engine failed with "No available memory for the cache blocks" every 30 seconds). install.sh restarts an engine only
when its signature changed or it is not running, the language model first; engine.sh waits through another engine's
stop and restart and while it loads for up to an hour; the panel's estimate is of the model computer's memory."""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import admin  # noqa: E402
import modelle  # noqa: E402


def _install():
    path = os.path.join(helpers.APP, "..", "install.sh")
    if not os.path.exists(path):
        raise unittest.SkipTest("install.sh is not part of this copy")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _block(text, start, end):
    """The lines of a shell script from the line starting with `start` through the next line equal to `end`."""
    i = text.index(start)
    j = text.index("\n" + end + "\n", i)
    return text[i:j + len(end) + 1]


class RestartEngine(unittest.TestCase):
    """install.sh's restart_engine, run in bash with systemctl replaced by a recorder."""

    def run_it(self, sig, active=True, from_update=0):
        fn = _block(_install(), "restart_engine() {", "}")
        script = f"""set -e
VAR={self.tmp}; PREFIX={self.tmp}; FROM_UPDATE={from_update}
systemctl() {{ case "$1" in is-active) [ "{int(active)}" = 1 ] ;; restart) echo "$2" >>{self.tmp}/restarts ;; *) : ;; esac; }}
as_svc() {{ "$@"; }}
no_links() {{ :; }}
{fn}
restart_engine llm "{sig}"
"""
        subprocess.run(["bash", "-c", script], check=True, timeout=30)
        path = os.path.join(self.tmp, "restarts")
        return open(path).read().split() if os.path.exists(path) else []

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "state"))
        os.makedirs(os.path.join(self.tmp, "app"))
        with open(os.path.join(self.tmp, "app", "engine.sh"), "w") as f:
            f.write("engine\n")

    def test_a_run_by_hand_leaves_an_unchanged_running_engine(self):
        self.assertEqual(self.run_it("v1 abc"), ["speech-spark-llm.service"])          # first install: no signature yet
        self.assertEqual(self.run_it("v1 abc"), ["speech-spark-llm.service"])          # by hand, nothing changed: no restart
        self.assertEqual(self.run_it("v1 abc", from_update=1), ["speech-spark-llm.service"])

    def test_a_changed_signature_or_a_stopped_engine_restarts(self):
        self.run_it("v1 abc")
        self.assertEqual(len(self.run_it("v2 abc")), 2)                                # new settings
        self.assertEqual(len(self.run_it("v2 abc", active=False)), 3)                  # not running

    def test_the_language_model_restarts_before_the_speech_engines(self):
        ins = _install()
        llm = ins.index("restart_engine llm ")
        self.assertLess(llm, ins.index("restart_engine asr-engine "))
        self.assertLess(llm, ins.index("restart_engine tts-engine "))
        self.assertIn("modelle.py\" signatur llm", ins)


class Signatur(unittest.TestCase):
    def test_only_the_language_models_own_entry_counts(self):
        kat = modelle.katalog()
        cfg = {"llm": {"modell": "qwen38-27b-nvfp4", "engine_port": 31016}}
        sig = modelle.signatur("llm", cfg, messung={}, kat=kat)
        self.assertRegex(sig, r"^[0-9a-f]{16}$")
        other = dict(kat)
        musik = next(k for k, m in kat.items() if m["art"] == "musik")
        other[musik] = dict(kat[musik], need_gib=kat[musik]["need_gib"] + 1)       # a music model changed
        self.assertEqual(modelle.signatur("llm", cfg, messung={}, kat=other), sig)
        other["qwen38-27b-nvfp4"] = dict(kat["qwen38-27b-nvfp4"], anteil=0.31)        # the language model's share changed
        self.assertNotEqual(modelle.signatur("llm", cfg, messung={}, kat=other), sig)
        self.assertNotEqual(modelle.signatur("llm", dict(cfg, llm=dict(cfg["llm"], engine_port=31018)), messung={}, kat=kat), sig)
        with mock.patch.object(modelle, "vllm_args", side_effect=lambda *a, **k: ["neue-option"]):
            self.assertNotEqual(modelle.signatur("llm", cfg, messung={}, kat=kat), sig)   # a new start option restarts it


class EngineWait(unittest.TestCase):
    """engine.sh's wait for the engines before it, run in bash with systemctl, curl and sleep replaced."""

    def test_waits_through_a_restart_and_a_long_load(self):
        with open(os.path.join(helpers.APP, "engine.sh"), encoding="utf-8") as f:
            loop = _block(f.read(), 'for o in "${others[@]}"; do', "done")
        tmp = tempfile.mkdtemp()
        # the language model stops, starts again and loads for 25 minutes (300 looks of 5 s) before it answers
        states = ["deactivating"] * 3 + ["activating"] * 2 + ["active"] * 400
        with open(os.path.join(tmp, "states"), "w") as f:
            f.write("\n".join(states) + "\n")
        # systemctl runs in $(…), a subshell: the count of its calls lives in a file
        script = f"""echo 0 >{tmp}/n
systemctl() {{ local n; n=$(( $(cat {tmp}/n) + 1 )); echo "$n" >{tmp}/n; sed -n "${{n}}p" {tmp}/states; }}
curl() {{ [ "$(cat {tmp}/n)" -gt 305 ]; }}
state() {{ echo "$1" >>{tmp}/looks; }}
sleep() {{ :; }}
others=("speech-spark-llm 31016")
{loop}
"""
        subprocess.run(["bash", "-c", script], check=True, timeout=60)
        self.assertEqual(open(os.path.join(tmp, "n")).read().strip(), "306")             # it waited until /health answered
        self.assertEqual(len(open(os.path.join(tmp, "looks")).read().split()), 305)


class Estimate(unittest.TestCase):
    """Zustand → Dienste: what an engine reserves, of the memory of the computer it runs on."""

    def test_the_share_is_of_the_model_computers_memory(self):
        cfg = admin.load_config()
        cfg["tts"].update(backend="vllm-omni", engine_mem_talker=0.06, engine_mem_code2wav=0.025, voicedesign_enabled=False)
        remote = {"cpu": 1, "load": None, "mem_total_gib": 121.0, "mem_avail_gib": 60.0, "mem_used_pct": 50.4,
                  "mem_von": "modell-rechner"}
        with mock.patch.object(admin, "system_stats", return_value=remote):
            s = admin._status(cfg, {})
        self.assertEqual(s["services"]["tts"]["engines"][0]["estimate_gib"], 11.8)       # not ~2.2 from the Pi's 8 GB
        with mock.patch.object(admin, "system_stats", return_value=dict(remote, mem_total_gib=None)):
            s = admin._status(cfg, {})
        self.assertIsNone(s["services"]["tts"]["engines"][0]["estimate_gib"])           # tars does not answer: no guess


if __name__ == "__main__":
    unittest.main()
