"""Dokumente erstellen (plan plaene/dokumente-erstellen.md): the files themselves, built by fixed code.

The language model never writes a file. It fills a checked content plan (docmake.check_content: title,
sections with paragraphs, bullet points, one table, one chart, pictures of the profile's own documents,
speaker notes; for a letter the letter's parts) and this module turns that plan into Word (.docx),
PowerPoint (.pptx), Excel (.xlsx), PDF, Markdown, plain text or CSV with fixed layouts (STYLES) or a
profile's own template (docx/pptx, checked by docmake when it was uploaded).

What can never end up in a file: macros (no .docm/.pptm/.xlsm is ever written, templates with macros are
refused on upload), links to other files or the internet (no hyperlinks are written at all), formulas
other than SUMME/MITTELWERT/MIN/MAX/ANZAHL over a cell range (everything else is written as text, so a
cell "=HYPERLINK(...)" stays a word), and in CSV a cell that starts with = + - @ gets a ' in front.
Pictures come only from paths docmake resolved inside the profile's own folder.

Pure functions over the content plan: render(content, fmt, style, pictures) -> bytes. No network, no
model, no clock (the date is part of the content). Runs in a worker thread (docmake), a few seconds at most.
"""
import csv
import io
import math
import os
import re

FORMATS = ("docx", "pptx", "xlsx", "pdf", "md", "txt", "csv")
CTYPE = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "pdf": "application/pdf", "md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8",
         "csv": "text/csv; charset=utf-8"}

# the built-in looks (Vorlagen): colors as hex without #, a font every office program has or replaces well
STYLES = {
    "schlicht": {"de": "Schlicht", "en": "Plain", "accent": "2F3A4F", "accent2": "6B7A99", "bg": "FFFFFF", "fg": "1D2433",
                 "muted": "5F6B85", "font": "Calibri", "dark": False},
    "spark-hell": {"de": "Spark hell", "en": "Spark light", "accent": "5B5BF0", "accent2": "0EA5C6", "bg": "FFFFFF",
                   "fg": "141824", "muted": "5F6B85", "font": "Calibri", "dark": False},
    "spark-dunkel": {"de": "Spark dunkel", "en": "Spark dark", "accent": "8B8CFF", "accent2": "22D3EE", "bg": "0B0D14",
                     "fg": "E8EBF2", "muted": "8B95AB", "font": "Calibri", "dark": True},
    "brief": {"de": "Brief (DIN 5008)", "en": "Letter (DIN 5008)", "accent": "1D2433", "accent2": "5F6B85", "bg": "FFFFFF",
              "fg": "1D2433", "muted": "5F6B85", "font": "Arial", "dark": False},
}
# fonts for PDF and chart pictures: the first that exists (DejaVu is on Ubuntu and DGX OS); without one the PDF
# uses the built-in Helvetica and characters outside Latin-1 are replaced (LATIN1)
FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF")
LATIN1 = {"„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'", "’": "'", "–": "-", "—": "-", "…": "...", "€": "EUR",
          "•": "-", "→": "->", "←": "<-", "≈": "~", "≤": "<=", "≥": ">=", "×": "x", "\u00a0": " ", "\u202f": " "}
FORMULA = re.compile(r"=\s*(SUMME|SUM|MITTELWERT|AVERAGE|MIN|MAX|ANZAHL|COUNT)\(\s*([A-Z]{1,2}[1-9][0-9]{0,4})\s*:"
                     r"\s*([A-Z]{1,2}[1-9][0-9]{0,4})\s*\)\s*", re.I)
