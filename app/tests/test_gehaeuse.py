"""Gehäuse (plan Raspberry-Pi split B7): the Pironman 5 around a Raspberry Pi 5, driven through the Pi's device files.
I2C and SPI are played by a fake (no hardware here): the OLED gets its start commands and 1024 bytes per page, the LEDs
the colour of the status, nothing on the display names a profile, night and "nur bei Problemen" darken it, and the root
part writes config.txt only from two checked numbers. Nothing depends on the time of day: every time is given."""
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests import helpers

helpers.start()
import common  # noqa: E402
import gehaeuse  # noqa: E402
import steuer  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = time.mktime((2026, 10, 15, 14, 0, 0, 0, 0, -1))      # 14:00 local time
NIGHT = time.mktime((2026, 10, 15, 23, 30, 0, 0, 0, -1))


class FakeHw(gehaeuse.Hw):
    def __init__(self, oled=0x3C, spi=True):
        self.oled, self.spi, self.i2c, self.leds, self.files = oled, spi, [], [], {}

    def exists(self, path):
        return {gehaeuse.I2C_DEV: True, gehaeuse.SPI_DEV: self.spi}.get(path, path in self.files)

    def i2c_write(self, addr, data):
        if addr != self.oled:
            raise OSError(121, "Remote I/O error")
        self.i2c.append(bytes(data))

    def spi_write(self, data):
        self.leds.append(bytes(data))

    def read(self, path):
        if path in self.files:
            return self.files[path]
        raise OSError(2, "missing")


class Base(unittest.TestCase):
    def setUp(self):
        self.old = common.load_config()
        self.addCleanup(helpers.write_config, self.old)
        self.hw = FakeHw()
        p = mock.patch.object(gehaeuse, "hw", self.hw)
        p.start()
        self.addCleanup(p.stop)
        gehaeuse._st.update(oled="aus", led="aus", addr=None, seite="", farbe="aus", next=0.0, i=0, led_t=0.0, fail={}, bild=None,
                            roh=b"", gleich=0.0)
        p = mock.patch.object(gehaeuse, "_hinweise", return_value=(0, 0))
        p.start()
        self.addCleanup(p.stop)

    def on(self, **kw):
        c = json.loads(json.dumps(self.old))
        c["chat"].update({"gehaeuse": True, "gehaeuse_art": "pironman5", **kw})
        helpers.write_config(c)
        return c["chat"]

    def tick(self, now=T0, c=None):
        with redirect_stdout(io.StringIO()) as out:
            gehaeuse.tick(now, c)
        return out.getvalue()


class Treiber(Base):
    def test_page_bytes(self):
        from PIL import Image
        img = Image.new("1", (gehaeuse.W, gehaeuse.H), 0)
        img.putpixel((0, 0), 1)
        img.putpixel((5, 9), 1)
        data = gehaeuse.packen(img)
        self.assertEqual(len(data), 1024)
        self.assertEqual(data[0], 0b1)
        self.assertEqual(data[128 + 5], 0b10)
        self.assertEqual(sum(1 for b in data if b), 2)

    def test_led_bytes(self):
        data = gehaeuse.led_bytes((255, 0, 0), n=1)
        bits = data[8:8 + 24]
        self.assertEqual(bits[:8], bytes([0b11000000]) * 8, "green first: 0")
        self.assertEqual(bits[8:16], bytes([0b11110000]) * 8, "then red: 255")
        self.assertEqual(len(gehaeuse.led_bytes((1, 2, 3))), 8 + 24 * gehaeuse.LED_N + 240)
        self.assertEqual(gehaeuse.led_farbe("gruen", 50), (0, 128, 0))

    def test_the_display_is_found_at_its_address(self):
        self.assertEqual(gehaeuse.finden(), 0x3C)
        self.hw.oled = 0x3D
        self.assertEqual(gehaeuse.finden(), 0x3D)
        self.hw.oled = None
        self.assertIsNone(gehaeuse.finden())


