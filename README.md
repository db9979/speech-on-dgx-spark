# Speech on DGX Spark

**English** | [Deutsch](README.de.md) · Idea: Dominik Bornhäußer

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/zquu1xu570)

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
- **Split** (Spark split): the panel on a computer of its own such as a Raspberry Pi 5, the DGX only serves the models. Guide, also for moving: [Spark split](docs/en/spark-split.md).

At the end it prints the address, password and API key, then TTS speaks a sentence and ASR checks it. The panel is at `https://SPARK:31443` (https is needed so the browser allows the microphone).

| Task | Command |
|---|---|
| Update | button in the panel under *Settings → Update and backup*, or `sudo speech-spark update` |
| Show addresses and keys | `sudo speech-spark info` |
| Uninstall | `sudo ./uninstall.sh` (config, models and voices stay; `--purge` removes everything) |

All options for running without questions (`--mode api --asr 1.7b --tts 0.6b --yes` …) are in [Installation in detail](docs/en/installation.md).

## Latest changes

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.627** Phone T2: Me → Phone with own phone numbers (confirmed by code), phone PIN and calls
- **V01.0.626** Phone T1: call the Spark from a phone in the house (FRITZ!Box or another SIP PBX), setup with presets, search and check
- **V01.0.625** Red fix: emergency mode switch only shown with Spark split
- **V01.0.624** Quota: limits per profile for day, week and month at the language model, with a warning and an extra; fixed commands still work
- **V01.0.623** Red fix: tests for the emergency mode with Parakeet
- **V01.0.622** Spark split: emergency mode with Parakeet, fixed commands without a language model
- **V01.0.621** Status → Architecture: overview in zones (devices, Spark, home network, internet), lines light up only on a click, boxes „Spark split“ and „Internet services“
- **V01.0.620** Status → Monitoring: new wide tile "Answers per hour" with bars for the last 24 hours, also in the iPhone app
- **V01.0.619** Spark split: guide and hint after the move under Status → Update
- **V01.0.616** Spark split: pairing with a code (`speech-spark teilen code` and `koppeln`)

All versions: [CHANGELOG.md](CHANGELOG.md)

## How it works

```mermaid
flowchart LR
  subgraph Clients["Devices and apps"]
    B["Browser and phone<br/>app view, notifications"]
    APP["iPhone app with CarPlay,<br/>Android app"]
    X["Pebble, Telegram, Siri,<br/>ESP32 room speakers"]
    W["HA Assist<br/>Wyoming :31003"]
    M["MCP programs<br/>Claude, n8n, Open WebUI"]
    A["Open WebUI, own apps"]
  end
  subgraph Spark["DGX Spark"]
    subgraph P["Web panel :31443"]
      G["Login, 2FA, passkeys<br/>profiles, roles, invitations"]
      R["Router: tool choice<br/>by fixed rules"]
      V["Priority for speech<br/>and people"]
      K["Own knowledge: uploads,<br/>reMarkable, memory"]
      LOG["Request log, backup,<br/>update after green test"]
      S["Guard netguard<br/>allowed targets only"]
    end
    ASR["ASR :31001<br/>Qwen3-ASR or Parakeet"]
    TTS["TTS :31002<br/>Qwen3-TTS, own voices"]
    subgraph Q38["dgx-spark-qwen38"]
      LLM["Language model :30001<br/>text and images"]
    end
  end
  subgraph Out["Services and sources"]
    E["Home Assistant, calendars, mail,<br/>weather, parcels, transit"]
    Q["SearXNG, Kiwix, Wikipedia,<br/>reMarkable cloud, MCP servers"]
  end
  B --> G
  APP --> G
  X --> G
  W --> G
  M -->|"MCP server /mcp"| G
  A --> ASR
  A --> TTS
  G --> V
  G --> R
  V --> ASR
  V --> TTS
  R --> LLM
  R --> K
  R --> S
  S --> E
  S --> Q
```

1. You speak into your phone, browser, one of the apps or a speaker. The panel signs you in, sends the audio to **speech recognition** and gets text back.
2. The **router** picks by fixed rules which tools the question needs. The panel passes the text, with memory, conversation history, your own knowledge and exactly those tools, to the **language model** from qwen38.
3. When the answer needs calendars, mail, weather, Home Assistant, web search, Kiwix or Wikipedia, the panel fetches the data itself; switching and adding entries only happen after you confirm.
4. The answer goes sentence by sentence to **text to speech** and is played as a stream while the model is still writing. Priority makes sure spoken answers and important people go first.
5. Other apps use ASR and TTS directly through the OpenAI-style APIs with an API key, MCP programs use the Spark as an MCP server with their own access.

Every feature can be switched on per profile and is off by default. Updates only go live after a green self-test and can be rolled back.

## Read more

- [Installation in detail](docs/en/installation.md): install modes, the `speech-spark` command, all options, update, uninstall
- [Assistant and panel](docs/en/assistant.md): voice chat, phone, features, menu
- [APIs and integration](docs/en/apis-and-integration.md): transcription, speech, streaming, Open WebUI, Siri, Pebble
- [Security and operation](docs/en/security-and-operation.md): login, lockouts, backups, watchdog, self-test, logs
- [Architecture](docs/en/architecture.md): parts, the way of a request, every storage place (also in the panel under Status → Architecture)
- [Technical details and troubleshooting](docs/en/technical.md): services and ports, benchmarks, next to qwen38, troubleshooting
- [Coding guideline](docs/en/guidelines.md) and [security checklist](docs/en/security-checklist.md): rules for every change, checklist for new features

The panel has its own guide for every feature under *Funktionen → Anleitungen* (Features → Guides).

## Support

The project is free. If you like it, you can support it at [buymeacoffee.com/zquu1xu570](https://buymeacoffee.com/zquu1xu570).

## License

FSL-1.1-MIT (Functional Source License), see [LICENSE](LICENSE). You may use, read, change and share the Spark for yourself, your family and friends, for teaching and research; the only thing not allowed is offering it as a competing commercial product. Every version turns MIT on its own two years after its release. Versions up to V01.0.542 remain under MIT. Third-party parts included (e.g. XiaoZhi firmware, Lucide icons) keep their own license. The models (Qwen3-ASR, Qwen3-TTS) and packages (vLLM, vllm-omni, PyTorch) are downloaded during installation and come under their own licenses. This project is not affiliated with NVIDIA or the Qwen team.
