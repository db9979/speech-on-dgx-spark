"""Several at once (Dominik 2026-10-17 „1+2+3“; modelle.parallel_messen, katalog "basis"): a main model candidate is
measured with 2 and 4 long questions really at once, one question that fits the context by the engine's own count, and
the context room from /metrics; a part that fails leaves its fixed word and the rest runs; no answer's text is kept. A
variant is its basis with only the named fields changed; a second repository beside the model (the DSpark helper,
vllm "entwurf") left with Qwen3.8 27B (Dominik 2026-11-11) and is refused. The engine is faked (no GPU); nothing
depends on the time of day."""
import copy
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from tests import helpers

helpers.start()
import modelle  # noqa: E402

GEHEIM = "Kohlweissling"
JE = 7000            # tokens the fake counts for VORLAUF
KONTEXT = 65536


class Fake(BaseHTTPRequestHandler):
    """Counts the streams that run at once; refuses a question longer than KONTEXT; fixed answers."""
    lock = threading.Lock()
    jetzt = hoechst = 0
    kein_platz = False

    def log_message(self, *a):
        pass

    def _send(self, code, data, typ="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        text = "" if Fake.kein_platz else \
            'vllm:cache_config_info{block_size="16",cache_dtype="auto",num_gpu_blocks="16384"} 1.0\n'
        self._send(200, text.encode(), "text/plain")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/tokenize":
            return self._send(200, json.dumps({"count": JE if body["prompt"] == modelle.VORLAUF else 10}).encode())
        lang = sum(len(str(x["content"])) for x in body["messages"])
        tokens = lang * JE // len(modelle.VORLAUF)
        if tokens > KONTEXT:
            return self._send(400, b'{"error": "too long"}')
        with Fake.lock:
            Fake.jetzt += 1
            Fake.hoechst = max(Fake.hoechst, Fake.jetzt)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for piece in ("Der ", GEHEIM, " leuchtet."):
                self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}).encode() + b"\n\n")
                self.wfile.flush()
                threading.Event().wait(0.05)        # long enough for the others to start meanwhile
            self.wfile.write(b"data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": tokens,
                                                                              "completion_tokens": 30}}).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
        finally:
            with Fake.lock:
                Fake.jetzt -= 1


class Engine:
    def __enter__(self):
        Fake.jetzt = Fake.hoechst = 0
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self.srv.server_address[1]

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()
        Fake.kein_platz = False


def qwen(**kw):
    return {**copy.deepcopy(modelle.eintrag("qwen36-35b-a3b-nvfp4")), "kontext": KONTEXT, **kw}


class Gleichzeitig(unittest.TestCase):
    def test_two_and_four_at_once_a_long_question_and_the_room(self):
        lines = []
        with Engine() as port:
            r = modelle.parallel_messen(qwen(), port, 1, lines.append)
        self.assertEqual(Fake.hoechst, 4)                             # really at once
        for n in modelle.PARALLEL:
            self.assertGreater(r[f"par{n}_tok_s"], 0)
            self.assertGreaterEqual(r[f"par{n}_summe"], r[f"par{n}_tok_s"] * n * 0.5)
        self.assertEqual(r["kv_tokens"], 16384 * 16)
        self.assertEqual(r["platz_64k"], 4)
        self.assertTrue(55000 < r["lang_tokens"] <= KONTEXT - 2048, r)  # sized by the engine's count, fits
        zeile = modelle.zeile("x", dict(r, ok=True))
        for x in ("2 gleichzeitig", "4 gleichzeitig", "lang ", "platz 4 mal 64k"):
            self.assertIn(x, zeile)
        for line in lines + [zeile, json.dumps(r)]:
            self.assertNotIn(GEHEIM, line)
        self.assertTrue(all(x.startswith("modelle: messung x ") or x.startswith("modelle: messung qwen36")
                            for x in lines), lines)

    def test_a_failing_part_leaves_its_word_and_the_rest_runs(self):
        global JE
        lines, alt = [], JE
        JE = 3000                  # the engine counts fewer: the long question would not fit with a guess
        self.addCleanup(lambda: globals().update(JE=alt))
        Fake.kein_platz = True
        with Engine() as port, mock.patch.object(modelle, "_je_vorlauf", return_value=2000):
            r = modelle.parallel_messen(qwen(vllm=dict(qwen()["vllm"], max_seqs=2)), port, 1, lines.append)
        self.assertNotIn("par4_tok_s", r)                             # max_seqs 2: never 4 at once
        self.assertIn("par2_tok_s", r)
        self.assertEqual(r["lang_fehler"], "httperror")
        self.assertNotIn("platz_64k", r)
        self.assertIn("lang fehler httperror", modelle.zeile("x", dict(r, ok=True)))
        self.assertIn("modelle: messung qwen36-35b-a3b-nvfp4 lang fehler httperror", lines)

    def test_only_a_main_model_with_a_long_context(self):
        seen = []
        with mock.patch.object(modelle, "parallel_messen", side_effect=lambda *a, **k: seen.append(a[0]["id"]) or {}), \
                mock.patch.object(modelle, "warte_bereit", return_value=1), \
                mock.patch.object(modelle, "_post", return_value={}), \
                mock.patch.object(modelle, "_get", return_value=""), \
                mock.patch.object(modelle, "stream_messen", return_value=(0.1, 10, 20.0)), \
                mock.patch.object(modelle, "load_config", return_value={}):
            for m in (qwen(werkzeuge=False, kann_sehen=False), qwen(kontext=8192, werkzeuge=False, kann_sehen=False),
                      dict(qwen(werkzeuge=False, kann_sehen=False), art="sehen")):
                modelle.messen_lauf(m, 31016, "", lambda s: None)
        self.assertEqual(seen, ["qwen36-35b-a3b-nvfp4"])


