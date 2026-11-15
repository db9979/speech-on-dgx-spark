"""Hinweis bei neuer Anmeldung (Nextcloud-Ideen 11, anmeldehinweis.py): a PIN login from a kind of browser new for
the profile sends one note to its devices.

- The login asks for the check (account.profile_login → anmeldehinweis.ask) with its own cookie value.
- Off (chat.login_notice, default off): never a note.
- The first login of a profile, and a kind already signed in, report nothing; a new kind reports with only the short
  kind and the way to Ich → Sicherheit, never an address.
- At most MAX_DAY notes per profile and day.
No wall clock: the day counter is the panel's own.
"""
import asyncio
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import account  # noqa: E402
import anmeldehinweis  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"


class Hinweis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = ADMIN.post("/api/admin/profiles", json={"name": "Anmelde Anke", "pin": "1234"})
        assert r.status_code in (200, 409), r.text

    def setUp(self):
        self.sent, self.asked = [], []
        self._send, self._ask = push.send, anmeldehinweis.ask

        async def send(uid, title, body, **kw):
            self.sent.append((uid, title, body, kw.get("tag")))
            return 1
        push.send = send
        anmeldehinweis.ask = lambda uid, raw, teile: self.asked.append((uid, raw)) or True
        helpers.set_config(login_notice=True)

    def tearDown(self):
        push.send, anmeldehinweis.ask = self._send, self._ask
        helpers.set_config(login_notice=False)

    def login(self, ua):
        c = TestClient(panel.app, headers={"user-agent": ua})
        r = c.post("/api/profile/login", json={"name": "Anmelde Anke", "pin": "1234"})
        self.assertEqual(r.status_code, 200, r.text)
        uid, raw = self.asked[-1]
        self.assertEqual(raw, c.cookies.get(profiles.COOKIE))
        return uid, raw

    def run_(self, uid, raw):
        return asyncio.run(anmeldehinweis.melden(uid, raw, account.ANMELDE_TEILE))

    def test_new_kind_reports_once_known_kind_not(self):
        uid, raw = self.login(MAC)
        profiles._drop_sessions(uid)          # start clean: no login yet
        uid, raw = self.login(MAC)
        self.assertEqual(self.run_(uid, raw), 0)             # the first login: nothing to compare
        uid, raw = self.login(MAC)
        self.assertEqual(self.run_(uid, raw), 0)             # the same kind again
        self.assertEqual(self.sent, [])
        uid, raw = self.login(WIN)
        self.assertEqual(self.run_(uid, raw), 1)
        (to, title, body, tag), = self.sent
        self.assertEqual((to, title, tag), (uid, "Neue Anmeldung", "login"))
        self.assertIn("Windows · Firefox", body)
        self.assertIn("Ich → Sicherheit", body)
        self.assertNotRegex(body, r"\d+\.\d+\.\d+\.\d+")    # never an address

    def test_off_never(self):
        helpers.set_config(login_notice=False)
        uid, raw = self.login(MAC)
        uid, raw = self.login(WIN)
        self.assertEqual(self.run_(uid, raw), 0)
        self.assertEqual(self.sent, [])

    def test_at_most_max_day(self):
        uid, raw = self.login(MAC)
        uid, raw = self.login(WIN)
        anmeldehinweis._count.today()["u:" + uid] = anmeldehinweis.MAX_DAY
        try:
            self.assertEqual(self.run_(uid, raw), 0)
            self.assertEqual(self.sent, [])
        finally:
            anmeldehinweis._count.today()["u:" + uid] = 0

    def test_unknown_login_nothing(self):
        self.assertEqual(anmeldehinweis.neu("kein-profil", "a.b.c.d", []), "")
        self.assertEqual(anmeldehinweis.neu("kein-profil", "kaputt", profiles.sessions("kein-profil")), "")


if __name__ == "__main__":
    unittest.main()
