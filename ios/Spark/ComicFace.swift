import SwiftUI

/// The comic face (a caricature of Dominik), the same drawing and life as in the panel
/// (static/js/face.js, comicSvg and comicFrame): heavy lids, glancing eyes, brows, head tilt,
/// the mouth opening under the mustache with the answer's loudness, a coloured ring for the mood.
/// A class: it keeps its own life between frames.
final class ComicFace: FaceStyle {
    // shapes and colours (COMIC in face.js)
    private let top = 36.0, hw = 47.0, cheekY = 92.0, chinW = 23.0, chinY = 167.0
    private let eyeX = 21.0, eyeY = 90.0, eRx = 10.5, eRy = 6.5, lidBase = 0.36
    private let noseLen = 29.0, noseW = 10.0, stacheS = 1.06, mouthW = 8.0, lw = 2.6
    private static func hex(_ v: UInt32) -> Color {
        Color(red: Double(v >> 16 & 255) / 255, green: Double(v >> 8 & 255) / 255, blue: Double(v & 255) / 255)
    }
    private let skin = ComicFace.hex(0xf0b48c), lidC = ComicFace.hex(0xe09d77), shade = ComicFace.hex(0xc9825e), hair = ComicFace.hex(0x2b2626)
    private let stache = ComicFace.hex(0x382c27), line = ComicFace.hex(0x22180f), bg = ComicFace.hex(0xd9e6f5), shirt = ComicFace.hex(0xf6e27a)
    private let chain = ComicFace.hex(0xc9cdd2), irisC = ComicFace.hex(0x6b6a3e), pupil = ComicFace.hex(0x141414), mouthC = ComicFace.hex(0x5a2320)
    /// hair tips, fixed so the face never changes (COMIC_HAIR)
    private static let hairTips: [(Double, Double)] = [
        (-6, 1), (-12.8, 1.31), (-19.7, 1), (-26.5, 1.19), (-33.3, 1), (-40.2, 1.33), (-47, 1), (-53.8, 1.22), (-60.7, 1),
        (-67.5, 1.3), (-74.3, 1), (-81.2, 1.2), (-88, 1), (-94.8, 1.34), (-101.7, 1), (-108.5, 1.21), (-115.3, 1),
        (-122.2, 1.3), (-129, 1), (-135.8, 1.18), (-142.7, 1), (-149.5, 1.32), (-156.3, 1), (-163.2, 1.24), (-170, 1)]

    // life (C in face.js)
    private var gx = 0.0, gy = 0.0, tx = 0.0, ty = 0.0, look = 0.0, lid = 0.36
    private var bL = 0.0, bR = 0.0, aL = 0.0, aR = 0.0, tilt = 0.0, nod = 0.0, open = 0.0, wide = 0.0, last = 0.0
    private var blinkAt = -1.0, nextBlink = 2.5

    private var m: Double { eyeY + noseLen + 6 }
    private var mcy: Double { m + 15 * stacheS }

