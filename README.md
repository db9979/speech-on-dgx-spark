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

At the end it prints the address, password and API key, then TTS speaks a sentence and ASR checks it. The panel is at `https://SPARK:31443` (https is needed so the browser allows the microphone).

| Task | Command |
|---|---|
| Update | button in the panel under *Settings → Update and backup*, or `sudo speech-spark update` |
| Show addresses and keys | `sudo speech-spark info` |
| Uninstall | `sudo ./uninstall.sh` (config, models and voices stay; `--purge` removes everything) |

All options for running without questions (`--mode api --asr 1.7b --tts 0.6b --yes` …) are in [Installation in detail](docs/en/installation.md).

## Latest changes

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.353** Spark companion deeper in the computer (per device, all off): right-click on files, ask about the screen, know the app, draft a reply in Outlook and Apple Mail, "Spark-Wissen" folder, buttons in notes, Spark acts on the PC with a question first, wake word on the PC
- **V01.0.352** Live overview full review: update check, NAS backup, reMarkable sheets, Spark-Begleiter, room mode, logins, speaker recognition and more in the picture
- **V01.0.351** reMarkable in the Live monitor: @Spark answer, guide, morning sheet, weekly review, meeting and page check show as background work with a done event, sync as event, web page/attachment as tools
- **V01.0.350** Daily briefing: no more "roomfar: briefing AttributeError" line on every briefing (services without a briefing part are skipped)
- **V01.0.349** Faster answer start: turns without any tool (small talk) get the short request without the tool list again
- **V01.0.348** Morning greeting names appointments only fresh from the calendar: "Guten Morgen" always reads the briefing, appointments marked as over are not named as coming up, and the answer check lets no appointment from an earlier answer through as today's
- **V01.0.347** Spark companion in the Spark look (face as icon, windows like the panel, light and dark), shows new versions and updates itself after a click (the Spark fetches and checks them), link "☕ Support Spark"
- **V01.0.346** reMarkable @Spark: question from handwriting without the reader's "Bild:" line and [unleserlich], the model also answers from its own knowledge instead of just "no answer", diagnosis line "remarkable: @Spark answer …"
- **V01.0.344** More with the reMarkable (admin sub-switch + one per function under Me → reMarkable, all off): morning sheet as PDF with note lines, "@Spark" questions on paper get an answer next to them, tasks from handwriting (reminder only after a click), meeting summaries, week in review on Fridays, web pages and mail attachments to the reMarkable, one inbox per day, a Spark guide to the reMarkable functions and the service that keeps itself up to date
- **V01.0.343** Better Spark help: the switch spots help questions by fixed rules, the help knows every page and frequent questions, a "?" at every switch, and it notes where a question came from (speaker, app, Telegram)

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
- [Technical details and troubleshooting](docs/en/technical.md): services and ports, benchmarks, next to qwen38, troubleshooting

The panel has its own guide for every feature under *Funktionen → Anleitungen* (Features → Guides).

## Support

The project is free. If you like it, you can support it at [buymeacoffee.com/zquu1xu570](https://buymeacoffee.com/zquu1xu570).

## License

MIT, see [LICENSE](LICENSE). The models (Qwen3-ASR, Qwen3-TTS) and packages (vLLM, vllm-omni, PyTorch) are downloaded during installation and come under their own licenses. This project is not affiliated with NVIDIA or the Qwen team.
