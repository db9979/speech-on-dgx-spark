"""Steuerzentrale am Bildschirm (plan Raspberry-Pi split B9, panel/schirm.py + steuerzentrale.py): off by default, the
panel answers only the screen on this machine (loopback, no forwarded sender) and only with its key, never what was
asked or answered or a profile's name; the unit follows the admin switch; the times switch the screen dark; the
picture fits every screen from small to 4K, draws every service the Live picture knows (the screen grows with every
change, Dominik 2026-10-16) and replaces glyphs the console font lacks. No wall clock dependence: every time is given.
"""
import json
import os
import re
import stat
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import common  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import schirm  # noqa: E402
import steuerzentrale as sz  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_live import reset, set_logs  # noqa: E402
from tests.test_tracelog import SECRET, ask, profile  # noqa: E402

LOKAL = ("127.0.0.1", 50000)
HEIM = ("192.168.1.40", 50000)
T0 = time.mktime((2026, 10, 16, 14, 0, 0, 0, 0, -1))      # 14:00 local time
NACHT = time.mktime((2026, 10, 16, 23, 30, 0, 0, 0, -1))
MORGEN = time.mktime((2026, 10, 16, 6, 30, 0, 0, 0, -1))


def set_chat(**kw):
    c = common.load_config()
    c["chat"].update(kw)
    helpers.write_config(c)


def beispiel(split=True, n_targets=None):
    """A state as the panel sends it, with two running requests (one through a tool to the internet)."""
    targets = [{"id": k, "name": v[0], "sub": v[1], "zone": "net" if v[2] == "net" else v[2]} for k, v in live.TARGETS.items()]
    if n_targets is not None:
        targets = targets[:n_targets]
    karten = [{"id": "modell", "name": "tars", "cpu": 31, "kerne": 20, "ram_total": 119.7, "ram_frei": 45.2, "temp": 62, "ok": True,
               "gpu": {"util": 64}, "llm": "qwen38-27b", "platte_pct": 41,
               "kurven": {"cpu": [30, 40, None, 35], "gpu": [50, 70, 60], "frei": [45, 44], "temp": [60, 61]},
               "dienste": [{"id": "asr", "state": "active"}, {"id": "llm", "state": "active"}, {"id": "bild", "state": "inactive"}]},
              {"id": "panel", "name": "pi", "cpu": 16, "kerne": 4, "ram_total": 7.9, "ram_frei": 7.2, "temp": 49, "ok": True, "luefter": False,
               "platte_pct": 12, "strom": {"spannung": "ok", "drossel": "nein"}, "kurven": {"cpu": [10, 20], "frei": [7.1], "temp": [48]},
               "dienste": [{"id": "turn", "state": "active"}, {"id": "schirm", "state": "active"}]}]
    web = next(k for k, v in live.TARGETS.items() if v[2] == "net")
    return {"t": T0, "an": True, "versatz": [1, 2], "schrift": "auto", "zeiten": [7, 23], "live_an": True,
            "tag": {"version": "V01.0.999", "backup": T0 - 3600, "answers": 47, "first_sound": 1.1, "hours": list(range(24)),
                    "speakers": {"known": 2, "online": 1}},
            "hinweise": [{"kind": "rechner", "level": "warn", "text": "Pi ist heiß"}],
            "rechner": {"an": True, "liste": karten} if split else {"an": False},
            "live": {"reqs": [{"id": "a1", "dev": "Lautsprecher", "intent": "Wetter", "stage": "tool", "tool": "Websuche", "to": web, "done": False,
                               "age": 2.1, "steps": [{"k": "asr"}, {"k": "weiche"}, {"k": "llm"}, {"k": "tool", "to": web}]},
                              {"id": "a2", "dev": "Browser", "intent": "", "stage": "llm", "tool": "", "to": "qwen", "done": False, "age": 0.4,
                               "steps": [{"k": "weiche"}]},
                              {"id": "a3", "dev": "Uhr", "stage": "done", "done": True, "steps": []}],
                     "targets": targets, "svc": {"asr": {"st": "ok", "wait": 2}, "llm": {"st": "load"}}, "hints": [],
                     "guard": {"ok": 31, "bad": 1, "cut": 0}, "door": {"in": 3, "out": 1, "items": [{"t": T0 - 60}]},
                     "bus": {"rule": 2, "timer": 1}, "events": [{"t": T0 - 9, "area": "Anfrage", "text": "a0 fertig in 1,3 s"}],
                     "conns": [{"name": "Lautsprecher", "n": 2}, {"name": "Terminal", "n": 1}],
                     "sys": {"cpu": 20, "gpu": 50, "free": 80.5, "temp": 55, "hist": {"gpu": [1, 2], "cpu": [3], "avail": [80]}},
                     "notaus": {"level": 0}, "wartung": {"on": False}, "upd": {"run": False},
                     "aktiv": {"gesamt": 4, "profile": 3, "gaeste": 1}}}


