import Foundation

/// Turn an HTML email into plain text, one line per block. Every table cell, paragraph, list
/// item and <br> starts a new line, so a layout like
///     <td>LEGO Icons Titanic</td><td>Qty: 1</td><td>$679.99</td>
/// comes out as three lines, the same way the order parser reads a plain-text email.
/// Pure Swift (no WebKit / AppKit), so it also works off the main thread and in tests.
public func htmlToText(_ html: String) -> String {
    guard !html.isEmpty else { return "" }
    var s = html
    // Source line breaks are just spaces in HTML.
    s = MRx.replace("[\\r\\n\\t]+", in: s, with: " ")
    // Things that never show up as text.
    for tag in ["head", "style", "script", "title", "noscript"] {
        s = MRx.replace("<\(tag)\\b[^>]*>.*?</\(tag)\\s*>", in: s, with: " ")
    }
    s = MRx.replace("<!--.*?-->", in: s, with: " ")
    // Line breaks and block edges.
    s = MRx.replace("<br\\s*/?>", in: s, with: "\n")
    s = MRx.replace("</?(p|div|tr|td|th|li|ul|ol|h[1-6]|table|tbody|thead|tfoot|section|article|header|footer|center|blockquote|hr)\\b[^>]*>",
                    in: s, with: "\n")
    // Everything else (<span>, <a>, <b>, <img>, ...) just goes away.
    s = MRx.replace("<[^>]*>", in: s, with: "")
    s = decodeHTMLEntities(s)
    return cleanLines(s).joined(separator: "\n")
}

private let namedEntities: [String: String] = [
    "nbsp": " ", "amp": "&", "lt": "<", "gt": ">", "quot": "\"", "apos": "'",
    "reg": "®", "trade": "™", "copy": "©", "ndash": "–", "mdash": "—", "hellip": "…",
    "rsquo": "’", "lsquo": "‘", "rdquo": "”", "ldquo": "“", "euro": "€", "pound": "£",
    "yen": "¥", "cent": "¢", "bull": "•", "middot": "·", "times": "×", "deg": "°",
    "shy": "", "zwnj": "", "zwj": "", "ensp": " ", "emsp": " ", "thinsp": " ",
]

/// "&amp;" -> "&", "&#174;" -> "®", "&#xAE;" -> "®". Unknown names are left as they are.
public func decodeHTMLEntities(_ s: String) -> String {
    guard s.contains("&") else { return s }
    let re = MRx.compile("&(#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});", caseInsensitive: false)
    let ns = s as NSString
    var out = ""
    var pos = 0
    for m in re.matches(in: s, range: NSRange(location: 0, length: ns.length)) {
        out += ns.substring(with: NSRange(location: pos, length: m.range.location - pos))
        let name = ns.substring(with: m.range(at: 1))
        var replacement: String?
        if name.hasPrefix("#x") || name.hasPrefix("#X") {
            replacement = scalarString(UInt32(name.dropFirst(2), radix: 16))
        } else if name.hasPrefix("#") {
            replacement = scalarString(UInt32(name.dropFirst(), radix: 10))
        } else {
            replacement = namedEntities[name] ?? namedEntities[name.lowercased()]
        }
        out += replacement ?? ns.substring(with: m.range)
        pos = m.range.location + m.range.length
    }
    out += ns.substring(from: pos)
    return out
}

/// A code point as a one-character string; nil if it isn't a valid character.
private func scalarString(_ code: UInt32?) -> String? {
    guard let code, let scalar = Unicode.Scalar(code) else { return nil }
    return String(Character(scalar))
}
