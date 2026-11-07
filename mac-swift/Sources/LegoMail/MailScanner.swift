import Foundation
import LegoCore

/// Where Apple Mail keeps its messages: ~/Library/Mail (inside it, V10/ on recent macOS).
public let defaultMailFolder: URL = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Mail", isDirectory: true)

/// Why a mail folder can't be read.
public enum MailAccessProblem: Error, CustomStringConvertible, Equatable {
    /// macOS privacy protection: the app needs Full Disk Access to read ~/Library/Mail.
    case needsFullDiskAccess(String)
    case notFound(String)

    public var description: String {
        switch self {
        case let .needsFullDiskAccess(path):
            return "macOS didn't let this app read \(path). Give it Full Disk Access: System Settings → "
                + "Privacy & Security → Full Disk Access, turn it on for this app, then quit and reopen the app."
        case let .notFound(path):
            return "The folder \(path) doesn't exist. Has Apple Mail been set up on this Mac?"
        }
    }
}

/// nil if the folder can be read; otherwise why not.
public func checkMailAccess(_ folder: URL) -> MailAccessProblem? {
    var isDir: ObjCBool = false
    guard FileManager.default.fileExists(atPath: folder.path, isDirectory: &isDir), isDir.boolValue else {
        return .notFound(folder.path)
    }
    do {
        _ = try FileManager.default.contentsOfDirectory(atPath: folder.path)
        return nil
    } catch {
        return .needsFullDiskAccess(folder.path)
    }
}

/// The System Settings page where Full Disk Access is turned on.
public let fullDiskAccessSettingsURL = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")!

public struct MailScanOptions {
    public var folder: URL
    /// Skip emails sent before this day (nil = all).
    public var since: SimpleDate?
    /// If set, every email that looked like a LEGO order email is saved here as text.
    public var saveTextDir: URL?

    public init(folder: URL, since: SimpleDate? = nil, saveTextDir: URL? = nil) {
        self.folder = folder; self.since = since; self.saveTextDir = saveTextDir
    }
}

public struct MailScanResult {
    public var emails: [LegoEmail] = []
    public var filesChecked = 0
    public var messagesChecked = 0
    /// Emails that looked like LEGO order emails but had no order number in them.
    public var withoutOrderNumber = 0
    public var unreadable = 0
}

/// Every mail file under `folder` (.emlx, .eml, mbox), in a stable order.
public func mailFiles(under folder: URL) -> [URL] {
    let keys: [URLResourceKey] = [.isRegularFileKey]
    guard let e = FileManager.default.enumerator(at: folder, includingPropertiesForKeys: keys,
                                                 options: [.skipsHiddenFiles], errorHandler: { _, _ in true })
    else { return [] }
    var files: [URL] = []
    for case let url as URL in e {
        guard mailFileKind(url) != nil,
              (try? url.resourceValues(forKeys: Set(keys)).isRegularFile) == true else { continue }
        files.append(url)
    }
    return files.sorted { $0.path < $1.path }
}

