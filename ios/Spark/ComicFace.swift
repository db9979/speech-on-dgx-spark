import SwiftUI

/// The comic faces, the same drawing and life as in the panel (static/js/face.js, comicSvg, comicWSvg and
/// comicFrame): heavy lids, glancing eyes, brows, head tilt, the mouth opening with the answer's loudness,
/// a coloured ring for the mood. `woman` false: the caricature of Dominik, the mouth under the mustache;
/// true: the comic woman (V01.0.490, "comic_woman"), long hair, lashes and lips that open with the mouth.
/// A class: it keeps its own life between frames.
final class ComicFace: FaceStyle {
    private let woman: Bool
    // shapes and colours (COMIC and COMIC_W in face.js)
    private let top: Double, hw: Double, cheekY = 92.0, chinW: Double, chinY: Double
    private let eyeX = 21.0, eyeY: Double, eRx = 10.5, eRy: Double, lidBase: Double
    private let noseLen: Double, noseW: Double, stacheS: Double, mouthW: Double, lw = 2.6
    private static func hex(_ v: UInt32) -> Color {
        Color(red: Double(v >> 16 & 255) / 255, green: Double(v >> 8 & 255) / 255, blue: Double(v & 255) / 255)
    }
    private let skin = ComicFace.hex(0xf0b48c), lidC = ComicFace.hex(0xe09d77), shade = ComicFace.hex(0xc9825e), hair: Color
    private let stache = ComicFace.hex(0x382c27), line = ComicFace.hex(0x22180f), bg: Color, shirt: Color
    private let chain: Color, irisC: Color, pupil = ComicFace.hex(0x141414), mouthC = ComicFace.hex(0x5a2320)
    private let lips = ComicFace.hex(0xc8565a), blush = ComicFace.hex(0xef7f86), pendant = ComicFace.hex(0xe9c46a)

    init(woman: Bool = false) {
        self.woman = woman
        top = woman ? 38 : 36; hw = woman ? 45 : 47; chinW = woman ? 19 : 23; chinY = woman ? 164 : 167
        eyeY = woman ? 91 : 90; eRy = woman ? 7 : 6.5; lidBase = woman ? 0.12 : 0.36
        noseLen = woman ? 25 : 29; noseW = woman ? 8 : 10; stacheS = woman ? 1 : 1.06; mouthW = woman ? 10 : 8
        hair = ComicFace.hex(woman ? 0x4a2c22 : 0x2b2626); bg = ComicFace.hex(woman ? 0xf5dfe6 : 0xd9e6f5)
        shirt = ComicFace.hex(woman ? 0x7cc4b8 : 0xf6e27a); chain = ComicFace.hex(woman ? 0xd9b45a : 0xc9cdd2)
        irisC = ComicFace.hex(woman ? 0x6b4a2e : 0x6b6a3e)
    }
    /// hair tips, fixed so the face never changes (COMIC_HAIR)
    private static let hairTips: [(Double, Double)] = [
        (-6, 1), (-12.8, 1.31), (-19.7, 1), (-26.5, 1.19), (-33.3, 1), (-40.2, 1.33), (-47, 1), (-53.8, 1.22), (-60.7, 1),
        (-67.5, 1.3), (-74.3, 1), (-81.2, 1.2), (-88, 1), (-94.8, 1.34), (-101.7, 1), (-108.5, 1.21), (-115.3, 1),
        (-122.2, 1.3), (-129, 1), (-135.8, 1.18), (-142.7, 1), (-149.5, 1.32), (-156.3, 1), (-163.2, 1.24), (-170, 1)]

    // life (C in face.js)
    private var gx = 0.0, gy = 0.0, tx = 0.0, ty = 0.0, look = 0.0, lid = 0.36
    private var bL = 0.0, bR = 0.0, aL = 0.0, aR = 0.0, tilt = 0.0, nod = 0.0, open = 0.0, wide = 0.0, last = 0.0
    private var blinkAt = -1.0, nextBlink = 2.5, smile = 0.0

    private var m: Double { eyeY + noseLen + 6 }
    private var mcy: Double { woman ? eyeY + noseLen + 17 : m + 15 * stacheS }

