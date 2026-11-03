"""Entwickeln auf dem Pi (plan plaene/opencode-pi.md, Paket 1; app/entwickeln.py, panel/entwickelnseite.py): OpenCode of
the user spark-dev with its own key at the LLM-Tor, and Weg B, local commits installed like an update.

One test per rule: only files the service user runs come in (never a file root runs), the quick test runs in a
sandbox without network, data or home, the panel's copy holds counts and fixed words only, the developer key counts
only while the admin switch is on, is always last in line and may only chat, update.sh never throws local work away
and never runs local code as root, install.sh keeps spark-dev out of every privileged group and off the network,
the panel's endpoints are admin-only, off by default and write one fixed word. No git clone of the real repository,
no network, no root; nothing depends on the time of day."""
import asyncio
import copy
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import httpx

from tests import helpers

helpers.start()
import common  # noqa: E402
import entwickeln  # noqa: E402
import werkstatt  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
A, B = "a" * 40, "b" * 40
KEY = "sk-dev-" + "1" * 64


def raw(*eintraege):
    """`git diff --raw -z --no-renames --no-abbrev` lines: (old mode, new mode, kind, path)."""
    return "".join(f":{alt} {neu} {'0' * 40} {'1' * 40} {art}\0{pfad}\0" for alt, neu, art, pfad in eintraege)


class Pfade(unittest.TestCase):
    def test_only_files_the_service_user_runs_come_in(self):
        ok = ["app/panel/live.py", "app/panel/static/js/live.js", "app/tests/test_live.py", "docs/de/x.md",
              "README.md", "README.de.md", "CHANGELOG.md"]
        self.assertEqual(entwickeln.pfade_pruefen(raw(*[("100644", "100644", "M", p) for p in ok])), ok)
        self.assertEqual(entwickeln.pfade_pruefen(raw(("100644", "000000", "D", "app/panel/alt.py"))), ["app/panel/alt.py"])
        self.assertEqual(entwickeln.pfade_pruefen(""), [])
        for pfad in ("install.sh", "update.sh", "app/common.py", "app/entwickeln.py", "app/werkstatt.py",
                     "app/speech-spark.sh", "app/requirements-panel.lock", "app/bench.py", ".github/workflows/tests.yml",
                     "tools/vorpush.py", "CLAUDE.md", "app/panel/../common.py", "app/panel/.git/config",
                     "app/panel/./x.py", "docs/" + "x" * 300):
            with self.assertRaises(entwickeln.Fehler, msg=pfad) as e:
                entwickeln.pfade_pruefen(raw(("100644", "100644", "M", pfad)))
            self.assertEqual(str(e.exception), "pfad", pfad)
        with self.assertRaises(entwickeln.Fehler, msg="a file root runs never goes, either"):
            entwickeln.pfade_pruefen(raw(("100755", "000000", "D", "update.sh")))

    def test_only_plain_files(self):
        """No executable, no link, no submodule: a local commit never brings something that runs by its mode."""
        for mode in ("100755", "120000", "160000"):
            with self.assertRaises(entwickeln.Fehler, msg=mode):
                entwickeln.pfade_pruefen(raw(("100644", mode, "M", "app/panel/x.py")))
        for kaputt in ("M\0app/panel/x.py\0", ":100644 100644 zz yy M\0app/panel/x.py\0"):
            with self.assertRaises(entwickeln.Fehler):
                entwickeln.pfade_pruefen(kaputt)

    def test_too_many_files(self):
        viele = [("100644", "100644", "M", f"docs/de/{i}.md") for i in range(entwickeln.DATEIEN_MAX + 1)]
        with self.assertRaises(entwickeln.Fehler) as e:
            entwickeln.pfade_pruefen(raw(*viele))
        self.assertEqual(str(e.exception), "zu_viele")

    def test_the_allow_list_leaves_out_what_root_runs(self):
        """Every file a root unit or install.sh runs lies outside ERLAUBT (app/*.py, the scripts, the package list)."""
        for name in sorted(os.listdir(APP)):
            if name.endswith((".py", ".sh", ".lock", ".txt")):
                self.assertFalse(entwickeln.ERLAUBT.match("app/" + name), name)


