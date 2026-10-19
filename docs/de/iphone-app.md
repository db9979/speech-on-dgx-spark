# iPhone-App „Spark“

Eine eigene App fürs iPhone (Quellcode in `ios/`): Knopf drücken, fragen, die Antwort kommt mit der Spark-Stimme, auch bei gesperrtem Bildschirm. „Hey Siri, Frag Spark“ läuft über die App, ohne Kurzbefehl, auch mit AirPods und über Siri im Auto. Seit V01.0.676 hat die App ein eigenes CarPlay-Symbol im Auto (Apple hat die Freigabe erteilt).

## Im Panel einschalten

1. Admin: **Funktionen → iPhone-App** an, speichern.
2. Das gilt sofort für jedes Profil. Einzelne Profile sperrt nur der Admin (**Personen und Geräte → Gesperrte Funktionen**).
3. Wer aus der App Licht und Geräte schalten will: **„Smart Home aus der App“** an. Das Codewort gilt wie überall.
4. Wer das Weckwort und den Ständer-Modus will: **„Dauerhaft zuhören erlauben“** an.
5. Wer Route und Anrufe per Sprache starten will: **„Route und Anrufe auf dem iPhone“** an.
6. Hinweise von selbst (Morgenrunde, Erinnerungen) kommen von Anfang an; abschalten lässt sich das unter **Ich → Von selbst**. Erinnerungen und Timer klingeln als Mitteilung auf dem iPhone, auch wenn die App zu ist.

## App auf das iPhone bringen (am Mac, einmalig etwa 15 Minuten)

1. **Xcode** aus dem Mac App Store installieren (kostenlos) und einmal öffnen.
2. Xcode → **Settings → Accounts → +** → mit deiner Apple-ID anmelden. Ein kostenloses Konto reicht zum Ausprobieren; die App läuft dann 7 Tage und muss danach neu aufgespielt werden. Mit dem Apple Developer Program (99 €/Jahr) läuft sie ein Jahr und geht auch über TestFlight.
3. Das Repo holen: im Terminal `git clone https://github.com/db9979/speech-on-dgx-spark.git` (oder `git pull`, wenn es schon da ist).
4. `ios/Spark.xcodeproj` doppelklicken.
5. Links oben das Projekt **Spark** anklicken → Target **Spark** → **Signing & Capabilities** → bei **Team** dein Konto wählen. Dasselbe beim zweiten Target **SparkNotify** (holt den Text für Push-Meldungen). Meldet Xcode, dass die Bundle-ID schon vergeben ist: Projekt **Spark** (nicht das Target) → **Build Settings** → `APP_BUNDLE_ID` suchen und hinten etwas Eigenes anhängen (z. B. `io.github.db9979.speechspark.dominik`). Beide Targets übernehmen es.
6. iPhone per Kabel anschließen, entsperren, „Diesem Computer vertrauen“ bestätigen.
7. Auf dem iPhone: **Einstellungen → Datenschutz & Sicherheit → Entwicklermodus** an (iPhone startet neu).
8. In Xcode oben in der Mitte dein iPhone als Ziel wählen, dann **▶︎ (Run)** drücken.
9. Beim ersten Start sagt das iPhone „Nicht vertrauenswürdiger Entwickler“: **Einstellungen → Allgemein → VPN und Geräteverwaltung → deine Apple-ID → Vertrauen**. Dann die App öffnen.

## Koppeln

1. Im Panel **Ich → iPhone-App → „iPhone koppeln“**.
2. Am PC: den QR-Code mit der Kamera des iPhones scannen. Auf dem iPhone: **„in der App öffnen“** antippen.
3. Die App fragt „Mit diesem Spark koppeln?“ und zeigt die Adresse. Nur bei deiner eigenen Adresse **Koppeln** tippen.

Der Link gilt 10 Minuten und nur einmal. Die Adresse muss https mit echtem Zertifikat sein (dein Reverse Proxy, z. B. `https://speech.example.de`); das selbst signierte Zertifikat auf Port 31443 nimmt die App nicht an. Öffnest du das Panel zum Koppeln über Port 31443 oder eine IP-Adresse, sagt das Panel das gleich unter dem QR-Code. Nimmt das iPhone das Zertifikat später nicht an, nennt die App im Hinweis „Spark nicht erreichbar“ die Adresse und den Reverse Proxy: Nach einem Umzug des Panels (z. B. auf den Raspberry Pi) muss der Reverse Proxy auf den neuen Rechner zeigen; die App selbst behält ihre Adresse und ihren Schlüssel.

**Mit Einladung** (seit V01.0.276): Öffnet jemand ohne Profil den Einladungs-Link auf dem iPhone und tippt „Lieber gleich in der iPhone-App“ an, legt die App mit Name und PIN das Profil an und ist sofort gekoppelt. Die App zeigt vorher die Adresse des Spark. Eine schon gekoppelte App nimmt keine Einladung an (erst entkoppeln), PIN-Links gehen nur im Browser.

**Mit Prüf-Code** (seit V01.0.754, für Apples Prüfung im App Store): Der Admin schaltet **Funktionen → Prüfzugang für die iPhone-App** an, wählt unter **Personen und Geräte → Prüfzugang für die iPhone-App** ein Profil (am besten ein eigenes wie „App Review“, nie eines mit Admin-Rolle) und tippt „Prüfzugang erstellen“. Das Panel zeigt einmal die https-Adresse und einen Code aus zwölf Buchstaben und Ziffern (`ABCD-EFGH-JKMN`, ohne 0/O und 1/I/L); gespeichert wird nur sein Hash. In der App unter **Mit Prüf-Code verbinden** beides eintippen (Groß- und Kleinschreibung, Leerzeichen und Bindestriche sind egal), die App fragt wie beim Link „Mit diesem Spark koppeln?“. Der Code gilt 14 Tage für höchstens 5 iPhones, höchstens 3 Prüfzugänge gleichzeitig. Falsche Codes zählen wie falsche PINs: Nach mehreren sperrt die Adresse eine Weile. Solange ein Profil einen Prüfzugang hat, sind dafür Smart Home, Mail, Kalender, Kontakte, Anrufe, Chats, Telegram, Aufträge, MCP, Lautsprecher, Raum-Modus, Durchsagen, Telefon, Begleiter, Spark-Update, Meldungen, NAS, Speicher und reMarkable gesperrt, egal was sonst an ist. Löschen des Prüfzugangs entfernt die damit gekoppelten iPhones sofort; nach 14 Tagen geschieht das von selbst.

**Ohne Spark ansehen** (seit V01.0.754): Unten auf dem Kopplungs-Bildschirm zeigt die App eine Vorführung mit Beispielen, ohne Kopplung und ohne Netz. Geschriebene Fragen beantwortet die App selbst mit festen Beispielen, Sprechen geht dort nicht (die Spracherkennung läuft auf dem Spark). **Vorführung beenden** oben links führt zurück zum Koppeln.

## Benutzen

