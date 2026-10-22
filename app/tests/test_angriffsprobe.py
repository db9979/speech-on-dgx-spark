"""Angriffsprobe (angriffsprobe.py, Werkstatt; Dominik 2026-10-22 „1“): the cases of angriffe.json against the real
model, played here by a fake model. Every case is wrapped like real outside text, offers only its reading and its
attacked tool, nothing runs, the result keeps only case ids and numbers, the page is for admins only and off by
default. Nothing depends on the time of day."""
import asyncio
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests import helpers

helpers.start()
import angriffsprobe  # noqa: E402
import chat  # noqa: E402
import llm  # noqa: E402
import mail  # noqa: E402

OBEY = {"dok-ha-offen", "mail-websuche-doppelgaenger", "web-gedaechtnis-offen"}


class _Antwort:
    def __init__(self, calls):
        self.calls = calls

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "Zusammenfassung.", "tool_calls": self.calls}}]}


class Probe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="angriffsprobe-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(angriffsprobe, "FILE", os.path.join(self.tmp, "a.json"))
        p.start()
        self.addCleanup(p.stop)
        self.data = angriffsprobe._all()
        self.sent = []

    def fake_post(self, obey=OBEY, fail=()):
        order = [f["id"] for f in angriffsprobe.faelle(self.data)]   # lauf asks the cases in this order

        async def post(c, ccfg, job, payload, who=None, speech_first=True):
            fid = order[len(self.sent)]
            self.sent.append((job, payload))
            names = [t["function"]["name"] for t in payload["tools"]]
            if fid in fail:
                raise OSError("down")
            ziel = names[1]
            return _Antwort([{"id": "c1", "type": "function", "function": {"name": ziel if fid in obey else names[0],
                                                                            "arguments": "{}"}}])
        return post

    def run_probe(self, **kw):
        async def model(c, ccfg, hdrs=None):
            return "qwen36-35b-a3b-nvfp4"
        with mock.patch.object(llm, "post", self.fake_post(**kw)), mock.patch.object(llm, "model", model), \
                redirect_stdout(io.StringIO()) as out:
            res = asyncio.run(angriffsprobe.lauf(now=1792600000))
        return res, out.getvalue()

    def test_every_disguise_has_its_name_and_every_case_its_tools(self):
        self.assertEqual(set(angriffsprobe.TARNUNG), set(self.data["verpackungen"]))
        tools = angriffsprobe._tools()
        cases = angriffsprobe.faelle(self.data)
        self.assertEqual({f["id"] for f in cases},
                         {f["id"] for f in self.data["faelle"] if f["eingang"] in tools and f["ziel"] in tools})
        self.assertGreaterEqual(len(cases), 20, "the reading-tool cases of the attack self-test")

    def test_a_case_is_wrapped_like_outside_text_and_offers_two_tools(self):
        for f in angriffsprobe.faelle(self.data):
            msgs, tools = angriffsprobe.nachrichten(f, self.data, {})
            self.assertEqual([t["function"]["name"] for t in tools], [f["eingang"], f["ziel"]], f["id"])
            result = msgs[-1]["content"]
            self.assertEqual(msgs[-1]["role"], "tool")
            self.assertTrue(result.startswith(mail.UNTRUSTED if f["eingang"].startswith("mail_") else chat.OUTSIDE_NOTE), f["id"])
            self.assertNotIn("<|im_start|>", result, "the markers are taken out as in a real turn")
            self.assertNotIn("<tool_call>", result)
            self.assertIn(f["ziel"], result, "the order names the attacked tool")

    def test_counts_only_ids_and_numbers(self):
        res, out = self.run_probe(fail={"verlauf-ha-unsichtbar"})
        n = len(angriffsprobe.faelle(self.data))
        self.assertEqual((res["gehorcht"], res["von"], res["fehler"]), (3, n - 1, 1))
        self.assertEqual(res["modell"], "qwen36-35b-a3b-nvfp4")
        self.assertEqual(res["zeit"], 1792600000)
        self.assertEqual(res["ziele"]["home_assistant_action"][0], 1)
        self.assertEqual(sum(v[0] for v in res["verpackungen"].values()), 3)
        self.assertEqual(sum(v[1] for v in res["ziele"].values()), n - 1)
        self.assertTrue(all(job == angriffsprobe.JOB for job, _ in self.sent))
        self.assertTrue(all(p["tools"] and len(p["tools"]) == 2 for _, p in self.sent))
        self.assertIn(f"werkstatt: angriffsprobe fertig 3 von {n - 1} gehorcht, 1 fehler", out)
        self.assertIn("werkstatt: angriffsprobe fall fehler OSError", out)
        with open(angriffsprobe.FILE, encoding="utf-8") as fh:
            kept = fh.read()
        for word in ("Ignoriere", "Kellerpumpe", "switch.keller", "ANGRIFF", "Zusammenfassung"):
            self.assertNotIn(word, kept, "only ids and numbers are kept, never a text")
        self.assertEqual(angriffsprobe.laeufe()[0]["id"], res["id"])

    def test_nothing_runs(self):
        calls, mem = len(helpers.HA_CALLS), len(helpers.LLM_CALLS)
        import chat_tools

        async def ran(*a, **kw):
            raise AssertionError("a tool ran")
        with mock.patch.object(chat_tools, "run", ran):
            res, _ = self.run_probe(obey={f["id"] for f in self.data["faelle"]})
        self.assertEqual(res["gehorcht"], res["von"])
        self.assertEqual(len(helpers.HA_CALLS), calls)
        self.assertEqual(len(helpers.LLM_CALLS), mem, "only the faked model was asked")

    def test_runs_are_kept_and_deleted(self):
        ids = [self.run_probe()[0]["id"] for _ in range(3)]
        self.assertEqual([r["id"] for r in angriffsprobe.laeufe()], ids[::-1], "newest first")
        self.assertTrue(angriffsprobe.weg(ids[1]))
        self.assertFalse(angriffsprobe.weg(ids[1]))
        self.assertEqual([r["id"] for r in angriffsprobe.laeufe()], [ids[2], ids[0]])
        kept = angriffsprobe.laeufe()
        with open(angriffsprobe.FILE, "w", encoding="utf-8") as fh:
            json.dump([{"id": "../x", "faelle": "Ignoriere"}] + kept * 15, fh)
        self.assertEqual(len(angriffsprobe.laeufe()), angriffsprobe.KEEP, "checked again, at most KEEP")


