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

**Einschalten:** Admin: Funktionen → *Spark als MCP-Server*. Das gilt für jedes Profil; einzelne Profile sperrt nur der Admin (Personen und Geräte → Gesperrte Funktionen). Einrichten im Profil: Ich → *Dienste per MCP* → „Programm mit Schlüssel verbinden“: Name, Werkzeuge, „Schlüssel erzeugen“. Der Schlüssel ist nur einmal sichtbar; im Programm als Header `Authorization: Bearer <Schlüssel>` eintragen.

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
- Handeln: Ein Programm legt nur einen Vorschlag an. Das Profil bekommt eine Mitteilung und entscheidet unter Ich → Spark als MCP-Server („Ja, ausführen“ mit Code-Fenster, oder „Nein“). Ein Vorschlag wartet 15 Minuten.
- Grenzen: 60 Aufrufe pro Minute und Zugang (`ask_spark` 10), 2 gleichzeitig pro Zugang, 6 insgesamt; Sprache läuft mit der Stufe „hinten“, Menschen am Spark gehen vor. Ohne Nutzung endet ein Zugang nach 90 Tagen.
- Das Journal zeigt jede Anfrage als `mcp-server:` mit Programm, Werkzeug und Dauer, nie den Inhalt.
- Zustand → Live (seit V01.0.334) zeigt jeden Werkzeug-Aufruf als eigene Anfrage „MCP-Client“ mit Werkzeug und Ziel (Sprache als Hören oder Sprechen, ein Vorschlag als „Bestätigung anfragen“ → Push, eine bestätigte Aktion als eigene Anfrage); der Name des Zugangs erscheint nur mit der Zustimmung des Profils („Mein Name im Anfragen-Log“), Inhalte nie. `ask_spark` erscheint wie ein Gespräch.

**Von außen (OAuth):** Admin: *MCP-Server von außen* unter dem Schalter. Ein Zugang „von außen“ braucht den zweiten Anmeldeschritt des Profils und einen frischen Code. Programme wie claude.ai melden sich per OAuth 2.1 an (dynamische Registrierung, PKCE S256, `/.well-known/oauth-authorization-server`): Im Programm einen eigenen MCP-Connector mit `https://dein-proxy/mcp` anlegen, das Programm schickt dich ins Panel, dort Warnhinweis, Werkzeuge wählen, mit Code bestätigen. Zugriffstoken gelten 1 Stunde, Erneuerungstoken 30 Tage und werden bei jeder Nutzung getauscht. Alles, was ein solches Programm liest, geht an dessen Anbieter.

**Beispiele:** Open WebUI: Einstellungen → Externe Werkzeuge → „+“, Typ MCP (Streamable HTTP). n8n: Knoten „MCP Client Tool“. Programme ohne Header-Feld: `npx mcp-remote http://SPARK:31080/mcp --header "Authorization: Bearer <Schlüssel>"`.

### Eigene MCP-Dienste pro Profil

Seit V01.0.363 (Plan `plaene/eigene-mcp-dienste.md`) bindet jedes Profil eigene MCP-Dienste an (Streamable HTTP), zusätzlich zu denen, die der Admin für alle anbindet. Nur dieses Profil sieht und nutzt sie.

**Einschalten:** Admin: Funktionen → Aufträge → Dienste per MCP → *Eigene MCP-Dienste für Profile* (`chat.mcp_own`), darunter *… auch in Hintergrundaufträgen* (`chat.mcp_own_jobs`) und *… mit Anmeldung (OAuth)* (`chat.mcp_own_oauth`); alle aus. Freigegeben gilt es für jedes Profil; einzelne Profile sperrt nur der Admin. Einrichten im Profil: Ich → *Meine MCP-Dienste*, Name, Adresse und Schlüssel eintragen und „Dienst anbinden“. Eine Agent-Stufe braucht das Profil dafür nicht.

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

### Fortgeschritten: MCP-Server auf der NAS

Seit V01.0.552 (Synology-Plan S7, nur Anleitung, kein Code im Spark). Wer seine Dateien lieber über ein eigenes MCP-Programm auf der Synology anbietet statt über die Wissensordner, findet unter [`docs/vorlagen/nas-mcp`](../vorlagen/nas-mcp) eine gehärtete Vorlage für den Container Manager: einen Dateiserver (`@modelcontextprotocol/server-filesystem` hinter `supergateway`, Streamable HTTP) und davor einen Türsteher (nginx), der nur `/mcp` mit dem richtigen Schlüssel durchlässt.

