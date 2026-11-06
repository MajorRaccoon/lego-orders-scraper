import XCTest
@testable import LegoCore

/// Ports of lego-tests: test_lego_parser, test_order_list_no_bleed, test_order_summary,
/// test_prices_and_names, test_since_date, test_reconcile_total, test_dedupe_merge.
final class ParserTests: XCTestCase {
    let list = """
    My Orders
    Backordered
    Order Number: T514535382
    Order Date: September 7, 2026
    Total: $1,369.95
    6 items in this order
    +2
    Manage my order
    Delivered
    Order Number: T500000001
    Order Date: June 1, 2025
    Total: $12.34
    1 item in this order
    """

    func testOrderList() {
        let orders = parseOrderList(list)
        XCTAssertEqual(orders.map(\.orderNumber), ["T514535382", "T500000001"])
        let a = orders[0], b = orders[1]
        XCTAssertEqual(a.status, "Backordered"); XCTAssertEqual(a.orderDate, "September 7, 2026")
        XCTAssertEqual(a.total, "1,369.95"); XCTAssertEqual(a.itemCountListed, 6)
        XCTAssertEqual(b.status, "Delivered"); XCTAssertEqual(b.total, "12.34"); XCTAssertEqual(b.itemCountListed, 1)
        XCTAssertTrue(a.url!.hasSuffix("/T514535382")); XCTAssertTrue(a.items.isEmpty); XCTAssertTrue(a.summary.isEmpty)
        XCTAssertEqual(parseOrderList(list, maxOrders: 1).map(\.orderNumber), ["T514535382"])
    }

    func testOrderListNoBleed() {
        let o = Dictionary(uniqueKeysWithValues: parseOrderList("""
        Shipped
        Order Number: T111111111
        Order Date: June 1, 2026
        Total: $10.00
        1 gift card in this order
        Shipped
        Order Number: T222222222
        Order Date: May 1, 2026
        Total: $99.99
        2 items in this order
        Backordered
        Order Number: T333333333
        Order Date: April 1, 2026
        2 items in this order
        """).map { ($0.orderNumber, $0) })
        XCTAssertEqual(o["T111111111"]?.total, "10.00"); XCTAssertNil(o["T111111111"]?.itemCountListed)
        XCTAssertEqual(o["T222222222"]?.total, "99.99")
        XCTAssertNil(o["T333333333"]?.total)

        let t2 = parseOrderList("""
        Just placed
        Order Number: T555555555
        Order Date: October 6, 2026
        In Process
        Order Number: T666666666
        Order Date: October 6, 2026
        Total: $579.13
        2 items in this order
        """)
        XCTAssertNil(t2[0].total); XCTAssertNil(t2[0].itemCountListed)
        XCTAssertEqual(t2[1].total, "579.13")
    }

    let detail = """
    Order details
    Shipped
    Tracking number: 1Z999AA10123456784
    Technic™ Hub
    Item: 88012
    Quantity: 2
    Price
    $49.99
    Free Poster
    Item: 5006
    Quantity: 1
    Price
    -
    Sale Set
    Item: 10300
    Quantity: 1
    Price
    $22.99
    product.salePrice
    $16.09
    Insiders Set
    Item: 21330
    Quantity: 1
    Price
    $69.99
    $48.99
    LEGO® Insiders Price
    Backordered
    Back Item
    Item: 76000
    Quantity: 3
    Price
    $10.00
    Bricks and Pieces
    Pick A Brick Container
    Item: 999
    Price
    $5.00
    Round Brick 1x1
    SKU: 300121
    Quantity: 25
    Price
    $2.50
    Digital Gifting
    LEGO E-Gift Card
    Quantity: 1
    Price
    $25.00
    Custom Minifigure
    Item: 3850083
    ID: ABC-123-XYZ
    Quantity: 1
    Price
    $9.99
    """

