import Foundation

/// Small regex helpers (LegoCore keeps its own copy internal, so this module has one too).
enum MRx {
    private static var cache: [String: NSRegularExpression] = [:]
    private static let lock = NSLock()

    static func compile(_ pattern: String, caseInsensitive: Bool = true) -> NSRegularExpression {
        let key = (caseInsensitive ? "i:" : "s:") + pattern
        lock.lock(); defer { lock.unlock() }
        if let r = cache[key] { return r }
        let r = try! NSRegularExpression(pattern: pattern, options: caseInsensitive ? [.caseInsensitive] : [])
        cache[key] = r
        return r
    }

    /// Groups of the first match (group 0 = whole match), or nil. Missing groups are nil.
    /// Case-insensitive by default: email layouts vary ("Order number", "ORDER NUMBER").
    static func search(_ pattern: String, _ s: String, caseInsensitive: Bool = true) -> [String?]? {
        let ns = s as NSString
        guard let m = compile(pattern, caseInsensitive: caseInsensitive)
            .firstMatch(in: s, range: NSRange(location: 0, length: ns.length)) else { return nil }
        return (0..<m.numberOfRanges).map {
            m.range(at: $0).location == NSNotFound ? nil : ns.substring(with: m.range(at: $0))
        }
    }

    /// Group 1 of every match (or the whole match when there are no groups).
    static func findAll(_ pattern: String, _ s: String, caseInsensitive: Bool = true) -> [String] {
        let ns = s as NSString
        return compile(pattern, caseInsensitive: caseInsensitive)
            .matches(in: s, range: NSRange(location: 0, length: ns.length)).map {
                ns.substring(with: $0.numberOfRanges > 1 ? $0.range(at: 1) : $0.range)
            }
    }

    static func replace(_ pattern: String, in s: String, with template: String, caseInsensitive: Bool = true) -> String {
        compile(pattern, caseInsensitive: caseInsensitive)
            .stringByReplacingMatches(in: s, range: NSRange(location: 0, length: (s as NSString).length), withTemplate: template)
    }
}

extension String {
    /// Trimmed of spaces, tabs, newlines and non-breaking spaces.
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "\u{A0}\u{200B}\u{FEFF}"))) }
}

/// The text split into trimmed, non-empty lines, with runs of spaces collapsed.
func cleanLines(_ text: String) -> [String] {
    text.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
        .components(separatedBy: "\n")
        .map { MRx.replace("[ \\t\\u00A0\\u200B\\u200C\\u200D\\uFEFF]+", in: $0, with: " ").trimmed }
        .filter { !$0.isEmpty }
}
