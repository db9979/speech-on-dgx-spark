"""Mitteilung antippen öffnet genau diese Meldung (mitteilungen.py, Dominik 2026-10-23 „nach Empfehlung umsetzen“).

- Every note to the iPhone app, the Android app, the Begleiter or a browser is kept on the Spark for KEEP seconds with
  a random number; only that number leaves with the note ("n" over Apple, "m" to the others).
- The card's target is picked by fixed rules from the kind of note (ziel): Vorgang, chat, new mail, code, way, text.
  Only fixed patterns pass; a way comes from the text or the kind (begleiter.note_weg).
- Only the own profile gets its note back (another profile's number answers 404 like an old one); the endpoints need a
  login and have a rate limit; every opening writes one journal line with fixed words only, never the text.
- The devices open the card: the iPhone app on a tap (Relay → Conversation.openNote → MitteilungKarte), the browser
  (sw.js → #meldung= / message), the Android app (NotePoll → #meldung=) and the Begleiter on the Mac (default click).

No wall clock beyond now= and no network.
"""
import asyncio
import contextlib
import io
import os
import re
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import android  # noqa: E402
import begleiter  # noqa: E402
import guard  # noqa: E402
import mitteilungen  # noqa: E402
import push  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import pair, profile, uid_of  # noqa: E402

ROOT = os.path.dirname(helpers.APP)
STATIC = os.path.join(helpers.APP, "panel", "static")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def outside(*p):
    """A file of the apps (android/, ios/, tools/): not in a copy with only app/ (the Spark tests only that)."""
    path = os.path.join(ROOT, *p)
    if not os.path.exists(path):
        raise unittest.SkipTest(f"{os.path.relpath(path, ROOT)} is not in this copy (the Spark tests only app/)")
    return read(path)


class Rules(unittest.TestCase):
    def setUp(self):
        mitteilungen._box.clear()

    def z(self, tag="", body="Text", vg="", ref="", title="T"):
        return mitteilungen.ziel({"tag": tag, "title": title, "body": body, "vg": vg, "ref": ref})

    def test_each_kind_of_note_gets_its_fixed_target(self):
        self.assertEqual(self.z(vg="v0123456789"), {"art": "vorgang", "vg": "v0123456789"})
        self.assertEqual(self.z(tag="chat-c0123456789ab"), {"art": "chat", "chat": "c0123456789ab"})
        self.assertEqual(self.z(tag="mail-new", ref="m0123abcd:42"),
                         {"art": "mail", "ref": "m0123abcd:42", "weg": begleiter.NOTE_WEG["mail-new"]})
        self.assertEqual(self.z(tag="mailcode", body="AB12CD · Bank"), {"art": "code", "code": "AB12CD"})
        self.assertEqual(self.z(body="Dein Lied liegt unter Ich → Musik."), {"art": "weg", "weg": "Ich → Musik"})
        self.assertEqual(self.z(tag="briefing", body="3 Termine heute"), {"art": "text"})

    def test_only_fixed_patterns_pass(self):
        self.assertEqual(self.z(vg="v0123<script>")["art"], "text")
        self.assertEqual(self.z(tag="chat-../etc")["art"], "text")
        self.assertEqual(self.z(tag="mail-new", ref="https://x.example/")["art"], "weg")   # only its fixed way
        self.assertEqual(self.z(tag="mailcode", body="hallo welt")["art"], "text")

    def test_kept_a_day_per_profile_and_at_most_max(self):
        mid = mitteilungen.keep("u_000000000001", "Titel", "Geheim", "rem-1", now=1000)
        self.assertRegex(mid, r"^[0-9a-f]{16}$")
        self.assertEqual(mitteilungen.get("u_000000000001", mid, now=1001)["body"], "Geheim")
        self.assertIsNone(mitteilungen.get("u_000000000001", mid, now=1000 + mitteilungen.KEEP + 1))
        self.assertIsNone(mitteilungen.get("u_000000000002", mid, now=1001))   # never another profile's
        self.assertIsNone(mitteilungen.get("u_000000000001", "../x", now=1001))
        for i in range(mitteilungen.MAX + 5):
            mitteilungen.keep("u_000000000001", "t", str(i), now=2000 + i)
        self.assertEqual(len(mitteilungen._box["u_000000000001"]), mitteilungen.MAX)


