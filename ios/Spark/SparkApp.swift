import SwiftUI

@main
struct SparkApp: App {
    @StateObject private var app = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(app)
                .onOpenURL { app.open($0) }
        }
    }
}
