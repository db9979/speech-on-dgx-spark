"""Mappen (plan open-notebook, Stufe 1, Push 1a; Dominik 2026-10-30 „1a 2a“): a Mappe bundles own documents,
Wissensbuch pages and notes for one undertaking; per entry a context level aus / kurz / ganz decides what of it the
language model gets when a conversation is bound to the Mappe. Later the core of „Projekte im Assistenten“ (only
name, goal and symbol today, nothing more).

Fixed rules of the panel, never the model:
- aus: nothing goes to the model; kurz: the document's Steckbrief line (wissen.card_line), for a page its title and
  KURZ_SAETZE sentences; ganz: the whole text while the sum fits the budget (chat.mappe_token tokens, characters /
  verbrauch.CHARS_PER_TOKEN), else the best pieces of the full-text search over those documents for this question.
  Order: every kurz entry first, then ganz in the Mappe's order.
- Everything goes as data (chat.wrap_outside) and marks the turn like outside text (chat_turn: carry "outside"):
  writing tools stay locked for it. The Mappe a conversation uses comes only from the person's choice in the page
  (body "mappe", an own id, checked here), never from the model; a tool names a Mappe only when the person's own words
  of this message hold its name.
- Only the profile's own documents and pages; ids only from its own wissen.db (another profile's id is never found).
  Deleting a Mappe or an entry removes only the assignment, never a document.

Tables in users/<id>/wissen.db (dateien.py), next to the documents:
    mp_mappe   (id, name, ziel, symbol, made, changed, pos)      at most MAX_MAPPEN per profile
    mp_eintrag (mappe, art, ref, stufe, pos, added)              at most MAX_EINTRAEGE per Mappe
Notes are documents with source "notiz" (documents.notebook_put): searched, with Steckbrief and in Finden like any
other document, no store of their own.

Journal: „mappen: …“ (logfilter area wissen), fixed words and numbers, a profile only as profiles.log_name.
"""
import asyncio
import os
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import documents
import features
import guard
import profiles
from common import DayCounter, load_config
from core import assistant, json_body, own_profile

router = APIRouter()
MAX_MAPPEN = 50          # per profile
MAX_EINTRAEGE = 100      # per Mappe
MAX_AUF_EINMAL = 20      # entries added in one request
NAME_LEN, ZIEL_LEN = 60, 200
NOTIZ_LEN, NOTIZ_TITEL = 20_000, 80
STUFEN = ("aus", "kurz", "ganz")
ARTEN = ("dok", "seite")
SYMBOLE = ("mappe", "haus", "garten", "auto", "gesundheit", "geld", "arbeit", "reise", "lernen", "familie")
TOKEN, TOKEN_MIN, TOKEN_MAX = 24_000, 4_000, 100_000   # chat.mappe_token (config.default.json holds the default)
KURZ_SAETZE = 3          # sentences of a Wissensbuch page at the level kurz
SUCH_K = 8               # pieces the search hands over for the entries that do not fit whole
BODY = 64 * 1024         # request body of the endpoints
ID = re.compile(r"[0-9a-f]{12}")
REF = re.compile(r"[0-9a-zA-Z_-]{1,40}")
SCHEMA = """
CREATE TABLE IF NOT EXISTS mp_mappe (id TEXT PRIMARY KEY, name TEXT NOT NULL, ziel TEXT DEFAULT '',
    symbol TEXT DEFAULT 'mappe', made INTEGER, changed INTEGER, pos INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS mp_eintrag (mappe TEXT NOT NULL, art TEXT NOT NULL, ref TEXT NOT NULL,
    stufe TEXT DEFAULT 'kurz', pos INTEGER DEFAULT 0, added INTEGER, PRIMARY KEY (mappe, art, ref));
"""
HINT = ("Der Nutzer hat dieses Gespräch auf eine seiner Mappen beschränkt. Antworte aus den Einträgen der Mappe unten "
        "und nenne bei jeder Aussage den Eintrag [M…] mit Namen und Seite. Steht etwas nicht darin, sag das.")
_day = DayCounter(chats=0, abgelehnt=0, filter=0)
_live = {"at": 0.0, "data": None}
LIVE_EVERY = 60          # seconds the sums over all profiles stay remembered for the Live page


def _chat():
    return load_config().get("chat", {})


def admin_on():
    return features.admin_on("mappen")


def token_budget():
    v = _chat().get("mappe_token", TOKEN)
    return v if isinstance(v, int) and not isinstance(v, bool) and TOKEN_MIN <= v <= TOKEN_MAX else TOKEN


def zeichen_budget():
    import verbrauch
    return int(token_budget() * verbrauch.CHARS_PER_TOKEN)


def token_of(chars):
    import verbrauch
    return int(round(chars / verbrauch.CHARS_PER_TOKEN))


def _clean(v, n):
    """A name or goal the person typed: one line, no block markers or quotes that could end a data block."""
    return re.sub(r"\s+", " ", re.sub(r"<<<|>>>|[\x00-\x1f\x7f<>„“\"\\]", " ", str(v or ""))).strip()[:n]


class _Db(documents._Db):
    """The profile's wissen.db with the tables of the Mappen."""
    def __enter__(self):
        con = super().__enter__()
        try:
            con.executescript(SCHEMA)
        except BaseException:
            self.__exit__(Exception)
            raise
        return con


def _exists(uid):
    return bool(uid) and os.path.exists(documents.db_path(uid))


