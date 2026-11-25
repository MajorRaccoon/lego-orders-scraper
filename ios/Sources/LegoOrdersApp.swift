import SwiftUI

/// LEGO Orders for iPhone and iPad: fetch your LEGO.com order history (Scrape tab) and read
/// the HTML report (Report tab). Same scraper and report as the Mac app.
@main
struct LegoOrdersApp: App {
    @StateObject private var model = OrdersModel()

    var body: some Scene {
        WindowGroup {
            TabView {
                ScrapeView()
                    .tabItem { Label("Scrape", systemImage: "arrow.down.circle") }
                ReportView()
                    .tabItem { Label("Report", systemImage: "doc.richtext") }
            }
            .environmentObject(model)
        }
    }
}
