"""The person's own Kiwix (kiwix-serve with ZIM files: Wikipedia, Wikivoyage, handbooks ...) as a knowledge
source that works without the internet. Off until the admin allows it (chat.kiwix with an address in
chat.kiwix_url) and a profile switches it on for itself (setting kiwix_on). Guests never.

Used by wiki.py: the wikipedia tool asks the Wikipedia books of the Kiwix first (online Wikipedia only
when nothing fits or the Kiwix does not answer), archive_search searches the full text of the chosen
books, article_more reads on in an article. When SearXNG or the internet is gone the web search falls
back to the Kiwix (chat_tools.py) and says so.

Every address is built from the admin's address: only paths of kiwix-serve's own endpoints (catalog,
suggest, search, content) go out, redirects only to the same host and only below /content/<book>/.
Connections go through netguard (HOME: the home network is allowed, the Spark's own ports and
link-local never). Answers are read with a byte cap, XML with a DOCTYPE is refused (no entities), HTML
is turned into plain text by a parser (no scripts, nothing evaluated). The text is outside text: the
tools are in wiki.offer's "outside" set, so it locks switching and saving like a web page.
"""
import asyncio
import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

import netguard
import profiles
from common import load_config

MAX_BOOKS = 10             # chosen books (admin) and books asked at once
MAX_SEARCH_BOOKS = 5       # books one full-text search asks at the same time
SMALL_BYTES = 1_000_000    # catalog, suggest, search answers
ARTICLE_BYTES = 4_000_000  # one article page (HTML with markup)
PART_CHARS = 1500          # one part of an article handed to the model
MAX_PARTS = 3              # parts of one article (intro + 2 more)
CATALOG_SECONDS = 3600
CACHE_SECONDS = 24 * 3600
MAX_CACHE = 300
MAX_REFS = 500
BOOK = re.compile(r"[\w.\-]{1,120}")
URL = re.compile(r"https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[\w.\-~/]*)?")
_catalog = [0.0, []]       # [when, books]
_cache = {}                # (kind, book, text) -> (when, value)
_refs = {}                 # short id -> (book, path, title)


def ccfg():
    return load_config().get("chat", {})


def base():
    """The admin's address without a trailing slash, or '' when none (or not a plain http(s) address)."""
    url = str(ccfg().get("kiwix_url") or "").strip().rstrip("/")
    return url if URL.fullmatch(url) else ""


def admin_on():
    return bool(ccfg().get("kiwix", False) is True and base())


def usable(uid):
    return bool(uid and admin_on() and profiles.settings(uid).get("kiwix_on"))


def web_fallback(uid):
    """The web search may answer from the Kiwix when SearXNG or the internet is gone (always with the switches)."""
    return usable(uid)


def log(what, book, hits, t0):
    """One line for Zustand -> Logs (area "Wissen"): book, hits and time, never the question."""
    print(f"kiwix: {what} buch={book or '-'} treffer={hits} ms={int((time.monotonic() - t0) * 1000)}", flush=True)


# ---------------------------------------------------------------- fetching
class Refused(ValueError):
    pass


def _origin(url):
    p = urlsplit(url)
    return p.scheme, (p.hostname or "").lower(), p.port or (443 if p.scheme == "https" else 80)


async def _get(path, params=None, most=SMALL_BYTES, under=None):
    """(text, final path) of base + path. Redirects (at most 3) only to the same host, and when under is
    given only to paths below it."""
    root = base()
    if not root:
        raise Refused("no Kiwix address")
    url = root + path
    home = _origin(root)
    async with netguard.client(netguard.HOME, max_bytes=most, timeout=httpx.Timeout(10, connect=3),
                               follow_redirects=False,
                               headers={"User-Agent": "speech-on-dgx-spark (local voice assistant)"}) as c:
        for _ in range(4):
            r = await c.get(url, params=params)
            if r.status_code in (301, 302, 303, 307, 308):
                nxt = urljoin(url, r.headers.get("location", ""))
                p = urlsplit(nxt)
                if _origin(nxt) != home or p.query or (under and not p.path.startswith(under)):
                    raise Refused("Kiwix redirect to another place")
                url, params = nxt, None
                continue
            if r.status_code == 404:
                return None, urlsplit(url).path
            if r.status_code >= 400:
                raise Refused(f"Kiwix answers {r.status_code}")
            return r.text, urlsplit(url).path
    raise Refused("too many Kiwix redirects")


def _xml(text):
    """The parsed XML, or None. A DOCTYPE (and with it any entity) is refused before parsing."""
    if not text or re.search(r"<!(DOCTYPE|ENTITY)", text, re.I):
        return None
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _local(el):
    return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""