def _has_table(con, name):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone())


# ---------------------------------------------------------------- the entries and what they would cost
def _docs(con, ids):
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    rows = con.execute(f"SELECT * FROM docs WHERE id IN ({q})", list(ids)).fetchall()
    size = dict(con.execute(f"SELECT doc, SUM(LENGTH(text)) FROM chunks WHERE doc IN ({q}) GROUP BY doc", list(ids)).fetchall())
    return {r["id"]: dict(documents.card(r), id=r["id"], name=r["name"], source=r["source"], kind=r["kind"],
                          state=r["state"], pages=r["pages"], zeichen=int(size.get(r["id"]) or 0)) for r in rows}


def _pages(con, ids):
    if not ids or not _has_table(con, "wb_pages"):
        return {}
    q = ",".join("?" * len(ids))
    out = {r["id"]: {"id": r["id"], "title": r["title"], "art": r["art"], "saetze": []}
           for r in con.execute(f"SELECT id, title, art FROM wb_pages WHERE id IN ({q})", list(ids))}
    live = {r[0] for r in con.execute("SELECT id FROM docs")}
    for s in con.execute(f"SELECT page, text, doc FROM wb_sent WHERE page IN ({q}) ORDER BY id", list(ids)):
        if s["page"] in out and s["doc"] in live:
            out[s["page"]]["saetze"].append(s["text"])
    return out


def kurz_text(e):
    """What the level kurz hands over: the Steckbrief line of a document, title and a few sentences of a page."""
    if e["art"] == "dok":
        import wissen
        return wissen.card_line(e["info"])
    p = e["info"]
    return "„" + _clean(p["title"], 80) + "“: " + " ".join(p["saetze"][:KURZ_SAETZE])


def _ganz_page(p):
    return "„" + _clean(p["title"], 80) + "“: " + " ".join(p["saetze"])


def _rows(con, mid):
    return con.execute("SELECT * FROM mp_eintrag WHERE mappe=? ORDER BY pos, added, ref", (mid,)).fetchall()


def _entries(con, mid, page_ok):
    """The entries of a Mappe with what they are, in order; entries whose document or page is gone are dropped here
    (a page deleted in the Wissensbuch, a document missed by documents.GONE). page_ok: Wissensbuch released."""
    rows = _rows(con, mid)
    docs = _docs(con, [r["ref"] for r in rows if r["art"] == "dok"])
    pages = _pages(con, [r["ref"] for r in rows if r["art"] == "seite"])
    out, gone = [], []
    for r in rows:
        info = docs.get(r["ref"]) if r["art"] == "dok" else pages.get(r["ref"])
        if not info:
            gone.append((r["art"], r["ref"]))
            continue
        e = {"art": r["art"], "ref": r["ref"], "stufe": r["stufe"] if r["stufe"] in STUFEN else "kurz", "pos": r["pos"],
             "info": info, "grau": r["art"] == "seite" and not page_ok}
        e["kurz"] = len(kurz_text(e))
        e["ganz"] = info["zeichen"] if r["art"] == "dok" else len(_ganz_page(info))
        out.append(e)
    for art, ref in gone:
        con.execute("DELETE FROM mp_eintrag WHERE mappe=? AND art=? AND ref=?", (mid, art, ref))
    return out


def plan(entries, budget):
    """The fixed rule of the levels: every kurz entry first, then ganz in the Mappe's order while the sum fits the
    budget (characters); a ganz entry that does not fit is only searched. Returns ({(art, ref): "kurz"|"ganz"|
    "suche"|"aus"|"voll"}, characters used)."""
    used, how = 0, {}
    for e in entries:
        if e["stufe"] == "aus" or e["grau"]:
            how[(e["art"], e["ref"])] = "aus"
    for e in entries:
        if e["stufe"] == "kurz" and not e["grau"]:
            if used + e["kurz"] <= budget:
                how[(e["art"], e["ref"])] = "kurz"
                used += e["kurz"]
            else:
                how[(e["art"], e["ref"])] = "voll"
    for e in entries:
        if e["stufe"] == "ganz" and not e["grau"]:
            if used + e["ganz"] <= budget:
                how[(e["art"], e["ref"])] = "ganz"
                used += e["ganz"]
            elif e["art"] == "dok":
                how[(e["art"], e["ref"])] = "suche"
            elif used + e["kurz"] <= budget:      # a page that does not fit whole comes short
                how[(e["art"], e["ref"])] = "kurz"
                used += e["kurz"]
            else:
                how[(e["art"], e["ref"])] = "voll"
    return how, used


# ---------------------------------------------------------------- reading and changing (own profile only)
def liste(uid):
    """[{id, name, ziel, symbol, n, changed}] of the profile's Mappen, in their order."""
    if not _exists(uid):
        return []
    with _Db(uid) as con:
        # only entries whose document or page is still there (a plain delete does not call documents.GONE)
        live = "(art='dok' AND ref IN (SELECT id FROM docs))" + \
            (" OR (art='seite' AND ref IN (SELECT id FROM wb_pages))" if _has_table(con, "wb_pages") else "")
        n = dict(con.execute(f"SELECT mappe, COUNT(*) FROM mp_eintrag WHERE {live} GROUP BY mappe").fetchall())
        return [{"id": r["id"], "name": r["name"], "ziel": r["ziel"] or "", "symbol": r["symbol"] or "mappe",
                 "n": int(n.get(r["id"]) or 0), "changed": r["changed"] or 0}
                for r in con.execute("SELECT * FROM mp_mappe ORDER BY pos, made, id")]


