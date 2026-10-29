# Speech on DGX Spark

**English** | [Deutsch](README.de.md) · Idea: Dominik Bornhäußer

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/zquu1xu570)

Speech recognition (**Qwen3-ASR**), text to speech (**Qwen3-TTS**), pictures (**FLUX.2 klein**) and an own language model (**vLLM**) as services on an NVIDIA DGX Spark (GB10), plus a web panel with a voice assistant, profiles and monitoring. Runs natively with systemd, without Docker. The panel runs on the Spark itself or on a small computer of its own such as a Raspberry Pi 5. Instead of the own language model, [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38) can still provide it.

| Assistant | Status | Architecture |
|---|---|---|
| [![Assistant](docs/bilder/en-chat.png)](docs/bilder/en-chat.png) | [![Status](docs/bilder/en-zustand.png)](docs/bilder/en-zustand.png) | [![Architecture](docs/bilder/en-technik.png)](docs/bilder/en-technik.png) |

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
| Update | button in the panel under *Settings → Update*, or `sudo speech-spark update` |
| Show addresses and keys | `sudo speech-spark info` |
| Own language model | `sudo ./install.sh --llm`, then `sudo speech-spark modelle llm uebernehmen` (back: `… zurueck`) |
| Workshop (test run, code measurement, diagnosis, repair) | on the model computer `sudo ./install.sh --werkstatt`, then *Features → Workshop* |
| Screen in remote access (guacd) | on the computer with the panel `sudo ./install.sh --fernbild`, then *Features → Remote access to servers → Screen* |
| Move the panel to another computer | `sudo speech-spark umziehen --code`, see [Spark split](docs/en/spark-split.md) |
| Uninstall | `sudo ./uninstall.sh` (config, models and voices stay; `--purge` removes everything) |

All options for running without questions (`--mode api --asr 1.7b --tts 0.6b --yes` …) are in [Installation in detail](docs/en/installation.md).

## Latest changes

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.1.243** https without TLS session tickets (`panel.tls_context`): about one https connection in a hundred to Python 3.11's asyncio loop hung after the handshake (a Fernzugang terminal never opened); test servers with the panel's TLS plus a guard, Fernzugang tests with a 60 s handshake and deadlines instead of loops
- **V01.1.242** Knowledge store faster (step 1 of 4, no new feature): document search vectors as float16 in memory (half the size, same ranking), the knowledge book finds pages through an FTS5 index (kept by triggers, built once, without FTS5 as before), the knowledge map picks its part with WITH RECURSIVE in SQLite, plus fixed queries rund_um and weg and the read function wissensbuch.liste (page ids with rank)
- **V01.1.241** AI Dungeon Master: one sorting for every typed action: all word lists in one module, every action gets exactly one kind by a fixed order; "Dann gehe ich los", "Wir schlagen hier unser Lager auf" and "We rest by the fire" are no attack any more
- **V01.1.240** AI Dungeon Master: every value the model gives hangs on a fixed rule (anchor table), the game page knows every value of the panel, a protocol checker checks every narration once more and turns copied rounds into test cases, the narrator bench plays 15 turns in a row; a thing or a writing counts only when the narration shows it
- **V01.1.239** AI Dungeon Master: sentence bench: about 300 fixed player sentences every word list must sort right; "I open the book", "staff" or "I set sail" are no attack any more, abilities are no longer named like spells
- **V01.1.238** AI Dungeon Master: unique spell names, everyday words marked
- **V01.1.237** Quick test: `tools/vorpush.py` installs missing system packages of GitHub "Tests" (guacd, x11vnc, Xvfb for test_fernbild) itself or stops before the first test with the exact command; a cloud container without x11vnc went red mid-run
- **V01.1.236** AI Dungeon Master: faults of the round in the Old Library: the dice bar names the same difficulty as the card, a damage spell claims no hit, sentences about the panel leave the story, "enter" is walking, a merchant only when the story shows one
- **V01.1.235** AI Dungeon Master: a word for "no name" such as "keine", "nobody" or "unknown" never becomes a person, such a card of a running round goes away
- **V01.1.234** AI Dungeon Master: in the settlement window a house's picture stands whole as a square beside name and line instead of cut off as a band




All versions: [CHANGELOG.md](CHANGELOG.md)

## How it works

