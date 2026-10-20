"""Akku schonen (Dominik 2026-10-16, guideline section 6 "Akku schonen"): a hidden page does not poll on a timer and
keeps no event stream open (it catches up on coming back), the Android app pauses its page in the background except
during a call, and the iPhone app stops its audio engine in the background once nothing listens, speaks or calls.
Static checks of the sources; files outside app/ skip in the app/-only copy the Spark tests. No wall clock dependence."""
import os
import re
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
JS = os.path.join(APP, "panel", "static", "js")
MAIN = os.path.join(ROOT, "android", "app", "src", "main", "java", "io", "github", "db9979", "spark", "MainActivity.kt")
IOS = os.path.join(ROOT, "ios", "Spark")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def need(path):
    if not os.path.exists(path):
        raise unittest.SkipTest(f"{os.path.relpath(path, ROOT)} is not in this copy (the Spark tests only app/)")
    return path


class HiddenPage(unittest.TestCase):
    def test_timers_ask_only_while_seen(self):
        self.assertIn("setInterval(()=>{if(!document.hidden)notausLoad()},15000)", read(os.path.join(JS, "notaus.js")))
        admin = read(os.path.join(JS, "admin.js"))
        self.assertIn("setInterval(()=>{if(ADMIN&&!document.hidden)ulWatch()},8000)", admin)
        # an update started elsewhere still locks the page as soon as it is seen again
        self.assertIn("document.addEventListener('visibilitychange',()=>{if(ADMIN&&!document.hidden)ulWatch()})", admin)
        self.assertRegex(read(os.path.join(JS, "chat.js")), r"setInterval\(\(\)=>\{if\(wake\.on&&!document\.hidden\)\$\('wakeind'\)")

    def test_history_stream_closes_while_hidden(self):
        v = read(os.path.join(JS, "verlauf.js"))
        settings = v[v.index("function syncSettings()"):v.index("function syncStart()")]
        self.assertIn("!document.hidden", settings)
        self.assertIn("syncStop()", settings)
        self.assertIn("document.addEventListener('visibilitychange',syncSettings)", v)
        # coming back asks ?since= at once, so nothing is missed while the stream was closed
        self.assertIn("document.addEventListener('visibilitychange',()=>{if(!document.hidden)convoLook(true)})",
                      read(os.path.join(JS, "chat.js")))


class Android(unittest.TestCase):
    def test_page_sleeps_in_the_background_except_in_a_call(self):
        m = read(need(MAIN))
        pause = m[m.index("override fun onPause()"):]
        pause = pause[:pause.index("\n    }\n")]
        self.assertIn("web.pauseTimers()", pause)
        self.assertIn("web.onPause()", pause)
        self.assertIn("AN.call", pause)   # anrufe.js: a ringing or running call keeps the page awake
        self.assertIn("!front", pause)    # back in front before the answer came: stays awake
        resume = m[m.index("override fun onResume()"):]
        resume = resume[:resume.index("\n    }\n")]
        self.assertIn("web.resumeTimers()", resume)
        self.assertIn("web.onResume()", resume)


class IPhone(unittest.TestCase):
    def test_audio_engine_sleeps_in_the_background(self):
        eng = read(need(os.path.join(IOS, "Engine.swift")))
        sleep = eng[eng.index("func sleep()"):]
        sleep = sleep[:sleep.index("\n    }\n")]
        self.assertRegex(sleep, r"guard engine\.isRunning, !tapOn, queued == 0, pending\.isEmpty, !holding")
        self.assertIn("engine.stop()", sleep)
        self.assertIn("setActive(false", sleep)
        # a route change or the end of an interruption does not wake it again by itself
        self.assertEqual(len(re.findall(r"!self\.sleeping", eng)), 2)
        a = read(need(os.path.join(IOS, "Assistant.swift")))
        guard = a[a.index("private func sleepAudio()"):]
        guard = guard[:guard.index("\n    }\n")]
        # in the car it sleeps in front too once a conversation ended (CarPlay stabil: a resting engine kept the car's sound)
        for x in ("!foreground || inCar", "!canWake", "phase == .idle", "!CallCenter.shared.active"):
            self.assertIn(x, guard)
        self.assertGreaterEqual(a.count("sleepAudio()"), 3)   # the definition, going to the background, base() after an answer

    def test_wake_word_on_battery_only_when_chosen(self):
        # Dominik 2026-10-16 (5a): the default of "Am Akku" is "Nur am Ladekabel", one default for both places
        p = read(need(os.path.join(IOS, "Phone.swift")))
        self.assertIn("static let batteryDefault = 0", p)
        self.assertIn("?? batteryDefault", p)
        self.assertIn('@AppStorage("batteryMinutes") private var batteryMinutes = Prefs.batteryDefault',
                      read(os.path.join(IOS, "Views.swift")))


if __name__ == "__main__":
    unittest.main()
