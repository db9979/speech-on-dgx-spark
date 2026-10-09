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

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER, created INTEGER,
    kind TEXT DEFAULT 'text', state TEXT DEFAULT 'ready', note TEXT DEFAULT '', pages INTEGER DEFAULT 0,
    use INTEGER DEFAULT 1, file TEXT DEFAULT '', source TEXT DEFAULT 'upload', shared INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, doc TEXT NOT NULL, n INTEGER, page INTEGER,
    text TEXT NOT NULL, vec BLOB);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(terms);
CREATE TABLE IF NOT EXISTS pages (doc TEXT NOT NULL, page INTEGER NOT NULL, jpeg BLOB NOT NULL,
    tries INTEGER DEFAULT 0, PRIMARY KEY (doc, page));
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def _dir(uid):
    return profiles._path(uid, "docs")


def _files(uid):
    return os.path.join(_dir(uid), "files")


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
    if "shared" not in {r[1] for r in con.execute("PRAGMA table_info(docs)")}:    # databases from V01.0.224
        con.execute("ALTER TABLE docs ADD COLUMN shared INTEGER DEFAULT 0")
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


def _put_chunk(con, doc, n, page, text):
    cur = con.execute("INSERT INTO chunks (doc, n, page, text) VALUES (?,?,?,?)", (doc, n, page, text))
    con.execute("INSERT INTO fts (rowid, terms) VALUES (?,?)", (cur.lastrowid, " ".join(_terms(text))))


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


