"""Wärter and Steuer (plan Raspberry-Pi split, stage B4a): with the models on another computer the panel starts,
stops and watches the model units and reads the GPU through the Wärter (tarswart.py). Only signed requests with a
fresh time and a new one-time number, only the fixed commands and only parts of common.UNITS get through; units of
the panel's own computer never go there, and on the all-in-one install nothing changes. systemctl is faked."""
import io
import json
import os
import secrets
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests import helpers

helpers.start()
import common  # noqa: E402
import steuer  # noqa: E402
import tarswart  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

KEY = secrets.token_bytes(32)
SHOW = ("Id=speech-spark-asr.service\nActiveState=active\nActiveEnterTimestampMonotonic={t}\n\n"
        "Id=speech-spark-tts.service\nActiveState=failed\nActiveEnterTimestampMonotonic=0\n")


def body(cmd="status", args=(), ts=None, nonce=None, daten=None):
    d = {"cmd": cmd, "args": list(args), "ts": int(time.time()) if ts is None else ts, "nonce": nonce or secrets.token_hex(16)}
    if daten is not None:
        d["daten"] = daten
    return json.dumps(d).encode()


class FakeRun:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, timeout=10, env=None):
        self.calls.append(cmd)
        if cmd[:2] == ["systemctl", "show"]:
            return 0, SHOW.format(t=int((time.monotonic() - 90) * 1e6))
        if cmd[:2] == ["systemctl", "is-active"]:
            return 3, "inactive"
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return 1, ""
        return 0, ""


class Base(unittest.TestCase):
    def setUp(self):
        self.key = os.path.join(helpers.TMP, "waerter.key")
        with open(self.key, "w") as f:
            f.write(KEY.hex())
        self.run = FakeRun()
        for target, value in ((tarswart, "run"), (tarswart, "gpu_stats")):
            p = mock.patch.object(target, value, self.run if value == "run" else (lambda: {"name": "GB10", "util": 7.0}))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(common, "WAERTER_KEY", self.key)
        p.start()
        self.addCleanup(p.stop)
        tarswart._seen.clear()
        tarswart._times.clear()
        self.app = TestClient(tarswart.app)

    def post(self, raw, key=KEY):
        return self.app.post("/v1/wart", content=raw, headers={"X-Wart": common.waerter_sign(key, raw)})


class Waerter(Base):
    def test_status_with_the_right_signature(self):
        r = self.post(body())
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["einheiten"]["speech-spark-asr"]["state"], "active")
        self.assertAlmostEqual(d["einheiten"]["speech-spark-asr"]["seit"], 90, delta=3)
        self.assertEqual(d["einheiten"]["speech-spark-tts"], {"state": "failed", "seit": None, "eintritt": 0})
        self.assertEqual(d["einheiten"]["speech-spark-llm"], {"state": "unknown", "seit": None, "eintritt": 0})
        self.assertEqual(d["gpu"]["name"], "GB10")
        self.assertEqual(len([c for c in self.run.calls if c[:2] == ["systemctl", "show"]]), 1, "one call for all")

    def test_refused_without_the_key_old_or_twice(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.post(body(), key=secrets.token_bytes(32)).status_code, 403)
            self.assertEqual(self.app.post("/v1/wart", content=body()).status_code, 403)
            self.assertEqual(self.post(body(ts=int(time.time()) - 300)).status_code, 403)
            raw = body()
            self.assertEqual(self.post(raw).status_code, 200)
            self.assertEqual(self.post(raw).status_code, 403, "the same request again")
            self.assertEqual(self.post(body(nonce="x" * 32)).status_code, 403)
        for word in ("unterschrift", "zeit", "nummer"):
            self.assertIn(f"waerter: abgelehnt {word}", out.getvalue())

    def test_only_fixed_commands_and_parts(self):
        out = io.StringIO()
        with redirect_stdout(out):
            for cmd, args in (("shell", ["ls"]), ("einheit", ["restart", "speech-spark-panel"]),
                              ("einheit", ["restart", "llm"]), ("einheit", ["kill", "asr"]),
                              ("einheit", ["restart", "asr; reboot"]), ("einheit", ["restart"])):
                self.assertEqual(self.post(body(cmd, args)).status_code, 400, (cmd, args))
        self.assertFalse([c for c in self.run.calls if "sudo" in c])
        r = self.post(body("einheit", ["restart", "tts-engine"]))
        self.assertEqual(r.json(), {"ok": True, "code": 0})
        self.assertIn(["sudo", "-n", "/usr/bin/systemctl", "restart", "speech-spark-tts-engine"], self.run.calls)

    def test_without_a_key_nothing(self):
        os.unlink(self.key)
        self.assertEqual(self.post(body()).status_code, 403)
        self.assertEqual(self.app.get("/health").json()["status"], "no key")

    def test_too_many(self):
        with redirect_stdout(io.StringIO()):
            codes = [self.post(body()).status_code for _ in range(tarswart.RATE[0] + 2)]
        self.assertEqual(codes[-1], 429)


