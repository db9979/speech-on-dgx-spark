import AuthenticationServices
import UIKit

/// Face ID instead of the six-digit code (V01.0.357): signs the Spark's passkey challenge with a passkey of the
/// Spark's host name. The passkey is made in Safari (Ich → Sicherheit → Passkey hinzufügen, over the address with
/// a name); iCloud Keychain brings it to the app. Apple lets the app use it because of the entitlement
/// webcredentials:<host> and the Spark's file /.well-known/apple-app-site-association (iphone.py).
final class Passkey: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private var done: CheckedContinuation<ASAuthorizationPlatformPublicKeyCredentialAssertion, Error>?
    private let anchor: ASPresentationAnchor
    private static var running: Passkey?

    private init(anchor: ASPresentationAnchor) { self.anchor = anchor }

    static func install() {
        SparkAPI.passkeySigner = { challenge, host in try await Passkey.sign(challenge, host: host) }
    }

    /// {"sid", "options"} from the Spark -> {"sid", "response"} as the browser's navigator.credentials.get gives it
    @MainActor
    static func sign(_ challenge: [String: Any], host: String) async throws -> [String: Any] {
        guard let sid = challenge["sid"] as? String,
              let pk = (challenge["options"] as? [String: Any])?["publicKey"] as? [String: Any],
              let rp = pk["rpId"] as? String, rp == host.lowercased(),
              let c = (pk["challenge"] as? String).flatMap(SparkAPI.unbase64url) else {
            throw SparkError(message: String(localized: "Die Passkey-Anfrage des Spark passt nicht zu dieser Adresse."))
        }
        let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(relyingPartyIdentifier: rp)
        let request = provider.createCredentialAssertionRequest(challenge: c)
        request.userVerificationPreference = .required
        request.allowedCredentials = (pk["allowCredentials"] as? [[String: Any]] ?? []).compactMap {
            ($0["id"] as? String).flatMap(SparkAPI.unbase64url).map { ASAuthorizationPlatformPublicKeyCredentialDescriptor(credentialID: $0) }
        }
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        guard let window = scenes.flatMap(\.windows).first(where: \.isKeyWindow) ?? scenes.first?.windows.first else {
            throw SparkError(message: String(localized: "Passkey geht nur, solange die App offen ist."))
        }
        let me = Passkey(anchor: window)
        running = me
        defer { running = nil }
        let a: ASAuthorizationPlatformPublicKeyCredentialAssertion = try await withCheckedThrowingContinuation { cont in
            me.done = cont
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = me
            controller.presentationContextProvider = me
            controller.performRequests()
        }
        let b = SparkAPI.base64url
        let auth: Data? = a.rawAuthenticatorData, signature: Data? = a.signature, user: Data? = a.userID
        var response: [String: Any] = ["clientDataJSON": b(a.rawClientDataJSON),
                                       "authenticatorData": b(auth ?? Data()), "signature": b(signature ?? Data())]
        if let user, !user.isEmpty { response["userHandle"] = b(user) }
        let id = b(a.credentialID)
        return ["sid": sid, "response": ["id": id, "rawId": id, "type": "public-key",
                                         "clientExtensionResults": [String: Any](), "response": response]]
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        if let a = authorization.credential as? ASAuthorizationPlatformPublicKeyCredentialAssertion {
            done?.resume(returning: a)
        } else {
            done?.resume(throwing: SparkError(message: String(localized: "Kein Passkey bekommen.")))
        }
        done = nil
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        let canceled = (error as? ASAuthorizationError)?.code == .canceled
        done?.resume(throwing: SparkError(message: canceled
            ? String(localized: "Passkey abgebrochen. Du kannst auch den Code eingeben.")
            : String(localized: "Kein passender Passkey auf diesem iPhone. Lege ihn in Safari über die Adresse mit Namen unter Ich → Sicherheit an, oder nimm den Code.")))
        done = nil
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor { anchor }
}
