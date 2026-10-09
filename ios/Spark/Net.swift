import Foundation
import Network

/// Typed questions that wait while the Spark cannot be reached (on this iPhone only, at most 10,
/// each one day at most; unpairing empties it so nothing goes to another Spark later).
enum Outbox {
    struct Item: Codable, Equatable {
        let text: String
        let t: Date
    }

    static let max = 10
    static let maxChars = 2000
    static let keep: TimeInterval = 24 * 3600
    private static let key = "outbox"

    static func load(now: Date = Date()) -> [Item] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let list = try? JSONDecoder().decode([Item].self, from: data) else { return [] }
        return list.filter { now.timeIntervalSince($0.t) < keep }
    }

    static func save(_ list: [Item]) {
        UserDefaults.standard.set(try? JSONEncoder().encode(Array(list.suffix(max))), forKey: key)
    }

    /// false when the box is full
    static func add(_ text: String) -> Bool {
        var list = load()
        guard list.count < max else { return false }
        list.append(Item(text: String(text.prefix(maxChars)), t: Date()))
        save(list)
        return true
    }

    static func clear() { UserDefaults.standard.removeObject(forKey: key) }
}

/// Whether the iPhone has a network at all; the Spark itself is checked with hello.
final class NetWatch {
    private let monitor = NWPathMonitor()
    /// Main thread: the network came back (true) or went away (false).
    var onChange: ((Bool) -> Void)?

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let up = path.status == .satisfied
            DispatchQueue.main.async { self?.onChange?(up) }
        }
        monitor.start(queue: DispatchQueue(label: "spark.net"))
    }

    /// Errors that mean "the Spark cannot be reached" (not: the Spark said no).
    static func offline(_ e: Error) -> Bool {
        guard let u = e as? URLError else { return false }
        let codes: [URLError.Code] = [.notConnectedToInternet, .cannotConnectToHost, .cannotFindHost, .timedOut,
                                      .networkConnectionLost, .dnsLookupFailed, .internationalRoamingOff,
                                      .dataNotAllowed, .secureConnectionFailed, .cannotLoadFromNetwork]
        return codes.contains(u.code)
    }
}
