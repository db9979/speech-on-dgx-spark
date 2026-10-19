# Spark teilen: Panel auf einem eigenen Rechner

← [README](../../README.de.md)

Normalerweise läuft alles auf dem DGX Spark: Modelle, APIs und das Panel mit dem Assistenten. Das bleibt der Standard. Wer möchte, stellt das Panel und die kleinen Dienste (Chats, Erinnerungen, Lautsprecher, Telegram, Logs) auf einen eigenen kleinen Rechner, zum Beispiel einen Raspberry Pi 5. Der DGX liefert dann nur noch die Modelle: Spracherkennung, Sprachausgabe, Bilder und das eigene Sprachmodell.

**Wozu:** Der DGX darf neu starten, Modelle wechseln oder ausgeschaltet sein, und Chats, Anrufe, Erinnerungen, Durchsagen und Logs laufen weiter. Sprachfragen bekommen in der Zeit den festen Satz „Der Spark macht gerade Pause.“ (Notbetrieb), und der Dienst-Wächter meldet den Ausfall. Mit Funktionen → Notbetrieb mit Parakeet hört der Panel-Rechner dann selbst und versteht ein paar feste Befehle ohne Sprachmodell: Licht und Geräte über Home Assistant, die Uhrzeit und die eigenen Erinnerungen. Lautsprecher hören dazu vorher aufgenommene Sätze.

## Was du brauchst

- **Rechner für das Panel:** Raspberry Pi 5 mit 8 GB, NVMe-SSD statt SD-Karte, Kabel-LAN und eine feste IP-Adresse im Router. Als System Raspberry Pi OS Lite 64-bit in der aktuellen Version (Trixie, Python 3.13), Start von der NVMe. Ein Gehäuse wie das SunFounder Pironman 5 bringt den M.2-Steckplatz gleich mit; dann ohne zusätzliche NVMe-Platine. Andere 64-Bit-Rechner mit Debian oder Ubuntu und Python ab 3.11 gehen genauso.
- **Auf dem DGX das eigene Sprachmodell:** Spark teilen erreicht das Sprachmodell über das LLM-Tor. qwen38 ist vom Panel-Rechner aus nicht erreichbar, also vorher `sudo speech-spark modelle llm uebernehmen` (siehe [Installation](installation.md)).
- Beide Rechner im selben Heimnetz.

## Neu installieren, geteilt

1. **Auf dem DGX:**
   ```bash
   sudo ./install.sh --mode api --teilen
   ```
   Das installiert die Modelle, das TLS-Tor, den Wärter und die Firewall und zeigt am Ende einen Kopplungscode (6 Zeichen, 10 Minuten gültig, einmal nutzbar). Einen neuen Code gibt es jederzeit mit `sudo speech-spark teilen code`.
2. **Auf dem Panel-Rechner:**
   ```bash
   git clone https://github.com/db9979/speech-on-dgx-spark
   cd speech-on-dgx-spark
   sudo ./install.sh --mode panel --modelle <IP-des-DGX>
   ```
   Er fragt nach dem Code, koppelt, installiert nur das Panel (ohne torch, vLLM oder CUDA) und macht danach den Rundlauf: Sprachausgabe spricht einen Satz, die Spracherkennung muss ihn verstehen.

## Bestehenden Spark umziehen

Das Panel mit allen Profilen, Gedächtnis, Chats, Stimmen und Einstellungen zieht in einem Rutsch um.

