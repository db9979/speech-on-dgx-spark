"""Tables in PDFs, read row by row (Dominik 2026-10-23: "welche Sanjeevini-Karte bei Durchfall" got the wrong card).

pypdf reads a table cell by cell, one cell per line: "Verstopfung / SS 22 Darm / viel trinken / Durchfall /
SR 18 …". Which card belongs to which complaint is then lost, and the piece boundaries (documents.CHUNK) may
fall into the middle of a row. Here every page is looked at again with pdfium (cheap: only the drawn objects,
about a tenth of pypdf's time; the text only where a table is): the table's lines and boxes (the rules drawn in the PDF) give its rows, its vertical lines or the
gaps in the text its columns, and each cell's text is taken from its own box. Each row becomes one line
"| Durchfall | SR 18 Darmflora, SS 25 Durchfall akut | Flüssigkeit ersetzen |", which documents.pieces keeps
together and gives the table's first row as its header in every piece.

Fixed rules only, no model: what is not clearly a table (fewer than two columns or two rows, no drawn rules)
stays as pypdf read it. Nothing from the PDF decides anything; the text stays outside text (documents.py).
"""
import re
import time

MAX_PAGES = 1000         # pages per document looked at again (as many as documents.MAX_PAGES)
MAX_OBJECTS = 4000       # drawn objects per page; a page with more (a map, a chart) is no table here
MAX_EDGES = 600          # rules per page taken into account (grouping them compares pairs)
BUDGET_S = 20            # seconds per document; pages after that stay as pypdf read them (a PDF made to stall)
THIN = 2.5               # a box at most this thick (points) is a line
GAP = 4.0                # an empty strip at least this wide (points) between text separates two columns
TOL = 2.0                # rules closer than this (points) are the same rule


def _clean(s):
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(s or "").replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"[ \t]+", " ", s).strip()


def _cell(s):
    return re.sub(r"\s+", " ", _clean(s)).replace("|", "/").strip()


def _edges(boxes, size):
    """Horizontal rules [(y, x0, x1)] and vertical rules [(x, y0, y1)] from the drawn boxes: a thin box is a
    line, a bigger one (a cell's frame, a shaded row) gives its four sides. A box over most of the page (the
    page's own background or frame) is left out."""
    w, h = size
    hs, vs = [], []
    for left, bottom, right, top in boxes:
        bw, bh = right - left, top - bottom
        if bw > 0.9 * w and bh > 0.9 * h:
            continue
        if bh <= THIN and bw >= 10:
            hs.append(((bottom + top) / 2, left, right))
        elif bw <= THIN and bh >= 6:
            vs.append(((left + right) / 2, bottom, top))
        elif bw >= 10 and bh >= 6:
            hs += [(bottom, left, right), (top, left, right)]
            vs += [(left, bottom, top), (right, bottom, top)]
    return hs[:MAX_EDGES], vs[:MAX_EDGES]


def _groups(hs):
    """The horizontal rules that belong together (overlapping, or on one height and touching): one table each.
    [(left, bottom, right, top, [row borders from the top down])], only with at least two rows."""
    up = list(range(len(hs)))

    def root(i):
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i
    order = sorted(range(len(hs)), key=lambda i: hs[i][1])
    for a in range(len(order)):
        i = order[a]
        for b in range(a + 1, len(order)):
            j = order[b]
            if hs[j][1] > hs[i][2] + TOL:
                break
            overlap = min(hs[i][2], hs[j][2]) - max(hs[i][1], hs[j][1])
            short = min(hs[i][2] - hs[i][1], hs[j][2] - hs[j][1])
            if overlap >= 0.5 * short or (abs(hs[i][0] - hs[j][0]) <= TOL and overlap >= -TOL):
                up[root(i)] = root(j)
    sets = {}
    for i in range(len(hs)):
        sets.setdefault(root(i), []).append(hs[i])
    out = []
    for g in sets.values():
        ys = []
        for y in sorted((e[0] for e in g), reverse=True):
            if not ys or ys[-1] - y > TOL:
                ys.append(y)
        if len(ys) >= 3:
            out.append((min(e[1] for e in g), ys[-1], max(e[2] for e in g), ys[0], ys))
    return out