- Oben das Gesicht des Assistenten, dasselbe wie im Panel (Roboter, Comic oder Comic (Frau); seit V01.0.521 wählst du es selbst ganz oben unter Einstellungen → *Gesicht* in der App oder im Panel unter Ich → Gespräch, sonst gilt die Vorgabe des Admins; die App übernimmt es beim Öffnen und nach der Wahl, mit dem nächsten TestFlight-Build): es blinzelt, schaut umher, hört mit roter Antenne zu, denkt mit kreisendem Bogen und bewegt beim Sprechen den Mund. Antippen ist wie der Knopf. Ist im Panel „Gesicht zeigt, was es tut“ an (V01.0.323), zeigt das Gesicht in der App dasselbe wie im Panel: Lupe beim Suchen, Kalenderblatt, Brief, Glühbirne beim Smart Home, Notizblock beim Merken, Denkblasen, Haken mit Zwinkern nach einer erledigten Aktion, Fragezeichen bei einem Fehler und „zzz“ nach 5 Minuten Ruhe. Ausgelöst nur von den Ereignissen des Spark, nie vom Text der Antwort.
- Großer Knopf: tippen, sprechen, die App merkt selbst, wann du fertig bist (oder nochmal tippen). Während der Spark spricht, hält Tippen ihn an.
- Unten kann man die Frage auch schreiben. Oben links beginnt ein neues Gespräch; nach 10 Minuten Pause beginnt es von selbst neu.
- „Hey Siri, Frag Spark“ (oder „Hey Siri, Spark fragen“): Siri fragt nach der Frage und liest die Antwort vor.

In der App unter **Einstellungen (Zahnrad)**:

| Schalter | Was er tut |
|---|---|
| Freihändig | Nach jeder Antwort hört die App wieder zu (ihr Signalton und Klicks zählen nicht als Frage, siehe „Stille wird nie zu Wörtern“ in assistent.md). 8 Sekunden Stille: Mikrofon aus. Seit V01.0.272 ein Wert deines Profils: Browser und App zeigen denselben (wie „Ins Wort fallen“). |
| Ins Wort fallen | Einfach losreden hält die Antwort an und hört zu. Das iPhone filtert die eigene Spark-Stimme aus dem Mikrofon. |
| Antworten vorlesen | Aus: Antworten nur als Text. Der Schalter gehört zum Profil (wie im Browser, alle Geräte). „Auf diesem iPhone vorlesen“ gilt nur für dieses iPhone. In CarPlay spricht die App immer (seit V01.0.409). |
| Weckwort | „Hey Spark“, „Jarvis“ oder „Computer“. Das iPhone erkennt das Wort selbst, ohne Internet und ohne Apple-Server; erst danach geht etwas an deinen Spark. Kann das iPhone kein Deutsch ohne Internet, bleibt es aus (Einstellungen → Allgemein → Tastatur → Diktat). |
| Am Akku | Wie lange das Weckwort am Akku nach der letzten Nutzung zuhört (nur am Ladekabel, 30 Minuten, 1 oder 3 Stunden). Am Ladekabel immer. Standard seit V01.0.668: nur am Ladekabel (Akku). |
| Ständer-Modus | Am Ladekabel: großes Gesicht, Uhr, letzte Antwort, Bildschirm bleibt an, nachts gedimmt. |
| Von selbst sprechen | Hinweise des Spark sagt die App laut, solange sie offen ist. |

Route und Anrufe: „Navigiere zur Arbeit“ oder „Ruf Anna an“. Die App fragt jedes Mal „Route nach … öffnen?“ oder „Anna anrufen (Nummer)?“. Erst „Ja“ (getippt oder gesagt) öffnet Karten oder ruft an. Kontakte sucht nur das iPhone; die Nummer geht nicht an den Spark. Gibt es mehrere passende Kontakte, fragt die App nach dem ganzen Namen.

## Schnellstart, Verlauf, Fotos, ohne Netz

- **Schnellstart:** „Spark zuhören“ öffnet die App und sie hört sofort zu. Auf dem Action-Button: iPhone-Einstellungen → Action-Button → Kurzbefehl → „Spark zuhören“. Im Kontrollzentrum (ab iOS 18) über „Steuerelement hinzufügen“, auf dem Sperrbildschirm als Widget. Per Siri: „Hey Siri, Spark zuhören“.
- **Verlauf:** Das Uhr-Symbol oben links zeigt deine früheren Gespräche, dieselbe Liste wie das Protokoll im Panel. Antippen setzt das Gespräch fort. Gespräche aus der App landen auch dort. Löschen geht nur im Panel.
- **Heute** (seit V01.0.286): Die Sonne oben rechts zeigt, was heute dran ist, wie *Ich → Heute* im Panel: nächste Termine von heute und morgen, offene Erinnerungen, ungelesene Nachrichten, Dokumente, gemerkte Fakten. Nur Karten der Funktionen, die dein Profil nutzen darf; zum Aktualisieren nach unten ziehen.
- **Foto oder Dokument fragen:** Die Büroklammer neben dem Eingabefeld: Foto aufnehmen, Foto auswählen oder Dokument (PDF, Text, Bild). Das iPhone liest den Text selbst, auch von gescannten Seiten. An den Spark geht nur der Text. Der Anhang gilt für das Gespräch, bis du ihn mit ✕ entfernst. **Fotos ansehen lassen:** Ist unter Ich → iPhone-App „Fotos aus der App ansehen lassen“ an (dazu der Admin-Schalter für Bilder), geht bei Fotos das Bild selbst an den Spark, verkleinert auf 1280 px. Er erkennt dann auch Dinge, Pflanzen oder eine Fehleranzeige. Rückfragen zum selben Foto gehen 10 Minuten lang. Ist das aus, liest das iPhone wie bisher nur den Text. PDFs und Dokumente bleiben immer beim Text.
- **Bei „Meine Sachen“ speichern:** Ist Eigene Dokumente für dein Profil freigegeben, zeigt der Anhang einen Knopf dafür. Dann findet der Spark das Dokument auch später, wie ein Upload im Panel. Einen eigenen Profilschalter dafür gibt es seit V01.0.723 nicht mehr.
- **Ohne Netz:** Ist der Spark nicht erreichbar, zeigt die App das oben an. Geschriebene Fragen warten (höchstens 10, einen Tag lang) und gehen raus, sobald der Spark wieder da ist. Sprechen geht dann nicht, weil der Spark die Sprache erkennt.
- **Ruhig, nichts springt** (seit V01.0.570): Der Hinweis „Spark nicht erreichbar“ kommt erst nach 3 Sekunden ohne Spark, ein kurzer Netzwechsel oder der Neustart beim Update lässt ihn nicht blinken. Kommen Nachrichten von einem anderen Gerät dazu, hängt die App nur die neuen an; der Verlauf baut sich nicht neu auf. Eine offene Seite unter Einstellungen bleibt offen, auch wenn der Admin sie gerade sperrt (mit Hinweis oben; Zurück schließt sie). Monitoring und Prüfen zeigen einen Fehler erst beim zweiten Fehlversuch und unten in der Liste, Zeilen in Logs und Hinweisen behalten ihren Platz. Beim Ladekabel bleibt der Verlauf hinter der Ständer-Ansicht stehen.
- **Letzter Stand sofort da** (seit V01.0.748, Funktion „Apps merken sich den letzten Stand“): Verlauf, Chats, Mein Profil, Einstellungen und „Im Panel öffnen“ zeigen beim Öffnen sofort den Stand vom letzten Mal, oben mit „Stand 16:05 · wird aktualisiert …“, bis der Spark geantwortet hat (dann verschwindet der Hinweis, oder er sagt „Spark gerade nicht erreichbar“). Gemerkt werden die 20 neuesten Gespräche mit je 50 Nachrichten, die Chat-Liste und die letzte Seite von bis zu 20 Chats, die eigenen Einstellungen und Funktionen und die Zahlen auf den Kacheln von „Meine Sachen“ (nur wie viele, kein Name); private Chats und Chats mit „Nachrichten verschwinden“ nie. Ohne gemerkten Stand zeigt die Seite graue Platzhalter, nach einer Sekunde „Verbinde mit dem Spark …“, nach 8 Sekunden „Das dauert länger als sonst …“ und bei einem Fehler „Noch einmal“. Kommt die App nach vorne, holt sie Verlauf, Chats und Einstellungen einmal im Hintergrund (höchstens alle 5 Minuten). Braucht eine Seite länger als 2 Sekunden, steht unter Zustand → Logs (Bereich Apps) eine Zeile `app: langsam <Seite> <ms> ms iphone`.
- **Akku schonen** (seit V01.0.668): Im Hintergrund stoppt die App ihre Audio-Engine, sobald nichts mehr zuhört, spricht oder telefoniert; eine laufende Antwort spricht sie noch zu Ende. So kann iOS die App schlafen legen. Ausnahmen: das Weckwort hört zu (am Ladekabel oder die Zeit unter „Am Akku“) oder CarPlay läuft.
- **Englisch:** Steht das iPhone auf Englisch, ist die App englisch, auch das Weckwort und Siri („Ask Spark“, „Start Spark“).
- **Lange Fragen** (seit V01.0.829): Das Eingabefeld wächst bis fünf Zeilen mit, darüber scrollt es. Die Zeilentaste macht eine neue Zeile, der Pfeil schickt ab. Ab vier Zeilen öffnet ⤢ oben rechts im Feld die Großansicht über den ganzen Bildschirm: *Fertig* übernimmt den Text ins Feld, *Senden* schickt ab.

