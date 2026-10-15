"""Umziehen und Zurückholen (plan Raspberry-Pi split, B6c): the panel moves to another computer inside the pairing and
comes back the same way. Two state folders play the two computers (A: the DGX with the panel, B: the new panel
computer); each side runs umziehen.py as its own process with its own folders, the pairing (teilen.warten/koppeln)
runs here on 127.0.0.1. Checked: profiles and the vault key arrive (a secret sealed on A opens on B), the panel's
https certificate goes along (the apps pinned it), the giving side learns the result only from a signed "fertig",
a failed restore changes nothing on either side, nothing is deleted on A, and the way back carries what changed on
B. No real models; nothing depends on the time of day."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

from tests import helpers

helpers.start()
import teilen  # noqa: E402
import tlstor  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
PANEL = os.path.join(APP, "panel")


class Rechner:
    """One computer: its own config, state, users, voices, tls and backups."""
    def __init__(self, root, name):
        self.dir = os.path.join(root, name)
        for d in ("state", "users", "voices", "tls"):
            os.makedirs(os.path.join(self.dir, d))
        with open(os.path.join(APP, "config.default.json")) as f:
            cfg = json.load(f)
        cfg["api"]["key"] = "sk-umzug1234567890"
        with open(os.path.join(self.dir, "config.json"), "w") as f:
            json.dump(cfg, f)
        self.env = dict(os.environ, SPEECH_SPARK_CONFIG=os.path.join(self.dir, "config.json"),
                        SPEECH_SPARK_STATE=os.path.join(self.dir, "state"),
                        SPEECH_SPARK_USERS=os.path.join(self.dir, "users"),
                        SPEECH_SPARK_VOICES=os.path.join(self.dir, "voices"),
                        SPEECH_SPARK_TLS=os.path.join(self.dir, "tls"), SPEECH_SPARK_PREFIX=self.dir,
                        SPEECH_SPARK_BACKUPS=os.path.join(self.dir, "backups"))
        self.env.pop("PYTHONPATH", None)

    def py(self, code):
        """A snippet with the panel's modules of this computer; its stdout."""
        r = subprocess.run([PY, "-c", "import sys; sys.path[:0] = [%r, %r]\n" % (PANEL, APP) + code],
                           env=self.env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        return r.stdout.strip()

    def profile(self):
        return json.loads(self.py("import json, profiles; print(json.dumps(sorted(u['name'] for u in profiles.names())))"))

    def packen(self, ordner, pw):
        """What `speech-spark umziehen --code` does before the pairing: the move file and the password."""
        with open(os.path.join(ordner, "umzug.bin"), "wb") as out:
            r = subprocess.run([PY, os.path.join(PANEL, "umziehen.py"), "packen"], input=(pw + "\n").encode(),
                               stdout=out, stderr=subprocess.PIPE, env=self.env, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        with open(os.path.join(ordner, "passwort"), "w") as f:
            f.write(pw + "\n")

    def einspielen(self, ordner):
        """What `speech-spark teilen umzug-einspielen` pipes into umziehen.py auspacken."""
        with open(os.path.join(ordner, "umzug.json"), "rb") as h, open(os.path.join(ordner, "umzug.tar.gz"), "rb") as t:
            data = h.read() + b"\n" + t.read()
        r = subprocess.run([PY, os.path.join(PANEL, "umziehen.py"), "auspacken"], input=data, capture_output=True,
                           env=self.env, timeout=300)
        self.last = r
        return r.returncode == 0


def umzug(geber, nehmer, root, pw="umzugspasswort-0123", stoeren=None):
    """The move from geber to nehmer through the pairing; (result of the giving side, result or Fehler of the other)."""
    gib, nimm = tempfile.mkdtemp(dir=root), tempfile.mkdtemp(dir=root)
    geber.packen(gib, pw)
    cert = os.path.join(geber.dir, "tls", "tor-cert.pem")
    if not os.path.exists(cert):
        tlstor.make_cert(cert, os.path.join(geber.dir, "tls", "tor-key.pem"), ["127.0.0.1"])
    ctx = teilen._Ctx(cert, os.path.join(geber.dir, "tls", "tor-key.pem"))
    sock = teilen.lauschen(0, "127.0.0.1")
    out = {}

    def run():
        try:
            out["ok"] = teilen.warten({"api": {"key": "sk-umzug1234567890"}}, "ABCDEF", ctx, sock,
                                      umzug={"pfad": os.path.join(gib, "umzug.bin"), "passwort": pw})
        except teilen.Fehler as e:
            out["fehler"] = str(e)
        finally:
            sock.close()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    try:
        got = teilen.koppeln("127.0.0.1", sock.getsockname()[1], "ABCDEF", umzug_ordner=nimm,
                             einspielen=stoeren or (lambda: nehmer.einspielen(nimm)))
    except teilen.Fehler as e:
        got = e
    t.join(60)
    return out, got


class Umziehen(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(dir=helpers.TMP)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.a, self.b = Rechner(self.root, "dgx"), Rechner(self.root, "pi")
        self.secret = self.a.py("import profiles, vault; profiles.add_user('Dominik', '1234'); print(vault.seal('geheim'))")
        tlstor.make_cert(os.path.join(self.a.dir, "tls", "cert.pem"), os.path.join(self.a.dir, "tls", "key.pem"),
                         ["spark.local"])

    def test_there_and_back(self):
        out, got = umzug(self.a, self.b, self.root)
        self.assertIs(out["ok"]["umzug_ok"], True, out)
        self.assertIs(got["umzug"], True)
        self.assertEqual(self.b.profile(), ["Dominik"])
        self.assertEqual(self.b.py(f"import vault; print(vault.open_({self.secret!r}))"), "geheim")
        with open(os.path.join(self.a.dir, "tls", "cert.pem")) as fa, open(os.path.join(self.b.dir, "tls", "cert.pem")) as fb:
            self.assertEqual(fa.read(), fb.read(), "the apps' pin stays valid")
        self.assertEqual(self.a.profile(), ["Dominik"], "nothing is deleted on the giving side")
        # Zustand → Update lists what stays to do by hand, on the new computer only and for 14 days
        self.assertEqual(self.b.py("import umziehen; print(umziehen.hinweis())"), "True")
        self.assertEqual(self.b.py("import json, umziehen; s = json.load(open(umziehen.HINWEIS))['seit']; "
                                   "print(umziehen.hinweis(s + 15 * 86400))"), "False")
        self.assertEqual(self.a.py("import umziehen; print(umziehen.hinweis())"), "False")
        self.assertFalse([n for n in os.listdir(os.path.join(self.a.dir, "backups")) if n.endswith("-move.tar.gz")],
                         "the move backup sealed with a password nobody keeps does not stay in the list")
        # on B life goes on, then everything comes back to A (zurueckholen)
        self.b.py("import profiles; profiles.add_user('Gast', '5678')")
        out, got = umzug(self.b, self.a, self.root, pw="zurueckpasswort-987")
        self.assertIs(out["ok"]["umzug_ok"], True, out)
        self.assertEqual(self.a.profile(), ["Dominik", "Gast"])
        self.assertEqual(self.a.py(f"import vault; print(vault.open_({self.secret!r}))"), "geheim")

    def test_the_engine_share_of_another_backend_moves(self):
        """V01.0.636: tars' settings (Qwen3-ASR-1.7B with a share below 0.055, fine for its backend) were refused on
        the Pi, whose backend is vLLM; the move gives it the share install.sh gives (0.06)."""
        p = os.path.join(self.a.dir, "config.json")
        with open(p) as f:
            cfg = json.load(f)
        cfg["asr"].update(backend="transformers", model="Qwen/Qwen3-ASR-1.7B", engine_mem=0.035)
        with open(p, "w") as f:
            json.dump(cfg, f)
        out, got = umzug(self.a, self.b, self.root)
        self.assertIs(out["ok"]["umzug_ok"], True, self.b.last.stderr.decode()[-500:])
        self.assertEqual(self.b.profile(), ["Dominik"])
        self.assertEqual(self.b.py("import common; print(common.load_config()['asr']['engine_mem'])"), "0.06")

    def test_a_refused_setting_names_the_check(self):
        """V01.0.635: the Pi refused tars' settings ("ValueError system.py _check_config"); the line also names the
        check of admin.validate that said no, in fixed words, never the value."""
        p = os.path.join(self.a.dir, "config.json")
        with open(p) as f:
            cfg = json.load(f)
        cfg["chat"]["max_tokens"] = 5
        with open(p, "w") as f:
            json.dump(cfg, f)
        out, got = umzug(self.a, self.b, self.root)
        self.assertIsInstance(got, teilen.Fehler)
        err = self.b.last.stderr.decode()
        self.assertRegex(err, r"teilen: umzug abgelehnt \| ValueError system\.py _check_config \d+ \| aus HTTPException "
                              r"admin\.py validate \d+")
        self.assertNotIn("max_tokens", err)
        self.assertEqual(self.b.profile(), [])

    def test_a_failed_restore_changes_nothing(self):
        out, got = umzug(self.a, self.b, self.root, stoeren=lambda: False)
        self.assertIsInstance(got, teilen.Fehler)
        self.assertEqual(str(got), "umzug")
        self.assertIs(out["ok"]["umzug_ok"], False, "the giving side keeps its role")
        self.assertEqual(self.b.profile(), [])
        self.assertEqual(self.a.profile(), ["Dominik"])

    def test_a_wrong_password_is_refused(self):
        gib = tempfile.mkdtemp(dir=self.root)
        self.a.packen(gib, "richtigespasswort-1")
        nimm = tempfile.mkdtemp(dir=self.root)
        with open(os.path.join(gib, "umzug.bin"), "rb") as f:
            f.readline()
            data = f.read()
        with open(os.path.join(nimm, "umzug.tar.gz"), "wb") as f:
            f.write(data)
        with open(os.path.join(nimm, "umzug.json"), "w") as f:
            json.dump({"passwort": "falschespasswort-2", "cert": "", "key": ""}, f)
        self.assertFalse(self.b.einspielen(nimm))
        err = self.b.last.stderr.decode()
        self.assertIn("teilen: umzug abgelehnt", err)
        # V01.0.632: the line says where it stopped (the Pi refused a real move without a hint), never a message text
        self.assertRegex(err, r"teilen: umzug abgelehnt \| \w+Error \w+\.py \w+ \d+")
        self.assertNotIn("passwort", err.lower())
        self.assertEqual(self.b.profile(), [])

    def test_a_changed_file_is_not_restored(self):
        """The size and SHA-256 travel inside the signed answer: other bytes never reach the restore."""
        called = []
        real = teilen._umzug_kopf

        def wrong(path):
            head, start, size, sha = real(path)
            return head, start, size, "0" * 64
        teilen._umzug_kopf = wrong
        try:
            out, got = umzug(self.a, self.b, self.root, stoeren=lambda: called.append(1) or True)
        finally:
            teilen._umzug_kopf = real
        self.assertIsInstance(got, teilen.Fehler)
        self.assertEqual(called, [])
        self.assertIs(out["ok"]["umzug_ok"], False)


if __name__ == "__main__":
    unittest.main()
