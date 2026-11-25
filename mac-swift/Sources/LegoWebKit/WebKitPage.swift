import Foundation
import LegoCore
import WebKit
#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

/// The apps' built-in browser (WebKit, the engine Safari uses), driven for the scraper.
/// Logins are kept in WebKit's normal website-data store, so you stay signed in between runs.
/// Shared by the Mac app and the iPhone/iPad app.
@MainActor
public final class WebKitPage: NSObject, BrowserPage, WKNavigationDelegate, WKUIDelegate {
    public let webView: WKWebView
    /// When set, every page text the scraper reads is also saved here (troubleshooting).
    public var debugDir: URL?
    private var debugCount = 0

    private var currentNav: WKNavigation?
    private var navCommitted = false
    private var navFinished = false
    private var navError: Error?

    public override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        // Present as Safari, so sign-in pages don't treat the app as an unsupported "embedded" browser.
        let os = ProcessInfo.processInfo.operatingSystemVersion.majorVersion
        config.applicationNameForUserAgent = "Version/\(os >= 26 ? os : os + 3).0 Safari/605.1.15"
        webView = WKWebView(frame: CGRect(x: 0, y: 0, width: 1000, height: 800), configuration: config)
        super.init()
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
    }

    // MARK: JavaScript

    /// Shared helpers injected in front of every script.
    private static let prelude = """
    var __vis = function(el) {
      if (!el || !el.getClientRects().length) return false;
      var s = getComputedStyle(el);
      return s.visibility !== 'hidden' && s.display !== 'none';
    };
    var __name = function(el) {
      return (el.getAttribute('aria-label') || el.innerText || el.textContent || el.value || '').replace(/\\s+/g, ' ').trim();
    };
    var __all = function(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)).filter(__vis); };
    var __buttons = function() { return __all('button, [role="button"], input[type="button"], input[type="submit"]'); };
    var __links = function() { return __all('a[href], [role="link"]'); };

    """

    /// Run JavaScript and return its result. Scripts must always return a value (not undefined).
    public func js(_ script: String) async throws -> Any? {
        try await withCheckedThrowingContinuation { cont in
            webView.evaluateJavaScript("(function(){\n" + Self.prelude + script + "\n})()") { result, error in
                if let error { cont.resume(throwing: error) } else { cont.resume(returning: result) }
            }
        }
    }

    private func jsBool(_ script: String) async -> Bool { ((try? await js(script)) as? Bool) ?? false }

    // MARK: BrowserPage

    public func goto(_ url: String, timeout: Double) async throws {
        guard let u = URL(string: url) else { throw ScraperError("bad URL: \(url)") }
        navCommitted = false; navFinished = false; navError = nil
        currentNav = webView.load(URLRequest(url: u))
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            try Task.checkCancellation()
            if let e = navError { throw ScraperError("couldn't load \(url): \(e.localizedDescription)") }
            if navFinished { return }
            // Like Playwright's "domcontentloaded": the page is parsed even if images are still loading.
            if navCommitted, let state = try? await js("return document.readyState;") as? String, state != "loading" { return }
            if Date() > deadline { throw ScraperError("Timeout \(Int(timeout * 1000))ms exceeded.") }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
    }

    public func dismissInterstitials() async {
        for label in ["continue", "reject all"] {
            let clicked = await jsBool("""
            var b = __buttons();
            var hit = b.find(function(el){ return __name(el).toLowerCase() === '\(label)'; })
                   || b.find(function(el){ return __name(el).toLowerCase().indexOf('\(label)') >= 0; });
            if (hit) { hit.click(); return true; }
            return false;
            """)
            if clicked { try? await Task.sleep(nanoseconds: 300_000_000) }
        }
    }

    public func isSignedOut() async -> Bool {
        await jsBool("""
        if ((document.title || '').trim() === 'Sign In') return true;
        return __links().some(function(el){ return __name(el).toLowerCase().indexOf('sign in') >= 0; });
        """)
    }

    public func mainText() async throws -> String {
        let text = (try await js("var m = document.querySelector('main') || document.body; return m ? m.innerText : '';") as? String) ?? ""
        if let dir = debugDir {
            debugCount += 1
            let name = String(format: "%03d", debugCount) + ".txt"
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try? ("URL: \(webView.url?.absoluteString ?? "")\n\n" + text).write(to: dir.appendingPathComponent(name), atomically: true, encoding: .utf8)
        }
        return text
    }

    public func orderLinkCount() async -> Int {
        let n = try? await js("return __links().filter(function(el){ return /^Order Number: T\\d+$/.test(__name(el)); }).length;")
        return (n as? Int) ?? (n as? NSNumber)?.intValue ?? 0
    }

    public func isLoadMoreVisible() async -> Bool {
        await jsBool("return __buttons().some(function(el){ return __name(el).toLowerCase().indexOf('load more') >= 0; });")
    }

    public func clickLoadMore() async throws {
        let ok = try await js("""
        var b = __buttons().find(function(el){ return __name(el).toLowerCase().indexOf('load more') >= 0; });
        if (!b) return false;
        b.scrollIntoView({block: 'center'});
        b.click();
        return true;
        """) as? Bool
        if ok != true { throw ScraperError("Load More button disappeared") }
    }

    public func waitForText(_ pattern: String, timeout: Double) async throws -> Bool {
        let re = try NSRegularExpression(pattern: pattern)
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            try Task.checkCancellation()
            let text = (try? await js("var m = document.querySelector('main') || document.body; return m ? m.innerText : '';") as? String) ?? ""
            for line in text.components(separatedBy: "\n") {
                let t = line.trimmingCharacters(in: .whitespacesAndNewlines)
                if re.firstMatch(in: t, range: NSRange(location: 0, length: (t as NSString).length)) != nil { return true }
            }
            if Date() > deadline { return false }
            try await Task.sleep(nanoseconds: 250_000_000)
        }
    }

    public func waitForLoadMore(timeout: Double) async throws -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            try Task.checkCancellation()
            if await isLoadMoreVisible() { return true }
            if Date() > deadline { return false }
            try await Task.sleep(nanoseconds: 250_000_000)
        }
    }

    public func sleep(_ seconds: Double) async throws {
        try await Task.sleep(nanoseconds: UInt64(max(0, seconds) * 1_000_000_000))
    }

    public var currentURL: String { webView.url?.absoluteString ?? "" }

    /// Sign out of LEGO.com in the built-in browser by deleting all saved website data.
    public func forgetLogin() async {
        let store = WKWebsiteDataStore.default()
        await store.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast)
    }

    // MARK: WKNavigationDelegate

    private func isCurrent(_ nav: WKNavigation?) -> Bool { currentNav == nil || nav === currentNav }

    public func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        if isCurrent(navigation) { navCommitted = true }
    }

    public func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if isCurrent(navigation) { navFinished = true }
    }

    public func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        guard isCurrent(navigation) else { return }
        handle(error)
    }

    public func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard isCurrent(navigation) else { return }
        handle(error)
    }

    private func handle(_ error: Error) {
        let ns = error as NSError
        // Cancelled because the page moved on to another navigation (a redirect): not a failure.
        if ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled { navFinished = true; return }
        if ns.domain == "WebKitErrorDomain" && ns.code == 102 { navFinished = true; return }
        navError = error
    }

    // MARK: WKUIDelegate

    /// Links that would open a new window (target=_blank) open in the same view instead.
    public func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if navigationAction.targetFrame == nil { webView.load(navigationAction.request) }
        return nil
    }

    #if canImport(AppKit)
    public func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                        initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.runModal()
        completionHandler()
    }

    public func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                        initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }
    #elseif canImport(UIKit)
    public func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                        initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        guard present(alert) else { completionHandler(); return }
    }

    public func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                        initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
        guard present(alert) else { completionHandler(false); return }
    }

    /// Shows an alert over whatever is on screen. false if there's nothing to show it on.
    private func present(_ alert: UIAlertController) -> Bool {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        guard var top = scenes.flatMap(\.windows).first(where: \.isKeyWindow)?.rootViewController else { return false }
        while let next = top.presentedViewController { top = next }
        top.present(alert, animated: true)
        return true
    }
    #endif
}
