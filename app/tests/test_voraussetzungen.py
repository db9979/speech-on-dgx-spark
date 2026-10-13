"""Voraussetzungen mit einschalten (Dominik 2026-10-12: "können wir da eine Info geben, wenn jemand Funktionen
einschaltet, die andere voraussetzen, auch mit einschalten"). features.py knows each function's chain (what it
builds on); the admin pages ask before switching the missing part on, say what goes off with a switch, and
the chat names everything that is missing."""
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import docmake  # noqa: E402
import features  # noqa: E402
import hilfe  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


def chat_cfg():
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        return json.load(f)["chat"]


KEEP = ("documents", "doc_make", "doc_make_templates", "doc_pictures", "remarkable", "remarkable_send", "doc_semantic")


class Base(unittest.TestCase):
    """Leaves the switches as it found them (test_wissen and others expect "Eigene Dokumente" on)."""
    def setUp(self):
        c = chat_cfg()
        self.kept = {k: c.get(k) for k in KEEP}

    def tearDown(self):
        helpers.set_config(**self.kept)


class Chain(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(documents=False, doc_make=False, doc_make_templates=False, doc_pictures=False,
                           remarkable=False, remarkable_send=False, doc_semantic=False)

    def test_chain_and_switches(self):
        self.assertEqual(features.chain("erstellenvorlagen"), ["documents", "erstellen", "erstellenvorlagen"])
        self.assertEqual(features.chain_switches("rmsend"), ["documents", "doc_pictures", "remarkable", "remarkable_send"])
        self.assertEqual(features.chain_switches("einordnungpost"), ["systemone", "systemone_tidy", "mail_tidy", "mail"])
        self.assertEqual(features.switch_name("documents"), ("Eigene Dokumente", "Own documents"))
        for f in features.FEATURES:       # no loops and only known parents
            self.assertEqual(features.chain(f.key)[-1], f.key)
            self.assertTrue(set(features.chain(f.key)) <= set(features.BY_KEY))

    def test_missing_and_affected(self):
        self.assertEqual(features.missing("erstellen"), ["documents", "doc_make"])
        helpers.set_config(documents=True, doc_make=True, doc_semantic=True)
        self.assertEqual(features.missing("erstellen"), [])
        self.assertEqual(set(features.affected("documents")), {"erstellen", "docmeaning"})
        self.assertEqual(features.affected("doc_make"), [])

    def test_missing_text_names_everything_with_ways(self):
        _, uid = profile("VorausText")
        t = features.missing_text("erstellen", uid)
        self.assertIn("Funktionen → Eigene Dokumente, Funktionen → Dokumente erstellen", t)
        self.assertNotIn("Ich →", t)                       # a profile switches nothing on (Freigabe vereinfachen)
        en = features.missing_text("erstellen", uid, "en")
        self.assertIn("Features → Own documents", en)
        helpers.set_config(documents=True, doc_make=True)
        self.assertEqual(features.missing_text("erstellen", uid), "")   # released: nothing missing for the profile
        # blocked for this profile by the admin (also through the chain): the way to Wer darf was
        r = ADMIN.put(f"/api/admin/features/documents/profiles/{uid}", json={"on": False})
        self.assertEqual(r.status_code, 200)
        self.addCleanup(ADMIN.put, f"/api/admin/features/documents/profiles/{uid}", json={"on": True})
        self.assertIn("Der Admin hat es für dich gesperrt (Funktionen → Wer darf was)", features.missing_text("erstellen", uid))
        # the chat's fixed sentence for a file wish while it is off
        self.assertIn("Funktionen → Wer darf was", docmake.off_hint(uid))
        self.assertNotIn("Ich →", docmake.off_hint(uid))
        ADMIN.put(f"/api/admin/features/documents/profiles/{uid}", json={"on": True})
        helpers.set_config(documents=False)
        self.assertIn("Funktionen → Eigene Dokumente", docmake.off_hint(uid))
        self.assertIn("Fehlt im Spark: Eigene Dokumente", hilfe.state_line("erstellen", uid, "profile"))
        # a preference the profile switched off: the way to its own page
        helpers.set_config(proactive=True)
        self.addCleanup(helpers.set_config, proactive=False)
        profiles.save_settings(uid, {"pro_on": False})
        self.assertIn("Du hast es ausgeschaltet: Ich →", features.missing_text("proactive", uid))


class Enable(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(documents=False, doc_make=False, doc_make_templates=False)

    def test_enable_switches_the_whole_chain(self):
        r = ADMIN.post("/api/admin/features/erstellenvorlagen/enable", json={})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["switched"], ["documents", "doc_make", "doc_make_templates"])
        self.assertTrue(d["spark"])
        c = chat_cfg()
        self.assertTrue(c["documents"] and c["doc_make"] and c["doc_make_templates"])
        self.assertEqual(ADMIN.post("/api/admin/features/erstellen/enable", json={}).json()["switched"], [])

    def test_enable_holds_for_every_profile(self):
        """Switching on is for the whole Spark: no profile to name, and what is released works for each profile."""
        _, uid = profile("VorausProfil")
        r = ADMIN.post("/api/admin/features/erstellen/enable", json={"uid": uid})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("doc_make", profiles.settings(uid))
        self.assertTrue(features.allowed("erstellen", uid))

    def test_refusals(self):
        self.assertEqual(ADMIN.post("/api/admin/features/nope/enable", json={}).status_code, 404)
        self.assertEqual(ADMIN.post("/api/admin/features/erstellen/enable", json=["x"]).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/features/erstellen/enable", content=b"{nope").status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/features/erstellen/enable", content=b"x" * 300).status_code, 413)
        # only the admin
        c, _ = profile("VorausGast")
        self.assertIn(c.post("/api/admin/features/erstellen/enable", json={}).status_code, (401, 403))
        self.assertIn(TestClient(panel.app).post("/api/admin/features/erstellen/enable", json={}).status_code, (401, 403))
        self.assertFalse(chat_cfg()["doc_make"])

    def test_switches_the_app_may_not_change_come_back_as_ways(self):
        import admin
        may = set(admin.app_switches())
        hidden = next((sw for f in features.FEATURES for sw in features.chain_switches(f.key) if sw not in may), None)
        if hidden is None:
            self.skipTest("every switch may be changed")
        key = next(f.key for f in features.FEATURES if hidden in features.chain_switches(f.key))
        helpers.set_config(**{hidden: False})
        d = ADMIN.post(f"/api/admin/features/{key}/enable", json={}).json()
        self.assertIn(hidden, [m["switch"] for m in d["manual"]])
        self.assertFalse(chat_cfg()[hidden])

    def test_matrix_carries_chain_states_and_names(self):
        m = ADMIN.get("/api/admin/features").json()
        row = next(r for r in m["features"] if r["key"] == "erstellen")
        self.assertEqual(row["chain"], ["documents", "doc_make"])
        self.assertIs(m["states"]["documents"], False)
        self.assertEqual(m["snames"]["documents"], ["Eigene Dokumente", "Own documents"])
        self.assertIn("doc_make", m["switchable"])


if __name__ == "__main__":
    unittest.main()
