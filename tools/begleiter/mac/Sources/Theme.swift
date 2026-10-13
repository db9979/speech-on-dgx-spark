import AppKit
import SwiftUI

// Design A ("Spark-Gesicht"): the panel's colours, the face, the gradient, chips and buttons. Every colour follows
// the system's light/dark appearance (and the stronger lines of "Kontrast erhöhen").

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

    static let bg = c(0xf4f6fb, 0x0b0d14)
    static let card = c(0xffffff, 0x131722)
    static let fg = c(0x141824, 0xe8ebf2)
    static let muted = c(0x5f6b85, 0x8b95ab, contrast: (0x3b4560, 0xb4bccd))
    static let line = c(0xe3e7f0, 0x242a3a, contrast: (0x5f6b85, 0x8b95ab))
    static let soft = c(0xf4f6fb, 0x1a1f2d)
    static let accent = c(0x5b5bf0, 0x8b8cff)
    static let accent2 = c(0x0ea5c6, 0x22d3ee)
    static let ok = c(0x16a34a, 0x16a34a)
    static let warn = c(0xc27803, 0xc27803)
    static let bad = c(0xdc2626, 0xdc2626)
    static let visor = c(0x151a2e, 0x070912)
    static let eye = c(0xbff6ff, 0xbff6ff)
    static let ins = c(0xdcfce7, 0x123524)
    static let insFg = c(0x166534, 0x86efac)
    static let del = c(0xfee2e2, 0x3b1717)
    static let delFg = c(0x991b1b, 0xfca5a5)
    static let coffee = c(0xffdd00, 0xffdd00)
    static let coffeeFg = c(0x1f1a00, 0x1f1a00)
    /// the recording pill's text
    static let pillFg = c(0xe8ebf2, 0xe8ebf2)

    static let nsCard = NSColor(name: nil) { ap in
        let m = ap.bestMatch(from: [.aqua, .darkAqua, .accessibilityHighContrastAqua, .accessibilityHighContrastDarkAqua])
        return NSColor(hex: (m == .darkAqua || m == .accessibilityHighContrastDarkAqua) ? 0x131722 : 0xffffff)
    }

    static var gradient: LinearGradient {
        LinearGradient(colors: [accent, accent2], startPoint: .leading, endPoint: .trailing)
    }

    static var diagonal: LinearGradient {
        LinearGradient(colors: [accent, accent2], startPoint: .topLeading, endPoint: .bottomTrailing)
    }
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

/// The Spark's robot face: gradient head, dark visor, two light eyes and a smile.
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
                .stroke(Theme.diagonal, style: StrokeStyle(lineWidth: max(6 * s, 0.8), lineCap: .round))
            FacePart(kind: .ball).fill(Theme.accent2)
            FacePart(kind: .head).fill(Theme.diagonal)
            FacePart(kind: .head).fill(RadialGradient(
                gradient: Gradient(stops: [.init(color: Color.white.opacity(0.45), location: 0),
                                           .init(color: Color.white.opacity(0), location: 0.5)]),
                center: UnitPoint(x: 0.39, y: 0.34), startRadius: 0, endRadius: size * 0.6))
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

/// The 6 px gradient bar on top of every window.
struct GradientBar: View {
    var body: some View {
        Rectangle().fill(Theme.gradient).frame(height: 6)
    }
}

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
                .stroke(dark ? Color(nsColor: NSColor(hex: 0x2a3350)) : Theme.line, lineWidth: 1))
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

/// Primary: accent gradient, white text.
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .foregroundColor(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 9).fill(Theme.diagonal))
            .opacity(enabled ? (configuration.isPressed ? 0.8 : 1) : 0.45)
            .contentShape(RoundedRectangle(cornerRadius: 9))
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
            .background(RoundedRectangle(cornerRadius: 9).fill(configuration.isPressed ? Theme.soft : Theme.card))
            .overlay(RoundedRectangle(cornerRadius: 9).stroke(Theme.line, lineWidth: 1))
            .opacity(enabled ? 1 : 0.45)
            .contentShape(RoundedRectangle(cornerRadius: 9))
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
                .background(RoundedRectangle(cornerRadius: 9)
                    .fill(enabled && (hover || configuration.isPressed) ? Theme.soft : Color.clear))
                .contentShape(RoundedRectangle(cornerRadius: 9))
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
                .foregroundColor(selected ? .white : Theme.fg)
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

/// A card: rounded 12, line, card colour.
struct CardBox<Content: View>: View {
    var padding: CGFloat = 12
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) { content() }
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.card))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.line, lineWidth: 1))
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
    static func image(dot: Dot, moon: Bool = false, face: FaceKind = .robot) -> NSImage {
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
            return true
        }
        img.isTemplate = !comic && dot == .plain
        img.accessibilityDescription = "Spark-Begleiter"
        return img
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
            (coloured ? NSColor(hex: 0xc27803) : NSColor.black).setFill()
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
            let acc = NSColor(hex: 0x5b5bf0)
            let acc2 = NSColor(hex: 0x0ea5c6)
            acc.setStroke()
            antenna.stroke()
            acc2.setFill()
            ball.fill()
            NSGradient(starting: acc, ending: acc2)?.draw(in: head, angle: 45)
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
        case .ok: color = NSColor(hex: 0x16a34a)
        case .grey: color = NSColor(hex: 0x8b95ab)
        case .red: color = NSColor(hex: 0xdc2626)
        case .accent: color = NSColor(hex: 0x5b5bf0)
        case .listening: color = NSColor(hex: 0x0ea5c6)
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