## Mein Profil

In der App unter Einstellungen → **Mein Profil** stellst du dieselben Werte ein wie im Panel, Änderungen gelten sofort auf beiden Seiten:

- **Stimme:** Stimme und Sprechtempo, mit „Probehören“.
- **Antworten:** Antwortlänge. Deine Wünsche zum Ton werden nur angezeigt; ändern geht im Panel, weil sie dem Sprachmodell gesagt werden.
- **Von selbst:** an/aus, Ruhezeit, höchstens so viele Hinweise am Tag, Termine mit Vorlauf, Wetter mit Ort und Uhrzeit, Pakete, Geburtstage, Bus und Bahn, Begrüßung, Mails, Morgenrunde mit Uhrzeit. Erscheint nur, wenn der Admin „Von selbst“ eingeschaltet hat. Themen, deren Dienst im Profil aus ist, sind ausgegraut.
- **Was die App darf:** nur Anzeige. Ändern im Panel unter Ich → iPhone-App.

## Erinnerungen, Teilen, Kurzbefehle

- **Apple Erinnerungen:** Mit dem Schalter „Apple Erinnerungen auf dem iPhone“ (Ich → iPhone-App, aus) fragt die App nach jeder Erinnerung des Spark „… auch in die Erinnerungen-App eintragen?“. Nach „Ja“ steht sie in der Liste „Spark“, ohne eigenen Alarm (der Spark klingelt schon). Sagt der Spark eine Erinnerung ab, verschwindet sie dort auch. Neue Einträge der Einkaufs- und Aufgabenliste holt die App beim Öffnen in die Listen „Einkauf“ und „Aufgaben“ (jeder Eintrag einmal). Liegt eine Liste in einem CalDAV-Konto, bleibt sie dort.
- **Teilen → Spark:** In Safari, Mail, Dateien oder Fotos auf Teilen → Spark. Text, Webseite (die lädt das iPhone selbst), PDF oder Foto: Das iPhone liest den Text (ein Foto geht als Bild, wenn „Fotos aus der App ansehen lassen“ an ist), dann fragst du dazu („Fass das kurz zusammen“) oder legst ihn unter „Meine Dokumente“ ab (mit dem Dokumente-Schalter). Die Antwort lässt sich teilen, z. B. als Notiz.
- **Kurzbefehle:** In der Kurzbefehle-App gibt es „Spark fragen“, „Erinnerung beim Spark“, „Auf die Liste beim Spark“ und „Dokument beim Spark ablegen“. Für die Liste braucht es den Erinnerungen-Schalter, für Dokumente den Dokumente-Schalter.
- **Notizen:** Apple lässt Apps nicht direkt in die Notizen-App schreiben. Zwei Wege: eine Antwort in der App lange drücken → „Teilen (z. B. als Notiz)“, oder ein Kurzbefehl aus „Spark fragen“ und Apples „Notiz erstellen“ (die Antwort von „Spark fragen“ als Text der Notiz).

## Panel-Bereiche in der App

Die App übernimmt das Panel Stück für Stück (Plan „iPhone-App übernimmt das Panel“). Dafür schaltet der Admin unter Funktionen „Panel-Bereiche in der iPhone-App“ ein; das gilt sofort für jedes Profil mit gekoppeltem iPhone, einzelne Profile sperrt nur der Admin (Personen und Geräte → Gesperrte Funktionen). Die früheren Schalter je Bereich unter Ich → iPhone-App gibt es seit dem App-Gleichstand (Dominik 2026-10-14) nicht mehr. Alles ist zuerst aus, Gäste bekommen nichts davon. Die App selbst kann keinen Bereich einschalten.

