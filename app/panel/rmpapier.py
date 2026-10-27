"""Paper for the reMarkable: folders by kind, designed sheets in the device's own page format, ticked boxes read
back (plan remarkable-aufwerten/plan.md, packages A, B and C; Dominik 2026-10-13 „1a 2b 3a 4a 5 umsetzen“).

Three parts, each off: the admin switch chat.remarkable_paper (below "Aufs reMarkable schicken"); released, each works
for every profile the admin did not block (chat.deny); "Selbst aufräumen" keeps a preference (rm_tidy); guests never.

rmordner    "Ordner nach Art": what the Spark puts on the reMarkable goes into one folder per kind below "Spark" (or
            the chosen folder): Morgenblatt, Wochenrückblick, Besprechungen, Antworten, Web und Anhänge, Eingang,
            Archiv. The guide lies on top as a favourite. The Spark keeps a folder's id, not its name, so renaming or
            moving it is fine; a folder gone is made again. "Jetzt einsortieren" moves the Spark's own loose documents.
rmaufraeumen "Selbst aufräumen": once a day Morgenblatt and Wochenrückblick without handwriting go to "Archiv" after
            ARCHIVE_DAYS, and from there into the reMarkable's trash (still restorable there) after TRASH_DAYS. A
            document with handwriting is never moved by itself. Only documents the Spark made (remarkable.load()["made"]).
rmpapier    "Gestaltete Blätter": Morgenblatt, Wochenrückblick, summaries, answers, the inbox and the guide become PDFs
            in the page format of the person's model (MODELS; the page is the screen, so nothing is scaled or shifted),
            with a header band, numbered sections, cards and ruled lines, colour only where the device shows colour.
            Each sheet has a box "Kann weg" (top right): ticked, the Spark puts the document into the trash (into
            "Archiv" when there is other handwriting on it). The Morgenblatt lists today's reminders with boxes: ticked
            = done (the reminder goes), the box filled in completely = taken back (the reminder comes back).
            Web pages stay EPUB (Dominik 3a). A sheet with handwriting is never filled with new text: a new version
            comes instead (remarkable.place).

Reading is geometry with fixed rules, never the language model (judge()): the Spark keeps each box's place in mm per
sheet ("papers"), reads the strokes of the sheet's pages from the cloud when the sheet changed, maps them onto the
page (the page file names its size, SceneInfo.paper_size; else MODELS) and counts ink inside each box. A one-time
"Abgleich-Blatt" (four targets) corrects the mapping when a device places strokes differently (calibration). Only
sheets the Spark made itself and recorded are read: a copied or foreign PDF does nothing. "Kontrollbild" draws what
was read (green ticked, amber unclear, grey taken back). Nothing read here goes to the language model.
"""
import asyncio
import io
import json
import math
import re
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import features
import guard
import netguard
import profiles
import remarkable
import core
from core import assistant, browser_profile

router = APIRouter()

# the page is the screen: width and height in pixels, pixels per inch; mm = px / ppi * 25.4
MODELS = {
    "rm2": {"de": "reMarkable 1 / 2", "en": "reMarkable 1 / 2", "px": (1404, 1872), "ppi": 226, "color": False},
    "pro": {"de": "Paper Pro", "en": "Paper Pro", "px": (1620, 2160), "ppi": 229, "color": True},
    "move": {"de": "Paper Pro Move", "en": "Paper Pro Move", "px": (954, 1696), "ppi": 264, "color": True},
}
# folders below the base folder, one per kind (rmordner); "" = the base folder itself
ARTEN = {"aufgaben": "Aufgaben", "morgen": "Morgenblatt", "woche": "Wochenrückblick", "besprechung": "Besprechungen", "antwort": "Antworten",
         "web": "Web und Anhänge", "eingang": "Eingang", "archiv": "Archiv"}
# the Spark's own loose documents from before the folders, by their title ("Jetzt einsortieren")
OLD_NAMES = ((re.compile(r"^Morgenblatt\b"), "morgen"), (re.compile(r"^Wochenrückblick\b"), "woche"),
             (re.compile(r"^Zusammenfassung\b"), "besprechung"), (re.compile(r"^Antwort:"), "antwort"),
             (re.compile(r"^Eingang \d"), "eingang"))
ARCHIVE_DAYS = 7            # Morgenblatt / Wochenrückblick without handwriting -> Archiv (Dominik 4a)
TRASH_DAYS = 30             # Archiv without handwriting -> the reMarkable's trash (Dominik 4a)
TIDY_MOST = 30              # documents moved in one tidy-up
MAX_PAPERS = 60             # sheets whose boxes are kept per profile
MAX_CHECK = 12              # changed sheets read in one round
MAX_FIELDS = 80             # boxes on one sheet
BOX = 6.0                   # mm, a box's side
TOL = 2.0                   # mm around a box that still counts as inside
NEAR = 6.0                  # mm: ink this close but not inside makes a box "unclear"
INK_MIN = 3.0               # mm of ink inside a box make it ticked
FILLED = 0.7                # share of a box covered: filled in = taken back
NOTES_MM = 15.0             # mm of ink outside every box count as handwriting on the sheet
CALIB_RADIUS = 25.0         # mm around a target where its cross is looked for
CALIB_FIT = 2.5             # mm: the calibration is kept only when every target fits this well
MAX_POINTS = 400_000        # stroke points looked at per page


def on(key, uid):
    return bool(uid) and features.allowed(key, uid) and bool(remarkable.load(uid).get("token"))


# ---------------------------------------------------------------- the device
def model_key(uid, d=None):
    """The model the sheets are made for: the profile's choice, else the one its pages showed (auto), else rm2."""
    want = profiles.settings(uid).get("rm_model") or "auto"
    if want in MODELS:
        return want
    d = remarkable.load(uid) if d is None else d
    return detect(d.get("paper_size")) or "rm2"


def detect(size):
    """A model for a page size (SceneInfo.paper_size, in the device's pixels), or None."""
    try:
        w, h = (int(size[0]), int(size[1]))
    except (TypeError, ValueError, IndexError):
        return None
    for k, m in MODELS.items():
        if abs(m["px"][0] - w) <= 4 and abs(m["px"][1] - h) <= 4:
            return k
    return None


def model(key):
    m = dict(MODELS.get(key) or MODELS["rm2"], key=key if key in MODELS else "rm2")
    m["mm"] = (round(m["px"][0] / m["ppi"] * 25.4, 1), round(m["px"][1] / m["ppi"] * 25.4, 1))
    return m


def model_of(uid, d=None):
    """The model a profile's sheets are made for, in colour only on a colour screen and while the profile keeps colour
    (Ich → reMarkable „Farbe“, rm_color; Dominik 2026-10-27 „Farbe oder Graustufen“): the one place for both."""
    m = model(model_key(uid, d))
    if m["color"] and profiles.settings(uid).get("rm_color") == "grau":
        m["color"] = False
    return m


# ---------------------------------------------------------------- building a sheet
COLOR = {"acc": (91, 91, 240), "acc2": (14, 165, 198), "fg": (20, 24, 36), "mut": (95, 107, 133), "tint": (238, 240, 253),
         "tint2": (232, 247, 251), "line": (205, 209, 222), "paper": (255, 255, 255)}
GRAY = {"acc": (52, 56, 66), "acc2": (100, 104, 114), "fg": (0, 0, 0), "mut": (80, 80, 80), "tint": (232, 232, 232),
        "tint2": (240, 240, 240), "line": (175, 175, 175), "paper": (255, 255, 255)}
_KEEP = set("☐☑✓✔•–—„“”‚‘’…€·×→←↑↓≈≤≥°")
TIDY_MD = re.compile(r"\*\*|__|`")
LINK = re.compile(r"\[([^\]]{1,200})\]\((https?://[^)\s]{1,300})\)")
ITALIC = re.compile(r"(?<![\w*])[*_](?=\S)([^*_\n]{1,200}?)(?<=\S)[*_](?![\w*])")
GAP = re.compile(r"(?<=\S)[ ]+([,.:;!?])(?=\s|$)")      # „Blech :“ after an emoji was left out


