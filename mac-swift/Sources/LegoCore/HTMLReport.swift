import Foundation

// Self-contained HTML report (inline CSS, no external files). A port of the Python
// render_orders_html(); output is identical apart from the "Generated ..." timestamp.

let htmlStyle = """

<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f7f5; --panel: #ffffff; --text: #1d1d1f; --muted: #6b6b70;
    --border: #e3e3e0; --accent: #d01012; --accent-soft: #fdeceb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #17171a; --panel: #212125; --text: #ededf0; --muted: #9a9aa2;
      --border: #313136; --accent: #ff5a5c; --accent-soft: #3a1e1f;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  .wrap { max-width: 980px; margin: 0 auto; }
  h1 { font-size: 1.6em; margin: 0 0 4px; }
  .generated { color: var(--muted); font-size: 0.9em; margin: 0 0 24px; }
  .stats { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 28px; }
  .stat {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 18px; min-width: 140px; flex: 1 1 140px;
  }
  .stat .n { font-size: 1.5em; font-weight: 600; }
  .stat .l { color: var(--muted); font-size: 0.85em; }
  table { width: 100%; border-collapse: collapse; }
  .index-table { background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    overflow: hidden; margin-bottom: 36px; }
  .index-table th, .index-table td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 0.92em; }
  .index-table tr:last-child td { border-bottom: none; }
  .index-table th { color: var(--muted); font-weight: 600; background: var(--bg); }
  .index-table a { color: var(--text); text-decoration: none; }
  .index-table a:hover { color: var(--accent); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .order {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; margin-bottom: 18px; scroll-margin-top: 16px;
  }
  .order-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin-bottom: 4px; }
  .order-head h2 { font-size: 1.1em; margin: 0; }
  .order-head .date, .order-head .total { color: var(--muted); font-size: 0.92em; }
  .order-head .total { margin-left: auto; font-weight: 600; color: var(--text); }
  .badge {
    display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.78em;
    font-weight: 600; background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  }
  .badge-warn { background: var(--accent-soft); color: var(--accent); border-color: transparent; }
  .order-link { font-size: 0.85em; margin: 2px 0 14px; }
  .order-link a { color: var(--accent); text-decoration: none; }
  .order-link a:hover { text-decoration: underline; }
  .summary-table { margin: 4px 0 16px; max-width: 320px; }
  .summary-table td { padding: 2px 10px 2px 0; font-size: 0.9em; }
  .summary-table td.num { padding-right: 0; }
  .summary-table tr.total td { font-weight: 600; border-top: 1px solid var(--border); padding-top: 5px; }
  .items-table th, .items-table td { padding: 7px 10px; border-bottom: 1px solid var(--border); font-size: 0.9em; vertical-align: top; }
  .items-table th { text-align: left; color: var(--muted); font-weight: 600; }
  .items-table tr:last-child td { border-bottom: none; }
  .item-name .tag { margin-left: 6px; }
  .tag {
    display: inline-block; padding: 1px 7px; border-radius: 6px; font-size: 0.74em;
    background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  }
  .strike { text-decoration: line-through; color: var(--muted); margin-right: 4px; }
  .no-detail { color: var(--muted); font-style: italic; font-size: 0.92em; margin: 4px 0 0; }
  .item-number { color: var(--muted); font-size: 0.85em; }
  .section-title { font-size: 1.05em; margin: 0 0 10px; }
  .monthly-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    overflow-x: auto; margin-bottom: 8px; }
  .monthly-table th, .monthly-table td { padding: 7px 12px; border-bottom: 1px solid var(--border);
    font-size: 0.9em; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .monthly-table th { color: var(--muted); font-weight: 600; background: var(--bg); }
  .monthly-table th:first-child, .monthly-table td:first-child { text-align: left; }
  .monthly-table td.zero { color: var(--muted); }
  .monthly-table tr.totals td { font-weight: 700; border-top: 2px solid var(--border); border-bottom: none;
    background: var(--bg); }
  .monthly-note { color: var(--muted); font-size: 0.8em; margin: 0 0 32px; }
</style>

"""

/// Python's html.escape(str(value)), with nil -> "".
func esc(_ value: String?) -> String {
    guard let value else { return "" }
    return value
        .replacingOccurrences(of: "&", with: "&amp;")
        .replacingOccurrences(of: "<", with: "&lt;")
        .replacingOccurrences(of: ">", with: "&gt;")
        .replacingOccurrences(of: "\"", with: "&quot;")
        .replacingOccurrences(of: "'", with: "&#x27;")
}

