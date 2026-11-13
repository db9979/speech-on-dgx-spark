"""Quellen-Weiche (plan such-index/zuverlaessig.md, step 3): the second stage of the Weiche. The Weiche (intent.py) stays
the first stage and decides what an action needs; for a question that wants to know or read something this module
decides by fixed rules, never the model, where the answer is looked for:

    intern   the person's own data (mail, attachments, documents, appointments, contacts, conversations, lists,
             Wissensbuch, NAS, reMarkable): „Erst lokal“ looks in all of them that are released (lokal.look)
    extern   the world outside (weather, prices in shops, news, current offices …): nothing changes, no delay
    beides   both: the quick look in the own data, and the panel starts the web search itself with the person's own
             words of the question (lokal.own_words), before any mail text is read
    ""       no knowledge question (an action, small talk, a plain yes): nothing changes

klasse() reads only the person's own latest message and the Weiche's groups. The rules, in this order:
  1. small talk, a plain yes or no                                          -> ""
  2. asks for the web in so many words                                      -> extern
  3. names an own source („in meinen Unterlagen“, „laut Angebot“)            -> intern, the web left out of this answer
  4. a group of the world (web search, weather, trains, feeds, Wikipedia; parcels without an own order)
                                                                            -> extern („Neuigkeiten von …“: the probe)
  5. a group of an action (smart home, iPhone, Spark …), unless a how-to question about the own device
                                                                            -> ""
  6. no question at all („Setz Milch auf die Liste“)                        -> ""
  7. a group of the own data (mail, calendar, contacts, Finden, lists …)    -> intern
  8. a word of ownership with own data („meine Versicherung“, „was ich bestellt habe“)
                                                                            -> intern
  9. a document word or „was steht im Angebot“ (a timeless question about it: beides)
                                                                            -> intern
 10. current things and the world (prices, news, offices, 20xx …)            -> extern
 11. timeless knowledge and how-to („Wie funktioniert …“, „Wer war …“)       -> beides
 12. else the probe: Finden's own index (fund.suche) for this profile only, at most PROBE_MS in a thread of its own,
     never on the event loop; strong hits -> intern, weak -> beides, none -> extern, too slow -> beides.
     Without Finden released for the profile (or for a guest, another voice, MCP) there is no probe: beides, and
     „Erst lokal“ behaves as before (documents, Kiwix, earlier conversations, the model decides about the web).

The reasons are fixed words (GRUENDE), never words of the question; the journal line is written by lokal.log_line.
"""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import features
import intent
import lokal

PROBE_MS = 150             # the probe's whole budget
PROBE_HITS = 3             # hits the probe asks for
PROBE_BUSY = 2             # probes at the same time; more go without one (beides)
STRONG_WORDS = 2           # words of the question a strong hit holds (unless its sender, company or person is named)
CLASSES = ("intern", "extern", "beides")
GRUENDE = ("Plaudern", "Antwort auf Rückfrage", "Websuche verlangt", "eigene Quelle", "Welt", "Neuigkeiten",
           "Handlung", "keine Frage", "eigene Daten", "Besitz", "Unterlage", "Aktuelles", "zeitlos", "Gerät",
           "keine Suchwörter", "Probe stark", "Probe schwach", "Probe leer", "Probe zu langsam", "ohne Probe",
           "Internet-Chip")
# the source named in so many words: then only there (the web is left out of this answer, lokal.LOCAL_ONLY)
LOCAL = re.compile(r"(?i)\b(mein\w* (dokument\w*|unterlage\w*|datei\w*|pdfs?|papier\w*|vertr[aä]g\w*|rechnung\w*|"
                   r"versicherung\w*|brief\w*|notiz\w*|ordner\w*|archiv\w*|aufzeichnung\w*)|in den (dokumenten|unterlagen)|"
                   r"hochgeladen\w*|kiwix|offline-?archiv\w*|im archiv|nachschlagewerk\w*|"
                   r"(haben|hatten) wir .{0,40}(gesprochen|geredet|besprochen)|hast du (mir )?(gesagt|erzählt)|"
                   r"letzte[ns]? mal|neulich|weißt du noch|weisst du noch)\b")
# current things the own data cannot know, and the world's offices („Wer ist Bundeskanzler?“)
EXTERN = re.compile(r"(?i)\b(aktuell\w*|neueste\w*|neuste\w*|heute|heutige\w*|gestern|morgen|übermorgen|gerade|derzeit|"
                    r"zurzeit|momentan|diese[nrms]? (woche|monat|jahr)|letzte[nrms]? (woche|monat|nacht)|live|"
                    r"nachrichten|news|schlagzeile\w*|preis\w*|kostet|kurs\w*|aktie\w*|börse\w*|bitcoin|wahl\w*|"
                    r"umfrage\w*|öffnungszeit\w*|geöffnet|stau\w*|verkehrslage|20[2-9]\d|latest|today|yesterday|"
                    r"current\w*|price\w*|\w*kanzler\w*|präsident\w*|minister\w*|bürgermeister\w*|papst|"
                    r"weltmeister\w*|chancellor|president|prime minister|mayor)\b")
