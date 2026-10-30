import AppKit
import SwiftUI

// "Klar 2 · Systemstil" (Redesign Stufe 9): the panel's colours from app/panel/static/tokens.css (neutral greys, one
// blue accent, no gradients, no shadows in a window), the face, chips and buttons. Every colour follows the system's
// light/dark appearance (and the stronger lines of "Kontrast erhöhen"). Every colour of the windows is here
// (test_design_tokens.Begleiter: equal to the tokens, no colour literal in another file).

extension NSColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
                  blue: CGFloat(hex & 0xff) / 255, alpha: alpha)
    }
}

enum Theme {
    /// light / dark (and, with "Kontrast erhöhen", the given stronger pair)
    private static func c(_ light: UInt32, _ dark: UInt32, contrast: (UInt32, UInt32)? = nil) -> Color {
        Color(nsColor: NSColor(name: nil) { ap in
            let m = ap.bestMatch(from: [.aqua, .darkAqua, .accessibilityHighContrastAqua, .accessibilityHighContrastDarkAqua])
            if m == .accessibilityHighContrastAqua { return NSColor(hex: contrast?.0 ?? light) }
            if m == .accessibilityHighContrastDarkAqua { return NSColor(hex: contrast?.1 ?? dark) }
            if m == .darkAqua { return NSColor(hex: dark) }
            return NSColor(hex: light)
        })
    }

    // tokens.css: --bg --card --fg --mut --line --side --acc --ok --warn --bad --visor (light, dark)
    static let bg = c(0xf5f5f7, 0x161618)
    static let card = c(0xffffff, 0x242426)
    static let fg = c(0x1d1d1f, 0xf5f5f7)
    static let muted = c(0x6e6e73, 0xa1a1a6, contrast: (0x3a3a3c, 0xd1d1d6))
    static let line = c(0xe2e2e7, 0x38383b, contrast: (0x6e6e73, 0xa1a1a6))
    static let soft = c(0xefeff2, 0x1f1f21)
    static let accent = c(0x0071e3, 0x0a84ff)
    static let ok = c(0x28a745, 0x32d74b)
    static let warn = c(0xe08600, 0xff9f0a)
    static let bad = c(0xe5342b, 0xff453a)
    static let visor = c(0x151a2e, 0x070912)
    /// --on-acc: text on a coloured ground (accent, red), the same in light and dark
    static let onAccent = c(0xffffff, 0xffffff)
    /// black for veils and shadows of floating things only (always with opacity)
    static let shade = c(0x000000, 0x000000)
    // the face, the diff marks and the coffee pill: own colours, not in the tokens
    static let eye = c(0xbff6ff, 0xbff6ff)
    static let ins = c(0xdcfce7, 0x123524)
    static let insFg = c(0x166534, 0x86efac)
    static let del = c(0xfee2e2, 0x3b1717)
    static let delFg = c(0x991b1b, 0xfca5a5)
    static let coffee = c(0xffdd00, 0xffdd00)
    static let coffeeFg = c(0x1f1a00, 0x1f1a00)
    /// the floating pills (recording, dictation, reading aloud) always lie on the dark visor: text and line of dark mode
    static let pillFg = c(0xf5f5f7, 0xf5f5f7)
    static let pillLine = c(0x38383b, 0x38383b)

    static let nsCard = NSColor(name: nil) { ap in
        let m = ap.bestMatch(from: [.aqua, .darkAqua, .accessibilityHighContrastAqua, .accessibilityHighContrastDarkAqua])
        return NSColor(hex: (m == .darkAqua || m == .accessibilityHighContrastDarkAqua) ? 0x242426 : 0xffffff)
    }

    /// the red of a running remote control (Fernsicht): bar and frames on the screen, outside SwiftUI
    static let nsBad = NSColor(hex: 0xe5342b)
    static let nsOnAccent = NSColor(hex: 0xffffff)
}

// ------------------------------------------------------------------ the face (viewBox 200 × 200 of the mockup)

struct FacePart: Shape {
    enum Kind {
        case antenna, ball, head, visor, eyes, smile
    }

