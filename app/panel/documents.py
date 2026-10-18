"""Documents per profile: text extraction, chunking and search (V01.0.223: one SQLite file per profile).

Everything lives in the profile's folder, so only that profile's requests can reach it:

    USERS_DIR/<user id>/wissen.db           documents, text pieces, full-text index, meaning vectors,
                                            pages still to be read by the language model
    USERS_DIR/<user id>/docs/files/<id>.*   the original file (only with "Originale aufbewahren")

Older versions kept one JSON file per document (docs/<id>.json); they are moved into the database the
first time the profile's documents are opened (also after restoring an old backup).

Search: full text (SQLite FTS5 over the same rough German/English word stems as before, ranked with
BM25) and, with "Bedeutungssuche" (docembed.py), vectors of a small embedding model; both lists are
merged by rank. Text from documents is outside text for the assistant (chat.READS_OUTSIDE): it can come
from anyone (a scanned letter, a forwarded PDF), so it is data, never an instruction.

Pictures and scans (V01.0.223, "Bilder und Scans lesen"): a photo or a PDF page without a text layer is
kept as a cleaned JPEG in the table "pages" until the language model has read it in a quiet moment
(wissen.py); its text then becomes pieces like any other.
"""
import email
import email.policy
import html
import html.parser
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import zipfile

import profiles

MAX_FILE = 100 * 1024 * 1024    # PDFs by default (scanned books are big; V01.0.242, was 20 MB for all)
MAX_PDF = 300 * 1024 * 1024     # the most the admin may allow (chat.doc_max_mb)
MAX_OTHER = 20 * 1024 * 1024    # every other kind of file
MAX_DOCS = 200
MAX_CHARS = 2_000_000          # text per document after extraction
MAX_UNPACKED = 50 * 1024 * 1024  # an Office file's text parts after unpacking, all together
MAX_PARTS = 300                # slides or sheets read from one Office file
MAX_PAGES = 1000
MAX_SCAN_PAGES = 300           # pages per document handed to the language model (100 a day, wissen.DAY_PAGES)
MAX_QUEUED = 600               # pages per profile waiting for the language model
DOCLING_WAIT_MAX = 30          # files per profile waiting for the Docling server (doclingdienst.py)
DOCLING_TYPES = (".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".jpg", ".jpeg", ".png")   # what it reads
SCAN_TEXT = 40                 # a PDF page with less text than this (and a picture) counts as scanned
CHUNK, OVERLAP = 900, 150
PICTURES = (".jpg", ".jpeg", ".png", ".webp")
TYPES = (".pdf", ".txt", ".md", ".docx", ".html", ".htm", ".csv", ".xlsx", ".pptx", ".odt", ".ods", ".odp",
         ".eml") + PICTURES
SIDE = 1600                    # longest side of a page picture for the language model (small print stays readable)
DB = "wissen.db"
CTYPE = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp"}
_lock = threading.RLock()
_vcache = {}                   # uid -> (data_version stamp, ids, matrix)

# added later; old databases get them on first open (V01.0.236 shared, V01.0.244 the profile "Steckbrief")
NEW_COLUMNS = (("shared", "INTEGER DEFAULT 0"), ("title", "TEXT DEFAULT ''"), ("art", "TEXT DEFAULT ''"),
               ("sender", "TEXT DEFAULT ''"), ("ddate", "TEXT DEFAULT ''"), ("due", "TEXT DEFAULT ''"),
               ("ref", "TEXT DEFAULT ''"), ("tags", "TEXT DEFAULT '[]'"), ("mytags", "TEXT DEFAULT ''"),
               ("brief", "TEXT DEFAULT ''"), ("changed", "INTEGER DEFAULT 0"),
               # Docling-Server (doclingdienst.py): '' not asked, wait, ok, x (failed or let go)
               ("docling", "TEXT DEFAULT ''"),
               # Stufe 2 of plan suche-schaerfen: the version of the context lines of its pieces (0 = to do)
               ("headv", "INTEGER DEFAULT 0"),
               # Wissensordner (nasquelle.py): "<folder id>:<path hash>" and the folder at the place it lies in
               ("origin", "TEXT DEFAULT ''"), ("place", "TEXT DEFAULT ''"))
# when a piece / page last changed (reMarkable: the page's own time, else the document's); 0 = the document's time
# part: the headings the piece stands under (NULL = not known yet, from before V01.0.519); head: the context line
# (title, kind, part) that the word search weighs lower (ftshead) and the meaning search reads with the piece
MORE_COLUMNS = {"chunks": (("changed", "INTEGER DEFAULT 0"), ("part", "TEXT"), ("head", "TEXT DEFAULT ''")),
                "pagetext": (("changed", "INTEGER DEFAULT 0"),)}
HEADV = 1                      # raise to build every context line again (in quiet moments, due_heads)
HEAD_WEIGHT = 0.4              # the context line counts this much against the piece's own words
TABLE = 2400                   # a table stays one piece up to this many characters
FRESH = 1 / 60 - 1 / 62      # the most a fresh piece gains in the search: about two places in the ranking
FRESH_HALF = 14 * 86400      # ... halved every two weeks
ARTS = ("Vertrag", "Rechnung", "Brief", "Anleitung", "Bescheid", "Versicherung", "Kontoauszug", "Beleg", "Befund",
        "Zeugnis", "Buch", "Artikel", "Notiz", "Foto", "Formular", "Sonstiges")
MAX_TAGS = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER, created INTEGER,
    kind TEXT DEFAULT 'text', state TEXT DEFAULT 'ready', note TEXT DEFAULT '', pages INTEGER DEFAULT 0,
    use INTEGER DEFAULT 1, file TEXT DEFAULT '', source TEXT DEFAULT 'upload', shared INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, doc TEXT NOT NULL, n INTEGER, page INTEGER,
    text TEXT NOT NULL, vec BLOB);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(terms);
CREATE VIRTUAL TABLE IF NOT EXISTS ftshead USING fts5(terms);
CREATE TABLE IF NOT EXISTS pages (doc TEXT NOT NULL, page INTEGER NOT NULL, jpeg BLOB NOT NULL,
    tries INTEGER DEFAULT 0, PRIMARY KEY (doc, page));
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS pagetext (doc TEXT NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL,
    done INTEGER DEFAULT 0, PRIMARY KEY (doc, page));
"""


def _dir(uid):
    return profiles._path(uid, "docs")


def _files(uid):
    return os.path.join(_dir(uid), "files")


def _wait_dir(uid):
    """Files waiting for the Docling server when the original is not kept (doclingdienst.py)."""
    return profiles._path(uid, "docling-wait")


def db_path(uid):
    return profiles._path(uid, DB)


def _open(uid):
    """The profile's database (created and filled from the old JSON files on first use)."""
    path = db_path(uid)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    new = not os.path.exists(path)
    if new:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(docs)")}
    for col, kind in NEW_COLUMNS:       # databases from older versions
        if col not in have:
            con.execute(f"ALTER TABLE docs ADD COLUMN {col} {kind}")
    for table, cols in MORE_COLUMNS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for col, kind in cols:
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
    _import_json(uid, con)
    return con


class _Db:
    """with _Db(uid) as con: ... (one connection per use; commits on success)."""
    def __init__(self, uid):
        self.uid = uid

    def __enter__(self):
        _lock.acquire()
        try:
            self.con = _open(self.uid)
        except BaseException:
            _lock.release()
            raise
        return self.con

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.con.commit()
            else:
                self.con.rollback()
            self.con.close()
        finally:
            _lock.release()


def _import_json(uid, con):
    d = _dir(uid)
    if not os.path.isdir(d):
        return
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(d, f)
        try:
            with open(p) as fh:
                x = json.load(fh)
            if not re.fullmatch(r"[0-9a-f]{12}", str(x.get("id", ""))) or not isinstance(x.get("chunks"), list):
                raise ValueError("not a document")
            if not con.execute("SELECT 1 FROM docs WHERE id=?", (x["id"],)).fetchone():
                con.execute("INSERT INTO docs (id, name, size, created) VALUES (?,?,?,?)",
                            (x["id"], str(x.get("name") or "document")[:120], int(x.get("size") or 0),
                             int(x.get("created") or 0)))
                for i, c in enumerate(x["chunks"]):
                    _put_chunk(con, x["id"], i, None, str(c))
            con.commit()
            os.remove(p)
        except (OSError, ValueError, TypeError, KeyError) as e:
            print("documents: old document not taken over:", type(e).__name__, flush=True)


def _put_chunk(con, doc, n, page, text, changed=0, part=None):
    cur = con.execute("INSERT INTO chunks (doc, n, page, text, changed, part) VALUES (?,?,?,?,?,?)",
                      (doc, n, page, text, int(changed or 0), part))
    con.execute("INSERT INTO fts (rowid, terms) VALUES (?,?)", (cur.lastrowid, " ".join(_terms(text))))
    con.execute("UPDATE docs SET headv=0 WHERE id=?", (doc,))


