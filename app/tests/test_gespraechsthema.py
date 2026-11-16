"""Gespräche nach Thema (gespraechsthema.py, Dominik 2026-11-14 „1-6“): one topic, one conversation by fixed rules of
the panel, a name from the first question only (never an answer), written in the background; pinned ones stay on top,
the oldest go into the archive instead of being lost; off by default, never guests. No clock: times are passed in."""
import asyncio
import json
import os
import time
import unittest

from tests import helpers
from tests import test_ui_browser as tub
from tests.test_ui_browser import async_playwright, browser_ok

helpers.start()
import features  # noqa: E402
import gespraechsthema as gt  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000.0


class Route:
    def __init__(self, *names):
        self.names = list(names)


def convo(area="kalender", rested=0.0):
    return {"id": "c1", "area": area, "updated": int((NOW - rested) * 1000), "msgs": [{"role": "user", "content": "x"}]}


class Rules(unittest.TestCase):
    def test_off_by_default(self):
        with open(os.path.join(os.path.dirname(PANEL), "config.default.json"), encoding="utf-8") as f:
            self.assertIs(json.load(f)["chat"]["convo_topics"], False)
        self.assertNotIn("chat.convo_topics", features.DEFAULT_ON)
        self.assertFalse(features.allowed(gt.KEY, None, {}))

    def test_the_group_is_one_fixed_word(self):
        self.assertEqual(gt.gruppe(Route("wetter")), "wetter")
        self.assertEqual(gt.gruppe(Route("wetter", "kalender")), "", "mixed: no group")
        self.assertEqual(gt.gruppe(Route()), "", "unclear: no group")
        self.assertEqual(gt.gruppe(Route("<b>x</b>")), "", "never a word outside the list")
        self.assertEqual(gt.gruppe(None), "")
        self.assertTrue(set(gt.LEISE) <= set(gt.AREAS))

    def test_when_a_new_conversation_begins(self):
        e = gt.entscheide
        self.assertEqual(e(None, "wetter", False, NOW), (False, "erstes"))
        self.assertEqual(e(convo(rested=gt.PAUSE_S), "kalender", True, NOW), (True, "pause"))
        self.assertEqual(e(convo(rested=gt.WECHSEL_S), "wetter", False, NOW), (True, "wechsel"))
        self.assertEqual(e(convo(rested=gt.WECHSEL_S - 1), "wetter", False, NOW), (False, "gleich"), "too soon")
        self.assertEqual(e(convo(rested=gt.WECHSEL_S), "wetter", True, NOW), (False, "gleich"), "a follow-up stays")
        self.assertEqual(e(convo(rested=gt.WECHSEL_S), "kalender", False, NOW), (False, "gleich"), "same group")
        self.assertEqual(e(convo(rested=gt.WECHSEL_S), "", False, NOW), (False, "gleich"), "unclear stays")
        for quiet in gt.LEISE:
            self.assertEqual(e(convo(rested=gt.WECHSEL_S), quiet, False, NOW)[0], False, quiet)
            self.assertEqual(e(convo(area=quiet, rested=gt.WECHSEL_S), "wetter", False, NOW)[0], False, quiet)

    def test_the_event_carries_only_the_group_and_the_decision(self):
        ev = gt.ereignis(convo(rested=gt.PAUSE_S), Route("wetter"), False, NOW)
        self.assertEqual(ev, {"type": "thema", "g": "wetter", "neu": True})

    def test_a_name_is_one_short_line_without_marks(self):
        self.assertEqual(gt.clean_name("<think>hm</think>\n\n**„Urlaub in Rom“.**\nErklärung"), "Urlaub in Rom")
        self.assertEqual(len(gt.clean_name("Wort " * 40)), gt.NAME_MAX)
        self.assertEqual(gt.clean_name("x"), "")
        self.assertEqual(gt.clean_name(None), "")

    def test_the_name_comes_from_the_first_question_only(self):
        seen, saved = [], []

        async def ask(system, user, job, max_tokens, **kw):
            seen.append((system, user, job))
            return "Wetter in Rom"

        def save(uid, cid, name=None):
            saved.append((uid, cid, name))

        async def run(c):
            started = gt.benennen("u1", c, ask, save)
            await asyncio.sleep(0.05)
            return started
        c = {"id": "c9", "msgs": [{"role": "user", "content": "Wie wird das Wetter in Rom?"},
                                  {"role": "assistant", "content": "GEHEIM aus einer Mail"}]}
        self.assertTrue(asyncio.run(run(c)))
        self.assertEqual(saved, [("u1", "c9", "Wetter in Rom")])
        self.assertEqual(seen[0][1], "Wie wird das Wetter in Rom?")
        self.assertNotIn("GEHEIM", json.dumps(seen))
        self.assertEqual(seen[0][2], gt.JOB)
        saved.clear()
        for done in (dict(c, name="schon"), dict(c, own=True), dict(c, msgs=c["msgs"][1:])):
            self.assertFalse(asyncio.run(run(done)))
        self.assertEqual(saved, [], "a name given by hand or a named one is never overwritten")
        self.assertNotIn("u1", gt._running)

    def test_a_failing_model_keeps_no_name(self):
        saved = []

        async def broken(*a, **kw):
            raise ValueError("weg")

        async def run():
            gt.benennen("u2", {"id": "c1", "msgs": [{"role": "user", "content": "Hallo"}]}, broken,
                        lambda *a, **kw: saved.append(a))
            await asyncio.sleep(0.05)
        asyncio.run(run())
        self.assertEqual(saved, [])
        self.assertNotIn("u2", gt._running)


