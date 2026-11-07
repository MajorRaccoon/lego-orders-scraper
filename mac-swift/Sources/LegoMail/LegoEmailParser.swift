import Foundation
import LegoCore

// Reads LEGO Shop emails (order confirmations, shipping and delivery notices, cancellations,
// refunds) and pulls out what the LEGO.com scraper would have found on the order's page.
//
// LEGO's email layout isn't documented and changes over time, so these rules are deliberately
// loose: they look for labels ("Item:", "Qty", "Subtotal", "Tracking number") anywhere in the
// email's text rather than at fixed positions. If an email is read wrong, turn on
// "Save matched emails for troubleshooting" in the app and adjust the rules here (each rule has
// a unit test in LegoMailTests).

/// What an email is about. Decides the order's status.
public enum LegoEmailKind: String, CaseIterable {
    case confirmation, shipped, delivered, cancelled, refunded, returned, backordered, other

    /// The status word saved for the order (same words the LEGO.com scraper uses).
    public var status: String? {
        switch self {
        case .confirmation: return "Processing"
        case .shipped: return "Shipped"
        case .delivered: return "Delivered"
        case .cancelled: return "Cancelled"
        case .refunded: return "Refunded"
        case .returned: return "Returned"
        case .backordered: return "Backordered"
        case .other: return nil
        }
    }
}

/// One LEGO order email, read.
public struct LegoEmail {
    public var orderNumber: String
    public var kind: LegoEmailKind
    public var subject: String
    /// When the email was sent (its Date header).
    public var sentDate: Date?
    /// The order date printed in the email ("September 7, 2026"), if there is one.
    public var orderDate: String?
    public var items: [LegoOrderLine]
    public var summary: OrderedStrings
    public var trackingNumbers: [String]
    /// Where the email came from (file path), for the log and troubleshooting.
    public var source: String

    public init(orderNumber: String, kind: LegoEmailKind, subject: String, sentDate: Date?, orderDate: String?,
                items: [LegoOrderLine], summary: OrderedStrings, trackingNumbers: [String], source: String) {
        self.orderNumber = orderNumber; self.kind = kind; self.subject = subject; self.sentDate = sentDate
        self.orderDate = orderDate; self.items = items; self.summary = summary
        self.trackingNumbers = trackingNumbers; self.source = source
    }
}

// MARK: Is this a LEGO order email?

/// True for an address at lego.com or one of its subdomains (e.g. e.lego.com).
public func isLegoAddress(_ address: String) -> Bool {
    guard let domain = address.split(separator: "@").last?.lowercased() else { return false }
    return domain == "lego.com" || domain.hasSuffix(".lego.com")
}

private let orderishSubject =
    "order|ship|deliver|dispatch|cancel|refund|return|on (its|the) way|tracking|track your|receipt|"
    + "confirm|purchase|package|parcel|thank(s| you) for (shopping|your)|backorder|pre-?order"

/// Cheap check on the headers alone: could this be a LEGO order email?
/// Sent by lego.com (or mentions LEGO, e.g. a forwarded copy) and the subject is about an
/// order or a delivery. Marketing emails get past this only to be dropped later because they
/// have no order number.
public func looksLikeLegoOrderEmail(_ m: MailMessage) -> Bool {
    let subject = m.subject
    guard MRx.search(orderishSubject, subject) != nil else { return false }
    if isLegoAddress(m.fromAddress) { return true }
    return MRx.search("\\bLEGO\\b", m.from + " " + subject) != nil
}

// MARK: Reading one email

