"""Gesperrt, aber eigene Daten (Dominik 2026-10-14: „Auf der Seite nur „Daten löschen“ zeigen“): when the admin blocks a
released function for one profile (chat.deny), Ich hides its page; what the profile stored for it stays its own. In
place of the page Ich shows a short note with the number of stored entries and „Daten löschen“ (whoami "locked",
DELETE /api/profile/owndata/{key}, features.OWN). Only the profile's own browser login, only while blocked, never a
guest or a device key. Every function with a page under Ich is in features.OWN or listed in OHNE with its reason.
No test reads the clock; each test makes its own profiles and removes them again."""
import asyncio
import contextlib
import io
import itertools
import os
import unittest

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()
import panel  # noqa: E402
import account  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import logfilter  # noqa: E402
import profiles  # noqa: E402
import telegram  # noqa: E402
import weather  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel", "static")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
_N = itertools.count(1)

# functions with a page under Ich (account.WHO) that keep no „Daten löschen“ card, each with its reason
OHNE = {
    "mailmanage": "ordnet nur Mails im eigenen Postfach, speichert nichts im Spark; die Mails löscht das Postfach selbst",
    "maildelete": "legt nur Mails im eigenen Postfach in dessen Papierkorb (endgültig nur dort), speichert nichts im Spark",
    "mailsend": "gesendete Mails liegen im Postfach unter Gesendet; im Spark bleibt nur die Vorschau höchstens 10 Minuten, ein Vorschlag per Sprache 5 Minuten",
    "bildaendern": "geänderte und hochgeladene Bilder liegen bei den Bildern (features.OWN bilder, Ich → Bilder)",
    "musikbearbeiten": "Fassungen und hochgeladene Dateien liegen bei den Liedern (features.OWN musik, Ich → Musik)",
    "documents": "alle Dokumente auf einmal wären zu einschneidend; jedes Dokument hat sein eigenes Löschen unter Ich → Dokumente",
    "erstellen": "erstellte Dokumente gehören zu den Dokumenten (dasselbe einschneidende Löschen)",
    "parcels": "keine eigenen Daten: liest nur das Postfach (E-Mail)",
    "tasks": "kein eigener Löschweg: die Listen liegen in Home Assistant, gespeichert ist nur die Zuordnung",
    "android": "kein eigener Löschweg der Funktion: die App-Schlüssel stehen unter Ich → Sicherheit (Geräte)",
    "androidlive": "keine eigenen Daten (Unterschalter der Android-App)",
    "androidupdate": "keine eigenen Daten: nur die App-Version im Speicher (Unterschalter der Android-App)",
    "androidassist": "keine eigenen Daten: Fragen und Antworten landen im Verlauf (Gespräche), dort löschbar",
    "androidlock": "keine eigenen Daten: die App fragt Android, der Spark speichert nichts",
    "pebblefolge": "keine eigenen Daten: die Vorschläge leben nur mit der Antwort im Speicher",
    "pebbleerinnern": "keine eigenen Daten: die Erinnerungen gehören zu Timer und Erinnerungen, die Uhr hält nur eine Kopie",
    "pebblezifferblatt": "keine eigenen Daten: das Zifferblatt zeigt nur, was andere Funktionen haben",
    "pebbletag": "keine eigenen Daten: Tag und Woche werden bei jedem Abruf neu gebaut",
    "pebblemeldung": "keine eigenen Daten: die Meldungen gehören zum Dienst-Wächter",
    "pebblemerken": "keine eigenen Daten: das Gemerkte liegt im Gedächtnis (Ich → Gedächtnis)",
    "pebbleort": "keine eigenen Daten: der Ort steht im gemerkten Satz im Gedächtnis",
    "pebblechat": "keine eigenen Daten: die Nachrichten gehören zu den Chats",
    "pebbleantwort": "keine eigenen Daten: die Vorschläge leben nur mit dem Abruf im Speicher",
    "iphonepanel": "keine eigenen Daten (Unterschalter der iPhone-App)",
    "schreibapps": "keine eigenen Daten (Unterschalter der Schreibhilfe)",
    "begleitertun": "keine eigenen Daten (Unterschalter des Begleiters)",
    "begleitermeeting": "keine eigenen Daten: Mitschriften landen als Dokumente",
    "begleiterschirm": "keine eigenen Daten: nur das neueste Bild im Arbeitsspeicher, weg mit dem Ende der Sitzung",
    "begleiterbedienen": "keine eigenen Daten: der Auftrag lebt nur im Arbeitsspeicher, das Ergebnis ist eine Meldung",
    "room": "keine eigenen Daten: der Raum-Modus läuft am Lautsprecher",
    "roomtv": "keine eigenen Daten (Unterschalter des Raum-Modus)",
    "roomfar": "keine eigenen Daten (Unterschalter des Raum-Modus)",
    "rmsend": "die Daten gehören zur reMarkable-Verbindung (remarkable)",
    "rmfresh": "die Daten gehören zur reMarkable-Verbindung (remarkable)",
    "rmguide": "die Daten gehören zur reMarkable-Verbindung (remarkable)",
    "rmpapier": "die Daten gehören zur reMarkable-Verbindung (remarkable)",
    "naszustand": "keine Daten des Profils: nur der Haupt-Admin richtet den Zustand der NAS unter Funktionen ein und vergisst ihn dort",
    "nashaushalt": "die Ordner gehören zu den Wissensordnern des Admin-Profils (nasquelle); andere Profile finden nur mit",
    "rmaufgaben": "die Daten gehören zur reMarkable-Verbindung (remarkable)",
    "mystatus": "keine eigenen Daten: zeigt nur, was andere Funktionen wissen",
    "vorrang": "keine eigenen Daten: die Stufe gibt der Admin",
    "halive": "keine eigenen Daten (Meldungen aus Home Assistant)",
    "haloud": "keine eigenen Daten (Ansagen aus Home Assistant)",
    "havoice": "die Regeln gehören zu „Von selbst melden“ (proactive)",
    "hacam": "keine eigenen Daten (Kamerabild nur im Moment)",
    "mailwichtig": "keine eigenen Daten (Einordnung beim Lesen)",
    "melden": "Meldungen sind schon bei GitHub; der Spark hält nichts Löschbares fürs Profil",
    "speicher": "einschneidend: ausgelagerte Originale liegen vielleicht nur dort; erst „Fehlendes zurückholen“ auf der eigenen Seite",
    "nas": "Verbindungen hängen an Kopie meiner Daten und Wissensordnern; Löschen nur dort der Reihe nach",
    "nasablage": "die Dateien liegen auf der eigenen NAS (spark_ablage), auf dem Spark nur zwei Vorlieben ohne Inhalte",
    "chats": "geteilt: Chats gehören auch den anderen Personen darin",
    "chatgroups": "geteilt: Gruppen gehören allen Mitgliedern",
    "chatmedia": "geteilt: Anhänge gehören zum Chat",
    "chatinvite": "geteilt: Einladungen betreffen andere Personen",
    "chatprivate": "geteilt: private Chats gehören beiden Seiten",
    "verbund": "geteilt: Chats mit anderen Sparks",
    "verbundmedia": "geteilt: Fotos und Dateien gehören zu den Chats mit anderen Sparks (deren Löschen gilt)",
    "verbundgruppen": "geteilt: Gruppen mit anderen Sparks sind Gruppen-Chats (deren Verlassen und Löschen gilt)",
    "anrufe": "keine eigenen Daten: nur die Zeile im Chat, die zum Chat gehört (dessen Löschen gilt)",
    "anrufeturn": "keine eigenen Daten: der Vermittler merkt sich nichts, sein Zugang läuft nach einer Stunde ab",
}


