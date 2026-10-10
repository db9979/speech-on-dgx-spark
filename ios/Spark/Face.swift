import SwiftUI

/// The assistant's face. The living part (moods, blinking, looking around, mouth following the
/// answer's loudness) is FaceView; how it looks is a FaceStyle that only draws a FacePose.
/// Another look (for example a caricature) is a new FaceStyle; nothing else has to change.
/// The robot is the same as in the panel (static/js/face.js).
enum FaceMood {
    case idle, waiting, listen, think, speak, sad
    /// "Gesicht zeigt, was es tut" (admin switch chat.face_life, hello "face_life"): what the answer is doing
    case search, calendar, mail, home, memory, happy, error, sleep
}

/// "Gesicht zeigt, was es tut" (V01.0.323, the panel's V01.0.294, static/js/face.js lifeMode): the face's
/// own state on top of the mood, taken only from the Spark's chat events (never from the answer's text):
/// a sign while a tool runs, a wink after something was done, "?" when it went wrong, asleep after 5 minutes.
/// A class: the assistant feeds it, the face reads it every frame.
final class FaceActs {
    static let sleepAfter: Double = 5 * 60
    private var act: FaceMood?
    private var actAt = 0.0, textAt = 0.0, happyUntil = 0.0, errAt = -100.0
    private var happyNext = false
    private var quiet = FaceActs.now

    static var now: Double { Date().timeIntervalSinceReferenceDate }

    /// one of the fixed names from SparkAPI.chat: search, calendar, mail, home, memory, happy, error
    func event(_ name: String) {
        let now = Self.now
        switch name {
        case "search": act = .search
        case "calendar": act = .calendar
        case "mail": act = .mail
        case "home": act = .home
        case "memory": act = .memory; happyNext = true
        case "happy": happyNext = true; return
        case "error": errAt = now; return
        default: return
        }
        actAt = now
    }

    func text() { textAt = Self.now }
    /// someone looked at the face: no sleeping right now
    func wake() { quiet = Self.now }

    func mode(_ base: FaceMood, _ now: Double) -> FaceMood {
        var m = base
        if (m == .idle || m == .waiting) && now - errAt < 5 { m = .sad }
        if m != .idle && m != .waiting && m != .sad { quiet = now }
        if m != .think { act = nil }
        switch m {
        case .sad: return .error
        case .think:
            if let a = act, actAt > textAt || now - actAt < 1.6 { return a }
            if happyNext { happyNext = false; happyUntil = now + 2.2 }
            return now < happyUntil ? .happy : .think
        case .idle, .waiting:
            if happyNext { happyNext = false; happyUntil = now + 2.2 }
            if now < happyUntil { quiet = now; return .happy }
            return now - quiet > Self.sleepAfter ? .sleep : m
        default: return m
        }
    }
}

/// How the faces hold themselves in the new states (LIFE_POSE, lifeGaze, winkOn in face.js).
enum FaceLook {
    /// lids, brows (up left, up right, angle left, angle right), tilt, nod, smile
    struct Pose { let lid: Double; let b: (Double, Double, Double, Double); let tilt: Double; let nod: Double; let smile: Double }
    static func pose(_ m: FaceMood) -> Pose? {
        switch m {
        case .search: return Pose(lid: 0.12, b: (-1, -1, 2, 2), tilt: 0, nod: 2, smile: 0)
        case .calendar: return Pose(lid: -0.04, b: (-2.5, -1, -2, 0), tilt: -3, nod: 0, smile: 0.1)
        case .mail: return Pose(lid: 0.14, b: (-0.5, -0.5, 0, 0), tilt: 2, nod: 2, smile: 0)
        case .home: return Pose(lid: -0.08, b: (-3, -3, -2, -2), tilt: -3, nod: 0, smile: 0.4)
        case .memory: return Pose(lid: 0.1, b: (-1, -2, 0, 0), tilt: 4, nod: 1.5, smile: 0.2)
        case .happy: return Pose(lid: 0.3, b: (-3, -3, -2, -2), tilt: 4, nod: 0, smile: 1)
        case .error: return Pose(lid: 0.12, b: (-1, -1, -10, -10), tilt: -7, nod: 0, smile: -1)
        case .sleep: return Pose(lid: 1, b: (1, 1, 0, 0), tilt: 6, nod: 5, smile: 0.1)
        default: return nil
        }
    }
    /// where the eyes look (-1 … 1), nil = look around as usual
    static func gaze(_ m: FaceMood, _ t: Double) -> (Double, Double)? {
        switch m {
        case .search: return (sin(t * 2.4) * 0.85, 0.05)
        case .calendar, .home: return t.truncatingRemainder(dividingBy: 2.6) < 1.7 ? (0.75, -0.6) : (0.1, 0)
        case .mail: return (0.35 + sin(t * 3) * 0.35, 0.45)
        case .memory: return (0.55, 0.55)
        case .sleep, .happy: return (0, 0)
        default: return nil
        }
    }
    static func wink(_ m: FaceMood, _ t: Double) -> Bool {
        let q = t.truncatingRemainder(dividingBy: 1.8)
        return m == .happy && q > 0.5 && q < 0.85
    }
}