/// Read one email. nil if it has no LEGO order or receipt number (e.g. a newsletter).
/// `attachmentTexts`: the text of its PDF attachments (LEGO Shop receipts), read like the body.
public func parseLegoEmail(_ m: MailMessage, source: String = "", attachmentTexts: [String] = []) -> LegoEmail? {
    let subject = m.subject
    // Read every version of the content: the HTML and plain-text bodies and any PDF receipt.
    // Use whichever one gives the most item detail (often the PDF, when there is one).
    let plain = m.plainText.trimmed.isEmpty ? "" : m.plainText
    let html = m.htmlText.isEmpty ? "" : htmlToText(m.htmlText)
    let candidates = ([html, plain] + attachmentTexts).filter { !$0.trimmed.isEmpty }
    guard let number = findOrderNumber(subject: subject, bodies: candidates)
        ?? findReceiptNumber(subject: subject, bodies: candidates) else { return nil }

    var best: (items: [LegoOrderLine], summary: OrderedStrings, text: String)?
    for text in candidates {
        let lines = cleanLines(text)
        let items = parseEmailItems(lines)
        let summary = parseEmailSummary(lines)
        let score = items.count * 10 + summary.keys.count
        let bestScore = best.map { $0.items.count * 10 + $0.summary.keys.count } ?? -1
        if score > bestScore { best = (items, summary, text) }
    }
    let text = best?.text ?? candidates.first ?? ""
    let lines = cleanLines(text)
    let allText = candidates.joined(separator: "\n")
    return LegoEmail(
        orderNumber: number,
        kind: classifyEmail(subject: subject, body: lines),
        subject: subject,
        sentDate: m.date,
        orderDate: findOrderDate(cleanLines(allText)) ?? dateInSubject(subject),
        items: best?.items ?? [],
        summary: best?.summary ?? OrderedStrings(),
        trackingNumbers: findTrackingNumbers(cleanLines(allText)),
        source: source
    )
}

/// LEGO order numbers look like "T514535382" (US store: T + 9 digits). Looks in the subject
/// first, then next to an "Order number" label, then anywhere in the body.
public func findOrderNumber(subject: String, bodies: [String]) -> String? {
    let strong = "\\b(T\\d{8,11})\\b"
    if let m = MRx.search(strong, subject, caseInsensitive: false), let n = m[1] { return n }
    let labelled = "order\\s*(?:number|no\\.?|#|id)?\\s*[:#]?\\s*(T\\d{6,12}|[A-Z]{0,3}\\d{7,14})\\b"
    for body in bodies {
        if let m = MRx.search(labelled, body), let n = m[1] { return n.uppercased() }
    }
    if let m = MRx.search(labelled, subject), let n = m[1] { return n.uppercased() }
    for body in bodies {
        if let m = MRx.search(strong, body, caseInsensitive: false), let n = m[1] { return n }
    }
    return nil
}

/// A receipt with no LEGO order number (e.g. from a LEGO Store) is saved under its receipt
/// number: "LEGO® Shop Receipt 5550002 from 11/01/2026" or "Receipt number: 5550002".
public func findReceiptNumber(subject: String, bodies: [String]) -> String? {
    let pattern = "receipt\\s*(?:number|no\\.?|#|id)?\\s*[:#]?\\s*([A-Z0-9][A-Z0-9-]{3,30})\\b"
    for text in [subject] + bodies {
        // Every "receipt ..." in the text, not just the first ("Your receipt is attached").
        for n in MRx.findAll(pattern, text) where MRx.search("\\d", n) != nil { return n.uppercased() }
    }
    return nil
}

/// True for a LEGO.com order number (T + digits), which has its own page on LEGO.com.
public func isLegoOrderNumber(_ s: String) -> Bool { MRx.search("^T\\d{6,12}$", s, caseInsensitive: false) != nil }

/// The date at the end of a subject like "LEGO® Shop Receipt 5550002 from November 1, 2026".
public func dateInSubject(_ subject: String) -> String? {
    guard let m = MRx.search("\\b(?:from|on|dated)\\s+(.+?)\\s*$", subject), let d = m[1] else { return nil }
    return normalizeDate(d)
}