    let kind: Kind

    func path(in rect: CGRect) -> Path {
        var p = Path()
        switch kind {
        case .antenna:
            p.move(to: CGPoint(x: 100, y: 34))
            p.addLine(to: CGPoint(x: 100, y: 18))
        case .ball:
            p.addEllipse(in: CGRect(x: 92, y: 7, width: 16, height: 16))
        case .head:
            p.addRoundedRect(in: CGRect(x: 26, y: 34, width: 148, height: 136), cornerSize: CGSize(width: 56, height: 56))
        case .visor:
            p.addRoundedRect(in: CGRect(x: 44, y: 62, width: 112, height: 82), cornerSize: CGSize(width: 38, height: 38))
        case .eyes:
            p.addRoundedRect(in: CGRect(x: 66, y: 84, width: 18, height: 24), cornerSize: CGSize(width: 9, height: 9))
            p.addRoundedRect(in: CGRect(x: 116, y: 84, width: 18, height: 24), cornerSize: CGSize(width: 9, height: 9))
        case .smile:
            p.move(to: CGPoint(x: 86, y: 122))
            p.addQuadCurve(to: CGPoint(x: 114, y: 122), control: CGPoint(x: 100, y: 130))
        }
        let s = min(rect.width, rect.height) / 200
        return p.applying(CGAffineTransform(a: s, b: 0, c: 0, d: s, tx: rect.minX, ty: rect.minY))
    }
}

/// The face in the head of the windows and next to answers only on request (Redesign Stufe 9, plan „Comic-Gesicht nur
/// auf Wunsch“): in den Einstellungen des Programms auf der Seite „Übersicht“ der Schalter „Gesicht in den Fenstern zeigen“, on this Mac only, off by default. The
/// menu-bar icon and „Über und Update“ show it always.
enum FacePref {
    static let key = "showFace"
    static var on: Bool { UserDefaults.standard.bool(forKey: key) }
}

/// The Spark's robot face: head in the accent, dark visor, two light eyes and a smile (no gradient, no gloss).
struct FaceView: View {
    var size: CGFloat = 24
    @ObservedObject private var model = AppModel.shared

    var body: some View {
        if model.face != .robot {
            ComicFaceView(size: size, woman: model.face == .comicWoman)
        } else {
            robot
        }
    }

    private var robot: some View {
        let s = size / 200
        return ZStack {
            FacePart(kind: .antenna)
                .stroke(Theme.accent, style: StrokeStyle(lineWidth: max(6 * s, 0.8), lineCap: .round))
            FacePart(kind: .ball).fill(Theme.accent)
            FacePart(kind: .head).fill(Theme.accent)
            FacePart(kind: .visor).fill(Theme.visor)
            FacePart(kind: .eyes).fill(Theme.eye)
            FacePart(kind: .smile)
                .stroke(Theme.eye, style: StrokeStyle(lineWidth: max(5 * s, 0.8), lineCap: .round))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

// ------------------------------------------------------------------ small pieces

/// A key combination as a small chip ("⌥⌘S").
struct KeyChip: View {
    let text: String
    var dark = false

    var body: some View {
        Text(verbatim: text)
            .font(.system(size: 11, design: .monospaced))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .foregroundColor(dark ? Theme.eye : Theme.muted)
            .background(RoundedRectangle(cornerRadius: 6).fill(dark ? Color.clear : Theme.soft))
            .overlay(RoundedRectangle(cornerRadius: 6)
                .stroke(dark ? Theme.pillLine : Theme.line, lineWidth: 1))
            .fixedSize()
    }
}

/// "● verbunden"
struct StatusPill: View {
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(verbatim: text)
                .font(.system(size: 11, weight: .semibold))
                .lineLimit(1)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 3)
        .background(Capsule().fill(Theme.soft))
        .overlay(Capsule().stroke(Theme.line, lineWidth: 1))
        .fixedSize()
    }
}

/// A small square with an SF symbol (the parts' icons).
struct IconTile: View {
    let symbol: String
    var color: Color = Theme.accent
    var back: Color = Theme.soft

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(color)
            .frame(width: 28, height: 28)
            .background(RoundedRectangle(cornerRadius: 8).fill(back))
            .accessibilityHidden(true)
    }
}

