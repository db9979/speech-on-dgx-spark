"""Zustand → Logs → Anfragen (V01.0.262, tracelog.py): off by default, only ways, tool names and numbers
(never question, answer, tool arguments or results), names only with the profile's own consent, admin only,
fixed ids and time ranges, old requests dropped. Fake LLM and TTS from helpers; no wall clock dependence.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import contextlib
import io
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
import tracelog  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SECRET = "Zitronenfalter"   # a word that may never reach a trace


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def set_trace(on):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c.setdefault("logs", {})["trace"] = on
    with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
        json.dump(c, f)


def ask(client, text):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": text}]})
    assert r.status_code == 200, r.text
    return helpers.events(r)


def items():
    return ADMIN.get("/api/admin/traces?minutes=60").json()["items"]


class Trace(unittest.TestCase):
    def setUp(self):
        tracelog.clear()
        set_trace(True)

    def tearDown(self):
        set_trace(False)
        tracelog.clear()

    def test_off_by_default_and_nothing_kept_while_off(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["logs"]["trace"], False)
        self.assertIs(profiles.SETTINGS["trace_name"][0], False)
        set_trace(False)
        ask(profile("Aus"), "Hallo")
        self.assertEqual(items(), [])

    def test_way_and_tools_without_any_text(self):
        a = profile("Weg")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ask(a, 'TOOL memory_save {"fact": "Weg mag ' + SECRET + '."}')
        x = items()[0]
        kinds = [s["k"] for s in x["steps"]]
        self.assertEqual(kinds[:3], ["in", "prep", "weiche"])
        self.assertEqual(kinds.count("llm"), 2)
        tool = next(s for s in x["steps"] if s["k"] == "tool")
        self.assertEqual(tool["n"], "memory_save")
        self.assertTrue(tool["x"]["ok"])
        self.assertIn("end", x["marks"])
        # no question, no arguments, no result, no answer: not in the API, not in the file, not in the journal
        with open(tracelog._file()) as f:
            stored = f.read()
        detail = ADMIN.get("/api/admin/traces/" + x["id"]).json()
        for text in (json.dumps(items(), ensure_ascii=False), stored, json.dumps({k: v for k, v in detail.items()
                                                                                   if k != "lines"}, ensure_ascii=False)):
            self.assertNotIn(SECRET, text)
            self.assertNotIn("Weg mag", text)
        line = next(ln for ln in buf.getvalue().splitlines() if ln.startswith("anfrage: "))
        self.assertIn("memory_save ok", line)
        self.assertNotIn(SECRET, line)
        self.assertNotIn("Weg", line)   # the journal never carries the profile's name

    def test_name_only_with_the_profiles_consent(self):
        a = profile("Zustimmung")
        ask(a, "Hallo")
        self.assertEqual(items()[0]["name"], "Profil")
        self.assertFalse(items()[0]["named"])
        self.assertEqual(a.put("/api/profile/settings", json={"trace_name": True}).status_code, 200)
        self.assertEqual(items()[0]["name"], "Zustimmung")   # also for requests from before
        a.put("/api/profile/settings", json={"trace_name": False})
        self.assertEqual(items()[0]["name"], "Profil")

    def test_device_key_cannot_give_consent(self):
        a = profile("Schluessel")
        uid = a.get("/api/whoami").json()["profile"]["id"]
        token = ADMIN.post("/api/admin/devices", json={"name": "Flur", "user": uid}).json()["token"]
        r = TestClient(panel.app).put("/api/profile/settings", json={"trace_name": True},
                                      headers={profiles.DEVICE_HEADER: token})
        self.assertIn(r.status_code, (401, 403))
        self.assertIsNot(profiles.settings(uid).get("trace_name"), True)

    def test_guest_is_gast(self):
        helpers.set_config(public=True)
        ask(TestClient(panel.app), "Hallo")
        self.assertEqual(items()[0]["name"], "Gast")
        self.assertEqual(items()[0]["device"], "")

    def test_a_tool_the_model_made_up_keeps_no_name(self):
        ask(profile("Erfunden"), "TOOL !" + SECRET + "_tool {}")
        steps = items()[0]["steps"]
        self.assertNotIn(SECRET, json.dumps(steps))
        self.assertTrue(any(s["n"] == "unbekannt" for s in steps if s["k"] in ("tool", "llm")) or
                        any("unbekannt" in str((s.get("x") or {}).get("calls")) for s in steps))

    def test_admin_only_and_fixed_values(self):
        self.assertIn(TestClient(panel.app).get("/api/admin/traces").status_code, (401, 403))
        self.assertIn(profile("Neugierig").get("/api/admin/traces").status_code, (401, 403))
        self.assertIn(TestClient(panel.app).delete("/api/admin/traces").status_code, (401, 403))
        self.assertEqual(ADMIN.get("/api/admin/traces?minutes=7").status_code, 400)
        self.assertEqual(ADMIN.get("/api/admin/traces/../../etc").status_code, 404)
        self.assertEqual(ADMIN.get("/api/admin/traces/ZZZZZZ").status_code, 400)
        self.assertEqual(ADMIN.get("/api/admin/traces/abcdef").status_code, 404)

    def test_switch_must_be_a_bool(self):
        r = ADMIN.get("/api/config").json()
        r["logs"]["trace"] = "ja"
        self.assertEqual(ADMIN.put("/api/config", json=r).status_code, 400)

    def test_clear(self):
        ask(profile("Weg2"), "Hallo")
        self.assertEqual(len(items()), 1)
        self.assertEqual(ADMIN.delete("/api/admin/traces").status_code, 200)
        self.assertEqual(items(), [])


class Record(unittest.TestCase):
    """The record itself, with fixed times (no wall clock)."""

    def test_only_fixed_words_and_numbers(self):
        r = tracelog.Rec(1000.0, "nonsense", who="../x", kind="root", device="Küche <b>")
        self.assertEqual((r.client, r.who, r.kind, r.device), ("other", None, "guest", ""))
        r.step("tool", "web_search", 1000.5, 1001.0, ok=True, chars=12, text="a\nb", BAD=1, extra={"x": 1})
        r.step("nope", "x", 1000.0)
        r.step("tool", "<script>", 1000.0)
        self.assertEqual(r.steps[0], {"k": "tool", "n": "web_search", "a": 500, "d": 500, "x": {"ok": True, "chars": 12}})
        self.assertEqual(r.steps[1]["n"], "unbekannt")
        self.assertEqual(len(r.steps), 2)
        for i in range(100):
            r.step("llm", "Runde", 1000.0)
        self.assertEqual(len(r.steps), tracelog.MAX_STEPS)
        r.fail("tts_error")
        r.fail("Bad Code!")
        self.assertEqual(r.errors, ["tts_error"])

    def test_status(self):
        r = tracelog.Rec(0.0, "web")
        r.mark("sound", 2.0)
        r.mark("end", 9.0)
        self.assertEqual(r.status(), "ok")
        r2 = tracelog.Rec(0.0, "web")
        r2.mark("sound", tracelog.SLOW_S + 1)
        self.assertEqual(r2.status(), "slow")
        r2.fail("llm_down")
        self.assertEqual(r2.status(), "err")

    def test_old_requests_are_dropped(self):
        now = 1_000_000.0
        rows = [{"id": "a00001", "t": now - tracelog.KEEP_S - 5}, {"id": "a00002", "t": now - 10}]
        self.assertEqual([x["id"] for x in tracelog._keep(rows, now)], ["a00002"])
        many = [{"id": f"{i:06x}", "t": now - 1} for i in range(tracelog.MAX_TRACES + 50)]
        self.assertEqual(len(tracelog._keep(many, now)), tracelog.MAX_TRACES)


if __name__ == "__main__":
    unittest.main()
