"""Hörstück in CarPlay (Dominik 2026-11-05: „Ein CarPlay fürs Hörstück noch ausarbeiten und umsetzen“): the list the
car shows (GET /api/profile/hoerstuecke) holds only the own finished Hörstücke of every own Mappe, with the Mappe's name
and the length, the newest first, at most AUTO_MAX; only while Hörstück is released, never for another profile or a
guest; the app may only read it (iphone.THINGS). The rules of the car and the player are in test_carplay. No test
depends on the clock."""
import unittest

from tests import helpers
from tests import test_hoerstueck as th

helpers.start()
import features  # noqa: E402
import hoerstueck  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class Car(th.Base):
    finished = th.Done.finished

    def test_only_the_own_finished_ones_newest_first(self):
        c, uid, mid, hid, _ = self.finished("Hoerstueckauto")
        with th.quiet():
            waits, _ = hoerstueck.bitte(uid, mid, 5, 2, now=th.NOW + 50)
        with hoerstueck._Db(uid) as con:      # a newer finished one (written directly: the steps are test_hoerstueck's)
            con.execute("INSERT INTO hs_stueck (id, mappe, titel, stand, dauer_s, datei, made) "
                        "VALUES ('abcdefabcdef', ?, 'Neu', 'fertig', 61, 'x', ?)", (mid, int(th.NOW + 100)))
        r = c.get("/api/profile/hoerstuecke")
        self.assertEqual(r.status_code, 200, r.text)
        got = r.json()
        self.assertEqual(got["max"], hoerstueck.AUTO_MAX)
        self.assertEqual(hoerstueck.AUTO_MAX, 12)
        self.assertEqual([x["id"] for x in got["stuecke"]], ["abcdefabcdef", hid])   # the waiting one is not there
        self.assertNotIn(waits, [x["id"] for x in got["stuecke"]])
        first = got["stuecke"][0]
        self.assertEqual(set(first), {"id", "titel", "mappe_name", "dauer_s", "made"})   # no script, no path
        self.assertEqual((first["mappe_name"], first["dauer_s"]), ("Wärmepumpe", 61))
        self.assertEqual(len(hoerstueck.fertige(uid, n=1)), 1)
        other, _ = self.fresh("Hoerstueckautofremd")
        self.assertEqual(other.get("/api/profile/hoerstuecke").json()["stuecke"], [])
        helpers.set_config(hoerstueck=False)
        self.assertEqual(c.get("/api/profile/hoerstuecke").status_code, 403)

    def test_never_for_a_guest_and_read_only_for_the_app(self):
        self.assertEqual(features.reason("hoerstueck", None), "guest")
        self.assertIn(TestClient(panel.app).get("/api/profile/hoerstuecke").status_code, (401, 403))
        rules = profiles.APP_AREAS["hoerstueck"]
        self.assertTrue(any("GET" in ms and p.fullmatch("/api/profile/hoerstuecke") for ms, p in rules))
        for method in ("POST", "PUT", "DELETE"):
            self.assertFalse(any(method in ms and p.fullmatch("/api/profile/hoerstuecke") for ms, p in rules), method)


if __name__ == "__main__":
    unittest.main()
