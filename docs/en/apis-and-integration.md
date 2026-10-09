# APIs and integration

← [README](../../README.md)

## APIs (OpenAI-style)

```bash
# Transcription
curl http://SPARK:31001/v1/audio/transcriptions -F file=@recording.webm -F language=de
# -> {"text": "...", "usage": {"type": "duration", "seconds": 4}, "processing_s": 0.6}

# Speech
curl http://SPARK:31002/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"Hello world","voice":"ryan","language":"English"}' -o hello.mp3
```

Both services answer `GET /health` with status and counters. `GET /v1/voices` (TTS) lists the voices and `GET /v1/models` the loaded model.

Speech recognition accepts anything ffmpeg can read (wav, mp3, webm, mp4, ogg …) and long recordings. `language` is a code (`de`) or a name (`German`); without it the model detects the language. `response_format` is `json`, `text` or `verbose_json` (with `language` and `duration`, without timestamps). With `-F stream=true` the text arrives in pieces as Server-Sent Events in OpenAI format (`transcription.chunk`, then `[DONE]`).

### Streaming speech

With `"stream": true` (and `"response_format": "pcm"`, the default then) the answer arrives as Server-Sent Events as soon as the first sounds are generated:

```
event: speech.audio.delta
data: {"type": "speech.audio.delta", "audio": "<base64>", "response_format": "pcm"}
...
event: speech.audio.done
data: {"type": "speech.audio.done", "usage": {...}}
```

`audio` is PCM, 16 bit, mono, 24 kHz. Errors arrive as `speech.audio.error`. This is vllm-omni's format, passed through unchanged.

```bash
curl -N http://SPARK:31002/v1/audio/speech -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"input":"Hello world","voice":"ryan","language":"English","stream":true,"response_format":"pcm"}'
```

**Steadier delivery:** Qwen samples with `temperature` 0.9 and `top_p` 1.0 by default, so tempo and emphasis vary from sentence to sentence. The server therefore applies `temperature` 0.7, `top_p` 0.9 and `seed` 42 (Settings → Speech output). Requests can override them with the same fields, top-level or inside `extra_params`. In Open WebUI, set response splitting to **paragraphs**: each part is generated separately, and longer parts sound more coherent. Set the default language to a fixed language instead of `auto`.

**Laughing and mood swings:** the model reads emojis, "haha", `*laughs*` and markdown as cues and laughs or changes tone. The server removes them before synthesis (Settings → Speech output → clean text, on by default).

**Overacting:** exclamation marks and interjections ("Oh", "Wow") make the voice act out excitement. With "speak calmly" (on by default) the server turns "!" into "." and drops such interjections at the start of a sentence. The default voice-chat prompt also asks the LLM for plain, calm everyday language.

**Numbers:** the server writes numbers out before synthesis, because the model guesses otherwise. Dates, times, money, percent and decimals become words ("on 2026-10-06 at 9:30, $49.90" → "on October sixth, twenty twenty-six at nine thirty, forty-nine dollars ninety"), phone numbers become pairs. Settings → Speech output → reading numbers: as words (default), in pairs, digit by digit or unchanged. Works for German and English.

**Speaking style:** `"instructions": "calm and friendly, rather slow"` in the request. Without it, the default instruction from Settings → Speech output applies. Only the 1.7B models (CustomVoice, VoiceDesign) follow instructions; the 0.6B models ignore them (per the Qwen model card).

**VoiceDesign** (voice from a description): `"task_type": "VoiceDesign"` and `"instructions": "deep, calm male voice"`. This needs its own model: enable "VoiceDesign zusätzlich bereitstellen" in Settings → Speech output. It starts a second engine with the same memory footprint again.

In the panel under **Zustand → Prüfen** (Status → Checks), "gestreamt" (streamed) plays audio while it is generated and shows the time to first audio.

### General

The services behave like the OpenAI audio API: TTS returns mp3 by default (also wav, flac, opus, pcm), STT understands `response_format=text`, and the language may be an ISO code like `de`. OpenAI voice names like `alloy` fall back to the default voice. If an API key is set in the panel, apps must send `Authorization: Bearer <key>`.

### Open WebUI

Admin Panel → Settings → Audio:

| Field | STT | TTS |
|---|---|---|
| Engine | OpenAI | OpenAI |
| API Base URL | `http://SPARK:31001/v1` | `http://SPARK:31002/v1` |
| API Key | key from the panel (Settings → Security → API key; the installer always sets one) | same |
| Model | anything | anything |
| Voice | | e.g. `ryan` |

If Open WebUI runs in Docker on the same Spark, use the LAN IP or `host.docker.internal` instead of `SPARK` (container started with `--add-host=host.docker.internal:host-gateway`). The panel shows these values ready to copy in the **Einbinden** tab.

### AI agents: Hermes Agent and OpenClaw

