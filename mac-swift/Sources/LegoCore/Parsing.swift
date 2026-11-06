import Foundation

// Line-by-line ports of the Python scraper's page-text parsers. LEGO.com has no API for
// order history, so these read the same text a person sees. If LEGO redesigns its pages,
// fix these functions (and the Python ones) - each has unit tests in LegoCoreTests.

/// Order/shipment status words. A line that is exactly one of these is a status line.
public let statusWords: Set<String> = [
    "Shipped", "Delivered", "Backordered", "In Warehouse",
    "Processing", "Cancelled", "Canceled", "Returned", "Refunded", "Pending",
]

/// Every "Order Number: Txxx" in page text, in page order.
public func currentOrderNumbers(_ text: String) -> [String] {
    Rx.findAll("Order Number:\\s*(T\\d+)", text)
}

/// Turn the My Orders page text into orders (items/summary still empty).
///
/// Expects blocks like:
///     Backordered
///     Order Number: T514535382
///     Order Date: September 7, 2026
///     Total: $369.95
///     6 items in this order
public func parseOrderList(_ text: String, maxOrders: Int? = nil) -> [LegoOrder] {
    let lines = nonEmptyStrippedLines(text)
    var orders: [LegoOrder] = []
    for (i, line) in lines.enumerated() {
        guard let m = Rx.match("^Order Number:\\s*(T\\d+)$", line), let orderNumber = m[1] else { continue }
        let status: String? = i > 0 ? lines[i - 1] : nil
        var orderDate: String?, total: String?, itemCount: Int?
        var j = i + 1
        while j < min(i + 8, lines.count) {
            let l = lines[j]
            // Reached the NEXT order's block: stop, or this order would get its neighbor's date/total.
            if Rx.match("^Order Number:\\s*T\\d+$", l) != nil { break }
            if let dm = Rx.match("^Order Date:\\s*(.+)$", l) {
                if orderDate == nil { orderDate = dm[1] }
            } else if let tm = Rx.match("^Total:\\s*\\$([\\d,.]+)$", l) {
                if total == nil { total = tm[1] }
            } else if let im = Rx.match("^(\\d+)\\s+items?\\s+in this order$", l) {
                itemCount = Int(im[1]!)
                break  // item-count line is always the last one we need
            }
            j += 1
        }
        orders.append(LegoOrder(orderNumber: orderNumber, status: status, orderDate: orderDate, total: total,
                                itemCountListed: itemCount, url: orderDetailURL(orderNumber)))
        if let maxOrders, maxOrders > 0, orders.count >= maxOrders { break }
    }
    return orders
}

/// Delete every non-ASCII character from an item name ("Technic™ Hub" -> "Technic Hub").
public func cleanItemName(_ name: String) -> String {
    String(String.UnicodeScalarView(name.unicodeScalars.filter { $0.value <= 127 }))
}

/// Prices collected off an item's Price block -> {regularPrice, salePrice}.
/// None: both nil (free gift). One: both the same. Two or more: first = regular, last = sale.
public func buildPrices(_ raw: [String]) -> OrderedStrings {
    guard let first = raw.first, let last = raw.last else { return emptyPrices() }
    return OrderedStrings([("product.regularPrice", first), ("product.salePrice", last)])
}

private let summaryLabels: [(String, String)] = [
    ("Subtotal", "subtotal"),
    ("Delivery", "delivery"),
    ("Shipping", "delivery"),  // alternate label for the same line
    ("Tax", "tax"),
    ("LEGO® Insiders discount", "insiders_discount"),  // kept separate from a generic Discount
    ("Discount", "discount"),
    ("Total", "total"),
]
private let summaryAmount = "(-?\\$[\\d,]+\\.\\d{2})"

/// Parse the "Order summary" block (Subtotal / Delivery / Tax / discounts / Total).
/// Handles "Subtotal $754.96" and "Subtotal" / "$754.96" layouts. Missing lines are left out.
public func parseOrderSummary(_ text: String) -> OrderedStrings {
    guard let r = text.range(of: "Order summary") else { return OrderedStrings() }
    let lines = nonEmptyStrippedLines(String(text[r.upperBound...]))
    var result = OrderedStrings()
    var i = 0
    while i < lines.count {
        let line = lines[i]
        var matchedKey: String?
        for (label, key) in summaryLabels {
            if result.contains(key) { continue }
            if Rx.match("^" + Rx.escape(label) + "\\b", line) != nil { matchedKey = key; break }
        }
        guard let key = matchedKey else { i += 1; continue }
        if let m = Rx.search(summaryAmount, line) {
            result[key] = m[1]!.replacingOccurrences(of: "$", with: "")
            i += 1
            continue
        }
        if i + 1 < lines.count, let m2 = Rx.search(summaryAmount, lines[i + 1]) {
            result[key] = m2[1]!.replacingOccurrences(of: "$", with: "")
            i += 2
            continue
        }
        i += 1  // label with no amount nearby - skip it, never fabricate
    }
    return result
}

