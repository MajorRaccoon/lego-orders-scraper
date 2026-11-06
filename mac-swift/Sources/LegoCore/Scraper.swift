import Foundation

/// What the scraper needs from a browser. The app implements this with WebKit (WKWebView);
/// the tests implement it with a fake page, so the whole scraping flow is testable.
@MainActor
public protocol BrowserPage: AnyObject {
    /// Navigate and wait until the page has loaded (throws on failure or timeout).
    func goto(_ url: String, timeout: Double) async throws
    /// Click through the cookie banner / "You are about to enter LEGO.com" splash, if shown.
    func dismissInterstitials() async
    /// True when LEGO.com shows us signed out.
    func isSignedOut() async -> Bool
    /// The visible text of the page's <main> element.
    func mainText() async throws -> String
    /// Number of order links currently on the list page.
    func orderLinkCount() async -> Int
    /// Is a "Load More" button visible?
    func isLoadMoreVisible() async -> Bool
    func clickLoadMore() async throws
    /// Wait up to `timeout` seconds for a regex to match a line of the main text. True if it did.
    func waitForText(_ pattern: String, timeout: Double) async throws -> Bool
    /// Wait up to `timeout` seconds for "Load More" to become visible. True if it did.
    func waitForLoadMore(timeout: Double) async throws -> Bool
    /// Pause (fakes return immediately). Throws CancellationError when the run is cancelled.
    func sleep(_ seconds: Double) async throws
}

/// Set when the user clicks Stop: the run finishes the current step, saves, and stops.
public final class StopFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var _requested = false
    public init() {}
    public var requested: Bool { lock.lock(); defer { lock.unlock() }; return _requested }
    public func request() { lock.lock(); _requested = true; lock.unlock() }
}

public struct ScrapeOptions {
    public var maxOrders: Int?
    public var delay: Double = 1.5
    public var loadMoreDelay: Double = 1.2
    public var loadMoreFinalWait: Double = 5.0
    public var sinceDate: SimpleDate? = defaultSinceDate
    public var fresh = false
    public var jsonURL: URL
    public var csvURL: URL
    public var htmlURL: URL?

    public init(jsonURL: URL, csvURL: URL, htmlURL: URL? = nil) {
        self.jsonURL = jsonURL; self.csvURL = csvURL; self.htmlURL = htmlURL
    }
}

public struct ScraperError: Error, CustomStringConvertible {
    public let description: String
    public init(_ d: String) { description = d }
}

/// The scraping flow: a port of the Python scrape() / load_all_orders_text().
@MainActor
public final class Scraper {
    let page: BrowserPage
    let log: (String) -> Void
    let stop: StopFlag
    let waitForLogin: () async throws -> Void

    /// - waitForLogin: called when LEGO.com shows us signed out; returns once the user has logged in.
    public init(page: BrowserPage, stop: StopFlag, log: @escaping (String) -> Void,
                waitForLogin: @escaping () async throws -> Void) {
        self.page = page; self.stop = stop; self.log = log; self.waitForLogin = waitForLogin
    }

    /// Open the orders page and make sure we're signed in.
    public func ensureLoggedIn() async throws {
        log("\nOpening LEGO.com...")
        try await page.goto(ordersURL, timeout: 30)
        await page.dismissInterstitials()
        if await page.isSignedOut() {
            log("You don't look signed in yet.\n"
                + "  1) Log in to your LEGO account in the browser panel.\n"
                + "  2) Once you can see 'My Orders' with your order history, click \"I've logged in, continue\".\n")
            try await waitForLogin()
            try await page.goto(ordersURL, timeout: 30)
            await page.dismissInterstitials()
        }
    }

    /// Click "Load More" until every order is shown (or max orders reached, or the oldest
    /// loaded order is before the since date), then return the list page's text.
    public func loadAllOrdersText(maxOrders: Int?, loadMoreDelay: Double, loadMoreFinalWait: Double,
                                  sinceDate: SimpleDate?) async throws -> String {
        // The list renders client-side after the page shell; reading too early looks like "0 orders".
        if try await !page.waitForText("Order Number:\\s*T\\d+", timeout: 15) {
            log("  (no order rows appeared within 15s -- either this account genuinely has none, "
                + "or the page didn't finish loading; continuing with whatever's currently on the page)")
        }

        var seen = Set<String>()
        var seenCount = 0
        var stopForSinceDate = false

        func reportNewOrders() async throws {
            let text = try await page.mainText()
            for num in currentOrderNumbers(text) where !seen.contains(num) {
                seen.insert(num)
                seenCount += 1
                log("  [\(seenCount)] \(num)")
            }
            if let sinceDate, !stopForSinceDate {
                // The last order on the page is the oldest loaded so far (newest-first list).
                if let last = parseOrderList(text).last, isBeforeSinceDate(last, sinceDate) {
                    stopForSinceDate = true
                    log("  (reached an order placed \(last.orderDate ?? "?"), which is before the since date -- "
                        + "stopping 'Load More' here instead of loading older orders we won't fetch item detail for anyway)")
                }
            }
        }

        try await reportNewOrders()

        while true {
            if stop.requested || stopForSinceDate { break }
            if await !page.isLoadMoreVisible() {
                // The button can take a while to come back after a click; give it one longer chance.
                log("  (Load More isn't visible -- waiting up to \(pyG(loadMoreFinalWait))s in case it's just "
                    + "slow to reappear before assuming we're done...)")
                if try await !page.waitForLoadMore(timeout: loadMoreFinalWait) { break }
                try await reportNewOrders()
                continue
            }
            if let maxOrders, maxOrders > 0, await page.orderLinkCount() >= maxOrders { break }
            do {
                try await page.clickLoadMore()
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                break
            }
            try await page.sleep(loadMoreDelay)
            try await reportNewOrders()
        }
        return try await page.mainText()
    }

