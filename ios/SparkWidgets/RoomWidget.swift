import ActivityKit
import AppIntents
import SwiftUI
import WidgetKit

/// Where the profile's devices listen in room mode: "Küche hört zu bis 21:30" or "Niemand hört zu".
/// Reads /api/room/active with the iPhone's key (shared keychain group) when iOS refreshes the
/// timeline; the app asks for a refresh whenever its list changes. Tapping opens the app.
private let roomsURL = URL(string: "spark-app://rooms")!

struct RoomEntry: TimelineEntry {
    let date: Date
    let rooms: [ListeningRoom]
    /// false: no answer (not paired, Spark not reachable or "Raum-Modus in der App zeigen" off)
    let known: Bool
}

struct RoomProvider: TimelineProvider {
    func placeholder(in context: Context) -> RoomEntry {
        RoomEntry(date: .now, rooms: [ListeningRoom(id: "x", name: "Küche", kind: "speaker", until: .now.addingTimeInterval(1800))], known: true)
    }

    func getSnapshot(in context: Context, completion: @escaping (RoomEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<RoomEntry>) -> Void) {
        Task {
            let now = Date()
            let rooms = try? await SparkAPI.current?.rooms()
            var entries = [RoomEntry(date: now, rooms: rooms ?? [], known: rooms != nil)]
            // after each end time the room drops out without asking the Spark again
            for end in Set((rooms ?? []).map(\.until)).sorted() where end > now {
                entries.append(RoomEntry(date: end, rooms: (rooms ?? []).filter { $0.until > end }, known: true))
            }
            let next = now.addingTimeInterval((rooms ?? []).isEmpty ? 30 * 60 : 15 * 60)
            completion(Timeline(entries: entries, policy: .after(next)))
        }
    }
}

struct RoomView: View {
    let entry: RoomEntry
    @Environment(\.widgetFamily) private var family

    private var title: String {
        guard entry.known else { return String(localized: "Raum-Modus") }
        guard !entry.rooms.isEmpty else { return String(localized: "Niemand hört zu") }
        return RoomLive.listening(entry.rooms.map(\.name))
    }

    private var until: Date? { entry.rooms.map(\.until).max() }

    var body: some View {
        switch family {
        case .accessoryInline:
            if let until {
                Text("\(Image(systemName: "ear")) \(title) bis \(until, style: .time)")
            } else {
                Text("\(Image(systemName: "ear")) \(title)")
            }
        case .accessoryRectangular:
            VStack(alignment: .leading) {
                Label(title, systemImage: "ear").font(.headline).lineLimit(1)
                if let until { Text("bis \(until, style: .time)").font(.caption) }
                else if !entry.known { Text("App öffnen").font(.caption) }
            }
        default:
            VStack(alignment: .leading, spacing: 6) {
                Image(systemName: entry.rooms.isEmpty ? "ear" : "ear.badge.waveform")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(entry.rooms.isEmpty ? Color.secondary : Color.green)
                Text(title).font(.headline).lineLimit(2).minimumScaleFactor(0.8)
                if let until {
                    Text("bis \(until, style: .time)").font(.subheadline).foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                    Button(intent: EndRoomsIntent()) {
                        Label("Beenden", systemImage: "stop.fill").font(.caption.weight(.semibold))
                    }
                    .tint(.red)
                } else if !entry.known {
                    Text("Im Panel unter Ich → iPhone-App einschalten").font(.caption).foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

struct RoomWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: RoomLive.widgetKind, provider: RoomProvider()) { entry in
            RoomView(entry: entry)
                .widgetURL(roomsURL)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Raum-Modus")
        .description("Zeigt, wo gerade zugehört wird, und beendet es.")
        .supportedFamilies([.accessoryRectangular, .accessoryInline, .systemSmall])
    }
}

/// Lock screen and Dynamic Island while a device listens (started by the app, see RoomLive).
struct RoomActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RoomActivityAttributes.self) { context in
            RoomLockView(state: context.state, stale: context.isStale)
                .padding()
                .activityBackgroundTint(Color.black.opacity(0.6))
                .activitySystemActionForegroundColor(.white)
                .widgetURL(roomsURL)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Label(RoomLive.label(context.state.names, count: context.state.count), systemImage: "ear.badge.waveform")
                        .font(.headline).foregroundStyle(.green).lineLimit(1)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    RoomCountdown(until: context.state.until, stale: context.isStale)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Button(intent: EndRoomsIntent()) {
                        Label("Raum-Modus beenden", systemImage: "stop.fill")
                    }
                    .tint(.red)
                }
            } compactLeading: {
                Image(systemName: "ear.badge.waveform").foregroundStyle(.green)
            } compactTrailing: {
                RoomCountdown(until: context.state.until, stale: context.isStale).frame(maxWidth: 52)
            } minimal: {
                Image(systemName: "ear.badge.waveform").foregroundStyle(.green)
            }
            .widgetURL(roomsURL)
        }
    }
}

struct RoomCountdown: View {
    let until: Date
    let stale: Bool

    var body: some View {
        if stale || until <= Date() {
            Text("vorbei")
        } else {
            Text(timerInterval: Date()...until, countsDown: true).monospacedDigit()
        }
    }
}

struct RoomLockView: View {
    let state: RoomActivityAttributes.ContentState
    let stale: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "ear.badge.waveform").font(.title2).foregroundStyle(.green)
            VStack(alignment: .leading, spacing: 2) {
                Text(RoomLive.listening(state.names, count: state.count))
                    .font(.headline).foregroundStyle(.white).lineLimit(1)
                HStack(spacing: 4) {
                    Text("bis \(state.until, style: .time) ·")
                    RoomCountdown(until: state.until, stale: stale)
                }
                .font(.subheadline).foregroundStyle(.white.opacity(0.8))
            }
            Spacer(minLength: 8)
            Button(intent: EndRoomsIntent()) {
                Text("Beenden").font(.subheadline.weight(.semibold))
            }
            .tint(.red)
        }
    }
}
