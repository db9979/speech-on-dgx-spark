# Speech on DGX Spark

**English** | [Deutsch](README.de.md) · Idea: Dominik Bornhäußer

Speech recognition (**Qwen3-ASR**) and text to speech (**Qwen3-TTS**) as services on an NVIDIA DGX Spark (GB10), plus a web panel with a voice assistant, profiles and monitoring. Runs natively with systemd, without Docker, next to [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38), which provides the language model.

## Installation

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

The script asks what to install:

- **Complete**: models, APIs and the web panel with the assistant.
- **Only the models with their APIs**: for Open WebUI, your own apps or Home Assistant, without the panel. Managed with `sudo speech-spark`.

At the end it prints the address, password and API key, then TTS speaks a sentence and ASR checks it. The panel is at `https://SPARK:31443` (https is needed so the browser allows the microphone).

| Task | Command |
|---|---|
| Update | button in the panel under *Settings → Update and backup*, or `sudo speech-spark update` |
| Show addresses and keys | `sudo speech-spark info` |
| Uninstall | `sudo ./uninstall.sh` (config, models and voices stay; `--purge` removes everything) |

All options for running without questions (`--mode api --asr 1.7b --tts 0.6b --yes` …) are in [Installation in detail](docs/en/installation.md).

## Latest changes

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.268** Unify phase 2: defaults only from config.default.json (load_config fills missing keys), presets and own values only through profiles.effective; self-test against second defaults and hand merges
- **V01.0.267** Unify phase 0–1: every function once in features.py, one check "Spark on, profile on" for all modules, /api/features with the reason; gaps closed (learning from corrections needs memory, push and update need the iPhone app, room from afar needs speakers)
- **V01.0.266** Kiwix: "look in your/our archive" and "in the archive" are recognised; the first round must then ask the archive instead of the uploaded documents
- **V01.0.265** Menu: Funktionen is its own entry (with guides), "Personen und Geräte" (with apps and interfaces), "Einbinden" is gone; Ctrl K/⌘ K search across pages, switches, settings, Ich, checks, logs and guides
- **V01.0.264** Look locally first (Features → Web search, off; profile switch): knowledge questions first look in documents, the Kiwix archive and earlier conversations (at most 400 ms, hits as data with their source), current things go straight out, "in my documents" stays local; web search after documents only with the words of the question; Status → Checks → "Test looking locally first", log line "lokal:"
- **V01.0.263** Logs → Requests (switch under Settings → Operation, off): the way of every request as a list with a bead chain and a time line (switch, model rounds, tools, check, speech output, first sound), without question or answer text; names only with the profile's consent
- **V01.0.262** Security: protection headers on every answer (no embedding in other pages, nosniff, referrer policy, microphone/camera only for the panel, HSTS on https), list of signed-in browsers with single sign-out (Me → Security, admin in the profile details), profile sign-in ends after 30 days without use (7–90 adjustable), "Security at a glance" as a traffic light at the top of Settings → Security
- **V01.0.261** Kiwix: books are saved without their date, updated files stay chosen (the newest is used, catalog re-read on 404); "Look in my archive" never searches the uploaded documents and says which switch is missing
- **V01.0.260** Kiwix: book choice as a list with search, language and kind filter (German/English first), grouped, with language, variant, article count, size and date; chosen ones on top as chips; without a choice German and English Wikipedia; catalog up to 2000 books
- **V01.0.259** Self-test "Profiles and devices" searches the test device instead of waiting on page 1 (GitHub tests green again)

All versions: [CHANGELOG.md](CHANGELOG.md)

## How it works

```mermaid
flowchart LR
  subgraph Clients["Devices and apps"]
    B["Browser / phone app"]
    A["Open WebUI, own apps"]
    X["Siri, Pebble, Telegram, speakers,<br/>HA Assist (Wyoming :31003)"]
  end
  subgraph Spark["DGX Spark"]
    P["Web panel :31443<br/>assistant, profiles, monitoring"]
    ASR["ASR :31001<br/>Qwen3-ASR or Parakeet"]
    TTS["TTS :31002<br/>Qwen3-TTS"]
    LLM["qwen38 :30001<br/>language model"]
  end
  E["Home Assistant, calendars,<br/>mail, SearXNG"]
  B --> P
  X --> P
  A --> ASR
  A --> TTS
  P --> ASR
  P --> LLM
  P --> TTS
  P --> E
```

1. You speak into your phone or browser. The panel sends the audio to **speech recognition**, which turns it into text.
2. The panel passes the text, with memory, conversation history and the allowed tools, to the **language model** from qwen38.
3. When the answer needs calendars, mail, weather, web search or Home Assistant, the panel fetches the data itself; switching and adding entries only happen after you confirm.
4. The answer goes sentence by sentence to **text to speech** and is played as a stream while the model is still writing.
5. Other apps can use ASR and TTS directly through the OpenAI-style APIs, with an API key.

Every feature can be switched on per profile and is off by default. Updates only go live after a green self-test and can be rolled back.

## Read more

- [Installation in detail](docs/en/installation.md): install modes, the `speech-spark` command, all options, update, uninstall
- [Assistant and panel](docs/en/assistant.md): voice chat, phone, features, menu
- [APIs and integration](docs/en/apis-and-integration.md): transcription, speech, streaming, Open WebUI, Siri, Pebble
- [Security and operation](docs/en/security-and-operation.md): login, lockouts, backups, watchdog, self-test, logs
- [Technical details and troubleshooting](docs/en/technical.md): services and ports, benchmarks, next to qwen38, troubleshooting

The panel has its own guide for every feature under *Einbinden → Anleitungen* (Integrate → Guides).

## License

MIT, see [LICENSE](LICENSE). The models (Qwen3-ASR, Qwen3-TTS) and packages (vLLM, vllm-omni, PyTorch) are downloaded during installation and come under their own licenses. This project is not affiliated with NVIDIA or the Qwen team.
