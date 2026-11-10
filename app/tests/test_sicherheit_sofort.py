"""P1 „Sicherheit sofort“ (Code-Review 10.11.2026, Dominik „1a, Rest nach Empfehlung“): one test per protection rule.

- K1: a browser's push subscription belongs to exactly one profile (push.add takes it from every other profile); it
  ends with the browser login that switched it on (Abmelden, a login ended, Überall abmelden: push.drop_login,
  logins_ended); the page shows „An“ only when the profile lists this browser and gives it up after a change of profile.
- H1 (review A-H6): a note never goes to another browser because the browser in use has no subscription (push.pick,
  zustellung.pick): the next way of the profile instead; the newest browser only when browsers are all it has.
- K2: answers of the conversation list asked for the profile before are dropped after a change of profile (chat.js).
- K3 + H4: negation is one fixed rule (intent.negated): no direct smart home command, Assist and the fallback never
  switch a negated command, nothing is narrowed, no changing or internet tool is a must; „Vergiss es“ is a cancel
  (plaudern, no tool), memory_forget runs only on the person's own word to forget.
- K4: only strong words make the web search a must; a private sentence (mein, health, money, „Nachrichten von Tom“)
  never does, and weak words alone give it no group websuche. An admin Pflicht-Regel never makes a changing tool a must.
- H2: a smart home command waiting for the code word belongs to its source (chat.ha_take): another device's code word
  neither runs nor clears it.

No clock (times are passed in), no network, no model.
"""
import asyncio
import contextlib
import io
import os
import re
import time
import types
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import apns  # noqa: E402
import android  # noqa: E402
import begleiter  # noqa: E402
import chat  # noqa: E402
import chat_tools  # noqa: E402
import homeassistant  # noqa: E402
import intent  # noqa: E402
import klaeren  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
import telegram  # noqa: E402
import zustellung  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
JS = os.path.join(os.path.dirname(helpers.__file__), "..", "panel", "static", "js")


def sub(name):
    return {"endpoint": "https://fcm.googleapis.com/fcm/send/p1-" + name,
            "keys": {"p256dh": push.b64(b"\x04" + b"7" * 64), "auth": push.b64(b"s" * 16)}}