EN_FN = {"SUMME": "SUM", "MITTELWERT": "AVERAGE", "ANZAHL": "COUNT"}
NUMBER_DE = re.compile(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?")
NUMBER_EN = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")


def style_of(key):
    return dict(STYLES.get(key) or STYLES["spark-hell"], key=key if key in STYLES else "spark-hell")


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def number(s, lang="de"):
    """A cell that is only a number ("1.234,5", "12", "-3,2"; English "1,234.5") -> float, else None."""
    s = str(s).strip()
    rx = NUMBER_EN if lang == "en" else NUMBER_DE
    if not s or len(s) > 24 or not rx.fullmatch(s):
        return None
    if lang == "en":
        s = s.replace(",", "")
    else:
        s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def formula(s):
    """The English formula for an allowed one (=SUMME(B2:B9) -> =SUM(B2:B9)), else None."""
    m = FORMULA.fullmatch(str(s))
    if not m:
        return None
    fn = m.group(1).upper()
    return f"={EN_FN.get(fn, fn)}({m.group(2).upper()}:{m.group(3).upper()})"


def csv_cell(s):
    """A cell for CSV: one that a spreadsheet would read as a formula gets a ' in front (CSV injection)."""
    s = str(s)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") and number(s) is None else s


def _font_files():
    for d in FONT_DIRS:
        reg, bold = os.path.join(d, "DejaVuSans.ttf"), os.path.join(d, "DejaVuSans-Bold.ttf")
        if os.path.isfile(reg) and os.path.isfile(bold):
            return reg, bold
    return None, None


def _sections(c):
    return c.get("sections") or []


def _all_pictures(c, pictures):
    return [p for s in _sections(c) for p in (pictures(s) if pictures else [])]


# ---------------------------------------------------------------- chart as a picture (Word, PDF)
def chart_png(chart, style, width=1200, height=640):
    """A plain bar, line or pie chart drawn with Pillow (Word and PDF have no own charts here)."""
    from PIL import Image, ImageDraw, ImageFont
    bg, fg, mut = _rgb(style["bg"]) if style["dark"] else (255, 255, 255), _rgb(style["fg"]), _rgb(style["muted"])
    cols = [_rgb(style["accent"]), _rgb(style["accent2"]), (234, 128, 52), (22, 163, 74), (220, 38, 38), (147, 51, 234)]
    im = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(im)
    reg, bold = _font_files()
    try:
        f = ImageFont.truetype(reg, 22) if reg else ImageFont.load_default(22)
        fb = ImageFont.truetype(bold, 28) if bold else ImageFont.load_default(28)
    except (OSError, TypeError):
        f = fb = ImageFont.load_default()
    top = 20
    if chart.get("title"):
        d.text((30, top), chart["title"], fill=fg, font=fb)
        top += 50
    labels, series = chart.get("labels") or [], chart.get("series") or []
    if not labels or not series:
        return _png(im)
    lx = 30
    for i, s in enumerate(series):     # legend
        d.rectangle((lx, top + 4, lx + 18, top + 22), fill=cols[i % len(cols)])
        d.text((lx + 26, top), s.get("label") or "", fill=mut, font=f)
        lx += 40 + int(d.textlength(s.get("label") or "", font=f))
    top += 44
    if chart.get("type") == "pie":
        vals = [max(0.0, float(v)) for v in (series[0].get("values") or [])][:len(labels)]
        total = sum(vals) or 1.0
        box = (60, top, 60 + min(height - top - 20, 520), top + min(height - top - 20, 520))
        a = -90.0
        for i, v in enumerate(vals):
            sweep = 360.0 * v / total
            d.pieslice(box, a, a + sweep, fill=cols[i % len(cols)], outline=bg)
            a += sweep
        y = top
        for i, lab in enumerate(labels[:len(vals)]):
            d.rectangle((box[2] + 40, y + 4, box[2] + 58, y + 22), fill=cols[i % len(cols)])
            d.text((box[2] + 66, y), f"{lab}: {_fmt(vals[i])}", fill=fg, font=f)
            y += 34
        return _png(im)
    allv = [float(v) for s in series for v in (s.get("values") or [])] or [0.0]
    lo, hi = min(0.0, min(allv)), max(allv)
    if hi == lo:
        hi = lo + 1
    x0, x1, y0, y1 = 110, width - 30, top + 10, height - 60
    for k in range(5):     # grid with values
        y = y1 - (y1 - y0) * k / 4
        d.line((x0, y, x1, y), fill=mut if not style["dark"] else (60, 66, 84), width=1)
        d.text((10, y - 12), _fmt(lo + (hi - lo) * k / 4), fill=mut, font=f)
    n = len(labels)
    step = (x1 - x0) / max(1, n)
    def ypos(v):
        return y1 - (y1 - y0) * (float(v) - lo) / (hi - lo)
    for i, lab in enumerate(labels):
        txt = str(lab)[:14]
        d.text((x0 + step * i + step / 2 - d.textlength(txt, font=f) / 2, y1 + 10), txt, fill=mut, font=f)
    for si, s in enumerate(series):
        vals = (s.get("values") or [])[:n]
        col = cols[si % len(cols)]
        if chart.get("type") == "line":
            pts = [(x0 + step * i + step / 2, ypos(v)) for i, v in enumerate(vals)]
            if len(pts) > 1:
                d.line(pts, fill=col, width=5)
            for p in pts:
                d.ellipse((p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6), fill=col)
        else:
            bw = step * 0.7 / max(1, len(series))
            for i, v in enumerate(vals):
                bx = x0 + step * i + step * 0.15 + bw * si
                d.rectangle((bx, min(ypos(v), ypos(0)), bx + bw - 2, max(ypos(v), ypos(0))), fill=col)
    return _png(im)


def _fmt(v):
    v = float(v)
    return str(int(v)) if v == int(v) and abs(v) < 1e12 else f"{v:.2f}".rstrip("0").rstrip(".")


def _png(im):
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue()


# ---------------------------------------------------------------- Word
def docx(c, style, pictures=None, base=None):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor
    doc = Document(base) if base else Document()
    if base:     # an own template: its styles, headers and footers stay, its body text goes
        body = doc.element.body
        for el in list(body):
            if not el.tag.endswith("}sectPr"):
                body.remove(el)
    else:
        st = doc.styles["Normal"]
        st.font.name = style["font"]
        st.font.size = Pt(11)
        st.font.color.rgb = RGBColor.from_string(style["fg"] if not style["dark"] else "141824")
        for name, size in (("Title", 26), ("Heading 1", 16), ("Heading 2", 13)):
            try:
                s = doc.styles[name]
                s.font.name = style["font"]
                s.font.size = Pt(size)
                s.font.color.rgb = RGBColor.from_string(style["accent"] if not style["dark"] else "2F3A4F")
            except KeyError:
                pass
        sec = doc.sections[0]
        sec.left_margin, sec.right_margin = Cm(2.5), Cm(2.0)
    if c.get("letter"):
        _docx_letter(doc, c, Pt, Cm, WD_ALIGN_PARAGRAPH)
    else:
        doc.add_paragraph(c.get("title") or "", style="Title")
        if c.get("subtitle"):
            p = doc.add_paragraph(c["subtitle"])
            p.runs[0].italic = True
        if c.get("date") or c.get("author"):
            p = doc.add_paragraph(" · ".join(x for x in (c.get("author"), c.get("date")) if x))
            p.runs[0].font.size = Pt(9)
        for s in _sections(c):
            if s.get("heading"):
                doc.add_heading(s["heading"], level=1)
            for t in s.get("paras") or []:
                doc.add_paragraph(t)
            for t in s.get("bullets") or []:
                doc.add_paragraph(t, style="List Bullet")
            if s.get("table"):
                _docx_table(doc, s["table"])
            if s.get("chart"):
                doc.add_picture(io.BytesIO(chart_png(s["chart"], style)), width=Cm(15))
            for p in (pictures(s) if pictures else []):
                doc.add_picture(p, width=Cm(12))
            if s.get("notes"):
                p = doc.add_paragraph(s["notes"])
                p.runs[0].italic = True
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _docx_table(doc, tb):
    head, rows = tb.get("head") or [], tb.get("rows") or []
    ncol = max([len(head)] + [len(r) for r in rows] + [1])
    t = doc.add_table(rows=0, cols=ncol)
    try:
        t.style = "Light Grid Accent 1"
    except (KeyError, ValueError):
        t.style = "Table Grid"
    if head:
        cells = t.add_row().cells
        for i, h in enumerate(head):
            cells[i].text = h
            for r in cells[i].paragraphs[0].runs:
                r.bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row[:ncol]):
            cells[i].text = v
    doc.add_paragraph("")


