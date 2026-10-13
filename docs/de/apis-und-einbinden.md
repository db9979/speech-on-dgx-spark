# APIs und Einbinden

← [README](../../README.de.md)

## APIs (OpenAI-ähnlich)

```bash
# Transkription
curl http://SPARK:31001/v1/audio/transcriptions -F file=@aufnahme.webm -F language=de
# -> {"text": "...", "usage": {"type": "duration", "seconds": 4}, "processing_s": 0.6}

# Sprachausgabe
curl http://SPARK:31002/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"Hallo Welt","voice":"ryan","language":"German"}' -o hallo.mp3
```

`GET /health` liefert bei beiden Diensten Status und Zähler, `GET /v1/voices` (TTS) die verfügbaren Stimmen, `GET /v1/models` das geladene Modell.

Die Spracherkennung nimmt alles, was ffmpeg lesen kann (wav, mp3, webm, mp4, ogg …), und lange Aufnahmen. `language` als Code (`de`) oder Name (`German`), ohne Angabe erkennt das Modell die Sprache selbst. `response_format`: `json`, `text` oder `verbose_json` (mit `language` und `duration`, ohne Zeitstempel). Mit `-F stream=true` kommt der Text stückweise als Server-Sent Events im OpenAI-Format (`transcription.chunk`, am Ende `[DONE]`).

### Gestreamte Sprachausgabe

Mit `"stream": true` (und `"response_format": "pcm"`, das ist dann der Standard) kommt die Antwort als Server-Sent Events, sobald die ersten Laute erzeugt sind:

```
event: speech.audio.delta
data: {"type": "speech.audio.delta", "audio": "<base64>", "response_format": "pcm"}
...
event: speech.audio.done
data: {"type": "speech.audio.done", "usage": {...}}
```

`audio` ist PCM, 16 bit, mono, 24 kHz. Bei einem Fehler kommt `speech.audio.error`. Das ist das Format von vllm-omni, der Dienst reicht es unverändert durch.

```bash
curl -N http://SPARK:31002/v1/audio/speech -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"input":"Hallo Welt","voice":"ryan","language":"German","stream":true,"response_format":"pcm"}'
```

**Gleichmäßigere Aussprache:** Qwen würfelt mit `temperature` 0.9 und `top_p` 1.0, dadurch schwanken Tempo und Betonung von Satz zu Satz. Der Server setzt deshalb `temperature` 0.7, `top_p` 0.9 und `seed` 42 (Einstellungen → Sprachausgabe). Pro Anfrage überschreibbar mit denselben Feldern. In Open WebUI „Antwort aufteilen“ auf **Absätze** stellen: Jeder Teil wird einzeln erzeugt, längere Teile klingen zusammenhängender. Standardsprache fest auf „German“ stellen statt „auto“.

**Lachen und Stimmungswechsel:** Das Modell liest Emojis, „haha“, `*lacht*` und Markdown als Hinweise und lacht dann oder wechselt den Ton. Der Server entfernt das vor dem Sprechen (Einstellungen → Sprachausgabe → „Text bereinigen“, Standard an).

**Zu viel Gefühl:** Ausrufezeichen und Ausrufe („Oh“, „Wow“) lassen die Stimme Begeisterung spielen. Mit „Ruhig sprechen lassen“ (Standard an) macht der Server aus „!“ einen Punkt und streicht solche Ausrufe am Satzanfang. Die Standard-Systemanweisung des Sprach-Chats bittet das LLM außerdem um schlichte, ruhige Alltagssprache.

**Zahlen:** Der Server schreibt Zahlen vor dem Sprechen aus, weil das Modell sonst rät. Datum, Uhrzeit, Geldbeträge, Prozent und Kommazahlen werden zu Wörtern („am 06.10.2026 um 9:30 Uhr, 49,90 €“ → „am sechsten Oktober zweitausendsechsundzwanzig um neun Uhr dreißig, neunundvierzig Euro neunzig“), Telefonnummern zu Zweierblöcken. Einstellungen → Sprachausgabe → „Zahlen vorlesen“: als Wörter (Standard), in Zweierblöcken, Ziffer für Ziffer oder unverändert. Funktioniert für Deutsch und Englisch.

