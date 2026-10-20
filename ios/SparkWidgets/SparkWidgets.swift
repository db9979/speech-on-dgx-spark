import AppIntents
import SwiftUI
import WidgetKit

/// Quick start without opening the app first: the lock screen widget and (iOS 18) the Control Center
/// button open spark-app://listen, and the app listens at once. They carry nothing else.
private let listenURL = URL(string: "spark-app://listen")!

struct ListenEntry: TimelineEntry {
    let date: Date
}

struct ListenProvider: TimelineProvider {
    func placeholder(in context: Context) -> ListenEntry { ListenEntry(date: .now) }

    func getSnapshot(in context: Context, completion: @escaping (ListenEntry) -> Void) {
        completion(ListenEntry(date: .now))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ListenEntry>) -> Void) {
        completion(Timeline(entries: [ListenEntry(date: .now)], policy: .never))
    }
}

struct ListenView: View {
    @Environment(\.widgetFamily) private var family

    var body: some View {
        switch family {
        case .accessoryCircular:
            ZStack {
                AccessoryWidgetBackground()
                Image(systemName: "waveform").font(.title2.weight(.semibold))
            }
            .accessibilityLabel("Spark zuhören")
        case .accessoryRectangular:
            Label("Spark zuhören", systemImage: "waveform").font(.headline)
        case .accessoryInline:
            Label("Spark zuhören", systemImage: "waveform")
        default:
            VStack(spacing: 8) {
                Image(systemName: "waveform").font(.system(size: 40, weight: .semibold))
                Text("Spark zuhören").font(.headline)
            }
        }
    }
}

struct ListenWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "spark.listen", provider: ListenProvider()) { _ in
            ListenView()
                .widgetURL(listenURL)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Spark zuhören")
        .description("Öffnet die App und hört sofort zu.")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryInline, .systemSmall])
    }
}

@available(iOS 18.0, *)
struct ListenControl: ControlWidget {
    var body: some ControlWidgetConfiguration {
        StaticControlConfiguration(kind: "spark.listen.control") {
            ControlWidgetButton(action: OpenURLIntent(listenURL)) {
                Label("Spark zuhören", systemImage: "waveform")
            }
        }
        .displayName("Spark zuhören")
        .description("Öffnet die App und hört sofort zu.")
    }
}

/// Einkauf (Listen Stufe 3, Dominik 2026-10-20 „5a“): the open entries of the shopping list on the home or lock
/// screen. Reads /api/profile/tasks with the iPhone's key (shared keychain group) when iOS refreshes the timeline;
/// the app asks for a refresh whenever a list changes. Tapping opens the app.
struct EinkaufEntry: TimelineEntry {
    let date: Date
    let items: [String]
    /// false: no answer (not paired, Spark not reachable or Listen not released)
    let known: Bool
}

struct EinkaufProvider: TimelineProvider {
    func placeholder(in context: Context) -> EinkaufEntry {
        EinkaufEntry(date: .now, items: ["Milch 2×", "Brot", "Äpfel"], known: true)
    }

    func getSnapshot(in context: Context, completion: @escaping (EinkaufEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<EinkaufEntry>) -> Void) {
        Task {
            let items = try? await SparkAPI.current?.shopping()
            let entry = EinkaufEntry(date: .now, items: items ?? [], known: items != nil)
            completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(30 * 60))))
        }
    }
}

struct EinkaufWidgetView: View {
    let entry: EinkaufEntry
    @Environment(\.widgetFamily) private var family

    private var rows: Int { family == .systemMedium ? 6 : family == .accessoryRectangular ? 2 : 4 }

    var body: some View {
        switch family {
        case .accessoryInline:
            Text("🛒 \(entry.items.count) auf der Einkaufsliste")
        case .accessoryRectangular:
            VStack(alignment: .leading) {
                Text("🛒 Einkauf · \(entry.items.count)").font(.headline).lineLimit(1)
                ForEach(Array(entry.items.prefix(rows).enumerated()), id: \.offset) { _, x in
                    Text(verbatim: x).font(.caption).lineLimit(1)
                }
            }
        default:
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("🛒 Einkauf").font(.headline)
                    Spacer()
                    Text(verbatim: "\(entry.items.count)").font(.headline).foregroundStyle(.secondary)
                }
                if !entry.known {
                    Text("App öffnen").font(.caption).foregroundStyle(.secondary)
                } else if entry.items.isEmpty {
                    Text("Nichts auf der Liste.").font(.caption).foregroundStyle(.secondary)
                }
                ForEach(Array(entry.items.prefix(rows).enumerated()), id: \.offset) { _, x in
                    Text(verbatim: "• " + x).font(.subheadline).lineLimit(1)
                }
                if entry.items.count > rows {
                    Text("und \(entry.items.count - rows) weitere").font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

struct EinkaufWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "spark.einkauf", provider: EinkaufProvider()) { entry in
            EinkaufWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Einkauf")
        .description("Was auf der Einkaufsliste steht.")
        .supportedFamilies([.accessoryInline, .accessoryRectangular, .systemSmall, .systemMedium])
    }
}

@main
struct SparkWidgets: WidgetBundle {
    var body: some Widget {
        ListenWidget()
        EinkaufWidget()
        RoomWidget()
        RoomActivityWidget()
        if #available(iOS 18.0, *) {
            ListenControl()
        }
    }
}