def _get(con, mid):
    if not ID.fullmatch(str(mid or "")):
        return None
    return con.execute("SELECT * FROM mp_mappe WHERE id=?", (mid,)).fetchone()


def neu(uid, name, ziel="", symbol="mappe", now=None):
    name, ziel = _clean(name, NAME_LEN), _clean(ziel, ZIEL_LEN)
    if not name:
        raise ValueError("name")
    symbol = symbol if symbol in SYMBOLE else "mappe"
    now = int(now or time.time())
    with _Db(uid) as con:
        if con.execute("SELECT COUNT(*) FROM mp_mappe").fetchone()[0] >= MAX_MAPPEN:
            raise ValueError("grenze")
        mid = secrets.token_hex(6)
        pos = con.execute("SELECT COALESCE(MAX(pos), -1) + 1 FROM mp_mappe").fetchone()[0]
        con.execute("INSERT INTO mp_mappe (id, name, ziel, symbol, made, changed, pos) VALUES (?,?,?,?,?,?,?)",
                    (mid, name, ziel, symbol, now, now, pos))
    return mid


def aendern(uid, mid, name=None, ziel=None, symbol=None, pos=None):
    with _Db(uid) as con:
        if not _get(con, mid):
            return False
        if name is not None:
            name = _clean(name, NAME_LEN)
            if not name:
                raise ValueError("name")
            con.execute("UPDATE mp_mappe SET name=? WHERE id=?", (name, mid))
        if ziel is not None:
            con.execute("UPDATE mp_mappe SET ziel=? WHERE id=?", (_clean(ziel, ZIEL_LEN), mid))
        if symbol is not None and symbol in SYMBOLE:
            con.execute("UPDATE mp_mappe SET symbol=? WHERE id=?", (symbol, mid))
        if isinstance(pos, int) and not isinstance(pos, bool) and 0 <= pos <= MAX_MAPPEN:
            con.execute("UPDATE mp_mappe SET pos=? WHERE id=?", (pos, mid))
        con.execute("UPDATE mp_mappe SET changed=? WHERE id=?", (int(time.time()), mid))
    return True


def loeschen(uid, mid):
    """The Mappe and its assignments; never a document."""
    if not _exists(uid):
        return False
    with _Db(uid) as con:
        if not _get(con, mid):
            return False
        con.execute("DELETE FROM mp_eintrag WHERE mappe=?", (mid,))
        con.execute("DELETE FROM mp_mappe WHERE id=?", (mid,))
    return True


def _ref_ok(con, art, ref):
    if art == "dok":
        return bool(ID.fullmatch(ref)) and bool(con.execute("SELECT 1 FROM docs WHERE id=?", (ref,)).fetchone())
    return bool(REF.fullmatch(ref)) and _has_table(con, "wb_pages") \
        and bool(con.execute("SELECT 1 FROM wb_pages WHERE id=?", (ref,)).fetchone())


def dazu(uid, mid, items, now=None):
    """Adds [(art, ref, stufe)] to a Mappe: only the profile's own documents and pages (an id of another profile is
    never found in this wissen.db). Returns (added, refused) or None when there is no such Mappe; ValueError("grenze")
    above MAX_EINTRAEGE."""
    now = int(now or time.time())
    with _Db(uid) as con:
        if not _get(con, mid):
            return None
        have = con.execute("SELECT COUNT(*) FROM mp_eintrag WHERE mappe=?", (mid,)).fetchone()[0]
        pos = con.execute("SELECT COALESCE(MAX(pos), -1) + 1 FROM mp_eintrag WHERE mappe=?", (mid,)).fetchone()[0]
        added, refused = 0, 0
        for art, ref, stufe in list(items)[:MAX_AUF_EINMAL]:
            art, ref = str(art), str(ref)
            if art not in ARTEN or not _ref_ok(con, art, ref):
                refused += 1
                continue
            if con.execute("SELECT 1 FROM mp_eintrag WHERE mappe=? AND art=? AND ref=?", (mid, art, ref)).fetchone():
                continue
            if have + added >= MAX_EINTRAEGE:
                raise ValueError("grenze")
            con.execute("INSERT INTO mp_eintrag (mappe, art, ref, stufe, pos, added) VALUES (?,?,?,?,?,?)",
                        (mid, art, ref, stufe if stufe in STUFEN else "kurz", pos + added, now))
            added += 1
        if added:
            con.execute("UPDATE mp_mappe SET changed=? WHERE id=?", (now, mid))
    return added, refused


def setzen(uid, mid, art, ref, stufe=None, pos=None):
    with _Db(uid) as con:
        if not _get(con, mid) or not con.execute("SELECT 1 FROM mp_eintrag WHERE mappe=? AND art=? AND ref=?",
                                                 (mid, art, ref)).fetchone():
            return False
        if stufe in STUFEN:
            con.execute("UPDATE mp_eintrag SET stufe=? WHERE mappe=? AND art=? AND ref=?", (stufe, mid, art, ref))
        if isinstance(pos, int) and not isinstance(pos, bool) and 0 <= pos <= MAX_EINTRAEGE:
            con.execute("UPDATE mp_eintrag SET pos=? WHERE mappe=? AND art=? AND ref=?", (pos, mid, art, ref))
        con.execute("UPDATE mp_mappe SET changed=? WHERE id=?", (int(time.time()), mid))
    return True


