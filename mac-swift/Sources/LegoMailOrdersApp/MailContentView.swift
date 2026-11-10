import AppKit
import LegoCore
import LegoMail
import SwiftUI

struct MailContentView: View {
    @EnvironmentObject var model: MailAppModel

    var body: some View {
        HSplitView {
            sidebar.frame(minWidth: 320, idealWidth: 340, maxWidth: 420)
            logView.frame(minWidth: 420)
        }
        .frame(minWidth: 800, minHeight: 560)
        // Coming back from System Settings: check again whether Full Disk Access is on now.
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            if !model.isBusy { model.checkAccess() }
        }
    }

    // MARK: Sidebar

    private var sidebar: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("LEGO Mail Orders").font(.title2.bold())
                    Text("Finds your LEGO Shop orders in Apple Mail.").font(.callout).foregroundStyle(.secondary)
                }

                if let problem = model.accessProblem { accessWarning(problem) }

                GroupBox("Read emails from") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.isDefaultMailFolder ? "Apple Mail (\(model.display(model.mailFolder)))" : model.display(model.mailFolder))
                            .font(.callout)
                            .lineLimit(2).truncationMode(.middle)
                            .textSelection(.enabled)
                        HStack {
                            Button("Browse…") { model.chooseMailFolder() }
                            Button("Use Apple Mail") { model.resetMailFolder() }.disabled(model.isDefaultMailFolder)
                        }
                        Text("Or pick a folder of emails you exported from Mail (.eml files or .mbox mailboxes).")
                            .font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(6)
                }
                .disabled(model.isBusy)

                GroupBox("Receipt PDFs (optional)") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.receiptFolder.map { model.display($0) } ?? "None")
                            .font(.callout)
                            .lineLimit(2).truncationMode(.middle)
                            .textSelection(.enabled)
                        HStack {
                            Button("Browse…") { model.chooseReceiptFolder() }
                            Button("Clear") { model.clearReceiptFolder() }.disabled(model.receiptFolder == nil)
                        }
                        Text("A folder of LEGO receipt PDFs you saved from Mail (File → Save Attachments). Use it when Mail hasn't downloaded the receipts.")
                            .font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(6)
                }
                .disabled(model.isBusy)

                GroupBox("Save files to") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.display(model.outputDir))
                            .font(.callout)
                            .lineLimit(2).truncationMode(.middle)
                            .textSelection(.enabled)
                        HStack {
                            Button("Browse…") { model.chooseOutputFolder() }
                            Button("Use default") { model.resetOutputFolder() }.disabled(model.isDefaultOutputDir)
                        }
                        Text("Saved as \(mailJSONName), .csv and .html. Separate from the LEGO.com scraper's files.")
                            .font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(6)
                }
                .disabled(model.isBusy)

                GroupBox("Options") {
                    VStack(alignment: .leading, spacing: 10) {
                        Toggle("Only orders placed on or after", isOn: $model.useSinceDate)
                        DatePicker("Since", selection: $model.sinceDate, displayedComponents: .date)
                            .labelsHidden()
                            .disabled(!model.useSinceDate)
                            .padding(.leading, 20)
                        Toggle("Also make an HTML report", isOn: $model.makeHTML)
                        Toggle("Leave out tracking numbers", isOn: $model.leaveOutTracking)
                        Toggle("Exclude orders with 0 item(s)", isOn: $model.excludeEmptyOrders)
                            .help("Orders whose emails gave no items aren't written to the JSON, CSV and HTML files.")
                        Toggle("Start fresh (forget orders from earlier runs)", isOn: $model.fresh)
                            .help("Normally, orders found in an earlier run are kept even if their emails have since been deleted.")
                        Toggle("Save matched emails for troubleshooting", isOn: $model.saveEmailText)
                            .help("Saves the text of every LEGO order email, with what the app read from it. Contains your order details and address.")
                        if model.saveEmailText {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("In \(model.display(model.matchedEmailsBase))")
                                    .font(.callout)
                                    .lineLimit(2).truncationMode(.middle)
                                    .textSelection(.enabled)
                                HStack {
                                    Button("Browse…") { model.chooseMatchedEmailsFolder() }
                                    Button("Same as Save files to") { model.resetMatchedEmailsFolder() }
                                        .disabled(model.matchedEmailsParent == nil)
                                }
                                Text("Each run makes a new folder there: \(matchedEmailsFolderPrefix)1, \(matchedEmailsFolderPrefix)2, …")
                                    .font(.caption).foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .padding(.leading, 20)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(6)
                }
                .disabled(model.isBusy)

                controls

                Text(model.status)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                Divider()

                VStack(alignment: .leading, spacing: 8) {
                    Text("Results").font(.headline)
                    Button { model.openReport() } label: { Label("Open HTML report", systemImage: "doc.richtext") }
                        .disabled(!model.reportExists)
                    Button { model.openDataFolder() } label: { Label("Show files in Finder", systemImage: "folder") }
                    if model.lastTextDir != nil {
                        Button { model.openTextFolder() } label: { Label("Show saved email text", systemImage: "envelope.open") }
                    }
                    Button { model.openLog() } label: { Label("Open log file", systemImage: "doc.text") }
                }
                .buttonStyle(.link)

                Text("Version \(legoMailVersion)").font(.caption2).foregroundStyle(.tertiary)
            }
            .padding(16)
        }
    }

    private func accessWarning(_ problem: MailAccessProblem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            switch problem {
            case .needsFullDiskAccess:
                Label("Full Disk Access needed", systemImage: "lock.shield").font(.headline)
                Text("macOS protects your Mail folder. To let this app read it:")
                    .fixedSize(horizontal: false, vertical: true)
                Text("1. Click Open Privacy Settings.\n2. Turn on LEGO Mail Orders under Full Disk Access (use + to add it if it isn't listed).\n3. Quit and reopen this app.")
                    .font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
                HStack {
                    Button("Open Privacy Settings") { model.openFullDiskAccessSettings() }
                        .buttonStyle(.borderedProminent)
                    Button("Check again") { model.checkAccess() }
                }
            case .notFound:
                Label("Mail folder not found", systemImage: "questionmark.folder").font(.headline)
                Text(problem.description).font(.callout).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder private var controls: some View {
        switch model.phase {
        case .idle:
            Button { model.start() } label: {
                Label("Start", systemImage: "play.fill").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
            .disabled(model.accessProblem != nil)
        case .running, .stopping:
            HStack {
                ProgressView().controlSize(.small)
                Button(role: .destructive) { model.stop() } label: {
                    Label("Stop", systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                .controlSize(.large)
                .disabled(model.phase == .stopping)
            }
        }
    }

    // MARK: Log

    private var logView: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Progress").font(.caption.bold())
                Spacer()
                Button("Copy") { model.copyLog() }.buttonStyle(.borderless).font(.caption)
            }
            .padding(.horizontal, 10).padding(.vertical, 4)
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 1) {
                        ForEach(model.log) { line in
                            Text(line.text.isEmpty ? " " : line.text)
                                .font(.system(.caption, design: .monospaced))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id(line.id)
                        }
                    }
                    .textSelection(.enabled)
                    .padding(8)
                }
                .onChange(of: model.log.last?.id) { id in
                    if let id { proxy.scrollTo(id, anchor: .bottom) }
                }
            }
            .background(Color(nsColor: .textBackgroundColor))
        }
    }
}
