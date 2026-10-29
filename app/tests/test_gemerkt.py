"""Gemerkt-Hinweis (gemerkt.py, gemerkt.js, plan nutzerwissen Punkt 1, Dominik 2026-10-29): memory_save shows a chip
with the fact's number and rev, „Rückgängig“ takes back exactly what was done and only while the fact is unchanged
since (a new fact goes, a fixed place gets its earlier wording back), only the own profile's facts, never for guests;
the message keeps only numbers; what was learned by itself becomes one card „Gemerkt von selbst“ whose title (it may
go out with a push and to Telegram) never holds the fact; the Begleiter's card; „Mach das rückgängig“ runs the same
take-back; Heute counts; logs and Live carry fixed words and numbers. Times are given, never read from the clock."""
import asyncio
import contextlib
import io
import re
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import aendern  # noqa: E402
import chat  # noqa: E402
import features  # noqa: E402
import gedaechtnis  # noqa: E402
import gemerkt  # noqa: E402
import guard  # noqa: E402
import logfilter  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
import vorgaenge  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_760_000_000


def profile(name, pin="3691"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def journal(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **kw)
    return r, out.getvalue()


def fact(uid, text):
    return next(f for f in profiles.memory(uid) if f["text"] == text)


def undo(c, f, rev=None):
    return c.post(f"/api/profile/memory/{f['id']}/undo", json={"rev": gemerkt.rev_of(f) if rev is None else rev})


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "memory", "memory_note", "memory_check", "reminders", "vorgaenge", "undo_voice")
        helpers.set_config(memory=True, memory_note=True, memory_check=True)
        for k in [k for k in guard._rate if str(k[0]).startswith(("memory", "vorgaenge"))]:
            guard._rate.pop(k, None)


class Rules(Base):
    def test_shipped_on_with_its_reason(self):
        self.assertIn("chat.memory_note", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["gedhinweis"].parent, "memory")

    def test_rev_follows_every_change_but_a_topic(self):
        f = {"id": "0a1b2c3d", "text": "Mag Tee.", "src": "said", "created": T0, "confirmed": T0}
        r = gemerkt.rev_of(f)
        self.assertRegex(r, r"^[0-9a-f]{12}$")
        self.assertEqual(gemerkt.rev_of(dict(f, topic="person")), r)
        for change in ({"text": "Mag Kaffee."}, {"confirmed": T0 + 1}, {"changed": T0 + 1}, {"src": "hand"}):
            self.assertNotEqual(gemerkt.rev_of(dict(f, **change)), r, change)

    def test_what_was_done(self):
        self.assertEqual(gemerkt.what({"text": "A", "created": T0}), "neu")
        self.assertEqual(gemerkt.what({"text": "B", "changed": T0 + 5, "prev": [{"text": "A", "until": T0 + 5}]}), "platz")
        self.assertEqual(gemerkt.what({"text": "B", "changed": T0 + 5, "prev": [{"text": "A", "until": T0 + 1}]}), "")

    def test_a_message_keeps_only_numbers(self):
        self.assertEqual(gemerkt.clean([{"id": "0a1b2c3d", "rev": "0123456789ab", "text": "Mag Tee."},
                                        {"id": "../x", "rev": "0123456789ab"}, "x"]),
                         [{"id": "0a1b2c3d", "rev": "0123456789ab"}])
        self.assertEqual(len(gemerkt.clean([{"id": "0a1b2c3d", "rev": "0123456789ab"}] * 9)), gemerkt.MEM_MAX)

    def test_the_card_title_holds_no_fact(self):
        for n in (1, 2, 3):
            self.assertRegex(gemerkt.title(n), r"^Spark hat sich (etwas|\d Dinge) gemerkt$")


