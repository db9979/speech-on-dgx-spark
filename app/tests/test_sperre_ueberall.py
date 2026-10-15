"""„Altlasten bereinigen“ (Paket 3 von „Freigabe vereinfachen“): what the admin blocks for one profile (chat.deny,
Funktionen → Wer darf was) holds everywhere a function acts for that profile, offers it something or shows it
something: tools in a chat turn, the pages in /api/whoami, the iPhone app, background jobs (Von selbst, Agent, Home
Assistant live, reMarkable, Telegram) and the endpoints where it sets something up. Another profile keeps all of it.
A static guard keeps it that way: no module gates a profile with features.admin_on alone; every call that is left
is listed here with its reason (admin-only, Spark-wide, or a display flag that is combined with the block).
No test depends on the time of day."""
import ast
import asyncio
import datetime
import glob
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import agent  # noqa: E402
import chat  # noqa: E402
import features  # noqa: E402
import hamelden  # noqa: E402
import iphone  # noqa: E402
import proactive  # noqa: E402
import profiles  # noqa: E402
import remarkable  # noqa: E402
import rmplus  # noqa: E402
import telegram  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOON = datetime.datetime(2026, 10, 13, 12, 0, tzinfo=datetime.timezone.utc)   # a fixed time: never quiet hours


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class Base(unittest.TestCase):
    """Two profiles: Anna, for whom the admin blocks the functions under test, and Bert, who keeps them."""
    BLOCK = ()

    def setUp(self):
        self.a, self.ua = profile("SpAnna")
        self.b, self.ub = profile("SpBert")
        if self.BLOCK:
            self.block(*self.BLOCK)

    def tearDown(self):
        helpers.set_config(deny={})

    def block(self, *keys):
        helpers.set_config(deny={k: [self.ua] for k in keys})
        for k in keys:   # the rule itself first: Anna blocked, Bert not
            self.assertTrue(features.blocked(k, self.ua), k)
            self.assertFalse(features.blocked(k, self.ub), k)


class ChatTools(Base):
    BLOCK = ("memory", "reminders", "search")

    def tools(self, client):
        helpers.LLM_CALLS.clear()
        r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Erzähl mir etwas über Leuchttürme."}],
                                           "convo": "sperre"})
        self.assertEqual(r.status_code, 200, r.text)
        call = next((x for x in helpers.LLM_CALLS if x.get("stream") and "tools" in x), None)
        self.assertIsNotNone(call, "the answer went to the model")
        return {t["function"]["name"] for t in call.get("tools") or []}

    def test_a_blocked_profile_is_offered_none_of_the_blocked_tools(self):
        helpers.set_config(search=True, search_url="http://127.0.0.1:9", routing=False)
        try:
            names = {t["function"]["name"] for t in chat.MEMORY_TOOLS + chat.REMINDER_TOOLS + [chat.SEARCH_TOOL]}
            bert, anna = self.tools(self.b), self.tools(self.a)
            self.assertTrue(names <= bert, names - bert)            # Bert: everything the admin released
            self.assertFalse(names & anna, names & anna)            # Anna: none of it
        finally:
            helpers.set_config(search=False, search_url="")

    def test_the_daily_briefing_leaves_out_what_is_blocked(self):
        helpers.set_config(deny={"calendar": [self.ua]})
        import push
        seen = []
        marks = [profiles._path(u, "briefing-sent") for u in (self.ua, self.ub)]
        for m in marks:   # a fresh profile has no folder yet; no mark left over from an earlier run
            os.makedirs(os.path.dirname(m), exist_ok=True)
            if os.path.exists(m):
                os.remove(m)
        self.addCleanup(lambda: [os.remove(m) for m in marks if os.path.exists(m)])

        async def fake_brief(uid, tz="", markdown=False):
            seen.append(uid)
            return ""
        with mock.patch.object(push, "reachable", return_value=True), \
                mock.patch.object(chat, "morning_briefing", new=fake_brief), \
                mock.patch.object(profiles, "user_ids", return_value=[self.ua, self.ub]), \
                mock.patch.object(profiles, "settings", side_effect=lambda u: {"briefing_at": "11:30", "tz": "UTC"}):
            asyncio.run(chat.due_briefings(now=NOON))
        self.assertNotIn(self.ua, seen)
        self.assertIn(self.ub, seen)


