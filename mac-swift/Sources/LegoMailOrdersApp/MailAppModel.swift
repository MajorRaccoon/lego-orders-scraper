import AppKit
import LegoCore
import LegoMail
import SwiftUI

/// App state: options, the running import, the log, and the result files.
@MainActor
final class MailAppModel: ObservableObject {
    enum Phase { case idle, running, stopping }

    struct LogLine: Identifiable { let id: Int; let text: String }

    @Published var phase: Phase = .idle
    @Published var log: [LogLine] = []
    @Published var status = "Ready. Click Start to read your LEGO order emails."
    @Published var reportExists = false
    /// Set when the mail folder can't be read (usually: Full Disk Access isn't on yet).
    @Published var accessProblem: MailAccessProblem?
    @Published var lastTextDir: URL?

    // Options, saved between launches (except "Start fresh", which is off at every launch).
    @Published var useSinceDate: Bool { didSet { defaults.set(useSinceDate, forKey: "useSinceDate") } }
    @Published var sinceDate: Date { didSet { defaults.set(sinceDate, forKey: "sinceDate") } }
    @Published var makeHTML: Bool { didSet { defaults.set(makeHTML, forKey: "makeHTML") } }
    @Published var leaveOutTracking: Bool { didSet { defaults.set(leaveOutTracking, forKey: "leaveOutTracking") } }
    @Published var excludeEmptyOrders: Bool { didSet { defaults.set(excludeEmptyOrders, forKey: "excludeEmptyOrders") } }
    @Published var saveEmailText: Bool { didSet { defaults.set(saveEmailText, forKey: "saveEmailText") } }
    @Published var fresh = false
    /// Where the JSON, CSV and HTML files are saved. Defaults to dataDir.
    @Published var outputDir: URL { didSet { defaults.set(outputDir.path, forKey: "outputDir"); refreshFiles() } }
    /// Optional folder of receipt PDFs saved from Mail (File > Save Attachments).
    @Published var receiptFolder: URL? { didSet { defaults.set(receiptFolder?.path, forKey: "receiptFolder") } }
    /// Which mail to read. Defaults to Apple Mail's own folder.
    @Published var mailFolder: URL { didSet { defaults.set(mailFolder.path, forKey: "mailFolder"); checkAccess() } }

    private let defaults = UserDefaults.standard
    private var task: Task<Void, Never>?
    private var stopFlag = StopFlag()
    private var lineCounter = 0

    /// ~/Library/Application Support/LEGO Order Scraper (the same folder as the LEGO.com scraper;
    /// this app's files have their own names, lego_mail_orders.*).
    static let defaultDataDir: URL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("LEGO Order Scraper", isDirectory: true)
    let dataDir = MailAppModel.defaultDataDir
    var jsonURL: URL { outputDir.appendingPathComponent(mailJSONName) }
    var csvURL: URL { outputDir.appendingPathComponent(mailCSVName) }
    var htmlURL: URL { outputDir.appendingPathComponent(mailHTMLName) }
    var isDefaultOutputDir: Bool { outputDir.standardizedFileURL.path == dataDir.standardizedFileURL.path }
    var isDefaultMailFolder: Bool { mailFolder.standardizedFileURL.path == defaultMailFolder.standardizedFileURL.path }
    let logFile: URL = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Logs/LEGO Mail Orders.log")

    init() {
        let d = UserDefaults.standard
        useSinceDate = d.object(forKey: "useSinceDate") as? Bool ?? false
        sinceDate = d.object(forKey: "sinceDate") as? Date ?? defaultSinceDate.toDate()
        makeHTML = d.object(forKey: "makeHTML") as? Bool ?? true
        leaveOutTracking = d.object(forKey: "leaveOutTracking") as? Bool ?? false
        excludeEmptyOrders = d.object(forKey: "excludeEmptyOrders") as? Bool ?? false  // unchecked by default
        saveEmailText = d.object(forKey: "saveEmailText") as? Bool ?? false
        outputDir = d.string(forKey: "outputDir").map { URL(fileURLWithPath: $0, isDirectory: true) } ?? MailAppModel.defaultDataDir
        mailFolder = d.string(forKey: "mailFolder").map { URL(fileURLWithPath: $0, isDirectory: true) } ?? defaultMailFolder
        receiptFolder = d.string(forKey: "receiptFolder").map { URL(fileURLWithPath: $0, isDirectory: true) }
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        refreshFiles()
        checkAccess()
    }

    var isBusy: Bool { phase != .idle }