class Varianten(unittest.TestCase):
    def kat(self, extra):
        p = os.path.join(tempfile.mkdtemp(), "k.json")
        with open(modelle.KATALOG) as f:
            data = json.load(f)
        data["modelle"] = [m for m in data["modelle"] if m["id"] == "qwen36-35b-a3b-nvfp4"] + extra
        with open(p, "w") as f:
            json.dump(data, f)
        return modelle.katalog(p, eigene=[])

    def test_a_variant_is_its_basis_with_only_the_named_fields(self):
        kat = modelle.katalog()
        basis, ohne = kat["qwen36-35b-a3b-nvfp4"], kat["qwen36-35b-a3b-nvfp4-ohne-mtp"]
        self.assertEqual((ohne["repo"], ohne["revision"], ohne["kontext"], ohne["anteil"]),
                         (basis["repo"], basis["revision"], basis["kontext"], basis["anteil"]))
        self.assertEqual((ohne["messen"], basis["messen"]), ("auf_wunsch", "immer"))    # only the one with MTP by default
        self.assertEqual(ohne["anfrage"], basis["anfrage"])
        self.assertEqual({k: v for k, v in ohne["vllm"].items() if k != "mtp"},
                         {k: v for k, v in basis["vllm"].items() if k != "mtp"})
        self.assertEqual((ohne["vllm"]["mtp"], ohne["gewerblich"]), (0, basis["gewerblich"]))

    def test_broken_variants_are_refused(self):
        for bad in ({"id": "v-1", "basis": "gibts-nicht", "name": {"de": "a", "en": "a"}},
                    {"id": "v-1", "basis": "qwen36-35b-a3b-nvfp4", "vllm": {"kv_cache_dtype": "fp4"}},
                    {"id": "v-1", "basis": "qwen36-35b-a3b-nvfp4", "vllm": "x"},
                    {"id": "v-1", "basis": "qwen36-35b-a3b-nvfp4", "vllm": {"trust_remote_code": True}}):
            with self.assertRaises(modelle.Fehler, msg=bad):
                self.kat([bad])
        with self.assertRaises(modelle.Fehler):          # a variant of a variant
            self.kat([{"id": "v-1", "basis": "qwen36-35b-a3b-nvfp4"}, {"id": "v-2", "basis": "v-1"}])
        self.assertIn("v-1", self.kat([{"id": "v-1", "basis": "qwen36-35b-a3b-nvfp4"}]))

    def test_no_second_repository_beside_the_model(self):
        m = modelle.eintrag("qwen36-35b-a3b-nvfp4")
        bad = dict(m, vllm=dict(m["vllm"], entwurf={"methode": "dspark", "repo": "a/b", "revision": "c" * 40, "tokens": 7}))
        with self.assertRaises(modelle.Fehler):
            modelle.pruefe_eintrag(bad)                                # an unknown vllm field, never passed on
        seen = []
        with mock.patch.object(modelle, "_laden", side_effect=lambda repo, rev, ordner: seen.append((repo, rev)) or rev):
            self.assertEqual(modelle.vorbereiten(m, "/x"), m["revision"])
        self.assertEqual(seen, [(m["repo"], m["revision"])])
        geprueft, gezeigt = [], []
        with mock.patch.object(modelle, "pruefen", side_effect=lambda o, r, hashes=True: geprueft.append((o, hashes))), \
                mock.patch.object(modelle, "zeiger", side_effect=lambda o, r: gezeigt.append((o, r))):
            modelle.start_args("llm", {"llm": {"modell": m["id"], "engine_port": 31016}}, {}, hf_home="/x")
        self.assertEqual(geprueft, [(modelle.hf_ordner(m, "/x"), False)])
        # refs/main on the pinned commit (vllm-omni and other loaders ask without a revision, offline)
        self.assertEqual(gezeigt, [(modelle.hf_ordner(m, "/x"), m["revision"])])
        self.assertTrue(all(modelle.ERLAUBT) and not any(modelle.VERBOTEN.search(p.replace("*", "x")) for p in modelle.ERLAUBT))

    def test_a_shared_folder_stays_while_any_of_its_entries_runs(self):
        cfg = {"llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4"}}
        with mock.patch.object(modelle, "jetzt_id", side_effect=lambda art, c, k=None: "qwen36-35b-a3b-nvfp4" if art == "llm" else ""), \
                mock.patch.object(modelle, "aktiv", return_value=[]):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.entfernbar("qwen36-35b-a3b-nvfp4-ohne-mtp", cfg, path=os.path.join(tempfile.mkdtemp(), "w.json"))
        self.assertEqual(str(e.exception), "aktiv")


if __name__ == "__main__":
    unittest.main()
