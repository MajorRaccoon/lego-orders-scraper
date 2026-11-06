import Foundation

/// The order's own detail page is the authoritative source for its total. If its summary
/// has a Total that differs from the list-page total, use it. Returns true if it changed.
@discardableResult
public func reconcileTotal(_ order: inout LegoOrder, log: (String) -> Void = { _ in }) -> Bool {
    if let detailTotal = order.summary["total"], !detailTotal.isEmpty, detailTotal != order.total {
        log("  note: \(order.orderNumber): list-page total \(pyRepr(order.total)) corrected to \(pyRepr(detailTotal)) (from its own order-detail page)")
        order.total = detailTotal
        return true
    }
    return false
}

func pyRepr(_ s: String?) -> String {
    guard let s else { return "None" }
    return "'" + s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'") + "'"
}

/// Combine this run's order list with orders saved by a previous run.
/// - In both: keep saved items, refresh list fields (status/date/total/count).
/// - Only new: added as-is (items empty, to be fetched).
/// - Only saved: kept at the end, never dropped.
public func mergeWithExisting(_ fresh: [LegoOrder], _ existing: [(String, LegoOrder)],
                              log: (String) -> Void = { _ in }) -> [LegoOrder] {
    var merged: [String: LegoOrder] = [:]
    for (k, v) in existing { merged[k] = v }
    for order in fresh {
        let num = order.orderNumber
        if var e = merged[num] {
            e.status = order.status
            e.orderDate = order.orderDate
            e.total = order.total
            e.itemCountListed = order.itemCountListed
            reconcileTotal(&e, log: log)
            merged[num] = e
        } else {
            merged[num] = order
        }
    }
    let seen = fresh.map(\.orderNumber)
    let seenSet = Set(seen)
    let leftovers = existing.map(\.0).filter { !seenSet.contains($0) }
    return (seen + leftovers).map { merged[$0]! }
}

/// Collapse repeated order numbers to one entry (LEGO's list sometimes renders an order twice).
/// Keeps the copy that has items when there's a choice, else the first. Order-preserving.
public func dedupeOrders(_ orders: [LegoOrder], log: (String) -> Void = { _ in }) -> [LegoOrder] {
    var byNumber: [String: LegoOrder] = [:]
    var sequence: [String] = []
    for order in orders {
        let num = order.orderNumber
        guard let existing = byNumber[num] else {
            byNumber[num] = order
            sequence.append(num)
            continue
        }
        if existing.items.isEmpty && !order.items.isEmpty {
            log("  (note: \(num) appeared more than once in the order list -- keeping the copy that has item detail)")
            byNumber[num] = order
        }
    }
    return sequence.map { byNumber[$0]! }
}
