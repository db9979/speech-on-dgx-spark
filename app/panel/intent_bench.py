"""The Weiche's test bench (intent.py): sentence -> expected group ("" = no rule fits, "+" = two at once).

Used by tests/test_intent.py and shown under Funktionen → Weiche („Testsätze“, weiche.py): every reported wrong
turn becomes a line here. The admin's own sentences (chat.route_tests) come on top of these.
"""

BENCH = [
    # Code-Auftrag im Chat (codeauftrag.py): an admin's order for OpenCode, never a question about the Spark's settings
    ("Code-Auftrag: die Begrüßung soll freundlicher klingen", "agent+codeauftrag"),
    ("Ändere am Code die Begrüßung, sie soll freundlicher klingen", "codeauftrag"),
    ("Lass OpenCode die Begrüßung im Code freundlicher machen", "codeauftrag"),
    # Dokumente erstellen (V01.0.415, Dominik 11.10.: only text came back): a file wish is the group "erstellen"
    ("Mach eine Präsentation über die der eine Folie.", "erstellen"),
    ("den mauer fall. gerne auch 3 folien", "erstellen"),
    ("Mach eine Präsentation über den Mauerfall mit 3 Folien", "erstellen"),
    ("Ich brauche eine Präsentation über unseren Urlaub", "erstellen"),
    # what the Spark already made or sent (Dominik 12.10., e62151: „Nein“ from the uploaded documents)
    ("Wurde ein neues Dokument für den reMarkable erstellt?", "dokument+erstellen"),
    # Spark-Tagebuch: what the Spark did itself, never a switching wish
    ("Was hast du heute für mich gemacht?", "erstellen"),
    ("Was hast du gestern im Wohnzimmer eingeschaltet?", "erstellen"),
    ("Ist der Brief fertig?", "erstellen"),
    ("Hast du mir heute was aufs reMarkable geschickt?", "erstellen"),
    ("Schreib mir einen Brief an die Hausverwaltung wegen der Heizung", "erstellen"),
    # Bilder malen (bilder.py): a picture wish, never a document, a search or switching; „Was ist auf dem Bild?“ stays out
    ("Mal mir eine Katze auf einem Skateboard", "bild"),
    ("Kannst du mir ein Bild von einem Leuchtturm malen?", "bild"),
    ("Erstell ein Logo für unseren Fußballverein", "bild"),
    ("Kannst du mir mal ein Bild erstellen von einem Mann im Auto, der durch den Wald fährt?", "bild"),
    ("Kannst du ein Logo für mich entwerfen?", "bild"),
    ("erstelle mir eine witzige karikatur comic stiel.", "bild"),
    ("Mach mir eine Malvorlage mit einem Dinosaurier", "bild"),
    ("Mal mir ein Haus mit Garten", "bild"),
    ("Was ist auf dem Bild?", ""),
    # Musik machen (musik.py): a song to make, never a document or a search
    ("Mach mir ein Lied über unsere Katze", "musik"),
    ("Komponier mir was Ruhiges zum Einschlafen", "musik"),
    ("Kannst du ein Geburtstagslied für mich machen?", "musik"),
    ("Erzeuge eine fröhliche Melodie mit Gitarre", "musik"),
    ("Schreib mir einen Song mit Gesang über den Sommer", "musik"),
    # Musik bearbeiten (musik.py): a change of an own song, never a reminder or a document
    ("Mach mein letztes Lied 30 Sekunden länger", "musik"),
    ("Mach aus meinem Lied eine Reggae-Version", "musik"),
    ("Verlängere das Lied hinten um eine halbe Minute", "musik"),
    ("Kannst du den Song etwas schneller machen?", "musik"),
    # Finden (fund.py, plan such-index): a thing of one's own to find, beside „dokument“ or „mail“; never the internet
    ("Such mir die Rechnung von Thomann vom OP", "dokument+finden"),
    ("Wo ist die Mail vom Vermieter mit der Nebenkostenabrechnung", "finden+mail"),
    ("Finde das Foto vom Strand", "finden"),
    ("Zeig mir den Vertrag mit der Telekom", "dokument+finden"),
    ("Such meine Bestellung bei Thomann", "finden+paket"),
    # Finden Stufe C (fundquellen.py): conversations, appointments, lists, pictures with „such/find“; „Zeig mir meine
    # Termine“ stays with the calendar
    ("Finde das Telegram-Gespräch von letzter Woche", "finden"),
    ("Such den Termin vom OP", "kalender+finden"),
    ("Such meine Baumarkt-Liste", "liste+finden"),
    ("Such mir das Lied über unsere Katze", "finden"),
    ("Zeig mir meine Termine morgen", "kalender"),
    ("Such im Internet nach Thomann", "websuche"),
    ("Wann ist mein OP-Termin", "kalender"),
    ("Lies meine neuen Mails", "mail"),
    # Mappen (mappen.py, plan open-notebook Stufe 1): the own collections by name; a document word keeps „dokument“
    ("Welche Mappen habe ich?", "mappe"),
    ("Was liegt in der Mappe Urlaub?", "mappe"),
    ("Zeig mir die Mappe Auto", "mappe"),
    ("Leg den Mietvertrag in die Mappe Wohnung", "dokument+mappe"),
    ("Which collections do I have?", "mappe"),
    ("Put the lease into the collection Flat", "mappe"),
    # Push 1b: a search within a Mappe keeps document_search (NARROW_KEEP), a finding word also fund_suche
    ("Such in der Mappe Wohnung nach der Kaution", "mappe"),
    ("Finde in der Mappe Wohnung die Rechnung", "finden+mappe"),
    ("Search the collection Flat for the deposit", "mappe"),
    # Hörstück aus einer Mappe (hoerstueck.py): a talk to listen to, beside the Mappe it names
    ("Mach ein Hörstück aus der Mappe Wohnung", "hoerstueck+mappe"),
    ("Mach mir einen Podcast aus der Mappe Wärmepumpe", "hoerstueck+mappe"),
    ("Ich hätte die Mappe Hochzeit gern zum Anhören", "hoerstueck+mappe"),
    ("Make an audio overview of the collection Flat", "hoerstueck+mappe"),
    # Links als Dokument (doklink.py, plan open-notebook Stufe 4): an address and a word of keeping it; „aufs reMarkable“
    # stays the reMarkable, an address alone is no wish to keep it
    ("Speicher https://example.org/artikel als Dokument", "doklink"),
    ("Übernimm https://heise.de/news/artikel in meine Dokumente", "doklink"),
    ("Leg https://a.example/b.pdf und https://c.example zu meinen Dokumenten", "doklink"),
    ("Save https://example.org/article as a document", "doklink"),
    ("Store https://example.org/manual.pdf in my documents", "doklink"),
    # YouTube-Links abschreiben (ytquelle.py, Stufe 3b): a video link to write down goes the same way
    ("Mach eine Abschrift von https://www.youtube.com/watch?v=dQw4w9WgXcQ", "doklink"),
    ("Transkribiere https://youtu.be/dQw4w9WgXcQ", "doklink"),
    ("Transcribe https://youtu.be/dQw4w9WgXcQ", "doklink"),
    ("Schick https://example.org/artikel aufs reMarkable", ""),
    ("Was steht auf https://example.org?", ""),
    # the own Kiwix archive (V01.0.264): mein, dein, im Archiv, never the uploaded documents
    ("Schaue in deinem Archiv nach, was du über Albert Einstein", "archiv"),
    ("Schau in meinem Archiv nach Sauerteig", "archiv"),
    # research, then the answer onto the reMarkable (V01.0.279): the switch stays web search, the panel sends it
    ("Fass die politische Lage zusammen und leg es auf dem reMarkable ab", "websuche"),
    ("Was steht im Archiv über Quasare?", "archiv"),
    ("Durchsuche unser Archiv nach Rom", "archiv"),
    ("Mach das Licht im Wohnzimmer aus", "smarthome"),
    ("Schalte den Fernseher ein", "smarthome"),
    ("Ist das Licht in der Küche noch an?", "smarthome"),
    ("Wie warm ist der Pool?", "smarthome"),
    ("Fahr die Rollläden runter", "smarthome"),
    ("Stell die Heizung im Bad auf 21 Grad", "smarthome"),
    ("Hey Spark, mach das Licht im Flur an", "smarthome"),
    ("Fernseher aus", "smarthome"),
    ("Licht an im Wohnzimmer", "smarthome"),
    ("Kannst du bitte das Licht einschalten?", "smarthome"),
    ("Wie ist die Temperatur im Schlafzimmer?", "smarthome"),
    ("Ist die Garage zu?", "smarthome"),
    ("Starte den Staubsauger", "smarthome"),
    ("Wann war das Licht im Keller zuletzt an?", "smarthome"),
    ("Turn off the light in the kitchen", "smarthome"),
    ("Was habe ich morgen für Termine?", "kalender"),
    ("Trag Zahnarzt am Dienstag um 10 ein", "kalender"),
    ("Was steht heute an?", "kalender"),
    # the briefing as one word (Dominik 20.10. at the phone: no group, the model made up the day)
    ("Gib mir mein Morgenbriefing", "kalender"),
    ("Was ist mein Morgenbriefing?", "kalender"),
    ("Tagesbriefing bitte", "kalender"),
    ("Habe ich heute Abend einen Termin?", "kalender"),
    ("Was steht morgen in meinem Kalender?", "kalender"),
    ("Verschieb den Termin beim Friseur", "kalender"),
    ("Bin ich am Freitag mit Tom verabredet?", "kalender"),
    ("Was hat Sabine morgen?", "kalender"),
    ("Hat Tom am Freitag Zeit?", "kalender"),
    ("Habe ich neue Mails?", "mail"),
    ("Was steht im Posteingang?", "mail"),
    ("Lies mir die letzte Mail vor", "mail"),
    ("Hat mir Tom eine E-Mail geschrieben?", "mail"),
    ("Do I have new e-mails?", "mail"),
    ("Was muss ich diese Woche erledigen?", "mail"),
    ("Wie hat Bayern gespielt?", "websuche"),
    ("Such mal im Internet nach dem Baumarkt in Ettlingen", "websuche"),
    ("Was ist heute politisch los?", "websuche"),
    ("Google mal die Öffnungszeiten vom Hallenbad", "websuche"),
    ("Wer hat die Champions League gewonnen?", "websuche"),
    ("Was gibt es Neues in den Nachrichten?", "websuche"),
    ("Recherchier mal, wie alt Goethe wurde", "websuche"),
    ("Wie ist das Spiel ausgegangen?", "websuche"),
    ("Search the web for DGX Spark", "websuche"),
    ("Erinnere mich in 10 Minuten an den Herd", "erinnerung"),
    ("Stell einen Timer auf 5 Minuten", "erinnerung"),
    ("Welche Erinnerungen habe ich?", "erinnerung"),
    ("Weck mich morgen um sieben", "erinnerung"),
    ("Ruf mich morgen um sieben an", "erinnerung"),
    ("Lösch die Erinnerung für den Müll", "erinnerung"),
    ("Remind me in ten minutes", "erinnerung"),
    ("Setz Milch auf die Einkaufsliste", "liste"),
    ("Was steht auf meiner Einkaufsliste?", "liste"),
    ("Schreib Brot auf die Liste", "liste"),
    ("Nimm Butter von der Einkaufsliste", "liste"),
    ("Was ist auf meiner To-do-Liste?", "liste"),
    ("Setz Schrauben auf die Baumarkt-Liste", "liste"),
    ("Was steht auf der Liste Baumarkt?", "liste"),
    ("Wie wird das Wetter morgen?", "wetter"),
    ("Regnet es heute noch?", "wetter"),
    ("Brauche ich morgen einen Schirm wegen Regen?", "wetter"),
    ("Schneit es am Wochenende?", "wetter"),
    ("Wie warm wird es morgen?", "wetter"),
    ("What's the weather tomorrow?", "wetter"),
    ("Wo ist mein Paket?", "paket"),
    ("Wann kommt die Lieferung von Amazon?", "paket"),
    ("Ist mein Päckchen schon unterwegs?", "paket"),
    ("Wie ist die Telefonnummer von Anna?", "kontakt"),
    ("Wann hat Lisa Geburtstag?", "kontakt"),
    ("Merk dir, dass ich Tee mag", "gedaechtnis"),
    ("Vergiss das mit dem Kaffee", "gedaechtnis"),
    ("Was weißt du über mich?", "gedaechtnis"),
    ("Weißt du noch, was ich dir über den Urlaub erzählt habe?", "gedaechtnis"),
    ("Haben wir schon mal darüber gesprochen?", "gedaechtnis"),
    ("Was steht in meinem Mietvertrag?", "dokument"),
    # since Finden (fund.py): a search in the own things keeps both groups (document_search stays anyway)
    ("Such in meinen Unterlagen nach der Versicherung", "dokument+finden"),
    ("Wie hoch war die Stromrechnung?", "dokument"),
    ("Wann läuft meine Kfz-Versicherung ab?", "dokument"),
    # Quellen-Messbank, step 2 (plan such-index/zuverlaessig.md): reading questions about the own data without a search
    # verb, a parcel word with the own mail, a price in an own paper; fund_suche stays beside every group (NARROW_KEEP)
    ("Was hat mir Thomann wegen der Lieferung geschrieben?", "mail"),
    ("Hat mir der Vermieter zurückgeschrieben?", "mail"),
    ("What did Thomann write to me?", "mail"),
    ("Hat sich der Klempner wegen dem Angebot gemeldet?", "finden"),
    ("Hat sich der Vermieter wegen der Heizung gemeldet?", "finden"),
    ("Was hatte ich bei Thomann bestellt?", "finden"),
    ("Did the plumber get back to me?", "finden"),
    ("Was kostet die Wärmepumpe laut Angebot?", "finden"),
    ("Wie viel kostet die Reparatur laut Rechnung?", "dokument"),
    ("Was schreibt die Hausverwaltung zur Nebenkostenabrechnung?", "dokument"),
    ("Hat mir irgendwer geschrieben?", ""),
    ("Was schreibt die Zeitung zur Wahl?", ""),
    ("Was kostet ein iPhone 17?", "websuche"),
    ("Wo ist die Anleitung für die Waschmaschine?", "dokument"),
    ("Wann ist die Kündigungsfrist für meinen Handyvertrag?", "dokument"),
    # Auswertungen (auswertung.py): the analysis of one own document comes with the documents group
    ("Was sind die Kernaussagen im Mietvertrag?", "dokument"),
    ("Fass mir den Arbeitsvertrag kurz zusammen", "dokument"),
    ("Welche Fristen stehen in der Versicherungspolice?", "dokument"),
    ("Zeig mir das Inhaltsverzeichnis vom Handbuch", "dokument"),
    ("Schreib Anna, dass das Essen fertig ist", "nachricht"),
    ("Schreib Anna, dass ich gleich da bin", "nachricht"),
    ("Sag Lisa, dass das Licht an ist", "nachricht"),
    ("Habe ich neue Nachrichten?", "nachricht"),
    ("Sag allen, dass wir gleich fahren", "nachricht"),
    ("Richte Tom aus, dass ich später komme", "nachricht"),
    ("Durchsage im Wohnzimmer: Essen ist fertig", "nachricht"),
    ("Was machen meine Agenten?", "agent"),
    ("Welche Routinen laufen bei meinem Agenten?", "agent"),
    ("Stell auf meinem iPhone einen Kurzbefehl an", "iphone"),
    # Werkzeug-Abdeckung (Dominik 13.10.: „überprüfe ob es für alle Dienste und Infos Werkzeuge gibt“): these were
    # „unklar“ or went to the wrong group, so route_model lean or a model pick lost the tool
    ("Ist die Haustür zu?", "smarthome"),
    ("Wann ist die Waschmaschine fertig?", "smarthome"),
    ("Wo ist die Anleitung für die Waschmaschine?", "dokument"),
    ("Ruf Mama an", "iphone"),
    ("Navigiere nach Hause", "iphone"),
    ("Ich rufe dich später an", ""),
    ("Hak Milch ab", "liste"),
    ("Was hab ich heute vor?", "kalender"),
    ("Lösch den Zahnarzttermin", "kalender"),
    ("Verschieb den Zahnarzttermin auf Freitag", "kalender"),
    ("Pausiere den Agenten mit dem Wochenbericht", "agent"),
    # Eigene Aufgaben (Dominik 13.10.: „erinnere mich dran, wenn du im Internet eine neue Firmware findest“): a watch,
    # not a search now, a reminder or the Spark's state
    ("Erinnere mich, wenn du im Internet eine neue Firmware für meine FRITZ!Box findest", "agent"),
    ("Sag mir Bescheid, wenn es eine neue Folge von Hard Fork gibt", "agent"),
    ("Melde dich, sobald der Flug nach Rom unter 100 Euro kostet", "agent"),
    ("Behalte den Preis der Bauknecht B6R 88 im Auge", "agent"),
    ("Zeig mir meine Aufträge", "agent"),
    ("Erinnere mich jeden Montag an den Müll", "erinnerung"),
    ("Schreib in die Familiengruppe, dass ich später komme", "nachricht"),
    ("Räum mein Postfach auf", "mail"),
    ("Wann kommt meine Amazon-Bestellung?", "paket"),
    # „Was kannst du mir zu X erzählen?“ is about X, never the Spark-Hilfe (Dominik 2026-10-26, Frauenkirche)
    ("was kannst du mir zur frauenkirche in dresden alles mitteilen. schaue im archiv oder kiwix.", "archiv"),
    ("was kannst du mir zur Frauen kirche in dresden erzählen?", ""),
    ("Schalte die Websuche ein", "spark"),
    # Alle meine Daten herunterladen (meinedaten.py): the way to Ich → Sicherheit → Meine Daten, never documents or memory
    ("Wie lade ich alle meine Daten herunter?", "spark"),
    ("Lade meine Daten herunter", "spark"),
    ("Ich möchte einen Datenexport", "spark"),
    ("How do I download all my data?", "spark"),
    ("Öffne eine Shell auf dem VPS", "spark"),
    ("Wie richte ich den Fernzugang ein?", "spark"),
    ("Mach das Wetter aus", "spark"),
    ("Schalte die Funktion Pakete an", "spark"),
    ("Danke", "plaudern"),
    ("Hallo Spark", "plaudern"),
    ("Guten Abend", "plaudern"),
    ("Tschüss", "plaudern"),
    ("Erzähl mir einen Witz", ""),
    ("Was ist die Hauptstadt von Frankreich?", ""),
    ("Wie viel ist 17 mal 23?", ""),
    ("Wie geht es dir?", ""),
    ("Übersetze 'Haus' ins Englische", ""),
    ("Was ist ein Quark?", ""),
    ("Erklär mir, wie ein Kühlschrank funktioniert", ""),
    ("", ""),
    # „Terminal“ is the terminal client, not an appointment (Weiche-Check 16.10.); the Spark calls the person
    ("Öffne das Terminal", ""),
    ("Mein Arzttermin ist verschoben", "kalender"),
    ("Kannst du mich morgen früh anrufen?", "erinnerung"),
    # P1 Sicherheit (Code-Review 10.11.): a cancel is small talk, never the memory; a negated wish keeps its group for the
    # journal (it is never narrowed, test_sicherheit_sofort); weak search words in a private sentence are no web search
    ("Vergiss es", "plaudern"),
    ("Vergiss es, war nur Spaß", "plaudern"),
    ("Lass es", "plaudern"),
    ("Schon gut", "plaudern"),
    ("Nein, doch nicht", "plaudern"),
    ("Never mind", "plaudern"),
    ("Vergiss, dass ich Tee mag", "gedaechtnis"),
    ("Mach das Licht nicht aus", "smarthome"),
    ("Ruf Mama nicht an", "iphone"),
    ("Wie ist das Ergebnis meiner Blutuntersuchung?", ""),
    ("Gibt es Nachrichten von Tom?", "nachricht"),
    ("Ich habe im Lotto gewonnen", ""),
    ("Wer hat gestern gewonnen?", "websuche"),
    ("Was sind die Schlagzeilen?", "websuche"),
    # P4 Weiche genauer (Code-Review 10.11., D-6/D-9): one normalization step before the rules (umlauts, „ss“, glued
    # device words, a few English phrases); a call for later is a reminder, an emergency number gets no tool
    ("Mach die Wohnzimmerlampe aus", "smarthome"),
    ("Mach den Heizlüfter aus", "smarthome"),
    ("Alles aus", "smarthome"),
    ("Wie hoch ist die Luftfeuchtigkeit?", "smarthome"),
    ("Ist die Haustuer zu?", "smarthome"),
    ("Search the internet for pizza places", "websuche"),
    ("What do you know about me?", "gedaechtnis"),
    ("What are my tasks?", "liste"),
    ("Ruf Tom morgen früh an", "erinnerung"),
    ("Ruf den Notarzt an", "plaudern"),
    ("Wie funktioniert meine Heizung?", "smarthome"),
    ("Rechne 7 mal 8 aus", ""),
]

