import SwiftUI

/// "Heute" (plan „Bedienung gesamt“ E1): what is due today, from the same endpoint as Ich → Heute in the panel
/// (api/profile/today). Only cards for functions this profile may use; only numbers and short titles.
struct TodayView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var cards: [String: Any] = [:]
    @State private var loaded = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let error {
                    Text(error).foregroundStyle(.red)
                } else if loaded && cards.isEmpty {
                    Text("Hier erscheint, was heute dran ist, sobald der Admin Kalender, Erinnerungen, Nachrichten oder Dokumente für dich einschaltet.")
                        .foregroundStyle(.secondary)
                }
                if let cal = cards["calendar"] as? [String: Any] { calendar(cal) }
                if let r = cards["reminders"] as? [String: Any] {
                    let next = r["next"] as? [String: Any]
                    row("bell", String(localized: "Erinnerungen"), "\(r["count"] as? Int ?? 0)",
                        next.map { when($0["due"]) + " · " + ($0["text"] as? String ?? "") } ?? String(localized: "Keine offen"))
                }
                if let m = cards["messages"] as? [String: Any] {
                    let n = m["unread"] as? Int ?? 0
                    row("envelope", String(localized: "Nachrichten"), "\(n)", n > 0 ? String(localized: "ungelesen") : String(localized: "Alles gelesen"))
                }
                if let d = cards["documents"] as? [String: Any] {
                    let w = d["waiting"] as? Int ?? 0
                    row("doc.text", String(localized: "Dokumente"), "\(d["count"] as? Int ?? 0)",
                        w > 0 ? String(localized: "\(w) Seiten warten aufs Lesen") : "")
                }
                if let m = cards["memory"] as? [String: Any] {
                    row("brain", String(localized: "Gedächtnis"), "\(m["facts"] as? Int ?? 0)", String(localized: "gemerkte Fakten"))
                }
            }
            .navigationTitle("Heute")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    @ViewBuilder private func calendar(_ c: [String: Any]) -> some View {
        let next = c["next"] as? [[String: Any]] ?? []
        if c["connected"] as? Bool == false {
            row("calendar", String(localized: "Termine"), String(localized: "Kalender verbinden"), String(localized: "Im Panel unter Ich → Kalender"))
        } else if next.isEmpty {
            row("calendar", String(localized: "Termine"), String(localized: "Heute und morgen frei"),
                c["error"] as? Bool == true ? String(localized: "Ein Kalender war nicht erreichbar.") : "")
        } else {
            ForEach(Array(next.enumerated()), id: \.offset) { i, e in
                row("calendar", i == 0 ? String(localized: "Termine") : "",
                    e["allday"] as? Bool == true ? String(localized: "ganztägig") : when(e["start"]), e["title"] as? String ?? "")
            }
        }
    }

    private func row(_ icon: String, _ title: String, _ big: String, _ small: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).foregroundStyle(.tint).frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                if !title.isEmpty { Text(title).font(.caption).foregroundStyle(.secondary) }
                Text(big).font(.headline)
                if !small.isEmpty { Text(small).font(.subheadline).foregroundStyle(.secondary) }
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func when(_ v: Any?) -> String {
        guard let t = (v as? NSNumber)?.doubleValue else { return "" }
        let d = Date(timeIntervalSince1970: t)
        let day = Calendar.current.isDateInToday(d) ? String(localized: "Heute")
            : Calendar.current.isDateInTomorrow(d) ? String(localized: "Morgen")
            : d.formatted(.dateTime.weekday(.abbreviated).day().month(.defaultDigits))
        return day + " " + d.formatted(date: .omitted, time: .shortened)
    }

    private func load() async {
        guard let api = SparkAPI.current else { error = String(localized: "Nicht gekoppelt."); return }
        do {
            cards = try await api.today()["cards"] as? [String: Any] ?? [:]
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }
}
