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

@main
struct SparkWidgets: WidgetBundle {
    var body: some Widget {
        ListenWidget()
        if #available(iOS 18.0, *) {
            ListenControl()
        }
    }
}
