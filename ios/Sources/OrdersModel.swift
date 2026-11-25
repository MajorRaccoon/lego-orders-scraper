import LegoCore
import LegoWebKit
import SwiftUI
import UIKit

/// App state for iPhone and iPad: options, the running scrape, the log and the result files.
/// The same steps as the Mac app (LegoCore's Scraper driving the built-in WebKit browser).
@MainActor
final class OrdersModel: ObservableObject {
    enum Phase { case idle, running, waitingForLogin, stopping }

    struct LogLine: Identifiable { let id: Int; let text: String }

    @Published var phase: Phase = .idle
    @Published var log: [LogLine] = []
    @Published var status = "Ready. Tap Start to fetch your LEGO orders."
    @Published var reportExists = false
    /// Goes up every time the files are rewritten, so the Report tab reloads.
    @Published var reportVersion = 0

    // Options (saved between launches, except "Refetch everything", which is off at every launch)
    @Published var useSinceDate: Bool { didSet { defaults.set(useSinceDate, forKey: "useSinceDate") } }
    @Published var sinceDate: Date { didSet { defaults.set(sinceDate, forKey: "sinceDate") } }
    @Published var maxOrdersText: String { didSet { defaults.set(maxOrdersText, forKey: "maxOrders") } }
    @Published var fresh = false
    @Published var leaveOutTracking: Bool { didSet { defaults.set(leaveOutTracking, forKey: "leaveOutTracking") } }
    @Published var delay: Double { didSet { defaults.set(delay, forKey: "delay") } }
    @Published var loadMoreDelay: Double { didSet { defaults.set(loadMoreDelay, forKey: "loadMoreDelay") } }
    @Published var loadMoreFinalWait: Double { didSet { defaults.set(loadMoreFinalWait, forKey: "loadMoreFinalWait") } }
    @Published var savePageText: Bool { didSet { defaults.set(savePageText, forKey: "savePageText") } }

    let page = WebKitPage()
    private let defaults = UserDefaults.standard
    private var task: Task<Void, Never>?
    private var stopFlag = StopFlag()
    private var loginConfirmed = false
    private var lineCounter = 0
    private var backgroundTask: UIBackgroundTaskIdentifier = .invalid

    /// The app's Documents folder: shown in the Files app as On My iPhone/iPad > LEGO Orders.
    let dataDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    var jsonURL: URL { dataDir.appendingPathComponent("lego_orders.json") }
    var csvURL: URL { dataDir.appendingPathComponent("lego_orders.csv") }
    var htmlURL: URL { dataDir.appendingPathComponent("lego_orders.html") }
    var logFile: URL { dataDir.appendingPathComponent("LEGO Order Scraper.log") }
    /// The result files that exist, for sharing.
    var resultFiles: [URL] { [htmlURL, csvURL, jsonURL].filter { FileManager.default.fileExists(atPath: $0.path) } }

    init() {
        let d = UserDefaults.standard
        useSinceDate = d.object(forKey: "useSinceDate") as? Bool ?? true
        sinceDate = d.object(forKey: "sinceDate") as? Date ?? defaultSinceDate.toDate()
        maxOrdersText = d.string(forKey: "maxOrders") ?? ""
        leaveOutTracking = d.object(forKey: "leaveOutTracking") as? Bool ?? false
        delay = d.object(forKey: "delay") as? Double ?? 1.5
        loadMoreDelay = d.object(forKey: "loadMoreDelay") as? Double ?? 1.2
        loadMoreFinalWait = d.object(forKey: "loadMoreFinalWait") as? Double ?? 5.0
        savePageText = d.object(forKey: "savePageText") as? Bool ?? false
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        refreshFiles()
        page.webView.load(URLRequest(url: URL(string: ordersURL)!))
    }

    var isBusy: Bool { phase != .idle }

    // MARK: Log

    func append(_ message: String) {
        for line in message.components(separatedBy: "\n") {
            lineCounter += 1
            log.append(LogLine(id: lineCounter, text: line))
        }
        if log.count > 5000 { log.removeFirst(log.count - 5000) }
        writeToLogFile(message + "\n")
    }

    private func writeToLogFile(_ s: String) {
        if let h = try? FileHandle(forWritingTo: logFile) {
            h.seekToEndOfFile(); h.write(Data(s.utf8)); try? h.close()
        } else {
            try? Data(s.utf8).write(to: logFile)
        }
    }

    var logText: String { log.map(\.text).joined(separator: "\n") }

    // MARK: Run

