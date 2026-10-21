"""Bestätigungscodes (mailcode.py, Dominik 2026-10-21 „5“): a new mail with a confirmation code becomes a note on the
device in use, with „Code kopieren“.

- Fixed rules find the code (WORDS near CODE), never a voucher, an order or a tracking number, never a year.
- Only an unread mail at most AGE seconds old, one note per mail, at most PER_HOUR an hour.
- Never Telegram: with Telegram as the device in use the note goes to another way, with none there is no note.
- Off (admin switch, or without „Neue Mails sofort“), blocked profile, Mein Notaus: nothing.
- The code is never in a log line and never on Live; the profile with the function keeps its IDLE connection.

Mail and push are stand-ins; no wall clock, no network.
"""
import contextlib
import datetime
import email
import email.policy
import io
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import mailcode  # noqa: E402
import mailidle  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})

NOW = 1_800_000_000.0


def head(subject, ago=60, unread=True, frm="GitHub <noreply@github.com>"):
    return {"subject": subject, "from": frm, "unread": unread,
            "date": datetime.datetime.fromtimestamp(NOW - ago, datetime.timezone.utc)}


def body(text):
    return email.message_from_bytes(f"Subject: x\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{text}\r\n".encode(),
                                    policy=email.policy.default)


class Find(unittest.TestCase):
    def test_codes_found(self):
        for subject, text, want in (
                ("482913 ist dein Bestätigungscode", "", "482913"),
                ("Dein Anmeldecode", "Hallo,\n\ndein Code lautet: 731 204\n\nGültig 10 Minuten.", "731204"),
                ("Sign in to GitHub", "Your verification code is\n\n  K7Q2ZP\n\nIt expires soon.", "K7Q2ZP"),
                ("Sign in", "Your one-time password: 5521", "5521"),
                ("Sicherheit", "Ihre TAN: 04419928", "04419928"),
                ("", "Code: 8812", "8812")):
            self.assertEqual(mailcode.find(subject, text), want, (subject, text))

    def test_no_code(self):
        for subject, text in (
                ("Dein Gutscheincode 123456", ""),
                ("Rabattcode für dich", "Code SOMMER2026 spart 10 %"),
                ("Bestellung 4711", "Deine Bestellnummer 99887766, Code folgt"),
                ("Sendung", "Tracking-Code 123456789"),
                ("Code of conduct", "Stand 2026"),
                ("Code", "Die Zahl steht weit weg vom Wort, ganz weit weg, viel weiter als achtzig Zeichen, wirklich: 482913"),
                ("Treffen", "Ruf mich an: 0711 123456"),
                ("Code", "Betrag 12.345,00 €")):
            self.assertEqual(mailcode.find(subject, text), "", (subject, text))