def _docx_letter(doc, c, Pt, Cm, center):
    L = c["letter"]
    if L.get("sender"):
        p = doc.add_paragraph(" · ".join(L["sender"]))
        p.runs[0].font.size = Pt(8)
        p.runs[0].underline = True
    for line in L.get("recipient") or []:
        p = doc.add_paragraph(line)
        p.paragraph_format.space_after = Pt(0)
    doc.add_paragraph("")
    p = doc.add_paragraph(L.get("place_date") or c.get("date") or "")
    p.alignment = 2   # right
    p = doc.add_paragraph()
    r = p.add_run(L.get("subject") or c.get("title") or "")
    r.bold = True
    if L.get("greeting"):
        doc.add_paragraph(L["greeting"])
    for t in L.get("paras") or []:
        doc.add_paragraph(t)
    if L.get("closing"):
        doc.add_paragraph(L["closing"])
    doc.add_paragraph("")
    if L.get("signature"):
        doc.add_paragraph(L["signature"])


# ---------------------------------------------------------------- PowerPoint
def pptx(c, style, pictures=None, base=None):
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.util import Emu, Inches, Pt
    prs = Presentation(base) if base else Presentation()
    if base:     # an own template: its masters and layouts stay, its slides go
        lst = prs.slides._sldIdLst
        for sid in list(lst):
            prs.part.drop_rel(sid.rId)
            lst.remove(sid)
    else:
        prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    W, H = prs.slide_width, prs.slide_height
    acc, acc2, fg, bg, mut = (RGBColor.from_string(style[k]) for k in ("accent", "accent2", "fg", "bg", "muted"))

    def layout(i):
        n = len(prs.slide_layouts)
        return prs.slide_layouts[min(i, n - 1)]

    def text(slide, x, y, w, h, value, size, color, bold=False):
        tb = slide.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.text = value
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, color
                if not base:
                    r.font.name = style["font"]
        return tf

    def plain(slide):
        if base:
            return
        f = slide.background.fill
        f.solid()
        f.fore_color.rgb = bg

    # title slide
    if base:
        s = prs.slides.add_slide(layout(0))
        if s.shapes.title is not None:
            s.shapes.title.text = c.get("title") or ""
        sub = next((p for p in s.placeholders if p.placeholder_format.idx == 1), None)
        if sub is not None:
            sub.text = c.get("subtitle") or " · ".join(x for x in (c.get("author"), c.get("date")) if x)
    else:
        s = prs.slides.add_slide(layout(6))
        f = s.background.fill
        f.solid()
        f.fore_color.rgb = acc
        bar = s.shapes.add_shape(1, 0, H - Inches(0.35), W, Inches(0.35))
        bar.fill.solid()
        bar.fill.fore_color.rgb = acc2
        bar.line.fill.background()
        white = RGBColor(0xFF, 0xFF, 0xFF)
        text(s, Inches(0.9), Inches(2.4), W - Inches(1.8), Inches(1.6), c.get("title") or "", 44, white, True)
        sub = c.get("subtitle") or ""
        info = " · ".join(x for x in (c.get("author"), c.get("date")) if x)
        text(s, Inches(0.9), Inches(4.1), W - Inches(1.8), Inches(1.2), "\n".join(x for x in (sub, info) if x), 20, white)
    for n, sec in enumerate(_sections(c), 2):
        pics = pictures(sec) if pictures else []
        if base:
            s = prs.slides.add_slide(layout(1))
            if s.shapes.title is not None:
                s.shapes.title.text = sec.get("heading") or ""
            body = next((p for p in s.placeholders if p.placeholder_format.idx == 1), None)
            lines = (sec.get("paras") or []) + (sec.get("bullets") or [])
            if body is not None and lines and not (sec.get("table") or sec.get("chart")):
                body.text_frame.text = lines[0]
                for t in lines[1:]:
                    body.text_frame.add_paragraph().text = t
            elif body is not None:
                body._element.getparent().remove(body._element)
            top, left, width = Inches(1.6), Inches(0.6), W - Inches(1.2)
            if lines and (sec.get("table") or sec.get("chart")):
                text(s, left, top, width / 2 - Inches(0.2), H - top - Inches(0.6), "\n".join("• " + t for t in lines), 16, fg)
                left, width = left + width / 2, width / 2
        else:
            s = prs.slides.add_slide(layout(6))
            plain(s)
            line = s.shapes.add_shape(1, Inches(0.6), Inches(1.25), Inches(1.2), Inches(0.08))
            line.fill.solid()
            line.fill.fore_color.rgb = acc2
            line.line.fill.background()
            text(s, Inches(0.6), Inches(0.35), W - Inches(1.2), Inches(0.9), sec.get("heading") or "", 30, acc, True)
            num = text(s, W - Inches(1.1), H - Inches(0.55), Inches(0.8), Inches(0.4), str(n), 11, mut)
            num.paragraphs[0].alignment = 3
            lines = (sec.get("paras") or []) + ["• " + t for t in (sec.get("bullets") or [])]
            side = bool(sec.get("table") or sec.get("chart") or pics)
            top, left, width = Inches(1.6), Inches(0.6), W - Inches(1.2)
            if lines:
                bw = width * (0.45 if side else 1)
                tf = text(s, left, top, bw, H - top - Inches(0.8), "\n".join(lines), 20 if len(lines) <= 6 else 16, fg)
                for p in tf.paragraphs:
                    p.space_after = Pt(8)
                if side:
                    left, width = left + bw + Inches(0.3), width - bw - Inches(0.3)
        h = H - top - Inches(0.8)
        if sec.get("chart"):
            ch = sec["chart"]
            cd = CategoryChartData()
            cd.categories = ch.get("labels") or []
            for sr in (ch.get("series") or [])[:1 if ch.get("type") == "pie" else 6]:
                cd.add_series(sr.get("label") or "", [float(v) for v in sr.get("values") or []])
            kind = {"pie": XL_CHART_TYPE.PIE, "line": XL_CHART_TYPE.LINE_MARKERS}.get(ch.get("type"), XL_CHART_TYPE.COLUMN_CLUSTERED)
            gh = h if not sec.get("table") else h / 2
            gf = s.shapes.add_chart(kind, left, top, width, gh, cd)
            chart = gf.chart
            chart.has_legend = len(ch.get("series") or []) > 1 or ch.get("type") == "pie"
            if chart.has_legend:
                chart.legend.position = XL_LEGEND_POSITION.BOTTOM
                chart.legend.include_in_layout = False
            if ch.get("title"):
                chart.has_title = True
                chart.chart_title.text_frame.text = ch["title"]
            if not base:
                try:
                    chart.font.color.rgb = fg
                    chart.font.size = Pt(12)
                    if kind != XL_CHART_TYPE.PIE:
                        for i, pl in enumerate(chart.plots[0].series):
                            col = acc if i == 0 else acc2
                            if kind == XL_CHART_TYPE.COLUMN_CLUSTERED:
                                pl.format.fill.solid()
                                pl.format.fill.fore_color.rgb = col
                            else:
                                pl.format.line.color.rgb = col
                except (AttributeError, ValueError, IndexError):
                    pass
            if sec.get("table"):
                top, h = top + gh + Inches(0.2), h / 2 - Inches(0.2)
        if sec.get("table"):
            tb = sec["table"]
            head, rows = tb.get("head") or [], (tb.get("rows") or [])[:14]
            ncol = max([len(head)] + [len(r) for r in rows] + [1])
            nrow = len(rows) + (1 if head else 0)
            if nrow:
                gt = s.shapes.add_table(nrow, min(ncol, 12), left, top, width, min(h, Emu(Inches(0.42) * nrow))).table
                for r, row in enumerate(([head] if head else []) + rows):
                    for i in range(min(ncol, 12)):
                        cell = gt.cell(r, i)
                        cell.text = row[i] if i < len(row) else ""
                        for p in cell.text_frame.paragraphs:
                            for run in p.runs:
                                run.font.size = Pt(12 if nrow < 9 else 10)
        elif pics and not sec.get("chart"):
            k = len(pics)
            cols = 1 if k == 1 else 2 if k <= 4 else 3
            rows_ = math.ceil(k / cols)
            cw, chh = width / cols, h / rows_
            for i, p in enumerate(pics):
                try:
                    from PIL import Image
                    with Image.open(p) as im:
                        iw, ih = im.size
                except Exception:
                    continue
                scale = min((cw - Inches(0.15)) / iw, (chh - Inches(0.15)) / ih)
                pw, ph = int(iw * scale), int(ih * scale)
                x = left + cw * (i % cols) + (cw - pw) / 2
                y = top + chh * (i // cols) + (chh - ph) / 2
                s.shapes.add_picture(p, int(x), int(y), pw, ph)
        if sec.get("notes"):
            s.notes_slide.notes_text_frame.text = sec["notes"]
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- Excel
def xlsx(c, style, pictures=None, base=None):
    import xlsxwriter
    out = io.BytesIO()
    lang = c.get("lang") or "de"
    wb = xlsxwriter.Workbook(out, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
                                   "strings_to_numbers": False})
    wb.set_properties({"title": (c.get("title") or "")[:200], "author": (c.get("author") or "")[:80]})
    head = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#" + style["accent"], "border": 1,
                          "font_name": style["font"]})
    cellf = wb.add_format({"border": 1, "font_name": style["font"], "text_wrap": True, "valign": "top"})
    numf = wb.add_format({"border": 1, "font_name": style["font"], "num_format": "#,##0.##"})
    titlef = wb.add_format({"bold": True, "font_size": 16, "font_color": "#" + style["accent"], "font_name": style["font"]})
    textf = wb.add_format({"text_wrap": True, "valign": "top", "font_name": style["font"]})
    boldf = wb.add_format({"bold": True, "font_name": style["font"]})
    used = set()

    def sheet_name(v, i):
        v = re.sub(r"[\[\]:*?/\\']", " ", str(v or "")).strip()[:28] or f"Blatt {i}"
        base_, k = v, 2
        while v.lower() in used:
            v = f"{base_[:25]} {k}"
            k += 1
        used.add(v.lower())
        return v

    over, orow = None, 0      # the sheet for sections without a table or chart, and its next row
    for i, s in enumerate(_sections(c), 1):
        tb, ch = s.get("table"), s.get("chart")
        if not tb and not ch:
            if over is None:
                over = wb.add_worksheet(sheet_name(c.get("title") or "Übersicht", 0))
                over.set_column(0, 0, 100)
                over.write_string(0, 0, c.get("title") or "", titlef)
                orow = 2
            over.write_string(orow, 0, s.get("heading") or "", boldf)
            orow += 1
            for t in (s.get("paras") or []) + ["• " + b for b in (s.get("bullets") or [])]:
                over.write_string(orow, 0, t, textf)
                orow += 1
            orow += 1
            continue
        ws = wb.add_worksheet(sheet_name(s.get("heading"), i))
        r0 = 0
        if s.get("heading"):
            ws.write_string(0, 0, s["heading"], titlef)
            r0 = 2
        for t in (s.get("paras") or []) + ["• " + b for b in (s.get("bullets") or [])]:
            ws.write_string(r0, 0, t, textf)
            r0 += 1
        if s.get("paras") or s.get("bullets"):
            r0 += 1
        if not tb and ch:      # the chart's numbers become the table it is drawn from
            tb = {"head": [""] + [sr.get("label") or "" for sr in ch.get("series") or []],
                  "rows": [[lab] + [_fmt(sr["values"][k]) if k < len(sr.get("values") or []) else "" for sr in ch["series"]]
                           for k, lab in enumerate(ch.get("labels") or [])]}
        hd, rows = tb.get("head") or [], tb.get("rows") or []
        ncol = max([len(hd)] + [len(r) for r in rows] + [1])
        widths = [8] * ncol
        if hd:
            for k, v in enumerate(hd):
                ws.write_string(r0, k, v, head)
                widths[k] = max(widths[k], len(v) + 2)
        first = r0 + (1 if hd else 0)
        for ri, row in enumerate(rows):
            for k, v in enumerate(row[:ncol]):
                f, n = formula(v), number(v, lang)
                if f:
                    ws.write_formula(first + ri, k, f, numf)
                elif n is not None:
                    ws.write_number(first + ri, k, n, numf)
                else:
                    ws.write_string(first + ri, k, v, cellf)
                widths[k] = max(widths[k], min(50, len(v) + 2))
        for k, w in enumerate(widths):
            ws.set_column(k, k, w)
        if hd:
            ws.freeze_panes(first, 0)
            if rows:
                ws.autofilter(r0, 0, first + len(rows) - 1, ncol - 1)
        if ch and rows:
            kind = {"pie": "pie", "line": "line"}.get(ch.get("type"), "column")
            chart = wb.add_chart({"type": kind})
            nser = 1 if kind == "pie" else min(6, ncol - 1)
            cols_ = ["#" + style["accent"], "#" + style["accent2"], "#EA8034", "#16A34A", "#DC2626", "#9333EA"]
            for k in range(1, nser + 1):
                ser = {"name": [ws.name, r0, k] if hd else f"Reihe {k}",
                       "categories": [ws.name, first, 0, first + len(rows) - 1, 0],
                       "values": [ws.name, first, k, first + len(rows) - 1, k]}
                if kind != "pie":
                    ser["fill" if kind == "column" else "line"] = {"color": cols_[(k - 1) % len(cols_)]}
                chart.add_series(ser)
            if ch.get("title"):
                chart.set_title({"name": ch["title"]})
            chart.set_size({"width": 640, "height": 360})
            ws.insert_chart(r0, ncol + 1, chart)
    if not wb.worksheets():
        ws = wb.add_worksheet("Blatt 1")
        ws.write_string(0, 0, c.get("title") or "", titlef)
    wb.close()
    return out.getvalue()


