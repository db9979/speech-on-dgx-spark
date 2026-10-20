import AppKit
import Carbon

/// A key combination for RegisterEventHotKey: virtual key code, Carbon modifiers and how it is shown.
struct Hotkey: Codable, Equatable {
    var keyCode: UInt32
    var mods: UInt32
    var label: String

    func same(as other: Hotkey) -> Bool {
        keyCode == other.keyCode && mods == other.mods
    }
}

enum HotAction: UInt32, CaseIterable, Identifiable {
    case write = 1
    case ask = 2
    case dictate = 3
    case screen = 4
    case mail = 5
    case speak = 6
    case meeting = 7
    case capture = 8

    var id: UInt32 { rawValue }

    /// the part of the contract it belongs to
    var part: String {
        switch self {
        case .write: return "write"
        case .ask: return "ask"
        case .dictate: return "dictate"
        case .screen: return "screen"
        case .mail: return "mail"
        case .speak: return "speak"
        case .meeting: return "meeting"
        case .capture: return "capture"
        }
    }

    var title: String {
        switch self {
        case .write: return "Schreibhilfe"
        case .ask: return "Frag Spark"
        case .dictate: return "Diktieren"
        case .screen: return "Bildschirm fragen"
        case .mail: return "Antwort entwerfen"
        case .speak: return "Vorlesen"
        case .meeting: return "Besprechung"
        case .capture: return "Schnell erfassen"
        }
    }

    /// ⌥⌘S, ⌥⌘A, ⌥⌘D, ⌥⌘B, ⌥⌘M, ⌥⌘L, ⌥⌘R; Schnell erfassen ⌃⌥N
    var standard: Hotkey {
        let mods = UInt32(cmdKey | optionKey)
        switch self {
        case .write: return Hotkey(keyCode: UInt32(kVK_ANSI_S), mods: mods, label: "⌥⌘S")
        case .ask: return Hotkey(keyCode: UInt32(kVK_ANSI_A), mods: mods, label: "⌥⌘A")
        case .dictate: return Hotkey(keyCode: UInt32(kVK_ANSI_D), mods: mods, label: "⌥⌘D")
        case .screen: return Hotkey(keyCode: UInt32(kVK_ANSI_B), mods: mods, label: "⌥⌘B")
        case .mail: return Hotkey(keyCode: UInt32(kVK_ANSI_M), mods: mods, label: "⌥⌘M")
        case .speak: return Hotkey(keyCode: UInt32(kVK_ANSI_L), mods: mods, label: "⌥⌘L")
        case .meeting: return Hotkey(keyCode: UInt32(kVK_ANSI_R), mods: mods, label: "⌥⌘R")
        case .capture: return Hotkey(keyCode: UInt32(kVK_ANSI_N), mods: UInt32(controlKey | optionKey), label: "⌃⌥N")
        }
    }
}

/// The hotkeys live on this Mac only (UserDefaults), never on the Spark.
enum HotkeyStore {
    private static func key(_ a: HotAction) -> String { "hotkey.\(a.part)" }

    static func load() -> [HotAction: Hotkey] {
        var out: [HotAction: Hotkey] = [:]
        for a in HotAction.allCases {
            if let data = UserDefaults.standard.data(forKey: key(a)),
               let hk = try? JSONDecoder().decode(Hotkey.self, from: data) {
                out[a] = hk
            } else {
                out[a] = a.standard
            }
        }
        return out
    }

    static func save(_ hk: Hotkey, for a: HotAction) {
        if let data = try? JSONEncoder().encode(hk) {
            UserDefaults.standard.set(data, forKey: key(a))
        }
    }
}

/// "SpBg"
let hotkeySignature: OSType = 0x5370_4267

/// Global hotkeys through Carbon's RegisterEventHotKey: they need no Accessibility permission.
@MainActor
final class HotkeyCenter {
    static let shared = HotkeyCenter()

    var onPress: ((HotAction) -> Void)?
    private var refs: [HotAction: EventHotKeyRef] = [:]
    private var installed = false

    func install() {
        guard !installed else { return }
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let status = InstallEventHandler(GetApplicationEventTarget(), hotkeyCallback, 1, &spec, nil, nil)
        installed = status == noErr
    }

    /// false when the combination is taken (by macOS or another program)
    @discardableResult
    func register(_ action: HotAction, _ hk: Hotkey) -> Bool {
        unregister(action)
        var ref: EventHotKeyRef?
        let id = EventHotKeyID(signature: hotkeySignature, id: action.rawValue)
        let status = RegisterEventHotKey(hk.keyCode, hk.mods, id, GetApplicationEventTarget(), 0, &ref)
        guard status == noErr, let ref else { return false }
        refs[action] = ref
        return true
    }

