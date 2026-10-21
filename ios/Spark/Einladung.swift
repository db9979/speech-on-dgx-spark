import SwiftUI

/// Einladungen aus Mails (einladung.py on the Spark, Dominik 2026-10-21 „ja alles umsetzen 1-6“, Punkt 3): a mail
/// with an invitation (.ics) shows a section above its text, like Apple Mail: what, when, where, who invites, the own
/// answer so far and the calendar; „Zusagen“, „Vielleicht“, „Absagen“ (with „Mails senden“ also to the organiser).
/// The Spark checks and writes everything; the app only shows what it answers.
struct EinladungSection: View {
    let id: String
    let folder: String
    @State private var d: [String: Any]?
    @State private var error: String?
    @State private var note: String?
    @State private var busy = false
    @State private var cal = ""
    @State private var reply = true
    @State private var askRemove = false

    private var method: String { d?["method"] as? String ?? "" }
    private var calendars: [(id: String, name: String)] {
        (d?["calendars"] as? [[String: Any]] ?? []).prefix(30).compactMap { c in
            guard let i = c["id"] as? String else { return nil }
            return (i, String((c["name"] as? String ?? "").prefix(80)))
        }
    }
    private var organizer: (name: String, addr: String) {
        let o = d?["organizer"] as? [String: Any] ?? [:]
        return (String((o["name"] as? String ?? "").prefix(80)), String((o["addr"] as? String ?? "").prefix(200)))
    }

    var body: some View {
        Section("Einladung") {
            if let d {
                VStack(alignment: .leading, spacing: 3) {
                    Label { Text(verbatim: (d["title"] as? String).flatMap { $0.isEmpty ? nil : String($0.prefix(200)) } ?? String(localized: "(ohne Titel)")).font(.headline) }
                        icon: { Image(systemName: "calendar.badge.plus").foregroundStyle(Color.accentColor) }
                    Text(verbatim: when(d)).font(.subheadline).foregroundStyle(.secondary)
                    if let place = d["place"] as? String, !place.isEmpty { Text(verbatim: String(place.prefix(200))).font(.subheadline).foregroundStyle(.secondary) }
                    let org = organizer.name.isEmpty ? organizer.addr : organizer.name
                    if !org.isEmpty {
                        Text(verbatim: (method == "cancel" ? String(localized: "Abgesagt von ") : String(localized: "Einladung von ")) + org)
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Text(verbatim: state(d)).font(.subheadline)
                if method == "cancel" {
                    if !(d["in"] as? String ?? "").isEmpty {
                        Button(role: .destructive) { askRemove = true } label: { Label("Aus dem Kalender entfernen", systemImage: "calendar.badge.minus") }
                            .disabled(busy)
                    }
                } else {
                    if (d["in"] as? String ?? "").isEmpty && calendars.count > 1 {
                        Picker("Kalender", selection: $cal) { ForEach(calendars, id: \.id) { Text(verbatim: $0.name).tag($0.id) } }
                    }
                    if d["reply"] as? Bool == true {
                        Toggle(isOn: $reply) { Text(verbatim: String(localized: "Antwort senden an ") + organizer.addr).font(.subheadline) }
                    }
                    HStack(spacing: 8) {
                        if method == "publish" {
                            knopf("In den Kalender", "accept", prominent: true)
                        } else {
                            knopf("Zusagen", "accept", prominent: true)
                            knopf("Vielleicht", "tentative")
                            knopf("Absagen", "decline")
                        }
                    }
                    .disabled(busy || calendars.isEmpty)
                }
                if let note { Text(verbatim: note).font(.footnote).foregroundStyle(.secondary) }
            } else if let error {
                Text(verbatim: error).foregroundStyle(.red).font(.subheadline)
            } else {
                ProgressView()
            }
        }
        .task(id: id) { await load() }
        .confirmationDialog("Den abgesagten Termin aus dem Kalender entfernen?", isPresented: $askRemove, titleVisibility: .visible) {
            Button("Entfernen", role: .destructive) { Task { await take("remove") } }
        }
    }

    private func knopf(_ label: LocalizedStringKey, _ answer: String, prominent: Bool = false) -> some View {
        Group {
            if prominent {
                Button { Task { await take(answer) } } label: { Text(label).frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent)
            } else {
                Button { Task { await take(answer) } } label: { Text(label).frame(maxWidth: .infinity) }.buttonStyle(.bordered)
            }
        }
    }

    private func when(_ d: [String: Any]) -> String {
        let s = Date(timeIntervalSince1970: (d["start"] as? NSNumber)?.doubleValue ?? 0)
        let e = Date(timeIntervalSince1970: (d["end"] as? NSNumber)?.doubleValue ?? 0)
        var out: String
        if d["allday"] as? Bool == true {
            out = s.formatted(.dateTime.weekday(.abbreviated).day().month(.wide).year())
        } else {
            out = s.formatted(.dateTime.weekday(.abbreviated).day().month(.wide).hour().minute())
            if e > s { out += " – " + e.formatted(Calendar.current.isDate(s, inSameDayAs: e) ? Date.FormatStyle.dateTime.hour().minute() : Date.FormatStyle.dateTime.day().month().hour().minute()) }
        }
        if d["repeats"] as? Bool == true { out += " · " + String(localized: "wiederholt sich") }
        return out
    }

    private func state(_ d: [String: Any]) -> String {
        let inCal = String((d["in"] as? String ?? "").prefix(80))
        let mine: String? = ["accepted": String(localized: "Zugesagt"), "tentative": String(localized: "Vielleicht"),
                             "declined": String(localized: "Abgesagt")][d["mine"] as? String ?? ""]
        if method == "cancel" {
            return inCal.isEmpty ? String(localized: "Abgesagt. Steht in keinem Kalender.") : String(localized: "Abgesagt. Steht noch im Kalender „\(inCal)“.")
        }
        if !inCal.isEmpty { return String(localized: "Im Kalender „\(inCal)“") + (mine.map { " · " + $0 } ?? "") }
        return mine ?? String(localized: "Noch nicht im Kalender")
    }

    private func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let got = try await api.object("GET", "api/profile/mail/invite", query: ["id": id, "folder": folder.isEmpty ? "INBOX" : folder], timeout: 90)
            d = got
            if cal.isEmpty { cal = calendars.first?.id ?? "" }
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func take(_ answer: String) async {
        guard let api = SparkAPI.current, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let r = try await api.object("POST", "api/profile/mail/invite",
                                         body: ["id": id, "folder": folder.isEmpty ? "INBOX" : folder, "answer": answer, "calendar": cal,
                                                "reply": reply && (d?["reply"] as? Bool == true)], timeout: 90)
            let inCal = String((r["in"] as? String ?? "").prefix(80))
            d?["in"] = inCal
            if let w = ["accept": "accepted", "tentative": "tentative", "decline": "declined"][answer] { d?["mine"] = w }
            var text = answer == "remove" ? String(localized: "Aus dem Kalender entfernt.")
                : inCal.isEmpty ? String(localized: "Nicht im Kalender.") : String(localized: "Im Kalender „\(inCal)“.")
            if r["replied"] as? Bool == true { text += " " + String(localized: "Antwort gesendet.") }
            note = text
        } catch {
            note = error.localizedDescription
        }
    }
}
