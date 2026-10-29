# Speech auf DGX Spark

[English](README.md) | **Deutsch** · Idee: Dominik Bornhäußer

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/zquu1xu570)

Spracherkennung (**Qwen3-ASR**), Sprachausgabe (**Qwen3-TTS**), Bilder (**FLUX.2 klein**) und ein eigenes Sprachmodell (**vLLM**) als Dienste auf einer NVIDIA DGX Spark (GB10), dazu ein Webportal mit Sprach-Assistent, Profilen und Monitoring. Läuft nativ mit systemd, ohne Docker. Das Portal läuft auf dem Spark selbst oder auf einem kleinen eigenen Rechner wie einem Raspberry Pi 5. Statt des eigenen Sprachmodells kann weiterhin [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38) es liefern.

| Assistent | Zustand | Technik |
|---|---|---|
| [![Assistent](docs/bilder/de-chat.png)](docs/bilder/de-chat.png) | [![Zustand](docs/bilder/de-zustand.png)](docs/bilder/de-zustand.png) | [![Technik](docs/bilder/de-technik.png)](docs/bilder/de-technik.png) |

## Installation

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

Das Skript fragt, was installiert werden soll:

- **Komplett**: Modelle, APIs und das Webportal mit dem Assistenten.
- **Nur die Modelle mit ihren APIs**: für Open WebUI, eigene Apps oder Home Assistant, ohne Portal. Verwaltet wird dann mit `sudo speech-spark`.
- **Geteilt** (Spark teilen): das Panel auf einem eigenen Rechner wie einem Raspberry Pi 5, der DGX liefert nur die Modelle. Anleitung, auch zum Umziehen: [Spark teilen](docs/de/spark-teilen.md).

Am Ende stehen Adresse, Passwort und API-Schlüssel auf dem Bildschirm, danach spricht die Sprachausgabe einen Satz und die Spracherkennung prüft ihn. Das Portal liegt auf `https://SPARK:31443` (https ist nötig, damit der Browser das Mikrofon freigibt).

| Aufgabe | Befehl |
|---|---|
| Aktualisieren | Knopf im Portal unter *Einstellungen → Update* oder `sudo speech-spark update` |
| Adressen und Schlüssel anzeigen | `sudo speech-spark info` |
| Eigenes Sprachmodell | `sudo ./install.sh --llm`, danach `sudo speech-spark modelle llm uebernehmen` (zurück: `… zurueck`) |
| Werkstatt (Testlauf, Code-Messung, Diagnose, Reparatur) | auf dem Modell-Rechner `sudo ./install.sh --werkstatt`, dann *Funktionen → Werkstatt* |
| Bildschirm im Fernzugang (guacd) | auf dem Rechner mit dem Panel `sudo ./install.sh --fernbild`, dann *Funktionen → Fernzugang zu Servern → Bildschirm* |
| Portal auf einen anderen Rechner umziehen | `sudo speech-spark umziehen --code`, siehe [Spark teilen](docs/de/spark-teilen.md) |
| Deinstallieren | `sudo ./uninstall.sh` (Konfiguration, Modelle und Stimmen bleiben; `--purge` löscht alles) |

Alle Optionen ohne Rückfragen (`--mode api --asr 1.7b --tts 0.6b --yes` …) stehen in [Installation im Detail](docs/de/installation.md).

