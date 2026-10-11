import AppKit
import SwiftUI

/// The face the admin picked for everybody (panel chat.face, sent in config.face): "robot" or "comic".
/// Unknown names keep the robot, like the panel.
enum FaceKind: String {
    case robot, comic

    init(_ any: Any?) {
        self = (any as? String) == "comic" ? .comic : .robot
    }

    /// the last face the Spark named, so the next start shows it before the first config
    static var saved: FaceKind {
        get { FaceKind(UserDefaults.standard.string(forKey: "face")) }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: "face") }
    }
}

/// The comic face (a caricature of Dominik) as a still: the same shapes and colours as the panel
/// (static/js/face.js comicSvg + comicIcon) and the iPhone app (ios/Spark/ComicFace.swift), at rest
/// (lids as in the panel's small picture, eyes ahead, mouth closed). Drawn with Core Graphics so the
/// windows (SwiftUI) and the menu-bar icon (NSImage) share one drawing.
enum ComicStill {
    // shapes (COMIC in face.js)
    private static let top: CGFloat = 36, hw: CGFloat = 47, cheekY: CGFloat = 92, chinW: CGFloat = 23, chinY: CGFloat = 167
    private static let eyeX: CGFloat = 21, eyeY: CGFloat = 90, eRx: CGFloat = 10.5, eRy: CGFloat = 6.5, lidBase: CGFloat = 0.36
    private static let noseLen: CGFloat = 29, noseW: CGFloat = 10, stacheS: CGFloat = 1.06, mouthW: CGFloat = 8, lw: CGFloat = 2.6
    private static var m: CGFloat { eyeY + noseLen + 6 }
    private static var mcy: CGFloat { m + 15 * stacheS }
    private static let hairTips: [(CGFloat, CGFloat)] = [
        (-6, 1), (-12.8, 1.31), (-19.7, 1), (-26.5, 1.19), (-33.3, 1), (-40.2, 1.33), (-47, 1), (-53.8, 1.22), (-60.7, 1),
        (-67.5, 1.3), (-74.3, 1), (-81.2, 1.2), (-88, 1), (-94.8, 1.34), (-101.7, 1), (-108.5, 1.21), (-115.3, 1),
        (-122.2, 1.3), (-129, 1), (-135.8, 1.18), (-142.7, 1), (-149.5, 1.32), (-156.3, 1), (-163.2, 1.24), (-170, 1)]

    private static func c(_ v: UInt32, _ a: CGFloat = 1) -> CGColor {
        CGColor(red: CGFloat(v >> 16 & 255) / 255, green: CGFloat(v >> 8 & 255) / 255, blue: CGFloat(v & 255) / 255, alpha: a)
    }
    private static let skin = c(0xf0b48c), lidC = c(0xe09d77), shade = c(0xc9825e), hair = c(0x2b2626)
    private static let stache = c(0x382c27), line = c(0x22180f), bg = c(0xd9e6f5), shirt = c(0xf6e27a)
    private static let chain = c(0xc9cdd2), irisC = c(0x6b6a3e), pupil = c(0x141414), eyeWhite = c(0xfbfbf8)