# Gegenprobe (P4 „Weiche genauer“, review D-13): BENCH and ALLTAG hold almost only sentences that should get a group;
# these measure the other side, sentences that must NOT get one. Measured, never tuned to 100 % (like ALLTAG):
# tests/test_intent.py holds the number of wrong ones (GEGEN_MAX_WRONG) and of wrong ones with a must-call tool
# (GEGEN_MAX_FORCED); both may only go down. Each line: sentence -> what it must not get:
#   ""        no group at all (small talk, a stop or a cancel may be „plaudern“)
#   "wissen"  a knowledge question: none of the acting groups (intent.KNOW_DROP); web search and Wikipedia may stay
#   "pflicht" a negated wish: it may keep its group for the journal, but it is never narrowed and never forces a tool
#             that changes something or goes out (intent.negated, chat.needed)
#   "a+b"     none of these groups
GEGEN = [
    # knowledge with everyday words (D-3)
    ("Was ist eine Lampe?", "wissen"),
    ("Wie funktioniert eine Steckdose?", "wissen"),
    ("Wer hat den Strom erfunden?", "wissen"),
    ("Was bedeutet Klima?", "wissen"),
    ("Wer hat das Fenster erfunden?", "wissen"),
    ("Erzähl mir was über Kameras", "wissen"),
    ("Was ist eine Versicherung?", "wissen"),
    ("Was ist ein Lebenslauf?", "wissen"),
    ("Was ist eine Allergie?", "wissen"),
    ("Was ist ein Agent?", "wissen"),
    ("Wer war James Bond, der Agent?", "wissen"),
    ("Was ist ein Chat-Bot?", "wissen"),
    ("Was ist ein Kontakt in der Elektrotechnik?", "wissen"),
    ("Was ist ein Kalender?", "wissen"),
    ("Was ist eine Anleitung?", "wissen"),
    ("Was ist ein Bescheid?", "wissen"),
    ("Wie funktioniert ein Thermostat?", "wissen"),
    ("Was sind Rollläden?", "wissen"),
    ("Wie funktioniert eine Waschmaschine?", "wissen"),
    ("Wer hat die Glühbirne erfunden?", "wissen"),
    ("Wer hat das Telefon erfunden?", "wissen"),
    ("Erklär mir, wie eine Heizung funktioniert", "wissen"),
    ("Erkläre mir, was ein Saugroboter ist", "wissen"),
    ("Wie funktioniert eine Kamera?", "wissen"),
    ("Was ist eine Garage?", "wissen"),
    ("Was bedeutet Kündigungsfrist?", "wissen"),
    ("Was ist eine Einkaufsliste?", "wissen"),
    ("Wer hat das iPhone erfunden?", "wissen"),
    ("Was ist eine Nachricht?", "wissen"),
    ("Wie funktioniert ein Akku?", "wissen"),
    ("Was sind Routinen?", "wissen"),
    ("Was ist ein Meeting?", "wissen"),
    ("Was ist eine Durchsage?", "wissen"),
    ("Wie funktioniert eine Klimaanlage?", "wissen"),
    ("Was sind Jalousien?", "wissen"),
    ("Wer hat den Fernseher erfunden?", "wissen"),
    ("Erklär mir den Begriff Steckdose", "wissen"),
    ("Was ist ein Garantieschein?", "wissen"),
    ("Wie funktioniert eine Lüftung im Haus?", "wissen"),
    ("Was ist ein Kurzbefehl?", "wissen"),
    ("What is a thermostat?", "wissen"),
    ("How does a heating system work?", "wissen"),
    ("Who invented the light bulb?", "wissen"),
    ("What is a smart home?", "wissen"),
    ("Explain how a camera works", "wissen"),
    ("Klimawandel erklärt", "smarthome"),
    ("Wie schreibe ich eine Kündigung?", "dokument"),
    ("Wie hoch ist die Steuer auf Benzin?", "dokument"),
    ("Remember the Alamo", "gedaechtnis"),
    # a list of things to name, not the own list (D-3: „Liste“ only with an own or place word)
    ("Nenne mir eine Liste von Pflanzen", "liste"),
    ("Liste mir drei Gründe auf", "liste"),
    ("Gib mir eine Liste der größten Städte", "liste"),
    ("Welche Liste der Bestseller ist die bekannteste?", "liste"),
    # small talk and sentences about the person (D-3)
    ("Ich bin gerade in der Küche", "smarthome"),
    ("Schreib ein Gedicht über das Licht", "smarthome"),
    ("Kennst du einen Witz über Lampen?", "smarthome"),
    ("Ich bin im Garten", "smarthome"),
    ("Mir ist langweilig", ""),
    ("Ich bin müde", ""),
    ("Du bist lustig", ""),
    ("Was machst du so?", ""),
    ("Wie war dein Tag?", ""),
    ("Mein Tag war anstrengend", "kalender"),
    ("Was hältst du von Politik?", "websuche"),
    ("Wir haben gewonnen!", ""),
    ("Ich spiele gern Schach", ""),
    ("Erzähl mir eine Geschichte über einen Roboter", ""),
    ("Call it a day", "iphone"),
    # stop and cancel (stoppwort.py, intent.cancel)
    ("Stopp", ""),
    ("Hör auf", ""),
    ("Spark, sei still", ""),
    ("Lass gut sein", ""),
    ("Abbrechen", ""),
    ("Egal", ""),
    ("Schon gut, danke", ""),
    ("Forget it", ""),
    ("Forget about it", ""),
    ("Vergiss das ganze", ""),
    # the call group (D-6): an emergency number and a wish for later never go to the instant call
    ("Ruf die 112 an", "iphone"),
    ("Ruf den Notruf an", "iphone"),
    ("Ruf die Feuerwehr an", "iphone"),
    ("Kannst du Mama anrufen, wenn ich zuhause bin?", "iphone"),
    ("Ruf Papa um 6 an", "iphone"),
    ("Remind me to call mom at 6", "iphone"),
    ("Ruf morgen den Zahnarzt an", "iphone"),
    ("Ruf Oma an, sobald ich im Auto sitze", "iphone"),
    # „Bescheid“ is a notice from an office only with it (D-10), „sag … Bescheid“ a message
    ("Sag Anna Bescheid", "dokument"),
    ("Gib mir Bescheid, wenn du fertig bist", "dokument"),
    # negated wishes (P1): the group may stay, but nothing is narrowed or forced
    ("Mach das Licht aus, nein doch nicht", "pflicht"),
    ("Mach das Licht im Wohnzimmer bloß nicht aus", "pflicht"),
    ("Trag den Termin nicht ein", "pflicht"),
    ("Lösch die Mail nicht", "pflicht"),
    ("Ich will keine Erinnerung", "pflicht"),
    ("Schalte bitte nicht den Fernseher ein", "pflicht"),
    ("Kein Licht bitte", "pflicht"),
    ("Such nicht im Internet nach meiner Diagnose", "pflicht"),
    ("Schick Tom keine Nachricht", "pflicht"),
    ("Setz Milch nicht auf die Einkaufsliste", "pflicht"),
    ("Don't turn off the lights", "pflicht"),
    ("Stell keinen Wecker", "pflicht"),
    ("Navigiere nicht nach Hause", "pflicht"),
]
GEGEN_KINDS = ("wissen", "pflicht")


