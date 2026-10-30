"""Erst lokal suchen (V01.0.264, plan plaene/erst-lokal.md): before anything goes outside, the panel looks in
the person's own sources itself. Off until the admin allows it (chat.local_first); then
on for every profile unless the admin blocks one (Personen und Geräte → Gesperrte Funktionen). Guests never (they have no own sources).

A fixed rule (classify) sorts the person's own latest message, never the model:
- "extern": asks for the web in so many words, weather, trains, parcels, news, prices, anything current.
  Nothing changes, no delay.
- "lokal": names an own source ("in meinen Unterlagen", "im Archiv", "haben wir besprochen"). The web search
  is left out of this answer; the person can ask for it in a new message.
- "wissen": any other question with words to look up. The quick look (run) asks the own and shared documents
  (full text; meaning search only when that model already runs and is free), the own Kiwix and the earlier
  conversations at the same time, for at most chat.local_first_ms (200 to 1500, default 400); the Kiwix has its
  own limit chat.local_first_kiwix_ms (200 to 2000, default 900), a big archive often needs longer than the own
  documents (Dominik 2026-10-21). What is not back by its limit is not waited for. Good hits (at most MAX_HITS, MAX_HIT_CHARS each;
  from a document the part around the question's words, from a table its head and the fitting rows: excerpt) go to the model in the
  first round as a tool result, wrapped as outside text: data, never an instruction, and the answer is
  locked like one made from a web page (no switching, saving, reminders).
- "": anything else (switching, lists, mail, small talk ...). Nothing changes.

Which sources a person gets is exactly what the tools of this turn offer (document_search, archive_search,
history_search, and fund_suche for Finden's clear sources since its Stufe D): a voice that is not the owner's, Telegram without personal data, a guest get none of them.

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
import features
from common import edit_distance, load_config
from core import auth

router = APIRouter()

MS_RANGE = (200, 1500)
DEFAULT_MS = 400
KIWIX_RANGE = (200, 2000)
DEFAULT_KIWIX_MS = 900
MAX_HITS = 3
MAX_HIT_CHARS = 500
COVER = 0.6                 # share of the question's words a passage must contain
PREFIX = 4                  # letters of a long word kept when the title lookup completes it (variants)
MAX_VARIANTS = 3            # further title lookups per book when the whole question found no title
MAX_TEST = 500
# "fund": Finden's index (fund.py, Stufe D), only its clear sources without an index of their own here (Wissensbuch,
# lists, reminders, pictures, songs: fund.LOKAL); documents and conversations come through their own source, mail,
# appointments and contacts never in the quick look (sealed, and a stranger's mail is no answer to a knowledge question)
SOURCES = {"docs": "document_search", "kiwix": "archive_search", "history": "history_search", "fund": "fund_suche"}
LABELS = {"docs": "Dokumente", "kiwix": "Archiv", "history": "Verlauf", "fund": "Finden"}

# words that only ask, they say nothing about what is asked for ("Wie hoch ist die Zugspitze?" -> zugspitze)
_ASK = """wer wen wem wessen was wie wo woher wohin wann warum wieso weshalb welche welcher welches welchen welchem
ist sind war waren bin bist hat haben hatte hatten gibt gab kann kannst können konnte soll sollte muss müssen
eigentlich denn mal bitte doch genau ungefähr etwa erklär erkläre erklären erzähl erzähle erzählen sag sage sagen
weißt weisst kennst über ueber mir mich uns dir dich hoch lang groß gross alt weit viel viele schwer tief breit
schnell heißt heisst bedeutet bedeutung ich du mein meine meinen meinem meiner dein deine unser unsere man macht mache machen funktioniert funktionieren
geht gehen gut beste besten richtig dauert einfach steht stehen stand the what who how where when why which does did tell me about explain
zur zum alles alle etwas mitteilen mitteile erzählst schau schaue nachschauen nachsehen such suche informationen info infos
details archiv kiwix dokumenten unterlagen"""
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
    return features.admin_on("lokal", cfg)


def on(cfg, who):
    """Released by the admin for this profile (never for guests)."""
    return bool(who and admin_on(cfg) and features.allowed("lokal", who["id"]))


def _ms(cfg, key, rng, default):
    ms = cfg.get(key, default)
    return ms if isinstance(ms, int) and not isinstance(ms, bool) and rng[0] <= ms <= rng[1] else default


def budget(cfg):
    """(own documents and conversations, Kiwix) in ms."""
    return (_ms(cfg, "local_first_ms", MS_RANGE, DEFAULT_MS),
            _ms(cfg, "local_first_kiwix_ms", KIWIX_RANGE, DEFAULT_KIWIX_MS))


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


def same(a, b):
    """Two stems are the same word; a long word may be mistyped by a letter (6 to 9 letters) or two (10 and more):
    „fraunkirch“ is „frauenkirch“ (Dominik 2026-10-21: „was weißt du über die Dresdner Fraunkirche?“ found nothing)."""
    if a == b:
        return True
    n = min(len(a), len(b))
    most = 0 if n < 6 else 1 if n < 10 else 2
    return most > 0 and edit_distance(a, b, most) <= most


def _found(word, terms):
    return word in terms or any(same(word, t) for t in terms)


def cover(words, text):
    """Share of the words that occur in the text (same(): a mistyped long word counts)."""
    ws, ts = set(words), set(documents._terms(text))
    return sum(_found(w, ts) for w in ws) / len(ws) if ws else 0.0


def title_fits(title, words):
    """An article title that names what is asked ("Albert Einstein" for "Wer war Einstein?")."""
    tw = set(documents._terms(title)) - ASK_WORDS
    both = [t for t in tw if _found(t, set(words))]
    return bool(both) and len(both) / len(tw) >= 0.5


def fit(title, words):
    """How many of the question's words a fitting title names (0: it does not fit); the best title wins
    („Dresdner Frauenkirche“ before „Dresdner Bank“)."""
    if not title_fits(title, words):
        return 0
    tw = set(documents._terms(title))
    return sum(_found(w, tw) for w in set(words))


def _best(books, results, words):
    """(book, title, path) with the best fitting title of the lookups (results in the order of books × lookups), or None."""
    best, top = None, 0
    per = len(results) // len(books) if books else 1
    for i, res in enumerate(results):
        for title, path in res if isinstance(res, list) else []:
            n = fit(title, words)
            if n > top:
                best, top = (books[i // per], title, path), n
    return best


def variants(text):
    """Further title lookups when the whole question found no title (a mistyped word): every long word alone, and the
    question with a long word cut to its first PREFIX letters at the end, where the suggestion completes it („Dresdner
    Frau…“ for „Dresdner Fraunkirche“). At most MAX_VARIANTS, longest words first; fixed rule, never the model."""
    said = [w for w, _ in _split(text)]
    long = sorted((w for w in said if len(w) >= 2 * PREFIX), key=len, reverse=True)[:2]
    out = []
    for w in long:
        out.append(" ".join([x for x in said if x != w] + [w[:PREFIX]]))
    out += long
    return [q for q in dict.fromkeys(out) if q][:MAX_VARIANTS]


# a short answer to the assistant's question before („Ja“, „Nein danke“, ablauf.short_reply) is never a knowledge
# question of its own (V01.0.804: „Ja“ to a proposed appointment looked up old conversations, the answer spoke of those)
def classify(text, route, tool_words=""):
    """(class, reason): "extern", "lokal", "wissen" or "" (see the module doc). Only the person's own words;
    the reason names a rule, never words of the question."""
    import ablauf
    import chat
    text = str(text or "")[:2000]
    if not text.strip() or chat.SMALLTALK.fullmatch(text):
        return "", "Plaudern"
    if ablauf.short_reply(text):   # „Ja“ to a question before: nothing to look up
        return "", "Antwort auf Rückfrage"
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


def excerpt(text, words, n=MAX_HIT_CHARS):
    """The part of a passage that holds the question's words, at most about n characters (Dominik 2026-10-23:
    the first 500 characters of a table left out the row asked for). A table ("| … |" lines): its head and the
    rows with the rarest of the words (a word in every row, "Karte", counts little; "Durchfall" in one row
    much; rows worth less than half the best are left out), in their order. Other text: the window with the most different words,
    cut at word ends, "…" where it was cut. Without any of the words: the start, as _cut."""
    text = str(text or "")
    lines = [x.strip() for x in text.split("\n") if x.strip()]
    if len(lines) >= 2 and all(x.startswith("|") for x in lines):
        rows = [(i, _hits(x, words)) for i, x in enumerate(lines[1:], 1) if not re.fullmatch(r"[|:\s-]+", x)]
        often = {w: sum(w in h for _, h in rows) for w in words}
        weight = lambda h: sum(1 / often[w] for w in h)  # noqa: E731
        best = sorted((r for r in rows if r[1]), key=lambda r: (-weight(r[1]), r[0]))
        best = [r for r in best if weight(r[1]) * 2 >= weight(best[0][1])]   # never padded with rows that fit little
        keep, size = [], len(lines[0])
        for i, _ in best:
            if size + len(lines[i]) + 1 > n and keep:
                break
            keep.append(i)
            size += len(lines[i]) + 1
        if keep:
            return "\n".join([_cut(lines[0], n)] + [_cut(lines[i], n) for i in sorted(keep)])
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= n:
        return flat
    spots = [(m.start(), st[0]) for m in documents._WORD.finditer(flat)
             if (st := documents._terms(m.group(0))) and any(_found(w, {st[0]}) for w in words)]
    if not spots:
        return _cut(flat, n)
    start = max((max(0, p - n // 4) for p, _ in spots),
                key=lambda a: (len({w for p, w in spots if a <= p < a + n - 4}), -a))
    if start:
        start = flat.find(" ", start) + 1 or start
    piece = flat[start:start + n - 4]
    if start + n - 4 < len(flat):
        piece = piece.rsplit(" ", 1)[0] + " …"
    return ("… " if start else "") + piece


def _hits(text, words):
    """The question's words found in a text."""
    ts = set(documents._terms(text))
    return {w for w in words if _found(w, ts)}