class Panel(unittest.TestCase):
    def setUp(self):
        self.old = common.load_config()
        self.addCleanup(helpers.write_config, self.old)
        import guard
        guard._rate.clear()
        try:
            os.remove(schirm.KEY)
        except OSError:
            pass
        schirm._st.update(gesehen=0.0, fehler=0.0)

    def get(self, client=LOKAL, key=None, **headers):
        if key is not None:
            headers[schirm.HEADER] = key
        return TestClient(panel.app, client=client).get("/api/schirm/zustand", headers=headers)

    def test_off_by_default_and_admin_only(self):
        self.assertFalse(common.load_config()["chat"]["schirm"])
        k = schirm.schluessel(create=True)
        self.assertEqual(self.get(key=k).status_code, 404)
        import features
        self.assertIn("schirm", features.SPARK_ONLY)

    def test_only_this_machine_with_its_key(self):
        set_chat(schirm=True)
        k = schirm.schluessel(create=True)
        self.assertEqual(stat.S_IMODE(os.stat(schirm.KEY).st_mode), 0o600)
        self.assertEqual(self.get(HEIM, key=k).status_code, 404)                       # another computer
        self.assertEqual(self.get(key=k, **{"X-Forwarded-For": "89.1.2.3"}).status_code, 404)   # through a proxy
        self.assertEqual(self.get(key="falsch" * 8).status_code, 401)
        self.assertEqual(self.get().status_code, 401)
        r = self.get(key=k)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for key in ("an", "versatz", "schrift", "zeiten", "live", "rechner", "tag", "hinweise"):
            self.assertIn(key, d)
        self.assertTrue(schirm.sieht())

    def test_one_place_for_key_header_and_path(self):
        self.assertEqual((schirm.KEY, schirm.HEADER, schirm.PFAD), (sz.KEY, sz.HEADER, sz.PFAD))
        self.assertIn(sz.PFAD, {r.path for r in schirm.router.routes})

    def test_never_a_question_an_answer_or_a_name(self):
        set_chat(schirm=True)
        set_logs(live=True, live_monitor=False, live_names=False, trace=False)
        self.addCleanup(set_logs, live=False)
        reset()
        a = profile("Sbild")
        ask(a, 'TOOL memory_save {"fact": "Sbild mag ' + SECRET + '."}')
        d = self.get(key=schirm.schluessel(create=True)).json()
        self.assertTrue(d["live"]["reqs"])
        self.assertNotIn(SECRET, json.dumps(d))
        self.assertNotIn("Sbild", json.dumps(d))
        self.assertNotIn(SECRET, sz.bild(d, 200, 60).text())

    def test_settings_are_checked(self):
        self.assertIsNone(schirm.check({}))
        for bad in ({"schirm_an": 24}, {"schirm_aus": -1}, {"schirm_an": True}, {"schirm_schrift": "riesig"}):
            self.assertTrue(schirm.check(bad), bad)
        from tests.test_tracelog import ADMIN
        cfg = common.load_config()
        cfg["chat"]["schirm_an"] = 30
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)

    def test_times_switch_the_screen_dark(self):
        c = {"schirm_an": 7, "schirm_aus": 23}
        self.assertTrue(schirm.an_jetzt(c, T0))
        self.assertFalse(schirm.an_jetzt(c, NACHT))
        self.assertFalse(schirm.an_jetzt(c, MORGEN))
        self.assertTrue(schirm.an_jetzt({"schirm_an": 22, "schirm_aus": 7}, NACHT))     # over midnight
        self.assertTrue(schirm.an_jetzt({"schirm_an": 5, "schirm_aus": 5}, NACHT))      # same hour: always on
        self.assertFalse(schirm.zustand(NACHT, dict(c, schirm=True))["an"])

    def test_unit_follows_the_switch(self):
        calls = []
        lauf = {"st": "inactive"}
        with mock.patch("common.unit_exists", return_value=True), \
                mock.patch("common.run", side_effect=lambda cmd, **k: (0, lauf["st"])), \
                mock.patch.object(schirm, "_systemctl", side_effect=lambda *a: calls.append(a) or True), \
                mock.patch.object(schirm, "anmeldung", side_effect=lambda: calls.append("anmeldung") or True):
            self.assertEqual(schirm.abgleich(T0, {"schirm": False}), "")
            self.assertEqual(schirm.abgleich(T0, {"schirm": True}), "an")
            self.assertEqual(calls[-1], ("enable", "--now"))                              # no login prompt while it shows
            self.assertTrue(schirm.schluessel())
            lauf["st"] = "active"
            self.assertEqual(schirm.abgleich(T0, {"schirm": True}), "")
            self.assertEqual(schirm.abgleich(T0, {"schirm": False}), "aus")
            self.assertEqual(calls[-2:], [("disable", "--now"), "anmeldung"])             # switched off: the login prompt again
        with mock.patch("common.unit_exists", return_value=True), mock.patch("common.run", return_value=(0, "inactive")), \
                mock.patch.object(schirm, "_systemctl", return_value=False):
            self.assertEqual(schirm.abgleich(T0, {"schirm": True}), "fehler")
            self.assertEqual(schirm.abgleich(T0 + 10, {"schirm": True}), "")              # waits before trying again
        with mock.patch("common.unit_exists", return_value=False):
            schirm._st["fehler"] = 0.0
            self.assertEqual(schirm.abgleich(T0, {"schirm": True}), "")                   # not installed here

    def test_live_and_service_watch_know_it(self):
        self.assertIn("schirm", live.TARGETS)
        self.assertEqual(schirm.for_live({"schirm": False}), {"on": False})
        import dienstwacht
        self.assertIn("schirm", dienstwacht.SVC)
        with mock.patch("common.unit_exists", return_value=True):
            self.assertEqual(schirm.probes(), {})                       # switch off: nothing to watch
            set_chat(schirm=True)
            self.assertEqual(schirm.probes(), {"schirm": {"schirm": True}})


