# Technical details and troubleshooting

← [README](../../README.md)

## What gets installed

| Part | Where | Port |
|---|---|---|
| Answer comes as text only | If it says "The browser is not playing sound right now", tap once (browsers allow sound only after a touch, iOS pauses it during calls). Otherwise look for "chat: tts HTTP …" or "chat: tts failed" in the diagnosis log (filter "chat:") and for "watchdog:" under errors: speech output was not ready or was restarted. |
| Clicks or cut-off word endings in the assistant | Since V01.0.124 the browser fades every end and every stall over 5 ms. If a word still ends cut off, it is the engine itself: listen to the same text via Telegram or `curl` on port 31012 (without streaming). If the assistant shows "stalls at …" under the answer, speech output fell behind; the diagnosis log (filter "chat:") then shows "chat: tts behind by … s", a broken stream "chat: tts stream broke" (the piece is tried once more, the rest of the answer is still spoken). |
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

Since V01.0.163 every value gets a level (very good, good, tight, too slow) and a sentence saying when it is good; an overall verdict sits on top, and the last run is shown next to each value. The borders are fixed rules in `bench.rate()`: first audio 0.5/1/2 s, voice speed 2×/1.3×/1× real time, several at once (total ÷ count) 1.5/1/0.7, latest first audio with several 1/1.5/3 s, test sentence recognised in 1.5/3/5 s, words understood 95/90/85 %, free memory 14 GiB good, 10 GiB tight, below critical. "Words understood" is missing with `--audio` (the text of your own recording is unknown). The last ten runs' key numbers are kept in `bench-history.json`.

The benchmark goes through the public ports, so it measures what apps see. The last result is stored in `/var/lib/speech-spark/state/bench-latest.json`.

## Next to dgx-spark-qwen38

- **Ports**: qwen38 uses 30000 to 30099 (engine 30000, proxy 30001, image 30020, video 30022, cockpit 30090/30091). Speech uses 31001, 31002, 31080 and 31443 (panel over https); the engines on 31011, 31012 and 31013 listen on 127.0.0.1 only. The panel rejects ports in qwen38's range, and the installer stops if a port is taken.
- **Memory**: the GB10 has one 128 GB pool shared by CPU and GPU. The qwen38 lanes reserve a fixed share of it: 50 % with `stock`/`fp8`, 76 % in 1M mode and 85 % with `flash`. According to the qwen38 docs only ~16.6 GiB stay free at idle with `flash`, and below ~8 GiB DGX OS's earlyoom kills processes. Therefore:
  - If the installer detects a flash or 1M lane, it picks the 0.6B models.
  - Before a service loads its model it checks that the reserve stays free afterwards (default 10 GiB). If not, it does not load and the panel shows `blocked` with the reason.
  - If memory still runs short, the system kills the panel first (`OOMScoreAdjust=900`), then the speech services (500), not the LLM lane and not sshd (see "Speech first").
  - Speech starts after the qwen38 lanes, so they take their fixed share first.
  - Engines start one after another, because vLLM measures free memory at start-up and parallel starts take each other's share.
- **Lane switch**: if you switch to `flash` in the cockpit, already loaded speech models stay in memory. With 1.7B models that can get too tight. Stop ASR and TTS in the panel first or switch them to 0.6B.
- **GPU time**: ASR and TTS share the GPU with the LLM. During a transcription or speech request the LLM gets a little slower.

## Speech first

Speech recognition and speech output always come first (fixed rule without a switch, since V01.0.225, plan `plaene/vorrang-sprache.md`).

