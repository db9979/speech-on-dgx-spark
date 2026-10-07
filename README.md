# Speech on DGX Spark

**English** | [Deutsch](README.de.md)

Version V01.0.5 · Idea: Dominik Bornhäußer

One script installs **Qwen3-ASR** (speech recognition) and **Qwen3-TTS** (text to speech) as systemd services on an NVIDIA DGX Spark (GB10), together with a web panel for configuration and monitoring. It runs alongside [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38).

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

At the end the script prints the panel address, the panel password and the API key. It then runs a round trip: TTS speaks a sentence (also streamed, with time to first audio) and ASR transcribes it back. Everything runs natively as systemd services, without Docker.

The panel switches between English and German (button at the top right).

## Voice chat

The **Gespräch** tab needs the microphone, and browsers only allow it over https. The panel therefore also listens on `https://SPARK:31443` with a self-signed certificate; the browser warns once. The LLM connection is under Configuration → voice chat (default: qwen38 at `http://127.0.0.1:30001/v1`). The installer takes the qwen38 API key from `~/.config/qwen38/api-key` of the user who runs `sudo ./install.sh`. Thinking is off for the chat so the answer starts right away. An animated assistant face shows whether it is listening, thinking or speaking; its mouth follows the voice. The same face sits in the bottom right corner of every tab, so you can talk from anywhere in the panel.

**Start page and password:** the panel opens with the assistant, without a password, for everyone on the network. Monitoring, settings, voices and logs need the panel password (button "Settings", the login is kept for 30 days). Configuration → voice chat → "Assistant without password" turns this off; the password can be changed under Configuration → Panel. Scripts can still use HTTP Basic.

**As an app on your phone:** open `https://SPARK:31443` in the phone's browser, accept the certificate warning, then use "Add to Home screen" in the browser menu (iPhone: Safari → Share → "Add to Home Screen"). The assistant then starts full screen with its own icon. With the self-signed certificate Android creates a shortcut instead of an installed app; it works the same, it just does not show up in the app list.

**Better recognition:** a fixed default language (Configuration → ASR, e.g. German) instead of "auto" helps most with short sentences. The "Context" field takes names and terms that are often misheard; the model then prefers them. The 1.7B model is noticeably more accurate than 0.6B and needs about 2–3 GiB more memory.

