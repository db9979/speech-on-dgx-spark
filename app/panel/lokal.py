"""Erst lokal suchen (V01.0.264, plan plaene/erst-lokal.md): before anything goes outside, the panel looks in
the person's own sources itself. Off until the admin allows it (chat.local_first) and the profile switches it
on for itself (setting local_first). Guests never (they have no own sources).

A fixed rule (classify) sorts the person's own latest message, never the model:
- "extern": asks for the web in so many words, weather, trains, parcels, news, prices, anything current.
  Nothing changes, no delay.
- "lokal": names an own source ("in meinen Unterlagen", "im Archiv", "haben wir besprochen"). The web search
  is left out of this answer; the person can ask for it in a new message.
- "wissen": any other question with words to look up. The quick look (run) asks the own and shared documents
  (full text; meaning search only when that model already runs and is free), the own Kiwix and the earlier
  conversations at the same time, for at most chat.local_first_ms (200 to 1500, default 400). What is not
  back by then is not waited for. Good hits (at most MAX_HITS, MAX_HIT_CHARS each) go to the model in the
  first round as a tool result, wrapped as outside text: data, never an instruction, and the answer is
  locked like one made from a web page (no switching, saving, reminders).
- "": anything else (switching, lists, mail, small talk ...). Nothing changes.

Which sources a person gets is exactly what the tools of this turn offer (document_search, archive_search,
history_search): a voice that is not the owner's, Telegram without personal data, a guest get none of them.

Web after documents: an answer that read the person's documents normally cannot search the web (a document
could carry its text away in a query). With this switch on the search stays possible, but the panel sends the
person's own words of this message (own_words), never what the model writes (chat_tools.py). After e-mail
the web stays locked as before.

Journal (Zustand -> Logs, area "Wissen"): one "lokal:" line per question with the class, hits per source, the
time and what happens next; never the question or what was found.
"""
import asyncio
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import documents
import guard
import kiwix
import profiles
import recall
from common import load_config
from core import auth

router = APIRouter()

MS_RANGE = (200, 1500)
DEFAULT_MS = 400
MAX_HITS = 3
MAX_HIT_CHARS = 500
COVER = 0.6                 # share of the question's words a passage must contain
MAX_TEST = 500
SOURCES = {"docs": "document_search", "kiwix": "archive_search", "history": "history_search"}
LABELS = {"docs": "Dokumente", "kiwix": "Archiv", "history": "Verlauf"}

# words that only ask, they say nothing about what is asked for ("Wie hoch ist die Zugspitze?" -> zugspitze)
_ASK = """wer wen wem wessen was wie wo woher wohin wann warum wieso weshalb welche welcher welches welchen welchem
ist sind war waren bin bist hat haben hatte hatten gibt gab kann kannst können konnte soll sollte muss müssen
eigentlich denn mal bitte doch genau ungefähr etwa erklär erkläre erklären erzähl erzähle erzählen sag sage sagen
weißt weisst kennst über ueber mir mich uns dir dich hoch lang groß gross alt weit viel viele schwer tief breit
schnell heißt heisst bedeutet bedeutung ich du mein meine meinen meinem meiner dein deine unser unsere man macht mache machen funktioniert funktionieren
geht gehen gut beste besten richtig dauert einfach steht stehen stand the what who how where when why which does did tell me about explain"""
ASK_WORDS = set(documents._terms(_ASK)) | set(_ASK.split())
# the person names an own source: then only there
LOCAL = re.compile(r"(?i)\b(mein\w* (dokument\w*|unterlage\w*|datei\w*|pdfs?|papier\w*|vertr[aä]g\w*|rechnung\w*|"
                   r"versicherung\w*|brief\w*|notiz\w*|ordner\w*|archiv\w*|aufzeichnung\w*)|in den (dokumenten|unterlagen)|"
                   r"hochgeladen\w*|kiwix|offline-?archiv\w*|im archiv|nachschlagewerk\w*|"
                   r"(haben|hatten) wir .{0,40}(gesprochen|geredet|besprochen)|hast du (mir )?(gesagt|erzählt)|"
                   r"letzte[ns]? mal|neulich|weißt du noch|weisst du noch)\b")
