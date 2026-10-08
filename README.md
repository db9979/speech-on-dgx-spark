# Speech on DGX Spark

**English** | [Deutsch](README.de.md)

Version V01.0.81 · Idea: Dominik Bornhäußer

One script installs **Qwen3-ASR** (speech recognition) and **Qwen3-TTS** (text to speech) as systemd services on an NVIDIA DGX Spark (GB10), together with a web panel for configuration and monitoring. It runs alongside [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38).

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

At the end the script prints the panel address, the panel password and the API key. It then runs a round trip: TTS speaks a sentence (also streamed, with time to first audio) and ASR transcribes it back. Everything runs natively as systemd services, without Docker.

The panel switches between English and German (button at the top right).

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

## Voice chat

The **Gespräch** tab needs the microphone, and browsers only allow it over https. The panel therefore also listens on `https://SPARK:31443` with a self-signed certificate; the browser warns once. The LLM connection is under Settings → Assistant (default: qwen38 at `http://127.0.0.1:30001/v1`). The installer takes the qwen38 API key from `~/.config/qwen38/api-key` of the user who runs `sudo ./install.sh`. Thinking is off for the chat so the answer starts right away. An animated assistant face shows whether it is listening, thinking or speaking; its mouth follows the voice. The same face sits in the bottom right corner of every tab, so you can talk from anywhere in the panel.

**Start page and password:** the panel opens with the assistant. Monitoring, settings, voices and logs need the panel password (button "Settings"; the login ends after 7 days without use and renews itself while in use). "Assistant without password" under Settings → Security is off on new installs: then guests are locked out, profiles sign in on the start page with name and PIN (devices with a key keep working), and the admin signs in with "Admin". Switched on, the assistant is open to everyone on the network, also without a profile. The password can be changed under Settings → Security. Scripts can still use HTTP Basic.

**On the phone:** below 760 px the page opens with the big face (tap = talk) and two buttons below it: "Settings" opens the "Ich" window ("Hey Spark" at the top), "History" the messenger view. That view fits the screen exactly: a slim top bar with an arrow back to the face, a small face, state, profile and menu, the history in the middle, and at the bottom a text field and round mic button (a stop button during the answer). The browser remembers which of the two views was open last. The menu (☰) holds new conversation, earlier conversations, conversation settings, language, light/dark and, for admins, every tab.

**As an app on your phone:** open `https://SPARK:31443` in the phone's browser, accept the certificate warning, then use "Add to Home screen" in the browser menu (iPhone: Safari → Share → "Add to Home Screen"). The assistant then starts full screen with its own icon. With the self-signed certificate Android creates a shortcut instead of an installed app; it works the same, it just does not show up in the app list.

**Better recognition:** a fixed default language (Settings → Speech recognition, e.g. German) instead of "auto" helps most with short sentences. The "Context" field takes names and terms that are often misheard; the model then prefers them. The 1.7B model is noticeably more accurate than 0.6B and needs about 2–3 GiB more memory.

