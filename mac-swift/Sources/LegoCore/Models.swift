import Foundation

/// Version of the Swift port. Bump by 1 with every change to LegoCore or the app.
public let legoSwiftVersion = "5"

public let baseURL = "https://www.lego.com"
public let ordersURL = "\(baseURL)/en-us/member/orders"
public func orderDetailURL(_ orderNumber: String) -> String { "\(baseURL)/en-us/member/orders/details/\(orderNumber)" }

/// Default "since" cutoff, same as the Python scraper's DEFAULT_SINCE_DATE (02/01/2024).
public let defaultSinceDate = SimpleDate(year: 2024, month: 2, day: 1)

/// A small string->string? dictionary that keeps insertion order, like a Python dict.
/// Used for an item's `prices` and an order's `summary`.
public struct OrderedStrings: Equatable {
    public private(set) var pairs: [(key: String, value: String?)] = []

    public init() {}
    public init(_ pairs: [(String, String?)]) { for (k, v) in pairs { self[k] = v } }

    public subscript(key: String) -> String? {
        get { pairs.first { $0.key == key }?.value ?? nil }
        set {
            if let i = pairs.firstIndex(where: { $0.key == key }) { pairs[i].value = newValue }
            else { pairs.append((key, newValue)) }
        }
    }

    public func contains(_ key: String) -> Bool { pairs.contains { $0.key == key } }
    public var isEmpty: Bool { pairs.isEmpty }
    public var keys: [String] { pairs.map(\.key) }

    public static func == (a: OrderedStrings, b: OrderedStrings) -> Bool {
        a.pairs.count == b.pairs.count && zip(a.pairs, b.pairs).allSatisfy { $0.key == $1.key && $0.value == $1.value }
    }

    var json: JSONValue { .object(pairs.map { ($0.key, $0.value.map(JSONValue.string) ?? .null) }) }

    init(json: JSONValue?) {
        if case let .object(p)? = json {
            for (k, v) in p {
                switch v {
                case .null: self[k] = nil
                case let .string(s): self[k] = s
                default: self[k] = v.pythonStr
                }
            }
        }
    }
}

/// One line item within an order (a set, a loose Pick A Brick piece, a gift card, a custom build).
/// Same fields and JSON shape as the Python `LegoOrderLine`.
public struct LegoOrderLine: Equatable {
    public var name: String
    public var itemNumber: String?
    public var customID: String?
    public var quantity: Int?
    public var prices: OrderedStrings
    public var isFreeGift: Bool
    public var isPiece: Bool
    public var isGiftCard: Bool
    public var status: String?
    public var trackingNumber: String?

    public init(name: String, itemNumber: String?, customID: String?, quantity: Int?, prices: OrderedStrings,
                isFreeGift: Bool, isPiece: Bool, isGiftCard: Bool, status: String?, trackingNumber: String?) {
        self.name = name; self.itemNumber = itemNumber; self.customID = customID; self.quantity = quantity
        self.prices = prices; self.isFreeGift = isFreeGift; self.isPiece = isPiece; self.isGiftCard = isGiftCard
        self.status = status; self.trackingNumber = trackingNumber
    }

    public var regularPrice: String? { prices["product.regularPrice"] }
    public var salePrice: String? { prices["product.salePrice"] }

    public func toJSON() -> JSONValue {
        .object([
            ("name", .string(name)),
            ("item_number", str(itemNumber)),
            ("custom_id", str(customID)),
            ("quantity", quantity.map(JSONValue.int) ?? .null),
            ("prices", prices.json),
            ("is_free_gift", .bool(isFreeGift)),
            ("is_piece", .bool(isPiece)),
            ("is_gift_card", .bool(isGiftCard)),
            ("status", str(status)),
            ("tracking_number", str(trackingNumber)),
        ])
    }

    public static func fromJSON(_ d: JSONValue) throws -> LegoOrderLine {
        guard let nameValue = d["name"] else { throw JSONParseError(message: "item is missing 'name'") }
        var prices = OrderedStrings(json: d["prices"])
        if prices.isEmpty { prices = emptyPrices() }  // Python: d.get("prices") or {defaults}
        return LegoOrderLine(
            name: nameValue.stringValue ?? nameValue.pythonStr,
            itemNumber: optStr(d["item_number"]),
            customID: optStr(d["custom_id"]),
            quantity: d["quantity"]?.intValue,
            prices: prices,
            isFreeGift: d["is_free_gift"]?.truthy ?? false,
            isPiece: d["is_piece"]?.truthy ?? false,
            isGiftCard: d["is_gift_card"]?.truthy ?? false,
            status: optStr(d["status"]),
            trackingNumber: optStr(d["tracking_number"])
        )
    }
}

/// One order from the My Orders list, plus everything fetched from its detail page.
public struct LegoOrder: Equatable {
    public var orderNumber: String
    public var status: String?
    public var orderDate: String?
    public var total: String?
    public var itemCountListed: Int?
    public var url: String?
    public var items: [LegoOrderLine] = []
    public var summary = OrderedStrings()
    public var fetchError: String?

    public init(orderNumber: String, status: String?, orderDate: String?, total: String?, itemCountListed: Int?,
                url: String?, items: [LegoOrderLine] = [], summary: OrderedStrings = OrderedStrings(), fetchError: String? = nil) {
        self.orderNumber = orderNumber; self.status = status; self.orderDate = orderDate; self.total = total
        self.itemCountListed = itemCountListed; self.url = url; self.items = items; self.summary = summary
        self.fetchError = fetchError
    }

    public func toJSON() -> JSONValue {
        var pairs: [(String, JSONValue)] = [
            ("order_number", .string(orderNumber)),
            ("status", str(status)),
            ("order_date", str(orderDate)),
            ("total", str(total)),
            ("item_count_listed", itemCountListed.map(JSONValue.int) ?? .null),
            ("url", str(url)),
            ("items", .array(items.map { $0.toJSON() })),
            ("summary", summary.json),
        ]
        if let e = fetchError { pairs.append(("fetch_error", .string(e))) }
        return .object(pairs)
    }

    public static func fromJSON(_ d: JSONValue) throws -> LegoOrder {
        guard let num = d["order_number"] else { throw JSONParseError(message: "order is missing 'order_number'") }
        var items: [LegoOrderLine] = []
        if case let .array(list)? = d["items"] { items = try list.map(LegoOrderLine.fromJSON) }
        return LegoOrder(
            orderNumber: num.stringValue ?? num.pythonStr,
            status: optStr(d["status"]),
            orderDate: optStr(d["order_date"]),
            total: optStr(d["total"]),
            itemCountListed: d["item_count_listed"]?.intValue,
            url: optStr(d["url"]),
            items: items,
            summary: OrderedStrings(json: d["summary"]),
            fetchError: optStr(d["fetch_error"])
        )
    }
}

public func emptyPrices() -> OrderedStrings { OrderedStrings([("product.regularPrice", nil), ("product.salePrice", nil)]) }

private func str(_ s: String?) -> JSONValue { s.map(JSONValue.string) ?? .null }

private func optStr(_ v: JSONValue?) -> String? {
    guard let v else { return nil }
    if case .null = v { return nil }
    return v.stringValue ?? v.pythonStr
}
