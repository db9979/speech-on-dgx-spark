"""Finden (plan such-index, Stufe A; Dominik 2026-10-29 „1a 2a 3a 4a 5a“): one index over the own data, its fields and
tags, one list of hits for the page Finden, Strg K and the assistant's tool fund_suche.

One source (plan „Grundsatz eine Quelle“): fund copies no text that already has an index. Documents, the NAS and the
reMarkable stay in wissen.db (documents.search), the Wissensbuch in its pages; fund keeps for them only fields (kind,
sender, date, amount, number) and tags and asks their own search. Text of its own it keeps only for sources without
an index (mail and attachments since Stufe B, fundmail.py; appointments, contacts, lists … in Stufe C), sealed where the
source is private: then titles, excerpts, fields and tag values are AES-GCM (vorrat.seal, bound to profile, source, entry
and field) and its words only HMAC marks in fund_blind (vorrat.marke), nothing of it in plain text on the disk.

    users/<id>/fund.db   own schema version (PRAGMA user_version), own lock, WAL, 0600 in a 0700 folder;
                         built again at any time („Neu aufbauen“), deleting = emptying its tables

The collecting contract (QUELLEN): one entry per source, Quelle(name, feature, schutz, art, neues_seit, noch_da,
oeffnen). neues_seit(uid, known, budget) -> (entries, state, done): known is {ext: stand} of what the index holds,
entries are what is new or changed (at most budget), state goes to fund_stand, done says nothing is left;
noch_da(uid, exts) -> the exts still there; oeffnen(uid, ext) -> the way to open it ({"art", "id"}). art "verweis":
only fields and tags, its words go through its own search; art "eigen": its text in fund_fts (clear) or fund_blind
(marks, schutz 1). A source with a round of its own (runde: mail reads its mailboxes in slices, fundmail.py) writes
itself through put_sealed. Each source follows the release of the function it comes from (documents, nasquelle,
remarkable, wissensbuch, fundmail); the index itself is the admin switch chat.fund (off), for every profile, never for
guests.

Tags (S1–S4): the fixed list KATEGORIEN (documents.ARTS without „Sonstiges“ plus the areas BEREICHE), persons,
companies and places; free tags of documents stay in the document's Steckbrief (documents.set_tags). Rules set them
(regel: the sender written in the text, a kind from fixed words, amount and number behind a fixed word); the model
(Stufe D) only proposes; the person's own (fund_hand) wins: shown is (regel ∪ modell − minus) ∪ plus, and a rebuild
never touches fund_hand.

Search (suche): reciprocal rank fusion (k = 60 like documents.search) over the index's own words (fund_fts, and the
marks in fund_blind), documents.search for the own documents, and the Wissensbuch's list when it has one; filters
(source, category, company, person, period) only by fixed rules. The tool's filters come only from the person's own
words of the message (filter_eigen); what the model adds beyond them is dropped and counted.

The journal gets fixed words and numbers only (fund: …), the profile only as profiles.log_name; Live only numbers.
"""
import json
import os
import re
import sqlite3
import statistics
import threading
import time
from typing import Callable, NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Request

import documents
import features
import guard
import profiles
import vorrat
from core import assistant, auth, browser_profile, json_body, own_profile

router = APIRouter()
DB = "fund.db"
SCHEMA_V = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS fund_item (id INTEGER PRIMARY KEY, quelle TEXT NOT NULL, ext TEXT NOT NULL,
    eltern INTEGER, wann INTEGER DEFAULT 0, geaendert INTEGER DEFAULT 0, gesehen INTEGER DEFAULT 0,
    schutz INTEGER DEFAULT 0, titel TEXT DEFAULT '', auszug TEXT DEFAULT '', felder TEXT DEFAULT '{}',
    stand TEXT DEFAULT '', UNIQUE (quelle, ext));
CREATE INDEX IF NOT EXISTS fund_item_wann ON fund_item(quelle, wann DESC);
CREATE INDEX IF NOT EXISTS fund_item_eltern ON fund_item(eltern);
CREATE VIRTUAL TABLE IF NOT EXISTS fund_fts USING fts5(terms);
CREATE VIRTUAL TABLE IF NOT EXISTS fund_blind USING fts5(marken);
CREATE TABLE IF NOT EXISTS fund_tag (item INTEGER NOT NULL, typ TEXT NOT NULL, wert TEXT NOT NULL, marke TEXT NOT NULL,
    ent TEXT, herkunft TEXT DEFAULT 'regel', beleg INTEGER DEFAULT 0, at INTEGER DEFAULT 0,
    PRIMARY KEY (item, typ, marke));
CREATE INDEX IF NOT EXISTS fund_tag_marke ON fund_tag(typ, marke);
CREATE INDEX IF NOT EXISTS fund_tag_ent ON fund_tag(ent);
CREATE TABLE IF NOT EXISTS fund_hand (quelle TEXT NOT NULL, ext TEXT NOT NULL, plus TEXT DEFAULT '[]',
    minus TEXT DEFAULT '[]', at INTEGER DEFAULT 0, PRIMARY KEY (quelle, ext));
CREATE TABLE IF NOT EXISTS fund_stand (quelle TEXT NOT NULL, konto TEXT NOT NULL DEFAULT '', schluessel TEXT NOT NULL,
    wert TEXT, PRIMARY KEY (quelle, konto, schluessel));
CREATE TABLE IF NOT EXISTS fund_todo (item INTEGER PRIMARY KEY, grund TEXT, versuche INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""
TABLES = ("fund_item", "fund_fts", "fund_blind", "fund_tag", "fund_stand", "fund_todo", "meta")   # „Index löschen“
# S1: the fixed list, derived, never typed twice: the kinds of the Steckbrief (documents.ARTS, with „Bestellung“ and
# „Buchung“) without „Sonstiges“, and the areas (only here)
BEREICHE = ("Gesundheit", "Reise", "Auto", "Wohnen", "Finanzen", "Behörde", "Arbeit", "Privat", "Familie", "Einkauf",
            "Freizeit", "Technik", "Bildung")
ARTEN = tuple(a for a in documents.ARTS if a != "Sonstiges")
KATEGORIEN = ARTEN + BEREICHE
TYPEN = ("kategorie", "person", "firma", "ort", "frei")
TYP_WORT = {"kategorie": ("Kategorie", "Category"), "person": ("Person", "Person"), "firma": ("Firma", "Company"),
            "ort": ("Ort", "Place"), "frei": ("Schlagwort", "Tag")}
MAX_TAG = 60             # characters of a person, company or place
MAX_HAND = 40            # own tags (plus and minus together) per item
MAX_WORTE = 200          # characters of the search words
MAX_HITS = 30            # per list in the fusion
MAX_SHOW = 30            # hits of the page
TOOL_MOST = 5            # hits to the model, ...
TOOL_CHARS = 400         # ... each at most this long
RRF = 60                 # the constant of documents.search
BUDGET = 200             # entries per source and round
TEXT_RULES = 30_000      # characters of a document the rules read for amount and number
ROUND_S = 300            # a round per profile at most every five minutes
AUSZUG = 300
LIVE_CACHE = 10
_locks, _locks_guard = {}, threading.Lock()
_running = set()         # profiles whose round runs now
_last = {}               # uid -> (when the last round ran, the stamp of its sources)
_live = {"at": 0.0, "d": None}
_stat = {"day": "", "suchen": 0, "ms": [], "verworfen": 0, "fehler": 0, "runden": 0}
_stat_lock = threading.Lock()


# ---------------------------------------------------------------- the file
def db_path(uid):
    return profiles._path(uid, DB)


def _lock(uid):
    with _locks_guard:
        return _locks.setdefault(uid, threading.RLock())


def _open(uid):
    path = db_path(uid)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    if not os.path.exists(path):
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    if con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_V:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        con.execute(f"PRAGMA user_version={SCHEMA_V}")
        con.commit()
    return con


class _Db:
    """with _Db(uid) as con: one connection per use, commits on success (one transaction per batch: the SD card)."""
    def __init__(self, uid):
        self.uid = uid

    def __enter__(self):
        self.lock = _lock(self.uid)
        self.lock.acquire()
        try:
            self.con = _open(self.uid)
        except BaseException:
            self.lock.release()
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
            self.lock.release()


def _exists(uid):
    return bool(uid) and os.path.exists(db_path(uid))


# ---------------------------------------------------------------- words and marks
def norm(v):
    """A tag as it is compared: one line, lower case, single spaces."""
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def terms(text):
    """Word stems like documents.search (one rule for both), only plain word characters (safe inside MATCH)."""
    return [t for t in documents._terms(str(text or "")[:20000]) if re.fullmatch(r"\w+", t)]


def _match(words):
    """An FTS5 query from stems or marks only, each in quotes, joined by OR (never the person's raw text)."""
    return " OR ".join(f'"{w}"' for w in sorted(set(words)) if re.fullmatch(r"\w+", w))


def clean_tag(typ, wert):
    """(typ, wert) checked by fixed rules, or None: a category only from KATEGORIEN, a free tag only through
    documents.clean_tags, a person, company or place one line of at most MAX_TAG plain characters."""
    if typ not in TYPEN:
        return None
    w = re.sub(r"\s+", " ", str(wert or "")).strip()
    if typ == "kategorie":
        hit = next((k for k in KATEGORIEN if k.lower() == w.lower()), None)
        return (typ, hit) if hit else None
    if typ == "frei":
        got = documents.clean_tags([w])
        return (typ, got[0]) if got else None
    w = re.sub(r"[\x00-\x1f\x7f<>\"\\{}\[\]`|]", "", w)[:MAX_TAG].strip()
    return (typ, w) if len(w) >= 2 else None


# ---------------------------------------------------------------- fixed rules for fields and tags (regel)
BETRAG = re.compile(r"(?i)\b(?:gesamt\w*|summe|rechnungsbetrag|endbetrag|zu zahlen|zahlbetrag|total)\b[^\d\n]{0,30}?"
                    r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,6},\d{2})\s?(?:€|eur\b)")
