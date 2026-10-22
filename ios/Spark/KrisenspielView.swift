import SwiftUI

// ---------------------------------------------------------------- IT-Krisenspiel (krisenspiel.py, plan krisenspiel Paket 7)
/// The crisis game in the app: the values on top, the systems, the moves as buttons, the chronicle, the console with a
/// key bar and the end with its debrief. Every value and every rule comes from the Spark (the same game as on the
/// panel's page Krisenspiel); the app only shows texts (Text(verbatim:)) and sends the move the player tapped or typed.
/// Opens with the admin's release of the game (iphone.THINGS "krisenspiel"); guides, the inspector and inviting others
/// stay on the panel's page („Im Panel öffnen“).
struct KsAsset: Identifiable {
    let id: String
    let name: String
    let kind: String
    let status: String
    let details: String
}

struct KsMove: Identifiable {
    let id: String
    let label: String
    let free: Bool
    let why: String
}

struct KsEvent: Identifiable {
    let id: Int
    let kind: String
    let minute: Int
    let text: String
}

struct KsLine: Identifiable {
    let id: Int
    let err: Bool
    let text: String
}

struct KsBar: Identifiable {
    let id: String
    let value: Int
    let total: Int
    let shown: String
    let bad: Bool
}

struct KsChallenge: Identifiable {
    let id: String
    let name: String
    let scenario: String
    let mine: String
}

@MainActor
final class KrisenspielModel: ObservableObject {
    @Published var loading = true
    @Published var busy = false
    @Published var error: String?
    @Published var running = false
    @Published var title = ""
    @Published var turn = 0
    @Published var minute = 0
    @Published var head = ""
    @Published var bars: [KsBar] = []
    @Published var result = ""
    @Published var damage = ""
    @Published var assets: [KsAsset] = []
    @Published var moves: [KsMove] = []
    @Published var hint = ""
    @Published var events: [KsEvent] = []
    @Published var lines: [KsLine] = []
    @Published var host = ""
    @Published var consoleOnly = false
    @Published var end: [String: Any]?
    @Published var challenges: [KsChallenge] = []
    /// Kampagnen (Paket 9): the running campaign as one line and its next chapter, else the campaigns to start
    @Published var campaign = ""
    @Published var campaignNext = ""
    @Published var campaigns: [KsChallenge] = []

    let en = Locale.current.language.languageCode?.identifier == "en"

    /// a [German, English] pair of the Spark in the app's language
    func p(_ x: Any?) -> String {
        guard let a = x as? [String] , a.count == 2 else { return x as? String ?? "" }
        return en ? a[1] : a[0]
    }

    static func euro(_ n: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.locale = Locale(identifier: "de_DE")
        return (f.string(from: NSNumber(value: n)) ?? String(n)) + " €"
    }

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            show(try await api.object("GET", "api/profile/krisenspiel"))
            error = nil
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    private func send(_ path: String, _ body: [String: Any]) async {
        guard let api = SparkAPI.current, !busy else { return }
        busy = true
        defer { busy = false }
        var b = body
        b["lang"] = en ? "en" : "de"
        do {
            show(try await api.object("POST", path, body: b))
            error = nil
        } catch {
            self.error = error.localizedDescription
            await load()
        }
    }

    func move(_ id: String) async { await send("api/profile/krisenspiel/zug", ["aktion": id, "zug": turn]) }

    func type(_ line: String) async {
        let l = String(line.prefix(200))
        if !l.trimmingCharacters(in: .whitespaces).isEmpty { await send("api/profile/krisenspiel/konsole", ["zeile": l, "zug": turn]) }
    }

    func start(challenge: String?) async {
        if let c = challenge { await send("api/profile/krisenspiel/neu", ["herausforderung": c]) }
        else { await send("api/profile/krisenspiel/neu", ["szenario": "zufall"]) }
    }

    func startCampaign(_ id: String) async { await send("api/profile/krisenspiel/neu", ["kampagne": id]) }

