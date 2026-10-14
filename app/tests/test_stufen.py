"""Wann fragt der Spark nach dem Code? (stufen.py, V01.0.427, plan plaene/zweiter-faktor-einheitlich.md): every
route that asks for a code is in the one list with the level its code says, the list decides whether a code from
the last minutes counts, the 428 answer says whose code and what for, and the panel password uses the second
step of the main admin's profile (one code per person) without ever losing its own."""
import base64
import glob
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import coadmin  # noqa: E402
import core  # noqa: E402
import guard  # noqa: E402
import iphone  # noqa: E402
import mfa  # noqa: E402
import panel  # noqa: E402
import stufen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import profile, uid_of  # noqa: E402
from tests.test_zweiter_schritt import fake_second_step  # noqa: E402

CODE = {"X-Speech-Code": "123456"}
ROUTE = re.compile(r'@(?:router|app)\.(get|post|put|delete|patch)\("([^"]*)"[^\n]*\n((?:@[^\n]*\n)*)'
                   r'(?:async )?def (\w+)\((.*?)\):\n', re.S)
NEXT = re.compile(r"\n(?=@|def |async def |class |\S)")


def asked():
    """{(method, route): level} of every route that asks for a code, read from the sources."""
    out = {}
    for f in glob.glob(os.path.join(helpers.APP, "panel", "*.py")):
        with open(f) as fh:
            text = fh.read()
        for m in ROUTE.finditer(text):
            rest = text[m.end():]
            n = NEXT.search(rest)
            body, head = rest[:n.start() if n else len(rest)], text[m.start():m.end()]
            lv = {stufen.PROTECT if d.endswith("_fresh") else stufen.CONFIRM
                  for d in re.findall(r"Depends\((admin_code_fresh|admin_code|secret_profile_fresh|secret_profile)\)", head)}
            lv |= {stufen.PROTECT if d.endswith("_fresh") else stufen.CONFIRM
                   for d in re.findall(r"await (?:core\.)?(admin_code_fresh|admin_code|secret_profile_fresh|secret_profile)\(", body)}
            lv |= {stufen.PROTECT if "True" in c else stufen.CONFIRM for c in re.findall(r"confirm_code\(([^\n]*)", body)}
            if lv:
                out[(m.group(1).upper(), m.group(2))] = stufen.PROTECT if stufen.PROTECT in lv else stufen.CONFIRM
    return out


def confirm_header(r):
    raw = r.headers.get("X-Speech-Confirm", "")
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))) if raw else None


class List(unittest.TestCase):
    def test_every_code_route_is_listed_with_its_level(self):
        found = asked()
        self.assertGreater(len(found), 60)
        self.assertEqual(sorted(set(found) - set(stufen.LIST)), [], "routes that ask for a code: add them to stufen.LIST")
        self.assertEqual(sorted(set(stufen.LIST) - set(found)), [], "stufen.LIST names routes that ask for no code")
        wrong = sorted(k for k in found if stufen.LIST[k][0] != found[k])
        self.assertEqual(wrong, [], "the code's level (…_fresh / fresh=True) and stufen.LIST disagree")

    def test_entries_are_complete(self):
        for k, (lvl, area, de, en) in stufen.LIST.items():
            self.assertIn(lvl, (stufen.CONFIRM, stufen.PROTECT), k)
            self.assertTrue(area and de and en, k)
        o = stufen.overview()
        self.assertIn("Konten", o[stufen.CONFIRM])
        self.assertIn("Schutz", o[stufen.PROTECT])
        self.assertNotIn("/api", json.dumps(o))          # the page shows what, never routes

    def test_the_protection_itself_always_asks(self):
        for k in (("POST", "/api/password"), ("POST", "/api/profile/mfa/disable"), ("PUT", "/api/admin/roles"),
                  ("POST", "/api/backups/{name}/restore"), ("PUT", "/api/admin/roles/{uid}"), ("POST", "/api/iphone/update"),
                  ("POST", "/api/profile/mfa/passkeys/begin"), ("PUT", "/api/profile/homeassistant/code")):
            self.assertEqual(stufen.LIST[k][0], stufen.PROTECT, k)


class Dialog(unittest.TestCase):
    def setUp(self):
        guard.reset()
        core._windows.clear()
        helpers.set_config(iphone=True)
        iphone._pending.clear()
        self.c = profile("StufenSina")
        self.uid = uid_of("StufenSina")
        fake_second_step(self.uid)
        self.real = mfa.verify
        mfa.verify = lambda who, code: code == "123456"

    def tearDown(self):
        mfa.verify = self.real
        mfa.disable(self.uid)
        helpers.set_config(iphone=False)
        core._windows.clear()
        guard.reset()

    def test_says_whose_code_what_for_and_how_long(self):
        self.c.put("/api/profile/settings", json={"app_on": True})
        body = {"base": "https://speech.example.de"}
        r = self.c.post("/api/profile/iphone/pair", json=body)
        self.assertEqual(r.status_code, 428)
        self.assertEqual(confirm_header(r), {"level": "confirm", "who": "StufenSina", "what": "iPhone koppeln", "what_en": "Pair an iPhone"})
        self.assertEqual(self.c.post("/api/profile/iphone/pair", json=body, headers=CODE).status_code, 200)
        # "Bestätigen": the code counts for a while in this login
        self.assertEqual(self.c.post("/api/profile/iphone/pair", json=body).status_code, 200)
        # "Schutz ändern": asked again, and the dialog says so
        r = self.c.post("/api/profile/mfa/recovery")
        self.assertEqual(r.status_code, 428)
        self.assertEqual(confirm_header(r)["level"], "protect")
        self.assertEqual(confirm_header(r)["what"], "Neue Wiederherstellungscodes")


