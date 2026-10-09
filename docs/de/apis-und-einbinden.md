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

Läuft Open WebUI in Docker auf derselben Spark, statt `SPARK` entweder die LAN-IP oder `host.docker.internal` nehmen (Container mit `--add-host=host.docker.internal:host-gateway`). Das Panel zeigt diese Werte im Reiter „Einbinden“ zum Kopieren an.

### KI-Agenten: Hermes Agent und OpenClaw

Ein Agent wie [Hermes Agent](https://hermes-agent.nousresearch.com) (Nous Research) oder [OpenClaw](https://docs.openclaw.ai) kann die Spracherkennung und Sprachausgabe der Spark nutzen. Der Agent läuft auf einem anderen Rechner und bekommt nur Audio und Vorlesetext, keinen Zugang zu Profilen, Gedächtnis oder Werkzeugen des Assistenten. Das Panel zeigt die fertigen Bausteine unter Einbinden zum Kopieren.

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

### „Hey Siri, frag Spark“

Ein iPhone-Kurzbefehl schickt die diktierte Frage an `POST /api/siri/ask` (Header `X-Speech-Device` mit
einem Geräteschlüssel deines Profils, Inhalt `{"text": "..."}`) und lässt Siri das Feld `answer`
vorlesen. Geht ohne geöffnete Seite, auch auf der Apple Watch, mit AirPods und mit CarPlay; Nachfragen
innerhalb von 10 Minuten kennen den Zusammenhang, die Fragen eines Tages stehen als Gespräch im Profil.
Schritt für Schritt unter Einbinden → Anleitungen.

### iPhone-App „Spark“

Eigene App fürs iPhone mit Spark-Stimme und „Hey Siri, Frag Spark“, Kopplung per QR-Code, eigener Schlüssel pro iPhone, der nur fragen und hören darf. Bauen, Koppeln und Sicherheit: [iphone-app.md](iphone-app.md).

### Nachrichten zwischen Profilen (für die iPhone-App)

Mit der Browser-Anmeldung des Profils oder dem Schlüssel der iPhone-App (Header `X-Speech-Device`), nur wenn der Admin „Nachrichten an andere“ und das Profil „Nachrichten für mich nutzen“ eingeschaltet hat; andere Geräteschlüssel bekommen 403. Höchstens 30 Aufrufe pro Minute.
- `GET /api/messages`: Postfach (`items` mit `id, from, name, text, t, read, kind, voice, secs`), Empfänger `to`, Lautsprecher für Durchsagen, Schalter (`all`, `announce`, `voice`), `max_text`, `max_voice`.
- `GET /api/messages/poll?since=<ms>`: neue, noch nirgends gesprochene Nachrichten; markiert das Gerät als offen (dann keine Mitteilung).
- `POST /api/messages/played {"id"}`: `{"play": true}` nur für das erste Gerät, das sie spricht.
- `POST /api/messages/send {"to": "<Profil-id>" | "all", "text"}` (höchstens 500 Zeichen).
- `POST /api/messages/voice?to=<Profil-id>`: Aufnahme als Body (höchstens 2 MB, 30 Sekunden); `GET /api/messages/audio?id=` liefert sie als Ogg/Opus.
- `POST /api/messages/announce {"speakers": [id], "text"}`, `POST /api/messages/read {"ids"?}`, `POST /api/messages/delete {"ids"?}` (ohne `ids`: alle).
- Mitteilungen: APNs mit Tag `msg-<id>`, der Text kommt wie bisher über `/api/iphone/note`. „Wer darf mir schreiben“ (`PUT /api/messages/who`) nur im Browser.

### Pebble-Uhr

Die Watch-App „Spark“ (`app/pebble/speech-spark.pbw`, Quellcode in `pebble/`) bringt den Sprach-Chat auf Pebble Time 2 und Core 2 Duo, mit Antwort als Text und über den Lautsprecher der Uhr. Auf Pebble Round 2 kommt die Antwort nur als Text. Sie braucht eine Uhr-Firmware mit Lautsprecher-API (ab etwa v4.9.170).

1. Im Panel unter **Profile** beim eigenen Profil ein Gerät „Pebble“ anlegen und den Schlüssel kopieren.
2. Auf dem gekoppelten Handy `http://SPARK:31080/pebble/speech-spark.pbw` laden und mit der Pebble-App öffnen.
3. In der Pebble-App bei „Spark“ die Einstellungen öffnen: Spark-Adresse (`http://SPARK:31080`) und Geräteschlüssel eintragen. Einstellungen und „Start App“ bleiben grau, solange die Pebble-App die Uhr nicht als verbunden sieht (Tab Devices).
4. Auf der Uhr: SELECT fragt (Diktat über das Handy), nochmal SELECT stoppt die Sprache, lang SELECT beginnt ein neues Gespräch. Ein kleines Gesicht oben zeigt, ob Spark zuhört, nachdenkt oder spricht; der Mund folgt der Sprache. Die Uhr-Einstellung Settings → Sounds & Haptics → Volume begrenzt, wie laut die App werden kann.

Das Handy muss die Spark erreichen, zu Hause im WLAN, unterwegs über ein VPN wie Tailscale. Die App nutzt HTTP, weil die Pebble-App dem selbstsignierten Zertifikat nicht vertraut. Auf der Spark laufen dafür `POST /api/watch/ask` und `GET /api/watch/poll`: die Antwort wird wie im Sprach-Chat erzeugt (kurz gehalten), der Ton für den kleinen Lautsprecher verdichtet (leise Silben angehoben, Spitzen weich begrenzt) und als 8-kHz-IMA-ADPCM an die Uhr geschickt.
