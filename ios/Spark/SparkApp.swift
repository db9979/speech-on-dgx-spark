import SwiftUI
import UserNotifications

@main
struct SparkApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var app = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(app)
                .onOpenURL { app.open($0) }
        }
    }
}

/// Start-up and Apple push: the iPhone's push address goes to the Spark (only with this app's key).
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // notifications that arrive while the app is open: banner, sound and said aloud
        UNUserNotificationCenter.current().delegate = Relay.shared
        Store.share()
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { _ = try? await SparkAPI.current?.pushToken(hex) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("push: not registered:", error.localizedDescription)
    }
}