class Einheit(unittest.TestCase):
    """The unit as install.sh writes it (Pi 2026-10-16: an update with the screen on stopped with "Job for
    speech-spark-schirm.service canceled", and putting the previous version back failed the same way)."""

    def setUp(self):
        path = os.path.join(helpers.APP, "..", "install.sh")
        if not os.path.exists(path):
            raise unittest.SkipTest("install.sh is not part of this copy")
        with open(path) as f:
            self.sh = f.read()
        self.unit = self.sh.split("cat >/etc/systemd/system/speech-spark-schirm.service <<EOF\n", 1)[1].split("\nEOF\n", 1)[0]

    def test_a_restart_is_never_cancelled_by_the_login_prompt(self):
        # what the unit conflicts with may not be started from its own stop: that runs on a restart too and cancels it
        conflicts = re.findall(r"^Conflicts=(.+)$", self.unit, re.M)
        self.assertEqual(conflicts, ["getty@tty1.service"])
        for line in self.unit.splitlines():
            if line.startswith(("ExecStop", "ExecStopPost", "ExecReload", "ExecStartPre", "ExecStartPost")):
                self.assertNotIn("getty", line, line)
        self.assertIn("/usr/bin/systemctl start getty@tty1.service", self.sh.split("/etc/sudoers.d/speech-spark", 1)[0])

    def test_the_screen_never_stops_an_update(self):
        line = next(x for x in self.sh.splitlines() if "restart_front schirm" in x)
        self.assertIn("|| warn", line)