class Anzeige(Base):
    def test_off_until_the_admin_switches_it_on(self):
        self.assertEqual(self.tick(), "")
        self.assertEqual(self.hw.i2c, [])
        self.assertEqual(self.hw.leds, [])

    def test_a_page_and_the_colour(self):
        c = self.on()
        out = self.tick(T0, c)
        self.assertIn("gehaeuse: oled an 0x3c", out)
        self.assertIn("gehaeuse: led an", out)
        self.assertEqual(self.hw.i2c[0], bytes([0x00, 0xE3]), "found by a NOP")
        self.assertEqual(self.hw.i2c[1], bytes((0x00,) + gehaeuse.OLED_INIT))
        self.assertEqual(self.hw.i2c[2], bytes([0x00, 0xAF]), "display on")
        data = b"".join(x[1:] for x in self.hw.i2c if x[0] == 0x40)
        self.assertEqual(len(data), 1024)
        self.assertEqual(gehaeuse._st["seite"], "spark")
        self.assertEqual(self.hw.leds[-1], gehaeuse.led_bytes(gehaeuse.led_farbe("gruen", 30)))
        # the next page only after its time
        n = len(self.hw.i2c)
        self.tick(T0 + 2, c)
        self.assertEqual(len(self.hw.i2c), n)
        self.tick(T0 + 7, c)
        self.assertEqual(gehaeuse._st["seite"], "dienste")

    def test_night_and_only_problems(self):
        c = self.on(gehaeuse_nacht="aus")
        self.tick(NIGHT, c)
        self.assertEqual(self.hw.i2c[-1], bytes([0x00, 0xAE]), "display off at night")
        self.assertEqual(self.hw.leds[-1], gehaeuse.led_bytes((0, 0, 0)))
        gehaeuse._st.update(oled="aus", addr=None, seite="", led_t=0.0)
        c = self.on(gehaeuse_anzeige="probleme")
        self.tick(T0, c)
        self.assertEqual(self.hw.i2c[-1], bytes([0x00, 0xAE]), "all green: dark")
        with mock.patch.object(gehaeuse, "_hinweise", return_value=(1, 0)):
            self.tick(T0 + 10, c)
        self.assertEqual(gehaeuse._st["seite"], "dienste", "a service down brings its page first")
        self.assertEqual(self.hw.leds[-1], gehaeuse.led_bytes(gehaeuse.led_farbe("rot", 30)))

    def test_model_computer_gone_comes_first(self):
        c = self.on()
        with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "weg", return_value=True), \
                mock.patch.object(steuer, "cached", return_value=None):
            self.assertEqual(gehaeuse.seiten(c, T0)[0], "dgx")
            self.assertEqual(gehaeuse.lage(T0), ("rot", "DGX weg"))
        with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "weg", return_value=False), \
                mock.patch.object(steuer, "cached", return_value={"pause": {"on": True, "until": T0 + 600}}):
            self.assertEqual(gehaeuse.lage(T0), ("gelb", "DGX in Pause"))
            self.assertEqual(gehaeuse.zeilen("dgx", T0)[1], "noch 10 min")
        self.assertNotIn("dgx", gehaeuse.seiten(c, T0), "only while it is gone or paused")
        self.assertNotIn("pi", gehaeuse.seiten(dict(c, gehaeuse_seiten_aus=["pi"]), T0))

    def test_no_profile_on_the_display(self):
        import profiles
        profiles.add_user("Geheimname", "1234")
        for key, _, _ in gehaeuse.SEITEN:
            text = " ".join(gehaeuse.zeilen(key, T0))
            self.assertNotIn("Geheimname", text)

    def test_a_missing_display_is_said_once_and_tried_again_later(self):
        c = self.on()
        self.hw.oled = None
        out = self.tick(T0, c) + self.tick(T0 + 10, c)
        self.assertEqual(out.count("gehaeuse: oled fehlt"), 1)
        self.hw.oled = 0x3C
        self.assertNotIn("oled an", self.tick(T0 + 20, c))
        self.assertIn("gehaeuse: oled an", self.tick(T0 + 10 + gehaeuse.RETRY, c))

    def test_settings_are_checked(self):
        self.assertIsNone(gehaeuse.check({}))
        self.assertIn("gehaeuse_art", gehaeuse.check({"gehaeuse_art": "fremd"}))
        self.assertIn("gehaeuse_hell", gehaeuse.check({"gehaeuse_hell": 0}))
        self.assertIn("gehaeuse_drehung", gehaeuse.check({"gehaeuse_drehung": 90}))
        self.assertIn("gehaeuse_anzeige", gehaeuse.check({"gehaeuse_anzeige": "nie"}))
        self.assertIn("unter", gehaeuse.check({"gehaeuse_luefter_an": 50, "gehaeuse_luefter_aus": 50}))
        self.assertIn("mindestens eine", gehaeuse.check({"gehaeuse_seiten_aus": [k for k, _, _ in gehaeuse.SEITEN]}))


    def test_number_fields_are_sent_as_numbers(self):
        """V01.0.648: the select of the rotation had a bare data-num (an empty dataset value counts as false in
        admin.js), so it sent "0" and saving Funktionen was refused (the list of pages likewise with a bare data-list):
        every number setting of the case has type=number or data-num="1", the list data-list="1"."""
        import re
        with open(os.path.join(APP, "config.default.json"), encoding="utf-8") as f:
            chat = json.load(f)["chat"]
        with open(os.path.join(APP, "panel", "static", "index.html"), encoding="utf-8") as f:
            html = f.read()
        nums = [k for k, v in chat.items() if k.startswith("gehaeuse_") and isinstance(v, int) and not isinstance(v, bool)]
        self.assertIn("gehaeuse_drehung", nums)
        for k in nums:
            m = re.search(r'<(?:input|select)[^>]*id="chat\.%s"[^>]*>' % k, html)
            if m:
                self.assertTrue('type="number"' in m.group(0) or 'data-num="1"' in m.group(0), m.group(0))
        m = re.search(r'<input[^>]*id="chat\.gehaeuse_seiten_aus"[^>]*>', html)   # a list goes as a list (data-list="1")
        self.assertIn('data-list="1"', m.group(0))


