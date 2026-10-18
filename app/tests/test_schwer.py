"""Schwere Aufträge (schwer.py, bedarf.py; plan plaene/schwere-auftraege.md, Dominik 2026-10-18 „soll immer nur ein
Model geladen sein, beide nicht gleichzeitig“, „ja wie Empfehlung“): pictures and songs share one place, never two
models at once; the loaded kind goes first at most BUNDLE times in a row; the other model ends before a new kind
starts; too little memory waits instead of failing; who waits behind others gets a fixed sentence with place and
time; the services refuse a second model themselves (bedarf.lock); journal lines in numbers only. The clock and the
waiting are faked: nothing depends on the time of day."""
import asyncio
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import bilder  # noqa: E402
import live  # noqa: E402
import logfilter  # noqa: E402
import musik  # noqa: E402
import schwer  # noqa: E402

import bedarf  # noqa: E402


def fresh():
    schwer._ready.clear()
    schwer._state.update(run=None, loaded=None, streak=0, t1=0.0)
    schwer._avg.update(schwer.RUN_S)
    schwer._load.update(schwer.LOAD_S)


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        self.stopped = []

        async def stop_bild():
            self.stopped.append("bild")
            return True

        async def stop_musik():
            self.stopped.append("musik")
            return True
        self.p = mock.patch.dict(schwer.STOPS, {"bild": stop_bild, "musik": stop_musik})
        self.s = mock.patch.dict(schwer.SOURCES, {"bild": lambda: [], "musik": lambda: []})
        self.p.start()
        self.s.start()

    def tearDown(self):
        self.p.stop()
        self.s.stop()
        fresh()


def e(jid, art, t0):
    return {"id": jid, "art": art, "t0": t0}


class Order(Base):
    def test_the_loaded_kind_goes_first_but_at_most_bundle_in_a_row(self):
        q = [e("m1", "musik", 1), e("b1", "bild", 2), e("b2", "bild", 3)]
        self.assertEqual(schwer.pick(q, None, 0)["id"], "m1")           # nothing loaded: the oldest
        self.assertEqual(schwer.pick(q, "bild", 0)["id"], "b1")         # the loaded kind first
        self.assertEqual(schwer.pick(q, "bild", schwer.BUNDLE)["id"], "m1")   # then the other kind
        self.assertEqual(schwer.pick([e("b1", "bild", 2)], "musik", 9)["id"], "b1")
        self.assertIsNone(schwer.pick([], "bild", 0))

    def test_never_two_models_at_once_and_the_other_one_ends_first(self):
        """Dominik 2026-10-18: always only one model loaded. Jobs of both kinds at the same time run one after the
        other; before a new kind the loaded model is ended."""
        active, most, order = [0], [0], []

        def job(name):
            async def once():
                active[0] += 1
                most[0] = max(most[0], active[0])
                for _ in range(3):
                    await asyncio.sleep(0)
                order.append(name)
                active[0] -= 1
                return name
            return once

        async def main():
            schwer._state["loaded"] = "bild"
            return await asyncio.gather(schwer.run("bild", "b1", 1, job("b1")), schwer.run("musik", "m1", 2, job("m1")),
                                        schwer.run("bild", "b2", 3, job("b2")))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(asyncio.run(main()), ["b1", "m1", "b2"])
        self.assertEqual(most[0], 1, "never two jobs on the place")
        self.assertEqual(order, ["b1", "b2", "m1"], "the loaded kind is bundled")
        self.assertEqual(self.stopped, ["bild"], "the picture model ends before the song")
        self.assertEqual(schwer._state["loaded"], "musik")
        self.assertIsNone(schwer._state["run"])
        self.assertEqual(schwer._ready, {})
        for line in out.getvalue().splitlines():
            self.assertTrue(line.startswith("schwer: "), line)

    def test_nobody_waits_forever_behind_the_loaded_kind(self):
        """After BUNDLE pictures in a row while a song waits, the song goes next."""
        order = []

        def job(name):
            async def once():
                await asyncio.sleep(0)
                order.append(name)
            return once

        async def main():
            schwer._state["loaded"] = "bild"
            jobs = [schwer.run("musik", "m1", 1, job("m1"))] + [schwer.run("bild", f"b{i}", 1 + i, job(f"b{i}"))
                                                                for i in range(1, 6)]
            schwer._state["run"] = "x"            # all of them line up before the first one starts
            tasks = [asyncio.ensure_future(j) for j in jobs]
            for _ in range(5):
                await asyncio.sleep(0)
            c = schwer._condition()
            async with c:
                schwer._state["run"] = None
                c.notify_all()
            await asyncio.gather(*tasks)
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(main())
        self.assertEqual(order[:schwer.BUNDLE + 1], ["b1", "b2", "b3", "m1"])