def must_call(text, route):
    """What the first round has to call for `text` with every group's tool on offer: the named tool (chat.first_tool),
    "required" (chat.needed found some), or "". The same fixed rules as a turn (chat_turn), no model."""
    import chat
    import intent
    offered = sorted({t for tools, _ in intent.GROUPS.values() for t in tools})
    need = chat.needed(text, offered)
    return chat.first_tool(route, need, offered) or ("required" if need else "")


def gegen(classify, rows=None):
    """Every GEGEN sentence through `classify` (text -> intent.Route): {"n", "richtig", "falsch", "erzwungen", "rows",
    "gruppen"}. falsch: it got what it must not get; erzwungen: falsch and the first round must call a tool (the risky
    part, review D-2/D-13); gruppen: {group: how many sentences wrongly got it}."""
    import intent
    import notaus
    import taten
    out = {"n": 0, "richtig": 0, "falsch": 0, "erzwungen": 0, "rows": [], "gruppen": {}}
    for q, rule in (GEGEN if rows is None else rows):
        r = classify(q)
        names = [] if r.names == ["plaudern"] else list(r.names)
        tool = must_call(q, r)
        if rule == "pflicht":
            bad = [] if r.neg and tool not in taten.KIND and tool not in notaus.INTERNET_TOOLS else names or ["eingegrenzt"]
        elif rule == "wissen":
            bad = [n for n in names if n in intent.KNOW_DROP]
        elif rule:
            bad = [n for n in names if n in rule.split("+")]
        else:
            bad = names
        out["n"] += 1
        if not bad:
            out["richtig"] += 1
            continue
        out["falsch"] += 1
        out["erzwungen"] += bool(tool)
        for n in bad:
            out["gruppen"][n] = out["gruppen"].get(n, 0) + 1
        out["rows"].append({"q": q, "rule": rule or "keine", "got": "+".join(names) or "unklar", "must": tool})
    return out


