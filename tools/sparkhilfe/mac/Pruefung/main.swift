import Foundation

// Selbsttest der Regeln im Programm SparkHilfe für den Mac (läuft nur in CI auf dem Mac, .github/workflows/sparkhilfe-mac.yml):
//   pruefung              Name, Ziel, Eingaben, Tasten und Texte
//   pruefung kopf <url>   öffnet die Verbindung wie das Programm (Sitzung.sitzung) zu einem lokalen Lauscher
//                         (kopf.py), der die Kopfzeilen festhält: es darf kein Origin und kein Cookie darin stehen
var fehler = 0
var geprueft = 0
func pruefe(_ ok: Bool, _ was: String) {
    geprueft += 1
    if !ok {
        fehler += 1
        print("FEHLER: " + was)
    }
}

let args = CommandLine.arguments
if args.count == 3 && args[1] == "kopf", let url = URL(string: args[2]) {
    let s = Sitzung.sitzung()
    let ws = s.webSocketTask(with: url)
    ws.resume()
    ws.send(.string(#"{"typ":"hallo"}"#)) { _ in }
    Thread.sleep(forTimeInterval: 4)
    ws.cancel(with: .goingAway, reason: nil)
    print("pruefung kopf: verbunden")
    exit(0)
}

let key = String(repeating: "A", count: 21) + "-"
// der Name der App, wie der Spark ihn packt (spontansteuern.mac_zip)
let z = Ziel.aus("SparkHilfe-spark.i234.me-\(key).app")
pruefe(z == Ziel(host: "spark.i234.me", port: 443, key: key), "Name mit Adresse und Schlüssel")
pruefe(z?.socket?.absoluteString == "wss://spark.i234.me/api/hilfe/steuern", "nur wss zur eigenen Adresse")
pruefe(!(z.map { "\($0)" } ?? key).contains(key), "nie der Schlüssel im Text")
pruefe(Ziel.aus("SparkHilfe-spark.i234.me_8443-\(key) 2.app")?.socket?.absoluteString
       == "wss://spark.i234.me:8443/api/hilfe/steuern", "Port und zweite Kopie im Finder")
pruefe(Ziel.aus("SparkHilfe-Spark.Example.ORG-\(key).app")?.host == "spark.example.org", "Adresse klein")
for bad in ["SparkHilfe.app", "SparkHilfe-spark.i234.me.app", "SparkHilfe-spark.i234.me-\(key.dropLast()).app",
            "SparkHilfe-spark.i234.me-\(key).exe", "SparkHilfe-spark..me-\(key).app", "SparkHilfe-a_b-\(key).app",
            "SparkHilfe-spark.me_0-\(key).app", "SparkHilfe-spark.me_70000-\(key).app", "SparkHilfe--x.me-\(key).app",
            "SparkHilfe-spark.me:443-\(key).app", "SparkHilfe-spark.me/x-\(key).app", "x/SparkHilfe-spark.me-\(key).app",
            "SparkHilfe-\(String(repeating: "a", count: 300))-\(key).app", ""] {
    pruefe(Ziel.aus(bad) == nil, "kein Ziel aus " + bad)
}

// Eingaben nur aus den festen Listen (fernsicht.KEYS, BUTTONS, TEXT_MAX, MAX_EVENTS)
let erlaubt = ["enter", "escape", "tab", "backspace", "delete", "space", "up", "down", "left", "right", "home", "end",
               "pageup", "pagedown", "undo", "redo", "copy", "paste", "save", "reload", "find"]
pruefe(Set(ViewKeys.keys.keys) == Set(erlaubt), "Tasten wie fernsicht.KEYS")
for (name, k) in ViewKeys.keys {
    pruefe(!k.flags.contains(.maskAlternate) && !k.flags.contains(.maskControl), "kein ⌥ oder ⌃: " + name)
    pruefe(k.flags.isEmpty || ["undo", "redo", "copy", "paste", "save", "reload", "find"].contains(name), "⌘ nur fest: " + name)
}
pruefe(ViewKeys.buttons == ["left", "right", "double"], "Knöpfe wie fernsicht.BUTTONS")
pruefe(ViewKeys.textMax == 200 && Ereignisse.maxEvents == 40, "Grenzen wie fernsicht")
pruefe(Ereignisse.maxFrame == 700 * 1024 && Ereignisse.maxMessage == 16 * 1024, "Bild und Nachricht wie im Panel")
pruefe(ViewKeys.frameGap >= 250_000_000, "höchstens vier Bilder je Sekunde")
let roh: [String: Any] = ["events": [
    ["t": "key", "k": "cmd"], ["t": "key", "k": "tab"], ["t": "key", "k": "f4"],
    ["t": "click", "x": 0.5, "y": 0.5, "b": "middle"], ["t": "click", "x": 1.5, "y": 0.5], ["t": "click", "x": true, "y": 0.5],
    ["t": "click", "x": 0.25, "y": 0.75, "b": "double"], ["t": "move", "x": 0, "y": 1],
    ["t": "scroll", "dy": 1.5], ["t": "scroll", "dy": 0], ["t": "scroll", "dy": 11], ["t": "scroll", "dy": -3],
    ["t": "text", "s": "a\u{0007}b\nc"], ["t": "text", "s": String(repeating: "x", count: 500)], ["t": "shell", "s": "ls"],
] as [Any]]
let sauber = Ereignisse.clean(roh)
pruefe(sauber.count == 6, "nur sechs Eingaben bleiben (\(sauber.count))")
pruefe(sauber.first?["k"] as? String == "tab", "erlaubte Taste bleibt")
pruefe(sauber.contains { $0["t"] as? String == "text" && $0["s"] as? String == "ab\nc" }, "Steuerzeichen fallen weg")
pruefe(sauber.contains { ($0["s"] as? String)?.count == 200 }, "Text höchstens 200 Zeichen")
pruefe(sauber.contains { $0["t"] as? String == "scroll" && $0["dy"] as? Int == -3 }, "Rollen ganzzahlig")
let viele: [String: Any] = ["events": Array(repeating: ["t": "key", "k": "tab"], count: 100) as [Any]]
pruefe(Ereignisse.clean(viele).count == 40, "höchstens 40 je Nachricht")
pruefe(Ereignisse.plain("Domi\u{202E}nik\u{0000}", max: 60) == "Dominik", "Name ohne Richtungs- und Steuerzeichen")
pruefe(Ereignisse.plain(String(repeating: "x", count: 99), max: 60).count == 60, "Name höchstens 60 Zeichen")

// Texte deutsch und englisch mit denselben Platzhaltern
for k in Texte.keys {
    guard let p = Texte.pair(k) else { continue }
    pruefe(!p.de.isEmpty && !p.en.isEmpty, "Text in beiden Sprachen: " + k)
    for ph in ["{0}", "{1}"] { pruefe(p.de.contains(ph) == p.en.contains(ph), "Platzhalter \(ph): " + k) }
}
pruefe(!Texte.t("frage", helper: "{1}", host: "spark.me").contains("spark.me (spark.me)"), "Name ersetzt keine Adresse")

print("pruefung: \(geprueft - fehler) von \(geprueft) ok")
exit(fehler == 0 ? 0 : 1)
