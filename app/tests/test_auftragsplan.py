"""Aufträge mit Plan, Rückfrage und Vorschlag (auftragsplan.py): a job's plan, its one question, its one proposal that
only the person's Ja on exactly this proposal carries out, and Nachschieben. Off by default, the profile's own only.
Jobs run by hand with a scripted model (test_agent.Script); no test reads the clock of the day."""
import asyncio
import threading
import time
import unittest

from tests import helpers

helpers.start()
import agent  # noqa: E402
import auftragsplan  # noqa: E402
import panel  # noqa: E402
import tasks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_agent import Base, Script, allow, call, profile  # noqa: E402

agent.AUTO = False


def fresh(client, uid, task="Finde einen leisen Geschirrspüler"):
    agent.mutate(uid, lambda d: d.update(jobs=[], count=0))
    r = client.post("/api/profile/agent/jobs", json={"task": task})
    assert r.status_code == 200, r.text
    return r.json()["jobs"][0]["id"]


def tools_of(got, n=0):
    return set(got[n][1])


class Plus(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "agent_plan", "tasks", "reminders")

    def on(self, name):
        a, uid = profile(name)
        allow(a, uid)
        helpers.set_config(agent_plan=True)
        return a, uid

    def test_off_by_default(self):
        a, uid = profile("Plana")
        allow(a, uid)
        helpers.set_config(agent_plan=False)
        jid = fresh(a, uid)
        agent._llm = Script({"content": "Kurz.\n\nNichts."})
        asyncio.run(agent.run_job(uid, jid))
        self.assertFalse(tools_of(agent._llm.got) & set(auftragsplan.TOOLS))
        self.assertNotIn("job_plan", agent._llm.got[0][0][0]["content"])
        for path, body in (("answer", {"text": "A"}), ("steer", {"text": "B"}), ("proposal", {"yes": True, "h": "x"})):
            self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/{path}", json=body).status_code, 403)
        self.assertFalse(a.get("/api/profile/agent").json()["plan"])

    def test_plan_is_kept_short_and_never_in_the_steps(self):
        a, uid = self.on("Planb")
        jid = fresh(a, uid)
        steps = [f"Schritt {i} mit Geheimwort Zebra" for i in range(9)]
        agent._llm = Script({"content": "", "tool_calls": [call("job_plan", {"steps": steps, "done": 2})]},
                            {"content": "Kurz.\n\nFertig."})
        asyncio.run(agent.run_job(uid, jid))
        self.assertTrue({"job_plan", "job_ask", "job_propose"} <= tools_of(agent._llm.got))
        item = a.get(f"/api/profile/agent/jobs/{jid}").json()
        self.assertEqual(len(item["todo"]), auftragsplan.MAX_TODO)
        self.assertEqual([x["done"] for x in item["todo"]][:3], [True, True, False])
        self.assertNotIn("Zebra", " ".join(item["steps"]))          # the model's words stay in the plan only
        self.assertEqual(agent.job(uid, jid)["state"], "done")

    def test_question_waits_for_the_answer_of_its_own_profile(self):
        a, uid = self.on("Planc")
        b, _ = profile("Pland")
        jid = fresh(a, uid)
        agent._llm = Script({"content": "", "tool_calls": [call("job_ask", {"question": "Welches Budget?",
                                                                            "choices": ["400 Euro", "600 Euro"]})]},
                            {"content": "Kurz.\n\nFertig."})
        t = threading.Thread(target=lambda: asyncio.run(agent.run_job(uid, jid)))
        t.start()
        for _ in range(200):
            if (agent.job(uid, jid) or {}).get("ask") and (uid, jid) in auftragsplan._asks:
                break
            time.sleep(0.05)
        view = a.get(f"/api/profile/agent/jobs/{jid}").json()
        self.assertEqual(view["ask"]["choices"], ["400 Euro", "600 Euro"])
        self.assertTrue(any("Frage" in s[1] and "Budget" not in s[2] for s in self.sent))   # the push names no question
        self.assertEqual(b.post(f"/api/profile/agent/jobs/{jid}/answer", json={"text": "1 Euro"}).status_code, 404)
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/answer", json={"text": "600 Euro"}).status_code, 200)
        t.join(20)
        self.assertFalse(t.is_alive())
        tool_msgs = [m["content"] for m in agent._llm.got[1][0] if m["role"] == "tool"]
        self.assertEqual(tool_msgs, ["The user answered (their own words): 600 Euro"])
        item = agent.job(uid, jid)
        self.assertIsNone(item.get("ask"))
        self.assertEqual(item["asks"], [{"q": "Welches Budget?", "a": "600 Euro"}])
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/answer", json={"text": "x"}).status_code, 409)

    def test_question_without_answer_and_never_for_secrets(self):
        a, uid = self.on("Plane")
        jid = fresh(a, uid)
        old, auftragsplan.ASK_SECONDS = auftragsplan.ASK_SECONDS, 0.05
        self.addCleanup(setattr, auftragsplan, "ASK_SECONDS", old)
        agent._llm = Script({"content": "", "tool_calls": [call("job_ask", {"question": "Wie lautet dein Passwort?"}),
                                                          call("job_ask", {"question": "Welche Farbe?"}, "c2")]},
                            {"content": "Kurz.\n\nFertig."})
        asyncio.run(agent.run_job(uid, jid))
        tool_msgs = [m["content"] for m in agent._llm.got[1][0] if m["role"] == "tool"]
        self.assertIn("never asks for passwords", tool_msgs[0])
        self.assertTrue(tool_msgs[1].startswith("No answer came"))
        self.assertEqual(agent.job(uid, jid)["state"], "done")

    def test_scheduled_jobs_never_ask(self):
        a, uid = self.on("Planf")
        item, _ = agent.enqueue(uid, "Wochenbericht", origin="plan")
        self.assertNotIn("job_ask", auftragsplan.tools_for(uid, item))
        self.assertIn("job_plan", auftragsplan.tools_for(uid, item))
        self.assertEqual(auftragsplan.tools_for(uid, dict(item, origin="watch")), {})

    def test_proposal_only_after_yes_on_exactly_this_proposal(self):
        a, uid = self.on("Plang")
        b, _ = profile("Planh")
        helpers.set_config(tasks=True)
        jid = fresh(a, uid)
        agent._llm = Script({"content": "", "tool_calls": [call("reminder_list", {})]},
                            {"content": "", "tool_calls": [call("job_propose", {"kind": "list", "list": "einkauf",
                                                                                "text": "Klarspüler"}),
                                                           call("job_propose", {"kind": "list", "text": "Zweiter"}, "c2")]},
                            {"content": "Kurz: Klarspüler fehlt.\n\nMehr."})
        asyncio.run(agent.run_job(uid, jid))
        tool_msgs = [m["content"] for m in agent._llm.got[2][0] if m["role"] == "tool"]
        self.assertIn("one proposal at most", tool_msgs[-1])
        have = lambda: [x["text"] for x in tasks._load(uid)["items"] if x["list"] == "einkauf"]  # noqa: E731
        self.assertNotIn("Klarspüler", have())                      # nothing done by the job itself
        self.assertIn("Vorschlag wartet", self.sent[-1][2])
        p = a.get(f"/api/profile/agent/jobs/{jid}").json()["proposal"]
        self.assertTrue(p["open"] and p["outside"])                  # it read something before: marked
        self.assertIn("Klarspüler", p["text"])
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/proposal", json={"yes": True, "h": "0" * 16}).status_code, 409)
        self.assertEqual(b.post(f"/api/profile/agent/jobs/{jid}/proposal", json={"yes": True, "h": p["h"]}).status_code, 404)
        # a changed proposal (other text, same hash) is refused
        agent._set_job(uid, jid, proposal=dict(agent.job(uid, jid)["proposal"], text="Spülmaschine kaufen"))
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/proposal", json={"yes": True, "h": p["h"]}).status_code, 409)
        agent._set_job(uid, jid, proposal=dict(agent.job(uid, jid)["proposal"], text="Klarspüler"))
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/proposal", json={"yes": True, "h": p["h"]}).status_code, 200)
        self.assertIn("Klarspüler", have())
        self.assertEqual(agent.job(uid, jid)["proposal"]["done"], "ja")
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/proposal", json={"yes": True, "h": p["h"]}).status_code, 409)

    def test_no_and_old_proposals_do_nothing(self):
        a, uid = self.on("Plani")
        jid = fresh(a, uid)
        agent._llm = Script({"content": "", "tool_calls": [call("job_propose", {"kind": "list", "text": "Salz"})]},
                            {"content": "Kurz.\n\nFertig."})
        asyncio.run(agent.run_job(uid, jid))
        h = agent.job(uid, jid)["proposal"]["h"]
        self.assertFalse(agent.job(uid, jid)["proposal"]["outside"])
        before = len(tasks._load(uid)["items"])
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/proposal", json={"yes": False, "h": h}).status_code, 200)
        self.assertEqual(len(tasks._load(uid)["items"]), before)
        jid2 = fresh(a, uid)
        agent._llm = Script({"content": "", "tool_calls": [call("job_propose", {"kind": "list", "text": "Salz"})]},
                            {"content": "Kurz.\n\nFertig."})
        asyncio.run(agent.run_job(uid, jid2))
        agent._set_job(uid, jid2, finished=agent.job(uid, jid2)["finished"] - auftragsplan.PROPOSAL_SECONDS - 1)
        h2 = agent.job(uid, jid2)["proposal"]["h"]
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid2}/proposal", json={"yes": True, "h": h2}).status_code, 409)

    def test_proposals_are_checked_by_the_panel(self):
        a, uid = self.on("Planj")
        counts = {"all": 0}
        with self.assertRaises(ValueError):
            auftragsplan.proposal(uid, {"kind": "home_assistant", "text": "Licht aus"}, counts)
        with self.assertRaises(ValueError):
            auftragsplan.proposal(uid, {"kind": "reminder", "text": "Müll", "at": "2001-01-01T08:00"}, counts)
        helpers.set_config(tasks=False)
        with self.assertRaises(ValueError):
            auftragsplan.proposal(uid, {"kind": "list", "text": "Milch"}, counts)

    def test_steer_reaches_the_next_round_as_the_persons_words(self):
        a, uid = self.on("Plank")
        jid = fresh(a, uid)
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/steer", json={"text": "Nur Bosch"}).status_code, 409)  # waits
        agent._set_job(uid, jid, state="running")
        for i in range(auftragsplan.MAX_STEERS):
            self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/steer", json={"text": f"Nur Bosch {i}"}).status_code, 200)
        self.assertEqual(a.post(f"/api/profile/agent/jobs/{jid}/steer", json={"text": "mehr"}).status_code, 409)
        agent._set_job(uid, jid, state="queued")
        agent._llm = Script({"content": "Kurz.\n\nFertig."})
        asyncio.run(agent.run_job(uid, jid))
        users = [m["content"] for m in agent._llm.got[0][0] if m["role"] == "user"]
        self.assertEqual(users[1:], [f"Nachtrag des Nutzers zum Auftrag: Nur Bosch {i}" for i in range(3)])
        self.assertEqual(len(a.get(f"/api/profile/agent/jobs/{jid}").json()["notes"]), 3)
        self.assertEqual(TestClient(panel.app).post(f"/api/profile/agent/jobs/{jid}/steer", json={"text": "x"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
