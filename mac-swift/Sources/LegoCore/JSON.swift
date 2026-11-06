import Foundation

/// A JSON value that keeps object keys in file order.
///
/// Foundation's JSON tools don't preserve key order, but the Python scraper does
/// (`json.dump` keeps dict insertion order). Keeping the order lets the Swift app
/// write files that are byte-for-byte identical to the Python version's.
public indirect enum JSONValue: Equatable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([(String, JSONValue)])

    public static func == (a: JSONValue, b: JSONValue) -> Bool {
        switch (a, b) {
        case (.null, .null): return true
        case let (.bool(x), .bool(y)): return x == y
        case let (.int(x), .int(y)): return x == y
        case let (.double(x), .double(y)): return x == y
        case let (.string(x), .string(y)): return x == y
        case let (.array(x), .array(y)): return x == y
        case let (.object(x), .object(y)):
            return x.count == y.count && zip(x, y).allSatisfy { $0.0 == $1.0 && $0.1 == $1.1 }
        default: return false
        }
    }

    public subscript(key: String) -> JSONValue? {
        if case let .object(pairs) = self { return pairs.first { $0.0 == key }?.1 }
        return nil
    }

    public var stringValue: String? { if case let .string(s) = self { return s }; return nil }

    public var intValue: Int? {
        switch self {
        case let .int(i): return i
        case let .double(d) where d.rounded() == d && abs(d) < 1e15: return Int(d)
        default: return nil
        }
    }

    /// Python's bool(value) rules.
    public var truthy: Bool {
        switch self {
        case .null: return false
        case let .bool(b): return b
        case let .int(i): return i != 0
        case let .double(d): return d != 0
        case let .string(s): return !s.isEmpty
        case let .array(a): return !a.isEmpty
        case let .object(o): return !o.isEmpty
        }
    }

    /// Python's str(value), for the rare non-string value in a string field.
    public var pythonStr: String {
        switch self {
        case .null: return "None"
        case let .bool(b): return b ? "True" : "False"
        case let .int(i): return String(i)
        case let .double(d): return String(d)
        case let .string(s): return s
        default: return JSONWriter.write(self)
        }
    }
}

// MARK: - Writer (matches Python json.dump(indent=2, ensure_ascii=False))

public enum JSONWriter {
    public static func write(_ value: JSONValue) -> String {
        var out = ""
        emit(value, indent: 0, into: &out)
        return out
    }

    private static func emit(_ v: JSONValue, indent: Int, into out: inout String) {
        switch v {
        case .null: out += "null"
        case let .bool(b): out += b ? "true" : "false"
        case let .int(i): out += String(i)
        case let .double(d): out += pythonFloatRepr(d)
        case let .string(s): out += quote(s)
        case let .array(items):
            if items.isEmpty { out += "[]"; return }
            let pad = String(repeating: " ", count: indent + 2)
            out += "[\n"
            for (n, item) in items.enumerated() {
                out += pad
                emit(item, indent: indent + 2, into: &out)
                out += n == items.count - 1 ? "\n" : ",\n"
            }
            out += String(repeating: " ", count: indent) + "]"
        case let .object(pairs):
            if pairs.isEmpty { out += "{}"; return }
            let pad = String(repeating: " ", count: indent + 2)
            out += "{\n"
            for (n, (k, item)) in pairs.enumerated() {
                out += pad + quote(k) + ": "
                emit(item, indent: indent + 2, into: &out)
                out += n == pairs.count - 1 ? "\n" : ",\n"
            }
            out += String(repeating: " ", count: indent) + "}"
        }
    }

    static func pythonFloatRepr(_ d: Double) -> String {
        if d.isNaN { return "NaN" }
        if d.isInfinite { return d > 0 ? "Infinity" : "-Infinity" }
        let s = "\(d)"  // Swift's shortest round-trip form, same digits as Python's repr
        return s
    }

    public static func quote(_ s: String) -> String {
        var out = "\""
        for u in s.unicodeScalars {
            switch u {
            case "\"": out += "\\\""
            case "\\": out += "\\\\"
            case "\n": out += "\\n"
            case "\r": out += "\\r"
            case "\t": out += "\\t"
            case "\u{08}": out += "\\b"
            case "\u{0C}": out += "\\f"
            default:
                if u.value < 0x20 {
                    out += String(format: "\\u%04x", u.value)
                } else {
                    out.unicodeScalars.append(u)
                }
            }
        }
        return out + "\""
    }
}

// MARK: - Parser (order-preserving)

public struct JSONParseError: Error, CustomStringConvertible {
    public let message: String
    public var description: String { message }
}

public enum JSONParser {
    public static func parse(_ text: String) throws -> JSONValue {
        var p = Parser(scalars: Array(text.unicodeScalars))
        p.skipWS()
        let v = try p.value()
        p.skipWS()
        if p.i != p.s.count { throw p.err("extra data after JSON value") }
        return v
    }