def _drop_chunks(con, doc_id):
    for t in ("fts", "ftshead"):
        con.execute(f"DELETE FROM {t} WHERE rowid IN (SELECT id FROM chunks WHERE doc=?)", (doc_id,))
    con.execute("DELETE FROM chunks WHERE doc=?", (doc_id,))


# ---------------------------------------------------------------- extraction
class _HtmlText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _html_text(s):
    p = _HtmlText()
    p.feed(s)
    return "".join(p.parts)


def _decode(data):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _zip_parts(data, want, what):
    """Texts of the zip members whose names match want (in natural order); the size after unpacking
    counts, all members together: a small file can unpack to gigabytes."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [i for i in z.infolist() if re.fullmatch(want, i.filename)]
            names.sort(key=lambda i: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", i.filename)])
            names = names[:MAX_PARTS]
            if not names or sum(i.file_size for i in names) > MAX_UNPACKED:
                raise ValueError("too big")
            out, total = [], 0
            for i in names:
                with z.open(i) as f:
                    raw = f.read(MAX_UNPACKED + 1 - total)
                total += len(raw)
                if total > MAX_UNPACKED:
                    raise ValueError("too big")
                out.append((i.filename, raw.decode("utf-8", errors="replace")))
            return out
    except Exception:
        raise ValueError(f"cannot read this {what} file (or it is too big unpacked)")


def _xml_text(xml, para, tab=None):
    xml = re.sub(para, "\n", xml)
    if tab:
        xml = re.sub(tab, "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def _num(name):
    return re.search(r"(\d+)", name.rsplit("/", 1)[1]).group(1)


def _xlsx(data):
    parts = _zip_parts(data, r"xl/sharedStrings\.xml|xl/worksheets/sheet\d+\.xml", "Excel")
    shared = []
    for name, xml in parts:
        if name.endswith("sharedStrings.xml"):
            shared = [html.unescape(re.sub(r"<[^>]+>", "", si)) for si in re.findall(r"<si>(.*?)</si>", xml, re.S)]
    out = []
    for name, xml in parts:
        if "worksheets" not in name:
            continue
        rows = []
        for row in re.findall(r"<row\b[^>]*>(.*?)</row>", xml, re.S):
            cells = []
            for attrs, inner in re.findall(r"<c\b([^>]*)>(.*?)</c>", row, re.S):
                v = re.search(r"<v>(.*?)</v>", inner, re.S)
                t = re.search(r'\bt="(\w+)"', attrs)
                if t and t.group(1) == "s" and v and v.group(1).isdigit() and int(v.group(1)) < len(shared):
                    cells.append(shared[int(v.group(1))])
                elif t and t.group(1) == "inlineStr":
                    cells.append(html.unescape(re.sub(r"<[^>]+>", "", inner)))
                elif v:
                    cells.append(html.unescape(v.group(1)))
            if any(c.strip() for c in cells):
                rows.append("\t".join(cells))
        if rows:
            out.append("Tabelle " + _num(name) + ":\n" + "\n".join(rows))
    return "\n\n".join(out)


def _pptx(data):
    out = []
    for name, xml in _zip_parts(data, r"ppt/slides/slide\d+\.xml", "PowerPoint"):
        text = "\n".join(html.unescape(t) for t in re.findall(r"<a:t>(.*?)</a:t>", xml, re.S))
        if text.strip():
            out.append("Folie " + _num(name) + ":\n" + text)
    return "\n\n".join(out)


def _odf(data):
    (_, xml), = _zip_parts(data, r"content\.xml", "OpenDocument")
    return _xml_text(xml, r"</text:(p|h)>|<table:table-row[^>]*>|<text:line-break/>", r"<text:tab/>|</table:table-cell>")


def _eml(data):
    try:
        msg = email.message_from_bytes(data, policy=email.policy.default)
        head = "\n".join(k + ": " + re.sub(r"[\r\n]+", " ", str(msg.get(k, "")))[:300]
                         for k in ("From", "To", "Date", "Subject") if msg.get(k))
        body = msg.get_body(preferencelist=("plain", "html"))
        text = body.get_content() if body else ""
        if body and body.get_content_type() == "text/html":
            text = _html_text(text)
    except Exception:
        raise ValueError("cannot read this e-mail file")
    return head + "\n\n" + str(text)


def extract(name, data):
    """Plain text of an uploaded file; raises ValueError for unsupported or unreadable files."""
    pages, scans = extract_pages(name, data)
    text = "\n\n".join(t for _, t in pages)
    if scans and not text.strip():
        raise ValueError("this PDF has no text layer (scanned pages are not supported)")
    return text


def _pdf(data, scans_wanted):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("PDF support is missing; run the update (it installs pypdf)")
    try:
        reader = PdfReader(io.BytesIO(data))
        pages, scans, size = [], [], 0
        for i, page in enumerate(reader.pages[:MAX_PAGES]):
            t = page.extract_text() or ""
            if len(t.strip()) < SCAN_TEXT:
                scans.append(i)
            if t.strip():
                pages.append((i + 1, t))
                size += len(t)
            if size > MAX_CHARS:
                break
        return pages, scans, reader if scans_wanted else None
    except Exception as e:
        raise ValueError(f"cannot read this PDF: {type(e).__name__}")


def extract_pages(name, data):
    """([(page or None, text)], [index of PDF pages without a text layer])."""
    ext = os.path.splitext(name.lower())[1]
    if ext == ".pdf":
        pages, scans, _ = _pdf(data, False)
        return pages, scans
    if ext == ".docx":
        (_, xml), = _zip_parts(data, r"word/document\.xml", "Word")
        return [(None, _xml_text(xml, r"</w:p>", r"<w:tab/>"))], []
    if ext == ".xlsx":
        return [(None, _xlsx(data))], []
    if ext == ".pptx":
        return [(None, _pptx(data))], []
    if ext in (".odt", ".ods", ".odp"):
        return [(None, _odf(data))], []
    if ext == ".eml":
        return [(None, _eml(data))], []
    if ext in (".html", ".htm"):
        return [(None, _html_text(_decode(data)))], []
    if ext in (".txt", ".md", ".csv"):
        return [(None, _decode(data))], []
    raise ValueError("supported: " + ", ".join(TYPES))


def _cut(text):
    """Pieces of about CHUNK characters, cut at paragraph or sentence ends, overlapping a little."""
    out, i = [], 0
    while i < len(text):
        end = min(len(text), i + CHUNK)
        if end < len(text):
            cut = max(text.rfind("\n\n", i + CHUNK // 2, end), text.rfind(". ", i + CHUNK // 2, end))
            if cut > 0:
                end = cut + 1
        piece = text[i:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        i = max(end - OVERLAP, i + 1)
    return out


# a heading at the start of a paragraph (Stufe 2 of plan suche-schaerfen): Markdown (Docling, .md, Word headings),
# "§ 3 Miete.", "TOP 2 …", "Artikel 4", a numbered "2.1 Kosten", or a short line of its own without a full stop
_H_MD = re.compile(r"#{1,6}\s+(\S.{0,118})")
_H_LAW = re.compile(r"((?:§|Art\.|Artikel|TOP|Kapitel|Abschnitt|Teil)\s*\d+[a-z]?\b[^.:\n]{0,60})[.:]?(\s|$)")
_H_NUM = re.compile(r"(\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+[A-ZÄÖÜ][^.!?:\n]{1,70})$")
_H_LINE = re.compile(r"[A-ZÄÖÜ0-9][^.!?;,:\n]{1,68}[^.!?;,:\s]")


def heading(block):
    """The heading a paragraph starts with, or "" (fixed rules, nothing from a model)."""
    first = block.split("\n", 1)[0].strip()
    m = _H_MD.fullmatch(first)
    if m:
        return m[1].strip(" #*")
    m = _H_LAW.match(first)
    if m:
        return m[1].strip()
    m = _H_NUM.fullmatch(first)
    if m and len(first.split()) <= 10:
        return m[1].strip()
    rest = block.strip().split("\n")[1:]
    # a short line over a paragraph (never over more short lines: an address, a list of names)
    if rest and len(rest[0]) >= 40 and _H_LINE.fullmatch(first) and len(first.split()) <= 8 and not first.isdigit():
        return first
    return ""


def _is_table(block):
    lines = [x for x in block.split("\n") if x.strip()]
    return len(lines) >= 2 and all(x.lstrip().startswith("|") for x in lines)


def pieces(text):
    """[(piece, part)]: the text cut at its headings into sections, each section cut as before (_cut), small
    sections joined with the next; a table stays one piece up to TABLE characters. part: the headings the piece
    stands under ("" when the text has none). A text without headings is cut exactly as before."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()[:MAX_CHARS]
    if not text:
        return []
    secs, cur, title, last = [], [], "", ""     # sections: (heading, [blocks]); last: the heading above
    for b in text.split("\n\n"):
        h = heading(b)
        if (h or _is_table(b)) and cur:
            secs.append((title, cur))
            cur = []
        if h:
            title = last = h
        elif not cur:
            title = last
        cur.append(b)
        if _is_table(b):
            secs.append((title, cur))
            cur = []
    if cur:
        secs.append((title, cur))
    out, buf, heads = [], [], []
    for n, (h, blocks) in enumerate(secs):
        body = "\n\n".join(blocks)
        if len(body) <= TABLE and _is_table(blocks[-1]):
            if buf:
                out += _with_parts(_cut("\n\n".join(buf)), heads)
                buf, heads = [], []
            out.append((body, _part([h])))
            continue
        buf.append(body)
        if h and h not in heads:
            heads.append(h)
        if len("\n\n".join(buf)) >= CHUNK // 2 or n == len(secs) - 1:
            out += _with_parts(_cut("\n\n".join(buf)), heads)
            buf, heads = [], []
    if buf:
        out += _with_parts(_cut("\n\n".join(buf)), heads)
    return out