# ---------------------------------------------------------------- PDF
def pdf(c, style, pictures=None, base=None):
    from fpdf import FPDF
    from fpdf.fonts import FontFace
    reg, bold = _font_files()
    fam = "DejaVu" if reg else "Helvetica"

    def tx(s):
        s = str(s or "")
        if reg:
            return s
        return "".join(LATIN1.get(ch, ch) if ord(ch) > 255 or ch in LATIN1 else ch for ch in s).encode(
            "latin-1", "replace").decode("latin-1")

    doc = FPDF(format="A4")
    doc.set_auto_page_break(True, margin=18)
    doc.set_margins(22, 18, 18)
    if reg:
        doc.add_font("DejaVu", "", reg)
        doc.add_font("DejaVu", "B", bold)
    doc.set_title(tx(c.get("title"))[:200])
    if c.get("author"):
        doc.set_author(tx(c["author"])[:80])
    doc.set_creator("Spark")
    acc, fg, mut = _rgb(style["accent"] if not style["dark"] else "2F3A4F"), _rgb("1D2433"), _rgb("5F6B85")
    doc.add_page()
    W = doc.epw

    def para(t, size=11, b=False, color=fg, gap=2.5, align="L"):
        doc.set_font(fam, "B" if b else "", size)
        doc.set_text_color(*color)
        doc.multi_cell(W, size * 0.5, tx(t), align=align, new_x="LMARGIN", new_y="NEXT")
        doc.ln(gap)

    if c.get("letter"):
        L = c["letter"]
        if L.get("sender"):
            para(" · ".join(L["sender"]), 7.5, color=mut, gap=1)
        for line in L.get("recipient") or []:
            para(line, 11, gap=0)
        doc.ln(14)
        para(L.get("place_date") or c.get("date") or "", 11, align="R", gap=6)
        para(L.get("subject") or c.get("title") or "", 11, b=True, gap=5)
        if L.get("greeting"):
            para(L["greeting"])
        for t in L.get("paras") or []:
            para(t)
        if L.get("closing"):
            para(L["closing"], gap=12)
        if L.get("signature"):
            para(L["signature"])
    else:
        para(c.get("title") or "", 22, b=True, color=acc, gap=2)
        if c.get("subtitle"):
            para(c["subtitle"], 13, color=mut, gap=1)
        if c.get("date") or c.get("author"):
            para(" · ".join(x for x in (c.get("author"), c.get("date")) if x), 9, color=mut, gap=4)
        for s in _sections(c):
            if s.get("heading"):
                doc.ln(2)
                para(s["heading"], 14, b=True, color=acc, gap=1.5)
            for t in s.get("paras") or []:
                para(t)
            for t in s.get("bullets") or []:
                doc.set_font(fam, "", 11)
                doc.set_text_color(*fg)
                doc.cell(6, 5.5, "-" if not reg else "•")
                doc.multi_cell(W - 6, 5.5, tx(t), new_x="LMARGIN", new_y="NEXT")
                doc.ln(1)
            if s.get("table"):
                tb = s["table"]
                hd, rows = tb.get("head") or [], tb.get("rows") or []
                ncol = max([len(hd)] + [len(r) for r in rows] + [1])
                doc.set_font(fam, "", 9 if ncol > 4 else 10)
                doc.set_text_color(*fg)
                with doc.table(headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=acc),
                               first_row_as_headings=bool(hd), line_height=5) as t:
                    for row in ([hd] if hd else []) + rows:
                        rr = t.row()
                        for i in range(ncol):
                            rr.cell(tx(row[i] if i < len(row) else ""))
                doc.ln(3)
            if s.get("chart"):
                doc.image(io.BytesIO(chart_png(s["chart"], dict(style, dark=False, bg="FFFFFF"))), w=min(W, 160))
                doc.ln(3)
            for p in (pictures(s) if pictures else []):
                try:
                    doc.image(p, w=min(W, 120))
                    doc.ln(3)
                except Exception:
                    continue
            if s.get("notes"):
                para(s["notes"], 9, color=mut)
    return bytes(doc.output())