def weg(uid, mid, art, ref):
    if not _exists(uid):
        return False
    with _Db(uid) as con:
        if not _get(con, mid):
            return False
        n = con.execute("DELETE FROM mp_eintrag WHERE mappe=? AND art=? AND ref=?", (mid, art, ref)).rowcount
    return bool(n)


def _short(e):
    """An entry as the page shows it: names and numbers, the document's own words only as plain text (textContent)."""
    i = e["info"]
    if e["art"] == "dok":
        return {"titel": i.get("title") or i["name"], "datei": i["name"], "art": i.get("art") or "", "quelle": i["source"] or "",
                "frist": i.get("due") or "", "seiten": i.get("pages") or 0}
    return {"titel": i["title"], "art": i["art"], "saetze": len(i["saetze"])}


def mappe(uid, mid):
    """One Mappe with its entries, levels and the count of what goes to the model (characters and ≈ tokens)."""
    if not _exists(uid):
        return None
    page_ok = features.allowed("wissensbuch", uid)
    with _Db(uid) as con:
        r = _get(con, mid)
        if not r:
            return None
        entries = _entries(con, mid, page_ok)
    budget = zeichen_budget()
    how, used = plan(entries, budget)
    out = [dict(_short(e), art_eintrag=e["art"], ref=e["ref"], stufe=e["stufe"], grau=e["grau"],
                geht=how[(e["art"], e["ref"])], zeichen={"kurz": e["kurz"], "ganz": e["ganz"]},
                token={"kurz": token_of(e["kurz"]), "ganz": token_of(e["ganz"])}) for e in entries]
    count = lambda w: sum(1 for x in out if x["geht"] == w)  # noqa: E731
    return {"id": r["id"], "name": r["name"], "ziel": r["ziel"] or "", "symbol": r["symbol"] or "mappe",
            "eintraege": out, "zeichen": used, "token": token_of(used), "budget": token_budget(),
            "summe": {"kurz": count("kurz"), "ganz": count("ganz"), "suche": count("suche"), "aus": count("aus"),
                      "voll": count("voll"), "wollen_ganz": sum(1 for x in out if x["stufe"] == "ganz" and not x["grau"])},
            "max_eintraege": MAX_EINTRAEGE}


def refs_of(uid, mid, stufen=("ganz",)):
    """(document ids, Wissensbuch page ids) of a Mappe at these levels, from mp_eintrag only (never fund_tag: a Mappe
    is the person's assignment, no tag). The filters of document_search and fund_suche (stufen ganz) and of the
    page Finden (every level)."""
    if not _exists(uid):
        return set(), set()
    with _Db(uid) as con:
        if not _get(con, mid):
            return set(), set()
        q = ",".join("?" * len(stufen))
        rows = con.execute(f"SELECT art, ref FROM mp_eintrag WHERE mappe=? AND stufe IN ({q})", (mid, *stufen)).fetchall()
    return {r["ref"] for r in rows if r["art"] == "dok"}, {r["ref"] for r in rows if r["art"] == "seite"}


def by_name(uid, text):
    """The Mappe whose whole name stands in the person's own words (the longest name first), or None."""
    low = " " + re.sub(r"\s+", " ", str(text or "")[:4000]).lower() + " "
    best = None
    for m in liste(uid):
        n = m["name"].lower()
        if n and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", low) and (not best or len(n) > len(best["name"])):
            best = m
    return best


def _said_ok(m, said):
    """The model's name of a Mappe fits the one the person's own words hold (or it named none)."""
    return bool(m) and (_norm(said) in ("", _norm(m["name"])) or _norm(m["name"]) in _norm(said))


SUCH_STUFEN = ("ganz",)   # the levels document_search and fund_suche search in (plan 1.4: kurz and aus are not searched)


def fuer_werkzeug(who, said, own, bound, wo="fund"):
    """The filter of document_search and fund_suche (wo: "dokumente" / "fund") by the panel's fixed rule, never the
    model's: the Mappe the tool names only when the person's own words of this message hold its name, else the Mappe
    the conversation is bound to (bound: its id, chosen by the person, checked again here). Returns ((document ids,
    page ids), the fixed sentence for the model) or (None, "") for a search without a Mappe."""
    uid = (who or {}).get("id")
    if not uid or not (said or bound):
        return None, ""
    if not features.allowed("mappen", uid):
        print(f"mappen: filter verworfen | {wo} | aus", flush=True)
        return None, ""
    m, how = None, ""
    if said:
        m = by_name(uid, own)
        if _said_ok(m, said):
            how = "worte"
        else:
            m = None
            _day.today()["abgelehnt"] += 1
            print(f"mappen: filter verworfen | {wo} | nicht in den eigenen worten |", profiles.log_name(who), flush=True)
    if not m and bound and ID.fullmatch(str(bound)):
        m = next((x for x in liste(uid) if x["id"] == bound), None)
        how = "chat" if m else ""
    if not m:
        if bound:
            print(f"mappen: filter verworfen | {wo} | fremd |", profiles.log_name(who), flush=True)
        return None, ""
    docs, pages = refs_of(uid, m["id"], SUCH_STUFEN)
    if not features.allowed("wissensbuch", uid):
        pages = set()
    _day.today()["filter"] += 1
    print(f"mappen: filter | {wo} | {how} | {len(docs)} dokumente {len(pages)} seiten |", profiles.log_name(who), flush=True)
    name = _clean(m["name"], NAME_LEN)
    if not docs and not pages:
        return (docs, pages), (f"In der Mappe „{name}“ steht kein Eintrag auf der Stufe ganz; durchsucht werden nur solche. "
                               "Sag das kurz.\n")
    return (docs, pages), f"Gesucht nur in der Mappe „{name}“ ({len(docs) + len(pages)} Einträge auf der Stufe ganz).\n"


