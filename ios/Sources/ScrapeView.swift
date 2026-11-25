import LegoCore
import SwiftUI
import WebKit

/// Hosts the app's WKWebView inside SwiftUI.
struct WebViewHost: UIViewRepresentable {
    let webView: WKWebView
    func makeUIView(context: Context) -> WKWebView { webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

/// The Scrape tab: Start/Stop and status on top, LEGO.com in the middle (log in there when
/// asked), and the progress log at the bottom. Options are behind the gear button.
struct ScrapeView: View {
    @EnvironmentObject var model: OrdersModel
    @State private var showOptions = false
    @State private var showLog = true

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                controls
                    .padding(.horizontal)
                    .padding(.vertical, 10)
                Divider()
                browserBar
                WebViewHost(webView: model.page.webView)
                    .frame(maxHeight: .infinity)
                Divider()
                logPanel
            }
            .navigationTitle("LEGO Orders")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { showOptions = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Options")
                }
            }
            .sheet(isPresented: $showOptions) {
                OptionsView().environmentObject(model)
            }
        }
    }

    // MARK: Start / Stop / log in

    @ViewBuilder private var controls: some View {
        VStack(alignment: .leading, spacing: 8) {
            switch model.phase {
            case .idle:
                Button { model.start() } label: {
                    Label("Start", systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            case .waitingForLogin:
                Label("Log in to LEGO.com below, then go to My Orders.", systemImage: "person.badge.key")
                    .font(.callout)
                HStack {
                    Button { model.confirmLoggedIn() } label: {
                        Text("I've logged in, continue").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Stop", role: .destructive) { model.stop() }
                        .buttonStyle(.bordered)
                }
                .controlSize(.large)
            case .running, .stopping:
                HStack {
                    ProgressView()
                    Button(role: .destructive) { model.stop() } label: {
                        Label(model.phase == .stopping ? "Stop now" : "Stop", systemImage: "stop.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                }
            }
            Text(model.status)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Browser and log

    private var browserBar: some View {
        HStack(spacing: 16) {
            Image(systemName: "globe").foregroundStyle(.secondary)
            Text("LEGO.com").font(.caption.bold())
            Spacer()
            Button { model.page.webView.goBack() } label: { Image(systemName: "chevron.left") }
                .disabled(model.isBusy)
                .accessibilityLabel("Back")
            Button { model.goToOrdersPage() } label: { Label("My Orders", systemImage: "list.bullet.rectangle") }
                .disabled(model.isBusy)
        }
        .font(.callout)
        .padding(.horizontal)
        .padding(.vertical, 6)
    }

    private var logPanel: some View {
        VStack(spacing: 0) {
            HStack {
                Button {
                    withAnimation { showLog.toggle() }
                } label: {
                    Label("Progress", systemImage: showLog ? "chevron.down" : "chevron.up").font(.caption.bold())
                }
                Spacer()
                Button("Copy") { model.copyLog() }.font(.caption)
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            if showLog {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 1) {
                            ForEach(model.log) { line in
                                Text(line.text.isEmpty ? " " : line.text)
                                    .font(.system(.caption2, design: .monospaced))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .id(line.id)
                            }
                        }
                        .textSelection(.enabled)
                        .padding(.horizontal)
                        .padding(.bottom, 6)
                    }
                    .frame(height: 150)
                    .onChange(of: model.log.last?.id) { id in
                        if let id { proxy.scrollTo(id, anchor: .bottom) }
                    }
                }
            }
        }
        .background(Color(uiColor: .secondarySystemBackground))
    }
}

/// What to fetch, plus the advanced timings and the saved login.
struct OptionsView: View {
    @EnvironmentObject var model: OrdersModel
    @Environment(\.dismiss) private var dismiss
    @State private var confirmForget = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Only orders placed on or after", isOn: $model.useSinceDate)
                    if model.useSinceDate {
                        DatePicker("Since", selection: $model.sinceDate, displayedComponents: .date)
                    }
                    HStack {
                        Text("Max orders")
                        Spacer()
                        TextField("all", text: $model.maxOrdersText)
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                            .frame(width: 90)
                    }
                    Toggle("Refetch everything", isOn: $model.fresh)
                    Toggle("Leave out tracking numbers", isOn: $model.leaveOutTracking)
                } header: {
                    Text("What to fetch")
                } footer: {
                    Text("Normally orders fetched before are kept and only new detail is fetched. \"Refetch everything\" ignores that, for the next run only.")
                }

                Section("Advanced") {
                    secondsStepper("Wait between orders", value: $model.delay)
                    secondsStepper("Wait after Load More", value: $model.loadMoreDelay)
                    secondsStepper("Wait for Load More to reappear", value: $model.loadMoreFinalWait)
                    Toggle("Save page text for troubleshooting", isOn: $model.savePageText)
                }

                Section {
                    Button("Forget saved LEGO login", role: .destructive) { confirmForget = true }
                        .confirmationDialog("Forget your saved LEGO.com login?", isPresented: $confirmForget, titleVisibility: .visible) {
                            Button("Forget login", role: .destructive) { model.forgetLogin() }
                        } message: {
                            Text("You'll need to log in again on the next run. Your saved orders are not deleted.")
                        }
                } footer: {
                    Text("Files are saved in the Files app under On My iPhone (or iPad) > LEGO Orders. Version \(legoSwiftVersion).")
                }
            }
            .disabled(model.isBusy)
            .navigationTitle("Options")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }

    private func secondsStepper(_ label: String, value: Binding<Double>) -> some View {
        Stepper(value: value, in: 0...30, step: 0.5) {
            HStack {
                Text(label)
                Spacer()
                Text("\(value.wrappedValue, specifier: "%.1f") s").foregroundStyle(.secondary)
            }
        }
    }
}
