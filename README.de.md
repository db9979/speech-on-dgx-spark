# Speech auf DGX Spark

[English](README.md) | **Deutsch** · Idee: Dominik Bornhäußer

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/zquu1xu570)

Spracherkennung (**Qwen3-ASR**) und Sprachausgabe (**Qwen3-TTS**) als Dienste auf einer NVIDIA DGX Spark (GB10), dazu ein Webportal mit Sprach-Assistent, Profilen und Monitoring. Läuft nativ mit systemd, ohne Docker, neben [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38), das das Sprachmodell liefert.

## Installation

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

Das Skript fragt, was installiert werden soll:

- **Komplett**: Modelle, APIs und das Webportal mit dem Assistenten.
- **Nur die Modelle mit ihren APIs**: für Open WebUI, eigene Apps oder Home Assistant, ohne Portal. Verwaltet wird dann mit `sudo speech-spark`.

Am Ende stehen Adresse, Passwort und API-Schlüssel auf dem Bildschirm, danach spricht die Sprachausgabe einen Satz und die Spracherkennung prüft ihn. Das Portal liegt auf `https://SPARK:31443` (https ist nötig, damit der Browser das Mikrofon freigibt).

| Aufgabe | Befehl |
|---|---|
| Aktualisieren | Knopf im Portal unter *Einstellungen → Update und Sicherung* oder `sudo speech-spark update` |
| Adressen und Schlüssel anzeigen | `sudo speech-spark info` |
| Deinstallieren | `sudo ./uninstall.sh` (Konfiguration, Modelle und Stimmen bleiben; `--purge` löscht alles) |

Alle Optionen ohne Rückfragen (`--mode api --asr 1.7b --tts 0.6b --yes` …) stehen in [Installation im Detail](docs/de/installation.md).

## Letzte Änderungen

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.411** Live-Seite zum Bedienen: Ereignisse mit Bereichs-Knöpfen, Suche und Anhalten, Klick zeigt die Stelle im Bild; Kasten im Bild öffnet Zahlen der letzten Stunde, ⚠ mit Erklärung und Weg zur Abhilfe; letzte 15 Minuten zurückspulen; Weg kopieren oder in Anfragen öffnen; Selbst-Notaus-Zähler; Begleiter-Aufträge und Sofort-Satz als Weg im Bild; Monitor hält per Tippen an
- **V01.0.410** Begleiter: „Öffne Safari mit Google“ am Mac wird jetzt wirklich ausgeführt (mit Rückfrage), nicht nur angekündigt
- **V01.0.409** Sprachausgabe abschaltbar: „Antworten vorlesen“ pro Profil und „Vorlesen“ je Gerät, aus = nur Text (Lautsprecher und CarPlay sprechen weiter)
- **V01.0.408** Unabhängige Prüfung, Paket 5: Englisch vollständiger, verständliche Fehlersätze, „?“ nur mit Hilfe, aktuelle Seitennamen, Labels, Live aus ohne Fehler
- **V01.0.407** Unabhängige Prüfung, Paket 4: signierbare Geräte-Updates, Begleiter nur https, feste CI-Versionen, root-Lesewege, ffmpeg-Grenzen, iPhone-Kopplung, Telegram
- **V01.0.406** Unabhängige Prüfung, Paket 6: Seiten-Dateien gepackt und gecacht, sichere JSON-Schreiber, schnellere Selbsttests, toter Code entfernt
- **V01.0.405** Unabhängige Prüfung, Paket 3: schnellere Verbindungen, Panel blockiert nicht mehr, Sprachausgabe übersteht Neustart, Frist fürs erste Wort, keine verlorenen Nachrichten
- **V01.0.404** Antwort kommt nicht mehr doppelt mit „</think>“ dazwischen: das Nachdenken wird nie gezeigt oder vorgelesen
- **V01.0.403** Unabhängige Prüfung, Paket 2: Zugriffslücken geschlossen (Codes für Sicherung und Geräte, fremde Stimmen als „von außen“, Wiederherstellen behält Admin-Passwort, API-Doku aus, Gast-Grenzen, MCP)
- **V01.0.402** Unabhängige Prüfung, Paket 1: lange Nachrichten bremsen nicht mehr, Abtastrate geprüft, Aufträge behalten Privates, Sperre, ESP32-Flashen, Zeitumstellung

Alle Versionen: [CHANGELOG.md](CHANGELOG.md)

## So funktioniert es

