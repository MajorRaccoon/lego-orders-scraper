import XCTest
@testable import LegoMail

/// The email reader: headers, MIME parts, encodings, and Mail's file formats.
final class MailMessageTests: XCTestCase {
    func mail(_ s: String) -> MailMessage { parseMail(Data(s.utf8)) }

    func testHeadersFoldingAndEncodedWords() {
        let m = mail("""
        From: =?UTF-8?Q?LEGO=C2=AE_Shop?= <NoReply@E.Lego.com>
        Subject: =?utf-8?B?WW91ciBMRUdPwq4=?=
         =?utf-8?Q?_order_has_shipped?=
        Date: Thu, 10 Sep 2026 09:30:00 -0400 (EDT)
        Message-ID: <abc@e.lego.com>

        Body
        """)
        XCTAssertEqual(m.subject, "Your LEGO® order has shipped")
        XCTAssertEqual(m.from, "LEGO® Shop <NoReply@E.Lego.com>")
        XCTAssertEqual(m.fromAddress, "noreply@e.lego.com")
        XCTAssertEqual(m.messageID, "abc@e.lego.com")
        XCTAssertEqual(m.date, ISO8601DateFormatter().date(from: "2026-09-10T13:30:00Z"))
        XCTAssertEqual(m.plainText, "Body")
    }

    func testMultipartAlternativeQuotedPrintableAndBase64() {
        let html = Data("<p>Caf\u{E9} &amp; LEGO&reg;</p>".utf8).base64EncodedString()
        let m = mail("""
        Content-Type: multipart/alternative; boundary="b1"

        preamble
        --b1
        Content-Type: text/plain; charset=iso-8859-1
        Content-Transfer-Encoding: quoted-printable

        Caf=E9 soft=
        break
        --b1
        Content-Type: text/html; charset=utf-8
        Content-Transfer-Encoding: base64

        \(html)
        --b1
        Content-Type: text/plain
        Content-Disposition: attachment; filename="notes.txt"

        not body text
        --b1--
        epilogue
        """)
        XCTAssertEqual(m.plainText.trimmed, "Café softbreak")
        XCTAssertEqual(htmlToText(m.htmlText), "Café & LEGO®")
        XCTAssertFalse(m.plainText.contains("not body text"))
    }

    func testBodyTextFallsBackToHTML() {
        let m = mail("Content-Type: text/html\n\n<div>One</div><div>Two</div>")
        XCTAssertEqual(m.bodyText, "One\nTwo")
    }

    func testHTMLToTextPutsCellsOnTheirOwnLines() {
        let t = htmlToText("""
        <html><head><style>td{color:red}</style></head><body><!-- hidden -->
        <table><tr><td>LEGO&#174; Icons<br>Titanic</td><td>Qty:&nbsp;1</td><td>&#x24;679.99</td></tr></table>
        <script>var x = 1;</script><span>a</span><span>b</span></body></html>
        """)
        XCTAssertEqual(t, "LEGO® Icons\nTitanic\nQty: 1\n$679.99\nab")
    }

    func testEmlxAndMboxFiles() {
        let msg = "Subject: Hi\r\n\r\nBody\r\n"
        let emlx = Data("\(msg.utf8.count)\n\(msg)<?xml version=\"1.0\"?><plist/>".utf8)
        XCTAssertEqual(String(decoding: emlxMessageData(emlx), as: UTF8.self), msg)
        XCTAssertEqual(parseMail(emlxMessageData(emlx)).plainText.trimmed, "Body")

        let mbox = Data("From a@b Sat Jan  1 00:00:00 2026\nSubject: One\n\n>From the start\nFrom b@c Sun Jan  2 00:00:00 2026\nSubject: Two\n\nx\n".utf8)
        let parts = splitMbox(mbox).map(parseMail)
        XCTAssertEqual(parts.map(\.subject), ["One", "Two"])
        XCTAssertEqual(parts[0].plainText.trimmed, "From the start")

        XCTAssertEqual(mailFileKind(URL(fileURLWithPath: "/x/123.partial.emlx")), .emlx)
        XCTAssertEqual(mailFileKind(URL(fileURLWithPath: "/x/Saved.eml")), .eml)
        XCTAssertEqual(mailFileKind(URL(fileURLWithPath: "/x/LEGO.mbox/mbox")), .mbox)
        XCTAssertNil(mailFileKind(URL(fileURLWithPath: "/x/Envelope Index")))
    }

    func testForwardedMessageInsideAnEmail() {
        let m = mail("""
        Content-Type: multipart/mixed; boundary=X

        --X
        Content-Type: text/plain

        See below
        --X
        Content-Type: message/rfc822

        Subject: Inner
        Content-Type: text/plain

        Order Number: T123456789
        --X--
        """)
        XCTAssertTrue(m.plainText.contains("See below"))
        XCTAssertTrue(m.plainText.contains("Order Number: T123456789"))
    }

    func testPDFAttachments() throws {
        let pdf = Data("%PDF-1.4 fake".utf8).base64EncodedString()
        let m = mail("""
        Content-Type: multipart/mixed; boundary=X

        --X
        Content-Type: text/plain

        Receipt attached
        --X
        Content-Type: application/pdf; name="r.pdf"
        Content-Disposition: attachment; filename*=utf-8''LEGO%C2%AE%20Receipt.pdf
        Content-Transfer-Encoding: base64

        \(pdf)
        --X
        Content-Type: application/octet-stream
        Content-Disposition: attachment; filename="Other.PDF"

        raw
        --X
        Content-Type: application/pdf; name="kept-outside.pdf"
        Content-Transfer-Encoding: base64

        --X--
        """)
        XCTAssertEqual(m.pdfAttachments.map(\.name), ["LEGO® Receipt.pdf", "Other.PDF"])  // the empty one is skipped
        XCTAssertEqual(m.pdfAttachments.first?.data, Data("%PDF-1.4 fake".utf8))
        XCTAssertEqual(m.plainText.trimmed, "Receipt attached")
        XCTAssertNil(pdfText(Data("not a pdf".utf8)))

        // Mail's layout for attachments kept outside the message file.
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("lego-att-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tmp) }
        let messages = tmp.appendingPathComponent("Messages")
        let folder = tmp.appendingPathComponent("Attachments/77/2")
        try FileManager.default.createDirectory(at: messages, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try Data("pdf bytes".utf8).write(to: folder.appendingPathComponent("Receipt.pdf"))
        try Data("x".utf8).write(to: folder.appendingPathComponent("logo.png"))
        let found = externalAttachments(forMailFile: messages.appendingPathComponent("77.partial.emlx"))
        XCTAssertEqual(found.map(\.name), ["Receipt.pdf"])
        XCTAssertTrue(externalAttachments(forMailFile: messages.appendingPathComponent("78.partial.emlx")).isEmpty)
    }

    func testAccessCheck() {
        XCTAssertEqual(checkMailAccess(URL(fileURLWithPath: "/no/such/folder")), .notFound("/no/such/folder"))
        XCTAssertNil(checkMailAccess(FileManager.default.temporaryDirectory))
    }
}
