# Architektur und Datenfluss

← [README](../../README.de.md) · [Technik und Fehlersuche](technik.md) · [Sicherheit und Betrieb](sicherheit-und-betrieb.md)

Diese Seite beschreibt, wie der Spark gebaut ist: welche Teile es gibt, welchen Weg eine Anfrage nimmt und wo welche Daten liegen. Im Panel steht dasselbe zum Anklicken unter **Zustand → Technik** (nur für Admins). Das Bild nutzt dort die ganze Breite, das Detail steht darunter; „⛶ Vollbild“ legt Überblick oder Datenfluss über den ganzen Bildschirm, mit ＋/− zum Vergrößern und Escape zum Schließen. Wie gebaut wird, regelt die [Coding-Richtlinie](richtlinien.md).

Die Abschnitte zwischen den Markierungen `<!-- technik:… -->` entstehen aus dem Code (`app/panel/technik.py`, dazu `speicher.AREAS`/`LOCAL` und `backup.STATE_FILES`/`STATE_LOCAL`). `python3 app/panel/hilfe.py --docs` schreibt sie neu. Ein Selbsttest (`test_technik`) wird rot, wenn ein Modul, eine Datei oder ein Schritt fehlt oder die Doku nicht neu geschrieben wurde. Nur die Texte außerhalb der Markierungen werden von Hand gepflegt.

## Überblick

Geräte und Programme sprechen nur mit dem Panel. Das Panel prüft jede Anfrage, fragt das Sprachmodell, ruft Werkzeuge über den Wächter auf und schreibt in die Ordner unter `/var/lib/speech-spark`. Spracherkennung und Sprachausgabe sind eigene Dienste. Das Sprachmodell gehört zu `dgx-spark-qwen38` und ist nicht Teil dieses Repos.

<!-- technik:bild -->
```mermaid
flowchart LR
  geraet["Browser und Handy<br/>static/js"]
  apps["Apps<br/>iPhone, Android"]
  kanaele["Telegram, Siri, Uhr<br/>Kanäle"]
  lautsprecher["Lautsprecher, HA<br/>esp32 · :31003"]
  mcpc["MCP-Programme<br/>/mcp"]
  middleware["Middleware<br/>panel.py"]
  zugang["Anmeldung, Profil<br/>guard · profiles"]
  vorbereiten["Anfrage vorbereiten<br/>chat_turn.prepare"]
  weiche["Weiche<br/>intent.py"]
  antwort["Antwort bauen<br/>chat._answer"]
  werkzeuge["Werkzeuge<br/>chat_tools.run"]
  wissen["Wissen<br/>documents · wissen"]
  waechter["Wächter<br/>netguard.py"]
  betrieb["Logs und Live<br/>tracelog · live"]
  llm["Sprachmodell<br/>:30001 qwen38"]
  asr["Spracherkennung<br/>:31001 → :31011"]
  tts["Sprachausgabe<br/>:31002 → :31012"]
  aussen["Dienste draußen<br/>HA, Mail, Suche …"]
  state[("state/<br/>global")]
  users[("users/ID/<br/>pro Profil")]
  ablage[("voices/, backups/<br/>Stimmen, Sicherungen")]
  journal[("journald<br/>speech-spark")]
  geraet --> middleware
  apps --> middleware
  kanaele --> middleware
  lautsprecher --> middleware
  mcpc --> middleware
  middleware --> zugang
  middleware --> asr
  zugang --> vorbereiten
  vorbereiten --> weiche
  weiche --> antwort
  antwort --> llm
  antwort --> werkzeuge
  werkzeuge --> waechter
  waechter --> aussen
  werkzeuge --> wissen
  antwort --> tts
  antwort --> geraet
  antwort --> betrieb
  betrieb --> state
  betrieb --> journal
  wissen --> users
  zugang --> users
  zugang --> state
  tts --> ablage
```
<!-- /technik:bild -->

## Prozesse und Ports

| Dienst | Port | Aufgabe |
|---|---|---|
| `speech-spark-panel` | 31080, HTTPS 31443 | Webportal, alle Endpunkte, Hintergrundaufgaben |
| `speech-spark-asr` → `speech-spark-asr-engine` | 31001 → 31011 (nur lokal) | Spracherkennung |
| `speech-spark-tts` → `speech-spark-tts-engine` | 31002 → 31012 (nur lokal) | Sprachausgabe; optional VoiceDesign auf 31013 |
| Wyoming im Panel | 31003 | Home Assistant Assist |
| `dgx-spark-qwen38` (fremdes Projekt) | 30001 | Sprachmodell; Ports 30000–30099 gehören ihm |
| `speech-spark-watch` | – | Wächter, nur ohne Panel |
| `speech-spark-update` | – | Update, nur auf Knopfdruck |

Alle Dienste laufen als Systembenutzer `speech` und loggen in den journald-Namespace `speech-spark`. Das Panel startet seine Hintergrundaufgaben selbst (`panel.py`: Messwerte, Stabilität, Posteingang aufräumen, Dokumente lesen, reMarkable-Abgleich, Lernen aus Gesprächen). Hintergrundarbeit wartet, solange gesprochen wird (`vorrang.py`).

## Datenfluss einer Anfrage

Der Weg einer gesprochenen Frage im Browser, von der Eingabe bis zur Speicherung:

<!-- technik:datenfluss -->
1. **Eingabe**: Das Mikrofon nimmt auf, das Panel reicht den Ton an die Spracherkennung weiter. Im Code: `POST /api/test/asr`
2. **Zugang**: Notaus, Herkunft und Größe, dann Rate-Limit, Anmeldung und Profil. Im Code: `POST /api/chat · guard.limit · profiles.current`
3. **Vorbereiten**: Sprache zuerst (vorrang), andere Geräte sehen „antwortet gerade“, dann Rechte, Sperren, Systemprompt. Im Code: `chat_turn.prepare()`
4. **Weiche**: Feste Regeln grenzen die Werkzeuge ein; ein klarer Lesewunsch läuft direkt. Im Code: `intent.classify_cfg() · intent.narrow()`
5. **Modell**: Sofort-Satz, Anfrage-Verlauf, dann Runden mit dem Sprachmodell, gestreamt. Im Code: `chat._answer()`
6. **Werkzeuge**: Werkzeugaufruf, Wächter, Dienst draußen oder eigenes Wissen; das Ergebnis geht als Daten zurück. Im Code: `chat_tools.run() · netguard`
7. **Antwort**: Sätze gehen an die Sprachausgabe; Text und Ton kommen als ein Strom zum Gerät. Im Code: `SSE · /v1/audio/speech`
8. **Speichern**: Das Gerät legt den Verlauf ab, das Panel Werkzeug-Log, Gedächtnis, Tagebuch, Anfrage-Verlauf und Journal. Im Code: `PUT /api/profile/convos · tracelog.finish`
<!-- /technik:datenfluss -->

Abzweige:

- **Telegram, Siri und Uhr** schicken Text (oder eine Sprachnachricht) an ihren eigenen Endpunkt. Den Verlauf legt das Panel selbst ab (`verlauf.keep`), nicht das Gerät.
- **ESP32-Lautsprecher und Home Assistant Assist** sprechen mit `esp32.py` und `wyoming.py`. Eine fremde Stimme am geteilten Lautsprecher bekommt nur Gastrechte.
- **MCP-Programme** fragen über `/mcp` (`mcpserver.py`) mit eigenem Token, das nur als Hash gespeichert ist.
- **Gäste** bekommen nur Frage und Antwort vom Sprachmodell, ohne Werkzeuge, ohne persönliche Daten und ohne Verlauf auf dem Spark.

An jeder Stelle gilt: Alles von außen (Web, Mail, Dokumente, Werkzeugergebnisse, Modellausgaben) ist Daten, nie ein Befehl. Entscheidungen trifft das Panel mit festen Regeln.

## Bausteine

Jedes Modul unter `app/panel/` und `app/` gehört zu genau einer Gruppe. Ein neues Modul ohne Eintrag in `technik.MODULE` macht `test_technik` rot.

<!-- technik:bausteine -->
### Zugang und Rechte

Jede Anfrage geht zuerst hier durch: Größe, Herkunft, Notaus, Anmeldung, Profil und Freigaben.

| Modul | Aufgabe |
|---|---|
| `app/panel/account.py` | Was ein Gerät für sich selbst darf: Anmelden und eigene Daten |
| `app/panel/coadmin.py` | Profile als Admins: Haupt-Admin, Mit-Admin, Verwalter |
| `app/panel/core.py` | Admin-Passwort, Sitzungen, gemeinsame Pfade und Helfer |
| `app/panel/features.py` | Alle Funktionen mit Namen und Freigaben an einer Stelle |
| `app/panel/guard.py` | Rate-Limits, Sperren nach falschen Versuchen, fremde Seiten, audit.log |
| `app/panel/join.py` | Neue Personen per Einladung |
| `app/panel/mfa.py` | Zweiter Anmeldeschritt mit Code (TOTP) und Wiederherstellungscodes |
| `app/panel/netguard.py` | Wächter: wohin eine Verbindung nach außen darf |
| `app/panel/notaus.py` | Notaus in drei Stufen, von außen nach innen |
| `app/panel/notzugang.py` | Wieder hinein nach einem Aussperren (nur per sudo am Spark) |
| `app/panel/panel.py` | Startet das Panel, Middleware (Notaus, Herkunft, Größe), liefert die Seite aus |
| `app/panel/passkey.py` | Passkeys statt Code (Face ID, Touch ID, Windows Hello) |
| `app/panel/profiles.py` | Profile, Geräte, Sitzungen, Gespräche und Gedächtnis pro Profil |
| `app/panel/signatur.py` | Prüft signierte Update-Manifeste (Ed25519) |
| `app/panel/stufen.py` | Liste, welche Änderung den Code verlangt |
| `app/panel/vault.py` | Versiegelt Passwörter und Tokens mit state/secret.key |
| `app/panel/zertpin.py` | Zertifikat eines Geräts im Heimnetz festpinnen |

### Gespräch

Bereitet eine Anfrage vor, fragt das Sprachmodell in Runden und prüft, was gesagt wird.

| Modul | Aufgabe |
|---|---|
| `app/panel/ack.py` | Sofortige Rückmeldung aus aufgenommenen Sätzen |
| `app/panel/answercheck.py` | Antwort-Prüfung: das Panel entscheidet, ob ein Satz gesagt werden darf |
| `app/panel/chat.py` | Der Assistent: /api/chat, Runden mit dem Modell, Text und Ton als Strom |
| `app/panel/chat_tools.py` | Führt die Werkzeugaufrufe des Modells aus und prüft die Sperren erneut |
| `app/panel/chat_turn.py` | Bereitet eine Anfrage vor: Rechte, Sperren, Systemprompt, Werkzeuge |
| `app/panel/echo.py` | Der Assistent antwortet nicht auf seine eigene Stimme |
| `app/panel/fixes.py` | Lernt aus Korrekturen der Person |
| `app/panel/fremdstimme.py` | Fernseher und fremde Stimmen im von selbst geöffneten Mikrofon werden keine Frage |
| `app/panel/images.py` | Bilder in der Frage: das Sprachmodell sieht sie selbst |
| `app/panel/klaeren.py` | Rückfrage, Korrektur und Merken von Zuordnungen |
| `app/panel/roles.py` | Rollen: wie der Assistent antworten soll |
| `app/panel/schreib.py` | Schreibhilfe: korrigieren, kürzen, übersetzen, entwerfen |
| `app/panel/stille.py` | Aus Stille werden nie Wörter |
| `app/panel/stufe.py` | Vorrang für Personen in der Warteschlange der Sprachausgabe |
| `app/panel/systemone.py` | Einordnung mit Wahrscheinlichkeit über qwen38 |
| `app/panel/taten.py` | Handlungs-Prüfung: hat ein Werkzeug wirklich getan, was der Satz sagt |
| `app/panel/tipps.py` | Schlägt passende Funktionen vor, die noch aus sind |
| `app/panel/vorab.py` | Holt bei einer Rückfrage die Antwort schon vorab |

### Weiche und Werkzeugnamen

Feste Regeln, welche Werkzeuge das Modell für eine Frage sieht. Gibt nie mehr frei als die Rechte.

| Modul | Aufgabe |
|---|---|
| `app/panel/intent.py` | Die Weiche: feste Regeln für die eigene letzte Nachricht |
| `app/panel/intent_alltag.py` | Alltagssätze der Weiche: nur zum Messen |
| `app/panel/intent_bench.py` | Testsätze der Weiche |
| `app/panel/weiche.py` | Seite Funktionen → Weiche und ihre Statistik |
| `app/panel/werkzeug_abdeckung.py` | Welche Funktion das Modell mit welchem Werkzeug erreicht (Regel 29) |
| `app/panel/werkzeuge.py` | Verständliche Namen aller Werkzeuge |

### Wissen und Dokumente

Eigene Dokumente, Gedächtnis, frühere Gespräche, Kiwix und Wikipedia, erstellte Dokumente.

| Modul | Aufgabe |
|---|---|
| `app/panel/docembed.py` | Bedeutungsvektoren für die Dokumentsuche |
| `app/panel/doclingdienst.py` | Docling-Server im Heimnetz: Dokumente und Scans besser lesen |
| `app/panel/docmake.py` | Dokumente erstellen: Aufträge, Vorlagen, Ablage |
| `app/panel/docrender.py` | Baut die Dateien (Word, PDF, PowerPoint, Excel) mit festem Code |
| `app/panel/documents.py` | Dokumente pro Profil in wissen.db: Text, Abschnitte mit Kontextzeile, Suche |
| `app/panel/embed_worker.py` | Das Vektormodell im eigenen Prozess |
| `app/panel/folien.py` | Folientypen und feste Regeln für erstellte Dokumente |
| `app/panel/gedaechtnis.py` | Gedächtnis mit Beleg und Prüfung |
| `app/panel/kiwix.py` | Eigenes Kiwix als Wissensquelle ohne Internet |
| `app/panel/lokal.py` | Erst lokal suchen, bevor etwas nach außen geht |
| `app/panel/memtidy.py` | Wöchentliches Aufräumen des Gedächtnisses |
| `app/panel/nachsortieren.py` | Treffer nachsortieren: ein Cross-Encoder auf dem Prozessor ordnet die Kandidaten |
| `app/panel/recall.py` | Suche in früheren Gesprächen, gelernte Fakten |
| `app/panel/suchpruefung.py` | Suchprüfung: Prüffragen messen, wie gut die Dokumentensuche trifft |
| `app/panel/symbole.py` | Feste Symbole für Folien und Dokumente |
| `app/panel/tagebuch.py` | Spark-Tagebuch: was der Spark selbst getan hat |
| `app/panel/wiki.py` | Wikipedia für „Was ist …?“ |
| `app/panel/wissen.py` | Wissen aus eigenen Uploads: Schalter und Kontingent |

### Anbindungen

Home Assistant, Mail, Kalender, Aufgaben, Wetter, reMarkable, MCP und was der Spark von selbst tut.

| Modul | Aufgabe |
|---|---|
| `app/panel/aendern.py` | Ändern per Sprache: Lautstärke, Termine und anderes nach „Ja“ |
| `app/panel/agent.py` | Aufträge im Hintergrund, Zeitpläne, Routinen |
| `app/panel/beobachten.py` | Beobachten: Funde prüfen, nur Neues melden (Eigene Aufgaben) |
| `app/panel/calendars.py` | Kalender und Tagesbriefing |
| `app/panel/contacts.py` | Kontakte per CardDAV, nur lesen |
| `app/panel/extras.py` | Kleine Zusatzdienste mit ihren Werkzeugen |
| `app/panel/hamelden.py` | Home Assistant meldet Ereignisse an den Spark |
| `app/panel/homeassistant.py` | Home Assistant pro Profil |
| `app/panel/mail.py` | Mail lesen per IMAP |
| `app/panel/mcp.py` | Werkzeuge von MCP-Servern, die der Admin einträgt |
| `app/panel/mcpserver.py` | Der Spark als MCP-Server für andere Programme |
| `app/panel/meinmcp.py` | Eigene MCP-Dienste pro Profil |
| `app/panel/parcels.py` | Pakete aus Versand-Mails |
| `app/panel/proactive.py` | Meldet sich von selbst, wenn etwas Echtes passiert |
| `app/panel/remarkable.py` | reMarkable-Notizbücher als Wissen |
| `app/panel/rmaufgaben.py` | Aufgabenblatt zum Ankreuzen aufs reMarkable |
| `app/panel/rmliste.py` | Werkzeug: was auf dem reMarkable liegt und welche Aufgaben dort stehen |
| `app/panel/rmpapier.py` | Gestaltete Blätter fürs reMarkable |
| `app/panel/rmplus.py` | Mehr mit dem reMarkable: Senden, Ordner, Abgleich |
| `app/panel/tasks.py` | Aufgaben und Einkaufsliste |
| `app/panel/tidy.py` | Posteingang aufräumen |
| `app/panel/transit.py` | Bus und Bahn |
| `app/panel/weather.py` | Wetter von Open-Meteo als feste Sätze |
| `app/panel/zustand_wz.py` | Werkzeug: Zustand des Spark per Sprache („Läuft alles?“) |

### Geräte und Kanäle

Apps, Telegram, Uhr, Lautsprecher, Raummodus, Chats und der Verlauf auf allen Geräten.

| Modul | Aufgabe |
|---|---|
| `app/panel/android.py` | Android-App: Download, Mitteilungen und Update in der App |
| `app/panel/apns.py` | Mitteilungen an die iPhone-App |
| `app/panel/appupdate.py` | Spark-Update aus der iPhone-App |
| `app/panel/begleiter.py` | Spark-Begleiter für Windows und Mac |
| `app/panel/chats.py` | Chats zwischen den Profilen, verschlüsselt |
| `app/panel/chatsec.py` | Private Chats mit Ende-zu-Ende-Verschlüsselung |
| `app/panel/esp32.py` | Eigene ESP32-Lautsprecher und ihre Firmware |
| `app/panel/geraeteupdate.py` | Übersicht und Hinweise zu Geräte-Updates |
| `app/panel/hintergrund.py` | Ich → Mein Zustand |
| `app/panel/iphone.py` | iPhone-App: Kopplung und Rechte |
| `app/panel/messages.py` | Der Weg des Assistenten in die Chats |
| `app/panel/onboard.py` | Einrichten an der Hand |
| `app/panel/pebblewatch.py` | Kopplung der Pebble-Uhr |
| `app/panel/push.py` | Web-Push für Erinnerungen |
| `app/panel/room.py` | Raummodus: hört zu und hilft in einer Pause |
| `app/panel/roomfar.py` | Raummodus auf einem anderen Gerät schalten |
| `app/panel/roomlive.py` | Wo der Raummodus gerade zuhört |
| `app/panel/speakers.py` | Sprechererkennung pro Profil |
| `app/panel/spkcode.py` | Codewort am geteilten Lautsprecher |
| `app/panel/telegram.py` | Telegram-Bot für Text und Sprachnachrichten |
| `app/panel/today.py` | Die Karte „Heute“ oben in Ich |
| `app/panel/verbund.py` | Spark-Verbund: Chats mit Menschen auf anderen Sparks, signiert |
| `app/panel/verlauf.py` | Verlauf auf allen Geräten gleich |
| `app/panel/watch.py` | Antworten für die Uhr |
| `app/panel/wyoming.py` | Home Assistant Assist über Wyoming |

### Betrieb

Live-Übersicht, Logs, Wächter, Sicherung, Update, Hilfe und die Admin-Seiten.

| Modul | Aufgabe |
|---|---|
| `app/panel/admin.py` | Admin-Seiten: Zustand, Einstellungen, Dienste, Stimmen |
| `app/panel/backup.py` | Sicherungen und Wiederherstellen |
| `app/panel/befund.py` | Befund: die Ursache eines Falls |
| `app/panel/berater.py` | Einstellungs-Assistent: Vorschläge aus Fällen |
| `app/panel/berater_katalog.py` | Was der Einstellungs-Assistent vorschlagen darf |
| `app/panel/dienstwacht.py` | Dienst-Wächter: meldet, wenn ein Dienst fehlt |
| `app/panel/faelle.py` | Fälle: jedes Problem wird festgehalten |
| `app/panel/ghtoken.py` | Lese-Token für GitHub |
| `app/panel/health.py` | Stabilität: Wächter für hängende Dienste, Echtprüfung |
| `app/panel/hilfe.py` | Spark-Hilfe und Index der Doku |
| `app/panel/latency.py` | Wartezeit bis zum ersten Ton |
| `app/panel/live.py` | Live-Übersicht: was der Spark gerade tut |
| `app/panel/logfilter.py` | Diagnose-Filter und Hinweise für die Logs |
| `app/panel/meldung.py` | Probleme melden als GitHub-Issue |
| `app/panel/monitor.py` | Messwerte: GPU, Speicher, CPU |
| `app/panel/nas.py` | Speicher und NAS: Speicherorte (NAS, Cloud), eine Anmeldung pro Ort für Kopie und Sicherung |
| `app/panel/nasablage.py` | Ablage-Ordner: spark_ablage im Heimnetz, der einzige Ordner, in den der Spark schreibt; Eingang wird zu Dokumenten |
| `app/panel/nashilfe.py` | NAS im Heimnetz finden (nur mDNS) und Rechte am Ort zeigen, mit Warnung bei Admin-Konto |
| `app/panel/nasquelle.py` | Wissensordner: Ordner an einem Speicherort nur lesen und in die Dokumentensuche bringen |
| `app/panel/naszustand.py` | Zustand der NAS: Belegung, RAID, Festplatten und Temperatur über SNMPv3 (nur lesen, nur Admin) |
| `app/panel/offsite.py` | Sicherung nach außen, verschlüsselt |
| `app/panel/quality.py` | Qualitätstest gegen das echte Sprachmodell |
| `app/panel/speicher.py` | Kopie meiner Daten pro Profil an einem Speicherort, verschlüsselt |
| `app/panel/system.py` | Sicherung, Echtprüfung der Dienste, Hinweise oben |
| `app/panel/technik.py` | Diese Seite: Zustand → Technik und die Architektur-Doku |
| `app/panel/technik_knoten.py` | Knoten-Seiten: jeder Kasten ganz genau, mit Ablauf, Regeln, Zahlen und Code |
| `app/panel/technik_seiten.py` | Die Texte der Knoten-Seiten, Zahlen als Platzhalter aus dem Code |
| `app/panel/tracelog.py` | Logs → Anfragen: der Weg jeder Anfrage |
| `app/panel/undo.py` | Rückgängig im Admin-Protokoll |
| `app/panel/update.py` | Updates von GitHub, nur nach grünem Test |
| `app/panel/wege.py` | Sprung-Links in Texten außerhalb des Panels |

### Sprachdienste

Spracherkennung und Sprachausgabe als eigene Dienste, mit Vorrang vor allem anderen.

| Modul | Aufgabe |
|---|---|
| `app/api_watchdog.py` | Wächter ohne Panel (Installationsart „api“) |
| `app/asr_proxy.py` | Spracherkennung: nimmt an und reicht an die Engine durch |
| `app/asr_server.py` | Spracherkennung als eigener kleiner Dienst |
| `app/bench.py` | Leistung messen |
| `app/common.py` | Gemeinsame Helfer für die Dienste: Einstellungen, Zustand |
| `app/parakeet.py` | Zweite Spracherkennung (Parakeet) auf der CPU |
| `app/tempo.py` | Sprechtempo für gestreamte Sprache |
| `app/textnorm.py` | Text aufräumen vor der Sprachausgabe |
| `app/tts_proxy.py` | Sprachausgabe: nimmt an und reicht an die Engine durch |
| `app/tts_server.py` | Sprachausgabe als eigener kleiner Dienst |
| `app/panel/vorrang.py` | Sprache zuerst: Hintergrundarbeit wartet |
<!-- /technik:bausteine -->

## Datenspeicherung

Alle Dateien gehören dem Benutzer `speech` (Ordner 0700, Dateien 0600) und werden atomar geschrieben (`.tmp`, dann umbenennen). „Sicherung“ heißt: Die Datei steckt in der Sicherung unter Zustand → System → Sicherung. „Eigener Speicher“ heißt: Ein Profil kann die Datei verschlüsselt auf seinen eigenen Speicher kopieren.

<!-- technik:speicher -->
### System

| Pfad | Inhalt | Schutz | Sicherung |
|---|---|---|---|
| `/etc/speech-spark/config.json` | Alle Einstellungen (Geheimnisse versiegelt) | teils | ja |
| `/etc/speech-spark/panel.env, mode, connection.txt` | Start-Passwort, Installationsart, API-Zugang | – | nein |
| `/etc/speech-spark/tls/` | HTTPS-Zertifikat des Panels | – | nein |
| `/opt/speech-spark/` | Code, venvs, installierte Version | – | nein |
| `/var/lib/speech-spark/hf/` | Modell-Cache (HuggingFace) | – | nein |
| `/var/lib/speech-spark/firmware/` | ESP32-Firmware | signiert | nein |
| `/var/lib/speech-spark/voices/` | Geklonte Stimmen (WAV und Text) | – | ja |
| `/var/lib/speech-spark/backups/` | Sicherungen: 7 neueste plus 5 Ereignis-Sicherungen | – | – |
| `journald (Namespace speech-spark)` | Logs aller Dienste, Dauer und Größe nach Einstellung | – | nein |

### users/ (alle Profile)

| Pfad | Inhalt | Schutz | Sicherung |
|---|---|---|---|
| `users/profiles.json` | Profile und Geräte | – | ja |
| `users/sessions.json` | Anmeldungen | – | ja |
| `users/seen.json` | Zuletzt gesehen | – | ja |
| `users/secret` | Schlüssel der Profil-Anmeldung | ist ein Schlüssel | nein |
| `users/_chats/` | Chats zwischen Profilen | AES-256-GCM | ja |
| `users/_verbund/` | Spark-Verbund: andere Sparks, Kontakte, Warteschlange | – | ja |
| `users/begleiter.json` | Begleiter-Geräte | – | ja |

### users/ID/ (pro Profil)

| Pfad | Inhalt | Art | Schutz | Sicherung | Kopie meiner Daten |
|---|---|---|---|---|---|
| `users/ID/convos.json` | Gespräche |  | – | ja | Gespräche |
| `users/ID/toollog.json` | Werkzeug-Log |  | – | ja | Gespräche |
| `users/ID/room-history.json` | Raummodus-Verlauf |  | – | ja | Gespräche |
| `users/ID/memory.json` | Gedächtnis |  | – | ja | Gedächtnis |
| `users/ID/learned.json` | Gelernte Fakten |  | – | ja | Gedächtnis |
| `users/ID/zuordnungen.json` | Gemerkte Zuordnungen |  | – | ja | Gedächtnis |
| `users/ID/tasks.json` | Aufgaben |  | – | ja | Aufgaben und Erinnerungen |
| `users/ID/reminders.json` | Erinnerungen |  | – | ja | Aufgaben und Erinnerungen |
| `users/ID/wissen.db` | Dokumente: Text, Abschnitte mit Kontextzeile, Suche, Vektoren (SQLite) |  | – | ja | Dokumente (Text, Suche, Originale) |
| `users/ID/docs/files/` | Originale der Uploads |  | – | ja | Dokumente (Text, Suche, Originale) |
| `users/ID/suchpruefung.json` | Prüffragen und Läufe der Suchprüfung |  | – | ja | Dokumente (Text, Suche, Originale) |
| `users/ID/erstellt/` | Erstellte Dokumente |  | – | ja | Erstellte Dokumente |
| `users/ID/settings.json` | Einstellungen | Einstellungen | – | ja | – |
| `users/ID/setup.json` | Einrichtung | Einstellungen | – | ja | – |
| `users/ID/speicher.json` | Ziele des eigenen Speichers | Einstellungen | Schlüssel versiegelt | ja | – |
| `users/ID/speicher-stand.json` | Stand des Abgleichs | Zustand | – | ja | – |
| `users/ID/transit.json` | Haltestelle | Einstellungen | – | ja | – |
| `users/ID/weather.json` | Wetter-Ort | Einstellungen | – | ja | – |
| `users/ID/proactive.json` | Von selbst melden | Einstellungen | – | ja | – |
| `users/ID/proactive-rules.json` | Eigene Melde-Regeln | Einstellungen | – | ja | – |
| `users/ID/hintergrund.json` | Mein Zustand | Einstellungen | – | ja | – |
| `users/ID/mail.json` | Mail-Zugang | Login | Passwort versiegelt | ja | – |
| `users/ID/nas.json` | Speicherorte des Profils (NAS, Cloud) | Login | Passwort versiegelt | ja | – |
| `users/ID/nasquelle.json` | Wissensordner des Profils | Einstellungen | – | ja | – |
| `users/ID/nasquelle-stand.json` | Was aus den Wissensordnern gelesen ist | Zustand | – | ja | – |
| `users/ID/nasablage.json` | Ablage-Ordner des Profils | Einstellungen | – | ja | – |
| `users/ID/speicher.vor-nas.json` | Kopie meiner Daten vor dem Umzug auf Speicherorte | Login | – | ja | – |
| `users/ID/mail-tidy.json` | Posteingang aufräumen | Einstellungen | – | ja | – |
| `users/ID/calendar.json` | Kalender-Zugang | Login | Passwort versiegelt | ja | – |
| `users/ID/homeassistant.json` | Home-Assistant-Zugang | Login | Token versiegelt | ja | – |
| `users/ID/telegram.json` | Telegram-Kopplung | Login | – | ja | – |
| `users/ID/push.json` | Push-Abos der Browser | Gerät | – | ja | – |
| `users/ID/remarkable.json` | reMarkable-Zugang | Login | Token versiegelt | ja | – |
| `users/ID/remarkable-lib.json` | reMarkable-Bibliothek | Zustand | – | ja | – |
| `users/ID/mcp-dienste.json` | Eigene MCP-Dienste | Login | Tokens versiegelt | ja | – |
| `users/ID/mcp-actions.json` | MCP-Aktionen | Zustand | – | ja | – |
| `users/ID/agent.json` | Aufträge und Routinen | Einstellungen | – | ja | – |
| `users/ID/voice.json` | Stimmabdruck | Stimmabdruck | versiegelt | ja | – |
| `users/ID/speaker-code.json` | Codewort am Lautsprecher | Schlüssel | versiegelt | ja | – |
| `users/ID/chatkeys.json` | Öffentliche Schlüssel der Geräte | Schlüssel | – | ja | – |
| `users/ID/contacts.json` | Kontakte-Zugang | noch nicht angeboten | Passwort versiegelt | ja | – |
| `users/ID/ha-events.json` | Home-Assistant-Ereignisse | Zustand | – | ja | – |
| `users/ID/briefing-sent` | Briefing gesendet | Zustand | – | ja | – |
| `users/ID/messages.json` | Nachrichten-Einstellungen | Einstellungen | teils versiegelt | ja | – |
| `users/ID/messages/` | Alte Sprachnachrichten | alte Sprachnachrichten (bis zur Übernahme in die Chats) | – | nein | – |
| `users/ID/agent-pending.json` | Wartet auf Ja | Warteschlange | – | ja | – |
| `users/ID/calendar-pending.json` | Wartet auf Ja | Warteschlange | – | ja | – |
| `users/ID/fix-pending.json` | Wartet auf Ja | Warteschlange | – | ja | – |
| `users/ID/memory-ask.json` | Offene Frage zum Gedächtnis | Warteschlange | – | ja | – |
| `users/ID/mail-pending.json` | Wartet auf Ja | Warteschlange | – | ja | – |
| `users/ID/mcp-dienste-pending.json` | Wartet auf Ja | Warteschlange | – | ja | – |
| `users/ID/messages-pending.json` | Wartet auf Ja | Warteschlange | – | nein | – |
| `users/ID/tasks-pending.json` | Wartet auf Ja | Warteschlange | – | ja | – |
| `users/ID/tagebuch.json` | Spark-Tagebuch | Zustand | – | ja | – |
| `users/ID/docling-wait` | Dateien, bis Docling sie gelesen hat | Warteschlange | – | ja | – |
| `users/ID/mfa.json` | Zweiter Schritt des Profils | Schlüssel | versiegelt | ja | – |
| `users/ID/memory-tidy.json` | Aufräum-Vorschlag | Warteschlange | – | ja | – |
| `users/ID/memory-tidy-checked` | Letzte Aufräum-Prüfung | Zustand | – | ja | – |

### state/ (global)