/// Smoothed values between frames (a class: the canvas changes them while drawing).
final class FaceLife {
    var open: Double = 0, smile: Double = 1, eyeH: Double = 24, halo: Double = 0.22, cheeks: Double = 0.6, brow: Double = 0
    var lx: Double = 0, ly: Double = 0, gx: Double = 0, gy: Double = 0
    var blink: Double = -1, nextBlink: Double = 2.5, nextLook: Double = 1.5
    var tilt: Double = 0
    /// the signs next to the face fading in and out (badge, think bubbles, zzz, magnifier)
    var badge: Double = 0, dots: Double = 0, zzz: Double = 0, lens: Double = 0, last: Double = 0
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
    var tilt: Double = 0     // head tilt in degrees (the new states)
    var wink = false         // left eye closed (happy)
    var life = false         // "Gesicht zeigt, was es tut" is on
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
    /// "Gesicht zeigt, was es tut": the assistant's state of the chat events, nil while the admin switch is off
    var acts: FaceActs? = nil
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
                if acts != nil { FaceProps.draw(&ctx, pose.mood, pose.now, life) }
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .onAppear { acts?.wake() }
        .accessibilityLabel("Gesicht des Assistenten")
    }

    private func lerp(_ a: Double, _ b: Double, _ k: Double) -> Double { a + (b - a) * k }

    /// The living part: moves the smoothed values one frame towards the mood.
    private func step(_ now: Double) -> FacePose {
        let L = life
        let m = Double(mic), o = Double(out())
        let mood = acts?.mode(self.mood, now) ?? self.mood
        // targets per mood (as in the panel)
        let t: (open: Double, smile: Double, eyeH: Double, halo: Double, cheeks: Double, brow: Double)
        switch mood {
        case .idle: t = (0, 1, 24, 0.22, 0.6, 0)
        case .waiting: t = (0, 0.8, 22, 0.18 + m * 0.3, 0.5, 0)
        case .listen: t = (0, 0.5, 28, 0.3 + m * 0.7, 0.35, 0.8)
        case .think: t = (1.5, 0, 20, 0.3, 0.2, -0.4)
        case .speak: t = (o * 16, 0.7, 24, 0.25 + o * 0.6, 0.5, 0.3 + o * 0.4)
        case .sad: t = (0, -1, 16, 0.15, 0, -1)
        case .search: t = (1, 0, 20, 0.3, 0.2, -0.4)
        case .calendar: t = (0, 0.1, 24, 0.25, 0.3, 0.3)
        case .mail: t = (0, 0, 20, 0.25, 0.2, 0)
        case .home: t = (0, 0.4, 26, 0.3, 0.4, 0.5)
        case .memory: t = (0, 0.2, 22, 0.25, 0.3, 0)
        case .happy: t = (0, 1, 9, 0.3, 0.9, 0.5)
        case .error: t = (0, -1, 18, 0.15, 0, -1)
        case .sleep: t = (0, 0.1, 3, 0.08, 0, 0)
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
        var tx = mood == .think ? 6.0 : L.gx, ty = mood == .think ? -6.0 : L.gy
        if let g = FaceLook.gaze(mood, now) { tx = g.0 * 7; ty = g.1 * 6 }
        L.lx = lerp(L.lx, tx, 0.12); L.ly = lerp(L.ly, ty, 0.12)
        let since = now - L.blink
        let lid = mood != .sleep && since < 0.15 ? max(0.08, abs(1 - since / 0.075)) : 1
        let P = FaceLook.pose(mood)
        L.tilt = lerp(L.tilt, P?.tilt ?? 0, 0.06)
        let bob = sin(now / (mood == .sleep ? 1.3 : 0.9)) * 1.6 + (mood == .speak ? o * -1.5 : 0) + (P?.nod ?? 0) * 0.8
        return FacePose(mood: mood, now: now, mic: m, out: o, open: L.open, smile: L.smile, eyeH: L.eyeH, lid: lid,
                        brow: L.brow, halo: L.halo, cheeks: L.cheeks, lookX: L.lx, lookY: L.ly, bob: bob,
                        tilt: L.tilt, wink: FaceLook.wink(mood, now), life: acts != nil)
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
        if p.tilt != 0 { head.translateBy(x: 100, y: 170); head.rotate(by: .degrees(p.tilt)); head.translateBy(x: -100, y: -170) }
        head.translateBy(x: 0, y: p.bob)
        // antenna
        var stick = Path(); stick.move(to: CGPoint(x: 100, y: 34)); stick.addLine(to: CGPoint(x: 100, y: 18))
        head.stroke(stick, with: shade, style: StrokeStyle(lineWidth: 4, lineCap: .round))
        let antColor: Color = mood == .listen ? Color(red: 1, green: 0.42, blue: 0.42)
            : mood == .sad || mood == .error ? Color(red: 0.96, green: 0.62, blue: 0.04)
            : mood == .waiting ? Self.acc2.opacity(0.55 + 0.45 * abs(sin(now / 1.2))) : Self.acc2
        var ant = head
        if ([.think, .search, .calendar, .mail, .home, .memory] as [FaceMood]).contains(mood) { ant.opacity = 0.4 + 0.6 * abs(sin(now / 0.22)) }
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
        let hl = p.wink ? 3 : h, yl = 96 - hl / 2 + p.lookY
        face.fill(Path(roundedRect: CGRect(x: 66 + p.lookX, y: yl, width: 18, height: hl), cornerRadius: min(9, hl / 2)), with: .color(Self.glow))
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

/// The signs next to the face in the new states (PROP_SVG and drawProps in face.js), in the same
/// 200 × 200 box: a badge top right (calendar sheet, letter, light bulb, note pad, tick, "?"),
/// think bubbles, "zzz" and a magnifier passing over the eyes. Drawn over both faces.
enum FaceProps {
    private static let ink = Color(red: 0.118, green: 0.141, blue: 0.2)
    private static let red = Color(red: 0.937, green: 0.267, blue: 0.267)
    private static let green = Color(red: 0.086, green: 0.639, blue: 0.29)
    private static let amber = Color(red: 0.961, green: 0.62, blue: 0.043)
    private static let yellow = Color(red: 0.992, green: 0.878, blue: 0.278)
    private static let pen = Color(red: 0.31, green: 0.322, blue: 0.839)
    private static let badged: [FaceMood] = [.calendar, .mail, .home, .memory, .happy, .error]

    private static func P(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: x, y: y) }
    private static func line(_ pts: [(Double, Double)]) -> Path {
        var p = Path()
        for (i, q) in pts.enumerated() { if i == 0 { p.move(to: P(q.0, q.1)) } else { p.addLine(to: P(q.0, q.1)) } }
        return p
    }
    /// an arc as short lines (no doubt about the turning direction)
    private static func arc(_ p: inout Path, _ cx: Double, _ cy: Double, _ r: Double, from a: Double, to b: Double) {
        for i in 0...16 {
            let t = (a + (b - a) * Double(i) / 16) * .pi / 180
            p.addLine(to: P(cx + cos(t) * r, cy + sin(t) * r))
        }
    }

    static func draw(_ ctx: inout GraphicsContext, _ mode: FaceMood, _ t: Double, _ L: FaceLife) {
        let dt = min(0.05, L.last == 0 ? 0 : t - L.last)
        L.last = t
        func k(_ n: Double) -> Double { min(1, dt * n) }
        func on(_ b: Bool) -> Double { b ? 1 : 0 }
        L.badge += (on(badged.contains(mode)) - L.badge) * k(10)
        L.dots += (on(mode == .think) - L.dots) * k(8)
        L.zzz += (on(mode == .sleep) - L.zzz) * k(6)
        L.lens += (on(mode == .search) - L.lens) * k(10)
        let thin = StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round)

        if L.badge > 0.01 {
            var b = ctx
            b.opacity = L.badge
            let s = 0.6 + 0.4 * L.badge
            b.translateBy(x: 166, y: 40); b.scaleBy(x: s, y: s); b.translateBy(x: -166, y: -40)
            let disc = Path(ellipseIn: CGRect(x: 144, y: 18, width: 44, height: 44))
            b.fill(disc, with: .color(.white))
            b.stroke(disc, with: .color(ink), lineWidth: 2.5)
            switch mode {
            case .calendar:
                let sheet = Path(roundedRect: CGRect(x: 154, y: 31, width: 24, height: 21), cornerRadius: 3)
                b.fill(sheet, with: .color(.white))
                b.stroke(sheet, with: .color(ink), style: thin)
                b.fill(Path(roundedRect: CGRect(x: 154, y: 31, width: 24, height: 7), cornerRadius: 3), with: .color(red))
                var pegs = line([(159, 28), (159, 34)]); pegs.addPath(line([(173, 28), (173, 34)]))
                b.stroke(pegs, with: .color(ink), style: thin)
                var page = b
                page.opacity = b.opacity * (t.truncatingRemainder(dividingBy: 1.3) < 1.05 ? 1 : 0.15)
                for (x, y, h, c) in [(157.0, 40.0, 4.0, ink), (164, 40, 4, red), (171, 40, 4, ink), (157, 46, 3, ink)] {
                    page.fill(Path(CGRect(x: x, y: y, width: 4, height: h)), with: .color(c))
                }
            case .mail:
                let env = Path(roundedRect: CGRect(x: 152, y: 31, width: 28, height: 19), cornerRadius: 3)
                b.fill(env, with: .color(.white))
                b.stroke(env, with: .color(ink), style: thin)
                b.stroke(line([(152, 31), (166, 43 - (sin(t * 2.2) + 1) / 2 * 16), (180, 31)]), with: .color(ink), style: thin)
            case .home:
                let lit = t.truncatingRemainder(dividingBy: 2.6) > 1
                if lit {
                    var g = b; g.opacity = b.opacity * 0.85
                    g.fill(Path(ellipseIn: CGRect(x: 153, y: 24, width: 26, height: 26)), with: .color(yellow))
                }
                var bulb = Path()
                bulb.move(to: P(159, 38))
                arc(&bulb, 166, 38, 7, from: 180, to: 360)
                bulb.addCurve(to: P(170, 45), control1: P(173, 41), control2: P(170.5, 42.5))
                bulb.addLine(to: P(162, 45))
                bulb.addCurve(to: P(159, 38), control1: P(161.5, 42.5), control2: P(159, 41))
                bulb.closeSubpath()
                b.fill(bulb, with: .color(lit ? yellow : .white))
                b.stroke(bulb, with: .color(ink), style: thin)
                var base = line([(162.5, 49), (169.5, 49)]); base.addPath(line([(163.5, 52), (168.5, 52)]))
                b.stroke(base, with: .color(ink), style: thin)
            case .memory:
                let pad = Path(roundedRect: CGRect(x: 155, y: 28, width: 20, height: 25), cornerRadius: 2)
                b.fill(pad, with: .color(.white))
                b.stroke(pad, with: .color(ink), style: thin)
                var rules = line([(159, 35), (171, 35)]); rules.addPath(line([(159, 40), (171, 40)]))
                var r = b; r.opacity = b.opacity * 0.5
                r.stroke(rules, with: .color(ink), style: StrokeStyle(lineWidth: 1.6, lineCap: .round))
                let wl = (t * 9).truncatingRemainder(dividingBy: 12)
                b.stroke(line([(159, 45), (159 + wl, 45)]), with: .color(pen), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                var nib = line([(171 + wl - 12, 41), (178 + wl - 12, 32), (181 + wl - 12, 34), (174 + wl - 12, 43)]); nib.closeSubpath()
                b.fill(nib, with: .color(amber))
                b.stroke(nib, with: .color(ink), style: StrokeStyle(lineWidth: 1.4, lineJoin: .round))
            case .happy:
                var h = b
                let s = 0.9 + 0.1 * sin(t * 6)
                h.translateBy(x: 166, y: 40); h.scaleBy(x: s, y: s); h.translateBy(x: -166, y: -40)
                h.stroke(line([(156, 41), (163, 48), (176, 33)]), with: .color(green), style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
            case .error:
                var e = b
                e.translateBy(x: 166, y: 40); e.rotate(by: .degrees(sin(t * 3) * 10)); e.translateBy(x: -166, y: -40)
                var q = Path()
                q.move(to: P(159.5, 33.5))
                arc(&q, 166, 33.53, 6.5, from: 180, to: 422.5)
                q.addCurve(to: P(166, 44), control1: P(167, 40.3), control2: P(166, 41.5))
                e.stroke(q, with: .color(red), style: StrokeStyle(lineWidth: 4.2, lineCap: .round))
                e.fill(Path(ellipseIn: CGRect(x: 163.4, y: 47.9, width: 5.2, height: 5.2)), with: .color(red))
            default: break
            }
        }
        if L.dots > 0.01 {
            var d = ctx
            d.opacity = L.dots
            let ph = t * 1.6
            for (x, y, r, o) in [(150.0, 58.0, 4.0, sin(ph)), (160, 44, 6, sin(ph - 1))] {
                var c = d; c.opacity = L.dots * (0.4 + 0.6 * (o + 1) / 2)
                let dot = Path(ellipseIn: CGRect(x: x - r, y: y - r, width: 2 * r, height: 2 * r))
                c.fill(dot, with: .color(.white)); c.stroke(dot, with: .color(ink), lineWidth: 2)
            }
            let cloud = Path(ellipseIn: CGRect(x: 162, y: 16, width: 28, height: 20))
            d.fill(cloud, with: .color(.white)); d.stroke(cloud, with: .color(ink), lineWidth: 2)
            var dd = d; dd.opacity = L.dots * (t.truncatingRemainder(dividingBy: 1.2) < 0.9 ? 1 : 0.3)
            for x in [170.0, 176, 182] { dd.fill(Path(ellipseIn: CGRect(x: x - 1.8, y: 24.2, width: 3.6, height: 3.6)), with: .color(ink)) }
        }
        if L.zzz > 0.01 {
            for (i, z) in [(146.0, 42.0, 9.0, 2.6), (160, 26, 12, 3), (176, 6, 15, 3.4)].enumerated() {
                let q = (t * 0.5 + Double(i) / 3).truncatingRemainder(dividingBy: 1)
                var c = ctx
                c.opacity = L.zzz * sin(q * .pi)
                c.translateBy(x: q * 6, y: -q * 8)
                let (x, y, w, lw) = z
                let path = line([(x, y), (x + w, y), (x, y + w), (x + w, y + w)])
                c.stroke(path, with: .color(.white), style: StrokeStyle(lineWidth: lw + 5, lineCap: .round, lineJoin: .round))
                c.stroke(path, with: .color(ink), style: StrokeStyle(lineWidth: lw, lineCap: .round, lineJoin: .round))
            }
        }
        if L.lens > 0.01 {
            var l = ctx
            l.opacity = L.lens
            l.translateBy(x: 100 + sin(t * 2.4) * 30, y: 96)
            let glass = Path(ellipseIn: CGRect(x: -17, y: -17, width: 34, height: 34))
            l.fill(glass, with: .color(Color(red: 0.81, green: 0.914, blue: 1).opacity(0.35)))
            l.stroke(glass, with: .color(ink), lineWidth: 4.5)
            l.stroke(line([(12, 12), (27, 27)]), with: .color(ink), style: StrokeStyle(lineWidth: 7, lineCap: .round))
            var shine = Path(); shine.move(to: P(-8, -8)); shine.addQuadCurve(to: P(0, -12), control: P(-5, -11.5))
            l.stroke(shine, with: .color(.white), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
        }
    }
}
