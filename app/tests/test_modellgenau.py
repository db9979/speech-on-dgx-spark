"""Zustand → Überblick → Modell-Rechner genau (Dominik 2026-11-16 „Alles auf einmal umsetzen“): what the computer
with the models does right now. Numbers and fixed words only: the requests show kind, stage, seconds and tokens,
never what was asked or answered; the model computer's look is data (unknown keys, words and numbers out of range are
dropped); the events follow fixed rules with one log line each; the page works the same with the models apart and on
one Spark (Dominik 2026-11-16: „auch im Standalone-Betrieb“). No test depends on the time of day: every time is given."""
import asyncio
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests import helpers

helpers.start()
import common  # noqa: E402
import modellblick  # noqa: E402
import modellgenau  # noqa: E402
import panel  # noqa: E402
import steuer  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_tracelog import ADMIN  # noqa: E402
from tests.test_ui_browser import browser_ok  # noqa: E402

SECRET = "GEHEIMNIS-im-Prompt-4711"

METRIK = """# HELP vllm:num_requests_running running
vllm:num_requests_running{{model_name="m"}} {laufen}
vllm:num_requests_waiting{{model_name="m"}} 1.0
vllm:kv_cache_usage_perc{{model_name="m"}} {kv}
vllm:prefix_cache_hits_total{{model_name="m"}} {treffer}
vllm:prefix_cache_queries_total{{model_name="m"}} {fragen}
vllm:spec_decode_num_accepted_tokens_total{{model_name="m"}} {an}
vllm:spec_decode_num_draft_tokens_total{{model_name="m"}} {entwurf}
vllm:spec_decode_num_drafts_total{{model_name="m"}} {schritte}
vllm:generation_tokens_total{{model_name="m"}} {raus}
vllm:prompt_tokens_total{{model_name="m"}} {rein}
vllm:num_preemptions_total{{model_name="m"}} {verdraengt}
vllm:time_to_first_token_seconds_bucket{{le="0.25",model_name="m"}} {t1}
vllm:time_to_first_token_seconds_bucket{{le="1.0",model_name="m"}} {t2}
vllm:time_to_first_token_seconds_bucket{{le="+Inf",model_name="m"}} {t2}
vllm:cache_config_info{{block_size="16",num_gpu_blocks="8192"}} 1.0
"""


def metrik(laufen=3, kv=0.41, treffer=900, fragen=1000, an=740, entwurf=1000, schritte=400, raus=10000, rein=50000,
           verdraengt=0, t1=8, t2=10):
    return METRIK.format(**locals())


def look(zustand="geladen", voll=0, kanarie="ready", wartet_s=0.8, kv=41.0, raus=10000, verdraengt=0, drossel=None,
         treffer=900, fragen=1000, engine=3, nvrm=None, fertig=(), bremse=None):
    """A look as the Wärter sends it in its status (modellblick.messen)."""
    v = modellblick.metriken(metrik(laufen=engine, kv=kv / 100, raus=raus, verdraengt=verdraengt, treffer=treffer, fragen=fragen))
    return {"v": 1, "dienste": {"llm": {"zustand": zustand, "plaetze": 8, "laufen": 3, "warten": 1, "voll": voll,
                                        "anfragen": 48, "fehler": 0},
                                "asr": {"zustand": "geladen", "plaetze": 4, "laufen": 1, "warten": 0, "anfragen": 31},
                                "sehen": {"zustand": "entladen"}},
            "anfragen": [{"d": "llm", "z": "laeuft", "stufe": 2, "art": "gespraech", "s": 1.4, "folge": False, "rein": 3812, "raus": 96},
                         {"d": "llm", "z": "wartet", "stufe": 0, "art": "entwickler", "s": wartet_s, "folge": False, "rein": None, "raus": None},
                         {"d": "asr", "z": "laeuft", "stufe": 2, "art": "hoeren", "s": 0.6, "folge": False, "rein": None, "raus": None}],
            "vllm": {"llm": v}, "kanarie": {"status": kanarie, "ms": 38},
            "gpu": {"drossel": drossel if drossel is not None else ["taktgrenze"], "pstate": "P0", "takt_max": 3003, "takt_speicher": 4266},
            "speicher": {"llm": 62.0, "asr": 8.1, "tts-engine": 14.0}, "nvrm": nvrm, "fertig": list(fertig), "bremse": bremse,
            "mem": {"frei": 40.2, "gesamt": 119.7}}


def leer():
    with modellgenau._lock:
        modellgenau._stand.update(letzt=None, t=None, raten={}, geladen=True, gesichert=0.0, zustand={}, episode=set(),
                                  kanarie=None, voll={}, verdraengt=None, tag=None, woche=None, ohne=0, nvrm=None,
                                  bremse=False)
        modellgenau._stand["fenster"].clear()
        for q in (modellgenau._kurz, modellgenau._tag, modellgenau._woche, modellgenau._ereignisse):
            q.clear()


