import XCTest
@testable import LegoCore

/// Ports of lego-tests: test_persistence, test_write_outputs_summary, test_html_report, test_monthly_table.
/// (Byte-for-byte equality with Python is checked by lego-tests/tests/test_swift_parity.py.)
final class OutputTests: XCTestCase {
    var tmp: URL!

    override func setUpWithError() throws {
        tmp = FileManager.default.temporaryDirectory.appendingPathComponent("lego-swift-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: tmp) }

    func order(_ json: String) throws -> LegoOrder { try LegoOrder.fromJSON(try JSONParser.parse(json)) }

    func testPersistenceAndResume() throws {
        let full = try order("""
        {"order_number": "T1", "status": "Shipped", "order_date": "June 1, 2026", "total": "123.45",
         "item_count_listed": 2, "url": "u/T1",
         "items": [{"name": "Hub, with comma", "item_number": "88012", "quantity": 2,
                    "prices": {"product.regularPrice": "59.99", "product.salePrice": "49.99"},
                    "is_free_gift": false, "status": "Shipped", "tracking_number": "1Z1"},
                   {"name": "Gift", "item_number": "5006", "custom_id": "ID9", "quantity": 1,
                    "prices": {"product.regularPrice": null, "product.salePrice": null},
                    "is_free_gift": true, "is_piece": true, "is_gift_card": false}],
         "summary": {"subtotal": "134.98", "tax": "8.47", "insiders_discount": "-20.00", "discount": "-1.00", "total": "123.45"}}
        """)
        let empty = try order(#"{"order_number": "T2", "status": "Processing", "order_date": "July 1, 2026", "total": "5.00", "url": "u/T2"}"#)
        let fail = try order(#"{"order_number": "T3", "status": "Shipped", "url": "u/T3", "fetch_error": "timeout"}"#)
        let jp = tmp.appendingPathComponent("o.json"), cp = tmp.appendingPathComponent("o.csv")
        try writeOutputs([full, empty, fail], json: jp, csv: cp, quiet: true)

        let data = try loadOrders(jp)
        XCTAssertEqual(data.map(\.orderNumber), ["T1", "T2", "T3"])
        XCTAssertNil(data[0].fetchError); XCTAssertEqual(data[2].fetchError, "timeout")
        XCTAssertFalse(try String(contentsOf: jp).contains("\"fetch_error\": null"))

        let csv = try String(contentsOf: cp)
        let rows = csv.components(separatedBy: "\r\n").filter { !$0.isEmpty }
        XCTAssertEqual(rows[0], csvHeader.joined(separator: ","))
        XCTAssertEqual(rows.count, 3)  // header + one row per item; item-less orders add none
        XCTAssertTrue(rows[1].contains("\"Hub, with comma\""))
        XCTAssertTrue(rows[2].contains(",True,True,False,"))

        let loaded = loadExistingOrders(jp)
        XCTAssertEqual(loaded.map(\.0), ["T1"])
        XCTAssertEqual(loaded[0].1.summary["total"], "123.45")

        XCTAssertTrue(loadExistingOrders(tmp.appendingPathComponent("missing.json")).isEmpty)
        try "{not json".write(to: tmp.appendingPathComponent("bad.json"), atomically: true, encoding: .utf8)
        var msgs: [String] = []
        XCTAssertTrue(loadExistingOrders(tmp.appendingPathComponent("bad.json")) { msgs.append($0) }.isEmpty)
        XCTAssertTrue(msgs[0].contains("starting fresh"))

        // round trip is lossless
        let rj = tmp.appendingPathComponent("r.json")
        try writeOutputs(loaded.map(\.1), json: rj, csv: tmp.appendingPathComponent("r.csv"), quiet: true)
        XCTAssertEqual(try loadOrders(rj)[0], data[0])
    }

    func testAtomicWrite() throws {
        let target = tmp.appendingPathComponent("keep.txt")
        try "OLD".write(to: target, atomically: false, encoding: .utf8)
        struct Boom: Error {}
        XCTAssertThrowsError(try atomicWrite(target) { p in try "PARTIAL".write(to: p, atomically: false, encoding: .utf8); throw Boom() })
        XCTAssertEqual(try String(contentsOf: target), "OLD")
        XCTAssertFalse(FileManager.default.fileExists(atPath: target.path + ".tmp"))
        try atomicWrite(target, text: "NEW")
        XCTAssertEqual(try String(contentsOf: target), "NEW")
    }

    func testWriteOutputsSummaryMessage() throws {
        func o(_ n: String, items: Bool) throws -> LegoOrder {
            try order(#"{"order_number": "\#(n)", "status": "Shipped", "order_date": "June 1, 2026", "total": "10.00", "url": "x""#
                      + (items ? #", "items": [{"name": "W", "item_number": "1", "quantity": 1, "prices": {}, "is_free_gift": false}]}"# : "}"))
        }
        var log: [String] = []
        let all = try [o("T0", items: true), o("T1", items: true), o("T2", items: true)]
        try writeOutputs(all, json: tmp.appendingPathComponent("a.json"), csv: tmp.appendingPathComponent("a.csv")) { log.append($0) }
        XCTAssertTrue(log.joined().contains("3 order(s))."))
        log = []
        try writeOutputs(all + [o("T100", items: false), o("T101", items: false)],
                         json: tmp.appendingPathComponent("b.json"), csv: tmp.appendingPathComponent("b.csv")) { log.append($0) }
        let s = log.joined()
        XCTAssertTrue(s.contains("5 order(s) listed") && s.contains("3 of them with item detail") && s.contains("other 2 have no items yet"), s)
        log = []
        try writeOutputs(all, json: tmp.appendingPathComponent("c.json"), csv: tmp.appendingPathComponent("c.csv"), quiet: true) { log.append($0) }
        XCTAssertTrue(log.isEmpty)
    }

    func testHTMLReport() throws {
        let o1 = try order("""
        {"order_number": "T900000001", "status": "Shipped", "order_date": "June 15, 2026", "total": "123.45",
         "url": "https://www.lego.com/x",
         "items": [{"name": "Technic Hub <script>alert(\\"x\\")</script> & Friends", "item_number": "42177", "quantity": 2,
                    "prices": {"product.regularPrice": "59.99", "product.salePrice": "49.99"}, "is_free_gift": false,
                    "tracking_number": "1Z999AA10123456784"},
                   {"name": "Wrench", "item_number": "6335381", "custom_id": "abc123", "quantity": 1,
                    "prices": {"product.regularPrice": null, "product.salePrice": null}, "is_free_gift": true, "is_piece": true},
                   {"name": "LEGO Gift Card", "quantity": 1, "prices": {"product.regularPrice": "25.00", "product.salePrice": "25.00"},
                    "is_free_gift": false, "is_gift_card": true}],
         "summary": {"subtotal": "134.98", "delivery": "0.00", "tax": "8.47", "insiders_discount": "-20.00", "total": "123.45"}}
        """)
        let o2 = try order(#"{"order_number": "T900000002", "status": "Processing", "order_date": "July 1, 2026", "total": "10.00", "url": "u"}"#)
        let html = renderOrdersHTML([o1, o2], title: "Test Order History")
        XCTAssertTrue(html.hasPrefix("<!doctype html>"))
        XCTAssertTrue(html.contains("<title>Test Order History</title>"))
        XCTAssertTrue(html.contains("id=\"order-T900000001\"") && html.contains("id=\"order-T900000002\""))
        XCTAssertFalse(html.contains("<script>alert"))
        XCTAssertTrue(html.contains("&lt;script&gt;") && html.contains("&amp; Friends"))
        XCTAssertTrue(html.contains("$59.99") && html.contains("$49.99"))
        XCTAssertTrue(html.contains(">free gift<") && html.contains(">piece<") && html.contains(">gift card<"))
        XCTAssertTrue(html.contains("-$20.00") && html.contains("LEGO Insiders discount"))
        XCTAssertTrue(html.contains("No item detail fetched for this order yet.") && html.contains("no detail"))
        XCTAssertTrue(html.contains("<div class=\"n\">2</div>") && html.contains("<div class=\"n\">3</div>"))
        XCTAssertFalse(renderOrdersHTML([o2]).contains("<table class=\"summary-table\">"))

        let p = tmp.appendingPathComponent("report.html")
        try writeHTMLReport([o1, o2], to: p)
        XCTAssertTrue(try String(contentsOf: p).contains("T900000002"))
        XCTAssertFalse(FileManager.default.fileExists(atPath: p.path + ".tmp"))
    }

    func testMonthlyTable() throws {
        func o(_ n: String, _ d: String, _ t: String?) -> LegoOrder {
            LegoOrder(orderNumber: n, status: "Shipped", orderDate: d, total: t, itemCountListed: 1, url: "u")
        }
        let orders = [o("T1", "February 3, 2024", "100.00"), o("T2", "February 20, 2024", "50.50"),
                      o("T3", "December 31, 2024", "1,200.00"), o("T4", "January 5, 2026", "10.00"),
                      o("T5", "October 6, 2026", "107.23"), o("T6", "not a date", "5.00"), o("T7", "March 1, 2026", nil)]
        let html = renderOrdersHTML(orders)
        let sec = String(html[html.range(of: "class=\"section-title\"")!.lowerBound..<html.range(of: "class=\"index-table\"")!.lowerBound])
        XCTAssertTrue(sec.contains("<th>Month</th><th>2024</th><th>2025</th><th>2026</th>"))
        XCTAssertTrue(sec.contains("<tr><td>February</td><td>$150.50</td><td class=\"zero\">—</td><td class=\"zero\">—</td></tr>"))
        XCTAssertTrue(sec.contains("<tr><td>December</td><td>$1,200.00</td>"))
        XCTAssertTrue(sec.contains("<tr class=\"totals\"><td>Total</td><td>$1,350.50</td><td>$0.00</td><td>$117.23</td></tr>"))
        XCTAssertTrue(sec.contains("2 order(s) with no readable date or total"))
        XCTAssertFalse(renderOrdersHTML([]).contains("Spending by month"))
        XCTAssertFalse(renderOrdersHTML([o("T9", "garbage", "1.00")]).contains("Spending by month"))
    }

    func testJSONWriterMatchesPythonFormat() throws {
        let v = JSONValue.object([("a", .array([])), ("b", .object([])), ("c", .string("é\n\"\u{01}")), ("d", .null), ("e", .array([.int(1), .bool(true)]))])
        XCTAssertEqual(JSONWriter.write(v), "{\n  \"a\": [],\n  \"b\": {},\n  \"c\": \"é\\n\\\"\\u0001\",\n  \"d\": null,\n  \"e\": [\n    1,\n    true\n  ]\n}")
        XCTAssertEqual(try JSONParser.parse(JSONWriter.write(v)), v)
        XCTAssertEqual(try JSONParser.parse(#""\ud83e\uddf1""#), .string("🧱"))
    }
}
