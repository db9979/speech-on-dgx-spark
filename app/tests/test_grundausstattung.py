"""Grundausstattung (features.GRUNDAUSSTATTUNG, Dominik 2026-10-17, plan grundeinstellungen/plan.md): what makes a
newcomer's chat good from the first question.

Only switches that need no setup of their own, send nothing new out of the house and never touch a sensitive setting
may be in the list; a new installation ships them on. The internet part (GRUND_INTERNET) is never shipped on: only the
admin's answer switches it on, the web search only with a stored SearXNG address. The card's endpoint is for the
admin alone, keeps every change for Rückgängig and never switches anything off. Guests still get no function. An
empty chat's first example names where the settings are found until the profile asked the Spark about itself.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import admin  # noqa: E402
import coadmin  # noqa: E402
import features  # noqa: E402
import onboard  # noqa: E402
import profiles  # noqa: E402
import saetze  # noqa: E402
import tipps  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(APP, "panel")
# what may go out for a switch of the list, and why that is nothing new (its guide says more than „Nichts“)
OUT_OK = {"instant_ack": "the recordings stay on the Spark",
          "prefetch": "only the services the profile set up itself, the same calls as for a plain question",
          "tasks": "CalDAV only once the profile sets it up itself",
          "history_live": "only between the profile's own devices and the Spark"}
ALL = [k.split(".", 1)[1] for k in (*features.GRUNDAUSSTATTUNG, *features.GRUND_INTERNET)]


def shipped():
    with open(os.path.join(APP, "config.default.json")) as f:
        return json.load(f)["chat"]


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    return next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class TheList(unittest.TestCase):
    def test_shipped_on_and_only_plain_switches(self):
        d = shipped()
        sens = {f"{sec}.{k}" for sec, k in admin.SENSITIVE}
        known = {f.admin[0] for f in features.FEATURES} | set(features.SPARK_NAMES)
        for key in features.GRUNDAUSSTATTUNG:
            sec, k = key.split(".", 1)
            self.assertEqual(sec, "chat", key)
            self.assertIs(d.get(k), True, f"{key} is in the Grundausstattung, so it ships on")
            self.assertIn(k, known, f"{key}: no function or Spark switch of that name")
            self.assertNotIn(key, sens, f"{key} wants the admin's code, never one click")
            self.assertNotIn(key, features.DEFAULT_ON, f"{key}: its reason stands in one list")

    def test_nothing_to_set_up_and_nothing_new_out_of_the_house(self):
        with open(os.path.join(PANEL, "static", "js", "guides.js"), encoding="utf-8") as f:
            guides = re.split(r"\n\{id:'", f.read())
        for key in features.GRUNDAUSSTATTUNG:
            k = key.split(".", 1)[1]
            for f in features.FEATURES:
                if f.admin[0] == k:
                    self.assertNotIn(f.key, onboard.OWN_SETUP, f"{key} needs a setup in „Los geht's“")
                    self.assertFalse(f.parent and f.parent not in {x.key for x in features.FEATURES
                                                                   if f"chat.{x.admin[0]}" in features.GRUNDAUSSTATTUNG
                                                                   or f"chat.{x.admin[0]}" in features.DEFAULT_ON},
                                     f"{key} builds on {f.parent}, which is not shipped on")
            g = [x for x in guides if f"sw:'{key}'" in x[:400]]
            if not g:
                continue        # a Spark switch without a guide of its own (face_life: the face only shows signs)
            out = re.search(r"\bout:(NOTHING_OUT)?", g[0])
            self.assertTrue(out and (out.group(1) or k in OUT_OK), f"{key}: its guide says something leaves the house")

    def test_the_internet_part_is_never_shipped_on(self):
        d = shipped()
        for key in features.GRUND_INTERNET:
            self.assertIs(d.get(key.split(".", 1)[1]), False, key)
        self.assertEqual(d.get("grund_internet"), "offen")
        self.assertEqual(set(features.GRUNDAUSSTATTUNG) & set(features.GRUND_INTERNET), set())

    def test_guests_get_none_of_it(self):
        for key in features.GRUNDAUSSTATTUNG:
            for f in features.FEATURES:
                if f"chat.{f.admin[0]}" == key:
                    self.assertFalse(features.allowed(f.key, None), f"{f.key} for a guest")


class Card(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, *ALL, "grund_internet", "search_url")
        helpers.set_config(**{k: False for k in ALL}, grund_internet="offen", search_url="")

    def test_state_names_switches_only(self):
        d = ADMIN.get("/api/admin/grundausstattung").json()
        self.assertEqual(d["basis"]["keys"], list(features.GRUNDAUSSTATTUNG))
        self.assertEqual(d["basis"]["on"], [])
        self.assertEqual((d["internet"]["frage"], d["internet"]["search_url"]), ("offen", False))
        self.assertEqual(d["names"]["chat.routing"], ["Gezielte Werkzeugwahl", "Targeted tool choice"])
        self.assertEqual(ADMIN.get("/api/admin/switches").json()["grund"], d)

    def test_take_all_switches_on_and_keeps_it_for_undo(self):
        r = ADMIN.post("/api/admin/grundausstattung", json={"teil": "basis", "on": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sorted(r.json()["turned"]), sorted(features.GRUNDAUSSTATTUNG))
        c = ADMIN.get("/api/config").json()["chat"]
        self.assertTrue(all(c[k.split(".", 1)[1]] is True for k in features.GRUNDAUSSTATTUNG))
        self.assertFalse(any(c[k.split(".", 1)[1]] for k in features.GRUND_INTERNET), "never the internet part")
        x = ADMIN.get("/api/admin/undo").json()["items"][0]
        self.assertEqual(len(x["changes"]), len(features.GRUNDAUSSTATTUNG))
        self.assertEqual(ADMIN.post(f"/api/admin/undo/{x['id']}").status_code, 200)
        self.assertFalse(ADMIN.get("/api/config").json()["chat"]["routing"])
        again = ADMIN.post("/api/admin/grundausstattung", json={"teil": "basis", "on": True})
        self.assertEqual(len(again.json()["turned"]), len(features.GRUNDAUSSTATTUNG))
        self.assertEqual(ADMIN.post("/api/admin/grundausstattung", json={"teil": "basis", "on": True}).json()["turned"], [])

    def test_internet_yes_no_and_the_search_only_with_an_address(self):
        r = ADMIN.post("/api/admin/grundausstattung", json={"teil": "internet", "on": False})
        self.assertEqual((r.status_code, r.json()["turned"], r.json()["internet"]["frage"]), (200, [], "nein"))
        self.assertFalse(ADMIN.get("/api/config").json()["chat"]["weather"])
        r = ADMIN.post("/api/admin/grundausstattung", json={"teil": "internet", "on": True})
        self.assertEqual(sorted(r.json()["turned"]), ["chat.svc_watch", "chat.weather", "chat.wiki"])
        self.assertEqual(r.json()["internet"]["frage"], "ja")
        helpers.set_config(search_url="http://127.0.0.1:9/")
        r = ADMIN.post("/api/admin/grundausstattung", json={"teil": "internet", "on": True})
        self.assertEqual(r.json()["turned"], ["chat.search"])

    def test_wrong_requests_and_never_switching_off(self):
        for body in ({"teil": "basis", "on": False}, {"teil": "alles", "on": True}, {"teil": "basis", "on": "ja"}, {}):
            self.assertEqual(ADMIN.post("/api/admin/grundausstattung", json=body).status_code, 400, body)
        self.assertEqual(ADMIN.post("/api/admin/grundausstattung", content=b"x" * 4096,
                                    headers={"Content-Type": "application/json"}).status_code, 413)
        cfg = ADMIN.get("/api/config").json()
        cfg["chat"]["grund_internet"] = "vielleicht"
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)

    def test_only_the_admin(self):
        guest = TestClient(panel.app)
        self.assertEqual(guest.get("/api/admin/grundausstattung").status_code, 401)
        self.assertEqual(guest.post("/api/admin/grundausstattung", json={"teil": "basis", "on": True}).status_code, 401)
        self.assertFalse(any(p.fullmatch("/api/admin/grundausstattung") for _, p in coadmin.MANAGER),
                         "a Verwalter never switches functions (Dominik 2026-10-14)")

    def test_the_page_asks_for_the_card_only_as_admin(self):
        """A profile's page start never asks the admin endpoint: its 401 opened the admin sign-in over the page (V01.0.742)."""
        with open(os.path.join(PANEL, "static", "js", "guides.js"), encoding="utf-8") as f:
            guides = f.read()
        with open(os.path.join(PANEL, "static", "js", "start.js"), encoding="utf-8") as f:
            start = f.read()
        self.assertIn("async function grundLoad(){if(!ADMIN)return;", guides)
        admin = re.search(r"else\{\$\('logoutbtn'\)[^\n]*", start)
        self.assertTrue(admin and "grundLoad()" in admin.group(0), "start.js loads the card once whoami named the admin")


