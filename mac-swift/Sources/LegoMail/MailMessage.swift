import Foundation

// A small, dependency-free email reader: enough of RFC 5322 (headers) and MIME (multipart
// bodies, base64 / quoted-printable, charsets, =?utf-8?...?= encoded headers) to get the
// text out of an order email. Attachments and images are skipped.
//
// Trick used throughout: raw message bytes are held as an ISO-8859-1 ("Latin-1") String.
// Latin-1 maps every byte 0-255 to exactly one character, so the bytes can be split and
// searched as text and turned back into the identical bytes before charset decoding.

/// The parts of one email this app needs.
public struct MailMessage {
    /// Header (lowercased name, unfolded raw value) pairs, in file order.
    public var headers: [(name: String, value: String)] = []
    /// Every text/plain part, decoded, joined with blank lines.
    public var plainText: String = ""
    /// Every text/html part, decoded (still HTML), joined.
    public var htmlText: String = ""
    /// PDF attachments (e.g. LEGO Shop receipts), as (file name, bytes). In Mail's .partial.emlx
    /// files the bytes are stored separately: see `externalAttachments(forMailFile:)`.
    public var pdfAttachments: [(name: String, data: Data)] = []

    public init() {}

    /// First header with this name, with =?charset?...?= words decoded.
    public func header(_ name: String) -> String? {
        let n = name.lowercased()
        return headers.first { $0.name == n }.map { decodeEncodedWords($0.value).trimmed }
    }

    public var subject: String { header("Subject") ?? "" }
    public var from: String { header("From") ?? "" }
    /// The bare address from From ("LEGO Shop <noreply@e.lego.com>" -> "noreply@e.lego.com").
    public var fromAddress: String { emailAddress(in: from) }
    public var messageID: String? { header("Message-ID")?.trimmingCharacters(in: CharacterSet(charactersIn: "<> ")) }
    public var date: Date? { header("Date").flatMap(parseMailDate) }

    /// The body as plain text: the text/plain part, or the HTML part converted to text.
    public var bodyText: String { plainText.trimmed.isEmpty ? htmlToText(htmlText) : plainText }
}

// MARK: Reading files

public enum MailFileKind { case emlx, eml, mbox }

/// Which kind of mail file a path is, or nil if it isn't one.
/// Mail's own store holds ".emlx" (and ".partial.emlx", same format). Exports are ".eml" or an
/// ".mbox" folder holding a file named "mbox" (or a single ".mbox" file).
public func mailFileKind(_ url: URL) -> MailFileKind? {
    let name = url.lastPathComponent.lowercased()
    if name.hasSuffix(".emlx") { return .emlx }
    if name.hasSuffix(".eml") { return .eml }
    if name == "mbox" || name.hasSuffix(".mbox") { return .mbox }
    return nil
}

/// The raw RFC 822 messages in a file (one, except for mbox files).
public func rawMessages(in data: Data, kind: MailFileKind) -> [Data] {
    switch kind {
    case .eml: return [data]
    case .emlx: return [emlxMessageData(data)]
    case .mbox: return splitMbox(data)
    }
}

/// An .emlx file is: a line with the message's length in bytes, the message, then an XML
/// property list of Mail's flags. Returns just the message.
public func emlxMessageData(_ data: Data) -> Data {
    let bytes = [UInt8](data.prefix(32))
    guard let nl = bytes.firstIndex(of: 0x0A),
          let count = Int(String(decoding: bytes[0..<nl], as: UTF8.self).trimmed), count > 0
    else { return data }  // not the usual layout: treat the whole file as the message
    let start = data.startIndex + nl + 1
    let end = min(data.endIndex, start + count)
    return data.subdata(in: start..<end)
}

/// Split an mbox file into messages. Each starts with a "From " line, which is dropped;
/// ">From " lines that mbox writers escaped are put back.
public func splitMbox(_ data: Data) -> [Data] {
    let text = latin1(data).replacingOccurrences(of: "\r\n", with: "\n")
    var messages: [String] = []
    var current: [Substring] = []
    var started = false
    for line in text.split(separator: "\n", omittingEmptySubsequences: false) {
        if line.hasPrefix("From ") {
            if started { messages.append(current.joined(separator: "\n")) }
            current = []
            started = true
            continue
        }
        if started { current.append(line.hasPrefix(">From ") ? line.dropFirst() : line) }
    }
    if started { messages.append(current.joined(separator: "\n")) }
    if !started && !text.trimmed.isEmpty { messages = [text] }  // no "From " lines: one plain message
    return messages.map(latin1Data)
}

// MARK: Parsing