class Devices(unittest.TestCase):
    """push.send hands the number to the Android app, the Begleiter and the browser; the text stays on the Spark."""

    def setUp(self):
        mitteilungen._box.clear()

    def test_number_goes_with_every_way_text_stays(self):
        uid = "u_0000000000aa"
        sent = []
        with mock.patch.object(push, "encrypt", lambda sub, payload: sent.append(payload) or b"x"), \
                mock.patch.object(push.httpx.AsyncClient, "post", mock.AsyncMock(return_value=mock.Mock(status_code=201))), \
                contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(push._send_one(uid, "web", [{"endpoint": "https://push.example/a"}], "Lied fertig",
                                       "Dein Lied liegt unter Ich → Musik.", "musik", True, "Musik"))
            asyncio.run(push._send_one(uid, "and", [], "Erinnerung", "Tee", "rem-1", True, ""))
            asyncio.run(push._send_one(uid, "desk", [], "Neue Mail von Anna", "Rechnung", "mail-new", True, "",
                                       ref="m0123abcd:7"))
        import json
        web = json.loads(sent[0])
        self.assertRegex(web["m"], r"^[0-9a-f]{16}$")
        self.assertEqual(mitteilungen.get(uid, web["m"])["title"], "Lied fertig")
        a = android.notes(uid, 0)[0][-1]
        self.assertEqual(mitteilungen.get(uid, a["m"])["body"], "Tee")
        d = begleiter.notes(uid, 0)[0][-1]
        self.assertEqual(mitteilungen.ziel(mitteilungen.get(uid, d["m"]))["art"], "mail")

    def test_iphone_gets_the_card_with_its_app_key(self):
        helpers.set_config(iphone=True, deny={})
        try:
            c = profile("Mitteil Mia")
            h = {"X-Speech-Device": pair(c).json()["token"]}
            uid = uid_of("Mitteil Mia")
            mid = mitteilungen.keep(uid, "💬 Anna", "Hallo", "chat-c0123456789ab")
            app = TestClient(panel.app)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                d = app.get("/api/iphone/note", params={"id": mid, "tapped": 1}, headers=h).json()
            self.assertEqual(d["ziel"], {"art": "chat", "chat": "c0123456789ab"})
            self.assertEqual(d["body"], "Hallo")
            self.assertIn("push: mitteilung geoeffnet chat app", out.getvalue())
            self.assertNotIn("Hallo", out.getvalue())
            # the banner's fetch stays as it was: title and text only
            self.assertEqual(set(app.get("/api/iphone/note", params={"id": mid}, headers=h).json()), {"title", "body"})
        finally:
            helpers.set_config(iphone=False, deny={})


class Endpoint(unittest.TestCase):
    def setUp(self):
        mitteilungen._box.clear()
        for k in [k for k in guard._rate if k[0] == "mitteilung"]:
            guard._rate.pop(k, None)

    def test_own_profile_only_with_a_login_and_a_line_each(self):
        c = profile("Mitteil Moritz")
        uid = uid_of("Mitteil Moritz")
        other = profile("Mitteil Mara")
        mid = mitteilungen.keep(uid, "☀️ Dein Tag", "Zahnarzt um 14 Uhr", "briefing", vg="v0123456789")
        self.assertIn(TestClient(panel.app).get("/api/profile/mitteilung", params={"id": mid}).status_code, (401, 403))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(other.get("/api/profile/mitteilung", params={"id": mid}).status_code, 404)
            r = c.get("/api/profile/mitteilung", params={"id": mid})
            self.assertEqual(c.get("/api/profile/mitteilung", params={"id": "nicht-da"}).status_code, 404)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["body"], "Zahnarzt um 14 Uhr")
        self.assertEqual(r.json()["ziel"], {"art": "vorgang", "vg": "v0123456789"})
        log = out.getvalue()
        self.assertIn("push: mitteilung geoeffnet vorgang web", log)
        self.assertIn("push: mitteilung nicht mehr da web", log)
        self.assertNotIn("Zahnarzt", log)

    def test_rate_limited(self):
        c = profile("Mitteil Mats")
        codes = set()
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(guard.RATE["mitteilung"][1] + 2):
                codes.add(c.get("/api/profile/mitteilung", params={"id": "0" * 16}).status_code)
        self.assertIn(429, codes)


class Apps(unittest.TestCase):
    """The devices open the card from the number (code checks; the apps build on GitHub)."""

    def test_browser_opens_the_card(self):
        sw = read(STATIC, "sw.js")
        self.assertIn("m: /^[0-9a-f]{16}$/.test(d.m || '')", sw)
        self.assertIn("'/#meldung=' + m", sw)
        self.assertIn("postMessage({meldung: m})", sw)
        js = read(STATIC, "js", "mitteilung.js")
        self.assertNotRegex(js, r"\.innerHTML|insertAdjacentHTML")
        self.assertIn("/api/profile/mitteilung?id=", js)
        self.assertIn('<script src="/static/js/mitteilung.js"></script>', read(STATIC, "index.html"))
        self.assertIn("mtHash()", read(STATIC, "js", "start.js"))

    def test_android_opens_the_card(self):
        kt = outside("android", "app", "src", "main", "java", "io", "github", "db9979", "spark", "NotePoll.kt")
        self.assertIn('Regex("[0-9a-f]{16}")', kt)
        self.assertIn('"$base/#meldung=$m"', kt)

    def test_iphone_opens_the_card_on_a_tap(self):
        relay = outside("ios", "Spark", "Assistant.swift")
        self.assertRegex(relay, r'UNNotificationDefaultActionIdentifier,\s+let n = response\.notification\.request\.content\.userInfo\["n"\]')
        self.assertIn("Conversation.shared.openNote(n)", relay)
        self.assertIn('"api/iphone/note", query: ["id": id, "tapped": "1"]', outside("ios", "Spark", "Vorgaenge.swift"))
        self.assertIn("MitteilungKarte(x: n)", outside("ios", "Spark", "Views.swift"))

    def test_begleiter_on_the_mac_opens_the_card(self):
        mac = outside("tools", "begleiter", "mac", "Sources", "Model.swift")
        self.assertIn('model.openPanel("#meldung=" + meldung)', mac)
        self.assertTrue(re.search(r'info\["m"\] = meldung', mac))


if __name__ == "__main__":
    unittest.main()