def _part(heads):
    return ", ".join(heads)[:120]


def _with_parts(cut, heads):
    """Small sections joined with the next: the first piece stands under all their headings, the rest only
    under the last one."""
    return [(p, _part(heads if i == 0 else heads[-1:])) for i, p in enumerate(cut)]


def chunks(text):
    """The pieces of a text without their parts (see pieces)."""
    return [p for p, _ in pieces(text)]


def _clean_text(text):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


# ---------------------------------------------------------------- pictures for the language model
def _jpeg_of(im):
    """A PIL image as a plain JPEG (upright, RGB, at most SIDE pixels, no metadata)."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.getchannel("A"))
        im = flat
    elif im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((SIDE, SIDE))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def picture_jpeg(data):
    """A photo upload, cleaned like images.prepare (format checked, pixel limit, EXIF/GPS gone)."""
    import images
    want = images.kind(data)
    if not want:
        raise ValueError("only JPEG, PNG or WebP pictures")
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = images.MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format != want:
                raise ValueError("the picture is not what it says it is")
            if im.size[0] * im.size[1] > images.MAX_PIXELS:
                raise ValueError("the picture is too big")
            im.seek(0)
            return _jpeg_of(im)
    except (Image.DecompressionBombError, OSError, SyntaxError) as e:
        raise ValueError(f"the picture cannot be read ({type(e).__name__})")


def _scan_jpegs(data, reader, scans):
    """{page number: JPEG} of the scanned pages (at most MAX_SCAN_PAGES): each page rendered whole with
    pdfium (V01.0.238); without it, the biggest picture on the page as before (scanners that store a page
    as strips or as JBIG2 lost pages that way)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        pdfium = None
    out = {}
    if pdfium is not None:
        try:
            pdf = pdfium.PdfDocument(data)
        except Exception as e:
            print("documents: pdfium cannot open this PDF:", type(e).__name__, flush=True)
            pdf = None
        if pdf is not None:
            try:
                for i in scans[:MAX_SCAN_PAGES]:
                    try:
                        page = pdf[i]
                        w, h = page.get_size()
                        scale = min(4.0, SIDE / max(w, h, 1))      # points -> at most SIDE pixels
                        im = page.render(scale=scale).to_pil()
                        out[i + 1] = _jpeg_of(im)
                        page.close()
                    except Exception as e:
                        print("documents: scanned page not rendered:", type(e).__name__, flush=True)
            finally:
                pdf.close()
            return out
    import images
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = images.MAX_PIXELS
    for i in scans:
        if len(out) >= MAX_SCAN_PAGES:
            break
        try:
            pics = list(reader.pages[i].images)[:20]
            best = None
            for p in pics:
                im = p.image
                if im is not None and im.size[0] * im.size[1] <= images.MAX_PIXELS and \
                        (best is None or im.size[0] * im.size[1] > best.size[0] * best.size[1]):
                    best = im
            if best is not None and min(best.size) >= 200:
                out[i + 1] = _jpeg_of(best)
        except Exception as e:
            print("documents: scanned page not read:", type(e).__name__, flush=True)
    return out


# ---------------------------------------------------------------- storage
def _row(r, todo):
    return {"id": r["id"], "name": r["name"], "size": r["size"], "created": r["created"], "chunks": r["nchunks"],
            "kind": r["kind"], "state": r["state"], "note": r["note"], "pages": r["pages"], "todo": todo.get(r["id"], 0),
            "vecs": r["nvecs"], "use": bool(r["use"]), "shared": bool(r["shared"]), "file": bool(r["file"]), "source": r["source"],
            **({"place": r["place"]} if r["source"] == "nas" else {}), **card(r)}


def _tags(v):
    try:
        t = json.loads(v or "[]")
        return [x for x in t if isinstance(x, str)][:MAX_TAGS] if isinstance(t, list) else []
    except ValueError:
        return []


def card(r):
    """The document's "Steckbrief" (V01.0.244): what the language model read from its beginning, and the
    tags (the owner's own ones win over the automatic ones)."""
    mine = _tags(r["mytags"]) if r["mytags"] else None
    return {"title": r["title"], "art": r["art"], "sender": r["sender"], "date": r["ddate"], "due": r["due"],
            "ref": r["ref"], "tags": mine if mine is not None else _tags(r["tags"]), "own_tags": mine is not None,
            "brief": r["brief"]}


TAG = re.compile(r"[\w äöüßÄÖÜ&.+/-]{1,24}")


def clean_tags(tags):
    """Tags as they are stored: words, at most MAX_TAGS of at most 24 characters, no doubles."""
    out = []
    for t in tags if isinstance(tags, list) else []:
        t = re.sub(r"\s+", " ", str(t)).strip().strip("#")
        if t and TAG.fullmatch(t) and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out[:MAX_TAGS]


def _short(v, n):
    return re.sub(r"[\x00-\x1f\x7f<>\"\\„“]", "", re.sub(r"\s+", " ", str(v or ""))).strip()[:n]


def _when(v):
    """YYYY-MM-DD or YYYY-MM from the model's answer, else ""."""
    m = re.fullmatch(r"((19|20)\d\d)-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?", str(v or "").strip())
    return m[0] if m else ""


def set_card(uid, doc_id, d=None, failed=False):
    """Stores the model's "Steckbrief" (a dict, checked here) or marks it failed ("x" = not again)."""
    with _Db(uid) as con:
        if failed or not isinstance(d, dict):
            con.execute("UPDATE docs SET brief='x' WHERE id=?", (doc_id,))
            return
        art = _short(d.get("art"), 30).capitalize()
        con.execute("UPDATE docs SET title=?, art=?, sender=?, ddate=?, due=?, ref=?, tags=?, brief='ok' WHERE id=?",
                    (_short(d.get("titel"), 80), art if art in ARTS else ("Sonstiges" if art else ""),
                     _short(d.get("absender"), 60), _when(d.get("datum")), _when(d.get("frist")),
                     _short(d.get("nummer"), 40), json.dumps(clean_tags(d.get("tags"))[:6]), doc_id))
        set_heads(con, doc_id)      # the card's title and kind go into the context lines


