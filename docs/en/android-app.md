# Android app "Spark" (APK, no store)

The app is a thin shell around the Spark's page: it shows the Spark as the phone browser does (like the iPhone app,
since V01.0.296) and adds only what a page cannot do:

- **Notes while the app is closed:** the app asks the Spark itself every 15 minutes (`/api/android/notes`), no
  Google service. Reminders, the morning briefing and notes go there when the app is the device used last or no
  other way (iPhone app) is set up.
- **Notes at once** (1.2.0 and later, V01.0.473): admin: Features → Android app → "Android: notes at once" (off).
  On for every profile at once; it can be switched off under Me → Android app → "Notes at once". Then open the app once. The app then keeps a connection to the
  Spark open (`/api/android/wait`: the Spark answers at once when a notification is there, otherwise empty after
  4 minutes, and the app asks again; from 1.3.3, before 50 seconds). For this to work through the reverse proxy, set its
  timeout to at least 5 minutes there (Synology: Login Portal → Reverse Proxy → Edit → Advanced / timeout); if the proxy
  cuts after a minute, the app falls back to 50 seconds by itself for a day. Chat messages, reminders and notes come without delay, without a Google
  service. Android shows a quiet lasting notice "Mit dem Spark verbunden" for it (a foreground service). So Android
  does not put the connection to sleep: in the Android settings under Apps, Spark, Battery pick "Unrestricted".
  After the phone restarts the connection starts when the app is opened first; until then the app asks every
  15 minutes. Switch off or signed out: the app ends the connection by itself. Live shows "Android-App (sofort)"
  under connections, with the number only.