**Second recognizer: Parakeet.** Under Settings → Speech recognition → "Recognizer" the admin switches between Qwen3-ASR (GPU) and Parakeet ([primeline/parakeet-primeline](https://huggingface.co/primeline/parakeet-primeline), a German fine-tune of NVIDIA Parakeet TDT 0.6B v3; the download is [flozen1981/parakeet-primeline-onnx](https://huggingface.co/flozen1981/parakeet-primeline-onnx), an int8 ONNX export of it, run via sherpa-onnx; idea from [winidi/dictate](https://github.com/winidi/dictate)). Parakeet runs on the CPU and needs about 1 GiB; the Qwen3-ASR engine is stopped meanwhile. It ignores the context field, and a stream returns the whole text in one piece. The first start downloads about 640 MB.

**Conversation comfort:** the assistant knows the date and time (the browser's time zone; can be turned off under Settings → Assistant). Conversations are kept in the browser and can be reopened or deleted at the top of the conversation. With "live transcript" the text appears while you speak; in the pause the recognition is usually already done, so that step is skipped at the end.

**Web search:** switch on "Websuche" under Settings → Features and enter the address of your SearXNG instance under Settings → Web search. If SearXNG's `settings.yml` allows `json` under `search: formats:`, the panel uses the JSON API, otherwise it reads the normal results page; "Test connection" shows whether it works. The LLM then searches by itself when a question needs current information (the LLM server needs tool calling; qwen38 has it on). The assistant says it is looking it up, reads the top pages and shows the sources under the answer.

**Wake word "Hey Spark":** with the checkbox below the chat the assistant keeps listening. Say "Hey Spark" and it listens; "Hey Spark, what's the weather?" in one go is taken as the question. The browser detects speech bursts, the speech recognition on the Spark checks for the phrase, nothing goes to the internet. The screen stays on; on a phone keep the app in the foreground.

**The "Ich" (me) window:** the button with your name (or "Guest") at the top of the history and the settings icon below the face open the same window. On the left is a short list: Conversation and, logged in, Memory, Log and Security, plus, depending on the features switched on, Documents, Calendar, E-mail, Smart home, Voice, Von selbst (speaking up by itself) and Raum-Modus (room mode); as a guest it shows "Sign in". Conversation holds listening (stop on silence, live transcript, barge-in and its sensitivity), answer (voice, profiles only; speaking rate, answer length) and display. Guests always hear the default voice. Logged in, the settings live in the profile on the Spark and apply on every device, including speakers with a device key; as a guest only in the browser. "Hey Spark" is set per device because it keeps the microphone and screen awake. Defaults for guests and new profiles are under Settings → Conversation. The speaking rate keeps the pitch; it also works for other apps that send `speed` to the TTS API (vllm-omni backend).

**Own documents:** logged-in profiles upload their own files in the "Ich" window (PDF with a text layer, Word, text, Markdown, HTML, CSV; up to 20 MB each). When asked about them, the assistant searches them and names the document below the answer. The search is keyword-based on the Spark, no extra model. Guests cannot upload anything, and no profile sees another's documents. Can be turned off under Settings → Features.

**Messages in the conversation:** hovering over a message (on a phone: tapping it) shows a bin and, on answers, a speaker. The bin deletes the message, a question together with its answer. The speaker reads the answer out again.

**Timers and reminders:** "remind me about the oven in 10 minutes" or "remind me tomorrow at 8 about the appointment". Pending reminders show as small chips below the toggles (✕ cancels); "which timers are running?" and "cancel the oven timer" work by voice too. When one is due, the page chimes, shows it in the conversation and speaks it; if the tab is in the background, a browser notification appears as well. This works while the page is open. Profiles keep their reminders on the Spark (every open device of the profile rings), guests only in their own browser. Can be turned off under Settings → Features.

**Reminders as notifications** (profiles only): in the "Ich" window under "Conversation", "Reminders on this device → Switch on" turns on push notifications. A reminder then arrives also when the page is closed, and only on the devices of that profile. This needs https with a valid certificate (e.g. behind a reverse proxy); on an iPhone first add the page to the home screen ("Share → Add to Home Screen"). The Spark only sends to the browsers' push services (Apple, Google, Mozilla, Microsoft), encrypted.

**Daily briefing as a notification** (profiles only): below that, each profile sets a time under "Tagesbriefing als Mitteilung" (daily briefing as notification). Every morning at that time a short briefing (appointments, reminders, unread mail, your topics) then goes to all devices of the profile with notifications on, and it is also kept in the history. "Aus" (off) turns it off.

**Daily briefing and calendar:** say "good morning" or "what's on today?" and the assistant reads out today's and tomorrow's appointments, today's reminders and a few lines on your own topics (e.g. "weather Berlin", via your SearXNG). "What do I have on Friday?" works too. Each profile connects one or more calendars (up to 8) in the "Ich" window, tab Calendar; an appointment found in two calendars is read out once. Each one is a CalDAV address with user and app password (iCloud: https://caldav.icloud.com with the Apple ID and an app-specific password from appleid.apple.com; Nextcloud: …/remote.php/dav; Radicale …), or a subscription link with webcal://, webcals:// or https:// (Google: "secret address in iCal format", a public iCloud calendar). New appointments: "put dentist on Tuesday 10 am in my calendar" makes the assistant read out a proposal; only when you answer with a plain yes in the same conversation does the panel itself write it to the first CalDAV calendar (optionally with an alarm). Subscription links stay read only. The password stays on the Spark and is never shown again. Guests get no calendar. Can be turned off under Settings → Features.

**Reading e-mail:** "Any new mail?", "What does Anna write?", "Read me the mail from the bank". Each profile connects up to 4 mailboxes over IMAP in the "Ich" window, tab E-mail: iCloud (imap.mail.me.com, your iCloud mail address and a new app-specific password from appleid.apple.com), Gmail (imap.gmail.com, app password, needs 2-step verification), GMX and web.de (allow IMAP in their settings first) or any other IMAP server with TLS. Outlook/Microsoft 365 is not supported yet (needs OAuth). The assistant only reads the inbox of the last 30 days and changes nothing: the mailbox is opened read only, no mail is sent, deleted, moved or marked as read. It summarizes mails and reads them out word for word only when asked; the daily briefing names the unread ones. Mail text is treated as someone else's words: once the assistant read a mail in an answer, in that answer it cannot switch smart home devices, change memory, cancel reminders, search the web or enter appointments, so a crafted mail cannot trigger anything; answers made from mails are not learned into memory. Guests and another person's voice at a different device get no access. The password is stored encrypted on the Spark and never shown again. Off until turned on under Settings → Features.

**Inbox tidying** (Settings → Features → "Postfach aufräumen", off by default; needs reading e-mail; profiles only): the Spark sorts advertising, newsletters, invoices, notifications and social media mail into folders under `Spark/` (e.g. `Spark/Werbung`) so the inbox keeps only what matters. It only moves; it never deletes, never sends and never marks mail as read. Each profile picks per mailbox in the "Ich" window, tab "Aufräumen": off, preview (only shows what it would move; a week is recommended to start), safe automatic (moves only what a rule or clear headers such as List-Unsubscribe prove) or fully automatic (also when the model is at least 85 % sure). Only new mail is checked, every 5, 15 (default) or 60 minutes. Who decides, in this order: people you wrote to (sent folder), sign-in and security mails and your "always keep" list stay put; then your rules (sender or @domain); then fixed headers; only then the language model, which may only return a category from the fixed list and has no tools. It asks first for invoices and notifications and for unclear mail; your answer can become a rule. Move a mail back into the inbox and it is not moved again, and the Spark asks. Brakes: at most 200 mails per run, and a run that would move more than half of at least 10 new mails stops and puts everything into the preview. Every move stays in the history for 30 days and can be undone. "Old mail" proposes once where the last 90 days belong; nothing moves until you press "Move". By voice: "Tidy my inbox", "Move everything from Lidl to advertising", "Undo that"; the assistant reads out a proposal and the panel carries it out only after your plain "yes". **Reply drafts** (per mailbox): "Write Anna that I'm coming" saves a draft in the drafts folder after your "yes"; you send it yourself in your mail app. Guests and other people's voices get no access.

**Room mode** (Settings → Features → "Raum-Modus", off by default; profiles only): the switch "Raum" below the face lets the assistant listen to the conversation in the room at this device for a chosen time (15 minutes to 4 hours, it ends by itself); an orange dot shows it. In a pause it helps when a fixed cue came up: an open question (with web search, nothing when in doubt), an appointment ("Shall I enter it?"), "cold", "too warm" or "too dark" (the room's real temperature from Home Assistant, offering to change the heating by one degree or switch on the light) and things to buy (Home Assistant shopping list). It changes something only after a "yes", for the smart home with the code word when one is set. In the "Ich" window under "Raum-Modus" each device sets the duration, how much it may say (questions only, also hints, also comments), each kind on its own, the device's room in Home Assistant and "text only" (silently in the conversation instead of spoken). What it hears stays in the panel's memory for five minutes and is never stored; room mode uses neither memory, mail nor earlier conversations. Everyone in the room should know it is listening.

**Speaking up by itself** (Settings → Features → "Von selbst melden", off by default; profiles only): each profile decides in the "Ich" window under "Von selbst" whether and why the assistant speaks unasked, each kind on its own: appointments ahead ("In 20 minutes: dentist. Shall I remind you again at 9:55?", a "yes" sets the reminder), its own smart home rules ("Whirlpool above 37.5", "bathroom window is open and rain is on", "washing machine power below 5 for 3 minutes"; read only, never switching), a short greeting with the next appointment or reminder when the conversation is opened after three hours or more, at most one follow-up a day on a plan mentioned yesterday, new mail from chosen senders (sender and subject only) and a weather note for tomorrow via web search. Plus quiet hours, a daily limit and learning from feedback: "nicht jetzt" means two hours of quiet, "das interessiert mich nicht" halves how often that kind may speak (can be reset). The panel decides when, by fixed rules from real data; where the model words something (follow-up, weather), its answer only counts when it quotes the data. With the conversation open the note is spoken, otherwise it arrives as a push notification. Every note is in the log with its reason.

**Natural turn-taking** (on by default, conversation settings): during a short pause the recording is transcribed already. A finished sentence ends the turn at once and its transcript becomes the question, so the answer starts noticeably sooner; after "and …", "because …", "um" or a comma the assistant waits up to 2 s for you to go on.

**New conversation every day** (on by default, conversation settings → Display): the first question of a new day starts a new conversation; earlier ones stay in the history and can be picked and continued.

**Speaker identification** (off by default, Settings → Features): each profile reads three short sentences in the "Ich" window. When the assistant then clearly recognizes a voice, it answers for that profile, with its memory, documents, reminders and voice, even on a guest device. The conversation shows "🎙 name" below the question. When someone other than the logged-in profile speaks at a device, the assistant gets only that one question (not the device's conversation), and the exchange stays out of the logged-in profile's history and memory. When the voice is unclear, nothing changes. Recognition runs on the Spark's CPU (Resemblyzer model, Apache 2.0) and needs no GPU memory. Strictness is adjustable. A voice is not a password: someone who sounds very similar or plays a recording can get into a profile.

**Profiles and memory:** under Users → Profiles and devices the admin creates profiles with a name and PIN. In the chat you log in with the "Guest" button at the top of the conversation by typing name and PIN. Logged in, the assistant remembers things for good when you tell it to ("remember that I'm vegetarian") or when they will be useful later, and forgets them on request; the profile button lists what it knows, for deleting. Memory and conversations belong to the profile and live on the Spark, so the same history shows on every device you are logged in on: which profile is asking is decided only by the login (cookie) or the device key, never by the model, and guests get no memory. Speakers and your own programs get a device key under Users → Profiles and devices that belongs to one profile, and send it as the header `X-Speech-Device` to `/api/chat`. A new PIN logs out every browser of that profile; deleting a profile removes its memory and devices. The data lives on the Spark under `/var/lib/speech-spark/users`, one folder per profile.

**Home Assistant** (Einstellungen → Funktionen → "Home Assistant", off by default): each profile connects its own Home Assistant in the "Ich" window under "Smart home" with the address (e.g. `http://homeassistant.local:8123`) and a long-lived access token (Home Assistant: your profile → Security; best for a separate non-admin user). Then "turn on the living room light" or "how warm is it in the bathroom?" work in the conversation. Commands go to Home Assistant's own Assist (`/api/conversation/process`), so only entities exposed to Assist (Settings → Voice assistants → Expose) can be switched. Devices Assist does not know are switched directly through their service (e.g. `switch.turn_on`), except locks, alarm systems and updates. With a **code word** ("Ich" window → Smart home) the assistant switches only when the code word is in the same message ("lights off, code word sunflower"); without it, it asks. The panel checks this itself, not the language model; the model and the stored conversations see only "[Codewort]", it is stored encrypted and compared with some tolerance for speech recognition (a letter or two off, "Apollo 13" = "Apollo dreizehn"). Questions need no code word. Also (ideas from ha-mcp): history ("how warm was it in the bathroom yesterday?"), several devices at once ("all lights in the living room off", each checked; an unknown room never switches the whole home), typo-tolerant device search and to-do lists such as the shopping list (read, add, tick off; changes need the code word). Questions about values, states, zones and where someone is are read directly (`/api/states`) instead: the assistant sees every device, sensor, zone and person the token's user may see, exposed or not. Home Assistant tells rooms (areas) only to an admin token; without admin rights devices are found by their names only. Only that profile can use its Home Assistant: guests never, and a voice recognized by speaker identification at someone else's device neither. The token is checked before saving, stays on the Spark (`users/<id>/homeassistant.json`, mode 0600) and is never sent back to the browser.

**Searching conversations**: the magnifier next to the conversation list (on phones in the menu) searches all earlier conversations, a profile's with a profile, the browser's as a guest. A click opens the conversation at that spot.

**Earlier conversations** (Einstellungen → Funktionen → "Frühere Gespräche", on by default; profiles only): the assistant can look up what you talked about before ("what did you tell me about the grill last week?", "what did we talk about yesterday?"), searching only your own profile's saved conversations. Conversations that have been quiet for ten minutes are also read once in the background, while nobody is talking, and up to three lasting facts per conversation go into the profile's memory, marked "automatic" in the "Ich" window, where they can be deleted. Each profile can switch this learning off in the conversation settings ("Learn from conversations"). Once a week (or with "Propose cleanup") the assistant proposes merging duplicate entries and removing outdated ones; nothing changes until you accept the proposal under Ich → Memory. With notifications on, a note is sent.

**Pronunciation:** Settings → Speech output → Pronunciation takes one rule per line, e.g. `DGX = De Ge Ix`. It applies to whole words and to all speech output, Open WebUI included.

**Barge-in:** while the assistant speaks, the microphone keeps listening. Talking for about a quarter of a second interrupts the answer, and what you said becomes the next question. This relies on the browser's echo cancellation; if the assistant interrupts itself on loud speakers, use headphones or untick "barge in" below the chat.

**Your own voice:** under Voices you can record a reference straight from the microphone (read the suggested text, about 10 seconds); the panel fills in the transcript with the speech recognition. Cloning needs a Base model (Settings → Speech output → model `…-Base`), then set the new voice as the default voice. A German reference gives much steadier German than the built-in speakers, which are not native German speakers. Under Voices, one or all of your own voices can be exported as a ZIP (reference audio and transcript) and imported again on this or another Spark; on a name clash the import renames, replaces or skips.

## Logs

All speech services log into their own journal (`journalctl --namespace=speech-spark -u 'speech-spark-*'`), capped at 500 MB and 14 days; journald deletes older entries automatically. Adjustable under Settings → System, effective after the next update. The panel's constant status polls are not logged at all.

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

## Self-test

Every install and update runs the panel's self-test (`app/tests`) against fake LLM, TTS and Home Assistant servers in a throw-away directory: login and access, that profiles never see each other's memory, documents, conversations, mailboxes or Home Assistant, the chat tools, learning from conversations, calendar and text cleaning. It runs before the new version goes live. In an update a failure stops the update and the old version keeps running; on a first install it is only reported. The result is in the update log. By hand: `cd /opt/speech-spark/app && sudo /opt/speech-spark/venv-panel/bin/python -m unittest discover -s tests -t .`

## Security

- **Assistant without password**: off on new installs. Then only profiles (name and PIN) and devices with a key reach the assistant. Switch under *Settings → Security*.
- **Lockout after wrong attempts**: after 5 wrong passwords or PINs from one address (or 10 for one profile name or the admin password, from anywhere) the panel waits 1 minute, twice as long with every further lockout, at most an hour. On top, each name gets at most 30 wrong attempts a day. Addresses that logged in successfully before are not locked out by a stranger this way. The counts survive a restart of the panel.
- **Reverse proxy**: behind a reverse proxy in the LAN (e.g. Synology) the real address from `X-Forwarded-For` counts, so one guesser cannot lock everybody out. Enter the proxy's address under *Settings → Security → Adressen des Reverse-Proxys* (reverse proxy addresses); then the panel trusts that header only from there, otherwise from any device in the home network.
- **Logins expire**: the admin login after 7 days without use, a profile login after 90 days; while in use they renew themselves. Logging out ends the login on the server too. *Me → Security → Log out everywhere* ends the profile's login in all other browsers. On https (also behind the proxy) the cookies are `Secure`.
- **Second login step (authenticator app)**: for the admin under *Settings → Security*, for profiles under *Me → Security* once the admin allows it under *Settings → Features* (off on new installs; each profile decides for itself). Set up with a QR code; then the login asks for the six-digit code, plus 10 recovery codes for a lost phone. "Trust this browser for 30 days" saves the code on your own device; "Log out everywhere" (profile) or "Forget trusted browsers" (admin) ends that. While the admin has it on, HTTP Basic no longer works, and changing the password, restoring a backup, creating or moving device keys and changing PINs ask for a code every time. Devices with a key (speakers, Siri, Pebble, phone) need no code. Way back in: admin `sudo rm /var/lib/speech-spark/state/mfa-admin.json`; the admin resets a profile under *Users → Profiles*.
- **Outside text switches nothing**: once the assistant read web pages, calendar, documents or earlier conversations in an answer, nothing in that answer can switch Home Assistant, change memory or cancel reminders; after an e-mail it also cannot search the web or enter appointments. The panel only runs tools it offered the model in that step.
- **Web search**: the panel reads result pages only from public addresses, never from the home network.
- **Appointments**: a proposed appointment is confirmed only by a plain "yes" in the same conversation.
- **Speaker identification**: the recognition result is given only to signed-in profiles and devices, and it is valid only there. Someone else's voice at a device gets answers but changes no memory.
- **No changes from foreign pages**: changing requests with a login cookie must come from the panel's own page (`Sec-Fetch-Site`/`Origin`). Scripts with a device key or HTTP Basic are not affected.
- **Secrets encrypted**: calendar and mail passwords and Home Assistant tokens are stored encrypted in the profile folders; the key is kept apart in `/var/lib/speech-spark/state/secret.key`.
- **Devices**: *Users → Profiles and devices* and *Me → Security* show when and from where each device key was last used; one click blocks it.
- **Change log**: *Overview → Logs → Change log* lists logins, wrong attempts, lockouts and every change with time, address and who (`/var/lib/speech-spark/state/audit.log`).

## Stability

- **Backups**: every day, before every update, before going back to the previous version and before every restore the panel backs up profiles (memory, conversations, documents, calendars, mail accounts, smart home, speaker ID), cloned voices, settings and the panel password to `/var/lib/speech-spark/backups`. Counted separately, the newest seven daily or manual ones and the newest five from before an update, rollback or restore are kept. *Overview → System and update → Backup* downloads, restores or deletes each one and restores a downloaded file. A restore checks the settings like the settings page does, caps the size and swaps all parts or none; the current state is backed up first. Passwords and tokens are in the backup encrypted, the key is not: on another Spark, calendar and mail passwords and Home Assistant tokens have to be entered again.
- **Back to the previous version**: after an update the update card shows "Back to the previous version", which installs the version that ran before (only versions of the official branch). By hand: `sudo /opt/speech-spark/src/update.sh --to <commit>`.
- **Watchdog** (*Settings → System*, on by default): restarts ASR, TTS or an engine that does not answer for 5 minutes, works for 5 minutes without finishing a request, or loads for 45 minutes; at most three times an hour. Every restart is shown on top of the admin pages and in the change log.
- **Live check**: after every update (and on request) the language model answers once, speech output says a sentence and speech recognition has to understand it again. A failure is shown on top of the admin pages.
- **Quality test**: after every update (when the live check passed) and on request (*Overview → System and update → Qualitätstest → Jetzt prüfen*) the panel asks the real language model 20 fixed questions with prepared tool results (appointments, mail, reminders, search, memory) and checks that it picks the right tool and only says what is in the result. No real data is read or changed.
- **Memory warning**: when free memory drops below *Settings → System → Warn below* (default 10 GiB), every admin page shows a warning on top; DGX OS kills processes at about 8 GiB.

## Uninstalling

```bash
sudo ./uninstall.sh            # remove services, code, venvs and the sudoers rule; config, models and voices stay
sudo ./uninstall.sh --purge    # also delete config, models, voices and the user speech
sudo ./uninstall.sh --yes      # no confirmation prompt
```

dgx-spark-qwen38 is not touched.

## What gets installed

| Part | Where | Port |
|---|---|---|
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

## The panel

On the first admin login a **setup wizard** walks through password, language model (with a connection test), voice (to listen to), profiles, access and features, and ends with the live check. Start it again: *Overview → System and update → Run setup again*.

The menu has five entries; Overview, Users and Integrate have a small bar with sub-pages at the top.

- **Assistent** (assistant): voice chat with the dgx-spark-qwen38 LLM. Speak (or type); the answer comes back as text and streamed speech, sentence by sentence while the LLM is still writing. Hands-free mode listens again after each answer; the space bar or "Speak" interrupts.
- **Übersicht** (overview): *Monitoring* (GPU load, free unified memory, temperature, CPU with history; per service status, requests, latency, RTF, start/stop/restart; the running qwen38 lane), *System and update* (version, update, quality test, live check, backup, benchmark) and *Logs*.
- **Einstellungen** (settings): sub-pages on the left. First *Features*: one switch per capability (memory, earlier conversations, documents, web search, reminders, calendar, Home Assistant, e-mail, speaking up by itself, room mode, speaker identification); a feature's details appear only once it is on. Then Assistant (LLM), Conversation (defaults), Web search, Speech output, Speech recognition (Qwen3-ASR or Parakeet), Security (assistant without password, password, API key, ports, reverse proxy addresses) and System (memory guard, watchdog, logs). Technical settings sit under "Advanced". Each sub-page saves on its own; only services whose settings changed are restarted.
- **Nutzer** (users): *Profiles and devices* and *Voices* (reference recordings for voice cloning, only with a `Base` TTS model).
- **Einbinden** (integrate): *Guides* with values to copy for Open WebUI, other OpenAI-compatible apps, the Pebble watch, curl and Python, and *Test* (transcribe an audio file, listen to text).

The panel is available in English and German; the button at the top right switches (default: the browser's language).

## APIs (OpenAI-style)

```bash
# Transcription
curl http://SPARK:31001/v1/audio/transcriptions -F file=@recording.webm -F language=de
# -> {"text": "...", "usage": {"type": "duration", "seconds": 4}, "processing_s": 0.6}

# Speech
curl http://SPARK:31002/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"Hello world","voice":"ryan","language":"English"}' -o hello.mp3
```

Both services answer `GET /health` with status and counters. `GET /v1/voices` (TTS) lists the voices and `GET /v1/models` the loaded model.

Speech recognition accepts anything ffmpeg can read (wav, mp3, webm, mp4, ogg …) and long recordings. `language` is a code (`de`) or a name (`German`); without it the model detects the language. `response_format` is `json`, `text` or `verbose_json` (with `language` and `duration`, without timestamps). With `-F stream=true` the text arrives in pieces as Server-Sent Events in OpenAI format (`transcription.chunk`, then `[DONE]`).

### Streaming speech

With `"stream": true` (and `"response_format": "pcm"`, the default then) the answer arrives as Server-Sent Events as soon as the first sounds are generated:

```
event: speech.audio.delta
data: {"type": "speech.audio.delta", "audio": "<base64>", "response_format": "pcm"}
...
event: speech.audio.done
data: {"type": "speech.audio.done", "usage": {...}}
```

`audio` is PCM, 16 bit, mono, 24 kHz. Errors arrive as `speech.audio.error`. This is vllm-omni's format, passed through unchanged.

```bash
curl -N http://SPARK:31002/v1/audio/speech -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"input":"Hello world","voice":"ryan","language":"English","stream":true,"response_format":"pcm"}'
```

**Steadier delivery:** Qwen samples with `temperature` 0.9 and `top_p` 1.0 by default, so tempo and emphasis vary from sentence to sentence. The server therefore applies `temperature` 0.7, `top_p` 0.9 and `seed` 42 (Settings → Speech output). Requests can override them with the same fields, top-level or inside `extra_params`. In Open WebUI, set response splitting to **paragraphs**: each part is generated separately, and longer parts sound more coherent. Set the default language to a fixed language instead of `auto`.

**Laughing and mood swings:** the model reads emojis, "haha", `*laughs*` and markdown as cues and laughs or changes tone. The server removes them before synthesis (Settings → Speech output → clean text, on by default).

**Overacting:** exclamation marks and interjections ("Oh", "Wow") make the voice act out excitement. With "speak calmly" (on by default) the server turns "!" into "." and drops such interjections at the start of a sentence. The default voice-chat prompt also asks the LLM for plain, calm everyday language.

**Numbers:** the server writes numbers out before synthesis, because the model guesses otherwise. Dates, times, money, percent and decimals become words ("on 2026-10-06 at 9:30, $49.90" → "on October sixth, twenty twenty-six at nine thirty, forty-nine dollars ninety"), phone numbers become pairs. Settings → Speech output → reading numbers: as words (default), in pairs, digit by digit or unchanged. Works for German and English.

**Speaking style:** `"instructions": "calm and friendly, rather slow"` in the request. Without it, the default instruction from Settings → Speech output applies. Only the 1.7B models (CustomVoice, VoiceDesign) follow instructions; the 0.6B models ignore them (per the Qwen model card).

**VoiceDesign** (voice from a description): `"task_type": "VoiceDesign"` and `"instructions": "deep, calm male voice"`. This needs its own model: enable "VoiceDesign zusätzlich bereitstellen" in Settings → Speech output. It starts a second engine with the same memory footprint again.

In the panel under **Testen**, "gestreamt" (streamed) plays audio while it is generated and shows the time to first audio.

### General

The services behave like the OpenAI audio API: TTS returns mp3 by default (also wav, flac, opus, pcm), STT understands `response_format=text`, and the language may be an ISO code like `de`. OpenAI voice names like `alloy` fall back to the default voice. If an API key is set in the panel, apps must send `Authorization: Bearer <key>`.

### Open WebUI

Admin Panel → Settings → Audio:

| Field | STT | TTS |
|---|---|---|
| Engine | OpenAI | OpenAI |
| API Base URL | `http://SPARK:31001/v1` | `http://SPARK:31002/v1` |
| API Key | key from the panel (Settings → Security → API key; the installer always sets one) | same |
| Model | anything | anything |
| Voice | | e.g. `ryan` |

If Open WebUI runs in Docker on the same Spark, use the LAN IP or `host.docker.internal` instead of `SPARK` (container started with `--add-host=host.docker.internal:host-gateway`). The panel shows these values ready to copy in the **Einbinden** tab.

### "Hey Siri, ask Spark"

An iPhone shortcut sends the dictated question to `POST /api/siri/ask` (header `X-Speech-Device` with a
device key of your profile, body `{"text": "..."}`) and lets Siri speak the `answer` field. Works without
the page open, also on Apple Watch, AirPods and CarPlay; follow-ups within 10 minutes keep the context,
and each day's questions are kept as a conversation of the profile. Step by step under Einbinden → Guides.

### Pebble watch

The watch app "Spark" (`app/pebble/speech-spark.pbw`, source in `pebble/`) brings the voice chat to Pebble Time 2 and Core 2 Duo, with the answer as text and through the watch speaker. On Pebble Round 2 the answer is text only. It needs a watch firmware with the speaker API (from about v4.9.170).

1. In the panel under **Users → Profiles and devices**, add a device "Pebble" to your profile and copy its key.
2. On the paired phone, download `http://SPARK:31080/pebble/speech-spark.pbw` and open it with the Pebble app.
3. In the Pebble app, open the settings of "Spark": Spark address (`http://SPARK:31080`) and device key. Settings and "Start App" stay grey while the Pebble app does not see the watch as connected (tab Devices).
4. On the watch: SELECT asks (dictation through the phone), SELECT again stops the speech, long SELECT starts a new conversation. A small face at the top shows whether Spark listens, thinks or speaks; its mouth follows the speech. The watch setting Settings → Sounds & Haptics → Volume caps how loud the app can get.

The phone must reach the Spark, at home over Wi-Fi, on the road through a VPN such as Tailscale. The app uses HTTP because the Pebble app does not trust the self-signed certificate. On the Spark, `POST /api/watch/ask` and `GET /api/watch/poll` serve it: the answer is made like in the voice chat (kept short), the audio is compressed for the small speaker (quiet syllables lifted, peaks softly limited) and goes to the watch as 8 kHz IMA ADPCM.

## Measuring performance

In the panel under **System → Leistung messen**, or on the console:

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

## Troubleshooting

| Symptom | Fix |
|---|---|
| Installer: "torch in venv-… has no CUDA" | Run `sudo ./install.sh` again. If that does not help, delete `/opt/speech-spark/venv-*` and reinstall. |
| Panel shows `blocked` | Not enough memory next to the running qwen38 lane. Switch to 0.6B, lower the reserve (at your own risk) or stop the big lane. |
| Panel shows `error` | Read the message in the panel and under Logs. |
| `no kernel image is available` | A package was built without Blackwell kernels. Check with `/opt/speech-spark/venv-engine/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| Engine does not start | Panel → Logs → engine. With "No available memory for the cache blocks", raise the engine's memory share in the panel. The first start downloads the model and takes longer. |
| Update fails | Panel → Overview → System and update → update log. The old version keeps running or is installed again; the log says which. |
| Port taken | Change the port in `/etc/speech-spark/config.json` and run the installer again. |

The per-model memory estimates (`MODEL_GIB` in `app/common.py`) are rough assumptions; correct them with the values the panel shows.

## License

MIT, see [LICENSE](LICENSE). The models (Qwen3-ASR, Qwen3-TTS) and packages (vLLM, vllm-omni, PyTorch) are downloaded during installation and come under their own licenses. This project is not affiliated with NVIDIA or the Qwen team.
