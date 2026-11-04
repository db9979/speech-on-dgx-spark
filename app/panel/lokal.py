"""Erst lokal suchen (V01.0.264, plan plaene/erst-lokal.md): before anything goes outside, the panel looks in
the person's own sources itself. Off until the admin allows it (chat.local_first); then
on for every profile unless the admin blocks one (Personen und Geräte → Gesperrte Funktionen). Guests never (they have no own sources).

Which of the person's questions get a quick look is decided by the Quellen-Weiche (quellen.klasse, plan
such-index/zuverlaessig.md, step 3), by fixed rules on the person's own words, never the model:
- "extern": the web, weather, trains, parcels, news, prices, anything current. Nothing changes, no delay.
- "intern": the own data. With Finden released (source "fund") the quick look (run) asks every own source at the
  same time (step 4): Finden's index over mails and attachments, appointments, contacts, documents, NAS, reMarkable,
  conversations, lists and the Wissensbuch (fund.suche with the profile's releases and a Mappe bound to the
  conversation), the own and shared documents (full text; meaning search only when that model already runs and
  is free) and the earlier conversations, for at most chat.local_first_ms (200 to 1500, default 400). An own
  source named in so many words („in meinen Unterlagen“, „laut Angebot“) also leaves the web out of this answer.
- "beides": the same quick look plus the own Kiwix (its own limit chat.local_first_kiwix_ms, 200 to 2000, default
  900, Dominik 2026-10-21) and the panel's own web search with the person's own words of this message (own_words),
  started before anything of the own data is read: no mail text can reach the web.
- "": anything else (switching, small talk, a plain yes ...). Nothing changes.
Without Finden it stays as before step 3: documents, Kiwix and conversations for a question to look up, no web
search by the panel. What is not back by its limit is not waited for. Good hits (at most MAX_HITS across the
sources, round by round, each with its source and date, MAX_HIT_CHARS each; from a document the part around the
question's words, from a table its head and the fitting rows: excerpt) go to the model in the first round as one
tool result, wrapped as outside text: data, never an instruction, and the answer is locked like one made from a web
page (no switching, saving, reminders); a mail or attachment among them locks it like a read mail
(chat.LOCKED_AFTER_MAIL: nothing more to the internet).

Which sources a person gets is exactly what the tools of this turn offer (document_search, archive_search,
history_search, fund_suche, web_search): a voice that is not the owner's, Telegram without personal data, MCP and a
guest get none of them.

Web after documents: an answer that read the person's documents normally cannot search the web (a document
could carry its text away in a query). With this switch on the search stays possible, but the panel sends the
person's own words of this message (own_words), never what the model writes (chat_tools.py); when the panel already
searched them for "beides", that result is used again. After e-mail the web stays locked as before.

Herkunft and „Auch im Internet suchen“ (step 5): under an answer with own hits the panel writes where it comes from,
counted from the hits' sources (herkunft: kinds and numbers only), and for the class intern without the web it keeps
the question's own words for the next message on the same device (web_offer); the chip's fixed words (web_chip) then
search exactly those on the web (chat_turn.prepare, chat_modell.herkunft_und_chip). Never after mail, at the Notaus,
for guests, another voice or MCP.

Journal (Zustand -> Logs, area "Wissen"): one "lokal:" line per question with the class, hits per source, the
time and what happens next ("lokal: Klasse intern (Probe stark) | Probe 3 Treffer 42 ms | …"); never the question or
what was found.
"""
import asyncio
import re
import threading
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
MAX_HITS = 5                # across all sources (plan such-index/zuverlaessig.md, step 4)
MAX_WEB_CHARS = 2000        # of the panel's own web search with the own words ("beides")
MAX_HIT_CHARS = 500
COVER = 0.6                 # share of the question's words a passage must contain
PREFIX = 4                  # letters of a long word kept when the title lookup completes it (variants)
MAX_VARIANTS = 3            # further title lookups per book when the whole question found no title
MAX_TEST = 500
# "fund": Finden's index (fund.py) over every source the profile released (mails and attachments, appointments,
# contacts, documents, NAS, reMarkable, conversations, lists, Wissensbuch …), since step 4 of plan such-index; "web":
# the panel's own web search with the own words (quellen.blick adds it for "beides", never a tool of its own here)
SOURCES = {"docs": "document_search", "kiwix": "archive_search", "history": "history_search", "fund": "fund_suche"}
LABELS = {"docs": "Dokumente", "kiwix": "Archiv", "history": "Verlauf", "fund": "Finden", "web": "Web"}

