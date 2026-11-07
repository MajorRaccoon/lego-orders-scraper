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

    func testScanFindsEachLegoEmailOnce() {
        var log: [String] = []
        let result = scanMail(MailScanOptions(folder: samples, saveTextDir: tmp.appendingPathComponent("text"))) { log.append($0) }
        XCTAssertEqual(result.messagesChecked, 10)  // 6 .emlx, 3 in the mbox, 1 .eml
        XCTAssertEqual(result.emails.count, 7)  // not the newsletter, the dinner email, or the All Mail duplicate
        XCTAssertEqual(result.withoutOrderNumber, 1)  // the newsletter
        XCTAssertEqual(Set(result.emails.map(\.orderNumber)), ["T100000001", "T100000002", "T100000003", "T099999999"])
        let saved = (try? FileManager.default.contentsOfDirectory(atPath: tmp.appendingPathComponent("text").path)) ?? []
        XCTAssertEqual(saved.count, 8)  // the 7 order emails + the newsletter
        XCTAssertTrue(saved.contains { $0.hasPrefix("2026-09-10_T100000001_shipped_") })
        XCTAssertTrue(log.contains { $0.contains("7 LEGO order email(s) found") }, log.joined(separator: "\n"))
    }

    func testFullRun() throws {
        let o = MailRunOptions(mailFolder: samples, outputDir: tmp)
        let orders = try runMailImport(o)
        XCTAssertEqual(orders.map(\.orderNumber), ["T100000003", "T100000002", "T100000001", "T099999999"])

        let t1 = orders[2]
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

        let t2 = orders[1]
        XCTAssertEqual(t2.status, "Processing")  // only one of its two items was cancelled
        XCTAssertEqual(t2.orderDate, "October 2, 2026")
        XCTAssertEqual(t2.total, "62.12")
        XCTAssertEqual(t2.items.map(\.status), ["Processing", "Cancelled"])
        XCTAssertTrue(t2.items[1].isPiece)

        let t3 = orders[0]  // only a forwarded shipping email
        XCTAssertEqual(t3.status, "Shipped")
        XCTAssertEqual(t3.items.first?.trackingNumber, "9400111899223344556677")
        XCTAssertNotNil(t3.orderDate)

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
        XCTAssertEqual(fresh.map(\.orderNumber), ["T100000003", "T100000002", "T100000001"])
        XCTAssertFalse(FileManager.default.fileExists(atPath: tmp.appendingPathComponent(mailHTMLName).path))
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