WORLD_GROUPS = {"websuche", "wetter", "bahn", "feeds", "wikipedia"}
# groups that read the person's own data
OWN_GROUPS = {"mail", "kalender", "kontakt", "finden", "liste", "gedaechtnis", "nachricht", "mappe"}
# groups the second stage reads at all; any other group is an action of the first stage
READ_GROUPS = WORLD_GROUPS | OWN_GROUPS | {"dokument", "paket", "archiv", "plaudern"}
# action groups a how-to question about the own device can come from („Wie geht mein iPhone in den Flugmodus?“)
DEVICE_GROUPS = {"iphone", "spark", "smarthome"}
HOWTO = re.compile(r"(?i)^\W*(\w+,\s*)?(wie|how)\s+(geht|gehen|mache|macht|kann|stelle|stellt|bekomme|kriege|"
                   r"lange\s+(hält|halten)|do|does|can)\b")
# a parcel of one's own order („meine Bestellung“, „was ich bestellt habe“) reads the own mails
PARCEL_OWN = re.compile(r"(?i)\b((mein|meine|meinen|meiner|unser|unsere|unseren)\s\S*bestellung\w*|"
                        r"(ich|wir)\b.{0,40}\bbestellt|bestellt (hab|habe|hatte|haben|hatten)\b)")
# „Gibt es Neuigkeiten von der Hausverwaltung?“: news from someone may be the own mail; the probe decides
NEWS_FROM = re.compile(r"(?i)\b(neuigkeit\w*|neues|news)\s+(von|vom|from)\b")
# a question at all (a W-word, a verb first, „zeig“, „such“, a question mark); „Setz Milch auf die Liste“ is none
FRAGE = re.compile(r"(?i)^\W*(\w+,\s*)?(was|wann|wo|wer|wen|wem|wessen|wie|welche\w*|warum|wieso|weshalb|woher|wohin|"
                   r"worüber|wovon|hat|hast|haben|hatte|hatten|ist|sind|war|waren|gibt|gab|kam|kamen|kommt|steht|"
                   r"stand|stehen|habe|hab|bin|kann|kannst|könnte|weißt|weisst|zeig\w*|such\w*|find\w*|schau\w*|lies|"
                   r"nenn\w*|erklär\w*|erzähl\w*|sag mir|what\w*|when|where|who|which|how|did|do|does|has|have|is|"
                   r"are|was|were|show|find|search|look|tell|read|any|explain)\b|\?\s*$")
# a word of ownership with own data or an own deed
BESITZ = re.compile(r"(?i)\b((mein|meine|meinem|meinen|meiner|meines|unser|unsere|unserem|unseren|unserer|my|our)\s+"
                    r"(\w+-)?\w*(rechnung|vertrag|verträge|versicherung|police|steuer|konto|kündigung|bestellung|termin|"
                    r"liste|notiz|wissensbuch|mail|post|brief|unterlage|dokument|datei|abo|miete|nebenkosten|gehalt|"
                    r"lohn|rente|antrag|bescheid|kontakt|invoice|contract|order|insurance)\w*|"
                    r"\b(ich|wir|mir|uns|i|we)\b.{0,40}\b(bestellt|gebucht|bezahlt|überwiesen|unterschrieben|gekündigt|"
                    r"abgeschlossen|geschrieben|besprochen|ordered|booked|paid|signed))\b")
# „Was steht im Angebot vom Dachdecker?“: an own paper by its plain name (a compound like „Koalitionsvertrag“ is not)
PAPER = re.compile(r"(?i)\b(steht|stand|stehen|standen)\s+(im|in dem|in der|in meinem|in meiner|in unserem|in unserer)\s+"
                   r"(angebot|rechnung|vertrag|brief|bescheid|kostenvoranschlag|police|schreiben)\b")
# timeless knowledge and how-to: the own data may know something, the world surely does
ZEITLOS = re.compile(r"(?i)^\W*(\w+,\s*)?(wie funktionier\w*|wie macht man|wie \w+e ich\b|wie \w+t man\b|wie geht\b|"
                     r"wie (hoch|lang|lange|groß|gross|alt|weit|tief|schwer|schnell|warm|kalt) (ist|sind|war|wird)\b|"
                     r"was (ist|sind) (ein|eine|der unterschied)\b|was bedeutet|was heißt|was heisst|wer war\b|warum\b|"
                     r"wieso\b|weshalb\b|erklär\w*|how (does|do|to|can)\b|what (is|are) (a|an)\b|who was\b|why\b|"
                     r"explain)|\b(was kann (ich|man) (da )?(tun|machen)|what can i do)\b")