class Fern(unittest.TestCase):
    """The models on another computer: the look comes with the Wärter's status."""

    def setUp(self):
        leer()
        self.status = {"einheiten": {}, "betrieb": look()}
        self.p = [mock.patch.object(steuer, "remote", return_value=True),
                  mock.patch.object(steuer, "cached", side_effect=lambda **kw: self.status),
                  mock.patch.object(modellgenau, "sichern")]
        for p in self.p:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.p])
        self.addCleanup(leer)

    def runde(self, now, mono, **kw):
        self.status = {"einheiten": {}, "betrieb": look(**kw)}
        with redirect_stdout(io.StringIO()) as out:
            self.assertTrue(modellgenau.probe({"util": 78, "power": 61, "temp": 64, "clock": 2400}, {}, now=now, mono=mono))
        return out.getvalue()

    def test_rates_from_two_looks(self):
        self.runde(1_800_000_000, 1000.0)
        self.runde(1_800_000_003, 1003.0, raus=10600, treffer=1800, fragen=2000)
        a = modellgenau.ansicht("20m", {})
        llm = a["innen"]
        self.assertEqual(set(a["innen"]) >= {"modell", "kontext", "kanarie"}, True)   # only the chat model, with its name
        self.assertEqual(llm["raus_s"], 200.0)                 # 600 tokens in 3 s
        self.assertEqual(llm["prefix_pct"], 90.0)              # (1800-900)/(2000-1000) over the window
        self.assertEqual(a["jetzt"]["laufen"], 4)
        self.assertEqual(a["jetzt"]["warten"], 1)
        self.assertEqual(a["jetzt"]["tok_s"], 200.0)
        self.assertEqual(len(a["kurve"]), 2)
        self.assertEqual(a["gpu"]["drossel_namen"], [["Taktgrenze", "clock cap"]])

    def test_a_cached_look_again_keeps_the_rate(self):
        """Dominik 2026-11-16 (Verlauf mit Zacken): the Wärter's status is cached, so the sampler may get the same look
        twice; that is no zero between two rates, and the rate uses the time between the measurements themselves."""
        self.status = {"betrieb": dict(look(raus=10000), uhr=500.0)}
        with redirect_stdout(io.StringIO()):
            modellgenau.probe(None, {}, now=1_800_000_000, mono=1000.0)
            self.status = {"betrieb": dict(look(raus=10600), uhr=503.0)}
            modellgenau.probe(None, {}, now=1_800_000_004, mono=1004.5)     # the panel's own clock: 4.5 s
            modellgenau.probe(None, {}, now=1_800_000_007, mono=1007.5)     # the very same look again
        k = modellgenau.ansicht("20m", {})["kurve"]
        self.assertEqual([p["tok"] for p in k], [None, 200.0, 200.0])      # 600 tokens in the computer's 3 s

    def test_hangs_orphans_and_refused_memory(self):
        """alzeo ideas (Dominik 2026-11-16 „alles“): hängt, requests nobody waits for, the driver refusing memory."""
        out = self.runde(1_800_000_000, 1000.0, nvrm={"h1": 0, "h24": 2})
        out += self.runde(1_800_000_003, 1003.0, zustand="haengt", engine=5, nvrm={"h1": 1, "h24": 3})
        out += self.runde(1_800_000_006, 1006.0, zustand="haengt", engine=5, nvrm={"h1": 1, "h24": 3})
        self.assertNotIn("ohne_auftrag", out)
        out += self.runde(1_800_000_009, 1009.0, zustand="haengt", engine=5, nvrm={"h1": 1, "h24": 3})
        out += self.runde(1_800_000_012, 1012.0, zustand="haengt", engine=5, nvrm={"h1": 1, "h24": 3})
        self.assertEqual(out.count("rechner: ereignis ohne_auftrag llm"), 1)     # once per episode
        self.assertEqual(out.count("rechner: ereignis haengt llm"), 1)
        self.assertEqual(out.count("rechner: ereignis gpu_speicher - 1"), 1)
        a = modellgenau.ansicht("20m", {})
        self.assertEqual([h["id"] for h in a["hinweise"] if h["id"] in ("haengt", "ohne_auftrag", "gpu_speicher")],
                         ["haengt", "ohne_auftrag", "gpu_speicher"])
        self.assertEqual(a["dienste"][0]["zustand_name"], "hängt")
        self.assertEqual(a["gpu"]["nvrm"], {"h1": 1, "h24": 3})
        self.runde(1_800_000_015, 1015.0, engine=3)
        self.assertNotIn("ohne_auftrag", [h["id"] for h in modellgenau.ansicht("20m", {})["hinweise"]])

    def test_emergency_brake_shows(self):
        out = self.runde(1_800_000_000, 1000.0, bremse={"an": False, "n": 0})
        out += self.runde(1_800_000_003, 1003.0, bremse={"an": True, "n": 1})
        out += self.runde(1_800_000_006, 1006.0, bremse={"an": True, "n": 2})
        self.assertEqual(out.count("rechner: ereignis bremse llm"), 1)
        a = modellgenau.ansicht("20m", {})
        self.assertIn("bremse", [h["id"] for h in a["hinweise"]])
        self.assertEqual(a["innen"]["bremse"], {"an": True, "n": 2})
        self.assertIsNone(modellgenau.pruefen({"bremse": {"an": "ja", "n": 1}})["bremse"])

    def test_finished_requests_with_result_and_client(self):
        ok = {"t": 1_800_000_000, "art": "programm", "stufe": 1, "s": 4.2, "rein": 900, "raus": 120, "kunde": "Open WebUI",
              "ergebnis": "abgebrochen"}
        bad = [dict(ok, ergebnis=SECRET), dict(ok, kunde=SECRET + "/<b>"), dict(ok, art=SECRET), "x", dict(ok, t=True)]
        self.runde(1_800_000_000, 1000.0, fertig=[ok, *bad])
        f = modellgenau.ansicht("20m", {})["fertig"]
        self.assertNotIn(SECRET, json.dumps(f, ensure_ascii=False))
        self.assertEqual([(x["ergebnis_name"], x["kunde"], x["art_name"]) for x in f],
                         [("abgebrochen", "Open WebUI", "Anfrage"), ("abgebrochen", "", "Programm"),
                          ("abgebrochen", "Open WebUI", "Programm")])

    def test_requests_without_content(self):
        self.status = {"betrieb": dict(look(), anfragen=[{"d": "llm", "z": "laeuft", "stufe": 1, "art": SECRET, "s": 2,
                                                          "text": SECRET, "prompt": SECRET, "rein": 10, "raus": 20}])}
        with redirect_stdout(io.StringIO()):
            modellgenau.probe(None, {}, now=1_800_000_000, mono=1.0)
        a = modellgenau.ansicht("20m", {})
        self.assertNotIn(SECRET, json.dumps(a, ensure_ascii=False))
        self.assertEqual(a["anfragen"][0]["art_name"], "Anfrage")   # an unknown kind is only „Anfrage“
        self.assertEqual(a["anfragen"][0]["tok_s"], 10.0)

    def test_data_from_outside_is_checked(self):
        b = look()
        b["dienste"]["../etc"] = {"zustand": "geladen"}
        b["dienste"]["llm"]["plaetze"] = -3
        b["dienste"]["asr"]["zustand"] = SECRET
        b["gpu"] = {"drossel": ["waerme", SECRET], "pstate": SECRET}
        b["speicher"] = {"llm": 1e9, "/root": 3.0, "asr": 2.0}
        b["vllm"]["llm"]["kv"] = 500
        m = modellgenau.pruefen(b)
        self.assertNotIn("../etc", m["dienste"])
        self.assertNotIn("asr", m["dienste"])
        self.assertIsNone(m["dienste"]["llm"]["plaetze"])
        self.assertEqual(m["gpu"]["drossel"], ["waerme"])
        self.assertEqual(m["gpu"]["pstate"], "")
        self.assertEqual(m["speicher"], {"asr": 2.0})
        self.assertIsNone(m["vllm"]["llm"]["kv"])
        self.assertIsNone(modellgenau.pruefen("x"))

    def test_events_follow_fixed_rules_with_a_log_line(self):
        self.runde(1_800_000_000, 1000.0)
        out = self.runde(1_800_000_003, 1003.0, zustand="laedt", voll=2, kanarie="error", wartet_s=7.0, kv=95.0,
                         verdraengt=3, drossel=["waerme"])
        for zeile in ("rechner: ereignis laedt llm", "rechner: ereignis warteschlange_voll llm 2",
                      "rechner: ereignis kanarie_fehler llm", "rechner: ereignis wartet_lang llm",
                      "rechner: ereignis kv_voll llm", "rechner: ereignis verdraengt llm 3", "rechner: ereignis drosselt waerme"):
            self.assertIn(zeile, out)
        # the same state again: no new events (an episode is one event)
        self.assertEqual(self.runde(1_800_000_006, 1006.0, zustand="laedt", voll=2, kanarie="error", wartet_s=9.0, kv=96.0,
                                    verdraengt=3, drossel=["waerme"]), "")
        a = modellgenau.ansicht("20m", {})
        self.assertEqual({h["id"] for h in a["hinweise"]}, {"kv_voll", "wartet_lang", "drosselt", "kanarie"})
        e = a["ereignisse"][0]                                  # the newest first, with its names
        self.assertEqual(e["name"], list(modellgenau.EREIGNIS_NAMEN[e["w"]]))
        out = self.runde(1_800_000_009, 1009.0)
        self.assertIn("rechner: ereignis geladen llm", out)
        self.assertIn("rechner: ereignis kanarie_ok llm", out)

    def test_long_curves_and_saved_file(self):
        t0 = 1_800_000_000 - 1_800_000_000 % 900
        for i in range(25):                                   # 75 s: one full minute, then the next begins
            self.runde(t0 + 3 * i, 1000.0 + 3 * i)
        self.assertEqual(len(modellgenau._tag), 1)
        self.assertEqual(modellgenau._tag[0]["t"], t0)
        self.assertEqual(modellgenau._tag[0]["laufen"], 4)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(modellgenau, "DATEI", os.path.join(d, "g.json")):
            self.p[2].stop()
            modellgenau.sichern()
            self.p[2].start()
            with open(modellgenau.DATEI) as f:
                gespeichert = json.load(f)
            self.assertEqual(set(gespeichert), {"tag", "woche", "ereignisse"})
            gespeichert["ereignisse"].append({"t": 5, "w": SECRET, "d": "llm"})
            gespeichert["tag"].append({"t": 6, "tok": SECRET})
            with open(modellgenau.DATEI, "w") as f:
                json.dump(gespeichert, f)
            leer()
            modellgenau._laden()
            self.assertEqual(len(modellgenau._tag), 2)
            self.assertIsNone(modellgenau._tag[-1]["tok"])
            self.assertNotIn(SECRET, json.dumps(list(modellgenau._ereignisse)))

    def test_silent_model_computer(self):
        self.status = None
        self.assertFalse(modellgenau.probe(None, {}, now=1_800_000_000, mono=1.0))
        self.assertEqual(modellgenau.ansicht("20m", {}), {"da": False, "remote": True})

    def test_live_numbers(self):
        """Live and the Steuerzentrale carry the numbers too (Richtlinie Teil 5), never more than numbers."""
        import live
        import schirm
        import steuerzentrale
        self.assertEqual(modellgenau.fuer_live(), {})
        self.assertEqual(live._genau("qwen"), "")
        self.runde(1_800_000_000, 1000.0)
        self.runde(1_800_000_003, 1003.0, raus=10600)
        self.assertEqual(modellgenau.fuer_live()["laufen"], 4)
        self.assertEqual(modellgenau.fuer_live(True)["laufen"], 3)
        self.assertEqual(live._genau("qwen"), " · 3 laufen, 1 warten · 200 tok/s")
        self.assertEqual(live._genau("modell"), " · 4 laufen, 1 warten · 200 tok/s")
        self.assertEqual(schirm.zustand(1_800_000_003)["genau"]["tok_s"], 200.0)
        d = {"live": {}, "genau": modellgenau.fuer_live(True)}
        R = steuerzentrale.Raster(200, 45)
        steuerzentrale.stufen_zeichnen(R, d, [("spark", 30, 160, 5, 38)],
                                       [], tuple((k, n, t, "spark") for k, n, t, _ in steuerzentrale.STUFEN))
        self.assertIn("3 laufen · 200 tok/s", R.text())