An agent such as [Hermes Agent](https://hermes-agent.nousresearch.com) (Nous Research) or [OpenClaw](https://docs.openclaw.ai) can use the Spark's speech recognition and speech output. The agent runs on another computer and only gets audio and text to read out, no access to the assistant's profiles, memory or tools. The panel shows ready-made snippets under Integrate.

Hermes Agent, `~/.hermes/config.yaml`:

```yaml
stt:
  enabled: true
  provider: openai
  language: en
  openai: {base_url: "http://SPARK:31001/v1", api_key: "KEY", model: "qwen3-asr"}
tts:
  provider: openai
  openai: {base_url: "http://SPARK:31002/v1", api_key: "KEY", model: "qwen3-tts", voice: "ryan"}
```

OpenClaw: `tts.provider: "openai"` with `tts.providers.openai.baseUrl` = `http://SPARK:31002/v1` (plus `apiKey`, `model`, `speakerVoice`, `responseFormat: "mp3"`), and for voice messages an entry in `tools.media.models` with `provider: "openai"`, `baseUrl` = `http://SPARK:31001/v1` and `capabilities: ["audio"]`; store the key as an OpenAI API key profile.

Do not install the agent on the Spark itself: it runs commands and could reach settings and keys. Without an API key anyone on the home network can use the speech services.

### "Hey Siri, ask Spark"

An iPhone shortcut sends the dictated question to `POST /api/siri/ask` (header `X-Speech-Device` with a
device key of your profile, body `{"text": "..."}`) and lets Siri speak the `answer` field. Works without
the page open, also on Apple Watch, AirPods and CarPlay; follow-ups within 10 minutes keep the context,
and each day's questions are kept as a conversation of the profile. Step by step under Einbinden → Guides.

### iPhone app "Spark"

Own iPhone app with the Spark voice and "Hey Siri, Frag Spark", paired by QR code, its own key per iPhone that may only ask and listen. Building, pairing and security: [iphone-app.md](iphone-app.md).

### Messages between profiles (for the iPhone app)

With the profile's browser login or the iPhone app's key (header `X-Speech-Device`), only when the admin switched on "Messages to others" and the profile "Use messages for me"; other device keys get 403. At most 30 calls a minute.
- `GET /api/messages`: mailbox (`items` with `id, from, name, text, t, read, kind, voice, secs`), recipients `to`, speakers for announcements, switches (`all`, `announce`, `voice`), `max_text`, `max_voice`.
- `GET /api/messages/ready` (also while the switches are off): `enabled`, `on`, `reach` (`id, name`), `off` (`name, why`), `why`; for the ready view. The admin switches every profile on with `POST /api/admin/messages/enable_all`.
- `GET /api/messages/poll?since=<ms>`: new messages not spoken anywhere yet; marks the device as open (then no notification).
- `POST /api/messages/played {"id"}`: `{"play": true}` only for the first device that speaks it.
- `POST /api/messages/send {"to": "<profile id>" | "all", "text"}` (at most 500 characters).
- `POST /api/messages/voice?to=<profile id>`: the recording as body (at most 2 MB, 30 seconds); `GET /api/messages/audio?id=` returns it as Ogg/Opus.
- `POST /api/messages/announce {"speakers": [id], "text"}`, `POST /api/messages/read {"ids"?}`, `POST /api/messages/delete {"ids"?}` (without `ids`: all).
- Notifications: APNs with tag `msg-<id>`, the text comes through `/api/iphone/note` as before. "Who may write to me" (`PUT /api/messages/who`) only in the browser.
- V01.0.206: `to` includes `call` (call name), plus `recent` (last written to, at most 5) and `fav`. `PUT /api/messages/fav {"id", "on"}` sets a favourite (at most 20, also with the app key). `PUT /api/messages/call {"call"}` sets the own call name (browser only). Admin: `GET /api/admin/profiles?q=&show=&sort=&page=&per=` (at most 100 per page), `GET /api/admin/profiles/<id>`, `PUT /api/admin/profiles/<id>/call`.

### Pebble watch

The watch app "Spark" (`app/pebble/speech-spark.pbw`, source in `pebble/`) brings the voice chat to Pebble Time 2 and Core 2 Duo, with the answer as text and through the watch speaker. On Pebble Round 2 the answer is text only. It needs a watch firmware with the speaker API (from about v4.9.170).

1. In the panel under **Profiles**, add a device "Pebble" to your profile and copy its key.
2. On the paired phone, download `http://SPARK:31080/pebble/speech-spark.pbw` and open it with the Pebble app.
3. In the Pebble app, open the settings of "Spark": Spark address (`http://SPARK:31080`) and device key. Settings and "Start App" stay grey while the Pebble app does not see the watch as connected (tab Devices).
4. On the watch: SELECT asks (dictation through the phone), SELECT again stops the speech, long SELECT starts a new conversation. A small face at the top shows whether Spark listens, thinks or speaks; its mouth follows the speech. The watch setting Settings → Sounds & Haptics → Volume caps how loud the app can get.

The phone must reach the Spark, at home over Wi-Fi, on the road through a VPN such as Tailscale. The app uses HTTP because the Pebble app does not trust the self-signed certificate. On the Spark, `POST /api/watch/ask` and `GET /api/watch/poll` serve it: the answer is made like in the voice chat (kept short), the audio is compressed for the small speaker (quiet syllables lifted, peaks softly limited) and goes to the watch as 8 kHz IMA ADPCM.
