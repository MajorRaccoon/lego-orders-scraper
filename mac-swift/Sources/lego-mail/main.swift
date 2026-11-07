import Foundation
import LegoCore
import LegoMail

// Command-line version of the LEGO Mail Orders app.
//   swift run lego-mail                                  # read ~/Library/Mail, save in the data folder
//   swift run lego-mail --mail-dir ~/Desktop/lego-emails # read exported .eml / .mbox files instead
// Run `swift run lego-mail --help` for every option.

let usage = """
usage: lego-mail [options]

Reads LEGO Shop order emails from Apple Mail and saves the orders as
lego_mail_orders.json, lego_mail_orders.csv and lego_mail_orders.html.

  --mail-dir DIR        Folder to read (default ~/Library/Mail). Can also be a folder of
                        exported .eml files or .mbox mailboxes.
  --output-dir DIR      Where to save the files (default ~/Library/Application Support/LEGO Order Scraper)
  --since MM/DD/YYYY    Only orders placed on or after this date ('all' = no cutoff, the default)
  --no-html             Don't write the HTML report
  --no-tracking         Leave tracking numbers out of the files
  --fresh               Don't keep orders from an earlier run that aren't in the mail any more
  --save-email-text DIR Save the text of every LEGO order email in DIR (for troubleshooting)
  --read-pdf FILE       Just read one PDF receipt: print its text and what was read from it
  --version             Print the version
"""

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("lego-mail: \(message)\n".utf8))
    exit(2)
}

func folder(_ path: String) -> URL {
    URL(fileURLWithPath: (path as NSString).expandingTildeInPath, isDirectory: true)
}

/// --read-pdf: show what the app gets out of one PDF receipt, without touching any mail.
func readOnePDF(_ file: URL) {
    guard let data = try? Data(contentsOf: file) else { fail("can't read \(file.path)") }
    guard let text = pdfText(data) else { fail("\(file.lastPathComponent) has no readable text (is it a scan or locked?)") }
    print("===== Text of \(file.lastPathComponent) =====\n\(text)\n")
    let clean = text.components(separatedBy: .newlines)
        .map { $0.trimmingCharacters(in: .whitespaces) }
        .filter { !$0.isEmpty }
    let number = findOrderNumber(subject: "", bodies: [text]) ?? findReceiptNumber(subject: "", bodies: [text])
    print("===== What the app read =====")
    print("Order or receipt number: \(number ?? "(none found)")")
    print("Order date: \(findOrderDate(clean) ?? "(none found)")")
    let summary = parseEmailSummary(clean)
    print("Summary: " + summary.keys.map { "\($0)=\(summary[$0] ?? "")" }.joined(separator: ", "))
    let items = parseEmailItems(clean)
    print("Items (\(items.count)):")
    for it in items {
        let qty = it.quantity.map { String($0) } ?? "-"
        print("  - \(it.name) | number \(it.itemNumber ?? "-") | qty \(qty) | regular \(it.regularPrice ?? "-") | sale \(it.salePrice ?? "-")")
    }
}

var args = Array(CommandLine.arguments.dropFirst())
var mailDir = defaultMailFolder
var outputDir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    .appendingPathComponent("LEGO Order Scraper", isDirectory: true)
var since: SimpleDate?
var makeHTML = true, includeTracking = true, fresh = false
var saveText: URL?

func value(_ flag: String) -> String {
    guard !args.isEmpty else { fail("\(flag) needs a value") }
    return args.removeFirst()
}

while !args.isEmpty {
    let a = args.removeFirst()
    switch a {
    case "--mail-dir": mailDir = folder(value(a))
    case "--output-dir": outputDir = folder(value(a))
    case "--since":
        do { since = try parseSinceDate(value(a)) } catch { fail("\(error)") }
    case "--no-html": makeHTML = false
    case "--no-tracking": includeTracking = false
    case "--fresh": fresh = true
    case "--save-email-text": saveText = folder(value(a))
    case "--read-pdf": readOnePDF(URL(fileURLWithPath: (value(a) as NSString).expandingTildeInPath)); exit(0)
    case "--version": print("lego-mail \(legoMailVersion)"); exit(0)
    case "-h", "--help": print(usage); exit(0)
    default: fail("unknown option \(a)\n\n\(usage)")
    }
}

var o = MailRunOptions(mailFolder: mailDir, outputDir: outputDir, makeHTML: makeHTML)
o.since = since
o.includeTracking = includeTracking
o.fresh = fresh
o.saveTextDir = saveText
print("LEGO Mail Orders v\(legoMailVersion)")
print("Saving files in \(outputDir.path)")
do {
    try runMailImport(o) { print($0) }
} catch {
    fail("\(error)")
}