## Letzte Änderungen

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.1.228** Fernzugang Ziel-Modus: „Als Ziel verfolgen“ heftet die Frage an den Assistenten an; nach jedem eigenen Befehl schlägt das eigene Sprachmodell genau einen nächsten Befehl mit Grund vor, bis „Fertig“ oder „Ziel beenden“ (nur mit „Bildschirm mitschicken“, nie Enter, höchstens 6 je Minute, derselbe Bildschirm nicht zweimal); dazu wählt „Zeilen“ 80, 300 oder 1000 Zeilen (chat.fernzugang_ki_zeilen, höchstens 60 000 Zeichen, sonst „gekürzt“)
- **V01.1.227** Spontanhilfe-Seite aufgeräumt (Variante A): Liste links wie bei Systeme (Läuft, Verlauf), rechts nur der nächste Schritt mit vier Punkten, Nummer mit Countdown-Ring, Neue Nummer und Verwerfen, die Wege Link, E-Mail und Shell als Reiter mit nur einer Zeile; Zeigepfeil und Vollbild erst beim Teilen, bei 0:00 Abgelaufen – Neue Nummer; Meldungen als Einblendung statt Textzeile, auch bei Systeme
- **V01.1.226** Fernzugang hält die Verbindung: Lebenszeichen alle 20 s und SSH-Keepalive; reißt die Leitung ab, bleibt die Shell 2 Minuten mit ihrer letzten Ausgabe offen und die Seite verbindet sich still wieder (neues Einmal-Ticket, dieselbe Anmeldung, entsperrt); Countdown vor Leerlauf, Entsperrung und Spontanhilfe-Ende mit Weiterarbeiten oder Verlängern; jede End-Meldung nennt den Grund und bietet Neu verbinden
- **V01.1.225** Fernzugang Stufe 4 Bildschirm: „Bildschirm“ zeigt den Bildschirm eines gekoppelten Systems im Browser (X11, GNOME auf Wayland, andere Wayland-Oberflächen, macOS), erst nur ansehen, „Steuern“ mit einem Klick; guacd als eigener Dienst nur auf 127.0.0.1 (install.sh --fernbild), höchstens 15 Bilder/s, „Sparsam“ mit 16 Bit und ein Hinweis bei langsamer Leitung; dazu sagen die Befehls-Vorschläge beim Zeigen, was sie tun, und das Fragefeld des Assistenten leert sich nach dem Senden
- **V01.1.224** Spontanhilfe: die Einladung „Per E-Mail“ kommt im neuen Design „Karte“ (Text und HTML, per du, Deutsch oder Englisch, ohne Bilder von außen) und nur einmal je Hilfe und Adresse: der Knopf ist beim Senden aus (mit Kreisel), ein zweiter Klick bekommt „Einladung schon gesendet“, „Nochmal senden“ erst nach 60 Sekunden mit Rückfrage, und eine unvollständige Einladung geht nie hinaus
- **V01.1.223** Spontanhilfe Stufe S3 Shell einmalig: für einen Server ohne Bildschirm fügt die Person eine Zeile (ohne sudo) in ihr Terminal ein, tippt dort Nummer und Vornamen und erlaubt mit „j“; dann arbeitet der Admin im Reiter Spontanhilfe in ihrer Shell, mit ihren Rechten, und nichts bleibt zurück
- **V01.1.222** Fernzugang Stufe 3 Dateien: auf der entsperrten Seite öffnet „Dateien“ ohne neuen Code die Ordner des Servers über SFTP in derselben SSH-Verbindung (Ordner öffnen, Laden über einen Einmal-Link, Hochladen bis zur eingestellten Größe, Standard 100 MB, „Ersetzen“ nur auf Wunsch); was geht, entscheiden die Rechte des Benutzers spark; Sperren schließt die Dateien, im Protokoll nie ein Name
- **V01.1.221** Spontanhilfe Stufe 1 (eigener Schalter unter Fernzugang, aus): einmal helfen wie TeamViewer QuickSupport, als Reiter der entsperrten Seite Fernzugang; „Neue Hilfe“ gibt eine 6-stellige Nummer (10 Minuten, einmal, 5 Fehlversuche) und einen Link (30 Minuten, einmal) zum Kopieren, Teilen, als QR oder per E-Mail vom eigenen Konto; die Person öffnet /hilfe ohne Anmeldung und ohne Installation, der Admin nimmt an, sie teilt selbst ihren Bildschirm (WebRTC, eigener Vermittler); Chat und Zeigen, 60 Minuten mit „Verlängern“ (Code) bis zur Höchstdauer (Standard 180), „Gerade verbunden“, Live, Verlauf ohne Namen, nichts aufgezeichnet, nichts ans Modell
- **V01.1.220** Fernzugang: ein Code oder Passkey entsperrt die Seite für 60 Minuten (nur dieser Browser, sperrt bei Sperren, Abmelden, Ortswechsel und Notaus; Koppeln und Entfernen fragen weiter jedes Mal), neue Seite im Layout A (Liste und gewähltes System, Statuszeile, Koppeln als Blatt, passt ohne Scrollen, Handy wie die iPhone-Einstellungen); ein Sprung gleich nach dem Laden bleibt auf seiner Seite
- **V01.1.219** ROT-FIX: Tests auf GitHub fest auf ubuntu-24.04 (ubuntu-latest ist jetzt 26.04, dort installiert Playwright kein Chromium; der Lauf zu V01.1.218 war rot, bevor ein Test lief)