**Sprechstil** (wie die Stimme spricht): `"instructions": "ruhig und freundlich, eher langsam"` in der Anfrage. Ohne Angabe gilt die Standard-Anweisung aus Einstellungen → Sprachausgabe. Beispiele: „Begeistert, etwas schneller“, „Sachlich wie eine Nachrichtensprecherin“, „Leise und beruhigend“. Nur die 1.7B-Modelle (CustomVoice, VoiceDesign) werten Anweisungen aus; die 0.6B-Modelle ignorieren sie (laut Qwen-Modellkarte).

**VoiceDesign** (Stimme per Beschreibung): `"task_type": "VoiceDesign"` und `"instructions": "tiefe, ruhige Männerstimme"`. Dafür braucht es ein eigenes Modell. Im Panel unter Einstellungen → Sprachausgabe „VoiceDesign zusätzlich bereitstellen“ einschalten. Das startet eine zweite Engine mit nochmal demselben Speicherbedarf.

Im Panel unter **Zustand → Prüfen** spielt „gestreamt“ den Ton schon während der Erzeugung ab und zeigt die Zeit bis zum ersten Ton.

### Allgemein

Die Dienste verhalten sich wie die OpenAI-Audio-API: TTS liefert standardmäßig mp3 (auch wav, flac, opus, pcm), STT versteht `response_format=text`, und die Sprache darf ein ISO-Code wie `de` sein. OpenAI-Stimmnamen wie `alloy` landen bei der Standardstimme. Ist im Panel ein API-Schlüssel gesetzt, müssen Apps `Authorization: Bearer <Schlüssel>` senden.

### Open WebUI

Admin-Panel → Einstellungen → Audio:

| Feld | STT | TTS |
|---|---|---|
| Engine | OpenAI | OpenAI |
| API Base URL | `http://SPARK:31001/v1` | `http://SPARK:31002/v1` |
| API Key | Schlüssel aus dem Panel (Einstellungen → Sicherheit → API-Schlüssel; der Installer setzt immer einen) | dito |
| Modell | beliebig | beliebig |
| Stimme | | z. B. `ryan` |

Läuft Open WebUI in Docker auf derselben Spark, statt `SPARK` entweder die LAN-IP oder `host.docker.internal` nehmen (Container mit `--add-host=host.docker.internal:host-gateway`). Das Panel zeigt diese Werte unter Personen und Geräte → Apps und Schnittstellen zum Kopieren an.

### KI-Agenten: Hermes Agent und OpenClaw

