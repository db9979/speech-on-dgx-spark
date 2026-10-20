"""Every action that changes something outside the panel or says something to others writes a journal line for every
outcome, done, refused or failed (Dominik 2026-10-13: "wieso taucht eine Durchsage aus dem Chat nicht im Log auf?").
The lines carry fixed words and numbers only, never texts, entries or names, and land under a filter of Zustand →
Logs → Diagnose. The Durchsage itself is in test_messages.Speakers.test_every_announcement_writes_a_journal_line."""
import ast
import asyncio
import contextlib
import glob
import io
import os
import re
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


PANEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel")
# prints whose line a helper builds (the helper's own words start with an area) or that go to a console, not the journal
PRINT_OK = {
    ("chat.py", "watch_report"): "watch.report_line baut „watch: …“",
    ("chat_turn.py", "prepare"): "lokal.log_line baut „wissen: …“ bzw. „lokal: …“",
    ("lokal.py", "run"): "log_line baut „wissen: …“",
    ("panel.py", "slow_reads"): "slow_read baut „seite: slow GET …“",
    ("tracelog.py", "finish"): "line() baut „anfrage: …“",
    ("logfilter.py", "detail"): "ausführliche Zeile „<bereich>: detail …“ eines festen Bereichs",
    ("notzugang.py", "main"): "Konsole von „speech-spark notzugang“, nicht das Journal",
    ("wartung.py", "<module>"): "Konsole von „speech-spark pause|weiter“, nicht das Journal",
    ("hilfe.py", "<module>"): "Konsole von „hilfe.py --docs“",
    ("werkzeuge.py", "<module>"): "Konsole von „werkzeuge.py --write“",
}
# functions behind a Notaus gate that write no line themselves, each with where its line comes from
ACTION_OK = {
    ("postfach.py", "_act"): "act schreibt „mail: page <aktion> done|refused|failed“ für jedes Ergebnis",
    ("postfach.py", "_act_many"): "act_many schreibt über _outcome „mail: page many <aktion> done|refused|failed“ für jedes Ergebnis",
    ("postfach.py", "_back_many"): "back_many schreibt über _outcome „mail: page many back done|refused|failed“ für jedes Ergebnis",
    ("postfach.py", "_folder_op"): "folder_op schreibt „mail: folder <aktion> done|refused|failed“ für jedes Ergebnis",
    ("halive.py", "wanted"): "liest nur, wer eine Live-Verbindung zu Home Assistant bekommt; look schreibt „homeassistant: live looked …“, der Thread jede Verbindung, jeden Verlust und jedes Ende",
    ("mailidle.py", "wanted"): "liest nur, wer eine IDLE-Verbindung bekommt; look schreibt „mail: idle looked …“, der Thread jede Öffnung und jedes Ende",
    ("musik.py", "_guard"): "prüft nur vor start_edit und tone; jede Absage schreibt _say „musik: nicht gestartet <grund> fuer …“, die Änderung selbst schreiben start_edit und tone",
    ("saetze.py", "start"): "liest nur und gibt drei feste Sätze zurück, nichts geschieht; die Notaus-Frage hält nur Vorschläge zurück",
    ("aendern.py", "set_volume"): "volume schreibt „aendern: lautstaerke …“, das Rückgängig answer seine Zeile",
    ("aendern.py", "undo"): "answer schreibt „aendern: rueckgaengig … ok|fehler“",
    ("begleiter.py", "asked"): "startet begleiter.check, das seine Zeile schreibt",
    ("begleiter.py", "_send_tool"): "ein Werkzeug: chat.run_tool schreibt „chat: tool pc_send …“",
    ("berater.py", "feedback"): "proactive.deliver schreibt die Zeile",
    ("berater.py", "_notify"): "proactive.deliver schreibt die Zeile",
    ("berater.py", "_tell_admins"): "proactive.deliver schreibt die Zeile",
    ("calendars.py", "_add_event"): "add_event schreibt für jedes Ergebnis die Zeile",
    ("calendars.py", "_change_event"): "change_event schreibt für jedes Ergebnis die Zeile",
    ("calendars.py", "delete_href"): "nur über aendern.undo; answer schreibt die Zeile",
    ("calendars.py", "put_ics"): "nur über aendern.undo; answer schreibt die Zeile",
    ("dienstwacht.py", "round_once"): "Ausfall und Entwarnung über live.event (ereignis: Dienste …)",
    ("docmake.py", "_can_start"): "nur eine Prüfung; Auftrag und Senden schreiben ihre Zeilen",
    ("geraeteupdate.py", "tick"): "check_all schreibt über live.job",
    ("naszustand.py", "_paused"): "nur eine Prüfung; read_once schreibt „naszustand: gelesen …“ oder „… fehlgeschlagen“",
    ("mcpserver.py", "carry_out"): "decide schreibt guard.log und „mcp-server: confirmed action …“",
    ("netguard.py", "allowed"): "nur eine Prüfung; der Wächter loggt die Ablehnung selbst",
    ("proactive.py", "blocked"): "nur eine Prüfung; deliver loggt „not said (Grund)“",
    ("tasks.py", "_add"): "add schreibt für jedes Ergebnis die Zeile",
    ("tasks.py", "_change"): "change schreibt für jedes Ergebnis die Zeile",
    ("tidy.py", "_carry_out"): "carry_out schreibt für jedes Ergebnis die Zeile",
    ("tidy.py", "append_doc"): "Teil von docmake-Senden und carry_out, die ihre Zeile schreiben",
    ("tidy.py", "append_draft"): "Teil von make_draft (carry_out, docmake), die ihre Zeile schreiben",
    ("tipps.py", "_quiet"): "nur eine Prüfung",
    ("tipps.py", "weekly_text"): "proactive.check_tips sagt den Tipp über deliver (Zeile dort)",
}
LOGS = re.compile(r"^(print|_?log\w*|\w*_log|_live\w*|_journal)$")


