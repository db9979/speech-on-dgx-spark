"""Ändern per Sprache (plan werkzeug-abdeckung.md, Paket 6): appointments moved or deleted, scheduled jobs paused,
smart home rules deleted, the notes paused, the own speakers' volume, repeating reminders, a message into an own
group, and „Mach das rückgängig“. Every change that is not plain switching waits for the person's yes; nothing
here depends on the clock (times are fixed years ahead)."""
import asyncio
import datetime
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import agent  # noqa: E402
import aendern  # noqa: E402
import calendars  # noqa: E402
import chat  # noqa: E402
import chat_tools  # noqa: E402
import hamelden  # noqa: E402
import mcpserver  # noqa: E402
import messages  # noqa: E402
import panel  # noqa: E402
import proactive  # noqa: E402
import profiles  # noqa: E402
import taten  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
DAV_PORT = helpers._port()
EVENTS = {}   # path -> (etag, iCal text)


def fake_caldav():
    """One appointment calendar /dav/termine/ that answers PROPFIND, REPORT (with etags), GET, PUT and DELETE."""
    app = FastAPI()
    ms = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'

    def resp(href, prop):
        return f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{prop}</d:prop></d:propstat></d:response>"

    @app.api_route("/dav/{rest:path}", methods=["GET", "PROPFIND", "REPORT", "PUT", "DELETE"])
    async def dav(rest: str, req: Request):
        path = "/dav/" + rest
        if req.method == "PROPFIND":
            x = resp("/dav/termine/", "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                                      "<d:displayname>Termine</d:displayname>")
            return Response(ms + x + "</d:multistatus>", status_code=207, media_type="application/xml")
        if req.method == "REPORT":
            x = "".join(resp(h, f"<d:getetag>{e}</d:getetag><c:calendar-data>{t}</c:calendar-data>")
                        for h, (e, t) in EVENTS.items())
            return Response(ms + x + "</d:multistatus>", status_code=207, media_type="application/xml")
        old = EVENTS.get(path)
        if req.method == "GET":
            return Response(old[1], headers={"ETag": old[0]}) if old else Response(status_code=404)
        if req.method == "PUT":
            if req.headers.get("if-none-match") == "*" and old:
                return Response(status_code=412)
            if req.headers.get("if-match") and (not old or old[0] != req.headers["if-match"]):
                return Response(status_code=412)
            EVENTS[path] = (f'"e{len(EVENTS)}{int(bool(old))}{len(await req.body())}"', (await req.body()).decode())
            return Response(status_code=201 if not old else 204)
        if req.method == "DELETE":
            if req.headers.get("if-match") and (not old or old[0] != req.headers["if-match"]):
                return Response(status_code=412)
            EVENTS.pop(path, None)
            return Response(status_code=204)
        return Response(status_code=501)
    return app


helpers._serve(fake_caldav(), DAV_PORT)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def ics(title, start, rrule=""):
    s = start.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    e = (start + datetime.timedelta(hours=1)).astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//DE\r\nBEGIN:VEVENT\r\nUID:" + title.replace(" ", "") +
            f"@t\r\nDTSTAMP:{s}\r\nDTSTART:{s}\r\nDTEND:{e}\r\nSUMMARY:{title}\r\n" + (f"RRULE:{rrule}\r\n" if rrule else "")
            + "END:VEVENT\r\nEND:VCALENDAR\r\n")


ZONE = chat.user_zone("Europe/Berlin")
DAY = datetime.datetime(2031, 3, 4, 10, 0, tzinfo=ZONE)   # far ahead: never „in the past“


class Turn:
    """The bits of a chat turn calendar_change reads (chat_tools.Turn has many more)."""
    def __init__(self, uid):
        self.who, self.src, self.cal_write, self.body = {"id": uid}, "web|c1", True, {"tz": "Europe/Berlin"}
        self.out = asyncio.Queue()


