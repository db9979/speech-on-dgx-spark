"""Verbrauchszähler and Kontingent for day, week and month (verbrauch.py).

Off by default; counts only numbers (never a question or an answer) per model, task and profile; a conversation's
"usage" (read, from the cache, written) comes from the last streamed piece, without it the characters are
estimated and marked; every task name the code counts under is in AUFGABEN (and so in an area); the file keeps 35
days and 13 months and folds profiles that are gone; each profile sees only its own numbers and can delete them;
a used-up limit (day, week, month) answers with one fixed sentence naming the restart, fixed commands still work,
the warning comes once, the Nachschlag holds for today, deleting the own numbers resets no limit; endpoints need
the admin or the own profile.
No test depends on the wall clock: the periods are fixed by patching verbrauch._day and verbrauch._keys or by `now`.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import glob
import json
import os
import re
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()
import panel  # noqa: E402
import systemone  # noqa: E402
import technik_knoten  # noqa: E402
import verbrauch  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
DAY = "2026-10-14"
KEYS = {"tag": DAY, "woche": "2026-W42", "monat": "2026-10"}
T = 1792000000.0   # a fixed moment for the tables (its own day per local time zone, used consistently)


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def chat(client, text):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": text}]})
    assert r.status_code == 200, r.text
    return helpers.events(r)


class Answer:
    """A finished chat/completions answer like httpx gives it."""
    def __init__(self, body, status=200):
        self.status_code, self._body = status, body

        class E:
            def total_seconds(self):
                return 0.25
        self.elapsed = E()

    def json(self):
        return self._body


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(usage_count=True, usage_quota=False, usage_quota_k=2000, usage_quota_wk=0, usage_quota_mk=0,
                           usage_quota_warn=80)
        verbrauch.clear()
        self.addCleanup(helpers.set_config, usage_count=False, usage_quota=False, usage_quota_k=2000, usage_quota_wk=0,
                        usage_quota_mk=0, usage_quota_warn=80)
        self.addCleanup(verbrauch.clear)
        self.addCleanup(verbrauch._warned.clear)
        self.addCleanup(lambda: __import__("common").write_json(verbrauch.QUOTA_FILE, {}))


class OffByDefault(unittest.TestCase):
    def test_off_counts_nothing_and_says_so(self):
        with open(os.path.join(os.path.dirname(PANEL), "config.default.json")) as f:
            cfg = json.load(f)
        self.assertFalse(cfg["chat"]["usage_count"])
        self.assertFalse(cfg["chat"]["usage_quota"])
        helpers.set_config(usage_count=False)
        verbrauch.clear()
        verbrauch.add("llm", "Gespräch", "s", 100, 0, 10)
        self.assertEqual(verbrauch.report("30t")["models"], [])
        self.assertFalse(ADMIN.get("/api/admin/verbrauch").json()["on"])
        self.assertFalse(ADMIN.get("/api/admin/verbrauch/heute").json()["on"])
        c = profile("Vbaus")
        r = c.get("/api/profile/verbrauch")
        self.assertEqual(r.status_code, 403)
        self.assertIn("Verbrauchszähler", r.json()["detail"])
        self.assertEqual(technik_knoten.heute("llm"), {"off": "verbrauch"})


class Counting(Base):
    def test_a_conversation_counts_its_usage_for_the_profile(self):
        c = profile("Vbeins")
        uid = uid_of("Vbeins")
        chat(c, "Hallo, wie geht es dir?")
        r = verbrauch.report("30t", who=uid)
        task = next(x for x in r["tasks"] if x["name"] == "Gespräch")
        self.assertGreaterEqual(task["read"], 1200)            # the fake model's usage: 1200 read, 3 written
        self.assertGreaterEqual(task["written"], 3)
        self.assertEqual(task["estimated"], 0)
        self.assertGreaterEqual(r["today"]["llm"]["cached"], 1024)
        row = next(p for p in ADMIN.get("/api/admin/verbrauch").json()["profiles"] if p["id"] == uid)
        self.assertEqual((row["kind"], row["name"]), ("profil", "Vbeins"))
        self.assertGreaterEqual(row["tokens"], 1203)
        h = technik_knoten.heute("llm")
        self.assertGreaterEqual(h["vb_llm_in"], 1200)
        self.assertGreaterEqual(h["vb_llm_calls"], 1)

    def test_without_usage_it_estimates_and_marks_it(self):
        verbrauch.llm("Gespräch", None, chars_in=350, chars_out=35, who="s")
        m = next(x for x in verbrauch.report("30t")["models"] if x["id"] == "llm")
        self.assertEqual((m["read"], m["written"], m["estimated"]), (100, 10, 1))

    def test_finished_answers_count_usage_else_the_text(self):
        verbrauch.response("Steckbrief", Answer({"usage": {"prompt_tokens": 500, "completion_tokens": 40,
                                                           "prompt_tokens_details": {"cached_tokens": 200}}}))
        verbrauch.response("Steckbrief", Answer({"choices": [{"message": {"content": "x" * 70}}]}),
                           {"messages": [{"role": "user", "content": "y" * 100}]})
        verbrauch.response("Steckbrief", Answer({"error": "nope"}, 500))        # a failed call counts nothing
        verbrauch.response("Steckbrief", "kein Objekt")                          # never raises
        t = next(x for x in verbrauch.report("30t")["tasks"] if x["name"] == "Steckbrief")
        self.assertEqual(t["calls"], 2)
        self.assertEqual(t["estimated"], 1)
        self.assertGreaterEqual(t["read"], 500 + 30)
        self.assertEqual(t["written"], 40 + 20)
        self.assertEqual(next(a for a in verbrauch.report("30t")["areas"] if a["id"] == "hintergrund")["cached"], 200)

    def test_speech_and_other_models_count_their_own_units(self):
        verbrauch.heard("Telegram", Answer({"text": "hallo", "usage": {"seconds": 2.5}}))
        verbrauch.spoken("Antwort sprechen", 48000 * 3)
        verbrauch.add("embed", "Suchindex", amount=12)
        verbrauch.add("bild", "Bild malen", amount=1, ms=9000)
        t = verbrauch.report("30t")["today"]
        self.assertEqual((t["asr"]["amount"], t["tts"]["amount"]), (2.5, 3.0))
        self.assertEqual((t["embed"]["amount"], t["bild"]["amount"]), (12, 1))
        self.assertEqual(t["bild"]["unit"], "bilder")
        z = ADMIN.get("/api/admin/verbrauch/heute").json()
        self.assertEqual((z["heard"], z["spoken"], z["pictures"]), (2.5, 3.0, 1))

    def test_an_unknown_task_counts_under_sonstige(self):
        verbrauch.add("llm", "Etwas Neues", "s", 10, 0, 1)
        self.assertEqual([x["name"] for x in verbrauch.report("30t")["tasks"]], ["Sonstige"])

    def test_no_content_ever(self):
        c = profile("Vbzwei")
        chat(c, "Mein Geheimwort ist Zebrastreifen")
        verbrauch.save()
        with open(verbrauch.FILE) as f:
            text = f.read()
        self.assertNotIn("Zebrastreifen", text)
        self.assertNotIn("Vbzwei", text)                   # the file holds the profile id, never the name
        self.assertNotIn("Zebrastreifen", json.dumps(ADMIN.get("/api/admin/verbrauch").json()))


class EveryTaskHasItsArea(unittest.TestCase):
    """Each name the code counts under is in AUFGABEN, so no new job lands in "Sonstige" unnoticed."""
    def test_names_in_the_code(self):
        names = set()
        pats = (r'vorrang\.post\(\s*\w+,\s*"([^"]+)"', r'verbrauch\.(?:response|heard|spoken|llm)\(\s*"([^"]+)"',
                r'verbrauch\.(?:add|audio)\(\s*"\w+",\s*"([^"]+)"', r'job="([^"]+)"')
        for path in glob.glob(os.path.join(PANEL, "*.py")):
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for p in pats:
                names |= set(re.findall(p, src))
        names |= set(systemone.USES.values())
        self.assertGreater(len(names), 25)
        self.assertEqual(sorted(n for n in names if n not in verbrauch.AUFGABEN), [])
        self.assertEqual(sorted(set(verbrauch.AUFGABEN.values()) - set(verbrauch.BEREICHE)), [])


class TheFile(Base):
    def test_keeps_35_days_and_13_months_and_folds_gone_profiles(self):
        for i in range(60):
            verbrauch.add("llm", "Gespräch", "u_000000000000", 10, 0, 1, now=T - 86400 * 7 * i)
        verbrauch.save(now=T)
        with open(verbrauch.FILE) as f:
            d = json.load(f)
        self.assertLessEqual(len(d["days"]), verbrauch.KEEP_DAYS)
        self.assertLessEqual(len(d["months"]), verbrauch.KEEP_MONTHS)
        keys = {k for rows in list(d["days"].values()) + list(d["months"].values()) for k in rows}
        self.assertEqual(keys, {"llm|Gespräch|" + verbrauch.GONE})
        self.assertIn("verbrauch.json", __import__("backup").STATE_LOCAL)
        self.assertIn("verbrauch-kontingent.json", __import__("backup").STATE_FILES)
        self.assertIn("verbrauch-stand.json", __import__("backup").STATE_LOCAL)

    def test_a_broken_file_starts_empty(self):
        verbrauch.save()
        with open(verbrauch.FILE, "w") as f:
            f.write("{kaputt")
        verbrauch._st["loaded"] = False
        for t in (verbrauch._days, verbrauch._months, verbrauch._hours):
            t.clear()
        verbrauch._load()
        self.assertEqual(verbrauch.report("30t")["models"], [])


class OwnNumbers(Base):
    def test_each_profile_sees_and_deletes_only_its_own(self):
        a, b = profile("Vbanna"), profile("Vbbert")
        ua, ub = uid_of("Vbanna"), uid_of("Vbbert")
        with mock.patch.object(verbrauch, "_day", lambda now: DAY):
            verbrauch.add("llm", "Gespräch", ua, 100, 0, 10)
            verbrauch.add("llm", "Gespräch", ub, 7000, 0, 70)
            verbrauch.add("asr", "Frage hören", ua, amount=4)
            ra = a.get("/api/profile/verbrauch").json()
            self.assertEqual(ra["today"]["llm"]["read"], 100)
            self.assertNotIn("profiles", ra)                      # no other profile, no names
            self.assertEqual(a.delete("/api/profile/verbrauch").json(), {"ok": True})
            ra = a.get("/api/profile/verbrauch").json()
            self.assertEqual(ra["today"], {})
            self.assertEqual(verbrauch.used(ua)["tag"], 110)             # the running totals of the limits stay
            self.assertEqual(ra["quota"]["used"]["tag"], 110)
            self.assertEqual(b.get("/api/profile/verbrauch").json()["today"]["llm"]["read"], 7000)
        self.assertGreater(verbrauch.own_count(ub), 0)

    def test_guests_and_strangers_get_nothing(self):
        self.assertEqual(verbrauch.who_of(None), verbrauch.GUEST)
        self.assertIn(TestClient(panel.app).get("/api/profile/verbrauch").status_code, (401, 403))
        self.assertIn(TestClient(panel.app).get("/api/admin/verbrauch").status_code, (401, 403))
        c = profile("Vbcarl")
        self.assertIn(c.get("/api/admin/verbrauch").status_code, (401, 403))
        self.assertIn(c.post("/api/admin/verbrauch/leeren", json={}).status_code, (401, 403))


class Quota(Base):
    def test_over_the_day_limit_the_conversation_says_the_fixed_sentence(self):
        helpers.set_config(usage_quota=True, usage_quota_k=1)        # 1000 tokens a day
        c = profile("Vkdora")  # not Vbdora: test_verbund has its own Vbdora with another PIN (one process: 401)
        uid = uid_of("Vkdora")
        with mock.patch.object(verbrauch, "_day", lambda now: DAY), mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            self.assertFalse(verbrauch.over(uid))
            verbrauch.add("llm", "Gespräch", uid, 900, 0, 200)
            self.assertEqual(verbrauch.over(uid), "tag")
            text = json.dumps(chat(c, "Erzähl mir was über Rom."), ensure_ascii=False)
            self.assertIn("Für heute sind deine Tokens aufgebraucht. Morgen geht es weiter", text)
            r = ADMIN.put("/api/admin/verbrauch/kontingent", json={"uid": uid, "zeit": "tag", "k": 0})   # 0: no limit
            self.assertEqual(r.status_code, 200, r.text)
            self.assertFalse(verbrauch.over(uid))
            self.assertNotIn("aufgebraucht", json.dumps(chat(c, "Und jetzt?"), ensure_ascii=False))
            q = c.get("/api/profile/verbrauch").json()["quota"]
            self.assertFalse(q["on"])
            self.assertEqual(q["limits"], {"tag": 0, "woche": 0, "monat": 0})
            ADMIN.put("/api/admin/verbrauch/kontingent", json={"uid": uid, "zeit": "tag", "k": None})
            self.assertEqual(verbrauch.limits(uid)["tag"], 1000)
            helpers.set_config(usage_quota=False)
            self.assertEqual(verbrauch.limits(uid), {"tag": 0, "woche": 0, "monat": 0})   # switched off: no limit

    def test_week_and_month_name_their_restart_and_the_longest_wins(self):
        helpers.set_config(usage_quota=True, usage_quota_k=0, usage_quota_wk=2, usage_quota_mk=3)
        profile("Vbwoche")
        uid = uid_of("Vbwoche")
        with mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            verbrauch.add("llm", "Gespräch", uid, 2000, 0, 0, now=T)
            self.assertEqual(verbrauch.over(uid, now=T), "woche")
            verbrauch.add("llm", "Gespräch", uid, 1000, 0, 0, now=T)
            self.assertEqual(verbrauch.over(uid, now=T), "monat")
        self.assertIn("Ab Montag geht es weiter", verbrauch.quota_text("woche"))
        oct14 = 1791979200.0   # 2026-10-14 12:00 UTC: the next month is November in every time zone
        self.assertIn("Ab dem 1. November geht es weiter", verbrauch.quota_text("monat", now=oct14))
        self.assertIn("from November 1", verbrauch.quota_text("monat", en=True, now=oct14))
        for z in verbrauch.ZEITRAEUME:
            self.assertIn("Ich → Verbrauch", verbrauch.quota_text(z))
        self.assertEqual(verbrauch._keys(oct14)["woche"], "2026-W42")

    def test_fixed_commands_still_work_without_the_model(self):
        helpers.set_config(usage_quota=True, usage_quota_k=1)
        c = profile("Vbuhr")
        uid = uid_of("Vbuhr")
        with mock.patch.object(verbrauch, "_day", lambda now: DAY), mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            verbrauch.add("llm", "Gespräch", uid, 5000, 0, 0)
            text = json.dumps(chat(c, "Wie spät ist es?"), ensure_ascii=False)
        self.assertIn("Es ist", text)
        self.assertNotIn("aufgebraucht", text)

    def test_the_warning_comes_once_per_period(self):
        helpers.set_config(usage_quota=True, usage_quota_k=10, usage_quota_warn=80)   # 10000 a day, warned from 8000
        c = profile("Vbwarn")
        uid = uid_of("Vbwarn")
        with mock.patch.object(verbrauch, "_day", lambda now: DAY), mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            verbrauch.add("llm", "Gespräch", uid, 7000, 0, 0)
            self.assertEqual(verbrauch.warn(uid), "")
            verbrauch.add("llm", "Gespräch", uid, 900, 0, 0)    # the answer itself counts about 1000 more
            text = json.dumps(chat(c, "Sag hallo."), ensure_ascii=False)
            self.assertIn("80 % deines Tageskontingents sind verbraucht.", text)
            self.assertNotIn("Tageskontingents", json.dumps(chat(c, "Noch mal."), ensure_ascii=False))
        helpers.set_config(usage_quota_warn=0)
        verbrauch._warned.clear()
        with mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            self.assertEqual(verbrauch.warn(uid), "")

    def test_the_extra_holds_for_today_only(self):
        helpers.set_config(usage_quota=True, usage_quota_k=1)
        profile("Vbmehr")
        uid = uid_of("Vbmehr")
        with mock.patch.object(verbrauch, "_day", lambda now: DAY), mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            verbrauch.add("llm", "Gespräch", uid, 1500, 0, 0)
            self.assertEqual(verbrauch.over(uid), "tag")
            r = ADMIN.post("/api/admin/verbrauch/nachschlag", json={"uid": uid, "k": 1})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(verbrauch.over(uid), "")
            self.assertEqual(verbrauch.extra(uid), 1000)
            row = next(p for p in ADMIN.get("/api/admin/verbrauch").json()["profiles"] if p["id"] == uid)
            self.assertEqual((row["limits"]["tag"], row["extra"]), (2000, 1000))
        with mock.patch.object(verbrauch, "_day", lambda now: "2026-10-15"):
            self.assertEqual(verbrauch.extra(uid), 0)
        for body, code in (({"uid": "u_nobody00000", "k": 5}, 404), ({"uid": uid, "k": 0}, 400),
                           ({"uid": uid, "k": verbrauch.EXTRA_MAX_K + 1}, 400), ({"uid": uid, "k": True}, 400)):
            self.assertEqual(ADMIN.post("/api/admin/verbrauch/nachschlag", json=body).status_code, code, body)
        c = profile("Vbmehr")
        self.assertIn(c.post("/api/admin/verbrauch/nachschlag", json={"uid": uid, "k": 5}).status_code, (401, 403))

    def test_the_quota_endpoint_checks_its_input(self):
        profile("Vkdora")
        uid = uid_of("Vkdora")
        for body, code in (({"uid": "u_nobody00000", "k": 5}, 404), ({"uid": uid, "k": -1}, 400),
                           ({"uid": uid, "k": "viel"}, 400), ({"uid": uid, "k": True}, 400),
                           ({"uid": uid, "zeit": "jahr", "k": 5}, 400),
                           ({"uid": uid, "zeit": "tag", "k": verbrauch.ZEITRAEUME["tag"][3] + 1}, 400),
                           ({"uid": uid, "zeit": "monat", "k": verbrauch.ZEITRAEUME["monat"][3]}, 200)):
            self.assertEqual(ADMIN.put("/api/admin/verbrauch/kontingent", json=body).status_code, code, body)
        self.assertEqual(verbrauch.quotas()[uid], {"monat": verbrauch.ZEITRAEUME["monat"][3]})
        import admin
        from fastapi import HTTPException
        cfg = ADMIN.get("/api/config").json()
        for key, bad in (("usage_quota_wk", -1), ("usage_quota_mk", True), ("usage_quota_warn", 100), ("usage_quota_k", "x")):
            new = json.loads(json.dumps(cfg))
            new["chat"][key] = bad
            with self.assertRaises(HTTPException, msg=key):
                admin.validate(new)

    def test_the_quota_is_never_for_guests_or_the_spark(self):
        helpers.set_config(usage_quota=True)
        none = {"tag": 0, "woche": 0, "monat": 0}
        self.assertEqual(verbrauch.limits(verbrauch.GUEST), none)
        self.assertEqual(verbrauch.limits(verbrauch.SPARK), none)
        verbrauch.add("llm", "Gespräch", verbrauch.SPARK, 10 ** 9, 0, 0)
        self.assertEqual(verbrauch.over(verbrauch.SPARK), "")

    def test_writing_help_and_documents_stop_at_a_full_limit(self):
        import docmake
        import schreib
        from fastapi import HTTPException
        helpers.set_config(usage_quota=True, usage_quota_k=1)
        profile("Vbschreib")
        uid = uid_of("Vbschreib")
        with mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            verbrauch.add("llm", "Schreibhilfe", uid, 2000, 0, 0)
            with self.assertRaises(HTTPException) as e:
                schreib._quota(uid)
            self.assertEqual(e.exception.status_code, 429)
            self.assertIn("aufgebraucht", e.exception.detail)
            with self.assertRaises(ValueError) as e:
                docmake._can_start(uid)
            self.assertIn("aufgebraucht", str(e.exception))

    def test_the_running_totals_survive_a_restart_and_come_from_the_days_once(self):
        profile("Vbstand")
        uid = uid_of("Vbstand")
        with mock.patch.object(verbrauch, "_keys", lambda now: KEYS):
            verbrauch.add("llm", "Gespräch", uid, 400, 0, 100, now=T)
            verbrauch.save(now=T)
            with open(verbrauch.STAND_FILE) as f:
                self.assertEqual(json.load(f)["woche"], {"p": "2026-W42", "who": {uid: 500}})
            verbrauch._st["loaded"] = False
            for z in verbrauch.ZEITRAEUME:
                verbrauch._stand[z] = ["", {}]
            self.assertEqual(verbrauch.used(uid)["woche"], 500)
            os.remove(verbrauch.STAND_FILE)                      # the first start: from the stored months
            verbrauch._st["loaded"] = False
            verbrauch._stand["monat"] = ["", {}]
            verbrauch._load()
        self.assertEqual(verbrauch._stand["monat"][1].get(uid, 0), sum(v[verbrauch.IN] + v[verbrauch.OUT]
                         for k, v in verbrauch._months.get("2026-10", {}).items() if k == f"llm|Gespräch|{uid}"))

    def test_live_counts_the_profiles_at_a_full_limit(self):
        helpers.set_config(usage_quota=True, usage_quota_k=1)
        profile("Vblive")
        uid = uid_of("Vblive")
        with mock.patch.object(verbrauch, "_keys", lambda now: KEYS), mock.patch.object(verbrauch, "_day", lambda now: DAY):
            self.assertEqual(verbrauch.for_live()["full"], 0)
            verbrauch.add("llm", "Gespräch", uid, 2000, 0, 0)
            self.assertEqual(verbrauch.for_live()["full"], 1)


class Live(Base):
    def test_the_box_of_the_language_model_shows_numbers(self):
        verbrauch.add("llm", "Gespräch", "s", 300, 0, 20)
        d = verbrauch.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["today"], 320)
        self.assertGreaterEqual(d["rate"], 320)
        self.assertEqual(set(d), {"on", "rate", "today", "calls", "full"})


WIDE = "document.documentElement.scrollWidth<=document.documentElement.clientWidth"


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Pages(unittest.TestCase):
    """Zustand → Verbrauch, the card under Monitoring and Ich → Verbrauch at 1280, 390 and 320 px: drawn, no error
    (strict CSP), nothing wider than the screen; the period buttons and an area's tasks work."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    def setUp(self):
        helpers.set_config(usage_count=True, usage_quota=True, usage_quota_k=2000)
        self.addCleanup(helpers.set_config, usage_count=False, usage_quota=False)
        self.addCleanup(verbrauch.clear)
        verbrauch.clear()
        profile("Vbseite")
        uid = uid_of("Vbseite")
        for i in range(30):
            verbrauch.add("llm", "Gespräch", uid, 4000 + 100 * i, 2000, 300, ms=1800, now=T - 86400 * i)
            verbrauch.add("llm", "Steckbrief", "s", 9000, 0, 600, ms=4000, now=T - 86400 * i)
        verbrauch.add("llm", "Gespräch", uid, 52000, 30000, 900, ms=2100)
        verbrauch.add("asr", "Frage hören", uid, amount=64.5, ms=300)
        verbrauch.add("tts", "Antwort sprechen", uid, amount=128.0)
        verbrauch.add("embed", "Suchindex", amount=120)

    async def _until(self, pg, expr):
        for _ in range(200):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    async def _run(self, w, h):
        async with async_playwright() as p:
            exe = chromium()
            br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
            try:
                pg = await (await br.new_context(viewport={"width": w, "height": h}, locale="de-DE")).new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text else None)
                base = f"http://127.0.0.1:{self.port}"
                await pg.route("**/api/setup", lambda route: route.fulfill(json={"done": True})
                               if route.request.method == "GET" else route.continue_())
                await pg.goto(base + "/")
                self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
                self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Vbseite", "pin": "1234"})).status, 200)
                await pg.goto(base + "/")
                await self._until(pg, "typeof ADMIN!=='undefined'&&ADMIN===true&&!!PROFILE&&document.body.classList.contains('adm')")
                # the card under Monitoring (asks the panel once Zustand is open, V01.0.750)
                await pg.evaluate("goSec('mon')")
                await self._until(pg, "!document.getElementById('zverbrauch').hidden")
                self.assertIn("Tokens", await pg.inner_text("#zverbrauch"))
                # Zustand → Verbrauch
                await pg.evaluate("goSec('usage')")
                await self._until(pg, "!!document.querySelector('#usgmain .vb-tile')&&!!window.lzIdle&&lzIdle()")
                self.assertEqual(await pg.evaluate("document.querySelectorAll('#usgmain .vb-bar').length"), 30)
                self.assertIn("Vbseite", await pg.inner_text("#usgmain"))
                self.assertIn("+500 heute", await pg.inner_text("#usgmain"))   # the card „Kontingent“
                self.assertTrue(await pg.evaluate(WIDE), f"{w}: Zustand → Verbrauch")
                await pg.click("#usgmain [data-vbarea='hintergrund']")
                await self._until(pg, "!!document.querySelector('#usgmain .vb-task')")
                self.assertIn("Steckbrief", await pg.inner_text("#usgmain"))
                for z, n in (("12m", 12), ("24h", 24)):
                    await pg.click(f"#usgseg [data-vbz='{z}']")
                    await self._until(pg, f"document.querySelectorAll('#usgmain .vb-bar').length==={n}")
                    self.assertTrue(await pg.evaluate(WIDE), f"{w}: {z}")
                # Ich → Verbrauch: only the own numbers, with the quota
                await pg.evaluate("openMe('usebox')")
                await self._until(pg, "!!document.querySelector('#usebox .vb-tile')")
                text = await pg.inner_text("#usebox")
                self.assertIn("Diese Woche", text)
                self.assertIn("neu um 0 Uhr", text)
                self.assertNotIn("Steckbrief", text)
                self.assertTrue(await pg.evaluate(WIDE), f"{w}: Ich → Verbrauch")
                self.assertEqual(errors, [])
            finally:
                await br.close()

    def test_pages_on_a_computer_and_phones(self):
        for w, h in ((1280, 900), (390, 844), (320, 700)):
            asyncio.run(self._run(w, h))


if __name__ == "__main__":
    unittest.main()