    /// The whole run: log in, load the order list, merge with saved progress, fetch each order's
    /// detail page (saving after every order), then write JSON, CSV and (optionally) HTML.
    @discardableResult
    public func run(_ o: ScrapeOptions) async throws -> [LegoOrder] {
        let existing = o.fresh ? [] : loadExistingOrders(o.jsonURL, log: log)
        if !existing.isEmpty {
            log("Resuming: \(existing.count) order(s) already have item detail saved in \(o.jsonURL.lastPathComponent) "
                + "-- skipping those (turn on \"Refetch everything\" to refetch them).")
        }

        try await ensureLoggedIn()

        var orders: [LegoOrder] = []
        var cancelled = false
        do {
            log("Loading order history (this may click 'Load More' a few times)...")
            let listText = try await loadAllOrdersText(maxOrders: o.maxOrders, loadMoreDelay: o.loadMoreDelay,
                                                       loadMoreFinalWait: o.loadMoreFinalWait, sinceDate: o.sinceDate)
            orders = parseOrderList(listText, maxOrders: o.maxOrders)
            orders = mergeWithExisting(orders, existing, log: log)
            orders = dedupeOrders(orders, log: log)

            let alreadySaved = orders.filter { !$0.items.isEmpty }.count
            let toFetch = orders.filter { $0.items.isEmpty && !isBeforeSinceDate($0, o.sinceDate) }.count
            var summary = "Found \(orders.count) order(s) total (\(alreadySaved) already saved"
            if o.sinceDate != nil { summary += ", \(orders.count - alreadySaved - toFetch) before the since date" }
            summary += ", \(toFetch) to fetch).\n"
            log(summary)

            for idx in orders.indices {
                if stop.requested { break }
                let tag = "  [\(idx + 1)/\(orders.count)] \(orders[idx].orderNumber)"
                if !orders[idx].items.isEmpty {
                    log("\(tag) (already saved, skipping)")
                    continue
                }
                if isBeforeSinceDate(orders[idx], o.sinceDate) {
                    log("\(tag) (placed \(orders[idx].orderDate ?? "?"), before the since date, skipping)")
                    continue
                }
                log(tag)
                do {
                    try await fetchDetail(&orders[idx], delay: o.delay)
                } catch is CancellationError {
                    throw CancellationError()
                } catch {
                    // One broken order shouldn't stop the run; it's retried next time.
                    log("      failed to fetch this order, skipping it: \(error)")
                    orders[idx].items = []
                    orders[idx].fetchError = "\(error)"
                }
                try writeOutputs(orders, json: o.jsonURL, csv: o.csvURL, quiet: true, log: log)
                try await page.sleep(o.delay)
            }
        } catch is CancellationError {
            cancelled = true
        }

        if stop.requested || cancelled {
            let done = orders.filter { !$0.items.isEmpty }.count
            log("\nStopped early. \(done)/\(orders.count) order(s) are saved in \(o.jsonURL.lastPathComponent) and "
                + "\(o.csvURL.lastPathComponent) -- click Start again to pick up where this left off.")
        }
        if !orders.isEmpty || !cancelled {
            try writeOutputs(orders, json: o.jsonURL, csv: o.csvURL, log: log)
            if let html = o.htmlURL {
                try writeHTMLReport(orders, to: html)
                log("Wrote \(html.lastPathComponent)")
            }
        }
        if cancelled { throw CancellationError() }
        return orders
    }

    func fetchDetail(_ order: inout LegoOrder, delay: Double) async throws {
        guard let url = order.url else { throw ScraperError("order has no URL") }
        try await page.goto(url, timeout: 20)
        await page.dismissInterstitials()
        // Wait for at least one item row (gift-card-only orders have only "Quantity:" lines).
        if try await !page.waitForText("^(Item|SKU|Quantity):\\s*\\S+", timeout: 15) {
            log("      (no item rows appeared within 15s -- this order may genuinely have none, "
                + "or the page didn't finish loading; parsing whatever's there)")
        }
        try await page.sleep(delay)
        let text = try await page.mainText()
        order.items = parseOrderDetail(text)
        order.summary = parseOrderSummary(text)
        reconcileTotal(&order, log: log)
        order.fetchError = nil
    }
}

/// Python's f"{x:g}" for the small delay values shown in messages.
func pyG(_ x: Double) -> String {
    if x == x.rounded(), abs(x) < 1e15 { return String(Int(x)) }
    return String(x)
}