def fuer_seite(prof, mid):
    """The filter of the page Finden (body "mappe", an own id): every entry of the Mappe whatever its level (the
    person looks herself, nothing goes to the model). Another profile's or an unknown id finds nothing, never all."""
    uid = prof["id"]
    if not features.allowed("mappen", uid):
        print("mappen: filter verworfen | seite | aus", flush=True)
        return set(), set()
    if not ID.fullmatch(str(mid or "")):
        print("mappen: filter verworfen | seite | fremd |", profiles.log_name(prof), flush=True)
        return set(), set()
    docs, pages = refs_of(uid, mid, STUFEN)
    _day.today()["filter"] += 1
    print(f"mappen: filter | seite | {len(docs)} dokumente {len(pages)} seiten |", profiles.log_name(prof), flush=True)
    return docs, pages if features.allowed("wissensbuch", uid) else set()


# ---------------------------------------------------------------- the conversation bound to a Mappe
def kontext(uid, mid, query):
    """{"text", "eintraege", "kurz", "ganz", "suche", "zeichen", "token"} for one turn, or None (no such Mappe).
    The text is the Mappe's data block for the model: entries by the fixed rule of plan(), each with its mark [M…]."""
    page_ok = features.allowed("wissensbuch", uid)
    with _Db(uid) as con:
        r = _get(con, mid)
        if not r:
            return None
        entries = _entries(con, mid, page_ok)
    budget = zeichen_budget()
    how, used = plan(entries, budget)
    lines, mark, rest = [], {}, []
    for e in entries:
        w = how[(e["art"], e["ref"])]
        if w in ("aus", "voll"):
            continue
        mark[e["ref"]] = "M" + str(len(mark) + 1)
        what = "Dokument" if e["art"] == "dok" else "Wissensbuch-Seite"
        if w == "kurz":
            lines.append(f"[{mark[e['ref']]}] {what}, Steckbrief: {kurz_text(e)}")
        elif w == "ganz" and e["art"] == "seite":
            lines.append(f"[{mark[e['ref']]}] {what}, ganz: {_ganz_page(e['info'])}")
        elif w == "ganz":
            got = documents.text_of(uid, e["ref"], most=e["ganz"] + 1) or {"parts": []}
            body = "\n".join((f"(Seite {p['page']}) " if p.get("page") else "") + p["text"] for p in got["parts"])
            lines.append(f"[{mark[e['ref']]}] {what} „{_clean(e['info'].get('title') or e['info']['name'], 80)}“, ganz:\n{body}")
        else:
            rest.append(e)
    found = 0
    if rest and str(query or "").strip():
        names = {e["ref"]: _clean(e["info"].get("title") or e["info"]["name"], 80) for e in rest}
        for h in documents.search(uid, str(query)[:500], SUCH_K, only_docs=set(names)):
            piece = f"[{mark[h['id']]}] Stelle aus „{names[h['id']]}“" + (f", Seite {h['page']}" if h.get("page") else "") \
                + ": " + h["text"]
            if used + len(piece) > budget:
                break
            lines.append(piece)
            used += len(piece)
            found += 1
    head = f"Mappe „{_clean(r['name'], NAME_LEN)}“" + (f", Ziel: {_clean(r['ziel'], ZIEL_LEN)}" if r["ziel"] else "")
    text = head + "\n" + ("\n\n".join(lines) if lines else "(In dieser Mappe geht gerade nichts an das Modell.)")
    count = lambda w: sum(1 for v in how.values() if v == w)  # noqa: E731
    return {"text": text, "eintraege": len(entries), "kurz": count("kurz"), "ganz": count("ganz"), "suche": count("suche"),
            "stellen": found, "zeichen": used, "token": token_of(used)}


def for_turn(who, mid, text):
    """chat_turn: the Mappe the person chose for this conversation (body "mappe"), when released and her own, as the
    data block and the numbers for the trace; None otherwise (the turn then runs without a Mappe)."""
    if not mid or not who:
        return None
    uid = who["id"]
    if not features.allowed("mappen", uid):
        _day.today()["abgelehnt"] += 1
        print("mappen: abgelehnt | aus", flush=True)
        return None
    got = kontext(uid, mid, text) if ID.fullmatch(str(mid)) and _exists(uid) else None
    if not got:
        _day.today()["abgelehnt"] += 1
        print("mappen: abgelehnt | fremd", profiles.log_name(who), flush=True)
        return None
    import chat
    _day.today()["chats"] += 1
    print(f"mappen: chat | {got['eintraege']} eintraege | {got['kurz']} kurz {got['ganz']} ganz {got['suche']} suche "
          f"{got['stellen']} stellen | {got['token']} token |", profiles.log_name(who), flush=True)
    return dict(got, id=mid, text=HINT + "\n" + chat.wrap_outside(got["text"]))