def _child(el, name):
    return next((x for x in el if _local(x) == name), None)


def _text(el, name, n=200):
    x = _child(el, name)
    return re.sub(r"\s+", " ", (x.text or "") if x is not None else "").strip()[:n]


def _clean(text, n=200):
    """Printable plain text of a title or snippet (tags and entities out)."""
    text = html.unescape(re.sub(r"<[^>]{0,200}>", "", str(text or "")))
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", text)).strip()[:n]


# ---------------------------------------------------------------- books
def parse_catalog(text, root_path=""):
    """[{"id", "title", "lang", "date", "count"}] from an OPDS catalog (kiwix-serve /catalog/v2/entries)."""
    doc = _xml(text)
    if doc is None:
        return []
    books = []
    for e in (x for x in doc.iter() if _local(x) == "entry"):
        book = ""
        for link in (x for x in e if _local(x) == "link"):
            href = unquote(link.get("href") or "")
            if (link.get("type") or "").startswith("text/html") and "/content/" in href:
                book = href.split("/content/", 1)[1].strip("/")
            elif (link.get("type") or "").startswith("text/html") and not book:
                book = href[len(root_path):].strip("/") if href.startswith(root_path) else ""
        if not BOOK.fullmatch(book) or any(b["id"] == book for b in books):
            continue
        date = _text(e, "issued", 10) or _text(e, "updated", 10)
        m = re.search(r"_(\d{4}-\d{2})$", book)
        books.append({"id": book, "title": _clean(_text(e, "title") or book, 120),
                      "lang": re.sub(r"[^a-z,]", "", _text(e, "language", 20).lower())[:20],
                      "date": date if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", date) else (m.group(1) if m else ""),
                      "count": int(_text(e, "articleCount", 12)) if _text(e, "articleCount", 12).isdigit() else 0})
        if len(books) >= 200:
            break
    return books


async def catalog(fresh=False):
    """The books of the Kiwix (kept an hour)."""
    if not fresh and _catalog[1] and time.monotonic() - _catalog[0] < CATALOG_SECONDS:
        return _catalog[1]
    root_path = urlsplit(base()).path.rstrip("/")
    text, _ = await _get("/catalog/v2/entries", {"count": "200"})
    books = parse_catalog(text, root_path)
    if not books:   # kiwix-serve before 3.1: the first catalog
        text, _ = await _get("/catalog/root.xml")
        books = parse_catalog(text, root_path)
    _catalog[:] = [time.monotonic(), books]
    return books


def chosen_ids():
    """The admin's choice (chat.kiwix_books): book names, at most MAX_BOOKS; empty = all."""
    raw = ccfg().get("kiwix_books") or []
    return [b for b in raw if isinstance(b, str) and BOOK.fullmatch(b)][:MAX_BOOKS] if isinstance(raw, list) else []


async def chosen():
    """The books to search: the admin's choice (or all, at most MAX_BOOKS), with title and date when known."""
    try:
        books = await catalog()
    except (httpx.HTTPError, ValueError):
        books = []
    ids = chosen_ids()
    if ids:
        known = {b["id"]: b for b in books}
        return [known.get(i) or {"id": i, "title": i, "lang": "", "date": "", "count": 0} for i in ids]
    return books[:MAX_BOOKS]


def _german(b):
    return "_de_" in b["id"] or b["id"].endswith("_de") or b["lang"].startswith(("deu", "de"))


async def wiki_books():
    """The chosen Wikipedia books, German first, then English, then the rest."""
    wp = [b for b in await chosen() if b["id"].lower().startswith("wikipedia")]
    return sorted(wp, key=lambda b: 0 if _german(b) else 1 if ("_en_" in b["id"] or b["lang"].startswith("en")) else 2)


def label(b):
    """'Wikipedia (Stand 2024-01)' for the answer."""
    return b["title"] + (f", Stand {b['date']}" if b.get("date") else "")


