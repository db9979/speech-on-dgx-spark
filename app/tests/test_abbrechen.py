"""Abbrechen heißt aus (Paket P2 der Code-Prüfung c vom 10.11.2026, Dominik „1a, Rest nach Empfehlung“, 2a, 4a).

- One list of stop words and goodbyes (stoppwort.py) for every client, whole sentences only, never the model: a stop
  word ends the talk in chat_turn before the switch, nothing goes to the language model, the clients get "ende" and
  close the microphone; „Hey Spark, stopp“ only stops (test/asr, desk/hear). „Vergiss es“ stays a cancel (intent).
- Notaus stage 3 „Alles still“ ends what is talking right now (laufend.py): answers, phone calls, Wyoming sessions.
- ESP32: a stop while it speaks drops the board's queue first and closes like a whole „Stopp“; a piece heard while
  another is recognized waits instead of being thrown away. Wyoming stops recognition and speech when HA is gone.
- Web, Android, Begleiter: Stopp ends the turn for good (turn number, no microphone again), the microphone track is
  released, another conversation is opened only after the running answer stopped (A-H1).
Nothing here depends on the clock; the client checks skip in a copy with only app/.
"""
import asyncio
import contextlib
import io
import json
import os
import re
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import esp32  # noqa: E402
import intent  # noqa: E402
import klaeren  # noqa: E402
import laufend  # noqa: E402
import notaus  # noqa: E402
import room  # noqa: E402
import stoppwort  # noqa: E402
import telefon  # noqa: E402
import wyoming  # noqa: E402
import zwischenruf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PANEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel")
JS = os.path.join(PANEL, "static", "js")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def outside(*parts):
    """A file outside app/ (apps, Begleiter); None in a copy with only app/."""
    path = os.path.join(ROOT, *parts)
    return read(path) if os.path.exists(path) else None