/// Only the headers (fast: used to skip the many non-LEGO emails without decoding bodies).
public func parseMailHeaders(_ data: Data) -> MailMessage {
    var m = MailMessage()
    let (head, _) = splitHeadBody(latin1(data.prefix(64 * 1024)).replacingOccurrences(of: "\r\n", with: "\n"))
    m.headers = parseHeaderBlock(head)
    return m
}

/// The full message: headers plus every text part.
public func parseMail(_ data: Data) -> MailMessage {
    var m = MailMessage()
    let raw = latin1(data).replacingOccurrences(of: "\r\n", with: "\n")
    let (head, body) = splitHeadBody(raw)
    m.headers = parseHeaderBlock(head)
    var parts = CollectedParts()
    collectText(headers: m.headers, body: body, into: &parts, depth: 0)
    m.plainText = parts.plain.joined(separator: "\n\n")
    m.htmlText = parts.html.joined(separator: "\n")
    m.pdfAttachments = parts.pdfs
    return m
}

private func splitHeadBody(_ raw: String) -> (String, String) {
    if let r = raw.range(of: "\n\n") { return (String(raw[..<r.lowerBound]), String(raw[r.upperBound...])) }
    return (raw, "")
}

/// "Name: value" lines, with continuation lines (starting with a space or tab) joined on.
func parseHeaderBlock(_ head: String) -> [(name: String, value: String)] {
    var result: [(name: String, value: String)] = []
    for line in head.components(separatedBy: "\n") {
        if let first = line.first, first == " " || first == "\t" {
            if !result.isEmpty { result[result.count - 1].value += " " + line.trimmed }
            continue
        }
        guard let colon = line.firstIndex(of: ":") else { continue }
        let name = line[..<colon].trimmed.lowercased()
        guard !name.isEmpty, !name.contains(" ") else { continue }
        result.append((name: name, value: rawHeaderText(String(line[line.index(after: colon)...]).trimmed)))
    }
    return result
}

/// Header bytes are usually ASCII, but some senders put raw UTF-8 in them.
private func rawHeaderText(_ latin1Value: String) -> String {
    guard latin1Value.unicodeScalars.contains(where: { $0.value > 127 }) else { return latin1Value }
    return String(data: latin1Data(latin1Value), encoding: .utf8) ?? latin1Value
}

/// Content-Type or Content-Disposition: "text/html; charset=UTF-8" -> ("text/html", ["charset": "UTF-8"]).
func parseParams(_ value: String) -> (String, [String: String]) {
    var parts: [String] = []
    var current = ""
    var inQuotes = false
    for ch in value {
        if ch == "\"" { inQuotes.toggle(); continue }
        if ch == ";" && !inQuotes { parts.append(current); current = ""; continue }
        current.append(ch)
    }
    parts.append(current)
    let main = (parts.first ?? "").trimmed.lowercased()
    var params: [String: String] = [:]
    for p in parts.dropFirst() {
        guard let eq = p.firstIndex(of: "=") else { continue }
        params[p[..<eq].trimmed.lowercased()] = p[p.index(after: eq)...].trimmed
    }
    return (main, params)
}

private func headerValue(_ headers: [(name: String, value: String)], _ name: String) -> String? {
    headers.first { $0.name == name }?.value
}

private struct CollectedParts {
    var plain: [String] = []
    var html: [String] = []
    var pdfs: [(name: String, data: Data)] = []
}

private func collectText(headers: [(name: String, value: String)], body: String,
                         into parts: inout CollectedParts, depth: Int) {
    guard depth < 12 else { return }
    let (type, params) = parseParams(headerValue(headers, "content-type") ?? "text/plain")
    let (disposition, dispParams) = parseParams(headerValue(headers, "content-disposition") ?? "")
    let fileName = decodeEncodedWords(dispParams["filename"] ?? dispParams["filename*"].map(decodeRFC2231)
                                      ?? params["name"] ?? "").trimmed

    if type.hasPrefix("multipart/"), let boundary = params["boundary"], !boundary.isEmpty {
        for part in splitMultipart(body, boundary: boundary) {
            let (h, b) = splitHeadBody(part)
            // A part that starts with a blank line has no headers.
            let partHeaders = part.hasPrefix("\n") ? [] : parseHeaderBlock(h)
            let partBody = part.hasPrefix("\n") ? String(part.dropFirst()) : b
            collectText(headers: partHeaders, body: partBody, into: &parts, depth: depth + 1)
        }
        return
    }
    if type == "message/rfc822" {  // a forwarded email attached whole
        let (h, b) = splitHeadBody(decodeTransfer(body, headerValue(headers, "content-transfer-encoding")).latin1String)
        collectText(headers: parseHeaderBlock(h), body: b, into: &parts, depth: depth + 1)
        return
    }
    if type == "application/pdf" || fileName.lowercased().hasSuffix(".pdf") {
        // Empty in a .partial.emlx: Mail keeps the file in its Attachments folder instead.
        let bytes = decodeTransfer(body, headerValue(headers, "content-transfer-encoding"))
        if !bytes.isEmpty { parts.pdfs.append((name: fileName.isEmpty ? "attachment.pdf" : fileName, data: bytes)) }
        return
    }
    guard type == "text/plain" || type == "text/html", disposition != "attachment" else { return }
    let bytes = decodeTransfer(body, headerValue(headers, "content-transfer-encoding"))
    let text = decodeCharset(bytes, params["charset"])
    if type == "text/html" { parts.html.append(text) } else { parts.plain.append(text) }
}

