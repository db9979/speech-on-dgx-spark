"""Eigene Aufgaben (plan „Eigene Aufgaben“, Variante 3): watches that report only what is new (beobachten.py), the
panel's check of every find, the proposal by voice with a fixed sentence and the person's "Ja", changing by voice and
on the page, and one list under Ich → Aufträge with scheduled jobs, repeating reminders, smart home rules and mail
senders. Off until the admin allows it, never for guests. No test reads the clock."""
import asyncio
import json
import unittest

from tests import helpers
from tests.test_agent import Base, Script, allow, ask, profile
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()
import agent  # noqa: E402
import beobachten  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

agent.AUTO = False
FIRMWARE = "Sag mir Bescheid, wenn es eine neue Firmware für meine FRITZ!Box gibt"
PAGE = "https://avm.de/service/downloads/fritzbox-7590"
TEXT = "FRITZ!Box 7590 – Downloads. Aktuelle Version: FRITZ!OS 8.10 vom 2. Oktober. Hinweise zur Installation."
DAY = 86400


def watch_plan(uid, **extra):
    import chat
    zone = chat.user_zone(profiles.settings(uid).get("tz", ""))
    w = dict(beobachten.parse(FIRMWARE), kind="watch", **extra)
    return agent.add_plan(uid, dict(agent.parse_plan(w, zone), created_by="page"))


def run_of(uid, pid):
    item, why = agent.enqueue(uid, "Firmware suchen", origin="watch", plan=pid)
    assert item, why
    return item["id"]


def plan_of(uid, pid):
    return next(x for x in agent.load(uid)["plans"] if x["id"] == pid)


class Words(unittest.TestCase):
    def test_sentences_become_watches_others_not(self):
        p = beobachten.parse(FIRMWARE)
        self.assertEqual((p["title"], p["repeat"], p["time"]), ("Neue Firmware für FRITZ!Box", "daily", "08:00"))
        p = beobachten.parse("Sag mir jeden Montag um 7 Uhr Bescheid, wenn es eine neue Folge von Hard Fork gibt")
        self.assertEqual((p["repeat"], p["weekday"], p["time"]), ("weekly", 0, "07:00"))
        p = beobachten.parse("Melde dich, sobald der Flug nach Rom unter 100 Euro kostet")
        self.assertEqual(p["below"], 100.0)
        self.assertEqual(beobachten.parse("Behalte den Preis der Bauknecht B6R 88 im Auge")["title"], "Preis der Bauknecht B6R 88")
        # the smart home, a fixed time, a plain reminder and a change of a watch there is: no new watch
        for text in ("Sag mir Bescheid, wenn die Haustür aufgeht", "Erinnere mich in 10 Minuten an den Herd",
                     "Erinnere mich morgen an den Müll", "Beobachte das lieber jeden Montag", "Beobachte das",
                     "x" * 401 + " sag mir Bescheid, wenn es eine neue Firmware gibt"):
            self.assertIsNone(beobachten.parse(text), text)
        self.assertTrue(beobachten.wants(FIRMWARE))
        self.assertFalse(beobachten.wants("Sag mir Bescheid, wenn die Waschmaschine fertig ist"))
        self.assertEqual(beobachten.mail_sender("Sag mir Bescheid, wenn eine Mail von der Sparkasse kommt"), "Sparkasse")
        self.assertEqual(beobachten.amount("jetzt 1.299,00 €"), 1299.0)
        self.assertEqual(beobachten.amount("nur 479 Euro"), 479.0)

    def test_routes_to_the_agent_not_to_search_or_reminder(self):
        import intent
        for text in (FIRMWARE, "Erinnere mich, wenn du im Internet eine neue Firmware für meine FRITZ!Box findest"):
            r = intent.classify(text)
            self.assertEqual(r.names, ["agent"], r.why)
        self.assertIn("agent_watch", intent.GROUPS["agent"][0])