```mermaid
flowchart LR
  subgraph Clients["Devices and apps"]
    B["Browser and phone,<br/>iPhone and Android app,<br/>Companion for Windows/Mac"]
    T["Terminal client spark-tui<br/>e.g. on the uConsole"]
    X["ESP32 speakers,<br/>HA Assist via Wyoming :31003,<br/>phone (SIP), Telegram,<br/>Siri, Pebble"]
    M["MCP programs<br/>Claude, n8n, Open WebUI"]
  end
  subgraph Panel["Panel computer: the Spark or a Raspberry Pi 5"]
    G["Web panel :31443<br/>login, 2FA, passkeys,<br/>profiles, releases"]
    R["Router: tool choice<br/>by fixed rules"]
    K["Own knowledge: documents,<br/>reMarkable, memory"]
    S["Guard netguard<br/>allowed targets only"]
    LOG["Request log, live,<br/>backup, update after test"]
    NB["Emergency mode with Parakeet<br/>while the DGX is away"]
  end
  subgraph Spark["DGX Spark: model computer"]
    ASR["Speech recognition :31001<br/>Qwen3-ASR or Parakeet"]
    TTS["Speech output :31002<br/>Qwen3-TTS, own voices"]
    LLM["LLM-Tor :31006<br/>own language model (vLLM)"]
    IMG["Pictures :31005<br/>FLUX.2 klein"]
    MUS["Music :31004<br/>ACE-Step 1.5"]
    WS["Workshop: sandbox without network<br/>or data, tests and OpenCode"]
  end
  subgraph Out["Services and sources"]
    E["Home Assistant, calendars,<br/>mail, weather, parcels, transit"]
    Q["SearXNG, Kiwix, Wikipedia,<br/>reMarkable cloud, MCP servers"]
  end
  A["Open WebUI, own apps"]
  B --> G
  T --> G
  X --> G
  M -->|"MCP server /mcp"| G
  G --> R
  R --> K
  R --> S
  S --> E
  S --> Q
  G ==>|"sound, text, pictures;<br/>split: through the TLS-Tor"| Spark
  A -->|"API key"| Spark
```

1. You speak into your phone, browser, one of the apps, the terminal client, a speaker or the phone. The panel signs you in, sends the audio to **speech recognition** and gets text back.
2. The **router** picks by fixed rules which tools the question needs. The panel passes the text, with memory, conversation history, your own knowledge and exactly those tools, to the **language model** behind the LLM-Tor (or to qwen38 if you keep it).
3. When the answer needs calendars, mail, weather, Home Assistant, web search, Kiwix or Wikipedia, the panel fetches the data itself; switching and adding entries only happen after you confirm. Pictures are painted and edited by FLUX.2 klein on the Spark; music is made by ACE-Step 1.5 (at first only “Test music” for the admin under State → Checks).
4. The answer goes sentence by sentence to **text to speech** and is played as a stream while the model is still writing. Priority makes sure spoken answers and important people go first.
5. With the **Spark split** the panel, profiles, chats and calls live on the small computer and reach the models only through the TLS-Tor. If the DGX restarts or is switched off, chats, reminders and calls keep running, and emergency mode understands a few fixed commands without a language model.
6. Other apps use ASR and TTS directly through the OpenAI-style APIs with an API key, MCP programs use the Spark as an MCP server with their own access.

Every new feature is off by default. Once the admin releases it, it applies to every profile at once; only the admin can block single profiles. Guests get questions and answers only, never a tool. Updates only go live after a green self-test and can be rolled back.

## Read more

- [Installation in detail](docs/en/installation.md): install modes, the `speech-spark` command, all options, update, uninstall
- [Spark split](docs/en/spark-split.md): the panel on a computer of its own such as a Raspberry Pi 5, moving, emergency mode
- [Assistant and panel](docs/en/assistant.md): voice chat, phone, features, menu
- [APIs and integration](docs/en/apis-and-integration.md): transcription, speech, streaming, Open WebUI, Siri, Pebble, terminal client
- [iPhone app](docs/en/iphone-app.md) and [Android app](docs/en/android-app.md): chat, calls, panel areas on the phone
- [Security and operation](docs/en/security-and-operation.md): login, lockouts, backups, watchdog, self-test, logs
- [Architecture](docs/en/architecture.md): parts, the way of a request, every storage place (also in the panel under Status → Architecture)
- [Technical details and troubleshooting](docs/en/technical.md): services and ports, benchmarks, own language model or qwen38, troubleshooting
- [Coding guideline](docs/en/guidelines.md) and [security checklist](docs/en/security-checklist.md): rules for every change, checklist for new features

The panel has its own guide for every feature under *Funktionen → Anleitungen* (Features → Guides).

## Support

The project is free. If you like it, you can support it at [buymeacoffee.com/zquu1xu570](https://buymeacoffee.com/zquu1xu570).

## License

FSL-1.1-MIT (Functional Source License), see [LICENSE](LICENSE). You may use, read, change and share the Spark for yourself, your family and friends, for teaching and research; the only thing not allowed is offering it as a competing commercial product. Every version turns MIT on its own two years after its release. Versions up to V01.0.542 remain under MIT. Third-party parts included (e.g. XiaoZhi firmware, Lucide icons) keep their own license. The models (Qwen3-ASR, Qwen3-TTS) and packages (vLLM, vllm-omni, PyTorch) are downloaded during installation and come under their own licenses. This project is not affiliated with NVIDIA or the Qwen team.
