"""Priority for people (stufe.py, common.PrioGate, V01.0.282): the stage per profile comes only from the admin,
the speech services believe it only from the panel, waiting requests go by stage without anybody starving,
and other people's language model rounds wait at most the set time. No test depends on the time of day."""
import asyncio
import os
import stat
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import common  # noqa: E402
import features  # noqa: E402
import profiles  # noqa: E402
import stufe  # noqa: E402
from common import GateFull, PrioGate  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def request(headers=None, host="127.0.0.1"):
    return Request({"type": "http", "method": "POST", "path": "/v1/audio/speech", "query_string": b"",
                    "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()], "client": (host, 1)})


class Gate(unittest.TestCase):
    def test_priority_goes_first_but_never_stops_a_running_one(self):
        async def go():
            g, order = PrioGate(1), []
            first = await g.enter(1)                     # runs

            async def wait(name, stage):
                t = await g.enter(stage)
                order.append((name, t["overtook"]))
                return t
            a = asyncio.ensure_future(wait("a", 1))
            await asyncio.sleep(0)
            b = asyncio.ensure_future(wait("b", 1))
            await asyncio.sleep(0)
            v = asyncio.ensure_future(wait("vip", 2))
            await asyncio.sleep(0)
            self.assertEqual(order, [])                  # the running one is not stopped
            self.assertEqual(g.view()["waiting"], 3)
            g.leave(first)
            g.leave(await v)
            g.leave(await a)
            g.leave(await b)
            return order
        self.assertEqual(asyncio.run(go()), [("vip", 2), ("a", 0), ("b", 0)])

    def test_nobody_starves(self):
        async def go():
            clock = Clock()
            g = PrioGate(1, age=4, clock=clock)
            first = await g.enter(1)
            low = asyncio.ensure_future(g.enter(0))
            await asyncio.sleep(0)
            clock.t += 9                                 # two stages up: as high as Vorrang now, and earlier
            vip = asyncio.ensure_future(g.enter(2))
            await asyncio.sleep(0)
            g.leave(first)
            for _ in range(10):
                await asyncio.sleep(0)
            return low.done(), vip.done(), g, low, vip
        low_done, vip_done, g, low, vip = asyncio.run(go())
        self.assertTrue(low_done)
        self.assertFalse(vip_done)

    def test_queue_has_a_limit(self):
        async def go():
            g = PrioGate(1, most=2)
            await g.enter()
            w = [asyncio.ensure_future(g.enter()) for _ in range(2)]
            await asyncio.sleep(0)
            with self.assertRaises(GateFull):
                await g.enter()
            for x in w:
                x.cancel()
            return g
        g = asyncio.run(go())
        self.assertEqual(g.stats["full"], 1)

    def test_a_lost_slot_comes_back_after_its_lease(self):
        async def go():
            clock = Clock()
            g = PrioGate(1, lease=90, clock=clock)
            await g.enter()                              # never left (client gone before the stream began)
            clock.t += 91
            t = await asyncio.wait_for(g.enter(), 1)
            return t
        self.assertEqual(asyncio.run(go())["waited_ms"], 0)

    def test_giving_up_while_waiting_frees_the_place(self):
        async def go():
            g = PrioGate(1)
            t = await g.enter()
            w = asyncio.ensure_future(g.enter())
            await asyncio.sleep(0)
            w.cancel()
            await asyncio.sleep(0)
            self.assertEqual(g.view()["waiting"], 0)
            g.leave(t)
            g.leave(t)                                   # twice is harmless
            self.assertEqual(g.view()["running"], 0)
            t2 = await asyncio.wait_for(g.enter(), 1)
            return t2
        asyncio.run(go())

    def test_unknown_stage_counts_as_normal(self):
        async def go():
            g, order = PrioGate(1), []
            first = await g.enter()
            for name, st in (("odd", 7), ("vip", 2)):
                asyncio.ensure_future(g.enter(st)).add_done_callback(lambda f, n=name: order.append(n))
                await asyncio.sleep(0)
            g.leave(first)
            for _ in range(10):
                await asyncio.sleep(0)
            return list(order)
        self.assertEqual(asyncio.run(go()), ["vip"])


class StageHeader(unittest.TestCase):
    def setUp(self):
        self.key = common.stage_key(create=True)

    def test_key_file_only_for_the_service_user(self):
        mode = stat.S_IMODE(os.stat(common.stage_key_path()).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(len(self.key), 64)

    def test_only_the_panel_from_this_machine(self):
        good = {"x-spark-stufe": "2", "x-spark-vorrang": self.key}
        self.assertEqual(common.stage_of(request(good)), 2)
        self.assertEqual(common.stage_of(request(dict(good, **{"x-spark-stufe": "0"}))), 0)
        self.assertEqual(common.stage_of(request(good, host="192.168.1.9")), 1)          # another machine
        self.assertEqual(common.stage_of(request({"x-spark-stufe": "2"})), 1)            # no key
        self.assertEqual(common.stage_of(request(dict(good, **{"x-spark-vorrang": "0" * 64}))), 1)
        self.assertEqual(common.stage_of(request(dict(good, **{"x-spark-stufe": "5"}))), 1)
        self.assertEqual(common.stage_of(request({})), 1)

    def test_both_services_use_the_gate(self):
        for fn in ("tts_proxy.py", "asr_proxy.py"):
            with open(os.path.join(helpers.APP, fn)) as f:
                src = f.read()
            self.assertIn("stage_of(request)", src, fn)
            self.assertIn(".leave(ticket)", src, fn)

    def test_panel_sends_nothing_for_normal(self):
        self.assertEqual(stufe.headers(""), {})
        self.assertEqual(stufe.headers("vorrang"), {"x-spark-stufe": "2", "x-spark-vorrang": self.key})
        self.assertEqual(stufe.headers("hinten")["x-spark-stufe"], "0")


class Admin(unittest.TestCase):
    def tearDown(self):
        helpers.set_config(person_priority=False)
        stufe._save({})

    def test_off_by_default_and_in_the_register(self):
        import json
        with open(features.DEFAULTS) as f:
            self.assertIs(json.load(f)["chat"]["person_priority"], False)
        self.assertIn("vorrang", features.BY_KEY)
        self.assertFalse(features.BY_KEY["vorrang"].guests)

    def test_only_the_admin_sets_a_stage(self):
        c, uid = profile("StufeAnna")
        self.assertEqual(c.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"}).status_code, 401)   # not itself
        for bad in ("root", 2, None, "Vorrang"):
            self.assertEqual(ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": bad}).status_code, 400)
        self.assertEqual(ADMIN.put("/api/admin/vorrang/u_000000000000", json={"level": "vorrang"}).status_code, 404)
        self.assertEqual(ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"}).json(), {"level": "vorrang"})
        self.assertEqual(ADMIN.get(f"/api/admin/profiles/{uid}").json()["rights"]["vorrang"]["level"], "vorrang")
        import guard
        self.assertTrue(any(x.get("event") == "person_priority" and x.get("uid") == uid for x in guard.read(50)))
        self.assertEqual(ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "x" * 300}).status_code, 413)
        # only while the admin switch is on
        self.assertEqual(stufe.level(uid), "")
        helpers.set_config(person_priority=True)
        self.assertEqual(stufe.level(uid), "vorrang")
        self.assertEqual(stufe.level(None), "")          # guests never
        ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": ""})
        self.assertEqual(stufe.level(uid), "")

    def test_at_most_three(self):
        ids = [profile(f"StufeMax{i}")[1] for i in range(4)]
        for u in ids[:3]:
            self.assertEqual(ADMIN.put(f"/api/admin/vorrang/{u}", json={"level": "vorrang"}).status_code, 200)
        self.assertEqual(ADMIN.put(f"/api/admin/vorrang/{ids[3]}", json={"level": "vorrang"}).status_code, 400)
        self.assertEqual(ADMIN.put(f"/api/admin/vorrang/{ids[0]}", json={"level": "vorrang"}).status_code, 200)   # again: fine
        self.assertEqual(ADMIN.put(f"/api/admin/vorrang/{ids[3]}", json={"level": "hinten"}).status_code, 200)

    def test_profile_sees_it_under_ich(self):
        c, uid = profile("StufeBen")
        helpers.set_config(person_priority=True)
        row = next(f for f in c.get("/api/features").json()["features"] if f["key"] == "vorrang")
        self.assertEqual(row["why"], "profile")
        ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"})
        row = next(f for f in c.get("/api/features").json()["features"] if f["key"] == "vorrang")
        self.assertTrue(row["can"])

    def test_only_the_profiles_own_turn(self):
        c, uid = profile("StufeCid")
        helpers.set_config(person_priority=True)
        ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"})

        class T:
            def __init__(self, who, own):
                self.who, self.own_browser, self.ccfg = who, own, None
        me = profiles.by_id(uid)
        self.assertEqual(stufe.turn_level(T(me, True)), "vorrang")
        self.assertEqual(stufe.turn_level(T(me, False)), "")          # another voice at this device
        self.assertEqual(stufe.turn_level(T(None, False)), "")        # stranger at a shared speaker, guest

    def test_answer_sentences_carry_the_stage(self):
        c, uid = profile("StufeDora")
        helpers.set_config(person_priority=True)
        helpers.TTS_SEEN.clear()
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(helpers.TTS_SEEN)
        self.assertNotIn("x-spark-stufe", helpers.TTS_SEEN[-1])        # normal: nothing extra
        ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"})
        helpers.TTS_SEEN.clear()
        c.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]})
        self.assertEqual(helpers.TTS_SEEN[-1].get("x-spark-stufe"), "2")
        self.assertEqual(helpers.TTS_SEEN[-1].get("x-spark-vorrang"), common.stage_key())
        helpers.set_config(person_priority=False)                        # switch off: as before
        helpers.TTS_SEEN.clear()
        c.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]})
        self.assertNotIn("x-spark-stufe", helpers.TTS_SEEN[-1])

    def test_config_check(self):
        cfg = ADMIN.get("/api/config").json()
        cfg["chat"]["person_priority_wait"] = 9
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)

    def test_backup_keeps_the_stages(self):
        import backup
        self.assertIn("personen-vorrang.json", backup.STATE_FILES)