class Calendar(unittest.TestCase):
    """calendar_change: one single appointment, found by title and day, changed only after the yes, undone again."""

    @classmethod
    def setUpClass(cls):
        profile("Kalla")
        cls.uid = uid_of("Kalla")
        calendars.add(cls.uid, calendars.entry({"url": f"http://127.0.0.1:{DAV_PORT}/dav/", "name": "Nextcloud"}))

    def setUp(self):
        EVENTS.clear()
        EVENTS["/dav/termine/zahnarzt.ics"] = ('"z1"', ics("Zahnarzt", DAY))
        EVENTS["/dav/termine/yoga.ics"] = ('"y1"', ics("Yoga", DAY, "FREQ=WEEKLY"))
        calendars.drop_pending(self.uid)

    def propose(self, **args):
        return asyncio.run(chat_tools.calendar_change(Turn(self.uid), args))

    def test_move_waits_for_the_yes_then_moves_and_undoes(self):
        out = self.propose(title="Zahnarzt", date="2031-03-04", action="move", new_start="2031-03-07T15:30")
        self.assertIn("NOT changed yet", out)
        self.assertIn("auf Fr 07.03.2031 15:30 verschieben", out)
        self.assertIn("DTSTART:20310304T090000Z", EVENTS["/dav/termine/zahnarzt.ics"][1])   # untouched before the yes
        p = calendars.pending(self.uid)
        kept = {}
        said = asyncio.run(calendars.change_event(self.uid, p, kept))
        self.assertIn("verschoben", said)
        self.assertIn("DTSTART:20310307T143000Z", EVENTS["/dav/termine/zahnarzt.ics"][1])
        self.assertIn("SEQUENCE:1", EVENTS["/dav/termine/zahnarzt.ics"][1])
        aendern.note(self.uid, "calendar_ics", kept, "den Termin wie vorher stellen")
        asyncio.run(aendern.undo(self.uid, aendern.last(self.uid), {}))
        self.assertIn("DTSTART:20310304T090000Z", EVENTS["/dav/termine/zahnarzt.ics"][1])

    def test_delete_and_restore(self):
        self.propose(title="Zahnarzt", action="delete")
        kept = {}
        asyncio.run(calendars.change_event(self.uid, calendars.pending(self.uid), kept))
        self.assertNotIn("/dav/termine/zahnarzt.ics", EVENTS)
        self.assertTrue(kept["deleted"])
        asyncio.run(calendars.put_ics(self.uid, kept["account"], kept["href"], kept["ics"], new=True))
        self.assertIn("Zahnarzt", EVENTS["/dav/termine/zahnarzt.ics"][1])

    def test_a_repeating_appointment_is_never_changed(self):
        out = self.propose(title="Yoga", action="delete")
        self.assertIn("repeat", out)
        self.assertIsNone(calendars.pending(self.uid))

    def test_a_change_made_meanwhile_is_not_overwritten(self):
        self.propose(title="Zahnarzt", action="delete")
        p = calendars.pending(self.uid)
        EVENTS["/dav/termine/zahnarzt.ics"] = ('"z2"', ics("Zahnarzt", DAY + datetime.timedelta(hours=2)))
        with self.assertRaises(ValueError):
            asyncio.run(calendars.change_event(self.uid, p))
        self.assertIn("/dav/termine/zahnarzt.ics", EVENTS)

    def test_nothing_fits_or_too_many_fit(self):
        self.assertIn("no matching appointment", self.propose(title="Friseur", action="delete"))
        EVENTS["/dav/termine/zahnarzt2.ics"] = ('"z3"', ics("Zahnarzt Kontrolle", DAY + datetime.timedelta(days=1)))
        self.assertIn("several appointments fit", self.propose(title="Zahnarzt", action="delete"))
        self.assertIn("in the past", self.propose(title="Zahnarzt Kontrolle", action="move", new_start="2020-01-01T10:00"))

    def test_the_hint_says_calendar_add_never_moves(self):
        self.assertIn("calendar_change", chat.CALENDAR_ADD_HINT)
        self.assertIn("calendar_change", chat.LOCKED_OUTSIDE)


class Plans(unittest.TestCase):
    def test_pause_after_the_yes_and_undo(self):
        profile("Planina")
        uid = uid_of("Planina")
        with mock.patch.object(agent, "may", return_value=True):
            item = agent.add_plan(uid, {"task": "Wochenüberblick Wetter", "repeat": "weekly", "weekday": 0, "time": "07:00"})
            ctx = {"who": {"id": uid}, "src": "web|p1", "private": True}
            out = asyncio.run(agent.tool("agent_change", {"plan": "Wochenüberblick", "action": "pause"}, ctx))
            self.assertIn("Noch NICHT geändert", out)
            self.assertFalse(agent.load(uid)["plans"][0]["paused"])
            no = asyncio.run(agent.answer(dict(ctx, own=True), "Nein"))
            self.assertIn("NICHT", no["system"])
            asyncio.run(agent.tool("agent_change", {"plan": "Wochenüberblick", "action": "pause"}, ctx))
            yes = asyncio.run(agent.answer(dict(ctx, own=True), "Ja"))
            self.assertIn("Pausiert", yes["system"])
            self.assertTrue(agent.load(uid)["plans"][0]["paused"])
            asyncio.run(aendern.undo(uid, aendern.last(uid), {}))
            self.assertFalse(agent.load(uid)["plans"][0]["paused"])
            asyncio.run(agent.tool("agent_change", {"plan": "Wochenüberblick", "action": "delete"}, ctx))
            asyncio.run(agent.answer(dict(ctx, own=True), "Ja"))
            self.assertEqual(agent.load(uid)["plans"], [])
            asyncio.run(aendern.undo(uid, aendern.last(uid), {}))
            self.assertEqual([x["id"] for x in agent.load(uid)["plans"]], [item["id"]])
        self.assertTrue(agent.PLAN_CHANGE.search("Pausiere den Plan mit dem Wetter"))
        self.assertFalse(agent.ASK.search("Was ist der Plan für heute"))