/// RFC 2231 file names: "utf-8''LEGO%C2%AE%20Receipt.pdf" -> "LEGO® Receipt.pdf".
func decodeRFC2231(_ s: String) -> String {
    let pieces = s.components(separatedBy: "'")
    guard pieces.count >= 3 else { return s.removingPercentEncoding ?? s }
    let value = pieces[2...].joined(separator: "'")
    return value.removingPercentEncoding ?? value
}

/// PDFs that Mail saved outside a message file. For ".../Messages/12345.partial.emlx", Mail keeps
/// the attachments in ".../Attachments/12345/<part>/<file name>".
public func externalAttachments(forMailFile file: URL) -> [(name: String, data: Data)] {
    let id = file.lastPathComponent.components(separatedBy: ".").first ?? ""
    guard !id.isEmpty else { return [] }
    let folder = file.deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("Attachments", isDirectory: true).appendingPathComponent(id, isDirectory: true)
    guard let e = FileManager.default.enumerator(at: folder, includingPropertiesForKeys: nil) else { return [] }
    var found: [(name: String, data: Data)] = []
    var paths: [URL] = []
    for case let url as URL in e where url.pathExtension.lowercased() == "pdf" { paths.append(url) }
    for url in paths.sorted(by: { $0.path < $1.path }) {
        if let data = try? Data(contentsOf: url), !data.isEmpty { found.append((name: url.lastPathComponent, data: data)) }
    }
    return found
}

/// The parts between "--boundary" lines (the preamble and the epilogue are dropped).
func splitMultipart(_ body: String, boundary: String) -> [String] {
    let open = "--" + boundary, close = "--" + boundary + "--"
    var parts: [String] = []
    var current: [Substring] = []
    var inPart = false
    for line in body.split(separator: "\n", omittingEmptySubsequences: false) {
        let l = line.trimmingCharacters(in: .whitespaces)
        if l == close {
            if inPart { parts.append(current.joined(separator: "\n")) }
            return parts
        }
        if l == open {
            if inPart { parts.append(current.joined(separator: "\n")) }
            current = []
            inPart = true
            continue
        }
        if inPart { current.append(line) }
    }
    if inPart { parts.append(current.joined(separator: "\n")) }  // missing closing line
    return parts
}

// MARK: Decoding

/// Undo Content-Transfer-Encoding. Returns the raw bytes.
func decodeTransfer(_ body: String, _ encoding: String?) -> Data {
    switch (encoding ?? "").trimmed.lowercased() {
    case "base64":
        let compact = body.filter { !$0.isWhitespace }
        return Data(base64Encoded: compact, options: .ignoreUnknownCharacters)
            ?? Data(base64Encoded: compact + String(repeating: "=", count: (4 - compact.count % 4) % 4),
                    options: .ignoreUnknownCharacters)
            ?? Data()
    case "quoted-printable":
        return decodeQuotedPrintable(body, underscoreIsSpace: false)
    default:
        return latin1Data(body)
    }
}

/// Quoted-printable: "=XX" is a byte in hex; "=" at a line end joins the lines.
/// (In headers, Q-encoding also uses "_" for a space.)
func decodeQuotedPrintable(_ s: String, underscoreIsSpace: Bool) -> Data {
    var out = [UInt8]()
    let b = Array(latin1Data(s))
    var i = 0
    func hex(_ c: UInt8) -> UInt8? {
        switch c {
        case 0x30...0x39: return c - 0x30
        case 0x41...0x46: return c - 0x41 + 10
        case 0x61...0x66: return c - 0x61 + 10
        default: return nil
        }
    }
    while i < b.count {
        let c = b[i]
        if c == UInt8(ascii: "=") {
            // Soft line break: "=" then optional trailing spaces, then a newline.
            var j = i + 1
            while j < b.count, b[j] == 0x20 || b[j] == 0x09 { j += 1 }
            if j < b.count, b[j] == 0x0A { i = j + 1; continue }
            if j >= b.count { break }
            if i + 2 < b.count, let h = hex(b[i + 1]), let l = hex(b[i + 2]) {
                out.append(h << 4 | l)
                i += 3
                continue
            }
        }
        out.append(underscoreIsSpace && c == UInt8(ascii: "_") ? 0x20 : c)
        i += 1
    }
    return Data(out)
}

