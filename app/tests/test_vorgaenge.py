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
import ablauf  # noqa: E402
import calendars  # noqa: E402
import chat  # noqa: E402
import fuerdich  # noqa: E402
import guard  # noqa: E402
import profiles  # noqa: E402
import senden  # noqa: E402
import tidy  # noqa: E402
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

    def test_a_meeting_task_is_a_card_that_follows_its_list_entry(self):
        """Besprechungs-Aufgaben (Dominik 2026-10-20 „ok“ 4a): one card per entry under Offen, never in the conversation;
        „Erledigt“ ticks the entry off and „Zurückholen“ brings it back; ticked off, taken back or deleted on the list,
        the card follows; overdue it stays open; „Nicht wichtig“ leaves the entry on the list."""
        import tasks
        helpers.keep_chat(self, "tasks")
        helpers.set_config(tasks=True)
        a = profile("Offen Bert")
        uid = uid_of("Offen Bert")
        asyncio.run(tasks.add(uid, "aufgaben", ["Angebot schicken", "Raum buchen"], src="besprechung", due="2026-01-02", qty=False))
        rows = {x["text"]: x["id"] for x in tasks._load(uid)["items"]}
        self.assertEqual(vorgaenge.from_meeting(uid, "aufgaben", "Aufgaben",
                                                [(rows["Angebot schicken"], "Angebot schicken", "2026-01-02"),
                                                 (rows["Raum buchen"], "Raum buchen", "")], "20.10. 14:00"), 2)
        self.assertEqual(vorgaenge.from_meeting(uid, "aufgaben", "Aufgaben",
                                                [(rows["Raum buchen"], "Raum buchen", "")], "20.10. 14:00"), 0)   # once
        items = {x["titel"]: x for x in a.get("/api/profile/vorgaenge").json()["items"]}
        x = items["Angebot schicken"]
        self.assertEqual((x["art"], x["frist"], x["gruppe"], x["zeile"]), ("besprechung", "2026-01-02", "braucht", "Besprechung 20.10. 14:00"))
        self.assertEqual(sorted(k["k"] for k in x["acts"]), ["ausblenden", "erledigt", "spaeter"])
        self.assertEqual(cards_in_convos(uid), [])                                   # not into the conversation
        self.assertFalse(vorgaenge._stale(vorgaenge._load(uid)["items"][0], datetime.datetime(2026, 12, 1).timestamp()))
        # the card's „Erledigt“ ticks the entry off; „Zurückholen“ brings both back
        r = a.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "erledigt", "rev": x["rev"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(next(y for y in tasks._load(uid)["items"] if y["id"] == rows["Angebot schicken"]).get("done"))
        r = a.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "zurueck", "rev": r.json()["item"]["rev"]})
        self.assertFalse(next(y for y in tasks._load(uid)["items"] if y["id"] == rows["Angebot schicken"]).get("done"))
        self.assertEqual(r.json()["item"]["gruppe"], "braucht")
        # ticked off on the list: the card is done; taken back: open again; deleted: gone
        a.post("/api/profile/tasks/aufgaben/done", json={"ids": [rows["Angebot schicken"]]})
        state = lambda t: next(y for y in vorgaenge._load(uid)["items"] if y["titel"] == t)["zustand"]   # noqa: E731
        self.assertEqual(state("Angebot schicken"), "erledigt")
        a.post("/api/profile/tasks/aufgaben/undo", json={"ids": [rows["Angebot schicken"]]})
        self.assertEqual(state("Angebot schicken"), "offen")
        # „Nicht wichtig“ hides the card only
        y = next(z for z in a.get("/api/profile/vorgaenge").json()["items"] if z["titel"] == "Raum buchen")
        a.post("/api/profile/vorgaenge/act", json={"id": y["id"], "act": "ausblenden", "rev": y["rev"]})
        self.assertIn("Raum buchen", [z["text"] for z in asyncio.run(tasks.items(uid, "aufgaben"))])
        a.delete(f"/api/profile/tasks/aufgaben/{rows['Angebot schicken']}")
        self.assertEqual(state("Angebot schicken"), "weg")

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
        self.assertEqual(set(live), {"on", "profiles", "braucht", "spaeter", "erledigt", "wieder", "streams", "warten", "ja", "arten"})
        self.assertTrue(all(isinstance(v, (int, bool)) for k, v in live.items() if k != "arten"))
        self.assertTrue(set(live["arten"]) <= {a["de"] for a in vorgaenge.ARTEN.values()})   # by kind: fixed names, numbers
        self.assertTrue(all(isinstance(v, int) for v in live["arten"].values()))



