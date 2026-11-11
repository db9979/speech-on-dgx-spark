"""Modelle wechseln, stage E4 (modelle.py wechsel_*, panel modellseite.py, speech-spark modelle wechseln|zurueckholen|
entfernen; plan plaene/eigene-modelle.md): only catalog models of the same kind, an own engine only on a pinned commit,
the language model only while the own one is on, never one that leaves the budget too tight; the old model can be brought back
for 7 days and is never removed while it runs or within those days; the panel only leaves a checked wish for the root
unit speech-spark-wechsel, behind an admin switch that is off by default. Nothing depends on the time of day."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000.0
DAY = 86400
VL = "qwen3-vl-8b-fp8"
MESSUNG = {"modelle": {VL: {"ok": True, "revision": "9" * 40}}}
OHNE = "qwen36-35b-a3b-nvfp4-ohne-mtp"


def kat_mit_alten():
    """The catalog plus two made-up entries (the catalog keeps one model per kind that switches since 2026-11-11):
    an older eye model to switch away from, and a language model on an engine that is not vLLM."""
    k = copy.deepcopy(modelle.katalog())
    alt = copy.deepcopy(k[VL])
    alt.update(id="sehen-alt", repo="beispiel/sehen-alt")
    fremd = copy.deepcopy(k["qwen36-35b-a3b-nvfp4"])
    fremd.update(id="fremde-engine", engine="extern", repo="")
    k.update({"sehen-alt": alt, "fremde-engine": fremd})
    return k


KAT = kat_mit_alten()


def cfg(**over):
    c = {"chat": {"llm_url": "http://127.0.0.1:31006/v1"}, "memory": {"reserve_gib": 10},
         "llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4", "sehen_modell": "sehen-alt"},
         "asr": {"enabled": True, "recognizer": "qwen", "model": "Qwen/Qwen3-ASR-1.7B"},
         "tts": {"enabled": True, "model": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"},
         "image": {"enabled": False, "variant": "4b-q8"}}
    for k, v in over.items():
        c[k] = dict(c.get(k, {}), **v)
    return c


class Regeln(unittest.TestCase):
    def test_what_runs_now(self):
        c = cfg()
        self.assertEqual(modelle.jetzt_id("llm", c), "qwen36-35b-a3b-nvfp4")
        self.assertEqual(modelle.jetzt_id("sehen", c, KAT), "sehen-alt")
        self.assertEqual(modelle.jetzt_id("sehen", c), "")                   # one the catalog does not know
        self.assertEqual(modelle.jetzt_id("asr", c), "qwen3-asr-1.7b")
        self.assertEqual(modelle.jetzt_id("tts", c), "qwen3-tts-0.6b")
        self.assertEqual(modelle.jetzt_id("bild", c), "")
        self.assertEqual(modelle.jetzt_id("asr", cfg(asr={"recognizer": "parakeet"})), "parakeet-primeline")
        self.assertEqual(modelle.jetzt_id("llm", cfg(llm={"enabled": False})), "")

    def test_fixed_rules(self):
        c = cfg()
        ok = modelle.wechsel_pruefen("sehen", VL, c, 120, KAT, messung=MESSUNG)
        self.assertEqual(ok["id"], VL)
        cases = [("musik", VL, c, "art"), ("llm", VL, c, "art"), ("llm", "gibts-nicht", c, "unbekannt"),
                 ("llm", "fremde-engine", c, "engine"), ("sehen", VL, c, "revision"),
                 ("llm", OHNE, cfg(llm={"enabled": False}), "aus"),
                 ("asr", "qwen3-forcedaligner-0.6b", c, "wahl"), ("asr", "qwen3-asr-1.7b", c, "schon")]
        for art, mid, cc, word in cases:
            with self.assertRaisesRegex(modelle.Fehler, f"^{word}$", msg=(art, mid)):
                modelle.wechsel_pruefen(art, mid, cc, 120, KAT, messung={} if word == "revision" else MESSUNG)
        with self.assertRaisesRegex(modelle.Fehler, "^budget$"):       # the panel decides from numbers, never a model
            modelle.wechsel_pruefen("llm", OHNE, c, 30, KAT, messung=MESSUNG)

    def test_the_switched_configuration(self):
        c = cfg()
        self.assertEqual(modelle.mit_wechsel(c, "llm", modelle.eintrag(OHNE))["llm"]["modell"], OHNE)
        p = modelle.mit_wechsel(c, "asr", modelle.eintrag("parakeet-primeline"))["asr"]
        self.assertEqual((p["recognizer"], p["model"]), ("parakeet", "Qwen/Qwen3-ASR-1.7B"))
        self.assertEqual(modelle.mit_wechsel(c, "bild", modelle.eintrag("flux2-klein-9b-q4") if "flux2-klein-9b-q4" in
                         modelle.katalog() else modelle.zur_variante("bild", "9b-q4"))["image"]["variant"], "9b-q4")
        self.assertEqual(c["llm"]["modell"], "qwen36-35b-a3b-nvfp4")              # the original stays as it was


class Zurueck(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.w = os.path.join(self.d, "modelle-wechsel.json")

    def test_seven_days_to_bring_it_back(self):
        modelle.wechsel_merken("sehen", "sehen-alt", VL, now=T0, path=self.w)
        self.assertEqual(modelle.zurueck_ziel("sehen", now=T0 + 6 * DAY, path=self.w), "sehen-alt")
        with self.assertRaisesRegex(modelle.Fehler, "frist"):
            modelle.zurueck_ziel("sehen", now=T0 + 8 * DAY, path=self.w)
        with self.assertRaisesRegex(modelle.Fehler, "keins"):
            modelle.zurueck_ziel("asr", now=T0, path=self.w)
        c = cfg(llm={"sehen_modell": VL})
        self.assertEqual(modelle.alte(c, now=T0 + 2 * DAY, path=self.w, kat=KAT), {"sehen": {"id": "sehen-alt", "tage_frei": 5}})
        self.assertEqual(modelle.alte(c, now=T0 + 9 * DAY, path=self.w, kat=KAT)["sehen"]["tage_frei"], 0)

    def test_never_removed_while_it_runs_or_within_the_days(self):
        hf = os.path.join(self.d, "hf")
        os.makedirs(modelle.hf_ordner(KAT["sehen-alt"], hf))
        os.makedirs(modelle.hf_ordner(modelle.eintrag("qwen3-asr-0.6b"), hf))
        c = cfg(llm={"sehen_modell": VL})
        modelle.wechsel_merken("sehen", "sehen-alt", VL, now=T0, path=self.w)
        with self.assertRaisesRegex(modelle.Fehler, "frist"):
            modelle.entfernbar("sehen-alt", c, now=T0 + DAY, path=self.w, kat=KAT, hf_home=hf)
        self.assertTrue(modelle.entfernbar("sehen-alt", c, now=T0 + 8 * DAY, path=self.w, kat=KAT, hf_home=hf).endswith(
            "models--beispiel--sehen-alt"))
        with self.assertRaisesRegex(modelle.Fehler, "aktiv"):
            modelle.entfernbar("qwen3-asr-1.7b", c, now=T0, path=self.w, kat=KAT, hf_home=hf)
        with self.assertRaisesRegex(modelle.Fehler, "aktiv"):
            modelle.entfernbar(VL, c, now=T0, path=self.w, kat=KAT, hf_home=hf)
        with self.assertRaisesRegex(modelle.Fehler, "art"):
            modelle.entfernbar("fremde-engine", c, now=T0, path=self.w, kat=KAT, hf_home=hf)   # no cache folder of its own
        self.assertTrue(modelle.entfernbar("qwen3-asr-0.6b", c, now=T0, path=self.w, kat=KAT, hf_home=hf))
        with self.assertRaisesRegex(modelle.Fehler, "fehlt"):
            modelle.entfernbar("qwen3-tts-1.7b", c, now=T0, path=self.w, kat=KAT, hf_home=hf)


class Wunsch(unittest.TestCase):
    def test_root_takes_a_checked_wish_once(self):
        p = os.path.join(tempfile.mkdtemp(), "w.json")
        modelle.wunsch_schreiben("sehen", VL, p)
        self.assertEqual(modelle.wunsch_nehmen(p), ("sehen", VL))
        self.assertFalse(os.path.exists(p))
        with self.assertRaisesRegex(modelle.Fehler, "wunsch"):
            modelle.wunsch_nehmen(p)
        for art, was in (("musik", VL), ("sehen", "x; rm -rf /"), ("sehen", "../x")):
            with self.assertRaisesRegex(modelle.Fehler, "wunsch"):
                modelle.wunsch_schreiben(art, was, p)
        with open(p, "w") as f:
            json.dump({"art": "asr", "was": "qwen3-asr-0.6b", "zeit": T0}, f)
        with self.assertRaisesRegex(modelle.Fehler, "wunsch"):
            modelle.wunsch_nehmen(p, now=T0 + 3600)                    # an old wish counts as none


class Panel(unittest.TestCase):
    def setUp(self):
        for k in [k for k in guard._rate if k[0] in ("modelle_wechsel", "modelle")]:
            guard._rate.pop(k, None)
        self.saved = modellseite._laeuft, modellseite._misst
        modellseite._laeuft = lambda: False
        modellseite._misst = lambda: False        # no measurement runs (test_messen_knopf checks one that does)

    def tearDown(self):
        modellseite._laeuft, modellseite._misst = self.saved
        helpers.set_config(modelle_wechseln=False)
        try:
            os.remove(modelle.WUNSCH)
        except OSError:
            pass

    def test_off_by_default_and_admin_only(self):
        self.assertNotIn("modellwechsel", features.DEFAULT_ON)
        self.assertIn("modellwechsel", features.SPARK_ONLY)
        self.assertEqual(ADMIN.post("/api/admin/modelle/wechseln", json={"art": "asr", "id": "qwen3-asr-0.6b"}).status_code, 409)
        self.assertFalse(os.path.exists(modelle.WUNSCH))
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.post("/api/admin/modelle/wechseln", json={"art": "asr", "id": "qwen3-asr-0.6b"}).status_code, (401, 403))
        self.assertIn(anon.post("/api/admin/modelle/zurueck", json={"art": "asr"}).status_code, (401, 403))
        self.assertFalse(ADMIN.get("/api/admin/modelle").json()["wechsel"]["an"])

    def test_the_panel_only_leaves_a_checked_wish_and_starts_the_fixed_unit(self):
        helpers.set_config(modelle_wechseln=True)
        done = subprocess.CompletedProcess([], 0, b"", b"")
        with mock.patch.object(modellseite.subprocess, "run", return_value=done) as run, \
                mock.patch.object(modelle, "gesamt_gib", return_value=128.0):
            bad = ADMIN.post("/api/admin/modelle/wechseln", json={"art": "asr", "id": "qwen3-forcedaligner-0.6b"})
            self.assertEqual(bad.status_code, 400)
            self.assertFalse(run.called)
            self.assertFalse(os.path.exists(modelle.WUNSCH))
            target = "qwen3-asr-0.6b" if modelle.jetzt_id("asr", modelle.load_config()) != "qwen3-asr-0.6b" else "qwen3-asr-1.7b"
            r = ADMIN.post("/api/admin/modelle/wechseln", json={"art": "asr", "id": target})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(run.call_args[0][0], ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "speech-spark-wechsel"])
        self.assertEqual(modelle.wunsch_nehmen(), ("asr", target))
        self.assertEqual(ADMIN.post("/api/admin/modelle/zurueck", json={"art": "musik"}).status_code, 400)

    def test_live_shows_only_that_a_switch_runs(self):
        helpers.set_config(modelle_wechseln=True)
        modellseite._laeuft = lambda: True
        modellseite._live["t"] = None
        try:
            v = modellseite.for_live(now=1e9)
            if v.get("on"):
                self.assertIs(v.get("wechsel"), True)
                self.assertEqual(set(v) - {"on", "frei", "regel", "eigen", "wechsel"}, set())
        finally:
            modellseite._live["t"] = None


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

    def test_root_checks_again_before_anything_happens(self):
        b = self.body("wechsel")
        self.assertLess(b.index("modelle.py wechsel-pruefen"), b.index("install.sh"))
        self.assertLess(b.index("modelle.py wechsel-pruefen"), b.index("modelle.py vorbereiten"))
        self.assertLess(b.index("modelle.py vorbereiten"), b.index("wechsel-schalten \"$art\""))      # checked before it switches
        self.assertLess(b.index("modelle.py rundlauf"), b.index("wechsel-merken"))
        self.assertIn('wechsel-schalten llm "$alt"', b)                                             # a failed round trip goes back
        self.assertIn("modelle: wechsel $art zurueckgenommen", b)
        self.assertIn("modelle.py wunsch-nehmen", self.body("cmd_wunsch_intern"))
        self.assertIn('wunsch-intern) [ "${INVOCATION_ID:-}" ] || die', self.sh)
        self.assertNotIn("rm -", b + self.body("cmd_wunsch_intern") + self.body("run_wechsel"))

    def test_removing_asks_and_stays_in_the_cache(self):
        b = self.body("cmd_entfernen")
        self.assertIn("modelle.py entfernbar", b)
        self.assertIn('[[ "$dir" == "$VAR/hf/hub/models--"* ]]', b)
        self.assertLess(b.index('ask_yes "${2:-}"'), b.index("rm -rf"))
        self.assertNotIn("qwen38", b)

    def test_the_panel_may_start_only_the_fixed_unit(self):
        if self.inst is None:
            self.skipTest("install.sh is not part of an app/-only copy")
        self.assertIn("/usr/bin/systemctl start --no-block speech-spark-wechsel'", self.inst)
        self.assertIn("ExecStart=/bin/bash $PREFIX/app/speech-spark.sh modelle wunsch-intern", self.inst)


if __name__ == "__main__":
    unittest.main()
