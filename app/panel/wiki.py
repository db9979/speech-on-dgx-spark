"""Wikipedia straight away: for "Was ist ...?" or "Wer war ...?" the panel asks Wikipedia for the best
matching article and hands its short intro to the model, without SearXNG and without reading whole
pages. Less text before the first word, so the answer starts sooner. Off until the admin allows it
(chat.wiki) and a profile switches it on for itself (setting wiki_on). Guests never.

With the own Kiwix (kiwix.py, V01.0.258) the Wikipedia books there are asked first, the online
Wikipedia only when nothing fits or the Kiwix does not answer; a profile with only the Kiwix switch gets
the wikipedia tool too, answered from the Kiwix alone. archive_search searches the other books,
article_more reads on in an article (at most 3 parts of 1500 characters).

Only the search words leave the Spark. Answers are kept 24 hours in memory (at most MAX_CACHE
entries), so the same question again needs no request. The article text is outside text: it is
handed over as data and locks switching and saving in the same answer like a web page.
"""
import hashlib
import json
import re
import time

import httpx

import kiwix
import profiles
from common import load_config

DEFAULT_URL = "https://de.wikipedia.org"
FALLBACK_URL = "https://en.wikipedia.org"   # only when the admin kept the default and German has nothing
CACHE_SECONDS = 24 * 3600
MAX_CACHE = 300
MAX_BYTES = 1_000_000          # one answer of the Wikipedia API (an intro is a few kB)
MAX_CHARS = 1500               # of the intro handed to the model
_cache = {}


def admin_on():
    return bool(load_config().get("chat", {}).get("wiki", False))


def base():
    return (load_config().get("chat", {}).get("wiki_url") or DEFAULT_URL).rstrip("/")


def usable(uid):
    return bool(uid and admin_on() and profiles.settings(uid).get("wiki_on"))


def _query(text):
    """The search words: printable text only, one line, at most 120 characters."""
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>{}\[\]|]", " ", str(text or ""))).strip()[:120]


def _cut(text, n=MAX_CHARS):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= n:
        return text
    part = text[:n]
    end = max(part.rfind(". "), part.rfind("! "), part.rfind("? "))
    return part[:end + 1] if end > n // 3 else part.rstrip() + " …"


async def _get(url, params):
    """The JSON answer of the Wikipedia API, read with a byte limit."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5), follow_redirects=False,
                                 headers={"User-Agent": "speech-on-dgx-spark (local voice assistant)"}) as c:
        async with c.stream("GET", url + "/w/api.php", params=params) as r:
            if r.status_code >= 400:
                raise ValueError(f"Wikipedia antwortet {r.status_code}")
            data = b""
            async for chunk in r.aiter_bytes():
                data += chunk
                if len(data) > MAX_BYTES:
                    raise ValueError("Antwort von Wikipedia zu groß")
    return json.loads(data or b"{}")


async def lookup(url, query):
    """{"title", "text", "url"} of the best matching article at url, or None."""
    data = await _get(url, {"action": "query", "format": "json", "formatversion": "2", "generator": "search",
                            "gsrsearch": query, "gsrlimit": "1", "gsrnamespace": "0", "prop": "extracts|info",
                            "exintro": "1", "explaintext": "1", "inprop": "url", "redirects": "1"})
    pages = (data.get("query") or {}).get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list) or not pages or not isinstance(pages[0], dict):
        return None
    p = pages[0]
    text = _cut(p.get("extract"))
    if not text:
        return None
    link = str(p.get("fullurl") or "")
    return {"title": str(p.get("title") or query)[:120], "text": text,
            "url": link if re.fullmatch(r"https://[\w.\-]+/\S{1,400}", link) else ""}


async def online(q):
    """The online Wikipedia's answer for q: (text or None, ref or None)."""
    first = base()
    found = await lookup(first, q)
    if not found and first == DEFAULT_URL:
        first = FALLBACK_URL
        found = await lookup(first, q)
    if not found:
        return None
    k = "w" + hashlib.sha1(f"{first}/{found['title']}".encode()).hexdigest()[:10]
    if k not in _online_refs and len(_online_refs) >= kiwix.MAX_REFS:
        for x in list(_online_refs)[:kiwix.MAX_REFS // 4]:
            _online_refs.pop(x, None)
    _online_refs[k] = (first, found["title"])
    return (f"Wikipedia, Artikel „{found['title']}“ [article: {k}]: {found['text']}"
            + (f" (Quelle: {found['url']})" if found["url"] else ""))


_online_refs = {}


async def search(query, uid=None, use_online=True):
    """A fixed sentence for the model: the article's intro, or why there is none. With uid the own
    Kiwix (kiwix.usable) is asked first."""
    q = _query(query)
    if len(q) < 2:
        return "Kein Suchbegriff angegeben."
    use_kiwix = bool(uid and kiwix.usable(uid))
    key = (base() if use_online else "", "kiwix" if use_kiwix else "", q.lower())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    out, why = None, ""
    if use_kiwix:
        try:
            found = await kiwix.wiki_lookup(q)
            if found:
                out = (f"Aus dem eigenen Kiwix-Archiv ({kiwix.label(found['book'])}), Artikel „{found['title']}“ "
                       f"[article: {found['ref']}]: {found['text']}")
        except (httpx.HTTPError, ValueError) as e:
            why = f" Das eigene Kiwix-Archiv antwortet nicht ({type(e).__name__})."
            print("kiwix: wikipedia nicht erreichbar", type(e).__name__, flush=True)
    if out is None and use_online:
        try:
            out = await online(q)
        except (httpx.HTTPError, ValueError) as e:
            if not use_kiwix:
                raise
            return f"Weder das Kiwix-Archiv noch die Wikipedia haben gerade einen Artikel zu „{q}“ ({type(e).__name__})."
    if out is None:
        return f"Wikipedia hat keinen Artikel zu „{q}“.{why} Nimm web_search, wenn es angeboten ist."
    if len(_cache) >= MAX_CACHE:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:MAX_CACHE // 4]:
            _cache.pop(k, None)
    _cache[key] = (time.time(), out)
    return out


async def online_more(k, part):
    """Part 1..3 of an online Wikipedia article named before."""
    hit = _online_refs.get(k)
    if not hit:
        return "Diesen Artikel kenne ich nicht; suche ihn zuerst mit wikipedia."
    url, title = hit
    data = await _get(url, {"action": "query", "format": "json", "formatversion": "2", "titles": title,
                            "prop": "extracts", "explaintext": "1", "redirects": "1"})
    pages = (data.get("query") or {}).get("pages") if isinstance(data, dict) else None
    text = str(pages[0].get("extract") or "") if isinstance(pages, list) and pages and isinstance(pages[0], dict) else ""
    got = kiwix.parts(re.sub(r"\s+", " ", re.sub(r"=+[^=\n]{1,120}=+", " ", text[:60_000])))
    if part < 1 or part > len(got):
        return f"Vom Artikel „{title}“ gibt es nur {len(got)} Teil(e) zum Vorlesen; mehr lese ich nicht."
    return f"Wikipedia, Artikel „{title}“, Teil {part} von {len(got)}: {got[part - 1]}"


# ---------------------------------------------------------------- the assistant's tool
TOOL = {"type": "function", "function": {
    "name": "wikipedia",
    "description": "Encyclopedia knowledge from Wikipedia: what something is, who someone was, terms, places, "
                   "history, science. Returns the intro of the best matching article. Not for news or anything current.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "the thing, person or term, e.g. 'Quasar' or 'Ada Lovelace'"}},
        "required": ["query"]}}}