# clearly outside: current things the own sources cannot know
EXTERN = re.compile(r"(?i)\b(aktuell\w*|neueste\w*|neuste\w*|heute|heutige\w*|gestern|morgen|übermorgen|gerade|derzeit|"
                    r"zurzeit|momentan|diese[nrms]? (woche|monat|jahr)|letzte[nrms]? (woche|monat|nacht)|live|"
                    r"nachrichten|news|schlagzeile\w*|preis\w*|kostet|kurs\w*|aktie\w*|börse\w*|bitcoin|wahl\w*|"
                    r"umfrage\w*|öffnungszeit\w*|geöffnet|stau\w*|verkehrslage|20[2-9]\d|latest|today|yesterday|"
                    r"current\w*|price\w*)\b")
EXTERN_GROUPS = {"websuche", "wetter", "bahn", "paket"}
LOCAL_ONLY = ("Der Nutzer fragt nach seinen eigenen Quellen: such nur dort (Dokumente, Archiv, frühere Gespräche). "
              "Ins Internet gehst du in dieser Antwort nicht. Steht dort nichts, sag das; will er im Web suchen, "
              "soll er es in einer neuen Nachricht sagen.")
HEAD = ("Vor jeder Suche draußen hat das Panel in den eigenen Quellen nachgesehen (eigene Unterlagen, eigenes "
        "Kiwix-Archiv, frühere Gespräche). Beantwortet das die Frage, antworte daraus und sag am Anfang in einem "
        "halben Satz, woher es stammt („In deinen Unterlagen …“, „Laut deinem Archiv …“, „Wir hatten am … darüber "
        "gesprochen …“). Passt es nicht zur Frage, nenne es nicht. Reicht es nicht und web_search ist angeboten, "
        "suche im Web und sag kurz, dass lokal nichts Passendes war. Zeitlose Allgemeinfragen darfst du aus eigenem "
        "Wissen beantworten. Mit article_more liest du einen Archiv-Artikel weiter.")


def ccfg():
    return load_config().get("chat", {})


def admin_on(cfg=None):
    return (cfg if cfg is not None else ccfg()).get("local_first", False) is True


def on(cfg, who):
    """The admin's and the profile's own switch (never for guests, never from the admin's presets)."""
    return bool(who and admin_on(cfg) and profiles.settings(who["id"]).get("local_first") is True)


def budget(cfg):
    ms = cfg.get("local_first_ms", DEFAULT_MS)
    return ms if isinstance(ms, int) and not isinstance(ms, bool) and MS_RANGE[0] <= ms <= MS_RANGE[1] else DEFAULT_MS


def _split(text):
    """[(word as said, stem)] of the words worth looking up, without the ones that only ask."""
    out, seen = [], set()
    for w in documents._WORD.findall(str(text or "")[:2000]):
        st = documents._terms(w)
        if st and st[0] not in ASK_WORDS and w.lower() not in ASK_WORDS and st[0] not in seen:
            seen.add(st[0])
            out.append((w, st[0]))
    return out[:12]


def terms(text):
    """The stems worth looking up (like the document search stems them), for comparing."""
    return [st for _, st in _split(text)]


def query(text):
    """The same words as said, for the searches ("Albert Einstein", not the stems)."""
    return " ".join(w for w, _ in _split(text))


def cover(words, text):
    """Share of the words that occur in the text."""
    ws = set(words)
    return len(ws & set(documents._terms(text))) / len(ws) if ws else 0.0


def title_fits(title, words):
    """An article title that names what is asked ("Albert Einstein" for "Wer war Einstein?")."""
    tw = set(documents._terms(title)) - ASK_WORDS
    both = tw & set(words)
    return bool(both) and len(both) / len(tw) >= 0.5


