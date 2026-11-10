"""Sprachmodell per API (llmapi.py): off by default, keys per profile (only hashes kept, at most 5), home network only
unless the admin allows outside, text only through the field guard, the model name always the Spark's own, the
stage "hinten", limits per key (none for admins), only with the own LLM-Tor, never a content in the journal."""
import asyncio
import contextlib
import io
import json
import unittest

import httpx

from tests import helpers

helpers.start()
import coadmin  # noqa: E402
import core  # noqa: E402
import guard  # noqa: E402
import llmapi  # noqa: E402
import mfa  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from common import STAGE_HEADER  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
LAN = ("192.168.178.50", 40000)
CODE = {"X-Speech-Code": "123456"}
SECRET = "Geheimnis-im-Text-4711"


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles.names() if u["name"] == name)


class Base(unittest.TestCase):
    def setUp(self):
        with open(helpers.os.environ["SPEECH_SPARK_CONFIG"]) as f:
            chat = json.load(f)["chat"]
        # the other test modules of the same run talk to the fake model at the configured address: put it back after
        self.before = {k: chat[k] for k in ("llm_api", "llm_api_extern", "llm_api_minute", "llm_api_tag_k", "deny",
                                             "llm_url", "llm_model") if k in chat}
        helpers.set_config(llm_api=True, llm_api_extern=False, llm_api_minute=20, llm_api_tag_k=300, deny={},
                           llm_url="http://127.0.0.1:31006/v1", llm_model="qwen-test")
        guard.reset()
        for k in [k for k in guard._rate if k[0] in ("llmapi", "features")]:
            guard._rate.pop(k, None)
        core._windows.clear()
        llmapi._busy.clear()
        llmapi._minute.clear()
        self.real = (mfa.enabled, mfa.verify, coadmin.unbegrenzt, llmapi._client)
        self.mfa_on, self.admins, self.seen = set(), set(), []
        mfa.enabled = lambda who: who in self.mfa_on
        mfa.verify = lambda who, code: who in self.mfa_on and code == "123456"
        coadmin.unbegrenzt = lambda uid: uid in self.admins

        def engine(req):
            body = json.loads(req.content)
            self.seen.append((str(req.url), dict(req.headers), body))
            usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
            if body.get("stream"):
                text = ('data: {"choices":[{"delta":{"content":"Hal"}}]}\n\n'
                        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
                        f'data: {{"choices":[],"usage":{json.dumps(usage)}}}\n\ndata: [DONE]\n\n')
                return httpx.Response(200, content=text.encode(), headers={"content-type": "text/event-stream"})
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Hallo"}}], "usage": usage})
        llmapi._client = httpx.AsyncClient(transport=httpx.MockTransport(engine))
        self.lan = TestClient(panel.app, client=LAN)

    def tearDown(self):
        mfa.enabled, mfa.verify, coadmin.unbegrenzt, _ = self.real
        llmapi._client = self.real[3]
        core._windows.clear()
        with open(helpers.os.environ["SPEECH_SPARK_CONFIG"]) as f:
            cfg = json.load(f)
        for k in ("llm_api", "llm_api_extern", "llm_api_minute", "llm_api_tag_k", "deny", "llm_url", "llm_model"):
            cfg["chat"].pop(k, None)
        cfg["chat"].update(self.before)
        helpers.write_config(cfg)

    def key(self, c, where="lokal", name="Laptop", tag_k=None, code=CODE):
        body = {"name": name, "where": where}
        if tag_k is not None:
            body["tag_k"] = tag_k
        r = c.post("/api/profile/llmapi/keys", json=body, headers=code)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["token"]

    def ask(self, token, client=None, headers=None, **body):
        h = {"Authorization": f"Bearer {token}"}
        h.update(headers or {})
        b = {"model": "egal", "messages": [{"role": "user", "content": "Hallo " + SECRET}]}
        b.update(body)
        return (client or self.lan).post("/v1/chat/completions", json=b, headers=h)