**Conversation comfort:** the assistant knows the date and time (the browser's time zone; can be turned off under Configuration → voice chat). Conversations are kept in the browser and can be reopened or deleted at the top of the conversation. With "live transcript" the text appears while you speak; in the pause the recognition is usually already done, so that step is skipped at the end.

**Web search:** under Configuration → voice chat → web search, enter the address of your SearXNG instance and tick "allow web search". If SearXNG's `settings.yml` allows `json` under `search: formats:`, the panel uses the JSON API, otherwise it reads the normal results page; "Test connection" shows whether it works. The LLM then searches by itself when a question needs current information (the LLM server needs tool calling; qwen38 has it on). The assistant says it is looking it up, reads the top pages and shows the sources under the answer.

**Wake word "Hey Spark":** with the checkbox below the chat the assistant keeps listening. Say "Hey Spark" and it listens; "Hey Spark, what's the weather?" in one go is taken as the question. The browser detects speech bursts, the speech recognition on the Spark checks for the phrase, nothing goes to the internet. The screen stays on; on a phone keep the app in the foreground.

**Conversation settings:** below the face are only "Hey Spark" and "Hands-free"; the "Settings" button next to them opens the rest: listening (stop on silence, live transcript, barge-in and its sensitivity), answer (voice, profiles only; speaking rate, answer length) and display. Guests always hear the default voice. Logged in, the settings live in the profile on the Spark and apply on every device, including speakers with a device key; as a guest only in the browser. "Hey Spark" is set per device because it keeps the microphone and screen awake. Defaults for guests and new profiles are under Configuration → Voice chat. The speaking rate keeps the pitch; it also works for other apps that send `speed` to the TTS API (vllm-omni backend).

**Profiles and memory:** under "Profiles" the admin creates profiles with a name and PIN. In the chat you log in with the "Guest" button at the top of the conversation by typing name and PIN. Logged in, the assistant remembers things for good when you tell it to ("remember that I'm vegetarian") or when they will be useful later, and forgets them on request; the profile button lists what it knows, for deleting. Memory and saved conversations belong to the profile: which profile is asking is decided only by the login (cookie) or the device key, never by the model, and guests get no memory. Speakers and your own programs get a device key under "Profiles → Devices" that belongs to one profile, and send it as the header `X-Speech-Device` to `/api/chat`. A new PIN logs out every browser of that profile; deleting a profile removes its memory and devices. The data lives on the Spark under `/var/lib/speech-spark/users`, one folder per profile.

**Pronunciation:** Configuration → TTS → Pronunciation takes one rule per line, e.g. `DGX = De Ge Ix`. It applies to whole words and to all speech output, Open WebUI included.

**Barge-in:** while the assistant speaks, the microphone keeps listening. Talking for about a quarter of a second interrupts the answer, and what you said becomes the next question. This relies on the browser's echo cancellation; if the assistant interrupts itself on loud speakers, use headphones or untick "barge in" below the chat.

**Your own voice:** under Voices you can record a reference straight from the microphone (read the suggested text, about 10 seconds); the panel fills in the transcript with the speech recognition. Cloning needs a Base model (Configuration → TTS → model `…-Base`), then set the new voice as the default voice. A German reference gives much steadier German than the built-in speakers, which are not native German speakers. Under Voices, one or all of your own voices can be exported as a ZIP (reference audio and transcript) and imported again on this or another Spark; on a name clash the import renames, replaces or skips.

## Logs

All speech services log into their own journal (`journalctl --namespace=speech-spark -u 'speech-spark-*'`), capped at 500 MB and 14 days; journald deletes older entries automatically. Adjustable under Configuration → Logs, effective after the next update. The panel's constant status polls are not logged at all.

## Updating

In the panel under **System** you see the installed version and, when GitHub has a newer one, the list of changes. **Update installieren** (install update) fetches and installs it. Settings, models and voices are kept, and the log streams live. **Update abbrechen** cancels a running update. If the installation fails, the services keep running the old version.

On the console:

```bash
sudo /opt/speech-spark/src/update.sh           # update
sudo /opt/speech-spark/src/update.sh --check   # only show what is new
```

The installer keeps its own git checkout in `/opt/speech-spark/src`, so it no longer matters where you cloned the repo originally.

| Option | Effect |
|---|---|
| `--small` | 0.6B models instead of 1.7B (less memory) |
| `--tts-backend transformers` | TTS via `qwen-tts` without streaming instead of vllm-omni (default: `vllm-omni`) |
| `--asr-backend transformers` | ASR via `qwen-asr`, one request at a time, instead of vLLM (default: `vllm`) |
| `--no-asr` / `--no-tts` | install only one of the two services |
| `--password XYZ` | set the panel password (otherwise one is generated) |
| `--no-download` | download models on first start instead |
| `--no-smoke` | skip the round-trip test at the end |
| `--uninstall` | same as `./uninstall.sh` (see below) |

Running the script again updates code and Python environments. The existing configuration is kept and new settings are added.

## Uninstalling

```bash
sudo ./uninstall.sh            # remove services, code, venvs and the sudoers rule; config, models and voices stay
sudo ./uninstall.sh --purge    # also delete config, models, voices and the user speech
sudo ./uninstall.sh --yes      # no confirmation prompt
```

dgx-spark-qwen38 is not touched.

## What gets installed

| Part | Where | Port |
|---|---|---|
| ASR service `speech-spark-asr` (accepts requests, passes them to the engine) | `/opt/speech-spark/venv-panel` | 31001 |
| ASR engine `speech-spark-asr-engine` (vLLM) | `/opt/speech-spark/venv-engine` | 31011, local only |
| TTS service `speech-spark-tts` (accepts requests, passes them to the engine) | `/opt/speech-spark/venv-panel` | 31002 |
| TTS engine `speech-spark-tts-engine` (vllm-omni) | `/opt/speech-spark/venv-engine` | 31012, local only |
| optional VoiceDesign engine `speech-spark-tts-design` | `/opt/speech-spark/venv-engine` | 31013, local only |
| Update `speech-spark-update` (runs only on demand) | `/opt/speech-spark/src` | |
| Panel `speech-spark-panel` | `/opt/speech-spark/venv-panel` | 31080 |
| Benchmark `speech-spark-bench` | `/usr/local/bin` | |
| Configuration | `/etc/speech-spark/config.json`, password in `panel.env` (a password changed in the panel is stored as a hash in `/var/lib/speech-spark/state/panel-password` and wins) | |
| Models, cloned voices | `/var/lib/speech-spark/hf`, `/var/lib/speech-spark/voices` | |

All services run as the system user `speech`. A sudoers rule lets the panel start, stop and restart the speech services and engines and trigger the update, nothing else.

## The panel

- **Monitoring**: GPU load, free unified memory, temperature and power, CPU, each with history. Per service: status, requests, latency and real-time factor (RTF), plus start, stop and restart. It also shows which dgx-spark-qwen38 lane is running and how much memory it holds.
- **Konfiguration** (configuration): model, port, default language, voice, speaking style, sampling, engine memory shares and memory reserve. Saving restarts the affected services.
- **Testen** (test): upload an audio file to transcribe, or type text and listen.
- **Stimmen** (voices): manage reference recordings for voice cloning (only with a `Base` TTS model).
- **Einbinden** (integrate): values to copy for Open WebUI and other OpenAI-compatible apps, plus curl and Python examples.
- **Gespräch** (talk): voice chat with the dgx-spark-qwen38 LLM. Speak (or type); the answer comes back as text and streamed speech, sentence by sentence while the LLM is still writing. Hands-free mode listens again after each answer; the space bar or "Speak" interrupts. Below the chat you see how long recognition, the first LLM word and the first audio took.
- **Logs**: journald output of the services and engines, with a copy button.

The panel is available in English and German; the button at the top right switches (default: browser language).
- **System**: version, update, benchmark.

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

**Steadier delivery:** Qwen samples with `temperature` 0.9 and `top_p` 1.0 by default, so tempo and emphasis vary from sentence to sentence. The server therefore applies `temperature` 0.7, `top_p` 0.9 and `seed` 42 (Konfiguration → TTS). Requests can override them with the same fields, top-level or inside `extra_params`. In Open WebUI, set response splitting to **paragraphs**: each part is generated separately, and longer parts sound more coherent. Set the default language to a fixed language instead of `auto`.

**Laughing and mood swings:** the model reads emojis, "haha", `*laughs*` and markdown as cues and laughs or changes tone. The server removes them before synthesis (Konfiguration → TTS → clean text, on by default).

**Overacting:** exclamation marks and interjections ("Oh", "Wow") make the voice act out excitement. With "speak calmly" (on by default) the server turns "!" into "." and drops such interjections at the start of a sentence. The default voice-chat prompt also asks the LLM for plain, calm everyday language.

**Numbers:** the server writes numbers out before synthesis, because the model guesses otherwise. Dates, times, money, percent and decimals become words ("on 2026-10-06 at 9:30, $49.90" → "on October sixth, twenty twenty-six at nine thirty, forty-nine dollars ninety"), phone numbers become pairs. Konfiguration → TTS → reading numbers: as words (default), in pairs, digit by digit or unchanged. Works for German and English.

**Speaking style:** `"instructions": "calm and friendly, rather slow"` in the request. Without it, the default instruction from Konfiguration → TTS applies. Only the 1.7B models (CustomVoice, VoiceDesign) follow instructions; the 0.6B models ignore them (per the Qwen model card).

**VoiceDesign** (voice from a description): `"task_type": "VoiceDesign"` and `"instructions": "deep, calm male voice"`. This needs its own model: enable "VoiceDesign zusätzlich bereitstellen" in Konfiguration → TTS. It starts a second engine with the same memory footprint again.

In the panel under **Testen**, "gestreamt" (streamed) plays audio while it is generated and shows the time to first audio.

### General

The services behave like the OpenAI audio API: TTS returns mp3 by default (also wav, flac, opus, pcm), STT understands `response_format=text`, and the language may be an ISO code like `de`. OpenAI voice names like `alloy` fall back to the default voice. If an API key is set in the panel, apps must send `Authorization: Bearer <key>`.

### Open WebUI

Admin Panel → Settings → Audio:

| Field | STT | TTS |
|---|---|---|
| Engine | OpenAI | OpenAI |
| API Base URL | `http://SPARK:31001/v1` | `http://SPARK:31002/v1` |
| API Key | key from the panel, or anything | same |
| Model | anything | anything |
| Voice | | e.g. `ryan` |

If Open WebUI runs in Docker on the same Spark, use the LAN IP or `host.docker.internal` instead of `SPARK` (container started with `--add-host=host.docker.internal:host-gateway`). The panel shows these values ready to copy in the **Einbinden** tab.

## Measuring performance

In the panel under **System → Leistung messen**, or on the console:

```bash
sudo speech-spark-bench                 # time to first audio, speed single and parallel, memory per service
sudo speech-spark-bench --parallel 8    # more concurrent requests
sudo speech-spark-bench --audio a.wav   # speech recognition with your own recording
```

The benchmark goes through the public ports, so it measures what apps see. The last result is stored in `/var/lib/speech-spark/state/bench-latest.json`.

## Next to dgx-spark-qwen38

- **Ports**: qwen38 uses 30000 to 30099 (engine 30000, proxy 30001, image 30020, video 30022, cockpit 30090/30091). Speech uses 31001, 31002 and 31080. The panel rejects ports in qwen38's range, and the installer stops if a port is taken.
- **Memory**: the GB10 has one 128 GB pool shared by CPU and GPU. The qwen38 lanes reserve a fixed share of it (on our box the `stock` lane held about 88 GiB). Below ~8 GiB free, DGX OS's earlyoom kills processes. Therefore:
  - If the installer detects a flash or 1M lane, it picks the 0.6B models.
  - Before an engine loads its model it checks that the reserve stays free afterwards. If not, it does not load and the panel shows `blocked` with the reason.
  - If memory still runs short, the system kills the speech services first (`OOMScoreAdjust=900`), not the LLM lane and not sshd.
  - Engines start one after another, because vLLM measures free memory at start-up and parallel starts take each other's share.
- **Lane switch**: if you switch to a bigger lane in the cockpit, already loaded speech models stay in memory. Stop ASR and TTS in the panel first or switch them to 0.6B.
- **GPU time**: ASR and TTS share the GPU with the LLM. During a transcription or speech request the LLM gets a little slower.

## Why the installation looks like this

- **PyTorch from the cu130 index**: the aarch64 torch on PyPI has no CUDA, so a plain `pip install qwen-tts` would run on the CPU. torch and torchaudio must come from the same index, otherwise `libtorchaudio.so` does not load.
- **No flash-attn**: there is no ARM wheel, and it reportedly does not build for sm_121. Both models use PyTorch SDPA instead.
- **Separate venvs** for the transformers backends: qwen-asr needs `transformers==4.57.6`, qwen-tts `transformers==4.57.3`.
- **ASR with vLLM**: vLLM 0.30 supports Qwen3-ASR natively, with `/v1/audio/transcriptions`, streaming and concurrent requests. It shares the environment with the TTS engine. `qwen-asr[vllm]` is not needed (it would force vllm 0.14).
- **TTS with vllm-omni**: `qwen-tts` cannot stream. The Qwen team points to vllm-omni for streaming. vllm 0.30.0 and vllm-omni 0.30.0 have ARM wheels on PyPI (CUDA 13) and are installed natively, without Docker.
- **Engine memory**: vLLM reserves a fixed share of the *whole* memory pool at start-up, for TTS per stage (talker and code2wav). The defaults (ASR 1.7B 0.06, 0.6B 0.035; TTS 0.04 + 0.025) are kept small so speech fits next to the qwen38 `stock` lane. If a share is too small, the engine stops at start-up with "No available memory for the cache blocks"; raise the share in the panel.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Installer: "torch in venv-… has no CUDA" | Run `sudo ./install.sh` again. If that does not help, delete `/opt/speech-spark/venv-*` and reinstall. |
| Panel shows `blocked` | Not enough memory next to the running qwen38 lane. Switch to 0.6B, lower the reserve (at your own risk) or stop the big lane. |
| Panel shows `error` | Read the message in the panel and under Logs. |
| `no kernel image is available` | A package was built without Blackwell kernels. Check with `/opt/speech-spark/venv-engine/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| Engine does not start | Panel → Logs → engine. With "No available memory for the cache blocks", raise the engine's memory share in the panel. The first start downloads the model and takes longer. |
| Update fails | Panel → System → update log. The old version keeps running. |
| Port taken | Change the port in `/etc/speech-spark/config.json` and run the installer again. |

The per-model memory estimates (`MODEL_GIB` in `app/common.py`) are rough assumptions; correct them with the values the panel shows.

## License

MIT, see [LICENSE](LICENSE). The models (Qwen3-ASR, Qwen3-TTS) and packages (vLLM, vllm-omni, PyTorch) are downloaded during installation and come under their own licenses. This project is not affiliated with NVIDIA or the Qwen team.
