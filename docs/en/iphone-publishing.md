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

Also needed: screenshots (6.9" or 6.5"), description, support URL, a privacy policy URL (ready: [app-privacy.md](app-privacy.md), German [app-datenschutz.md](../de/app-datenschutz.md)), App Privacy "Data Not Collected" (everything goes to the user's own Spark), age rating, and review notes: reviewers need a Spark, so offer a test profile and a short video. Unlisted distribution can be requested if the app should not show up in search. Review usually takes 1–3 days.

### Fill in the texts automatically

Name, subtitle, promotional text, description, keywords, URLs and categories (German and English) are in `ios/fastlane/metadata`. The GitHub workflow **App Store texts** (Actions → Run workflow, by hand only) writes them into App Store Connect. It uploads no build or screenshots and never submits for review. It needs the app already created in App Store Connect and three repository secrets from an App Store Connect API team key with role App Manager: `ASC_KEY_ID`, `ASC_ISSUER_ID` and `ASC_KEY` (the whole `.p8` file). Screenshots (German and English, 6.9" and 6.3") come from the workflow **App Store screenshots**, which runs the app in the simulator with example content (`-SparkDemo`, Debug builds only) and stores them on the branch `app-store-screenshots`; the texts workflow uploads them too when its "screenshots" box is ticked. App privacy, age rating, review notes and price stay manual.

## CarPlay

Builds with CarPlay can only be uploaded once Apple granted the entitlement and it is in `ios/Spark.entitlements` (see [iphone-app.md](iphone-app.md#carplay)).
