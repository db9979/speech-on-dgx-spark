"""Funktionen → Weiche → unklar: unclear questions kept anonymized (weiche_unklar.py, plan unklare-fragen).

The protection rules: fixed redaction (names of profiles and the own address book, mail, links, IPs, phone numbers,
secrets, every number), never a sentence with the code word, a second check drops what still leaks, never a guest,
never who asked, only with the admin switch and the profile's preference, admin only to see and delete, gone after
KEEP_DAYS, at most MAX_ROWS. Fixed moments: nothing here depends on the time of day.
"""
import os
import threading
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import contacts  # noqa: E402
import intent  # noqa: E402
import meldung  # noqa: E402
import profiles  # noqa: E402
import weiche  # noqa: E402
import weiche_unklar as wu  # noqa: E402
from common import STATE  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000
ON = dict(routing=True, route_unklar=True, route_words="", route_not="", route_tests=[], route_model="off")
UNKLAR = "Erzähl mir was über Quasare"


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, next(u["id"] for u in profiles.names() if u["name"] == name)


def settle():
    """Wait for the background keep() of the turns just made (threads, not the clock)."""
    for t in threading.enumerate():
        if t.name == "weiche-unklar":
            t.join(10)


def rows():
    return wu.view()["rows"]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(**ON)
        wu._known["k"] = None
        wu.remove()
        self.addCleanup(wu.remove)
        self.addCleanup(helpers.set_config, route_unklar=False)


class Anon(Base):
    def test_personal_parts_become_placeholders(self):
        _, uid = profile("Hildegard")
        cases = {
            "Schreib hildegard@example.org dass Hildegard morgen kommt": "Schreib [MAIL] dass [PERSON] morgen kommt",
            "Ruf Frau Kowalski unter 0171 2345678 an": "Ruf Frau [PERSON] unter [TELEFON] an",
            "Was steht auf https://intern.example.de/plan?x=1": "Was steht auf [URL]",
            "Ist 192.168.178.20 erreichbar": "Ist [IP-LAN] erreichbar",
            "Weck mich um 6:45 und kauf 3 Liter Milch": "Weck mich um [ZAHL] und kauf [ZAHL] Liter Milch",
            "Mein Code ist 4711 bitte merken": "Mein Code ist [ZAHL] bitte merken",
        }
        for q, want in cases.items():
            self.assertEqual(wu.anon(q, uid), want, q)

    def test_contacts_and_secrets_never_stay(self):
        _, uid = profile("Konrad")
        old = contacts.cards
        contacts.cards = lambda u: [{"name": "Zacharias Wunderlich"}] if u == uid else []
        self.addCleanup(setattr, contacts, "cards", old)
        self.assertEqual(wu.anon("Was hat Wunderlich zu Zacharias gesagt", uid), "Was hat [PERSON] zu [PERSON] gesagt")
        helpers.set_config(llm_key="geheim-schluessel-xyz")
        self.addCleanup(helpers.set_config, llm_key="")
        wu._known["k"] = None
        self.assertNotIn("geheim-schluessel-xyz", wu.anon("Sag mal geheim-schluessel-xyz rückwärts", uid) or "")

    def test_code_word_and_leaks_are_never_kept(self):
        self.assertIsNone(wu.anon("Mach die Sauna an [Codewort]"))
        self.assertIsNone(wu.anon("[ZAHL] 42"), "nothing left but placeholders")
        old = meldung.leaks
        meldung.leaks = lambda text, k=None: ["Name"]
        self.addCleanup(setattr, meldung, "leaks", old)
        self.assertIsNone(wu.anon("Eine ganz harmlose Frage"))
        wu.keep(intent.Route([], {}), "Eine ganz harmlose Frage", None, now=NOW)
        d = wu._clean(wu._read(), NOW)
        self.assertEqual((d["rows"], sum(d["dropped"].values())), ([], 1), "dropped and only counted")

    def test_placeholders_are_never_offered_as_words(self):
        self.assertEqual(weiche.suggest("Erinner [PERSON] an [ZAHL] Glitzerkugeln", "erinnerung", {}), ["erinner", "glitzerkugeln"])