/// Primary: the one accent, white text (radius 6 like --r-ctl).
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .foregroundColor(Theme.onAccent)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 6).fill(Theme.accent))
            .opacity(enabled ? (configuration.isPressed ? 0.8 : 1) : 0.45)
            .contentShape(RoundedRectangle(cornerRadius: 6))
    }
}

/// Secondary: card with a line.
struct SoftButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    var danger = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)   // a label never breaks inside a word
            .foregroundColor(danger ? Theme.bad : Theme.fg)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 6).fill(configuration.isPressed ? Theme.soft : Theme.card))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.line, lineWidth: 1))
            .opacity(enabled ? 1 : 0.45)
            .contentShape(RoundedRectangle(cornerRadius: 6))
    }
}

/// A list row in the tray panel (highlight on hover).
struct RowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        RowBody(configuration: configuration)
    }

    private struct RowBody: View {
        let configuration: ButtonStyleConfiguration
        @State private var hover = false
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            configuration.label
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 8)
                    .fill(enabled && (hover || configuration.isPressed) ? Theme.soft : Color.clear))
                .contentShape(RoundedRectangle(cornerRadius: 8))
                .onHover { hover = $0 }
        }
    }
}

/// A choice as a chip; the chosen one in accent.
struct ChipButton: View {
    let title: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(verbatim: title)
                .font(.system(size: 12))
                .foregroundColor(selected ? Theme.onAccent : Theme.fg)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(Capsule().fill(selected ? Theme.accent : Theme.card))
                .overlay(Capsule().stroke(selected ? Theme.accent : Theme.line, lineWidth: 1))
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// The yellow coffee pill: opens the link in the browser only on click.
struct CoffeePill: View {
    let title: String
    let url: URL

    var body: some View {
        Button {
            NSWorkspace.shared.open(url)
        } label: {
            Text(verbatim: "☕ " + title)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.coffeeFg)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Capsule().fill(Theme.coffee))
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .help(Text(verbatim: "Öffnet \(url.absoluteString) im Browser"))
        .fixedSize()
    }
}

/// A card: rounded 10 (--r-box), line, card colour.
struct CardBox<Content: View>: View {
    var padding: CGFloat = 12
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) { content() }
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 10).fill(Theme.card))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
    }
}

/// A rounded rectangle with its own radius per corner (UnevenRoundedRectangle is macOS 14+).
struct BubbleShape: Shape {
    var topLeft: CGFloat
    var topRight: CGFloat
    var bottomRight: CGFloat
    var bottomLeft: CGFloat

    func path(in r: CGRect) -> Path {
        let m = min(r.width, r.height) / 2
        let tl = min(topLeft, m), tr = min(topRight, m), br = min(bottomRight, m), bl = min(bottomLeft, m)
        var p = Path()
        p.move(to: CGPoint(x: r.minX + tl, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - tr, y: r.minY))
        p.addArc(center: CGPoint(x: r.maxX - tr, y: r.minY + tr), radius: tr,
                 startAngle: .degrees(-90), endAngle: .degrees(0), clockwise: false)
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - br))
        p.addArc(center: CGPoint(x: r.maxX - br, y: r.maxY - br), radius: br,
                 startAngle: .degrees(0), endAngle: .degrees(90), clockwise: false)
        p.addLine(to: CGPoint(x: r.minX + bl, y: r.maxY))
        p.addArc(center: CGPoint(x: r.minX + bl, y: r.maxY - bl), radius: bl,
                 startAngle: .degrees(90), endAngle: .degrees(180), clockwise: false)
        p.addLine(to: CGPoint(x: r.minX, y: r.minY + tl))
        p.addArc(center: CGPoint(x: r.minX + tl, y: r.minY + tl), radius: tl,
                 startAngle: .degrees(180), endAngle: .degrees(270), clockwise: false)
        p.closeSubpath()
        return p
    }
}

