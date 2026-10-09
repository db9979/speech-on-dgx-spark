# iPhone-App „Spark“

Eine eigene App fürs iPhone (Quellcode in `ios/`): Knopf drücken, fragen, die Antwort kommt mit der Spark-Stimme, auch bei gesperrtem Bildschirm. „Hey Siri, Frag Spark“ läuft über die App, ohne Kurzbefehl, auch mit AirPods und über Siri im Auto. CarPlay als eigenes Symbol im Auto ist geplant (`plaene/ios-carplay.md`, Weg 3) und braucht eine Freigabe von Apple.

## Im Panel einschalten

1. Admin: **Einstellungen → Funktionen → iPhone-App** an, speichern.
2. Profil: **Ich → iPhone-App → „iPhone-App für mich“** an.
3. Wer aus der App Licht und Geräte schalten will: **„Smart Home aus der App“** an. Das Codewort gilt wie überall.
4. Wer das Weckwort und den Ständer-Modus will: **„Dauerhaft zuhören erlauben“** an.
5. Wer Route und Anrufe per Sprache starten will: **„Route und Anrufe auf dem iPhone“** an.
6. Hinweise von selbst (Morgenrunde, Erinnerungen) kommen, wenn für das Profil **„Von selbst“** an ist. Erinnerungen und Timer klingeln als Mitteilung auf dem iPhone, auch wenn die App zu ist.

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

Der Link gilt 10 Minuten und nur einmal. Die Adresse muss https mit echtem Zertifikat sein (dein Reverse Proxy, z. B. `https://speech.example.de`); das selbst signierte Zertifikat auf Port 31443 nimmt die App nicht an.

## Benutzen

- Oben das Gesicht des Assistenten, dasselbe wie im Panel (Roboter oder Comic, der Admin wählt es unter Einstellungen → Vorgaben; die App übernimmt es beim Öffnen): es blinzelt, schaut umher, hört mit roter Antenne zu, denkt mit kreisendem Bogen und bewegt beim Sprechen den Mund. Antippen ist wie der Knopf.
- Großer Knopf: tippen, sprechen, die App merkt selbst, wann du fertig bist (oder nochmal tippen). Während der Spark spricht, hält Tippen ihn an.
- Unten kann man die Frage auch schreiben. Oben links beginnt ein neues Gespräch; nach 10 Minuten Pause beginnt es von selbst neu.
- „Hey Siri, Frag Spark“ (oder „Hey Siri, Spark fragen“): Siri fragt nach der Frage und liest die Antwort vor.

In der App unter **Einstellungen (Zahnrad)**:

| Schalter | Was er tut |
|---|---|
| Freihändig | Nach jeder Antwort hört die App wieder zu. 8 Sekunden Stille: Mikrofon aus. |
| Ins Wort fallen | Einfach losreden hält die Antwort an und hört zu. Das iPhone filtert die eigene Spark-Stimme aus dem Mikrofon. |
| Weckwort | „Hey Spark“, „Jarvis“ oder „Computer“. Das iPhone erkennt das Wort selbst, ohne Internet und ohne Apple-Server; erst danach geht etwas an deinen Spark. Kann das iPhone kein Deutsch ohne Internet, bleibt es aus (Einstellungen → Allgemein → Tastatur → Diktat). |
| Am Akku | Wie lange das Weckwort am Akku nach der letzten Nutzung zuhört (nur am Ladekabel, 30 Minuten, 1 oder 3 Stunden). Am Ladekabel immer. |
| Ständer-Modus | Am Ladekabel: großes Gesicht, Uhr, letzte Antwort, Bildschirm bleibt an, nachts gedimmt. |
| Von selbst sprechen | Hinweise des Spark sagt die App laut, solange sie offen ist. |

