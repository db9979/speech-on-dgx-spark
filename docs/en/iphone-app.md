# iPhone app "Spark"

An own app for the iPhone (source in `ios/`): press the button, ask, the answer comes in the Spark voice, also with the screen locked. "Hey Siri, Ask Spark" (German phrase "Frag Spark") runs through the app without a shortcut, also with AirPods and through Siri in the car. CarPlay as its own icon in the car is planned and needs Apple's approval.

## Switch it on in the panel

1. Admin: **Features → iPhone app** on, save.
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

**With an invitation** (since V01.0.276): when someone without a profile opens the invitation link on the iPhone and taps "Rather straight in the iPhone app", the app creates the profile with name and PIN and is paired right away. The app shows the Spark's address first. An app that is already paired takes no invitation (unpair first); PIN links work only in the browser.

## Using it

- The assistant's face at the top is the same as in the panel (robot or comic, picked by the admin under Settings → Defaults; the app takes it over when it opens). It blinks, looks around, listens with a red antenna, thinks with a turning arc and moves its mouth while speaking. Tapping it works like the button.
- Big button: tap, speak; the app notices when you are done (or tap again). Tapping while the Spark speaks stops it.
- Questions can also be typed. Top left starts a new conversation; after 10 minutes of quiet it starts anew by itself.

In the app under **Settings (gear)**:

| Switch | What it does |
|---|---|
| Hands-free | After each answer the app listens again. 8 seconds of silence: microphone off. Since V01.0.272 a value of your profile: browser and app show the same (like "Interrupt"). |
| Interrupt | Just start talking to stop the answer and be heard. The iPhone filters the Spark's own voice out of the microphone. |
| Wake word | "Hey Spark", "Jarvis" or "Computer". The iPhone recognizes it itself, offline and without Apple's servers; only then does anything go to your Spark. If the iPhone cannot do German offline, it stays off. |
| On battery | How long the wake word listens on battery after the last use (charger only, 30 minutes, 1 or 3 hours). Always on the charger. |
| Stand mode | On the charger: big face, clock, last answer, screen stays on, dimmed at night. |
| Speak on its own | The app says the Spark's notes aloud while it is open. |

Routes and calls: "Navigiere zur Arbeit" or "Ruf Anna an". The app asks every time ("Open route to …?", "Call Anna (number)?"). Only "Ja" (tapped or said) opens Maps or calls. Contacts are searched only on the iPhone; the number does not go to the Spark.

## Quick start, history, photos, offline

- **Quick start:** "Talk to Spark" opens the app and it listens at once. On the Action button: iPhone Settings → Action Button → Shortcut → "Talk to Spark". In Control Center (iOS 18 and later) via "Add a Control", on the lock screen as a widget. With Siri: "Hey Siri, Start Spark".
- **History:** The clock icon at the top left shows your earlier conversations, the same list as the panel's log. Tapping one continues it. Deleting stays in the panel.
- **Ask about a photo or document:** The paper clip next to the input: take a photo, choose a photo, or a document (PDF, text, image). The iPhone reads the text itself, scanned pages too. Only the text goes to the Spark. The attachment stays for the conversation until you remove it with ✕. **Let the Spark look at photos:** with "Let the model look at photos from the app" on under Me → iPhone app (plus the admin and profile switches for pictures), a photo goes to the Spark as a picture, scaled to 1280 px, so it also recognises things, plants or an error display. Follow-up questions about the same photo work for 10 minutes. With it off, the iPhone reads only the text as before. PDFs and documents always stay text.
- **Save to "My documents":** With "Store documents from the app" on under Me → iPhone app in the panel, the attachment shows a button for it. The Spark then finds the document later, like an upload in the panel.
- **Offline:** When the Spark cannot be reached, the app says so at the top. Typed questions wait (at most 10, for one day) and go out once the Spark is back. Speaking does not work then, because the Spark recognises the speech.
- **English:** On an iPhone set to English the app is in English, including the wake word and Siri ("Ask Spark", "Start Spark").

## My profile

In the app under Settings → **My profile** you set the same values as in the panel; changes apply on both sides at once:

- **Voice:** voice and speaking speed, with "Listen to a sample".
- **Answers:** answer length. Your wishes for the tone are only shown; they change in the panel, because the language model is told them.
- **By itself:** on/off, quiet time, at most so many notes a day, appointments with lead time, weather with place and time, parcels, birthdays, bus and train, greeting, mails, morning briefing with time. Shown only when the admin has "By itself" on. Topics whose service is off in the profile are greyed out.
- **What the app may do:** shown only. Change it in the panel under Me → iPhone app.

## Reminders, sharing, Shortcuts