/// Lays out chips in rows that wrap.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 400
        var x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0, widest: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > 0 && x + s.width > width {
                y += rowH + spacing
                x = 0
                rowH = 0
            }
            x += s.width + spacing
            rowH = max(rowH, s.height)
            widest = max(widest, x - spacing)
        }
        return CGSize(width: proposal.width ?? widest, height: y + rowH)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowH: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > bounds.minX && x + s.width > bounds.maxX {
                y += rowH + spacing
                x = bounds.minX
                rowH = 0
            }
            v.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(s))
            x += s.width + spacing
            rowH = max(rowH, s.height)
        }
    }
}

// ------------------------------------------------------------------ the menu-bar icon

enum MenuIcon {
    enum Dot {
        case plain, ok, grey, red, accent
        /// the wake word listens: a ring instead of a full dot
        case listening
    }

    /// The face as menu-bar icon (18 pt). Without a dot it is a template silhouette (macOS colours it like the
    /// other icons); with a dot it is drawn in colour, the dot bottom right.
    /// `moon`: part "quiet" found the person busy (a call, a presentation): a small crescent top left.
    /// `face` "comic" or "comic_woman": the comic still in colour (a silhouette of it would only be a disc), dot and moon as usual.
    /// `micClosed`: "Mikrofon zu": a struck-through microphone bottom left.
    static func image(dot: Dot, moon: Bool = false, face: FaceKind = .robot, micClosed: Bool = false) -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let comic = face != .robot
        let img = NSImage(size: size, flipped: true) { rect in
            if comic, let g = NSGraphicsContext.current?.cgContext {
                if face == .comicWoman { ComicWomanStill.draw(g, in: rect) } else { ComicStill.draw(g, in: rect) }
                drawDot(in: rect, dot: dot)
            } else {
                draw(in: rect, coloured: dot != .plain, dot: dot)
            }
            if moon { drawMoon(in: rect, coloured: comic || dot != .plain) }
            if micClosed { drawMicClosed(in: rect, coloured: comic || dot != .plain) }
            return true
        }
        img.isTemplate = !comic && dot == .plain
        img.accessibilityDescription = "Spark-Begleiter"
        return img
    }

    /// a struck-through microphone in the bottom-left corner, with a clear ring like the moon
    private static func drawMicClosed(in rect: NSRect, coloured: Bool) {
        let d: CGFloat = 9
        let disc = NSRect(x: rect.minX, y: rect.maxY - d, width: d, height: d)
        guard let ctx = NSGraphicsContext.current,
              let symbol = NSImage(systemSymbolName: "mic.slash.fill", accessibilityDescription: "Mikrofon zu") else { return }
        ctx.saveGraphicsState()
        ctx.compositingOperation = .clear
        NSBezierPath(ovalIn: disc.insetBy(dx: -1.2, dy: -1.2)).fill()
        ctx.restoreGraphicsState()
        let tinted = NSImage(size: disc.size, flipped: false) { r in
            symbol.draw(in: r)
            (coloured ? NSColor(hex: 0xe5342b) : NSColor.black).set()
            r.fill(using: .sourceAtop)
            return true
        }
        tinted.draw(in: disc, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
    }

    /// a crescent in the top-left corner, with a clear ring so it stands apart from the face
    private static func drawMoon(in rect: NSRect, coloured: Bool) {
        let d: CGFloat = 8
        let disc = NSRect(x: rect.minX, y: rect.minY, width: d, height: d)
        let cut = disc.offsetBy(dx: 2.6, dy: -1.4)
        if let ctx = NSGraphicsContext.current {
            ctx.saveGraphicsState()
            ctx.compositingOperation = .clear
            NSBezierPath(ovalIn: disc.insetBy(dx: -1.2, dy: -1.2)).fill()
            ctx.restoreGraphicsState()
            ctx.saveGraphicsState()
            let crescent = NSBezierPath(ovalIn: disc)
            crescent.append(NSBezierPath(ovalIn: cut))
            crescent.windingRule = .evenOdd
            // only the part of the disc outside the cut
            let clip = NSBezierPath(ovalIn: disc)
            clip.addClip()
            (coloured ? NSColor(hex: 0xe08600) : NSColor.black).setFill()
            crescent.fill()
            ctx.restoreGraphicsState()
        }
    }

    private static func draw(in rect: NSRect, coloured: Bool, dot: Dot) {
        let s = rect.width / 200
        func r(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) -> NSRect {
            NSRect(x: x * s, y: y * s, width: w * s, height: h * s)
        }
        let head = NSBezierPath(roundedRect: r(26, 34, 148, 136), xRadius: 56 * s, yRadius: 56 * s)
        let visor = NSBezierPath(roundedRect: r(44, 62, 112, 82), xRadius: 38 * s, yRadius: 38 * s)
        let eyeL = NSBezierPath(roundedRect: r(66, 84, 18, 24), xRadius: 9 * s, yRadius: 9 * s)
        let eyeR = NSBezierPath(roundedRect: r(116, 84, 18, 24), xRadius: 9 * s, yRadius: 9 * s)
        let antenna = NSBezierPath()
        antenna.move(to: NSPoint(x: 100 * s, y: 34 * s))
        antenna.line(to: NSPoint(x: 100 * s, y: 16 * s))
        antenna.lineWidth = 14 * s
        antenna.lineCapStyle = .round
        let ball = NSBezierPath(ovalIn: r(88, 2, 24, 24))
        let smile = NSBezierPath()
        smile.move(to: NSPoint(x: 84 * s, y: 121 * s))
        smile.curve(to: NSPoint(x: 116 * s, y: 121 * s), controlPoint1: NSPoint(x: 94 * s, y: 130 * s),
                    controlPoint2: NSPoint(x: 106 * s, y: 130 * s))
        smile.lineWidth = 12 * s
        smile.lineCapStyle = .round

        if coloured {
            let acc = NSColor(hex: 0x0071e3)
            acc.setStroke()
            antenna.stroke()
            acc.setFill()
            ball.fill()
            head.fill()
            NSColor(hex: 0x151a2e).setFill()
            visor.fill()
            NSColor(hex: 0xbff6ff).setFill()
            eyeL.fill()
            eyeR.fill()
            NSColor(hex: 0xbff6ff).setStroke()
            smile.stroke()
        } else {
            // silhouette: head with the visor cut out, eyes and smile solid inside it
            NSColor.black.setStroke()
            NSColor.black.setFill()
            antenna.stroke()
            ball.fill()
            let shape = NSBezierPath()
            shape.append(head)
            shape.append(visor)
            shape.windingRule = .evenOdd
            shape.fill()
            eyeL.fill()
            eyeR.fill()
            smile.stroke()
        }
        drawDot(in: rect, dot: dot)
    }

    private static func drawDot(in rect: NSRect, dot: Dot) {
        let color: NSColor?
        switch dot {
        case .plain: color = nil
        case .ok: color = NSColor(hex: 0x28a745)
        case .grey: color = NSColor(hex: 0xa1a1a6)
        case .red: color = NSColor(hex: 0xe5342b)
        case .accent: color = NSColor(hex: 0x0071e3)
        case .listening: color = NSColor(hex: 0x0071e3)
        }
        if let color {
            let d: CGFloat = 8
            let dotRect = NSRect(x: rect.maxX - d, y: rect.maxY - d, width: d, height: d)
            // a clear ring around the dot so it stands apart from the face
            if let ctx = NSGraphicsContext.current {
                ctx.saveGraphicsState()
                ctx.compositingOperation = .clear
                NSBezierPath(ovalIn: dotRect.insetBy(dx: -1.5, dy: -1.5)).fill()
                ctx.restoreGraphicsState()
            }
            if dot == .listening {
                color.setStroke()
                let ring = NSBezierPath(ovalIn: dotRect.insetBy(dx: 1, dy: 1))
                ring.lineWidth = 2
                ring.stroke()
            } else {
                color.setFill()
                NSBezierPath(ovalIn: dotRect).fill()
            }
        }
    }
}

