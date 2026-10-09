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
2. Xcode → Target **Spark** → **General**: **Version** (z. B. 1.1) erhöhen, wenn sich für Nutzer etwas ändert; **Build** muss bei jedem Upload größer werden (1, 2, 3 …).
3. Oben als Ziel **Any iOS Device (arm64)** wählen.
4. **Product → Archive**. Nach ein paar Minuten öffnet sich der Organizer.
5. **Distribute App → App Store Connect → Distribute**. Xcode signiert und lädt hoch.
6. Nach 5–30 Minuten erscheint der Build in App Store Connect unter **TestFlight**. Die Frage nach Verschlüsselung beantwortet die App selbst (nur https, `ITSAppUsesNonExemptEncryption = NO`).

Danach im Panel unter **Einstellungen → Funktionen → Push an die iPhone-App** die Art auf **„Produktion“** stellen: TestFlight- und App-Store-Builds nutzen Apples Produktions-Push. Direkt aus Xcode aufgespielt heißt es wieder „Entwicklung“.

## 3. TestFlight (Empfehlung für dich und die Familie)

1. App Store Connect → **Benutzer und Zugriff**: Familienmitglieder mit ihrer Apple-ID einladen (Rolle z. B. „Marketing“ reicht).
2. App → **TestFlight → Interne Tests → +** → Gruppe „Familie“ anlegen, die Leute hinzufügen, den Build zuweisen.
3. Jeder lädt auf dem iPhone die App **TestFlight** aus dem App Store und nimmt die Einladung an. Neue Builds kommen dort automatisch.

Ein TestFlight-Build läuft 90 Tage, danach einfach einen neuen hochladen.

## 4. App Store (nur wenn Fremde die App laden sollen)

Zusätzlich zu Schritt 1–2 in App Store Connect unter der App:

- **Screenshots**: mindestens für 6,9" (iPhone 16 Pro Max) oder 6,5", aus dem Simulator mit ⌘S.
- **Beschreibung, Stichwörter, Support-URL** (z. B. die GitHub-Seite).
- **Datenschutzrichtlinie (URL)**: eine Seite, die sagt, dass die App nur mit dem eigenen Spark spricht und nichts an dich als Entwickler schickt.
- **App-Datenschutz**: „Keine Daten erfasst“ (alles geht an den Spark des Nutzers, nicht an dich). Mitteilungen über Apple enthalten nur einen festen Satz.
- **Altersfreigabe**: Fragebogen ausfüllen (keine Inhalte der Kategorien → 4+; wegen freier Antworten eines Sprachmodells eher 12+).
- **Hinweise für die Prüfung**: Apples Prüfer brauchen einen Spark. Ein eigenes Testprofil anlegen, einen Kopplungs-Link erzeugen (gilt nur 10 Minuten, daher besser ein kurzes Video der App beilegen und anbieten, auf Zuruf einen Link zu schicken) und die Adresse deines Reverse Proxys nennen.
- **Verfügbarkeit**: „Nicht gelistet“ (nur per Link) bei Apple beantragen, wenn die App nicht in der Suche im App Store auftauchen soll.

Dann **Zur Prüfung einreichen**. Die Prüfung dauert meist 1–3 Tage. Häufige Ablehnung: Prüfer kommt nicht weiter, weil er keinen Spark hat (Richtlinie 2.1) – deshalb Video und Testzugang.

## CarPlay

Builds mit CarPlay gehen erst hoch, wenn Apple die CarPlay-Freigabe erteilt hat und sie in `ios/Spark.entitlements` eingetragen ist (siehe [iphone-app.md](iphone-app.md#carplay)). Bis dahin lädst du Builds ohne diese Zeile hoch; alles andere funktioniert.