class FirstChat(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "spark_help", "feature_tips", "feature_sentences")
        helpers.set_config(spark_help=True, feature_tips=True, feature_sentences=True)
        self.uid = profile("GrundNeu")
        self.addCleanup(tipps.forget, self.uid)

    def test_first_example_says_where_the_settings_are(self):
        items = saetze.start(self.uid, now=1_800_000_000)
        self.assertEqual((items[0]["tool"], items[0]["text"]), ("spark_hilfe", list(saetze.HELP_START)))
        self.assertEqual(len(items), saetze.MAX_START)
        self.assertNotEqual(saetze.start(self.uid, now=1_800_000_000, n=1)[0]["tool"], "spark_hilfe",
                            "never the sentence of the week")

    def test_gone_once_the_profile_asked_the_spark(self):
        tipps._mut(self.uid, lambda st: st["used"].update(spark_hilfe=1_800_000_000))
        self.assertNotIn("spark_hilfe", [x["tool"] for x in saetze.start(self.uid, now=1_800_000_000)])

    def test_not_without_the_help(self):
        helpers.set_config(spark_help=False)
        self.assertNotIn("spark_hilfe", [x["tool"] for x in saetze.start(self.uid, now=1_800_000_000)])


if __name__ == "__main__":
    unittest.main()