class Allein(unittest.TestCase):
    """One Spark without a Pi (Dominik 2026-11-16): the panel looks itself, with the same module as the Wärter."""

    def setUp(self):
        leer()
        self.addCleanup(leer)

    def test_standalone_looks_itself(self):
        with mock.patch.object(steuer, "remote", return_value=False), \
                mock.patch.object(modellblick, "messen", return_value=look()) as m, mock.patch.object(modellgenau, "sichern"):
            self.assertTrue(modellgenau.probe({"util": 5}, {}, now=1_800_000_000, mono=1.0))
        self.assertEqual(m.call_args[0][0], None)       # its own unit states
        self.assertEqual(m.call_args[0][2], {"util": 5})
        a = modellgenau.ansicht("20m", {})
        self.assertTrue(a["da"])
        self.assertFalse(a["remote"])

    def test_memory_comes_with_the_look(self):
        """The unified memory is the model computer's own, measured with the look (never the Pi's)."""
        b = modellblick._mem()
        self.assertGreater(b["gesamt"], 0)
        with mock.patch.object(steuer, "remote", return_value=False), \
                mock.patch.object(modellblick, "messen", return_value=dict(look(), mem={"frei": 40.5, "gesamt": 119.7})), \
                mock.patch.object(modellgenau, "sichern"):
            modellgenau.probe(None, {}, now=1_800_000_000, mono=1.0)
        self.assertEqual(modellgenau.ansicht("20m", {})["mem"], {"frei": 40.5, "gesamt": 119.7})
        self.assertEqual(modellgenau.pruefen({"mem": {"frei": True, "gesamt": 1e9}})["mem"], {"frei": None, "gesamt": None})