def profile(name, pin="2468"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def sid_of(c):
    raw = c.cookies.get(profiles.COOKIE) or ""
    return raw.split(".")[2] if raw.count(".") == 3 else ""


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        res = fn(*a, **k)
    return res, out.getvalue()


def js(name):
    with open(os.path.join(JS, name), encoding="utf-8") as f:
        return f.read()


class PushOneProfile(unittest.TestCase):
    """K1: one subscription, one profile; it ends with its login."""

    @classmethod
    def setUpClass(cls):
        cls.ca, cls.a = profile("Sofort Saskia")
        cls.cb, cls.b = profile("Sofort Severin")

    def setUp(self):
        for uid in (self.a, self.b):
            for s in push.subs(uid):
                push.remove(uid, s["endpoint"])

    def test_the_same_browser_leaves_the_profile_before(self):
        push.add(self.a, sub("shared"))
        self.assertEqual([s["endpoint"] for s in push.subs(self.a)], [sub("shared")["endpoint"]])
        _, log = quiet(push.add, self.b, sub("shared"))
        self.assertEqual(push.subs(self.a), [])                     # Saskia's notes never reach this browser again
        self.assertEqual([s["endpoint"] for s in push.subs(self.b)], [sub("shared")["endpoint"]])
        self.assertIn("push: browser moved to another profile", log)
        self.assertNotIn("Saskia", log)                             # fixed words, never a name

    def test_logout_ends_the_subscription_of_this_login(self):
        c, uid = profile("Sofort Selma")
        push.add(uid, sub("selma"), login=sid_of(c))
        push.add(uid, sub("selma-other"), login="ffffffffffffffff")    # another browser of hers stays
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post("/api/profile/logout").status_code, 200)
        self.assertEqual([s["endpoint"] for s in push.subs(uid)], [sub("selma-other")["endpoint"]])
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{16}", s["login"]) for s in push.subs(uid)))
        self.assertNotIn("ffffffffffffffff", str(push.subs(uid)))     # only a hash of the login is kept

    def test_ending_a_login_or_logging_out_everywhere_ends_its_subscriptions(self):
        push.add(self.a, sub("one"), login="1111111111111111")
        push.add(self.a, sub("two"), login="2222222222222222")
        push.add(self.a, sub("old"))                                   # an older one without a login stays
        quiet(push.drop_login, self.a, "1111111111111111")
        self.assertEqual({s["endpoint"] for s in push.subs(self.a)}, {sub("two")["endpoint"], sub("old")["endpoint"]})
        quiet(push.logins_ended, self.a, "2222222222222222", "3333333333333333")   # this browser keeps it, new login
        self.assertEqual({s["endpoint"] for s in push.subs(self.a)}, {sub("two")["endpoint"], sub("old")["endpoint"]})
        quiet(push.drop_login, self.a, "3333333333333333")
        self.assertEqual([s["endpoint"] for s in push.subs(self.a)], [sub("old")["endpoint"]])
        push.add(self.a, sub("three"), login="4444444444444444")
        quiet(push.logins_ended, self.a)                               # from an app: every browser login ended
        self.assertEqual([s["endpoint"] for s in push.subs(self.a)], [sub("old")["endpoint"]])

    def test_the_page_binds_its_subscription_to_the_profile(self):
        me = js("me.js")
        show = me[me.index("async function showPush"):me.index("$('briefat').onchange")]
        self.assertIn("pushMine(s)", show)                             # „An“ only when the profile lists it
        mine = me[me.index("async function pushMine"):me.index("async function pushBind")]
        self.assertIn("d.devices.some(x=>x.endpoint===s.endpoint)", mine)
        self.assertIn("s.unsubscribe()", mine)                         # otherwise this browser gives it up
        self.assertIn("gen!==PROFILE_GEN", mine)
        prof = me[me.index("function setProfile"):me.index("const isGuest")]
        self.assertIn("pushBind()", prof)                              # after every change of profile
        self.assertIn("await pushDrop()", me[me.index("$('proflogout').onclick"):])
        self.assertIn("pushDrop()", js("coadmin.js"))