1. **Auf dem neuen Panel-Rechner** das Panel installieren wie oben in Schritt 2, aber erst, wenn der DGX den Code zeigt.
2. **Auf dem DGX:** `sudo speech-spark umziehen --code`. Er macht eine Umzugs-Sicherung mit dem Tresor-Schlüssel (versiegelt mit einem Zufallspasswort) und dem https-Zertifikat des Panels und zeigt den Code.
3. Der neue Rechner holt beim Koppeln den Umzug, spielt ihn ein, zählt die Profile und meldet „fertig“. Bei einem schon installierten Panel-Rechner geht das auch mit `sudo speech-spark umziehen --von <IP-des-DGX>`.
4. Erst nach diesem „fertig“ schaltet der DGX sein Panel ab und läuft als Modell-Rechner weiter. Bricht etwas ab, bleibt der DGX unverändert. Keiner der Schritte löscht etwas.
5. **Von Hand danach** (steht auch unter Zustand → Update, 14 Tage lang):
   - im Router die Weiterleitung 31443 und die Ports für Anrufe (Funktionen → Chats → „Anrufe von unterwegs“) auf den neuen Rechner,
   - in Home Assistant Wyoming auf `<neuer-Rechner>:31003`,
   - bei jedem ESP32-Lautsprecher die neue Server-Adresse (http://<Pi-IP>:31080, per USB unter Lautsprecher einrichten; steht im Board noch die Adresse des DGX, sagen die Diagnose und „Netz prüfen“ das und nennen die richtige),
   - den Reverse Proxy (echtes Zertifikat für iPhone-App, Android-App und Passkeys) auf den neuen Rechner; läuft er auf einem anderen Gerät, bleibt seine Adresse unter Einstellungen → Sicherheit → Reverse Proxy richtig, lief er auf dem DGX selbst, dort die neue Adresse eintragen. Die iPhone-App nennt sonst im Hinweis „Spark nicht erreichbar“ das Zertifikat.

Die Apps bleiben angemeldet, weil das Zertifikat des Panels mitzieht. Was zwischen Sicherung und Umschalten im alten Panel geändert wird, geht nicht mit; am besten umziehen, wenn gerade niemand spricht.

## Zurückholen

Auf dem Panel-Rechner `sudo speech-spark umziehen --code`, auf dem DGX `sudo speech-spark zurueckholen --von <IP-des-Panel-Rechners>`. Derselbe Ablauf in die Gegenrichtung; danach läuft wieder alles auf dem DGX, und der Panel-Rechner schaltet nur sein Panel ab (seine Daten bleiben).

## Wie die Verbindung geschützt ist

- Zwischen den Rechnern geht nichts im Klartext: das TLS-Tor auf dem DGX spricht nur TLS 1.3 mit seinem eigenen Zertifikat, und der Panel-Rechner vertraut genau diesem einen (beim Koppeln gemerkt).
- Der Kopplungscode beweist beim Koppeln, dass beide dasselbe Zertifikat sehen. Wer sich dazwischen stellt, zeigt ein anderes und bekommt nichts.
- Die Firewall des DGX lässt die Ports der Tür nur für den Panel-Rechner zu. Jeder Befehl an den Wärter ist mit einem eigenen Schlüssel unterschrieben, hat einen Zeitstempel und gilt nur einmal.
- Welche Version der DGX installiert, entscheidet er nach seinen eigenen Regeln, nie der Panel-Rechner.

## Gehäuse des Panel-Rechners (Pironman 5)

Steckt der Raspberry Pi im Pironman-5-Gehäuse, zeigt das kleine Display den Zustand, die vier LEDs leuchten in der Statusfarbe und die Lüfter laufen nach der Temperatur. Einschalten unter Funktionen → Gehäuse (nur Admin, nur auf einem geteilten Spark sichtbar): „Pironman 5“ wählen, „Einrichten“ (Admin-Code), dann „Neu starten“. Oder bei der Installation `sudo ./install.sh --gehaeuse pironman5` und danach den Pi neu starten.

- **Einrichten** schreibt einen markierten Block in `/boot/firmware/config.txt` (I2C, SPI, Lüfter an GPIO 6 mit Ein- und Ausschaltgrenze), lädt `i2c-dev` und gibt dem Dienstbenutzer die Gruppen `i2c`, `spi`, `gpio`. Eine Kopie der alten Datei bleibt als `config.txt.speech-spark-alt`. **Entfernen** nimmt nur diesen Block wieder heraus.
- **Display** (SSD1306, 128×64) wechselt alle paar Sekunden zwischen vierzehn Seiten: Spark, Dienste und Wartung, Pi (Temperatur, Last, Speicher), DGX weg oder in Pause, Netz, DGX im Detail (GPU-Temperatur, freier Speicher, geladenes Sprachmodell), Sicherheit (falsche Anmeldungen und vom Wächter geblockte Verbindungen heute, solange Live an ist, Notaus-Stufe), Geräte (Lautsprecher und Apps verbunden, Verbund), Haus (Home Assistant, Synology, Kiwix, Suche laut Dienst-Wächter), Strom (Unterspannung und Drosselung des Pi, Laufzeit), Version (Pi und DGX gleich oder abweichend) und Aktiv 10 min (wie viele Menschen in den letzten 10 Minuten eine Anfrage gestellt haben, als große Zahl, daneben Profile und Gäste; ein Profil zählt einmal, auch auf mehreren Geräten, ein Gast je Gerät; was der Spark von selbst tut, zählt nie; nur im Arbeitsspeicher, ohne Namen, auch wenn Logs und Live aus sind). Dazu „Pi“ und „TARS“: CPU- und RAM-Auslastung in Prozent als zwei große Zahlen, CPU links, RAM rechts (die TARS-Seite nur, wenn die Modelle auf einem zweiten Rechner laufen; beim TARS zählt der RAM den gemeinsamen Speicher mit den geladenen Modellen, er steht deshalb oft bei 70 bis 90 %). Die Zahl der Aktiven steht auch unter Zustand → Überblick („Aktiv (10 min)“), in Zustand → Live, in der Steuerzentrale und im Zustand der iPhone-App. Ist der DGX weg oder pausiert, kommt seine Seite zuerst; bei einem Problem die Dienste. Wechselt oder startet das Sprachmodell, kommt die Seite Spark zuerst und zeigt unten den Schritt, etwa „LLM wechselt (4/6)“. Unter Funktionen → Gehäuse stehen alle Seiten als kleine Bilder mit den Werten von jetzt, genau wie am Display gezeichnet: Antippen schaltet eine Seite an oder aus, Ziehen oder ◀ ▶ ändert die Reihenfolge, das große Bild zeigt, was gerade am Display steht. Das Bild lässt sich um 180° drehen (die Vorschau bleibt aufrecht), „nur bei Problemen“ hält es sonst dunkel. Läuft ein Update, hält das Display den Wechsel an und zeigt nur „Update TARS“ bzw. „Update Pi“ mit großer Prozentzahl, Balken und Schritt (ein Balken für beide: TARS bis 30 %, dann der Pi bis 100 %), auch nachts und bei „nur bei Problemen“, nachts gedimmt; die LEDs leuchten dabei blau. Gegen Ende startet das Panel neu, dann bleibt das letzte Bild ein paar Sekunden stehen. Danach steht eine Minute „Update fertig“ oder „Fehler“, dann geht der Wechsel weiter. Nachtbetrieb: aus, dunkel oder ganz aus zwischen zwei Stunden. Gegen Einbrennen wandert der Inhalt alle 3 Minuten um ein bis zwei Punkte, und ein Bild, das sich 10 Minuten nicht ändert, wird dunkler.
- **LEDs**: grün = alles läuft, gelb = Pause, Hinweis, ein Dienst fehlt oder das Sprachmodell wechselt, rot = DGX nicht erreichbar.
- **Lüfter** steuert der Kernel selbst (Overlay `gpio-fan`); die Grenzen gelten nach dem nächsten Einrichten und Neustart.

Das Panel schreibt nie selbst in Systemdateien: es legt einen Wunsch ab und startet die feste Einheit `speech-spark-gehaeuse`, die den Wunsch noch einmal prüft und den Block aus zwei Zahlen selbst schreibt. Prüfen mit `sudo speech-spark gehaeuse status`; der Live-Kasten „Gehäuse“ zeigt Display, LEDs und Seite, die Logs stehen im Bereich „gehaeuse“.

## Beide Rechner im Monitoring

Laufen Panel und Modelle getrennt, zeigt Zustand → Überblick beide Rechner gleichwertig: oben je eine Kachel (Modell-Rechner mit freiem Speicher, GPU und CPU; Panel-Rechner mit belegtem Arbeitsspeicher, CPU, Temperatur und Platte) und darunter unter „Rechner“ zwei Karten nebeneinander mit Kurven der letzten 20 Minuten:

- **Modell-Rechner**: GPU mit Temperatur und Leistung, Unified Memory mit der 8-GiB-Grenze, CPU, Platte, Netz, das laufende Sprachmodell und seine Dienste. Die Werte schickt der Wärter mit seinem Zustand.
- **Panel-Rechner**: CPU, Arbeitsspeicher (belegt, verfügbar, Cache), Temperatur und Lüfter, Speicherkarte oder SSD, Netz, Strom (Unterspannung und Drosselung des Raspberry Pi) und seine Dienste, dazu „Panel hing“: wie oft der Hänge-Wächter das Panel in den letzten 24 Stunden stillstehen sah, und wie lange längstens ([Sicherheit und Betrieb](sicherheit-und-betrieb.md)).

Antwortet der Modell-Rechner nicht, bleibt seine Karte stehen, rot mit „antwortet nicht seit …“ und den letzten Werten grau. Unter „Braucht dich“ meldet sich das Panel mit festen Regeln: Panel-Rechner ab 80 °C, gedrosselt oder mit zu wenig Strom, weniger als 0,5 GiB Arbeitsspeicher frei; auf jedem Rechner weniger als 10 % Platte frei; der Modell-Rechner antwortet nicht. Jeder Hinweis führt zu den Karten. Dasselbe zeigen Zustand → Live (Kasten „Panel-Rechner“, CPU des Panel-Rechners neben der des Modell-Rechners), die iPhone-App unter Monitoring und die Android-App über die Panel-Ansicht. Gezeigt werden nur Zahlen und feste Wörter, nie Adressen oder Prozesse; auf einem einzelnen Spark bleibt die Seite wie bisher. Logs im Bereich „system“ (`rechner: hinweis …`).

## Steuerzentrale am Bildschirm

Ein Bildschirm am HDMI-Ausgang des Panel-Rechners zeigt die Steuerzentrale: alles auf einer Anzeige, als reiner Text ohne Desktop und Browser (etwa 20 MB). Einschalten unter Funktionen → Steuerzentrale am Bildschirm; danach startet sie bei jedem Booten von selbst auf dem ersten Bildschirm, ohne Anmeldung. Ausschalten beendet sie, und die normale Anmeldung kommt zurück.

- **Oben**: Gesamtzustand, laufende Anfragen, Hinweise, Wartung und Version, darunter die Zahlen des Tages (Antworten, erster Ton, Wächter, Eingang, Sicherung, Zeiten des Bildschirms).
- **Mitte**: die Stufen Hören, Weiche, Sprachmodell, Werkzeuge und Sprechen im Rahmen des Rechners, auf dem sie laufen; bei Spark teilen tars und Pi nebeneinander mit CPU, GPU, Arbeitsspeicher, Temperatur und 20-Minuten-Kurve. Jede laufende Anfrage hat eine eigene Farbe und springt sichtbar zwischen den Rechnern hin und her; die Wege laufen unter den Kästen durch, und eine fertige Antwort bleibt mit „fertig in … s“ stehen wie in der Live-Übersicht. Im Kasten Werkzeuge steht jedes benutzte Werkzeug in der Farbe seiner Anfrage, mit ▶ läuft, ✓ fertig oder ✗ Fehler; bei Full HD ein Name und „+N“ für die übrigen. Läuft gerade nichts, stehen dort die zuletzt benutzten Werkzeuge mit ✓ oder ✗ (bei 4K mit Uhrzeit). Jeder Kasten hat eine dunkle Farbfläche in seiner Farbe und runde Ecken (eigene Farbtafel der Konsole, beim Beenden zurückgesetzt); die Rahmen der beiden Rechner bleiben dunkel.
- **Links** die Geräte mit Anfrage, die verbundenen Geräte und Zugriffe über das Internet; **rechts** die Dienste und Ziele der Live-Übersicht, die gerade benutzt werden (die übrigen in einer Zeile „+ N bereit“ und „+ N ruhig“, wie in Zustand → Live), das Internet hinter dem Wächter, „Braucht dich“, Modelle und Dienste, die letzten Ereignisse, Sicherheit und Wartung.
- **Unten** die letzten 20 Minuten als Kurven (GPU, CPU, freier Speicher, Temperatur) und die Antworten je Stunde.

Die Größe richtet sich nach dem Bildschirm: Beim Start und wenn sich die Auflösung ändert, wählt die Anzeige eine Terminus-Schrift für mindestens 160 × 45 Zeichen (Full HD etwa 160 × 45, 4K mit doppelt so großer Schrift etwa 240 × 67); „kleiner“ oder „größer“ nimmt die nächste Schrift. Auf einem sehr kleinen Bildschirm erscheint eine knappe Liste ohne Fluss. Zeichen, die die Schrift nicht kennt, ersetzt sie durch einfache Zeichen. Zwischen „Anzeige aus ab“ und „Anzeige an ab“ (Standard 23 bis 7 Uhr, zweimal dieselbe Stunde heißt immer an) schaltet sie den Bildschirm dunkel, der Monitor geht in den Ruhezustand. Gegen Einbrennen wandert das Bild alle 3 Minuten um ein bis zwei Zeichen.

Gezeigt werden nur Art, Ort, Zeit und Zahlen, nie Fragen, Antworten oder Namen: Es sieht jeder im Raum. Die Anzeige fragt jede Sekunde nur das Panel auf demselben Rechner (127.0.0.1) mit einem eigenen Schlüssel, den nur der Dienstbenutzer lesen kann; von anderen Rechnern oder über einen Proxy antwortet das Panel nicht. Eine langsame Antwort (bis 8 Sekunden) oder ein kurzer Aussetzer lässt das letzte Bild stehen; erst nach fünf Fehlversuchen in Folge zeigt sie „Panel weg“. Neue Dienste der Live-Übersicht erscheinen von selbst. Zustand → Live zeigt im Kasten „Steuerzentrale“, ob sie gerade zeigt; der Dienst-Wächter meldet, wenn sie nicht mehr fragt. Logs im Bereich „system“ (`schirm: …`).

## Prüfen und Fehler suchen

| Was | Befehl |
|---|---|
| Tür, Firewall, Fingerabdruck, Modell-Rechner | `sudo speech-spark teilen status` (auf beiden Rechnern) |
| Weg einmal ganz prüfen | `sudo speech-spark teilen rundlauf` (auf dem Panel-Rechner) |
| Logs der Tür und des Wärters | `sudo speech-spark logs tlstor`, `sudo speech-spark logs waerter` (auf dem DGX) |
| Neu koppeln (neuer Panel-Rechner, neues Zertifikat) | DGX: `sudo speech-spark teilen code`, Panel-Rechner: `sudo speech-spark teilen koppeln <IP-des-DGX>` |

Der Live-Kasten „Modell-Rechner“ zeigt, ob der DGX erreichbar ist, wie viele Dienste laufen, seine Version und eine Pause. Technik dazu: [Sicherheit und Betrieb](sicherheit-und-betrieb.md) und [Architektur](architektur.md).