```mermaid
flowchart LR
  subgraph Clients["Geräte und Apps"]
    B["Browser und Handy<br/>App-Ansicht, Mitteilungen"]
    APP["iPhone-App mit CarPlay,<br/>Android-App"]
    X["Pebble, Telegram, Siri,<br/>Raumlautsprecher ESP32"]
    W["HA Assist<br/>Wyoming :31003"]
    M["MCP-Programme<br/>Claude, n8n, Open WebUI"]
    A["Open WebUI, eigene Apps"]
  end
  subgraph Spark["DGX Spark"]
    subgraph P["Webportal :31443"]
      G["Anmeldung, 2FA, Passkeys,<br/>Profile, Rollen, Einladungen"]
      R["Weiche: Werkzeugwahl<br/>nach festen Regeln"]
      V["Vorrang für Sprache<br/>und Personen"]
      K["Eigenes Wissen: Uploads,<br/>reMarkable, Gedächtnis"]
      LOG["Anfragen-Log, Sicherung,<br/>Update nach grünem Test"]
      S["Wächter netguard<br/>nur erlaubte Ziele"]
    end
    ASR["ASR :31001<br/>Qwen3-ASR oder Parakeet"]
    TTS["TTS :31002<br/>Qwen3-TTS, eigene Stimmen"]
    subgraph Q38["dgx-spark-qwen38"]
      LLM["Sprachmodell :30001<br/>Text und Bilder"]
    end
  end
  subgraph Out["Dienste und Quellen"]
    E["Home Assistant, Kalender, Mail,<br/>Wetter, Pakete, Nahverkehr"]
    Q["SearXNG, Kiwix, Wikipedia,<br/>reMarkable-Cloud, MCP-Server"]
  end
  B --> G
  APP --> G
  X --> G
  W --> G
  M -->|"MCP-Server /mcp"| G
  A --> ASR
  A --> TTS
  G --> V
  G --> R
  V --> ASR
  V --> TTS
  R --> LLM
  R --> K
  R --> S
  S --> E
  S --> Q
```

1. Du sprichst ins Handy, in den Browser, in eine der Apps oder einen Lautsprecher. Das Portal meldet dich an, schickt den Ton an die **Spracherkennung** und bekommt Text zurück.
2. Die **Weiche** wählt nach festen Regeln, welche Werkzeuge die Frage braucht. Das Portal gibt den Text mit Gedächtnis, Gesprächsverlauf, eigenem Wissen und genau diesen Werkzeugen an das **Sprachmodell** von qwen38.
3. Braucht die Antwort Kalender, Mail, Wetter, Home Assistant, Websuche, Kiwix oder Wikipedia, holt das Portal die Daten selbst; schalten und eintragen geht nur nach Bestätigung.
4. Die Antwort geht Satz für Satz an die **Sprachausgabe** und wird gestreamt abgespielt, während das Modell noch schreibt. Der Vorrang sorgt dafür, dass gesprochene Antworten und wichtige Personen zuerst drankommen.
5. Andere Apps nutzen ASR und TTS direkt über die OpenAI-ähnlichen APIs mit API-Schlüssel, MCP-Programme den Spark als MCP-Server mit eigenem Zugang.

Jede Funktion ist pro Profil einzeln schaltbar und ab Werk aus. Updates laufen erst nach grünem Selbsttest und lassen sich zurücknehmen.

## Weiterlesen

- [Installation im Detail](docs/de/installation.md): Installationsarten, Befehl `speech-spark`, alle Optionen, Update, Deinstallieren
- [Assistent und Oberfläche](docs/de/assistent.md): Sprach-Chat, Handy, Funktionen, Menü
- [APIs und Einbinden](docs/de/apis-und-einbinden.md): Transkription, Sprachausgabe, Streaming, Open WebUI, Siri, Pebble
- [Sicherheit und Betrieb](docs/de/sicherheit-und-betrieb.md): Anmeldung, Sperren, Sicherungen, Wächter, Selbsttest, Logs
- [Technik und Fehlersuche](docs/de/technik.md): Dienste und Ports, Leistung messen, neben qwen38, Fehlersuche

Im Portal steht zu jeder Funktion eine eigene Anleitung unter *Funktionen → Anleitungen*.

## Unterstützen

Das Projekt ist kostenlos. Wenn es dir gefällt, kannst du es über [buymeacoffee.com/zquu1xu570](https://buymeacoffee.com/zquu1xu570) unterstützen.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Die Modelle (Qwen3-ASR, Qwen3-TTS) und Pakete (vLLM, vllm-omni, PyTorch) werden bei der Installation geladen und stehen unter ihren eigenen Lizenzen. Dieses Projekt steht in keiner Verbindung zu NVIDIA oder dem Qwen-Team.
