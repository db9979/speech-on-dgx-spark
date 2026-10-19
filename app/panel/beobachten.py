"""Eigene Aufgaben, die beobachten (plan „Eigene Aufgaben“, Variante 3): „Sag mir Bescheid, wenn es eine neue Firmware
für meine FRITZ!Box gibt“, „Erinnere mich, wenn der Flug nach Rom unter 100 Euro kostet“.

A watch is a scheduled job of agent.py (plan with kind "watch") that runs like every job (read only, one after the
other, conversations first) and reports only what is new. The language model only names candidates, one line each:

    FUND: <value> | <address> | <quote from that page>

The panel decides, by fixed rules, what counts:
  1. the address was read or returned by a search in this very run,
  2. the quote stands word for word in that page (or in the search result that named the address),
  3. the value stands in the quote,
  4. with a price limit: the value holds an amount below the limit,
  5. the value is not among the values already known for this watch.
Only then a notification goes out (fixed sentence with value and host). Everything else stays quiet and goes into the
watch's history ("nichts Neues"). After FAILS failed runs in a row the watch pauses itself and says why; after
IDLE_DAYS without anything new it pauses as well and says so. The person turns it on again under Ich → Aufträge.

Making and changing a watch: by voice only as a proposal with a fixed sentence and the person's "Ja" (agent.answer),
or on the page. The Admin allows it (Funktionen → Aufträge → „Beobachten“, chat.agent_watch, off), for every
profile that may use agent functions; guests never.
"""
import re
import time
from urllib.parse import urlsplit

MAX_WATCH = 10             # watches per profile
MAX_KNOWN = 50             # values remembered per watch
MAX_HIST = 20              # runs kept in the history of a watch
HIST_DAYS = 14
FAILS = 5                  # failed runs in a row, then the watch pauses itself
IDLE_DAYS = 90             # days without anything new, then the watch pauses itself
MAX_FINDS = 8              # candidate lines read from one report

# "Erinnere mich / sag Bescheid / melde dich, wenn …" plus a word that points to the web (not to the smart home,
# not to a time): the panel makes the proposal itself (agent.answer), the model is not asked
ASK = r"(erinner\w* mich|sag\w* (mir )?([\w:]+ ){0,5}bescheid|gib (mir )?([\w:]+ ){0,5}bescheid|meld\w* dich|benachrichtig\w* mich|" \
      r"informier\w* mich|schreib\w* mir|remind me|let me know|tell me|notify me)"
WHEN = r"(wenn|sobald|falls|when|once|as soon as|if)"
WEB = (r"(im internet|im netz|online|im web|auf der (seite|webseite|homepage)|"
       r"neue[nsrm]? (firmware|version|software|update|folge|ausgabe|staffel|album|buch|treiber|release|modell|"
       r"artikel|beitrag|termin(e)? für)|erschein\w*|veröffentlich\w*|herauskommt|rauskommt|herausgekommen|"
       r"preis\w*|kostet|günstiger|billiger|im angebot|verfügbar|lieferbar|wieder da|wieder vorrätig|findest|gefunden|"
       r"es gibt|gibt es|new (firmware|version|update|episode|release)|price|cheaper|available|in stock|released|you find)")
WATCH = re.compile(r"(?i)\b" + ASK + r"\b[ ,]*" + WHEN + r"\b(?P<clause>.{3,200}?)[.!?]*$")
KEEP_EYE = re.compile(r"(?i)\b(behalt\w* (?P<a>.{3,120}?) im auge|beobacht\w* (?P<b>.{3,160})|halt\w* ausschau nach "
                      r"(?P<c>.{3,160})|keep an eye on (?P<d>.{3,160})|watch (out )?for (?P<e>.{3,160}))[.!?]*$")
CHANGE = re.compile(r"(?i)\b(lieber|nur noch|stattdessen|ab jetzt|instead|from now on)\b")
POINTER = re.compile(r"(?i)(das|dies|dieses|it|that|this)\b")
WEB_RX = re.compile(r"(?i)\b" + WEB)
# words that belong to the smart home or a fixed time: those sentences are hamelden's or a reminder's
NOT_WEB = re.compile(r"(?i)\b(in \d+ (minute|stunde|tag)\w*|"
                     r"haustür|klingel\w*|bewegung|fenster|zu hause|nach hause|heimkommt|temperatur im|grad im|"
                     r"waschmaschine fertig|trockner)")
WORDS = re.compile(r"(?i)\b(beobacht\w*|im auge behalten|behalt\w* .{0,60} im auge|halt\w* ausschau|keep an eye on|"
                   + ASK + r"[ ,]*" + WHEN + r"\b.{0,80}" + WEB + r")")
PRICE = re.compile(r"(?i)\b(unter|weniger als|höchstens|maximal|below|under|less than|at most)\s+(\d{1,7}(?:[.,]\d{1,2})?)"
                   r"\s*(€|euro|eur\b|\$|dollar|usd)")