    func start() {
        guard phase == .idle else { return }
        let trimmed = maxOrdersText.trimmingCharacters(in: .whitespaces)
        var maxOrders: Int?
        if !trimmed.isEmpty {
            guard let n = Int(trimmed), n > 0 else {
                status = "\"Max orders\" must be a whole number above 0, or blank for all orders."
                return
            }
            maxOrders = n
        }
        var o = ScrapeOptions(jsonURL: jsonURL, csvURL: csvURL, htmlURL: htmlURL)
        o.maxOrders = maxOrders
        o.sinceDate = useSinceDate ? SimpleDate(sinceDate) : nil
        o.fresh = fresh
        o.includeTracking = !leaveOutTracking
        o.delay = max(0, delay)
        o.loadMoreDelay = max(0, loadMoreDelay)
        o.loadMoreFinalWait = max(0, loadMoreFinalWait)

        let stamp = ISO8601DateFormatter().string(from: Date())
        page.debugDir = savePageText ? dataDir.appendingPathComponent("page-text/\(stamp.replacingOccurrences(of: ":", with: "-"))") : nil
        stopFlag = StopFlag()
        log = []
        phase = .running
        status = "Running... keep the app open until it's done."
        writeToLogFile("\n===== \(stamp) =====\n")
        append("LEGO Orders for iPhone and iPad v\(legoSwiftVersion)")
        append(o.sinceDate.map { "Since date: \($0) (turn off \"Only orders since\" in Options for every order)" }
               ?? "Since date: none (fetching all orders)")

        // iOS pauses apps in the background and dims the screen when idle: keep the screen on
        // while fetching, and ask for a little extra time if the app is sent to the background.
        UIApplication.shared.isIdleTimerDisabled = true
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "Fetching LEGO orders") { [weak self] in
            Task { @MainActor in self?.endBackgroundTime() }
        }

        let scraper = Scraper(page: page, stop: stopFlag, log: { [weak self] in self?.append($0) },
                              waitForLogin: { [weak self] in try await self?.waitForUserLogin() })
        task = Task { [weak self] in
            do {
                let orders = try await scraper.run(o)
                let withItems = orders.filter { !$0.items.isEmpty }.count
                self?.status = self?.stopFlag.requested == true
                    ? "Stopped. Progress is saved; tap Start to continue."
                    : "Done: \(orders.count) order(s), \(withItems) with item detail. See the Report tab."
            } catch is CancellationError {
                self?.status = "Stopped. Progress is saved; tap Start to continue."
            } catch {
                self?.append("\nERROR: \(error)")
                self?.status = "Something went wrong: \(error)"
            }
            UIApplication.shared.isIdleTimerDisabled = false
            self?.endBackgroundTime()
            self?.phase = .idle
            self?.task = nil
            self?.fresh = false
            self?.refreshFiles()
        }
    }

    /// Called by the scraper when LEGO.com shows us signed out. Returns once the user has
    /// tapped "I've logged in, continue", or we can see their order list.
    private func waitForUserLogin() async throws {
        phase = .waitingForLogin
        status = "Log in to LEGO.com in the browser below."
        loginConfirmed = false
        defer { if phase == .waitingForLogin { phase = .running; status = "Running... keep the app open until it's done." } }
        while !loginConfirmed {
            try await Task.sleep(nanoseconds: 1_000_000_000)
            if page.currentURL.contains("/member/orders"), await !page.isSignedOut(),
               let text = try? await page.mainText(), text.contains("Order Number:") {
                append("Signed in -- continuing.")
                return
            }
        }
    }

    func confirmLoggedIn() { loginConfirmed = true }

    private func endBackgroundTime() {
        guard backgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTask)
        backgroundTask = .invalid
    }

    /// First tap: finish the current step, save, stop. Second tap: stop immediately.
    func stop() {
        switch phase {
        case .running:
            stopFlag.request()
            phase = .stopping
            status = "Stopping after the current step... (tap Stop again to stop right away)"
            append("\nStop requested -- finishing the current step and saving. Tap Stop again to stop right away.")
        case .waitingForLogin, .stopping:
            stopFlag.request()
            task?.cancel()
            status = "Stopping now..."
        case .idle:
            break
        }
    }

    // MARK: Files and login

    func refreshFiles() {
        reportExists = FileManager.default.fileExists(atPath: htmlURL.path)
        reportVersion += 1
    }

    func copyLog() { UIPasteboard.general.string = logText }

    func forgetLogin() {
        Task {
            await page.forgetLogin()
            append("Saved LEGO.com login removed. You'll be asked to log in on the next run.")
            page.webView.load(URLRequest(url: URL(string: ordersURL)!))
        }
    }

    func goToOrdersPage() { page.webView.load(URLRequest(url: URL(string: ordersURL)!)) }
}
