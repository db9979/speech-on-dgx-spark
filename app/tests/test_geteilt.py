"""Teilen mit Profilen (geteilt.py, Ich → Geteilt): off until the admin releases it, a document to single profiles
only by its owner and only to profiles that may use it, found in the other's search while shared and gone at once
when taken back, never for guests, a blocked profile or a device key; the page lists both directions; one note per
profile at most every NOTE_GAP seconds; Live gets numbers only."""
import asyncio
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import features  # noqa: E402
import geteilt  # noqa: E402
import guard  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
import wissen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TEXT = b"Garage: der Code fuer das Tor steht auf der Rueckseite der Fernbedienung, Batterie CR2032. " * 3


def profile(name, pin="2468"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def upload(c, name, data=TEXT):
    r = c.post("/api/profile/docs", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def block(uid, key, on=True):
    """The admin blocks a function for one profile (chat.deny), or lifts it."""
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        deny = dict(json.load(f)["chat"].get("deny") or {})
    deny[key] = [u for u in deny.get(key, []) if u != uid] + ([uid] if on else [])
    helpers.set_config(deny=deny)


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(documents=True, share=True, doc_shared=False, doc_pictures=False, doc_semantic=False, deny={})
        for k in [k for k in guard._rate if k[0] in ("doc", "teilen", "geteilt")]:
            guard._rate.pop(k, None)
        geteilt._note.clear()
        self.sent = []

        async def fake_send(uid, title, body, tag="", **kw):
            self.sent.append((uid, title, body, tag))
            return 1
        self.push = mock.patch.object(push, "send", fake_send)
        self.push.start()

    def tearDown(self):
        self.push.stop()
        helpers.set_config(share=False, deny={})

    def share(self, c, doc, to, level="see"):
        return c.put(f"/api/profile/teilen/doc/{doc}", json={"to": to, "level": level})


class Off(Base):
    def test_off_by_default_and_never_for_guests(self):
        own = profile("Tgerda")
        doc = upload(own, "garage.txt")
        helpers.set_config(share=False)
        self.assertFalse(features.admin_on("teilen"))
        self.assertEqual(own.get("/api/profile/geteilt").status_code, 403)
        self.assertEqual(own.get(f"/api/profile/teilen/doc/{doc}").status_code, 403)
        self.assertEqual(self.share(own, doc, uid_of("Tgerda")).status_code, 403)
        self.assertEqual(geteilt.for_live(), {"on": False})
        guest = TestClient(panel.app)
        self.assertEqual(guest.get("/api/profile/geteilt").status_code, 401)
        self.assertEqual(guest.put(f"/api/profile/teilen/doc/{doc}", json={"to": "u_000000000000", "level": "see"}).status_code, 401)


class Documents(Base):
    def test_one_document_to_one_profile_found_while_shared_gone_when_taken_back(self):
        own, other, third = profile("Thanna"), profile("Tigor"), profile("Tjule")
        doc = upload(own, "garage.txt")
        upload(own, "privat.txt", b"Garage Kontostand geheim. " * 3)
        u_o, u_t = uid_of("Tigor"), uid_of("Tjule")
        self.assertEqual(asyncio.run(wissen.search(u_o, "Garage Fernbedienung")), [])
        r = own.get(f"/api/profile/teilen/doc/{doc}").json()
        self.assertEqual((r["name"], r["levels"], r["all"]), ("garage.txt", ["see"], None))   # „Für alle“ is off
        self.assertIn({"id": u_o, "name": "Tigor", "level": "", "can": True}, r["people"])
        self.assertEqual(self.share(own, doc, u_o).status_code, 200)
        hits = asyncio.run(wissen.search(u_o, "Garage Fernbedienung"))
        self.assertEqual({h["name"] for h in hits}, {"garage.txt"})            # never the one not shared
        self.assertEqual(hits[0]["owner"], "Thanna")
        self.assertEqual(asyncio.run(wissen.search(u_t, "Garage Fernbedienung")), [])   # nobody else
        self.assertEqual(other.get(f"/api/profile/wissen/{doc}/text").json()["owner"], "Thanna")
        self.assertEqual(third.get(f"/api/profile/wissen/{doc}/text").status_code, 404)
        info = other.get("/api/profile/wissen").json()
        self.assertEqual([(d["name"], d["owner"]) for d in info["others"]], [("garage.txt", "Thanna")])
        self.assertEqual(own.get("/api/profile/wissen").json()["teil"], [doc])
        # only the owner shares: the other one cannot pass it on or take it back
        self.assertEqual(self.share(other, doc, u_t).status_code, 404)
        self.assertEqual(self.share(other, doc, uid_of("Thanna"), "").status_code, 404)
        # taken back: gone at once, in the search and the text
        self.assertEqual(self.share(own, doc, u_o, "").status_code, 200)
        self.assertEqual(asyncio.run(wissen.search(u_o, "Garage Fernbedienung")), [])
        self.assertEqual(other.get(f"/api/profile/wissen/{doc}/text").status_code, 404)

    def test_fixed_rules_level_profile_block_device_key(self):
        own, other = profile("Tkarl"), profile("Tlore")
        doc = upload(own, "garage.txt")
        u_own, u_o = uid_of("Tkarl"), uid_of("Tlore")
        self.assertEqual(self.share(own, doc, u_o, "add").status_code, 400)        # documents: only „Sehen“
        self.assertEqual(self.share(own, doc, u_own).status_code, 400)            # not oneself
        self.assertEqual(self.share(own, doc, "u_000000000000").status_code, 400)  # no such profile
        self.assertEqual(self.share(own, "0123456789ab", u_o).status_code, 404)  # no such document
        self.assertEqual(own.put(f"/api/profile/teilen/doc/{doc}", content=b"x" * 2000,
                                 headers={"Content-Type": "application/json"}).status_code, 413)
        block(u_o, "teilen")                                                       # the admin blocked Lore
        self.assertEqual(self.share(own, doc, u_o).status_code, 400)
        self.assertEqual(other.get("/api/profile/geteilt").status_code, 403)
        block(u_o, "teilen", False)
        self.assertEqual(self.share(own, doc, u_o).status_code, 200)
        block(u_o, "documents")                                                    # a share stays, but is not seen
        self.assertEqual(asyncio.run(wissen.search(u_o, "Garage")), [])
        self.assertEqual(geteilt.doc_offer(u_o, u_own), frozenset())
        block(u_o, "documents", False)
        self.assertEqual(geteilt.doc_offer(u_o, u_own), frozenset({doc}))
        # a device key (speaker, Siri, the app) never shares or reads the page: only the own browser login
        for scope in (None, "app"):
            dev = TestClient(panel.app, headers={profiles.DEVICE_HEADER: profiles.add_device("Kueche", u_own, scope=scope)})
            self.assertIn(dev.put(f"/api/profile/teilen/doc/{doc}", json={"to": u_o, "level": ""}).status_code, (401, 403))
            self.assertIn(dev.get("/api/profile/geteilt").status_code, (401, 403))
        self.assertEqual(geteilt.doc_offer(u_o, u_own), frozenset({doc}))

    def test_for_everyone_is_one_row_of_the_dialog(self):
        own, other = profile("Tmia"), profile("Tnils")
        doc = upload(own, "garage.txt")
        r = own.put(f"/api/profile/teilen/doc/{doc}", json={"all": True})
        self.assertEqual(r.status_code, 403)                                        # Gemeinsame Dokumente is off
        helpers.set_config(doc_shared=True)
        self.assertEqual(own.put(f"/api/profile/teilen/doc/{doc}", json={"all": True}).json()["all"], True)
        page = other.get("/api/profile/geteilt").json()
        self.assertEqual([(x["name"], x["all"]) for x in page["theirs"] if x["kind"] == "doc"], [("garage.txt", True)])
        self.assertEqual([x for x in own.get("/api/profile/geteilt").json()["mine"] if x.get("all")][0]["id"], doc)
        self.assertEqual(own.put(f"/api/profile/teilen/doc/{doc}", json={"all": False}).json()["all"], False)


class Page(Base):
    def test_both_directions_new_once_and_a_deleted_document_is_shared_no_more(self):
        own, other = profile("Tole"), profile("Tpia")
        doc = upload(own, "garage.txt")
        u_o = uid_of("Tpia")
        self.share(own, doc, u_o)
        first = other.get("/api/profile/geteilt").json()
        self.assertEqual([(x["kind"], x["name"], x["who"], x["level"], x["new"]) for x in first["theirs"]],
                         [("doc", "garage.txt", "Tole", "see", True)])
        self.assertEqual(first["new"], 1)
        self.assertEqual(other.get("/api/profile/geteilt").json()["new"], 0)      # seen once it was opened
        mine = own.get("/api/profile/geteilt").json()["mine"]
        self.assertEqual([(x["kind"], x["id"], [p["name"] for p in x["people"]]) for x in mine], [("doc", doc, ["Tpia"])])
        self.assertIn("doc", own.get("/api/profile/geteilt").json()["kinds"])
        own.delete(f"/api/profile/docs/{doc}")
        self.assertEqual(own.get("/api/profile/geteilt").json()["mine"], [])
        self.assertEqual(other.get("/api/profile/geteilt").json()["theirs"], [])
        self.assertEqual(geteilt.doc_ids(uid_of("Tole")), frozenset())

    def test_calendars_and_lists_are_only_taken_back_here(self):
        own, other = profile("Tquentin"), profile("Trosa")
        u_o = uid_of("Trosa")
        for kind in ("cal", "list"):
            r = own.put(f"/api/profile/teilen/{kind}/x1", json={"to": u_o, "level": "see"})
            self.assertIn(r.status_code, (400, 404))
            self.assertEqual(own.get(f"/api/profile/teilen/{kind}/x1").status_code, 404)   # their own dialog
        self.assertEqual(own.put("/api/profile/teilen/bild/x1", json={"to": u_o, "level": "see"}).status_code, 404)

    def test_a_shared_list_shows_both_ways_and_is_taken_back_here(self):
        import tasks
        helpers.set_config(tasks=True, tasks_share=True)
        try:
            own, other = profile("Tlisa"), profile("Tlutz")
            u_own, u_o = uid_of("Tlisa"), uid_of("Tlutz")
            tasks.set_share(u_own, "einkauf", u_o, "add")
            mine = own.get("/api/profile/geteilt").json()["mine"]
            self.assertEqual([(x["kind"], x["id"], [p["level"] for p in x["people"]]) for x in mine if x["kind"] == "list"],
                             [("list", "einkauf", ["add"])])
            theirs = [x for x in other.get("/api/profile/geteilt").json()["theirs"] if x["kind"] == "list"]
            self.assertEqual([(x["id"], x["level"], x["owner"]) for x in theirs], [(f"{u_own}.einkauf", "add", u_own)])
            self.assertEqual(own.put("/api/profile/teilen/list/einkauf", json={"to": u_o, "level": ""}).status_code, 200)
            self.assertEqual(tasks.shared_to(u_o), [])
            self.assertEqual([x for x in other.get("/api/profile/geteilt").json()["theirs"] if x["kind"] == "list"], [])
        finally:
            helpers.set_config(tasks_share=False)


class Note(Base):
    def test_one_note_then_collected_and_off_by_preference(self):
        own, other = profile("Tsven"), profile("Ttina")
        a, b, c = upload(own, "a.txt"), upload(own, "b.txt"), upload(own, "c.txt")
        u_o = uid_of("Ttina")
        self.share(own, a, u_o)
        self.assertEqual(len(self.sent), 1)
        to, title, body, tag = self.sent[0]
        self.assertEqual((to, tag), (u_o, "share"))
        self.assertIn("Tsven", title)
        self.assertNotIn("a.txt", title + body)                                     # the title stays on the page
        self.assertIn("Ich → Geteilt", body)                                        # a way, a jump link everywhere
        self.share(own, b, u_o)
        self.assertEqual(len(self.sent), 1)                                         # within NOTE_GAP: collected
        self.assertEqual(geteilt._note[u_o]["n"], 1)
        self.share(own, b, u_o)                                                     # the same level again: no note
        self.assertEqual(geteilt._note[u_o]["n"], 1)
        geteilt._note.clear()
        self.assertEqual(other.put("/api/profile/settings", json={"share_note": False}).status_code, 200)
        self.share(own, c, u_o)
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(other.get("/api/profile/geteilt").json()["note"])
        other.put("/api/profile/settings", json={"share_note": True})


class Live(Base):
    def test_numbers_only(self):
        own, _ = profile("Tulf"), profile("Tvera")
        doc = upload(own, "garage-geheim.txt")
        self.assertEqual(self.share(own, doc, uid_of("Tvera")).status_code, 200)
        geteilt._live[0] = 0.0
        d = geteilt.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["docs"], 1)
        self.assertEqual(set(d), {"on", "docs", "owners", "set", "back"})
        self.assertNotIn("garage", json.dumps(d))
        self.assertNotIn("Tulf", json.dumps(d))


if __name__ == "__main__":
    unittest.main()