class Memory(Base):
    def test_too_little_memory_waits_and_tries_again(self):
        """Dominik 5a: "memory" is not the end; the job keeps the place and tries again every RETRY_S seconds."""
        tries, slept, now = [], [], [1000.0]

        async def once():
            tries.append(schwer._ready["j1"]["phase"])
            if len(tries) < 3:
                raise ValueError("memory")
            return "ok"

        async def sleep(s):
            slept.append(s)
            now[0] += s
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(asyncio.run(schwer.run("bild", "j1", 1, once, sleep=sleep, clock=lambda: now[0])), "ok")
        self.assertEqual(slept, [schwer.RETRY_S, schwer.RETRY_S])
        self.assertIn("schwer: wartet bild memory", out.getvalue())

    def test_after_the_waiting_time_it_gives_up(self):
        now = [0.0]

        async def once():
            raise ValueError("memory")

        async def sleep(s):
            now[0] += s
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(ValueError) as err:
            asyncio.run(schwer.run("musik", "j2", 1, once, sleep=sleep, clock=lambda: now[0]))
        self.assertEqual(str(err.exception), "memory")
        self.assertGreaterEqual(now[0], schwer.MEM_WAIT_S)
        self.assertIn("schwer: abgesagt musik memory", out.getvalue())
        self.assertIsNone(schwer._state["run"], "the place is free again")

    def test_the_other_model_still_there_is_ended_at_once(self):
        """After a restart the panel does not know which model a service holds: "belegt" ends the other one and
        tries again at once, without waiting."""
        tries = []

        async def once():
            tries.append(1)
            if len(tries) == 1:
                raise ValueError("belegt")
            return "ok"

        async def sleep(s):
            raise AssertionError("no waiting")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(asyncio.run(schwer.run("musik", "j3", 1, once, sleep=sleep)), "ok")
        self.assertEqual(self.stopped, ["bild"])

    def test_other_reasons_end_the_job_at_once(self):
        async def once():
            raise ValueError("wartung")
        with self.assertRaises(ValueError):
            asyncio.run(schwer.run("bild", "j4", 1, once))
        self.assertEqual(schwer._ready, {})


class Hint(Base):
    def test_who_waits_behind_others_gets_place_and_time_in_a_fixed_sentence(self):
        """Dominik 3a 4a: only when it really waits, the place and about how long; no wish, no prompt."""
        jobs = {"bild": [{"id": "b1", "t0": 1, "state": "run", "prompt": "a red fox"}],
                "musik": [{"id": "m1", "t0": 2, "state": "wait"}, {"id": "m2", "t0": 3, "state": "wait"}]}
        with mock.patch.dict(schwer.SOURCES, {a: (lambda a=a: jobs[a]) for a in jobs}):
            self.assertEqual(schwer.hint("b1"), "")             # it runs: nothing to say
            w = schwer.where("m2", now=10)
            self.assertEqual((w["platz"], w["von"]), (3, 3))
            text = schwer.hint("m2", now=10)
            self.assertIn("Platz 3", text)
            self.assertIn("Gerade laufen viele Anfragen", text)
            self.assertRegex(text, r"etwa (eine Minute|\d+ Minuten)\.$")
            self.assertIn("place 3", schwer.hint("m2", en=True, now=10))
            self.assertNotIn("fox", text)
            self.assertEqual(schwer.offen(), 3)
            self.assertIsNone(schwer.where("nope"))
            with mock.patch.object(schwer, "WAITING", 3):
                self.assertTrue(schwer.full())

    def test_the_limit_counts_pictures_and_songs_together(self):
        """At most schwer.WAITING heavy jobs on the whole Spark, whatever their kind (one source, no list per module)."""
        self.assertFalse(hasattr(bilder, "WAITING"))
        self.assertFalse(hasattr(musik, "WAITING"))
        jobs = [{"id": f"x{i}", "t0": i, "state": "wait"} for i in range(schwer.WAITING)]
        with mock.patch.dict(schwer.SOURCES, {"bild": lambda: jobs[:4], "musik": lambda: jobs[4:]}):
            self.assertTrue(schwer.full())

    def test_the_modules_register_their_jobs_and_stops(self):
        self.p.stop()
        self.s.stop()
        try:
            self.assertIs(schwer.SOURCES["bild"], bilder._open_jobs)
            self.assertIs(schwer.SOURCES["musik"], musik._open_jobs)
            self.assertIs(schwer.STOPS["bild"], bilder._stop_engine)
            self.assertIs(schwer.STOPS["musik"], musik._stop_engine)
        finally:
            self.p.start()
            self.s.start()


class Live(Base):
    def test_live_shows_kind_state_and_numbers_only(self):
        jobs = [{"id": "m1", "t0": 1, "state": "wait", "caption": "a sad song about rain"}]
        with mock.patch.dict(schwer.SOURCES, {"musik": lambda: jobs}):
            schwer._ready["m1"] = {"art": "musik", "t0": 1, "phase": "speicher"}
            rows = schwer.busy(now=31)
            self.assertEqual(rows, [{"job": "Musik machen", "st": "speicher", "secs": 30}])
            d = schwer.for_live()
            self.assertEqual(d["wait"], {"bild": 0, "musik": 1})
            self.assertNotIn("rain", repr(d) + repr(rows))
            snap = live.snapshot("admin")
            self.assertIn("schwer", snap)
            self.assertNotIn("rain", repr(snap))
        self.assertIn("schwer", dict(logfilter.AREAS))


class Lock(unittest.TestCase):
    """bedarf.py: a service takes the one place before its engine starts; a second one gets Belegt (503 "belegt")."""

    def test_only_one_engine_holds_the_place(self):
        d = tempfile.mkdtemp()
        with mock.patch.object(bedarf, "LOCK", os.path.join(d, "bedarf.lock")), contextlib.redirect_stdout(io.StringIO()) as out:
            a, b = bedarf.OnDemand("bild"), bedarf.OnDemand("musik")
            a.claim()
            a.claim()                    # again: it holds it already
            with self.assertRaises(bedarf.Belegt):
                b.claim()
            a.stop("leerlauf")           # the stop frees the place
            b.claim()
            with self.assertRaises(bedarf.Belegt):
                a.claim()
            b.release()
            a.claim()
            a.release()
        self.assertIn("musik: engine nicht gestartet belegt", out.getvalue())

    def test_both_services_answer_belegt_before_they_load(self):
        for name in ("bild_server.py", "musik_server.py"):
            with open(os.path.join(os.path.dirname(bedarf.__file__), name)) as f:
                src = f.read()
            self.assertIn('raise HTTPException(503, "belegt")', src, name)
            self.assertLess(src.index("self.claim()"), src.index("check_memory("), name)


if __name__ == "__main__":
    unittest.main()
