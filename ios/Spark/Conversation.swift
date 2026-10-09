import Foundation
import SwiftUI
import UIKit

/// Pairing state of the app. A pairing link always asks first which Spark it leads to,
/// so a link from somewhere else cannot quietly send the questions to a strange server.
@MainActor
final class AppState: ObservableObject {
    struct Link: Identifiable {
        let id = UUID()
        let base: URL
        let code: String
    }

    @Published var paired = Store.paired
    @Published var profile = Store.profile
    @Published var busy = false
    @Published var message: String?
    @Published var offered: Link?

    /// spark-app://pair?url=https://...&code=... (from the panel: QR code or link)
    /// spark-app://listen (widget, Control Center): listen right away; it carries nothing else.
    func open(_ url: URL) {
        if url.scheme == "spark-app", url.host == "listen" {
            if paired { Conversation.shared.listenNow() }
            return
        }
        guard url.scheme == "spark-app", url.host == "pair",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
              let raw = items.first(where: { $0.name == "url" })?.value,
              let code = items.first(where: { $0.name == "code" })?.value,
              code.range(of: "^[A-Za-z0-9_-]{20,40}$", options: .regularExpression) != nil,
              let base = Self.checked(raw) else {
            message = String(localized: "Das ist kein gültiger Kopplungs-Link vom Spark.")
            return
        }
        offered = Link(base: base, code: code)
    }

    /// Only https with a real certificate, a host and no path (as the panel makes the link).
    static func checked(_ raw: String) -> URL? {
        guard let u = URL(string: raw.trimmingCharacters(in: .whitespaces)), u.scheme == "https",
              let host = u.host, !host.isEmpty, u.path.isEmpty || u.path == "/", u.query == nil, u.user == nil else { return nil }
        return u
    }

    func pair(_ link: Link) async {
        offered = nil
        busy = true
        defer { busy = false }
        do {
            let r = try await SparkAPI.pair(base: link.base, code: link.code, name: UIDevice.current.name)
            Store.baseURL = link.base
            Store.key = r.key
            Store.profile = r.profile
            Store.language = r.language
            profile = r.profile
            paired = true
            message = nil
        } catch {
            message = error.localizedDescription
        }
    }

    /// Whose key and what the profile allows; nil when the Spark cannot be reached.
    func refresh() async -> Allowed? {
        guard let api = SparkAPI.current, let r = try? await api.hello() else { return nil }
        Store.profile = r.profile
        Store.language = r.language
        profile = r.profile
        return r
    }

    func unpair() {
        Store.forget()
        paired = false
        profile = ""
    }
}

