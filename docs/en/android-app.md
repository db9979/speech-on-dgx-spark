# Android app "Spark" (APK, no store)

The app is a thin shell around the Spark's page: it shows the Spark as the phone browser does (like the iPhone app,
since V01.0.296) and adds only what a page cannot do:

- **Notes while the app is closed:** the app asks the Spark itself every 15 minutes (`/api/android/notes`), no
  Google service. Reminders, the morning briefing and notes go there when the app is the device used last or no
  other way (iPhone app) is set up.
- **Assistant button:** Settings → Apps → Default apps → Digital assistant → "Spark"; holding the button opens the
  app and it listens.
- **Share to Spark:** share text in another app → Spark. The text is put into the text field, you send it yourself.
- **New version:** the app shows a notification when the Spark has a newer APK.

## Setup

1. **Signing key (once, admin):** on a computer with Java:
   `keytool -genkeypair -v -keystore spark.jks -alias spark -keyalg RSA -keysize 4096 -validity 10000`
   (one password for key and file). In the GitHub repo under Settings → Secrets and variables → Actions add
   `ANDROID_KEYSTORE` = output of `base64 -w0 spark.jks` and `ANDROID_KEYSTORE_PASSWORD` = the password. Keep
   `spark.jks` safe: later versions only install over the old one with the same key.
2. **Build the app:** Actions → "Android app" → Run workflow. It appears as release `android-v1.0.0` with
   `spark.apk`, `spark.apk.sha256` and `android.json`.
3. **Spark:** Settings → Features → Android app on, save, "Fetch the app now" (otherwise it fetches once a day).
   It checks size and SHA-256 and keeps it under `STATE/android`.
4. **Profile:** Me → Android app → "Android app for me" on, "Get a download link", scan the QR code with the
   Android phone's camera, install the APK (the phone asks once whether the browser may install apps). The link
   is valid for 30 minutes.
5. **In the app:** enter the Spark's address (https with a real certificate, e.g. the reverse proxy), sign in with
   name and PIN like in the browser, allow notifications and the microphone. For reliable notes turn off battery
   optimisation for Spark.

## Security

- Admin switch `chat.android` and profile switch `android_on`, both off; never guests.
- The app has no key of its own: it uses its page's login (cookie). Signing out in the page ends it.
- The app only loads pages of its own Spark (same address and port), everything else opens in the browser; https
  only, system certificates. Microphone only for the own Spark page.
- `#ask=` only puts shared text into the text field, nothing is ever sent by itself; both jumps only work in the app.
- The APK only comes from GitHub's download addresses with matching size and SHA-256. The download link carries a
  one-time token (only its hash in memory, 30 minutes, at most 5 downloads); without a valid link 404.
- Notes stay in memory only (24 hours, at most 30 per profile) and only go to the profile's own login.

## New version

Raise `name` and `code` in `android/version.properties` and push to main: the action builds, signs and publishes
`android-v<name>`; the Spark fetches it and the apps say so.