class Settings(Base):
    """B4b: the panel's speech settings reach the model computer; its own addresses, ports and backends never move."""
    def setUp(self):
        super().setUp()
        self.old = common.load_config()
        self.addCleanup(helpers.write_config, self.old)

    def test_known_keys_are_taken(self):
        with redirect_stdout(io.StringIO()) as out:
            r = self.post(body("einstellen", daten={"tts": {"temperature": 0.4, "default_voice": "vivian"},
                                                    "asr": {"context": "Spark"}}))
        self.assertEqual(r.status_code, 200, r.text)
        c = common.load_config()
        self.assertEqual((c["tts"]["temperature"], c["tts"]["default_voice"], c["asr"]["context"]), (0.4, "vivian", "Spark"))
        self.assertEqual(r.json()["einstellungen"], common.model_settings_hash(c))
        self.assertEqual(c["tts"]["port"], self.old["tts"]["port"])
        self.assertIn("waerter: einstellen ok", out.getvalue())

    def test_never_addresses_ports_backends_or_foreign_models(self):
        for daten in ({"tts": {"port": 31999}}, {"asr": {"host": "0.0.0.0"}}, {"tts": {"backend": "x"}},
                      {"image": {"enabled": True}}, {"chat": {"llm_url": "http://x"}}, {"tts": {"temperature": "hot"}},
                      {"tts": {"model": "evil/Qwen3-TTS-x"}}, {"asr": {"neu": 1}}, {"tts": {"calm": 1}}, {"tts": []}):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(self.post(body("einstellen", daten=daten)).status_code, 400, daten)
        self.assertEqual(common.load_config(), self.old)
        self.assertEqual(self.post(body("einstellen")).status_code, 400, "einstellen without settings")

    def test_the_panel_hands_them_over_when_they_differ(self):
        steuer._client = self.app
        self.addCleanup(setattr, steuer, "_client", None)
        steuer._status.update(t=0.0, d=None, push=-steuer.PUSH)
        self.addCleanup(steuer._status.update, t=0.0, d=None, push=-steuer.PUSH)
        c = json.loads(json.dumps(self.old))
        c["models"]["host"] = "192.168.178.171"
        c["tts"]["temperature"] = 0.55
        with redirect_stdout(io.StringIO()) as out:
            steuer.status(c, now=1000.0)
            self.assertEqual(common.load_config()["tts"]["temperature"], 0.55)
            steuer.status(c, now=1010.0)                     # cached: nothing again
        self.assertEqual(out.getvalue().count("steuer: einstellen abgleich ok"), 1)

    def test_the_model_choice_goes_the_other_way(self):
        # B4c: which model runs is the model computer's; it reports it and the panel takes it over
        c = common.load_config()
        self.assertEqual(self.post(body()).json()["modellwahl"], common.model_choice(c))
        for sec, keys in common.MODEL_CHOICE.items():
            self.assertFalse(set(keys) & set(common.model_settings(c).get(sec, {})), sec)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.post(body("einstellen", daten={"asr": {"recognizer": "parakeet"}})).status_code, 400)
        panel = json.loads(json.dumps(c))
        panel["models"]["host"] = "192.168.178.171"
        got = common.model_choice(c)
        got["tts"]["model"] = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        got["llm"]["modell"] = "qwen3-30b-a3b"
        steuer._status["wahl"] = None
        self.addCleanup(steuer._status.update, wahl=None)
        with redirect_stdout(io.StringIO()) as out:
            self.assertTrue(steuer.modellwahl(panel, got))
            self.assertFalse(steuer.modellwahl(panel, got), "the same report once")
        now = common.load_config()
        self.assertEqual((now["tts"]["model"], now["llm"]["modell"]), ("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "qwen3-30b-a3b"))
        self.assertIn("steuer: modellwahl uebernommen 2", out.getvalue())

    def test_a_strange_model_choice_is_not_taken(self):
        c = common.load_config()
        for sec, k, v in (("tts", "model", "evil/Qwen3-TTS-x"), ("asr", "model", 5), ("llm", "enabled", "ja"),
                          ("llm", "modell", "../../etc"), ("tts", "port", 1), ("chat", "llm_url", "http://x")):
            got = common.model_choice(c)
            got.setdefault(sec, {})[k] = v
            with self.assertRaises(ValueError, msg=(sec, k)):
                common.model_choice_take(c, got, common.shipped())
            steuer._status["wahl"] = None
            with redirect_stdout(io.StringIO()) as out:
                self.assertFalse(steuer.modellwahl(c, got))
            self.assertIn("steuer: modellwahl abgelehnt", out.getvalue())
        steuer._status["wahl"] = None
        self.assertEqual(common.load_config(), self.old)

    def test_logs_of_a_model_unit(self):
        with mock.patch.object(tarswart, "journal", lambda unit, n, fmt: f"{unit} {n}\n"), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(self.post(body("logs", ["tts-engine", "50"])).json()["text"], "speech-spark-tts-engine 50\n")
            for args in (["panel", "5"], ["tts", "99999"], ["tts", "-1"], ["tts"]):
                self.assertEqual(self.post(body("logs", args)).status_code, 400, args)


class Modelle(Base):
    """B4c: Zustand → Modelle with the models on another computer: its numbers, its switch, its own models."""
    def setUp(self):
        super().setUp()
        import features
        import modellseite
        import modelle
        self.m, self.seite = modelle, modellseite
        steuer._client = self.app
        self.addCleanup(setattr, steuer, "_client", None)
        self.old = common.load_config()
        self.addCleanup(helpers.write_config, self.old)
        helpers.set_config(modelle_wechseln=True)
        self.addCleanup(helpers.set_config, modelle_wechseln=False)
        self.assertTrue(features.admin_on("modellwechsel", common.load_config()["chat"]))
        self.cfg = json.loads(json.dumps(common.load_config()))
        self.cfg["models"]["host"] = "192.168.178.171"
        p = mock.patch.object(modelle, "gesamt_gib", return_value=128.0)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: os.path.exists(modelle.WUNSCH) and os.remove(modelle.WUNSCH))

    def test_the_page_comes_from_the_model_computer(self):
        d = self.post(body("modelle")).json()
        self.assertEqual(set(d), {"gesamt_gib", "lanes", "messung", "wechsel", "eigene", "laeuft"})
        with mock.patch.object(self.seite, "_laeuft", side_effect=AssertionError("asked here")):
            page = self.seite.seite(cfg=self.cfg)
        self.assertTrue(page["wechsel"]["an"])
        self.assertFalse(page["wechsel"]["laeuft"])
        steuer._client = None
        with mock.patch.object(steuer, "call", return_value=None), self.assertRaises(Exception) as e:
            self.seite.seite(cfg=self.cfg)
        self.assertEqual(getattr(e.exception, "status_code", None), 503)

    def test_a_switch_runs_there_with_its_own_rules(self):
        out = io.StringIO()
        with redirect_stdout(out):
            for args in (["musik", "x"], ["asr", "x; reboot"], ["asr"]):
                self.assertEqual(self.post(body("wechseln", args)).status_code, 400, args)
            bad = self.post(body("wechseln", ["asr", "qwen3-forcedaligner-0.6b"])).json()
        self.assertEqual(bad["ok"], False)
        self.assertIn(bad["fehler"], self.seite.GRUND)
        self.assertFalse([c for c in self.run.calls if "sudo" in c])
        self.assertFalse(os.path.exists(self.m.WUNSCH))
        cur = self.m.jetzt_id("asr", common.load_config())
        target = "qwen3-asr-0.6b" if cur != "qwen3-asr-0.6b" else "qwen3-asr-1.7b"
        with redirect_stdout(out):
            good = self.post(body("wechseln", ["asr", target])).json()
        self.assertEqual(good["ok"], True, good)
        self.assertIn(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "speech-spark-wechsel"], self.run.calls)
        self.assertEqual(self.m.wunsch_nehmen(), ("asr", target))
        self.assertIn("waerter: wechseln asr ok", out.getvalue())

    def test_own_models_are_checked_there_again(self):
        with redirect_stdout(io.StringIO()) as out:
            bad = self.post(body("eigen_dazu", daten={"id": "eigen-x", "art": "llm"})).json()
            self.assertEqual(self.post(body("eigen_weg", ["eigen-gibtsnicht"])).json(), {"ok": False, "fehler": "unbekannt"})
            self.assertEqual(self.post(body("eigen_weg", ["../x"])).status_code, 400)
            self.assertEqual(self.post(body("eigen_dazu")).status_code, 400, "eigen_dazu without an entry")
        self.assertEqual(bad["ok"], False)
        self.assertIn(bad["fehler"], self.seite.GRUND)
        self.assertIn(f"waerter: eigen_dazu abgelehnt {bad['fehler']}", out.getvalue())
        self.assertEqual(self.m.eigene(), [])


