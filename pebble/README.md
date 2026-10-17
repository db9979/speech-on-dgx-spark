# Spark watch app (Pebble)

Source of `app/pebble/speech-spark.pbw`, which the panel serves at `/pebble/speech-spark.pbw`.

- `src/c/main.c`: watch side. SELECT starts dictation, the text goes to the phone with a job
  number (`SEQ`); the answer arrives as text (`ANSWER`) and 8 kHz IMA ADPCM (`AUDIO`), decoded into
  the speaker stream. Messages of an older job are dropped. The watch reports how many bytes it
  played (`FREED`, a running total, repeated every 2 s, so a lost report cannot stall the audio);
  the phone sends at most that plus the buffer size. Every message to the phone is retried; no
  message for 30 s ends the answer. Playback starts with 1.5 s buffered; when the buffer runs dry it waits
  for 1 s more (plus 0.5 s per earlier stall) instead of playing every scrap, and counts the stall
  (`STALLS`, "Aussetzer" in the log line).
- Notaus: holding SELECT 3 s (after the 600 ms "Neues Gespräch") arms it with a long buzz; letting go sends
  the fixed sentence "Spark, Notaus" as a question. The Spark decides (big Notaus only for an admin profile's watch).
- `src/c/face.c`: the face above the answer (idle, listen, think, speak, sad; the mouth follows
  the audio level): the robot, the comic face or the comic woman, whichever the admin picked in the panel
  (`chat.face`, sent as `FACE` with each answer and kept on the watch). `src/c/comic_shapes.h` is
  made by `tools/comic_shapes.py` from the comic faces in `app/panel/static/js/face.js`.
- `src/pkjs/index.js`: phone side. `POST /api/watch/ask`, then `GET /api/watch/poll` until done,
  with the device key in `X-Speech-Device`. Text goes ahead of audio, failed sends are retried,
  audio pieces are up to 3.8 KB, and at the end `POST /api/watch/report` puts the times into the
  Spark log (Zustand → Logs, area "Uhr"). `APP_VERSION` must match `version` in `package.json`; the Spark
  compares it with the app file it serves and the phone adds "Neue Uhr-App" under an answer once a day.
- `src/pkjs/config.js`: settings page (setup code from Ich → Pebble-Uhr, or Spark address and
  device key; speech, volume, auto-listen).

- `src/c/agenda.c` (app 2.0): reminders, timers and quick commands kept on the watch. The phone sends the next
  reminders (`AGENDA`, "id|due|made|rep|text" per line, `REMIND` 0 when the admin switched it off) and the quick
  commands (`QUICK`); they sit in persistent storage (keys 100-141) and every reminder gets a wake-up, so it rings
  without the phone. Alert: UP close, SELECT later (10 min), DOWN end a series; timer ring: UP +1 min, long DOWN stop.
  What the watch rang or changed goes back through one queued `REM_ID`/`REM_ACT` message (`POST /api/watch/reminder`).
  Long UP shows the quick commands, long DOWN the reminders.
- Follow-ups (`FOLLOW`, up to 3 lines) open with DOWN at the end of an answer; a proposal (`PROPOSAL`) shows ✓ and ✕,
  which send "Ja" or "Nein". `WHERE` 1 shows "unterwegs" when the phone uses the second address.
- `src/pkjs/index.js` also keeps a second address (`server_out`, https only, from the setup line's `&aussen=`): when
  home does not answer within 4 s it uses that one for 5 minutes. `GET /api/watch/sync` fills the watch at start,
  after a reminder was set and after saving the settings.

- App 2.1: the list (long UP) starts with fixed entries the phone adds when the admin released them ("\x01" and a
  letter: T Mein Tag, W Meine Woche, M Merken). Tag/Woche send `BRIEF_ASK`, Merken dictates and sends `NOTE`; the
  phone answers with `BRIEF` (fixed sentences from `GET /api/watch/brief`, or "Gemerkt: …" from `POST
  /api/watch/merken`, with the place when `place` is on and the person allowed location).
- `zifferblatt/`: the Spark-Zifferblatt, a watchface of its own (served as `/pebble/spark-zifferblatt.pbw`, paired
  with a setup code of its own). Every 15 minutes it sends `REFRESH`; the phone fetches `GET /api/watch/blick` and
  sends `NEXT_T`/`NEXT`, `REM_T`/`REM`, `WX`, `TIP`, `ALERT` (admins; a new one buzzes twice) and `WHERE`. The parts
  are kept in persistent storage. The workflow builds both and puts both files on `pebble-build`.
- App 2.2: two more fixed entries, C Nachrichten and F Fernbedienung. They send `LIST_ASK` ("C"/"F"); the phone
  answers with `LIST` ("C" or "F", then one line per chat or per device as "name|letters", one letter per button:
  u toggle, a on, o off, p play/pause, w next, l louder, s quieter, f up, z down) and the watch opens an ActionMenu.
  A pick goes back as `LIST_ASK` "c3" or "f2:l", only the place and the letter; the phone keeps the list and calls
  `GET /api/watch/chat` or `POST /api/watch/fern`. A chat comes as `BRIEF` with `FOLLOW` (the replies, "\x01D" is
  dictation) and `REPLYTO`; a tapped or dictated reply goes as `REPLY` (`POST /api/watch/chat`). With `HEALTH_ON` 1
  (sync) the watch adds `HEALTH` "steps|bpm|sleep" (Pebble Health, -1 unknown) to each `SYNC`, and the phone sends it
  to `POST /api/watch/gesundheit` with the phone's date.

Platforms: emery (Pebble Time 2) and flint (Core 2 Duo) with speaker, gabbro (Pebble Round 2)
text only.

## Building

GitHub builds it on every change in `pebble/` (workflow "Pebble watch app", artifact `speech-spark-pbw`);
copy that file to `app/pebble/speech-spark.pbw` in a commit. By hand:

```sh
uv tool install pebble-tool
pebble sdk install latest
pebble build
cp build/pebble.pbw ../app/pebble/speech-spark.pbw
```

The app declares SDK minor `0x5e` (the revision that added the speaker API), so it also runs on
watch firmware older than the current SDK. A firmware refuses apps built for a newer SDK minor than
its own. When building with a newer SDK, set `PROCESS_INFO_CURRENT_SDK_VERSION_MINOR` to `0x5e` in
`<sdk>/pebble/<platform>/include/pebble_process_info.h`; the exported function table is append-only,
so the binary stays compatible as long as the app uses nothing newer than the speaker API.
