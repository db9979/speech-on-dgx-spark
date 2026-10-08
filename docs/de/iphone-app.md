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
5. Links oben das Projekt **Spark** anklicken → Target **Spark** → **Signing & Capabilities** → bei **Team** dein Konto wählen. Meldet Xcode, dass die Bundle-ID schon vergeben ist, bei **Bundle Identifier** hinten etwas Eigenes anhängen (z. B. `io.github.db9979.speechspark.dominik`).
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

- Oben das Gesicht des Assistenten: es blinzelt, schaut umher, hört mit roter Antenne zu, denkt mit kreisendem Bogen und bewegt beim Sprechen den Mund. Antippen ist wie der Knopf.
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

## Sicherheit

- Jedes iPhone bekommt beim Koppeln einen eigenen Schlüssel. Er liegt nur im Schlüsselbund dieses iPhones und auf dem Spark nur als Hash.
- Der Schlüssel darf nur fragen und hören (Chat, Spracherkennung, Siri-Frage). Einstellungen, Gedächtnis, Geräte, Verbindungen und weitere Kopplungen gehen damit nicht.
- Der eigene Schalter aus sperrt sofort alle iPhones des Profils, der Admin-Schalter alle. Ein verlorenes iPhone unter **Ich → iPhone-App → Entfernen**.
- Smart Home aus der App nur mit eigenem Schalter und Codewort. Was die App als Absender angibt, zählt nicht; das Panel entscheidet am Schlüssel.
- Weckwort, Ständer-Modus, Route und Anrufe nur mit eigenem Schalter im Panel. Der Spark schlägt Route und Anruf nur vor, das Werkzeug gibt es nur für den App-Schlüssel mit Schalter; starten tut erst dein „Ja“ auf dem iPhone. Ein Hinweis von außen (Mail, Webseite) kann keine Route und keinen Anruf auslösen.
- Vor dem Weckwort geht kein Ton an den Spark. Im Hintergrund hört die App nur mit eingeschaltetem Weckwort zu.
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

Jeder Push, der `ios/` ändert, baut die App auf GitHub für den Simulator (`.github/workflows/ios.yml`), damit Fehler dort auffallen und nicht erst in Xcode.
