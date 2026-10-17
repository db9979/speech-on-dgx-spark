# Android-App „Spark“ (APK, ohne Store)

Die App ist eine schlanke Hülle um die Spark-Seite: Sie zeigt den Spark so, wie er im Handy-Browser aussieht
(wie die iPhone-App, seit V01.0.296), und ergänzt nur, was eine Seite nicht kann:

- **Mitteilungen bei geschlossener App:** Die App fragt alle 15 Minuten selbst beim Spark nach (`/api/android/notes`),
  ohne Google-Dienst. Erinnerungen, Morgenrunde und Hinweise kommen dorthin, wenn die App das zuletzt benutzte Gerät
  ist oder kein anderer Weg (iPhone-App) eingerichtet ist.
- **Mitteilungen sofort** (ab 1.2.0, V01.0.473): Admin: Funktionen → Android-App → „Android: Mitteilungen sofort“ (aus).
  Für jedes Profil gleich an; abschalten lässt es sich unter Ich → Android-App → „Mitteilungen sofort“. Dann die App einmal öffnen. Die App hält dann eine Verbindung
  zum Spark offen (`/api/android/wait`: der Spark antwortet sofort, wenn eine Mitteilung da ist, sonst nach 4 Minuten
  leer, und die App fragt wieder; ab 1.3.3, vorher 50 Sekunden). Damit das über den Reverse Proxy klappt, dort den Timeout
  auf mindestens 5 Minuten setzen (Synology: Anmeldeportal → Reverse Proxy → Bearbeiten → Erweitert/Benutzerdefinierter
  Header bzw. Timeout); schneidet der Proxy nach einer Minute ab, fällt die App von selbst für einen Tag auf 50 Sekunden zurück. Chat-Nachrichten, Erinnerungen und Hinweise kommen so ohne Verzögerung, ohne
  Google-Dienst. Android zeigt dafür eine stille Daueranzeige „Mit dem Spark verbunden“ (Dienst im Vordergrund). Damit
  Android die Verbindung nicht schlafen legt: in den Android-Einstellungen bei Apps, Spark, Akku „Nicht eingeschränkt“.
  Nach einem Neustart des Handys startet die Verbindung beim ersten Öffnen der App; bis dahin fragt die App alle
  15 Minuten. Schalter aus oder abgemeldet: Die App beendet die Verbindung von selbst. Live zeigt unter Verbindungen
  „Android-App (sofort)“ nur mit der Anzahl.
- **Spark als Assistent** (ab 1.4.0, V01.0.732): Admin: Funktionen → Android-App → „Android: Spark als Assistent“ (aus).
  Freigegeben öffnet die Assistenten-Taste (Einstellungen → Apps → Standard-Apps → Digitaler Assistent „Spark“, dann
  lange auf Ein/Aus oder Home drücken) ein Blatt über der App, die gerade offen ist: das Gesicht des Spark, was er
  gehört hat, die Antwort zum Mitlesen, ein Feld zum Tippen und „Ganze App“. Die App nimmt die Frage selbst auf
  (Echo- und Rauschunterdrückung des Handys, Pause von knapp einer Sekunde beendet die Frage), schickt sie an den
  Spark (`/api/test/asr`, dann `/api/chat` als Gerät „android“) und spielt die Antwort selbst ab, kurz und ohne
  Listen. Reinsprechen während der Antwort macht sie leiser; erst wenn der Spark eine echte Frage erkennt, hört sie
  auf. Mit „Freihändig“ im Chat hört sie danach wieder zu. Auf dem Sperrbildschirm will das Handy zuerst
  entsperrt werden. Das Gespräch steht danach unter Chats wie jedes andere.
  Dazu: das **Widget** „Spark“ für den Startbildschirm (Gesicht, Mikrofon, nur Zahlen: „Heute: 2 Termine ·
  1 Erinnerung · 3 ungelesen“, und wo ein Gerät im Raum-Modus zuhört), die Kachel **„Spark zuhören“** in den
  Schnelleinstellungen und die **Kurzbefehle** am App-Symbol (lange drücken: Spark zuhören, Frage schreiben, Heute,
  Chats). Ist der Spark gerade nicht erreichbar, wartet eine getippte Frage (höchstens 10, einen Tag) und geht von
  selbst raus, sobald er wieder da ist; die Antwort kommt als Mitteilung „Antwort vom Spark“.
  Ohne Freigabe öffnet die Taste wie bisher die App, die zuhört.