Alle Versionen: [CHANGELOG.md](CHANGELOG.md)

## So funktioniert es

```mermaid
flowchart LR
  subgraph Clients["Geräte und Apps"]
    B["Browser und Handy,<br/>iPhone- und Android-App,<br/>Begleiter für Windows/Mac"]
    T["Terminal-Client spark-tui<br/>z. B. auf der uConsole"]
    X["ESP32-Lautsprecher,<br/>HA Assist über Wyoming :31003,<br/>Telefon (SIP), Telegram,<br/>Siri, Pebble"]
    M["MCP-Programme<br/>Claude, n8n, Open WebUI"]
  end
  subgraph Panel["Panel-Rechner: der Spark oder ein Raspberry Pi 5"]
    G["Webportal :31443<br/>Anmeldung, 2FA, Passkeys,<br/>Profile, Freigaben"]
    R["Weiche: Werkzeugwahl<br/>nach festen Regeln"]
    K["Eigenes Wissen: Dokumente,<br/>reMarkable, Gedächtnis"]
    S["Wächter netguard<br/>nur erlaubte Ziele"]
    LOG["Anfrage-Verlauf, Live,<br/>Sicherung, Update nach Test"]
    NB["Notbetrieb mit Parakeet,<br/>wenn der DGX weg ist"]
  end
  subgraph Spark["DGX Spark: Modellrechner"]
    ASR["Spracherkennung :31001<br/>Qwen3-ASR oder Parakeet"]
    TTS["Sprachausgabe :31002<br/>Qwen3-TTS, eigene Stimmen"]
    LLM["LLM-Tor :31006<br/>eigenes Sprachmodell (vLLM)"]
    IMG["Bilder :31005<br/>FLUX.2 klein"]
    MUS["Musik :31004<br/>ACE-Step 1.5"]
    WS["Werkstatt: Sandbox ohne Netz<br/>und Daten, Tests und OpenCode"]
  end
  subgraph Out["Dienste und Quellen"]
    E["Home Assistant, Kalender,<br/>Mail, Wetter, Pakete, ÖPNV"]
    Q["SearXNG, Kiwix, Wikipedia,<br/>reMarkable-Cloud, MCP-Server"]
  end
  A["Open WebUI, eigene Apps"]
  B --> G
  T --> G
  X --> G
  M -->|"MCP-Server /mcp"| G
  G --> R
  R --> K
  R --> S
  S --> E
  S --> Q
  G ==>|"Ton, Text, Bilder;<br/>getrennt über das TLS-Tor"| Spark
  A -->|"API-Schlüssel"| Spark
```

