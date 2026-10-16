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

In the panel under **Status → Checks**, "streamed" plays audio while it is generated and shows the time to first audio.

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

If Open WebUI runs in Docker on the same Spark, use the LAN IP or `host.docker.internal` instead of `SPARK` (container started with `--add-host=host.docker.internal:host-gateway`). The panel shows these values ready to copy under People and devices → Apps and interfaces.

### AI agents: Hermes Agent and OpenClaw

An agent such as [Hermes Agent](https://hermes-agent.nousresearch.com) (Nous Research) or [OpenClaw](https://docs.openclaw.ai) can use the Spark's speech recognition and speech output. The agent runs on another computer and only gets audio and text to read out, no access to the assistant's profiles, memory or tools. The panel shows ready-made snippets under People and devices → Apps and interfaces.

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

### Spark as an MCP server

Other programs use the Spark over the [Model Context Protocol](https://modelcontextprotocol.io) (Streamable HTTP, the panel's address `/mcp`, e.g. `http://SPARK:31080/mcp`). Off by default.

**Switching on:** admin: Features → *Spark as MCP server*. This works for every profile; only the admin blocks single profiles (Features → Who may do what). Setup in the profile: Me → *Services over MCP* → "Connect a program with a key": name, tools, "Create key". The key is shown once; enter it in the program as the header `Authorization: Bearer <key>`.

| Group | Tools |
|---|---|
| Speech | `transcribe` (audio as base64, at most 10 MB), `speak` (text up to 2000 characters, answer mp3), `voices` |
| Reading | `wikipedia`, `archive_search` (Kiwix), `document_search`, `calendar_events`, `reminder_list`, `today` |
| Ask Spark | `ask_spark`: the profile's assistant, only with the read tools of this access |
| Acting with confirmation | `home_assistant`, `reminder_set`, `calendar_add`, `action_status` (own admin switch) |

**Rules (fixed, no switch):**
- Each access belongs to one profile and can only use the tools the profile gave it and may use itself right now. Never to the outside: mail, memory, earlier conversations, secrets, settings.
- "Home network only" (default): the key works only for requests straight from the LAN, without proxy headers and not from a listed reverse proxy.
- `ask_spark`: the question counts as outside text. Nothing is switched, saved, learned, sent or proposed; nothing of it lands in the conversations.
- Acting: a program only leaves a proposal. The profile gets a notification and decides under Me → Services over MCP ("Yes, do it" with the code window, or "No"). A proposal waits 15 minutes.
- Limits: 60 calls per minute and access (`ask_spark` 10), 2 at once per access, 6 overall; speech runs with the stage "last", people at the Spark go first. Without use an access ends after 90 days.
- The journal shows each request as `mcp-server:` with program, tool and time, never the content.
- Status → Live (since V01.0.334) shows each tool call as its own request "MCP-Client" with tool and target (speech as hearing or speaking, a proposal as "Bestätigung anfragen" → push, a confirmed action as its own request); the access's name shows only with the profile's consent ("My name in the request log"), contents never. `ask_spark` shows like a conversation.

**From outside (OAuth):** admin: *MCP server from outside* below the switch. An access "from outside" needs the profile's second sign-in step and a fresh code. Programs like claude.ai sign in with OAuth 2.1 (dynamic registration, PKCE S256, `/.well-known/oauth-authorization-server`): add a custom MCP connector with `https://your-proxy/mcp` in the program, it sends you to the panel, there you see a warning, pick the tools and confirm with your code. Access tokens last 1 hour, refresh tokens 30 days and are swapped with every use. Everything such a program reads goes to its provider.

**Examples:** Open WebUI: Settings → External tools → "+", type MCP (Streamable HTTP). n8n: node "MCP Client Tool". Programs without a header field: `npx mcp-remote http://SPARK:31080/mcp --header "Authorization: Bearer <key>"`.

### Own MCP services per profile

Since V01.0.363 (plan `plaene/eigene-mcp-dienste.md`) every profile can connect its own MCP services (Streamable HTTP), besides the ones the admin connects for everybody. Only that profile sees and uses them.

**Switching on:** Admin: Features → Agent functions → Services over MCP → *Own MCP services for profiles* (`chat.mcp_own`), below it *… also in background jobs* (`chat.mcp_own_jobs`) and *… with sign-in (OAuth)* (`chat.mcp_own_oauth`); all off. Once released it works for every profile; only the admin blocks single profiles. Setup in the profile: Me → *My MCP services*, enter name, address and key and "Connect service". The profile needs no agent level for this.

**Rules (fixed):**
- At most 5 services per profile, each with at most 30 tools. Every tool is "Off" until the profile sets it to "Read" or "Act after yes". If the service changes a tool's description or inputs, it is "Off" again after "Fetch tools again".
- Never for guests, never for other profiles, never for a foreign voice at a speaker (only when speech recognition surely heard the profile's own voice), over Telegram only with "private data".
- Connecting a service, a new address, a new key: only in the profile's own browser login with a fresh code (second sign-in step, when set up). A new address always needs a new key; all tools are "Off" again then. Keys and sign-in data are kept encrypted (vault), never sent back, never logged.
- Connections through the guard (`netguard.USER`): public addresses with https; home network addresses (also http) only when the admin allows them under Security; the Spark's own services (ports 30000–31099) never.
- "Read": the answer is outside text (framed, the assistant switches and saves nothing more in that answer, never learned). "Act after yes": only a proposal; carried out after a plain "Yes" in the next message from the same device and conversation, for 15 minutes, never after outside text, never in background jobs, not during Notaus stage 2 or "Mein Notaus".
- Limits: 30 seconds per call, at most 2 MB read, 8000 characters to the model, arguments at most 4000 characters, 10 calls per minute and 2 at once per profile.
- Background jobs (with the admin switch and the box ticked at the service): reading tools only, only in jobs with private data.
- Sign-in (OAuth): if the service wants a sign-in, leave the key empty and tap "Sign in at the service". The Spark reads the service's sign-in addresses (protected resource metadata, authorization server metadata), registers there as a program (dynamic registration, PKCE S256, `resource`), the browser signs in at the service and comes back through `/api/mymcp/back` (this address changes nothing, it hands code and state to the signed-in page, 10 minutes, once). Access and refresh token are kept encrypted; the Spark renews the access before it ends.

**Admin:** People and devices → Apps and interfaces → *Profiles' own MCP services*: profile, name, address (host only), number of released tools, last fetched, never a key. "Block" applies at once and also when the profile connects the service again; "Remove" deletes it with its key. Optionally a list of allowed hosts (empty: every public one; an entry also allows its subdomains).

**Visible:** Status → Live shows each call as a step to the target "MCP-Dienste" and under events "MCP: service · host · ok or error · duration", plus connected, removed, signed in, blocked; never question, arguments or answer, never the profile's name. Me → My status shows one row per service (answers, sign-in needed, blocked). The guard's decisions show under Live as always.

### Advanced: MCP server on the NAS

Since V01.0.552 (Synology plan S7, guide only, no code in the Spark). If you would rather offer your files through an MCP program of your own on the Synology than through knowledge folders, [`docs/vorlagen/nas-mcp`](../vorlagen/nas-mcp) has a hardened template for Container Manager: a file server (`@modelcontextprotocol/server-filesystem` behind `supergateway`, Streamable HTTP) with a doorman (nginx) in front that only lets `/mcp` through with the right key.

**Honestly first:** knowledge folders (Me → Storage) are the better way for almost everyone: no third-party program, the Spark reads by itself, everything through the Wächter and in Live. An MCP container is third-party software on your NAS with access to the folder you give it. It is as safe as its dependencies, and you have to build updates yourself. Only use it when you know exactly why.

**What the template fixes:**
- Base images only by digest (`node:22-alpine@sha256:…`, `nginx-unprivileged@sha256:…`), fixed package versions, `npm ci` at build time instead of `npm install` at every start, without install scripts.
- The folder read-only (`/volume1/dokumente:/data:ro`), plus `read_only: true`, `user: "1000:1000"`, `cap_drop: [ALL]`, `security_opt: no-new-privileges`, memory and process limits.
- The file server sits only in the internal network (`internal: true`): no port, no internet. Only the doorman faces outward, and only on `127.0.0.1:8765`.
- Reachable only through the NAS's reverse proxy with HTTPS and a valid certificate (the Spark checks it and refuses a self-signed one). The doorman requires `Authorization: Bearer <key>` and does not pass the key on.

**Setup:**
1. Copy the four files to the NAS (e.g. `/volume1/docker/nas-mcp`). Run `npm install --package-lock-only` once (another computer will do) so `package-lock.json` pins the exact versions.
2. Enter both digests (the commands are in the files), adjust the folder in `compose.yaml`, replace `SCHLUESSEL` in `nginx.conf` with a long random value (`openssl rand -hex 32`).
3. Container Manager → Project → Create, choose the path, take `compose.yaml`, build and start.
4. DSM → Control Panel → Login Portal → Advanced → Reverse Proxy → Create: source HTTPS with its own port or name, destination HTTP `localhost:8765`. Assign a certificate under Security → Certificate.
5. Spark: the admin turns on Features → Agent functions → Services over MCP → *Own MCP services for profiles* and, since the NAS is in the home network, Settings → Security → *Allow home network addresses*.
6. Profile: Me → *My MCP services*: name "NAS files", address `https://<NAS>:<port>/mcp`, the key, "Connect service". Under "Release tools" set only the reading tools (`read_text_file`, `list_directory`, `search_files`, `get_file_info` …) to "Read"; everything that writes, moves or creates stays "Off" (the folder is mounted read-only anyway).

**Off:** remove the service in the Spark (the key is deleted), stop the project on the NAS and delete the reverse proxy rule. A new key: change it in `nginx.conf`, restart the doorman, enter the service again in the Spark with the new key.

### "Hey Siri, ask Spark"

An iPhone shortcut sends the dictated question to `POST /api/siri/ask` (header `X-Speech-Device` with a
device key of your profile, body `{"text": "..."}`) and lets Siri speak the `answer` field. Works without
the page open, also on Apple Watch, AirPods and CarPlay; follow-ups within 10 minutes keep the context,
and each day's questions are kept as a conversation of the profile. Step by step under People and devices → Apps and interfaces and in Features → Guides.

### iPhone app "Spark"

Own iPhone app with the Spark voice and "Hey Siri, Frag Spark", paired by QR code, its own key per iPhone that may only ask and listen. Building, pairing and security: [iphone-app.md](iphone-app.md).

### Chats between profiles (for the iPhone app)

Since V01.0.488 messages between profiles go through chats only; `/api/messages…` no longer exists. With the profile's browser login or the iPhone app's key (header `X-Speech-Device`), only when the admin switched on "Chats" and the profile "Chats with others"; other device keys get 403.
- `GET /api/chats`: `enabled`, `on`, `chats` (each `id, kind, title, unread, mute, last`, the group "Alle" with `fixed`), `contacts` (`id, name, call`), `all` (takes part in "Alle"), `speakers` (for announcements), `max_text`.
- `POST /api/chats/open {"to": "<profile id>"}` returns the `id` of the chat for two; `POST /api/chats/send {"id", "text"}` writes into it (into "Alle" at most 5 an hour).
- `POST /api/chats/announce {"speakers": [id], "text"}`: an announcement on picked speakers (admin switch "Announcements on speakers").
- Browser only: `GET`/`PUT /api/chats/who {"allow"?, "block"?}` ("Who may write to me") and `PUT /api/chats/call {"call"}` (own call name, unique). Admin: `GET /api/admin/profiles?q=&show=&sort=&page=&per=` (at most 100 per page), `GET /api/admin/profiles/<id>`, `PUT /api/admin/profiles/<id>/call`.

### Chats with other Sparks (V01.0.496)

Between Sparks (open, a signature instead of a login): `GET /.well-known/spark-verbund` returns `{"v": 1, "key": "<Ed25519, base64>", "inbox": "/api/verbund/in"}`, only while "Chats with other Sparks" is on. `POST /api/verbund/in` takes JSON up to 32 KB with the headers `X-Spark-From: <sender's domain>` and `X-Spark-Sig: <base64>`; signed is `spark-verbund v1\n<receiver's domain>\n<body>`. Body: `v`, `t` (Unix time, ±600 s), `n` (32 hex characters, once), `type` (`pair`, `ask`, `yes`, `msg`, `read`, `edit`, `back`, `react`, for groups `gadd`, `gmsg`, `gleave`, `gremove`, `gname`, `gmembers`), `from`/`to` (the part before the @), by type `name`, `id`, `text`, `reply`, `emoji`, `secret`. The answer is always `{"ok": true}`, refusals 400/403/409/413/429 without a reason.
For the profile (browser or iPhone app, switches as above): `GET /api/verbund` (own address, QR, contacts with `state` in/out/ok/block), `POST /api/verbund/ask {"addr"}`, `POST /api/verbund/answer {"id", "act": "ok"|"no"|"block"|"unblock"}`, `POST /api/verbund/remove {"id"}`, `POST /api/verbund/open {"id"}` (chat `id`). Admin: `GET /api/admin/verbund`, `POST /api/admin/verbund/pair` and `/connect {"code"}` (second step's code), `POST /api/admin/verbund/peer {"domain", "act": "allow"|"block"|"remove"}`.

Files (V01.0.568, switch "Photos and files to other Sparks"): `POST /api/verbund/blob` with the content as body, `X-Spark-From`, `X-Spark-Blob` (base64url of `{"v": 1, "t", "n", "sha", "size"}`) and `X-Spark-Sig` (signature as for messages over that head); then `msg` with `"media": {"kind": "photo"|"file"|"voice", "sha", "size", "name"?}`. Answers: 200, 400 (form, time, size, hash), 401 (no known, allowed Spark, or off), 403 (signature), 409 (repeated), 429 (daily limit).

Groups (V01.0.568, switch "Groups with other Sparks"): the group belongs to the Spark it was created on; `gid` is its chat id there. From it: `gadd` to one person (`from` is the admin, who must be an accepted contact of that person; `name`, `members` as a list of `{"addr", "name"}`), `gmsg` with `id`, `text`, `reply`, `by` (the author's address) and `byname`, once per Spark, `gremove` to one person, `gname` with `name`, `gmembers` with `members`. To it, with an empty `to`: `gmsg` (`from` is the member, `id`, `text`, `reply`) and `gleave`. The home Spark checks membership and passes a message on to all other Sparks, never back to the one it came from. Text only for now, at most 10 other Sparks per group.

### Calls (V01.0.556)

Only in the profile's own browser (the Android app is one; never with a device key), admin switch "Calls (voice and video)", sound and picture go over WebRTC straight between the devices. `dev` is a random id of the page (12 hex characters), `call` the call's (16 hex characters). `GET /api/anrufe/ice` returns `servers` (empty without "Calls when away", else STUN/TURN with an access for one hour). `POST /api/anrufe/start {"id", "video", "dev"}` → `{"call", "state": "ring"|"busy"|"missed", "servers"}`; `POST /api/anrufe/answer {"call", "dev"}`; `POST /api/anrufe/signal {"call", "dev", "data": {"sdp": {"type", "sdp"}} | {"ice": {…}}}` (16 KB); `POST /api/anrufe/end {"call", "dev", "why": "hangup"|"reject"}` → `{"line"}`. News come over `GET /api/chats/stream` as `call`, `call_ok`, `call_taken`, `call_sig` (with `to`: only that device takes it) and `call_end`.

### Pebble watch

The watch app "Spark" (`app/pebble/speech-spark.pbw`, source in `pebble/`) brings the voice chat to Pebble Time 2 and Core 2 Duo, with the answer as text and through the watch speaker. On Pebble Round 2 the answer is text only. It needs a watch firmware with the speaker API (from about v4.9.170).

1. Pairing with a setup code (new in V01.0.230, off): the admin switches on *Features → Pair the Pebble watch* (works for every profile), the profile picks "Pair a Pebble" under *Me → Pebble watch* and copies the line (valid 10 minutes, once). The watch gets its own key, which only reaches `/api/watch/` and is locked at once when the admin switches the feature off or blocks the profile. Without pairing it still works: add a device "Pebble" under **People and devices** and copy its key.
2. On the paired phone, download `http://SPARK:31080/pebble/speech-spark.pbw` and open it with the Pebble app. Easier: *Me → Pebble watch* shows a QR code for it to scan with the phone camera. When the Spark has a newer watch app, "Neue Uhr-App" shows under an answer at most once a day; reinstalling keeps the pairing.
3. In the Pebble app, open the settings of "Spark": paste the setup code, or enter the Spark address (`http://SPARK:31080`) and device key. Settings and "Start App" stay grey while the Pebble app does not see the watch as connected (tab Devices).
4. On the watch: SELECT asks (dictation through the phone), SELECT again stops the speech, long SELECT starts a new conversation. A small face at the top shows whether Spark listens, thinks or speaks; its mouth follows the speech. The watch setting Settings → Sounds & Haptics → Volume caps how loud the app can get.

The phone must reach the Spark, at home over Wi-Fi, on the road through a VPN such as Tailscale. The app uses HTTP because the Pebble app does not trust the self-signed certificate. On the Spark, `POST /api/watch/ask` and `GET /api/watch/poll` serve it: the answer is made like in the voice chat (kept short), the audio is compressed for the small speaker (quiet syllables lifted, peaks softly limited) and goes to the watch as 8 kHz IMA ADPCM. Watch and phone retry lost messages; after 30 s without a message the watch gives up. At the end the phone sends the times to `POST /api/watch/report`; *Status → Logs* then shows one line `watch: zeit …` per answer in the area "Watch" (dictation, first text, first sound, done, retries, outcome). The watch shows the same face as the panel (robot, comic or comic woman), taken over with the next answer.

### Terminal client (spark-tui)

`spark-tui` (`app/tui/spark-tui.py`, one Python file) brings the chat with your history, *Today* and your jobs, plans and routines into a terminal, e.g. on the ClockworkPi uConsole or over SSH (new in V01.0.646, off).

1. The admin switches on *Functions → Terminal client* (applies to every profile, the admin blocks single ones; never guests).
2. *Me → Terminal* shows a line that fetches the program, checks the checksum (`sha256sum -c` with the value from the page) and sets it up as the command `~/.local/bin/spark-tui` (from V01.0.661; Raspberry Pi OS has `~/.local/bin` in the path after the next login). The window needs Textual in its own environment (`python3 -m venv ~/.local/share/spark-tui && ~/.local/share/spark-tui/bin/pip install textual`, Raspberry Pi OS and Debian refuse pip outside an environment; spark-tui finds it by itself), `spark-tui frage "…"` works without it.
3. "Get a pairing line" (with confirmation code) gives a line `~/.local/bin/spark-tui koppeln 'https://…#tui=…&fp=…'`, valid for 10 minutes and once. In the home network the terminal pins the panel's certificate (`fp`, SHA-256) and sends nothing if it does not match. If you fetch the line over the outside address (reverse proxy with a real certificate), it has no `fp` and the certificate is checked as in the browser. `spark-tui adresse-dazu https://…` adds a second address; the terminal uses the first one that answers. Only `https` works.
4. The terminal keeps its key in `~/.config/spark-tui/geraet.json` (readable only by you). The key is called "Terminal · name", reaches only chat, conversations, Today, the function list and the job pages, and gets 503 while the function is off or the profile is blocked. Jobs follow the profile's agent level. Remove it under *Me → Terminal* or under **People and devices**.

Window: conversations, jobs and Today on the left (below 100 columns only the chat), the chat on the right. F2 conversations, F3 jobs (`n` new job; in a job `d` as document, `x` cancel, Del delete), F4 reload, Ctrl+N new conversation, Esc stops the answer, F10 quit. `spark-tui status` shows address, profile and what the terminal may do. When the Spark has a newer version, the window's head line says "Neue Version …: spark-tui update"; `spark-tui update` fetches it over the paired connection and replaces the program only when the checksum matches the one the Spark names (from V01.0.665). Questions show up in the request history with input "Terminal", *Status → Live* shows the number of open terminals, *Status → Logs* has the `terminal: …` lines in the area "Apps".