- **Teilen an Spark:** Text in einer anderen App teilen → Spark: Der Text steht im Tippfeld, abschicken tust du selbst.
  Ab 1.4.0 auch **Fotos, PDFs und Office-Dateien** (höchstens 3): Die App fragt „Dazu fragen“ oder „Nur ablegen“.
  Ein Foto wird auf dem Handy auf 1280 Pixel verkleinert und neu gezeichnet (ohne Ort und Kameradaten) und hängt dann
  am Gespräch (braucht „Bilder erkennen“) oder liegt unter „Meine Dokumente“; andere Dateien gehen nach „Meine
  Dokumente“ (braucht „Dokumente“), danach steht „Fass das Dokument … kurz zusammen.“ im Tippfeld. Abgeschickt wird nie
  von selbst.
- **Fingerabdruck für Admins** (ab 1.4.0, V01.0.732): Admin: Funktionen → Android-App → „Android: Fingerabdruck für
  Admins“ (aus). Ist die App mit einem Profil mit Admin-Rolle angemeldet, fragt sie beim Öffnen und nach 5 Minuten im
  Hintergrund nach Fingerabdruck, Gesicht oder Displaysperre des Handys (wie Face ID vor „Spark verwalten“ in der
  iPhone-App). Android prüft das; die App erfährt nur ja oder nein, der Spark gar nichts.
- **Notaus-Kachel** (ab 1.1.0): Schnelleinstellungen bearbeiten → „Notaus“ hinzufügen. Admins wählen „Ganzer Spark“ (Stufe 2) oder „Mein Notaus“, alle anderen „Mein Notaus“, immer mit Rückfrage; aufheben nur im Browser (siehe [Sicherheit und Betrieb](sicherheit-und-betrieb.md)).
- **Neue Version:** Die App meldet sich mit einer Mitteilung, wenn der Spark eine neuere APK hat.
- **Ruhig beim Update des Spark** (ab 1.3.2, V01.0.570): Startet der Spark neu (ein Update), zeigt die App „Spark startet neu … Die Seite kommt gleich wieder.“ und versucht es von selbst wieder, statt zur Adresseingabe zu springen (erst nach etwa fünf Minuten ohne Spark kommt die Adresseingabe, „Adresse ändern“ geht jederzeit). Eine Mitteilung, Teilen oder die Assistenten-Taste laden die offene Seite nicht neu: die Seite springt nur an die Stelle.
- **Akku schonen** (ab 1.3.3, V01.0.668): Im Hintergrund pausiert die App ihre Seite (keine Abfragen, keine offenen Verbindungen der Seite); beim Zurückholen holt sie nach. Während eines Anrufs bleibt die Seite wach. „Mitteilungen sofort“ läuft unabhängig davon weiter.
- **Kamera für Videoanrufe** (ab 1.3.1, V01.0.556): Die App fragt beim ersten Videoanruf in Chats nach der Kamera, beim ersten Anruf nach dem Mikrofon; nur für die Seite des eigenen Sparks. Ohne Kamera geht der Anruf mit Ton weiter.
- **Update in der App** (ab 1.3.0, V01.0.533): Admin: Funktionen → Android-App → „Android: Update in der App“ (aus).
  Freigegeben zeigt die App oben einen Streifen „Neue App-Version … · Jetzt aktualisieren“ (✕ blendet ihn bis zur
  nächsten Version aus); auch die Mitteilung „Neue Spark-App“ und der Knopf unter Ich → Android-App starten das Update.
  Die App fragt nur ihren eigenen Spark (`/api/profile/android`: Version, Größe, SHA-256), nie GitHub, und lädt die APK
  mit ihrer Anmeldung von `GET /api/android/apk` in ihren Cache. Vor dem Installieren prüft sie selbst: Größe und
  SHA-256 wie gemeldet, Paketname `io.github.db9979.spark`, höhere Versionsnummer, gleicher Signierschlüssel wie die
  installierte App. Dann übernimmt der Paket-Installer von Android; er prüft die Signatur noch einmal und fragt
  „Aktualisieren“. Beim ersten Mal fragt Android einmal, ob die Spark-App Apps installieren darf („Dieser Quelle
  vertrauen“). Passt etwas nicht, löscht die App die Datei und installiert nichts. Ganz ohne Tipp geht es nicht: Still
  installieren dürfen nur Store-Apps oder Apps einer Firmen-Geräteverwaltung. Das Update auf 1.3.0 selbst läuft noch
  einmal über den Download-Link.
