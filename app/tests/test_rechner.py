"""Zustand → Monitoring → Rechner (Dominik 2026-10-16, Variante 1): with the panel and the models on two computers,
both side by side. The values of a computer are numbers and fixed words only, the model computer's are taken as data
(unknown keys, wrong kinds and numbers out of range are dropped), the warnings follow fixed rules with one log line
per change, and on one Spark nothing changes. No test depends on the time of day: every time is given."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests import helpers

helpers.start()
import health  # noqa: E402
import live  # noqa: E402
import rechenteile  # noqa: E402
import rechner  # noqa: E402
import rechnerblick  # noqa: E402
import steuer  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIB = 2 ** 30


def messung(t=100.0, **kw):
    """A measurement as rechner.messen gives it."""
    m = {"t": t, "name": "tars", "geraet": "NVIDIA DGX Spark", "system": "Ubuntu 24.04", "cpu": 4.0, "kerne": 20, "last": 0.8,
         "ram_total": 121.7, "ram_frei": 41.2, "ram_cache": 3.0, "ram_pct": 66.1, "swap": 0.0, "platte_total": 3700.0,
         "platte_frei": 1200.0, "platte_pct": 67.6, "netz_rx": 1_000_000, "netz_tx": 2_000_000, "netz_mbit": 10000,
         "laeuft_s": 780000, "temp": 45.0, "luefter": None, "strom": None}
    m.update(kw)
    return m


def leer():
    for k in ("modell", "panel"):
        rechnerblick._verlauf[k].clear()
        rechnerblick._letzt[k] = None
        rechnerblick._netz[k] = (None, None)
    rechnerblick._warn.clear()
    rechnerblick._gpu.clear()
    rechnerblick._dienste.update(t=0.0, d=[])


class Messen(unittest.TestCase):
    def test_power_flags_in_words(self):
        self.assertEqual(rechner.strom_worte(0x50005), ("zu niedrig", "jetzt"))
        self.assertEqual(rechner.strom_worte(0x50000), ("war niedrig", "war an"))
        self.assertEqual(rechner.strom_worte(0), ("ok", "nein"))
        self.assertEqual(rechner.strom_worte(None), ("?", "?"))

    def test_temperature_fan_and_flags_from_the_reader(self):
        files = {f"{rechner.THERMAL}/thermal_zone0/temp": "52345\n", rechner.THROTTLED: "0x4\n"}

        def read(p):
            if p in files:
                return files[p]
            raise OSError(2, "missing")
        self.assertEqual(rechner.temp(read), 52.3)
        self.assertEqual(rechner.strom_flags(read), 4)
        self.assertIsNone(rechner.strom_flags(lambda p: (_ for _ in ()).throw(OSError(2, "missing"))))
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "cooling_device0"))
            for name, v in (("type", "pwm-fan\n"), ("cur_state", "2\n")):
                with open(os.path.join(d, "cooling_device0", name), "w") as f:
                    f.write(v)
            with mock.patch.object(rechner, "THERMAL", d):
                self.assertTrue(rechner.luefter())
            with open(os.path.join(d, "cooling_device0", "type"), "w") as f:
                f.write("cpufreq\n")
            with mock.patch.object(rechner, "THERMAL", d):
                self.assertIsNone(rechner.luefter())

    def test_a_measurement_holds_numbers_and_plain_words_only(self):
        rechner.cpu_pct()
        m = rechner.messen()
        for k, v in m.items():
            if k in rechnerblick.WORTE:
                self.assertIsInstance(v, str)
                self.assertRegex(v, r"^[A-Za-z0-9 .()+_-]*$")
            elif k == "luefter":
                self.assertIn(v, (True, False, None))
            elif k == "dienste_cpu":     # {service id: %}, None without systemd's counters (a container in the tests)
                self.assertTrue(v is None or all(rechnerblick.DIENST_ID.fullmatch(i) and 0 <= x <= 100 for i, x in v.items()), v)
            else:
                self.assertTrue(v is None or isinstance(v, (int, float)) and not isinstance(v, bool), k)
        self.assertGreater(m["ram_total"], 0)
        self.assertLessEqual(m["ram_frei"], m["ram_total"])
        self.assertTrue(set(rechnerblick.ZAHLEN) <= set(m), set(rechnerblick.ZAHLEN) - set(m))

    def test_the_cpu_load_has_its_own_baseline(self):
        """psutil.cpu_percent(None) is shared with every other caller; the own one is not reset by them."""
        import psutil
        rechner._cpu.clear()
        self.assertIsNone(rechner.cpu_pct())
        psutil.cpu_percent(None)
        v = rechner.cpu_pct()
        self.assertTrue(v is None or 0 <= v <= 100)

    def test_the_waerter_sends_the_values_with_its_status(self):
        import tarswart
        with mock.patch.object(tarswart.rechner, "messen", return_value=messung()):
            self.assertEqual(tarswart._rechner()["ram_total"], 121.7)
        with mock.patch.object(tarswart.rechner, "messen", side_effect=OSError("x")), redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(tarswart._rechner())
        self.assertEqual(out.getvalue(), "waerter: rechner OSError\n")


class Daten(unittest.TestCase):
    def test_the_model_computers_values_are_data(self):
        m = messung(cpu=250, kerne="20", platte_pct=True, name="tars;rm -rf /", geraet=7, extra="x", luefter="an",
                    ram_frei=-1.0)
        got = rechnerblick.pruefen(m)
        self.assertIsNone(got["cpu"])            # out of range
        self.assertIsNone(got["kerne"])          # not a number
        self.assertIsNone(got["platte_pct"])     # a bool is no number
        self.assertIsNone(got["ram_frei"])
        self.assertEqual(got["name"], "tarsrm -rf")
        self.assertEqual(got["geraet"], "")
        self.assertIsNone(got["luefter"])
        self.assertNotIn("extra", got)
        self.assertIsNone(rechnerblick.pruefen("kaputt"))


class Karten(unittest.TestCase):
    def setUp(self):
        leer()
        self.addCleanup(leer)
        for name, kw in (("remote", {"return_value": True}), ("weg", {"return_value": False}), ("stumm_s", {"return_value": 2})):
            p = mock.patch.object(steuer, name, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.status = {"version": "V01.0.700", "gpu": {"util": 12.0, "temp": 58.0, "power": 41.0, "name": "GB10"},
                       "einheiten": {"speech-spark-asr": {"state": "active"}, "speech-spark-tts": {"state": "failed"},
                                     "speech-spark-llm": {"state": "active"}, "speech-spark-sehen": {"state": "unknown"},
                                     "speech-spark-musik": {"state": "active"}},
                       "modellwahl": {"llm": {"modell": "RadixArk/qwen38-27b-nvfp4", "enabled": True}},
                       "rechner": messung()}
        p = mock.patch.object(steuer, "cached", side_effect=lambda **kw: self.status)
        p.start()
        self.addCleanup(p.stop)
        self.pi = messung(t=50.0, name="speech", geraet="Raspberry Pi 5 Model B Rev 1.0", cpu=3.0, kerne=4, ram_total=7.9,
                          ram_frei=7.2, platte_total=238.0, platte_frei=212.0, platte_pct=11.0, temp=52.0, luefter=True, strom=0)
        p = mock.patch.object(rechner, "messen", side_effect=lambda **kw: dict(self.pi))
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(rechnerblick, "run", return_value=(0, "Id=speech-spark-turn.service\nActiveState=active\n"
                                                                   "LoadState=loaded\n\nId=speech-spark-notasr.service\n"
                                                                   "ActiveState=inactive\nLoadState=not-found\n"))
        p.start()
        self.addCleanup(p.stop)

    def runde(self, now, **pi):
        self.pi.update(pi)
        with redirect_stdout(io.StringIO()) as out:
            rechnerblick.probe(now=now, mono=now)
        return out.getvalue()

    def test_both_cards_side_by_side(self):
        self.runde(1000.0)
        self.status["rechner"] = messung(t=103.0, netz_rx=4_000_000, netz_tx=2_300_000)
        self.runde(1003.0, t=53.0)
        d = rechnerblick.fuer_status(now=1003.0, mono=1003.0)
        self.assertTrue(d["an"])
        m, p = d["liste"]
        self.assertEqual((m["id"], p["id"]), ("modell", "panel"))
        self.assertEqual(m["gpu"], {"util": 12.0, "temp": 58.0, "power": 41.0})
        self.assertEqual(m["llm"], "qwen38-27b-nvfp4")
        self.assertEqual((m["netz_rx_mbs"], m["netz_tx_mbs"]), (1.0, 0.1))
        self.assertEqual([(x["id"], x["state"]) for x in m["dienste"]],
                         [("asr", "active"), ("tts", "failed"), ("llm", "active"), ("musik", "active"), ("waerter", "active")])
        self.assertEqual([(x["id"], x["state"]) for x in p["dienste"]], [("panel", "active"), ("turn", "active")])
        self.assertEqual((m["dienste"][3]["name"], m["dienste"][3]["en"]), ("Musik machen", "Making music"))   # names from here
        self.assertEqual((m["stufe"], p["stufe"]), ("ok", "ok"))
        self.assertEqual(p["temp_warn"], rechnerblick.TEMP_WARN)
        self.assertEqual(len(m["kurven"]["gpu"]), 2)
        self.assertNotIn("gpu", p["kurven"])

    def test_the_same_status_counts_once(self):
        self.runde(1000.0)
        self.runde(1003.0, t=53.0)
        self.assertEqual(len(rechnerblick._verlauf["modell"]), 1)
        self.assertEqual(len(rechnerblick._verlauf["panel"]), 2)

    def test_a_curve_has_at_most_its_points(self):
        for i in range(rechnerblick.VERLAUF + 30):
            self.status["rechner"] = messung(t=100.0 + i)
            self.runde(1000.0 + 3 * i, t=50.0 + i)
        k = rechnerblick.kurven("modell")
        self.assertLessEqual(len(k["cpu"]), rechnerblick.PUNKTE)
        self.assertGreater(len(k["cpu"]), rechnerblick.PUNKTE / 2)
        rechnerblick._verlauf["modell"].append({"t": 1000.0 + 3 * rechnerblick.VERLAUF + 5000, "cpu": 9.0})
        self.assertEqual(rechnerblick.kurven("modell")["cpu"], [9.0])     # older than FENSTER_S: not shown
        self.assertEqual(len(rechnerblick._verlauf["modell"]), rechnerblick.VERLAUF)

    def test_warnings_follow_fixed_rules_with_one_line_per_change(self):
        out = self.runde(1000.0, temp=rechnerblick.TEMP_WARN + 1.0)
        self.assertEqual(out, "rechner: hinweis heiss an\n")
        self.assertEqual(self.runde(1003.0, t=51.0, temp=rechnerblick.TEMP_OK + 1.0), "")    # still warm: stays on
        self.assertEqual(self.runde(1006.0, t=52.0, temp=rechnerblick.TEMP_OK - 1.0), "rechner: hinweis heiss aus\n")
        out = self.runde(1009.0, t=53.0, strom=0x5, ram_frei=0.3, platte_pct=95.0, platte_frei=12.0)
        self.assertEqual(sorted(out.splitlines()), ["rechner: hinweis drossel an", "rechner: hinweis platte_panel an",
                                                    "rechner: hinweis ram an", "rechner: hinweis strom an"])
        al = rechnerblick.alerts()
        self.assertEqual({a["kind"] for a in al}, {"rechner"})
        self.assertEqual({a["go"] for a in al}, {"Zustand → Monitoring → Rechner"})
        self.assertIn({"kind": "rechner", "level": "bad", "go": "Zustand → Monitoring → Rechner",
                       "text": "Der Panel-Rechner hat nur noch 0.3 GiB Arbeitsspeicher frei."}, al)
        self.assertEqual(rechnerblick.karte("panel", mono=1009.0)["stufe"], "bad")
        self.assertEqual(rechnerblick.karte("modell", mono=1009.0)["stufe"], "ok")
        self.assertTrue(any(a["kind"] == "rechner" for a in health.alerts()))

    def test_the_model_computer_gone_keeps_its_card(self):
        self.runde(1000.0)
        self.status = None
        with mock.patch.object(steuer, "weg", return_value=True), mock.patch.object(steuer, "stumm_s", return_value=240):
            self.assertEqual(self.runde(1003.0, t=51.0), "rechner: hinweis weg an\n")
            m = rechnerblick.karte("modell", mono=1003.0)
            al = rechnerblick.alerts()
        self.assertEqual((m["ok"], m["stufe"], m["stumm_s"]), (False, "bad", 240))
        self.assertEqual(m["ram_total"], 121.7)                  # the last values stay (the page greys them)
        self.assertIn("Der Modell-Rechner antwortet seit 4 min nicht: Notbetrieb.", [a["text"] for a in al])

    def test_disk_of_the_model_computer(self):
        self.status["rechner"] = messung(platte_pct=93.0, platte_frei=250.0)
        self.assertEqual(self.runde(1000.0), "rechner: hinweis platte_modell an\n")
        self.assertIn("Auf dem Modell-Rechner sind nur noch 250 GB frei (93 % belegt).", [a["text"] for a in rechnerblick.alerts()])

    def test_no_address_and_no_process_in_a_card(self):
        self.runde(1000.0)
        txt = json.dumps(rechnerblick.fuer_status(now=1000.0, mono=1000.0))
        self.assertNotRegex(txt, r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        self.assertNotIn("pid", txt)
        self.assertNotIn("processes", txt)

    def test_live_shows_both_in_numbers(self):
        self.runde(1000.0)
        d = rechnerblick.for_live()
        self.assertEqual(d["panel"], {"cpu": 3.0, "belegt": 7.9 - 7.2, "total": 7.9, "temp": 52.0, "platte": 11.0,
                                      "haenger": 0, "spitze": None})   # no stall (loopwacht.view), nothing measured yet
        self.assertEqual(d["modell"], {"gpu": 12.0, "frei": 41.2, "cpu": 4.0, "spitze": None})
        self.assertIn("panelrechner", live.TARGETS)
        self.assertEqual(live._n(7.25, 1), "7,2")
        self.assertEqual(live._n(None), "-")
        self.assertIn("pi", live._sys())

    def test_the_status_shows_the_model_computers_cpu(self):
        import monitor
        s = monitor.system_stats()
        self.assertEqual((s["cpu"], s["mem_von"]), (4.0, "modell-rechner"))


class WerRechnet(unittest.TestCase):
    """„Wer rechnet gerade“ (Dominik 2026-10-18 „1a 2a 3a 4b“): the services' share of the CPU from systemd's counters,
    the panel's parts from its threads, the biggest for the tile, Live and the Steuerzentrale, the strip of 20 minutes."""
    def setUp(self):
        leer()
        self.addCleanup(leer)
        rechner._dienst.clear()
        rechenteile._alt.clear()
        self.addCleanup(rechner._dienst.clear)
        self.addCleanup(rechenteile._alt.clear)

    def cgroup(self, werte):
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        for name, usec in werte.items():
            os.makedirs(os.path.join(d, name))
            with open(os.path.join(d, name, "cpu.stat"), "w") as f:
                f.write(f"usage_usec {usec}\nuser_usec 1\nsystem_usec 1\n")
        return d

    def test_each_service_from_systemds_counters(self):
        d = self.cgroup({"speech-spark-llm.service": 0, "speech-spark-asr.service": 0, "qwen38-sglang.service": 0,
                         "docker-abc.scope": 0, "ssh.service": 0, "speech-spark-tts.service": 5_000_000})
        self.assertEqual(rechner.dienste_cpu(base=d, now=100.0, kerne=4), {})          # the first round: no baseline
        d2 = self.cgroup({"speech-spark-llm.service": 6_000_000, "speech-spark-asr.service": 1_200_000,
                          "qwen38-sglang.service": 30_000, "docker-abc.scope": 600_000, "ssh.service": 9_000_000,
                          "speech-spark-tts.service": 100})                               # tts started again: counts 0
        got = rechner.dienste_cpu(base=d2, now=103.0, kerne=4)
        self.assertEqual(got, {"llm": 50.0, "asr": 10.0, "docker": 5.0, "qwen38": 0.2})
        self.assertEqual(list(got), ["llm", "asr", "docker", "qwen38"])                 # the biggest first
        self.assertIsNone(rechner.dienste_cpu(base=os.path.join(d, "fehlt")))           # no counters (cgroup v1)

    def test_the_model_computers_services_are_data(self):
        got = rechnerblick.pruefen(messung(dienste_cpu={"llm": 30.0, "Böse;rm": 5.0, "asr": 120.0, "tts": True,
                                                        "x" * 30: 1.0, "bild": 2.5}))
        self.assertEqual(got["dienste_cpu"], {"llm": 30.0, "bild": 2.5})
        self.assertIsNone(rechnerblick.pruefen(messung(dienste_cpu="viel"))["dienste_cpu"])

    def test_the_panels_parts_from_its_threads(self):
        self.assertEqual(rechenteile.teil_von("MainThread", haupt=True), "anfragen")
        self.assertEqual(rechenteile.teil_von("asyncio_3"), "anfragen")
        self.assertEqual(rechenteile.teil_von("bg-Mail sortieren"), "bg:Mail sortieren")
        self.assertEqual(rechenteile.teil_von("auslassen"), "auslassen")
        self.assertEqual(rechenteile.teil_von("irgendwas"), "weitere")
        runde = [{("t", 1): ("anfragen", 100), ("t", 2): ("bg:Suchindex", 50), ("p", 9): ("bedeutungssuche", 10)},
                 {("t", 1): ("anfragen", 130), ("t", 2): ("bg:Suchindex", 50), ("p", 9): ("bedeutungssuche", 250),
                  ("t", 3): ("auslassen", 400)}]                                          # a new thread: next round
        self.assertEqual(rechenteile.messen(now=10.0, lesen=lambda: runde[0], kerne=4, hz=100), {})
        self.assertEqual(rechenteile.messen(now=13.0, lesen=lambda: runde[1], kerne=4, hz=100),
                         {"bedeutungssuche": 20.0, "anfragen": 2.5})
        self.assertTrue(all(isinstance(v, int) for v in rechenteile._lesen().values() for v in v[1:]))   # this process

    def test_who_computes_lists_rest_and_parts(self):
        m = messung(cpu=46.0, dienste_cpu={"panel": 39.0, "notasr": 4.0, "schirm": 2.0},
                    teile={"bedeutungssuche": 31.0, "anfragen": 6.0})
        r = rechnerblick.rechnen("panel", m)
        self.assertEqual([(x["id"], x["pct"]) for x in r], [("panel", 39.0), ("notasr", 4.0), ("schirm", 2.0), ("rest", 1.0)])
        self.assertEqual([(x["id"], x["name"], x["pct"]) for x in r[0]["teile"]],
                         [("bedeutungssuche", "Bedeutungssuche", 31.0), ("anfragen", "Anfragen und Seiten", 6.0),
                          ("uebrig", "Kurze Programme und Rest", 2.0)])
        self.assertEqual(rechnerblick.spitze("panel", m), {"id": "panel/bedeutungssuche", "name": "Panel · Bedeutungssuche",
                                                           "en": "Panel · Meaning search", "pct": 31.0})
        self.assertEqual(rechnerblick.spitze("modell", messung(cpu=38.0, dienste_cpu={"llm": 29.0, "asr": 7.0}))["name"], "Sprachmodell")
        self.assertIsNone(rechnerblick.spitze("modell", messung(cpu=4.0, dienste_cpu={"llm": rechnerblick.LEERLAUF_PCT - 1})))
        self.assertEqual(rechnerblick.rechnen("modell", messung()), [])               # an older Wärter: nothing measured
        many = {f"d{i}": 10.0 - i for i in range(9)}
        r = rechnerblick.rechnen("modell", messung(cpu=60.0, dienste_cpu=many))
        self.assertEqual(len(r), rechnerblick.ZEILEN + 1)                               # the others count for the rest
        self.assertEqual(r[-1], {"id": "rest", "name": "System und Rest", "en": "System and rest", "pct": 15.0})

    def test_the_strip_keeps_who_worked_most(self):
        with mock.patch.object(steuer, "remote", return_value=True), mock.patch.object(steuer, "cached", return_value=None), \
                mock.patch.object(steuer, "weg", return_value=False), mock.patch.object(steuer, "stumm_s", return_value=None):
            for i, (pct, teile) in enumerate([(1.0, {}), (30.0, {"anfragen": 25.0}), (40.0, {"bg:Suchindex": 35.0})]):
                pi = messung(t=50.0 + i, cpu=pct + 2, dienste_cpu={"panel": pct})
                with mock.patch.object(rechner, "messen", return_value=pi), mock.patch.object(rechenteile, "messen", return_value=teile):
                    rechnerblick.probe(now=1000.0 + 3 * i, mono=1000.0 + 3 * i)
            k = rechnerblick.karte("panel", now=1006.0, mono=1006.0)
        self.assertEqual(k["kurven"]["top"], [None, "panel/anfragen", "panel/bg:Suchindex"])   # idle grey first
        self.assertEqual(k["namen"], {"panel/anfragen": ["Panel · Anfragen und Seiten", "Panel · Requests and pages"],
                                      "panel/bg:Suchindex": ["Panel · Suchindex", "Panel · Suchindex"]})
        self.assertEqual(k["spitze"]["id"], "panel/bg:Suchindex")
        txt = json.dumps(k)
        self.assertNotIn("pid", txt)
        self.assertNotIn("/proc", txt)

    def test_every_own_service_and_thread_has_a_name(self):
        """Guideline part 5: every speech-spark-<name>.service of install.sh has its name de/en, every fixed thread of
        the panel its part with a name."""
        import re
        units = set(re.findall(r"speech-spark-([a-z][a-z0-9-]*)\.service", helpers.repo_file("install.sh")))
        self.assertTrue(units)
        stumm = {"teilen-fw", "werkstatt-fw"}   # oneshots that only load firewall rules: never takes CPU worth a line
        self.assertEqual(units - set(rechnerblick.DIENST_NAMEN) - stumm, set())
        for teil in (*rechenteile.THREADS.values(), *rechenteile.PROZESSE.values(), rechenteile.ANFRAGEN, "weitere", "uebrig"):
            self.assertIn(teil, rechnerblick.TEIL_NAMEN)
        for de, en in (*rechnerblick.DIENST_NAMEN.values(), *rechnerblick.TEIL_NAMEN.values()):
            self.assertTrue(de and en)

    def test_live_and_the_screen_name_the_biggest(self):
        sp = {"id": "llm", "name": "Sprachmodell", "en": "Language model", "pct": 29.0}
        self.assertEqual(live._spitze(sp), " · am meisten Sprachmodell 29 %")
        self.assertEqual(live._spitze(None), "")
        rechnerblick._letzt["modell"] = messung(cpu=38.0, dienste_cpu={"llm": 29.0})
        rechnerblick._letzt["panel"] = messung(cpu=3.0, dienste_cpu={"panel": 2.0})
        with mock.patch.object(steuer, "remote", return_value=True):
            d = rechnerblick.for_live()
        self.assertEqual(d["modell"]["spitze"]["name"], "Sprachmodell")
        self.assertIsNone(d["panel"]["spitze"])                                         # idle: nobody named


