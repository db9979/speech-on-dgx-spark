"""Umfragen in Chats (Nextcloud-Ideen 4, umfrage.py): a question with 2 to 10 answers as a message in a chat of this Spark.

- Off (chat.chats_polls, default off): the endpoints say no, the state says polls false.
- On: 2 to 10 different answers, never in a private chat; question and answers sealed at rest (never plain text);
  every member votes (one, or several with „Mehrere“), changes and takes back the vote; who voted is seen only by the
  members, by name; nobody outside the chat votes or reads it.
- Only who asked closes it; then no vote counts; the winner is the answer with the most votes (the first on a tie),
  ON_CLOSE of its art runs once with it. A poll cannot be changed; taking the message back takes it along.
- Journal with fixed words only, Live with numbers only.
"""
import contextlib
import io
import json
import os
import unittest

from tests import helpers

helpers.start()
import chats  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import umfrage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "2468"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "2468"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Umfrage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.aid = profile("Umfrage Ute")
        cls.b, cls.bid = profile("Umfrage Udo")
        cls.c, cls.cid_ = profile("Umfrage Uwe")

    def setUp(self):
        helpers.keep_chat(self, "chats", "chats_groups", "chats_polls")
        helpers.set_config(chats=True, chats_groups=True, chats_polls=True)
        r = self.a.post("/api/chats/group", json={"name": "Grillen", "members": [self.bid]})
        self.assertEqual(r.status_code, 200, r.text)
        self.cid = r.json()["id"]

    def make(self, client=None, **kw):
        body = dict({"id": self.cid, "q": "Wann grillen wir?", "opts": ["Samstag", "Sonntag", "Montag"]}, **kw)
        return (client or self.a).post("/api/chats/poll", json=body)

    def poll(self, client, mid):
        items = client.get("/api/chats/items", params={"id": self.cid}).json()["items"]
        return next(x for x in items if x["id"] == mid)

    def vote(self, client, mid, picks):
        return client.post("/api/chats/poll/vote", json={"id": self.cid, "mid": mid, "picks": picks})

    def test_off(self):
        helpers.set_config(chats_polls=False)
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["chats_polls"], False)
        self.assertEqual(self.make().status_code, 403)
        self.assertFalse(self.a.get("/api/chats").json()["polls"])
        helpers.set_config(chats_polls=True)
        self.assertTrue(self.a.get("/api/chats").json()["polls"])

    def test_wrong_answers_refused(self):
        for opts in (["Nur eine"], ["Ja", "ja"], [str(i) for i in range(11)], ["", " "], "Ja,Nein"):
            self.assertEqual(self.make(opts=opts).status_code, 400, opts)
        self.assertEqual(self.make(q="  ").status_code, 400)

    def test_sealed_and_votes(self):
        r = self.make()
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["item"]["id"]
        with open(chats._chat_file(self.cid), encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("Samstag", raw)                                            # sealed, never plain text
        self.assertNotIn("grillen", raw)
        p = self.poll(self.b, mid)
        self.assertEqual(p["text"], "📊 Wann grillen wir?")
        self.assertEqual(p["poll"]["opts"], ["Samstag", "Sonntag", "Montag"])
        self.assertFalse(self.poll(self.a, mid)["can_edit"])
        self.assertFalse(p["poll"]["can_close"])
        self.assertTrue(self.poll(self.a, mid)["poll"]["can_close"])
        self.assertEqual(self.vote(self.b, mid, [1]).status_code, 200)
        self.assertEqual(self.vote(self.b, mid, [0, 1]).status_code, 400)          # one answer without „Mehrere“
        self.assertEqual(self.vote(self.b, mid, [7]).status_code, 400)
        self.assertEqual(self.vote(self.c, mid, [0]).status_code, 404)             # not a member
        self.assertEqual(self.vote(self.a, mid, [1]).status_code, 200)
        p = self.poll(self.a, mid)["poll"]
        self.assertEqual((p["n"], p["voters"], p["mine"]), ([0, 2, 0], 2, [1]))
        self.assertEqual(sorted(p["who"][1]), ["Umfrage Udo", "Umfrage Ute"])
        self.vote(self.b, mid, [2])                                                 # changes the vote
        self.vote(self.a, mid, [])                                                  # takes it back
        p = self.poll(self.b, mid)["poll"]
        self.assertEqual((p["n"], p["voters"], p["mine"]), ([0, 0, 1], 1, [2]))
        r = self.a.post("/api/chats/edit", json={"id": self.cid, "mid": mid, "text": "Anders"})
        self.assertEqual(r.status_code, 403)                                        # a poll cannot be changed

    def test_several_allowed(self):
        mid = self.make(multi=True).json()["item"]["id"]
        self.assertEqual(self.vote(self.b, mid, [0, 2, 2]).status_code, 200)
        self.assertEqual(self.poll(self.b, mid)["poll"]["mine"], [0, 2])
        self.assertEqual(self.vote(self.b, mid, [True]).status_code, 200)           # no number: nothing chosen
        self.assertEqual(self.poll(self.b, mid)["poll"]["mine"], [])

    def test_only_who_asked_closes(self):
        mid = self.make().json()["item"]["id"]
        seen = []
        umfrage.ON_CLOSE["test"] = lambda *a: seen.append(a)
        self.addCleanup(umfrage.ON_CLOSE.pop, "test", None)
        self.vote(self.b, mid, [2])
        self.vote(self.a, mid, [1])
        r = self.b.post("/api/chats/poll/close", json={"id": self.cid, "mid": mid})
        self.assertEqual(r.status_code, 403)
        r = self.a.post("/api/chats/poll/close", json={"id": self.cid, "mid": mid})
        self.assertEqual(r.json()["win"], 1)                                        # tie: the first
        p = self.poll(self.b, mid)["poll"]
        self.assertTrue(p["closed"])
        self.assertEqual(p["win"], 1)
        self.assertEqual(self.vote(self.b, mid, [0]).status_code, 403)              # closed: nothing counts
        self.assertEqual(self.a.post("/api/chats/poll/close", json={"id": self.cid, "mid": mid}).status_code, 403)
        self.assertEqual(seen, [])                                                  # only its own art
        mid2 = self.make(opts=["Ja", "Nein"]).json()["item"]["id"]
        chats._mutate(self.cid, lambda m, d, _: next(x for x in d["items"] if x["id"] == mid2)["poll"].update(art="test"))
        self.vote(self.b, mid2, [1])
        self.assertEqual(umfrage.schliessen(self.aid, self.cid, mid2), 1)
        self.assertEqual([(a[2], a[4]) for a in seen], [(mid2, 1)])

    def test_taken_back_with_the_message(self):
        mid = self.make().json()["item"]["id"]
        self.assertEqual(self.a.post("/api/chats/back", json={"id": self.cid, "mid": mid}).status_code, 200)
        p = self.poll(self.b, mid)
        self.assertNotIn("poll", p)
        with open(chats._chat_file(self.cid), encoding="utf-8") as f:
            stored = next(x for x in json.load(f)["items"] if x["id"] == mid)
        self.assertNotIn("poll", stored)                                            # nothing of it stays
        self.assertEqual(self.vote(self.b, mid, [0]).status_code, 404)

    def test_live_and_journal_numbers_only(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mid = self.make().json()["item"]["id"]
            self.vote(self.b, mid, [0])
            self.a.post("/api/chats/poll/close", json={"id": self.cid, "mid": mid})
        text = out.getvalue()
        self.assertIn("chats: poll made", text)
        self.assertIn("chats: poll vote", text)
        self.assertIn("chats: poll closed", text)
        for word in ("grillen", "Samstag", "Udo"):
            self.assertNotIn(word, text)
        v = umfrage.for_live()
        self.assertTrue(v["on"])
        self.assertGreaterEqual(v["gestellt"], 1)
        self.assertEqual(set(v), {"on", "gestellt", "stimmen"})
        self.assertIn("umfrage", chats.LIVE)
        self.assertEqual(chats.PUBLIC.count(umfrage.public), 1)
        self.assertTrue(live)


if __name__ == "__main__":
    unittest.main()