/// "1234.5" -> "$1,234.50"; unparseable -> "$<raw>"; nil/empty -> "—".
public func fmtMoney(_ value: String?) -> String {
    guard let value, !value.isEmpty else { return "—" }
    guard let amount = pyFloat(value) else { return "$" + esc(value) }
    return (amount < 0 ? "-" : "") + "$" + pyCommaFixed2(abs(amount))
}

func renderSummaryTable(_ summary: OrderedStrings) -> String {
    if summary.isEmpty { return "" }
    var rows: [String] = []
    for (key, label) in [("subtotal", "Subtotal"), ("delivery", "Delivery"), ("tax", "Tax"),
                         ("insiders_discount", "LEGO Insiders discount"), ("discount", "Discount")]
    where summary.contains(key) {
        rows.append("<tr><td>\(esc(label))</td><td class=\"num\">\(fmtMoney(summary[key]))</td></tr>")
    }
    if summary.contains("total") {
        rows.append("<tr class=\"total\"><td>Total</td><td class=\"num\">\(fmtMoney(summary["total"]))</td></tr>")
    }
    if rows.isEmpty { return "" }
    return "<table class=\"summary-table\">\(rows.joined())</table>"
}

func renderItemRow(_ item: LegoOrderLine) -> String {
    var tags: [String] = []
    if item.isPiece { tags.append("piece") }
    if item.isGiftCard { tags.append("gift card") }
    if item.isFreeGift { tags.append("free gift") }
    let tagsHTML = tags.map { "<span class=\"tag\">\(esc($0))</span>" }.joined()

    var numberBits: [String] = []
    if let n = item.itemNumber, !n.isEmpty { numberBits.append(esc(n)) }
    if let c = item.customID, !c.isEmpty { numberBits.append("ID: \(esc(c))") }
    let itemNumberHTML = numberBits.isEmpty ? "—" : numberBits.joined(separator: " &middot; ")

    let regular = item.regularPrice, sale = item.salePrice
    let priceHTML: String
    if let r = regular, let s = sale, r != s {
        priceHTML = "<span class=\"strike\">\(fmtMoney(r))</span>\(fmtMoney(s))"
    } else {
        priceHTML = fmtMoney(sale ?? regular)
    }

    return "<tr>"
        + "<td class=\"item-name\">\(esc(item.name))\(tagsHTML)</td>"
        + "<td class=\"item-number\">\(itemNumberHTML)</td>"
        + "<td class=\"num\">\(item.quantity.map(String.init) ?? "—")</td>"
        + "<td class=\"num\">\(priceHTML)</td>"
        + "<td>\(esc(item.status))</td>"
        + "<td>\(esc(item.trackingNumber))</td>"
        + "</tr>"
}

func renderOrderSection(_ order: LegoOrder, anchor: String) -> String {
    let itemsHTML: String
    if !order.items.isEmpty {
        itemsHTML = "<table class=\"items-table\"><thead><tr>"
            + "<th>Item</th><th>Item #</th><th>Qty</th><th>Price</th>"
            + "<th>Status</th><th>Tracking #</th>"
            + "</tr></thead><tbody>"
            + order.items.map(renderItemRow).joined()
            + "</tbody></table>"
    } else {
        itemsHTML = "<p class=\"no-detail\">No item detail fetched for this order yet.</p>"
    }
    return "<section class=\"order\" id=\"\(esc(anchor))\">"
        + "<div class=\"order-head\">"
        + "<h2>\(esc(order.orderNumber))</h2>"
        + "<span class=\"badge\">\(esc(order.status))</span>"
        + "<span class=\"date\">\(esc(order.orderDate))</span>"
        + "<span class=\"total\">\(fmtMoney(order.total))</span>"
        + "</div>"
        + "<p class=\"order-link\"><a href=\"\(esc(order.url))\" target=\"_blank\" rel=\"noopener\">View on LEGO.com &rarr;</a></p>"
        + renderSummaryTable(order.summary)
        + itemsHTML
        + "</section>"
}