# ---------------------------------------------------------------- articles
class _Text(HTMLParser):
    """Paragraphs, list items and headings of an article page as plain text; no scripts, tables, boxes."""
    SKIP = {"script", "style", "table", "sup", "noscript", "figure", "nav", "footer", "math", "svg", "button"}
    KEEP = {"p", "li", "h2", "h3", "h4", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.keep, self.parts, self.cur = 0, 0, [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.KEEP:
            self.keep += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.KEEP:
            self.keep = max(0, self.keep - 1)
            line = re.sub(r"\s+", " ", "".join(self.cur)).strip()
            if line:
                self.parts.append(line + (":" if tag[0] == "h" and not line.endswith(":") else ""))
            self.cur = []

    def handle_data(self, data):
        if self.keep and not self.skip and sum(map(len, self.parts)) < 60_000:
            self.cur.append(data)


def page_text(page):
    p = _Text()
    try:
        p.feed(page or "")
        p.close()
    except Exception:
        pass
    text = " ".join(p.parts)
    text = re.sub(r"\[\s*(\d+|[a-z]|Anm\. \d+|Bearbeiten|edit)\s*\]", "", text)
    return re.sub(r"[\x00-\x1f\x7f]", " ", re.sub(r"\s+", " ", text)).strip()


def cut(text, n=PART_CHARS):
    """At most n characters, ended at a sentence where possible: (part, rest)."""
    text = text.strip()
    if len(text) <= n:
        return text, ""
    part = text[:n]
    end = max(part.rfind(". "), part.rfind("! "), part.rfind("? "))
    if end > n // 3:
        return part[:end + 1], text[end + 2:]
    return part.rstrip() + " …", text[n:]


def parts(text):
    out = []
    while text and len(out) < MAX_PARTS:
        p, text = cut(text)
        out.append(p)
    return out


def _path(p):
    """An article path inside a book: printable, no '..', no query, at most 300 characters."""
    p = unquote(str(p or "")).strip().lstrip("/")
    if not p or len(p) > 300 or ".." in p.split("/") or re.search(r"[\x00-\x1f\x7f?#\\]", p):
        return ""
    return p


def ref(book, path, title):
    """A short id the model can hand back to article_more (never a free address)."""
    k = "k" + hashlib.sha1(f"{book}/{path}".encode()).hexdigest()[:10]
    if k not in _refs and len(_refs) >= MAX_REFS:
        for x in list(_refs)[:MAX_REFS // 4]:
            _refs.pop(x, None)
    _refs[k] = (book, path, title)
    return k


def cached(key):
    hit = _cache.get(key)
    return hit[1] if hit and time.time() - hit[0] < CACHE_SECONDS else None


def keep(key, value):
    if len(_cache) >= MAX_CACHE:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:MAX_CACHE // 4]:
            _cache.pop(k, None)
    _cache[key] = (time.time(), value)


async def article(book, path):
    """The parts of one article (at most MAX_PARTS × PART_CHARS), or []."""
    if not BOOK.fullmatch(book or "") or not _path(path):
        return []
    key = ("article", book, path)
    hit = cached(key)
    if hit is not None:
        return hit
    root_path = urlsplit(base()).path.rstrip("/")
    page, _ = await _get(f"/content/{book}/" + quote(_path(path), safe="/:,()'!*-._~"),
                         most=ARTICLE_BYTES, under=f"{root_path}/content/{book}/")
    out = parts(page_text(page)) if page else []
    keep(key, out)
    return out


async def suggest(book, query):
    """[(title, path)] of article titles that fit (kiwix-serve /suggest)."""
    text, _ = await _get("/suggest", {"content": book, "term": query, "count": "5"})
    try:
        items = json.loads(text or "[]")
    except ValueError:
        return []
    out = []
    for x in items if isinstance(items, list) else []:
        if isinstance(x, dict) and x.get("path") and x.get("kind", "path") == "path":
            p = _path(x["path"])
            if p:
                out.append((_clean(x.get("value") or x.get("label") or p, 120), p))
    return out[:5]


def parse_search(text, book, root_path=""):
    """[(title, path, snippet)] from kiwix-serve /search?format=xml; links only inside this book."""
    doc = _xml(text)
    if doc is None:
        return []
    out = []
    for it in (x for x in doc.iter() if _local(x) == "item"):
        link = unquote(_text(it, "link", 600))
        link = urlsplit(link).path if link.startswith(("http://", "https://")) else link
        for pre in (f"{root_path}/content/{book}/", f"{root_path}/{book}/"):
            if link.startswith(pre):
                p = _path(link[len(pre):])
                if p:
                    out.append((_clean(_text(it, "title"), 120) or p, p, _clean(_text(it, "description", 600), 300)))
                break
        if len(out) >= 5:
            break
    return out


async def fulltext(book, query):
    root_path = urlsplit(base()).path.rstrip("/")
    text, _ = await _get("/search", {"content": book, "pattern": query, "format": "xml", "pageLength": "5"})
    return parse_search(text, book, root_path)


# ---------------------------------------------------------------- what the tools hand over
async def wiki_lookup(query):
    """{"title", "text", "book", "ref"} for the best Wikipedia article in the Kiwix, or None."""
    t0 = time.monotonic()
    books = (await wiki_books())[:3]
    for b in books:
        hits = await suggest(b["id"], query) or [(t, p) for t, p, _ in await fulltext(b["id"], query)][:1]
        for title, path in hits[:1]:
            got = await article(b["id"], path)
            if got:
                log("wikipedia", b["id"], 1, t0)
                return {"title": title, "text": got[0], "book": b, "ref": ref(b["id"], path, title), "more": len(got) > 1}
    log("wikipedia", ",".join(b["id"] for b in books)[:120], 0, t0)
    return None


async def search(query, book=""):
    """Full text in the chosen books (or the one named): a fixed text for the model."""
    t0 = time.monotonic()
    books = await chosen()
    if book:
        books = [b for b in books if b["id"] == book or b["title"].lower() == str(book).lower()] or books
    books = books[:MAX_SEARCH_BOOKS]
    if not books:
        return "Im Kiwix-Archiv sind keine Bücher ausgewählt oder es ist nicht erreichbar.", []
    found = await asyncio.gather(*(fulltext(b["id"], query) for b in books), return_exceptions=True)
    hits = [(b, h) for b, res in zip(books, found) if isinstance(res, list) for h in res]
    log("search", ",".join(b["id"] for b in books)[:120], len(hits), t0)
    if not hits:
        if all(isinstance(r, Exception) for r in found):
            raise Refused("Kiwix not reachable")
        return f"Im Kiwix-Archiv steht nichts zu „{query}“.", []
    best_b, (title, path, _) = hits[0]
    got = await article(best_b["id"], path)
    lines = [f"Aus dem eigenen Kiwix-Archiv ({label(best_b)}), Artikel „{title}“"
             f" [article: {ref(best_b['id'], path, title)}]: {got[0] if got else ''}"]
    others = hits[1:6]
    if others:
        lines.append("Weitere Treffer (mit article_more lesbar): " + "; ".join(
            f"„{t}“ aus {b['title']} [article: {ref(b['id'], p, t)}]" + (f" – {s[:160]}" if s else "")
            for b, (t, p, s) in others))
    sources = [{"title": f"{t} ({b['title']})", "url": f"{base()}/content/{b['id']}/{quote(p, safe='/')}"}
               for b, (t, p, _) in hits[:6]]
    return "\n".join(lines), sources


async def more(article_ref, part):
    """Part 1..MAX_PARTS of an article the tools named before."""
    hit = _refs.get(str(article_ref or "").strip())
    if not hit:
        return "Diesen Artikel kenne ich nicht; suche ihn zuerst mit wikipedia oder archive_search."
    book, path, title = hit
    got = await article(book, path)
    if part < 1 or part > len(got):
        return f"Vom Artikel „{title}“ gibt es nur {len(got)} Teil(e) zum Vorlesen; mehr lese ich nicht."
    return f"Kiwix-Archiv, Artikel „{title}“, Teil {part} von {len(got)}: {got[part - 1]}"


async def web_instead(query):
    """When the web search fails: (text, sources) from the Kiwix, saying it is no current news."""
    text, sources = await search(query)
    books = await chosen()
    when = ", ".join(sorted({b["date"] for b in books if b.get("date")}))[:60]
    return ("Die Websuche ist gerade nicht erreichbar (Internet oder SearXNG weg). Die folgende Antwort kommt aus dem "
            f"Offline-Archiv Kiwix{f' (Stand {when})' if when else ''}. Sag dem Nutzer das am Anfang und dass es "
            "nichts Aktuelles enthält.\n\n" + text), sources


async def check():
    """For "Kiwix prüfen": reachable? which books? one test lookup with its time."""
    t0 = time.monotonic()
    out = {"ok": False, "url": base(), "books": [], "ms": 0, "test": None, "error": ""}
    if not out["url"]:
        out["error"] = "Keine Kiwix-Adresse eingetragen."
        return out
    try:
        books = await catalog(fresh=True)
        out["ms"] = int((time.monotonic() - t0) * 1000)
        out["books"] = books[:200]
        out["chosen"] = [b["id"] for b in await chosen()]
        out["ok"] = bool(books)
        if not books:
            out["error"] = "Kiwix antwortet, aber der Katalog ist leer oder nicht lesbar."
        wp = (await wiki_books())[:1] or [b for b in books if b["id"] in out["chosen"]][:1]
        if wp:
            t1 = time.monotonic()
            hits = await suggest(wp[0]["id"], "Erde") or await suggest(wp[0]["id"], "Earth")
            out["test"] = {"book": wp[0]["title"], "hits": len(hits), "ms": int((time.monotonic() - t1) * 1000)}
    except (httpx.HTTPError, ValueError) as e:
        out["error"] = f"Kiwix nicht erreichbar ({type(e).__name__}: {str(e)[:120]})"
    log("check", "", len(out["books"]), t0)
    return out