    private func show(_ d: [String: Any]) {
        if let k = d["kampagne"] as? [String: Any] {
            let n = (k["n"] as? NSNumber)?.intValue ?? 0
            let at = ((k["kapitel"] as? NSNumber)?.intValue ?? 0) + 1
            campaign = p(k["titel"]) + (en ? " · chapter \(at) of \(n)" : " · Kapitel \(at) von \(n)")
            campaignNext = p((k["naechstes"] as? [String: Any])?["text"])
        } else {
            campaign = ""
            campaignNext = ""
        }
        campaigns = (d["kampagnen"] as? [[String: Any]] ?? []).compactMap { k in
            guard let id = k["id"] as? String else { return nil }
            return KsChallenge(id: id, name: p(k["titel"]), scenario: p(k["kurz"]), mine: "")
        }
        challenges = (d["herausforderungen"] as? [[String: Any]] ?? []).compactMap { h in
            guard let art = h["art"] as? String else { return nil }
            let me = h["ich"] as? [String: Any]
            let mine = me.map { m in
                let pts = (m["punkte"] as? NSNumber)?.intValue ?? 0
                return (en ? "First try: " : "Erster Versuch: ") + "\(pts) · " + (m["note"] as? String ?? "")
            } ?? ""
            return KsChallenge(id: art, name: p(h["name"]), scenario: p(h["titel"]), mine: mine)
        }
        guard let g = d["spiel"] as? [String: Any] else {
            running = false
            end = nil
            return
        }
        title = p(g["titel"])
        turn = (g["zug"] as? NSNumber)?.intValue ?? 0
        minute = (g["min"] as? NSNumber)?.intValue ?? 0
        consoleOnly = (g["modus"] as? String) == "konsole"
        head = (en ? "Move \(turn) · minute \(minute)" : "Zug \(turn) · Minute \(minute)") + ((g["heraus"] as? String) != nil ? (en ? " · challenge" : " · Herausforderung") : "")
        let m = g["m"] as? [String: Any] ?? [:]
        func n(_ k: String) -> Int { (m[k] as? NSNumber)?.intValue ?? 0 }
        bars = [KsBar(id: en ? "Time" : "Zeit", value: n("zeit"), total: max(1, n("zeit_start")), shown: "\(n("zeit")) min",
                      bad: n("zeit") * 4 < n("zeit_start")),
                KsBar(id: "Stress", value: n("stress"), total: 100, shown: "\(n("stress")) %", bad: n("stress") >= 75),
                KsBar(id: en ? "Trust" : "Vertrauen", value: n("vertrauen"), total: 100, shown: "\(n("vertrauen")) %", bad: n("vertrauen") < 30),
                KsBar(id: en ? "Morale" : "Moral", value: n("moral"), total: 100, shown: "\(n("moral")) %", bad: n("moral") < 30),
                KsBar(id: "Budget", value: n("budget"), total: max(1, n("budget_start")), shown: Self.euro(n("budget")),
                      bad: n("budget") * 5 < n("budget_start"))]
        damage = Self.euro(n("kosten"))
        assets = (g["assets"] as? [[String: Any]] ?? []).prefix(30).map { a in
            KsAsset(id: a["id"] as? String ?? UUID().uuidString, name: a["name"] as? String ?? "", kind: p(a["typ"]),
                    status: a["status"] as? String ?? "", details: p(a["details"]))
        }
        moves = (g["aktionen"] as? [[String: Any]] ?? []).prefix(40).compactMap { a in
            guard let id = a["id"] as? String else { return nil }
            return KsMove(id: id, label: p(a["label"]), free: a["frei"] as? Bool ?? false, why: p(a["warum"]))
        }
        hint = (g["tipp"] as? [String: Any]).map { p($0["label"]) } ?? ""
        let chron = g["chronik"] as? [[String: Any]] ?? []
        events = Array(chron.suffix(40).enumerated()).reversed().map { i, c in
            KsEvent(id: i, kind: c["art"] as? String ?? "", minute: (c["min"] as? NSNumber)?.intValue ?? 0,
                    text: (c["erzaehlt"] as? String) ?? p(c["text"]))
        }
        let k = g["konsole"] as? [String: Any] ?? [:]
        host = k["host"] as? String ?? ""
        lines = (k["zeilen"] as? [[String: Any]] ?? []).suffix(60).enumerated().map { i, z in
            KsLine(id: i, err: (z["k"] as? String) == "err", text: z["s"] as? String ?? "")
        }
        end = g["ende"] as? [String: Any]
        running = end == nil
        if let e = end {
            let pts = (e["punkte"] as? NSNumber)?.intValue ?? 0
            result = (e["note"] as? String ?? "") + " · " + String(pts) + (en ? " points" : " Punkte")
        }
    }

    static func tint(_ status: String) -> Color {
        switch status {
        case "Online": return .green
        case "Degraded": return .orange
        case "Isolated": return .purple
        default: return .red
        }
    }
}

struct KrisenspielView: View {
    @StateObject private var m = KrisenspielModel()
    @State private var typed = ""
    @FocusState private var typing: Bool