def set_tags(uid, doc_id, tags):
    """The owner's own tags (None: back to the automatic ones)."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return False
    with _Db(uid) as con:
        return con.execute("UPDATE docs SET mytags=? WHERE id=?",
                           ("" if tags is None else json.dumps(clean_tags(tags)), doc_id)).rowcount > 0


def next_card(uid):
    """(doc id, beginning of its text) of the oldest ready document without a "Steckbrief", or None."""
    if not os.path.exists(db_path(uid)):
        return None
    with _Db(uid) as con:
        r = con.execute("SELECT id FROM docs WHERE brief='' AND state='ready' ORDER BY created, id LIMIT 1").fetchone()
        if not r:
            return None
        rows = con.execute("SELECT text FROM chunks WHERE doc=? ORDER BY COALESCE(page, 0), n LIMIT 6", (r["id"],)).fetchall()
    return r["id"], "\n".join(x["text"] for x in rows)[:3000]


def related(uid, doc_id, most=8):
    """[{"id", "name", "why"}] documents of this profile that belong together with this one: the same
    number, the same sender, or at least two tags in common."""
    with _Db(uid) as con:
        rows = con.execute("SELECT * FROM docs").fetchall()
    me = next((r for r in rows if r["id"] == doc_id), None)
    if not me:
        return []
    mc = card(me)
    mtags = {t.lower() for t in mc["tags"]}
    out = []
    for r in rows:
        if r["id"] == doc_id:
            continue
        c = card(r)
        why = "Nummer" if mc["ref"] and c["ref"].lower() == mc["ref"].lower() else \
            "Absender" if mc["sender"] and c["sender"].lower() == mc["sender"].lower() else \
            "Tags" if len(mtags & {t.lower() for t in c["tags"]}) >= 2 else ""
        if why:
            out.append({"id": r["id"], "name": r["name"], "title": c["title"], "why": why})
    return out[:most]


def match_docs(uid, tags=None, art=None, used_only=True, shared_only=False):
    """Ids of the documents with all these tags (any spelling of case) and this art."""
    want = {t.lower() for t in clean_tags(tags or [])}
    art = _short(art, 30).lower()
    if not os.path.exists(db_path(uid)):
        return set()
    with _Db(uid) as con:
        rows = con.execute("SELECT * FROM docs" + (" WHERE use=1" if used_only else "")).fetchall()
    out = set()
    for r in rows:
        if shared_only and not (r["shared"] and r["state"] == "ready"):
            continue
        c = card(r)
        if want - {t.lower() for t in c["tags"]}:
            continue
        if art and c["art"].lower() != art:
            continue
        out.add(r["id"])
    return out


def list_docs(uid, used_only=False):
    if not os.path.exists(db_path(uid)) and not os.path.isdir(_dir(uid)):
        return []
    with _Db(uid) as con:
        todo = dict(con.execute("SELECT doc, COUNT(*) FROM pages GROUP BY doc").fetchall())
        rows = con.execute("SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.doc=d.id) AS nchunks, "
                           "(SELECT COUNT(c.vec) FROM chunks c WHERE c.doc=d.id) AS nvecs FROM docs d "
                           + ("WHERE d.use=1 " if used_only else "") + "ORDER BY d.created DESC, d.id").fetchall()
    return [_row(r, todo) for r in rows]


def usage_total(uid):
    """Bytes this profile's uploads take: the database (text, vectors, pages waiting) and the originals."""
    try:
        db = os.path.getsize(db_path(uid))
    except OSError:
        db = 0
    return db + usage(uid)


def usage(uid):
    """Bytes of the kept originals of this profile."""
    d, n = _files(uid), 0
    if os.path.isdir(d):
        for f in os.listdir(d):
            try:
                n += os.path.getsize(os.path.join(d, f))
            except OSError:
                pass
    return n


def _read(name, data, text=None, pictures=False, cleaned=False, later=False):
    """(pieces [(page, text)], {page: JPEG} for the language model, kind, note) of one file.
    cleaned: a picture kept by the Spark itself (already a cleaned JPEG). later: the Docling server reads the
    file afterwards, so a PDF without any text is taken (it waits for Docling instead of being refused)."""
    ext = os.path.splitext(name.lower())[1]
    pages, todo, kind, notes = [], {}, "text", []
    if text is not None:
        pages = [(None, text[:MAX_CHARS])]
    elif ext in PICTURES:
        if not pictures:
            raise ValueError("pictures in documents are off (Funktionen → Bilder und Scans lesen)")
        todo, kind = {1: data if cleaned else picture_jpeg(data)}, "picture"
    elif ext == ".pdf":
        pages, scans, reader = _pdf(data, pictures)
        if scans and pictures:
            todo = _scan_jpegs(data, reader, scans)
            if todo:
                kind = "scan"
            if len(scans) > MAX_SCAN_PAGES:
                notes.append(f"nur die ersten {MAX_SCAN_PAGES} von {len(scans)} Seiten ohne Text werden gelesen")
            lost = min(len(scans), MAX_SCAN_PAGES) - len(todo)
            if lost > 0:
                notes.append(f"{lost} Seite{'n' if lost > 1 else ''} ohne lesbares Bild übersprungen")
        elif scans and not "".join(t for _, t in pages).strip() and not later:
            raise ValueError("this PDF has no text layer (scanned pages are read only with "
                             "Funktionen → Bilder und Scans lesen)")
        elif scans and later:
            notes.append(f"{len(scans)} Seite{'n' if len(scans) > 1 else ''} ohne Text: wartet auf Docling")
        elif scans:
            notes.append(f"{len(scans)} Seite{'n' if len(scans) > 1 else ''} ohne Text nicht gelesen "
                         "(„Bilder und Scans lesen“ ist aus)")
        if len(pages) and pages[-1][0] and sum(len(t) for _, t in pages) > MAX_CHARS:
            notes.append(f"Text nach Seite {pages[-1][0]} abgeschnitten")
    else:
        pages, _ = extract_pages(name, data)
    parts = [(p, c, part) for p, t in pages for c, part in pieces(_clean_text(t))]
    if not parts and not todo and not later:
        raise ValueError("no text found in this file")
    return parts, todo, kind, "; ".join(notes)


