"""Mischbetrieb (app/mischbetrieb.py, plan alzeo-mischbetrieb M2/M5, Dominik 2026-11-18 „1a 2a 3a“): another project
(Alzeo) gets the DGX Spark's GPU, the Spark keeps Hören and Sprechen with the small models. „an“ remembers exactly
what it changes and „aus“ restores exactly that; while it is on nothing of the language model, Bilder or Musik starts,
switches or is measured; the panel computer answers with a fixed sentence or the foreign model service, the
Dienst-Wächter counts no outage, and the Live view says it. No time of day."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import fremdmodell  # noqa: E402
import llm  # noqa: E402
import mischbetrieb  # noqa: E402
import modelle  # noqa: E402
import steuer  # noqa: E402
import wartung  # noqa: E402

FREMD = llm.fremd   # the real one, before a test replaces it
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Ablage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="misch-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.datei = os.path.join(self.tmp, "mischbetrieb.json")
        p = mock.patch.object(mischbetrieb, "DATEI", self.datei)
        p.start()
        self.addCleanup(p.stop)
        self.kat = modelle.katalog()
        self.geschrieben = []

    def schreib(self, raw):
        self.geschrieben.append(json.loads(json.dumps(raw)))

    def cfg(self, asr="Qwen/Qwen3-ASR-1.7B", tts="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"):
        return {"llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4"}, "image": {"enabled": True},
                "music": {"enabled": False}, "asr": {"enabled": True, "recognizer": "qwen", "model": asr},
                "tts": {"enabled": True, "model": tts, "voicedesign_enabled": True}}


class AnAus(Ablage):
    def test_an_remembers_and_aus_restores_exactly(self):
        roh = {"llm": {"enabled": True, "port": 31006}, "image": {"enabled": True, "variant": "4b-q8"},
               "tts": {"voicedesign_enabled": True}, "chat": {"llm_url": "x"}}
        wechsel = mischbetrieb.an(self.cfg(), self.kat, roh=json.loads(json.dumps(roh)), schreib=self.schreib, now=0)
        self.assertEqual(wechsel, [("asr", "qwen3-asr-0.6b"), ("tts", "qwen3-tts-0.6b")])
        neu = self.geschrieben[-1]
        self.assertEqual((neu["llm"]["enabled"], neu["image"]["enabled"], neu["music"]["enabled"],
                          neu["tts"]["voicedesign_enabled"], neu["tts"]["klon_enabled"]), (False,) * 5)
        self.assertEqual((neu["llm"]["port"], neu["image"]["variant"], neu["chat"]), (31006, "4b-q8", {"llm_url": "x"}))
        self.assertTrue(mischbetrieb.ist_an())
        self.assertEqual(oct(os.stat(self.datei).st_mode & 0o777), "0o600")
        self.assertEqual(mischbetrieb.an(self.cfg(), self.kat, roh={}, schreib=self.schreib), [], "a second an: nothing")
        self.assertEqual(len(self.geschrieben), 1)
        klein = self.cfg("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
        back = mischbetrieb.aus(klein, self.kat, roh=json.loads(json.dumps(neu)), schreib=self.schreib)
        self.assertEqual(back, [("asr", "qwen3-asr-1.7b"), ("tts", "qwen3-tts-1.7b")])
        self.assertEqual(self.geschrieben[-1], dict(roh, tts={"voicedesign_enabled": True}, music={}),
                         "exactly the old values; a value that was not set is gone again")
        self.assertFalse(mischbetrieb.ist_an())
        self.assertEqual(mischbetrieb.aus(klein, self.kat, roh={}, schreib=self.schreib), [])

    def test_the_small_ones_can_be_the_main_model(self):
        # V01.1.528: the Base entry is only for own voices (rolle), so the switch was refused with "wahl" on tars
        for art, mid in mischbetrieb.KLEIN.items():
            m = self.kat[mid]
            self.assertEqual((m["art"], "rolle" in m, bool(m.get("wahl"))), (art, False, True), mid)

    def test_a_base_voice_stays_a_base_voice(self):
        # V01.1.529: tars speaks with own voices on 1.7B Base; the CustomVoice model does not know their names, so
        # every sentence and speaker file failed with „voice“. A Base main voice goes to the small Base one and back.
        base = self.cfg(tts="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
        wechsel = mischbetrieb.an(base, self.kat, roh={}, schreib=self.schreib, now=0)
        self.assertEqual(wechsel, [("asr", "qwen3-asr-0.6b"), ("tts", "qwen3-tts-0.6b-base")])
        self.assertEqual(modelle.wechsel_pruefen("tts", "qwen3-tts-0.6b-base", base, 120.0, self.kat)["id"],
                         "qwen3-tts-0.6b-base")
        # V01.1.528 had put tars on the CustomVoice one: „aus“ still brings the remembered Base one back
        falsch = self.cfg("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
        back = mischbetrieb.aus(falsch, self.kat, roh={}, schreib=self.schreib)
        self.assertIn(("tts", "qwen3-tts-1.7b-base"), back)
        self.assertEqual(modelle.wechsel_pruefen("tts", "qwen3-tts-1.7b-base", falsch, 120.0, self.kat)["id"],
                         "qwen3-tts-1.7b-base")
        os.unlink(self.datei)
        with self.assertRaises(modelle.Fehler) as e:   # not remembered: a CustomVoice one never becomes a Base one
            modelle.wechsel_pruefen("tts", "qwen3-tts-1.7b-base", falsch, 120.0, self.kat)
        self.assertEqual(e.exception.args[0], "wahl")

    def test_never_to_a_bigger_model(self):
        klein = self.cfg("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
        self.assertEqual(mischbetrieb.an(klein, self.kat, roh={}, schreib=self.schreib), [])

    def test_engine_roles_and_units(self):
        self.assertEqual(mischbetrieb.main(["sperrt", "llm"]), 1, "off: everything starts")
        mischbetrieb.an(self.cfg(), self.kat, roh={}, schreib=self.schreib)
        for rolle in mischbetrieb.GESPERRT:
            self.assertEqual(mischbetrieb.main(["sperrt", rolle]), 0, rolle)
        for rolle in ("main", "asr", "x; rm -rf /"):
            self.assertEqual(mischbetrieb.main(["sperrt", rolle]), 1, rolle)
        self.assertIn("speech-spark-llm-docker", mischbetrieb.EINHEITEN)
        self.assertNotIn("speech-spark-tts-engine", mischbetrieb.EINHEITEN)
        self.assertNotIn("speech-spark-asr-engine", mischbetrieb.EINHEITEN)


class PanelSendet(Ablage):
    """V01.1.528: the panel computer sends its speech settings every minute; VoiceDesign and the clone engine came
    back on tars while Mischbetrieb was on (3 TTS engines of 12.4 GiB). They stay off, the wish waits for „aus“."""

    def test_voicedesign_and_klon_stay_off_and_wait_for_aus(self):
        import common
        roh = {"tts": {"voicedesign_enabled": True}}
        mischbetrieb.an(self.cfg(), self.kat, roh=json.loads(json.dumps(roh)), schreib=self.schreib, now=0)
        neu = self.geschrieben[-1]
        daten = {"tts": {"voicedesign_enabled": True, "klon_enabled": True, "speed": 1.1}, "asr": {"language": "de"}}
        rest = mischbetrieb.einstellen_merken(json.loads(json.dumps(daten)))
        self.assertEqual(rest, {"tts": {"speed": 1.1}, "asr": {"language": "de"}}, "everything else goes on as before")
        self.assertEqual(mischbetrieb.stand()["vorher"]["tts"], {"voicedesign_enabled": True, "klon_enabled": True})
        cfg = json.loads(json.dumps(neu))
        cfg["tts"]["speed"] = 1.1
        sicht = mischbetrieb.sicht(cfg)
        self.assertEqual((sicht["tts"]["voicedesign_enabled"], sicht["tts"]["klon_enabled"]), (True, True))
        self.assertEqual((cfg["tts"]["voicedesign_enabled"], cfg["tts"]["klon_enabled"]), (False, False), "a copy")
        self.assertEqual(common.model_settings_hash(sicht)[:4], common.model_settings_hash(
            dict(cfg, tts=dict(cfg["tts"], voicedesign_enabled=True, klon_enabled=True)))[:4],
            "the panel's hash matches: it stops sending")
        mischbetrieb.aus(self.cfg(), self.kat, roh=json.loads(json.dumps(neu)), schreib=self.schreib)
        self.assertEqual((self.geschrieben[-1]["tts"]["voicedesign_enabled"], self.geschrieben[-1]["tts"]["klon_enabled"]),
                         (True, True), "„aus“ brings the panel's latest wish")
        self.assertEqual(mischbetrieb.einstellen_merken(daten), daten, "off: nothing held back")
        self.assertIs(mischbetrieb.sicht(cfg), cfg)

    def test_the_waerter_keeps_to_it(self):
        with open(os.path.join(APP, "tarswart.py"), encoding="utf-8") as f:
            s = f.read()
        body = s[s.index("def einstellen("):s.index("def logs(")]
        self.assertLess(body.index("mischbetrieb.einstellen_merken(daten)"), body.index("model_settings_take("))
        self.assertNotIn("model_settings_hash(cfg)", s)
        self.assertNotIn("model_settings_hash(load_config())", s)


class Wache(Ablage):
    """M3 Speicher-Wache: our engines give their memory back while the other project starts or memory runs short, and
    come back only after RUHIG_N calm looks; it only starts what it stopped itself."""

    def test_the_rule(self):
        laeuft = {"qwen38-sglang": {"state": "active", "seit": 5000, "da": True}}
        neu = {"qwen38-sglang": {"state": "active", "seit": 30, "da": True}}
        self.assertEqual(mischbetrieb.wache(40, laeuft, False, 0), (None, 0))
        self.assertEqual(mischbetrieb.wache(40, neu, False, 0)[0], "freigeben", "it starts: give the memory back")
        self.assertEqual(mischbetrieb.wache(40, {"x": {"state": "activating", "da": True}}, False, 0)[0], "freigeben")
        self.assertEqual(mischbetrieb.wache(mischbetrieb.FREI_MIN - 1, laeuft, False, 0)[0], "freigeben")
        self.assertEqual(mischbetrieb.wache(None, laeuft, False, 0), (None, 0), "unknown memory alone does nothing")
        self.assertEqual(mischbetrieb.wache(40, {"x": {"state": "inactive", "da": False}}, False, 0), (None, 0))
        ruhig = 0
        for _ in range(mischbetrieb.RUHIG_N - 1):
            aktion, ruhig = mischbetrieb.wache(mischbetrieb.ZURUECK_GIB, laeuft, True, ruhig)
            self.assertIsNone(aktion)
        self.assertEqual(mischbetrieb.wache(mischbetrieb.ZURUECK_GIB - 1, laeuft, True, ruhig), (None, 0), "calm anew")
        self.assertEqual(mischbetrieb.wache(None, laeuft, True, 99), (None, 0))
        self.assertEqual(mischbetrieb.wache(mischbetrieb.ZURUECK_GIB, laeuft, True, mischbetrieb.RUHIG_N - 1)[0], "zurueck")
        self.assertGreater(mischbetrieb.ZURUECK_GIB - 7, mischbetrieb.FREI_MIN, "loading ours never gives it back at once")

    def test_the_loop_stops_and_starts_only_ours(self):
        import threading
        mischbetrieb.an(self.cfg(), self.kat, roh={}, schreib=self.schreib)
        calls, stop = [], threading.Event()
        frei = iter([40, 3] + [40] * (mischbetrieb.RUHIG_N + 1))
        def sleep(_s):
            try:
                self.mem = next(frei)
            except StopIteration:
                stop.set()
        mischbetrieb.wache_lauf(lambda a, t: calls.append((a, t)) or {"ok": True},
                                lambda units: {u: {"state": "active", "seit": 9999, "da": True} for u in units},
                                lambda: self.mem, stop, sleep=sleep)
        self.assertEqual(calls, [("stop", "asr-engine"), ("stop", "tts-engine"), ("start", "asr-engine"),
                                 ("start", "tts-engine")])
        self.assertFalse(mischbetrieb.stimme_frei())
        mischbetrieb.aus(self.cfg(), self.kat, roh={}, schreib=self.schreib)
        calls.clear()
        stop.clear()
        frei = iter([3, 3])
        mischbetrieb.wache_lauf(lambda a, t: calls.append((a, t)) or {"ok": True}, lambda units: {}, lambda: self.mem,
                                stop, sleep=sleep)
        self.assertEqual(calls, [], "off: the guard never touches a unit")


class Sperren(Ablage):
    def setUp(self):
        super().setUp()
        mischbetrieb.an(self.cfg(), self.kat, roh={}, schreib=self.schreib)

    def test_no_switch_and_no_measurement(self):
        for art, mid in (("llm", "qwen36-35b-a3b-nvfp4-ohne-mtp"), ("asr", "qwen3-asr-1.7b")):
            with self.assertRaises(modelle.Fehler, msg=art) as e:
                modelle.wechsel_pruefen(art, mid, self.cfg(), 120, self.kat)
            self.assertEqual(str(e.exception), "mischbetrieb")
        with self.assertRaises(modelle.Fehler) as e:
            modelle.messliste(["llm"], self.kat)
        self.assertEqual(str(e.exception), "mischbetrieb")
        import modellseite
        self.assertIn("mischbetrieb aus", modellseite.GRUND["mischbetrieb"])

    def test_the_shell_keeps_to_it(self):
        with open(os.path.join(APP, "engine.sh"), encoding="utf-8") as f:
            eng = f.read()
        self.assertIn('mischbetrieb.py" sperrt "$ROLE"', eng)
        self.assertLess(eng.index("mischbetrieb.py"), eng.index("LLM_ARGS=()"), "before any engine starts")
        with open(os.path.join(APP, "speech-spark.sh"), encoding="utf-8") as f:
            sh = f.read()
        self.assertIn("mischbetrieb.py sperrt llm; then echo \"modelle: messung abgelehnt mischbetrieb\"", sh)
        self.assertIn('[[ "$art" =~ ^(asr|tts)$ ]]', sh, "root runs only switches of Hören and Sprechen")
        r = subprocess.run(["bash", "-n", os.path.join(APP, "speech-spark.sh")], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class Panel(unittest.TestCase):
    """The panel computer: the language model off on purpose, no outage, a fixed sentence or the foreign service."""

    def setUp(self):
        for name, wert in (("mischbetrieb", lambda now=None: True), ("weg", lambda now=None: False)):
            p = mock.patch.object(steuer, name, wert)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(llm, "fremd", lambda ccfg: None)
        p.start()
        self.addCleanup(p.stop)

    def test_fixed_sentence_and_no_outage(self):
        self.assertTrue(wartung.paused("llm"))
        self.assertFalse(wartung.paused("asr"), "Hören goes on")
        self.assertFalse(wartung.paused("tts"), "Sprechen goes on")
        self.assertTrue(wartung.quiet("llm"))
        self.assertEqual(wartung.sentence(), wartung.MISCHBETRIEB[0])
        self.assertEqual(wartung.sentence(True), wartung.MISCHBETRIEB[1])

    def test_while_the_guard_gave_the_voice_away(self):
        import notbetrieb
        with mock.patch.object(steuer, "stimme_frei", lambda now=None: True):
            with mock.patch.object(notbetrieb, "hoert", lambda cfg=None, now=None: True):
                self.assertFalse(wartung.paused("asr"), "Parakeet on the panel computer hears")
            with mock.patch.object(notbetrieb, "hoert", lambda cfg=None, now=None: False):
                self.assertTrue(wartung.paused("asr"))
            self.assertTrue(wartung.paused("tts"))
            self.assertTrue(wartung.quiet("asr") and wartung.quiet("tts"), "no outage alarm")
        with mock.patch.object(steuer, "remote", lambda cfg=None: True), \
                mock.patch.object(steuer, "weg", lambda now=None: False), \
                mock.patch.object(steuer, "stimme_frei", lambda now=None: True), \
                mock.patch.object(notbetrieb, "admin_on", lambda c: True):
            self.assertTrue(notbetrieb.hoert({"chat": {}}))

    def test_a_foreign_service_answers_instead(self):
        with mock.patch.object(llm, "fremd", lambda ccfg: {"id": "f1"}):
            self.assertFalse(wartung.paused("llm"))

    def test_mail_sorting_asks_the_foreign_model(self):
        """tidy._ask never asks the own model's list while a foreign service answers (V01.1.529: Connection refused)."""
        import httpx
        import tidy
        seen = []

        def antwort(req):
            seen.append((req.method, str(req.url), json.loads(req.content or b"null")))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        echt = httpx.Client
        x = {"url": "http://192.168.178.171:30001/v1", "modell": "alzeo-lane", "key": "k"}
        with mock.patch.object(llm, "fremd", lambda ccfg: x), \
                mock.patch.object(tidy.httpx, "Client", lambda **kw: echt(transport=httpx.MockTransport(antwort))), \
                mock.patch.object(tidy.vorrang, "hold", lambda *a, **kw: None), \
                mock.patch.object(tidy.verbrauch, "response", lambda *a, **kw: None), \
                mock.patch.object(tidy, "_model", {}):
            self.assertEqual(tidy._ask("s", "u", 10), "ok")
        self.assertEqual([(m, u) for m, u, _ in seen], [("POST", x["url"] + "/chat/completions")])
        self.assertEqual(seen[0][2]["model"], "alzeo-lane")

    def _tmp_state(self, mod, *names):
        tmp = tempfile.mkdtemp(prefix="misch-q-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for n in names:
            p = mock.patch.object(mod, n, os.path.join(tmp, n.lower() + ".json"))
            p.start()
            self.addCleanup(p.stop)

    def test_quality_test_waits_for_the_own_model(self):
        """Zustand → Prüfen → Qualitätstest asks only the own model, which is off: a clear sentence, no 0 / 39 in the
        history (V01.1.530); after an update it is not even shown."""
        import asyncio
        import quality
        self._tmp_state(quality, "RESULT", "HISTORY", "HELFER_RESULT")
        asked = []
        with mock.patch.object(llm, "model", lambda *a, **kw: asked.append(a)):
            self.assertIsNone(asyncio.run(quality.run("after update")).get("model"))
            self.assertIsNone(quality.last(), "after an update nothing is shown")
            res = asyncio.run(quality.run("manual"))
            self.assertEqual((res["error"], res["error_en"]), quality.MISCH)
            self.assertEqual(quality.last()["error"], quality.MISCH[0])
            self.assertEqual(quality.history(), [])
            h = asyncio.run(quality.helfer_run("manual"))
            self.assertEqual(h["error"], "mischbetrieb")
            self.assertEqual(h["verdict"]["de"], quality.HELFER_ERR["mischbetrieb"][0])
        self.assertEqual(asked, [], "the own model is never asked")

    def test_the_quality_test_checks_the_foreign_service(self):
        """„Fremden Dienst prüfen“ (V01.1.531, Dominik 2026-11-25 „3“): the same questions to the service that answers
        now, also in Mischbetrieb, shown with its name, never in the own model's history (Probetag)."""
        import asyncio
        import quality
        self._tmp_state(quality, "RESULT", "HISTORY")
        res = asyncio.run(quality.run("manual", "fremd"))
        self.assertEqual(res["error"], quality.FREMD_KEINER[0], "no service answers")
        x = {"id": "f1", "name": "Alzeo", "url": "http://192.168.178.171:30001/v1", "modell": "qwen3.8-27b", "key": "k"}
        seen = []

        async def fall(c, ccfg, headers, model, case):
            seen.append((ccfg.get("eigen"), model, llm.url(ccfg)))
            return {"answer": "", "raw": "", "held": [], "retried": False, "tools": [], "seconds": 0}

        async def kein_urteil(*a, **kw):
            return None

        zwei = quality.cases()[:2]
        with mock.patch.object(llm, "fremd", lambda ccfg: None if ccfg.get("eigen") else x), \
                mock.patch.object(quality, "_run_case", fall), mock.patch.object(quality, "judge", kein_urteil), \
                mock.patch.object(quality, "cases", lambda: zwei):
            res = asyncio.run(quality.run("manual", "fremd"))
        self.assertEqual((res.get("fremd"), res["model"], res["total"]), ("Alzeo", "qwen3.8-27b", 2), res.get("error"))
        self.assertEqual({s for s in seen}, {(None, "qwen3.8-27b", x["url"] + "/chat/completions")})
        self.assertEqual(quality.history(), [], "never compared with the own model's runs")

    def test_a_run_that_reached_no_model_is_no_result(self):
        import asyncio
        import httpx
        import quality
        self._tmp_state(quality, "RESULT", "HISTORY")

        async def name(*a, **kw):
            return "sprachmodell"   # an old name from the cache, as before V01.1.530

        async def weg(*a, **kw):
            raise httpx.ConnectError("refused")

        zwei = quality.cases()[:2]
        with mock.patch.object(steuer, "mischbetrieb", lambda now=None: False), \
                mock.patch.object(llm, "model", name), mock.patch.object(quality, "_run_case", weg), \
                mock.patch.object(quality, "cases", lambda: zwei):
            res = asyncio.run(quality.run("manual"))
        self.assertEqual(res["error"], "LLM nicht erreichbar: ConnectError")
        self.assertEqual(quality.history(), [], "no 0 / N in the history")

    def test_live_check_skips_the_language_model(self):
        import asyncio
        import httpx
        import health
        self._tmp_state(health, "LIVE_FILE")
        seen = []

        def antwort(req):
            seen.append(str(req.url))
            return httpx.Response(500, text="x")

        echt = httpx.AsyncClient
        with mock.patch.object(health.httpx, "AsyncClient", lambda **kw: echt(transport=httpx.MockTransport(antwort))):
            res = asyncio.run(health.livecheck("manual"))
        step = [x for x in res["steps"] if x["name"] == "llm"][0]
        self.assertEqual((step["ok"], step["detail"]), (None, "skipped: Mischbetrieb"))
        self.assertFalse([u for u in seen if u.endswith(("/chat/completions", "/models"))], seen)
        self.assertNotIn("tools", [x["name"] for x in res["steps"]])

    def test_systemone_is_not_asked(self):
        """The own LLM-Tor's /systemone (Weiche, Einordnung) is off too, also while a foreign service answers."""
        import systemone
        with mock.patch.object(llm, "fremd", lambda ccfg: {"id": "f1"}):
            with self.assertRaises(systemone.Unavailable) as e:
                systemone._prep({"llm_url": "http://127.0.0.1:31006/v1"}, next(iter(systemone.USES)), "x", [])
        self.assertEqual(e.exception.why, "Mischbetrieb")

    def test_ersatz_steps_in(self):
        tmp = tempfile.mkdtemp(prefix="misch-fremd-")
        self.addCleanup(shutil.rmtree, tmp, True)
        with mock.patch.object(fremdmodell, "DATEI", os.path.join(tmp, "f.json")):
            fid = fremdmodell.speichern("", "Alzeo", "http://192.168.178.171:30001/v1")
            fremdmodell.geprueft(fid, "qwen3.8-27b")
            fremdmodell.nutzung("", fid)
            with mock.patch.object(llm, "fremd", FREMD), mock.patch.object(steuer, "mischbetrieb", lambda now=None: True), \
                    mock.patch.object(steuer, "weg", lambda now=None: False), \
                    mock.patch.object(llm.netguard, "allowed", lambda ip, port, level: None):
                x = llm.fremd({"modelle_fremd": True})
                self.assertEqual((x or {}).get("id"), fid, "Ersatz while the own model is off in Mischbetrieb")
            with mock.patch.object(llm, "fremd", FREMD), mock.patch.object(steuer, "mischbetrieb", lambda now=None: False), \
                    mock.patch.object(steuer, "weg", lambda now=None: False):
                self.assertIsNone(llm.fremd({"modelle_fremd": True}))

    def test_live_says_it(self):
        with mock.patch.object(steuer, "remote", lambda cfg=None: True), \
                mock.patch.object(steuer, "cached", lambda max_age=60, now=None: {"mischbetrieb": True, "einheiten": {}}):
            self.assertTrue(steuer.for_live()["mischbetrieb"])
        with open(os.path.join(APP, "panel", "live.py"), encoding="utf-8") as f:
            self.assertIn("Mischbetrieb: nur Hören und Sprechen", f.read())


if __name__ == "__main__":
    unittest.main()
