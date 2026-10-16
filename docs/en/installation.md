# Installation in detail

← [README](../../README.md)

Split install (the panel on a computer of its own such as a Raspberry Pi 5), moving and taking back: [Spark split](spark-split.md).

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
| `sudo speech-spark logs tts -n 100` | last log lines (asr, tts, asr-engine, tts-engine, tts-design, bild, watch, update, messen, all) |
| `sudo speech-spark panel enable` | add the web panel later; models and API key stay |
| `sudo speech-spark panel disable` | remove the web panel; profiles and data stay on disk |
| `sudo speech-spark notzugang` | locked out: new panel password (shown once), the emergency access's second step off (old file kept as `.bak`), the main admin profile unlinked (roles stay); asks first, noted in the change log, push to the admins. Then `https://…/#admin` without a code, set the second step up again, choose the main admin again |
| `sudo speech-spark modelle liste` | the model catalog (`app/modelle.json`): models, kind, memory, whether the revision is pinned |
| `sudo speech-spark modelle messen` | measures the catalog models on this Spark (default: Qwen3.8 27B NVFP4 and Qwen3-VL 8B; `fp8`, `gemma`, `kolibri` on request; Kolibri needs `--kolibri` first). Fetches missing models (Qwen3.8 is copied from qwen38's cache and every file checked), stops qwen38 with a maintenance pause, measures speed, first answer, memory, a tool call and test pictures per model and always starts qwen38 again. Switches nothing, deletes nothing. Result in *Status → Logs* (area System) or `sudo speech-spark logs messen` |
| `sudo speech-spark modelle llm uebernehmen` | moves the chat to the own language model (first `sudo ./install.sh --llm` and one measurement): notes the running qwen38 services and the old address, stops and disables qwen38 (deletes nothing), starts the own model behind the LLM-Tor and checks it (German sentence, tool call, picture, System One). Only then does the chat point at the door; if the check fails, everything goes back by itself |
| `sudo speech-spark modelle llm zurueck` | own language model off, the noted qwen38 services on again, old address back |
| `sudo speech-spark modelle qwen38-aufraeumen` | only after a working move and only on your command: shows what qwen38's own uninstall removes, asks, then runs it. Never automatic, not in an update either |
| `sudo speech-spark teilen [status]` | split install (panel on another computer, since V01.0.608): whether the door (TLS-Tor) is open, for how many panel computers, whether the firewall is set, and the certificate's fingerprint |
| `sudo speech-spark teilen modelle-update` | On the panel computer: start the model computer's own update and wait for it (`update.sh` does this first by itself) |
| `sudo speech-spark teilen code` | On the model computer: show a pairing code (10 minutes, one use) and wait for the panel computer |
| `sudo speech-spark teilen koppeln <name-or-ip>` | On the panel computer: pair with the model computer (asks for the code, remembers its certificate) |
| `sudo speech-spark teilen rundlauf` | On the panel computer: ask the Wärter, TTS speaks a sentence, ASR hears it, all through the door |
| `sudo speech-spark umziehen --code` | On the computer that has the panel now: offer the move (code, move backup with the vault key and the panel's certificate); it changes its role only after "fertig" from the other computer |
| `sudo speech-spark umziehen --von <name-or-ip>` | On the new panel computer: fetch the move, restore, check (also happens when pairing with `install.sh --mode panel`) |
| `sudo speech-spark zurueckholen --von <name-or-ip>` | On the model computer: take the panel back; everything runs on one computer again |
| `sudo speech-spark teilen firewall [aus]` | make the door's ports reachable only from the panel computer (`api.tls_from`, nftables table `speech_spark_teilen`), or off again |

The watchdog for hung services, which otherwise runs in the panel, runs as `speech-spark-watch` with the same rules. After an update, TTS speaks a sentence and ASR has to understand it; if that fails, the update puts the previous version back. The self-tests run before every update in both modes. If the language model still comes from dgx-spark-qwen38, it is not touched; the own language model is updated along. If Open WebUI runs in Docker on the same Spark, the APIs have to be reachable from the network (`127.0.0.1` inside the container is the container itself).

## Updating

In the panel under **System** you see the installed version and, when GitHub has a newer one, the list of changes. **Update installieren** (install update) fetches and installs it. Settings, models and voices are kept, and the log streams live. **Update abbrechen** cancels a running update. Packages that are already installed are not upgraded; only what the new version needs is added. The self-test runs before the new version goes live. If it or an earlier step (download, packages) fails, the update stops and the services keep running the old version unchanged. If something fails after the switch, `update.sh` installs the previous version again and says so in the log. While the update runs, a progress window locks the panel (other tabs and phones too: the server refuses changes, the assistant keeps answering); question, progress and restart stand in this one window: behind it the page keeps still (no band "The Spark is not answering", no version bar), the bar only moves forward, and the window waits calmly across the panel restart. At the end the page loads once and comes back to the same place (Settings → Update). Each state shows only its own buttons: the question Install and Cancel, a running update none; after 45 minutes without finishing it offers Reload and Cancel update, a failed one Close and Copy log. The log stays folded below.

**What's new (changelog)**: every change up to the installed version, one line per version, newest first, with a search. Open it with "Was ist neu" (What's new) at the bottom next to the version number or under *Settings → Update und Sicherung (update and backup) → Was ist neu (Changelog) → View*. The admin and every profile in its own browser login can see it (not guests, not device keys). Versions newer than at the last opening in this browser carry "new". The list comes from `CHANGELOG.md` of the installed version (the update puts a copy into `app/`).

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
| `--mode api --teilen` | Spark split, model computer: only the models, services only on 127.0.0.1, plus the TLS-Tor, the Wärter, the firewall and the door's own certificate (`tor-cert.pem`); shows the pairing code at the end |
| `--mode panel --modelle <name-or-ip>` | Spark split, panel computer (e.g. Raspberry Pi 5): only the panel with `venv-panel` and coturn, no model, no engine; checks 64 bit and Python ≥ 3.11, asks for the code (or `SPEECH_SPARK_CODE`) and runs the round trip afterwards |
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

## Painting pictures (optional)

With `--bild` the installation also installs the picture model FLUX.2 [klein] (only with the web panel; the first install asks, the default is none, `sudo speech-spark models` asks again):

```bash
sudo ./install.sh --bild 4b-q8   # 4B, Q8: ~9 GB disk, ~11 GiB while painting, Apache 2.0 (recommended)
sudo ./install.sh --bild 4b-q4   # 4B, Q4: less memory
sudo ./install.sh --bild 9b-q8   # 9B (also 9b-q4): FLUX Non-Commercial, private use only
sudo ./install.sh --bild none    # off again (the files stay in /var/lib/speech-spark/models/bild)
```

**Own language model (preparation, since V01.0.590):** `sudo ./install.sh --llm` creates `venv-llm` with vLLM for the own language model, `sudo ./install.sh --kolibri` also `venv-kolibri` (vLLM 0.29 with Aleph Alpha's plugin, pinned by its hash). Both stay current with every update. The services `speech-spark-llm`, `speech-spark-llmtor` and `speech-spark-sehen` are set up but only run once `sudo speech-spark modelle llm uebernehmen` (stage E3) switches the own model on; until then qwen38 stays the language model. Logs: `sudo speech-spark logs llm`, `llmtor`, `sehen`.

It builds stable-diffusion.cpp once (`sd-server`, pinned commit, CUDA for the GB10, needs `nvcc` and `cmake`) into `/opt/speech-spark/sdcpp`, downloads the model files with a SHA-256 check into `/var/lib/speech-spark/models/bild` and sets up the service `speech-spark-bild` (only `127.0.0.1`, ports `image.port` 31005 and `image.engine_port` 31015). The model takes memory only while painting. Then switch on Features → Painting pictures in the panel and press "Bild testen". Details: [Assistant](assistant.md).

## Making music (optional, stage M0: measuring)

With `--musik` the installation also installs the music model ACE-Step 1.5 (MIT licence; on the model computer, with a split install together with `--teilen`; the first install asks, the default is none, `sudo speech-spark models` asks again):

```bash
sudo ./install.sh --musik 2b         # 2B turbo + 1.7B planner: ~5.6 GB disk, ~10 GiB while making music (recommended)
sudo ./install.sh --musik 2b-klein   # 2B turbo + 0.6B planner: less memory
sudo ./install.sh --musik xl         # XL turbo (4B) + 1.7B: sounds better, ~16 GiB, measure first
sudo ./install.sh --musik none       # off again (the files stay in /var/lib/speech-spark/models/musik)
```

It builds acestep.cpp once (`ace-server`, pinned commit, CUDA for the GB10, no torch and no Docker, needs `nvcc` and `cmake`) into `/opt/speech-spark/acestep`, downloads the GGUF files with a SHA-256 check into `/var/lib/speech-spark/models/musik` and sets up the service `speech-spark-musik` (only `127.0.0.1`, with a split install through the TLS-Tor; ports `music.port` 31004 and `music.engine_port` 31014). The engine loads only for a song and frees the memory after 10 minutes without one; without enough free memory it does not load. In this stage only the admin measures: State → Checks → "Test music" makes two fixed samples (30 s of piano, 60 s with German vocals) and shows time, memory and both samples to listen to. Profiles cannot order anything yet. Logs: `sudo speech-spark logs musik`, maintenance pause: `sudo speech-spark pause musik 30`.

## Uninstalling

```bash
sudo ./uninstall.sh            # remove services, code, venvs and the sudoers rule; config, models and voices stay
sudo ./uninstall.sh --purge    # also delete config, models, voices and the user speech
sudo ./uninstall.sh --yes      # no confirmation prompt
```

dgx-spark-qwen38 is not touched; the own language model (`venv-llm`) goes with `uninstall.sh`.
