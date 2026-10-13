"""Einstellungs-Assistent Version 3 (plan plaene/vorschlaege-besser.md, Dominik 2026-10-12 „1-9“): rule versions with
export and import, cleanup of doubled and unused rules, re-check after an update or a model change, automatic undo
when the 👍 share drops, and the guard that one profile alone never changes rules by itself. No test depends on the
time of day."""
import asyncio
import json
from unittest import mock

from tests import helpers
from tests.test_einstellungs_assistent import ADMIN, Base, T0
from tests.test_regeln_admin import consent, e62151

import admin  # noqa: E402
import berater  # noqa: E402
import faelle  # noqa: E402
import intent  # noqa: E402
import notaus  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import panel  # noqa: E402


def taken_extra(test, name):
    """Dominik's case as an „extra tool“ proposal, taken by the admin."""
    test.on()
    first = mock.patch.object(berater, "pick", new=mock.AsyncMock(return_value=(0, "")))
    first.start()
    test.addCleanup(first.stop)
    uid = consent(name)
    case = faelle.add("schlecht", e62151(uid), grund="antwort", soll="erstellt", now=T0)
    p = asyncio.run(berater.propose(faelle.get(case["id"])))
    test.assertEqual(ADMIN.post(f"/api/admin/berater/{p['id']}/take").status_code, 200)
    return berater.get(p["id"]), uid


