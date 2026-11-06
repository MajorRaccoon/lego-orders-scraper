import Foundation

/// Write to "<name>.tmp", then rename into place, so the real file is always either the old
/// complete version or the new complete version - never half-written.
public func atomicWrite(_ url: URL, _ write: (URL) throws -> Void) throws {
    let tmp = url.deletingLastPathComponent().appendingPathComponent(url.lastPathComponent + ".tmp")
    do {
        try write(tmp)
        if FileManager.default.fileExists(atPath: url.path) {
            _ = try FileManager.default.replaceItemAt(url, withItemAt: tmp)
        } else {
            try FileManager.default.moveItem(at: tmp, to: url)
        }
    } catch {
        try? FileManager.default.removeItem(at: tmp)
        throw error
    }
}

public func atomicWrite(_ url: URL, text: String) throws {
    try atomicWrite(url) { tmp in try Data(text.utf8).write(to: tmp) }
}

/// Load every order from a saved JSON file (throws on a missing or broken file).
public func loadOrders(_ url: URL) throws -> [LegoOrder] {
    let text = try String(contentsOf: url, encoding: .utf8)
    guard case let .array(list) = try JSONParser.parse(text) else {
        throw JSONParseError(message: "expected a JSON list of orders")
    }
    return try list.map(LegoOrder.fromJSON)
}

/// Orders from a previous run that already have item detail (so they can be skipped),
/// in file order. Missing or unreadable file -> empty (start fresh).
public func loadExistingOrders(_ url: URL, log: (String) -> Void = { _ in }) -> [(String, LegoOrder)] {
    guard FileManager.default.fileExists(atPath: url.path) else { return [] }
    do {
        var result: [(String, LegoOrder)] = []
        for o in try loadOrders(url) where !o.items.isEmpty {
            if let i = result.firstIndex(where: { $0.0 == o.orderNumber }) { result[i].1 = o }
            else { result.append((o.orderNumber, o)) }
        }
        return result
    } catch {
        log("  (couldn't read existing \(url.path), starting fresh: \(error))")
        return []
    }
}

public func ordersJSON(_ orders: [LegoOrder]) -> String {
    JSONWriter.write(.array(orders.map { $0.toJSON() }))
}

public let csvHeader = [
    "order_number", "order_date", "order_status", "order_total",
    "order_subtotal", "order_delivery", "order_tax",
    "order_insiders_discount", "order_discount",
    "item_name", "item_number", "custom_id", "quantity",
    "regular_price", "sale_price",
    "is_free_gift", "is_piece", "is_gift_card", "item_status",
    "tracking_number",
]

/// One CSV field the way Python's csv.writer (QUOTE_MINIMAL) writes it.
func csvField(_ s: String) -> String {
    if s.contains(",") || s.contains("\"") || s.contains("\n") || s.contains("\r") {
        return "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }
    return s
}

private func py(_ b: Bool) -> String { b ? "True" : "False" }

/// The CSV text (one row per item), byte-identical to the Python scraper's output.
public func ordersCSV(_ orders: [LegoOrder]) -> String {
    var rows: [[String]] = [csvHeader]
    for o in orders {
        let s = o.summary
        func sum(_ k: String) -> String { s[k].flatMap { $0.isEmpty ? nil : $0 } ?? "" }
        for it in o.items {
            rows.append([
                o.orderNumber, o.orderDate ?? "", o.status ?? "", o.total ?? "",
                sum("subtotal"), sum("delivery"), sum("tax"), sum("insiders_discount"), sum("discount"),
                it.name, it.itemNumber ?? "", it.customID ?? "", it.quantity.map(String.init) ?? "",
                it.regularPrice.flatMap { $0.isEmpty ? nil : $0 } ?? "",
                it.salePrice.flatMap { $0.isEmpty ? nil : $0 } ?? "",
                py(it.isFreeGift), py(it.isPiece), py(it.isGiftCard),
                it.status ?? "", it.trackingNumber ?? "",
            ])
        }
    }
    return rows.map { $0.map(csvField).joined(separator: ",") + "\r\n" }.joined()
}

/// Copies of `orders` with every item's tracking number blanked ("Leave out tracking numbers").
/// The field/column stays in every file, just empty, so files keep the same shape.
public func withoutTracking(_ orders: [LegoOrder]) -> [LegoOrder] {
    orders.map { o in
        var c = o
        for i in c.items.indices { c.items[i].trackingNumber = nil }
        return c
    }
}

/// The CSV's name before Swift app v7 / scraper v36.
public let oldDefaultCSVName = "lego_order_items.csv"

/// One-time switch to the new CSV name: if `csv` (lego_orders.csv) doesn't exist yet and an old
/// lego_order_items.csv sits next to it, rename the old file. Same rule as the Python scraper.
@discardableResult
public func renameOldCSV(_ csv: URL) -> Bool {
    let fm = FileManager.default
    let old = csv.deletingLastPathComponent().appendingPathComponent(oldDefaultCSVName)
    guard csv.lastPathComponent == "lego_orders.csv", !fm.fileExists(atPath: csv.path),
          fm.fileExists(atPath: old.path) else { return false }
    return (try? fm.moveItem(at: old, to: csv)) != nil
}

/// Write the JSON and CSV files atomically. Safe to call after every order.
/// includeTracking false blanks every tracking number.
public func writeOutputs(_ orders: [LegoOrder], json: URL, csv: URL, quiet: Bool = false,
                         includeTracking: Bool = true, log: (String) -> Void = { _ in }) throws {
    // Dedupe here too so JSON and CSV are always built from the same list.
    var orders = dedupeOrders(orders, log: log)
    if !includeTracking { orders = withoutTracking(orders) }
    try atomicWrite(json, text: ordersJSON(orders))
    try atomicWrite(csv, text: ordersCSV(orders))
    guard !quiet else { return }
    let withItems = orders.filter { !$0.items.isEmpty }.count
    if withItems == orders.count {
        log("\nWrote \(json.lastPathComponent) and \(csv.lastPathComponent) (\(orders.count) order(s)).")
    } else {
        log("\nWrote \(json.lastPathComponent) and \(csv.lastPathComponent): \(orders.count) order(s) listed, "
            + "\(withItems) of them with item detail (the other \(orders.count - withItems) have no items yet -- "
            + "skipped by the since date, or a fetch that failed and will be retried next run).")
    }
}