- **Apple Reminders:** With "Apple Reminders on the iPhone" (Me → iPhone app, off) the app asks after each Spark reminder "… also put into the Reminders app?". After "yes" it is in the list "Spark", without its own alarm (the Spark rings already). When the Spark cancels a reminder it goes there too. New shopping and to-do entries come into the lists "Shopping" and "To-dos" when the app opens (each entry once). A list kept in a CalDAV account stays there.
- **Share → Spark:** In Safari, Mail, Files or Photos tap Share → Spark. Text, web page (the iPhone loads it itself), PDF or photo: the iPhone reads the text (a photo goes as a picture with the photo switch on), then you ask about it or store it under "My documents" (with the documents switch). The answer can be shared, e.g. as a note.
- **Shortcuts:** The Shortcuts app gets "Ask Spark", "Reminder at the Spark", "Add to a Spark list" and "Store a document at the Spark". Lists need the reminders switch, documents the documents switch.
- **Notes:** Apple does not let apps write into Notes directly. Two ways: long-press an answer in the app → "Share (e.g. as a note)", or a shortcut of "Ask Spark" plus Apple's "Create Note".

## Panel areas in the app

The app takes over the panel bit by bit (plan "iPhone app takes over the panel"). The admin switches on "Panel areas in the iPhone app" under Features, and each profile switches on each area on its own under Me → iPhone app. Everything starts off, guests get none of it. The app itself cannot switch an area on.

- **Open in the panel** (Settings): whatever the app does not show itself opens the panel in Safari at the right place (memory, e-mail, security …). With "Manage the Spark" also monitoring, logs, features and profiles. Pages whose functions the admin switched off entirely say "Switched off by the admin" (since V01.0.276, from the same list `/api/features` as the panel).
- **Features and People and devices under Manage the Spark** (since V01.0.276): the names and groups of the switches come from the Spark, the app keeps no list of its own. A profile also shows its functions "n of m on" to switch, its admin role and the signed-in browsers (swipe to sign out).
- **My day** (switch "My day in the app"): the next appointments of your calendars, the Spark's reminders (swipe to delete) and the memory (look at it, delete single entries, ask for a tidy-up and apply it). Under My profile the conversation switches join: learn from conversations, a new conversation every day and, when the admin allows them, learn from corrections, think when choosing tools and targeted tool choice. Forgetting everything at once stays in the browser.
- **Manage the Spark** (switch "Manage the Spark in the app"): after Face ID you sign in with the admin password and the admin's code, as in the browser. Without the admin's second login step the Spark refuses this sign-in from an iPhone. The sign-in lasts only while the app is open. Inside: **Monitoring** ("Needs you", memory, CPU/GPU, services), **Logs** (diagnosis as in the panel with areas and time span, "Copy for thread" and share) and **Checks** (function check, quality test, priority check). Under **Change** (V01.0.250): **Features** (the plain on/off switches; sensitive ones like "Port", the second login step for profiles and the iPhone switches themselves stay in the browser), **People and devices** (create a profile, remove devices, new PIN, reset the second step, delete a profile; the last three with a code) and **Backups** (back up now, delete old ones; restoring and downloading in the browser). If your profile has an admin role (co-admin or manager, V01.0.256), there is also **"Sign in with my profile"**: with your profile's code instead of the admin password, ending after 15 minutes without use. A manager sees only monitoring, logs, features and profiles and devices; a co-admin does not delete backups.
- **Manage documents** (switch "Manage documents in the app", V01.0.250): in "My documents" swipe to delete, long-press for "For everyone", searching on/off, tags, read again and "Remind me of the deadline". At the bottom "Document switches" with the switches of Me → Documents, as far as the admin allows them.
- **Teach your voice** (switch "Teach your voice in the app"): the app shows three sentences, you read them aloud, saving needs the code from the authenticator app. Below, "Teach" for each of your speakers (the speaker then asks for five sentences). Needs speaker recognition from the admin and your profile's second login step.
- **Proactive** (switch "Proactive in the app"): weather place, parcels from e-mails, bus and train (search and set a stop), look at and stop your jobs, room mode "+30 min" (at most four hours from now). The switches weather, parcels, bus and train and jobs are here too.
- **Security** (switch "Security in the app"): your devices (swipe to remove), recent logins, log out everywhere, turn the second step off or new recovery codes (with a code). Setting it up works only in the browser with the PIN: otherwise someone with your unlocked iPhone alone could set their own second step.
- **Connect accounts** (switch "Connect accounts in the app"): mail, calendar, contacts, smart home and Telegram. Only with your profile's second login step and a fresh code. The Spark checks the connection, stores password or token encrypted and never hands it out; the iPhone does not keep it.

## Looking at my documents

With "Documents from the app" (Me → iPhone app), Settings → **My documents** lists your documents on the Spark, with search. Tap one to open it: a kept PDF or picture opens in Apple's preview (zoom, search, share), and the "Text" tab shows the text the Spark stored. Other file types show as text only. Long texts come in parts: "Read on" at the bottom adds the next one. Deleting and more work with "Manage documents in the app" (above).

