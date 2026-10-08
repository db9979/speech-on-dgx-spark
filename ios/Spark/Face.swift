import SwiftUI

/// The assistant's face. The living part (moods, blinking, looking around, mouth following the
/// answer's loudness) is FaceView; how it looks is a FaceStyle that only draws a FacePose.
/// Another look (for example a caricature) is a new FaceStyle; nothing else has to change.
/// The robot is the same as in the panel (static/js/face.js).
enum FaceMood { case idle, waiting, listen, think, speak, sad }

/// Smoothed values between frames (a class: the canvas changes them while drawing).
final class FaceLife {
    var open: Double = 0, smile: Double = 1, eyeH: Double = 24, halo: Double = 0.22, cheeks: Double = 0.6, brow: Double = 0
    var lx: Double = 0, ly: Double = 0, gx: Double = 0, gy: Double = 0
    var blink: Double = -1, nextBlink: Double = 2.5, nextLook: Double = 1.5
}

/// Everything a look needs for one frame, in a 200 × 200 box.
struct FacePose {
    var mood: FaceMood
    var now: Double
    var mic: Double          // microphone loudness 0...1
    var out: Double          // loudness of what plays 0...1
    var open: Double         // mouth opening (0...16)
    var smile: Double        // -1 sad ... 1 happy
    var eyeH: Double         // eye height without the blink
    var lid: Double          // 1 open ... 0.08 closed (blinking)
    var brow: Double         // -1 frowning ... 1 raised
    var halo: Double         // glow / ring strength 0...1
    var cheeks: Double       // 0...1
    var lookX: Double        // where the eyes look, in points
    var lookY: Double
    var bob: Double          // head moving up and down, in points
}

protocol FaceStyle {
    func draw(_ ctx: inout GraphicsContext, _ p: FacePose)
}

struct FaceView: View {
    var mood: FaceMood
    var mic: Float
    /// read every frame: the loudness of what plays right now
    var out: () -> Float
    /// the face the admin picked in the panel ("robot" or "comic", from hello)
    var kind = "robot"
    @State private var life = FaceLife()
    @State private var robot = RobotFace()
    @State private var comic = ComicFace()

