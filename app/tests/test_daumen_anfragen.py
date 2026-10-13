"""👍/👎 on its request in Zustand → Logs → Anfragen (tracelog.vote, faelle.rate; Dominik 2026-10-12 „alle 4
umsetzten“): the list shows the thumb, two filters count them, the detail names the fixed reason and jumps to the
case, the copy for a thread carries it. Only thumb, fixed reason word, seconds and case id are kept, never the note
or the question; a changed vote replaces the old one; unknown or malformed ids change nothing.
Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import os
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import faelle  # noqa: E402
import profiles  # noqa: E402
import tracelog  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_einstellungs_assistent import Base, profile, trace  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOTE = "Zitronenfalter-Notiz"


def items():
    return ADMIN.get("/api/admin/traces?minutes=60").json()


class Thumb(Base):
    def setUp(self):
        super().setUp()
        tracelog.clear()
        self.now = time.time()
        rec = trace(persist=True)
        self.tid = rec.id
        tracelog._write([{"id": rec.id, "t": self.now - 10, "client": "web", "who": None, "kind": "guest",
                          "device": "", "intent": "wetter", "steps": rec.steps, "marks": rec.marks, "errors": [],
                          "status": "ok"}])
        self.rec = rec

    def tearDown(self):
        tracelog.clear()
        super().tearDown()

    def rate(self, good, grund="", note=""):
        self.on(bewerten=True)
        _, uid = profile("DaumenDora")
        profiles.save_settings(uid, {"rate_on": True})
        rid = faelle.turn_end(self.rec, {"id": uid, "name": "DaumenDora"}, "Wie wird das Wetter", "x", now=self.now)
        self.assertTrue(rid)
        return faelle.rate(rid, uid, good, grund, note, now=self.now + 3)

    def test_bad_vote_with_reason_and_case_never_the_note(self):
        res = self.rate(False, "werkzeug", NOTE)
        d = items()
        x = next(x for x in d["items"] if x["id"] == self.tid)
        self.assertEqual(x["vote"]["v"], "schlecht")
        self.assertEqual(x["vote"]["grund"], "werkzeug")
        self.assertEqual(x["vote"]["case"], res["case"])
        self.assertEqual(x["vote"]["after"], 11)   # the answer ended 8.3 s ago (start 10 s ago, 1.7 s long), rated 3 s later
        self.assertIn("werkzeug", d["reasons"])
        with open(tracelog._file()) as f:
            self.assertNotIn(NOTE, f.read())
        self.assertNotIn("Wetter", str(x))

    def test_changed_vote_replaces_and_good_has_no_reason(self):
        self.rate(False, "antwort")
        _, uid = profile("DaumenDora")
        rid = next(r for r, s in faelle._recent.items() if s.get("who") == uid)
        faelle.rate(rid, uid, True, "antwort", now=self.now + 5)
        x = next(x for x in items()["items"] if x["id"] == self.tid)
        self.assertEqual(x["vote"]["v"], "gut")
        self.assertEqual(x["vote"]["grund"], "")
        self.assertEqual(x["vote"]["case"], "")

    def test_bad_ids_and_values_change_nothing(self):
        for tid, v in (("../x", "gut"), ("zzzzzz", "gut"), ("ffffff", "gut"), (self.tid, "egal")):
            self.assertFalse(tracelog.vote(tid, v, now=self.now))
        self.assertTrue(tracelog.vote(self.tid, "schlecht", "erfunden", "nicht-hex", now=self.now))
        x = tracelog.all_traces(self.now)[0]["vote"]
        self.assertEqual((x["grund"], x["case"]), ("", ""))

    def test_not_kept_request_gets_nothing(self):
        self.rec.persist = False
        self.rate(False, "antwort")
        x = next(x for x in items()["items"] if x["id"] == self.tid)
        self.assertIsNone(x["vote"])

    def test_panel_shows_thumb_filters_detail_and_copy(self):
        with open(os.path.join(helpers.APP, "panel", "static", "js", "logs.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function rthumb(", js)                          # 1 list
        self.assertIn("['gut','👍'", js)                                # 2 filters
        self.assertIn("['schlecht','👎'", js)
        self.assertIn("Bewertet nach ${v.after} s", js)                 # 3 detail with reason
        self.assertIn("window.openCase(v.case)", js)                    #   and the jump to the case
        self.assertIn("` · Bewertung ${", js)                          # 4 copy for the thread
        with open(os.path.join(helpers.APP, "panel", "static", "js", "verbessern.js"), encoding="utf-8") as f:
            self.assertIn("window.openCase=", f.read())


if __name__ == "__main__":
    unittest.main()
