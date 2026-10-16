import CarPlay
import Combine
import SwiftUI
import UIKit

/// CarPlay: an own icon in the car. Tapping "Mit Spark sprechen" starts a hands-free conversation
/// (the same assistant as on the phone, with short answers); the car screen shows only the state
/// (listening, thinking, speaking) with the face the admin picked (robot or comic, as a still picture:
/// CarPlay allows no own drawing or animation), never text. Needs the CarPlay entitlement for voice-based
/// conversational apps (Spark.entitlements; granted by Apple since V01.0.676, docs/de/iphone-app.md).
@MainActor
final class CarPlayScene: UIResponder, CPTemplateApplicationSceneDelegate {
    private var interface: CPInterfaceController?
    private var voice: CPVoiceControlTemplate?
    private var shown = false
    private var watch: AnyCancellable?

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didConnect interfaceController: CPInterfaceController) {
        interface = interfaceController
        let talk = Conversation.shared
        talk.inCar = true
        let start = CPListItem(text: String(localized: "Mit Spark sprechen"), detailText: String(localized: "Antippen und losreden"),
                               image: FaceStill.image(talk.allowed.face, .idle) ?? UIImage(systemName: "waveform"))
        start.handler = { [weak self] _, done in
            self?.begin(fresh: false)
            done()
        }
        let fresh = CPListItem(text: String(localized: "Neues Gespräch"), detailText: String(localized: "Das bisherige Gespräch vergessen"),
                               image: UIImage(systemName: "square.and.pencil"))
        fresh.handler = { [weak self] _, done in
            self?.begin(fresh: true)
            done()
        }
        let list = CPListTemplate(title: "Spark", sections: [CPListSection(items: [start, fresh])])
        interfaceController.setRootTemplate(list, animated: false, completion: nil)
        let face = talk.allowed.face
        voice = CPVoiceControlTemplate(voiceControlStates: [
            CPVoiceControlState(identifier: "listen", titleVariants: [String(localized: "Ich höre zu …")],
                                image: FaceStill.image(face, .listen) ?? UIImage(systemName: "mic.fill"), repeats: true),
            CPVoiceControlState(identifier: "think", titleVariants: [String(localized: "Denke nach …")],
                                image: FaceStill.image(face, .think) ?? UIImage(systemName: "ellipsis"), repeats: true),
            CPVoiceControlState(identifier: "speak", titleVariants: [String(localized: "Spark spricht …")],
                                image: FaceStill.image(face, .speak) ?? UIImage(systemName: "speaker.wave.2.fill"), repeats: true)])
        watch = talk.$phase.receive(on: RunLoop.main).sink { [weak self] p in self?.show(p) }
    }

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didDisconnectInterfaceController interfaceController: CPInterfaceController) {
        watch = nil
        interface = nil
        shown = false
        let talk = Conversation.shared
        talk.inCar = false
        talk.stop()
    }

    private func begin(fresh: Bool) {
        let talk = Conversation.shared
        if fresh { talk.restart() }
        if talk.phase == .idle || talk.phase == .waiting { talk.tap() }
    }

    private func show(_ phase: Conversation.Phase) {
        guard let interface, let voice else { return }
        let state: String?
        switch phase {
        case .listening: state = "listen"
        case .transcribing, .thinking: state = "think"
        case .speaking: state = "speak"
        case .idle, .waiting: state = nil
        }
        if let state {
            if !shown {
                shown = true
                interface.presentTemplate(voice, animated: true, completion: nil)
            }
            voice.activateVoiceControlState(withIdentifier: state)
        } else if shown {
            shown = false
            interface.dismissTemplate(animated: true, completion: nil)
        }
    }
}

/// The picked face (FaceView's looks) as one still picture per state for CarPlay. The comic faces keep
/// their own life between frames, so a few frames are drawn invisibly first until the pose has settled
/// (before the first blink).
@MainActor
enum FaceStill {
    static func image(_ kind: String, _ mood: FaceMood, side: CGFloat = 240) -> UIImage? {
        let style: FaceStyle = kind == "comic" ? ComicFace() : kind == "comic_woman" ? ComicFace(woman: true) : RobotFace()
        let t: (open: Double, smile: Double, eyeH: Double, halo: Double, brow: Double, look: Double)
        switch mood {
        case .listen: t = (0, 0.5, 28, 0.6, 0.8, 0)
        case .think: t = (1.5, 0, 20, 0.3, -0.4, 6)
        case .speak: t = (9, 0.7, 24, 0.55, 0.6, 0)
        default: t = (0, 1, 24, 0.22, 0, 0)
        }
        func pose(_ now: Double) -> FacePose {
            FacePose(mood: mood, now: now, mic: mood == .listen ? 0.5 : 0, out: mood == .speak ? 0.6 : 0, open: t.open,
                     smile: t.smile, eyeH: t.eyeH, lid: 1, brow: t.brow, halo: t.halo, cheeks: 0.5,
                     lookX: t.look, lookY: -t.look, bob: 0)
        }
        let drawing = Canvas { ctx, size in
            let s = min(size.width, size.height) / 200
            ctx.scaleBy(x: s, y: s)
            var warm = ctx
            warm.opacity = 0
            for i in 0..<28 { style.draw(&warm, pose(1 + Double(i) * 0.05)) }
            style.draw(&ctx, pose(2.4))
        }
        .frame(width: side, height: side)
        let r = ImageRenderer(content: drawing)
        r.scale = 2
        return r.uiImage
    }
}
