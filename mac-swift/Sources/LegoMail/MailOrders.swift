import Foundation
import LegoCore

// An order usually has several emails: a confirmation (items and prices), then one or more
// "shipped" emails (tracking numbers), then "delivered". This file combines them into one
// LegoOrder, the same record the LEGO.com scraper saves, so the JSON/CSV/HTML writers and the
// HTML report work unchanged.

/// Combine every LEGO email into orders, newest order first.
/// - Items, prices and the money summary come from the email with the most item detail
///   (normally the order confirmation).
/// - The order's status comes from the latest email that says something about it.
/// - A shipped/delivered/cancelled email that lists items updates only those items (partial
///   shipments and cancellations); one that lists none updates every item.
public func buildOrders(from emails: [LegoEmail], timeZone: TimeZone = .current) -> [LegoOrder] {
    // A receipt saved under its receipt number (its PDF wasn't available) joins the order that
    // the same receipt's PDF names, when that PDF was read elsewhere (e.g. a folder of PDFs).
    var orderForReceipt: [String: String] = [:]
    for e in emails where isLegoOrderNumber(e.orderNumber) {
        if let r = e.receiptNumber { orderForReceipt[r] = e.orderNumber }
    }
    let resolved = emails.map { e -> LegoEmail in
        guard !isLegoOrderNumber(e.orderNumber), let order = orderForReceipt[e.orderNumber] else { return e }
        var moved = e
        moved.orderNumber = order
        return moved
    }
    var groups: [String: [LegoEmail]] = [:]
    var sequence: [String] = []
    for e in resolved {
        if groups[e.orderNumber] == nil { sequence.append(e.orderNumber) }
        groups[e.orderNumber, default: []].append(e)
    }
    var orders = sequence.map { buildOrder($0, groups[$0]!, timeZone: timeZone) }
    // Newest first, like LEGO's My Orders list. Undated orders go last.
    let dates = Dictionary(uniqueKeysWithValues: orders.map { ($0.orderNumber, parseOrderDate($0.orderDate)) })
    orders = orders.enumerated().sorted { a, b in
        switch (dates[a.element.orderNumber] ?? nil, dates[b.element.orderNumber] ?? nil) {
        case let (x?, y?) where x != y: return x > y
        case (.some, .none): return true
        case (.none, .some): return false
        default: return a.offset < b.offset
        }
    }.map(\.element)
    return orders
}

private func sameItem(_ a: LegoOrderLine, _ b: LegoOrderLine) -> Bool {
    if let x = a.itemNumber, let y = b.itemNumber { return x == y }
    // A PDF receipt may cut a long name short ("Millennium Falcon...").
    let x = a.name.lowercased().replacingOccurrences(of: "...", with: ""), y = b.name.lowercased().replacingOccurrences(of: "...", with: "")
    return x == y || (min(x.count, y.count) >= 12 && (x.hasPrefix(y) || y.hasPrefix(x)))
}

/// A LEGO Shop receipt (PDF). A split order gets one per shipment, each with its own total.
private func isReceipt(_ e: LegoEmail) -> Bool { e.kind == .confirmation && e.receiptNumber != nil }

/// The order's receipts, each receipt number once (the same receipt can come from Mail and from
/// the receipt folder), keeping the copy with the most detail.
private func distinctReceipts(_ emails: [LegoEmail]) -> [LegoEmail] {
    var best: [String: LegoEmail] = [:]
    var order: [String] = []
    for e in emails where isReceipt(e) && !e.summary.isEmpty {
        let r = e.receiptNumber!
        if let b = best[r] {
            if e.summary.keys.count > b.summary.keys.count { best[r] = e }
        } else { best[r] = e; order.append(r) }
    }
    return order.map { best[$0]! }
}

/// Adds up several receipts' summaries, line by line ("subtotal", "tax", "total", ...).
private func sumSummaries(_ summaries: [OrderedStrings]) -> OrderedStrings {
    var result = OrderedStrings()
    var keys: [String] = []
    for s in summaries { for k in s.keys where !keys.contains(k) { keys.append(k) } }
    for k in keys {
        let values = summaries.compactMap { $0[k] }.compactMap(amountValue)
        if !values.isEmpty { result[k] = String(format: "%.2f", values.reduce(0, +)) }
    }
    return result
}