_busy = threading.BoundedSemaphore(PROBE_BUSY)
_pool = ThreadPoolExecutor(max_workers=PROBE_BUSY, thread_name_prefix="quellen-probe")
_stat_lock = threading.Lock()
_stat = {"day": "", "intern": 0, "extern": 0, "beides": 0, "probe": 0, "ms": []}
# Live (step 5): today's Herkunft lines under answers, „Auch im Internet suchen“ offered and tapped (numbers only)
ZAEHLER = ("herkunft", "chip", "chip_genutzt")


def _fund_probe(uid, text, nur):
    """Finden's hits for this profile's own question (None: Finden is not released for it, no probe)."""
    import fund
    if not uid or not features.allowed("fund", uid):
        return None
    return fund.suche(uid, lokal.query(text), anzahl=PROBE_HITS, nur=nur)


def _timed(fn):
    """fn() in the probe's own thread, at most PROBE_MS; (hits or None, ms, late)."""
    if not _busy.acquire(blocking=False):
        return [], PROBE_MS, True
    t0 = time.monotonic()

    def run():
        try:
            return fn()
        finally:
            _busy.release()
    try:
        fut = _pool.submit(run)
    except RuntimeError:
        _busy.release()
        return [], 0, True
    try:
        hits = fut.result(timeout=PROBE_MS / 1000)
    except FutureTimeout:
        return [], int((time.monotonic() - t0) * 1000), True
    except Exception as e:     # a broken index: no probe, the question goes on as without Finden
        print("lokal: probe fehler", type(e).__name__, flush=True)
        return None, int((time.monotonic() - t0) * 1000), False
    return hits, int((time.monotonic() - t0) * 1000), False


def staerke(text, hits):
    """How well the probe's hits fit: "stark" (a hit holds lokal.COVER of the question's words and at least
    STRONG_WORDS of them, or a word names its sender, company or person), "schwach" (hits, but none fits so), "leer"
    (none). One word in a title alone is weak („Was weißt du über Lissabon?“ with a hotel mail: beides)."""
    if not hits:
        return "leer"
    words = lokal.terms(text)
    for h in hits:
        if words and lokal.cover(words, lokal.fund_text(h)) >= lokal.COVER \
                and len(lokal._hits(lokal.fund_text(h), words)) >= STRONG_WORDS:
            return "stark"
        named = " ".join(str(v) for k, v in (h.get("felder") or {}).items() if k in ("absender", "firma", "person", "name"))
        named += " " + " ".join(str(t.get("wert", "")) for t in h.get("tags") or [] if t.get("typ") in ("firma", "person"))
        if any(len(w) >= 4 for w in lokal._hits(named, words)):
            return "stark"
    return "schwach"


def _probe(text, uid, ctx):
    """(class, reason) of the probe; ctx["probe"] (the bench's stand-in index) or Finden for the own profile."""
    info = ctx.setdefault("info", {})
    if callable(ctx.get("probe")):
        t0 = time.monotonic()
        hits, late = ctx["probe"](lokal.query(text)), False
        ms = int((time.monotonic() - t0) * 1000)
    elif ctx.get("eigen") and uid:
        hits, ms, late = _timed(lambda: _fund_probe(uid, text, ctx.get("nur")))
    else:
        hits, ms, late = None, 0, False
    if hits is None:
        return "beides", "ohne Probe"
    info.update(probe=len(hits), ms=ms)
    if late:
        return "beides", "Probe zu langsam"
    got = staerke(text, hits)
    return {"stark": ("intern", "Probe stark"), "schwach": ("beides", "Probe schwach"),
            "leer": ("extern", "Probe leer")}[got]


# tools outside the Weiche's groups that read the world (intent.GROUPS knows the rest)
WELT_WERKZEUGE = {"read_page"}


def werkzeug_art(tool):
    """For the Quellenangabe (quellenangabe.teile): "eigen" (a tool of the person's own data), "welt" (the web, the
    archive, weather, trains …) or "" by the Weiche's groups of the tool."""
    g = {name for name, (tools, _) in intent.GROUPS.items() if tool in tools}
    if tool in WELT_WERKZEUGE or g & (WORLD_GROUPS | {"archiv", "paket"}) and not g & OWN_GROUPS:
        return "welt"
    if g & (OWN_GROUPS | {"dokument"}):
        return "eigen"
    return ""