def add(uid, name, data, text=None, pictures=False, keep=0, source="upload", most=MAX_FILE, docling=False, limit=None):
    """Stores a document. text: already read elsewhere (the iPhone app reads PDFs and scans itself;
    data is then only its size). pictures: photos and scanned pages may wait for the language model.
    keep: bytes the original may take (0 = do not keep it). docling: the Docling server reads the file again
    later (doclingdienst.wanted); until then it is kept (the original, else in docling-wait/). Documents from a
    place (source "nas", nasquelle.py) count only against their own limit, the others against MAX_DOCS."""
    if len(data) > most:
        raise ValueError(f"file is larger than {most // 1024**2} MB")
    name = re.sub(r"[\x00-\x1f\x7f<>\"\\]", "", os.path.basename(str(name or "document")))[:120].strip() or "document"
    ext = os.path.splitext(name.lower())[1]
    if text is None and ext != ".pdf" and len(data) > MAX_OTHER:
        raise ValueError(f"file is larger than {MAX_OTHER // 1024**2} MB (only PDFs may be bigger)")
    docling = bool(docling) and text is None
    parts, todo, kind, note = _read(name, data, text, pictures, later=docling)
    doc_id = secrets.token_hex(6)
    stored = ""
    with _Db(uid) as con:
        most_docs = (limit or MAX_DOCS) if source == "nas" else MAX_DOCS
        if con.execute("SELECT COUNT(*) FROM docs WHERE " + ("source='nas'" if source == "nas" else "source<>'nas'")).fetchone()[0] >= most_docs:
            raise ValueError(f"at most {most_docs} documents per profile")
        if todo and con.execute("SELECT COUNT(*) FROM pages").fetchone()[0] + len(todo) > MAX_QUEUED:
            raise ValueError(f"at most {MAX_QUEUED} pages may wait to be read; try again later")
        if keep and text is None:
            blob = todo[1] if kind == "picture" else data
            if usage(uid) + len(blob) <= keep:
                stored = doc_id + (".jpg" if kind == "picture" else ext)
                os.makedirs(_files(uid), mode=0o700, exist_ok=True)
                with open(os.open(os.path.join(_files(uid), stored), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                    f.write(blob)
            else:
                note = (note + "; " if note else "") + "Original nicht aufbewahrt: Speicher voll"
        if docling and not stored:
            if con.execute("SELECT COUNT(*) FROM docs WHERE docling='wait'").fetchone()[0] >= DOCLING_WAIT_MAX:
                docling = False            # enough waits: this one is read by the Spark only
                if not parts and not todo:
                    raise ValueError("no text found in this file")
            else:
                os.makedirs(_wait_dir(uid), mode=0o700, exist_ok=True)
                with open(os.open(os.path.join(_wait_dir(uid), doc_id + (".jpg" if kind == "picture" else ext)),
                                  os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                    f.write(todo[1] if kind == "picture" else data)
        state = "reading" if todo or (docling and not parts) else "ready"
        con.execute("INSERT INTO docs (id, name, size, created, kind, state, note, pages, file, source, docling) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (doc_id, name, len(data), int(time.time()), kind, state, note,
                     len(todo), stored, source, "wait" if docling else ""))
        for i, (page, c, part) in enumerate(parts):
            _put_chunk(con, doc_id, i, page, c, part=part)
        for page, jpeg in todo.items():
            con.execute("INSERT INTO pages (doc, page, jpeg) VALUES (?,?,?)", (doc_id, page, jpeg))
        set_heads(con, doc_id)
    return {"id": doc_id, "name": name, "chunks": len(parts), "state": state,
            "todo": len(todo), "kind": kind, "file": bool(stored), "docling": docling}


def delete(uid, doc_id):
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return False
    if not os.path.exists(db_path(uid)) and not os.path.isdir(_dir(uid)):
        return False
    with _Db(uid) as con:
        r = con.execute("SELECT file FROM docs WHERE id=?", (doc_id,)).fetchone()
        if not r:
            return False
        _drop_chunks(con, doc_id)
        con.execute("DELETE FROM pages WHERE doc=?", (doc_id,))
        con.execute("DELETE FROM pagetext WHERE doc=?", (doc_id,))
        con.execute("DELETE FROM docs WHERE id=?", (doc_id,))
        _drop_wait(uid, doc_id)
        if r["file"]:
            try:
                os.remove(os.path.join(_files(uid), r["file"]))
            except OSError:
                pass
    return True


def set_place(uid, doc_id, origin, place):
    """Wissensordner (nasquelle.py): where a document from a place comes from (folder id and path hash, and the
    folder shown in Ich → Dokumente)."""
    with _Db(uid) as con:
        con.execute("UPDATE docs SET origin=?, place=? WHERE id=?", (str(origin)[:60], str(place)[:500], doc_id))


def count_source(uid, source):
    if not os.path.exists(db_path(uid)):
        return 0
    with _Db(uid) as con:
        return con.execute("SELECT COUNT(*) FROM docs WHERE source=?", (source,)).fetchone()[0]


def set_use(uid, doc_id, on):
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return False
    with _Db(uid) as con:
        return con.execute("UPDATE docs SET use=? WHERE id=?", (1 if on else 0, doc_id)).rowcount > 0


def set_shared(uid, doc_id, on):
    """"Für alle": the owner (or the admin) offers one document to the other profiles, or takes it back."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return False
    with _Db(uid) as con:
        return con.execute("UPDATE docs SET shared=? WHERE id=?", (1 if on else 0, doc_id)).rowcount > 0


def reread(uid, doc_id, pictures=False, docling=False):
    """Reads a document again from its kept original (V01.0.238): same id, place, "use" and "Für alle";
    pieces, meaning vectors and waiting pages are replaced. Returns like add, None without an original.
    docling: the Docling server reads it once more afterwards."""
    got = original(uid, doc_id)
    if not got:
        return None
    path, name, _ = got
    with open(path, "rb") as f:
        data = f.read(MAX_PDF + 1)
    with _Db(uid) as con:
        r = con.execute("SELECT name, kind FROM docs WHERE id=?", (doc_id,)).fetchone()
    if not r:
        return None
    docling = bool(docling) and os.path.splitext(name.lower())[1] in DOCLING_TYPES
    parts, todo, kind, note = _read(name, data, None, pictures, cleaned=r["kind"] == "picture", later=docling)
    with _Db(uid) as con:
        waiting = con.execute("SELECT COUNT(*) FROM pages WHERE doc<>?", (doc_id,)).fetchone()[0]
        if todo and waiting + len(todo) > MAX_QUEUED:
            raise ValueError(f"at most {MAX_QUEUED} pages may wait to be read; try again later")
        _drop_chunks(con, doc_id)
        con.execute("DELETE FROM pages WHERE doc=?", (doc_id,))
        state = "reading" if todo or (docling and not parts) else "ready"
        con.execute("UPDATE docs SET kind=?, state=?, note=?, pages=?, docling=? WHERE id=?",
                    (kind, state, note, len(todo), "wait" if docling else "", doc_id))
        for i, (page, c, part) in enumerate(parts):
            _put_chunk(con, doc_id, i, page, c, part=part)
        for page, jpeg in todo.items():
            con.execute("INSERT INTO pages (doc, page, jpeg) VALUES (?,?,?)", (doc_id, page, jpeg))
        set_heads(con, doc_id)
    return {"id": doc_id, "name": r["name"], "chunks": len(parts), "state": state,
            "todo": len(todo), "kind": kind, "file": True, "docling": bool(docling)}


def list_shared(uid):
    """[{"id", "name", "file", "kind", "pages"}] this profile offers to everyone (ready and in use)."""
    if not os.path.exists(db_path(uid)):
        return []
    with _Db(uid) as con:
        rows = con.execute("SELECT * FROM docs WHERE shared=1 AND use=1 AND state='ready' "
                           "ORDER BY created DESC, id").fetchall()
    return [{"id": r["id"], "name": r["name"], "file": bool(r["file"]), "kind": r["kind"], "pages": r["pages"], **card(r)}
            for r in rows]


def is_shared(uid, doc_id):
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id) or not os.path.exists(db_path(uid)):
        return False
    with _Db(uid) as con:
        return bool(con.execute("SELECT 1 FROM docs WHERE id=? AND shared=1 AND use=1 AND state='ready'",
                                (doc_id,)).fetchone())


def _from_storage(uid, file, path):
    """Eigener Speicher, "Originale auslagern": a missing original is fetched back (speicher.bring_back checks it);
    one that is here is marked as used, so it is not moved out."""
    try:
        import speicher
        rel = "docs/files/" + file
        if os.path.lexists(path):
            speicher.opened(uid, rel)
        else:
            speicher.bring_back(uid, rel)
    except Exception:
        pass


def away(uid, doc_id):
    """The original lives only on the profile's own storage (and could not be fetched just now)."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return False
    with _Db(uid) as con:
        r = con.execute("SELECT file FROM docs WHERE id=?", (doc_id,)).fetchone()
    if not r or not r["file"]:
        return False
    try:
        import speicher
        return bool(speicher.offloaded(uid, "docs/files/" + r["file"]))
    except Exception:
        return False


def original(uid, doc_id):
    """(path, download name, content type) of the kept original, or None."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return None
    with _Db(uid) as con:
        r = con.execute("SELECT name, file FROM docs WHERE id=?", (doc_id,)).fetchone()
    if not r or not r["file"] or not re.fullmatch(r"[0-9a-f]{12}\.[a-z]{2,4}", r["file"]):
        return None
    path = os.path.join(_files(uid), r["file"])
    _from_storage(uid, r["file"], path)
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    ext = os.path.splitext(r["file"])[1]
    name = r["name"] if r["name"].lower().endswith(ext) else os.path.splitext(r["name"])[0] + ext
    return path, name, CTYPE.get(ext, "application/octet-stream")


def text_of(uid, doc_id, most=200_000, start=0):
    """{"name", "kind", "parts": [{"page", "text"}]} of a document for reading it again (pieces without
    their overlap is not worth the effort: they are shown one after another), or None."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return None
    with _Db(uid) as con:
        d = con.execute("SELECT name, kind, state, file FROM docs WHERE id=?", (doc_id,)).fetchone()
        if not d:
            return None
        rows = con.execute("SELECT page, text FROM chunks WHERE doc=? ORDER BY COALESCE(page, 0), n LIMIT -1 OFFSET ?",
                           (doc_id, max(0, int(start)))).fetchall()
    parts, size = [], 0
    for r in rows:
        if size > most:
            break
        parts.append({"page": r["page"], "text": r["text"]})
        size += len(r["text"])
    more = len(parts) < len(rows)
    # the view shows a part at a time ("Weiterlesen", V01.0.243); search always uses the whole text
    return {"name": d["name"], "kind": d["kind"], "state": d["state"], "file": bool(d["file"]), "parts": parts,
            "cut": more, "next": max(0, int(start)) + len(parts) if more else None}


# ---------------------------------------------------------------- notebooks from elsewhere (remarkable.py)
def notebook_texts(uid, doc_id):
    """{page: text} of the pages of a notebook that are completely read (typed text, highlights and
    what the language model read), to keep them when the notebook changes elsewhere."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id or "") or not os.path.exists(db_path(uid)):
        return {}
    with _Db(uid) as con:
        return {r[0]: r[1] for r in con.execute("SELECT page, text FROM pagetext WHERE doc=? AND done=1", (doc_id,))}


def has_doc(uid, doc_id):
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id or "") or not os.path.exists(db_path(uid)):
        return False
    with _Db(uid) as con:
        return bool(con.execute("SELECT 1 FROM docs WHERE id=?", (doc_id,)).fetchone())


def notebook_put(uid, doc_id, name, pages, note="", source="remarkable", changed=0):
    """Stores a notebook kept elsewhere, replacing what was stored for it before: pages is a list of
    (page number, text, JPEG or None[, when the page last changed]); a JPEG waits for the language model, its
    text comes on top of the page's own text. changed: when the notebook last changed (0 = now). doc_id None: a new document. Returns (doc id, pages that could not wait, as the
    queue was full; they are left out and tried again with the next comparison)."""
    name = re.sub(r"[\x00-\x1f\x7f<>\"\\]", "", str(name or "Notizbuch"))[:120].strip() or "Notizbuch"
    with _Db(uid) as con:
        if doc_id and not con.execute("SELECT 1 FROM docs WHERE id=?", (doc_id,)).fetchone():
            doc_id = None
        if not doc_id:
            if con.execute("SELECT COUNT(*) FROM docs WHERE source<>'nas'").fetchone()[0] >= MAX_DOCS:
                raise ValueError(f"at most {MAX_DOCS} documents per profile")
            doc_id = secrets.token_hex(6)
            con.execute("INSERT INTO docs (id, name, size, created, kind, state, note, pages, source) "
                        "VALUES (?,?,?,?,?,?,?,?,?)", (doc_id, name, 0, int(time.time()), "notebook", "ready", "", 0, source))
        _drop_chunks(con, doc_id)
        con.execute("DELETE FROM pages WHERE doc=?", (doc_id,))
        con.execute("DELETE FROM pagetext WHERE doc=?", (doc_id,))
        room = MAX_QUEUED - con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        n, size, waiting, left = 0, 0, 0, 0
        changed = int(changed or time.time())
        for row in pages:
            page, text, jpeg = row[:3]
            when = int(row[3]) if len(row) > 3 and row[3] else changed
            text = str(text or "")[:MAX_CHARS]
            if jpeg and room <= 0:
                left += 1
                continue
            con.execute("INSERT INTO pagetext (doc, page, text, done, changed) VALUES (?,?,?,?,?)",
                        (doc_id, page, text, 0 if jpeg else 1, when))
            for c, part in pieces(_clean_text(text)):
                _put_chunk(con, doc_id, n, page, c, when, part)
                n += 1
            size += len(text.encode())
            if jpeg:
                con.execute("INSERT INTO pages (doc, page, jpeg) VALUES (?,?,?)", (doc_id, page, jpeg))
                room -= 1
                waiting += 1
                size += len(jpeg)
        state = "reading" if waiting else "ready"
        if left:
            note = (note + "; " if note else "") + f"{left} Seite{'n' if left > 1 else ''} warten auf Platz"
        con.execute("UPDATE docs SET name=?, size=?, kind='notebook', state=?, note=?, pages=?, changed=? WHERE id=?",
                    (name, size, state, note[:300], waiting, changed, doc_id))
        set_heads(con, doc_id)
    return doc_id, left


# ---------------------------------------------------------------- the Docling server (doclingdienst.py)
def _wait_files(uid, doc_id):
    d = _wait_dir(uid)
    try:
        return [os.path.join(d, f) for f in os.listdir(d) if f.split(".")[0] == doc_id]
    except OSError:
        return []


def _drop_wait(uid, doc_id):
    for p in _wait_files(uid, doc_id):
        try:
            os.remove(p)
        except OSError:
            pass


def _settle(con, doc_id):
    """After Docling: ready when no page waits for the language model (error without any text)."""
    if con.execute("SELECT 1 FROM pages WHERE doc=?", (doc_id,)).fetchone():
        con.execute("UPDATE docs SET state='reading' WHERE id=?", (doc_id,))
    else:
        has = con.execute("SELECT 1 FROM chunks WHERE doc=?", (doc_id,)).fetchone()
        con.execute("UPDATE docs SET state=? WHERE id=?", ("ready" if has else "error", doc_id))


def _add_note(con, doc_id, text):
    con.execute("UPDATE docs SET note=CASE WHEN note='' THEN ? ELSE note || '; ' || ? END WHERE id=?", (text, text, doc_id))


def docling_waiting(uid):
    """Documents of this profile waiting for the Docling server (0 without a database; never creates one)."""
    if not os.path.exists(db_path(uid)):
        return 0
    with _Db(uid) as con:
        return con.execute("SELECT COUNT(*) FROM docs WHERE docling='wait'").fetchone()[0]


def docling_next(uid, older_than):
    """(doc id, neutral file name, path of the file) of the oldest document waiting for Docling, or None. Documents waiting since
    before older_than (unix time) are let go first: their file goes, their pages wait for the language model."""
    if not os.path.exists(db_path(uid)):
        return None
    while True:
        with _Db(uid) as con:
            for r in con.execute("SELECT id FROM docs WHERE docling='wait' AND created<?", (int(older_than),)).fetchall():
                con.execute("UPDATE docs SET docling='x' WHERE id=?", (r["id"],))
                _add_note(con, r["id"], "Docling: zu lange gewartet")
                _drop_wait(uid, r["id"])
                _settle(con, r["id"])
            r = con.execute("SELECT id FROM docs WHERE docling='wait' ORDER BY created, id LIMIT 1").fetchone()
        if not r:
            return None
        files = _wait_files(uid, r["id"])
        got = files[0] if files else (original(uid, r["id"]) or [None])[0]
        if got:   # the kind of the file as stored (a picture is kept as a cleaned JPEG)
            return r["id"], "dokument" + os.path.splitext(got)[1], got
        docling_done(uid, r["id"], None, "failed")     # nothing left to send: the Spark's own text stays


def docling_done(uid, doc_id, pages, why="", text_min=SCAN_TEXT):
    """Docling's text of a document ([(page or None, text)]) replaces the Spark's own: pieces, meaning vectors and
    the "Steckbrief" are made again; pages the language model would read go where Docling found text. pages None:
    not read (why), the Spark's own text stays. Returns the pages Docling gave."""
    with _Db(uid) as con:
        if not con.execute("SELECT 1 FROM docs WHERE id=? AND docling='wait'", (doc_id,)).fetchone():
            _drop_wait(uid, doc_id)
            return 0                               # deleted or let go meanwhile
        _drop_wait(uid, doc_id)
        if pages is None:
            con.execute("UPDATE docs SET docling='x' WHERE id=?", (doc_id,))
            _add_note(con, doc_id, "Docling: nicht lesbar")
            _settle(con, doc_id)
            return 0
        parts = [(page, c, part) for page, t in pages for c, part in pieces(_clean_text(t))]
        if parts:
            _drop_chunks(con, doc_id)
            for i, (page, c, part) in enumerate(parts):
                _put_chunk(con, doc_id, i, page, c, part=part)
            set_heads(con, doc_id)
        found = {p for p, t in pages if p is not None and len(t.strip()) >= text_min}
        waiting = [r[0] for r in con.execute("SELECT page FROM pages WHERE doc=?", (doc_id,)).fetchall()]
        if any(p is None for p, _ in pages):       # no page breaks: enough text for every waiting page, or none goes
            total = sum(len(t.strip()) for _, t in pages)
            found = set(waiting) if total >= text_min * max(1, len(waiting)) else set()
        for page in waiting:
            if page in found:
                con.execute("DELETE FROM pages WHERE doc=? AND page=?", (doc_id, page))
        # the language model's notes about pages without text are told by Docling's reading now
        con.execute("UPDATE docs SET docling=?, note=?, brief=CASE WHEN ? THEN '' ELSE brief END WHERE id=?",
                    ("ok" if parts else "x", "mit Docling gelesen" if parts else "Docling: kein Text", 1 if parts else 0,
                     doc_id))
        _settle(con, doc_id)
    return len(pages)


def docling_release(uid):
    """Docling switched off (or not for this profile): waiting documents keep the Spark's own text, their files go
    and their pages wait for the language model again."""
    if not os.path.exists(db_path(uid)):
        return 0
    with _Db(uid) as con:
        ids = [r[0] for r in con.execute("SELECT id FROM docs WHERE docling='wait'").fetchall()]
        for doc_id in ids:
            con.execute("UPDATE docs SET docling='' WHERE id=?", (doc_id,))
            _drop_wait(uid, doc_id)
            _settle(con, doc_id)
    return len(ids)


# ---------------------------------------------------------------- pages for the language model
def next_page(uid, most_pages=None):
    """(doc id, doc name, page, JPEG, tries) of the oldest page still to read, or None.
    most_pages: only documents with at most this many pages to read (short ones by day, wissen.night)."""
    if not os.path.exists(db_path(uid)):
        return None
    with _Db(uid) as con:
        # a document waiting for the Docling server is read by it first (its pages wait until then)
        r = con.execute("SELECT p.doc, d.name, p.page, p.jpeg, p.tries FROM pages p JOIN docs d ON d.id=p.doc "
                        "WHERE d.docling<>'wait' " + ("AND d.pages<=? " if most_pages else "")
                        + "ORDER BY d.created, p.doc, p.page LIMIT 1",
                        (most_pages,) if most_pages else ()).fetchone()
    return tuple(r) if r else None


def pages_waiting(uid):
    """Pages still to be read by the language model (0 without a database; never creates one)."""
    if not os.path.exists(db_path(uid)):
        return 0
    with _Db(uid) as con:
        return con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]


def waiting_state(uid, long_pages, doc_id=None):
    """Numbers for Ich → Mein Zustand (hintergrund.py), never text: pages still to read (in short
    documents and in long ones), documents without a card yet, and for doc_id its name and pages."""
    out = {"docs": 0, "pages": 0, "short": 0, "long_docs": 0, "long_pages": 0, "briefs": 0, "doc": None}
    if not os.path.exists(db_path(uid)):
        return out
    with _Db(uid) as con:
        for pages, n in con.execute("SELECT d.pages, COUNT(*) FROM pages p JOIN docs d ON d.id=p.doc GROUP BY p.doc").fetchall():
            out["pages"] += n
            if (pages or 0) <= long_pages:
                out["short"] += n
            else:
                out["long_docs"] += 1
                out["long_pages"] += n
        out["docs"] = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        out["briefs"] = con.execute("SELECT COUNT(*) FROM docs WHERE brief='' AND state='ready'").fetchone()[0]
        if doc_id:
            r = con.execute("SELECT name, pages, (SELECT COUNT(*) FROM pages p WHERE p.doc=d.id) FROM docs d WHERE id=?",
                            (doc_id,)).fetchone()
            if r:
                out["doc"] = {"name": r[0], "pages": r[1] or 0, "left": r[2]}
    return out


def page_read(uid, doc_id, page, text=None, failed=False, max_tries=2):
    """The model's text of a page (or a failed try); the document is ready once no page waits."""
    with _Db(uid) as con:
        if not con.execute("SELECT 1 FROM pages WHERE doc=? AND page=?", (doc_id, page)).fetchone():
            return   # deleted meanwhile
        if failed:
            con.execute("UPDATE pages SET tries=tries+1 WHERE doc=? AND page=?", (doc_id, page))
            if con.execute("SELECT tries FROM pages WHERE doc=? AND page=?", (doc_id, page)).fetchone()[0] < max_tries:
                return
            con.execute("UPDATE docs SET note=CASE WHEN note='' THEN ? ELSE note || '; ' || ? END WHERE id=?",
                        (f"Seite {page} nicht lesbar", f"Seite {page} nicht lesbar", doc_id))
            con.execute("UPDATE pagetext SET done=1 WHERE doc=? AND page=?", (doc_id, page))   # not tried again
        else:
            n = con.execute("SELECT COALESCE(MAX(n), -1) FROM chunks WHERE doc=?", (doc_id,)).fetchone()[0]
            w = con.execute("SELECT changed FROM pagetext WHERE doc=? AND page=?", (doc_id, page)).fetchone()
            for c, part in pieces(_clean_text(text or "")):
                n += 1
                _put_chunk(con, doc_id, n, page, c, w[0] if w else 0, part)
        # a notebook page (reMarkable): its whole text is kept, so an unchanged page is not read again
        con.execute("UPDATE pagetext SET text=CASE WHEN text='' THEN ? ELSE text || char(10) || ? END, done=1 "
                    "WHERE doc=? AND page=?", (text or "", text or "", doc_id, page))
        con.execute("DELETE FROM pages WHERE doc=? AND page=?", (doc_id, page))
        set_heads(con, doc_id)
        if not con.execute("SELECT 1 FROM pages WHERE doc=?", (doc_id,)).fetchone():
            has = con.execute("SELECT 1 FROM chunks WHERE doc=?", (doc_id,)).fetchone()
            con.execute("UPDATE docs SET state=? WHERE id=?", ("ready" if has else "error", doc_id))


def count_today(uid, day, add=0, key="vision"):
    """Pages read by the language model on this day (day: "YYYY-MM-DD" from the caller); key "night"
    counts the night window apart."""
    with _Db(uid) as con:
        r = con.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        d = json.loads(r[0]) if r else {}
        n = d.get("n", 0) if d.get("day") == day else 0
        if add:
            n += add
            con.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (key, json.dumps({"day": day, "n": n})))
    return n