/// Which kind of email this is, from its subject (or, failing that, the first lines of the body).
public func classifyEmail(subject: String, body: [String] = []) -> LegoEmailKind {
    func kind(_ s: String) -> LegoEmailKind {
        if MRx.search("cancel", s) != nil { return .cancelled }
        if MRx.search("refund", s) != nil { return .refunded }
        if MRx.search("\\breturn(ed)?\\b", s) != nil && MRx.search("return(s)? policy", s) == nil { return .returned }
        if MRx.search("\\b(has been |was |been )?delivered\\b", s) != nil
            && MRx.search("(will|to) be delivered|out for delivery", s) == nil { return .delivered }
        if MRx.search("back-?order", s) != nil { return .backordered }
        if MRx.search("ship|on (its|the) way|dispatch|out for delivery|track(ing)?\\b|package|parcel", s) != nil {
            return .shipped
        }
        if MRx.search("order|confirm|thank|receipt|received|placed|purchase", s) != nil { return .confirmation }
        return .other
    }
    let fromSubject = kind(subject)
    if fromSubject != .other { return fromSubject }
    return kind(body.prefix(15).joined(separator: " "))
}

// MARK: Money

/// An amount with a currency mark: "$679.99", "-$20.00", "US$ 5.00", "£1,234.56", "€12,99".
/// A minus counts only right next to the amount ("Titanic - $679.99" is not negative).
let moneyPattern = "(-|−)?(?:US\\$|CA\\$|C\\$|A\\$|AU\\$|NZ\\$|\\$|£|€|¥|CHF\\s?|kr\\.?\\s?)\\s?(-)?(\\d{1,3}(?:[,.\\u00A0 ]\\d{3})*(?:[.,]\\d{2})|\\d+(?:[.,]\\d{2})?)"

/// Every amount in a line, as the number text ("679.99", "-20.00"); currency marks dropped.
func amounts(in line: String) -> [String] {
    let ns = line as NSString
    return MRx.compile(moneyPattern).matches(in: line, range: NSRange(location: 0, length: ns.length)).map { m in
        let negative = m.range(at: 1).location != NSNotFound || m.range(at: 2).location != NSNotFound
        let digits = ns.substring(with: m.range(at: 3)).replacingOccurrences(of: "\u{A0}", with: "")
            .replacingOccurrences(of: " ", with: "")
        return (negative ? "-" : "") + digits
    }
}

/// "1,234.56" -> 1234.56 and "12,99" -> 12.99, for comparing amounts.
func amountValue(_ s: String) -> Double? {
    var t = s
    if let r = MRx.search("^(-?[\\d.,]*?)[.,](\\d{2})$", t), let whole = r[1], let cents = r[2] {
        t = whole.replacingOccurrences(of: ",", with: "").replacingOccurrences(of: ".", with: "") + "." + cents
    } else {
        t = t.replacingOccurrences(of: ",", with: "")
    }
    return Double(t)
}

private func isOnlyAmount(_ line: String) -> Bool {
    MRx.search("^\\s*(?:price|each|unit price|item price|total|line total|subtotal)?\\s*[:]?\\s*" + moneyPattern + "\\s*$", line) != nil
}

private func isFreeWord(_ line: String) -> Bool {
    MRx.search("^(price\\s*[:]?\\s*)?(free|free gift|complimentary|gift with purchase|-)$", line) != nil
}

// MARK: Items

/// "Item: 10316", "Item #10316", "Item No. 10316", "Product code: 10316", "Set number 10316",
/// "SKU: 6334567", "Element ID: 6334567". Text before the label (same line) can be the name.
private let itemNumberPattern =
    "^(.*?)\\b(item\\s*(?:no\\.?|number|#|code)?|product\\s*(?:code|number|no\\.?|id)|set\\s*(?:number|no\\.?|#)|sku|element\\s*(?:id|no\\.?|number))\\s*[:#]?\\s*(\\d{3,8})\\b"
private let quantityPattern = "(?:^|\\b)(?:qty|quantity)\\s*[:.]?\\s*(\\d{1,3})\\b|^x\\s?(\\d{1,3})$|^(\\d{1,3})\\s?x$"
private let customIDPattern = "^(?:custom\\s*)?id\\s*[:#]\\s*(\\S+)$"

