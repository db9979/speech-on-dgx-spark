# Technical details and troubleshooting

← [README](../../README.md)

## What gets installed

| Part | Where | Port |
|---|---|---|
| Clicks or cut-off word endings in the assistant | Since V01.0.124 the browser fades every end and every stall over 5 ms. If a word still ends cut off, it is the engine itself: listen to the same text via Telegram or `curl` on port 31012 (without streaming). If the assistant shows "stalls at …" under the answer, speech output fell behind. |
| ASR service `speech-spark-asr` (accepts requests, passes them to the engine) | `/opt/speech-spark/venv-panel` | 31001 |
| ASR engine `speech-spark-asr-engine` (vLLM) | `/opt/speech-spark/venv-engine` | 31011, local only |
| TTS service `speech-spark-tts` (accepts requests, passes them to the engine) | `/opt/speech-spark/venv-panel` | 31002 |
| TTS engine `speech-spark-tts-engine` (vllm-omni) | `/opt/speech-spark/venv-engine` | 31012, local only |
| optional VoiceDesign engine `speech-spark-tts-design` | `/opt/speech-spark/venv-engine` | 31013, local only |
| Update `speech-spark-update` (runs only on demand) | `/opt/speech-spark/src` | |
| Panel `speech-spark-panel` (complete only) | `/opt/speech-spark/venv-panel` | 31080, https 31443 |
| Watchdog `speech-spark-watch` (only without the panel) | `/opt/speech-spark/venv-panel` | |
| Command `speech-spark` | `/usr/local/bin` | |
| Benchmark `speech-spark-bench` | `/usr/local/bin` | |
| Configuration | `/etc/speech-spark/config.json`, install mode in `mode`, connection details in `connection.txt`, password in `panel.env` (a password changed in the panel is stored as a hash in `/var/lib/speech-spark/state/panel-password` and wins) | |
| Models, cloned voices | `/var/lib/speech-spark/hf`, `/var/lib/speech-spark/voices` | |

All services run as the system user `speech`. A sudoers rule lets the panel start, stop and restart the speech services and engines and trigger the update, nothing else.

## Measuring performance

In the panel under **Status → Checks → Leistung messen**, or on the console:

```bash
sudo speech-spark-bench                 # time to first audio, speed single and parallel, memory per service
sudo speech-spark-bench --parallel 8    # more concurrent requests
sudo speech-spark-bench --audio a.wav   # speech recognition with your own recording
```

The benchmark goes through the public ports, so it measures what apps see. The last result is stored in `/var/lib/speech-spark/state/bench-latest.json`.

## Next to dgx-spark-qwen38

- **Ports**: qwen38 uses 30000 to 30099 (engine 30000, proxy 30001, image 30020, video 30022, cockpit 30090/30091). Speech uses 31001, 31002, 31080 and 31443 (panel over https); the engines on 31011, 31012 and 31013 listen on 127.0.0.1 only. The panel rejects ports in qwen38's range, and the installer stops if a port is taken.
- **Memory**: the GB10 has one 128 GB pool shared by CPU and GPU. The qwen38 lanes reserve a fixed share of it: 50 % with `stock`/`fp8`, 76 % in 1M mode and 85 % with `flash`. According to the qwen38 docs only ~16.6 GiB stay free at idle with `flash`, and below ~8 GiB DGX OS's earlyoom kills processes. Therefore:
  - If the installer detects a flash or 1M lane, it picks the 0.6B models.
  - Before a service loads its model it checks that the reserve stays free afterwards (default 10 GiB). If not, it does not load and the panel shows `blocked` with the reason.
  - If memory still runs short, the system kills the speech services first (`OOMScoreAdjust=900`), not the LLM lane and not sshd.
  - Speech starts after the qwen38 lanes, so they take their fixed share first.
  - Engines start one after another, because vLLM measures free memory at start-up and parallel starts take each other's share.