Route und Anrufe: „Navigiere zur Arbeit“ oder „Ruf Anna an“. Die App fragt jedes Mal „Route nach … öffnen?“ oder „Anna anrufen (Nummer)?“. Erst „Ja“ (getippt oder gesagt) öffnet Karten oder ruft an. Kontakte sucht nur das iPhone; die Nummer geht nicht an den Spark. Gibt es mehrere passende Kontakte, fragt die App nach dem ganzen Namen.

## Schnellstart, Verlauf, Fotos, ohne Netz

- **Schnellstart:** „Spark zuhören“ öffnet die App und sie hört sofort zu. Auf dem Action-Button: iPhone-Einstellungen → Action-Button → Kurzbefehl → „Spark zuhören“. Im Kontrollzentrum (ab iOS 18) über „Steuerelement hinzufügen“, auf dem Sperrbildschirm als Widget. Per Siri: „Hey Siri, Spark zuhören“.
- **Verlauf:** Das Uhr-Symbol oben links zeigt deine früheren Gespräche, dieselbe Liste wie das Protokoll im Panel. Antippen setzt das Gespräch fort. Gespräche aus der App landen auch dort. Löschen geht nur im Panel.
- **Foto oder Dokument fragen:** Die Büroklammer neben dem Eingabefeld: Foto aufnehmen, Foto auswählen oder Dokument (PDF, Text, Bild). Das iPhone liest den Text selbst, auch von gescannten Seiten. An den Spark geht nur der Text. Der Anhang gilt für das Gespräch, bis du ihn mit ✕ entfernst. **Fotos ansehen lassen:** Ist unter Ich → iPhone-App „Fotos aus der App ansehen lassen“ an (dazu der Admin-Schalter für Bilder und der Profilschalter), geht bei Fotos das Bild selbst an den Spark, verkleinert auf 1280 px. Er erkennt dann auch Dinge, Pflanzen oder eine Fehleranzeige. Rückfragen zum selben Foto gehen 10 Minuten lang. Ist das aus, liest das iPhone wie bisher nur den Text. PDFs und Dokumente bleiben immer beim Text.
- **In „Meine Dokumente“ speichern:** Ist im Panel unter Ich → iPhone-App „Dokumente aus der App ablegen“ an, zeigt der Anhang einen Knopf dafür. Dann findet der Spark das Dokument auch später, wie ein Upload im Panel.
- **Ohne Netz:** Ist der Spark nicht erreichbar, zeigt die App das oben an. Geschriebene Fragen warten (höchstens 10, einen Tag lang) und gehen raus, sobald der Spark wieder da ist. Sprechen geht dann nicht, weil der Spark die Sprache erkennt.
- **Englisch:** Steht das iPhone auf Englisch, ist die App englisch, auch das Weckwort und Siri („Ask Spark“, „Start Spark“).

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

## Meine Dokumente ansehen

Mit „Dokumente aus der App“ (Ich → iPhone-App) steht unter Einstellungen → **Meine Dokumente** die Liste deiner Dokumente auf dem Spark, mit Suche. Ein Tippen öffnet eines: Ist das Original aufbewahrt und ein PDF oder Bild, zeigt es Apples Vorschau (zoomen, suchen, teilen), daneben gibt es den Reiter „Text“ mit dem Text, den der Spark gespeichert hat. Andere Dateiarten zeigt die App nur als Text. Löschen und Hochladen gehen weiter im Panel.

## Nachrichten an andere Profile

