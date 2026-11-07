import Foundation
import LegoCore

/// File names used by the Mail reader. Kept apart from the LEGO.com scraper's lego_orders.*
/// so the two never overwrite each other. Same formats, so the same tools read both.
public let mailJSONName = "lego_mail_orders.json"
public let mailCSVName = "lego_mail_orders.csv"
public let mailHTMLName = "lego_mail_orders.html"

public struct MailRunOptions {
    public var mailFolder: URL
    public var jsonURL: URL
    public var csvURL: URL
    /// nil = no HTML report.
    public var htmlURL: URL?
    public var since: SimpleDate?
    public var includeTracking = true
    /// Ignore orders saved by an earlier run (normally they're kept if their emails are gone).
    public var fresh = false
    public var saveTextDir: URL?

    public init(mailFolder: URL, outputDir: URL, makeHTML: Bool = true) {
        self.mailFolder = mailFolder
        jsonURL = outputDir.appendingPathComponent(mailJSONName)
        csvURL = outputDir.appendingPathComponent(mailCSVName)
        htmlURL = makeHTML ? outputDir.appendingPathComponent(mailHTMLName) : nil
    }
}

public struct MailRunError: Error, CustomStringConvertible {
    public let description: String
}

/// One complete run: read the mail, build the orders, write JSON + CSV (+ HTML). Blocking; call
/// it off the main thread. Returns the orders written.
@discardableResult
public func runMailImport(_ o: MailRunOptions, stop: StopFlag = StopFlag(), log: (String) -> Void = { _ in }) throws -> [LegoOrder] {
    if let problem = checkMailAccess(o.mailFolder) { throw MailRunError(description: problem.description) }
    let started = Date()
    let scan = scanMail(MailScanOptions(folder: o.mailFolder, since: o.since, saveTextDir: o.saveTextDir), stop: stop, log: log)
    if stop.requested { throw CancellationError() }

    var orders = buildOrders(from: scan.emails)
    if let since = o.since {
        let before = orders.count
        orders = orders.filter { !isBeforeSinceDate($0, since) }
        if before != orders.count { log("Left out \(before - orders.count) order(s) placed before \(since).") }
    }

    var previous: [LegoOrder] = []
    if !o.fresh, FileManager.default.fileExists(atPath: o.jsonURL.path) {
        do { previous = try loadOrders(o.jsonURL) } catch { log("  (couldn't read the earlier \(o.jsonURL.lastPathComponent), starting fresh: \(error))") }
    }
    let all = mergeMailOrders(orders, previous: previous)
    let kept = all.count - orders.count
    if kept > 0 { log("Kept \(kept) order(s) from the earlier run that weren't found in the mail this time.") }

    try FileManager.default.createDirectory(at: o.jsonURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try writeOutputs(all, json: o.jsonURL, csv: o.csvURL, quiet: true, includeTracking: o.includeTracking, log: log)
    var written = [o.jsonURL.lastPathComponent, o.csvURL.lastPathComponent]
    if let html = o.htmlURL {
        let rows = dedupeOrders(o.includeTracking ? all : withoutTracking(all))
        try atomicWrite(html, text: renderOrdersHTML(rows, title: "LEGO Orders from Apple Mail"))
        written.append(html.lastPathComponent)
    }

    let withItems = all.filter { !$0.items.isEmpty }.count
    log("")
    for order in orders {
        let itemsText = order.items.isEmpty ? "no items found in its emails" : "\(order.items.count) item(s)"
        log("  \(order.orderNumber)  \(order.orderDate ?? "date unknown")  \(order.status ?? "-")  "
            + "\(order.total.map { "$" + $0 } ?? "total unknown")  \(itemsText)")
    }
    log("\nWrote \(written.joined(separator: ", ")): \(all.count) order(s), \(withItems) with item detail. "
        + String(format: "(%.1f s)", Date().timeIntervalSince(started)))
    if all.count > withItems {
        log("Some orders have no items: their confirmation email may be missing, or in a layout this app "
            + "doesn't read yet. Turn on \"Save matched emails for troubleshooting\" and send the files to get it fixed.")
    }
    return all
}
