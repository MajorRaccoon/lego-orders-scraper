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

    func testReceipts() {
        let subject = "LEGO® Shop  Receipt 5550002 from 11/01/2026"
        XCTAssertEqual(classifyEmail(subject: subject), .confirmation)
        XCTAssertNil(findOrderNumber(subject: subject, bodies: ["Your receipt is attached."]))
        XCTAssertEqual(findReceiptNumber(subject: "Your LEGO receipt", bodies: ["Your receipt is attached.\nReceipt #: ab-1234"]), "AB-1234")
        XCTAssertEqual(findReceiptNumber(subject: subject, bodies: []), "5550002")
        XCTAssertNil(findReceiptNumber(subject: "Your receipt", bodies: ["Your receipt is attached."]))
        XCTAssertEqual(dateInSubject(subject), "November 1, 2026")
        XCTAssertEqual(dateInSubject("LEGO® Shop Receipt 1 from October 15, 2026"), "October 15, 2026")
        XCTAssertNil(dateInSubject("A message from LEGO"))
        XCTAssertTrue(isLegoOrderNumber("T514535382"))
        XCTAssertFalse(isLegoOrderNumber("5550002"))

        // A proper date label beats a bare "Date:" (e.g. a forwarded email's own header line).
        XCTAssertEqual(findOrderDate(lines("Date: Mon, Oct 26, 2026 at 8:00 AM\nPurchase date: 10/01/2026")), "October 1, 2026")
        XCTAssertEqual(findOrderDate(lines("Date: 11/01/2026")), "November 1, 2026")

        // The PDF's text is read like the body; the order number can be only in the PDF.
        let m = parseMail(Data("Subject: \(subject)\nFrom: LEGO Shop <noreply@e.lego.com>\n\nYour receipt is attached.".utf8))
        let e = parseLegoEmail(m, attachmentTexts: ["Order Number: T123456789\nLEGO Icons Bonsai Tree\nItem: 10281\nQty: 1\n$49.99\nTotal $53.11"])
        XCTAssertEqual(e?.orderNumber, "T123456789")
        XCTAssertEqual(e?.items.map(\.name), ["LEGO Icons Bonsai Tree"])
        XCTAssertEqual(e?.summary["total"], "53.11")
        XCTAssertEqual(e?.orderDate, "November 1, 2026")  // from the subject
    }

    /// The layout of a real LEGO Shop receipt PDF (as PDFKit reads it), with the customer's
    /// name, address and numbers replaced: a label column then a value column for the dates,
    /// and a one-line-per-item table without currency signs.
    func testLegoRetailReceiptPDF() {
        let pdf = """
        LEGO Retail Receipt
        Bill to: 000000001
        Sample Customer
        1 Example St
        ANYTOWN NC 00000-0000
        USA
        Ship to: 000000002
        Sample Customer
        1 Example St
        Anytown NC 00000-0000
        Page 1 / 1
        LEGO Order No.
        T100000005
        Order Date
        Invoice No.
        Invoice Date
        Customer No.
        06 Oct 2026
        5550005
        07 Oct 2026
        000000001
        Article Product Description Quantity Unit Price Discount Net Price Net Amount
        6503751 3850082 Minifigure Factory Online V39 1 11.99 11.99
        -6153328 -26880 -MINI HEAD NO. 1965 1
        -6266075 -23187 -MINI WIG, NO. 106 1
        -4275461 -76382 -MINI UPPER PART "NO. 1206" 1
        -9339 -73200 -MINI BODY LOWER PART BLACK 1
        -6361949 -53020 -INJECTION SYRINGE 1
        -362201 -3622 -BRICK 1X3 1
        -6535979 -904363 -SPECIAL BOX, NO. 43, 3850082 V39 1
        6646481 5010228 Darth Vader™ Vacation B GLOBAL 1 1 9.99 9.99
        6487855 5008114 The Mandalorian™ with G GLOBAL 1 1 9.99 5.00 4.99 4.99
        Subtotal 26.97
        Shipping & Handling Free
        Tax 1.96
        Invoice Total 28.93
        Paid by Credit Card -28.93
        Payment Terms
        Credit card
        Balance due USD
        0.00
        LEGO Retail Tel.: 1-844-903-5346
        """
        let subject = "LEGO® Shop  Receipt 5550005 from 10/07/2026"
        let m = parseMail(Data("Subject: \(subject)\nFrom: LEGO Shop <noreply@e.lego.com>\n\nYour receipt is attached.".utf8))
        guard let e = parseLegoEmail(m, attachmentTexts: [pdf]) else { return XCTFail("receipt not read") }
        XCTAssertEqual(e.orderNumber, "T100000005")
        XCTAssertEqual(e.kind, .confirmation)
        XCTAssertEqual(e.orderDate, "October 6, 2026")  // the Order Date, not the Invoice Date
        XCTAssertEqual(e.items.map(\.name), ["Minifigure Factory Online", "Darth Vader Vacation B GLOBAL 1",
                                             "The Mandalorian with G GLOBAL 1"])
        XCTAssertEqual(e.items.map(\.itemNumber), ["3850082", "5010228", "5008114"])
        XCTAssertEqual(e.items.map(\.quantity), [1, 1, 1])
        XCTAssertEqual(e.items.map(\.regularPrice), ["11.99", "9.99", "9.99"])
        XCTAssertEqual(e.items.map(\.salePrice), ["11.99", "9.99", "4.99"])  // the $5.00 discount
        XCTAssertEqual(e.summary.keys, ["subtotal", "delivery", "tax", "total"])
        XCTAssertEqual(e.summary["subtotal"], "26.97")
        XCTAssertEqual(e.summary["delivery"], "0.00")
        XCTAssertEqual(e.summary["tax"], "1.96")
        XCTAssertEqual(e.summary["total"], "28.93")

        XCTAssertEqual(labelColumnValues(cleanLines(pdf))["invoice date"], "07 Oct 2026")
        // Quantity 2 with no discount: sale = net amount / quantity = the unit price.
        let two = parseReceiptTableItems(["1234567 75192 Millennium Falcon 2 849.99 1,699.98"])
        XCTAssertEqual(two.first?.quantity, 2)
        XCTAssertEqual(two.first?.salePrice, "849.99")
        // A free gift row.
        XCTAssertEqual(parseReceiptTableItems(["1234567 40000 Gift with Purchase 1 0.00 0.00"]).first?.isFreeGift, true)
    }

    /// A real 2020 "Update on your LEGO Shop order" email (as text, personal details replaced):
    /// items as an article-number line then "item number + name" with no quantity or price,
    /// and the status only in the body ("reached our warehouse").
    func testOlderWarehouseUpdateEmail() {
        let html = """
        <table><tr><td>UPDATE ABOUT YOUR ORDER</td></tr>
        <tr><td>Dear Customer,</td></tr>
        <tr><td>Thanks for your recent LEGO&reg; order T100000006.</td></tr>
        <tr><td>We know you&rsquo;re waiting for it to arrive on your doorstep and the good news is it&rsquo;s now reached our warehouse team.
        We wanted to let you know that our warehouse teams are following additional safety guidelines.</td></tr>
        <tr><td>We&rsquo;re working hard to get your delivery to you as quickly as possible and you&rsquo;ll receive another email once your order&rsquo;s left our warehouse.</td></tr>
        <tr><td>The following products will be shipped soon:</td></tr>
        <tr><td>6222893</td></tr><tr><td>5005376 Star Wars&trade; Anniversary Pod V46</td></tr>
        <tr><td>6301717</td></tr><tr><td>40416 Ice Skating Rink V39</td></tr>
        <tr><td>6361472</td></tr><tr><td>5006482 Holiday Gift Set 2020 V46</td></tr>
        <tr><td>6294186</td></tr><tr><td>75275 A-wing Starfighter&trade; V39</td></tr>
        <tr><td>Thanks again for your order and we hope you have fun building!</td></tr>
        <tr><td>LEGO and the LEGO logo are trademarks of the LEGO Group. 2020 The LEGO Group.</td></tr>
        <tr><td>LEGO&reg; Shop, 100 Print Shop Road, Enfield, CT PO Box 1138 06082</td></tr></table>
        """
        let raw = "From: <donotreply@lego.com>\nSubject: Update on your LEGO Shop order\nDate: Fri, 4 Dec 2020 04:07:18 +0100\n"
            + "Content-Type: text/html; charset=utf-8\n\n" + html
        let m = parseMail(Data(raw.utf8))
        XCTAssertTrue(looksLikeLegoOrderEmail(m))
        guard let e = parseLegoEmail(m) else { return XCTFail("email not read") }
        XCTAssertEqual(e.orderNumber, "T100000006")
        XCTAssertEqual(e.kind, .inWarehouse)
        XCTAssertEqual(e.items.map(\.itemNumber), ["5005376", "40416", "5006482", "75275"])
        XCTAssertEqual(e.items.map(\.name), ["Star Wars Anniversary Pod", "Ice Skating Rink", "Holiday Gift Set 2020", "A-wing Starfighter"])
        XCTAssertEqual(e.items.map(\.quantity), [nil, nil, nil, nil])
        XCTAssertFalse(e.items.contains { $0.isFreeGift })  // no price shown is not "free"

        let order = buildOrders(from: [e], timeZone: TimeZone(identifier: "UTC")!)[0]
        XCTAssertEqual(order.status, "In Warehouse")
        XCTAssertEqual(order.items.map(\.status), ["In Warehouse", "In Warehouse", "In Warehouse", "In Warehouse"])
        XCTAssertEqual(order.orderDate, "December 4, 2020")  // the email's date, as nothing better is in it
        XCTAssertEqual(order.itemCountListed, 4)

        // A vague "update" subject defers to the body; a clear subject doesn't.
        XCTAssertEqual(classifyEmail(subject: "Update on your LEGO Shop order", body: ["Your order has shipped"]), .shipped)
        XCTAssertEqual(classifyEmail(subject: "Your order has shipped", body: ["It reached our warehouse"]), .shipped)
        // Footer lines with a number first aren't items without the article-number line above.
        XCTAssertTrue(parseArticleProductPairs(["2020 The LEGO Group.", "Thanks", "100 Print Shop Road"]).isEmpty)
    }

    /// A real 2023 order confirmation (as text, personal details replaced): items listed as
    /// name / price / quantity / line total under a "Price QTD. TOTAL" heading, no item number,
    /// and "SUB TOTAL" written as two words.
    func testCurrentOrderConfirmationEmail() {
        let html = """
        <h1>We've got your order</h1><p>Hi Customer,</p><p>Thanks for your order.</p>
        <table><tr><td>Your order details</td></tr><tr><td>Order: T100000007</td></tr>
        <tr><td>Order date: 1/9/2023</td></tr><tr><td>Shipping address:<br>1 Example St<br>Anytown<br>00000</td></tr></table>
        <table><tr><td>SUB TOTAL:</td><td>$36.98</td></tr><tr><td>SHIPPING:</td><td>$0.00</td></tr>
        <tr><td>TAX:</td><td>$2.68</td></tr><tr><td>ORDER TOTAL:</td><td>$39.66</td></tr></table>
        <table><tr><td>Price</td><td>QTD.</td><td>TOTAL</td></tr>
        <tr><td>Money Tree V39</td><td>$24.99</td><td>1</td><td>$24.99</td></tr><tr><td>Status:</td><td>In Process</td></tr>
        <tr><td>Clone Trooper&trade; Command Station V46</td><td>$11.99</td><td>1</td><td>$11.99</td></tr><tr><td>Status:</td><td>In Process</td></tr></table>
        <p>CONTACT US</p><p>My Account</p>
        """
        let raw = "From: LEGO® Shop <Noreply@t.crm.lego.com>\nSubject: We've got it! Your LEGO® order is confirmed, Customer\n"
            + "Date: Mon, 09 Jan 2023 13:53:20 -0600\nContent-Type: text/html; charset=utf-8\n\n" + html
        let m = parseMail(Data(raw.utf8))
        XCTAssertTrue(looksLikeLegoOrderEmail(m))
        guard let e = parseLegoEmail(m) else { return XCTFail("email not read") }
        XCTAssertEqual(e.orderNumber, "T100000007")
        XCTAssertEqual(e.kind, .confirmation)
        XCTAssertEqual(e.orderDate, "January 9, 2023")
        XCTAssertEqual(e.items.map(\.name), ["Money Tree", "Clone Trooper Command Station"])
        XCTAssertEqual(e.items.map(\.quantity), [1, 1])
        XCTAssertEqual(e.items.map(\.regularPrice), ["24.99", "11.99"])
        XCTAssertEqual(e.items.map(\.salePrice), ["24.99", "11.99"])
        XCTAssertEqual(e.summary.keys, ["subtotal", "delivery", "tax", "total"])
        XCTAssertEqual(e.summary["subtotal"], "36.98")
        XCTAssertEqual(e.summary["total"], "39.66")

        // On sale (old price shown first), quantity 2.
        let sale = parsePriceQuantityColumns(["Price", "QTD.", "TOTAL", "Botanical Orchid V29", "$49.99", "$39.99", "2", "$79.98"])
        XCTAssertEqual(sale.first?.regularPrice, "49.99")
        XCTAssertEqual(sale.first?.salePrice, "39.99")
        XCTAssertEqual(sale.first?.quantity, 2)
        // Summary lines aren't taken for items.
        XCTAssertTrue(parsePriceQuantityColumns(["SUB TOTAL:", "$36.98", "TAX:", "$2.68", "ORDER TOTAL:", "$39.66"]).isEmpty)
    }

    /// A real receipt PDF where PDFKit split the one item row and ran it into the column
    /// headings (personal details replaced).
    func testReceiptRowSplitAcrossHeadingLines() {
        let pdf = """
        LEGO Retail Receipt
        Bill to: 000000001
        Sample Customer
        LEGO Order No.
        T100000008
        Order Date
        Invoice No.
        Invoice Date
        Customer No.
        29 Aug 2026
        5550008
        02 Sep 2026
        000000001
        Article Product Description 6589530 76476 The Ministry of Magic™
        Quantity Unit Price Discount Net Price Net Amount
        – Col.. V39 1 449.99 449.99
        Subtotal 449.99
        Shipping & Handling Free
        Tax 32.62
        Invoice Total 482.61
        Paid by Credit Card -482.61
        """
        let m = parseMail(Data("Subject: LEGO Shop  Receipt 5550008 from 09/02/2026\nFrom: LEGOshop.com <no-reply-billing03@lego.com>\n\nInvoice enclosed.".utf8))
        guard let e = parseLegoEmail(m, attachmentTexts: [pdf]) else { return XCTFail("receipt not read") }
        XCTAssertEqual(e.orderNumber, "T100000008")
        XCTAssertEqual(e.orderDate, "August 29, 2026")
        XCTAssertEqual(e.items.map(\.name), ["The Ministry of Magic - Col.."])
        XCTAssertEqual(e.items.map(\.itemNumber), ["76476"])
        XCTAssertEqual(e.items.map(\.quantity), [1])
        XCTAssertEqual(e.items.first?.regularPrice, "449.99")
        XCTAssertEqual(e.summary["total"], "482.61")

        // Two split rows, with a Minifigure Factory part line between them.
        let two = parseReceiptTableItems(cleanLines("""
        Article Product Description 1111111 75192 Millennium
        Quantity Unit Price Discount Net Price Net Amount
        Falcon V39 1 849.99 849.99 2222222 40000 Gift
        -6153328 -26880 -MINI HEAD NO. 1965 1
        Bag 1 0.00 0.00
        Subtotal 849.99
        """))
        XCTAssertEqual(two.map(\.name), ["Millennium Falcon", "Gift Bag"])
        XCTAssertEqual(two.map(\.isFreeGift), [false, true])
    }

    /// A real 2020 order confirmation (as text, personal details replaced): "USD 199.99" prices,
    /// the item number before the name, summary labels in one column and amounts in the next,
    /// and the order date mid-sentence.
    func testOlderOrderConfirmationEmail() {
        let html = """
        <p>LEGO.COM</p><p>Thank you for shopping with us!</p><p>Dear Customer,</p>
        <p>This email is confirmation that we have received your order placed on December 01 2020*.</p>
        <p>Order Confirmation</p><p>Order Number:</p><p>T100000006</p><p>VIP Number:</p><p>000000003</p>
        <p>Shipping Address:</p><p>Sample Customer<br>1 Example St<br>Anytown, NC, 00000</p>
        <table><tr><td>PRICE</td><td>QTY</td><td>TOTAL</td></tr>
        <tr><td>5005376 Star Wars&trade; Anniversary Pod V46</td></tr><tr><td>USD 0.00</td><td>Qty: 1</td><td>Total: USD 0.00</td></tr>
        <tr><td>75275 A-wing Starfighter&trade; V39</td></tr><tr><td>USD 199.99</td><td>Qty: 1</td><td>Total: USD 199.99</td></tr>
        <tr><td>5006482 Holiday Gift Set 2020 V46</td></tr><tr><td>USD 0.00</td><td>Qty: 1</td><td>Total: USD 0.00</td></tr>
        <tr><td>40416 Ice Skating Rink V39</td></tr><tr><td>USD 0.00</td><td>Qty: 1</td><td>Total: USD 0.00</td></tr></table>
        <p>VIP points are applied to your account once the order has shipped from our warehouse.</p>
        <table><tr><td>Sub Total<br>Shipping<br>VIP Discount<br>Tax</td><td>USD 199.99<br>USD 0.00<br>USD 0.00<br>USD 14.50</td></tr>
        <tr><td>ORDER TOTAL</td><td>USD 214.49</td></tr></table>
        <p>LEGO and the LEGO logo are trademarks of the LEGO Group. &copy; 2020 The LEGO Group.</p>
        """
        let raw = "From: LEGOShop.com <LEGOshop@e.LEGO.com>\nSubject: Thank you for your LEGO® Order T100000006\n"
            + "Date: Tue, 1 Dec 2020 06:26:28 -0800\nContent-Type: text/html; charset=utf-8\n\n" + html
        guard let e = parseLegoEmail(parseMail(Data(raw.utf8))) else { return XCTFail("email not read") }
        XCTAssertEqual(e.orderNumber, "T100000006")
        XCTAssertEqual(e.kind, .confirmation)
        XCTAssertEqual(e.orderDate, "December 1, 2020")
        XCTAssertEqual(e.items.map(\.name), ["Star Wars Anniversary Pod", "A-wing Starfighter", "Holiday Gift Set 2020", "Ice Skating Rink"])
        XCTAssertEqual(e.items.map(\.itemNumber), ["5005376", "75275", "5006482", "40416"])
        XCTAssertEqual(e.items.map(\.quantity), [1, 1, 1, 1])
        XCTAssertEqual(e.items.map(\.isFreeGift), [true, false, true, true])
        XCTAssertEqual(e.items[1].regularPrice, "199.99")
        XCTAssertEqual(e.summary.keys, ["subtotal", "delivery", "tax", "insiders_discount", "total"])
        XCTAssertEqual(e.summary["subtotal"], "199.99")
        XCTAssertEqual(e.summary["tax"], "14.50")  // not the subtotal sitting right after the "Tax" label
        XCTAssertEqual(e.summary["insiders_discount"], "0.00")
        XCTAssertEqual(e.summary["total"], "214.49")
        XCTAssertEqual(amounts(in: "USD 1,234.56"), ["1,234.56"])
    }

    func testCombiningEmailsIntoOrders() {
        func line(_ name: String, _ number: String, _ price: String?) -> LegoOrderLine {
            LegoOrderLine(name: name, itemNumber: number, customID: nil, quantity: 1,
                          prices: price.map { OrderedStrings([("product.regularPrice", $0), ("product.salePrice", $0)]) } ?? emptyPrices(),
                          isFreeGift: price == nil, isPiece: false, isGiftCard: false, status: nil, trackingNumber: nil)
        }
        let day: (Int) -> Date = { Date(timeIntervalSince1970: 1_788_000_000 + Double($0) * 86_400) }
        let confirm = LegoEmail(orderNumber: "T123456781", kind: .confirmation, subject: "", sentDate: day(0), orderDate: "September 7, 2026",
                                items: [line("A", "1001", "10.00"), line("B", "1002", "20.00"), line("Gift", "1003", nil)],
                                summary: OrderedStrings([("total", "30.00")]), trackingNumbers: [], source: "")
        let ship1 = LegoEmail(orderNumber: "T123456781", kind: .shipped, subject: "", sentDate: day(2), orderDate: nil,
                              items: [line("A", "1001", nil)], summary: OrderedStrings(), trackingNumbers: ["TRACK1"], source: "")
        let cancel = LegoEmail(orderNumber: "T123456781", kind: .cancelled, subject: "", sentDate: day(1), orderDate: nil,
                               items: [line("B", "1002", nil)], summary: OrderedStrings(), trackingNumbers: [], source: "")
        let other = LegoEmail(orderNumber: "T123456782", kind: .shipped, subject: "", sentDate: day(30), orderDate: nil,
                              items: [], summary: OrderedStrings(), trackingNumbers: ["TRACK2"], source: "")

        let orders = buildOrders(from: [ship1, other, confirm, cancel], timeZone: TimeZone(identifier: "UTC")!)
        XCTAssertEqual(orders.map(\.orderNumber), ["T123456782", "T123456781"])  // newest first
        let t1 = orders[1]
        XCTAssertEqual(t1.status, "Shipped")  // the partial cancellation doesn't cancel the order
        XCTAssertEqual(t1.orderDate, "September 7, 2026")
        XCTAssertEqual(t1.total, "30.00")
        XCTAssertEqual(t1.items.map(\.status), ["Shipped", "Cancelled", "Processing"])
        XCTAssertEqual(t1.items.map(\.trackingNumber), ["TRACK1", nil, nil])
        XCTAssertEqual(t1.items[0].regularPrice, "10.00")  // prices from the confirmation, not the shipping email
        XCTAssertEqual(t1.itemCountListed, 3)
        XCTAssertEqual(t1.url, orderDetailURL("T123456781"))
        XCTAssertEqual(orders[0].status, "Shipped")
        XCTAssertTrue(orders[0].items.isEmpty)
        XCTAssertEqual(orders[0].orderDate, formatOrderDate(day(30), timeZone: TimeZone(identifier: "UTC")!))

        let kept = mergeMailOrders([orders[1]], previous: [orders[0], orders[1]])
        XCTAssertEqual(kept.map(\.orderNumber), ["T123456782", "T123456781"])
    }
}
