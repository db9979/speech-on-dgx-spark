"""Units and abbreviations spoken in full (plan genauer-und-schneller, 10): textnorm.UNITS, speak_abbreviations."""
import os
import unittest

from tests import helpers  # noqa: F401  (sets up paths and a throw-away state directory)
import textnorm  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def say(text, lang="de"):
    return textnorm.speak_numbers(textnorm.speak_abbreviations(text, lang), lang)


class Units(unittest.TestCase):
    def test_units_after_a_number(self):
        self.assertEqual(say("Mit 50 km/h fährt er 12 km."), "Mit fünfzig Kilometer pro Stunde fährt er zwölf Kilometer.")
        self.assertIn("drei Kilowattstunden", say("Heute 3 kWh."))
        self.assertIn("zwei Liter Milch und fünfhundert Gramm Mehl", say("Ich habe 2 l Milch und 500 g Mehl."))
        self.assertIn("sechzehn Gigabyte", say("Noch 16 GB frei."))
        self.assertIn("drei Stunden und zwanzig Minuten", say("Wir fahren 3 h und 20 min."))
        self.assertIn("einundzwanzig Grad Celsius und achtzig Prozent", say("Es sind 21 °C und 80 % Regen."))

    def test_a_letter_is_a_unit_only_as_a_whole_word(self):
        self.assertIn("gibt", say("Es gibt 3 Gründe."))           # no "Gramm" in "Gründe"
        self.assertIn("lange", say("Das dauert 5 lange Tage."))   # no "Liter" in "lange"
        self.assertEqual(say("Er war h. Das l. Wort"), "Er war h. Das l. Wort")

    def test_english_units(self):
        self.assertEqual(say("It is 5 km away, 20 °C.", "en"), "It is five kilometres away, twenty degrees Celsius.")


class Abbreviations(unittest.TestCase):
    def test_german_abbreviations(self):
        self.assertEqual(say("Das kostet ca. 30 €/Monat, bzw. 5 kg."),
                         "Das kostet circa dreißig Euro pro Monat, beziehungsweise fünf Kilogramm.")
        self.assertIn("zum Beispiel", say("Obst, z. B. Äpfel."))
        self.assertIn("zum Beispiel", say("Obst, z.B. Äpfel."))
        self.assertIn("Nummer fünf", say("Die Nr. 5 ist frei."))
        self.assertIn("Hauptstraße drei", say("Er wohnt in der Hauptstr. 3"))

    def test_plain_words_stay(self):
        for text in ("Ich mag das Café.", "Das ist usw ohne Punkt.", "Herr Dr Müller"):
            self.assertEqual(textnorm.speak_abbreviations(text, "de"), text)

    def test_english_unchanged(self):
        self.assertEqual(textnorm.speak_abbreviations("This is e.g. fine, ca. 5.", "en"), "This is e.g. fine, ca. 5.")

    def test_both_speech_services_use_it(self):
        for name in ("tts_proxy.py", "tts_server.py"):   # read, not imported: the server needs soundfile/torch
            with open(os.path.join(APP, name), encoding="utf-8") as f:
                self.assertIn("speak_abbreviations(", f.read(), name)


if __name__ == "__main__":
    unittest.main()