class Check(unittest.TestCase):
    """The panel decides what is new, never the model."""
    SEEN = {"pages": {PAGE: TEXT}, "searches": []}

    def test_only_checked_finds_count(self):
        good = f"FUND: FRITZ!OS 8.10 | {PAGE} | Aktuelle Version: FRITZ!OS 8.10 vom 2. Oktober"
        v = beobachten.check("Bericht\n\n" + good, self.SEEN)
        self.assertEqual([f["v"] for f in v["new"]], ["FRITZ!OS 8.10"])
        self.assertEqual(v["dropped"], 0)
        # a quote that is not on the page, an address not read in this run, a value not in its quote
        for bad in (f"FUND: FRITZ!OS 8.20 | {PAGE} | Aktuelle Version: FRITZ!OS 8.20 vom 9. Oktober",
                    "FUND: FRITZ!OS 8.10 | https://example.org/fake | Aktuelle Version: FRITZ!OS 8.10 vom 2. Oktober",
                    f"FUND: FRITZ!OS 9.00 | {PAGE} | Aktuelle Version: FRITZ!OS 8.10 vom 2. Oktober",
                    f"FUND: 8.10 | ftp://avm.de/x | Aktuelle Version: FRITZ!OS 8.10 vom 2. Oktober",
                    "FUND: nur zwei | Teile"):
            v = beobachten.check(bad, self.SEEN)
            self.assertEqual(v["new"], [], bad)
        # an address a search returned counts with the search text
        v = beobachten.check(good, {"pages": {}, "searches": [f"1. Downloads ({PAGE})\n{TEXT}"]})
        self.assertEqual(len(v["new"]), 1)
        # known values are old, a value twice is one find
        v = beobachten.check(good + "\n" + good, self.SEEN, known=["FRITZ!OS 8.10"])
        self.assertEqual((v["new"], len(v["old"])), ([], 1))
        # injected text in a find never gets past the fixed words of the notification
        title, body = beobachten.push_text({"title": "Neue Firmware"}, [{"v": "FRITZ!OS 8.10", "src": PAGE, "q": "x"}])
        self.assertEqual(title, "🔔 Neu gefunden: Neue Firmware")
        self.assertEqual(body, "FRITZ!OS 8.10 (avm.de).\nEigene Aufgabe „Neue Firmware“ · Öffnen: Ich → Aufträge")

    def test_price_limit(self):
        page = "https://shop.example/b6r88"
        seen = {"pages": {page: "Bauknecht B6R 88 jetzt für 479,00 € statt 549,00 €"}}
        line = f"FUND: 479,00 € | {page} | jetzt für 479,00 € statt 549,00 €"
        self.assertEqual(len(beobachten.check(line, seen, below=500)["new"]), 1)
        self.assertEqual(beobachten.check(line, seen, below=450)["new"], [])
        self.assertEqual(beobachten.check(f"FUND: günstig | {page} | jetzt günstig", seen, below=500)["new"], [])

    def test_history_and_idle(self):
        p = {"created": 1000}
        for i in range(beobachten.MAX_HIST + 5):
            beobachten.note(p, "still", "", 0, now=2000 + i)
        self.assertEqual(len(p["hist"]), beobachten.MAX_HIST)
        beobachten.note(p, "neu", "8.10", 1, now=2000 + 15 * DAY)
        self.assertEqual(len(p["hist"]), 1)           # older than HIST_DAYS goes
        self.assertFalse(beobachten.idle(p, now=1000 + beobachten.IDLE_DAYS * DAY))
        self.assertTrue(beobachten.idle(p, now=1001 + beobachten.IDLE_DAYS * DAY))
        self.assertFalse(beobachten.idle(dict(p, last_hit=5000), now=1001 + beobachten.IDLE_DAYS * DAY))
        beobachten.remember(p, [{"v": "a", "src": PAGE}] * 2 + [{"v": f"v{i}", "src": PAGE} for i in range(60)], now=1)
        self.assertEqual(len(p["known"]), beobachten.MAX_KNOWN)