class Rules(unittest.TestCase):
    def test_delete_after_the_yes_and_restore(self):
        profile("Regina")
        uid = uid_of("Regina")
        rule = {"id": "r1", "conds": [{"name": "Haustür", "entity": "binary_sensor.haustuer", "op": "is", "value": "on"}]}
        proactive._save_rules(uid, [rule])
        ctx = {"who": {"id": uid}, "own": True, "src": "web|r1", "text": "Lösch die Regel für die Haustür"}
        with mock.patch.object(hamelden.features, "allowed", return_value=True):
            got = hamelden.offer(ctx)
            self.assertIn("home_rule_delete", got["changes"])
            out = asyncio.run(hamelden.tool("home_rule_delete", {"rule": "Haustür"}, ctx))
            self.assertIn("Noch NICHT gelöscht", out)
            self.assertEqual(len(proactive.rules(uid)), 1)
            asyncio.run(hamelden.answer(ctx, "Ja"))
            self.assertEqual(proactive.rules(uid), [])
            asyncio.run(aendern.undo(uid, aendern.last(uid), {}))
            self.assertEqual([r["id"] for r in proactive.rules(uid)], ["r1"])
            self.assertIn("keine Regel", asyncio.run(hamelden.tool("home_rule_delete", {"rule": "Garage"}, ctx)))


class PauseVolumeUndo(unittest.TestCase):
    def setUp(self):
        profile("Paulina")
        self.uid = uid_of("Paulina")

    def test_offered_only_with_the_switches_and_never_over_mcp(self):
        ctx = {"who": {"id": self.uid}, "own": True, "text": "Melde dich heute nicht mehr"}
        with mock.patch.object(aendern.features, "allowed", return_value=False):
            self.assertIsNone(aendern.offer(ctx))
        with mock.patch.object(aendern.features, "allowed", return_value=True):
            self.assertEqual([t["function"]["name"] for t in aendern.offer(ctx)["tools"]], ["proactive_pause"])
            self.assertIsNone(aendern.offer(dict(ctx, client="mcp")))
            self.assertIsNone(aendern.offer(dict(ctx, who=None)))
            self.assertIsNone(aendern.offer(dict(ctx, own=False)))
        for name in ("calendar_change", "agent_change", "home_rule_delete", "proactive_pause", "speaker_volume", "undo_last"):
            self.assertIn(name, mcpserver.NEVER)
            self.assertIn(name, taten.KIND)

    def test_pause_until_midnight_and_back(self):
        out = aendern.pause(self.uid, {"action": "pause", "hours": 3})
        self.assertIn("Done", out)
        self.assertGreater(proactive.state(self.uid)["pause_until"], 0)
        aendern.pause(self.uid, {"action": "resume"})
        self.assertEqual(proactive.state(self.uid)["pause_until"], 0)
        asyncio.run(aendern.undo(self.uid, aendern.last(self.uid), {}))   # the pause comes back
        self.assertGreater(proactive.state(self.uid)["pause_until"], 0)

    def test_volume_only_own_speakers(self):
        set_to = []

        async def fake_set(uid, did, v):
            set_to.append(v)
            return True
        with mock.patch.object(aendern, "my_speakers", return_value=[("d1", "c1", "Küche", 50), ("d2", "c2", "Bad", 30)]), \
                mock.patch.object(aendern, "set_volume", fake_set):
            self.assertIn("more than one", asyncio.run(aendern.volume(self.uid, {"change": "louder"})))
            self.assertIn("from 50 to 65", asyncio.run(aendern.volume(self.uid, {"speaker": "Küche", "change": "louder"})))
            self.assertIn("to 100", asyncio.run(aendern.volume(self.uid, {"speaker": "Bad", "change": "set", "level": 400})))
            asyncio.run(aendern.undo(self.uid, aendern.last(self.uid), {}))
        self.assertEqual(set_to, [65, 100, 30])
        with mock.patch.object(aendern, "my_speakers", return_value=[]):
            self.assertIn("no own speaker", asyncio.run(aendern.volume(self.uid, {"change": "quieter"})))

    def test_undo_a_reminder_only_after_the_yes(self):
        profiles.add_reminder(self.uid, "Müll rausbringen", int(DAY.timestamp() * 1000))
        aendern.note_tool(self.uid, "reminder_set", {"text": "Müll rausbringen"}, "Set: ...")
        ctx = {"who": {"id": self.uid}, "own": True, "src": "web|u1"}
        with mock.patch.object(aendern.features, "allowed", return_value=True):
            out = asyncio.run(aendern.tool("undo_last", {}, ctx))
        self.assertIn("Müll rausbringen", out)
        self.assertIn("Noch NICHT", out)
        self.assertEqual(len(profiles.reminders(self.uid)), 1)
        no = asyncio.run(aendern.answer(ctx, "Ja, aber erst morgen"))
        self.assertIn("NICHT", no["system"])
        self.assertEqual(len(profiles.reminders(self.uid)), 1)
        with mock.patch.object(aendern.features, "allowed", return_value=True):
            asyncio.run(aendern.tool("undo_last", {}, ctx))
        yes = asyncio.run(aendern.answer(ctx, "Ja"))
        self.assertIn("gelöscht", yes["system"])
        self.assertEqual(profiles.reminders(self.uid), [])

    def test_undo_off_by_default(self):
        import json
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["undo_voice"], False)
        self.assertNotIn("undo_voice", profiles.SETTINGS)      # the admin's switch holds for every profile


