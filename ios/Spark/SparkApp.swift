import SwiftUI
import UserNotifications

@main
struct SparkApp: App {
    @StateObject private var app = AppState()

    init() {
        // reminders that ring while the app is open: banner, sound and said aloud
        UNUserNotificationCenter.current().delegate = Relay.shared
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(app)
                .onOpenURL { app.open($0) }
        }
    }
}