class Arrived(unittest.TestCase):
    def setUp(self):
        r = ADMIN.post("/api/admin/profiles", json={"name": "Code Conni", "pin": "1234"})
        assert r.status_code in (200, 409), r.text
        c = TestClient(panel.app)
        assert c.post("/api/profile/login", json={"name": "Code Conni", "pin": "1234"}).status_code == 200
        self.uid = c.get("/api/whoami").json()["profile"]["id"]
        mailcode._said.clear()
        mailcode._hour.clear()
        self.sent = []

    def run_it(self, found, texts=None, way=("app", []), have=None, allowed=True, blocked=False):
        async def send(uid, title, body, **kw):
            self.sent.append((title, body, kw))
            return 1
        have = have or {"app": True, "and": False, "desk": False, "tg": True, "web": False}
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(mailcode.features, "allowed", side_effect=lambda k, u: allowed), \
                mock.patch.object(mailcode.notaus, "blocks", return_value=blocked), \
                mock.patch("mail.find", return_value=(found, 0, 0)), \
                mock.patch("mail.message", side_effect=lambda u, ref: body((texts or {}).get(ref, ""))), \
                mock.patch("mail.known", side_effect=lambda u, f: f), \
                mock.patch("push.pick", return_value=way), mock.patch("push._have", return_value=have), \
                mock.patch("push.send", side_effect=send):
            n = mailcode.arrived(self.uid, NOW)
        return n, out.getvalue()

    def test_note_with_the_code_never_logged(self):
        found = [("m1", 1, head("482913 ist dein Bestätigungscode")), ("m1", 2, head("Dein Login")),
                 ("m1", 3, head("Newsletter"))]
        n, log = self.run_it(found, {"m1:2": "Login-Code: 731204"})
        self.assertEqual(n, 2)
        self.assertEqual([(t, b) for t, b, _ in self.sent], [("Bestätigungscode", "482913 · GitHub"),
                                                              ("Bestätigungscode", "731204 · GitHub")])
        self.assertEqual({(kw["tag"], kw["to"]) for _, _, kw in self.sent}, {("mailcode", "app")})
        self.assertIn("mail: code looked | 3 new, 2 notes", log)
        for secret in ("482913", "731204", "GitHub"):
            self.assertNotIn(secret, log)
        self.assertEqual(self.run_it(found)[0], 0)                              # once per mail
        self.assertTrue(mailcode.COPY.fullmatch("482913") and mailcode.COPY.fullmatch("K7Q2ZP"))

    def test_only_new_unread(self):
        found = [("m1", 1, head("482913 ist dein Code", ago=mailcode.AGE + 1)),
                 ("m1", 2, head("731204 ist dein Code", unread=False))]
        self.assertEqual(self.run_it(found)[0], 0)
        self.assertEqual(self.sent, [])

    def test_never_telegram(self):
        found = [("m1", 1, head("482913 ist dein Code"))]
        have = {"app": False, "and": False, "desk": True, "tg": True, "web": False}
        self.assertEqual(self.run_it(found, way=("tg", []), have=have)[0], 1)
        self.assertEqual(self.sent[0][2]["to"], "desk")                         # the other way, not Telegram
        mailcode._said.clear()
        self.sent.clear()
        have = {"app": False, "and": False, "desk": False, "tg": True, "web": False}
        n, log = self.run_it(found, way=("tg", []), have=have)
        self.assertEqual((n, self.sent), (0, []))
        self.assertIn("mail: code no device", log)

    def test_off_blocked_notaus_and_limit(self):
        found = [("m1", 1, head("482913 ist dein Code"))]
        self.assertEqual(self.run_it(found, allowed=False)[0], 0)
        self.assertEqual(self.run_it(found, blocked=True)[0], 0)
        self.assertEqual(self.sent, [])
        many = [("m1", i, head(f"{100000 + i} ist dein Code")) for i in range(mailcode.PER_HOUR + 1)]
        n = sum(self.run_it(many[k:k + mailcode.LOOK_MAX])[0] for k in range(0, len(many), mailcode.LOOK_MAX))
        self.assertEqual(n, mailcode.PER_HOUR)

    def test_idle_for_active_profiles_and_live(self):
        with mock.patch.dict(profiles.LAST_USED, {self.uid: ("app", "", NOW - 60)}), \
                mock.patch.object(mailcode.features, "allowed", return_value=True):
            self.assertEqual(mailcode.wants_idle(self.uid, NOW), NOW - 60)
            self.assertEqual(mailcode.wants_idle(self.uid, NOW + mailidle.ACTIVE_SECONDS + 61), 0)
        with mock.patch.dict(profiles.LAST_USED, {self.uid: ("app", "", NOW - 60)}), \
                mock.patch.object(mailcode.features, "allowed", return_value=False):
            self.assertEqual(mailcode.wants_idle(self.uid, NOW), 0)
        self.assertEqual(set(mailcode.for_live()), {"on", "today"})
        self.assertIn(mailcode.arrived, mailidle.LISTENERS)


if __name__ == "__main__":
    unittest.main()
