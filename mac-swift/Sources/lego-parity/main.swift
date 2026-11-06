// lego-parity: runs the Swift parsers/writers on test input so lego-tests/tests/test_swift_parity.py
// can check they produce exactly what the Python scraper produces. Not part of the app.
//
//   lego-parity list [MAX] < page.txt       -> JSON list of orders (parse_order_list)
//   lego-parity detail < page.txt           -> JSON list of items (parse_order_detail)
//   lego-parity summary < page.txt          -> JSON object (_parse_order_summary)
//   lego-parity render IN.json OUT.json OUT.csv OUT.html
//                                           -> load IN.json and write all three outputs
//   lego-parity dates < lines.txt           -> one parse result per line (order dates)
import Foundation
import LegoCore

func readStdin() -> String {
    String(decoding: FileHandle.standardInput.readDataToEndOfFile(), as: UTF8.self)
}

func out(_ s: String) { FileHandle.standardOutput.write(Data(s.utf8)) }

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write(Data("usage: lego-parity list|detail|summary|render|dates ...\n".utf8))
    exit(2)
}

switch args[1] {
case "list":
    let max = args.count > 2 ? Int(args[2]) : nil
    out(ordersJSON(parseOrderList(readStdin(), maxOrders: max)))
case "detail":
    out(JSONWriter.write(.array(parseOrderDetail(readStdin()).map { $0.toJSON() })))
case "summary":
    let s = parseOrderSummary(readStdin())
    out(JSONWriter.write(.object(s.pairs.map { ($0.key, $0.value.map(JSONValue.string) ?? .null) })))
case "render":
    guard args.count == 6 else { exit(2) }
    let orders = try loadOrders(URL(fileURLWithPath: args[2]))
    try writeOutputs(orders, json: URL(fileURLWithPath: args[3]), csv: URL(fileURLWithPath: args[4]), quiet: true)
    try writeHTMLReport(orders, to: URL(fileURLWithPath: args[5]))
case "dates":
    for line in readStdin().components(separatedBy: "\n") where !line.isEmpty {
        out((parseOrderDate(line)?.description ?? "None") + "\n")
    }
case "version":
    out(legoSwiftVersion + "\n")
default:
    exit(2)
}