**Ehrlich vorweg:** Die Wissensordner (Ich → Speicher) sind für fast alle der bessere Weg: kein fremdes Programm, der Spark liest selbst, alles im Wächter und in Live. Ein MCP-Container ist Software von Dritten auf deiner NAS, mit Zugriff auf den Ordner, den du ihm gibst. Er ist so sicher wie seine Abhängigkeiten, und Updates musst du selbst bauen. Nimm ihn nur, wenn du genau weißt, warum.

**Was die Vorlage festlegt:**
- Basis-Images nur mit Digest (`node:22-alpine@sha256:…`, `nginx-unprivileged@sha256:…`), feste Paketversionen, `npm ci` beim Bauen statt `npm install` bei jedem Start, ohne Install-Skripte.
- Der Ordner nur lesend (`/volume1/dokumente:/data:ro`), dazu `read_only: true`, `user: "1000:1000"`, `cap_drop: [ALL]`, `security_opt: no-new-privileges`, Speicher- und Prozessgrenze.
- Der Dateiserver hängt nur im internen Netz (`internal: true`): kein Port, kein Internet. Nach außen geht nur der Türsteher, und der nur auf `127.0.0.1:8765`.
- Erreichbar nur über den Reverse-Proxy der NAS mit HTTPS und einem gültigen Zertifikat (der Spark prüft es; ein selbst signiertes lehnt er ab). Der Türsteher verlangt `Authorization: Bearer <Schlüssel>` und gibt den Schlüssel nicht weiter.

**Einrichten:**
1. Die vier Dateien auf die NAS kopieren (z. B. `/volume1/docker/nas-mcp`). Einmal `npm install --package-lock-only` ausführen (auf einem anderen Rechner genügt), damit `package-lock.json` die genauen Versionen festhält.
2. Die beiden Digests eintragen (Befehle stehen in den Dateien), in `compose.yaml` den Ordner anpassen, in `nginx.conf` `SCHLUESSEL` durch einen langen Zufallswert ersetzen (`openssl rand -hex 32`).
3. Container Manager → Projekt → Erstellen, Pfad wählen, `compose.yaml` übernehmen, bauen und starten.
4. DSM → Systemsteuerung → Anmeldeportal → Erweitert → Reverse Proxy → Erstellen: Quelle HTTPS mit eigenem Port oder Namen, Ziel HTTP `localhost:8765`. Zertifikat unter Sicherheit → Zertifikat zuordnen.
5. Spark: Admin schaltet Funktionen → Aufträge → Dienste per MCP → *Eigene MCP-Dienste für Profile* an und, weil die NAS im Heimnetz steht, Einstellungen → Sicherheit → *Heimnetz-Adressen erlauben*.
6. Profil: Ich → *Meine MCP-Dienste*: Name „NAS-Dateien“, Adresse `https://<NAS>:<Port>/mcp`, den Schlüssel, „Dienst anbinden“. Unter „Werkzeuge freigeben“ nur die lesenden Werkzeuge (`read_text_file`, `list_directory`, `search_files`, `get_file_info` …) auf „Lesen“; alles, was schreibt, verschiebt oder anlegt, bleibt „Aus“ (der Ordner ist ohnehin nur lesend eingebunden).

**Aus:** Im Spark den Dienst entfernen (der Schlüssel wird gelöscht), auf der NAS das Projekt stoppen und die Reverse-Proxy-Regel löschen. Ein neuer Schlüssel: in `nginx.conf` ändern, Türsteher neu starten, im Spark den Dienst mit dem neuen Schlüssel neu eintragen.

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

### Chats mit anderen Sparks (V01.0.496)

