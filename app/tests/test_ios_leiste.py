"""iPhone app, bar on top of the Assistent view (Dominik 2026-11-17 „die drei Punkte oben rechts haben keine
Funktion“): with seven symbols the iPhone folded the last ones into its own „⋯“, which cannot show or start buttons
with drawn labels (the ladybug, Chats with its count). Each side holds at most three symbols, so nothing is folded
away; Heute and Einstellungen sit in the app's own „⋯“ menu with written labels. (ios/ is not in an app/-only copy,
then this is skipped.)"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IOS = os.path.join(ROOT, "ios")
MOST = 3


def chat_bar():
    with open(os.path.join(IOS, "Spark", "Views.swift")) as f:
        s = f.read()
    body = s[s.index("struct ChatView: View"):]
    return body[:body.index("private var talking")]


class AssistentLeiste(unittest.TestCase):
    def setUp(self):
        if not os.path.isdir(IOS):
            self.skipTest("ios/ is not in an app/-only copy")

    def test_each_side_at_most_three(self):
        bar = chat_bar()
        right = bar.count("placement: .topBarTrailing")
        if ".kaefer(" in bar:   # the ladybug's modifier adds one on the right (ReportView.swift Kaefer)
            right += 1
        self.assertLessEqual(right, MOST, "rechts zu viele Symbole: das iPhone klappt sie in ein „⋯“, das nichts tut")
        # the demo's „Vorführung beenden“ only shows in the demo and is not counted
        left = bar.count("placement: .topBarLeading") - bar.count('Button("Vorführung beenden")')
        self.assertLessEqual(left, MOST, "links zu viele Symbole")

    def test_heute_and_settings_in_own_menu_with_words(self):
        bar = chat_bar()
        menu = bar[bar.index("Menu {"):]
        menu = menu[:menu.index('} label: { Image(systemName: "ellipsis.circle") }')]
        for word, sym in (("Heute", "sun.max"), ("Einstellungen", "gearshape")):
            self.assertRegex(menu, r'Label\("%s", systemImage: "%s"\)' % (word, re.escape(sym)))
        self.assertIn('.accessibilityLabel("Mehr")', bar)


if __name__ == "__main__":
    unittest.main()