# ---------------------------------------------------------------- reading the text (one reader for every document)
# Every document the Spark puts on the reMarkable reads its text here (Dominik 2026-10-21 „1a 2a 3a 4a 5a“): the designed
# sheet, the plain sheet and the EPUB draw the same blocks, so a list stays a list and a table a table everywhere.
HEAD = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
BUL = re.compile(r"^\s*[-*•+]\s+(.+)$")
NUM = re.compile(r"^\s*(\d{1,3})[.)]\s+(.+)$")
RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
TROW = re.compile(r"^\s*\|.*\|\s*$")
TSEP = re.compile(r"^\s*\|?(\s*:?-{2,}:?\s*\|)+\s*(:?-{2,}:?\s*)?\|?\s*$")
QUOTE = re.compile(r"^\s*>\s?(.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")
TABLE_COLS = 3              # wider tables become one line per row („Spalte: Wert“)
MAX_BLOCKS = 600


def inline(s):
    """One line without Markdown marks: **fett**, *kursiv*, `code`, [Link](url) -> Link (url)."""
    return ITALIC.sub(r"\1", TIDY_MD.sub("", LINK.sub(r"\1 (\2)", str(s or "")))).strip()


def _cells(line):
    return [inline(c) for c in line.strip().strip("|").split("|")]


def blocks(body):
    """The text as blocks: ("h", text), ("p", [lines]), ("ul", [items]), ("ol", [(number, text)]), ("table", [row, ...]),
    ("quote", [lines]), ("hr", None), ("pre", [lines]). A single line break stays one; a line that is only "**Teil**"
    is a heading (heads())."""
    out, lines, i = [], heads(str(body or "")).replace("\r", "").split("\n"), 0

    def add(kind, data):
        if out and out[-1][0] == kind and kind in ("ul", "ol", "p", "quote"):
            out[-1][1].extend(data)
        else:
            out.append((kind, list(data) if isinstance(data, list) else data))
    while i < len(lines) and len(out) < MAX_BLOCKS:
        ln = lines[i]
        i += 1
        if not ln.strip():
            if out and out[-1][0] in ("p", "quote"):
                out.append(("gap", None))
            continue
        if FENCE.match(ln):
            pre = []
            while i < len(lines) and not FENCE.match(lines[i]):
                pre.append(lines[i].rstrip())
                i += 1
            i += 1
            out.append(("pre", pre))
        elif TROW.match(ln):
            rows = [_cells(ln)]
            while i < len(lines) and TROW.match(lines[i]):
                if not TSEP.match(lines[i]):
                    rows.append(_cells(lines[i]))
                i += 1
            out.append(("table", rows))
        elif HEAD.match(ln):
            out.append(("h", inline(HEAD.match(ln).group(1))))
        elif RULE.match(ln):
            out.append(("hr", None))
        elif NUM.match(ln):
            m = NUM.match(ln)
            add("ol", [(m.group(1), inline(m.group(2)))])
        elif BUL.match(ln):
            add("ul", [inline(BUL.match(ln).group(1))])
        elif QUOTE.match(ln):
            add("quote", [inline(QUOTE.match(ln).group(1))])
        else:
            add("p", [inline(ln)])
    return [b for b in out if b[0] != "gap"]


def clean(s, n=4000):
    """Text for the sheet: no control signs, no emoji (the font has none), no Markdown marks."""
    s = LINK.sub(r"\1 (\2)", str(s or ""))
    s = TIDY_MD.sub("", s)
    out = []
    for ch in s[:n]:
        o = ord(ch)
        if ch in "\n\t" or (32 <= o < 0x2000) or ch in _KEEP:
            out.append(" " if ch == "\t" else ch)
    return GAP.sub(r"\1", "".join(out))