    var body: some View {
        List {
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if !m.running && m.end == nil && !m.loading {
                Section {
                    Text("Noch kein Spiel. Starte eine Herausforderung oder ein Überraschungs-Szenario; alles Weitere gibt es auf der Seite Krisenspiel im Panel.")
                        .foregroundStyle(.secondary)
                }
            }
            if m.running || m.end != nil {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(verbatim: m.title).font(.headline)
                        Text(verbatim: m.head).font(.caption).foregroundStyle(.secondary)
                        ForEach(m.bars) { b in
                            HStack {
                                Text(verbatim: b.id).font(.caption).frame(width: 80, alignment: .leading)
                                ProgressView(value: Double(max(0, min(b.value, b.total))), total: Double(b.total))
                                    .tint(b.bad ? Color.red : Color.accentColor)
                                Text(verbatim: b.shown).font(.caption.monospacedDigit()).frame(width: 84, alignment: .trailing)
                            }
                        }
                        HStack {
                            Text("Schaden").font(.caption)
                            Spacer()
                            Text(verbatim: m.damage).font(.caption.bold())
                        }
                    }
                }
            }
            if let e = m.end {
                Section("Ergebnis") {
                    Text(verbatim: m.result).font(.title2.bold())
                    ForEach(Array((e["gruende"] as? [[String]] ?? []).enumerated()), id: \.offset) { _, x in
                        Text(verbatim: m.p(x)).font(.callout)
                    }
                }
                let lessons = e["lehren"] as? [[String: Any]] ?? []
                if !lessons.isEmpty {
                    Section("Nachbesprechung") {
                        ForEach(Array(lessons.enumerated()), id: \.offset) { _, x in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: ((x["gut"] as? Bool ?? false) ? "✓ " : "→ ") + m.p(x["text"]))
                                Text(verbatim: x["bezug"] as? String ?? "").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            if m.running {
                if !m.hint.isEmpty {
                    Section { Text(verbatim: (m.en ? "Hint: " : "Tipp: ") + m.hint).foregroundStyle(.blue) }
                }
                if !m.consoleOnly && !m.moves.isEmpty {
                    Section("Züge") {
                        ForEach(m.moves) { a in
                            Button { Task { await m.move(a.id) } } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(verbatim: a.label)
                                    if !a.free { Text(verbatim: a.why).font(.caption).foregroundStyle(.secondary) }
                                }
                            }
                            .disabled(!a.free || m.busy)
                        }
                    }
                }
                Section("Konsole") {
                    ScrollView(.horizontal) {
                        VStack(alignment: .leading, spacing: 1) {
                            ForEach(m.lines) { l in
                                Text(verbatim: l.text).font(.caption.monospaced()).foregroundStyle(l.err ? .red : .primary)
                            }
                        }
                    }
                    .defaultScrollAnchor(.bottom)
                    HStack {
                        Text(verbatim: m.host + "$").font(.caption.monospaced()).foregroundStyle(.secondary)
                        TextField("Befehl", text: $typed)
                            .font(.body.monospaced())
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .focused($typing)
                            .submitLabel(.send)
                            .onSubmit { let l = typed; typed = ""; Task { await m.type(l) }; typing = true }
                    }
                }
                Section("Systeme") {
                    ForEach(m.assets) { a in
                        HStack(alignment: .top) {
                            Circle().fill(KrisenspielModel.tint(a.status)).frame(width: 10, height: 10).padding(.top, 5)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: a.name).font(.subheadline.weight(.semibold))
                                Text(verbatim: a.kind + " · " + a.status + (a.details.isEmpty ? "" : " · " + a.details))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            if !m.events.isEmpty {
                Section("Chronik") {
                    ForEach(m.events) { c in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: (m.en ? "minute " : "Minute ") + String(c.minute)).font(.caption).foregroundStyle(.secondary)
                            Text(verbatim: c.text).font(.callout)
                        }
                    }
                }
            }
            if !m.running {
                Section("Kampagne") {
                    if m.campaign.isEmpty {
                        ForEach(m.campaigns) { k in
                            Button { Task { await m.startCampaign(k.id) } } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(verbatim: k.name)
                                    Text(verbatim: k.scenario).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            .disabled(m.busy)
                        }
                    } else {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: m.campaign)
                            if !m.campaignNext.isEmpty { Text(verbatim: m.campaignNext).font(.caption).foregroundStyle(.secondary) }
                        }
                        Button("Nächstes Kapitel") { Task { await m.startCampaign("weiter") } }.disabled(m.busy)
                    }
                }
                Section("Herausforderungen") {
                    ForEach(m.challenges) { h in
                        Button { Task { await m.start(challenge: h.id) } } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: h.name)
                                Text(verbatim: h.scenario + (h.mine.isEmpty ? "" : " · " + h.mine)).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .disabled(m.busy)
                    }
                    Button("Überraschungs-Szenario starten") { Task { await m.start(challenge: nil) } }.disabled(m.busy)
                }
            }
            if let url = SparkAPI.panelLink("me=ksbox") {
                Section { Link("Im Panel öffnen (Anleitung, Inspector, gemeinsam spielen)", destination: url) }
            }
        }
        .navigationTitle("Krisenspiel")
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                ForEach(["help", "hosts", "ssh ", "sudo ", "|", "-h"], id: \.self) { w in
                    Button(w.trimmingCharacters(in: .whitespaces)) { typed += w }
                }
                Spacer()
            }
        }
        .refreshable { await m.load() }
        .task { await m.load() }
        .overlay { if m.loading { ProgressView() } }
    }
}
