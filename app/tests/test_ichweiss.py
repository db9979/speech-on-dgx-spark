"""Was ich über dich weiß (ichweiss.py, plan persoenlicher-assistent, Dominik 2026-10-18 „3a 4a 6a 7a“, stages 3 and 4):
interests count only after „Stimmt“, „Nicht so“ is remembered, the web tip sends only the interest word, recurring bills
come from headers only, the sums only from checked amounts; never for guests, blocked profiles or with the switch off;
logs carry no contents. Rules get fixed days; the end-to-end tests put their dates relative to the day they run."""
import asyncio
import contextlib
import datetime
import io
import os
import unittest

from tests import helpers
from tests.test_panel import ADMIN, profile  # noqa: F401  (ADMIN logs in once)
from tests import test_fuerdich as tf
from tests.test_fuerdich import dated

import features  # noqa: E402
import fuerdich  # noqa: E402
import ichweiss  # noqa: E402
import mail  # noqa: E402
import profiles  # noqa: E402

FMB = helpers.FakeMailbox
DAY = datetime.date(2026, 10, 18)


class Rules(unittest.TestCase):
    def test_amounts_and_sums(self):
        self.assertEqual(ichweiss.cents("84,20 €"), 8420)
        self.assertEqual(ichweiss.cents("1.234,50 €"), 123450)
        self.assertEqual(ichweiss.cents(""), 0)
        self.assertEqual(ichweiss.euro(123450), "1.234,50 €")
        items = [{"kind": "rechnung", "amount": "84,20 €", "sent": "2026-10-03"},
                 {"kind": "bestellung", "amount": "49,90 €", "sent": "2026-10-11"},
                 {"kind": "bestellung", "amount": "10,00 €", "sent": "2026-09-30"},      # last month
                 {"kind": "angebot", "day": "2026-10-20", "sent": "2026-10-12"},
                 {"kind": "rechnung", "amount": "kaputt", "sent": "2026-10-12"}]
        m = ichweiss.month_sum(items, DAY)
        self.assertEqual((m["bills"], m["orders"], m["total"], m["n"]), (8420, 4990, 13410, 2))
        self.assertEqual(ichweiss.month_line(m),
                         "Diesen Monat aus Mails: 134,10 € (Rechnungen 84,20 €, Bestellungen 49,90 €), aus 2 Mails.")

    def test_monthly_reminder_day(self):
        now = datetime.datetime(2026, 10, 18, 12, tzinfo=datetime.timezone.utc)
        self.assertEqual(ichweiss.next_monthly(15, now).date().isoformat(), "2026-11-15")
        self.assertEqual(ichweiss.next_monthly(20, now).date().isoformat(), "2026-10-20")
        self.assertEqual(ichweiss.next_monthly(31, now).date().isoformat(), "2026-10-28")
        dec = datetime.datetime(2026, 12, 20, 12, tzinfo=datetime.timezone.utc)
        self.assertEqual(ichweiss.next_monthly(1, dec).date().isoformat(), "2027-01-01")

    def test_names_are_cleaned(self):
        self.assertEqual(ichweiss.clean('  Rose <Bikes> "Shop"  '), "Rose Bikes Shop")
        self.assertEqual(ichweiss.norm("Rose  Bikes"), "rose bikes")
        self.assertLessEqual(len(ichweiss.clean("x" * 100)), ichweiss.NAME_MAX)

    def test_topics_come_from_fixed_words(self):
        """Plan interessen-themen (Dominik 2026-10-22 „ok“): a topic from fixed words and domains, never a sender's name;
        each word in one topic only; service and machine senders are never an interest."""
        self.assertEqual(ichweiss.topics_in("IoTThinks New ESP32 board", "iotthinks.example"), ["smarthome"])
        self.assertEqual(ichweiss.topics_in("Sonokinetic New orchestral sample library", "x.example"), ["musikproduktion"])
        self.assertEqual(ichweiss.topics_in("Neuigkeiten", "lieferando.de"), ["essen"])
        self.assertEqual(ichweiss.topics_in("Automatisch verlängert", "x.example"), [])        # a whole word, not a part
        self.assertEqual(ichweiss.topics_in("Dein Gutschein-Code", "news.example"), [])
        self.assertTrue(ichweiss.service("notifications@github.com"))
        self.assertTrue(ichweiss.service("noreply@mail.github.com"))
        self.assertTrue(ichweiss.service("security@shop.example"))
        self.assertFalse(ichweiss.service("newsletter@lieferando.de"))
        self.assertEqual(ichweiss.topic_of({"news": 6, "topics": {"smarthome": 3}}), "smarthome")
        self.assertEqual(ichweiss.topic_of({"news": 9, "topics": {"smarthome": 2}}), "")          # under a third
        self.assertEqual(ichweiss.topic_of({"news": 1, "topics": {"smarthome": 1}}), "")          # one mail is no topic
        seen = {}
        for k, (de, en, words, doms) in ichweiss.TOPICS.items():
            self.assertTrue(de and en and words, k)
            self.assertLessEqual(len(de), ichweiss.NAME_MAX, k)
            self.assertEqual(ichweiss.clean(de), de, k)                     # a topic is a valid interest name
            for w in list(words) + list(doms):
                self.assertNotIn(w.lower(), seen, f"{w} in {k} and {seen.get(w.lower())}")
                seen[w.lower()] = k

    def test_web_tip_takes_only_https(self):
        self.assertEqual(ichweiss._safe_url("https://shop.example/a?b=1"), ("https://shop.example/a?b=1", "shop.example"))
        for bad in ("http://shop.example/", "javascript:alert(1)", "https://shop.example/<x>", "ftp://a.example"):
            self.assertEqual(ichweiss._safe_url(bad), ("", ""), bad)


