"""Krisenspiel gemeinsam (krisenteam.py, plan krisenspiel/plan.md Paket 11): up to three more players join a profile's
running game by an invitation link, each with a role.

- Off by default (chat.krisenspiel_team, under IT-Krisenspiel): without it the seat's routes are 404 and the owner
  cannot invite; switched off later, every seat stops at once.
- Only the hash of the code is kept, the code only comes back once (with its QR code); the owner's list never shows it.
- A seat sees the fixed values and texts of the game, never the narrator's words, the inspector, the console or the
  owner's history and achievements, and takes only the moves of its role (Leitung all); a stale move is refused.
- Expiry, „Entfernen“, a new game of the owner, a blocked owner end the seat; wrong codes lock like a PIN; another
  site's Origin is refused; at most PLAETZE seats.
- Journal lines with fixed words only, never the code or the typed name; Live numbers only; the owner's data
  deletion takes the seats along.

No wall clock in the checks: expiry is tested with a given now.
"""
import asyncio
import contextlib
import io
import json
import os
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import features  # noqa: E402
import guard  # noqa: E402
import krisenspiel as K  # noqa: E402
import krisenteam as KT  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
BASE = "https://spark.example"


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def code_of(link):
    return link.split("#krise=", 1)[1]


class Rollen(unittest.TestCase):
    def test_every_move_has_a_known_role_and_every_scenario_needs_the_team(self):
        self.assertEqual(K.check_data(), [])
        for sid, sz in K.SZENARIEN.items():
            roles = {a.get("rolle", "technik") for a in K._all_actions(sz)}
            self.assertEqual(roles, set(K.ROLLEN), sid)

    def test_leitung_may_all_the_others_only_their_own(self):
        st = K.new_game("ransomware", "normal", 77, now=1_800_000_000)
        for a in K.available(st):
            self.assertTrue(K.darf("leitung", a))
            self.assertEqual(K.darf("technik", a), a["rolle"] == "technik")
            self.assertEqual(K.darf("kommunikation", a), a["rolle"] == "kommunikation")
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                K.move(st, "polizei", rolle="technik")
            self.assertEqual(st["zug"], 0)
            K.move(st, "polizei", rolle="kommunikation", wer={"rolle": "kommunikation", "name": "Ute"})
        self.assertEqual([c["wer"] for c in st["chronik"] if c.get("wer")], [{"rolle": "kommunikation", "name": "Ute"}])
        self.assertEqual(st["trace"][-1]["steps"][0]["daten"]["rolle"], "kommunikation")


