"""Funktionen vorschlagen (tipps.py, plan plaene/funktionen-entdecken.md): the assistant points out a function that
is not on yet and helps setting it up.

Off without the admin's switch, for a profile the admin blocked, for guests or a device key (since Freigabe
vereinfachen, Dominik 2026-10-13, what the admin releases works for every profile at once). Which hint comes is fixed rules
(the Weiche's group and features.reason, half set up, done often, new), never the model, and nothing switches by
itself: a plain own switch goes on a card that only the person's tap applies, the rest is a guided setup, and what
only the admin can switch is "Admin fragen" (once a day, only the function's name). Sparing: one hint per
conversation, three a week, "Nicht mehr zeigen" for good, none after outside text, under the Notaus, at a speaker,
on Telegram or over MCP. Only kinds and counts are stored, never the question. No test depends on the wall clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import json
import os
import time
import unittest
from unittest import mock

from tests import helpers
from tests.test_ui_browser import PAGE_READY, async_playwright, browser_ok, chromium

helpers.start()
import panel  # noqa: E402
import features  # noqa: E402
import hilfe  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
import proactive  # noqa: E402
import onboard  # noqa: E402
import tipps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000


def profile(name, pin="1234", admin=False):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    if admin:
        assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


def why_events(c, text, **body):
    r = c.post("/api/chat", json=dict({"messages": [{"role": "user", "content": text}], "speak": False}, **body))
    assert r.status_code == 200, r.text
    return [e for e in helpers.events(r) if e["type"] == "why"]


WISH = {"key": "tasks", "why": "spark"}


def block(test, key, uid, on=False):
    """The admin blocks a function for one profile (Personen und Geräte → Gesperrte Funktionen), lifted again after the test."""
    test.assertEqual(ADMIN.put(f"/api/admin/features/{key}/profiles/{uid}", json={"on": on}).status_code, 200)
    if not on:
        test.addCleanup(ADMIN.put, f"/api/admin/features/{key}/profiles/{uid}", json={"on": True})


class Tipps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.uid = profile("Tipptest")
        cls.a, cls.auid = profile("Tippadmin", admin=True)
        cls.o, cls.ouid = profile("Tippandere")

    def setUp(self):
        helpers.keep_chat(self, "spark_help", "feature_tips", "tasks")
        helpers.set_config(spark_help=True, feature_tips=True, tasks=False, weather=False, routing=False, direct_read=False,
                           proactive=False)
        for uid in (self.uid, self.auid, self.ouid):
            tipps.forget(uid)
            profiles.save_settings(uid, {"pro_on": True, "pro_tips": True})

    def tearDown(self):
        try:
            os.remove(notaus.FILE)
        except FileNotFoundError:
            pass
        helpers.set_config(feature_tips_push=False, proactive=False)

    # ---------------------------------------------------------------- switches
    def test_off_by_default_and_never_for_guests(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            chat = json.load(f)["chat"]
        self.assertIs(chat["feature_tips"], True)  # Grundausstattung (2026-10-17)
        self.assertIn("chat.feature_tips", features.GRUNDAUSSTATTUNG)
        self.assertIs(chat["feature_tips_push"], False)
        self.assertNotIn("tips_on", profiles.SETTINGS)                 # no release switch per profile any more
        self.assertIs(profiles.SETTINGS["pro_tips"][0], True)          # the note by itself: a preference, on unless off
        self.assertFalse(features.allowed("tipps", None))
        self.assertFalse(features.allowed("tipps", None))
        self.assertIsNone(tipps.wish(None, WISH))
        helpers.set_config(feature_tips=False)
        self.assertIsNone(tipps.wish(self.uid, WISH, now=T0))
        self.assertEqual(self.p.get("/api/profile/tipps").json(), {"on": False, "items": []})
        self.assertEqual(self.p.post("/api/profile/tipps/f:tasks", json={"do": "setup"}).status_code, 403)
        self.assertFalse(self.p.get("/api/whoami").json()["tipps"])
        helpers.set_config(feature_tips=True, spark_help=False)   # it lives under "Hilfe zum Spark"
        self.assertFalse(features.allowed("tipps", self.uid))
        helpers.set_config(spark_help=True)
        self.assertTrue(features.allowed("tipps", self.uid))                        # released: on for the profile at once
        # the admin blocks it for this one profile
        block(self, "tipps", self.uid)
        self.assertIsNone(tipps.wish(self.uid, WISH, now=T0))
        self.assertFalse(self.p.get("/api/whoami").json()["tipps"])
        self.assertEqual(self.p.post("/api/profile/tipps/f:tasks", json={"do": "setup"}).status_code, 403)
        self.assertTrue(features.allowed("tipps", self.ouid))                       # only that one
        block(self, "tipps", self.uid, on=True)
        self.assertTrue(self.p.get("/api/whoami").json()["tipps"])
        guest = TestClient(panel.app)
        self.assertIn(guest.get("/api/profile/tipps").status_code, (401, 403))
        key = profiles.add_device("tipp-test", self.uid)
        self.assertFalse(TestClient(panel.app).get("/api/whoami", headers={profiles.DEVICE_HEADER: key}).json()["tipps"])

    # ---------------------------------------------------------------- 1: a wish without its tool
    def test_wish_comes_from_the_rules_with_the_way_to_set_it_up(self):
        tip = tipps.wish(self.uid, WISH, "c1", now=T0)
        self.assertEqual((tip["kind"], tip["key"], tip["how"], tip["me"]), ("wish", "tasks", "ask", "taskbox"))   # a profile asks the admin
        tip = tipps.wish(self.auid, {"key": "weather", "why": "spark"}, "c3", admin=True, now=T0)
        self.assertEqual(tip["how"], "admin")                      # the admin switches it in Funktionen
        # a preference the profile switched off: the guided setup on its own page, never a release switch
        helpers.set_config(proactive=True)
        profiles.save_settings(self.uid, {"pro_on": False})
        tip = tipps.wish(self.uid, {"key": "proactive", "why": "profile"}, "c2", now=T0)
        self.assertEqual((tip["how"], tip["me"]), ("setup", "probox"))
        self.assertIsNone(tipps.wish(self.uid, {"key": "weather", "why": "voice"}, "c4", now=T0))
        self.assertIsNone(tipps.wish(self.uid, {"key": "weather", "why": "blocked"}, "c6", now=T0))   # blocked: no nagging
        self.assertIsNone(tipps.wish(self.uid, {"key": "../x", "why": "profile"}, "c5", now=T0))

    def test_wish_in_the_chat_stream(self):
        ev = why_events(self.p, "Setz Milch auf die Einkaufsliste", convo="k1")
        self.assertEqual(len(ev), 1, ev)
        self.assertEqual((ev[0]["key"], ev[0]["why"]), ("tasks", "spark"))
        self.assertEqual((ev[0]["tip"]["kind"], ev[0]["tip"]["how"]), ("wish", "ask"))
        self.assertFalse(features.chat_cfg()["tasks"])                  # nothing switched by itself
        # once per conversation
        self.assertIsNone(why_events(self.p, "Setz Brot auf die Einkaufsliste", convo="k1")[0]["tip"])
        # nothing stored of the question
        with open(tipps.FILE) as f:
            self.assertNotIn("Milch", f.read())

    def test_sparing(self):
        self.assertIsNotNone(tipps.wish(self.uid, WISH, "a", now=T0))
        self.assertIsNone(tipps.wish(self.uid, WISH, "a", now=T0 + 1))              # one per conversation
        self.assertIsNotNone(tipps.wish(self.uid, WISH, "b", now=T0 + 2))
        self.assertIsNotNone(tipps.wish(self.uid, WISH, "c", now=T0 + 3))
        self.assertIsNone(tipps.wish(self.uid, WISH, "d", now=T0 + 4))              # three a week
        self.assertIsNotNone(tipps.wish(self.uid, WISH, "e", now=T0 + tipps.WEEK + 5))
        # quiet: outside text, speaker, Telegram, MCP, watch, Siri, the Notaus
        self.assertIsNone(tipps.wish(self.ouid, WISH, "x", outside=True, now=T0))
        for org in ("speaker", "telegram", "mcp", "watch", "siri"):
            self.assertIsNone(tipps.wish(self.ouid, WISH, "x", org=org, now=T0), org)
        with mock.patch.object(notaus, "refuse", return_value=True):
            self.assertIsNone(tipps.wish(self.ouid, WISH, "x", now=T0))
        self.assertIsNotNone(tipps.wish(self.ouid, WISH, "x", org="kopf", now=T0))

    def test_never_is_for_good(self):
        self.assertEqual(self.p.post("/api/profile/tipps/f:tasks", json={"do": "never"}).json(), {"state": "never"})
        self.assertIsNone(tipps.wish(self.uid, WISH, "z", now=T0 + 10 * tipps.WEEK))
        self.assertEqual(self.p.post("/api/profile/tipps/<x>", json={"do": "never"}).status_code, 404)
        self.assertEqual(self.p.post("/api/profile/tipps/f:gibtsnicht", json={"do": "never"}).status_code, 404)
        self.assertEqual(self.p.post("/api/profile/tipps/f:tasks", json={"do": "switch"}).status_code, 400)

    # ---------------------------------------------------------------- 5: setting it up
    def test_setup_guides_and_never_switches_by_itself(self):
        helpers.set_config(proactive=True)
        profiles.save_settings(self.uid, {"pro_on": False})
        d = self.p.post("/api/profile/tipps/f:proactive", json={"do": "setup"}).json()
        self.assertEqual((d["how"], d["me"]), ("setup", "probox"))
        self.assertTrue(d["steps"])
        self.assertFalse([s for s in d["steps"] if s.startswith("Admin")])   # a profile gets only its own steps
        self.assertIsNone(d["card"])                                    # no release switch to put on a card
        self.assertIs(profiles.settings(self.uid)["pro_on"], False)     # nothing switched by itself
        r = self.p.post("/api/profile/tipps/f:proactive", json={"do": "check"}).json()
        self.assertEqual((r["ok"], r["why"]), (False, "Von dir ausgeschaltet"))
        profiles.save_settings(self.uid, {"pro_on": True})               # the person sets it on its own page
        self.assertTrue(self.p.post("/api/profile/tipps/f:proactive", json={"do": "check"}).json()["ok"])
        # blocked by the admin: the check says so
        helpers.set_config(tasks=True)
        self.assertTrue(self.p.post("/api/profile/tipps/f:tasks", json={"do": "check"}).json()["ok"])
        block(self, "tasks", self.uid)
        r = self.p.post("/api/profile/tipps/f:tasks", json={"do": "check"}).json()
        self.assertEqual((r["ok"], r["why"]), (False, "Vom Admin für dich gesperrt"))

    def test_setup_never_puts_a_spark_switch_or_security_on_a_profiles_card(self):
        helpers.set_config(weather=False)
        d = self.p.post("/api/profile/tipps/f:weather", json={"do": "setup"}).json()
        self.assertEqual((d["how"], d["card"]), ("ask", None))
        d = self.p.post("/api/profile/tipps/f:mfa", json={"do": "setup"}).json()
        self.assertIsNone(d["card"])                                    # security only by hand
        import guard
        with mock.patch.object(guard, "limit", lambda *a, **k: None):   # every function once: past the rate limit
            ds = {key: self.p.post(f"/api/profile/tipps/f:{key}", json={"do": "setup"}).json() for key in features.BY_KEY}
        for key, d in ds.items():
            for x in (d["card"] or {}).get("items", []):
                self.assertEqual(x["kind"], "profile", key)
                self.assertIn(x["key"], hilfe.APPLY_PROFILE, key)

    def test_setup_under_the_notaus_has_no_card(self):
        with mock.patch.object(notaus, "refuse", return_value=True):
            d = self.p.post("/api/profile/tipps/f:tasks", json={"do": "setup"}).json()
        self.assertIsNone(d["card"])

    def test_ask_the_admin_once_a_day_only_the_name(self):
        helpers.set_config(weather=False)
        sent = []

        async def fake_send(uid, title, body, tag="", private=True, why=""):
            sent.append((uid, title, body, tag))
            return 1
        with mock.patch("push.send", fake_send), mock.patch.object(tipps, "_admins", return_value=[self.auid, self.uid]):
            helpers.set_config(proactive=True)
            profiles.save_settings(self.uid, {"pro_on": False})
            self.assertEqual(self.p.post("/api/profile/tipps/f:proactive", json={"do": "ask"}).status_code, 409)   # its own preference
            r = self.p.post("/api/profile/tipps/f:weather", json={"do": "ask"})
            self.assertEqual(r.json(), {"state": "asked", "reached": 1})
            self.assertEqual(self.p.post("/api/profile/tipps/f:weather", json={"do": "ask"}).status_code, 429)
            with mock.patch.object(notaus, "refuse", return_value=True):
                self.assertEqual(self.o.post("/api/profile/tipps/f:weather", json={"do": "ask"}).status_code, 423)
        self.assertEqual([(u, tag) for u, _, _, tag in sent], [(self.auid, "admin")])   # never to itself
        self.assertIn("„Wetter“", sent[0][2])

    # ---------------------------------------------------------------- 2-4: half set up, done often, new; 6: the list
    def test_gap_from_the_profiles_own_state(self):
        helpers.set_config(iphone=True, iphone_push=True)
        profiles.save_settings(self.uid, {"app_push": False})
        try:
            with mock.patch.object(tipps, "_my_devices", return_value=[{"id": "d1", "app": True}]):
                items = self.p.get("/api/profile/tipps").json()["items"]
                self.assertEqual([(x["id"], x["kind"], x["how"]) for x in items][:1], [("g:apppush", "gap", "setup")])
                self.assertIn("iPhone", items[0]["why"][0])
                self.p.post("/api/profile/tipps/g:apppush", json={"do": "never"})
                self.assertNotIn("g:apppush", [x["id"] for x in self.p.get("/api/profile/tipps").json()["items"]])
            # another profile without the app gets nothing of this
            self.assertNotIn("g:apppush", [x["id"] for x in self.o.get("/api/profile/tipps").json()["items"]])
        finally:
            helpers.set_config(iphone=False, iphone_push=False)

    def test_repeat_counts_kinds_only(self):
        helpers.set_config(local_first=False)   # would help, the admin can switch it
        try:
            for i in range(4):
                tipps.record(self.uid, ["websuche"], False, now=T0 + i)
            self.assertNotIn("f:lokal", [x["id"] for x in tipps.candidates(self.uid, now=T0 + 10)])
            tipps.record(self.uid, ["websuche", "../evil", "kalender"], False, now=T0 + 5)
            items = tipps.candidates(self.uid, now=T0 + 10)
            self.assertIn(("f:lokal", "repeat"), [(x["id"], x["kind"]) for x in items])
            st = tipps._st(self.uid)
            self.assertEqual({k for d in st["count"].values() for k in d}, {"websuche"})
            self.assertNotIn("f:lokal", [x["id"] for x in tipps.candidates(self.uid, now=T0 + 8 * 86400)])  # a week back only
            block(self, "tipps", self.uid)
            tipps.record(self.uid, ["websuche"], False, now=T0 + 6)    # blocked for the profile: nothing counted
            self.assertEqual(sum(d.get("websuche", 0) for d in tipps._st(self.uid)["count"].values()), 5)
        finally:
            helpers.set_config(local_first=False)
        helpers.set_config(local_first=True)
        self.addCleanup(helpers.set_config, local_first=False)
        self.assertNotIn("f:lokal", [x["id"] for x in tipps.candidates(self.uid, now=T0 + 10)])   # on now: no hint

    def test_new_only_what_the_profile_sets_up_itself(self):
        """Dominik 2026-10-14: a released function works for every profile at once, so "neu" is only a hint where
        the profile still sets something up itself (its item under Los geht's); „Rückfrage statt Raten“, Chats and
        the Dienst-Wächter just work and never come."""
        helpers.set_config(weather=True, wiki=True, chats=True, klaeren=True, svc_watch=True)
        self.addCleanup(helpers.set_config, weather=False, wiki=False, chats=False, klaeren=False, svc_watch=False)
        plain = ("wiki", "chats", "klaeren", "dienstwacht")
        for key in plain:
            self.assertTrue(features.admin_on(key), key)
            self.assertIsNone(onboard.own_setup(key), key)
        self.assertEqual(onboard.own_setup("weather"), ("weather", "wxbox"))
        tipps._mut(self.uid, lambda st: st.update(since=T0))
        seen = {k: T0 + 100 for k in plain + ("weather",)}
        with mock.patch.object(features, "_seen", return_value=seen):
            new = [x for x in tipps.candidates(self.uid, now=T0 + 200) if x["kind"] == "new"]
            self.assertEqual([(x["id"], x["me"]) for x in new], [("f:weather", "wxbox")])
            # NEW_DAYS after the release it ends, set up or not
            last = T0 + 100 + tipps.NEW_DAYS * 86400
            self.assertIn("f:weather", [x["id"] for x in tipps.candidates(self.uid, now=last - 1)])
            self.assertNotIn("f:weather", [x["id"] for x in tipps.candidates(self.uid, now=last)])
            with mock.patch.object(features, "_seen", return_value={"weather": T0 - 100}):   # on before: not new
                self.assertNotIn("f:weather", [x["id"] for x in tipps.candidates(self.uid, now=T0 + 200)])
            # set up (the panel checks it, onboard.done): gone
            with mock.patch.object(onboard, "done", return_value=True):
                self.assertNotIn("f:weather", [x["id"] for x in tipps.candidates(self.uid, now=T0 + 200)])
            # blocked for this profile: no hint either
            block(self, "weather", self.uid)
            self.assertNotIn("f:weather", [x["id"] for x in tipps.candidates(self.uid, now=T0 + 200)])

    def test_new_goes_once_check_says_it_works(self):
        """„Prüfen“ asks the panel whether it is set up; once it is, the hint does not come again."""
        helpers.set_config(weather=True)
        self.addCleanup(helpers.set_config, weather=False)
        now = int(time.time())   # the endpoint uses the clock: release and start relative to it
        tipps._mut(self.uid, lambda st: st.update(since=now - 1000))
        with mock.patch.object(features, "_seen", return_value={"weather": now - 900}):
            self.assertIn("f:weather", [x["id"] for x in self.p.get("/api/profile/tipps").json()["items"]])
            r = self.p.post("/api/profile/tipps/f:weather", json={"do": "check"}).json()
            self.assertEqual(r, {"ok": False, "why": "Noch nicht eingerichtet."})
            self.assertEqual(self.p.post("/api/profile/tipps/f:weather", json={"do": "check", "lang": "en"}).json()["why"],
                             "Not set up yet.")
            with mock.patch.object(onboard, "done", return_value=True):
                self.assertEqual(self.p.post("/api/profile/tipps/f:weather", json={"do": "check"}).json(), {"ok": True, "why": ""})
            self.assertIn("f:weather", tipps._st(self.uid)["done"])
            # remembered: it stays away even while the panel would still miss something
            self.assertNotIn("f:weather", [x["id"] for x in self.p.get("/api/profile/tipps").json()["items"]])

    def test_setup_jumps_to_the_setting(self):
        """„Seite öffnen“ goes to the row or part the person fills in: the guide's own way into Ich, else the
        function's row on its Ich page, else the page."""
        was = features.chat_cfg().get("calendar")
        helpers.set_config(calendar=True, klaeren=True)
        self.addCleanup(helpers.set_config, calendar=was, klaeren=False)
        d = self.p.post("/api/profile/tipps/f:calendar", json={"do": "setup"}).json()
        self.assertTrue(d["way"].startswith("Kalender → Einstellungen → „Kalender hinzufügen“"), d["way"])
        d = self.p.post("/api/profile/tipps/f:calendar", json={"do": "setup", "lang": "en"}).json()
        self.assertTrue(d["way"].startswith('Calendar → Settings → "Add calendar"'), d["way"])
        d = self.p.post("/api/profile/tipps/f:klaeren", json={"do": "setup"}).json()
        self.assertEqual(d["way"], features.me_way("klaeren"))
        self.assertEqual(tipps._way({"key": "", "me": "secbox"}, []), "Ich → Sicherheit")
        self.assertEqual(tipps._way({"key": "", "me": ""}, []), "")

    def test_list_holds_at_most_three_and_never_admin_items_for_a_profile(self):
        many = [tipps._tip("new", f"f:{k}", k, self.uid, False, ["", ""]) for k in ("wiki", "kiwix", "lokal", "roles")]
        with mock.patch.object(tipps, "candidates", return_value=many):
            self.assertEqual(len(self.p.get("/api/profile/tipps").json()["items"]), 3)
        for x in tipps.candidates(self.uid):
            self.assertNotEqual(x["how"], "admin")

    # ---------------------------------------------------------------- 7: once a week by itself
    def test_weekly_note_needs_its_switches_and_comes_once_a_week(self):
        helpers.set_config(proactive=True, weather=True)
        try:
            tipps._mut(self.uid, lambda st: st.update(since=T0))
            with mock.patch.object(features, "_seen", return_value={"weather": T0 + 100}):
                self.assertEqual(tipps.weekly_text(self.uid, now=T0 + 200), ("", None))   # admin switch off
                helpers.set_config(feature_tips_push=True)
                profiles.save_settings(self.uid, {"pro_tips": False})
                self.assertEqual(tipps.weekly_text(self.uid, now=T0 + 200), ("", None))   # preference off
                profiles.save_settings(self.uid, {"pro_tips": True})
                text, tip = tipps.weekly_text(self.uid, now=T0 + 200)
                self.assertIn("Wetter", text)
                self.assertEqual(tip["id"], "f:weather")
                self.assertEqual(tipps.weekly_text(self.uid, now=T0 + 300), ("", None))
                self.assertTrue(tipps.weekly_text(self.uid, now=T0 + 200 + tipps.WEEK)[0])
            self.assertIn("tipp", proactive.KINDS)
            self.assertEqual(proactive.KINDS["tipp"][2], "pro_tips")
        finally:
            helpers.set_config(proactive=False, weather=False, feature_tips_push=False)

    # ---------------------------------------------------------------- the rest of the Spark knows it
    def test_registered_everywhere(self):
        import account
        import guard
        self.assertEqual(account.ALLOW["tips_on"], "tipps")
        self.assertIn("tipps", guard.RATE)
        guides = {g["id"] for g in hilfe.guides()}
        self.assertTrue({"tipps", "tippspush"} <= guides)
        with open(os.path.join(os.path.dirname(tipps.__file__), "static", "index.html")) as f:
            page = f.read()
        self.assertIn('id="chat.feature_tips"', page)
        self.assertIn('id="chat.feature_tips_push"', page)
        self.assertIn("/static/js/tipps.js", page)

    def test_profile_deleted_forgets_its_hints(self):
        c, uid = profile("Tippweg")
        tipps.record(uid, ["websuche"], False, now=T0)
        self.assertIn(uid, tipps._all())
        ADMIN.delete(f"/api/admin/profiles/{uid}")
        self.assertNotIn(uid, tipps._all())


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    """Dominik 2026-10-14: „springt nicht genau auf die Einstellungen“ and „nach erfolgreicher Einrichtung sollten
    diese Meldungen verschwinden“: the setup lands on the row and marks it, and „Prüfen“ takes the entry away."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Tippsprung", "4711")
        except Exception:
            pass
        cls.uid = next(u["id"] for u in profiles._load()["users"] if u["name"] == "Tippsprung")

    async def until(self, pg, expr, seconds=20):
        for _ in range(int(seconds * 10)):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    def test_setup_lands_on_the_row_and_check_takes_the_hint_away(self):
        was = features.chat_cfg().get("calendar")
        helpers.set_config(spark_help=True, feature_tips=True, calendar=True, weather=True)
        self.addCleanup(helpers.set_config, spark_help=False, feature_tips=False, calendar=was, weather=False)
        tipps.forget(self.uid)
        self.addCleanup(tipps.forget, self.uid)
        now = int(time.time())
        tipps._mut(self.uid, lambda st: st.update(since=now - 1000))
        seen = mock.patch.object(features, "_seen", return_value={"weather": now - 900})
        seen.start()
        self.addCleanup(seen.stop)

        async def go():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                pg = await (await br.new_context(viewport={"width": 1280, "height": 900}, locale="de-DE")).new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                base = f"http://127.0.0.1:{self.port}"
                await pg.goto(base + "/")
                r = await pg.request.post(base + "/api/profile/login", data={"name": "Tippsprung", "pin": "4711"})
                self.assertEqual(r.status, 200)
                await pg.goto(base + "/")
                await self.until(pg, PAGE_READY + "&&!!PROFILE&&TIPS_ON")
                await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
                # what way.js marks
                await pg.evaluate("window.FLASHED=[];const o=sFlash;sFlash=el=>{FLASHED.push(visText(el));o(el)}")
                # the setup of the calendar lands on „Kalender hinzufügen“ on Kalender → Einstellungen (a page of its own)
                await pg.evaluate("tipSetup({id:'f:calendar'})")
                await self.until(pg, "$('cal').classList.contains('on')&&!$('calbox').hidden&&$('kalroot').contains($('calbox'))")
                await self.until(pg, "FLASHED.some(x=>x.includes('Kalender hinzufügen'))")
                # Ich → Überblick lists the new weather; „Prüfen“ after it is set up takes it away
                await pg.evaluate("$('tipsetup')&&$('tipsetup').remove();openMe('overbox')")
                await self.until(pg, "!!document.querySelector('#tipover .tipitem[data-tip=\"f:weather\"]')")
                await pg.click("#tipover .tipitem[data-tip='f:weather'] button.p")
                await self.until(pg, "!!$('tipsetup')&&document.querySelector('#ptabs button.on').dataset.t==='wxbox'")
                with mock.patch.object(onboard, "done", return_value=True):
                    await pg.click("#tipsetup .row button.p")
                    await self.until(pg, "$('tipsetup').textContent.includes('Eingerichtet')")
                self.assertFalse(await pg.evaluate("!!document.querySelector('#tipover .tipitem[data-tip=\"f:weather\"]')"))
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