- **Im Panel öffnen** (Einstellungen): Alles, was die App noch nicht selbst zeigt, öffnet das Panel hier in der App an der richtigen Stelle (beim ersten Mal meldest du dich an wie im Browser). Die Liste zeigt jede Seite von Ich, die dein Profil gerade nutzen kann, auch reMarkable, Speicher, Schreibhilfe, Begleiter und MCP; sie kommt vom Spark (`/api/features`, Liste `pages` aus `features.ME_PAGES`), eine neue Seite steht also ohne App-Update drin. Nur Überblick, Los geht's, Anmelden und Android-App fehlen mit Grund (`features.APP_SKIP`). Mit „Spark verwalten“ auch Monitoring, Logs, Funktionen und Profile.
- **Funktionen und Personen und Geräte unter Spark verwalten** (seit V01.0.276): Die Namen und Gruppen der Schalter kommen vom Spark, die App hat keine eigene Liste mehr. Ein Profil zeigt zusätzlich seine Funktionen „n von m an“ zum Schalten, seine Admin-Rolle und die angemeldeten Browser (Wischen meldet ab).
- **Mein Alltag**: die nächsten Termine aus deinen Kalendern und die Erinnerungen des Spark (wischen zum Löschen). Unter Mein Profil kommen die Gesprächsschalter dazu: aus Gesprächen lernen, jeden Tag neues Gespräch und, wenn der Admin sie erlaubt, aus Korrekturen lernen, bei Werkzeugen nachdenken und gezielte Werkzeugwahl. Das Gedächtnis steht seit V01.0.723 unter Meine Sachen.
- **Spark verwalten** (nur für Profile mit Rolle Admin oder Verwalter): Nach Face ID gilt die App so, wie dein Profil angemeldet ist, ohne eigene Admin-Anmeldung (seit V01.0.541). Der App-Schlüssel zählt nur, wenn er nach dem Einschalten deines zweiten Anmeldeschritts angelegt wurde; das Panel-Passwort geht nur im Browser. Darin: **Monitoring** („Braucht dich“, Speicher, CPU/GPU, Dienste), **Logs** (Diagnose wie im Panel mit Bereichen und Zeitraum, „Kopieren für Thread“ und Teilen) und **Prüfen** (Funktionsprüfung, Qualitätstest, Vorrang prüfen). Unter **Ändern**: **Funktionen** (die einfachen Ein/Aus-Schalter; heikle wie „Port“, zweiter Anmeldeschritt für Profile und die iPhone-Schalter selbst bleiben im Browser), **Personen und Geräte** (Profil anlegen, Geräte entfernen, neue PIN, zweiten Schritt zurücksetzen, Profil löschen; Code nur bei „Schutz ändern“) und **Sicherungen** (jetzt sichern; alte löschen nur als Admin; Zurückspielen und Herunterladen im Browser). Ein Verwalter sieht nur Monitoring, Logs und Personen und Geräte; dort hebt er Sperren eines Profils auf, schaltet aber keine Funktion und sperrt nichts (das macht nur der Admin, seit V01.0.551).
- **Stimme einlernen**: Die App zeigt drei Sätze, du liest sie vor, gespeichert wird mit dem Code aus der Authenticator-App. Darunter „Anlernen“ für jeden deiner Lautsprecher (der Lautsprecher fragt dann nach fünf Sätzen). Braucht die Sprechererkennung vom Admin und den zweiten Anmeldeschritt deines Profils.
- **Von selbst**: Wetter-Ort, Pakete aus E-Mails, Bus und Bahn (Haltestelle suchen und setzen), deine Aufträge ansehen und stoppen, Raum-Modus „+30 Min.“ (höchstens vier Stunden ab jetzt). Die Schalter Wetter, Pakete, Bus und Bahn, Aufträge gibt es hier auch.
- **Sicherheit**: deine Geräte (wischen zum Entfernen), letzte Anmeldungen, überall abmelden, zweiten Schritt ausschalten oder neue Wiederherstellungscodes (mit Code). Einrichten geht nur im Browser mit PIN: sonst könnte jemand mit deinem entsperrten iPhone allein einen eigenen zweiten Schritt setzen.
- **Konten verbinden**: E-Mail, Kalender, Kontakte, Smart Home und Telegram. Nur mit dem zweiten Anmeldeschritt deines Profils und frischem Code. Der Spark prüft die Verbindung, speichert Passwort oder Token verschlüsselt und gibt es nie heraus; das iPhone behält es nicht.

## Meine Sachen

Seit V01.0.723 (Dominik 2026-10-17, Plan `app-meine-sachen/plan.md`) liegt alles, was der Spark für dich aufhebt, auf einer Seite: das Symbol mit den vier Kästchen oben links neben dem Gespräch oder Einstellungen → **Meine Sachen**. Kacheln mit Anzahl zeigen Dokumente, Vom Spark erstellt, Bilder, Musik und Gedächtnis, darunter „Zuletzt dazugekommen“. Die Suche oben geht über alles: Titel, Dateinamen, Absender, Tags, Bildwünsche, Lieder und gemerkte Fakten (sie läuft auf dem iPhone, an den Spark geht dabei nichts).

Jede Kachel richtet sich nur nach der Freigabe ihrer Funktion durch den Admin (Eigene Dokumente, Dokumente erstellen, Bilder malen, Musik machen, Gedächtnis), ohne Profilschalter und ohne den Schalter „Panel-Bereiche in der iPhone-App“. Sperrt der Admin eine Funktion für dein Profil, verschwindet ihre Kachel, und der App-Schlüssel erreicht ihre Pfade nicht mehr (`iphone.THINGS`). Gäste bekommen nichts davon.

- **Dokumente:** eine Zeile pro Dokument mit Titel aus dem Steckbrief, darunter Art, Absender und Quelle, rechts Datum und ein Schild nur, wenn etwas wichtig ist (Frist, wird gelesen, nicht lesbar, für alle, Suche aus). Schnellfilter mit Anzahl (Alle, Frist offen, Wird gelesen, Für alle, Suche aus, Nicht lesbar), dazu Sortieren (Neueste, Name, Frist, Größe), Quelle und Tag im Filter-Menü; die App merkt sich Sortierung und Quelle. Bei „Neueste zuerst“ stehen die Dokumente in Gruppen: Diese Woche, Diesen Monat, Älter. Die Suche findet Titel, Absender und Tags sofort, Enter sucht zusätzlich im Inhalt („Im Inhalt gefunden“). „Auswählen“ markiert mehrere: Löschen (mit Rückfrage), Für alle, Nur für mich, Durchsuchen an oder aus, Neu einlesen (höchstens 20), über `POST /api/profile/wissen/batch`. Ein Tippen öffnet die Seite des Dokuments: Steckbrief, „Original und Text“ (ein aufbewahrtes PDF oder Bild in Apples Vorschau, daneben der gespeicherte Text, lange Texte stückweise mit „Weiterlesen“), Tags antippen zum Entfernen und neue dazuschreiben, „Assistent sucht darin“, „Für alle“, an die Frist erinnern, Neu einlesen und Löschen. Unten „Schalter für Dokumente“ mit den Schaltern von Ich → Dokumente, soweit der Admin sie erlaubt, und „Ausgelassene Ordner“ (seit V01.0.778): die Liste der Ordner und Namen, die der Spark nie liest, mit „Wieder zulassen“, Namensregeln hinzufügen (mit Rückfrage, wie viele Dokumente die Suche verlassen) und per Wischen entfernen; einen einzelnen Ordner auslassen geht im Ordnerbaum im Panel.
- **Wissensbuch** (seit V01.0.787, Plan *wissensbuch* Stufe E, nur wenn der Admin das Wissensbuch freigegeben hat): unter Dokumente die Zeile „Wissensbuch“ mit den Seiten nach Art, oben Widersprüche („Stimmt“ behält einen Wert) und veraltete Sätze („Stimmt noch“, „Stimmt nicht“). Eine Seite zeigt jeden Satz mit seiner Quelle; nach links wischen ist „Stimmt nicht“. „Als Obsidian-Ordner laden“ holt das Buch als ZIP zum Teilen. Im Gespräch steht unter einer Antwort aus mindestens zwei Quellen „Ins Wissensbuch“; erst dein Tippen legt sie ab. Neu schreiben und Seiten löschen gehen im Panel unter Ich → Dokumente → Wissensbuch. Android zeigt das alles über die Panel-Ansicht.
- **Vom Spark erstellt:** die Dokumente, die der Spark gemacht hat, wie bisher.
- **Bilder:** alle gemalten Bilder als Raster, ein Tippen zeigt eines groß mit Wunsch und Zeit, Teilen und Löschen. Oben ein Feld „Was soll ich malen?“; solange gemalt wird, schaut die App alle 4 Sekunden nach. Ändern, Schnellknöpfe und eigene Fotos gehen weiter im Panel unter Ich → Bilder.
- **Musik:** alle Lieder nach Tag gruppiert wie im Panel (Heute, Gestern, Letzte 7 Tage, Älter), mit Abspielen direkt in der App, Länge, mit oder ohne Gesang, Uhrzeit oder Tag, wischen zum Löschen. Oben „Was für Musik?“ mit der Länge zur Wahl (dieselben Längen wie die Chips im Panel, bis zur Grenze des Admins) macht ein Stück ohne Gesang; Gesang und eigener Liedtext gehen im Panel unter Ich → Musik.
- **Gedächtnis:** alle gemerkten Fakten mit Suche, „aus einem Gespräch gelernt“ oder „selbst gesagt“ mit Datum. Wischen zum Ändern oder Löschen, „Auswählen“ löscht mehrere, „Aufräumen vorschlagen“ fragt das Sprachmodell nach doppelten Einträgen, erst nach deinem „Übernehmen“ ändert sich etwas. Alles auf einmal vergessen geht weiter nur im Browser.

