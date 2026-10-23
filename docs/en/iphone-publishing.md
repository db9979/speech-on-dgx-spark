# Publishing the iPhone app

Three ways, from the simplest to the most work. All need the Apple Developer Program (99 €/year).

| Way | For whom | Apple review |
|---|---|---|
| **TestFlight internal** (recommended) | you and up to 100 people of your developer team | none |
| **TestFlight external** | up to 10,000 people by link | short beta review |
| **App Store** (public or unlisted) | everybody | full review |

## 1. Once: create the app at Apple

1. Check in Xcode: project **Spark** → **Build Settings** → `APP_BUNDLE_ID` is your own bundle ID (e.g. `io.github.db9979.speechspark.dominik`). Both targets (**Spark** and **SparkNotify**) have your team selected under **Signing & Capabilities**.
2. appstoreconnect.apple.com → **Apps → + → New App**: platform iOS, a name (it must be free in the App Store; "Spark" is surely taken, e.g. "Spark voice assistant"), primary language, the bundle ID from the list, any SKU (e.g. `speechspark`).

## 2. Upload every new version

1. `git pull` in the repo.
2. Xcode → target **Spark** → **General**: raise **Version** (e.g. 1.1) when something changes for users. The **Build** number counts up by itself: building sets it to the number of commits in the repo, the same for the app and all its extensions, so it is larger after every `git pull`. The app shows both small at the bottom, e.g. "1.0 (412)".
3. Choose **Any iOS Device (arm64)** as the destination at the top.
4. **Product → Archive**. After a few minutes the Organizer opens.
5. **Distribute App → App Store Connect → Distribute**. Xcode signs and uploads.
6. After 5–30 minutes the build shows in App Store Connect under **TestFlight**. The app answers the encryption question itself (https only, `ITSAppUsesNonExemptEncryption = NO`).

Then set the kind to **"Production"** in the panel under **Features → Push to the iPhone app**: TestFlight and App Store builds use Apple's production push. Installed straight from Xcode it is "Development" again.

### Upload with the GitHub button "TestFlight"

Instead of Archive and Distribute on the Mac this also works on GitHub. The button builds the app, lets Apple sign it and uploads it to TestFlight. It starts only for a commit whose tests passed. The build number counts up by itself.

Once:
1. App Store Connect → **Users and Access → Integrations → App Store Connect API → Team Keys**: create a key with role **Admin**. Only Admin may fetch certificates for signing. If you already have an App Manager key for the texts, replace it with this one.
2. GitHub → **Settings → Secrets and variables → Actions**: `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY` (the whole content of the `.p8` file) and also `ASC_TEAM_ID` (developer.apple.com → Membership → Team ID).

Then: GitHub → **Actions → TestFlight → Run workflow**, enter the bundle ID, **Run**. After 15 to 30 minutes the build is in App Store Connect under TestFlight.

**Automatic:** when a commit on main changes something under `ios/`, TestFlight starts by itself as soon as "iPhone app" and "Tests" passed. At most one upload per hour. It waits up to 100 minutes for "Tests", because Tests on main run one after another (V01.0.965). If a newer iOS commit comes in the waiting time, only that one is uploaded. If a newer push cancelled the tests of the iOS commit, the newest main commit with passed tests that contains the iOS commit goes up (V01.0.321). The certificates a run makes for itself are revoked again at its end, otherwise Apple's limit is reached after some dozen runs ("reached the maximum number of certificates", V01.0.334). If that message still shows in a run, revoke the old entries under developer.apple.com → Certificates. Turn it off: GitHub → Settings → Secrets and variables → Actions → Variables → `TESTFLIGHT_AUTO` = `off`. A bundle ID other than `io.github.db9979.speechspark` goes into the variable `APP_BUNDLE_ID`. To start again always use **Run workflow**, not "Re-run", because a re-run builds the old commit.

If it does not work the first time, send the red line from the run.

## 3. TestFlight (recommended for you and the family)

1. App Store Connect → **Users and Access**: invite family members with their Apple ID (a role like "Marketing" is enough).
2. App → **TestFlight → Internal Testing → +** → create a group "Family", add the people, assign the build.
3. Everybody installs the **TestFlight** app from the App Store on the iPhone and accepts the invitation. New builds arrive there by themselves.

A TestFlight build runs 90 days; then simply upload a new one.

## 4. App Store (only when strangers should load the app)

In addition to steps 1–2, in App Store Connect under the app:

- **Screenshots**: at least for 6.9" (iPhone 16 Pro Max) or 6.5", from the simulator with ⌘S.
- **Description, keywords, support URL** (e.g. the GitHub page).
- **Privacy policy (URL)**: ready in [app-privacy.md](app-privacy.md), German in [app-datenschutz.md](../de/app-datenschutz.md). Enter the GitHub link of the file as the URL.
- **App Privacy**: "Data Not Collected" (everything goes to the user's own Spark, not to you). Notifications through Apple carry only a fixed sentence.
- **Age rating**: fill in the questionnaire (no content of the categories → 4+; because of the free answers of a language model rather 12+).
- **Notes for the review**: Apple's reviewers need a Spark. Create a test profile of its own such as "App Review" and make a review access under People and devices → Review access for the iPhone app (valid 14 days). In the sign-in details put the address of your reverse proxy as the user name and the review code as the password, and add: "On the first screen tap 'Connect with a review code', type address and code. Without access, 'Look without a Spark' shows a demo." A short video of the app helps as well.
- **Availability**: request "Unlisted" (by link only) at Apple when the app should not show up in the App Store search.

### Fill in the texts automatically

Name, subtitle, promotional text, description, keywords, URLs and categories (German and English) are in `ios/fastlane/metadata`. A button on GitHub writes them into App Store Connect. It uploads no build and no pictures and submits nothing for review.

1. The app must already exist in App Store Connect (step 1), with German as the primary language.
2. App Store Connect → **Users and Access → Integrations → App Store Connect API → Team Keys → +**: name "GitHub texts", role **App Manager**. Download the `.p8` file (works only once), note the **Key ID** and the **Issuer ID**.
3. GitHub → repo → **Settings → Secrets and variables → Actions → New repository secret**, three times: `ASC_KEY_ID` (Key ID), `ASC_ISSUER_ID` (Issuer ID), `ASC_KEY` (the whole content of the `.p8` file).
4. GitHub → **Actions → App Store texts → Run workflow**: enter bundle ID, version (`1.0`) and copyright (e.g. `2026 First Last`), **Run**.
5. After about 2 minutes the texts are in App Store Connect. You can revoke the key there afterwards.

The screenshots (German and English, 6.9" and 6.3") are made by the workflow **App Store screenshots** in the iPhone simulator with example content. It puts them on the branch `app-store-screenshots`. With the box "upload screenshots too" ticked, **App Store texts** enters them as well. The demo mode (`-SparkDemo`) exists only in the test build, not in the app from the store.

Left by hand: App Privacy, age rating, notes for the review and price. The answers for them are in the project's papers ("App Store Connect: Angaben für Spark").

Then **Submit for Review**. The review usually takes 1–3 days. A frequent rejection: the reviewer gets no further because they have no Spark (guideline 2.1), hence the video and the test access.

## CarPlay

Builds with CarPlay can only be uploaded once Apple granted the CarPlay entitlement and it is entered in `ios/Spark.entitlements` (see [iphone-app.md](iphone-app.md#carplay)). Until then upload builds without that line; everything else works.