# ---------------------------------------------------------------- the sources
async def _docs(uid, q, words):
    import docembed
    import wissen
    semantic = bool(docembed.status().get("running")) and not docembed._busy()
    hits = await wissen.search(uid, q, k=MAX_HITS, semantic=semantic, keep=False)   # rides along, no keep-awake
    return [{"src": "docs", "title": "Unterlagen: " + wissen.where(h), "text": excerpt(h["text"], words)}
            for h in hits if cover(words, h["name"] + " " + h["text"]) >= COVER]


def _history(uid, words, skip):
    return [{"src": "history", "title": f"früheres Gespräch vom {recall._day(p['updated'])}",
             "text": _cut(f"Frage: {p['q'][:300]} Antwort: {p['a']}")}
            for _, p in recall.scored(uid, words, skip, MAX_HITS) if cover(words, p["q"] + " " + p["a"]) >= COVER]


async def _kiwix(q, words):
    books = kiwix.pick(await kiwix.chosen(), words)
    if not books:
        return []
    got = await asyncio.gather(*(kiwix.suggest(b["id"], q) for b in books), return_exceptions=True)
    pick = _best(books, got, words)
    more = variants(q) if not pick else []
    if more:   # a mistyped word: the long words alone and cut short (variants), same rule for the titles
        tries = await asyncio.gather(*(kiwix.suggest(b["id"], v) for b in books for v in more), return_exceptions=True)
        pick = _best(books, tries, words)
        got += tries
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
             "text": _cut(parts[0]), "ref": kiwix.ref(b["id"], path, title), "source": kiwix.source(b, title, path),
             "date": b.get("date", "")}]


