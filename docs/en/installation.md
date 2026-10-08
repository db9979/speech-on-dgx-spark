# Installation in detail

← [README](../../README.md)

## Only the models (without the web panel)

The first install asks in the terminal what to install:

1. **Complete:** models, APIs and the web panel with the assistant (as before).
2. **Only the models with their APIs:** for other services (Open WebUI, your own apps, Home Assistant …), without web panel, password and certificate.

Then it asks which models (speech recognition Qwen3-ASR 1.7B, 0.6B, Parakeet or none; speech output Qwen3-TTS 0.6B, 1.7B or none; VoiceDesign yes or no, each with a rough memory estimate) and whether the APIs should be reachable from the network or only on the Spark itself (`127.0.0.1`, e.g. behind your own reverse proxy). An API key is always generated and required. Later runs and updates do not ask again. Without questions:

```bash
sudo ./install.sh --mode api --asr 1.7b --tts 0.6b --yes   # only the models, reachable in the LAN
sudo ./install.sh --mode api --asr parakeet --tts none --local --yes
```

At the end the addresses, the key and ready-made `curl` examples are printed and kept in `/etc/speech-spark/connection.txt` (readable by root only). Without the panel, the `speech-spark` command does its jobs:

| Command | What it does |
|---|---|
| `sudo speech-spark status` | services, models, free memory, last update |
| `sudo speech-spark info` | addresses, API key, examples, values for Open WebUI |
| `sudo speech-spark key new` | new API key (the old one stops working at once) |
| `sudo speech-spark models` | choose the models again, same questions as the install |
| `sudo speech-spark update` | update like the panel's button (`--check` only shows what is new) |
| `sudo speech-spark logs tts -n 100` | last log lines (asr, tts, asr-engine, tts-engine, tts-design, watch, update, all) |
| `sudo speech-spark panel enable` | add the web panel later; models and API key stay |
| `sudo speech-spark panel disable` | remove the web panel; profiles and data stay on disk |

The watchdog for hung services, which otherwise runs in the panel, runs as `speech-spark-watch` with the same rules. After an update, TTS speaks a sentence and ASR has to understand it; if that fails, the update puts the previous version back. The self-tests run before every update in both modes. The chat model (qwen38) is not part of this repo and is not touched. If Open WebUI runs in Docker on the same Spark, the APIs have to be reachable from the network (`127.0.0.1` inside the container is the container itself).

## Updating

In the panel under **System** you see the installed version and, when GitHub has a newer one, the list of changes. **Update installieren** (install update) fetches and installs it. Settings, models and voices are kept, and the log streams live. **Update abbrechen** cancels a running update. Packages that are already installed are not upgraded; only what the new version needs is added. The self-test runs before the new version goes live. If it or an earlier step (download, packages) fails, the update stops and the services keep running the old version unchanged. If something fails after the switch, `update.sh` installs the previous version again and says so in the log. While the update runs, a progress window locks the panel (other tabs and phones too: the server refuses changes, the assistant keeps answering); the page reconnects across the panel restart and reloads when done. After 20 minutes without finishing it offers Reload and Cancel.

On the console:

```bash
sudo speech-spark update                       # update (or: sudo /opt/speech-spark/src/update.sh)
sudo /opt/speech-spark/src/update.sh --check   # only show what is new
```

The installer keeps its own git checkout in `/opt/speech-spark/src`, so it no longer matters where you cloned the repo originally.

**Once, for installs from before the update button:** run `git pull` and `sudo ./install.sh` in the cloned repo. After that the button works.

| Option | Effect |
|---|---|
| `--mode full` / `--mode api` | complete with the web panel / only the models with their APIs (see above) |
| `--asr 1.7b\|0.6b\|parakeet\|none`, `--tts 0.6b\|1.7b\|none`, `--voicedesign` | choose the models without questions |
| `--local` / `--network` | APIs only on `127.0.0.1` / in the whole network (default) |
| `--yes` | ask nothing; what is not given stays as it is (new: complete) |
| `--small` | 0.6B models instead of 1.7B (less memory) |
| `--tts-backend transformers` | TTS via `qwen-tts` without streaming instead of vllm-omni (default: `vllm-omni`) |
| `--asr-backend transformers` | ASR via `qwen-asr`, one request at a time, instead of vLLM (default: `vllm`) |
| `--no-asr` / `--no-tts` | install only one of the two services |
| `--password XYZ` | set the panel password (otherwise one is generated) |
| `--no-download` | download models on first start instead |
| `--no-smoke` | skip the round-trip test at the end |
| `--uninstall` | same as `./uninstall.sh` (see below) |

Running the script again updates the code and adds what is missing to the Python environments; packages already installed stay as they are. The existing configuration is kept and new settings are added.

## Uninstalling

```bash
sudo ./uninstall.sh            # remove services, code, venvs and the sudoers rule; config, models and voices stay
sudo ./uninstall.sh --purge    # also delete config, models, voices and the user speech
sudo ./uninstall.sh --yes      # no confirmation prompt
```

dgx-spark-qwen38 is not touched.