- **When "speech is running"**: while an answer of `/api/chat` streams (browser, app, speakers, Telegram, Siri) and while ASR or TTS handle a request from anyone (Open WebUI and Wyoming too). The services report it through `common.SpeechMark`: every `POST /v1/audio/...` request that passed the size limit and API key touches `state/speech-active`. 20 seconds after that still count (follow-up question).
- **Background work** waits during that time; its running request to the language model is cancelled (vLLM stops it when the connection closes) and repeated in the next pause, at most three times. Only one background request runs at a time. Connected: learning from conversations, memory tidy, agents, proactive notes, daily briefing, mail sorting, quality test, reading documents and meaning search (`wissen.quiet()`), backup (also with low CPU priority).
- **Interface for new background work** (`app/panel/vorrang.py`):
  - `r = await vorrang.post(c, "Name", url, json=..., headers=...)`: one request to the language model (httpx client `c`): waits, runs alone, is cancelled on speech and repeated; gives up with `vorrang.Busy` after three cancellations.
  - `await vorrang.run("Name", lambda: coroutine())`: the same for any other coroutine.
  - `await vorrang.quiet("Name")`: only wait for a pause.
  - `await vorrang.in_thread("Name", fn, *args)`: CPU work (e.g. an embedding model) after a pause in its own thread with `nice 15`.
  - `vorrang.hold("Name")`: inside a worker thread, wait between two steps while speech runs (never call it on the event loop).
  - `vorrang.speaking()`: whether speech is running.
- **Operating system**: the ASR and TTS services and their engines run with `Nice=-5`, `CPUWeight=1000`, `IOWeight=1000`. When memory runs out, the system ends the panel first (`OOMScoreAdjust=900`), then the speech services (500), not the LLM lane and not sshd.
- **GPU**: the GB10 has no priorities between processes. The speech engines' memory is reserved from their start. The language model's own answer runs at the same time as the speech output and sometimes slows it down ("tts behind … inside the piece").
- **Checking**: Zustand → Prüfen → "Speech first" speaks a sentence alone, under load without priority and under load with priority, and shows first audio, real-time factor and recognition time, above it today's counters. Zustand → Logs shows the lines in the area "Priority" (`vorrang: … wartet`, `… abgebrochen`, `… wartete N s`).

## Priority for people

When several people talk at once, chosen profiles get their answer first (since V01.0.282, plan `plaene/vorrang-personen.md`). Off by default.

- **Switching on**: Funktionen → Gespräch → "Vorrang für Personen" (`chat.person_priority`, feature register `vorrang`). Only the admin sets the stage per profile under Personen und Geräte → profile → Rechte → Vorrang: "Vorrang" (three profiles at most), "normal" or "hinten anstellen" (last in line). Stored in `state/personen-vorrang.json` (in the backup), changes in the admin log (`person_priority`). Under Ich the profile sees the function as on or "off for you".
- **Who asks**: only from the sign-in (browser, app, device key), never from the text. Guests and programs without a profile (Open WebUI, Wyoming) are always normal. At a shared speaker the stage counts only when the speaker recognition heard the profile's voice; the recording itself goes to the recognition as normal there, because the voice is known only afterwards.
- **Speech output and recognition**: both services let only as many requests go to the engine at once as it takes (`tts.engine_max_seqs`, `asr.engine_max_seqs`); the rest wait in the service (`common.PrioGate`) by stage, then by arrival. A running request is never stopped. Every 4 s of waiting move a request one stage up, so nobody starves. At most 64 wait, else 503. A slot comes back after 90 s at the latest, even when a device dropped the connection before its stream began.
- **Language model** (since V01.0.284): while an answer with priority has no first sentence yet, new rounds of other people wait at most `chat.person_priority_wait` seconds (0–5, default 2) before they go to the language model (`stufe.wait_turn`). Running answers are never stopped; an answer without a first sentence holds others for 30 s at most. Logs → Anfragen shows "waited … for an answer with priority" at the round, journal `vorrang: Antwort wartete N s auf eine Antwort mit Vorrang`.
- **Early notice**: the browser and the iPhone app send `POST /api/vorrang/spricht` when a recording starts (profile or device key, at most 60 per minute). If the profile has priority, background work stops at once and the language model gate closes for 15 s at most, until the question arrives. The answer is the same for everybody, so it does not tell who has priority. Shared speakers do not send it.
- **Who may say the stage**: only the panel. It sends `X-Spark-Stufe` (0, 1, 2) together with the key from `state/vorrang-key` (made once by the panel, mode 0600, not in the backup). The services believe it only from 127.0.0.1 and only with that key; everybody else is normal, even with the API key.
- **Seeing it**: Zustand → Logs → Anfragen shows "with priority" at the arrival and, at speech output, how long the sentences queued and how many they overtook. Journal: `vorrang: Stufe 2 überholt N wartende Anfrage(n)`. The services' `/health` shows slots, waiting requests and counters under `queue`.
- **Measuring**: Zustand → Prüfen → "Speech first" also measures the case "two people at once": the speech output is full with sentences of others (all slots plus two waiting), then one more sentence comes, once normal and once with priority. It shows the first audio of both.
- **Limits**: the language model (qwen38) knows no order; Open WebUI and other programs that ask it directly are not held back. With one person talking nothing gets faster.

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