/// Lines that are labels, prices or boilerplate, never an item's name.
private func canBeName(_ line: String) -> Bool {
    if line.count < 3 || line.count > 160 { return false }
    if isOnlyAmount(line) || isFreeWord(line) { return false }
    if MRx.search(quantityPattern, line) != nil { return false }
    if MRx.search("^(item|items|product|products|description|qty|quantity|price|prices|each|total|subtotal|status|"
                  + "your order|order summary|order details|in this (order|shipment|package)|shipped items|"
                  + "item\\(s\\)|details|amount|view (order|item)|buy again|write a review|track( (package|shipment|order))?)\\s*:?$", line) != nil {
        return false
    }
    if MRx.search("^(order\\s*(number|no\\.?|#|date)|tracking|shipping|delivery|tax|discount|sold by|ship to|"
                  + "billing|payment|estimated|carrier|delivered|shipped)\\b", line) != nil { return false }
    if statusWords.contains(line) { return false }
    return MRx.search("[A-Za-z]", line) != nil
}

/// Lines that end an item's block: the order summary has started.
private let summaryStart = "^(sub-?total|order total|grand total|total\\b|shipping|delivery|postage|tax|sales tax|estimated tax|"
    + "discount|promo|order summary|payment|billing|lego\\s*®?\\s*insiders)"

/// "LEGO Star Wars Millennium Falcon 75192" or "... (75192)" -> ("LEGO Star Wars Millennium Falcon", "75192").
func splitTrailingSetNumber(_ name: String) -> (String, String?) {
    if let m = MRx.search("^(.*?)[\\s,-]*\\((?:item\\s*#?\\s*)?(\\d{4,7})\\)$", name), let n = m[1], let num = m[2], !n.trimmed.isEmpty {
        return (n.trimmed, num)
    }
    if let m = MRx.search("^(.*?[A-Za-z].*?)[\\s,#-]+(\\d{5,7})$", name), let n = m[1], let num = m[2] {
        return (n.trimmed, num)
    }
    return (name, nil)
}

/// Read the item list out of an email's lines.
///
/// Each item is found by its item-number line ("Item: 10316"). Its name is the line just above
/// (or text before the label on the same line); quantity and prices come from the lines after
/// it, up to the next item or the order summary. If there are no item-number lines at all
/// (some shipping emails), items are found by their "Qty" lines instead.
public func parseEmailItems(_ lines: [String]) -> [LegoOrderLine] {
    // A receipt's item table ("Article Product Description Quantity Unit Price ... Net Amount").
    let tableItems = parseReceiptTableItems(lines)
    if !tableItems.isEmpty { return tableItems }

    struct Anchor { var index: Int; var nameIndex: Int; var name: String; var number: String?; var isPiece: Bool }
    var anchors: [Anchor] = []
    for (i, line) in lines.enumerated() {
        guard let m = MRx.search(itemNumberPattern, line), let label = m[2], let number = m[3] else { continue }
        let before = (m[1] ?? "").trimmed.trimmingCharacters(in: CharacterSet(charactersIn: "-–|,:( "))
        let isPiece = MRx.search("^(sku|element)", label) != nil
        if before.count >= 3, canBeName(before) {
            anchors.append(Anchor(index: i, nameIndex: i, name: before, number: number, isPiece: isPiece))
            continue
        }
        // Name: the nearest line above that looks like a name, but not past the previous item.
        let floor = max(0, (anchors.last?.index ?? -1) + 1, i - 4)
        guard let j = stride(from: i - 1, through: floor, by: -1).first(where: { canBeName(lines[$0]) }) else { continue }
        anchors.append(Anchor(index: i, nameIndex: j, name: lines[j], number: number, isPiece: isPiece))
    }
    if anchors.isEmpty {
        // Fallback: items found by their quantity line, with the name just above.
        for (i, line) in lines.enumerated() where MRx.search(quantityPattern, line) != nil {
            let floor = max(0, (anchors.last?.index ?? -1) + 1, i - 3)
            guard let j = stride(from: i - 1, through: floor, by: -1).first(where: { canBeName(lines[$0]) }) else { continue }
            anchors.append(Anchor(index: j, nameIndex: j, name: lines[j], number: nil, isPiece: false))
        }
    }

    var items: [LegoOrderLine] = []
    for (k, a) in anchors.enumerated() {
        // This item's lines: from its name to just before the next item's name (at most 10 lines).
        var end = min(lines.count, a.index + 9)
        if k + 1 < anchors.count { end = min(end, anchors[k + 1].nameIndex) }
        end = max(end, a.index + 1)

        var quantity: Int?
        var customID: String?
        var prices: [String] = []
        var free = false
        for n in a.nameIndex..<end {
            let line = lines[n]
            // The order summary starts: stop, or the tax would become this item's price.
            if n > a.index, MRx.search(summaryStart, line) != nil { break }
            if quantity == nil, let q = MRx.search(quantityPattern, line) { quantity = Int(q[1] ?? q[2] ?? q[3] ?? "") }
            if customID == nil, let c = MRx.search(customIDPattern, line) { customID = c[1] }
            if isFreeWord(line) { free = true }
            prices += amounts(in: line)
        }
        // The last amount is quantity x an earlier one: that's the line total, not a price.
        // ("$59.99 $49.99 $99.98" for 2 = regular, sale, line total.)
        if prices.count >= 2, let q = quantity, q > 1, let last = amountValue(prices[prices.count - 1]),
           prices.dropLast().contains(where: { amountValue($0).map { abs(last - $0 * Double(q)) < 0.005 } ?? false }) {
            prices.removeLast()
        }
        // "$0.00" is a free gift, like "Free".
        if !prices.isEmpty, prices.allSatisfy({ amountValue($0) == 0 }) { free = true; prices = [] }

        var name = cleanItemName(a.name).trimmed
        var number = a.number
        if number == nil { (name, number) = splitTrailingSetNumber(name) }
        let isGiftCard = MRx.search("gift ?card|e-?gift", name) != nil
        items.append(LegoOrderLine(
            name: name, itemNumber: number, customID: customID, quantity: quantity,
            prices: buildPrices(prices), isFreeGift: free && prices.isEmpty,
            isPiece: a.isPiece, isGiftCard: isGiftCard, status: nil, trackingNumber: nil))
    }
    return items
}

