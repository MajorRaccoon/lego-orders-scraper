import LegoCore
import XCTest
@testable import LegoMail

/// Reading LEGO order details out of email text.
final class LegoEmailParserTests: XCTestCase {
    func lines(_ s: String) -> [String] { cleanLines(s) }

    func headers(from: String, subject: String) -> MailMessage {
        parseMailHeaders(Data("From: \(from)\nSubject: \(subject)\n\n".utf8))
    }

    func testWhichEmailsAreLookedAt() {
        XCTAssertTrue(isLegoAddress("noreply@e.lego.com"))
        XCTAssertTrue(isLegoAddress("shop@lego.com"))
        XCTAssertFalse(isLegoAddress("lego.com@phish.example"))
        XCTAssertFalse(isLegoAddress("someone@notlego.com"))

        XCTAssertTrue(looksLikeLegoOrderEmail(headers(from: "LEGO Shop <noreply@e.lego.com>", subject: "Thank you for your order")))
        XCTAssertTrue(looksLikeLegoOrderEmail(headers(from: "Me <me@example.com>", subject: "Fwd: Your LEGO order has shipped")))
        XCTAssertFalse(looksLikeLegoOrderEmail(headers(from: "LEGO <news@e.lego.com>", subject: "New sets are here")))
        XCTAssertFalse(looksLikeLegoOrderEmail(headers(from: "Store <a@example.com>", subject: "Your order has shipped")))
    }

    func testOrderNumber() {
        XCTAssertEqual(findOrderNumber(subject: "Your LEGO order T514535382 has shipped", bodies: []), "T514535382")
        XCTAssertEqual(findOrderNumber(subject: "Thank you", bodies: ["Hello\nOrder Number: T514535382\n"]), "T514535382")
        XCTAssertEqual(findOrderNumber(subject: "Thank you", bodies: ["Order #: t514535382"]), "T514535382")
        XCTAssertNil(findOrderNumber(subject: "Pre-order the new Icons set", bodies: ["Shop now. Call 1-800-422-5346"]))
    }

    func testEmailKinds() {
        let cases: [(String, LegoEmailKind)] = [
            ("Thank you for your order!", .confirmation),
            ("Your LEGO® Shop order confirmation T1", .confirmation),
            ("Your order is on its way", .shipped),
            ("Good news! Your order has shipped", .shipped),
            ("Your order is out for delivery", .shipped),
            ("Your LEGO order has been delivered", .delivered),
            ("Your order has been cancelled", .cancelled),
            ("Order canceled", .cancelled),
            ("Your refund has been processed", .refunded),
            ("We've received your return", .returned),
            ("An item in your order is backordered", .backordered),
            ("Hello", .other),
        ]
        for (subject, kind) in cases { XCTAssertEqual(classifyEmail(subject: subject), kind, subject) }
        XCTAssertEqual(classifyEmail(subject: "Hello", body: ["Your order has shipped"]), .shipped)
        XCTAssertEqual(LegoEmailKind.cancelled.status, "Cancelled")
    }

    func testAmounts() {
        XCTAssertEqual(amounts(in: "$679.99"), ["679.99"])
        XCTAssertEqual(amounts(in: "Was $59.99 now $49.99"), ["59.99", "49.99"])
        XCTAssertEqual(amounts(in: "-$20.00"), ["-20.00"])
        XCTAssertEqual(amounts(in: "$-5.00"), ["-5.00"])
        XCTAssertEqual(amounts(in: "Total: US$1,234.56"), ["1,234.56"])
        XCTAssertEqual(amounts(in: "£12.50 and €12,99"), ["12.50", "12,99"])
        XCTAssertEqual(amounts(in: "Item: 10294 Qty: 2"), [])
        XCTAssertEqual(amountValue("1,234.56"), 1234.56)
        XCTAssertEqual(amountValue("12,99"), 12.99)
        XCTAssertEqual(amountValue("-20.00"), -20)
    }

