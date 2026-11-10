"""P6 „Gerät statt Profil als Schlüssel“ (review A, Dominik 2026-11-10 „1a, Rest nach Empfehlung“): one test per rule.

- H3: everything that waits on an answer (a yes to a proposal, the code word, the panel's own question, a follow-up)
  belongs to its source, profiles.quelle: kind of client, conversation and device (profiles.geraet, the one helper),
  so two iPhones, two speakers, two browsers or two conversations never answer each other. A plain yes that finds no
  proposal of its own source while one waits elsewhere, or after its own was replaced from elsewhere, carries out
  nothing and the model gets a fixed sentence (chat_turn.YES_ELSEWHERE). The iPhone app sends its conversation.
- H5: Meldung ans genutzte Gerät keeps one signal per device (and page tab): an idle second window never outvotes the
  one in use, a hidden tab marks only itself away, and a note counts as seen only by the browser it went to.
- M1: today's main conversation is fixed for the day (verlauf.main_today, users/<id>/hauptgespraech.json), never the
  one changed last.
- M2: Siri's and the Begleiter's follow-ups are kept per device (chat._SIRI).
- N1: a question queued without the Spark keeps its conversation (verlauf.js).
- N2: a stream that gives way to a newer one ends with the event "verdraengt" (sse.Hub), the page comes back later.

No clock of the day (times are passed in or only compared within the test), no network beyond the fake model.
"""
import asyncio
import contextlib
import datetime
import io
import json
import os
import unittest

from tests import helpers

