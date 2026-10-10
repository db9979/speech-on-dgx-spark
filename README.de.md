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
| Aktualisieren | Knopf im Portal unter *Einstellungen → Update und Sicherung* oder `sudo speech-spark update` |
| Adressen und Schlüssel anzeigen | `sudo speech-spark info` |
| Deinstallieren | `sudo ./uninstall.sh` (Konfiguration, Modelle und Stimmen bleiben; `--purge` löscht alles) |

Alle Optionen ohne Rückfragen (`--mode api --asr 1.7b --tts 0.6b --yes` …) stehen in [Installation im Detail](docs/de/installation.md).

## Letzte Änderungen

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.264** Erst lokal suchen (Funktionen → Websuche, aus; Profil-Schalter): Wissensfragen schauen zuerst in Dokumenten, Kiwix-Archiv und früheren Gesprächen (höchstens 400 ms, Treffer als Daten mit Quelle), Aktuelles geht direkt hinaus, „in meinen Unterlagen“ bleibt lokal; Websuche nach Dokumenten nur mit den Worten der Frage; Zustand → Prüfen → „Erst lokal testen“, Logzeile „lokal:“
- **V01.0.263** Logs → Anfragen (Schalter unter Einstellungen → Betrieb, aus): Weg jeder Anfrage als Liste mit Perlenkette und Zeitstrahl (Weiche, Sprachmodell-Runden, Werkzeuge, Prüfung, Sprachausgabe, erster Ton), ohne Frage- und Antworttext; Name nur mit Zustimmung des Profils
- **V01.0.262** Sicherheit: Schutz-Kopfzeilen auf jeder Antwort (kein Einbetten in fremde Seiten, nosniff, Referrer-Policy, Mikrofon/Kamera nur fürs Panel, HSTS auf https), Liste der angemeldeten Browser mit Einzel-Abmelden (Ich → Sicherheit, Admin in den Profil-Details), Profil-Anmeldung endet nach 30 Tagen ohne Nutzung (7–90 einstellbar), „Sicherheit auf einen Blick“ als Ampel oben unter Einstellungen → Sicherheit
- **V01.0.261** Kiwix: Bücher werden ohne Datum gespeichert, aktualisierte Dateien bleiben gewählt (neueste wird genommen, Katalog bei 404 neu gelesen); „Schau in meinem Archiv“ sucht nie in den hochgeladenen Dokumenten und sagt, welcher Schalter fehlt
- **V01.0.260** Kiwix: Bücherauswahl als Liste mit Suche, Sprach- und Artfilter (Deutsch/Englisch zuerst), gruppiert, mit Sprache, Variante, Artikelzahl, Größe und Stand; gewählte oben als Chips; ohne Auswahl deutsche und englische Wikipedia; Katalog bis 2000 Bücher
- **V01.0.259** Selbsttest „Profile und Geräte“ sucht das Testgerät statt auf Seite 1 zu warten (GitHub-Tests wieder grün)
- **V01.0.258** Eigenes Kiwix-Archiv (Funktionen → Websuche, aus; Profil-Schalter): Wikipedia-Fragen zuerst aus dem eigenen kiwix-serve, Volltextsuche in gewählten Büchern, „Erzähl mehr“ liest weiter, fällt die Websuche aus antwortet das Offline-Archiv; Zustand → Prüfen → „Kiwix prüfen“, Logs-Bereich „Wissen“
- **V01.0.257** Profile und Geräte: Profil eines Geräts als Auswahlliste statt Namensfeld; iPhone-App, Lautsprecher, Pebble-Uhr und Home Assistant stehen „🔒 fest“ mit Ort der Verwaltung (Server lehnt Umhängen ab), Zeilen gleich ausgerichtet
- **V01.0.256** iPhone-App: „Mit meinem Profil anmelden“ in Spark verwalten für Mit-Admin und Verwalter (Profil-Code, endet nach 15 Min. ohne Bedienung)
- **V01.0.255** Benutzer als Admin (Schalter unter Einstellungen → Sicherheit, aus; nur mit zweitem Schritt des Hauptadmins): Rollen Mit-Admin und Verwalter für Profile, Admin-Modus unter Ich → Sicherheit mit eigenem Code (15 min ohne Bedienung, höchstens 8 h), Hauptadmin behält Passwort, Rollen, Sicherungen und Admin-Profile, Logs → Admin-Protokoll zeigt wer, App-Anmeldung mit Profil-Code (Server)

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