    var body: some View {
        TimelineView(.animation) { tl in
            Canvas { ctx, size in
                let pose = step(tl.date.timeIntervalSinceReferenceDate)
                let s = min(size.width, size.height) / 200
                ctx.translateBy(x: (size.width - 200 * s) / 2, y: (size.height - 200 * s) / 2)
                ctx.scaleBy(x: s, y: s)
                let style: FaceStyle = kind == "comic" ? comic as FaceStyle : robot
                style.draw(&ctx, pose)
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .accessibilityLabel("Gesicht des Assistenten")
    }

    private func lerp(_ a: Double, _ b: Double, _ k: Double) -> Double { a + (b - a) * k }

    /// The living part: moves the smoothed values one frame towards the mood.
    private func step(_ now: Double) -> FacePose {
        let L = life
        let m = Double(mic), o = Double(out())
        // targets per mood (as in the panel)
        let t: (open: Double, smile: Double, eyeH: Double, halo: Double, cheeks: Double, brow: Double)
        switch mood {
        case .idle: t = (0, 1, 24, 0.22, 0.6, 0)
        case .waiting: t = (0, 0.8, 22, 0.18 + m * 0.3, 0.5, 0)
        case .listen: t = (0, 0.5, 28, 0.3 + m * 0.7, 0.35, 0.8)
        case .think: t = (1.5, 0, 20, 0.3, 0.2, -0.4)
        case .speak: t = (o * 16, 0.7, 24, 0.25 + o * 0.6, 0.5, 0.3 + o * 0.4)
        case .sad: t = (0, -1, 16, 0.15, 0, -1)
        }
        L.open = lerp(L.open, t.open, 0.45); L.smile = lerp(L.smile, t.smile, 0.15); L.eyeH = lerp(L.eyeH, t.eyeH, 0.2)
        L.halo = lerp(L.halo, t.halo, 0.2); L.cheeks = lerp(L.cheeks, t.cheeks, 0.1); L.brow = lerp(L.brow, t.brow, 0.15)
        if now > L.nextBlink { L.blink = now; L.nextBlink = now + 2.2 + Double.random(in: 0...3.8) }
        // looking around now and then (no mouse on a phone): small saccades, straight ahead while listening
        if now > L.nextLook {
            L.nextLook = now + 1.2 + Double.random(in: 0...2.8)
            if mood == .listen || mood == .speak { L.gx = 0; L.gy = 0 } else {
                L.gx = Double.random(in: -5...5); L.gy = Double.random(in: -3...3)
            }
        }
        let tx = mood == .think ? 6.0 : L.gx, ty = mood == .think ? -6.0 : L.gy
        L.lx = lerp(L.lx, tx, 0.12); L.ly = lerp(L.ly, ty, 0.12)
        let since = now - L.blink
        let lid = since < 0.15 ? max(0.08, abs(1 - since / 0.075)) : 1
        let bob = sin(now / 0.9) * 1.6 + (mood == .speak ? o * -1.5 : 0)
        return FacePose(mood: mood, now: now, mic: m, out: o, open: L.open, smile: L.smile, eyeH: L.eyeH, lid: lid,
                        brow: L.brow, halo: L.halo, cheeks: L.cheeks, lookX: L.lx, lookY: L.ly, bob: bob)
    }
}

/// The robot from the panel: halo, antenna, rounded head, visor with glowing eyes and mouth.
struct RobotFace: FaceStyle {
    private static let acc = Color(red: 0.36, green: 0.36, blue: 0.94)
    private static let acc2 = Color(red: 0.05, green: 0.65, blue: 0.78)
    private static let glow = Color(red: 0.75, green: 0.96, blue: 1.0)
    private static let visor = Color(red: 0.09, green: 0.11, blue: 0.19)

    func draw(_ ctx: inout GraphicsContext, _ p: FacePose) {
        let mood = p.mood, now = p.now
        let grad = Gradient(colors: [Self.acc, Self.acc2])
        let shade = GraphicsContext.Shading.linearGradient(grad, startPoint: CGPoint(x: 26, y: 34), endPoint: CGPoint(x: 174, y: 170))

        // halo
        var halo = ctx
        halo.addFilter(.blur(radius: 8))
        halo.opacity = p.halo
        let hr = 78 + p.halo * 14
        halo.fill(Path(ellipseIn: CGRect(x: 100 - hr, y: 104 - hr, width: hr * 2, height: hr * 2)), with: shade)
        // thinking: a turning arc
        if mood == .think {
            var arc = Path()
            let a = now.truncatingRemainder(dividingBy: 1.2) / 1.2 * 2 * .pi
            arc.addArc(center: CGPoint(x: 100, y: 104), radius: 90, startAngle: .radians(a), endAngle: .radians(a + 0.7), clockwise: false)
            ctx.stroke(arc, with: shade, style: StrokeStyle(lineWidth: 3, lineCap: .round))
        }

        var head = ctx
        head.translateBy(x: 0, y: p.bob)
        // antenna
        var stick = Path(); stick.move(to: CGPoint(x: 100, y: 34)); stick.addLine(to: CGPoint(x: 100, y: 18))
        head.stroke(stick, with: shade, style: StrokeStyle(lineWidth: 4, lineCap: .round))
        let antColor: Color = mood == .listen ? Color(red: 1, green: 0.42, blue: 0.42)
            : mood == .sad ? Color(red: 0.96, green: 0.62, blue: 0.04)
            : mood == .waiting ? Self.acc2.opacity(0.55 + 0.45 * abs(sin(now / 1.2))) : Self.acc2
        var ant = head
        if mood == .think { ant.opacity = 0.4 + 0.6 * abs(sin(now / 0.22)) }
        ant.addFilter(.shadow(color: antColor, radius: 4))
        ant.fill(Path(ellipseIn: CGRect(x: 94, y: 9, width: 12, height: 12)), with: .color(antColor))
        // head, ears, shine
        head.fill(Path(roundedRect: CGRect(x: 26, y: 34, width: 148, height: 136), cornerRadius: 56), with: shade)
        head.fill(Path(roundedRect: CGRect(x: 26, y: 34, width: 148, height: 136), cornerRadius: 56),
                  with: .radialGradient(Gradient(colors: [.white.opacity(0.45), .white.opacity(0)]),
                                        center: CGPoint(x: 78, y: 68), startRadius: 0, endRadius: 90))
        head.fill(Path(roundedRect: CGRect(x: 18, y: 86, width: 12, height: 34), cornerRadius: 6), with: shade)
        head.fill(Path(roundedRect: CGRect(x: 170, y: 86, width: 12, height: 34), cornerRadius: 6), with: shade)
        head.fill(Path(roundedRect: CGRect(x: 44, y: 62, width: 112, height: 82), cornerRadius: 38), with: .color(Self.visor))
        // cheeks
        var ch = head
        ch.opacity = p.cheeks * 0.55
        let pink = Color(red: 1, green: 0.48, blue: 0.66)
        ch.fill(Path(ellipseIn: CGRect(x: 53, y: 119, width: 18, height: 10)), with: .color(pink))
        ch.fill(Path(ellipseIn: CGRect(x: 129, y: 119, width: 18, height: 10)), with: .color(pink))
        // eyes and mouth glow
        var face = head
        face.addFilter(.shadow(color: Self.glow.opacity(0.9), radius: 3))
        let h = p.eyeH * p.lid, y = 96 - h / 2 + p.lookY
        face.fill(Path(roundedRect: CGRect(x: 66 + p.lookX, y: y, width: 18, height: h), cornerRadius: min(9, h / 2)), with: .color(Self.glow))
        face.fill(Path(roundedRect: CGRect(x: 116 + p.lookX, y: y, width: 18, height: h), cornerRadius: min(9, h / 2)), with: .color(Self.glow))
        let w = 13 + p.open * 0.35, my = 124 + p.lookY * 0.4, c = p.smile * 8, op = p.open, mx = 100 + p.lookX * 0.6
        var mouth = Path()
        mouth.move(to: CGPoint(x: mx - w, y: my))
        mouth.addQuadCurve(to: CGPoint(x: mx + w, y: my), control: CGPoint(x: mx, y: my + c - op * 0.3))
        mouth.addQuadCurve(to: CGPoint(x: mx - w, y: my), control: CGPoint(x: mx, y: my + c + op * 1.7))
        mouth.closeSubpath()
        face.fill(mouth, with: .color(Self.glow))
        face.stroke(mouth, with: .color(Self.glow), style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
    }
}