def chunks(text):
    """Pieces of about CHUNK characters, cut at paragraph or sentence ends, overlapping a little."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()[:MAX_CHARS]
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
            "vecs": r["nvecs"], "use": bool(r["use"]), "shared": bool(r["shared"]), "file": bool(r["file"]), "source": r["source"]}


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


def _read(name, data, text=None, pictures=False, cleaned=False):
    """(pieces [(page, text)], {page: JPEG} for the language model, kind, note) of one file.
    cleaned: a picture kept by the Spark itself (already a cleaned JPEG)."""
    ext = os.path.splitext(name.lower())[1]
    pages, todo, kind, notes = [], {}, "text", []
    if text is not None:
        pages = [(None, text[:MAX_CHARS])]
    elif ext in PICTURES:
        if not pictures:
            raise ValueError("pictures in documents are off (Einstellungen → Funktionen → Bilder und Scans lesen)")
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
        elif scans and not "".join(t for _, t in pages).strip():
            raise ValueError("this PDF has no text layer (scanned pages are read only with "
                             "Einstellungen → Funktionen → Bilder und Scans lesen)")
        elif scans:
            notes.append(f"{len(scans)} Seite{'n' if len(scans) > 1 else ''} ohne Text nicht gelesen "
                         "(„Bilder und Scans lesen“ ist aus)")
        if len(pages) and pages[-1][0] and sum(len(t) for _, t in pages) > MAX_CHARS:
            notes.append(f"Text nach Seite {pages[-1][0]} abgeschnitten")
    else:
        pages, _ = extract_pages(name, data)
    parts = [(p, c) for p, t in pages for c in chunks(_clean_text(t))]
    if not parts and not todo:
        raise ValueError("no text found in this file")
    return parts, todo, kind, "; ".join(notes)


def add(uid, name, data, text=None, pictures=False, keep=0, source="upload", most=MAX_FILE):
    """Stores a document. text: already read elsewhere (the iPhone app reads PDFs and scans itself;
    data is then only its size). pictures: photos and scanned pages may wait for the language model.
    keep: bytes the original may take (0 = do not keep it)."""
    if len(data) > most:
        raise ValueError(f"file is larger than {most // 1024**2} MB")
    name = re.sub(r"[\x00-\x1f\x7f<>\"\\]", "", os.path.basename(str(name or "document")))[:120].strip() or "document"
    ext = os.path.splitext(name.lower())[1]
    if text is None and ext != ".pdf" and len(data) > MAX_OTHER:
        raise ValueError(f"file is larger than {MAX_OTHER // 1024**2} MB (only PDFs may be bigger)")
    parts, todo, kind, note = _read(name, data, text, pictures)
    doc_id = secrets.token_hex(6)
    stored = ""
    with _Db(uid) as con:
        if con.execute("SELECT COUNT(*) FROM docs").fetchone()[0] >= MAX_DOCS:
            raise ValueError(f"at most {MAX_DOCS} documents per profile")
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
        con.execute("INSERT INTO docs (id, name, size, created, kind, state, note, pages, file, source) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (doc_id, name, len(data), int(time.time()), kind, "reading" if todo else "ready", note,
                     len(todo), stored, source))
        for i, (page, c) in enumerate(parts):
            _put_chunk(con, doc_id, i, page, c)
        for page, jpeg in todo.items():
            con.execute("INSERT INTO pages (doc, page, jpeg) VALUES (?,?,?)", (doc_id, page, jpeg))
    return {"id": doc_id, "name": name, "chunks": len(parts), "state": "reading" if todo else "ready",
            "todo": len(todo), "kind": kind, "file": bool(stored)}


def delete(uid, doc_id):
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return False
    if not os.path.exists(db_path(uid)) and not os.path.isdir(_dir(uid)):
        return False
    with _Db(uid) as con:
        r = con.execute("SELECT file FROM docs WHERE id=?", (doc_id,)).fetchone()
        if not r:
            return False
        con.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE doc=?)", (doc_id,))
        con.execute("DELETE FROM chunks WHERE doc=?", (doc_id,))
        con.execute("DELETE FROM pages WHERE doc=?", (doc_id,))
        con.execute("DELETE FROM docs WHERE id=?", (doc_id,))
        if r["file"]:
            try:
                os.remove(os.path.join(_files(uid), r["file"]))
            except OSError:
                pass
    return True


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


def reread(uid, doc_id, pictures=False):
    """Reads a document again from its kept original (V01.0.238): same id, place, "use" and "Für alle";
    pieces, meaning vectors and waiting pages are replaced. Returns like add, None without an original."""
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
    parts, todo, kind, note = _read(name, data, None, pictures, cleaned=r["kind"] == "picture")
    with _Db(uid) as con:
        waiting = con.execute("SELECT COUNT(*) FROM pages WHERE doc<>?", (doc_id,)).fetchone()[0]
        if todo and waiting + len(todo) > MAX_QUEUED:
            raise ValueError(f"at most {MAX_QUEUED} pages may wait to be read; try again later")
        con.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE doc=?)", (doc_id,))
        con.execute("DELETE FROM chunks WHERE doc=?", (doc_id,))
        con.execute("DELETE FROM pages WHERE doc=?", (doc_id,))
        con.execute("UPDATE docs SET kind=?, state=?, note=?, pages=? WHERE id=?",
                    (kind, "reading" if todo else "ready", note, len(todo), doc_id))
        for i, (page, c) in enumerate(parts):
            _put_chunk(con, doc_id, i, page, c)
        for page, jpeg in todo.items():
            con.execute("INSERT INTO pages (doc, page, jpeg) VALUES (?,?,?)", (doc_id, page, jpeg))
    return {"id": doc_id, "name": r["name"], "chunks": len(parts), "state": "reading" if todo else "ready",
            "todo": len(todo), "kind": kind, "file": True}


def list_shared(uid):
    """[{"id", "name", "file", "kind", "pages"}] this profile offers to everyone (ready and in use)."""
    if not os.path.exists(db_path(uid)):
        return []
    with _Db(uid) as con:
        rows = con.execute("SELECT id, name, file, kind, pages FROM docs WHERE shared=1 AND use=1 AND state='ready' "
                           "ORDER BY created DESC, id").fetchall()
    return [{"id": r["id"], "name": r["name"], "file": bool(r["file"]), "kind": r["kind"], "pages": r["pages"]}
            for r in rows]


def is_shared(uid, doc_id):
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id) or not os.path.exists(db_path(uid)):
        return False
    with _Db(uid) as con:
        return bool(con.execute("SELECT 1 FROM docs WHERE id=? AND shared=1 AND use=1 AND state='ready'",
                                (doc_id,)).fetchone())


def original(uid, doc_id):
    """(path, download name, content type) of the kept original, or None."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return None
    with _Db(uid) as con:
        r = con.execute("SELECT name, file FROM docs WHERE id=?", (doc_id,)).fetchone()
    if not r or not r["file"] or not re.fullmatch(r"[0-9a-f]{12}\.[a-z]{2,4}", r["file"]):
        return None
    path = os.path.join(_files(uid), r["file"])
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