**Kalender und E-Mail** (seit V01.0.815, Plan `kalender-mail/plan.md` Stufe 4): Oben in Meine Sachen stehen „Kalender“ und „E-Mail“, wenn der Admin die Funktion für dich freigegeben hat (Kalender, E-Mail lesen; ohne den Panel-Schalter). Der Kalender zeigt die Termine von vier Wochen ab dieser Woche nach Tagen, in der Farbe ihres Kalenders; „+“ legt einen Termin an, ein Tippen zeigt ihn mit „Ändern“ und „Löschen“ (nur in eigenen CalDAV-Kalendern, nie bei wiederholten oder geteilten Terminen, die Regeln prüft der Spark wie auf der Seite). E-Mail zeigt den Posteingang aller Postfächer (die 50 neuesten), ein Tippen die Mail als reinen Text (sie bleibt ungelesen); mit „Mails ordnen“ darunter Gelesen/Ungelesen, Archivieren und Verschieben, mit „Mails senden“ „Antworten“ und oben „Neue Mail“, beides mit dem Vorschau-Blatt des Spark, gesendet wird nur mit „Senden“ dort. Mit „Apps merken sich den letzten Stand“ bleiben die Termine der vier Wochen, die Mail-Liste (Absender, Betreff, Zeit) und bis zu 20 zuletzt geöffnete Mails mit Text auf dem iPhone; ist die Funktion aus, löscht die App sie beim nächsten Öffnen, beim Entkoppeln und bei einem anderen Profil sofort.

**Kalender und E-Mail wie im Panel** (V01.0.830, Dominik 2026-10-19 „a“): Der Kalender hat oben „Schnell eintragen“: eine Zeile wie „Morgen 15 Uhr Zahnarzt bei Dr. Weiß“, der Spark liest sie mit festen Regeln und zeigt Titel, Tag, Uhrzeit und Ort; erst „Eintragen“ speichert, in deinen ersten eigenen Kalender. Ein Termin hat neben „Ändern“ und „Löschen“ jetzt „+1 Tag“ und „+1 Woche“, danach „Rückgängig“, solange das Blatt offen ist. E-Mail zeigt die Liste nach Tagen (Heute, Gestern, …) mit dem Kürzel des Absenders; mit „Mails ordnen“ wischt du nach links zum Archivieren und nach rechts für Gelesen oder Ungelesen. Unter einer Mail legt „Als Termin“ mit dem Betreff eine Zeile für Schnell eintragen an. Teilen von Kalendern bleibt aus Sicherheitsgründen im Browser (Kalender → Einstellungen), wie die Verbindung der Konten.

## Nachrichten an andere Profile

Geschrieben wird in Chats (Knopf oben rechts, wenn Chats an sind). Seit V01.0.488 gibt es in der App kein eigenes Nachrichten-Fenster und keine Mitteilung mit Antwortfeld mehr; neue Chat-Nachrichten kommen als „💬 Name“ und öffnen die App. Mit Siri: „Nachricht mit Spark“. Siri fragt nach Empfänger und Text und vor dem Senden noch einmal nach; die Nachricht landet im Chat mit dieser Person, „alle“ in der Gruppe „Alle“. Der Name muss zu einem Profil passen, das deine Nachrichten annimmt (Name oder Rufname). Passen mehrere, fragt Siri „Wen meinst du?“ mit höchstens 4 Namen; bei einem unbekannten Namen nennt sie höchstens 3 ähnliche. Die Heute-Karte „Chats“ zählt ungelesene Chat-Nachrichten. Wer dir schreiben darf, stellst du im Browser ein (Ich → Gespräch → Chats). Braucht den nächsten TestFlight-Build.

Seit V01.0.654 können die Chats in der App so viel wie im Panel: Änderungen kommen sofort (über dieselbe Verbindung wie die Chats-Seite, nur solange die Chats offen sind und die App vorn ist; sonst kommen die Mitteilungen wie bisher), oben steht „schreibt …“. Lange auf eine Nachricht drücken: **Reagieren** (👍 ❤️ 😂 😮 😢 🙏, noch einmal tippen nimmt sie weg), **Antworten** (mit Zitat, Tippen aufs Zitat springt hin), **Kopieren**, **Ändern** (15 Minuten) und **Für alle zurücknehmen** (1 Stunde). Weiter oben „Ältere Nachrichten“, Trennlinien pro Tag, ✓ gesendet, ✓✓ zugestellt, blaue ✓✓ gelesen. Mit ✎ oben links ein neuer Chat oder eine **neue Gruppe** (wenn Gruppen-Chats an sind; du bist ihr Admin). Das Suchfeld über der Liste sucht in deinen Chats. Ein Tippen auf den Namen oben öffnet die **Chat-Infos**: Stumm (1 Stunde, 8 Stunden, immer), Nachrichten verschwinden (24 Stunden, 7 oder 90 Tage; in Gruppen nur die Admins), bei Gruppen Name, Mitglieder (nach links wischen: zum Admin machen oder entfernen), Personen hinzufügen, Chat für mich leeren und Gruppe verlassen. Es gelten dieselben Regeln und Grenzen wie im Panel; die App kann nichts, was das Profil im Browser nicht auch darf.