# words that only ask, they say nothing about what is asked for ("Wie hoch ist die Zugspitze?" -> zugspitze)
_ASK = """wer wen wem wessen was wie wo woher wohin wann warum wieso weshalb welche welcher welches welchen welchem
ist sind war waren bin bist hat haben hatte hatten gibt gab kann kannst können konnte soll sollte muss müssen
eigentlich denn mal bitte doch genau ungefähr etwa erklär erkläre erklären erzähl erzähle erzählen sag sage sagen
weißt weisst kennst über ueber mir mich uns dir dich hoch lang groß gross alt weit viel viele schwer tief breit
schnell heißt heisst bedeutet bedeutung ich du mein meine meinen meinem meiner dein deine unser unsere man macht mache machen funktioniert funktionieren
geht gehen gut beste besten richtig dauert einfach steht stehen stand the what who how where when why which does did tell me about explain
zur zum alles alle etwas mitteilen mitteile erzählst schau schaue nachschauen nachsehen such suche informationen info infos
details archiv kiwix dokumenten unterlagen weiß weiss hieß hiess nochmal wegen beim vom von sich show from get back"""
ASK_WORDS = set(documents._terms(_ASK)) | set(_ASK.split())
LOCAL_ONLY = ("Der Nutzer fragt nach seinen eigenen Quellen: such nur dort (eigene Daten, Dokumente, Archiv, frühere "
              "Gespräche). Ins Internet gehst du in dieser Antwort nicht. Steht dort nichts, sag das; will er im Web "
              "suchen, soll er es in einer neuen Nachricht sagen.")
HEAD = ("Vor jeder Suche draußen hat das Panel in den eigenen Quellen nachgesehen (eigene Mails und Anhänge, Termine, "
        "Kontakte, Unterlagen, Listen, Wissensbuch, eigenes Kiwix-Archiv, frühere Gespräche, soweit freigegeben). "
        "Beantwortet das die Frage, antworte daraus und sag am Anfang in einem halben Satz, woher es stammt („In "
        "deinen Unterlagen …“, „In der Mail vom … schreibt …“, „Laut deinem Archiv …“, „Wir hatten am … darüber "
        "gesprochen …“). Passt es nicht zur Frage, nenne es nicht. Reicht es nicht und web_search ist angeboten, "
        "suche im Web und sag kurz, dass lokal nichts Passendes war. Zeitlose Allgemeinfragen darfst du aus eigenem "
        "Wissen beantworten. Mit article_more liest du einen Archiv-Artikel weiter.")
WEB_ONLY_HEAD = ("Der Nutzer hat „Auch im Internet suchen“ gewählt: Das Panel hat mit seinen eigenen Worten der Frage "
                 "im Web gesucht (Ergebnis unten, mit Quellen). Antworte daraus und sag, was woher stammt.")
WEB_HEAD = ("Dazu hat das Panel mit den eigenen Worten der Frage im Web gesucht (Ergebnis unten, mit Quellen). Nimm "
            "eigene Daten und Web zusammen und sag, was woher stammt.")


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
async def _docs(uid, q, words, nur=None):
    import docembed
    import wissen
    semantic = bool(docembed.status().get("running")) and not docembed._busy()
    hits = await wissen.search(uid, q, k=MAX_HITS, semantic=semantic, keep=False,    # rides along, no keep-awake
                               only=set(nur[0]) if nur is not None else None)       # a Mappe: only its documents
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


def fund_text(h):
    """A Finden hit as one text for comparing with the question's words: title, excerpt, fields, attachments, tags."""
    parts = [h.get("titel") or "", h.get("auszug") or ""]
    parts += [str(v) for v in (h.get("felder") or {}).values() if isinstance(v, (str, int, float))]
    parts += [str(a.get("titel") or "") for a in h.get("anhaenge") or []]
    parts += [str(t.get("wert") or "") for t in h.get("tags") or []]
    return " ".join(parts)


def _fund(uid, q, words, nur=None):
    """Finden over every source this profile released (fund.quellen_fuer); a Mappe bound to the conversation: only its
    entries. Each hit with its source and date (fund._line); a mail or attachment is marked "mail"."""
    import fund
    now = time.time()
    hits = fund.suche(uid, q, anzahl=MAX_HITS, nur=nur)
    return [{"src": "fund", "quelle": h["quelle"], "mail": h["quelle"] in fund.MAIL_Q,
             "title": f"Finden: {fund.BY_NAME[h['quelle']].de}", "text": _cut(fund._line(h, now))}
            for h in hits if cover(words, fund_text(h)) >= COVER]


