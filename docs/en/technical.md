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

In the panel under **Status → Checks → Measure performance**, or on the console:

```bash
sudo speech-spark-bench                 # time to first audio, speed single and parallel, memory per service
sudo speech-spark-bench --parallel 8    # more concurrent requests
sudo speech-spark-bench --audio a.wav   # speech recognition with your own recording
```

Since V01.0.163 every value gets a level (very good, good, tight, too slow) and a sentence saying when it is good; an overall verdict sits on top, and the last run is shown next to each value. The borders are fixed rules in `bench.rate()`:

| Value | very good | good | tight |
|---|---|---|---|
| First audio (one request) | up to 0.5 s | up to 1 s | up to 2 s |
| Speed of the voice | from 2× real time | from 1.3× | from 1× (below it stutters) |
| Several at once (total / count) | from 1.5 | from 1 | from 0.7 |
| First audio with several (latest) | up to 1 s | up to 1.5 s | up to 3 s |
| Test sentence recognised in | up to 1.5 s | up to 3 s | up to 5 s |
| Understood correctly (words of the test sentence) | from 95 % | from 90 % | from 85 % |
| Free on the Spark | | from 14 GiB | from 10 GiB (below it critical) |

"Words understood" is missing with `--audio` (the text of your own recording is unknown). The last ten runs' key numbers are kept in `bench-history.json`.

The benchmark goes through the public ports, so it measures what apps see. The last result is stored in `/var/lib/speech-spark/state/bench-latest.json`. The memory shares of the engines (configuration) are starting values: set them to fit after the measurement.

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
- **New hint in `health.alerts`**: add it to `live.hints` too, with its place in the picture and fixed words.
- **New event in the audit log** (`guard.log`): a fixed word in `guard.LIVE_WORDS`, then it shows under events. A line from anywhere: `live.mark(area, text)`; something the Spark does by itself with a service: `live.job(why, tool, t0, ok)`.
- **Interface for new background work** (`app/panel/vorrang.py`):
  - `r = await vorrang.post(c, "Name", url, json=..., headers=...)`: one request to the language model (httpx client `c`): waits, runs alone, is cancelled on speech and repeated; gives up with `vorrang.Busy` after three cancellations.
  - `await vorrang.run("Name", lambda: coroutine())`: the same for any other coroutine.
  - `await vorrang.quiet("Name")`: only wait for a pause.
  - `await vorrang.in_thread("Name", fn, *args)`: CPU work (e.g. an embedding model) after a pause in its own thread with `nice 15`.
  - `vorrang.hold("Name")`: inside a worker thread, wait between two steps while speech runs (never call it on the event loop).
  - `vorrang.speaking()`: whether speech is running.
- **Operating system**: the ASR and TTS services and their engines run with `Nice=-5`, `CPUWeight=1000`, `IOWeight=1000`. When memory runs out, the system ends the panel first (`OOMScoreAdjust=900`), then the speech services (500), not the LLM lane and not sshd.
- **GPU**: the GB10 has no priorities between processes. The speech engines' memory is reserved from their start. The language model's own answer runs at the same time as the speech output and sometimes slows it down ("tts behind … inside the piece"). Since V01.0.430 the panel therefore sends the next piece to the speech output at 5 s of audio in stock while the answer is still being written (times the speaking rate, so 6 s at 1.2; `chat.WRITE_LEAD`), afterwards at 2 to 3 s as before. The iPhone app collects 0.4 s of audio after it ran dry before it plays on, and starts with a 5 ms fade-in after silence.
- **Checking**: Status → Checks → "Speech first" speaks a sentence alone, under load without priority and under load with priority, and shows first audio, real-time factor and recognition time, above it today's counters. Status → Logs shows the lines in the area "Priority" (`vorrang: … wartet`, `… abgebrochen`, `… wartete N s`).

## Priority for people

When several people talk at once, chosen profiles get their answer first (since V01.0.282, plan `plaene/vorrang-personen.md`). Off by default.