## Messages to other profiles

The envelope next to the input opens the messages (a dot shows new ones), no language model involved. "Ready?" shows whether the admin and your profile allow messages and whom you can reach, with the reason for those you cannot (e.g. "has messages off"). Pick the recipient and write (at most 500 characters); in the inbox swipe right to reply, left to delete. A message notification can be answered in place (long press → "Reply"). Who may write to you is set in the browser only. The app does not read messages aloud by itself; ask the assistant ("Do I have messages?"), also in the car. Voice messages are listed; listen to them in the panel. With Siri: "Message with Spark" asks for recipient and text and confirms before sending; the name must match a profile that takes your messages. With many profiles (V01.0.206) "To" opens a list with a search (name or call name), ★ favourites and recent ones on top; the star keeps a favourite on the Spark. "Ready?" then shows only numbers, the names open on a tap. When several profiles fit for Siri, Siri asks "Whom do you mean?" with at most 4 names; for an unknown name it says at most 3 similar ones.

## Where the Spark is listening (room mode)

Since V01.0.209 the app shows when a device of your profile listens in room mode (browser or speaker). Switch it on in the panel under Ich → iPhone-App → "Raum-Modus in der App zeigen" (off, needs room mode from the admin). The top of the chat then reads "● Küche hört zu bis 21:30" with "Beenden", with several devices one line that opens a list. The app asks when it opens, when it comes back and every 30 seconds. The lock screen and the Dynamic Island show a Live Activity with the time left and "Beenden" (turn off in the iPhone Settings → Spark → Live Activities). It is only updated while the app runs; after the end time it reads "vorbei" until the app looks again. The "Raum-Modus" widget (home and lock screen) shows "Küche hört zu bis 21:30" or "Niemand hört zu". With Siri: "End room mode with Spark". The app can only end room mode, never start it; it sees only where and until when, never what was heard.

## Spark update from the app

For chosen profiles, off by default. The admin switches on **Features → Spark update from the iPhone app** and ticks per profile:

- **Notices:** when a new version with green GitHub tests is ready, a notification arrives on the iPhone, once per version and not during the profile's quiet time. Needs "Push to the iPhone app".
- **Start:** the app shows "Update now" under **Settings → Spark version**, confirmed with Face ID (or the iPhone passcode) and a fresh code from the profile's authenticator app, so "Start" can only be ticked for profiles with the second login step.

The page shows the installed and the new version with its changes. The update runs as in the panel: a backup, then update.sh, which installs only versions with green tests. The app follows the progress and the restart. At most one start from the app every 10 minutes; the other profiles with notices hear who started it. Going back to the old version stays in the panel (Status → System/Update).

## Push notifications with the app closed

Needs the Apple Developer Program. Once:

1. developer.apple.com → **Certificates, IDs & Profiles → Keys → +** → tick **Apple Push Notifications service (APNs)** → **Continue → Register → Download**. The `.p8` file can be downloaded only once. The **Key ID** is shown next to it, the **Team ID** under **Membership**.
2. Panel as admin: **Features → Push to the iPhone app** on, enter `.p8`, Key ID, Team ID and the app's bundle ID. **Kind of app**: "Development" while you install from Xcode, "Production" for TestFlight and the App Store. Save.
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
- Photos and documents: the iPhone reads the text, only text goes to the Spark (at most 20,000 characters per question). Photos go as pictures only with the photo switch on; a round with a picture offers no tools, and the picture is not kept in the history. The Spark treats it as outside text: it sits as data in the prompt, not in the conversation, and locks actions as after a mail. The history keeps only the attachment's name.
- Storing documents only with its own switch, only with the app key, at most 10 per minute and 3 MB. The app cannot list or delete the documents.
- "My profile" changes only a fixed list (voice, speed, length, by itself, morning briefing). The app's rights, Telegram, the smart home and the tone cannot be changed through it; a request with any other field is refused as a whole.
- Apple Reminders: only with its own switch, only after "yes" on the iPhone. The app reads nothing from Reminders for the Spark. Shortcuts may only add entries to the lists; list settings stay in the panel.
- Sharing: shared content is outside text (locks actions), at most 20,000 characters per question; the iPhone loads web pages itself, at most 3 MB.
- Waiting questions stay on the iPhone and are deleted when unpairing.
- CarPlay never loosens anything: in the car the smart home is locked without its own car switch.
- Pairing only from the profile's own browser login, with the second login step when the profile has it. At most 5 iPhones per profile.

Every push that changes `ios/` builds the app on GitHub for the simulator (`.github/workflows/ios.yml`).
- Spark update: only the admin gives the rights; starting needs the app's key, Face ID and a fresh 6-digit code of the profile (each code once), at most once in 10 minutes. The app cannot pick a version; only versions with passed GitHub tests are installed. Every start is in the security log, and the language model has no tool for it.