def classify(text, route, tool_words=""):
    """(class, reason): "extern", "lokal", "wissen" or "" (see the module doc). Only the person's own words;
    the reason names a rule, never words of the question."""
    import chat
    text = str(text or "")[:2000]
    if not text.strip() or chat.SMALLTALK.fullmatch(text):
        return "", "Plaudern"
    if chat.needed(text, {"web_search"}, tool_words):
        return "extern", "Websuche verlangt"
    if LOCAL.search(text):
        return "lokal", "eigene Quelle genannt"
    groups = set(route.names) & EXTERN_GROUPS
    if groups:
        return "extern", "+".join(sorted(groups))
    if EXTERN.search(text):
        return "extern", "Aktuelles"
    if route.names and not set(route.names) <= {"dokument", "wikipedia"}:
        return "", route.label()
    if not terms(text):
        return "", "keine Suchwörter"
    return "wissen", "Wissensfrage"


def sources(offered):
    """The sources this turn may look in: exactly the ones whose tools it offers."""
    return [k for k, tool in SOURCES.items() if tool in offered]


def own_words(text):
    """The person's own words of this message as a web query (printable, one line, at most 120 characters)."""
    text = str(text or "").replace("[Codewort]", " ")
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>{}\[\]|]", " ", text)).strip()[:120]


def _cut(text, n=MAX_HIT_CHARS):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


# ---------------------------------------------------------------- the sources
async def _docs(uid, q, words):
    import docembed
    import wissen
    semantic = bool(docembed.status().get("running")) and not docembed._busy()
    hits = await wissen.search(uid, q, k=MAX_HITS, semantic=semantic)
    return [{"src": "docs", "title": "Unterlagen: " + wissen.where(h), "text": _cut(h["text"])}
            for h in hits if cover(words, h["name"] + " " + h["text"]) >= COVER]


def _history(uid, words, skip):
    return [{"src": "history", "title": f"früheres Gespräch vom {recall._day(p['updated'])}",
             "text": _cut(f"Frage: {p['q'][:300]} Antwort: {p['a']}")}
            for _, p in recall.scored(uid, words, skip, MAX_HITS) if cover(words, p["q"] + " " + p["a"]) >= COVER]


async def _kiwix(q, words):
    books = (await kiwix.chosen())[:kiwix.MAX_SEARCH_BOOKS]
    if not books:
        return []
    pick = None
    got = await asyncio.gather(*(kiwix.suggest(b["id"], q) for b in books), return_exceptions=True)
    for b, res in zip(books, got):
        for title, path in res if isinstance(res, list) else []:
            if title_fits(title, words):
                pick = (b, title, path)
                break
        if pick:
            break
    if not pick:
        found = await asyncio.gather(*(kiwix.fulltext(b["id"], q) for b in books), return_exceptions=True)
        if all(isinstance(r, Exception) for r in got + found):
            raise kiwix.Refused("Kiwix not reachable")
        for b, res in zip(books, found):
            for title, path, snip in res if isinstance(res, list) else []:
                if title_fits(title, words) or cover(words, title + " " + snip) >= COVER:
                    pick = (b, title, path)
                    break
            if pick:
                break
    if not pick:
        return []
    b, title, path = pick
    parts = await kiwix.article(b["id"], path)
    if not parts:
        return []
    return [{"src": "kiwix", "title": f"Archiv: {kiwix.label(b)}, Artikel „{title}“",
             "text": _cut(parts[0]), "ref": kiwix.ref(b["id"], path, title)}]


def _quiet(task):
    """A source that came back too late: its result or error is dropped without a warning."""
    if not task.cancelled():
        task.exception()


async def look(uid, text, srcs, ms, skip=None):
    """The quick look: {"hits", "n", "late", "err", "ms"}. Never longer than ms (late sources are not
    waited for; they end on their own timeouts and are dropped)."""
    t0 = time.monotonic()
    words, q = terms(text), query(text)
    out = {"hits": [], "n": {}, "late": [], "err": [], "ms": 0}
    jobs = {}
    if words:
        if "docs" in srcs:
            jobs["docs"] = asyncio.ensure_future(_docs(uid, q, words))
        if "history" in srcs:
            jobs["history"] = asyncio.ensure_future(asyncio.to_thread(_history, uid, words, skip))
        if "kiwix" in srcs:
            jobs["kiwix"] = asyncio.ensure_future(_kiwix(q, words))
    if jobs:
        await asyncio.wait(list(jobs.values()), timeout=ms / 1000)
    found = {}
    for k, job in jobs.items():
        if not job.done():
            out["late"].append(k)
            job.add_done_callback(_quiet)
        elif job.exception() is not None:
            out["err"].append(k)
            print(f"lokal: {LABELS[k]} nicht erreichbar:", type(job.exception()).__name__, flush=True)
        else:
            found[k] = job.result()
            out["n"][k] = len(found[k])
    out["hits"] = (found.get("docs", [])[:2] + found.get("kiwix", [])[:1] + found.get("history", [])[:1])[:MAX_HITS]
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