# ---------------------------------------------------------------- documents that went
def forget(uid, ids, why="geloescht"):
    """documents.on_gone: the entries of documents that left go at once (the documents themselves are gone already)."""
    ids = [d for d in ids or () if ID.fullmatch(str(d))]
    if not ids or not _exists(uid):
        return 0
    with documents._Db(uid) as con:
        if not _has_table(con, "mp_eintrag"):
            return 0
        q = ",".join("?" * len(ids))
        n = con.execute(f"DELETE FROM mp_eintrag WHERE art='dok' AND ref IN ({q})", ids).rowcount
    if n:
        print(f"mappen: eintrag weg | dokument {why if why in ('geloescht', 'ausgelassen') else 'geloescht'} | {n}", flush=True)
    return n


if forget not in documents.GONE:
    documents.GONE.append(forget)


# ---------------------------------------------------------------- Live (numbers only)
def for_live(now=None):
    """{"on", "mappen", "eintraege", "profile", "chats", "abgelehnt", "filter"}: sums over all profiles, remembered LIVE_EVERY s."""
    now = time.time() if now is None else now
    if not admin_on():
        return {"on": False}
    if _live["data"] is None or now - _live["at"] > LIVE_EVERY:
        m = e = p = 0
        for uid in profiles.user_ids():
            if not _exists(uid):
                continue
            try:
                with documents._Db(uid, keep=True) as con:
                    if not _has_table(con, "mp_mappe"):
                        continue
                    a = con.execute("SELECT COUNT(*) FROM mp_mappe").fetchone()[0]
                    b = con.execute("SELECT COUNT(*) FROM mp_eintrag").fetchone()[0]
            except Exception:   # noqa: BLE001  (a broken database is counted as none, never a word of it)
                continue
            m, e, p = m + a, e + b, p + (1 if a else 0)
        _live.update(at=now, data={"mappen": m, "eintraege": e, "profile": p})
    d = _day.today(now)
    return dict(_live["data"], on=True, chats=d["chats"], abgelehnt=d["abgelehnt"], filter=d["filter"])


