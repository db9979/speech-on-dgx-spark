# Speech auf DGX Spark

[English](README.md) | **Deutsch** · Idee: Dominik Bornhäußer

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
| Aktualisieren | Knopf im Portal unter *Zustand → System und Update* oder `sudo speech-spark update` |
| Adressen und Schlüssel anzeigen | `sudo speech-spark info` |
| Deinstallieren | `sudo ./uninstall.sh` (Konfiguration, Modelle und Stimmen bleiben; `--purge` löscht alles) |

Alle Optionen ohne Rückfragen (`--mode api --asr 1.7b --tts 0.6b --yes` …) stehen in [Installation im Detail](docs/de/installation.md).

## Letzte Änderungen

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.155** iPhone-App zeigt das im Panel gewählte Gesicht, jetzt auch das Comic-Gesicht mit eigenem Leben (Lider, Blicke, Brauen, Mund unterm Schnurrbart)
- **V01.0.154** Gesicht wählbar: Admin stellt unter Einstellungen → Vorgaben „Roboter“ (bisher) oder „Comic“ ein (Karikatur, schaut umher, blinzelt, Mund folgt der Stimme, farbiger Ring je Zustand); gilt für Panel und iPhone-App
- **V01.0.153** iPhone-App lebendig: Gesicht wie im Panel (Aussehen austauschbar), Freihändig und Ins-Wort-fallen, Weckwort auf dem iPhone ohne Internet, Ständer-Modus am Ladekabel, Erinnerungen als Mitteilung, Hinweise von selbst, Route und Anruf nur nach „Ja“ (neue Schalter im Panel, aus)
- **V01.0.152** iPhone-App „Spark“ (aus, Admin + Profil): eigene SwiftUI-App in ios/, Kopplung per QR-Code oder Link, eigener Schlüssel pro iPhone, der nur fragen und hören darf, Antwort mit Spark-Stimme, „Hey Siri, Frag Spark“ über die App; Smart Home daraus nur mit eigenem Schalter
- **V01.0.151** Update wartet bis zu 10 Minuten, wenn apt gerade belegt ist (z. B. automatische Updates), statt abzubrechen
- **V01.0.150** Qualitätstest: Kalender-Fragen nennen „morgen“ und „Dienstag“ immer passend zum heutigen Tag (der feste 8.10. war ab dem 8.10. falsch)
- **V01.0.149** Lautsprecher-Seite geordnet: Liste → eigene Seite pro Lautsprecher (Klang, Raum-Modus mit „Starten“ und wählbaren Arten, Stimme, Firmware, Prüfen), „Lautsprecher hinzufügen“ per USB oder Code, Admin „Adresse prüfen“, Lautsprecher-Schlüssel gekennzeichnet
- **V01.0.148** Browser-Test für Zustand hält auch dort, wo systemd echte Dienste meldet (GitHub)
- **V01.0.147** Design „Klar“, Schritt 3: Ich öffnet am Rechner als Seite neben der Menüleiste statt als Fenster; ein anderer Menüpunkt schließt es
- **V01.0.146** Design „Klar“, Schritt 2: Zustand beginnt mit einem Satz („Alles läuft.“ oder was nicht läuft) und „Braucht dich“ (Update, ungespeicherte Einstellungen, Dienst aus/Fehler) mit Knopf dorthin; Punkt im Menü grün/gelb/rot; qwen38 und GPU-Prozesse zugeklappt

Alle Versionen: [CHANGELOG.md](CHANGELOG.md)

## So funktioniert es

```mermaid
flowchart LR
  subgraph Clients["Geräte und Apps"]
    B["Browser / Handy-App"]
    A["Open WebUI, eigene Apps"]
    X["Siri, Pebble, Telegram, Lautsprecher,<br/>HA Assist (Wyoming :31003)"]
  end
  subgraph Spark["DGX Spark"]
    P["Webportal :31443<br/>Assistent, Profile, Monitoring"]
    ASR["ASR :31001<br/>Qwen3-ASR oder Parakeet"]
    TTS["TTS :31002<br/>Qwen3-TTS"]
    LLM["qwen38 :30001<br/>Sprachmodell"]
  end
  E["Home Assistant, Kalender,<br/>E-Mail, SearXNG"]
  B --> P
  X --> P
  A --> ASR
  A --> TTS
  P --> ASR
  P --> LLM
  P --> TTS
  P --> E
```

1. Du sprichst ins Handy oder in den Browser. Das Portal schickt den Ton an die **Spracherkennung**, die Text daraus macht.
2. Das Portal gibt den Text mit Gedächtnis, Gesprächsverlauf und den erlaubten Werkzeugen an das **Sprachmodell** von qwen38.
3. Braucht die Antwort Kalender, Mail, Wetter, Websuche oder Home Assistant, holt das Portal die Daten selbst; schalten und eintragen geht nur nach Bestätigung.
4. Die Antwort geht Satz für Satz an die **Sprachausgabe** und wird gestreamt abgespielt, während das Modell noch schreibt.
5. Andere Apps können ASR und TTS auch direkt über die OpenAI-ähnlichen APIs nutzen, mit API-Schlüssel.

Jede Funktion ist pro Profil einzeln schaltbar und ab Werk aus. Updates laufen erst nach grünem Selbsttest und lassen sich zurücknehmen.

## Weiterlesen

- [Installation im Detail](docs/de/installation.md): Installationsarten, Befehl `speech-spark`, alle Optionen, Update, Deinstallieren
- [Assistent und Oberfläche](docs/de/assistent.md): Sprach-Chat, Handy, Funktionen, Menü
- [APIs und Einbinden](docs/de/apis-und-einbinden.md): Transkription, Sprachausgabe, Streaming, Open WebUI, Siri, Pebble
- [Sicherheit und Betrieb](docs/de/sicherheit-und-betrieb.md): Anmeldung, Sperren, Sicherungen, Wächter, Selbsttest, Logs
- [Technik und Fehlersuche](docs/de/technik.md): Dienste und Ports, Leistung messen, neben qwen38, Fehlersuche

Im Portal steht zu jeder Funktion eine eigene Anleitung unter *Einbinden → Anleitungen*.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Die Modelle (Qwen3-ASR, Qwen3-TTS) und Pakete (vLLM, vllm-omni, PyTorch) werden bei der Installation geladen und stehen unter ihren eigenen Lizenzen. Dieses Projekt steht in keiner Verbindung zu NVIDIA oder dem Qwen-Team.
