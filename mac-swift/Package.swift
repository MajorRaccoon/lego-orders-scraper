// swift-tools-version:5.10
// Native macOS version of the LEGO order scraper.
//   LegoCore             - parsing, merge/dedupe, JSON/CSV/HTML output, scraping steps (no UI)
//   LegoOrderScraperApp  - the SwiftUI app (WebKit browser + options + log)
//   lego-parity          - tiny CLI used by lego-tests to compare Swift output with Python's
import PackageDescription

let package = Package(
    name: "LegoOrderScraper",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "LegoOrderScraperApp", targets: ["LegoOrderScraperApp"]),
        .executable(name: "lego-parity", targets: ["lego-parity"]),
    ],
    targets: [
        .target(name: "LegoCore"),
        .executableTarget(name: "LegoOrderScraperApp", dependencies: ["LegoCore"]),
        .executableTarget(name: "lego-parity", dependencies: ["LegoCore"]),
        .testTarget(name: "LegoCoreTests", dependencies: ["LegoCore"]),
    ]
)