class Chip(Base):
    def test_memory_save_sends_number_and_rev_and_keeps_them_with_the_message(self):
        c, uid = profile("Gm Anja")
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": 'TOOL memory_save {"fact": "Mag Quitten."}'}]})
        self.assertEqual(r.status_code, 200, r.text)
        ev = next(e for e in helpers.events(r) if e.get("type") == "memory")
        f = fact(uid, "Mag Quitten.")
        self.assertEqual((ev["action"], ev["text"], ev["id"], ev["rev"], ev["undo"]),
                         ("saved", "Mag Quitten.", f["id"], gemerkt.rev_of(f), True))
        # the conversation keeps only the numbers; the text comes from the memory when it is drawn again
        c.put("/api/profile/convos", json={"id": "gm1", "title": "Quitten", "msgs": [
            {"role": "user", "content": "Merk dir das"},
            {"role": "assistant", "content": "Gemerkt.", "mem": [{"id": ev["id"], "rev": ev["rev"], "text": "Mag Quitten."}]}]})
        m = next(x for x in profiles.convos(uid) if x["id"] == "gm1")["msgs"][1]
        self.assertEqual(m["mem"], [{"id": ev["id"], "rev": ev["rev"]}])

    def test_switch_off_no_number(self):
        c, uid = profile("Gm Bodo")
        helpers.set_config(memory_note=False)
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": 'TOOL memory_save {"fact": "Mag Feigen."}'}]})
        ev = next(e for e in helpers.events(r) if e.get("type") == "memory")
        self.assertNotIn("id", ev)
        self.assertEqual(undo(c, fact(uid, "Mag Feigen.")).status_code, 403)
        self.assertTrue(any(f["text"] == "Mag Feigen." for f in profiles.memory(uid)))

    def test_never_for_guests(self):
        g = TestClient(panel.app)
        self.assertEqual(g.post("/api/profile/memory/0a1b2c3d/undo", json={"rev": "0123456789ab"}).status_code, 401)


