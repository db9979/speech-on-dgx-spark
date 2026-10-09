# iPhone-App veröffentlichen

Drei Wege, vom einfachsten zum aufwendigsten. Alle brauchen das Apple Developer Program (99 €/Jahr).

| Weg | Für wen | Prüfung durch Apple |
|---|---|---|
| **TestFlight intern** (Empfehlung) | du und bis zu 100 Leute aus deinem Developer-Team | keine |
| **TestFlight extern** | bis zu 10.000 Leute per Link | kurze Beta-Prüfung |
| **App Store** (öffentlich oder nur per Link) | alle | volle Prüfung |

## 1. Einmalig: App bei Apple anlegen

1. In Xcode prüfen: Projekt **Spark** → **Build Settings** → `APP_BUNDLE_ID` ist deine eigene Bundle-ID (z. B. `io.github.db9979.speechspark.dominik`). Bei beiden Targets (**Spark** und **SparkNotify**) ist unter **Signing & Capabilities** dein Team gewählt.
2. appstoreconnect.apple.com → **Apps → + → Neue App**: Plattform iOS, Name (muss im App Store frei sein, „Spark“ ist sicher vergeben, z. B. „Spark Sprachassistent“), Sprache Deutsch, Bundle-ID aus der Liste, SKU frei wählbar (z. B. `speechspark`).

## 2. Jede neue Version hochladen

1. Im Repo `git pull`.
2. Xcode → Target **Spark** → **General**: **Version** (z. B. 1.1) erhöhen, wenn sich für Nutzer etwas ändert. Die **Build**-Nummer zählt von selbst hoch: Beim Bauen wird sie auf die Zahl der Commits im Repo gesetzt, für die App und alle Erweiterungen gleich. Nach jedem `git pull` ist sie also größer. In der App steht beides klein unten, z. B. „1.0 (412)“.
3. Oben als Ziel **Any iOS Device (arm64)** wählen.
4. **Product → Archive**. Nach ein paar Minuten öffnet sich der Organizer.
5. **Distribute App → App Store Connect → Distribute**. Xcode signiert und lädt hoch.
6. Nach 5–30 Minuten erscheint der Build in App Store Connect unter **TestFlight**. Die Frage nach Verschlüsselung beantwortet die App selbst (nur https, `ITSAppUsesNonExemptEncryption = NO`).

Danach im Panel unter **Einstellungen → Funktionen → Push an die iPhone-App** die Art auf **„Produktion“** stellen: TestFlight- und App-Store-Builds nutzen Apples Produktions-Push. Direkt aus Xcode aufgespielt heißt es wieder „Entwicklung“.

### Hochladen per GitHub-Knopf „TestFlight“

Statt Archive und Distribute am Mac geht es auch auf GitHub. Der Knopf baut die App, lässt sie von Apple signieren und lädt sie zu TestFlight hoch. Er startet nur für einen Stand, dessen Tests grün sind. Die Build-Nummer zählt von selbst hoch.

Einmalig:
1. App Store Connect → **Benutzer und Zugriff → Integrationen → App Store Connect API → Team-Schlüssel**: einen Schlüssel mit Rolle **Admin** anlegen. Nur Admin darf Zertifikate für das Signieren holen. Hast du für die Texte schon einen App-Manager-Schlüssel, ersetze ihn durch diesen.
2. GitHub → **Settings → Secrets and variables → Actions**: `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY` (der ganze Inhalt der `.p8`-Datei) und neu `ASC_TEAM_ID` (developer.apple.com → Membership → Team ID).

Dann: GitHub → **Actions → TestFlight → Run workflow**, Bundle-ID eintragen, **Run**. Nach 15 bis 30 Minuten ist der Build in App Store Connect unter TestFlight.

**Automatisch:** Ändert ein Commit auf main etwas unter `ios/`, startet TestFlight von selbst, sobald „iPhone app“ und „Tests“ grün sind. Höchstens ein Upload pro Stunde. Kommt in der Wartezeit ein neuerer iOS-Commit, wird nur dieser hochgeladen. Abschalten: GitHub → Settings → Secrets and variables → Actions → Variables → `TESTFLIGHT_AUTO` = `off`. Eine andere Bundle-ID als `io.github.db9979.speechspark` trägst du als Variable `APP_BUNDLE_ID` ein. Zum Neustarten immer **Run workflow** nehmen, nicht „Re-run“, denn ein Re-run baut den alten Stand.

Klappt es beim ersten Mal nicht, schick mir die rote Zeile aus dem Lauf.

## 3. TestFlight (Empfehlung für dich und die Familie)

