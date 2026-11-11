"""The own language model is the only one (Dominik 2026-11-11 „Ganz weg“, Ausdünnen point 6): `install.sh --llm`
switches it on and the chat to its LLM-Tor, the move from qwen38 (modelle llm uebernehmen|zurueck, qwen38-aufraeumen,
the copy out of qwen38's cache) is gone for good; the round trip through the LLM-Tor (German sentence, tool call,
picture, System One) still checks a model switch. The door is faked; nothing depends on the time of day."""
import copy
import json
import os
import re
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


class Schluessel(unittest.TestCase):
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

    def test_no_way_back_to_qwen38(self):
        for word in ("umzug-intern", "qwen38-aufraeumen", "hf_from_qwen38", "UMZUG_UNIT", "llm uebernehmen", "qwen38-*"):
            self.assertNotIn(word, self.sh, word)
        with open(os.path.join(helpers.APP, "modelle.py")) as f:
            m = f.read()
        for word in ("umzug-", "qwen38-vorher", "qwen38_lanes", "qwen38-extern"):
            self.assertNotIn(word, m, word)
        self.assertNotIn("qwen38-extern", modelle.katalog())

    def test_install_llm_switches_the_chat_to_the_own_door(self):
        if self.inst is None:
            self.skipTest("install.sh is not part of an app/-only copy")
        i = self.inst.index('if [ "$LLM_PICK" = 1 ] && [ "$PANEL_ONLY" = 0 ]')
        b = self.inst[i:self.inst.index("\nfi\n", i)]
        self.assertIn(".llm.enabled = true", b)
        self.assertIn('.chat.llm_url = "http://127.0.0.1:\\($p)/v1"', b)       # this computer's door, never elsewhere
        self.assertIn('.chat.llm_key = ""', b)                                 # its key is api.key (llm.key)
        self.assertLess(self.inst.index("PANEL_ONLY=1; WITH_ASR=0"), i)          # a panel computer keeps its address
        self.assertNotIn(".config/qwen38", self.inst)                          # no foreign key is read any more


class Panel(unittest.TestCase):
    def test_maintenance_and_live_know_the_own_model(self):
        self.assertIn("speech-spark-llm", wartung.watched()["llm"])
        self.assertIn("speech-spark-llmtor", wartung.watched()["llm"])
        import modellseite
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            saved = json.load(f)
        c = copy.deepcopy(saved)
        c["llm"] = dict(c.get("llm", {}), enabled=True, modell="qwen36-35b-a3b-nvfp4")
        helpers.write_config(c)
        try:
            modellseite._live["t"] = None
            v = modellseite.for_live(now=1e9)
            if v.get("on"):
                self.assertEqual(v["eigen"], modelle.eintrag("qwen36-35b-a3b-nvfp4")["name"]["de"])
        finally:
            modellseite._live["t"] = None
            helpers.write_config(saved)
        self.assertTrue(live.TARGETS["qwen"][3])


if __name__ == "__main__":
    unittest.main()