# ---------------------------------------------------------------- meaning vectors (docembed.py)
def missing_vectors(uid, limit=16):
    """[(chunk id, text)] of pieces without a vector yet; the text with its context line in front (Stufe 2)."""
    if not os.path.exists(db_path(uid)):
        return []
    with _Db(uid) as con:
        return [tuple(r) for r in con.execute("SELECT id, CASE WHEN COALESCE(head, '')<>'' THEN head || char(10) || text "
                                              "ELSE text END FROM chunks WHERE vec IS NULL ORDER BY id LIMIT ?",
                                              (limit,)).fetchall()]


# ---------------------------------------------------------------- context lines (Stufe 2 of plan suche-schaerfen)
def _title(d):
    return str(d["title"] or "").strip() or re.sub(r"[_]+", " ", os.path.splitext(d["name"])[0]).strip()


def head_line(title, art, part):
    """The context line of a piece: the document's title (its card's, else the file name), its kind and the
    headings above the piece. Outside text, so it is cut hard and only ever read as data."""
    q = lambda v, n: re.sub(r"\s+", " ", re.sub(r"<<<|>>>|[„“\n\r\t]", "", str(v or ""))).strip()[:n]  # noqa: E731
    return " · ".join(x for x in (q(title, 80), q(art, 30), q(part, 120)) if x)