/// Years-by-months grid of money spent, with a Total row. Orders with no readable date or
/// total are counted in a note under the table.
func renderMonthlySpendingTable(_ orders: [LegoOrder]) -> String {
    var amounts: [Int: [Int: Double]] = [:]  // year -> month -> dollars
    var firstSeen: [(Int, Int)] = []         // (year, month) in first-seen order, like a Python dict
    var skipped = 0
    for o in orders {
        let d = parseOrderDate(o.orderDate)
        let amount = pyFloat((o.total ?? "None").replacingOccurrences(of: ",", with: ""))
        guard let d, let amount else { skipped += 1; continue }
        if amounts[d.year]?[d.month] == nil { firstSeen.append((d.year, d.month)) }
        amounts[d.year, default: [:]][d.month, default: 0.0] += amount
    }
    guard let minYear = amounts.keys.min(), let maxYear = amounts.keys.max() else { return "" }
    let years = Array(minYear...maxYear)
    let head = "<th>Month</th>" + years.map { "<th>\($0)</th>" }.joined()

    var rows: [String] = []
    for (idx, name) in monthNames.enumerated() {
        let cells = years.map { y -> String in
            if let v = amounts[y]?[idx + 1] { return "<td>\(fmtMoney(pyFixed2(v)))</td>" }
            return "<td class=\"zero\">—</td>"
        }
        rows.append("<tr><td>\(name)</td>\(cells.joined())</tr>")
    }
    let totals = years.map { y -> String in
        // Add in first-seen order, exactly like Python's sum() over the dict, so rounding matches.
        let total = firstSeen.filter { $0.0 == y }.map { amounts[y]![$0.1]! }.reduce(0.0, +)
        return "<td>" + fmtMoney(pyFixed2(total)) + "</td>"
    }.joined()
    rows.append("<tr class=\"totals\"><td>Total</td>\(totals)</tr>")

    let note = skipped > 0
        ? "<p class=\"monthly-note\">\(skipped) order(s) with no readable date or total are not included in this table.</p>"
        : "<p class=\"monthly-note\">Based on each order's total, by the month it was placed.</p>"

    return "<h2 class=\"section-title\">Spending by month</h2>\n"
        + "<div class=\"monthly-wrap\"><table class=\"monthly-table\">"
        + "<thead><tr>\(head)</tr></thead><tbody>\(rows.joined())</tbody></table></div>\n"
        + note
}

/// "%B %d, %Y at %I:%M %p", e.g. "November 06, 2026 at 10:24 AM".
func generatedTimestamp(_ date: Date = Date()) -> String {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.dateFormat = "MMMM dd, yyyy 'at' hh:mm a"
    return f.string(from: date)
}

/// A complete self-contained HTML document listing every order and its items.
public func renderOrdersHTML(_ orders: [LegoOrder], title: String = "LEGO Order History", now: Date = Date()) -> String {
    let totalOrders = orders.count
    let withItems = orders.filter { !$0.items.isEmpty }.count
    let totalItems = orders.reduce(0) { $0 + $1.items.count }
    // Same as Python's float(o.total): a total with a thousands comma doesn't parse and isn't counted.
    let totalSpent = orders.compactMap { pyFloat($0.total) }.reduce(0.0, +)

    var indexRows: [String] = []
    var sections: [String] = []
    for order in orders {
        let anchor = "order-\(order.orderNumber)"
        let detailNote = order.items.isEmpty ? " <span class=\"badge badge-warn\">no detail</span>" : ""
        indexRows.append("<tr>"
            + "<td><a href=\"#\(esc(anchor))\">\(esc(order.orderNumber))</a></td>"
            + "<td>\(esc(order.orderDate))</td>"
            + "<td>\(esc(order.status))</td>"
            + "<td class=\"num\">\(fmtMoney(order.total))</td>"
            + "<td>\(order.items.count) item(s)\(detailNote)</td>"
            + "</tr>")
        sections.append(renderOrderSection(order, anchor: anchor))
    }

    let stats = [(String(totalOrders), "Orders"), (String(withItems), "With item detail"),
                 (String(totalItems), "Total items"), ("$" + pyCommaFixed2(totalSpent), "Total spent")]
        .map { "<div class=\"stat\"><div class=\"n\">\(esc($0.0))</div><div class=\"l\">\(esc($0.1))</div></div>" }
        .joined()

    return "<!doctype html>\n"
        + "<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        + "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        + "<title>\(esc(title))</title>\n" + htmlStyle + "</head>\n<body>\n"
        + "<div class=\"wrap\">\n"
        + "<h1>\(esc(title))</h1>\n"
        + "<p class=\"generated\">Generated \(esc(generatedTimestamp(now)))</p>\n"
        + "<div class=\"stats\">\(stats)</div>\n"
        + renderMonthlySpendingTable(orders)
        + "\n<table class=\"index-table\"><thead><tr>"
        + "<th>Order</th><th>Date</th><th>Status</th><th>Total</th><th>Items</th>"
        + "</tr></thead><tbody>\(indexRows.joined())</tbody></table>\n"
        + sections.joined(separator: "\n")
        + "\n</div>\n</body>\n</html>\n"
}

/// Write the HTML report atomically.
public func writeHTMLReport(_ orders: [LegoOrder], to url: URL, includeTracking: Bool = true) throws {
    let orders = dedupeOrders(orders)
    try atomicWrite(url, text: renderOrdersHTML(includeTracking ? orders : withoutTracking(orders)))
}
