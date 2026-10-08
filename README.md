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
| Update | button in the panel under *Overview → System and update*, or `sudo speech-spark update` |
| Show addresses and keys | `sudo speech-spark info` |
| Uninstall | `sudo ./uninstall.sh` (config, models and voices stay; `--purge` removes everything) |

All options for running without questions (`--mode api --asr 1.7b --tts 0.6b --yes` …) are in [Installation in detail](docs/en/installation.md).

## Latest changes

<!-- New version: add one line at the top here and in CHANGELOG.md, drop the oldest line here (keep 10). Details go to docs/de and docs/en, not into this README. -->

- **V01.0.144** Follow-up without wake word (off, admin + profile): after answering a spoken question the assistant keeps listening for 4–10 seconds, "And tomorrow?" needs no "Hey Spark"
- **V01.0.143** Hands-free listens again even when the browser has paused playback (iOS, no speaker): "still speaking" only counts when something is actually playing; GitHub test green again
- **V01.0.142** Speakers: "Stimme hier anlernen" (three sentences, own voiceprint for the board microphone); "only known voices" applies at a speaker only once a voice was taught there
- **V01.0.141** Web log with diagnostic filters: Overview → Logs → "Diagnostic filters" shows chat:, web search, Home Assistant, room mode, speakers, update/self-test and errors with time range and line count, ready to copy into a thread (instead of journalctl | grep on the console)
- **V01.0.140** Room mode quicker and finds more questions: speaker cuts talk into short pieces, speaks after 1.5 s of quiet, streams the voice; the answer is looked up while people still talk; questions also without a question mark and after "Weißt du, …"; "Also comments" chattier
- **V01.0.139** Room mode ignores TV voices: per device "Who it listens to" (everybody / known voices while the TV is on / always known voices only), with a trial that only counts; admin switch "Ignore TV voices", off by default
- **V01.0.138** Speakers: no more gaps in long answers, new firmware 2.5.1.5 waits when its sound buffer is full instead of dropping sound; the Spark keeps 0.7 s lead
- **V01.0.137** Speakers: sound no longer stutters, the Spark buffers ahead (0.6 s before start, up to 0.9 s lead, after a stall it collects 0.3 s again); stalls show under "Check" and in the log
- **V01.0.136** Speakers: "Check" shows live what the speaker is doing (every 2 seconds), also in room mode (only that a sentence was heard and whether it speaks, never the text)
- **V01.0.135** Speakers: volume and microphone sensitivity per speaker under Me → Speakers (applies at once when connected, otherwise at the next connection)

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
