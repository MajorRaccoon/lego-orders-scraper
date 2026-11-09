import Foundation
#if canImport(PDFKit)
import PDFKit
#endif

/// The text of a PDF (e.g. a LEGO Shop receipt), page after page, one line per text line.
/// Uses macOS's built-in PDFKit. nil if it isn't a readable PDF (damaged, locked, or a scan
/// with no text in it).
public func pdfText(_ data: Data) -> String? {
    #if canImport(PDFKit)
    guard let doc = PDFDocument(data: data), !doc.isLocked else { return nil }
    var pages: [String] = []
    for i in 0..<doc.pageCount {
        if let s = doc.page(at: i)?.string, !s.trimmed.isEmpty { pages.append(s) }
    }
    let text = pages.joined(separator: "\n")
    return text.trimmed.isEmpty ? nil : text
    #else
    return nil
    #endif
}