class Versions(Base):
    def setUp(self):
        super().setUp()
        try:
            import os
            os.remove(berater._vfile())
        except FileNotFoundError:
            pass

    def test_every_change_keeps_the_rules_before(self):
        p, _ = taken_extra(self, "V3Take")
        rows = berater.versions()
        self.assertEqual(rows[-1]["rules"]["route_extra"], "")
        self.assertIn("weiche_extra", rows[-1]["why"])
        ADMIN.post(f"/api/admin/berater/{p['id']}/undo")
        self.assertEqual(berater.versions()[-1]["rules"]["route_extra"], "dokument: document_status")
        r = ADMIN.post("/api/admin/berater/regeln/version", json={"i": 0})    # the newest: just before the undo
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(admin.get_config()["chat"]["route_extra"], "dokument: document_status")
        self.assertEqual(ADMIN.post("/api/admin/berater/regeln/version", json={"i": 99}).status_code, 404)
        self.assertEqual(ADMIN.post("/api/admin/berater/regeln/version", json={"i": "0"}).status_code, 400)

    def test_export_and_import(self):
        self.on()
        helpers.set_config(tool_words="document_status: morgenblatt", route_extra="dokument: document_status")
        exp = ADMIN.get("/api/admin/berater/regeln/export").json()
        self.assertEqual(set(exp["rules"]), set(berater.RULE_KEYS))
        self.assertNotIn("llm_key", json.dumps(exp))
        helpers.set_config(tool_words="", route_extra="")
        r = ADMIN.post("/api/admin/berater/regeln/import", json={"rules": exp["rules"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["imported"]["ok"])
        self.assertEqual(admin.get_config()["chat"]["tool_words"], "document_status: morgenblatt")
        self.assertEqual(berater.versions()[-1]["why"], "Import")
        # only the six rule keys, with their checks; a test sentence that turns red needs „Trotzdem“
        for bad in ({"llm_url": "http://x"}, {"tool_words": ["x"]}, {"tool_hints": "rm_rf: Mach das."}):
            self.assertEqual(ADMIN.post("/api/admin/berater/regeln/import", json={"rules": bad}).status_code, 400, bad)
        red = {"route_tests": [{"q": "Wie wird das Wetter?", "want": "mail"}]}
        r = ADMIN.post("/api/admin/berater/regeln/import", json={"rules": red}).json()["imported"]
        self.assertFalse(r["ok"])
        self.assertEqual(admin.get_config()["chat"].get("route_tests", []), [])
        r = ADMIN.post("/api/admin/berater/regeln/import", json={"rules": red, "force": True}).json()["imported"]
        self.assertTrue(r["ok"])
        helpers.set_config(route_tests=[], tool_words="", route_extra="")
        self.assertEqual(ADMIN.post("/api/admin/berater/regeln/import",
                                    content=b"{" + b" " * (berater.MAX_IMPORT + 10) + b"}").status_code, 413)
        self.assertEqual(TestClient(panel.app).get("/api/admin/berater/regeln/export").status_code, 401)


class Cleanup(Base):
    def test_doubled_and_unused_rules_are_marked(self):
        self.on()
        builtin = next(w for w in ("dokumente", "dokument", "unterlagen") if intent.GROUPS["dokument"][1].search(w))
        helpers.set_config(route_extra="dokument: document_search, document_status",
                           route_words=f"dokument: {builtin}, morgenblatt", route_not="dokument: morgenblatt")
        rows = {(r["key"], r["item"]): r for r in berater.regeln()}
        self.assertEqual(rows[("route_extra", "document_search")]["weg"][0], "schon in der Gruppe")
        self.assertNotIn("weg", rows[("route_extra", "document_status")])
        self.assertEqual(rows[("route_words", builtin)]["weg"][0], "schon eingebaut")
        self.assertIn("Nicht bei", rows[("route_words", "morgenblatt")]["weg"][0])
        # never used: marked only after 30 days since it was first seen, and a hit keeps it
        later = T0 + 40 * 86400
        d = berater._read()
        d["first"] = {k: T0 for k in d["first"]}
        berater._write(d)
        marked = {(r["key"], r["item"]): r.get("weg") for r in berater._cleanup(berater.regeln(), admin.get_config()["chat"], later)}
        self.assertEqual(marked[("route_extra", "document_status")][0], "30 Tage nicht gebraucht")
        berater.rule_hits("Liegt das Morgenblatt in meinen Dokumenten?", intent.classify("Liegt das Morgenblatt in meinen Dokumenten?"),
                          [], {"document_status"}, admin.get_config()["chat"], now=later)
        self.assertEqual(set(berater._hits["rows"]) - {"route_extra|dokument", "route_words|dokument"}, set())
        marked = {(r["key"], r["item"]): r.get("weg") for r in berater._cleanup(berater.regeln(), admin.get_config()["chat"], later)}
        self.assertIsNone(marked[("route_extra", "document_status")])
        helpers.set_config(route_extra="", route_words="", route_not="")
        berater._hits.update(rows={}, flushed=0.0)


class Recheck(Base):
    def test_after_an_update_every_taken_rule_is_replayed(self):
        p, _ = taken_extra(self, "V3Re")
        with mock.patch.object(berater, "_version", return_value="V01.0.900"):
            self.assertIsNone(berater.recheck_changed(T0))         # the first time: nothing to compare with
            self.assertIsNone(berater.recheck_changed(T0 + 1))     # nothing changed
        with mock.patch.object(berater, "_version", return_value="V01.0.901"):
            self.assertEqual(berater.recheck_changed(T0 + 2), 1)
        r = berater.get(p["id"])["recheck"]
        self.assertEqual(r["why"], "update")
        self.assertTrue(r["ok"], r)


class AutoUndo(Base):
    def test_a_falling_share_undoes_with_the_switch(self):
        p, _ = taken_extra(self, "V3Undo")
        q = {"before": {"dokument": [18, 2]}, "after": {"dokument": [6, 6]}}

        def quota(days=7, now=None, part="g"):
            return q["before"] if now == p["applied"] else q["after"]
        with mock.patch.object(faelle, "quota", side_effect=quota):
            self.assertEqual(berater.quote_drop(p, p["applied"] + 86400), 40)
            berater._update(p["id"], check_at=0)
            berater.nachkontrolle(p["applied"] + 86400)      # switch off: worse, but the admin's own stays
            self.assertEqual(berater.get(p["id"])["status"], "uebernommen")
            self.assertEqual(berater.get(p["id"])["check"]["result"], "schlechter")
            berater._update(p["id"], check=None, check_at=0)
            helpers.set_config(berater_auto_undo=True)
            berater.nachkontrolle(p["applied"] + 86400)
        self.assertEqual(berater.get(p["id"])["status"], "zurueck")
        self.assertEqual(admin.get_config()["chat"]["route_extra"], "")
        with mock.patch.object(faelle, "quota", return_value={"dokument": [3, 1]}):
            self.assertIsNone(berater.quote_drop(p, T0))          # too few ratings: no verdict


class Guard(Base):
    def test_one_profile_alone_never_changes_rules_by_itself(self):
        self.on(berater_auto=True)
        uid = consent("V3Alone")
        for i in range(5):
            case = faelle.add("schlecht", e62151(uid), grund="antwort", soll="erstellt", now=T0 + i)
        case = faelle.get(case["id"])
        self.assertEqual(case["who"], [uid])
        self.assertFalse(berater.trusted(case))
        other = consent("V3Other")
        case2 = faelle.add("schlecht", e62151(other), grund="antwort", soll="erstellt", now=T0 + 9)
        self.assertTrue(berater.trusted(faelle.get(case2["id"])))
        with mock.patch.object(notaus, "admin_uids", return_value=[uid]):
            self.assertTrue(berater.trusted(case))               # the admin's own 👎 counts
        prop = {"id": "x", "stufe": "A", "pruef": {"ok": True}, "title": ["t", "t"]}
        with mock.patch.object(berater, "take") as take:
            asyncio.run(berater._autopilot(prop, case, T0 + 12 * 3600, berater.features.chat_cfg()))
            take.assert_not_called()


class Version4(Base):
    def test_why_for_every_profile_only_with_its_switch(self):
        self.on()
        c, uid = __import__("tests.test_eigenes_tun", fromlist=["profile"]).profile("V4Why")
        q = "Warum hast du eben im Web gesucht?"
        self.assertFalse(berater.takes(q, uid))
        helpers.set_config(berater_why=True)
        self.assertFalse(berater.takes(q, uid))                  # the profile's own switch too
        import profiles
        profiles.save_settings(uid, {"why_on": True})
        self.assertTrue(berater.takes(q, uid))
        with mock.patch.object(notaus, "admin_uids", return_value=[]):     # the proposals stay for admins
            self.assertIn("aus", berater.by_phrase(uid, "Was schlägt der Einstellungs-Assistent vor?"))
        with mock.patch.object(faelle, "_last_of", return_value=(0, {"group": "websuche", "tools": [("web_search", True)]})):
            text = berater.by_phrase(uid, q)
        self.assertIn("Websuche", text)
        self.assertNotIn("web_search", text)                       # no tool names, rules or settings
        self.assertNotIn("Weiche", text)
        helpers.set_config(berater_why=False)

    def test_monthly_report_numbers_only(self):
        p, _ = taken_extra(self, "V4Report")
        r = berater.report()
        self.assertEqual(r["taken"], 1)
        self.assertEqual(r["rules"], 1)
        text = berater.report_text(r)
        self.assertIn("1 Regeln übernommen", text)
        self.assertNotIn("Morgenblatt", text)
        self.assertNotIn("Morgenblatt", json.dumps(r))
        first = 1_793_520_000          # some 1st of a month; its local hour is moved to 10 o'clock
        import time as _t
        lt = _t.localtime(first)
        first += (1 - lt.tm_mday) * 86400 + (10 - lt.tm_hour) * 3600
        told = []

        async def tell(text):
            told.append(text)
        with mock.patch.object(berater, "_tell_admins", side_effect=tell):
            self.assertTrue(asyncio.run(berater.monthly(first)))
            self.assertFalse(asyncio.run(berater.monthly(first + 60)))       # once a month
            self.assertFalse(asyncio.run(berater.monthly(first + 86400)))    # not on the 2nd
        self.assertEqual(len(told), 1)
        self.assertTrue(told[0].startswith("Monatsbericht"))

    def test_english_form_of_a_word_rule(self):
        self.on(berater_analyse=True)
        self.assertEqual(asyncio.run(berater.english_form("erstellt")), "created")
        self.assertIsNone(asyncio.run(berater.english_form("morgenblatt")))   # the model's odd answer is refused
        self.assertIsNone(asyncio.run(berater.english_form("rm -rf")))
        prop = {"key": "pflicht_wort", "change": {"tool": "document_status", "word": "erstellt"},
                "title": ["Bei „erstellt“ muss Dokument-Stand laufen", 'With "erstellt" Document status must run'], "alts": []}
        asyncio.run(berater._with_english(prop, admin.get_config(), T0))
        self.assertEqual(prop["alts"][0]["change"]["word"], "created")
        self.assertIn("„created“", prop["alts"][0]["title"][0])
        self.assertTrue(prop["alts"][0]["pruef"]["ok"])
        helpers.set_config(berater_analyse=False)
        prop["alts"] = []
        asyncio.run(berater._with_english(prop, admin.get_config(), T0))
        self.assertEqual(prop["alts"], [])                                  # only with „Fall analysieren“
