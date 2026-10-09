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
5. Click the project **Spark** → target **Spark** → **Signing & Capabilities** → pick your account as **Team**. Do the same for the second target **SparkNotify** (it fetches the text of push notifications). If Xcode says the bundle ID is taken: project **Spark** (not the target) → **Build Settings** → search `APP_BUNDLE_ID` and add something of your own; both targets take it over.
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

## Quick start, history, photos, offline

- **Quick start:** "Talk to Spark" opens the app and it listens at once. On the Action button: iPhone Settings → Action Button → Shortcut → "Talk to Spark". In Control Center (iOS 18 and later) via "Add a Control", on the lock screen as a widget. With Siri: "Hey Siri, Start Spark".
- **History:** The clock icon at the top left shows your earlier conversations, the same list as the panel's log. Tapping one continues it. Deleting stays in the panel.
- **Ask about a photo or document:** The paper clip next to the input: take a photo, choose a photo, or a document (PDF, text, image). The iPhone reads the text itself, scanned pages too. Only the text goes to the Spark, never the picture. The attachment stays for the conversation until you remove it with ✕. Pictures without text do not help, the Spark has no image model.
- **Save to "My documents":** With "Store documents from the app" on under Me → iPhone app in the panel, the attachment shows a button for it. The Spark then finds the document later, like an upload in the panel.
- **Offline:** When the Spark cannot be reached, the app says so at the top. Typed questions wait (at most 10, for one day) and go out once the Spark is back. Speaking does not work then, because the Spark recognises the speech.
- **English:** On an iPhone set to English the app is in English, including the wake word and Siri ("Ask Spark", "Start Spark").

## Push notifications with the app closed

Needs the Apple Developer Program. Once:

1. developer.apple.com → **Certificates, IDs & Profiles → Keys → +** → tick **Apple Push Notifications service (APNs)** → **Continue → Register → Download**. The `.p8` file can be downloaded only once. The **Key ID** is shown next to it, the **Team ID** under **Membership**.
2. Panel as admin: **Settings → Features → Push to the iPhone app** on, enter `.p8`, Key ID, Team ID and the app's bundle ID. **Kind of app**: "Development" while you install from Xcode, "Production" for TestFlight and the App Store. Save.
3. Profile: **Me → iPhone app → "Notifications to the iPhone"** on.
4. Open the app once and allow notifications, then **"Send a test message"** in the panel.

Then reminders and timers (also those set in the panel or on a speaker), the morning briefing, notes and memory tidying arrive with the app closed. Only "Neue Nachricht vom Spark" goes through Apple; the text stays on the Spark for 24 hours and the app fetches it with its key. With push, reminders no longer ring twice. At most 30 notifications per hour and profile.

## CarPlay

An own "Spark" icon in the car. Tap → **"Mit Spark sprechen"** → talk. The conversation goes on hands-free until 8 seconds of silence; interrupting works as in the app. The car shows only the state, never text. Answers are short in the car. Smart home in the car only with its own switch **"Smart home in the car too"** and the code word. Route and call only after "Ja".

**Apple must grant CarPlay first**: request the category "Voice-based conversational app" at developer.apple.com/contact/carplay. After approval, enable it for the App ID and add `<key>com.apple.developer.carplay-voice-based-conversation</key><true/>` to `ios/Spark.entitlements` (not before: without the grant Xcode cannot sign the app). After the grant, try it without a car: Simulator → **I/O → External Displays → CarPlay**.

## Publishing

Step by step (TestFlight, App Store): [iphone-publishing.md](iphone-publishing.md).

## Security

- Each iPhone gets its own key when pairing, kept only in that iPhone's keychain and on the Spark only as a hash.
- The key may only ask and listen (chat, speech recognition, Siri question). Settings, memory, devices, connections and further pairings are refused.
- The profile's switch off locks all its iPhones at once, the admin switch all of them. Remove a lost iPhone under **Me → iPhone app → Remove**.
- Smart home from the app only with its own switch and the code word. What the app claims to be does not count; the panel decides by the key.
- Wake word, stand mode, routes and calls only with their own switch in the panel. The Spark only suggests a route or call; the tool exists only for the app key with the switch, and only your "yes" on the iPhone starts it. Outside text (mail, web page) cannot start a route or call.
- No sound goes to the Spark before the wake word. In the background the app listens only with the wake word on.
- Push: the Apple key (.p8) is stored encrypted, changed only by the admin with the second step, never shown again. Apple only gets a fixed sentence and a random number. Only the app with its own key signs up its push address; only the profile's own app gets a notification's text.
- Photos and documents: the iPhone reads the text, only text goes to the Spark (at most 20,000 characters per question). The Spark treats it as outside text: it sits as data in the prompt, not in the conversation, and locks actions as after a mail. The history keeps only the attachment's name.
- Storing documents only with its own switch, only with the app key, at most 10 per minute and 3 MB. The app cannot list or delete the documents.
- Waiting questions stay on the iPhone and are deleted when unpairing.
- CarPlay never loosens anything: in the car the smart home is locked without its own car switch.
- Pairing only from the profile's own browser login, with the second login step when the profile has it. At most 5 iPhones per profile.

Every push that changes `ios/` builds the app on GitHub for the simulator (`.github/workflows/ios.yml`).