class Seiten(Base):
    """B7b: pages 6 to 11, the admin's order, the move and the dimming against burn-in, the preview in the panel."""

    def test_every_page_fits_the_display(self):
        for key, _, _ in gehaeuse.SEITEN:
            lines = gehaeuse.zeilen(key, T0)
            self.assertTrue(1 <= len(lines) <= 5, key)
            for line in lines:
                self.assertLessEqual(len(line), 21, (key, line))
        self.assertEqual(len(gehaeuse.SEITEN), 14)

    def test_active_people_as_one_big_number(self):
        """Dominik 2026-10-17 "1b 2a 3a": page "Aktiv 10 min" with the people of the last 10 minutes as one big number,
        profiles and guests beside it; in the normal rotation, switched and moved like the others; never a name."""
        import aktiv
        aktiv._seen.clear()
        self.addCleanup(aktiv._seen.clear)
        aktiv.sah(T0 - 60, "u1", "profile", "web")
        aktiv.sah(T0 - 30, None, "guest", "speaker", ort="10.0.0.9")
        self.assertEqual(gehaeuse.zeilen("aktiv", T0), ["Aktiv 10 min", "2", "Profile 1", "Gaeste 1"])
        c = self.on()
        self.assertIn("aktiv", gehaeuse.seiten(c, T0))
        self.assertNotIn("aktiv", gehaeuse.seiten(dict(c, gehaeuse_seiten_aus=["aktiv"]), T0))
        gross = gehaeuse.bild(gehaeuse.zeilen("aktiv", T0), key="aktiv")
        klein = gehaeuse.bild(["Aktiv 10 min", "2"])
        hoch = [y for y in range(gehaeuse.H) if any(gross.getpixel((x, y)) for x in range(70))]
        self.assertGreater(max(hoch) - 14, 30, "the number is big: more than 30 points high")
        self.assertNotEqual(gross.tobytes(), klein.tobytes())
        for n in ("7", "88", "123", "9999"):     # every count fits left of the divider
            img = gehaeuse.bild(["Aktiv 10 min", n, "Profile 1", "Gaeste 0"], key="aktiv")
            self.assertTrue(any(img.getpixel((x, 40)) for x in range(70)), n)
            self.assertFalse(any(img.getpixel((x, y)) for x in range(70, 72) for y in range(14, 64)), n)

    def test_cpu_and_ram_as_two_big_numbers(self):
        """Dominik 2026-10-17 "1a, Namen Pi und TARS": pages "Pi" and "TARS" with CPU left and RAM right in %, as two
        big numbers; "TARS" only while the models run on another computer, "-" while it is gone."""
        import rechnerblick
        with mock.patch.object(gehaeuse, "_pi", return_value={"cpu": 12.4, "ram": 9.0, "temp": None, "platte": None, "luefter": None}):
            self.assertEqual(gehaeuse.zeilen("lastpi", T0), ["Pi", "12", "9"])
        with mock.patch.dict(rechnerblick._letzt, {"modell": {"cpu": 64.2, "ram_total": 120.0, "ram_frei": 30.0}}), \
                mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "weg", return_value=False):
            self.assertEqual(gehaeuse.zeilen("lasttars", T0), ["TARS", "64", "75"])
            self.assertIn("lasttars", gehaeuse.seiten(self.on(), T0))
        with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "weg", return_value=True):
            self.assertEqual(gehaeuse.zeilen("lasttars", T0), ["TARS weg", "-", "-"])
        with mock.patch.object(steuer, "remote", return_value=False):
            self.assertNotIn("lasttars", gehaeuse.seiten(self.on(), T0), "one Spark: no second computer")
        for cpu, ram in (("7", "100"), ("100", "100"), ("?", "?")):
            img = gehaeuse.bild(["TARS", cpu, ram], key="lasttars")
            links = [y for y in range(14, 50) if any(img.getpixel((x, y)) for x in range(62))]
            rechts = [y for y in range(14, 50) if any(img.getpixel((x, y)) for x in range(65, 128))]
            self.assertGreaterEqual(max(links) - min(links), 18, (cpu, "big: more than twice the small font"))
            self.assertGreaterEqual(max(rechts) - min(rechts), 18, (ram, "big: more than twice the small font"))
            self.assertFalse(any(img.getpixel((x, y)) for x in (62, 64) for y in range(14, 64)), "numbers stay off the divider")

    def test_the_admins_order(self):
        c = self.on(gehaeuse_reihenfolge=["version", "pi"])
        self.assertEqual(gehaeuse.seiten(c, T0)[:3], ["version", "pi", "spark"])
        self.assertIn("gehaeuse_reihenfolge", gehaeuse.check({"gehaeuse_reihenfolge": ["pi", "pi"]}))
        self.assertIn("gehaeuse_reihenfolge", gehaeuse.check({"gehaeuse_reihenfolge": ["fremd"]}))
        self.assertIsNone(gehaeuse.check({"gehaeuse_reihenfolge": ["netz", "spark"]}))

    def test_power_flags_of_the_pi(self):
        self.hw.files[gehaeuse.THROTTLED] = "0x50005\n"
        self.assertEqual(gehaeuse._strom(), ("zu niedrig", "jetzt"))
        self.hw.files[gehaeuse.THROTTLED] = "0x50000\n"
        self.assertEqual(gehaeuse._strom(), ("war niedrig", "war an"))
        self.hw.files[gehaeuse.THROTTLED] = "0x0\n"
        self.assertEqual(gehaeuse._strom(), ("ok", "nein"))
        del self.hw.files[gehaeuse.THROTTLED]
        self.assertEqual(gehaeuse.zeilen("strom", T0)[1], "Spannung ?")

    def test_model_computer_in_detail_and_versions(self):
        st = {"gpu": {"temp": 61.0}, "mem_avail_gib": 37.6, "version": "V01.0.001",
              "modellwahl": {"llm": {"enabled": True, "modell": "RedHatAI/qwen38-27b-nvfp4"}}}
        with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "cached", return_value=st):
            self.assertEqual(gehaeuse.zeilen("dgxdetail", T0), ["DGX Detail", "GPU 61 C", "Frei 38 GiB", "LLM qwen38-27b-nvfp4"])
            self.assertEqual(gehaeuse.zeilen("version", T0)[2:], ["DGX V01.0.001", "abweichend"])

    def test_burn_in(self):
        self.assertNotEqual(gehaeuse.versatz(T0), gehaeuse.versatz(T0 + gehaeuse.VERSATZ_S))
        a, b = gehaeuse.bild(["X"]), gehaeuse.bild(["X"], versatz=(1, 1))
        self.assertNotEqual(gehaeuse.packen(a), gehaeuse.packen(b), "the picture moves")
        c = self.on(gehaeuse_seiten_aus=[k for k, _, _ in gehaeuse.SEITEN if k != "netz"], gehaeuse_hell=80)
        with mock.patch.object(gehaeuse, "zeilen", return_value=["Netz", "gleich"]):
            self.tick(T0, c)
            hell = [x for x in self.hw.i2c if x[:2] == bytes([0x00, 0x81])]
            self.assertEqual(hell[-1][2], round(80 * 255 / 100))
            self.tick(T0 + gehaeuse.GLEICH_S + 7, c)
            hell = [x for x in self.hw.i2c if x[:2] == bytes([0x00, 0x81])]
            self.assertEqual(hell[-1][2], round(gehaeuse.GLEICH_HELL * 255 / 100), "the same picture for 10 min: darker")

    def test_preview_for_the_admin_only(self):
        import base64
        from fastapi.testclient import TestClient
        import panel
        c = self.on(gehaeuse_seiten_aus=["haus"])
        v = gehaeuse.vorschau(c, T0)
        self.assertEqual([p["id"] for p in v["seiten"]], gehaeuse.reihenfolge(c))
        self.assertFalse(next(p for p in v["seiten"] if p["id"] == "haus")["an"])
        self.assertEqual(len(base64.b64decode(v["seiten"][0]["bits"])), gehaeuse.W * gehaeuse.H // 8)
        self.assertEqual(v["jetzt"], "")
        self.tick(T0, c)
        v = gehaeuse.vorschau(c, T0)
        self.assertEqual(v["jetzt"], "spark")
        self.assertEqual(len(base64.b64decode(v["jetzt_bits"])), 1024)
        self.assertIn(TestClient(panel.app).get("/api/admin/gehaeuse/vorschau").status_code, (401, 403))
        admin = TestClient(panel.app)
        admin.post("/api/login", json={"password": "secret-admin"})
        r = admin.get("/api/admin/gehaeuse/vorschau")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["seiten"]), len(gehaeuse.SEITEN))

