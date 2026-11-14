"""Spark-Clients (plan spark-entkoppeln E1 + E2, Dominik 2026-11-14 „2a“): other programs use the model computer's
services with a key of their own. The protection rules, each with its test:

- off by default (api.clients, chat.spark_clients); off, a client key opens nothing and api.key works as before;
- a key is shown once and kept only as its SHA-256; blocked or removed clients are refused at once;
- rights per service: a request without the right is refused (403), the Wärter and the stop of pictures and music
  never belong to a client; limits per minute, at once and tokens per day (429);
- the priority class decides the stage; a client never signs a stage itself, only "sprache" counts as speech;
- only networks in the home network (private, not wider than /8); the door (tlstor.allowed) and the firewall
  (teilen.regeln) let clients in only from them and only while open; a caller through the door is not "this machine";
- GET /v1/spark/faehigkeiten names the API version, the services and the key's rights, never a hash or another client;
- the panel: admins only, 409 while the function is off, switching it off closes the services again;
- every outcome writes a journal line with fixed words, never a name or key.
Nothing depends on the time of day (the day of the tokens is passed in)."""
import hashlib
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import common  # noqa: E402
import mandanten  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1763100000.0   # a fixed moment: the tokens of the day never depend on today's date


def api(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c["api"] = dict(c.get("api") or {}, **kw)
    helpers.write_config(c)


class Base(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            self.before = json.load(f).get("api") or {}
        self.addCleanup(self.back)
        if os.path.exists(mandanten.PATH):
            os.remove(mandanten.PATH)
        mandanten._cache.update(mtime=None, d=None)
        for tab in (mandanten._minute, mandanten._tage, mandanten._offen, mandanten._gemeldet):
            tab.clear()

    def back(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["api"] = self.before
        helpers.write_config(c)
        if os.path.exists(mandanten.PATH):
            os.remove(mandanten.PATH)
        mandanten._cache.update(mtime=None, d=None)

    def neu(self, rechte=("llm",), klasse="dialog", **grenzen):
        with redirect_stdout(io.StringIO()):
            return mandanten.neu("Open WebUI", list(rechte), klasse, now=T0, **grenzen)


class Keys(Base):
    def test_off_by_default(self):
        shipped = common.shipped()
        self.assertIs(shipped["api"]["clients"], False)
        self.assertEqual(shipped["api"]["clients_from"], [])
        self.assertIs(shipped["chat"]["spark_clients"], False)
        c, key = self.neu()
        api(clients=False)
        self.assertIsNone(mandanten.finden("Bearer " + key))

    def test_key_once_only_its_hash_kept(self):
        c, key = self.neu()
        api(clients=True)
        self.assertTrue(key.startswith(mandanten.KEY_PREFIX) and len(key) > 40)
        raw = open(mandanten.PATH).read()
        self.assertNotIn(key, raw)
        self.assertIn(hashlib.sha256(key.encode()).hexdigest(), raw)
        self.assertNotIn("sha", c)
        self.assertTrue(all("sha" not in x for x in mandanten.clients()))
        self.assertEqual(os.stat(mandanten.PATH).st_mode & 0o777, 0o600)
        self.assertEqual(mandanten.finden("Bearer " + key)["id"], c["id"])
        for bad in ("Bearer " + key[:-1] + "x", key, "Bearer sk-spark-", "Basic " + key, "", None):
            self.assertIsNone(mandanten.finden(bad), bad)

    def test_blocked_and_removed_at_once(self):
        c, key = self.neu()
        api(clients=True)
        with redirect_stdout(io.StringIO()):
            mandanten.aendern(c["id"], {"gesperrt": True})
        self.assertIsNone(mandanten.finden("Bearer " + key))
        with redirect_stdout(io.StringIO()):
            mandanten.aendern(c["id"], {"gesperrt": False})
        self.assertIsNotNone(mandanten.finden("Bearer " + key))
        with redirect_stdout(io.StringIO()):
            mandanten.weg(c["id"])
        self.assertIsNone(mandanten.finden("Bearer " + key))

    def test_values_checked(self):
        for name, rechte, klasse, grenzen, why in (
                ("", ["llm"], "dialog", {}, "name"), ("x" * 41, ["llm"], "dialog", {}, "name"),
                ("<b>", ["llm"], "dialog", {}, "name"), ("A", [], "dialog", {}, "recht"),
                ("A", ["verwalten"], "dialog", {}, "recht"), ("A", ["llm"], "admin", {}, "klasse"),
                ("A", ["llm"], "dialog", {"minute": 0}, "wert"), ("A", ["llm"], "dialog", {"parallel": 99}, "wert"),
                ("A", ["llm"], "dialog", {"tokens_tag": True}, "wert")):
            with self.assertRaises(mandanten.Fehler) as e, redirect_stdout(io.StringIO()):
                mandanten.neu(name, rechte, klasse, **grenzen)
            self.assertEqual(str(e.exception), why)
        with redirect_stdout(io.StringIO()):
            for i in range(mandanten.MAX_CLIENTS):
                mandanten.neu(f"C {i}", ["llm"], "dialog")
            with self.assertRaises(mandanten.Fehler):
                mandanten.neu("einer zu viel", ["llm"], "dialog")
        self.assertNotIn("verwalten", mandanten.RECHTE)

    def test_only_home_networks(self):
        for bad in ("0.0.0.0/0", "8.8.8.0/24", "10.0.0.0/7", "127.0.0.0/8", "fe80::/10x", "irgendwas", "::/0"):
            with self.assertRaises(mandanten.Fehler, msg=bad), redirect_stdout(io.StringIO()):
                mandanten.schalten(True, [bad])
        with redirect_stdout(io.StringIO()) as out:
            d = mandanten.schalten(True, ["192.168.178.7/24", "10.1.0.0/16"])
        self.assertEqual(d["netze"], ["10.1.0.0/16", "192.168.178.0/24"])
        self.assertTrue(d["an"])
        self.assertIn("sparkclient: panel an netze 2", out.getvalue())
        self.assertNotIn("192.168", out.getvalue())


class Services(Base):
    """api_key_dependency(recht): what a service's door says to api.key and to a client."""

    def setUp(self):
        super().setUp()
        app = FastAPI()
        dep = common.api_key_dependency("asr")

        @app.post("/v1/x")
        def x(_=Depends(dep)):
            return {"ok": True}
        self.c = TestClient(app)   # its peer is "testclient": not this machine, not in any network
        self.key = common.load_config()["api"]["key"] or "panel-key"
        api(key=self.key)

    def post(self, key, host="192.168.178.20"):
        with mock.patch.object(mandanten, "im_netz", lambda h, cfg=None: h != "draussen"):
            return self.c.post("/v1/x", headers={"Authorization": "Bearer " + key} if key else {})

    def test_api_key_as_before_and_clients_only_while_open(self):
        c, key = self.neu(rechte=("asr",))
        self.assertEqual(self.post(self.key).status_code, 200)
        self.assertEqual(self.post("").status_code, 401)
        self.assertEqual(self.post(key).status_code, 401)        # closed
        api(clients=True)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.post(key).status_code, 200)

    def test_right_and_limit(self):
        api(clients=True)
        c, key = self.neu(rechte=("llm",))
        with redirect_stdout(io.StringIO()) as out:
            r = self.post(key)
        self.assertEqual((r.status_code, r.json()["detail"]), (403, "recht"))
        self.assertIn(f"sparkclient: abgelehnt recht {c['id']} asr", out.getvalue())
        self.assertNotIn("Open WebUI", out.getvalue())
        c, key = self.neu(rechte=("asr",), minute=2)
        with redirect_stdout(io.StringIO()):
            self.assertEqual([self.post(key).status_code for _ in range(3)], [200, 200, 429])

    def test_network(self):
        api(clients=True, clients_from=["192.168.178.0/24"])
        cfg = common.load_config()
        self.assertTrue(mandanten.im_netz("192.168.178.9", cfg))
        self.assertTrue(mandanten.im_netz(common.TOR_SOURCE, cfg))   # the door checked it already
        self.assertFalse(mandanten.im_netz("192.168.10.9", cfg))
        self.assertFalse(mandanten.im_netz("8.8.8.8", cfg))
        api(clients=False)
        self.assertEqual(mandanten.netze(), [])

    def test_class_decides_the_stage(self):
        api(clients=True)
        signed = {common.STAGE_HEADER: "2", common.STAGE_KEY_HEADER: common.stage_key(create=True)}
        for klasse, stage in (("sprache", common.STAGE_HIGH), ("dialog", common.STAGE_NORMAL),
                              ("hintergrund", common.STAGE_LOW)):
            c, key = self.neu(rechte=("tts",), klasse=klasse)
            h = dict(signed, authorization="Bearer " + key)
            self.assertEqual(common._stage(lambda k, d="": h.get(k, d), "127.0.0.1"), (stage, False), klasse)
        c, key = self.neu(rechte=("tts",), klasse="hintergrund")
        scope = {"headers": [(b"authorization", ("Bearer " + key).encode())], "client": ("127.0.0.2", 1)}
        self.assertTrue(common._kein_sprecher(scope))
        c, key = self.neu(rechte=("tts",), klasse="sprache")
        scope = {"headers": [(b"authorization", ("Bearer " + key).encode())], "client": ("127.0.0.2", 1)}
        self.assertFalse(common._kein_sprecher(scope))

    def test_through_the_door_is_not_this_machine(self):
        self.assertFalse(common._hier(common.TOR_SOURCE))
        self.assertTrue(common._hier("127.0.0.1"))
        self.assertTrue(common._loopback(common.TOR_SOURCE))
        api(key="")
        self.assertFalse(common.api_key_ok({"headers": [], "client": (common.TOR_SOURCE, 1)}))
        self.assertTrue(common.api_key_ok({"headers": [], "client": ("127.0.0.1", 1)}))
        src = open(os.path.join(APP, "tlstor.py")).read()
        self.assertIn("local_addr=(TOR_SOURCE, 0)", src)

    def test_tokens_and_parallel(self):
        api(clients=True)
        c, key = self.neu(tokens_tag=1000, parallel=1)
        self.assertTrue(mandanten.tokens_ok(c, T0))
        mandanten.tokens_zaehlen(c, 999, T0)
        self.assertTrue(mandanten.tokens_ok(c, T0))
        mandanten.tokens_zaehlen(c, 1, T0)
        self.assertFalse(mandanten.tokens_ok(c, T0))
        self.assertTrue(mandanten.tokens_ok(c, T0 + 2 * 86400))   # another day
        self.assertTrue(mandanten.herein(c))
        self.assertFalse(mandanten.herein(c))
        mandanten.raus(c)
        self.assertTrue(mandanten.herein(c))

    def test_stop_and_waerter_never_for_clients(self):
        for f in ("bild_server.py", "musik_server.py"):
            src = open(os.path.join(APP, f)).read()
            self.assertIn('if getattr(request.state, "client", None) is not None:', src, f)
        import tarswart
        src = open(os.path.join(APP, "tarswart.py")).read()
        self.assertNotIn("mandanten.finden", src)   # the Wärter takes only the signed panel
        self.assertIn("clients_schalten", tarswart.COMMANDS)
        for f, recht in (("asr_proxy.py", "asr"), ("tts_proxy.py", "tts"), ("bild_server.py", "bild"),
                         ("musik_server.py", "musik")):
            self.assertIn(f'api_key_dependency("{recht}")', open(os.path.join(APP, f)).read(), f)
        for f in ("asr_server.py", "tts_server.py"):   # the engines behind them: api.key only
            self.assertIn("api_key_dependency())", open(os.path.join(APP, f)).read(), f)


class Door(Base):
    def test_door_and_firewall_only_while_open(self):
        import teilen
        import tlstor
        api(tls_listen="192.168.178.171", tls_from=["192.168.178.20"], clients=False, clients_from=["192.168.178.0/24"])
        cfg = common.load_config()
        self.assertTrue(tlstor.allowed("192.168.178.20", cfg))
        self.assertFalse(tlstor.allowed("192.168.178.30", cfg))
        self.assertNotIn("192.168.178.0/24", teilen.regeln(cfg))
        api(clients=True)
        cfg = common.load_config()
        self.assertTrue(tlstor.allowed("192.168.178.30", cfg))
        self.assertTrue(tlstor.allowed("::ffff:192.168.178.30", cfg))
        self.assertFalse(tlstor.allowed("192.168.10.5", cfg))
        self.assertIn("192.168.178.0/24", teilen.regeln(cfg))

    def test_firewall_unit_root_reads_the_config(self):
        try:
            sh = helpers.repo_file("install.sh")
        except unittest.SkipTest:
            sh = ""   # the copy with only app/: the root unit is checked where install.sh is
        if sh:
            self.assertIn("ExecStart=/bin/bash $PREFIX/app/speech-spark.sh teilen firewall", sh)
            self.assertIn("/usr/bin/systemctl start --no-block speech-spark-clients-fw", sh)
        with mock.patch.object(mandanten, "model_side", lambda: True), \
                mock.patch.object(mandanten, "run", return_value=(0, "")) as r, redirect_stdout(io.StringIO()) as out:
            mandanten.schalten(False, [])
        self.assertEqual(r.call_args[0][0], ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", mandanten.FW_UNIT])
        self.assertIn("sparkclient: firewall gestartet", out.getvalue())


class Faehigkeiten(Base):
    def test_what_the_key_may(self):
        api(clients=True)
        c, key = self.neu(rechte=("llm", "tts"), klasse="hintergrund")
        d = mandanten.faehigkeiten(mandanten.finden("Bearer " + key))
        self.assertEqual(d["spark_api"], common.SPARK_API)
        self.assertEqual(d["rechte"], ["llm", "tts"])
        self.assertEqual(d["client"]["name"], "Open WebUI")
        self.assertEqual(d["dienste"]["llm"]["modell"], common.LLM_ALIAS)
        self.assertEqual(set(d["dienste"]), set(common.MODEL_ARTS))
        text = json.dumps(d)
        self.assertNotIn("sha", text)
        self.assertNotIn(key, text)
        self.assertEqual(mandanten.faehigkeiten(None)["rechte"], list(mandanten.RECHTE))
        for f in ("llm_tor.py", "asr_proxy.py", "tts_proxy.py"):
            self.assertIn('@app.get("/v1/spark/faehigkeiten")', open(os.path.join(APP, f)).read(), f)


class Panel(Base):
    def test_off_409_and_admin_only(self):
        helpers.keep_chat(self, "spark_clients")
        helpers.set_config(spark_clients=False)
        self.assertEqual(ADMIN.get("/api/admin/spark-clients").status_code, 409)
        self.assertEqual(ADMIN.post("/api/admin/spark-clients/neu", json={"name": "A", "rechte": ["llm"]}).status_code, 409)
        guest = TestClient(panel.app)
        self.assertIn(guest.get("/api/admin/spark-clients").status_code, (401, 403))
        self.assertFalse(os.path.exists(mandanten.PATH))

    def test_make_block_delete_and_close_when_off(self):
        helpers.keep_chat(self, "spark_clients")
        helpers.set_config(spark_clients=True)
        with redirect_stdout(io.StringIO()) as out:
            r = ADMIN.post("/api/admin/spark-clients/schalten", json={"an": True, "netze": ["192.168.178.0/24"]})
            self.assertEqual(r.status_code, 200, r.text)
            r = ADMIN.post("/api/admin/spark-clients/neu", json={"name": "Open WebUI", "rechte": ["llm"], "klasse": "dialog"})
            self.assertEqual(r.status_code, 200, r.text)
            key, cid = r.json()["key"], r.json()["client"]["id"]
            self.assertIsNotNone(mandanten.finden("Bearer " + key))
            self.assertNotIn(key, json.dumps(ADMIN.get("/api/admin/spark-clients").json()))
            r = ADMIN.post("/api/admin/spark-clients/neu", json={"name": "<x>", "rechte": ["llm"]})
            self.assertEqual(r.status_code, 400)
            self.assertEqual(ADMIN.post("/api/admin/spark-clients/aendern", json={"id": cid, "felder": {"gesperrt": True}}).status_code, 200)
            self.assertIsNone(mandanten.finden("Bearer " + key))
            self.assertEqual(ADMIN.post("/api/admin/spark-clients/weg", json={"id": "../x"}).status_code, 400)
            self.assertEqual(ADMIN.post("/api/admin/spark-clients/weg", json={"id": cid}).status_code, 200)
            import steuer
            steuer.clients_zu()   # admin._save when Funktionen → Spark-Clients goes off
        self.assertFalse(mandanten.an())
        log = out.getvalue()
        for line in log.splitlines():
            if "sparkclient" in line:
                self.assertTrue(line.startswith("sparkclient: "), line)
        self.assertNotIn(key, log)
        self.assertNotIn("Open WebUI", log)

    def test_code_levels(self):
        import stufen
        self.assertEqual(stufen.LIST[("POST", "/api/admin/spark-clients/neu")][0], stufen.PROTECT)
        for p in ("schalten", "aendern", "weg"):
            self.assertEqual(stufen.LIST[("POST", "/api/admin/spark-clients/" + p)][0], stufen.CONFIRM, p)

    def test_no_tool_for_the_model(self):
        names = open(os.path.join(APP, "panel", "werkzeuge.py"), encoding="utf-8").read()
        self.assertNotIn("sparkclient", names)
        self.assertNotIn("spark_client", names)


if __name__ == "__main__":
    unittest.main()