/// Read every LEGO order email under the folder. Slow part of a run (seconds to a minute for a
/// big mailbox), so call it off the main thread. Checks `stop` between files.
public func scanMail(_ o: MailScanOptions, stop: StopFlag = StopFlag(), log: (String) -> Void = { _ in }) -> MailScanResult {
    var result = MailScanResult()
    let files = mailFiles(under: o.folder)
    log("Found \(files.count) mail file(s) in \(o.folder.path). Looking for LEGO order emails...")
    let sinceDate = o.since?.toDate()
    var seenIDs = Set<String>()
    var saved = 0
    if let dir = o.saveTextDir { try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true) }

    for (n, file) in files.enumerated() {
        if stop.requested { log("Stopped while reading emails."); break }
        if n > 0 && n % 5000 == 0 {
            log("  checked \(n) of \(files.count) files, \(result.emails.count) LEGO order email(s) so far")
        }
        result.filesChecked += 1
        guard let kind = mailFileKind(file) else { continue }

        // Fast path for Mail's one-message files: look at the headers before reading the rest.
        if kind != .mbox {
            guard let head = readPrefix(file, bytes: 64 * 1024) else { result.unreadable += 1; continue }
            result.messagesChecked += 1
            let headers = parseMailHeaders(kind == .emlx ? emlxMessageData(head) : head)
            guard looksLikeLegoOrderEmail(headers), !isBefore(headers.date, sinceDate) else { continue }
        }
        guard let data = try? Data(contentsOf: file) else { result.unreadable += 1; continue }
        for raw in rawMessages(in: data, kind: kind) {
            if kind == .mbox {
                result.messagesChecked += 1
                let headers = parseMailHeaders(raw)
                guard looksLikeLegoOrderEmail(headers), !isBefore(headers.date, sinceDate) else { continue }
            }
            let message = parseMail(raw)
            // The same email often sits in two mailboxes (e.g. Gmail's Inbox and All Mail).
            let id = message.messageID ?? "\(file.path)#\(message.subject)#\(message.header("Date") ?? "")"
            guard seenIDs.insert(id).inserted else { continue }

            let email = parseLegoEmail(message, source: file.path)
            if let email { result.emails.append(email) } else { result.withoutOrderNumber += 1 }
            if let dir = o.saveTextDir {
                saved += 1
                saveEmailText(message, email, file: file, number: saved, to: dir)
            }
        }
    }
    log("Checked \(result.messagesChecked) email(s): \(result.emails.count) LEGO order email(s) found"
        + (result.withoutOrderNumber > 0 ? ", \(result.withoutOrderNumber) LEGO email(s) without an order number skipped" : "")
        + (result.unreadable > 0 ? ", \(result.unreadable) file(s) couldn't be read" : "") + ".")
    if let dir = o.saveTextDir, saved > 0 { log("Saved the text of \(saved) email(s) in \(dir.path)") }
    return result
}

private func isBefore(_ date: Date?, _ since: Date?) -> Bool {
    guard let date, let since else { return false }
    return date < since
}

private func readPrefix(_ url: URL, bytes: Int) -> Data? {
    guard let h = try? FileHandle(forReadingFrom: url) else { return nil }
    defer { try? h.close() }
    return try? h.read(upToCount: bytes) ?? Data()
}

/// Troubleshooting copy of one email: its headers, both text versions, and what was read from it.
/// Contains order details and your address, so share it only with someone you trust.
func saveEmailText(_ m: MailMessage, _ email: LegoEmail?, file: URL, number: Int, to dir: URL) {
    let day = m.date.map { d -> String in
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM-dd"; return f.string(from: d)
    } ?? "undated"
    let name = "\(day)_\(email?.orderNumber ?? "no-order-number")_\(email?.kind.rawValue ?? "skipped")_"
        + String(format: "%04d", number) + ".txt"
    var out = """
    File: \(file.path)
    From: \(m.from)
    Subject: \(m.subject)
    Date: \(m.header("Date") ?? "")

    ===== What the app read =====

    """
    if let e = email {
        out += "Order number: \(e.orderNumber)\nEmail kind: \(e.kind.rawValue) (status \(e.kind.status ?? "none"))\n"
        out += "Order date: \(e.orderDate ?? "(not in email)")\nTracking: \(e.trackingNumbers.joined(separator: ", "))\n"
        out += "Summary: " + e.summary.keys.map { "\($0)=\(e.summary[$0] ?? "")" }.joined(separator: ", ") + "\n"
        out += "Items (\(e.items.count)):\n"
        for it in e.items {
            out += "  - \(it.name) | number \(it.itemNumber ?? "-") | qty \(it.quantity.map(String.init) ?? "-") | "
                + "regular \(it.regularPrice ?? "-") | sale \(it.salePrice ?? "-")"
                + (it.isFreeGift ? " | free gift" : "") + (it.isPiece ? " | piece" : "") + (it.isGiftCard ? " | gift card" : "") + "\n"
        }
    } else {
        out += "No LEGO order number found, so this email was skipped.\n"
    }
    out += "\n===== Plain-text part =====\n\n" + (m.plainText.trimmed.isEmpty ? "(none)" : m.plainText)
    out += "\n\n===== HTML part, as text =====\n\n" + (m.htmlText.isEmpty ? "(none)" : htmlToText(m.htmlText)) + "\n"
    try? out.write(to: dir.appendingPathComponent(name), atomically: true, encoding: .utf8)
}