/// One row of a LEGO receipt's item table, all on one line:
///     Article  Product  Description                  Qty  Unit  [Discount  Net price]  Net amount
///     6487855  5008114  The Mandalorian with G GLOBAL 1  1  9.99  5.00  4.99  4.99
/// "Product" is the item number. Indented "-" lines under a row (the parts of a Minifigure
/// Factory build) aren't rows and are skipped.
private let receiptRow = "^(\\d{4,9})\\s+(\\d{3,9})\\s+(.+?)\\s+(\\d{1,4})\\s+((?:-?\\d{1,3}(?:,\\d{3})*\\.\\d{2}\\s*){2,4})$"

/// Items from a receipt's item table. Prices: the unit price is the regular price; the sale
/// price is the net price when there's a discount (4 amounts), else net amount / quantity.
public func parseReceiptTableItems(_ lines: [String]) -> [LegoOrderLine] {
    var items: [LegoOrderLine] = []
    for line in lines {
        guard let m = MRx.search(receiptRow, line), let number = m[2], let rawName = m[3],
              let q = m[4].flatMap({ Int($0) }), let money = m[5],
              MRx.search("[A-Za-z]", rawName) != nil else { continue }
        let values = money.split(separator: " ").map(String.init)
        guard let unit = values.first, let amount = values.last,
              let unitValue = amountValue(unit), let amountTotal = amountValue(amount) else { continue }
        var sale = values.count == 4 ? values[2] : String(format: "%.2f", q > 0 ? amountTotal / Double(q) : amountTotal)
        if amountValue(sale) == unitValue { sale = unit }
        let free = unitValue == 0 && amountTotal == 0
        let name = cleanItemName(rawName).trimmed
        let isGiftCard = MRx.search("gift ?card|e-?gift", name) != nil
        items.append(LegoOrderLine(
            name: name, itemNumber: number, customID: nil, quantity: q,
            prices: free ? emptyPrices() : buildPrices([unit, sale]), isFreeGift: free,
            isPiece: false, isGiftCard: isGiftCard, status: nil, trackingNumber: nil))
    }
    return items
}