def _old_parts(texts):
    """The parts of pieces cut before V01.0.519, from the headings inside them (one heading carries on)."""
    out, carry = [], ""
    for t in texts:
        blocks = [b for b in re.sub(r"\n\s*\n+", "\n\n", t).split("\n\n") if b.strip()]
        found = [h for h in (heading(b) for b in blocks) if h]
        starts = bool(blocks) and bool(heading(blocks[0]))
        heads = ([] if starts or not carry else [carry]) + [h for h in found if h != carry or starts]
        out.append(_part(list(dict.fromkeys(heads))))
        if found:
            carry = found[-1]
    return out


def set_heads(con, doc_id):
    """Builds the context lines of one document's pieces (and their entry in ftshead). A piece whose line
    changed loses its meaning vector, so missing_vectors embeds it again with the line."""
    d = con.execute("SELECT name, title, art FROM docs WHERE id=?", (doc_id,)).fetchone()
    if not d:
        return 0
    rows = con.execute("SELECT id, text, part, head FROM chunks WHERE doc=? ORDER BY n, id", (doc_id,)).fetchall()
    old = _old_parts([r["text"] for r in rows]) if any(r["part"] is None for r in rows) else []
    changed = 0
    for i, r in enumerate(rows):
        part = r["part"] if r["part"] is not None else old[i]
        h = head_line(_title(d), d["art"], part)
        con.execute("DELETE FROM ftshead WHERE rowid=?", (r["id"],))
        if h:
            con.execute("INSERT INTO ftshead (rowid, terms) VALUES (?,?)", (r["id"], " ".join(_terms(h))))
        if h != (r["head"] or "") or r["part"] is None:
            con.execute("UPDATE chunks SET part=?, head=?, vec=CASE WHEN ?<>COALESCE(head, '') THEN NULL ELSE vec END "
                        "WHERE id=?", (part, h, h, r["id"]))
            changed += 1
    con.execute("UPDATE docs SET headv=? WHERE id=?", (HEADV, doc_id))
    return changed


def due_heads(uid, most=20):
    """Quiet moments (wissen.due_once): context lines for up to `most` documents still without (new, read
    again, a new card, or from before V01.0.519). Returns how many documents were done."""
    if not os.path.exists(db_path(uid)):
        return 0
    with _Db(uid) as con:
        ids = [r[0] for r in con.execute("SELECT id FROM docs WHERE COALESCE(headv, 0)<? ORDER BY created LIMIT ?", (HEADV, int(most))).fetchall()]
        for i in ids:
            set_heads(con, i)
    return len(ids)


def heads_left(uid):
    """Documents whose context lines are still to be built (Live-Übersicht, Ich → Dokumente)."""
    if not os.path.exists(db_path(uid)):
        return 0
    with _Db(uid) as con:
        return con.execute("SELECT COUNT(*) FROM docs WHERE COALESCE(headv, 0)<?", (HEADV,)).fetchone()[0]


def set_vectors(uid, pairs):
    """pairs: [(chunk id, float16 bytes)]."""
    with _Db(uid) as con:
        con.executemany("UPDATE chunks SET vec=? WHERE id=?", [(v, i) for i, v in pairs])



def vector_state(uid):
    """(pieces with a vector, all pieces)."""
    if not os.path.exists(db_path(uid)):
        return 0, 0
    with _Db(uid) as con:
        r = con.execute("SELECT COUNT(vec), COUNT(*) FROM chunks").fetchone()
    return r[0], r[1]


def _vectors(uid):
    import numpy as np
    with _Db(uid) as con:
        stamp = (os.path.getmtime(db_path(uid)), con.execute("SELECT COUNT(vec), MAX(id) FROM chunks").fetchone()[:])
        hit = _vcache.get(uid)
        if hit and hit[0] == stamp:
            return hit[1], hit[2]
        rows = con.execute("SELECT c.id, c.vec FROM chunks c JOIN docs d ON d.id=c.doc "
                           "WHERE c.vec IS NOT NULL AND d.use=1").fetchall()
    ids = [r[0] for r in rows]
    mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float16).reshape(len(rows), -1) if rows else None
    if len(_vcache) > 50:
        _vcache.clear()
    _vcache[uid] = (stamp, ids, mat)
    return ids, mat


# ---------------------------------------------------------------- search
_WORD = re.compile(r"[\wäöüß]+", re.I)
_STOP = set("""der die das und oder ein eine einer eines einem einen ist sind war waren wird werden
mit von zu im in am an auf für fur bei aus nach wie was wer wo wann ich du er sie es wir ihr mein dein
nicht auch noch nur so dass den dem des als um the a an and or of to in on for is are was be with by""".split())