async def _web(ccfg, query, text):
    """The panel's own web search with the person's own words ("beides"): one hit with the result and its sources."""
    import chat
    import dienstwacht
    import frisch
    try:
        result, items = await chat.web_search_own(ccfg, query, frisch.zeitraum(text, query), frisch.news(text, query))
    except Exception:
        dienstwacht.saw("web")   # like the tool: the service watch hears of it
        raise
    return [{"src": "web", "title": "Websuche mit den eigenen Worten der Frage", "text": _cut(result, MAX_WEB_CHARS),
             "sources": items}]


def _quiet(task):
    """A source that came back too late: its result or error is dropped without a warning."""
    if not task.cancelled():
        task.exception()


# documents and conversations also come through Finden: a hit there is left out when their own source found something
_DOC_Q = ("dokument", "nas", "remarkable")


async def look(uid, text, srcs, ms, skip=None, nur=None, ccfg=None):
    """The quick look: {"hits", "web", "n", "late", "err", "ms", "mail"}. ms: one limit or (own sources, Kiwix and
    web) as budget() gives them; never longer than the larger one (late sources are not waited for; they end on
    their own timeouts and are dropped). "web" (with ccfg) searches the person's own words of this message, fixed
    and started before any own source is read, so nothing found here can go into it. nur: a Mappe (documents,
    Wissensbuch pages)."""
    ms, kms = ms if isinstance(ms, tuple) else (ms, ms)
    t0 = time.monotonic()
    web_q = own_words(text)          # the person's own words, before anything is read
    text = str(text or "").replace("[Codewort]", " ")   # the code word's place holder is no word to look up
    words, q = terms(text), query(text)
    out = {"hits": [], "web": None, "n": {}, "late": [], "err": [], "ms": 0, "mail": False, "nur_web": list(srcs) == ["web"]}
    jobs = {}
    if "web" in srcs and web_q and ccfg is not None:
        jobs["web"] = asyncio.ensure_future(_web(ccfg, web_q, text))
    if words:
        if "docs" in srcs:
            jobs["docs"] = asyncio.ensure_future(_docs(uid, q, words, nur))
        if "history" in srcs:
            jobs["history"] = asyncio.ensure_future(asyncio.to_thread(_history, uid, words, skip))
        if "kiwix" in srcs:
            jobs["kiwix"] = asyncio.ensure_future(_kiwix(q, words))
        if "fund" in srcs:
            jobs["fund"] = asyncio.ensure_future(asyncio.to_thread(_fund, uid, q, words, nur))
    own = [j for k, j in jobs.items() if k not in ("kiwix", "web")]
    if own:
        await asyncio.wait(own, timeout=ms / 1000)
    far = [jobs[k] for k in ("kiwix", "web") if k in jobs]
    if far:     # their own limit, counted from the start like the others
        await asyncio.wait(far, timeout=max(0.0, kms / 1000 - (time.monotonic() - t0)))
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
    fh = found.get("fund", [])
    if found.get("docs"):
        fh = [h for h in fh if h["quelle"] not in _DOC_Q]
    if found.get("history"):
        fh = [h for h in fh if h["quelle"] != "chat"]
    # across the sources, round by round: Finden's best, a passage of the documents, a conversation, the archive
    lists = [fh, found.get("docs", []), found.get("history", []), found.get("kiwix", [])]
    for i in range(MAX_HITS):
        out["hits"] += [x[i] for x in lists if len(x) > i]
    out["hits"] = out["hits"][:MAX_HITS]
    out["web"] = (found.get("web") or [None])[0]
    out["mail"] = any(h.get("mail") for h in out["hits"])
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


NEXT = {"intern": "eigene Quellen", "beides": "eigene Quellen und Web mit eigenen Worten", "extern": "direkt, kein Vorlauf"}


