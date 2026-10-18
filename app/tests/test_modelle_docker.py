"""Docker nur auf tars, nur für Modell-Engines (Dominik 2026-10-17 „1a 2a 3a“, Richtlinie Teil 1): an entry with a
recipe (modelle.DOCKER) runs only as a container with a pinned image, no network, the panel's user, no capabilities and
the model cache read-only; its engine answers only on a Unix socket that dockertor.py puts on 127.0.0.1. For now it is
measured only: no native start, no switch. Nothing depends on the time of day."""
import asyncio
import os
import re
import sys
import tempfile
import unittest

from tests import helpers

helpers.start()
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
import modelle  # noqa: E402
import dockertor  # noqa: E402

FN = "qwen38-flash-next-fp4"
FN65 = "qwen38-flash-next-fp4-065"


def args(**k):
    m = modelle.eintrag(FN)
    return modelle.docker_args(m, m["revision"], "speech-spark-messen-engine", 990, 990,
                               hf_home="/var/lib/speech-spark/hf", ordner="/var/lib/speech-spark/state/docker-modelle", **k)


def cfg():
    return {"memory": {"reserve_gib": 10}, "llm": {"enabled": True, "modell": "qwen38-27b-nvfp4"},
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

    def test_wrong_calls_are_refused(self):
        m = modelle.eintrag(FN)
        for name, uid in (("messen", 990), ("speech-spark-Engine", 990), ("speech-spark-x;rm", 990),
                          ("speech-spark-messen-engine", 0), ("speech-spark-messen-engine", True)):
            with self.assertRaises(modelle.Fehler):
                modelle.docker_args(m, m["revision"], name, uid, 990)
        with self.assertRaises(modelle.Fehler):
            modelle.docker_args(m, "c" * 40, "speech-spark-messen-engine", 990, 990)    # pinned: no other commit
        with self.assertRaises(modelle.Fehler):
            modelle.docker_args(modelle.eintrag("qwen38-27b-nvfp4"), "", "speech-spark-messen-engine", 990, 990)

    def test_catalog_rules(self):
        m = modelle.eintrag(FN)
        for bad in ({"docker": "gibts-nicht"}, {"docker": "b12x", "venv": "llm"}):
            with self.assertRaises(modelle.Fehler):
                modelle.pruefe_eintrag(dict(m, vllm=dict(m["vllm"], **bad)))
        with self.assertRaises(modelle.Fehler):
            modelle.pruefe_eintrag(dict(m, art="sehen"))
        self.assertFalse(m["gewerblich"])                            # Qwen Community License + NVIDIA agreement
        self.assertEqual((m["anteil"], modelle.eintrag(FN65)["anteil"]), (0.7, 0.65))
        self.assertEqual(modelle.eintrag(FN65)["vllm"]["docker"], "b12x")
        eigen = dict(m, id="eigen-flash", eigen=True)
        with self.assertRaises(modelle.Fehler):
            modelle.eigen_ok(eigen)                                  # an own entry never brings a recipe

    def test_measured_only(self):
        m = modelle.eintrag(FN)
        with self.assertRaises(modelle.Fehler):
            modelle.vllm_args(m, revision=m["revision"])              # never natively on a port
        with self.assertRaises(modelle.Fehler):
            modelle.vllm_args(modelle.eintrag("qwen38-27b-nvfp4"), uds=modelle.DOCKER_SOCK)
        with self.assertRaises(modelle.Fehler) as e:
            modelle.rolle("llm", {"llm": {"modell": FN}})
        self.assertEqual(str(e.exception), "docker")
        for messung, wort in (({}, "ungeprueft"), ({"modelle": {FN: {"ok": True}}}, "docker")):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.wechsel_pruefen("llm", FN, cfg(), 200, messung=messung)
            self.assertEqual(str(e.exception), wort)
        self.assertEqual(modelle.messliste(["flash"]), [FN, FN65])
        self.assertEqual(modelle.laden_frist(m), modelle.DOCKER["b12x"]["laden_s"])
        self.assertEqual(modelle.laden_frist(modelle.eintrag("qwen38-27b-nvfp4")), modelle.GESUND_S)


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
