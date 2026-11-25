import SwiftUI
import WebKit

/// The Report tab: the HTML report (same as the Mac app's), with a share button for the
/// report, CSV and JSON files.
struct ReportView: View {
    @EnvironmentObject var model: OrdersModel

    var body: some View {
        NavigationStack {
            Group {
                if model.reportExists {
                    ReportWebView(url: model.htmlURL, version: model.reportVersion)
                        .ignoresSafeArea(edges: .bottom)
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "doc.richtext").font(.system(size: 44)).foregroundStyle(.secondary)
                        Text("No report yet").font(.headline)
                        Text("Go to the Scrape tab and tap Start. The report appears here when it's done.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(32)
                }
            }
            .navigationTitle("Report")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if !model.resultFiles.isEmpty {
                        ShareLink(items: model.resultFiles) { Image(systemName: "square.and.arrow.up") }
                            .accessibilityLabel("Share report and files")
                    }
                }
            }
            .onAppear { model.refreshFiles() }
        }
    }
}

/// Shows the report file. Links inside it (order index, month links, Back to top) stay in the
/// view; "View on LEGO.com" links open in Safari.
struct ReportWebView: UIViewRepresentable {
    let url: URL
    let version: Int

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let view = WKWebView()
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        guard context.coordinator.loadedVersion != version else { return }
        context.coordinator.loadedVersion = version
        view.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var loadedVersion: Int?

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if let target = action.request.url, target.scheme == "http" || target.scheme == "https" {
                UIApplication.shared.open(target)
                decisionHandler(.cancel)
            } else {
                decisionHandler(.allow)
            }
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let target = action.request.url { UIApplication.shared.open(target) }
            return nil
        }
    }
}
