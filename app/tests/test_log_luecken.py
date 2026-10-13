"""Every action that changes something outside the panel or says something to others writes a journal line for every
outcome, done, refused or failed (Dominik 2026-10-13: "wieso taucht eine Durchsage aus dem Chat nicht im Log auf?").
The lines carry fixed words and numbers only, never texts, entries or names, and land under a filter of Zustand →
Logs → Diagnose. The Durchsage itself is in test_messages.Speakers.test_every_announcement_writes_a_journal_line."""
import asyncio
import contextlib
import io
import unittest

from tests import helpers

helpers.start()
import calendars  # noqa: E402
import chats  # noqa: E402
import guard  # noqa: E402
import logfilter  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
import tasks  # noqa: E402
import tidy  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SECRET = "Geheimwort"   # in every text these tests hand over: it never reaches a line


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Lines(unittest.TestCase):
    def lines(self, do, name=""):
        """The journal lines do() prints; each one fixed words only (no secret word, no profile name)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                do()
            except Exception:
                pass
        got = out.getvalue().splitlines()
        for x in got:
            self.assertNotIn(SECRET, x)
            if name:
                self.assertNotIn(name, x)
        return got

    def area(self, got, start):
        hit = [x for x in got if x.startswith(start)]
        self.assertTrue(hit, (start, got))
        return [logfilter.parse(x)["area"] for x in hit]

    def notaus(self):
        """notaus.stop as while a Notaus holds every action off."""
        def stop(kind, uid=None):
            raise notaus.NotausAktiv("Notaus Stufe 2: aktion gesperrt")
        old = notaus.stop
        notaus.stop = stop
        self.addCleanup(setattr, notaus, "stop", old)


class Lists(Lines):
    def test_list_changes_done_refused_and_handed_over(self):
        _, uid = profile("Log-Lotte")
        got = self.lines(lambda: run(tasks.add(uid, "einkauf", [SECRET, "Brot"])), "Log-Lotte")
        self.assertEqual(self.area(got, "tasks: add einkauf | 2 entries"), ["listen"])
        have = run(tasks.items(uid, "einkauf"))
        got = self.lines(lambda: run(tasks.change(uid, "einkauf", have[:1], "delete")), "Log-Lotte")
        self.assertEqual(self.area(got, "tasks: delete einkauf | 1 entries"), ["listen"])
        got = self.lines(lambda: tasks.inbox(uid, "einkauf", True), "Log-Lotte")
        self.assertEqual(self.area(got, "tasks: 1 entries handed to the iPhone"), ["listen"])
        self.notaus()
        got = self.lines(lambda: run(tasks.add(uid, "einkauf", [SECRET])), "Log-Lotte")
        self.assertEqual(self.area(got, "tasks: add einkauf | refused notaus"), ["listen"])

    def test_reminders_played_deleted_and_dropped(self):
        a, uid = profile("Log-Ronja")
        profiles.add_reminder(uid, SECRET, 1000)
        rid = profiles.reminders(uid)[-1]["id"]
        got = self.lines(lambda: a.post("/api/profile/reminders/played", json={"id": rid}), "Log-Ronja")
        self.assertEqual(self.area(got, "reminders: one played on a device"), ["listen"])
        profiles.add_reminder(uid, SECRET, 1000)
        rid = profiles.reminders(uid)[-1]["id"]
        got = self.lines(lambda: a.delete(f"/api/profile/reminders/{rid}"), "Log-Ronja")
        self.assertEqual(self.area(got, "reminders: 1 deleted"), ["listen"])
        # pushed long after it was due (the panel was off): dropped, with a line
        profiles.add_reminder(uid, SECRET, 1000)
        old = push.reachable
        push.reachable = lambda u, private=True: u == uid
        self.addCleanup(setattr, push, "reachable", old)
        got = self.lines(lambda: run(push.due_reminders()), "Log-Ronja")
        self.assertEqual(self.area(got, "reminders: one dropped, more than 6 h overdue"), ["listen"])

    def test_calendar_entry_saved_or_not(self):
        _, uid = profile("Log-Carla")
        got = self.lines(lambda: run(calendars.add_event(uid, {"title": SECRET})), "Log-Carla")
        self.assertEqual(self.area(got, "calendar: appointment not saved (ValueError)"), ["listen"])
        self.notaus()
        got = self.lines(lambda: run(calendars.add_event(uid, {"title": SECRET})), "Log-Carla")
        self.assertEqual(self.area(got, "calendar: appointment refused, notaus"), ["listen"])


class Others(Lines):
    def test_notes_to_devices(self):
        _, uid = profile("Log-Nele")
        old = push._have
        push._have = lambda u, private=True: {k: False for k in push.WAYS}
        self.addCleanup(setattr, push, "_have", old)
        got = self.lines(lambda: run(push.send(uid, SECRET, SECRET, tag="agent")), "Log-Nele")
        self.assertEqual(self.area(got, "push: Auftrag reached no device | 0 device(s) | no way"), ["mitteilung"])
        self.assertEqual(push._word("pro-x", "frei erfunden"), "Von selbst")   # never a free word in the line

    def test_memory_saved_and_forgotten(self):
        _, uid = profile("Log-Mira")
        got = self.lines(lambda: profiles.remember(uid, SECRET), "Log-Mira")
        self.assertEqual(self.area(got, "gedaechtnis: fact saved | said"), ["gedaechtnis"])
        got = self.lines(lambda: profiles.forget(uid, text=SECRET), "Log-Mira")
        self.assertEqual(self.area(got, "gedaechtnis: 1 fact(s) forgotten"), ["gedaechtnis"])

    def test_confirmed_mail_action(self):
        _, uid = profile("Log-Malte")
        got = self.lines(lambda: tidy.carry_out(uid, {"kind": "draft", "aid": SECRET}), "Log-Malte")
        self.assertTrue(any(x.startswith("tidy: confirmed draft failed (") for x in got), got)
        self.notaus()
        got = self.lines(lambda: tidy.carry_out(uid, {"kind": "draft"}), "Log-Malte")
        self.assertEqual(self.area(got, "tidy: confirmed draft refused, notaus"), ["mail"])

    def test_chat_refusals(self):
        a, uid = profile("Log-Cleo")
        helpers.set_config(chats=True)
        self.addCleanup(helpers.set_config, chats=False)
        a.put("/api/profile/settings", json={"chats_on": True})
        got = self.lines(lambda: a.post("/api/chats/send", json={"id": "c" + "0" * 12, "text": SECRET}), "Log-Cleo")
        self.assertEqual(self.area(got, "chats: refused | why not found | http 404"), ["nachrichten"])
        self.assertIsNotNone(chats._err(PermissionError(SECRET)))

    def test_every_tool_call(self):
        a, uid = profile("Log-Tilda")
        helpers.set_config(tasks=True)
        self.addCleanup(helpers.set_config, tasks=False)
        a.put("/api/profile/settings", json={"tasks_on": True})
        got = self.lines(lambda: a.post("/api/chat", json={"messages": [{"role": "user", "content":
                         'TOOL tasks_add {"list": "einkauf", "items": ["' + SECRET + '"]}'}], "convo": "t1"}), "Log-Tilda")
        self.assertEqual(self.area(got, "chat: tool tasks_add ok |"), ["werkzeug"])

    def test_change_log_has_the_chats_settings_not_the_writing(self):
        for path in ("/api/chats/announce", "/api/chats/group", "/api/chats/members", "/api/chats/leave",
                     "/api/chats/invite", "/api/chats/keys", "/api/chats/private", "/api/chats/who", "/api/chats/call"):
            self.assertTrue(guard.logged(path, "POST"), path)
        for path in ("/api/chat", "/api/chat/rate", "/api/chats/send", "/api/chats/read", "/api/chats/typing",
                     "/api/chats/react", "/api/chats/edit", "/api/chats/find", "/api/chats/media", "/api/chats/open"):
            self.assertFalse(guard.logged(path, "POST"), path)


if __name__ == "__main__":
    unittest.main()