Zwischen Sparks (offen, statt einer Anmeldung eine Unterschrift): `GET /.well-known/spark-verbund` liefert `{"v": 1, "key": "<Ed25519, Base64>", "inbox": "/api/verbund/in"}`, nur solange „Chats mit anderen Sparks“ an ist. `POST /api/verbund/in` nimmt JSON bis 32 KB mit den Kopfzeilen `X-Spark-From: <Domain des Absenders>` und `X-Spark-Sig: <Base64>`; unterschrieben wird `spark-verbund v1\n<Domain des Empfängers>\n<Body>`. Body: `v`, `t` (Unix-Zeit, ±600 s), `n` (32 Hex-Zeichen, einmal), `type` (`pair`, `ask`, `yes`, `msg`, `read`, `edit`, `back`, `react`, für Gruppen `gadd`, `gmsg`, `gleave`, `gremove`, `gname`, `gmembers`), `from`/`to` (der Teil vor dem @), je nach Art `name`, `id`, `text`, `reply`, `emoji`, `secret`. Antwort immer `{"ok": true}`, Ablehnungen 400/403/409/413/429 ohne Grund.
Für das Profil (Browser oder iPhone-App, Schalter wie oben): `GET /api/verbund` (eigene Adresse, QR, Kontakte mit `state` in/out/ok/block), `POST /api/verbund/ask {"addr"}`, `POST /api/verbund/answer {"id", "act": "ok"|"no"|"block"|"unblock"}`, `POST /api/verbund/remove {"id"}`, `POST /api/verbund/open {"id"}` (Chat-`id`). Admin: `GET /api/admin/verbund`, `POST /api/admin/verbund/pair` und `/connect {"code"}` (Code des zweiten Schritts), `POST /api/admin/verbund/peer {"domain", "act": "allow"|"block"|"remove"}`.

Dateien (V01.0.568, Schalter „Fotos und Dateien zu anderen Sparks“): `POST /api/verbund/blob` mit dem Inhalt als Body, `X-Spark-From`, `X-Spark-Blob` (Base64url von `{"v": 1, "t", "n", "sha", "size"}`) und `X-Spark-Sig` (Unterschrift wie bei Nachrichten über diesen Kopf); danach `msg` mit `"media": {"kind": "photo"|"file"|"voice", "sha", "size", "name"?}`. Antworten: 200, 400 (Form, Zeit, Größe, Hash), 401 (kein bekannter, erlaubter Spark oder aus), 403 (Unterschrift), 409 (wiederholt), 429 (Tageslimit).

Gruppen (V01.0.568, Schalter „Gruppen mit anderen Sparks“): Die Gruppe gehört dem Spark, auf dem sie erstellt wurde; `gid` ist ihre Chat-Kennung dort. Von ihm: `gadd` an eine Person (`from` ist der Admin, der ein angenommener Kontakt der Person sein muss; `name`, `members` als Liste von `{"addr", "name"}`), `gmsg` mit `id`, `text`, `reply`, `by` (Adresse des Verfassers) und `byname`, einmal pro Spark, `gremove` an eine Person, `gname` mit `name`, `gmembers` mit `members`. An ihn, mit `to` leer: `gmsg` (`from` ist das Mitglied, `id`, `text`, `reply`) und `gleave`. Der Heimat-Spark prüft die Mitgliedschaft und reicht eine Nachricht an alle anderen Sparks weiter, nie an den, von dem sie kam. Bisher nur Text, höchstens 10 andere Sparks pro Gruppe.

### Anrufe (V01.0.556)

Nur im eigenen Browser des Profils (die Android-App ist einer; nie mit Geräteschlüssel), Admin-Schalter „Anrufe (Sprache und Video)“, Ton und Bild gehen per WebRTC direkt zwischen den Geräten. `dev` ist eine zufällige Kennung der Seite (12 Hex-Zeichen), `call` die des Anrufs (16 Hex-Zeichen). `GET /api/anrufe/ice` liefert `servers` (leer ohne „Anrufe von unterwegs“, sonst STUN/TURN mit einem Zugang für eine Stunde). `POST /api/anrufe/start {"id", "video", "dev"}` → `{"call", "state": "ring"|"busy"|"missed", "servers"}`; `POST /api/anrufe/answer {"call", "dev"}`; `POST /api/anrufe/signal {"call", "dev", "data": {"sdp": {"type", "sdp"}} | {"ice": {…}}}` (16 KB); `POST /api/anrufe/end {"call", "dev", "why": "hangup"|"reject"}` → `{"line"}`. Neuigkeiten kommen über `GET /api/chats/stream` als `call`, `call_ok`, `call_taken`, `call_sig` (mit `to`: nur dieses Gerät nimmt es) und `call_end`. Anrufe per Assistent (`rufen.py`): `GET /api/chats` hat `ruf` (`null` oder `{"id", "name", "video", "secs"}`: ein Anruf, den der Assistent für das Profil bereithält); `DELETE /api/anrufe/bereit` → `{"ok"}` nimmt ihn weg („Nicht jetzt“). Im Antwort-Strom von `POST /api/chat` nach dem Ja `{"type": "anruf", "id", "name", "video"}` (das Gerät startet den Anruf) oder auf Android `{"type": "waehlen", "number"}` (Telefon-App öffnen).

