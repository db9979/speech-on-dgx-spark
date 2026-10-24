"""Qwen3.8 faster and several at once (Dominik 2026-10-17 „1+2+3“; modelle.parallel_messen, katalog "basis",
vllm "entwurf"): a main model candidate is measured with 2 and 4 long questions really at once, one question that
fits the context by the engine's own count, and the context room from /metrics; a part that fails leaves its fixed
word and the rest runs; no answer's text is kept. A variant is its basis with only the named fields changed; the
DSpark helper model has a pinned commit, is fetched and checked like the main one, never measured without itself and
never brings code. The engine is faked (no GPU); nothing depends on the time of day."""
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
    return {**copy.deepcopy(modelle.eintrag("qwen38-27b-nvfp4")), "kontext": KONTEXT, **kw}


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
        self.assertTrue(all(x.startswith("modelle: messung x ") or x.startswith("modelle: messung qwen38")
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
        self.assertIn("modelle: messung qwen38-27b-nvfp4 lang fehler httperror", lines)

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
        self.assertEqual(seen, ["qwen38-27b-nvfp4"])


class Varianten(unittest.TestCase):
    def kat(self, extra):
        p = os.path.join(tempfile.mkdtemp(), "k.json")
        with open(modelle.KATALOG) as f:
            data = json.load(f)
        data["modelle"] = [m for m in data["modelle"] if m["id"] == "qwen38-27b-nvfp4"] + extra
        with open(p, "w") as f:
            json.dump(data, f)
        return modelle.katalog(p, eigene=[])

    def test_a_variant_is_its_basis_with_only_the_named_fields(self):
        kat = modelle.katalog()
        basis, ds = kat["qwen38-27b-nvfp4"], kat["qwen38-27b-nvfp4-dspark"]
        self.assertEqual((ds["repo"], ds["revision"], ds["kontext"]), (basis["repo"], basis["revision"], basis["kontext"]))
        self.assertEqual(ds["messen"], "auf_wunsch")
        self.assertEqual(ds["anfrage"], basis["anfrage"])
        self.assertFalse(ds["gemessen"])
        self.assertEqual({k: v for k, v in ds["vllm"].items() if k not in ("mtp", "entwurf")},
                         {k: v for k, v in basis["vllm"].items() if k != "mtp"})
        self.assertGreater(ds["anteil"], basis["anteil"])          # the helper and its room need more (tars: 0.33 too little)
        self.assertFalse(ds["gewerblich"])                            # the helper model's licence is "other"
        self.assertEqual(modelle.messliste(["dspark"]), ["qwen38-27b-nvfp4-dspark"])
        self.assertNotIn("qwen38-27b-nvfp4-kv8", kat)                 # Qwen3.8 NVFP4 keeps its context store in FP8 already

    def test_broken_variants_are_refused(self):
        for bad in ({"id": "v-1", "basis": "gibts-nicht", "name": {"de": "a", "en": "a"}},
                    {"id": "v-1", "basis": "qwen38-27b-nvfp4", "vllm": {"kv_cache_dtype": "fp4"}},
                    {"id": "v-1", "basis": "qwen38-27b-nvfp4", "vllm": "x"},
                    {"id": "v-1", "basis": "qwen38-27b-nvfp4", "vllm": {"trust_remote_code": True}}):
            with self.assertRaises(modelle.Fehler, msg=bad):
                self.kat([bad])
        with self.assertRaises(modelle.Fehler):          # a variant of a variant
            self.kat([{"id": "v-1", "basis": "qwen38-27b-nvfp4"}, {"id": "v-2", "basis": "v-1"}])
        self.assertIn("v-1", self.kat([{"id": "v-1", "basis": "qwen38-27b-nvfp4"}]))

    def test_the_helper_model_is_pinned_and_never_left_out(self):
        ds = modelle.eintrag("qwen38-27b-nvfp4-dspark")
        e = ds["vllm"]["entwurf"]
        a = modelle.vllm_args(ds)
        spec = json.loads(a[a.index("--speculative-config") + 1])
        self.assertEqual(spec, {"method": "dspark", "model": e["repo"], "revision": e["revision"],
                                "num_speculative_tokens": 7, "draft_sample_method": "probabilistic"})
        self.assertEqual(a.count("--speculative-config"), 1)          # no MTP beside it
        self.assertNotIn("trust", " ".join(a))
        with self.assertRaises(modelle.Fehler):
            modelle.vllm_args(ds, mtp=False)                          # never "measured" without the helper
        for bad in ({"methode": "eagle9", "repo": e["repo"], "revision": e["revision"], "tokens": 7},
                    {"methode": "dspark", "repo": "../x", "revision": e["revision"], "tokens": 7},
                    {"methode": "dspark", "repo": e["repo"], "revision": "", "tokens": 7},
                    {"methode": "dspark", "repo": e["repo"], "revision": e["revision"], "tokens": 0},
                    dict(e, code=True)):
            with self.assertRaises(modelle.Fehler, msg=bad):
                modelle.pruefe_eintrag(dict(ds, vllm=dict(ds["vllm"], entwurf=bad)))
        with self.assertRaises(modelle.Fehler):
            modelle.pruefe_eintrag(dict(ds, vllm=dict(ds["vllm"], mtp=3)))

    def test_the_helper_model_is_fetched_and_checked_like_the_main_one(self):
        ds = modelle.eintrag("qwen38-27b-nvfp4-dspark")
        seen = []
        with mock.patch.object(modelle, "_laden", side_effect=lambda repo, rev, ordner: seen.append((repo, rev)) or rev):
            self.assertEqual(modelle.vorbereiten(ds, "/x"), ds["revision"])
        self.assertEqual(seen, [(ds["repo"], ds["revision"]),
                                (ds["vllm"]["entwurf"]["repo"], ds["vllm"]["entwurf"]["revision"])])
        geprueft = []
        gezeigt = []
        with mock.patch.object(modelle, "pruefen", side_effect=lambda o, r, hashes=True: geprueft.append((o, hashes))), \
                mock.patch.object(modelle, "zeiger", side_effect=lambda o, r: gezeigt.append((o, r))):
            cfg = {"llm": {"modell": ds["id"], "engine_port": 31016}}
            modelle.start_args("llm", cfg, {}, hf_home="/x")
        self.assertEqual([o for o, _ in geprueft], [modelle.hf_ordner(ds, "/x"), modelle.hf_ordner(ds["vllm"]["entwurf"], "/x")])
        # refs/main of both on their pinned commits (vllm-omni and other loaders ask without a revision, offline)
        self.assertEqual(gezeigt, [(modelle.hf_ordner(ds, "/x"), ds["revision"]),
                                   (modelle.hf_ordner(ds["vllm"]["entwurf"], "/x"), ds["vllm"]["entwurf"]["revision"])])
        self.assertTrue(all(modelle.ERLAUBT) and not any(modelle.VERBOTEN.search(p.replace("*", "x")) for p in modelle.ERLAUBT))

    def test_a_shared_folder_stays_while_any_of_its_entries_runs(self):
        cfg = {"llm": {"enabled": True, "modell": "qwen38-27b-nvfp4"}}
        with mock.patch.object(modelle, "jetzt_id", side_effect=lambda art, c, k=None: "qwen38-27b-nvfp4" if art == "llm" else ""), \
                mock.patch.object(modelle, "aktiv", return_value=[]):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.entfernbar("qwen38-27b-nvfp4-dspark", cfg, path=os.path.join(tempfile.mkdtemp(), "w.json"))
        self.assertEqual(str(e.exception), "aktiv")


if __name__ == "__main__":
    unittest.main()
