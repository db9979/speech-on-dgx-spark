# Spark watch app (Pebble)

Source of `app/pebble/speech-spark.pbw`, which the panel serves at `/pebble/speech-spark.pbw`.

- `src/c/main.c`: watch side. SELECT starts dictation, the text goes to the phone with a job
  number (`SEQ`); the answer arrives as text (`ANSWER`) and 8 kHz IMA ADPCM (`AUDIO`), decoded into
  the speaker stream. Messages of an older job are dropped. The watch reports how many bytes it
  played (`FREED`, a running total, repeated every 2 s, so a lost report cannot stall the audio);
  the phone sends at most that plus the buffer size. Every message to the phone is retried; no
  message for 30 s ends the answer.
- `src/c/face.c`: the face above the answer (idle, listen, think, speak, sad; the mouth follows
  the audio level): the robot or the comic face, whichever the admin picked in the panel
  (`chat.face`, sent as `FACE` with each answer and kept on the watch). `src/c/comic_shapes.h` is
  made by `tools/comic_shapes.py` from the comic face in `app/panel/static/js/face.js`.
- `src/pkjs/index.js`: phone side. `POST /api/watch/ask`, then `GET /api/watch/poll` until done,
  with the device key in `X-Speech-Device`. Text goes ahead of audio, failed sends are retried,
  audio pieces are up to 3.8 KB, and at the end `POST /api/watch/report` puts the times into the
  Spark log (Zustand → Logs, area "Uhr"). `APP_VERSION` must match `version` in `package.json`; the Spark
  compares it with the app file it serves and the phone adds "Neue Uhr-App" under an answer once a day.
- `src/pkjs/config.js`: settings page (setup code from Ich → Pebble-Uhr, or Spark address and
  device key; speech, volume, auto-listen).

Platforms: emery (Pebble Time 2) and flint (Core 2 Duo) with speaker, gabbro (Pebble Round 2)
text only.

## Building

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