- **Lane switch**: if you switch to `flash` in the cockpit, already loaded speech models stay in memory. With 1.7B models that can get too tight. Stop ASR and TTS in the panel first or switch them to 0.6B.
- **GPU time**: ASR and TTS share the GPU with the LLM. During a transcription or speech request the LLM gets a little slower.

## Why the installation looks like this

- **PyTorch from the cu130 index**: the aarch64 torch on PyPI has no CUDA, so a plain `pip install qwen-tts` would run on the CPU. torch and torchaudio must come from the same index, otherwise `libtorchaudio.so` does not load.
- **No flash-attn**: there is no ARM wheel, and it reportedly does not build for sm_121. Both models use PyTorch SDPA instead.
- **Separate venvs** for the transformers backends: qwen-asr needs `transformers==4.57.6`, qwen-tts `transformers==4.57.3`.
- **ASR with vLLM**: vLLM 0.30 supports Qwen3-ASR natively, with `/v1/audio/transcriptions`, streaming and concurrent requests. It shares the environment with the TTS engine. `qwen-asr[vllm]` is not needed (it would force vllm 0.14).
- **TTS with vllm-omni**: `qwen-tts` cannot stream. The Qwen team points to vllm-omni for streaming. vllm 0.30.0 and vllm-omni 0.30.0 have ARM wheels on PyPI (CUDA 13) and are installed natively, without Docker.
- **Engine memory**: vLLM reserves a fixed share of the *whole* memory pool at start-up, for TTS per stage (talker and code2wav). The defaults (ASR 1.7B 0.06, 0.6B 0.035; TTS 0.04 + 0.025) are kept small so speech fits next to the qwen38 `stock` lane. If a share is too small, the engine stops at start-up with "No available memory for the cache blocks"; raise the share in the panel.

## How the chat is built

One answer of the assistant runs through three files in `app/panel/`:

- `chat_turn.py` (`prepare`): who is speaking and what they may use (profile, recognized voice, device key, Telegram, iPhone app), the system prompt, answers to waiting proposals ("yes" to an appointment, mail change, correction ...), the tools on offer and the locks after outside text. The result is a `Turn` with all values.
- `chat_tools.py` (`run`): what a tool call does (web search, Home Assistant, mail, calendar, reminders ...). Only offered tools run; the locks are checked here again.
- `chat.py` (`_answer`): asks the language model in rounds, runs tool calls through `chat_tools.run`, checks the answer and streams text and sound. Tool definitions and lock lists (`READS_OUTSIDE`, `LOCKED_OUTSIDE` ...) stay in `chat.py`.

New rights or hints go into `chat_turn.py`, new tools into `chat_tools.py` (definition and lock list in `chat.py`).

## Tests

`app/tests/` holds the self-tests that run on every update (`cd app && python -m unittest discover -s tests`). All services are faked (`tests/helpers.py`); no test talks to real models or Home Assistant. `tests/test_ui_browser.py` also opens the panel in Chromium (Playwright) at computer and phone width: every page without script errors and without sideways scrolling, the settings search, the Me window. Without Playwright (as in the self-test on the Spark) it is skipped; on GitHub it runs in the "Tests" workflow on every push.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Installer: "torch in venv-… has no CUDA" | Run `sudo ./install.sh` again. If that does not help, delete `/opt/speech-spark/venv-*` and reinstall. |
| Panel shows `blocked` | Not enough memory next to the running qwen38 lane. Switch to 0.6B, lower the reserve (at your own risk) or stop the big lane. |
| Panel shows `error` | Read the message in the panel and under Logs. |
| `no kernel image is available` | A package was built without Blackwell kernels. Check with `/opt/speech-spark/venv-engine/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| Engine does not start | Panel → Logs → engine. With "No available memory for the cache blocks", raise the engine's memory share in the panel. The first start downloads the model and takes longer. |
| Update fails | Panel → Status → System and update → update log. The old version keeps running or is installed again; the log says which. |
| Port taken | Change the port in `/etc/speech-spark/config.json` and run the installer again. |

The per-model memory estimates (`MODEL_GIB` in `app/common.py`) are rough assumptions; correct them with the values the panel shows.
