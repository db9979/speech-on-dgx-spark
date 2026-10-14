"""sudo speech-spark notzugang (notzugang.py, V01.0.439): locked out after an update, the Spark's own shell gives a new
panel password, moves the emergency access's second step aside, ends the link to the main admin profile's code and
says so in the change log and to the admins. Never reachable from the panel."""
import asyncio
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
import mfa  # noqa: E402
import notzugang  # noqa: E402
import panel  # noqa: E402
import push  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import profile, uid_of  # noqa: E402
from tests.test_zweiter_schritt import fake_second_step  # noqa: E402


class Notzugang(unittest.TestCase):
    def setUp(self):
        guard.reset()
        try:
            with open(core.PASSWORD_FILE) as f:
                self.pw = f.read()
        except OSError:
            self.pw = None
        profile("NotOtto")                              # (before the admin's step: it signs the admin's login)
        self.uid = uid_of("NotOtto")
        fake_second_step(mfa.ADMIN)
        fake_second_step(self.uid)
        coadmin.set_role(self.uid, "admin")             # the first admin the password gives: the main one
        self.sent = []

        async def send(uid, title, body, **kw):
            self.sent.append((uid, body, kw))
            return 1
        self.real = push.send
        push.send = send

    def tearDown(self):
        push.send = self.real
        if self.pw is None:
            if os.path.exists(core.PASSWORD_FILE):
                os.remove(core.PASSWORD_FILE)
        else:
            with open(core.PASSWORD_FILE, "w") as f:
                f.write(self.pw)
        for p in [coadmin.FILE, mfa._own_path(mfa.ADMIN), mfa._own_path(self.uid)] + \
                glob.glob(mfa._own_path(mfa.ADMIN) + ".*.bak"):
            try:
                os.remove(p)
            except OSError:
                pass
        guard.reset()

    def test_back_in_with_the_new_password_only(self):
        self.assertEqual(mfa.linked(), self.uid)
        password, done = notzugang.reset(now=1_800_000_000)
        self.assertRegex(password, r"^[a-z2-9]{5}(-[a-z2-9]{5}){3}$")
        self.assertNotRegex(password, r"[01ilo]")
        self.assertEqual(done, {"second_step_off": True, "main_unlinked": True, "notify": [self.uid]})
        # the new password counts, the old one not; no code asked
        self.assertTrue(core.check_password(password))
        self.assertFalse(core.check_password("secret-admin"))
        self.assertIsNone(mfa.linked())
        self.assertFalse(mfa.enabled(mfa.ADMIN))
        a = TestClient(panel.app)
        self.assertEqual(a.post("/api/login", json={"password": password}).json(), {"ok": True})
        # the old step is kept aside, the roles stay, only the main admin is unlinked
        self.assertTrue(os.path.exists(mfa._own_path(mfa.ADMIN) + ".1800000000.bak"))
        self.assertEqual(coadmin.main_uid(), "")
        self.assertEqual(coadmin.role(self.uid), "admin")
        self.assertTrue(mfa.enabled(self.uid))          # the profile's own step is untouched
        # noted and told
        self.assertIn("notzugang_cli", _events()[-3:])
        self.assertEqual(asyncio.run(notzugang.tell(done["notify"])), 1)
        self.assertEqual(self.sent[0][0], self.uid)
        self.assertIn("Notzugang", self.sent[0][1])
        self.assertIs(self.sent[0][2].get("private"), False)

    def test_nothing_to_turn_off(self):
        coadmin.unlink_main()
        os.remove(mfa._own_path(mfa.ADMIN))
        password, done = notzugang.reset()
        self.assertEqual((done["second_step_off"], done["main_unlinked"]), (False, False))
        self.assertTrue(core.check_password(password))

    def test_only_from_the_shell(self):
        """No route starts it, and the shell command needs root, asks first and runs as the service user."""
        for f in glob.glob(os.path.join(helpers.APP, "panel", "*.py")):
            if not f.endswith("notzugang.py"):
                with open(f) as fh:
                    self.assertNotRegex(fh.read(), r"import notzugang|notzugang\.reset", f)
        with open(os.path.join(helpers.APP, "speech-spark.sh")) as fh:
            cli = fh.read()
        body = re.search(r"cmd_notzugang\(\) \{\n(.*?)\n\}", cli, re.S).group(1)
        self.assertIn("need_root notzugang", body)
        self.assertIn('read -r -p "Weiter? [j/N] "', body)
        self.assertIn("as_panel_user notzugang.py", body)
        helper = re.search(r"as_panel_user\(\) \{\n(.*?)\n\}", cli, re.S).group(1)   # the one way to run as the service user
        self.assertIn('runuser -u "$svc" -- env -i', helper)
        self.assertIn('[ "$svc" != root ]', helper)
        self.assertIn("notzugang) shift; cmd_notzugang", cli)


def _events():
    with open(guard.AUDIT) as f:
        return [json.loads(x)["event"] for x in f if x.strip()]


if __name__ == "__main__":
    unittest.main()