class OffAndKeys(Base):
    def test_off_by_default_and_no_profile_switch(self):
        with open(helpers.APP + "/config.default.json") as f:
            d = json.load(f)["chat"]
        self.assertIs(d["llm_api"], False)
        self.assertIs(d["llm_api_extern"], False)
        self.assertEqual((d["llm_api_minute"], d["llm_api_tag_k"]), (20, 300))
        self.assertNotIn("llm_api", profiles.SETTINGS)
        helpers.set_config(llm_api=False)
        self.assertEqual(self.ask("sk-spark-" + "x" * 43).status_code, 404)
        self.assertEqual(self.lan.get("/v1/models").status_code, 404)

    def test_key_only_hash_kept_and_needs_the_browser_login(self):
        c, uid = profile("ApiMia")
        helpers.set_config(deny={"llmapi": [uid]})   # the admin blocks this profile
        self.assertEqual(c.post("/api/profile/llmapi/keys", json={"name": "X"}, headers=CODE).status_code, 403)
        helpers.set_config(deny={})
        for bad in ({"name": ""}, {"name": "x" * 61}, {"name": "A<b>"}, {"name": "A", "where": "anywhere"},
                    {"name": "A", "tag_k": 0}, {"name": "A", "tag_k": 301}, {"name": "A", "tag_k": True}):
            self.assertIn(c.post("/api/profile/llmapi/keys", json=bad, headers=CODE).status_code, (400, 403), bad)
        token = self.key(c)
        self.assertTrue(token.startswith("sk-spark-"))
        with open(llmapi._file()) as f:
            self.assertNotIn(token, f.read())
        dev = profiles.add_device("Skript", uid)
        r = TestClient(panel.app).post("/api/profile/llmapi/keys", json={"name": "Y"}, headers={profiles.DEVICE_HEADER: dev})
        self.assertIn(r.status_code, (401, 403))
        # the key works for /v1 only, never as a device key of the profile
        self.assertEqual(TestClient(panel.app).get("/api/profile/today", headers={profiles.DEVICE_HEADER: token}).status_code, 401)
        # guests never
        self.assertIn(TestClient(panel.app).post("/api/profile/llmapi/keys", json={"name": "G"}).status_code, (401, 403))

    def test_at_most_five_and_delete(self):
        c, uid = profile("ApiFuenf")
        tokens = [self.key(c, name=f"K{i}") for i in range(llmapi.MAX_KEYS)]
        self.assertEqual(c.post("/api/profile/llmapi/keys", json={"name": "Zu viel"}, headers=CODE).status_code, 409)
        kid = c.get("/api/profile/llmapi").json()["keys"][0]["id"]
        self.assertEqual(c.delete("/api/profile/llmapi/keys/" + kid).status_code, 200)
        self.assertEqual(self.ask(tokens[0]).status_code, 401)
        self.assertEqual(self.ask(tokens[1]).status_code, 200)
        # another profile cannot delete it, the admin can (with the code)
        other, _ = profile("ApiAndere")
        kid2 = c.get("/api/profile/llmapi").json()["keys"][0]["id"]
        self.assertEqual(other.delete("/api/profile/llmapi/keys/" + kid2).status_code, 404)
        self.assertEqual(ADMIN.delete("/api/admin/llmapi/" + kid2).status_code, 200)

    def test_wrong_or_missing_key(self):
        for h in ({}, {"Authorization": "Bearer falsch"}, {"Authorization": "Bearer sk-spark-" + "A" * 43}):
            r = self.lan.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "x"}]}, headers=h)
            self.assertEqual(r.status_code, 401, h)
        self.assertEqual(self.seen, [])


