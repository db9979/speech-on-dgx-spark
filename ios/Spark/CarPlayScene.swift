import CarPlay
import Combine
import UIKit

/// CarPlay: an own icon in the car. Tapping "Mit Spark sprechen" starts a hands-free conversation
/// (the same assistant as on the phone, with short answers); the car screen shows only the state
/// (listening, thinking, speaking), never text. Runs only once Apple granted the CarPlay
/// entitlement for voice-based conversational apps (docs/de/iphone-app.md).
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
        let start = CPListItem(text: "Mit Spark sprechen", detailText: "Antippen und losreden",
                               image: UIImage(systemName: "waveform"))
        start.handler = { [weak self] _, done in
            self?.begin(fresh: false)
            done()
        }
        let fresh = CPListItem(text: "Neues Gespräch", detailText: "Das bisherige Gespräch vergessen",
                               image: UIImage(systemName: "square.and.pencil"))
        fresh.handler = { [weak self] _, done in
            self?.begin(fresh: true)
            done()
        }
        let list = CPListTemplate(title: "Spark", sections: [CPListSection(items: [start, fresh])])
        interfaceController.setRootTemplate(list, animated: false, completion: nil)
        voice = CPVoiceControlTemplate(voiceControlStates: [
            CPVoiceControlState(identifier: "listen", titleVariants: ["Ich höre zu …"],
                                image: UIImage(systemName: "mic.fill"), repeats: true),
            CPVoiceControlState(identifier: "think", titleVariants: ["Denke nach …"],
                                image: UIImage(systemName: "ellipsis"), repeats: true),
            CPVoiceControlState(identifier: "speak", titleVariants: ["Spark spricht …"],
                                image: UIImage(systemName: "speaker.wave.2.fill"), repeats: true)])
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
