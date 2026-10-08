# iPhone app "Spark"

An own app for the iPhone (source in `ios/`): press the button, ask, the answer comes in the Spark voice, also with the screen locked. "Hey Siri, Ask Spark" (German phrase "Frag Spark") runs through the app without a shortcut, also with AirPods and through Siri in the car. CarPlay as its own icon in the car is planned and needs Apple's approval.

## Switch it on in the panel

1. Admin: **Settings → Features → iPhone app** on, save.
2. Profile: **Me → iPhone app → "iPhone app for me"** on.
3. To switch lights and devices from the app: **"Smart home from the app"** on. The code word applies as everywhere.

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

## Security

- Each iPhone gets its own key when pairing, kept only in that iPhone's keychain and on the Spark only as a hash.
- The key may only ask and listen (chat, speech recognition, Siri question). Settings, memory, devices, connections and further pairings are refused.
- The profile's switch off locks all its iPhones at once, the admin switch all of them. Remove a lost iPhone under **Me → iPhone app → Remove**.
- Smart home from the app only with its own switch and the code word. What the app claims to be does not count; the panel decides by the key.
- Pairing only from the profile's own browser login, with the second login step when the profile has it. At most 5 iPhones per profile.

Every push that changes `ios/` builds the app on GitHub for the simulator (`.github/workflows/ios.yml`).
