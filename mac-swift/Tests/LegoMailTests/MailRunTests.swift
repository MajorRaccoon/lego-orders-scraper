import LegoCore
import XCTest
@testable import LegoMail

/// End to end: read the made-up mailbox in mac-swift/sample-mail and check the files written.
/// (Regenerate the samples with `python3 sample-mail/make_sample_mail.py`.)
final class MailRunTests: XCTestCase {
    var tmp: URL!
    let samples = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("sample-mail", isDirectory: true)

    override func setUpWithError() throws {
        tmp = FileManager.default.temporaryDirectory.appendingPathComponent("lego-mail-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: tmp) }

    func testScanFindsEachLegoEmailOnce() throws {
        var log: [String] = []
        let result = scanMail(MailScanOptions(folder: samples, saveTextDir: tmp.appendingPathComponent("text"))) { log.append($0) }
        XCTAssertEqual(result.messagesChecked, 12)  // 8 .emlx, 3 in the mbox, 1 .eml
        XCTAssertEqual(result.emails.count, 9)  // not the newsletter, the dinner email, or the All Mail duplicate
        XCTAssertEqual(result.withoutOrderNumber, 1)  // the newsletter
        XCTAssertEqual(result.pdfsRead, 2)  // one inside its email, one in Mail's Attachments folder
        XCTAssertEqual(Set(result.emails.map(\.orderNumber)),
                       ["T100000001", "T100000002", "T100000003", "T100000004", "T099999999", "5550002"])
        let textDir = tmp.appendingPathComponent("text")
        let saved = (try? FileManager.default.contentsOfDirectory(atPath: textDir.path)) ?? []
        XCTAssertEqual(saved.count, 10)  // the 9 order emails + the newsletter
        XCTAssertTrue(saved.contains { $0.hasPrefix("2026-09-10_T100000001_shipped_") })
        let receiptFile = try XCTUnwrap(saved.first { $0.contains("_5550002_") })
        let receiptText = try String(contentsOf: textDir.appendingPathComponent(receiptFile))
        XCTAssertTrue(receiptText.contains("===== PDF attachment Receipt 5550002.pdf, as text ====="))
        XCTAssertTrue(receiptText.contains("LEGO Technic Lamborghini Sian"))
        XCTAssertTrue(log.contains { $0.contains("9 LEGO order email(s) found, 1 LEGO email(s) without an order number skipped, 2 PDF receipt(s) read") },
                      log.joined(separator: "\n"))
    }

    /// A receipt email whose PDF Mail never downloaded (a .partial.emlx with no Attachments
    /// folder): the run says so in the log and in the troubleshooting file.
    func testReceiptPDFNotDownloadedIsReported() throws {
        let messages = tmp.appendingPathComponent("Mail/Data/Messages")
        try FileManager.default.createDirectory(at: messages, withIntermediateDirectories: true)
        let msg = """
        From: LEGOshop.com <no-reply-billing03@lego.com>\r
        Subject: LEGO Shop  Receipt 5550009 from 06/06/2022\r
        Date: Tue, 7 Jun 2022 05:54:48 +0200\r
        Message-ID: <r9@lego.com>\r
        Content-Type: multipart/mixed; boundary="B"\r
        \r
        --B\r
        Content-Type: text/plain\r
        \r
        You'll find enclosed a copy of the invoice 5550009.\r
        --B\r
        Content-Type: application/pdf; name="5550009.pdf"\r
        Content-Disposition: attachment; filename="5550009.pdf"\r
        Content-Transfer-Encoding: base64\r
        \r
        --B--\r

        """
        let data = Data("\(msg.utf8.count)\n\(msg)<plist/>".utf8)
        try data.write(to: messages.appendingPathComponent("77.partial.emlx"))

        var log: [String] = []
        let textDir = tmp.appendingPathComponent("text")
        let result = scanMail(MailScanOptions(folder: tmp.appendingPathComponent("Mail"), saveTextDir: textDir)) { log.append($0) }
        XCTAssertEqual(result.emails.map(\.orderNumber), ["5550009"])  // the receipt number, until the PDF is there
        XCTAssertEqual(result.pdfsNotDownloaded, 1)
        XCTAssertTrue(log.contains { $0.contains("1 email(s) whose PDF receipt Mail hasn't downloaded") }, log.joined(separator: "\n"))
        XCTAssertTrue(log.contains { $0.contains("Download Attachments: All") })
        let file = try XCTUnwrap(try FileManager.default.contentsOfDirectory(atPath: textDir.path).first)
        let text = try String(contentsOf: textDir.appendingPathComponent(file))
        XCTAssertTrue(text.contains("NOTE: This email lists 5550009.pdf, but the file isn't on this Mac"), text)
    }

    /// A receipt email whose PDF Mail never downloaded, plus the same receipt saved into a folder
    /// of PDFs: one order under the real order number, with the PDF's items. A receipt-number
    /// placeholder saved by an earlier run (before the folder was used) is dropped.
    func testReceiptFolderFillsInMissingPDFs() throws {
        let mail = tmp.appendingPathComponent("Mail")
        let messages = mail.appendingPathComponent("Data/Messages")
        try FileManager.default.createDirectory(at: messages, withIntermediateDirectories: true)
        let msg = """
        From: LEGOshop.com <no-reply-billing03@lego.com>\r
        Subject: LEGO Shop  Receipt 5550001 from 10/15/2026\r
        Date: Thu, 15 Oct 2026 18:00:00 +0000\r
        Message-ID: <r1@lego.com>\r
        Content-Type: multipart/mixed; boundary="B"\r
        \r
        --B\r
        Content-Type: text/plain\r
        \r
        You'll find enclosed a copy of the invoice 5550001.\r
        --B\r
        Content-Type: application/pdf; name="Receipt.pdf"\r
        Content-Transfer-Encoding: base64\r
        \r
        --B--\r

        """
        try Data("\(msg.utf8.count)\n\(msg)<plist/>".utf8).write(to: messages.appendingPathComponent("51.partial.emlx"))
        let out = tmp.appendingPathComponent("out")

        // Without the folder: the receipt has only its receipt number, so it's left out.
        var o = MailRunOptions(mailFolder: mail, outputDir: out, makeHTML: false)
        var firstLog: [String] = []
        XCTAssertEqual(try runMailImport(o) { firstLog.append($0) }.map(\.orderNumber), [])
        XCTAssertTrue(firstLog.contains { $0.contains("Left out 1 order(s) without a LEGO.com order number (T...): 5550001.") },
                      firstLog.joined(separator: "\n"))

        // With the folder of saved PDFs.
        o.receiptFolder = samples.appendingPathComponent("receipts")
        var log: [String] = []
        let orders = try runMailImport(o) { log.append($0) }
        XCTAssertEqual(orders.map(\.orderNumber), ["T100000004"])  // the receipt joined its T order
        XCTAssertEqual(orders[0].items.map(\.itemNumber), ["10281", "76914"])
        XCTAssertEqual(orders[0].orderDate, "October 15, 2026")
        XCTAssertEqual(orders[0].total, "108.34")
        XCTAssertTrue(log.contains { $0.contains("Read 1 receipt PDF(s) from the folder") }, log.joined(separator: "\n"))
    }

    func testFullRun() throws {
        let o = MailRunOptions(mailFolder: samples, outputDir: tmp)
        var log: [String] = []
        let orders = try runMailImport(o) { log.append($0) }
        // Only T orders: the store receipt saved under its receipt number (5550002) is left out.
        XCTAssertEqual(orders.map(\.orderNumber), ["T100000003", "T100000004", "T100000002", "T100000001", "T099999999"])
        XCTAssertTrue(log.contains { $0.contains("Left out 1 order(s) without a LEGO.com order number (T...): 5550002.") },
                      log.joined(separator: "\n"))

        let t1 = orders[3]
        XCTAssertEqual(t1.status, "Delivered")
        XCTAssertEqual(t1.orderDate, "September 7, 2026")
        XCTAssertEqual(t1.total, "808.72")
        XCTAssertEqual(t1.summary.keys, ["subtotal", "delivery", "tax", "insiders_discount", "total"])
        XCTAssertEqual(t1.summary["insiders_discount"], "-20.00")
        XCTAssertEqual(t1.items.map(\.name), ["LEGO Icons Titanic", "LEGO Technic Hub", "Brick Calendar"])
        XCTAssertEqual(t1.items.map(\.status), ["Delivered", "Delivered", "Delivered"])
        XCTAssertEqual(t1.items.map(\.trackingNumber), ["1Z999AA10123456784", nil, nil])
        XCTAssertEqual(t1.items[1].salePrice, "49.99")
        XCTAssertTrue(t1.items[2].isFreeGift)

        let t2 = orders[2]
        XCTAssertEqual(t2.status, "Processing")  // only one of its two items was cancelled
        XCTAssertEqual(t2.orderDate, "October 2, 2026")
        XCTAssertEqual(t2.total, "62.12")
        XCTAssertEqual(t2.items.map(\.status), ["Processing", "Cancelled"])
        XCTAssertTrue(t2.items[1].isPiece)

        let t3 = orders[0]  // only a forwarded shipping email
        XCTAssertEqual(t3.status, "Shipped")
        XCTAssertEqual(t3.items.first?.trackingNumber, "9400111899223344556677")
        XCTAssertNotNil(t3.orderDate)

        // An online order whose details are only in its PDF receipt.
        let t4 = orders[1]
        XCTAssertEqual(t4.orderDate, "October 15, 2026")
        XCTAssertEqual(t4.status, "Processing")
        XCTAssertEqual(t4.total, "108.34")
        XCTAssertEqual(t4.summary["delivery"], "0.00")
        XCTAssertEqual(t4.items.map(\.itemNumber), ["10281", "76914"])
        XCTAssertEqual(t4.items.map(\.quantity), [1, 2])
        XCTAssertEqual(t4.items[1].regularPrice, "25.99")  // not the $51.98 line total
        XCTAssertEqual(t4.url, orderDetailURL("T100000004"))


        // Same file formats as the LEGO.com scraper.
        let saved = try loadOrders(tmp.appendingPathComponent(mailJSONName))
        XCTAssertEqual(saved, orders)
        let csv = try String(contentsOf: tmp.appendingPathComponent(mailCSVName))
        XCTAssertTrue(csv.hasPrefix(csvHeader.joined(separator: ",") + "\r\n"))
        XCTAssertTrue(csv.contains("T100000001,\"September 7, 2026\",Delivered,808.72,779.97,0.00,48.75,-20.00,,LEGO Icons Titanic,10294,"))
        XCTAssertTrue(csv.contains("1Z999AA10123456784"))
        let html = try String(contentsOf: tmp.appendingPathComponent(mailHTMLName))
        XCTAssertTrue(html.contains("LEGO Orders from Apple Mail"))
        XCTAssertTrue(html.contains("T100000002"))
    }

    func testSinceDateKeepsEarlierOrdersAndFreshDropsThem() throws {
        var o = MailRunOptions(mailFolder: samples, outputDir: tmp, makeHTML: false)
        try runMailImport(o)
        o.since = SimpleDate(year: 2026, month: 1, day: 1)
        var log: [String] = []
        let kept = try runMailImport(o) { log.append($0) }
        XCTAssertEqual(kept.map(\.orderNumber).last, "T099999999")  // kept from the first run
        XCTAssertTrue(log.contains { $0.contains("Kept 1 order(s)") })

        o.fresh = true
        let fresh = try runMailImport(o)
        XCTAssertEqual(fresh.map(\.orderNumber), ["T100000003", "T100000004", "T100000002", "T100000001"])
        XCTAssertFalse(FileManager.default.fileExists(atPath: tmp.appendingPathComponent(mailHTMLName).path))
    }

    /// Orders saved by an earlier version under a receipt number are dropped from the files.
    func testEarlierNonTOrdersAreDropped() throws {
        let jsonURL = tmp.appendingPathComponent(mailJSONName)
        let store = LegoOrder(orderNumber: "LEGO0000000001", status: "In-store purchase", orderDate: "October 25, 2024",
                              total: "85.79", itemCountListed: 1, url: ordersURL,
                              items: [LegoOrderLine(name: "Desert Skiff", itemNumber: "75396", customID: nil, quantity: 1,
                                                    prices: emptyPrices(), isFreeGift: false, isPiece: false, isGiftCard: false,
                                                    status: nil, trackingNumber: nil)])
        let online = LegoOrder(orderNumber: "T123456789", status: "Delivered", orderDate: "January 2, 2020", total: "9.99",
                               itemCountListed: 1, url: orderDetailURL("T123456789"),
                               items: store.items)
        try writeOutputs([store, online], json: jsonURL, csv: tmp.appendingPathComponent(mailCSVName), quiet: true)
        let orders = try runMailImport(MailRunOptions(mailFolder: samples, outputDir: tmp, makeHTML: false))
        XCTAssertFalse(orders.contains { $0.orderNumber == "LEGO0000000001" })
        XCTAssertTrue(orders.contains { $0.orderNumber == "T123456789" })  // earlier T orders are still kept
        XCTAssertTrue(orders.allSatisfy(isTOrder))
    }

    func testNoTrackingAndMissingFolder() throws {
        var o = MailRunOptions(mailFolder: samples, outputDir: tmp)
        o.includeTracking = false
        try runMailImport(o)
        let csv = try String(contentsOf: tmp.appendingPathComponent(mailCSVName))
        XCTAssertFalse(csv.contains("1Z999AA10123456784"))

        o.mailFolder = tmp.appendingPathComponent("nope")
        XCTAssertThrowsError(try runMailImport(o)) { XCTAssertTrue("\($0)".contains("doesn't exist")) }
    }
}