/// Receipts lay out some fields as a column of labels followed by a column of values:
///     Order Date / Invoice No. / Invoice Date / Customer No.
///     06 Oct 2026 / 1357256193 / 07 Oct 2026 / 833748993
/// Returns label -> value ("order date" -> "06 Oct 2026"), labels lowercased without "LEGO" or dots.
public func labelColumnValues(_ lines: [String]) -> [String: String] {
    let label = "^(?:lego\\s+)?(?:order|invoice|receipt|customer|transaction)\\s*(?:no\\.?|number|#|date)$"
    func key(_ s: String) -> String {
        MRx.replace("\\s+", in: MRx.replace("^lego\\s+|\\.", in: s.lowercased(), with: ""), with: " ").trimmed
    }
    var result: [String: String] = [:]
    var i = 0
    while i < lines.count {
        guard MRx.search(label, lines[i]) != nil else { i += 1; continue }
        var j = i
        while j < lines.count, MRx.search(label, lines[j]) != nil { j += 1 }
        let count = j - i
        guard j + count <= lines.count else { i = j; continue }
        for n in 0..<count where result[key(lines[i + n])] == nil { result[key(lines[i + n])] = lines[j + n] }
        i = j + count
    }
    return result
}

// MARK: Summary, date, tracking

private let summaryRules: [(key: String, pattern: String)] = [
    ("subtotal", "^(?:order\\s+|merchandise\\s+|item(?:s)?\\s+)?sub-?total"),
    ("delivery", "^(?:standard\\s+|express\\s+)?(?:shipping|delivery|postage|shipping\\s*(?:&|and)\\s*handling)\\b"),
    ("tax", "^(?:estimated\\s+|sales\\s+)?(?:tax(?:es)?|vat|gst|hst)\\b"),
    ("insiders_discount", "^(?:lego\\s*®?\\s*)?insiders\\s+(?:discount|reward|savings)"),
    ("discount", "^(?:discount|promotion(?:al)?|promo(?:\\s*code)?|coupon|savings|you saved)\\b"),
    ("total", "^(?:order\\s+|grand\\s+|estimated\\s+|invoice\\s+)?total\\b(?!\\s*(?:items|savings|quantity|qty))"),
]

/// "Subtotal 26.97" (receipts often have no currency sign) -> "26.97". Only used on a line
/// that already has a summary label, so a plain number there is that label's amount.
private func bareAmount(atEndOf line: String) -> String? {
    MRx.search("\\s(-?\\d{1,3}(?:,\\d{3})*\\.\\d{2})$", line).flatMap { $0[1] }
}

/// The order's money summary (subtotal, delivery, tax, discounts, total), same keys as the
/// LEGO.com scraper. Reads "Label $1.00" and "Label" / "$1.00" layouts. "Free" delivery -> 0.00.
/// Uses the first match for each label, except Total, where the last one wins (item lines
/// above the summary sometimes have their own "Total").
public func parseEmailSummary(_ lines: [String]) -> OrderedStrings {
    var found: [String: String] = [:]
    for (i, line) in lines.enumerated() {
        for (key, pattern) in summaryRules {
            guard MRx.search(pattern, line) != nil else { continue }
            if key != "total", found[key] != nil { break }
            var value = amounts(in: line).last ?? bareAmount(atEndOf: line)
            if value == nil, MRx.search("\\bfree\\b", line) != nil { value = "0.00" }
            if value == nil, i + 1 < lines.count {
                let next = lines[i + 1]
                if isOnlyAmount(next) { value = amounts(in: next).last }
                else if MRx.search("^-?\\d{1,3}(?:,\\d{3})*\\.\\d{2}$", next) != nil { value = next }
                else if MRx.search("^free$", next) != nil { value = "0.00" }
            }
            if var v = value {
                if key.hasSuffix("discount"), !v.hasPrefix("-"), amountValue(v) != 0 { v = "-" + v }
                found[key] = v
            }
            break
        }
    }
    var result = OrderedStrings()
    for key in ["subtotal", "delivery", "tax", "insiders_discount", "discount", "total"] {
        if let v = found[key] { result[key] = v }
    }
    return result
}