def profile(prefix):
    name = f"{prefix}{next(_N)}"
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "4711"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "4711"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def place(uid):
    profiles._write(weather._file(uid), {"lat": 52.5, "lon": 13.4, "name": "Berlin"})


def keep_config(case, *keys):
    """Puts the chat switches back as they were before the test (other test modules in the same run rely on them)."""
    import json
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        chat = json.load(f)["chat"]
    old = {k: chat[k] for k in keys if k in chat}
    gone = [k for k in keys if k not in chat]

    def back():
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        for k in gone:
            c["chat"].pop(k, None)
        c["chat"].update(old)
        helpers.write_config(c)
    case.addCleanup(back)


class Base(unittest.TestCase):
    def setUp(self):
        keep_config(self, "weather", "deny", "reminders", "telegram", "esp32")
        helpers.set_config(weather=True, deny={})
        self.a, self.ua = profile("Owna")
        self.b, self.ub = profile("Ownb")
        for u in (self.ua, self.ub):
            self.addCleanup(profiles.delete_user, u)
            self.addCleanup(weather.forget, u)
            place(u)

    def block(self, *keys):
        helpers.set_config(deny={k: [self.ua] for k in keys})
        for k in keys:
            self.assertTrue(features.blocked(k, self.ua), k)
            self.assertFalse(features.blocked(k, self.ub), k)

    def locked(self, client):
        return client.get("/api/whoami").json()["locked"]