    func unregister(_ action: HotAction) {
        if let r = refs.removeValue(forKey: action) {
            UnregisterEventHotKey(r)
        }
    }

    func unregisterAll() {
        for a in HotAction.allCases { unregister(a) }
    }

    func fire(_ id: UInt32) {
        guard let a = HotAction(rawValue: id), refs[a] != nil else { return }
        onPress?(a)
    }
}

private func hotkeyCallback(_ call: EventHandlerCallRef?, _ event: EventRef?, _ data: UnsafeMutableRawPointer?) -> OSStatus {
    guard let event else { return OSStatus(eventNotHandledErr) }
    var hk = EventHotKeyID()
    let status = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                                   nil, MemoryLayout<EventHotKeyID>.size, nil, &hk)
    guard status == noErr, hk.signature == hotkeySignature else { return OSStatus(eventNotHandledErr) }
    let id = hk.id
    Task { @MainActor in
        HotkeyCenter.shared.fire(id)
    }
    return noErr
}

/// How a pressed key is shown ("⌥⌘S", "⌃⇧F5").
enum KeyNames {
    static let named: [Int: String] = [
        kVK_F1: "F1", kVK_F2: "F2", kVK_F3: "F3", kVK_F4: "F4", kVK_F5: "F5", kVK_F6: "F6",
        kVK_F7: "F7", kVK_F8: "F8", kVK_F9: "F9", kVK_F10: "F10", kVK_F11: "F11", kVK_F12: "F12",
        kVK_Space: "Leertaste", kVK_Return: "↩", kVK_Tab: "⇥", kVK_Delete: "⌫", kVK_ForwardDelete: "⌦",
        kVK_LeftArrow: "←", kVK_RightArrow: "→", kVK_UpArrow: "↑", kVK_DownArrow: "↓",
        kVK_Home: "↖", kVK_End: "↘", kVK_PageUp: "⇞", kVK_PageDown: "⇟",
    ]

    static func modifierLabel(_ flags: NSEvent.ModifierFlags) -> String {
        var s = ""
        if flags.contains(.control) { s += "⌃" }
        if flags.contains(.option) { s += "⌥" }
        if flags.contains(.shift) { s += "⇧" }
        if flags.contains(.command) { s += "⌘" }
        return s
    }

    static func carbonMods(_ flags: NSEvent.ModifierFlags) -> UInt32 {
        var m = 0
        if flags.contains(.control) { m |= controlKey }
        if flags.contains(.option) { m |= optionKey }
        if flags.contains(.shift) { m |= shiftKey }
        if flags.contains(.command) { m |= cmdKey }
        return UInt32(m)
    }

    static func keyLabel(_ e: NSEvent) -> String {
        if let n = named[Int(e.keyCode)] { return n }
        let c = (e.charactersIgnoringModifiers ?? "").uppercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if !c.isEmpty, c.unicodeScalars.allSatisfy({ $0.properties.generalCategory != .control }) { return c }
        return "Taste \(e.keyCode)"
    }
}

/// Records a new combination in the settings window. While recording, the global hotkeys are off,
/// so the combination reaches this window.
@MainActor
final class HotkeyRecorder: ObservableObject {
    @Published private(set) var recording: HotAction?
    @Published var hint = ""
    private var monitor: Any?

    func start(_ a: HotAction) {
        stop()
        recording = a
        hint = "Neue Tastenkombination drücken (Esc bricht ab)."
        HotkeyCenter.shared.unregisterAll()
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
            guard let self else { return e }
            self.take(e)
            return nil
        }
    }

    func stop() {
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
        if recording != nil {
            recording = nil
            AppModel.shared.applyHotkeys()
        }
    }

    private func take(_ e: NSEvent) {
        guard let a = recording else { return }
        if Int(e.keyCode) == kVK_Escape {
            hint = ""
            stop()
            return
        }
        let flags = e.modifierFlags.intersection(.deviceIndependentFlagsMask)
        guard flags.contains(.command) || flags.contains(.option) || flags.contains(.control) else {
            hint = "Bitte mit ⌘, ⌥ oder ⌃ kombinieren (⇧ allein reicht nicht)."
            return
        }
        let hk = Hotkey(keyCode: UInt32(e.keyCode), mods: KeyNames.carbonMods(flags),
                        label: KeyNames.modifierLabel(flags) + KeyNames.keyLabel(e))
        stop()
        hint = AppModel.shared.setHotkey(a, hk) ?? ""
    }
}
