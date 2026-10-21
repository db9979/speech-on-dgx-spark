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
| Update | button in the panel under *Settings → Update and backup*, or `sudo speech-spark update` |
| Show addresses and keys | `sudo speech-spark info` |
| Own language model | `sudo ./install.sh --llm`, then `sudo speech-spark modelle llm uebernehmen` (back: `… zurueck`) |
| Workshop (test run, code measurement, diagnosis, repair) | on the model computer `sudo ./install.sh --werkstatt`, then *Features → Workshop* |
| Move the panel to another computer | `sudo speech-spark umziehen --code`, see [Spark split](docs/en/spark-split.md) |
| Uninstall | `sudo ./uninstall.sh` (config, models and voices stay; `--purge` removes everything) |

All options for running without questions (`--mode api --asr 1.7b --tts 0.6b --yes` …) are in [Installation in detail](docs/en/installation.md).

## Latest changes

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.894** Knowledge map (stage 1): the knowledge book gets its own menu entry with Pages and Map; connections between pages, each with its source and checked by fixed rules, "Wrong", export as Mermaid, Graphviz, SVG, PNG and Obsidian links, native map on the iPhone (off by default)
- **V01.0.893** Folders at once and folder menu: the Mail page's folder list is kept sealed in the mail supply and is there at once after a restart; the "⋯" at a folder is a small menu beside it like Apple Mail (right click, a sheet on a phone), renaming and new folders right in the row; iPhone with symbols
- **V01.0.892** reMarkable documents well formatted: lists, numbers, tables, smaller head, device format
- **V01.0.891** Up to date: a stand always names its day („as of yesterday 18:00“), the weather takes „today“ from the clock instead of a forecast of yesterday, the morning briefing names mails with their day and only unread ones, the web search looks within a period with a date per hit for questions about today, and a fixed sentence of the panel says what is not current; an opened mail counts as read
- **V01.0.890** Fix iPhone app: the contact card loads the .vcf file for Share as data (the app did not build since V01.0.888)
- **V01.0.889** CarPlay round 2: no barge-in in the car, „not recognised“ instead of a silent end, drop-outs end nothing, mail and deadlines never hang, „My day“, „Speak a reminder“, briefing when getting in
- **V01.0.888** Contacts like Apple Contacts (stage 3a): a page of its own in the menu with address books as groups, search, A–Z with a letter bar, the card with Message, Call, Mail, Event, Share and "With Anna" (next appointment, latest mail); tapping a mail's sender opens the card; with the admin switch "Edit contacts" (off) editing with − and + per field, back into the own address book with its ETag, new cards also "On the Spark"; iPhone under My things
- **V01.0.887** Load older mail: at the end of the list the next 50 older mails come by themselves, in the inbox and in every folder, down to the first mail; a search goes over the whole mailbox on the mail server; panel, iPhone and spark-tui (up to 200)
- **V01.0.886** Workshop made clear: own page Status → Workshop with four tiles, history and a result that explains what red means and what comes next (find the cause, test only the red ones again, copy for Claude)
- **V01.0.885** Editing music on a page of its own over the whole width: big wave, tools on the left, settings in the middle, versions on the right, the button in a fixed bar at the bottom; the same order on a phone and in the iPhone app




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