class Wunsch(Base):
    def test_only_a_fresh_wish_with_the_switch_on(self):
        self.on(gehaeuse_luefter_an=60, gehaeuse_luefter_aus=50)
        gehaeuse.wunsch("ein", now=T0)
        self.assertEqual(gehaeuse.wunsch_nehmen(T0 + 5), "ein 60 50")
        self.assertIsNone(gehaeuse.wunsch_nehmen(T0 + 6), "taken once")
        gehaeuse.wunsch("aus", now=T0)
        self.assertIsNone(gehaeuse.wunsch_nehmen(T0 + gehaeuse.WUNSCH_S + 1), "too old")
        gehaeuse.wunsch("neustart", now=T0)
        self.assertEqual(gehaeuse.wunsch_nehmen(T0 + 1), "neustart")
        c = self.on(gehaeuse_art="keins")
        gehaeuse.wunsch("ein", now=T0)
        self.assertIsNone(gehaeuse.wunsch_nehmen(T0 + 1), "no case chosen")
        with self.assertRaises(ValueError):
            gehaeuse.wunsch("reboot")
        self.assertTrue(c)


def _bash(src, script, env):
    return subprocess.run(["bash", "-c", src + "\n" + script], env=env, capture_output=True, text=True, timeout=30)


class Root(unittest.TestCase):
    """The root part of speech-spark.sh (cmd_gehaeuse and its helpers), with a config.txt in a temporary folder."""
    def setUp(self):
        path = os.path.join(APP, "speech-spark.sh")
        if not os.path.exists(path):
            self.skipTest("speech-spark.sh missing")
        with open(path) as f:
            sh = f.read()
        self.src = sh[sh.index("GEHAEUSE_TXT="):sh.index("cmd_gehaeuse() {")]
        self.dir = tempfile.mkdtemp(dir=helpers.TMP)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.txt = os.path.join(self.dir, "config.txt")
        with open(self.txt, "w") as f:
            f.write("# Pi\ndtparam=audio=on\n\n[pi5]\narm_boost=1\n")
        self.env = dict(os.environ, SPEECH_SPARK_CONFIG_TXT=self.txt,
                        SPEECH_SPARK_GEHAEUSE_NEUSTART=os.path.join(self.dir, "neustart"),
                        SPEECH_SPARK_MODULES_D=os.path.join(self.dir, "modules"))
        # no root here: the groups, the module and the restart are only written down
        self.stubs = ("panel_user() { echo speech; }\ngetent() { [ \"$2\" != gpio ]; }\n"
                      "usermod() { echo \"usermod $*\"; }\nmodprobe() { :; }\nsystemctl() { echo \"systemctl $*\"; }\n")

    def run_sh(self, script):
        return _bash(self.src + self.stubs, script, self.env)

    def text(self):
        with open(self.txt) as f:
            return f.read()

    def test_the_block_goes_in_and_out(self):
        r = self.run_sh("gehaeuse_ein 55 48")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = self.text()
        self.assertTrue(t.startswith("# Pi\ndtparam=audio=on\n\n[pi5]\narm_boost=1\n"), t)
        self.assertIn("# speech-spark gehaeuse begin\n[all]\ndtparam=i2c_arm=on\ndtparam=spi=on\n"
                      "dtoverlay=gpio-fan,gpiopin=6,temp=55000,hyst=7000\n# speech-spark gehaeuse end\n", t)
        self.assertIn("usermod -aG i2c speech", r.stdout)
        self.assertNotIn("gpio speech", r.stdout, "a group the system does not have is left out")
        self.assertTrue(os.path.exists(os.path.join(self.dir, "neustart")))
        with open(os.path.join(self.dir, "modules", "speech-spark-gehaeuse.conf")) as f:
            self.assertEqual(f.read(), "i2c-dev\n")
        # the same again changes nothing, other thresholds replace the block
        os.remove(os.path.join(self.dir, "neustart"))
        self.assertIn("gehaeuse: config.txt unveraendert", self.run_sh("gehaeuse_ein 55 48").stdout)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "neustart")))
        self.run_sh("gehaeuse_ein 60 50")
        self.assertEqual(self.text().count("gehaeuse begin"), 1)
        self.assertIn("temp=60000,hyst=10000", self.text())
        r = self.run_sh("gehaeuse_aus")
        self.assertIn("gehaeuse: entfernt", r.stdout)
        self.assertEqual(self.text(), "# Pi\ndtparam=audio=on\n\n[pi5]\narm_boost=1\n")

    def test_only_checked_numbers(self):
        for bad in ("55 55", "90 48", "5x 48", "'55;reboot' 48", "55 29"):
            r = self.run_sh(f"gehaeuse_ein {bad}")
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn("gehaeuse: abgelehnt grenzen", r.stdout)
        self.assertNotIn("gehaeuse", self.text())

    def test_restart_only_when_needed(self):
        r = self.run_sh("gehaeuse_neustart")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gehaeuse: neustart abgelehnt nicht noetig", r.stdout)
        self.run_sh("gehaeuse_ein 55 48")
        self.assertIn("systemctl reboot", self.run_sh("gehaeuse_neustart").stdout)

    def test_not_a_raspberry_pi(self):
        os.remove(self.txt)
        self.assertIn("gehaeuse: abgelehnt kein raspberry pi", self.run_sh("gehaeuse_ein 55 48").stdout)


if __name__ == "__main__":
    unittest.main()
