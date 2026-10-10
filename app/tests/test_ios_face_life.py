"""iPhone app "Gesicht zeigt, was es tut" (V01.0.323): only fixed names from the Spark's chat events reach
the face, never text from an event, and only with the admin switch (hello "face_life"). (ios/ is not in
an app/-only copy, then this is skipped.)"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IOS = os.path.join(ROOT, "ios")
NAMES = {"search", "calendar", "mail", "home", "memory", "happy", "error"}


def read(*p):
    with open(os.path.join(IOS, *p)) as f:
        return f.read()


class FaceLifeApp(unittest.TestCase):
    def setUp(self):
        if not os.path.isdir(IOS):
            self.skipTest("ios/ is not in an app/-only copy")

    def test_only_fixed_names_reach_the_face(self):
        api = read("Shared", "SparkAPI.swift")
        calls = re.findall(r"\.face\((.*?)\)\)", api)
        self.assertTrue(calls)
        for c in calls:
            # what the event says only decides between fixed names (ev["ok"] for happy or error)
            lits = re.findall(r'"([a-z]+)"', re.sub(r'ev\["ok"\] as\? Bool == true', "", c))
            self.assertTrue(lits, c)
            self.assertLessEqual(set(lits), NAMES, c)
            self.assertNotIn("ev[\"text\"]", c)
            self.assertNotIn("delta", c)

    def test_face_knows_only_these_names(self):
        face = read("Spark", "Face.swift")
        body = face[face.index("func event(_ name: String)"):face.index("func text()")]
        self.assertEqual(set(re.findall(r'case "([a-z]+)"', body)), NAMES)
        self.assertIn("default: return", body)

    def test_only_with_the_admin_switch(self):
        self.assertIn('faceLife: d["face_life"] as? Bool ?? false', read("Shared", "SparkAPI.swift"))
        views = read("Spark", "Views.swift")
        for line in [l for l in views.splitlines() if "FaceView(" in l]:
            self.assertIn("acts: talk.allowed.faceLife ? talk.faceActs : nil", line)


if __name__ == "__main__":
    unittest.main()