def log_line(kind, why, srcs, res=None):
    """One journal line (area "Wissen"): class, hits per source, time, what happens next. Never the question."""
    head = f"lokal: Klasse {kind or 'keine'} ({why})"
    if res is None:
        nxt = ("nur eigene Quellen, Web in dieser Antwort aus" if kind == "lokal" else
               "direkt, kein Vorlauf" if kind == "extern" else "kein Vorlauf (keine eigene Quelle)" if kind == "wissen"
               else "unverändert")
        return f"{head} | weiter: {nxt}"
    counts = ", ".join(f"{LABELS[k]} " + (str(res['n'][k]) if k in res["n"] else "zu langsam" if k in res["late"]
                                           else "Fehler") for k in SOURCES if k in srcs)
    nxt = "Treffer an das Modell" if res["hits"] else "lokal nichts, Modell entscheidet (eigenes Wissen oder Web)"
    return f"{head} | {counts} | {res['ms']} ms | weiter: {nxt}"


async def run(uid, text, srcs, ms, skip=None):
    """look() for a chat turn, with its journal line; never raises."""
    try:
        res = await look(uid, text, srcs, ms, skip)
    except Exception as e:      # a source broke in an unexpected way: the answer goes on as without it
        print("lokal: Vorlauf fehlgeschlagen:", type(e).__name__, flush=True)
        return {"hits": [], "n": {}, "late": [], "err": list(srcs), "ms": 0}
    print(log_line("wissen", "Wissensfrage", srcs, res), flush=True)
    return res


def block(hits):
    """The hits as one text (each with where it comes from); outside text, chat wraps it as data."""
    return "\n\n".join(f"[{h['title']}" + (f" [article: {h['ref']}]" if h.get("ref") else "") + f"]\n{h['text']}"
                       for h in hits)


# ---------------------------------------------------------------- "Erst lokal testen" (Zustand -> Prüfen)
@router.post("/api/admin/lokal/test", dependencies=[Depends(auth)])
async def lokal_test(request: Request):
    """One sentence through the rule and the quick look: class, sources, hits (titles only) and times. Looks in
    the documents and conversations of the profile signed in in this browser, if any, and in the Kiwix when the
    admin set it up. Nothing stored, nothing logged."""
    guard.limit(request, "lokal", admin=True)
    body = await request.json()
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEST:
        raise HTTPException(400, f"text: 1 bis {MAX_TEST} Zeichen")
    import intent
    import wissen
    cfg = ccfg()
    kind, why = classify(text, intent.classify(text, cfg.get("tool_words", ""), cfg.get("route_words", "")),
                         cfg.get("tool_words", ""))
    who = profiles.current(request)
    srcs = []
    if who and cfg.get("documents", True) and (documents.list_docs(who["id"], used_only=True) or wissen.shared_list(who["id"])):
        srcs.append("docs")
    if kiwix.admin_on():
        srcs.append("kiwix")
    if who and cfg.get("memory", True) and cfg.get("history", True):
        srcs.append("history")
    out = {"kind": kind, "why": why, "words": query(text).split(), "profile": who["name"] if who else "", "sources": srcs,
           "ms": 0, "n": {}, "late": [], "err": [], "hits": [], "budget": budget(cfg)}
    if kind == "wissen" and srcs:
        res = await look(who["id"] if who else None, text, srcs, budget(cfg))
        out.update(ms=res["ms"], n=res["n"], late=res["late"], err=res["err"],
                   hits=[{"src": h["src"], "title": h["title"], "chars": len(h["text"])} for h in res["hits"]])
    return out
