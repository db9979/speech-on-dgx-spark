"""Hintergrund-Läufe beim Start (2026-10-31): every background task the panel's startup handlers start with
core.spawn comes to rest without ending on an error.

dungeon_musik.loop ended on every start from V01.1.280 on: its pause TAKT had become the dict of time signatures,
asyncio.sleep({…}) raised a TypeError, core._done wrote "hintergrund: background task … ended" and the music made
ahead never came again, while every test stayed green. Here the panel starts with its startup handlers (TestClient
as a context); a task counts as at rest once it waits in asyncio.sleep or asyncio.wait_for (the pause checked like
asyncio does it, `delay <= 0`). It must not end with an error, and each one must come to rest, so a new loop that
waits some other way is named here and the test never waits for its deadline.

No wall clock: helpers.until is a deadline for the waiting, never a fixed pause. Reads only app/.
Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import core  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def where(task):
    """file:line of a task's coroutine, for the message."""
    coro = task.get_coro()
    code = getattr(coro, "cr_code", None)
    return f"{os.path.basename(code.co_filename)}:{code.co_firstlineno}" if code else task.get_name()


class StartupTasks(unittest.TestCase):
    def test_every_startup_task_comes_to_rest_without_an_error(self):
        real_sleep, real_wait_for, real_done = asyncio.sleep, asyncio.wait_for, core._done
        rested, ended, died = set(), set(), []

        def rest():
            t = asyncio.current_task()
            if t is not None:
                rested.add(t)

        async def sleep(delay, *a, **kw):
            bool(delay <= 0)     # what asyncio.sleep checks first: a dict or None raises here like there
            rest()
            return await real_sleep(delay, *a, **kw)

        async def wait_for(aw, timeout, *a, **kw):
            rest()
            return await real_wait_for(aw, timeout, *a, **kw)

        def done(task):
            ended.add(task)
            if not task.cancelled() and task.exception() is not None:
                e = task.exception()
                died.append(f"{where(task)} {type(e).__name__}: {str(e)[:120]}")
            real_done(task)

        before = set(core._tasks)    # tasks of an earlier start in this process (their loop has stopped)
        with mock.patch.object(asyncio, "sleep", sleep), mock.patch.object(asyncio, "wait_for", wait_for), \
                mock.patch.object(core, "_done", done):
            with TestClient(panel.app):
                started = set(core._tasks) - before
                self.assertGreater(len(started) + len(died), 20)   # the startup handlers really ran
                helpers.until(lambda: died or all(t in ended or t in rested for t in started), s=60)
                self.assertEqual(died, [], "a background task ended at the start (core._done: hintergrund)")
                restless = sorted(where(t) for t in started if not (t in ended or t in rested))
                self.assertEqual(restless, [], "background tasks that never came to rest in asyncio.sleep or "
                                               "asyncio.wait_for: wait in one of them or add the way here")


class ModellDienste(unittest.TestCase):
    """The background loops of the model services (speech output, speech recognition, LLM-Tor) start only through
    common.dauerlauf (code review 2026-11-11, point 5): kept, and started again after an error with a line."""
    def test_a_loop_that_fails_writes_a_line_and_starts_again(self):
        import contextlib
        import io
        import common
        runs = []

        async def loop():
            runs.append(1)
            if len(runs) < 3:
                raise ValueError("geheim 4711")
            await asyncio.sleep(3600)

        async def main():
            t = common.dauerlauf("tts", "probe", loop, pause=0.01)
            self.assertIn(t, common._dauerlaeufe)                      # kept: asyncio holds only a weak reference
            for _ in range(500):
                if len(runs) >= 3:
                    break
                await asyncio.sleep(0.01)
            self.assertFalse(t.done())
            t.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await t
            await asyncio.sleep(0)
            self.assertNotIn(t, common._dauerlaeufe)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            asyncio.run(main())
        self.assertEqual(len(runs), 3)
        self.assertEqual(out.getvalue(), "tts: hintergrundlauf probe fehler | ValueError | neu in 0 s\n" * 2)   # no content
        self.assertEqual(common.DAUERLAUF_PAUSE, 30)

    def test_a_loop_that_ends_by_itself_is_done(self):
        import common

        async def kurz():
            return None

        async def main():
            t = common.dauerlauf("asr", "kurz", kurz)
            await t
            await asyncio.sleep(0)
            return t in common._dauerlaeufe

        self.assertFalse(asyncio.run(main()))

    def test_no_service_starts_a_loop_without_it(self):
        import re
        seen = 0
        for name in sorted(os.listdir(helpers.APP)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(helpers.APP, name), encoding="utf-8") as f:
                text = f.read()
            bare = [z.strip() for z in text.split("\n") if re.match(r"\s*asyncio\.create_task\(", z)]
            self.assertEqual(bare, [], f"{name}: a background loop without reference and catch; use common.dauerlauf")
            seen += text.count("dauerlauf(\"")
        self.assertGreaterEqual(seen, 6)                               # tts 2, asr 2, llmtor 2


if __name__ == "__main__":
    unittest.main()