def _columns(box, vs, chars):
    """Column borders inside a table: its vertical rules that run through at least half of it, else the
    empty strips in its text."""
    left, bottom, right, top, _ = box
    height = top - bottom
    run = {}
    for x, y0, y1 in vs:
        if left + TOL < x < right - TOL and y1 > bottom and y0 < top:
            key = next((k for k in run if abs(k - x) <= TOL), x)
            run[key] = run.get(key, 0) + min(y1, top) - max(y0, bottom)
    xs = sorted(x for x, n in run.items() if n >= 0.5 * height)
    if xs:
        return xs
    spans = sorted((l, r) for l, b, r, t in chars if left <= (l + r) / 2 <= right and bottom <= (b + t) / 2 <= top and r > l)
    xs, end = [], None
    for l, r in spans:
        if end is not None and l - end >= GAP:
            xs.append((l + end) / 2)
        end = r if end is None else max(end, r)
    return xs


def _table(tp, box, xs):
    """The table's rows as "| a | b |" lines, or "" when it is no real table (fewer than two columns, two rows
    with text, or most rows with only one filled cell)."""
    left, _, right, _, ys = box
    cols = [left] + xs + [right]
    if len(cols) < 3:
        return ""
    rows = []
    for top, bottom in zip(ys, ys[1:]):
        cells = [_cell(tp.get_text_bounded(a + 0.5, bottom + 0.5, b - 0.5, top - 0.5)) for a, b in zip(cols, cols[1:])]
        if any(cells):
            rows.append(cells)
    if len(rows) < 2 or sum(1 for r in rows if sum(1 for c in r if c) >= 2) * 2 < len(rows):
        return ""
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


def _page(page, raw):
    """The page's text with each table as rows, or None when no table was found."""
    w, h = page.get_size()
    boxes = []
    for n, obj in enumerate(page.get_objects(filter=[raw.FPDF_PAGEOBJ_PATH], max_depth=2)):
        if n >= MAX_OBJECTS:
            return None
        boxes.append(obj.get_bounds() if hasattr(obj, "get_bounds") else obj.get_pos())   # pdfium 5 / 4
    hs, vs = _edges(boxes, (w, h))
    found = _groups(hs)
    if not found:
        return None
    tp = page.get_textpage()
    try:
        chars = [tp.get_charbox(i) for i in range(tp.count_chars())]
        tables = []
        for box in found:
            rows = _table(tp, box, _columns(box, vs, chars))
            if rows:
                tables.append((box, rows))
        if not tables:
            return None
        far = 1e5           # the page's own coordinates may start anywhere: the bands reach past its edges
        parts, above = [], far
        for (left, bottom, right, top, _), rows in sorted(tables, key=lambda t: -t[0][3]):
            parts.append(_clean(tp.get_text_bounded(-far, top, far, above)))
            parts.append(_clean(tp.get_text_bounded(-far, bottom, left, top)))     # text beside the table
            parts.append(rows)
            parts.append(_clean(tp.get_text_bounded(right, bottom, far, top)))
            above = bottom
        parts.append(_clean(tp.get_text_bounded(-far, -far, far, above)))
        return "\n\n".join(p for p in parts if p)
    finally:
        tp.close()


def read(data, want):
    """{page index: text with its tables as rows} for the pages in `want` (indexes from 0) that hold a table.
    Empty without pdfium or when the PDF cannot be opened; a page that fails stays as pypdf read it."""
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as raw
    except ImportError:
        return {}
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as e:
        print("documents: pdfium cannot open this PDF for tables:", type(e).__name__, flush=True)
        return {}
    out, t0 = {}, time.monotonic()
    try:
        for i in sorted(want)[:MAX_PAGES]:
            if time.monotonic() - t0 > BUDGET_S:
                print("documents: tables not read further (time limit)", flush=True)
                break
            try:
                page = pdf[i]
                try:
                    got = _page(page, raw)
                finally:
                    page.close()
                if got:
                    out[i] = got
            except Exception as e:
                print("documents: table page not read:", type(e).__name__, flush=True)
    finally:
        pdf.close()
    return out