def _lead(a):
    """The fixed start of a print's first argument ("{}" for each placeholder), or None for an expression."""
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return a.value
    if isinstance(a, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in a.values)
    if isinstance(a, ast.BinOp) and isinstance(a.op, ast.Add):
        return _lead(a.left)
    if isinstance(a, ast.Subscript):
        return _lead(a.value)
    return None


# What people say or write, what a foreign server answers, a raw profile id: never in a journal line (only how long it
# is, via len, or the profile via profiles.log_name). A print may name such a variable only with a reason here.
CONTENT = {"text", "msg", "message", "line", "title", "query", "prompt", "answer", "reply", "body", "content", "command",
           "words", "said", "q", "utterance", "transcript", "latest", "uid", "ha_direct", "ask", "ask0", "question", "spoken",
           "heard", "note", "fact", "subject"}
CONTENT_SAFE = {"len", "log_name", "_log_name", "_who", "type", "bool", "int", "round", "sum", "_word"}
CONTENT_OK = {
    ("chat.py", "body"): "watch.report_line schreibt aus body nur Zahlen und feste Wörter (OUTCOMES)",
    ("faelle.py", "said"): "Titel des Melders aus festen Regeln, auf Buchstaben und Zahlen gekürzt, höchstens 100 Zeichen",
    ("wartung.py", "line"): "Antwort von „speech-spark pause|weiter“ auf der Konsole, feste Sätze mit Teilen und Minuten",
    ("live.py", "text"): "Live-Ereignisse tragen nur Art, Anzahl und Status (Grundsatz 6), nie Inhalte",
    ("logfilter.py", "text"): "Ausführliches Log, nur nach Einschalten durch den Admin und durch redact gefiltert",
    ("offsite.py", "msg"): "eigene Fehlertexte der Sicherung (HTTP-Code, Ordner), kein Inhalt",
    ("panel.py", "line"): "slow_read baut die Zeile aus Methode, Route und Zeit",
    ("tasks.py", "uid"): "tasks._log macht daraus profiles.log_name",
    ("tracelog.py", "line"): "line() baut die Anfrage-Zeile aus festen Feldern",
}


def _content(x):
    """The first content variable a log argument shows as it is, or None."""
    if isinstance(x, ast.Call):
        f = x.func
        if (f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "") in CONTENT_SAFE:
            return None
    if isinstance(x, ast.Compare):     # only yes or no ends up in the line
        return None
    if isinstance(x, ast.IfExp):       # the condition picks a fixed word; what is shown are the two branches
        return _content(x.body) or _content(x.orelse)
    if isinstance(x, ast.Name) and x.id in CONTENT:
        return x.id
    if isinstance(x, ast.Attribute) and x.attr in ("text", "uid"):
        return x.attr
    for c in ast.iter_child_nodes(x):
        got = _content(c)
        if got:
            return got
    return None


def _files():
    for path in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
        with open(path, encoding="utf-8") as f:
            yield os.path.basename(path), ast.parse(f.read())


