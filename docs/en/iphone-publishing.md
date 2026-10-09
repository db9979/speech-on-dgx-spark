# Publishing the iPhone app

Three ways; all need the Apple Developer Program (99 €/year).

| Way | For whom | Apple review |
|---|---|---|
| **TestFlight internal** (recommended) | you and up to 100 people of your developer team | none |
| **TestFlight external** | up to 10,000 people by link | short beta review |
| **App Store** (public or unlisted) | everybody | full review |

## 1. Once: create the app at Apple

1. In Xcode: project **Spark** → **Build Settings** → `APP_BUNDLE_ID` is your own bundle ID; both targets (**Spark**, **SparkNotify**) have your team under **Signing & Capabilities**.
2. appstoreconnect.apple.com → **Apps → + → New App**: iOS, a name that is free in the store, your bundle ID, any SKU.

## 2. Upload every new version

1. `git pull` in the repo.
2. Target **Spark** → **General**: raise **Version** for user-visible changes; **Build** must grow with every upload.
3. Destination **Any iOS Device (arm64)**, then **Product → Archive**.
4. **Distribute App → App Store Connect → Distribute**.
5. After 5–30 minutes the build shows under **TestFlight**. The encryption question is answered by the app itself (`ITSAppUsesNonExemptEncryption = NO`, https only).

Then set the panel's **Push to the iPhone app** to **"Production"**: TestFlight and App Store builds use Apple's production push.

## 3. TestFlight

App Store Connect → **Users and Access**: invite family members; app → **TestFlight → Internal Testing → +**: add them and the build. Each installs **TestFlight** from the App Store and accepts. A build runs 90 days.

## 4. App Store

Also needed: screenshots (6.9" or 6.5"), description, support URL, a privacy policy URL, App Privacy "Data Not Collected" (everything goes to the user's own Spark), age rating, and review notes: reviewers need a Spark, so offer a test profile and a short video. Unlisted distribution can be requested if the app should not show up in search. Review usually takes 1–3 days.

## CarPlay

Builds with CarPlay can only be uploaded once Apple granted the entitlement and it is in `ios/Spark.entitlements` (see [iphone-app.md](iphone-app.md#carplay)).
