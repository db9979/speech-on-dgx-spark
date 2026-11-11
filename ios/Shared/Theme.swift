import SwiftUI
import UIKit

// "Klar 2 · Systemstil" (Redesign Stufe 8): the panel's tokens (app/panel/static/tokens.css) for the iPhone app, its
// widgets and the share sheet. Lists, bars and fields stay the system's own (List .insetGrouped, SF Symbols); this
// file holds the one accent, the status colours (a dot with its word), the neutral greys for drawn things, the
// spacing on the 4/8 grid and the radii. Every colour follows the system's light/dark appearance. The names and
// values are the companion's (tools/begleiter/mac/Sources/Theme.swift); test_design_tokens.Apps checks both against
// tokens.css, and no other app file writes a colour of its own (the drawn faces excepted).

enum Theme {
    /// light / dark from tokens.css (:root and :root[data-theme=dark])
    private static func c(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(uiColor: UIColor { t in
            let h = t.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((h >> 16) & 0xff) / 255, green: CGFloat((h >> 8) & 0xff) / 255,
                           blue: CGFloat(h & 0xff) / 255, alpha: 1)
        })
    }

    // tokens.css: --bg --card --fg --mut --line --side --acc --ok --warn --bad --visor (light, dark)
    static let bg = c(0xf5f5f7, 0x161618)
    static let card = c(0xffffff, 0x242426)
    static let fg = c(0x1d1d1f, 0xf5f5f7)
    static let muted = c(0x6e6e73, 0xa1a1a6)
    static let line = c(0xe2e2e7, 0x38383b)
    static let soft = c(0xefeff2, 0x1f1f21)
    static let accent = c(0x0071e3, 0x0a84ff)
    static let ok = c(0x28a745, 0x32d74b)
    static let warn = c(0xe08600, 0xff9f0a)
    static let bad = c(0xe5342b, 0xff453a)
    static let visor = c(0x151a2e, 0x070912)
    /// --faint: placeholders, arrows, a part that is off
    static let faint = c(0xa1a1a6, 0x6e6e73)
    /// --okt --warnt --badt: the word beside a status dot, readable on the card
    static let okText = c(0x1f7a35, 0x32d74b)
    static let warnText = c(0xa35a00, 0xffb340)
    static let badText = c(0xc4271f, 0xff6961)
    /// --on-acc: text and symbols on a coloured ground (accent, status, photo, video), the same in light and dark
    static let onAccent = c(0xffffff, 0xffffff)
    /// black for the ground of a call, a photo in full and veils (mostly with opacity), the same in light and dark
    static let shade = c(0x000000, 0x000000)
    // --wk-*: the kinds of points of the knowledge map, the same as in the panel
    static let wkPerson = c(0xbe185d, 0xbe185d)
    static let wkFirma = c(0x0369a1, 0x0369a1)
    static let wkOrt = c(0xb45309, 0xb45309)
    static let wkVertrag = c(0x7c3aed, 0x7c3aed)
    static let wkKonto = c(0x047857, 0x047857)
    static let wkFrist = c(0xdc2626, 0xdc2626)
    // --lst-*: the colours of a list (tasks.COLORS), the same as in the panel, light and dark alike
    static let lstBlau = c(0x0a7aff, 0x0a7aff)
    static let lstRot = c(0xff3b30, 0xff3b30)
    static let lstOrange = c(0xff9500, 0xff9500)
    static let lstGelb = c(0xe6b800, 0xe6b800)
    static let lstGruen = c(0x34c759, 0x34c759)
    static let lstTuerkis = c(0x30b0c7, 0x30b0c7)
    static let lstLila = c(0xaf52de, 0xaf52de)
    static let lstRosa = c(0xff2d55, 0xff2d55)
    static let lstBraun = c(0xa2845e, 0xa2845e)
    static let lstGrau = c(0x8e8e93, 0x8e8e93)
    /// a list's colour by its name from the Spark (tasks.COLORS); the accent for one it does not know
    static func list(_ name: String) -> Color {
        ["blau": lstBlau, "rot": lstRot, "orange": lstOrange, "gelb": lstGelb, "gruen": lstGruen, "tuerkis": lstTuerkis, "lila": lstLila, "rosa": lstRosa, "braun": lstBraun, "grau": lstGrau][name] ?? accent
    }

    // spacing on the 4/8 grid (--s1 … --s12)
    static let s1: CGFloat = 4
    static let s2: CGFloat = 8
    static let s3: CGFloat = 12
    static let s4: CGFloat = 16
    static let s6: CGFloat = 24
    // radii: badge, button and field, list row, group, window (--r-badge --r-ctl --r-item --r-box --r-win)
    static let rBadge: CGFloat = 5
    static let rCtl: CGFloat = 6
    static let rItem: CGFloat = 8
    static let rBox: CGFloat = 10
    static let rWin: CGFloat = 12
    // fixed heights: a tap target and a list row (--h-touch --h-item)
    static let hTouch: CGFloat = 44
    static let hItem: CGFloat = 52
}

/// A status as a dot with its word (Klar 2): green, yellow or red never stands alone and never colours a whole box.
struct StatusDot: View {
    let color: Color

    var body: some View {
        Circle().fill(color).frame(width: 8, height: 8).accessibilityHidden(true)
    }
}
