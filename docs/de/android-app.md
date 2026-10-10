# Android-App „Spark“ (APK, ohne Store)

Die App ist eine schlanke Hülle um die Spark-Seite: Sie zeigt den Spark so, wie er im Handy-Browser aussieht
(wie die iPhone-App, seit V01.0.296), und ergänzt nur, was eine Seite nicht kann:

- **Mitteilungen bei geschlossener App:** Die App fragt alle 15 Minuten selbst beim Spark nach (`/api/android/notes`),
  ohne Google-Dienst. Erinnerungen, Morgenrunde und Hinweise kommen dorthin, wenn die App das zuletzt benutzte Gerät
  ist oder kein anderer Weg (iPhone-App) eingerichtet ist.
- **Assistenten-Taste:** Unter Einstellungen → Apps → Standard-Apps → Digitaler Assistent „Spark“ wählen; langes
  Drücken öffnet die App und sie hört zu.
- **Teilen an Spark:** Text in einer anderen App teilen → Spark. Der Text steht im Tippfeld, abschicken tust du selbst.
- **Neue Version:** Die App meldet sich mit einer Mitteilung, wenn der Spark eine neuere APK hat.

## Einrichten

1. **Signierschlüssel (einmal, Admin):** Auf einem Rechner mit Java:
   `keytool -genkeypair -v -keystore spark.jks -alias spark -keyalg RSA -keysize 4096 -validity 10000`
   (ein Passwort wählen, für Schlüssel und Datei dasselbe). Dann im GitHub-Repo unter Settings → Secrets and
   variables → Actions zwei Secrets anlegen: `ANDROID_KEYSTORE` = Inhalt von `base64 -w0 spark.jks`,
   `ANDROID_KEYSTORE_PASSWORD` = das Passwort. Die Datei `spark.jks` gut aufheben: Ohne denselben Schlüssel lassen
   sich spätere Versionen nicht über die alte installieren.
2. **App bauen:** Actions → „Android app“ → Run workflow. Sie erscheint als Release `android-v1.0.0` mit
   `spark.apk`, `spark.apk.sha256` und `android.json`.
3. **Spark:** Einstellungen → Funktionen → Android-App an, speichern, „App jetzt holen“ (sonst holt er sie einmal am Tag).
   Er prüft Größe und SHA-256 und behält sie unter `STATE/android`.
4. **Profil:** Ich → Android-App → „Android-App für mich“ an, „Download-Link holen“, den QR-Code mit der Kamera des
   Android-Handys scannen, die APK installieren (das Handy fragt einmal, ob der Browser Apps installieren darf).
   Der Link gilt 30 Minuten.
5. **In der App:** Adresse des Spark eintragen (https mit echtem Zertifikat, z. B. der Reverse Proxy), dann wie im
   Browser mit Name und PIN anmelden, Mitteilungen und Mikrofon erlauben. Für zuverlässige Mitteilungen die
   Akku-Optimierung für Spark ausschalten.

## Sicherheit

- Admin-Schalter `chat.android` und Profilschalter `android_on`, beide aus; Gäste nie.
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
