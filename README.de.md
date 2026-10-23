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
| Portal auf einen anderen Rechner umziehen | `sudo speech-spark umziehen --code`, siehe [Spark teilen](docs/de/spark-teilen.md) |
| Deinstallieren | `sudo ./uninstall.sh` (Konfiguration, Modelle und Stimmen bleiben; `--purge` löscht alles) |

Alle Optionen ohne Rückfragen (`--mode api --asr 1.7b --tts 0.6b --yes` …) stehen in [Installation im Detail](docs/de/installation.md).

## Letzte Änderungen

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.951** ROT-FIX: jedes apt wartet jetzt per DPkg::Lock::Timeout auf die dpkg-Sperre, damit der Install nicht an unattended-upgrades („Could not get lock … code 100“) rot fällt
- **V01.0.950** Tests-Workflow robuster: Install-Netzschritte mit Timeout und drei Versuchen, damit hängende Runner nicht ins 45-min-Limit laufen
- **V01.0.949** KI-Dungeon-Master (Schalter, aus): Rollenspiel für bis zu fünf, auch Gäste per Link; Beute, Stufen, Tauschen und Helden zum Mitnehmen, Regeln vom Admin anpassbar
- **V01.0.948** ROT-FIX: der Angriffs-Selbsttest für das Tagesbriefing hing von der Uhrzeit um Mitternacht ab; sein Termin gilt jetzt unabhängig von Uhrzeit und Zeitzone als „heute“
- **V01.0.947** IT-Krisenspiel wieder entfernt (auf Wunsch): Spiel, Netzduell und Spielprofile „Nur Krisenspiel“
- **V01.0.946** Satzende am Tonfall (Schalter, aus): Smart Turn auf dem Modell-Rechner misst an jeder Sprechpause, ob du fertig klingst; nur Zahlen, entscheidet noch nichts, Auswertung nach 200 Pausen oder 7 Tagen unter dem Schalter
- **V01.0.945** Spielprofile „Nur Krisenspiel“: Mitspieler ohne Assistent
- **V01.0.944** Ins Wort fallen: erst anhalten auch in der iPhone-App: ein „mhm“ pausiert die Antwort nur, „Stopp“ beendet sie, ein Satz wird die neue Frage; ohne Entscheidung nach 4 s läuft sie weiter
- **V01.0.943** IT-Krisenspiel (Paket 9): Kampagnen über mehrere Spieltage, Folgen wirken ins nächste Kapitel
- **V01.0.942** Ins Wort fallen: erst anhalten (Schalter, aus): ein „mhm“, Husten oder die eigene Stimme hält die Antwort nur an und sie läuft weiter, „Stopp“ beendet sie, ein echter Satz wird die neue Frage; feste Wörter im Panel, nie das Modell; Browser und Android, iPhone folgt




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