## Settings page building blocks

Since V01.0.207 all pages under Settings are built the same way (`index.html`, style in `app.css`). New settings use only these parts:

- **Row from JavaScript** (since V01.0.270): `setRow(l, h, ctl, {why, extra})` and `tglIn(attrs, on)` in `base.js` build every row, whether Ich → Gespräch, presets, weather/contacts, speaking up or speakers. `why` locks the row visibly with a reason ("Switched off by the admin") instead of hiding it.

- **Header**: `<h2 class="pt">` and below it `<div class="pintro">` with one sentence on what the page controls.
- **Section**: `<h3 class="sec">Name <span>hint</span></h3>`.
- **Row**: `<div class="setrow"><div class="lbl"><b>Name</b><span>one sentence</span></div>control</div>`, the control on the right: switch `.tgl` (no `label.chk` check boxes), short number `input.num` in `.ctl` with `.unit`, address `input.wide`, choice `select.wide`; several fields in `.ctl.full`. Text areas come after the row.
- **Help**: at most one visible sentence (≤ 140 characters); the rest in `<div class="fh more" hidden>` right after the row, plus `<button class="mlink" type="button">Mehr</button>` in the sentence.
- **Advanced**: always `<details class="adv"><summary>Erweitert <span class="mut">· what is inside</span></summary>`.
- **Instant actions** (password, second step, sign out, update, backup): a section of their own, "acts at once, without saving"; everything else is collected by the page's save bar `.savebar`.
- **At a glance**: new pages get a line in `glanceText()` (`admin.js`), only from data the panel already has.
- **Menu** (since V01.0.265): Zustand (Monitoring, Prüfen, Logs), Funktionen (features, guides), Personen und Geräte (profiles and devices, apps and interfaces), Einstellungen. New parts under Zustand (e.g. a check button or a logs tab) go as a section into `#test` or a tab into `#logs`; a new sub-page gets a line in `GROUPS` (`base.js`) with one sentence in `SUBDESC`. Funktionen is the page `pane-feat` of the settings form, shown without the settings menu (`goSec('feat')`, class `featmode`); `goCfg('feat')` leads there, `goSec('sys')` to Settings → Update and backup.
- **Search** (`find.js`, Ctrl K): finds by itself every page from `GROUPS` and `#cfgnav`, every settings row (`.setrow .lbl>b`, `h3.sec`, `summary`), every Ich page (`ME_ITEMS`), headings and buttons under Prüfen, tabs under Logs and every guide. New parts need nothing of their own as long as they use these building blocks.
- **Frame**: content that continues below a row (change password, second login step) gets `class="rowtail"`; the line then sits below the content, not between row and content. `html{scrollbar-gutter:stable}` keeps the scrollbar's space, so short pages do not move sideways (V01.0.254).
- **Buttons without inline code** (since V01.0.286, strict CSP): never `onclick="…"` or `<script>` in the page. Static buttons get an id and `$('x').onclick=…`; buttons in generated HTML `${onAttr('name', arg1, …)}` and a line `ON.name=(button, arg1, …)=>…` in the same script (arguments as JSON, through `esc`).

`tests/test_guides.py` (class `BuildingBlocks`) checks this without a browser: title and intro on every page, no `label.chk`, "Erweitert" only as `details`, as many "More" buttons as more texts, short sentences and English translations.

## Features and rights (features.py)

Since V01.0.267 every function the admin can switch is written once in `app/panel/features.py`: name (de/en), group, the admin switches (`chat.*`), the function it builds on (`parent`), the profile's own switch (`profile`), whether guests may ever use it, the Ich page and the guide. Values are still stored under the old names in `config.json` and `settings.json`; only this table knows both.

