"""Seitenänderung und wartende Fragen (Ideen aus OpenFuse, Dominik 2026-11-15 „1-3“).

1. A watch whose task is an address compares the page with the last run by fixed rules (seitenvergleich.py), never
   with the language model: times do not count, a number change is „geändert“, one old line stands for one new line
   at most, only checksums are kept, never the page's text; the first run only keeps the stand.
2. A question typed in the chat while the Spark answers waits in a visible line and goes out after the answer;
   Stopp holds the line. No test reads the clock.
"""
import asyncio
import unittest

from tests import helpers
from tests.test_agent import Base, allow, profile
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()
import agent  # noqa: E402
import beobachten  # noqa: E402
import seitenvergleich as sv  # noqa: E402

agent.AUTO = False
URL = "https://avm.de/service/downloads"
OLD = "# Downloads\nFRITZ!OS 8.10 für FRITZ!Box 7590\nPreis: 199 €\nvor 5 Minuten aktualisiert\nStand 14.11.2026 18:30\nAlter Hinweis"
NEW = "# Downloads\nFRITZ!OS 8.20 für FRITZ!Box 7590\nPreis: 199 €\nvor 2 Stunden aktualisiert\nStand 15.11.2026 09:10\nNeue Labor-Version"


class Rules(unittest.TestCase):
    def test_times_do_not_count_numbers_change_rest_is_new_or_gone(self):
        d = sv.compare(sv.stand(sv.lines(OLD)), sv.lines(NEW))
        self.assertEqual(d, {"neu": ["Neue Labor-Version"], "geaendert": ["FRITZ!OS 8.20 für FRITZ!Box 7590"], "weg": 1})
        self.assertEqual(sv.summary(d), "1 neu, 1 geändert, 1 weg")
        self.assertEqual(sv.count(sv.compare(sv.stand(sv.lines(OLD)), sv.lines(OLD))), 0)

    def test_a_version_is_no_date(self):
        d = sv.compare(sv.stand(["Version 1.2.3"]), ["Version 1.2.4"])
        self.assertEqual(d["geaendert"], ["Version 1.2.4"])

    def test_one_old_line_never_answers_for_two(self):
        d = sv.compare(sv.stand(["Preis 10 €"]), ["Preis 11 €", "Preis 12 €"])
        self.assertEqual((len(d["geaendert"]), len(d["neu"]), d["weg"]), (1, 1, 0))

    def test_only_checksums_are_kept(self):
        kept = "".join(sv.stand(sv.lines(OLD)))
        self.assertNotIn("FRITZ", kept)
        self.assertTrue(all(len(x) == 24 for x in sv.stand(sv.lines(OLD))))
        self.assertLessEqual(len(sv.lines("\n".join(f"Zeile {i}" for i in range(1000)))), sv.LINES)
        self.assertLessEqual(max(len(x) for x in sv.lines("x" * 5000)), sv.LINE)

    def test_address_only_when_it_is_the_task(self):
        self.assertEqual(sv.address(URL), URL)
        self.assertEqual(sv.address(f"Sag mir Bescheid, wenn sich {URL} ändert."), URL)
        self.assertIsNone(sv.address(f"Melde dich, wenn auf {URL} der Preis unter 100 € fällt"))
        self.assertIsNone(sv.address(f"{URL} und https://example.org ändern sich"))
        self.assertTrue(beobachten.wants(f"Sag mir Bescheid, wenn sich {URL} ändert"))
        self.assertFalse(beobachten.wants(URL))     # an address alone in the chat is no watch
        w = beobachten.parse(f"Sag mir Bescheid, wenn sich {URL} ändert")
        self.assertEqual(w["title"], "Änderungen: avm.de/service/downloads")

    def test_report_and_note_have_fixed_words(self):
        d = sv.compare(sv.stand(sv.lines(OLD)), sv.lines(NEW))
        title, body = sv.push_text("Änderungen: avm.de/service/downloads", d, URL)
        self.assertEqual(title, "🔔 Seite geändert: avm.de/service/downloads")
        self.assertTrue(body.startswith("1 neu, 1 geändert, 1 weg (avm.de)."))
        self.assertIn("Ich → Aufträge", body)
        self.assertIn("Weg: 1 Zeile.", sv.report(d, URL))


