# Spark watch app (Pebble)

Source of `app/pebble/speech-spark.pbw`, which the panel serves at `/pebble/speech-spark.pbw`.

- `src/c/main.c`: watch side. SELECT starts dictation, the text goes to the phone; the answer
  arrives as text (`ANSWER`) and 8 kHz IMA ADPCM (`AUDIO`), decoded into the speaker stream.
  The phone only sends as much audio as the watch buffer has room for (`CREDIT`).
- `src/c/face.c`: the face above the answer (idle, listen, think, speak, sad; the mouth follows
  the audio level). A new design replaces only this file and keeps the calls in `face.h`.
- `src/pkjs/index.js`: phone side. `POST /api/watch/ask`, then `GET /api/watch/poll` until done,
  with the device key in `X-Speech-Device`.
- `src/pkjs/config.js`: settings page (Spark address, device key, speech, volume, auto-listen).

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