class Team(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Ksteam Tom")

    def setUp(self):
        helpers.keep_chat(self, "krisenspiel", "krisenspiel_team", "deny")
        helpers.set_config(krisenspiel=True, krisenspiel_team=True, deny={})
        guard.reset()
        if os.path.exists(KT.FILE):
            os.remove(KT.FILE)
        KT._seen.clear()
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        g = self.c.post("/api/profile/krisenspiel/neu", json={"szenario": "ransomware", "stufe": "normal", "seed": 77})
        self.assertEqual(g.status_code, 200, g.text)
        self.v = TestClient(panel.app)   # a player without a profile

    def invite(self, rolle="technik", status=200):
        r = self.c.post("/api/profile/krisenspiel/team", json={"rolle": rolle, "base": BASE})
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    def lage(self, code, status=200, **kw):
        r = self.v.post("/api/krise/lage", json=dict({"code": code}, **kw))
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["krisenspiel_team"], False)
        self.assertNotIn("krisenteam", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["krisenteam"].parent, "krisenspiel")
        code = code_of(self.invite()["link"])
        helpers.set_config(krisenspiel_team=False)
        self.lage(code, 404)
        self.assertEqual(self.v.post("/api/krise/zug", json={"code": code, "aktion": "logs", "zug": 0}).status_code, 404)
        self.assertEqual(self.c.get("/api/profile/krisenspiel/team").status_code, 403)
        self.invite(status=403)
        self.assertFalse(self.c.get("/api/profile/krisenspiel").json()["team"])
        helpers.set_config(krisenspiel_team=True)
        self.lage(code)
        self.assertTrue(self.c.get("/api/profile/krisenspiel").json()["team"])

    def test_only_the_hash_and_the_code_once(self):
        made = self.invite()
        code = code_of(made["link"])
        self.assertTrue(made["link"].startswith(BASE + "/#krise="))
        self.assertTrue(KT.CODE.fullmatch(code))
        self.assertIn("<svg", made["qr"])
        with open(KT.FILE) as f:
            raw = f.read()
        self.assertNotIn(code, raw)
        self.assertIn(KT._hash(code), raw)
        listed = json.dumps(self.c.get("/api/profile/krisenspiel/team").json())
        self.assertNotIn(code, listed)
        self.assertNotIn(KT._hash(code), listed)
        self.assertEqual(self.c.get("/api/profile/krisenspiel/team").json()["plaetze"][0]["rolle"], "technik")

    def test_a_seat_sees_the_game_and_plays_its_role(self):
        code = code_of(self.invite("technik")["link"])
        d = self.lage(code, name="Ute <b>")
        self.assertEqual((d["rolle"], d["name"], d["zug"]), ("technik", "Ute b", 0))
        for key in ("trace", "konsole", "verlauf", "erfolge", "stats", "seed"):
            self.assertNotIn(key, d)
        self.assertEqual({a["id"] for a in d["aktionen"] if a["darf"]},
                         {a["id"] for a in d["aktionen"] if a["rolle"] == "technik"})
        self.assertEqual(self.lage(code, name="Anders")["name"], "Ute b")   # the name stays as it came first
        self.assertTrue(self.c.get("/api/profile/krisenspiel/team").json()["plaetze"][0]["online"])
        r = self.v.post("/api/krise/zug", json={"code": code, "aktion": "polizei", "zug": 0})
        self.assertEqual(r.status_code, 422)
        r = self.v.post("/api/krise/zug", json={"code": code, "aktion": "logs", "zug": 0})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["zug"], 1)
        self.assertEqual(self.v.post("/api/krise/zug", json={"code": code, "aktion": "isolieren", "zug": 0}).status_code, 409)
        self.assertEqual(self.v.post("/api/krise/zug", json={"code": code, "aktion": "x;rm", "zug": 1}).status_code, 400)
        g = self.c.get("/api/profile/krisenspiel").json()["spiel"]       # the owner sees the move and who took it
        self.assertEqual(g["zug"], 1)
        self.assertEqual([c["wer"] for c in g["chronik"] if c.get("wer")], [{"rolle": "technik", "name": "Ute b"}])
        self.assertEqual(self.c.get("/api/profile/krisenspiel/team").json()["zug"], 1)
        # the narrator's words never reach a seat
        st = K.load(self.uid)
        st["spiel"]["chronik"][-1]["erzaehlt"] = "Erzaehlt vom Modell"
        K.save(self.uid, st)
        self.assertNotIn("Erzaehlt vom Modell", json.dumps(self.lage(code)))

    def test_leitung_and_kommunikation(self):
        lead = code_of(self.invite("leitung")["link"])
        talk = code_of(self.invite("kommunikation")["link"])
        self.assertEqual(self.v.post("/api/krise/zug", json={"code": talk, "aktion": "polizei", "zug": 0}).status_code, 200)
        self.assertEqual(self.v.post("/api/krise/zug", json={"code": lead, "aktion": "logs", "zug": 1}).status_code, 200)
        self.assertEqual(len(self.lage(talk)["team"]), 3)          # the owner and two seats

    def test_the_end_of_a_seat(self):
        made = [self.invite(r) for r in ("technik", "kommunikation", "leitung")]
        self.invite(status=409)                                     # PLAETZE
        self.invite("chef", status=400)
        code = code_of(made[0]["link"])
        self.assertEqual(self.c.delete(f"/api/profile/krisenspiel/team/{made[0]['id']}").status_code, 200)
        self.lage(code, 400)
        self.assertEqual(self.c.delete(f"/api/profile/krisenspiel/team/{made[0]['id']}").status_code, 404)
        self.assertEqual(self.c.delete("/api/profile/krisenspiel/team/x;y").status_code, 404)
        code = code_of(made[1]["link"])
        v = KT.find(code)
        self.assertIsNotNone(v)
        self.assertIsNone(KT.find(code, now=v["until"] + 1))       # expiry
        helpers.set_config(deny={"krisenteam": [self.uid]})        # the owner blocked
        self.lage(code, 400)
        helpers.set_config(deny={})
        guard.reset()
        self.lage(code)
        self.c.post("/api/profile/krisenspiel/neu", json={"szenario": "san", "seed": 3})   # a new game ends every seat
        self.lage(code, 400)
        self.assertEqual(self.c.get("/api/profile/krisenspiel/team").json()["plaetze"], [])

    def test_wrong_codes_lock_and_other_sites_are_refused(self):
        self.invite()
        for _ in range(guard.MAX_FAILS):
            self.v.post("/api/krise/lage", json={"code": "A" * 32})
        self.assertEqual(self.v.post("/api/krise/lage", json={"code": "B" * 32}).status_code, 429)
        guard.reset()
        r = self.v.post("/api/krise/lage", json={"code": "A" * 32}, headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.v.post("/api/krise/lage", json={"code": "kurz"}).status_code, 400)

    def test_journal_live_and_own_data(self):
        made = self.invite("technik")
        code = code_of(made["link"])
        self.lage(code, name="Geheimname")
        self.v.post("/api/krise/zug", json={"code": code, "aktion": "logs", "zug": 0})
        self.v.post("/api/krise/zug", json={"code": code, "aktion": "polizei", "zug": 1})
        self.v.post("/api/krise/lage", json={"code": "C" * 32})
        d = KT.for_live()
        self.assertEqual((d["on"], d["plaetze"], d["online"]), (True, 1, 1))
        self.assertGreaterEqual(d["zuege"], 1)
        for v in d.values():
            self.assertIsInstance(v, (int, bool))
        K._live.update(at=0.0, d=None)
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            cfg = json.load(f)
        was = cfg.setdefault("logs", {}).get("live", False)
        cfg["logs"]["live"] = True
        helpers.write_config(cfg)
        try:
            snap = json.dumps(ADMIN.get("/api/admin/live").json(), ensure_ascii=False)
        finally:
            cfg["logs"]["live"] = was
            helpers.write_config(cfg)
        self.assertNotIn("Geheimname", snap)
        self.assertIn("gemeinsam", snap)
        self.assertEqual(features.OWN["krisenteam"][0](self.uid), 1)
        features.OWN["krisenteam"][1](self.uid)
        self.lage(code, 400)
        log = self.out.getvalue()
        for line in log.splitlines():
            self.assertTrue(line.startswith("spiel: ") or line.startswith("live"), line)
        for word in ("Geheimname", code, "Ksteam", "polizei"):
            self.assertNotIn(word, log)
        for want in ("spiel: team | einladung | technik", "spiel: team zug | ok | technik",
                     "spiel: team zug abgelehnt | nicht erlaubt", "spiel: team abgelehnt | falscher code"):
            self.assertIn(want, log)
        self.assertIn("spiel", live.TARGETS)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(krisenspiel=True, krisenspiel_team=True, krisenspiel_erzaehler=False)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(krisenspiel=False, krisenspiel_team=False)

    def test_invite_a_player_and_use_the_editors(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for w in (1280, 390):
                    br, pg, errors = await b.page(p, w, 900)
                    try:
                        guard.reset()
                        st = await pg.evaluate("apiTry('/api/profile/krisenspiel/neu',xjson('POST',{szenario:'ransomware',seed:77})).then(x=>x.r.status)")
                        self.assertEqual(st, 200)
                        await pg.evaluate("KS_ON=true;KS.data=null;KS.team=null;KS.made=null;KS.ed=null;KS.big=false;KS.con=true;icTabSet('spiel','spiel');goSec('spiel')")
                        await b.until(pg, "!!document.querySelector('#ksview [data-ksinvite]')")
                        await pg.click("#ksview [data-ksinvite]")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-teamlink')")
                        link = await pg.input_value("#ksview .ks-teamlink")
                        self.assertIn("/#krise=", link)
                        # the player: another browser without any login
                        ctx2 = await br.new_context(viewport={"width": w, "height": 900}, locale="de-DE", bypass_csp=True)
                        g = await ctx2.new_page()
                        gerr = []
                        g.on("pageerror", lambda e: gerr.append(str(e)))
                        await g.goto(link)
                        await b.until(g, "!!document.getElementById('kggo')")
                        self.assertEqual(await g.evaluate("location.hash"), "")          # the code leaves the address bar
                        await g.fill("#kgname", "Ute")
                        await g.click("#kggo")
                        await b.until(g, "!!document.querySelector('#kgcard [data-kgmove]:not([disabled])')")
                        self.assertGreater(await g.evaluate("document.querySelectorAll('#kgcard [data-kgmove][disabled]').length"), 0)
                        await g.evaluate("document.querySelector('#kgcard [data-kgmove]:not([disabled])').click()")
                        await b.until(g, "!KG.busy&&KG.d.zug===1")
                        over = await g.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the player's page scrolls sideways")
                        await b.until(pg, "KS.data.spiel.zug===1&&!!document.querySelector('#ksview .ks-team .pill.ok')")
                        self.assertIn("Ute", await pg.evaluate("document.querySelector('#ksview .ks-chron').textContent"))
                        self.assertEqual(gerr, [])
                        await ctx2.close()
                        # Tab completes paths, the large console and back
                        await pg.fill("#ksview .ks-in", "cat /etc/pas")
                        await pg.press("#ksview .ks-in", "Tab")
                        self.assertEqual(await pg.input_value("#ksview .ks-in"), "cat /etc/passwd ")
                        await pg.fill("#ksview .ks-in", "cat /etc/hos")              # hostname and hosts: their common start
                        await pg.click("#ksview [data-kstabkey]")
                        self.assertEqual(await pg.input_value("#ksview .ks-in"), "cat /etc/host")
                        await pg.fill("#ksview .ks-in", "")
                        await pg.click("#ksview [data-ksbig]")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-condet.ks-big')")
                        await pg.keyboard.press("Escape")
                        await b.until(pg, "!document.querySelector('#ksview .ks-condet.ks-big')")
                        # nano: Ctrl+O writes, Ctrl+X leaves
                        await pg.fill("#ksview .ks-in", "nano notiz.txt")
                        await pg.press("#ksview .ks-in", "Enter")
                        await b.until(pg, "!KS.busy&&!!document.querySelector('#ksview .ks-ed.nano .ks-edtext')")
                        await pg.fill("#ksview .ks-edtext", "eins\nzwei\n")
                        await pg.press("#ksview .ks-edtext", "Control+o")
                        await b.until(pg, "!KS.busy&&KS.ed&&KS.ed.saved===KS.ed.text")
                        await pg.press("#ksview .ks-edtext", "Control+x")
                        await b.until(pg, "!KS.busy&&!document.querySelector('#ksview .ks-ed')&&!!document.querySelector('#ksview .ks-in')")
                        # vi: i writes, Esc, :wq
                        await pg.fill("#ksview .ks-in", "vi notiz.txt")
                        await pg.press("#ksview .ks-in", "Enter")
                        await b.until(pg, "!KS.busy&&!!document.querySelector('#ksview .ks-ed.vi .ks-edtext[readonly]')")
                        await pg.press("#ksview .ks-edtext", "o")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-ed.vi .ks-edtext:not([readonly])')")
                        await pg.keyboard.type("drei")
                        await pg.keyboard.press("Escape")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-ed.vi .ks-edtext[readonly]')")
                        await pg.keyboard.press(":")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-edcmd')")
                        await pg.keyboard.type("wq")
                        await pg.keyboard.press("Enter")
                        await b.until(pg, "!KS.busy&&!document.querySelector('#ksview .ks-ed')")
                        await pg.fill("#ksview .ks-in", "cat notiz.txt")
                        await pg.press("#ksview .ks-in", "Enter")
                        await b.until(pg, "!KS.busy&&[...document.querySelectorAll('#ksview .ks-con .kc-out')].some(x=>x.textContent==='drei')")
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the page scrolls sideways")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