Ein Agent wie [Hermes Agent](https://hermes-agent.nousresearch.com) (Nous Research) oder [OpenClaw](https://docs.openclaw.ai) kann die Spracherkennung und Sprachausgabe der Spark nutzen. Der Agent läuft auf einem anderen Rechner und bekommt nur Audio und Vorlesetext, keinen Zugang zu Profilen, Gedächtnis oder Werkzeugen des Assistenten. Das Panel zeigt die fertigen Bausteine unter Personen und Geräte → Apps und Schnittstellen zum Kopieren.

Hermes Agent, `~/.hermes/config.yaml`:

```yaml
stt:
  enabled: true
  provider: openai
  language: de
  openai: {base_url: "http://SPARK:31001/v1", api_key: "SCHLÜSSEL", model: "qwen3-asr"}
tts:
  provider: openai
  openai: {base_url: "http://SPARK:31002/v1", api_key: "SCHLÜSSEL", model: "qwen3-tts", voice: "ryan"}
```

OpenClaw: `tts.provider: "openai"` mit `tts.providers.openai.baseUrl` = `http://SPARK:31002/v1` (dazu `apiKey`, `model`, `speakerVoice`, `responseFormat: "mp3"`), und für Sprachnachrichten ein Eintrag in `tools.media.models` mit `provider: "openai"`, `baseUrl` = `http://SPARK:31001/v1` und `capabilities: ["audio"]`; den Schlüssel als OpenAI-API-Key-Profil hinterlegen.

Den Agenten nicht auf der Spark selbst installieren: Er führt Befehle aus und käme an Einstellungen und Schlüssel. Ohne API-Schlüssel kann jeder im Heimnetz die Sprachdienste nutzen.

### Spark als MCP-Server

Andere Programme nutzen den Spark über das [Model Context Protocol](https://modelcontextprotocol.io) (Streamable HTTP, Adresse `/mcp` des Panels, z. B. `http://SPARK:31080/mcp`). Standardmäßig aus.

**Einschalten:** Admin: Funktionen → *Spark als MCP-Server*. Profil: Ich → *Dienste per MCP* → „Spark als MCP-Server für mich“, dann „Programm mit Schlüssel verbinden“: Name, Werkzeuge, „Schlüssel erzeugen“. Der Schlüssel ist nur einmal sichtbar; im Programm als Header `Authorization: Bearer <Schlüssel>` eintragen.

| Gruppe | Werkzeuge |
|---|---|
| Sprache | `transcribe` (Audio als base64, höchstens 10 MB), `speak` (Text bis 2000 Zeichen, Antwort mp3), `voices` |
| Lesen | `wikipedia`, `archive_search` (Kiwix), `document_search`, `calendar_events`, `reminder_list`, `today` |
| Spark fragen | `ask_spark`: der Assistent des Profils, nur mit den Lesewerkzeugen dieses Zugangs |
| Handeln mit Bestätigung | `home_assistant`, `reminder_set`, `calendar_add`, `action_status` (eigener Admin-Schalter) |

**Regeln (fest, nicht abschaltbar):**
- Jeder Zugang gehört zu einem Profil und kann nur die Werkzeuge, die das Profil ihm gegeben hat und gerade selbst nutzen darf. Nie nach außen: Mails, Gedächtnis, frühere Gespräche, Geheimnisse, Einstellungen.
- „Nur im Heimnetz“ (Standard): Der Schlüssel gilt nur, wenn die Anfrage direkt aus dem LAN kommt, ohne Proxy-Kopfzeilen und nicht von einem eingetragenen Reverse-Proxy.
- `ask_spark`: Die Frage gilt als Text von außen. Nichts wird geschaltet, gespeichert, gelernt, gesendet oder vorgeschlagen; nichts davon landet in den Gesprächen.
- Handeln: Ein Programm legt nur einen Vorschlag an. Das Profil bekommt eine Mitteilung und entscheidet unter Ich → Dienste per MCP („Ja, ausführen“ mit Code-Fenster, oder „Nein“). Ein Vorschlag wartet 15 Minuten.
- Grenzen: 60 Aufrufe pro Minute und Zugang (`ask_spark` 10), 2 gleichzeitig pro Zugang, 6 insgesamt; Sprache läuft mit der Stufe „hinten“, Menschen am Spark gehen vor. Ohne Nutzung endet ein Zugang nach 90 Tagen.
- Das Journal zeigt jede Anfrage als `mcp-server:` mit Programm, Werkzeug und Dauer, nie den Inhalt.
- Zustand → Live (seit V01.0.334) zeigt jeden Werkzeug-Aufruf als eigene Anfrage „MCP-Client“ mit Werkzeug und Ziel (Sprache als Hören oder Sprechen, ein Vorschlag als „Bestätigung anfragen“ → Push, eine bestätigte Aktion als eigene Anfrage); der Name des Zugangs erscheint nur mit der Zustimmung des Profils („Mein Name im Anfragen-Log“), Inhalte nie. `ask_spark` erscheint wie ein Gespräch.

**Von außen (OAuth):** Admin: *MCP-Server von außen* unter dem Schalter. Ein Zugang „von außen“ braucht den zweiten Anmeldeschritt des Profils und einen frischen Code. Programme wie claude.ai melden sich per OAuth 2.1 an (dynamische Registrierung, PKCE S256, `/.well-known/oauth-authorization-server`): Im Programm einen eigenen MCP-Connector mit `https://dein-proxy/mcp` anlegen, das Programm schickt dich ins Panel, dort Warnhinweis, Werkzeuge wählen, mit Code bestätigen. Zugriffstoken gelten 1 Stunde, Erneuerungstoken 30 Tage und werden bei jeder Nutzung getauscht. Alles, was ein solches Programm liest, geht an dessen Anbieter.

**Beispiele:** Open WebUI: Einstellungen → Externe Werkzeuge → „+“, Typ MCP (Streamable HTTP). n8n: Knoten „MCP Client Tool“. Programme ohne Header-Feld: `npx mcp-remote http://SPARK:31080/mcp --header "Authorization: Bearer <Schlüssel>"`.

### Eigene MCP-Dienste pro Profil

Seit V01.0.363 (Plan `plaene/eigene-mcp-dienste.md`) bindet jedes Profil eigene MCP-Dienste an (Streamable HTTP), zusätzlich zu denen, die der Admin für alle anbindet. Nur dieses Profil sieht und nutzt sie.

**Einschalten:** Admin: Funktionen → Agent-Funktionen → Dienste per MCP → *Eigene MCP-Dienste für Profile* (`chat.mcp_own`), darunter *… auch in Hintergrundaufträgen* (`chat.mcp_own_jobs`) und *… mit Anmeldung (OAuth)* (`chat.mcp_own_oauth`); alle aus. Profil: Ich → *Meine MCP-Dienste* → „Eigene MCP-Dienste für mich“ (`mymcp_on`), dann Name, Adresse und Schlüssel eintragen und „Dienst anbinden“. Eine Agent-Stufe braucht das Profil dafür nicht.

**Regeln (fest):**
- Höchstens 5 Dienste pro Profil, je höchstens 30 Werkzeuge. Jedes Werkzeug steht auf „Aus“, bis das Profil es auf „Lesen“ oder „Handeln mit Ja“ stellt. Ändert der Dienst Beschreibung oder Eingaben eines Werkzeugs, steht es nach „Werkzeuge neu abrufen“ wieder auf „Aus“.
- Nie für Gäste, nie für andere Profile, nie für eine fremde Stimme am Lautsprecher (nur wenn die Spracherkennung sicher die eigene Stimme gehört hat), über Telegram nur mit „private Daten“.
- Dienst anbinden, neue Adresse, neuer Schlüssel: nur im eigenen Browser-Login mit frischem Code (zweiter Anmeldeschritt, wenn eingerichtet). Eine neue Adresse braucht immer einen neuen Schlüssel; alle Werkzeuge stehen dann wieder auf „Aus“. Schlüssel und Anmeldedaten liegen verschlüsselt (vault), werden nie zurückgegeben und nie ins Log geschrieben.
- Verbindungen über den Wächter (`netguard.USER`): öffentliche Adressen mit https; Heimnetz-Adressen (auch http) nur, wenn der Admin sie unter Sicherheit erlaubt; die Dienste des Spark selbst (Ports 30000–31099) nie.
- „Lesen“: Die Antwort ist fremder Text (eingerahmt, danach schaltet und speichert der Assistent in dieser Antwort nichts, nie gelernt). „Handeln mit Ja“: nur ein Vorschlag; ausgeführt nach einem schlichten „Ja“ in der nächsten Nachricht vom selben Gerät und Gespräch, 15 Minuten lang, nie nach fremdem Text, nie in Hintergrundaufträgen, nicht bei Notaus Stufe 2 oder Mein Notaus.
- Grenzen: 30 Sekunden pro Aufruf, höchstens 2 MB lesen, 8000 Zeichen ans Modell, Angaben höchstens 4000 Zeichen, 10 Aufrufe pro Minute und 2 gleichzeitig pro Profil.
- Hintergrundaufträge (mit Admin-Schalter und Haken am Dienst): nur lesende Werkzeuge, nur in Aufträgen mit privaten Daten.
- Anmeldung (OAuth): Will der Dienst eine Anmeldung, den Schlüssel leer lassen und „Beim Dienst anmelden“ tippen. Der Spark liest die Anmelde-Adressen des Dienstes (Protected Resource Metadata, Authorization Server Metadata), meldet sich dort als Programm an (dynamische Registrierung, PKCE S256, `resource`), der Browser meldet sich beim Dienst an und kommt über `/api/mymcp/back` zurück (diese Adresse ändert nichts, sie reicht Code und Kennung an die angemeldete Seite weiter, 10 Minuten, einmal). Zugang und Erneuerungs-Token liegen verschlüsselt; vor dem Ablauf erneuert der Spark den Zugang selbst.

**Admin:** Personen und Geräte → Apps und Schnittstellen → *Eigene MCP-Dienste der Profile*: Profil, Name, Adresse (nur der Host), Zahl der freigegebenen Werkzeuge, zuletzt abgerufen, nie ein Schlüssel. „Sperren“ gilt sofort und auch, wenn das Profil den Dienst neu anbindet; „Entfernen“ löscht ihn samt Schlüssel. Optional eine Liste erlaubter Adressen (leer: alle öffentlichen; ein Eintrag erlaubt auch seine Unteradressen).

**Sichtbar:** Zustand → Live zeigt jeden Aufruf als Schritt zum Ziel „MCP-Dienste“ und unter Ereignisse „MCP: Dienst · Host · ok oder Fehler · Dauer“, dazu angebunden, entfernt, angemeldet, gesperrt; nie Frage, Angaben oder Antwort, nie den Profilnamen. Ich → Mein Zustand zeigt eine Zeile pro Dienst (antwortet, Anmeldung nötig, gesperrt). Die Entscheidungen des Wächters stehen wie immer unter Live.

### „Hey Siri, frag Spark“

Ein iPhone-Kurzbefehl schickt die diktierte Frage an `POST /api/siri/ask` (Header `X-Speech-Device` mit
einem Geräteschlüssel deines Profils, Inhalt `{"text": "..."}`) und lässt Siri das Feld `answer`
vorlesen. Geht ohne geöffnete Seite, auch auf der Apple Watch, mit AirPods und mit CarPlay; Nachfragen
innerhalb von 10 Minuten kennen den Zusammenhang, die Fragen eines Tages stehen als Gespräch im Profil.
Schritt für Schritt unter Funktionen → Anleitungen.

### iPhone-App „Spark“

Eigene App fürs iPhone mit Spark-Stimme und „Hey Siri, Frag Spark“, Kopplung per QR-Code, eigener Schlüssel pro iPhone, der nur fragen und hören darf. Bauen, Koppeln und Sicherheit: [iphone-app.md](iphone-app.md).

### Chats zwischen Profilen (für die iPhone-App)

Seit V01.0.488 gehen Nachrichten zwischen Profilen nur noch über die Chats; `/api/messages…` gibt es nicht mehr. Mit der Browser-Anmeldung des Profils oder dem Schlüssel der iPhone-App (Header `X-Speech-Device`), nur wenn der Admin „Chats“ und das Profil „Chats mit anderen“ eingeschaltet hat; andere Geräteschlüssel bekommen 403.
- `GET /api/chats`: `enabled`, `on`, `chats` (je `id, kind, title, unread, mute, last`, die Gruppe „Alle“ mit `fixed`), `contacts` (`id, name, call`), `all` (nimmt an „Alle“ teil), `speakers` (für Durchsagen), `max_text`.
- `POST /api/chats/open {"to": "<Profil-id>"}` liefert die `id` des Chats zu zweit; `POST /api/chats/send {"id", "text"}` schreibt hinein (in „Alle“ höchstens 5 pro Stunde).
- `POST /api/chats/announce {"speakers": [id], "text"}`: Durchsage auf gewählten Lautsprechern (Admin-Schalter „Durchsagen auf Lautsprechern“).
- Nur im Browser: `GET`/`PUT /api/chats/who {"allow"?, "block"?}` („Wer darf mir schreiben“) und `PUT /api/chats/call {"call"}` (eigener Rufname, eindeutig). Admin: `GET /api/admin/profiles?q=&show=&sort=&page=&per=` (höchstens 100 pro Seite), `GET /api/admin/profiles/<id>`, `PUT /api/admin/profiles/<id>/call`.

### Pebble-Uhr

Die Watch-App „Spark“ (`app/pebble/speech-spark.pbw`, Quellcode in `pebble/`) bringt den Sprach-Chat auf Pebble Time 2 und Core 2 Duo, mit Antwort als Text und über den Lautsprecher der Uhr. Auf Pebble Round 2 kommt die Antwort nur als Text. Sie braucht eine Uhr-Firmware mit Lautsprecher-API (ab etwa v4.9.170).

1. Kopplung per Einrichtungscode (neu in V01.0.230, aus): Admin schaltet *Funktionen → Pebble-Uhr koppeln* ein, das Profil unter *Ich → Pebble-Uhr* „Pebble-Uhr für mich“, dann „Pebble koppeln“ und die Zeile kopieren (gilt 10 Minuten, einmal). Die Uhr bekommt einen eigenen Schlüssel, der nur `/api/watch/` erreicht und mit einem der beiden Schalter sofort gesperrt ist. Ohne Kopplung geht weiter: unter **Personen und Geräte** ein Gerät „Pebble“ anlegen und den Schlüssel kopieren.
2. Auf dem gekoppelten Handy `http://SPARK:31080/pebble/speech-spark.pbw` laden und mit der Pebble-App öffnen. Einfacher: *Ich → Pebble-Uhr* zeigt dafür einen QR-Code, den man mit der Handy-Kamera scannt. Gibt es auf dem Spark eine neuere Uhr-App, steht höchstens einmal am Tag „Neue Uhr-App“ unter einer Antwort; die Kopplung bleibt beim Neuinstallieren erhalten.
3. In der Pebble-App bei „Spark“ die Einstellungen öffnen: den Einrichtungscode einfügen, oder Spark-Adresse (`http://SPARK:31080`) und Geräteschlüssel eintragen. Einstellungen und „Start App“ bleiben grau, solange die Pebble-App die Uhr nicht als verbunden sieht (Tab Devices).
4. Auf der Uhr: SELECT fragt (Diktat über das Handy), nochmal SELECT stoppt die Sprache, lang SELECT beginnt ein neues Gespräch. Ein kleines Gesicht oben zeigt, ob Spark zuhört, nachdenkt oder spricht; der Mund folgt der Sprache. Es ist dasselbe Gesicht wie im Panel (Roboter oder Comic, *Einstellungen → Assistent*), die Uhr übernimmt es mit der nächsten Antwort. Die Uhr-Einstellung Settings → Sounds & Haptics → Volume begrenzt, wie laut die App werden kann.

Das Handy muss die Spark erreichen, zu Hause im WLAN, unterwegs über ein VPN wie Tailscale. Die App nutzt HTTP, weil die Pebble-App dem selbstsignierten Zertifikat nicht vertraut. Auf der Spark laufen dafür `POST /api/watch/ask` und `GET /api/watch/poll`: die Antwort wird wie im Sprach-Chat erzeugt (kurz gehalten), der Ton für den kleinen Lautsprecher verdichtet (leise Silben angehoben, Spitzen weich begrenzt) und als 8-kHz-IMA-ADPCM an die Uhr geschickt. Uhr und Handy wiederholen verlorene Nachrichten, nach 30 s ohne Nachricht gibt die Uhr auf. Am Ende schickt das Handy die Zeiten an `POST /api/watch/report`; unter *Zustand → Logs* steht dann im Bereich „Uhr“ pro Antwort eine Zeile `watch: zeit …` (Diktat, erster Text, erster Ton, fertig, Wiederholungen, Ausgang).