- **Spark as assistant** (1.4.0 and later, V01.0.732): admin: Features → Android app → "Android: Spark as assistant"
  (off). Once released the assistant button (Settings → Apps → Default apps → Digital assistant → "Spark", then hold
  power or home) opens a sheet over whatever app is open: the Spark's face, what it heard, the answer to read along, a
  field to type and "Ganze App" (whole app). The app records the question itself (the phone's echo and noise
  suppression, a pause of just under a second ends the question), sends it to the Spark (`/api/test/asr`, then
  `/api/chat` as device "android") and plays the answer itself, short and without lists. Speaking during the answer
  makes it quieter; it only stops once the Spark recognizes a real question. With "hands-free" in the chat it
  listens again afterwards. On the lock screen the phone wants to be unlocked first. The conversation is then under
  Chats like any other.
  Also: the **widget** "Spark" for the home screen (face, microphone, numbers only: "Heute: 2 Termine · 1 Erinnerung ·
  3 ungelesen", and where a device listens in room mode), the tile **"Spark zuhören"** in quick settings and the
  **shortcuts** on the app icon (long press: listen, write a question, Today, Chats). When the Spark cannot be reached,
  a typed question waits (at most 10, one day) and goes out by itself once it is back; the answer comes as the
  notification "Antwort vom Spark".
  Without the release the button opens the app listening, as before.
- **Share to Spark:** share text in another app → Spark: the text is put into the text field, you send it yourself.
  From 1.4.0 also **photos, PDFs and Office files** (at most 3): the app asks "Dazu fragen" (ask about it) or "Nur
  ablegen" (just store). A photo is made smaller on the phone (1280 pixels) and drawn anew (no place or camera data),
  then attached to the conversation (needs "Recognize images") or stored under "Meine Dokumente"; other files go to
  "Meine Dokumente" (needs "Documents"), then "Fass das Dokument … kurz zusammen." is put into the text field. Nothing
  is ever sent by itself.
- **Fingerprint for admins** (1.4.0 and later, V01.0.732): admin: Features → Android app → "Android: fingerprint for
  admins" (off). When the app is signed in with a profile with an admin role, it asks for the phone's fingerprint,
  face or screen lock when opened and after 5 minutes in the background (like Face ID before "Spark verwalten" in the
  iPhone app). Android checks it; the app learns only yes or no, the Spark nothing.
- **Emergency stop tile** (1.1.0 and later): edit quick settings → add "Notaus". Admins choose "Ganzer Spark" (stage 2) or "Mein Notaus", everyone else "Mein Notaus", always behind a question; lifting only in the browser (see [Security and operation](security-and-operation.md)).
- **New version:** the app shows a notification when the Spark has a newer APK.
- **Calm during a Spark update** (from 1.3.2, V01.0.570): when the Spark restarts (an update), the app shows "Spark startet neu … Die Seite kommt gleich wieder." (Spark restarting … the page is back in a moment) and tries again by itself instead of jumping to the address screen (only after about five minutes without the Spark the address screen comes back, "Adresse ändern" works any time). A notification, sharing or the assistant button no longer reload the open page: the page only jumps to the place.
- **Last state at once** (from 1.4.1, V01.0.748, function "Apps keep the last state"): nothing stays blank on the first load: after a second "Verbinde mit dem Spark …" (connecting), after 8 seconds "Das dauert länger als sonst …" (takes longer), when the Spark cannot be reached "Noch einmal" (try again) and "Adresse ändern". Then the page in the app shows the conversations (the 20 newest with 50 messages each), the chat list and the own settings of last time at once, above the conversation with "As of 16:05 · refreshing …" until the Spark has answered. When the app comes to the front it fetches settings and chats once in the background (at most every 5 minutes). When the start or a list needs more than 2 seconds, Status → Logs (area Apps) shows `app: langsam <page> <ms> ms android`.
- **Calls by the assistant** (from 1.4.2, V01.0.803, function "Calls by the assistant"): saying "Call Sabine" to the app's assistant and then "Yes" opens the app with "Sabine anrufen? · Anrufen". "Call Mum by phone" looks Mum up in the profile's contacts on the Spark (Me → Contacts) and after the yes opens the phone app with the number; only the tap on the green button dials. On the page in the app the Spark call starts right after the yes.
- **Save the battery** (from 1.3.3, V01.0.668): in the background the app pauses its page (no polling, no open connections of the page); coming back it catches up. During a call the page stays awake. "Mitteilungen sofort" keeps running independently.
- **Camera for video calls** (1.3.1 and later, V01.0.556): the app asks for the camera at the first video call in Chats, for the microphone at the first call; only for the own Spark's page. Without the camera the call goes on with sound.
- **Update in the app** (1.3.0 and later, V01.0.533): admin: Features → Android app → "Android: update in the app" (off).
  Once released the app shows a strip "New app version … · Update now" at the top (✕ hides it until the next
  version); the note "New Spark app" and the button under Me → Android app start the update too. The app asks only
  its own Spark (`/api/profile/android`: version, size, SHA-256), never GitHub, and loads the APK with its sign-in from
  `GET /api/android/apk` into its cache. Before installing it checks itself: size and SHA-256 as reported, package
  name `io.github.db9979.spark`, a higher version code, the same signing key as the installed app. Then Android's
  package installer takes over; it checks the signature once more and asks "Update". The first time Android asks
  once whether the Spark app may install apps ("Allow from this source"). If anything does not match, the app
  deletes the file and installs nothing. It cannot work without a tap: only store apps or apps of a company device
  management may install silently. The update to 1.3.0 itself still goes once through the download link.
- **Versions of the phones:** Status → Device updates shows for the Android app which profile runs which app version
  and how many phones are up to date (from the "SparkAndroid/x.y.z" tag of their requests, in memory only, 14 days);
  Live counts "Android current/all". A new version of a profile shows as a line `android: app version … -> …` in the log.

## Setup

1. **Signing key (once, admin):** on the Spark (or a Mac) run `bash /opt/speech-spark/src/tools/android-schluessel.sh`
   in a terminal (no sudo, needs only openssl). It creates `~/spark-android.p12` and `~/spark-android.pass` and shows
   two values. In the GitHub repo under Settings → Secrets and variables → Actions → "New repository secret" add
   both: `ANDROID_KEYSTORE_PASSWORD` and `ANDROID_KEYSTORE` (the long line). Keep both files safe: later versions
   only install over the old one with the same key.
2. **Build the app:** Actions → "Android app" → Run workflow. It appears as release `android-v1.0.0` with
   `spark.apk`, `spark.apk.sha256` and `android.json`.
3. **Spark:** Features → Android app on, save, "Fetch the app now" (otherwise it fetches once a day).
   It checks size and SHA-256 and keeps it under `STATE/android`.
4. **Profile:** Me → Android app → "Get a download link", scan the QR code with the
   Android phone's camera, install the APK (the phone asks once whether the browser may install apps). The link
   is valid for 30 minutes.
5. **In the app:** enter the Spark's address (https with a real certificate, e.g. the reverse proxy), sign in with
   name and PIN like in the browser, allow notifications and the microphone. For reliable notes turn off battery
   optimisation for Spark.

## Security

- Admin switch `chat.android`, off. Once released it works for every profile; only the admin blocks single profiles (People and devices → Blocked functions). Never guests.
- The app has no key of its own: it uses its page's login (cookie). Signing out in the page ends it.
- The app only loads pages of its own Spark (same address and port), everything else opens in the browser; https
  only, system certificates. Microphone only for the own Spark page.
- `#ask=` only puts shared text into the text field, nothing is ever sent by itself; both jumps only work in the app.
- The APK only comes from GitHub's download addresses with matching size and SHA-256. The download link carries a
  one-time token (only its hash in memory, 30 minutes, at most 5 downloads); without a valid link 404.
- Update in the app: its own admin switch `chat.android_update` (off), blockable per profile; `GET /api/android/apk`
  only with the profile's browser login (no device key), rate limit, hands out only the APK the Spark checked when
  fetching it. The app follows no redirect and trusts only its own address; Android installs over the installed app
  only when the signing key matches. The page hands the app nothing: the button is the fixed link `sparkapp:update`
  the app catches. Log: `android: app update … sent to …` or `… refused … reason …`.
- Notes stay in memory only (24 hours, at most 30 per profile) and only go to the profile's own login.
- Spark as assistant: its own admin switch `chat.android_assist` (off), blockable per profile, never guests. The Spark
  checks every question of the sheet itself (device "android"); without the release it answers 403 and logs
  `android: assistant refused for … reason …`. The app learns the release only from `/api/profile/android` and shows
  or hides widget, tile and shortcuts by it. The microphone runs only while the sheet is open and the question lasts
  (at most 30 seconds); on the lock screen only after unlocking. The widget shows numbers only, never titles or names
  of appointments and messages. Waiting questions stay in the app only (at most 10, one day).
- Shared files go through the Spark's normal ways (`/api/chat/image`, `/api/profile/docs`) with their rights, size and
  rate limits; the app reads only content addresses (`content://`), no file paths.
- Last state: admin switch `chat.app_cache` (on in the basic set), blockable per profile. The page keeps only inside
  the app (mark "SparkAndroid/") and only while `/api/profile/settings` says "app_keep"; when the Spark says no it
  deletes everything. The copy lies in the app's page storage (in the app's encrypted storage, apart per profile), never
  keys, codes, admin pages or files. Signing out and another profile delete it. A browser keeps nothing this way (that
  is "Read history offline" with a trusted browser).
- Fingerprint for admins: its own admin switch `chat.android_lock` (off); it applies only to a login with an admin
  role. A phone without any screen lock has nothing to check: the app says so and opens.

## New version

Raise `name` and `code` in `android/version.properties` and push to main: the action builds, signs and publishes
`android-v<name>`; the Spark fetches it and the apps say so.