1. Du sprichst ins Handy, in den Browser, in eine der Apps, den Terminal-Client, einen Lautsprecher oder ins Telefon. Das Portal meldet dich an, schickt den Ton an die **Spracherkennung** und bekommt Text zurück.
2. Die **Weiche** wählt nach festen Regeln, welche Werkzeuge die Frage braucht. Das Portal gibt den Text mit Gedächtnis, Gesprächsverlauf, eigenem Wissen und genau diesen Werkzeugen an das **Sprachmodell** hinter dem LLM-Tor (oder an qwen38, wenn du es behältst).
3. Braucht die Antwort Kalender, Mail, Wetter, Home Assistant, Websuche, Kiwix oder Wikipedia, holt das Portal die Daten selbst; schalten und eintragen geht nur nach Bestätigung. Bilder malt und ändert FLUX.2 klein auf dem Spark; Musik macht ACE-Step 1.5 (zuerst nur „Musik testen“ für den Admin unter Zustand → Prüfen).
4. Die Antwort geht Satz für Satz an die **Sprachausgabe** und wird gestreamt abgespielt, während das Modell noch schreibt. Der Vorrang sorgt dafür, dass gesprochene Antworten und wichtige Personen zuerst drankommen.
5. Mit **Spark teilen** liegen Portal, Profile, Chats und Anrufe auf dem kleinen Rechner und erreichen die Modelle nur über das TLS-Tor. Startet der DGX neu oder ist er aus, laufen Chats, Erinnerungen und Anrufe weiter, und der Notbetrieb versteht ein paar feste Befehle ohne Sprachmodell.
6. Andere Apps nutzen ASR und TTS direkt über die OpenAI-ähnlichen APIs mit API-Schlüssel, MCP-Programme den Spark als MCP-Server mit eigenem Zugang.

Jede neue Funktion ist ab Werk aus. Gibt der Admin sie frei, gilt sie sofort für jedes Profil; nur der Admin kann einzelne Profile sperren. Gäste bekommen nur Frage und Antwort, nie ein Werkzeug. Updates laufen erst nach grünem Selbsttest und lassen sich zurücknehmen.

## Weiterlesen

- [Installation im Detail](docs/de/installation.md): Installationsarten, Befehl `speech-spark`, alle Optionen, Update, Deinstallieren
- [Spark teilen](docs/de/spark-teilen.md): das Portal auf einem eigenen Rechner wie einem Raspberry Pi 5, Umziehen, Notbetrieb
- [Assistent und Oberfläche](docs/de/assistent.md): Sprach-Chat, Handy, Funktionen, Menü
- [APIs und Einbinden](docs/de/apis-und-einbinden.md): Transkription, Sprachausgabe, Streaming, Open WebUI, Siri, Pebble, Terminal-Client
- [iPhone-App](docs/de/iphone-app.md) und [Android-App](docs/de/android-app.md): Chat, Anrufe, Panel-Bereiche auf dem Handy
- [Sicherheit und Betrieb](docs/de/sicherheit-und-betrieb.md): Anmeldung, Sperren, Sicherungen, Wächter, Selbsttest, Logs
- [Architektur](docs/de/architektur.md): Bausteine, Weg einer Anfrage, alle Speicherorte (auch im Panel unter Zustand → Technik)
- [Technik und Fehlersuche](docs/de/technik.md): Dienste und Ports, Leistung messen, eigenes Sprachmodell oder qwen38, Fehlersuche
- [Coding-Richtlinie](docs/de/richtlinien.md) und [Sicherheits-Checkliste](docs/de/sicherheits-checkliste.md): Regeln für jede Änderung, Pflichtliste für neue Funktionen

Im Portal steht zu jeder Funktion eine eigene Anleitung unter *Funktionen → Anleitungen*.

## Unterstützen

Das Projekt ist kostenlos. Wenn es dir gefällt, kannst du es über [buymeacoffee.com/zquu1xu570](https://buymeacoffee.com/zquu1xu570) unterstützen.

## Lizenz

FSL-1.1-MIT (Functional Source License), siehe [LICENSE](LICENSE). Du darfst den Spark nutzen, lesen, ändern und weitergeben, für dich, deine Familie und Freunde, in Lehre und Forschung; nicht erlaubt ist nur, ihn als kommerzielles Konkurrenzangebot zu vertreiben. Jede Version wird zwei Jahre nach ihrer Veröffentlichung von selbst MIT. Versionen bis V01.0.542 stehen weiter unter MIT. Eingebundene fremde Teile (z. B. XiaoZhi-Firmware, Lucide-Symbole) behalten ihre eigene Lizenz. Die Modelle (Qwen3-ASR, Qwen3-TTS) und Pakete (vLLM, vllm-omni, PyTorch) werden bei der Installation geladen und stehen unter ihren eigenen Lizenzen. Dieses Projekt steht in keiner Verbindung zu NVIDIA oder dem Qwen-Team.