Der Umschlag neben dem Eingabefeld öffnet die Nachrichten, mit Punkt bei neuen. Das geht ohne Sprachmodell. Unter „Bereit?“ siehst du, ob der Admin und dein Profil Nachrichten erlauben und wen du erreichst. Wer nicht erreichbar ist, steht mit Grund dabei, z. B. „hat Nachrichten aus“. Dort wählst du den Empfänger und schreibst (höchstens 500 Zeichen). Im Eingang wischst du nach rechts zum Antworten und nach links zum Löschen. Kommt eine Nachricht als Mitteilung, antwortest du direkt darin: lange drücken → „Antworten“. Wer dir schreiben darf, stellst du nur im Browser ein. Die App liest Nachrichten nicht von selbst vor. Frag dafür den Assistenten („Habe ich Nachrichten?“), das geht auch im Auto. Sprachnachrichten zeigt die App nur an, anhören kannst du sie im Panel. Mit Siri: „Nachricht mit Spark“. Siri fragt nach Empfänger und Text und vor dem Senden noch einmal nach. Der Name muss zu einem Profil passen, das deine Nachrichten annimmt. Bei vielen Profilen (V01.0.206) öffnet „An“ eine Liste mit Suche (Name oder Rufname), oben ★ Favoriten und Zuletzt; der Stern merkt einen Favoriten auf dem Spark. „Bereit?“ zeigt dann nur Zahlen, die Namen zum Aufklappen. Passen bei Siri mehrere Profile, fragt Siri „Wen meinst du?“ mit höchstens 4 Namen; bei einem unbekannten Namen nennt sie höchstens 3 ähnliche.

## Wo gerade zugehört wird (Raum-Modus)

Ab V01.0.209 zeigt die App, wenn ein Gerät deines Profils im Raum-Modus zuhört (Browser oder Lautsprecher). Einschalten im Panel unter Ich → iPhone-App → „Raum-Modus in der App zeigen“ (aus, braucht den Raum-Modus vom Admin). Oben im Chat steht dann „● Küche hört zu bis 21:30“ mit „Beenden“, bei mehreren Geräten eine Zeile zum Aufklappen. Die App fragt beim Öffnen, bei der Rückkehr und alle 30 Sekunden nach. Auf dem Sperrbildschirm und in der Dynamic Island erscheint eine Live-Aktivität mit Restzeit und „Beenden“ (abschalten in den iPhone-Einstellungen → Spark → Live-Aktivitäten). Sie wird nur aktualisiert, solange die App läuft; nach der Endzeit steht dort „vorbei“, bis die App wieder nachsieht. Das Widget „Raum-Modus“ (Home- und Sperrbildschirm) zeigt „Küche hört zu bis 21:30“ oder „Niemand hört zu“. Per Siri: „Raummodus beenden mit Spark“. Die App kann nur beenden, nie starten; sie sieht nur wo und bis wann, nie was gehört wurde.

## Spark-Update aus der App

Für ausgewählte Profile, standardmäßig aus. Einschalten als Admin: **Einstellungen → Funktionen → Spark-Update über die iPhone-App**, darunter pro Profil:

- **Hinweise:** Liegt eine neue Version mit grünen GitHub-Tests bereit, kommt eine Mitteilung aufs iPhone („V… ist geprüft und bereit (3 Änderungen)“), pro Version einmal und nicht in der Ruhezeit des Profils. Braucht „Push an die iPhone-App“.
- **Starten:** In der App unter **Einstellungen → Spark-Version** steht „Jetzt aktualisieren“. Bestätigt wird mit Face ID (oder dem iPhone-Code) und einem frischen Code aus der Authenticator-App des Profils. Darum lässt sich „Starten“ nur für Profile mit zweitem Anmeldeschritt anhaken.

Die Seite zeigt die installierte und die neue Version mit der Liste der Änderungen. Das Update läuft wie im Panel: erst eine Sicherung, dann update.sh, das nur grün getestete Stände installiert. Die App zeigt den Fortschritt, während der Spark neu startet „Spark startet neu …“, am Ende die neue Version. Höchstens ein Start aus der App alle 10 Minuten. Die anderen Profile mit Hinweisen erfahren, wer gestartet hat. Zurück zur alten Version geht nur im Panel unter **Zustand → System/Update**.

## Push-Meldungen bei geschlossener App

Braucht das Apple Developer Program. Einmalig:

1. developer.apple.com → **Certificates, IDs & Profiles → Keys → +** → Name z. B. „Spark Push“, **Apple Push Notifications service (APNs)** anhaken → **Continue → Register → Download**. Die `.p8`-Datei gibt es nur dieses eine Mal; gut aufheben. Die **Key ID** steht daneben, die **Team ID** unter **Membership**.
2. Panel als Admin: **Einstellungen → Funktionen → Push an die iPhone-App** an. Darunter `.p8`, Key ID, Team ID und die Bundle-ID der App eintragen. **Art der App**: „Entwicklung“, solange du die App direkt aus Xcode aufspielst, „Produktion“ für TestFlight und App Store. Speichern.
3. Profil: **Ich → iPhone-App → „Meldungen aufs iPhone“** an.
4. App einmal öffnen und Mitteilungen erlauben. Dann im Panel **„Test-Meldung schicken“**.

Was dann kommt: Erinnerungen und Timer (auch die im Panel oder am Lautsprecher gesetzten), Morgenrunde, Hinweise von selbst, Gedächtnis-Aufräumen. Über Apple geht nur „Neue Nachricht vom Spark“; der Text bleibt 24 Stunden auf dem Spark, die App holt ihn mit ihrem Schlüssel und zeigt ihn im Banner. Ist der Spark gerade nicht erreichbar, bleibt es bei „Neue Nachricht“. Mit Push klingeln Erinnerungen nicht mehr doppelt (die App legt dann keine eigenen Wecker mehr an). Höchstens 30 Meldungen pro Stunde und Profil.

Test sagt **BadDeviceToken**: „Entwicklung“ und „Produktion“ vertauscht. **InvalidProviderToken**: Key ID oder Team ID passen nicht zum Schlüssel. **TopicDisallowed**: Bundle-ID passt nicht.

## CarPlay

Ein eigenes Symbol „Spark“ im Auto. Antippen → **„Mit Spark sprechen“** → losreden. Das Gespräch geht freihändig weiter, bis 8 Sekunden lang nichts kommt; Ins-Wort-Fallen geht wie in der App. Das Auto zeigt nur „Ich höre zu“, „Denke nach“, „Spark spricht“, nie Text. Antworten sind im Auto kurz. Smart Home im Auto nur mit dem eigenen Schalter **„Smart Home auch im Auto“** (zusätzlich zu „Smart Home aus der App“) und Codewort. Route und Anruf nur nach „Ja“. Hinweise von selbst sagt die App im Auto laut. Ein eigenes Weckwort im Auto erlaubt Apple nicht; „Hey Siri, Frag Spark“ geht weiter.

**Apple muss CarPlay freigeben**, sonst erscheint das Symbol nicht:

1. developer.apple.com/contact/carplay → Kategorie **„Voice-based conversational app“** beantragen. Apple prüft jeden Antrag; das dauert Tage bis Wochen.
2. Nach der Zusage: developer.apple.com → **Identifiers** → die App-ID → **Additional Capabilities / CarPlay** die Freigabe anhaken.
3. In `ios/Spark.entitlements` diese zwei Zeilen innerhalb von `<dict>` ergänzen und die App neu aufspielen:
   ```xml
   <key>com.apple.developer.carplay-voice-based-conversation</key>
   <true/>
   ```
   (Vorher nicht eintragen: ohne Freigabe kann Xcode die App sonst nicht signieren.)

Nach der Freigabe ausprobieren ohne Auto: Xcode → **Open Developer Tool → Simulator**, dort **I/O → External Displays → CarPlay**.

## Veröffentlichen

Schritt für Schritt (TestFlight für dich und die Familie, App Store): [iphone-veroeffentlichen.md](iphone-veroeffentlichen.md).

## Sicherheit

