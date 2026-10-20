"""Alles Offene im Assistenten (vorgaenge.py, offen.js, plan assistent-zentrale Stufe 1): one Vorgang per thing by its
key, the card as a message of today's main conversation, the buttons only as fixed names checked on the Spark (kind,
state, rev, Notaus), „Später“ coming back once, Für dich and the Vorgang marked together, and the rules every
endpoint keeps (sign-in, switch, block, size, input). Times are given, never read from the clock of the run."""
import asyncio
import datetime
import unittest
import zoneinfo
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
import fuerdich  # noqa: E402
import guard  # noqa: E402
import profiles  # noqa: E402
import vorgaenge  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def cards_in_convos(uid):
    return [m for c in profiles.convos(uid) for m in c["msgs"] if m.get("vg")]


class Vorgaenge(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "reminders", "vorgaenge")
        helpers.set_config(reminders=True, vorgaenge=True)
        for k in [k for k in guard._rate if str(k[0]).startswith("vorgaenge")]:
            guard._rate.pop(k, None)

    def test_a_reminder_that_rang_becomes_one_card_in_todays_conversation(self):
        a = profile("Offen Olga")
        uid = uid_of("Offen Olga")
        rid = profiles.add_reminder(uid, "Ofen aus", 1000)["id"]
        r = a.post("/api/profile/reminders/played", json={"id": rid})
        self.assertTrue(r.json()["play"])
        vid = r.json()["vg"]
        self.assertRegex(vid, r"^v[0-9a-f]{10}$")
        self.assertFalse(a.post("/api/profile/reminders/played", json={"id": rid}).json()["play"])   # one ring only
        d = a.get("/api/profile/vorgaenge").json()
        x = next(y for y in d["items"] if y["id"] == vid)
        self.assertEqual((x["art"], x["zustand"], x["gruppe"], x["titel"]), ("erinnerung", "offen", "braucht", "Erinnerung: Ofen aus"))
        self.assertEqual([k["k"] for k in x["acts"]], ["erledigt", "spaeter"])
        msgs = [m for m in cards_in_convos(uid) if m["vg"] == vid]
        self.assertEqual(len(msgs), 1)                                 # the card once, as the panel's sentence
        self.assertEqual((msgs[0]["role"], msgs[0]["content"]), ("assistant", "Erinnerung: Ofen aus"))
        # the same key never makes a second one
        y, new = vorgaenge.put(uid, "erinnerung", "erinnerung:" + rid, "Erinnerung: Ofen aus")
        self.assertEqual((y["id"], new), (vid, False))
        self.assertEqual(len([m for m in cards_in_convos(uid) if m["vg"] == vid]), 1)

    def test_buttons_are_fixed_names_checked_on_the_spark(self):
        a = profile("Offen Otto")
        uid = uid_of("Offen Otto")
        x, _ = vorgaenge.put(uid, "erinnerung", "erinnerung:k1", "Erinnerung: Blumen")
        act = lambda **b: a.post("/api/profile/vorgaenge/act", json=dict({"id": x["id"]}, **b))  # noqa: E731
        self.assertEqual(act(act="loeschen", rev=x["rev"]).status_code, 400)       # no such button
        self.assertEqual(act(act="fd_remind", rev=x["rev"]).status_code, 403)      # not a button of this kind
        self.assertEqual(act(act="spaeter", rev=x["rev"], wann="nie").status_code, 400)
        r = act(act="erledigt", rev=x["rev"] + 5)                                  # another device was quicker
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["item"]["zustand"], "offen")
        r = act(act="erledigt", rev=x["rev"])
        self.assertEqual(r.status_code, 200, r.text)
        y = r.json()["item"]
        self.assertEqual((y["zustand"], y["gruppe"], y["wo"], [k["k"] for k in y["acts"]]), ("erledigt", "erledigt", "Rechner", ["zurueck"]))
        self.assertEqual(act(act="erledigt", rev=y["rev"]).status_code, 403)        # done is done
        r = act(act="zurueck", rev=y["rev"])
        self.assertEqual(r.json()["item"]["zustand"], "offen")
        with mock.patch.object(vorgaenge.notaus, "refuse", return_value=True):     # Notaus: nothing changes
            self.assertEqual(act(act="erledigt").status_code, 503)
        other = profile("Offen Oda")                                               # never another profile's
        self.assertEqual(other.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "erledigt"}).status_code, 404)

    def test_later_comes_back_once_at_the_chosen_time(self):
        local = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=BERLIN)               # a Wednesday
        at = lambda w, d=local: datetime.datetime.fromtimestamp(vorgaenge.later_at(w, d), BERLIN)  # noqa: E731
        self.assertEqual(at("abend").strftime("%a %H:%M"), "Wed 18:00")
        self.assertEqual(at("abend", local.replace(hour=19)).strftime("%a %H:%M"), "Wed 22:00")
        self.assertEqual(at("morgen").strftime("%a %H:%M"), "Thu 08:00")
        self.assertEqual(at("woche").strftime("%a %d %H:%M"), "Mon 26 08:00")
        self.assertEqual(at("woche", local.replace(day=25)).strftime("%a %d %H:%M"), "Mon 26 08:00")   # a Sunday
        self.assertEqual(vorgaenge.later_at("ohne", local), 0)
        profile("Offen Paul")
        uid = uid_of("Offen Paul")
        local = local.replace(tzinfo=chat.user_zone(profiles.effective(uid).get("tz", "")))   # the profile's own zone
        now = local.timestamp()
        x, _ = vorgaenge.put(uid, "erinnerung", "erinnerung:k2", "Erinnerung: Paket", now=now)
        y = vorgaenge.act(uid, x["id"], "spaeter", x["rev"], "abend", now=now)["item"]
        self.assertEqual((y["zustand"], y["gruppe"]), ("spaeter", "spaeter"))
        self.assertEqual(y["spaeter_bis"], int(local.replace(hour=18).timestamp()))
        self.assertEqual(asyncio.run(vorgaenge.due(now=y["spaeter_bis"] - 60)), 0)  # not yet
        with mock.patch("push.send", new=mock.AsyncMock()) as sent:
            self.assertEqual(asyncio.run(vorgaenge.due(now=y["spaeter_bis"] + 1)), 1)
            self.assertEqual(asyncio.run(vorgaenge.due(now=y["spaeter_bis"] + 61)), 0)   # once
        self.assertEqual(sent.await_count, 1)
        self.assertEqual(sent.await_args.kwargs["tag"], "vg-" + x["id"])
        z = next(v for v in vorgaenge.view(uid)["items"] if v["id"] == x["id"])
        self.assertEqual(z["zustand"], "offen")
        self.assertIn("Wieder da: Erinnerung: Paket", [m["content"] for m in cards_in_convos(uid) if m["vg"] == x["id"]])

    def test_fuer_dich_and_the_vorgang_are_marked_together(self):
        profile("Offen Fritz")
        uid = uid_of("Offen Fritz")
        k = "ab" * 10
        x, _ = vorgaenge.put(uid, "fuerdich", "fuerdich:" + k, "Rechnung von Stadtwerke", felder=[["Von", "Stadtwerke"]])
        fuerdich.mark(uid, k, "done")                       # marked on the mail page
        self.assertEqual(vorgaenge.view(uid)["items"][0]["zustand"], "erledigt")
        fuerdich.mark(uid, k, "open")                       # „Markierungen vergessen“
        y = vorgaenge.view(uid)["items"][0]
        self.assertEqual(y["zustand"], "offen")
        vorgaenge.act(uid, x["id"], "ausblenden", y["rev"])  # pressed on the card
        self.assertEqual(fuerdich.marks(uid)[k][0], "no")
        self.assertEqual(vorgaenge.view(uid)["items"][0]["zustand"], "weg")

    def test_only_an_assistant_message_keeps_its_card_number(self):
        clean = profiles._clean_msg
        self.assertEqual(clean({"role": "assistant", "content": "x", "vg": "v0123456789"}).get("vg"), "v0123456789")
        self.assertNotIn("vg", clean({"role": "user", "content": "x", "vg": "v0123456789"}))
        self.assertNotIn("vg", clean({"role": "assistant", "content": "x", "vg": "<b>"}))

    def test_every_endpoint_keeps_the_rules(self):
        guest = TestClient(panel.app)
        for m, p in (("get", "/api/profile/vorgaenge"), ("post", "/api/profile/vorgaenge/act"),
                     ("post", "/api/profile/vorgaenge/seen"), ("delete", "/api/profile/vorgaenge")):
            self.assertIn(getattr(guest, m)(p, **({"json": {}} if m == "post" else {})).status_code, (401, 403), p)
        a = profile("Offen Ines")
        uid = uid_of("Offen Ines")
        x, _ = vorgaenge.put(uid, "erinnerung", "erinnerung:k3", "Erinnerung: Tee")
        self.assertEqual(a.post("/api/profile/vorgaenge/act", content=b"{" + b" " * 4000 + b"}",
                                headers={"Content-Type": "application/json"}).status_code, 413)
        self.assertEqual(a.post("/api/profile/vorgaenge/act", json={"id": "x", "act": "erledigt"}).status_code, 400)
        self.assertEqual(a.post("/api/profile/vorgaenge/seen", json={"ids": ["v" + "0" * 10] * 21}).status_code, 400)
        r = a.post("/api/profile/vorgaenge/seen", json={"ids": [x["id"]]})
        self.assertEqual(r.json()["n"], 1)
        self.assertEqual(vorgaenge.view(uid)["items"][0]["zustand"], "gesehen")
        self.assertEqual(a.get(f"/api/profile/vorgaenge?seit={vorgaenge.view(uid)['rev']}").json()["items"], [])
        # blocked by the admin, or off for everyone: nothing new and the endpoints say no
        r = ADMIN.put(f"/api/admin/features/vorgaenge/profiles/{uid}", json={"on": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.addCleanup(ADMIN.put, f"/api/admin/features/vorgaenge/profiles/{uid}", json={"on": True})
        self.assertEqual(a.get("/api/profile/vorgaenge").status_code, 403)
        self.assertEqual(vorgaenge.put(uid, "erinnerung", "erinnerung:k4", "Erinnerung: x"), (None, False))
        ADMIN.put(f"/api/admin/features/vorgaenge/profiles/{uid}", json={"on": True})
        helpers.set_config(vorgaenge=False)
        self.assertEqual(a.get("/api/profile/vorgaenge").status_code, 403)
        self.assertEqual(vorgaenge.for_live(), {"on": False})
        helpers.set_config(vorgaenge=True)
        # the done ones away, then all
        y = vorgaenge.act(uid, x["id"], "erledigt")["item"]
        vorgaenge.put(uid, "erinnerung", "erinnerung:k5", "Erinnerung: Brot")
        self.assertEqual(a.delete("/api/profile/vorgaenge?nur=erledigt").json()["n"], 1)
        self.assertEqual([v["titel"] for v in vorgaenge.view(uid)["items"]], ["Erinnerung: Brot"])
        self.assertEqual(a.delete("/api/profile/vorgaenge").json()["n"], 1)
        self.assertEqual(vorgaenge.view(uid)["items"], [])
        self.assertNotEqual(y["rev"], vorgaenge.view(uid)["rev"])
        # Live: numbers only
        live = vorgaenge.for_live()
        self.assertEqual(set(live), {"on", "profiles", "braucht", "spaeter", "erledigt", "wieder", "streams"})
        self.assertTrue(all(isinstance(v, (int, bool)) for v in live.values()))


if __name__ == "__main__":
    unittest.main()
