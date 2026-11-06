import Foundation

/// Small regex helpers that behave like Python's re.match / re.search / re.findall.
enum Rx {
    private static var cache: [String: NSRegularExpression] = [:]
    private static let lock = NSLock()

    static func compile(_ pattern: String, caseInsensitive: Bool = false) -> NSRegularExpression {
        let key = (caseInsensitive ? "i:" : "s:") + pattern
        lock.lock(); defer { lock.unlock() }
        if let r = cache[key] { return r }
        let r = try! NSRegularExpression(pattern: pattern, options: caseInsensitive ? [.caseInsensitive] : [])
        cache[key] = r
        return r
    }

    /// Groups of the first match (group 0 = whole match), or nil. Missing groups are nil.
    static func search(_ pattern: String, _ s: String, caseInsensitive: Bool = false) -> [String?]? {
        let ns = s as NSString
        guard let m = compile(pattern, caseInsensitive: caseInsensitive).firstMatch(in: s, range: NSRange(location: 0, length: ns.length))
        else { return nil }
        return (0..<m.numberOfRanges).map { m.range(at: $0).location == NSNotFound ? nil : ns.substring(with: m.range(at: $0)) }
    }

    /// Like Python re.match: the pattern must match at the start (patterns here already start with ^).
    static func match(_ pattern: String, _ s: String, caseInsensitive: Bool = false) -> [String?]? {
        search(pattern.hasPrefix("^") ? pattern : "^(?:" + pattern + ")", s, caseInsensitive: caseInsensitive)
    }

    /// Group 1 of every match (or the whole match when there are no groups).
    static func findAll(_ pattern: String, _ s: String) -> [String] {
        let ns = s as NSString
        return compile(pattern).matches(in: s, range: NSRange(location: 0, length: ns.length)).map {
            ns.substring(with: $0.numberOfRanges > 1 ? $0.range(at: 1) : $0.range)
        }
    }

    static func escape(_ s: String) -> String { NSRegularExpression.escapedPattern(for: s) }
}

/// Python's `[l.strip() for l in text.split("\n") if l.strip()]`.
func nonEmptyStrippedLines(_ text: String) -> [String] {
    text.components(separatedBy: "\n").compactMap {
        let t = pyStrip($0)
        return t.isEmpty ? nil : t
    }
}

/// Python's str.strip(): removes leading/trailing Unicode whitespace.
func pyStrip(_ s: String) -> String {
    let ws = CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "\u{1C}\u{1D}\u{1E}\u{1F}\u{85}"))
    let scalars = s.unicodeScalars
    guard let first = scalars.firstIndex(where: { !ws.contains($0) }) else { return "" }
    let last = scalars.lastIndex(where: { !ws.contains($0) })!
    return String(scalars[first...last])
}

/// Python's float(str): accepts surrounding whitespace, a sign, decimals, exponents, inf/nan.
/// Returns nil where Python would raise ValueError.
func pyFloat(_ s: String?) -> Double? {
    guard let s else { return nil }
    let t = pyStrip(s).replacingOccurrences(of: "_", with: "")
    guard !t.isEmpty else { return nil }
    let lower = t.lowercased()
    if lower.hasPrefix("0x") || lower.hasPrefix("-0x") || lower.hasPrefix("+0x") { return nil }
    guard t.unicodeScalars.allSatisfy({ CharacterSet(charactersIn: "0123456789+-.eE").contains($0) })
        || ["inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "nan", "+nan", "-nan"].contains(lower)
    else { return nil }
    return Double(t)
}

/// Python's f"{x:,.2f}".
func pyCommaFixed2(_ x: Double) -> String {
    if x.isNaN { return "nan" }
    if x.isInfinite { return x > 0 ? "inf" : "-inf" }
    let raw = String(format: "%.2f", x)
    let negative = raw.hasPrefix("-")
    let body = negative ? String(raw.dropFirst()) : raw
    let parts = body.split(separator: ".", omittingEmptySubsequences: false)
    let intPart = Array(parts[0])
    var grouped = ""
    for (n, ch) in intPart.enumerated() {
        if n > 0 && (intPart.count - n) % 3 == 0 { grouped.append(",") }
        grouped.append(ch)
    }
    return (negative ? "-" : "") + grouped + "." + parts[1]
}

/// Python's f"{x:.2f}".
func pyFixed2(_ x: Double) -> String {
    if x.isNaN { return "nan" }
    if x.isInfinite { return x > 0 ? "inf" : "-inf" }
    return String(format: "%.2f", x)
}