class Sheet:
    """One PDF in the page format of a model. Positions are mm from the top left; every box is recorded in fields."""

    def __init__(self, m, label, title, sub="", code="", weg=True, plain=False):
        from fpdf import FPDF
        import docrender
        self.m, (self.W, self.H) = m, m["mm"]
        self.small = self.W < 120
        self.s = 0.84 if self.small else 1.0
        self.M = 7.0 if self.small else 11.0
        self.c = COLOR if m["color"] and not plain else GRAY
        self.label, self.title, self.sub, self.code, self.weg = label, title, sub, code, weg
        self.fields, self.n_sec, self.page = [], 0, -1
        doc = self.doc = FPDF(unit="mm", format=(self.W, self.H))
        doc.set_auto_page_break(False)
        doc.set_margins(self.M, self.M, self.M)
        doc.set_creator("Spark")
        doc.set_title(clean(title, 200))
        reg, bold = docrender._font_files()
        self.fam = "DejaVu" if reg else "Helvetica"
        self.uni = bool(reg)
        if reg:
            doc.add_font("DejaVu", "", reg)
            doc.add_font("DejaVu", "B", bold)
        doc.alias_nb_pages()
        self._page(first=True)

    # -- small helpers
    def tx(self, s):
        s = clean(s)
        if self.uni:
            return s
        import docrender
        return "".join(docrender.LATIN1.get(ch, ch) for ch in s).encode("latin-1", "replace").decode("latin-1")

    def font(self, size, b=False, color="fg"):
        self.doc.set_font(self.fam, "B" if b else "", size * self.s)
        self.doc.set_text_color(*self.c[color])

    @property
    def bottom(self):
        return self.H - self.M - 7

    @property
    def width(self):
        return self.W - 2 * self.M

    def need(self, h):
        if self.doc.get_y() + h > self.bottom:
            self._page()

    def field(self, name, kind, x, y, w, h, label=""):
        if len(self.fields) < MAX_FIELDS:
            self.fields.append({"n": name, "k": kind, "p": self.page, "x": round(x, 2), "y": round(y, 2),
                                "w": round(w, 2), "h": round(h, 2), "t": clean(label, 60)})

    def box(self, x, y, name, kind, label=""):
        d = self.doc
        d.set_draw_color(*self.c["fg"])
        d.set_fill_color(*self.c["paper"])
        d.set_line_width(0.35)
        d.rect(x, y, BOX, BOX, style="DF", round_corners=True, corner_radius=0.8)
        self.field(name, kind, x, y, BOX, BOX, label)

    def _marks(self):
        """Corner marks: where the page is, for the eye and for the control picture."""
        d, a, o = self.doc, 3.5, 3.0
        d.set_draw_color(*self.c["fg"])
        d.set_line_width(0.4)
        for x, y, dx, dy in ((o, o, 1, 1), (self.W - o, o, -1, 1), (o, self.H - o, 1, -1), (self.W - o, self.H - o, -1, -1)):
            d.line(x, y, x + dx * a, y)
            d.line(x, y, x, y + dy * a)

    def _page(self, first=False):
        d = self.doc
        d.add_page()
        self.page += 1
        self._marks()
        if self.weg and first:
            x, y = self.W - self.M - BOX, 4.0
            self.box(x, y, "weg", "weg", "Kann weg")
            self.font(7.5, color="mut")
            d.set_xy(x - 24, y + 0.6)
            d.cell(22.5, 4.8, self.tx("Kann weg"), align="R")
        # footer
        self.font(7, color="mut")
        d.set_xy(self.M, self.H - self.M - 3)
        d.cell(self.width / 2, 4, self.tx(f"Spark · {self.label}"))
        d.set_xy(self.M + self.width / 2, self.H - self.M - 3)
        d.cell(self.width / 2, 4, self.tx(f"{self.code} · Seite {self.page + 1}/{{nb}}"), align="R")
        if first:
            self._header()
        else:
            self.font(8, True, "mut")
            d.set_xy(self.M, self.M + 1)
            d.cell(self.width - 30, 5, self.tx(self.title))
            d.set_y(self.M + 9)

    def _header(self):
        d, top = self.doc, self.M + 5
        # a small head, so the first page keeps room for the text (Dominik 2026-10-21 „Überschriften etwas kleiner“)
        lab, tit, sub = 6.5 * self.s, 13 * self.s if not self.small else 12 * self.s, 8 * self.s
        d.set_font(self.fam, "B", tit / self.s * self.s)
        lines = d.multi_cell(self.width - 10, tit * 0.42, self.tx(self.title), dry_run=True, output="LINES")[:3]
        h = 7 + 3 + len(lines) * tit * 0.42 + (4.5 if self.sub else 0)
        d.set_fill_color(*self.c["acc"])
        d.rect(self.M, top, self.width, h, style="F", round_corners=True, corner_radius=2.4)
        if self.m["color"]:
            d.set_fill_color(*self.c["acc2"])
            d.rect(self.M + self.width * 0.62, top + h - 1.4, self.width * 0.38 - 2.4, 1.4, style="F")
        d.set_text_color(255, 255, 255)
        d.set_font(self.fam, "B", lab)
        d.set_char_spacing(0.8)
        d.set_xy(self.M + 5, top + 3)
        d.cell(self.width - 10, 3.5, self.tx(("SPARK · " + self.label).upper()))
        d.set_char_spacing(0)
        d.set_font(self.fam, "B", tit)
        d.set_xy(self.M + 5, top + 7)
        d.multi_cell(self.width - 10, tit * 0.42, self.tx("\n".join(lines)))
        if self.sub:
            d.set_font(self.fam, "", sub)
            d.set_x(self.M + 5)
            d.cell(self.width - 10, 4.5, self.tx(self.sub))
        d.set_y(top + h + 3)

    # -- building blocks
    def section(self, title):
        self.n_sec += 1
        self.need(15 * self.s)
        d = self.doc
        y = d.get_y() + 2
        self.font(10, True, "acc2")
        d.set_xy(self.M, y)
        num = f"{self.n_sec:02d}"
        d.cell(d.get_string_width(num) + 2, 6 * self.s, num)
        self.font(10, True)
        d.cell(self.width - 12, 6 * self.s, self.tx(title)[:80])
        y += 6 * self.s
        d.set_draw_color(*self.c["acc"])
        d.set_line_width(0.45)
        d.line(self.M, y, self.W - self.M, y)
        d.set_y(y + 2.5)

    def para(self, text, size=9.5, color="fg", b=False, indent=0.0):
        d = self.doc
        if getattr(self, "_after_list", False) and not indent:
            d.set_y(d.get_y() + 1.5)
        self._after_list = False
        self.font(size, b, color)
        lh = size * self.s * 0.47
        w = self.width - indent
        for ln in d.multi_cell(w, lh, self.tx(text), dry_run=True, output="LINES"):
            self.need(lh)
            d.set_x(self.M + indent)
            d.cell(w, lh, ln, new_x="LMARGIN", new_y="NEXT")
        d.set_y(d.get_y() + 1.2)

    def bullet(self, text, size=9.5):
        d = self.doc
        self.need(size * self.s * 0.5)
        y = d.get_y()
        d.set_fill_color(*self.c["acc"])
        d.ellipse(self.M + 0.6, y + size * self.s * 0.47 / 2 - 0.7, 1.4, 1.4, style="F")
        self.para(text, size, indent=4.5)
        d.set_y(d.get_y() - 0.6)
        self._after_list = True

    def cards(self, pairs):
        """(value, label) side by side, two per row."""
        d = self.doc
        gap, h = 3.0, 15 * self.s
        w = (self.width - gap) / 2
        for i in range(0, len(pairs), 2):
            self.need(h + 2)
            y = d.get_y()
            for j, (v, lab) in enumerate(pairs[i:i + 2]):
                x = self.M + j * (w + gap)
                d.set_fill_color(*self.c["tint" if j == 0 else "tint2"])
                d.rect(x, y, w, h, style="F", round_corners=True, corner_radius=1.6)
                d.set_fill_color(*self.c["acc" if j == 0 else "acc2"])
                d.rect(x, y, 1.3, h, style="F")
                self.font(15, True, "acc" if j == 0 else "acc2")
                d.set_xy(x + 4, y + 1.6)
                d.cell(w - 6, 7 * self.s, self.tx(v)[:18])
                self.font(7.5, color="mut")
                d.set_xy(x + 4, y + 9 * self.s)
                d.cell(w - 6, 4, self.tx(lab)[:40])
            d.set_y(y + h + 3)

    def check(self, text, name, kind, sub=""):
        """A box with its text; the box is recorded."""
        d = self.doc
        self.font(9.5)
        lh = 9.5 * self.s * 0.47
        tw = self.width - BOX - 3
        lines = d.multi_cell(tw, lh, self.tx(text), dry_run=True, output="LINES")[:3]
        h = max(BOX, len(lines) * lh + (4 if sub else 0)) + 2.5
        self.need(h)
        y = d.get_y()
        self.box(self.M, y, name, kind, text)
        self.font(9.5)
        d.set_xy(self.M + BOX + 3, y + max(0.0, (BOX - lh) / 2) if len(lines) == 1 and not sub else y)
        d.multi_cell(tw, lh, "\n".join(lines), new_x="LMARGIN", new_y="NEXT")
        if sub:
            self.font(7.5, color="mut")
            d.set_x(self.M + BOX + 3)
            d.cell(tw, 4, self.tx(sub)[:90], new_x="LMARGIN", new_y="NEXT")
        d.set_y(y + h)

    def choice(self, text, item, options, sub=""):
        """A point with its answers side by side: [(key, label)], each a box "item|key" (kind "wahl"); the panel
        decided beforehand what each answer does (rmaufgaben.py), the paper only picks one of them."""
        d = self.doc
        self.font(9.5, True)
        lh = 9.5 * self.s * 0.47
        lines = d.multi_cell(self.width, lh, self.tx(text), dry_run=True, output="LINES")[:3]
        gap = 2 * TOL + 3          # from a label to the next box: more than the box's margin
        self.font(8.5)
        widths = [BOX + 1.5 + d.get_string_width(self.tx(lab)) for _, lab in options]
        rows, row, w = [], [], 0.0
        for (k, lab), wd in zip(options, widths):
            if row and w + wd + gap > self.width:
                rows.append(row)
                row, w = [], 0.0
            row.append((k, lab, wd))
            w += wd + gap
        rows.append(row)
        h = len(lines) * lh + (4 if sub else 0) + len(rows) * (BOX + 2 * TOL + 1) + 3
        self.need(h)
        y = d.get_y()
        self.font(9.5, True)
        d.set_xy(self.M, y)
        d.multi_cell(self.width, lh, "\n".join(lines), new_x="LMARGIN", new_y="NEXT")
        if sub:
            self.font(7.5, color="mut")
            d.set_x(self.M)
            d.cell(self.width, 4, self.tx(sub)[:110], new_x="LMARGIN", new_y="NEXT")
        y = d.get_y() + TOL
        for row in rows:
            x = self.M + TOL
            for k, lab, wd in row:
                self.box(x, y, f"{item}|{k}", "wahl", f"{text[:40]}: {lab}")
                self.font(8.5)
                d.set_xy(x + BOX + 1.5, y + (BOX - 4) / 2)
                d.cell(wd - BOX - 1.5, 4, self.tx(lab))
                x += wd + gap
            y += BOX + 2 * TOL + 1
        d.set_draw_color(*self.c["line"])
        d.set_line_width(0.2)
        d.line(self.M, y + 0.5, self.W - self.M, y + 0.5)
        d.set_y(y + 2.5)

    def lines(self, title="Notizen", n=None, pitch=8.0):
        """Ruled lines for writing, to the bottom of the page (or n)."""
        d = self.doc
        self.need(14)
        self.font(8, True, "mut")
        d.set_char_spacing(0.6)
        d.set_xy(self.M, d.get_y() + 2)
        d.cell(self.width, 5, self.tx(title.upper()), new_x="LMARGIN", new_y="NEXT")
        d.set_char_spacing(0)
        d.set_draw_color(*self.c["line"])
        d.set_line_width(0.25)
        y, k = d.get_y() + pitch - 1, 0
        while y <= self.bottom - 1 and (n is None or k < n):
            d.line(self.M, y, self.W - self.M, y)
            y += pitch
            k += 1
        d.set_y(y)

    def note_area(self, name, title="Anmerkung", n=4, pitch=8.0):
        """Ruled lines whose handwriting the panel reads as text (rmaufgaben: a point on the next version to tick,
        never a command). Recorded as a field of kind "notiz": no box, never judged as a tick."""
        self.need(14 + n * pitch)
        top = self.doc.get_y() + 7
        self.lines(title, n, pitch)
        self.field(name, "notiz", self.M, top, self.width, self.doc.get_y() - top)

    def lined_page(self):
        self._page()
        d = self.doc
        d.set_draw_color(*self.c["line"])
        d.set_line_width(0.25)
        y = d.get_y() + 6
        while y <= self.bottom - 1:
            d.line(self.M, y, self.W - self.M, y)
            y += 8.0

    def numbered(self, num, text, size=9.5):
        d = self.doc
        self.need(size * self.s * 0.5)
        y = d.get_y()
        self.font(size, True, "acc")
        d.set_xy(self.M, y)
        d.cell(5.5, size * self.s * 0.47, f"{num}.")
        d.set_y(y)
        self.para(text, size, indent=6.0)
        d.set_y(d.get_y() - 0.6)
        self._after_list = True

    def quote(self, text):
        d = self.doc
        y = d.get_y()
        self.para(text, 9.5, "mut", indent=4.0)
        d.set_draw_color(*self.c["acc2"])
        d.set_line_width(0.8)
        if d.page == self.page + 1 and d.get_y() > y:
            d.line(self.M + 1, y, self.M + 1, d.get_y() - 1.6)

    def rule(self):
        d = self.doc
        self.need(5)
        y = d.get_y() + 1.5
        d.set_draw_color(*self.c["line"])
        d.set_line_width(0.3)
        d.line(self.M, y, self.W - self.M, y)
        d.set_y(y + 2.5)

    def table(self, rows, size=8.5):
        """A table with its first row as head; more than TABLE_COLS columns become one line per row."""
        d = self.doc
        n = max(len(r) for r in rows)
        rows = [r + [""] * (n - len(r)) for r in rows]
        if n > TABLE_COLS or len(rows) < 2:
            head = rows[0]
            for r in rows[1:] or rows:
                self.bullet(" · ".join(f"{h}: {v}" if h and v and r is not head else v or h for h, v in zip(head, r)))
            return
        lh, pad = size * self.s * 0.47, 1.4
        w = self.width / n
        for k, r in enumerate(rows):
            self.font(size, k == 0)
            cells = [d.multi_cell(w - 2 * pad, lh, self.tx(c), dry_run=True, output="LINES") or [""] for c in r]
            h = max(len(c) for c in cells) * lh + 2 * pad
            if k and d.get_y() + h > self.bottom:
                self._page()
            y = d.get_y()
            if k == 0:
                d.set_fill_color(*self.c["tint"])
                d.rect(self.M, y, self.width, h, style="F")
            for j, c in enumerate(cells):
                d.set_xy(self.M + j * w + pad, y + pad)
                d.multi_cell(w - 2 * pad, lh, "\n".join(c))
            d.set_draw_color(*self.c["line"])
            d.set_line_width(0.2)
            d.line(self.M, y + h, self.W - self.M, y + h)
            d.set_y(y + h)
        d.set_y(d.get_y() + 2)

    def text(self, body):
        """Text as blocks (blocks(): headings, paragraphs with their lines, lists, numbers, tables, quotes)."""
        for kind, data in blocks(str(body or "")[:30000]):
            if kind == "h":
                self.section(data)
            elif kind == "p":
                self.para("\n".join(data))
            elif kind == "ul":
                for x in data:
                    self.bullet(x)
            elif kind == "ol":
                for num, x in data:
                    self.numbered(num, x)
            elif kind == "table":
                self.table(data)
            elif kind == "quote":
                self.quote("\n".join(data))
            elif kind == "hr":
                self.rule()
            elif kind == "pre":
                self.para("\n".join(data), 8.5)

    def finish(self):
        return bytes(self.doc.output()), self.fields, self.page + 1