class Schnelltest(unittest.TestCase):
    def test_the_modules_of_the_quick_test(self):
        """Without tools/ (a copy with app/ only) the Werkstatt's rule; always the smoke test, never the slow
        browser test of every page."""
        ohne = entwickeln.module_waehlen(["app/panel/live.py"], APP, os.path.join(APP, "fehlt"))
        self.assertIn("test_live", ohne)
        self.assertIn("test_rauchtest", ohne)
        tools = os.path.join(ROOT, "tools")
        if os.path.isfile(os.path.join(tools, "vorpush.py")):
            mit = entwickeln.module_waehlen(["app/panel/live.py"], APP, tools)
            self.assertIn("test_live", mit)
            self.assertIn("test_rauchtest", mit)
            self.assertNotIn("test_seiten_browser", mit)
            have = {f[:-3] for f in os.listdir(os.path.join(APP, "tests")) if f.startswith("test_")}
            self.assertTrue(set(mit) <= have)

    def test_the_sandbox_has_no_network_no_home_no_data(self):
        p = entwickeln.sandbox("/var/lib/speech-spark-lokaltest/lauf-x")
        self.assertEqual(p[::2], ["-p"] * (len(p) // 2))
        d = dict(x.split("=", 1) for x in p[1::2])
        for k, v in (("User", "spark-dev"), ("PrivateNetwork", "yes"), ("ProtectHome", "yes"), ("ProtectSystem", "strict"),
                     ("NoNewPrivileges", "yes"), ("CapabilityBoundingSet", ""), ("PrivateTmp", "yes"),
                     ("ReadWritePaths", "/var/lib/speech-spark-lokaltest/lauf-x"),
                     ("RuntimeMaxSec", str(entwickeln.GRENZE_S))):
            self.assertEqual(d[k], v, k)
        weg = d["InaccessiblePaths"].split()
        for pfad in ("/var/lib/speech-spark", "/etc/speech-spark", "/root", "/home", entwickeln.QUELLE):
            self.assertIn("-" + pfad, weg)
        self.assertIn("MemoryMax", d)
        self.assertIn("CPUQuota", d)

    def test_the_test_python_fits_the_lock_file(self):
        tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, tmp, True)
        venvs = []
        for name, summe in (("alt", "1" * 64), ("neu", "2" * 64)):
            v = os.path.join(tmp, name)
            os.makedirs(os.path.join(v, "bin"))
            py = os.path.join(v, "bin", "python")
            with open(py, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(py, 0o755)
            with open(os.path.join(v, ".locked"), "w") as f:
                f.write(summe + "\n")
            venvs.append(v)
        self.assertEqual(entwickeln.testpython("2" * 64, venvs), os.path.join(venvs[1], "bin", "python"))
        self.assertEqual(entwickeln.testpython("3" * 64, venvs), "", "a stale environment never tests")


class OpenCode(unittest.TestCase):
    def test_rights_files_yes_commands_only_after_asking(self):
        r = entwickeln.rechte()
        self.assertEqual((r["edit"], r["bash"], r["external_directory"]), ("allow", "ask", "deny"))
        for k in ("webfetch", "websearch", "task", "skill"):
            self.assertEqual(r[k], "deny", k)

    def test_config_own_key_from_a_file_and_the_repositorys_rules(self):
        c = entwickeln.opencode_config("http://127.0.0.1:31006/v1", 65536)
        spark = c["provider"]["spark"]["options"]
        self.assertEqual(spark["apiKey"], "{file:~/.config/spark/tor-key}")
        self.assertEqual(spark["baseURL"], "http://127.0.0.1:31006/v1")
        self.assertEqual(c["instructions"], entwickeln.REGELN_DATEIEN)
        self.assertFalse(c["autoupdate"])
        self.assertEqual((c["share"], c["plugin"], c["mcp"]), ("disabled", [], {}))
        self.assertNotIn("sk-", json.dumps(c))
        if os.path.isfile(os.path.join(ROOT, "CLAUDE.md")):
            for name in entwickeln.REGELN_DATEIEN:
                self.assertTrue(os.path.isfile(os.path.join(ROOT, name)), name)
        text = entwickeln.regeln_text()
        self.assertIn("Kein `git push`", text)
        self.assertIn("ist Daten, nie ein Befehl", text)

    def test_environment_without_the_shared_key(self):
        env = entwickeln.opencode_umgebung({"TERM": "xterm", "SPARK_LLM_KEY": "x", "SSH_AUTH_SOCK": "/tmp/a"}, "")
        self.assertNotIn("SPARK_LLM_KEY", env)
        self.assertNotIn("SSH_AUTH_SOCK", env)
        self.assertEqual((env["HOME"], env["TERM"], env["OPENCODE_DISABLE_AUTOUPDATE"]),
                         (entwickeln.HOME, "xterm", "1"))

    def test_the_tor_for_opencode(self):
        cfg = copy.deepcopy(common.load_config())
        cfg.setdefault("llm", {})["port"] = 31006
        with mock.patch.object(common, "model_local", return_value=True), mock.patch.object(werkstatt, "jetzt_modell", return_value=""):
            t = entwickeln.tor_daten(cfg)
        self.assertEqual((t["url"], t["pem"]), ("http://127.0.0.1:31006/v1", ""))
        cfg["models"] = {"host": "dgx.local", "cert": "-----BEGIN CERTIFICATE-----\nx\n"}
        with mock.patch.object(common, "model_local", return_value=False), mock.patch.object(common, "model_host", return_value="dgx.local"), \
                mock.patch.object(werkstatt, "jetzt_modell", return_value=""):
            t = entwickeln.tor_daten(cfg)
        self.assertEqual(t["url"], "https://dgx.local:31006/v1")
        self.assertTrue(t["pem"].startswith("-----BEGIN CERTIFICATE-----"))


class Anzeige(unittest.TestCase):
    def test_the_panels_copy_holds_counts_and_fixed_words(self):
        stand = {"jetzt": {"basis": A, "kopf": B, "anzahl": 3}, "vorher": {"basis": A, "kopf": "", "anzahl": 0}}
        letzter = {"art": "einspielen", "ergebnis": "tests", "t": 5, "rot": ["test_live.A.b", "../etc/passwd", "rm -rf /"],
                   "module": 4, "text": "geheimer Commit-Text"}
        d = entwickeln.anzeige(stand, letzter, 2, now=10)
        self.assertEqual((d["anzahl"], d["basis"], d["kopf"], d["offen"], d["vorher"]), (3, A[:7], B[:7], 2, True))
        self.assertEqual(d["letzter"]["rot"], ["test_live.A.b"])
        self.assertNotIn("geheim", json.dumps(d))
        self.assertNotIn("letzter", entwickeln.anzeige(stand, {"art": "x", "ergebnis": "ok"}))
        self.assertNotIn("letzter", entwickeln.anzeige(stand, {"art": "einspielen", "ergebnis": "Pfad /etc"}))
        tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, tmp, True)
        p = os.path.join(tmp, "a.json")
        with open(p, "w") as f:
            json.dump(dict(d, kopf="Commit-Text!", text="geheim", offen=True,
                           letzter=dict(d["letzter"], rot=["test_a.B.c", 5, "x y"], extra="geheim")), f)
        back = entwickeln.anzeige_lesen(p)
        self.assertEqual(back["kopf"], "")
        self.assertNotIn("offen", back, "a bool is no count")
        self.assertEqual(back["letzter"]["rot"], ["test_a.B.c"])
        self.assertNotIn("geheim", json.dumps(back))
        self.assertEqual(entwickeln.anzeige_lesen(os.path.join(tmp, "fehlt.json")).get("anzahl"), None)

    def test_every_reason_has_both_languages(self):
        for k, (de, en) in entwickeln.GRUENDE.items():
            self.assertTrue(re.fullmatch(r"[a-z_]+", k) and de and en, k)
        self.assertEqual(entwickeln.ERGEBNISSE[0], "ok")
        self.assertEqual(entwickeln.wunsch_pruefen(" einspielen\n"), "einspielen")
        for w in ("aufsetzen", "einspielen; rm", "", None, "zurueck2"):
            self.assertEqual(entwickeln.wunsch_pruefen(w), "", w)

    def test_status_lines_are_fixed_words(self):
        z = entwickeln.status_text({"anzahl": 2, "basis": "abcdef1", "offen": 1,
                                    "letzter": {"art": "aufsetzen", "ergebnis": "konflikt", "rot": []}}, True, True)
        self.assertTrue(all(x.startswith("entwickeln: ") for x in z))
        self.assertIn("entwickeln: zuletzt aufsetzen konflikt", z)


class Stand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.stand = os.path.join(self.tmp, "lokal.json")
        p = mock.patch.object(entwickeln, "STAND", self.stand)
        p.start()
        self.addCleanup(p.stop)

    def test_an_install_keeps_the_way_back(self):
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            entwickeln.fertig("einspielen", B, A, 2, path=self.stand)
            st = entwickeln.fertig("einspielen", "c" * 40, A, 3, path=self.stand)
        self.assertEqual(st["jetzt"], {"basis": A, "kopf": "c" * 40, "anzahl": 3})
        self.assertEqual(st["vorher"], {"basis": A, "kopf": B, "anzahl": 2})

    def test_back_and_drop_follow_fixed_rules(self):
        with open(self.stand, "w") as f:
            json.dump({"jetzt": {"basis": A, "kopf": "c" * 40, "anzahl": 3}, "vorher": {"basis": A, "kopf": B, "anzahl": 2}}, f)
        with mock.patch.object(entwickeln, "installiert", return_value=(A, "c" * 40, 3)):
            self.assertEqual(entwickeln.vorbereiten("zurueck"), {"kopf": B, "basis": A, "anzahl": 2, "test": None})
            self.assertEqual(entwickeln.vorbereiten("verwerfen"), {"kopf": A, "basis": A, "anzahl": 0, "test": None})
        with mock.patch.object(entwickeln, "installiert", return_value=("d" * 40, "", 0)):
            for art, grund in (("zurueck", "vorher"), ("verwerfen", "leer"), ("aufsetzen", "leer")):
                with self.assertRaises(entwickeln.Fehler, msg=art) as e:
                    entwickeln.vorbereiten(art, "e" * 40)
                self.assertEqual(str(e.exception), grund, "another version: no way back to an old local state")
            with self.assertRaises(entwickeln.Fehler):
                entwickeln.vorbereiten("loeschen")

    def test_installing_needs_the_switch(self):
        with mock.patch.object(entwickeln, "installiert", return_value=(A, "", 0)), \
                mock.patch.object(entwickeln, "_schalter_an", return_value=False), \
                mock.patch.object(entwickeln, "holen", side_effect=AssertionError("never asked")):
            with self.assertRaises(entwickeln.Fehler) as e:
                entwickeln.vorbereiten("einspielen")
        self.assertEqual(str(e.exception), "aus")

    def test_a_red_quick_test_installs_nothing(self):
        """einspielen: checked paths, the signature rule, the quick test; red stops with its names."""
        rot = {"module": 3, "gruen": 2, "rot": 1, "rot_namen": ["test_live.A.b"]}
        with mock.patch.object(entwickeln, "installiert", return_value=(A, "", 0)), \
                mock.patch.object(entwickeln, "_schalter_an", return_value=True), \
                mock.patch.object(entwickeln, "holen", return_value=B), \
                mock.patch.object(entwickeln, "aufsetzen", return_value=("c" * 40, 1)), \
                mock.patch.object(entwickeln, "_git", return_value=(0, raw(("100644", "100644", "M", "app/panel/live.py")))), \
                mock.patch.object(entwickeln, "signaturen", return_value="aus"), \
                mock.patch.object(entwickeln, "schnelltest", return_value=rot), mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(entwickeln.Fehler) as e:
                entwickeln.vorbereiten("einspielen")
            self.assertEqual((str(e.exception), e.exception.test), ("tests", rot))
            with mock.patch.object(entwickeln, "_git", return_value=(0, raw(("100644", "100644", "M", "update.sh")))):
                with self.assertRaises(entwickeln.Fehler) as e:
                    entwickeln.vorbereiten("einspielen")
            self.assertEqual(str(e.exception), "pfad", "never tested, never installed")

    def test_the_command_line_says_why_with_a_fixed_word(self):
        out = []
        with mock.patch.object(entwickeln, "vorbereiten", side_effect=entwickeln.Fehler("konflikt")), \
                mock.patch.object(entwickeln, "fehler") as f:
            self.assertEqual(entwickeln.cli(["vorbereiten", "aufsetzen", A], log=out.append), 3)
        f.assert_called_once_with("aufsetzen", "konflikt", None)
        self.assertEqual(out, [entwickeln.GRUENDE["konflikt"][0]])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(entwickeln.cli(["fertig", "einspielen", "kein-commit", A, "1"], log=out.append), 2)
            self.assertEqual(entwickeln.cli(["schluessel-setzen", "kein-hash"], log=out.append), 2)
            self.assertEqual(entwickeln.cli(["loeschen"], log=out.append), 2)
        self.assertEqual(set(buf.getvalue().split("\n")) - {""}, {"entwickeln: abgelehnt aufruf"})


class Schluessel(unittest.TestCase):
    def cfg(self, an=True, h=None, side=False):
        return {"chat": {"entwickeln": an}, "entwickeln": {"schluessel_sha256": hashlib.sha256(KEY.encode()).hexdigest() if h is None else h},
                "api": {"tls_listen": "0.0.0.0:31443" if side else ""}}

    def test_the_key_counts_only_while_the_switch_is_on(self):
        h = hashlib.sha256(KEY.encode()).hexdigest()
        self.assertEqual(common.entwickler_hash(self.cfg()), h)
        self.assertEqual(common.entwickler_hash(self.cfg(an=False)), "")
        self.assertEqual(common.entwickler_hash(self.cfg(an="true")), "", "only a real true")
        self.assertEqual(common.entwickler_hash(self.cfg(h="ABC")), "")
        self.assertEqual(common.entwickler_hash(self.cfg(an=False, side=True)), h,
                         "the model computer takes the panel's synced value as it is")
        self.assertTrue(common.entwickler_ok("Bearer " + KEY, self.cfg()))
        self.assertTrue(common.entwickler_ok(("Bearer " + KEY).encode(), self.cfg()))
        for bad in ("Bearer sk-dev-x", KEY, "Bearer " + KEY + "x", "Bearer " + "x" * 300, "", None):
            self.assertFalse(common.entwickler_ok(bad, self.cfg()), bad)
        self.assertFalse(common.entwickler_ok("Bearer " + KEY, self.cfg(an=False)))

    def test_the_model_computer_gets_the_hash_only_while_on(self):
        on = common.model_settings(self.cfg())
        self.assertEqual(on["entwickeln"]["schluessel_sha256"], hashlib.sha256(KEY.encode()).hexdigest())
        self.assertEqual(common.model_settings(self.cfg(an=False))["entwickeln"]["schluessel_sha256"], "")
        self.assertIn("entwickeln", common.SYNC_SECTIONS)

    def test_the_panel_never_writes_the_hash(self):
        """Only the command line sets it (speech-spark entwickeln schluessel): the panel's settings keep it."""
        import admin
        import berater_katalog
        self.assertIn(("entwickeln", "schluessel_sha256"), berater_katalog.NEVER_KEYS)
        self.assertIn(("chat", "entwickeln"), berater_katalog.NEVER_KEYS)
        with open(admin.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('("entwickeln", ("schluessel_sha256",))', src)

    def test_a_fixed_stage_never_ages(self):
        g = common.PrioGate(1, age=1)
        self.assertEqual(g._rank([common.STAGE_LOW, 0, 7, None, {}, True], 10_000), (common.STAGE_LOW, -7))
        self.assertGreater(g._rank([common.STAGE_LOW, 0, 7, None, {}, False], 10_000)[0], common.STAGE_LOW)


class Tor(unittest.TestCase):
    """The LLM-Tor with the developer key: chat and the model list, always stage "hinten", its own gate; never
    System One; nothing while the switch is off."""

    def setUp(self):
        import llm_tor
        from fastapi.testclient import TestClient
        self.t = llm_tor
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            self.saved = json.load(f)
        c = copy.deepcopy(self.saved)
        c["llm"] = dict(c.get("llm", {}), modell="qwen38-27b-nvfp4", engine_port=31016)
        c["chat"]["entwickeln"] = True
        c["entwickeln"] = {"schluessel_sha256": hashlib.sha256(KEY.encode()).hexdigest()}
        helpers.write_config(c)
        self.addCleanup(helpers.write_config, self.saved)
        self.got = []

        def engine(request):
            if request.url.path == "/health":
                return httpx.Response(200, text="")
            self.got.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}],
                                             "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
        old = llm_tor.client
        llm_tor.client = httpx.AsyncClient(transport=httpx.MockTransport(engine))
        self.addCleanup(setattr, llm_tor, "client", old)
        self.stages = []
        test = self

        class Spy(common.PrioGate):
            async def enter(self, stage=common.STAGE_NORMAL, fest=False):
                test.stages.append((stage, fest))
                return await super().enter(stage, fest)
        llm_tor.gate = Spy(4)
        llm_tor.entwickler_tor = None
        self.addCleanup(setattr, llm_tor, "gate", None)
        self.addCleanup(setattr, llm_tor, "entwickler_tor", None)
        self.app = TestClient(llm_tor.app)

    def test_the_developer_key_is_last_in_line(self):
        dev = {"Authorization": "Bearer " + KEY, "X-Speech-Stufe": "2"}
        before = self.t.stats["entwickler"]
        with redirect_stdout(io.StringIO()) as out:
            r = self.app.post("/v1/chat/completions", headers=dev, json={"messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.stages[-1], (common.STAGE_LOW, True), "a header asking for more never counts")
        self.assertEqual(self.t.stats["entwickler"], before + 1)
        self.assertEqual(self.t.entwickler_tor.slots, common.ENTWICKLER_PLAETZE)
        self.assertEqual(self.t.entwickler_tor.age, 0)
        self.assertTrue(all(x.startswith("llmtor: ") for x in out.getvalue().splitlines()))
        self.assertEqual(self.app.get("/v1/models", headers=dev).status_code, 200)
        self.assertEqual(self.app.post("/v1/systemone", headers=dev, json={}).status_code, 401, "only chat and models")

    def test_a_full_developer_gate_says_busy(self):
        g = self.t._entwickler_gate()
        g.most = 0

        async def belegen():
            return await g.enter(common.STAGE_LOW, fest=True)
        asyncio.run(belegen())
        with redirect_stdout(io.StringIO()) as out:
            r = self.app.post("/v1/chat/completions", headers={"Authorization": "Bearer " + KEY},
                              json={"messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(r.status_code, 503)
        self.assertIn("llmtor: abgelehnt voll entwickler", out.getvalue())
        self.assertEqual(self.got, [])

    def test_nothing_while_the_switch_is_off(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["chat"]["entwickeln"] = False
        helpers.write_config(c)
        r = self.app.post("/v1/chat/completions", headers={"Authorization": "Bearer " + KEY},
                          json={"messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.got, [])


class Skripte(unittest.TestCase):
    """update.sh, install.sh and the command line (read as text: they run as root on the Pi only)."""

    def test_an_update_never_loses_local_work(self):
        s = helpers.repo_file("update.sh")
        self.assertIn('lokal aufsetzen "$new"', s, "local commits go along onto the new main")
        self.assertLess(s.index("SIGNERS="), s.index('lokal aufsetzen "$new"'), "main's checks first")
        self.assertLess(s.index('git diff HEAD -- >"$kept"'), s.index('git reset --hard --quiet "$inst"'),
                        "uncommitted edits are kept as a patch before the reset")
        self.assertNotIn('git reset --hard --quiet "$new"', s)
        self.assertIn('stop_early "$(printf', s, "a conflict or a red test keeps the running version")
        self.assertIn("never upstream code", s)
        self.assertIn("vouch only for main", s)

    def test_local_code_never_runs_as_root(self):
        s = helpers.repo_file("update.sh")
        self.assertIn('LOKAL_ENV=(SPEECH_SPARK_NO_SELFTEST=1 SPEECH_SPARK_LOKAL_BASIS="$new"', s,
                      "install.sh's self-test runs as root: with local commits the sandbox's quick test ran instead")
        self.assertIn('/usr/bin/python3 -I "$ENTW" vorbereiten', s, "the installed entwickeln.py, never the candidate's")
        i = helpers.repo_file("install.sh")
        self.assertIn('grep -q \'"lokal_kopf"\'', i, "speech-spark-bench imports panel modules: as the service user then")
        self.assertIn('if [ "${SPEECH_SPARK_NO_SELFTEST:-0}" = 1 ]; then', i)

    def test_spark_dev_has_no_privileges_and_only_the_tor(self):
        i = helpers.repo_file("install.sh")
        self.assertIn("passwd -l spark-dev", i)
        self.assertIn('for grp in sudo adm wheel root "$SVC_USER"; do', i)
        self.assertNotRegex(i, r"sudoers[^\n]*spark-dev|spark-dev[^\n]*NOPASSWD")
        self.assertIn('echo "    meta skuid \\"spark-dev\\" reject"', i)
        self.assertIn('[ "\\$(id -un)" = spark-dev ]', i, "spark-opencode only as spark-dev")
        self.assertIn('opencode_holen "$PREFIX/opencode"', i, "the same pinned download as the Werkstatt's")
        body = i[i.index("opencode_holen() {"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("hashlib.sha512", body)
        self.assertIn('[ "$got" = "$OC_SHA" ] || {', body, "a download that does not match its pinned hash stops")
        self.assertNotIn("/var/lib/speech-spark ", i[i.index("Entwickeln auf dem Pi: user spark-dev"):][:4000])

    def test_the_command_line(self):
        with open(os.path.join(APP, "speech-spark.sh"), encoding="utf-8") as f:
            s = f.read()
        for cmd in ("lokal) shift; cmd_lokal", "entwickeln) shift; cmd_entwickeln", "need_root lokal \"$1\"",
                    "printf '%s' \"$art\" | runuser -u \"$(panel_user)\" -- tee \"$VAR/state/update-lokal\""):
            self.assertIn(cmd, s)
        top = s.split("set -euo pipefail")[0]
        help_lines = int(re.search(r"sed -n '2,(\d+)p' \"\$0\"", s).group(1))
        self.assertEqual(help_lines, len(top.splitlines()), "the help shows every line of the header")
        self.assertIn("speech-spark lokal einspielen", top)


class Seite(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import entwickelnseite
        import panel
        import update
        self.s = entwickelnseite
        self.update = update
        helpers.keep_chat(self, "entwickeln")
        self.tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for name, value in (("WUNSCH", os.path.join(self.tmp, "update-lokal")), ("ANZEIGE", os.path.join(self.tmp, "e.json"))):
            p = mock.patch.object(entwickeln, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.anon = TestClient(panel.app)
        self.admin = TestClient(panel.app)
        self.admin.post("/api/login", json={"password": "secret-admin"})

    def test_admin_only_and_off_by_default(self):
        import features
        self.assertNotIn("entwickeln", features.DEFAULT_ON)
        with open(os.path.join(APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["entwickeln"], False)
        for m, path in (("get", "/api/admin/entwickeln"), ("post", "/api/admin/entwickeln/einspielen"),
                        ("post", "/api/admin/entwickeln/zurueck"), ("post", "/api/admin/entwickeln/verwerfen")):
            self.assertIn(getattr(self.anon, m)(path).status_code, (401, 403), path)
        helpers.set_config(entwickeln=False)
        out = io.StringIO()
        with redirect_stdout(out):
            r = self.admin.post("/api/admin/entwickeln/einspielen")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertFalse(os.path.exists(entwickeln.WUNSCH))
        self.assertIn("entwickeln: einspielen abgelehnt aus", out.getvalue())

    def test_the_levels_of_the_code(self):
        import stufen
        self.assertEqual(stufen.LIST[("POST", "/api/admin/entwickeln/einspielen")][0], stufen.PROTECT)
        for p in ("zurueck", "verwerfen"):
            self.assertEqual(stufen.LIST[("POST", f"/api/admin/entwickeln/{p}")][0], stufen.CONFIRM)

    def test_a_wish_is_one_fixed_word_and_starts_the_update(self):
        helpers.set_config(entwickeln=True)
        out = io.StringIO()
        with mock.patch.object(self.update, "begin", return_value={"ok": True}) as begin, redirect_stdout(out):
            r = self.admin.post("/api/admin/entwickeln/zurueck", json={"art": "einspielen; rm -rf /"})
        self.assertEqual(r.status_code, 200, r.text)
        begin.assert_called_once_with("before-update", "")
        with open(entwickeln.WUNSCH) as f:
            self.assertEqual(f.read(), "zurueck", "the body never reaches the wish")
        self.assertIn("entwickeln: zurueck gestartet", out.getvalue())
        from fastapi import HTTPException
        with mock.patch.object(self.update, "begin", side_effect=HTTPException(409, "x")), redirect_stdout(out):
            self.assertEqual(self.admin.post("/api/admin/entwickeln/verwerfen").status_code, 409)
        self.assertFalse(os.path.exists(entwickeln.WUNSCH), "a wish without its update goes again")
        self.assertIn("entwickeln: verwerfen abgelehnt start", out.getvalue())
        d = self.admin.get("/api/admin/entwickeln").json()
        self.assertTrue(d["an"])

    def test_live_and_the_hint_hold_no_content(self):
        helpers.set_config(entwickeln=True)
        with open(entwickeln.ANZEIGE, "w") as f:
            json.dump({"anzahl": 2, "offen": 1, "basis": "abcdef1", "kopf": "1234567", "vorher": True,
                       "letzter": {"art": "aufsetzen", "ergebnis": "tests", "t": 1000, "rot": ["test_live.A.b"], "module": 3},
                       "text": "Commit-Text"}, f)
        v = self.s.for_live()
        self.assertEqual(v, {"on": True, "anzahl": 2, "offen": 1, "letzter": "tests", "art": "aufsetzen"})
        sub = self.s.live_sub(v)
        self.assertEqual(sub, "lokale Änderungen: 2 · 1 im Klon noch nicht eingespielt · zuletzt Update mit lokalen Änderungen abgelehnt: tests")
        a = self.s.alerts(now=1000 + 60)
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["kind"], a[0]["level"], a[0]["go"]), ("entwickeln", "warn", "Einstellungen → Update"))
        self.assertIn("test_live.A.b", a[0]["text"])
        self.assertNotIn("Commit-Text", json.dumps(a) + sub)
        self.assertEqual(self.s.alerts(now=1000 + self.s.HINWEIS_S + 1), [], "the hint goes after its days")
        helpers.set_config(entwickeln=False)
        self.assertEqual(self.s.for_live(), {"on": False})
        self.assertEqual(self.s.alerts(now=1060), [])

    def test_registered_everywhere(self):
        import dateien
        import features
        import guard
        import live
        import logfilter
        import rechnerblick
        import technik
        f = {x.key: x for x in features.FEATURES}["entwickeln"]
        self.assertEqual((f.admin, f.group, f.guide), (("entwickeln",), "sec", "entwickeln"))
        self.assertIn("entwickeln", features.SPARK_ONLY)
        self.assertIn("entwickeln", features.DESK_SKIP)
        self.assertIn("entwickeln", live.TARGETS)
        self.assertTrue(any(re.match(rx, "entwickeln: einspielen gestartet") for _k, rx in logfilter.AREAS))
        self.assertIn("entwickeln_lokal", guard.LIVE_WORDS)
        self.assertEqual((guard.RATE["entwickeln"], guard.RATE["entwickeln_einspielen"]), ((0, 60), (0, 6)), "never for guests")
        self.assertTrue({"entwickeln.json", "update-lokal"} <= {d.name for d in dateien.DATEIEN})
        self.assertIn("lokaltest", rechnerblick.DIENST_NAMEN)
        self.assertIn("entwickeln", technik.MODULE)
        self.assertIn("entwickelnseite", technik.MODULE)


if __name__ == "__main__":
    unittest.main()