class EinSpark(unittest.TestCase):
    def setUp(self):
        leer()
        self.addCleanup(leer)

    def test_one_spark_shows_what_it_showed_before(self):
        with mock.patch.object(steuer, "remote", return_value=False):
            self.assertFalse(rechnerblick.probe(now=1000.0, mono=1000.0))
            self.assertEqual(rechnerblick.fuer_status(), {"an": False})
            self.assertEqual(rechnerblick.alerts(), [])
            self.assertEqual(rechnerblick.for_live(), {"on": False})
            self.assertNotIn("pi", live._sys())


class Seite(unittest.TestCase):
    def read(self, *p):
        with open(os.path.join(APP, "panel", *p), encoding="utf-8") as f:
            return f.read()

    def test_the_page_has_its_place_and_its_way(self):
        html, js = self.read("static", "index.html"), self.read("static", "js", "admin.js")
        self.assertIn('<h3 class="zsec" id="zrechnerh" hidden>Rechner', html)
        self.assertIn('id="zrechner"', html)
        self.assertIn("function zRechner(R)", js)
        self.assertIn("s.rechner", js)
        self.assertIn("function zRWer(c)", js)            # „Wer rechnet gerade“ with its strip
        self.assertNotIn("ZR_DIENST", js)                 # the services' names come only from rechnerblick.py

