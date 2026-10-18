"""Umzug aufs eigene Sprachmodell, Stufe E3 (modelle.py umzug-*, rundlauf; speech-spark modelle llm uebernehmen|zurueck,
qwen38-aufraeumen; plan plaene/eigene-modelle.md): the running qwen38 units and the chat's old address are noted before
anything stops; the chat switches only after a round trip through the LLM-Tor (German sentence, tool call, picture,
System One) and goes back by itself when it fails; the way back restores exactly what was noted; qwen38 is stopped and
disabled, never removed, except by its own uninstall on Dominik's command after a working move. The door is faked;
nothing depends on the time of day."""
import copy
import json
import os
import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests import helpers

helpers.start()
import modelle  # noqa: E402
import llm  # noqa: E402
import live  # noqa: E402
import wartung  # noqa: E402


class Tor(BaseHTTPRequestHandler):
    """A fake LLM-Tor: needs the API key, answers health, chat (sentence, tool call, picture) and System One."""
    key = "sk-test"
    seen = []

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._json({"service": "llm", "status": "ready"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != f"Bearer {self.key}":
            return self._json({"detail": "key"}, 401)
        Tor.seen.append(self.path)
        if self.path == "/v1/systemone":
            return self._json({"answers": {"wetter": {"noul": 0.93}}})
        msg = body["messages"][-1]["content"]
        if body.get("tools"):
            return self._json({"choices": [{"message": {"tool_calls": [
                {"function": {"name": "wetter", "arguments": json.dumps({"ort": "Hamburg"})}}]}}]})
        if isinstance(msg, list):
            return self._json({"choices": [{"message": {"content": "Rechnung 4711 über 23,50 EUR."}}]})
        return self._json({"choices": [{"message": {"content": "Licht wird an der Luft gestreut, blaues Licht am meisten, "
                                                               "darum sehen wir den Himmel blau."}}]})


def cfg_with(port, **llm_extra):
    c = copy.deepcopy(modelle.load_config())
    c["llm"] = dict(c["llm"], port=port, **{"engine_port": port, **llm_extra})
    return c


class Schalten(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.note = os.path.join(self.d, "qwen38-vorher.json")
        self.raw = {"chat": {"llm_url": "http://127.0.0.1:30001/v1", "llm_key": "qk-123", "llm_key_from": "/home/db/.config/qwen38/api-key"},
                    "api": {"key": "sk-test"}}

    def test_the_way_back_restores_exactly_what_was_noted(self):
        modelle.merken(["qwen38-sglang.service", "qwen38-keepalive.service"], self.raw, self.note)
        units, alt = modelle.vorher(self.note)
        self.assertEqual(units, ["qwen38-sglang.service", "qwen38-keepalive.service"])
        an = modelle.schalten("an", self.raw, self.note)
        self.assertTrue(an["llm"]["enabled"])
        self.assertEqual(an["chat"], self.raw["chat"])                  # "an" alone changes nothing of the chat
        um = modelle.schalten("um", an, self.note)
        self.assertEqual(um["chat"]["llm_url"], modelle.tor_url(modelle.load_config()))
        self.assertEqual(um["chat"]["llm_key"], "")                     # the door takes api.key (llm.key)
        self.assertNotIn("llm_key_from", um["chat"])                   # so an update never brings qwen38's key back
        back = modelle.schalten("zurueck", um, self.note)
        self.assertFalse(back["llm"]["enabled"])
        self.assertEqual({k: back["chat"][k] for k in self.raw["chat"]}, self.raw["chat"])
        self.assertNotIn("llm_model", {k for k in back["chat"] if k not in self.raw["chat"] and back["chat"][k]})

    def test_no_second_move_and_only_qwen38_units(self):
        modelle.merken([], self.raw, self.note)
        with self.assertRaisesRegex(modelle.Fehler, "schon"):
            modelle.merken([], self.raw, self.note)
        with self.assertRaisesRegex(modelle.Fehler, "unit"):
            modelle.merken(["sshd.service"], self.raw, os.path.join(self.d, "x.json"))
        with self.assertRaisesRegex(modelle.Fehler, "aus"):
            modelle.schalten("um", self.raw, self.note)               # the chat never points at a door that is off

    def test_the_chat_uses_the_api_key_for_the_own_door(self):
        cfg = {"llm": {"port": 31006}, "api": {"key": "sk-neu"}}
        self.assertEqual(llm.key({"llm_url": "http://127.0.0.1:31006/v1", "llm_key": ""}, cfg), "sk-neu")
        self.assertEqual(llm.key({"llm_url": "http://127.0.0.1:31006/v1", "llm_key": "eigen"}, cfg), "eigen")
        self.assertEqual(llm.key({"llm_url": "http://192.168.1.5:31006/v1", "llm_key": ""}, cfg), "")   # never to elsewhere
        self.assertEqual(llm.key({"llm_url": "http://127.0.0.1:30001/v1", "llm_key": ""}, cfg), "")


class Rundlauf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Tor)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_round_trip_through_the_door(self):
        Tor.seen.clear()
        lines = []
        stufen = []
        ok, wort = modelle.rundlauf(cfg_with(self.srv.server_port), lines.append, sleep=lambda s: None, stufe=stufen.append)
        self.assertEqual((ok, wort), (True, "ok"), lines)
        self.assertEqual((stufen[0], stufen[1], stufen[-1]), ("probe", "satz", "systemone"))   # what Zustand → Modelle shows
        self.assertIn("/v1/systemone", Tor.seen)
        self.assertTrue(all(re.fullmatch(r"modelle: rundlauf [a-z ]+( nach \d+ s)?", x) for x in lines), lines)

    def test_a_wrong_key_fails_the_round_trip(self):
        c = cfg_with(self.srv.server_port)
        c["api"] = {"key": "falsch"}
        ok, wort = modelle.rundlauf(c, lambda s: None, sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertEqual(wort, "httperror")

    def test_waits_for_the_new_engine_not_the_door_alone(self):
        """Dominik 2026-10-18: right after the restart the door still said "ready" from the old engine."""
        t = iter(range(0, 100000, 400))
        Tor.seen.clear()
        c = cfg_with(self.srv.server_port, engine_port=1)         # the door answers, the new engine does not yet
        ok, wort = modelle.rundlauf(c, lambda s: None, frist=1200, now=lambda: next(t), sleep=lambda s: None)
        self.assertEqual((ok, wort), (False, "nicht bereit"))
        self.assertEqual([x for x in Tor.seen if x.startswith("/v1/")], [])   # no question went through the door

    def test_a_door_that_never_gets_ready_fails_in_time(self):
        t = iter(range(0, 100000, 400))
        c = cfg_with(1)          # nobody listens there
        ok, wort = modelle.rundlauf(c, lambda s: None, frist=1200, now=lambda: next(t), sleep=lambda s: None)
        self.assertEqual((ok, wort), (False, "nicht bereit"))


class Kommando(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(helpers.APP, "speech-spark.sh")) as f:
            cls.sh = f.read()
        root = os.path.dirname(helpers.APP)
        p = os.path.join(root, "install.sh")
        cls.inst = None                                             # a copy with only app/ has no install.sh
        if os.path.exists(p):
            with open(p) as f:
                cls.inst = f.read()

    def body(self, name):
        s = self.sh[self.sh.index(name + "() {"):]
        return s[:s.index("\n}\n")]

    def test_move_notes_first_and_goes_back_by_itself(self):
        b = self.body("cmd_umzug_intern")
        self.assertLess(b.index("umzug-merken"), b.index("trap umzug_abbruch EXIT"))
        self.assertLess(b.index("trap umzug_abbruch EXIT"), b.index('systemctl stop "${units[@]}"'))
        self.assertLess(b.index("modelle.py rundlauf"), b.index("umzug-schalten um"))     # the chat switches last
        self.assertIn("umzug_zurueck", self.body("umzug_abbruch"))
        self.assertIn("modelle: uebernahme abgebrochen", self.body("umzug_abbruch"))
        back = self.body("umzug_zurueck")
        self.assertIn('systemctl start --no-block "$u"', back)
        self.assertIn("umzug-schalten zurueck", back)
        self.assertIn('systemd-run --quiet --collect --unit="$UMZUG_UNIT"', self.body("run_umzug"))

    def test_qwen38_is_removed_only_by_its_own_uninstall_after_a_working_move(self):
        b = self.body("cmd_qwen38_aufraeumen")
        self.assertIn('[ "$(cfg \'.llm.enabled // false\')" = true ] && [ "$tor" = ready ]', b)
        self.assertLess(b.index('ask_yes ""'), b.index('if bash "$d/uninstall.sh"'))     # asks first, never --yes
        self.assertNotRegex(b, r"\brm -")
        self.assertIn("qwen38-aufraeumen) cmd_qwen38_aufraeumen ;;", self.sh)
        for name in ("cmd_umzug_intern", "umzug_zurueck", "cmd_messen_intern", "mess_restore"):
            self.assertNotIn("uninstall", self.body(name), name)

    def test_updates_never_bring_qwen38s_key_back_after_the_move(self):
        if self.inst is None:
            self.skipTest("install.sh is not part of an app/-only copy")
        i = self.inst.index('[ "$(cfgq -r \'.llm.enabled // false\')" = true ] && qkey=""')
        self.assertLess(i, self.inst.index('if [ -n "$qkey" ]; then'))
        self.assertNotRegex(self.inst, r"(?i)qwen38[^\n]*uninstall")


class Panel(unittest.TestCase):
    def test_maintenance_and_live_know_the_own_model(self):
        self.assertIn("speech-spark-llm", wartung.watched()["llm"])
        self.assertIn("speech-spark-llmtor", wartung.watched()["llm"])
        import modellseite
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            saved = json.load(f)
        c = copy.deepcopy(saved)
        c["llm"] = dict(c.get("llm", {}), enabled=True, modell="qwen38-27b-nvfp4")
        helpers.write_config(c)
        try:
            modellseite._live["t"] = None
            v = modellseite.for_live(now=1e9)
            if v.get("on"):
                self.assertEqual(v["eigen"], modelle.eintrag("qwen38-27b-nvfp4")["name"]["de"])
        finally:
            modellseite._live["t"] = None
            helpers.write_config(saved)
        self.assertTrue(live.TARGETS["qwen"][3])


if __name__ == "__main__":
    unittest.main()
