// swift-tools-version:5.10
// Native macOS versions of the LEGO order scraper.
//   LegoCore             - parsing, merge/dedupe, JSON/CSV/HTML output, scraping steps (no UI)
//   LegoOrderScraperApp  - the SwiftUI app that reads LEGO.com (WebKit browser + options + log)
//   lego-parity          - tiny CLI used by lego-tests to compare Swift output with Python's
//   LegoMail             - reads LEGO order emails from Apple Mail (.emlx, .eml, .mbox) (no UI)
//   LegoMailOrdersApp    - the SwiftUI app that reads Apple Mail ("LEGO Mail Orders")
//   lego-mail            - command-line version of LegoMailOrdersApp
import PackageDescription

let package = Package(
    name: "LegoOrderScraper",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "LegoOrderScraperApp", targets: ["LegoOrderScraperApp"]),
        .executable(name: "lego-parity", targets: ["lego-parity"]),
        .executable(name: "LegoMailOrdersApp", targets: ["LegoMailOrdersApp"]),
        .executable(name: "lego-mail", targets: ["lego-mail"]),
    ],
    targets: [
        .target(name: "LegoCore"),
        .executableTarget(name: "LegoOrderScraperApp", dependencies: ["LegoCore"]),
        .executableTarget(name: "lego-parity", dependencies: ["LegoCore"]),
        .testTarget(name: "LegoCoreTests", dependencies: ["LegoCore"]),
        .target(name: "LegoMail", dependencies: ["LegoCore"]),
        .executableTarget(name: "LegoMailOrdersApp", dependencies: ["LegoCore", "LegoMail"]),
        .executableTarget(name: "lego-mail", dependencies: ["LegoCore", "LegoMail"]),
        .testTarget(name: "LegoMailTests", dependencies: ["LegoMail", "LegoCore"]),
    ]
)