class OneCodePerPerson(unittest.TestCase):
    """The panel password (emergency access) and the main admin's profile: one second step, the profile's."""
    def setUp(self):
        guard.reset()
        core._windows.clear()
        self.real = mfa.verify
        self.c = profile("StufenOtto")                  # (before the admin's step: it signs the admin's login)
        self.uid = uid_of("StufenOtto")
        fake_second_step(mfa.ADMIN)                     # the admin's own step, before any link
        fake_second_step(self.uid)
        self.own = mfa._load(mfa._own_path(mfa.ADMIN))

    def tearDown(self):
        mfa.verify = self.real
        try:
            os.remove(coadmin.FILE)
        except OSError:
            pass
        for p in (mfa._own_path(mfa.ADMIN), mfa._own_path(self.uid)):
            try:
                os.remove(p)
            except OSError:
                pass
        core._windows.clear()
        guard.reset()

    def test_password_uses_the_owner_profiles_code(self):
        self.assertIsNone(mfa.linked())                 # no Haupt-Admin yet: the admin's own step
        coadmin.set_role(self.uid, "admin")             # the first admin the password gives: the main one
        self.assertEqual(mfa.linked(), self.uid)
        used = []
        mfa.verify = lambda who, code: used.append(mfa._path(who)) or code == "123456"
        a = TestClient(panel.app)
        r = a.post("/api/login", json={"password": "secret-admin"}).json()
        self.assertTrue(r.get("code"))
        self.assertEqual(a.post("/api/login", json={"password": "secret-admin", "code": "123456"}).status_code, 200)
        self.assertEqual(used, [mfa._own_path(self.uid)])   # the profile's secret, not the admin's file
        self.assertEqual(core.code_name(mfa.ADMIN, guard.ADMIN), "StufenOtto")
        # the step itself is changed only in the profile, never through the emergency access
        for path in ("/api/mfa/setup", "/api/mfa/disable", "/api/mfa/recovery", "/api/mfa/passkeys/begin"):
            r = a.post(path, headers=CODE)
            self.assertEqual(r.status_code, 409, path)
            self.assertIn("StufenOtto", r.json()["detail"])
        self.assertEqual(a.get("/api/mfa").json()["linked"], "StufenOtto")
        # the admin's own file stays as it was and counts again when the role goes
        self.assertEqual(mfa._load(mfa._own_path(mfa.ADMIN)), self.own)
        coadmin.set_role(self.uid, "")
        self.assertIsNone(mfa.linked())
        self.assertTrue(mfa.enabled(mfa.ADMIN))
        self.assertEqual(core.code_name(mfa.ADMIN, guard.ADMIN), "Notzugang")

    def test_never_without_a_second_step(self):
        coadmin.set_role(self.uid, "admin")
        mfa.disable(self.uid)                           # the profile switches its step off
        self.assertIsNone(mfa.linked())
        self.assertTrue(mfa.enabled(mfa.ADMIN))         # the admin's own step again
        fake_second_step(self.uid)
        coadmin.unlink_main()                           # unlinked (sudo speech-spark notzugang): the admin's own step
        self.assertIsNone(mfa.linked())
        self.assertEqual(mfa._path(mfa.ADMIN), mfa._own_path(mfa.ADMIN))


class LoginAsAdmin(unittest.TestCase):
    """Since V01.0.541 (no admin mode): the code typed for the login makes a profile with a role admin at once,
    never without the second step."""
    def setUp(self):
        self.real = (mfa.enabled, mfa.verify)
        self.on = {mfa.ADMIN}
        mfa.enabled = lambda who: who in self.on
        mfa.verify = lambda who, code: who in self.on and code == "123456"
        guard.reset()

    def tearDown(self):
        mfa.enabled, mfa.verify = self.real
        try:
            os.remove(coadmin.FILE)
        except OSError:
            pass
        guard.reset()

    def login(self, c, **more):
        return c.post("/api/profile/login", json=dict({"name": "StufenAda", "pin": "1234"}, **more))

    def test_one_code_for_both(self):
        profile("StufenAda")
        uid = uid_of("StufenAda")
        self.on.add(uid)
        fake_second_step(uid)                                   # its mark goes into the login
        self.addCleanup(lambda: os.path.exists(mfa._own_path(uid)) and os.remove(mfa._own_path(uid)))
        c = TestClient(panel.app)
        self.assertEqual(self.login(c, code="123456").json(), {"ok": True})     # no role: only the profile
        coadmin.set_role(uid, "admin")
        self.assertEqual(self.login(c).json(), {"code": True})
        r = self.login(c, code="123456")
        self.assertEqual(r.json(), {"ok": True, "admin": True})
        self.assertEqual(c.get("/api/whoami").json()["admin_by"], "admin")
        # a wrong code opens nothing, and without the second step the role never counts
        e = TestClient(panel.app)
        self.assertEqual(self.login(e, code="000000").status_code, 401)
        self.on.discard(uid)
        f = TestClient(panel.app)
        self.assertEqual(self.login(f).json(), {"ok": True})
        self.assertFalse(f.get("/api/whoami").json().get("admin"))


if __name__ == "__main__":
    unittest.main()
