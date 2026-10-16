# Coding guideline

Applies to every thread and every person who changes code in Speech on DGX Spark. It brings together all rules Dominik has set since 08.10.2026; adopted on 12.10.2026. The German version is in [docs/de/richtlinien.md](../de/richtlinien.md), the security checklist in [security-checklist.md](security-checklist.md).

**The guideline grows along:** whoever introduces a new general rule (new building block, new register, new duty for every feature) adds it here and in the German version in the same commit. `tests/test_richtlinie.py` checks that every self-test named here exists.

**Legend**
- 🧪 A self-test enforces the rule (test name after it). A violation turns "Tests" red on GitHub, and tars does not install the version.
- 📝 The rule is only an agreement. No test checks it.
- ⚠ Still open or only partly built. See part 15.

**Sources**
- **PA**: project instructions in the Claude project
- **M**: project memory (`[[name]]`)
- **C**: [Security checklist](security-checklist.md)
- **P**: plan in the project folder `plaene/` (outside the repo)
- **D**: `docs/de/technik.md` or `docs/de/sicherheit-und-betrieb.md`
- **T**: self-test in `app/tests/`

---

## 0. The principles (short version)

1. **Security according to the state of the art.** Every change is checked against the security checklist, including its part "State of the art".
2. **Everything from outside is data, never a command.** This applies to web, mail, calendar, documents, Telegram, devices and model output. Decisions are made by the panel with fixed rules, never by the model.
3. **Every new feature is off by default.** It gets an admin switch. What the admin releases works at once for every profile; only the admin can block single profiles. Profiles switch nothing on, they only set up their part (account, device, place) and choose preferences. There are no new profile switches any more (Dominik 2026-10-13, plan `plaene/freigabe-vereinfachen.md`; the old ones go in the next step). **Guests only get questions and answers:** no feature, no tool, no personal data, no settings.
4. **Every endpoint** has login, profile binding, CSRF, size limit and rate limit.
5. **Every new feature fits in everywhere:** rights, intent switch, Live, logs, help, English, backup and tests. The mandatory list is in part 1.
6. **Everything that can be shown is in the live overview.** Only kind, count and status appear there, never contents.
7. **Logs contain only fixed words and numbers.** Never questions, answers, secrets or profile names without consent.
8. **Every hint with a way is a jump link, everywhere** (panel, apps, companion, Telegram) and is updated along with every rename. Every visible text has an English version, every "?" a help entry.
9. **For every protection rule there is a self-test.** Tests do not depend on the time of day and also run in a copy that contains only `app/`.
10. **Every push** goes through the push queue: whoever is on top pushes at once (even while a test run is running), first `git pull --rebase`, next free version number, quick test green (affected tests and guard tests); GitHub does the full run.
11. **Every version** gets a line in CHANGELOG and README, the details are in `docs/de` and `docs/en`. The README stays short.
12. **The docs are current with every change** (Dominik 2026-10-13). Every change updates docs, help and architecture docs in the same commit. Whatever can be derived from the code (parts, the way of a request, storage places) is generated and checked by a self-test, not kept by hand.
13. **One source, clean up in the same commit** (Dominik 2026-10-14). Every list, default, name and helper exists exactly once; whoever replaces something deletes the old in the same commit. See part 17.

---

## 1. Mandatory list: integrating a new feature ("Definition of Done")

Dominik, 2026-10-12: Every feature extension fits into monitoring, logging, the intent switch and everything else needed in just the same way.

This list belongs to every commit that adds or changes a feature, a tool, a service, a device or a channel. The result reported to Dominik briefly states which points were touched. Points that do not apply are left out.