1. App Store Connect → **Benutzer und Zugriff**: Familienmitglieder mit ihrer Apple-ID einladen (Rolle z. B. „Marketing“ reicht).
2. App → **TestFlight → Interne Tests → +** → Gruppe „Familie“ anlegen, die Leute hinzufügen, den Build zuweisen.
3. Jeder lädt auf dem iPhone die App **TestFlight** aus dem App Store und nimmt die Einladung an. Neue Builds kommen dort automatisch.

Ein TestFlight-Build läuft 90 Tage, danach einfach einen neuen hochladen.

## 4. App Store (nur wenn Fremde die App laden sollen)

Zusätzlich zu Schritt 1–2 in App Store Connect unter der App:

- **Screenshots**: mindestens für 6,9" (iPhone 16 Pro Max) oder 6,5", aus dem Simulator mit ⌘S.
- **Beschreibung, Stichwörter, Support-URL** (z. B. die GitHub-Seite).
- **Datenschutzrichtlinie (URL)**: fertig in [app-datenschutz.md](app-datenschutz.md), englisch in [app-privacy.md](../en/app-privacy.md). Als URL den GitHub-Link der Datei eintragen.
- **App-Datenschutz**: „Keine Daten erfasst“ (alles geht an den Spark des Nutzers, nicht an dich). Mitteilungen über Apple enthalten nur einen festen Satz.
- **Altersfreigabe**: Fragebogen ausfüllen (keine Inhalte der Kategorien → 4+; wegen freier Antworten eines Sprachmodells eher 12+).
- **Hinweise für die Prüfung**: Apples Prüfer brauchen einen Spark. Ein eigenes Testprofil anlegen, einen Kopplungs-Link erzeugen (gilt nur 10 Minuten, daher besser ein kurzes Video der App beilegen und anbieten, auf Zuruf einen Link zu schicken) und die Adresse deines Reverse Proxys nennen.
- **Verfügbarkeit**: „Nicht gelistet“ (nur per Link) bei Apple beantragen, wenn die App nicht in der Suche im App Store auftauchen soll.


### Texte automatisch eintragen

Name, Untertitel, Werbetext, Beschreibung, Stichwörter, URLs und Kategorien (deutsch und englisch) liegen in `ios/fastlane/metadata`. Ein Knopf auf GitHub trägt sie in App Store Connect ein. Er lädt keinen Build und keine Bilder hoch und reicht nichts zur Prüfung ein.

1. Die App muss in App Store Connect schon angelegt sein (Schritt 1), mit Hauptsprache Deutsch.
2. App Store Connect → **Benutzer und Zugriff → Integrationen → App Store Connect API → Team-Schlüssel → +**: Name „GitHub Texte“, Rolle **App-Manager**. Die `.p8`-Datei herunterladen (geht nur einmal), **Schlüssel-ID** und **Issuer-ID** notieren.
3. GitHub → Repo → **Settings → Secrets and variables → Actions → New repository secret**, dreimal: `ASC_KEY_ID` (Schlüssel-ID), `ASC_ISSUER_ID` (Issuer-ID), `ASC_KEY` (der ganze Inhalt der `.p8`-Datei).
4. GitHub → **Actions → App Store texts → Run workflow**: Bundle-ID, Version (`1.0`) und Copyright (z. B. `2026 Vorname Nachname`) eintragen, **Run**.
5. Nach etwa 2 Minuten stehen die Texte in App Store Connect. Den Schlüssel kannst du danach dort wieder widerrufen.

Die Bildschirmfotos (deutsch und englisch, 6,9" und 6,3") macht der Ablauf **App Store screenshots** im iPhone-Simulator mit Beispielinhalten. Er legt sie in den Zweig `app-store-screenshots`. Mit dem Häkchen „Bildschirmfotos mit hochladen“ trägt **App Store texts** sie gleich mit ein. Den Vorführmodus (`-SparkDemo`) gibt es nur im Testbuild, nicht in der App aus dem Store.

Von Hand bleiben: App-Datenschutz, Altersfreigabe, Hinweise für die Prüfung und Preis. Die Antworten dafür stehen in den Unterlagen aus dem Projekt („App Store Connect: Angaben für Spark“).

Dann **Zur Prüfung einreichen**. Die Prüfung dauert meist 1–3 Tage. Häufige Ablehnung: Prüfer kommt nicht weiter, weil er keinen Spark hat (Richtlinie 2.1) – deshalb Video und Testzugang.

## CarPlay

Builds mit CarPlay gehen erst hoch, wenn Apple die CarPlay-Freigabe erteilt hat und sie in `ios/Spark.entitlements` eingetragen ist (siehe [iphone-app.md](iphone-app.md#carplay)). Bis dahin lädst du Builds ohne diese Zeile hoch; alles andere funktioniert.