- **Versionen der Handys:** Zustand → Geräte-Updates zeigt für die Android-App, welches Profil welche App-Version hat
  und wie viele Handys aktuell sind (aus der Kennung „SparkAndroid/x.y.z“ ihrer Anfragen, nur im Speicher, 14 Tage);
  Live zählt „Android aktuell/alle“. Eine neue Version eines Profils steht als Zeile `android: app version … -> …` im Log.

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

- Admin-Schalter `chat.android`, aus. Freigegeben gilt er für jedes Profil; einzelne Profile sperrt nur der Admin (Personen und Geräte → Gesperrte Funktionen). Gäste nie.
- Die App hat keinen eigenen Schlüssel: Sie nutzt die Anmeldung ihrer Seite (Cookie). Abmelden in der Seite beendet sie.
- Die App lädt nur Seiten ihres eigenen Spark (gleiche Adresse und Port), alles andere öffnet der Browser; nur https,
  System-Zertifikate. Mikrofon nur für die eigene Spark-Seite.
- `#ask=` legt geteilten Text nur ins Tippfeld, nie wird etwas von selbst geschickt; beide Sprünge gelten nur in der App.
- Die APK kommt nur von GitHubs Download-Adressen, mit passender Größe und SHA-256. Der Download-Link trägt ein
  Einmal-Token (nur sein Hash im Speicher, 30 Minuten, höchstens 5 Abrufe); ohne gültigen Link 404.
- Update in der App: eigener Admin-Schalter `chat.android_update` (aus), sperrbar je Profil; `GET /api/android/apk`
  nur mit Browser-Anmeldung des Profils (kein Geräteschlüssel), Rate-Limit, gibt nur die APK heraus, die der Spark
  beim Holen geprüft hat. Die App folgt keiner Umleitung und vertraut nur der eigenen Adresse; Android installiert
  nur über die installierte App, wenn der Signierschlüssel passt. Die Seite gibt der App nichts mit: der Knopf ist der
  feste Link `sparkapp:update`, den die App abfängt. Log: `android: app update … sent to …` oder `… refused … reason …`.
- Mitteilungen liegen nur im Speicher (24 Stunden, höchstens 30 pro Profil) und gehen nur an die eigene Anmeldung.
- Spark als Assistent: eigener Admin-Schalter `chat.android_assist` (aus), sperrbar je Profil, nie Gäste. Der Spark
  prüft jede Frage des Blatts selbst (Gerät „android“); ohne Freigabe antwortet er 403 und schreibt
  `android: assistant refused for … reason …` ins Log. Die App erfährt die Freigabe nur aus `/api/profile/android`
  und blendet Widget, Kachel und Kurzbefehle danach aus oder ein. Das Mikrofon läuft nur, solange das Blatt offen ist
  und die Frage dauert (höchstens 30 Sekunden); auf dem Sperrbildschirm erst nach dem Entsperren. Das Widget zeigt
  nur Zahlen, nie Titel oder Namen von Terminen und Nachrichten. Wartende Fragen liegen nur in der App (höchstens 10,
  einen Tag).
- Geteilte Dateien gehen über die normalen Wege des Spark (`/api/chat/image`, `/api/profile/docs`) mit ihren Rechten,
  Größen- und Ratenlimits; die App liest nur Inhalts-Adressen (`content://`), keine Dateipfade.
- Fingerabdruck für Admins: eigener Admin-Schalter `chat.android_lock` (aus); er greift nur bei einer Anmeldung mit
  Admin-Rolle. Das Handy ohne jede Displaysperre kann nichts prüfen: dann sagt die App das und öffnet.

## Neue Version

In `android/version.properties` `name` und `code` erhöhen und nach main pushen: Die Aktion baut, signiert und
veröffentlicht `android-v<name>`; der Spark holt sie und die Apps melden sich.
