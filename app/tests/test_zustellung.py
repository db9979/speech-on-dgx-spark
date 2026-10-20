"""Meldung ans gerade genutzte Gerät (zustellung.py, plan benachrichtigung-geraet, Dominik 2026-10-20 "ok", stage 1).

- Off (admin switch chat.note_device): push.pick as before (the device used last), the signal endpoint keeps nothing.
- On: a note goes to the device touched last within zustellung.ACTIVE seconds (page, Android app, iPhone app, Begleiter),
  else to the phone app at once, else as before. A way the profile chose (to=) still wins; a device that said "weg" or
  whose signal is older than FRESH is not in use; a blocked profile goes on as before.
- The signal carries only a number and a state; only pages and the apps may send it, the profile comes from the login.
- Logs: one fixed line per routed note; Live: devices in use and notes routed as numbers.
- Stage 2: a note to a device other than the phone app comes once more to the phone after FOLLOW (urgent: FOLLOW_URGENT)
  unless that device was touched after it or its Vorgang is no longer open; never a third time. Opening a note says
  "gesehen" for its Vorgang; done elsewhere, the devices take it away ("zu", Begleiter and Android no longer fetch it).

No wall clock beyond the signals' own times (all passed as now=), no network.
"""
import contextlib
import io
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import asyncio  # noqa: E402
import apns  # noqa: E402
import android  # noqa: E402
import begleiter  # noqa: E402
import vorgaenge  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
import telegram  # noqa: E402
import zustellung  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/zust", "keys": {"p256dh": push.b64(b"\x04" + b"1" * 64),
                                                                       "auth": push.b64(b"a" * 16)}}


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Base(unittest.TestCase):
    NAME = "Zustell Zora"

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile(cls.NAME)
        push.add(cls.uid, SUB)
        cls.web = push.sub_id(SUB["endpoint"])

    def setUp(self):
        helpers.set_config(reminders=True, note_device=True, iphone=True, deny={})
        for k in [k for k in guard._rate if k[0] == "zustellung"]:
            guard._rate.pop(k, None)
        zustellung._sig.pop(self.uid, None)
        profiles.LAST_USED.pop(self.uid, None)
        self.real = apns.reachable, android.reachable, telegram.push_on
        self.phone = True
        apns.reachable = lambda u: u == self.uid and self.phone
        android.reachable = lambda u, now=None: False
        telegram.push_on = lambda u, private=True: False

    def tearDown(self):
        apns.reachable, android.reachable, telegram.push_on = self.real
        helpers.set_config(note_device=False, iphone=False, deny={})
        zustellung._sig.pop(self.uid, None)
        profiles.LAST_USED.pop(self.uid, None)

    def pick(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            kind, subs = push.pick(self.uid)
        return kind, [push.sub_id(s["endpoint"]) for s in subs], out.getvalue()


class Off(Base):
    def test_off_the_device_used_last_as_before(self):
        helpers.set_config(note_device=False)
        self.assertFalse(features.allowed("notedevice", self.uid))
        profiles.used(self.uid, "web", self.web)
        zustellung.seen(self.uid, "app", 0)                   # even a signal changes nothing while off
        self.assertEqual(self.pick()[:2], ("web", [self.web]))
        r = self.c.post("/api/zustellung/da", json={"idle": 0, "id": self.web})
        self.assertEqual(r.json(), {"on": False})

    def test_parent_off_or_blocked_profile_as_before(self):
        helpers.set_config(reminders=False)
        self.assertFalse(features.allowed("notedevice", self.uid))
        helpers.set_config(reminders=True, deny={"notedevice": [self.uid]})   # the admin blocks this profile
        self.assertFalse(features.allowed("notedevice", self.uid))
        profiles.used(self.uid, "web", self.web)
        zustellung.seen(self.uid, "app", 0)
        self.assertEqual(self.pick()[:2], ("web", [self.web]))

    def test_never_for_guests(self):
        r = TestClient(panel.app).post("/api/zustellung/da", json={"idle": 0})
        self.assertIn(r.status_code, (401, 403))


class Route(Base):
    def test_the_device_in_use_wins_over_the_one_used_last(self):
        profiles.used(self.uid, "app")                        # used last, but now the page is touched
        r = self.c.post("/api/zustellung/da", json={"idle": 3, "id": self.web})
        self.assertEqual(r.json(), {"on": True, "zu": []})
        kind, subs, log = self.pick()
        self.assertEqual((kind, subs), ("web", [self.web]))   # this browser only
        self.assertIn("push: route aktiv web |", log)

    def test_nothing_in_use_the_phone_at_once(self):
        profiles.used(self.uid, "web", self.web)              # used last a minute ago: the page is open, nobody there
        zustellung.seen(self.uid, "web", zustellung.ACTIVE + 5, key=self.web)
        kind, subs, log = self.pick()
        self.assertEqual(kind, "app")
        self.assertIn("push: route handy app |", log)

    def test_touched_last_wins_and_away_or_old_signals_do_not_count(self):
        now = time.time()
        zustellung.seen(self.uid, "web", 50, key=self.web, now=now)
        zustellung.seen(self.uid, "app", 0, now=now)
        self.assertEqual([w for w, _, _ in zustellung.in_use(self.uid, now)], ["app", "web"])
        zustellung.seen(self.uid, "app", 0, gone=True, now=now)          # the app went to the background
        self.assertEqual([w for w, _, _ in zustellung.in_use(self.uid, now)], ["web"])
        self.assertEqual(zustellung.in_use(self.uid, now + zustellung.FRESH + 1), [])   # no fresh word from the page
        zustellung.seen(self.uid, "web", 0, key=self.web, now=now)
        self.assertEqual(zustellung.in_use(self.uid, now + zustellung.ACTIVE + 1), [])  # input too long ago

    def test_no_phone_app_as_before(self):
        self.phone = False
        profiles.used(self.uid, "web", self.web)
        zustellung.seen(self.uid, "web", zustellung.ACTIVE + 5, key=self.web)
        kind, subs, log = self.pick()
        self.assertEqual((kind, subs), ("web", [self.web]))
        self.assertNotIn("route", log)

    def test_a_chosen_way_still_wins(self):
        self.c.post("/api/zustellung/da", json={"idle": 0, "id": self.web})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(push.pick(self.uid, to="app")[0], "app")

    def test_a_device_not_set_up_is_skipped(self):
        zustellung.seen(self.uid, "desk", 0)                  # no Begleiter online with notes: not a way
        self.assertEqual(self.pick()[0], "app")


class Signal(Base):
    def test_the_iphone_app_says_front_and_back(self):
        key = profiles.add_device("iPhone Zora", self.uid, scope="app")
        app = TestClient(panel.app)
        app.headers[profiles.DEVICE_HEADER] = key
        self.assertTrue(app.post("/api/zustellung/da", json={"idle": 0, "weg": False}).json()["on"])
        self.assertEqual([w for w, _, _ in zustellung.in_use(self.uid)], ["app"])
        app.post("/api/zustellung/da", json={"idle": 0, "weg": True})
        self.assertEqual(zustellung.in_use(self.uid), [])

    def test_other_keys_and_bad_values_are_refused(self):
        key = profiles.add_device("Skript Zora", self.uid)
        other = TestClient(panel.app)
        other.headers[profiles.DEVICE_HEADER] = key
        self.assertEqual(other.post("/api/zustellung/da", json={"idle": 0}).status_code, 403)
        self.assertEqual(self.c.post("/api/zustellung/da", json={"idle": "0"}).status_code, 400)
        self.assertEqual(self.c.post("/api/zustellung/da", content=b"{" + b" " * 400 + b"}",
                                     headers={"Content-Type": "application/json"}).status_code, 413)
        self.assertEqual(zustellung.in_use(self.uid), [])

    def test_android_app_counts_as_its_own_way(self):
        ua = {"User-Agent": "Mozilla/5.0 SparkAndroid/1.4.3"}
        self.c.post("/api/zustellung/da", json={"idle": 0}, headers=ua)
        self.assertEqual([w for w, _, _ in zustellung.in_use(self.uid)], ["and"])

    def test_a_key_that_is_no_push_id_is_not_kept(self):
        zustellung.seen(self.uid, "web", 0, key="../x")
        self.assertEqual(zustellung.in_use(self.uid)[0][1], "")
        zustellung.seen(self.uid, "nowhere", 0)
        self.assertEqual([w for w, _, _ in zustellung.in_use(self.uid)], ["web"])


class Shown(Base):
    def test_live_numbers_only(self):
        zustellung._today.update(day="", aktiv=0, handy=0)
        self.c.post("/api/zustellung/da", json={"idle": 0, "id": self.web})
        self.pick()
        z = zustellung.for_live()
        self.assertEqual((z["on"], z["aktiv"], z["handy"]), (True, 1, 0))
        self.assertGreaterEqual(z["devices"], 1)
        conns = [x for x in live._conns(time.time()) if x["name"] == "Gerade benutzte Geräte"]
        self.assertEqual(len(conns), 1)
        self.assertNotIn(self.NAME, str(conns))

    def test_the_log_line_names_no_one_without_consent(self):
        self.c.post("/api/zustellung/da", json={"idle": 0, "id": self.web})
        log = self.pick()[2]
        self.assertNotIn(self.uid, log)
        self.assertRegex(log.strip(), r"^push: route aktiv web \| ")


class Follow(Base):
    NAME = "Zustell Fiete"

    def setUp(self):
        super().setUp()
        helpers.set_config(vorgaenge=True)
        zustellung._out.pop(self.uid, None)
        self.went = []
        self.real_one = push._send_one

        async def one(uid, kind, targets, title, body, tag, private, why, ref="", vg=""):
            self.went.append((kind, tag, vg))
            return 1
        push._send_one = one

    def tearDown(self):
        push._send_one = self.real_one
        zustellung._out.pop(self.uid, None)
        vorgaenge.forget(self.uid)
        helpers.set_config(vorgaenge=False)
        super().tearDown()

    def send(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(push.send(self.uid, "T", "B", **kw))
        return zustellung._out[self.uid][-1]

    def follow(self, now):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            n = asyncio.run(zustellung.follow(now))
        return n, out.getvalue()

    def test_a_note_nobody_saw_comes_once_to_the_phone(self):
        zustellung.seen(self.uid, "web", 0, key=self.web)          # the page is in use: the note goes there
        x = self.send(tag="pro-x")
        self.assertEqual((self.went[-1][0], x["due"]), ("web", x["t"] + zustellung.FOLLOW))
        self.assertEqual(self.follow(x["t"] + zustellung.FOLLOW - 10)[0], 0)   # not yet
        n, log = self.follow(x["t"] + zustellung.FOLLOW + 1)
        self.assertEqual((n, self.went[-1][0]), (1, "app"))
        self.assertIn("push: nachgefasst web → app |", log)
        self.assertEqual(self.follow(x["t"] + 3 * zustellung.FOLLOW)[0], 0)    # never a third time
        self.assertEqual(zustellung.for_live()["nachgefasst"] >= 1, True)

    def test_touched_after_the_note_no_follow_up(self):
        zustellung.seen(self.uid, "web", 0, key=self.web)
        x = self.send(tag="pro-x")
        zustellung.seen(self.uid, "web", 0, key=self.web, now=x["t"] + 30)    # the person went on at the computer
        n, log = self.follow(x["t"] + zustellung.FOLLOW + 1)
        self.assertEqual((n, self.went[-1][0]), (0, "web"))
        self.assertIn("push: nachfassen nicht noetig, gesehen web |", log)

    def test_urgent_waits_shorter_phone_and_chosen_way_never(self):
        self.assertTrue(vorgaenge.ARTEN["erinnerung"]["dringend"])
        zustellung.seen(self.uid, "web", 0, key=self.web)
        x = self.send(tag="r1", why="Erinnerung")
        self.assertEqual(x["due"], x["t"] + zustellung.FOLLOW_URGENT)
        self.assertEqual(self.send(tag="pro-x", to="web")["due"], 0)        # a way the profile chose
        zustellung._sig.pop(self.uid, None)
        self.assertEqual(self.send(tag="pro-x")["way"], "app")             # nothing in use: the phone at once
        self.assertEqual(zustellung._out[self.uid][-1]["due"], 0)

    def test_no_phone_app_no_follow_up(self):
        zustellung.seen(self.uid, "web", 0, key=self.web)
        x = self.send(tag="pro-x")
        self.phone = False
        n, log = self.follow(x["t"] + zustellung.FOLLOW + 1)
        self.assertEqual(n, 0)
        self.assertIn("push: nachfassen ohne handy web |", log)

    def test_off_nothing_kept(self):
        helpers.set_config(note_device=False)
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(push.send(self.uid, "T", "B", tag="pro-x"))
        self.assertNotIn(self.uid, zustellung._out)

    def test_opened_on_one_device_seen_and_gone_everywhere(self):
        with contextlib.redirect_stdout(io.StringIO()):
            v, _ = vorgaenge.put(self.uid, "erinnerung", "erinnerung:zf1", "Erinnerung: Tee")
        zustellung.seen(self.uid, "web", 0, key=self.web)
        x = self.send(tag="r2", why="Erinnerung", vg=v["id"])
        self.assertEqual(self.went[-1], ("web", "r2", v["id"]))
        android.keep(self.uid, "T", "B", "r2", vg=v["id"])
        begleiter.keep(self.uid, "T", "B", "r2", vg=v["id"])
        self.assertTrue(any(n["title"] == "T" for n in android.notes(self.uid, 0)[0]))
        ua = {"User-Agent": "Mozilla/5.0 SparkAndroid/1.4.3"}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            r = self.c.post("/api/zustellung/da", json={"idle": 0, "gesehen": [v["id"]]}, headers=ua).json()
        self.assertIn("push: gesehen 1 and |", out.getvalue())
        self.assertEqual(vorgaenge.find(self.uid, v["id"])["zustand"], "gesehen")
        self.assertEqual(r["zu"], [v["id"]])                                # every device takes it away
        self.assertEqual([n for n in android.notes(self.uid, 0)[0] if n.get("tag") == "r2"], [])
        self.assertEqual([n for n in begleiter.notes(self.uid, 0)[0] if n.get("tag") == "r2"], [])
        self.assertEqual(self.follow(x["t"] + zustellung.FOLLOW + 1)[0], 0)  # seen: no follow-up

    def test_bad_seen_values_refused(self):
        for bad in (["x"], ["v0123456789"] * 6, "v0123456789", [1]):
            self.assertEqual(self.c.post("/api/zustellung/da", json={"idle": 0, "gesehen": bad}).status_code, 400)

    def test_apple_carries_only_the_number(self):
        p = apns.payload("a" * 16, "pro-x", "v0123456789")
        self.assertEqual((p["v"], p["aps"]["alert"]["body"]), ("v0123456789", apns.GENERIC))
        self.assertNotIn("v", apns.payload("a" * 16, "pro-x", "../x"))


class Wiring(unittest.TestCase):
    def test_registered(self):
        self.assertIn("notedevice", {f.key for f in features.FEATURES})
        self.assertIn("/api/zustellung/da", profiles.APP_PATHS)
        self.assertIn("zustellung", guard.RATE)


if __name__ == "__main__":
    unittest.main()
