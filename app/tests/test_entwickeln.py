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
        self.assertEqual((a[0]["kind"], a[0]["level"], a[0]["go"]), ("entwickeln", "warn", "Zustand → Werkstatt → Entwickeln"))
        self.assertIn("Weiter unter Zustand → Werkstatt → Entwickeln", a[0]["text"], "the hint points to the page (package 3)")
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



# ---------------------------------------------------------------- Weg A: an GitHub geben (package 2)
class GitHubRegeln(unittest.TestCase):
    """The fixed rules of An GitHub geben: only opencode/<thema> from a fixed charset, never main, never forced, never
    .github, only GitHub's pinned host key, the deploy key root's own and never in a log, offline it waits."""

    def test_the_topic_is_a_fixed_charset(self):
        for roh, gut in (("Live-Übersicht", "live-uebersicht"), ("  Größe; rm -rf /  ", "groesse-rm-rf"),
                         ("opencode/abc", "abc"), ("a" * 80, "a" * 40), ("--x--", "x"), ("../../main", "main"),
                         ("refs/heads/main", "refs-heads-main"), ("lokal", "lokal")):
            self.assertEqual(entwickeln.thema_pruefen(roh), gut, roh)
        for roh in ("", None, "../..", "///", "äöü"[:0], "-"):
            self.assertEqual(entwickeln.thema_pruefen(roh), "", roh)
        self.assertTrue(all(entwickeln.THEMA.fullmatch(entwickeln.thema_pruefen(x)) for x in ("ÄÖÜ ß", "x y z", "1")))

    def test_a_push_only_ever_writes_opencode(self):
        """Every topic the charset allows ends below refs/heads/opencode/; anything else is refused before git."""
        self.assertEqual(entwickeln.ziel_ref("main"), "refs/heads/opencode/main", "never refs/heads/main")
        for t in ("abc", "x-1", "a" * 40):
            self.assertTrue(entwickeln.ziel_ref(t).startswith("refs/heads/opencode/"), t)
        for t in ("", "Main", "a/b", "../main", "x" * 41, "-x", "a b", None, "main\n"):
            with self.assertRaises(entwickeln.Fehler, msg=repr(t)) as e:
                entwickeln.ziel_ref(t)
            self.assertEqual(str(e.exception), "thema")

    def test_only_a_github_repository(self):
        url, repo = entwickeln.github_ziel("https://github.com/db9979/speech-on-dgx-spark")
        self.assertEqual((url, repo), ("ssh://git@ssh.github.com:443/db9979/speech-on-dgx-spark.git", "db9979/speech-on-dgx-spark"))
        self.assertEqual(entwickeln.github_ziel("git@github.com:db9979/speech-on-dgx-spark.git")[1], "db9979/speech-on-dgx-spark")
        for boese in ("https://github.com.evil.example/x/y", "https://evil.example/github.com/x/y", "http://github.com/x/y",
                      "https://github.com/x", "https://github.com/x/y/z", "https://github.com/../..", "file:///root/x", "", None):
            self.assertEqual(entwickeln.github_ziel(boese), ("", ""), boese)

    def test_never_the_workflows_a_link_or_a_submodule(self):
        """Weg A takes what Weg B never takes (a Claude thread reviews it), but never what GitHub runs with its token."""
        ok = [("100644", "100755", "M", "install.sh"), ("100644", "100644", "M", "app/common.py"),
              ("000000", "100644", "A", "app/neu.py"), ("100644", "000000", "D", "docs/alt.md")]
        self.assertEqual(entwickeln.pfade_github(raw(*ok)), ["install.sh", "app/common.py", "app/neu.py", "docs/alt.md"])
        for eintrag in (("100644", "100644", "M", ".github/workflows/tests.yml"), ("000000", "100644", "A", ".github/x"),
                        ("100644", "000000", "D", ".github/workflows/tests.yml"), ("100644", "120000", "M", "app/x.py"),
                        ("000000", "160000", "A", "sub"), ("100644", "100644", "M", "app/.git/config"),
                        ("100644", "100644", "M", "app/../x"), ("100644", "100644", "M", "x" * 201)):
            with self.assertRaises(entwickeln.Fehler, msg=eintrag) as e:
                entwickeln.pfade_github(raw(eintrag))
            self.assertEqual(str(e.exception), "pfad", eintrag)
        viele = [("100644", "100644", "M", f"docs/{i}.md") for i in range(entwickeln.DATEIEN_MAX + 1)]
        with self.assertRaises(entwickeln.Fehler) as e:
            entwickeln.pfade_github(raw(*viele))
        self.assertEqual(str(e.exception), "zu_viele")

    def test_gits_answer_becomes_one_fixed_word(self):
        for text, wort in (("ssh: Could not resolve hostname ssh.github.com: Temporary failure in name resolution", "wartet"),
                           ("ssh: connect to host ssh.github.com port 443: Connection timed out", "wartet"),
                           ("ssh: connect to host ssh.github.com port 443: Network is unreachable", "wartet"),
                           ("git@ssh.github.com: Permission denied (publickey).\nfatal: Could not read from remote repository.", "schluessel"),
                           ("ERROR: The key you are authenticating with has been marked as read only.", "schluessel"),
                           ("Host key verification failed.", "hostschluessel"),
                           (" ! [rejected] refs/spark/github -> opencode/x (fetch first)", "nicht_vorwaerts"),
                           (" ! [rejected] refs/spark/github -> opencode/x (non-fast-forward)", "nicht_vorwaerts"),
                           ("remote: error: GH013: Repository rule violations found for refs/heads/opencode/x.", "abgelehnt"),
                           (" ! [remote rejected] x -> opencode/x (protected branch hook declined)", "abgelehnt"),
                           ("irgendwas anderes", "fehler"), ("", "fehler"), (None, "fehler")):
            self.assertEqual(entwickeln.push_grund(text), wort, text)
        for k, (de, en) in entwickeln.GH_GRUENDE.items():
            self.assertTrue(re.fullmatch(r"[a-z_]+", k) and de and en, k)

    def test_ssh_takes_only_this_key_and_githubs_pinned_host_key(self):
        cmd = entwickeln.ssh_befehl("/tmp/x/key", "/tmp/x/known_hosts").split()
        self.assertEqual(cmd[:3], ["ssh", "-F", "/dev/null"], "no ssh config of root's")
        for opt in ("IdentitiesOnly=yes", "IdentityAgent=none", "BatchMode=yes", "StrictHostKeyChecking=yes",
                    "UserKnownHostsFile=/tmp/x/known_hosts", "GlobalKnownHostsFile=/dev/null", "ProxyCommand=none",
                    "PermitLocalCommand=no", "UpdateHostKeys=no"):
            self.assertIn(opt, cmd)
        host, art, blob = entwickeln.GH_HOSTKEY.split()
        self.assertEqual((host, art), ("[ssh.github.com]:443", "ssh-ed25519"))
        import base64
        fp = base64.b64encode(hashlib.sha256(base64.b64decode(blob)).digest()).decode().rstrip("=")
        self.assertEqual(fp, "+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU", "GitHub's published fingerprint")

    def test_the_deploy_key_is_roots_own_file_or_nothing_goes(self):
        tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, tmp, True)
        key = os.path.join(tmp, "key")
        with open(key, "w") as f:
            f.write("-----BEGIN OPENSSH PRIVATE KEY-----\nx\n")
        os.chmod(key, 0o600)
        me = os.getuid()
        self.assertTrue(entwickeln.schluessel_datei_ok(key, uid=me))
        self.assertFalse(entwickeln.schluessel_datei_ok(key, uid=me + 1), "another owner")
        os.chmod(key, 0o640)
        self.assertFalse(entwickeln.schluessel_datei_ok(key, uid=me), "readable by the group")
        os.chmod(key, 0o600)
        link = os.path.join(tmp, "link")
        os.symlink(key, link)
        self.assertFalse(entwickeln.schluessel_datei_ok(link, uid=me), "a link")
        self.assertFalse(entwickeln.schluessel_datei_ok(tmp, uid=me), "a folder")
        self.assertFalse(entwickeln.schluessel_datei_ok(os.path.join(tmp, "fehlt"), uid=me))
        self.assertEqual(entwickeln.GH_KEY, "/etc/speech-spark-github-key", "root's own, never in spark-dev's home")
        self.assertFalse(entwickeln.GH_KEY.startswith(entwickeln.HOME))

    def test_githubs_tests_only_for_this_branch_and_head(self):
        k = "c" * 40
        runs = [{"head_branch": "main", "head_sha": k, "status": "completed", "conclusion": "success"},
                {"head_branch": "opencode/x", "head_sha": k, "status": "completed", "conclusion": "cancelled"},
                {"head_branch": "opencode/x", "head_sha": k, "status": "completed", "conclusion": "failure"}]
        self.assertEqual(entwickeln.tests_zustand(runs, "opencode/x", k), "rot", "a run of main never counts")
        self.assertEqual(entwickeln.tests_zustand(runs[:2], "opencode/x", k), "unbekannt", "cancelled says nothing")
        self.assertEqual(entwickeln.tests_zustand([dict(runs[2], status="in_progress", conclusion=None)], "opencode/x", k), "laeuft")
        self.assertEqual(entwickeln.tests_zustand([dict(runs[2], conclusion="success")], "opencode/x", k), "gruen")
        self.assertEqual(entwickeln.tests_zustand([dict(runs[2], conclusion="success")], "opencode/x", "d" * 40), "unbekannt")
        for kaputt in (None, {}, "x", [None, 5]):
            self.assertEqual(entwickeln.tests_zustand(kaputt, "opencode/x", k), "unbekannt")
        self.assertEqual(set(entwickeln.GH_TESTS), {"gruen", "laeuft", "rot", "unbekannt"})

    def test_the_hint_for_dominik(self):
        de, en = entwickeln.hinweis("opencode/x", "db9979/speech-on-dgx-spark")
        self.assertEqual(de, "Gib den Zweig opencode/x einem Claude-Thread zum Prüfen: "
                             "https://github.com/db9979/speech-on-dgx-spark/tree/opencode/x")
        self.assertIn("Claude thread", en)

    def test_the_panels_copy_holds_branches_and_fixed_words(self):
        k = "c" * 40
        d = entwickeln.github_anzeige({}, "gegeben", {"zweig": "opencode/x", "kopf": k, "anzahl": 2, "t": 5, "text": "geheim"}, "x", now=9)
        self.assertEqual(d, {"zweige": [{"zweig": "opencode/x", "kopf": k, "anzahl": 2, "t": 5}],
                             "letzter": {"zustand": "gegeben", "t": 9, "zweig": "opencode/x"}})
        alt = {"zweige": [{"zweig": "main", "kopf": k}, {"zweig": "opencode/a", "kopf": "Commit-Text"},
                          *[{"zweig": f"opencode/z{i}", "kopf": k, "anzahl": 1, "t": i} for i in range(12)]]}
        d = entwickeln.github_anzeige(alt, "kaputt; rm", {"zweig": "opencode/z3", "kopf": "d" * 40, "anzahl": 1, "t": 1}, "../x", now=1)
        self.assertEqual(len(d["zweige"]), entwickeln.GH_ZWEIGE_MAX)
        self.assertEqual(d["zweige"][0]["kopf"], "d" * 40, "the same branch again: newest first, once")
        self.assertEqual([z["zweig"] for z in d["zweige"]].count("opencode/z3"), 1)
        self.assertNotIn("main", [z["zweig"] for z in d["zweige"]])
        self.assertEqual(d["letzter"], {"zustand": "fehler", "t": 1})
        tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, tmp, True)
        p = os.path.join(tmp, "g.json")
        with open(p, "w") as f:
            json.dump({"zweige": [{"zweig": "opencode/x", "kopf": k, "anzahl": True, "t": "x", "text": "geheim"},
                                  {"zweig": "opencode/../main", "kopf": k}],
                       "letzter": {"zustand": "gegeben", "t": 3, "zweig": "main", "text": "geheim"}}, f)
        back = entwickeln.github_anzeige_lesen(p)
        self.assertEqual(back, {"zweige": [{"zweig": "opencode/x", "kopf": k, "anzahl": 0, "t": 0}],
                                "letzter": {"zustand": "gegeben", "t": 3}})
        self.assertEqual(entwickeln.github_anzeige_lesen(os.path.join(tmp, "fehlt.json")), {"zweige": []})