AMOUNT = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,(\d{1,2})|\.(\d{1,2}))?\s*(?:€|euro|eur\b|\$|usd)|"
                    r"(?:€|\$)\s*(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,](\d{1,2}))?", re.I)
FIND_LINE = re.compile(r"(?im)^\W{0,4}(?:FUND|FOUND)\s*:\s*(.+)$")
DAYS = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5, "sonntag": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
LEAD = re.compile(r"(?i)^(du|es|ich|sie|er|man|you|it|there)\s+(im internet|im netz|online)?\s*")
TAIL = re.compile(r"(?i)\s+(findest|gefunden hast|gibt|geben sollte|erscheint|erschienen ist|herauskommt|rauskommt|"
                  r"veröffentlicht wird|kommt|ist|wird|siehst|liest|kostet|kosten|liegt|fällt|is out|is released|exists|appears|costs)$")

RULES = ("Dies ist eine Beobachtung: suche, ob es zum Auftrag etwas Neues gibt. Schreib am Ende für jeden Fund genau "
         "eine Zeile in dieser Form:\nFUND: <kurzer Wert, z. B. Versionsnummer oder Preis> | <Adresse der Seite> | "
         "<wörtliches Zitat aus dieser Seite, höchstens 200 Zeichen, das den Wert enthält>\n"
         "Nimm nur Adressen, die du gelesen hast oder die die Suche geliefert hat. Gibt es keinen Fund, schreib die "
         "Zeile: KEIN FUND. Das Panel prüft jeden Fund selbst; erfinde nichts.")


def _norm(text):
    t = str(text or "").lower()
    t = re.sub(r"[„“\"'»«‚‘’`]", "", t)
    return re.sub(r"\s+", " ", t).strip(" .,;:")


def wants(text):
    """True when the person's words ask for a watch (also the Weiche's word for group "agent")."""
    t = str(text or "")
    return bool(WORDS.search(t)) and not NOT_WEB.search(t)


def _clean(text, most):
    text = re.sub(r"[\x00-\x1f\x7f<>`]", " ", str(text or ""))
    return re.sub(r"\s+", " ", text).strip(" ,.;:!?")[:most]


def title_of(clause):
    """A short name for the list: „du im Internet eine neue Firmware für meine FRITZ!Box findest“ → „Neue Firmware …“."""
    t = _clean(clause, 160)
    for _ in range(2):
        t = LEAD.sub("", t).strip()
    t = re.sub(r"(?i)^(eine?[nrms]?|ein|der|die|das|den|dem|a|an|the)\s+", "", t)
    t = re.sub(r"(?i)\s+(im internet|im netz|online)\b", "", t)
    for _ in range(2):
        t = TAIL.sub("", t).strip()
    t = re.sub(r"(?i)\bmeine[nrms]?\b", "", t).replace("  ", " ").strip()
    t = t[:1].upper() + t[1:]
    return t[:80] or "Beobachtung"


def parse(text):
    """{"task", "title", "repeat", "time", "weekday"?, "below"?} from the person's own words, else None."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) > 400 or NOT_WEB.search(t):
        return None
    m = WATCH.search(t)
    clause = None
    if m and WEB_RX.search(m.group("clause")):
        clause = m.group("clause")
    else:
        k = KEEP_EYE.search(t)
        if k:
            clause = next(g for g in k.group("a", "b", "c", "d", "e") if g)
            # „Beobachte das …“ points at something said before: no new watch from the panel
            if POINTER.match(clause.strip()):
                return None
    # „… lieber jeden Montag“ changes a watch there is (agent_change), it is no new one
    if not clause or CHANGE.search(t):
        return None
    out = {"task": _clean(t, 500), "title": title_of(clause), "repeat": "daily", "time": "08:00"}
    tl = t.lower()
    hm = re.search(r"\bum (\d{1,2})(?::(\d{2}))? ?uhr\b|\bat (\d{1,2})(?::(\d{2}))? ?(am|pm)?\b", tl)
    if hm:
        h = int(hm.group(1) or hm.group(3))
        mi = int(hm.group(2) or hm.group(4) or 0)
        if hm.group(5) == "pm" and h < 12:
            h += 12
        if 0 <= h <= 23 and 0 <= mi <= 59:
            out["time"] = "%02d:%02d" % (h, mi)
    day = re.search(r"\b(jeden|immer|every|on) (montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|monday|"
                    r"tuesday|wednesday|thursday|friday|saturday|sunday)s?\b|\b(montag|dienstag|mittwoch|donnerstag|"
                    r"freitag|samstag|sonntag)s\b", tl)
    if day:
        out["repeat"], out["weekday"] = "weekly", DAYS[(day.group(2) or day.group(3))]
    elif re.search(r"\b(wöchentlich|einmal (in der|pro) woche|weekly)\b", tl):
        out["repeat"], out["weekday"] = "weekly", 0
    elif re.search(r"\b(werktags|on weekdays)\b", tl):
        out["repeat"] = "weekdays"
    elif re.search(r"\b(monatlich|einmal im monat|monthly)\b", tl):
        out["repeat"], out["day"] = "monthly", 1
    p = PRICE.search(t)
    if p:
        out["below"] = float(p.group(2).replace(",", "."))
    return out


MAIL = re.compile(r"(?i)\b" + ASK + r"\b[ ,]*" + WHEN + r"\b\s*(mir )?(eine |die |neue |eine neue )?(e-?mail|mail|post|nachricht)\s+"
                  r"(von|vom|from)\s+(der |dem |den |die )?(?P<who>[\w@.\- ]{2,60}?)\s*(kommt|eingeht|eintrifft|ankommt|da ist|"
                  r"gekommen ist|arrives|comes in)?[.!?]*$")


def mail_sender(text):
    """The sender in „Sag mir Bescheid, wenn eine Mail von der Sparkasse kommt“ (for „Von selbst melden“), else None."""
    m = MAIL.search(re.sub(r"\s+", " ", str(text or "")).strip())
    if not m:
        return None
    who = _clean(m.group("who"), 60)
    return who if len(who) > 2 else None


def amount(text):
    """The first amount of money in the text as a number (479, 479.99, 1.299,00 → 1299.0), else None."""
    m = AMOUNT.search(str(text or ""))
    if not m:
        return None
    whole, cents = (m.group(1), m.group(2) or m.group(3)) if m.group(1) else (m.group(4), m.group(5))
    whole = re.sub(r"[.,\s]", "", whole)
    try:
        return float(whole + ("." + cents if cents else ""))
    except ValueError:
        return None


def candidates(report):
    """[(value, address, quote)] from the report's FUND lines (at most MAX_FINDS)."""
    out = []
    for m in FIND_LINE.finditer(str(report or "")):
        parts = [x.strip() for x in m.group(1).split("|")]
        if len(parts) < 3:
            continue
        value, url, quote = _clean(parts[0], 120), parts[1].strip(" <>()[]"), _clean("|".join(parts[2:]), 300)
        out.append((value, url[:500], quote))
        if len(out) >= MAX_FINDS:
            break
    return out