class Coverage(unittest.TestCase):
    def test_every_ich_function_has_a_card_or_a_reason(self):
        who = set(account.WHO.values())
        self.assertEqual(set(features.OWN) & set(OHNE), set(), "in OWN and in OHNE")
        self.assertEqual(who - set(features.OWN) - set(OHNE), set(), "neither in features.OWN nor in OHNE with a reason")
        self.assertEqual(set(OHNE) - who, set(), "OHNE names a function without an Ich page")
        self.assertEqual(set(features.OWN) - who, set(), "features.OWN names a function without an Ich page")
        for k, why in OHNE.items():
            self.assertGreater(len(why), 15, k)

    def test_every_card_has_a_page_to_stand_on(self):
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
            html = f.read()
        for k in features.OWN:
            box = features.BY_KEY[k].me or account.OWN_BOX.get(k, "")
            self.assertTrue(box, k)
            self.assertIn(f'id="{box}"', html, k)

    def test_count_and_clear_are_callable_and_count_nothing_for_a_new_profile(self):
        _, uid = profile("Ownleer")
        self.addCleanup(profiles.delete_user, uid)
        for k, (count, clear) in features.OWN.items():
            self.assertTrue(callable(clear), k)
            self.assertEqual(count(uid), 0, k)


class Whoami(Base):
    def test_locked_lists_a_blocked_function_with_data_numbers_only(self):
        self.assertEqual(self.locked(self.a), [])
        self.block("weather")
        got = self.locked(self.a)
        self.assertEqual([(x["key"], x["box"], x["n"]) for x in got], [("weather", "wxbox", 1)])
        self.assertNotIn("Berlin", str(got))   # numbers, never contents
        self.assertFalse(self.a.get("/api/whoami").json()["weather"], "the page itself stays hidden")
        self.assertEqual(self.locked(self.b), [], "another profile keeps its page")

    def test_nothing_without_data_or_while_the_admin_has_it_off(self):
        self.block("weather")
        helpers.set_config(weather=False)
        self.assertEqual(self.locked(self.a), [], "admin off: no card")
        helpers.set_config(weather=True)
        weather.forget(self.ua)
        self.assertEqual(self.locked(self.a), [], "no data: no card")

    def test_never_for_guests_or_device_keys(self):
        self.block("weather")
        self.assertEqual(TestClient(panel.app).get("/api/whoami").json()["locked"], [])
        dev = TestClient(panel.app, headers={profiles.DEVICE_HEADER: profiles.add_device("Owndev", self.ua)})
        self.assertEqual(dev.get("/api/whoami").json()["locked"], [])


class Route(Base):
    def test_blocked_deletes_the_own_data(self):
        self.block("weather")
        r = self.a.delete("/api/profile/owndata/weather")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"ok": True, "n": 1})
        self.assertEqual(features.OWN["weather"][0](self.ua), 0)
        self.assertEqual(self.locked(self.a), [])
        self.assertEqual(features.OWN["weather"][0](self.ub), 1, "the other profile keeps its place")

    def test_not_blocked_is_refused_with_the_way_to_the_page(self):
        r = self.b.delete("/api/profile/owndata/weather")
        self.assertEqual(r.status_code, 409)
        self.assertIn("unter Ich", r.json()["detail"])
        self.assertEqual(features.OWN["weather"][0](self.ub), 1)

    def test_unknown_function_is_404(self):
        self.block("weather")
        self.assertEqual(self.a.delete("/api/profile/owndata/gibtsnicht").status_code, 404)
        self.assertEqual(self.a.delete("/api/profile/owndata/documents").status_code, 404, "drastic: not in OWN")

    def test_guest_and_device_key_are_refused(self):
        self.block("weather")
        self.assertEqual(TestClient(panel.app).delete("/api/profile/owndata/weather").status_code, 401)
        dev = TestClient(panel.app, headers={profiles.DEVICE_HEADER: profiles.add_device("Owndev", self.ua)})
        self.assertEqual(dev.delete("/api/profile/owndata/weather").status_code, 403)
        self.assertEqual(features.OWN["weather"][0](self.ua), 1, "nothing deleted")

    def test_rate_limit(self):
        codes = [self.a.delete("/api/profile/owndata/gibtsnicht").status_code for _ in range(guard.RATE["owndata"][1] + 1)]
        self.assertEqual(codes[-1], 429)
        self.assertEqual(set(codes[:-1]), {404})

    def test_more_kinds_of_data(self):
        """Reminders (account.py), the linked Telegram chat and the speakers (an awaitable clear) go the same way."""
        self.block("reminders", "telegram", "esp32")
        helpers.set_config(weather=True, reminders=True, telegram=True, esp32=True)
        profiles.add_reminder(self.ua, "Müll", 4_102_444_800_000)
        profiles.add_reminder(self.ua, "Post", 4_102_444_800_000)
        profiles._write(telegram._link_file(self.ua), {"chat": 12345})
        self.addCleanup(telegram.unlink, self.ua)
        got = {x["key"]: x["n"] for x in self.locked(self.a)}
        self.assertEqual(got.get("reminders"), 2)
        self.assertEqual(got.get("telegram"), 1)
        self.assertNotIn("esp32", got, "no speakers: no card")
        for k, n in (("reminders", 2), ("telegram", 1), ("esp32", 0)):
            r = self.a.delete(f"/api/profile/owndata/{k}")
            self.assertEqual(r.json(), {"ok": True, "n": n}, k)
        self.assertEqual(profiles.reminders(self.ua), [])
        self.assertIsNone(telegram.link(self.ua))

    def test_one_journal_line_for_every_outcome(self):
        self.block("weather")
        cases = (("weather", "profiles: own data deleted while blocked | weather | 1 entries"),
                 ("gibtsnicht", "profiles: own data not deleted | unknown function"),
                 ("telegram", "profiles: own data not deleted | telegram not blocked"))
        name = profiles.by_id(self.ua)["name"]
        for key, start in cases:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.a.delete(f"/api/profile/owndata/{key}")
            lines = [x for x in out.getvalue().splitlines() if x.startswith("profiles:")]
            self.assertEqual(len(lines), 1, (key, lines))
            self.assertTrue(lines[0].startswith(start), lines)
            self.assertNotIn(name, lines[0])
            self.assertEqual(logfilter.parse(lines[0])["area"], "gedaechtnis")

    def test_a_failing_clear_says_so_in_the_journal(self):
        self.block("weather")
        old = features.OWN["weather"]

        def broken(uid):
            raise OSError("disk")
        features.OWN["weather"] = (old[0], broken)
        self.addCleanup(features.OWN.__setitem__, "weather", old)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.a.delete("/api/profile/owndata/weather")
        self.assertEqual(r.status_code, 500)
        self.assertIn("profiles: own data delete failed | weather | OSError", out.getvalue())


