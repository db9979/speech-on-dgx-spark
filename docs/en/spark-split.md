# Spark split: the panel on a computer of its own

← [README](../../README.md)

Normally everything runs on the DGX Spark: models, APIs and the panel with the assistant. That stays the default. If you like, the panel and the small services (chats, reminders, speakers, Telegram, logs) move to a small computer of their own, for example a Raspberry Pi 5. The DGX then only serves the models: speech recognition, speech output, pictures and the own language model.

**What for:** the DGX may restart, switch models or be switched off, and chats, calls, reminders, announcements and logs keep running. Voice questions get the fixed sentence "The Spark is taking a break right now." meanwhile (emergency mode), and the Dienst-Wächter reports the outage. With Features → Emergency mode with Parakeet the panel computer then hears by itself and understands a few fixed commands without a language model: lights and devices through Home Assistant, the time and your own reminders. Speakers hear sentences recorded beforehand.

## What you need

- **Computer for the panel:** Raspberry Pi 5 with 8 GB, an NVMe SSD instead of an SD card, wired LAN and a fixed IP address in the router. As the system Raspberry Pi OS Lite 64-bit in the current version (Trixie, Python 3.13), booting from the NVMe. A case like the SunFounder Pironman 5 brings the M.2 slot along; then without an extra NVMe board. Other 64-bit computers with Debian or Ubuntu and Python 3.11 or newer work the same way.
- **The own language model on the DGX:** Spark split reaches the language model through the LLM-Tor. qwen38 cannot be reached from the panel computer, so first `sudo speech-spark modelle llm uebernehmen` (see [Installation](installation.md)).
- Both computers in the same home network.

## New install, split

1. **On the DGX:**
   ```bash
   sudo ./install.sh --mode api --teilen
   ```
   This installs the models, the TLS-Tor, the Wärter and the firewall and shows a pairing code at the end (6 characters, valid 10 minutes, one use). A new code any time with `sudo speech-spark teilen code`.
2. **On the panel computer:**
   ```bash
   git clone https://github.com/db9979/speech-on-dgx-spark
   cd speech-on-dgx-spark
   sudo ./install.sh --mode panel --modelle <IP-of-the-DGX>
   ```
   It asks for the code, pairs, installs only the panel (without torch, vLLM or CUDA) and then runs the round trip: speech output speaks a sentence, speech recognition has to understand it.

## Moving an existing Spark

The panel with all profiles, memory, chats, voices and settings moves in one go.

1. **On the new panel computer** install the panel as in step 2 above, but only once the DGX shows the code.
2. **On the DGX:** `sudo speech-spark umziehen --code`. It makes a move backup with the vault key (sealed with a random password) and the panel's https certificate and shows the code.
3. While pairing, the new computer fetches the move, restores it, counts the profiles and reports "fertig". On a panel computer that is already installed this also works with `sudo speech-spark umziehen --von <IP-of-the-DGX>`.
4. Only after this "fertig" does the DGX switch its panel off and run on as the model computer. If something breaks off, the DGX stays as it was. No step deletes anything.
5. **By hand afterwards** (also listed under Status → Update for 14 days):
   - in the router the forward of 31443 and the ports for calls (Features → Chats → "Calls when away") to the new computer,
   - in Home Assistant Wyoming to `<new-computer>:31003`,
   - on every ESP32 speaker the new server address.

The apps stay signed in because the panel's certificate moves along. What is changed in the old panel between the backup and the switch does not move; best move while nobody is talking.

## Taking it back

On the panel computer `sudo speech-spark umziehen --code`, on the DGX `sudo speech-spark zurueckholen --von <IP-of-the-panel-computer>`. The same way in the other direction; afterwards everything runs on the DGX again, and the panel computer only switches its panel off (its data stays).

## How the connection is protected

- Nothing crosses between the computers in plain text: the TLS-Tor on the DGX speaks only TLS 1.3 with its own certificate, and the panel computer trusts exactly that one (remembered at the pairing).
- The pairing code proves while pairing that both see the same certificate. Whoever stands in between shows another one and gets nothing.
- The DGX's firewall lets only the panel computer reach the door's ports. Every command to the Wärter is signed with a key of its own, carries a time stamp and counts only once.
- Which version the DGX installs is decided by its own rules, never by the panel computer.

## Case of the panel computer (Pironman 5)

When the Raspberry Pi sits in the Pironman 5 case, the small display shows the state, the four LEDs light in the status colour and the fans run by temperature. Switch it on under Funktionen → Gehäuse (admin only, shown only on a split Spark): pick "Pironman 5", "Set up" (admin code), then "Restart". Or at install time `sudo ./install.sh --gehaeuse pironman5` and restart the Pi afterwards.

- **Set up** writes a marked block into `/boot/firmware/config.txt` (I2C, SPI, fan on GPIO 6 with on and off threshold), loads `i2c-dev` and gives the service user the groups `i2c`, `spi`, `gpio`. A copy of the old file stays as `config.txt.speech-spark-alt`. **Remove** takes only this block out again.
- **Display** (SSD1306, 128×64) changes every few seconds between the pages Spark, Services and maintenance, Pi (temperature, load, memory), DGX gone or paused, Network. When the DGX is gone or paused that page comes first; on a problem the services. Pages can be left out, the picture turned by 180°, "only on problems" keeps it dark otherwise. Night mode: off, dim or fully off between two hours.
- **LEDs**: green = all running, yellow = pause, a hint or a service missing, red = DGX not reachable.
- **Fans** are driven by the kernel itself (overlay `gpio-fan`); the thresholds apply after the next setup and restart.

The panel never writes system files itself: it leaves a wish and starts the fixed unit `speech-spark-gehaeuse`, which checks the wish again and writes the block itself from two numbers. Check with `sudo speech-spark gehaeuse status`; the Live box "Gehäuse" shows display, LEDs and page, the logs are in the area "gehaeuse".

## Checking and finding faults

| What | Command |
|---|---|
| Door, firewall, fingerprint, model computer | `sudo speech-spark teilen status` (on both computers) |
| Check the whole way once | `sudo speech-spark teilen rundlauf` (on the panel computer) |
| Logs of the door and the Wärter | `sudo speech-spark logs tlstor`, `sudo speech-spark logs waerter` (on the DGX) |
| Pair again (new panel computer, new certificate) | DGX: `sudo speech-spark teilen code`, panel computer: `sudo speech-spark teilen koppeln <IP-of-the-DGX>` |

The Live box "Model computer" shows whether the DGX is reachable, how many services run, its version and a pause. Technical details: [Security and operation](security-and-operation.md) and [Architecture](architecture.md).