/// Read a Price block starting at `i`: "-" (free), "$X.XX" values, and sale/Insiders labels.
private func collectPrices(_ lines: [String], _ i: inout Int) -> [String] {
    var raw: [String] = []
    while i < lines.count {
        let nxt = lines[i]
        if nxt == "-" { i += 1; continue }
        if Rx.match("^\\$[\\d,.]+$", nxt) != nil {
            raw.append(String(nxt.drop(while: { $0 == "$" })))
            i += 1
            continue
        }
        if nxt == "product.salePrice" || nxt == "LEGO® Insiders Price" { i += 1; continue }
        break
    }
    return raw
}

private let priceToken = "Price|product\\.salePrice|LEGO® Insiders Price|\\$[\\d,.]+|-"
private let priceLabels: Set<String> = ["Price", "product.salePrice", "LEGO® Insiders Price"]

/// Split a price line whose parts got run together back into separate lines.
/// LEGO's "Price" label is visually hidden; Chromium's page text puts it on its own line, but
/// WebKit (this app's browser) runs it into the amount: "Price$119.99", "Price-",
/// "product.salePrice$4.99". A line made up entirely of 2+ price pieces, at least one a label,
/// is split into those pieces; any other line comes back unchanged. Same as the Python version.
public func splitGluedPriceLine(_ line: String) -> [String] {
    let ns = line as NSString
    let re = Rx.compile(priceToken)
    var tokens: [String] = []
    var pos = 0
    while pos < ns.length {
        guard let m = re.firstMatch(in: line, options: [.anchored], range: NSRange(location: pos, length: ns.length - pos))
        else { return [line] }
        tokens.append(ns.substring(with: m.range))
        pos = m.range.location + m.range.length
        while pos < ns.length, let u = Unicode.Scalar(ns.character(at: pos)),
              CharacterSet.whitespacesAndNewlines.contains(u) { pos += 1 }
    }
    if tokens.count >= 2 && tokens.contains(where: priceLabels.contains) { return tokens }
    return [line]
}

/// Parse an order-details page into line items. Handles normal items, free gifts, sale and
/// Insiders prices, multiple shipments with tracking numbers, per-item status lines,
/// Bricks and Pieces (SKU) pieces, digital gift cards, and custom IDs (Minifigure Factory).
public func parseOrderDetail(_ text: String) -> [LegoOrderLine] {
    let lines = nonEmptyStrippedLines(text).flatMap(splitGluedPriceLine)
    let n = lines.count
    var items: [LegoOrderLine] = []
    var currentStatus: String?
    var currentTracking: String?
    var i = 0
    while i < n {
        let line = lines[i]

        if let tm = Rx.match("^Tracking number:\\s*(\\S+)$", line) {
            currentTracking = tm[1]
            i += 1
            continue
        }
        if statusWords.contains(line) {
            currentStatus = line
            i += 1
            continue
        }

        let numberLine = i + 1 < n ? lines[i + 1] : ""
        if let nm = Rx.match("^(Item|SKU):\\s*(.+)$", numberLine) {
            let name = cleanItemName(line)
            let isPiece = nm[1] == "SKU"
            let itemNumber = pyStrip(nm[2]!)
            i += 2

            var customID: String?
            if i < n, let idm = Rx.match("^ID:\\s*(.+)$", lines[i]) {
                customID = pyStrip(idm[1]!)
                i += 1
            }

            var quantity: Int?
            if i < n, lines[i].hasPrefix("Quantity:") {
                if let q = Rx.search("\\d+", lines[i]) { quantity = Int(q[0]!) }
                i += 1
            }

            if i < n, lines[i] == "Price" { i += 1 }
            let raw = collectPrices(lines, &i)
            items.append(LegoOrderLine(name: name, itemNumber: itemNumber, customID: customID, quantity: quantity,
                                       prices: buildPrices(raw), isFreeGift: raw.isEmpty, isPiece: isPiece,
                                       isGiftCard: false, status: currentStatus, trackingNumber: currentTracking))
            continue
        }

        // Digital gift card: Name, then straight into "Quantity: N" (no Item/SKU line).
        if let qm = Rx.match("^Quantity:\\s*(\\d+)$", numberLine) {
            let name = cleanItemName(line)
            let quantity = Int(qm[1]!)
            i += 2
            if i < n, lines[i] == "Price" { i += 1 }
            let raw = collectPrices(lines, &i)
            items.append(LegoOrderLine(name: name, itemNumber: nil, customID: nil, quantity: quantity,
                                       prices: buildPrices(raw), isFreeGift: raw.isEmpty, isPiece: false,
                                       isGiftCard: true, status: currentStatus, trackingNumber: currentTracking))
            continue
        }

        i += 1
    }
    return items
}
