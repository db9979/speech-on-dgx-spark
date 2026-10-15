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
   - bei jedem ESP32-Lautsprecher die neue Server-Adresse.

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
- **Display** (SSD1306, 128×64) wechselt alle paar Sekunden zwischen den Seiten Spark, Dienste und Wartung, Pi (Temperatur, Last, Speicher), DGX weg oder in Pause, Netz. Ist der DGX weg oder pausiert, kommt diese Seite zuerst; bei einem Problem die Dienste. Seiten lassen sich abwählen, das Bild um 180° drehen, „nur bei Problemen“ hält es sonst dunkel. Nachtbetrieb: aus, dunkel oder ganz aus zwischen zwei Stunden.
- **LEDs**: grün = alles läuft, gelb = Pause, Hinweis oder ein Dienst fehlt, rot = DGX nicht erreichbar.
- **Lüfter** steuert der Kernel selbst (Overlay `gpio-fan`); die Grenzen gelten nach dem nächsten Einrichten und Neustart.

Das Panel schreibt nie selbst in Systemdateien: es legt einen Wunsch ab und startet die feste Einheit `speech-spark-gehaeuse`, die den Wunsch noch einmal prüft und den Block aus zwei Zahlen selbst schreibt. Prüfen mit `sudo speech-spark gehaeuse status`; der Live-Kasten „Gehäuse“ zeigt Display, LEDs und Seite, die Logs stehen im Bereich „gehaeuse“.

## Prüfen und Fehler suchen

| Was | Befehl |
|---|---|
| Tür, Firewall, Fingerabdruck, Modell-Rechner | `sudo speech-spark teilen status` (auf beiden Rechnern) |
| Weg einmal ganz prüfen | `sudo speech-spark teilen rundlauf` (auf dem Panel-Rechner) |
| Logs der Tür und des Wärters | `sudo speech-spark logs tlstor`, `sudo speech-spark logs waerter` (auf dem DGX) |
| Neu koppeln (neuer Panel-Rechner, neues Zertifikat) | DGX: `sudo speech-spark teilen code`, Panel-Rechner: `sudo speech-spark teilen koppeln <IP-des-DGX>` |

Der Live-Kasten „Modell-Rechner“ zeigt, ob der DGX erreichbar ist, wie viele Dienste laufen, seine Version und eine Pause. Technik dazu: [Sicherheit und Betrieb](sicherheit-und-betrieb.md) und [Architektur](architektur.md).
