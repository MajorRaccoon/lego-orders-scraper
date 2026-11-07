import AppKit
import SwiftUI

final class MailAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Needed when run straight from `swift run` (outside the .app bundle); harmless inside it.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main
struct LegoMailOrdersApp: App {
    @NSApplicationDelegateAdaptor(MailAppDelegate.self) var appDelegate
    @StateObject private var model = MailAppModel()

    var body: some Scene {
        Window("LEGO Mail Orders", id: "main") {
            MailContentView().environmentObject(model)
        }
        .defaultSize(width: 980, height: 700)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandGroup(after: .appInfo) {
                Button("Show Files in Finder") { model.openDataFolder() }
            }
        }
    }
}