def check(report, seen, known=(), below=None):
    """The panel's verdict on a run: ({"new": [find], "old": [find], "dropped": n}).
    seen: {"pages": {address: text}, "searches": [text]} of this run (raw text, not wrapped).
    find: {"v", "src", "q"}."""
    known_n = {_norm(k) for k in known}
    pages = {u.rstrip("/.,;:"): _norm(t) for u, t in (seen.get("pages") or {}).items()}
    searches = [str(s or "") for s in seen.get("searches") or []]
    new, old, dropped, taken = [], [], 0, set()
    for value, url, quote in candidates(report):
        u, q, v = url.rstrip("/.,;:"), _norm(quote), _norm(value)
        if not v or len(q) < 8 or not re.match(r"https?://", u) or v not in q:
            dropped += 1
            continue
        ok = u in pages and q in pages[u]
        if not ok:
            ok = any(u in s and q in _norm(s) for s in searches)
        if not ok:
            dropped += 1
            continue
        if below is not None:
            a = amount(value) if amount(value) is not None else amount(quote)
            if a is None or a >= below:
                dropped += 1
                continue
        if v in taken:
            continue
        taken.add(v)
        f = {"v": value, "src": url, "q": quote[:200]}
        (old if v in known_n else new).append(f)
    return {"new": new, "old": old, "dropped": dropped}


def host(url):
    try:
        return (urlsplit(url).hostname or "").removeprefix("www.")[:60]
    except ValueError:
        return ""


def remember(p, finds, now=None):
    """Adds the new values to the watch's known list (newest first, at most MAX_KNOWN)."""
    now = int(now or time.time())
    have = {_norm(k.get("v")) for k in p.get("known") or []}
    add = [{"v": f["v"], "src": f["src"], "t": now} for f in finds if _norm(f["v"]) not in have]
    p["known"] = (add + list(p.get("known") or []))[:MAX_KNOWN]
    return p


def note(p, result, what="", n=0, now=None):
    """One line of history: result is "neu", "still", "bericht" or "fehler"."""
    now = int(now or time.time())
    hist = [h for h in p.get("hist") or [] if now - int(h.get("t") or 0) < HIST_DAYS * 86400]
    p["hist"] = ([{"t": now, "r": result, "n": int(n), "what": _clean(what, 160)}] + hist)[:MAX_HIST]
    return p


def push_text(p, finds):
    """(title, body) of the notification: fixed words, the values and hosts the panel checked."""
    name = p.get("title") or p.get("task", "")[:60]
    first = finds[0]
    more = f" und {len(finds) - 1} weitere" if len(finds) > 1 else ""
    body = f"{first['v']} ({host(first['src'])}){more}.\nEigene Aufgabe „{name[:60]}“ · Öffnen: Ich → Aufträge"
    return f"🔔 Neu gefunden: {name[:60]}", body


def idle(p, now=None):
    """True when the watch found nothing new for IDLE_DAYS."""
    now = now or time.time()
    since = max(int(p.get("created") or 0), int(p.get("last_hit") or 0))
    return bool(since) and now - since > IDLE_DAYS * 86400