def _terms(text):
    out = []
    for w in _WORD.findall(text.lower()):
        if len(w) < 2 or w in _STOP:
            continue
        for suf in ("ungen", "ung", "en", "er", "es", "e", "n", "s"):  # rough stemming, German and English
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[:-len(suf)]
                break
        out.append(w)
    return out


def search(uid, query, k=5, qvec=None, shared_only=False, only_docs=None, fresh=False, now=None):
    """Best-matching pieces of this profile's documents in use: [{"id", "name", "page", "text", "file", "score"}].
    qvec: the query's meaning vector (docembed), merged with the full-text ranking. shared_only: only the
    documents this profile offers to everyone ("Für alle"), for another profile's search. only_docs: a set
    of document ids (tags, art) the search keeps to. fresh ("Neueste zuerst"): a piece changed lately gains up
    to FRESH (about two places), halved every FRESH_HALF; fit stays first. Each hit then carries "changed"."""
    if not os.path.exists(db_path(uid)) and not os.path.isdir(_dir(uid)):
        return []
    q = sorted(set(t for t in _terms(query) if re.fullmatch(r"\w+", t)))
    ranks, only = {}, None
    keep = None if only_docs is None else [d for d in only_docs if re.fullmatch(r"[0-9a-f]{12}", d)]
    if keep is not None and not keep:
        return []
    cond = "d.use=1" + (" AND d.shared=1 AND d.state='ready'" if shared_only else "") + \
        (" AND d.id IN (%s)" % ",".join("'%s'" % d for d in keep) if keep is not None else "")
    with _Db(uid) as con:
        if shared_only or only_docs is not None:
            only = {r[0] for r in con.execute("SELECT c.id FROM chunks c JOIN docs d ON d.id=c.doc WHERE " + cond)}
            if not only:
                return []
        if q:
            # the piece's own words, and its context line (title, kind, headings) weighed lower (Stufe 2)
            match = " OR ".join(f'"{t}"' for t in q)
            score = {}
            for table, w, most in (("fts", 1.0, 60), ("ftshead", HEAD_WEIGHT, 200)):
                for r in con.execute(f"SELECT {table}.rowid, bm25({table}) FROM {table} JOIN chunks c ON c.id={table}.rowid "
                                     f"JOIN docs d ON d.id=c.doc WHERE {table} MATCH ? AND " + cond +
                                     f" ORDER BY bm25({table}) LIMIT {most}", (match,)):
                    score[r[0]] = score.get(r[0], 0.0) + w * r[1]
            for i, cid in enumerate(sorted(score, key=lambda x: (score[x], x))[:30]):
                ranks[cid] = 1 / (60 + i)
    if qvec is not None:
        import numpy as np
        ids, mat = _vectors(uid)
        if mat is not None and mat.shape[1] == len(qvec):
            sims = mat.astype(np.float32) @ np.asarray(qvec, dtype=np.float32)
            i = 0
            for j in np.argsort(-sims):
                if sims[j] < 0.75 or i >= 30:     # e5 vectors: below 0.75 nothing is really related
                    break
                if only is not None and ids[j] not in only:
                    continue
                ranks[ids[j]] = ranks.get(ids[j], 0) + 1 / (60 + i)
                i += 1
    if not ranks:
        return []
    when = {}
    if fresh:
        now = now or time.time()
        when = _changed(uid, list(ranks))
        for i in ranks:
            if when.get(i):
                ranks[i] += FRESH * 0.5 ** (max(0, now - when[i]) / FRESH_HALF)
    best = sorted(ranks, key=lambda x: -ranks[x])[:k]
    with _Db(uid) as con:
        got = {r["id"]: r for r in con.execute(
            "SELECT c.id, c.doc, c.page, c.text, c.part, c.head, d.name, d.file, d.source, d.place FROM chunks c JOIN docs d ON d.id=c.doc WHERE c.id IN (%s)"
            % ",".join("?" * len(best)), best).fetchall()}
    return [dict({"id": got[i]["doc"], "name": got[i]["name"], "page": got[i]["page"], "text": got[i]["text"],
                  "part": got[i]["part"] or "", "head": got[i]["head"] or "",
                  "file": bool(got[i]["file"]) or got[i]["source"] == "nas", "source": got[i]["source"], "score": ranks[i]},
                 **({"place": got[i]["place"] or ""} if got[i]["source"] == "nas" else {}),
                 **({"changed": when.get(i, 0)} if fresh else {})) for i in best if i in got]


def _changed(uid, ids):
    """{chunk id: when it last changed}: the piece's own time, else its document's change, else its upload."""
    out = {}
    with _Db(uid) as con:
        for at in range(0, len(ids), 500):
            part = ids[at:at + 500]
            for r in con.execute("SELECT c.id, COALESCE(NULLIF(c.changed, 0), NULLIF(d.changed, 0), d.created, 0) "
                                 "FROM chunks c JOIN docs d ON d.id=c.doc WHERE c.id IN (%s)" % ",".join("?" * len(part)), part):
                out[r[0]] = int(r[1] or 0)
    return out


def recent(uid, since=0, until=None, k=8, shared_only=False):
    """The pages changed last (newest first), within [since, until): [{"id", "name", "page", "text", "file",
    "source", "changed"}]: "Was habe ich zuletzt notiert?" (only for "Neueste zuerst"). One hit per page."""
    if not os.path.exists(db_path(uid)):
        return []
    until = until or 2 ** 62
    cond = "d.use=1" + (" AND d.shared=1 AND d.state='ready'" if shared_only else "")
    t = "COALESCE(NULLIF(c.changed, 0), NULLIF(d.changed, 0), d.created, 0)"
    with _Db(uid) as con:
        rows = con.execute(f"SELECT c.doc, c.page, d.name, d.file, d.source, MAX({t}) AS w, "
                           f"GROUP_CONCAT(c.text, char(10)) AS text FROM chunks c JOIN docs d ON d.id=c.doc "
                           f"WHERE {cond} AND {t} >= ? AND {t} < ? GROUP BY c.doc, COALESCE(c.page, 0) "
                           f"ORDER BY w DESC LIMIT ?", (int(since or 0), int(until), int(k))).fetchall()
    return [{"id": r["doc"], "name": r["name"], "page": r["page"], "text": (r["text"] or "")[:1500], "file": bool(r["file"]),
             "source": r["source"], "changed": int(r["w"] or 0)} for r in rows]


def sample_pieces(uid, skip=(), most=20, least=200):
    """Suchprüfung (suchpruefung.py): up to `most` random pieces [(doc id, page, text)] of ready documents in use,
    at least `least` characters long, never from the documents in skip (those have enough test questions)."""
    if not os.path.exists(db_path(uid)):
        return []
    with _Db(uid) as con:
        rows = con.execute("SELECT c.doc, c.page, c.text FROM chunks c JOIN docs d ON d.id=c.doc WHERE d.use=1 "
                           "AND d.state='ready' AND length(c.text)>=? ORDER BY random() LIMIT ?",
                           (int(least), int(most) * 3)).fetchall()
    return [(r[0], r[1], r[2]) for r in rows if r[0] not in skip][:most]


def doc_piece(uid, doc, least=200):
    """Suchprüfung, Sammelfragen: one random piece (page, text) of this ready document in use, at least `least`
    characters long (else the longest), or None."""
    if not os.path.exists(db_path(uid)):
        return None
    with _Db(uid) as con:
        r = con.execute("SELECT c.page, c.text FROM chunks c JOIN docs d ON d.id=c.doc WHERE d.id=? AND d.use=1 "
                        "AND d.state='ready' ORDER BY length(c.text)>=? DESC, random() LIMIT 1", (doc, int(least))).fetchone()
    return (r[0], r[1]) if r else None


def notebook_pages(uid, since=0, doc=None, most=400):
    """The reMarkable pages changed since then (rmplus.py: @Spark, tasks, meetings, the week), newest first:
    [{"doc", "name", "page", "text", "done", "changed"}]; done False while the handwriting is not read yet.
    doc: only that notebook's pages, whenever they changed."""
    if not os.path.exists(db_path(uid)):
        return []
    t = "COALESCE(NULLIF(p.changed, 0), NULLIF(d.changed, 0), d.created, 0)"
    cond, args = ("p.doc=?", [doc]) if doc else (f"{t} >= ?", [int(since or 0)])
    with _Db(uid) as con:
        rows = con.execute(f"SELECT p.doc, d.name, p.page, p.text, p.done, {t} AS w FROM pagetext p JOIN docs d ON d.id=p.doc "
                           f"WHERE d.source='remarkable' AND d.use=1 AND {cond} ORDER BY w DESC, p.page LIMIT ?",
                           args + [int(most)]).fetchall()
    return [{"doc": r["doc"], "name": r["name"], "page": r["page"], "text": r["text"] or "", "done": bool(r["done"]),
             "changed": int(r["w"] or 0)} for r in rows]


def sqlite_copy(src, dst):
    """A consistent copy of a database file, also while it is written (for the backup)."""
    a = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=15)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
