import XCTest
@testable import LegoCore

/// A fake LEGO.com: order-list batches revealed by "Load More", and detail pages by URL.
@MainActor
final class FakePage: BrowserPage {
    var batches: [String]
    var loaded = 1
    var clicks = 0
    var details: [String: String] = [:]
    var signedOut = false
    var visited: [String] = []
    var current = ""
    var failingURLs: Set<String> = []
    /// After a click, Load More stays hidden until waitForLoadMore is called with at least this timeout.
    var reappearAfter: Double? = nil
    var loadMoreHidden = false

    init(batches: [String]) { self.batches = batches }

    func goto(_ url: String, timeout: Double) async throws {
        visited.append(url)
        if failingURLs.contains(url) { throw ScraperError("Timeout 20000ms exceeded.") }
        current = url
    }
    func dismissInterstitials() async {}
    func isSignedOut() async -> Bool { signedOut }
    func mainText() async throws -> String {
        if current == ordersURL { return batches[..<loaded].joined() }
        return details[current] ?? ""
    }
    func orderLinkCount() async -> Int { batches[..<loaded].joined().components(separatedBy: "Order Number:").count - 1 }
    func isLoadMoreVisible() async -> Bool { loaded < batches.count && !loadMoreHidden }
    func clickLoadMore() async throws {
        clicks += 1; loaded += 1
        if reappearAfter != nil { loadMoreHidden = true }
    }
    func waitForText(_ pattern: String, timeout: Double) async throws -> Bool {
        Rx.search("(?m)" + pattern, try await mainText()) != nil
    }
    func waitForLoadMore(timeout: Double) async throws -> Bool {
        guard loaded < batches.count, let r = reappearAfter, r <= timeout else { return false }
        loadMoreHidden = false
        return true
    }
    func sleep(_ seconds: Double) async throws { try Task.checkCancellation() }
}

func block(_ n: String, _ date: String, total: String = "10.00") -> String {
    "Shipped\nOrder Number: T\(n)\nOrder Date: \(date)\nTotal: $\(total)\n1 item in this order\nManage my order\n"
}

/// Ports of lego-tests: test_since_date_early_stop, test_load_more_final_wait, test_load_more_progress,
/// test_pipeline_integration, test_interrupt - run against the fake page.
@MainActor
final class ScraperTests: XCTestCase {
    var tmp: URL!
    var log: [String] = []