    func testOrderDetail() {
        let items = parseOrderDetail(detail)
        XCTAssertEqual(items.count, 9)
        let by = Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0) })

        let hub = by["Technic Hub"]!
        XCTAssertEqual(hub.itemNumber, "88012"); XCTAssertEqual(hub.quantity, 2)
        XCTAssertEqual(hub.status, "Shipped"); XCTAssertEqual(hub.trackingNumber, "1Z999AA10123456784")
        XCTAssertEqual(hub.regularPrice, "49.99"); XCTAssertEqual(hub.salePrice, "49.99")
        XCTAssertFalse(hub.isFreeGift || hub.isPiece || hub.isGiftCard); XCTAssertNil(hub.customID)

        let free = by["Free Poster"]!
        XCTAssertTrue(free.isFreeGift); XCTAssertNil(free.regularPrice); XCTAssertNil(free.salePrice)
        XCTAssertEqual(by["Sale Set"]!.regularPrice, "22.99"); XCTAssertEqual(by["Sale Set"]!.salePrice, "16.09")
        XCTAssertEqual(by["Insiders Set"]!.regularPrice, "69.99"); XCTAssertEqual(by["Insiders Set"]!.salePrice, "48.99")

        let back = by["Back Item"]!
        XCTAssertEqual(back.status, "Backordered"); XCTAssertEqual(back.quantity, 3)
        XCTAssertEqual(back.trackingNumber, "1Z999AA10123456784")

        let cont = by["Pick A Brick Container"]!, piece = by["Round Brick 1x1"]!
        XCTAssertNil(cont.quantity); XCTAssertFalse(cont.isPiece); XCTAssertEqual(cont.itemNumber, "999")
        XCTAssertTrue(piece.isPiece); XCTAssertEqual(piece.itemNumber, "300121"); XCTAssertEqual(piece.quantity, 25)

        let gift = by["LEGO E-Gift Card"]!
        XCTAssertTrue(gift.isGiftCard); XCTAssertNil(gift.itemNumber); XCTAssertEqual(gift.salePrice, "25.00")

        let mini = by["Custom Minifigure"]!
        XCTAssertEqual(mini.customID, "ABC-123-XYZ"); XCTAssertEqual(mini.itemNumber, "3850083")
        XCTAssertNil(by["ID: ABC-123-XYZ"])

        XCTAssertTrue(parseOrderDetail("").isEmpty)
        XCTAssertTrue(parseOrderDetail("nothing useful here\nat all").isEmpty)
    }

    /// WebKit runs LEGO's hidden "Price" label into the amount; prices must still be read.
    func testWebKitGluedPriceLines() {
        let webkit = "Holiday Set\nItem: 11111\nQuantity: 1\nPrice$119.99\nFree Promo\nItem: 40000\nQuantity: 1\nPrice-\n"
            + "Bag Tag\nItem: 5008114\nQuantity: 2\nPrice$9.99\nproduct.salePrice$4.99\n"
            + "Insiders Set\nItem: 21330\nQuantity: 1\nPrice$69.99$48.99LEGO® Insiders Price\nSupport\n"
        let chromium = webkit.replacingOccurrences(of: "Price$", with: "Price\n$")
            .replacingOccurrences(of: "Price-", with: "Price\n-")
            .replacingOccurrences(of: "product.salePrice$", with: "product.salePrice\n$")
            .replacingOccurrences(of: "$69.99$48.99LEGO", with: "$69.99\n$48.99\nLEGO")
        let w = parseOrderDetail(webkit)
        XCTAssertEqual(w, parseOrderDetail(chromium))
        XCTAssertEqual(w.count, 4)
        XCTAssertEqual(w[0].salePrice, "119.99"); XCTAssertFalse(w[0].isFreeGift)
        XCTAssertTrue(w[1].isFreeGift)
        XCTAssertEqual(w[2].regularPrice, "9.99"); XCTAssertEqual(w[2].salePrice, "4.99")
        XCTAssertEqual(w[3].regularPrice, "69.99"); XCTAssertEqual(w[3].salePrice, "48.99")
        for keep in ["-$15.00", "Price", "$9.99", "Prices may vary", "Price match", "Price$", "Pricey$5.00"] {
            XCTAssertEqual(splitGluedPriceLine(keep), [keep], keep)
        }
    }

    /// "In Process" orders list their items under "Pre-order"; e-gift cards have no status.
    func testPreOrderStatus() {
        let items = parseOrderDetail("Cancel order\nPre-order\nFreight Depot\nItem: 910072\nQuantity: 2\nPrice$439.98\n"
            + "Digital gifting\nLEGO E-Gift Card\nQuantity: 1\nPrice$200.00\n")
        XCTAssertEqual(items.count, 2)
        XCTAssertEqual(items[0].status, "Pre-order"); XCTAssertEqual(items[0].salePrice, "439.98")
        XCTAssertTrue(items[1].isGiftCard)
        XCTAssertNil(items[1].status)                 // "Digital gifting" clears the pre-order status
        XCTAssertNil(items[1].trackingNumber)
    }

    func testOrderSummary() {
        let two = parseOrderSummary("Items...\nOrder summary\nSubtotal\n$754.96\nDelivery\n$0.00\nTax\n$54.08\nLEGO® Insiders discount\n-$9.00\nTotal\n$800.04\n")
        XCTAssertEqual(two.keys, ["subtotal", "delivery", "tax", "insiders_discount", "total"])
        XCTAssertEqual(two["insiders_discount"], "-9.00"); XCTAssertEqual(two["total"], "800.04")

        let same = parseOrderSummary("Order summary\nSubtotal $10.00\nShipping $4.99\nTax $0.80\nDiscount -$2.00\nTotal $13.79\n")
        XCTAssertEqual(same["delivery"], "4.99"); XCTAssertEqual(same["discount"], "-2.00")

        XCTAssertTrue(parseOrderSummary("no summary block on this page").isEmpty)
        XCTAssertNotEqual(parseOrderSummary("Order summary\nSubtotal\nTotal\n$5.00\n")["subtotal"], "5.00")
        XCTAssertEqual(parseOrderSummary("Order summary\nSubtotal $1.00\n"), OrderedStrings([("subtotal", "1.00")]))
    }

    func testPricesAndNames() {
        XCTAssertEqual(buildPrices([]), emptyPrices())
        XCTAssertEqual(buildPrices(["10.00"])["product.salePrice"], "10.00")
        XCTAssertEqual(buildPrices(["22.99", "16.09"]), OrderedStrings([("product.regularPrice", "22.99"), ("product.salePrice", "16.09")]))
        XCTAssertEqual(cleanItemName("Technic™ Hub"), "Technic Hub")
        XCTAssertEqual(cleanItemName("NINJAGO® City Workshops"), "NINJAGO City Workshops")
        XCTAssertEqual(cleanItemName("Café “Quoted”"), "Caf Quoted")
        XCTAssertEqual(cleanItemName(""), "")
    }

    func testDates() throws {
        XCTAssertEqual(parseOrderDate("September 7, 2026"), SimpleDate(year: 2026, month: 9, day: 7))
        XCTAssertEqual(parseOrderDate("January 31, 2024"), SimpleDate(year: 2024, month: 1, day: 31))
        for bad in [nil, "", "garbage", "2026-09-07", "Sept 7, 2026", "February 30, 2024"] {
            XCTAssertNil(parseOrderDate(bad), bad ?? "nil")
        }
        func o(_ d: String?) -> LegoOrder { LegoOrder(orderNumber: "T1", status: nil, orderDate: d, total: nil, itemCountListed: nil, url: "u") }
        let since = SimpleDate(year: 2026, month: 6, day: 1)
        XCTAssertTrue(isBeforeSinceDate(o("May 31, 2026"), since))
        XCTAssertFalse(isBeforeSinceDate(o("June 1, 2026"), since))
        XCTAssertFalse(isBeforeSinceDate(o("not a date"), since))
        XCTAssertFalse(isBeforeSinceDate(o(nil), since))
        XCTAssertFalse(isBeforeSinceDate(o("May 31, 2026"), nil))

        XCTAssertEqual(try parseSinceDate("01/31/2026"), SimpleDate(year: 2026, month: 1, day: 31))
        XCTAssertNil(try parseSinceDate("all")); XCTAssertNil(try parseSinceDate(" None ")); XCTAssertNil(try parseSinceDate(""))
        XCTAssertThrowsError(try parseSinceDate("2026-01-31"))
        XCTAssertThrowsError(try parseSinceDate("02/30/2026"))
        XCTAssertEqual(defaultSinceDate.description, "02/01/2024")
    }

    func mk(_ num: String, items: Int = 0, status: String = "Shipped", total: String? = "1.00",
            date: String = "May 1, 2026", summary: OrderedStrings = OrderedStrings()) -> LegoOrder {
        LegoOrder(orderNumber: num, status: status, orderDate: date, total: total, itemCountListed: items, url: "u/\(num)",
                  items: (0..<items).map { LegoOrderLine(name: "i\($0)", itemNumber: "\($0)", customID: nil, quantity: 1,
                                                          prices: emptyPrices(), isFreeGift: false, isPiece: false,
                                                          isGiftCard: false, status: nil, trackingNumber: nil) },
                  summary: summary)
    }

    func testReconcileTotal() {
        var a = mk("T517109946", items: 1, total: "579.13", summary: OrderedStrings([("total", "107.23")]))
        var b = mk("T517109748", items: 1, total: "579.13", summary: OrderedStrings([("total", "579.13")]))
        var logged: [String] = []
        XCTAssertTrue(reconcileTotal(&a) { logged.append($0) })
        XCTAssertFalse(reconcileTotal(&b) { logged.append($0) })
        XCTAssertEqual(a.total, "107.23"); XCTAssertEqual(b.total, "579.13")
        XCTAssertEqual(logged.count, 1); XCTAssertTrue(logged[0].contains("T517109946"))

        let merged = mergeWithExisting([mk("T517109946", total: "579.13")], [("T517109946", a)])
        XCTAssertEqual(merged[0].total, "107.23")
        var c = mk("T1", total: "5.00")
        XCTAssertFalse(reconcileTotal(&c)); XCTAssertEqual(c.total, "5.00")
    }

    func testDedupeAndMerge() {
        var out = dedupeOrders([mk("T1"), mk("T2", items: 2), mk("T1", items: 3), mk("T2")])
        XCTAssertEqual(out.map(\.orderNumber), ["T1", "T2"])
        XCTAssertEqual(out[0].items.count, 3); XCTAssertEqual(out[1].items.count, 2)
        out = dedupeOrders([mk("T1", items: 1), mk("T1", items: 2)])
        XCTAssertEqual(out.count, 1); XCTAssertEqual(out[0].items.count, 1)

        let existing = [("T1", mk("T1", items: 2, status: "Backordered", total: "9.00")), ("T9", mk("T9", items: 1))]
        let fresh = [mk("T2"), mk("T1", status: "Shipped", total: "9.50", date: "June 2, 2026")]
        let merged = mergeWithExisting(fresh, existing)
        XCTAssertEqual(merged.map(\.orderNumber), ["T2", "T1", "T9"])
        XCTAssertEqual(merged[1].items.count, 2)
        XCTAssertEqual(merged[1].status, "Shipped"); XCTAssertEqual(merged[1].total, "9.50"); XCTAssertEqual(merged[1].orderDate, "June 2, 2026")
        XCTAssertTrue(merged[0].items.isEmpty); XCTAssertEqual(merged[2].items.count, 1)
    }
}
