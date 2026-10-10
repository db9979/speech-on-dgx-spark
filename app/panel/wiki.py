"""Wikipedia straight away: for "Was ist ...?" or "Wer war ...?" the panel asks Wikipedia for the best
matching article and hands its short intro to the model, without SearXNG and without reading whole
pages. Less text before the first word, so the answer starts sooner. Off until the admin allows it
(chat.wiki) and a profile switches it on for itself (setting wiki_on). Guests never.

Only the search words leave the Spark. Answers are kept 24 hours in memory (at most MAX_CACHE
entries), so the same question again needs no request. The article text is outside text: it is
handed over as data and locks switching and saving in the same answer like a web page.
"""
import json
import re
import time

import httpx

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


async def search(query):
    """A fixed sentence for the model: the article's intro, or why there is none."""
    q = _query(query)
    if len(q) < 2:
        return "Kein Suchbegriff angegeben."
    first = base()
    key = (first, q.lower())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    found = await lookup(first, q)
    if not found and first == DEFAULT_URL:
        found = await lookup(FALLBACK_URL, q)
    if found:
        out = f"Wikipedia, Artikel „{found['title']}“: {found['text']}" + (f" (Quelle: {found['url']})" if found["url"] else "")
    else:
        out = f"Wikipedia hat keinen Artikel zu „{q}“. Nimm web_search, wenn es angeboten ist."
    if len(_cache) >= MAX_CACHE:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:MAX_CACHE // 4]:
            _cache.pop(k, None)
    _cache[key] = (time.time(), out)
    return out


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


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or not usable(who["id"]):
        return None
    return {"tools": [TOOL], "hint": HINT, "outside": {"wikipedia"},
            "filler": {"wikipedia": ("Ich schaue in der Wikipedia nach.", "Let me check Wikipedia.")}}


async def tool(name, args, ctx):
    try:
        return await search(args.get("query"))
    except (httpx.HTTPError, ValueError) as e:
        return f"Wikipedia ist gerade nicht erreichbar ({type(e).__name__})."


async def briefing(uid, zone=None):
    return ""