class Pages(Base):
    BLOCK = ("weather", "mail", "calendar")

    def test_whoami_shows_no_page_of_a_blocked_function(self):
        helpers.set_config(weather=True, mail=True)
        try:
            wa, wb = self.a.get("/api/whoami").json(), self.b.get("/api/whoami").json()
            for k in ("weather", "mail", "calendar"):
                self.assertIs(wa[k], False, k)
                self.assertIs(wb[k], True, k)
            self.assertTrue(ADMIN.get("/api/whoami").json()["weather"])   # the admin's own login keeps the pages
        finally:
            helpers.set_config(weather=False, mail=False)

    def test_setting_up_a_blocked_function_is_refused(self):
        r = self.a.post("/api/profile/calendar", json={"url": "https://cal.example/x", "user": "a", "password": "b"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("blocked", r.text)
        r = self.b.post("/api/profile/calendar", json={})
        self.assertNotEqual(r.status_code, 403, r.text)               # Bert gets as far as checking his entry

    def test_the_iphone_app_gets_nothing_blocked(self):
        helpers.set_config(iphone=True, room=True, iphone_panel=True)
        helpers.set_config(deny={"reminders": [self.ua], "room": [self.ua], "iphonepanel": [self.ua]})
        try:
            for uid, want in ((self.ua, False), (self.ub, True)):
                profiles.save_settings(uid, {"app_room": True})
                hello = iphone.app_hello(prof=profiles.by_id(uid))
                self.assertIs(hello["reminders"], want, uid)
                self.assertIs(hello["rooms"], want, uid)
                self.assertIs(hello["panel"], want, uid)
                self.assertIs(iphone.area_on(uid, "app_mine"), want, uid)
        finally:
            helpers.set_config(iphone=False, room=False, iphone_panel=False)


class Background(Base):
    def test_von_selbst(self):
        helpers.set_config(proactive=True)
        try:
            self.block("proactive")
            self.assertEqual(proactive.blocked(self.ua, "greet", proactive.prefs(self.ua), NOON, {}), "blocked by the admin")
            self.assertNotEqual(proactive.blocked(self.ub, "greet", proactive.prefs(self.ub), NOON, {}), "blocked by the admin")
            self.assertEqual(self.a.get("/api/proactive").status_code, 403)
            self.assertEqual(self.b.get("/api/proactive").status_code, 200)
            self.assertIs(self.a.get("/api/proactive/status").json()["enabled"], False)
            self.assertIs(self.b.get("/api/proactive/status").json()["enabled"], True)
            # a part of it: reminders blocked, Von selbst itself not
            self.block("reminders")
            self.assertIs(self.a.get("/api/proactive/status").json()["has"]["reminders"], False)
            self.assertIs(self.b.get("/api/proactive/status").json()["has"]["reminders"], True)
        finally:
            helpers.set_config(proactive=False)

    def test_agent(self):
        helpers.set_config(agent=True, search=True, search_url="http://127.0.0.1:9")
        try:
            r = ADMIN.put("/api/admin/agent/levels", json={"levels": {self.ua: "act", self.ub: "act"}})
            self.assertEqual(r.status_code, 200, r.text)
            self.block("reminders", "search")
            self.assertNotIn("reminder_list", agent.job_tools(self.ua, True)[0])
            self.assertNotIn("web_search", agent.job_tools(self.ua, True)[0])
            self.assertIn("reminder_list", agent.job_tools(self.ub, True)[0])
            self.assertIn("web_search", agent.job_tools(self.ub, True)[0])
            self.block("agent")
            self.assertEqual(agent.level(self.ua), "")
            self.assertEqual(agent.level(self.ub), "act")
            self.assertIs(self.a.get("/api/whoami").json()["agent"], False)
            self.assertIs(self.b.get("/api/whoami").json()["agent"], True)
        finally:
            ADMIN.put("/api/admin/agent/levels", json={"levels": {}})
            helpers.set_config(agent=False, search=False, search_url="")

    def test_home_assistant_live(self):
        helpers.set_config(proactive=True, ha_live=True)
        try:
            self.block("halive")
            with mock.patch("homeassistant.get", return_value={"url": "http://ha.example"}), \
                    mock.patch.object(hamelden, "_entities", return_value=["light.flur"]):
                self.assertFalse(hamelden.live_wanted(self.ua))
                self.assertTrue(hamelden.live_wanted(self.ub))
            self.assertFalse(hamelden.status(self.ua)["allowed"])
            self.assertTrue(hamelden.status(self.ub)["allowed"])
        finally:
            helpers.set_config(proactive=False, ha_live=False)

    def test_remarkable_plus(self):
        helpers.set_config(documents=True, doc_pictures=True, remarkable=True, remarkable_send=True, remarkable_plus=True)
        try:
            self.block("remarkable")      # a function it builds on: every part goes with it
            with mock.patch.object(remarkable, "load", return_value={"token": "x"}):
                for k in rmplus.PARTS:
                    self.assertFalse(rmplus.on(k, self.ua), k)
                    self.assertTrue(rmplus.on(k, self.ub), k)
        finally:
            helpers.set_config(doc_pictures=False, remarkable=False, remarkable_send=False, remarkable_plus=False)

    def test_telegram(self):
        helpers.set_config(telegram=True)
        try:
            self.block("telegram")
            with mock.patch.object(telegram, "token", return_value="1:x"), \
                    mock.patch.object(telegram, "link", return_value={"chat": 5}):
                for uid in (self.ua, self.ub):
                    profiles.save_settings(uid, {"tg_push": True})
                self.assertFalse(telegram.push_on(self.ua))
                self.assertTrue(telegram.push_on(self.ub))
                sent = []

                async def call(c, method, **kw):
                    sent.append(kw.get("text", ""))
                with mock.patch.object(telegram, "call", new=call), \
                        mock.patch.object(telegram, "owner", return_value=self.ua):
                    asyncio.run(telegram.handle(None, {"message": {"chat": {"id": 5, "type": "private"}, "text": "Wie wird das Wetter?"}}))
                self.assertEqual(len(sent), 1)
                self.assertIn("gesperrt", sent[0])
            self.assertFalse(self.a.get("/api/profile/telegram").json()["enabled"])
        finally:
            helpers.set_config(telegram=False)


class SecondStep(Base):
    def test_the_second_step_is_never_blocked(self):
        """A profile must always be able to set up its second step: mfa is not blockable anywhere."""
        import admin
        self.assertIn("mfa", features.NO_BLOCK)
        r = ADMIN.put(f"/api/admin/features/mfa/profiles/{self.ua}", json={"on": False})
        self.assertEqual(r.status_code, 400)
        self.assertIn("not blockable", r.text)
        self.assertNotIn("mfa", features.clean_deny({"mfa": [self.ua], "weather": [self.ua]}))
        cfg = admin.get_config()
        cfg["chat"]["deny"] = {"mfa": [self.ua]}
        with self.assertRaises(Exception) as e:
            admin.validate(cfg)
        self.assertEqual(getattr(e.exception, "status_code", None), 400)
        helpers.set_config(deny={"mfa": [self.ua]})          # even written into the file by hand: no effect
        self.assertFalse(features.blocked("mfa", self.ua))
        helpers.set_config(deny={})
        row = next(f for f in ADMIN.get("/api/admin/features").json()["features"] if f["key"] == "mfa")
        self.assertIs(row["blockable"], False)
        self.assertTrue(all(f["blockable"] for f in ADMIN.get("/api/admin/features").json()["features"] if f["key"] != "mfa"))


class OwnData(Base):
    """Blocked: own data can still be seen and deleted; adding, connecting and acting are refused."""

    def test_weather_place(self):
        helpers.set_config(weather=True)
        try:
            self.block("weather")
            import weather
            with open(weather._file(self.ua), "w") as f:
                json.dump({"lat": 52.5, "lon": 13.4, "name": "Berlin"}, f)
            self.assertEqual(self.a.put("/api/profile/weather", json={"place": "Hamburg"}).status_code, 403)
            self.assertEqual(self.a.get("/api/profile/weather").status_code, 200)
            self.assertEqual(self.a.delete("/api/profile/weather").status_code, 200)
            self.assertFalse(os.path.exists(weather._file(self.ua)))
        finally:
            helpers.set_config(weather=False)

    def test_iphone_pairing(self):
        helpers.set_config(iphone=True)
        try:
            self.block("iphone")
            profiles.add_device("SpAnna iPhone", self.ua, scope="app")
            did = iphone.phones(self.ua)[0]["id"]
            self.assertEqual(self.a.post("/api/profile/iphone/pair", json={"base": "https://spark.example"}).status_code, 403)
            self.assertEqual(self.a.get("/api/profile/iphone").status_code, 200)
            self.assertEqual(self.a.delete(f"/api/profile/iphone/{did}").status_code, 200)
            self.assertEqual(iphone.phones(self.ua), [])
        finally:
            helpers.set_config(iphone=False)

    def test_task_lists(self):
        helpers.set_config(tasks=True)
        try:
            self.block("tasks")
            self.assertEqual(self.a.get("/api/profile/tasks").status_code, 200)    # seen
            self.assertEqual(self.a.post("/api/profile/tasks/einkauf", json={"items": ["Brot"]}).status_code, 403)
        finally:
            helpers.set_config(tasks=False)


# Every features.admin_on call left in the panel (file:function) and why it may stay: it is admin-only, Spark-wide
# (no profile), a module's own Spark switch next to its per-profile check, or a display flag combined with the block.
ADMIN_ON_OK = {
    "verbrauch.py:on": "Spark-wide counter (admin switch); each profile's own view asks features.allowed verbrauch",
    "verbrauch.py:quota_on": "Spark-wide early out; each profile then features.allowed kontingent (verbrauch.limit)",
    "account.py:whoami": "page flags: admin switch and not features.blocked for the profile",
    "account.py:profile_voice": "display flag: admin switch and not features.blocked",
    "account.py:_allow": "display flags: admin switch and not features.blocked",
    "account.py:_locked": "„Daten löschen“ card: only released functions that are features.blocked for the profile",
    "admin.py:glance": "admin overview",
    "agent.py:admin_on": "Spark switch; per profile agent.level (block and granted level)",
    "android.py:admin_on": "Spark switch; per profile features.allowed android / profile_on",
    "android.py:profile_get": "display flag: admin switch and not features.blocked",
    "apns.py:admin_on": "Spark-wide push setup; per profile apns.on_for (features.allowed)",
    "appupdate.py:admin_on": "Spark-wide check and admin page; per profile features.allowed iphoneupdate",
    "nasquelle.py:admin_on": "Spark switch for the round and Live; per profile nasquelle.allowed (features.allowed)",
    "nasquelle.py:haus_on": "Spark switch for reading the Haushaltsordner (no profile); who finds it: nasquelle.haus_find (features.allowed)",
    "nasablage.py:admin_on": "Spark switch for the round, Live and the Dienst-Wächter; per profile nasablage.allowed (features.allowed)",
    "naszustand.py:admin_on": "admin only: the Spark's own NAS, read for the admins; the tool asks features.allowed and an admin profile",
    "naszustand.py:switched": "admin only: the main admin's settings page may set it up before the NAS is stored (READY)",
    "doclingdienst.py:admin_on": "Spark switch for the shared Docling queue and Live; per profile doclingdienst.allowed",
    "begleiter.py:admin_on": "Spark-wide download of the program; per profile begleiter.allowed",
    "berater.py:wanted": "Spark-wide: the Einstellungs-Assistent runs at all",
    "berater.py:candidates": "Spark-wide proposals (admin)",
    "berater.py:replay_model": "Spark-wide analysis (admin)",
    "berater.py:english_form": "Spark-wide analysis (admin)",
    "berater.py:analyse": "Spark-wide analysis (admin)",
    "berater.py:pick": "Spark-wide proposals (admin)",
    "berater.py:idea": "Spark-wide proposals (admin)",
    "berater.py:idea_wish": "Spark-wide proposals (admin)",
    "berater.py:propose": "Spark-wide proposals (admin)",
    "berater.py:to_issue": "Spark-wide report (admin)",
    "berater.py:nachkontrolle": "Spark-wide follow-up (admin)",
    "berater.py:_notify": "Spark-wide early out; each admin profile then features.allowed beraterhinweis",
    "berater.py:_autopilot": "Spark-wide autopilot (admin)",
    "berater.py:_tell_admins": "Spark-wide early out; each admin profile then features.allowed beraterhinweis",
    "berater.py:explain_area": "admin page",
    "berater.py:overview": "admin page",
    "berater.py:admin_act": "admin endpoint",
    "berater.py:admin_case": "admin endpoint",
    "berater.py:admin_explain": "admin endpoint",
    "berater.py:admin_explain_area": "admin endpoint",
    "chats.py:admin_on": "Spark switch; per profile chats.usable (features.allowed)",
    "chats.py:groups_on": "Spark switch of a chat kind; members checked with chats.usable",
    "chats.py:invite_on": "Spark switch; the inviting profile checked with chats.usable",
    "chats.py:media_on": "Spark switch; the sender checked with chats.usable",
    "chatsec.py:admin_on": "Spark switch; per profile chatsec.usable (features.allowed)",
    "contacts.py:admin_on": "Spark switch; per profile contacts.usable, endpoints add features.blocked",
    "core.py:_gate": "setup endpoints: admin switch, then features.blocked for the profile",
    "dienstwacht.py:admin_on": "Spark-wide service watch",
    "wartung.py:admin_on": "Spark-wide maintenance pause, only admins start it",
    "wartung.py:auto_on": "Spark-wide: the panel pauses a restarting part by itself, no profile involved",
    "modellseite.py:_an": "Spark-wide model switch, admin-only endpoints (Zustand → Modelle), no profile involved",
    "modellseite.py:_eigen_an": "Spark-wide own models, admin-only endpoints (Zustand → Modelle), no profile involved",
    "dienstwacht.py:active": "Spark-wide: which services are watched",
    "dienstwacht.py:_affected": "Spark-wide: which functions a gone service touches",
    "docmake.py:admin_on": "Spark switch for Live; per profile features.allowed erstellen",
    "bilder.py:admin_on": "Spark switch for Live; per profile features.allowed bilder",
    "esp32.py:admin_on": "Spark switch (firmware, OTA without a profile); per profile profile_on / allowed",
    "esp32.py:profile_get": "display flag next to the profile's own state",
    "esp32.py:profile_speaker_code": "endpoint: admin switch, then features.blocked",
    "faelle.py:wanted": "Spark-wide: turns are summed up at all",
    "gedaechtnis.py:for_live": "Spark-wide numbers for Live; each profile then features.allowed gedpruefen",
    "gedaechtnis.py:topics_once": "Spark-wide early out; each profile then topics_on (features.allowed)",
    "geraeteupdate.py:admin_on": "Spark-wide version checks; notes per profile features.allowed",
    "geraeteupdate.py:night_on": "Spark-wide night round; each speaker features.allowed geraetenacht",
    "geraeteupdate.py:upstream_on": "Spark-wide check of XiaoZhi",
    "geraeteupdate.py:kept": "Spark-wide: versions the Spark keeps",
    "geraeteupdate.py:speakers": "device list (admin overview, or the profile's own devices)",
    "geraeteupdate.py:_desks": "device list (admin overview, or the profile's own devices)",
    "geraeteupdate.py:_watches": "device list (admin overview, or the profile's own devices)",
    "geraeteupdate.py:check_all": "Spark-wide version checks",
    "geraeteupdate.py:night_step": "Spark-wide early out; each speaker features.allowed esp32 and geraetenacht",
    "hamelden.py:status": "display flag: admin switch and not features.blocked",
    "hamelden.py:api_events_get": "display flag: admin switch and not features.blocked",
    "hilfe.py:visible": "which guides exist on this Spark (no profile)",
    "hilfe.py:state_line": "the Spark switch shown to admins next to the profile's own reason",
    "hilfe.py:answer_text": "Spark switch named for admins; the block is told the profile right after",
    "hilfe.py:build_card.add": "Spark switches on an admin's card; the profile's block is checked before",
    "hintergrund.py:admin_state": "admin page",
    "images.py:admin_on": "Spark switch; per profile images.allowed (features.allowed)",
    "iphone.py:admin_on": "Spark switch (pairing); per profile iphone.allowed, endpoints add features.blocked",
    "join.py:mfa_due": "the second step is a protection, never released or blocked per profile",
    "join.py:admin_get": "admin page",
    "join.py:admin_invite": "admin endpoint (invitation before the profile exists)",
    "join.py:join_check": "invitation before the profile exists",
    "join.py:app_join": "invitation before the profile exists",
    "kiwix.py:admin_on": "Spark switch; per profile kiwix.usable (features.allowed)",
    "live.py:unset": "admin's Live overview",
    "live.py:snapshot": "admin's Live overview",
    "logfilter.py:logfilter": "admin's log page",
    "lokal.py:admin_on": "Spark switch; per profile lokal.on (features.allowed)",
    "mcpserver.py:admin_on": "Spark switch; per profile and connection features.allowed mcpserver",
    "mcpserver.py:extern_on": "Spark-wide: the server reachable from outside",
    "mcpserver.py:act_on": "Spark switch; each call checks features.allowed for the profile",
    "meinmcp.py:admin_on": "Spark switch; per profile features.allowed mymcp",
    "meldung.py:admin_on": "Spark switch; per profile features.allowed melden (meldung.caller)",
    "messages.py:admin_on": "Spark switch; per profile messages.usable (features.allowed)",
    "messages.py:all_on": "Spark switch; per profile messages.takes_all (features.allowed)",
    "messages.py:announce_on": "Spark switch; per profile features.allowed messages_announce",
    "nachsortieren.py:admin_on": "Spark switch for the shared reranker model (load and idle stop); per profile "
                                 "features.allowed nachsortieren",
    "nas.py:admin_on": "Spark switch for Live and reading own connections; acting per profile features.allowed nas",
    "onboard.py:_shown": "Spark switch; the block is checked in onboard.items",
    "parcels.py:admin_on": "Spark switch; per profile parcels.usable (features.allowed)",
    "pebblewatch.py:admin_on": "Spark switch; per profile pebblewatch.allowed, endpoints add features.blocked",
    "proactive.py:enabled": "Spark switch; per profile proactive.blocked (features.blocked) and features.allowed",
    "quality.py:judge": "admin's quality test",
    "remarkable.py:due_once": "Spark-wide early out; each profile then features.allowed remarkable",
    "remarkable.py:public": "display: the paper part only when the Spark has it; it reports features.allowed itself",
    "rmaufgaben.py:public": "display of the Spark switch next to features.allowed",
    "rmpapier.py:public": "display of the Spark switches next to features.allowed",
    "rmplus.py:guide_text": "lists what the Spark offers, each with features.allowed for the profile",
    "rmplus.py:due_once": "Spark-wide early out; each profile then features.allowed remarkable and rmplus.on",
    "rmplus.py:public": "display of the Spark switches next to features.allowed",
    "roles.py:admin_on": "Spark switch; per profile roles.on (features.allowed)",
    "room.py:enabled": "Spark switch; per profile features.allowed room",
    "roomfar.py:admin_on": "Spark switch; per profile roomfar.profile_on (block included)",
    "roomlive.py:enabled": "Spark switch; per profile through room.py and esp32.py",
    "roomlive.py:ha_on": "Spark switch; per profile roomlive._gate (features.allowed roomha)",
    "schreib.py:admin_on": "Spark switch; per profile features.allowed schreib",
    "schreib.py:write_info": "display of the Spark switch next to the profile's own flags",
    "schreib.py:office_file": "Spark-wide static file of the Office add-in",
    "speicher.py:admin_on": "Spark switch; per profile features.allowed speicher",
    "speicher.py:offload_ok": "Spark-wide option",
    "speicher.py:lan_ok": "Spark-wide option",
    "speicher.py:folder_ok": "Spark-wide option",
    "stufe.py:on": "Spark switch; per profile stufe.level checks features.blocked",
    "suchpruefung.py:admin_on": "Spark switch for the background step, Live and the admin page; per profile suchpruefung.allowed",
    "tasks.py:admin_on": "Spark switch; per profile features.allowed tasks, endpoints add features.blocked",
    "telegram.py:admin_on": "Spark-wide bot; per profile features.allowed / features.blocked",
    "tidy.py:admin_on": "Spark switch; per profile features.allowed tidy",
    "tipps.py:<module>": "tip about the second step: a protection, never blocked per profile",
    "tracelog.py:traces": "admin's request log",
    "transit.py:admin_on": "Spark switch; per profile transit.usable, endpoints add features.blocked",
    "verbund.py:admin_on": "Spark switch; per profile verbund.usable (features.allowed)",
    "verbund.py:media_on": "Spark switch: whether this Spark takes files from other Sparks at all; per profile verbund.media_ok (features.allowed)",
    "anrufe.py:admin_on": "Spark switch; per profile anrufe.usable (features.allowed)",
    "verbundgruppe.py:admin_on": "Spark switch: whether this Spark takes group requests of other Sparks at all; per profile verbundgruppe.usable (features.allowed)",
    "anrufe.py:turn_on": "Spark-wide: the Vermittler (coturn) runs for the whole Spark, no profile",
    "vorab.py:admin_on": "Spark switch; per profile vorab.on (features.allowed)",
    "weather.py:admin_on": "Spark switch; per profile weather.usable, endpoints add features.blocked",
    "wiki.py:admin_on": "Spark switch; per profile features.allowed wiki",
    "wissen.py:admin_on": "Spark switch; per profile wissen.on (features.allowed)",
}


def admin_on_calls():
    """{"file.py:function": [lines]} of every features.admin_on call in the panel outside features.py."""
    out = {}
    for path in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
        name = os.path.basename(path)
        if name == "features.py":
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        def walk(node, where):
            for ch in ast.iter_child_nodes(node):
                here = where
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    here = (where + "." if where else "") + ch.name
                if isinstance(ch, ast.Call) and isinstance(ch.func, ast.Attribute) and ch.func.attr == "admin_on" \
                        and isinstance(ch.func.value, ast.Name) and ch.func.value.id == "features":
                    out.setdefault(f"{name}:{where or '<module>'}", []).append(ch.lineno)
                walk(ch, here)
        walk(tree, "")
    return out


class Guard(unittest.TestCase):
    def test_no_module_gates_a_profile_with_admin_on_alone(self):
        """A new place that acts for a profile must ask features.allowed (switch, chain, block, preference, second
        step). features.admin_on stays only where this list says why; add a line with the reason, or use allowed."""
        found = admin_on_calls()
        new = {k: v for k, v in found.items() if k not in ADMIN_ON_OK}
        self.assertEqual(new, {}, "features.admin_on outside the list: use features.allowed(key, uid), or add the "
                                  "place to ADMIN_ON_OK with its reason (admin-only or Spark-wide)")
        self.assertEqual(sorted(set(ADMIN_ON_OK) - set(found)), [], "entries without a call any more: remove them")
        for k, why in ADMIN_ON_OK.items():
            self.assertTrue(why.strip(), k)


if __name__ == "__main__":
    unittest.main()