class Keeping(Base):
    def test_same_sentence_counts_and_old_ones_go(self):
        for i in range(3):
            wu.keep(intent.Route([], {}), UNKLAR, None, now=NOW + i)
        d = wu._clean(wu._read(), NOW)
        self.assertEqual([(r["q"], r["n"]) for r in d["rows"]], [(UNKLAR, 3)])
        self.assertEqual(set(d["rows"][0]), {"id", "q", "n", "took", "day"}, "no profile, device or time of day")
        self.assertEqual(wu._clean(wu._read(), NOW + (wu.KEEP_DAYS + 1) * 86400)["rows"], [])
        for i in range(wu.MAX_ROWS + 5):
            wu.keep(intent.Route([], {}), f"Frage über Sterne Variante {chr(65 + i % 26)}{chr(65 + i // 26)}", None, now=NOW)
        self.assertLessEqual(len(wu._clean(wu._read(), NOW)["rows"]), wu.MAX_ROWS)

    def test_kept_sealed(self):
        wu.keep(intent.Route([], {}), UNKLAR, None, now=NOW)
        with open(os.path.join(STATE, "weiche-unklar.json")) as f:
            raw = f.read()
        import vault
        if vault.available():
            self.assertNotIn("Quasare", raw)
        self.assertEqual(wu._read()["rows"][0]["q"], UNKLAR)

    def test_group_the_model_took(self):
        r = intent.Route([], {})
        wu.took(r, "websuche")      # the model's tool can come before keep() has written
        wu.keep(r, UNKLAR, None, now=NOW)
        r2 = intent.Route([], {})
        wu.keep(r2, UNKLAR, None, now=NOW)
        wu.took(r2, "websuche")
        self.assertEqual(wu._read()["rows"][0]["took"], {"websuche": 2})


class Chat(Base):
    def ask(self, c, text=UNKLAR):
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": text}]})
        self.assertEqual(r.status_code, 200, r.text)
        helpers.events(r)
        settle()

    def test_only_unclear_questions_of_profiles_with_everything_on(self):
        c, uid = profile("Ottfrieda")
        self.ask(c)
        self.assertEqual([x["q"] for x in rows()], [UNKLAR])
        self.assertNotIn("Ottfrieda", str(wu._read()), "never who asked")
        self.ask(c, "Mach das Licht im Flur an")
        self.assertEqual(len(rows()), 1, "a question a rule recognized is not kept")
        # the profile's preference off
        profiles.save_settings(uid, {"unklar_anon": False})
        self.addCleanup(profiles.save_settings, uid, {"unklar_anon": True})
        self.ask(c, "Erzähl mir was über Pulsare")
        self.assertEqual(len(rows()), 1)
        profiles.save_settings(uid, {"unklar_anon": True})
        # the admin switch off
        helpers.set_config(route_unklar=False)
        self.ask(c, "Erzähl mir was über Neutronensterne")
        self.assertEqual(len(rows()), 1)

    def test_never_guests(self):
        helpers.set_config(public=True)
        self.addCleanup(helpers.set_config, public=False)
        guest = TestClient(panel.app)
        guest.post("/api/chat", json={"messages": [{"role": "user", "content": UNKLAR}]})
        settle()
        self.assertEqual(rows(), [])


class Page(Base):
    def test_admin_sees_and_deletes(self):
        wu.keep(intent.Route([], {}), UNKLAR, None)
        wu.keep(intent.Route([], {}), "Erzähl mir was über Pulsare", None)
        today = __import__("time").time()     # the rows are kept with today's day; Live counts from the same moment
        d = ADMIN.get("/api/admin/weiche").json()["unklar"]["fragen"]
        self.assertTrue(d["on"])
        self.assertEqual(len(d["rows"]), 2)
        rid = d["rows"][0]["id"]
        self.assertEqual(ADMIN.delete("/api/admin/weiche/unklar/zz").status_code, 400)
        self.assertEqual(ADMIN.delete(f"/api/admin/weiche/unklar/{rid}").json()["gone"], 1)
        self.assertEqual(len(rows()), 1)
        self.assertEqual(weiche.live_today(now=today)["anon"], 1, "Live: only the number")
        self.assertEqual(ADMIN.delete("/api/admin/weiche/unklar").json()["gone"], 1)
        self.assertEqual(rows(), [])
        helpers.set_config(route_unklar=False)
        self.assertIsNone(weiche.live_today(now=today)["anon"])

    def test_profiles_never_see_or_delete(self):
        c, _ = profile("Eberhard")
        wu.keep(intent.Route([], {}), UNKLAR, None)
        self.assertIn(c.get("/api/admin/weiche").status_code, (401, 403))
        self.assertIn(c.delete("/api/admin/weiche/unklar").status_code, (401, 403))
        self.assertEqual(len(rows()), 1)


if __name__ == "__main__":
    unittest.main()
