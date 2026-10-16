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
- **Assistant button:** Settings → Apps → Default apps → Digital assistant → "Spark"; holding the button opens the
  app and it listens.
- **Share to Spark:** share text in another app → Spark. The text is put into the text field, you send it yourself.
- **Emergency stop tile** (1.1.0 and later): edit quick settings → add "Notaus". Admins choose "Ganzer Spark" (stage 2) or "Mein Notaus", everyone else "Mein Notaus", always behind a question; lifting only in the browser (see [Security and operation](security-and-operation.md)).
- **New version:** the app shows a notification when the Spark has a newer APK.
- **Calm during a Spark update** (from 1.3.2, V01.0.570): when the Spark restarts (an update), the app shows "Spark startet neu … Die Seite kommt gleich wieder." (Spark restarting … the page is back in a moment) and tries again by itself instead of jumping to the address screen (only after about five minutes without the Spark the address screen comes back, "Adresse ändern" works any time). A notification, sharing or the assistant button no longer reload the open page: the page only jumps to the place.
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

- Admin switch `chat.android`, off. Once released it works for every profile; only the admin blocks single profiles (Features → Who may do what). Never guests.
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

## New version

Raise `name` and `code` in `android/version.properties` and push to main: the action builds, signs and publishes
`android-v<name>`; the Spark fetches it and the apps say so.