def _fund(uid, q, words):
    import fund
    import frisch
    hits = fund.suche(uid, q, anzahl=MAX_HITS, quellen=fund.LOKAL)
    return [{"src": "fund", "title": f"Finden: {fund.BY_NAME[h['quelle']].de} „{_cut(h['titel'], 80)}“"
             + (f", {frisch.stand(h['wann']).split(',')[0]}" if h.get("wann") else ""),
             "text": _cut(h.get("auszug") or h["titel"])}
            for h in hits if cover(words, h["titel"] + " " + (h.get("auszug") or "")) >= COVER]


def _quiet(task):
    """A source that came back too late: its result or error is dropped without a warning."""
    if not task.cancelled():
        task.exception()


async def look(uid, text, srcs, ms, skip=None):
    """The quick look: {"hits", "n", "late", "err", "ms"}. ms: one limit or (own sources, Kiwix) as budget()
    gives them; never longer than the larger one (late sources are not waited for; they end on their own timeouts
    and are dropped)."""
    ms, kms = ms if isinstance(ms, tuple) else (ms, ms)
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
        if "fund" in srcs:
            jobs["fund"] = asyncio.ensure_future(asyncio.to_thread(_fund, uid, q, words))
    own = [j for k, j in jobs.items() if k != "kiwix"]
    if own:
        await asyncio.wait(own, timeout=ms / 1000)
    if "kiwix" in jobs:     # its own limit, counted from the start like the others
        await asyncio.wait([jobs["kiwix"]], timeout=max(0.0, kms / 1000 - (time.monotonic() - t0)))
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
    out["hits"] = (found.get("docs", [])[:2] + found.get("fund", [])[:1] + found.get("kiwix", [])[:1]
                   + found.get("history", [])[:1])[:MAX_HITS]
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
    kind, why = classify(text, intent.classify_cfg(text, cfg),
                         cfg.get("tool_words", ""))
    who = profiles.current(request)
    srcs = []
    if who and cfg.get("documents", True) and (documents.count_docs(who["id"], used_only=True) or wissen.shared_list(who["id"])):
        srcs.append("docs")
    if kiwix.admin_on():
        srcs.append("kiwix")
    if who and cfg.get("memory", True) and cfg.get("history", True):
        srcs.append("history")
    lim = budget(cfg)
    out = {"kind": kind, "why": why, "words": query(text).split(), "profile": who["name"] if who else "", "sources": srcs,
           "ms": 0, "n": {}, "late": [], "err": [], "hits": [], "budget": lim[0], "kiwix_budget": lim[1]}
    if kind == "wissen" and srcs:
        res = await look(who["id"] if who else None, text, srcs, lim)
        out.update(ms=res["ms"], n=res["n"], late=res["late"], err=res["err"],
                   hits=[{"src": h["src"], "title": h["title"], "chars": len(h["text"])} for h in res["hits"]])
    return out