# ---------------------------------------------------------------- Markdown, text, CSV
def _md_cell(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


def md(c, style=None, pictures=None, base=None, plain=False):
    out = []
    h1, h2, b = ("", "", "- ") if plain else ("# ", "## ", "- ")
    if c.get("letter"):
        L = c["letter"]
        out += [" · ".join(L.get("sender") or []), ""] if L.get("sender") else []
        out += list(L.get("recipient") or []) + ["", L.get("place_date") or c.get("date") or "", ""]
        out += [(L.get("subject") if plain else "**" + (L.get("subject") or "") + "**"), ""]
        out += ([L["greeting"], ""] if L.get("greeting") else [])
        for t in L.get("paras") or []:
            out += [t, ""]
        out += ([L["closing"], ""] if L.get("closing") else []) + ([L["signature"]] if L.get("signature") else [])
        return ("\n".join(out).strip() + "\n").encode("utf-8")
    out += [h1 + (c.get("title") or ""), ""]
    if c.get("subtitle"):
        out += [c["subtitle"] if plain else "_" + c["subtitle"] + "_", ""]
    if c.get("date") or c.get("author"):
        out += [" · ".join(x for x in (c.get("author"), c.get("date")) if x), ""]
    for s in _sections(c):
        if s.get("heading"):
            out += [h2 + s["heading"], ""]
        for t in s.get("paras") or []:
            out += [t, ""]
        if s.get("bullets"):
            out += [b + t for t in s["bullets"]] + [""]
        tb = s.get("table")
        if not tb and s.get("chart"):
            ch = s["chart"]
            tb = {"head": [""] + [sr.get("label") or "" for sr in ch.get("series") or []],
                  "rows": [[lab] + [_fmt(sr["values"][k]) if k < len(sr.get("values") or []) else "" for sr in ch["series"]]
                           for k, lab in enumerate(ch.get("labels") or [])]}
            if ch.get("title"):
                out += [ch["title"] + ":", ""]
        if tb:
            hd, rows = tb.get("head") or [], tb.get("rows") or []
            ncol = max([len(hd)] + [len(r) for r in rows] + [1])
            if plain:
                for row in ([hd] if hd else []) + rows:
                    out.append("\t".join(row))
            else:
                hd = hd or [""] * ncol
                out.append("| " + " | ".join(_md_cell(x) for x in hd + [""] * (ncol - len(hd))) + " |")
                out.append("|" + "---|" * ncol)
                for row in rows:
                    out.append("| " + " | ".join(_md_cell(x) for x in row + [""] * (ncol - len(row))) + " |")
            out.append("")
        for p in (pictures(s) if pictures else []):
            out += [("[Bild]" if plain else "*[Bild: " + os.path.basename(p) + "]*"), ""]
        if s.get("notes"):
            out += [("Notiz: " if plain else "> ") + s["notes"], ""]
    return ("\n".join(out).strip() + "\n").encode("utf-8")


def txt(c, style=None, pictures=None, base=None):
    return md(c, style, pictures, base, plain=True)


def csv_(c, style=None, pictures=None, base=None):
    """Every table one after another (an empty line between), German Excel's ; for German documents."""
    b = io.StringIO()
    w = csv.writer(b, delimiter=";" if (c.get("lang") or "de") == "de" else ",", lineterminator="\r\n")
    first = True
    for s in _sections(c):
        tb = s.get("table")
        if not tb:
            continue
        if not first:
            w.writerow([])
        first = False
        for row in ([tb["head"]] if tb.get("head") else []) + (tb.get("rows") or []):
            w.writerow([csv_cell(x) for x in row])
    if first:   # no table: the headings and bullet points as one column
        for s in _sections(c):
            for x in [s.get("heading") or ""] + (s.get("bullets") or []) + (s.get("paras") or []):
                w.writerow([csv_cell(x)])
    return ("\ufeff" + b.getvalue()).encode("utf-8")


BUILD = {"docx": docx, "pptx": pptx, "xlsx": xlsx, "pdf": pdf, "md": md, "txt": txt, "csv": csv_}


def render(c, fmt, style_key="spark-hell", pictures=None, base=None):
    """The file in this format: bytes. pictures(section) -> [paths] (already checked), base: an own template."""
    if fmt not in BUILD:
        raise ValueError("format: " + ", ".join(FORMATS))
    st = style_of(style_key)
    if fmt not in ("docx", "pptx"):
        base = None
    return BUILD[fmt](c, st, pictures, base)


def german_date(y, m, d, lang="de"):
    if lang == "en":
        import calendar
        return f"{calendar.month_name[m]} {d}, {y}"
    return f"{d}. {MONTHS[m - 1]} {y}"