- Jedes iPhone bekommt beim Koppeln einen eigenen Schlüssel. Er liegt nur im Schlüsselbund dieses iPhones und auf dem Spark nur als Hash.
- Der Schlüssel darf nur fragen und hören (Chat, Spracherkennung, Siri-Frage). Einstellungen, Gedächtnis, Geräte, Verbindungen und weitere Kopplungen gehen damit nicht.
- Der eigene Schalter aus sperrt sofort alle iPhones des Profils, der Admin-Schalter alle. Ein verlorenes iPhone unter **Ich → iPhone-App → Entfernen**.
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
- Spark-Update: Rechte vergibt nur der Admin (mit seinem Code, wenn der zweite Schritt an ist), ein Profil kann sie sich nicht selbst geben. Starten nur mit dem App-Schlüssel, Face ID und einem frischen 6-stelligen Code des Profils (jeder Code einmal, falsche Codes zählen zur Sperre), höchstens einmal in 10 Minuten. Die App kann keine Version wählen; installiert wird nur, was die GitHub-Tests bestanden hat. Jeder Start steht im Sicherheitsprotokoll. Das Sprachmodell hat kein Werkzeug dafür.
- CarPlay macht nichts lockerer: Im Auto ist Smart Home ohne den eigenen Auto-Schalter gesperrt, auch wenn die App es sonst darf.
- Koppeln nur aus der eigenen Browser-Anmeldung, mit dem zweiten Anmeldeschritt, wenn das Profil ihn hat. Höchstens 5 iPhones pro Profil.

## Was der Spark dafür anbietet

| Weg | Wozu |
|---|---|
| `POST /api/profile/iphone/pair` | Browser-Anmeldung: einmaliger Kopplungs-Link (`spark-app://pair?url=…&code=…`) mit QR-Code |
| `POST /api/iphone/pair` | App: Code gegen eigenen Schlüssel tauschen (10 pro Minute und Adresse) |
| `GET /api/iphone/hello` | App: prüft den Schlüssel, nennt Profil, Sprache und was das Profil erlaubt |
| `GET /api/profile/reminders` | App: Erinnerungen und Timer des Profils, damit sie auf dem iPhone klingeln |
| `GET /api/proactive`, `POST /api/proactive/greet` | App: Hinweise von selbst |
| `POST /api/assistant/say` | App: Hinweise mit der Spark-Stimme sprechen |
| `POST /api/test/asr`, `POST /api/chat`, `POST /api/siri/ask` | Fragen und Antworten wie im Browser und bei Siri |
| `DELETE /api/profile/iphone/{id}` | Browser-Anmeldung: iPhone entfernen |
| `POST /api/iphone/push-token` | App: ihre Push-Adresse anmelden (nur mit dem App-Schlüssel) |
| `GET /api/iphone/note?id=…` | App (Mitteilungs-Erweiterung): Text einer Push-Meldung holen |
| `POST /api/profile/iphone/push-test` | Browser-Anmeldung: Test-Meldung an die eigenen iPhones |
| `GET/PUT /api/profile/convos` | App: Verlauf lesen und das laufende Gespräch speichern (Löschen nur im Panel) |
| `GET/PUT /api/iphone/settings` | App: „Mein Profil“, nur die Felder aus `iphone.APP_FIELDS` |
| `GET /api/assistant/voices` | App: Stimmen zur Auswahl |
| `POST /api/tasks/inbox`, `POST /api/profile/tasks/einkauf|aufgaben` | App: neue Listeneinträge holen, Einträge aus Kurzbefehlen setzen (nur mit `app_ios`) |
| `POST /api/iphone/doc` | App: Text eines Dokuments in „Meine Dokumente“ (nur mit `app_docs`) |
| `GET /api/iphone/update` | App: installierte und neue geprüfte Version, Änderungen, Fortschritt (nur mit Recht vom Admin) |
| `POST /api/iphone/update` | App: Update starten, Header `X-Speech-Code` mit frischem Code (nur mit Recht „Starten“) |
| `GET /api/admin/iphone-update`, `PUT /api/admin/iphone-update/{id}` | Admin: wer Hinweise bekommt und wer starten darf |
| `GET/PUT/DELETE /api/admin/apns` | Admin: Apple-Schlüssel (PUT und DELETE mit zweitem Schritt) |

Jeder Push, der `ios/` ändert, baut die App auf GitHub für den Simulator (`.github/workflows/ios.yml`), damit Fehler dort auffallen und nicht erst in Xcode.
