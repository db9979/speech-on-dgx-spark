"""Modell-Katalog, Stufe E0 (modelle.py, modelle.json, speech-spark modelle; plan plaene/eigene-modelle.md, Dominik
2026-10-14 „1a 2a 3a 4a 5a 6a“): every catalog entry follows the fixed rules (known engine, plain repository, full
commit or empty, memory share at most ANTEIL_MAX, never trust_remote_code); the vLLM arguments come only from those
fields and listen on 127.0.0.1; a cached model is checked file by file against its names (no pickle, no links out of
blobs/); a measurement keeps numbers and fixed words only, never an answer's text; the shell command never leaves
qwen38 stopped and never removes it. The engine is faked (no GPU); nothing depends on the time of day."""
import copy
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from tests import helpers

helpers.start()
import modelle  # noqa: E402

GEHEIM = "Zitronenfalter"   # a word only the fake model says: it must never reach a log line or the result file


class Fake(BaseHTTPRequestHandler):
    """An OpenAI-compatible engine with fixed answers: streamed text, a tool call, the two test pictures."""
    accepted = 0

    def log_message(self, *a):
        pass

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/metrics":
            Fake.accepted += 30
            text = (f"vllm:spec_decode_num_accepted_tokens_total{{model_name=\"x\"}} {Fake.accepted}.0\n"
                    f"vllm:spec_decode_num_draft_tokens_total{{model_name=\"x\"}} {Fake.accepted * 2}.0\n")
            data = text.encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msg = body["messages"][-1]["content"]
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for piece in ("Der ", GEHEIM, " fliegt."):
                self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}).encode() + b"\n\n")
            self.wfile.write(b"data: " + json.dumps({"choices": [], "usage": {"completion_tokens": 42}}).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            return
        if body.get("tools"):
            call = {"function": {"name": "wetter", "arguments": json.dumps({"ort": "Hamburg", "tag": "morgen"})}}
            return self._json({"choices": [{"message": {"content": None, "tool_calls": [call]}}]})
        if isinstance(msg, list):
            frage = msg[-1]["text"]
            text = ("Rechnung 4711 über 23,50 EUR, " + GEHEIM) if frage == modelle.BILD_TEXT_FRAGE else \
                "Ein roter Kreis und ein blaues Quadrat."
            return self._json({"choices": [{"message": {"content": text}}]})
        return self._json({"choices": [{"message": {"content": GEHEIM}}]})


class Engine:
    def __enter__(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self.srv.server_address[1]

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()


def qwen():
    return copy.deepcopy(modelle.eintrag("qwen38-27b-nvfp4"))


class Katalog(unittest.TestCase):
    def test_every_entry_follows_the_rules(self):
        kat = modelle.katalog()
        self.assertIn("qwen38-27b-nvfp4", kat)
        self.assertTrue(any(m["art"] == "sehen" for m in kat.values()))
        for mid, m in kat.items():
            self.assertLessEqual(m["anteil"], modelle.ANTEIL_MAX, mid)
            self.assertNotIn("trust_remote_code", json.dumps(m), mid)
            self.assertRegex(m["revision"], r"^([0-9a-f]{40})?$", mid)
            self.assertTrue(m["name"]["de"] and m["name"]["en"], mid)
        # the default language model is pinned, so a measurement and later the switch load exactly this commit
        self.assertRegex(kat["qwen38-27b-nvfp4"]["revision"], r"^[0-9a-f]{40}$")

    def test_broken_entries_are_refused(self):
        bad = [("trust", lambda m: m["vllm"].update(trust_remote_code=True)),
               ("anteil", lambda m: m.update(anteil=0.85)),
               ("repo", lambda m: m.update(repo="../etc")),
               ("repo2", lambda m: m.update(repo="a/b/c")),
               ("revision", lambda m: m.update(revision="main")),
               ("engine", lambda m: m.update(engine="docker")),
               ("flag", lambda m: m["vllm"].update(extra="--trust-remote-code")),
               ("parser", lambda m: m["vllm"].update(tool_call_parser="x; rm -rf /")),
               ("quant", lambda m: m["vllm"].update(quantization="gguf")),
               ("anfrage", lambda m: m["anfrage"].update(n=8)),
               ("sehen", lambda m: m.update(art="sehen", kann_sehen=False))]
        for name, change in bad:
            m = qwen()
            change(m)
            with self.assertRaises(modelle.Fehler, msg=name):
                modelle.pruefe_eintrag(m)

    def test_doubled_ids_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "k.json")
            with open(path, "w") as f:
                json.dump({"modelle": [qwen(), qwen()]}, f)
            with self.assertRaises(modelle.Fehler):
                modelle.katalog(path)

    def test_messliste(self):
        self.assertEqual(modelle.messliste([]), ["qwen38-27b-nvfp4", "qwen3-vl-8b-fp8"])
        self.assertEqual(modelle.messliste(["llm"]), ["qwen38-27b-nvfp4"])
        # the big downloads only when asked for by name
        self.assertNotIn("gemma-4-26b-a4b", modelle.messliste(["llm", "sehen"]))
        self.assertIn("gemma-4-26b-a4b", modelle.messliste(["gemma"]))
        self.assertIn("qwen38-27b-fp8", modelle.messliste(["fp8"]))
        with self.assertRaises(modelle.Fehler):
            modelle.messliste(["alles; rm"])


class VllmArgs(unittest.TestCase):
    def test_local_pinned_never_remote_code(self):
        a = modelle.vllm_args(qwen())
        self.assertEqual(a[0], "RadixArk/Qwen3.8-27B-NVFP4")
        self.assertEqual(a[a.index("--host") + 1], "127.0.0.1")
        self.assertEqual(a[a.index("--revision") + 1], qwen()["revision"])
        self.assertEqual(a[a.index("--max-model-len") + 1], "131072")
        self.assertEqual(a[a.index("--gpu-memory-utilization") + 1], "0.30")
        self.assertIn("--no-enable-flashinfer-autotune", a)
        self.assertNotIn("--trust-remote-code", a)
        self.assertEqual(json.loads(a[a.index("--speculative-config") + 1]), {"method": "mtp", "num_speculative_tokens": 3})
        self.assertNotIn("--speculative-config", modelle.vllm_args(qwen(), mtp=False))
        for kat in modelle.katalog().values():
            rev = kat["revision"] or "a" * 40
            self.assertNotIn("--trust-remote-code", modelle.vllm_args(kat, revision=rev))

    def test_revision_and_port_rules(self):
        vl = modelle.eintrag("qwen3-vl-8b-fp8")
        with self.assertRaises(modelle.Fehler):
            modelle.vllm_args(vl)                       # no commit yet: only after the download
        self.assertIn("b" * 40, modelle.vllm_args(vl, revision="b" * 40))
        with self.assertRaises(modelle.Fehler):
            modelle.vllm_args(qwen(), revision="c" * 40)   # a pinned entry never takes another commit
        for port in (30001, 31443, 8080, True):
            with self.assertRaises(modelle.Fehler):
                modelle.vllm_args(qwen(), port=port)

    def test_cli_prints_one_argument_per_line(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(modelle.cli(["vllm-args", "qwen38-27b-nvfp4", "--ohne-mtp"]), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "RadixArk/Qwen3.8-27B-NVFP4")
        self.assertNotIn("--speculative-config", lines)
        with redirect_stdout(io.StringIO()) as o:
            self.assertEqual(modelle.cli(["vllm-args", "gibtsnicht"]), 2)
        self.assertEqual(o.getvalue().strip(), "modelle: abgelehnt unbekannt")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(modelle.cli(["feld", "qwen38-27b-nvfp4", "anteil"]), 2)


class Pruefen(unittest.TestCase):
    """A Hugging Face cache folder: blobs named by their hash, the snapshot links into blobs/."""
    REV = "d" * 40

    def cache(self, d, files):
        os.makedirs(os.path.join(d, "blobs"))
        snap = os.path.join(d, "snapshots", self.REV)
        os.makedirs(snap)
        for name, data in files.items():
            if len(data) > 100:
                blob = hashlib.sha256(data).hexdigest()
            else:
                blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            with open(os.path.join(d, "blobs", blob), "wb") as f:
                f.write(data)
            os.symlink(os.path.join("..", "..", "blobs", blob), os.path.join(snap, name))
        return snap

    def test_good_cache(self):
        with tempfile.TemporaryDirectory() as d:
            self.cache(d, {"model.safetensors": b"x" * 500, "config.json": b"{}"})
            self.assertEqual(modelle.pruefen(d, self.REV), (2, 502))

    def test_changed_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.cache(d, {"model.safetensors": b"x" * 500, "config.json": b"{}"})
            blob = [b for b in os.listdir(os.path.join(d, "blobs")) if len(b) == 64][0]
            with open(os.path.join(d, "blobs", blob), "r+b") as f:
                f.write(b"y")
            with self.assertRaisesRegex(modelle.Fehler, "hash"):
                modelle.pruefen(d, self.REV)

    def test_pickle_code_links_and_no_weights(self):
        with tempfile.TemporaryDirectory() as d:
            self.cache(d, {"model.safetensors": b"x" * 500, "pytorch_model.bin": b"p" * 200})
            with self.assertRaisesRegex(modelle.Fehler, "dateiart"):
                modelle.pruefen(d, self.REV)
        with tempfile.TemporaryDirectory() as d:
            self.cache(d, {"model.safetensors": b"x" * 500, "modeling_x.py": b"import os"})
            with self.assertRaisesRegex(modelle.Fehler, "dateiart"):
                modelle.pruefen(d, self.REV)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            snap = self.cache(d, {"model.safetensors": b"x" * 500})
            with open(os.path.join(out, "x.json"), "w") as f:
                f.write("{}")
            os.symlink(os.path.join(out, "x.json"), os.path.join(snap, "tokenizer.json"))
            with self.assertRaisesRegex(modelle.Fehler, "link"):
                modelle.pruefen(d, self.REV)
        with tempfile.TemporaryDirectory() as d:
            self.cache(d, {"config.json": b"{}"})
            with self.assertRaisesRegex(modelle.Fehler, "gewichte"):
                modelle.pruefen(d, self.REV)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(modelle.Fehler, "fehlt"):
                modelle.pruefen(d, self.REV)
            with self.assertRaisesRegex(modelle.Fehler, "revision"):
                modelle.pruefen(d, "../../etc")

    def test_download_takes_only_allowed_kinds(self):
        for pat in modelle.ERLAUBT:
            self.assertFalse(modelle.VERBOTEN.search(pat.replace("*", "x")), pat)
        for name in ("a.bin", "b.pt", "c.pkl", "d.ckpt", "e.py", "f.pth"):
            self.assertTrue(modelle.VERBOTEN.search(name), name)


class Messen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = os.path.join(self.tmp.name, "modelle-messung.json")

    def run_one(self, m):
        lines = []
        with Engine() as port, mock.patch.object(modelle, "load_config", return_value={"image": {"enabled": False}}):
            r = modelle.messen_lauf(m, port, "", lines.append)
        return r, lines

    def test_measures_without_keeping_any_answer(self):
        r, lines = self.run_one(qwen())
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["tok_s"], 0)
        self.assertEqual(r["mtp_annahme"], 0.5)
        self.assertTrue(r["werkzeug"])
        self.assertTrue(r["bild_text"])
        self.assertTrue(r["bild_szene"])
        modelle.merke("qwen38-27b-nvfp4", r, self.file)
        with open(self.file) as f:
            saved = f.read()
        for line in lines + [modelle.zeile("qwen38-27b-nvfp4", r)]:
            self.assertTrue(line.startswith("modelle: "), line)
            self.assertNotIn(GEHEIM, line)
        self.assertNotIn(GEHEIM, saved)
        self.assertIn("werkzeug ok", modelle.zeile("qwen38-27b-nvfp4", r))

    def test_a_model_without_tools_or_eyes_is_not_asked(self):
        m = qwen()
        m.update(werkzeuge=False, kann_sehen=False)
        r, lines = self.run_one(m)
        self.assertTrue(r["ok"])
        self.assertNotIn("werkzeug", r)
        self.assertNotIn("bild_text", r)

    def test_stopped_engine_ends_the_measurement(self):
        with mock.patch.object(modelle, "_aktiv", return_value=False):
            r = modelle.messen_lauf(qwen(), 1, "speech-spark-messen-engine", lambda s: None)
        self.assertFalse(r["ok"])
        self.assertEqual(r["grund"], "engine_aus")
        self.assertEqual(modelle.zeile("x", r), "modelle: ergebnis x abgebrochen engine_aus")

    def test_waiting_has_a_limit(self):
        t = iter(range(0, 10000, 600))
        with mock.patch.object(modelle, "_post", side_effect=OSError):
            with self.assertRaisesRegex(modelle.Fehler, "zeit"):
                modelle.warte_bereit(qwen(), 1, "", now=lambda: next(t), sleep=lambda s: None)

    def test_checks_are_fixed_rules(self):
        self.assertTrue(modelle.bild_text_ok("Nr. 4711, Betrag 23,50 EUR"))
        self.assertFalse(modelle.bild_text_ok("Nr. 4711"))
        self.assertTrue(modelle.bild_szene_ok("Links ein roter Kreis, rechts ein blaues Rechteck."))
        self.assertFalse(modelle.bild_szene_ok("Ein Kreis."))
        self.assertFalse(modelle.werkzeug_ok({"choices": [{"message": {"tool_calls": [
            {"function": {"name": "wetter", "arguments": "kein json"}}]}}]}))
        self.assertEqual(modelle.spec_zaehler("vllm:spec_decode_num_accepted_tokens_total 3.0\n"), (3.0, 0))


class Kommando(unittest.TestCase):
    """speech-spark modelle (app/speech-spark.sh): runs as the service user, in its own unit, qwen38 always back."""
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(helpers.APP, "speech-spark.sh")) as f:
            cls.sh = f.read()

    def body(self, name):
        s = self.sh[self.sh.index(name + "() {"):]
        return s[:s.index("\n}\n")]

    def test_wired(self):
        self.assertIn("modelle) shift; cmd_modelle", self.sh)
        self.assertIn("as_panel_user ../modelle.py", self.sh)
        self.assertIn("messen) units=(-u speech-spark-messen -u speech-spark-messen-engine)", self.sh)
        # the help text (sed range) reaches the new lines
        head = self.sh.splitlines()
        rng = re.search(r"sed -n '2,(\d+)p'", self.sh).group(1)
        self.assertIn("speech-spark modelle messen", "\n".join(head[1:int(rng)]))
        self.assertTrue(head[int(rng)].startswith("set -euo"))

    def test_qwen38_comes_back_and_stays_installed(self):
        intern = self.body("cmd_messen_intern")
        # the trap is set before anything of qwen38 stops
        self.assertLess(intern.index("trap mess_restore EXIT"), intern.index('systemctl stop "${MESS_QWEN[@]}"'))
        self.assertIn('systemctl start --no-block "$u"', self.body("mess_restore"))
        self.assertIn("as_panel_user wartung.py weiter", self.body("mess_restore"))
        self.assertIn('[ "${INVOCATION_ID:-}" ]', self.body("cmd_modelle"))
        for line in self.sh.splitlines():
            code = line.split("#", 1)[0]
            self.assertNotRegex(code, r"(?i)qwen38.*(uninstall|disable|rm -)", line)

    def test_the_own_unit_runs_the_script_through_bash(self):
        # /opt/speech-spark/app/speech-spark.sh is not executable (the wrapper runs it with /bin/bash): systemd-run
        # refused "$self" with "Permission denied" on tars (V01.0.586)
        for line in self.sh.splitlines():
            if '"$self" modelle' in line:
                self.assertIn('/bin/bash "$self" modelle', line)

    def test_engine_runs_as_the_service_user_offline(self):
        eng = self.body("mess_engine")
        self.assertIn('-p User="$svc"', eng)
        self.assertIn("--setenv=HF_HUB_OFFLINE=1", eng)
        self.assertIn('"$PREFIX/venv-engine/bin/vllm" serve "${args[@]}"', eng)
        # the copy out of qwen38's cache is written by the service user and checked before use
        cp = self.body("hf_from_qwen38")
        self.assertIn('runuser -u "$svc" -- tar -C', cp)
        self.assertIn("as_panel_user ../modelle.py pruefen", cp)
        self.assertNotRegex(cp, r"\bcp\b|\bmv\b")


if __name__ == "__main__":
    unittest.main()