// ------------------------------------------------------------------ building blocks of "Begleiter aufpolieren" (Dominik 2026-10-17)

/// Small section title in capitals above a box, like the panel's sections.
struct SectionLabel: View {
    let text: String
    var count = 0

    var body: some View {
        HStack(spacing: 6) {
            Text(verbatim: text.uppercased())
                .font(.system(size: 10.5, weight: .semibold))
                .kerning(0.5)
                .foregroundColor(Theme.muted)
            if count > 0 {
                Text(verbatim: "\(count)")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(Theme.warn)
                    .padding(.horizontal, 6)
                    .background(Capsule().fill(Theme.warn.opacity(0.16)))
            }
        }
        .padding(.horizontal, 2)
        .accessibilityAddTraits(.isHeader)
    }
}

/// The on/off switch: accent when on, line colour when off, white knob with a hairline (no shadow).
struct SwitchKnob: View {
    let on: Bool

    var body: some View {
        ZStack(alignment: on ? .trailing : .leading) {
            Capsule().fill(Theme.line)
            if on { Capsule().fill(Theme.accent) }
            Circle()
                .fill(Theme.onAccent)
                .overlay(Circle().stroke(Theme.shade.opacity(0.12), lineWidth: 0.5))
                .frame(width: 16, height: 16)
                .padding(2)
        }
        .frame(width: 36, height: 20)
        .accessibilityHidden(true)
    }
}