class Sammeln(unittest.TestCase):
    """modellblick on the computer with the models: counters from vLLM, states, only local services."""

    def test_metrics(self):
        m = modellblick.metriken(metrik())
        self.assertEqual((m["laufen"], m["warten"], m["kv"]), (3.0, 1.0, 41.0))
        self.assertEqual(m["kv_tokens"], 8192 * 16)
        self.assertEqual(m["ttft"], [[0.25, 8.0], [1.0, 10.0], [1e9, 10.0]])
        self.assertIsNone(modellblick.metriken("garbage\n")["laufen"])

    def test_quantile(self):
        self.assertEqual(modellgenau._quantil([[0.25, 0], [1.0, 0], [1e9, 0]], [[0.25, 8], [1.0, 10], [1e9, 10]], 0.5), 0.25)
        self.assertEqual(modellgenau._quantil(None, [[0.25, 8], [1.0, 10], [1e9, 10]], 0.95), 1.0)
        self.assertIsNone(modellgenau._quantil(None, [[0.25, 0], [1e9, 0]], 0.5))

    def test_states(self):
        z = modellblick._zustand
        self.assertEqual(z({"state": "active"}, True, False), "geladen")
        self.assertEqual(z({"state": "active"}, False, False), "laedt")
        self.assertEqual(z({"state": "inactive"}, False, True), "entladen")
        self.assertEqual(z({"state": "inactive"}, False, False), "aus")
        self.assertEqual(z({"state": "failed"}, False, False), "fehler")
        self.assertEqual(z({"state": "inactive", "da": False}, False, True), "fehlt")
        self.assertEqual(z({"state": "active"}, False, True, "starting"), "laedt")

    def test_throttle_words(self):
        lauf = lambda cmd: (0, "0x0000000000000024, P0, 3003, 4266\n")   # noqa: E731
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
            modellblick._gpu_feld.clear()
            g = modellblick.gpu_mehr(lauf)
        self.assertEqual(g, {"drossel": ["leistungsgrenze", "waerme"], "pstate": "P0", "takt_max": 3003.0, "takt_speicher": 4266.0})

    def test_only_local_services_and_running_engines(self):
        asked = []

        class C:
            def get(self, url, timeout=None, headers=None):
                asked.append(url)
                r = mock.Mock(status_code=200)
                r.text = metrik() if url.endswith("/metrics") else json.dumps({"status": "ready", "requests": 4, "queue":
                                                                                    {"slots": 4, "running": 1, "waiting": 0}})
                return r
        cfg = {"llm": {"engine_port": 31016, "port": 31006, "sehen_port": 31017, "helfer_port": 31018},
               "asr": {"engine_port": 31011, "port": 31001}, "tts": {"engine_port": 31012, "port": 31002},
               "image": {"enabled": False, "port": 31005}, "music": {"enabled": False, "port": 31004}, "api": {"key": "k"}}
        units = {"speech-spark-llm": {"state": "active"}, "speech-spark-asr-engine": {"state": "active"},
                 "speech-spark-sehen": {"state": "inactive"}}
        out = modellblick.messen(units, cfg, None, client=C())
        self.assertTrue(all(u.startswith("http://127.0.0.1:") for u in asked))
        self.assertNotIn("http://127.0.0.1:31017/health", asked)       # the image engine does not run
        self.assertEqual(out["dienste"]["sehen"]["zustand"], "entladen")
        self.assertEqual(out["dienste"]["llm"]["zustand"], "geladen")
        self.assertEqual(out["vllm"]["llm"]["laufen"], 3.0)
        self.assertNotIn("bild", out["dienste"])                        # pictures off: not shown