class LanguageModelGate(unittest.TestCase):
    """Step B (V01.0.284): other people's rounds wait while a Vorrang answer has no first sentence yet."""
    def setUp(self):
        stufe._active.clear()
        stufe._hints.clear()

    def tearDown(self):
        helpers.set_config(person_priority=False, person_priority_wait=2)
        stufe._active.clear()
        stufe._hints.clear()
        stufe._save({})

    def run_wait(self, lv):
        clock = Clock()

        async def sleep(s):
            clock.t += s
        return asyncio.run(stufe.wait_turn(lv, sleep=sleep, clock=clock))

    def turn(self, name):
        c, uid = profile(name)

        class T:
            who, own_browser, ccfg = profiles.by_id(uid), True, None
        return c, uid, T()

    def test_others_wait_at_most_the_set_time(self):
        c, uid, t = self.turn("GateAnna")
        helpers.set_config(person_priority=True, person_priority_wait=2)
        ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"})
        tok = stufe.begin(t)
        self.assertIsNotNone(tok)
        waited = self.run_wait("")
        self.assertGreaterEqual(waited, 2)
        self.assertLess(waited, 2.2)
        self.assertEqual(self.run_wait("vorrang"), 0)        # Vorrang never waits for Vorrang
        stufe.first(tok)
        self.assertEqual(self.run_wait(""), 0)               # first sentence there: nobody waits
        stufe.first(tok)                                     # twice is harmless

    def test_no_wait_when_off_or_nobody_has_priority(self):
        c, uid, t = self.turn("GateBen")
        self.assertIsNone(stufe.begin(t))                    # normal profile
        ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"})
        self.assertIsNone(stufe.begin(t))                    # switch off
        helpers.set_config(person_priority=True, person_priority_wait=0)
        tok = stufe.begin(t)
        self.assertEqual(self.run_wait(""), 0)               # 0 s: only speech output and recognition
        stufe.first(tok)

    def test_a_stuck_answer_holds_nobody_for_long(self):
        stufe._active[object()] = ("u_000000000000", 0.0)   # began long ago, no first sentence
        self.assertFalse(stufe.holding(now=stufe.FIRST_MAX + 1))
        stufe.hint("u_000000000000", now=100)
        self.assertTrue(stufe.holding(now=100 + stufe.HINT_S - 1))
        self.assertFalse(stufe.holding(now=100 + stufe.HINT_S + 1))

    def test_recording_starts(self):
        import vorrang
        self.assertEqual(TestClient(panel.app).post("/api/vorrang/spricht").status_code, 401)   # guests
        c, uid, t = self.turn("GateCid")
        helpers.set_config(person_priority=True)
        saved = vorrang._local[0]
        vorrang._local[0] = 0.0
        try:
            self.assertEqual(c.post("/api/vorrang/spricht").json(), {"ok": True})
            self.assertNotIn(uid, stufe._hints)              # normal: the same answer, nothing happens
            ADMIN.put(f"/api/admin/vorrang/{uid}", json={"level": "vorrang"})
            self.assertEqual(c.post("/api/vorrang/spricht").json(), {"ok": True})
            self.assertIn(uid, stufe._hints)
            self.assertGreater(vorrang._local[0], 0)        # marked as speech: background work stops at once
            self.assertTrue(c.get("/api/whoami").json()["person_priority"])
        finally:
            vorrang._local[0] = saved

    def test_the_app_may_say_it(self):
        self.assertIn("/api/vorrang/spricht", profiles.APP_PATHS)


if __name__ == "__main__":
    unittest.main()
