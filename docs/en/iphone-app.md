# iPhone app "Spark"

An own app for the iPhone (source in `ios/`): press the button, ask, the answer comes in the Spark voice, also with the screen locked. "Hey Siri, Ask Spark" (German phrase "Frag Spark") runs through the app without a shortcut, also with AirPods and through Siri in the car. CarPlay as its own icon in the car is planned and needs Apple's approval.

## Switch it on in the panel

1. Admin: **Settings → Features → iPhone app** on, save.
2. Profile: **Me → iPhone app → "iPhone app for me"** on.
3. To switch lights and devices from the app: **"Smart home from the app"** on. The code word applies as everywhere.
4. For the wake word and stand mode: **"Allow listening all the time"** on.
5. To start routes and calls by voice: **"Routes and calls on the iPhone"** on.
6. Notes on its own (morning briefing, reminders) come when **"On its own"** is on for the profile. Reminders and timers ring as iPhone notifications, also with the app closed.

## Getting the app onto the iPhone (on a Mac, about 15 minutes once)

1. Install **Xcode** from the Mac App Store (free) and open it once.
2. Xcode → **Settings → Accounts → +** → sign in with your Apple ID. A free account is enough to try it; the app then runs for 7 days and has to be installed again. With the Apple Developer Program (99 €/year) it runs for a year and works with TestFlight.
3. Get the repo: `git clone https://github.com/db9979/speech-on-dgx-spark.git` (or `git pull`).
4. Double-click `ios/Spark.xcodeproj`.
5. Click the project **Spark** → target **Spark** → **Signing & Capabilities** → pick your account as **Team**. If Xcode says the bundle ID is taken, add something of your own to the **Bundle Identifier**.
6. Connect the iPhone by cable, unlock it, confirm "Trust This Computer".
7. On the iPhone: **Settings → Privacy & Security → Developer Mode** on (the iPhone restarts).
8. In Xcode pick your iPhone as the destination at the top, then press **▶︎ (Run)**.
9. On first start the iPhone says "Untrusted Developer": **Settings → General → VPN & Device Management → your Apple ID → Trust**. Then open the app.

## Pairing

1. In the panel **Me → iPhone app → "Pair an iPhone"**.
2. On a PC: scan the QR code with the iPhone camera. On the iPhone: tap **"open in the app"**.
3. The app asks "Pair with this Spark?" and shows the address. Tap **Pair** only for your own address.

The link is valid for 10 minutes and once. The address must be https with a real certificate (your reverse proxy); the self-signed certificate on port 31443 is not accepted.

## Using it

- The assistant's face at the top is the same as in the panel (robot or comic, picked by the admin under Settings → Defaults; the app takes it over when it opens). It blinks, looks around, listens with a red antenna, thinks with a turning arc and moves its mouth while speaking. Tapping it works like the button.
- Big button: tap, speak; the app notices when you are done (or tap again). Tapping while the Spark speaks stops it.
- Questions can also be typed. Top left starts a new conversation; after 10 minutes of quiet it starts anew by itself.

In the app under **Settings (gear)**:

| Switch | What it does |
|---|---|
| Hands-free | After each answer the app listens again. 8 seconds of silence: microphone off. |
| Interrupt | Just start talking to stop the answer and be heard. The iPhone filters the Spark's own voice out of the microphone. |
| Wake word | "Hey Spark", "Jarvis" or "Computer". The iPhone recognizes it itself, offline and without Apple's servers; only then does anything go to your Spark. If the iPhone cannot do German offline, it stays off. |
| On battery | How long the wake word listens on battery after the last use (charger only, 30 minutes, 1 or 3 hours). Always on the charger. |
| Stand mode | On the charger: big face, clock, last answer, screen stays on, dimmed at night. |
| Speak on its own | The app says the Spark's notes aloud while it is open. |

Routes and calls: "Navigiere zur Arbeit" or "Ruf Anna an". The app asks every time ("Open route to …?", "Call Anna (number)?"). Only "Ja" (tapped or said) opens Maps or calls. Contacts are searched only on the iPhone; the number does not go to the Spark.

## Security

- Each iPhone gets its own key when pairing, kept only in that iPhone's keychain and on the Spark only as a hash.
- The key may only ask and listen (chat, speech recognition, Siri question). Settings, memory, devices, connections and further pairings are refused.
- The profile's switch off locks all its iPhones at once, the admin switch all of them. Remove a lost iPhone under **Me → iPhone app → Remove**.
- Smart home from the app only with its own switch and the code word. What the app claims to be does not count; the panel decides by the key.
- Wake word, stand mode, routes and calls only with their own switch in the panel. The Spark only suggests a route or call; the tool exists only for the app key with the switch, and only your "yes" on the iPhone starts it. Outside text (mail, web page) cannot start a route or call.
- No sound goes to the Spark before the wake word. In the background the app listens only with the wake word on.
- Pairing only from the profile's own browser login, with the second login step when the profile has it. At most 5 iPhones per profile.

Every push that changes `ios/` builds the app on GitHub for the simulator (`.github/workflows/ios.yml`).
