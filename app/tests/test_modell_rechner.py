"""The model computer (plan Raspberry-Pi split, stage B1): speech recognition, speech output, pictures and the LLM-Tor
come from one address, common.model_url with models.host. On the all-in-one install (127.0.0.1, the default)
everything stays exactly as before; another computer is always https with the API key, a broken setting never
leaves this Spark, and the model computer's ports are the Spark's own services for netguard."""
import glob
import ipaddress
import json
import os
import re
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import admin as admin_mod  # noqa: E402
import common  # noqa: E402
import llm  # noqa: E402
import netguard  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PANEL = os.path.join(helpers.APP, "panel")
# the services on the model computer (asr_proxy.py, tts_proxy.py, llm_tor.py, bild_server.py, modelle.py, bench.py)
# live in app/, not in the panel, and ask their own engines on 127.0.0.1
FIXED_URL = re.compile(r"(127\.0\.0\.1|localhost):\{[^}]*(port|PORT)[^}]*\}")


def cfg_with(host, **ports):
    c = json.loads(json.dumps(common.load_config()))
    c["models"]["host"] = host
    for art, port in ports.items():
        c[common.MODEL_ARTS[art]]["port"] = port
    return c


class OneAddress(unittest.TestCase):
    def test_no_fixed_model_address_in_the_panel(self):
        # rule: every request of the panel to a model service goes through common.model_url
        found = []
        for path in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if FIXED_URL.search(line):
                        found.append(f"{os.path.basename(path)}:{n}")
        self.assertEqual(found, [], "use common.model_url(art, path, cfg) instead")

    def test_all_in_one_stays_as_before(self):
        c = cfg_with("127.0.0.1", asr=31001, tts=31002, bild=31005, llm=31006)
        self.assertEqual(common.model_url("asr", "/v1/audio/transcriptions", c),
                         "http://127.0.0.1:31001/v1/audio/transcriptions")
        self.assertEqual(common.model_url("tts", "/health", c), "http://127.0.0.1:31002/health")
        self.assertEqual(common.model_url("bild", "", c), "http://127.0.0.1:31005")
        self.assertEqual(common.model_url("llm", "/v1", c), "http://127.0.0.1:31006/v1")
        self.assertTrue(common.model_local(c))
        with open(os.path.join(helpers.APP, "config.default.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["models"]["host"], "127.0.0.1")

    def test_another_computer_is_https(self):
        c = cfg_with("dgx.fritz.box", asr=31001)
        self.assertFalse(common.model_local(c))
        self.assertEqual(common.model_url("asr", "/health", c), "https://dgx.fritz.box:31001/health")
        c = cfg_with("fd00::5", tts=31002)
        self.assertEqual(common.model_url("tts", "/v1/voices", c), "https://[fd00::5]:31002/v1/voices")

    def test_a_broken_setting_stays_on_this_spark(self):
        for bad in ("http://dgx", "dgx/v1", "dgx:31001", "a b", "-dgx", "", "dgx@evil", "x" * 300):
            c = cfg_with(bad, asr=31001)
            self.assertEqual(common.model_url("asr", "", c), "http://127.0.0.1:31001", bad)


class Validate(unittest.TestCase):
    def base(self):
        new = json.loads(json.dumps(common.load_config()))
        new["api"]["key"] = "sk-test"
        return new

    def test_only_a_name_or_ip(self):
        for good in ("127.0.0.1", "dgx", "dgx.fritz.box", "192.168.178.171", "fd00::5"):
            new = self.base()
            new["models"]["host"] = good
            admin_mod.validate(new)
        for bad in ("http://dgx", "dgx/v1", "dgx:31001", "", "a b", "dgx;rm"):
            new = self.base()
            new["models"]["host"] = bad
            with self.assertRaises(HTTPException, msg=bad):
                admin_mod.validate(new)

    def test_another_computer_needs_the_key(self):
        new = self.base()
        new["api"]["key"] = ""
        for s in ("asr", "tts"):
            new[s]["host"] = "127.0.0.1"
        admin_mod.validate(json.loads(json.dumps(new)))      # all-in-one, services only on loopback: no key needed
        new["models"]["host"] = "192.168.178.171"
        with self.assertRaises(HTTPException):
            admin_mod.validate(new)


class OwnTor(unittest.TestCase):
    def test_the_tor_on_the_model_computer_gets_the_key(self):
        c = cfg_with("192.168.178.171", llm=31006)
        self.assertTrue(llm.own_tor({"llm_url": "https://192.168.178.171:31006/v1"}, c))
        self.assertFalse(llm.own_tor({"llm_url": "http://192.168.178.171:31006/v1"}, c), "never in plain text")
        self.assertFalse(llm.own_tor({"llm_url": "https://192.168.178.172:31006/v1"}, c))
        self.assertFalse(llm.own_tor({"llm_url": "https://192.168.178.171:30001/v1"}, c))
        self.assertTrue(llm.own_tor({"llm_url": "http://127.0.0.1:31006/v1"}, c))

    def test_all_in_one_knows_only_this_spark(self):
        c = cfg_with("127.0.0.1", llm=31006)
        self.assertTrue(llm.own_tor({"llm_url": "http://localhost:31006/v1"}, c))
        self.assertFalse(llm.own_tor({"llm_url": "https://127.0.0.1:31006/v1"}, c))
        self.assertFalse(llm.own_tor({"llm_url": "http://192.168.178.171:31006/v1"}, c))
        self.assertFalse(llm.own_tor({"llm_url": "http://[::1:31006/v1"}, c))


class Netguard(unittest.TestCase):
    def setUp(self):
        netguard._model.update(host="", t=0.0, ips=set())
        self.addCleanup(netguard._model.update, host="", t=0.0, ips=set())

    def check(self, host, ip, port):
        with mock.patch.object(common, "load_config", return_value=cfg_with(host)):
            netguard._model.update(host="", t=0.0, ips=set())
            return netguard.allowed(ip, port, netguard.HOME)

    def test_the_model_computer_is_own_ground(self):
        self.assertIsNotNone(self.check("192.168.178.171", "192.168.178.171", 31001))
        self.assertIsNotNone(self.check("192.168.178.171", "192.168.178.171", 31006))
        self.assertIsNone(self.check("192.168.178.171", "192.168.178.171", 443), "other ports stay home network")
        self.assertIsNone(self.check("127.0.0.1", "192.168.178.171", 31001), "all-in-one: a LAN device like any")

    def test_a_name_is_looked_up(self):
        with mock.patch.object(netguard.socket, "getaddrinfo",
                               return_value=[(2, 1, 6, "", ("192.168.178.171", 0))]) as look:
            self.assertIsNotNone(self.check("dgx.fritz.box", "192.168.178.171", 31002))
            look.assert_called_once()
        with mock.patch.object(common, "load_config", return_value=cfg_with("dgx.fritz.box")):
            self.assertEqual(netguard.model_addresses(), {ipaddress.ip_address("192.168.178.171")})


if __name__ == "__main__":
    unittest.main()
