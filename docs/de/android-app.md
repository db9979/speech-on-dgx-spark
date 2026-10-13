# Android-App „Spark“ (APK, ohne Store)

Die App ist eine schlanke Hülle um die Spark-Seite: Sie zeigt den Spark so, wie er im Handy-Browser aussieht
(wie die iPhone-App, seit V01.0.296), und ergänzt nur, was eine Seite nicht kann:

- **Mitteilungen bei geschlossener App:** Die App fragt alle 15 Minuten selbst beim Spark nach (`/api/android/notes`),
  ohne Google-Dienst. Erinnerungen, Morgenrunde und Hinweise kommen dorthin, wenn die App das zuletzt benutzte Gerät
  ist oder kein anderer Weg (iPhone-App) eingerichtet ist.
- **Mitteilungen sofort** (ab 1.2.0, V01.0.473): Admin: Funktionen → Android-App → „Android: Mitteilungen sofort“ (aus).
  Für jedes Profil gleich an; abschalten lässt es sich unter Ich → Android-App → „Mitteilungen sofort“. Dann die App einmal öffnen. Die App hält dann eine Verbindung
  zum Spark offen (`/api/android/wait`: der Spark antwortet sofort, wenn eine Mitteilung da ist, sonst nach 50 Sekunden
  leer, und die App fragt wieder). Chat-Nachrichten, Erinnerungen und Hinweise kommen so ohne Verzögerung, ohne
  Google-Dienst. Android zeigt dafür eine stille Daueranzeige „Mit dem Spark verbunden“ (Dienst im Vordergrund). Damit
  Android die Verbindung nicht schlafen legt: in den Android-Einstellungen bei Apps, Spark, Akku „Nicht eingeschränkt“.
  Nach einem Neustart des Handys startet die Verbindung beim ersten Öffnen der App; bis dahin fragt die App alle
  15 Minuten. Schalter aus oder abgemeldet: Die App beendet die Verbindung von selbst. Live zeigt unter Verbindungen
  „Android-App (sofort)“ nur mit der Anzahl.
- **Assistenten-Taste:** Unter Einstellungen → Apps → Standard-Apps → Digitaler Assistent „Spark“ wählen; langes
  Drücken öffnet die App und sie hört zu.
- **Teilen an Spark:** Text in einer anderen App teilen → Spark. Der Text steht im Tippfeld, abschicken tust du selbst.
- **Notaus-Kachel** (ab 1.1.0): Schnelleinstellungen bearbeiten → „Notaus“ hinzufügen. Admins wählen „Ganzer Spark“ (Stufe 2) oder „Mein Notaus“, alle anderen „Mein Notaus“, immer mit Rückfrage; aufheben nur im Browser (siehe [Sicherheit und Betrieb](sicherheit-und-betrieb.md)).
- **Neue Version:** Die App meldet sich mit einer Mitteilung, wenn der Spark eine neuere APK hat.

## Einrichten

1. **Signierschlüssel (einmal, Admin):** Auf dem Spark (oder einem Mac) im Terminal
   `bash /opt/speech-spark/src/tools/android-schluessel.sh` ausführen (ohne sudo, braucht nur openssl). Es legt
   `~/spark-android.p12` und `~/spark-android.pass` an und zeigt zwei Werte. Im GitHub-Repo unter Settings → Secrets
   and variables → Actions → „New repository secret“ beide anlegen: `ANDROID_KEYSTORE_PASSWORD` und
   `ANDROID_KEYSTORE` (die lange Zeile). Die beiden Dateien gut aufheben: Ohne denselben Schlüssel lassen sich
   spätere Versionen nicht über die alte installieren.
2. **App bauen:** Actions → „Android app“ → Run workflow. Sie erscheint als Release `android-v1.0.0` mit
   `spark.apk`, `spark.apk.sha256` und `android.json`.
3. **Spark:** Funktionen → Android-App an, speichern, „App jetzt holen“ (sonst holt er sie einmal am Tag).
   Er prüft Größe und SHA-256 und behält sie unter `STATE/android`.
4. **Profil:** Ich → Android-App → „Download-Link holen“, den QR-Code mit der Kamera des
   Android-Handys scannen, die APK installieren (das Handy fragt einmal, ob der Browser Apps installieren darf).
   Der Link gilt 30 Minuten.
5. **In der App:** Adresse des Spark eintragen (https mit echtem Zertifikat, z. B. der Reverse Proxy), dann wie im
   Browser mit Name und PIN anmelden, Mitteilungen und Mikrofon erlauben. Für zuverlässige Mitteilungen die
   Akku-Optimierung für Spark ausschalten.

## Sicherheit

- Admin-Schalter `chat.android`, aus. Freigegeben gilt er für jedes Profil; einzelne Profile sperrt nur der Admin (Funktionen → Wer darf was). Gäste nie.
- Die App hat keinen eigenen Schlüssel: Sie nutzt die Anmeldung ihrer Seite (Cookie). Abmelden in der Seite beendet sie.
- Die App lädt nur Seiten ihres eigenen Spark (gleiche Adresse und Port), alles andere öffnet der Browser; nur https,
  System-Zertifikate. Mikrofon nur für die eigene Spark-Seite.
- `#ask=` legt geteilten Text nur ins Tippfeld, nie wird etwas von selbst geschickt; beide Sprünge gelten nur in der App.
- Die APK kommt nur von GitHubs Download-Adressen, mit passender Größe und SHA-256. Der Download-Link trägt ein
  Einmal-Token (nur sein Hash im Speicher, 30 Minuten, höchstens 5 Abrufe); ohne gültigen Link 404.
- Mitteilungen liegen nur im Speicher (24 Stunden, höchstens 30 pro Profil) und gehen nur an die eigene Anmeldung.

## Neue Version

In `android/version.properties` `name` und `code` erhöhen und nach main pushen: Die Aktion baut, signiert und
veröffentlicht `android-v<name>`; der Spark holt sie und die Apps melden sich.