class Pause(Base):
    """B4c: a Wartungspause on the model computer pauses the same parts in the panel; "Weiter" ends both; the Live view
    shows the model computer in counts. The panel never waits for it on a question (only its last status counts)."""
    def setUp(self):
        super().setUp()
        import wartung
        self.w = wartung
        self.old = common.load_config()
        self.addCleanup(helpers.write_config, self.old)
        c = json.loads(json.dumps(self.old))
        c["models"]["host"] = "192.168.178.171"
        c["chat"]["wartung"] = True
        helpers.write_config(c)
        steuer._client = self.app
        self.addCleanup(setattr, steuer, "_client", None)
        self.addCleanup(steuer._status.update, t=0.0, d=None)
        for f in (common.WARTUNG_FILE,):
            self.addCleanup(lambda f=f: os.path.exists(f) and os.remove(f))
        wartung._cache.update(key=None, state=None)
        self.addCleanup(wartung._cache.update, key=None, state=None)

    def there(self, pause, age=0.0):
        steuer._status.update(t=time.monotonic() - age, d={"einheiten": {}, "pause": pause})

    def test_the_waerter_reports_only_what_the_panel_needs(self):
        with open(common.WARTUNG_FILE, "w") as f:
            json.dump({"on": True, "parts": ["llm"], "since": 1.0, "until": 2.0, "by": "kommandozeile",
                       "channel": "kommandozeile"}, f)
        d = self.post(body()).json()
        self.assertEqual(set(d["pause"]), {"on", "parts", "since", "until", "channel"}, "never who")
        self.assertIn("eintritt", d["einheiten"]["speech-spark-asr"])
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.post(body("weiter")).json(), {"ok": True, "war": True})
            self.assertEqual(self.post(body("weiter")).json(), {"ok": True, "war": False})
        self.assertFalse(os.path.exists(common.WARTUNG_FILE))
        self.assertIn("waerter: weiter ok", out.getvalue())
        self.assertIn("waerter: weiter keine", out.getvalue())

    def test_its_pause_counts_here_while_its_time_runs(self):
        now = time.time()
        self.there({"on": True, "parts": ["llm", "asr"], "since": now - 60, "until": now + 600, "channel": "kommandozeile"})
        s = self.w.state()
        self.assertTrue(s["on"] and s.get("fern"))
        self.assertTrue(self.w.paused("llm") and self.w.quiet("asr"))
        self.assertFalse(self.w.paused("tts"))
        self.assertTrue(self.w.view()["fern"])
        helpers.set_config(wartung=False)
        self.assertFalse(self.w.paused("llm"), "the panel's own switch decides")
        helpers.set_config(wartung=True)
        self.there({"on": True, "parts": ["llm"], "since": now - 900, "until": now - 1, "channel": "kommandozeile"})
        self.assertFalse(self.w.paused("llm"), "its time is over: no pause here")
        self.there({"on": True, "parts": ["llm"], "since": now, "until": now + 600}, age=steuer.PUSH + 5)
        self.assertFalse(self.w.paused("llm"), "an old status counts as none")
        self.there({"on": True, "parts": ["musik"], "since": now, "until": now + 600})
        self.assertFalse(self.w.state()["on"], "a strange pause counts as none")

    def test_a_question_never_waits_for_the_model_computer(self):
        steuer._client = None
        steuer._status.update(t=0.0, d=None)
        with mock.patch.object(steuer, "call", side_effect=AssertionError("asked")):
            self.assertFalse(self.w.paused("llm"))

    def test_weiter_ends_both(self):
        now = time.time()
        self.there({"on": True, "parts": ["llm"], "since": now - 120, "until": now + 600})
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.w.end("weiter", now), 2)
        self.assertIn("wartung: modell-rechner weiter ok", out.getvalue())
        self.assertEqual(steuer._status["t"], 0.0, "its next status is asked fresh")

    def test_the_automatic_looks_there(self):
        steuer._status.update(t=time.monotonic(), d={"einheiten": {"speech-spark-asr": {"state": "active", "eintritt": 123},
                                                                   "speech-spark-tts": {"state": "unknown"}}})
        self.assertEqual(self.w._look("speech-spark-asr"), ("active", "123"))
        self.assertIsNone(self.w._look("speech-spark-tts"))

    def test_the_shell_on_the_model_computer_needs_no_panel_switch(self):
        helpers.set_config(wartung=False)
        c = common.load_config()
        c["models"]["host"] = "127.0.0.1"
        helpers.write_config(c)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.w.cli(["llm", "30"])[0], 1, "an all-in-one Spark: its switch decides")
            c["api"]["tls_listen"] = "192.168.178.171"
            helpers.write_config(c)
            self.assertEqual(self.w.cli(["llm", "30"])[0], 0)
        self.assertTrue(os.path.exists(common.WARTUNG_FILE))

    def test_live_shows_the_model_computer_in_counts(self):
        import live
        self.assertIn("modell", live.TARGETS)
        self.assertEqual(steuer.for_live(), {"on": True, "ok": False})
        steuer._status.update(t=time.monotonic(), d={"version": "V01.0.612", "pause": {"on": True},
                                                      "einheiten": {"a": {"state": "active"}, "b": {"state": "failed"},
                                                                    "c": {"state": "unknown"}}})
        self.assertEqual(steuer.for_live(), {"on": True, "ok": True, "aktiv": 1, "n": 2, "version": "V01.0.612", "pause": True})
        c = common.load_config()
        c["models"]["host"] = "127.0.0.1"
        helpers.write_config(c)
        self.assertEqual(steuer.for_live(), {"on": False})