/// A command as a tile in the tray panel: tinted symbol, name (two lines), hotkey small below.
struct PanelTile: View {
    let title: String
    let symbol: String
    var color: Color = Theme.accent
    var key = ""
    var danger = false
    /// small tile, four in a row ("Begleiter-Fenster ordnen" 3a): symbol on top in the middle, name below, the key only as help
    var compact = false
    let run: () -> Void
    @State private var hover = false
    @Environment(\.isEnabled) private var enabled

    var body: some View {
        Button(action: run) {
            if compact { small } else { large }
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .help(Text(verbatim: key.isEmpty ? title : title + " (" + key + ")"))
        .accessibilityLabel(Text(verbatim: title))
    }

    private var small: some View {
        VStack(spacing: 4) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(danger ? Theme.bad : color)
                .frame(width: 26, height: 26)
                .background(RoundedRectangle(cornerRadius: 8).fill((danger ? Theme.bad : color).opacity(0.14)))
            Text(verbatim: title)
                .font(.system(size: 10.5, weight: .semibold))
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 3)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, minHeight: 62, alignment: .top)
        .background(RoundedRectangle(cornerRadius: 10)
            .fill(danger ? Theme.bad.opacity(0.06) : (hover && enabled ? Theme.soft : Theme.card)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(danger ? Theme.bad.opacity(0.4) : Theme.line, lineWidth: 1))
        .opacity(enabled ? 1 : 0.5)
        .contentShape(RoundedRectangle(cornerRadius: 10))
    }

    private var large: some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: symbol)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(danger ? Theme.bad : color)
                .frame(width: 28, height: 28)
                .background(RoundedRectangle(cornerRadius: 8).fill((danger ? Theme.bad : color).opacity(0.14)))
            Text(verbatim: title)
                .font(.system(size: 12, weight: .semibold))
                .lineLimit(2)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            if !key.isEmpty {
                Text(verbatim: key)
                    .font(.system(size: 10.5))
                    .foregroundColor(Theme.muted)
            }
        }
        .padding(9)
        .frame(maxWidth: .infinity, minHeight: 82, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 10)
            .fill(danger ? Theme.bad.opacity(0.06) : (hover && enabled ? Theme.soft : Theme.card)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(danger ? Theme.bad.opacity(0.4) : Theme.line, lineWidth: 1))
        .opacity(enabled ? 1 : 0.5)
        .contentShape(RoundedRectangle(cornerRadius: 10))
    }
}

/// A row in a box: symbol, name and one sentence; on the right a switch (`on` set) or a word like "Öffnen".
struct PanelRow: View {
    let title: String
    var detail = ""
    let symbol: String
    var on: Bool? = nil
    var verb = ""
    let run: () -> Void
    @State private var hover = false
    @Environment(\.isEnabled) private var enabled