    private static func P(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: x, y: y) }

    /// Draws into `rect` of a context whose y axis points down (SwiftUI, a flipped NSImage).
    /// The head fills a circle like the panel's small picture (viewBox 36 24 128 128).
    static func draw(_ g: CGContext, in rect: CGRect) {
        let side = min(rect.width, rect.height)
        guard side > 0 else { return }
        let box = CGRect(x: rect.midX - side / 2, y: rect.midY - side / 2, width: side, height: side)
        g.saveGState()
        defer { g.restoreGState() }
        g.addEllipse(in: box)
        g.clip()
        g.setFillColor(bg)
        g.fill(box)
        let s = side / 128
        g.translateBy(x: box.minX, y: box.minY)
        g.scaleBy(x: s, y: s)
        g.translateBy(x: -36, y: -24)
        g.setLineCap(.round)
        g.setLineJoin(.round)

        func outline(_ p: CGPath, _ fill: CGColor) {
            g.addPath(p); g.setFillColor(fill); g.fillPath()
            g.addPath(p); g.setStrokeColor(line); g.setLineWidth(lw); g.strokePath()
        }
        func stroke(_ p: CGPath, _ col: CGColor, _ w: CGFloat) {
            g.addPath(p); g.setStrokeColor(col); g.setLineWidth(w); g.strokePath()
        }
        let cy = chinY

        // neck, shirt, chain
        let neck = CGMutablePath()
        neck.move(to: P(80, cy - 26)); neck.addLine(to: P(78, 200)); neck.addLine(to: P(122, 200)); neck.addLine(to: P(120, cy - 26))
        neck.closeSubpath()
        outline(neck, skin)
        let sh = CGMutablePath()
        sh.move(to: P(0, 200)); sh.addLine(to: P(0, cy + 30))
        sh.addQuadCurve(to: P(78, cy + 11), control: P(30, cy + 14))
        sh.addQuadCurve(to: P(122, cy + 11), control: P(100, cy + 27))
        sh.addQuadCurve(to: P(200, cy + 30), control: P(170, cy + 14))
        sh.addLine(to: P(200, 200)); sh.closeSubpath()
        outline(sh, shirt)
        let ch = CGMutablePath()
        ch.move(to: P(83, cy + 8)); ch.addQuadCurve(to: P(117, cy + 8), control: P(100, cy + 24))
        g.saveGState()
        g.setLineDash(phase: 0, lengths: [1.8, 1.3])
        stroke(ch, chain, 2.2)
        g.restoreGState()

        // ears
        for k: CGFloat in [-1, 1] {
            let ex = 100 + k * (hw + 1)
            outline(CGPath(ellipseIn: CGRect(x: ex - 7, y: eyeY + 8 - 13, width: 14, height: 26), transform: nil), skin)
            let e = CGMutablePath()
            e.move(to: P(ex - k, eyeY + 1)); e.addQuadCurve(to: P(ex - k, eyeY + 14), control: P(ex + 2 * k, eyeY + 7))
            stroke(e, shade, 1.3)
        }
        let face = facePath()
        outline(face, skin)
        g.saveGState()
        g.addPath(face); g.clip()
        g.setAlpha(0.13)
        g.setFillColor(hair)
        g.fillEllipse(in: CGRect(x: 100 - (hw - 2), y: m + 30 - 36, width: 2 * (hw - 2), height: 72))
        g.restoreGState()
        let chin = CGMutablePath()
        chin.move(to: P(100, cy - 9)); chin.addQuadCurve(to: P(91, cy - 10), control: P(94, cy - 6))
        chin.move(to: P(100, cy - 9)); chin.addQuadCurve(to: P(109, cy - 10), control: P(106, cy - 6))
        g.saveGState(); g.setAlpha(0.6); stroke(chin, shade, 1.2); g.restoreGState()

        // eyes, lids, brows
        for k: CGFloat in [-1, 1] {
            let x = 100 + k * eyeX, y = eyeY, by = y - eRy - 7
            let eye = CGPath(ellipseIn: CGRect(x: x - eRx, y: y - eRy, width: 2 * eRx, height: 2 * eRy), transform: nil)
            g.saveGState()
            g.addPath(eye); g.clip()
            g.setFillColor(eyeWhite); g.addPath(eye); g.fillPath()
            g.setFillColor(irisC); g.fillEllipse(in: CGRect(x: x - 5.53, y: y - 5.53, width: 11.06, height: 11.06))
            g.setFillColor(pupil); g.fillEllipse(in: CGRect(x: x - 2.76, y: y - 2.76, width: 5.52, height: 5.52))
            g.setFillColor(.white); g.fillEllipse(in: CGRect(x: x + 0.5, y: y - 2.9, width: 2.2, height: 2.2))
            let y0 = y - eRy - 1, h = (2 * eRy + 2) * lidBase, ly = y0 + h
            g.setFillColor(lidC); g.fill(CGRect(x: x - eRx - 1, y: y0, width: 2 * eRx + 2, height: h))
            g.restoreGState()
            stroke(eye, line, lw * 0.7)
            let lid = CGMutablePath()
            lid.move(to: P(x - eRx - 0.5, ly)); lid.addQuadCurve(to: P(x + eRx + 0.5, ly), control: P(x, ly + 1.6))
            stroke(lid, line, lw * 0.95)
            let b = CGMutablePath()
            b.move(to: P(x - k * 12, by + 1)); b.addQuadCurve(to: P(x + k * 13, by + 2), control: P(x + k, by - 5))
            stroke(b, hair, 5)
        }

        // nose
        let ny = eyeY, nl = noseLen, nw = noseW
        let ns = CGMutablePath()
        ns.move(to: P(100 - nw * 0.5, ny + nl - 6))
        ns.addCurve(to: P(97, ny + nl + 4), control1: P(100 - nw - 1, ny + nl - 3), control2: P(100 - nw, ny + nl + 5))
        ns.addQuadCurve(to: P(103, ny + nl + 4), control: P(100, ny + nl + 6))
        ns.addCurve(to: P(100 + nw * 0.5, ny + nl - 6), control1: P(100 + nw, ny + nl + 5), control2: P(100 + nw + 1, ny + nl - 3))
        g.saveGState(); g.setAlpha(0.35); g.addPath(ns); g.setFillColor(shade); g.fillPath(); g.restoreGState()
        let nose = CGMutablePath()
        nose.move(to: P(97, ny + 4))
        nose.addCurve(to: P(100 - nw * 0.6, ny + nl - 4), control1: P(97, ny + nl * 0.5), control2: P(100 - nw * 0.5, ny + nl * 0.75))
        nose.addCurve(to: P(96, ny + nl + 4), control1: P(100 - nw - 1, ny + nl), control2: P(100 - nw + 1, ny + nl + 5))
        nose.addQuadCurve(to: P(104, ny + nl + 4), control: P(100, ny + nl + 6))
        nose.addCurve(to: P(100 + nw * 0.6, ny + nl - 4), control1: P(100 + nw - 1, ny + nl + 5), control2: P(100 + nw + 1, ny + nl))
        stroke(nose, line, lw)

        // closed mouth and lower lip under the mustache
        let w = mouthW, my = mcy
        let ml = CGMutablePath()
        ml.move(to: P(100 - w, my)); ml.addQuadCurve(to: P(100 + w, my), control: P(100, my + 0.6))
        stroke(ml, line, lw * 0.9)
        let lipY = my + 4
        let lip = CGMutablePath()
        lip.move(to: P(100 - w * 0.55, lipY)); lip.addQuadCurve(to: P(100 + w * 0.55, lipY), control: P(100, lipY + 2.4))
        g.saveGState(); g.setAlpha(0.7); stroke(lip, shade, 1.4); g.restoreGState()

        // mustache, scaled around (100, m)
        var t = CGAffineTransform(translationX: 100, y: m).scaledBy(x: stacheS, y: stacheS).translatedBy(x: -100, y: -m)
        if let mu = stachePath().copy(using: &t) { outline(mu, stache) }
        let strands = CGMutablePath()
        for (x, dy, dx, ey) in [(88.0, 3.0, -3.0, 7.0), (95, 2, -1, 7), (105, 2, 1, 7), (112, 3, 3, 7), (80, 7, -4, 7), (120, 7, 4, 7)] as [(CGFloat, CGFloat, CGFloat, CGFloat)] {
            strands.move(to: P(x, m + dy)); strands.addLine(to: P(x + dx, m + dy + ey))
        }
        var ts = CGAffineTransform(translationX: 100, y: m).scaledBy(x: 0.63, y: 0.77).translatedBy(x: -100, y: -m).concatenating(t)
        if let st = strands.copy(using: &ts) {
            g.saveGState(); g.setAlpha(0.25); stroke(st, CGColor(gray: 0, alpha: 1), 0.9); g.restoreGState()
        }

        outline(hairPath(), hair)
    }

    private static func facePath() -> CGPath {
        let f = CGMutablePath()
        f.move(to: P(100, top))
        f.addCurve(to: P(100 + hw, cheekY), control1: P(100 + hw * 0.72, top), control2: P(100 + hw, top + 22))
        f.addCurve(to: P(100 + chinW, chinY - 5), control1: P(100 + hw, cheekY + 36), control2: P(100 + chinW + 13, chinY - 15))
        f.addQuadCurve(to: P(100 - chinW, chinY - 5), control: P(100, chinY + 6))
        f.addCurve(to: P(100 - hw, cheekY), control1: P(100 - chinW - 13, chinY - 15), control2: P(100 - hw, cheekY + 36))
        f.addCurve(to: P(100, top), control1: P(100 - hw, top + 22), control2: P(100 - hw * 0.72, top))
        f.closeSubpath()
        return f
    }

    private static func hairPath() -> CGPath {
        let cy = top + 44, rx = hw + 4
        let h = CGMutablePath()
        h.move(to: P(100 + hw + 2, cy))
        for (a, k) in hairTips {
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

    private static func stachePath() -> CGPath {
        let s = CGMutablePath()
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

/// The comic still as a SwiftUI view.
struct ComicFaceView: View {
    var size: CGFloat

    var body: some View {
        Canvas { ctx, sz in
            ctx.withCGContext { g in ComicStill.draw(g, in: CGRect(origin: .zero, size: sz)) }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
