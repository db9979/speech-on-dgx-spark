"""Docker nur auf tars, nur für Modell-Engines (Dominik 2026-10-17 „1a 2a 3a“, Richtlinie Teil 1): an entry with a
recipe (modelle.DOCKER) runs only as a container with a pinned image, no network, the panel's user, no capabilities and
the model cache read-only; its engine answers only on a Unix socket that dockertor.py puts on 127.0.0.1. Never a native start; a switch to it only
after a measurement here found it working (stage 2, Dominik 2026-11-17): root's unit speech-spark-llm-docker runs the
container, speech-spark-llm only the door. Nothing depends on the time of day."""
import asyncio
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
import modelle  # noqa: E402
import dockertor  # noqa: E402

FN = "qwen38-flash-next-fp4"


def args(**k):
    m = modelle.eintrag(FN)
    return modelle.docker_args(m, m["revision"], "speech-spark-messen-engine", 990, 990,
                               hf_home="/var/lib/speech-spark/hf", ordner="/var/lib/speech-spark/state/docker-modelle", **k)


def cfg():
    return {"memory": {"reserve_gib": 10}, "llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4"},
            "asr": {"enabled": True, "recognizer": "qwen", "model": "Qwen/Qwen3-ASR-1.7B"},
            "tts": {"enabled": True, "model": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"}}


class Rezept(unittest.TestCase):
    def test_every_recipe_is_pinned_and_quiet(self):
        for name, d in modelle.DOCKER.items():
            self.assertRegex(d["image"], modelle.IMAGE, name)       # by digest, never a moving tag
            self.assertNotIn("HF_TOKEN", d["umgebung"])
            self.assertTrue(all(re.fullmatch(r"[A-Z0-9_]+", k) for k in d["umgebung"]), name)
            self.assertTrue(all(a.startswith("--") for a in d["args"][::2]), name)
            self.assertNotIn("--trust-remote-code", d["args"])
            self.assertLessEqual(d["laden_s"], 3600)

    def test_flash_next_leaves_memory_free(self):
        # qwen38 v1.37.0, same image: PyTorch keeps at most 95 % and gives blocks back early (17-19 GiB stay free)
        a = args()
        self.assertIn("PYTORCH_CUDA_ALLOC_CONF=per_process_memory_fraction:0.95,garbage_collection_threshold:0.8", a)

    def test_container_has_no_network_and_no_rights(self):
        a = args()
        self.assertEqual(a[:2], ["run", "--rm"])
        self.assertEqual(a[a.index("--network") + 1], "none")
        self.assertEqual(a[a.index("--cap-drop") + 1], "ALL")
        self.assertEqual(a[a.index("--security-opt") + 1], "no-new-privileges")
        self.assertEqual(a[a.index("--user") + 1], "990:990")
        flach = " ".join(a)
        for nie in ("--privileged", "--network host", "--net=host", "--ipc", "unconfined", "apparmor", "HF_TOKEN",
                    "--cap-add", "--pid", "/var/run/docker.sock", "--trust-remote-code", "--host 0.0.0.0", "--port"):
            self.assertNotIn(nie, flach)
        mounts = [a[i + 1] for i, x in enumerate(a) if x == "-v"]
        self.assertEqual(mounts, ["/var/lib/speech-spark/hf:/hf:ro",
                                  f"/var/lib/speech-spark/state/docker-modelle/{FN}/cache:/cache",
                                  f"/var/lib/speech-spark/state/docker-modelle/{FN}/sock:/sock"])
        env = dict(a[i + 1].split("=", 1) for i, x in enumerate(a) if x == "-e")
        self.assertEqual((env["HF_HUB_OFFLINE"], env["HF_HOME"], env["HOME"]), ("1", "/hf", "/cache"))
        bild = a.index(modelle.docker_bild(modelle.eintrag(FN)))
        self.assertEqual(a[bild - 2:bild], ["--entrypoint", "vllm"])
        self.assertEqual(a[bild + 1:bild + 3], ["serve", "nvidia/Qwen3.8-Flash-Next-FP4-Local"])
        self.assertEqual(a[a.index("--uds") + 1], modelle.DOCKER_SOCK)
        self.assertEqual(a[a.index("--revision") + 1], modelle.eintrag(FN)["revision"])
        self.assertNotIn("--speculative-config", args(mtp=False))
        opts = [a[i + 1] for i, x in enumerate(a) if x == "--security-opt"]
        self.assertEqual(opts, ["no-new-privileges", "seccomp=" + os.path.join(APP, "docker-seccomp-b12x.json")])

    def test_own_seccomp_profile_only_adds_io_uring(self):
        """tars 2026-10-18: b12x reads its PLE table with io_uring, which Docker's default profile blocks. The own profile
        is that default plus exactly the three io_uring calls, pinned by its hash; seccomp is never switched off."""
        import json
        name, sha = modelle.DOCKER["b12x"]["seccomp"]
        with open(os.path.join(APP, name), encoding="utf-8") as f:
            prof = json.load(f)
        self.assertEqual((prof["defaultAction"], prof["defaultErrnoRet"]), ("SCMP_ACT_ERRNO", 1))
        extra = [r for r in prof["syscalls"] if "io_uring_setup" in r["names"]]
        self.assertEqual(len(extra), 1)
        self.assertEqual((sorted(extra[0]["names"]), extra[0]["action"]),
                         (["io_uring_enter", "io_uring_register", "io_uring_setup"], "SCMP_ACT_ALLOW"))
        self.assertNotIn("args", extra[0])
        self.assertFalse(any("io_uring" in n for r in prof["syscalls"] if r is not extra[0] for n in r["names"]))
        self.assertEqual(modelle.seccomp_profil(modelle.DOCKER["b12x"]), os.path.join(APP, name))
        with self.assertRaises(modelle.Fehler):
            modelle.seccomp_profil({"seccomp": (name, "0" * 64)})          # a changed file is refused
        with self.assertRaises(modelle.Fehler):
            modelle.seccomp_profil({"seccomp": ("../etc/x.json", sha)})
        self.assertEqual(modelle.seccomp_profil({}), "")

    def test_measured_without_thinking(self):
        """tars 2026-10-18: with thinking on, the cache measurement's 16 tokens all went to the reasoning and the answer
        came back empty ("leer"), and tok/s counted the thinking after the first visible word. Every language model with a
        reasoning parser is asked without thinking, like the 27B."""
        for mid, m in modelle.katalog().items():
            if m["engine"] == "vllm" and m["art"] == "llm" and m["vllm"].get("reasoning_parser"):
                self.assertIs(m["anfrage"].get("chat_template_kwargs", {}).get("enable_thinking"), False, mid)

    def test_no_picture_into_the_reserve(self):
        """tars 2026-10-18: Flash Next at 0.70 left about 8 GiB, the picture painted meanwhile took it to 0.1 GiB. The
        measurement paints only when the picture model's need plus the reserve is free."""
        c = {"image": {"enabled": True, "variant": "9b-q4"}, "memory": {"reserve_gib": 10}}     # 13 GiB + 10
        self.assertFalse(modelle.bild_platz(c, 8.0))
        self.assertFalse(modelle.bild_platz(c, 22.9))
        self.assertTrue(modelle.bild_platz(c, 23.0))
        self.assertTrue(modelle.bild_platz({"image": {"enabled": True}}, 21.0))                  # default 4B Q8: 11 + 10
        with open(os.path.join(APP, "modelle.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertLess(src.index("not bild_platz(cfg, mem_available_gib())"), src.index("target=_bild_malen"))

    def test_wrong_calls_are_refused(self):
        m = modelle.eintrag(FN)
        for name, uid in (("messen", 990), ("speech-spark-Engine", 990), ("speech-spark-x;rm", 990),
                          ("speech-spark-messen-engine", 0), ("speech-spark-messen-engine", True)):
            with self.assertRaises(modelle.Fehler):
                modelle.docker_args(m, m["revision"], name, uid, 990)
        with self.assertRaises(modelle.Fehler):
            modelle.docker_args(m, "c" * 40, "speech-spark-messen-engine", 990, 990)    # pinned: no other commit
        with self.assertRaises(modelle.Fehler):
            modelle.docker_args(modelle.eintrag("qwen36-35b-a3b-nvfp4"), "", "speech-spark-messen-engine", 990, 990)

    def test_catalog_rules(self):
        m = modelle.eintrag(FN)
        for bad in ({"docker": "gibts-nicht"}, {"docker": "b12x", "venv": "llm"}):
            with self.assertRaises(modelle.Fehler):
                modelle.pruefe_eintrag(dict(m, vllm=dict(m["vllm"], **bad)))
        with self.assertRaises(modelle.Fehler):
            modelle.pruefe_eintrag(dict(m, art="sehen"))
        self.assertFalse(m["gewerblich"])                            # Qwen Community License + NVIDIA agreement
        self.assertEqual(m["gpu_gib"], 84)
        with self.assertRaises(modelle.Fehler):
            modelle.eintrag("qwen38-flash-next-fp4-065")            # share 0.65 never started (tars 2026-10-21)
        eigen = dict(m, id="eigen-flash", eigen=True)
        with self.assertRaises(modelle.Fehler):
            modelle.eigen_ok(eigen)                                  # an own entry never brings a recipe

    def test_measured_first_never_natively(self):
        m = modelle.eintrag(FN)
        with self.assertRaises(modelle.Fehler):
            modelle.vllm_args(m, revision=m["revision"])              # never natively on a port
        with self.assertRaises(modelle.Fehler):
            modelle.vllm_args(modelle.eintrag("qwen36-35b-a3b-nvfp4"), uds=modelle.DOCKER_SOCK)
        c = {"llm": {"enabled": True, "modell": FN}}
        self.assertEqual(modelle.rolle("llm", c)[0]["id"], FN)       # the door's port, like every engine
        with self.assertRaises(modelle.Fehler) as e:
            modelle.start_args("llm", c)                              # engine.sh never starts it with vLLM
        self.assertEqual(str(e.exception), "docker")
        with self.assertRaises(modelle.Fehler) as e:
            modelle.wechsel_pruefen("llm", FN, cfg(), 200, messung={})
        self.assertEqual(str(e.exception), "ungeprueft")
        self.assertEqual(modelle.wechsel_pruefen("llm", FN, cfg(), 200, messung={"modelle": {FN: {"ok": True}}})["id"], FN)
        self.assertEqual(modelle.messliste(["flash"]), [FN])
        self.assertEqual(modelle.laden_frist(m), modelle.DOCKER["b12x"]["laden_s"])
        self.assertEqual(modelle.laden_frist(modelle.eintrag("qwen36-35b-a3b-nvfp4")), modelle.GESUND_S)


class Hauptmodell(unittest.TestCase):
    """Stage 2: the language model in Docker."""
    OK = {"modelle": {FN: {"ok": True}}}

    def test_only_a_measured_one_and_only_while_on(self):
        c = {"llm": {"enabled": True, "modell": FN}}
        self.assertEqual(modelle.docker_llm(c, messung=self.OK)["id"], FN)
        with self.assertRaises(modelle.Fehler) as e:
            modelle.docker_llm(c, messung={"modelle": {FN: {"ok": False}}})
        self.assertEqual(str(e.exception), "ungeprueft")
        self.assertIsNone(modelle.docker_llm({"llm": {"enabled": False, "modell": FN}}, messung=self.OK))
        self.assertIsNone(modelle.docker_llm({"llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4"}}, messung=self.OK))
        self.assertEqual(modelle.docker_llm_args({"llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4"}}, 990, 990,
                                                 messung=self.OK), [])
        self.assertEqual(modelle.docker_sock(modelle.eintrag(FN), "/var/lib/speech-spark/state/docker-modelle"),
                         "/var/lib/speech-spark/state/docker-modelle/" + FN + "/sock/engine.sock")

    def test_the_same_closed_container_under_its_own_name(self):
        c = {"llm": {"enabled": True, "modell": FN}}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(modelle, "pruefen"), mock.patch.object(modelle, "zeiger"):
            a = modelle.docker_llm_args(c, 990, 990, messung=self.OK, hf_home=d, ordner=d + "/docker-modelle")
        self.assertEqual(a[:4], ["run", "--rm", "--name", modelle.DOCKER_LLM])
        for x in ("--network", "none", "--cap-drop", "ALL", "no-new-privileges", "--uds", modelle.DOCKER_SOCK, "--max-logprobs"):
            self.assertIn(x, a)
        self.assertIn(modelle.docker_bild(modelle.eintrag(FN)), a)
        self.assertNotIn("--privileged", a)
        self.assertFalse(any(x.startswith("--network=host") or x == "host" for x in a))

    def test_root_checks_the_call_again(self):
        """speech-spark.sh docker_args_ok: the real call passes, every loosened one is refused."""
        import subprocess
        with open(os.path.join(APP, "speech-spark.sh"), encoding="utf-8") as f:
            sp = f.read()
        fn = sp[sp.index("docker_args_ok() {"):]
        fn = fn[:fn.index("\n}\n") + 3]
        a = args()

        def ok(x):
            return subprocess.run(["bash", "-c", fn + 'SVC_UID=990 SVC_GID=990 docker_args_ok "$@"', "x", *x]).returncode == 0
        self.assertTrue(ok(a))
        i = a.index("--network")
        for bad in (a[:i + 1] + ["host"] + a[i + 2:], a[:1] + ["--privileged"] + a[1:], a[:1] + ["--pid=host"] + a[1:],
                    a[:1] + ["--cap-add", "SYS_ADMIN"] + a[1:], a[:1] + ["--device", "/dev/mem"] + a[1:],
                    [x if x != "990:990" else "0:0" for x in a], [x for x in a if x != "none"], ["create"] + a[1:]):
            self.assertFalse(ok(bad), bad[:6])

    def test_signature_counts_the_image(self):
        c = {"llm": {"enabled": True, "modell": FN}}
        s = modelle.signatur("llm", c, messung=self.OK)
        self.assertRegex(s, r"^[0-9a-f]{16}$")
        with mock.patch.dict(modelle.DOCKER, {"b12x": dict(modelle.DOCKER["b12x"], image="x/y@sha256:" + "1" * 64)}):
            self.assertNotEqual(modelle.signatur("llm", c, messung=self.OK), s)

    def test_the_units_and_the_door(self):
        with open(os.path.join(APP, "engine.sh"), encoding="utf-8") as f:
            eng = f.read()
        with open(os.path.join(APP, "speech-spark.sh"), encoding="utf-8") as f:
            sp = f.read()
        # engine.sh: the door before any vLLM start, only for the language model
        self.assertLess(eng.index("modelle.py\" docker-llm"), eng.index("modelle.py\" start-args"))
        self.assertIn('exec "$PY" "$APP_DIR/dockertor.py" "$PORT" "$SOCK"', eng)
        self.assertIn('docker-llm-intern) [ "${INVOCATION_ID:-}" ] || die', sp)
        body = sp[sp.index("cmd_docker_llm_intern() {"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("io_uring_disabled", body)
        self.assertIn('docker_args_ok "${args[@]}"', body)
        self.assertIn('exec "$dk" "${args[@]}"', body)
        self.assertIn('DOCKER_LLM=speech-spark-llm-docker', sp)
        self.assertEqual(modelle.DOCKER_LLM, "speech-spark-llm-docker")
        self.assertIn("modelle: wechsel $art abgelehnt docker fehlt", sp)

    def test_roots_unit_is_part_of_the_language_model(self):
        inst = helpers.repo_file("install.sh")
        # root's unit: part of speech-spark-llm, the container removed after it stops, only inside its unit
        unit = inst[inst.index("speech-spark-llm-docker.service <<EOF"):]
        unit = unit[:unit.index("\nEOF")]
        for x in ("PartOf=speech-spark-llm.service", "WantedBy=speech-spark-llm.service", "modelle docker-llm-intern",
                  "docker rm -f speech-spark-llm-docker"):
            self.assertIn(x, unit)
        self.assertNotIn("User=", unit)
        self.assertIn("systemctl enable speech-spark-llm-docker.service", inst)


class Tor(unittest.TestCase):
    def test_only_a_model_socket_and_an_own_port(self):
        ok = "/var/lib/speech-spark/state/docker-modelle/x/sock/engine.sock"
        self.assertEqual(dockertor.pruefe("31016", ok), (31016, ok))
        for port, sock in (("30001", ok), ("31016", "/tmp/engine.sock"), ("31016", "relativ/docker-modelle/x/sock/engine.sock"),
                           ("31016", "/var/lib/speech-spark/state/docker-modelle/x/sock/other.sock"),
                           ("31016", "/var/run/docker.sock")):
            with self.assertRaises(ValueError):
                dockertor.pruefe(port, sock)

    def test_bytes_pass_both_ways(self):
        async def lauf(sock):
            async def echo(r, w):
                w.write(b"engine:" + await r.read(5))
                await w.drain()
                w.close()
            engine = await asyncio.start_unix_server(echo, sock)
            tor = await asyncio.start_server(lambda r, w: dockertor.handle(sock, r, w), "127.0.0.1", 0)
            port = tor.sockets[0].getsockname()[1]
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(b"hallo")
            await w.drain()
            antwort = await asyncio.wait_for(r.read(100), 5)
            w.close()
            tor.close()
            engine.close()
            return antwort
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(asyncio.run(lauf(os.path.join(d, "engine.sock"))), b"engine:hallo")

    def test_no_engine_yet_closes_the_connection(self):
        async def lauf(sock):
            tor = await asyncio.start_server(lambda r, w: dockertor.handle(sock, r, w), "127.0.0.1", 0)
            r, w = await asyncio.open_connection("127.0.0.1", tor.sockets[0].getsockname()[1])
            antwort = await asyncio.wait_for(r.read(10), 10)
            w.close()
            tor.close()
            return antwort
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(asyncio.run(lauf(os.path.join(d, "fehlt.sock"))), b"")


class Skript(unittest.TestCase):
    def test_measuring_runs_the_container_as_built(self):
        with open(os.path.join(APP, "speech-spark.sh"), encoding="utf-8") as f:
            sh = f.read()
        body = sh[sh.index("mess_docker() {"):sh.index("# one catalog model in its own engine unit")]
        self.assertIn("modelle.py docker-args", body)
        self.assertIn('-p User="$svc"', body)                 # the door runs as the panel's user, not as root
        self.assertIn("dockertor.py", body)
        self.assertIn("docker_weg", body)
        self.assertNotIn("--privileged", sh)
        self.assertNotIn("--network host", sh)
        self.assertIn('docker-bild "$1")" ] && { mess_docker', sh)  # an entry in Docker never starts natively
        self.assertIn('docker pull -q "$image"', sh)
        self.assertIn("io_uring_disabled", body)                # the host's own switch is only read, never changed
        self.assertNotIn("sysctl", body)            # the pinned image, before the language model stops


if __name__ == "__main__":
    unittest.main()