### Pebble-Uhr

Die Watch-App „Spark“ (`app/pebble/speech-spark.pbw`, Quellcode in `pebble/`) bringt den Sprach-Chat auf Pebble Time 2 und Core 2 Duo, mit Antwort als Text und über den Lautsprecher der Uhr. Auf Pebble Round 2 kommt die Antwort nur als Text. Sie braucht eine Uhr-Firmware mit Lautsprecher-API (ab etwa v4.9.170).

1. Kopplung per Einrichtungscode (neu in V01.0.230, aus): Admin schaltet *Funktionen → Pebble-Uhr koppeln* ein (gilt für jedes Profil), das Profil wählt unter *Ich → Pebble-Uhr* „Pebble koppeln“ und kopiert die Zeile (gilt 10 Minuten, einmal). Die Uhr bekommt einen eigenen Schlüssel, der nur `/api/watch/` erreicht und sofort gesperrt ist, wenn der Admin die Funktion ausschaltet oder das Profil sperrt. Ohne Kopplung geht weiter: unter **Personen und Geräte** ein Gerät „Pebble“ anlegen und den Schlüssel kopieren.
2. Auf dem gekoppelten Handy `http://SPARK:31080/pebble/speech-spark.pbw` laden und mit der Pebble-App öffnen. Einfacher: *Ich → Pebble-Uhr* zeigt dafür einen QR-Code, den man mit der Handy-Kamera scannt. Gibt es auf dem Spark eine neuere Uhr-App, steht höchstens einmal am Tag „Neue Uhr-App“ unter einer Antwort; die Kopplung bleibt beim Neuinstallieren erhalten.
3. In der Pebble-App bei „Spark“ die Einstellungen öffnen: den Einrichtungscode einfügen, oder Spark-Adresse (`http://SPARK:31080`) und Geräteschlüssel eintragen. Einstellungen und „Start App“ bleiben grau, solange die Pebble-App die Uhr nicht als verbunden sieht (Tab Devices).
4. Auf der Uhr: SELECT fragt (Diktat über das Handy), nochmal SELECT stoppt die Sprache, lang SELECT beginnt ein neues Gespräch. Ein kleines Gesicht oben zeigt, ob Spark zuhört, nachdenkt oder spricht; der Mund folgt der Sprache. Es ist dasselbe Gesicht wie im Panel (Roboter, Comic oder Comic (Frau), *Einstellungen → Assistent*), die Uhr übernimmt es mit der nächsten Antwort. Die Uhr-Einstellung Settings → Sounds & Haptics → Volume begrenzt, wie laut die App werden kann.

Das Handy muss die Spark erreichen, zu Hause im WLAN, unterwegs über ein VPN wie Tailscale oder die Adresse unterwegs (unten). Die App nutzt HTTP, weil die Pebble-App dem selbstsignierten Zertifikat nicht vertraut. Auf der Spark laufen dafür `POST /api/watch/ask` und `GET /api/watch/poll`: die Antwort wird wie im Sprach-Chat erzeugt (kurz gehalten), der Ton für den kleinen Lautsprecher verdichtet (leise Silben angehoben, Spitzen weich begrenzt) und als 8-kHz-IMA-ADPCM an die Uhr geschickt. Uhr und Handy wiederholen verlorene Nachrichten, nach 30 s ohne Nachricht gibt die Uhr auf. Am Ende schickt das Handy die Zeiten an `POST /api/watch/report`; unter *Zustand → Logs* steht dann im Bereich „Uhr“ pro Antwort eine Zeile `watch: zeit …` (Diktat, erster Text, erster Ton, fertig, Wiederholungen, Ausgang).

**Mehr auf der Uhr (Uhr-App 2.0, Paket 1 aus `pebble-ideen/plan.md`):** Drei Unterschalter unter *Funktionen → Pebble-Uhr*, alle aus; freigegeben gelten sie für jedes Profil, Gäste nie.

