"""The page „Listen“ (tasks.py, listen.js): own lists, who put an entry on and from where, „Erledigt“ with
„Zurückholen“, amounts, departments on shopping lists, the Heute card, and the rules every endpoint keeps."""
import contextlib
import io
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import tasks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def ask(client, text):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": text}]})
    assert r.status_code == 200, r.text
    return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")


class Listen(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "tasks")
        helpers.set_config(tasks=True)
        for k in [k for k in guard._rate if k[0] == "listen"]:
            guard._rate.pop(k, None)

    def test_due_and_meeting_source(self):
        """„bis“ of an entry (a meeting's task from the Begleiter, Dominik 2026-10-20): only a real date, kept and shown,
        set on an entry that had none; qty=False reads no amount; the source „aus Besprechung“."""
        import asyncio
        a = profile("Listen Bea")
        uid = uid_of("Listen Bea")
        self.assertTrue(tasks.due_ok("2026-10-24"))
        for bad in ("2026-02-30", "24.10.2026", "2026-10-24T10:00", "", None, 5):
            self.assertFalse(tasks.due_ok(bad), bad)
        asyncio.run(tasks.add(uid, "aufgaben", ["3 Angebote einholen"], src="besprechung", due="2026-10-24", qty=False))
        asyncio.run(tasks.add(uid, "aufgaben", ["Raum buchen"], src="besprechung", due="morgen", qty=False))
        asyncio.run(tasks.add(uid, "aufgaben", ["Raum buchen"], src="besprechung", due="2026-10-25", qty=False))
        rows = {x["text"]: x for x in a.get("/api/profile/tasks").json()["lists"]["aufgaben"]["items"]}
        self.assertEqual((rows["3 Angebote einholen"]["qty"], rows["3 Angebote einholen"]["due"]), ("", "2026-10-24"))
        self.assertEqual(rows["Raum buchen"]["due"], "2026-10-25")     # the second time it brought a date
        self.assertEqual(rows["Raum buchen"]["src"], "besprechung")
        self.assertEqual(a.get("/api/profile/tasks").json()["sources"]["besprechung"], ["aus Besprechung", "from a meeting"])
        d = tasks._load(uid)                                             # a broken date in the file is dropped
        d["items"][0]["due"] = "bald"
        tasks._save(uid, d)
        self.assertNotIn("due", tasks._load(uid)["items"][0])
        self.assertIn("DUE;VALUE=DATE:20261024", tasks._ical("x", "2026-10-24")[1].decode())

    def test_own_lists_who_when_done_and_back(self):
        a = profile("Listen Lea")
        r = a.post("/api/profile/listen", json={"name": "  Baumarkt  ", "icon": "🔧"})
        self.assertEqual(r.status_code, 200, r.text)
        lid = r.json()["made"]
        li = r.json()["lists"][lid]
        self.assertEqual((li["name"], li["own"], li["shop"]), ("Baumarkt", True, False))
        self.assertEqual(r.json()["order"][:2], ["einkauf", "aufgaben"])
        self.assertEqual(a.post("/api/profile/listen", json={"name": "baumarkt"}).status_code, 400)    # taken
        self.assertEqual(a.post("/api/profile/listen", json={"name": "Einkauf"}).status_code, 400)     # a fixed one
        self.assertEqual(a.post("/api/profile/listen", json={"name": "   "}).status_code, 400)
        # an entry: amount, who and from where
        r = a.post(f"/api/profile/tasks/{lid}", json={"text": "Schrauben 2x, Dübel"})
        rows = r.json()["lists"][lid]["items"]
        self.assertEqual([(x["text"], x["qty"], x["by_name"], x["src"]) for x in rows],
                         [("Schrauben", "2×", "Listen Lea", "panel"), ("Dübel", "", "Listen Lea", "panel")])
        self.assertTrue(all(x["t"] > 0 for x in rows))
        r = a.post(f"/api/profile/tasks/{lid}", json={"text": "3 Schrauben"})                         # adds up
        self.assertEqual([x["qty"] for x in r.json()["lists"][lid]["items"] if x["text"] == "Schrauben"], ["5×"])
        # ticked off: under „Erledigt“ with who, and back with „Zurückholen“
        sid = next(x["id"] for x in r.json()["lists"][lid]["items"] if x["text"] == "Schrauben")
        r = a.post(f"/api/profile/tasks/{lid}/done", json={"ids": [sid]})
        self.assertEqual([x["text"] for x in r.json()["lists"][lid]["items"]], ["Dübel"])
        self.assertEqual([(x["text"], x["done_name"]) for x in r.json()["lists"][lid]["done"]], [("Schrauben", "Listen Lea")])
        r = a.post(f"/api/profile/tasks/{lid}/undo", json={"ids": [sid]})
        self.assertEqual(sorted(x["text"] for x in r.json()["lists"][lid]["items"]), ["Dübel", "Schrauben"])
        self.assertEqual(r.json()["lists"][lid]["done"], [])
        # renamed, its symbol, one entry deleted, then the whole list
        r = a.put(f"/api/profile/listen/{lid}", json={"name": "Werkstatt", "icon": "🏠"})
        self.assertEqual((r.json()["lists"][lid]["name"], r.json()["lists"][lid]["icon"]), ("Werkstatt", "🏠"))
        self.assertEqual(a.put(f"/api/profile/listen/{lid}", json={"name": "Aufgaben"}).status_code, 400)
        self.assertEqual(a.put("/api/profile/listen/lnichtda", json={"name": "X"}).status_code, 404)
        r = a.delete(f"/api/profile/tasks/{lid}/{sid}")
        self.assertEqual([x["text"] for x in r.json()["lists"][lid]["items"]], ["Dübel"])
        r = a.delete(f"/api/profile/listen/{lid}")
        self.assertNotIn(lid, r.json()["lists"])
        self.assertEqual(a.post(f"/api/profile/tasks/{lid}", json={"text": "Nägel"}).status_code, 404)
        self.assertEqual(a.delete(f"/api/profile/listen/{lid}").status_code, 404)
        self.assertEqual(a.delete("/api/profile/listen/einkauf").status_code, 404)                   # fixed: stays

    def test_shopping_by_department_and_the_heute_card(self):
        a = profile("Listen Mia")
        r = a.post("/api/profile/tasks/einkauf", json={"text": "Milch, Äpfel, Spülmittel, Schraubenzieher"})
        li = r.json()["lists"]["einkauf"]
        self.assertTrue(li["shop"])
        dept = {x["text"]: x["dept"] for x in li["items"]}
        self.assertNotEqual(dept["Milch"], dept["Äpfel"])
        self.assertIn(tasks.OTHER_DEPT[0], [d[0] for d in r.json()["depts"]])
        self.assertNotIn("dept", r.json()["lists"]["aufgaben"]["items"][:1] and r.json()["lists"]["aufgaben"]["items"][0] or {})
        uid = uid_of("Listen Mia")
        c = tasks.card(uid)
        self.assertEqual((c["open"], c["shopping"], c["lists"]), (4, 4, 2))
        self.assertEqual(c["first"][0], "Schraubenzieher")
        home = a.get("/api/profile/today").json()
        self.assertEqual(home["cards"]["tasks"]["shopping"], 4)

    def test_assistant_puts_on_an_own_list_and_never_makes_one(self):
        a = profile("Listen Ole")
        lid = a.post("/api/profile/listen", json={"name": "Baumarkt"}).json()["made"]
        self.assertIn("gesetzt: Schrauben", ask(a, 'TOOL tasks_add {"list": "Baumarkt", "items": ["Schrauben"]}'))
        row = a.get("/api/profile/tasks").json()["lists"][lid]["items"][0]
        self.assertEqual((row["text"], row["by_name"], row["src"]), ("Schrauben", "Listen Ole", "assistent"))
        self.assertIn("gesetzt: Dübel", ask(a, 'TOOL tasks_add {"list": "Baumarkt-Liste", "items": ["Dübel"]}'))
        self.assertEqual(len(a.get("/api/profile/tasks").json()["lists"][lid]["items"]), 2)
        out = ask(a, 'TOOL tasks_add {"list": "Gartencenter", "items": ["Erde"]}')
        self.assertIn("Nicht geändert", out)
        self.assertNotIn("Gartencenter", [x["name"] for x in a.get("/api/profile/tasks").json()["lists"].values()])

    def test_the_iphone_app_with_the_release_of_the_lists(self):
        from tests.test_iphone import pair
        import iphone
        helpers.keep_chat(self, "iphone")
        helpers.set_config(iphone=True)
        iphone._pending.clear()
        for k in [k for k in guard._rate if k[0] == "pair"]:
            guard._rate.pop(k, None)
        a = profile("Listen Uwe")
        app = TestClient(panel.app)
        h = {"X-Speech-Device": pair(a).json()["token"]}
        self.assertTrue(app.get("/api/iphone/hello", headers=h).json()["areas"]["tasks"])
        r = app.post("/api/profile/tasks/einkauf/add", json={"text": "Tee"}, headers=h)   # Meine Sachen → Listen
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([(x["text"], x["src"]) for x in r.json()["lists"]["einkauf"]["items"]], [("Tee", "app")])
        self.assertEqual(app.post("/api/profile/tasks/einkauf", json={"text": "Kaffee"}, headers=h).status_code, 403)  # the shortcut: app_ios
        self.assertEqual(app.get("/api/profile/tasks/collections", headers=h).status_code, 401)    # stays in the browser
        helpers.set_config(deny={"tasks": [uid_of("Listen Uwe")]})
        self.addCleanup(helpers.set_config, deny={})
        self.assertEqual(app.get("/api/profile/tasks", headers=h).status_code, 401)

    def test_every_endpoint_keeps_the_rules(self):
        guest = TestClient(panel.app)
        for m, p in (("get", "/api/profile/tasks"), ("post", "/api/profile/listen"), ("post", "/api/profile/tasks/einkauf"),
                     ("post", "/api/profile/tasks/einkauf/done"), ("delete", "/api/profile/listen/l1")):
            self.assertIn(getattr(guest, m)(p, **({"json": {}} if m == "post" else {})).status_code, (401, 403), p)
        a = profile("Listen Ina")
        uid = uid_of("Listen Ina")
        self.assertEqual(a.post("/api/profile/tasks/einkauf", content=b"x" * 20000,
                                headers={"Content-Type": "application/json"}).status_code, 413)
        self.assertEqual(a.post("/api/profile/listen", content=b"{" + b" " * 9000 + b"}",
                                headers={"Content-Type": "application/json"}).status_code, 413)
        a.post("/api/profile/tasks/einkauf", json={"text": "Brot"})
        # blocked by the admin: nothing new, but the own data stays visible and deletable
        r = ADMIN.put(f"/api/admin/features/tasks/profiles/{uid}", json={"on": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.addCleanup(ADMIN.put, f"/api/admin/features/tasks/profiles/{uid}", json={"on": True})
        self.assertEqual(a.post("/api/profile/tasks/einkauf", json={"text": "Käse"}).status_code, 403)
        self.assertEqual(a.post("/api/profile/listen", json={"name": "Neu"}).status_code, 403)
        self.assertEqual(a.get("/api/profile/tasks").status_code, 200)
        ADMIN.put(f"/api/admin/features/tasks/profiles/{uid}", json={"on": True})
        # off for everyone: off everywhere
        helpers.set_config(tasks=False)
        self.assertEqual(a.get("/api/profile/tasks").status_code, 403)
        helpers.set_config(tasks=True)
        # too often in a minute
        old = guard.RATE["listen"]
        guard.RATE["listen"] = (0, 3)
        self.addCleanup(guard.RATE.__setitem__, "listen", old)
        codes = [a.get("/api/profile/tasks").status_code for _ in range(5)]
        self.assertEqual(codes[-1], 429, codes)

    def test_the_journal_never_carries_names_or_entries(self):
        a = profile("Listen Kai")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            lid = a.post("/api/profile/listen", json={"name": "Geheimprojekt"}).json()["made"]
            a.post(f"/api/profile/tasks/{lid}", json={"text": "Tresorschlüssel"})
            a.post("/api/profile/tasks/einkauf", json={"text": "Tresorschlüssel"})
            a.delete(f"/api/profile/listen/{lid}")
        log = out.getvalue()
        live = tasks.for_live()   # Zustand → Live: only how many
        self.assertGreaterEqual((live["added"], live["lists"] >= 0), (2, True))
        self.assertNotIn("Geheimprojekt", str(live))
        self.assertIn("tasks: list make | ok", log)
        self.assertIn("tasks: add own | 1 entries", log)
        self.assertIn("tasks: add einkauf | 1 entries", log)
        self.assertIn("tasks: list delete | 1 entries", log)
        for word in ("Geheimprojekt", "Tresorschlüssel", "Listen Kai"):
            self.assertNotIn(word, log)


class Teilen(unittest.TestCase):
    """Stufe 2 (Dominik 2026-10-20 „3a“): an own list shared with another profile, see or put on and tick off; deleting
    and sharing stay with the owner; taking it back holds at once; a note when others put something on."""

    def setUp(self):
        helpers.keep_chat(self, "tasks", "tasks_share", "deny")
        helpers.set_config(tasks=True, tasks_share=True, deny={})
        for k in [k for k in guard._rate if k[0] == "listen"]:
            guard._rate.pop(k, None)

    def test_see_add_and_back(self):
        owner, other, third = profile("Mitlist Sabine"), profile("Mitlist Tom"), profile("Mitlist Uli")
        so, to = uid_of("Mitlist Sabine"), uid_of("Mitlist Tom")
        owner.post("/api/profile/tasks/einkauf", json={"text": "Milch"})
        key = f"{so}.einkauf"
        self.assertNotIn(key, other.get("/api/profile/tasks").json()["lists"])          # nothing before sharing
        self.assertEqual(other.post(f"/api/profile/tasks/{key}", json={"text": "Kekse"}).status_code, 404)
        r = owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "see"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["lists"]["einkauf"]["shares"], {to: "see"})
        self.assertIn({"id": to, "name": "Mitlist Tom"}, r.json()["people"])
        seen = other.get("/api/profile/tasks").json()
        self.assertEqual(seen["lists"][key]["shared"], {"owner": "Mitlist Sabine", "level": "see"})
        self.assertEqual([x["text"] for x in seen["lists"][key]["items"]], ["Milch"])
        self.assertEqual(other.post(f"/api/profile/tasks/{key}", json={"text": "Kekse"}).status_code, 403)   # see only
        self.assertNotIn(key, third.get("/api/profile/tasks").json()["lists"])          # never someone else
        # Mitschreiben: put on and tick off, with who; deleting and sharing stay with the owner
        owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "add"})
        r = other.post(f"/api/profile/tasks/{key}", json={"text": "Kekse"})
        self.assertEqual(r.status_code, 200, r.text)
        mine = owner.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"]
        kekse = next(x for x in mine if x["text"] == "Kekse")
        self.assertEqual(kekse["by_name"], "Mitlist Tom")
        self.assertEqual(other.delete(f"/api/profile/tasks/{key}/{kekse['id']}").status_code, 404)
        self.assertEqual(other.put(f"/api/profile/listen/{key}/share", json={"to": so, "level": "add"}).status_code, 404)
        r = other.post(f"/api/profile/tasks/{key}/done", json={"ids": [kekse["id"]]})
        self.assertEqual(r.json()["lists"][key]["done"][0]["done_name"], "Mitlist Tom")
        # taken back: at once
        owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": ""})
        self.assertNotIn(key, other.get("/api/profile/tasks").json()["lists"])
        self.assertEqual(other.post(f"/api/profile/tasks/{key}/add", json={"text": "Wein"}).status_code, 404)
        self.assertEqual(owner.put("/api/profile/listen/einkauf/share", json={"to": so, "level": "see"}).status_code, 400)
        self.assertEqual(owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "all"}).status_code, 400)

    def test_switch_off_and_blocked_close_it(self):
        owner, other = profile("Mitlist Vera"), profile("Mitlist Willi")
        so, to = uid_of("Mitlist Vera"), uid_of("Mitlist Willi")
        owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "add"})
        key = f"{so}.einkauf"
        self.assertIn(key, other.get("/api/profile/tasks").json()["lists"])
        helpers.set_config(deny={"listshare": [so]})          # the owner blocked: nobody reaches it
        self.assertNotIn(key, other.get("/api/profile/tasks").json()["lists"])
        helpers.set_config(deny={})
        helpers.set_config(tasks_share=False)                 # off for everyone
        self.assertNotIn(key, other.get("/api/profile/tasks").json()["lists"])
        self.assertEqual(owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "see"}).status_code, 403)

    def test_by_voice_and_outside(self):
        owner, other = profile("Mitlist Xenia"), profile("Mitlist Yann")
        so, to = uid_of("Mitlist Xenia"), uid_of("Mitlist Yann")
        owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "add"})
        self.assertIn("gesetzt: Butter", ask(other, 'TOOL tasks_add {"list": "Mitlist Xenias Einkaufsliste", "items": ["Butter"]}'))
        row = next(x for x in owner.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"] if x["text"] == "Butter")
        self.assertEqual((row["by_name"], row["src"]), ("Mitlist Yann", "assistent"))
        self.assertIn("Löschen darf", ask(other, 'TOOL tasks_change {"list": "Mitlist Xenias Einkaufsliste", "items": ["Butter"], "action": "delete"}'))
        # what others wrote is outside text: after reading it nothing is added in the same answer
        helpers.LLM_CALLS.clear()
        out = ask(other, 'TOOL tasks_show {"list": "Einkauf von Mitlist Xenia"}')
        self.assertIn("Butter", out)
        self.assertNotIn("tasks_add", [t["function"]["name"] for t in helpers.LLM_CALLS[-1].get("tools", [])])

    def test_a_note_for_the_others(self):
        import asyncio
        import push
        owner, other = profile("Mitlist Zora"), profile("Mitlist Anton")
        so, to = uid_of("Mitlist Zora"), uid_of("Mitlist Anton")
        owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "add"})
        sent = []

        async def fake(uid, title, body, tag="", **kw):
            sent.append((uid, body, tag))
            return 1
        real = push.send
        push.send = fake
        self.addCleanup(setattr, push, "send", real)
        tasks._notes.clear()
        tasks._tell(so, "einkauf", to, 2)                    # Anton put two on Zora's list
        tasks._tell(so, "einkauf", to, 1)
        self.assertEqual(asyncio.run(tasks._flush((so, so, "einkauf"))), 1)
        self.assertEqual(sent, [(so, "Mitlist Anton hat 3 Einträge auf „Einkauf“ gesetzt.", "listen")])
        self.assertNotIn((to, so, "einkauf"), tasks._notes)   # never to the one who wrote
        # the profile's own preference off: no note
        owner.put("/api/profile/settings", json={"list_note": False})
        tasks._tell(so, "einkauf", to, 1)
        self.assertEqual(asyncio.run(tasks._flush((so, so, "einkauf"))), 0)
        owner.put("/api/profile/settings", json={"list_note": True})

    def test_journal_says_shared_never_names(self):
        owner, other = profile("Mitlist Berta"), profile("Mitlist Carl")
        so, to = uid_of("Mitlist Berta"), uid_of("Mitlist Carl")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            owner.put("/api/profile/listen/einkauf/share", json={"to": to, "level": "add"})
            other.post(f"/api/profile/tasks/{so}.einkauf", json={"text": "Geheimkäse"})
        log = out.getvalue()
        self.assertIn("tasks: list share | ok add", log)
        self.assertIn("tasks: add einkauf shared | 1 entries", log)
        for word in ("Geheimkäse", "Mitlist Berta", "Mitlist Carl"):
            self.assertNotIn(word, log)
        self.assertGreaterEqual(tasks.for_live()["shares"], 1)