def klasse(text, uid, ctx):
    """(class, reasons): "intern", "extern", "beides" or "" and a list of fixed words (GRUENDE). Only the person's own
    words and the Weiche's groups (ctx["route"], an intent.Route; ctx["tool_words"], the admin's must words). The
    probe runs only with ctx["eigen"] (own profile, own browser or voice, not Telegram without personal data, not
    MCP; chat_turn decides) and ctx["nur"] (a Mappe: its entries only), or with ctx["probe"] (a stand-in index for
    the bench); it fills ctx["info"] with {"probe": hits, "ms": ms}. Never raises for a text."""
    import ablauf
    import chat
    import homeassistant
    text = str(text or "")[:2000]
    route = ctx.get("route") or intent.Route([], {})
    if not text.strip() or chat.SMALLTALK.fullmatch(text):
        return "", ["Plaudern"]
    if ablauf.short_reply(text):   # „Ja“ to a question before: nothing to look up
        return "", ["Antwort auf Rückfrage"]
    if chat.needed(text, {"web_search"}, ctx.get("tool_words", "")):
        return "extern", ["Websuche verlangt"]
    if LOCAL.search(text) or intent.OWN_PAPER.search(text):
        return "intern", ["eigene Quelle"]
    names = set(route.names) - {"plaudern"}
    if "paket" in names and PARCEL_OWN.search(text):
        names.discard("paket")
    world = names & (WORLD_GROUPS | {"paket"})
    if world:
        if "websuche" in world and NEWS_FROM.search(text) and not EXTERN.search(text):
            kind, why = _probe(text, uid, ctx)
            return ("intern" if kind == "intern" else "extern"), ["Neuigkeiten", why]
        return "extern", ["Welt"]
    act = names - READ_GROUPS
    if act and not (act <= DEVICE_GROUPS and HOWTO.search(text)
                    and not ("smarthome" in act and homeassistant.is_command(text))):   # a switching command stays one
        return "", ["Handlung"]
    if not FRAGE.search(text):
        return "", ["keine Frage"]
    if names & OWN_GROUPS:
        return "intern", ["eigene Daten"]
    if BESITZ.search(text):
        return "intern", ["Besitz"]
    if "dokument" in names or PAPER.search(text):
        return ("beides", ["zeitlos"]) if ZEITLOS.search(text) else ("intern", ["Unterlage"])
    if EXTERN.search(text):
        return "extern", ["Aktuelles"]
    if ZEITLOS.search(text) or HOWTO.search(text):
        return "beides", ["Gerät" if act else "zeitlos"]
    if not lokal.terms(text):
        return "", ["keine Suchwörter"]
    kind, why = _probe(text, uid, ctx)
    return kind, [why]


def blick(kind, why, srcs, web_ok):
    """The sources the quick look asks for this class (srcs: lokal.sources of the tools this turn offers before the
    Weiche narrows, the same rights). With Finden (source "fund"): intern -> every own source; beides -> every own
    source, the Kiwix and, with web_ok, the panel's own web search with the person's own words ("web"). Without
    Finden it stays as before step 3: documents, Kiwix and earlier conversations for a question to look up, nothing
    for an own source named or a group of the own data, never the panel's web search."""
    if kind not in ("intern", "beides"):
        return []
    if "fund" in srcs:
        if kind == "intern":
            return [s for s in srcs if s != "kiwix"]
        return list(srcs) + (["web"] if web_ok else [])
    if set(why) & {"eigene Quelle", "eigene Daten"}:
        return []
    return list(srcs)


def note(kind, info=None, now=None):
    """Live: today's classes and the probe's time, or one of ZAEHLER (numbers only)."""
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))
    with _stat_lock:
        if _stat["day"] != day:
            _stat.update(day=day, intern=0, extern=0, beides=0, probe=0, ms=[], **{k: 0 for k in ZAEHLER})
        if kind in CLASSES or kind in ZAEHLER:
            _stat[kind] = _stat.get(kind, 0) + 1
        if info and "ms" in info:
            _stat["probe"] += 1
            _stat["ms"] = (_stat["ms"] + [int(info["ms"])])[-200:]


def for_live(now=None):
    """{"intern", "extern", "beides", "probe", "ms", "herkunft", "chip", "chip_genutzt"} of today (ms: the probe's
    median, or None)."""
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))
    with _stat_lock:
        if _stat["day"] != day:
            return {"intern": 0, "extern": 0, "beides": 0, "probe": 0, "ms": None} | {k: 0 for k in ZAEHLER}
        ms = sorted(_stat["ms"])
        return {k: _stat[k] for k in ("intern", "extern", "beides", "probe")} | {"ms": ms[len(ms) // 2] if ms else None} \
            | {k: _stat.get(k, 0) for k in ZAEHLER}