- *Zuhause und unterwegs*: Unter *Ich → Pebble-Uhr* steht beim Koppeln das Feld „Adresse unterwegs“ (nur `https://name[:port]`, etwa der Reverse-Proxy). Die Kopplungszeile trägt sie als `&aussen=…` mit. Antwortet die Adresse von zu Hause nicht innerhalb von 4 Sekunden, nimmt das Handy die zweite und bleibt 5 Minuten dabei; die Uhr zeigt dann „unterwegs“. Fragen ohne https gehen nie über das Internet.
- *Uhr: Nachfragen zum Antippen*: Unter einer Antwort öffnet UNTEN am Ende bis zu 3 kurze Folgefragen; antippen fragt weiter wie gesagt. Das Modell schlägt nur Text vor (Aufgabe „Uhr-Nachfragen“, höchstens 6 Sekunden); das Panel lässt nur kurze Fragen ohne Ja/Nein, Links, lange Zahlen oder Löschen, Kaufen, Schicken durch. Nach einer Antwort aus Mail, Web oder fremdem Text, nach einem Vorschlag, einem Fehler oder Notaus gibt es keine. Schlägt der Spark etwas vor („Soll ich …?“), zeigt die Uhr ✓ und ✕; ✓ schickt „Ja“, ✕ „Nein“ als normale Antwort, entschieden wird wie immer im Panel.
- *Uhr: Schnellbefehle*: Bis zu 12 eigene Sätze je Profil (je höchstens 60 Zeichen) unter *Ich → Pebble-Uhr*. Lang OBEN auf der Uhr zeigt die Liste, SELECT schickt einen Satz als Frage.
- *Uhr: Erinnerungen und Timer am Handgelenk* (braucht auch *Timer und Erinnerungen*): Die nächsten 8 Erinnerungen der nächsten 30 Tage liegen auf der Uhr als Wecker und klingeln auch ohne Handy (gelbes Fenster, dreimal Vibration). OBEN schließt, SELECT „Später“ (10 Minuten), UNTEN beendet eine Serie. Ein Timer zeigt einen Ring; OBEN gibt eine Minute dazu, UNTEN lang stoppt ihn. Lang UNTEN zeigt die Liste. Die Uhr meldet, was sie geklingelt hat (`POST /api/watch/reminder`), so klingelt eine Erinnerung für das Profil nur einmal; Push wartet 90 Sekunden auf die Uhr, wenn sie die Erinnerung hält. Das Handy holt die Liste über `GET /api/watch/sync` beim Start, nach jedem Stellen und nach dem Speichern der Einstellungen.

**Paket 2 (Uhr-App 2.1, Spark-Zifferblatt 1.0):** fünf weitere Unterschalter unter *Funktionen → Pebble-Uhr*, alle aus.

- *Spark-Zifferblatt*: ein eigenes Zifferblatt (`/pebble/spark-zifferblatt.pbw`, Quellcode `pebble/zifferblatt/`) mit Uhrzeit, Datum, nächstem Termin, nächster Erinnerung („in 12 Min“), Wetter und einem Tipp. Es fragt alle 15 Minuten über das Handy `GET /api/watch/blick` und hält das Letzte im Speicher der Uhr. Unter *Ich → Pebble-Uhr* steht ein zweiter QR-Code; das Zifferblatt bekommt mit „Pebble koppeln“ einen eigenen Schlüssel (gleicher Bereich wie die Uhr-App, nur `/api/watch/`).
- *Uhr: Mein Tag und meine Woche*: Oben in der Liste (lang OBEN) stehen „Mein Tag“ und „Meine Woche“ (`GET /api/watch/brief?art=tag|woche`). Mein Tag: heutige Termine, Erinnerungen, Wetter, ungelesene Nachrichten. Meine Woche: Fragen und neu Gemerktes der letzten 7 Tage, Termine und Erinnerungen der nächsten 7 Tage. Feste Sätze aus den eigenen Daten, nie das Sprachmodell, nie Mail- oder Nachrichtentext; jeder Teil nur, wenn seine Funktion für das Profil an ist.
- *Uhr: Meldungen für Admins* (braucht den Dienst-Wächter): Antwortet ein Dienst nicht, zeigt das Zifferblatt der Admins, die die Meldungen bekommen, oben einen roten Streifen mit demselben festen Satz wie das Banner und vibriert einmal.
- *Uhr: Schnell merken* (braucht das Gedächtnis): „Merken“ in der Liste, einen Satz sagen; er geht über `POST /api/watch/merken` ins Gedächtnis wie „Merk dir …“, ohne Sprachmodell. *Uhr: Ort beim Merken* (eigener Schalter): Das Handy hängt den Ort auf drei Nachkommastellen (etwa 100 m) an, nur wenn man der Pebble-App den Standort erlaubt.