class Store(unittest.TestCase):
    """profiles: pinned on top, the oldest into the archive (only while on), back from it, a hand name stays."""

    @classmethod
    def setUpClass(cls):
        name = "Themenablage"
        ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "4821"})
        cls.c = TestClient(panel.app)
        assert cls.c.post("/api/profile/login", json={"name": name, "pin": "4821"}).status_code == 200
        cls.uid = cls.c.get("/api/whoami").json()["profile"]["id"]

    def setUp(self):
        helpers.keep_chat(self, "convo_topics")
        old = profiles.MAX_CONVOS
        profiles.MAX_CONVOS = 3
        self.addCleanup(setattr, profiles, "MAX_CONVOS", old)
        for c in profiles.convos(self.uid) + profiles.archive(self.uid):
            profiles.delete_convo(self.uid, c["id"])

    def add(self, cid, area=None):
        return profiles.append_convo(self.uid, cid, cid, [{"role": "user", "content": "Frage " + cid}], area)

    def test_off_the_oldest_go_as_before(self):
        helpers.set_config(convo_topics=False)
        for i in range(5):
            self.add(f"k{i}")
        self.assertEqual(len(profiles.convos(self.uid)), 3)
        self.assertEqual(profiles.archive(self.uid), [], "no archive while the function is off")

    def test_on_the_oldest_go_into_the_archive_and_come_back(self):
        helpers.set_config(convo_topics=True)
        self.add("k0", "wetter")
        self.assertEqual(profiles.convo_meta(self.uid, "k0", pin=True)["pin"], True)
        for i in range(1, 6):
            self.add(f"k{i}")
        ids = [c["id"] for c in profiles.convos(self.uid)]
        self.assertIn("k0", ids, "a pinned conversation never goes")
        arch = [c["id"] for c in profiles.archive(self.uid)]
        self.assertEqual(sorted(arch), ["k1", "k2", "k3"])
        self.assertIsNone(profiles.convo_meta(self.uid, "k1", pin=True), "first continue, then pin")
        self.add("k1")
        self.assertIn("k1", [c["id"] for c in profiles.convos(self.uid)], "asking in it brings it back")
        self.assertNotIn("k1", [c["id"] for c in profiles.archive(self.uid)])
        self.assertEqual(next(c for c in profiles.convos(self.uid) if c["id"] == "k0")["area"], "wetter")
        profiles.delete_convo(self.uid, "k2")
        self.assertNotIn("k2", [c["id"] for c in profiles.archive(self.uid)], "delete also in the archive")

    def test_a_name_by_hand_is_never_overwritten(self):
        helpers.set_config(convo_topics=True)
        self.add("n1")
        profiles.convo_meta(self.uid, "n1", name="Mein Name", own=True)
        profiles.convo_meta(self.uid, "n1", name="Vom Modell")
        self.add("n1")
        c = next(c for c in profiles.convos(self.uid) if c["id"] == "n1")
        self.assertEqual((c["name"], c["own"]), ("Mein Name", True))
        profiles.convo_meta(self.uid, "n1", name="", own=False)
        self.assertNotIn("name", next(c for c in profiles.convos(self.uid) if c["id"] == "n1"))

    def test_endpoints_only_while_on(self):
        self.add("e1")
        helpers.set_config(convo_topics=False)
        self.assertEqual(self.c.post("/api/profile/convos/meta", json={"id": "e1", "pin": True}).status_code, 403)
        self.assertEqual(self.c.get("/api/profile/convos/archiv").status_code, 403)
        helpers.set_config(convo_topics=True)
        r = self.c.post("/api/profile/convos/meta", json={"id": "e1", "name": "Urlaub"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["item"]["name"], "Urlaub")
        for bad in ({"id": "e1"}, {"id": "../x", "pin": True}, {"id": "e1", "pin": "ja"}, {"id": "e1", "name": 3}):
            self.assertEqual(self.c.post("/api/profile/convos/meta", json=bad).status_code, 400, bad)
        self.assertEqual(self.c.post("/api/profile/convos/meta", json={"id": "fehlt", "pin": True}).status_code, 409)
        big = {"id": "e1", "name": "x" * 5000}
        self.assertEqual(self.c.post("/api/profile/convos/meta", json=big).status_code, 413)
        r = self.c.get("/api/profile/convos/archiv")
        self.assertEqual(set(r.json()), {"items", "mehr"})

    def test_never_for_guests(self):
        helpers.keep_chat(self, "public")
        helpers.set_config(convo_topics=True, public=True)
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/convos/meta", json={"id": "e1", "pin": True}).status_code, (401, 403))
        self.assertIn(guest.get("/api/profile/convos/archiv").status_code, (401, 403))


class Chat(unittest.TestCase):
    """The turn tells the page by fixed rules; only for the own browser while on."""

    @classmethod
    def setUpClass(cls):
        name = "Themenwechsel"
        ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "4821"})
        cls.c = TestClient(panel.app)
        assert cls.c.post("/api/profile/login", json={"name": name, "pin": "4821"}).status_code == 200

    def setUp(self):
        helpers.keep_chat(self, "convo_topics")

    def thema(self, client=None):
        r = (client or self.c).post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}],
                                                       "speak": False, "convo": "neu1"})
        self.assertEqual(r.status_code, 200, r.text)
        return [e for e in helpers.events(r) if e.get("type") == "thema"]

    def test_off_no_event(self):
        helpers.set_config(convo_topics=False)
        self.assertEqual(self.thema(), [])

    def test_on_one_event_without_text(self):
        helpers.set_config(convo_topics=True)
        ev = self.thema()
        self.assertEqual(len(ev), 1)
        self.assertEqual(set(ev[0]), {"type", "g", "neu"})
        self.assertFalse(ev[0]["neu"], "the first question of a conversation begins none")

    def test_never_for_guests(self):
        helpers.keep_chat(self, "public")
        helpers.set_config(convo_topics=True, public=True)
        self.assertEqual(self.thema(TestClient(panel.app)), [])


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    """The list shows name, symbol and the pinned group; a new topic gets its own conversation and a line."""
    # the page helpers of test_ui_browser, borrowed (a subclass would run all of its tests again)
    setUpClass = tub.Browser.__dict__["setUpClass"]
    B = tub.Browser
    run_async, _chrome, until, page = B.run_async, B._chrome, B.until, B.page

    def test_names_pins_and_a_new_topic(self):
        helpers.keep_chat(self, "convo_topics")
        helpers.set_config(convo_topics=True)

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1600, 900)
                uid = await pg.evaluate("PROFILE.id")
                self.assertTrue(await pg.evaluate("window.TOPICS_ON===true"))
                now = int(time.time() * 1000)
                for cid, title, area in (("t0000000b01", "Wie wird das Wetter?", "wetter"),
                                         ("t0000000b02", "Termine morgen", "kalender")):
                    profiles.save_convo(uid, {"id": cid, "title": title, "updated": now, "area": area,
                                              "msgs": [{"role": "user", "content": title},
                                                       {"role": "assistant", "content": "Antwort"}]})
                profiles.convo_meta(uid, "t0000000b02", name="Kalender <b>Woche</b>", pin=True)
                await pg.evaluate("(async()=>{goSec('chat');await convos.sync();fillConvos()})()")
                await self.until(pg, "document.querySelectorAll('#cvlrows [data-cid]').length>=2")
                await pg.click("#cvlbtn")   # the list opens over the conversation (Vorschlag 3, 2026-11-16)
                await self.until(pg, "!!$('convolist').offsetParent")
                heads = await pg.evaluate("[...document.querySelectorAll('#cvlrows .ld-grp')].map(e=>e.textContent)")
                self.assertEqual(heads[0], "Angeheftet")
                row = "document.querySelector('#cvlrows [data-cid=t0000000b02]')"
                self.assertIn("Kalender <b>Woche</b>", await pg.evaluate(row + ".textContent"), "a name is text, never markup")
                self.assertTrue(await pg.evaluate(row + ".querySelector('.cvpin')!==null"))
                await pg.click("#cvlrows [data-cid=t0000000b01]")
                await self.until(pg, "chat.cid==='t0000000b01'")
                self.assertTrue(await pg.evaluate("!!$('cvpinbtn').offsetParent&&!!$('cvnamebtn').offsetParent"))
                # the turn says a new topic: the question moves into a new conversation, a line marks it
                n = await pg.evaluate("""(()=>{const um={role:'user',content:'Und das Paket?'};chat.msgs.push(um);
                  const ub=[...document.querySelectorAll('#chatlog .bubble')].at(-1);const old=chat.msgs;
                  const n=topicTurn({type:'thema',g:'paket',neu:true},old,um,ub);
                  return {cid:n.cid,len:n.msgs.length,area:n.msgs.area,same:chat.msgs===n.msgs,left:old.includes(um),
                          sep:document.querySelectorAll('#chatlog .cvsep').length}})()""")
                self.assertNotEqual(n["cid"], "t0000000b01")
                self.assertEqual((n["len"], n["area"], n["same"], n["left"], n["sep"]), (1, "paket", True, False, 1))
                # not new: the area only fills an empty one
                self.assertIsNone(await pg.evaluate("topicTurn({type:'thema',g:'wetter',neu:false},chat.msgs,{},null)"))
                self.assertEqual(await pg.evaluate("chat.msgs.area"), "paket")
                self.assertEqual(errors, [])
        self.run_async(go())


if __name__ == "__main__":
    unittest.main()