BOLD_HEAD = re.compile(r"(?m)^[ \t]*\*\*([^*\n]{1,80})\*\*:?[ \t]*$")


def heads(body):
    """A line that is only "**Termine**" (as the structured briefing writes its parts) counts as a heading."""
    return BOLD_HEAD.sub(lambda m: "## " + m.group(1).strip(), body or "")


def _code(*parts):
    import hashlib
    return "SP-" + hashlib.sha256("\x00".join(map(str, parts)).encode()).hexdigest()[:4].upper()


def build_text(m, label, title, body, sub="", notes=True):
    """A designed sheet for any text (answer, summary, week, inbox, guide): pdf, fields, pages."""
    sh = Sheet(m, label, title, sub, _code(label, title, time.time()))
    sh.text(body)
    if notes:
        sh.lines()
    return sh.finish()


def plain_pdf(uid, label, title, body, sub=""):
    """Without „Gestaltete Blätter“ (Morgenblatt, Wochenrückblick): the same reader and layout in the device's format,
    black and white, no boxes (nothing is read back), ruled lines and a lined page for handwriting."""
    sh = Sheet(model_of(uid), label, title, sub, _code(label, title, time.time()), weg=False, plain=True)
    sh.text(body)
    sh.lines()
    sh.lined_page()
    return sh.finish()[0]


def build_morning(m, title, sub, overview, todo):
    """The Morgenblatt: the briefing, today's reminders with boxes (ticked = done), lines; a lined second page.
    todo: [{"id", "text", "at"}]."""
    sh = Sheet(m, "Morgenblatt", title, sub, _code("morgen", title, time.time()))
    if todo:
        sh.section("Heute zu erledigen")
        for x in todo[:12]:
            sh.check(x["text"], "rem:" + x["id"], "erledigt", x.get("at", ""))
        sh.para("Ankreuzen = erledigt. Kästchen ganz ausmalen = zurücknehmen.", 7.5, "mut")
    overview = heads(overview)
    sh.text(overview if re.search(r"(?m)^#{1,4}\s", overview) else "## Überblick\n" + overview)
    sh.lines()
    sh.lined_page()
    return sh.finish()


def build_calibration(m):
    """Four targets: a cross on each tells the Spark how this device places strokes on a sheet."""
    sh = Sheet(m, "Abgleich", "Abgleich für dein reMarkable", m["de"], _code("kalib", m["key"], time.time()), weg=True)
    sh.para("Mach in jeden der vier Kreise ein kleines Kreuz, genau auf die Mitte. Danach nichts weiter: Der Spark "
            "liest das Blatt beim nächsten Abgleich (meist in wenigen Minuten) und stellt sich auf dein Gerät ein. "
            "Das Ergebnis steht unter Ich → reMarkable → Papier.", 9)
    d = sh.doc
    top, bot = d.get_y() + 14, sh.bottom - 14
    inset = sh.M + 12
    for i, (x, y) in enumerate(((inset, top), (sh.W - inset, top), (inset, bot), (sh.W - inset, bot)), 1):
        d.set_draw_color(*sh.c["acc"])
        d.set_line_width(0.4)
        d.ellipse(x - 5, y - 5, 10, 10)
        d.set_draw_color(*sh.c["mut"])
        d.set_line_width(0.2)
        d.line(x - 7, y, x - 5.5, y)
        d.line(x + 5.5, y, x + 7, y)
        d.line(x, y - 7, x, y - 5.5)
        d.line(x, y + 5.5, x, y + 7)
        sh.field(f"ziel{i}", "ziel", x - 5, y - 5, 10, 10, f"Ziel {i}")
    return sh.finish()


# ---------------------------------------------------------------- reading a sheet back
def strokes(data):
    """(paper size or None, [[(x, y), …], …]) of one v6 page file: pen strokes only (no highlighter, no eraser)."""
    if not data.startswith(b"reMarkable .lines file, version=6"):
        raise ValueError("old page format (please update the reMarkable)")
    from rmscene import scene_items as si
    from rmscene import scene_stream as ss
    remarkable._quiet_rmscene()
    size, out, n = None, [], 0
    for b in ss.read_blocks(io.BytesIO(data)):
        if isinstance(b, ss.SceneInfo) and getattr(b, "paper_size", None):
            size = tuple(b.paper_size)
            continue
        v = getattr(getattr(b, "item", None), "value", None)
        if isinstance(v, si.Line) and v.points and n < MAX_POINTS:
            tool = int(getattr(v.tool, "value", v.tool))
            if tool in (5, 18, 6, 8):          # highlighters and erasers
                continue
            out.append([(float(p.x), float(p.y)) for p in v.points])
            n += len(v.points)
    return size, out


def calib_key(m, size):
    """Which calibration belongs to a page: the sheet's model, or "move@pro" when the page says it was written on another
    model (one account, two devices; Dominik 2026-10-13: the Move's calibration on a page from a Paper Pro put every
    cross 0.59 times too small and off to the side). Unknown size: the sheet's model."""
    mk = detect(size)
    return m["key"] if mk in (None, m["key"]) else f"{m['key']}@{mk}"


def _extent(raw):
    """Where the ink lies in device units (fixed numbers for the journal): x from..to, y from..to."""
    pts = [pt for ls in raw.values() for ln in ls for pt in ln]
    if not pts:
        return "none"
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return f"x {int(min(xs))}..{int(max(xs))}, y {int(min(ys))}..{int(max(ys))}"


def to_mm(lines, size, m, calib=None):
    """Device units -> mm on the sheet. The sheet fills the page's width; x counts from the page's middle, y from the
    top. With a calibration [ax, bx, ay, by] that one is used (mm = a·unit + b)."""
    if calib and len(calib) == 4:
        ax, bx, ay, by = calib
    else:
        wu = float((size or m["px"])[0]) or float(m["px"][0])
        k = m["mm"][0] / wu
        ax, bx, ay, by = k, m["mm"][0] / 2, k, 0.0
    return [[(ax * x + bx, ay * y + by) for x, y in ln] for ln in lines]


