import AppKit
import SwiftUI

/// The face the admin picked for everybody (panel chat.face, sent in config.face): "robot", "comic" or
/// "comic_woman" (V01.0.497). Unknown names keep the robot, like the panel.
enum FaceKind: String {
    case robot, comic
    case comicWoman = "comic_woman"

    init(_ any: Any?) {
        self = FaceKind(rawValue: any as? String ?? "") ?? .robot
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

/// The comic woman (V01.0.497) as a still: the same drawing as the panel (static/js/face.js comicWSvg +
/// comicIcon) and the iPhone app, at rest, as fixed layers (path, fill, outline, width, opacity) in the
/// panel's 200 x 200 box. Only these fixed strings are ever drawn.
enum ComicWomanStill {
    private static let bg = CGColor(red: 0xf5 / 255.0, green: 0xdf / 255.0, blue: 0xe6 / 255.0, alpha: 1)
    private static let layers: [(String, UInt32?, UInt32?, CGFloat, CGFloat)] = [
        ("M82 138 L80 200 L120 200 L118 138Z", 0xf0b48c, 0x22180f, 2.6, 1),
        ("M0 200 L0 196 Q30 180 80 177 Q100 194 120 177 Q170 180 200 196 L200 200Z", 0x7cc4b8, 0x22180f, 2.6, 1),
        ("M86 174 Q100 186 114 174", nil, 0xd9b45a, 1.6, 1),
        ("M102.6 183 C102.6 184.44 101.44 185.6 100 185.6 C98.56 185.6 97.4 184.44 97.4 183 C97.4 181.56 98.56 180.4 100 180.4 C101.44 180.4 102.6 181.56 102.6 183Z", 0xe9c46a, 0x22180f, 1, 1),
        ("M100 24 C152 24 164 66 160 118 C157 156 166 184 176 200 L121 200 L119 140 L81 140 L79 200 L24 200 C34 184 43 156 40 118 C36 66 48 24 100 24Z", 0x4a2c22, 0x22180f, 2.6, 1),
        ("M52 96 C44 130 46 168 34 200 L62 200 C64 172 58 140 60 110Z M148 96 C156 130 154 168 166 200 L138 200 C136 172 142 140 140 110Z", 0x4a2c22, 0x22180f, 2.6, 1),
        ("M100 38 C132.4 38 145 60 145 92 C145 128 132 149 119 159 Q100 169 81 159 C68 149 55 128 55 92 C55 60 67.6 38 100 38Z", 0xf0b48c, 0x22180f, 2.6, 1),
        ("M100 156 Q95 158.5 92 155 M100 156 Q105 158.5 108 155", nil, 0xc9825e, 1.1, 0.5),
        ("M82 112 C82 114.76 77.97 117 73 117 C68.03 117 64 114.76 64 112 C64 109.24 68.03 107 73 107 C77.97 107 82 109.24 82 112Z", 0xef7f86, nil, 0, 0.35),
        ("M136 112 C136 114.76 131.97 117 127 117 C122.03 117 118 114.76 118 112 C118 109.24 122.03 107 127 107 C131.97 107 136 109.24 136 112Z", 0xef7f86, nil, 0, 0.35),
        ("M89.5 91 C89.5 94.87 84.8 98 79 98 C73.2 98 68.5 94.87 68.5 91 C68.5 87.13 73.2 84 79 84 C84.8 84 89.5 87.13 89.5 91Z", 0xfbfbf8, nil, 0, 1),
        ("M84.8 91.5 C84.8 94.7 82.2 97.3 79 97.3 C75.8 97.3 73.2 94.7 73.2 91.5 C73.2 88.3 75.8 85.7 79 85.7 C82.2 85.7 84.8 88.3 84.8 91.5Z", 0x6b4a2e, nil, 0, 1),
        ("M81.8 91.5 C81.8 93.05 80.55 94.3 79 94.3 C77.45 94.3 76.2 93.05 76.2 91.5 C76.2 89.95 77.45 88.7 79 88.7 C80.55 88.7 81.8 89.95 81.8 91.5Z", 0x141414, nil, 0, 1),
        ("M81.8 89.6 C81.8 90.26 81.26 90.8 80.6 90.8 C79.94 90.8 79.4 90.26 79.4 89.6 C79.4 88.94 79.94 88.4 80.6 88.4 C81.26 88.4 81.8 88.94 81.8 89.6Z", 0xffffff, nil, 0, 1),
        ("M73.8 84.92 Q79 83.08 84.2 84.92Z", 0xe09d77, nil, 0, 1),
        ("M89.5 91 C89.5 94.87 84.8 98 79 98 C73.2 98 68.5 94.87 68.5 91 C68.5 87.13 73.2 84 79 84 C84.8 84 89.5 87.13 89.5 91Z", nil, 0x22180f, 1.82, 1),
        ("M68 84.92 Q79 86.52 90 84.92", nil, 0x22180f, 2.99, 1),
        ("M70.4 85 L66.2 81.4 M68.6 87.2 L64 85.6 M73.2 84.4 L70.6 80.4", nil, 0x22180f, 1.6, 1),
        ("M90 78 Q77 71 67 77", nil, 0x4a2c22, 3.2, 1),
        ("M131.5 91 C131.5 94.87 126.8 98 121 98 C115.2 98 110.5 94.87 110.5 91 C110.5 87.13 115.2 84 121 84 C126.8 84 131.5 87.13 131.5 91Z", 0xfbfbf8, nil, 0, 1),
        ("M126.8 91.5 C126.8 94.7 124.2 97.3 121 97.3 C117.8 97.3 115.2 94.7 115.2 91.5 C115.2 88.3 117.8 85.7 121 85.7 C124.2 85.7 126.8 88.3 126.8 91.5Z", 0x6b4a2e, nil, 0, 1),
        ("M123.8 91.5 C123.8 93.05 122.55 94.3 121 94.3 C119.45 94.3 118.2 93.05 118.2 91.5 C118.2 89.95 119.45 88.7 121 88.7 C122.55 88.7 123.8 89.95 123.8 91.5Z", 0x141414, nil, 0, 1),
        ("M123.8 89.6 C123.8 90.26 123.26 90.8 122.6 90.8 C121.94 90.8 121.4 90.26 121.4 89.6 C121.4 88.94 121.94 88.4 122.6 88.4 C123.26 88.4 123.8 88.94 123.8 89.6Z", 0xffffff, nil, 0, 1),
        ("M115.8 84.92 Q121 83.08 126.2 84.92Z", 0xe09d77, nil, 0, 1),
        ("M131.5 91 C131.5 94.87 126.8 98 121 98 C115.2 98 110.5 94.87 110.5 91 C110.5 87.13 115.2 84 121 84 C126.8 84 131.5 87.13 131.5 91Z", nil, 0x22180f, 1.82, 1),
        ("M110 84.92 Q121 86.52 132 84.92", nil, 0x22180f, 2.99, 1),
        ("M129.6 85 L133.8 81.4 M131.4 87.2 L136 85.6 M126.8 84.4 L129.4 80.4", nil, 0x22180f, 1.6, 1),
        ("M110 78 Q123 71 133 77", nil, 0x4a2c22, 3.2, 1),
        ("M96 110 C91 113 92 121 97.5 120 Q100 122 102.5 120 C108 121 109 113 104 110", 0xc9825e, nil, 0, 0.3),
        ("M97.5 97 C97.5 103.5 96 109.75 95.2 112 C91 116 93 120 96.5 119.5 Q100 121 103.5 119.5 C107 120 109 116 104.8 112", nil, 0x22180f, 2.6, 1),
        ("M89 133 Q95 128.8 100 131 Q105 128.8 111 133 Q100 133 89 133Z", 0xc8565a, 0x22180f, 1.56, 1),
        ("M89 133 Q100 141.5 111 133 Q100 133 89 133Z", 0xc8565a, 0x22180f, 1.56, 1),
        ("M90 133 Q100 133.6 110 133", nil, 0x22180f, 2.08, 1),
        ("M52 104 C44 54 68 27 101 27 C134 27 156 54 148 104 C146 84 142 70 136 62 C126 50 116 47 107 47 C90 50 74 60 66 74 C60 82 55 92 52 104Z", 0x4a2c22, 0x22180f, 2.6, 1),
        ("M107 47 C96 52 82 60 72 74 M107 47 C120 52 132 62 138 74", nil, 0x22180f, 1.3, 0.45),
    ]

    private static func c(_ v: UInt32) -> CGColor {
        CGColor(red: CGFloat(v >> 16 & 255) / 255, green: CGFloat(v >> 8 & 255) / 255, blue: CGFloat(v & 255) / 255, alpha: 1)
    }

    /// absolute M, L, C, Q and Z of a fixed path string
    private static func path(_ d: String) -> CGPath {
        let p = CGMutablePath()
        var cmd: Character = "M", n: [CGFloat] = [], num = ""
        func take() { if let v = Double(num) { n.append(CGFloat(v)) }; num = "" }
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

    /// Draws into `rect` of a context whose y axis points down, the head filling a circle like ComicStill.
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
        for (d, fill, stroke, w, a) in layers {
            let p = path(d)
            g.saveGState()
            g.setAlpha(a)
            if let fill { g.addPath(p); g.setFillColor(c(fill)); g.fillPath() }
            if let stroke { g.addPath(p); g.setStrokeColor(c(stroke)); g.setLineWidth(w); g.strokePath() }
            g.restoreGState()
        }
    }
}

/// The comic still as a SwiftUI view (`woman`: the comic woman).
struct ComicFaceView: View {
    var size: CGFloat
    var woman = false

    var body: some View {
        Canvas { ctx, sz in
            ctx.withCGContext { g in
                let r = CGRect(origin: .zero, size: sz)
                if woman { ComicWomanStill.draw(g, in: r) } else { ComicStill.draw(g, in: r) }
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