    private static func P(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: x, y: y) }
    private func lerp(_ a: Double, _ b: Double, _ k: Double) -> Double { a + (b - a) * k }

    // ---------------------------------------------------------------- life
    private enum Mode { case idle, listen, think, speak, sad }

    private func mode(_ m: FaceMood) -> Mode {
        switch m {
        case .idle, .waiting: return .idle
        case .listen: return .listen
        case .think: return .think
        case .speak: return .speak
        case .sad: return .sad
        }
    }

    private func step(_ mode: Mode, out: Double, mic: Double, now: Double) -> (lid: Double, ix: Double, iy: Double) {
        let dt = min(0.05, last == 0 ? 0 : now - last)
        last = now
        func k(_ n: Double) -> Double { min(1, dt * n) }
        if now > look {
            var x = (Double.random(in: 0...1) - 0.5) * 0.4, y = (Double.random(in: 0...1) - 0.5) * 0.25
            if mode == .think { x = 0.55 + Double.random(in: 0...0.3); y = -0.75 + Double.random(in: 0...0.2) }
            else if mode == .speak && Double.random(in: 0...1) < 0.45 {
                x = (Double.random(in: 0...1) - 0.5) * 0.8; y = (Double.random(in: 0...1) - 0.5) * 0.4
            } else if mode == .idle && Double.random(in: 0...1) < 0.35 {
                // no pointer on a phone: now and then a longer glance to the side
                x = (Double.random(in: 0...1) - 0.5) * 1.4; y = (Double.random(in: 0...1) - 0.5) * 0.6
            }
            tx = max(-1, min(1, x)); ty = max(-1, min(1, y))
            look = now + 0.5 + Double.random(in: 0...(mode == .idle ? 2.6 : 1.8))
        }
        gx = lerp(gx, tx, k(22)); gy = lerp(gy, ty, k(22))
        if now > nextBlink { blinkAt = now; nextBlink = now + 2.2 + Double.random(in: 0...3.8) }
        let bt = (now - blinkAt) / 0.17
        let blink = bt >= 0 && bt < 1 ? sin(bt * .pi) : 0
        let lidT: Double
        switch mode {
        case .listen: lidT = -0.14
        case .think: lidT = 0.06
        case .speak: lidT = -0.06
        case .idle: lidT = 0.1
        case .sad: lidT = 0.18
        }
        lid = lerp(lid, lidBase + lidT, k(6))
        let l = min(1, max(0, lid + (1 - lid) * blink))
        let o = mode == .speak ? min(1, out * 1.3) : 0, emph = o > 0.8 ? 1.0 : 0
        open = lerp(open, o, k(30)); wide = lerp(wide, mode == .speak ? out : 0, k(14))
        var tL = 0.0, tR = 0.0, a1 = 0.0, a2 = 0.0
        switch mode {
        case .listen: tL = -2.6 - mic * 2; tR = tL; a1 = -3; a2 = -3
        case .think: tL = -4.5; tR = 1; a1 = -6; a2 = 4
        case .speak: tL = -1 - emph * 2.2 - open * 1.2; tR = tL
        case .sad: tL = -1; tR = -1; a1 = -9; a2 = -9
        case .idle: break
        }
        bL = lerp(bL, tL, k(9)); bR = lerp(bR, tR, k(9)); aL = lerp(aL, a1, k(8)); aR = lerp(aR, a2, k(8))
        var ti = 0.0, n = sin(now / 0.65) * 0.5
        switch mode {
        case .listen: ti = 5
        case .think: ti = -4 + sin(now / 1.25) * 1.5
        case .speak: ti = sin(now / 0.83) * 1.6; n += emph * 1.6 + open * 0.8
        default: break
        }
        tilt = lerp(tilt, ti, k(4)); nod = lerp(nod, n, k(8))
        return (l, gx * eRx * 0.45, gy * eRy * 0.38)
    }

    // ---------------------------------------------------------------- drawing
    func draw(_ ctx: inout GraphicsContext, _ p: FacePose) {
        let md = mode(p.mood)
        let (l, ix, iy) = step(md, out: p.out, mic: p.mic, now: p.now)
        let P = Self.P
        let st = StrokeStyle(lineWidth: lw, lineCap: .round, lineJoin: .round)
        func outline(_ c: inout GraphicsContext, _ path: Path, _ fill: Color) {
            c.fill(path, with: .color(fill))
            c.stroke(path, with: .color(line), style: st)
        }
        let c = chinY

        ctx.fill(Path(ellipseIn: CGRect(x: 4, y: 4, width: 192, height: 192)), with: .color(bg))
        var inner = ctx
        inner.clip(to: Path(ellipseIn: CGRect(x: 5, y: 5, width: 190, height: 190)))
        // neck, shirt, chain
        var neck = Path()
        neck.move(to: P(80, c - 26)); neck.addLine(to: P(78, 200)); neck.addLine(to: P(122, 200)); neck.addLine(to: P(120, c - 26)); neck.closeSubpath()
        outline(&inner, neck, skin)
        var sh = Path()
        sh.move(to: P(0, 200)); sh.addLine(to: P(0, c + 30))
        sh.addQuadCurve(to: P(78, c + 11), control: P(30, c + 14))
        sh.addQuadCurve(to: P(122, c + 11), control: P(100, c + 27))
        sh.addQuadCurve(to: P(200, c + 30), control: P(170, c + 14))
        sh.addLine(to: P(200, 200)); sh.closeSubpath()
        outline(&inner, sh, shirt)
        var ch = Path(); ch.move(to: P(83, c + 8)); ch.addQuadCurve(to: P(117, c + 8), control: P(100, c + 24))
        inner.stroke(ch, with: .color(chain), style: StrokeStyle(lineWidth: 2.2, lineCap: .round, dash: [1.8, 1.3]))

        // the head turns around the neck and nods
        var head = inner
        head.translateBy(x: 100, y: 175); head.rotate(by: .degrees(tilt)); head.translateBy(x: -100, y: -175)
        head.translateBy(x: 0, y: nod)
        for k in [-1.0, 1.0] {
            let ex = 100 + k * (hw + 1)
            outline(&head, Path(ellipseIn: CGRect(x: ex - 7, y: eyeY + 8 - 13, width: 14, height: 26)), skin)
            var e = Path(); e.move(to: P(ex - k, eyeY + 1)); e.addQuadCurve(to: P(ex - k, eyeY + 14), control: P(ex + 2 * k, eyeY + 7))
            head.stroke(e, with: .color(shade), style: StrokeStyle(lineWidth: 1.3, lineCap: .round))
        }
        let face = facePath()
        outline(&head, face, skin)
        var stubble = head
        stubble.clip(to: face)
        stubble.opacity = 0.13
        stubble.fill(Path(ellipseIn: CGRect(x: 100 - (hw - 2), y: m + 30 - 36, width: 2 * (hw - 2), height: 72)), with: .color(hair))
        var chin = Path()
        chin.move(to: P(100, c - 9)); chin.addQuadCurve(to: P(91, c - 10), control: P(94, c - 6))
        chin.move(to: P(100, c - 9)); chin.addQuadCurve(to: P(109, c - 10), control: P(106, c - 6))
        var chinC = head; chinC.opacity = 0.6
        chinC.stroke(chin, with: .color(shade), style: StrokeStyle(lineWidth: 1.2, lineCap: .round))

        // eyes, lids, brows
        for (k, left) in [(-1.0, true), (1.0, false)] {
            let x = 100 + k * eyeX, y = eyeY, by = y - eRy - 7
            let eye = Path(ellipseIn: CGRect(x: x - eRx, y: y - eRy, width: 2 * eRx, height: 2 * eRy))
            var inEye = head
            inEye.clip(to: eye)
            inEye.fill(eye, with: .color(Color(red: 0.984, green: 0.984, blue: 0.973)))
            let cx = x + ix, cy = y + iy
            inEye.fill(Path(ellipseIn: CGRect(x: cx - 5.53, y: cy - 5.53, width: 11.06, height: 11.06)), with: .color(irisC))
            inEye.fill(Path(ellipseIn: CGRect(x: cx - 2.76, y: cy - 2.76, width: 5.52, height: 5.52)), with: .color(pupil))
            inEye.fill(Path(ellipseIn: CGRect(x: cx + 1.6 - 1.1, y: cy - 1.8 - 1.1, width: 2.2, height: 2.2)), with: .color(.white))
            let y0 = y - eRy - 1, h = (2 * eRy + 2) * l, ly = y0 + h
            inEye.fill(Path(CGRect(x: x - eRx - 1, y: y0, width: 2 * eRx + 2, height: h)), with: .color(lidC))
            head.stroke(eye, with: .color(line), lineWidth: lw * 0.7)
            var lidLine = Path(); lidLine.move(to: P(x - eRx - 0.5, ly)); lidLine.addQuadCurve(to: P(x + eRx + 0.5, ly), control: P(x, ly + 1.6))
            head.stroke(lidLine, with: .color(line), style: StrokeStyle(lineWidth: lw * 0.95, lineCap: .round))
            var brow = head
            brow.translateBy(x: 0, y: left ? bL : bR)
            brow.translateBy(x: x, y: by); brow.rotate(by: .degrees(k * (left ? aL : aR))); brow.translateBy(x: -x, y: -by)
            var b = Path(); b.move(to: P(x - k * 12, by + 1)); b.addQuadCurve(to: P(x + k * 13, by + 2), control: P(x + k, by - 5))
            brow.stroke(b, with: .color(hair), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        }

        // nose
        let ny = eyeY, nl = noseLen, nw = noseW
        var ns = Path()
        ns.move(to: P(100 - nw * 0.5, ny + nl - 6))
        ns.addCurve(to: P(97, ny + nl + 4), control1: P(100 - nw - 1, ny + nl - 3), control2: P(100 - nw, ny + nl + 5))
        ns.addQuadCurve(to: P(103, ny + nl + 4), control: P(100, ny + nl + 6))
        ns.addCurve(to: P(100 + nw * 0.5, ny + nl - 6), control1: P(100 + nw, ny + nl + 5), control2: P(100 + nw + 1, ny + nl - 3))
        var nsC = head; nsC.opacity = 0.35
        nsC.fill(ns, with: .color(shade))
        var nose = Path()
        nose.move(to: P(97, ny + 4))
        nose.addCurve(to: P(100 - nw * 0.6, ny + nl - 4), control1: P(97, ny + nl * 0.5), control2: P(100 - nw * 0.5, ny + nl * 0.75))
        nose.addCurve(to: P(96, ny + nl + 4), control1: P(100 - nw - 1, ny + nl), control2: P(100 - nw + 1, ny + nl + 5))
        nose.addQuadCurve(to: P(104, ny + nl + 4), control: P(100, ny + nl + 6))
        nose.addCurve(to: P(100 + nw * 0.6, ny + nl - 4), control1: P(100 + nw - 1, ny + nl + 5), control2: P(100 + nw + 1, ny + nl))
        head.stroke(nose, with: .color(line), style: st)

        // mouth under the mustache
        let o = open * 7 * stacheS, w = mouthW * (1 + wide * 0.35 - open * 0.15), my = mcy
        if o > 0.4 {
            var mo = Path()
            mo.move(to: P(100 - w, my))
            mo.addQuadCurve(to: P(100 + w, my), control: P(100, my - o * 0.35))
            mo.addQuadCurve(to: P(100 - w, my), control: P(100, my + o * 2))
            mo.closeSubpath()
            head.fill(mo, with: .color(mouthC))
            head.stroke(mo, with: .color(line), style: StrokeStyle(lineWidth: lw * 0.7, lineJoin: .round))
        }
        let sad = md == .sad
        var ml = Path()
        ml.move(to: P(100 - w, my + (sad ? 1.5 : 0)))
        ml.addQuadCurve(to: P(100 + w, my + (sad ? 1.5 : 0)), control: P(100, my + (sad ? -1.6 : 0.6)))
        head.stroke(ml, with: .color(line), style: StrokeStyle(lineWidth: lw * 0.9, lineCap: .round))
        let lipY = my + o * 1.7 + 4
        var lip = Path(); lip.move(to: P(100 - w * 0.55, lipY)); lip.addQuadCurve(to: P(100 + w * 0.55, lipY), control: P(100, lipY + 2.4))
        var lipC = head; lipC.opacity = 0.7
        lipC.stroke(lip, with: .color(shade), style: StrokeStyle(lineWidth: 1.4, lineCap: .round))

        // mustache (lifts a little when the mouth opens)
        var mu = head
        mu.translateBy(x: 0, y: -open * 1.3)
        mu.translateBy(x: 100, y: m); mu.scaleBy(x: stacheS, y: stacheS); mu.translateBy(x: -100, y: -m)
        outline(&mu, stachePath(), stache)
        var strands = Path()
        for (x, dy, dx, ey) in [(88.0, 3.0, -3.0, 7.0), (95, 2, -1, 7), (105, 2, 1, 7), (112, 3, 3, 7), (80, 7, -4, 7), (120, 7, 4, 7)] {
            strands.move(to: P(x, m + dy)); strands.addLine(to: P(x + dx, m + dy + ey))
        }
        var sc = mu; sc.opacity = 0.25
        sc.stroke(strands, with: .color(.black), style: StrokeStyle(lineWidth: 0.9, lineCap: .round))

        outline(&head, hairPath(), hair)

        // the ring shows the mood
        let ring: Color
        switch md {
        case .idle: ring = Self.hex(0x94a3b8)
        case .listen: ring = Self.hex(0x3b82f6)
        case .think: ring = Self.hex(0xf59e0b)
        case .speak: ring = Self.hex(0x22c55e)
        case .sad: ring = Self.hex(0xef4444)
        }
        ctx.stroke(Path(ellipseIn: CGRect(x: 4, y: 4, width: 192, height: 192)), with: .color(ring),
                   lineWidth: md == .listen ? 5 + p.mic * 4 : 5)
    }

    private func facePath() -> Path {
        let P = Self.P
        var f = Path()
        f.move(to: P(100, top))
        f.addCurve(to: P(100 + hw, cheekY), control1: P(100 + hw * 0.72, top), control2: P(100 + hw, top + 22))
        f.addCurve(to: P(100 + chinW, chinY - 5), control1: P(100 + hw, cheekY + 36), control2: P(100 + chinW + 13, chinY - 15))
        f.addQuadCurve(to: P(100 - chinW, chinY - 5), control: P(100, chinY + 6))
        f.addCurve(to: P(100 - hw, cheekY), control1: P(100 - chinW - 13, chinY - 15), control2: P(100 - hw, cheekY + 36))
        f.addCurve(to: P(100, top), control1: P(100 - hw, top + 22), control2: P(100 - hw * 0.72, top))
        f.closeSubpath()
        return f
    }

    private func hairPath() -> Path {
        let P = Self.P, cy = top + 44, rx = hw + 4
        var h = Path()
        h.move(to: P(100 + hw + 2, cy))
        for (a, k) in Self.hairTips {
            let r = a * .pi / 180
            h.addLine(to: P(100 + cos(r) * rx * k, cy + sin(r) * 50 * k))
        }
        h.addLine(to: P(100 - hw - 2, cy))
        h.addLine(to: P(100 - hw + 3, top + 38))
        h.addQuadCurve(to: P(100, top + 18), control: P(100 - hw * 0.45, top + 13))
        h.addQuadCurve(to: P(100 + hw - 3, top + 38), control: P(100 + hw * 0.45, top + 13))
        h.closeSubpath()
        return h
    }

    private func stachePath() -> Path {
        let P = Self.P
        var s = Path()
        s.move(to: P(100, m))
        s.addCurve(to: P(130, m + 12), control1: P(110, m - 2), control2: P(124, m + 2))
        s.addCurve(to: P(129, m + 27), control1: P(133, m + 18), control2: P(132, m + 24))
        s.addCurve(to: P(108, m + 13), control1: P(126, m + 21), control2: P(118, m + 14))
        s.addQuadCurve(to: P(92, m + 13), control: P(100, m + 11))
        s.addCurve(to: P(71, m + 27), control1: P(82, m + 14), control2: P(74, m + 21))
        s.addCurve(to: P(70, m + 12), control1: P(68, m + 24), control2: P(67, m + 18))
        s.addCurve(to: P(100, m), control1: P(76, m + 2), control2: P(90, m - 2))
        s.closeSubpath()
        return s
    }
}