**Paket 3 (Uhr-App 2.2):** vier weitere Unterschalter unter *Funktionen → Pebble-Uhr*, alle aus.

- *Uhr: Nachrichten* (braucht die Chats): „Nachrichten“ in der Liste zeigt die letzten 8 Chats mit der Zahl der ungelesenen (`GET /api/watch/chats`), ein Chat seine letzten 6 Nachrichten (`GET /api/watch/chat?id=…`, danach gelesen). UNTEN am Ende: „Okay“, „Bin unterwegs“, „Melde mich gleich“, „Danke!“ oder „Diktieren …“; geschickt wird über `POST /api/watch/chat`, das alle Regeln der Chats noch einmal prüft. Private Chats erscheinen nicht, sie nehmen nur auf dem Gerät verschlüsselte Nachrichten an.
- *Uhr: Antwortvorschläge*: Kam die letzte Nachricht von jemand anderem, schlägt das Sprachmodell bis zu 3 kurze Antworten vor (Aufgabe „Uhr-Antworten“, höchstens 6 Sekunden). Die Nachrichten gehen als Inhalt zwischen <<< >>> hin, nie als Anweisung; das Panel lässt nur Sätze bis 40 Zeichen ohne Links, Zahlen, Geld, Codes oder PIN durch. Geschickt wird nur, was man antippt.
- *Uhr: Fernbedienung*: Unter *Ich → Pebble-Uhr* bis zu 12 Geräte aus dem eigenen Home Assistant anhaken; „Fernbedienung“ in der Liste zeigt sie mit festen Tasten (Fernseher und Musik: an, aus, Play/Pause, weiter, lauter, leiser; Rollläden: auf, zu; Licht und Schalter: umschalten, an, aus), dazu die eigenen Lautsprecher (lauter, leiser). `POST /api/watch/fern` schaltet nur Geräte aus der eigenen Liste, die Home Assistant noch als schaltbar meldet, mit einer Taste ihrer Art; Notaus, die erlaubten Bereiche (nie Schlösser, Alarm, Skripte) und die Rückmeldung von Home Assistant gelten wie bei jedem Schalten. Mit Smart-Home-Codewort schaltet die Uhr nichts in Home Assistant.
- *Uhr: Schritte, Puls und Schlaf*: Beim Öffnen der App schickt die Uhr die Zahlen von Pebble Health (Schritte heute, letzter Puls, Schlaf heute) über `POST /api/watch/gesundheit`. Der Spark hält 30 Tage, eine Zeile pro Tag, versiegelt in `gesundheit.json` im Profil. Nur das eigene Profil sieht sie unter *Ich → Pebble-Uhr* und löscht sie dort („Alle löschen“), auch wenn die Funktion aus ist; das Sprachmodell bekommt sie nie.

Logs im Bereich „Uhr“: `watch: sync | n Schnellbefehle · n Erinnerungen`, `watch: reminder played|snooze|stop|plus|cancel | ok`, `watch: Nachfragen | n | ms`, `watch: Nachfragen weggelassen | why …`, `watch: blick | n Teile`, `watch: brief tag|woche | n Zeilen`, `watch: merken | ok`, `watch: chats | n`, `watch: chat | n Nachrichten · n Vorschläge`, `watch: chat send | ok`, `watch: fern | n Geräte`, `watch: fern um|an|aus|… | ok`, `watch: gesundheit | ok`, `watch: … refused | why off|invalid`, nur Zahlen und feste Wörter.

### Terminal-Client (spark-tui)

`spark-tui` (`app/tui/spark-tui.py`, eine Python-Datei) bringt den Chat mit deinem Verlauf, *Heute* und deine Aufträge, Pläne und Routinen in ein Terminal, etwa auf die ClockworkPi uConsole oder per SSH (neu in V01.0.646, aus).

