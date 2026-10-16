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
        gehaeuse._st.update(oled="aus", led="aus", addr=None, seite="", farbe="aus", next=0.0, i=0, led_t=0.0, fail={}, bild=None)
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
