"""Zustand → Verbessern in Klartext (klartext.py, befund.py, berater.py; Dominik 2026-10-14 „sprechender machen …
warum genau, woher genau, und Behebungsempfehlung“, Plan „Verbessern verständlicher“ 1–6, „1 bis 6 als ein Paket“).

Every case carries a card in fixed sentences: what happened, where from, why, what helps; never words of a question.
An automatic case always has a cause of its own (never „Ursache noch unklar“); a 👎 without an expectation still asks.
The same change for several cases is one proposal („N Fälle“) and every action works on all of its cases. The kinds of
proposal are words with what they risk; the best pick follows fixed rules. An idea of the model shows settings by
their name, never by the key. The plain sentences of error codes exist once (klartext.CODES), also for Logs → Anfragen.
No test depends on the time of day: times are passed in.
Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import os
import re
import unittest
from unittest import mock

from tests import helpers
from tests.test_einstellungs_assistent import ADMIN, Base, T0, run, trace
from tests.test_ui_browser import async_playwright, browser_ok, chromium

import befund  # noqa: E402
import berater  # noqa: E402
import faelle  # noqa: E402
import klartext  # noqa: E402
import logfilter  # noqa: E402

PANEL = os.path.join(helpers.APP, "panel")
JS = os.path.join(PANEL, "static", "js")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


class Texts(unittest.TestCase):
    def test_every_kind_code_and_area_has_both_languages(self):
        self.assertEqual(set(klartext.WAS), set(faelle.KINDS))
        for de, en in klartext.WAS.values():
            self.assertTrue(de and en)
        for k, (was, why, helps, svc) in klartext.CODES.items():
            self.assertTrue(all(was + why + helps), k)
            self.assertIn(svc, set(berater.UMGEBUNG) | {""}, k)
        known = {a for a, _ in logfilter.AREAS} | {"other"}
        for k, (de, en, svc) in klartext.AREAS.items():
            self.assertTrue(de and en, k)
            self.assertIn(k, known)
            self.assertIn(svc, set(berater.UMGEBUNG) | {""}, k)
        for k, (de, en, helps) in befund.KLASSEN.items():
            self.assertTrue(de and en and all(helps), k)

    def test_codes_resolve_by_prefix(self):
        self.assertEqual(klartext.code_text("tts_http_413"), klartext.CODES["tts_http"][0])
        self.assertEqual(klartext.code_text("llm_irgendwas"), klartext.CODES["llm_error"][0])
        self.assertEqual(klartext.code_text("search"), klartext.AREAS["search"][:2])
        self.assertEqual(klartext.code_text("unbekannt"), klartext.CODES["error"][0])

    def test_one_source_for_the_code_sentences(self):
        logs = read(JS, "logs.js")
        self.assertNotIn("const RERR", logs)                      # Logs → Anfragen gets them with the list
        self.assertIn("(RQ.data||{}).codes", logs)
        src = read(PANEL, "berater.py")
        self.assertNotIn("ERR_WORDS", src)
        self.assertNotIn("AREA_WORDS", src)


class Card(Base):
    def test_automatic_cases_always_have_a_cause(self):
        self.on()
        for kind, kw in (("fehler", {"code": "llm_slow"}), ("fehler", {"code": "other"}), ("tool", {"tool": "web_search"}),
                         ("unklar", {}), ("absage", {}), ("doppelt", {}), ("pruefung", {}), ("abbruch", {}),
                         ("aussetzer", {"code": "tts_behind"}), ("melder", {"melder": "langsam", "title": "Antworten oft langsam"})):
            case = faelle.add(kind, {}, now=T0, **kw)
            ks = [o["k"] for o in befund.diagnose(case)]
            self.assertNotIn("unklar", ks, kind)
            k = klartext.card(case, befund.diagnose(case))
            self.assertEqual(set(k), {"was", "woher", "warum", "hilft"})
            self.assertTrue(k["was"][0] and k["was"][1] and k["warum"] and k["hilft"], kind)

    def test_error_card_says_what_where_why_and_what_helps(self):
        self.on()
        s = faelle.summary(trace("wetter", errors=["llm_slow"], persist=True), {"id": "u1"}, "Geheime Frage", "x", now=T0)
        case = faelle.add("fehler", s, code="llm_slow", now=T0)
        k = klartext.card(case, befund.diagnose(case))
        self.assertEqual(k["was"], list(klartext.CODES["llm_slow"][0]))
        self.assertEqual(k["woher"]["clients"], ["web"])
        self.assertEqual(k["woher"]["traces"], ["abc123"])
        self.assertTrue(any("Typische Ursache" in x[0] for x in k["warum"]))
        self.assertTrue(any("Zustand → Monitoring" in x[0] for x in k["hilft"]))
        self.assertNotIn("Geheime Frage", str(k))                # never a question, even when it is kept
        d = ADMIN.get("/api/admin/berater").json()
        self.assertEqual(d["cases"][0]["karte"]["was"], k["was"])

    def test_a_thumb_down_without_expectation_still_asks(self):
        self.on()
        case = faelle.add("schlecht", {"group": "dokument", "offered": ["document_search"], "tools": [("document_search", True)],
                                       "neg": True}, grund="antwort", now=T0)
        self.assertEqual([o["k"] for o in befund.diagnose(case)], ["unklar"])
        self.assertIn("falsche Antwort", klartext.card(case, befund.diagnose(case))["was"][0])

    def test_diagnose_case_names_its_place(self):
        self.on()
        case = faelle.add("fehler", {}, code="search", now=T0)
        k = klartext.card(case, befund.diagnose(case))
        self.assertIn("Zustand → Logs → Diagnose", k["woher"]["src"][0])
        self.assertEqual(k["was"][0], klartext.AREAS["search"][0])


class Bundle(Base):
    def _prop(self, code):
        with mock.patch.object(berater, "pick", new=mock.AsyncMock(return_value=(0, ""))):
            case = faelle.add("fehler", {}, code=code, now=T0)
            return run(berater.propose(case, T0)), case

    def test_same_change_is_one_proposal_for_all_cases(self):
        self.on()
        p1, c1 = self._prop("kiwix")
        p2, c2 = self._prop("searxng")
        self.assertEqual((p1["key"], p2["id"]), ("issue", p1["id"]))
        open_ = [p for p in berater.props(("offen",))]
        self.assertEqual(len(open_), 1)
        self.assertEqual(berater._case_ids(open_[0]), [c1["id"], c2["id"]])
        self.assertEqual(faelle.get(c2["id"])["status"], "vorschlag")
        shown = next(p for p in ADMIN.get("/api/admin/berater").json()["props"] if p["id"] == p1["id"])
        self.assertEqual([x["case"] for x in shown["faelle"]], [c1["id"], c2["id"]])
        self.assertIn("2 Fällen", shown["warum"][0])
        r = ADMIN.post(f"/api/admin/berater/{p1['id']}/reject")
        self.assertEqual(r.status_code, 200, r.text)
        for c in (c1, c2):                                       # every case of the proposal
            self.assertEqual(faelle.get(c["id"])["status"], "verworfen")
        rej = berater._read()["rejected"]
        self.assertEqual(sum(1 for k in rej if k.startswith((c1["fp"] + "#", c2["fp"] + "#"))), 2)

    def test_old_duplicates_join_and_a_new_proposal_keeps_the_rest(self):
        self.on()
        p1, c1 = self._prop("kiwix")
        with berater._lock:      # as before the bundling: a second open proposal with the same change
            d = berater._read()
            d["props"][0]["more"] = []
            twin = dict(d["props"][0], id="0badc0de", case=faelle.add("fehler", {}, code="searxng", now=T0)["id"], t=T0 + 1)
            d["props"].append(twin)
            berater._write(d, T0)
        self.assertEqual(berater.bundle_open(T0), 1)
        p = berater.props(("offen",))
        self.assertEqual((len(p), len(berater._case_ids(p[0]))), (1, 2))
        with berater._lock:
            d = berater._read()
            berater._drop_case(d, c1["id"])                      # the first case gets a new proposal
            self.assertEqual([x["case"] for x in d["props"] if x["status"] == "offen"], [twin["case"]])


class Words(Base):
    def test_kinds_are_words_with_risk_and_the_best_pick_follows_rules(self):
        self.assertEqual(set(berater.STUFEN), {"A", "B", "C", "U", "I", "P"})
        for k, v in berater.STUFEN.items():
            self.assertEqual(len(v), 4)
            self.assertTrue(all(v), k)
        ok = {"ok": True}
        rows = [{"id": "u", "status": "offen", "stufe": "U", "pruef": ok, "n": 9, "case": "a"},
                {"id": "i", "status": "offen", "stufe": "I", "pruef": ok, "n": 9, "case": "b"},
                {"id": "red", "status": "offen", "stufe": "A", "pruef": {"ok": False}, "n": 9, "case": "c"},
                {"id": "c1", "status": "offen", "stufe": "C", "pruef": ok, "n": 2, "case": "d"},
                {"id": "a1", "status": "offen", "stufe": "A", "pruef": ok, "n": 2, "case": "e"},
                {"id": "bad", "status": "offen", "stufe": "A", "pruef": ok, "n": 5, "case": "f", "replay": {"ok": False}}]
        self.assertEqual(berater.best_pick(rows), "a1")         # a rule before a switch at the same count
        rows.append({"id": "b2", "status": "offen", "stufe": "B", "pruef": ok, "n": 1, "case": "g",
                     "more": [{"case": "h", "n": 1}]})
        self.assertEqual(berater.best_pick(rows), "b2")         # more cases first
        self.assertEqual(berater.best_pick(rows[:3]), "")

    def test_page_shows_words_legend_card_and_why(self):
        js = read(JS, "verbessern.js")
        self.assertNotIn("VBSTUFE", js)
        self.assertNotIn("${esc(x.stufe)}", js)                  # never the bare letter
        for part in ("function vbLegend(", "function vbKarte(", "function vbWhy(", "data-vbtrace", "window.openTrace(",
                     "beste Empfehlung"):
            self.assertIn(part, js)
        self.assertNotIn("<code>${esc(i.setting)}</code>", js)  # an idea names the setting, never its key


class Idea(Base):
    def test_keys_and_tool_names_become_names(self):
        places = klartext.places()
        self.assertIn("logs.trace", places)
        name, way = places["logs.trace"]
        self.assertTrue(way.startswith("Einstellungen → ") and way.endswith(name))
        got = klartext.readable("logs.trace einschalten, dann web_search prüfen; chat.gibtsnicht ändern",
                                {"logs.trace", "chat.gibtsnicht"})
        self.assertNotIn("logs.trace", got)
        self.assertIn(f"„{name}“", got)
        self.assertNotIn("web_search", got)
        self.assertIn("eine Einstellung", got)
        self.assertEqual(klartext.readable("z.B. 3.5 Sekunden"), "z.B. 3.5 Sekunden")

    def test_idea_on_the_page_has_name_and_way(self):
        self.on(berater_ideas=True)
        with mock.patch.object(berater, "pick", new=mock.AsyncMock(return_value=(0, ""))):
            case = faelle.add("fehler", {}, code="other", now=T0)
            p = run(berater.propose(case, T0))
        berater._update(p["id"], idea={"text": "logs.trace kurz einschalten", "setting": "logs.trace", "steps": []})
        shown = next(x for x in ADMIN.get("/api/admin/berater").json()["props"] if x["id"] == p["id"])
        name, way = klartext.places()["logs.trace"]
        self.assertEqual((shown["idea"]["name"], shown["idea"]["where"]), (name, way))
        self.assertNotIn("logs.trace", shown["idea"]["text"])
        self.assertEqual(berater.get(p["id"])["idea"]["text"], "logs.trace kurz einschalten")   # shown, not changed

    def test_prompt_has_plain_words_not_codes(self):
        src = read(PANEL, "berater.py")
        fn = re.search(r"async def idea\(.*?\n(?=\ndef |\nasync def )", src, re.S).group(0)
        self.assertNotIn("Fehler {case['code']}", fn)
        self.assertIn("klartext.card(", fn)


class Requests(Base):
    def test_request_list_carries_the_sentences_of_its_codes(self):
        import tracelog
        import time
        tracelog.clear()
        self.addCleanup(tracelog.clear)
        now = time.time()
        tracelog._write([{"id": "abc123", "t": now - 5, "client": "web", "who": None, "kind": "guest", "device": "",
                          "intent": "wetter", "steps": [], "marks": {}, "errors": ["llm_slow", "tts_http_500"], "status": "error"}])
        with mock.patch.object(tracelog, "on", return_value=True):
            d = ADMIN.get("/api/admin/traces?minutes=60").json()
        self.assertEqual(d["codes"]["llm_slow"], list(klartext.CODES["llm_slow"][0]))
        self.assertEqual(d["codes"]["tts_http_500"], list(klartext.CODES["tts_http"][0]))


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(Base):
    """The page itself: a case's card and a proposal with its kind as a word, the legend and „Warum dieser Vorschlag“;
    nothing scrolls sideways at 1280, 390 and 320 px, and narrow the opened proposal shows (it sat one level below
    the box and stayed hidden before)."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        import profiles
        try:
            profiles.add_user("Verbesserer", "4711")
        except Exception:
            pass

    def test_card_kind_and_why_fit(self):
        self.on()
        with mock.patch.object(berater, "pick", new=mock.AsyncMock(return_value=(0, ""))):
            s = faelle.summary(trace("wetter", errors=["llm_slow"], persist=True), {"id": "u1"}, "", "x", now=T0)
            run(berater.propose(faelle.add("fehler", s, code="llm_slow", now=T0), T0))
            run(berater.propose(faelle.add("fehler", {}, code="other", now=T0 + 1), T0 + 1))

        async def go():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                try:
                    for w, h in ((1280, 900), (390, 844), (320, 640)):
                        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
                        pg = await ctx.new_page()
                        errors = []
                        pg.on("pageerror", lambda e: errors.append(str(e)))
                        base = f"http://127.0.0.1:{self.port}"
                        await pg.goto(base + "/")
                        self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
                        await pg.request.post(base + "/api/profile/login", data={"name": "Verbesserer", "pin": "4711"})
                        await pg.goto(base + "/")
                        await pg.wait_for_timeout(800)
                        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
                        await pg.evaluate("goSec('verb')")
                        await pg.wait_for_selector("#vblist [data-vbsel^=p]")
                        rows = await pg.inner_text("#vblist")
                        self.assertIn("2 Fälle", rows)                     # one proposal for both cases
                        self.assertIn("Selbst prüfen", rows + await pg.inner_text("#vblist details"))
                        await pg.evaluate("document.querySelector('#vblist [data-vbsel^=p]').click()")
                        await pg.wait_for_selector("#vbdetail:not([hidden]) h3")
                        det = await pg.inner_text("#vbdetail")
                        for part in ("Was ist passiert", "Woher", "Warum dieser Vorschlag", "Risiko und Rückgängig"):
                            self.assertIn(part, det, w)
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 0, w)
                        self.assertEqual(errors, [], w)
                        await ctx.close()
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
