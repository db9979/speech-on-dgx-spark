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
   - on every ESP32 speaker the new server address,
   - the reverse proxy (real certificate for the iPhone app, Android app and passkeys) to the new computer; if it runs on another device its address under Settings → Security → Reverse proxy stays right, if it ran on the DGX itself enter the new address there. Otherwise the iPhone app names the certificate in its "Spark not reachable" note.

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
- **Display** (SSD1306, 128×64) changes every few seconds between eleven pages: Spark, Services and maintenance, Pi (temperature, load, memory), DGX gone or paused, Network, DGX in detail (GPU temperature, free memory, loaded language model), Security (wrong logins and connections the Wächter blocked today, while Live is on, Notaus level), Devices (speakers and apps connected, Verbund), House (Home Assistant, Synology, Kiwix, search as the service watcher sees them), Power (the Pi's under-voltage and throttling, uptime) and Version (Pi and DGX the same or different). When the DGX is gone or paused its page comes first; on a problem the services. Under Funktionen → Gehäuse all pages show as small pictures with the values of now, drawn exactly as on the display: a tap switches a page on or off, dragging or ◀ ▶ changes the order, the big picture shows what is on the display right now. The picture can be turned by 180° (the preview stays upright), "only on problems" keeps it dark otherwise. Night mode: off, dim or fully off between two hours. Against burn-in the content moves by one or two points every 3 minutes, and a picture that does not change for 10 minutes gets darker.
- **LEDs**: green = all running, yellow = pause, a hint or a service missing, red = DGX not reachable.
- **Fans** are driven by the kernel itself (overlay `gpio-fan`); the thresholds apply after the next setup and restart.

The panel never writes system files itself: it leaves a wish and starts the fixed unit `speech-spark-gehaeuse`, which checks the wish again and writes the block itself from two numbers. Check with `sudo speech-spark gehaeuse status`; the Live box "Gehäuse" shows display, LEDs and page, the logs are in the area "gehaeuse".

## Both computers in Monitoring

When the panel and the models run apart, Status → Monitoring shows both computers as equals: a tile each on top (the model computer with free memory, GPU and CPU; the panel computer with used memory, CPU, temperature and disk) and below, under "Computers", two cards side by side with curves of the last 20 minutes:

- **Model computer**: GPU with temperature and power, unified memory with the 8 GiB limit, CPU, disk, network, the running language model and its services. The Wärter sends the values with its status.
- **Panel computer**: CPU, memory (used, available, cache), temperature and fan, SD card or SSD, network, power (the Raspberry Pi's under-voltage and throttling) and its services.

When the model computer does not answer, its card stays, red with "not answering for …" and its last values grey. Under "Braucht dich" the panel speaks up by fixed rules: the panel computer from 80 °C, throttled or short of power, less than 0.5 GiB memory free; on either computer less than 10 % disk free; the model computer not answering. Each note leads to the cards. The same shows in Status → Live (box "Panel computer", the panel computer's CPU next to the model computer's), in the iPhone app under Monitoring and in the Android app through the panel view. Only numbers and fixed words, never addresses or processes; on a single Spark the page stays as before. Logs in the area "system" (`rechner: hinweis …`).

## Control centre on the screen

A screen on the panel computer's HDMI output shows the control centre: everything on one display, as plain text without a desktop or browser (about 20 MB). Switch it on under Features → Control centre on the screen; then it starts at every boot by itself on the first screen, without signing in. Switching it off ends it, and the normal sign-in comes back.

- **Top**: overall state, running requests, notes, maintenance and version, below it the day's numbers (answers, first sound, Wächter, entrance, backup, the screen's times).
- **Middle**: the stages Hören, Weiche, Sprachmodell, Werkzeuge and Sprechen in the frame of the computer they run on; with Spark split tars and the Pi side by side with CPU, GPU, memory, temperature and a 20-minute curve. Every running request has its own colour and visibly jumps between the computers; the ways run underneath the boxes, and a finished answer stays with "fertig in … s" as in the Live view.
- **Left** the devices with a request, the connected devices and access over the internet; **right** the services and targets of the Live view that are in use right now (the others in one line "+ N ready" and "+ N quiet", as in Status → Live), the internet behind the Wächter, "Braucht dich", models and services, the last events, security and maintenance.
- **Bottom** the last 20 minutes as curves (GPU, CPU, free memory, temperature) and the answers per hour.

The size follows the screen: at the start and whenever the resolution changes, the screen program picks a Terminus font for at least 160 × 45 characters (Full HD about 160 × 45, 4K with a font twice as big about 240 × 67); "smaller" or "larger" takes the next font. A very small screen gets a short list without the flow. Characters the font lacks are replaced by plain ones. Between "Screen off from" and "Screen on from" (default 23 to 7 o'clock, the same hour twice means always on) it turns the screen dark and the monitor sleeps. Against burn-in the picture moves by one or two characters every 3 minutes.

Only kind, place, time and numbers are shown, never questions, answers or names: everyone in the room sees it. The screen program asks only the panel on the same computer (127.0.0.1) once a second, with a key of its own that only the service user can read; the panel does not answer other computers or a proxy. A slow answer (up to 8 seconds) or a short hiccup keeps the last picture; only after five failed questions in a row it shows "panel gone". New services of the Live view appear by themselves. Status → Live shows in the box "Control centre" whether it shows right now; the service watch reports when it stops asking. Logs in the area "system" (`schirm: …`).

## Checking and finding faults

| What | Command |
|---|---|
| Door, firewall, fingerprint, model computer | `sudo speech-spark teilen status` (on both computers) |
| Check the whole way once | `sudo speech-spark teilen rundlauf` (on the panel computer) |
| Logs of the door and the Wärter | `sudo speech-spark logs tlstor`, `sudo speech-spark logs waerter` (on the DGX) |
| Pair again (new panel computer, new certificate) | DGX: `sudo speech-spark teilen code`, panel computer: `sudo speech-spark teilen koppeln <IP-of-the-DGX>` |

The Live box "Model computer" shows whether the DGX is reachable, how many services run, its version and a pause. Technical details: [Security and operation](security-and-operation.md) and [Architecture](architecture.md).