class Repeat(unittest.TestCase):
    def test_a_repeating_reminder_comes_back_at_its_clock_time(self):
        profile("Rita")
        uid = uid_of("Rita")
        mon = datetime.datetime(2031, 3, 3, 7, 0, tzinfo=ZONE)          # a Monday
        item = profiles.add_reminder(uid, "Müll", int(mon.timestamp() * 1000), "weekly")
        self.assertEqual(item["every"], "weekly")
        profiles.take_reminder(uid, item["id"], 10 ** 15)
        rest = profiles.reminders(uid)
        self.assertEqual(len(rest), 1)
        nxt = datetime.datetime.fromtimestamp(rest[0]["due"] / 1000, ZONE)
        self.assertEqual((nxt.date(), nxt.hour), (datetime.date(2031, 3, 10), 7))
        fri = datetime.datetime(2031, 3, 28, 8, 0, tzinfo=ZONE)          # Friday before the clocks change
        nxt = datetime.datetime.fromtimestamp(profiles.next_due({"due": fri.timestamp() * 1000, "every": "weekdays"},
                                                                "Europe/Berlin") / 1000, ZONE)
        self.assertEqual((nxt.date(), nxt.hour), (datetime.date(2031, 3, 31), 8))   # Monday, still 8 o'clock
        self.assertIsNone(profiles.next_due({"due": fri.timestamp() * 1000, "every": "hourly"}))
        profiles.remove_reminders(uid, {x["id"] for x in profiles.reminders(uid)})


class Groups(unittest.TestCase):
    def test_an_own_group_by_its_name(self):
        import chats
        metas = {"g1": {"kind": "group", "members": ["u1"], "name": "x"}, chats.ALL_ID: {"kind": "group", "members": ["u1"]},
                 "p1": {"kind": "priv", "members": ["u1"], "name": "y"}}
        names = {"g1": "Familie", "p1": "Familie"}
        with mock.patch.object(chats, "mine", return_value=metas), mock.patch.object(chats, "groups_on", return_value=True), \
                mock.patch.object(chats, "unseal", side_effect=lambda v, cid, k: names.get(cid, "")):
            self.assertEqual(messages.my_group("u1", "die Familiengruppe"), ("g1", "Familie"))
            self.assertEqual(messages.my_group("u1", "Familie"), ("g1", "Familie"))
            self.assertIsNone(messages.my_group("u1", "Fa"))
            self.assertIsNone(messages.my_group("u1", "Kollegen"))
        self.assertEqual(messages.describe({"kind": "group", "names": ["Familie"], "text": "Bin gleich da"}),
                         "Nachricht an die Gruppe „Familie“: „Bin gleich da“")


if __name__ == "__main__":
    unittest.main()