class Bild(unittest.TestCase):
    def test_fits_every_screen(self):
        for split in (True, False):
            for w, h in (sz.BASIS, (240, 67), (180, 50), (119, 35), (80, 24)):
                R = sz.bild(beispiel(split), w, h)
                self.assertEqual(len(R.z), h)
                self.assertTrue(all(len(row) == w for row in R.z))
        self.assertIn("wartet auf das Panel", sz.bild(None, 160, 45).text())

    def test_shows_both_computers_stages_and_requests(self):
        t = sz.bild(beispiel(), 240, 67).text()
        for word in ("tars · Modell-Rechner", "pi · Panel-Rechner", "Hören", "Weiche", "Sprachmodell", "Werkzeuge", "Sprechen",
                     "Lautsprecher", "Browser", "Braucht dich", "Pi ist heiß", "LETZTE 20 MINUTEN", "INTERNET", "▶ Websuche"):
            self.assertIn(word, t)
        self.assertNotIn("Uhr ·", t.split("\n")[3])     # a finished request is no device line
        one = sz.bild(beispiel(split=False), 240, 67).text()
        self.assertIn("Panel und Modelle", one)

    def test_a_way_never_runs_across_a_box(self):
        # Pi 2026-10-16 "die verbindungen sind manchmal über den kästen": a way that skips stages (Hören straight to
        # Werkzeuge, or Weiche to Sprechen) went through the boxes in between
        reqs = [{"id": "s1", "stage": "tool", "steps": [{"k": "asr"}, {"k": "tool"}]},
                {"id": "s2", "stage": "tts", "steps": [{"k": "weiche"}, {"k": "tts"}]},
                {"id": "s3", "stage": "tts", "steps": [{"k": "asr"}, {"k": "llm"}, {"k": "tts"}]}]
        for lanes, stufen in (([("modell", 30, 50, 5, 38), ("panel", 80, 50, 5, 38)], sz.STUFEN),
                              ([("spark", 30, 100, 5, 38)], tuple((k, n, t, "spark") for k, n, t, _ in sz.STUFEN))):
            R = sz.Raster(200, 45)
            pos, hoch = sz.stufen_zeichnen(R, {"live": {"reqs": reqs}}, lanes, reqs, stufen)
            for key, (x, y, w) in pos.items():
                for yy in range(y + 1, y + hoch - 1):
                    inner = "".join(c for c, _ in R.z[yy][x + 1:x + w - 1])
                    self.assertFalse(set(inner) & set("│┃─━┌┐└┘"), f"{key}: {inner!r}")

    def test_a_finished_answer_stays_a_moment(self):
        # "die letzte meldung verschwindet ziemlich schnell": the Live picture keeps the last answer (last) and fades
        # the others (left seconds); the screen shows them too, marked as done, and counts only the running ones
        d = beispiel()
        d["live"]["reqs"] = [{"id": "f1", "dev": "Küche", "intent": "Wetter", "stage": "done", "done": True, "last": True,
                              "age": 2.4, "steps": [{"k": "asr"}, {"k": "llm"}, {"k": "tts"}]},
                             {"id": "f2", "dev": "Bad", "stage": "done", "done": True, "left": 0, "age": 1, "steps": []}]
        self.assertEqual([r["id"] for r in sz.gezeigt(d)], ["f1"])
        self.assertEqual(sz.laufende(d), [])
        t = sz.bild(d, 240, 67).text()
        self.assertIn("Küche", t)
        self.assertIn("fertig in 2,4 s", t)
        self.assertNotIn("Bad", t.split("GERÄTE", 1)[1].split("Verbunden", 1)[0])

    def test_the_tool_box_names_each_tool(self):
        # "unterhalb von werkzeugen nicht ersichtlich was für ein werkzeug benutzt wird": every shown request names
        # its tool in its colour, running (▶), done (✓) or failed (✗), and keeps it until the request fades
        d = beispiel()
        d["live"]["reqs"] = [{"id": "w1", "dev": "Küche", "intent": "Wetter", "stage": "tool", "tool": "Websuche", "done": False,
                              "age": 1, "steps": [{"k": "llm"}, {"k": "tool", "n": "Websuche", "ok": True}]},
                             {"id": "w2", "dev": "Bad", "intent": "Licht", "stage": "done", "done": True, "last": True, "age": 2,
                              "steps": [{"k": "tool", "n": "Kalender", "ok": True}, {"k": "tool", "n": "Licht schalten", "ok": False}]},
                             {"id": "w3", "dev": "Uhr", "stage": "llm", "done": False, "age": 1, "steps": [{"k": "llm"}]}]
        lauf = sz.gezeigt(d)
        farbe = {r["id"]: sz.FARBEN[j] for j, r in enumerate(lauf)}    # the colour of its request's way
        self.assertEqual(sz.werkzeug_teile(lauf), [("▶ Websuche", farbe["w1"]), (" · ", "m"), ("✗ Licht schalten +1", farbe["w2"])])
        groß = sz.bild(d, 240, 67).text()
        self.assertIn("▶ Websuche · ✗ Licht schalten +1", groß)
        klein = sz.bild(d, 160, 45).text()           # Full HD: the first name whole, the rest counted
        self.assertRegex(klein, r"Werkzeuge ▶ Websuche( \+1| · ✗)")
        for r in d["live"]["reqs"]:
            r["steps"] = [s for s in r["steps"] if s["k"] != "tool"]
            r["stage"] = "llm" if r["stage"] == "tool" else r["stage"]
        self.assertEqual(sz.werkzeug_teile(sz.gezeigt(d)), [])
        self.assertIn("Suchen · Schalten · Lesen", sz.bild(d, 240, 67).text())

    def test_the_tool_box_names_the_last_tools_when_quiet(self):
        # Dominik 2026-10-17 (photo): with nothing running the box only said "Suchen · Schalten · Lesen";
        # now it names the last tools from the Live returns, newest first, each once, with ✓/✗ and the time
        d = beispiel()
        d["live"]["reqs"] = []
        t0 = time.mktime((2026, 10, 17, 9, 12, 0, 0, 0, -1))
        d["live"]["rets"] = [{"t": t0, "tool": "Websuche", "ok": True}, {"t": t0 - 300, "tool": "Kalender", "ok": False},
                             {"t": t0 - 400, "tool": "Websuche", "ok": True}]
        self.assertEqual(sz.zuletzt_teile(d["live"]), [("✓ Websuche 09:12", "w"), (" · ", "m"), ("✗ Kalender 09:07", "w")])
        self.assertEqual(sz.zuletzt_teile(d["live"], False)[0], ("✓ Websuche", "w"))
        groß = sz.bild(d, 240, 67).text()
        self.assertIn("zuletzt ✓ Websuche 09:12", groß)
        self.assertNotIn("Suchen · Schalten · Lesen", groß)
        self.assertRegex(sz.bild(d, 160, 45).text(), r"Werkzeuge ✓ Websuche")
        d["live"]["rets"] = []
        self.assertIn("Suchen · Schalten · Lesen", sz.bild(d, 240, 67).text())

    def test_boxes_have_a_surface_and_round_corners(self):
        # Dominik 2026-10-17 picked draft 1: every box gets a coloured surface (the console's dark colours 1-7) and
        # round corners; the frames of the computers stay dark, the palette is set on the Linux console only
        R = sz.Raster(30, 12)
        R.box(0, 0, 30, 12, "b", "tars", "b", flaeche=False)
        R.box(2, 2, 10, 4, "y", voll=True)
        self.assertEqual((R.z[2][2][0], R.z[2][11][0], R.z[5][2][0], R.z[5][11][0]), ("╭", "╮", "╰", "╯"))
        self.assertEqual(R.bg[3][5], sz.FLAECHE["y"])
        self.assertEqual(R.bg[2][5], 0)                   # the frame line itself has no surface
        self.assertEqual(R.bg[8][20], 0)                  # inside the computer's frame
        self.assertTrue(all(0 < v < 8 for v in sz.FLAECHE.values()))
        self.assertEqual(sz.farbtafel().count("\033]P"), 16)
        self.assertEqual(sz.farbtafel(False), "\033]R")
        self.assertEqual(sz.ersetzen("╭─╮╰╯", set("┌─┐└┘")), "┌─┐└┘")   # a font without round corners
        t = sz.bild(beispiel(), 240, 67)
        self.assertTrue(any(v for row in t.bg for v in row))

    def test_every_live_service_has_its_line(self):
        """Dominik 2026-10-16: the screen grows with every change. Every box of the Live picture is drawn or counted."""
        d = beispiel()
        t = sz.bild(d, 240, 67).text()
        heim = [x for x in d["live"]["targets"] if x["zone"] != "net"]
        drawn = [x for x in heim if sz.kurz(x["name"], 240 * 23 // 100 * 3 // 5) in t]
        rest = len(heim) - len(drawn)
        if rest:
            self.assertIn(f"+ {rest} weitere", t)
        self.assertGreater(len(drawn), 10)
        self.assertEqual(set(sz.SCHRITT), {"asr", "weiche", "llm", "tool", "tts", "ack"})

    def test_quiet_targets_fold_like_the_live_picture(self):
        """Dominik 2026-10-16: only what is in use gets a line; the quiet ones fold into "+ N bereit" / "+ N ruhig"."""
        d = beispiel()
        busy = {"qwen", "kiwix", "bild"}
        for x in d["live"]["targets"]:
            x["quiet"] = x["id"] not in busy
        t = sz.bild(d, 240, 67).text()
        heim = [x for x in d["live"]["targets"] if x["zone"] != "net"]
        netz = [x for x in d["live"]["targets"] if x["zone"] == "net"]
        self.assertIn(f"+ {sum(x['quiet'] for x in heim)} bereit", t)
        self.assertIn(f"+ {sum(x['quiet'] for x in netz)} ruhig", t)
        self.assertNotIn("+ 1 weitere", t)
        self.assertNotIn("weitere", t)

    def test_missing_glyphs_are_replaced(self):
        have = set(" abc|+-_#.>v")
        s = sz.ersetzen("a▁█✓●┌─┐", have)
        self.assertEqual(len(s), 8)
        self.assertTrue(all(ch in have or ord(ch) < 128 for ch in s))
        self.assertEqual(sz.ersetzen("✓", None), "✓")
        self.assertEqual(sz.ersetzen("✓", set("√")), "√")

    def test_font_follows_the_resolution(self):
        da = lambda p: True   # noqa: E731
        self.assertTrue(sz.schrift((1920, 1080), da=da).endswith("TerminusBold24x12.psf.gz"))
        self.assertTrue(sz.schrift((3840, 2160), da=da).endswith("TerminusBold32x16.psf.gz"))
        self.assertTrue(sz.schrift((1920, 1080), "kleiner", da).endswith("TerminusBold22x11.psf.gz"))
        self.assertTrue(sz.schrift((1920, 1080), "groesser", da).endswith("TerminusBold28x14.psf.gz"))
        self.assertTrue(sz.schrift((1280, 720), da=da).endswith("TerminusBold16.psf.gz"))
        self.assertIsNone(sz.schrift((1920, 1080), da=lambda p: False))
        self.assertIsNone(sz.schrift(None, da=da))

    def test_active_people_in_the_header(self):
        """Aktiv 10 min (aktiv.py, Dominik 2026-10-17): the same number as on the OLED, in the second header row."""
        text = sz.bild(beispiel(), 200, 60, T0).text().splitlines()[1]
        self.assertIn("Aktiv 10 min 4 (3 Profile · 1 Gäste)", text)
        d = beispiel()
        del d["live"]["aktiv"]
        self.assertIn("Aktiv 10 min – (– Profile · – Gäste)", sz.bild(d, 200, 60, T0).text().splitlines()[1])

    def test_update_with_its_share(self):
        """Dominik 2026-10-18: a running update shows its share and step (live._upd, one bar for both computers)."""
        d = beispiel()
        d["live"]["upd"] = {"run": True, "pct": 15, "step": "TARS: TARS aktualisiert"}
        self.assertIn("Update 15 % · TARS", sz.bild(d, 200, 60, T0).text())

    def test_the_biggest_service_in_each_frame(self):
        """„Wer rechnet gerade“ (rechnerblick.spitze, Dominik 2026-10-18): the service that takes the most CPU leads the
        frame's last line, the panel with its part; idle says „▶ Leerlauf“ in the same field (Spiegel-Karten 2026-10-20)."""
        d = beispiel()
        d["rechner"]["liste"][0]["spitze"] = {"id": "llm", "name": "Sprachmodell", "en": "Language model", "pct": 29.0}
        d["rechner"]["liste"][1]["spitze"] = {"id": "panel/bedeutungssuche", "name": "Panel · Bedeutungssuche", "en": "", "pct": 31.4}
        t = sz.bild(d, 240, 67).text()
        self.assertIn("▶ Sprachmodell 29 %", t)
        self.assertIn("▶ Panel · Bedeutungssuche 31 %", t)
        self.assertNotIn("▶ Sprachmodell", sz.bild(beispiel(), 240, 67).text())
        self.assertIn("▶ Leerlauf", sz.bild(beispiel(), 240, 67).text())

    def test_both_frames_have_their_values_in_the_same_places(self):
        """Spiegel-Karten (Dominik 2026-10-20): in both frames GPU, RAM, the biggest service and „Platte“ start at the
        same column of their frame, whatever the biggest service is called; the Pi's GPU is „–“."""
        d = beispiel()
        d["rechner"]["liste"][0]["spitze"] = {"id": "llm", "name": "Sprachmodell", "en": "", "pct": 29.0}
        zeilen = sz.bild(d, 240, 67).text().splitlines()
        # the frames start where their CPU lines start: the same distance to GPU, and „Platte“ after the same field
        z1 = next(z for z in zeilen if z.count("CPU ") == 2)
        c = [m for m in range(len(z1)) if z1.startswith("CPU ", m)]
        g = [m for m in range(len(z1)) if z1.startswith("GPU ", m)]
        self.assertEqual(g[0] - c[0], g[1] - c[1])
        self.assertIn("GPU – keine", z1)
        z3 = next(z for z in zeilen if "▶ Sprachmodell" in z and "▶ Leerlauf" in z)
        p = [m for m in range(len(z3)) if z3.startswith("Platte ", m)]
        s0 = [z3.index("▶ Sprachmodell"), z3.index("▶ Leerlauf")]
        self.assertEqual(p[0] - s0[0], p[1] - s0[1])

    def test_curve_and_numbers(self):
        self.assertEqual(sz.linie([0, 100], 4, 0, 100), "▁▁██")
        self.assertEqual(sz.linie([], 3), "   ")
        self.assertEqual(sz.linie([None, 50], 2, 0, 100), " ▄")
        self.assertEqual(sz.zahl(1.25, 1), "1,2")
        self.assertEqual(sz.zahl(None), "–")

    def test_probe_from_a_saved_state(self):
        import io
        import sys
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(beispiel()))), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(sz.main(["--probe", "160", "45"]), 0)
        self.assertIn("Steuerzentrale", out.getvalue())


if __name__ == "__main__":
    unittest.main()