class Runs(Base):
    def setUp(self):
        super().setUp()
        self.a, self.uid = profile("Seitenblick")
        allow(self.a, self.uid)
        helpers.set_config(agent=True, agent_watch=True)
        agent.mutate(self.uid, lambda d: d.update(plans=[], jobs=[], count=0))
        import chat
        zone = chat.user_zone("")
        self.pid = agent.add_plan(self.uid, dict(agent.parse_plan(
            {"task": URL, "kind": "watch", "repeat": "daily", "time": "08:00", "only_new": False, "below": 50}, zone),
            created_by="page"))["id"]
        self.page = OLD
        self._pt = chat.page_text

        async def fake(c, url, limit=3000, seconds=8, query=None):
            self.read = (url, limit)
            return self.page
        chat.page_text = fake

        async def no_model(*a, **k):
            raise AssertionError("a page change never asks the model")
        self._llm, agent._llm = agent._llm, no_model

    def tearDown(self):
        import chat
        chat.page_text, agent._llm = self._pt, self._llm
        super().tearDown()
        helpers.set_config(agent_watch=False)

    def plan(self):
        return next(x for x in agent.load(self.uid)["plans"] if x["id"] == self.pid)

    def run_once(self):
        item, why = agent.enqueue(self.uid, URL, origin="watch", plan=self.pid)
        self.assertTrue(item, why)
        asyncio.run(agent.run_job(self.uid, item["id"]))
        return item["id"]

    def test_plan_from_an_address(self):
        p = self.plan()
        self.assertEqual((p["page"], p["only_new"], p.get("below")), (URL, True, None))
        self.assertIn("ohne Sprachmodell", agent.describe_plan(p))

    def test_first_run_keeps_the_stand_then_only_changes_count(self):
        self.run_once()
        p = self.plan()
        self.assertEqual(self.read, (URL, agent.PAGE_CHARS))
        self.assertEqual((p["hist"][0]["r"], p["hist"][0]["what"]), ("still", "Ausgangsstand: 6 Zeilen"))
        self.assertEqual(len(p["stand"]), 6)
        self.assertEqual(self.sent, [])
        # the same page with other times: quiet
        self.page = OLD.replace("vor 5 Minuten", "vor 9 Minuten").replace("18:30", "18:55")
        jid = self.run_once()
        self.assertEqual((self.plan()["hist"][0]["r"], self.sent), ("still", []))
        self.assertIsNone(agent.job(self.uid, jid))
        # a changed page: one note in fixed words, the finds and the report under Ich → Aufträge
        self.page = NEW
        jid = self.run_once()
        self.assertEqual(self.plan()["hist"][0]["r"], "neu")
        self.assertEqual(self.sent[-1][1], "🔔 Seite geändert: avm.de/service/downloads")
        j = agent.job(self.uid, jid)
        self.assertEqual([f["v"] for f in j["finds"]], ["Neu", "Geändert"])
        self.assertIn("Neue Labor-Version", j["report"])
        self.assertEqual(self.plan().get("known") or [], [])
        # the page's view never carries the stand
        self.assertNotIn("stand", self.a.get("/api/profile/agent").json()["plans"][0])

    def test_unreadable_page_is_a_failed_run_and_start_afresh_forgets(self):
        self.run_once()
        self.page = ""
        self.run_once()
        p = self.plan()
        self.assertEqual((p["hist"][0]["r"], p["fails"]), ("fehler", 1))
        self.assertIn("stand", p)
        r = self.a.put(f"/api/profile/agent/plans/{self.pid}", json={"forget": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("stand", self.plan())
        # another task without an address is a normal watch again, its stand gone
        self.page = OLD
        self.run_once()
        agent.edit_plan(self.uid, self.pid, {"task": "Neue Firmware für meine FRITZ!Box"})
        p = self.plan()
        self.assertNotIn("page", p)
        self.assertNotIn("stand", p)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Waiting(unittest.TestCase):
    """A question typed while the Spark answers waits visibly; ✕ drops it; Stopp holds the line."""
    @classmethod
    def setUpClass(cls):
        import panel  # noqa: F401
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Wartetest", "4713")
        except Exception:
            pass

    async def until(self, pg, expr, seconds=20):
        for _ in range(int(seconds * 10)):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass
            await pg.wait_for_timeout(100)
        self.fail("timed out: " + expr)

    def test_queue(self):
        async def go():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                try:
                    pg = await (await br.new_context(viewport={"width": 390, "height": 844}, locale="de-DE",
                                                     bypass_csp=True)).new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    base = f"http://127.0.0.1:{self.port}"
                    await pg.goto(base + "/")
                    r = await pg.request.post(base + "/api/profile/login", data={"name": "Wartetest", "pin": "4713"})
                    self.assertEqual(r.status, 200)
                    await pg.goto(base + "/")
                    await self.until(pg, "typeof PROFILE!=='undefined'&&!!PROFILE")
                    await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
                    await pg.evaluate("goSec('chat')")
                    await self.until(pg, "$('chattext').getClientRects().length>0")
                    # an answer is running: the typed question waits, the field is empty again
                    await pg.evaluate("chat.ctrl=new AbortController();$('chattext').value='Und morgen?';$('chatsend').click()")
                    self.assertEqual(await pg.evaluate("[chat.queue.length,$('chatq').hidden,$('chattext').value]"),
                                     [1, False, ""])
                    self.assertIn("Und morgen?", await pg.inner_text("#chatq"))
                    self.assertIn("Wartet", await pg.inner_text("#chatq"))
                    # ✕ drops it
                    await pg.click("#chatq [data-qdel]")
                    self.assertEqual(await pg.evaluate("[chat.queue.length,$('chatq').hidden]"), [0, True])
                    # Stopp holds the line: nothing goes out by itself
                    await pg.evaluate("$('chattext').value='Und übermorgen?';$('chatsend').click()")
                    await pg.evaluate("chat.ctrl=null;chat.qHeld=true;chatQueueDraw()")
                    await pg.wait_for_timeout(800)
                    self.assertEqual(await pg.evaluate("chat.queue.length"), 1)
                    self.assertIn("Angehalten", await pg.inner_text("#chatq"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