def log_line(kind, why, srcs, res=None, info=None):
    """One journal line (area "Wissen"): class and its reasons (fixed words, quellen.GRUENDE), the probe's hits and
    time, hits per source, time, what happens next. Never the question."""
    why = "+".join(why) if isinstance(why, (list, tuple)) else str(why or "")
    head = f"lokal: Klasse {kind or 'keine'} ({why})"
    if info and "ms" in info:
        head += f" | Probe {info.get('probe', 0)} Treffer {info['ms']} ms"
    if res is None:
        nxt = ("nur eigene Quellen, Web in dieser Antwort aus" if "eigene Quelle" in why else
               "direkt, kein Vorlauf" if kind == "extern" else "kein Vorlauf (keine eigene Quelle)" if kind
               else "unverändert")
        return f"{head} | weiter: {nxt}"
    counts = ", ".join(f"{LABELS[k]} " + (str(res['n'][k]) if k in res["n"] else "zu langsam" if k in res["late"]
                                           else "Fehler") for k in LABELS if k in srcs)
    nxt = ("Treffer an das Modell" + (", Mail gelesen" if res.get("mail") else "") if res["hits"] or res.get("web")
           else "lokal nichts, Modell entscheidet (eigenes Wissen oder Web)")
    return f"{head} | {counts} | {res['ms']} ms | weiter: {nxt}"


async def run(uid, text, srcs, ms, skip=None, kind="beides", why=("ohne Probe",), info=None, nur=None, ccfg=None):
    """look() for a chat turn, with its journal line; never raises."""
    try:
        res = await look(uid, text, srcs, ms, skip, nur, ccfg)
    except Exception as e:      # a source broke in an unexpected way: the answer goes on as without it
        print("lokal: Vorlauf fehlgeschlagen:", type(e).__name__, flush=True)
        return {"hits": [], "web": None, "n": {}, "late": [], "err": list(srcs), "ms": 0, "mail": False}
    print(log_line(kind, why, srcs, res, info), flush=True)
    return res


def block(hits):
    """The hits as one text (each with where it comes from); outside text, chat wraps it as data."""
    return "\n\n".join(f"[{h['title']}" + (f" [article: {h['ref']}]" if h.get("ref") else "") + f"]\n{h['text']}"
                       for h in hits)


def message(found):
    """The tool result for the model: HEAD, and the own hits and the web's result, wrapped as outside text."""
    import chat
    parts = [block(found["hits"])] if found["hits"] else []
    if found.get("web"):
        parts.append(block([found["web"]]))
    if found.get("nur_web"):   # „Auch im Internet suchen“: the web only, the own data were looked at the turn before
        return WEB_ONLY_HEAD + "\n" + chat.wrap_outside("\n\n".join(parts))
    return HEAD + ("\n" + WEB_HEAD if found.get("web") else "") + "\n" + chat.wrap_outside("\n\n".join(parts))


# ---------------------------------------------------------------- Herkunft und „Auch im Internet suchen“ (step 5)
# what a hit is, by its source (lokal's own sources and Finden's, fund.QUELLEN): (one, more) in German and English.
# Every source of Finden is here or in ART_OF (test_quellen.Herkunft), so a new source cannot be left out.
ARTEN = {"mail": ("Mail", "Mails", "mail", "mails"), "anhang": ("Anhang", "Anhänge", "attachment", "attachments"),
         "dokument": ("Dokument", "Dokumente", "document", "documents"),
         "termin": ("Termin", "Termine", "appointment", "appointments"),
         "kontakt": ("Kontakt", "Kontakte", "contact", "contacts"),
         "chat": ("Gespräch", "Gespräche", "conversation", "conversations"),
         "liste": ("Liste", "Listen", "list", "lists"), "erinnerung": ("Erinnerung", "Erinnerungen", "reminder", "reminders"),
         "wissensbuch": ("Wissensbuch-Seite", "Wissensbuch-Seiten", "knowledge book page", "knowledge book pages"),
         "bild": ("Bild", "Bilder", "picture", "pictures"), "musik": ("Lied", "Lieder", "song", "songs"),
         "archiv": ("Archiv-Artikel", "Archiv-Artikel", "archive article", "archive articles")}
ART_OF = {"docs": "dokument", "history": "chat", "kiwix": "archiv", "nas": "dokument", "remarkable": "dokument"}
WEB_WORD = ("Internet", "the web")
# the chip's words; sent like a typed answer (panel, apps, Begleiter, Telegram), a typed one counts the same
WEB_CHIP = ("Auch im Internet suchen", "Also search the web")
WEB_TTL = 900               # the offer holds 15 minutes, and only for the very next message on the same device
MAX_OFFERS = 500
_offers = {}                # (profile id, device "client:convo") -> (the question's own words, monotonic time)
_offers_lock = threading.Lock()


def art(h):
    """The kind of one hit (a key of ARTEN): a hit of Finden by its source, the others by theirs."""
    k = h.get("quelle") if h.get("src") == "fund" else h.get("src")
    return ART_OF.get(k, k)