class Structure(unittest.TestCase):
    """Dominik 2026-10-13: „alles neues immer im log mit aufnehmen“. These fail for a new line or action that
    does not fit, without anyone having to remember it."""

    def test_every_journal_line_has_an_area(self):
        """Every print of the panel starts with a word of logfilter.AREAS, so it shows under a filter of Zustand →
        Logs → Diagnose. A new word goes into an area in the same commit."""
        bad = []

        class V(ast.NodeVisitor):
            def __init__(self, name):
                self.name, self.stack = name, []

            def visit_FunctionDef(self, n):
                self.stack.append(n.name)
                self.generic_visit(n)
                self.stack.pop()
            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, n):
                if isinstance(n.func, ast.Name) and n.func.id == "print" and n.args:
                    where = (self.name, self.stack[-1] if self.stack else "<module>")
                    lead = _lead(n.args[0])
                    if where not in PRINT_OK and (lead is None or not logfilter.parse(lead.replace("{}", "x"))["area"]):
                        bad.append(f"{self.name}:{n.lineno} {(lead or '<Ausdruck>')[:40]!r}")
                self.generic_visit(n)
        for name, tree in _files():
            V(name).visit(tree)
        self.assertEqual(bad, [], "Zeilen ohne Bereich in logfilter.AREAS")

    def test_every_action_writes_a_line(self):
        """A function behind a Notaus gate (notaus.stop/refuse/blocks) does something: it writes a journal line
        (print, a _log or _live helper, live.mark/event/job/note/begin), is an endpoint (the change log has it) or
        says in ACTION_OK where its line comes from."""
        bad = []
        for name, tree in _files():
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or (name, fn.name) in ACTION_OK:
                    continue
                if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name)
                       and d.func.value.id in ("router", "app") for d in fn.decorator_list):
                    continue
                gate = logs = False
                for n in ast.walk(fn):
                    if not isinstance(n, ast.Call):
                        continue
                    f = n.func
                    owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
                    word = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                    gate = gate or (owner == "notaus" and word in ("stop", "refuse", "blocks"))
                    logs = logs or bool(LOGS.match(word)) or (owner == "live" and word in ("mark", "event", "job", "note", "begin"))
                if gate and not logs:
                    bad.append(f"{name}:{fn.lineno} {fn.name}")
        self.assertEqual(bad, [], "Aktionen ohne Log-Zeile (oder Grund in ACTION_OK)")
        for (name, fn), why in ACTION_OK.items():
            self.assertTrue(os.path.exists(os.path.join(PANEL, name)) and why, name)

    def test_quiet_paths_have_a_reason(self):
        """Every path the change log leaves out has its reason (guard.QUIET_WHY); a prefix never swallows a whole
        family of other paths again (the Durchsage under /api/chats/)."""
        self.assertEqual(set(guard.QUIET), set(guard.QUIET_WHY))
        for path, why in guard.QUIET_WHY.items():
            self.assertTrue(path.startswith("/api/") and len(why) > 5, path)
        self.assertTrue(guard.logged("/api/chats/announce", "POST"))

    def test_no_content_in_journal_lines(self):
        """Logs only with fixed words and numbers (Grundsatz 7): no print, and no _log helper that prints, shows what
        was said, a foreign server's answer or a raw profile id; a new one turns this red."""
        bad = []
        for name, tree in _files():
            helpers_ = {"print"} | {fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
                                    and fn.name.startswith("_log") and any(isinstance(n, ast.Call) and
                                    isinstance(n.func, ast.Name) and n.func.id == "print" for n in ast.walk(fn))}
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in helpers_:
                    hit = next(filter(None, (_content(a) for a in n.args)), None)
                    if hit and (name, hit) not in CONTENT_OK:
                        bad.append(f"{name}:{n.lineno} {hit}")
        self.assertEqual(bad, [], "Logzeilen mit Inhalt statt festen Wörtern (oder Grund in CONTENT_OK)")
        for (name, _), why in CONTENT_OK.items():
            self.assertTrue(os.path.exists(os.path.join(PANEL, name)) and why, name)

    def test_live_events_are_in_the_journal(self):
        """What Zustand → Live shows under Ereignisse is in the journal too, whether Live is on or not."""
        import live
        got = Lines.lines(self, lambda: (live.mark("Chats", "Durchsage auf 1 Lautsprecher"),
                                        live.event("Notaus", "Stufe 1")))
        self.assertIn("ereignis: Chats | Durchsage auf 1 Lautsprecher", got)
        self.assertIn("ereignis: Notaus | Stufe 1", got)
        self.assertEqual({logfilter.parse(x)["area"] for x in got}, {"ereignis"})


if __name__ == "__main__":
    unittest.main()
