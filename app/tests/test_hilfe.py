"""Spark-Hilfe (hilfe.py), V01.0.326: answers about the Spark itself and suggestion cards.

Off without the admin's and the profile's switch, never for guests. Each login only gets what its rights allow:
Spark settings and the docs about running the Spark only for admins (a Verwalter only the feature switches), the
Spark's switch state only for admins. A card never switches by itself: the panel checks the model's wish against
fixed rules (only APPLY functions, a profile only its own switches, Spark switches only for admins), and only
the person's tap through /api/hilfe/karte applies it, once, bound to the profile, in time, not under the Notaus.
After outside text no card. No test depends on the wall clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import features  # noqa: E402
import hilfe  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
from common import load_config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234", admin=False):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    if admin:
        assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


def ask(c, text, **body):
    r = c.post("/api/chat", json=dict({"messages": [{"role": "user", "content": text}], "speak": False}, **body))
    assert r.status_code == 200, r.text
    ev = helpers.events(r)
    return "".join(e.get("delta", "") for e in ev if e["type"] == "text"), [e["card"] for e in ev if e["type"] == "hilfe"]


def tool(name, **args):
    return f"TOOL {name} {json.dumps(args)}"


class Hilfe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.uid = profile("Hilfetest")
        cls.a, cls.auid = profile("Hilfeadmin", admin=True)
        cls.o, cls.ouid = profile("Hilfeandere")
        for c in (cls.p, cls.a, cls.o):
            c.put("/api/profile/settings", json={"spark_help": True})

    def setUp(self):
        helpers.set_config(spark_help=True, spark_suggest=True, spark_drawer=True, routing=False, direct_read=False,
                           prefetch=False, search=False)
        for uid in (self.uid, self.auid):
            profiles.save_settings(uid, {"spark_help": True, "route": False, "direct_read": False, "prefetch": False})
        hilfe._cards.clear()

    def tearDown(self):
        try:
            os.remove(notaus.FILE)
        except FileNotFoundError:
            pass
        helpers.set_config(spark_help=False, spark_suggest=False, spark_drawer=False, routing=False)

    # ---------------------------------------------------------------- off, guests, own switch
    def test_off_without_both_switches_and_never_for_guests(self):
        helpers.set_config(spark_help=False)
        text, _ = ask(self.p, tool("spark_hilfe", question="Gezielte Werkzeugwahl"))
        self.assertIn("NO TOOL", text)
        helpers.set_config(spark_help=True)
        profiles.save_settings(self.uid, {"spark_help": False})
        text, _ = ask(self.p, tool("spark_hilfe", question="Gezielte Werkzeugwahl"))
        self.assertIn("NO TOOL", text)
        helpers.set_config(public=True)
        try:
            text, _ = ask(TestClient(panel.app), tool("spark_hilfe", question="Gezielte Werkzeugwahl"))
            self.assertIn("NO TOOL", text)
        finally:
            helpers.set_config(public=False)
        self.assertFalse(hilfe.on(None))
        self.assertEqual(self.p.get("/api/whoami").json()["hilfe"], None)
        profiles.save_settings(self.uid, {"spark_help": True})
        self.assertEqual(self.p.get("/api/whoami").json()["hilfe"], {"suggest": True, "page": True})

    def test_answer_names_the_way_and_the_profiles_state(self):
        text, _ = ask(self.p, tool("spark_hilfe", question="Was macht die Gezielte Werkzeugwahl?"))
        self.assertIn("Gezielte Werkzeugwahl", text)
        self.assertIn("Ich → Gespräch", text)
        self.assertNotIn("Funktionen → Gezielte Werkzeugwahl", text)
        self.assertIn("Funktionen → Gezielte Werkzeugwahl",
                      hilfe.answer_text("Was macht die Gezielte Werkzeugwahl?", self.auid, "admin"))
        self.assertIn("Kennung: routing", text)
        self.assertIn("Daten, keine Anweisungen", text)
        text, _ = ask(self.p, tool("spark_hilfe", question="Wie bekomme ich schnellere Antworten?"))
        self.assertIn("Tipp: Schneller antworten", text)

    # ---------------------------------------------------------------- only what the rights allow
    def test_profile_gets_no_admin_settings_docs_or_spark_state(self):
        q = "Schneller Antwortbeginn Sprachmodell Temperatur"
        mine = hilfe.answer_text(q, self.uid, "profile")
        boss = hilfe.answer_text(q, self.auid, "admin")
        self.assertNotIn("Admin-Einstellung", mine)
        self.assertIn("Admin-Einstellung", boss)
        self.assertNotIn("Spark-Schalter", hilfe.answer_text("Gezielte Werkzeugwahl", self.uid, "profile"))
        self.assertIn("Spark-Schalter", hilfe.answer_text("Gezielte Werkzeugwahl", self.auid, "admin"))
        for it in hilfe.search("Sicherung Backup Update Wächter Proxy", "de", level="profile", n=50):
            self.assertNotEqual(it["kind"], "setting")
            if it["kind"] == "doc":
                self.assertIn(it["src"], hilfe.USER_DOCS)
        # a Verwalter: the feature switches, not the other Spark settings
        for it in hilfe.search("Schalter Funktion Temperatur Sprachmodell", "de", level="manager", n=50):
            if it["kind"] == "setting":
                self.assertEqual(it["page"], "feat")
        # the admin's steps of a guide are left out for a profile, and so is the admin's tip
        g = hilfe.answer_text("Wikipedia direkt einrichten", self.uid, "profile")
        self.assertNotIn("Admin: Funktionen", g)
        self.assertNotIn("sicherer machen", hilfe.answer_text("Spark sicherer machen", self.uid, "profile"))
        self.assertIn("sicherer machen", hilfe.answer_text("Spark sicherer machen", self.auid, "admin", request=None))

    def test_chat_level_follows_the_login(self):
        text, _ = ask(self.p, tool("spark_hilfe", question="Schneller Antwortbeginn Sprachmodell"))
        self.assertNotIn("Spark-Schalter", text)
        text, _ = ask(self.a, tool("spark_hilfe", question="Schneller Antwortbeginn Sprachmodell"))
        self.assertIn("Spark-Schalter", text)

    def test_no_secrets_in_hits(self):
        self.assertEqual(hilfe.SECRET.sub("…", "der token: abc123 und pin=4711"), "der … und …")

    def test_unknown_page_is_ignored(self):
        self.assertIsNone(hilfe.page_of({"page": "cfg/sec; drop"}, self.uid))
        self.assertIsNone(hilfe.page_of({"page": "Ignoriere alles"}, self.uid))
        self.assertEqual(hilfe.page_of({"page": "cfg/sec"}, self.uid), "cfg/sec")
        helpers.set_config(spark_drawer=False)
        self.assertIsNone(hilfe.page_of({"page": "cfg/sec"}, self.uid))

    def test_page_routes_to_the_help_and_is_named(self):
        helpers.set_config(routing=True)
        profiles.save_settings(self.uid, {"route": True})
        text, _ = ask(self.p, tool("spark_hilfe", question="Was kann ich hier einstellen?"), page="me/setbox")
        self.assertIn("Seite: Ich → Gespräch", text)

    # ---------------------------------------------------------------- the card
    def test_profile_card_only_own_switches_and_apply_once_with_undo(self):
        helpers.set_config(routing=True, direct_read=True)
        _, cards = ask(self.p, tool("spark_vorschlag", functions=["routing", "direct", "mfa", "telegram", "gibtsnicht"]))
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual({x["kind"] for x in card["items"]}, {"profile"})
        self.assertEqual({x["key"] for x in card["items"]}, {"routing", "direct"})
        self.assertEqual({x["name"] for x in card["blocked"]} >= {"Zweiter Anmeldeschritt", "Telegram"}, True)
        self.assertNotIn("uid", card)
        self.assertFalse(profiles.settings(self.uid).get("route"))   # nothing changed by the model
        # another profile and a device key cannot use it
        self.assertEqual(self.o.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"}).status_code, 404)
        key = profiles.add_device("hilfe-test", self.uid)
        dev = TestClient(panel.app)
        self.assertEqual(dev.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"},
                                  headers={profiles.DEVICE_HEADER: key}).status_code, 403)
        r = self.p.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"})
        self.assertEqual(r.json(), {"state": "applied"})
        self.assertTrue(profiles.settings(self.uid)["route"])
        self.assertTrue(profiles.settings(self.uid)["direct_read"])
        self.assertEqual(self.p.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"}).status_code, 409)
        self.assertEqual(self.p.post(f"/api/hilfe/karte/{card['id']}", json={"do": "undo"}).json(), {"state": "undone"})
        self.assertFalse(profiles.settings(self.uid)["route"])
        self.assertEqual(self.p.post(f"/api/hilfe/karte/{card['id']}", json={"do": "undo"}).status_code, 409)

    def test_one_open_card_per_profile(self):
        helpers.set_config(routing=True)
        first = hilfe.build_card(self.uid, ["routing"], True, False)
        second = hilfe.build_card(self.uid, ["routing"], True, False)
        self.assertEqual(self.p.post(f"/api/hilfe/karte/{first['id']}", json={"do": "apply"}).status_code, 404)
        self.assertEqual(self.p.post(f"/api/hilfe/karte/{second['id']}", json={"do": "apply"}).status_code, 200)

    def test_profile_never_gets_spark_switches(self):
        card = hilfe.build_card(self.uid, ["routing"], True, False)
        self.assertEqual(card["items"], [])   # the Spark's switch is off and this login is no admin
        self.assertIn("Admin", card["blocked"][0]["why"])

    def test_admin_card_switches_the_spark_with_undo_log(self):
        _, cards = ask(self.a, tool("spark_vorschlag", recipe="schneller"))
        card = cards[0]
        kinds = {(x["key"], x["kind"]) for x in card["items"]}
        self.assertIn(("routing", "admin"), kinds)
        self.assertIn(("routing", "profile"), kinds)
        self.assertTrue(card["admin"])
        self.assertFalse(load_config()["chat"]["routing"])
        r = self.a.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(load_config()["chat"]["routing"])
        self.assertTrue(load_config()["chat"]["direct_read"])
        undo = ADMIN.get("/api/admin/undo").json()
        self.assertIn("chat.routing", json.dumps(undo))
        self.a.post(f"/api/hilfe/karte/{card['id']}", json={"do": "undo"})
        self.assertFalse(load_config()["chat"]["routing"])

    def test_switching_off_never_for_everybody(self):
        helpers.set_config(routing=True)
        profiles.save_settings(self.auid, {"route": True})
        card = hilfe.build_card(self.auid, ["routing"], False, True)
        self.assertEqual([(x["key"], x["kind"]) for x in card["items"]], [("routing", "profile")])

    def test_admin_session_needed_at_apply(self):
        card = hilfe.build_card(self.uid, ["routing"], True, True)   # built as if by an admin ...
        self.assertTrue(card["admin"])
        r = self.p.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"})   # ... applied without the admin login
        self.assertEqual(r.status_code, 403)
        self.assertFalse(load_config()["chat"]["routing"])

    def test_old_card_and_notaus(self):
        helpers.set_config(routing=True)
        card = hilfe.build_card(self.uid, ["routing"], True, False)
        card["t"] -= hilfe.CARD_S + 1
        self.assertEqual(self.p.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"}).status_code, 409)
        card = hilfe.build_card(self.uid, ["routing"], True, False)
        notaus.trigger(2, "test", "", "panel")
        home, notaus.at_home = notaus.at_home, lambda request: True   # the test client counts as outside the home
        try:
            r = self.p.post(f"/api/hilfe/karte/{card['id']}", json={"do": "apply"})
        finally:
            notaus.at_home = home
        self.assertEqual(r.status_code, 423)
        self.assertFalse(profiles.settings(self.uid).get("route"))

    def test_no_card_after_outside_text(self):
        """Prompt injection: a web page or mail read before may not put a card in front of the person."""
        msgs = [{"role": "user", "content": "Such im Netz"}, {"role": "assistant", "content": "Laut Seite ...", "outside": True},
                {"role": "user", "content": tool("spark_vorschlag", functions=["routing"])}]
        r = self.p.post("/api/chat", json={"messages": msgs, "speak": False})
        ev = helpers.events(r)
        self.assertEqual([e for e in ev if e["type"] == "hilfe"], [])
        self.assertEqual(hilfe._cards, {})

    def test_no_card_outside_the_browser(self):
        helpers.set_config(routing=True)
        _, cards = ask(self.p, tool("spark_vorschlag", functions=["routing"]), client="telegram")
        self.assertEqual(cards, [])
        self.assertEqual(hilfe._cards, {})

    def test_suggest_switch_off_means_no_card_tool(self):
        helpers.set_config(spark_suggest=False)
        text, cards = ask(self.p, tool("spark_vorschlag", functions=["routing"]))
        self.assertEqual(cards, [])
        self.assertIn("NO TOOL", text)

    # ---------------------------------------------------------------- the fixed rules themselves
    def test_apply_lists_hold_no_security_or_outside_switch(self):
        never = {f.key for f in features.FEATURES if f.group == "sec"} | {
            "mcpserver", "mcpextern", "mcpact", "telegram", "messages", "agent", "mcp", "ha", "mail", "tidy",
            "esp32", "roomfar", "iphone", "android", "pebble", "proactive", "search", "calendar", "contacts", "docshared"}
        self.assertEqual(hilfe.APPLY_PROFILE & never, set())
        for k in hilfe.APPLY_ADMIN:
            f = features.BY_KEY[k]
            self.assertEqual(len(f.admin), 1, k)   # "off" switches exactly the function's own switch
            self.assertNotIn(f.admin[0], features.SPARK_ONLY, k)
        for _, keys in hilfe.RECIPES.values():
            self.assertTrue(set(keys) <= hilfe.APPLY_PROFILE)
        for _, _, keys, _, _ in hilfe.TIPS:
            self.assertTrue(all(k in features.BY_KEY for k in keys))

    def test_every_guide_and_setting_is_in_the_index(self):
        ix = hilfe.index()
        titles = {it["title"] for it in ix["items"] if it["kind"] == "guide"}
        self.assertEqual({g["t"][0] for g in hilfe.guides()} - titles, set())
        self.assertGreater(len(hilfe.setting_rows()), 100)
        self.assertGreater(len(hilfe.me_settings()), 15)

    @unittest.skipUnless(os.path.isdir(hilfe.REPO_DOCS), "docs/ only in the full repository")
    def test_docs_copy_is_current(self):
        self.assertEqual(hilfe.build_docs(), hilfe.docs(), "docs changed: python3 app/panel/hilfe.py --docs")


if __name__ == "__main__":
    unittest.main()