class AppleStil(unittest.TestCase):
    """Apple-Stil Stufe 4 (Dominik 2026-10-20 „7a“): like Apple's Reminders. Info per entry (note, date, time, flag,
    priority) checked by the panel, „Erinnern“ as a reminder of Timer und Erinnerungen that follows ticking off,
    taking back and deleting, moving onto another list (away only the owner, onto it only with Mitschreiben), the
    order of entries and lists, the colour of every list, the rules of every new endpoint, the journal without names.
    The dates lie in 2099, so nothing depends on today."""

    def setUp(self):
        helpers.keep_chat(self, "tasks", "tasks_share", "reminders", "deny")
        helpers.set_config(tasks=True, tasks_share=True, reminders=True, deny={})
        for k in [k for k in guard._rate if k[0] == "listen"]:
            guard._rate.pop(k, None)

    def test_info_of_an_entry(self):
        a = profile("Apfel Anna")
        a.post("/api/profile/tasks/aufgaben", json={"text": "Reifen wechseln"})
        x = a.get("/api/profile/tasks").json()["lists"]["aufgaben"]["items"][0]
        self.assertEqual((x["note"], x["at"], x["flag"], x["prio"], x["remind"]), ("", "", False, 0, False))
        path = f"/api/profile/tasks/aufgaben/{x['id']}"
        r = a.put(path, json={"note": "Winterreifen\nim Keller", "due": "2099-03-01", "at": "17:30", "flag": True, "prio": 3})
        self.assertEqual(r.status_code, 200, r.text)
        y = r.json()["lists"]["aufgaben"]["items"][0]
        self.assertEqual((y["note"], y["due"], y["at"], y["flag"], y["prio"]), ("Winterreifen\nim Keller", "2099-03-01", "17:30", True, 3))
        for bad in ({"at": "25:00"}, {"prio": 7}, {"due": "morgen"}, {"text": "  "}):
            self.assertEqual(a.put(path, json=bad).status_code, 400, bad)
        self.assertEqual(a.put("/api/profile/tasks/aufgaben/ffffffffff", json={"flag": True}).status_code, 404)
        y = a.put(path, json={"due": "", "flag": False, "prio": 0, "note": ""}).json()["lists"]["aufgaben"]["items"][0]
        self.assertEqual((y["due"], y["at"], y["flag"], y["prio"], y["note"]), ("", "", False, 0, ""))   # no time without a date
        y = a.put(path, json={"text": "3 Reifen"}).json()["lists"]["aufgaben"]["items"][0]
        self.assertEqual((y["text"], y["qty"]), ("Reifen", "3×"))

    def test_remind_follows_the_entry(self):
        import profiles
        a = profile("Apfel Bert")
        uid = uid_of("Apfel Bert")
        a.post("/api/profile/tasks/einkauf", json={"text": "Äpfel"})
        x = a.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"][0]
        path = f"/api/profile/tasks/einkauf/{x['id']}"
        mine = lambda: [r for r in profiles.reminders(uid) if r["text"].startswith("Äpfel")]
        a.put(path, json={"due": "2099-03-01", "remind": True})
        self.assertEqual(mine(), [])                                  # no time: nothing rings
        a.put(path, json={"at": "17:00"})
        self.assertEqual(len(mine()), 1)
        self.assertEqual(mine()[0]["text"], "Äpfel (Einkauf)")
        a.put(path, json={"at": "18:00"})                             # a new time: one reminder, the new one
        self.assertEqual(len(mine()), 1)
        a.post("/api/profile/tasks/einkauf/done", json={"ids": [x["id"]]})
        self.assertEqual(mine(), [])                                  # ticked off: gone
        a.post("/api/profile/tasks/einkauf/undo", json={"ids": [x["id"]]})
        self.assertEqual(len(mine()), 1)                              # taken back: it comes again
        a.delete(path)
        self.assertEqual(mine(), [])                                  # deleted: gone
        # without Timer und Erinnerungen the entry keeps „Erinnern“, but nothing rings
        a.post("/api/profile/tasks/einkauf", json={"text": "Birnen"})
        y = next(x for x in a.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"] if x["text"] == "Birnen")
        helpers.set_config(reminders=False)
        r = a.put(f"/api/profile/tasks/einkauf/{y['id']}", json={"due": "2099-03-01", "at": "08:00", "remind": True})
        self.assertFalse(r.json()["reminders"])
        self.assertEqual([r for r in profiles.reminders(uid) if r["text"].startswith("Birnen")], [])

    def test_move_order_and_colours(self):
        owner, other = profile("Apfel Cora"), profile("Apfel Dirk")
        so, to = uid_of("Apfel Cora"), uid_of("Apfel Dirk")
        lid = owner.post("/api/profile/listen", json={"name": "Baumarkt", "icon": "🔨", "color": "gruen"}).json()["made"]
        owner.post("/api/profile/tasks/aufgaben", json={"text": "Dübel, Schrauben, Leim"})
        items = owner.get("/api/profile/tasks").json()["lists"]["aufgaben"]["items"]
        self.assertEqual([x["text"] for x in items], ["Dübel", "Schrauben", "Leim"])     # in the order typed
        ids = {x["text"]: x["id"] for x in items}
        r = owner.put("/api/profile/tasks/aufgaben/order", json={"ids": [ids["Leim"], ids["Dübel"]]})
        self.assertEqual([x["text"] for x in r.json()["lists"]["aufgaben"]["items"]], ["Leim", "Dübel", "Schrauben"])
        owner.put(f"/api/profile/tasks/aufgaben/{ids['Leim']}", json={"note": "Holzleim", "flag": True})
        r = owner.put(f"/api/profile/tasks/aufgaben/{ids['Leim']}", json={"to": lid})
        self.assertEqual(r.status_code, 200, r.text)
        moved = r.json()["lists"][lid]["items"]
        self.assertEqual([(x["text"], x["note"], x["flag"]) for x in moved], [("Leim", "Holzleim", True)])  # keeps its info
        self.assertNotIn("Leim", [x["text"] for x in r.json()["lists"]["aufgaben"]["items"]])
        self.assertEqual(owner.put(f"/api/profile/tasks/{lid}/{ids['Leim']}", json={"to": lid}).status_code, 400)
        # colours: every list, a fixed one too; a colour not in the choice changes nothing
        self.assertEqual(r.json()["lists"][lid]["color"], "gruen")
        self.assertEqual(r.json()["lists"]["einkauf"]["color"], "orange")
        r = owner.put("/api/profile/listen/einkauf", json={"color": "lila"})
        self.assertEqual(r.json()["lists"]["einkauf"]["color"], "lila")
        self.assertEqual(owner.put("/api/profile/listen/einkauf", json={"color": "#ff0000"}).status_code, 400)
        self.assertEqual(owner.put("/api/profile/listen/einkauf", json={"name": "Shop"}).status_code, 400)
        # the order of the lists: what was dragged first, the rest after it; unknown ids are dropped
        r = owner.put("/api/profile/listen/order", json={"order": [lid, "aufgaben", "lffffffff", "<b>"]})
        self.assertEqual(r.json()["order"][:3], [lid, "aufgaben", "einkauf"])
        # shared: see only takes nothing; Mitschreiben may put on, sort and change info, but never move away
        owner.put("/api/profile/listen/aufgaben/share", json={"to": to, "level": "see"})
        key = f"{so}.aufgaben"
        self.assertEqual(other.put(f"/api/profile/tasks/{key}/{ids['Dübel']}", json={"flag": True}).status_code, 403)
        self.assertEqual(owner.put(f"/api/profile/tasks/aufgaben/{ids['Dübel']}", json={"to": f"{to}.einkauf"}).status_code, 404)
        owner.put("/api/profile/listen/aufgaben/share", json={"to": to, "level": "add"})
        self.assertEqual(other.put(f"/api/profile/tasks/{key}/{ids['Dübel']}", json={"prio": 2}).status_code, 200)
        self.assertEqual(other.put(f"/api/profile/tasks/{key}/order", json={"ids": [ids["Schrauben"]]}).status_code, 200)
        self.assertEqual(other.put(f"/api/profile/tasks/{key}/{ids['Dübel']}", json={"to": "einkauf"}).status_code, 404)
        r = owner.put(f"/api/profile/tasks/aufgaben/{ids['Dübel']}", json={"to": f"{to}.einkauf"})
        self.assertEqual(r.status_code, 404)                          # Tom shares nothing with Cora
        self.assertEqual([x["text"] for x in owner.get("/api/profile/tasks").json()["lists"]["aufgaben"]["items"]],
                         ["Schrauben", "Dübel"])

    def test_every_new_endpoint_keeps_the_rules(self):
        guest = TestClient(panel.app)
        for p in ("/api/profile/tasks/einkauf/abcdefabcd", "/api/profile/tasks/einkauf/order", "/api/profile/listen/order"):
            self.assertIn(guest.put(p, json={}).status_code, (401, 403), p)
        a = profile("Apfel Emil")
        uid = uid_of("Apfel Emil")
        for p in ("/api/profile/tasks/einkauf/abcdefabcd", "/api/profile/tasks/einkauf/order", "/api/profile/listen/order"):
            self.assertEqual(a.put(p, content=b"{" + b" " * 9000 + b"}", headers={"Content-Type": "application/json"}).status_code, 413, p)
        a.post("/api/profile/tasks/einkauf", json={"text": "Brot"})
        x = a.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"][0]
        ADMIN.put(f"/api/admin/features/tasks/profiles/{uid}", json={"on": False})
        self.addCleanup(ADMIN.put, f"/api/admin/features/tasks/profiles/{uid}", json={"on": True})
        self.assertEqual(a.put(f"/api/profile/tasks/einkauf/{x['id']}", json={"flag": True}).status_code, 403)
        self.assertEqual(a.put("/api/profile/listen/order", json={"order": []}).status_code, 403)

    def test_the_journal_says_what_never_which(self):
        a = profile("Apfel Frida")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            lid = a.post("/api/profile/listen", json={"name": "Geheimliste"}).json()["made"]
            a.post("/api/profile/tasks/einkauf", json={"text": "Tresorcode"})
            x = a.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"][0]
            a.put(f"/api/profile/tasks/einkauf/{x['id']}", json={"note": "Geheimnotiz"})
            a.put(f"/api/profile/tasks/einkauf/{x['id']}", json={"at": "99:99"})
            a.put("/api/profile/tasks/einkauf/order", json={"ids": [x["id"]]})
            a.put(f"/api/profile/tasks/einkauf/{x['id']}", json={"to": lid})
            a.put("/api/profile/listen/order", json={"order": [lid]})
        log = out.getvalue()
        for line in ("tasks: edit einkauf | 1 entries", "tasks: edit einkauf | refused", "tasks: sort einkauf | 1 entries",
                     "tasks: move einkauf | 1 entries", "tasks: list order | ok"):
            self.assertIn(line, log)
        for word in ("Geheimliste", "Tresorcode", "Geheimnotiz", "Apfel Frida"):
            self.assertNotIn(word, log)


if __name__ == "__main__":
    unittest.main()