/// Bytes -> String in the named charset, falling back to UTF-8 then Windows-1252.
func decodeCharset(_ data: Data, _ charset: String?) -> String {
    let name = (charset ?? "utf-8").trimmed.lowercased()
    var encoding: String.Encoding?
    switch name {
    case "utf-8", "utf8", "us-ascii", "ascii", "": encoding = .utf8
    case "iso-8859-1", "latin1", "iso_8859-1", "latin-1": encoding = .isoLatin1
    case "windows-1252", "cp1252": encoding = .windowsCP1252
    case "utf-16": encoding = .utf16
    default:
        #if canImport(Darwin)
        let cf = CFStringConvertIANACharSetNameToEncoding(name as CFString)
        if cf != kCFStringEncodingInvalidId {
            encoding = String.Encoding(rawValue: CFStringConvertEncodingToNSStringEncoding(cf))
        }
        #endif
    }
    if let encoding, let s = String(data: data, encoding: encoding) { return s }
    if let s = String(data: data, encoding: .utf8) { return s }
    return String(data: data, encoding: .windowsCP1252) ?? latin1(data)
}

/// Decode RFC 2047 words: "=?UTF-8?Q?Your_LEGO=C2=AE_order?=" -> "Your LEGO® order".
/// Spaces between two encoded words are dropped, as the standard says.
public func decodeEncodedWords(_ s: String) -> String {
    let re = MRx.compile("=\\?([^?\\s]+)\\?([BbQq])\\?([^?\\s]*)\\?=")
    let ns = s as NSString
    let matches = re.matches(in: s, range: NSRange(location: 0, length: ns.length))
    guard !matches.isEmpty else { return s }
    var out = ""
    var pos = 0
    for (n, m) in matches.enumerated() {
        let gap = ns.substring(with: NSRange(location: pos, length: m.range.location - pos))
        if !(n > 0 && gap.trimmed.isEmpty) { out += gap }
        let charset = ns.substring(with: m.range(at: 1)).split(separator: "*").first.map(String.init)
        let mode = ns.substring(with: m.range(at: 2)).uppercased()
        let payload = ns.substring(with: m.range(at: 3))
        let bytes = mode == "B"
            ? (Data(base64Encoded: payload + String(repeating: "=", count: (4 - payload.count % 4) % 4)) ?? Data())
            : decodeQuotedPrintable(payload, underscoreIsSpace: true)
        out += decodeCharset(bytes, charset)
        pos = m.range.location + m.range.length
    }
    out += ns.substring(from: pos)
    return out
}

/// "LEGO Shop <noreply@e.lego.com>" -> "noreply@e.lego.com" (lowercased).
public func emailAddress(in from: String) -> String {
    if let m = MRx.search("<([^<>@\\s]+@[^<>\\s]+)>", from), let a = m[1] { return a.lowercased() }
    if let m = MRx.search("([^\\s<>\"']+@[^\\s<>\"']+)", from), let a = m[1] { return a.lowercased() }
    return from.lowercased()
}

/// "Mon, 7 Sep 2026 10:15:00 -0400 (EDT)" -> Date. nil if it can't be read.
public func parseMailDate(_ s: String) -> Date? {
    var t = MRx.replace("\\([^)]*\\)", in: s, with: "").trimmed  // drop "(EDT)" comments
    t = MRx.replace("\\s+", in: t, with: " ")
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone(secondsFromGMT: 0)
    for format in ["EEE, d MMM yyyy HH:mm:ss Z", "d MMM yyyy HH:mm:ss Z", "EEE, d MMM yyyy HH:mm Z",
                   "d MMM yyyy HH:mm Z", "EEE, d MMM yyyy HH:mm:ss z", "d MMM yyyy HH:mm:ss z",
                   "EEE, d MMM yy HH:mm:ss Z"] {
        f.dateFormat = format
        if let d = f.date(from: t) { return d }
    }
    return nil
}

func latin1(_ data: Data) -> String { String(data: data, encoding: .isoLatin1) ?? String(decoding: data, as: UTF8.self) }
func latin1Data(_ s: String) -> Data { s.data(using: .isoLatin1) ?? Data(s.utf8) }

extension Data {
    var latin1String: String { latin1(self) }
}