func buildOrder(_ number: String, _ emails: [LegoEmail], timeZone: TimeZone) -> LegoOrder {
    // Oldest email first; emails with no date keep their place at the start.
    let byDate = emails.enumerated().sorted { a, b in
        switch (a.element.sentDate, b.element.sentDate) {
        case let (x?, y?) where x != y: return x < y
        case (.none, .some): return true
        case (.some, .none): return false
        default: return a.offset < b.offset
        }
    }.map(\.element)

    // Items: the email with the most items, preferring a confirmation, then the earliest.
    let detail = byDate.max { a, b in
        let sa = (a.items.count, a.kind == .confirmation ? 1 : 0), sb = (b.items.count, b.kind == .confirmation ? 1 : 0)
        return sa < sb
    }
    var items = detail?.items ?? []
    // Items only some later email mentions (e.g. a replacement part, or another shipment's
    // receipt) are added at the end.
    for e in byDate where e.kind != .confirmation || isReceipt(e) {
        for it in e.items where !items.contains(where: { sameItem($0, it) }) { items.append(it) }
    }

    // Money summary: the order confirmation's; else, for an order shipped in parts, all its
    // receipts added up (each covers one shipment); else whichever email has the most of it.
    let receipts = distinctReceipts(byDate)
    let summary = byDate.first { $0.kind == .confirmation && !isReceipt($0) && $0.summary["total"] != nil }?.summary
        ?? (receipts.count > 1 ? sumSummaries(receipts.map(\.summary)) : receipts.first?.summary)
        ?? byDate.max { $0.summary.keys.count < $1.summary.keys.count }?.summary
        ?? OrderedStrings()

    // Status, oldest to newest, for the order and each item.
    var orderStatus: String? = byDate.contains { $0.kind == .confirmation } ? LegoEmailKind.confirmation.status : nil
    var itemStatus = [String?](repeating: orderStatus, count: items.count)
    var itemTracking = [String?](repeating: nil, count: items.count)
    for e in byDate {
        guard let status = e.kind.status, e.kind != .confirmation else { continue }
        let tracking = e.trackingNumbers.first
        let listed = items.indices.filter { i in e.items.contains { sameItem($0, items[i]) } }
        let targets = listed.isEmpty ? Array(items.indices) : listed
        for i in targets {
            itemStatus[i] = status
            if let tracking { itemTracking[i] = tracking }
        }
        // A partial cancellation (some items listed, others not) doesn't cancel the whole order.
        if e.kind == .cancelled && !listed.isEmpty && listed.count < items.count { continue }
        orderStatus = status
    }
    for i in items.indices {
        // Digital gift cards are emailed, not shipped: no status or tracking, same as the scraper.
        if items[i].isGiftCard { items[i].status = nil; items[i].trackingNumber = nil; continue }
        items[i].status = itemStatus[i]
        items[i].trackingNumber = itemTracking[i]
    }

    // Order date: printed in an email, else the confirmation's send date, else the first email's.
    let orderDate = byDate.lazy.compactMap(\.orderDate).first
        ?? (byDate.first { $0.kind == .confirmation }?.sentDate ?? byDate.first?.sentDate).map { formatOrderDate($0, timeZone: timeZone) }

    let itemCount: Int? = items.isEmpty ? nil : items.reduce(0) { $0 + ($1.quantity ?? 1) }
    // A cancelled order cost nothing: $0.00, as on LEGO.com. The summary keeps what it would have cost.
    let total = orderStatus == LegoEmailKind.cancelled.status ? "0.00" : summary["total"]
    return LegoOrder(orderNumber: number, status: orderStatus, orderDate: orderDate, total: total,
                     itemCountListed: itemCount,
                     // A receipt saved under its receipt number has no order page: link to My Orders.
                     url: isLegoOrderNumber(number) ? orderDetailURL(number) : ordersURL,
                     items: items, summary: summary)
}

/// This run's orders first (newest first), then orders saved by an earlier run that weren't
/// found this time (their emails may have been deleted or archived elsewhere), so nothing is lost.
public func mergeMailOrders(_ fresh: [LegoOrder], previous: [LegoOrder]) -> [LegoOrder] {
    let seen = Set(fresh.map(\.orderNumber))
    var kept = fresh
    // A receipt-number placeholder with no items (its PDF wasn't read then) isn't worth keeping.
    for o in previous where !seen.contains(o.orderNumber) && !kept.contains(where: { $0.orderNumber == o.orderNumber })
        && (isLegoOrderNumber(o.orderNumber) || !o.items.isEmpty) {
        kept.append(o)
    }
    // Re-sort so kept orders land at their date, not at the end.
    let indexed = kept.enumerated().map { ($0.offset, $0.element, parseOrderDate($0.element.orderDate)) }
    return indexed.sorted { a, b in
        switch (a.2, b.2) {
        case let (x?, y?) where x != y: return x > y
        case (.some, .none): return true
        case (.none, .some): return false
        default: return a.0 < b.0
        }
    }.map(\.1)
}