class Where(Base):
    def test_home_network_only(self):
        c, _ = profile("ApiLeo")
        token = self.key(c)
        self.assertEqual(self.ask(token).status_code, 200)
        self.assertEqual(self.ask(token, client=TestClient(panel.app, client=("8.8.8.8", 1))).status_code, 403)
        for h in ({"X-Forwarded-For": "192.168.178.9"}, {"X-Forwarded-Host": "speech.example.de"}, {"Forwarded": "for=1.2.3.4"}):
            self.assertEqual(self.ask(token, headers=h).status_code, 403, h)

    def test_outside_needs_switch_second_step_and_fresh_code(self):
        c, uid = profile("ApiOut")
        self.assertEqual(c.post("/api/profile/llmapi/keys", json={"name": "Weg", "where": "extern"}, headers=CODE).status_code, 403)
        helpers.set_config(llm_api_extern=True)
        self.assertEqual(c.post("/api/profile/llmapi/keys", json={"name": "Weg", "where": "extern"}, headers=CODE).status_code, 403)
        self.mfa_on.add(uid)
        self.assertEqual(c.post("/api/profile/llmapi/keys", json={"name": "Weg", "where": "extern"}).status_code, 428)
        token = self.key(c, where="extern")
        proxy = {"X-Forwarded-For": "8.8.8.8"}
        self.assertEqual(self.ask(token, headers=proxy).status_code, 200)
        helpers.set_config(llm_api_extern=False)   # switched off: no key from outside any more
        self.assertEqual(self.ask(token, headers=proxy).status_code, 403)

    def test_own_notaus_and_block(self):
        c, uid = profile("ApiStop")
        token = self.key(c)
        helpers.set_config(deny={"llmapi": [uid]})
        self.assertEqual(self.ask(token).status_code, 403)
        helpers.set_config(deny={})
        import notaus
        real = notaus.own
        notaus.own = lambda u: u == uid
        try:
            self.assertEqual(self.ask(token).status_code, 503)
        finally:
            notaus.own = real


class Guard(Base):
    def test_text_only_and_fields(self):
        c, _ = profile("ApiText")
        token = self.key(c)
        pic = [{"role": "user", "content": [{"type": "text", "text": "was ist das"},
                                              {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]}]
        for bad in ({"messages": pic}, {"messages": []}, {"messages": "x"}, {"n": 2},
                    {"max_tokens": llmapi.MAX_TOKENS + 1}, {"max_tokens": 0}, {"stream": "ja"},
                    {"messages": [{"role": "root", "content": "x"}]}):
            self.assertEqual(self.ask(token, **bad).status_code, 400, bad)
        self.assertEqual(self.seen, [])
        r = self.ask(token, model="sehen", logit_bias={"1": 100}, prompt_token_ids=[1, 2], top_logprobs=5,
                     chat_template_kwargs={"enable_thinking": True, "x": 1}, temperature=0.2)
        self.assertEqual(r.status_code, 200, r.text)
        url, heads, body = self.seen[-1]
        self.assertEqual(body["model"], "qwen-test")          # never "sehen" or "helfer"
        for k in ("logit_bias", "prompt_token_ids", "top_logprobs"):
            self.assertNotIn(k, body)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": True})
        self.assertEqual(body["max_tokens"], llmapi.MAX_TOKENS)
        self.assertEqual(heads.get(STAGE_HEADER), "0")        # stage "hinten": speech goes first
        self.assertTrue(url.startswith("http://127.0.0.1:31006/v1/"))

    def test_only_with_the_own_llm_tor(self):
        c, _ = profile("ApiTor")
        token = self.key(c)
        helpers.set_config(llm_url="http://192.168.178.9:30001/v1")
        self.assertEqual(self.ask(token).status_code, 503)
        self.assertEqual(self.seen, [])

    def test_streams_counts_and_logs_no_content(self):
        c, uid = profile("ApiStream")
        token = self.key(c)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.ask(token, stream=True)
            self.assertEqual(r.status_code, 200)
            self.assertIn("Hal", r.text)
            r = self.ask(token)
            self.assertEqual(r.json()["choices"][0]["message"]["content"], "Hallo")
            self.ask("sk-spark-" + "B" * 43)
        self.assertEqual(self.seen[0][2]["stream_options"], {"include_usage": True})
        log = out.getvalue()
        self.assertNotIn(SECRET, log)
        self.assertNotIn("Hallo", log)
        self.assertNotIn(token, log)
        self.assertIn("llmapi: antwort", log)
        self.assertIn("llmapi: abgelehnt schluessel", log)
        k = c.get("/api/profile/llmapi").json()["keys"][0]
        self.assertEqual(k["used"], 20)
        with open(llmapi._file()) as f:
            self.assertNotIn(SECRET, f.read())
        live = llmapi.for_live()
        self.assertTrue(live["on"])
        self.assertNotIn(SECRET, json.dumps(live) + llmapi.live_sub(live))


class Limits(Base):
    def test_per_minute_and_day_limit(self):
        c, _ = profile("ApiGrenze")
        helpers.set_config(llm_api_minute=2)
        token = self.key(c)
        self.assertEqual(self.ask(token).status_code, 200)
        self.assertEqual(self.ask(token).status_code, 200)
        self.assertEqual(self.ask(token).status_code, 429)
        llmapi._minute.clear()
        token2 = self.key(c, name="Klein", tag_k=1)
        kid = next(k for k in c.get("/api/profile/llmapi").json()["keys"] if k["name"] == "Klein")["id"]
        llmapi.count(kid, 1000)
        r = self.ask(token2)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["error"]["type"], "tageslimit")

    def test_at_once(self):
        c, _ = profile("ApiParallel")
        token = self.key(c)
        kid = c.get("/api/profile/llmapi").json()["keys"][0]["id"]
        llmapi._busy[kid] = llmapi.AT_ONCE
        self.assertEqual(self.ask(token).json()["error"]["type"], "gleichzeitig")

    def test_admin_always_unlimited(self):
        c, uid = profile("ApiChefin")
        self.admins.add(uid)
        helpers.set_config(llm_api_minute=1)
        token = self.key(c, tag_k=None)
        kid = c.get("/api/profile/llmapi").json()["keys"][0]["id"]
        llmapi.count(kid, 10 ** 7)
        llmapi._busy[kid] = llmapi.AT_ONCE
        for _ in range(3):
            self.assertEqual(self.ask(token).status_code, 200)
        self.assertTrue(c.get("/api/profile/llmapi").json()["unlimited"])