def fifteenth(today, back):
    """The 15th of the month that lies back months before today's (the bills of Wiederkehrendes)."""
    y, m = divmod(today.year * 12 + today.month - 1 - back, 12)
    return datetime.date(y, m + 1, 15)


class IchWeiss(unittest.TestCase):
    """The page with the mailbox of test_fuerdich (its setUp, tearDown and profiles) plus orders and monthly bills."""
    setup_profile = tf.FuerDich.setup_profile
    tearDown = tf.FuerDich.tearDown

    def setUp(self):
        tf.FuerDich.setUp(self)
        ichweiss._rec.clear()
        fuerdich._shops.clear()
        today = datetime.date.today()
        orders = [dated(helpers.box_mail("Rose Bikes <shop@rosebikes.example>", "Deine Bestellung 47" + str(i),
                                         "Gesamtsumme: 49,90 €"), 2 + i) for i in range(2)]
        bills = [dated(helpers.box_mail("Telekom <rechnung@telekom.example>", "Ihre Rechnung",
                                        "Rechnungsbetrag 39,95 €"), (today - fifteenth(today, k)).days) for k in range(1, 5)]
        for raw in orders + bills:
            FMB.put("INBOX", raw)
        helpers.set_config(search=False)

    def test_interests_count_only_after_yes(self):
        p, uid = self.setup_profile("Wissa")
        p.get("/api/profile/fuerdich")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            d = p.get("/api/profile/ichweiss").json()
        names = [x["name"] for x in d["proposals"]]
        self.assertIn("Sport & Fitness", names)                            # the topic, not the shop's name
        self.assertNotIn("Rose Bikes", names)
        rose = next(x for x in d["proposals"] if x["name"] == "Sport & Fitness")
        self.assertEqual((rose["why"], rose["senders"], rose["topic"], rose["en"]),
                         ("2 Bestellungen in 30 Tagen", ["Rose Bikes"], "sport", "Sports & fitness"))
        self.assertEqual(d["interests"], [])
        self.assertNotIn("Rose", out.getvalue())                          # the log names no shop
        yes = {"name": "Sport & Fitness", "state": "yes", "src": "thema", "topic": "sport", "senders": ["Rose Bikes"]}
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json=yes).status_code, 200)
        d = p.get("/api/profile/ichweiss").json()
        self.assertEqual([(x["name"], x["senders"]) for x in d["interests"]], [("Sport & Fitness", ["Rose Bikes"])])
        self.assertNotIn("Sport & Fitness", [x["name"] for x in d["proposals"]])
        self.assertEqual(ichweiss.fits(uid, "Rose Bikes"), "Sport & Fitness")
        self.assertEqual(ichweiss.fits(uid, "Neuer Laden", "Laufschuhe für den Marathon", "news@neu.example"), "Sport & Fitness")
        # „Nicht so“ is remembered: no proposal again
        p.post("/api/profile/ichweiss/interest", json=dict(yes, state="no"))
        self.assertNotIn("Sport & Fitness", [x["name"] for x in p.get("/api/profile/ichweiss").json()["proposals"]])
        self.assertEqual(ichweiss.fits(uid, "Rose Bikes"), "")
        for bad in ({"name": "x", "state": "yes"}, {"name": "Rad", "state": "maybe"}, {"name": ["a"], "state": "yes"},
                    {"name": "Rad", "state": "yes", "web": "ja"}, {"name": "Rad", "state": "yes", "src": "modell"},
                    {"name": "Rad", "state": "yes", "topic": "quatsch"}, {"name": "Rad", "state": "adopt"},
                    {"name": "Rad", "state": "yes", "senders": "Rose"}, {"name": "Rad", "state": "yes", "senders": [1]},
                    {"name": "Rad", "state": "yes", "senders": ["a"] * 21}):
            self.assertEqual(p.post("/api/profile/ichweiss/interest", json=bad).status_code, 400, bad)
        raw = profiles.own_bytes(uid, "interessen.json").decode()   # opened: the seal would hide everything
        for bad in ("Gesamtsumme", "49,90", "shop@"):
            self.assertNotIn(bad, raw)
        self.assertEqual(features.OWN["ichweiss"][0](uid), 1)
        self.assertEqual(p.delete("/api/profile/ichweiss").status_code, 200)
        self.assertFalse(os.path.exists(profiles._path(uid, "interessen.json")))

    def test_topics_instead_of_senders(self):
        """Plan interessen-themen 1a-6a: topics with the senders as chips and up to three subjects as evidence, a sender
        without a topic as „Thema unklar“, never the own address or a service (GitHub), a chip said no to stays out, an
        own topic for an unclear sender, older confirmed senders asked once for their topic; subjects only on the page,
        never in the log or a file."""
        news = {"List-Unsubscribe": "<mailto:x@example.org>"}
        for subj in ("ESP32 Neuigkeiten", "Neuer Zigbee-Sensor", "IoT Wochenbrief"):
            FMB.put("INBOX", helpers.box_mail("IoTThinks <news@iotthinks.example>", subj, headers=news))
        for subj in ("Neuigkeiten aus dem Oktober", "Unser Herbstbrief"):
            FMB.put("INBOX", helpers.box_mail("hasso <brief@hasso.example>", subj, headers=news))
        for i in range(3):
            FMB.put("INBOX", helpers.box_mail("db9979 <notifications@github.com>", f"[db9979/speech] Run {i} failed",
                                              headers={"List-Id": "db9979/speech <speech.db9979.github.com>"}))
            FMB.put("INBOX", helpers.box_mail(f"Ich <{helpers.MAIL_USER}>", f"Notiz {i}", headers=news))
        p, uid = self.setup_profile("Wissthema")
        p.get("/api/profile/fuerdich")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            d = p.get("/api/profile/ichweiss").json()
        props = {x["name"]: x for x in d["proposals"]}
        iot = props["Smart Home & IoT"]
        self.assertEqual((iot["senders"], iot["why"], iot["unclear"]), (["IoTThinks"], "3 Newsletter in 30 Tagen", False))
        self.assertEqual(sorted(iot["ex"]), ["ESP32 Neuigkeiten", "IoT Wochenbrief", "Neuer Zigbee-Sensor"])
        self.assertTrue(props["hasso"]["unclear"])
        self.assertEqual(len(props["hasso"]["ex"]), 2)
        flat = str(d["proposals"])
        for never in ("db9979", "github", helpers.MAIL_USER, "Ich"):           # own and service senders are no interest
            self.assertNotIn(never, [x["name"] for x in d["proposals"]])
            self.assertNotIn(never, [s for x in d["proposals"] for s in x["senders"]])
        self.assertNotIn("db9979", flat)
        for word in ("ESP32", "Zigbee", "Herbstbrief", "IoTThinks", "hasso"):   # the log has counts only
            self.assertNotIn(word, out.getvalue())
        # 6a: an older confirmed sender is asked once for its topic, „Übernehmen“ moves it into the topic
        ichweiss.set_state(uid, "IoTThinks", "yes", "shop")
        d = p.get("/api/profile/ichweiss").json()
        self.assertEqual([(x["name"], x["topic"]) for x in d["asks"]], [("IoTThinks", "smarthome")])
        self.assertNotIn("Smart Home & IoT", [x["name"] for x in d["proposals"]])
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "IoTThinks", "state": "adopt", "topic": "smarthome"}).status_code, 200)
        d = p.get("/api/profile/ichweiss").json()
        self.assertEqual([(x["name"], x["senders"]) for x in d["interests"]], [("Smart Home & IoT", ["IoTThinks"])])
        self.assertEqual(d["asks"], [])
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "IoTThinks", "state": "adopt", "topic": "smarthome"}).status_code, 404)
        # „So lassen“: asked no more, the sender stays
        ichweiss.set_state(uid, "Rose Bikes", "yes", "shop")
        self.assertEqual([x["name"] for x in p.get("/api/profile/ichweiss").json()["asks"]], ["Rose Bikes"])
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "Rose Bikes", "state": "keep"}).status_code, 200)
        d = p.get("/api/profile/ichweiss").json()
        self.assertEqual(d["asks"], [])
        self.assertIn("Rose Bikes", [x["name"] for x in d["interests"]])
        # an own topic for the unclear sender (4a): the sender belongs to it from now on
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "Wandern", "state": "yes", "src": "hand",
                                                                        "senders": ["hasso"]}).status_code, 200)
        self.assertNotIn("hasso", [x["name"] for x in p.get("/api/profile/ichweiss").json()["proposals"]])
        self.assertEqual(ichweiss.fits(uid, "hasso"), "Wandern")
        # an own topic picked from the ones there are (Dominik 2026-10-22): the confirmed first, then the list; a list
        # topic named in German or English is that topic
        ch = p.get("/api/profile/ichweiss").json()["choices"]
        # an older confirmed sender (no topic) is no topic to pick (Dominik 2026-10-22: the chips looked like entries)
        self.assertEqual([x["name"] for x in ch[:2]], ["Smart Home & IoT", "Wandern"])
        self.assertNotIn("Rose Bikes", [x["name"] for x in ch])
        self.assertTrue(next(x for x in p.get("/api/profile/ichweiss").json()["interests"] if x["name"] == "Rose Bikes")["old"])
        self.assertEqual([x["topic"] for x in ch].count("smarthome"), 1)              # a confirmed topic only once
        self.assertIn({"name": "Essen bestellen", "en": "Food delivery", "topic": "essen"}, ch)
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "food delivery", "state": "yes",
                                                                        "senders": ["Pizzaladen"]}).status_code, 200)
        item = next(x for x in p.get("/api/profile/ichweiss").json()["interests"] if x["name"] == "Essen bestellen")
        self.assertEqual((item["topic"], item["senders"]), ("essen", ["Pizzaladen"]))
        # rename a confirmed interest (Dominik 2026-10-22): an old sender name becomes a sender of the topic it gets
        r = p.post("/api/profile/ichweiss/interest", json={"name": "Rose Bikes", "state": "rename", "to": "Sport & Fitness"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["item"]["topic"], r.json()["item"]["senders"]), ("sport", ["Rose Bikes"]))
        names = [x["name"] for x in p.get("/api/profile/ichweiss").json()["interests"]]
        self.assertIn("Sport & Fitness", names)
        self.assertNotIn("Rose Bikes", names)
        self.assertEqual(ichweiss.fits(uid, "Rose Bikes"), "Sport & Fitness")
        r = p.post("/api/profile/ichweiss/interest", json={"name": "Wandern", "state": "rename", "to": "Bergwandern"})
        self.assertEqual((r.json()["item"]["name"], r.json()["item"]["senders"]), ("Bergwandern", ["hasso"]))
        self.assertEqual(ichweiss.fits(uid, "hasso"), "Bergwandern")
        # ✕ at a sender in the details: it leaves the topic and stays out
        r = p.post("/api/profile/ichweiss/interest", json={"name": "Sport & Fitness", "state": "drop", "senders": ["Rose Bikes"]})
        self.assertEqual((r.status_code, r.json()["item"]["senders"]), (200, []))
        self.assertEqual(ichweiss.fits(uid, "Rose Bikes"), "")
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "Sport & Fitness", "state": "drop", "senders": ["Rose Bikes"]}).status_code, 404)
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "Sport & Fitness", "state": "drop", "senders": []}).status_code, 400)
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "Gibtsnicht", "state": "rename", "to": "Xyz"}).status_code, 404)
        self.assertEqual(p.post("/api/profile/ichweiss/interest", json={"name": "Bergwandern", "state": "rename", "to": " x "}).status_code, 400)
        raw = profiles.own_bytes(uid, "interessen.json").decode()   # opened: the seal would hide everything
        for word in ("ESP32", "Zigbee", "Herbstbrief", "Oktober", "iotthinks.example"):   # subjects never in the file
            self.assertNotIn(word, raw)

    def test_more_of_this_on_a_card(self):
        p, uid = self.setup_profile("Wissb")
        items = p.get("/api/profile/fuerdich").json()["items"]
        order = next(x for x in items if x["kind"] == "bestellung")
        self.assertIn("more", order["acts"])
        ichweiss.set_state(uid, order["who"], "yes", "karte")
        fuerdich._v.forget(uid)
        order = next(x for x in p.get("/api/profile/fuerdich").json()["items"] if x["kind"] == "bestellung")
        self.assertNotIn("more", order["acts"])
        self.assertEqual(order["fits"], order["who"])

    def test_recurring_bills_and_monthly_reminder(self):
        p, uid = self.setup_profile("Wissc")
        d = p.get("/api/profile/ichweiss").json()
        rec = [x for x in d["recurring"] if x["who"] == "Telekom"]
        self.assertEqual(len(rec), 1, d["recurring"])
        self.assertGreaterEqual(rec[0]["months"], 3)
        self.assertFalse(rec[0]["set"])
        r = p.post("/api/profile/ichweiss/recurring", json={"id": rec[0]["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["text"].startswith("Rechnung Telekom kommt um den 15."))
        self.assertEqual([x.get("every") for x in profiles.reminders(uid) if x["text"] == r.json()["text"]], ["monthly"])
        self.assertTrue(p.post("/api/profile/ichweiss/recurring", json={"id": rec[0]["id"]}).json()["again"])
        self.assertTrue([x for x in p.get("/api/profile/ichweiss").json()["recurring"] if x["who"] == "Telekom"][0]["set"])
        self.assertEqual(p.post("/api/profile/ichweiss/recurring", json={"id": "nope"}).status_code, 404)

    def test_week_and_month(self):
        p, uid = self.setup_profile("Wissd")
        d = p.get("/api/profile/ichweiss").json()
        self.assertTrue(d["week"]["sentence"].startswith("Deine Woche: 0 erledigt, "))
        self.assertTrue(d["month"]["line"].startswith("Diesen Monat aus Mails: ") or d["month"]["n"] == 0)

    def test_web_tip_sends_only_the_word(self):
        import chat
        p, uid = self.setup_profile("Wisse")
        ichweiss.set_state(uid, "Rennrad", "yes", "hand", web=True)
        asked, saved = [], chat.web_search

        async def search(c, cc, query):
            asked.append(query)
            return "", [{"title": "Bestes Rennrad <b>2026</b>", "url": "http://plain.example/x"},
                        {"title": "Rennrad-Test", "url": "https://rad.example/test"}]
        chat.web_search = search
        try:
            now = datetime.datetime.now(datetime.timezone.utc).replace(hour=12)
            tip = asyncio.run(ichweiss.tip_run(uid, now))
            again = asyncio.run(ichweiss.tip_run(uid, now))            # once a day
        finally:
            chat.web_search = saved
        self.assertEqual(asked, ["Rennrad"])
        self.assertEqual((tip["url"], tip["domain"], tip["name"]), ("https://rad.example/test", "rad.example", "Rennrad"))
        self.assertIsNone(again)

    def test_off_blocked_and_guests(self):
        p, uid = self.setup_profile("Wissf")
        helpers.set_config(mail_insight=False)
        self.assertEqual(p.get("/api/profile/ichweiss").status_code, 403)
        helpers.set_config(mail_insight=True, deny={"ichweiss": [uid]})
        self.assertEqual(p.get("/api/profile/ichweiss").status_code, 403)
        helpers.set_config(deny={})
        self.assertFalse(features.allowed("ichweiss", None))
        from fastapi.testclient import TestClient
        import panel
        self.assertIn(TestClient(panel.app).get("/api/profile/ichweiss").status_code, (401, 403))