def _segments(lines):
    for ln in lines:
        if len(ln) == 1:
            yield ln[0], ln[0]
        for a, b in zip(ln, ln[1:]):
            yield a, b


def _inside(p, x, y, w, h, pad):
    return x - pad <= p[0] <= x + w + pad and y - pad <= p[1] <= y + h + pad


def judge(lines, f):
    """The state of one box from the strokes in mm: "leer", "an" (ticked), "zurück" (filled in), "unklar"."""
    x, y, w, h = f["x"], f["y"], f["w"], f["h"]
    inside = near = 0.0
    cell, r = 0.25, 0.35
    cells = set()
    for a, b in _segments(lines):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        length = math.dist(a, b) or 0.3
        if _inside(mid, x, y, w, h, TOL):
            inside += length
            steps = max(1, int(length / 0.2))
            for i in range(steps + 1):
                px, py = a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps
                if _inside((px, py), x, y, w, h, 0):
                    ci, cj = int((px - x) / cell), int((py - y) / cell)
                    reach = int(r / cell) + 1
                    for di in range(-reach, reach + 1):
                        for dj in range(-reach, reach + 1):
                            if (di * cell) ** 2 + (dj * cell) ** 2 <= r * r:
                                cells.add((ci + di, cj + dj))
        elif _inside(mid, x, y, w, h, NEAR):
            near += length
    if inside >= INK_MIN:
        total = max(1, int(w / cell) * int(h / cell))
        covered = len([c for c in cells if 0 <= c[0] < int(w / cell) and 0 <= c[1] < int(h / cell)])
        return "zurück" if covered / total >= FILLED else "an"
    if inside > 0.8 or near >= INK_MIN:
        return "unklar"
    return "leer"


def other_ink(lines, fields):
    """mm of ink farther than NEAR from every box: handwriting on the sheet itself."""
    total = 0.0
    for a, b in _segments(lines):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if not any(_inside(mid, f["x"], f["y"], f["w"], f["h"], NEAR) for f in fields):
            total += math.dist(a, b)
    return total


def evaluate(fields, pages):
    """pages: {page index: strokes in mm}. Returns ({field name: state}, mm of other ink)."""
    states, ink = {}, 0.0
    for p, lines in pages.items():
        here = [f for f in fields if f["p"] == p]
        for f in here:
            if f["k"] not in ("ziel", "notiz"):
                states[f["n"]] = judge(lines, f)
        ink += other_ink(lines, [f for f in here if f["k"] != "notiz"])   # writing in the Anmerkung is handwriting
    return states, ink


def widths(size, m):
    """Device units across the page that a page's strokes may use: its own size, the sheet's model, every model.
    (Dominik 2026-10-13: on the Move some sheets came back in units 1.7 times as large as others.)"""
    out = []
    for w in ([size[0]] if size else []) + [m["px"][0]] + [x["px"][0] for x in MODELS.values()]:
        if w and float(w) not in out:
            out.append(float(w))
    return out


def plain(m, w):
    """The mapping without a calibration for units w across the sheet's width (x from the middle, y from the top)."""
    k = m["mm"][0] / w
    return [k, m["mm"][0] / 2, k, 0.0]


def boxed(fields, pages):
    """mm of ink inside the boxes (with their margin): how well a mapping puts the ticks into the boxes. Only strokes
    lying (almost) wholly in a box count: a line of handwriting that a scale drags across boxes is no tick."""
    n = 0.0
    for p, lines in pages.items():
        here = [f for f in fields if f["p"] == p and f["k"] not in ("ziel", "notiz")]
        for ln in lines:
            inside = total = 0.0
            for a, b in _segments([ln]):
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                length = math.dist(a, b)
                total += length
                if any(_inside(mid, f["x"], f["y"], f["w"], f["h"], TOL) for f in here):
                    inside += length
            if inside and inside >= 0.8 * total:
                n += inside
    return n


def best_map(fields, raw, size, m, calib):
    """(the strokes in mm, units across or 0 for the calibration): the calibration, unless the page's ink lands clearly
    better in the boxes with another unit width; then that one (a tick never moves by chance to a box)."""
    first = to_mm_pages(raw, size, m, calib)
    best, score, used = first, boxed(fields, first), 0
    wc = m["mm"][0] / calib[0] if calib and len(calib) == 4 and calib[0] > 0 else 0
    for w in widths(size, m):
        # the calibration's own offsets kept, only its scale moved to the other unit width
        alt = [calib[0] * wc / w, calib[1], calib[2] * wc / w, calib[3]] if wc else plain(m, w)
        mm = to_mm_pages(raw, size, m, alt)
        sc = boxed(fields, mm)
        if sc >= max(2 * score, score + INK_MIN):
            best, score, used = mm, sc, int(w)
    return best, used


def to_mm_pages(raw, size, m, calib):
    return {p: to_mm(ls, size, m, calib) for p, ls in raw.items()}


def fit(fields, raw_pages, size, m):
    """A calibration from the four targets: [ax, bx, ay, by] or None when a target has no cross or it does not fit.
    Tries every unit width a page may use for the first rough look (widths)."""
    for w in widths(size, m):
        got = _fit(fields, raw_pages, plain(m, w))
        if got:
            return got
    return None


def _fit(fields, raw_pages, rough_map):
    rough = {p: to_mm(ls, None, None, rough_map) for p, ls in raw_pages.items()}
    pairs = []
    for f in fields:
        if f["k"] != "ziel":
            continue
        cx, cy = f["x"] + f["w"] / 2, f["y"] + f["h"] / 2
        us, vs = [], []
        for ln_raw, ln_mm in zip(raw_pages.get(f["p"], []), rough.get(f["p"], [])):
            for (u, v), (px, py) in zip(ln_raw, ln_mm):
                if math.dist((px, py), (cx, cy)) <= CALIB_RADIUS:
                    us.append(u)
                    vs.append(v)
        if not us:
            return None
        pairs.append(((sum(us) / len(us), sum(vs) / len(vs)), (cx, cy)))
    if len(pairs) < 4:
        return None

    def line(xs, ys):
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((a - mx) ** 2 for a in xs)
        if sxx <= 0:
            return None
        k = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sxx
        return k, my - k * mx
    fx = line([p[0][0] for p in pairs], [p[1][0] for p in pairs])
    fy = line([p[0][1] for p in pairs], [p[1][1] for p in pairs])
    if not fx or not fy or fx[0] <= 0 or fy[0] <= 0:
        return None
    worst = max(math.dist((fx[0] * u + fx[1], fy[0] * v + fy[1]), c) for (u, v), c in pairs)
    return [fx[0], fx[1], fy[0], fy[1]] if worst <= CALIB_FIT else None


SHADE = {"an": (22, 163, 74), "unklar": (194, 120, 3), "zurück": (120, 120, 120), "leer": (190, 194, 205)}


def _pic_font():
    """The sheets' own font for the control picture (arrows, umlauts), else PIL's small default."""
    from PIL import ImageFont
    import docrender
    reg, _ = docrender._font_files()
    try:
        return ImageFont.truetype(reg, 14) if reg else ImageFont.load_default()
    except OSError:
        return ImageFont.load_default()