NUMMER = re.compile(r"(?i)\b(rechnungs|kunden|bestell|auftrags|buchungs|vertrags)-?\s?(?:nr|nummer|no)\.?\s*[:#]?\s*"
                    r"([A-Z0-9][A-Z0-9/-]{2,24})\b")
ART_WORTE = (("Rechnung", re.compile(r"(?i)\b(rechnung|rechnungsnummer|rechnungsbetrag|invoice)\b")),
             ("Bestellung", re.compile(r"(?i)\b(bestellbestätigung|ihre bestellung|bestellnummer|order confirmation)\b")),
             ("Buchung", re.compile(r"(?i)\b(buchungsbestätigung|ihre buchung|buchungsnummer|booking confirmation)\b")))


def regeln(text, card=None):
    """(felder, tags) from fixed rules: the amount behind „Gesamt/Summe/Rechnungsbetrag“, a number behind its fixed
    word, a kind from fixed words or the Steckbrief's kind when it is one of KATEGORIEN, the sender as a company only
    when it stands in the text word for word. tags: [(typ, wert, beleg)]."""
    text = str(text or "")[:TEXT_RULES]
    card = card or {}
    felder, tags = {}, []
    m = BETRAG.search(text)
    if m:
        felder["betrag"] = m.group(1) + " €"
    m = NUMMER.search(text)
    if m:
        felder["nr"] = m.group(2)
    art = str(card.get("art") or "")
    if art in KATEGORIEN:
        tags.append(("kategorie", art, 1))
    for name, rx in ART_WORTE:
        if rx.search(text) and name != art:
            tags.append(("kategorie", name, 1))
    sender = re.sub(r"\s+", " ", str(card.get("sender") or "")).strip()
    if sender:
        felder["absender"] = sender[:MAX_TAG]
        if len(sender) >= 2 and re.search(r"(?<!\w)" + re.escape(sender) + r"(?!\w)", text, re.I):
            tags.append(("firma", sender[:MAX_TAG], 1))
    if card.get("date"):
        felder["datum"] = str(card["date"])[:10]
    if card.get("ref") and "nr" not in felder:
        felder["nr"] = str(card["ref"])[:40]
    return felder, tags[:6]


# ---------------------------------------------------------------- the sources
class Quelle(NamedTuple):
    name: str
    feature: str             # the function it follows (features.allowed); the index itself needs chat.fund
    schutz: int              # 0 clear, 1 sealed (marks and AES-GCM, Stufe B)
    art: str                 # "verweis" (fields and tags, its own search) or "eigen" (text in fund_fts/fund_blind)
    neues_seit: Callable
    noch_da: Callable
    oeffnen: Callable
    de: str
    en: str
    runde: Callable = None   # a round of its own (uid, now, seconds) -> (new, gone): mail in slices (fundmail.py)


def _doc_source(d):
    s = d.get("source") or "upload"
    return "nas" if s == "nas" else "remarkable" if s == "remarkable" else "dokument"


def _doc_stand(d):
    c = {k: d.get(k) for k in ("name", "created", "changed", "state", "use", "title", "art", "sender", "date", "ref")}
    return json.dumps(c, sort_keys=True, ensure_ascii=False)[:2000]


def _doc_entries(uid, quelle, known, budget):
    docs = [d for d in documents.list_docs(uid) if _doc_source(d) == quelle and d.get("state") == "ready"]
    out = []
    for d in docs:
        st = _doc_stand(d)
        if known.get(d["id"]) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        t = documents.text_of(uid, d["id"], most=TEXT_RULES) or {}
        text = "\n".join(p["text"] for p in t.get("parts") or [])
        felder, tags = regeln(text, d)
        titel = d.get("title") or d.get("name") or ""
        when = 0
        if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", str(d.get("date") or "")):
            try:
                when = int(time.mktime(time.strptime(d["date"][:10] if len(d["date"]) == 10 else d["date"] + "-01", "%Y-%m-%d")))
            except (ValueError, OverflowError):
                when = 0
        out.append({"ext": d["id"], "wann": when or int(d.get("created") or 0), "geaendert": int(d.get("changed") or d.get("created") or 0),
                    "titel": titel[:160], "auszug": re.sub(r"\s+", " ", (d.get("brief") or "") if d.get("brief") not in ("ok", "x") else "")[:AUSZUG],
                    "felder": dict(felder, name=d.get("name") or "", tags=list(d.get("tags") or [])), "stand": st, "tags": tags,
                    # only fields and tags as words (the text stays in wissen.db)
                    "worte": " ".join([titel, d.get("name") or "", d.get("art") or "", d.get("sender") or "",
                                       felder.get("nr", ""), " ".join(d.get("tags") or [])])})
    return out, {}, True


def _doc_still(uid, quelle, exts):
    have = {d["id"] for d in documents.list_docs(uid) if _doc_source(d) == quelle and d.get("state") == "ready"}
    return {e for e in exts if e in have}


def _doc_way(uid, ext):
    return {"art": "dokument", "id": ext}


def _wb_allowed(uid):
    import wissensbuch
    return wissensbuch.allowed(uid)


def _wb_entries(uid, known, budget):
    import wissensbuch
    if not _wb_allowed(uid) or not os.path.exists(documents.db_path(uid)):
        return [], {}, True
    out = []
    typ = {"Person": "person", "Firma": "firma", "Ort": "ort"}
    for p in wissensbuch.index(uid):
        st = json.dumps([p["title"], p["art"], p["changed"], p["n"]], ensure_ascii=False)
        if known.get(p["id"]) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        tags = [(typ[p["art"]], p["title"][:MAX_TAG], 1)] if p["art"] in typ else []
        out.append({"ext": p["id"], "wann": int(p["changed"] or 0), "geaendert": int(p["changed"] or 0), "titel": p["title"][:160],
                    "auszug": "", "felder": {"art": p["art"], "saetze": p["n"]}, "stand": st, "tags": tags,
                    "worte": p["title"] + " " + p["art"]})
    return out, {}, True


def _wb_still(uid, exts):
    import wissensbuch
    if not _wb_allowed(uid) or not os.path.exists(documents.db_path(uid)):
        return set()
    have = {p["id"] for p in wissensbuch.index(uid)}
    return {e for e in exts if e in have}


QUELLEN = (
    # documents (upload, Begleiter, mail taken over): follow „Eigene Dokumente“, their text stays in wissen.db
    Quelle("dokument", "documents", 0, "verweis", lambda uid, known, budget: _doc_entries(uid, "dokument", known, budget),
           lambda uid, exts: _doc_still(uid, "dokument", exts), _doc_way, "Dokument", "Document"),
    # Wissensordner on the NAS (nasquelle.py → documents, source nas): follows its own release
    Quelle("nas", "nasquelle", 0, "verweis", lambda uid, known, budget: _doc_entries(uid, "nas", known, budget),
           lambda uid, exts: _doc_still(uid, "nas", exts), _doc_way, "NAS", "NAS"),
    # reMarkable notebooks (remarkable.py → documents, source remarkable)
    Quelle("remarkable", "remarkable", 0, "verweis", lambda uid, known, budget: _doc_entries(uid, "remarkable", known, budget),
           lambda uid, exts: _doc_still(uid, "remarkable", exts), _doc_way, "reMarkable", "reMarkable"),
    # Wissensbuch pages (wb_pages): titles and kinds; Person/Firma/Ort pages stand in for the Wissenskarte's nodes until
    # those are on main (plan §9, S3)
    Quelle("wissensbuch", "wissensbuch", 0, "verweis", _wb_entries, _wb_still,
           lambda uid, ext: {"art": "wissensbuch", "id": ext}, "Wissensbuch", "Knowledge book"),
    # mails of the inbox, the archive and the sent folder (never spam or trash), sealed, read in slices (fundmail.py,
    # Stufe B, switch „Mails und Anhänge“); attachments go with their mail (eltern) and its round
    Quelle("mail", "fundmail", 1, "eigen", lambda uid, known, budget: _fm().neues_seit(uid, known, budget),
           lambda uid, exts: _fm().noch_da(uid, exts), lambda uid, ext: _fm().weg(uid, ext), "Mail", "Mail",
           lambda uid, now, secs: _fm().runde(uid, now, secs)),
    Quelle("anhang", "fundmail", 1, "eigen", lambda uid, known, budget: ([], {}, True),
           lambda uid, exts: _fm().noch_da(uid, exts), lambda uid, ext: _fm().weg(uid, ext), "Anhang", "Attachment",
           lambda uid, now, secs: (0, 0)),
)
BY_NAME = {q.name: q for q in QUELLEN}
# words of the person that name a source (the tool's filter „quelle“ only when one of them was said)
QUELLE_WORTE = {"dokument": r"dokument\w*|unterlage\w*|datei\w*|pdf", "nas": r"nas\b|wissensordner\w*",
                "remarkable": r"re\s?markable|notizbuch\w*", "wissensbuch": r"wissensbuch\w*",
                "mail": r"e?-?mails?\b|\w*mails?\b|nachricht\w*", "anhang": r"anh[aä]ng\w*|attachment\w*"}