1. Admin schaltet *Funktionen → Terminal-Client* ein (gilt für jedes Profil, der Admin sperrt einzelne; Gäste nie).
2. Unter *Ich → Terminal* steht eine Zeile, die das Programm holt, die Prüfsumme prüft (`sha256sum -c` mit dem Wert von der Seite) und es als Befehl `~/.local/bin/spark-tui` einrichtet (ab V01.0.661; Raspberry Pi OS hat `~/.local/bin` nach dem nächsten Anmelden im Suchpfad). Für das Fenster braucht es Textual in einer eigenen Umgebung (`python3 -m venv ~/.local/share/spark-tui && ~/.local/share/spark-tui/bin/pip install textual`, Raspberry Pi OS und Debian lassen pip außerhalb einer Umgebung nicht zu; spark-tui findet sie selbst), `spark-tui frage "…"` geht ohne.
3. „Kopplungszeile holen“ (mit Bestätigungscode) gibt eine Zeile `~/.local/bin/spark-tui koppeln 'https://…#tui=…&fp=…'`, die 10 Minuten und einmal gilt. Im Heimnetz pinnt das Terminal das Zertifikat des Panels (`fp`, SHA-256) und schickt nichts, wenn es nicht passt. Holt man die Zeile über die Adresse von außen (Reverse-Proxy mit echtem Zertifikat), steht kein `fp` darin und das Zertifikat wird wie im Browser geprüft. `spark-tui adresse-dazu https://…` fügt eine zweite Adresse hinzu; das Terminal nimmt die erste, die antwortet. Nur `https` geht.
4. Das Terminal speichert seinen Schlüssel in `~/.config/spark-tui/geraet.json` (nur für dich lesbar). Der Schlüssel heißt „Terminal · Name“, erreicht nur Chat, Gespräche, Heute, Funktionsliste und die Aufträge-Seiten und bekommt 503, solange die Funktion aus oder das Profil gesperrt ist. Aufträge folgen der Agent-Stufe des Profils. Entfernen unter *Ich → Terminal* oder bei **Personen und Geräte**.

Fenster: links Gespräche, Aufträge und Heute (unter 100 Spalten nur der Chat), rechts der Chat. F2 Gespräche, F3 Aufträge (`n` neuer Auftrag; im Auftrag `d` als Dokument, `x` abbrechen, Entf löschen), F4 neu laden, F5 Kalender (die Woche als Text, ← → blättert, `t` heute; ab V01.0.807), Strg+N neues Gespräch, Esc stoppt die Antwort, F10 Ende. `spark-tui kalender` (oder `--woche 1` für die nächste) druckt die Termine der Woche wie die Seite Kalender, nur lesen. `spark-tui status` zeigt Adresse, Profil und was das Terminal darf. Hat der Spark eine neuere Version, steht oben im Fenster „Neue Version …: spark-tui update“; `spark-tui update` holt sie über die gekoppelte Verbindung und ersetzt das Programm nur, wenn die Prüfsumme zu der passt, die der Spark nennt (ab V01.0.665). Fragen erscheinen im Anfrage-Verlauf mit Eingang „Terminal“, unter *Zustand → Live* steht die Zahl offener Terminals, unter *Zustand → Logs* im Bereich „Apps“ die Zeilen `terminal: …`. Die Frage tippt man in ein Feld mit drei Zeilen, das bis sechs Zeilen mitwächst (seit V01.0.829): Enter schickt ab, Strg+J (oder Umschalt+Enter, wo das Terminal es unterscheidet) macht eine neue Zeile; ebenso beim neuen Auftrag.

Kalender und E-Mail ohne Fenster (V01.0.830, Dominik 2026-10-19 „a“): `spark-tui neu 'Morgen 15 Uhr Zahnarzt'` zeigt, was der Spark aus der Zeile liest (Titel, Tag, Uhrzeit, Ort; feste Regeln wie „Schnell eintragen“ auf der Seite Kalender), fragt „Eintragen? [j/N]“ und speichert erst dann in deinen ersten eigenen Kalender (`--ja` ohne Rückfrage). `spark-tui mails` listet die neuesten Mails nach Tagen (Nummer, `*` ungelesen, Uhrzeit, Absender, Betreff), `spark-tui mail 3` zeigt die dritte als reinen Text; sie bleibt ungelesen. Ändern, Ordnen und Senden bleiben im Panel und in der App. Texte aus Kalender und Mail zeigt das Terminal nur mit druckbaren Zeichen, nie Steuerzeichen.