class Tor(unittest.TestCase):
    """The gates name their requests with fixed words; the LLM-Tor counts a stream's tokens without passing on more
    than the client asked for."""

    def test_gate_rows(self):
        g = common.PrioGate(1, clock=lambda: 10.0)

        async def zwei():
            t = await g.enter(common.STAGE_HIGH, art="gespraech")
            t["raus"] = 12
            w = asyncio.ensure_future(g.enter(common.STAGE_LOW, art=SECRET))
            await asyncio.sleep(0)
            rows = g.bild()
            g.leave(t)
            await w
            return rows
        rows = asyncio.run(zwei())
        self.assertEqual([(r["z"], r["stufe"], r["art"], r["raus"]) for r in rows],
                         [("laeuft", 2, "gespraech", 12), ("wartet", 0, "", None)])
        self.assertEqual(g.tickets.keys(), g.running.keys())

    def test_stream_usage_only_as_asked(self):
        import llm_tor
        stueck = 'data: {"id":"x","choices":[{"delta":{"content":"Hallo"}}],"usage":{"prompt_tokens":40,"completion_tokens":5}}'
        schluss = 'data: {"id":"x","choices":[],"usage":{"prompt_tokens":40,"completion_tokens":6}}'
        t = {}
        line, s = llm_tor._stueck(stueck, t, (False, False))
        self.assertNotIn("usage", line)
        self.assertIn("Hallo", line)
        self.assertEqual(t, {"rein": 40, "raus": 5})
        self.assertEqual(llm_tor._stueck(schluss, t, (False, False))[0], None)
        self.assertEqual(llm_tor._stueck(schluss, t, (False, False))[1]["usage"]["completion_tokens"], 6)
        self.assertEqual(json.loads(llm_tor._stueck(stueck, {}, (True, False))[0][6:])["usage"], None)
        self.assertEqual(llm_tor._stueck(stueck, {}, (True, True))[0], stueck)
        self.assertEqual(llm_tor._stueck(schluss, {}, (True, False))[0], schluss)
        self.assertEqual(llm_tor._stueck("data: [DONE]", {}, (False, False)), ("data: [DONE]", None))