class Steuer(Base):
    def setUp(self):
        super().setUp()
        steuer._client = self.app
        steuer._status.update(t=0.0, d=None)
        self.addCleanup(setattr, steuer, "_client", None)
        self.addCleanup(steuer._status.update, t=0.0, d=None)
        self.local = FakeRun()
        p = mock.patch.object(steuer, "run", self.local)
        p.start()
        self.addCleanup(p.stop)

    def cfg(self, host):
        c = json.loads(json.dumps(common.load_config()))
        c["models"]["host"] = host
        return c

    def test_remote_units_and_gpu_come_from_the_waerter(self):
        c = self.cfg("192.168.178.171")
        self.assertEqual(steuer.unit_state("speech-spark-asr", c), "active")
        self.assertEqual(steuer.unit_state("speech-spark-tts", c), "failed")
        self.assertAlmostEqual(steuer.active_seconds("speech-spark-asr", c), 90, delta=3)
        self.assertIsNone(steuer.active_seconds("speech-spark-tts", c))
        self.assertEqual(steuer.gpu(c)["name"], "GB10")
        self.assertEqual(self.local.calls, [], "nothing asked on this computer")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(steuer.systemctl("restart", "speech-spark-asr-engine", c), (0, ""))
        self.assertIn(["sudo", "-n", "/usr/bin/systemctl", "restart", "speech-spark-asr-engine"], self.run.calls)
        self.assertIn("steuer: einheit restart asr-engine ok", out.getvalue())

    def test_own_units_stay_here(self):
        c = self.cfg("192.168.178.171")
        steuer.unit_state("speech-spark-panel", c)
        steuer.systemctl("restart", "coturn", c)
        self.assertEqual(self.local.calls, [["systemctl", "is-active", "speech-spark-panel"],
                                            ["sudo", "-n", "/usr/bin/systemctl", "restart", "coturn"]])
        self.assertFalse([x for x in self.run.calls if "sudo" in x])

    def test_all_in_one_is_local(self):
        c = self.cfg("127.0.0.1")
        steuer.unit_state("speech-spark-asr", c)
        steuer.systemctl("restart", "speech-spark-asr", c)
        self.assertEqual(self.local.calls, [["systemctl", "is-active", "speech-spark-asr"],
                                            ["sudo", "-n", "/usr/bin/systemctl", "restart", "speech-spark-asr"]])
        self.assertEqual(self.run.calls, [], "the Wärter is never asked")

    def test_a_silent_model_computer_reads_unknown(self):
        steuer._client = None
        c = self.cfg("192.0.2.1")         # TEST-NET: nothing answers
        with mock.patch.object(steuer, "TIMEOUT", 0.2), mock.patch.object(steuer.httpx, "Client") as client:
            client.return_value.__enter__.return_value.post.side_effect = steuer.httpx.ConnectError("no")
            self.assertEqual(steuer.unit_state("speech-spark-asr", c), "unknown")
            self.assertIsNone(steuer.gpu(c))
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(steuer.systemctl("restart", "speech-spark-asr", c)[0], 1)
            self.assertIn("steuer: einheit restart asr fehler", out.getvalue())

    def test_the_status_is_reused_for_a_moment(self):
        c = self.cfg("192.168.178.171")
        for _ in range(5):
            steuer.unit_state("speech-spark-asr", c)
        self.assertEqual(len([x for x in self.run.calls if x[:2] == ["systemctl", "show"]]), 1)


if __name__ == "__main__":
    unittest.main()
