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
    @Published var invited: Link?

    /// spark-app://pair?url=https://...&code=... (from the panel: QR code or link)
    /// spark-app://join?url=https://...&code=... (an invitation: a new profile and this iPhone's key in one step)
    /// spark-app://listen (widget, Control Center): listen right away; it carries nothing else.
    func open(_ url: URL) {
        if url.scheme == "spark-app", url.host == "listen" {
            if paired { Conversation.shared.listenNow() }
            return
        }
        if url.scheme == "spark-app", url.host == "rooms" {
            // from the room widget or the Live Activity: the app shows the line at the top of the chat
            if paired { Task { await Conversation.shared.refreshRooms(now: true) } }
            return
        }
        if url.scheme == "spark-app", url.host == "join" {
            guard let link = Self.link(url) else {
                message = String(localized: "Das ist kein gültiger Einladungs-Link vom Spark.")
                return
            }
            // an already paired app keeps its profile: an invitation link must not swap it quietly
            guard !paired else {
                Conversation.shared.error = String(localized: "Diese App ist schon gekoppelt. Die Einladung im Browser öffnen oder die App erst in den Einstellungen entkoppeln.")
                return
            }
            message = nil
            invited = link
            return
        }
        guard url.scheme == "spark-app", url.host == "pair", let link = Self.link(url) else {
            message = String(localized: "Das ist kein gültiger Kopplungs-Link vom Spark.")
            return
        }
        offered = link
    }

    /// The Spark's address and the one-time code from a pair or join link.
    static func link(_ url: URL) -> Link? {
        guard let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
              let raw = items.first(where: { $0.name == "url" })?.value,
              let code = items.first(where: { $0.name == "code" })?.value,
              code.range(of: "^[A-Za-z0-9_-]{20,40}$", options: .regularExpression) != nil,
              let base = checked(raw) else { return nil }
        return Link(base: base, code: code)
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

    /// Takes the invitation: the Spark makes the profile and this iPhone's key. Throws with the Spark's
    /// reason (name taken, invitation used up) so the sheet can show it and stay open.
    func join(_ link: Link, name: String, pin: String) async throws {
        busy = true
        defer { busy = false }
        let r = try await SparkAPI.join(base: link.base, code: link.code, name: name, pin: pin, device: UIDevice.current.name)
        Store.baseURL = link.base
        Store.key = r.key
        Store.profile = r.profile
        Store.language = r.language
        profile = r.profile
        invited = nil
        paired = true
        message = nil
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
        Outbox.clear()
        AppleReminders.forget()
        paired = false
        profile = ""
    }
}