class Ende(unittest.TestCase):
    """The LLM-Tor: each finished request with its result, a hanging engine, the kernel log's memory refusals."""

    def setUp(self):
        import llm_tor
        self.t = llm_tor
        llm_tor.fertig.clear()
        self.addCleanup(llm_tor.fertig.clear)
        llm_tor.haengt.update(an=False, zaehler=None, t=0.0)
        self.addCleanup(llm_tor.haengt.update, an=False, zaehler=None, t=0.0)

    def test_result_and_client_name(self):
        g = common.PrioGate(2)

        async def eine():
            return await g.enter(common.STAGE_NORMAL, art="programm", kunde="Open WebUI")
        ticket = asyncio.run(eine())
        self.assertEqual(g.bild()[0]["kunde"], "Open WebUI")
        self.t._tokens(ticket, {"prompt_tokens": 30, "completion_tokens": True})
        with redirect_stdout(io.StringIO()) as out:
            self.t._ende(ticket, 0.0, "abgebrochen")
            self.t._ende(ticket, 0.0, SECRET)
        self.assertEqual([x["ergebnis"] for x in self.t.fertig], ["abgebrochen", "fehler"])
        self.assertEqual((self.t.fertig[0]["rein"], self.t.fertig[0]["raus"], self.t.fertig[0]["kunde"]), (30, None, "Open WebUI"))
        self.assertEqual(out.getvalue(), "llmtor: abgebrochen vom geraet\n")
        self.assertEqual(modellblick.fertige(list(self.t.fertig))[0]["ergebnis"], "abgebrochen")

    def test_a_stream_the_client_leaves_is_cancelled(self):
        """The device goes away mid-answer: the engine's stream is closed (vLLM stops) and the result says so."""
        import httpx
        t = self.t
        closed = []

        class Strom(httpx.AsyncByteStream):
            async def __aiter__(self):
                for i in range(50):
                    yield f'data: {{"choices":[{{"delta":{{"content":"{i}"}}}}]}}\n\n'.encode()

            async def aclose(self):
                closed.append(1)
        engine = httpx.MockTransport(lambda req: httpx.Response(200, stream=Strom()))
        old = (t.client, t.gate)
        t.client, t.gate = httpx.AsyncClient(transport=engine), common.PrioGate(2)
        self.addCleanup(lambda: setattr(t, "client", old[0]) or setattr(t, "gate", old[1]))

        class Anfrage:
            class state:
                pass
            headers = {}

        async def los():
            with mock.patch.object(t, "stage_of", return_value=common.STAGE_NORMAL), \
                    mock.patch.object(t.mandanten, "halten", new=mock.AsyncMock()):
                resp = await t._forward(1, {"stream": True, "messages": []}, Anfrage())
            it = resp.body_iterator
            await it.__anext__()
            await it.aclose()
        with redirect_stdout(io.StringIO()):
            asyncio.run(los())
        self.assertEqual(closed, [1])
        self.assertEqual([x["ergebnis"] for x in t.fertig], ["abgebrochen"])
        self.assertEqual(t.gate.view()["running"], 0)

    def test_hangs_after_quiet_tokens(self):
        t = self.t
        gate = mock.Mock()
        gate.view.return_value = {"running": 1}
        zaehler = [500]
        with mock.patch.object(t, "gate", gate), mock.patch.object(t, "laufend", new=mock.AsyncMock(return_value=({}, "m", 1))), \
                mock.patch.object(t, "_zaehler", new=mock.AsyncMock(side_effect=lambda port: zaehler[0])), \
                redirect_stdout(io.StringIO()) as out:
            asyncio.run(t.haengt_runde(100.0))
            asyncio.run(t.haengt_runde(100.0 + t.HAENGT_S - 1))
            self.assertFalse(t.haengt["an"])
            asyncio.run(t.haengt_runde(100.0 + t.HAENGT_S))
            self.assertTrue(t.haengt["an"])
            zaehler[0] = 501
            asyncio.run(t.haengt_runde(300.0))
            self.assertFalse(t.haengt["an"])
        self.assertEqual(out.getvalue(), f"llmtor: haengt {t.HAENGT_S} s\nllmtor: haengt nicht mehr\n")

    def notbremse(self, an=True, gemeinsam=True, gib=6):
        cfg = {"memory": {"notbremse": an, "notbremse_gib": gib}}
        return [mock.patch.object(self.t, "load_config", return_value=cfg),
                mock.patch.object(self.t.hardware, "profil", return_value={"gemeinsam": gemeinsam})]

    def test_emergency_brake(self):
        """alzeo 4 (Dominik 2026-11-16 „alles“): below the limit no new request, the oldest stream is ended, one per
        round; it lets go BREMSE_LUFT_GIB above; never on a computer whose GPU has its own memory, never while off."""
        t = self.t
        self.addCleanup(t.bremse.update, an=False, n=0)
        g = common.PrioGate(4)

        async def drei():
            return [await g.enter(common.STAGE_NORMAL, art="gespraech") for _ in range(3)]
        a, b, c = asyncio.run(drei())
        a["strom"] = b["strom"] = True          # c answers without a stream: it cannot be ended in the middle
        with mock.patch.object(t, "gate", g), redirect_stdout(io.StringIO()) as out:
            for p in self.notbremse():
                p.start()
            try:
                t.bremse_runde(frei=9.0)
                self.assertFalse(t.bremse["an"])
                t.bremse_runde(frei=5.5)
                self.assertTrue(t.bremse["an"])
                self.assertEqual((a.get("bremse"), b.get("bremse")), (True, None))     # the oldest first
                t.bremse_runde(frei=5.5)
                self.assertTrue(b.get("bremse"))
                self.assertIsNone(c.get("bremse"))
                with self.assertRaises(t.HTTPException) as e:
                    asyncio.run(t._forward(1, {"messages": []}, mock.Mock()))
                self.assertEqual(e.exception.status_code, 503)
                t.bremse_runde(frei=7.0)                      # above the limit, not yet BREMSE_LUFT_GIB above
                self.assertTrue(t.bremse["an"])
                t.bremse_runde(frei=8.0)
                self.assertFalse(t.bremse["an"])
            finally:
                mock.patch.stopall()
        self.assertEqual(t.bremse["n"], 2)
        self.assertIn("llmtor: bremse an 5 GiB", out.getvalue())
        self.assertIn("llmtor: bremse abgelehnt", out.getvalue())
        for an, gemeinsam in ((False, True), (True, False)):            # off, or a DGX Station: nothing happens
            t.bremse.update(an=False)
            with mock.patch.object(t, "gate", g), redirect_stdout(io.StringIO()):
                for p in self.notbremse(an, gemeinsam):
                    p.start()
                try:
                    t.bremse_runde(frei=1.0)
                finally:
                    mock.patch.stopall()
            self.assertFalse(t.bremse["an"])
            self.assertIsNone(c.get("bremse"))

    def test_kernel_log_counts_only(self):
        modellblick._nvrm.update(t=None, wert=None)
        self.addCleanup(modellblick._nvrm.update, t=None, wert=None)
        log = ("1799999000.1 tars kernel: NVRM: nvAssertFailed " + SECRET + "\n"
               "1799990000.2 tars kernel: NVRM: GPU0 NV_ERR_NO_MEMORY " + SECRET + "\n"
               "1799999900.0 tars kernel: NVRM: Out of memory [NV_ERR_NO_MEMORY]\n"
               "1799999950.0 tars kernel: usb 1-1: out of memory\n")
        lauf = mock.Mock(return_value=(0, log))
        self.assertEqual(modellblick.nvrm(lauf, now=1_800_000_000), {"h1": 1, "h24": 2})
        self.assertEqual(modellblick.nvrm(lauf, now=1_800_000_030), {"h1": 1, "h24": 2})   # cached
        self.assertEqual(lauf.call_count, 1)
        self.assertIsNone(modellblick.nvrm(mock.Mock(return_value=(1, "no access")), now=1_800_001_000))