def herkunft(found, web=False):
    """The line under an answer the quick look found own hits for: only kinds and numbers, built by the panel from the
    hits' sources, never by the model and never with a title or a word of what was found. web: the web was searched in
    this answer too (the panel's own search or the model's). {"de", "en", "arten": [[kind, n], …]} or None."""
    n = {}
    for h in (found or {}).get("hits") or []:
        k = art(h)
        if k in ARTEN:
            n[k] = n.get(k, 0) + 1
    if not n:
        return None
    de = [f"{c} {ARTEN[k][0 if c == 1 else 1]}" for k, c in n.items()]
    en = [f"{c} {ARTEN[k][2 if c == 1 else 3]}" for k, c in n.items()]
    if web or (found or {}).get("web"):
        de.append(WEB_WORD[0])
        en.append(WEB_WORD[1])
    return {"de": "Aus: " + ", ".join(de), "en": "From: " + ", ".join(en), "arten": [[k, c] for k, c in n.items()]}


def web_chip(text):
    """The person asks for the offered web search in the chip's words (also typed, either language)."""
    s = re.sub(r"[^\w ]", "", str(text or "").lower()).strip()
    return s in {w.lower() for w in WEB_CHIP}


def web_offer(uid, src, text, now=None):
    """Keep „Auch im Internet suchen“ for the next message of this profile on this device: only the person's own
    words of the question (own_words), never a word of what was found. text None: nothing offered (any older offer of
    this device goes)."""
    now = time.monotonic() if now is None else now
    with _offers_lock:
        _offers.pop((uid, src), None)
        words = own_words(text) if text else ""
        if words:
            if len(_offers) >= MAX_OFFERS:
                for k in [k for k, v in _offers.items() if now - v[1] > WEB_TTL] or list(_offers)[:MAX_OFFERS // 10]:
                    _offers.pop(k, None)
            _offers[(uid, src)] = (words, now)
        return bool(words)


def web_pop(uid, src, now=None):
    """The offer of this device, taken away at every new message (used or not): the question's own words or ""."""
    now = time.monotonic() if now is None else now
    with _offers_lock:
        got = _offers.pop((uid, src), None)
    return got[0] if got and now - got[1] <= WEB_TTL else ""


# ---------------------------------------------------------------- "Erst lokal testen" (Zustand -> Prüfen)
@router.post("/api/admin/lokal/test", dependencies=[Depends(auth)])
async def lokal_test(request: Request):
    """One sentence through the Quellen-Weiche and the quick look: class, reasons, the probe, sources, hits (titles
    only) and times. Looks in the own data of the profile signed in in this browser, if any (Finden with its
    releases, documents, conversations), and in the Kiwix when the admin set it up; never in the web (nothing goes
    out from a test). Nothing stored, nothing logged."""
    guard.limit(request, "lokal", admin=True)
    body = await request.json()
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEST:
        raise HTTPException(400, f"text: 1 bis {MAX_TEST} Zeichen")
    import intent
    import quellen
    import wissen
    cfg = ccfg()
    who = profiles.current(request)
    ctx = {"route": intent.classify_cfg(text, cfg), "tool_words": cfg.get("tool_words", ""), "eigen": bool(who)}
    kind, why = await asyncio.to_thread(quellen.klasse, text, who["id"] if who else None, ctx)
    srcs = []
    if who and cfg.get("documents", True) and (documents.count_docs(who["id"], used_only=True) or wissen.shared_list(who["id"])):
        srcs.append("docs")
    if kiwix.admin_on():
        srcs.append("kiwix")
    if who and cfg.get("memory", True) and cfg.get("history", True):
        srcs.append("history")
    if who and features.allowed("fund", who["id"]):
        srcs.append("fund")
    srcs = quellen.blick(kind, why, srcs, False)
    lim = budget(cfg)
    info = ctx.get("info") or {}
    out = {"kind": kind, "why": why, "words": query(text).split(), "profile": who["name"] if who else "", "sources": srcs,
           "probe": info.get("probe"), "probe_ms": info.get("ms"), "ms": 0, "n": {}, "late": [], "err": [], "hits": [],
           "budget": lim[0], "kiwix_budget": lim[1]}
    if srcs:
        res = await look(who["id"] if who else None, text, srcs, lim)
        out.update(ms=res["ms"], n=res["n"], late=res["late"], err=res["err"],
                   hits=[{"src": h["src"], "title": h["title"], "chars": len(h["text"])} for h in res["hits"]])
    return out