TERMIN = {"title": "Steuerberater", "start": "2026-10-23T14:00:00+02:00", "end": "2026-10-23T15:00:00+02:00",
          "location": "Lahr"}


class Vorschlaege(unittest.TestCase):
    """Stufe 2: a proposal waiting for a yes is the card „Wartet auf dein Ja“; its button runs the module's own carry
    (the same as a typed „Ja“), the module's switches are checked again at the press, and the card closes when the
    proposal is answered in the conversation, replaced or over."""
    def setUp(self):
        helpers.keep_chat(self, "reminders", "vorgaenge")
        helpers.set_config(reminders=True, vorgaenge=True)
        for k in [k for k in guard._rate if str(k[0]).startswith("vorgaenge")]:
            guard._rate.pop(k, None)

    def card(self, uid):
        return [x for x in vorgaenge.view(uid)["items"] if x["art"] == "vorschlag"]

    def test_a_new_appointment_waits_as_a_card_and_its_button_saves_it(self):
        a = profile("Vorschlag Vera")
        uid = uid_of("Vorschlag Vera")
        calendars.propose(uid, dict(TERMIN), "web:c1")
        [x] = self.card(uid)
        self.assertEqual((x["titel"], x["zustand"], x["gruppe"]), ("Neuer Termin", "offen", "braucht"))
        self.assertEqual(x["felder"], [["Was", "Steuerberater"], ["Wann", "Fr 23.10., 14:00–15:00"], ["Wo", "Lahr"]])
        self.assertEqual([(k["k"], k["de"], k["stufe"]) for k in x["acts"]],
                         [("vs_ja", "Eintragen", "ja"), ("vs_aendern", "Ändern …", "seite"), ("vs_nein", "Abbrechen", "direkt")])
        # under the answer that made it: the Freigabe-Karte carries the card's number
        [ev] = ablauf.waiting(uid, [calendars], 0, "web:c1")
        self.assertEqual(ev["vg"], x["id"])
        act = lambda **b: a.post("/api/profile/vorgaenge/act", json=dict({"id": x["id"]}, **b))  # noqa: E731
        with mock.patch.object(vorgaenge.notaus, "refuse", return_value=True):     # Notaus: nothing is carried out
            self.assertEqual(act(act="vs_ja", rev=x["rev"]).status_code, 503)
        with mock.patch.object(calendars, "carry", new=mock.AsyncMock(return_value=(True, "Privat"))) as carry:
            r = act(act="vs_ja", rev=x["rev"])
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(act(act="vs_ja", rev=r.json()["item"]["rev"]).status_code, 403)   # once
        self.assertEqual(carry.await_count, 1)
        self.assertEqual(carry.await_args.args[1]["title"], "Steuerberater")
        d = r.json()
        self.assertEqual((d["text"], d["gelungen"]), ("Eingetragen in „Privat“.", True))
        self.assertEqual((d["item"]["zustand"], d["item"]["wie"], d["item"]["fertig"], d["item"]["acts"]),
                         ("erledigt", "vs_ja", ["Eingetragen", "Added"], []))
        self.assertIsNone(calendars.pending(uid))                                  # a later „Ja“ finds nothing
        self.assertEqual(vorgaenge.for_live()["ja"] >= 1, True)

    def test_change_goes_to_the_form_and_cancel_drops_it(self):
        a = profile("Vorschlag Viktor")
        uid = uid_of("Vorschlag Viktor")
        calendars.propose(uid, dict(TERMIN), "web:c2")
        [x] = self.card(uid)
        r = a.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "vs_aendern", "rev": x["rev"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["item"]["zustand"], r.json()["item"]["wie"]), ("weg", "vs_aendern"))
        self.assertIsNone(calendars.pending(uid))
        q = calendars.quick(r.json()["event"], datetime.datetime(2026, 10, 20, 9, 0, tzinfo=BERLIN))   # the form reads it
        self.assertEqual((q["title"], q["location"], q["start"][:16]), ("Steuerberater", "Lahr", "2026-10-23T14:00"))
        calendars.propose(uid, dict(TERMIN, title="Zahnarzt"), "web:c2")
        y = next(c for c in self.card(uid) if c["zustand"] == "offen")
        r = a.post("/api/profile/vorgaenge/act", json={"id": y["id"], "act": "vs_nein", "rev": y["rev"]})
        self.assertEqual((r.json()["item"]["zustand"], r.json()["item"]["wie"]), ("weg", "vs_nein"))
        self.assertIsNone(calendars.pending(uid))

    def test_the_card_closes_when_answered_replaced_or_over(self):
        profile("Vorschlag Wanda")
        uid = uid_of("Vorschlag Wanda")
        vorgaenge.from_pending(uid, "calendar", dict(TERMIN, t=100))
        old = self.card(uid)[0]["id"]
        calendars.propose(uid, dict(TERMIN, title="Friseur"), "web:c3")            # a newer one replaces it
        by = {x["id"]: x for x in self.card(uid)}
        self.assertEqual((by[old]["zustand"], by[old]["wie"]), ("weg", "ersetzt"))
        new = next(i for i in by if i != old)
        p = calendars.pending(uid)
        calendars.drop_pending(uid)                                                # „Ja“ or „Nein“ typed in the conversation
        self.assertEqual(vorgaenge.sweep(uid, now=p["t"] + 30), 1)
        x = next(c for c in self.card(uid) if c["id"] == new)
        self.assertEqual((x["zustand"], x["wie"]), ("weg", "beantwortet"))
        vorgaenge.from_pending(uid, "calendar", dict(TERMIN, t=200))               # long over: nothing waits
        self.assertEqual(vorgaenge.sweep(uid, now=200 + 16 * 60), 1)
        self.assertEqual(sorted(c["wie"] for c in self.card(uid)), ["abgelaufen", "beantwortet", "ersetzt"])

    def test_the_modules_switches_count_at_the_press_and_the_text_goes_with_the_answer(self):
        a = profile("Vorschlag Willi")
        uid = uid_of("Vorschlag Willi")
        p = {"kind": "new", "account": "x", "to": "anna@example.org", "label": "Anna", "text": "Samstag passt.", "subject": "Samstag"}
        profiles.pending_set(uid, senden.NAME, p, "web:c4")
        [x] = self.card(uid)
        self.assertEqual((x["titel"], x["felder"][-1], [k["de"] for k in x["acts"]]),
                         ("Neue Mail", ["Text", "Samstag passt."], ["Senden", "Ändern …", "Abbrechen"]))
        with mock.patch.object(senden, "level", return_value="off"):               # „Mails senden“ switched off since
            r = a.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "vs_ja", "rev": x["rev"]})
        self.assertEqual(r.status_code, 403)
        self.assertIsNotNone(senden.pending(uid))
        other = profile("Vorschlag Wilma")                                         # never another profile's
        self.assertEqual(other.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "vs_ja"}).status_code, 404)
        with mock.patch.object(vorgaenge, "_may", return_value=True):            # „Mails senden“ on
            r = a.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "vs_aendern", "rev": x["rev"]})
        self.assertEqual(r.json()["draft"], {"to": "anna@example.org", "subject": "Samstag", "text": "Samstag passt."})
        self.assertNotIn("Text", [f[0] for f in r.json()["item"]["felder"]])       # the mail's text only while it waits
        self.assertEqual(senden.card(uid, dict(p, kind="reply")).get("aendern"), None)   # an answer stays one
        self.assertEqual(tidy.card(uid, {"kind": "draft", "to_show": "Anna", "subject": "Re: x", "text": "Hallo"})["knopf"], "ablegen")