| Pfad | Inhalt | Schutz | Sicherung |
|---|---|---|---|
| `state/ack` | Sofort-Sätze als Ton | – | nein |
| `state/admin-session.key` | Schlüssel der Admin-Sitzung | ist ein Schlüssel | nein |
| `state/admins.json` | Profile als Admins | – | ja |
| `state/agent.json` | Agent-Stufen, MCP-Dienste | Tokens versiegelt | ja |
| `state/android` | Android-App zum Download | – | nein |
| `state/apns-tokens.json` | iPhone-Geräte für Push | – | ja |
| `state/apns.json` | Apple-Push-Schlüssel | Schlüssel versiegelt | ja |
| `state/audit.log` | Admin-Protokoll, 1 MB | – | nein |
| `state/begleiter` | Begleiter-Updates | – | nein |
| `state/begleiter-inbox` | Vom Handy auf den PC, 24 h | – | nein |
| `state/bench-history.json` | Messungen | – | nein |
| `state/bench-latest.json` | Letzte Messung | – | nein |
| `state/berater.json` | Vorschläge des Assistenten | – | ja |
| `state/bewertungen.json` | Bewertungen pro Tag | – | nein |
| `state/config-undo.json` | Rückgängig (ohne Geheimnisse) | ohne Geheimnisse | nein |
| `state/dienste-zustand.json` | Hintergrund-Dienste | – | nein |
| `state/dienstwacht.json` | Dienst-Wächter | – | ja |
| `state/doc-embed.json` | Vektormodell | – | nein |
| `state/doc-quotas.json` | Dokument-Kontingente | – | ja |
| `state/doc-rank.json` | Nachsortier-Modell | – | nein |
| `state/docling.json` | Docling-Server: Adresse, Zertifikat, Zahlen | Schlüssel versiegelt | ja |
| `state/esp32.json` | Lautsprecher und Firmware | teils versiegelt | ja |
| `state/faelle.json` | Fälle | – | ja |
| `state/features-seen.json` | Wann Funktionen frei wurden | – | ja |
| `state/geraete-updates.json` | Geräte-Updates | – | ja |
| `state/github-token.json` | GitHub-Lese-Token | versiegelt | ja |
| `state/guard-xff-hinted.json` | Proxy-Hinweis gezeigt | – | nein |
| `state/guard.json` | Sperren nach Fehlversuchen | – | nein |
| `state/gut-saetze.json` | Mit 👍 bestätigte Fragen | – | ja |
| `state/iphone-update.json` | Update aus der iPhone-App | – | nein |
| `state/join.json` | Einladungen (Hashes) | nur Hashes | ja |
| `state/latency.json` | Wartezeiten | – | nein |
| `state/live-monitors.json` | Wandmonitore | – | nein |
| `state/livecheck.json` | Echtprüfung | – | nein |
| `state/mcp-dienste-admin.json` | Erlaubte MCP-Ziele | – | ja |
| `state/mcp-server.json` | MCP-Programme (Token-Hashes) | nur Hashes | ja |
| `state/meldung-token.json` | Token für Meldungen | versiegelt | nein |
| `state/meldungen` | Meldungs-Entwürfe | – | nein |
| `state/mfa-admin.json` | Zweiter Schritt des Admins | versiegelt | ja |
| `state/migrated-chunk10` | Einmalige Umstellung erledigt | – | nein |
| `state/nas-admin.json` | NAS-Verbindung des Spark | Passwort versiegelt | ja |
| `state/nasquelle-tmp` | Zwischendateien der Wissensordner, Sekunden | – | nein |
| `state/naszustand.json` | Zustand der NAS: Adresse, SNMP-Benutzer, letzte Werte | Passwörter versiegelt | ja |
| `state/notaus-keys.json` | Notaus-Auslöser | – | nein |
| `state/notaus-mine.json` | Mein Notaus | – | nein |
| `state/notaus.json` | Notaus | – | nein |
| `state/offsite.json` | Sicherung nach außen | versiegelt | ja |
| `state/panel-password` | Admin-Passwort (Hash) | Hash | ja |
| `state/personen-vorrang.json` | Vorrang pro Profil | – | ja |
| `state/quality-cases.json` | Eigene Testfragen | – | ja |
| `state/quality-history.json` | Verlauf der Qualitätstests | – | ja |
| `state/quality.json` | Letzter Qualitätstest | – | nein |
| `state/regel-versionen.json` | Regel-Versionen | – | ja |
| `state/revoked.json` | Widerrufene Sitzungen | – | nein |
| `state/secret.key` | Schlüssel für alles Versiegelte | ist der Schlüssel | nein |
| `state/setup.json` | Einrichtungs-Assistent erledigt | – | ja |
| `state/speech-active` | Zeitpunkt der letzten Sprache | – | nein |
| `state/speech-spark-asr-engine.json` | Zustand der ASR-Engine | – | nein |
| `state/speech-spark-tts-*.json` | Zustand der TTS-Engines | – | nein |
| `state/speicher-tmp` | Zwischenablage des eigenen Speichers | AES-256-GCM | nein |
| `state/telegram.json` | Telegram-Bot | Token versiegelt | ja |
| `state/tipps.json` | Gezeigte Tipps | – | nein |
| `state/traces.jsonl` | Logs → Anfragen, 48 h | – | nein |
| `state/update-night.json` | Nacht-Update | – | nein |
| `state/update-progress.json` | Update-Fortschritt | – | nein |
| `state/update-target` | Gewünschter Update-Stand | – | nein |
| `state/vapid.pem` | Web-Push-Schlüssel | ist ein Schlüssel | ja |
| `state/vision.json` | Bildfragen, 10 min | – | nein |
| `state/vorrang-key` | Schlüssel Panel ↔ Sprachdienste | ist ein Schlüssel | nein |
| `state/weiche-history.json` | Weiche-Änderungen | – | nein |
| `state/weiche-stats.json` | Weiche-Statistik | – | nein |
<!-- /technik:speicher -->

### Schlüssel und Verschlüsselung

- `state/secret.key` versiegelt alle Passwörter und Tokens (Fernet, `vault.py`). Aus ihm wird auch der Schlüssel der Chats abgeleitet (HKDF, AES-256-GCM). Er kommt nur in die **Umzugs-Sicherung**, versiegelt mit dem Passwort des Admins (`state/move-keys.json`, scrypt). Eine normale Sicherung auf einem anderen Spark verliert deshalb Chats und alle versiegelten Zugänge.
- `users/secret` und `state/admin-session.key` unterschreiben Anmeldungen und kommen nie in eine Sicherung. Nach einem Umzug melden sich alle neu an.
- Der Stimmabdruck `users/ID/voice.json` ist versiegelt wie ein Passwort (`speakers.py`), auch in der Sicherung. Eine ältere, offene Datei wird beim ersten Lesen versiegelt. Nach einer Sicherung auf einem anderen Spark nimmt das Profil seine Stimme neu auf.
- Die Sicherung nach außen (`offsite.py`) und der eigene Speicher (`speicher.py`) sind als Ganzes verschlüsselt (scrypt + AES-GCM, AES-256-GCM in Stücken von 1 MiB).

### Caches im Arbeitsspeicher

Diese Caches gehen bei einem Neustart verloren und enthalten nichts, was nicht neu geholt werden kann: Kalender 300 s, Mail 120 s, Bus und Bahn 60 s, Wetter 900 s, Pakete 600 s, Wikipedia und Kiwix 24 h, Bildfragen 600 s (Ergebnisse auch in `state/vision.json`), Antworten für die Uhr 600 s, die Vektoren der Dokumentsuche pro Profil, die Stimmen der Sprachausgabe.

### Logs

Alle Dienste schreiben in den journald-Namespace `speech-spark` (persistent, höchstens `logs.max_mb` = 500 MB, `logs.keep_days` = 14 Tage). In die Zeilen kommen nur feste Wörter und Zahlen, ein Profil nur über `profiles.log_name`. Der Anfrage-Verlauf (`state/traces.jsonl`, 48 h) läuft nur, solange der Admin-Schalter `logs.trace` an ist.

## Die Kästen im Einzelnen

Jeder Kasten im Bild hat eine eigene Seite (Zustand → Technik, Kasten anklicken, dann „Ganz genau“): was er macht und warum, sein Ablauf als Schaubild mit nummerierten Schritten, Regeln, Zahlen, wo man ihn einstellt und sieht, und sein Code. Die Texte stehen in `app/panel/technik_knoten.py`; Zahlen und Listen von Aufrufern werden aus dem Code gelesen.

<!-- technik:knoten -->
### Browser und Handy

Die Seite im Browser (static/js/chat.js) ist das Gerät: sie nimmt die Frage auf, schickt den Ton zur Spracherkennung, schickt den Text an /api/chat und spielt Text und Ton aus einem einzigen Strom ab. Die Gespräche eines Profils liegen auf dem Spark, jede offene Seite gleicht sie ab.

**Warum:** Gerechnet wird nur auf dem Spark; die Seite bleibt dünn. Browser, Handy-Browser und die Android-App (eine WebView) nehmen denselben Weg, deshalb gelten Anmeldung, Grenzen und Regeln an genau einer Stelle, und ein Gespräch sieht auf jedem Gerät gleich aus.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. „Sprechen“ getippt"])
  s2{{"2. Sichere Verbindung?"}}
  s3["3. Aufnehmen, Satzende erkennen"]
  s4["4. Ton an /api/test/asr"]
  s5{{"5. Stille, eigene oder fremde Stimme?"}}
  s6["6. Frage an /api/chat"]
  s7["7. Text und Ton in einem Strom"]
  s8{{"8. Spricht jemand dazwischen?"}}
  s9{{"9. Fehler im Strom?"}}
  s10["10. Gespräch speichern"]
  s11["11. Abgleich mit anderen Geräten"]
  s12(["12. Bereit"])
  s1 --> s2
  s2 -->|ja| s3
  s3 --> s4
  s4 --> s5
  s5 -->|nein| s6
  s6 --> s7
  s7 --> s8
  s8 -->|nein| s9
  s9 -->|nein| s10
  s10 --> s11
  s11 --> s12
  s2x(["Hinweis: Mikrofon braucht https"])
  s2 -->|nein| s2x
  s5x(["Überhört, nichts gesendet"])
  s5 -->|ja| s5x
  s8 -.->|ja| s4
  s9x(["Antwort als Text oder Hinweis"])
  s9 -->|ja| s9x
  s10x(["Gäste: nur in diesem Browser"])
  s10 -->|Gast| s10x
  s12 -.->|freihändig, Nachfrage| s3
```

1. <a id="kn-geraet-s1"></a>**„Sprechen“ getippt**: startListening holt das Mikrofon und merkt sich, wie es aufging: von Hand, nach einer Antwort (Nachfrage), freihändig oder durch Dazwischenreden. Ein Mikrofon, das die Seite selbst geöffnet hat, nimmt später nur eine bekannte Stimme an.
2. <a id="kn-geraet-s2"></a>**Sichere Verbindung?**: Browser geben das Mikrofon nur auf einer sicheren Seite frei. Ohne https zeigt die Seite einen Hinweis mit der https-Adresse des Panels und nimmt nichts auf.
3. <a id="kn-geraet-s3"></a>**Aufnehmen, Satzende erkennen**: MediaRecorder nimmt auf, ein Pegelmesser hört auf Stille. Etwa jede Sekunde geht die Aufnahme bis jetzt zur Spracherkennung und erscheint als blasse Blase. Endet der Satz mit Punkt, Frage- oder Ausrufezeichen, ist die Frage sofort fertig; endet er auf „und“, „weil“, „ähm“ oder einem Komma, wartet die Seite etwas länger.
4. <a id="kn-geraet-s4"></a>**Ton an /api/test/asr**: Die Seite wandelt die Aufnahme in ein einfaches WAV in Mono (sonst geht das Original). Der Spark prüft das Rate-Limit (240 pro Minute für ein Profil, Gäste höchstens 3 gleichzeitig), liest höchstens 50 MB und schickt den Ton an die Spracherkennung. Nebenher misst er auf der CPU, wie viel davon Stimme ist und wessen Stimme es ist.
5. <a id="kn-geraet-s5"></a>**Stille, eigene oder fremde Stimme?**: Feste Regeln, kein Modell: ein „Ja“ aus Stille oder einem Klick (stille.check), die eigene Stimme des Spark von einem anderen Gerät (echo.check) und bei selbst geöffnetem Mikrofon eine fremde Stimme, etwa vom Fernseher (fremdstimme.check), sind keine Frage. Die Antwort ist dann leerer Text mit dem Grund.
6. <a id="kn-geraet-s6"></a>**Frage an /api/chat**: Die Seite schickt die letzten Nachrichten des offenen Gesprächs, seine Kennung, Stimme, Tempo und, wenn die Stimme erkannt wurde, ein signiertes Einmal-Token. Der Spark prüft das Rate-Limit (120 pro Minute für ein Profil, Gäste höchstens 4 gleichzeitig), lässt Hintergrundarbeit warten (vorrang) und sagt den anderen offenen Seiten des Profils „antwortet gerade“ (nur die Art des Geräts).
7. <a id="kn-geraet-s7"></a>**Text und Ton in einem Strom**: Die Antwort kommt als Ereignisse: Textstücke, Tonstücke, Suche, Quellen, Rückfragen, Fehler. Der Text wird höchstens einmal pro Bild neu gezeichnet. Der Ton läuft in einem eigenen Audio-Kontext mit der Rate der Sprachausgabe; jedes Stück endet mit einer kurzen Blende, damit die Nähte nicht knacken.
8. <a id="kn-geraet-s8"></a>**Spricht jemand dazwischen?**: Während die Antwort spielt, hört das Mikrofon weiter. Ist der Pegel eine Weile deutlich über der eigenen Ausgabe und dem Raum (Fernseher), bricht die Antwort ab, und die schon laufende Aufnahme wird die nächste Frage.
9. <a id="kn-geraet-s9"></a>**Fehler im Strom?**: Ein Fehler erscheint unter der Antwort in einfachen Worten; der Admin sieht zusätzlich die technische Angabe, Gäste nur die Art des Fehlers. Fehlt nur die Sprachausgabe, bleibt die Antwort als Text.
10. <a id="kn-geraet-s10"></a>**Gespräch speichern**: Bei einem Profil schickt die Seite nur die neuen Nachrichten (PUT /api/profile/convos mit „add“). Der Spark hängt sie unter einer Sperre an seine Kopie an, damit ein anderes Gerät nichts überschreibt, und behält höchstens 50 Gespräche mit je 60 Nachrichten.
11. <a id="kn-geraet-s11"></a>**Abgleich mit anderen Geräten**: Kommt die Seite wieder nach vorn und regelmäßig dazwischen, fragt sie, was sich seit dem letzten Mal geändert hat; ein anderswo gelöschtes Gespräch schließt sich. Mit dem Sofort-Abgleich hält jede Seite einen Ereignis-Strom offen, der nur „Gespräch geändert“ und „antwortet gerade“ meldet, nie Inhalte (höchstens 8 pro Profil, je 30 Minuten).
12. <a id="kn-geraet-s12"></a>**Bereit**: Die Seite wartet, bis die Antwort ausgesprochen ist. Freihändig oder nach einer gesprochenen Frage mit Nachfrage-Fenster öffnet sie das Mikrofon wieder.

**Beispiele:** Gesprochene Frage eines Profils: Antwort gehört, auf dem Spark gespeichert, auf den anderen Geräten sichtbar. · Panel über http geöffnet: Kein Mikrofon: die Seite zeigt die https-Adresse. · Fernseher im Nachfrage-Fenster: Überhört: fremde Stimme, es geht keine Frage raus. · Dazwischenreden: Die Antwort bricht ab, das Gesagte wird die nächste Frage.

#### Regeln

Gilt bei: [Schritt 6](#kn-geraet-s6), [Schritt 10](#kn-geraet-s10)

| Wer | Gespräche liegen | Fragen pro Minute | gleichzeitig |
|---|---|---|---|
| Profil | auf dem Spark, gleich auf jedem Gerät | 120 | ohne feste Grenze |
| Gast | nur in diesem Browser | 30 | 4 Gäste zusammen |

#### Zahlen (aus dem Code)

- **50 MB** größte Aufnahme ([Schritt 4](#kn-geraet-s4))
- **120** Fragen pro Minute und Profil ([Schritt 4](#kn-geraet-s4), [Schritt 6](#kn-geraet-s6))
- **4** Gäste gleichzeitig im Chat ([Schritt 4](#kn-geraet-s4), [Schritt 6](#kn-geraet-s6))
- **50** Gespräche pro Profil ([Schritt 10](#kn-geraet-s10))
- **4 MB** größtes Gespräch beim Speichern ([Schritt 10](#kn-geraet-s10))
- **8** offene Seiten mit Sofort-Abgleich pro Profil ([Schritt 11](#kn-geraet-s11))

#### Einstellen

- Ich → Gespräch: die Gesprächs-Einstellungen des Profils, etwa Freihändig und Unterbrechen.
- Funktionen → Verlauf sofort abgleichen: der Ereignis-Strom zwischen den offenen Seiten (Standard aus).

#### Was du siehst

- Unter jeder Antwort: Zeiten für Spracherkennung, erstes Wort, ersten Ton und Aussetzer der Sprachausgabe.
- Logs → Anfragen: jede Frage mit Eingang „Browser“ und ihren Schritten, ohne Inhalt.
- Zustand → Live: die laufende Anfrage im Bild.

#### Im Code

- `app/panel/admin.py` `test_asr`: Rate-Limit, Gast-Plätze, dann die Erkennung ([Schritt 4](#kn-geraet-s4))
- `app/panel/admin.py` `_test_asr`: Spracherkennung mit Stille-, Echo- und Fremdstimmen-Prüfung ([Schritt 4](#kn-geraet-s4), [Schritt 5](#kn-geraet-s5))
- `app/panel/admin.py` `read_audio`: liest die Aufnahme mit Größengrenze ([Schritt 4](#kn-geraet-s4))
- `app/panel/stille.py` `check`: Stille wird nie zu Worten ([Schritt 5](#kn-geraet-s5))
- `app/panel/echo.py` `check`: die eigene Stimme des Spark ist keine Frage ([Schritt 5](#kn-geraet-s5))
- `app/panel/chat.py` `chat`: Grenzen, Vorrang, „antwortet gerade“, dann der Strom ([Schritt 6](#kn-geraet-s6), [Schritt 7](#kn-geraet-s7))
- `app/panel/account.py` `profile_save_convo`: speichert nur die neuen Nachrichten ([Schritt 10](#kn-geraet-s10))
- `app/panel/account.py` `profile_convos`: Liste und Änderungen seit ?since= ([Schritt 11](#kn-geraet-s11))
- `app/panel/profiles.py` `append_convo`: hängt unter Sperre an ([Schritt 10](#kn-geraet-s10))
- `app/panel/profiles.py` `_clean_convo`: prüft und kürzt ein Gespräch ([Schritt 10](#kn-geraet-s10))
- `app/panel/verlauf.py` `stream`: der Sofort-Abgleich je offener Seite ([Schritt 11](#kn-geraet-s11))
- `app/panel/verlauf.py` `begin`: „antwortet gerade“ für die anderen Seiten ([Schritt 6](#kn-geraet-s6), [Schritt 11](#kn-geraet-s11))

Selbsttests: `test_verlauf_sync`, `test_stille`, `test_echo`, `test_fremdstimme`, `test_follow_up`

### Apps

Die iPhone-App bekommt beim Koppeln einen eigenen Geräteschlüssel des Profils und spricht damit dieselben Endpunkte an wie der Browser. Der Schlüssel öffnet nur eine feste Liste von Pfaden. Die Android-App hat keinen eigenen Schlüssel: sie zeigt das Panel in einer WebView und meldet sich an wie ein Browser.

**Warum:** Ein Handy geht verloren oder wird weitergegeben. Deshalb kann ein App-Schlüssel nur fragen und zuhören, nie Konto, Geräte oder Sicherheit ändern, und er hört sofort auf zu gelten, wenn das Gerät im Panel entfernt oder die App ausgeschaltet wird.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Kopplung anfordern"])
  s2{{"2. App frei und Platz da?"}}
  s3["3. Einmal-Link als QR-Code"]
  s4{{"4. Code gültig?"}}
  s5["5. Eigener Geräteschlüssel"]
  s6["6. Jede Anfrage mit Schlüssel"]
  s7{{"7. Pfad für die App erlaubt?"}}
  s8{{"8. App gerade aus oder Mein Notaus?"}}
  s9["9. Wie ein Browser des Profils"]
  s10{{"10. Konto, Geräte oder Sicherheit?"}}
  s11(["11. Entfernen wirkt sofort"])
  s1 --> s2
  s2 -->|ja| s3
  s3 --> s4
  s4 -->|ja| s5
  s5 --> s6
  s6 --> s7
  s7 -->|ja| s8
  s8 -->|nein| s9
  s9 --> s10
  s10 -->|nein| s11
  s2x(["Abgelehnt"])
  s2 -->|nein| s2x
  s4x(["Link passt nicht oder ist abgelaufen"])
  s4 -->|nein| s4x
  s5x(["Android: kein Schlüssel; Download-Link mit Einmal-Token, Anmeldung wie im Browser"])
  s5 -->|Android| s5x
  s7x(["Kein Profil (401)"])
  s7 -->|nein| s7x
  s8x(["Gerade nicht (503)"])
  s8 -->|ja| s8x
  s10x(["Nur im eigenen Browser (403)"])
  s10 -->|ja| s10x
```

1. <a id="kn-apps-s1"></a>**Kopplung anfordern**: Nur die eigene Browser-Anmeldung des Profils darf koppeln, nie ein Geräteschlüssel. Hat das Profil einen zweiten Anmeldeschritt, braucht es dafür einen Code, denn ein neuer Weg ins Profil entsteht.
2. <a id="kn-apps-s2"></a>**App frei und Platz da?**: Die App muss vom Admin eingeschaltet und für das Profil nicht gesperrt sein, und das Profil darf höchstens 5 iPhones haben. Die Panel-Adresse muss mit https beginnen und ohne Pfad sein.
3. <a id="kn-apps-s3"></a>**Einmal-Link als QR-Code**: new_code macht einen zufälligen Code; im Speicher liegt nur sein Hash. Ein Profil hat höchstens 3 offene Codes, der Spark höchstens 20. Der Link spark-app://pair öffnet die App mit Adresse und Code.
4. <a id="kn-apps-s4"></a>**Code gültig?**: Die App schickt den Code. Der Spark prüft das Rate-Limit (10 pro Minute und Adresse), vergleicht den Hash zeitkonstant und löscht den Code beim ersten Treffer. Ein abgelaufener oder schon benutzter Code passt nie.
5. <a id="kn-apps-s5"></a>**Eigener Geräteschlüssel**: profiles.add_device erzeugt den Schlüssel und speichert nur seinen SHA-256-Hash in profiles.json. Die App bekommt ihn genau einmal und legt ihn im Schlüsselbund ab.
6. <a id="kn-apps-s6"></a>**Jede Anfrage mit Schlüssel**: profiles.current sucht den Hash des Schlüssels in der Geräteliste. Ein Geräteschlüssel geht vor dem Cookie; das Profil kommt so immer aus dem Schlüssel, nie aus dem, was die App schreibt.
7. <a id="kn-apps-s7"></a>**Pfad für die App erlaubt?**: Ein App-Schlüssel gilt nur für die 57 Pfade in profiles.APP_PATHS (Chat, Spracherkennung, Gespräche, Erinnerungen, Chats …), ein paar Lese-Muster und die Panel-Bereiche, die das Profil für die App einzeln freigegeben hat. Alles andere sieht er ohne Profil.
8. <a id="kn-apps-s8"></a>**App gerade aus oder Mein Notaus?**: Ist die App vom Admin aus- oder für das Profil gesperrt, oder hat das Profil Mein Notaus an, gibt es für diese Anfrage kein Profil. Die App bekommt „gerade nicht“ (503), behält ihre Kopplung und geht wieder, sobald der Schalter zurück ist.
9. <a id="kn-apps-s9"></a>**Wie ein Browser des Profils**: Die App fragt über dieselben Endpunkte wie die Seite, mit denselben Grenzen. Was sie zusätzlich darf (Smart Home, CarPlay, Zuhören, Dokumente, Bilder), sagt ihr der Spark in /api/iphone/hello; die App zeigt es nur an und hält sich daran.
10. <a id="kn-apps-s10"></a>**Konto, Geräte oder Sicherheit?**: Endpunkte, die Verbindungen, Geräte oder Sicherheit des Profils ändern, nehmen nur die eigene Browser-Anmeldung (core.browser_profile). Einen Geräteschlüssel lehnen sie ab, außer in einem Bereich, den das Profil der App freigegeben hat; Geheimnisse brauchen dort zusätzlich einen frischen Code.
11. <a id="kn-apps-s11"></a>**Entfernen wirkt sofort**: Wird das iPhone im Panel entfernt, verschwindet der Hash aus der Geräteliste. Die nächste Anfrage der App findet kein Profil mehr.

**Beispiele:** iPhone koppeln und fragen: Die App hat ihren Schlüssel und fragt wie der Browser. · Alter QR-Code: Abgelehnt: der Code war schon benutzt oder abgelaufen. · App will die PIN ändern: Abgelehnt: das geht nur im eigenen Browser. · Admin schaltet die App aus: Gerade nicht: die Kopplung bleibt für später.

#### Regeln