MAIL_Q = ("mail", "anhang")   # the sealed mail sources: their rows go with their mailbox (ext starts with its id)


def _fm():
    import fundmail   # fundmail imports this module
    return fundmail


def on(c=None):
    """The Spark's switch for the background round, Live and the admin page; each profile asks features.allowed."""
    return features.admin_on("fund", c)


def quellen_fuer(uid, c=None):
    """The sources this profile may search: the index's own release and the function each comes from."""
    if not features.allowed("fund", uid, c):
        return []
    return [q for q in QUELLEN if features.allowed(q.feature, uid, c) and (q.name != "wissensbuch" or _wb_allowed(uid))]


# ---------------------------------------------------------------- writing
def _put(con, uid, q, e, now):
    felder = json.dumps(e.get("felder") or {}, ensure_ascii=False)[:4000]
    row = con.execute("SELECT id FROM fund_item WHERE quelle=? AND ext=?", (q.name, e["ext"])).fetchone()
    vals = (int(e.get("wann") or 0), int(e.get("geaendert") or 0), int(now), q.schutz, str(e.get("titel") or "")[:160],
            str(e.get("auszug") or "")[:AUSZUG], felder, str(e.get("stand") or "")[:2000])
    if row:
        iid = row["id"]
        con.execute("UPDATE fund_item SET wann=?, geaendert=?, gesehen=?, schutz=?, titel=?, auszug=?, felder=?, stand=? "
                    "WHERE id=?", vals + (iid,))
        con.execute("DELETE FROM fund_fts WHERE rowid=?", (iid,))
        con.execute("DELETE FROM fund_tag WHERE item=? AND herkunft='regel'", (iid,))
    else:
        iid = con.execute("INSERT INTO fund_item (quelle, ext, wann, geaendert, gesehen, schutz, titel, auszug, felder, stand) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?)", (q.name, e["ext"]) + vals).lastrowid
    con.execute("INSERT INTO fund_fts (rowid, terms) VALUES (?,?)",
                (iid, " ".join(terms(e.get("worte") or "") + [t for _, w, _ in e.get("tags") or [] for t in terms(w)])))
    for typ, wert, beleg in e.get("tags") or []:
        ok = clean_tag(typ, wert)
        mk = ok and vorrat.marke(uid, norm(ok[1]))
        if mk:   # without a key no tag (the marks need it)
            con.execute("INSERT OR REPLACE INTO fund_tag (item, typ, wert, marke, herkunft, beleg, at) VALUES (?,?,?,?,?,?,?)",
                        (iid, ok[0], ok[1], mk, "regel", int(bool(beleg)), int(now)))
    return iid


# ---------------------------------------------------------------- sealed sources (schutz 1: mail, attachments)
def _ad(uid, quelle, ext, feld):
    """What a sealed value is bound to: profile, source, entry and field (a value copied elsewhere does not open)."""
    return f"fund:{uid}:{quelle}:{ext}:{feld}"


def siegel(uid, quelle, ext, feld, text):
    return vorrat.seal(str(text or "").encode(), _ad(uid, quelle, ext, feld))


def offen(uid, quelle, ext, feld, text):
    """The plain value of a sealed one, "" when it does not open (other key, other profile, changed)."""
    raw = vorrat.unseal(text, _ad(uid, quelle, ext, feld)) if text else None
    return raw.decode("utf-8", "replace") if raw is not None else ""


def klar(uid, item):
    """(titel, auszug, felder) of a row as plain values, opened where it is sealed."""
    if not item["schutz"]:
        return item["titel"], item["auszug"], json.loads(item["felder"] or "{}")
    q, e = item["quelle"], item["ext"]
    try:
        f = json.loads(offen(uid, q, e, "felder", item["felder"]) or "{}")
    except ValueError:
        f = {}
    return offen(uid, q, e, "titel", item["titel"]), offen(uid, q, e, "auszug", item["auszug"]), f


def marken(uid, text, absender=""):
    """The blind words of a sealed entry: per word stem its mark, per stem of four letters or more the mark of its
    first four (a search word finds the longer forms, like lokal.PREFIX), per word of the sender a mark of its own
    ("@", the filters firma and person). Marks only, never a word."""
    out = set()
    for t in terms(text):
        out.add(vorrat.marke(uid, t))
        if len(t) >= 4:
            out.add(vorrat.marke(uid, "~" + t[:4]))
    for t in terms(absender):
        out.add(vorrat.marke(uid, "@" + t))
    out.discard(None)
    return sorted(out)


def put_sealed(con, uid, quelle, e, now, eltern=None):
    """One entry of a sealed source (a source's own round, in its batch's transaction): title, excerpt and fields
    AES-GCM, its words and the sender as marks, the tags with sealed values and their marks. Without a key nothing is
    written (None); in plain text stay only source, entry key and date."""
    ext = str(e["ext"])
    vals = [siegel(uid, quelle, ext, "titel", str(e.get("titel") or "")[:160]),
            siegel(uid, quelle, ext, "auszug", re.sub(r"\s+", " ", str(e.get("auszug") or ""))[:AUSZUG]),
            siegel(uid, quelle, ext, "felder", json.dumps(e.get("felder") or {}, ensure_ascii=False)[:4000])]
    mk = marken(uid, e.get("worte") or "", e.get("absender") or "")
    if None in vals or not mk:
        return None
    row = con.execute("SELECT id FROM fund_item WHERE quelle=? AND ext=?", (quelle, ext)).fetchone()
    if row:
        iid = row["id"]
        con.execute("UPDATE fund_item SET eltern=?, wann=?, geaendert=?, gesehen=?, schutz=1, titel=?, auszug=?, felder=?, "
                    "stand='' WHERE id=?", (eltern, int(e.get("wann") or 0), int(now), int(now), *vals, iid))
        con.execute("DELETE FROM fund_blind WHERE rowid=?", (iid,))
        con.execute("DELETE FROM fund_tag WHERE item=? AND herkunft='regel'", (iid,))
    else:
        iid = con.execute("INSERT INTO fund_item (quelle, ext, eltern, wann, geaendert, gesehen, schutz, titel, auszug, "
                          "felder, stand) VALUES (?,?,?,?,?,?,1,?,?,?,'')",
                          (quelle, ext, eltern, int(e.get("wann") or 0), int(now), int(now), *vals)).lastrowid
    con.execute("INSERT INTO fund_blind (rowid, marken) VALUES (?,?)", (iid, " ".join(mk)))
    for typ, wert, beleg in e.get("tags") or []:
        ok = clean_tag(typ, wert)
        m = ok and vorrat.marke(uid, norm(ok[1]))
        w = m and vorrat.seal(ok[1].encode(), _ad(uid, "tag", m, ok[0]))
        if w:
            con.execute("INSERT OR REPLACE INTO fund_tag (item, typ, wert, marke, herkunft, beleg, at) VALUES (?,?,?,?,?,?,?)",
                        (iid, ok[0], w, m, "regel", int(bool(beleg)), int(now)))
    return iid


def _tag_wert(uid, item, r):
    """A tag's value as shown: sealed for a sealed entry (bound to its mark and kind)."""
    if not item["schutz"]:
        return r["wert"]
    raw = vorrat.unseal(r["wert"], _ad(uid, "tag", r["marke"], r["typ"]))
    return raw.decode("utf-8", "replace") if raw is not None else ""