if __name__ == "__main__":
    unittest.main()


class Stufe34(unittest.TestCase):
    """Stages 3 and 4 (Dominik 2026-10-21 „weiter bis zum ende“): chats, shares, important mails, services (admins),
    questions of jobs and MCP approvals as cards; the buttons under a Telegram note and the Begleiter's „Erledigt“
    run the same checks as the card; „Was ist offen?“ only reads. No clock of the run is read."""
    def setUp(self):
        helpers.keep_chat(self, "reminders", "vorgaenge", "chats")
        helpers.set_config(reminders=True, vorgaenge=True, chats=True)
        for k in [k for k in guard._rate if str(k[0]).startswith("vorgaenge")]:
            guard._rate.pop(k, None)

    def test_a_chat_message_is_one_card_without_its_text_and_reading_closes_it(self):
        import chats
        a, b = profile("Offen Chat A"), profile("Offen Chat B")
        ua, ub = uid_of("Offen Chat A"), uid_of("Offen Chat B")
        cid = a.post("/api/chats/open", json={"to": ub}).json()["id"]
        meta = chats._index()[cid]
        with mock.patch.object(chats, "listening", return_value=False):
            asyncio.run(chats._notify(ub, cid, meta, ua, "Geheimer Text", 1000.0))
            asyncio.run(chats._notify(ub, cid, meta, ua, "Noch einer", 1001.0))
        mine = [x for x in vorgaenge._load(ub)["items"] if x["art"] == "nachricht"]
        self.assertEqual(len(mine), 1)                                    # one card per chat
        x = mine[0]
        self.assertEqual((x["key"], x["zeile"], x["daten"]), ("chat:" + cid, "Neue Nachricht", {"chat": cid}))
        self.assertNotIn("Geheim", str(x))                                # never the text
        self.assertEqual(cards_in_convos(ub), [])                         # only under Offen
        r = b.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "cx_gelesen", "rev": x["rev"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["item"]["zustand"], r.json()["item"]["wie"]), ("erledigt", "cx_gelesen"))
        with mock.patch.object(chats, "listening", return_value=False):   # a new message opens it again
            asyncio.run(chats._notify(ub, cid, meta, ua, "Dritte", 1002.0))
        self.assertEqual(next(y for y in vorgaenge._load(ub)["items"] if y["key"] == "chat:" + cid)["zustand"], "offen")
        chats.read(ub, cid)                                               # reading the chat closes it
        y = next(y for y in vorgaenge._load(ub)["items"] if y["key"] == "chat:" + cid)
        self.assertEqual((y["zustand"], y["wie"]), ("erledigt", "cx_gelesen"))
        self.assertEqual(a.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "cx_gelesen"}).status_code, 404)

    def test_a_share_is_a_card_and_a_mail_reply_needs_the_mail_switch(self):
        import geteilt
        profile("Offen Teil A"), profile("Offen Teil B")
        ua, ub = uid_of("Offen Teil A"), uid_of("Offen Teil B")
        asyncio.run(geteilt.tell(ub, ua, "doc"))
        asyncio.run(geteilt.tell(ub, ua, "doc"))                          # a second share: still one card
        x = next(y for y in vorgaenge._load(ub)["items"] if y["art"] == "geteilt")
        self.assertEqual((x["key"], x["titel"], x["daten"]), (f"geteilt:doc:{ua}", "Offen Teil A hat etwas mit dir geteilt",
                                                             {"weg": "Ich → Geteilt"}))
        self.assertEqual([m["vg"] for m in cards_in_convos(ub)], [x["id"]])   # the note is on: the card once in the conversation
        self.assertEqual([k["k"] for k in vorgaenge.public(ub, x)["acts"]], ["oeffnen", "erledigt", "spaeter"])
        m, _ = vorgaenge.put(ub, "mail", "mail:a1:42", "Wichtige Mail von Bank", "Kontoauszug",
                             daten={"ref": "a1:42", "folder": "INBOX", "addr": "bank@example.org"})
        acts = lambda: [k["k"] for k in vorgaenge.public(ub, m)["acts"]]  # noqa: E731
        real = vorgaenge.features.allowed
        with mock.patch.object(vorgaenge.features, "allowed", side_effect=lambda k, *a: k != "mailsend" and real(k, *a)):
            self.assertEqual(acts(), ["ml_lesen", "erledigt", "spaeter"])
        with mock.patch.object(vorgaenge.features, "allowed", side_effect=lambda k, *a: True):
            self.assertEqual(acts(), ["ml_lesen", "fd_reply", "erledigt", "spaeter"])

    def test_stage_four_cards_close_at_their_source_and_never_confirm(self):
        import dienstwacht
        profile("Offen Admin")
        uid = uid_of("Offen Admin")
        with mock.patch.object(dienstwacht, "recipients", return_value=[uid]), \
                mock.patch.object(dienstwacht, "_read", return_value={"queue": {}}):
            dienstwacht._queue_all({"k": "down", "s": "tts", "t": 1000}, 1000.0)
            x = next(y for y in vorgaenge._load(uid)["items"] if y["art"] == "dienst")
            self.assertEqual((x["key"], x["titel"], x["daten"]), ("dienst:tts", "Sprechen ist ausgefallen", {"weg": "Zustand → Überblick"}))
            self.assertNotIn("neustart", str(vorgaenge.public(uid, x)["acts"]).lower())    # nothing restarts from a card
            dienstwacht._queue_all({"k": "up", "s": "tts", "t": 1100}, 1100.0)
        y = next(y for y in vorgaenge._load(uid)["items"] if y["key"] == "dienst:tts")
        self.assertEqual((y["zustand"], y["wie"]), ("erledigt", "wieder_da"))
        # an MCP approval: the card only opens the page; „Erledigt“ is no button of it, the decision closes it
        f, _ = vorgaenge.put(uid, "freigabe", "freigabe:ab12cd34", "„Notizen“ möchte etwas tun", "Licht an",
                             daten={"weg": "Ich → Spark als MCP-Server"}, now=1000.0)
        self.assertEqual([k["k"] for k in vorgaenge.public(uid, f)["acts"]], ["oeffnen", "spaeter"])
        with self.assertRaises(vorgaenge.HTTPException) as e:
            vorgaenge.act(uid, f["id"], "erledigt")
        self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(vorgaenge.knoepfe(uid, f["id"]), [("spaeter", "Später")])     # Telegram: no yes, ever
        self.assertTrue(vorgaenge._stale(f, 1000.0 + 16 * 60))                          # gone with the action's 15 min
        vorgaenge.done(uid, "freigabe:ab12cd34", "abgelehnt")
        self.assertEqual(next(y for y in vorgaenge._load(uid)["items"] if y["id"] == f["id"])["zustand"], "weg")
        # a job's question: no answer in time closes its card as „Abgelaufen“
        import auftragsplan
        with mock.patch.object(auftragsplan, "ASK_SECONDS", 0.01), mock.patch.object(auftragsplan.agent, "_set_job"), \
                mock.patch.object(auftragsplan.agent, "job", return_value={}):
            self.assertIsNone(asyncio.run(auftragsplan._wait(uid, "j1a2b3c4d5", "Welche Farbe?", [], "Bild malen")))
        j = next(y for y in vorgaenge._load(uid)["items"] if y["key"] == "auftrag:j1a2b3c4d5")
        self.assertEqual((j["zustand"], j["wie"], j["daten"]), ("weg", "abgelaufen", {"weg": "Ich → Aufträge"}))

    def test_telegram_buttons_are_the_direct_ones_and_only_from_the_own_chat(self):
        import telegram
        profile("Offen Tele")
        uid = uid_of("Offen Tele")
        x, _ = vorgaenge.put(uid, "erinnerung", "erinnerung:tg1", "Erinnerung: Müll")
        keys = telegram.vg_keyboard(uid, x["id"])
        self.assertEqual([b["callback_data"] for b in keys["inline_keyboard"][0]],
                         [f"vg:{x['id']}:erledigt", f"vg:{x['id']}:spaeter"])
        self.assertIsNone(telegram.vg_keyboard(uid, "nonsense"))
        calls = []

        async def fake(c, method, **p):
            calls.append((method, p))
        q = lambda frm, data: {"id": "q1", "data": data, "from": {"id": frm},  # noqa: E731
                               "message": {"message_id": 7, "chat": {"id": 555, "type": "private"}}}
        with mock.patch.object(telegram, "call", fake), mock.patch.object(telegram, "owner", return_value=uid):
            asyncio.run(telegram.on_press(None, q(999, f"vg:{x['id']}:erledigt")))      # someone else's press
            self.assertEqual(vorgaenge._load(uid)["items"][-1]["zustand"], "offen")
            asyncio.run(telegram.on_press(None, q(555, f"vg:{x['id']}:fd_remind")))     # not a button of this note
            self.assertEqual(vorgaenge._load(uid)["items"][-1]["zustand"], "offen")
            asyncio.run(telegram.on_press(None, q(555, f"vg:{x['id']}:erledigt")))
        y = next(y for y in vorgaenge._load(uid)["items"] if y["id"] == x["id"])
        self.assertEqual((y["zustand"], y["wo"]), ("erledigt", "Telegram"))
        self.assertEqual([m for m, _ in calls].count("answerCallbackQuery"), 3)          # Telegram always gets its answer
        self.assertIn("editMessageReplyMarkup", [m for m, _ in calls])

    def test_the_begleiter_closes_a_vorgang_note_with_the_cards_checks(self):
        import begleiter
        profile("Offen Desk")
        uid = uid_of("Offen Desk")
        x, _ = vorgaenge.put(uid, "erinnerung", "erinnerung:bg1", "Erinnerung: Tee")
        note = {"tag": "", "vg": x["id"], "ref": ""}
        self.assertEqual(begleiter.note_acts(uid, note), ["done", "reply", "later", "open"])
        self.assertEqual(begleiter._vg_act({"id": uid, "name": "Offen Desk"}, x["id"])["ok"], True)
        self.assertEqual(next(y for y in vorgaenge._load(uid)["items"] if y["id"] == x["id"])["wo"], "Begleiter")
        self.assertEqual(begleiter.note_acts(uid, note), ["reply", "later", "open"])        # closed: no „Erledigt“

    def test_what_is_open_only_reads_and_counts_as_mail(self):
        profile("Offen Frage")
        uid = uid_of("Offen Frage")
        ctx = {"who": {"id": uid}, "own": True, "text": "Was ist noch offen?"}
        o = vorgaenge.offer(ctx)
        self.assertEqual(([t["function"]["name"] for t in o["tools"]], o["mail"]), (["offen_zeigen"], {"offen_zeigen"}))
        self.assertIsNone(vorgaenge.offer(dict(ctx, text="Wie wird das Wetter?")))
        self.assertIsNone(vorgaenge.offer(dict(ctx, client="mcp")))
        self.assertIsNone(vorgaenge.offer(dict(ctx, own=False)))
        self.assertEqual(asyncio.run(vorgaenge.tool("offen_zeigen", {}, ctx)), "Nichts offen.")
        vorgaenge.put(uid, "erinnerung", "erinnerung:of1", "Erinnerung: Brot", now=1000.0)
        vorgaenge.put(uid, "geteilt", "geteilt:doc:x", "Anna hat etwas mit dir geteilt", "Dokument", now=2000.0)
        before = [dict(y) for y in vorgaenge._load(uid)["items"]]
        out = asyncio.run(vorgaenge.tool("offen_zeigen", {}, ctx))
        self.assertTrue(out.startswith("Offen: 2. Erinnerung: Erinnerung: Brot; Geteilt: Anna"), out)   # urgent first
        self.assertEqual(vorgaenge._load(uid)["items"], before)            # reading changes nothing
        with mock.patch.object(vorgaenge.features, "allowed", return_value=False):
            self.assertIsNone(vorgaenge.offer(ctx))
            self.assertIn("aus", asyncio.run(vorgaenge.tool("offen_zeigen", {}, ctx)))

    def test_a_source_module_registers_its_own_buttons(self):
        """vorgaenge.QUELLEN: a module's kind with its own buttons; act() checks first, then runs the module's rule."""
        profile("Offen Quelle")
        uid = uid_of("Offen Quelle")
        ran = []
        arten, aktionen = dict(vorgaenge.ARTEN), dict(vorgaenge.AKTIONEN)
        self.addCleanup(lambda: (vorgaenge.ARTEN.clear(), vorgaenge.ARTEN.update(arten), vorgaenge.AKTIONEN.clear(),
                                 vorgaenge.AKTIONEN.update(aktionen), vorgaenge.QUELLEN.pop("probe", None)))
        vorgaenge.ARTEN["probe"] = {"de": "Probe", "en": "Probe", "sym": "check", "mail": False, "dringend": False,
                                    "acts": ("pr_tun", "pr_nie")}
        vorgaenge.AKTIONEN.update(pr_tun={"de": "Tun", "en": "Do", "stufe": "direkt"}, pr_nie={"de": "Nie", "en": "Never", "stufe": "direkt"})
        vorgaenge.QUELLEN["probe"] = {"acts": lambda u, x: {"pr_tun"}, "run": lambda u, x, n: ran.append(n) or {"text": "getan"}}
        x, _ = vorgaenge.put(uid, "probe", "probe:1", "Eine Probe")
        self.assertEqual([k["k"] for k in vorgaenge.public(uid, x)["acts"]], ["pr_tun", "spaeter"])
        with self.assertRaises(vorgaenge.HTTPException):
            vorgaenge.act(uid, x["id"], "pr_nie")                         # its rules do not allow it now
        self.assertEqual(vorgaenge.act(uid, x["id"], "pr_tun")["text"], "getan")
        self.assertEqual(ran, ["pr_tun"])