- **One check:** `features.admin_on(key)`, `features.profile_on(key, uid)`, `features.allowed(key, uid)` and `features.reason(key, uid)` (reason: `spark`, `profile`, `guest`). Modules only ask here (`admin_on`, `usable`, `allowed` are one-liners); what must be set up besides (Kiwix address, agent level) the module registers in `features.READY` or `features.GRANTED`.
- **One list for the pages:** `GET /api/features` (signed in, rate limited) returns every function with Spark on/off, own switch, "may" and reason; guests see only guest functions. The flags in `/api/whoami` and `allow` in `/api/profile/settings` and `/api/iphone/settings` come from the same table.
- **New function:** an entry in `features.py`, a guide in `guides.js`. `tests/test_features.py` fails when a `chat.*` switch belongs to no function, a profile switch does not start off, or a module builds its own check.
- **Values in one place** (since V01.0.268): `common.load_config()` fills every missing key from `config.default.json` (like `jq '.[0] * .[1]'` in install.sh); a second default in code (`.get(k, other)`) and hand merges fail the self-test. What applies to a profile comes only from `profiles.effective(uid)`: the admin's presets (`chat.defaults`) with the profile's own values on top; guests get the presets.
- **Heute** (since V01.0.286): `today.py` builds `GET /api/profile/today` only from `features.allowed`; every card is its own block that is missing when the function is not allowed. Calendars with `asyncio.wait_for` (3 s) and a 5 minute cache per profile and time zone; what is still to set up comes from `onboard.py` ("Los geht's"). The sentences of "Probier mal" come from `guides.js` (`say`), filtered by `/api/features` (`can`).
- Fixed protection rules (secrets never spoken, speech first, the owner's voice at a shared speaker) are no switches and stay rules of their own.
- **Main admin** (since V01.0.275): `core.owner_auth` lets the panel password and the admin mode of a profile with role `owner` through (roles, `/api/audit`, backups); `main_auth` stays only for the password, its second step and *sign out everywhere*. Profile shell: `body.prof` (start.js) shows the admin menu with only Assistent and Ich; `.mainonly` is seen by the main admin profile, `.pwonly` only with the password.
- **App** (since V01.0.272): `GET /api/admin/switches` returns `names` and `groups` for every switch from `features.switch_names()`; the app keeps no list of its own. The app key may read `GET /api/features`; `hands` and `barge` are in `iphone.APP_FIELDS`.
- **Profile detail** (since V01.0.271): `GET /api/admin/profiles/{uid}` also returns `features` (`features.count(uid)`: on / allowed by the Spark), `role`, `main` (is the main admin asking?) and `rights` (agent level, update right, upload space; missing for managers). `PUT /api/admin/agent/levels/{uid}` (`{"level": "" | "read" | "act"}`, logged as `agent_level`) sets one profile's agent level. The profile list carries `guests` (`features.guests()`).

## Keeping the live overview current (live.py)

Since V01.0.312 *Status → Live* (and the monitor `/live`) show everything the Spark does right now. So the picture never lies by leaving something out, every change also adds its entry there:

- **New tool:** a target in `live.TOOLS` (an existing one or a new one in `live.TARGETS` with zone `spark`, `lan` or `net`) and a word in `live.RETURNS`. `tests/test_live.py` turns red when a tool from `chat.py` or an extra service is missing.
- **New kind of device:** a word in `live.CLIENT` (the test compares with `tracelog.CLIENTS`).
- **New channel** (WebSocket, long poll): a line in `live._conns`.
- **New entry check or guard level:** `guard.failed` and `netguard.resolve` already report to `live.refused` and `live.outgoing`; add new words there.
- Only fixed words and numbers, never contents; names only through `live._who`.

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
| Update fails | Panel → Settings → Update and backup → update log. The old version keeps running or is installed again; the log says which. |
| Port taken | Change the port in `/etc/speech-spark/config.json` and run the installer again. |

The per-model memory estimates (`MODEL_GIB` in `app/common.py`) are rough assumptions; correct them with the values the panel shows.
