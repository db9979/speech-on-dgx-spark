import AVFoundation
import AppKit
import CoreAudio
import CoreGraphics

/// Part "quiet" (Nicht stören erkennen): every 10 s the Mac looks whether another app uses the camera
/// (AVCaptureDevice.isInUseByAnotherApplication) or the default microphone (kAudioDevicePropertyDeviceIsRunningSomewhere,
/// only while the Begleiter itself does not record: dictation, wake word and meeting are its own use), or whether the
/// front app shows a window over a whole display (a presentation, full screen). While busy: POST /api/desk/busy
/// {"busy": true, "why"} with every poll (and right when it starts); when it ends {"busy": false}. The menu-bar face
/// shows a small moon. Nothing about the apps leaves the Mac, only "call" or "present".
@MainActor
final class Quiet: ObservableObject {
    static let shared = Quiet()
    static let interval: TimeInterval = 10

    @Published private(set) var busy = false
    @Published private(set) var why: String?

    private var active = false
    private var timer: Timer?
    /// what the Spark was told last (nil: nothing yet)
    private var told: Bool?

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            let t = Timer(timeInterval: Self.interval, repeats: true) { _ in
                Task { @MainActor in Quiet.shared.check() }
            }
            RunLoop.main.add(t, forMode: .common)
            timer = t
            check()
        } else {
            guard active else { return }
            active = false
            timer?.invalidate()
            timer = nil
            if busy || told == true { send(false, why: nil) }
            busy = false
            why = nil
            told = nil
        }
    }

    var text: String {
        switch why {
        case "call": return "Anruf erkannt – Meldungen warten"
        case "present": return "Vollbild erkannt – Meldungen warten"
        default: return "gerade frei"
        }
    }

    func check() {
        guard active else { return }
        let now = QuietLogic.why(mic: micBusy(), camera: cameraBusy(), fullScreen: frontFullScreen())
        let was = busy
        why = now
        busy = now != nil
        if busy != was { send(busy, why: now) }
    }

    /// with every poll while busy (the Spark forgets it after 120 s without)
    func pollTick() {
        guard active else { return }
        if busy { send(true, why: why) }
    }

    private func send(_ on: Bool, why: String?) {
        guard let client = AppModel.shared.client else { return }
        told = on
        Task { @MainActor in
            do {
                try await client.busy(on, why: why)
            } catch {
                AppModel.shared.absorb(error)
            }
        }
    }

    // ------------------------------------------------------------------ the checks

    /// the Begleiter itself has the microphone open: then the microphone says nothing about a call
    private var ownMic: Bool {
        Dictation.shared.recording || Wake.shared.listening || Meeting.shared.capturing
    }

    private func micBusy() -> Bool {
        guard !ownMic else { return false }
        var device = AudioDeviceID(0)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultInputDevice,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &device) == noErr,
              device != 0 else { return false }
        var running = UInt32(0)
        size = UInt32(MemoryLayout<UInt32>.size)
        addr.mSelector = kAudioDevicePropertyDeviceIsRunningSomewhere
        guard AudioObjectGetPropertyData(device, &addr, 0, nil, &size, &running) == noErr else { return false }
        return running != 0
    }

    private func cameraBusy() -> Bool {
        let types: [AVCaptureDevice.DeviceType]
        if #available(macOS 14.0, *) {
            types = [.builtInWideAngleCamera, .external, .continuityCamera]
        } else {
            types = [.builtInWideAngleCamera, .externalUnknown]
        }
        let devices = AVCaptureDevice.DiscoverySession(deviceTypes: types, mediaType: .video, position: .unspecified).devices
        return devices.contains { $0.isInUseByAnotherApplication }
    }

    /// a normal-level window of the front app as big as a whole display (window bounds need no permission)
    private func frontFullScreen() -> Bool {
        guard let front = NSWorkspace.shared.frontmostApplication, front != NSRunningApplication.current,
              !QuietLogic.ignoredBundles.contains(front.bundleIdentifier ?? "") else { return false }
        let pid = front.processIdentifier
        guard let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
                as? [[String: Any]] else { return false }
        var rects: [QuietLogic.Rect] = []
        for w in info {
            guard let owner = (w[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value, owner == pid,
                  let layer = (w[kCGWindowLayer as String] as? NSNumber)?.intValue, layer >= 0, layer < 1000,
                  let b = w[kCGWindowBounds as String] as? NSDictionary,
                  let r = CGRect(dictionaryRepresentation: b as CFDictionary) else { continue }
            rects.append(QuietLogic.Rect(x: r.origin.x, y: r.origin.y, w: r.width, h: r.height))
        }
        guard !rects.isEmpty else { return false }
        var count: UInt32 = 0
        guard CGGetActiveDisplayList(0, nil, &count) == .success, count > 0 else { return false }
        var ids = [CGDirectDisplayID](repeating: 0, count: Int(count))
        guard CGGetActiveDisplayList(count, &ids, &count) == .success else { return false }
        let displays = ids.prefix(Int(count)).map { id -> QuietLogic.Rect in
            let r = CGDisplayBounds(id)
            return QuietLogic.Rect(x: r.origin.x, y: r.origin.y, w: r.width, h: r.height)
        }
        return QuietLogic.coversDisplay(rects, displays: displays)
    }
}