- **Switching on**: Funktionen → Gespräch → "Vorrang für Personen" (`chat.person_priority`, feature register `vorrang`). Only the admin sets the stage per profile under People and devices → profile → Rights → Priority: "Vorrang" (three profiles at most), "normal" or "hinten anstellen" (last in line). Stored in `state/personen-vorrang.json` (in the backup), changes in the admin log (`person_priority`). Under Me the profile sees the function as on or "off for you".
- **Who asks**: only from the sign-in (browser, app, device key), never from the text. Guests and programs without a profile (Open WebUI, Wyoming) are always normal. At a shared speaker the stage counts only when the speaker recognition heard the profile's voice; the recording itself goes to the recognition as normal there, because the voice is known only afterwards.
- **Speech output and recognition**: both services let only as many requests go to the engine at once as it takes (`tts.engine_max_seqs`, `asr.engine_max_seqs`); the rest wait in the service (`common.PrioGate`) by stage, then by arrival. A running request is never stopped. Every 4 s of waiting move a request one stage up, so nobody starves. At most 64 wait, else 503. A slot comes back after 90 s at the latest, even when a device dropped the connection before its stream began.
- **Language model** (since V01.0.284): while an answer with priority has no first sentence yet, new rounds of other people wait at most `chat.person_priority_wait` seconds (0–5, default 2) before they go to the language model (`stufe.wait_turn`). Running answers are never stopped; an answer without a first sentence holds others for 30 s at most. Logs → Anfragen shows "waited … for an answer with priority" at the round, journal `vorrang: Antwort wartete N s auf eine Antwort mit Vorrang`.
- **Early notice**: the browser and the iPhone app send `POST /api/vorrang/spricht` when a recording starts (profile or device key, at most 60 per minute). If the profile has priority, background work stops at once and the language model gate closes for 15 s at most, until the question arrives. The answer is the same for everybody, so it does not tell who has priority. Shared speakers do not send it.
- **Who may say the stage**: only the panel. It sends `X-Spark-Stufe` (0, 1, 2) together with the key from `state/vorrang-key` (made once by the panel, mode 0600, not in the backup). The services believe it only from 127.0.0.1 and only with that key; everybody else is normal, even with the API key.
- **Seeing it**: Status → Logs → Anfragen shows "with priority" at the arrival and, at speech output, how long the sentences queued and how many they overtook. Journal: `vorrang: Stufe 2 überholt N wartende Anfrage(n)`. The services' `/health` shows slots, waiting requests and counters under `queue`.
- **Measuring**: Status → Checks → "Speech first" also measures the case "two people at once": the speech output is full with sentences of others (all slots plus two waiting), then one more sentence comes, once normal and once with priority. It shows the first audio of both.
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

- **Row from JavaScript** (since V01.0.270): `setRow(l, h, ctl, {why, extra})` and `tglIn(attrs, on)` in `base.js` build every row, whether Me → Conversation, presets, weather/contacts, speaking up or speakers. `why` locks the row visibly with a reason ("Switched off by the admin") instead of hiding it.