**Private Chats (Ende-zu-Ende)** seit V01.0.654: Sind sie an (Funktionen → Chats → „Private Chats (Ende-zu-Ende)“), steht beim neuen Chat der Schalter „Privat (Ende-zu-Ende)“. Beim ersten Mal tippst du „Dieses iPhone eintragen“: Das iPhone macht seinen eigenen Schlüssel im Secure Enclave (er verlässt das iPhone nie), der Spark bekommt nur die öffentliche Hälfte; mit zweitem Anmeldeschritt fragt die App nach dem Code. Texte, Fotos (vorher neu gezeichnet, ohne Ort und Kameradaten) und Dateien verschlüsselt das iPhone selbst, genau wie Browser und Android-App. Unter den Chat-Infos stehen die Sicherheitsnummer zum Vergleichen und „Deine Geräte“ (nach links wischen: entfernen). Hast du schon ein anderes Gerät, wartet das iPhone auf den Verlauf und zeigt einen Code; auf dem älteren Gerät „Übertragen“ tippen, wenn dort derselbe Code steht. Umgekehrt zeigt die App oben in den Chats „🔒 Neues Gerät“ mit Code, „Übertragen“ und „Nicht ich“. Beim Entkoppeln löscht die App ihren Schlüssel.

## Anrufe und Videoanrufe

Seit V01.0.652 telefoniert die App selbst: Im Chat zu zweit auf diesem Spark stehen oben 📞 und 🎥. Kommt ein Anruf, klingelt das iPhone wie bei einem normalen Anruf, auch gesperrt und bei geschlossener App (Apples Anruf-Bildschirm mit „Spark“). Im Gespräch: Stumm, Kamera aus, Kamera wechseln, Lautsprecher, Auflegen. Der Anruf steht danach im Chat („📞 Anruf · 3:12“, „Verpasster Anruf“, „Anruf abgelehnt“); in die Anrufliste der Telefon-App kommt er bewusst nicht. Ist die App offen, klingelt sie auch ohne Apples VoIP-Push (seit V01.0.705): Sie hört die Nachrichten des Spark selbst mit. Es gelten dieselben festen Regeln wie im Browser (nur wer Nachrichten von dir annimmt, nicht in der Ruhezeit, 45 Sekunden Klingeln); das andere Ende kann ein Browser, die Android-App oder ein iPhone sein. Nimmt ein anderes Gerät desselben Profils ab, hört das iPhone auf zu klingeln.

Mit **Anrufe per Assistent** (V01.0.803) startet „Ruf Sabine an“ und das „Ja“ im Assistenten der App den Anruf gleich über Apples Anruf-Fenster. Hat man vom Lautsprecher oder Telefon aus angerufen, fragt die App beim Öffnen „Sabine anrufen?“. „Ruf Mama übers Telefon an“ geht wie bisher über die iPhone-Kontakte.

Braucht: **Funktionen → Chats → Anrufe (Sprache und Video)** (Admin, von unterwegs zusätzlich „Anrufe von unterwegs“) und **Push an die iPhone-App** (sonst klingelt es nur bei offener App), außerdem den nächsten TestFlight-Build. Beim ersten Anruf fragt das iPhone nach Mikrofon und Kamera.

## Wo gerade zugehört wird (Raum-Modus)

Ab V01.0.209 zeigt die App, wenn ein Gerät deines Profils im Raum-Modus zuhört (Browser oder Lautsprecher). Einschalten im Panel unter Ich → iPhone-App → „Raum-Modus in der App zeigen“ (aus, braucht den Raum-Modus vom Admin). Oben im Chat steht dann „● Küche hört zu bis 21:30“ mit „Beenden“, bei mehreren Geräten eine Zeile zum Aufklappen. Die App fragt beim Öffnen, bei der Rückkehr und alle 30 Sekunden nach. Auf dem Sperrbildschirm und in der Dynamic Island erscheint eine Live-Aktivität mit Restzeit und „Beenden“ (abschalten in den iPhone-Einstellungen → Spark → Live-Aktivitäten). Sie wird nur aktualisiert, solange die App läuft; nach der Endzeit steht dort „vorbei“, bis die App wieder nachsieht. Das Widget „Raum-Modus“ (Home- und Sperrbildschirm) zeigt „Küche hört zu bis 21:30“ oder „Niemand hört zu“. Per Siri: „Raummodus beenden mit Spark“. Die App kann nur beenden, nie starten; sie sieht nur wo und bis wann, nie was gehört wurde.

## Spark-Update aus der App

Für ausgewählte Profile, standardmäßig aus. Einschalten als Admin: **Funktionen → Spark-Update über die iPhone-App**, darunter pro Profil:

- **Hinweise:** Liegt eine neue Version mit grünen GitHub-Tests bereit, kommt eine Mitteilung aufs iPhone („V… ist geprüft und bereit (3 Änderungen)“), pro Version einmal und nicht in der Ruhezeit des Profils. Braucht „Push an die iPhone-App“.
- **Starten:** In der App unter **Einstellungen → Spark-Version** steht „Jetzt aktualisieren“. Bestätigt wird mit Face ID (oder dem iPhone-Code) und einem frischen Code aus der Authenticator-App des Profils. Darum lässt sich „Starten“ nur für Profile mit zweitem Anmeldeschritt anhaken.

Die Seite zeigt die installierte und die neue Version mit der Liste der Änderungen. Das Update läuft wie im Panel: erst eine Sicherung, dann update.sh, das nur grün getestete Stände installiert. Die App zeigt den Fortschritt, während der Spark neu startet „Spark startet neu …“, am Ende die neue Version. Höchstens ein Start aus der App alle 10 Minuten. Die anderen Profile mit Hinweisen erfahren, wer gestartet hat. Zurück zur alten Version geht nur im Panel unter **Zustand → System/Update**.

## Push-Meldungen bei geschlossener App

Braucht das Apple Developer Program. Einmalig:

1. developer.apple.com → **Certificates, IDs & Profiles → Keys → +** → Name z. B. „Spark Push“, **Apple Push Notifications service (APNs)** anhaken → **Continue → Register → Download**. Die `.p8`-Datei gibt es nur dieses eine Mal; gut aufheben. Die **Key ID** steht daneben, die **Team ID** unter **Membership**.
2. Panel als Admin: **Funktionen → Push an die iPhone-App** an. Darunter `.p8`, Key ID, Team ID und die Bundle-ID der App eintragen. **Art der App**: „Entwicklung“, solange du die App direkt aus Xcode aufspielst, „Produktion“ für TestFlight und App Store. Speichern.
3. Profil: nichts zu tun, „Meldungen aufs iPhone“ ist von Anfang an an. Abschalten lässt es sich unter **Ich → iPhone-App → „Meldungen aufs iPhone“**.
4. App einmal öffnen und Mitteilungen erlauben. Dann im Panel **„Test-Meldung schicken“**.

Was dann kommt: Erinnerungen und Timer (auch die im Panel oder am Lautsprecher gesetzten), Morgenrunde, Hinweise von selbst, Gedächtnis-Aufräumen. Über Apple geht nur „Neue Nachricht vom Spark“; der Text bleibt 24 Stunden auf dem Spark, die App holt ihn mit ihrem Schlüssel und zeigt ihn im Banner. Ist der Spark gerade nicht erreichbar, bleibt es bei „Neue Nachricht“. Mit Push klingeln Erinnerungen nicht mehr doppelt (die App legt dann keine eigenen Wecker mehr an). Höchstens 30 Meldungen pro Stunde und Profil.