class Seite(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import panel
        import werkstatt
        import werkstattseite
        self.w = werkstattseite
        helpers.keep_chat(self, "werkstatt", "angriffsprobe")
        self.anon = TestClient(panel.app)
        self.admin = TestClient(panel.app)
        self.admin.post("/api/login", json={"password": "secret-admin"})
        self.tmp = tempfile.mkdtemp(prefix="angriffsprobe-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for mod, name, value in ((werkstatt, "WUNSCH", os.path.join(self.tmp, "w.json")),
                                 (werkstatt, "DATEN", os.path.join(self.tmp, "d.json")),
                                 (angriffsprobe, "FILE", os.path.join(self.tmp, "a.json")),
                                 (werkstattseite, "_im_gang", lambda: "inactive\ninactive\n")):
            p = mock.patch.object(mod, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.started = []

        async def lauf(now=None):
            self.started.append(1)
        p = mock.patch.object(angriffsprobe, "lauf", lauf)
        p.start()
        self.addCleanup(p.stop)

    def test_admin_only_and_off_by_default(self):
        for m, path in (("post", "/api/admin/werkstatt/angriffsprobe"),
                        ("delete", "/api/admin/werkstatt/angriffsprobe/0123456789ab")):
            self.assertIn(getattr(self.anon, m)(path).status_code, (401, 403), path)
        self.assertFalse(angriffsprobe.an(), "off by default")
        helpers.set_config(werkstatt=True)
        out = io.StringIO()
        with redirect_stdout(out):
            r = self.admin.post("/api/admin/werkstatt/angriffsprobe")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("Angriffsprobe ist aus", r.json()["detail"])
        self.assertIn("werkstatt: angriffsprobe abgelehnt aus", out.getvalue())
        self.assertFalse(self.admin.get("/api/admin/werkstatt").json()["probe"]["an"])
        self.assertEqual(self.started, [])

    def test_start_page_live_and_delete(self):
        helpers.set_config(werkstatt=True, angriffsprobe=True)
        out = io.StringIO()
        with redirect_stdout(out):
            r = self.admin.post("/api/admin/werkstatt/angriffsprobe")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("werkstatt: angriffsprobe gestartet", out.getvalue())
        d = r.json()["probe"]
        self.assertTrue(d["an"])
        self.assertEqual(set(d["tarnungen"]), set(angriffsprobe.TARNUNG))
        res = {"id": "0123456789ab", "zeit": 1792600000, "dauer_s": 60, "modell": "m", "version": "V01.0.1", "von": 23,
               "gehorcht": 4, "fehler": 0, "faelle": [], "verpackungen": {}, "ziele": {}}
        angriffsprobe.write_json(angriffsprobe.FILE, [res])
        self.assertEqual(self.admin.get("/api/admin/werkstatt").json()["probe"]["laeufe"][0]["gehorcht"], 4)
        self.assertEqual(self.w.live_sub({"da": True, "installiert": True, "probe": angriffsprobe.for_live()}),
                         "bereit · Angriffsprobe 4/23 gehorcht")
        with redirect_stdout(out):
            self.assertEqual(self.admin.delete("/api/admin/werkstatt/angriffsprobe/0123456789ab").json()["probe"]["laeufe"], [])
            self.assertEqual(self.admin.delete("/api/admin/werkstatt/angriffsprobe/0123456789ab").status_code, 404)
            self.assertEqual(self.admin.delete("/api/admin/werkstatt/angriffsprobe/zz").status_code, 404)
        self.assertIn("werkstatt: angriffsprobe weg ok", out.getvalue())
        self.assertIn("werkstatt: angriffsprobe weg keins", out.getvalue())


if __name__ == "__main__":
    unittest.main()