def confusion(classify, rows):
    """soll -> ist per group for (sentence, want) rows (BENCH, ALLTAG): {(want, got): count} of the wrong ones only;
    "–" stands for no group."""
    out = {}
    for q, want in rows:
        r = classify(q)
        got = "+".join(n for n in r.names if n != "plaudern") or "–"
        want = "+".join(w for w in want.split("+") if w and w != "plaudern" and not w.startswith("@")) or "–"
        if set(got.split("+")) != set(want.split("+")):
            out[(want, got)] = out.get((want, got), 0) + 1
    return out


def report(classify=None):
    """The numbers as lines of text: BENCH, ALLTAG, GEGEN, the confusion per group and the wrong GEGEN sentences."""
    import intent
    import intent_alltag
    classify = classify or intent.classify
    lines = []
    bench_ok = sum(1 for q, w in BENCH if set(classify(q).names) == (set(w.split("+")) if w else set()))
    lines.append(f"BENCH   {bench_ok}/{len(BENCH)} richtig")
    a = intent_alltag.measure(classify)
    lines.append(f"ALLTAG  {a['n']} Sätze: richtig {a['richtig']}, geschützt {a['geschuetzt']}, offen {a['offen']}, "
                 f"falsch {a['falsch']}")
    g = gegen(classify)
    lines.append(f"GEGEN   {g['n']} Sätze: richtig {g['richtig']}, falsch {g['falsch']}, falsch erzwungen {g['erzwungen']}")
    lines.append("")
    lines.append("Gegenprobe: falsch vergeben je Gruppe")
    for name, n in sorted(g["gruppen"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {name:<14}{n:>4}")
    for title, rows in (("BENCH", BENCH), ("ALLTAG", intent_alltag.ALLTAG)):
        lines.append("")
        lines.append(f"Verwechslungen {title} (soll -> ist)")
        for (want, got), n in sorted(confusion(classify, rows).items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {want:<22} -> {got:<22}{n:>4}")
    lines.append("")
    lines.append("Gegenprobe: falsche Sätze")
    for row in g["rows"]:
        lines.append(f"  {row['q']!r}: {row['got']} (darf nicht: {row['rule']}){' Pflicht ' + row['must'] if row['must'] else ''}")
    return lines


if __name__ == "__main__":   # cd app && python3 panel/intent_bench.py   (the test configuration, no model, no clock)
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from tests import helpers
    helpers.start()
    sys.stdout.write("\n".join(report()) + "\n")