- **Header**: `<h2 class="pt">` and below it `<div class="pintro">` with one sentence on what the page controls.
- **Section**: `<h3 class="sec">Name <span>hint</span></h3>`.
- **Row**: `<div class="setrow"><div class="lbl"><b>Name</b><span>one sentence</span></div>control</div>`, the control on the right: switch `.tgl` (no `label.chk` check boxes), short number `input.num` in `.ctl` with `.unit`, address `input.wide`, choice `select.wide`; several fields in `.ctl.full`. Text areas come after the row.
- **Help**: at most one visible sentence (≤ 140 characters); the rest in `<div class="fh more" hidden>` right after the row, plus `<button class="mlink" type="button">Mehr</button>` in the sentence.
- **Advanced**: always `<details class="adv"><summary>Erweitert <span class="mut">· what is inside</span></summary>`.
- **Instant actions** (password, second step, sign out, update, backup): a section of their own, "acts at once, without saving"; everything else is collected by the page's save bar `.savebar`.
- **At a glance**: new pages get a line in `glanceText()` (`admin.js`), only from data the panel already has.
- **Menu** (since V01.0.265): Assistant and Me for oneself; then Status (Monitoring, Checks, Logs, Live), Features (with Guides and Who may do what), People and devices (with Apps and interfaces), Settings. New parts under Status (e.g. a check button or a logs tab) go as a section into `#test` or a tab into `#logs`; a new sub-page gets a line in `GROUPS` (`base.js`) with one sentence in `SUBDESC`. Features is the page `pane-feat` of the settings form, shown without the settings menu (`goSec('feat')`, class `featmode`); `goCfg('feat')` leads there, `goSec('sys')` to Settings → Update, Backup.
- **Search** (`find.js`, Ctrl K): finds by itself every page from `GROUPS` and `#cfgnav`, every settings row (`.setrow .lbl>b`, `h3.sec`, `summary`), every Me page (`ME_ITEMS`), headings and buttons under Checks, tabs under Logs and every guide. New parts need nothing of their own as long as they use these building blocks.
- **Jump links** (`way.js`, since V01.0.435): every hint with a way like "under Settings → Spark → Operation → Logs “Live page”", "Me → Documents" or "Status → Logs → Requests" turns into a link by itself that opens the place, unfolds it and marks it; for fixed texts, panel messages and the assistant's answers alike. The way is matched step by step against the names on the page (menu, `#cfgnav`, rows, tabs, Me pages from `meAll()`); only what the person may open is linked (admin pages for admins, Me with a profile). A way always starts with Settings, Features, Status, People and devices or Me; a step starting in lower case ("→ switch on") is an action. A way after another "→" ("watch → Settings → …") belongs to another program and stays text. `#weg=<way>` in the address opens a way from outside, also in a page that is already open. **Outside the panel** (since V01.0.448, same rule as `wege.py`): the iPhone app (`SparkAPI.way`) and the Mac companion (`Wege.text`) show the way in their texts and error messages as a link, the Windows companion makes labels, balloon notes, the hint in the tray window and the menu item clickable (`Wege.cs`), the Android app opens the named place when a notification is tapped and the emergency stop tile dialog has "Open in the panel" (`Wege.kt`); a web push notification carries the way along (`push.py`, `sw.js`). Telegram messages with a way get an "Open in the panel" button once the admin enters the panel address for links under Features → Telegram (https only); without an address no button, and if Telegram refuses the button the message goes without it. In an app "Settings → …" counts as a way into the panel only with "panel" right before it, otherwise it is the device's own settings. A #weg= link only opens a place, it switches and sends nothing. `test_sprunglinks.py` collects every way from the scripts, the page and the Python texts and checks in the browser that each finds its place: new hints need nothing of their own, a renamed place turns the test red.
- **Notes on top of the admin pages** (`health.alerts`, since V01.0.447): every note (memory, watchdog, live check, quality test, slow answers, Telegram, service watch) carries with `go` a fixed way to the place where you can look or act; the "View" button jumps there, "Notes are shown above" on Status jumps to the notes. `test_sprunglinks` finds every new note (`kind`, `level`, `text`) without `go` and checks in the browser that each way is found completely.
- **Frame**: content that continues below a row (change password, second login step) gets `class="rowtail"`; the line then sits below the content, not between row and content. `html{scrollbar-gutter:stable}` keeps the scrollbar's space, so short pages do not move sideways (V01.0.254).
- **Buttons without inline code** (since V01.0.286, strict CSP): never `onclick="…"` or `<script>` in the page. Static buttons get an id and `$('x').onclick=…`; buttons in generated HTML `${onAttr('name', arg1, …)}` and a line `ON.name=(button, arg1, …)=>…` in the same script (arguments as JSON, through `esc`).

- **English, errors, "?", names** (since V01.0.408, review of 11.10.2026, B1–B8): every text in `index.html` is in `EN` (`i18n.js`), `title` and `aria-label` too; a sentence with tags inside gets `data-tr` and is in `EN` as a whole (inner HTML). `api()` shows errors as a sentence (`errSay` in `base.js`): a 422 list names the fields, short English answers become sentences, the panel's German sentences come from `EN`; the raw words for checks are in `e.detail` (`errRaw(e)`). A "?" stands only at rows the Spark help knows (`/api/hilfe/ids`); rows from scripts with a field of their own are listed in `hilfe.JS_ROWS`. Fields of a row without a label of their own get the row's title as `aria-label` (`rowLabels`). `tests/test_bedienung_hilfe.py` checks this.