    func testItemsWithLabelsAndPrices() {
        let items = parseEmailItems(lines("""
        Your order
        LEGO® Icons Titanic
        Item: 10294
        Qty: 1
        $679.99
        LEGO® Technic™ Hub
        Item: 88012
        Qty: 2
        $59.99 $49.99
        $99.98
        Brick Calendar
        Item: 5008000
        Qty: 1
        FREE
        Subtotal
        $779.97
        Tax
        $48.75
        """))
        XCTAssertEqual(items.map(\.name), ["LEGO Icons Titanic", "LEGO Technic Hub", "Brick Calendar"])
        XCTAssertEqual(items.map(\.itemNumber), ["10294", "88012", "5008000"])
        XCTAssertEqual(items.map(\.quantity), [1, 2, 1])
        XCTAssertEqual(items[0].regularPrice, "679.99"); XCTAssertEqual(items[0].salePrice, "679.99")
        XCTAssertEqual(items[1].regularPrice, "59.99"); XCTAssertEqual(items[1].salePrice, "49.99")
        XCTAssertTrue(items[2].isFreeGift)
        XCTAssertNil(items[2].regularPrice)  // the summary's amounts must not leak into the last item
        XCTAssertFalse(items[0].isFreeGift)
    }

    func testItemVariants() {
        let items = parseEmailItems(lines("""
        LEGO Ideas Tree House Item #21318
        Quantity: 1
        Price: $199.99
        Pick a Brick 2x4 Brick Red
        Element ID: 300121
        Quantity: 10
        Price: $0.25
        Total: $2.50
        LEGO® Digital Gift Card
        Item No. 5005890
        Qty 1
        $50.00
        Minifigure Factory Custom Minifigure
        Item: 40645
        ID: ABC123
        Qty: 1
        $14.99
        """))
        XCTAssertEqual(items.map(\.name), ["LEGO Ideas Tree House", "Pick a Brick 2x4 Brick Red",
                                           "LEGO Digital Gift Card", "Minifigure Factory Custom Minifigure"])
        XCTAssertTrue(items[1].isPiece)
        XCTAssertEqual(items[1].regularPrice, "0.25")
        XCTAssertEqual(items[1].quantity, 10)
        XCTAssertTrue(items[2].isGiftCard)
        XCTAssertEqual(items[3].customID, "ABC123")
    }

    func testItemsFoundByQuantityWhenThereAreNoItemNumbers() {
        let items = parseEmailItems(lines("""
        Items in this shipment
        LEGO Star Wars Millennium Falcon 75192
        Qty: 1
        LEGO Botanicals Orchid (10311)
        Qty: 2
        """))
        XCTAssertEqual(items.map(\.name), ["LEGO Star Wars Millennium Falcon", "LEGO Botanicals Orchid"])
        XCTAssertEqual(items.map(\.itemNumber), ["75192", "10311"])
        XCTAssertEqual(items.map(\.quantity), [1, 2])
    }

    func testSummary() {
        let s = parseEmailSummary(lines("""
        Item total: $5.00
        Total: $5.00
        Subtotal: $754.96
        Shipping
        FREE
        Estimated Tax $47.18
        LEGO® Insiders discount
        $20.00
        Promo code SAVE10: -$10.00
        Order Total
        $772.14
        """))
        XCTAssertEqual(s.keys, ["subtotal", "delivery", "tax", "insiders_discount", "discount", "total"])
        XCTAssertEqual(s["subtotal"], "754.96")
        XCTAssertEqual(s["delivery"], "0.00")
        XCTAssertEqual(s["tax"], "47.18")
        XCTAssertEqual(s["insiders_discount"], "-20.00")  // discounts are saved as negatives
        XCTAssertEqual(s["discount"], "-10.00")
        XCTAssertEqual(s["total"], "772.14")  // the last Total wins
        XCTAssertTrue(parseEmailSummary(lines("Shipping address\n1 Main St")).isEmpty)
    }