class PushNoOtherBrowser(unittest.TestCase):
    """H1: the browser in use without a subscription never sends the note to another browser."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Sofort Sanna")

    def setUp(self):
        for s in push.subs(self.uid):
            push.remove(self.uid, s["endpoint"])
        push.add(self.uid, sub("drawer"))                               # the old phone in the drawer
        self.real = apns.reachable, android.reachable, telegram.push_on, begleiter.reachable
        self.phone = True
        apns.reachable = lambda u: u == self.uid and self.phone
        android.reachable = lambda u, now=None: False
        telegram.push_on = lambda u, private=True: False
        begleiter.reachable = lambda u, *a, **k: False
        zustellung._sig.pop(self.uid, None)
        profiles.LAST_USED.pop(self.uid, None)

    def tearDown(self):
        apns.reachable, android.reachable, telegram.push_on, begleiter.reachable = self.real
        helpers.set_config(note_device=False)
        zustellung._sig.pop(self.uid, None)
        profiles.LAST_USED.pop(self.uid, None)

    def test_last_used_browser_without_push_goes_to_the_phone(self):
        helpers.set_config(note_device=False)
        profiles.LAST_USED[self.uid] = ("web", "", time.time())        # a page open without push
        (kind, targets), log = quiet(push.pick, self.uid)
        self.assertEqual((kind, targets), ("app", []))
        self.assertIn("push: route web ohne abo | app", log)
        profiles.LAST_USED[self.uid] = ("web", "0123456789abcdef", time.time())   # push of a browser it does not have
        self.assertEqual(quiet(push.pick, self.uid)[0], ("app", []))
        mine = push.sub_id(sub("drawer")["endpoint"])
        profiles.LAST_USED[self.uid] = ("web", mine, time.time())      # the browser in use has it: that one
        kind, targets = quiet(push.pick, self.uid)[0]
        self.assertEqual((kind, [s["endpoint"] for s in targets]), ("web", [sub("drawer")["endpoint"]]))

    def test_only_browsers_left_takes_the_profiles_newest(self):
        helpers.set_config(note_device=False)
        self.phone = False
        profiles.LAST_USED[self.uid] = ("web", "", time.time())
        (kind, targets), log = quiet(push.pick, self.uid)
        self.assertEqual((kind, [s["endpoint"] for s in targets]), ("web", [sub("drawer")["endpoint"]]))
        self.assertIn("neuester browser", log)

    def test_device_in_use_counts_only_with_its_own_subscription(self):
        helpers.set_config(note_device=True, deny={})
        now = time.time()
        zustellung.seen(self.uid, "web", idle=0, key="0123456789abcdef", now=now)   # a browser without push
        with contextlib.redirect_stdout(io.StringIO()):
            got = zustellung.pick(self.uid, {"web": True, "app": True}, now=now)
        self.assertEqual(got[:2], ("app", ""))
        zustellung.seen(self.uid, "web", idle=0, key=push.sub_id(sub("drawer")["endpoint"]), now=now)
        with contextlib.redirect_stdout(io.StringIO()):
            got = zustellung.pick(self.uid, {"web": True, "app": True}, now=now)
        self.assertEqual(got[0], "web")


class ConvosOfTheProfileBefore(unittest.TestCase):
    """K2: an answer asked for the profile before never lands with the next one."""

    def test_every_answer_checks_the_profile_generation(self):
        src = js("chat.js")
        self.assertIn("let PROFILE_GEN=0", src)
        convos = src[src.index("const convos={"):src.index("function saveConvo")]
        for part in ("async add(", "async sync(", "async fresh("):
            body = convos[convos.index(part):]
            body = body[:body.index("\n  async ", 10) if "\n  async " in body[10:] else len(body)]
            self.assertIn("gen=PROFILE_GEN", body.replace("const gen=PROFILE_GEN", "gen=PROFILE_GEN"), part)
            self.assertIn("gen!==PROFILE_GEN", body, part)
        me = js("me.js")
        self.assertIn("if(changed)PROFILE_GEN++", me[me.index("function setProfile"):me.index("const isGuest")])


ITEM = {"url": "http://ha.invalid", "token": "x"}


class Negation(unittest.TestCase):
    """K3 + H4: „nicht“ is one fixed rule of the panel, never the opposite."""

    def test_negated_switching_is_no_direct_command(self):
        for s in ("Mach das Licht nicht aus", "Mach das Licht aus, nein doch nicht", "Kein Licht bitte",
                  "Mach das Licht im Wohnzimmer bloß nicht aus", "Schalte bitte nicht den Fernseher ein",
                  "Don't turn off the light"):
            self.assertTrue(intent.negated(s), s)
            self.assertFalse(homeassistant.is_command(s), s)
        for s in ("Mach das Licht aus", "Schalte den Fernseher ein", "Erinnere mich, die Tabletten nicht zu vergessen",
                  "Vergiss nicht, den Müll rauszustellen"):
            self.assertFalse(intent.negated(s), s)
        self.assertTrue(homeassistant.is_command("Mach das Licht aus"))

    def test_assist_and_the_fallback_never_switch_a_negated_command(self):
        async def never(*a, **k):
            raise AssertionError("Home Assistant was asked")
        real = homeassistant._assist, homeassistant._switchable
        homeassistant._assist = homeassistant._switchable = never
        try:
            (ok, text, targets), log = quiet(asyncio.run, homeassistant.command(ITEM, "Mach das Licht nicht aus"))
            self.assertFalse(ok)
            self.assertTrue(text.startswith("Not done"), text)
            self.assertIn("homeassistant: nothing switched | verneint", log)
            (done, text), _ = quiet(asyncio.run, homeassistant.fallback(ITEM, "Licht im Bad bloß nicht aus"))
            self.assertFalse(done)
            self.assertTrue(text.startswith("Not done"), text)
        finally:
            homeassistant._assist, homeassistant._switchable = real

    def test_a_negated_wish_is_never_narrowed_and_forces_no_changing_tool(self):
        tools = [{"function": {"name": n}} for n in ("iphone_action", "web_search", "calendar_events", "calendar_add",
                                                     "home_assistant", "memory_save")]
        r = intent.classify("Ruf Mama nicht an")
        self.assertEqual(r.names, ["iphone"])                          # the journal still names the group
        self.assertTrue(r.neg)
        self.assertEqual(intent.narrow(r, tools), tools)
        self.assertIsNone(intent.forced(r, ["iphone_action"], {"iphone_action"}))
        r = intent.classify("Trag den Termin nicht ein")
        need = chat.needed("Trag den Termin nicht ein", {"calendar_events", "calendar_add"})
        self.assertEqual(need, ["calendar_events"])
        self.assertEqual(chat.first_tool(r, need, {"calendar_events", "calendar_add"}), "calendar_events")
        # a negated sentence never forces the internet either
        self.assertEqual(chat.needed("Such bloß nicht im Internet danach", {"web_search"}), [])
        self.assertEqual(chat.needed("Such im Internet danach", {"web_search"}), ["web_search"])
        # the admin's own word for a changing tool is never a must (review D-5), one for a reading tool is
        self.assertEqual(chat.needed("Ich will Mama anrufen", {"iphone_action"}, "iphone_action: anrufen"), [])
        self.assertEqual(chat.needed("Zeig mir den Vertrag", {"document_search"}, "document_search: vertrag"),
                         ["document_search"])

    def test_cancel_is_no_memory_wish(self):
        for s in ("Vergiss es", "Vergiss es, war nur Spaß", "Lass es", "Schon gut", "Nein, doch nicht", "Never mind"):
            self.assertTrue(intent.cancel(s), s)
            self.assertEqual(intent.classify(s).names, ["plaudern"], s)
            self.assertFalse(intent.forget_ok(s), s)
            self.assertTrue(klaeren._none(s), s)                       # the same phrases for the panel's own question
        self.assertFalse(intent.cancel("Vergiss, dass ich Tee mag"))
        self.assertTrue(intent.forget_ok("Vergiss, dass ich Tee mag"))
        self.assertTrue(intent.forget_ok("Vergiss, dass ich keinen Kaffee trinke"))
        for s in ("Vergiss das bloß nicht", "Vergiss nicht, dass ich Tee mag", "Ich mag Tee", "Don't forget my tea"):
            self.assertFalse(intent.forget_ok(s), s)

    def test_memory_forget_needs_the_own_word(self):
        c, uid = profile("Sofort Sinja")
        profiles.remember(uid, "Sinja mag Pfefferminztee")
        out = asyncio.Queue()

        def call(said):
            t = types.SimpleNamespace(who={"id": uid}, prof={"id": uid}, ask_text=said, out=out,
                                      ex={"changes": set(), "run": {}, "mail": set(), "outside": set(), "own": set()},
                                      locked=lambda st: set())
            st = {"offered": {"memory_forget"}, "mail": False, "outside": False, "first": True}
            return quiet(asyncio.run, chat_tools.run(t, "memory_forget", {"text": "Pfefferminztee"}, st))

        res, log = call("Vergiss es")
        self.assertTrue(res.startswith("Not done"), res)
        self.assertIn("gedaechtnis: vergessen abgelehnt", log)
        self.assertTrue(any("Pfefferminztee" in x["text"] for x in profiles.memory(uid)))
        res, _ = call("Vergiss das mit dem Pfefferminztee bloß nicht")
        self.assertTrue(res.startswith("Not done"), res)
        res, _ = call("Vergiss, dass ich Pfefferminztee mag")
        self.assertEqual(res, "Forgot 1 fact(s).")
        self.assertFalse(any("Pfefferminztee" in x["text"] for x in profiles.memory(uid)))


class PrivateNeverSearched(unittest.TestCase):
    """K4: the web search is a must only from strong words, never for a private sentence."""

    def test_private_sentences_never_force_the_web(self):
        for s in ("Wie ist das Ergebnis meiner Blutuntersuchung?", "Gibt es Nachrichten von Tom?",
                  "Ich habe im Lotto gewonnen", "Wir haben gewonnen!", "Was ist das Ergebnis von 17 mal 23?",
                  "Ich habe die Tabelle vergessen", "Was hältst du von Politik?", "Wie spielt man Skat?",
                  "Wie hat mein Verein gespielt?", "Wie hoch ist mein Kontostand in der Bundesliga-Tabelle?"):
            self.assertEqual(chat.needed(s, {"web_search"}), [], s)
        for s in ("Wie ist das Ergebnis meiner Blutuntersuchung?", "Gibt es Nachrichten von Tom?",
                  "Ich habe im Lotto gewonnen", "Wir haben gewonnen!"):
            self.assertNotIn("websuche", intent.classify(s).names, s)
        self.assertIn("nachricht", intent.classify("Gibt es Nachrichten von Tom?").names)

    def test_strong_words_still_make_it_a_must(self):
        for s in ("Wer hat gestern gewonnen?", "Wie ist das Spiel ausgegangen?", "Was gibt es in den Nachrichten?",
                  "Such im Internet nach Pizzerien", "Google mal den Fahrplan", "Wie steht es in der Bundesliga?",
                  "Was sind die Schlagzeilen?"):
            self.assertEqual(chat.needed(s, {"web_search"}), ["web_search"], s)
            self.assertIn("websuche", intent.classify(s).names, s)


class CodeWordAtItsSource(unittest.TestCase):
    """H2: the command waiting for the code word belongs to the device it was said at."""

    def test_another_source_neither_runs_nor_clears_it(self):
        uid = "p1-codeword"
        chat.ha_wait(uid, "web:c1:aaa", "Garagentor auf", now=1000)
        self.assertIsNone(chat.ha_take(uid, "telegram::bbb", now=1010))     # another device: nothing runs
        self.assertIsNone(chat.ha_take(uid, "web:c2:aaa", now=1010))        # another conversation neither
        self.assertEqual(chat.ha_take(uid, "web:c1:aaa", now=1020), "Garagentor auf")
        self.assertIsNone(chat.ha_take(uid, "web:c1:aaa", now=1021))         # taken once
        chat.ha_wait(uid, "web:c1:aaa", "Garagentor auf", now=1000)
        self.assertIsNone(chat.ha_take(uid, "web:c1:aaa", now=1000 + chat.HA_WAIT_S))   # too old
        self.assertNotIn(uid, chat._HA_PENDING)

    def test_the_source_names_the_device_or_the_login(self):
        def req(cookie="", key=""):
            heads = ([(b"cookie", f"{profiles.COOKIE}={cookie}".encode())] if cookie else []) \
                + ([(profiles.DEVICE_HEADER.lower().encode(), key.encode())] if key else [])
            return Request({"type": "http", "headers": heads})
        a = chat.ha_source(req("u1.1700000000.1111111111111111.sig"), "web:c1")
        b = chat.ha_source(req("u1.1700000000.2222222222222222.sig"), "web:c1")
        self.assertNotEqual(a, b)                                          # two browsers of the profile
        self.assertTrue(a.startswith("web:c1:"))
        self.assertNotIn("1111111111111111", a)                            # only a hash of the login


if __name__ == "__main__":
    unittest.main()