HINT = ("Für Wissensfragen (was etwas ist, wer jemand war, Begriffe, Orte, Geschichte, Natur, Technik) rufe zuerst "
        "wikipedia auf und antworte kurz aus dem Artikel. Für Aktuelles (Nachrichten, Ergebnisse, Preise, "
        "Öffnungszeiten) nimm die Websuche.")
MORE = {"type": "function", "function": {
    "name": "article_more",
    "description": "Reads on in an article that wikipedia or archive_search named before (its [article: …] id): "
                   "part 1 is the start, at most part 3. Only when the person wants to hear more.",
    "parameters": {"type": "object", "properties": {
        "article": {"type": "string", "description": "the id from [article: …], e.g. 'k1a2b3c4d5e'"},
        "part": {"type": "integer", "description": "1, 2 or 3; usually 2 for 'erzähl mehr'"}},
        "required": ["article", "part"]}}}
ARCHIVE = {"type": "function", "function": {
    "name": "archive_search",
    "description": "Full-text search in the person's own offline archive (Kiwix: Wikipedia, travel guides, "
                   "handbooks, manuals, books). Works without internet. Returns the best article's start and "
                   "further hits. Not for news or anything current.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "search words, e.g. 'Sauerteig ansetzen'"},
        "book": {"type": "string", "description": "optional: only this book (its name)"}},
        "required": ["query"]}}}
ARCHIVE_HINT = ("Mit archive_search suchst du im eigenen Offline-Archiv (Kiwix) nach Anleitungen, Reiseführern und "
                "Nachschlagewerken. Sagt der Nutzer „erzähl mehr“, lies mit article_more den nächsten Teil des "
                "Artikels. Nenne bei Antworten aus dem Archiv kurz die Quelle.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own"):
        return None
    online_ok, own = usable(who["id"]), kiwix.usable(who["id"])
    if not online_ok and not own:
        return None
    tools, hint = [TOOL, MORE], HINT
    if own:
        tools.append(ARCHIVE)
        hint += " " + ARCHIVE_HINT
    return {"tools": tools, "hint": hint, "outside": {"wikipedia", "article_more", "archive_search"},
            "filler": {"wikipedia": ("Ich schaue in der Wikipedia nach.", "Let me check Wikipedia."),
                       "archive_search": ("Ich schaue in deinem Archiv nach.", "Let me check your archive.")}}


async def tool(name, args, ctx):
    uid = (ctx.get("who") or {}).get("id")
    try:
        if name == "article_more":
            try:
                part = int(args.get("part") or 2)
            except (TypeError, ValueError):
                part = 2
            k = str(args.get("article") or "").strip()[:20]
            if k.startswith("w") and usable(uid):
                return await online_more(k, part)
            if not kiwix.usable(uid):
                return "Weiterlesen geht hier nicht."
            return await kiwix.more(k, part)
        if name == "archive_search":
            if not kiwix.usable(uid):
                return "Das Archiv ist für dieses Profil aus."
            q = _query(args.get("query"))
            if len(q) < 2:
                return "Kein Suchbegriff angegeben."
            text, _ = await kiwix.search(q, _query(args.get("book"))[:120])
            return text
        return await search(args.get("query"), uid, use_online=usable(uid))
    except (httpx.HTTPError, ValueError) as e:
        where = "Wikipedia" if name == "wikipedia" and not kiwix.usable(uid) else "Das Archiv"
        return f"{where} ist gerade nicht erreichbar ({type(e).__name__})."


async def briefing(uid, zone=None):
    return ""