helpers.start()
import calendars  # noqa: E402
import chat  # noqa: E402
import chat_turn  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import sse  # noqa: E402
import verlauf  # noqa: E402
import zustellung  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel", "static", "js")


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def second_login(name, pin="1234"):
    """Another browser of the same profile (its own login)."""
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def req(key="", cookie="", scope=None):
    heads = ([(profiles.DEVICE_HEADER.lower().encode(), key.encode())] if key else []) \
        + ([(b"cookie", f"{profiles.COOKIE}={cookie}".encode())] if cookie else [])
    return Request(dict({"type": "http", "headers": heads}, **(scope or {})))


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def quiet(f, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        got = f(*a, **kw)
    return got, out.getvalue()


class Quelle(unittest.TestCase):
    """H3: the one key of a turn's source."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Quelle Quirin")
        cls.k1 = profiles.add_device("iPhone Quirin", cls.uid, scope="app")
        cls.k2 = profiles.add_device("iPad Quirin", cls.uid, scope="app")

    def test_two_devices_of_one_kind_are_two_sources(self):
        a = profiles.quelle(req(self.k1), {"client": "iphone"})
        b = profiles.quelle(req(self.k2), {"client": "iphone"})
        self.assertNotEqual(a, b)                                   # iPhone and iPad (before: both "iphone:")
        self.assertEqual(a, profiles.quelle(req(self.k1), {"client": "iphone"}))
        self.assertNotEqual(a, profiles.quelle(req(self.k1), {"client": "iphone", "convo": "app-2"}))   # its conversations
        self.assertNotIn(self.k1, a)
        self.assertTrue(profiles.geraet(req(self.k1)).startswith("dev:"))

    def test_browsers_by_their_login_only_as_a_hash(self):
        a = profiles.quelle(req(cookie="u1.1700000000.1111111111111111.sig"), {"convo": "c1"})
        b = profiles.quelle(req(cookie="u1.1700000999.1111111111111111.other"), {"convo": "c1"})
        c = profiles.quelle(req(cookie="u1.1700000000.2222222222222222.sig"), {"convo": "c1"})
        self.assertEqual(a, b)                                      # the same login, its cookie renewed
        self.assertNotEqual(a, c)
        self.assertNotIn("1111111111111111", a + profiles.geraet(req(cookie="u1.1.1111111111111111.s")))

    def test_the_panels_own_channels_and_bounds(self):
        self.assertEqual(profiles.geraet(req(scope={"speech_profile": self.uid})), "")   # Telegram, phone: one per profile
        self.assertEqual(profiles.geraet(req(self.k1, scope={"speech_mcp": {"tools": []}})), "")
        self.assertEqual(profiles.geraet(req()), "")
        long = profiles.quelle(req(self.k1), {"client": "x" * 500, "convo": "y" * 500})
        self.assertLessEqual(len(long), 120)                        # klaeren._same and pending_set compare 120 signs
        self.assertNotEqual(long, profiles.quelle(req(self.k2), {"client": "x" * 500, "convo": "y" * 500}))
        self.assertEqual(profiles.quelle(req(), {"convo": 7})[:5], "web::")             # a convo that is no text


class Ja(unittest.TestCase):
    """H3: a yes only from where it was proposed; replaced from elsewhere, the yes there does nothing and says so."""

    @classmethod
    def setUpClass(cls):
        cls.a, cls.uid = profile("Ja Jolanda")
        cls.b = second_login("Ja Jolanda")
        cls.item = {"title": "Zahnarzt", "start": "2026-11-11T10:00", "end": "2026-11-11T11:00"}

    def tearDown(self):
        calendars.drop_pending(self.uid)
        profiles._REPLACED.clear()

    def turn(self, client, text, convo="c1"):
        n = len(helpers.LLM_CALLS)
        r, log = quiet(client.post, "/api/chat", json={"messages": [{"role": "user", "content": text}],
                                                       "convo": convo, "speak": False})
        self.assertEqual(r.status_code, 200, r.text)
        system = " ".join(str(m.get("content")) for c in helpers.LLM_CALLS[n:] for m in c.get("messages", [])
                          if m.get("role") == "system")
        return system, log

    def test_replaced_once_from_another_device(self):
        sa, sb = helpers.quelle(self.a, "c1"), helpers.quelle(self.b, "c1")
        self.assertNotEqual(sa, sb)                                 # same conversation id, two browsers
        profiles.pending_set(self.uid, "calendar", self.item, sa)
        self.assertFalse(profiles.pending_replaced(self.uid, sa))
        profiles.pending_set(self.uid, "calendar", self.item, sa)  # the same source again replaces nothing
        self.assertFalse(profiles.pending_replaced(self.uid, sa))
        profiles.pending_set(self.uid, "calendar", self.item, sb)
        self.assertFalse(profiles.pending_replaced(self.uid, sb))
        self.assertTrue(profiles.pending_replaced(self.uid, sa))
        self.assertFalse(profiles.pending_replaced(self.uid, sa))  # said once

    def test_a_yes_from_another_browser_does_nothing_and_says_so(self):
        calendars.propose(self.uid, self.item, helpers.quelle(self.a, "c1"))
        system, log = self.turn(self.b, "Ja")
        self.assertIn(chat_turn.YES_ELSEWHERE, system)
        self.assertIn("chat: ja ohne vorschlag hier | anderes geraet", log)
        self.assertEqual(calendars.pending(self.uid)["src"], helpers.quelle(self.a, "c1"))   # still waits there
        system, _ = self.turn(self.a, "Ja", convo="c2")             # another conversation of the same browser neither
        self.assertIn(chat_turn.YES_ELSEWHERE, system)

    def test_a_yes_after_the_proposal_was_replaced_elsewhere(self):
        calendars.propose(self.uid, self.item, helpers.quelle(self.a, "c1"))
        calendars.propose(self.uid, dict(self.item, title="Friseur"), helpers.quelle(self.b, "c1"))
        calendars.drop_pending(self.uid)                            # (the other one was answered meanwhile)
        system, log = self.turn(self.a, "Ja")
        self.assertIn(chat_turn.YES_ELSEWHERE, system)
        self.assertIn("chat: ja ohne vorschlag hier | ersetzt", log)

    def test_no_note_for_other_sentences_or_without_a_proposal(self):
        system, log = self.turn(self.a, "Ja")
        self.assertNotIn(chat_turn.YES_ELSEWHERE, system)
        calendars.propose(self.uid, self.item, helpers.quelle(self.a, "c1"))
        system, log = self.turn(self.b, "Wie wird das Wetter morgen?")
        self.assertNotIn(chat_turn.YES_ELSEWHERE, system)
        self.assertNotIn("ja ohne vorschlag", log)

    def test_the_iphone_app_sends_its_conversation(self):
        api = helpers.repo_file("ios", "Shared", "SparkAPI.swift")
        app = helpers.repo_file("ios", "Spark", "Assistant.swift")
        self.assertRegex(api, r"more: String\? = nil, convo: String\? = nil\)")
        self.assertIn('if let c = convo { body["convo"] = c }', api)
        self.assertRegex(app, r"api\.chat\(history, [^\n]*convo: convoId\)")


class Zustellung(unittest.TestCase):
    """H5: one signal per device and page."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Zustell Gerda")

    def setUp(self):
        helpers.set_config(note_device=True, deny={})
        zustellung._sig.pop(self.uid, None)
        zustellung._out.pop(self.uid, None)

    def tearDown(self):
        helpers.set_config(note_device=False)
        zustellung._sig.pop(self.uid, None)
        zustellung._out.pop(self.uid, None)

    def test_an_idle_second_window_never_outvotes_the_one_in_use(self):
        now = 10000.0
        zustellung.seen(self.uid, "web", 5, key="a" * 16, now=now, dev="web:laptop")
        zustellung.seen(self.uid, "web", 900, key="b" * 16, now=now + 30, dev="web:desktop")   # says later, idle
        self.assertEqual([(w, k) for w, k, _ in zustellung.in_use(self.uid, now + 31)], [("web", "a" * 16)])

    def test_a_hidden_tab_marks_only_itself_away(self):
        now = 10000.0
        zustellung.seen(self.uid, "web", 0, key="a" * 16, now=now, dev="web:laptop:tab1")
        zustellung.seen(self.uid, "web", 0, key="a" * 16, gone=True, now=now + 1, dev="web:laptop:tab2")
        zustellung.seen(self.uid, "web", 0, key="c" * 16, gone=True, now=now + 2, dev="web:other")
        self.assertEqual([k for _, k, _ in zustellung.in_use(self.uid, now + 3)], ["a" * 16])

    def test_seen_only_by_the_browser_it_went_to(self):
        now = 10000.0
        zustellung.sent(self.uid, ["web"], {"title": "T", "body": "B", "tag": "pro-x", "private": True, "why": "",
                                             "ref": ""}, now=now, keys=["a" * 16])
        x = zustellung._out[self.uid][-1]
        zustellung.seen(self.uid, "web", 0, key="b" * 16, now=now + 30, dev="web:other")      # another browser touched
        self.assertFalse(zustellung._was_seen(self.uid, x))
        zustellung.seen(self.uid, "web", 0, key="a" * 16, now=now + 40, dev="web:mine")
        self.assertTrue(zustellung._was_seen(self.uid, x))

    def test_devices_per_profile_are_bounded(self):
        for i in range(zustellung.DEVICES_MAX + 5):
            zustellung.seen(self.uid, "web", 0, now=1000.0 + i, dev=f"web:{i}")
        self.assertEqual(len(zustellung._sig[self.uid]), zustellung.DEVICES_MAX)
        self.assertIn(("web", f"web:{zustellung.DEVICES_MAX + 4}"), zustellung._sig[self.uid])   # the newest stays

    def test_the_page_names_its_tab_and_the_server_its_login(self):
        r = self.c.post("/api/zustellung/da", json={"idle": 0, "tab": "abc123"})
        self.assertEqual(r.status_code, 200, r.text)
        self.c.post("/api/zustellung/da", json={"idle": 0, "tab": "<script>"})               # not a tab name
        devs = sorted(d for _, d in zustellung._sig[self.uid])
        self.assertEqual(len(devs), 2)
        self.assertTrue(devs[0].startswith("web:") and devs[0].endswith(":abc123") or devs[1].endswith(":abc123"))
        self.assertFalse(any("<" in d for d in devs))
        js = read(STATIC, "reminders.js")
        self.assertIn("tab:typeof TAB==='string'?TAB:undefined", js)

    def test_the_begleiter_says_it_per_computer(self):
        src = read(os.path.dirname(chat.__file__), "begleiter.py")
        self.assertIn('zustellung.seen(prof["id"], "desk", idle, dev=profiles.geraet(request))', src)