- **Page frame** (since V01.0.416, `js/seite.js`, plan `einstellungen-neu.md`): on load `seite.js` puts the rows between two `h3.sec` into one box `.sgrp` (the heading sits small above it); ids, order and neighbours of the rows stay, so loading, saving, search and "More" work unchanged. A select with 2 to 4 short fixed options becomes segment buttons `.segc` in front of the hidden `select.segsel`, which keeps value, events and id; lists filled from data (profiles, voices, models) stay selects (`data-noseg` turns it off for an area). The save bar stays quiet while nothing changed and floats at the bottom with the names of the changed rows while something is unsaved; changed rows carry a line on the left (`.dirtyrow`). On phones (app view) the face sits small at the top right of the bar outside the conversation. `tests/test_einstellungen_neu.py` checks boxes, segments, face and title bar in a browser.
- **Feature detail** (since V01.0.416, `js/fdetail.js`): when `#pane-feat` is at least 740 px wide (not in the app view) it gets the class `fsplit`; the open `.fitem` moves its rows (all but the first) into `#fdet .fdbody` and back on close, ids stay. `featOpen` calls `featSide`, `featNeed` and `featShow` also look into `#fdet`. "Wer darf es" (`.fwho`, `data-nodirty`) reads `/api/admin/features` and switches over the same endpoints as the table. `presetMove()` (after `renderSet` in `loadCfg`) puts the presets `follow` and `echo` into the feature detail; saving takes only the presets whose row is on that page. Groups: `features.GROUPS` and `GGROUPS` match (test `test_einstellungen_neu`).
- **Me as a page, people, apps** (since V01.0.416, packages 4 and 5): Me keeps `#profmodal` (many places check `display==='grid'`) but on computers looks like the settings: page title `#mepage`, symbols in `#ptabs` (`seite.js meIcons`), no "Schließen". `renderSet` for profiles draws no tabs any more: `meLayout` puts the groups one below the other in boxes (`pageGroup`, `pageSeg`), "Tempo und Genauigkeit" as `details.mefold`, locked rows in `details.melockrows` at the bottom. SETF groups: listening, answer, knowledge and style, speed and accuracy, devices, display, privacy. People: from 740 px card width `.pcard.split`, the open profile in `#pside` (`pSide()` in users.js). Apps: `js/kacheln.js` turns the cards under `#apps` into tiles (`.atile`, open over the full width); tiles with `data-sw` show the switch from `/api/admin/features` and jump there with `whoOpen`.
- **Me pages tidied** (since V01.0.424, `js/ichteile.js`, plan `ich-aufraeumen/plan.md`): shared building blocks `icTabs` (sub-tabs with a count; an orange count needs you and opens first), `icCard` (status card, rare actions in the "⋯" menu `icMenu`), `icRow`/`icList` (title, grey line, small icon buttons), `icCheck` (tick, also half), `icSearch`, `icChip`, `icDanger`, `icStats`; all built with textContent. `icAutoTabs(box,key)` turns the `h3` of a page into tabs (security, jobs, messages); what follows `.ic-tabend` stays below (my emergency stop). A MutationObserver on `#profmodal` cuts every `ul.facts` to 10 entries with "Show … more" and styles the remaining `<details>` as cards, "add" forms as a button. Me has no lists with their own height any more, long addresses wrap. Mail tidying (`tidy.js`): a card per mailbox with the mode as segments, tabs questions, preview (by folder), history, rules, folders and exceptions; one tap on a chip answers a question, "Always" (ticked) makes a rule. reMarkable (`remarkable.js rmDraw`): status card, figures, tabs read (folder tree on the left from 700 px, content on the right with the path on top, search across everything), send, more, settings; changes to the choice are collected by the save bar at the bottom. Memory (`me.js factDraw`): search, chips all/from you/automatic, date, ✎ change in place (`PUT /api/profile/memory/{id}`, browser login only, at most 300 characters, counts as "from you" afterwards), select and delete several (`POST /api/profile/memory/forget`, at most 500 ids), "Forget everything" in the danger zone. No new switches. `tests/test_ich_aufraeumen.py` checks width (320/390/1280 px), scroll boxes, tabs, answer by chip, folder tree and memory.
- **Pages show that they load** (`js/laden.js`, plan `plaene/seiten-laden.md`): `api()` fetches through `lzFetch`. After a click, a key or at start a thin bar on top (`#lzbar`) shows that something loads; timed polls (Status every 3 s, Live, version check) do not move it. After 30 s without an answer a box shows "No answer after 30 seconds" with "Try again"; the request goes on, and a late answer still fills the box. Two requests without an answer (network, 502, 504; 503 is the emergency stop) show the band "The Spark is not answering." with a retry every 5 s; when the Spark is back the open page loads again (never the settings form). `ladeBox(box, load, {at, form, quiet, auth, skel, stale, top})` shows grey placeholders after 150 ms (`.lz-sk`, forms `zeilen`, `karten`, `tabelle`) or, for a box loaded before, the old content dimmed with "updating …", after 8 s "taking longer than usual …" and an error in the box itself with "Try again". `showSec()` loads every page through `lzb(...)`; Me loads its boxes side by side with `lzPool(..., 4)` instead of one after the other, only a 401 signs out. Slow reads (from 1.5 s, once a minute per route at most, only the route pattern) appear as `seite: slow GET …` under Status → Logs → Diagnosis ("Page loading"). `tests/test_seiten_laden.py`.

