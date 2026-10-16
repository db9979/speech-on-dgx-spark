"""Dienst-Wächter (dienstwacht.py, plan plaene/dienst-ausfall-melden.md).

Off without the admin's switch; a service counts as gone only after three failed probes over three minutes and
as back after two good ones; one note per outage and admin, at most one per service in half an hour (wobbling is
counted and told once), the internet's outage is one note naming what is behind it; notes only to admin profiles
with their own switch, on the device they chose, collected at night, kept when they did not get out; fixed words
only (no address, no error text); the probes send no login and do not show on the Wächter list; the banner, Live
and Zustand show fixed words; the assistant says a missing service at once only with both switches.
No test depends on the wall clock: times are passed in.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import json
import os
import time
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat_tools  # noqa: E402
import dienstwacht as dw  # noqa: E402
import guard  # noqa: E402
import health  # noqa: E402
import live  # noqa: E402
import netguard  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402

REAL_PROBE = dw.probe
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def run(coro):
    return asyncio.run(coro)


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in profiles.names() if u["name"] == name)


def local(h, m, day=12):
    """A unix time at h:m Spark-local time on 2026-10-<day>."""
    return time.mktime((2026, 10, day, h, m, 0, 0, 0, -1))


class Base(unittest.TestCase):
    SERVICES = ("inet", "kiwix", "ha", "mail")

    def hint(self, uid, on):
        r = ADMIN.put(f"/api/admin/features/dienstnutzer/profiles/{uid}", json={"on": on})
        self.assertEqual(r.status_code, 200, r.text)

    def setUp(self):
        helpers.set_config(svc_watch=True, svc_watch_users=True)
        dw.reset()
        for k in [k for k in guard._rate if k[0] in ("svcwatch", "svcwatchnow")]:
            guard._rate.pop(k, None)
        self.anna_c, self.ben_c = profile("Anjuli"), profile("Bentje")
        self.anna, self.ben = uid_of("Anjuli"), uid_of("Bentje")
        profiles.save_settings(self.anna, {"svc_note": True, "svc_night": False, "svc_device": ""})
        profiles.save_settings(self.ben, {"svc_note": True})
        self.hint(self.ben, False)        # the admin blocked "Hinweis, wenn ein Dienst fehlt" for Bentje
        self.addCleanup(self.hint, self.ben, True)
        self.sent, self.reached = [], True
        self.up = {s: True for s in self.SERVICES}          # what the fake probes answer
        self.public = {"inet": True, "kiwix": False, "ha": False, "mail": True}

        async def send(uid, title, body, tag="", private=True, why="", to=""):
            self.sent.append({"uid": uid, "title": title, "body": body, "tag": tag, "to": to, "private": private})
            return 1 if self.reached else 0

        async def probe(sid, key, p, cfg):
            return dw.Probe(self.up.get(sid, True))

        acts = {s: {"p1": {"url": f"https://{s}.example/", "level": netguard.HOME}} for s in self.SERVICES}
        acts["mail"] = {"m1": {"host": "mail.example", "port": 993, "uids": [self.anna]}}
        self.patches = [mock.patch.object(push, "send", send), mock.patch.object(push, "reachable", lambda uid, private=True: True),
                        mock.patch.object(dw, "probe", probe),
                        mock.patch.object(dw, "_is_public", lambda host: next((v for s, v in self.public.items() if host.startswith(s)), False)),
                        mock.patch.object(dw, "_paused", lambda now: False),
                        mock.patch.object(notaus, "admin_uids", lambda: [self.anna, self.ben]),
                        mock.patch.object(dw, "active", lambda c=None, cfg=None: {k: v for k, v in acts.items() if k not in dw._read()["skip"]})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        dw.reset()
        # off again: else the panel's own loop goes on looking at the services of later tests (Live test unfolded "mail")
        helpers.set_config(svc_watch=False, svc_watch_users=False)

    def rounds(self, t0, minutes, step=1):
        """One round per minute (everything due), from t0 for so many minutes; returns the last time."""
        t = t0
        for i in range(0, minutes, step):
            t = t0 + i * 60
            dw._due.clear()
            run(dw.round_once(t))
        return t


class Off(Base):
    def test_nothing_without_the_admin_switch(self):
        helpers.set_config(svc_watch=False)
        self.up["kiwix"] = False
        self.rounds(local(10, 0), 10)
        self.assertEqual(self.sent, [])
        self.assertEqual(dw.alerts(), [])
        self.assertEqual(dw._read()["svc"], {})
        self.assertFalse(dw.overview()["on"])

    def test_off_by_default_everywhere(self):
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            chat = json.load(f)["chat"]
        self.assertIs(chat["svc_watch"], False)
        self.assertIs(chat["svc_watch_users"], False)
        self.assertIs(profiles.SETTINGS["svc_night"][0], False)
        self.assertIs(profiles.SETTINGS["svc_note"][0], True)    # a preference, on unless switched off (admins only)
        self.assertNotIn("svc_hint", profiles.SETTINGS)          # no profile switch: the admin's release counts
        self.assertEqual(profiles.SETTINGS["svc_device"][0], "")


class Flood(Base):
    def test_a_short_wobble_stays_quiet(self):
        t0 = local(10, 0)
        self.up["kiwix"] = False
        self.rounds(t0, 2)                       # two failed probes: not yet gone
        self.up["kiwix"] = True
        self.rounds(t0 + 120, 3)
        self.assertEqual(self.sent, [])
        self.assertEqual(dw._read()["log"], [])
        self.assertEqual(dw._read()["svc"]["kiwix"]["st"], "ok")

    def test_gone_after_three_probes_and_three_minutes_back_after_two(self):
        t0 = local(10, 0)
        self.up["kiwix"] = False
        self.rounds(t0, 3)                       # 10:00, 10:01, 10:02: three probes but only two minutes
        self.assertEqual(self.sent, [])
        self.rounds(t0 + 180, 1)                 # 10:03: three minutes since the first failure
        self.assertEqual(len(self.sent), 2)      # Anjuli and Bentje, one note each
        n = self.sent[0]
        self.assertIn("Archiv (Kiwix) nicht erreichbar", n["title"])
        self.assertIn("antwortet seit 10:00 nicht", n["body"])
        self.assertIn("Fragen ans Archiv gehen gerade nicht", n["body"])
        self.assertEqual((n["tag"], n["private"]), ("svc", False))
        self.assertNotIn("example", n["title"] + n["body"])      # never an address
        self.assertEqual(dw._read()["svc"]["kiwix"]["st"], "down")
        self.sent.clear()
        self.rounds(t0 + 240, 5)                 # still gone: nothing more
        self.assertEqual(self.sent, [])
        self.up["kiwix"] = True
        self.rounds(t0 + 540, 1)                 # one good probe: not back yet
        self.assertEqual(self.sent, [])
        self.rounds(t0 + 600, 1)                 # two good ones: back
        self.assertEqual(len(self.sent), 2)
        self.assertIn("Wieder da: Archiv (Kiwix)", self.sent[0]["title"])
        self.assertIn("war 10 min weg", self.sent[0]["body"])
        self.assertIn("Alles läuft wieder", self.sent[0]["body"])
        log = dw._read()["log"]
        self.assertEqual(len(log), 1)
        self.assertEqual((log[0]["s"], log[0]["a"], log[0]["b"]), ("kiwix", int(t0), int(t0 + 600)))

    def test_flapping_is_one_note_per_half_hour_with_the_count(self):
        t0 = local(10, 0)
        for start in (0, 10, 20):                 # gone 4 min, back, gone again ... every 10 minutes
            self.up["kiwix"] = False
            self.rounds(t0 + start * 60, 4)
            self.up["kiwix"] = True
            self.rounds(t0 + (start + 4) * 60, 6)
        downs = [n for n in self.sent if n["uid"] == self.anna and "nicht erreichbar" in n["title"]]
        ups = [n for n in self.sent if n["uid"] == self.anna and "Wieder da" in n["title"]]
        self.assertEqual((len(downs), len(ups)), (1, 1))      # only the first outage was told
        self.sent.clear()
        self.up["kiwix"] = False
        self.rounds(t0 + 30 * 60, 6)              # gone again when the half hour is over: one note with the count
        downs = [n for n in self.sent if n["uid"] == self.anna]
        self.assertEqual(len(downs), 1, self.sent)
        self.assertIn("Wackelt: 3 Ausfälle", downs[0]["body"])

    def test_internet_is_one_note_with_what_is_behind_it(self):
        t0 = local(6, 0)
        self.up.update(inet=False, mail=False)    # the mail server is on the internet: no note of its own
        self.rounds(t0, 4)
        mine = [n for n in self.sent if n["uid"] == self.anna]
        self.assertEqual(len(mine), 1, self.sent)
        self.assertEqual(mine[0]["title"], "⚠️ Internet weg")
        self.assertIn("Internet weg seit 06:00", mine[0]["body"])
        self.assertIn("Betroffen: Mail", mine[0]["body"])
        self.assertIn("Das Heimnetz läuft weiter", mine[0]["body"])
        self.assertEqual(dw._read()["svc"]["mail"]["st"], "inet")
        self.assertEqual([a["text"][:30] for a in dw.alerts()], ["Gerade eingeschränkt: Internet"])
        self.sent.clear()
        self.up["kiwix"] = False                  # a home service gone too: a note of its own
        self.rounds(t0 + 240, 4)
        self.assertIn("Archiv (Kiwix) nicht erreichbar", self.sent[0]["title"])
        self.sent.clear()
        self.up.update(inet=True, mail=True, kiwix=True)
        self.rounds(t0 + 480, 2)                  # both back in the same round: one note per admin
        mine = [n for n in self.sent if n["uid"] == self.anna]
        self.assertEqual(len(mine), 1, self.sent)
        self.assertEqual(mine[0]["title"], "✅ Wieder da: Internet, Archiv (Kiwix)")
        self.assertEqual(dw._read()["svc"]["mail"]["st"], "ok")
        self.assertEqual([x["s"] for x in dw._read()["log"]], ["inet", "kiwix"])   # mail had no outage of its own

    def test_still_gone_behind_the_internet_gets_its_own_note_after_it(self):
        t0 = local(6, 0)
        self.up.update(inet=False, mail=False)
        self.rounds(t0, 4)
        self.sent.clear()
        self.up["inet"] = True
        self.rounds(t0 + 240, 3)
        mine = [n for n in self.sent if n["uid"] == self.anna]
        self.assertEqual(len(mine), 2, mine)      # internet back; then mail, still gone, its own note
        self.assertIn("Wieder da: Internet", mine[0]["title"])
        self.assertIn("Mail nicht erreichbar", mine[1]["title"])

    def test_nothing_while_paused_or_in_the_notaus(self):
        t0 = local(10, 0)
        self.up["kiwix"] = False
        with mock.patch.object(dw, "_paused", lambda now: True):
            self.rounds(t0, 6)
        self.assertEqual(self.sent, [])
        with mock.patch.object(notaus, "blocks", lambda kind, uid=None: kind == "auto"):
            self.rounds(t0 + 360, 6)
        self.assertEqual(self.sent, [])
        self.assertNotIn("kiwix", dw._read()["svc"])

    def test_notaus_stage_one_does_not_count_as_internet_gone(self):
        self.up["inet"] = False
        with mock.patch.object(notaus, "level", lambda: 1):
            self.rounds(local(10, 0), 6)
        self.assertEqual(self.sent, [])
        self.assertEqual(dw._read()["svc"]["inet"]["st"], "held")

    def test_a_restart_by_the_watchdog_is_no_outage(self):
        acts = {"asr": {"own": {"name": "asr"}}}
        t0 = local(10, 0)
        self.up["asr"] = False
        with mock.patch.object(dw, "active", lambda c=None, cfg=None: acts), \
                mock.patch.object(health, "events", [{"t": t0 + 30, "unit": "ASR", "reason": "hängt", "done": True}]):
            self.rounds(t0, 5)
        self.assertEqual(self.sent, [])


class Who(Base):
    def gone(self, t0=None):
        t0 = t0 or local(10, 0)
        self.up["kiwix"] = False
        self.rounds(t0, 4)
        return t0

    def test_only_admin_profiles_with_their_own_switch(self):
        profiles.save_settings(self.ben, {"svc_note": False})
        profile("Carl")                    # no admin: never, also with the switch
        carl = uid_of("Carl")
        profiles.save_settings(carl, {"svc_note": True})
        self.gone()
        self.assertEqual({n["uid"] for n in self.sent}, {self.anna})

    def test_the_chosen_device(self):
        profiles.save_settings(self.anna, {"svc_device": "tg"})
        self.gone()
        self.assertEqual({n["uid"]: n["to"] for n in self.sent}, {self.anna: "tg", self.ben: ""})
        r = self.anna_c.put("/api/profile/settings", json={"svc_device": "fax"})
        self.assertNotEqual(profiles.settings(self.anna).get("svc_device"), "fax", r.text)

    def test_push_to_the_chosen_way_and_to_all(self):
        uid = self.anna
        with mock.patch.object(push, "_have", lambda u, p: {"app": True, "and": False, "desk": True, "tg": True, "web": False}), \
                mock.patch.dict(profiles.LAST_USED, {uid: ("app", "", time.time())}):
            self.assertEqual(push.pick(uid)[0], "app")
            self.assertEqual(push.pick(uid, to="tg")[0], "tg")
            self.assertEqual(push.pick(uid, to="and")[0], "app")     # not set up: as usual
        self.patches[0].stop()
        try:
            got = []

            async def one(u, kind, targets, title, body, tag, private, why):
                got.append(kind)
                return 1
            with mock.patch.object(push, "_have", lambda u, p: {"app": True, "and": False, "desk": True, "tg": True, "web": False}), \
                    mock.patch.object(push, "_send_one", one):
                self.assertEqual(run(push.send(uid, "T", "B", tag="svc", private=False, to="all")), 3)
            self.assertEqual(got, ["app", "desk", "tg"])
        finally:
            self.patches[0].start()

    def test_night_collects_and_gives_one_summary_at_seven(self):
        profiles.save_settings(self.anna, {"svc_night": True})
        t0 = local(2, 0)
        self.gone(t0)
        self.up["kiwix"] = True
        self.rounds(t0 + 1800, 3)
        self.assertEqual([n["uid"] for n in self.sent], [self.ben, self.ben])   # Bentje is told at once, Anjuli not
        self.sent.clear()
        self.rounds(local(6, 58), 1)
        self.assertEqual(self.sent, [])
        self.rounds(local(7, 0), 1)
        self.assertEqual(len(self.sent), 1)
        n = self.sent[0]
        self.assertEqual(n["uid"], self.anna)
        self.assertTrue(n["title"].startswith("🌙 Heute Nacht"), n["title"])
        self.assertIn("Archiv (Kiwix) war von 02:00 bis 02:31 weg", n["body"])

    def test_a_note_that_did_not_get_out_follows_with_the_times(self):
        self.reached = False
        t0 = self.gone()
        self.assertEqual(len(self.sent), 2)
        self.sent.clear()
        self.rounds(t0 + 240, 2)                   # tried again only after RETRY_GAP
        self.assertEqual(self.sent, [])
        self.up["kiwix"] = True
        self.reached = True
        self.rounds(t0 + 360, 2)                   # back: the waiting note goes with it, one for both
        mine = [n for n in self.sent if n["uid"] == self.anna]
        self.assertEqual(len(mine), 1, self.sent)
        self.assertEqual(mine[0]["title"], "✅ Wieder da: Archiv (Kiwix)")
        self.assertIn("war von 10:00 bis 10:07 weg", mine[0]["body"])
        self.assertEqual(dw._read()["queue"], {})


class Probes(Base):
    def test_probes_send_no_login_and_stay_off_the_waechter_list(self):
        for p in self.patches:
            p.stop()
        self.patches = []
        with open(profiles._path(self.anna, "homeassistant.json"), "w") as f:
            json.dump({"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": "sealed-token-never-sent"}, f)
        try:
            acts = dw.active()
            self.assertIn("ha", acts)
            part = next(iter(acts["ha"].values()))
            self.assertNotIn("token", json.dumps(part).lower())
            self.assertEqual(part["url"], f"http://127.0.0.1:{helpers.HA_PORT}{dw.HA_PATH}")
            before = list(live._guard)
            calls = len(helpers.HA_CALLS)
            unauth = len(helpers.HA_UNAUTH)
            with mock.patch.object(live, "on", lambda: True):   # the Live page is on: a request would be listed
                r = run(REAL_PROBE("ha", "x", part, {}))
            self.assertTrue(r.ok)
            self.assertEqual(helpers.HA_UNAUTH[unauth:], [])   # no failed login in Home Assistant's log (ban.py)
            self.assertEqual(list(live._guard), before, [x["to"] for x in live._guard])   # no line on the Wächter list
            for c in helpers.HA_CALLS[calls:]:
                self.assertNotIn("sealed-token", json.dumps(c))
            bad = run(REAL_PROBE("kiwix", "x", {"url": "http://127.0.0.1:9/", "level": netguard.HOME}, {}))
            self.assertFalse(bad.ok)
            self.assertEqual(bad.why, "")
        finally:
            os.remove(profiles._path(self.anna, "homeassistant.json"))

    def test_the_spark_s_own_ports_stay_refused_for_outside_probes(self):
        r = run(REAL_PROBE("kiwix", "x", {"url": "http://127.0.0.1:31080/", "level": netguard.HOME}, {}))
        self.assertEqual((r.ok, r.why), (False, "blocked"))

    def test_the_admin_takes_a_service_off_the_list(self):
        r = ADMIN.put("/api/admin/svcwatch/kiwix", json={"on": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.up["kiwix"] = False
        self.rounds(local(10, 0), 5)
        self.assertEqual(self.sent, [])
        row = next(x for x in ADMIN.get("/api/admin/svcwatch").json()["services"] if x["id"] == "kiwix")
        self.assertFalse(row["watched"])
        self.assertEqual(ADMIN.put("/api/admin/svcwatch/nope", json={"on": False}).status_code, 404)
        self.assertEqual(ADMIN.put("/api/admin/svcwatch/kiwix", json={"on": "ja"}).status_code, 400)
        self.assertEqual(ADMIN.put("/api/admin/svcwatch/kiwix", content=b"x" * 100).status_code, 413)

    def test_admin_only(self):
        for c in (TestClient(panel.app), self.ben_c):
            self.assertIn(c.get("/api/admin/svcwatch").status_code, (401, 403))
            self.assertIn(c.post("/api/admin/svcwatch/check").status_code, (401, 403))
            self.assertIn(c.put("/api/admin/svcwatch/kiwix", json={"on": False}).status_code, (401, 403))

    def test_check_now_is_rate_limited(self):
        codes = [ADMIN.post("/api/admin/svcwatch/check").status_code for _ in range(6)]
        self.assertEqual(codes[0], 200)
        self.assertIn(429, codes)


class Shown(Base):
    def live_snapshot(self, now):
        # Live page switch sits under "logs" (like test_live.set_logs); put it back afterwards
        path = os.environ["SPEECH_SPARK_CONFIG"]
        with open(path) as f:
            c = json.load(f)
        old = dict(c.get("logs", {}))
        c.setdefault("logs", {})["live"] = True
        helpers.write_config(c)
        try:
            return live.snapshot("admin", now)
        finally:
            with open(path) as f:
                c = json.load(f)
            c["logs"] = old
            helpers.write_config(c)

    def test_banner_live_and_zustand_in_fixed_words(self):
        t0 = local(10, 0)
        self.up["kiwix"] = False
        self.rounds(t0, 4)
        a = dw.alerts()
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["kind"], "service")
        self.assertIn("Gerade eingeschränkt: Archiv (Kiwix) antwortet seit 10:00 nicht.", a[0]["text"])
        self.assertIn(a[0], health.alerts())
        svc, hints = dw.for_live(t0 + 200)
        self.assertEqual(svc["kiwix"]["st"], "down")
        self.assertEqual(svc["inet"]["st"], "ok")
        self.assertEqual(hints, [{"at": "kiwix", "level": "bad", "word": "antwortet nicht seit 10:00"}])
        snap = self.live_snapshot(t0 + 200)
        self.assertIn("inet", [x["id"] for x in snap["targets"]])
        self.assertEqual(snap["svc"]["kiwix"]["st"], "down")
        self.assertTrue(any(h["at"] == "kiwix" and h["why"] for h in snap["hints"]))
        self.assertTrue(any(e["area"] == "Dienste" and "Archiv (Kiwix) antwortet nicht" in e["text"] for e in snap["events"]))
        o = ADMIN.get("/api/admin/svcwatch").json()
        row = next(x for x in o["services"] if x["id"] == "kiwix")
        self.assertEqual((row["st"], row["since"]), ("down", t0))
        # "today" counts the outages of the day of now: asked for t0's day, so the test runs on any date
        self.assertEqual(next(x for x in dw.overview(t0 + 200)["services"] if x["id"] == "kiwix")["today"], 1)
        self.assertEqual(o["admins"], 2)
        self.assertNotIn("example", json.dumps(o))
        self.assertNotIn("example", json.dumps(snap))

    def test_live_leaves_out_what_is_not_set_up_or_not_looked_at(self):
        t0 = local(10, 0)
        self.up["kiwix"] = False
        self.rounds(t0, 4)
        self.assertIn("kiwix", dw.for_live(t0 + 200)[0])
        dw._read()["skip"].append("kiwix")           # taken off the list in Zustand → Dienste
        svc, hints = dw.for_live(t0 + 200)
        self.assertNotIn("kiwix", svc)
        self.assertFalse(any(h["at"] == "kiwix" for h in hints))
        dw._read()["skip"].remove("kiwix")
        with mock.patch.object(dw, "active", lambda c=None, cfg=None: {}):   # nothing set up
            self.assertEqual(dw.for_live(t0 + 200), ({}, []))

    def test_every_service_has_its_node_on_the_live_picture(self):
        for sid, v in dw.SVC.items():
            self.assertIn(v[4], live.TARGETS if v[4] not in ("asr", "tts") else ("asr", "tts"), sid)


class Assistant(Base):
    def turn(self, uid):
        t = types.SimpleNamespace(who={"id": uid} if uid else None, ex={"changes": False, "run": {}, "mail": set(), "outside": set()},
                                  locked=lambda st: set())
        return t

    def call(self, name, uid):
        st = {"offered": {name}, "mail": False, "outside": False, "first": True}
        return run(chat_tools.run(self.turn(uid), name, {}, st))

    def test_a_missing_service_is_said_at_once_with_both_switches(self):
        self.up["kiwix"] = False
        self.rounds(local(10, 0), 4)
        out = self.call("archive_search", self.anna)
        self.assertTrue(out.startswith("Not done: the service Archive (Kiwix) is not reachable"), out)
        self.assertIn("Archiv (Kiwix) ist gerade nicht erreichbar (seit 10:00).", out)
        self.assertEqual(dw.tool_down("archive_search", self.ben), "")          # the admin blocked it for Bentje
        self.assertEqual(dw.tool_down("archive_search", ""), "")                # guests never
        helpers.set_config(svc_watch_users=False)
        self.assertEqual(dw.tool_down("archive_search", self.anna), "")
        helpers.set_config(svc_watch_users=True)
        self.assertEqual(dw.tool_down("calendar_events", self.anna), "")        # calendar is fine

    def test_internet_tools_name_the_internet(self):
        self.up["inet"] = False
        self.rounds(local(10, 0), 4)
        out = dw.tool_down("weather", self.anna)
        self.assertIn("Internet ist gerade nicht erreichbar", out)
        self.assertIn("Internet ist gerade nicht erreichbar", dw.tool_down("web_search", self.anna))
        self.assertEqual(dw.tool_down("archive_search", self.anna), "")         # the archive is at home

    def test_only_the_profile_s_own_mail_server(self):
        self.public["mail"] = False               # a mail server at home: not behind the internet
        self.hint(self.ben, True)
        self.up["mail"] = False
        with mock.patch.object(dw, "_mail_parts", lambda: {"m1": {"host": "imap.example", "port": 993, "uids": [self.anna]}}):
            self.rounds(local(10, 0), 4)
            self.assertIn("Mail ist gerade nicht erreichbar", dw.tool_down("mail_list", self.anna))
            self.assertEqual(dw.tool_down("mail_list", self.ben), "")    # Bentje's mail is elsewhere


if __name__ == "__main__":
    unittest.main()