def picture(paper, page, lines_mm):
    """The control picture of one page: the boxes (coloured by what was read) and the strokes, PNG."""
    from PIL import Image, ImageDraw
    w, h = paper["mm"]
    k = 5.0
    im = Image.new("RGB", (int(w * k), int(h * k)), (250, 250, 247))
    dr = ImageDraw.Draw(im)
    font = _pic_font()
    res = paper.get("r") or {}
    said = set()
    for f in paper.get("f", []):
        if f["p"] != page:
            continue
        st = res.get(f["n"], "leer")
        col = SHADE.get(st, SHADE["leer"])
        box = (f["x"] * k, f["y"] * k, (f["x"] + f["w"]) * k, (f["y"] + f["h"]) * k)
        dr.rectangle(box, outline=(120, 124, 136), width=2)
        if st != "leer":
            pad = TOL * k
            dr.rectangle((box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad), outline=col, width=4)
        if f.get("t") and f["k"] == "wahl":      # answers side by side: the point once above, each box its answer
            point, _, answer = f["t"].rpartition(": ")
            item = f["n"].split("|")[0]
            if point and item not in said:
                said.add(item)
                dr.text((box[0], box[1] - 6 * k), point[:48], fill=(60, 64, 76), font=font)
            dr.text((box[2] + 6, box[1]), (answer or f["t"])[:24], fill=(60, 64, 76), font=font)
        elif f.get("t") and f["k"] not in ("weg", "notiz"):
            dr.text((box[2] + 6, box[1]), f["t"][:48], fill=(60, 64, 76), font=font)
    for ln in lines_mm:
        pts = [(x * k, y * k) for x, y in ln]
        if len(pts) == 1:
            x, y = pts[0]
            dr.ellipse((x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=(29, 43, 143))
        else:
            dr.line(pts, fill=(29, 43, 143), width=3)
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------- folders and moving (cloud)
def _alone(fn):
    """One cloud job per profile at a time (the comparison in remarkable.py uses the same mark)."""
    async def run(uid, *a, **kw):
        if uid in remarkable._busy:
            return 0
        remarkable._busy.add(uid)
        try:
            return await fn(uid, *a, **kw)
        finally:
            remarkable._busy.discard(uid)
    run.inner = fn
    return run


async def set_meta(uid, items, changes):
    """New .metadata for the Spark's own documents: {doc id: {"parent": …, "pinned": …}}. Returns the root lines for
    remarkable._add_to_root(swap=…)."""
    swap = {}
    for did, ch in changes.items():
        it = items.get(did)
        if not it:
            continue
        files = remarkable.parse_index(await remarkable.blob(uid, it["h"], did + ".docSchema"))
        mf = next((f for f in files if f["id"] == did + ".metadata"), None)
        if not mf:
            continue
        meta = remarkable._json_of(await remarkable.blob(uid, mf["hash"], mf["id"], remarkable.MAX_META))
        if not meta:
            continue
        meta.update({k: v for k, v in ch.items() if k in ("parent", "pinned")})
        meta["lastModified"] = str(int(time.time() * 1000))
        nf = await remarkable._put(uid, json.dumps(meta, sort_keys=True).encode(), did + ".metadata")
        entries = sorted([nf if f["id"] == mf["id"] else f for f in files], key=lambda e: e["id"])
        swap[did] = await remarkable._index(uid, did, entries)
    return swap


async def has_ink(uid, items, did):
    it = items.get(did)
    if not it:
        return False
    files = remarkable.parse_index(await remarkable.blob(uid, it["h"], did + ".docSchema"))
    return any(f["id"].endswith(".rm") for f in files)


def _folder_ok(items, fid, parent=None):
    it = items.get(fid) if fid else None
    return bool(it and it.get("folder") and remarkable.path_of(items, fid) is not None
                and (parent is None or it.get("parent") == parent))


async def art_folder(uid, items, base, art, new):
    """The folder of one kind below base (made when missing; a new one is appended to new). Keeps its id."""
    d = remarkable.load(uid)
    known = (d.get("folders") or {}).get(art)
    if _folder_ok(items, known):
        return known
    name = ARTEN[art]
    fid = next((i for i, it in items.items() if it.get("folder") and it["name"] == name and it.get("parent") == base
                and remarkable.path_of(items, i) is not None), None)
    if not fid:
        made = next((e for e in new if e.get("folder_of") == (base, art)), None)
        if made:
            return made["id"]
        import uuid
        fid = str(uuid.uuid4())
        entry = await remarkable._new_doc(uid, fid, [(fid + ".metadata", remarkable._meta(name, base, "CollectionType"))])
        entry["folder_of"] = (base, art)
        new.append(entry)
    d = remarkable.load(uid)
    d.setdefault("folders", {})[art] = fid
    remarkable.save(uid, d)
    return fid


async def _commit(uid, new, swap):
    if new or swap:
        await remarkable._add_to_root(uid, [{k: v for k, v in e.items() if k not in ("folder_of", "spark_base")}
                                            for e in new], swap)


@_alone
async def sort_in(uid):
    """"Jetzt einsortieren": the Spark's own loose documents in the base folder go into their kind's folder.
    Only PDFs and e-books it made (recorded, or with one of its old titles); never notebooks. Returns how many."""
    items = await remarkable.refresh_library(uid)
    new = []
    base, _, _ = await remarkable.base_folder(uid, items, new)
    d = remarkable.load(uid)
    made = d.get("made") or {}
    moves = {}
    for i, it in items.items():
        if it.get("folder") or it.get("parent") != base or it.get("kind") not in ("pdf", "epub"):
            continue
        art = (made.get(i) or {}).get("art") or next((a for rx, a in OLD_NAMES if rx.search(it["name"])), "")
        if art in ARTEN and art != "archiv" and len(moves) < TIDY_MOST:
            moves[i] = art
    changes = {}
    for i, art in moves.items():
        changes[i] = {"parent": await art_folder(uid, items, base, art, new)}
        made.setdefault(i, {"art": art, "t": int(time.time()), "k": items[i].get("kind")})
    await _commit(uid, new, await set_meta(uid, items, changes))
    d = remarkable.load(uid)
    d["made"] = made
    remarkable.save(uid, d)
    print(f"remarkable: sorted in | {len(changes)} document(s)", flush=True)
    return len(changes)


@_alone
async def tidy(uid, now=None):
    """Once a day: old Morgenblatt / Wochenrückblick without handwriting -> Archiv; old Archiv without handwriting ->
    the reMarkable's trash. Returns (archived, trashed)."""
    now = now or time.time()
    d = remarkable.load(uid)
    made = d.get("made") or {}
    if not made:
        return 0, 0
    items = await remarkable.refresh_library(uid)
    new, changes, arch, gone = [], {}, 0, 0
    base, _, _ = await remarkable.base_folder(uid, items, new)
    for did, m in sorted(made.items(), key=lambda x: x[1].get("t", 0)):
        if len(changes) >= TIDY_MOST:
            break
        it = items.get(did)
        if not it or remarkable.path_of(items, did) is None:
            continue
        if m.get("arch") and now - m["arch"] >= TRASH_DAYS * 86400:
            if not await has_ink(uid, items, did):
                changes[did] = {"parent": "trash"}
                m["gone"] = int(now)
                gone += 1
        elif not m.get("arch") and m.get("art") in ("morgen", "woche") and now - m.get("t", now) >= ARCHIVE_DAYS * 86400:
            if not await has_ink(uid, items, did):
                changes[did] = {"parent": await art_folder(uid, items, base, "archiv", new)}
                m["arch"] = int(now)
                arch += 1
    await _commit(uid, new, await set_meta(uid, items, changes))
    d = remarkable.load(uid)
    d["made"] = {k: v for k, v in made.items() if not v.get("gone")}
    d["tidied"] = time.strftime("%Y-%m-%d", time.localtime(now))
    remarkable.save(uid, d)
    print(f"remarkable: tidied | {arch} to the archive, {gone} to the trash", flush=True)
    return arch, gone


# ---------------------------------------------------------------- placing a sheet
async def place(uid, art, title, built, kind, own="", pinned=False, auto=True):
    """Puts a built sheet (pdf, fields, pages) there and records its boxes. kind: what it is (morgen, text, kalib)."""
    data, fields, pages = built
    r = await remarkable.place(uid, title, data, "pdf", own=own, auto=auto, art=art,
                               pinned=pinned and features.allowed("rmordner", uid))
    m = model(model_key(uid))
    d = remarkable.load(uid)
    pp = d.get("papers") if isinstance(d.get("papers"), dict) else {}
    pp[r["id"]] = {"f": fields, "m": m["key"], "mm": list(m["mm"]), "t": int(time.time()), "k": kind,
                   "title": remarkable._clean(title, 80), "pages": pages, "h": ""}
    d["papers"] = dict(sorted(pp.items(), key=lambda x: x[1].get("t", 0))[-MAX_PAPERS:])
    remarkable.save(uid, d)
    return r


def built_text(uid, label, title, body, sub=""):
    return build_text(model_of(uid), label, title, body, sub)


# ---------------------------------------------------------------- reading the sheets back (background)
async def _read(uid, did, it, pp):
    """{page index: raw strokes}, the page size seen (or None)."""
    files = remarkable.parse_index(await remarkable.blob(uid, it["h"], did + ".docSchema"))
    byid = {f["id"]: f for f in files}
    cf = byid.get(did + ".content")
    content = remarkable._json_of(await remarkable.blob(uid, cf["hash"], cf["id"], remarkable.MAX_META)) if cf else {}
    order = remarkable.page_order(content)
    raw, size = {}, None
    for p in sorted({f["p"] for f in pp.get("f", [])} | ({0} if pp.get("k") == "kalib" else set())):
        if p >= len(order):
            continue
        f = byid.get(f"{did}/{order[p]}.rm")
        if not f:
            continue
        data = await remarkable.blob(uid, f["hash"], f["id"], remarkable.MAX_PAGE)
        s, lines = await asyncio.wait_for(asyncio.to_thread(strokes, data), 60)
        size = size or s
        raw[p] = lines
    return raw, size


@_alone
async def check(uid, now=None):
    """Reads the sheets that changed since the last look and does what their boxes say. Returns what was read
    (a number of sheets) or 0."""
    now = now or time.time()
    d = remarkable.load(uid)
    papers = d.get("papers") or {}
    if not papers:
        return 0
    import rmaufgaben
    quiet = [did for did, pp in papers.items() if rmaufgaben.pending(pp, now)]
    if quiet and rmaufgaben.on(uid):           # an Aufgabenblatt left alone long enough: its ticks count now
        for did in quiet:
            await rmaufgaben.act(uid, papers[did], now)
        d = remarkable.load(uid)
        cur = d.get("papers") or {}
        for did in quiet:
            if did in cur:
                cur[did] = papers[did]
        d["papers"] = cur
        remarkable.save(uid, d)
    rh, _ = await remarkable.root(uid)
    if rh == d.get("paper_root"):
        return len(quiet)
    items = await remarkable.refresh_library(uid)
    read, new, swap_changes, gone = 0, [], {}, []
    calib = dict(d.get("calib") or {})
    size_seen = None
    for did, pp in sorted(papers.items(), key=lambda x: -x[1].get("t", 0)):
        it = items.get(did)
        if not it or remarkable.path_of(items, did) is None:
            if not pp.get("gone"):
                gone.append(did)          # deleted or in the trash on the device: nothing more to read
            continue
        if it["h"] == pp.get("h") or read >= MAX_CHECK:
            continue
        raw, size = await _read(uid, did, it, pp)
        pp["h"] = it["h"]
        if not raw:
            continue
        read += 1
        size_seen = size or size_seen
        m = model(pp.get("m"))
        if pp.get("k") == "kalib":
            got = fit(pp["f"], raw, size, m)
            pp["r"] = {"kalib": "an" if got else "unklar"}
            pp["read"] = int(now)
            if got:
                calib[calib_key(m, size)] = got
            page = f"{int(size[0])}x{int(size[1])}" if size else "no size"
            print(f"remarkable: calibration sheet read | {'fits' if got else 'no fit'} | page {page} | ink {_extent(raw)}",
                  flush=True)
            continue
        if calib_key(m, size) != m["key"]:
            print(f"remarkable: sheet for {m['key']} written on {detect(size)}", flush=True)
        mm, units = best_map(pp["f"], raw, size, m, calib.get(calib_key(m, size)))
        states, ink = evaluate(pp["f"], mm)
        pp["r"], pp["ink"], pp["read"] = states, round(ink, 1), int(now)
        done = await _act(uid, did, it, pp, states, ink, items, new, swap_changes)
        if pp.get("k") == "aufgaben":
            pp["changed"] = int(now)
            if rmaufgaben.on(uid):
                await rmaufgaben.read_note(uid, did, pp, mm, now)
                await rmaufgaben.read_new(uid, pp, mm)
            if rmaufgaben.on(uid) and rmaufgaben.ready(pp, now):
                done += await rmaufgaben.act(uid, pp, now)
        n_on = sum(1 for v in states.values() if v == "an")
        n_q = sum(1 for v in states.values() if v == "unklar")
        page = f"{int(size[0])}x{int(size[1])}" if size else "no size"
        print(f"remarkable: sheet read | {n_on} ticked, {n_q} unclear, {done} done | {m['key']} sheet, page {page}, "
              f"calibration {'yes' if calib.get(calib_key(m, size)) else 'no'}, units {units or 'calibrated'} | "
              f"ink {_extent(raw)}", flush=True)
        _live(f"Blatt gelesen: {n_on} angekreuzt, {n_q} unklar")
    await _commit(uid, new, await set_meta(uid, items, swap_changes))
    d = remarkable.load(uid)
    cur = d.get("papers") or {}
    for did, pp in papers.items():
        if did in cur:
            cur[did] = pp
    for did in gone:
        if did in cur:
            cur[did]["gone"] = True
    d["papers"] = cur
    d["calib"] = calib
    if size_seen and detect(size_seen):
        d["paper_size"] = list(size_seen)
    d["paper_root"] = remarkable._roots.get(uid) or rh
    remarkable.save(uid, d)
    return read


async def _act(uid, did, it, pp, states, ink, items, new, changes):
    """What the boxes say, by fixed rules: "Kann weg" -> trash (Archiv when there is handwriting); a reminder's box ->
    done, filled in again -> back. Each box acts once per state (pp["a"])."""
    acted = pp.setdefault("a", {})
    undo = pp.setdefault("u", {})
    n = 0
    for f in pp.get("f", []):
        st, before = states.get(f["n"]), acted.get(f["n"])
        if st == before or st in (None, "leer", "unklar"):
            continue
        if f["k"] == "weg" and st == "an":
            if ink >= NOTES_MM:
                if features.allowed("rmordner", uid):
                    new_base, _, _ = await remarkable.base_folder(uid, items, new)
                    changes[did] = {"parent": await art_folder(uid, items, new_base, "archiv", new)}
                    pp["did"] = "archiv"
                else:
                    pp["did"] = "notizen"       # handwriting on it: it stays where it is
            else:
                changes[did] = {"parent": "trash"}
                pp["did"] = "papierkorb"
            undo["weg"] = it.get("parent") or ""
            pp["gone"] = pp["did"] != "notizen"
            n += 1
        elif f["k"] == "erledigt" and f["n"].startswith("rem:"):
            rid = f["n"][4:]
            if st == "an":
                item = next((x for x in profiles.reminders(uid) if x.get("id") == rid), None)
                if item:
                    profiles.remove_reminders(uid, {rid})
                    undo[f["n"]] = {"text": item["text"], "due": item["due"]}
                    n += 1
            elif st == "zurück" and before == "an" and isinstance(undo.get(f["n"]), dict):
                back = undo.pop(f["n"])
                profiles.add_reminder(uid, back["text"], back["due"])
                n += 1
        acted[f["n"]] = st
    return n


def _live(text):
    try:
        import live
        if live.on():
            live.event("reMarkable", text)
    except Exception:
        pass


# ---------------------------------------------------------------- what Ich → reMarkable → Papier shows
STATE_DE = {"an": "angekreuzt", "unklar": "unklar", "zurück": "zurückgenommen", "leer": "leer"}
DID_DE = {"papierkorb": "in den Papierkorb gelegt", "archiv": "ins Archiv gelegt",
          "notizen": "bleibt liegen (Handschrift darauf)"}


ONE_SHOWN = ("kalib", "aufgaben")   # kinds whose newest sheet replaces the older ones in the list
GONE_SHOWN = 86400                  # a sheet the Spark put away ("Kann weg") stays in the list one more day


def public(uid):
    d = remarkable.load(uid)
    s = profiles.settings(uid)
    key = model_key(uid, d)
    seen = detect(d.get("paper_size"))
    out, kinds = [], set()
    now = time.time()
    # newest first; within the same second the one added last (place() appends) counts as newer
    for did, pp in sorted(list((d.get("papers") or {}).items())[::-1], key=lambda x: -x[1].get("t", 0)):
        k = pp.get("k", "")
        if k in ONE_SHOWN and k in kinds:
            continue            # a newer one of this kind is there: the older ones stay out of the list (Dominik 2026-10-13)
        if pp.get("gone") and (not pp.get("did") or now - int(pp.get("read") or pp.get("t", 0)) > GONE_SHOWN):
            continue            # deleted on the device: out at once; put away by "Kann weg": one more day
        kinds.add(k)
        if len(out) >= 15:
            break
        res = pp.get("r") or {}
        boxes = [{"n": f["n"], "t": f.get("t", ""), "k": f["k"], "state": res.get(f["n"], "")}
                 for f in pp.get("f", []) if f["k"] not in ("ziel", "notiz")]
        out.append({"id": did, "title": pp.get("title", ""), "t": pp.get("t", 0), "read": pp.get("read", 0),
                    "kind": pp.get("k", ""), "pages": pp.get("pages", 1), "boxes": boxes, "did": pp.get("did", ""),
                    "gone": bool(pp.get("gone")), "ink": bool(pp.get("ink", 0) >= NOTES_MM),
                    "calib": (res.get("kalib") or "") if pp.get("k") == "kalib" else "",
                    "undo": sorted(k for k in (pp.get("u") or {}) if k.startswith("rem:") or k == "weg")})
    return {"on": {k: features.allowed(k, uid) for k in ("rmordner", "rmaufraeumen", "rmpapier", "rmaufgaben")},
            "spark": {k: features.admin_on(k) for k in ("rmordner", "rmaufraeumen", "rmpapier", "rmaufgaben")},
            "model": s.get("rm_model") or "auto", "used": key, "seen": seen or "",
            "models": [{"k": k, "de": m["de"], "en": m["en"], "mm": list(model(k)["mm"]), "color": m["color"]}
                       for k, m in MODELS.items()],
            "calibrated": sorted((d.get("calib") or {}).keys()), "folders": ARTEN, "papers": out,
            "tidied": d.get("tidied", ""), "archive_days": ARCHIVE_DAYS, "trash_days": TRASH_DAYS,
            "tasks": _tasks_public(uid)}


def _tasks_public(uid):
    import rmaufgaben
    return rmaufgaben.public(uid)


def _need(uid, key, what):
    if not features.allowed(key, uid):
        raise HTTPException(403, f"{what} ist aus ({features.admin_way(key)})")
    if not remarkable.load(uid).get("token"):
        raise HTTPException(400, "nicht verbunden")


def _cloud_error(e, what):
    why = remarkable._redact(e) if isinstance(e, remarkable.CloudError) else type(e).__name__
    print(f"remarkable: {what} failed:", why, flush=True)
    raise HTTPException(502, "reMarkable-Cloud: " + why)


CLOUD = (remarkable.CloudError, httpx.HTTPError, netguard.Blocked, netguard.TooLarge)


@router.get("/api/profile/remarkable/papier", dependencies=[Depends(assistant)])
def info(prof=Depends(browser_profile)):
    uid = prof["id"]
    if not features.allowed("remarkable", uid):
        raise HTTPException(403, "reMarkable ist aus")
    return public(uid)


@router.get("/api/profile/remarkable/papier/{did}/{page}.png", dependencies=[Depends(assistant)])
async def control_picture(did: str, page: int, request: Request, prof=Depends(browser_profile)):
    """The control picture of one page of one of the profile's own sheets (read from the cloud once more)."""
    uid = prof["id"]
    _need(uid, "rmpapier", "Gestaltete Blätter")
    guard.limit(request, "rmpic", uid)
    pp = (remarkable.load(uid).get("papers") or {}).get(did)
    if not remarkable.ID.fullmatch(did) or not pp or not 0 <= page < min(int(pp.get("pages", 1)), 50):
        raise HTTPException(404, "dieses Blatt kennt der Spark nicht")
    items = remarkable.library(uid)
    lines = []
    if did in items:
        try:
            raw, size = await _read(uid, did, items[did], {"f": [{"p": page}], "k": ""})
        except CLOUD as e:
            _cloud_error(e, "control picture")
        except (ValueError, asyncio.TimeoutError):
            raw, size = {}, None
        m = model(pp.get("m"))
        mm, _ = best_map(pp.get("f", []), {page: raw.get(page, [])}, size, m,
                         (remarkable.load(uid).get("calib") or {}).get(calib_key(m, size)))
        lines = mm[page]
    png = await asyncio.to_thread(picture, pp, page, lines)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/api/profile/remarkable/papier/abgleich", dependencies=[Depends(assistant)])
async def send_calibration(request: Request, prof=Depends(browser_profile)):
    """Puts the "Abgleich" sheet (four targets) there."""
    uid = prof["id"]
    _need(uid, "rmpapier", "Gestaltete Blätter")
    guard.limit(request, "rmsend", uid)
    try:
        r = await place(uid, "", "Abgleich für dein reMarkable", build_calibration(model(model_key(uid))), "kalib",
                        auto=False)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except CLOUD as e:
        _cloud_error(e, "calibration sheet")
    guard.log("remarkable_calibration", ip=guard.client_ip(request), profile=uid)
    return dict(public(uid), where=r["where"])


@router.post("/api/profile/remarkable/papier/einsortieren", dependencies=[Depends(assistant)])
async def sort_route(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid, "rmordner", "Ordner nach Art")
    guard.limit(request, "rmsend", uid)
    if uid in remarkable._busy:
        raise HTTPException(409, "der Abgleich läuft gerade; gleich noch einmal")
    try:
        n = await sort_in(uid)
    except CLOUD as e:
        _cloud_error(e, "sorting in")
    guard.log("remarkable_sort", ip=guard.client_ip(request), profile=uid)
    return dict(public(uid), moved=n)


@router.post("/api/profile/remarkable/papier/zurueck", dependencies=[Depends(assistant)])
async def undo_route(request: Request, prof=Depends(browser_profile)):
    """{"id": sheet, "n": "weg" | "rem:<id>"}: takes back what a box did (the document from the trash or archive to
    where it was, a reminder back)."""
    uid = prof["id"]
    _need(uid, "rmpapier", "Gestaltete Blätter")
    guard.limit(request, "rm", uid)
    body = await core.json_body(request, 1024, lenient=True)
    did, n = body.get("id"), body.get("n")
    if not isinstance(did, str) or not remarkable.ID.fullmatch(did) or not isinstance(n, str) \
            or not re.fullmatch(r"weg|rem:[0-9a-f]{8}", n):
        raise HTTPException(400, "id und n (weg oder rem:…)")
    d = remarkable.load(uid)
    pp = (d.get("papers") or {}).get(did)
    if not pp or n not in (pp.get("u") or {}):
        raise HTTPException(404, "hier gibt es nichts zurückzunehmen")
    back = pp["u"][n]
    if n == "weg":
        if uid in remarkable._busy:
            raise HTTPException(409, "der Abgleich läuft gerade; gleich noch einmal")
        remarkable._busy.add(uid)
        try:
            items = await remarkable.refresh_library(uid)
            parent = back if _folder_ok(items, back) else ""
            await _commit(uid, [], await set_meta(uid, items, {did: {"parent": parent}}))
        except CLOUD as e:
            _cloud_error(e, "taking back")
        finally:
            remarkable._busy.discard(uid)
    else:
        profiles.add_reminder(uid, back["text"], back["due"])
    d = remarkable.load(uid)
    pp = d["papers"][did]
    pp["u"].pop(n, None)
    if n == "weg":
        pp["gone"] = False
        pp["did"] = ""
    remarkable.save(uid, d)
    guard.log("remarkable_undo", ip=guard.client_ip(request), profile=uid)
    return public(uid)


@router.post("/api/profile/remarkable/papier/aufgaben", dependencies=[Depends(assistant)])
async def tasks_route(request: Request, prof=Depends(browser_profile)):
    """Puts a new version of the Aufgabenblatt there now (rmaufgaben.py)."""
    import rmaufgaben
    uid = prof["id"]
    _need(uid, "rmaufgaben", "Das Aufgabenblatt")
    guard.limit(request, "rmsend", uid)
    if uid in remarkable._busy:
        raise HTTPException(409, "der Abgleich läuft gerade; gleich noch einmal")
    try:
        r = await rmaufgaben.send(uid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except CLOUD as e:
        _cloud_error(e, "task sheet")
    guard.log("remarkable_tasks", ip=guard.client_ip(request), profile=uid)
    return dict(public(uid), where=r["where"])


@router.post("/api/profile/remarkable/papier/aufgaben/zurueck", dependencies=[Depends(assistant)])
async def tasks_undo_route(request: Request, prof=Depends(browser_profile)):
    """{"i": …}: takes back one point the Aufgabenblatt did (a reminder, a memory entry, a setting, a proposal)."""
    import rmaufgaben
    uid = prof["id"]
    _need(uid, "rmaufgaben", "Das Aufgabenblatt")
    guard.limit(request, "rm", uid)
    body = await core.json_body(request, 1024, lenient=True)
    i = body.get("i")
    if not isinstance(i, str) or not re.fullmatch(r"[0-9]{1,14}", i):
        raise HTTPException(400, "i")
    try:
        ok = await rmaufgaben.undo(uid, i)
    except HTTPException:
        raise
    except Exception as e:
        print("remarkable: taking back a task point failed:", type(e).__name__, flush=True)
        raise HTTPException(409, "ging nicht")
    if not ok:
        raise HTTPException(404, "hier gibt es nichts zurückzunehmen")
    guard.log("remarkable_task_undo", ip=guard.client_ip(request), profile=uid)
    return public(uid)
