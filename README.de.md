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
| Aktualisieren | Knopf im Portal unter *Einstellungen → Update und Sicherung* oder `sudo speech-spark update` |
| Adressen und Schlüssel anzeigen | `sudo speech-spark info` |
| Eigenes Sprachmodell | `sudo ./install.sh --llm`, danach `sudo speech-spark modelle llm uebernehmen` (zurück: `… zurueck`) |
| Werkstatt (Testlauf, Code-Messung, Diagnose, Reparatur) | auf dem Modell-Rechner `sudo ./install.sh --werkstatt`, dann *Funktionen → Werkstatt* |
| Portal auf einen anderen Rechner umziehen | `sudo speech-spark umziehen --code`, siehe [Spark teilen](docs/de/spark-teilen.md) |
| Deinstallieren | `sudo ./uninstall.sh` (Konfiguration, Modelle und Stimmen bleiben; `--purge` löscht alles) |

Alle Optionen ohne Rückfragen (`--mode api --asr 1.7b --tts 0.6b --yes` …) stehen in [Installation im Detail](docs/de/installation.md).

## Letzte Änderungen

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.869** Besprechung aus dem Spark-Begleiter: ausgewählte Aufgaben kommen mit „Ausgewählte auf die Liste“ auf eine Liste (Standard „Aufgaben“, wählbar) mit dem Datum aus „bis“ und der Quelle „aus Besprechung“, auch im iPhone und in Erinnerungen; „Als Erinnerung“ bleibt. Erinnerungen unter dem Gesicht sind nicht mehr links und rechts abgeschnitten, die Zusammenfassung landet auf dem reMarkable unter „Besprechungen“ statt „Antworten“
- **V01.0.868** Musik: „Text schreiben“ unter Ich → Musik und in der iPhone-App – das Sprachmodell schreibt den Liedtext aus der Beschreibung (Strophen und Refrain passend zur Länge) ins Feld, erst der nächste Klick macht das Lied; Künstlernamen werden zu Stilwörtern, feste Prüfung, auch „im stiel“; Fix: im Gespräch kam bei Künstlernamen kein Lied (Beschreibung wird ohne Namen neu geschrieben, „so wie“ im Text gilt nicht mehr als Künstler)
- **V01.0.867** Alles Offene im Assistenten (Stufe 1): was dich braucht, kommt als Karte mit Knöpfen ins Gespräch des Tages (dringende Für-dich-Funde, Erinnerungen, die geklingelt haben), direkt erledigen oder „Später“ (heute Abend, morgen früh, nächste Woche, ohne Zeit); neue Seite Offen (Braucht dich, Später, Erledigt) mit Zahl am Menüpunkt, „Noch offen“ über dem Gespräch, Heute-Karte; iPhone: Karten im Gespräch, Meine Sachen → Offen; Admin-Schalter, aus
- **V01.0.866** Teilen mit Profilen (Stufe 1): ein Dokument einzeln mit anderen Profilen teilen (Knopf „Teilen“, Person suchen, Sehen oder Aus), Ich → Geteilt zeigt alles, was andere mit dir und du mit anderen teilst (auch Listen und Kalender), zurückziehen wirkt sofort, Mitteilung gebündelt; Admin-Schalter, aus
- **V01.0.865** Listen teilen (Stufe 2): eine Liste je Profil zum Sehen oder Mitschreiben teilen (eintragen und abhaken, Löschen bleibt beim Besitzer), „Mit mir geteilt“ auf der Seite und im iPhone, „Setz Butter auf Sabines Einkaufsliste“, Neues von anderen als gebündelter Hinweis; Listen in der Erinnerungen-App des iPhone in beide Richtungen (Stufe 3, über den Kalender-Server) und ein Widget Einkauf; je ein Admin-Schalter, zuerst aus
- **V01.0.864** Mitteilung ans genutzte Gerät (Admin-Schalter unter Funktionen → Timer und Erinnerungen, aus): eine Mitteilung geht an das Gerät, das du gerade benutzt (Panel-Seite, Android-App, iPhone-App, Spark-Begleiter am PC oder Mac), sonst sofort an die Handy-App; die Geräte melden nur „benutzt vor n Sekunden“ oder „weg“, nie Inhalte; Live zeigt die Anzahl
- **V01.0.863** Musik bearbeiten (Admin-Schalter, aus): unter Ich → Musik ein Lied als neue Fassung ändern (Abschnitt neu, verlängern, Musikrichtung, Remix, Liedtext mit Strophen per Ziehen verschieben, schneiden, Tempo und Tonart), eigene Dateien mit Rechte-Haken hochladen, Werkzeug musik_bearbeiten; auch in der iPhone-App
- **V01.0.862** Wackelnde Tests robust gemacht; dabei behoben: ein Kalender-Abgleich während einer Änderung schreibt nicht mehr den alten Termin zurück, das Formular „Kalender hinzufügen“ bleibt beim Ausfüllen offen
- **V01.0.861** E-Mail: Liste, Mail und Ordner als drei gleiche Kästen, die Ordner rechts ein- und ausblendbar (Knopf „Ordner“, Taste O), Mails per Ziehen in einen Ordner, aufs Archiv oder in den Papierkorb; Löschen mit eigenem Schalter (aus) nur durch dich, in den Papierkorb mit „Rückgängig“, endgültig nur dort nach Rückfrage; nach dem dritten Verschieben vom selben Absender in denselben Ordner fragt der Spark, ob eine Regel das übernehmen soll; alles auch im iPhone
- **V01.0.860** Spark-Begleiter (Windows und Mac) zieht Kalender und E-Mail nach: Post im Fenster (ungelesen, Für dich, dringende Karten), wichtige neue Mail als Hinweis mit „Antwort entwerfen“, Knöpfe je Meldung, Karten in Frag Spark, Schnell erfassen mit Strg+Alt+N (Termin, Erinnerung oder Liste), 3 Antwortvorschläge auch im Outlook-Add-in, geteilte Kalender in „Als Nächstes“, Listen im Fenster; alles je Gerät aus

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
