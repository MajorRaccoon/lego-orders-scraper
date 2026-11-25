# LEGO Orders for iPhone and iPad

The LEGO.com order scraper as an iPhone/iPad app. It uses the same scraping, parsing and report code as the Mac app (the `LegoCore` and `LegoWebKit` libraries in [`../mac-swift`](../mac-swift)).

- **Scrape tab:** tap **Start**. LEGO.com opens in the app, and you log in there the first time. Options (since date, max orders, tracking numbers, timings) are behind the gear button.
- **Report tab:** the same HTML report as on the Mac, with a share button for the report, CSV and JSON.
- **Files:** saved in the **Files** app under **On My iPhone** (or **iPad**) **→ LEGO Orders**.
- **Keep the app open while it runs.** iOS pauses apps in the background, so the screen stays on during a run. If you leave the app, tap **Start** again later to pick up where it stopped.

The Apple Mail reader stays Mac-only, because iOS apps can't read Mail's mailbox.

## Install it with TestFlight

GitHub builds the app and uploads it to TestFlight. You install and update it from Apple's **TestFlight** app. It needs a paid **Apple Developer Program** membership. One-time setup:

1. **Register the bundle ID.** At [developer.apple.com](https://developer.apple.com/account) → **Certificates, IDs & Profiles → Identifiers → +**, choose **App IDs → App**. Enter a description and the explicit bundle ID `io.github.majorraccoon.legoorders`, or your own; see step 5.
2. **Create the app in App Store Connect.** At [appstoreconnect.apple.com](https://appstoreconnect.apple.com) → **Apps → + → New App**:
   - Platform: **iOS**.
   - Name: any name not already used on the App Store, for example "Brick Order History". It's only shown in TestFlight.
   - Bundle ID: the one from step 1.
   - SKU: anything, for example `lego-orders`.
3. **Create an API key.** In App Store Connect → **Users and Access → Integrations → App Store Connect API → Team Keys → +**:
   - Give it **Admin** access. Xcode needs that to create the distribution certificate.
   - Download the `.p8` file. You can only download it once.
   - Note its **Key ID** and the **Issuer ID** shown above the list.
4. **Find your Team ID.** At [developer.apple.com](https://developer.apple.com/account) → **Membership details**.
5. **Add the GitHub secrets.** In the repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `APP_STORE_CONNECT_KEY_ID`: the Key ID.
   - `APP_STORE_CONNECT_ISSUER_ID`: the Issuer ID.
   - `APP_STORE_CONNECT_KEY_P8`: open the `.p8` file in TextEdit and paste all of it, including the `-----BEGIN PRIVATE KEY-----` and `-----END PRIVATE KEY-----` lines.
   - `APPLE_TEAM_ID`: the Team ID.
   - If you used a different bundle ID, add it under the **Variables** tab as `IOS_BUNDLE_ID`.
6. **Upload a build.** Go to **Actions → iOS app → Run workflow** and tick **Upload to TestFlight**. Every **Release** run uploads one too.
7. **Install it.** In App Store Connect → your app → **TestFlight → Internal Testing**, create a group and add yourself. Then install **TestFlight** from the App Store on your iPhone/iPad, accept the invitation, and install **LEGO Orders**. Internal testing needs no App Review. Each build works for 90 days, and new builds show up in TestFlight as updates.

None of these keys or IDs go into the repository. They live only in GitHub's encrypted secrets, and the workflow deletes the key file when it's done.

## Build it yourself (Xcode)

```bash
brew install xcodegen
cd ios
xcodegen generate
open LegoOrders.xcodeproj
```

Choose your team under **Signing & Capabilities**, pick your iPhone/iPad, and press **Run**.

## For developers

```
ios/
  project.yml            XcodeGen project (LegoOrders.xcodeproj is generated from it, not committed)
  Sources/
    LegoOrdersApp.swift  the app: Scrape and Report tabs
    OrdersModel.swift    options, the running scrape, log, files (port of the Mac AppModel)
    ScrapeView.swift     Start/Stop, the LEGO.com browser, progress log, Options sheet
    ReportView.swift     the HTML report, share button
  Assets.xcassets        app icon (the Mac icon, flattened: App Store icons can't be transparent)
```

The **iOS app** GitHub workflow builds it for the iOS Simulator on every change to `ios/` or the shared code, and uploads to TestFlight when asked.