class Pure(unittest.TestCase):
    def test_clean_keeps_text_parts(self):
        out = llmapi.clean({"messages": [{"role": "user", "content": [{"type": "text", "text": "a"}]}], "max_tokens": 5})
        self.assertEqual(out["messages"][0]["content"], [{"type": "text", "text": "a"}])
        self.assertEqual(out["max_tokens"], 5)
        for bad in ({"messages": [{"role": "user", "content": [{"type": "input_audio"}]}]}, [], None):
            with self.assertRaises(ValueError):
                llmapi.clean(bad)

    def test_token_shape(self):
        self.assertIsNone(llmapi.find("spk_mcp_" + "a" * 40))
        self.assertIsNone(llmapi.find(None))


if __name__ == "__main__":
    asyncio.run(asyncio.sleep(0))
    unittest.main()


class FesterName(unittest.TestCase):
    """Dominik 2026-11-10 „1“: programs see one fixed name for the language model, the real one only as "modell";
    the panel asks again after llm.MODELS_TTL seconds, so a switch shows without a restart."""

    def test_fixed_name_real_model_and_a_switch_shows(self):
        import llm
        from common import LLM_ALIAS
        laeuft = {"id": "qwen36-35b-a3b-nvfp4"}

        def tor(request):
            return httpx.Response(200, json={"data": [{"id": LLM_ALIAS, "modell": laeuft["id"]}]})
        cc = {"llm_url": "http://127.0.0.1:31006/v1", "llm_key": ""}
        llm._models.clear()

        async def ask():
            async with httpx.AsyncClient(transport=httpx.MockTransport(tor)) as c:
                return await llm.model(c, cc)
        self.assertEqual(asyncio.run(ask()), LLM_ALIAS)
        self.assertEqual(llm.known_model(), "qwen36-35b-a3b-nvfp4")
        laeuft["id"] = "qwen38-27b-nvfp4"
        base = cc["llm_url"]
        t, name, real = llm._models[base]
        llm._models[base] = (t - llm.MODELS_TTL - 1, name, real)     # the time is up (no clock in the test)
        self.assertEqual(asyncio.run(ask()), LLM_ALIAS)
        self.assertEqual(llm.known_model(), "qwen38-27b-nvfp4")
        llm._models.clear()