    /// "~/Library/Mail" instead of "/Users/me/Library/Mail".
    func display(_ url: URL) -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let path = url.path
        return path.hasPrefix(home + "/") ? "~" + path.dropFirst(home.count) : path
    }

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
        try? FileManager.default.createDirectory(at: logFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let h = try? FileHandle(forWritingTo: logFile) {
            h.seekToEndOfFile(); h.write(Data(s.utf8)); try? h.close()
        } else {
            try? Data(s.utf8).write(to: logFile)
        }
    }

    var logText: String { log.map(\.text).joined(separator: "\n") }

    // MARK: Mail access

    /// Re-check whether the mail folder can be read (e.g. after turning on Full Disk Access).
    func checkAccess() { accessProblem = checkMailAccess(mailFolder) }

    func openFullDiskAccessSettings() { NSWorkspace.shared.open(fullDiskAccessSettingsURL) }

    // MARK: Run

    func start() {
        guard phase == .idle else { return }
        checkAccess()
        if let problem = accessProblem {
            status = problem.description
            return
        }
        do {
            try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
        } catch {
            status = "Can't use the folder \(display(outputDir)): \(error.localizedDescription) Choose another one."
            return
        }

        var o = MailRunOptions(mailFolder: mailFolder, outputDir: outputDir, makeHTML: makeHTML)
        o.since = useSinceDate ? SimpleDate(sinceDate) : nil
        o.includeTracking = !leaveOutTracking
        o.excludeEmptyOrders = excludeEmptyOrders
        o.fresh = fresh
        o.receiptFolder = receiptFolder
        let stamp = ISO8601DateFormatter().string(from: Date())
        o.saveTextDir = saveEmailText ? dataDir.appendingPathComponent("mail-text/\(stamp.replacingOccurrences(of: ":", with: "-"))") : nil

        let flag = StopFlag()
        stopFlag = flag
        log = []
        phase = .running
        status = "Reading your mail..."
        writeToLogFile("\n===== \(stamp) =====\n")
        append("LEGO Mail Orders v\(legoMailVersion)")
        append("Reading: \(display(mailFolder))")
        if let r = receiptFolder { append("Receipt PDFs: \(display(r))") }
        append(o.since.map { "Since date: \($0)" } ?? "Since date: none (every order in the mail)")

        let options = o
        task = Task { [weak self] in
            let activity = ProcessInfo.processInfo.beginActivity(options: [.userInitiated], reason: "Reading LEGO order emails")
            defer { ProcessInfo.processInfo.endActivity(activity) }
            // Lines from the background work are handed to the main thread in order.
            let log: (String) -> Void = { line in Task { @MainActor [weak self] in self?.append(line) } }
            do {
                let orders = try await Task.detached(priority: .userInitiated) {
                    try runMailImport(options, stop: flag, log: log)
                }.value
                let withItems = orders.filter { !$0.items.isEmpty }.count
                self?.status = "Done: \(orders.count) order(s), \(withItems) with item detail."
            } catch is CancellationError {
                self?.status = "Stopped. Nothing was saved this time; click Start to read the mail again."
            } catch {
                self?.append("\nERROR: \(error)")
                self?.status = "Something went wrong: \(error)"
            }
            // Let queued log lines land before showing "idle".
            await Task.yield()
            self?.lastTextDir = options.saveTextDir.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil }
            self?.phase = .idle
            self?.task = nil
            self?.fresh = false
            self?.refreshFiles()
        }
    }

    func stop() {
        guard phase == .running else { return }
        stopFlag.request()
        phase = .stopping
        status = "Stopping..."
    }

    // MARK: Files

    func refreshFiles() { reportExists = FileManager.default.fileExists(atPath: htmlURL.path) }

    func openReport() { NSWorkspace.shared.open(htmlURL) }

    func openDataFolder() {
        let files = [jsonURL, csvURL, htmlURL].filter { FileManager.default.fileExists(atPath: $0.path) }
        NSWorkspace.shared.activateFileViewerSelecting(files.isEmpty ? [outputDir] : files)
    }

    func openTextFolder() { if let d = lastTextDir { NSWorkspace.shared.activateFileViewerSelecting([d]) } }

    func openLog() { NSWorkspace.shared.open(logFile) }

    func copyLog() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(logText, forType: .string)
    }

    private func pickFolder(message: String, start: URL) -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Choose"
        panel.message = message
        panel.directoryURL = start
        return panel.runModal() == .OK ? panel.url : nil
    }

    func chooseOutputFolder() {
        if let url = pickFolder(message: "Choose where to save the LEGO order files (JSON, CSV and HTML).",
                                start: FileManager.default.fileExists(atPath: outputDir.path) ? outputDir : dataDir) {
            outputDir = url
        }
    }

    func resetOutputFolder() { outputDir = dataDir }

    func chooseMailFolder() {
        if let url = pickFolder(message: "Choose a folder of exported emails (.eml files or .mbox mailboxes), or Apple Mail's folder.",
                                start: FileManager.default.homeDirectoryForCurrentUser) {
            mailFolder = url
        }
    }

    func resetMailFolder() { mailFolder = defaultMailFolder }

    func chooseReceiptFolder() {
        if let url = pickFolder(message: "Choose the folder where you saved the LEGO receipt PDFs (Mail: File > Save Attachments).",
                                start: receiptFolder ?? FileManager.default.homeDirectoryForCurrentUser) {
            receiptFolder = url
        }
    }

    func clearReceiptFolder() { receiptFolder = nil }
}