class GitHubGeben(unittest.TestCase):
    """an_github and github_geben with git, runuser and systemctl replaced: what root would run."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.key = os.path.join(self.tmp, "github-key")
        with open(self.key, "w") as f:
            f.write("GEHEIMER-SCHLUESSEL")
        os.chmod(self.key, 0o600)
        self.calls = []
        self.push = (0, "")
        for name, wert in (("GH_KEY", self.key), ("_schalter_an", mock.Mock(return_value=True)),
                           ("schluessel_datei_ok", mock.Mock(return_value=True)), ("_update_laeuft", mock.Mock(return_value=False)),
                           ("_als_dev", mock.Mock(return_value=mock.Mock(returncode=0, stderr=b""))),
                           ("_git", self.git), ("_als_svc", mock.Mock(return_value=mock.Mock(returncode=0, stdout=b"")))):
            p = mock.patch.object(entwickeln, name, wert)
            p.start()
            self.addCleanup(p.stop)

    def git(self, *args, **kw):
        self.calls.append((args, kw))
        if args[:2] == ("remote", "get-url"):
            return 0, "https://github.com/db9979/speech-on-dgx-spark"
        if args[0] == "rev-parse":
            return 0, B
        if args[0] == "merge-base":
            return 0, A
        if args[0] == "rev-list":
            return 0, "2"
        if args[0] == "diff":
            return 0, raw(("100644", "100755", "M", "install.sh"))
        if args[0] == "push":
            return self.push
        return 0, ""

    def pushes(self):
        return [(a, kw) for a, kw in self.calls if a[0] == "push"]

    def test_the_push_never_writes_main_and_never_forces(self):
        r = entwickeln.an_github("mein-thema")
        self.assertEqual(r, {"zweig": "opencode/mein-thema", "kopf": B, "anzahl": 2, "repo": "db9979/speech-on-dgx-spark"})
        (args, kw), = self.pushes()
        self.assertEqual(args[-2:], ("ssh://git@ssh.github.com:443/db9979/speech-on-dgx-spark.git",
                                     f"{entwickeln.REF_GITHUB}:refs/heads/opencode/mein-thema"))
        self.assertFalse(any(a.startswith("+") or a in ("-f", "--force", "--force-with-lease", "--mirror", "--all",
                                                        "--tags", "--delete", "-d") for a in args), args)
        self.assertNotIn("main", " ".join(args[-1:]).replace("opencode/", ""))
        self.assertIn("StrictHostKeyChecking=yes", kw["env"]["GIT_SSH_COMMAND"])
        self.assertNotIn("GEHEIMER-SCHLUESSEL", json.dumps([list(a) for a, _ in self.calls]) + json.dumps([k for _, k in self.calls]),
                         "the key is a file of root's, never an argument or a variable")
        self.assertIn((("update-ref", "-d", entwickeln.REF_GITHUB), {}), self.calls, "the ref goes again")
        fetch = [a for a, _ in self.calls if a[0] == "fetch"][0]
        self.assertTrue(fetch[-1].endswith(":" + entwickeln.REF_GITHUB), "the bundle lands only in root's own ref")

    def test_a_branch_of_spark_devs_own_topic_or_lokal(self):
        dev = entwickeln._als_dev
        dev.side_effect = lambda *a, **k: mock.Mock(returncode=1 if a[-1] == "refs/heads/opencode/x" else 0, stderr=b"")
        entwickeln.an_github("x")
        bundle = [c.args for c in dev.call_args_list if "bundle" in c.args][0]
        self.assertEqual(bundle[bundle.index("create") + 2], "refs/heads/lokal")
        self.assertEqual(bundle[-2:], ("--not", "--remotes"))

    def test_nothing_while_the_switch_is_off(self):
        entwickeln._schalter_an.return_value = False
        with self.assertRaises(entwickeln.Fehler) as e:
            entwickeln.an_github("x")
        self.assertEqual(str(e.exception), "aus")
        entwickeln._schalter_an.assert_called_with("entwickeln_github")
        self.assertEqual(self.calls, [])

    def test_no_key_no_push_and_never_while_updating(self):
        entwickeln.schluessel_datei_ok.return_value = False
        with self.assertRaises(entwickeln.Fehler) as e:
            entwickeln.an_github("x")
        self.assertEqual(str(e.exception), "schluessel")
        entwickeln.schluessel_datei_ok.return_value = True
        entwickeln._update_laeuft.return_value = True
        with self.assertRaises(entwickeln.Fehler) as e:
            entwickeln.an_github("x")
        self.assertEqual(str(e.exception), "wartet")
        self.assertEqual(self.pushes(), [])

    def test_the_workflows_never_go(self):
        orig = self.git

        def git(*args, **kw):
            if args[0] == "diff":
                return 0, raw(("100644", "100644", "M", ".github/workflows/tests.yml"))
            return orig(*args, **kw)
        with mock.patch.object(entwickeln, "_git", git):
            with self.assertRaises(entwickeln.Fehler) as e:
                entwickeln.an_github("x")
        self.assertEqual(str(e.exception), "pfad")
        self.assertEqual(self.pushes(), [])

    def test_offline_it_waits_and_says_so_without_gits_text(self):
        self.push = (128, "ssh: Could not resolve hostname ssh.github.com GEHEIMER-SCHLUESSEL\nfatal: Could not read from remote repository.")
        out, err, said = io.StringIO(), io.StringIO(), []
        with redirect_stdout(out), mock.patch("sys.stderr", err):
            self.assertEqual(entwickeln.github_geben("x", log=said.append), 4)
        svc = [c.args for c in entwickeln._als_svc.call_args_list]
        self.assertIn(("tee", "--", entwickeln.GH_WUNSCH), svc, "the wish stays for the timer")
        self.assertNotIn(("rm", "-f", "--", entwickeln.GH_WUNSCH), svc)
        self.assertEqual(said, [entwickeln.GH_GRUENDE["wartet"][0]])
        self.assertIn("entwickeln: github wartet", err.getvalue())
        alles = out.getvalue() + err.getvalue() + json.dumps(said) + json.dumps([str(c) for c in entwickeln._als_svc.call_args_list])
        self.assertNotIn("GEHEIM", alles, "git's text never reaches a log, the panel or the screen")
        self.assertNotIn("resolve", alles)

    def test_a_refusal_drops_the_wish_and_success_gives_the_hint(self):
        self.push = (1, "remote: error: GH013: Repository rule violations found")
        err, said = io.StringIO(), []
        with mock.patch("sys.stderr", err):
            self.assertEqual(entwickeln.github_geben("x", log=said.append), 3)
        self.assertIn(("rm", "-f", "--", entwickeln.GH_WUNSCH), [c.args for c in entwickeln._als_svc.call_args_list])
        self.assertIn("entwickeln: github abgelehnt abgelehnt", err.getvalue())
        self.push = (0, "")
        said = []
        with mock.patch("sys.stderr", err):
            self.assertEqual(entwickeln.github_geben("x", log=said.append), 0)
        self.assertIn("entwickeln: github gegeben 2 commits", err.getvalue())
        self.assertEqual(said[-1], "Gib den Zweig opencode/x einem Claude-Thread zum Prüfen: "
                                   "https://github.com/db9979/speech-on-dgx-spark/tree/opencode/x")
        geschrieben = [c for c in entwickeln._als_svc.call_args_list if c.args[:3] == ("tee", "--", entwickeln.GH_ANZEIGE)][-1]
        d = json.loads(geschrieben.kwargs["eingabe"])
        self.assertEqual((d["letzter"]["zustand"], d["zweige"][0]["zweig"], d["zweige"][0]["kopf"]), ("gegeben", "opencode/x", B))

    def test_the_unit_takes_only_a_waiting_wish(self):
        said = []
        with mock.patch.object(entwickeln, "github_geben") as geben:
            self.assertEqual(entwickeln.cli(["an-github", "--wunsch"], log=said.append), 0)
            geben.assert_not_called()
            entwickeln._als_svc.return_value = mock.Mock(returncode=0, stdout="Größe; rm -rf /\n".encode())
            geben.return_value = 4
            self.assertEqual(entwickeln.cli(["an-github", "--wunsch"], log=said.append), 0, "offline is no failed unit")
            geben.assert_called_once_with("groesse-rm-rf", said.append)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(entwickeln.cli(["an-github", "///"], log=said.append), 2)
        self.assertEqual(buf.getvalue().strip(), "entwickeln: abgelehnt thema")


class Zusammengefuehrt(unittest.TestCase):
    """After the branch is on main, the next update drops the installed local commits that are in it (aufsetzen,
    git rebase --empty=drop): a real git repository in a temporary folder, nothing of the real one."""

    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("no git")
        self.tmp = tempfile.mkdtemp(prefix="entwickeln-git-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "src")
        os.makedirs(self.repo)
        p = mock.patch.object(entwickeln, "GIT_HOME", self.tmp)   # not /root: GitHub's runner is no root
        p.start()
        self.addCleanup(p.stop)
        self.g("init", "-q", "-b", "main")
        self.schreiben("app/panel/a.py", "eins\nzwei\ndrei\n")
        self.basis = self.commit("basis")

    def g(self, *args):
        return entwickeln._git(*args, cwd=self.repo, ident=True)[1]

    def schreiben(self, pfad, text):
        p = os.path.join(self.repo, pfad)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def commit(self, text):
        self.g("add", "-A")
        self.g("commit", "-q", "-m", text)
        return self.g("rev-parse", "HEAD")

    def test_merged_commits_drop_out(self):
        self.g("switch", "-q", "-c", "lokal")
        self.schreiben("app/panel/a.py", "eins\nZWEI\ndrei\n")
        lokal = self.commit("lokal: zwei groß")
        self.g("switch", "-q", "main")
        # what a Claude thread brings onto main: the same change, more in the same file, docs, another commit
        self.schreiben("app/panel/a.py", "eins\nZWEI\ndrei\nvier\n")
        self.schreiben("docs/de/x.md", "Doku\n")
        self.commit("V01.1.300 aus opencode/x, ergänzt")
        neu = self.commit_leer()
        ziel = os.path.join(self.tmp, "ziel")
        os.makedirs(ziel)
        with mock.patch.object(entwickeln, "QUELLE", self.repo):
            kopf, n = entwickeln.aufsetzen(neu, lokal, ziel)
        self.assertEqual((kopf, n), (neu, 0), "every local commit is in main now: the branch is empty again")
        # one that is not in main yet stays, on top of the new main
        self.g("switch", "-q", "lokal")
        self.schreiben("app/panel/b.py", "neu\n")
        noch = self.commit("lokal: noch nicht auf main")
        with mock.patch.object(entwickeln, "QUELLE", self.repo):
            kopf, n = entwickeln.aufsetzen(neu, noch, ziel)
        self.assertEqual(n, 1)
        self.assertEqual(self.g("rev-parse", f"{kopf}^"), neu)

    def commit_leer(self):
        self.g("commit", "-q", "--allow-empty", "-m", "noch einer")
        return self.g("rev-parse", "HEAD")


class GitHubSeite(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import entwickelnseite
        import panel
        self.s = entwickelnseite
        helpers.keep_chat(self, "entwickeln", "entwickeln_github")
        self.tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for name, value in (("GH_WUNSCH", os.path.join(self.tmp, "github-wunsch")), ("GH_ANZEIGE", os.path.join(self.tmp, "g.json")),
                            ("ANZEIGE", os.path.join(self.tmp, "e.json"))):
            p = mock.patch.object(entwickeln, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(entwickelnseite, "_repo", return_value="db9979/speech-on-dgx-spark")
        p.start()
        self.addCleanup(p.stop)
        entwickelnseite._tests.clear()
        self.anon = TestClient(panel.app)
        self.admin = TestClient(panel.app)
        self.admin.post("/api/login", json={"password": "secret-admin"})

    def test_admin_only_off_by_default_and_needs_entwickeln(self):
        import features
        self.assertNotIn("entwickelngithub", features.DEFAULT_ON)
        with open(os.path.join(APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["entwickeln_github"], False)
        for m, path in (("get", "/api/admin/entwickeln/github"), ("post", "/api/admin/entwickeln/github")):
            self.assertIn(getattr(self.anon, m)(path).status_code, (401, 403), path)
        import core
        for an in ((True, False), (False, True)):
            helpers.set_config(entwickeln=an[0], entwickeln_github=an[1])
            out = io.StringIO()
            with redirect_stdout(out), mock.patch.object(core, "run", side_effect=AssertionError("never started")):
                r = self.admin.post("/api/admin/entwickeln/github", json={"thema": "x"})
            self.assertEqual(r.status_code, 409, (an, r.text))
            self.assertFalse(os.path.exists(entwickeln.GH_WUNSCH))
            self.assertIn("entwickeln: github abgelehnt aus", out.getvalue())

    def test_the_wish_is_a_checked_topic_and_starts_roots_unit(self):
        import core
        helpers.set_config(entwickeln=True, entwickeln_github=True)
        out = io.StringIO()
        with mock.patch.object(core, "run", return_value=(0, "")) as run, redirect_stdout(out):
            r = self.admin.post("/api/admin/entwickeln/github", json={"thema": "Größe; rm -rf / && git push origin main"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["zweig"], "opencode/groesse-rm-rf-git-push-origin-main")
        run.assert_called_once_with(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "speech-spark-github"], timeout=20)
        with open(entwickeln.GH_WUNSCH) as f:
            self.assertEqual(f.read(), "groesse-rm-rf-git-push-origin-main")
        self.assertIn("entwickeln: github gestartet", out.getvalue())
        self.assertIn("Gib den Zweig opencode/groesse-rm-rf-git-push-origin-main einem Claude-Thread zum Prüfen", r.json()["hinweis"][0])
        with redirect_stdout(out):
            r = self.admin.post("/api/admin/entwickeln/github", json={"thema": "///"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("entwickeln: github abgelehnt thema", out.getvalue())
        os.remove(entwickeln.GH_WUNSCH)
        with mock.patch.object(core, "run", return_value=(1, "sudo: a password is required")), redirect_stdout(out):
            r = self.admin.post("/api/admin/entwickeln/github", json={})
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("sudo:", r.text)
        self.assertFalse(os.path.exists(entwickeln.GH_WUNSCH), "a wish without its unit goes again")
        self.assertIn("entwickeln: github abgelehnt start", out.getvalue())
        r = self.admin.post("/api/admin/entwickeln/github", content=b"x" * 2000, headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_the_state_with_githubs_tests_and_the_hint(self):
        import update
        helpers.set_config(entwickeln=True, entwickeln_github=True)
        k = "c" * 40
        with open(entwickeln.GH_ANZEIGE, "w") as f:
            json.dump(entwickeln.github_anzeige({}, "gegeben", {"zweig": "opencode/x", "kopf": k, "anzahl": 2, "t": 5}, "x", now=7), f)
        runs = [{"head_branch": "opencode/x", "head_sha": k, "status": "completed", "conclusion": "success"}]

        async def gruen(repo, branch, passed=False):
            self.assertEqual((repo, branch), ("db9979/speech-on-dgx-spark", "opencode/x"))
            return runs
        with mock.patch.object(update, "green_runs", side_effect=gruen) as g:
            d = self.admin.get("/api/admin/entwickeln/github").json()
            self.admin.get("/api/admin/entwickeln/github")
        self.assertEqual(g.call_count, 1, "GitHub is asked at most every TESTS_S per branch")
        self.assertEqual(d["zweige"], [{"zweig": "opencode/x", "kopf": k[:7], "anzahl": 2, "t": 5, "tests": "gruen",
                                        "link": "https://github.com/db9979/speech-on-dgx-spark/tree/opencode/x"}])
        self.assertTrue(d["an"])
        self.assertFalse(d["wartet"])
        self.assertEqual(d["letzter"]["zustand"], "gegeben")
        self.assertTrue(d["hinweis"][0].startswith("Gib den Zweig opencode/x einem Claude-Thread zum Prüfen"))
        self.s._tests.clear()
        with mock.patch.object(update, "green_runs", side_effect=update.GitHubRefused(403, 99)), redirect_stdout(io.StringIO()) as out:
            d = self.admin.get("/api/admin/entwickeln/github").json()
        self.assertEqual(d["zweige"][0]["tests"], "unbekannt")
        self.assertIn("entwickeln: github tests unbekannt GitHubRefused", out.getvalue())

    def test_live_and_the_hints_hold_no_content(self):
        helpers.set_config(entwickeln=True, entwickeln_github=True)
        k = "c" * 40
        with open(entwickeln.GH_ANZEIGE, "w") as f:
            json.dump(entwickeln.github_anzeige({}, "gegeben", {"zweig": "opencode/x", "kopf": k, "anzahl": 2, "t": 5}, "x", now=1000), f)
        v = self.s.for_live()
        self.assertEqual((v["github"], v["gegeben"]), ("gegeben", 1))
        self.assertIn("an GitHub gegeben: 1", self.s.live_sub(v))
        a = [x for x in self.s.alerts(now=1060) if x["kind"] == "entwickeln_github"]
        self.assertEqual((a[0]["level"], a[0]["go"]), ("info", "Zustand → Werkstatt → Entwickeln"))
        self.assertIn("Gib den Zweig opencode/x einem Claude-Thread zum Prüfen", a[0]["text"])
        self.assertEqual([x for x in self.s.alerts(now=1000 + self.s.HINWEIS_S + 1) if x["kind"] == "entwickeln_github"], [])
        for zustand, n in (("wartet", 0), ("schluessel", 1)):
            with open(entwickeln.GH_ANZEIGE, "w") as f:
                json.dump(entwickeln.github_anzeige({}, zustand, None, "x", now=1000), f)
            a = [x for x in self.s.alerts(now=1060) if x["kind"] == "entwickeln_github"]
            self.assertEqual(len(a), n, zustand)
        self.assertEqual(a[0]["level"], "warn")
        self.assertIn(entwickeln.GH_GRUENDE["schluessel"][0], a[0]["text"])
        self.assertIn("an GitHub zuletzt: schluessel", self.s.live_sub(self.s.for_live()))
        helpers.set_config(entwickeln=True, entwickeln_github=False)
        self.assertNotIn("github", self.s.for_live())
        self.assertEqual([x for x in self.s.alerts(now=1060) if x["kind"] == "entwickeln_github"], [])

    def test_registered_everywhere(self):
        import berater_katalog
        import dateien
        import features
        import guard
        import rechnerblick
        import stufen
        f = {x.key: x for x in features.FEATURES}["entwickelngithub"]
        self.assertEqual((f.admin, f.group, f.parent, f.guide), (("entwickeln_github",), "sec", "entwickeln", "entwickelngithub"))
        self.assertIn("entwickelngithub", features.SPARK_ONLY)
        self.assertEqual(stufen.LIST[("POST", "/api/admin/entwickeln/github")][0], stufen.PROTECT)
        self.assertEqual(guard.RATE["entwickeln_github"], (0, 6), "never for guests")
        self.assertIn("entwickeln_github", guard.LIVE_WORDS)
        self.assertIn(("chat", "entwickeln_github"), berater_katalog.NEVER_KEYS)
        self.assertTrue({"github-wunsch", "entwickeln-github.json"} <= {d.name for d in dateien.DATEIEN})
        self.assertIn("github", rechnerblick.DIENST_NAMEN)


class GitHubSkripte(unittest.TestCase):
    def test_githubs_tests_run_on_opencode_branches_and_the_pi_only_looks_at_main(self):
        p = os.path.join(ROOT, ".github", "workflows", "tests.yml")
        if os.path.isfile(p):   # a copy with app/ only has no workflows
            with open(p) as f:
                wf = f.read()
            self.assertIn("branches: [main, 'opencode/**']", wf)
            self.assertIn("cancel-in-progress: false", wf)
            self.assertIn("github.ref == 'refs/heads/main'", wf, "the notes main rot / Wackelnde Tests only from main")
        u = helpers.repo_file("update.sh")
        self.assertIn("\nBRANCH=main\n", u, "the Pi installs only from main")
        self.assertIn('runs?branch=$BRANCH&event=push', u)
        self.assertIn('select(.head_branch == $b and .conclusion == "success")', u, "a green opencode/ run never counts")
        vp = os.path.join(ROOT, "tools", "vorpush.py")
        if os.path.isfile(vp):
            with open(vp) as f:
                self.assertIn("runs?branch=main&event=push", f.read())

    def test_spark_dev_stays_off_the_internet(self):
        i = helpers.repo_file("install.sh")
        teil = i[i.index('echo "table inet speech_spark_entwickeln {"'):]
        teil = teil[:teil.index('} >"$(dirname "$ETC")/speech-spark-entwickeln.nft"')]
        self.assertNotIn("443", teil, "spark-dev never gets https: root pushes")
        self.assertNotIn("22", teil.replace("32768", ""))
        unit = i[i.index("cat >/etc/systemd/system/speech-spark-github.service"):]
        unit = unit[:unit.index("\nEOF\n")]
        for z in ("MemoryMax=", "PrivateTmp=yes", "ProtectSystem=full", "NoNewPrivileges=yes", "lokal an-github --wunsch"):
            self.assertIn(z, unit)
        self.assertIn("printf ', /usr/bin/systemctl start --no-block speech-spark-github'", i)
        self.assertNotRegex(i, r"sudoers[^\n]*spark-dev|spark-dev[^\n]*NOPASSWD")

    def test_the_command_line(self):
        with open(os.path.join(APP, "speech-spark.sh"), encoding="utf-8") as f:
            s = f.read()
        for z in ("an-github)", "need_root lokal an-github", "zweige) need_root lokal zweige", "github-schluessel)",
                  "local gk=/etc/speech-spark-github-key", "( umask 077; ssh-keygen -q -t ed25519", 'chmod 600 "$gk"',
                  "-u speech-spark-github"):
            self.assertIn(z, s)
        top = s.split("set -euo pipefail")[0]
        self.assertIn("speech-spark lokal an-github", top)
        self.assertIn("speech-spark entwickeln github-schluessel", top)


# ---------------------------------------------------------------- package 3: the page and its terminal
class SeiteDrei(unittest.TestCase):
    """Zustand → Werkstatt → Entwickeln (package 3): the local commits with their titles only on the admin page (never in
    Live or a hint), every hint points to the page, the root side builds the terminal's unit from fixed values."""

    def test_commit_titles_are_parsed_as_data(self):
        raw = ("\x1eabc1234\x1fKalender: Begrüßung angepasst\n\n2\t1\tapp/panel/a.py\n5\t0\tdocs/de/b.md\n"
               "\x1edef5678\x1fHilfe \x1b[31mrot\x07 <b>fett</b>\n-\t-\tapp/panel/static/x.png\n"
               "\x1exyz\x1fkein Commit\n")
        c = entwickeln.commits_parsen(raw)
        self.assertEqual(len(c), 2, "a line without a short commit is dropped")
        self.assertEqual(c[0], {"kurz": "abc1234", "titel": "Kalender: Begrüßung angepasst", "dateien": 2, "plus": 7, "minus": 1})
        self.assertNotIn("\x1b", c[1]["titel"])
        self.assertNotIn("\x07", c[1]["titel"])
        self.assertEqual(c[1]["dateien"], 1)
        lang = "".join(f"\x1e{i:07x}\x1f{'x' * 300}\n" for i in range(50))
        c = entwickeln.commits_parsen(lang)
        self.assertEqual(len(c), entwickeln.COMMITS_MAX)
        self.assertEqual(len(c[0]["titel"]), entwickeln.TITEL_MAX)

    def test_the_copy_checks_titles_again_and_live_never_shows_one(self):
        import entwickelnseite
        helpers.keep_chat(self, "entwickeln")
        helpers.set_config(entwickeln=True)
        tmp = tempfile.mkdtemp(prefix="entwickeln-")
        self.addCleanup(shutil.rmtree, tmp, True)
        pfad = os.path.join(tmp, "e.json")
        d = entwickeln.anzeige({}, None, 0, now=5, commits=[{"kurz": "abc1234", "titel": "Geheimer Titel\x1b", "dateien": 1, "plus": 2, "minus": 3},
                                                           {"kurz": "nicht-hex", "titel": "x"}, "kaputt"])
        self.assertEqual(d["commits"], [{"kurz": "abc1234", "titel": "Geheimer Titel", "dateien": 1, "plus": 2, "minus": 3}])
        d["commits"].append({"kurz": "1234567", "titel": "y" * 500, "dateien": True, "plus": -1, "minus": "9"})
        with open(pfad, "w") as f:
            json.dump(d, f)
        lesen = entwickeln.anzeige_lesen(pfad)
        self.assertEqual(lesen["commits"][1], {"kurz": "1234567", "titel": "y" * entwickeln.TITEL_MAX, "dateien": 0, "plus": 0, "minus": 0})
        with mock.patch.object(entwickeln, "ANZEIGE", pfad):
            v = entwickelnseite.for_live()
            a = entwickelnseite.alerts(now=10)
        self.assertNotIn("Geheimer Titel", json.dumps(v) + entwickelnseite.live_sub(v) + json.dumps(a))

    def test_every_hint_points_to_the_page(self):
        import entwickelnseite
        self.assertEqual(entwickelnseite.WEG, "Zustand → Werkstatt → Entwickeln")
        with open(os.path.join(APP, "panel", "entwickelnseite.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("Weiter mit sudo speech-spark", src, "hints name the page, not only the command line")
        html = open(os.path.join(APP, "panel", "static", "index.html"), encoding="utf-8").read()
        werk = html[html.index('<section id="werk">'):html.index("</section>", html.index('<section id="werk">'))]
        self.assertIn('data-wt="dev">Entwickeln</button>', werk, "the part „Entwickeln“ is a tab of Zustand → Werkstatt")
        self.assertIn('id="dvbox"', werk)
        js = open(os.path.join(APP, "panel", "static", "js", "entwickeln.js"), encoding="utf-8").read()
        self.assertNotRegex(js, r"innerHTML|insertAdjacentHTML|outerHTML|document\.write", "titles and the terminal are data")
        self.assertIn("fzLaden()", js, "xterm.js of the Fernzugang, one source")

    def test_the_terminal_unit_is_fixed_and_never_root(self):
        b = entwickeln.terminal_befehl(1234, start="/home/spark-dev/speech-on-dgx-spark")
        self.assertEqual(b[:3], ["systemd-run", "--quiet", "--pty"])
        self.assertEqual(b[-2:], ["/bin/bash", "--login"])
        props = dict(b[i + 1].split("=", 1) for i, x in enumerate(b) if x == "-p")
        self.assertEqual((props["User"], props["Group"]), ("spark-dev", "spark-dev"))
        self.assertEqual(props["Slice"], "user-1234.slice", "spark-dev's own limits, below the panel")
        for k, v in (("NoNewPrivileges", "yes"), ("ProtectSystem", "strict"), ("ReadWritePaths", entwickeln.HOME),
                     ("CapabilityBoundingSet", ""), ("RuntimeMaxSec", str(entwickeln.TERM_GRENZE_S)), ("PrivateTmp", "yes")):
            self.assertEqual(props[k], v, k)
        for weg in ("/var/lib/speech-spark", "/etc/speech-spark", "/root", entwickeln.GH_KEY):
            self.assertIn("-" + weg, props["InaccessiblePaths"].split())
        for falsch in (0, -1, True, "1000", None):
            with self.assertRaises(entwickeln.Fehler):
                entwickeln.terminal_befehl(falsch)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(entwickeln.cli(["terminal", "--extra"]), 2, "never an argument from the caller")
            if os.geteuid() != 0:
                self.assertEqual(entwickeln.cli(["terminal"]), 2, "only root, through the wrapper")

    def test_the_installer_gives_the_panel_one_fixed_program(self):
        i = helpers.repo_file("install.sh")
        if not i:
            return
        sudo = i[:i.index("} >/etc/sudoers.d/speech-spark")]
        self.assertIn('printf \', /usr/local/bin/spark-dev-terminal ""\'', sudo, "no arguments allowed (\"\")")
        self.assertEqual(sudo.count("spark-dev-terminal"), 1, "the panel may start it, nothing else of spark-dev")
        w = i[i.index("cat >/usr/local/bin/spark-dev-terminal <<EOF"):]
        w = w[:w.index("\nEOF\n")]
        self.assertIn('[ "\\$#" = 0 ] || exit 2', w)
        self.assertIn("entwickeln.py terminal", w)
        self.assertIn("chown root:root /usr/local/bin/spark-dev-terminal", i)
        self.assertNotRegex(i, r"sudoers[^\n]*spark-dev|spark-dev[^\n]*NOPASSWD")


class Terminal(unittest.TestCase):
    """The terminal as spark-dev in the browser: a sub-switch (off), an admin in the browser with a second step, a fresh
    code every session, a ticket once in the same login and from the panel's own page, one session at a time, nothing
    of what runs in the journal or Live; the Notaus and logging out end it. A harmless program stands for root's."""

    CODE = {"x-speech-code": "123456"}

    def setUp(self):
        from fastapi.testclient import TestClient
        import entwickelnseite
        import guard
        import mfa
        import panel
        self.s, self.mfa, self.guard = entwickelnseite, mfa, guard
        self.real = (mfa.enabled, mfa.verify)
        self.admin, self.other = TestClient(panel.app), TestClient(panel.app)   # logged in before a code is asked
        self.anmelden()
        self.other.post("/api/login", json={"password": "secret-admin"})
        mfa.enabled = lambda who: who == mfa.ADMIN
        mfa.verify = lambda who, code: who == mfa.ADMIN and code == "123456"
        helpers.keep_chat(self, "entwickeln", "entwickeln_terminal")
        helpers.set_config(entwickeln=True, entwickeln_terminal=True)
        p = mock.patch.object(entwickelnseite, "BEFEHL", ["cat"])
        p.start()
        self.addCleanup(p.stop)
        self.reset()

    def anmelden(self):
        an = self.mfa.enabled
        self.mfa.enabled = self.real[0]
        self.assertEqual(self.admin.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        self.mfa.enabled = an

    def reset(self):
        self.s.TERM_TICKETS.clear()
        self.s.TERM.clear()
        for k in [k for k in self.guard._rate if str(k[0]).startswith("entwickeln")]:
            self.guard._rate.pop(k, None)

    def tearDown(self):
        self.mfa.enabled, self.mfa.verify = self.real
        self.reset()

    def ticket(self, client=None):
        r = (client or self.admin).post("/api/admin/entwickeln/terminal", json={"cols": 100, "rows": 30}, headers=self.CODE)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["ticket"]

    def refused(self, client, ticket, origin="http://testserver"):
        from starlette.websockets import WebSocketDisconnect
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/entwickeln/terminal?t={ticket}", headers={"origin": origin} if origin else {}) as ws:
                ws.receive_text()
        return out.getvalue()

    def warten(self, bedingung):
        import time
        for _ in range(200):
            if bedingung():
                return True
            time.sleep(0.025)
        return bedingung()

    def test_off_by_default_admin_only_and_registered(self):
        import features
        import stufen
        with open(os.path.join(APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["entwickeln_terminal"], False)
        self.assertNotIn("entwickelnterminal", features.DEFAULT_ON)
        f = {x.key: x for x in features.FEATURES}["entwickelnterminal"]
        self.assertEqual((f.admin, f.parent), (("entwickeln_terminal",), "entwickeln"))
        self.assertEqual(stufen.LIST[("POST", "/api/admin/entwickeln/terminal")][0], stufen.PROTECT, "a fresh code every session")
        from fastapi.testclient import TestClient
        import panel
        anon = TestClient(panel.app)
        self.assertIn(anon.post("/api/admin/entwickeln/terminal", headers=self.CODE).status_code, (401, 403))
        helpers.set_config(entwickeln_terminal=False)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.admin.post("/api/admin/entwickeln/terminal", headers=self.CODE).status_code, 409)
        self.assertIn("entwickeln: terminal abgelehnt aus", out.getvalue())
        self.assertEqual(self.s.TERM_TICKETS, {})

    def test_fresh_code_and_a_second_step(self):
        r = self.admin.post("/api/admin/entwickeln/terminal", json={})
        self.assertNotEqual(r.status_code, 200, "never without the code")
        self.assertEqual(self.s.TERM_TICKETS, {})
        self.mfa.enabled = lambda who: False
        out = io.StringIO()
        with redirect_stdout(out):
            r = self.admin.post("/api/admin/entwickeln/terminal", json={}, headers=self.CODE)
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("terminal abgelehnt zweiter_schritt", out.getvalue())

    def test_ticket_once_bound_to_its_login_and_the_own_page(self):
        t = self.ticket()
        self.assertNotIn(t, json.dumps(list(self.s.TERM_TICKETS)), "only its hash is kept")
        self.assertIn("abgewiesen fremde_seite", self.refused(self.admin, t, "https://evil.example"))
        self.assertIn("abgewiesen fremde_seite", self.refused(self.admin, t, ""))
        self.assertIn("abgewiesen ticket", self.refused(self.other, t), "another login of the same admin: no")
        t = self.ticket()
        for v in self.s.TERM_TICKETS.values():
            v["until"] -= self.s.TICKET_S + 1
        self.assertIn("abgewiesen ticket", self.refused(self.admin, t), "too late")
        from fastapi.testclient import TestClient
        import panel
        self.assertIn("abgewiesen kein_admin", self.refused(TestClient(panel.app), "x" * 43))

    def test_a_session_runs_once_and_ends(self):
        import entwickelnseite
        t = self.ticket()
        out = io.StringIO()
        with redirect_stdout(out):
            with self.admin.websocket_connect(f"/api/entwickeln/terminal?t={t}", headers={"origin": "http://testserver"}) as ws:
                m = json.loads(ws.receive_text())
                self.assertEqual((m["typ"], m["stand"]), ("stand", "offen"))
                self.assertEqual(len(entwickelnseite.TERM), 1)
                self.assertEqual(entwickelnseite.terminal_zahlen()["offen"], 1)
                ws.send_bytes(b"Geheimbefehl\n")
                got = b""
                while b"Geheimbefehl" not in got:
                    got += ws.receive_bytes()
                ws.send_text(json.dumps({"typ": "groesse", "cols": 120, "rows": 40}))
                self.assertEqual(self.admin.post("/api/admin/entwickeln/terminal", json={}, headers=self.CODE).status_code, 429, "one at a time")
                self.refused(self.admin, "y" * 43)
                ws.send_text(json.dumps({"typ": "ende"}))
                zu = None
                while zu is None:
                    m = ws.receive()
                    if m.get("text"):
                        zu = json.loads(m["text"])
                self.assertEqual(zu, {"typ": "zu", "grund": "beendet"})
            self.assertTrue(self.warten(lambda: not entwickelnseite.TERM and "terminal zu" in out.getvalue()))
        lines = out.getvalue()
        self.assertIn("entwickeln: terminal auf admin 1", lines)
        self.assertIn("entwickeln: terminal zu beendet 0", lines)
        self.assertIn("entwickeln: terminal abgelehnt voll 1", lines)
        self.assertNotIn("Geheimbefehl", lines, "what runs never reaches the journal")

    def test_notaus_and_logging_out_end_it(self):
        import asyncio as aio
        import entwickelnseite
        for weg in ("notaus", "abmelden"):
            t = self.ticket()
            with redirect_stdout(io.StringIO()):
                with self.admin.websocket_connect(f"/api/entwickeln/terminal?t={t}", headers={"origin": "http://testserver"}) as ws:
                    ws.receive_text()
                    s = next(iter(entwickelnseite.TERM.values()))
                    if weg == "notaus":
                        aio.run_coroutine_threadsafe(entwickelnseite.notaus_close(), s.loop).result(10)
                    else:
                        self.admin.post("/api/logout")
                    self.assertTrue(self.warten(lambda: not entwickelnseite.TERM), weg)
                    self.assertEqual(s.grund, weg)
            self.anmelden()
        with open(os.path.join(APP, "panel", "notaus.py"), encoding="utf-8") as f:
            self.assertIn("await entwickelnseite.notaus_close()", f.read())


DEMO_SEITE = {"an": True, "anzahl": 2, "offen": 1, "basis": "abcdef1", "kopf": "7be20d4", "vorher": True, "update": False,
              "letzter": {"art": "einspielen", "ergebnis": "ok", "t": 1762166000, "rot": [], "module": 12},
              "commits": [{"kurz": "a3f91c2", "titel": "Kalender: Begrüßung angepasst", "dateien": 2, "plus": 7, "minus": 1},
                          {"kurz": "7be20d4", "titel": "Hilfe Wetter: <b>zwei</b> Tippfehler", "dateien": 1, "plus": 2, "minus": 2}],
              "version": "V01.1.294+lokal", "internet": "da", "github_an": True, "terminal_an": True, "opencode": True,
              "opencode_version": "1.18.34", "zweig": "lokal", "terminal": {"offen": 0, "max": 1}, "leerlauf_min": 60}
DEMO_GITHUB = {"an": True, "wartet": False, "letzter": {"zustand": "gegeben", "t": 1762160000},
               "zweige": [{"zweig": "opencode/begruessung", "kopf": "a3f91c2", "anzahl": 1, "t": 1762160000, "tests": "gruen",
                           "link": "https://github.com/x/y/tree/opencode/begruessung"},
                          {"zweig": "opencode/logzeile-musik", "kopf": "1234567", "anzahl": 3, "t": 1761600000, "tests": "rot", "link": ""}]}


class ImBrowser(unittest.TestCase):
    """Zustand → Werkstatt → Entwickeln in a real browser at 320, 390 and 1280 px: the way opens the part, the tiles,
    the commits (their titles as text, never as HTML), the buttons with their lock, the Ablauf and the terminal tab;
    nothing is wider than the screen."""

    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import browser_ok
        if not browser_ok():
            raise unittest.SkipTest("no Playwright/Chromium here")
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    def test_the_page_at_three_widths(self):
        from tests.test_ui_browser import PAGE_READY, async_playwright, chromium
        demo = json.dumps(DEMO_SEITE)
        gh = json.dumps(DEMO_GITHUB)

        async def go():
            out = {}
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                base = f"http://127.0.0.1:{self.port}"
                for w in (320, 390, 1280):
                    ctx = await br.new_context(viewport={"width": w, "height": 900}, locale="de-DE", bypass_csp=True)
                    pg = await ctx.new_page()
                    await pg.goto(base + "/")
                    await pg.request.post(base + "/api/login", data={"password": "secret-admin"})
                    await pg.goto(base + "/")
                    await pg.wait_for_function(PAGE_READY, timeout=30000)
                    weg = await pg.evaluate("(()=>{const w='Zustand → Werkstatt → Entwickeln',r=wayParse(w,0);return r&&r.end===w.length?r.steps:0})()")
                    await pg.evaluate("wayGo('Zustand → Werkstatt → Entwickeln')")
                    await pg.wait_for_function("!document.getElementById('dvbox').hidden&&document.getElementById('werk').classList.contains('on')", timeout=10000)
                    await pg.wait_for_function("DV.d!==null", timeout=10000)   # the page's own first load is done
                    r = await pg.evaluate("""([d,g])=>{clearTimeout(DV.timer);DV.d=d;DV.gh=g;DV.sel='lokal';dvShow();
                        const det=$('dvdetail'),c=[...det.querySelectorAll('.dvcommit b')].map(x=>x.textContent);
                        return {kacheln:det.querySelectorAll('.dvtile').length,commits:c,fett:det.querySelectorAll('.dvcommit b b').length,
                          knoepfe:[...det.querySelectorAll('.ld-acts button')].map(b=>[b.textContent,b.disabled,b.classList.contains('needcode2')||b.classList.contains('needcode')]),
                          schritte:det.querySelectorAll('.dvschritt').length,zeilen:[...$('dvlist').querySelectorAll('.ld-row b')].map(x=>x.textContent),
                          breit:document.documentElement.scrollWidth-innerWidth,werk:getComputedStyle($('wkbox')).display}}""", [json.loads(demo), json.loads(gh)])
                    await pg.evaluate("dvAnsicht('term')")
                    t = await pg.evaluate("""()=>({knopf:[...$('dvxterm').querySelectorAll('button')].map(b=>b.textContent),
                        karten:$('dvtside').querySelectorAll('.dvtcard').length,breit:document.documentElement.scrollWidth-innerWidth})""")
                    out[w] = (weg, r, t)
                    await ctx.close()
                await br.close()
            return out
        out = asyncio.run(go())
        for w, (weg, r, t) in out.items():
            self.assertEqual(weg, 2, "both steps after Zustand match, to the end")
            self.assertEqual(r["kacheln"], 3, w)
            self.assertEqual(r["commits"], ["Kalender: Begrüßung angepasst", "Hilfe Wetter: <b>zwei</b> Tippfehler"], w)
            self.assertEqual(r["fett"], 0, "a title is text, never HTML")
            self.assertEqual([k[0] for k in r["knoepfe"]], ["Lokal einspielen", "An GitHub geben", "Zurück zur alten Version", "Verwerfen …"])
            self.assertTrue(all(k[2] for i, k in enumerate(r["knoepfe"]) if i != 1), "the buttons with a code show their lock")
            self.assertEqual(r["schritte"], 5)
            self.assertIn("opencode/begruessung", r["zeilen"])
            self.assertLessEqual(r["breit"], 0, f"nothing wider than {w} px")
            self.assertEqual(r["werk"], "none", "only the chosen part of the Werkstatt shows")
            self.assertEqual(t["knopf"], ["Terminal öffnen"])
            self.assertEqual(t["karten"], 2)
            self.assertLessEqual(t["breit"], 0, f"the terminal tab fits {w} px")


if __name__ == "__main__":
    unittest.main()
