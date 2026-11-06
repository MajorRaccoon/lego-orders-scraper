import AppKit
import LegoCore
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Needed when run straight from `swift run` (outside the .app bundle); harmless inside it.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

/// Developer self-check: `LEGO_SELFCHECK=/some/folder open -n "LEGO Order Scraper.app"` (or run the
/// binary with that variable set) waits for the page to load, saves window.png, page.png and
/// state.txt (URL, signed-in check, page text length) into that folder, then quits.
@MainActor
enum SelfCheck {
    static func runIfRequested(_ model: AppModel) {
        guard let dir = ProcessInfo.processInfo.environment["LEGO_SELFCHECK"], !dir.isEmpty else { return }
        let out = URL(fileURLWithPath: dir, isDirectory: true)
        Task { @MainActor in
            try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            var gotoResult = "ok"
            // LEGO_SELFCHECK_URL: optional page to load instead of My Orders (e.g. one order's detail page).
            let target = ProcessInfo.processInfo.environment["LEGO_SELFCHECK_URL"] ?? ordersURL
            do { try await model.page.goto(target, timeout: 30) } catch { gotoResult = "\(error)" }
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            await model.page.dismissInterstitials()
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            if let window = NSApp.windows.first(where: { $0.isVisible }), let view = window.contentView,
               let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
                view.cacheDisplay(in: view.bounds, to: rep)
                try? rep.representation(using: .png, properties: [:])?.write(to: out.appendingPathComponent("window.png"))
            }
            if let image = try? await model.page.webView.takeSnapshot(configuration: nil),
               let tiff = image.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff) {
                try? rep.representation(using: .png, properties: [:])?.write(to: out.appendingPathComponent("page.png"))
            }
            let text = (try? await model.page.mainText()) ?? "<error>"
            let state = """
            goto: \(gotoResult)
            url: \(model.page.currentURL)
            title: \((try? await model.page.js("return document.title;")) as? String ?? "")
            signedOut: \(await model.page.isSignedOut())
            loadMoreVisible: \(await model.page.isLoadMoreVisible())
            mainTextLength: \(text.count)
            userAgent: \((try? await model.page.js("return navigator.userAgent;")) as? String ?? "")
            """
            try? state.write(to: out.appendingPathComponent("state.txt"), atomically: true, encoding: .utf8)
            try? text.write(to: out.appendingPathComponent("main-text.txt"), atomically: true, encoding: .utf8)
            let html = (try? await model.page.js("var m = document.querySelector('main') || document.body; return m ? m.outerHTML : '';")) as? String ?? ""
            try? html.write(to: out.appendingPathComponent("main.html"), atomically: true, encoding: .utf8)
            NSApp.terminate(nil)
        }
    }
}

@main
struct LegoOrderScraperApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        Window("LEGO Order Scraper", id: "main") {
            ContentView().environmentObject(model)
                .onAppear { SelfCheck.runIfRequested(model) }
        }
        .defaultSize(width: 1180, height: 800)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandGroup(after: .appInfo) {
                Button("Show Files in Finder") { model.openDataFolder() }
            }
        }
    }
}