class MainConversation(unittest.TestCase):
    """M1: fixed for the day, never the one changed last."""

    def test_fixed_for_the_day(self):
        a, uid = profile("Haupt Hanna")
        local = datetime.datetime(2026, 11, 10, 12, 0)
        stamp = int(local.timestamp() * 1000)
        profiles.save_convo(uid, {"id": "thema1", "title": "Urlaub", "updated": stamp, "msgs": [{"role": "user", "content": "A"}]})
        got, log = quiet(verlauf.main_today, uid, local)
        self.assertEqual(got[0], "thema1")
        self.assertIn("chat: hauptgespraech festgelegt | vorhanden", log)
        profiles.save_convo(uid, {"id": "thema2", "title": "Garten", "updated": stamp + 5000, "msgs": [{"role": "user", "content": "B"}]})
        self.assertEqual(quiet(verlauf.main_today, uid, local)[0][0], "thema1")   # changed later: not the main one
        self.assertEqual(profiles.read_own(uid, verlauf.MAIN_FILE, {}), {"tag": "20261110", "id": "thema1"})
        profiles.delete_convo(uid, "thema1")                                     # deleted: the next need fixes anew
        self.assertEqual(quiet(verlauf.main_today, uid, local)[0][0], "thema2")
        next_day = local + datetime.timedelta(days=1)
        got, log = quiet(verlauf.main_today, uid, next_day)                      # a new day: a new one
        self.assertEqual(got, ("tag-20261111", "Heute 11.11."))
        self.assertIn("| neu", log)
        self.assertEqual(quiet(verlauf.main_today, uid, next_day)[0][0], "tag-20261111")