Test sagt **BadDeviceToken**: „Entwicklung“ und „Produktion“ vertauscht. **InvalidProviderToken**: Key ID oder Team ID passen nicht zum Schlüssel. **TopicDisallowed**: Bundle-ID passt nicht.

## CarPlay

Ein eigenes Symbol „Spark“ im Auto. Antippen → **„Mit Spark sprechen“** → losreden. Das Gespräch geht freihändig weiter, bis 15 Sekunden lang keine Stimme mehr kommt; Ins-Wort-Fallen geht wie in der App. Im Auto zählt auch eine leisere Stimme über dem Fahrgeräusch, und erst 1,6 Sekunden Pause beenden eine Frage, damit Spark nicht mitten im Satz abbricht (seit V01.0.734). Das Auto zeigt nur „Ich höre zu“, „Denke nach“, „Spark spricht“, nie Text, dazu das Gesicht deines Profils (Roboter oder Comic, wie in der App), passend zum Zustand als Standbild; startet nur das Auto die App, fragt sie den Spark gleich selbst nach dem Gesicht (seit V01.0.676; bewegte Bilder erlaubt Apple in CarPlay nicht). Antworten sind im Auto kurz. Smart Home im Auto nur mit dem eigenen Schalter **„Smart Home auch im Auto“** (zusätzlich zu „Smart Home aus der App“) und Codewort. Route und Anruf nur nach „Ja“. Hinweise von selbst sagt die App im Auto laut. Ein eigenes Weckwort im Auto erlaubt Apple nicht; „Hey Siri, Frag Spark“ geht weiter.

**Freigabe von Apple:** Apple hat die CarPlay-Kategorie „Voice-based conversational app“ erteilt, sie ist für die App-ID `io.github.db9979.speechspark` unter developer.apple.com → Identifiers → Additional Capabilities angehakt (**CarPlay Voice Based Conversation**), und `ios/Spark.entitlements` enthält seit V01.0.676 `com.apple.developer.carplay-voice-based-conversation`. Der TestFlight-Build holt das passende Profil selbst. Fehlt der Haken bei der App-ID, scheitert die Signatur des Builds.

Erscheint das Symbol nicht: iPhone → Einstellungen → Allgemein → CarPlay → dein Auto → **Anpassen**, dort Spark hinzufügen.

Ausprobieren ohne Auto: Xcode → **Open Developer Tool → Simulator**, dort **I/O → External Displays → CarPlay**.

**Termine und Mails vorlesen** (seit V01.0.815): Mit Kalender oder E-Mail lesen freigegeben stehen im Auto zusätzlich „Termine vorlesen“ und „Neue Mails vorlesen“. Ein Tippen stellt dem Assistenten die Frage („Was steht heute und morgen an?“, „Habe ich neue Mails?“), die Antwort kommt gesprochen; das Auto zeigt dabei wie immer keinen Text.

## Veröffentlichen

Schritt für Schritt (TestFlight für dich und die Familie, App Store): [iphone-veroeffentlichen.md](iphone-veroeffentlichen.md).

## Sicherheit

- Jedes iPhone bekommt beim Koppeln einen eigenen Schlüssel. Er liegt nur im Schlüsselbund dieses iPhones und auf dem Spark nur als Hash.
- Der Schlüssel darf nur fragen und hören (Chat, Spracherkennung, Siri-Frage). Einstellungen, Gedächtnis, Geräte, Verbindungen und weitere Kopplungen gehen damit nicht.
- Sperrt der Admin ein Profil (Personen und Geräte → Gesperrte Funktionen), sind sofort alle iPhones dieses Profils gesperrt, der Admin-Schalter sperrt alle. Ein verlorenes iPhone unter **Ich → iPhone-App → Entfernen**.
- Smart Home aus der App nur mit eigenem Schalter und Codewort. Was die App als Absender angibt, zählt nicht; das Panel entscheidet am Schlüssel.
- Weckwort, Ständer-Modus, Route und Anrufe nur mit eigenem Schalter im Panel. Der Spark schlägt Route und Anruf nur vor, das Werkzeug gibt es nur für den App-Schlüssel mit Schalter; starten tut erst dein „Ja“ auf dem iPhone. Ein Hinweis von außen (Mail, Webseite) kann keine Route und keinen Anruf auslösen.
- Vor dem Weckwort geht kein Ton an den Spark. Im Hintergrund hört die App nur mit eingeschaltetem Weckwort zu.
- Push: Der Apple-Schlüssel (.p8) liegt verschlüsselt auf dem Spark, ändern nur als Admin mit zweitem Anmeldeschritt, er wird nie wieder angezeigt. Apple bekommt nur einen festen Satz und eine Zufallsnummer. Die Push-Adresse meldet nur die App mit ihrem eigenen Schlüssel an; ein entferntes iPhone bekommt sofort nichts mehr. Den Text einer Meldung bekommt nur die App des eigenen Profils.
- Fotos und Dokumente: Den Text liest das iPhone, an den Spark geht nur Text (höchstens 20 000 Zeichen pro Frage). Fotos gehen nur mit dem Schalter „Fotos aus der App ansehen lassen“ als Bild. In einer Runde mit Bild bietet der Spark keine Werkzeuge an, und das Bild kommt nicht in den Verlauf. Der Spark behandelt ihn wie Text von außen: Er steht als Daten im Prompt, nicht im Gespräch, und sperrt Aktionen wie nach einer Mail. Im Verlauf steht nur der Name des Anhangs.
- Dokumente ablegen nur mit eigenem Schalter, nur mit dem App-Schlüssel, höchstens 10 pro Minute und 3 MB. Lesen oder löschen kann die App die Dokumente nicht.
- „Mein Profil“ ändert nur eine feste Liste (Stimme, Tempo, Länge, Von selbst, Morgenrunde). Rechte der App, Telegram, Smart Home und der Ton lassen sich darüber nicht ändern; eine Anfrage mit einem anderen Feld wird ganz abgelehnt.
- Apple Erinnerungen: nur mit eigenem Schalter, nur nach „Ja“ auf dem iPhone. Aus den Erinnerungen liest die App nichts für den Spark. Kurzbefehle dürfen nur Einträge auf die Listen setzen, die Listen-Einstellungen bleiben im Panel.
- Teilen: Der geteilte Inhalt ist Text von außen (sperrt Aktionen), höchstens 20 000 Zeichen pro Frage; Webseiten lädt das iPhone selbst, höchstens 3 MB.
- Wartende Fragen liegen nur auf dem iPhone und werden beim Entkoppeln gelöscht.
- Letzter Stand (Admin-Schalter `chat.app_cache`, in der Grundausstattung an, sperrbar je Profil): Die App merkt sich nur, solange `GET /api/iphone/hello` „keep“ sagt; sagt der Spark nein, löscht sie alles sofort. Die Dateien liegen im eigenen Speicher der App mit Datenschutz „vollständig“ (gesperrt unlesbar), nie in der iCloud- oder Computer-Sicherung, in einem Ordner je Kopplung (sein Name ist ein Hash aus Adresse und Schlüssel, nie der Schlüssel). Entkoppeln, eine neue Kopplung und ein anderes Profil löschen alles. Nie gemerkt: Schlüssel, Codes, „Spark verwalten“, private und verschwindende Chats, Dateien und Bilder. Gemerkte Rechte schalten nichts ein (Mikrofon, Push, Anrufe, Apple Erinnerungen warten auf die Antwort des Spark).
- Spark-Update: Rechte vergibt nur der Admin (mit seinem Code, wenn der zweite Schritt an ist), ein Profil kann sie sich nicht selbst geben. Starten nur mit dem App-Schlüssel, Face ID und einem frischen 6-stelligen Code des Profils (jeder Code einmal, falsche Codes zählen zur Sperre), höchstens einmal in 10 Minuten. Die App kann keine Version wählen; installiert wird nur, was die GitHub-Tests bestanden hat. Jeder Start steht im Sicherheitsprotokoll. Das Sprachmodell hat kein Werkzeug dafür.
- CarPlay macht nichts lockerer: Im Auto ist Smart Home ohne den eigenen Auto-Schalter gesperrt, auch wenn die App es sonst darf.
- Anrufe: Ton und Bild gehen verschlüsselt (DTLS-SRTP) direkt zwischen den Geräten oder über den eigenen Vermittler des Sparks, nie über Apple. Apple bekommt beim Klingeln nur eine Zufallsnummer, Name und Art holt die App mit ihrem Schlüssel vom Spark. Der App-Schlüssel erreicht nur die Anruf-Wege (Start, Annehmen, Signal, Ende, Info, ICE), und nur für Anrufe, an denen sein Profil beteiligt ist. Das Sprachmodell kann keinen Anruf starten.
- Private Chats: Der Schlüssel des iPhones liegt im Secure Enclave und verlässt es nie; der Spark sieht nur verschlüsselte Nachrichten. Ein neuer Schlüssel braucht den Code des zweiten Schritts, wie ein neues Gerät.
- Koppeln nur aus der eigenen Browser-Anmeldung, mit dem zweiten Anmeldeschritt, wenn das Profil ihn hat. Höchstens 5 iPhones pro Profil.

