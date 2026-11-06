import Foundation

/// A calendar date with no time or time zone (like Python's datetime.date).
public struct SimpleDate: Comparable, Hashable, CustomStringConvertible {
    public let year: Int, month: Int, day: Int

    public init(year: Int, month: Int, day: Int) { self.year = year; self.month = month; self.day = day }

    /// nil when the day doesn't exist (e.g. February 30).
    public static func valid(year: Int, month: Int, day: Int) -> SimpleDate? {
        guard year >= 1, year <= 9999, (1...12).contains(month), day >= 1, day <= daysIn(month: month, year: year)
        else { return nil }
        return SimpleDate(year: year, month: month, day: day)
    }

    static func daysIn(month: Int, year: Int) -> Int {
        switch month {
        case 2: return (year % 4 == 0 && year % 100 != 0) || year % 400 == 0 ? 29 : 28
        case 4, 6, 9, 11: return 30
        default: return 31
        }
    }

    public static func < (a: SimpleDate, b: SimpleDate) -> Bool {
        (a.year, a.month, a.day) < (b.year, b.month, b.day)
    }

    /// MM/DD/YYYY
    public var description: String { String(format: "%02d/%02d/%04d", month, day, year) }

    public init(_ date: Date, calendar: Calendar = .current) {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        self.init(year: c.year!, month: c.month!, day: c.day!)
    }

    public func toDate(calendar: Calendar = .current) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day))!
    }
}

public let monthNames = ["January", "February", "March", "April", "May", "June", "July",
                         "August", "September", "October", "November", "December"]

private let dayPattern = "(3[01]|[12]\\d|0[1-9]|[1-9]| [1-9])"

/// Parse LEGO's order date ("September 7, 2026"); nil if it can't be parsed.
/// Same rules as Python's strptime(date_str, "%B %d, %Y").
public func parseOrderDate(_ s: String?) -> SimpleDate? {
    guard let s, !s.isEmpty else { return nil }
    let months = monthNames.joined(separator: "|")
    guard let g = Rx.match("^(\(months))\\s+\(dayPattern),\\s+(\\d\\d\\d\\d)$", s, caseInsensitive: true),
          let m = g[1], let d = g[2], let y = g[3],
          let mi = monthNames.firstIndex(where: { $0.lowercased() == m.lowercased() }),
          let di = Int(pyStrip(d)), let yi = Int(y)
    else { return nil }
    return SimpleDate.valid(year: yi, month: mi + 1, day: di)
}

public enum SinceDateError: Error, CustomStringConvertible {
    case invalid(String)
    public var description: String {
        if case let .invalid(v) = self { return "invalid date '\(v)' -- expected MM/DD/YYYY, e.g. 01/31/2026 (or 'all')" }
        return ""
    }
}

/// Parse a since-date setting: MM/DD/YYYY, or "all" / "none" / blank for no cutoff (nil).
public func parseSinceDate(_ value: String) throws -> SimpleDate? {
    if ["all", "none", ""].contains(pyStrip(value).lowercased()) { return nil }
    guard let g = Rx.match("^(1[0-2]|0[1-9]|[1-9])/\(dayPattern)/(\\d\\d\\d\\d)$", value),
          let m = Int(g[1]!), let d = Int(pyStrip(g[2]!)), let y = Int(g[3]!),
          let date = SimpleDate.valid(year: y, month: m, day: d)
    else { throw SinceDateError.invalid(value) }
    return date
}

/// True only when the order's date parses AND is earlier than `since`.
/// Unparseable dates are never skipped ("fetch it anyway").
public func isBeforeSinceDate(_ order: LegoOrder, _ since: SimpleDate?) -> Bool {
    guard let since, let d = parseOrderDate(order.orderDate) else { return false }
    return d < since
}