Gilt bei: [Schritt 6](#kn-apps-s6), [Schritt 7](#kn-apps-s7)

| Schlüssel-Bereich | Wer ihn hat | Was er öffnet |
|---|---|---|
| app | iPhone-App | profiles.APP_PATHS und freigegebene Bereiche |
| watch | Pebble-Uhr | nur /api/watch/… |
| desk, write | Spark-Begleiter, Schreibhilfe | nur ihre eigenen Pfade |
| ohne | Lautsprecher, Siri-Kurzbefehl, eigene Skripte | fragen wie das Profil, nie Konto oder Sicherheit |
| kein Schlüssel | Android-App | Anmeldung wie ein Browser |

#### Zahlen (aus dem Code)

- **10** Minuten gilt ein Kopplungs-Code ([Schritt 3](#kn-apps-s3))
- **5** iPhones pro Profil ([Schritt 2](#kn-apps-s2))
- **57** feste Pfade für den App-Schlüssel ([Schritt 7](#kn-apps-s7))
- **30** Minuten gilt ein Android-Download-Link ([Schritt 3](#kn-apps-s3))
- **5** Downloads pro Android-Link ([Schritt 3](#kn-apps-s3))

#### Einstellen

- Funktionen → iPhone-App und Funktionen → Android-App: die Apps für alle Profile (Standard aus).
- Funktionen → Wer darf was: die App für einzelne Profile sperren.
- Ich → iPhone und Ich → Android: koppeln, Rechte der App, Geräte entfernen.

#### Was du siehst

- Zustand → Live: eine Zeile unter Ereignisse, wenn ein iPhone gekoppelt oder entfernt wird.
- Logs → Anfragen: Fragen der App mit Eingang „iPhone-App“ oder „CarPlay“.

#### Im Code

- `app/panel/iphone.py` `profile_pair`: Kopplungslink nur aus dem eigenen Browser ([Schritt 1](#kn-apps-s1), [Schritt 2](#kn-apps-s2))
- `app/panel/iphone.py` `new_code`: zufälliger Einmal-Code, nur der Hash ([Schritt 3](#kn-apps-s3))
- `app/panel/iphone.py` `take_code`: Code einmal einlösen ([Schritt 4](#kn-apps-s4))
- `app/panel/iphone.py` `app_pair`: der erste Kontakt der App ([Schritt 4](#kn-apps-s4), [Schritt 5](#kn-apps-s5))
- `app/panel/iphone.py` `app_hello`: was die App darf, entscheidet der Spark ([Schritt 9](#kn-apps-s9))
- `app/panel/profiles.py` `add_device`: Schlüssel erzeugen, Hash speichern ([Schritt 5](#kn-apps-s5))
- `app/panel/profiles.py` `current`: Profil aus Schlüssel oder Cookie, Bereiche, Schalter, Notaus ([Schritt 6](#kn-apps-s6))
- `app/panel/profiles.py` `_app_path`: die feste Pfadliste der App ([Schritt 7](#kn-apps-s7))
- `app/panel/core.py` `browser_profile`: nur die eigene Browser-Anmeldung ([Schritt 10](#kn-apps-s10))
- `app/panel/account.py` `profile_remove_device`: Gerät entfernen ([Schritt 11](#kn-apps-s11))
- `app/panel/android.py` `apk_response`: App-Datei nur mit gültigem Link ([Schritt 3](#kn-apps-s3))

Selbsttests: `test_iphone`, `test_iphone_panel`, `test_android`, `test_app_notaus`

### Telegram, Siri, Uhr

Telegram, der Siri-Kurzbefehl und die Pebble-Uhr stellen kurze Fragen ohne Browser. Jeder Kanal baut daraus eine Anfrage an /api/chat wie ein Gerät, sammelt die Antwort aus dem Strom ein und gibt sie in seiner Form zurück. Den Verlauf speichert das Panel selbst im Profil.

**Warum:** Die Kanäle sollen nichts eigenes entscheiden: dieselben Rechte, Sperren und Grenzen wie im Browser gelten, weil alles durch denselben Chat läuft. Was ein Kanal zusätzlich mitbringt (fremde weitergeleitete Texte, Telegrams Server), wird vorher fest geregelt.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Frage über einen Kanal"])
  s2{{"2. Telegram: Chat verknüpft?"}}
  s3{{"3. Gesperrt oder Mein Notaus?"}}
  s4{{"4. Weitergeleitet?"}}
  s5["5. Sprachnachricht in Text"]
  s6["6. Kurzer Verlauf"]
  s7["7. Anfrage an /api/chat"]
  s8["8. Antwort einsammeln"]
  s9["9. Ausgabe je Kanal"]
  s10["10. Codewort schwärzen"]
  s11(["11. Im Verlauf des Profils"])
  s1 --> s2
  s2 -->|ja| s3
  s3 -->|nein| s4
  s4 -->|nein| s5
  s5 --> s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 --> s10
  s10 --> s11
  s2x(["Fester Satz, sonst nichts"])
  s2 -->|nein| s2x
  s3x(["Keine Antwort, kein Werkzeug"])
  s3 -->|ja| s3x
  s4x(["Fester Hinweis"])
  s4 -->|ja| s4x
```

1. <a id="kn-kanaele-s1"></a>**Frage über einen Kanal**: Telegram: das Panel fragt Telegram selbst nach neuen Nachrichten (Long Polling), es braucht keinen offenen Port. Siri: ein Kurzbefehl schickt den diktierten Text mit einem Geräteschlüssel an /api/siri/ask. Uhr: das Handy schickt die Frage mit dem Uhr-Schlüssel an /api/watch/ask.
2. <a id="kn-kanaele-s2"></a>**Telegram: Chat verknüpft?**: Gruppen und Kanäle werden nie beantwortet. Ein Chat gehört zu einem Profil, wenn er „/start CODE“ mit einem Code aus Ich → Telegram geschickt hat (gilt 10 Minuten, höchstens 5 falsche Codes pro Chat und Stunde). Ein fremder Chat bekommt höchstens einmal am Tag einen festen Satz.
3. <a id="kn-kanaele-s3"></a>**Gesperrt oder Mein Notaus?**: Mein Notaus des Profils, eine Sperre durch den Admin oder ein ausgeschalteter Kanal beenden die Frage. Telegram antwortet dann mit einem festen Satz; Siri und die Uhr finden zu ihrem Schlüssel kein Profil.
4. <a id="kn-kanaele-s4"></a>**Weitergeleitet?**: Eine in Telegram weitergeleitete Nachricht stammt von jemand anderem. Sie wird nie als Auftrag genommen und schaltet auch keine Befehle wie /notaus.
5. <a id="kn-kanaele-s5"></a>**Sprachnachricht in Text**: Eine Telegram-Sprachnachricht wird mit Größengrenze geladen, mit ffmpeg zu WAV gewandelt (Länge begrenzt) und von der Spracherkennung des Spark gelesen. Bei Siri diktiert das iPhone, bei der Uhr das Handy.
6. <a id="kn-kanaele-s6"></a>**Kurzer Verlauf**: Für Nachfragen gehen die letzten acht Nachrichten mit, solange die letzte Frage nicht länger her ist als 30 Minuten (Telegram) oder 10 Minuten (Siri). Die Uhr schickt ihren Verlauf selbst; Antworten aus fremdem Text erkennt das Panel daran wieder (watch.mark_of).
7. <a id="kn-kanaele-s7"></a>**Anfrage an /api/chat**: Der Kanal ruft den Chat im Panel selbst auf. Bei Telegram setzt das Panel das Profil in die Anfrage, was keine Anfrage von außen kann; Siri und die Uhr tragen ihren Schlüssel. Rechte, Weiche, Grenzen und Anfrage-Verlauf sind dieselben wie im Browser.
8. <a id="kn-kanaele-s8"></a>**Antwort einsammeln**: Aus dem Strom zählen Textstücke und Rücknahmen. Kam die Antwort aus Mail oder fremdem Text, wird sie so markiert, damit die nächste Frage gesperrt beginnt. Eine Rückfrage des Panels wird in Telegram zu Knöpfen, die wie eine getippte Antwort zurückkommen.
9. <a id="kn-kanaele-s9"></a>**Ausgabe je Kanal**: Telegram bekommt reinen Text und, wenn das Profil es will, eine Sprachnachricht in seiner Stimme. Siri bekommt vorlesbaren Text ohne Passwörter und Codes. Die Uhr holt Text und Ton (auf 6000 Bytes je Abruf, für ihren kleinen Lautsprecher gepackt) über /api/watch/poll; höchstens 8 Uhr-Antworten laufen gleichzeitig. Der Begleiter bekommt Text ohne Markdown und zusätzlich die Antwort mit Markdown (höchstens 60000 Zeichen), wenn darin nicht weniger Geheimnisse verdeckt sind.
10. <a id="kn-kanaele-s10"></a>**Codewort schwärzen**: Vor dem Speichern wird das Smart-Home-Codewort durch [Codewort] ersetzt. In Telegram löscht der Bot die Nachricht mit dem Codewort oder bittet darum, sie zu löschen.
11. <a id="kn-kanaele-s11"></a>**Im Verlauf des Profils**: verlauf.keep legt Frage und Antwort in das Tagesgespräch des Kanals („Telegram“, „Siri“, „Uhr“ mit Datum). Mit „Ein Gespräch für alle Kanäle“ landen sie im Hauptgespräch des Tages, markiert mit ihrem Kanal.

**Beispiele:** Telegram-Sprachnachricht: Beantwortet und im Gespräch „Telegram“ des Tages gespeichert. · Fremder schreibt dem Bot: Ein fester Satz, sonst nichts. · Weitergeleitete Mail mit Auftrag: Nicht ausgeführt: fremde Worte sind kein Auftrag. · Siri bei Mein Notaus: Keine Antwort: der Schlüssel findet kein Profil.

#### Regeln

Gilt bei: [Schritt 1](#kn-kanaele-s1), [Schritt 9](#kn-kanaele-s9), [Schritt 11](#kn-kanaele-s11)

| Kanal | Wie er sich ausweist | Verlauf | Ausgabe |
|---|---|---|---|
| Telegram | verknüpfter privater Chat | „Telegram“ und Datum | Text, auf Wunsch Sprachnachricht |
| Siri | Geräteschlüssel des Profils | „Siri“ und Datum | vorlesbarer Text ohne Geheimnisse |
| Uhr | Uhr-Schlüssel, nur /api/watch/… | „Uhr“ und Datum | Text ohne Markdown und Ton |

#### Zahlen (aus dem Code)

- **10** Minuten gilt ein Telegram-Code ([Schritt 2](#kn-kanaele-s2))
- **5** falsche Codes pro Chat und Stunde ([Schritt 2](#kn-kanaele-s2))
- **5 MB** größte Sprachnachricht ([Schritt 5](#kn-kanaele-s5))
- **10** Minuten zählen bei Siri frühere Fragen ([Schritt 6](#kn-kanaele-s6))
- **8** Uhr-Antworten gleichzeitig ([Schritt 9](#kn-kanaele-s9))
- **10** Minuten bleibt eine Uhr-Antwort abrufbar ([Schritt 9](#kn-kanaele-s9))

#### Einstellen

- Funktionen → Telegram: Bot-Token und Schalter (Standard aus).
- Ich → Telegram: den eigenen Chat verknüpfen; Sprachnachrichten, private Daten, Smart Home und Mitteilungen einzeln erlauben.
- Ich → Pebble-Uhr: die Uhr koppeln.
- Funktionen → Ein Gespräch für alle Kanäle: alle Kanäle schreiben ins Hauptgespräch des Tages.

#### Was du siehst

- Logs → Anfragen: Eingang „Telegram“, „Siri“ oder „Uhr“, ohne Inhalt.
- Zustand → Live: die laufende Anfrage im Bild.

#### Im Code

- `app/panel/telegram.py` `loop`: fragt Telegram, ruht bei Notaus ([Schritt 1](#kn-kanaele-s1))
- `app/panel/telegram.py` `handle`: eine Nachricht: Verknüpfung, Sperren, Befehle, Sprache ([Schritt 2](#kn-kanaele-s2), [Schritt 3](#kn-kanaele-s3), [Schritt 4](#kn-kanaele-s4))
- `app/panel/telegram.py` `ask`: Frage an den Chat, Antwort einsammeln, speichern ([Schritt 7](#kn-kanaele-s7), [Schritt 8](#kn-kanaele-s8), [Schritt 11](#kn-kanaele-s11))
- `app/panel/telegram.py` `transcribe`: Sprachnachricht über ffmpeg zur Spracherkennung ([Schritt 5](#kn-kanaele-s5))
- `app/panel/chat.py` `siri_ask`: Siri: Profil aus dem Schlüssel ([Schritt 1](#kn-kanaele-s1), [Schritt 3](#kn-kanaele-s3))
- `app/panel/chat.py` `text_ask`: Siri und Begleiter: Frage, Antwort, Verlauf ([Schritt 6](#kn-kanaele-s6), [Schritt 7](#kn-kanaele-s7), [Schritt 11](#kn-kanaele-s11))
- `app/panel/chat.py` `watch_ask`: Uhr: Antwort als Auftrag starten ([Schritt 1](#kn-kanaele-s1), [Schritt 7](#kn-kanaele-s7))
- `app/panel/chat.py` `_watch_run`: Uhr: Antwort in den Verlauf ([Schritt 11](#kn-kanaele-s11))
- `app/panel/watch.py` `run`: liest den Strom in den Uhr-Auftrag ([Schritt 8](#kn-kanaele-s8))
- `app/panel/watch.py` `poll`: Text und Ton stückweise ([Schritt 9](#kn-kanaele-s9))
- `app/panel/verlauf.py` `keep`: Tagesgespräch des Kanals oder Hauptgespräch ([Schritt 11](#kn-kanaele-s11))

Selbsttests: `test_telegram_tasks`, `test_pebble`, `test_verlauf_sync`, `test_notaus`

### Lautsprecher, HA

Eigene Lautsprecher sind ESP32-Boards mit der offenen XiaoZhi-Firmware. Sie hören auf ihr Weckwort, schicken den Ton über eine WebSocket-Verbindung an den Spark und spielen die Antwort ab. Jeder Lautsprecher ist ein Geräteschlüssel seines Profils. Home Assistant Assist nutzt über Wyoming nur Spracherkennung und Stimme des Spark.

**Warum:** Ein Lautsprecher steht im Raum, jeder kann mit ihm reden. Deshalb bekommt Persönliches nur die Stimme, die sicher als die des Profils erkannt ist (oder das Codewort sagt), und ein Board bekommt seinen Schlüssel nur einmal und nur an die Adresse, die den Code gezeigt hat.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Board startet"])
  s2{{"2. Board bekannt?"}}
  s3{{"3. Gleiches Board?"}}
  s4["4. Antwort der Start-Prüfung"]
  s5{{"5. Verbindung erlaubt?"}}
  s6["6. Zuhören"]
  s7["7. Erkennen und Stimme prüfen"]
  s8{{"8. Nichts, Stopp oder eigene Stimme?"}}
  s9{{"9. Persönliches ohne sichere Stimme?"}}
  s10["10. Wie ein Gerät an /api/chat"]
  s11["11. Ton zurück"]
  s12(["12. Im Verlauf des Lautsprechers"])
  s1 --> s2
  s2 -->|ja| s3
  s3 -->|ja| s4
  s4 --> s5
  s5 -->|ja| s6
  s6 --> s7
  s7 --> s8
  s8 -->|nein| s9
  s9 -->|nein| s10
  s10 --> s11
  s11 --> s12
  s2x(["Code am Board, wartet aufs Eintippen"])
  s2 -->|nein| s2x
  s3x(["Abgelehnt (403)"])
  s3 -->|nein| s3x
  s5x(["Verbindung abgelehnt"])
  s5 -->|nein| s5x
  s8x(["Keine Antwort"])
  s8 -->|ja| s8x
  s9x(["„Sag bitte dein Codewort“"])
  s9 -->|ja| s9x
```

1. <a id="kn-lautsprecher-s1"></a>**Board startet**: Bei jedem Start fragt das Board mit seiner Kennung, MAC-Adresse und Firmware-Version, welchen Server und welche Firmware es nehmen soll. Sind die Lautsprecher in Funktionen aus, gibt es nichts (403).
2. <a id="kn-lautsprecher-s2"></a>**Board bekannt?**: Ein unbekanntes Board bekommt einen sechsstelligen Code für sein Display (gilt 10 Minuten, höchstens 3 pro Adresse und 30 insgesamt). Das Profil tippt ihn unter Ich → Lautsprecher ein.
3. <a id="kn-lautsprecher-s3"></a>**Gleiches Board?**: Ist zu einer Board-Kennung schon eine MAC-Adresse bekannt, muss sie passen. Eine kopierte Kennung von einem anderen Board bekommt keinen Schlüssel und keine Firmware.
4. <a id="kn-lautsprecher-s4"></a>**Antwort der Start-Prüfung**: Das Board bekommt Uhrzeit und WebSocket-Adresse. Den Schlüssel gibt es genau einmal, direkt nach dem Eintippen, und nur an die Adresse, die den Code gezeigt hat. Eine neuere Firmware wird nur über https angeboten, über http nur mit dem Schalter des Admins.
5. <a id="kn-lautsprecher-s5"></a>**Verbindung erlaubt?**: Beim Aufbau prüft der Spark: Notaus Stufe 3 aus, der Schlüssel gehört einem Lautsprecher (nicht einer Uhr oder einem anderen Gerät), Lautsprecher in Funktionen an und für das Profil nicht gesperrt. Danach schaut er alle 2.0 Sekunden wieder nach und beendet die Verbindung, wenn sich etwas geändert hat.
6. <a id="kn-lautsprecher-s6"></a>**Zuhören**: Nach dem Weckwort schickt das Board Opus-Ton. Der Spark erkennt das Satzende selbst (0.7 Sekunden Stille nach Sprache) und nimmt höchstens 30 Sekunden pro Frage.
7. <a id="kn-lautsprecher-s7"></a>**Erkennen und Stimme prüfen**: Die Spracherkennung macht Text daraus. Gleichzeitig prüft speakers.verify, ob es die Stimme des Profils ist, wenn die Sprechererkennung an ist und das Profil seine Stimme angelernt hat.
8. <a id="kn-lautsprecher-s8"></a>**Nichts, Stopp oder eigene Stimme?**: Kein Text, ein Stopp-Wort oder die eigene Stimme des Spark von einem anderen Gerät (echo.check) bekommen keine Antwort. Das Board wartet wieder auf sein Weckwort.
9. <a id="kn-lautsprecher-s9"></a>**Persönliches ohne sichere Stimme?**: Mit Codewort am Lautsprecher: eine unsichere Stimme, die nach Persönlichem fragt, wird nach dem Codewort gefragt, die Frage wartet. Nach 3 falschen Versuchen fragt der Lautsprecher 30 Minuten lang nicht mehr. Ohne sichere Stimme gibt es nur Allgemeines.
10. <a id="kn-lautsprecher-s10"></a>**Wie ein Gerät an /api/chat**: Der Spark ruft den Chat mit dem Schlüssel des Lautsprechers auf; Stimme, Gedächtnis und Raum des Profils gelten. Wessen Stimme es war, setzt nur das Panel selbst in die Anfrage; war sie nicht sicher die des Profils, gilt die Frage wie die eines Gastes.
11. <a id="kn-lautsprecher-s11"></a>**Ton zurück**: Die Antwort geht als Opus mit 24000 Hz im Takt der Wiedergabe zum Board, der Text ohne Markdown für ein Display. Andere Geräte im Haus wissen, dass gerade der Spark spricht (echo.said).
12. <a id="kn-lautsprecher-s12"></a>**Im Verlauf des Lautsprechers**: Frage und Antwort kommen in das Tagesgespräch des Lautsprechers, das Codewort geschwärzt. Eine Stimme, die nicht sicher die des Profils war, wird als fremder Text markiert: die nächste Frage beginnt gesperrt, und daraus wird nichts über das Profil gelernt.

**Beispiele:** Inhaber fragt nach seinen Terminen: Stimme erkannt: persönliche Antwort, im Tagesgespräch gespeichert. · Neues Board: Code auf dem Display, bis das Profil ihn eintippt. · Kopierte Board-Kennung: Abgelehnt: die MAC-Adresse passt nicht. · Gast fragt nach Mails: Codewort erfragt; ohne richtiges Codewort nichts Persönliches.

#### Regeln

Gilt bei: [Schritt 5](#kn-lautsprecher-s5), [Schritt 9](#kn-lautsprecher-s9)

| Weg | Wer darf | Was geht | Persönliches |
|---|---|---|---|
| ESP32-Lautsprecher | Schlüssel eines Lautsprechers, Profil nicht gesperrt | Fragen wie das Profil | nur bei sicherer Stimme oder Codewort |
| Home Assistant Assist | Adressen in der Erlaubt-Liste des Admins | nur Ton zu Text und Text zu Ton | nie |

#### Home Assistant Assist (Wyoming)

- Ein eigener Server lauscht auf dem Wyoming-Port (Standard 31003), solange der Schalter an ist. Wyoming hat kein Passwort; deshalb antwortet er nur Adressen aus der Liste des Admins, mit leerer Liste niemandem.
- Home Assistant bekommt nur „Ton rein, Text raus“ und „Text rein, Ton raus“, kein Sprachmodell, kein Profil, nichts Persönliches. Höchstens 8 Verbindungen gleichzeitig; Längen werden geprüft, bevor gelesen wird; nur Tonformate, die ein Mikrofon schickt.
- Abgewiesene Adressen erscheinen auf Zustand → Live unter Eingang und als Vorschlag für die Liste.

#### Zahlen (aus dem Code)

- **10** Minuten gilt ein Kopplungs-Code ([Schritt 2](#kn-lautsprecher-s2))
- **30** Sekunden Ton pro Frage ([Schritt 6](#kn-lautsprecher-s6))
- **2.0** Sekunden, dann werden die Rechte neu geprüft ([Schritt 5](#kn-lautsprecher-s5))
- **10** Minuten zählen frühere Fragen am Lautsprecher ([Schritt 12](#kn-lautsprecher-s12))
- **3** falsche Codewörter bis zur Sperre ([Schritt 9](#kn-lautsprecher-s9))
- **8** Wyoming-Verbindungen gleichzeitig ([Schritt 5](#kn-lautsprecher-s5))

#### Einstellen

- Funktionen → Eigene Lautsprecher: Lautsprecher für alle Profile (Standard aus).
- Ich → Lautsprecher: einrichten, Code eintippen, Raum, Lautstärke, Prüfen und das eigene Codewort.
- Funktionen → Home Assistant Assist: Wyoming an und die erlaubten Adressen.

#### Was du siehst

- Ich → Lautsprecher → Prüfen: was der Lautsprecher zuletzt getan hat (nur im Speicher, weg nach einem Neustart).
- Zustand → Live: Anfragen vom Lautsprecher und von Home Assistant, abgewiesene Wyoming-Adressen unter Eingang.

#### Im Code

- `app/panel/esp32.py` `ota`: Start-Prüfung: Code, Schlüssel einmal, Update ([Schritt 1](#kn-lautsprecher-s1))
- `app/panel/esp32.py` `_activation`: sechsstelliger Code mit Grenzen ([Schritt 2](#kn-lautsprecher-s2))
- `app/panel/esp32.py` `same_board`: MAC muss passen ([Schritt 3](#kn-lautsprecher-s3))
- `app/panel/esp32.py` `speaker_ws`: Verbindung annehmen und laufend prüfen ([Schritt 5](#kn-lautsprecher-s5))
- `app/panel/esp32.py` `still_allowed`: Schalter und Gerät noch gültig ([Schritt 5](#kn-lautsprecher-s5))
- `app/panel/esp32.py` `Session.run_answer`: erkennen, filtern, Codewort, antworten ([Schritt 10](#kn-lautsprecher-s10))
- `app/panel/esp32.py` `Session.code_gate`: Codewort bei unsicherer Stimme ([Schritt 9](#kn-lautsprecher-s9))
- `app/panel/esp32.py` `Session.speak`: Chat mit dem Schlüssel, Ton zurück ([Schritt 11](#kn-lautsprecher-s11))
- `app/panel/esp32.py` `remember`: Tagesgespräch, fremde Stimme markiert ([Schritt 12](#kn-lautsprecher-s12))
- `app/panel/wyoming.py` `settings`: Schalter, Port, erlaubte Adressen ([Schritt 5](#kn-lautsprecher-s5))
- `app/panel/wyoming.py` `handle`: nur erlaubte Adressen, höchstens so viele ([Schritt 5](#kn-lautsprecher-s5))
- `app/panel/wyoming.py` `_session`: Ton zu Text und Text zu Ton ([Schritt 7](#kn-lautsprecher-s7), [Schritt 11](#kn-lautsprecher-s11))

Selbsttests: `test_esp32`, `test_wyoming`, `test_notaus`, `test_echo`

### MCP-Programme

Andere Programme (Claude, n8n, Open WebUI, Home Assistant) nutzen den Spark über das Model Context Protocol unter /mcp. Jede Verbindung gehört einem Profil, hat ihren eigenen Schlüssel und ihre eigene Werkzeugliste. Lesen geht direkt, Handeln nur als Vorschlag, den das Profil bestätigt.

**Warum:** Was ein Programm schickt, ist Text von außen und nie ein Befehl. Deshalb entscheidet das Panel mit festen Listen, welches Werkzeug laufen darf, und nichts ändert sich ohne das Ja der Person im eigenen Browser.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Programm schickt eine Anfrage"])
  s2{{"2. Von einer fremden Webseite?"}}
  s3{{"3. Schlüssel gültig?"}}
  s4{{"4. Heimnetz-Schlüssel von außen?"}}
  s5{{"5. Mein Notaus oder Profil gesperrt?"}}
  s6["6. Rate-Limit und Größe"]
  s7{{"7. Werkzeug freigegeben?"}}
  s8{{"8. Zu viele gleichzeitig?"}}
  s9["9. Sprache und Lesen"]
  s10["10. Spark fragen, nur lesend"]
  s11{{"11. Soll etwas geändert werden?"}}
  s12(["12. Antwort ans Programm"])
  s1 --> s2
  s2 -->|nein| s3
  s3 -->|ja| s4
  s4 -->|nein| s5
  s5 -->|nein| s6
  s6 --> s7
  s7 -->|ja| s8
  s8 -->|nein| s9
  s9 --> s10
  s10 --> s11
  s11 -->|nein| s12
  s2x(["Abgelehnt (403)"])
  s2 -->|ja| s2x
  s3x(["Nicht angemeldet (401)"])
  s3 -->|nein| s3x
  s4x(["Abgelehnt (403)"])
  s4 -->|ja| s4x
  s5x(["Gesperrt"])
  s5 -->|ja| s5x
  s7x(["„nicht freigegeben“"])
  s7 -->|nein| s7x
  s8x(["„bitte gleich noch einmal“"])
  s8 -->|ja| s8x
  s11x(["Vorgeschlagen, noch nicht ausgeführt"])
  s11 -->|ja| s11x
```

1. <a id="kn-mcpc-s1"></a>**Programm schickt eine Anfrage**: Jede Anfrage ist eine JSON-RPC-Nachricht. Ist der MCP-Server vom Admin aus, gibt es den Endpunkt nicht (404).
2. <a id="kn-mcpc-s2"></a>**Von einer fremden Webseite?**: Schickt ein Browser einen Origin, muss es der des Panels sein. So kann keine fremde Seite den Endpunkt über DNS-Rebinding benutzen.
3. <a id="kn-mcpc-s3"></a>**Schlüssel gültig?**: Der Bearer-Schlüssel ist ein fester Schlüssel oder ein OAuth-Zugangstoken (gilt 60 Minuten). Gespeichert sind nur Hashes. Eine Verbindung endet nach 90 Tagen ohne Nutzung.
4. <a id="kn-mcpc-s4"></a>**Heimnetz-Schlüssel von außen?**: Ein Schlüssel „lokal“ gilt nur, wenn die Gegenstelle eine private Adresse ist, kein Proxy-Kopf in der Anfrage steht und sie keiner der eingetragenen Reverse Proxys ist. „extern“ geht nur mit dem Schalter des Admins.
5. <a id="kn-mcpc-s5"></a>**Mein Notaus oder Profil gesperrt?**: Mein Notaus des Profils sperrt jeden MCP-Zugang (503); hat der Admin den MCP-Server für das Profil gesperrt, gibt es nichts (403).
6. <a id="kn-mcpc-s6"></a>**Rate-Limit und Größe**: Jede Verbindung darf 60 Anfragen pro Minute schicken; eine Anfrage ist höchstens 16 MB groß. Viele abgewiesene Anfragen von außen zählen für „Notaus von selbst“.
7. <a id="kn-mcpc-s7"></a>**Werkzeug freigegeben?**: Nur Werkzeuge aus der festen Liste (15), nur die, die dieser Verbindung gegeben wurden, und nur, wenn das Profil die Funktion gerade nutzen darf, bei jedem Aufruf neu geprüft. Mail, Gedächtnis, frühere Gespräche, Einstellungen und Code sind nie dabei (31 Namen in mcpserver.NEVER).
8. <a id="kn-mcpc-s8"></a>**Zu viele gleichzeitig?**: Höchstens 2 Aufrufe einer Verbindung und 6 aller Verbindungen laufen gleichzeitig.
9. <a id="kn-mcpc-s9"></a>**Sprache und Lesen**: Spracherkennung (höchstens 10 MB) und Sprachausgabe (höchstens 2000 Zeichen) laufen mit der Stufe „hinten“, damit Menschen am Spark immer zuerst dran sind. Die Lese-Werkzeuge lesen nur die Daten dieses Profils.
10. <a id="kn-mcpc-s10"></a>**Spark fragen, nur lesend**: ask_spark (10 pro Minute) läuft als ein Zug des Assistenten für das Profil, aber nur mit den Lese-Werkzeugen dieser Verbindung. Die Frage gilt von Anfang an als fremder Text: nichts wird geschaltet, gespeichert, gelernt oder gesendet, kein Gedächtnis, nichts davon im Verlauf. Passwörter und Codes werden aus der Antwort entfernt.
11. <a id="kn-mcpc-s11"></a>**Soll etwas geändert werden?**: Smart Home, Erinnerung und Termin werden nur vorgeschlagen (höchstens 10 offen). Das Profil bekommt eine Mitteilung und entscheidet unter Ich → Dienste per MCP innerhalb von 15 Minuten; erst dann führt das Panel es aus. Bei Notaus oder gesetztem Smart-Home-Codewort schaltet ein MCP-Programm nichts.
12. <a id="kn-mcpc-s12"></a>**Antwort ans Programm**: Die Antwort wird auf 12000 Zeichen gekürzt. Ins Journal kommt nur, welches Programm, welches Werkzeug, ob es ging und wie lange, nie Frage oder Antwort.

**Beispiele:** Claude liest die Termine: Termine des Profils als Text, gekürzt. · Heimnetz-Schlüssel über den Proxy: Abgelehnt: dieser Schlüssel gilt nur im Heimnetz. · n8n will das Licht schalten: Nur vorgeschlagen; es schaltet erst nach dem Ja im Browser. · Programm will Mails lesen: Nicht freigegeben: Mail gibt es über MCP nie.

#### Regeln

Gilt bei: [Schritt 9](#kn-mcpc-s9)

| Gruppe | Werkzeuge | Was passiert |
|---|---|---|
| Sprache | transcribe, speak, voices | Dienste mit Stufe „hinten“ |
| Lesen | wikipedia, archive_search, document_search, calendar_events, reminder_list, today, write_text | liest nur, speichert nichts |
| Spark fragen | ask_spark | ein Zug nur mit Lese-Werkzeugen |
| Handeln mit Bestätigung | home_assistant, reminder_set, calendar_add | nur Vorschlag, das Profil sagt Ja |
| nie | Mail, Gedächtnis, Verlauf, Einstellungen, Code | gibt es unter keinem Namen |

#### Zahlen (aus dem Code)

- **90** Tage ohne Nutzung, dann endet eine Verbindung ([Schritt 3](#kn-mcpc-s3))
- **10** Verbindungen pro Profil ([Schritt 3](#kn-mcpc-s3))
- **60** Anfragen pro Minute je Verbindung ([Schritt 6](#kn-mcpc-s6), [Schritt 10](#kn-mcpc-s10))
- **2** Aufrufe gleichzeitig je Verbindung ([Schritt 8](#kn-mcpc-s8))
- **12000** Zeichen höchstens in einer Antwort ([Schritt 12](#kn-mcpc-s12))
- **15** Minuten wartet ein Vorschlag auf das Ja ([Schritt 11](#kn-mcpc-s11))

#### Einstellen

- Funktionen → Spark als MCP-Server: der Server für alle Profile (Standard aus).
- Funktionen → Spark als MCP-Server → MCP-Server von außen: Verbindungen über den Reverse Proxy und OAuth.
- Funktionen → Spark als MCP-Server → MCP: Handeln mit Bestätigung: die Werkzeuge, die etwas vorschlagen.
- Ich → Dienste per MCP: Verbindungen anlegen, Werkzeuge wählen, Vorschläge bestätigen oder ablehnen.

#### Was du siehst

- Zustand → Live: jeder Werkzeug-Aufruf als Anfrage des Programms, von außen unter „Über das Internet“.
- Ich → Dienste per MCP: die letzten Vorschläge mit ihrem Stand.

#### Im Code

- `app/panel/mcpserver.py` `mcp_post`: der Endpunkt: Origin, Schlüssel, Limit, Methode ([Schritt 1](#kn-mcpc-s1))
- `app/panel/mcpserver.py` `origin_ok`: keine fremde Webseite ([Schritt 2](#kn-mcpc-s2))
- `app/panel/mcpserver.py` `check_conn`: Schlüssel, Heimnetz, Notaus, Schalter ([Schritt 3](#kn-mcpc-s3))
- `app/panel/mcpserver.py` `is_local`: wirklich aus dem Heimnetz ([Schritt 4](#kn-mcpc-s4))
- `app/panel/mcpserver.py` `find`: Verbindung zum Hash des Schlüssels ([Schritt 3](#kn-mcpc-s3))
- `app/panel/mcpserver.py` `tool_ok`: darf das Profil dieses Werkzeug jetzt ([Schritt 7](#kn-mcpc-s7))
- `app/panel/mcpserver.py` `call`: gleichzeitige Aufrufe, Journal-Zeile ([Schritt 8](#kn-mcpc-s8))
- `app/panel/mcpserver.py` `run`: verteilt auf Sprache, Lesen, Fragen, Handeln ([Schritt 9](#kn-mcpc-s9), [Schritt 10](#kn-mcpc-s10))
- `app/panel/mcpserver.py` `ask`: ein Zug nur mit Lese-Werkzeugen ([Schritt 10](#kn-mcpc-s10))
- `app/panel/mcpserver.py` `propose`: Vorschlag statt Handlung ([Schritt 11](#kn-mcpc-s11))
- `app/panel/mcpserver.py` `decide`: das Ja des Profils, dann ausführen ([Schritt 11](#kn-mcpc-s11))
- `app/panel/mcpserver.py` `carry_out`: führt nur bestätigte Aktionen aus ([Schritt 11](#kn-mcpc-s11))

Selbsttests: `test_mcpserver`, `test_notaus`

### Middleware

Die Middleware ist die Schicht in panel.py, durch die jede HTTP-Anfrage geht, bevor ein Endpunkt sie liest: Notaus, fremde Seiten (CSRF), Größe der Anfrage und Update-Sperre. Auf dem Rückweg setzt sie Schutz-Kopfzeilen, schreibt Änderungen ins Admin-Protokoll und erneuert Anmeldungen.

**Warum:** FastAPI liest Datei-, Formular- und JSON-Teile, bevor die Anmeldung eines Endpunkts geprüft wird. Ohne diese Schicht könnte jeder mit einem riesigen Upload Speicher oder Platte füllen und bekäme sein „nicht angemeldet“ erst danach. Ebenso muss der Notaus greifen, bevor irgendein Endpunkt etwas tut, und eine fremde Webseite darf die Cookies des Browsers nie für Änderungen benutzen.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Anfrage kommt an"])
  s2["2. Zeit messen"]
  s3{{"3. Mein Notaus für diesen Schlüssel?"}}
  s4{{"4. Notaus an?"}}
  s5{{"5. Von außen?"}}
  s6{{"6. Alles still?"}}
  s7{{"7. Fremde Seite?"}}
  s8{{"8. Großer Upload ohne Anmeldung?"}}
  s9{{"9. Zu groß?"}}
  s10{{"10. Update läuft?"}}
  s11["11. Endpunkt"]
  s12(["12. Antwort mit Schutz"])
  s1 --> s2
  s2 --> s3
  s3 -->|nein| s4
  s4 -->|ja| s5
  s5 -->|nein| s6
  s6 -->|nein| s7
  s7 -->|nein| s8
  s8 -->|nein| s9
  s9 -->|nein| s10
  s10 -->|nein| s11
  s11 --> s12
  s3x(["Gesperrt (503)"])
  s3 -->|ja| s3x
  s4 -.->|nein| s7
  s5x(["Von außen gesperrt (503)"])
  s5 -->|ja| s5x
  s6x(["Alles angehalten (503)"])
  s6 -->|ja| s6x
  s7x(["Abgewiesen (403), Eintrag im Admin-Protokoll"])
  s7 -->|ja| s7x
  s8x(["Anmeldung nötig (401)"])
  s8 -->|ja| s8x
  s9x(["Zu groß (413)"])
  s9 -->|ja| s9x
  s10x(["Gesperrt bis zum Ende (423)"])
  s10 -->|ja| s10x
```

1. <a id="kn-middleware-s1"></a>**Anfrage kommt an**: Jede HTTP-Anfrage an das Panel geht durch diese Schicht, von außen nach innen in der Reihenfolge, in der Starlette die Middleware stapelt (die zuletzt angemeldete liegt außen). Telegram, „Spark fragen“ über MCP und die Lautsprecher bauen ihre Frage im Panel selbst und rufen chat.chat direkt auf; deren äußere Anfrage ist vorher schon hier durchgegangen.
2. <a id="kn-middleware-s2"></a>**Zeit messen**: slow_reads misst die ganze Anfrage. Ein Lesen unter /api/, das länger als 1.5 s braucht, wird eine Zeile im Journal, je Route höchstens alle 60 s; nur das Muster der Route und die Zeit, nie die Abfrage oder Namen.
3. <a id="kn-middleware-s3"></a>**Mein Notaus für diesen Schlüssel?**: Trägt die Anfrage einen Geräteschlüssel und hat dessen Profil seinen eigenen Notaus an, bekommt sie nichts außer dem Stand des Notaus. Sonst merkt sich das Panel, für welches Profil diese Anfrage handelt, damit die letzte Abwehr tiefer unten weiß, wessen Aktion es wäre.
4. <a id="kn-middleware-s4"></a>**Notaus an?**: Ist der Notaus aus, geht die Anfrage gleich weiter zur Herkunftsprüfung. Die Seite selbst und ihre Dateien kommen immer durch, damit man den Notaus sehen und aufheben kann.
5. <a id="kn-middleware-s5"></a>**Von außen?**: Im Heimnetz ist nur, wer eine private Adresse hat und nicht über einen Proxy kommt, oder über einen eingetragenen Proxy, der eine private Adresse meldet. Ab Notaus-Stufe 1 bekommt alles von außen nur noch die Seite und den Notaus-Stand.
6. <a id="kn-middleware-s6"></a>**Alles still?**: In Stufe 3 gehen auch im Heimnetz nur noch Anmelden, der Admin-Modus, das Aufheben des Notaus und das Lesen von Zustand, Logs und Live durch. In den Stufen darunter läuft im Heimnetz alles weiter; Aktionen hält das Panel dann tiefer unten an.
7. <a id="kn-middleware-s7"></a>**Fremde Seite?**: Eine ändernde Anfrage (POST, PUT, PATCH, DELETE), die ein Anmelde-Cookie mitbringt, muss von der eigenen Seite kommen: der Browser sagt es mit Sec-Fetch-Site, sonst wird Origin mit dem Host verglichen. Ein anderer Port auf demselben Rechner gilt als fremd. Ohne beide Kopfzeilen ist es kein Browser (Skripte) und geht durch.
8. <a id="kn-middleware-s8"></a>**Großer Upload ohne Anmeldung?**: Die Pfade für große Uploads (Sicherungen, Stimmen, Ton, Dokumente, Bilder, MCP) nehmen nur an, wer überhaupt angemeldet sein könnte: Admin-Cookie, Profil, Admin-Modus oder eine Authorization-Zeile. Die echte Prüfung kommt danach im Endpunkt; hier geht es nur darum, dass kein Byte eines fremden Uploads gelesen wird.
9. <a id="kn-middleware-s9"></a>**Zu groß?**: Jeder Pfad hat seine Grenze, sonst gilt eine kleine Standardgrenze von zwei MB. Eine zu große Content-Length wird sofort abgelehnt; beim Lesen zählt BodyLimit zusätzlich mit und bricht ab, sobald mehr kommt als erlaubt.
10. <a id="kn-middleware-s10"></a>**Update läuft?**: Während ein Update läuft, werden Änderungen unter /api/ angehalten. Der Assistent, die Geräte und das Anmelden bleiben offen (update.UNLOCKED).
11. <a id="kn-middleware-s11"></a>**Endpunkt**: Erst jetzt liest der Endpunkt die Anfrage und prüft selbst Anmeldung, Profil und Rate-Limit (die nächste Station, „Anmeldung, Profil“).
12. <a id="kn-middleware-s12"></a>**Antwort mit Schutz**: Jede Antwort bekommt die Schutz-Kopfzeilen (keine fremden Rahmen, strenge Content-Security-Policy, auf https auch HSTS), unter /api/ „no-store“. Eine Änderung landet mit wer, Pfad und Status im Admin-Protokoll, außer gewöhnlicher Nutzung aus guard.QUIET_WHY. Benutzte Anmeldungen werden erneuert, auf https immer mit Secure.

**Beispiele:** Einstellung im Browser zu Hause: Durch: der Endpunkt prüft die Anmeldung, die Änderung steht im Admin-Protokoll. · Fremde Webseite schickt ein Formular: Abgewiesen mit 403, bevor ein Endpunkt etwas tut. · Notaus Stufe 1, App unterwegs: Gesperrt mit 503 und der Stufe; die App zeigt den Notaus. · Großer Upload ohne Anmeldung: Abgewiesen mit 401, kein Byte gelesen.

#### Regeln

Gilt bei: [Schritt 4](#kn-middleware-s4), [Schritt 5](#kn-middleware-s5), [Schritt 6](#kn-middleware-s6)

| Notaus-Stufe | Von außen | Im Heimnetz |
|---|---|---|
| aus | alles | alles |
| 1 und 2 | nur die Seite und der Notaus-Stand | alles; Aktionen hält das Panel tiefer unten an |
| 3 | nur die Seite und der Notaus-Stand | Anmelden, Admin-Modus, Aufheben, Zustand und Logs lesen |

#### Warum diese Reihenfolge

- Der Notaus liegt außen: auch eine fremde Seite oder ein zu großer Upload von außen bekommt bei Notaus nur die Stufe zu hören.
- Die Herkunft kommt vor der Größe: eine fremde Seite wird abgewiesen, ohne dass ihr Inhalt gelesen wird.
- Was der Notaus tief unten anhält (NotausAktiv), wird als klarer Satz mit 503 beantwortet, nie als Serverfehler.

#### Zahlen (aus dem Code)

- **1** Notaus-Stufe, ab der nichts von außen durchkommt ([Schritt 5](#kn-middleware-s5), [Schritt 6](#kn-middleware-s6))
- **3** Notaus-Stufe, in der auch zu Hause fast alles steht ([Schritt 5](#kn-middleware-s5), [Schritt 6](#kn-middleware-s6))
- **1.5 s** ab hier gilt ein Lesen als langsam ([Schritt 2](#kn-middleware-s2))
- **60 s** höchstens eine Zeile je Route ([Schritt 2](#kn-middleware-s2))

#### Einstellen

- Einstellungen → Sicherheit → Reverse Proxy: nur von diesen Adressen zählt X-Forwarded-For. Das entscheidet, wer als „im Heimnetz“ gilt und welche Adresse gesperrt wird.
- Einstellungen → Sicherheit → Notaus von selbst: viele falsche Anmeldungen, MCP-Anfragen oder gesperrte Verbindungen von außen lösen Notaus Stufe 1 aus (Standard aus).

#### Was du siehst

- Zustand → Live: unter Ereignisse steht „fremde Seite abgewiesen“; der Notaus erscheint als Banner.
- Logs → Admin-Protokoll: jede Änderung mit wer, Pfad und Status, auch abgewiesene fremde Seiten.
- Zustand → Logs: langsame Lesezugriffe als Zeile „seite: slow GET …“.

#### Im Code

- `app/panel/panel.py` `slow_reads`: misst jede Anfrage ([Schritt 2](#kn-middleware-s2))
- `app/panel/panel.py` `emergency`: Notaus vor jedem Endpunkt ([Schritt 3](#kn-middleware-s3), [Schritt 4](#kn-middleware-s4))
- `app/panel/notaus.py` `mine_gate`: Mein Notaus für Geräteschlüssel ([Schritt 3](#kn-middleware-s3))
- `app/panel/notaus.py` `gate`: was bei welcher Stufe durchkommt ([Schritt 4](#kn-middleware-s4))
- `app/panel/notaus.py` `at_home`: im Heimnetz oder von außen ([Schritt 5](#kn-middleware-s5))
- `app/panel/panel.py` `sessions`: fremde Seiten, Protokoll, Cookies erneuern ([Schritt 7](#kn-middleware-s7), [Schritt 12](#kn-middleware-s12))
- `app/panel/guard.py` `same_origin`: die Herkunftsregel ([Schritt 7](#kn-middleware-s7))
- `app/panel/panel.py` `_may_upload`: große Uploads nur mit Anmeldung ([Schritt 8](#kn-middleware-s8))
- `app/common.py` `BodyLimit`: Größengrenze vor dem Lesen ([Schritt 9](#kn-middleware-s9))
- `app/panel/update.py` `update_lock`: Änderungen während eines Updates ([Schritt 10](#kn-middleware-s10))
- `app/panel/panel.py` `protect`: Schutz-Kopfzeilen ([Schritt 12](#kn-middleware-s12))

Selbsttests: `test_hardening`, `test_panel`, `test_notaus`, `test_seiten_laden`

### Anmeldung, Profil

Hier entscheidet das Panel, wer eine Anfrage stellt und was diese Person darf: Anmeldung mit Passwort oder PIN (mit Sperre nach Fehlversuchen), Cookie oder Geräteschlüssel, Rate-Limit und die Freigaben je Funktion. Das Profil kommt nur aus Cookie, Schlüssel oder dem Panel selbst, nie aus dem Text einer Anfrage oder vom Modell.

**Warum:** Der Spark ist über das Heimnetz und oft über einen Proxy aus dem Internet erreichbar. Ohne Sperre ließe sich eine PIN durchprobieren, ohne Rate-Limit könnte eine Seite oder ein Skript die GPU für sich nehmen, und ohne feste Bindung an ein Profil könnte eine Anfrage sich als jemand anderes ausgeben.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Anmelden oder fragen"])
  s2{{"2. Gesperrt?"}}
  s3{{"3. Passwort oder PIN richtig?"}}
  s4{{"4. Zweiter Schritt?"}}
  s5["5. Cookie setzen"]
  s6["6. Profil bestimmen"]
  s7{{"7. Schlüssel für diesen Weg frei?"}}
  s8{{"8. Ohne Profil und Gastzugang aus?"}}
  s9{{"9. Zu viele Anfragen?"}}
  s10{{"10. Gast, alle Plätze belegt?"}}
  s11["11. Freigabe je Funktion"]
  s12(["12. Weiter zur Vorbereitung"])
  s1 --> s2
  s2 -->|nein| s3
  s3 -->|ja| s4
  s4 -->|nein| s5
  s5 --> s6
  s6 --> s7
  s7 -->|ja| s8
  s8 -->|nein| s9
  s9 -->|nein| s10
  s10 -->|nein| s11
  s11 --> s12
  s2x(["Zu viele Fehlversuche (429)"])
  s2 -->|ja| s2x
  s3x(["Abgewiesen (401)"])
  s3 -->|nein| s3x
  s4x(["Code oder Passkey, dann weiter"])
  s4 -->|ja| s4x
  s7x(["Kein Profil (401 oder 503)"])
  s7 -->|nein| s7x
  s8x(["Anmeldung nötig (401)"])
  s8 -->|ja| s8x
  s9x(["Bitte kurz warten (429)"])
  s9 -->|ja| s9x
  s10x(["Assistent beschäftigt (429)"])
  s10 -->|ja| s10x
```

1. <a id="kn-zugang-s1"></a>**Anmelden oder fragen**: Beim Anmelden bekommt der Browser ein Cookie; Apps, Uhr und Lautsprecher haben stattdessen einen Geräteschlüssel. Die Schritte 2 bis 5 laufen einmal beim Anmelden, die Schritte ab 6 bei jeder Anfrage.
2. <a id="kn-zugang-s2"></a>**Gesperrt?**: Gesperrt wird je Adresse und je Name (oder Admin-Passwort). Die Sperre eines Namens gilt nicht für einen Browser, der sich mit diesem Namen schon angemeldet hat (Cookie speech_known, gespeichert wird nur sein Hash). So kann ein Fremder durch Raten den Besitzer nicht aussperren.
3. <a id="kn-zugang-s3"></a>**Passwort oder PIN richtig?**: Geprüft wird in einem eigenen Thread. Ein unbekannter Name kostet dieselbe Arbeit wie eine falsche PIN, die Antwort ist dieselbe. Ein Fehlversuch wartet eine Sekunde, zählt für die Sperre und, wenn er von außen kommt, für „Notaus von selbst“.
4. <a id="kn-zugang-s4"></a>**Zweiter Schritt?**: Hat das Profil (oder der Admin) den zweiten Schritt an und ist der Browser nicht als vertraut eingetragen, kommt als Nächstes der Code aus der App oder ein Passkey. Ein falscher Code zählt wie eine falsche PIN.
5. <a id="kn-zugang-s5"></a>**Cookie setzen**: Der Zähler der Adresse wird gelöscht; Fehlversuche Fremder für den Namen zählen weiter. Das Profil-Cookie ist signiert und steht in der Liste der angemeldeten Browser; es gilt höchstens 90 Tage ohne Nutzung und wird erneuert, solange es benutzt wird. Das Admin-Cookie ist mit Passwort, einem eigenen Schlüssel dieses Spark und dem zweiten Schritt signiert.
6. <a id="kn-zugang-s6"></a>**Profil bestimmen**: Zuerst, was nur das Panel selbst setzt (Telegram, „Spark fragen“ über MCP), dann der Geräteschlüssel (nur sein Hash ist gespeichert), dann das Cookie: Signatur, Alter, Sitzung noch in der Liste und nicht abgemeldet.
7. <a id="kn-zugang-s7"></a>**Schlüssel für diesen Weg frei?**: Ein Schlüssel mit Bereich (App, Uhr, Raum, Home Assistant, Schreibhilfe, Begleiter) reicht nur für seine eigenen Pfade und nur, solange Admin und Profil die Funktion anhaben. Ist sie gerade aus oder hat das Profil seinen eigenen Notaus an, antwortet das Panel mit 503 statt 401, damit die App ihre Kopplung behält.
8. <a id="kn-zugang-s8"></a>**Ohne Profil und Gastzugang aus?**: Ohne Profil kommt nur durch, wer der Admin ist (Cookie oder HTTP Basic, dessen Fehlversuche wie auf der Anmeldeseite zählen), oder wenn der Admin den Assistenten ohne Passwort freigegeben hat. Gäste bekommen dann nur Frage und Antwort.
9. <a id="kn-zugang-s9"></a>**Zu viele Anfragen?**: Je Profil, sonst je Adresse, zählt das Panel die Anfragen der letzten Minute: im Chat 120 für ein Profil oder den Admin, 30 für einen Gast.
10. <a id="kn-zugang-s10"></a>**Gast, alle Plätze belegt?**: Gäste teilen sich 4 gleichzeitige Plätze im Chat. Ein Platz, den niemand freigibt, gilt nach 10 Minuten wieder als frei.
11. <a id="kn-zugang-s11"></a>**Freigabe je Funktion**: Für jede Funktion fragt das Panel in fester Reihenfolge: Schalter des Admins (und der Funktion, auf der sie aufbaut), Gast (bekommt nie eine), vom Admin für das Profil gesperrt, eigener Wunsch des Profils, zweiter Schritt nötig. Gelesen wird bei jeder Anfrage neu, eine Änderung gilt also sofort.
12. <a id="kn-zugang-s12"></a>**Weiter zur Vorbereitung**: Die Anfrage geht mit ihrem Profil (oder als Gast) an chat_turn.prepare. Die Sprache bekommt Vorrang vor Hintergrundarbeit, und die anderen offenen Seiten des Profils sehen „antwortet gerade“.

**Beispiele:** Anmeldung mit PIN: Angemeldet: der Browser hat ein signiertes Cookie. · Fremder rät eine PIN: Abgewiesen; nach 5 Fehlversuchen ist die Adresse gesperrt. · Frage aus der iPhone-App: Durch: Profil aus dem Geräteschlüssel, Freigaben je Funktion. · Gast, Gastzugang aus: Abgewiesen mit 401: ohne Profil kein Assistent.

#### Regeln

Gilt bei: [Schritt 6](#kn-zugang-s6), [Schritt 7](#kn-zugang-s7)

| Weg hinein | Wie geprüft | Was er erreicht |
|---|---|---|
| Browser mit Profil | signiertes Cookie, Sitzung in der Liste | alles des Profils |
| Admin | Passwort-Cookie oder HTTP Basic | Admin-Seiten; HTTP Basic nur ohne zweiten Schritt |
| Geräteschlüssel ohne Bereich | Hash des Schlüssels | Assistent des Profils, keine Verbindungen oder Sicherheit ändern |
| Geräteschlüssel mit Bereich | Hash, Pfad, Schalter | nur die Pfade seines Bereichs |
| Gast | nur mit Assistent ohne Passwort | Frage und Antwort, kein Werkzeug |

#### Hinter einem Proxy

- X-Forwarded-For zählt nur von einem eingetragenen Proxy (oder einem auf dem Spark selbst, solange keiner eingetragen ist). Sonst könnte jedes Gerät behaupten, eine andere Adresse zu sein, und die Sperre umgehen.

#### Abmelden

- Ein abgemeldetes Cookie wird auch auf dem Server ungültig, eine Kopie davon geht nicht mehr. Beim Admin gilt das für jede Kopie derselben Anmeldung.

#### Zahlen (aus dem Code)

- **5** Fehlversuche je Adresse in 15 Minuten bis zur Sperre ([Schritt 2](#kn-zugang-s2), [Schritt 3](#kn-zugang-s3))
- **10** Fehlversuche je Name in 15 Minuten bis zur Sperre ([Schritt 2](#kn-zugang-s2), [Schritt 3](#kn-zugang-s3))
- **60 s** erste Sperre, jede weitere doppelt so lang bis 60 Minuten ([Schritt 2](#kn-zugang-s2))
- **30** Fehlversuche je Name in 24 Stunden höchstens ([Schritt 2](#kn-zugang-s2), [Schritt 3](#kn-zugang-s3))
- **120** Chat-Anfragen je Minute für ein Profil ([Schritt 9](#kn-zugang-s9))
- **4** gleichzeitige Plätze für Gäste ([Schritt 10](#kn-zugang-s10))
- **90** Tage höchstens für eine Anmeldung im Browser ([Schritt 5](#kn-zugang-s5))

#### Einstellen

- Einstellungen → Sicherheit → Assistent ohne Passwort: Gäste dürfen fragen (Standard aus).
- Einstellungen → Sicherheit → Anmeldung im Browser: wie viele Tage ohne Nutzung ein Profil angemeldet bleibt.
- Funktionen → Wer darf was: eine Funktion für einzelne Profile sperren.
- Ich → Sicherheit: der zweite Schritt eines Profils.

#### Was du siehst

- Zustand → Live: unter Eingang angenommene Zugriffe aus dem Internet und abgewiesene Anmeldungen.
- Logs → Admin-Protokoll: Anmeldungen, Fehlversuche und Sperren.
- Ich → Sicherheit: die letzten Anmeldungen des eigenen Profils.

#### Im Code

- `app/panel/guard.py` `check`: Sperre vor dem Prüfen ([Schritt 2](#kn-zugang-s2))
- `app/panel/guard.py` `failed`: Fehlversuch zählen, sperren ([Schritt 3](#kn-zugang-s3))
- `app/panel/guard.py` `succeeded`: Zähler löschen, Browser merken ([Schritt 5](#kn-zugang-s5))
- `app/panel/account.py` `profile_login`: Anmeldung eines Profils ([Schritt 3](#kn-zugang-s3))
- `app/panel/account.py` `second_step`: Code oder Passkey ([Schritt 4](#kn-zugang-s4))
- `app/panel/core.py` `is_main_admin`: Admin per Cookie oder HTTP Basic ([Schritt 6](#kn-zugang-s6))
- `app/panel/profiles.py` `current`: das Profil hinter einer Anfrage ([Schritt 6](#kn-zugang-s6))
- `app/panel/profiles.py` `_cookie_user`: Cookie prüfen ([Schritt 6](#kn-zugang-s6))
- `app/panel/core.py` `assistant`: Profil, Gastzugang oder Admin ([Schritt 8](#kn-zugang-s8))
- `app/panel/guard.py` `limit`: Rate-Limit je Minute ([Schritt 9](#kn-zugang-s9))
- `app/panel/guard.py` `Slot`: Plätze für Gäste ([Schritt 10](#kn-zugang-s10))
- `app/panel/features.py` `reason`: warum eine Funktion nicht geht ([Schritt 11](#kn-zugang-s11))

Selbsttests: `test_panel`, `test_features`, `test_rechte_sofort`, `test_passkey`, `test_coadmin`

### Anfrage vorbereiten

chat_turn.prepare macht aus einer Chat-Anfrage einen fertigen Gesprächszug, bevor das Sprachmodell gefragt wird: wer spricht und was diese Person darf, der Systemprompt, Antworten auf Rückfragen und Vorschläge, die Sperren nach fremdem Text und die Liste der angebotenen Werkzeuge.

**Warum:** Das Modell soll nur sehen, was es in diesem Zug wirklich darf. Alles, was entscheidet (Rechte, Sperren, ein „Ja“ zu einem Vorschlag, die Auswahl bei einer Rückfrage), macht das Panel hier mit festen Regeln; das Modell sagt danach nur das Ergebnis.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Nachrichten lesen"])
  s2["2. Verlauf kürzen, Sperre übernehmen"]
  s3{{"3. Gast oder fremde Stimme?"}}
  s4["4. Weiche liest die Frage"]
  s5["5. Systemprompt bauen"]
  s6{{"6. Fester Satz?"}}
  s7{{"7. Antwort auf eine Rückfrage?"}}
  s8{{"8. Notaus oder Mein Notaus?"}}
  s9["9. Ja zu einem Vorschlag"]
  s10["10. Werkzeuge nach Rechten"]
  s11{{"11. Etwas nimmt Werkzeuge weg?"}}
  s12["12. Weiche grenzt ein"]
  s13(["13. Gesprächszug fertig"])
  s1 --> s2
  s2 --> s3
  s3 -->|nein| s4
  s4 --> s5
  s5 --> s6
  s6 -->|nein| s7
  s7 -->|nein| s8
  s8 -->|nein| s9
  s9 --> s10
  s10 --> s11
  s11 -->|nein| s12
  s12 --> s13
  s1x(["Keine Nachricht (400)"])
  s1 -->|leer| s1x
  s3x(["nur Frage und Antwort"])
  s3 -->|ja| s3x
  s6x(["Panel führt aus, kein Werkzeug"])
  s6 -->|ja| s6x
  s7x(["Panel führt die Wahl aus"])
  s7 -->|ja| s7x
  s8x(["nur lesen, kein Ja"])
  s8 -->|ja| s8x
  s11x(["weniger oder keine Werkzeuge"])
  s11 -->|ja| s11x
```

1. <a id="kn-vorbereiten-s1"></a>**Nachrichten lesen**: Übernommen werden nur Textnachrichten von Nutzer und Assistent, jede auf 20000 Zeichen gekürzt. Eine Antwort, die der Browser als aus Mail oder fremdem Text gemacht markiert hat, behält diese Marke.
2. <a id="kn-vorbereiten-s2"></a>**Verlauf kürzen, Sperre übernehmen**: Der Verlauf wird auf sein Budget gekürzt. Steht eine Antwort aus fremdem Text unter den letzten drei Nachrichten, beginnt dieser Zug gesperrt; ältere werden gar nicht mehr mitgeschickt.
3. <a id="kn-vorbereiten-s3"></a>**Gast oder fremde Stimme?**: Ohne Profil, oder am eigenen Lautsprecher, wenn die Spracherkennung nicht klar die Stimme des Profils gehört hat, gibt es nur Frage und Antwort: kein Werkzeug, kein Gedächtnis, kein Verlauf. Wessen Stimme es war, setzt nur das Panel selbst, nie die Anfrage.
4. <a id="kn-vorbereiten-s4"></a>**Weiche liest die Frage**: Feste Regeln ordnen die eigene letzte Nachricht einer Gruppe zu. Eine neue eigene Bitte, die nicht auf die Antwort aus fremdem Text zurückzeigt, lässt diese Antwort und ihre Sperre weg. Erkennt keine Regel die Frage, kann das Modell parallel einmal aus einer festen Liste wählen (wenn der Admin das anhat). Eine Folgefrage wie „Und morgen?“ übernimmt die Gruppe der eigenen Frage davor (intent.follow_up); Hinweiswörter geben ihre Gruppen dazu, auch neben der Wahl des Modells.
5. <a id="kn-vorbereiten-s5"></a>**Systemprompt bauen**: Der Systemprompt des Admins, dazu Länge und Stil des Profils und ein Hinweis je Kanal (Uhr, Siri, Lautsprecher, Telegram, App, Browser). Mit „Schneller Antwortbeginn“ geht, was nur für diesen Zug gilt, mit der Frage statt in den Systemprompt, damit der Server ihn aus dem Cache liest.
6. <a id="kn-vorbereiten-s6"></a>**Fester Satz?**: Sätze wie „Spark Notaus“, „Problem melden: …“ oder „Das war falsch“ führt das Panel selbst aus, nur aus den eigenen Worten des Profils und nie über MCP. Das Modell sagt nur das Ergebnis und bekommt in diesem Zug kein Werkzeug.
7. <a id="kn-vorbereiten-s7"></a>**Antwort auf eine Rückfrage?**: Hat das Panel gefragt, welches Gerät gemeint ist, gilt als Antwort ein Knopf, eine Zahl oder der Name, nur im selben Gespräch, vom eigenen Profil und innerhalb von 2 Minuten. „Keins davon“ bringt die ganze Liste, „Nein, den anderen“ korrigiert die letzte Wahl. Das Panel führt die Wahl aus und bietet an, sie sich zu merken; ein „Ja“ dazu zählt 15 Minuten.
8. <a id="kn-vorbereiten-s8"></a>**Notaus oder Mein Notaus?**: Ab Notaus-Stufe 2 oder mit dem eigenen Notaus des Profils werden alle wartenden Vorschläge verworfen; kein „Ja“ führt etwas aus. Lesen und Antworten gehen weiter.
9. <a id="kn-vorbereiten-s9"></a>**Ja zu einem Vorschlag**: Wartet ein Vorschlag aus diesem Gespräch (ein Termin, eine Mail-Änderung, ein Listeneintrag, eine Korrektur), entscheidet das Panel über das „Ja“. Ein Ja bestätigt genau eine Sache; jede Antwort erledigt alle anderen wartenden Vorschläge dieses Gesprächs.
10. <a id="kn-vorbereiten-s10"></a>**Werkzeuge nach Rechten**: Jede Werkzeuggruppe kommt nur mit Schalter des Admins, Freigabe für das Profil und den eigenen Daten dazu: Suche, Gedächtnis, Verlauf, Dokumente, Smart Home, Erinnerungen, Kalender, Mail. Telegram, die iPhone-App und CarPlay können das nur enger machen, nie weiter. Eine fremde erkannte Stimme an diesem Gerät bekommt nichts Persönliches.
11. <a id="kn-vorbereiten-s11"></a>**Etwas nimmt Werkzeuge weg?**: Der Notaus nimmt Werkzeuge ins Internet oder ändernde weg, „Spark fragen“ über MCP behält nur die Werkzeuge der Verbindung, ein Bild oder ein fester Satz lässt keines übrig. Für einen Gast wird die Liste noch einmal geleert, egal was sie gefüllt hat.
12. <a id="kn-vorbereiten-s12"></a>**Weiche grenzt ein**: Mit „Gezielte Werkzeugwahl“ bleibt nur die Gruppe der Frage übrig. Danach entscheidet das Panel, ob erst lokal gesucht wird, ob es ein eindeutiges Abrufen selbst macht und welches Werkzeug die erste Runde rufen muss.
13. <a id="kn-vorbereiten-s13"></a>**Gesprächszug fertig**: Der Systemprompt steht vorn, dazu die Werkzeuge und die Sperrregel. Der Notaus wird bei jedem Werkzeugaufruf neu gelesen: wird er während einer Antwort ausgelöst, hält er den nächsten Aufruf an.

**Beispiele:** Gast fragt nach dem Wetter: Antwort ohne Werkzeug: Gäste bekommen nur Frage und Antwort. · „Das zweite“ nach einer Rückfrage: Das Panel schaltet das gewählte Gerät; das Modell sagt nur das Ergebnis. · Notaus Stufe 2, Frage nach Terminen: Nur lesende Werkzeuge; Termine eintragen wird nicht angeboten.

#### Regeln

Gilt bei: [Schritt 10](#kn-vorbereiten-s10), [Schritt 11](#kn-vorbereiten-s11)

| Wer spricht | Werkzeuge | Persönliches | Ja zu Vorschlägen |
|---|---|---|---|
| Profil, eigener Login oder Schlüssel | nach Freigaben | ✓ | ✓ |
| andere erkannte Stimme an diesem Gerät | allgemeine | ✕ | ✕ |
| Spark fragen über MCP | nur die der Verbindung | nur lesen, kein Gedächtnis, keine Mail | ✕ |
| Gast oder unbekannte Stimme am Lautsprecher | ✕ | ✕ | ✕ |

#### Zahlen (aus dem Code)

- **20000** Zeichen höchstens je Nachricht ([Schritt 1](#kn-vorbereiten-s1))
- **2** Minuten gilt eine Auswahl bei einer Rückfrage ([Schritt 7](#kn-vorbereiten-s7))
- **15** Minuten wartet „Soll ich mir das merken?“ ([Schritt 7](#kn-vorbereiten-s7))
- **4** Knöpfe höchstens bei einer Rückfrage ([Schritt 7](#kn-vorbereiten-s7))
- **2** Notaus-Stufe ohne Aktionen ([Schritt 8](#kn-vorbereiten-s8))

#### Einstellen

- Funktionen → Wer darf was: was ein einzelnes Profil nicht bekommt.
- Funktionen → Rückfrage statt Raten: das Panel fragt nach, statt zu raten (Standard aus).
- Funktionen → Weiche: die festen Regeln, die die Werkzeuge eingrenzen.

#### Was du siehst

- Logs → Anfragen: je Frage Gruppe, Werkzeuge „x von y“, Pflichtwerkzeug und Sperre, ohne Inhalt.
- Zustand → Logs: Zeilen wie „weiche: Absicht …“, „chat: web search …“ oder „notaus: … Werkzeuge nicht angeboten“.

#### Im Code

- `app/panel/chat_turn.py` `prepare`: der ganze Ablauf ([Schritt 1](#kn-vorbereiten-s1), [Schritt 13](#kn-vorbereiten-s13))
- `app/panel/chat_turn.py` `shared_stranger`: fremde Stimme am Lautsprecher ([Schritt 3](#kn-vorbereiten-s3))
- `app/panel/chat.py` `trim_history`: Verlauf kürzen ([Schritt 2](#kn-vorbereiten-s2))
- `app/panel/chat.py` `left_out`: Antworten aus fremdem Text weglassen ([Schritt 2](#kn-vorbereiten-s2), [Schritt 4](#kn-vorbereiten-s4))
- `app/panel/intent.py` `classify_cfg`: feste Regeln der Weiche ([Schritt 4](#kn-vorbereiten-s4))
- `app/panel/klaeren.py` `answer`: Antwort auf eine Rückfrage ([Schritt 7](#kn-vorbereiten-s7))
- `app/panel/features.py` `allowed`: Freigabe je Funktion ([Schritt 10](#kn-vorbereiten-s10))
- `app/panel/notaus.py` `locked_tools`: was der Notaus wegnimmt ([Schritt 11](#kn-vorbereiten-s11))
- `app/panel/intent.py` `narrow`: Werkzeuge eingrenzen ([Schritt 12](#kn-vorbereiten-s12))
- `app/panel/chat_turn.py` `notaus_note`: Satz für das Modell bei Notaus ([Schritt 8](#kn-vorbereiten-s8), [Schritt 11](#kn-vorbereiten-s11))

Selbsttests: `test_klaeren`, `test_features`, `test_notaus`, `test_hardening`, `test_weiche`

### Weiche

Die Weiche ordnet die eigene letzte Nachricht einer Gruppe zu (Smart Home, Kalender, Wetter, Mail und so weiter, heute 20 Gruppen) und grenzt damit die Werkzeuge ein, die das Sprachmodell in diesem Zug sieht. Sie arbeitet mit festen Wortlisten; das Modell darf höchstens einmal aus einer festen Liste wählen, wenn keine Regel passt, und auch das kann nur eingrenzen.

**Warum:** Wenige passende Werkzeuge machen das Modell schneller und treffsicherer: es liest weniger und greift seltener daneben. Weil die Weiche nur wegnimmt, was die Rechte und Sperren übrig gelassen haben, kann ein falsch zugeordneter Satz nie mehr erlauben, höchstens ein Werkzeug fehlen lassen.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Nur die eigene Nachricht"])
  s2{{"2. Nur Plaudern?"}}
  s3{{"3. Frage zum Spark?"}}
  s4["4. Wörter je Gruppe"]
  s5["5. Vorrang zwischen Gruppen"]
  s6{{"6. Gruppe erkannt?"}}
  s7["7. Hinweiswörter merken"]
  s8{{"8. Folgefrage?"}}
  s9{{"9. Gezielte Werkzeugwahl an?"}}
  s10{{"10. Modell ordnet ein?"}}
  s11["11. Eingrenzen"]
  s12{{"12. Knapp?"}}
  s13["13. Erstes Werkzeug festlegen"]
  s14(["14. Journal und Zählung"])
  s1 --> s2
  s2 -->|nein| s3
  s3 -->|nein| s4
  s4 --> s5
  s5 --> s6
  s6 -->|nein| s7
  s7 --> s8
  s8 -->|nein| s9
  s9 -->|ja| s10
  s10 -->|nein| s11
  s11 --> s12
  s12 -->|nein| s13
  s13 --> s14
  s2 -.->|ja| s14
  s3 -.->|ja| s9
  s6 -.->|ja| s9
  s8x(["Gruppe der Frage davor"])
  s8 -->|ja| s8x
  s9 -.->|nein| s14
  s10x(["Grund „Modell“"])
  s10 -->|ja| s10x
  s12x(["kurze Liste"])
  s12 -->|ja| s12x
```

1. <a id="kn-weiche-s1"></a>**Nur die eigene Nachricht**: Gelesen wird nur die letzte Nachricht der Person selbst, nie eine Antwort davor, fremder Text oder was das Modell geschrieben hat. Dazu kommen die Wörter, die der Admin unter Funktionen → Weiche gespeichert hat.
2. <a id="kn-weiche-s2"></a>**Nur Plaudern?**: Ist der ganze Satz ein Gruß oder Dank, heißt die Gruppe „plaudern“. Die Antwort bekommt dann gar kein Werkzeug.
3. <a id="kn-weiche-s3"></a>**Frage zum Spark?**: „Wie verbinde ich Home Assistant?“ oder „Schalte die Websuche ein“ fragen nach dem Spark selbst, nicht nach einem Gerät oder einer Suche: Gruppe „spark“. Eine Frage zu Wörtern oder Sprachen zählt nie dazu. Wurde auf einer Seite des Panels „Frag Spark“ benutzt, gilt dieselbe Gruppe nach fester Regel über den Ort der Frage.
4. <a id="kn-weiche-s4"></a>**Wörter je Gruppe**: Jede Gruppe hat ihre eingebaute Wortliste (Licht, Termin, Postfach, Schirm …). Ein Schaltwort ohne Gerät („Alles aus“) zählt nur als ganzer Befehl. Die Pflicht-Wörter des Admins und seine eigenen Wörter je Gruppe (höchstens 20, nur ganze Wörter) finden eine Gruppe zusätzlich, ersetzen aber nichts.
5. <a id="kn-weiche-s5"></a>**Vorrang zwischen Gruppen**: Treffen mehrere Gruppen, räumen feste Regeln auf: Wetter, Liste, Nachricht, Dokument und „Dokument erstellen“ gehen vor Smart Home, wenn kein Schaltbefehl dabei ist; Pakete vor Mail; „Habe ich neue Nachrichten?“ ist eine Nachricht, „Was gibt es in den Nachrichten?“ die Websuche; ein Auftrag, der regelmäßig wiederkommt oder etwas beobachtet, ist ein Agent; eine Frage zu Sprache oder Natur ist nie ein Gerät. Zuletzt nehmen die „Nicht bei“-Wörter des Admins Gruppen wieder heraus.
6. <a id="kn-weiche-s6"></a>**Gruppe erkannt?**: Eine Gruppe oder höchstens 2 gelten als klar und grenzen ein. Mehr Gruppen auf einmal sind nicht klar genug: dann bleiben alle Werkzeuge.
7. <a id="kn-weiche-s7"></a>**Hinweiswörter merken**: Erkennt keine Regel eine Gruppe sicher, sucht die Weiche schwächere Hinweiswörter: „gießen“ deutet aufs Wetter, „Freitag“ auf den Kalender. Ein Hinweis grenzt nie ein; er sorgt nur dafür, dass die Werkzeuge seiner Gruppe bleiben, wenn später eingegrenzt wird.
8. <a id="kn-weiche-s8"></a>**Folgefrage?**: Ist die Nachricht kurz (höchstens 80 Zeichen), zeigt zurück („und“, „das“, „es“) und hatte die eigene Frage direkt davor eine klare Gruppe, gilt diese Gruppe wieder. Es zählt nur die eigene Frage, nie die Antwort. Im Journal steht „weiche: Folgefrage“.
9. <a id="kn-weiche-s9"></a>**Gezielte Werkzeugwahl an?**: Nur mit diesem Schalter grenzt die Weiche ein, und nicht bei einem Bild oder einem direkten Smart-Home-Befehl. Ohne ihn bleibt die Gruppe nur für Journal und Statistik; das Modell sieht alle Werkzeuge, die die Rechte erlauben.
10. <a id="kn-weiche-s10"></a>**Modell ordnet ein?**: Hat keine Regel eine Gruppe gefunden und steht „Fragen, die keine Regel erkennt“ auf „Modell“, wählt das Sprachmodell einmal eine Gruppe aus der festen Liste (nur JSON, nur die eigene Nachricht). Die Frage läuft schon ab dem Beginn der Vorbereitung nebenher; gewartet wird höchstens 4 Sekunden, mit „Schneller Antwortbeginn“ nur 300 ms nach der Vorbereitung. Mit der Einordnung mit Wahrscheinlichkeit zählt die Wahl erst ab der Schwelle (Standard 80 %). Die Hinweis-Gruppen bleiben neben der Wahl.
11. <a id="kn-weiche-s11"></a>**Eingrenzen**: Bei einer klaren Gruppe bleiben ihre Werkzeuge, dazu immer 4 feste (sich etwas merken, eigene Dokumente, PC), die Werkzeuge der Hinweise, die zusätzlichen Werkzeuge des Admins für diese Gruppe (höchstens 6) und was die eigenen Worte ausdrücklich nennen („aufs reMarkable“). Alles nur, soweit schon angeboten. Ist von der Gruppe nichts angeboten oder steht die Gruppe auf „nicht eingrenzen“, bleiben alle.
12. <a id="kn-weiche-s12"></a>**Knapp?**: Bleibt die Frage ohne Gruppe, steht die Einstellung auf „Knapp“ und verlangt kein Pflicht-Wort ein Werkzeug, bekommt das Modell nur die kurze Liste: Websuche, Wikipedia, Archiv, frühere Gespräche, die festen Werkzeuge und die Werkzeuge der Hinweis-Gruppen. Es liest weniger und beginnt früher.
13. <a id="kn-weiche-s13"></a>**Erstes Werkzeug festlegen**: Eine einzige klare Gruppe, ein Pflicht-Werkzeug und nur dieses aus der Gruppe angeboten: die erste Runde muss genau dieses rufen („Wie wird das Wetter?“). Ein kurzer, eindeutiger Lesesatz („Wie ist das Wetter heute?“) wird mit „Eindeutiges direkt abrufen“ vom Panel selbst abgerufen, für morgen und übermorgen mit dem Datum, das das Panel ausrechnet.
14. <a id="kn-weiche-s14"></a>**Journal und Zählung**: Jeder Zug schreibt eine Zeile „weiche: Absicht … | Grund … | Hinweis … | Werkzeuge x von y | Pflicht … | gesperrt … | eingrenzen an/aus“; ein Grundwort steht nur da, wenn es noch in der Nachricht steht. Gezählt werden je Tag und Gruppe nur Anzahlen (8 Tage), nie ein Wort der Frage. Dann geht die Liste an die Antwort.

**Beispiele:** „Mach das Licht im Wohnzimmer aus“: Gruppe smarthome (Wort „Licht“): das Modell sieht nur die Smart-Home-Werkzeuge und die festen. · „Und morgen?“ nach einer Wetterfrage: Keine Regel greift, aber die Folgefrage übernimmt „wetter“: nur das Wetter-Werkzeug ist Pflicht. · „Muss ich die Pflanzen gießen?“ mit „Knapp“: Unklar, Hinweis „gießen“ → wetter: kurze Liste plus Wetter-Werkzeug. · „Danke!“: Gruppe plaudern: Antwort ohne Werkzeug.

#### Regeln

Gilt bei: [Schritt 9](#kn-weiche-s9)

| Fragen, die keine Regel erkennt | Was das Modell sieht | Zeit |
|---|---|---|
| Alle Werkzeuge (Standard) | alles, was die Rechte erlauben | keine zusätzliche |
| Modell ordnet ein | die gewählte Gruppe und die Hinweis-Gruppen | eine kurze Modellfrage nebenher |
| Knapp | kurze Liste und Hinweis-Gruppen | keine, beginnt früher |
| Einordnung mit Wahrscheinlichkeit | die Gruppe erst ab der Schwelle | eine kurze Einordnung nebenher |

#### Alltagsquote

- Die Testsätze (132) halten jede gemeldete Fehlzuordnung fest und müssen alle stimmen. Die Alltagssätze (183) wurden nie zum Einstellen benutzt: sie messen, wie viele richtig landen, von einem Hinweis geschützt werden, offen bleiben oder falsch landen. Ein Selbsttest verbietet, dass richtig plus geschützt sinkt oder falsch steigt.

#### Werkzeugnamen

- Überall, wo ein Werkzeug sichtbar wird, steht ein lesbarer Name aus einer Tabelle (79 Werkzeuge), zum Beispiel „Postfach-Überblick“ statt mail_tidy_overview.

#### Zahlen (aus dem Code)

- **20** Gruppen der Weiche ([Schritt 4](#kn-weiche-s4), [Schritt 6](#kn-weiche-s6))
- **2** Gruppen höchstens, die noch eingrenzen ([Schritt 6](#kn-weiche-s6))
- **80** Zeichen höchstens für eine Folgefrage ([Schritt 8](#kn-weiche-s8))
- **4** Sekunden höchstens für die Wahl des Modells ([Schritt 10](#kn-weiche-s10))
- **300 ms** Wartezeit mit „Schneller Antwortbeginn“ ([Schritt 10](#kn-weiche-s10))
- **80 %** Standard-Schwelle der Einordnung ([Schritt 10](#kn-weiche-s10))
- **132** eingebaute Testsätze ([Schritt 4](#kn-weiche-s4), [Schritt 5](#kn-weiche-s5))
- **183** Alltagssätze zum Messen ([Schritt 14](#kn-weiche-s14))
- **20** Versionen für Rückgängig ([Schritt 4](#kn-weiche-s4))

#### Einstellen

- Funktionen → Gezielte Werkzeugwahl: ohne diesen Schalter grenzt die Weiche nichts ein (Standard aus).
- Funktionen → Weiche: eigene Wörter je Gruppe, „Nicht bei“, zusätzliche Werkzeuge, Gruppen ohne Eingrenzen, Pflicht-Wörter, eigene Testsätze und was Fragen bekommen, die keine Regel erkennt. Jede Änderung läuft vorher durch alle Testsätze; ändert sich einer, wird erst nach Bestätigung gespeichert. Rückgängig hält die letzten 20 Fassungen.
- Funktionen → Eindeutiges direkt abrufen: kurze Lesefragen ruft das Panel selbst ab (Standard aus).

#### Was du siehst

- Funktionen → Weiche: „Satz ausprobieren“ zeigt den ganzen Weg eines Satzes ohne Modell; dazu Testsätze, Alltagsquote und Statistik (7 Tage, nur Anzahlen).
- Zustand → Logs: Zeilen „weiche: Absicht …“, „weiche: Folgefrage“, „weiche: Modell-Zuordnung …“ und „weiche: direkt abgerufen“.
- Logs → Anfragen: je Frage Gruppe, Werkzeuge „x von y“ und was aus der Wahl des Modells wurde.

#### Im Code

- `app/panel/intent.py` `classify`: Gruppen nach festen Wörtern und Vorrang ([Schritt 1](#kn-weiche-s1))
- `app/panel/intent.py` `Route`: Gruppe, Grund, Hinweise; wann klar ([Schritt 6](#kn-weiche-s6))
- `app/panel/intent.py` `hints_of`: Hinweiswörter ([Schritt 7](#kn-weiche-s7))
- `app/panel/intent.py` `follow_up`: Folgefrage ([Schritt 8](#kn-weiche-s8))
- `app/panel/intent.py` `ask_model`: Wahl des Modells aus fester Liste ([Schritt 10](#kn-weiche-s10))
- `app/panel/intent.py` `pick_in_time`: auf die Wahl warten oder abbrechen ([Schritt 10](#kn-weiche-s10))
- `app/panel/intent.py` `narrow`: Werkzeuge eingrenzen ([Schritt 11](#kn-weiche-s11))
- `app/panel/intent.py` `lean`: kurze Liste bei „Knapp“ ([Schritt 12](#kn-weiche-s12))
- `app/panel/intent.py` `forced`: Pflicht für die erste Runde ([Schritt 13](#kn-weiche-s13))
- `app/panel/weiche.py` `count`: Statistik ohne Inhalt ([Schritt 14](#kn-weiche-s14))
- `app/panel/weiche.py` `trace`: Satz ausprobieren ([Schritt 14](#kn-weiche-s14))
- `app/panel/intent_alltag.py` `measure`: Alltagsquote ([Schritt 14](#kn-weiche-s14))

Selbsttests: `test_intent`, `test_intent_alltag`, `test_weiche`, `test_werkzeuge`, `test_systemone`

### Antwort bauen

Hier entsteht die Antwort: Das Panel fragt das Sprachmodell in Runden, lässt angebotene Werkzeuge laufen, prüft jeden fertigen Satz mit festen Regeln und schickt Text und Ton als einen Strom ans Gerät. Die Prüfungen entscheidet das Panel, nie das Modell.

**Warum:** Ein Sprachmodell erfindet gern Uhrzeiten, Beträge oder Taten („Licht ist an“), die nie passiert sind. Gesprochen wirkt das wie eine Tatsache. Deshalb sagt das Panel nur Sätze, die zu dem passen, was wirklich gelesen oder getan wurde, und beginnt trotzdem schnell zu sprechen.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Frage kommt an"])
  s2["2. Strom öffnen, Sofort-Satz"]
  s3["3. Was das Panel selbst erledigt"]
  s4["4. Runde vorbereiten"]
  s5["5. Streamen und in Sätze schneiden"]
  s6{{"6. Zahl ohne Beleg?"}}
  s7{{"7. Tat ohne Werkzeug?"}}
  s8["8. Zeigen und sprechen"]
  s9{{"9. Datenfrage ohne Nachsehen?"}}
  s10{{"10. Werkzeug gewünscht?"}}
  s11["11. Werkzeuge ausführen"]
  s12["12. Ehrliche Schlusssätze"]
  s13["13. Nachfragen des Panels"]
  s14(["14. Strom endet"])
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 --> s5
  s5 --> s6
  s6 -->|nein| s7
  s7 -->|nein| s8
  s8 --> s9
  s9 -->|nein| s10
  s10 -->|ja| s11
  s11 --> s12
  s12 --> s13
  s13 --> s14
  s6x(["Satz fällt weg, am Ende ein ehrlicher Satz"])
  s6 -->|ja| s6x
  s7x(["Satz fällt weg, am Ende „hat nicht geklappt“"])
  s7 -->|ja| s7x
  s9 -.->|ja| s4
  s10 -.->|nein| s12
  s11 -.->|nächste Runde| s4
```

1. <a id="kn-antwort-s1"></a>**Frage kommt an**: chat() prüft das Rate-Limit, setzt die Marke „Sprache läuft“ (Hintergrundarbeit wartet) und zeigt den anderen Geräten des Profils „antwortet gerade“. Dann bereitet chat_turn.prepare Rechte, Sperren, Systemprompt und die angebotenen Werkzeuge vor; _answer übernimmt.
2. <a id="kn-antwort-s2"></a>**Strom öffnen, Sofort-Satz**: Zwei Warteschlangen verbinden alles: eine für die Ereignisse ans Gerät, eine für Sätze an die Sprachausgabe. Ist die Sofortige Rückmeldung frei, spielt sofort ein aufgenommener Satz (ohne GPU); bleibt die Antwort danach still, kommt einmal ein Brücken-Satz.
3. <a id="kn-antwort-s3"></a>**Was das Panel selbst erledigt**: Hat die Vorbereitung entschieden, dass das Panel selbst handelt (ein Schaltbefehl, Zustände lesen, „Erst lokal suchen“, ein eindeutiger Lesewunsch), läuft das jetzt. Das Ergebnis geht wie ein Werkzeug-Ergebnis an das Modell, fremder Text eingepackt als Daten.
4. <a id="kn-antwort-s4"></a>**Runde vorbereiten**: Angeboten wird die Liste ohne gesperrte, wegen Fehlern gestoppte oder zu oft genutzte Werkzeuge. Verlangt die Frage ein Werkzeug, muss das Modell eines wählen (tool_choice), mit eigener Temperatur. Die fünfte Runde hat keine Liste mehr: das Modell hört, dass es jetzt antworten soll.
5. <a id="kn-antwort-s5"></a>**Streamen und in Sätze schneiden**: Die Antwort kommt Stück für Stück. Denktext und als Text geschriebene Werkzeugaufrufe werden nie gezeigt oder gesprochen. split_sentences schneidet fertige Sätze ab („z. B.“ und „5. Oktober“ sind kein Satzende); ein langer erster Satz geht schon am Komma los, damit der erste Ton früh kommt.
6. <a id="kn-antwort-s6"></a>**Zahl ohne Beleg?**: Bei Datenfragen vergleicht answercheck jede Uhrzeit, jedes Datum, jeden Spielstand und Betrag im Satz mit allem, was das Modell bekommen hat. Nach einem Kalender-Abruf zählen nur Angaben aus dieser Antwort, nicht aus früheren; ein zitierter Termin-Titel muss im Ergebnis stehen.
7. <a id="kn-antwort-s7"></a>**Tat ohne Werkzeug?**: Behauptet ein Satz eine Tat („ist jetzt an“, „habe eingetragen“), muss in dieser Antwort ein Werkzeug dieser Art geklappt haben (taten.check). Gilt nur, wenn ein änderndes Werkzeug angeboten war.
8. <a id="kn-antwort-s8"></a>**Zeigen und sprechen**: Ein geprüfter Satz geht als Text ans Gerät und in die Warteschlange der Sprachausgabe; Codeblöcke werden nur gezeigt. Ein schon gesagter Satz aus einer früheren Runde wird ausgelassen. Die Sprachausgabe fasst nach dem ersten Satz alles Wartende zu einem Stück zusammen, damit die Stimme ruhig bleibt.
9. <a id="kn-antwort-s9"></a>**Datenfrage ohne Nachsehen?**: Braucht die Frage ein Werkzeug und das Modell antwortet ohne eines, wird die ganze Runde nie gesagt. Das Modell wird einmal neu gefragt, mit dem Hinweis, zuerst das Werkzeug zu nutzen.
10. <a id="kn-antwort-s10"></a>**Werkzeug gewünscht?**: Hat das Modell keinen Werkzeugaufruf geschrieben oder ist die Länge erreicht, ist die Antwort fertig. Bei erreichter Länge wird bis zum letzten Satzende gesprochen, der Rest fällt weg.
11. <a id="kn-antwort-s11"></a>**Werkzeuge ausführen**: Halbe Worte vor dem Aufruf werden zurückgenommen, ein fertiger Satz bleibt. Jeder Aufruf geht über chat_tools.run; das Ergebnis kommt als Werkzeug-Nachricht zurück. Scheitert ein Werkzeug zweimal gleich, wird es für diese Antwort gestoppt.
12. <a id="kn-antwort-s12"></a>**Ehrliche Schlusssätze**: Fiel ein Satz wegen einer Zahl weg, sagt das Panel „Genauere Angaben dazu habe ich nicht.“; fiel eine Tat weg, einen festen Satz aus taten.sentence. Beide Sätze kommen vom Panel, nie vom Modell.
13. <a id="kn-antwort-s13"></a>**Nachfragen des Panels**: Nur wenn nichts Fremdes gelesen wurde: eine gelernte Korrektur zum Merken anbieten oder ein Fakt aus dem Gedächtnis nachfragen (nach festen Regeln). Danach legt das Panel die Antwort aufs reMarkable, wenn gewünscht, und holt bei einer Rückfrage schon vorab. Das Werkzeug-Log des Profils wird geschrieben.
14. <a id="kn-antwort-s14"></a>**Strom endet**: Der Anfrage-Verlauf wird abgeschlossen, Fälle und die Prüfung im Hintergrund laufen erst nach dem Sprechen. Bricht das Gerät ab (Unterbrechen), stoppen Modell und Sprachausgabe sofort.

**Beispiele:** Plaudern ohne Werkzeug: Gesprochen ab dem ersten Satz, keine Prüfung greift. · Termine von morgen: Das Modell ruft den Kalender, die nächste Runde antwortet aus dem Ergebnis. · Erfundene Uhrzeit: Der Satz mit der Uhrzeit wird nie gesagt, dafür ein ehrlicher Satz. · „Licht ist an“, Schalten scheiterte: Statt der Behauptung: „Das hat nicht geklappt: …“.

#### Zahlen (aus dem Code)

- **4** Werkzeugaufrufe pro Runde, mehr laufen nicht ([Schritt 11](#kn-antwort-s11))
- **3** Gedächtnis-Notizen pro Antwort ([Schritt 11](#kn-antwort-s11))
- **2** gleiche Fehler, bis ein Werkzeug stoppt (oder 3 beliebige) ([Schritt 11](#kn-antwort-s11))
- **50** Zeichen, ab denen der erste Satz am Komma losgeht ([Schritt 5](#kn-antwort-s5))

#### Einstellen

- Einstellungen → Sprachmodell: Antwort-Prüfung, Taten prüfen und Fehlerschleife stoppen (alle drei Standard an).
- Einstellungen → Sprachmodell: Länge einer Antwort, Temperatur, Vorher nachdenken; unter Erweitert die Websuchen pro Antwort.

#### Was du siehst

- Zustand → Logs → Anfragen: jede Runde, jedes Werkzeug, „Antwort-Prüfung“ und „Taten-Prüfung“ mit Zahlen, nie mit Text.
- Zustand → Logs → Erweitert → Gespräch: wo die Zeit einer Antwort blieb, bis zum ersten Ton.
- Zustand → Verbessern: wie oft die eingebauten Regeln heute eingegriffen haben.

#### Im Code

- `app/panel/chat.py` `chat`: Rate-Limit, Sprache zuerst, „antwortet gerade“ ([Schritt 1](#kn-antwort-s1))
- `app/panel/chat.py` `_answer`: Runden, Werkzeuge, Prüfungen, Sprachausgabe als ein Strom ([Schritt 4](#kn-antwort-s4), [Schritt 5](#kn-antwort-s5), [Schritt 11](#kn-antwort-s11))
- `app/panel/chat.py` `split_sentences`: schneidet fertige Sätze ab ([Schritt 5](#kn-antwort-s5))
- `app/panel/chat.py` `said_key`: erkennt einen schon gesagten Satz ([Schritt 8](#kn-antwort-s8))
- `app/panel/chat.py` `no_code`: Codeblöcke nur zeigen, nie sprechen ([Schritt 8](#kn-antwort-s8))
- `app/panel/chat.py` `loop_count`: zählt Fehlschläge für Fehlerschleife stoppen ([Schritt 11](#kn-antwort-s11))
- `app/panel/answercheck.py` `known`: alle Angaben, die das Modell bekommen hat ([Schritt 6](#kn-antwort-s6))
- `app/panel/answercheck.py` `unsupported`: Angaben im Satz ohne Beleg ([Schritt 6](#kn-antwort-s6))
- `app/panel/answercheck.py` `fresh`: nach dem Kalender nur Angaben dieser Antwort ([Schritt 6](#kn-antwort-s6))
- `app/panel/taten.py` `check`: Tat behauptet, aber kein Werkzeug hat es geschafft ([Schritt 7](#kn-antwort-s7))
- `app/panel/taten.py` `sentence`: der feste ehrliche Satz ([Schritt 12](#kn-antwort-s12))

Selbsttests: `test_panel`, `test_taten`, `test_handlungsregel`, `test_fast_start`, `test_morgen_termine`

### Werkzeuge

Wenn das Modell ein Werkzeug aufruft, führt chat_tools.run es aus, aber nur, wenn es in dieser Runde angeboten war und keine Sperre greift. Das Ergebnis geht als Daten an das Modell zurück, nie als Befehl.

**Warum:** Ein Server-Parser reicht jeden Werkzeugnamen durch, den das Modell schreibt, auch erfundene oder gesperrte. Und eine Webseite oder Mail könnte das Modell bitten, das Licht zu schalten oder Daten wegzuschicken. Darum prüft das Panel bei jedem Aufruf neu, statt dem Modell zu glauben.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Modell ruft ein Werkzeug"])
  s2{{"2. In dieser Runde angeboten?"}}
  s3{{"3. Notaus hält es an?"}}
  s4{{"4. Fremder Text gelesen?"}}
  s5{{"5. Dienst gerade weg?"}}
  s6["6. Lesen markieren"]
  s7["7. Werkzeug ausführen"]
  s8["8. Fehler als Satz"]
  s9["9. Ergebnis als Daten einpacken"]
  s10["10. Gerät markiert die Antwort"]
  s11["11. Festhalten"]
  s12{{"12. Zweimal gescheitert?"}}
  s13(["13. Ergebnis zurück ans Modell"])
  s1 --> s2
  s2 -->|ja| s3
  s3 -->|nein| s4
  s4 -->|nein| s5
  s5 -->|nein| s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 --> s10
  s10 --> s11
  s11 --> s12
  s12 -->|nein| s13
  s2x(["Nicht ausgeführt"])
  s2 -->|nein| s2x
  s3x(["Gesperrt (Notaus)"])
  s3 -->|ja| s3x
  s4x(["Gesperrt (fremder Text)"])
  s4 -->|ja| s4x
  s5x(["Fester Satz: nicht erreichbar"])
  s5 -->|ja| s5x
  s12x(["Für diese Antwort gestoppt"])
  s12 -->|ja| s12x
```

1. <a id="kn-werkzeuge-s1"></a>**Modell ruft ein Werkzeug**: Höchstens 4 Aufrufe pro Runde laufen, und ein wegen Fehlern gestopptes Werkzeug läuft nicht mehr. Gedächtnis-Notizen sind auf 3 pro Antwort begrenzt.
2. <a id="kn-werkzeuge-s2"></a>**In dieser Runde angeboten?**: Nur Werkzeuge aus der Liste dieser Runde laufen. Die Liste ist schon um Sperren gekürzt; alles andere bekommt „nicht verfügbar, nicht noch einmal aufrufen“ oder, nach einer Mail, den Grund der Mail-Sperre.
3. <a id="kn-werkzeuge-s3"></a>**Notaus hält es an?**: Der Notaus wird bei jedem Aufruf gelesen, also greift er auch mitten in einer Antwort. Ab Stufe 1 sind die Werkzeuge gesperrt, die selbst ins Internet gehen; ab Stufe 2 oder mit dem eigenen Notaus des Profils jedes Werkzeug, das etwas ändert.
4. <a id="kn-werkzeuge-s4"></a>**Fremder Text gelesen?**: Hat diese Antwort schon Text von draußen gelesen, darf nichts mehr das Zuhause, das Gedächtnis, Termine oder Erinnerungen ändern. Nach einer Mail ist auch die Websuche zu, nach eigenen Dokumenten ebenfalls (außer bei „Erst lokal suchen“, dann nur mit den eigenen Worten der Frage).
5. <a id="kn-werkzeuge-s5"></a>**Dienst gerade weg?**: Sieht der Dienst-Wächter den Dienst dieses Werkzeugs gerade ausgefallen (und der Schalter dafür ist an), kommt sofort ein fester Satz mit der Uhrzeit des Ausfalls statt eines Versuchs. Die Websuche fragt erst unten und kann dann aufs eigene Archiv ausweichen.
6. <a id="kn-werkzeuge-s6"></a>**Lesen markieren**: Werkzeuge, die fremden Text bringen (Websuche, Dokumente, Kalender, frühere Gespräche, Kamera), setzen die Marke schon vor dem Lauf. Ab dann sind die Sperren aus Schritt 4 für den Rest der Antwort aktiv.
7. <a id="kn-werkzeuge-s7"></a>**Werkzeug ausführen**: Erweiterungen bekommen Profil, Gerät und Herkunft vom Panel, nie vom Modell. Smart-Home-Änderungen brauchen das Codewort in der letzten Nachricht, wenn eines eingestellt ist. Verbindungen zu Diensten draußen gehen über den Wächter.
8. <a id="kn-werkzeuge-s8"></a>**Fehler als Satz**: Ist ein Dienst nicht erreichbar, wird daraus ein kurzer Ergebnis-Text („nicht erreichbar“, „Suche fehlgeschlagen, nicht raten“). Ein angebotenes Werkzeug ohne passende Einrichtung meldet „unbekannt“.
9. <a id="kn-werkzeuge-s9"></a>**Ergebnis als Daten einpacken**: Fremder Text bekommt einen festen Hinweis davor und steht zwischen Markierungen, die er selbst nicht schließen kann. Zustände aus Home Assistant mit freiem Text (Titel, Listen) zählen auch als fremd.
10. <a id="kn-werkzeuge-s10"></a>**Gerät markiert die Antwort**: Das Gerät erfährt, dass die Antwort auf fremdem Text beruht. Solche Antworten gehen später nicht noch einmal ans Modell.
11. <a id="kn-werkzeuge-s11"></a>**Festhalten**: Die Log-Zeile nennt den Namen nur, wenn er angeboten war, sonst „unbekannt“. Was eine Tat war, merkt sich taten für die Handlungs-Prüfung. Menschen sehen die verständlichen Namen aus werkzeuge.py.
12. <a id="kn-werkzeuge-s12"></a>**Zweimal gescheitert?**: Scheitert ein Werkzeug 2 Mal mit denselben Angaben oder 3 Mal überhaupt, wird es für diese Antwort gestoppt und das Modell hört, dass es ehrlich sagen soll, was nicht ging.
13. <a id="kn-werkzeuge-s13"></a>**Ergebnis zurück ans Modell**: Das Modell bekommt das Ergebnis in der nächsten Runde als Daten. Was es daraus sagt, prüft wieder die Antwort (Antwort-Prüfung, Taten prüfen).

**Beispiele:** Termine lesen: Läuft; das Ergebnis geht eingepackt als Daten zurück. · Erfundener Werkzeugname: Nicht ausgeführt: das Werkzeug war nicht angeboten. · Notaus während der Antwort: Gesperrt: der nächste Aufruf liest den Notaus neu. · Websuche und Licht in einer Runde: Gesperrt: nach der Websuche darf nichts mehr schalten.

#### Regeln

Gilt bei: [Schritt 4](#kn-werkzeuge-s4)

| Lage in dieser Antwort | Gesperrt |
|---|---|
| fremder Text gelesen | 13 ändernde Werkzeuge und die der Erweiterungen |
| Mail gelesen | dazu Websuche und neue Termine |
| eigene Dokumente gelesen | Websuche (bei Erst lokal nur eigene Worte) |
| Notaus Stufe 1 | 7 Werkzeuge, die selbst ins Internet gehen |
| Notaus Stufe 2 oder eigener Notaus | jedes Werkzeug, das etwas ändert |

#### Zahlen (aus dem Code)

- **4** Aufrufe pro Runde ([Schritt 1](#kn-werkzeuge-s1))
- **3** Gedächtnis-Notizen pro Antwort ([Schritt 1](#kn-werkzeuge-s1))
- **13** Werkzeuge gesperrt nach fremdem Text ([Schritt 4](#kn-werkzeuge-s4))
- **7** Werkzeuge ohne Internet bei Notaus ([Schritt 3](#kn-werkzeuge-s3))
- **79** Werkzeuge mit verständlichem Namen ([Schritt 11](#kn-werkzeuge-s11))

#### Einstellen

- Einstellungen → Sprachmodell: Fehlerschleife stoppen (Standard an) und unter Erweitert die Websuchen pro Antwort.
- Funktionen → Weiche: welche Werkzeuge das Modell für eine Frage überhaupt sieht.

#### Was du siehst

- Zustand → Logs → Anfragen: jeder Aufruf mit verständlichem Namen, ok oder nicht, Länge und ob gesperrt.
- Zustand → Live: welches Werkzeug gerade läuft und was der Dienst zurückgab (nur die Art).

#### Im Code

- `app/panel/chat_tools.py` `run`: die Prüfungen und alle eingebauten Werkzeuge ([Schritt 2](#kn-werkzeuge-s2), [Schritt 7](#kn-werkzeuge-s7))
- `app/panel/chat.py` `_answer`: ruft run_tool, packt Ergebnisse ein, stoppt Schleifen ([Schritt 1](#kn-werkzeuge-s1))
- `app/panel/chat.py` `wrap_outside`: fremder Text als Datenblock ([Schritt 9](#kn-werkzeuge-s9))
- `app/panel/chat.py` `LOCKED_OUTSIDE`: gesperrt nach fremdem Text ([Schritt 4](#kn-werkzeuge-s4))
- `app/panel/chat.py` `LOCKED_MAIL`: gesperrt nach einer Mail ([Schritt 4](#kn-werkzeuge-s4))
- `app/panel/chat.py` `READS_OUTSIDE`: Werkzeuge, die fremden Text bringen ([Schritt 4](#kn-werkzeuge-s4), [Schritt 6](#kn-werkzeuge-s6))
- `app/panel/notaus.py` `locked_tools`: was der Notaus je Stufe sperrt ([Schritt 3](#kn-werkzeuge-s3))
- `app/panel/dienstwacht.py` `tool_down`: fester Satz, wenn ein Dienst weg ist ([Schritt 5](#kn-werkzeuge-s5))
- `app/panel/chat.py` `tool_info`: Zahlen für Logs → Anfragen ([Schritt 11](#kn-werkzeuge-s11))
- `app/panel/werkzeuge.py` `label`: verständlicher Name eines Werkzeugs ([Schritt 11](#kn-werkzeuge-s11))

Selbsttests: `test_fast_start`, `test_dienstwacht`, `test_taten`, `test_notaus`, `test_werkzeuge`, `test_werkzeug_abdeckung`

### Wissen

Wissen ist alles, was der Spark selbst weiß, ohne ins Internet zu gehen: die hochgeladenen Dokumente jedes Profils (eine SQLite-Datei wissen.db pro Profil), das Gedächtnis, frühere Gespräche, das eigene Kiwix-Archiv und erstellte Dokumente. Die Seite zeigt den Weg, auf dem eine Frage passende Stellen in den Dokumenten findet.

**Warum:** Das Sprachmodell kennt die eigenen Unterlagen nicht. Es bekommt nur die wenigen Stellen, die das Panel mit festen Regeln und zwei kleinen Modellen auf dem Prozessor heraussucht, jeweils mit Herkunft. Was in einem Dokument steht, ist Text von außen: Daten, nie ein Befehl.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Modell ruft document_search"])
  s2{{"2. Tags oder Art erlaubt?"}}
  s3["3. Bedeutungsvektor der Frage"]
  s4{{"4. Eingegrenzt?"}}
  s5["5. Volltext: Wörter und Kontextzeile"]
  s6["6. Bedeutung dazumischen"]
  s7{{"7. Neueste zuerst?"}}
  s8["8. Geteilte Dokumente der anderen"]
  s9{{"9. Treffer nachsortieren an?"}}
  s10["10. Cross-Encoder ordnet"]
  s11{{"11. „Was habe ich zuletzt notiert?“"}}
  s12{{"12. Keine Stelle gefunden?"}}
  s13(["13. Stellen mit Herkunft ans Modell"])
  s1 --> s2
  s2 -->|ja| s3
  s3 --> s4
  s4 -->|nein| s5
  s5 --> s6
  s6 --> s7
  s7 -->|nein| s8
  s8 --> s9
  s9 -->|ja| s10
  s10 --> s11
  s11 -->|nein| s12
  s12 -->|nein| s13
  s2x(["Tags und Art verworfen"])
  s2 -->|nein| s2x
  s3x(["nur Volltext"])
  s3 -->|kein Vektor| s3x
  s4x(["nur diese Dokumente"])
  s4 -->|ja| s4x
  s7x(["kleiner Vorsprung für Neues"])
  s7 -->|ja| s7x
  s9 -.->|nein| s11
  s10x(["Reihenfolge der Mischung"])
  s10 -->|schläft, belegt, langsam| s10x
  s11x(["neueste Seiten zuerst"])
  s11 -->|ja| s11x
  s12x(["Nichts gefunden, nicht raten"])
  s12 -->|ja| s12x
```

1. <a id="kn-wissen-s1"></a>**Modell ruft document_search**: Das Werkzeug wird nur angeboten, wenn das Profil eigene oder geteilte Dokumente hat, die Funktion für das Profil frei ist und die Stimme erkannt ist. Gäste und fremde Stimmen am geteilten Lautsprecher bekommen es nie. Das Profil kommt aus der Anmeldung, nie vom Modell.
2. <a id="kn-wissen-s2"></a>**Tags oder Art erlaubt?**: Das Modell darf die Suche auf Tags oder eine Dokumentart eingrenzen (höchstens fünf Tags). Ist „Steckbrief und Tags“ für das Profil aus, werden diese Angaben verworfen und alle Dokumente durchsucht.
3. <a id="kn-wissen-s3"></a>**Bedeutungsvektor der Frage**: Mit Bedeutungssuche rechnet ein kleines Vektormodell (eigener Prozess, nur Prozessor) den Vektor der Frage. Es startet nur bei mindestens 8.5 GiB freiem Speicher und endet nach 10 Minuten ohne Arbeit. Kommt kein Vektor, sucht der Spark nur im Volltext, ohne Fehler.
4. <a id="kn-wissen-s4"></a>**Eingegrenzt?**: Mit Tags oder Art sucht match_docs zuerst die Dokumente, die alle Tags und die Art tragen. Nur deren Stellen kommen weiter in Frage; passt keines, gibt es keine Treffer.
5. <a id="kn-wissen-s5"></a>**Volltext: Wörter und Kontextzeile**: Die Frage wird in Suchwörter zerlegt (Füllwörter weg, Endungen grob gekürzt). Gesucht wird in den Wörtern jeder Stelle und in ihrer Kontextzeile (Titel, Art, Überschriften), die nur mit 0.4 zählt. Die besten 30 bekommen einen Rang.
6. <a id="kn-wissen-s6"></a>**Bedeutung dazumischen**: Hat die Frage einen Vektor, werden die Vektoren aller Stellen verglichen. Unter 0,75 Ähnlichkeit gilt nichts als verwandt; die besten 30 darüber bekommen ebenfalls einen Rang. Beide Ränge werden addiert, so steigt eine Stelle, die in beiden Listen weit oben steht.
7. <a id="kn-wissen-s7"></a>**Neueste zuerst?**: Mit „Neueste zuerst“ bekommt eine kürzlich geänderte Stelle einen kleinen Vorsprung, etwa zwei Plätze, der mit dem Alter kleiner wird. Die Passung bleibt wichtiger; jeder Treffer trägt dann sein Datum.
8. <a id="kn-wissen-s8"></a>**Geteilte Dokumente der anderen**: Mit „Gemeinsame Dokumente“ läuft dieselbe Suche in den Dateien der anderen Profile, aber nur über Dokumente, die dort „Für alle“ sind. Die Treffer tragen den Namen des Besitzers; alles wird nach Rang sortiert.
9. <a id="kn-wissen-s9"></a>**Treffer nachsortieren an?**: Ohne Nachsortieren gehen die ersten fünf der Mischung weiter. Mit Nachsortieren reicht die Mischung ihre besten 30 weiter.
10. <a id="kn-wissen-s10"></a>**Cross-Encoder ordnet**: Ein kleines Modell auf dem Prozessor liest Frage und Stelle zusammen und gibt jeder eine Zahl. Stellen unter -4.0 beantworten die Frage nicht und fallen weg, die besten fünf bleiben. Schläft das Modell, ist es belegt, zu langsam oder kaputt, bleibt die Reihenfolge der Mischung; die Antwort wartet nie länger als eingestellt.
11. <a id="kn-wissen-s11"></a>**„Was habe ich zuletzt notiert?“**: Fragt die Person mit eigenen Worten nach dem, was sie zuletzt, heute oder diese Woche notiert hat, kommen die zuletzt geänderten Seiten zuerst. Ist in der Zeit nichts geändert, sagt das Werkzeug das, statt zu raten.
12. <a id="kn-wissen-s12"></a>**Keine Stelle gefunden?**: Findet die Suche nichts, waren aber Tags oder Art genannt, bekommt das Modell die Steckbrief-Zeilen der passenden Dokumente. Sonst heißt es: nichts gefunden, sag das, rate nicht.
13. <a id="kn-wissen-s13"></a>**Stellen mit Herkunft ans Modell**: Jede Stelle geht mit Dokument, Seite und Abschnitt ans Modell. Ab jetzt gilt die Antwort als eine, die Text von außen gelesen hat: Schalten, Merken und Erinnerungen sind in ihr gesperrt. Das Gerät zeigt die Quellen.

**Beispiele:** Frage nach einer Vertragsklausel: Gefunden: die Klausel und zwei Nachbarstellen, nachsortiert, mit Seite. · Vektormodell schläft noch: Gefunden über den Volltext allein; die Antwort hat nicht gewartet. · Rechnungen mit Tag, Wörter passen nicht: Keine Stelle, aber die Liste der Dokumente mit dem Tag.

#### Regeln

Gilt bei: [Schritt 1](#kn-wissen-s1), [Schritt 8](#kn-wissen-s8)

| Quelle | Wie sie gefunden wird | Wer |
|---|---|---|
| Eigene Dokumente | document_search: Volltext, Bedeutung, Nachsortieren | eigenes Profil |
| Geteilte Dokumente | dieselbe Suche, nur „Für alle“ | andere Profile, nie Gäste |
| Gedächtnis | wird nicht gesucht: steht in drei Blöcken im Systemprompt | eigenes Profil |
| Frühere Gespräche | history_search über Wörter | eigenes Profil |
| Kiwix | archive_search und wikipedia über das eigene Kiwix im Heimnetz | alle Profile, nie Gäste |
| Erst lokal suchen | Volltext ohne Warten auf Modelle, vor der ersten Runde | wie die Werkzeuge der Anfrage |

#### Erst lokal suchen

- Vor der ersten Runde schaut das Panel selbst in Dokumente, Kiwix und frühere Gespräche, gleichzeitig und nur kurz. Die Bedeutungssuche fährt nur mit, wenn ihr Modell schon läuft und frei ist; es wird dafür nicht geweckt.
- Eine Stelle zählt nur, wenn sie mindestens 0.6 der Suchwörter enthält. Was zu spät kommt, wird nicht abgewartet.

#### Gedächtnis

- Das Gedächtnis wird nicht durchsucht. Das Panel sortiert die Fakten mit festen Regeln in drei Blöcke (sicher, gelernt, vielleicht veraltet) und gibt sie dem Modell im Systemprompt.

#### Zahlen (aus dem Code)

- **30** Kandidaten für das Nachsortieren ([Schritt 9](#kn-wissen-s9))
- **-4.0** Untergrenze des Cross-Encoders ([Schritt 10](#kn-wissen-s10))
- **0.4** Gewicht der Kontextzeile ([Schritt 5](#kn-wissen-s5))
- **8 s** längstes Warten auf den Fragevektor ([Schritt 3](#kn-wissen-s3))
- **8.5 GiB** freier Speicher, damit das Vektormodell startet ([Schritt 3](#kn-wissen-s3))
- **3** Treffer höchstens bei „Erst lokal suchen“ ([Schritt 5](#kn-wissen-s5))

#### Einstellen

- Funktionen → Eigene Dokumente und darunter Bedeutungssuche an: Stellen bekommen einen Bedeutungsvektor (Standard aus).
- Funktionen → Eigene Dokumente und darunter Treffer nachsortieren an: dazu Modellgröße und wie lange höchstens gewartet wird.
- Funktionen → Eigene Dokumente und darunter Steckbrief und Tags an: Suche nach Tags und Art.
- Funktionen → Eigene Dokumente und darunter Gemeinsame Dokumente an: Dokumente „Für alle“.

#### Was du siehst

- Zustand → Logs → Anfragen: der Schritt „Nachsortieren“ mit Zahl der Kandidaten, behaltenen Stellen und Zustand des Modells.
- Zustand → Logs → Diagnose, Bereich Wissen: Zeilen von wissen, docembed, lokal und kiwix, nur feste Wörter und Zahlen.

#### Im Code

- `app/panel/wissen.py` `search`: eigene und geteilte Dokumente, Mischung, Nachsortieren ([Schritt 1](#kn-wissen-s1), [Schritt 8](#kn-wissen-s8), [Schritt 9](#kn-wissen-s9))
- `app/panel/documents.py` `search`: Volltext und Vektoren, Rangmischung ([Schritt 5](#kn-wissen-s5), [Schritt 6](#kn-wissen-s6))
- `app/panel/documents.py` `_terms`: Suchwörter aus der Frage ([Schritt 5](#kn-wissen-s5))
- `app/panel/documents.py` `match_docs`: Dokumente mit Tags und Art ([Schritt 4](#kn-wissen-s4))
- `app/panel/docembed.py` `query`: Fragevektor oder nichts ([Schritt 3](#kn-wissen-s3))
- `app/panel/docembed.py` `_call`: ein Auftrag an den Modellprozess ([Schritt 3](#kn-wissen-s3))
- `app/panel/nachsortieren.py` `rank`: Cross-Encoder oder Reihenfolge der Mischung ([Schritt 10](#kn-wissen-s10))
- `app/panel/wissen.py` `recent_window`: „zuletzt notiert“ als feste Regel ([Schritt 11](#kn-wissen-s11))
- `app/panel/wissen.py` `where`: Herkunft einer Stelle für das Modell ([Schritt 13](#kn-wissen-s13))
- `app/panel/lokal.py` `look`: der kurze Blick vor der Antwort ([Schritt 5](#kn-wissen-s5))
- `app/panel/gedaechtnis.py` `hint_lines`: Fakten in drei Blöcken ([Schritt 13](#kn-wissen-s13))

Selbsttests: `test_wissen`, `test_nachsortieren`, `test_abschnitte`, `test_lokal`, `test_kiwix`, `test_gedaechtnis`, `test_suchpruefung`

### Wächter

Der Wächter entscheidet bei jeder Verbindung, die ein Werkzeug nach außen aufbaut, ob sie sein darf: Webseiten aus der Suche, Kalender, Kontakte, Mail, Home Assistant, NAS und MCP-Dienste. Er prüft die Adresse, die wirklich angefragt wird, nach festen Regeln; das Sprachmodell fragt er nie.

**Warum:** Text von draußen (eine Webseite, eine Mail, ein Kalendereintrag) könnte das Sprachmodell dazu bringen, Adressen im Heimnetz, Cloud-Metadaten oder die eigenen Dienste des Spark anzufragen (SSRF). Der Wächter lässt das gar nicht erst zu, egal was im Text steht.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Werkzeug will nach außen"])
  s2["2. Name einmal auflösen"]
  s3{{"3. Eigener Dienst?"}}
  s4{{"4. Internet und Notaus an?"}}
  s5{{"5. Öffentliche Adresse?"}}
  s6{{"6. Stufe „nur Internet“?"}}
  s7{{"7. Nie erlaubt?"}}
  s8{{"8. Heimnetz erlaubt?"}}
  s9["9. Verbinden mit genau dieser Adresse"]
  s10["10. Passwort nur zur eigenen Seite"]
  s11["11. Antwort höchstens 20 MB"]
  s12(["12. Antwort ans Werkzeug"])
  s1 --> s2
  s2 --> s3
  s3 -->|nein| s4
  s4 -->|nein| s5
  s5 -->|nein| s6
  s6 -->|nein| s7
  s7 -->|nein| s8
  s8 -->|ja| s9
  s9 --> s10
  s10 --> s11
  s11 --> s12
  s3x(["Gesperrt"])
  s3 -->|ja| s3x
  s4x(["Gesperrt (Notaus)"])
  s4 -->|ja| s4x
  s5 -.->|ja| s9
  s6x(["Gesperrt"])
  s6 -->|ja| s6x
  s7x(["Gesperrt"])
  s7 -->|ja| s7x
  s8x(["Gesperrt"])
  s8 -->|nein| s8x
  s11x(["Abbruch"])
  s11 -->|größer| s11x
  s12 -.->|Weiterleitung| s2
```

1. <a id="kn-waechter-s1"></a>**Werkzeug will nach außen**: Alles, was eine Adresse aus Einstellungen oder aus fremdem Text ansteuert, holt sich seinen Zugang über netguard.client mit einer Stufe (heute 27 Module). Feste eigene Dienste wie das Sprachmodell laufen direkt; welche das sind und warum, steht in netguard.DIRECT_OK, ein Selbsttest hält die Liste vollständig.
2. <a id="kn-waechter-s2"></a>**Name einmal auflösen**: resolve() fragt den Namen genau einmal ab. Hat er mehrere Adressen, muss jede erlaubt sein, sonst ist Schluss.
3. <a id="kn-waechter-s3"></a>**Eigener Dienst?**: Die Ports der eigenen Dienste sind auf dieser Maschine gesperrt: auf Loopback und auf jeder eigenen Adresse im LAN oder VPN (own_addresses liest sie jede Minute neu).
4. <a id="kn-waechter-s4"></a>**Internet und Notaus an?**: Ist die Adresse öffentlich und der Notaus mindestens auf Stufe 1, geht nichts ins Internet, egal welche Stufe das Werkzeug hat. Das Heimnetz bleibt erreichbar, wie die Stufe es erlaubt.
5. <a id="kn-waechter-s5"></a>**Öffentliche Adresse?**: Eine öffentliche Adresse ist auf jeder Stufe erlaubt.
6. <a id="kn-waechter-s6"></a>**Stufe „nur Internet“?**: Was aus Suchergebnissen oder Antworten kommt, darf nie ins Heimnetz (chat, geraeteupdate, ghtoken, meldung, remarkable, verbund).
7. <a id="kn-waechter-s7"></a>**Nie erlaubt?**: Link-lokale Adressen (169.254.x, dort antworten Cloud-Metadaten), Multicast, unbestimmte und reservierte Adressen sind auf keiner Stufe erlaubt.
8. <a id="kn-waechter-s8"></a>**Heimnetz erlaubt?**: Home Assistant und andere Dienste im Heimnetz (doclingdienst, esp32, hamelden, homeassistant, kiwix, offsite) dürfen immer. Kalender, Kontakte, Mail und MCP (calendars, contacts, mail, mcp, meinmcp, tasks, technik_seiten) nur, wenn unter Einstellungen → Sicherheit → Heimnetz-Adressen erlauben eingeschaltet ist.
9. <a id="kn-waechter-s9"></a>**Verbinden mit genau dieser Adresse**: Die Verbindung geht an die geprüfte Adresse, nicht noch einmal an den Namen. Ein zweites Nachschlagen könnte anders antworten (DNS-Rebinding). Das Zertifikat wird trotzdem für den Namen geprüft.
10. <a id="kn-waechter-s10"></a>**Passwort nur zur eigenen Seite**: Anmeldedaten gehen nur an die Seite, für die sie eingetragen wurden (gleicher Host oder gleiche Hauptdomain, etwa die CalDAV-Server von icloud.com), nie über http, wenn die Adresse https war.
11. <a id="kn-waechter-s11"></a>**Antwort höchstens 20 MB**: Antworten werden bei 20 MB abgeschnitten, auch nach dem Entpacken von gzip, damit eine riesige oder gepackte Antwort den Speicher nicht füllt.
12. <a id="kn-waechter-s12"></a>**Antwort ans Werkzeug**: Das Werkzeug bekommt die Antwort als Daten. Eine Weiterleitung ist eine neue Verbindung und wird genauso geprüft, ab Schritt 2.

**Beispiele:** Webseite aus der Suche: Erlaubt: verbunden mit der geprüften öffentlichen Adresse. · Home Assistant im Heimnetz: Erlaubt: die Stufe Heimnetz darf ins Heimnetz. · Kalender im Heimnetz, Schalter aus: Gesperrt: Heimnetz-Adressen sind für Nutzer-Dienste aus. · Link auf Cloud-Metadaten: Gesperrt: eine Seite aus der Suche darf nie ins Heimnetz, 169.254 nie. · Notaus an, Wetter abfragen: Gesperrt: bei Notaus geht nichts ins Internet.

#### Regeln

Gilt bei: [Schritt 6](#kn-waechter-s6), [Schritt 8](#kn-waechter-s8)

| Stufe | Wer sie nutzt (aus dem Code) | Internet | Heimnetz |
|---|---|---|---|
| nur Internet | chat, geraeteupdate, ghtoken, meldung, remarkable, verbund | ✓ | ✕ |
| Nutzer | calendars, contacts, mail, mcp, meinmcp, tasks, technik_seiten | ✓ | nur mit Schalter |
| Heimnetz | doclingdienst, esp32, hamelden, homeassistant, kiwix, offsite | ✓ | ✓ |
| je nach Ziel | dienstwacht, nas, nasquelle, speicher, technik_seiten, zertpin | wie das Ziel eingestellt ist | – |
| immer | alle | ✕ bei Notaus | ✕ eigene Dienste, 169.254, Multicast |

#### Wenn gesperrt

- Das Werkzeug bekommt statt einer Antwort den Fehler Blocked mit dem Grund; es kommt keine Verbindung zustande.
- Die Sperre zählt für „Notaus von selbst“: 15 in 10 Minuten heben den Notaus auf Stufe 1, wenn der Schalter an ist. Sperren durch den Notaus selbst und Proben des Dienst-Wächters zählen nicht.

#### Zahlen (aus dem Code)

- **20 MB** größte Antwort ([Schritt 11](#kn-waechter-s11))
- **30000–31099, 31443** gesperrte eigene Ports ([Schritt 3](#kn-waechter-s3))
- **15** Sperren in 10 Minuten bis Notaus Stufe 1 (wenn an) ([Schritt 4](#kn-waechter-s4))
- **1** Notaus-Stufe ohne Internet ([Schritt 4](#kn-waechter-s4))

#### Einstellen

- Einstellungen → Sicherheit → Heimnetz-Adressen erlauben: Kalender, Kontakte, Mail und MCP dürfen auch ins Heimnetz (Standard aus).
- Einstellungen → Sicherheit → Notaus von selbst: viele gesperrte Verbindungen in kurzer Zeit lösen Notaus Stufe 1 aus (Standard aus).

#### Was du siehst

- Zustand → Live: eine rote Linie endet mit ✕ an der Wand, mit Adresse und Grund; die Kachel „Wächter heute“ zählt die Sperren.
- Ich → Mein Zustand: ob ein eigener Dienst (Kalender, Mail) antwortet oder die Anmeldung abgelehnt hat.

#### Im Code

- `app/panel/netguard.py` `allowed`: die Regel: nichts oder der Grund ([Schritt 3](#kn-waechter-s3), [Schritt 7](#kn-waechter-s7), [Schritt 8](#kn-waechter-s8))
- `app/panel/netguard.py` `resolve`: einmal auflösen, jede Adresse prüfen, Live melden ([Schritt 2](#kn-waechter-s2))
- `app/panel/netguard.py` `client`: der Zugang nach außen für Werkzeuge ([Schritt 1](#kn-waechter-s1))
- `app/panel/netguard.py` `_Transport`: Passwort-Schutz, Größengrenze, Ergebnis für Mein Zustand ([Schritt 10](#kn-waechter-s10), [Schritt 11](#kn-waechter-s11))
- `app/panel/netguard.py` `_Capped`: schneidet die Antwort ab, auch entpackt ([Schritt 11](#kn-waechter-s11))
- `app/panel/netguard.py` `same_site`: gleiche Seite für Anmeldedaten ([Schritt 10](#kn-waechter-s10))
- `app/panel/netguard.py` `own_addresses`: alle Adressen dieser Maschine ([Schritt 3](#kn-waechter-s3))
- `app/panel/netguard.py` `IMAP4_SSL`: Mail über die geprüfte Adresse ([Schritt 9](#kn-waechter-s9))
- `app/panel/notaus.py` `watch`: zählt Sperren für Notaus von selbst ([Schritt 2](#kn-waechter-s2))
- `app/panel/live.py` `outgoing`: zeigt jede Entscheidung auf Live ([Schritt 2](#kn-waechter-s2))

Selbsttests: `test_hardening`, `test_notaus`, `test_waechter_umgehung`

### Logs und Live

Betrieb hält fest, was der Spark tut, ohne Inhalte: den Weg jeder Anfrage (Logs → Anfragen), die Live-Übersicht, das Journal mit festen Wörtern, den Dienst-Wächter und die Sicherung. Die Seite zeigt, welche Spuren eine Anfrage hinterlässt.

**Warum:** Wer einen Fehler sucht, muss sehen, welchen Weg eine Anfrage nahm und wie lange jeder Schritt dauerte. Fragen, Antworten und Werkzeugergebnisse gehören aber der Person; deshalb gehen nur feste Wörter, Werkzeugnamen und Zahlen in Log und Verlauf.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Anfrage kommt an"])
  s2{{"2. Etwas eingeschaltet?"}}
  s3["3. Schritte mit festen Wörtern"]
  s4{{"4. Live-Seite an?"}}
  s5["5. Journal-Zeilen der Module"]
  s6["6. Ende und Bewertung"]
  s7{{"7. Anfragen verfolgen an?"}}
  s8["8. Zeile „anfrage:“ ins Journal"]
  s9["9. Anfrage-Verlauf auf der Platte"]
  s10["10. Admin liest Logs → Anfragen"]
  s11["11. Journal lesen und einordnen"]
  s12(["12. Diagnose mit festem Hinweis"])
  s1 --> s2
  s2 -->|ja| s3
  s3 --> s4
  s4 -->|nein| s5
  s5 --> s6
  s6 --> s7
  s7 -->|ja| s8
  s8 --> s9
  s9 --> s10
  s10 --> s11
  s11 --> s12
  s2x(["Kein Verlauf, nur Journal"])
  s2 -->|nein| s2x
  s4x(["Zustand → Live zeigt es"])
  s4 -->|ja| s4x
  s7x(["Nicht gespeichert"])
  s7 -->|nein| s7x
```

1. <a id="kn-betrieb-s1"></a>**Anfrage kommt an**: Chat, Schreibhilfe, Dokumente erstellen und was der Spark von selbst tut, legen beim Start einen Datensatz an: Kanal, Art (Profil, Gast, Admin, Spark) und Gerät.
2. <a id="kn-betrieb-s2"></a>**Etwas eingeschaltet?**: Ist weder „Anfragen verfolgen“ noch die Live-Seite noch der Einstellungs-Assistent an, gibt es keinen Datensatz. Übrig bleiben nur die Journal-Zeilen der Module.
3. <a id="kn-betrieb-s3"></a>**Schritte mit festen Wörtern**: Jeder Schritt (Weiche, Modellrunde, Werkzeug, Prüfung, Sprachausgabe) kommt mit Art, Name und Zeit dazu. Ein Wert geht nur hinein, wenn er eine Zahl oder ein kurzes festes Wort ist; alles andere wird verworfen. Frage, Antwort, Argumente und Ergebnisse kommen nie hinein.
4. <a id="kn-betrieb-s4"></a>**Live-Seite an?**: Bei eingeschalteter Live-Seite sieht live.py jeden Schritt sofort: welcher Dienst gefragt wird, was der Wächter entscheidet, was zurückkommt. Alles bleibt im Speicher und ist nach einem Neustart weg.
5. <a id="kn-betrieb-s5"></a>**Journal-Zeilen der Module**: Unabhängig davon schreibt jedes Modul seine Zeilen ins Journal des Spark. Jede Zeile beginnt mit einem Wort aus logfilter.AREAS (28 Bereiche), Profile nur über profiles.log_name. Ein Selbsttest prüft beides.
6. <a id="kn-betrieb-s6"></a>**Ende und Bewertung**: Am Ende bekommt der Datensatz seinen Zustand: Fehler, wenn ein Fehlerwort gesetzt ist, langsam, wenn der erste Ton später als 5.0 s kam, sonst gut.
7. <a id="kn-betrieb-s7"></a>**Anfragen verfolgen an?**: Ist nur Live oder der Einstellungs-Assistent an, endet der Datensatz hier. Er wird nirgends geschrieben.
8. <a id="kn-betrieb-s8"></a>**Zeile „anfrage:“ ins Journal**: Eine Zeile pro Anfrage: Kennung, Kanal, Einordnung, Werkzeuge mit ok oder nicht ok, Zeit bis zur Rückmeldung, bis zum ersten Ton und bis zum Ende. Ohne Namen.
9. <a id="kn-betrieb-s9"></a>**Anfrage-Verlauf auf der Platte**: Der Datensatz wird angehängt. Wird die Datei zu groß, bleiben nur die letzten 500 Anfragen der letzten 2880 Minuten. Die Datei ist in keiner Sicherung.
10. <a id="kn-betrieb-s10"></a>**Admin liest Logs → Anfragen**: Nur Admin und Mit-Admins lesen den Verlauf, mit Rate-Limit. Name und Gerät eines Profils stehen nur da, wenn das Profil es erlaubt; sonst heißt es „Profil“. Zu einer Anfrage zeigt das Panel die Journal-Zeilen aus ihrer Zeit.
11. <a id="kn-betrieb-s11"></a>**Journal lesen und einordnen**: logfilter liest höchstens 20000 Zeilen; an journalctl gehen nur Zahlen aus festen Listen. Jede Zeile bekommt ihren Bereich aus dem ersten Wort, ihre Stufe aus festen Fehlerwörtern; Tokens, Schlüssel und Passwörter werden geschwärzt, bevor die Zeile das Panel verlässt.
12. <a id="kn-betrieb-s12"></a>**Diagnose mit festem Hinweis**: Die Diagnose zählt Zeilen pro Bereich und zeigt zum neuesten Fehler einen festen Hinweis aus einer Liste, nie einen vom Modell.

**Beispiele:** Alles an, eine Frage mit Werkzeug: Live zeigt den Weg, Logs → Anfragen behält ihn, das Journal hat die Zeile „anfrage:“. · Nur die Live-Seite an: Auf Zustand → Live zu sehen, danach nirgends gespeichert. · Alles aus: Kein Datensatz; nur die Journal-Zeilen der Module.

#### Regeln

Gilt bei: [Schritt 4](#kn-betrieb-s4)

| Spur | Wo | Wie lange | In der Sicherung |
|---|---|---|---|
| Live | Speicher | bis zum Neustart | ✕ |
| Anfrage-Verlauf | state/traces.jsonl | 2880 min | ✕ |
| Journal | journald | wie journald eingestellt ist | ✕ |
| Dienst-Wächter | state/dienstwacht.json | Ausfälle 10080 min | ✓ |
| Sicherungen | backups/ | 7 tägliche, 5 andere | – |

#### Dienst-Wächter

- Eine Schleife prüft Sprachmodell, Hören, Sprechen, Internet, SearXNG, Kiwix, Home Assistant, Mail, Kalender und NAS, je nach Dienst jede Minute oder alle 5 Minuten, ohne Anmeldung: eine HTTP-Antwort unter 500 gilt als „antwortet“.
- Weg ist ein Dienst nach 3 Fehlproben über mindestens 3 Minuten, zurück nach 2 guten. Ist das Internet weg, gibt es eine Meldung für alles dahinter. Während Update, Start und Notaus Stufe 2 zählt nichts.
- Die Proben gehen über den Wächter, zählen aber nicht auf der Live-Liste und lösen nie „Notaus von selbst“ aus.

#### Sicherung

- Einmal am Tag packt das Panel in einer Pause users/, voices/, config.json, das Panel-Passwort und die Dateien aus backup.STATE_FILES. Der Schlüssel state/secret.key und die Anmeldeschlüssel sind nicht dabei; Datenbanken werden als stimmige Kopie gesichert.

#### Zahlen (aus dem Code)

- **500** Anfragen im Verlauf höchstens ([Schritt 9](#kn-betrieb-s9))
- **2880 min** so lange bleibt eine Anfrage ([Schritt 9](#kn-betrieb-s9))
- **5.0 s** ab hier gilt eine Anfrage als langsam ([Schritt 6](#kn-betrieb-s6))
- **3** Fehlproben in Folge, bis ein Dienst als weg gilt ([Schritt 5](#kn-betrieb-s5))
- **30 min** höchstens eine Ausfall-Meldung pro Dienst ([Schritt 5](#kn-betrieb-s5))
- **7** tägliche und eigene Sicherungen, die bleiben ([Schritt 9](#kn-betrieb-s9))

#### Einstellen

- Einstellungen → Spark → Betrieb → Anfragen verfolgen: Logs → Anfragen (Standard aus).
- Einstellungen → Spark → Betrieb → Logs „Live-Seite“: Zustand → Live (Standard aus).
- Funktionen → Dienst-Wächter: Dienste prüfen und Admins bei Ausfall benachrichtigen (Standard aus).
- Einstellungen → Sicherung: eine Sicherung von Hand anlegen oder zurückspielen.

#### Was du siehst

- Zustand → Logs → Anfragen: der Weg jeder Anfrage mit Werkzeugen und Zeiten.
- Zustand → Logs → Diagnose: Zeilen nach Bereich, Fehler und Warnungen, mit festem Hinweis.
- Zustand → Live: laufende Anfragen, Wächter-Entscheidungen und Dienste als Bild.
- Zustand → Dienste: was der Dienst-Wächter prüft und die Ausfälle der letzten Tage.

#### Im Code

- `app/panel/tracelog.py` `start`: ein Datensatz, wenn etwas an ist ([Schritt 1](#kn-betrieb-s1))
- `app/panel/tracelog.py` `safe`: nur Zahlen und kurze feste Wörter ([Schritt 3](#kn-betrieb-s3))
- `app/panel/tracelog.py` `Rec`: Schritte, Marken, Zustand ([Schritt 3](#kn-betrieb-s3), [Schritt 6](#kn-betrieb-s6))
- `app/panel/tracelog.py` `finish`: Journal-Zeile und Anfrage-Verlauf ([Schritt 8](#kn-betrieb-s8), [Schritt 9](#kn-betrieb-s9))
- `app/panel/tracelog.py` `shown`: Name nur mit Zustimmung ([Schritt 10](#kn-betrieb-s10))
- `app/panel/live.py` `step`: jeder Schritt auf Zustand → Live ([Schritt 4](#kn-betrieb-s4))
- `app/panel/logfilter.py` `AREAS`: die Bereichswörter des Journals ([Schritt 5](#kn-betrieb-s5))
- `app/panel/logfilter.py` `parse`: Bereich, Stufe, Schwärzen ([Schritt 11](#kn-betrieb-s11))
- `app/panel/logfilter.py` `summary`: Zähler und fester Hinweis ([Schritt 12](#kn-betrieb-s12))
- `app/panel/dienstwacht.py` `round_once`: eine Runde Proben und Meldungen ([Schritt 5](#kn-betrieb-s5))
- `app/panel/backup.py` `create`: eine Sicherung packen ([Schritt 9](#kn-betrieb-s9))

Selbsttests: `test_tracelog`, `test_live`, `test_logfilter`, `test_log_luecken`, `test_dienstwacht`, `test_hardening`, `test_panel`

### Sprachmodell

Das Sprachmodell (qwen38 aus dgx-spark-qwen38, nicht Teil dieses Repos) schreibt die Antworten. Das Panel spricht es an der eingestellten Adresse über die OpenAI-Schnittstelle an, gestreamt, und sorgt dafür, dass Sprache immer vor Hintergrundarbeit kommt.

**Warum:** Die GPU teilt sich das Modell mit der Sprachausgabe. Wartet eine Person, darf kein Lernen oder Aufräumen im Hintergrund die Antwort bremsen. Und ein hängendes oder fehlendes Modell soll einen klaren Satz ergeben, keine Minuten Stille.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Sprache zuerst"])
  s2["2. Verbindung für diese Antwort"]
  s3["3. Modellname"]
  s4["4. Anfrage bauen"]
  s5{{"5. Wartet jemand mit Vorrang?"}}
  s6["6. Eine Runde an das Modell"]
  s7{{"7. Zu lang für das Modell?"}}
  s8{{"8. Erste Zeile rechtzeitig?"}}
  s9["9. Zeilen lesen"]
  s10["10. Nur Antworttext weiter"]
  s11["11. Runde festhalten"]
  s12{{"12. Fehler unterwegs?"}}
  s13(["13. Text und Werkzeugaufrufe zurück"])
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 --> s5
  s5 -->|nein| s6
  s6 --> s7
  s7 -->|nein| s8
  s8 -->|ja| s9
  s9 --> s10
  s10 --> s11
  s11 --> s12
  s12 -->|nein| s13
  s5x(["kurz warten, dann weiter"])
  s5 -->|ja| s5x
  s7 -.->|ja| s6
  s8x(["„antwortet gerade nicht“"])
  s8 -->|nein| s8x
  s12x(["Fester Satz statt Antwort"])
  s12 -->|ja| s12x
```

1. <a id="kn-llm-s1"></a>**Sprache zuerst**: Mit dem Start einer Antwort und bei jedem gestreamten Stück setzt das Panel die Marke „Sprache läuft“. Hintergrundarbeit am Modell wartet bis 20 Sekunden danach und wird abgebrochen, sobald jemand spricht; nach 3 Abbrüchen gibt sie für diesmal auf.
2. <a id="kn-llm-s2"></a>**Verbindung für diese Antwort**: Jede Antwort hat eine eigene Verbindung mit dem eingestellten Zeitlimit (ein Wert außerhalb gilt nicht) und fünf Sekunden zum Verbinden. Ist ein Schlüssel eingetragen, geht er als Bearer mit. Das Modell ist ein fester eigener Dienst und läuft nicht über den Wächter.
3. <a id="kn-llm-s3"></a>**Modellname**: Ist kein Modell eingestellt, fragt das Panel einmal /models und merkt sich den ersten Namen für diese Adresse.
4. <a id="kn-llm-s4"></a>**Anfrage bauen**: Die Anfrage streamt, mit Länge, Temperatur, top_p und presence_penalty aus den Einstellungen. Denken ist aus, außer „Vorher nachdenken“ ist an. Während der Werkzeugwahl gilt die eigene Temperatur dafür. Bei eingeschalteten Logs meldet der Server, wie viel er gelesen hat und wie viel aus seinem Zwischenspeicher kam.
5. <a id="kn-llm-s5"></a>**Wartet jemand mit Vorrang?**: Hat eine andere Person Vorrang und ihre Antwort noch keinen ersten Satz, wartet diese Runde höchstens die eingestellte Zeit (bis 5 Sekunden). Eine Antwort mit Vorrang hält andere höchstens 30 Sekunden auf.
6. <a id="kn-llm-s6"></a>**Eine Runde an das Modell**: Die Runde geht an die eingestellte Adresse. Lehnt der Server die erzwungene Werkzeugwahl ab, geht dieselbe Runde einmal ohne sie.
7. <a id="kn-llm-s7"></a>**Zu lang für das Modell?**: Meldet der Server, dass die Anfrage länger als sein Kontext ist, kürzt das Panel in der ersten Runde den Verlauf auf ein Viertel des Verlaufsbudgets und fragt einmal neu.
8. <a id="kn-llm-s8"></a>**Erste Zeile rechtzeitig?**: Die erste Zeile muss innerhalb von 90 Sekunden kommen (oder des kürzeren Zeitlimits). Ein Modell, das länger schweigt, hängt: die Antwort endet mit einem klaren Satz statt mit Minuten Stille.
9. <a id="kn-llm-s9"></a>**Zeilen lesen**: Jede Zeile ist ein Stück JSON. Werkzeugaufrufe kommen in Teilen und werden nach ihrer Nummer zusammengesetzt; Denktext, den der Server getrennt liefert, wird nur gezählt. Unlesbare Zeilen werden übersprungen.
10. <a id="kn-llm-s10"></a>**Nur Antworttext weiter**: Denktext im Text (<think> … </think>) und Werkzeugaufrufe, die als Text kommen, werden nie gezeigt oder gesprochen. Der Rest geht Stück für Stück an „Antwort bauen“.
11. <a id="kn-llm-s11"></a>**Runde festhalten**: Für den Anfrage-Verlauf zählen nur Zahlen: gelesene Tokens, davon aus dem Zwischenspeicher, Größe von Systemprompt, Werkzeugliste und Verlauf, Zeit bis zum ersten Wort, Wartezeit wegen Vorrang.
12. <a id="kn-llm-s12"></a>**Fehler unterwegs?**: Ein Fehler wird zu einem festen Kürzel: nicht erreichbar, zu langsam, Schlüssel abgelehnt, Modell fehlt. Bei „nicht erreichbar“ und „zu langsam“ wird ein fester Satz auch gesprochen, wenn noch nichts gesagt war. Gäste sehen nur die Art des Fehlers, nie seinen Text.
13. <a id="kn-llm-s13"></a>**Text und Werkzeugaufrufe zurück**: Die Runde gibt zurück, warum sie endete und welche Werkzeuge das Modell aufrufen will. Was davon läuft, entscheidet das Panel.

**Beispiele:** Normale Antwort: Gestreamt, der erste Satz geht sofort zur Sprachausgabe. · Zwei Personen, eine mit Vorrang: Die Runde wartet kurz, bis die Antwort mit Vorrang ihren ersten Satz hat. · Sehr langes Dokument im Verlauf: Verlauf gekürzt, einmal neu gefragt. · qwen38 hängt: „Mein Sprachmodell antwortet gerade nicht.“ statt Stille.

#### Zahlen (aus dem Code)

- **90 s** bis zur ersten Zeile des Modells ([Schritt 8](#kn-llm-s8))
- **60 bis 600 s** erlaubtes Zeitlimit ([Schritt 2](#kn-llm-s2))
- **20 s** nach Sprache wartet Hintergrundarbeit noch ([Schritt 1](#kn-llm-s1))
- **3** Abbrüche, bis Hintergrundarbeit aufgibt ([Schritt 1](#kn-llm-s1))
- **5 s** längste Wartezeit für Vorrang ([Schritt 5](#kn-llm-s5))
- **30 s** so lange hält eine Antwort mit Vorrang höchstens auf ([Schritt 5](#kn-llm-s5))

#### Einstellen

- Einstellungen → Sprachmodell: Adresse, Schlüssel und Modell; dazu Vorher nachdenken, Temperatur und Länge einer Antwort.
- Einstellungen → Sprachmodell, unter Erweitert: Zeitlimit für eine Antwort.
- Funktionen → Vorrang für Personen: ausgewählte Profile bekommen ihre Antwort zuerst.

#### Was du siehst

- Zustand → Logs → Erweitert → Gespräch: pro Runde gelesene Tokens, davon aus dem Zwischenspeicher, und die Zeit bis zum ersten Wort.
- Zustand → Prüfen → Vorrang für Sprache: ob die Sprachausgabe flüssig bleibt, während das Modell rechnet.

#### Im Code

- `app/panel/chat.py` `chat`: setzt „Sprache läuft“ bei jedem Stück ([Schritt 1](#kn-llm-s1))
- `app/panel/chat.py` `_answer`: Verbindung, Anfrage, Runden (llm_round), Fehlerfälle ([Schritt 2](#kn-llm-s2), [Schritt 4](#kn-llm-s4), [Schritt 6](#kn-llm-s6))
- `app/panel/chat.py` `llm_model`: Modellname aus Einstellung oder /models ([Schritt 3](#kn-llm-s3))
- `app/panel/chat.py` `sampling`: top_p und presence_penalty ([Schritt 4](#kn-llm-s4))
- `app/panel/chat.py` `first_within`: die erste Zeile muss rechtzeitig kommen ([Schritt 8](#kn-llm-s8))
- `app/panel/chat.py` `ContextFull`: Anfrage länger als der Kontext ([Schritt 7](#kn-llm-s7))
- `app/panel/chat.py` `llm_error_code`: Fehler als festes Kürzel ([Schritt 12](#kn-llm-s12))
- `app/panel/chat.py` `LLM_GONE`: der gesprochene Satz, wenn das Modell fehlt ([Schritt 12](#kn-llm-s12))
- `app/panel/chat.py` `prompt_sizes`: Größe der Teile einer Anfrage ([Schritt 11](#kn-llm-s11))
- `app/panel/stufe.py` `wait_turn`: wartet auf eine Antwort mit Vorrang ([Schritt 5](#kn-llm-s5))
- `app/panel/vorrang.py` `mark`: Marke „Sprache läuft“ ([Schritt 1](#kn-llm-s1))
- `app/panel/vorrang.py` `run`: Hintergrundarbeit weicht der Sprache ([Schritt 1](#kn-llm-s1))

Selbsttests: `test_panel`, `test_llm_settings`, `test_vorrang`, `test_stufe`, `test_fast_start`

### Spracherkennung

Die Spracherkennung macht aus einer Aufnahme Text. Das Panel nimmt die Aufnahme an, prüft sie und reicht sie an den ASR-Dienst weiter. Dieser Proxy prüft Schlüssel, Größe und Abtastrate, lässt Anfragen nach Vorrang warten und gibt sie an die Engine, die nur auf dieser Maschine lauscht.

**Warum:** Eine Aufnahme kommt von draußen: von einem Browser, einer App, einem Lautsprecher. Sie könnte riesig sein, eine erfundene Abtastrate tragen oder nur Stille, ein Klick oder die eigene Stimme des Spark sein. Feste Regeln fangen das ab, bevor die Grafikkarte rechnet und bevor ein Text als Frage zählt.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Aufnahme kommt an"])
  s2["2. Höchstens 50 MB"]
  s3["3. Nebenbei auf dem Prozessor"]
  s4["4. An den ASR-Dienst"]
  s5{{"5. Schlüssel und Größe in Ordnung?"}}
  s6{{"6. Engine bereit?"}}
  s7["7. Warten nach Vorrang"]
  s8{{"8. Abtastrate erlaubt?"}}
  s9["9. Erkennen"]
  s10{{"10. Stille, Füllwort oder Echo?"}}
  s11{{"11. Stimme erkannt?"}}
  s12(["12. Text zurück"])
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 --> s5
  s5 -->|ja| s6
  s6 -->|ja| s7
  s7 --> s8
  s8 -->|ja| s9
  s9 --> s10
  s10 -->|nein| s11
  s11 -->|nein| s12
  s2x(["Abgelehnt (413)"])
  s2 -->|größer| s2x
  s5x(["Abgelehnt (401 oder 413)"])
  s5 -->|nein| s5x
  s6x(["Nicht bereit (503)"])
  s6 -->|nein| s6x
  s7x(["Besetzt (503)"])
  s7 -->|Schlange voll| s7x
  s8x(["Abgelehnt (415)"])
  s8 -->|nein| s8x
  s10x(["Leerer Text, nicht als Frage"])
  s10 -->|ja| s10x
  s11x(["Name und ein Token des Profils gehen mit"])
  s11 -->|ja| s11x
```

1. <a id="kn-asr-s1"></a>**Aufnahme kommt an**: Der Browser schickt die Aufnahme ans Panel. Jeder Anrufer darf nur so oft pro Minute (Profil 240), Gäste teilen sich 3 Plätze gleichzeitig.
2. <a id="kn-asr-s2"></a>**Höchstens 50 MB**: read_audio liest die Aufnahme in Stücken und bricht bei 50 MB ab. Ein Weckwort darf nur ein angemeldetes Profil mitschicken; es geht dann als Hinweis an das Modell.
3. <a id="kn-asr-s3"></a>**Nebenbei auf dem Prozessor**: Während die Grafikkarte erkennt, laufen auf dem Prozessor schon die Sprechererkennung (wenn an und ein Profil fragt), die Raum-Stimme, die Prüfung auf eine fremde Stimme und die Messung, wie viel der Aufnahme wirklich Stimme ist.
4. <a id="kn-asr-s4"></a>**An den ASR-Dienst**: Das Panel schickt die Aufnahme mit dem API-Schlüssel an den Proxy. stufe.asr_level legt die Stufe des Profils bei, an einem geteilten Lautsprecher aber nicht. Nur das Panel kann eine Stufe setzen: mit dem Schlüssel aus vorrang-key und nur von dieser Maschine, sonst gilt normal.
5. <a id="kn-asr-s5"></a>**Schlüssel und Größe in Ordnung?**: BodyLimit lehnt zu große Anfragen und solche ohne den richtigen Schlüssel ab, bevor etwas gelesen wird. Ohne eingetragenen Schlüssel darf nur diese Maschine selbst fragen.
6. <a id="kn-asr-s6"></a>**Engine bereit?**: engine_status fragt /health der Engine. Antwortet sie nicht, liest der Proxy ihren Zustand und den der systemd-Einheit und nennt den Grund.
7. <a id="kn-asr-s7"></a>**Warten nach Vorrang**: PrioGate lässt so viele Aufnahmen durch, wie die Engine gleichzeitig nimmt (engine_max_seqs). Die anderen warten nach Stufe, dann nach Ankunft. Wer wartet, rückt alle vier Sekunden eine Stufe auf; eine laufende Anfrage wird nie unterbrochen.
8. <a id="kn-asr-s8"></a>**Abtastrate erlaubt?**: audio_rate_ok liest die Abtastrate aus dem Kopf der Datei (WAV, FLAC, Ogg, WebM) oder fragt ffprobe. Ein Kopf mit erfundener Rate würde beim Umrechnen den Speicher füllen.
9. <a id="kn-asr-s9"></a>**Erkennen**: Mit Qwen3-ASR geht die Aufnahme an die vLLM-Engine, die nur auf dieser Maschine lauscht; nur prompt, temperature und stream reichen durch, dazu die Kontextwörter aus den Einstellungen. Mit Parakeet erkennt der Proxy selbst auf dem Prozessor, in Stücken von höchstens 90 Sekunden, die an einer leisen Stelle geschnitten werden.
10. <a id="kn-asr-s10"></a>**Stille, Füllwort oder Echo?**: stille.check verwirft Text aus fast stummen Aufnahmen und ein einzelnes „Ja“ oder „Okay“ mit zu wenig Stimme. Für Profile prüft echo.check, ob der Text die eigene Stimme des Spark von einem anderen Gerät ist, und fremdstimme, ob ein von selbst geöffnetes Mikrofon eine fremde Stimme hörte.
11. <a id="kn-asr-s11"></a>**Stimme erkannt?**: speakers.identify vergleicht die Aufnahme mit jedem eingelernten Stimmabdruck. Nur ein klarer Treffer (über der Schwelle der gewählten Strenge und deutlich vor dem Zweiten) zählt. Live zeigt nur „Stimme erkannt“, nie wessen.
12. <a id="kn-asr-s12"></a>**Text zurück**: Der Text geht an das Gerät, das daraus die Frage an den Chat macht. Bei einem Fehler bekommt ein Gast nur einen festen Code, nie den Text des Dienstes.

**Beispiele:** Frage im Browser, Profil: Text mit erkannter Stimme zurück. · Klick nach der Antwort: Verworfen: zu wenig Stimme, keine Frage. · Datei mit erfundener Abtastrate: Abgelehnt, bevor die Engine sie sieht. · Engine lädt noch: Abgelehnt mit dem Grund, das Gerät sagt Bescheid.

#### Zahlen (aus dem Code)

- **50 MB** größte Aufnahme am Panel ([Schritt 2](#kn-asr-s2))
- **8000–192000** erlaubte Abtastrate in Hz ([Schritt 8](#kn-asr-s8))
- **240** Aufnahmen pro Minute und Profil ([Schritt 1](#kn-asr-s1))
- **3** Gäste gleichzeitig ([Schritt 1](#kn-asr-s1))
- **0.75** Schwelle der Sprechererkennung bei normaler Strenge ([Schritt 11](#kn-asr-s11))
- **120** Minuten Ton liest Parakeet höchstens ([Schritt 9](#kn-asr-s9))

#### Einstellen

- Einstellungen → Spracherkennung: Qwen3-ASR auf der Grafikkarte oder Parakeet auf dem Prozessor, Sprache und Kontextwörter.
- Funktionen → Sprechererkennung: Profile an der Stimme erkennen und wie streng (Standard aus).

#### Was du siehst

- Zustand → Monitoring: Zustand der Engine, Anfragen, Fehler, mittlere Dauer und die Warteschlange.
- Zustand → Logs → Anfragen: wie lange eine Aufnahme gewartet hat und wie viele sie überholt hat.

#### Im Code

- `app/panel/admin.py` `test_asr`: Ratenlimit und Plätze für Gäste ([Schritt 1](#kn-asr-s1))
- `app/panel/admin.py` `_test_asr`: der Weg im Panel: lesen, nebenbei prüfen, weiterreichen ([Schritt 2](#kn-asr-s2), [Schritt 4](#kn-asr-s4))
- `app/panel/stufe.py` `asr_level`: Stufe des Profils, nicht am geteilten Lautsprecher ([Schritt 4](#kn-asr-s4))
- `app/common.py` `BodyLimit`: Größe und Schlüssel vor dem Lesen ([Schritt 5](#kn-asr-s5))
- `app/common.py` `PrioGate`: Warten nach Vorrang ([Schritt 7](#kn-asr-s7))
- `app/common.py` `audio_rate_ok`: Abtastrate aus dem Dateikopf ([Schritt 8](#kn-asr-s8))
- `app/asr_proxy.py` `transcriptions`: der Proxy vor der Engine ([Schritt 4](#kn-asr-s4))
- `app/asr_proxy.py` `engine_status`: bereit, lädt, Fehler oder aus ([Schritt 6](#kn-asr-s6))
- `app/parakeet.py` `Recognizer`: Parakeet auf dem Prozessor ([Schritt 9](#kn-asr-s9))
- `app/panel/stille.py` `check`: Stille und Füllwörter ([Schritt 10](#kn-asr-s10))
- `app/panel/echo.py` `check`: die eigene Stimme des Spark ([Schritt 10](#kn-asr-s10))
- `app/panel/speakers.py` `identify`: wessen Stimme, nur bei klarem Treffer ([Schritt 11](#kn-asr-s11))

Selbsttests: `test_units`, `test_hardening`, `test_stufe`, `test_stille`, `test_echo`, `test_stimmabdruck`

### Sprachausgabe

Die Sprachausgabe macht aus Text Ton. Der TTS-Dienst nimmt einen Satz an, räumt ihn auf, verdeckt Geheimnisse, wählt Sprache und Stimme und gibt ihn an die Engine (Qwen3-TTS über vllm-omni), die nur auf dieser Maschine lauscht. Der Ton kommt gestreamt zurück.

**Warum:** Ein Lautsprecher im Raum sagt alles laut, was er bekommt. Passwörter und Codes dürfen dort nie gesprochen werden, und Zeichen wie Sternchen, Links oder Emojis klingen falsch. Deshalb laufen feste Regeln auf jedem Satz, egal woher er kommt: Chat, Lautsprecher, Telegram, Erinnerungen.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Satz zum Sprechen"])
  s2{{"2. Schlüssel und Größe in Ordnung?"}}
  s3{{"3. Text gültig?"}}
  s4{{"4. Engine bereit?"}}
  s5["5. Markdown weg, Geheimnisse verdeckt"]
  s6["6. Text bereinigen"]
  s7["7. Sprache, Aussprache, Zahlen"]
  s8["8. Stimme wählen"]
  s9{{"9. Gestreamt mit anderem Tempo?"}}
  s10["10. Warten nach Vorrang"]
  s11["11. Engine spricht"]
  s12(["12. Ton zurück"])
  s1 --> s2
  s2 -->|ja| s3
  s3 -->|ja| s4
  s4 -->|ja| s5
  s5 --> s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 -->|nein| s10
  s10 --> s11
  s11 --> s12
  s2x(["Abgelehnt (401 oder 413)"])
  s2 -->|nein| s2x
  s3x(["Abgelehnt (400)"])
  s3 -->|nein| s3x
  s4x(["Nicht bereit (503)"])
  s4 -->|nein| s4x
  s6x(["Abgelehnt (400)"])
  s6 -->|nichts übrig| s6x
  s9x(["Der Proxy streckt den Ton selbst"])
  s9 -->|ja| s9x
  s10x(["Besetzt (503)"])
  s10 -->|Schlange voll| s10x
```

1. <a id="kn-tts-s1"></a>**Satz zum Sprechen**: Das Panel schickt jeden Satz einer Antwort mit dem API-Schlüssel und der Stufe des Profils an den TTS-Dienst. Andere Programme dürfen das mit dem API-Schlüssel auch.
2. <a id="kn-tts-s2"></a>**Schlüssel und Größe in Ordnung?**: BodyLimit lehnt zu große Anfragen und solche ohne den richtigen Schlüssel ab, bevor etwas gelesen wird.
3. <a id="kn-tts-s3"></a>**Text gültig?**: Der Text darf nicht leer sein und höchstens 20000 Zeichen haben. Eine Vorlage-Stimme nimmt check_reference nur als eingebettete data:audio-Adresse an, nie als Link: die Engine würde einen Link sonst selbst aus dem Heimnetz holen.
4. <a id="kn-tts-s4"></a>**Engine bereit?**: Eine VoiceDesign-Anfrage geht an die zweite Engine, wenn sie eingeschaltet ist; alles andere an die Haupt-Engine. engine_status fragt deren /health und nennt sonst den Grund.
5. <a id="kn-tts-s5"></a>**Markdown weg, Geheimnisse verdeckt**: speech_markdown nimmt die Zeichen der Formatierung heraus, dann ersetzt hide_secrets Passwörter, Codewörter, Einmal-Codes und Schlüssel durch „nur schriftlich sichtbar“. Das läuft auf jeder Anfrage, auch wenn „Text bereinigen“ aus ist; die geschriebene Antwort behält den Wert.
6. <a id="kn-tts-s6"></a>**Text bereinigen**: clean_text nimmt Emojis, „haha“, *lacht*, Codeblöcke und Links heraus, beruhigt auf Wunsch Ausrufe und setzt ans Zeilenende einen Punkt, damit die Stimme absetzt. Bleibt nichts übrig, kommt keine Anfrage an die Engine.
7. <a id="kn-tts-s7"></a>**Sprache, Aussprache, Zahlen**: Steht die Sprache auf Auto, rät guess_language an häufigen Wörtern Deutsch oder Englisch, damit ein einzelnes englisches Wort nicht den Ton der ganzen Antwort ändert. Dann gilt die eigene Aussprache-Liste, danach schreibt speak_numbers Datum, Uhrzeit, Geld und Zahlen aus.
8. <a id="kn-tts-s8"></a>**Stimme wählen**: Temperatur, top_p und ein fester Seed aus den Einstellungen halten die Stimme von Satz zu Satz gleich. Ein Base-Modell spricht mit einer geklonten Stimme aus voices/ (apply_clone); ein unbekannter Name fällt auf die Standardstimme zurück.
9. <a id="kn-tts-s9"></a>**Gestreamt mit anderem Tempo?**: vllm-omni nimmt beim Streamen kein Tempo an. Dann streckt tempo.Stretcher den Ton Stück für Stück selbst (WSOLA, die Tonhöhe bleibt).
10. <a id="kn-tts-s10"></a>**Warten nach Vorrang**: PrioGate lässt so viele Sätze durch, wie die Engine gleichzeitig nimmt (engine_max_seqs); die anderen warten nach Stufe, dann nach Ankunft.
11. <a id="kn-tts-s11"></a>**Engine spricht**: Die Engine erzeugt den Ton. Gestreamt kommt er als Stücke zurück; das erste Stück ist absichtlich klein (initial_chunk_frames), damit der Ton schnell beginnt, auch wenn mehrere Anfragen laufen.
12. <a id="kn-tts-s12"></a>**Ton zurück**: Der Proxy reicht den Ton unverändert weiter und zählt nur Dauer, Länge und Fehler für das Monitoring, nie den Text.

**Beispiele:** Antwortsatz im Chat: Gesprochen, gestreamt, mit fester Stimme. · Passwort in der Antwort: Gesprochen wird „nur schriftlich sichtbar“, geschrieben bleibt der Wert. · Nur ein Emoji: Nichts zu sagen, nichts geht an die Engine. · Schneller sprechen: Der Proxy streckt den gestreamten Ton.

#### Zahlen (aus dem Code)

- **20000** Zeichen pro Anfrage höchstens ([Schritt 3](#kn-tts-s3))
- **„nur schriftlich sichtbar“** sagt die Stimme statt eines Geheimnisses ([Schritt 5](#kn-tts-s5))
- **4** Arten, Zahlen vorzulesen ([Schritt 7](#kn-tts-s7))

#### Einstellen

- Einstellungen → Sprachausgabe: Modell, Standardstimme, Sprache, Text bereinigen, Zahlen vorlesen und die eigene Aussprache-Liste.
- Einstellungen → Stimmen: eigene Stimmen aufnehmen, anhören und sichern (für ein Base-Modell).

#### Was du siehst

- Zustand → Monitoring: Zustand der Engines, Anfragen, Fehler, Zeit bis zum ersten Ton und die Warteschlange.

#### Im Code

- `app/tts_proxy.py` `speech`: der Weg eines Satzes durch den Proxy ([Schritt 1](#kn-tts-s1))
- `app/tts_proxy.py` `check_reference`: Vorlage nur eingebettet ([Schritt 8](#kn-tts-s8))
- `app/tts_proxy.py` `engine_status`: bereit, lädt, Fehler oder aus ([Schritt 4](#kn-tts-s4))
- `app/tts_proxy.py` `apply_clone`: geklonte Stimme aus voices/ ([Schritt 8](#kn-tts-s8))
- `app/textnorm.py` `speech_markdown`: Markdown-Zeichen weg ([Schritt 5](#kn-tts-s5))
- `app/textnorm.py` `hide_secrets`: Geheimnisse nie sprechen ([Schritt 5](#kn-tts-s5))
- `app/textnorm.py` `clean_text`: Emojis, Lachen, Links, Code ([Schritt 6](#kn-tts-s6))
- `app/textnorm.py` `guess_language`: Deutsch oder Englisch raten ([Schritt 7](#kn-tts-s7))
- `app/textnorm.py` `speak_numbers`: Zahlen ausschreiben ([Schritt 7](#kn-tts-s7))
- `app/tempo.py` `Stretcher`: Tempo beim Streamen ([Schritt 9](#kn-tts-s9))
- `app/common.py` `PrioGate`: Warten nach Vorrang ([Schritt 10](#kn-tts-s10))

Selbsttests: `test_units`, `test_markdown`, `test_hardening`, `test_stufe`, `test_tempo`

### Dienste draußen

Dienste draußen sind alles, was der Spark über das Netz fragt: Home Assistant, Kalender, Kontakte, Mail, SearXNG, Kiwix, reMarkable und MCP-Dienste. Adressen aus Einstellungen gehen über den Wächter (netguard) mit einer festen Stufe; feste Dienste wie SearXNG, Wetter, Fahrplan und Wikipedia gehen direkt.

**Warum:** Ein Werkzeugaufruf kommt vom Modell, und das Modell kann von fremdem Text gelenkt sein. Deshalb prüft das Panel vor jedem Aufruf mit festen Regeln, ob er sein darf, und behandelt jede Antwort von draußen als Daten.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Modell ruft ein Werkzeug"])
  s2{{"2. In dieser Runde angeboten?"}}
  s3{{"3. Notaus hält es an?"}}
  s4{{"4. Schon Text von außen gelesen?"}}
  s5{{"5. Dienst als weg bekannt?"}}
  s6{{"6. Fester eigener Weg?"}}
  s7["7. Stufe des Dienstes"]
  s8{{"8. Wächter erlaubt die Adresse?"}}
  s9["9. Anfrage an den Dienst"]
  s10{{"10. Antwort zu groß?"}}
  s11["11. Ergebnis für Mein Zustand und Live"]
  s12(["12. Antwort als Daten ans Modell"])
  s1 --> s2
  s2 -->|ja| s3
  s3 -->|nein| s4
  s4 -->|nein| s5
  s5 -->|nein| s6
  s6 -->|nein| s7
  s7 --> s8
  s8 -->|ja| s9
  s9 --> s10
  s10 -->|nein| s11
  s11 --> s12
  s2x(["Nicht angeboten"])
  s2 -->|nein| s2x
  s3x(["Gesperrt (Notaus)"])
  s3 -->|ja| s3x
  s4x(["Gesperrt nach Text von außen"])
  s4 -->|ja| s4x
  s5x(["Fester Satz: gerade nicht erreichbar"])
  s5 -->|ja| s5x
  s6 -.->|ja| s9
  s8x(["Gesperrt"])
  s8 -->|nein| s8x
  s10x(["Abbruch"])
  s10 -->|ja| s10x
```

1. <a id="kn-aussen-s1"></a>**Modell ruft ein Werkzeug**: Das Modell nennt ein Werkzeug und Angaben dazu. Wer fragt, steht schon fest (Anmeldung); die Zugangsdaten des Dienstes liegen versiegelt beim Profil und gehen nie ans Modell.
2. <a id="kn-aussen-s2"></a>**In dieser Runde angeboten?**: Nur Werkzeuge, die diese Runde angeboten hat, laufen. Ein anderer Name wird nicht ausgeführt.
3. <a id="kn-aussen-s3"></a>**Notaus hält es an?**: Der Notaus wird bei jedem Aufruf neu gelesen. Ab Stufe 1 sind die 7 Werkzeuge gesperrt, die selbst ins Internet gehen (Websuche, Wetter, Fahrplan, Wikipedia, Pakete, Seiten lesen); ab Stufe 2 oder mit „Mein Notaus“ jedes Werkzeug, das etwas ändert.
4. <a id="kn-aussen-s4"></a>**Schon Text von außen gelesen?**: Hat die Antwort schon Mails, Webseiten, Kalender, Dokumente oder ein Archiv gelesen, darf sie nichts mehr schalten, merken oder eintragen. Die Person muss das in einer neuen Nachricht selbst sagen.
5. <a id="kn-aussen-s5"></a>**Dienst als weg bekannt?**: Sieht der Dienst-Wächter den Dienst dieses Werkzeugs als weg (und ist der Hinweis an), antwortet das Werkzeug sofort mit einem festen Satz, statt zu warten. Die Websuche versucht dann das eigene Kiwix.
6. <a id="kn-aussen-s6"></a>**Fester eigener Weg?**: Das Sprachmodell, SearXNG an der eingetragenen Adresse, Wetter, Fahrplan, Wikipedia und feste Dienste wie Apple-Push laufen direkt, ohne Wächter. Welche Module das dürfen und warum, steht in netguard.DIRECT_OK; ein Selbsttest meldet jedes Modul, das direkt verbindet und dort fehlt.
7. <a id="kn-aussen-s7"></a>**Stufe des Dienstes**: Jedes Modul ruft den Wächter mit seiner festen Stufe: Home Assistant und Kiwix mit Heimnetz; Kalender, Kontakte, Aufgaben, Mail und MCP mit Nutzer; reMarkable und Seiten aus der Suche mit nur Internet. Die Stufe steht im Code, nicht in den Einstellungen.
8. <a id="kn-aussen-s8"></a>**Wächter erlaubt die Adresse?**: Der Wächter löst den Namen einmal auf und prüft jede Adresse: keine eigenen Dienste, kein 169.254, Heimnetz nur auf Stufe Heimnetz oder mit Schalter, im Notaus kein Internet. Danach verbindet er genau mit der geprüften Adresse.
9. <a id="kn-aussen-s9"></a>**Anfrage an den Dienst**: Das Panel öffnet den Zugang des Profils (Token, Passwort) erst jetzt und schickt ihn nur an die eingetragene Seite. Mail geht über IMAP mit TLS an die geprüfte Adresse.
10. <a id="kn-aussen-s10"></a>**Antwort zu groß?**: Über den Wächter wird jede Antwort an der Grenze des Moduls abgeschnitten, auch nach dem Entpacken.
11. <a id="kn-aussen-s11"></a>**Ergebnis für Mein Zustand und Live**: Ob der Dienst geantwortet oder die Anmeldung abgelehnt hat, sieht das Profil unter Ich → Mein Zustand; die Live-Seite zählt, was der Wächter erlaubt oder gesperrt hat. Inhalte gehen nirgends hin.
12. <a id="kn-aussen-s12"></a>**Antwort als Daten ans Modell**: Das Werkzeug gibt die Antwort als Daten zurück. Liest es fremden Text (Mail, Kalender, Archiv, Webseite, MCP im Lesemodus), gilt die Antwort ab jetzt als eine mit Text von außen; siehe Schritt 4.

**Beispiele:** Licht im Wohnzimmer an: Home Assistant im Heimnetz über die Stufe Heimnetz; geschaltet. · Websuche: SearXNG direkt; Seiten aus den Treffern gehen danach über den Wächter. · Notaus Stufe 1, Wetter fragen: Gesperrt, bevor irgendetwas hinausgeht. · Licht schalten nach einer Mail: Gesperrt: eine Mail darf nichts schalten.

#### Regeln

Gilt bei: [Schritt 7](#kn-aussen-s7), [Schritt 8](#kn-aussen-s8)

| Dienst | Weg | Stufe |
|---|---|---|
| Home Assistant | netguard.client | Heimnetz |
| Kiwix | netguard.client | Heimnetz |
| Kalender, Kontakte, Aufgaben | netguard.client | Nutzer |
| Mail | netguard.IMAP4_SSL | Nutzer |
| MCP-Dienste | netguard.client | Nutzer |
| reMarkable | netguard.client, nur erlaubte Hosts | nur Internet |
| SearXNG | direkt (netguard.DIRECT_OK) | – |
| Wetter, Fahrplan, Wikipedia | direkt, feste Adresse | – |
| Sprachmodell | direkt (eigener Dienst) | – |

#### Zahlen (aus dem Code)

- **20 MB** größte Antwort über den Wächter ([Schritt 10](#kn-aussen-s10))
- **2 MB** größte Antwort eines MCP-Dienstes ([Schritt 10](#kn-aussen-s10))
- **7** Werkzeuge, die ab Notaus-Stufe 1 ruhen ([Schritt 3](#kn-aussen-s3))
- **5 s** längste Probe des Dienst-Wächters ([Schritt 5](#kn-aussen-s5))

#### Einstellen

- Einstellungen → Sicherheit → Heimnetz-Adressen erlauben: Kalender, Kontakte, Mail und MCP dürfen auch ins Heimnetz (Standard aus).
- Funktionen → Agent-Funktionen → Dienste per MCP: welche Server und Werkzeuge angeboten werden.
- Funktionen → Dienst-Wächter: Ausfälle sehen, darunter der Hinweis an Nutzer, wenn ein Dienst fehlt.

#### Was du siehst

- Zustand → Live: jede Verbindung nach außen als Linie, gesperrte mit Grund.
- Ich → Mein Zustand: ob der eigene Kalender, die Mail oder Home Assistant antwortet.
- Zustand → Dienste: was gerade erreichbar ist.

#### Im Code

- `app/panel/chat_tools.py` `run`: angeboten, Notaus, Text von außen, Dienst weg ([Schritt 1](#kn-aussen-s1))
- `app/panel/notaus.py` `locked_tools`: welche Werkzeuge der Notaus sperrt ([Schritt 3](#kn-aussen-s3))
- `app/panel/notaus.py` `INTERNET_TOOLS`: Werkzeuge, die selbst ins Internet gehen ([Schritt 3](#kn-aussen-s3))
- `app/panel/dienstwacht.py` `tool_down`: fester Satz, wenn der Dienst weg ist ([Schritt 5](#kn-aussen-s5))
- `app/panel/netguard.py` `DIRECT_OK`: wer direkt verbinden darf und warum ([Schritt 6](#kn-aussen-s6))
- `app/panel/netguard.py` `client`: der Zugang über den Wächter ([Schritt 8](#kn-aussen-s8), [Schritt 9](#kn-aussen-s9), [Schritt 10](#kn-aussen-s10))
- `app/panel/netguard.py` `IMAP4_SSL`: Mail an die geprüfte Adresse ([Schritt 9](#kn-aussen-s9))
- `app/panel/homeassistant.py` `_client`: Home Assistant mit Stufe Heimnetz ([Schritt 7](#kn-aussen-s7), [Schritt 9](#kn-aussen-s9))
- `app/panel/mcp.py` `_client`: MCP-Server mit Stufe Nutzer ([Schritt 7](#kn-aussen-s7), [Schritt 9](#kn-aussen-s9), [Schritt 10](#kn-aussen-s10))
- `app/panel/chat.py` `web_search`: SearXNG direkt ([Schritt 6](#kn-aussen-s6), [Schritt 9](#kn-aussen-s9))

Selbsttests: `test_waechter_umgehung`, `test_notaus`, `test_sperre_ueberall`, `test_dienstwacht`, `test_kiwix`, `test_meinmcp`, `test_remarkable`

### state/

In state/ liegt, was für den ganzen Spark gilt und keinem Profil gehört: Schlüssel, Zugänge des Admins, Telegram-Bot, Push-Schlüssel, Lautsprecher, Zähler, Sperren und Zustände der Dienste. Geheimnisse darin sind mit dem Schlüssel des Spark versiegelt.

**Warum:** Eine Kopie der Dateien (eine Sicherung, ein Blick in den Ordner) soll keine Passwörter verraten. Und was nur auf diesem Gerät Sinn hat (Sperren, Zähler, Caches, Schlüssel), soll nicht mit einer Sicherung auf einen anderen Spark wandern.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Ein Modul merkt sich etwas"])
  s2{{"2. Ein Geheimnis dabei?"}}
  s3["3. Schlüssel des Spark holen"]
  s4["4. Versiegeln"]
  s5["5. Atomar schreiben"]
  s6["6. Lesen"]
  s7{{"7. Kommt in die Sicherung?"}}
  s8{{"8. Umzugs-Sicherung?"}}
  s9{{"9. Beim Wiederherstellen in Ordnung?"}}
  s10["10. Einsetzen mit Rückweg"]
  s11(["11. Schlüssel neu lesen"])
  s1 --> s2
  s2 -->|ja| s3
  s3 --> s4
  s4 --> s5
  s5 --> s6
  s6 --> s7
  s7 -->|ja| s8
  s8 -->|nein| s9
  s9 -->|ja| s10
  s10 --> s11
  s2 -.->|nein| s5
  s7x(["Bleibt auf diesem Gerät: Schlüssel, Sperren, Zähler, Caches"])
  s7 -->|nein| s7x
  s8x(["Mit dem Passwort öffnet der neue Spark alle Geheimnisse"])
  s8 -->|ja| s8x
  s9x(["Nichts geändert"])
  s9 -->|nein| s9x
```

1. <a id="kn-state-s1"></a>**Ein Modul merkt sich etwas**: Der Ordner state/ gehört dem Dienst-Benutzer; install.sh legt ihn an. Neue Dateien darin kann nur der Dienst lesen.
2. <a id="kn-state-s2"></a>**Ein Geheimnis dabei?**: Passwörter, Tokens und Schlüssel werden versiegelt, bevor sie gespeichert werden. Alles andere geht direkt zum Schreiben.
3. <a id="kn-state-s3"></a>**Schlüssel des Spark holen**: vault._key liest secret.key. Gibt es ihn nicht, entsteht er einmal (nur lesbar für den Dienst, nie überschrieben). Danach bleibt er im Speicher des Panels.
4. <a id="kn-state-s4"></a>**Versiegeln**: vault.seal macht aus dem Wert „enc1:“ und ein Fernet-Token (verschlüsselt und gegen Änderung geschützt). Ein schon versiegelter Wert bleibt, wie er ist.
5. <a id="kn-state-s5"></a>**Atomar schreiben**: common.write_json schreibt in eine frische Zwischendatei daneben, nie durch einen Link, gibt ihr die Rechte der alten Datei (eine neue ist nur für den Dienst lesbar) und tauscht sie dann in einem Schritt aus. Ein Absturz mittendrin lässt die alte Datei ganz.
6. <a id="kn-state-s6"></a>**Lesen**: Ein versiegelter Wert wird mit dem Schlüssel geöffnet. Passt der Schlüssel nicht (Sicherung von einem anderen Spark), kommt ein leerer Wert zurück und der Zugang muss neu eingetragen werden. Ältere unversiegelte Werte werden gelesen und beim nächsten Speichern versiegelt.
7. <a id="kn-state-s7"></a>**Kommt in die Sicherung?**: Jede Datei in state/ steht in genau einer Liste: backup.STATE_FILES (28, kommen in jede Sicherung) oder backup.STATE_LOCAL (43, mit ihrem Grund). test_technik findet jeden Namen, den der Code dort schreibt, und verlangt ihn in einer der Listen.
8. <a id="kn-state-s8"></a>**Umzugs-Sicherung?**: secret.key ist in keiner gewöhnlichen Sicherung. Nur eine Umzugs-Sicherung trägt ihn, versiegelt mit einem Passwort des Admins (scrypt und Fernet, move-keys.json). Die Anmelde-Schlüssel des Spark sind in keiner Sicherung.
9. <a id="kn-state-s9"></a>**Beim Wiederherstellen in Ordnung?**: _check_state prüft jede Datei der Sicherung: höchstens 8 MB, gültiges JSON, der Push-Schlüssel ein echter EC-Schlüssel. Ein zweiter Schritt des Admins, dessen Geheimnis sich hier nicht öffnen lässt, wird nicht übernommen; der bisherige bleibt.
10. <a id="kn-state-s10"></a>**Einsetzen mit Rückweg**: _swap schreibt jede Datei über eine Zwischendatei (nie durch einen Link) und merkt sich den alten Inhalt. Geht ein Schritt schief, kommt alles Getauschte zurück.
11. <a id="kn-state-s11"></a>**Schlüssel neu lesen**: _forget_cached lässt die Module, die einen Schlüssel im Speicher halten (vault, push, apns, chats, verbund), ihn neu lesen.

**Beispiele:** Telegram-Bot-Token eintragen: Versiegelt gespeichert, kommt in jede Sicherung. · Sperre nach Fehlversuchen: Schlicht gespeichert, bleibt auf diesem Gerät. · Umzug auf einen neuen Spark: Alle Geheimnisse öffnen sich wieder, ohne Neueingabe.

#### Zahlen (aus dem Code)

- **28** Dateien in jeder Sicherung ([Schritt 7](#kn-state-s7))
- **43** Dateien und Ordner, die mit Grund draußen bleiben ([Schritt 7](#kn-state-s7))
- **8 MB** größte Datei beim Wiederherstellen ([Schritt 9](#kn-state-s9))
- **12** Zeichen hat das Umzugs-Passwort mindestens ([Schritt 8](#kn-state-s8))

#### Einstellen

- Einstellungen → Sicherung: Sicherung jetzt, Umzugs-Sicherung mit Passwort, Wiederherstellen.

#### Was du siehst

- Zustand → Technik: die Tabelle der Speicherorte nennt jede Datei, ob sie in die Sicherung kommt und ob sie versiegelt ist.

#### Im Code

- `app/common.py` `write_json`: atomar schreiben, Rechte behalten ([Schritt 5](#kn-state-s5))
- `app/panel/vault.py` `_key`: secret.key holen oder einmal anlegen ([Schritt 3](#kn-state-s3))
- `app/panel/vault.py` `seal`: versiegeln ([Schritt 4](#kn-state-s4))
- `app/panel/vault.py` `open_`: öffnen, leer bei fremdem Schlüssel ([Schritt 6](#kn-state-s6))
- `app/panel/backup.py` `STATE_FILES`: was in die Sicherung kommt ([Schritt 7](#kn-state-s7))
- `app/panel/backup.py` `STATE_LOCAL`: was mit Grund draußen bleibt ([Schritt 7](#kn-state-s7))
- `app/panel/backup.py` `_seal_keys`: secret.key für den Umzug versiegeln ([Schritt 8](#kn-state-s8))
- `app/panel/backup.py` `_check_state`: Dateien der Sicherung prüfen ([Schritt 9](#kn-state-s9))
- `app/panel/backup.py` `_swap`: einsetzen mit Rückweg ([Schritt 10](#kn-state-s10))
- `app/panel/backup.py` `_forget_cached`: Schlüssel neu lesen ([Schritt 11](#kn-state-s11))

Selbsttests: `test_technik`, `test_hardening`, `test_panel`, `test_tempo`

### users/ID/

Jedes Profil hat seinen eigenen Ordner users/ID/: Gespräche, Gedächtnis, Aufgaben, Dokumente, Einstellungen, Zugänge und den Stimmabdruck. Welcher Ordner gilt, kommt nur aus der Anmeldung. Auf Wunsch geht eine verschlüsselte Kopie davon auf einen eigenen Speicher.

**Warum:** Was einer Person gehört, darf keine andere sehen, auch nicht über das Sprachmodell. Passwörter und der Stimmabdruck sollen auch in einer Kopie der Dateien nicht lesbar sein.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Anfrage mit Profil"])
  s2["2. Pfad im eigenen Ordner"]
  s3{{"3. Ein Geheimnis dabei?"}}
  s4["4. Schreiben nur für den Dienst"]
  s5["5. Jede Datei einsortiert"]
  s6{{"6. Eigener Speicher eingerichtet?"}}
  s7["7. Nur Geändertes der gewählten Bereiche"]
  s8["8. Verschlüsselt, Namen zufällig"]
  s9["9. Gelöschtes wartet im Papierkorb"]
  s10["10. In der Sicherung"]
  s11{{"11. Profil gelöscht?"}}
  s12(["12. Nur für dieses Profil"])
  s1 --> s2
  s2 --> s3
  s3 -->|nein| s4
  s4 --> s5
  s5 --> s6
  s6 -->|ja| s7
  s7 --> s8
  s8 --> s9
  s9 --> s10
  s10 --> s11
  s11 -->|nein| s12
  s3x(["Versiegelt mit secret.key"])
  s3 -->|ja| s3x
  s6 -.->|nein| s10
  s9x(["Später noch einmal"])
  s9 -->|Ziel weg| s9x
  s11x(["Ordner gelöscht"])
  s11 -->|ja| s11x
```

1. <a id="kn-users-s1"></a>**Anfrage mit Profil**: profiles.current findet das Profil aus dem signierten Anmelde-Cookie oder dem Geräteschlüssel. Was das Sprachmodell sagt, wählt nie ein Profil.
2. <a id="kn-users-s2"></a>**Pfad im eigenen Ordner**: Jede Datei liegt unter users/ID/ mit einem festen Namen aus dem Code. Die ID kommt aus Schritt 1, nie aus einem Text.
3. <a id="kn-users-s3"></a>**Ein Geheimnis dabei?**: Passwörter von Mail, Kalender und Speicherorten, Tokens von Home Assistant und MCP und der Schlüssel des eigenen Speichers werden mit dem Schlüssel des Spark versiegelt. Der Stimmabdruck (voice.json) ist biometrisch und wird ganz versiegelt; eine ältere offene Datei wird beim ersten Lesen versiegelt.
4. <a id="kn-users-s4"></a>**Schreiben nur für den Dienst**: profiles._write legt den Ordner so an, dass nur der Dienst hineinsieht, schreibt eine Zwischendatei, die nur der Dienst lesen kann, und tauscht sie in einem Schritt aus.
5. <a id="kn-users-s5"></a>**Jede Datei einsortiert**: Jeder Dateiname steht entweder in einem Bereich von speicher.AREAS (darf auf den eigenen Speicher) oder in speicher.LOCAL (bleibt auf dem Spark, mit Grund: Schlüssel, Zugänge, Einstellungen, Stimmabdruck, Warteschlangen). test_technik prüft jeden Namen, den der Code schreibt.
6. <a id="kn-users-s6"></a>**Eigener Speicher eingerichtet?**: Nur wenn der Admin den eigenen Speicher freigegeben hat und das Profil ein Ziel mit mindestens einem Bereich hat (höchstens 2 Ziele).
7. <a id="kn-users-s7"></a>**Nur Geändertes der gewählten Bereiche**: local_files nimmt nur Dateien der gewählten Bereiche: echte Dateien, keine Links, höchstens 5000 Stück. copy_once schickt nur, was sich seit dem letzten Lauf geändert hat, höchstens 2048 MB pro Lauf; der nächste Lauf macht weiter.
8. <a id="kn-users-s8"></a>**Verschlüsselt, Namen zufällig**: seal_file verschlüsselt jede Datei in nummerierten Stücken mit einem eigenen Schlüssel je Objekt (abgeleitet aus dem Speicher-Schlüssel des Profils und dem Objektnamen). Die Namen auf dem Ziel sind zufällig; das Ziel sieht nur Rauschen.
9. <a id="kn-users-s9"></a>**Gelöschtes wartet im Papierkorb**: Ein gelöschtes oder ersetztes Objekt bleibt 30 Tage auf dem Ziel. Ist das Ziel nicht erreichbar, ändert sich auf dem Spark nichts; der Besitzer hört nach 60 Minuten einmal davon.
10. <a id="kn-users-s10"></a>**In der Sicherung**: Die tägliche Sicherung nimmt users/ ganz mit, außer users/secret (signiert die Anmeldungen) und den Nachrichten zwischen Profilen. SQLite-Dateien werden als stimmige Kopie gepackt.
11. <a id="kn-users-s11"></a>**Profil gelöscht?**: delete_user nimmt das Profil und seine Geräte aus profiles.json und löscht den Ordner, aber nur wenn die ID genau die Form einer Profil-ID hat.
12. <a id="kn-users-s12"></a>**Nur für dieses Profil**: Jede Funktion liest nur den Ordner des angemeldeten Profils. Gäste haben keinen Ordner.

**Beispiele:** Gedächtnis-Eintrag, kein eigener Speicher: Liegt im eigenen Ordner und in der Sicherung. · Mail-Passwort eintragen: Versiegelt, bleibt auf dem Spark (Zugang). · Dokument mit eigenem Speicher: Verschlüsselte Kopie auf dem Ziel.

#### Regeln

Gilt bei: [Schritt 5](#kn-users-s5), [Schritt 7](#kn-users-s7)

| Bereich | Dateien | Eigener Speicher |
|---|---|---|
| Gespräche | convos.json, toollog.json, room-history.json | ✓ |
| Gedächtnis | memory.json, learned.json, zuordnungen.json | ✓ |
| Aufgaben und Erinnerungen | tasks.json, reminders.json | ✓ |
| Dokumente | wissen.db, docs/files/, suchpruefung.json | ✓ |
| Erstellte Dokumente | erstellt/ | ✓ |
| Zugänge, Schlüssel, Stimmabdruck | speicher.LOCAL | ✕ |

#### Zahlen (aus dem Code)

- **2** Ziele pro Profil höchstens ([Schritt 6](#kn-users-s6))
- **30** Minuten zwischen zwei Läufen ([Schritt 7](#kn-users-s7))
- **2048 MB** höchstens pro Lauf ([Schritt 7](#kn-users-s7))
- **30** Tage im Papierkorb des Ziels ([Schritt 9](#kn-users-s9))
- **5000** Dateien pro Kopie höchstens ([Schritt 7](#kn-users-s7))

#### Einstellen

- Ich → Speicher: eigene Ziele (NAS, WebDAV, SFTP, SMB) und welche Bereiche dorthin gehen.

#### Was du siehst

- Ich → Speicher: die eigenen Ziele mit Zustand und den letzten Läufen.
- Zustand → Technik: die Tabelle der Speicherorte nennt jede Datei eines Profils, ob sie mitkopiert wird und ob sie versiegelt ist.

#### Im Code

- `app/panel/profiles.py` `current`: das Profil aus Cookie oder Geräteschlüssel ([Schritt 1](#kn-users-s1))
- `app/panel/profiles.py` `_path`: Pfad im Ordner des Profils ([Schritt 2](#kn-users-s2))
- `app/panel/profiles.py` `_write`: schreiben nur für den Dienst ([Schritt 4](#kn-users-s4))
- `app/panel/profiles.py` `delete_user`: Profil und Ordner löschen ([Schritt 11](#kn-users-s11))
- `app/panel/vault.py` `seal`: versiegeln ([Schritt 3](#kn-users-s3))
- `app/panel/speakers.py` `_store`: Stimmabdruck versiegelt ([Schritt 3](#kn-users-s3), [Schritt 4](#kn-users-s4))
- `app/panel/speicher.py` `AREAS`: was auf den eigenen Speicher darf ([Schritt 5](#kn-users-s5))
- `app/panel/speicher.py` `_key`: Speicher-Schlüssel des Profils, versiegelt ([Schritt 8](#kn-users-s8))
- `app/panel/speicher.py` `local_files`: nur die Liste, keine Links ([Schritt 7](#kn-users-s7))
- `app/panel/speicher.py` `seal_file`: AES-256-GCM in Stücken ([Schritt 8](#kn-users-s8))
- `app/panel/speicher.py` `copy_once`: ein Lauf der Kopie ([Schritt 7](#kn-users-s7), [Schritt 8](#kn-users-s8))
- `app/panel/backup.py` `_add_dir`: users/ in die Sicherung ([Schritt 10](#kn-users-s10))

Selbsttests: `test_speicher`, `test_technik`, `test_stimmabdruck`, `test_hardening`

### voices/, backups/

In voices/ liegen die geklonten Stimmen (WAV und Text), in backups/ die Sicherungen des Spark. Eine Sicherung entsteht einmal am Tag von selbst, vor jedem Update und auf Knopfdruck; die ältesten fallen weg.

**Warum:** Eine Stimme oder ein ganzer Spark soll sich nach einem Fehler, einem Update oder einem Umzug zurückholen lassen. Eine Sicherung enthält alles über alle Profile, deshalb ist sie nur für den Dienst lesbar und lässt sich nur mit Code herunterladen.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Admin nimmt eine Stimme auf"])
  s2{{"2. Name erlaubt?"}}
  s3{{"3. Kein WAV?"}}
  s4["4. Ablegen"]
  s5["5. Mit der Stimme sprechen"]
  s6["6. Stimmen als ZIP"]
  s7["7. Einmal am Tag"]
  s8["8. Packen"]
  s9{{"9. Umzugs-Sicherung?"}}
  s10["10. Alte aufräumen"]
  s11["11. Herunterladen nur mit Code"]
  s12(["12. Wiederherstellen"])
  s1 --> s2
  s2 -->|ja| s3
  s3 -->|nein| s4
  s4 --> s5
  s5 --> s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 -->|nein| s10
  s10 --> s11
  s11 --> s12
  s2x(["Abgelehnt (400)"])
  s2 -->|nein| s2x
  s3x(["ffmpeg wandelt um"])
  s3 -->|ja| s3x
  s9x(["secret.key reist versiegelt mit"])
  s9 -->|ja| s9x
  s12x(["Nichts geändert"])
  s12 -->|Prüfung schlägt fehl| s12x
```

1. <a id="kn-ablage-s1"></a>**Admin nimmt eine Stimme auf**: Unter Einstellungen → Stimmen lädt der Admin eine Aufnahme hoch, mit Namen und am besten mit dem gesprochenen Text.
2. <a id="kn-ablage-s2"></a>**Name erlaubt?**: Der Name wird zum Dateinamen; deshalb nur Buchstaben, Ziffern, Unterstrich und Bindestrich. Die Aufnahme darf höchstens sechzig MB groß sein.
3. <a id="kn-ablage-s3"></a>**Kein WAV?**: Die Engine erwartet WAV. Alles andere wandelt ffmpeg in Mono-WAV um, höchstens zwei Minuten lang.
4. <a id="kn-ablage-s4"></a>**Ablegen**: Die Aufnahme wird voices/Name.wav, der Text voices/Name.txt. Ohne Text nutzt die Engine nur die Klangfarbe.
5. <a id="kn-ablage-s5"></a>**Mit der Stimme sprechen**: Ist ein Base-Modell eingestellt, liest der TTS-Dienst die Stimme als eingebettete Aufnahme (apply_clone) und merkt sie sich, bis sich die Datei ändert.
6. <a id="kn-ablage-s6"></a>**Stimmen als ZIP**: Ein Import nimmt nur flache Name.wav und Name.txt, prüft die Größe jeder Datei, bevor etwas entpackt wird, und benennt bei Gleichstand um, überschreibt oder überspringt, wie gewählt.
7. <a id="kn-ablage-s7"></a>**Einmal am Tag**: Das Panel schaut jede Stunde, ob die letzte Sicherung älter als ein Tag ist. Dann packt es in einer Pause (vorrang.in_thread), mit niedriger Priorität. Dazu kommen Sicherungen vor jedem Update, Zurücksetzen und Wiederherstellen.
8. <a id="kn-ablage-s8"></a>**Packen**: backup.create schreibt in backups/ (nur für den Dienst) erst eine .part-Datei, dann den fertigen Namen: backup.json, users/ ohne users/secret und Nachrichten, voices/, config.json, das Panel-Passwort und die Dateien aus STATE_FILES. SQLite-Dateien kommen als stimmige Kopie hinein.
9. <a id="kn-ablage-s9"></a>**Umzugs-Sicherung?**: Mit einem Passwort (12 bis 200 Zeichen) trägt die Sicherung auch secret.key, versiegelt mit diesem Passwort. Nur der Haupt-Admin mit frischem Code kann sie anlegen.
10. <a id="kn-ablage-s10"></a>**Alte aufräumen**: _prune behält die neuesten 7 täglichen und manuellen Sicherungen und die neuesten 5 anderen (Update, Wiederherstellen, Umzug). So verdrängen ein paar Updates nie die täglichen.
11. <a id="kn-ablage-s11"></a>**Herunterladen nur mit Code**: Eine Sicherung enthält alle Profile. Der Browser holt mit dem Code ein Ticket, das eine Minute gilt und einmal benutzbar ist, und lädt damit die Datei.
12. <a id="kn-ablage-s12"></a>**Wiederherstellen**: restore entpackt nur bekannte Pfade, höchstens 8192 MB und nur bei genug freiem Platz, prüft die Einstellungen wie die Einstellungsseite, legt eine Sicherung des jetzigen Stands an und tauscht dann users/, voices/, Einstellungen und state-Dateien, mit Rückweg bei einem Fehler.

**Beispiele:** Stimme aus einer m4a-Datei: Als WAV abgelegt, das Base-Modell spricht damit. · Tägliche Sicherung: Neue Sicherung, die älteste tägliche fällt weg. · Umzug auf einen neuen Spark: Alles kommt mit, auch die Geheimnisse. · Kaputte Datei hochgeladen: Abgelehnt, am Spark ändert sich nichts.

#### Regeln

Gilt bei: [Schritt 8](#kn-ablage-s8)

| Teil | In der Sicherung | Warum |
|---|---|---|
| users/ | ✓ | ohne users/secret und Nachrichten zwischen Profilen |
| voices/ | ✓ | geklonte Stimmen |
| config.json | ✓ | Geheimnisse darin versiegelt |
| state/ | nur STATE_FILES und panel-password | der Rest gilt nur hier |
| secret.key | nur Umzugs-Sicherung | versiegelt mit Passwort |

#### Zahlen (aus dem Code)

- **7** tägliche und manuelle Sicherungen bleiben ([Schritt 10](#kn-ablage-s10))
- **5** Ereignis-Sicherungen bleiben ([Schritt 10](#kn-ablage-s10))
- **2048 MB** größte hochgeladene Sicherung ([Schritt 12](#kn-ablage-s12))
- **8192 MB** entpackt höchstens ([Schritt 12](#kn-ablage-s12))
- **12–200** Zeichen des Umzugs-Passworts ([Schritt 9](#kn-ablage-s9))

#### Einstellen

- Einstellungen → Stimmen: eigene Stimmen aufnehmen, anhören, als ZIP sichern und einspielen.
- Einstellungen → Sicherung: Sicherung jetzt, Umzugs-Sicherung, herunterladen, wiederherstellen und die verschlüsselte Kopie nach außen.

#### Was du siehst

- Einstellungen → Sicherung: die Liste der Sicherungen mit Zeit, Größe und Anlass.
- Zustand → Logs → Diagnose, Bereich Speicher: jede tägliche Sicherung und jeder Fehler.

#### Im Code

- `app/panel/admin.py` `add_clone_voice`: Stimme prüfen, umwandeln, ablegen ([Schritt 1](#kn-ablage-s1), [Schritt 2](#kn-ablage-s2), [Schritt 4](#kn-ablage-s4))
- `app/panel/admin.py` `import_clone_voices`: Stimmen aus einem ZIP ([Schritt 6](#kn-ablage-s6))
- `app/tts_proxy.py` `apply_clone`: mit der Stimme sprechen ([Schritt 5](#kn-ablage-s5))
- `app/panel/panel.py` `stability`: tägliche Sicherung in einer Pause ([Schritt 7](#kn-ablage-s7))
- `app/panel/backup.py` `create`: eine Sicherung packen ([Schritt 8](#kn-ablage-s8))
- `app/panel/backup.py` `_add_dir`: Ordner ohne Anmelde-Schlüssel ([Schritt 8](#kn-ablage-s8))
- `app/panel/backup.py` `_prune`: alte aufräumen ([Schritt 10](#kn-ablage-s10))
- `app/panel/system.py` `backup_ticket`: Einmal-Ticket zum Herunterladen ([Schritt 11](#kn-ablage-s11))
- `app/panel/backup.py` `_check`: nur bekannte Pfade, Größe, Platz ([Schritt 12](#kn-ablage-s12))
- `app/panel/backup.py` `restore`: prüfen, sichern, tauschen ([Schritt 12](#kn-ablage-s12))

Selbsttests: `test_panel`, `test_hardening`, `test_offsite`

### journald

Alle Dienste des Spark schreiben ihre Zeilen in einen eigenen Bereich des Systemjournals (Namespace speech-spark), mit eigener Grenze für Platz und Alter. Das Panel liest diese Zeilen nur für den Admin, schwärzt Geheimnisse und ordnet sie nach festen Wörtern.

**Warum:** Logs sollen zeigen, was passiert, ohne zu verraten, was jemand gefragt hat. Und ein gesprächiger Dienst darf weder die Platte füllen noch die anderen Logs des Systems verdrängen.

#### Ablauf

```mermaid
flowchart TD
  s1(["1. Ein Dienst schreibt eine Zeile"])
  s2["2. Feste Wörter und Zahlen"]
  s3{{"3. Ausführlich an?"}}
  s4["4. Abfragen still"]
  s5["5. Eigener Bereich mit Grenze"]
  s6["6. Admin öffnet die Diagnose"]
  s7{{"7. Filter aus der festen Liste?"}}
  s8["8. Journal lesen"]
  s9["9. Geheimnisse schwärzen"]
  s10["10. Bereich und Stufe nach Regeln"]
  s11["11. Zählen und Hinweis"]
  s12(["12. Zeilen ans Panel"])
  s1 --> s2
  s2 --> s3
  s3 -->|nein| s4
  s4 --> s5
  s5 --> s6
  s6 --> s7
  s7 -->|ja| s8
  s8 --> s9
  s9 --> s10
  s10 --> s11
  s11 --> s12
  s3x(["Zusätzliche Zeilen mit Zahlen"])
  s3 -->|ja| s3x
  s7x(["Abgelehnt (400)"])
  s7 -->|nein| s7x
```

1. <a id="kn-journal-s1"></a>**Ein Dienst schreibt eine Zeile**: Panel, ASR, TTS, Engines und Wächter schreiben mit print. systemd gibt die Zeile an das Journal; jede Einheit hat LogNamespace=speech-spark.
2. <a id="kn-journal-s2"></a>**Feste Wörter und Zahlen**: Jede Zeile des Panels beginnt mit einem Wort aus logfilter.AREAS (28 Bereiche) und trägt nur feste Wörter und Zahlen. Ein Profil steht dort nur über profiles.log_name: sein Name nur mit seiner Zustimmung, sonst „Profil“ und das Ende der ID. test_log_luecken verlangt für jede Aktion eine Zeile je Ergebnis.
3. <a id="kn-journal-s3"></a>**Ausführlich an?**: Für einige Bereiche kann der Admin zusätzliche Zeilen einschalten, höchstens 240 Minuten. Auch sie tragen nur Zahlen und Entscheidungen; ein Neustart schaltet sie aus.
4. <a id="kn-journal-s4"></a>**Abfragen still**: Erfolgreiche Statusabfragen, die das Panel alle paar Sekunden stellt, schreiben keine Zeile.
5. <a id="kn-journal-s5"></a>**Eigener Bereich mit Grenze**: install.sh schreibt die Grenze für Platz und Alter aus logs.max_mb und logs.keep_days. Ältere Zeilen löscht journald selbst. Eine Änderung wirkt nach dem nächsten Update oder install.sh.
6. <a id="kn-journal-s6"></a>**Admin öffnet die Diagnose**: Nur der Admin, höchstens 60 Abrufe pro Minute.
7. <a id="kn-journal-s7"></a>**Filter aus der festen Liste?**: Bereiche, Zeitfenster (bis 24 Stunden) und Zeilenzahl (bis 1000) kommen nur aus festen Listen. Nichts, was der Browser schickt, erreicht eine Shell.
8. <a id="kn-journal-s8"></a>**Journal lesen**: read_journal fragt journalctl mit dem Namespace, bei alten Installationen ohne ihn das System-Journal. Höchstens 20000 Zeilen und 2 MB Text.
9. <a id="kn-journal-s9"></a>**Geheimnisse schwärzen**: redact ersetzt Telegram-Tokens, Bearer-Schlüssel, key=, token=, password= und Anmeldungen in Adressen durch Sternchen, bevor eine Zeile das Panel verlässt.
10. <a id="kn-journal-s10"></a>**Bereich und Stufe nach Regeln**: parse ordnet jede Zeile nach ihrem ersten Wort einem Bereich zu. Fehler und Warnungen erkennt es an festen Wörtern; bei Web-Anfragen zählt nur der Statuscode, bei Update-Zeilen nie der Betreff.
11. <a id="kn-journal-s11"></a>**Zählen und Hinweis**: summary zählt je Bereich und Stufe, zeichnet einen kleinen Verlauf und hängt an den neuesten Fehler einen festen Hinweis mit Weg.
12. <a id="kn-journal-s12"></a>**Zeilen ans Panel**: Das Panel zeigt die neuesten passenden Zeilen. Sie liegen nur im Journal dieses Spark, nie in einer Sicherung.

**Beispiele:** Fehler der Websuche ansehen: Zeile im Bereich Suche mit festem Hinweis. · Zeitfenster aus dem Browser verändert: Abgelehnt, journalctl wird nicht gefragt. · Speicher-Lauf eines Profils: Zeile „speicher: lauf …“ mit Zahlen, das Profil nur als Kürzel.

#### Zahlen (aus dem Code)

- **28** Bereiche der Diagnose ([Schritt 2](#kn-journal-s2))
- **20000** Zeilen pro Abruf höchstens gelesen ([Schritt 8](#kn-journal-s8))
- **2 MB** Journal-Text pro Abruf höchstens ([Schritt 8](#kn-journal-s8))
- **1000** Zeilen höchstens angezeigt ([Schritt 7](#kn-journal-s7))
- **240** Minuten „Ausführlich“ höchstens ([Schritt 3](#kn-journal-s3))

#### Einstellen

- In den Einstellungen unter Betrieb, Abschnitt Logs: wie viel Platz das Journal höchstens nimmt und wie lange es Zeilen aufbewahrt (wirkt nach dem nächsten Update).

#### Was du siehst

- Zustand → Logs → Diagnose: Filter nach Bereich, Zähler, kleiner Verlauf und der neueste Fehler mit Hinweis.
- Zustand → Logs: die letzten Zeilen jedes Dienstes.

#### Im Code

- `app/panel/logfilter.py` `AREAS`: die festen Bereiche ([Schritt 2](#kn-journal-s2))
- `app/panel/logfilter.py` `logfilter`: der Abruf: nur feste Listen ([Schritt 6](#kn-journal-s6))
- `app/panel/logfilter.py` `read_journal`: Namespace zuerst, Grenzen ([Schritt 8](#kn-journal-s8))
- `app/panel/logfilter.py` `redact`: Geheimnisse schwärzen ([Schritt 9](#kn-journal-s9))
- `app/panel/logfilter.py` `parse`: Bereich und Stufe ([Schritt 10](#kn-journal-s10))
- `app/panel/logfilter.py` `summary`: Zähler, Verlauf, Hinweis ([Schritt 11](#kn-journal-s11))
- `app/panel/logfilter.py` `detail`: Ausführlich, nur Zahlen ([Schritt 12](#kn-journal-s12))
- `app/common.py` `JOURNAL_NAMESPACE`: der eigene Bereich ([Schritt 5](#kn-journal-s5))
- `app/common.py` `journal`: letzte Zeilen eines Dienstes ([Schritt 1](#kn-journal-s1))
- `app/common.py` `quiet_access_log`: Statusabfragen still ([Schritt 4](#kn-journal-s4))
- `app/panel/profiles.py` `log_name`: Profil nur mit Zustimmung beim Namen ([Schritt 2](#kn-journal-s2))

Selbsttests: `test_logfilter`, `test_log_luecken`
<!-- /technik:knoten -->

## So bleibt die Doku aktuell

Bei jeder Änderung gilt (Richtlinie Teil 1, Punkt „Technik-Doku“):

1. Ein neues Modul bekommt seine Gruppe und eine Zeile in `technik.MODULE`.
2. Eine neue Datei unter `state/` kommt in `backup.STATE_FILES` (gesichert) oder `backup.STATE_LOCAL` (mit Grund, warum nicht), dazu ihre Zeile in `technik.INHALT`. Eine neue Datei unter `users/ID/` kommt in `speicher.AREAS` oder `speicher.LOCAL` und in `technik.INHALT`. Ist sie versiegelt, kommt sie in `technik.VERSCHLUESSELT`.
3. Ändert sich der Weg einer Anfrage, werden `technik.KNOTEN`, `KANTEN` und `SCHRITTE` angepasst.
4. Danach `python3 app/panel/hilfe.py --docs` ausführen. Das schreibt diese Seite, die englische Fassung und den Hilfe-Index neu.

5. Ändert sich, wie ein Kasten arbeitet, wird seine Seite in `technik_knoten.SEITEN_DATEN` im selben Commit angepasst. Jede Seite trägt einen Fingerabdruck (`stand`) des Codes, den sie beschreibt; ändert sich dieser Code, wird `test_technik` rot, bis die Seite geprüft und der neue Fingerabdruck eingetragen ist. Der Test nennt ihn.

`test_technik` prüft alle fünf Punkte.