# ---------------------------------------------------------------- tools for the model
INSIDE = {"mappe_liste"}   # only the names the person gave her own Mappen
TOOLS = [
    {"type": "function", "function": {
        "name": "mappe_liste",
        "description": "List the user's own Mappen (collections of documents, pages and notes): names and number of entries.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "mappe_stand",
        "description": "What lies in one of the user's Mappen: entry names, kinds and their context level (aus, kurz, ganz). "
                       "Not their text.",
        "parameters": {"type": "object", "properties": {"mappe": {"type": "string", "description": "the Mappe's name as the user said it"}},
                       "required": ["mappe"]}}},
    {"type": "function", "function": {
        "name": "mappe_dazu",
        "description": "Put one of the user's own documents into one of the user's Mappen, only when the user asks for it. "
                       "Both names as the user said them.",
        "parameters": {"type": "object", "properties": {
            "mappe": {"type": "string", "description": "the Mappe's name as the user said it"},
            "dokument": {"type": "string", "description": "the document's name or title as the user said it"},
            "stufe": {"type": "string", "enum": list(STUFEN)}}, "required": ["mappe", "dokument"]}}},
]
TOOL_HINT = ("Fragt der Nutzer nach seinen Mappen, ruf mappe_liste oder mappe_stand. Legt er ein Dokument in eine Mappe, "
             "ruf mappe_dazu mit seinen Worten.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp" \
            or not features.allowed("mappen", who["id"]):
        return None
    return {"tools": TOOLS, "hint": TOOL_HINT, "outside": {"mappe_stand"}, "changes": {"mappe_dazu"},
            "filler": {"mappe_stand": ("Ich schau in die Mappe.", "Let me look into the folder.")}}


def _norm(v):
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", str(v or "").lower())).strip()


def _doc_by_words(uid, said, own):
    """The one own document whose title or file name matches what the person said; the words must stand in her own
    message. Returns (doc, "") or (None, reason word)."""
    said = _norm(said)
    if not said or said not in _norm(own):
        return None, "worte"
    hits = [d for d in documents.list_docs(uid) if said in _norm(d.get("title")) or said in _norm(d["name"])]
    if len(hits) != 1:
        return None, "keins" if not hits else "mehrere"
    return hits[0], ""


async def tool(name, args, ctx):
    who = ctx.get("who") or {}
    uid = who.get("id")
    if name not in ("mappe_liste", "mappe_stand", "mappe_dazu") or not uid or not features.allowed("mappen", uid) \
            or ctx.get("private") is False:
        print("mappen: werkzeug abgelehnt | aus", flush=True)
        return "Not done: Mappen sind für dieses Profil aus (Funktionen → Mappen)."
    args = args if isinstance(args, dict) else {}
    own = ctx.get("text") or ""
    if name == "mappe_liste":
        got = await asyncio.to_thread(liste, uid)
        print(f"mappen: liste | {len(got)} |", profiles.log_name(who), flush=True)
        if not got:
            return "Der Nutzer hat noch keine Mappe (Mappen → + Neue Mappe)."
        return "Mappen des Nutzers:\n" + "\n".join(f"- {m['name']}: {m['n']} Einträge" for m in got)
    # a Mappe only from the person's own words of this message, never from the model's or a document's
    m = await asyncio.to_thread(by_name, uid, own)
    if not _said_ok(m, args.get("mappe")):
        _day.today()["abgelehnt"] += 1
        print(f"mappen: {name} abgelehnt | nicht in den eigenen worten |", profiles.log_name(who), flush=True)
        return "Not done: Nenne den Namen der Mappe in deiner Nachricht."
    if name == "mappe_stand":
        d = await asyncio.to_thread(mappe, uid, m["id"])
        print(f"mappen: stand | {len(d['eintraege'])} eintraege |", profiles.log_name(who), flush=True)
        if not d["eintraege"]:
            return f"Die Mappe „{m['name']}“ ist leer."
        say = {"aus": "aus", "kurz": "kurz", "ganz": "ganz"}
        return f"Mappe „{m['name']}“ ({d['token']} von {d['budget']} Token an das Modell):\n" + \
            "\n".join(f"- {x['titel']} ({'Dokument' if x['art_eintrag'] == 'dok' else 'Wissensbuch-Seite'}, Stufe {say[x['stufe']]})"
                      for x in d["eintraege"][:MAX_EINTRAEGE])
    doc, why = await asyncio.to_thread(_doc_by_words, uid, args.get("dokument"), own)
    if not doc:
        print(f"mappen: dazu abgelehnt | {why} |", profiles.log_name(who), flush=True)
        return {"worte": "Not done: Nenne das Dokument in deiner Nachricht.",
                "keins": "Not done: Kein eigenes Dokument passt zu diesem Namen.",
                "mehrere": "Not done: Mehrere Dokumente passen; leg es unter Mappen selbst hinein."}[why]
    stufe = args.get("stufe") if args.get("stufe") in STUFEN else "kurz"
    try:
        got = await asyncio.to_thread(dazu, uid, m["id"], [("dok", doc["id"], stufe)])
    except ValueError:
        print("mappen: dazu abgelehnt | grenze", flush=True)
        return f"Not done: Die Mappe hat schon {MAX_EINTRAEGE} Einträge."
    print(f"mappen: eintrag | dazu {got[0] if got else 0} | werkzeug |", profiles.log_name(who), flush=True)
    return f"Erledigt: „{doc.get('title') or doc['name']}“ liegt in der Mappe „{m['name']}“ (Stufe {stufe})." \
        if got and got[0] else f"Erledigt: es lag schon in der Mappe „{m['name']}“."


# ---------------------------------------------------------------- endpoints
def _need(uid):
    if not features.allowed("mappen", uid):
        raise HTTPException(403, features.missing_text("mappen", uid))


def _mid(mid):
    if not ID.fullmatch(str(mid or "")):
        raise HTTPException(404, "no such Mappe")
    return mid


def _item(body):
    art, ref = str(body.get("art") or ""), str(body.get("ref") or "")
    if art not in ARTEN or not REF.fullmatch(ref):
        raise HTTPException(400, "art und ref")
    return art, ref


@router.get("/api/profile/mappen", dependencies=[Depends(assistant)])
async def list_route(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "mappe", uid)
    got = await asyncio.to_thread(liste, uid)
    return {"mappen": got, "max": MAX_MAPPEN, "budget": token_budget(), "symbole": list(SYMBOLE)}


@router.post("/api/profile/mappen", dependencies=[Depends(assistant)])
async def new_route(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "mappe", uid)
    body = await json_body(request, BODY)
    try:
        mid = await asyncio.to_thread(neu, uid, body.get("name"), body.get("ziel"), body.get("symbol"))
    except ValueError as e:
        print(f"mappen: neu abgelehnt | {'grenze' if str(e) == 'grenze' else 'name'} |", profiles.log_name(prof), flush=True)
        raise HTTPException(400, f"Höchstens {MAX_MAPPEN} Mappen." if str(e) == "grenze" else "Name fehlt.") from None
    print("mappen: neu | 1 |", profiles.log_name(prof), flush=True)
    return {"ok": True, "id": mid}


@router.get("/api/profile/mappen/{mid}", dependencies=[Depends(assistant)])
async def one_route(mid: str, request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "mappe", uid)
    got = await asyncio.to_thread(mappe, uid, _mid(mid))
    if not got:
        raise HTTPException(404, "no such Mappe")
    return got


@router.put("/api/profile/mappen/{mid}", dependencies=[Depends(assistant)])
async def change_route(mid: str, request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "mappe", uid)
    body = await json_body(request, BODY)
    try:
        ok = await asyncio.to_thread(aendern, uid, _mid(mid), body.get("name"), body.get("ziel"), body.get("symbol"), body.get("pos"))
    except ValueError:
        print("mappen: aendern abgelehnt | name |", profiles.log_name(prof), flush=True)
        raise HTTPException(400, "Name fehlt.") from None
    if not ok:
        print("mappen: aendern abgelehnt | keine mappe |", profiles.log_name(prof), flush=True)
        raise HTTPException(404, "no such Mappe")
    print("mappen: geaendert | 1 |", profiles.log_name(prof), flush=True)
    return {"ok": True}


@router.delete("/api/profile/mappen/{mid}", dependencies=[Depends(assistant)])
async def delete_route(mid: str, request: Request, prof=Depends(own_profile)):
    """Only the assignment goes, never a document; also while the admin blocked Mappen (own data can always go)."""
    uid = prof["id"]
    guard.limit(request, "mappe", uid)
    ok = await asyncio.to_thread(loeschen, uid, _mid(mid))
    if not ok:
        print("mappen: loeschen abgelehnt | keine mappe |", profiles.log_name(prof), flush=True)
        raise HTTPException(404, "no such Mappe")
    print("mappen: geloescht | 1 |", profiles.log_name(prof), flush=True)
    return {"ok": True}


@router.post("/api/profile/mappen/{mid}/eintrag", dependencies=[Depends(assistant)])
async def add_route(mid: str, request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "mappe", uid)
    body = await json_body(request, BODY)
    raw = body.get("eintraege") if isinstance(body.get("eintraege"), list) else [body]
    if len(raw) > MAX_AUF_EINMAL:
        raise HTTPException(400, f"Höchstens {MAX_AUF_EINMAL} auf einmal.")
    items = [(*_item(x), x.get("stufe")) for x in raw if isinstance(x, dict)]
    try:
        got = await asyncio.to_thread(dazu, uid, _mid(mid), items)
    except ValueError:
        print("mappen: eintrag abgelehnt | grenze |", profiles.log_name(prof), flush=True)
        raise HTTPException(400, f"Höchstens {MAX_EINTRAEGE} Einträge je Mappe.") from None
    if got is None:
        print("mappen: eintrag abgelehnt | keine mappe |", profiles.log_name(prof), flush=True)
        raise HTTPException(404, "no such Mappe")
    print(f"mappen: eintrag | dazu {got[0]} | abgelehnt {got[1]} |", profiles.log_name(prof), flush=True)
    return {"ok": True, "dazu": got[0], "abgelehnt": got[1]}


@router.put("/api/profile/mappen/{mid}/eintrag", dependencies=[Depends(assistant)])
async def level_route(mid: str, request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "mappe", uid)
    body = await json_body(request, BODY)
    art, ref = _item(body)
    stufe = body.get("stufe") if body.get("stufe") in STUFEN else None
    ok = await asyncio.to_thread(setzen, uid, _mid(mid), art, ref, stufe, body.get("pos"))
    if not ok:
        print("mappen: stufe abgelehnt | kein eintrag |", profiles.log_name(prof), flush=True)
        raise HTTPException(404, "no such entry")
    print(f"mappen: stufe | {stufe or 'reihenfolge'} 1 |", profiles.log_name(prof), flush=True)
    return {"ok": True}


@router.delete("/api/profile/mappen/{mid}/eintrag", dependencies=[Depends(assistant)])
async def remove_route(mid: str, request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    guard.limit(request, "mappe", uid)
    body = await json_body(request, BODY)
    art, ref = _item(body)
    ok = await asyncio.to_thread(weg, uid, _mid(mid), art, ref)
    if not ok:
        print("mappen: eintrag weg abgelehnt | kein eintrag |", profiles.log_name(prof), flush=True)
        raise HTTPException(404, "no such entry")
    print("mappen: eintrag weg | 1 |", profiles.log_name(prof), flush=True)
    return {"ok": True}


def _notiz(uid, mid, titel, text):
    import wissen
    if documents.usage_total(uid) >= wissen.quota_bytes(uid):
        raise ValueError("platz")
    with _Db(uid) as con:
        if not _get(con, mid):
            return None
    doc, _ = documents.notebook_put(uid, None, titel, [(1, text, None)], source="notiz")
    dazu(uid, mid, [("dok", doc, "ganz")])
    return doc


@router.post("/api/profile/mappen/{mid}/notiz", dependencies=[Depends(assistant)])
async def note_route(mid: str, request: Request, prof=Depends(own_profile)):
    """A note becomes an own document (source "notiz") and an entry of the Mappe at the level ganz."""
    uid = prof["id"]
    _need(uid)
    if features.blocked("documents", uid) or not features.allowed("documents", uid):
        raise HTTPException(403, features.missing_text("documents", uid))
    guard.limit(request, "mappe", uid)
    body = await json_body(request, BODY)
    titel = _clean(body.get("titel"), NOTIZ_TITEL) or "Notiz"
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(body.get("text") or "")).strip()
    if not text or len(text) > NOTIZ_LEN:
        print("mappen: notiz abgelehnt | laenge |", profiles.log_name(prof), flush=True)
        raise HTTPException(400, f"Eine Notiz hat 1 bis {NOTIZ_LEN} Zeichen.")
    try:
        doc = await asyncio.to_thread(_notiz, uid, _mid(mid), titel, text)
    except ValueError as e:
        why = "platz" if str(e) == "platz" else "grenze"
        print(f"mappen: notiz abgelehnt | {why} |", profiles.log_name(prof), flush=True)
        raise HTTPException(400, "Der Platz für Dokumente ist voll." if why == "platz"
                            else f"Höchstens {documents.MAX_DOCS} Dokumente oder {MAX_EINTRAEGE} Einträge.") from None
    if not doc:
        print("mappen: notiz abgelehnt | keine mappe |", profiles.log_name(prof), flush=True)
        raise HTTPException(404, "no such Mappe")
    print(f"mappen: notiz | 1 | {len(text)} zeichen |", profiles.log_name(prof), flush=True)
    return {"ok": True, "doc": doc}


def _own_count(uid):
    if not _exists(uid):
        return 0
    with _Db(uid) as con:
        return con.execute("SELECT COUNT(*) FROM mp_mappe").fetchone()[0]


def _own_clear(uid):
    """Ich → Daten löschen while the admin blocked Mappen: every Mappe and assignment, never a document."""
    if not _exists(uid):
        return
    with _Db(uid) as con:
        n = con.execute("DELETE FROM mp_mappe").rowcount
        con.execute("DELETE FROM mp_eintrag")
    print(f"mappen: geloescht | {n} | daten loeschen", flush=True)


features.OWN["mappen"] = (_own_count, _own_clear)