    override func setUp() async throws {
        tmp = FileManager.default.temporaryDirectory.appendingPathComponent("lego-scraper-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true)
        log = []
    }

    func scraper(_ page: FakePage, stop: StopFlag = StopFlag(), login: @escaping () async throws -> Void = {}) -> Scraper {
        Scraper(page: page, stop: stop, log: { [weak self] in self?.log.append($0) }, waitForLogin: login)
    }

    func listText(_ page: FakePage, since: SimpleDate?, finalWait: Double = 5, maxOrders: Int? = nil) async throws -> String {
        page.current = ordersURL
        return try await scraper(page).loadAllOrdersText(maxOrders: maxOrders, loadMoreDelay: 0, loadMoreFinalWait: finalWait, sinceDate: since)
    }

    let since = SimpleDate(year: 2026, month: 6, day: 1)

    func testSinceDateEarlyStop() async throws {
        let p1 = FakePage(batches: [block("1", "June 15, 2026") + block("2", "June 10, 2026"),
                                    block("3", "June 2, 2026") + block("4", "May 20, 2026"),
                                    block("5", "April 1, 2026") + block("6", "March 1, 2026")])
        let text = try await listText(p1, since: since)
        XCTAssertEqual(p1.clicks, 1)
        XCTAssertEqual(parseOrderList(text).map(\.orderNumber), ["T1", "T2", "T3", "T4"])

        let p2 = FakePage(batches: [block("10", "June 15, 2026") + block("11", "May 1, 2026"), block("12", "April 1, 2026")])
        _ = try await listText(p2, since: since)
        XCTAssertEqual(p2.clicks, 0)

        let p3 = FakePage(batches: [block("20", "June 15, 2026") + block("21", "June 1, 2026"), block("22", "May 31, 2026")])
        _ = try await listText(p3, since: since)
        XCTAssertEqual(p3.clicks, 1)

        let p4 = FakePage(batches: [block("30", "June 15, 2026"), block("31", "January 1, 2020")])
        _ = try await listText(p4, since: nil)
        XCTAssertEqual(p4.clicks, 1)
    }

    func testLoadMoreFinalWaitAndMaxOrders() async throws {
        let batches = (0..<3).map { block("\($0)", "June 15, 2026") }
        let slow = FakePage(batches: batches); slow.reappearAfter = 3
        _ = try await listText(slow, since: nil, finalWait: 5)
        XCTAssertEqual(slow.clicks, 2)  // waited long enough each time

        let impatient = FakePage(batches: batches); impatient.reappearAfter = 3
        _ = try await listText(impatient, since: nil, finalWait: 0.1)
        XCTAssertEqual(impatient.clicks, 1)  // gave up after the first slow reappearance

        let capped = FakePage(batches: batches)
        _ = try await listText(capped, since: nil, maxOrders: 2)
        XCTAssertEqual(capped.clicks, 1)
    }

    func testLoadMoreProgressLines() async throws {
        let p = FakePage(batches: ["Order Number: T500000000\nOrder Number: T500000001\n",
                                   "Order Number: T500000001\nOrder Number: T500000002\n"])
        _ = try await listText(p, since: nil)
        XCTAssertEqual(log.filter { $0.hasPrefix("  [") }, ["  [1] T500000000", "  [2] T500000001", "  [3] T500000002"])
    }

    func makeSite() -> FakePage {
        let p = FakePage(batches: [block("100", "June 5, 2026", total: "25.00") + block("100", "June 5, 2026", total: "25.00"),
                                   block("200", "January 5, 2020", total: "8.00") + block("300", "June 1, 2026", total: "3.00")])
        p.details = [
            orderDetailURL("T100"): "Shipped\nTracking number: 1Z\nWidget™\nItem: 111\nQuantity: 1\nPrice\n$18.50\nOrder summary\nSubtotal $18.50\nTax $1.50\nTotal $20.00\n",
            orderDetailURL("T200"): "Old Thing\nItem: 222\nQuantity: 1\nPrice\n$8.00\n",
            orderDetailURL("T300"): "Digital Gifting\nLEGO E-Gift Card\nQuantity: 1\nPrice\n$3.00\n",
        ]
        return p
    }

    func options() -> ScrapeOptions {
        var o = ScrapeOptions(jsonURL: tmp.appendingPathComponent("lego_orders.json"),
                              csvURL: tmp.appendingPathComponent("lego_order_items.csv"),
                              htmlURL: tmp.appendingPathComponent("lego_orders.html"))
        o.sinceDate = SimpleDate(year: 2026, month: 1, day: 1)
        o.delay = 0
        return o
    }

    func testFullRunThenResume() async throws {
        let site = makeSite()
        var loginCalls = 0
        site.signedOut = true
        let s = scraper(site, login: { loginCalls += 1; site.signedOut = false })
        let orders = try await s.run(options())

        XCTAssertEqual(loginCalls, 1)
        XCTAssertEqual(orders.map(\.orderNumber), ["T100", "T200", "T300"])        // duplicate T100 collapsed
        XCTAssertEqual(orders[0].items.first?.name, "Widget")
        XCTAssertEqual(orders[0].total, "20.00")                                    // corrected from its detail page
        XCTAssertTrue(orders[1].items.isEmpty)                                      // before the since date: not fetched
        XCTAssertTrue(orders[2].items.first?.isGiftCard ?? false)
        XCTAssertFalse(site.visited.contains(orderDetailURL("T200")))
        for f in ["lego_orders.json", "lego_order_items.csv", "lego_orders.html"] {
            XCTAssertTrue(FileManager.default.fileExists(atPath: tmp.appendingPathComponent(f).path), f)
        }

        // Run 2 resumes: nothing refetched, data intact.
        let site2 = makeSite()
        let again = try await scraper(site2).run(options())
        XCTAssertEqual(site2.visited, [ordersURL])
        XCTAssertEqual(again[0].items.first?.trackingNumber, "1Z")
        XCTAssertTrue(log.contains { $0.hasPrefix("Resuming: 2 order(s)") })
    }

    func testLeaveOutTracking() async throws {
        var o = options()
        o.includeTracking = false
        let orders = try await scraper(makeSite()).run(o)
        XCTAssertNil(orders[0].items.first?.trackingNumber)
        XCTAssertEqual(orders[0].items.first?.name, "Widget")                       // everything else intact
        for f in [o.jsonURL, o.csvURL, o.htmlURL!] {
            let text = try String(contentsOf: f)
            XCTAssertFalse(text.contains("1Z"), f.lastPathComponent)
        }
        XCTAssertTrue(try String(contentsOf: o.jsonURL).contains("\"tracking_number\": null"))  // field kept
        XCTAssertTrue(try String(contentsOf: o.csvURL).hasPrefix(csvHeader.joined(separator: ",")))

        // Default keeps them.
        try FileManager.default.removeItem(at: o.jsonURL)
        let withTracking = try await scraper(makeSite()).run(options())
        XCTAssertEqual(withTracking[0].items.first?.trackingNumber, "1Z")
        XCTAssertTrue(try String(contentsOf: o.csvURL).contains(",1Z\r\n"))
    }

    func testFailedOrderIsRecordedAndRetried() async throws {
        let site = makeSite()
        site.failingURLs = [orderDetailURL("T100")]
        let orders = try await scraper(site).run(options())
        XCTAssertTrue(orders[0].items.isEmpty)
        XCTAssertEqual(orders[0].fetchError, "Timeout 20000ms exceeded.")
        XCTAssertEqual(orders[2].items.count, 1)                                    // the run kept going

        let site2 = makeSite()
        let retried = try await scraper(site2).run(options())
        XCTAssertTrue(site2.visited.contains(orderDetailURL("T100")))
        XCTAssertNil(retried[0].fetchError)
    }

    func testStopSavesProgressAndCancelStillSaves() async throws {
        let site = makeSite()
        let stop = StopFlag()
        let s = Scraper(page: site, stop: stop, log: { [weak self] line in
            self?.log.append(line)
            if line.hasPrefix("  [1/3] T100") { stop.request() }                    // Stop clicked mid-run
        }, waitForLogin: {})
        let orders = try await s.run(options())
        XCTAssertEqual(orders[0].items.count, 1)                                    // current order finished
        XCTAssertTrue(orders[2].items.isEmpty)                                      // later ones not started
        XCTAssertTrue(log.contains { $0.contains("Stopped early. 1/3") })
        XCTAssertEqual(try loadOrders(options().jsonURL)[0].items.count, 1)

        // A hard stop (task cancelled) throws CancellationError but still leaves saved files behind.
        try FileManager.default.removeItem(at: options().jsonURL)
        let site2 = makeSite()
        let task = Task { @MainActor in try await self.scraper(site2).run(self.options()) }
        task.cancel()
        do { _ = try await task.value; XCTFail("expected cancellation") } catch is CancellationError {}
    }
}