    func testDatesAndTracking() {
        XCTAssertEqual(normalizeDate("September 7, 2026"), "September 7, 2026")
        XCTAssertEqual(normalizeDate("Sep 7, 2026"), "September 7, 2026")
        XCTAssertEqual(normalizeDate("Monday, September 7, 2026 at 10:15 AM"), "September 7, 2026")
        XCTAssertEqual(normalizeDate("09/07/2026"), "September 7, 2026")
        XCTAssertEqual(normalizeDate("2026-09-07"), "September 7, 2026")
        XCTAssertEqual(normalizeDate("7 September 2026"), "September 7, 2026")
        XCTAssertNil(normalizeDate("soon"))
        XCTAssertEqual(findOrderDate(lines("Order Date:\nJanuary 5, 2026")), "January 5, 2026")
        XCTAssertEqual(findOrderDate(lines("Order placed on 1/5/2026")), "January 5, 2026")
        XCTAssertNil(findOrderDate(lines("Delivered on January 9, 2026")))

        XCTAssertEqual(findTrackingNumbers(lines("Tracking number: 1Z999AA10123456784\nTracking #: 9400111899223344556677")),
                       ["1Z999AA10123456784", "9400111899223344556677"])
        XCTAssertEqual(findTrackingNumbers(lines("Tracking Number\n1Z999AA10123456784\nTrack your package")), ["1Z999AA10123456784"])
        XCTAssertEqual(findTrackingNumbers(lines("Tracking information will follow")), [])
    }

    func testCombiningEmailsIntoOrders() {
        func line(_ name: String, _ number: String, _ price: String?) -> LegoOrderLine {
            LegoOrderLine(name: name, itemNumber: number, customID: nil, quantity: 1,
                          prices: price.map { OrderedStrings([("product.regularPrice", $0), ("product.salePrice", $0)]) } ?? emptyPrices(),
                          isFreeGift: price == nil, isPiece: false, isGiftCard: false, status: nil, trackingNumber: nil)
        }
        let day: (Int) -> Date = { Date(timeIntervalSince1970: 1_788_000_000 + Double($0) * 86_400) }
        let confirm = LegoEmail(orderNumber: "T1", kind: .confirmation, subject: "", sentDate: day(0), orderDate: "September 7, 2026",
                                items: [line("A", "1001", "10.00"), line("B", "1002", "20.00"), line("Gift", "1003", nil)],
                                summary: OrderedStrings([("total", "30.00")]), trackingNumbers: [], source: "")
        let ship1 = LegoEmail(orderNumber: "T1", kind: .shipped, subject: "", sentDate: day(2), orderDate: nil,
                              items: [line("A", "1001", nil)], summary: OrderedStrings(), trackingNumbers: ["TRACK1"], source: "")
        let cancel = LegoEmail(orderNumber: "T1", kind: .cancelled, subject: "", sentDate: day(1), orderDate: nil,
                               items: [line("B", "1002", nil)], summary: OrderedStrings(), trackingNumbers: [], source: "")
        let other = LegoEmail(orderNumber: "T2", kind: .shipped, subject: "", sentDate: day(30), orderDate: nil,
                              items: [], summary: OrderedStrings(), trackingNumbers: ["TRACK2"], source: "")

        let orders = buildOrders(from: [ship1, other, confirm, cancel], timeZone: TimeZone(identifier: "UTC")!)
        XCTAssertEqual(orders.map(\.orderNumber), ["T2", "T1"])  // newest first
        let t1 = orders[1]
        XCTAssertEqual(t1.status, "Shipped")  // the partial cancellation doesn't cancel the order
        XCTAssertEqual(t1.orderDate, "September 7, 2026")
        XCTAssertEqual(t1.total, "30.00")
        XCTAssertEqual(t1.items.map(\.status), ["Shipped", "Cancelled", "Processing"])
        XCTAssertEqual(t1.items.map(\.trackingNumber), ["TRACK1", nil, nil])
        XCTAssertEqual(t1.items[0].regularPrice, "10.00")  // prices from the confirmation, not the shipping email
        XCTAssertEqual(t1.itemCountListed, 3)
        XCTAssertEqual(t1.url, orderDetailURL("T1"))
        XCTAssertEqual(orders[0].status, "Shipped")
        XCTAssertTrue(orders[0].items.isEmpty)
        XCTAssertEqual(orders[0].orderDate, formatOrderDate(day(30), timeZone: TimeZone(identifier: "UTC")!))

        let kept = mergeMailOrders([orders[1]], previous: [orders[0], orders[1]])
        XCTAssertEqual(kept.map(\.orderNumber), ["T2", "T1"])
    }
}