def quiet(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        res = fn(*a, **kw)
    return res, out.getvalue()


class Words(unittest.TestCase):
    def test_whole_sentences_of_stop_words(self):
        for s in ("Stopp", "Stopp!", "Jarvis, stopp!", "Hey Spark, stopp", "Spark, hör auf", "Okay, stopp", "Halt",
                  "Ruhe", "Sei still.", "Danke, das reicht", "das reicht", "Schon gut", "Abbrechen", "stop", "be quiet",
                  "Nicht jetzt", "Hör auf, bitte."):
            self.assertTrue(stoppwort.stop(s), s)
            self.assertEqual(stoppwort.ende(s), "stopp", s)
        for s in ("Stopp die Musik", "Halt, wie spät ist es?", "Stopp mal, wie heißt der Film", "Danke", "Hey Spark",
                  "Wie spät ist es?", "Nein", "Ruhe dich aus", "", None, "Stopp " * 60):
            self.assertFalse(stoppwort.stop(s), s)

    def test_goodbyes_and_greetings_only_on_a_call(self):
        for s in ("Tschüss", "Okay, danke, tschüss!", "Danke, das war's", "Das ist alles, danke", "Bye bye"):
            self.assertEqual(stoppwort.ende(s), "tschuess", s)
        # „Gute Nacht“ may be the smart home's evening wish: it ends only a phone call
        self.assertEqual(stoppwort.ende("Gute Nacht"), "")
        self.assertTrue(stoppwort.bye("Gute Nacht, Spark", call=True))
        self.assertTrue(stoppwort.no_more("Nein danke."))
        self.assertFalse(stoppwort.no_more("Nein, wie wird das Wetter?"))
        self.assertTrue(stoppwort.starts("Stopp, das stimmt nicht"))
        self.assertFalse(stoppwort.starts("Wie spät ist es, stopp"))

    def test_one_list_for_every_way(self):
        """Regel 12: the lists are only in stoppwort.py; intent, klaeren, zwischenruf, room, esp32 and telefon use it."""
        self.assertIn(stoppwort.ABBRUCH, intent.CANCEL.pattern)
        self.assertTrue(intent.cancel("Vergiss es") and intent.cancel("Schon gut"))
        self.assertTrue(klaeren._none("Vergiss es"))
        self.assertEqual(zwischenruf.decide("Tschüss"), ("stopp", "stoppwort"))
        for mod, name in ((esp32, "STOP_WORDS"), (telefon, "BYE_WORDS"), (telefon, "NO_MORE"), (room, "STOP"),
                          (zwischenruf, "STOP"), (intent, "CANCEL_PHRASES")):
            self.assertFalse(hasattr(mod, name), f"{mod.__name__}.{name}")
        own = re.compile(r"stopp\?\|halt|tschüss\|tschüs|vergiss es\|")
        for f in sorted(os.listdir(PANEL)):
            if f.endswith(".py") and f != "stoppwort.py":
                self.assertIsNone(own.search(read(PANEL, f)), f)
        for f in sorted(os.listdir(JS)):
            if f.endswith(".js"):
                self.assertNotRegex(read(JS, f), r"stopp\?\|halt", f)


class Chat(unittest.TestCase):
    def ask(self, client, text, **more):
        n = len(helpers.LLM_CALLS)
        r, log = quiet(client.post, "/api/chat", json=dict({"messages": [{"role": "user", "content": text}],
                                                            "speak": False}, **more))
        self.assertEqual(r.status_code, 200, r.text)
        return helpers.events(r), len(helpers.LLM_CALLS) - n, log

    def test_a_stop_word_never_reaches_the_model(self):
        c, _ = profile("Abbruch Anni")
        ev, calls, log = self.ask(c, "Stopp!")
        self.assertEqual(ev, [{"type": "ende", "art": "stopp"}, {"type": "done", "total": 0}])
        self.assertEqual(calls, 0)
        self.assertIn("chat: ende stopp | web", log)
        self.assertNotIn("Stopp", log.replace("chat: ende stopp", ""))
        ev, calls, _ = self.ask(c, "Danke, das war's.")
        self.assertEqual((ev[0], calls), ({"type": "ende", "art": "tschuess"}, 0))
        ev, calls, _ = self.ask(ADMIN, "Hör auf")   # without a profile too: only stops
        self.assertEqual((ev[0]["type"], calls), ("ende", 0))
        ev, calls, _ = self.ask(c, "Stopp die Musik")            # a question with the word inside
        self.assertNotIn("ende", [e["type"] for e in ev])
        self.assertGreater(calls, 0)

    def test_a_stop_word_drops_the_panels_waiting_question(self):
        c, uid = profile("Abbruch Bert")
        with klaeren._lock:
            klaeren._waiting[uid] = {"kind": "choice", "id": "q1", "t": time.time(), "src": helpers.quelle(c, "k1"),
                                     "area": "licht"}
        self.ask(c, "Halt", convo="k2")                  # another conversation: its question stays
        self.assertTrue(klaeren.waiting(uid, helpers.quelle(c, "k1")))
        self.ask(c, "Halt", convo="k1")
        self.assertFalse(klaeren.waiting(uid, helpers.quelle(c, "k1")))

    def test_notaus_ends_a_running_answer(self):
        """The answer puts itself into laufend while it streams; its stop says "ende" with "notaus" and ends."""
        c, _ = profile("Abbruch Carl")
        real, seen = laufend.add, []

        def at_once(kind, stop):
            seen.append(kind)
            stop()
            return real(kind, stop)
        laufend.add = at_once
        try:
            ev, _, log = self.ask(c, "Erzähl mir etwas über Wale")
        finally:
            laufend.add = real
        self.assertEqual(seen, ["chat"])
        self.assertIn({"type": "ende", "art": "notaus"}, ev)
        self.assertNotIn("done", [e["type"] for e in ev])
        self.assertIn("chat: ende notaus |", log)
        self.assertEqual(laufend.counts()["chat"], 0)    # taken out again at its end

    def test_text_clients_get_a_fixed_word(self):
        import chat
        self.assertEqual(set(chat.ENDE_SAY), {"stopp", "tschuess", "notaus"})
        src = read(PANEL, "telegram.py")
        self.assertIn('ev.get("type") == "ende" and ev.get("art") in chat.ENDE_SAY', src)


class Notaus(unittest.TestCase):
    def test_stage_3_ends_everything_that_talks(self):
        hit = []
        tokens = [laufend.add(k, lambda k=k: hit.append(k)) for k in laufend.KINDS]
        before = laufend.ended()
        _, log = quiet(asyncio.run, notaus.after_change(0, 3, "Test", "test"))
        self.assertEqual(sorted(hit), sorted(laufend.KINDS))
        self.assertEqual(laufend.counts(), {k: 0 for k in laufend.KINDS})
        self.assertIn("notaus: laufendes beendet | notaus | chat 1 | telefon 1 | wyoming 1", log)
        self.assertEqual({k: laufend.ended()[k] - before[k] for k in laufend.KINDS}, {k: 1 for k in laufend.KINDS})
        for t in tokens:
            laufend.drop(t)

    def test_stage_2_leaves_answers_running(self):
        hit = []
        t = laufend.add("chat", lambda: hit.append(1))
        try:
            quiet(asyncio.run, notaus.after_change(0, 2, "Test", "test"))
            self.assertEqual(hit, [])
        finally:
            laufend.drop(t)

    def test_a_stop_that_fails_never_stops_the_others(self):
        hit = []

        def bad():
            raise RuntimeError("x")
        laufend.add("telefon", bad)
        laufend.add("wyoming", lambda: hit.append(1))
        got, log = quiet(laufend.end_all, "notaus")
        self.assertEqual((got["wyoming"], hit), (1, [1]))
        self.assertIn("notaus: laufendes telefon nicht beendet RuntimeError", log)
        with self.assertRaises(ValueError):
            laufend.add("anderes", lambda: None)

    def test_calls_and_sessions_register(self):
        self.assertIn('laufend.add("telefon", lambda: self.end("notaus"))', read(PANEL, "telefon.py"))
        self.assertIn('laufend.add("wyoming", stop)', read(PANEL, "wyoming.py"))
        self.assertIn('laufend.add("chat"', read(PANEL, "chat.py"))


class Wyoming(unittest.TestCase):
    def test_work_stops_when_home_assistant_is_gone(self):
        async def go():
            reader = asyncio.StreamReader()
            job = {"cancelled": False}

            async def work():
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    job["cancelled"] = True
                    raise
            asyncio.get_running_loop().call_later(0.05, reader.feed_eof)
            with self.assertRaises(ConnectionError):
                await wyoming.until_gone(reader, work())
            await asyncio.sleep(0)
            self.assertTrue(job["cancelled"])

            async def quick():
                return 7
            self.assertEqual(await wyoming.until_gone(asyncio.StreamReader(), quick()), 7)
        quiet(asyncio.run, go())


class Esp32(unittest.TestCase):
    class WS:
        def __init__(self):
            self.sent, self.closed = [], []

        async def send_text(self, t):
            self.sent.append(json.loads(t))

        async def send_bytes(self, b):
            pass

        async def close(self, code=1000):
            self.closed.append(code)

    def test_a_piece_heard_meanwhile_is_checked_after(self):
        heard = []

        async def asr(pcm):
            heard.append(pcm)
            return {b"a": "Wie bitte", b"b": "Stopp"}[pcm]

        async def go():
            ws = self.WS()
            ses = esp32.Session(ws, "t", {"id": "d_p2", "user": "u_p2", "name": "T"}, "c_p2")
            ses.answer = asyncio.ensure_future(asyncio.sleep(30))
            ses.stop_next = b"b"             # came in while b"a" was being recognized
            await ses.check_stop(b"a")
            return ses, ws
        old = esp32.transcribe
        esp32.transcribe = asr
        try:
            (ses, ws), _ = quiet(asyncio.run, go())
        finally:
            esp32.transcribe = old
        self.assertEqual(heard, [b"a", b"b"])
        self.assertTrue(ses.answer.cancelled())
        self.assertEqual(ws.closed, [1000])
        self.assertIsNone(ses.stop_next)

    def test_quiet_stop_first_and_no_plain_stop_after(self):
        """spark_quiet goes out before the answer is cancelled; the answer's own end then sends no plain "stop"
        (the board would leave Speaking before spark_quiet and keep its queue)."""
        async def asr(pcm):
            if pcm == b"answer":
                await asyncio.sleep(30)
            return "Stopp"

        async def go():
            ws = self.WS()
            ses = esp32.Session(ws, "t", {"id": "d_p2b", "user": "u_p2", "name": "T"}, "c_p2b")
            ses.testing = True
            ses.answer = asyncio.ensure_future(ses.run_answer(b"answer"))
            await asyncio.sleep(0.01)
            await ses.check_stop(b"stop")
            return ses, ws
        old = esp32.transcribe
        esp32.transcribe = asr
        try:
            (ses, ws), _ = quiet(asyncio.run, go())
        finally:
            esp32.transcribe = old
        tts = [{k: v for k, v in m.items() if k != "session_id"} for m in ws.sent if m.get("type") == "tts"]
        self.assertEqual(tts, [{"type": "tts", "state": "stop", "spark_quiet": True}])
        self.assertTrue(ses.answer.cancelled())
        self.assertEqual(ws.closed, [1000])


class WakeWordStop(unittest.TestCase):
    def test_hey_spark_stopp_only_stops(self):
        src = read(PANEL, "admin.py")
        self.assertIn("ende = stoppwort.ende(got.get(\"text\"))", src)
        js = read(JS, "chat.js")
        # the page: no tone and no microphone after „Hey Spark, stopp“; room mode takes the Spark's word
        self.assertIn("if(d.ende){wake.busy=false;endTurn();", js)
        self.assertIn("room.heard(text,d.ende)", js)
        self.assertIn("if(this.speaking&&ende)stopAnswer();", read(JS, "room.js"))


class Web(unittest.TestCase):
    """chat.js: one turn number that Stopp, a new or another conversation and a stop word raise."""
    js = read(JS, "chat.js")

    def body(self, start):
        i = self.js.index(start)
        return self.js[i:i + 4000]

    def test_stop_ends_the_turn_for_good(self):
        self.assertIn("function endTurn(){chat.turn++;chat.resumeMic=false;stopListening(true);stopAnswer();releaseMic();", self.js)
        self.assertIn("$('chatstop').onclick=()=>{endTurn();", self.js)
        self.assertIn("$('chatnew').onclick=()=>{endTurn();", self.js)
        self.assertIn("$('convosel').onchange=()=>{endTurn();", self.js)
        done = self.body("const done=async()=>")
        self.assertIn("g===chat.turn)await", done)
        self.assertIn("if(g!==chat.turn)return;", done)
        self.assertIn("else releaseMic()", done)
        # „Nichts gehört, Mikrofon aus“ closes it; any other cancel keeps a live stream for hands-free (test_ui_browser)
        self.assertIn("if(cancel){clearLive();if(why==='quiet')releaseMic();", self.js)

    def test_no_question_after_stop_during_recognition(self):
        self.assertIn("||chat.asrBusy)}", self.body("function setTalk()"))
        t2 = self.body("async function transcribe2(")
        self.assertIn("g=chat.turn", t2)
        self.assertLess(t2.index("if(g!==chat.turn){releaseMic();return}"), t2.index("ask(r.text"))
        self.assertIn("if(!o.held){stopAnswer();chat.turn++}", self.js)

    def test_the_microphone_track_is_released(self):
        rel = self.body("function releaseMic()")
        self.assertIn("if(chat.rec||chat.barge||wake.on||(window.room&&room.on)||!chat.stream)return;", rel)
        self.assertIn("x.stop()", rel)
        self.assertIn("releaseMic()}", self.body("function stopWake()"))

    def test_ende_from_the_spark_closes_up(self):
        a = self.body("async function ask(")
        self.assertIn("else if(ev.type==='ende')", self.js)
        self.assertIn("if(ended){drop();", self.js)
        self.assertIn("const g=chat.turn,msgs=chat.msgs,cid=chat.cid", a)

    def test_another_conversation_stops_the_answer_first(self):
        """A-H1: Finden, Offen and Ich open a conversation only through showConvo (endTurn first); an answer whose
        conversation is no longer open goes into its own conversation, never into the open one."""
        self.assertIn("function showConvo(id){endTurn();openConvo(id,true)}", self.js)
        for f in sorted(os.listdir(JS)):
            if f.endswith(".js") and f != "chat.js":
                self.assertNotRegex(read(JS, f), r"(?<!\w)openConvo\([^)]*,true\)", f)
        self.assertIn("if(moved){saveOther(cid,msgs,", self.js)


class Apps(unittest.TestCase):
    def test_android_closes_the_stream_and_honours_ende(self):
        src = outside("android", "app", "src", "main", "java", "io", "github", "db9979", "spark", "Talk.kt")
        if src is None:
            raise unittest.SkipTest("the Android app is not part of this copy")
        stop = src[src.index("    fun stop() {"):src.index("    /** A typed question. */")]
        self.assertIn("hangUp()", stop)
        self.assertIn("c.disconnect()", stop)
        self.assertIn('"ende" -> { ende = ev.optString("art")', src)
        self.assertIn("if (ende.isNotEmpty()) {", src)

    def test_begleiter_honours_ende_and_drops_a_question_after_mic_off(self):
        mac = outside("tools", "begleiter", "mac", "Sources", "Wake.swift")
        win = outside("tools", "begleiter", "windows", "TrayContext.Parts.cs")
        if mac is None or win is None:
            raise unittest.SkipTest("the Begleiter is not part of this copy")
        self.assertIn("guard self.listening, !self.paused, !MicSwitch.shared.closed else { return }", mac)
        self.assertIn("if r.ende {", mac)
        self.assertIn("if (!ReferenceEquals(listener, _wake) || listener.Paused || MicSwitch.Closed)", win)
        self.assertIn("(bool wake, string rest, bool ende) = await SparkClient.HearAsync(", win)
        self.assertIn("if (reply.Ende is not null)", outside("tools", "begleiter", "windows", "AskForm.cs"))
        self.assertIn("if r.ende != nil {", outside("tools", "begleiter", "mac", "Sources", "AskView.swift"))


if __name__ == "__main__":
    unittest.main()
