"""Verdeckter Prüfsatz der Weiche (Kritische Prüfung 2026-11-12 point 2): intent_bench.BENCH and GEGEN are the sentences
the rules were tuned on, so they say little about sentences nobody has seen. VERDECKT below was written on 2026-11-12
by a helper that never saw intent.py (only the group names and their meaning): 168 everyday sentences, 24 of them
without a tool. It measures the Weiche on new sentences.

The rule that keeps it worth anything (docs/de/richtlinien.md Teil 8): nobody changes intent.py to make a sentence of
VERDECKT pass. Fixes come from real requests (Logs → Anfragen) and from BENCH/GEGEN; VERDECKT only shows whether they
also help sentences nobody tuned for. MIN_TREFFER is a floor: a change that loses hits here is red. When the rules get
better on their own the number may be raised, never lowered. The set is renewed by a new helper when it is used up.

Measured on V01.1.397: 136 of 168 (81 %), BENCH 100 %. No model, no clock.
"""
import unittest

from tests import helpers

helpers.start()
import intent  # noqa: E402

MIN_TREFFER = 136
# a call („Ruf Oma an“) lands on the phone: kontakt and iphone both hold the tool
GLEICH = {"kontakt": {"kontakt", "iphone"}}
VERDECKT = (   # (sentence, expected group; "unklar" = no tool), never tuned on (see above)
 ("Mach mal das Licht im Flur an", "smarthome"),
 ("Mach das Licht bloß NICHT aus, ich lese noch", "smarthome"),
 ("Is die Heizung im Bad eigentlich an?", "smarthome"),
 ("Fahr die Rollos im Wohnzimmer bitte halb runter", "smarthome"),
 ("Ist das Küchenfenster noch offen?", "smarthome"),
 ("Schick den Saugroboter los, aber nicht ins Schlafzimmer", "smarthome"),
 ("Schalt die Steckdose vom Fernseher aus", "smarthome"),
 ("Läuft die Waschmaschine noch oder ist die fertig?", "smarthome"),
 ("Was steht nächste Woche Dienstag bei mir an?", "kalender"),
 ("Trag mal den Zahnarzt am Freitag um halb drei ein", "kalender"),
 ("Verschieb das Meeting morgen auf 16 Uhr", "kalender"),
 ("Hab ich übermorgen irgendwas vor?", "kalender"),
 ("Gib mir mal meinen Tagesüberblick", "kalender"),
 ("Lösch den Termin mit Frau Krüger wieder raus", "kalender"),
 ("Wann ist nochmal das Elterngespräch?", "kalender"),
 ("Ist Samstag Vormittag was im Kalender oder bin ich frei?", "kalender"),
 ("Hat mir der Chef schon auf meine Mail geantwortet?", "mail"),
 ("Zeig mir die ungelesenen Mails von heute", "mail"),
 ("Schreib ne kurze Antwort an Tanja, dass ich später komme, aber schick sie noch nicht ab", "mail"),
 ("Such mal die Mail mit der Rechnung von Amazon", "mail"),
 ("Les mir die letzte Mail vom Vermieter vor", "mail"),
 ("Räum mal meinen Posteingang auf, der Newsletter-Kram nervt", "mail"),
 ("Entwirf eine Mail an die Hausverwaltung wegen der Heizung", "mail"),
 ("Is was Wichtiges im Postfach?", "mail"),
 ("Wer hat gestern Abend das Bundesligaspiel gewonnen?", "websuche"),
 ("Such im Internet nach einem guten Rezept für Gulasch", "websuche"),
 ("Was kostet gerade ein Liter Diesel?", "websuche"),
 ("Hat der Baumarkt heute noch offen?", "websuche"),
 ("Was gibt es Neues in den Nachrichten?", "websuche"),
 ("Wie steht der Dax heute?", "websuche"),
 ("Google mal, wie lange der neue Film im Kino geht", "websuche"),
 ("Wie ist der aktuelle Bitcoinkurs?", "websuche"),
 ("Erinner mich in zehn Minuten an die Nudeln", "erinnerung"),
 ("Stell nen Timer auf 25 Minuten", "erinnerung"),
 ("Weck mich morgen um halb sieben", "erinnerung"),
 ("Ruf mich um acht, ich muss zum Bus", "erinnerung"),
 ("Denk bitte dran, dass ich heute Abend die Tabletten nehmen muss", "erinnerung"),
 ("Sag mir Bescheid, wenn ich um drei Mama anrufen soll", "erinnerung"),
 ("Lösch den Wecker für morgen wieder", "erinnerung"),
 ("Timer für die Pizza, zwölf Minuten", "erinnerung"),
 ("Setz Milch und Eier auf die Einkaufsliste", "liste"),
 ("Was steht alles auf meiner Einkaufsliste?", "liste"),
 ("Streich die Butter von der Liste, hab ich schon", "liste"),
 ("Pack noch Klopapier auf die Liste", "liste"),
 ("Neue Aufgabe für die To-do-Liste: Steuererklärung machen", "liste"),
 ("Hak auf der Todo-Liste das Auto waschen ab", "liste"),
 ("Was muss ich noch alles erledigen laut meiner Liste?", "liste"),
 ("Schreib Katzenfutter auf den Einkaufszettel", "liste"),
 ("Wird das morgen regnen?", "wetter"),
 ("Wie warm wird es am Wochenende?", "wetter"),
 ("Brauch ich heut nen Schirm?", "wetter"),
 ("Wie is das Wetter in Hamburg nächste Woche?", "wetter"),
 ("Kann ich morgen die Wäsche draußen aufhängen oder wirds nass?", "wetter"),
 ("Gibts heute Nacht Frost?", "wetter"),
 ("Wetter heute Nachmittag?", "wetter"),
 ("Wann kommt die Sonne wieder raus?", "wetter"),
 # Bus und Bahn is gone (Ausdünnen 5, V01.1.439): no group of the Weiche any more, the source switch sends them out
 ("Wann fährt der nächste Zug nach Köln?", "unklar"),
 ("Hat der ICE nach München Verspätung?", "unklar"),
 ("Wie komm ich mit dem Bus zum Hauptbahnhof?", "unklar"),
 ("Fährt die S-Bahn heute überhaupt oder streiken die wieder?", "websuche"),
 ("Verbindung von Leipzig nach Berlin morgen früh gegen acht", "unklar"),
 ("Welches Gleis fährt der RE 5 ab?", "unklar"),
 ("Wann geht die nächste U-Bahn Richtung Innenstadt?", "unklar"),
 ("Ich muss um neun in Frankfurt sein, welcher Zug passt?", "unklar"),
 ("Wo is mein Paket eigentlich?", "paket"),
 ("Kommt heute noch was von DHL?", "paket"),
 ("Wann wird die Bestellung von Zalando geliefert?", "paket"),
 ("Verfolg mal die Sendung mit der Nummer 00340434", "paket"),
 ("Is der Paketbote schon da gewesen?", "paket"),
 ("Steckt mein Hermes-Paket irgendwo fest?", "paket"),
 ("Welche Lieferungen sind gerade unterwegs zu mir?", "paket"),
 ("Wann kommt das Päckchen von Ebay an?", "paket"),
 ("Wie ist die Handynummer von Oma?", "kontakt"),
 ("Ruf mal den Klaus an", "kontakt"),
 ("Wo wohnt der Peter nochmal, hab ich seine Adresse?", "kontakt"),
 ("Gib mir die Telefonnummer vom Zahnarzt", "kontakt"),
 ("Ruf bitte meine Schwester an, aber nicht auf dem Festnetz", "kontakt"),
 ("Hab ich die Mailadresse von Frau Weber gespeichert?", "kontakt"),
 ("Such mir den Kontakt vom Klempner raus", "kontakt"),
 ("Wähl die Nummer vom Papa", "kontakt"),
 ("Merk dir, dass ich Erdnüsse nicht vertrage", "gedaechtnis"),
 ("Vergiss bitte, was ich dir gestern über meinen Urlaub erzählt hab", "gedaechtnis"),
 ("Was weißt du eigentlich alles über mich?", "gedaechtnis"),
 ("Worüber haben wir letzte Woche gesprochen?", "gedaechtnis"),
 ("Merk dir mal, mein Auto steht in Parkhaus B", "gedaechtnis"),
 ("Weißt du noch, was ich dir über meinen Bruder gesagt hab?", "gedaechtnis"),
 ("Das mit der Allergie darfst du wieder vergessen", "gedaechtnis"),
 ("Behalt im Kopf, dass ich morgens keinen Kaffee mag", "gedaechtnis"),
 ("Was steht in meinem Mietvertrag zur Kündigungsfrist?", "dokument"),
 ("Such in meinen Unterlagen die Versicherungspolice fürs Auto", "dokument"),
 ("Wie hoch war die Stromrechnung im letzten Jahr laut meinen Dokumenten?", "dokument"),
 ("Fass mir den Vertrag von der Handyfirma kurz zusammen", "dokument"),
 ("Was deckt meine Hausratversicherung bei Wasserschaden ab?", "dokument"),
 ("Schau mal in die hochgeladene Rechnung, wann ist die fällig?", "dokument"),
 ("Is in meinem Arbeitsvertrag was zu Überstunden drin?", "dokument"),
 ("Find mir den Garantieschein vom Kühlschrank", "dokument"),
 ("Sag Mama, dass das Essen fertig ist", "nachricht"),
 ("Schick dem Papa ne Nachricht, ich bin gleich da", "nachricht"),
 ("Mach ne Durchsage in der Küche, dass wir essen", "nachricht"),
 ("Hat mir die Lisa was geschrieben?", "nachricht"),
 ("Sag allen Bescheid, dass morgen früh Abfahrt um sieben ist", "nachricht"),
 ("Ruf über die Lautsprecher, dass die Kinder runterkommen sollen", "nachricht"),
 ("Schreib meinem Mann, er soll Brot mitbringen", "nachricht"),
 ("Les mir die Nachrichten von den Kindern vor", "nachricht"),
 ("Schau jeden Morgen nach dem Spritpreis und sag mir Bescheid", "agent"),
 ("Schick mir jeden Montag eine Zusammenfassung der Wochentermine", "agent"),
 ("Beobachte den Preis von der Kamera und meld dich, wenn er unter 400 fällt", "agent"),
 ("Starte im Hintergrund eine Recherche zu Wärmepumpen und gib mir morgen das Ergebnis", "agent"),
 ("Richte mir eine Morgenroutine ein: Wetter, Termine, Nachrichten", "agent"),
 ("Prüf täglich, ob neue Wohnungen in Jena drin sind", "agent"),
 ("Mach jeden Freitag einen Bericht über den Stromverbrauch", "agent"),
 ("Halt für mich die Augen offen, ob der Flug billiger wird", "agent"),
 ("Was kannst du eigentlich alles?", "spark"),
 ("Wie schalte ich bei dir die Wetterfunktion ein?", "spark"),
 ("Wo stell ich deine Stimme leiser?", "spark"),
 ("Kannst du auch Mails lesen oder geht das nicht?", "spark"),
 ("Welche Funktionen sind bei dir gerade aktiv?", "spark"),
 ("Wie ändere ich deine Sprache auf Englisch?", "spark"),
 ("Warum antwortest du manchmal so langsam, kann man das einstellen?", "spark"),
 ("Was bedeutet der Gästemodus bei dir?", "spark"),
 ("Schreib mir einen Brief an die Krankenkasse als Word-Datei", "erstellen"),
 ("Mach mir ne Präsentation über Klimawandel, so zehn Folien", "erstellen"),
 ("Erstell eine Tabelle mit meinen Monatsausgaben als Excel", "erstellen"),
 ("Setz eine Kündigung fürs Fitnessstudio als PDF auf", "erstellen"),
 ("Bau mir bitte einen Lebenslauf als Dokument", "erstellen"),
 ("Ich brauch ein Powerpoint für Omas Geburtstag", "erstellen"),
 ("Formulier ein Anschreiben für die Bewerbung und speicher es als Datei", "erstellen"),
 ("Mach ne Tabelle für den Putzplan zum Ausdrucken", "erstellen"),
 ("Mal mir einen Drachen, der auf einem Berg sitzt", "bild"),
 ("Generier ein Bild von nem Sonnenuntergang am Meer", "bild"),
 ("Zeichne mir bitte eine Katze mit Sombrero", "bild"),
 ("Ich will ein Foto-Poster von einer Stadt der Zukunft, mach das mal", "bild"),
 ("Erzeug mir ein Logo für meinen Backladen", "bild"),
 ("Mal ein lustiges Bild von nem Hund im Raumanzug", "bild"),
 ("Kannst du mir ein Porträt im Comicstil malen?", "bild"),
 ("Bild bitte: ein Waldweg im Herbst, Aquarell", "bild"),
 ("Komponier mir ein Lied über den Montag", "musik"),
 ("Mach nen Song im Stil von Rock über meinen Hund", "musik"),
 ("Schreib und sing mir ein Geburtstagslied für Opa", "musik"),
 ("Ich will einen Popsong über den Sommer, mit Gesang", "musik"),
 ("Kannst du mir ne entspannte Klaviermusik zum Einschlafen machen?", "musik"),
 ("Produzier mir einen Hip-Hop-Beat mit Text über Pizza", "musik"),
 ("Mach mal ein Lied für die Hochzeit meiner Schwester", "musik"),
 ("Komponier was Fröhliches mit Ukulele", "musik"),
 ("Wie funktioniert eine Heizung?", "unklar"),
 ("Wer hat den Kalender erfunden?", "unklar"),
 ("Wer war Goethe?", "unklar"),
 ("Was ist 17 mal 23?", "unklar"),
 ("Erzähl mir nen Witz", "unklar"),
 ("Übersetz mal \"Ich hätte gern einen Kaffee\" ins Französische", "unklar"),
 ("Warum ist der Himmel blau?", "unklar"),
 ("Wie entsteht eigentlich ein Gewitter?", "unklar"),
 ("Was hältst du von Pineapple auf Pizza?", "unklar"),
 ("Wie viele Einwohner hat Brasilien ungefähr, so aus dem Kopf?", "unklar"),
 ("Wie wurde die Glühbirne erfunden?", "unklar"),
 ("Was ist der Unterschied zwischen Wetter und Klima?", "unklar"),
 ("Hallo, wie gehts dir heute?", "unklar"),
 ("Was heißt Eisenbahn auf Englisch?", "unklar"),
 ("Woher kommt das Wort Paket?", "unklar"),
 ("Wie funktioniert eigentlich eine E-Mail technisch?", "unklar"),
 ("Was ist die Wurzel aus 144?", "unklar"),
 ("Warum sind Rollläden eigentlich außen am Fenster?", "unklar"),
 ("Danke dir, das war nett", "unklar"),
 ("Was ist ein gutes Gedicht-Reim auf Sonne?", "unklar"),
 ("Wer hat die Glocke erfunden und wann ungefähr?", "unklar"),
 ("Erklär mir bitte, was Inflation ist", "unklar"),
 ("Was bedeutet das Wort Timer auf Deutsch?", "unklar"),
 ("Soll ich lieber Tee oder Kaffee trinken, was meinst du?", "unklar"),
)


def treffer():
    """(hits, misses as (expected, got, sentence))"""
    hits, misses = 0, []
    for q, want in VERDECKT:
        names = [n for n in intent.classify(q).names if n != "plaudern"]
        hit = not names if want == "unklar" else bool(set(names) & GLEICH.get(want, {want}))
        hits += hit
        if not hit:
            misses.append((want, "+".join(names) or "unklar", q))
    return hits, misses


class Verdeckt(unittest.TestCase):
    def test_the_weiche_keeps_its_hits_on_unseen_sentences(self):
        hits, misses = treffer()
        self.assertGreaterEqual(hits, MIN_TREFFER, f"the Weiche lost hits on sentences nobody tuned for ({hits} of "
                                                   f"{len(VERDECKT)}); fix the rule that changed, never tune on VERDECKT")

    def test_the_set_stays_as_written(self):
        self.assertEqual(len(VERDECKT), 168)
        self.assertEqual(len({q for q, _ in VERDECKT}), len(VERDECKT))
        groups = {g for _, g in VERDECKT} - {"unklar"}
        self.assertEqual(sorted(groups - set(intent.GROUPS)), [], "a group of VERDECKT is gone from intent.GROUPS")


if __name__ == "__main__":
    unittest.main()