def drop_ids(con, ids):
    """Rows and everything hanging on them (an attachment goes with its mail). Returns how many."""
    ids, kids = list(dict.fromkeys(ids)), []
    for at in range(0, len(ids), 500):
        part = ids[at:at + 500]
        kids += [r[0] for r in con.execute("SELECT id FROM fund_item WHERE eltern IN (%s)" % ",".join("?" * len(part)), part)]
    every = list(dict.fromkeys(ids + kids))
    _drop(con, every)
    return len(every)


def _drop(con, ids):
    for at in range(0, len(ids), 500):
        part = ids[at:at + 500]
        q = ",".join("?" * len(part))
        con.execute(f"DELETE FROM fund_fts WHERE rowid IN ({q})", part)
        con.execute(f"DELETE FROM fund_blind WHERE rowid IN ({q})", part)
        con.execute(f"DELETE FROM fund_tag WHERE item IN ({q})", part)
        con.execute(f"DELETE FROM fund_todo WHERE item IN ({q})", part)
        con.execute(f"DELETE FROM fund_item WHERE id IN ({q})", part)


def runde(uid, now=None, budget=BUDGET, secs=None):
    """One collecting round for a profile (in a worker thread: vorrang.in_thread("Suchindex")): every source it may use
    brings what is new or changed, what is gone leaves; sources no longer allowed lose their rows. A source with a round
    of its own (mail) gets `secs` seconds (None: its own choice, 0: not this time; extras.due_once starts the mail's
    round apart, fundmail.due). Returns {source: (new, gone)}."""
    now = time.time() if now is None else now
    if not features.allowed("fund", uid):
        return {}
    mine = {x.name for x in quellen_fuer(uid)}
    out = {}
    t0 = time.time()
    for src in QUELLEN:
        if src.runde is not None:
            if src.name not in mine:
                with _Db(uid) as con:
                    gone = [r[0] for r in con.execute("SELECT id FROM fund_item WHERE quelle=?", (src.name,))]
                    if gone:
                        n = drop_ids(con, gone)
                        con.execute("DELETE FROM fund_stand WHERE quelle=?", (src.name,))
                        out[src.name] = (0, n)
                        print(f"fund: runde {src.name} | 0 neu | {n} weg | nicht freigegeben | "
                              f"{profiles.log_name(profiles.by_id(uid))}", flush=True)
                continue
            if secs == 0:
                continue
            try:
                got = src.runde(uid, now, secs)
            except Exception as e:
                with _stat_lock:
                    _stat["fehler"] += 1
                print(f"fund: runde {src.name} fehler | {type(e).__name__} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
                continue
            if got and (got[0] or got[1]):
                out[src.name] = tuple(got)
            continue
        with _Db(uid) as con:
            known = {r["ext"]: r["stand"] for r in con.execute("SELECT ext, stand FROM fund_item WHERE quelle=?", (src.name,))}
            if src.name not in mine:
                gone = [r[0] for r in con.execute("SELECT id FROM fund_item WHERE quelle=?", (src.name,))]
                if gone:
                    _drop(con, gone)
                    out[src.name] = (0, len(gone))
                continue
        try:
            entries, state, _done = src.neues_seit(uid, known, budget)
            still = src.noch_da(uid, set(known))
        except Exception as e:
            with _stat_lock:
                _stat["fehler"] += 1
            print(f"fund: runde {src.name} fehler | {type(e).__name__} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
            continue
        with _Db(uid) as con:
            for e in entries:
                _put(con, uid, src, e, now)
            gone = [r[0] for r in con.execute("SELECT id, ext FROM fund_item WHERE quelle=?", (src.name,))
                    if r[1] not in still and r[1] not in {x["ext"] for x in entries}]
            if gone:
                _drop(con, gone)
            for k, v in (state or {}).items():
                con.execute("INSERT OR REPLACE INTO fund_stand (quelle, konto, schluessel, wert) VALUES (?,?,?,?)",
                            (src.name, "", str(k)[:60], str(v)[:200]))
            con.execute("INSERT OR REPLACE INTO fund_stand (quelle, konto, schluessel, wert) VALUES (?,?,?,?)",
                        (src.name, "", "runde", str(int(now))))
        if entries or gone:
            out[src.name] = (len(entries), len(gone))
            print(f"fund: runde {src.name} | {len(entries)} neu | {len(gone)} weg | {time.time() - t0:.1f} s | "
                  f"{profiles.log_name(profiles.by_id(uid))}", flush=True)
    with _stat_lock:
        _stat["runden"] += 1
    _live["d"] = None
    return out


def _stamp(uid):
    """What the document sources depend on: when it is unchanged, a round finds nothing new (no work every 5 min)."""
    try:
        s = os.stat(documents.db_path(uid))
        return (documents._gen.get(uid, 0), s.st_ino, s.st_mtime_ns, sorted(q.name for q in quellen_fuer(uid)))
    except OSError:
        return (documents._gen.get(uid, 0), None, None, sorted(q.name for q in quellen_fuer(uid)))


async def due_once(now=None):
    """From the panel's loop (extras.due_once): at most every ROUND_S per profile, only for profiles the index is
    allowed for and whose sources moved, in a worker thread with low priority (vorrang.in_thread "Suchindex")."""
    import vorrang
    now = time.time() if now is None else now
    if not on():
        return None
    did = 0
    for uid in profiles.user_ids():
        if uid in _running or not features.allowed("fund", uid):
            continue
        _fm().due(uid, now)   # the mails: a round of their own in the background, never waited for here
        last = _last.get(uid)
        if last and now - last[0] < ROUND_S:
            continue
        stamp = _stamp(uid)
        if last and last[1] == stamp and _exists(uid):
            _last[uid] = (now, stamp)
            continue
        _running.add(uid)
        try:
            await vorrang.in_thread("Suchindex", runde, uid, now, BUDGET, 0)
            _last[uid] = (now, stamp)
            did += 1
        except Exception as e:
            print(f"fund: runde fehler | {type(e).__name__} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        finally:
            _running.discard(uid)
    return did or None


def forget(uid, quelle, konto=""):
    """An account or a source is gone: its rows leave at once (with konto only that mailbox's, whose id starts the
    entry key; fundmail finds a removed mailbox itself at its next look, fundmail.ohne_konto)."""
    if not _exists(uid) or quelle not in BY_NAME:
        return 0
    with _Db(uid) as con:
        if konto:
            ids = [r[0] for r in con.execute("SELECT id FROM fund_item WHERE quelle=? AND ext LIKE ?", (quelle, konto + ":%"))]
        else:
            ids = [r[0] for r in con.execute("SELECT id FROM fund_item WHERE quelle=?", (quelle,))]
        n = drop_ids(con, ids)
        if konto:
            con.execute("DELETE FROM fund_stand WHERE quelle=? AND konto=?", (quelle, konto))
        else:
            con.execute("DELETE FROM fund_stand WHERE quelle=?", (quelle,))
    _live["d"] = None
    print(f"fund: vergessen {quelle} | {n} weg | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return n


def leeren(uid, hand=False):
    """„Index löschen“: every table emptied, the own tags stay unless hand (its own question on the page)."""
    if not _exists(uid):
        return 0
    with _Db(uid) as con:
        n = con.execute("SELECT COUNT(*) FROM fund_item").fetchone()[0]
        for t in TABLES:
            con.execute(f"DELETE FROM {t}")
        if hand:
            con.execute("DELETE FROM fund_hand")
    _last.pop(uid, None)
    _live["d"] = None
    return n


# ---------------------------------------------------------------- own tags (S4)
def _load_list(v, uid=None, quelle="", ext="", feld=""):
    """[(typ, wert)] of an own-tag list; a sealed source's list is sealed itself ("S:" + vorrat.seal)."""
    v = v or "[]"
    if v.startswith("S:"):
        v = offen(uid, "hand", f"{quelle}:{ext}", feld, v[2:]) if uid else ""
    try:
        x = json.loads(v or "[]")
    except ValueError:
        return []
    return [(t[0], t[1]) for t in x if isinstance(t, list) and len(t) == 2 and clean_tag(t[0], t[1])] if isinstance(x, list) else []


def hand(con, quelle, ext, uid=None):
    r = con.execute("SELECT plus, minus FROM fund_hand WHERE quelle=? AND ext=?", (quelle, ext)).fetchone()
    return (_load_list(r["plus"], uid, quelle, ext, "plus"), _load_list(r["minus"], uid, quelle, ext, "minus")) if r else ([], [])


def _hand_text(uid, quelle, ext, feld, pairs):
    """An own-tag list as stored: JSON, sealed for a sealed source (its words are the person's words about a mail)."""
    v = json.dumps([list(t) for t in pairs], ensure_ascii=False)
    if BY_NAME.get(quelle) and BY_NAME[quelle].schutz:
        got = siegel(uid, "hand", f"{quelle}:{ext}", feld, v)
        if got is None:
            raise RuntimeError("no key")
        return "S:" + got
    return v


def tags_of(con, uid, item):
    """The tags shown for an item: (regel ∪ modell − minus) ∪ plus, each {"typ", "wert", "herkunft", "beleg"};
    a document's free tags come from its Steckbrief (one place for them)."""
    plus, minus = hand(con, item["quelle"], item["ext"], uid)
    gone = {(t, norm(w)) for t, w in minus}
    out, seen = [], set()
    for r in con.execute("SELECT typ, wert, marke, herkunft, beleg FROM fund_tag WHERE item=? ORDER BY herkunft, typ, marke",
                         (item["id"],)):
        wert = _tag_wert(uid, item, r)
        k = (r["typ"], norm(wert))
        if not wert or k in gone or k in seen:
            continue
        seen.add(k)
        out.append({"typ": r["typ"], "wert": wert, "herkunft": r["herkunft"], "beleg": bool(r["beleg"])})
    if item["quelle"] in ("dokument", "nas", "remarkable"):
        f = json.loads(item["felder"] or "{}")
        for w in f.get("tags") or []:
            k = ("frei", norm(w))
            if k not in seen and k not in gone:
                seen.add(k)
                out.append({"typ": "frei", "wert": w, "herkunft": "dokument", "beleg": True})
    for t, w in plus:
        k = (t, norm(w))
        out = [x for x in out if (x["typ"], norm(x["wert"])) != k]
        out.append({"typ": t, "wert": w, "herkunft": "hand", "beleg": True})
    return out


def set_hand(uid, iid, plus, minus, now=None):
    """The person's own tags of one item (the page; never a tool): plus wins over everything, minus hides a tag for
    good (a rule or the model never brings it back). Free tags of a document go to its Steckbrief instead
    (documents.set_tags). Returns the shown tags or None (no such item)."""
    now = time.time() if now is None else now
    p = [x for x in (clean_tag(*t) if isinstance(t, (list, tuple)) and len(t) == 2 else None for t in plus or []) if x]
    m = [x for x in (clean_tag(*t) if isinstance(t, (list, tuple)) and len(t) == 2 else None for t in minus or []) if x]
    with _Db(uid) as con:
        item = con.execute("SELECT * FROM fund_item WHERE id=?", (int(iid),)).fetchone()
        if not item:
            return None
        doc = item["quelle"] in ("dokument", "nas", "remarkable")
        if doc:
            frei = [w for t, w in p if t == "frei"]
            drop = {norm(w) for t, w in m if t == "frei"}
            have = json.loads(item["felder"] or "{}").get("tags") or []
            p = [x for x in p if x[0] != "frei"]
            m = [x for x in m if x[0] != "frei"]
        k = lambda t: (t[0], norm(t[1]))  # noqa: E731
        p = list({k(t): t for t in p}.values())
        m = [t for t in {k(t): t for t in m}.values() if k(t) not in {k(x) for x in p}]
        if len(p) + len(m) > MAX_HAND:
            raise ValueError("too many")
        con.execute("INSERT OR REPLACE INTO fund_hand (quelle, ext, plus, minus, at) VALUES (?,?,?,?,?)",
                    (item["quelle"], item["ext"], _hand_text(uid, item["quelle"], item["ext"], "plus", p),
                     _hand_text(uid, item["quelle"], item["ext"], "minus", m), int(now)))
    if doc and (frei or drop or have):
        new = documents.clean_tags([w for w in have if norm(w) not in drop] + frei)
        if [norm(x) for x in new] != [norm(x) for x in have]:
            documents.set_tags(uid, item["ext"], new)
            with _Db(uid) as con:
                f = json.loads(con.execute("SELECT felder FROM fund_item WHERE id=?", (int(iid),)).fetchone()[0] or "{}")
                f["tags"] = new
                con.execute("UPDATE fund_item SET felder=? WHERE id=?", (json.dumps(f, ensure_ascii=False), int(iid)))
    with _Db(uid) as con:
        item = con.execute("SELECT * FROM fund_item WHERE id=?", (int(iid),)).fetchone()
        return tags_of(con, uid, item)


# ---------------------------------------------------------------- search
def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _note(ms=None, verworfen=0, now=None):
    now = time.time() if now is None else now
    with _stat_lock:
        if _stat["day"] != _day(now):
            _stat.update(day=_day(now), suchen=0, ms=[], verworfen=0)
        if ms is not None:
            _stat["suchen"] += 1
            _stat["ms"] = (_stat["ms"] + [int(ms)])[-200:]
        _stat["verworfen"] += int(verworfen)


def _ts(day, end=False):
    """JJJJ-MM-TT -> unix time (start of the day, or its end), else None."""
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return None
    try:
        t = time.mktime(time.strptime(day, "%Y-%m-%d"))
    except (ValueError, OverflowError):
        return None
    return int(t + (86399 if end else 0))


def _tag_items(con, uid, typ, wert):
    """Items carrying this tag (rule, model or own), minus what the person took away."""
    mk = vorrat.marke(uid, norm(wert))
    ids = {r[0] for r in con.execute("SELECT item FROM fund_tag WHERE typ=? AND marke=?", (typ, mk))} if mk else set()
    want = (typ, norm(wert))
    for r in con.execute("SELECT h.plus, h.minus, h.quelle, h.ext, i.id FROM fund_hand h "
                         "JOIN fund_item i ON i.quelle=h.quelle AND i.ext=h.ext"):
        if want in {(t, norm(w)) for t, w in _load_list(r["plus"], uid, r["quelle"], r["ext"], "plus")}:
            ids.add(r["id"])
        if want in {(t, norm(w)) for t, w in _load_list(r["minus"], uid, r["quelle"], r["ext"], "minus")}:
            ids.discard(r["id"])
    if typ == "frei":   # a document's own free tags (Steckbrief)
        for r in con.execute("SELECT id, felder FROM fund_item WHERE quelle IN ('dokument','nas','remarkable')"):
            if want[1] in {norm(x) for x in json.loads(r["felder"] or "{}").get("tags") or []}:
                ids.add(r["id"])
    return ids


def _blind_from(con, uid, wert):
    """Items of sealed sources whose sender holds every word of wert (the "@" marks, fundmail)."""
    mk = [vorrat.marke(uid, "@" + t) for t in terms(wert)]
    if not mk or None in mk:
        return set()
    return {r[0] for r in con.execute("SELECT rowid FROM fund_blind WHERE fund_blind MATCH ?",
                                      (" AND ".join(f'"{m}"' for m in sorted(set(mk))),))}


def _konten(uid, mine):
    """The ids of the profile's mailboxes now (a mail of a mailbox just removed is never a hit), or None without mail."""
    if not any(n in mine for n in MAIL_Q):
        return None
    import mail
    return [a["id"] for a in mail.get(uid)["accounts"]]


def suche(uid, worte="", quelle=None, kategorie=None, firma=None, person=None, von=None, bis=None, anzahl=MAX_SHOW,
          now=None):
    """The hits of this profile: [{"id", "quelle", "ext", "titel", "wann", "auszug", "felder", "tags", "weg", "score"}]
    (a mail also "anhaenge": the attachments that matched, one card with them). Only the profile's own index and the
    sources it may use; never another profile's (its file, its marks)."""
    t0 = time.time()
    now = time.time() if now is None else now
    mine = {q.name: q for q in quellen_fuer(uid)}
    if quelle:
        mine = {k: v for k, v in mine.items() if k == quelle}
    if not mine or not _exists(uid):
        _note(0, now=now)
        return []
    worte = str(worte or "")[:MAX_WORTE]
    q = terms(worte)
    ranks = {}
    lo, hi = _ts(von) if von else None, _ts(bis, True) if bis else None
    konten = _konten(uid, mine)
    with _Db(uid) as con:
        ok_ids = None
        for typ, wert in (("kategorie", kategorie), ("firma", firma), ("person", person)):
            if wert:
                got = _tag_items(con, uid, typ, wert)
                if typ in ("firma", "person"):   # also the sender field, word for word
                    for r in con.execute("SELECT id, felder FROM fund_item WHERE schutz=0"):
                        if norm(wert) in norm(json.loads(r["felder"] or "{}").get("absender", "")):
                            got.add(r["id"])
                    got |= _blind_from(con, uid, wert)
                ok_ids = got if ok_ids is None else ok_ids & got
        cond, args = ["quelle IN (%s)" % ",".join("?" * len(mine))], list(mine)
        if konten is not None:
            cond.append("(quelle NOT IN ('mail','anhang') OR substr(ext, 1, instr(ext, ':') - 1) IN (%s))"
                        % ",".join("?" * max(1, len(konten))))
            args += konten or [""]
        if lo is not None:
            cond.append("wann >= ?")
            args.append(lo)
        if hi is not None:
            cond.append("wann <= ?")
            args.append(hi)
        where = " AND ".join(cond)
        allowed_ids = {r[0] for r in con.execute(f"SELECT id FROM fund_item WHERE {where}", args)}
        if ok_ids is not None:
            allowed_ids &= ok_ids
        if q:
            # L1: the index's own words (fields, titles, tags) and the marks of sealed sources (mail, attachments)
            rows = con.execute("SELECT rowid, bm25(fund_fts) FROM fund_fts WHERE fund_fts MATCH ? ORDER BY bm25(fund_fts) "
                               "LIMIT 200", (_match(q),)).fetchall()
            marks = [m for m in (vorrat.marke(uid, t) for t in q) if m]
            marks += [m for m in (vorrat.marke(uid, "~" + t[:4]) for t in q if len(t) > 4) if m]
            if marks:
                rows += con.execute("SELECT rowid, bm25(fund_blind) FROM fund_blind WHERE fund_blind MATCH ? "
                                    "ORDER BY bm25(fund_blind) LIMIT 200", (_match(marks),)).fetchall()
            i = 0
            for r in sorted(rows, key=lambda x: x[1]):
                if r[0] in allowed_ids and r[0] not in ranks and i < MAX_HITS:
                    ranks[r[0]] = 1 / (RRF + i)
                    i += 1
            # the own tags (fund_hand) are words of the person: found like the index's own words
            i = 0
            for r in con.execute("SELECT h.plus, h.quelle, h.ext, i.id FROM fund_hand h JOIN fund_item i ON i.quelle=h.quelle "
                                 "AND i.ext=h.ext"):
                if r["id"] in allowed_ids and i < MAX_HITS and \
                        any(set(q) & set(terms(w)) for _, w in _load_list(r["plus"], uid, r["quelle"], r["ext"], "plus")):
                    ranks[r["id"]] = ranks.get(r["id"], 0) + 1 / (RRF + i)
                    i += 1
        items = {}
        # L2: the own documents' search (BM25 on their whole text), mapped onto their index rows
        dq = [n for n in ("dokument", "nas", "remarkable") if n in mine]
        if q and dq:
            seen, i = set(), 0
            ext_id = {(r["quelle"], r["ext"]): r["id"] for r in con.execute(
                "SELECT id, quelle, ext FROM fund_item WHERE quelle IN (%s)" % ",".join("?" * len(dq)), dq)}
            for h in documents.search(uid, worte, k=MAX_HITS):
                iid = ext_id.get((_doc_source({"source": h.get("source")}), h["id"]))
                if iid is None or iid in seen or iid not in allowed_ids:
                    continue
                seen.add(iid)
                ranks[iid] = ranks.get(iid, 0) + 1 / (RRF + i)
                i += 1
        # L4: the Wissensbuch's own list once it has one (Wissenskarte thread, Stufe 1: liste(uid, worte, k))
        if q and "wissensbuch" in mine:
            import wissensbuch
            if hasattr(wissensbuch, "liste"):
                ext_id = {r["ext"]: r["id"] for r in con.execute("SELECT id, ext FROM fund_item WHERE quelle='wissensbuch'")}
                try:
                    for key, rang in wissensbuch.liste(uid, worte, MAX_HITS):
                        iid = ext_id.get(key)
                        if iid in allowed_ids:
                            ranks[iid] = ranks.get(iid, 0) + 1 / (RRF + max(0, int(rang) - 1))
                except Exception as e:
                    print("fund: wissensbuch liste", type(e).__name__, flush=True)
        if not q:   # only filters: the newest first
            for i, r in enumerate(con.execute(f"SELECT id FROM fund_item WHERE {where} ORDER BY wann DESC LIMIT 2000", args)):
                if r[0] in allowed_ids and len(ranks) < MAX_HITS:
                    ranks[r[0]] = 1 / (RRF + len(ranks))
        if not ranks:
            _note((time.time() - t0) * 1000, now=now)
            return []
        rows = con.execute("SELECT * FROM fund_item WHERE id IN (%s)" % ",".join("?" * len(ranks)), list(ranks)).fetchall()
        # an attachment's hit lifts its mail: one card, the attachment inside it (unless only attachments are asked)
        fold = quelle != "anhang" and "mail" in mine
        parents = {r["eltern"] for r in rows if r["quelle"] == "anhang" and r["eltern"]} if fold else set()
        parents = {r["id"]: r for r in con.execute("SELECT * FROM fund_item WHERE id IN (%s)" % ",".join("?" * len(parents)),
                                                   list(parents))} if parents else {}
        qs = set(q)
        inside = {}
        for r in rows:
            if fold and r["quelle"] == "anhang" and r["eltern"] in parents:
                inside.setdefault(r["eltern"], []).append(r)
                ranks[r["eltern"]] = ranks.get(r["eltern"], 0) + ranks.pop(r["id"])
        rows = [r for r in rows if r["id"] in ranks] + [p for k, p in parents.items() if k not in {r["id"] for r in rows}]
        for r in rows:
            item = dict(r)
            tags = tags_of(con, uid, item)
            for t in tags:   # fixed bonuses: an own tag counts more than one by rule or model
                if qs & set(terms(t["wert"])):
                    ranks[r["id"]] += (1.0 if t["herkunft"] == "hand" else 0.5) / RRF
            if item["geaendert"] and not item["schutz"]:
                ranks[r["id"]] += documents.FRESH * 0.5 ** (max(0, now - item["geaendert"]) / documents.FRESH_HALF)
            elif item["schutz"] and item["wann"]:   # a mail: fresh by its date
                ranks[r["id"]] += documents.FRESH * 0.5 ** (max(0, now - item["wann"]) / documents.FRESH_HALF)
            item["tags"] = tags
            item["titel"], item["auszug"], item["felder"] = klar(uid, item)
            item["anhaenge"] = []
            for a in inside.get(r["id"], []):
                at, _, af = klar(uid, a)
                item["anhaenge"].append({"id": a["id"], "titel": at, "felder": {k: v for k, v in af.items() if k in ("betrag", "nr", "kb")}})
            items[r["id"]] = item
    best = sorted(items, key=lambda x: (-ranks[x], -items[x]["wann"], x))[:max(1, min(int(anzahl or MAX_SHOW), MAX_SHOW))]
    out = []
    for iid in best:
        it = items[iid]
        f = dict(it["felder"])
        f.pop("tags", None)
        hit = {"id": iid, "quelle": it["quelle"], "ext": it["ext"], "titel": it["titel"], "wann": it["wann"],
               "auszug": it["auszug"], "felder": f, "tags": it["tags"], "weg": BY_NAME[it["quelle"]].oeffnen(uid, it["ext"]),
               "score": round(ranks[iid], 6)}
        if it["anhaenge"]:
            hit["anhaenge"] = it["anhaenge"]
        out.append(hit)
    _note((time.time() - t0) * 1000, now=now)
    return out


def eintrag(uid, iid):
    """One item with every field and the origin of each tag, or None."""
    if not _exists(uid):
        return None
    mine = {q.name for q in quellen_fuer(uid)}
    konten = _konten(uid, mine)
    with _Db(uid) as con:
        r = con.execute("SELECT * FROM fund_item WHERE id=?", (int(iid),)).fetchone()
        if not r or r["quelle"] not in mine or (r["quelle"] in MAIL_Q and r["ext"].split(":")[0] not in (konten or [])):
            return None
        item = dict(r)
        tags = tags_of(con, uid, item)
        plus, minus = hand(con, item["quelle"], item["ext"], uid)
    titel, auszug, f = klar(uid, item)
    f = dict(f)
    f.pop("tags", None)
    return {"id": item["id"], "quelle": item["quelle"], "ext": item["ext"], "titel": titel, "wann": item["wann"],
            "auszug": auszug, "felder": f, "tags": tags, "minus": [{"typ": t, "wert": w} for t, w in minus],
            "weg": BY_NAME[item["quelle"]].oeffnen(uid, item["ext"])}


def export(uid):
    """„Alle meine Daten herunterladen“ (meinedaten.LESER): the index readable, never its marks (fund_blind, the HMAC
    of each tag): per item title, time, excerpt, fields and the shown tags; and the own tags (fund_hand), which a
    rebuild never makes again; both empty without an index."""
    if not _exists(uid):
        return {"eintraege": [], "eigene_schlagworte": []}
    with _Db(uid) as con:
        items = []
        for r in con.execute("SELECT * FROM fund_item ORDER BY quelle, wann DESC"):
            item = dict(r)
            f = json.loads(item["felder"] or "{}")
            f.pop("tags", None)
            items.append({"quelle": item["quelle"], "titel": item["titel"], "wann": item["wann"],
                          "auszug": item["auszug"], "felder": f,
                          "tags": [{"typ": x["typ"], "wert": x["wert"], "herkunft": x["herkunft"]} for x in tags_of(con, uid, item)]})
        eigen = [{"quelle": r["quelle"], "ext": r["ext"], "plus": _load_list(r["plus"]), "minus": _load_list(r["minus"])}
                 for r in con.execute("SELECT quelle, ext, plus, minus FROM fund_hand ORDER BY quelle, ext")]
    return {"eintraege": items, "eigene_schlagworte": eigen}


def stand(uid, now=None):
    """The page's tab Einstellungen and Schlagworte: per source the count and the last round, the categories with their
    counts, the own tags. Numbers and the profile's own words only."""
    now = time.time() if now is None else now
    mine = [q.name for q in quellen_fuer(uid)]
    per, last, kat, eigene, total, mail_rest = {}, {}, {}, 0, 0, 0
    if _exists(uid):
        names = {vorrat.marke(uid, norm(k)): k for k in KATEGORIEN}   # sealed values: counted by their marks
        with _Db(uid) as con:
            per = dict(con.execute("SELECT quelle, COUNT(*) FROM fund_item GROUP BY quelle").fetchall())
            last = {r[0]: int(r[1]) for r in con.execute("SELECT quelle, wert FROM fund_stand WHERE schluessel='runde'")}
            for mk, n in con.execute("SELECT marke, COUNT(DISTINCT item) FROM fund_tag WHERE typ='kategorie' GROUP BY marke"):
                if names.get(mk):
                    kat[names[mk]] = kat.get(names[mk], 0) + n
            mail_rest = _rest(con)
            for r in con.execute("SELECT plus, quelle, ext FROM fund_hand"):
                for t, w in _load_list(r["plus"], uid, r["quelle"], r["ext"], "plus"):
                    eigene += 1
                    if t == "kategorie":
                        kat[w] = kat.get(w, 0) + 1
            total = sum(per.values())
    docs = 0
    if any(n in mine for n in ("dokument", "nas", "remarkable")):
        docs = sum(1 for d in documents.list_docs(uid) if d.get("state") == "ready" and _doc_source(d) in mine)
    have_docs = sum(per.get(n, 0) for n in ("dokument", "nas", "remarkable"))
    import frisch
    return {"on": True, "eintraege": total, "eigene": eigene, "laeuft": uid in _running or uid in _fm()._running,
            "mail_rest": mail_rest, "platz": bool(_fm().knapp.get(uid)),
            "quellen": [{"name": q.name, "de": q.de, "en": q.en, "an": q.name in mine, "n": per.get(q.name, 0),
                         "stand": frisch.stand(last[q.name], now) if last.get(q.name) else ""} for q in QUELLEN],
            "rueckstand": max(0, docs - have_docs),
            "kategorien": [{"wert": k, "n": kat.get(k, 0), "bereich": k in BEREICHE} for k in KATEGORIEN],
            "typen": [{"typ": k, "de": v[0], "en": v[1]} for k, v in TYP_WORT.items()]}


def _rest(con):
    """Mails of the mailboxes not read into the index yet (fundmail keeps the number per folder)."""
    return int(con.execute("SELECT COALESCE(SUM(CAST(wert AS INTEGER)), 0) FROM fund_stand WHERE quelle='mail' "
                           "AND schluessel LIKE '%:rest'").fetchone()[0] or 0)


def for_live():
    """Live-Übersicht and Zustand: summed over all profiles, numbers only (never a title, a tag or a word)."""
    if not on():
        return {"on": False}
    if _live["d"] is not None and time.time() - _live["at"] < LIVE_CACHE:
        return dict(_live["d"], running=bool(_running or _fm()._running))
    items = profs = hand_n = rest = 0
    per = {}
    for uid in profiles.user_ids():
        if not features.allowed("fund", uid) or not _exists(uid):
            continue
        profs += 1
        with _Db(uid) as con:
            for q, n in con.execute("SELECT quelle, COUNT(*) FROM fund_item GROUP BY quelle"):
                per[q] = per.get(q, 0) + n
                items += n
            hand_n += con.execute("SELECT COUNT(*) FROM fund_hand").fetchone()[0]
            rest += _rest(con)
    fm = _fm().for_live()
    with _stat_lock:
        ms = int(statistics.median(_stat["ms"])) if _stat["ms"] else None
        d = {"on": True, "eintraege": items, "profile": profs, "quellen": per, "hand": hand_n,
             "suchen": _stat["suchen"] if _stat["day"] == _day(time.time()) else 0, "ms": ms,
             "verworfen": _stat["verworfen"], "fehler": _stat["fehler"], "runden": _stat["runden"],
             "mail_on": fm["on"], "mail_rest": rest, "mail_heute": fm["heute"], "mail_fehler": fm["fehler"],
             "mail_platz": fm["platz"]}
    _live.update(at=time.time(), d=d)
    return dict(d, running=bool(_running or _fm()._running))


# ---------------------------------------------------------------- the tool fund_suche (extras.py)
FIND_VERB = re.compile(r"(?i)\b(such(e|en|st|t)?|durchsuch\w*|find(e|en|est)?|wiederfind\w*|wo (ist|sind|war|liegt|liegen|"
                       r"hab ich|habe ich)|zeig(e)? mir|search|find)\b")
FIND_OBJECT = re.compile(r"(?i)\b(\w*rechnung\w*|\w*beleg\w*|quittung\w*|\w*mail\w*|\w*brief\w*|\w*vertr[aä]g\w*|"
                         r"\w*bestellung\w*|\w*buchung\w*|foto\w*|\w*notiz\w*|\w*dokument\w*|unterlage\w*|anh[aä]ng\w*|"
                         r"pdf|scan\w*|\w*bescheid\w*|police\w*|wissensbuch\w*|invoice|receipt)\b")
FIND_OWN = re.compile(r"(?i)\b(mein(e|en|em|er|es)?|my)\b")
FIND_NOT = re.compile(r"(?i)\b(im (internet|netz|web)|online|google\w*|wikipedia|kiwix|archiv\w*)\b")


class _FindWords:
    """The Weiche's words of the group „finden“ (intent.GROUPS): a search verb and a thing of one's own (an invoice,
    a mail, a contract …, or with „such/find“ the own „mein …“), never a search in the internet or the archive."""
    pattern = FIND_VERB.pattern + "|" + FIND_OBJECT.pattern.removeprefix("(?i)")

    def search(self, text):
        import intent
        text = str(text or "")[:2000]
        v = FIND_VERB.search(text)
        if not v or FIND_NOT.search(text) or intent.SEARCH_WORDS.search(text):
            return None
        if FIND_OBJECT.search(text):
            return v
        if FIND_OWN.search(text) and re.match(r"(?i)(such|find|durchsuch|wiederfind|search)", v.group(0)):
            return v
        return None


FIND_WORDS = _FindWords()
TOOL = {"type": "function", "function": {
    "name": "fund_suche",
    "description": "Search the user's OWN data index (documents, NAS, reMarkable, Wissensbuch, e-mails with their "
                   "attachments when released): finds an item by words, "
                   "kind (Rechnung, Vertrag …), company, person or period. Returns at most five hits with source, date "
                   "and fields. Answer only from them and name source and date; never as a fact from a tag.",
    "parameters": {"type": "object", "properties": {
        "worte": {"type": "string", "description": "search words in the user's own words"},
        "quelle": {"type": "string", "enum": [q.name for q in QUELLEN]},
        "kategorie": {"type": "string", "enum": list(KATEGORIEN)},
        "firma": {"type": "string"}, "person": {"type": "string"},
        "anzahl": {"type": "integer", "minimum": 1, "maximum": TOOL_MOST}}, "required": ["worte"]}}}
HINT = ("Sucht der Nutzer etwas Eigenes (eine Rechnung, einen Vertrag, ein Dokument, eine Mail, eine Seite im Wissensbuch), "
        "ruf fund_suche mit seinen Worten. Antworte nur aus den Treffern und nenne Quelle und Datum.")


def filter_eigen(args, text):
    """The tool's filters, kept only when the person's own words of this message hold them (the panel decides, never
    the model): {filter: value}, how many were dropped. A period comes only from a year the person said."""
    own = str(text or "")[:4000]
    low, stems = own.lower(), set(terms(own))
    out, dropped = {}, 0
    for k in ("kategorie", "firma", "person"):
        v = args.get(k)
        if not v:
            continue
        v = str(v)[:MAX_TAG]
        ws = terms(v)
        if (k == "kategorie" and v in KATEGORIEN and set(ws) <= stems) or (k != "kategorie" and ws and norm(v) in norm(low)):
            out[k] = v
        else:
            dropped += 1
    qv = args.get("quelle")
    if qv:
        if qv in QUELLE_WORTE and re.search(r"(?i)\b(" + QUELLE_WORTE[qv] + r")", own):
            out["quelle"] = qv
        else:
            dropped += 1
    years = sorted(set(re.findall(r"\b(19[5-9]\d|20\d\d)\b", own)))
    if len(years) == 1:
        out["von"], out["bis"] = f"{years[0]}-01-01", f"{years[0]}-12-31"
    for k in ("von", "bis"):
        if args.get(k) and args.get(k) != out.get(k):
            dropped += 1
    return out, dropped


def _line(h, now):
    import frisch
    f = h["felder"]
    when = frisch.stand(h["wann"], now).split(",")[0] if h["wann"] else "ohne Datum"
    parts = [f"[{BY_NAME[h['quelle']].de}] {h['titel']}", f"Datum: {when}"]
    for k, label in (("absender", "Absender"), ("betrag", "Betrag"), ("nr", "Nummer"), ("name", "Datei")):
        if f.get(k):
            parts.append(f"{label}: {f[k]}")
    for a in h.get("anhaenge") or []:   # a mail with the attachment that matched (the sender's address, never „von Firma“)
        parts.append("Anhang: " + a["titel"] + "".join(f", {lab} {a['felder'][k]}" for k, lab in (("betrag", "Betrag"),
                                                                                              ("nr", "Nummer")) if a["felder"].get(k)))
    tags = [t["wert"] for t in h["tags"] if t["typ"] != "frei"][:6]
    if tags:
        parts.append("Schlagworte: " + ", ".join(tags))
    if h["auszug"]:
        parts.append(h["auszug"])
    return " | ".join(parts)[:TOOL_CHARS]


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp" \
            or not features.allowed("fund", who["id"]):
        return None
    # with the mails released a hit can be a stranger's mail: the answer counts as one that read mail (LOCKED_AFTER_MAIL)
    mails = features.allowed("fundmail", who["id"])
    return {"tools": [TOOL], "hint": HINT, "outside": {"fund_suche"}, "mail": {"fund_suche"} if mails else set(),
            "filler": {"fund_suche": ("Ich schau in deinen Sachen nach.", "Let me look through your things.")}}


async def tool(name, args, ctx):
    import asyncio
    who = ctx.get("who") or {}
    uid = who.get("id")
    if name != "fund_suche" or not uid or not features.allowed("fund", uid) or ctx.get("private") is False:
        print("fund: suche abgelehnt | aus", flush=True)
        return "Not done: Finden ist für dieses Profil aus (Funktionen → Finden in allen Daten)."
    args = args if isinstance(args, dict) else {}
    own = ctx.get("text") or ""
    flt, dropped = filter_eigen(args, own)
    worte = str(args.get("worte") or "")[:MAX_WORTE].strip() or str(own)[:MAX_WORTE]
    try:
        n = max(1, min(int(args.get("anzahl") or TOOL_MOST), TOOL_MOST))
    except (TypeError, ValueError):
        n = TOOL_MOST
    t0 = time.time()
    hits = await asyncio.to_thread(suche, uid, worte, anzahl=n, **flt)
    ms = int((time.time() - t0) * 1000)
    if dropped:
        _note(verworfen=dropped)
        print(f"fund: filter verworfen | {dropped}", flush=True)
    print(f"fund: suche | {len(hits)} treffer | {ms} ms | {profiles.log_name(who)}", flush=True)
    if ctx.get("out") is not None and hits:   # the card „In Finden ansehen“ (chat.js gotoCard, Begleiter DESK_GOTO)
        await ctx["out"].put({"type": "goto", "to": "fund", "q": worte[:120]})
    if not hits:
        return "Keine Treffer in den eigenen Daten (Finden). Sag das kurz; erfinde nichts."
    now = time.time()
    return "Treffer in den eigenen Daten (Finden), neueste Daten zuerst nach Passung:\n" + \
        "\n".join(f"{i + 1}. {_line(h, now)}" for i, h in enumerate(hits))


# ---------------------------------------------------------------- endpoints
def _need(uid):
    if not features.allowed("fund", uid):
        raise HTTPException(403, features.missing_text("fund", uid))


def _iid(iid):
    if not re.fullmatch(r"\d{1,12}", str(iid or "")):
        raise HTTPException(404, "no such entry")
    return int(iid)


def _pairs(v):
    return [(str(x.get("typ") or ""), str(x.get("wert") or "")) for x in v if isinstance(x, dict)][:MAX_HAND + 1] \
        if isinstance(v, list) else []


@router.post("/api/profile/fund/suche", dependencies=[Depends(assistant)])
async def search_route(request: Request, prof=Depends(own_profile)):
    import asyncio
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "fund", uid)
    body = await json_body(request, 4096)
    quelle = body.get("quelle") if body.get("quelle") in BY_NAME else None
    kat = body.get("kategorie") if body.get("kategorie") in KATEGORIEN else None
    von = body.get("von") if _ts(body.get("von")) is not None else None
    bis = body.get("bis") if _ts(body.get("bis")) is not None else None
    t0 = time.time()
    hits = await asyncio.to_thread(suche, uid, str(body.get("worte") or "")[:MAX_WORTE], quelle, kat, None, None, von, bis)
    print(f"fund: suche seite | {len(hits)} treffer | {int((time.time() - t0) * 1000)} ms | {profiles.log_name(prof)}", flush=True)
    return {"treffer": hits}


@router.get("/api/profile/fund/eintrag/{iid}", dependencies=[Depends(assistant)])
async def item_route(iid: str, prof=Depends(own_profile)):
    import asyncio
    _need(prof["id"])
    got = await asyncio.to_thread(eintrag, prof["id"], _iid(iid))
    if not got:
        raise HTTPException(404, "no such entry")
    return got


@router.put("/api/profile/fund/eintrag/{iid}/schlagworte", dependencies=[Depends(assistant)])
async def tags_route(iid: str, request: Request, prof=Depends(own_profile)):
    import asyncio
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "fundtag", uid)
    body = await json_body(request, 4096)
    try:
        got = await asyncio.to_thread(set_hand, uid, _iid(iid), _pairs(body.get("plus")), _pairs(body.get("minus")))
    except ValueError:
        print("fund: schlagworte abgelehnt | zu viele", flush=True)
        raise HTTPException(400, f"höchstens {MAX_HAND} eigene Schlagworte") from None
    except RuntimeError:
        print("fund: schlagworte abgelehnt | ohne schluessel", flush=True)
        raise HTTPException(503, "ohne Schlüssel nicht möglich") from None
    if got is None:
        print("fund: schlagworte abgelehnt | kein eintrag", flush=True)
        raise HTTPException(404, "no such entry")
    print(f"fund: schlagworte | {sum(1 for t in got if t['herkunft'] == 'hand')} eigene | {profiles.log_name(prof)}", flush=True)
    return {"tags": got}


@router.get("/api/profile/fund/stand", dependencies=[Depends(assistant)])
async def state_route(prof=Depends(own_profile)):
    import asyncio
    _need(prof["id"])
    return await asyncio.to_thread(stand, prof["id"])


@router.post("/api/profile/fund/neu", dependencies=[Depends(assistant)])
async def rebuild_route(request: Request, prof=Depends(browser_profile)):
    import asyncio
    import vorrang
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "fundneu", uid)
    if uid in _running:
        raise HTTPException(409, "läuft schon")
    n = await asyncio.to_thread(leeren, uid)
    print(f"fund: neu aufbauen | {n} eintraege geleert | {profiles.log_name(prof)}", flush=True)
    _running.add(uid)
    try:
        got = await vorrang.in_thread("Suchindex", runde, uid, None, BUDGET, 0)
        _last[uid] = (time.time(), _stamp(uid))
        _fm().anstossen(uid)   # the mails come again in their own round in the background, never waited for here
    finally:
        _running.discard(uid)
    return {"ok": True, "neu": sum(v[0] for v in got.values())}


@router.delete("/api/profile/fund", dependencies=[Depends(assistant)])
async def delete_route(request: Request, hand: bool = False, prof=Depends(browser_profile)):
    """„Index löschen“, also while the admin blocked Finden for this profile (own data can always be deleted)."""
    import asyncio
    uid = prof["id"]
    guard.limit(request, "fundneu", uid)
    n = await asyncio.to_thread(leeren, uid, hand)
    print(f"fund: index geloescht | {n} eintraege | eigene {'mit' if hand else 'bleiben'} | {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "geloescht": n}


@router.get("/api/admin/fund", dependencies=[Depends(auth)])
def admin_route():
    """Zustand: sums over all profiles, numbers only."""
    return for_live()


def _own_count(uid):
    if not _exists(uid):
        return 0
    with _Db(uid) as con:
        return con.execute("SELECT COUNT(*) FROM fund_item").fetchone()[0] + con.execute("SELECT COUNT(*) FROM fund_hand").fetchone()[0]


def _own_clear(uid):
    """Ich → Daten löschen while the admin blocked Finden for this profile: the index and the own tags."""
    n = leeren(uid, hand=True)
    print(f"fund: index geloescht | {n} eintraege | daten loeschen", flush=True)


features.OWN["fund"] = (_own_count, _own_clear)