`tests/test_guides.py` (class `BuildingBlocks`) checks this without a browser: title and intro on every page, no `label.chk`, "Erweitert" only as `details`, as many "More" buttons as more texts, short sentences and English translations.

## Features and rights (features.py)

Since V01.0.267 every function the admin can switch is written once in `app/panel/features.py`: name (de/en), group, the admin switches (`chat.*`), the function it builds on (`parent`), the profile's own switch (`profile`), whether guests may ever use it, the Me page and the guide. Values are still stored under the old names in `config.json` and `settings.json`; only this table knows both.

- **One check:** `features.admin_on(key)`, `features.profile_on(key, uid)`, `features.allowed(key, uid)` and `features.reason(key, uid)` (reason: `spark`, `profile`, `guest`). Modules only ask here (`admin_on`, `usable`, `allowed` are one-liners); what must be set up besides (Kiwix address, agent level) the module registers in `features.READY` or `features.GRANTED`.
- **One list for the pages:** `GET /api/features` (signed in, rate limited) returns every function with Spark on/off, own switch, "may" and reason; guests see only guest functions. The flags in `/api/whoami` and `allow` in `/api/profile/settings` and `/api/iphone/settings` come from the same table.
- **New function:** an entry in `features.py`, a guide in `guides.js`. `tests/test_features.py` fails when a `chat.*` switch belongs to no function, a profile switch does not start off, or a module builds its own check.
- **Values in one place** (since V01.0.268): `common.load_config()` fills every missing key from `config.default.json` (like `jq '.[0] * .[1]'` in install.sh); a second default in code (`.get(k, other)`) and hand merges fail the self-test. What applies to a profile comes only from `profiles.effective(uid)`: the admin's presets (`chat.defaults`) with the profile's own values on top; guests get the presets.
- **Heute** (since V01.0.286): `today.py` builds `GET /api/profile/today` only from `features.allowed`; every card is its own block that is missing when the function is not allowed. Calendars with `asyncio.wait_for` (3 s) and a 5 minute cache per profile and time zone; what is still to set up comes from `onboard.py` ("Los geht's"). The sentences of "Probier mal" come from `guides.js` (`say`), filtered by `/api/features` (`can`).
- Fixed protection rules (secrets never spoken, speech first, the owner's voice at a shared speaker) are no switches and stay rules of their own.
- **Main admin** (since V01.0.275): `core.owner_auth` lets the panel password and the admin mode of a profile with role `owner` through (roles, `/api/audit`, backups); `main_auth` stays only for the password, its second step and *sign out everywhere*. Profile shell: `body.prof` (start.js) shows the admin menu with only Assistant and Me; `.mainonly` is seen by the main admin profile, `.pwonly` only with the password.
- **App** (since V01.0.272): `GET /api/admin/switches` returns `names` and `groups` for every switch from `features.switch_names()`; the app keeps no list of its own. The app key may read `GET /api/features`; `hands` and `barge` are in `iphone.APP_FIELDS`.
- **Profile detail** (since V01.0.271): `GET /api/admin/profiles/{uid}` also returns `features` (`features.count(uid)`: on / allowed by the Spark), `role`, `main` (is the main admin asking?) and `rights` (agent level, update right, upload space; missing for managers). `PUT /api/admin/agent/levels/{uid}` (`{"level": "" | "read" | "act"}`, logged as `agent_level`) sets one profile's agent level. The profile list carries `guests` (`features.guests()`).

## Keeping the live overview current (live.py)

Since V01.0.312 *Status → Live* (and the monitor `/live`) show everything the Spark does right now. So the picture never lies by leaving something out, every change also adds its entry there:

- **New tool:** a target in `live.TOOLS` (an existing one or a new one in `live.TARGETS` with zone `spark`, `lan` or `net`) and a word in `live.RETURNS`. `tests/test_live.py` turns red when a tool from `chat.py` or an extra service is missing.
- **New kind of device:** a word in `live.CLIENT` (the test compares with `tracelog.CLIENTS`).
- **New channel** (WebSocket, long poll): a line in `live._conns`.
- **Request without a conversation** (only hearing or only speaking, e.g. Wyoming): `rec = live.begin(client, device)`, then `rec.step("asr"|"tts", …)` and `live.end(rec, ok)`; refused senders with `live.door(...)`.
- **Something the Spark does by itself** (rule, reminder, task): `live.begin(client, "", uid=…, auto=True, why="fixed word")` and the steps below it inside `with live.within(rec):` (no way back to a device). Notes are reported by `push.send` itself (`live.note`, targets Web Push, Apple Push, Android app, Telegram); a new tag gets a word in `push.WHY`.
- **Background work** runs through `vorrang.run`/`post`/`in_thread`/`quiet`/`hold` with a fixed name; that reports it to `live.bg` itself (no contents in the name).
- **New entry check or guard level:** `guard.failed` and `netguard.resolve` already report to `live.refused` and `live.outgoing`; add new words there.
- Only fixed words and numbers, never contents; names only through `live._who`.

## Tests

`app/tests/` holds the self-tests that run on every update (`cd app && python -m unittest discover -s tests`). All services are faked (`tests/helpers.py`); no test talks to real models or Home Assistant. `tests/test_ui_browser.py` also opens the panel in Chromium (Playwright) at computer and phone width: every page without script errors and without sideways scrolling, the settings search, the Me window. Without Playwright (as in the self-test on the Spark) it is skipped; on GitHub it runs in the "Tests" workflow on every push. There everything runs in four parts at the same time (`python selftest.py discover -s tests --part K/4`, cut by test module and its duration in `tests/dauer.json`, the long browser test test by test); the job "Ergebnis" checks that every part reported and counts the failures over the whole run.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Installer: "torch in venv-… has no CUDA" | Run `sudo ./install.sh` again. If that does not help, delete `/opt/speech-spark/venv-*` and reinstall. |
| Panel shows `blocked` | Not enough memory next to the running qwen38 lane. Switch to 0.6B, lower the reserve (at your own risk) or stop the big lane. |
| Panel shows `error` | Read the message in the panel and under Logs. |
| `no kernel image is available` | A package was built without Blackwell kernels. Check with `/opt/speech-spark/venv-engine/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| Engine does not start | Panel → Logs → engine. With "No available memory for the cache blocks", raise the engine's memory share in the panel. The first start downloads the model and takes longer. |
| Update fails | Panel → Settings → Update → update log. The old version keeps running or is installed again; the log says which. |
| Port taken | Change the port in `/etc/speech-spark/config.json` and run the installer again. |

The per-model memory estimates (`MODEL_GIB` in `app/common.py`) are rough assumptions; correct them with the values the panel shows.