class FollowUps(unittest.TestCase):
    """M2: Siri's and the Begleiter's history per device."""

    def test_two_devices_never_share_their_history(self):
        _, uid = profile("Siri Silas")
        k1 = profiles.add_device("iPhone Siri Silas", uid)
        k2 = profiles.add_device("iPad Siri Silas", uid)
        chat._SIRI.clear()
        c = TestClient(panel.app)
        for k, text in ((k1, "Wie heißt der Mond des Mars?"), (k2, "Und morgen?")):
            n = len(helpers.LLM_CALLS)
            r, _ = quiet(c.post, "/api/siri/ask", json={"text": text}, headers={profiles.DEVICE_HEADER: k})
            self.assertEqual(r.status_code, 200, r.text)
            sent = json.dumps([m for x in helpers.LLM_CALLS[n:] for m in x.get("messages", []) if m.get("role") != "system"])
        self.assertNotIn("Mond des Mars", sent)                                  # the iPad never got the iPhone's question
        self.assertEqual(len([k for k in chat._SIRI if k[1] == uid]), 2)
        self.assertTrue(all(k[2].startswith("dev:") for k in chat._SIRI if k[1] == uid))


class Offline(unittest.TestCase):
    """N1: a queued question keeps its conversation."""

    def test_the_queue_keeps_the_conversation(self):
        js = read(STATIC, "verlauf.js")
        chatjs = read(STATIC, "chat.js")
        self.assertIn("offlineQueue(text,cid)", chatjs)
        self.assertIn("q.push({t:String(text).slice(0,2000),c:", js)
        flush = js[js.index("async function offlineFlush"):]
        self.assertRegex(flush, r"if\(cid&&cid!==chat\.cid\)\{if\(convos\.load\(\)\.some\(c=>c\.id===cid\)\)showConvo\(cid\)")
        self.assertIn("typeof x==='string'?x:", flush)                         # older plain entries still go out


class Displaced(unittest.TestCase):
    """N2: the stream that gives way ends with "verdraengt" and asks the page to come back later."""

    def test_the_oldest_stream_ends_and_says_so(self):
        hub = sse.Hub(5, 1, beat=60)

        async def go():
            old = hub.stream("u", lambda: True, 600)
            it = old.body_iterator
            first = await it.__anext__()                                         # "retry: 5000"
            with contextlib.redirect_stdout(io.StringIO()) as out:
                hub.stream("u", lambda: True, 600)                               # a newer page
            rest = []
            async for chunk in it:                                               # ends by itself, no beat needed
                rest.append(chunk)
            return first, rest, out.getvalue()
        first, rest, log = asyncio.run(asyncio.wait_for(go(), 10))
        self.assertTrue(first.startswith("retry: 5000"))
        self.assertEqual(len(rest), 1)
        self.assertIn(f"retry: {sse.GONE_RETRY_MS}", rest[0])
        self.assertIn('"type": "verdraengt"', rest[0])
        self.assertIn("seite: ereignisstrom verdraengt", log)
        self.assertEqual(hub.count(), 1)
        js = read(STATIC, "verlauf.js")
        self.assertIn("ev.type==='verdraengt'", js)


if __name__ == "__main__":
    unittest.main()