    var body: some View {
        Button(action: run) {
            HStack(spacing: 10) {
                Image(systemName: symbol)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(Theme.muted)
                    .frame(width: 20)
                VStack(alignment: .leading, spacing: 1) {
                    Text(verbatim: title)
                        .font(.system(size: 13, weight: .semibold))
                        .lineLimit(1)
                    if !detail.isEmpty {
                        Text(Wege.text(detail))
                            .font(.system(size: 11))
                            .foregroundColor(Theme.muted)
                            .lineLimit(2)
                    }
                }
                Spacer(minLength: 6)
                if let on {
                    SwitchKnob(on: on)
                } else if !verb.isEmpty {
                    Text(verbatim: verb)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Theme.accent)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8).fill(hover && enabled ? Theme.soft : Color.clear))
            .opacity(enabled ? 1 : 0.5)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .accessibilityLabel(Text(verbatim: title + (on.map { $0 ? ", an" : ", aus" } ?? "")))
    }
}

/// A box with rows separated by thin lines (the rows are passed in order; nil rows are left out).
struct PanelBox<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(spacing: 0) {
            content()
        }
        .padding(3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.card))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
    }
}

/// The thin line between two rows of a PanelBox.
struct RowLine: View {
    var body: some View {
        Rectangle().fill(Theme.line).frame(height: 1).padding(.horizontal, 10)
    }
}

/// A point in a side menu: chosen = card with line and accent text.
struct NavRow: View {
    let title: String
    let symbol: String
    let selected: Bool
    var badge = ""
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 9) {
                Image(systemName: symbol)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(selected ? Theme.accent : Theme.muted)
                    .frame(width: 18)
                Text(verbatim: title)
                    .font(.system(size: 13, weight: selected ? .semibold : .regular))
                    .foregroundColor(selected ? Theme.accent : Theme.fg)
                    .lineLimit(1)
                Spacer(minLength: 0)
                if !badge.isEmpty {
                    Text(verbatim: badge)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(Theme.accent)
                        .padding(.horizontal, 6)
                        .background(Capsule().fill(Theme.accent.opacity(0.14)))
                }
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8).fill(selected ? Theme.card : (hover ? Theme.line.opacity(0.5) : Color.clear)))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(selected ? Theme.line : Color.clear, lineWidth: 1))
            .contentShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// The state as a sentence in a lightly tinted card with a round colour symbol ("Alles läuft").
struct StatusCard: View {
    let title: String
    let detail: String
    let color: Color
    let good: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: good ? "checkmark" : "exclamationmark")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(color)
                .frame(width: 36, height: 36)
                .background(Circle().fill(color.opacity(0.18)))
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: title)
                    .font(.system(size: 14, weight: .semibold))
                Text(Wege.text(detail))
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(color.opacity(0.07))
            .background(RoundedRectangle(cornerRadius: 10).fill(Theme.card)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(color.opacity(0.35), lineWidth: 1))
        .accessibilityElement(children: .combine)
    }
}

/// A row with a name (and a sentence) on the left and the switch always in one column on the right, for lists of
/// switches in a PanelBox (Dominik 2026-10-17: switches right after the label looked ragged).
struct SwitchRow: View {
    let title: String
    var detail = ""
    var symbol = ""
    @Binding var isOn: Bool

    var body: some View {
        Button {
            isOn.toggle()
        } label: {
            HStack(spacing: 10) {
                if !symbol.isEmpty {
                    Image(systemName: symbol)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Theme.muted)
                        .frame(width: 20)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(verbatim: title)
                        .font(.system(size: 13))
                        .fixedSize(horizontal: false, vertical: true)
                    if !detail.isEmpty {
                        Text(verbatim: detail)
                            .font(.system(size: 11))
                            .foregroundColor(Theme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 12)
                SwitchKnob(on: isOn)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(verbatim: title))
        .accessibilityValue(Text(verbatim: isOn ? "an" : "aus"))
        .accessibilityAddTraits(.isButton)
    }
}
