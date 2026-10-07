"""Documents per profile: text extraction, chunking and keyword search (BM25).

Files live in the profile's folder, so only that profile's requests can reach them:

    USERS_DIR/<user id>/docs/<doc id>.json   {"id", "name", "size", "created", "chunks": [text, ...]}

No embedding model is needed: the search is lexical, which works well for names, numbers and
terms from one's own documents.
"""
import html.parser
import io
import json
import math
import os
import re
import secrets
import threading
import time
import zipfile
from collections import Counter

import profiles

MAX_FILE = 20 * 1024 * 1024
MAX_DOCS = 200
MAX_CHARS = 2_000_000          # text per document after extraction
CHUNK, OVERLAP = 900, 150
TYPES = (".pdf", ".txt", ".md", ".docx", ".html", ".htm", ".csv")
_lock = threading.Lock()
_cache = {}                    # uid -> (mtime of the docs folder, index)


def _dir(uid):
    return profiles._path(uid, "docs")


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


def _decode(data):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract(name, data):
    """Plain text of an uploaded file; raises ValueError for unsupported or unreadable files."""
    ext = os.path.splitext(name.lower())[1]
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("PDF support is missing; run the update (it installs pypdf)")
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            raise ValueError(f"cannot read this PDF: {e}")
        if not text.strip():
            raise ValueError("this PDF has no text layer (scanned pages are not supported)")
        return text
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        except Exception:
            raise ValueError("cannot read this Word file")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))
    if ext in (".html", ".htm"):
        p = _HtmlText()
        p.feed(_decode(data))
        return "".join(p.parts)
    if ext in (".txt", ".md", ".csv"):
        return _decode(data)
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


# ---------------------------------------------------------------- storage
def list_docs(uid):
    d = _dir(uid)
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            try:
                with open(os.path.join(d, f)) as fh:
                    x = json.load(fh)
                out.append({"id": x["id"], "name": x["name"], "size": x.get("size"),
                            "created": x.get("created"), "chunks": len(x.get("chunks", []))})
            except (OSError, ValueError, KeyError):
                continue
    return sorted(out, key=lambda x: -(x["created"] or 0))


def add(uid, name, data):
    if len(data) > MAX_FILE:
        raise ValueError("file is larger than 20 MB")
    name = os.path.basename(str(name or "document"))[:120] or "document"
    parts = chunks(extract(name, data))
    if not parts:
        raise ValueError("no text found in this file")
    with _lock:
        if len(list_docs(uid)) >= MAX_DOCS:
            raise ValueError(f"at most {MAX_DOCS} documents per profile")
        doc = {"id": secrets.token_hex(6), "name": name, "size": len(data), "created": int(time.time()),
               "chunks": parts}
        profiles._write(os.path.join(_dir(uid), doc["id"] + ".json"), doc)
    return {"id": doc["id"], "name": name, "chunks": len(parts)}


def delete(uid, doc_id):
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        return False
    path = os.path.join(_dir(uid), doc_id + ".json")
    with _lock:
        if os.path.exists(path):
            os.remove(path)
            return True
    return False


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


def _index(uid):
    d = _dir(uid)
    try:
        stamp = max([os.stat(d).st_mtime] + [os.stat(os.path.join(d, f)).st_mtime for f in os.listdir(d)])
    except OSError:
        return []
    hit = _cache.get(uid)
    if hit and hit[0] == stamp:
        return hit[1]
    idx = []
    for f in os.listdir(d):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, f)) as fh:
                x = json.load(fh)
        except (OSError, ValueError):
            continue
        for i, c in enumerate(x.get("chunks", [])):
            t = _terms(c)
            idx.append((x["name"], i, c, Counter(t), len(t)))
    _cache[uid] = (stamp, idx)
    return idx


def search(uid, query, k=5):
    """Best-matching pieces of this profile's documents: [{"name", "text"}]."""
    idx = _index(uid)
    q = set(_terms(query))
    if not idx or not q:
        return []
    n = len(idx)
    avg = sum(x[4] for x in idx) / n or 1
    df = {t: sum(1 for x in idx if t in x[3]) for t in q}
    scored = []
    for name, i, text, tf, length in idx:
        s = 0.0
        for t in q:
            if tf.get(t):
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * length / avg))
        if s > 0:
            scored.append((s, name, text))
    scored.sort(key=lambda x: -x[0])
    return [{"name": name, "text": text} for _, name, text in scored[:k]]