/// "Order date: September 7, 2026" (or "Order placed: 09/07/2026", "Date ordered 7 Sep 2026",
/// "Purchase date: ...", "Date: ..." on a receipt)
/// -> "September 7, 2026", the format the LEGO.com scraper saves. nil if there's no such line.
public func findOrderDate(_ lines: [String]) -> String? {
    let columns = labelColumnValues(lines)
    if let d = columns["order date"].flatMap(normalizeDate) { return d }
    let labelled = "^(?:order\\s*date|date\\s*ordered|order\\s*placed(?:\\s*on)?|placed\\s*on|date\\s*placed|"
        + "(?:receipt|purchase|transaction|sale)\\s*date|date\\s*of\\s*purchase)\\s*[:]?\\s*(.*)$"
    // A bare "Date:" only counts when nothing better is there (a forwarded email's own
    // "Date:" header line would otherwise win).
    for pattern in [labelled, "^date\\s*:\\s*(.*)$"] {
        for (i, line) in lines.enumerated() {
            guard let m = MRx.search(pattern, line) else { continue }
            var value = (m[1] ?? "").trimmed
            if value.isEmpty, i + 1 < lines.count { value = lines[i + 1] }
            if let d = normalizeDate(value) { return d }
        }
        if pattern == labelled {
            // A receipt's own date column, before falling back to a bare "Date:".
            for k in ["receipt date", "transaction date", "invoice date"] {
                if let d = columns[k].flatMap(normalizeDate) { return d }
            }
        }
    }
    return nil
}

/// Many date spellings -> "September 7, 2026". nil if it isn't a date.
public func normalizeDate(_ s: String) -> String? {
    var t = MRx.replace("^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\\.?,?\\s+", in: s.trimmed, with: "")
    // Drop a time after the date: "September 7, 2026 at 10:15 AM", "09/07/2026 10:15".
    t = MRx.replace("(\\s+(at|@|\\|)\\s+.*|,?\\s+\\d{1,2}:\\d{2}.*)$", in: t, with: "")
    t = MRx.replace("\\s+", in: t, with: " ").trimmed
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone(secondsFromGMT: 0)
    f.isLenient = false
    for format in ["MMMM d, yyyy", "MMM d, yyyy", "MMM. d, yyyy", "MMMM d yyyy", "d MMMM yyyy", "d MMM yyyy",
                   "MM/dd/yyyy", "M/d/yyyy", "yyyy-MM-dd", "MM/dd/yy", "M/d/yy"] {
        f.dateFormat = format
        if let d = f.date(from: t) { return formatOrderDate(d, timeZone: TimeZone(secondsFromGMT: 0)!) }
    }
    return nil
}

/// Date -> "September 7, 2026" (in the given time zone; the Mac's own by default).
public func formatOrderDate(_ d: Date, timeZone: TimeZone = .current) -> String {
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = timeZone
    let c = cal.dateComponents([.year, .month, .day], from: d)
    return "\(monthNames[c.month! - 1]) \(c.day!), \(c.year!)"
}

/// "Tracking number: 1Z999AA10123456784", "Tracking #: 9400...", or the label on one line and
/// the number on the next. Returns each distinct number, in email order.
public func findTrackingNumbers(_ lines: [String]) -> [String] {
    var found: [String] = []
    func add(_ s: String?) {
        guard let s, s.count >= 8, MRx.search("\\d", s) != nil, !found.contains(s) else { return }
        found.append(s)
    }
    for (i, line) in lines.enumerated() {
        guard let m = MRx.search("tracking\\s*(?:number|no\\.?|#|id|code)?\\s*[:#]?\\s*([A-Z0-9]{8,40})?\\b", line) else { continue }
        if let n = m[1], MRx.search("^[A-Z0-9]+$", n, caseInsensitive: false) != nil { add(n); continue }
        if MRx.search("^tracking\\s*(?:number|no\\.?|#|id|code)?\\s*:?$", line) != nil, i + 1 < lines.count,
           let n = MRx.search("^([A-Z0-9]{8,40})$", lines[i + 1], caseInsensitive: false) {
            add(n[1])
        }
    }
    return found
}