class Undo(Base):
    def test_a_new_fact_goes_once(self):
        c, uid = profile("Gm Carla")
        profiles.remember(uid, "Spielt Cello.", src="said")
        f = fact(uid, "Spielt Cello.")
        r = undo(c, f)
        self.assertEqual((r.status_code, r.json()["how"]), (200, "geloescht"), r.text)
        self.assertFalse(any(x["text"] == "Spielt Cello." for x in profiles.memory(uid)))
        self.assertEqual(undo(c, f).status_code, 404)

    def test_a_fixed_place_gets_its_earlier_wording_back(self):
        c, uid = profile("Gm Dora")
        profiles.remember(uid, "Wohnt in Ulm.", src="said")
        old = dict(fact(uid, "Wohnt in Ulm."))
        profiles.remember(uid, "Wohnt in Bonn.", src="said")
        f = fact(uid, "Wohnt in Bonn.")
        self.assertEqual((f["id"], gemerkt.what(f)), (old["id"], "platz"))
        r = undo(c, f)
        self.assertEqual(r.json()["how"], "zurueckgeholt", r.text)
        back = fact(uid, "Wohnt in Ulm.")
        self.assertEqual(back["id"], old["id"])
        self.assertEqual((back["src"], back["confirmed"], back.get("changed")), (old["src"], old["confirmed"], old.get("changed")))
        self.assertNotIn("Wohnt in Bonn.", [p["text"] for p in back.get("prev") or []])   # the undone wording is gone

    def test_changed_since_is_refused_and_nothing_changes(self):
        c, uid = profile("Gm Emil")
        profiles.remember(uid, "Trinkt Mate.", src="said")
        f = dict(fact(uid, "Trinkt Mate."))
        profiles.change_fact(uid, f["id"], "Trinkt viel Mate.")
        r = undo(c, f)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("Ich → Gedächtnis", r.json()["detail"])
        self.assertEqual(fact(uid, "Trinkt viel Mate.")["id"], f["id"])
        self.assertEqual(undo(c, f, rev="zz").status_code, 404)   # a malformed rev never matches

    def test_said_again_has_nothing_to_take_back(self):
        c, uid = profile("Gm Frida")
        profiles.remember(uid, "Wohnt in Kiel.", src="said")
        profiles.remember(uid, "Wohnt in Kiel.", src="said")
        f = fact(uid, "Wohnt in Kiel.")
        self.assertEqual(gemerkt.note(uid, "Wohnt in Kiel.")["undo"], False)
        self.assertEqual(undo(c, f).status_code, 409)
        self.assertTrue(any(x["text"] == "Wohnt in Kiel." for x in profiles.memory(uid)))

    def test_only_the_own_profile(self):
        c, uid = profile("Gm Gerd")
        other, ouid = profile("Gm Hanna")
        profiles.remember(ouid, "Mag Rosen.", src="said")
        f = fact(ouid, "Mag Rosen.")
        self.assertEqual(undo(c, f).status_code, 404)
        self.assertEqual(fact(ouid, "Mag Rosen.")["id"], f["id"])

    def test_body_is_limited(self):
        c, uid = profile("Gm Ilse")
        r = c.post("/api/profile/memory/0a1b2c3d/undo", content=b'{"rev": "' + b"a" * 2000 + b'"}',
                   headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_one_journal_line_per_result_without_the_fact(self):
        c, uid = profile("Gm Jonas")
        profiles.remember(uid, "Sammelt Muscheln.", src="said")
        f = dict(fact(uid, "Sammelt Muscheln."))
        how, log = journal(gemerkt.take_back, uid, f["id"], "0123456789ab", "chip")
        self.assertEqual(how, "geaendert")
        self.assertIn("gedaechtnis: rueckgaengig abgelehnt grund=geaendert", log)
        how, log2 = journal(gemerkt.take_back, uid, f["id"], gemerkt.rev_of(f), "chip")
        self.assertEqual(how, "geloescht")
        for line in (log + log2).strip().splitlines():
            self.assertTrue(any(re.match(rx, line) for _, rx in logfilter.AREAS), line)
            self.assertNotIn("Muscheln", line)

    def test_voice_undo_takes_back_the_same_way(self):
        """„Mach das rückgängig“ after memory_save (aendern): a fixed place gets its old wording, it is not forgotten."""
        c, uid = profile("Gm Karl")
        profiles.remember(uid, "Fährt einen Polo.", src="said")
        profiles.remember(uid, "Fährt einen Golf.", src="said")
        aendern.note_tool(uid, "memory_save", {"fact": "Fährt einen Golf."}, "Saved.")
        entry = aendern.last(uid)
        self.assertEqual(entry["kind"], "memory")
        out = asyncio.run(aendern.undo(uid, entry, {}))
        self.assertEqual(out, "Die frühere Fassung gilt wieder.")
        self.assertTrue(any(x["text"] == "Fährt einen Polo." for x in profiles.memory(uid)))


class Card(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(reminders=True, vorgaenge=True)

    def learn(self, name):
        c, uid = profile(name)
        old = int((time.time() - 3600) * 1000)
        c.put("/api/profile/convos", json={"id": "gmq1", "title": "Tee", "updated": old, "msgs": [
            {"role": "user", "content": "Ich trinke gern Tee."}, {"role": "assistant", "content": "Schön."}]})
        chat._last_chat[0] = 0
        asyncio.run(chat.learn_once())
        x = next(y for y in c.get("/api/profile/vorgaenge").json()["items"] if y["art"] == gemerkt.CARD)
        return c, uid, x

    def test_learned_by_itself_becomes_one_card_without_the_fact_in_its_title(self):
        c, uid, x = self.learn("Gm Lotte")
        f = fact(uid, "Test mag Tee.")
        self.assertEqual(x["titel"], "Spark hat sich etwas gemerkt")
        self.assertNotIn("Tee", x["titel"])
        self.assertEqual(x["felder"], [["Gemerkt", "Test mag Tee."]])
        self.assertEqual(x["daten"]["fakten"], f"{f['id']}:{gemerkt.rev_of(f)}")
        self.assertEqual(x["daten"]["weg"], "Ich → Gedächtnis")
        self.assertEqual(sorted(k["k"] for k in x["acts"]), ["gm_stimmt", "gm_weg", "oeffnen", "spaeter"])
        self.assertFalse([m for cv in profiles.convos(uid) for m in cv["msgs"] if m.get("vg") == x["id"]])  # never said
        self.assertEqual(c.get("/api/profile/today").json()["cards"]["memory"]["neu"], 1)
        # „Stimmt“ confirms it and closes the card
        r = c.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "gm_stimmt", "rev": x["rev"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(gedaechtnis.confirmed(fact(uid, "Test mag Tee.")))
        self.assertEqual(vorgaenge.find(uid, x["id"])["wie"], "bestaetigt")
        self.assertEqual(c.get("/api/profile/today").json()["cards"]["memory"]["neu"], 0)

    def test_undo_on_the_card(self):
        c, uid, x = self.learn("Gm Mia")
        r = c.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "gm_weg", "rev": x["rev"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(any(f["text"] == "Test mag Tee." for f in profiles.memory(uid)))
        self.assertEqual(vorgaenge.find(uid, x["id"])["wie"], "rueckgaengig")

    def test_a_push_never_carries_the_fact(self):
        """After „Später“ the card comes back with a push (and so maybe on Telegram): fixed words and a number only."""
        c, uid, x = self.learn("Gm Nils")
        r = c.post("/api/profile/vorgaenge/act", json={"id": x["id"], "act": "spaeter", "rev": x["rev"], "wann": "abend"})
        self.assertEqual(r.status_code, 200, r.text)
        sent = []

        async def fake(u, title, body="", **kw):
            sent.append((title, body))
        later = vorgaenge.find(uid, x["id"])["spaeter_bis"]
        with mock.patch.object(push, "send", fake):
            asyncio.run(vorgaenge.due(now=later + 1))
        mine = [s for s in sent if "gemerkt" in s[0]]
        self.assertTrue(mine, sent)
        for title, body in mine:
            self.assertNotIn("Tee", title + body)
        self.assertEqual(vorgaenge.knoepfe(uid, x["id"])[:2], [("gm_stimmt", "Stimmt"), ("gm_weg", "Rückgängig")])

    def test_off_no_card(self):
        helpers.set_config(memory_note=False)
        c, uid = profile("Gm Olga")
        self.assertEqual(gemerkt.learned(uid, {"id": "gmq2", "updated": T0 * 1000}, ["Mag Birnen."]), 0)


class Begleiter(unittest.TestCase):
    def test_a_card_with_undo_and_the_memory_page(self):
        out = chat.desk_cards([], [], [{"type": "memory", "action": "saved", "text": "Mag Tee.", "id": "0a1b2c3d",
                                        "rev": "0123456789ab", "undo": True}], True)
        self.assertEqual(out["cards"][0], {"title": "Gemerkt: Mag Tee.", "buttons": [
            {"label": "Rückgängig", "send": "Mach das rückgängig"}, {"label": "Gedächtnis ansehen", "open": "#me=factbox"}]})
        off = chat.desk_cards([], [], [{"type": "memory", "text": "Mag Tee.", "id": "0a1b2c3d", "undo": True}], False)
        self.assertEqual([b["label"] for b in off["cards"][0]["buttons"]], ["Gedächtnis ansehen"])


class Live(Base):
    def test_numbers_only(self):
        c, uid = profile("Gm Paul")
        profiles.remember(uid, "Liest Krimis.", src="said")
        gemerkt.note(uid, "Liest Krimis.")
        live = gemerkt.for_live()
        self.assertTrue(live["on"])
        self.assertGreaterEqual(live["chip"], 1)
        self.assertTrue(all(isinstance(v, (int, bool)) for v in live.values()), live)


if __name__ == "__main__":
    unittest.main()