| # | Area | What to do | Enforced |
|---|---|---|---|
| 1 | **Rights and switches** | Entry in `features.py`: name de/en, group, admin switch `chat.*`, `parent`, Me page and guide (no new profile switch, no guest access to features). Admin switches are **off**; the few preferences (`pref=`) are on. Whatever is shipped on as an exception is listed with a reason in `features.DEFAULT_ON`. Modules only ask `features.allowed/admin_on`. Defaults live only in `config.default.json`. A switch that only applies to the Spark goes into `SPARK_ONLY`. | 🧪 test_features, test_richtlinie (DefaultOn) and off tests per feature |
| 2 | **Guests and unknown voice** | Guests only get questions and answers: no tool, no feature, nothing personal. At the shared speaker an unknown voice only gets guest rights. A new feature needs to do nothing for this: `features.reason` always says "guest" for guests, and `chat_turn` offers guests no tool. | 🧪 test_gaeste and per feature ("never for guests") |
| 3 | **Endpoint** | It needs a login (`auth`, `browser_profile`, `secret_profile`, …). Without login it is listed with a reason in `OPEN`. Plus a size limit before reading, a rate-limit key and state changes only via POST, PUT or DELETE. Endpoints with a code go into `stufen.LIST` and get the lock in `mfa.js CODE_LOCKS`. If the app reaches them, they are in `APP_PATHS`. | 🧪 test_scanner.test_every_route_has_a_login, test_stufen, test_hardening (body rejected before reading) |
| 4 | **Tool for the model** | The tool goes into exactly one block list: `READS_OUTSIDE`, `HA_READS`, `LOCKED_OUTSIDE` or `INSIDE`. Add-on services declare it in their `offer()` sets. If a question strictly needs the tool, it goes into `chat.NEED_TOOLS`. If it is a lookup tool, it goes into `chat.LOOKUPS` (at most 2 per question). | 🧪 test_scanner.test_every_tool_is_sorted |
| 5 | **Intent switch** (`intent.py`) | The new intent or group goes into `intent.GROUPS` with its words. Plus test sentences in `intent_bench.py` (BENCH), also for every reported misassignment. If there is only one matching tool, it becomes a mandatory tool (`forced`). For a new group check the page Features → Switch (list, detail, statistics). | 🧪 test_intent, test_weiche |
| 6 | **Immediate feedback** | Every new intent-switch group and every new direct panel path gets **at least 5** sentences (de and en) in `ack.PHRASES`, assigned in `ack.group_of`. The sentences have no digits, no yes or no and at most 60 characters. Alternatively the group is listed with a reason in `NO_ACK`. | 🧪 test_ack (Coverage, test_plenty_of_variants) |
| 7 | **Live overview** (`live.py`) | For a tool: target in `live.TOOLS` and word in `live.RETURNS`. A new target goes into `TARGETS` with zone `spark`, `lan` or `net`. A new device type goes into `live.CLIENT` and `tracelog.CLIENTS`. A new channel goes into `live._conns`. What the Spark does by itself runs via `live.begin(auto=True)` and `live.within`. Background work runs via `vorrang.*` with a fixed name. New guard or log kinds go into `guard.LIVE_WORDS` or `LIVE_SKIP`. A new push tag gets a word in `push.WHY`. Targets that are not set up are hidden via `live.unset()`. | 🧪 test_live (tools, targets, clients, guard kinds), test_dienstwacht (node per service) |
| 8 | **Logging** | Journal lines start with a fixed area (`chat:`, `weiche:`, `mail:`, …). A new area goes into `logfilter.AREAS`. If there is a fixed hint for the error, it goes into `logfilter.HINTS`. Lines contain only fixed words, numbers and decisions. A profile appears only as `profiles.log_name(prof)`. Detailed lines are `… detail …` behind the time-limited diagnostics. Repeated rejections are logged once, with the time of the next attempt. | 🧪 test_logfilter, test_richtlinie (JournalNames), test_schonend, test_log_luecken.Structure; 📝 prefix duty |
| 9 | **Request trace** (`tracelog.py`) | New steps of a request run via `tr.step(...)`, only with `SAFE` words and numbers (at most 40 steps, at most 8 infos). A tool name appears only if the tool was offered. | 🧪 test_tracelog (SECRET test) |
| 10 | **Service watch** | If the feature depends on a service of its own (LAN or internet), it gets a probe in `dienstwacht.py` (via netguard, without credentials, to an address the service answers without a login: a probe must never count as a failed login there), a live node and a fixed sentence for "service missing". | 🧪 test_dienstwacht |
| 11 | **Outgoing connections** | Only via `netguard.client(level, origin=…)`. The levels are PUBLIC, USER and HOME. The emergency-stop levels apply automatically. A module that connects by itself (own service on localhost, language model, fixed service) is listed with kind and reason in `netguard.DIRECT_OK`; an address from settings or outside text never belongs there. | 📝 (C, SSRF); 🧪 test_hardening, test_waechter_umgehung |
| 12 | **Interface** | Only use the building blocks from part 6. No inline code. Every text is in `i18n.js`. Every settings row with a field has a help entry (`sw:`/`me:`). Where it fits, a line goes into the search (Ctrl K, automatically via the building blocks) and a line into `glanceText()` (At a glance). | 🧪 test_guides.BuildingBlocks, test_bedienung_hilfe, test_scanner (CSP), test_ui_browser |
| 13 | **Guide and help** | A guide in `guides.js` with the 7 sections (what, you need, set up, say, leaves the house, off, if not). After doc changes run `python3 app/panel/hilfe.py --docs`. Questions that should be found go as a case into `test_hilfe_quality.py`. Where it fits, a tip goes into `tipps.py` (GAPS) and a card into Me → Today (`today.py`). | 🧪 test_guides (every switch has a guide), test_hilfe (index current), test_hilfe_quality (≥ 60 questions) |
| 14 | **Hints with a way** | "Switch on under Features → …" starts with a menu name and names the steps with today's names. `way.js` turns this into a link by itself. This applies **everywhere**: in the iPhone and Android app, companion, Telegram and push as a link `…/#weg=<way>`. If a page or row is renamed, all ways are updated in the same commit. Hints without a way get a jump target: every hint at the top of the admin pages (`health.alerts`) carries `go` with a way and shows "View" (since V01.0.447). | 🧪 test_sprunglinks (panel, notes on top); apps, companion and Telegram: test_sprunglinks.Outside |
| 15 | **Backup** | A new file in `state/` (folder only from `common.STATE`) gets a line in the file register `dateien.py`: with settings and its kind (`sicherung=`) it goes into the backup (`backup.STATE_FILES`), any other with its reason (`lokal=`, `backup.STATE_LOCAL`) is left out of the backup. Secrets live only in the vault. | 🧪 test_technik.Storage |
| 16 | **Update and services** | A new module that ASR or TTS services import goes into `app/restart-map`. A new package goes with hash into `requirements-panel.lock`. A new systemd unit gets `MemoryMax=` and `PrivateTmp=yes`. A page that belongs in the panel goes into the static allowlist of `panel.py`. | 🧪 test_rauchtest, test_lock, test_hardening |
| 17 | **Admin log and undo** | Admin changes to the configuration run via `undo.py` (without secrets). Sensitive switches go into `SENSITIVE`. | 📝 |
| 18 | **Apps** | Every function with an Ich page or a setting can be reached in every app: set up, look at, delete (Dominik 2026-10-14). Android shows the panel itself (WebView, `appview.js` takes the panel's list). The iPhone app shows a page natively or opens it under "Open in the panel" inside the app; the list of pages comes from `features.ME_PAGES` through `/api/features` (`pages`), never from a list in Swift or Kotlin. A new Ich page goes into `ME_PAGES` (and `me.js meAll`, `guides.js ME_NAME`); if it is missing in the app, it stands with a reason in `features.APP_SKIP`. The app reads names and rights from `/api/features` and `/api/admin/switches`. Every new text of the app gets its English version in `Localizable.xcstrings`. Panel areas are opened by the admin switch for every profile, no switch per area. | 🧪 test_app_gleichstand, test_features.test_swift_keeps_no_list, test_iphone_panel |
| 19 | **Tests** | A self-test for every protection rule. A browser test for every new page (320, 390 and 1280 px). A check item at the bottom of `pruefung/praxistest-tars-2.md` in the project folder (A = admin, P = profile). | 📝 (field test), see part 9 |
| 20 | **Docs** | A line in CHANGELOG and README (de and en), details in `docs/de` and `docs/en`. New general rules go into this guideline. | 🧪 test_richtlinie (Versions, Guideline), test_changelog |
| 21 | **Security according to the state of the art** | The change is checked against the part "State of the art" of the security checklist (cryptography, login, headers, supply chain, LLM risks). | 📝 |
| 22 | **Prerequisites** | When a feature builds on another one, that is its `parent` in `features.py` (the chain follows from it, `features.chain`). No own "switch on X first" text: hints name missing switches through `features.missing_text`, the Features page offers the chain when switching on (`needs.js`) and says what goes off with a switch. A setup that can be missing goes into `features.READY`. | 🧪 test_voraussetzungen, test_voraussetzungen_mit_einschalten |
| 23 | **Settings assistant** | Every new setting in `config.default.json` or `profiles.SETTINGS` gets its classification in `berater_katalog.py` in the same commit: in the catalogue (stage A–C, P), in `NEVER_KEYS` (D, never) or in `OHNE` / `OHNE_PROFIL` (deliberately not suggestible). So the assistant can suggest it or safely leave it out. | 🧪 test_einstellungs_assistent.test_every_setting_is_classified |
| 24 | **Copy of my data** | Every new file under `users/<id>/` is classified in the file register `dateien.py`: with `bereich=` (may go encrypted into the copy at a storage place, `speicher.AREAS`) or with `art=` as its reason (`speicher.LOCAL`) (always stays on the Spark: keys, logins, settings, voiceprint, queues). Local first; the sync runs in the background via the watcher. | 🧪 test_speicher |
| 25 | **History on every device** | A new channel that answers for a profile keeps question and answer via `verlauf.keep` (its own conversation per day like Siri, Telegram, the watch; with "One conversation for all channels" today's main conversation, marked with the channel; a voice that is not surely the profile's never goes there), never via `save_convo` with an old copy. Devices send only new messages (`PUT /api/profile/convos` with `add`); only deleting replaces the copy. Open pages fetch changes via `?since=`. Every change is told by `profiles` to the event connections (`verlauf.changed`), carrying only the id and the kind of device, never contents. A copy in the browser only where `offline_here` allows it (trusted browser, function on); every other browser deletes it, signing out always. Guests get no history on the Spark. | 🧪 test_verlauf_sync |
| 26 | **Created documents** | Numbers in a created document need a source from the Kiwix, the own documents, the user's words or the facts of the conversation (`folien.drop_unbacked`, `folien.check_chart`), otherwise they are left out; charts only with at least 3 different values that have a source. Icons only from `app/panel/symbole/` (the model names a word, never a path), nothing from the net. Pictures only from the own Kiwix via `kiwix.picture_of`, with a switch of their own (off), saved anew via PIL with size and pixel limits and with the source on the slide. Slide types and text length are decided by `folien.py`, not by the model. | 🧪 test_folien |
| 27 | **Tool name** | Every new tool (for the model, as a panel step or over MCP) gets a readable name de/en in `werkzeuge.NAMES` in the same commit, then `python3 app/panel/werkzeuge.py --js`. Pages show tools only through `wzName` (copies for threads through `wzFull`, with the internal name in brackets), the panel through `werkzeuge.label`/`full`; never the internal name alone. | 🧪 test_werkzeuge |
| 28 | **Deeds** | Every tool that changes something (switching, entering, sending, creating, remembering) gets its kind in `taten.KIND`. Only then does the action check test sentences like "is on now" against its result; the error loop stop holds for every tool anyway. A result that did not work starts with one of the fixed words in `taten.FAILED` ("Not done", "Fehler" …), a proposal still to be confirmed with "NOT saved yet" or "NOT done yet". | 🧪 test_taten (tools with a kind) |
| 29 | **Tool coverage** | Every function in `features.py` stands in `werkzeug_abdeckung.py` in the same commit: with its tools (`TOOLS`), with the panel's fixed rule that answers it (`RULES`), or with the reason there is nothing to ask for (`WITHOUT`). Every tool for the model sits in a Weiche group, in `intent.NARROW_KEEP` or, when its module offers it only on the person's own word, in `BY_WORD` with `keep` in its `offer()`; otherwise the Weiche drops it when narrowing. Every tool of a group has a typical sentence in `SENTENCES` that leads there, and every new tool runs once for real in a self-test. (Dominik 2026-10-13: "check whether there are tools for all services and information") | 🧪 test_werkzeug_abdeckung |
| 30 | **Architecture docs** | The architecture docs (`docs/de/architektur.md`, `docs/en/architecture.md`, panel Status → Architecture) come from `technik.py`. A new module gets its group and a line in `technik.MODULE`; a new file in `state/` or under `users/` gets exactly one line in the file register `dateien.py` with its content (de/en), backup, area of the copy and protection (`schutz=` when sealed); `backup.STATE_FILES`/`STATE_LOCAL`, `speicher.AREAS`/`LOCAL` and `technik.INHALT`/`VERSCHLUESSELT`/`USERS_SONST` are built from it, none of these lists is written by hand. If the way of a request changes, `KNOTEN`, `KANTEN` and `SCHRITTE` follow. Every box has its node page in `technik_knoten.SEITEN_DATEN` (way, rules, numbers, code); when the way a box works changes, its page changes in the same commit. Numbers are placeholders read from the code, never typed; the fingerprint `stand` turns the test red as soon as the described code changes, until the page was checked (Dominik 2026-10-14). Every number, code line and rules table knows its step: if no step text names it, the page's `bezug` does (a click marks the bubble). Then `python3 app/panel/hilfe.py --docs`. | 🧪 test_technik |
| 31 | **Clean up** | Before a new helper, list, name or setting, look whether it already exists and use that. Delete what was replaced or is dead (keys, functions, imports, texts, CSS) in the same commit. Never leave a file on the legacy list with more hits. Part 17. | 🧪 test_aufraeumen |

**Coming with work in progress** (applies as soon as the version is on main; the thread then extends this table and the test):

| Area | What to do then | Thread |
|---|---|---|
| **Static files** | Every static route and every public file answers; new short paths pass the request on. | in force since V01.0.442, 🧪 test_statische_routen |
| **Background models** | The display says "working" only while something is really being computed, otherwise "Standby" (loaded or not); sharing a running model does not extend its run time and never starts it (`docembed.embed(..., keep=False)`); the stop check also runs during a Notaus and after errors. | applies since V01.0.444, 🧪 test_wissen.Worker |

**Planned, not yet approved** (no rule): read state for the history (plan `verlauf-sync.md`), asking before GitHub reports (plan `frage-vor-meldung.md`).

---

## 2. Security

The complete list is the **[Security checklist](security-checklist.md)** (about 45 points plus "State of the art"). It is gone through before every commit, and the answer names the points touched (PA, C, M [[secure-coding-rules]]). Every change is additionally checked against the current state of the art (Dominik 2026-10-12); whatever is listed there as "not yet met" is brought up to date the next time the place is touched.

### 2.1 Access
- For every endpoint it is defined who may: guest, profile in the browser, device key or admin. (C; 🧪 test_scanner)
- The following things need a browser login and a fresh code (`browser_profile` + `confirm_code`), never the device key: secrets, addresses that receive a token, code word, push targets and mail accounts. (C)
  - Only exception: the iPhone app key with the scope switch (`secret_profile`).
- "Fresh" means: correct code of the same login within the last 10 minutes.
  - Really asked every time with `*_fresh` or `fresh=True`. These are password, second step, roles and main admin, backups, code word and Spark update from the app.
  - Admins (panel password or a profile with a role, signed in with the second step) are never asked at the "confirm" level, only at "change protection" (`core.admin_login`). Admin rights only come from a login with the second step, never from a PIN or handoff. New admin endpoints use `core.auth`; there is no second admin stage.
  - A passkey counts like a code. Code prompts therefore always run via `confirm_code`, never via a separate `mfa.verify`.
  - (C; 🧪 test_stufen, test_zweiter_schritt, test_passkey)
- In the browser always use `api()` or `apiTry()`, never a raw `fetch` to code endpoints. In the iPhone app always `SparkAPI.confirmed`. (C)
- If an address changes, the token must be entered again. State changes never via GET. Keys are compared with `hmac.compare_digest`. (C)
- Guests only get questions and answers: no tools, no personal data, no actions and no error texts, only error codes. (C, PA; 🧪 test_gaeste)
- **Shared speakers:** The device key alone is not enough.
  - Personal things only when the owner's voice is reliably recognised in the same recording.
  - Whose voice it was is set only by the panel (`request.scope`).
  - This is a fixed rule without a switch. (C, M [[shared-speaker-voice-rule]])
- Rights are always checked by the server. A hidden tab does not mean "forbidden". (P handy-wie-app)
- Rights changes reach open pages without reloading. A device whose feature is off gets 503 and keeps its pairing. (🧪 test_rechte_sofort)

### 2.2 Size and load
- The body limit applies before reading. Parse the body only after login. Read uploads with `read(limit+1)`. (C; 🧪 test_scanner.test_uploads_read_with_a_limit, test_hardening)
- Limit unpacked content (zip, docx, backup). Audio only with 8000 to 48000 Hz and with `ffmpeg -t`. ffmpeg and ffprobe only with `-protocol_whitelist file,pipe`. (C; 🧪 test_lieferkette)
- Downloads streamed and with a byte limit. Texts for TTS and chat limited, the last message to about 4000 characters. (C, P Prüfung)
- Rate limit per IP plus a global semaphore for LLM, ASR and TTS (`guard.limit`, `guard.Slot`). Upper limits for jobs, tool calls, searches and memory entries. (C)
- Caches with expiry and maximum size. Heavy work runs via `to_thread` with a budget, never in the event loop. (C; 🧪 test_tempo.OffTheLoop)
- Background work gives speech priority: `vorrang.run`, `post`, `in_thread`, `quiet` and `hold`. At most one background request at a time to the language model. This is a fixed rule. (M [[vorrang-sprache-plan]]; 🧪 test_vorrang)
- **Maintenance pause** (Dominik 2026-10-14): background work that asks the language model goes through `vorrang.run`/`post` or waits first with `quiet`/`hold(…, model=True)`; that way it also waits during a maintenance pause. Code that asks the model itself in the foreground checks `wartung.paused("llm")` first and says `wartung.sentence` instead of waiting for a time-out. (🧪 test_wartung)

### 2.3 Outside text (prompt injection)
- Counts as outside: web, pages, mail, calendar, contacts, parcels, documents, HA states, Telegram, things overheard in the room and old answers built from them. (C)
- Outside text is wrapped as data (`chat.wrap_outside`). After that, switching, memory, reminders, suggestions, drafts and help cards are blocked, **also in the next turn**. Outside text is never learned into memory. (C; 🧪 test_hardening Stage2, test_left_out, test_hilfe)
- Only offered tools run. The intent (intent switch) and the origin can only **restrict**, never grant. The order is rights → blocks → intent. (P funktionswahl, hilfe-besser)
- Who is asking comes from the login, never from the text. (P vorrang-personen)
- Content with an unverified sender is never presented as "from DHL". (C)
- **Probabilities from the model** (`systemone.py`, `/v1/systemone` of the LLM-Tor or of qwen38) are only a signal: questions and options are fixed in the code, the judged text goes only into "state", and the panel decides with a fixed threshold (a constant or a choice among fixed steps). Below `systemone.MIN_MASS` label mass an answer counts as unsure, and everything goes on as without it. Every new use gets a name in `systemone.USES` and runs in the background through `vorrang`. Security, rights, Notaus and the choice in a follow-up question never go by probabilities. (Dominik 2026-10-13; 🧪 test_systemone)

### 2.4 Confirming and acting
- Per profile there is exactly one open suggestion. It is valid only for the same device, a plain "Yes" and 15 minutes. (C; 🧪 test_hardening)
- Home Assistant runs with an allowlist of domains. Mail is never deleted. (C)
- Suggestion cards (help, tips, settings assistant) never switch by themselves. Only the person's tap on "Apply" ("Übernehmen") switches, with the same checks as the form. Security is never weakened via a card; for that there is only "Show me where" ("Zeig mir wo"). (P panel-hilfe, funktionen-entdecken, einstellungs-assistent)

### 2.5 Outgoing connections (SSRF)
- Only http(s), only via `netguard`. Loopback, private and link-local addresses are blocked, unless the admin allows the home network. (C)
- The checked IP is pinned, every redirect is checked again. Credentials go only to the same origin. Never a fallback to http, TLS verification is on. (C)

### 2.6 Injection
- No `shell=True`, `eval`, `exec`, `os.system`, `pickle` or `yaml.load`. (C; 🧪 test_scanner.test_no_dangerous_calls)
- HTML only via `textContent` or `esc()` and `data-` attributes. Strict CSP `script-src 'self'`: no inline script, no `on…=` handlers, buttons via `data-on` or `onAttr`. (C, D; 🧪 test_scanner.test_no_inline_script_for_the_strict_csp, test_csp_is_strict, test_hardening)
  - ⚠ The general rule "data never via innerHTML" is only tested for individual files.
- **The model's answers** are shown in the panel only through `md.render` (md.js): nodes made with `createElement`/`textContent`, only allowed elements, no pictures, links only http(s) to public addresses (like netguard), with `noopener noreferrer`, and the host name when the link text differs. Devices without formatting (Telegram, Siri, companion, reMarkable, watch, speaker display) get `textnorm.plain_markdown`, the voice always `textnorm.speech_markdown` (in both speech services before `hide_secrets`, whatever `tts.clean_text` says); code blocks are never spoken (`chat.no_code`). A new channel that shows answers picks one of these. (Dominik 2026-10-12; 🧪 test_markdown)
- **Every sentence of an answer comes only once**, in the chat and in the voice. Answer text goes only through `take()`/`speak()` in `chat.py`; when the model already writes text before a tool call, the next round shows its sentences only when complete and leaves out each one already said (`chat.said_key`, Logs → Requests "Repetition left out"). A new path that puts text into the answer uses these. (Dominik 2026-10-12; 🧪 test_answer_never_twice)
- Configuration values are checked the same way when saving, when restoring and in `install.sh`. IMAP values only as printable ASCII. (C)

### 2.7 Secrets and logs
- Secrets live only in the vault and are never returned. Never in logs or error texts, never `str(e)` with a token. (C, PA)
- Passwords, codes, PINs and keys are **never spoken** (`textnorm.hide_secrets`). This is a fixed rule without a switch. (M [[secrets-never-spoken]]; 🧪 test_units.Secrets)
- **Silence never becomes words:** whatever the speech recognition makes of a recording without voice, of a typical silence sentence ("Untertitel im Auftrag des ZDF") or as a lone short word from an almost voiceless recording is no question (`stille.check` in `/api/test/asr`). A new path that turns recordings into text and passes it on uses `stille.measure`/`stille.check`. Fixed rule without a switch. (Dominik 2026-10-13; 🧪 test_stille)
- Code words never go to the model, never into the history, the diagnostics or the journal. (C)
- Passwords and keys are only typed into the form, never into the chat. (P funktionen-entdecken)

### 2.8 root boundary, update, supply chain
- root follows no symlinks in folders of `speech`. Writing only via `put_file` or `as_svc`. (C; 🧪 test_hardening)
- Packages with fixed version and hash (`--require-hashes`). Nothing from the configuration ends up unchecked in a root script. (C; 🧪 test_lock)
- Security headers on every response (X-Frame-Options, nosniff, Referrer-Policy, CSP, Permissions-Policy). (🧪 test_bedienung)
- Rollback only to the remembered previous version. Signatures fail closed. (🧪 test_hardening, test_lieferkette)

---

## 3. Features, switches, rights

- **Off by default:** one admin switch; once released it holds for every profile, never for guests. (PA; 🧪 test_features, test_gaeste and off tests per feature)
- **Exceptions:** fixed protection rules have no switch at all when Dominik said "never" or "always". These are: never speak secrets, priority for speech and the owner's voice at the speaker. (M, D)
- **Microphone opened by itself:** when a page, app or device opens the microphone without a tap or wake word (barge-in, follow-up window, hands-free), the recording tells the panel (`opened` to `/api/test/asr`). Then, with a taught voiceprint, only a known voice counts, and without one the voice must be above the learned room level; TV and other voices never become a question. A fixed protection rule without a switch, like the silence rule. (Dominik 2026-10-13, request d80a75; 🧪 test_fremdstimme)
- **Shipped on** are only pure protection and stability features and the basic features from the start. Each is listed with a reason in `features.DEFAULT_ON` (Dominik 2026-10-12). A new value `true` in `config.default.json` without an entry there is red. (🧪 test_richtlinie.DefaultOn)
- **One register:** every feature is listed exactly once in `features.py`. Stored keys are never renamed, the register translates. Values are read only via `profiles.effective(uid)`. The order is admin default, then own values, then device; device values exist only for location-dependent things. (D, P vereinheitlichen; 🧪 test_features)
- **Locked means visible:** locked rows are shown grey with a reason ("Switched off by the admin" / "Vom Admin ausgeschaltet"), not hidden. Under Me they are collected in a collapsed box. The reason comes from `features.reason()`, never from the model. (D, P einstellungen-neu)
- **The Features page stays short.** New sub-features come as sub-switches (`data-show`) under their main switch. (M; 🧪 test_ui_browser height budget)
- **Preferences only for unasked actions, on and switchable off under Me:** A feature gets a profile preference (`pref=` in `features.py`) only when the Spark does something by itself with it (speaks up, announces, sends to a device, tidies up). The preference starts on, a missing value counts as on; it is in `profiles.NO_PRESET` and gets its toggle on the Me page named in `me` in the same commit. Nothing else has a profile switch. (Dominik 2026-10-13; 🧪 test_features)
- **A block holds everywhere:** What acts for a profile asks `features.allowed`; `features.admin_on` only on admin pages or Spark-wide places, each with its reason in `test_sperre_ueberall.ADMIN_ON_OK`. Seeing and deleting own data works also while blocked: the function's delete routes let DELETE through, and Me shows in place of the hidden page a card of the function with "Delete data". For it every module with a profile's own data registers count and delete in `features.OWN`; what is left out on purpose is listed with its reason in `test_eigene_daten.OHNE`. (Dominik 2026-10-13/14; 🧪 test_sperre_ueberall, test_eigene_daten)
- **Roles:** logs, requests and Live are seen by the panel password and profiles with the Admin role, not by the manager. (P anfrage-verfolgen, live-uebersicht)
- Build only after Dominik's OK. For larger features first a plan under `plaene/` with pictures, numbered points and a ★ recommendation. (PA, M)

---

## 4. Logging and diagnostics

- All services write to the journal namespace `speech-spark` (500 MB, 14 days). Constant status queries and the fetches of the Logs page are not logged. (D)
- **Format:** `area: what | reason | numbers`. The area is a fixed word before the colon. Areas that should be filterable in the panel are in `logfilter.AREAS`. (D, P logs-darstellung; 📝)
- **Only fixed words, numbers and decisions.** Never question text, answer text, tool arguments, results, secrets or error texts of outside servers. (P anfrage-verfolgen, M; 🧪 test_tracelog, test_hintergrund, test_logfilter)
- **Profile names** appear in the journal, requests and Live only with the profile's consent (`trace_name`, `live_names`). In the journal a profile appears only as `profiles.log_name(prof)`: the name with consent, otherwise "Profile" ("Profil") and the end of the identifier. The admin log (`guard.log`) still names who changed something. (Dominik 2026-10-12; 🧪 test_richtlinie.JournalNames)
- **Levels:** red and yellow are determined via fixed word lists (`logfilter.ERR`, `WARN`), for web server lines only via the status code. Expected disruptions (service briefly gone, rate limit) are warnings with "retry in …", not errors. (D; 🧪 test_logfilter)
- **Detailed diagnostics** are on per area only for a limited time (15 min, 1 h or 4 h, off after a restart) and write only `… detail …` lines with numbers. (D)
- **Every outcome of an action is in the journal.** Whatever changes something outside the panel or says something to others (announcement, message, list, reminder, appointment, mail, notification, tool, computer, own service, memory) writes one line for every outcome: done, refused (with a fixed reason such as `notaus`, `hourly limit`) or failed (kind of exception). Every tool call writes `chat: tool <name> ok|not ok|not offered | ms`. Exceptions in the admin log (`guard.QUIET`) are exact paths, never a too short prefix: `/api/chat` otherwise swallowed every `/api/chats/` change. (Dominik 2026-10-13; 🧪 test_log_luecken, test_messages.Speakers.test_every_announcement_writes_a_journal_line)
- **Everything new goes into the log, checked by tests** (Dominik 2026-10-13: "always put everything new into the log"): every journal line starts with a word of `logfilter.AREAS`; a new word goes into an area in the same commit (with its button in `logs.js`). A function behind a Notaus gate (`notaus.stop`, `refuse`, `blocks`) writes a line or says in `ACTION_OK` (test) where its line comes from. Every exception of the admin log has its reason in `guard.QUIET_WHY`. What Live shows under Events is in the journal too as `ereignis:`, whether Live is on or not. No line shows what someone said or wrote, what a foreign server answers, or a raw profile id: only the length (`len`) or `profiles.log_name`; exceptions with their reason in `CONTENT_OK` (test). (🧪 test_log_luecken.Structure)
- **No log flood:** a repeated rejection is logged once, with the time of the next attempt. (🧪 test_schonend.QuieterLogs)
- **Request trace** (Logs → Requests): one `anfrage:` line per request, steps via `tracelog`, at most 48 h or 500 requests, not in the backup. (M [[anfrage-verfolgen-plan]])
- **For Dominik:** logs come via Status → Logs → Diagnostics, "Copy for thread" ("Kopieren für Thread"), or via Logs → Requests, not via console commands. (M)
- **Towards the outside** (GitHub reports) an allowlist applies instead of a block list. Replacements are `[PERSON-n]`, `[IP]` etc. On a leak nothing is sent. (P probleme-melden)
- Error fingerprints consist of kind, feature and error type, never of words. (P frage-vor-meldung)

---

## 5. Live overview and monitoring

- **Rule (PA, Dominik 2026-10-10):** everything that can be shown appears under Status → Live and on the monitor `/live`. This applies to new things and retroactively, **in the same commit as the feature** (Dominik 2026-10-12). Gaps are listed in `live-uebersicht/was-fehlt.md`. (M [[live-monitor-aktuell-halten]]; 🧪 test_live)
- **Only kind, count and status, never contents.** External targets only as service or host name. Names only via `live._who` with consent. Never password or code values. (PA, D; 🧪 test_live.test_request_shows_without_any_text)
- **Only what is set up** is shown (`live.unset`). Proxy detection only counts for the picture, never for decisions. (M)
- `live.py` keeps everything in memory only. The admin page polls every second. The monitor is only in the home network, with a pairing code. (M)
  - The old plan mentioned SSE; what is built is polling.
- **Service state:** a service counts as gone after 3 failed probes and 3 minutes, as back after 2 good probes. At most one message per 30 minutes. If the internet fails, a collective message comes. Messages consist of fixed sentences. This is shown as the banner `health.alerts`, as a Status card and as a live node. (M [[dienst-ausfall-plan]])
- **The control centre on the screen grows along (Dominik 2026-10-16):** what Status → Live, Status → Monitoring (both computers) or the notes show also appears on the text screen at the panel computer (`steuerzentrale.py`), in the same commit. Services and targets come by themselves from `live.snapshot`; a new stage, number or curve needs a line in `steuerzentrale.py`. (M [[live-monitor-aktuell-halten]]; 🧪 test_steuerzentrale.test_every_live_service_has_its_line)
- **Background work** reports its state with fixed reasons (sprache, nacht, tageslimit, pause, …). (P hintergrund-status)

---

## 6. Interface: layout, building blocks, design

- **Design "Clear"** ("Klar", 2026-10-08): sidebar on the computer, bar at the bottom on the phone. The app view starts below 760 px. (M [[panel-design-directions]])
- **Menu** (as of 2026-10-11): Assistant · Me | Status · Features · People and devices · Settings, plus Ctrl/⌘ K. The settings groups are Assistant, Speech and Spark. (D; 🧪 test_guides.MenuStructure)
- **Page skeleton** (`docs/de/technik.md` → building blocks), use only these parts:
  - **Head:** `h2.pt` with `.pintro` (one sentence). Sections are `h3.sec`, which `seite.js` puts into boxes `.sgrp`.
  - **Row:** `setrow` with name and one sentence on the left, exactly one control on the right. Switch `.tgl`, never `label.chk`. For 2 to 4 options segment buttons.
  - **Help text:** at most one sentence and ≤ 140 characters visible, the rest behind "More". "Advanced" always sits in `details.adv`.
  - **Saving:** one floating save bar per page. Immediate actions are in a section of their own "takes effect immediately".
  - **Lists:** pattern "list with detail area" (`ld-`), on the phone the detail becomes a page of its own. Me pages use `ichteile.js` (sub-tabs with count, status card, ⋯ menu, 10 rows + "Show more", danger zone) and **no inner scroll boxes**.
  - (D, P einstellungen-neu, ich-aufraeumen; 🧪 test_guides.BuildingBlocks, test_einstellungen_neu, test_ich_aufraeumen)
- **Width:** no horizontal scrolling at 320, 390 and 1280 px. No element sticks out over the edge on the phone. (🧪 test_ui_browser, test_ich_aufraeumen)
- **Frame:** every page with a side menu (Zustand, Funktionen, Personen und Geräte, Einstellungen, Ich) uses the one frame from `app.css` (`--frame`, `--sidecol`, `--sidegap`): menu column and content sit in the same place with the same width on every tab, no page sets a width of its own. (D 2026-10-14; 🧪 test_seitenrahmen)
- **Height:** the Assistant fills the window (only the history scrolls). Height budgets apply to the Features page (< 2450 px at 1280) and People and devices (< 1500 px). (🧪 test_ui_browser, test_einstellungen_neu)
- **Phone:** tap targets at least 44 px, input fields 16 px, respect the safe area. The face or "Ask Spark" ("Frag Spark") never lies over controls. (P handy-wie-app; partly 🧪)
- **Status colours** green, yellow and red. "Needs you" always has a button leading there. Amber (`--c4`) exists in the live picture only for the internet. (P design-klar, M)
- **Browser cache:** HTML is `no-store`, CSS and JS are loaded with `?v=VERSION`, `/api` is `no-store`. (🧪 test_panel.Page)
- **Loading is visible** (since V01.0.459, plan `seiten-laden.md`): what a page or box loads when it opens goes through `ladeBox`/`lzb` (`laden.js`): placeholders, "updating …", "taking longer than usual …" and the error with "Try again" stand in the box itself; an error takes nothing from the rest of the page and never signs out (only a 401 does). Several boxes load side by side (`lzPool`, at most 4), never in an `await` chain. After 30 s without an answer the box shows the error with "Try again"; the request is not cut off, and a late answer still fills the box. Browser tests wait for `lzIdle()` (every box loaded) after opening a page, never for a fixed pause: a switch flipped earlier would be set back by the settings arriving after it. (🧪 test_seiten_laden)
- **Start with a guard** (since V01.0.655, Dominik 2026-10-16): the page's start runs in `startPage()` (`start.js`) and reports its end to the start guard (`theme.js`); when a script is missing or the start fails, the page loads itself again once the Spark answers. No second start block beside `startPage()`, and without an answer from the Spark never go on with made-up values (before `{admin:true}`). (🧪 test_seiten_laden)
- **Calm, nothing jumps** (since V01.0.558, Dominik 2026-10-14, plan `ruhige-seiten.md`): what the user has open stays open and in its place. Saving and switching never reload the page: changed functions reach the menu with the next change of page (`whoPendingGo`). When the page must reload itself (new version, update finished, language), it does so only through `verReload()`, which remembers the place (page, sub-page, open function, person or Me area, scroll) and `placeBack` restores it; no new `location.reload()` for this. Opened parts (`details`) stay open or closed as the user set them when they are drawn anew (`laden.js`). Timed polls draw only what changed (`setHtml`) and run fast only while their page is seen. While the update window is open (`updBusy()`), everything else keeps still: no band, no version bar, no poll behind it, the bar only moves forward. The panel asks in its own window, not with `confirm()`. The apps do the same: fixed ids for rows, new entries only appended, open pages never vanish by themselves. (🧪 test_ruhige_seiten)
- **Save the battery** (V01.0.668, Dominik 2026-10-16): a hidden page does not poll on a timer and keeps no event stream open; it catches up on coming back (`visibilitychange`). The Android app pauses the page in the background (`WebView.onPause`/`pauseTimers`, except during a call), the iPhone app stops its audio engine in the background as soon as nothing listens, speaks or calls. Lasting connections hold one question as long as the way allows (Android: 4 minutes, falling back to 50 s), always-on listening on battery is on only when chosen. (🧪 test_akku, test_android)
- **All panel scripts share one global namespace.** Check new function names against all JS files. (M [[dienst-ausfall-plan]]; 📝)
- **Terms:** "Me" (not "My profile"), "Status" (not Overview), "People and devices" (not Profiles), "Operation" (not System), "Spark", "Admin rights" (roles means the speaking roles). Old page names are forbidden. (P ordnung-und-darstellung, bedienung-gesamt; 🧪 test_bedienung_hilfe.Names, test_guides)

---

## 7. Texts, hints, help, English

- **Jump links (PA, 2026-10-12):** every message that refers to a place has a direct link there, as far as the person may see the place.
  - The way starts with a menu name (Settings, Features, Status, People and devices, Me). Steps in lower case are actions.
  - This applies to fixed texts, server messages and the assistant's answers.
  - Counts, rows and badges that stand for a place are jump links too (PA, 2026-10-14: "should be clickable and take you straight there"): every row of a card under Status opens its place (`way.js` `WAY_CARDS` or `data-way`), every number like the "Today" tiles is a link (`wayFirst`). A new card gets its target in the same commit; `test_sprunglinks` checks every card.
  - (M [[sprung-links]]; 🧪 test_sprunglinks)
  - **Everywhere** (Dominik 2026-10-12): the iPhone and Android app, companion, Telegram and push notifications also show ways as a link (`…/#weg=<way>` opens the place in the panel). If a page, a tab or a row is renamed, all ways are updated in the same commit, including in docs, help and apps. New texts in the apps go through their helpers (`SparkAPI.way`, `Wege.text`, `Wege.cs`, `Wege.kt`), Telegram and push through `wege.py`; in an app it says "in the panel under Settings → …". (🧪 test_sprunglinks.Outside checks the same rule in all apps and their ways in the panel)
  - Hints without a way (at the top of the admin pages, Status cards) get a jump target to where one can act or take a look.
- **English:** every visible text in `index.html` is in `i18n.js`, including `title` and `aria-label`. New texts from JS via `t()` or `tt(de,en)`. Server sentences exist in German and English. The English docs use English menu names. (D; 🧪 test_bedienung_hilfe.English/Names, test_guides)
- **Errors as sentences:** `errSay`/`errRaw` from `base.js`. No paths, no `f"… failed: {e}"`, no raw English exceptions. Guests never see internal addresses. (D; 🧪 test_bedienung_hilfe.PlainErrors)
- **"?"** exists only where the help knows the row. Every settings row with a field has an `sw:` entry. (🧪 test_bedienung_hilfe.QuestionMarks)
- **Guides:** every switch has a guide in `guides.js` with 7 sections. (🧪 test_guides)
- **Help answers:** at most 3 hits and about 1200 characters. Ways only from the fixed list. The origin comes from the panel, never from the question. (P hilfe-besser; 🧪 test_hilfe_quality)
- **Tips sparingly:** at most 1 per conversation and 3 per week. "Don't show again" applies forever. No tips after outside text, during emergency stop or for guests. (P funktionen-entdecken)
- **Notifications** (push): only once per version, never at night, not during the profile's quiet time. System messages are fixed sentences without names. (P iphone-update, firmware-verteilen, home-assistant-meldungen)
- **Spoken bridge sentences** (`ack.PHRASES`) are continually extended, with lots of variety: at least 5 per group, never one of the last 6. (M [[sofortige-rueckmeldung]], Dominik 2026-10-11/12; 🧪 test_ack)
- Answers name the source briefly ("According to your archive …"). Links are never read aloud. (P erst-lokal)

---

## 8. Language model, intent switch, tools

- **The intent switch** reads only the person's own last message. It only restricts and writes one line `weiche:` per turn. (M [[funktionswahl-plan]])
- **Misassignments:** correct the rule in `intent.py` and add the sentence to `intent_bench.py`. (M; 🧪 test_intent)
- **Fix model errors in the panel** (NEED_TOOLS, answer check), not only in the prompt. Always add a self-test. (M [[answer-check-and-fixes]])
- **Texts for the model name only tools offered in this answer.** Otherwise it calls a tool it was not offered (Logs → Requests: "unbekannt"). (M [[ha-states-tool]]; 🧪 test_panel)
- **Dates** in quality cases relative to today, never fixed. (M)
- **Times from outside** (mail headers, calendars, trains, Home Assistant) are converted into the person's zone (`chat.user_zone`, else `chat.system_zone`, Europe/Berlin) before they are read out or shown, never given with the sender's offset. (Dominik 2026-10-12: a mail from 20:30 was read out as 18:30; 🧪 test_mail_zeit)
- **Thinking text:** every new LLM call that can run with thinking uses `common.no_think`, not its own `<think>` regex. (M [[think-tag-doppelt]])
- **Local first, then external:** documents, Kiwix, history. Data stays in the LAN as far as possible. No second model just for a sub-feature (GPU memory). Creating documents works offline. (P erst-lokal, hilfe-besser, praesentationen-professionell)
- **Never change:** dgx-spark-qwen38 on ports 30000–30099, and never switch it off for good or delete it automatically (only a command the admin runs and that asks first). Own ports are at 31001–31443, own engines only on 127.0.0.1. (M; Dominik 2026-10-14)
- **Models only from the catalog:** every model the Spark runs itself is one line in `app/modelle.json` and is read only through `app/modelle.py`: a pinned revision (a full commit), a memory share of at most `modelle.ANTEIL_MAX` (0.80; above it the GB10 freezes), never `trust_remote_code`, only safetensors and text files (never pickle or Python code), every file checked against its hash after the download and for file kinds and links before every start, engine flags only from the catalog fields, an engine starts only with a pinned commit (from the catalog or the checked measurement). Measuring never switches qwen38 off for good; only `speech-spark modelle llm uebernehmen` disables it (after a note, with a round trip and a way back by itself), and only `qwen38-aufraeumen` on command after a working move removes it. (Dominik 2026-10-14, plan eigene-modelle; 🧪 test_modelle, test_llm_tor, test_umzug)
- **The own language model only through the LLM-Tor:** the engines listen on 127.0.0.1 only; from outside the way is `llm_tor.py` (`llm.port`) with the API key and a size limit. The door passes only the fields in `llm_tor.FELDER` (no token ids, no `logit_bias`, `n` is 1, `top_logprobs` at most `modelle.LOGPROBS_MAX`), sets the model name and the sampling values from the catalog, and which model answers is a fixed rule (`zum_sehen`), never the model. The journal gets fixed words and numbers only. (Plan eigene-modelle, stage E2; 🧪 test_llm_tor)
- **Tools have names people understand:** what shows is the name from `werkzeuge.NAMES` (de/en), the internal name only small beside it or in copies for threads. (Dominik 2026-10-12; 🧪 test_werkzeuge)
- **Own doing into the Spark diary:** every function that does something for a person (switching, reminding, saving a draft, making or sending a file, sending a message) calls `tagebuch.note(uid, art, title, ref, before, src)` with a fixed kind; titles from outside with `src="web"` or `"mail"`. Questions about its own doing are answered by the model only from `spark_tagebuch` or `document_status`. (P vorschlaege-besser; 🧪 test_tagebuch)
- **Fix errors with rules, not code:** what the admin can set in the panel (must words, tool hints, Weiche), the settings assistant only proposes from fixed templates; the model never writes the text of a rule, and a rule is never taken by itself from the reports of a single person. (P vorschlaege-besser; 🧪 test_regeln_admin, test_regeln_v3)

---

## 9. Tests

- **A self-test for every protection rule.** A regression test for every finding of a review. (PA, C; 🧪 test_pruefung, test_hardening)
- **Only simulated services:** no test talks to real models, Home Assistant, mail or calendar (`tests/helpers.py`). The real test on tars is done by Dominik. (D)
- **No dependence on the time of day:** times are passed in. tars tests in the time zone Europe/Berlin, GitHub in UTC. (PA, M)
  - ⚠ No test checks this in general.
- **`app/`-only copy:** tests that read files outside `app/` (`install.sh`, `update.sh`, `.github`, `docs`, `ios`) call `skipTest` when the file is missing. So run new tests once like this: `cp -r app /tmp/x/ && cd /tmp/x/app && python selftest.py discover -s tests`. (M [[selftest-app-only]])
- **Browser tests** wait for a state, never for a fixed time. Contexts with `bypass_csp=True`. Widths 320, 390 and 1280 px. (M)
- **Tests write no unknown config keys**, write the configuration atomically (`helpers.write_config`) and in `tearDown` switch off loops they switched on. (M)
- **One panel per test class, and it stops with it:** browser tests start the panel only with `helpers.serve_panel(cls, port)`, which stops it after the class. Otherwise its background loops keep running for the rest of the run, every class adds a copy, the panel gets slower and slower and takes the work later tests wait for. Tests leave no devices, connections or profiles behind that disturb later tests; pairs like `python -m unittest tests.test_chats tests.test_meldung` find such leaks. (2026-10-13, main red after V01.0.473; 🧪 test_testserver)
- **Ports for test servers stay reserved:** a port for a test server comes only from `helpers._port()`, which keeps it bound until `helpers._serve` or `helpers.take_port` (for servers that listen themselves) uses it; never get a port and give it back. A busy port fails at once instead of waiting 60 s (run of V01.0.489: a port was taken on the runner, every test waited again, cut off after 45 min). Self-test `test_testserver`.
- **A second attempt** (Dominik 2026-10-11): a red test gets exactly one second attempt (`app/selftest.py`).
  - Red twice means red. With more than 5 failures there is no second attempt.
  - Green only in the second attempt gives a visible WARNING, and the test must still be repaired.
  - (🧪 test_selftest_runner)
- **Never** skip, weaken or disable a test in order to turn green. (PA, M)
- **Smoke test** (`test_rauchtest`) stays fast. It is the only test that tars runs for versions already checked. (M [[schonende-updates]])
- **Quality test** (real model): a red case is first checked for whether the regex is too strict, and only then treated as a model error. (M)
- **Field test:** every feature gets a check item at the bottom of `pruefung/praxistest-tars-2.md`. (M; 📝)
- **Test bank of the document search:** whoever changes the document search (`documents.py` splitting, search, merging, later re-ranking) runs `test_suchpruefung`. The fixed test bank `tests/data/suchbank.json` must find at least `FLOOR` percent among the first 5 with the word search. The floor is only raised when the search got better, never lowered to turn green; new questions only come with an honestly measured number. (2026-10-13, plan suche-schaerfen; 🧪 test_suchpruefung)

---

## 10. Repo, push procedure, CI, releases

- **Directly on main.** Before every commit `git pull`, increase the patch number in `app/VERSION` (V01.0.541). (PA)
- **Batched push (PA, Dominik 2026-10-13, replaces "wait for the test run"):**
  1. Pushes go in order through the push queue (`push-warteschlange.md`); only whoever is on top pushes, never jump the queue.
  2. Whoever is on top pushes at once, even while a "Tests" run for main is running or waiting: first `git pull --rebase`, the **next free version number at push time** (never reserve in advance), quick test green. Then remove your own line; the next one goes at once.
  3. In the end GitHub tests only the newest state: the running run finishes, of the waiting ones only the newest stays (`cancel-in-progress: false`).
  4. If the run on main turns red: PUSH-STOPP for everyone; the coordinator finds the cause and puts its ROT-FIX on top.
  5. **Quick test instead of the full run (Dominik 2026-10-15):** before the push run only the test modules of the changed files and the guard tests (`test_richtlinie`, `test_aufraeumen`, `test_technik`, `test_sperre_ueberall`, `test_log_luecken`, `test_app_gleichstand`, `test_sprunglinks`, `test_changelog`, `test_doku_stand`), each `selftest.py discover -s tests -p 'test_NAME.py'`, a few minutes instead of over an hour. "Tests" on GitHub does the full run (about 8 minutes); if it turns red, point 4 applies. Run the full run locally only for big rebuilds or to reproduce a red GitHub run.
- **Tests in parts (V01.0.502):** "Tests" runs in four parts at the same time (`selftest.py --part K/4`), cut by test module and its duration in `app/tests/dauer.json` (a module stays together because some tests build on earlier classes of their module; only a very long class with entries per test is spread test by test); together the parts hold every test exactly once. The job "Ergebnis" adds up the failures of all parts; the limit of 5 failures counts for the whole run. If one part gets clearly longer than the others, measure `dauer.json` again. (🧪 test_selftest_runner)
- **PUSH STOP:** if the coordinator says "PUSH-STOPP", nothing is pushed until they explicitly lift the block. (M)
- **PROJECT LOCK:** while a "PROJEKT-SPERRE …" line is on top of the queue, only the thread named there pushes to main; others only plan, urgent fixes go through the coordinator to that thread. The lock ends when the coordinator removes the line. (M)
- **Commit message:** `V01.0.541 short description`. The CHANGELOG lines are made from it. Avoid a plain "merge main" as the message. (📝)
- **Workflows** (repo-absichern, 2026-10-11):
  - Every `uses:` is pinned to a 40-character SHA with `# vN`. `contents: write` only at job level. `persist-credentials: false`.
  - Signing keys and releases only with `environment: release`. No `pull_request_target`.
  - (🧪 test_workflows)
- **`cancel-in-progress: false`** in `tests.yml` must never be set to true again. (M [[tests-lauf-nicht-abbrechen]])
- **Update gate:** tars only installs the newest main commit with a green "Tests" run. (🧪 test_hardening)
- **Releases:** always delete old GitHub releases, keep only the newest per series. A new release workflow goes into the `workflow_run` list of `releases-aufraeumen.yml`. (PA, M [[releases-aufraeumen]]; 🧪 test_releases_aufraeumen)
- **Ubuntu 26:** GitHub `ubuntu-latest` switches from 2026-10-19. GitHub uses Python 3.11. (M)

---

## 11. Documentation and versions

- **README.md and README.de.md stay short** (about 90 lines): installation, "Latest changes" with exactly 10 lines, diagram, links into `docs/`. (PA, M [[readme-layout]])
- **Per version** one line at the top of `CHANGELOG.md` in the format `- **V01.0.541** · YYYY-MM-DD · Text` (otherwise it is missing from "What's new") and in both READMEs; the oldest line drops out. (PA; 🧪 test_changelog only checks the format)
  - VERSION, the newest CHANGELOG line and the first line of both READMEs match, each README has exactly 10 lines. (🧪 test_richtlinie.Versions)
- **Details** are only in `docs/de/*.md` and `docs/en/*.md`, both languages structured the same way. Then run `hilfe.py --docs`. (PA; 🧪 test_hilfe.test_docs_copy_is_current)
- **Docs always current** (Dominik 2026-10-13): every change updates docs, help and architecture docs in the same commit. The blocks between `<!-- technik:… -->` in `architektur.md`/`architecture.md` are written from the code by `hilfe.py --docs`; never edit them by hand. (PA; 🧪 test_technik.Docs)
- **README, diagram and ports follow the code** (Dominik 2026-10-16): when a port, a service (`speech-spark-*.service` in `install.sh`) or what a part does changes, the same commit updates the Mermaid diagram of both READMEs (every public port from `config.default.json`), the table "Processes and ports" in `architektur.md`/`architecture.md` (every port, every service), the boxes in `technik.py` and the help. A sentence that is no longer true goes with its reason into `test_doku_stand.STALE`, so it never comes back. Screenshots in the README only with demo data (`docs/bilder/`). (PA; 🧪 test_doku_stand)
- **Plans** live under `/mnt/project-files/plaene/` with "Status" ("Stand": date, version), ★ for the recommendation and "Questions for Dominik" ("Fragen an Dominik"). Pictures come from the real panel or from mockups. (P)

---

## 12. Operation, update, resources

- About 10 GiB of free memory on tars. DGX OS kills processes below about 8 GiB. New services need `MemoryMax=`. (M, D; 🧪 test_hardening)
- An update interrupts for about 8 seconds. Nightly work does not run during an update (`update.update_running()`). Device rounds run from 05:15. (M)
- Self-test on tars with `nice 19` and `ionice`. Test priority code with `nice -n 19`. (M)
- The panel venv is created from the lock only if venv-panel is new. A new library therefore needs an installation path for existing installations. (M)
- Questions to `api.github.com` only through `ghtoken.get` (read-only token, 401 → on without it), never for reachability probes: without a token all devices at home share 60 per hour. (D; 🧪 test_ghtoken, test_update_check)

---

## 13. Collaboration (threads and Dominik)

- Answers in German, short numbered suggestions with a marked recommendation. For larger features first a plan, then build. (PA)
- The result states which points of the security checklist and the mandatory list (part 1) were touched. For new features also what was added to Live. (PA)
- A new general rule goes into this guideline (de and en) in the same commit and, if possible, into a self-test.
- When there is a new version, first check in Dominik's trace which version tars already has. (M)
- If two threads touch the same file, the coordinator tells both. (M)

---

## 14. What self-tests already enforce (overview)

| Test | Enforces |
|---|---|
| test_scanner | no dangerous calls, login on every route (otherwise OPEN with a reason), upload limits, strict CSP, tools sorted |
| test_hardening | body limited before reading, root write paths, unit limits, only green versions, outside-text blocks |
| test_stufen | every code endpoint with a level in `stufen.LIST` |
| test_features | one register, a release holds for every profile, only the admin blocks, preferences start on, no checks of their own, one default value |
| test_live | every tool, target, client and guard kind in the live picture, no contents |
| test_testserver | a browser test class's panel stops with it, no one starts it otherwise |
| test_werkzeuge | every tool has a name de/en, pages read the same table |
| test_ack | every intent-switch group has ≥ 5 bridge sentences |
| test_intent, test_weiche | intent-switch rules and BENCH sentences |
| test_tracelog, test_logfilter | logs and requests only fixed words and numbers, filter safe |
| test_sprunglinks | every way starts with a menu name and is found |
| test_bedienung_hilfe | English, errors as sentences, "?" with help, old names forbidden |
| test_guides | page building blocks, menu, guide per switch, ≤ 140 characters |
| test_hilfe, test_hilfe_quality | help index current, ≥ 60 everyday questions right |
| test_seiten_laden | pages load through `ladeBox`, Me side by side, errors in the box, "Try again" after 30 s, band "The Spark is not answering", slow reads in Diagnosis |
| test_ruhige_seiten | saving does not reload, a reload comes back to the same place, one calm update window (no band, the bar only moves forward), opened parts stay open, Status polls every 3 s only while seen |
| test_akku | hidden pages do not poll and close the history stream, Android pauses the page in the background (except in a call), the iPhone stops the audio engine in the background |
| test_ui_browser, test_ich_aufraeumen, test_einstellungen_neu | no width beyond the edge (320/390/1280), height budgets, no inner scroll boxes |
| test_seitenrahmen | one frame for every page with a side menu: same place and width on every tab, nothing wider than the phone |
| test_workflows, test_lock, test_lieferkette | pinned actions, permissions, signing environment, package hashes, ffmpeg whitelist |
| test_selftest_runner | one second attempt, > 5 no attempt, warning |
| test_rauchtest | every module loads, `restart-map` complete |
| test_technik | every module, every file in `state/` and `users/` in the architecture docs and in the backup or local list, doc blocks current, Architecture page admin only |
| test_doku_stand | README diagram with every public port, table "Processes and ports" with every port and service, ports of the model boxes in Technik, links in the README, no stale sentences (`STALE`) in README, docs and help |
| test_changelog | CHANGELOG format |
| test_releases_aufraeumen | only the newest release per series |
| test_app_gleichstand | one list of Ich pages, every page reachable in the apps (exceptions with a reason), pages follow the release, app texts with English |
| test_aufraeumen | no new duplicates: own `<think>` filter, a dict key twice, unused import, own JSON write, own model call, raw `fetch(`, names differing between features.py and guides.js (the legacy list only shrinks) |
| test_richtlinie | values shipped on with a reason, journal without profile names, VERSION/CHANGELOG/README in agreement, guideline de/en present and its test names valid |

**Agreement only (no test):**
- push order
- independence of the time of day in general
- log prefix
- `undo.py` / `SENSITIVE`
- field test item
- "data never via innerHTML" (general)
- global JS names
- commit message
- check against the state of the art

---

## 15. Outdated and still open

**Outdated (no longer applies):**
- Feature pause of 2026-10-09: it has been lifted. What applies is "build after Dominik's explicit OK".
- Menu states before 11.10. ("Overview", "Integrate" (German "Übersicht", "Einbinden"), the old profile page, phone bar "Assistant · Me · Status · Manage"): part 6 applies.
- Features page as a "Who may do what" table or short rows: list plus detail applies.
- Live overview with SSE or "blueprint": what is built is 1 s polling and "1 flow".
- Help with 3–5 hits: at most 3 applies.

**Planned but not built (no rule until built):**
- central page list `js/pages.js`
- trace ID before every log line (`[a7f3]`)
- translation via keys instead of text comparison
- shared `jsonstore` or `llm.complete()` (review package 7)

**Open (live overview, `live-uebersicht/was-fehlt.md`):** GitHub reports as a node of their own, single steps in the morning overview, number of companions, a device of its own "Writing aid" ("Schreibhilfe"), reMarkable steps.

**Open (security):** see "State of the art → not yet met" in the [Security checklist](security-checklist.md).

---

## 16. Decisions of 12.10.2026

1. On by default only with a reason in `features.DEFAULT_ON`, checked by `test_richtlinie`.
2. This guideline lives in `docs/de/richtlinien.md` and `docs/en/guidelines.md`; `CLAUDE.md` in the repo summarises it; README and project instructions refer to it.
3. New self-test for VERSION, CHANGELOG and README.
4. The security checklist lives in the repo (`docs/de/sicherheits-checkliste.md`, `docs/en/security-checklist.md`) and has a part "State of the art" against which every change is checked.
5. Jump links apply everywhere and are updated along with every change.
6. Journal lines name profiles only with their consent.

---

## 17. Clean up: one source (Dominik 2026-10-14)

"… that we have no duplicate settings entries, duplicate data keeping, duplicate whatever, that everything is simply always clean." Plan and inventory: `plaene/aufraeumen-und-apps.md` in the project folder.

1. **One source.** Every list, default, name, file name and helper exists exactly once. If a second place needs it (JS, Swift, Kotlin, docs), the copy is generated (like `werkzeuge.py --js`, `hilfe.py --docs`) or a self-test keeps it equal.
2. **Look first, then build.** Before a new helper, list or setting, check whether it already exists: `common.write_json`/`read_json`, `common.STATE` (state folder), `dateien.py` (file register: every file of the panel with its content, backup and copy), `common.no_think`, `common.load_config`, `llm.complete` (language model), `core.json_body` (request body), `common.DayCounter` (numbers of today), `kopplung.Codes` (one-time pairing codes), `sse.Hub` (events to open pages), `geraeteupdate.newer` (compare versions), `profiles.pending_set`/`pending_get` (open proposal with a time limit), `features`, `profiles.SETTINGS`, `profiles.CHOICES`, `netguard.client`, `api()`/`apiTry()` in JS, the building blocks of part 6. Use or extend what exists, never copy it.
3. **Clean up in the same commit.** Whoever replaces or removes something deletes the old with it: keys (old ones go to the list of removed keys), functions, imports, translations in `i18n.js`, CSS rules, old names and wrappers.
4. **Defaults in one place only:** `config.default.json` for the Spark, `profiles.SETTINGS` for profiles, their allowed values and bounds in `profiles.CHOICES`/`RANGES`. No second default in the code; the browser gets defaults, lists and bounds from `/api/profile/settings` (me.js `loadSettings`, `SDEF`, `SETC`).
5. **No new duplicates, the old ones get fewer.** `test_aufraeumen` keeps a legacy list per check with the state of 14.10.2026. A file may never have more hits than its entry; if it has fewer, its entry is lowered in the same commit. So the list only gets shorter. An import kept only for its side effect gets `# noqa: F401`.
6. **The big cleanup** (working off the legacy list) starts only when no other thread builds on main anymore (Dominik 2026-10-14), so the whole code gets one clean state. Until then nobody cleans up legacy in files another thread is working on.
7. **No check wrappers.** No one-line function that only passes on `features.allowed(…)`: call `features.allowed` directly (it is already false for guests, a `bool(uid) and` in front is not needed). Only where the function is handed over as a callback (`profiles.*_GATE`) or a test replaces it. The wrappers around `features.admin_on` stay: they are the audited places of the list `ADMIN_ON_OK` (test_sperre_ueberall).

| Check in test_aufraeumen | Shared place |
|---|---|
| OwnThinkFilter | `common.no_think` |
| DoubleDictKey | a key once |
| UnusedImport | delete, or `# noqa: F401` with a reason |
| OwnJsonWrite | `common.write_json` (fresh name instead of a fixed `.tmp`) |
| OwnModelCall | planned: one shared `llm.complete` |
| RawFetch | `api()`/`apiTry()` from base.js (sign-in, code dialog, Notaus, loading bar) |
| SameNames | groups and names from `features.py` |
| SettingCopies | defaults and allowed values from `profiles.SETTINGS`/`CHOICES` (browser: `SDEF`, `SETC`) |
| StateFolder | state folder only from `common.STATE` |
| FileRegister | file lists only from the file register `dateien.py` |
| CheckWrapper | `features.allowed` directly, no wrapper |
