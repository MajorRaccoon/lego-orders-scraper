import LegoCore
import SwiftUI
import WebKit

/// Hosts the app's WKWebView inside SwiftUI.
struct WebViewHost: NSViewRepresentable {
    let webView: WKWebView
    func makeNSView(context: Context) -> WKWebView { webView }
    func updateNSView(_ nsView: WKWebView, context: Context) {}
}

struct ContentView: View {
    @EnvironmentObject var model: AppModel
    @State private var confirmForget = false

    var body: some View {
        HSplitView {
            sidebar
                .frame(minWidth: 300, idealWidth: 320, maxWidth: 380)
            VSplitView {
                browser.frame(minHeight: 360, maxHeight: .infinity).layoutPriority(1)
                logView.frame(minHeight: 120, idealHeight: 180, maxHeight: 320)
            }
            .frame(minWidth: 520)
        }
        .frame(minWidth: 900, minHeight: 620)
    }

    // MARK: Sidebar

    private var sidebar: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("LEGO Order Scraper").font(.title2.bold())
                    Text("Downloads your own LEGO.com order history.").font(.callout).foregroundStyle(.secondary)
                }

                GroupBox("What to fetch") {
                    VStack(alignment: .leading, spacing: 10) {
                        Toggle("Only orders placed on or after", isOn: $model.useSinceDate)
                        DatePicker("Since", selection: $model.sinceDate, displayedComponents: .date)
                            .labelsHidden()
                            .disabled(!model.useSinceDate)
                            .padding(.leading, 20)
                        HStack {
                            Text("Max orders")
                            TextField("all", text: $model.maxOrdersText)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 70)
                            Text("(blank = all)").foregroundStyle(.secondary).font(.caption)
                        }
                        Toggle("Refetch everything (ignore saved progress)", isOn: $model.fresh)
                        Toggle("Also make an HTML report", isOn: $model.makeHTML)
                        Toggle("Leave out tracking numbers", isOn: $model.leaveOutTracking)
                            .help("Tracking numbers are left blank in the JSON, CSV and HTML files.")
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(6)
                }
                .disabled(model.isBusy)

                DisclosureGroup("Advanced") {
                    VStack(alignment: .leading, spacing: 8) {
                        secondsField("Wait between orders", value: $model.delay)
                        secondsField("Wait after Load More", value: $model.loadMoreDelay)
                        secondsField("Wait for Load More to reappear", value: $model.loadMoreFinalWait)
                        Toggle("Save page text for troubleshooting", isOn: $model.savePageText)
                            .help("Saves each page the app reads to a page-text folder in the data folder. Useful if orders come out wrong.")
                    }
                    .padding(.top, 6)
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
                    Button { model.openLog() } label: { Label("Open log file", systemImage: "doc.text") }
                }
                .buttonStyle(.link)

                Divider()

                Button(role: .destructive) { confirmForget = true } label: { Label("Forget saved LEGO login", systemImage: "person.crop.circle.badge.xmark") }
                    .buttonStyle(.link)
                    .disabled(model.isBusy)
                    .confirmationDialog("Forget your saved LEGO.com login?", isPresented: $confirmForget) {
                        Button("Forget login", role: .destructive) { model.forgetLogin() }
                    } message: {
                        Text("You'll need to log in again on the next run. Your saved orders are not deleted.")
                    }

                Text("Version \(legoSwiftVersion)").font(.caption2).foregroundStyle(.tertiary)
            }
            .padding(16)
        }
    }

    private func secondsField(_ label: String, value: Binding<Double>) -> some View {
        HStack {
            Text(label)
            Spacer()
            TextField("", value: value, format: .number.precision(.fractionLength(0...2)))
                .textFieldStyle(.roundedBorder)
                .frame(width: 56)
                .multilineTextAlignment(.trailing)
            Text("s").foregroundStyle(.secondary)
        }
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
        case .waitingForLogin:
            VStack(alignment: .leading, spacing: 8) {
                Label("Log in to LEGO.com in the browser on the right, then go to My Orders.", systemImage: "person.badge.key")
                    .fixedSize(horizontal: false, vertical: true)
                Button { model.confirmLoggedIn() } label: {
                    Text("I've logged in, continue").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                Button("Stop") { model.stop() }
            }
            .padding(10)
            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
        case .running, .stopping:
            HStack {
                ProgressView().controlSize(.small)
                Button(role: .destructive) { model.stop() } label: {
                    Label(model.phase == .stopping ? "Stop now" : "Stop", systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                .controlSize(.large)
            }
        }
    }

    // MARK: Browser and log

    private var browser: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "globe").foregroundStyle(.secondary)
                Text("LEGO.com").font(.caption.bold())
                Spacer()
                Button { model.page.webView.goBack() } label: { Image(systemName: "chevron.left") }
                    .disabled(model.isBusy)
                Button { model.goToOrdersPage() } label: { Label("My Orders", systemImage: "list.bullet.rectangle") }
                    .disabled(model.isBusy)
            }
            .buttonStyle(.borderless)
            .padding(.horizontal, 10).padding(.vertical, 6)
            Divider()
            WebViewHost(webView: model.page.webView)
        }
    }

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
