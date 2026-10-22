"""Spielprofile „Nur Krisenspiel“ (nurspiel.py, plan krisenspiel/plan-netzduell.md Schritt 1): a profile the admin
marks so reaches only the page, its sign-in, its own security and the Krisenspiel. Every other route of the panel
answers it 403 before the route runs (the walk below goes through all of them), every function but the game is
blocked for it, it never gets an admin role, another profile keeps everything. Logs only fixed words. No clock."""
import contextlib
import io
import re
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import coadmin  # noqa: E402
import features  # noqa: E402
import krisenspiel as K  # noqa: E402
import nurspiel  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_pruefung import all_routes  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def login(name, pin="1234"):
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


class NurSpiel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = io.StringIO()
        with contextlib.redirect_stdout(cls.out):
            ADMIN.post("/api/admin/profiles", json={"name": "Nurspiel Nina", "pin": "1234", "nur_spiel": True})
            ADMIN.post("/api/admin/profiles", json={"name": "Normal Norbert", "pin": "1234"})
        cls.uid, cls.other = uid_of("Nurspiel Nina"), uid_of("Normal Norbert")
        cls.c, cls.n = login("Nurspiel Nina"), login("Normal Norbert")

    def setUp(self):
        helpers.keep_chat(self, "krisenspiel", "calendar", "deny")
        helpers.set_config(krisenspiel=True, calendar=True)

    def test_only_the_game_among_the_functions(self):
        self.assertTrue(profiles.nur_spiel(self.uid))
        self.assertFalse(profiles.nur_spiel(self.other))
        self.assertTrue(features.allowed("krisenspiel", self.uid))
        for f in features.FEATURES:
            if nurspiel.SPIEL not in features.chain(f.key) and f.key not in features.NO_BLOCK:
                self.assertTrue(features.blocked(f.key, self.uid), f.key)
                self.assertFalse(features.blocked(f.key, self.other), f.key)
        who = self.c.get("/api/whoami").json()
        self.assertEqual((who["nur_spiel"], who["krisenspiel"], who["calendar"]), (True, True, False))
        self.assertIs(self.n.get("/api/whoami").json()["nur_spiel"], False)
        row = next(u for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["id"] == self.uid)
        self.assertIs(row["nur_spiel"], True)

    def test_every_other_route_refuses_it(self):
        out = io.StringIO()
        seen = 0
        with contextlib.redirect_stdout(out):
            for r in all_routes(panel.app.routes):
                if not getattr(r, "methods", None):
                    continue
                path = re.sub(r"\{[^}]+\}", "x1", r.path)
                for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                    if nurspiel.may(m, path):
                        continue
                    res = self.c.request(m, path, json={})
                    self.assertEqual((res.status_code, res.json().get("detail")), (403, nurspiel.DETAIL), (m, path))
                    seen += 1
        self.assertGreater(seen, 300)
        self.assertIn("spiel: nur spiel gesperrt | profile", out.getvalue())
        self.assertIn("spiel: nur spiel gesperrt | seite", out.getvalue())
        self.assertNotIn("Nina", out.getvalue())
        # another profile is not touched: its own pages answer
        self.assertEqual(self.n.get("/api/profile/settings").status_code, 200)

    def test_the_game_itself_plays(self):
        with contextlib.redirect_stdout(io.StringIO()):
            d = self.c.post("/api/profile/krisenspiel/neu", json={"szenario": "san", "seed": 3})
            self.assertEqual(d.status_code, 200)
            self.assertEqual(self.c.get("/api/profile/krisenspiel").json()["spiel"]["szenario"], "san")
            self.assertEqual(self.c.get("/api/profile/krisenspiel/anleitung").status_code, 200)
            self.assertEqual(self.c.get("/").status_code, 200)
            self.assertEqual(self.c.get("/api/profile/mfa").status_code, 200)
            self.c.delete("/api/profile/krisenspiel/daten")
            helpers.set_config(krisenspiel=False)                             # the game off: nothing at all
            self.assertEqual(self.c.get("/api/profile/krisenspiel").status_code, 403)

    def test_the_admin_switches_it_and_never_for_an_admin(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ADMIN.put(f"/api/admin/profiles/{self.other}/nurspiel", json={"on": "ja"}).status_code, 400)
            self.assertEqual(ADMIN.put("/api/admin/profiles/u_000000000000/nurspiel", json={"on": True}).status_code, 404)
            self.assertEqual(ADMIN.post("/api/admin/profiles", json={"name": "Nurspiel X", "pin": "1234", "nur_spiel": 1}).status_code, 400)
            with mock.patch.object(coadmin, "role", side_effect=lambda u: "admin" if u == self.other else ""):
                self.assertEqual(ADMIN.put(f"/api/admin/profiles/{self.other}/nurspiel", json={"on": True}).status_code, 409)
            self.assertEqual(ADMIN.put(f"/api/admin/profiles/{self.other}/nurspiel", json={"on": True}).json()["nur_spiel"], True)
            self.assertEqual(self.n.get("/api/profile/settings").status_code, 403)
            self.assertEqual(ADMIN.get(f"/api/admin/profiles/{self.other}").json()["nur_spiel"], True)
            with self.assertRaises(ValueError):
                coadmin.set_role(self.other, "admin")
            ADMIN.put(f"/api/admin/profiles/{self.other}/nurspiel", json={"on": False})
            self.assertEqual(self.n.get("/api/profile/settings").status_code, 200)
        log = out.getvalue() + self.out.getvalue()
        for want in ("spiel: nur spiel | profil angelegt", "spiel: nur spiel | an", "spiel: nur spiel | aus",
                     "spiel: nur spiel abgelehnt | eingabe", "spiel: nur spiel abgelehnt | kein profil",
                     "spiel: nur spiel abgelehnt | admin rolle"):
            self.assertIn(want, log)

    def test_live_counts_game_profiles(self):
        K._live.update(at=0.0, d=None)
        self.assertGreaterEqual(K.for_live()["nur_spiel"], 1)


if __name__ == "__main__":
    unittest.main()