## Was der Spark dafür anbietet

| Weg | Wozu |
|---|---|
| `POST /api/profile/iphone/pair` | Browser-Anmeldung: einmaliger Kopplungs-Link (`spark-app://pair?url=…&code=…`) mit QR-Code |
| `POST /api/iphone/pair` | App: Code gegen eigenen Schlüssel tauschen (10 pro Minute und Adresse) |
| `GET /api/iphone/hello` | App: prüft den Schlüssel, nennt Profil, Sprache und was das Profil erlaubt |
| `POST /api/app/langsam` | App: eine Seite brauchte länger als 2 s (feste Seitenwörter und Millisekunden, eine Logzeile; 6 pro Minute) |
| `GET /api/profile/reminders` | App: Erinnerungen und Timer des Profils, damit sie auf dem iPhone klingeln |
| `GET /api/proactive`, `POST /api/proactive/greet` | App: Hinweise von selbst |
| `POST /api/assistant/say` | App: Hinweise mit der Spark-Stimme sprechen |
| `POST /api/test/asr`, `POST /api/chat`, `POST /api/siri/ask` | Fragen und Antworten wie im Browser und bei Siri |
| `DELETE /api/profile/iphone/{id}` | Browser-Anmeldung: iPhone entfernen |
| `POST /api/iphone/push-token` | App: ihre Push-Adresse anmelden (nur mit dem App-Schlüssel), `kind` `alert` oder `voip` (Klingeln) |
| `GET /api/chats/stream` | App: Chat-Ereignisse live, darunter die Anruf-Signale |
| `GET/POST /api/chats/keys`, `POST /api/chats/keys/remove\|private`, `GET/POST /api/chats/share`, `POST /api/chats/share/done` | App: eigener Schlüssel für private Chats, privaten Chat beginnen, Verlauf an ein neues Gerät |
| `POST /api/anrufe/start\|answer\|signal\|end`, `GET /api/anrufe/ice\|info` | App: Anruf starten, annehmen, Signale tauschen, beenden; Zugang zum Vermittler; wer anruft |
| `GET /api/iphone/note?id=…` | App (Mitteilungs-Erweiterung): Text einer Push-Meldung holen |
| `POST /api/profile/iphone/push-test` | Browser-Anmeldung: Test-Meldung an die eigenen iPhones |
| `GET/PUT /api/profile/convos` | App: Verlauf lesen und das laufende Gespräch speichern (Löschen nur im Panel) |
| `GET/PUT /api/iphone/settings` | App: „Mein Profil“, nur die Felder aus `iphone.APP_FIELDS` |
| `GET /api/assistant/voices` | App: Stimmen zur Auswahl |
| `POST /api/tasks/inbox`, `POST /api/profile/tasks/einkauf\|aufgaben` | App: neue Listeneinträge holen, Einträge aus Kurzbefehlen setzen (nur mit `app_ios`) |
| `POST /api/iphone/doc` | App: Text eines Dokuments zu den eigenen Dokumenten (nur mit Eigene Dokumente) |
| `GET /api/profile/wissen`, `PUT /api/profile/wissen/{id}`, `POST /api/profile/wissen/{id}/reread\|remind`, `POST /api/profile/wissen/batch\|search`, `DELETE /api/profile/docs/{id}`, `GET\|POST\|DELETE /api/profile/auslassen` | App, Meine Sachen → Dokumente (nur mit Eigene Dokumente) |
| `GET /api/profile/memory`, `PUT\|DELETE /api/profile/memory/{id}`, `POST /api/profile/memory/tidy\|forget` | App, Meine Sachen → Gedächtnis (nur mit Gedächtnis) |
| `GET\|POST\|DELETE /api/bilder`, `GET /api/bilder/job/{id}`, `GET /api/bilder/{id}/datei`, `DELETE /api/bilder/{id}` | App, Meine Sachen → Bilder (nur mit Bilder malen) |
| `GET\|POST\|DELETE /api/musik`, `GET /api/musik/job/{id}`, `GET /api/musik/{id}/datei`, `DELETE /api/musik/{id}` | App, Meine Sachen → Musik (nur mit Musik machen) |
| `GET /api/iphone/update` | App: installierte und neue geprüfte Version, Änderungen, Fortschritt (nur mit Recht vom Admin) |
| `POST /api/iphone/update` | App: Update starten, Header `X-Speech-Code` mit frischem Code (nur mit Recht „Starten“) |
| `GET /api/admin/iphone-update`, `PUT /api/admin/iphone-update/{id}` | Admin: wer Hinweise bekommt und wer starten darf |
| `GET/PUT/DELETE /api/admin/apns` | Admin: Apple-Schlüssel (PUT und DELETE mit zweitem Schritt) |

Jeder Push, der `ios/` ändert, baut die App auf GitHub für den Simulator (`.github/workflows/ios.yml`), damit Fehler dort auffallen und nicht erst in Xcode.