class Seite(unittest.TestCase):
    def test_admin_only_and_limited(self):
        self.assertEqual(TestClient(panel.app).get("/api/admin/modellgenau").status_code, 401)
        r = ADMIN.get("/api/admin/modellgenau?zeit=nonsense")
        self.assertEqual(r.status_code, 200)
        self.assertIn("da", r.json())
        import guard
        self.assertIn("modellgenau", guard.RATE)


def fake_view():
    """What the page gets: a full look of the model computer after a few rounds (numbers and fixed words)."""
    with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(modellgenau, "sichern"):
        leer()
        for i, (raus, kv) in enumerate(((10000, 41.0), (10600, 43.0), (11300, 47.0))):
            st = {"betrieb": look(raus=raus, kv=kv, treffer=900 + 300 * i, fragen=1000 + 330 * i,
                                  zustand="laedt" if i == 1 else "geladen", nvrm={"h1": 0, "h24": 1},
                                  fertig=[{"t": 1_799_999_990, "art": "gespraech", "stufe": 2, "s": 6.1, "rein": 4210, "raus": 388,
                                           "kunde": "", "ergebnis": "fertig"},
                                          {"t": 1_799_999_995, "art": "programm", "stufe": 1, "s": 2.4, "rein": 812, "raus": 40,
                                           "kunde": "Open WebUI", "ergebnis": "abgebrochen"}])}
            with mock.patch.object(steuer, "cached", return_value=st), redirect_stdout(io.StringIO()):
                modellgenau.probe({"name": "NVIDIA GB10", "util": 70 + i, "power": 58.0 + i, "temp": 63, "clock": 2400,
                                   "grenze": {"wort": "2400"}}, {}, now=1_800_000_000 + 3 * i, mono=1000.0 + 3 * i)
        v = modellgenau.ansicht("20m", {})
        leer()
    return v


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Seitenbild(unittest.TestCase):
    """The page at 320, 390 and 1280 px: no sideways scrolling, no error with the strict CSP, every part there, the
    bars sized through the CSSOM; it opens from „Technische Details“ and closes with „Überblick“."""

    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def test_page(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        view = json.dumps(fake_view())
        self.assertNotIn(SECRET, view)

        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 900), (390, 844), (320, 700)):
                    br, pg, errors = await b.page(p, w, h, csp=True)
                    await pg.route("**/api/admin/modellgenau*", lambda route, request=None: route.fulfill(
                        status=200, content_type="application/json", body=view))
                    await pg.evaluate("goSec('mon')")
                    await pg.evaluate("$('ztech').open=true")
                    await pg.click("#zmggo")
                    await b.until(pg, "!!document.querySelector('#zmgbody .mgtiles')")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#zmgbody .mgtile').length"), 6)
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#zmgbody .mgtab')[0].querySelectorAll('tbody tr').length"), 3)
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#zmgbody .mgtab')[1].querySelectorAll('tbody tr').length"), 3)
                    self.assertTrue(await pg.evaluate("[...document.querySelectorAll('#zmgbody [data-w]')].every(e=>e.style.width.endsWith('%'))"))
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#zmgcharts svg path').length"), 3)
                    await pg.evaluate("mgDraw();mgDraw()")              # drawn again with the same text: still one line each
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#zmgcharts svg path').length"), 3)
                    self.assertIn("tok/s", await pg.inner_text("#zmgcharts"))          # the value now and the scale beside
                    box = await pg.evaluate("(()=>{const s=document.querySelector('#zmgcharts svg');s.scrollIntoView({block:'center'});"
                                            "const r=s.getBoundingClientRect();"
                                            "return [r.left+r.width*0.99,r.top+r.height/2]})()")
                    await pg.mouse.move(*box)
                    self.assertIn("tok/s", await pg.inner_text("#zmgrd"))              # pointing shows the values
                    self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth"), 0, w)
                    if os.environ.get("MG_SHOT"):
                        await pg.screenshot(path=os.path.join(os.environ["MG_SHOT"], f"modellgenau-{w}.png"), full_page=True)
                    await pg.click("#zmgdet [data-mgz='24h']")
                    await pg.click("#zmgback")
                    self.assertTrue(await pg.evaluate("$('zmgdet').hidden"))
                    self.assertEqual(errors, [], w)
                    await br.close()
        asyncio.run(go())

    def test_console_tab(self):
        """The Spark-Konsole (Dominik 2026-11-16 „1+2“): the same page as its tab „Modell genau“ under the strict CSP,
        and the overview's line about the chat model jumps there."""
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        view = json.dumps(fake_view())
        status = json.dumps({"system": {"mem_total_gib": 121, "mem_avail_gib": 60, "cpu": 12}, "gpu": {"util": 70},
                             "services": {}, "alerts": [], "genau": {"laufen": 2, "warten": 1, "tok_s": 48.4, "kv": 47.0}})
        with open(os.path.join(os.path.dirname(modellgenau.__file__), "static", "konsole.html"), encoding="utf-8") as f:
            html = f.read()

        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 900), (390, 844)):
                    br, pg, errors = await b.page(p, w, h, csp=True)
                    base = f"http://127.0.0.1:{self.port}"
                    csp = (await pg.request.get(base + "/")).headers.get("content-security-policy", "")
                    self.assertIn("script-src", csp)
                    await pg.route("**/konsole-probe", lambda route, request=None: route.fulfill(
                        status=200, content_type="text/html", body=html, headers={"Content-Security-Policy": csp}))
                    await pg.route("**/api/admin/modellgenau*", lambda route, request=None: route.fulfill(
                        status=200, content_type="application/json", body=view))
                    await pg.route("**/api/status", lambda route, request=None: route.fulfill(
                        status=200, content_type="application/json", body=status))
                    await pg.goto(base + "/konsole-probe")
                    await b.until(pg, "!!document.querySelector('#tab-ueberblick .kgenau')")
                    self.assertIn("48 tok/s", await pg.inner_text("#tab-ueberblick .kgenau"))
                    await pg.click("#tab-ueberblick .kgenau a")
                    await b.until(pg, "!!document.querySelector('#zmgbody .mgtiles')")
                    self.assertFalse(await pg.evaluate("document.getElementById('tab-modellgenau').hidden"))
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#zmgbody .mgtile').length"), 6)
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#zmgcharts svg path').length"), 3)
                    self.assertTrue(await pg.evaluate("[...document.querySelectorAll('#zmgbody [data-w]')].every(e=>e.style.width.endsWith('%'))"))
                    self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth"), 0, w)
                    if os.environ.get("MG_SHOT"):
                        await pg.screenshot(path=os.path.join(os.environ["MG_SHOT"], f"konsole-modellgenau-{w}.png"), full_page=True)
                    await pg.click("#ktabs a[data-tab='logs']")
                    self.assertTrue(await pg.evaluate("document.getElementById('zmgdet').hidden"))   # leaving the tab stops the poll
                    self.assertEqual(errors, [], w)
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
