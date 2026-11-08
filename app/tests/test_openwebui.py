"""Open WebUI einbinden (openwebui.py): off by default and built on „Sprachmodell per API“; one step makes a key and a
MCP connection with only the reading tools and „Spark fragen“, both home network only; connecting again replaces the
pair, „Trennen“ removes both; only ids are kept; the menu link is the inner address at home and the outer one through
the proxy; the Wächter asks only /health of the inner address; the addresses are plain http(s); never for guests,
never a token in the journal."""
import contextlib
import io
import json
import unittest

from tests import helpers

helpers.start()
import core  # noqa: E402
import dienstwacht  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import llmapi  # noqa: E402
import mcpserver  # noqa: E402
import mfa  # noqa: E402
import netguard  # noqa: E402
import openwebui  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
LAN = ("192.168.178.50", 40000)
CODE = {"X-Speech-Code": "123456"}
KEYS = ("llm_api", "mcp_server", "mcp_server_act", "openwebui", "openwebui_url", "openwebui_link_url", "deny")


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app, client=LAN)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles.names() if u["name"] == name)


class Base(unittest.TestCase):
    def setUp(self):
        with open(helpers.os.environ["SPEECH_SPARK_CONFIG"]) as f:
            chat = json.load(f)["chat"]
        self.before = {k: chat[k] for k in KEYS if k in chat}
        helpers.set_config(llm_api=True, mcp_server=True, mcp_server_act=True, openwebui=True,
                           openwebui_url="http://192.168.178.20:3000", openwebui_link_url="https://chat.example.org",
                           deny={})
        guard.reset()
        for k in [k for k in guard._rate if k[0] in ("openwebui", "features", "llmapi")]:
            guard._rate.pop(k, None)
        core._windows.clear()
        self.real = (mfa.enabled, mfa.verify)
        mfa.enabled = lambda who: False
        mfa.verify = lambda who, code: code == "123456"

    def tearDown(self):
        mfa.enabled, mfa.verify = self.real
        core._windows.clear()
        with open(helpers.os.environ["SPEECH_SPARK_CONFIG"]) as f:
            cfg = json.load(f)
        for k in KEYS:
            cfg["chat"].pop(k, None)
        cfg["chat"].update(self.before)
        helpers.write_config(cfg)

    def connect(self, c):
        r = c.post("/api/profile/openwebui", json={}, headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class OffAndRights(Base):
    def test_off_by_default_built_on_llm_api_no_profile_switch(self):
        with open(helpers.APP + "/config.default.json") as f:
            d = json.load(f)["chat"]
        self.assertIs(d["openwebui"], False)
        self.assertEqual((d["openwebui_url"], d["openwebui_link_url"]), ("", ""))
        self.assertNotIn("openwebui", profiles.SETTINGS)
        self.assertEqual(features.BY_KEY["openwebui"].parent, "llmapi")
        c, uid = profile("OwOff")
        helpers.set_config(openwebui=False)
        self.assertEqual(c.post("/api/profile/openwebui", json={}, headers=CODE).status_code, 403)
        self.assertFalse(c.get("/api/profile/openwebui").json()["enabled"])
        self.assertEqual(openwebui.probes(), {})
        helpers.set_config(openwebui=True, llm_api=False)   # without its parent it is off too
        self.assertFalse(openwebui.admin_on())
        self.assertEqual(c.post("/api/profile/openwebui", json={}, headers=CODE).status_code, 403)

    def test_blocked_guest_and_device_key_refused(self):
        c, uid = profile("OwBlock")
        helpers.set_config(deny={"openwebui": [uid]})
        self.assertEqual(c.post("/api/profile/openwebui", json={}, headers=CODE).status_code, 403)
        self.assertEqual(c.get("/api/profile/openwebui").json()["link"], "")
        helpers.set_config(deny={})
        self.assertIn(TestClient(panel.app, client=LAN).post("/api/profile/openwebui", json={}).status_code, (401, 403))
        dev = profiles.add_device("Skript", uid)
        r = TestClient(panel.app, client=LAN).post("/api/profile/openwebui", json={}, headers={profiles.DEVICE_HEADER: dev})
        self.assertIn(r.status_code, (401, 403))


class Pair(Base):
    def test_connect_makes_key_and_read_only_connection_home_only(self):
        c, uid = profile("OwMia")
        r = self.connect(c)
        self.assertTrue(r["llm_token"].startswith("sk-spark-"))
        self.assertTrue(r["mcp_token"])
        k = llmapi.find(r["llm_token"])
        self.assertEqual((k["uid"], k["where"], k["name"]), (uid, "lokal", openwebui.NAME))
        conn = mcpserver.find(r["mcp_token"])
        self.assertEqual((conn["uid"], conn["where"]), (uid, "lokal"))
        self.assertTrue(conn["tools"])
        # only reading and „Spark fragen“, never „Handeln“ (even with the admin's switch on)
        self.assertTrue(all(mcpserver.TOOLS[n][0] in ("read", "ask") for n in conn["tools"]), conn["tools"])
        self.assertIn("ask_spark", conn["tools"])
        # only ids are kept, never a token
        for path in (openwebui._file(), llmapi._file(), mcpserver._file()):
            with open(path) as f:
                text = f.read()
            self.assertNotIn(r["llm_token"], text)
            self.assertNotIn(r["mcp_token"], text)
        g = c.get("/api/profile/openwebui").json()
        self.assertTrue(g["connected"] and g["llm"] and g["mcp_conn"])

    def test_again_replaces_and_disconnect_removes_both(self):
        c, uid = profile("OwNeu")
        old = self.connect(c)
        new = self.connect(c)
        self.assertIsNone(llmapi.find(old["llm_token"]))
        self.assertIsNone(mcpserver.find(old["mcp_token"]))
        self.assertIsNotNone(llmapi.find(new["llm_token"]))
        self.assertEqual(sum(1 for k in llmapi.keys(uid) if k["name"] == openwebui.NAME), 1)
        self.assertEqual(c.delete("/api/profile/openwebui").status_code, 200)
        self.assertIsNone(llmapi.find(new["llm_token"]))
        self.assertIsNone(mcpserver.find(new["mcp_token"]))
        self.assertEqual(c.delete("/api/profile/openwebui").status_code, 404)
        self.assertFalse(c.get("/api/profile/openwebui").json()["connected"])

    def test_without_mcp_server_only_the_key(self):
        c, uid = profile("OwNurKey")
        helpers.set_config(mcp_server=False)
        r = self.connect(c)
        self.assertIsNone(r["mcp_token"])
        self.assertIsNotNone(llmapi.find(r["llm_token"]))
        self.assertEqual(openwebui.pair(uid)["mcp"], None)

    def test_blocked_profile_keeps_delete_through_own(self):
        c, uid = profile("OwOwn")
        self.connect(c)
        count, clear = features.OWN["openwebui"]
        self.assertEqual(count(uid), 2)
        clear(uid)
        self.assertEqual(count(uid), 0)

    def test_journal_only_fixed_words(self):
        c, uid = profile("OwLog")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.connect(c)
            c.delete("/api/profile/openwebui")
        lines = [x for x in out.getvalue().splitlines() if x.startswith("openwebui:")]
        self.assertTrue(any("verbunden" in x for x in lines) and any("getrennt" in x for x in lines), lines)
        for x in lines:
            self.assertNotIn(r["llm_token"], x)
            self.assertNotIn(uid, x)


class LinkAndWatch(Base):
    def test_link_inner_at_home_outer_through_the_proxy(self):
        c, uid = profile("OwLink")
        self.assertEqual(c.get("/api/profile/openwebui").json()["link"], "http://192.168.178.20:3000")
        via = c.get("/api/profile/openwebui", headers={"X-Forwarded-For": "1.2.3.4"}).json()["link"]
        self.assertEqual(via, "https://chat.example.org")
        helpers.set_config(openwebui_link_url="")
        self.assertEqual(c.get("/api/profile/openwebui", headers={"X-Forwarded-For": "1.2.3.4"}).json()["link"], "")

    def test_addresses_plain_http_only(self):
        cfg = ADMIN.get("/api/config").json()
        for bad in ({"openwebui_url": "javascript:alert(1)"}, {"openwebui_url": "http://a.b/x?y=1"},
                    {"openwebui_link_url": "https://user@a.b"}, {"openwebui_link_url": "ftp://a.b"}):
            new = {k: dict(v) for k, v in cfg.items()}
            new["chat"].update(bad)
            self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 400, bad)
        helpers.set_config(openwebui_url="http://a.b/x?y=1")
        self.assertEqual(openwebui.base(), "")

    def test_watcher_asks_only_health_at_home_level(self):
        p = openwebui.probes()["openwebui"]
        self.assertEqual(p["url"], "http://192.168.178.20:3000/health")
        self.assertEqual(p["level"], netguard.HOME)
        self.assertNotIn("key", p)
        self.assertIn("openwebui", dienstwacht.active())
        self.assertIn("openwebui", dienstwacht.SVC)
        helpers.set_config(openwebui_url="")
        self.assertNotIn("openwebui", dienstwacht.active())

    def test_live_numbers_only(self):
        c, uid = profile("OwLive")
        self.connect(c)
        v = openwebui.for_live()
        self.assertTrue(v["on"] and v["connected"] >= 1 and v["inner"])
        self.assertIn("openwebui", live.TARGETS)
        sub = openwebui.live_sub(v)
        self.assertNotIn("192.168", sub)
        self.assertNotIn("example", sub)


if __name__ == "__main__":
    unittest.main()