# ---------------------------------------------------------------- pages for the language model
def next_page(uid, most_pages=None):
    """(doc id, doc name, page, JPEG, tries) of the oldest page still to read, or None.
    most_pages: only documents with at most this many pages to read (short ones by day, wissen.night)."""
    if not os.path.exists(db_path(uid)):
        return None
    with _Db(uid) as con:
        r = con.execute("SELECT p.doc, d.name, p.page, p.jpeg, p.tries FROM pages p JOIN docs d ON d.id=p.doc "
                        + ("WHERE d.pages<=? " if most_pages else "") + "ORDER BY d.created, p.doc, p.page LIMIT 1",
                        (most_pages,) if most_pages else ()).fetchone()
    return tuple(r) if r else None


def pages_waiting(uid):
    """Pages still to be read by the language model (0 without a database; never creates one)."""
    if not os.path.exists(db_path(uid)):
        return 0
    with _Db(uid) as con:
        return con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]


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
        else:
            n = con.execute("SELECT COALESCE(MAX(n), -1) FROM chunks WHERE doc=?", (doc_id,)).fetchone()[0]
            for c in chunks(_clean_text(text or "")):
                n += 1
                _put_chunk(con, doc_id, n, page, c)
        con.execute("DELETE FROM pages WHERE doc=? AND page=?", (doc_id, page))
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
    """[(chunk id, text)] of pieces without a vector yet."""
    if not os.path.exists(db_path(uid)):
        return []
    with _Db(uid) as con:
        return [tuple(r) for r in con.execute("SELECT id, text FROM chunks WHERE vec IS NULL ORDER BY id LIMIT ?",
                                              (limit,)).fetchall()]


def set_vectors(uid, pairs):
    """pairs: [(chunk id, float16 bytes)]."""
    with _Db(uid) as con:
        con.executemany("UPDATE chunks SET vec=? WHERE id=?", [(v, i) for i, v in pairs])


def drop_vectors(uid):
    if os.path.exists(db_path(uid)):
        with _Db(uid) as con:
            con.execute("UPDATE chunks SET vec=NULL")


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


def search(uid, query, k=5, qvec=None, shared_only=False):
    """Best-matching pieces of this profile's documents in use: [{"id", "name", "page", "text", "file", "score"}].
    qvec: the query's meaning vector (docembed), merged with the full-text ranking. shared_only: only the
    documents this profile offers to everyone ("Für alle"), for another profile's search."""
    if not os.path.exists(db_path(uid)) and not os.path.isdir(_dir(uid)):
        return []
    q = sorted(set(t for t in _terms(query) if re.fullmatch(r"\w+", t)))
    ranks, only = {}, None
    cond = "d.use=1" + (" AND d.shared=1 AND d.state='ready'" if shared_only else "")
    with _Db(uid) as con:
        if shared_only:
            only = {r[0] for r in con.execute("SELECT c.id FROM chunks c JOIN docs d ON d.id=c.doc WHERE " + cond)}
            if not only:
                return []
        if q:
            rows = con.execute("SELECT fts.rowid FROM fts JOIN chunks c ON c.id=fts.rowid JOIN docs d ON d.id=c.doc "
                               "WHERE fts MATCH ? AND " + cond + " ORDER BY bm25(fts) LIMIT 30",
                               (" OR ".join(f'"{t}"' for t in q),)).fetchall()
            for i, r in enumerate(rows):
                ranks[r[0]] = 1 / (60 + i)
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
    best = sorted(ranks, key=lambda x: -ranks[x])[:k]
    with _Db(uid) as con:
        got = {r["id"]: r for r in con.execute(
            "SELECT c.id, c.doc, c.page, c.text, d.name, d.file FROM chunks c JOIN docs d ON d.id=c.doc WHERE c.id IN (%s)"
            % ",".join("?" * len(best)), best).fetchall()}
    return [{"id": got[i]["doc"], "name": got[i]["name"], "page": got[i]["page"], "text": got[i]["text"],
             "file": bool(got[i]["file"]), "score": ranks[i]} for i in best if i in got]


def sqlite_copy(src, dst):
    """A consistent copy of a database file, also while it is written (for the backup)."""
    a = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=15)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
