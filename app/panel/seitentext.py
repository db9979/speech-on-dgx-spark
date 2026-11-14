"""Seitentext: the readable part of an HTML page as Markdown (idea from get-md of the Nano Collective, MIT, rebuilt
in Python without a new library, Dominik 2026-11-14 „B“).

One source for every page the Spark reads as text: search result pages and pages a job reads (chat.page_text), the
web page to the reMarkable (rmplus.web_page through page_text) and HTML files and HTML mails stored as documents
(documents._html_text). Fixed rules, nothing from a model:

- the main part only: what stands in <main>, <article> or role="main" when that holds at least MAIN_MIN characters,
  else the whole body;
- no page furniture: scripts, styles, forms, menus (<nav>, role navigation/banner/contentinfo/complementary/search),
  hidden parts (hidden, aria-hidden, display:none) and parts whose class or id names cookie banners, sharing,
  newsletters, comments, ads or sidebars (JUNK); <header>, <footer> and <aside> only outside the main part;
- headings as „#“ lines, list items as „- “ or „1. “, tables as Markdown rows with the line under the head (a table
  of one column or with very long cells is a layout table: its cells become paragraphs), <pre> keeps its lines;
- links and images give their text only, never an address (nothing to follow, fewer tokens);
- the text stays data, never an instruction: the callers wrap it as outside text as before (chat.wrap_outside).

The parser reads at most READ characters of HTML and writes at most `most` characters of Markdown.
"""
import html.parser
import re

READ = 2_000_000          # characters of HTML read at most (netguard already cuts a page at 1.5 MB)
MAIN_MIN = 200            # the main part counts from this many characters of text, else the whole body
CELL_LONG = 300           # a table cell longer than this makes it a layout table
MAX_COLS = 20             # a table row keeps this many cells at most
SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "object", "embed", "canvas", "form", "button",
        "select", "textarea", "dialog", "nav", "math", "head", "title"}
OUTSIDE_MAIN = {"header", "footer", "aside"}           # page furniture, unless inside the main part
ROLES = {"navigation", "banner", "contentinfo", "complementary", "search", "dialog", "alertdialog", "menu", "menubar"}
JUNK = re.compile(r"(?:^|[\s_-])(?:cookie\w*|consent|gdpr|newsletter|share|sharing|social|breadcrumbs?|sidebar|"
                  r"related|comments?|advert\w*|ads?|promo|popup|modal|skip-?link|subscribe|paywall|teaser-?list)"
                  r"(?:$|[\s_-])", re.I)
BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "aside", "blockquote", "figure", "figcaption",
         "dl", "dt", "dd", "address", "details", "summary", "center", "hr", "body", "html"}
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "base", "col", "embed", "param", "track"}
HEAD = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _Leser(html.parser.HTMLParser):
    def __init__(self, junk=True):
        super().__init__(convert_charrefs=True)
        self.junk = junk          # hide parts by their class or id (JUNK); markdown() reads once more without
        self.stack = []           # (tag, skipped here, main here)
        self.skip = 0
        self.main = 0
        self.blocks = []          # (kind, text, in main)
        self.cur = []
        self.kind = "p"
        self.lists = []           # ["ul"] or ["ol", n] per open list
        self.pre = 0
        self.table = None         # {"rows": [[cell]], "row": [..] or None, "cell": [..] or None, "depth": n}

    # ---------------------------------------------------------------- the text of one block
    def _flush(self):
        text = "".join(self.cur)
        self.cur = []
        if self.pre:
            text = text.strip("\n")
        else:
            text = re.sub(r"\s+", " ", text).strip()
        if text:
            self.blocks.append((self.kind, text, self.main > 0))
        self.kind = "p"

    def _hidden(self, tag, a):
        if tag in SKIP:
            return True
        if tag in OUTSIDE_MAIN and not self.main:
            return True
        if "hidden" in a or (a.get("aria-hidden") or "").lower() == "true":
            return True
        if (a.get("role") or "").lower() in ROLES:
            return True
        if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", a.get("style") or "", re.I):
            return True
        names = re.sub(r"\b(?:has|with)-\S+", "", " ".join(filter(None, (a.get("class"), a.get("id")))))
        return self.junk and tag not in ("html", "body", "main", "article") and bool(JUNK.search(names))

    # ---------------------------------------------------------------- tags
    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in VOID:
            if tag == "br" and not self.skip:
                if self.table is not None:
                    self._data(" ")
                else:
                    self._flush_keep()
            elif tag == "hr" and not self.skip and not self.table:
                self._flush()
            return
        hide = not self.skip and self._hidden(tag, a)
        is_main = not self.skip and not hide and (tag in ("main", "article") or (a.get("role") or "").lower() == "main")
        self.stack.append((tag, hide, is_main))
        if hide:
            self.skip += 1
        if self.skip:
            return
        if is_main:
            self._flush()
            self.main += 1
        if self.table is not None:
            self._in_table_start(tag)
            return
        if tag == "table":
            self._flush()
            self.table = {"rows": [], "row": None, "cell": None, "depth": 0}
        elif tag in HEAD:
            self._flush()
            self.kind = "h" + str(HEAD[tag])
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists.append(["ol", 0] if tag == "ol" else ["ul"])
        elif tag == "li":
            self._flush()
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
            self.kind = "li"
        elif tag == "pre":
            self._flush()
            self.pre += 1
            self.kind = "pre"
        elif tag in BLOCK and not (self.kind.startswith("li") and not "".join(self.cur).strip()):
            self._flush()       # a paragraph inside a list item keeps the item's mark

    def _flush_keep(self):
        """<br> outside tables: a new line in a list item or heading is a space, elsewhere a new paragraph."""
        if self.pre:
            self.cur.append("\n")
        elif self.kind.startswith(("li", "h")):
            self.cur.append(" ")
        else:
            self._flush()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        # close up to the matching open tag (HTML from outside is often not well formed)
        if not any(t == tag for t, _, _ in self.stack):
            return
        while self.stack:
            t, hide, is_main = self.stack.pop()
            self._close(t, hide, is_main)
            if t == tag:
                break

    def _close(self, tag, hide, is_main):
        if hide:
            self.skip -= 1
            return
        if self.skip:
            return
        if self.table is not None:
            if self._in_table_end(tag):
                return
        if tag in HEAD or tag == "li" or tag in BLOCK:
            self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            if self.lists:
                self.lists.pop()
            if not self.lists:
                self.blocks.append(("end", "", self.main > 0))     # the next list starts apart
        elif tag == "pre":
            self._flush()
            self.pre = max(0, self.pre - 1)
        if is_main:
            self._flush()
            self.main = max(0, self.main - 1)

    def handle_data(self, data):
        if not self.skip:
            self._data(data)

    def _data(self, data):
        if self.table is not None:
            if self.table["cell"] is not None:
                self.table["cell"].append(data)
            return
        if self.kind == "li" and not self.cur:
            depth = max(0, len(self.lists) - 1)
            mark = f"{self.lists[-1][1]}." if self.lists and self.lists[-1][0] == "ol" else "-"
            self.kind = "li:" + str(depth) + ":" + mark
        self.cur.append(data)

    # ---------------------------------------------------------------- tables
    def _in_table_start(self, tag):
        t = self.table
        if tag == "table":
            t["depth"] += 1               # a table inside a cell: its text stays in the cell
        elif t["depth"]:
            if t["cell"] is not None:
                t["cell"].append(" ")
        elif tag == "tr":
            self._end_row()
            t["row"] = []
        elif tag in ("td", "th"):
            self._end_cell()
            if t["row"] is None:
                t["row"] = []
            t["cell"] = []
        elif t["cell"] is not None and (tag in BLOCK or tag in HEAD or tag in ("li", "ul", "ol")):
            t["cell"].append(" ")

    def _in_table_end(self, tag):
        t = self.table
        if tag == "table":
            if t["depth"]:
                t["depth"] -= 1
                return True
            self._end_row()
            self.table = None
            self._table_blocks(t["rows"])
            return True
        if t["depth"]:
            return True
        if tag in ("td", "th"):
            self._end_cell()
        elif tag == "tr":
            self._end_row()
        return True

    def _end_cell(self):
        t = self.table
        if t["cell"] is not None:
            if t["row"] is None:
                t["row"] = []
            t["row"].append(re.sub(r"\s+", " ", "".join(t["cell"])).strip())
            t["cell"] = None

    def _end_row(self):
        t = self.table
        self._end_cell()
        if t["row"] is not None:
            if any(t["row"]):
                t["rows"].append(t["row"][:MAX_COLS])
            t["row"] = None

    def _table_blocks(self, rows):
        if not rows:
            return
        cols = max(len(r) for r in rows)
        layout = cols < 2 or any(len(c) > CELL_LONG for r in rows for c in r)
        if layout:
            for r in rows:
                for c in r:
                    if c:
                        self.blocks.append(("p", c, self.main > 0))
            return
        lines = []
        for i, r in enumerate(rows):
            r = [c.replace("|", "/") for c in r] + [""] * (cols - len(r))
            lines.append("| " + " | ".join(r) + " |")
            if i == 0:
                lines.append("|" + "---|" * cols)
        self.blocks.append(("table", "\n".join(lines), self.main > 0))


def _line(kind, text):
    if kind.startswith("h") and kind[1:].isdigit():
        return "#" * int(kind[1:]) + " " + text
    if kind.startswith("li:"):
        _, depth, mark = kind.split(":", 2)
        return "  " * int(depth) + mark + " " + text
    if kind == "pre":
        return "```\n" + text + "\n```"
    return text


def markdown(page, most=None):
    """The readable part of an HTML page as Markdown (see the module text); "" for a page without text. When hiding
    by class or id leaves less than MAIN_MIN characters (a wrapper named „sidebar“ around everything), the page is
    read once more without that rule."""
    page = str(page or "")[:READ]
    text = _markdown(page, most, True)
    if len(text) < MAIN_MIN:
        other = _markdown(page, most, False)
        if len(other) > len(text):
            return other
    return text


def _markdown(page, most, junk):
    p = _Leser(junk)
    try:
        for i in range(0, len(page), 65_536):
            p.feed(page[i:i + 65_536])
            if most and sum(len(b[1]) for b in p.blocks) > 3 * most:
                break
        p.close()
    except Exception:   # noqa: BLE001  (broken HTML from outside: what was read so far stays)
        pass
    if p.table is not None:         # a table the page never closed
        p._end_row()
        rows, p.table = p.table["rows"], None
        p._table_blocks(rows)
    p._flush()
    blocks = p.blocks
    inner = [b for b in blocks if b[2]]
    if sum(len(b[1]) for b in inner) >= MAIN_MIN:
        blocks = inner
    out, last = [], None
    for kind, text, _ in blocks:
        if kind == "end":
            last = None
            continue
        line = _line(kind, text)
        if out and line == out[-1][1]:
            continue                       # the same line twice in a row (a title repeated by the page)
        tight = last is not None and kind.startswith("li:") and last.startswith("li:")
        out.append(("\n" if tight else "\n\n", line))
        last = kind
    text = "".join(sep + line for sep, line in out).strip()
    return text[:most] if most else text