    private static func P(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: x, y: y) }
    private func lerp(_ a: Double, _ b: Double, _ k: Double) -> Double { a + (b - a) * k }

    // ---------------------------------------------------------------- life
    /// the mood as the comic face knows it ("waiting" looks like idle)
    private func mode(_ m: FaceMood) -> FaceMood { m == .waiting ? .idle : m }

    private func step(_ mode: FaceMood, out: Double, mic: Double, now: Double) -> (lid: Double, ix: Double, iy: Double) {
        let dt = min(0.05, last == 0 ? 0 : now - last)
        last = now
        func k(_ n: Double) -> Double { min(1, dt * n) }
        let P = FaceLook.pose(mode)
        if let g = FaceLook.gaze(mode, now) { tx = g.0; ty = g.1 }
        else if now > look {
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
        gx = lerp(gx, tx, k(mode == .search ? 40 : 22)); gy = lerp(gy, ty, k(22))
        if now > nextBlink { blinkAt = now; nextBlink = now + 2.2 + Double.random(in: 0...3.8) }
        let bt = (now - blinkAt) / 0.17
        let blink = mode != .sleep && bt >= 0 && bt < 1 ? sin(bt * .pi) : 0
        let lidT: Double
        switch mode {
        case .listen: lidT = -0.14
        case .think: lidT = 0.06
        case .speak: lidT = -0.06
        case .sad: lidT = 0.18
        default: lidT = P?.lid ?? 0.1
        }
        lid = lerp(lid, min(1, lidBase + lidT), k(6))
        let l = min(1, max(0, lid + (1 - lid) * blink))
        let o = mode == .speak ? min(1, out * 1.3) : 0, emph = o > 0.8 ? 1.0 : 0
        open = lerp(open, o, k(30)); wide = lerp(wide, mode == .speak ? out : 0, k(14))
        var tL = 0.0, tR = 0.0, a1 = 0.0, a2 = 0.0
        switch mode {
        case .listen: tL = -2.6 - mic * 2; tR = tL; a1 = -3; a2 = -3
        case .think: tL = -4.5; tR = 1; a1 = -6; a2 = 4
        case .speak: tL = -1 - emph * 2.2 - open * 1.2; tR = tL
        case .sad: tL = -1; tR = -1; a1 = -9; a2 = -9
        default: if let P { (tL, tR, a1, a2) = P.b }
        }
        bL = lerp(bL, tL, k(9)); bR = lerp(bR, tR, k(9)); aL = lerp(aL, a1, k(8)); aR = lerp(aR, a2, k(8))
        var ti = 0.0, n = sin(now / 0.65) * 0.5
        switch mode {
        case .listen: ti = 5
        case .think: ti = -4 + sin(now / 1.25) * 1.5
        case .speak: ti = sin(now / 0.83) * 1.6; n += emph * 1.6 + open * 0.8
        default: if let P { ti = P.tilt; n = P.nod + (mode == .sleep ? sin(now / 0.83) * 1.4 : n) }
        }
        smile = lerp(smile, P?.smile ?? 0, k(6))
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
        let nk = woman ? 2.0 : 0, sy = woman ? 2.0 : 0
        var neck = Path()
        neck.move(to: P(80 + nk, c - 26)); neck.addLine(to: P(78 + nk, 200)); neck.addLine(to: P(122 - nk, 200)); neck.addLine(to: P(120 - nk, c - 26)); neck.closeSubpath()
        outline(&inner, neck, skin)
        var sh = Path()
        sh.move(to: P(0, 200)); sh.addLine(to: P(0, c + 30 + sy))
        sh.addQuadCurve(to: P(78 + nk, c + 11 + sy), control: P(30, c + 14 + sy))
        sh.addQuadCurve(to: P(122 - nk, c + 11 + sy), control: P(100, c + 27 + 1.5 * sy))
        sh.addQuadCurve(to: P(200, c + 30 + sy), control: P(170, c + 14 + sy))
        sh.addLine(to: P(200, 200)); sh.closeSubpath()
        outline(&inner, sh, shirt)
        if woman {
            // a thin chain with a pendant
            var ch = Path(); ch.move(to: P(86, c + 10)); ch.addQuadCurve(to: P(114, c + 10), control: P(100, c + 22))
            inner.stroke(ch, with: .color(chain), style: StrokeStyle(lineWidth: 1.6, lineCap: .round))
            let pd = Path(ellipseIn: CGRect(x: 100 - 2.6, y: c + 19 - 2.6, width: 5.2, height: 5.2))
            inner.fill(pd, with: .color(pendant)); inner.stroke(pd, with: .color(line), lineWidth: 1)
        } else {
            var ch = Path(); ch.move(to: P(83, c + 8)); ch.addQuadCurve(to: P(117, c + 8), control: P(100, c + 24))
            inner.stroke(ch, with: .color(chain), style: StrokeStyle(lineWidth: 2.2, lineCap: .round, dash: [1.8, 1.3]))
        }

        // the head turns around the neck and nods
        var head = inner
        head.translateBy(x: 100, y: 175); head.rotate(by: .degrees(tilt)); head.translateBy(x: -100, y: -175)
        head.translateBy(x: 0, y: nod)
        if woman {
            // the long hair behind the head and the locks over the shoulders turn with it
            outline(&head, Self.svg(Self.backHair), hair)
            outline(&head, Self.svg(Self.locks), hair)
        }
        for k in [-1.0, 1.0] where !woman {
            let ex = 100 + k * (hw + 1)
            outline(&head, Path(ellipseIn: CGRect(x: ex - 7, y: eyeY + 8 - 13, width: 14, height: 26)), skin)
            var e = Path(); e.move(to: P(ex - k, eyeY + 1)); e.addQuadCurve(to: P(ex - k, eyeY + 14), control: P(ex + 2 * k, eyeY + 7))
            head.stroke(e, with: .color(shade), style: StrokeStyle(lineWidth: 1.3, lineCap: .round))
        }
        let face = facePath()
        outline(&head, face, skin)
        if woman {
            var chin = Path()
            chin.move(to: P(100, c - 8)); chin.addQuadCurve(to: P(92, c - 9), control: P(95, c - 5.5))
            chin.move(to: P(100, c - 8)); chin.addQuadCurve(to: P(108, c - 9), control: P(105, c - 5.5))
            var chinC = head; chinC.opacity = 0.5
            chinC.stroke(chin, with: .color(shade), style: StrokeStyle(lineWidth: 1.1, lineCap: .round))
            var cheeks = head; cheeks.opacity = 0.35
            for cx in [73.0, 127.0] {
                cheeks.fill(Path(ellipseIn: CGRect(x: cx - 9, y: eyeY + 21 - 5, width: 18, height: 10)), with: .color(blush))
            }
        } else {
            var stubble = head
            stubble.clip(to: face)
            stubble.opacity = 0.13
            stubble.fill(Path(ellipseIn: CGRect(x: 100 - (hw - 2), y: m + 30 - 36, width: 2 * (hw - 2), height: 72)), with: .color(hair))
            var chin = Path()
            chin.move(to: P(100, c - 9)); chin.addQuadCurve(to: P(91, c - 10), control: P(94, c - 6))
            chin.move(to: P(100, c - 9)); chin.addQuadCurve(to: P(109, c - 10), control: P(106, c - 6))
            var chinC = head; chinC.opacity = 0.6
            chinC.stroke(chin, with: .color(shade), style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
        }

        // eyes, lids, brows
        for (k, left) in [(-1.0, true), (1.0, false)] {
            let x = 100 + k * eyeX, y = eyeY, by = y - eRy - 7
            let eye = Path(ellipseIn: CGRect(x: x - eRx, y: y - eRy, width: 2 * eRx, height: 2 * eRy))
            var inEye = head
            inEye.clip(to: eye)
            inEye.fill(eye, with: .color(Color(red: 0.984, green: 0.984, blue: 0.973)))
            let cx = x + ix, cy = y + iy + (woman ? 0.5 : 0), ir = woman ? 5.8 : 5.53, pr = woman ? 2.8 : 2.76
            let hr = woman ? 1.2 : 1.1, hy = woman ? cy - 1.9 : cy - 1.8
            inEye.fill(Path(ellipseIn: CGRect(x: cx - ir, y: cy - ir, width: 2 * ir, height: 2 * ir)), with: .color(irisC))
            inEye.fill(Path(ellipseIn: CGRect(x: cx - pr, y: cy - pr, width: 2 * pr, height: 2 * pr)), with: .color(pupil))
            inEye.fill(Path(ellipseIn: CGRect(x: cx + 1.6 - hr, y: hy - hr, width: 2 * hr, height: 2 * hr)), with: .color(.white))
            let y0 = y - eRy - 1, h = left && p.wink ? 2 * eRy + 2 : (2 * eRy + 2) * l, ly = y0 + h
            inEye.fill(Path(CGRect(x: x - eRx - 1, y: y0, width: 2 * eRx + 2, height: h)), with: .color(lidC))
            head.stroke(eye, with: .color(line), lineWidth: lw * 0.7)
            var lidLine = Path(); lidLine.move(to: P(x - eRx - 0.5, ly)); lidLine.addQuadCurve(to: P(x + eRx + 0.5, ly), control: P(x, ly + (md == .happy ? -2.4 : 1.6)))
            head.stroke(lidLine, with: .color(line), style: StrokeStyle(lineWidth: lw * (woman ? 1.15 : 0.95), lineCap: .round))
            if woman {
                var lash = Path()
                for (dx, dy, lx, ly) in [(8.6, -6.0, 4.2, -3.6), (10.4, -3.8, 4.6, -1.6), (5.8, -6.6, 2.6, -4.0)] {
                    lash.move(to: P(x + k * dx, y + dy)); lash.addLine(to: P(x + k * (dx + lx), y + dy + ly))
                }
                head.stroke(lash, with: .color(line), style: StrokeStyle(lineWidth: 1.6, lineCap: .round))
            }
            var brow = head
            brow.translateBy(x: 0, y: left ? bL : bR)
            brow.translateBy(x: x, y: by); brow.rotate(by: .degrees(k * (left ? aL : aR))); brow.translateBy(x: -x, y: -by)
            var b = Path()
            if woman { b.move(to: P(x - k * 11, by + 1)); b.addQuadCurve(to: P(x + k * 12, by), control: P(x + k * 2, by - 6)) }
            else { b.move(to: P(x - k * 12, by + 1)); b.addQuadCurve(to: P(x + k * 13, by + 2), control: P(x + k, by - 5)) }
            brow.stroke(b, with: .color(hair), style: StrokeStyle(lineWidth: woman ? 3.2 : 5, lineCap: .round))
        }

        // nose
        // (the woman's nose is a little smaller: the same lines with her own offsets, like comicWSvg)
        let ny = eyeY, nl = noseLen, nw = noseW, n0 = woman ? 2.5 : 3, n1 = woman ? 3.5 : 4, n2 = woman ? 5.0 : 6, n3 = woman ? 4.0 : 5
        var ns = Path()
        ns.move(to: P(100 - nw * 0.5, ny + nl - 6))
        ns.addCurve(to: P(100 - n0, ny + nl + 4), control1: P(100 - nw - 1, ny + nl - 3), control2: P(100 - nw, ny + nl + 5))
        ns.addQuadCurve(to: P(100 + n0, ny + nl + 4), control: P(100, ny + nl + 6))
        ns.addCurve(to: P(100 + nw * 0.5, ny + nl - 6), control1: P(100 + nw, ny + nl + 5), control2: P(100 + nw + 1, ny + nl - 3))
        var nsC = head; nsC.opacity = woman ? 0.3 : 0.35
        nsC.fill(ns, with: .color(shade))
        var nose = Path()
        nose.move(to: P(100 - n0, ny + (woman ? 6 : 4)))
        nose.addCurve(to: P(100 - nw * 0.6, ny + nl - 4), control1: P(100 - n0, ny + nl * 0.5), control2: P(100 - nw * 0.5, ny + nl * 0.75))
        nose.addCurve(to: P(100 - n1, ny + nl + n1), control1: P(100 - nw - 1, ny + nl), control2: P(100 - nw + 1, ny + nl + n3))
        nose.addQuadCurve(to: P(100 + n1, ny + nl + n1), control: P(100, ny + nl + n2))
        nose.addCurve(to: P(100 + nw * 0.6, ny + nl - 4), control1: P(100 + nw - 1, ny + nl + n3), control2: P(100 + nw + 1, ny + nl))
        head.stroke(nose, with: .color(line), style: st)

        // mouth under the mustache
        // thinking with the new states on: the mouth small and to the side, like the panel
        let thinkL = p.life && md == .think, mx = thinkL ? 105.0 : 100
        let o = open * 7 * stacheS, my = mcy
        let w = mouthW * (1 + wide * 0.35 - open * 0.15 + (md == .happy ? 0.3 : 0)) * (thinkL ? 0.7 : 1)
        if o > 0.4 {
            var mo = Path()
            mo.move(to: P(mx - w, my))
            mo.addQuadCurve(to: P(mx + w, my), control: P(mx, my - o * 0.35))
            mo.addQuadCurve(to: P(mx - w, my), control: P(mx, my + o * 2))
            mo.closeSubpath()
            head.fill(mo, with: .color(mouthC))
            head.stroke(mo, with: .color(line), style: StrokeStyle(lineWidth: lw * (woman ? 0.6 : 0.7), lineJoin: .round))
        }
        let sad = md == .sad
        if woman {
            // upper lip above the opening, lower lip below it (comicLips in face.js)
            let sm = FaceLook.pose(md) != nil ? smile * 3.2 : 0, y0 = my - sm * 0.5, up = my - o * 0.2, lo = my + o * 2 + sm
            var lt = Path()
            lt.move(to: P(mx - w - 1, y0))
            lt.addQuadCurve(to: P(mx, up - 2), control: P(mx - w * 0.5, up - 4.2))
            lt.addQuadCurve(to: P(mx + w + 1, y0), control: P(mx + w * 0.5, up - 4.2))
            lt.addQuadCurve(to: P(mx - w - 1, y0), control: P(mx, my + sm - o * 0.35))
            lt.closeSubpath()
            var lb = Path()
            lb.move(to: P(mx - w - 1, y0))
            lb.addQuadCurve(to: P(mx + w + 1, y0), control: P(mx, lo + 8.5))
            lb.addQuadCurve(to: P(mx - w - 1, y0), control: P(mx, lo))
            lb.closeSubpath()
            for lp in [lt, lb] {
                head.fill(lp, with: .color(lips))
                head.stroke(lp, with: .color(line), style: StrokeStyle(lineWidth: lw * 0.6, lineJoin: .round))
            }
        }
        var ml = Path()
        if FaceLook.pose(md) != nil {
            let sm = smile * 3.2
            ml.move(to: P(mx - w, my - sm * 0.5))
            ml.addQuadCurve(to: P(mx + w, my - sm * 0.5), control: P(mx, my + sm))
        } else {
            ml.move(to: P(mx - w, my + (sad ? 1.5 : 0)))
            ml.addQuadCurve(to: P(mx + w, my + (sad ? 1.5 : 0)), control: P(mx, my + (sad ? -1.6 : 0.6)))
        }
        head.stroke(ml, with: .color(line), style: StrokeStyle(lineWidth: lw * (woman ? 0.8 : 0.9), lineCap: .round))
        if woman {
            outline(&head, Self.svg(Self.frontHair), hair)
            var sc = head; sc.opacity = 0.45
            sc.stroke(Self.svg(Self.strands), with: .color(line), style: StrokeStyle(lineWidth: 1.3, lineCap: .round))
        } else {
            let lipY = my + o * 1.7 + 4
            var lip = Path(); lip.move(to: P(mx - w * 0.55, lipY)); lip.addQuadCurve(to: P(mx + w * 0.55, lipY), control: P(mx, lipY + 2.4))
            var lipC = head; lipC.opacity = 0.7
            lipC.stroke(lip, with: .color(shade), style: StrokeStyle(lineWidth: 1.4, lineCap: .round))

            // mustache (lifts a little when the mouth opens)
            var mu = head
            mu.translateBy(x: 0, y: -open * 1.3 - max(0, smile) * 0.8)
            mu.translateBy(x: 100, y: m); mu.scaleBy(x: stacheS, y: stacheS); mu.translateBy(x: -100, y: -m)
            outline(&mu, stachePath(), stache)
            var strands = Path()
            for (x, dy, dx, ey) in [(88.0, 3.0, -3.0, 7.0), (95, 2, -1, 7), (105, 2, 1, 7), (112, 3, 3, 7), (80, 7, -4, 7), (120, 7, 4, 7)] {
                strands.move(to: P(x, m + dy)); strands.addLine(to: P(x + dx, m + dy + ey))
            }
            // the strands shrink with the shorter mustache, around (100, m) like face.js
            strands = strands.applying(CGAffineTransform(translationX: 100, y: m).scaledBy(x: 0.63, y: 0.77).translatedBy(x: -100, y: -m))
            var sc = mu; sc.opacity = 0.25
            sc.stroke(strands, with: .color(.black), style: StrokeStyle(lineWidth: 0.9, lineCap: .round))

            outline(&head, hairPath(), hair)
        }

        // the ring shows the mood
        let ring: Color
        switch md {
        case .idle: ring = Self.hex(0x94a3b8)
        case .listen: ring = Self.hex(0x3b82f6)
        case .think: ring = Self.hex(0xf59e0b)
        case .speak: ring = Self.hex(0x22c55e)
        case .sad, .error: ring = Self.hex(0xef4444)
        case .search, .calendar, .mail, .home, .memory: ring = Self.hex(0xf59e0b)
        case .happy: ring = Self.hex(0x22c55e)
        case .waiting, .sleep: ring = Self.hex(0x94a3b8)
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
        f.addQuadCurve(to: P(100 - chinW, chinY - 5), control: P(100, chinY + (woman ? 5 : 6)))
        f.addCurve(to: P(100 - hw, cheekY), control1: P(100 - chinW - 13, chinY - 15), control2: P(100 - hw, cheekY + 36))
        f.addCurve(to: P(100, top), control1: P(100 - hw, top + 22), control2: P(100 - hw * 0.72, top))
        f.closeSubpath()
        return f
    }

    // the woman's hair, the same path strings as comicWSvg in face.js (chin at 164)
    private static let backHair = "M100 24 C152 24 164 66 160 118 C157 156 166 184 176 200 L121 200 L119 140 L81 140 L79 200 L24 200 C34 184 43 156 40 118 C36 66 48 24 100 24Z"
    private static let locks = "M52 96 C44 130 46 168 34 200 L62 200 C64 172 58 140 60 110Z M148 96 C156 130 154 168 166 200 L138 200 C136 172 142 140 140 110Z"
    private static let frontHair = "M52 104 C44 54 68 27 101 27 C134 27 156 54 148 104 C146 84 142 70 136 62 C126 50 116 47 107 47 C90 50 74 60 66 74 C60 82 55 92 52 104Z"
    private static let strands = "M107 47 C96 52 82 60 72 74 M107 47 C120 52 132 62 138 74"

    /// A fixed path string of the drawing (absolute M, L, C, Q and Z only) as a Path; never text from outside.
    private static func svg(_ d: String) -> Path {
        var p = Path(), cmd: Character = "M", n: [Double] = [], num = ""
        func take() { if let v = Double(num) { n.append(v) }; num = "" }
        func run() {
            func q(_ i: Int) -> CGPoint { CGPoint(x: n[i], y: n[i + 1]) }
            var i = 0
            switch cmd {
            case "M":
                if n.count >= 2 { p.move(to: q(0)); i = 2 }
                while i + 1 < n.count { p.addLine(to: q(i)); i += 2 }
            case "L": while i + 1 < n.count { p.addLine(to: q(i)); i += 2 }
            case "C": while i + 5 < n.count { p.addCurve(to: q(i + 4), control1: q(i), control2: q(i + 2)); i += 6 }
            case "Q": while i + 3 < n.count { p.addQuadCurve(to: q(i + 2), control: q(i)); i += 4 }
            case "Z": p.closeSubpath()
            default: break
            }
            n = []
        }
        for ch in d {
            if ch.isLetter { take(); run(); cmd = ch }
            else if ch == " " || ch == "," { take() }
            else if ch == "-" { take(); num = "-" }
            else { num.append(ch) }
        }
        take(); run()
        return p
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
        // short and bushy (same path as face.js)
        s.move(to: P(100, m))
        s.addCurve(to: P(119, m + 4.5), control1: P(106.33, m - 2), control2: P(115.2, m + 2))
        s.addCurve(to: P(118.43, m + 10), control1: P(120.9, m + 6.7), control2: P(120.33, m + 9))
        s.addCurve(to: P(105.13, m + 10), control1: P(116.53, m + 7.8), control2: P(111.4, m + 11))
        s.addQuadCurve(to: P(94.87, m + 10), control: P(100, m + 8))
        s.addCurve(to: P(81.57, m + 10), control1: P(88.6, m + 11), control2: P(83.47, m + 7.8))
        s.addCurve(to: P(81, m + 4.5), control1: P(79.67, m + 9), control2: P(79.1, m + 6.7))
        s.addCurve(to: P(100, m), control1: P(84.8, m + 2), control2: P(93.67, m - 2))
        s.closeSubpath()
        return s
    }
}