class Static(unittest.TestCase):
    def test_card_texts_have_english_and_no_inline_code(self):
        with open(os.path.join(STATIC, "js", "me.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function meOwn()", js)
        self.assertIn("t('Daten löschen','Delete data')", js)
        self.assertIn("(People and devices → Blocked functions)", js)
        self.assertIn("/api/profile/owndata/", js)
        self.assertNotIn("onclick=\"", js)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    def setUp(self):
        keep_config(self, "weather", "deny")
        helpers.set_config(weather=True, deny={})
        self.name = f"Ownweb{next(_N)}"
        profiles.add_user(self.name, "4711")
        self.uid = next(u["id"] for u in profiles._load()["users"] if u["name"] == self.name)
        self.addCleanup(profiles.delete_user, self.uid)
        self.addCleanup(weather.forget, self.uid)
        place(self.uid)
        helpers.set_config(deny={"weather": [self.uid]})

    def test_card_in_place_of_the_page_and_delete(self):
        async def go():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                try:
                    for w, h in ((1280, 900), (390, 844), (320, 640)):
                        place(self.uid)
                        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE")
                        pg = await ctx.new_page()
                        errors = []
                        pg.on("pageerror", lambda e: errors.append(str(e)))
                        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
                        base = f"http://127.0.0.1:{self.port}"
                        await pg.goto(base + "/")
                        r = await pg.request.post(base + "/api/profile/login", data={"name": self.name, "pin": "4711"})
                        self.assertEqual(r.status, 200)
                        await pg.goto(base + "/")
                        for _ in range(100):   # the strict CSP of the page allows no wait_for_function (eval)
                            if await pg.evaluate("typeof ME_OWN!=='undefined'&&ME_OWN.length===1"):
                                break
                            await pg.wait_for_timeout(100)
                        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
                        await pg.evaluate("openMe('wxbox')")
                        await pg.wait_for_selector("#wxbox .meown button", state="visible")
                        text = await pg.inner_text("#wxbox .meown p")
                        self.assertIn("„Wetter“ für dich gesperrt", text)
                        self.assertIn("Gespeichert: 1 Eintrag.", text)
                        shown = await pg.evaluate("[...document.querySelectorAll('#wxbox>*')].filter(e=>getComputedStyle(e).display!=='none').map(e=>e.className)")
                        self.assertEqual(shown, ["meown"], f"{w}: only the card shows")
                        over = await pg.evaluate("(()=>{const b=document.querySelector('#profmodal .mebody');return b.scrollWidth-b.clientWidth})()")
                        self.assertLessEqual(over, 0, f"{w}: no sideways scroll")
                        await pg.click("#wxbox .meown button")
                        await pg.wait_for_selector("#wxbox .meown", state="detached")
                        self.assertEqual(weather.get(self.uid), {})
                        tabs = await pg.evaluate("[...document.querySelectorAll('#ptabs button[data-t]')].map(b=>b.dataset.t)")
                        self.assertNotIn("wxbox", tabs, f"{w}: the page leaves the list")
                        self.assertEqual(errors, [])
                        await ctx.close()
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