    private struct Parser {
        let s: [Unicode.Scalar]
        var i = 0
        init(scalars: [Unicode.Scalar]) { s = scalars }

        func err(_ m: String) -> JSONParseError { JSONParseError(message: "\(m) (at character \(i))") }

        mutating func skipWS() {
            while i < s.count, [" ", "\n", "\r", "\t"].contains(s[i]) { i += 1 }
        }

        mutating func literal(_ word: String) -> Bool {
            let w = Array(word.unicodeScalars)
            guard i + w.count <= s.count, Array(s[i..<i + w.count]) == w else { return false }
            i += w.count
            return true
        }

        mutating func value() throws -> JSONValue {
            guard i < s.count else { throw err("unexpected end of JSON") }
            switch s[i] {
            case "{": return try object()
            case "[": return try array()
            case "\"": return .string(try string())
            default:
                if literal("null") { return .null }
                if literal("true") { return .bool(true) }
                if literal("false") { return .bool(false) }
                if literal("NaN") { return .double(.nan) }
                if literal("Infinity") { return .double(.infinity) }
                if literal("-Infinity") { return .double(-.infinity) }
                return try number()
            }
        }

        mutating func object() throws -> JSONValue {
            i += 1
            var pairs: [(String, JSONValue)] = []
            skipWS()
            if i < s.count, s[i] == "}" { i += 1; return .object(pairs) }
            while true {
                skipWS()
                guard i < s.count, s[i] == "\"" else { throw err("expected a property name") }
                let k = try string()
                skipWS()
                guard i < s.count, s[i] == ":" else { throw err("expected ':'") }
                i += 1
                skipWS()
                let v = try value()
                if let idx = pairs.firstIndex(where: { $0.0 == k }) { pairs[idx].1 = v } else { pairs.append((k, v)) }
                skipWS()
                guard i < s.count else { throw err("unterminated object") }
                if s[i] == "," { i += 1; continue }
                if s[i] == "}" { i += 1; return .object(pairs) }
                throw err("expected ',' or '}'")
            }
        }

        mutating func array() throws -> JSONValue {
            i += 1
            var items: [JSONValue] = []
            skipWS()
            if i < s.count, s[i] == "]" { i += 1; return .array(items) }
            while true {
                skipWS()
                items.append(try value())
                skipWS()
                guard i < s.count else { throw err("unterminated array") }
                if s[i] == "," { i += 1; continue }
                if s[i] == "]" { i += 1; return .array(items) }
                throw err("expected ',' or ']'")
            }
        }

        mutating func hex4() throws -> UInt32 {
            guard i + 4 <= s.count else { throw err("bad \\u escape") }
            var v: UInt32 = 0
            for _ in 0..<4 {
                guard let d = Int(String(s[i]), radix: 16) else { throw err("bad \\u escape") }
                v = v * 16 + UInt32(d)
                i += 1
            }
            return v
        }

        mutating func string() throws -> String {
            i += 1
            var out = String.UnicodeScalarView()
            while true {
                guard i < s.count else { throw err("unterminated string") }
                let c = s[i]
                i += 1
                if c == "\"" { return String(out) }
                if c != "\\" { out.append(c); continue }
                guard i < s.count else { throw err("unterminated string") }
                let e = s[i]
                i += 1
                switch e {
                case "\"": out.append("\"")
                case "\\": out.append("\\")
                case "/": out.append("/")
                case "b": out.append("\u{08}")
                case "f": out.append("\u{0C}")
                case "n": out.append("\n")
                case "r": out.append("\r")
                case "t": out.append("\t")
                case "u":
                    var code = try hex4()
                    if (0xD800..<0xDC00).contains(code), i + 1 < s.count, s[i] == "\\", s[i + 1] == "u" {
                        let save = i
                        i += 2
                        let low = try hex4()
                        if (0xDC00..<0xE000).contains(low) {
                            code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                        } else {
                            i = save
                        }
                    }
                    out.append(Unicode.Scalar(code) ?? "\u{FFFD}")
                default: throw err("bad escape")
                }
            }
        }

        mutating func number() throws -> JSONValue {
            let start = i
            if i < s.count, s[i] == "-" { i += 1 }
            var isFloat = false
            while i < s.count {
                let c = s[i]
                if ("0"..."9").contains(c) { i += 1 }
                else if c == "." || c == "e" || c == "E" || ((c == "+" || c == "-") && isFloat) { isFloat = true; i += 1 }
                else { break }
            }
            let text = String(String.UnicodeScalarView(s[start..<i]))
            if text.isEmpty || text == "-" { throw err("expected a value") }
            if !isFloat, let n = Int(text) { return .int(n) }
            guard let d = Double(text) else { throw err("bad number") }
            return .double(d)
        }
    }
}