class Access(Base):
    def tearDown(self):
        super().tearDown()
        helpers.set_config(agent_watch=False, proactive=False)

    def test_off_by_default_and_never_for_guests(self):
        a, uid = profile("AufWanda")   # own names: test_panel and test_many_users use Wanda and Xaver
        allow(a, uid)
        agent.mutate(uid, lambda d: d.update(plans=[], jobs=[]))
        agent.drop_pending(uid)
        # agent functions on, watching not: no proposal, no tool, no watch from the page
        ask(a, FIRMWARE)
        self.assertIsNone(agent.pending(uid))
        self.assertIn("NO TOOL agent_watch", ask(a, 'TOOL agent_watch {"task": "' + FIRMWARE + '"}'))
        r = a.post("/api/profile/agent/plans", json={"kind": "watch", "task": "Firmware", "repeat": "daily", "time": "08:00"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(a.get("/api/profile/agent").json()["watch"])
        helpers.set_config(agent=True, agent_watch=True)
        self.assertTrue(a.get("/api/profile/agent").json()["watch"])
        # guests never, even with the assistant open to everybody
        helpers.set_config(agent=True, agent_watch=True, public=True)
        guest = TestClient(panel.app)
        ask(guest, FIRMWARE)
        self.assertIn("NO TOOL agent_watch", ask(guest, 'TOOL agent_watch {"task": "' + FIRMWARE + '"}'))
        self.assertEqual(guest.get("/api/profile/agent").status_code, 401)
        # the admin's agent switch wins: the list and its changes are closed
        helpers.set_config(agent=False, agent_watch=True)
        self.assertFalse(agent.watch_on(uid))
        for r in (a.get("/api/profile/agent"), a.post("/api/profile/agent/reminders/x/pause"),
                  a.put("/api/profile/agent/mail", json={"add": "Bank"}), a.post("/api/profile/agent/rules/x/pause")):
            self.assertEqual(r.status_code, 403)

    def test_other_profiles_never_reach_a_watch(self):
        a, uid = profile("AufXaver")
        b, uid_b = profile("Yvana")
        allow(a, uid)
        allow(b, uid_b)
        helpers.set_config(agent=True, agent_watch=True)
        agent.mutate(uid, lambda d: d.update(plans=[], jobs=[]))
        pid = watch_plan(uid)["id"]
        self.assertEqual(b.put(f"/api/profile/agent/plans/{pid}", json={"time": "09:00"}).status_code, 404)
        self.assertEqual(b.post(f"/api/profile/agent/plans/{pid}/run").status_code, 400)
        self.assertEqual(plan_of(uid, pid)["time"], "08:00")
        # a device key never changes tasks
        key = ADMIN().post("/api/admin/devices", json={"name": "Uhr", "user": uid}).json()["token"]
        dev = TestClient(panel.app, headers={profiles.DEVICE_HEADER: key})
        self.assertEqual(dev.put(f"/api/profile/agent/plans/{pid}", json={"time": "09:00"}).status_code, 403)
        self.assertEqual(dev.put("/api/profile/agent/mail", json={"add": "Bank"}).status_code, 403)


def ADMIN():
    c = TestClient(panel.app)
    c.post("/api/login", json={"password": "secret-admin"})
    return c


class Voice(Base):
    def setUp(self):
        super().setUp()
        self.a, self.uid = profile("Zorela")
        allow(self.a, self.uid)
        helpers.set_config(agent=True, agent_watch=True)
        agent.mutate(self.uid, lambda d: d.update(plans=[], jobs=[], count=0))
        agent.drop_pending(self.uid)

    def tearDown(self):
        super().tearDown()
        helpers.set_config(agent_watch=False)

    def test_watch_only_after_yes_with_the_panels_sentence(self):
        n = len(helpers.LLM_CALLS)
        ask(self.a, FIRMWARE)
        p = agent.pending(self.uid)
        self.assertEqual(p["kind"], "watch")
        self.assertEqual(p["plan"]["title"], "Neue Firmware für FRITZ!Box")
        system = "\n".join(m["content"] for c in helpers.LLM_CALLS[n:] for m in c["messages"] if m["role"] == "system")
        self.assertIn("Soll ich das so anlegen", system)
        self.assertEqual(agent.load(self.uid)["plans"], [])
        ask(self.a, "Nein")
        self.assertEqual(agent.load(self.uid)["plans"], [])
        ask(self.a, FIRMWARE)
        ask(self.a, "Ja")
        plans = agent.load(self.uid)["plans"]
        self.assertEqual([(x["kind"], x["created_by"], x["title"]) for x in plans],
                         [("watch", "voice", "Neue Firmware für FRITZ!Box")])
        # at most MAX_WATCH watches
        for _ in range(beobachten.MAX_WATCH - 1):
            watch_plan(self.uid)
        ask(self.a, FIRMWARE)
        self.assertIsNone(agent.pending(self.uid))

    def test_change_by_voice_after_yes_and_undo(self):
        pid = watch_plan(self.uid)["id"]
        ask(self.a, 'TOOL agent_change {"action": "edit", "plan": "Firmware", "repeat": "weekly", "weekday": 0, '
                    '"time": "07:00", "x": "änder den Plan"}')
        p = agent.pending(self.uid)
        self.assertEqual(p["kind"], "plan_edit")
        self.assertEqual(plan_of(self.uid, pid)["repeat"], "daily")
        ask(self.a, "Ja")
        after = plan_of(self.uid, pid)
        self.assertEqual((after["repeat"], after["weekday"], after["time"], after["kind"]), ("weekly", 0, "07:00", "watch"))
        # „Mach das rückgängig“ puts the old times back
        import aendern
        entry = aendern.last(self.uid)
        self.assertEqual(entry["kind"], "plan")
        asyncio.run(aendern.undo(self.uid, entry, {}))
        back = plan_of(self.uid, pid)
        self.assertEqual((back["repeat"], back["time"], back["kind"]), ("daily", "08:00", "watch"))

    def test_mail_sender_after_yes(self):
        helpers.set_config(agent=True, agent_watch=True, proactive=True)
        self.a.put("/api/profile/settings", json={"pro_on": True})
        try:
            ask(self.a, "Sag mir Bescheid, wenn eine Mail von der Sparkasse kommt")
            self.assertEqual(agent.pending(self.uid)["kind"], "mail_from")
            ask(self.a, "Ja")
            self.assertIn("Sparkasse", agent.senders(self.uid))
        finally:
            helpers.set_config(proactive=False)
            profiles.save_settings(self.uid, {"pro_mail_from": ""})


class Runs(Base):
    def setUp(self):
        super().setUp()
        self.a, self.uid = profile("Verla")
        allow(self.a, self.uid)
        helpers.set_config(agent=True, agent_watch=True)
        agent.mutate(self.uid, lambda d: d.update(plans=[], jobs=[], count=0))
        self.pid = watch_plan(self.uid)["id"]

    def tearDown(self):
        super().tearDown()
        helpers.set_config(agent_watch=False)

    def done(self, report, pages=None):
        jid = run_of(self.uid, self.pid)
        agent._set_job(self.uid, jid, state="done", report=report)
        return jid, asyncio.run(agent.watch_done(self.uid, jid, report, {"pages": pages or {}, "searches": []}))

    def test_new_once_then_quiet(self):
        line = f"Gefunden.\n\nFUND: FRITZ!OS 8.10 | {PAGE} | Aktuelle Version: FRITZ!OS 8.10 vom 2. Oktober"
        jid, r = self.done(line, {PAGE: TEXT})
        self.assertEqual(r, "neu")
        self.assertEqual(self.sent[-1][1], "🔔 Neu gefunden: Neue Firmware für FRITZ!Box")
        self.assertIn("FRITZ!OS 8.10 (avm.de)", self.sent[-1][2])
        self.assertEqual(agent.job(self.uid, jid)["finds"][0]["v"], "FRITZ!OS 8.10")
        p = plan_of(self.uid, self.pid)
        self.assertEqual([k["v"] for k in p["known"]], ["FRITZ!OS 8.10"])
        self.assertEqual(p["hist"][0]["r"], "neu")
        # the same find again: quiet, no notification, the run leaves only its history line
        n = len(self.sent)
        jid, r = self.done(line, {PAGE: TEXT})
        self.assertEqual(r, "still")
        self.assertEqual(len(self.sent), n)
        self.assertIsNone(agent.job(self.uid, jid))
        self.assertEqual(plan_of(self.uid, self.pid)["hist"][0]["r"], "still")
        # a made-up find (page not read in this run) stays quiet too
        _, r = self.done(f"FUND: FRITZ!OS 9.00 | {PAGE} | Aktuelle Version: FRITZ!OS 9.00")
        self.assertEqual((r, len(self.sent)), ("still", n))
        # „Bekanntes vergessen“ on the page: the next find is new again
        self.a.put(f"/api/profile/agent/plans/{self.pid}", json={"forget": True})
        self.assertEqual(self.done(line, {PAGE: TEXT})[1], "neu")

    def test_report_every_time_when_asked(self):
        agent.edit_plan(self.uid, self.pid, {"only_new": False})
        n = len(self.sent)
        _, r = self.done("Nichts Neues bei AVM.\n\nKEIN FUND")
        self.assertEqual(r, "bericht")
        self.assertEqual(len(self.sent), n + 1)

    def test_pauses_itself_after_failures_and_when_idle(self):
        for i in range(beobachten.FAILS):
            self.assertEqual(self.done("")[1], "fehler")
        p = plan_of(self.uid, self.pid)
        self.assertEqual((p["paused"], p["why"]), (True, "fehler"))
        self.assertEqual(self.sent[-1][1], "⏸ Beobachtung pausiert")
        self.assertIn("Ich → Aufträge", self.sent[-1][2])
        # a paused watch is not due; turned on again on the page it runs again
        asyncio.run(agent.due_once(now=p["next"] + 30))
        self.assertFalse(any(j.get("plan") == self.pid and j["state"] == "queued" for j in agent.load(self.uid)["jobs"]))
        self.a.post(f"/api/profile/agent/plans/{self.pid}/pause")
        p = plan_of(self.uid, self.pid)
        self.assertEqual((p.get("paused"), p.get("why"), p.get("fails")), (False, None, 0))
        # nothing new for IDLE_DAYS: pauses itself and says why
        agent.mutate(self.uid, lambda d: [x.update(created=1000, last_hit=0) for x in d["plans"]])
        self.assertEqual(self.done("KEIN FUND")[1], "still")
        p = plan_of(self.uid, self.pid)
        self.assertEqual((p["paused"], p["why"]), (True, "idle"))

    def test_job_gets_the_rules_and_the_known_values(self):
        agent.mutate(self.uid, lambda d: [x.update(known=[{"v": "FRITZ!OS 8.00", "src": PAGE, "t": 1}], below=None)
                                          for x in d["plans"]])
        jid = run_of(self.uid, self.pid)
        agent._llm = Script({"content": f"FUND: FRITZ!OS 8.10 | {PAGE} | Aktuelle Version: FRITZ!OS 8.10"})
        asyncio.run(agent.run_job(self.uid, jid))
        system = agent._llm.got[0][0][0]["content"]
        self.assertIn("FUND:", system)
        self.assertIn("Schon bekannt (nicht neu): FRITZ!OS 8.00", agent._llm.got[0][0][1]["content"])
        self.assertEqual(plan_of(self.uid, self.pid)["hist"][0]["r"], "still")   # the page was never read
        self.assertEqual(self.sent, [])

    def test_run_now_once(self):
        r = self.a.post(f"/api/profile/agent/plans/{self.pid}/run")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(any(j.get("plan") == self.pid and j["origin"] == "watch" for j in agent.load(self.uid)["jobs"]))
        self.assertEqual(self.a.post(f"/api/profile/agent/plans/{self.pid}/run").status_code, 400)

    def test_page_edit_checks_its_input(self):
        r = self.a.put(f"/api/profile/agent/plans/{self.pid}", json={"time": "06:30", "below": 99.5, "title": "AVM"})
        self.assertEqual(r.status_code, 200, r.text)
        p = plan_of(self.uid, self.pid)
        self.assertEqual((p["time"], p["below"], p["title"], p["kind"]), ("06:30", 99.5, "AVM", "watch"))
        for bad in ({"time": "25:00"}, {"repeat": "hourly"}, {"below": -5}, {"task": ""}):
            self.assertEqual(self.a.put(f"/api/profile/agent/plans/{self.pid}", json=bad).status_code, 400, bad)
        self.assertEqual(self.a.put(f"/api/profile/agent/plans/{self.pid}", json={"on": False}).status_code, 200)
        self.assertTrue(plan_of(self.uid, self.pid)["paused"])
        big = self.a.put(f"/api/profile/agent/plans/{self.pid}", content=json.dumps({"task": "x" * 9000}),
                         headers={"content-type": "application/json"})
        self.assertIn(big.status_code, (400, 413))


class OwnTasks(Base):
    def setUp(self):
        super().setUp()
        self.a, self.uid = profile("Uschi")
        allow(self.a, self.uid)
        helpers.set_config(agent=True, reminders=True)

    def tearDown(self):
        super().tearDown()
        helpers.set_config(proactive=False)

    def test_repeating_reminder_pause_change_delete(self):
        profiles.remove_reminders(self.uid, {x["id"] for x in profiles.reminders(self.uid)})
        once = profiles.add_reminder(self.uid, "Zahnarzt", 4102444800000, "")
        item = profiles.add_reminder(self.uid, "Müll rausbringen", 4102444800000, "weekly")
        own = self.a.get("/api/profile/agent").json()["own"]
        self.assertEqual([x["text"] for x in own["reminders"]], ["Müll rausbringen"])   # only repeating ones
        # paused: out of reminders.json (no device rings it), kept under Ich → Aufträge
        self.assertEqual(self.a.post(f"/api/profile/agent/reminders/{item['id']}/pause").status_code, 200)
        self.assertNotIn(item["id"], [x["id"] for x in profiles.reminders(self.uid)])
        own = self.a.get("/api/profile/agent").json()["own"]
        self.assertEqual([(x["text"], x["paused"]) for x in own["reminders"]], [("Müll rausbringen", True)])
        self.a.post(f"/api/profile/agent/reminders/{item['id']}/pause")
        back = [x for x in profiles.reminders(self.uid) if x["text"] == "Müll rausbringen"]
        self.assertEqual(len(back), 1)
        self.assertEqual(self.a.get("/api/profile/agent").json()["own"]["reminders"][0]["paused"], False)
        # changed: new text and time
        r = self.a.put(f"/api/profile/agent/reminders/{back[0]['id']}", json={"text": "Gelbe Tonne", "time": "19:30"})
        self.assertEqual(r.status_code, 200, r.text)
        new = next(x for x in profiles.reminders(self.uid) if x.get("every") == "weekly")
        self.assertEqual(new["text"], "Gelbe Tonne")
        self.assertEqual(self.a.put(f"/api/profile/agent/reminders/{new['id']}", json={"time": "7 Uhr"}).status_code, 400)
        self.assertEqual(self.a.put(f"/api/profile/agent/reminders/{once['id']}", json={"text": "x"}).status_code, 400)
        self.assertEqual(self.a.post(f"/api/profile/agent/reminders/{once['id']}/pause").status_code, 404)
        self.a.delete(f"/api/profile/agent/reminders/{new['id']}")
        self.assertEqual([x["text"] for x in profiles.reminders(self.uid)], ["Zahnarzt"])
        profiles.remove_reminders(self.uid, {once["id"]})

    def test_rules_pause_and_mail_senders(self):
        import proactive
        helpers.set_config(agent=True, proactive=True)
        self.a.put("/api/profile/settings", json={"pro_on": True})
        proactive._save_rules(self.uid, [{"id": "r1", "text": "Haustür offen", "minutes": 0,
                                          "conds": [{"entity": "binary_sensor.haustuer", "op": "is", "value": "on"}]}])
        try:
            own = self.a.get("/api/profile/agent").json()["own"]
            self.assertEqual([(x["id"], x["paused"]) for x in own["rules"]], [("r1", False)])
            self.assertEqual(self.a.post("/api/profile/agent/rules/r1/pause").status_code, 200)
            self.assertTrue(proactive.rules(self.uid)[0]["paused"])
            self.assertEqual(self.a.post("/api/profile/agent/rules/nope/pause").status_code, 404)
            self.a.post("/api/profile/agent/rules/r1/pause")
            self.assertNotIn("paused", proactive.rules(self.uid)[0])
            # mail senders of „Von selbst melden“
            self.assertEqual(self.a.put("/api/profile/agent/mail", json={"add": "Sparkasse"}).status_code, 200)
            self.a.put("/api/profile/agent/mail", json={"add": "sparkasse "})
            self.assertEqual(self.a.get("/api/profile/agent").json()["own"]["mail"], ["Sparkasse"])
            self.assertEqual(self.a.put("/api/profile/agent/mail", json={}).status_code, 400)
            codes = [self.a.put("/api/profile/agent/mail", json={"add": f"Absender {i} " + "x" * 70}).status_code
                     for i in range(5)]
            self.assertEqual(codes, [200, 200, 200, 400, 400])     # the list holds at most 300 characters
            for i in range(3):
                self.a.put("/api/profile/agent/mail", json={"remove": f"Absender {i} " + "x" * 70})
            self.a.put("/api/profile/agent/mail", json={"remove": "SPARKASSE"})
            self.assertEqual(agent.senders(self.uid), [])
        finally:
            proactive._save_rules(self.uid, [])
            profiles.save_settings(self.uid, {"pro_mail_from": ""})


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    """Ich → Aufträge: one list with a detail, fits 320, 390 and 1280 px, nothing scrolls sideways."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Aufgabenseite", "4711")
        except Exception:
            pass

    def tearDown(self):
        helpers.set_config(agent=False, agent_watch=False)

    async def page(self, p, w, h):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/profile/login",
                                                data={"name": "Aufgabenseite", "pin": "4711"})).status, 200)
        uid = (await (await pg.request.get(base + "/api/whoami")).json())["profile"]["id"]
        helpers.set_config(agent=True, agent_watch=True, reminders=True)
        agent.mutate(uid, lambda d: d.update(plans=[], jobs=[], rem_paused=[]))
        r = ADMIN().put("/api/admin/agent/levels", json={"levels": dict(agent.admin_state()["levels"], **{uid: "read"})})
        self.assertEqual(r.status_code, 200, r.text)
        pid = watch_plan(uid)["id"]
        agent.mutate(uid, lambda d: [x.update(known=[{"v": "FRITZ!OS 8.10", "src": PAGE + "/" + "a" * 120, "t": 1}],
                                              hist=[{"t": 1, "r": "neu", "n": 1, "what": "FRITZ!OS 8.10"}])
                                     for x in d["plans"] if x["id"] == pid])
        import chat
        zone = chat.user_zone("")
        agent.add_plan(uid, agent.parse_plan({"task": "Fass mir jeden Montag die Termine der Woche zusammen",
                                              "repeat": "weekly", "weekday": 0, "time": "07:00"}, zone))
        profiles.remove_reminders(uid, {x["id"] for x in profiles.reminders(uid)})
        profiles.add_reminder(uid, "Müll rausbringen", 4102444800000, "weekly")
        await pg.goto(base + "/")
        await pg.wait_for_timeout(600)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        return br, pg, errors, uid

    async def fits(self, pg, what):
        over = await pg.evaluate("(()=>{const b=document.querySelector('#profmodal .mebody');return b.scrollWidth-b.clientWidth})()")
        self.assertLessEqual(over, 0, what)

    def test_list_and_detail_fit(self):
        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 900), (390, 844), (320, 640)):
                    br, pg, errors, uid = await self.page(p, w, h)
                    try:
                        await pg.evaluate("openMe('agentbox')")
                        await pg.wait_for_selector("#agld [data-agrow]")
                        rows = await pg.evaluate("[...document.querySelectorAll('#agld [data-agrow]')].map(r=>r.dataset.agrow.split(':')[0])")
                        self.assertEqual(sorted(rows), ["plan", "rem", "watch"], w)
                        tab = await pg.evaluate("document.querySelector('#agentbox .ic-tabs button').textContent")
                        self.assertIn("3", tab)      # the tab counts the tasks, not the lines of a detail
                        await self.fits(pg, f"{w} Liste")
                        await pg.evaluate("document.querySelector('#agld [data-agrow^=\"watch:\"]').click()")
                        await pg.wait_for_selector("#agdet:not([hidden]) h3")
                        self.assertIn("FRITZ!OS 8.10", await pg.inner_text("#agdet"))
                        await self.fits(pg, f"{w} Detail")
                        # the switch in the row pauses the watch without opening anything else
                        await pg.evaluate("document.querySelector('#agld [data-agon^=\"watch:\"]').click()")
                        await pg.wait_for_timeout(500)
                        self.assertTrue(next(x for x in agent.load(uid)["plans"] if x.get("kind") == "watch")["paused"])
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
